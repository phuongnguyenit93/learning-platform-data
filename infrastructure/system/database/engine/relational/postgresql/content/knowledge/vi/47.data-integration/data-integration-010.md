# Giới hạn PostgreSQL một nút và tiêu chí cân nhắc phân tán dữ liệu

## 1. PostgreSQL một nút mạnh đến đâu và giới hạn xuất hiện ở đâu?

PostgreSQL thường được triển khai với một primary database server phục vụ reads và writes. Một máy chủ có CPU nhiều lõi, RAM lớn, NVMe nhanh và hệ thống backup tốt có thể xử lý workload đáng kể. Nhiều hệ thống không cần sharding trong suốt vòng đời sản phẩm nếu schema, indexes, queries, connection management và capacity được thiết kế hợp lý.

Tuy nhiên, một node vẫn có giới hạn vật lý và kiến trúc. CPU, RAM, I/O, network, dung lượng lưu trữ, khả năng phục hồi và tốc độ bảo trì đều hữu hạn. Khi workload vượt quá một trong các giới hạn đó, tăng thêm tài nguyên có thể ngày càng đắt hoặc không giải quyết đúng bottleneck. Một số workloads còn bị giới hạn bởi contention trên cùng dữ liệu, write serialization, locks hoặc một transaction coordinator duy nhất.

**Phân tán dữ liệu** là đưa dữ liệu và/hoặc xử lý qua nhiều database nodes để tăng capacity, locality hoặc availability. Cách làm này có thể giúp mở rộng ngang, nhưng tạo thêm chi phí về routing, consistency, distributed transactions, failure handling, observability, backup và vận hành.

Quyết định phân tán không nên dựa riêng vào số lượng rows hoặc cảm giác “database đã lớn”. Cần xác định bottleneck thực tế, dự báo tăng trưởng, thử các cách tối ưu ít phức tạp hơn và đánh giá xem workload có thể chia thành các phần độc lập hay không.

```text
Workload
   |
   v
Measure the bottleneck
   |
   +-- Query / schema / index issue? ----> Optimize SQL and data model
   |
   +-- Connection pressure? -------------> Pooling and concurrency control
   |
   +-- Read capacity? -------------------> Cache / read replicas
   |
   +-- Storage or memory capacity? ------> Tune / partition / scale up
   |
   +-- One node is the hard ceiling?
             |
             v
       Evaluate distribution
             |
       +-----+-------------------+
       |                         |
       v                         v
 Independent partitions      Tight cross-data
 and routing possible?       transactions/joins?
       |                         |
       v                         v
 Shard/distribute candidate   Keep centralized or
                              redesign boundaries
```

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích mô hình PostgreSQL một primary và các giới hạn của một node.
2. Phân biệt scale up, read scaling, partitioning, replication và sharding.
3. Nhận diện bottleneck CPU, memory, storage, network, locks, WAL và vacuum.
4. Đo capacity bằng metrics và workload forecasts.
5. Xác định khi nào query/schema optimization vẫn còn hiệu quả.
6. Hiểu vì sao read replicas không tự mở rộng write throughput.
7. Phân biệt HA/failover với horizontal scaling.
8. Đánh giá shard key, tenant locality, skew và cross-shard queries.
9. Hiểu consistency, distributed transactions và failure modes.
10. So sánh application sharding, Citus, FDW và distributed SQL systems.
11. Xây decision framework với ngưỡng đo được.
12. Lập kế hoạch migration, rebalancing, backup và disaster recovery.
13. Thiết kế observability cho nhiều database nodes.
14. Nhận biết dấu hiệu phân tán quá sớm hoặc quá muộn.
15. Xây lộ trình mở rộng từ một node đến kiến trúc phân tán có kiểm soát.

---

## 2. Mô hình PostgreSQL một node

Trong mô hình phổ biến, một PostgreSQL cluster chạy trên một host hoặc một managed database instance. Một primary nhận writes và thường phục vụ reads. PostgreSQL backend processes xử lý client sessions, shared memory hỗ trợ phối hợp và storage chứa data files/WAL.

Một node có thể có:
- Nhiều CPU cores.
- RAM lớn.
- Local SSD/NVMe hoặc network-attached storage.
- Nhiều data tablespaces/volumes.
- Connection pooler.
- Background workers, autovacuum và WAL writer.
- Backup/archive agents.
- Monitoring và failover integration.

### 2.1. Một node không đồng nghĩa một CPU core

PostgreSQL có thể dùng nhiều cores thông qua nhiều concurrent backends, parallel query workers và background processes. Một query đơn lẻ không phải lúc nào cũng tận dụng toàn bộ cores; mức parallelism phụ thuộc query plan, settings và operation.

### 2.2. Một primary thường là điểm ghi tập trung

Trong PostgreSQL core, một primary xử lý writes cho một cluster. Nhiều clients có thể ghi đồng thời, nhưng locks, WAL ordering, shared catalogs và transaction coordination vẫn nằm trong cùng cluster.

### 2.3. Nhiều database trong một cluster vẫn chia sẻ tài nguyên

Tạo nhiều databases không tạo thêm CPU, RAM, IOPS hay WAL capacity. Các databases cùng cluster cạnh tranh tài nguyên host và cùng chịu giới hạn của instance.

### 2.4. Nhiều tablespaces không phải sharding

Tablespaces có thể đặt objects trên các storage locations khác nhau, nhưng PostgreSQL vẫn quản lý chúng trong một cluster. Chúng không tự tạo nhiều independent query engines hoặc phân phối transaction execution.

## 3. Các giới hạn phần cứng

Các tài nguyên chính:

| Tài nguyên | Bottleneck thường thấy | Hướng xử lý ban đầu |
|---|---|---|
| CPU | CPU utilization cao, runnable queues, query latency tăng | Query tuning, indexes, reduce concurrency, scale up |
| RAM | Cache misses, memory pressure, swap/OOM | Tune memory, reduce concurrency, inspect plans |
| Storage capacity | Disk gần đầy, tăng trưởng nhanh | Retention, compression, partition lifecycle, larger storage |
| IOPS/throughput | I/O wait, latency cao | Better storage, query/index tuning, cache |
| Network | Throughput/latency giữa app và DB | App placement, batching, protocol/pool tuning |
| WAL/archive | WAL generation hoặc archive backlog cao | Tune write pattern, storage/archive capacity |
| Recovery | Restore/rebuild quá lâu | Backup strategy, replicas, faster storage, smaller recovery scope |

### 3.1. CPU ceiling

Nếu query execution, index maintenance, vacuum và concurrent sessions liên tục tiêu thụ toàn bộ CPU, latency có thể tăng phi tuyến. Thêm cores có thể giúp, nhưng query serial, lock contention hoặc skew có thể không scale tương ứng.

### 3.2. Memory ceiling

RAM phục vụ shared buffers, OS page cache, backend memory, sort/hash operations và background processes. Một setting như work_mem có thể được dùng nhiều lần trong một query và nhiều sessions cùng lúc; không nhân đơn giản theo số connections mà bỏ qua operator/concurrency.

### 3.3. Storage capacity

Database growth có thể vượt khả năng của một volume, backup window hoặc restore window trước khi server hết CPU. Cần dự báo table/index bloat, WAL, temp files, snapshots và backup copies.

### 3.4. Storage latency và throughput

Một query có thể bị giới hạn bởi random I/O, sequential throughput hoặc fsync latency. Tăng CPU không sửa được storage bottleneck.

### 3.5. Network ceiling

Ứng dụng ở xa database hoặc gửi quá nhiều round trips có thể bị network latency giới hạn. Phân tán database có thể làm vấn đề tệ hơn nếu mỗi request cần gọi nhiều nodes.

## 4. Giới hạn kiến trúc và concurrency

Ngay cả khi có thể thêm CPU/RAM, một số workloads vẫn gặp giới hạn do cách dữ liệu và giao dịch được tổ chức.

### 4.1. Write serialization

Nhiều writes vào cùng rows, hot counters, hot index pages hoặc cùng key range tạo contention. Thêm nodes không tự chia tải nếu mọi transaction vẫn cần cập nhật cùng một logical record.

### 4.2. Lock contention

Một transaction dài có thể block nhiều requests. DDL, row locks, advisory locks và table-level locks có thể tạo queue. Sharding chỉ giúp nếu contention được chia theo shard boundary.

### 4.3. Hot rows và hot keys

Ví dụ một row lưu global inventory counter hoặc một tenant cực lớn. Dù có 100 shards, mọi request vẫn dồn vào cùng shard/key nếu partition key không phân tán đúng workload.

