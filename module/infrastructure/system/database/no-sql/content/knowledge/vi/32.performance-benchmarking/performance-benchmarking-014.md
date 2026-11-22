# So sánh trước/sau thay đổi với cấu hình và điều kiện được ghi lại

## 1. Vấn đề: “sau khi tối ưu nhanh hơn” có nghĩa gì?

Một nhóm Java vận hành hệ thống NoSQL báo cáo:

> “Sau khi thêm index mới, p99 giảm từ 120 ms xuống 45 ms và throughput tăng 30%.”

Đây là một kết quả đáng chú ý, nhưng chưa đủ để khẳng định index là nguyên nhân. Giữa hai lần đo, có thể đã xảy ra những thay đổi khác:

- Dataset nhỏ đi do TTL cleanup.
- Cache đã được làm nóng ở lần đo sau.
- Driver được nâng cấp hoặc thay đổi kích thước connection pool.
- Load generator ở một máy khác, gần cụm database hơn.
- Tải thực tế giảm trong giờ thấp điểm.
- Index build hoàn tất, nhưng compaction của lần đo trước chưa hoàn tất.
- Một số requests ở lần sau timeout và bị loại khỏi phép tính p99.
- Truy vấn thay đổi projection, consistency hoặc số records trả về.
- Hệ có thêm replica/shard nhưng không ghi vào báo cáo.

Vì vậy, **so sánh trước/sau (before/after comparison)** không đơn thuần là đo hai lần; nó là một thí nghiệm có thiết kế, ghi lại **biến được thay đổi, điều kiện giữ nguyên, cách lấy mẫu, tiêu chí thành công và mức độ chắc chắn của kết luận**.

Trong chương **Hiệu năng và đo tải** của **Database No SQL**, bài này hướng dẫn tổ chức các phép so sánh có thể tái lập và có thể kiểm chứng, cho cả tối ưu truy vấn, driver Java, bộ nhớ đệm, partitioning, replication, transaction và hệ thống tích hợp.

**Nguyên tắc:** không hỏi chỉ “đã nhanh hơn bao nhiêu?”, mà hỏi “nhanh hơn trên cùng thao tác và điều kiện nào, đo ra sao, có đổi correctness hay chi phí không, và khác biệt ấy có thật sự đến từ thay đổi được thử?”.

## 2. Từ thay đổi kỹ thuật đến giả thuyết đo được

Giả sử hệ có thao tác:

```text
GET /customers/U42/orders?status=PAID&limit=50
```

Nhóm định thêm compound index vào MongoDB.

Một giả thuyết tốt:

> Với 12 triệu đơn hàng, truy vấn theo `customerId + status + createdAt` sẽ giảm p99 của **driver-level query latency** ít nhất 25% ở offered load 2.000 req/s, trong khi tỷ lệ lỗi không tăng, kết quả trả về giữ nguyên và write throughput không giảm quá 5%.

Giả thuyết này xác định:

1. **Đối tượng:** truy vấn nào.
2. **Treatment:** thêm index cụ thể.
3. **Baseline:** cấu hình hiện tại không có index ấy.
4. **Dữ liệu:** volume và phân phối.
5. **Load:** arrival model/tốc độ.
6. **Metric chính:** p99 query latency.
7. **Mức thay đổi quan trọng:** ít nhất 25%.
8. **Guardrails:** errors, correctness, write throughput.
9. **Cửa sổ:** phải bổ sung thời lượng, warmup và số lần lặp.

Một phát biểu yếu:

> “Thêm index giúp NoSQL nhanh hơn.”

Nó không đủ cụ thể để quyết định nên triển khai hay rollback.

## 3. Định nghĩa baseline, candidate và treatment

- **Baseline (A):** hệ hiện tại trước thay đổi, gồm toàn bộ cấu hình, dữ liệu và cách đo.
- **Candidate/treatment (B):** hệ sau khi áp dụng đúng thay đổi đang được kiểm chứng.
- **Controlled variables:** những yếu tố cần giữ tương đương giữa A và B.
- **Confounders:** yếu tố khác đồng thời thay đổi và có thể gây sai lệch.
- **Outcome/response variables:** latency, throughput, error, cost, correctness...
- **Guardrail metrics:** các chỉ số không được xấu quá ngưỡng.

### 3.1. Một biến thay đổi, nhiều chỉ số được quan sát

Ví dụ thay đổi **index** là treatment, còn read latency, write latency, index storage, ingestion lag và compaction là outcomes. Không nên coi việc nhiều metrics thay đổi là “nhiều treatments”.

### 3.2. Nhiều changes cùng lúc

Nếu đồng thời:

```text
A -> B:
  + compound index
  + tăng pool 100 -> 400
  + bật Redis cache
  + đổi write concern
```

và p99 giảm, không thể quy kết mức giảm cho **compound index** riêng lẻ. Đây là thử nghiệm một **gói changes**, không phải cô lập tác động của từng change.

### 3.3. Đúng câu hỏi trước

Có hai câu hỏi khác nhau:

- *“Gói cấu hình release B có tốt hơn release A không?”* Có thể so cả gói.
- *“Chính index mới cải thiện được bao nhiêu?”* Cần kiểm soát những thay đổi còn lại hoặc thiết kế nhiều nhánh thí nghiệm.

Ghi rõ câu hỏi ngay đầu báo cáo.

## 4. Một so sánh có ba lớp bằng chứng

```text
                Giả thuyết thay đổi
                         |
            +------------+-------------+
            |            |             |
            v            v             v
       Tương đương    Hiệu năng     Tính đúng đắn
       điều kiện A/B  latency/QPS    invariant/data
            |            |             |
            +------------+-------------+
                         |
                         v
               Kết luận có điều kiện
```

Một quyết định tối ưu đáng tin cần:

1. **Bằng chứng tính tương đương:** workload, dataset, hardware và những điều kiện trọng yếu có thể so.
2. **Bằng chứng hiệu năng:** nhiều metrics, nhiều mức tải, biến thiên và sai số.
3. **Bằng chứng correctness:** kết quả trả về, consistency, durability, semantics của operations không bị thay đổi ngoài chủ đích.

Nếu B nhanh hơn do lược bỏ validation hoặc đọc dữ liệu stale trái yêu cầu, B **không phải tối ưu tương đương**.

## 5. Định nghĩa thao tác giống nhau ở A và B

Một phép so sánh đầu tiên cần thống nhất **operation contract**.

Ví dụ:

```yaml
operation:
  name: GetOrderById
  request: "read order O100 from authoritative database"
  result: "one order; 14 requested fields"
  payloadP50Bytes: 2048
  readConsistency: "primary read; exact config recorded"
  onNotFound: "valid absence, counted separately"
  start: "before synchronous Java driver call"
  end: "after result decode or exception"
  timeoutMs: 250
  retries: "disabled for controlled baseline comparison"
```

Đây là tài liệu thí nghiệm, không phải YAML cấu hình chạy trực tiếp.

### 5.1. Một GET có thay đổi nội dung trả về không?

Nếu A trả full document còn B chỉ trả `id,status`, sự khác biệt có thể đến từ **projection**, không phải index hoặc driver.

### 5.2. Một query có thay đổi semantics không?

`WHERE status='PAID'` khác `WHERE status IN ('PAID','CAPTURED')`. Hai phép đo không cùng workload nếu tập kết quả khác.

### 5.3. Một batch không bằng một item

Một RPC ghi 100 items không so với một RPC ghi 1 item chỉ bằng `requests/s`; báo thêm successful items/s.

### 5.4. Một workflow không bằng một DB command

Checkout qua Order, Inventory, Payment không thể so trực tiếp với latency của một DynamoDB `UpdateItem` và gọi cả hai là “checkout latency”.

## 6. Measurement boundary phải nhất quán

Sơ đồ:

```text
Client
   |
   v
Gateway
   |
   v
Java API  --> Redis Cache
   |
   v
Repository / SDK
   |
   v
NoSQL Coordinator
   |
   v
Storage/Replica
```

Các phép đo có thể là:

| Boundary | Mốc bắt đầu → kết thúc | Ý nghĩa |
|---|---|---|
| HTTP end-to-end | Client gửi → nhận response | Người dùng thấy gì |
| Java handler | Vào handler → hoàn thành response | Application-side processing |
| Repository method | Gọi DAO → return/throw | Mapping + driver + DB |
| Driver call | Trước command → nhận result/error | Pool/network/server/retry |
| Server execution | Server nhận → xử lý xong | Database internal service time |
| Transaction | Begin → commit ACK/abort | Toàn transaction scope |
| CDC freshness | Source commit → sink query visible | End-to-end propagation |
| Business workflow | Create intent → confirmed/final state | Nhiều services |

**A driver p99=18 ms và B HTTP p99=45 ms không phải hai số so sánh trực tiếp**, dù cùng thao tác đọc dữ liệu.

### 6.1. Đo song song nhiều boundary

Để giải thích nguồn cải thiện, có thể đo cả end-to-end, driver, server, pool wait, cache và JVM. Nhưng cần giữ **metric chính** cố định; các số khác là bằng chứng chẩn đoán.

### 6.2. Không cộng p99 các thành phần

Percentiles không tuyến tính. p99 của gateway + p99 của driver không tự bằng p99 HTTP.

### 6.3. Đừng đổi đơn vị

Thống nhất ms, µs, req/s, ops/s, bytes/s; ghi MB (10^6) hay MiB (2^20) rõ ràng.

## 7. Cấu hình database phải có ảnh chụp trước/sau

Không đủ ghi “MongoDB 3 nodes” hoặc “Cassandra 6 nodes”. Cần lưu các thông tin ảnh hưởng performance:

- Database engine/version/edition.
- Node count, CPU cores, RAM, instance type.
- Disk loại, size, IOPS/bandwidth/throttling.
- Replica factor, quorum/write concern/read consistency.
- Shard/partition count và partitioning policy.
- Index definitions và index build status.
- Compression, cache sizes, memory/heap limits.
- Compaction/flush policies nếu liên quan.
- Rate limits, provisioned/on-demand capacity.
- Transaction/serial consistency config.
- Backup, repair, CDC và monitoring workloads.
- Topology AZ/region, network distances.
- Maintenance/rollout/migration states.
- Node health và replication lag.

### 7.1. Version cụ thể

“Phiên bản mới hơn” không đủ. Ghi semantic version/build, feature flags và compatibility mode. Một patch release có thể thay query planner hoặc connection management.

### 7.2. Topology mới có là treatment không?