### 4.4. WAL pipeline

Writes được ghi vào WAL để bảo đảm durability và phục vụ recovery/replication. Một primary có giới hạn về WAL generation, fsync, checkpoints và downstream replay capacity.

### 4.5. Vacuum và transaction horizons

Long-running transactions, replication slots hoặc idle-in-transaction sessions có thể giữ xmin cũ, ngăn cleanup dead tuples và tăng bloat. Phân tán không tự loại bỏ vấn đề transaction lifecycle.

## 5. Vì sao “database lớn” chưa đủ để kết luận cần sharding?

Một database vài terabytes có thể chạy tốt trên một instance phù hợp nếu workload chủ yếu là indexed lookups và sequential scans có kiểm soát. Một database nhỏ hơn có thể quá tải vì hàng nghìn concurrent writes vào cùng rows hoặc query plans kém.

Cần đo:
- Request rate và transaction mix.
- Read/write ratio.
- Query p50/p95/p99.
- CPU utilization và run queue.
- Storage latency/IOPS/throughput.
- Cache hit/read patterns.
- Lock waits và deadlocks.
- Connections và pool wait.
- WAL generation và replication lag.
- Table/index growth và bloat.
- Vacuum progress và transaction age.
- Backup/restore duration.

### 5.1. Row count không phải capacity metric

Một tỷ rows không tự nói được server cần bao nhiêu CPU. Row width, indexes, access patterns, selectivity, cache locality và concurrency mới quyết định chi phí.

### 5.2. Database size không phản ánh active working set

Một cluster 5 TB nhưng chỉ truy cập thường xuyên 50 GB có thể phù hợp với RAM/storage nhất định. Một cluster 500 GB có working set lớn hơn RAM và random access nặng có thể I/O-bound.

### 5.3. Peak matters more than daily average

Capacity phải đáp ứng peak traffic, batch jobs, maintenance và burst patterns. Average CPU 30% không bảo đảm peak không gây outage.

### 5.4. Forecast horizon

Dự báo capacity theo 6–18 tháng hoặc theo chu kỳ sản phẩm phù hợp. Sharding cần được chuẩn bị trước khi không còn đủ thời gian di chuyển, nhưng cũng không nên triển khai chỉ dựa vào một dự báo thiếu bằng chứng.

## 6. Scale up: mở rộng theo chiều dọc

Scale up tăng tài nguyên cho một node:
- CPU nhiều cores hơn.
- RAM nhiều hơn.
- Storage nhanh/dung lượng lớn hơn.
- Network bandwidth cao hơn.
- Instance class mạnh hơn.

### 6.1. Ưu điểm

Ứng dụng thường tiếp tục kết nối tới một database endpoint. Không cần shard routing, distributed joins hay cross-shard transaction design. Transactions và SQL semantics vẫn tập trung trong một cluster.

### 6.2. Hạn chế

Chi phí instance lớn có thể tăng nhanh. Có giới hạn instance class, storage throughput và maintenance windows. Một node lớn vẫn là một failure domain nếu không có HA.

### 6.3. Scale up có thể là bước tối ưu nhất

Nếu bottleneck là CPU/RAM/I/O và workload không cần locality, scale up thường đơn giản hơn đáng kể so với phân tán.

### 6.4. Benchmark trước khi đổi instance

Dùng workload representative và theo dõi query plans, cache state, I/O latency, memory headroom và failover behavior. Không chỉ so sánh số cores.

## 7. Scale out: mở rộng theo chiều ngang

Scale out thêm nodes và phân chia reads, writes hoặc data giữa chúng.

Một số cách:
- Read replicas cho reads.
- Sharding/partitioning across nodes cho data distribution.
- Distributed SQL/database layer.
- Application-level routing.
- Managed distributed PostgreSQL-compatible services.

### 7.1. Scale out reads

Nhiều replicas có thể phục vụ read queries độc lập. Cần xử lý replication lag và stale reads.

### 7.2. Scale out writes

Writes cần được phân phối theo shard/key hoặc distributed transaction mechanism. Read replicas thông thường không nhận writes độc lập.

### 7.3. Data placement

Mỗi row/table cần một nơi authoritative. Routing phải xác định node sở hữu data và xử lý requests không có shard key.

### 7.4. Cross-node work

Joins, aggregates, transactions và ordering trên nhiều shards có thể cần network exchange, coordinator work hoặc application orchestration.

## 8. Phân biệt HA với horizontal scaling

High availability (HA) giảm thời gian gián đoạn khi node lỗi. Horizontal scaling tăng capacity hoặc locality. Một kiến trúc có thể làm một việc, cả hai hoặc không làm được việc nào tốt.

| Cơ chế | Mục tiêu chính | Tăng write capacity? | Tăng read capacity? |
|---|---|---:|---:|
| Primary + standby | Failover/availability | Không đáng kể | Không khi standby chỉ chờ |
| Read replicas | Read offload | Không cho primary writes | Có |
| Partitioning một cluster | Manageability/pruning | Không tự tạo nhiều write nodes | Có thể giảm query work |
| Sharding | Phân chia data/write load | Có nếu workload phân tán được | Có |
| Multi-primary | Nhiều write endpoints | Có thể, tùy conflict/consistency model | Có |
| Distributed SQL | Phân tán data/transactions | Có theo kiến trúc | Có |

### 8.1. Streaming replication

Physical streaming replication truyền WAL từ primary tới standby. Standby thường ở recovery/read-only state và không nhận writes độc lập như một primary thứ hai.

### 8.2. Failover

Khi primary lỗi, standby có thể được promote theo HA procedure. Đây là chuyển vai trò, không phải chia writes thường xuyên giữa hai nodes.

### 8.3. Read replica

Replica nhận changes từ primary và có thể phục vụ reads. Nó không làm primary có thêm CPU cho write execution.

### 8.4. Multi-primary không phải mặc định PostgreSQL core

Multi-writer cần cơ chế ngoài core hoặc hệ thống distributed SQL. Phải đánh giá conflict resolution, global ordering, sequences, DDL và transaction guarantees.

## 9. Read replicas: giải pháp khi read-heavy

Nếu workload chủ yếu là reads, replicas có thể giảm áp lực primary.

### 9.1. Phân loại queries

- Strongly consistent reads: cần đọc ngay sau write trên primary.
- Eventual/stale-tolerant reads: chấp nhận replication lag.
- Analytics/reporting: có thể chạy trên replica hoặc warehouse.
- Session-consistent reads: cần đảm bảo request đọc được writes trước đó của cùng session.

### 9.2. Replica lag

Asynchronous replication có thể khiến replica chưa replay kịp WAL. Query vừa ghi xong có thể không thấy row trên replica.

### 9.3. Read-after-write routing

Application có thể gửi read ngay sau write tới primary hoặc dùng consistency token/LSN-aware strategy khi cần.

### 9.4. Không chia đều mọi reads

Health checks, metadata, transactions và queries cần consistency có thể phải ở primary. Routing policy nên theo query class và consistency requirements.

## 10. Partitioning trong một PostgreSQL cluster

Declarative partitioning chia một logical table thành nhiều physical partitions trong cùng một PostgreSQL cluster.

Ví dụ partition theo tháng:

```sql
CREATE TABLE public.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY,
    occurred_at timestamptz NOT NULL,
    payload jsonb NOT NULL
) PARTITION BY RANGE (occurred_at);

CREATE TABLE public.events_2026_11
PARTITION OF public.events
FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');

CREATE TABLE public.events_2026_12
PARTITION OF public.events
FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');
```

### 10.1. Partitioning không phải sharding

Các partitions vẫn thuộc một cluster, chia sẻ primary, CPU, RAM, WAL và failure domain. Nó không tự phân phối dữ liệu qua nhiều servers.

### 10.2. Partition pruning

Planner có thể loại partitions không liên quan dựa trên partition key, giảm lượng data cần scan.

### 10.3. Lifecycle management

Có thể detach/drop old partitions nhanh hơn delete hàng triệu rows, hỗ trợ retention và archival.

### 10.4. Partition key quyết định hiệu quả

Query phải có điều kiện phù hợp partition key để pruning xảy ra. Partitioning theo key không xuất hiện trong queries có thể không mang lại lợi ích.

## 11. Khi nào partitioning giúp và khi nào không?

Partitioning có ích khi:
- Table rất lớn và queries thường lọc theo partition key.
- Data có lifecycle rõ theo thời gian.
- Cần drop/archive ranges nhanh.
- Indexes lớn cần được chia nhỏ.
- Maintenance cần thực hiện theo từng partition.

Partitioning ít giúp khi:
- Query thường scan toàn bộ partitions.
- Table nhỏ.
- Workload không lọc theo partition key.
- Có quá nhiều partitions gây planning/metadata overhead.
- Bottleneck nằm ở hot row, CPU query hoặc network.

### 11.1. Unique constraints

PostgreSQL partitioned table có các constraints/index limitations phụ thuộc partition key và version. Thiết kế primary/unique keys phù hợp với partition key.

### 11.2. Foreign keys và partitioning

Foreign-key behavior trên partitioned tables đã mở rộng qua các major versions, nhưng cần xác minh capability và operational implications đúng version.

### 11.3. Partition count

Quá nhiều partitions có thể tăng planning time, catalog size và maintenance overhead. Chọn granularity dựa vào data volume/query pattern.

### 11.4. Partitioning không giải quyết nhiều writers trên một primary

Nó có thể giảm work cho từng query và quản lý data lifecycle, nhưng mọi writes vẫn đi vào cùng cluster.

## 12. Sharding là gì?

Sharding chia một logical dataset thành nhiều independent database shards. Mỗi shard giữ một phần dữ liệu và thường có primary/replicas riêng.

Ví dụ sharding theo tenant:

```text
Application
    |
    v
Shard router
    |
    +-- tenant_id 1..1000  ----> Shard A
    |
    +-- tenant_id 1001..2000 -> Shard B
    |
    +-- tenant_id 2001..3000 -> Shard C
    |
    +-- tenant_id 3001..4000 -> Shard D
```

### 12.1. Data ownership

Mỗi key/range/tenant được ánh xạ tới một shard. Router phải biết nơi authoritative của data.

### 12.2. Independent capacity

Mỗi shard có CPU, RAM, storage và WAL riêng. Thêm shards có thể tăng tổng capacity nếu workload phân bố tương đối đều.

### 12.3. Local transactions

Transactions chỉ chạm một shard có thể giữ semantics PostgreSQL thông thường trên shard đó.

### 12.4. Cross-shard operations

Một query hoặc transaction chạm nhiều shards cần orchestration, distributed transaction support hoặc application-level aggregation. Đây là nơi complexity tăng mạnh.

## 13. Shard key là quyết định kiến trúc quan trọng

Shard key quyết định data placement và khả năng route requests.

Các lựa chọn:
- tenant_id/customer_id.
- user_id/account_id.
- Geographic region.
- Hash of entity ID.
- Time range hoặc composite key.

### 13.1. High cardinality

Key nên có đủ giá trị phân bố dữ liệu. Một key chỉ có vài giá trị có thể tạo quá ít shards hiệu quả.

### 13.2. Query locality

Các records thường được đọc/ghi cùng nhau nên nằm cùng shard. Nếu một transaction thường cập nhật order, order_items và payment của cùng tenant, tenant_id có thể là lựa chọn tốt.

### 13.3. Even distribution

Shard key cần phân bố storage và request rate, không chỉ row counts. Một shard chứa ít rows nhưng traffic rất cao vẫn là hot shard.

### 13.4. Immutability

Shard key ít thay đổi giúp tránh di chuyển records giữa shards. Nếu key thay đổi thường xuyên, routing và transaction phức tạp hơn.

### 13.5. Avoid hot keys

Một tenant lớn, một region nóng hoặc một global counter có thể làm một shard quá tải. Cần dự báo skew và khả năng split.

## 14. Shard key theo tenant

Tenant-based sharding phù hợp SaaS khi dữ liệu và transactions chủ yếu nằm trong một tenant.

Ưu điểm:
- Tenant request route tới một shard.
- Joins trong tenant có thể local.
- Backup/restore hoặc export tenant có thể khoanh vùng.
- Data residency theo tenant/region có thể rõ ràng.

Rủi ro:
- Một tenant lớn hơn nhiều tenant khác.
- Tenant migration giữa shards.
- Global analytics cần fan-out.
- Unique constraints across tenants cần thiết kế.
- Tenant không có shard key trong query có thể buộc scatter-gather.

### 14.1. Tenant directory

Một metadata service/table ánh xạ tenant_id sang shard. Cần cache, versioning và consistency khi tenant chuyển shard.

### 14.2. Large tenant isolation

Có thể dành shard riêng cho tenant lớn trong khi các tenant nhỏ dùng shared shards.

### 14.3. Tenant affinity

Mọi tables thuộc tenant cần dùng cùng placement key để giảm cross-shard joins/transactions.

### 14.4. Global identities

ID cần unique toàn hệ thống có thể dùng UUID, composite keys hoặc ID allocation strategy. Sequence local trên mỗi shard không bảo đảm globally unique.

## 15. Hash sharding và range sharding

| Cách chia | Ưu điểm | Nhược điểm |
|---|---|---|
| Hash | Phân bố đều hơn khi key uniform | Range scans/fan-out khó hơn |
| Range | Range queries/locality tốt | Hot ranges và uneven growth |
| Tenant mapping | Transaction locality rõ | Skew do tenant size/traffic |
| Geographic | Data locality/residency | Region imbalance và cross-region operations |
| Composite | Cân bằng nhiều mục tiêu | Routing/maintenance phức tạp hơn |

### 15.1. Hash

Hash key rồi ánh xạ vào shard. Phù hợp point lookups và phân bố đều, nhưng query theo range có thể cần fan-out.

### 15.2. Range

Phân chia theo khoảng key hoặc time ranges. Query range có thể route ít shards, nhưng sequential inserts có thể làm shard cuối nóng.

### 15.3. Consistent hashing

Consistent hashing có thể giảm lượng keys phải di chuyển khi số nodes thay đổi, nhưng cần quản lý virtual nodes/ring metadata và hot partitions.

### 15.4. Không có shard key hoàn hảo

Chọn key dựa vào transaction boundaries, query patterns, data growth, tenant distribution, compliance và migration costs.

## 16. Cross-shard queries và scatter-gather

Khi query không chỉ ra shard key hoặc cần kết quả toàn hệ thống, router có thể gửi query tới nhiều shards, thu kết quả và hợp nhất.

### 16.1. Scatter

Gửi query tới các shards liên quan hoặc toàn bộ shards.

### 16.2. Gather

Thu rows/aggregates về coordinator/application.

### 16.3. Cost

Network transfer, remote execution, skew và coordinator memory có thể làm query chậm hơn nhiều so với một cluster.

### 16.4. Aggregation correctness

SUM/COUNT/MIN/MAX có thể combine theo cách phù hợp, nhưng AVG cần tổng và count; percentile/distinct/order có thể phức tạp hơn. Không cộng các kết quả partial sai semantics.

### 16.5. Pagination

ORDER BY/LIMIT across shards cần global merge. OFFSET lớn càng tốn chi phí; cursor/keyset pagination cần thiết kế theo global ordering.

## 17. Distributed transactions và consistency

Transaction một shard thường dễ quản lý hơn transaction qua nhiều shards.

### 17.1. Single-shard transaction

Nếu mọi rows cần thay đổi nằm cùng shard, một PostgreSQL transaction có thể giữ atomicity local.

### 17.2. Cross-shard atomicity

Nếu cần commit nhiều shards như một đơn vị, cần distributed transaction protocol như two-phase commit (2PC) hoặc orchestration/saga. Không phải mọi sharding framework đều hỗ trợ cùng guarantees.

### 17.3. Two-phase commit

2PC có prepare và commit phases. Nó tăng coordination, có thể để prepared transactions tồn tại khi coordinator gặp sự cố và cần operational recovery.

### 17.4. Saga

Saga chia business transaction thành các local transactions với compensating actions. Nó cho phép workflow dài nhưng không tương đương atomic rollback của một transaction PostgreSQL.

### 17.5. Eventual consistency

Một số systems chấp nhận dữ liệu cập nhật lan truyền trễ. Application cần định nghĩa stale-read tolerance, retry, duplicate handling và conflict semantics.

## 18. Network là một phần của transaction

Trong một node, nhiều operations có thể dùng shared memory và local storage. Trong distributed architecture, remote calls chịu network latency và có thể thất bại độc lập.

### 18.1. Partial failure

Một shard có thể reachable trong khi shard khác timeout. Query fan-out cần deadline, cancellation và partial-result policy.

### 18.2. Retry