Nếu B tăng từ 3 lên 6 nodes, đây là **scale-out experiment**, không phải “tối ưu SQL/NoSQL query thuần”. So cả chi phí và hiệu suất trên mỗi đơn vị tài nguyên.

### 7.3. Managed service

Ghi region, plan/tier, autoscaling mode, capacity caps, provisioned throughput và service limits. Một autoscaling event xảy ra trong B có thể làm mất tính tương đương.

## 8. Cấu hình Java, driver và ứng dụng

Một thay đổi nhỏ ở Java có thể tác động lớn đến phép đo NoSQL.

| Nhóm | Thông số nên ghi |
|---|---|
| Runtime | Java version, JVM flags, GC, heap, container CPU/memory |
| Driver | Library version, sync/async/reactive, timeouts |
| Connections | Pool min/max, idle TTL, wait queue |
| Retry | Max attempts, backoff, jitter, retryable error classes |
| Serialization | BSON/JSON/Protobuf, POJO mapper/version |
| Threads | Worker pool, event-loop, virtual threads nếu dùng |
| Spring | Spring Boot/Data version, cache/repository annotations |
| Query execution | Batch size, page size, projection, consistency |
| Telemetry | Metrics/logging/tracing sampling |
| Security | TLS, connection auth, compression |
| JVM warmup | JIT, class loading, hot code paths |

### 8.1. Native driver vs mapper

Nếu A dùng raw MongoDB `Document` còn B chuyển sang `Spring Data MongoRepository`, phép đo repository latency gồm mapping và abstraction overhead có thể thay đổi. Cần phân biệt **driver-level** và **application-level** effects.

### 8.2. Pool size

Pool 50 vs 200 có thể thay queue time. Nếu mục tiêu là đánh giá index, giữ pool tương đương hoặc công bố đây là biến khác.

### 8.3. Tracing

Bật full tracing ở một phía và tắt phía kia là confounder. Có thể dùng sampling đồng nhất hoặc đo instrumentation overhead riêng.

### 8.4. JIT/GC

Một lần chạy B sau khi JVM đã warm còn A trong cold start có thể khiến B đẹp hơn không vì database. Warmup và đo JVM GC pauses phải có chủ ý.

## 9. Dataset: không chỉ số lượng records

Hai datasets cùng 10 triệu documents vẫn có hiệu năng khác nhau nếu:

- Document size distribution khác.
- Fields có cardinality/selectivity khác.
- Tỷ lệ null/missing khác.
- Keys và tenants phân phối khác.
- Dữ liệu nén được nhiều/ít khác.
- Có nhiều updates/deletes/tombstones.
- Index sizes khác.
- Working set có vừa RAM/page cache không.
- TTL đã xóa dữ liệu trước B.
- Archive/partition age khác.

### 9.1. Mô tả dataset

```yaml
dataset:
  totalDocuments: 12000000
  p50DocumentBytes: 1800
  p95DocumentBytes: 12500
  maxDocumentBytes: 450000
  tenants: 12000
  hotKeyDistribution: "Zipfian, parameter recorded"
  recentWritesPercent: 15
  deletedOrExpiredPercent: 8
  indexes: ["_id", "customerId_createdAt"]
  seed: 20261114
```

### 9.2. Cùng snapshot có lợi nhưng chưa đủ

Clone A và B từ cùng snapshot giảm sai lệch dữ liệu. Tuy nhiên, sau khi chạy workloads, compaction/index/caches có thể diverge. Ghi thời điểm clone, cách restore và giai đoạn warmup.

### 9.3. Khi không thể clone dataset

Production A/B có thể phải dùng data slicing/tenant cohorts và điều chỉnh theo thực tế. Khi ấy cần nói rõ kết luận mang tính quan sát nhiều hơn thí nghiệm kiểm soát.

### 9.4. Dữ liệu bí mật

Không sao chép PII/payment credentials vào benchmark mà thiếu quyền và kiểm soát. Có thể dùng dữ liệu tổng hợp có phân phối thống kê tương tự.

## 10. Key distribution và hot partitions

Một test dùng uniform keys có thể báo p99 tuyệt đẹp; production có một tenant chiếm 60% lưu lượng khiến một partition nóng.

Phân phối thường gặp:

- Uniform.
- Zipfian.
- Hotset 80/20.
- Sequential inserts.
- Latest/newest records.
- Tenant-weighted.
- Day/night time windows.
- Geographic locality.
- Burst/tải sự kiện.

### 10.1. Cố định seed?

Cùng random seed và keyspace giúp so các runs trên tập requests tương tự. Nhưng chỉ một seed có thể bị tình cờ thuận lợi; có thể thực hiện nhiều seeds đã định trước.

### 10.2. Cùng key distribution, khác physical placement

Khi đổi partition key/sharding, cùng logical key distribution nhưng physical hotspot có thể khác — chính đó là outcome cần đo.

### 10.3. “Nhiều node” không cứu một key nóng

Nếu mọi writes cần serialize trên một logical key/leader, tăng node count có thể không tăng capacity tương ứng.

### 10.4. Đo theo tenant/partition

Ghi p99 và throttling theo tenant/key class, không chỉ cluster average.

## 11. Workload mix: đọc, ghi, scan và transaction

Bảng ví dụ:

| Operation | Tỷ trọng request | Định nghĩa |
|---|---:|---|
| GetOrderById | 50% | Point read, 2 KiB, key tồn tại |
| ListOrdersByCustomer | 20% | Index query, page 50 |
| UpdateOrderStatus | 15% | Conditional update, expected version |
| CreateOrder | 10% | Insert + unique operation ID |
| ArchiveOldOrders | 5% | Batch/scan có phân trang |

Một benchmark chỉ dùng 100% GET có thể đánh giá cao một index mới mà không thấy write amplification.

### 11.1. Tỷ trọng phải dùng chung mẫu số

Nếu các phần trăm là **requests**, không đổi sang phần trăm **items** hoặc **bytes** giữa hai run.

### 11.2. Mixed vs isolated workloads

Đo riêng reads/writes giúp tìm bottleneck; đo hỗn hợp mô phỏng resource contention thực tế. Báo cả hai nếu cần.

### 11.3. Workload thay đổi theo giờ

A được đo giờ cao điểm và B giờ khuya không tương đương. Dùng reproducible generator hoặc phương pháp canary/paired observation có điều chỉnh.

## 12. Offered load, achieved throughput và goodput

Dùng cùng thuật ngữ:

\[
\text{Offered RPS}=\frac{N_{\text{scheduled arrivals}}}{\Delta t}
\]

\[
\text{Completed RPS}=\frac{N_{\text{completed requests}}}{\Delta t}
\]

\[
\text{Goodput}=\frac{N_{\text{successful, correct operations}}}{\Delta t}
\]

Ví dụ trong 60 giây:

```text
Scheduled:       300,000 requests -> 5,000 offered req/s
Completed:       282,000 requests -> 4,700 completed req/s
Correct success: 279,000 requests -> 4,650 good ops/s
Failures:          3,000
Pending at cutoff:18,000
```

**Không gọi 5.000 req/s là throughput của database khi hệ chỉ hoàn tất 4.700/s.**

### 12.1. Ghi tất cả outcomes

Success, not-found đúng, CAS conflict, timeout, throttle, HTTP 5xx, validation error, canceled và unknown write outcome cần được phân nhóm theo operation contract.

### 12.2. Đếm retry đúng

Một logical request có thể tạo ba physical DB attempts. Đo logical end-to-end latency và physical attempt rate riêng.

### 12.3. Không cải thiện bằng cách bỏ lỗi khỏi thống kê

Nếu B trả error nhanh hơn A, p99 success-only có thể giảm trong khi user success giảm. Guardrails phải phát hiện điều đó.

## 13. Open-loop và closed-loop làm phép so khác nhau

**Open-loop:** requests đến theo lịch tương đối độc lập với thời gian hoàn tất requests cũ.

**Closed-loop:** mỗi worker chờ response rồi mới phát request tiếp.

```text
Open-loop:
  issue at scheduled times -> queue may grow

Closed-loop:
  request -> response -> next request
```

### 13.1. Vì sao phải chọn trước?

Khi hệ chậm, closed-loop tự giảm arrival rate và có thể tạo **coordinated omission**, khiến tail latency trông tốt hơn workload thực có arrivals độc lập.

### 13.2. Không đổi model giữa A và B

A open-loop 3.000 RPS và B closed-loop 200 workers không phải một cặp so sánh trực tiếp, ngay cả khi observed goodput gần bằng nhau.

### 13.3. Cùng offered load

Để đánh giá p99 tại cùng traffic, thử A và B với **cùng scheduled arrival rate**; nếu B không thể đạt nó, vẫn ghi pending/errors, không tự giảm load để B đạt SLO rồi nói “p99 thấp hơn”.

### 13.4. Cùng concurrency

Một bài riêng có thể cố định 100/200/400 concurrent workers để xem throughput và latency theo worker count. Nêu rõ đó là closed-loop concurrency sweep, không phải fixed-arrival test.

## 14. Warmup, cold-start và cache conditions

Một phép đo tốt thường tách:

```text
Prepare -> Warmup -> Ramp -> Steady-state measurement -> Drain
```

Nhưng **cold-start** cũng có thể là đối tượng đo riêng:

- Cold Java JVM/JIT.
- Cold connection pool.
- Empty Redis cache.
- OS page cache lạnh.
- Database buffer cache lạnh.
- New index chưa warm.
- Một node vừa restart sau failover.

### 14.1. Không để A lạnh, B nóng

A chạy trước có thể làm nóng page cache; B chạy sau được hưởng lợi. Một chuỗi A rồi B duy nhất thường thiếu tính kiểm soát.

### 14.2. Cách giảm carry-over

- Warm cả hai theo cùng policy.
- Randomize thứ tự chạy.
- Dùng ABBA/BAAB paired runs trong môi trường có thể quay lại cấu hình.
- Tách cold và warm benchmarks.
- Reset cache chỉ khi hợp đồng thử nghiệm yêu cầu.
- Ghi lại cache hit rate/page cache và sự thay đổi qua thời gian.

### 14.3. Cache hit ratio là biến quan trọng

A cache hit=40%, B hit=95% có thể giải thích phần lớn cải thiện latency. Nếu bật cache là treatment, đó chính là hiệu ứng cần đo; nếu đang thử index, đây là confounder.

### 14.4. Chú ý TTL

Chạy trong 10 phút khi TTL=30 phút không cho thấy cache expiry storm hoặc refresh behavior.

## 15. Compaction, TTL, GC và trạng thái ổn định

Một số NoSQL dùng LSM storage, tạo công việc nền:

- Memtable flush.
- SSTable compaction.
- Tombstone cleanup.
- Index maintenance.
- Repair.
- Replication catch-up.
- Backup/snapshot.
- TTL expiration.
- Storage reclamation.

### 15.1. Tránh benchmark quá ngắn

Nếu B chạy ngay sau khi dữ liệu vừa nạp và chưa có compaction, throughput ngắn hạn có thể cao hơn long-run throughput.

### 15.2. Đo trạng thái ổn định

Trong run đủ dài, quan sát CPU/disk, pending compactions, backlog, heap/GC và p99. Không kết luận sustained capacity nếu backlog tăng mãi.

### 15.3. Snapshot condition

Nếu A chạy lúc cluster đang backup, B không backup, khác biệt không nhất thiết do code.

### 15.4. Bản ghi “đang chạy maintenance” là dữ liệu, không chỉ ghi chú

Có thể loại run theo tiêu chí đã định trước hoặc phân nhóm maintenance/no-maintenance. Không chọn bỏ một run chỉ vì kết quả xấu sau khi đã nhìn thấy.

## 16. Cô lập thay đổi và quản lý confounders

Ví dụ treatment là `MongoDB add compound index`:

```text
CONTROLLED:
  MongoDB version, node count, instance size
  Dataset, keys, query, projection
  Java version, driver, pool
  Load generator, offered load
  Read concern, read preference
  Warmup and measurement duration

TREATMENT:
  index {customerId:1,status:1,createdAt:-1}

OBSERVED:
  latency, goodput, write cost, index size
  query plan, scanned keys/docs, CPU/disk
```

### 16.1. Khi có biến không giữ được

Ghi rõ:

```text
Known deviation:
  B ran on different availability zone
  median network RTT increased 2ms
```

Không xóa dòng này để bảng trông đẹp.

### 16.2. “Chỉ một biến” không phải quy tắc máy móc

Trong production, migration có thể buộc đi kèm index rebuild, schema rewrite và code change. Khi không cô lập được, hãy nói rõ tác động đo là **tác động của gói rollout**.

### 16.3. Không giải thích nguyên nhân từ tương quan đơn giản

“Sau thay đổi” là quan hệ thời gian; không tự là “do thay đổi”. Có thể dùng controls/canary/repeated reversal để tăng độ tin cậy.

## 17. Chọn thứ tự chạy: A/B, A/B/A và ABBA

Một thử nghiệm đơn giản:

```text
Run 1: A
Run 2: B
```

có rủi ro drift theo thời gian.

Các mẫu tốt hơn khi khả thi:

```text
A -> B -> A
```

hoặc:

```text
A -> B -> B -> A
B -> A -> A -> B
```

### 17.1. Vì sao đảo thứ tự?

Nếu môi trường ấm dần hoặc noisy neighbor thay đổi, so xen kẽ có thể giảm bias do thời điểm.

### 17.2. Nếu thay đổi không thể đảo ngay

Ví dụ migration partition key làm rewrite dữ liệu. Có thể dùng clone hai cụm từ cùng snapshot và chạy song song có kiểm soát, hoặc nhiều paired runs từ nguồn dữ liệu tương đương.

### 17.3. Không chạy A và B cùng hạ tầng khi tranh tài nguyên

Hai test cùng dùng shared disk/network/cluster có thể gây interference. Nếu cần concurrency, phải xem đó là thí nghiệm sharing resources chứ không phải isolated before/after.

### 17.4. Thứ tự phải được ghi trước

Tránh chạy đi chạy lại B đến khi có kết quả đẹp rồi chỉ công bố lượt tốt nhất.

## 18. Repeated runs và biến thiên

Một phép đo p99 duy nhất không mô tả uncertainty.

Ví dụ 5 lần chạy cùng mức tải:

| Run | A p99 (ms) | B p99 (ms) | B/A ratio |
|---|---:|---:|---:|
| 1 | 95 | 68 | 0,716 |
| 2 | 100 | 73 | 0,730 |
| 3 | 92 | 70 | 0,761 |
| 4 | 98 | 69 | 0,704 |
| 5 | 96 | 71 | 0,740 |

Các số giả định.

### 18.1. Tại sao ghép cặp?

Nếu A và B của mỗi run cùng seed/data condition/time block, chênh lệch **trong cặp** giúp giảm một phần nhiễu giữa ngày/cluster.

### 18.2. Không giả định các requests là độc lập

Một triệu requests trên một run không tương đương một triệu thí nghiệm độc lập: các requests cùng chịu GC, shard hotspot, network burst và compaction.

### 18.3. Báo phân phối per-run

Có thể báo median, min/max hoặc khoảng biến thiên của p99 **theo run**, cùng histogram gộp nếu có population tương thích.

### 18.4. Chọn số repetitions theo độ biến thiên

Không có số cố định đúng mọi workload. Nếu chênh lệch nhỏ và nhiễu lớn, cần nhiều runs hơn hoặc môi trường kiểm soát hơn trước khi quyết định.

## 19. Thống kê độ trễ: không chỉ một mean

Một báo cáo tốt phân biệt:

- p50: kinh nghiệm điển hình.
- p90/p95: phần chậm hơn.
- p99/p99.9: tail.
- Mean: chi phí trung bình/Little's Law.
- Histogram: toàn phân phối.
- Timeout rate: các requests không hoàn thành trong deadline.

### 19.1. Tránh lấy trung bình p99 các khoảng để tạo p99 tổng

Không lấy p99 từng phút rồi tính trung bình. Percentiles phải được tính từ cùng population/histograms hoặc dùng cấu trúc quantile có khả năng merge theo contract.

### 19.2. Tail latency cần đủ mẫu

p99.9 trên 1.000 requests chỉ liên quan khoảng một request ở tail. Cần lượng samples và thời gian đủ để tránh kết luận từ một outlier.

### 19.3. Timeout không được giấu

Nếu B có p99(success)=30 ms nhưng 20% requests timeout, đó không phải improvement thực với SLO “99% requests hoàn thành đúng trong 100 ms”.

### 19.4. Giữ histogram policy

A dùng HDRHistogram độ chính xác ba chữ số, B dùng bucket 0–100/100–1000 ms có thể không so p99 tinh tế. Ghi library/config/aggregation method.

## 20. Chỉ số cải thiện: tuyệt đối và tương đối

Giả sử:

```text
A p99 = 120 ms
B p99 = 75 ms
```

**Cải thiện tuyệt đối:**

\[
\Delta L=L_B-L_A=75-120=-45\ \text{ms}
\]

**Mức giảm phần trăm (baseline A là mẫu số):**

\[
\text{Latency reduction \%}
=\frac{L_A-L_B}{L_A}\times 100
=\frac{120-75}{120}\times100=37{,}5\%
\]

Giả sử:

```text
A goodput = 3,800 ops/s
B goodput = 4,560 ops/s
```

**Tăng goodput:**

\[
\frac{4.560-3.800}{3.800}\times100=20\%
\]

### 20.1. Percentage points khác percent

Error rate từ 2% xuống 1% là **giảm 1 điểm phần trăm** và **giảm tương đối 50%**.

### 20.2. Ghi hướng tốt/xấu

Latency thấp hơn tốt; goodput cao hơn tốt; error thấp hơn tốt; cost thấp hơn tốt. Không dùng một cột “+20% improvement” mơ hồ.

### 20.3. Tránh phép chia baseline gần zero

Nếu A timeout rate=0, không thể nói B timeout rate=0,1% là “tăng vô hạn phần trăm” một cách hữu ích. Báo chênh lệch tuyệt đối, counts và confidence.

## 21. Ý nghĩa thống kê và ý nghĩa kỹ thuật

Một chênh lệch có thể:

- **Có ý nghĩa thống kê** nhưng quá nhỏ để tạo giá trị.
- **Có ý nghĩa kỹ thuật** nhưng chưa đủ bằng chứng do nhiễu cao.
- Có vẻ lớn chỉ vì một run bị ảnh hưởng incident.
- Là sản phẩm của việc chọn outcome sau khi đã nhìn dữ liệu.

### 21.1. Đặt ngưỡng trước

Ví dụ:

```text
Ship B if:
  p99 GetOrderById improves >= 20% at 3,000 offered RPS
  successful goodput is non-inferior by 5%
  error rate increase <= 0.1 percentage point
  write p99 regression <= 10%
  no correctness regression
```

Đây là policy minh họa; ngưỡng phải dựa vào SLO/business.

### 21.2. P-value không đủ

Một p-value nhỏ không nêu effect size hoặc business importance. Báo chênh lệch, khoảng tin cậy, số runs và điều kiện.

### 21.3. Tránh p-hacking

Không thay metrics/đo thêm đến khi thấy “tối ưu” rồi chỉ báo kết quả có lợi. Đăng ký trước metric chính và guardrails; nếu khám phá hậu nghiệm, ghi là exploratory.

## 22. Confidence interval và bootstrap theo run

Khi có nhiều paired runs, có thể ước lượng độ không chắc của **per-run effect** (ví dụ p99 difference hoặc log ratio) bằng bootstrap trên đơn vị run/block phù hợp.

Quy trình khái niệm:

```text
Pairs: (A1,B1), (A2,B2), ... (An,Bn)
Effect per pair: d_i = B_i - A_i

Repeat many times:
  resample whole paired runs with replacement
  compute aggregate paired effect

Use percentiles of resampled effects
to describe estimated uncertainty.
```

### 22.1. Vì sao không bootstrap từng request ngẫu nhiên không xét tương quan?

Requests cùng run có correlation do cache, GC, compaction và shared queue. Resample độc lập từng request có thể tạo khoảng tin cậy quá hẹp.

### 22.2. CI của p99 và CI của difference khác nhau

Không suy “hai khoảng p99 overlap” là chắc chắn không có khác biệt. Có thể ước lượng trực tiếp paired difference với phương pháp phù hợp.

### 22.3. Không biến CI thành bảo đảm tương lai

CI dựa trên sampling model và điều kiện đã đo; không cam kết tương lai khi dữ liệu, phần cứng hoặc traffic thay đổi.

### 22.4. Khi dữ liệu ít

Ưu tiên thu thêm runs/khôi phục controlled environment thay vì vẽ khoảng tin cậy quá chính xác từ hai mẫu.

## 23. Đồng nhất điều kiện đo tải

Một so sánh bắt buộc ghi:

```text
Load model: open-loop / closed-loop
Target offered RPS: 500, 1000, 2000, 3000 ...
Actual scheduled and issued arrivals
Warmup: 5 minutes
Ramp: 2 minutes
Measure: 15 minutes
Drain: until outstanding outcomes resolved
Retries: disabled or fixed policy
Key distribution: specified
Thread count/connections: specified
```

### 23.1. Fixed-arrival comparison

Ở cùng offered 2.000 req/s, so p99/error/goodput của A và B. Nếu một bản overload, report backlog/timeouts chứ không che chúng.

### 23.2. Capacity comparison

Quét nhiều offered loads cho mỗi bản và tìm **mức cao nhất còn đạt SLO**, ví dụ “p99 dưới 100 ms và error dưới 0,1% liên tục 20 phút”.

### 23.3. Không so hai “max throughput” không cùng tiêu chí

Một bản có đỉnh 10k/s nhưng p99 3s khác bản 8k/s p99 50ms. Khả năng phục vụ theo SLO có thể nghiêng về bản thứ hai.

## 24. Đường cong throughput–latency–error

Số liệu minh họa:

| Offered req/s | A goodput | A p99 | B goodput | B p99 |
|---:|---:|---:|---:|---:|
| 500 | 500 | 12 ms | 500 | 11 ms |
| 1.000 | 999 | 20 ms | 999 | 15 ms |
| 2.000 | 1.990 | 58 ms | 1.996 | 30 ms |
| 3.000 | 2.850 | 170 ms | 2.980 | 75 ms |
| 4.000 | 3.000 | 760 ms | 3.720 | 190 ms |

Tại low load, B cải thiện nhỏ; gần saturation, B cải thiện nhiều hơn nhưng vẫn có giới hạn.

### 24.1. Knee point

Vùng mà tăng offered load khiến latency bắt đầu tăng nhanh còn goodput tăng rất ít thường là vùng hệ gần bão hòa.

### 24.2. SLO capacity

Với p99 mục tiêu dưới 100 ms, dữ liệu trên gợi ý B đạt mức 3.000 offered req/s, A không đạt ở mức ấy. Nhưng phải xét error budget và thời lượng.

### 24.3. Đừng nội suy thành một cam kết chính xác

Các điểm đo thưa không chứng minh capacity chính xác 3.451 RPS. Có thể đo thêm quanh threshold.

## 25. Kết quả phải kèm error, timeout và correctness

Bảng trước/sau nên có các cột:

| Metric | A | B | Đánh giá |
|---|---:|---:|---|
| Offered RPS | 2.000 | 2.000 | Bằng nhau |
| Goodput | 1.985/s | 1.994/s | Tăng nhẹ |
| p50 latency | 18 ms | 14 ms | Giảm |
| p95 latency | 70 ms | 45 ms | Giảm |
| p99 latency | 132 ms | 81 ms | Giảm |
| Timeout rate | 0,50% | 0,20% | Giảm |
| Business conflict | 0,25% | 0,25% | Không đổi |
| Incorrect/stale beyond contract | 0 | 0 | Không regression |
| Server CPU p95 | 68% | 74% | Tăng |
| Storage per million records | 5,0 GiB | 6,1 GiB | Tăng |
| Write p99 | 48 ms | 56 ms | Regression |

Các số là minh họa. **Tối ưu đọc** có thể đổi lấy chi phí ghi và lưu trữ; kết luận cần đánh giá toàn bộ hợp đồng.

## 26. NoSQL index: case study trước/sau

Bài toán: MongoDB có 12 triệu orders. Query:

```javascript
db.orders.find({
  customerId: "U42",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(50);
```

Baseline chỉ có index:

```javascript
{ customerId: 1 }
```

Candidate thêm compound index:

```javascript
db.orders.createIndex({
  customerId: 1,
  status: 1,
  createdAt: -1
});
```

### 26.1. Hypothesis

Compound index có thể giảm keys/docs scanned và sort work cho đúng query shape.

### 26.2. Cần cố định

- Cùng MongoDB server/version/hardware.
- Cùng 12 triệu documents và key distribution.
- Cùng filter/sort/projection/limit.
- Cùng client-side measurement boundary.
- Cùng read concern/preference.
- Cùng concurrency/offered load.
- Cùng cache warmup policy.

### 26.3. Cần quan sát thêm

- `explain` plan, winning index.
- Total keys examined, docs examined.
- Sort stage/memory.
- Index size.
- Read p50/p95/p99.
- Insert/update p99.
- Disk/CPU during index build and steady state.

### 26.4. Index build phải hoàn tất trước steady-state comparison

Đo B khi index đang build hoặc replica vẫn chưa hoàn tất build có thể làm kết quả khó giải thích. **Index build time** lại là một metric rollout riêng đáng quan tâm.

### 26.5. Không coi kế hoạch query giống nhau là chắc chắn performance giống nhau

Dữ liệu, cache và contention vẫn có thể làm execution time khác. Ngược lại, thấy latency giảm cần explain để tăng bằng chứng cải thiện do index.

## 27. Case study: đổi partition key trong Cassandra

Một bảng cũ:

```text
orders_by_tenant
partition key = tenantId
```

Một tenant lớn chứa hàng chục triệu orders và nhận lượng traffic rất cao. Candidate thêm bucket:

```text
partition key = (tenantId, yyyyMM)
clustering key = (createdAt, orderId)
```

### 27.1. Đây là thay đổi model, không chỉ code

- Dữ liệu phải được backfill/repartition.
- Query cross-month cần nhiều partitions.
- Pagination token thay đổi.
- Một số queries nhanh hơn, một số tốn fan-out.
- Retention, TTL và compaction behavior thay đổi.

### 27.2. Trước/sau phải kiểm tra invariant

Cùng kết quả đơn hàng trên một khoảng thời gian; không bỏ missing/duplicate records do migration.

### 27.3. Workload matrix

Đo:

1. Latest-month query.
2. Cross-12-month query.
3. Insert new order.
4. Update order status.
5. Hot-tenant reads.
6. Small-tenant reads.
7. Compaction/repair sustained load.

### 27.4. Metric quan trọng

p99 theo tenant, partition size distribution, tombstones scanned, coordinator fan-out, goodput, CPU/disk và read consistency.

### 27.5. Tránh so sai semantics

Nếu B chỉ lấy đơn trong tháng gần nhất còn A lấy toàn lịch sử, đó không phải cùng operation. Phải nêu rõ điều kiện lọc.

## 28. Case study: DynamoDB Scan sang Query/GSI

Baseline code dùng `Scan` rồi lọc `customerId`. Candidate thêm GSI và dùng `Query`.

```text
A: Scan Orders + FilterExpression(customerId)
B: Query CustomerOrdersGSI with partition key customerId
```

### 28.1. Lợi ích kỳ vọng

B giảm dữ liệu phải quét theo query pattern, có thể giảm consumed capacity và latency.

### 28.2. Nhưng phải so cùng hợp đồng đọc

Một GSI DynamoDB có read consistency semantics khác base table strong read (GSI reads là eventual consistency). Nếu API yêu cầu strong/authoritative read, thay Scan mạnh hơn bằng GSI eventual không tự tương đương.

### 28.3. Backfill GSI

Khi thêm GSI, trạng thái index build/backfill và write capacity/replication của index ảnh hưởng chi phí. Chỉ đo steady-state sau khi GSI sẵn sàng theo contract, còn migration cost report riêng.

### 28.4. Cost metrics

- Read capacity consumed.
- Write capacity của index.
- Throttling.
- GSI storage.
- p99 Query latency.
- Number of items scanned/returned.
- Staleness/freshness nếu thuộc requirement.

### 28.5. Không chỉ nhìn p50

B có thể giảm mean nhưng tăng throttling cho hot partition nếu key design gây skew.

## 29. Case study: Redis cache trước/sau

A đọc MongoDB trực tiếp. B thêm cache-aside với Redis.

```text
A: HTTP -> MongoDB
B: HTTP -> Redis (hit) / MongoDB (miss)
```

### 29.1. Đây là thay đổi kiến trúc read path

Nếu metric chính là **HTTP GetProduct latency** và contract cho phép dữ liệu hơi stale, so A/B ở API level hợp lý.

Nếu mục tiêu là **MongoDB engine latency**, trộn cache hit path của B vào DB latency là sai.

### 29.2. Báo ba loại requests

- Cache hit.
- Cache miss và refill.
- Cache stale/error/bypass.

### 29.3. Không chỉ so warm cache

Chạy cả cold-start, TTL expiry burst, Redis restart, invalidation lag và MongoDB failure fallback.

### 29.4. Correctness guardrail

Nếu B trả sai giá tại checkout do cache stale, giảm p99 không đạt mục tiêu nghiệp vụ. Phân biệt browsing cache và authoritative purchase path.

### 29.5. Tác động lên write

Thêm cache có thể thêm invalidation events, Redis writes, cache stampede và consistency complexity. Chưa chắc tổng chi phí thấp hơn khi cache memory lớn.

## 30. Case study: đổi consistency hoặc durability level

A ghi MongoDB với một write concern, B dùng concern khác; hoặc A đọc Cassandra `ONE`, B đọc `LOCAL_QUORUM`.

### 30.1. Nếu bảo đảm khác, đây là thí nghiệm trade-off

Không nên báo “B nhanh hơn A cùng operation” mà không nói **đã đổi consistency contract**.

### 30.2. Đo chính xác

- Latency/throughput.
- Read staleness.
- Failure behavior.
- Durability sau node loss.
- Availability khi replica chậm.
- Conflict/LWT outcomes.

### 30.3. SLO bao gồm correctness

Nếu business yêu cầu không bán vượt kho, một read nhanh hơn với consistency yếu không thay thế atomic conditional reserve tại authority.

### 30.4. Khi trade-off hợp lệ

Có paths như public catalog browsing cho phép eventual read. Có paths như giao dịch tài chính cần bảo đảm mạnh hơn. Quyết định dựa trên từng use case, không dùng một consistency level cho mọi API rồi so p99 tổng.

## 31. Case study: tăng số shards/replicas

A có 3 nodes, B có 6 nodes.

### 31.1. Đặt câu hỏi đúng

Đây là **scale-out capacity experiment**:

- Throughput tăng bao nhiêu tại cùng SLO?
- Latency có giảm hay tăng do fan-out?
- Tải phân phối đều chưa?
- Cost tăng bao nhiêu?
- Rebalance/migration kéo dài bao lâu?
- Failure capacity khi mất 1 node ra sao?

### 31.2. Không so node count mà bỏ hardware

3 nodes 16 vCPU mỗi node khác 6 nodes 4 vCPU; tổng cores và memory thay đổi.

### 31.3. Data rebalancing