Retry một remote write có thể thực hiện operation hai lần nếu response mất sau khi commit. Cần idempotency keys hoặc deduplication.

### 18.3. Clock differences

Không dùng wall-clock timestamps từ nhiều nodes như một global total order. Dùng database commit positions, logical clocks hoặc ordering mechanism theo requirement.

### 18.4. Network partitions

Khi network bị chia cắt, consistency/availability trade-offs trở nên rõ. Application cần biết node nào là authoritative và khi nào fail closed.

## 19. Citus và distributed PostgreSQL

Citus là extension/distributed database technology dựa trên PostgreSQL, dùng coordinator và worker nodes để phân phối tables theo distribution key và thực thi queries phân tán trong phạm vi được hỗ trợ.

### 19.1. Coordinator

Coordinator nhận SQL, xác định shard placements và điều phối execution.

### 19.2. Worker nodes

Workers lưu shards và thực hiện phần query được phân phối.

### 19.3. Distributed tables

Tables được phân phối theo key; colocated tables có thể giữ records cùng key trên cùng worker để localize joins/transactions.

### 19.4. Reference tables

Một số small tables có thể được replicate tới workers để joins với distributed tables thuận tiện hơn. Cần hiểu replication/update semantics và storage overhead.

### 19.5. Compatibility và limitations

Không giả định mọi PostgreSQL features/extensions/DDL/query patterns hoạt động giống hệt một cluster thường. Kiểm tra version-specific support matrix, managed offering và migration requirements.

## 20. Application-level sharding

Application-level sharding để code/service tự quyết định shard placement và kết nối.

### 20.1. Ưu điểm

- Kiểm soát routing rõ.
- Có thể dùng PostgreSQL instances độc lập.
- Có thể tối ưu theo domain/tenant.
- Ít phụ thuộc một distributed extension cụ thể.

### 20.2. Nhược điểm

- Mọi service phải biết routing rules.
- Cross-shard joins và transactions khó.
- Schema migrations phải chạy trên nhiều shards.
- Rebalancing và tenant movement cần tooling.
- Một bug routing có thể đọc/ghi nhầm shard.

### 20.3. Shard map

Lưu mapping shard key/range/tenant tới connection endpoint. Version hóa và cache mapping; xử lý invalidation khi chuyển shard.

### 20.4. Connection management

Mỗi shard có connection pools riêng hoặc pool routing. Tổng số connections có thể tăng theo số shards và app instances.

## 21. Foreign Data Wrappers không tự biến PostgreSQL thành sharded database

PostgreSQL FDW như postgres_fdw cho phép truy cập remote tables qua foreign tables.

### 21.1. Federation

Có thể query nhiều remote databases từ một local server trong một số workflows.

### 21.2. Pushdown

Một số predicates, projections và joins có thể được push xuống remote server. Mức pushdown phụ thuộc query, FDW và version.

### 21.3. Distributed transaction semantics

Không mặc định mọi cross-server operations có atomicity/consistency như một local transaction. Kiểm tra remote transaction behavior và failure handling.

### 21.4. Routing và rebalancing

FDW không tự cung cấp complete shard map, automated rebalancing, global uniqueness hoặc distributed query optimizer đầy đủ cho mọi workload.

## 22. Distributed SQL và PostgreSQL-compatible systems

Một số distributed SQL databases cung cấp SQL interface hoặc PostgreSQL wire/protocol compatibility, nhưng internal architecture có thể khác PostgreSQL single-node.

Đánh giá:
- SQL compatibility và unsupported features.
- Transaction isolation/consistency guarantees.
- DDL and schema change behavior.
- Index types and extensions.
- Query planner/execution.
- Sequences/identity behavior.
- Replication and failure semantics.
- Operational tooling and backup.
- Vendor lock-in and portability.
- Latency across regions.

### 22.1. Wire compatibility không phải full semantic compatibility

Một client có thể kết nối bằng PostgreSQL protocol nhưng server không hỗ trợ mọi SQL behavior/extension.

### 22.2. Distributed transactions có chi phí

Strong consistency across nodes thường cần coordination, replication và network round trips.

### 22.3. Benchmark theo ứng dụng

Chạy migrations, ORM tests, transaction workloads và failure tests. Không chọn chỉ dựa trên một microbenchmark.

### 22.4. Exit strategy

Xác định cách export data/schema và khả năng quay về PostgreSQL standard nếu vendor/system không còn phù hợp.

## 23. Replication không đồng nghĩa sharding

Replication giữ nhiều copies của cùng data. Sharding chia data thành các subsets.

| Đặc điểm | Replication | Sharding |
|---|---|---|
| Dữ liệu | Copies trùng nhau hoặc gần giống | Mỗi shard giữ subset |
| Mục tiêu | HA/read availability | Capacity/locality |
| Write path | Thường một primary cho physical replication | Writes route tới owner shard |
| Read routing | Có thể chọn replica | Chọn shard(s) chứa data |
| Failure | Promote replica hoặc rebuild | Mất shard ảnh hưởng subset; cần replica/restore |
| Cross-node query | Replica đọc cùng dataset | Fan-out/aggregation cần thiết |

### 23.1. Replica không tăng storage partitioning

Mỗi replica giữ bản copy cluster. Tổng storage tăng nhưng mỗi node vẫn chứa toàn bộ dataset được replicate.

### 23.2. Shard cần replication riêng cho HA

Một shard có thể có primary và standby. Sharding và replication thường kết hợp: shards phân chia data, replicas bảo vệ từng shard.

### 23.3. Logical replication có use cases khác

Logical replication có thể replicate selected tables/changes, hỗ trợ migration hoặc integration. Nó không tự tạo transparent horizontal sharding.

### 23.4. Partitioned tables không tự là distributed tables

Partitioning trong một cluster khác với distributed partition placement qua worker nodes.

## 24. Khi nào nên giữ PostgreSQL một node?

Một node thường phù hợp nếu:
- Bottleneck chưa được đo hoặc query/schema còn nhiều cơ hội tối ưu.
- Workload vẫn nằm trong capacity của instance phù hợp.
- Transactions thường chạm nhiều bảng cần atomicity.
- Joins và reports thường cần toàn dataset.
- Một shard key tự nhiên không tồn tại.
- Data growth và recovery objectives vẫn đáp ứng được.
- Team chưa có năng lực vận hành nhiều database nodes.
- Chi phí distributed architecture vượt lợi ích dự kiến.

### 24.1. Tối ưu trước

Kiểm tra slow queries, indexes, statistics, vacuum, connection pooling, N+1 queries, caching và data retention.

### 24.2. Tách workloads

Đưa analytics/ETL sang warehouse hoặc reporting replica có thể giảm tải primary mà không phải shard OLTP.

### 24.3. Tăng instance và storage

Scale up có thể mua thêm thời gian với complexity thấp.

### 24.4. Đặt capacity trigger

Xác định ngưỡng CPU, I/O, storage, latency, replication lag và recovery time để bắt đầu dự án scale-out trước khi chạm hard ceiling.

## 25. Dấu hiệu cân nhắc phân tán

Cân nhắc distributed data khi có evidence như:
- Một node đạt giới hạn CPU/RAM/IOPS dù query và schema đã được tối ưu.
- Write throughput cần thiết vượt capacity của primary class có thể mua.
- Dataset/working set vượt storage hoặc recovery limits.
- Workload tự nhiên chia theo tenant/region/entity và ít cross-shard transactions.
- Data residency yêu cầu đặt dữ liệu ở nhiều regions.
- Read replicas/caching không giải quyết bottleneck chính.
- Capacity growth dự báo vượt headroom trong planning horizon.
- Operational requirement cần scale độc lập theo domain/tenant.

### 25.1. Hard limit thay vì một peak ngắn

Một spike vài phút có thể giải quyết bằng queueing/autoscaling ở application. Distributed database là quyết định dài hạn; cần bottleneck lặp lại và được đo.

### 25.2. Marginal cost

Nếu instance lớn hơn vẫn đáp ứng SLA với chi phí hợp lý, sharding có thể không kinh tế.

### 25.3. Independent scaling

Nếu một tenant hoặc domain tăng trưởng khác biệt, tách placement có thể giúp scale riêng. Cần kiểm tra shared dependencies.

### 25.4. Geographic locality

Nếu users và data nằm ở nhiều regions, local reads/writes có thể giảm latency, nhưng multi-region consistency/failover phức tạp hơn.

## 26. Dấu hiệu phân tán quá sớm

Tránh sharding chỉ vì:
- Table có hàng trăm triệu rows nhưng query vẫn nhanh.
- Muốn “future-proof” mà không có forecast.
- Một dashboard CPU cao do query regression chưa sửa.
- Connection count lớn nhưng pooler chưa được cấu hình.
- Một report nặng có thể chuyển sang replica/warehouse.
- Một table retention có thể partition/drop theo thời gian.
- Team chưa có backup/monitoring/recovery automation cho một cluster.
- Chưa biết shard key hoặc phần lớn transactions cross-shard.

### 26.1. Complexity tax

Mỗi shard thêm migrations, monitoring, credentials, backup, restore, failover, connection pools và incident paths.

### 26.2. Debugging tax

Một request có thể liên quan nhiều nodes, trace/correlation IDs và partial failures.

### 26.3. Development tax

Local/test environments cần mô phỏng shard map và cross-shard behaviors. CI có thể cần nhiều database instances.

### 26.4. Hiring/operations tax

Team cần kỹ năng vận hành nhiều clusters, rebalancing, distributed transactions và incident response.

## 27. Decision framework theo bottleneck

| Bottleneck chính | Thử trước | Cân nhắc tiếp |
|---|---|---|
| Slow query | EXPLAIN, indexes, query rewrite, ANALYZE | Read replica/warehouse nếu workload riêng |
| CPU saturated | Query tuning, reduce concurrency, scale up | Shard nếu writes/CPU phân tán được |
| Read-heavy | Cache, replicas, reporting offload | Distributed read architecture |
| Write-heavy | Batch, hot-row redesign, indexes/transactions | Sharding hoặc distributed SQL |
| Storage growth | Retention, compression, partitioning, larger volume | Shard by tenant/time if operationally suitable |
| I/O bound | Storage tier, cache, query/index tuning | Split independent workloads/data |
| Lock contention | Shorter transactions, lock order, DDL strategy | Shard only if contention partitions cleanly |
| Recovery too slow | Backup/PITR/restore tuning, standby | Smaller failure domains/shard-level recovery |
| Geographic latency | App placement, regional read replicas/cache | Regional data placement/distribution |

### 27.1. Một bottleneck có thể có nhiều nguyên nhân

CPU saturation có thể do query plan, too many connections, vacuum, encryption, JSON processing hoặc workload burst. Xác định root cause trước khi chọn kiến trúc.

### 27.2. Chỉ phân tán bottleneck có thể phân tán

Nếu mọi writes cập nhật một global row, sharding các bảng khác không giải quyết được hot row đó.

### 27.3. Scale out không phải miễn phí

Tổng capacity có thể tăng, nhưng mỗi request có thể cần nhiều network hops hoặc coordinator aggregation.

### 27.4. So sánh cost per transaction

Tính cả database instances, network, storage, backup, observability, engineering và on-call effort.

## 28. Tính khả thi của shard key

Đánh giá shard key bằng các câu hỏi:
1. Bao nhiêu distinct keys?
2. Distribution của rows theo key?
3. Distribution của requests/writes theo key?
4. Bao nhiêu transactions chỉ chạm một key?
5. Bao nhiêu queries không có key?
6. Key có immutable không?
7. Có global uniqueness requirement không?
8. Có data residency constraints không?
9. Có tenant lớn/hot keys không?
10. Có thể di chuyển key/shard an toàn không?

### 28.1. Data skew

Một shard có 40% data trong khi các shard khác chỉ 10% có thể gây capacity imbalance.

### 28.2. Traffic skew

Rows phân bố đều nhưng traffic không đều vẫn tạo hot shard. Đo requests/s và write rate theo key.

### 28.3. Co-location

Các tables join/transaction thường xuyên nên colocate theo cùng distribution key nếu framework hỗ trợ.

### 28.4. Global lookup

Nếu nhiều requests chỉ có email hoặc external ID, cần global lookup table/index hoặc secondary mapping. Mapping đó phải consistent và không thành bottleneck mới.

## 29. Cross-shard constraints và identity

Một PostgreSQL cluster có thể enforce unique constraints và foreign keys trong phạm vi cluster. Với sharding, enforcement global có thể khó.

### 29.1. Unique keys

Nếu unique constraint không chứa shard key, database có thể không biết mọi values ở mọi shards. Dùng globally unique IDs hoặc central uniqueness service/pattern phù hợp.

### 29.2. Foreign keys

Foreign keys cross-shard có thể không được framework hỗ trợ hoặc cần application-level enforcement. Chọn data boundaries để FK thường local.

### 29.3. Sequences

Sequence riêng trên từng shard có thể sinh cùng giá trị. Dùng UUID, composite key, range allocation hoặc globally coordinated ID strategy.

### 29.4. Referential integrity

Nếu app chịu trách nhiệm kiểm tra references, cần xử lý race conditions, retries và orphan cleanup. Không coi một SELECT-then-INSERT đơn giản là atomic global constraint.

## 30. Rebalancing và shard lifecycle

Khi thêm shard hoặc một shard quá nóng, cần di chuyển dữ liệu.

### 30.1. Rebalance

Chuyển shard/range/tenant từ node này sang node khác để cân bằng storage và traffic.

### 30.2. Online movement

Một số systems hỗ trợ copy data và replicate changes trong lúc source còn hoạt động, sau đó cutover routing. Cần kiểm tra consistency và write fencing.

### 30.3. Routing metadata

Shard map phải có version/generation. Clients/router cache cần biết khi nào refresh và tránh ghi vào owner cũ.

### 30.4. Failure during movement

Thiết kế resume/checkpoint, idempotent copy, conflict handling và source/destination ownership. Không xóa source trước khi destination được xác minh.

### 30.5. Split hot shard

Có thể tách tenant/range nóng thành shard riêng. Cần đánh giá cross-tenant/shared rows và key mapping.

## 31. Backup, restore và disaster recovery cho shards

Sharding làm recovery scope phức tạp hơn.

### 31.1. Backup per shard

Mỗi shard cần base backup/PITR hoặc managed backup tương đương. Theo dõi coverage và retention cho tất cả shards.

### 31.2. Consistent cross-shard snapshot

Nếu business operation spanning shards cần consistent restore point, cần coordination/consistent snapshot strategy. Restore từng shard tới thời điểm khác nhau có thể tạo state không nhất quán.

### 31.3. RPO/RTO

Đặt recovery point objective và recovery time objective theo shard và toàn hệ thống. Một shard outage có thể ảnh hưởng tenant subset hoặc toàn app tùy routing.

### 31.4. Rebuild replicas

Mỗi shard có thể có HA replicas riêng. Test failover và replica rebuild theo đúng shard identity.

### 31.5. Global metadata

Backup shard directory, routing metadata, tenant mapping, schema version và credentials/config cùng data. Thiếu metadata có thể khiến data còn đó nhưng app không route được.

## 32. Schema migrations trên nhiều shards

Một migration phải được triển khai trên nhiều clusters/nodes.

### 32.1. Fan-out deployment

Runner có thể chạy migration theo shard tuần tự hoặc có giới hạn concurrency. Chạy tất cả cùng lúc có thể tạo I/O/CPU burst.

### 32.2. Version consistency

Theo dõi migration version trên từng shard. Một shard fail giữa deployment làm hệ thống ở trạng thái mixed schema.

### 32.3. Backward-compatible migrations

Application phải tương thích với schema cũ và mới trong rolling migration window. Expand-contract đặc biệt quan trọng.

### 32.4. Per-shard locks

Migration lock cần được quản lý trên từng shard và orchestration layer cần biết shard nào thành công/thất bại.

### 32.5. Resume

Deployment cần resume từ shard đã fail mà không chạy lại destructive operations trên shards đã thành công.

## 33. Observability cho distributed PostgreSQL

Một hệ thống nhiều shards cần metrics ở hai cấp: từng node và toàn hệ thống.

Node-level:
- CPU, RAM, IOPS, storage, WAL.
- Connections, locks, deadlocks.
- Query latency, slow queries.
- Vacuum, bloat, replication lag.
- Backup/restore status.

System-level:
- Requests/s theo shard/tenant.
- Fan-out width và remote call latency.
- Hot shard/key.
- Cross-shard transaction count/duration.
- Router cache misses/stale mappings.
- Rebalance progress.
- Partial failures/timeouts/retries.
- Schema version divergence.
- End-to-end p95/p99.

### 33.1. Correlation IDs

Gắn request/trace ID vào logs và remote shard calls để nối một business request qua nhiều nodes.

### 33.2. Per-shard dashboards