B ngay sau scale-out có thể đang copy data; đo steady state và rollout state riêng.

### 31.4. Hot key có thể chặn scale-out

Nếu bottleneck là một leader/partition, tăng shards không chữa được. Đo utilization theo shard.

### 31.5. Cost efficiency

B 20% nhanh hơn nhưng chi phí gấp đôi có thể không phù hợp nếu A đã đạt SLO.

## 32. Case study: thay batch size

A ghi từng item; B ghi batch 50 items.

### 32.1. So cả hai mẫu số

```text
RPC/s
Successful items/s
Items per batch
p99 batch completion time
p99 per-item acknowledgment latency
```

### 32.2. Định nghĩa p99 per-item

Nếu 50 items được gom chờ tới khi batch đầy, latency end-to-end mỗi item phải tính **thời gian chờ gom batch**, không chỉ thời gian RPC.

### 32.3. Partial failures

Một batch HTTP success có thể có items fail và cần retry. Đếm goodput ở mức items, không tự coi batch thành công hoàn toàn.

### 32.4. Memory/backpressure

Batch lớn có thể làm ít RPC hơn nhưng tăng heap allocations, tail latency và retry amplification.

### 32.5. Reorder semantics

Nếu operations trên cùng key có thứ tự, batching/parallelism có thể thay đổi behavior. Test correctness trước khi tuyên bố throughput tăng.

## 33. Case study: transaction so với independent writes

A dùng hai writes riêng:

```text
Update inventory
Insert order
```

B dùng native transaction bao cả hai khi database hỗ trợ.

### 33.1. Phạm vi khác nhau

B có atomicity mạnh hơn. So latency có thể có penalty do coordination, nhưng đó là chi phí để đạt guarantee.

### 33.2. So với cùng business contract

Nếu baseline A có thể commit một phần, không thể chỉ vì A nhanh hơn mà khuyến nghị A cho nghiệp vụ yêu cầu all-or-nothing.

### 33.3. Metrics

- Committed transactions/s.
- Transaction abort/conflict rate.
- p99 commit latency.
- Number of items/partitions.
- Retry attempts.
- Lock/coordination time.
- Business invariant violations.

### 33.4. Không gọi `@Transactional` một phép đo cross-service

Spring transaction không tự atomic với HTTP Payment Service. Nếu đo toàn checkout, phải tính Saga/idempotency và workflow completion separately.

## 34. So sánh trước/sau CDC hoặc search projection

A đồng bộ search mỗi 5 phút theo batch. B dùng Change Streams/Kafka Connect để cập nhật gần thời gian thực.

### 34.1. Metric chính không chỉ là QPS

- Source commit → CDC captured lag.
- Broker publish lag.
- Sink apply lag.
- Search query-visible freshness.
- Missed/duplicate events.
- Rebuild time.
- Source overhead.
- Sink ingestion throughput.

### 34.2. Một phương pháp đo

Phát 10.000 updates có source version riêng; ghi thời điểm commit ở source và poll/observe khi search trả version đó. Đo distribution của **end-to-end visibility lag**.

### 34.3. Clock skew

Nếu source và sink ghi wall-clock timestamps trên máy khác, hiệu đo thời điểm có thể bị skew. Có thể dùng trace correlation, client-observed timestamps cùng clock và phương pháp kiểm soát latency rõ.

### 34.4. Deletes

B có vẻ nhanh nhưng không chuyển DELETE events đúng thì không đạt consistency của read model.

### 34.5. Recovery

Test connector downtime lâu hơn retention và resnapshot/reconciliation; không chỉ test steady state khi mọi node khỏe.

## 35. So sánh tốt hơn nhờ per-operation breakdown

Một dashboard tổng:

```text
All requests:
  A p99=100ms
  B p99=70ms
```

có thể che regression:

| Operation | Traffic share | A p99 | B p99 |
|---|---:|---:|---:|
| Read profile | 70% | 25ms | 18ms |
| Search product | 20% | 90ms | 60ms |
| Reserve inventory | 9% | 130ms | 190ms |
| Capture payment | 1% | 300ms | 550ms |

Tổng có thể cải thiện nhờ nhiều reads nhanh, trong khi **đường critical** xấu đi.

### 35.1. Không gộp các population khác nhau

Tách theo operation, cache hit/miss, tenant, region và request size. Sau đó mới báo số tổng nếu muốn.

### 35.2. Simpson's paradox

Nếu A có 80% writes khó, B có 10% writes khó, aggregate latency có thể giảm dù latency trong từng nhóm không đổi hoặc xấu đi. Giữ workload mix cố định hoặc chuẩn hóa theo lớp.

### 35.3. So cùng trọng số

Có thể chuẩn hóa outcomes theo fixed reference workload mix, song vẫn báo production traffic distribution riêng.

## 36. A/B test với lưu lượng production

Khi không thể tái tạo mọi điều kiện staging, một **A/B test** có thể phân bổ traffic giữa control và candidate.

```text
                  Load Balancer / Router
                      /             \
                     v               v
                 Version A        Version B
                    |                |
                 NoSQL A?         NoSQL B?
```

### 36.1. Randomization unit

Randomize theo request, user, tenant hay key? Nếu một user có sticky session hoặc request phụ thuộc nhau, randomize từng request có thể tạo cross-over làm kết quả khó giải thích.

### 36.2. Shared database

Nếu A/B ứng dụng cùng dùng một NoSQL index hoặc schema, treatment index thay đổi cho cả hai, **control không còn độc lập**. Muốn cô lập index treatment có thể cần clone clusters, query hint có kiểm soát hoặc thiết kế khác.

### 36.3. Cross-talk

A và B cùng chia CPU/DB quota khiến bản này làm ảnh hưởng bản kia. Cần quan sát shared resource contention.

### 36.4. Production traffic drift

Các cohorts phải tương đồng theo geography, tenant size, payload, time of day và operation mix; cần kiểm tra sample ratio mismatch.

### 36.5. Correctness và an toàn rollout

Dùng shadow reads cho non-side-effect reads nếu phù hợp; không nhân đôi payment/inventory writes chỉ để A/B, vì có thể gây hai business effects.

## 37. Canary rollout và before/after time series

Một **canary** chỉ chuyển một tỷ lệ nhỏ traffic sang B, tăng dần nếu đạt guardrails.

```text
1% -> 5% -> 25% -> 50% -> 100%
```

### 37.1. Khi nào hợp lý?

- Thay đổi driver/config/app có thể bật theo instance.
- Có thể rollback nhanh.
- Metrics/alerts được phân biệt version.
- Dữ liệu có khả năng tương thích giữa hai versions.

### 37.2. Với database schema/index global

Index tạo ở shared cluster có thể ảnh hưởng mọi traffic; rollout app canary không phân lập được tác động index. Phải đánh giá database-wide metrics và experiment design riêng.

### 37.3. Interrupted time series

Khi chỉ có một cụm production và không quay lại A dễ dàng, có thể ghi chuỗi metrics trước/sau, kiểm soát mùa vụ, traffic, deploy khác và incidents, nhưng kết luận về nhân quả yếu hơn randomized controlled test.

### 37.4. Rollback criteria

Xác định trước rollback khi p99, errors, CPU, index build, replication lag hoặc correctness vi phạm ngưỡng. Không đợi hết toàn bộ rollout mới đánh giá.

## 38. So sánh deployment trước/sau qua nhiều phiên bản

Một thay đổi kéo dài có thể có:

```text
Baseline A
  |
  v
Backfill phase
  |
  v
Dual-read/dual-write migration phase
  |
  v
Candidate B steady state
```

### 38.1. Không trộn migration cost vào steady-state số liệu mà không ghi

Nếu mục tiêu là long-run query performance, báo B steady-state. Nhưng phải **báo riêng downtime, backfill duration và peak resource use** vì triển khai thật phải chịu những chi phí đó.

### 38.2. Dual-write

Trong migration, ghi cả schema cũ và mới có thể làm write latency cao hơn. SLO trong migration cũng quan trọng, không thể bỏ vì “chỉ là tạm thời”.

### 38.3. Data parity

Trước cutover, so record counts, checksums/sample queries, event ordering, delete/TTL propagation, permissions, index completeness.

### 38.4. Khả năng quay lại

Đổi partition key hoặc upgrade storage format có thể khiến rollback không đơn giản. Cần kế hoạch backup/recovery tương thích.

## 39. Ghi lại cấu hình dạng machine-readable manifest

Một file thí nghiệm minh họa:

```yaml
experiment:
  id: orders-query-index-2026-11
  objective: "Reduce p99 without write regression"
  owner: "data-platform"
  hypothesis: "Composite index reduces scanned documents"
  treatment:
    kind: "index"
    before: "customerId_1"
    after: "customerId_1_status_1_createdAt_-1"

environment:
  database:
    engine: "MongoDB"
    version: "record exact server build"
    topology: "3-node replica set"
    instanceType: "record exact CPU/RAM"
    disks: "record IOPS, throughput, size"
    readConcern: "record exact setting"
    writeConcern: "record exact setting"
    indexes: "snapshot DDL and build status"
  application:
    javaVersion: "record exact build"
    springVersion: "record if relevant"
    driverVersion: "record exact"
    poolMax: 100
    retries: "disabled for test"
    timeoutMs: 250
  client:
    location: "same region, separate host"
    hardware: "record CPU/RAM/NIC"
    loadTool: "record version and config"

dataset:
  sourceSnapshotId: "snapshot-001"
  records: 12000000
  seed: 20261114
  keyDistribution: "Zipfian"
  documentSize: "record p50/p95/p99"

workload:
  operation: "find customer paid orders, limit 50"
  offeredRatesRps: [500, 1000, 2000, 3000]
  model: "open-loop"
  warmupSeconds: 300
  measureSeconds: 1200
  repetitions: 5
  randomizedRunOrder: true

outcomes:
  primary: "p99 driver query latency"
  secondary: ["p50", "p95", "goodput", "cost"]
  guardrails: ["errors", "write p99", "correctness"]
  timeoutPolicy: "include all scheduled outcomes in SLI"

artifacts:
  configHash: "record actual hash"
  deploymentRevision: "record git commit"
  queryPlan: "store explain output"
  metricsLocation: "store link/path"
  notes: "record deviations and incidents"
```

Đây là **mẫu ghi nhận**, không phải schema của một benchmark tool cụ thể.

### 39.1. Giữ bản trước và sau

Lưu manifest cho A và B (hoặc một manifest chung kèm differencing rõ), tránh bị cấu hình “current” thay đổi khiến không tái lập được.

### 39.2. Ghi hash

Hash của config, container image, migration script, test dataset generator và benchmark script giúp biết đúng phiên bản đã chạy. Không thay bằng “main branch ngày hôm đó”.

### 39.3. Secrets

Không đưa credentials vào manifest. Ghi secret reference/version hoặc ID an toàn, tuân theo chính sách.

## 40. Ghi lại thay đổi cấu hình dưới dạng diff

Một ghi chú tốt:

```diff
# Index change
- { customerId: 1 }
+ { customerId: 1, status: 1, createdAt: -1 }

# Unchanged
  readPreference: primary
  writeConcern: majority
  driverPoolMax: 100
  readTimeoutMs: 250
  queryLimit: 50
```

### 40.1. Configuration drift

Nếu sau run phát hiện A driver pool=50 còn B pool=100, phải đánh dấu **deviation**. Có thể chạy lại với pool cố định hoặc đổi kết luận thành tác động của gói index+pool.

### 40.2. Flags và defaults

Default của driver thay đổi theo phiên bản. Ghi **effective configuration**, không chỉ properties được khai báo thủ công.

### 40.3. Query planner

Nên lưu explain/plan và query hints để xác nhận index thực sự được sử dụng theo mong đợi.

## 41. Java: một timer đo đúng operation boundary

Một ví dụ Java 17 minh họa cách đo một operation:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.atomic.LongAdder;

public final class OperationMetrics {
    private final LongAdder success = new LongAdder();
    private final LongAdder failures = new LongAdder();
    private final LongAdder totalNanos = new LongAdder();

    public <T> T around(
            String operationName,
            Callable<T> work
    ) throws Exception {
        long start = System.nanoTime();
        boolean ok = false;

        try {
            T result = work.call();
            ok = true;
            return result;
        } finally {
            long elapsed = System.nanoTime() - start;
            totalNanos.add(elapsed);
            if (ok) success.increment();
            else failures.increment();

            // Production: histogram per low-cardinality
            // operationName và outcome, không log từng call.
        }
    }

    public long successes() { return success.sum(); }
    public long failures() { return failures.sum(); }
}
```

### 41.1. Vì sao dùng `System.nanoTime()`?

Để đo elapsed duration trong cùng JVM, tránh wall-clock adjustments. Giá trị này không phải Unix timestamp để so giữa hai máy.

### 41.2. Không đo chỉ các requests thành công

`finally` giúp ghi duration khi exception. Nhưng chương trình mẫu chưa phân loại timeout, conflict, not-found, invalid result; production meter cần nhiều outcomes hơn.

### 41.3. Không benchmark production bằng `println` mỗi request

Console I/O và lock có thể làm biến dạng p99 và throughput.

### 41.4. Cần histogram

`LongAdder` cho tổng/count là chưa đủ để tính p99. Dùng HDRHistogram, Micrometer hoặc hệ telemetry thích hợp.

## 42. Java: Micrometer đo p99 và outcome

Trong Spring Boot, có thể khai báo Timer:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.function.Supplier;

public final class MeasuredOrderRepository {
    private final MeterRegistry registry;
    private final OrderStore store;

    public MeasuredOrderRepository(
            MeterRegistry registry,
            OrderStore store
    ) {
        this.registry = registry;
        this.store = store;
    }

    public Order getOrder(String orderId) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            Order result = store.getOrder(orderId);
            if (result == null) {
                outcome = "not_found";
            }
            return result;
        } catch (RuntimeException error) {
            outcome = "error";
            throw error;
        } finally {
            sample.stop(
                    Timer.builder("nosql.operation.duration")
                            .tag("operation", "getOrderById")
                            .tag("outcome", outcome)
                            .publishPercentileHistogram()
                            .register(registry)
            );
        }
    }

    public interface OrderStore {
        Order getOrder(String id);
    }
    public record Order(String id, String status) {}
}
```

### 42.1. Độ nhất quán instrumentation A/B

Cả A và B nên dùng cùng Timer definition/tags/histogram config. Nếu B có thêm instrumentation overhead, ghi rõ hoặc đo tác động.

### 42.2. Không dùng ID động làm tag

`orderId` hay `tenantId` tùy ý làm tăng cardinality time series, có thể làm backend monitoring quá tải.

### 42.3. Endpoint latency vẫn khác driver latency

Đặt Timer ở repository sẽ không bao gồm HTTP gateway/queue/JSON rendering. Nên có trace spans và end-to-end SLI riêng.

## 43. Java: chọn cùng dataset/query cho hai run

Một lớp benchmark harness mang cùng workload cho A/B:

```java
import java.util.List;
import java.util.Random;
import java.util.function.Function;

public final class ReadWorkload {
    private final List<String> orderIds;
    private final long seed;

    public ReadWorkload(
            List<String> orderIds,
            long seed
    ) {
        this.orderIds = List.copyOf(orderIds);
        this.seed = seed;
    }

    public void runOnce(
            Function<String, ?> operation,
            int count
    ) {
        Random rng = new Random(seed);
        for (int i = 0; i < count; i++) {
            String id = orderIds.get(
                    rng.nextInt(orderIds.size())
            );
            operation.apply(id);
        }
    }
}
```

Đây là **ví dụ chọn cùng tập keys theo seed**, chưa phải load generator đáng tin.

### 43.1. Điều nó giữ tương đương

Cùng ordered key list, seed và count sẽ tạo cùng chuỗi lựa chọn keys trong một JVM theo code này.

### 43.2. Điều nó không giữ được

- Realistic Zipfian distribution.
- Concurrent requests.
- Open-loop scheduled arrivals.
- Latency histogram.
- Error accounting.
- Time-based measurement window.
- Transaction correctness.
- Producer saturation.

### 43.3. Không dùng số vòng lặp làm throughput

Nếu A kết thúc 10.000 calls trong 1 giây còn B trong 2 giây, đây là closed-loop throughput khác nhau. Muốn đo cùng arrival rate phải có scheduler/harness thích hợp.

## 44. Java: tách p99 của một query và API request

Một service có cache:

```java
public Order getOrder(String id) {
    Order cached = redisCache.get(id);
    if (cached != null) return cached;
    return mongoStore.getById(id);
}
```

Đo bên ngoài `getOrder` là **API/service operation**. Đo riêng `mongoStore.getById` là **source read latency** chỉ trên cache misses.

### 44.1. Regression dễ bị bỏ qua

Nếu B làm cache hit từ 70% lên 95%, overall p99 có thể giảm nhưng source DB p99 khi miss lại tăng do cold keys.

### 44.2. Report breakdown

```text
HTTP:
  offered, goodput, p50/p95/p99

Cache:
  hits, misses, hit p99, miss p99

NoSQL:
  driver p99, server p99, read bytes, retry

Correctness:
  staleness, wrong result, consistency violations
```

### 44.3. Không trộn population

Không nói MongoDB p99 giảm nếu thực ra đang đo Redis hits; chỉ so các DB calls cùng scope.

## 45. Operational metrics giúp giải thích thay đổi

Khi B p99 giảm, cần hỏi **tại sao**. Ghi thêm:

- CPU per node/shard.
- Memory and page cache hit.
- Disk latency, IOPS, bandwidth.
- Network RTT, throughput, packet loss.
- Connection pool wait/in-use.
- Request queue/admission time.
- GC pauses/allocations.
- Index hit/keys scanned/docs scanned.
- Partition skew/hot keys.
- Replication lag/quorum time.
- Compaction/flush backlog.
- Cache hit/miss and eviction.
- Retry/throttle/conflict.
- CDC and search freshness.
- Tail by region/tenant/operation.

### 45.1. Metrics chẩn đoán không thay kết quả người dùng

Server CPU giảm không đủ nếu HTTP p99 tăng. Một index ít scanned keys hơn chưa chắc làm goodput tăng khi network/lock là bottleneck.

### 45.2. Ghi baseline health

Nếu A vừa bị incident, B khỏe, cần tách effect của sự cố hoặc chạy lại. Không sử dụng incident bất thường để làm đẹp treatment.

## 46. So sánh chi phí vận hành, không chỉ độ trễ

Một thay đổi có thể:

```text
A:
  3 nodes x $/hour
  p99 75 ms
  goodput 3,000/s

B:
  6 nodes x $/hour
  p99 45 ms
  goodput 3,700/s
```

B nhanh hơn, nhưng liệu chi phí có đáng?

### 46.1. Cost per million correct operations

\[
C_{1M}
=
\frac{\text{Total cost during window}}
{\text{Successful correct operations}/10^6}
\]

Ghi chi phí compute, storage, data transfer, managed capacity, cache, replication và CDC nếu nằm trong scope.

### 46.2. Storage trade-off

Một compound index có thể tăng disk footprint và write amplification. B có read p99 tốt hơn nhưng total cost cao hơn.

### 46.3. Energy/network

Cross-region replication, logging và index build gây network/storage overhead; có thể là guardrail đối với hệ lớn.

### 46.4. SLO-compliant cost

Một metric thực dụng là **chi phí thấp nhất để đáp ứng SLO với margin failover**, không phải p99 thấp nhất bằng mọi giá.

## 47. Benchmark report nên có cấu trúc gì?

Một báo cáo hoàn chỉnh:

1. **Decision summary:** Ship/No ship/Need more data, cùng phạm vi kết luận.
2. **Hypothesis và metric chính:** định trước.
3. **Changes:** diff cấu hình/code/index.
4. **Environment:** hardware, topology, DB/driver version.
5. **Dataset:** size, distribution, snapshot.
6. **Workload:** operation definitions, mix, arrival model.
7. **Method:** warmup, duration, repeats, run order.
8. **Results:** p50/p95/p99, goodput, errors, correctness, cost.
9. **Variability:** per-run table/CI, outliers/deviations.
10. **Mechanism:** query plan, CPU, index, queue, hot partitions.
11. **Guardrails:** regressions và failure modes.
12. **Rollout/rollback plan:** production acceptance.

### 47.1. Kết luận có điều kiện

> “B giảm p99 của query X 32% trên dataset 12M records, 2k offered RPS, warm cache, primary read và cùng driver settings. Chưa có bằng chứng cho workload scan nhiều partitions hoặc failover conditions.”

Đây là kết luận tốt hơn “B nhanh hơn 32%” không có scope.

### 47.2. Link tới raw artifacts

Lưu logs/histograms, query plans, configs, seeds, commits, timestamps và biểu đồ. Không chỉ screenshot dashboard.

## 48. Bảng quyết định mẫu