Một average toàn hệ thống có thể che giấu một shard quá nóng. Hiển thị distribution và worst shard.

### 33.3. Cardinality control

Không tạo metric label cho mọi customer ID nếu số lượng lớn. Dùng top-N/histograms và sampled diagnostics.

### 33.4. Alert on skew

Cảnh báo khi shard storage, CPU, latency hoặc queue diverge vượt ngưỡng so với peers.

## 34. Security và data residency

Phân tán data có thể giúp đặt records gần users hoặc trong jurisdiction phù hợp, nhưng cũng tăng bề mặt quản trị.

### 34.1. Network boundaries

Mỗi shard/replica cần network access rules, TLS, credentials và firewall policies riêng.

### 34.2. Secret rotation

Router/service có thể giữ credentials cho nhiều shards. Thiết kế rotation không làm mất kết nối toàn bộ nodes.

### 34.3. Tenant isolation

Shard placement không thay thế authorization. Application vẫn phải xác minh tenant access; không tin shard key từ client mà chưa kiểm tra.

### 34.4. Data residency

Xác định data nào phải ở region nào, kể cả backups, WAL archives, replicas, logs và analytics copies.

## 35. Multi-region và latency

Multi-region architecture có thể giảm latency cho local users hoặc đáp ứng residency, nhưng network distance ảnh hưởng transactions.

### 35.1. Regional primary

Đặt write owner theo region/tenant có thể giữ writes local, nhưng cross-region queries và transactions sẽ remote.

### 35.2. Synchronous replication across regions

Có thể tăng commit latency đáng kể vì mỗi commit chờ acknowledgement qua network. RPO/consistency phải được cân bằng với latency.

### 35.3. Asynchronous replication

Giảm commit latency nhưng có thể mất một số writes gần nhất khi failover sang replica chưa nhận/replay hết WAL, tùy failure scenario.

### 35.4. Global transactions

Một transaction cập nhật nhiều regions cần coordination và failure policy. Thiết kế business workflows để localize transactions nếu có thể.

## 36. Đo workload trước khi phân tán

Tạo baseline ít nhất bao gồm:
- Peak TPS/queries per second.
- Read/write ratio.
- p50/p95/p99 latency.
- Concurrent active sessions.
- CPU and run queue.
- Memory and cache behavior.
- Storage latency/throughput/IOPS.
- WAL bytes per second.
- Replica lag.
- Lock wait time.
- Top queries by total time and calls.
- Largest/hottest tables and tenants.
- Growth per week/month.
- Backup and restore duration.

### 36.1. pg_stat_statements

Dùng pg_stat_statements để tìm query families chiếm tổng execution time lớn, calls cao hoặc temp I/O đáng kể.

### 36.2. pg_stat_activity

Dùng để quan sát active sessions, wait events và transaction age trong incident.

### 36.3. OS/cloud metrics

Database views không thay metrics host/storage/network. Kết hợp provider monitoring và OS metrics.

### 36.4. Representative load test

Replay hoặc generate workload với data distribution và concurrency gần thực tế. Synthetic uniform keys có thể bỏ sót hot tenant.

## 37. Capacity model và growth forecast

Dự báo capacity nên tính:
- Data growth.
- Index growth.
- WAL and archive growth.
- Backup storage.
- Active working set.
- Peak concurrency.
- Read/write mix.
- Per-tenant growth/skew.
- Maintenance overhead.
- Recovery/rebuild headroom.

### 37.1. Headroom

Không vận hành liên tục ở 95–100% resource utilization. Cần buffer cho bursts, vacuum, index builds, failover và traffic growth.

### 37.2. Growth rate

Dùng trend thực tế, seasonality và product roadmap. Đừng ngoại suy một tuần bất thường thành annual growth.

### 37.3. Restore capacity

Một node có thể đủ chạy production nhưng restore 10 TB trong RTO yêu cầu có thể không khả thi. Recovery time là một dimension của capacity.

### 37.4. Scale trigger

Ví dụ trigger có thể là p99 vượt SLO liên tục, storage headroom dưới threshold, replica lag tăng bền vững hoặc projected capacity vượt instance ceiling trong horizon. Ngưỡng phải dựa baseline hệ thống.

## 38. Thử giải pháp đơn giản trước sharding

Một thứ tự điều tra thực tế:

1. Sửa N+1 và round trips.
2. Dùng EXPLAIN (ANALYZE, BUFFERS) cho top queries.
3. Bổ sung/điều chỉnh indexes.
4. Chạy ANALYZE và xử lý statistics.
5. Rút ngắn transactions, cải thiện lock ordering.
6. Dùng connection pooling và giới hạn concurrency.
7. Thêm caching cho reads phù hợp.
8. Offload reports/analytics sang replica hoặc warehouse.
9. Partition tables theo access/lifecycle pattern.
10. Tăng CPU/RAM/storage của instance.
11. Tách workloads/database theo domain nếu coupling thấp.
12. Chỉ sau đó đánh giá sharding/distributed SQL nếu bottleneck còn lại phù hợp để phân tán.

### 38.1. Tối ưu SQL trước

Query scan toàn bảng hoặc join sai có thể gây tải dù database nhỏ. Sharding làm mỗi query phức tạp hơn mà không sửa query logic.

### 38.2. Connection pooling

Một backend process cho mỗi connection có overhead. PgBouncer hoặc pooling ở platform có thể giảm connection churn và memory pressure.

### 38.3. Cache

Cache giảm reads nhưng cần invalidation, TTL, consistency và stampede protection.

### 38.4. Workload isolation

Tách analytics, ETL và reporting có thể đem lại hiệu quả lớn hơn sharding OLTP.

## 39. Ví dụ: SaaS nhiều tenants

Một SaaS có 20.000 tenants. Mỗi tenant có users, orders, invoices và audit events.

### 39.1. Một node ban đầu

Dùng tenant_id trong keys, indexes và foreign keys. Nếu workload còn trong capacity, giữ một cluster đơn giản.

### 39.2. Read replicas

Chuyển dashboards/reporting stale-tolerant sang replicas; giữ critical transactional reads ở primary.

### 39.3. Partitioning

Partition audit/events theo thời gian để retention và query pruning.

### 39.4. Sharding theo tenant

Khi primary đạt write/storage ceiling, tenant_id có thể là shard key vì phần lớn transactions nằm trong tenant.

### 39.5. Tenant skew

Một vài enterprise tenants có thể tạo phần lớn traffic. Đặt chúng trên dedicated shards hoặc thiết kế split strategy.

### 39.6. Cross-tenant reporting

Đưa analytics toàn hệ thống sang warehouse/CDC pipeline thay vì fan-out mọi OLTP queries trên tất cả shards.

## 40. Ví dụ: hệ thống events/time-series

Một ứng dụng thu thập hàng tỷ events theo thời gian.

### 40.1. Partitioning theo thời gian

Nếu queries chủ yếu theo time windows và retention, time partitioning trên một node có thể đáp ứng lâu dài.

### 40.2. Retention

Detach/archive/drop partitions cũ theo policy. Không giữ toàn bộ event history trên primary nếu business không cần.

### 40.3. Sharding theo tenant/device/time

Nếu ingest throughput vượt một primary, có thể chia theo tenant/device hash hoặc region. Đảm bảo event ordering và query locality.

### 40.4. Analytics

Dữ liệu event thường phù hợp CDC/ETL vào analytical store. Tránh chạy full scans trên OLTP primary.

## 41. Ví dụ: global application

Một ứng dụng có users tại nhiều regions và yêu cầu latency thấp.

### 41.1. Local read cache/replica

Bắt đầu với regional caches hoặc read replicas nếu stale reads được chấp nhận.

### 41.2. Data residency

Nếu records phải ở region cụ thể, tenant/region placement có thể trở thành shard key hoặc database boundary.

### 41.3. Local writes

Nếu mỗi tenant có một home region, writes có thể route về regional primary/shard owner.

### 41.4. Cross-region workflows

Payments, inventory và global accounts có thể cần consistency/coordination phức tạp. Thiết kế saga hoặc centralized ownership thay vì giả định transaction local.

## 42. Migration từ single node sang sharded architecture

Một kế hoạch chuyển đổi nên có các bước:

1. Xác định workload bottleneck và business goal.
2. Chọn data ownership boundary/shard key.
3. Inventory tables, foreign keys, transactions và queries.
4. Xác định global IDs/uniqueness.
5. Thiết kế shard map và routing.
6. Chọn framework/platform.
7. Rehearse schema migrations trên nhiều shards.
8. Copy initial data.
9. Đồng bộ changes trong migration window.
10. Validate counts, checksums và business invariants.
11. Cutover reads/writes theo tenant/range.
12. Theo dõi hot shards, errors và latency.
13. Giữ rollback/reconciliation plan.
14. Rebalance và scale theo metrics.

### 42.1. Dual-write risks

Ghi vào old và new database đồng thời có thể tạo partial success. Nếu cần dual-write, dùng outbox/CDC, idempotency và reconciliation thay vì hai writes độc lập không coordination.

### 42.2. Backfill

Copy theo key ranges/batches và checkpoint. Tránh làm primary cũ quá tải khi vừa phục vụ traffic vừa export.

### 42.3. Cutover

Freeze writes hoặc dùng CDC catch-up để xác định consistency point. Update routing metadata một cách atomic/versioned.

### 42.4. Rollback

Nếu new shards đã nhận writes, quay lại old node cần reverse sync/reconciliation. Chỉ đổi endpoint có thể làm mất dữ liệu mới.

## 43. Failure scenarios trong distributed architecture

Phải test:
- Một shard unreachable.
- Replica lag quá cao.
- Coordinator/router restart.
- Network timeout sau khi write commit.
- Một shard đầy disk.
- Migration thành công trên một phần shards.
- Rebalance bị gián đoạn.
- Global metadata stale.
- Hot shard vượt capacity.
- Backup/restore một shard.
- Cross-shard transaction prepare nhưng coordinator chết.

### 43.1. Partial availability

Quyết định tiếp tục phục vụ tenants trên shards khỏe hay fail toàn service. Business contract phải rõ.

### 43.2. Idempotent retries

Một timeout không cho biết write đã commit chưa. Dùng operation IDs và unique constraints trong shard scope.

### 43.3. Circuit breakers

Ngăn router tiếp tục gửi requests tới shard lỗi và tạo queue không giới hạn.

### 43.4. Recovery ownership

Xác định ai có thể promote replica, repair shard map, replay changes hoặc resume rebalance.

## 44. Anti-patterns khi phân tán

- Shard trước khi đo bottleneck.
- Chọn shard key chỉ vì dễ code.
- Chọn key phân bố rows đều nhưng traffic skew nặng.
- Mọi query đều scatter-gather.
- Transactions thường xuyên cross-shard.
- Global counters/unique checks trở thành central bottleneck.
- Dùng asynchronous replication nhưng giả định strong consistency.
- Dùng read replicas cho read-after-write mà không có policy.
- Không có shard map versioning.
- Không có rebalancing tooling.
- Migration chỉ chạy trên một shard.
- Backup từng shard mà không có consistent recovery plan.
- Không quan sát per-shard metrics.
- Dual-write không idempotent.
- Không có tenant/data migration path.
- Dùng FDW như thể tự động có distributed transaction guarantees.
- Nhầm partitioning trong một cluster với sharding.
- Nhầm HA replicas với write scaling.
- Không test partial failures và retry behavior.
- Không tính engineering/on-call cost.

## 45. Decision checklist

Trước khi quyết định sharding/distributed data, trả lời:

| Câu hỏi | Bằng chứng cần có |
|---|---|
| Bottleneck là gì? | Metrics và query analysis |
| Đã tối ưu query/schema chưa? | EXPLAIN, index review, load test |
| Scale up có còn khả thi? | Instance/storage options và cost |
| Read replicas/cache có đủ? | Read/write split và consistency needs |
| Partitioning có giải quyết? | Partition pruning/lifecycle benefit |
| Workload có shard key tự nhiên? | Query/transaction access patterns |
| Cross-shard transactions bao nhiêu? | Transaction tracing |
| Data/traffic skew ra sao? | Per-tenant/key distribution |
| Global uniqueness cần gì? | ID and constraint design |
| Recovery có đáp ứng RTO/RPO? | Restore and failover rehearsal |
| Team vận hành được không? | Runbooks, staffing, automation |
| Chi phí có hợp lý? | TCO per request/transaction |
| Migration có thể rollback? | CDC/reconciliation/failback plan |
| Multi-region có thực sự cần? | Latency/residency requirements |

## 46. Bài tập thực hành có đáp án

### Bài 1. PostgreSQL một node là gì?

**Đáp án:** Một PostgreSQL cluster chạy trên một host/instance, thường có một primary xử lý writes và có thể có standby/replicas riêng.

### Bài 2. Nhiều databases trong cùng cluster có chia CPU thành nhiều phần độc lập không?

**Đáp án:** Không. Chúng chia sẻ tài nguyên host và cluster.

### Bài 3. Scale up là gì?

**Đáp án:** Tăng CPU, RAM, storage hoặc network capacity của một node.

### Bài 4. Scale out là gì?

**Đáp án:** Thêm nodes và phân phối reads, writes hoặc dữ liệu qua nhiều nodes.

### Bài 5. Một database lớn có nhất thiết phải shard?

**Đáp án:** Không. Cần xét workload, working set, query patterns, hardware và recovery requirements.

### Bài 6. Vì sao peak load quan trọng hơn daily average?

**Đáp án:** Capacity phải chịu bursts, batch jobs và peak concurrency; average có thể che giấu overload.

### Bài 7. Read replica có tăng write throughput cho primary không?

**Đáp án:** Không. Nó chủ yếu offload reads; writes vẫn đi qua primary.

### Bài 8. HA và horizontal scaling khác nhau thế nào?

**Đáp án:** HA giảm downtime khi lỗi; horizontal scaling tăng capacity/locality bằng nhiều nodes.

### Bài 9. Physical standby thường nhận writes trực tiếp như primary không?

**Đáp án:** Không. Nó replay WAL và thường read-only cho tới khi được promote.

### Bài 10. Partitioning trong PostgreSQL một cluster có phải sharding?

**Đáp án:** Không. Partitions vẫn nằm trong cùng cluster/node resources.

### Bài 11. Partition pruning là gì?

**Đáp án:** Planner loại partitions không liên quan tới query predicates, giảm lượng data cần scan.

### Bài 12. Khi nào partitioning theo thời gian hữu ích?

**Đáp án:** Khi data lifecycle/query chủ yếu theo time ranges và cần retention/archive/drop partitions.

### Bài 13. Sharding là gì?

**Đáp án:** Chia logical dataset thành subsets lưu trên các independent database shards.

### Bài 14. Shard key quyết định điều gì?

**Đáp án:** Data placement, request routing và khả năng localize transactions/queries.

### Bài 15. Vì sao tenant_id thường là shard key SaaS tốt?

**Đáp án:** Nhiều transactions/queries thường nằm trong một tenant, giúp colocate data và giảm cross-shard work.

### Bài 16. Hot shard là gì?

**Đáp án:** Shard nhận traffic hoặc writes lớn hơn peers và trở thành bottleneck.

### Bài 17. Data skew và traffic skew khác nhau thế nào?

**Đáp án:** Data skew là phân bố storage/rows không đều; traffic skew là requests/load không đều.

### Bài 18. Hash sharding có ưu điểm gì?

**Đáp án:** Phân bố keys khá đều nếu hash/key distribution tốt.

### Bài 19. Range sharding có ưu điểm gì?

**Đáp án:** Range queries có thể route tới ít shards và giữ locality theo key range.

### Bài 20. Sequential inserts có thể làm range shard nào nóng?

**Đáp án:** Range cuối cùng nhận các keys mới liên tục.

### Bài 21. Scatter-gather là gì?

**Đáp án:** Gửi query tới nhiều shards rồi thu/hợp nhất kết quả.

### Bài 22. Vì sao global ORDER BY/LIMIT khó hơn trên shards?

**Đáp án:** Mỗi shard trả local ordering; coordinator phải merge results và xử lý global top-N.

### Bài 23. AVG có thể combine bằng cách lấy trung bình các shard averages không?

**Đáp án:** Không nếu shard counts khác nhau. Cần combine SUM và COUNT rồi chia.

### Bài 24. Cross-shard transaction là gì?

**Đáp án:** Transaction tác động tới dữ liệu nằm trên nhiều shards.

### Bài 25. 2PC có trade-off gì?

**Đáp án:** Cung cấp coordination cho atomic commit nhưng thêm latency, coordinator dependency và prepared-transaction recovery.

### Bài 26. Saga là gì?

**Đáp án:** Workflow gồm local transactions và compensating actions; không tương đương atomic rollback toàn cục.