| Tiêu chí đã định trước | A | B | Kết luận |
|---|---:|---:|---|
| p99 GetOrders @2k RPS | 120 ms | 76 ms | B giảm 36,7% |
| Successful goodput | 1.982/s | 1.993/s | B tốt hơn nhẹ |
| Error rate | 0,30% | 0,20% | B giảm 0,10 điểm % |
| Write p99 | 55 ms | 61 ms | B xấu hơn 10,9% |
| Index disk | 8,0 GiB | 10,2 GiB | Tăng 27,5% |
| Correctness mismatches | 0 | 0 | Không ghi nhận |
| Cold-cache p99 | 240 ms | 235 ms | Khác biệt nhỏ |
| Failover p99 | Chưa đo | Chưa đo | Thiếu bằng chứng |

**Quyết định mẫu:** chưa rollout toàn bộ nếu write p99 guardrail đặt ngưỡng 10% và B vượt ngưỡng, hoặc nếu failover performance là yêu cầu bắt buộc. Có thể tối ưu lại/cân nhắc canary và đo thêm.

### 48.1. Không chỉ chọn dòng đẹp

Bảng phải chứa cả regressions, không xóa dòng write p99 hoặc cost vì làm kết luận khó hơn.

### 48.2. Số đo “0 lỗi” không chứng minh “không bao giờ lỗi”

Số mẫu, test coverage và failure mode quyết định ý nghĩa của zero observed errors.

## 49. Các mẫu kết luận sai thường gặp

**“B đo sau A nên B nhanh hơn do thay đổi.”** Có thể cache, dữ liệu, traffic hoặc maintenance drift.

**“B throughput 10k ops/s, A 8k nên B tốt hơn 25%.”** Chưa biết success, errors, scope và SLO.

**“p99 giảm nhưng 30% requests timeout.”** Không phải improvement cho trải nghiệm chung.

**“Test A 1KiB, B 100KiB mà p99 tương tự.”** Khác workload, không thể kết luận tương đương.

**“A đọc quorum, B đọc eventual, B nhanh hơn.”** Đã đổi guarantee.

**“Cùng 10M documents nên dataset giống nhau.”** Phân phối, size, cache và tombstones có thể khác.

**“Thêm index không ảnh hưởng write.”** Có index maintenance và storage overhead.

**“Một run B đẹp nhất đại diện cho tất cả.”** Selection bias.

**“Trung bình p99 theo ngày là p99 tháng.”** Không, percentiles không cộng tuyến tính.

**“Cùng số threads nên cùng offered RPS.”** Không với closed-loop khi latency khác.

**“Không thấy lỗi trong staging nên production an toàn.”** Chưa test failure/replay/topology.

**“Có canary 5% thì dữ liệu được cô lập.”** Không nếu mọi canary requests dùng chung source cluster.

**“Clone hai clusters là identical.”** Có thể khác caches, autoscaling, noisy neighbors và physical placement.

**“GSI Query nhanh hơn Scan nên GSI luôn tốt hơn.”** Đọc GSI có consistency/cost và query semantics khác.

**“Thêm nodes nhanh hơn nên index đã tối ưu.”** Hai interventions bị trộn.

**“CPU giảm chứng minh người dùng nhanh hơn.”** Phải đo end-to-end latency/goodput.

**“Benchmark 60 giây đủ cho Cassandra.”** Có thể chưa thấy compaction/tombstones/repair effects.

**“Quay lại A sau khi thêm index sẽ y hệt A ban đầu.”** Cache/data state/physical layout có thể đã thay đổi.

**“Retried command được tính thêm một business operation.”** Sai nếu logical operation chỉ một nhưng attempts nhiều.

**“Cùng p99 nghĩa hai systems giống nhau.”** Errors, cost, correctness và tail beyond p99 có thể khác.

**“Một CI hẹp chứng minh causal effect.”** Còn phụ thuộc thiết kế thí nghiệm và confounders.

**“Đo performance chỉ cần một bảng số.”** Cần config, raw traces, workload spec và test protocol.

## 50. Failure testing của thay đổi mới

Ngoài steady-state A/B, cần chạy test riêng cho:

- Cache cold start.
- Database node loss.
- Replica failover/leader election.
- Cross-region packet loss.
- Connection pool exhaustion.
- Hot partition overload.
- Compaction peak.
- Backup/snapshot/index rebuild.
- High conflict CAS/transactions.
- Broker/CDC lag.
- Write timeout after commit.
- Retry storm.
- Search refresh lag.
- Disk approaching capacity.
- Rolling upgrade/rebalance.

### 50.1. Giữ cùng fault injection

Nếu A mất leader trong 30 giây còn B chỉ ngắt một replica không tham gia reads, phép so fault behavior không tương đương.

### 50.2. Recovery metrics

- Unavailability window.
- Time to recover normal p99.
- Backlog drain duration.
- Stale read count.
- Unknown write outcomes.
- Data mismatches/lost updates.
- Retry amplification.

### 50.3. Không chạy chaos phá hủy trên production không được phép

Dùng staging/controlled environment hoặc quy trình production được phê duyệt, dữ liệu/tenants có blast-radius phù hợp.

## 51. Case study end-to-end: thay đổi index ở hệ Java

Một team muốn tối ưu API:

```text
GET /orders?customer=U42&status=PAID
```

Kiến trúc:

```text
API Gateway
     |
     v
Spring Boot Order Service
     |
     v
MongoDB Driver
     |
     v
MongoDB Replica Set
```

### 51.1. Trước thay đổi

- Index `customerId` đơn.
- Query filter thêm status, sort createdAt.
- p99 HTTP=210ms tại 2k offered RPS.
- Database examined nhiều docs.
- Write p99=40ms.

### 51.2. Thay đổi

Thêm index `{customerId:1,status:1,createdAt:-1}`; không đổi endpoint, driver, pool, read preference, query projection, dataset.

### 51.3. Đo

- Clone A/B từ snapshot tương đương.
- Warmup theo policy chung.
- 5 paired runs, randomized order.
- Offered RPS sweep 500/1k/2k/3k.
- Đo HTTP p99, driver p99, DB explain, write p99, CPU/disk, errors.
- Test cold-cache và index-build impact riêng.

### 51.4. Giả sử kết quả

B giảm p99 HTTP còn 145ms nhưng write p99 tăng 12% do index maintenance. Nếu write guardrail là 5%, cần đánh giá trade-off hoặc cải tiến khác, không kết luận “đã thành công” chỉ từ read p99.

### 51.5. Rollout

Canary không cô lập index global; có thể rollout index build có giám sát, rồi chuyển query/hint từng phần nếu hệ hỗ trợ. Bảo đảm query plan và index build đã ổn định.

### 51.6. Report

Ghi đầy đủ diff, raw artifacts, decision và rollback procedure. Nếu regression xuất hiện sau 1 tuần do compaction hoặc data growth, có căn cứ tái phân tích.

## 52. Case study end-to-end: tối ưu ghi DynamoDB

Một dịch vụ ghi inventory reservations qua DynamoDB.

### 52.1. Baseline

Thực hiện read `GetItem` rồi conditional `UpdateItem`.

### 52.2. Candidate

Bỏ read trước và dùng `UpdateItem` với `ConditionExpression` để kiểm tra availability tại source.

### 52.3. Hypothesis

Giảm một round trip, giảm latency, vẫn giữ atomic invariant không oversell.

### 52.4. Controlled variables

- Cùng table/key distribution.
- Cùng capacity mode và region.
- Cùng condition/expression semantics.
- Cùng quantity/expected version.
- Cùng concurrency và retries.
- Cùng count of successful reservations.

### 52.5. Guardrails

- Không oversell khi 100 clients cùng claim item cuối.
- Conflict rate hợp lý và đếm riêng.
- Throttling/capacity consumed.
- Transaction/conditional failure latency.
- Unknown outcomes/idempotency.
- Cost/operation.

### 52.6. Khác biệt đặc biệt

Nếu A kiểm tra business rule khác B, B nhanh hơn nhưng không tương đương. Phải kiểm tra invariant trước khi so throughput.

## 53. Case study end-to-end: thay đổi driver Java

A dùng MongoDB Java Driver phiên bản X; B nâng lên phiên bản Y và thay pool config.

### 53.1. Hai thay đổi

Driver upgrade và pool tuning là hai treatments. Có thể:

- So A(X, pool old), B(Y, pool old): tác động driver.
- So B(Y, pool old), C(Y, pool new): tác động pool.
- So A với C: tác động release bundle.

### 53.2. Không bảo đảm driver mới luôn nhanh

Driver mới có thể thay routing/retry defaults, mapping hoặc protocol features. Performance và correctness phải kiểm tra trên server version thật.

### 53.3. Java workload

Chọn query giống nhau, codec/mapping tương đương, payload size, warmup JIT, GC và connection reuse.

### 53.4. Hiện tượng liên quan pool

Pool tăng có thể giảm wait time nhưng cũng tăng concurrency tới database gây overload. Cần quét load và đo cả client queue lẫn server CPU/latency.

### 53.5. Kết luận

Mục tiêu là xác định cấu hình mới có đạt SLO và tương thích hay không, không mặc định upgrade được “thưởng” vì tên version lớn hơn.

## 54. Bài tập thực hành

### Bài tập 1 — Định nghĩa treatment

Team đồng thời thêm index, bật cache và tăng node count.

**Câu hỏi:** Có thể nói “index giúp p99 giảm 30%” không?

**Gợi ý:** Không nếu chưa cô lập; đây là tác động của gói thay đổi.

### Bài tập 2 — Measurement boundary

A đo driver call, B đo HTTP end-to-end.

**Câu hỏi:** Có so p99 trực tiếp được không?

**Gợi ý:** Không; boundary khác.

### Bài tập 3 — Relative change

A p99=120ms, B p99=75ms.

**Câu hỏi:** Latency giảm bao nhiêu ms và bao nhiêu %?

**Gợi ý:** 45ms, 37,5%.

### Bài tập 4 — Goodput

A goodput=3.800/s, B=4.560/s.

**Câu hỏi:** Tăng phần trăm?

**Gợi ý:** 20%.

### Bài tập 5 — Percentage point

A error rate=2%, B=1%.

**Câu hỏi:** Giảm bao nhiêu điểm phần trăm?

**Gợi ý:** 1 điểm phần trăm.

### Bài tập 6 — Warm cache

A chạy đầu tiên với cache cold, B chạy thứ hai khi cache warm.

**Câu hỏi:** Bias nào xuất hiện?

**Gợi ý:** Carry-over/warmup confounder.

### Bài tập 7 — ABBA

Một test có thể bật/tắt feature nhanh và không phá dữ liệu.

**Câu hỏi:** Vì sao A-B-B-A hữu ích?

**Gợi ý:** Giảm ảnh hưởng drift theo thời gian.

### Bài tập 8 — Irreversible migration

Partition key change cần rewrite toàn bộ dữ liệu.

**Câu hỏi:** Có thể lặp ABBA dễ dàng không?

**Gợi ý:** Không; dùng clone/snapshot và báo migration impact.

### Bài tập 9 — Retries

A tắt retry, B bật ba attempts.

**Câu hỏi:** Có cùng physical workload không?

**Gợi ý:** Không; ghi logical và physical attempts.

### Bài tập 10 — Success-only p99

B p99(success)=20ms nhưng 25% requests timeout.

**Câu hỏi:** Có đủ chứng minh B tốt hơn không?

**Gợi ý:** Không; SLI/error/goodput.

### Bài tập 11 — Dataset

Hai tests có 10M documents nhưng B có ít tombstones hơn.

**Câu hỏi:** Cùng dataset conditions không?

**Gợi ý:** Không hoàn toàn.

### Bài tập 12 — GSI

B chuyển DynamoDB Scan sang GSI Query.

**Câu hỏi:** Read consistency có thể thay đổi không?

**Gợi ý:** Có, GSI queries eventual consistency; kiểm tra API contract.

### Bài tập 13 — Query plan

Index mới tồn tại nhưng optimizer không dùng.

**Câu hỏi:** Cần lưu bằng chứng gì?

**Gợi ý:** Explain plan/keys examined và query latency.

### Bài tập 14 — Cassandra partition key

B giảm hot partition p99 nhưng cross-month query chậm hơn.

**Câu hỏi:** Báo cáo thế nào?

**Gợi ý:** Per-operation matrix và workload mix, không chỉ overall p99.

### Bài tập 15 — Batches

A 200 RPC/s ×1 item, B 100 RPC/s ×100 items.

**Câu hỏi:** Có thể kết luận A throughput cao hơn B vì RPC/s cao hơn không?

**Gợi ý:** Không; xem successful items/s và per-item latency.

### Bài tập 16 — Partial success

Bulk API trả HTTP 200 nhưng 10/100 items lỗi.

**Câu hỏi:** Goodput nên đếm bao nhiêu item?

**Gợi ý:** 90 item successes, retry tính riêng.

### Bài tập 17 — Transaction

B dùng transaction atomic, A hai writes riêng không atomic.

**Câu hỏi:** Có cùng correctness guarantee không?

**Gợi ý:** Không.

### Bài tập 18 — Read consistency

A Cassandra `ONE`, B `LOCAL_QUORUM`.

**Câu hỏi:** Chỉ so latency rồi chọn cái nhanh hơn có hợp lý không?

**Gợi ý:** Không nếu business yêu cầu consistency khác.

### Bài tập 19 — Metrics p99

Có ba runs p99 20, 30, 40ms.

**Câu hỏi:** Trung bình 30ms có là p99 gộp không?

**Gợi ý:** Không.

### Bài tập 20 — Uncertainty

Một run A p99=100, B p99=90; biến thiên các ngày ±30ms.

**Câu hỏi:** Có thể kết luận B thực sự tốt hơn chưa?

**Gợi ý:** Chưa đủ; cần paired repeated runs/uncertainty.

### Bài tập 21 — Statistical vs practical

B cải thiện 1ms có ý nghĩa thống kê nhưng SLO 200ms đã đạt.

**Câu hỏi:** Có nhất thiết rollout không?

**Gợi ý:** Xem business benefit, cost, risk và ngưỡng đã định.

### Bài tập 22 — Cache effect

API p99 giảm nhưng MongoDB miss p99 tăng.

**Câu hỏi:** Tối ưu áp dụng ở tầng nào?

**Gợi ý:** End-to-end API nhờ cache hits; không khẳng định DB engine nhanh hơn.

### Bài tập 23 — Scale-out

B gấp đôi nodes, throughput tăng 25%.

**Câu hỏi:** Metric nào cần thêm?

**Gợi ý:** Cost/operation, SLO capacity, hotspot, rebalance.

### Bài tập 24 — User-visible freshness

B CDC capture nhanh hơn nhưng Search visible lag không đổi.

**Câu hỏi:** Đã cải thiện user-facing freshness chưa?

**Gợi ý:** Chưa, có thể bottleneck ở broker/sink/index refresh.

### Bài tập 25 — Canary

Canary B 5% và A 95% cùng dùng một MongoDB index đã đổi.

**Câu hỏi:** Có control cho tác động index không?

**Gợi ý:** Không; index shared ảnh hưởng cả hai.

### Bài tập 26 — Production seasonality

A đo ngày thường, B đo ngày flash sale.

**Câu hỏi:** Nên làm gì?

**Gợi ý:** Cùng workload/cùng time blocks hoặc điều chỉnh bằng controlled design.

### Bài tập 27 — Cold-start

B tốt ở warm cache, xấu ở cache restart.

**Câu hỏi:** Kết luận nên bao gồm gì?

**Gợi ý:** Steady-state + degraded/cold-start guardrails.

### Bài tập 28 — Cost per million

A tốn $20/triệu successful ops, B tốn $32 nhưng p99 tốt hơn.

**Câu hỏi:** Có ship B không?

**Gợi ý:** So SLO margin và business value, không chỉ p99.

### Bài tập 29 — Rollback

Index mới gây p99 write tăng 20%, guardrail tối đa 10%.

**Câu hỏi:** Quyết định hợp lý?

**Gợi ý:** Không ship toàn bộ/rollback hoặc điều chỉnh và đo lại.

### Bài tập 30 — Thiết kế hoàn chỉnh

Một hệ Java/Spring Data MongoDB chuyển từ single-field index sang compound index, dùng Redis cache và có CDC sang Elasticsearch.

**Yêu cầu:** Viết manifest A/B, chọn workload, measurement boundary, outcomes, guardrails, randomized runs, query-plan metrics, cold-cache/compaction/failover tests và rollback criteria.

**Gợi ý:** Giữ nguyên driver/cache/traffic cho phép đo tác động index; đo HTTP và driver riêng; thêm write cost, search freshness, error/correctness; ghi query plans, config diff, data snapshot và raw histograms.

## 55. Checklist trước khi kết luận A/B

- [ ] Đã đặt giả thuyết và mục tiêu business rõ ràng.
- [ ] Đã định nghĩa A, B và treatment chính xác.
- [ ] Đã nêu thao tác, result contract, start/end boundary.
- [ ] Có metric chính và guardrails định trước.
- [ ] Không nhầm offered load với goodput.
- [ ] Đã tách HTTP, driver, server và CDC freshness.
- [ ] Ghi engine/version/edition/hardware/topology.
- [ ] Ghi replica/shard/partition, read/write consistency.
- [ ] Ghi effective driver, JVM, GC, pool và retry settings.
- [ ] Ghi dataset snapshot/size/distribution/tombstones.
- [ ] Cùng key/payload/query/projection/limit/ordering.
- [ ] Giữ consistency/durability contract tương đương hoặc nêu trade-off.
- [ ] Có index definitions, build status và explain plans.
- [ ] Ghi cache state/hit rate, warm/cold test policy.
- [ ] Ghi generator tool/version/hardware/location.
- [ ] Chọn đúng open-loop/closed-loop và coordinated-omission policy.
- [ ] Có offered RPS sweep và SLO-compliant capacity.
- [ ] Có warmup/ramp/measurement/drain windows.
- [ ] Có repeated runs và randomized/paired order khi khả thi.
- [ ] Không cherry-pick run đẹp nhất.
- [ ] Ghi deviations/noisy neighbors/incidents.
- [ ] Có p50/p95/p99, histograms và sampling method.
- [ ] Có errors, timeouts, throttling, conflicts, pending.
- [ ] Không gộp success-only p99 với SLI availability.
- [ ] Có correctness, stale reads và transaction invariants.
- [ ] Có cost, index size, write amplification và storage impact.
- [ ] Có CPU/GC/disk/network/pool/compaction diagnostics.
- [ ] Có cold-cache, hot partition, failover/recovery cases.
- [ ] Có migration/backfill và steady-state riêng.
- [ ] Có per-operation/per-tenant/per-region breakdown.
- [ ] Không coi same time order là proof nhân quả.
- [ ] Có confidence/variability và effect-size reporting.
- [ ] Có quyết định ship/no-ship/need-more-data theo ngưỡng.
- [ ] Có plan canary, rollback và monitoring sau rollout.
- [ ] Đã lưu configs, seeds, revisions, artifacts và raw metrics.
- [ ] Kết luận giới hạn đúng workload/điều kiện đã đo.

## 56. Tổng kết

Một phép đo **trước/sau thay đổi** trong NoSQL chỉ đáng tin khi **cùng một loại thao tác và cùng hợp đồng về dữ liệu, consistency và độ bền** được đánh giá bằng **cùng ranh giới đo** dưới những điều kiện đã được ghi nhận.

- **Định nghĩa được A và B:** chỉ ra treatment, baseline, những biến cần giữ nguyên và những khác biệt không tránh khỏi.
- **Ghi lại toàn bộ điều kiện:** database/driver/JVM versions, topology, instance size, index, query plan, dataset, cache, workload, traffic, retries và warmup.
- **Đo nhiều chiều:** p50/p95/p99, successful goodput, errors, timeouts, correctness, CPU/disk/network, chi phí và độ mới của read models.
- **Giảm thiên lệch:** repeated paired runs, randomized order, A-B-A khi có thể, histogram population đúng và uncertainty theo run.
- **Xem trade-off:** index giúp read nhưng có thể làm writes/index storage đắt hơn; cache tăng tốc nhưng có thể stale; consistency yếu có thể nhanh hơn nhưng không còn là cùng hợp đồng; scale-out có cost và rebalancing.
- **Kết luận theo SLO:** chọn candidate khi lợi ích đủ lớn và guardrails chấp nhận được, đồng thời có canary/rollback và artifacts để tái kiểm chứng.

**Nguyên tắc cốt lõi:** *“Nhanh hơn” không phải thuộc tính tuyệt đối của một database hay một phiên bản code. Đó là kết luận có phạm vi: nhanh hơn đối với thao tác nào, tại tải nào, trên dữ liệu và cấu hình nào, với độ tin cậy nào, và có giữ nguyên tính đúng đắn hay không.* Nếu không ghi được các điều kiện ấy, phép so sánh chỉ là hai con số được đặt cạnh nhau chứ chưa phải bằng chứng tối ưu hiệu năng.