### Bài 27. Vì sao retry distributed write cần idempotency?

**Đáp án:** Timeout có thể xảy ra sau khi remote commit; retry mù có thể thực hiện operation hai lần.

### Bài 28. Một shard key tốt cần query locality thế nào?

**Đáp án:** Các rows thường được đọc/ghi cùng nhau nên nằm trên cùng shard.

### Bài 29. Vì sao global unique constraint khó trong sharding?

**Đáp án:** Không có một local index/constraint tự kiểm tra tất cả values trên mọi shards.

### Bài 30. Sequence local trên mỗi shard có thể tạo duplicate IDs không?

**Đáp án:** Có. Cần UUID, composite IDs, range allocation hoặc globally coordinated ID strategy.

### Bài 31. Citus cung cấp mô hình nào?

**Đáp án:** Coordinator/workers phân phối tables/shards theo distribution key và thực thi queries phân tán trong phạm vi hỗ trợ.

### Bài 32. postgres_fdw có tự cung cấp complete sharding framework không?

**Đáp án:** Không. Nó cung cấp foreign table access/federation, không tự giải quyết mọi routing, rebalancing và global consistency.

### Bài 33. PostgreSQL wire compatibility bảo đảm full SQL compatibility không?

**Đáp án:** Không. Cần kiểm tra semantics, features, extensions và unsupported operations.

### Bài 34. Vì sao multi-primary phức tạp?

**Đáp án:** Cần conflict resolution, ordering, identity allocation và transaction consistency across writers.

### Bài 35. Khi nào nên giữ một node?

**Đáp án:** Khi workload nằm trong capacity hợp lý, transactions cross-table nhiều, shard key không tự nhiên hoặc distributed complexity lớn hơn lợi ích.

### Bài 36. Khi nào cân nhắc sharding?

**Đáp án:** Khi bottleneck đã đo và tối ưu, một node không đáp ứng capacity/SLO, workload chia được theo key và cross-shard work có thể kiểm soát.

### Bài 37. Vì sao database size đơn lẻ không đủ để quyết định?

**Đáp án:** Row width, working set, query mix, concurrency, indexes và I/O patterns quyết định load thực tế.

### Bài 38. Connection pooling có thể giải quyết bottleneck nào?

**Đáp án:** Connection churn và backend-process overhead do quá nhiều client connections.

### Bài 39. Analytics workload có thể offload đi đâu?

**Đáp án:** Read replica, warehouse hoặc analytical platform tùy freshness/volume needs.

### Bài 40. Vì sao phải theo dõi per-shard metrics?

**Đáp án:** Aggregate averages có thể che hot shard, storage imbalance hoặc một node lỗi.

### Bài 41. Rebalancing là gì?

**Đáp án:** Di chuyển shards/ranges/tenants giữa nodes để cân bằng capacity và load.

### Bài 42. Vì sao shard map cần versioning?

**Đáp án:** Clients/router cần nhận biết mapping mới và tránh ghi vào owner cũ trong lúc movement/cutover.

### Bài 43. Vì sao backup per shard chưa chắc tạo consistent global restore?

**Đáp án:** Các shards có thể được backup/restore tại những điểm thời gian khác nhau; cross-shard invariants cần coordination.

### Bài 44. Migration trên nhiều shards cần gì?

**Đáp án:** Orchestrated rollout, per-shard history/locks, bounded concurrency, resume và schema compatibility.

### Bài 45. Multi-region synchronous replication ảnh hưởng latency ra sao?

**Đáp án:** Commit có thể phải chờ network acknowledgement xa, làm tăng write latency.

### Bài 46. Asynchronous failover có rủi ro gì?

**Đáp án:** Replica chưa nhận/replay hết WAL có thể thiếu các writes gần nhất tại thời điểm failover.

### Bài 47. Vì sao dual-write nguy hiểm?

**Đáp án:** Hai writes độc lập có thể chỉ một bên thành công; cần outbox/CDC, idempotency và reconciliation.

### Bài 48. Dấu hiệu phân tán quá sớm là gì?

**Đáp án:** Chưa đo bottleneck, còn query/index/pooling/partitioning options và chưa có shard key rõ.

### Bài 49. Cần benchmark gì trước khi chọn distributed SQL?

**Đáp án:** Workload thực tế, transactions, SQL/extension compatibility, consistency, failure behavior, migrations và recovery.

### Bài 50. Quyết định phân tán dữ liệu cần bằng chứng nào?

**Đáp án:** Metrics, growth forecast, failed single-node options, shard-key locality, cross-shard transaction profile, cost model, team readiness và tested recovery plan.

## 47. Tài liệu PostgreSQL và hệ sinh thái liên quan

- [PostgreSQL Documentation](https://www.postgresql.org/docs/current/) — kiến trúc, performance, replication, partitioning và administration.
- [PostgreSQL Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html) — declarative partitioning trong một cluster.
- [PostgreSQL Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html) — primary/standby và WAL streaming.
- [PostgreSQL Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html) — publication/subscription và replication scope.
- [PostgreSQL Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — activity, locks, I/O và replication statistics.
- [PostgreSQL EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) — query plan analysis.
- [PostgreSQL postgres_fdw](https://www.postgresql.org/docs/current/postgres-fdw.html) — truy cập remote PostgreSQL tables.
- [Citus Documentation](https://docs.citusdata.com/) — distributed PostgreSQL, distribution keys, colocated tables và coordinator/workers.
- [PgBouncer Documentation](https://www.pgbouncer.org/) — connection pooling.
- [PostgreSQL Wiki: Sharding](https://wiki.postgresql.org/wiki/Shard) — các hướng tiếp cận sharding trong hệ sinh thái PostgreSQL.

Feature support, transaction guarantees, replication behavior và deployment options thay đổi theo PostgreSQL major version, Citus release và managed provider. Kiểm tra compatibility matrix và chạy failure/recovery tests trước khi đưa distributed architecture vào production.

## 48. Tổng kết: chỉ phân tán khi bottleneck và data boundary đã rõ

```text
Measure workload and bottleneck
             |
             v
Optimize SQL / schema / indexes
             |
             v
Pool connections and isolate workloads
             |
             v
Scale up / cache / read replicas
             |
             v
Partition for pruning and lifecycle
             |
             v
Does one node still miss capacity/SLO?
          /             \
        No               Yes
        |                 |
        v                 v
Keep single node     Is there a natural shard key?
and monitor             /          \
                      No            Yes
                      |              |
                      v              v
                Redesign workload  Evaluate sharding /
                or keep centralized distributed SQL
                                      |
                                      v
                           Test transactions, failures,
                           rebalancing, backup and cost
                                      |
                                      v
                                  Cut over
```

Những nguyên tắc cần nhớ:

1. **PostgreSQL một node có thể scale rất xa.** Đo workload và tối ưu trước khi thay đổi kiến trúc.
2. **Database size không tự quyết định sharding.** Query mix, working set, concurrency, I/O và recovery mới là bằng chứng quan trọng.
3. **Scale up, replicas và partitioning giải quyết các vấn đề khác nhau.** Không nhầm HA/read scaling với write sharding.
4. **Read replicas giảm read load, không tự tăng write capacity của primary.**
5. **Partitioning trong một cluster không phân phối tài nguyên qua nodes.** Nó hỗ trợ pruning và data lifecycle.
6. **Sharding cần một data ownership key rõ.** Query locality, transaction locality và traffic distribution quyết định hiệu quả.
7. **Cross-shard joins và transactions làm complexity tăng.** Thiết kế domain boundaries để giữ operations local.
8. **Distributed systems phải xử lý partial failure, retries và consistency.** Network timeout không cho biết write đã commit hay chưa.
9. **Mỗi shard cần backup, HA, migrations và observability.** Tổng thể còn cần global metadata và consistent recovery strategy.
10. **Rebalancing và schema rollout là công việc thường xuyên.** Không chỉ là một lần chia dữ liệu.
11. **Tính engineering và on-call cost vào TCO.** Thêm nodes cũng thêm failure modes và vận hành.
12. **Phân tán khi một node không còn đáp ứng yêu cầu và workload có thể chia hợp lý.** Quyết định dựa trên metrics, forecast, shard key và recovery rehearsal.

**Một câu để nhớ:** *Hãy mở rộng PostgreSQL một node tới giới hạn hợp lý; chỉ phân tán khi bottleneck đã được đo, dữ liệu có thể chia theo một key tự nhiên và team sẵn sàng vận hành consistency, routing, recovery cùng nhiều shards.*

