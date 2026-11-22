# Ghi rõ phiên bản, cấu hình và các giả định khi báo cáo so sánh

## 1. Vì sao một bảng “NoSQL A nhanh hơn NoSQL B” có thể vô nghĩa?

Một nhóm Java cần chọn database cho dịch vụ đặt hàng. Báo cáo nội bộ ghi:

> Database A đạt 60.000 requests/giây và p99 = 18 ms; Database B đạt 35.000 requests/giây và p99 = 31 ms. Đề xuất chọn A.

Nhìn qua, A có vẻ thắng. Nhưng người phản biện hỏi:

- A và B là phiên bản nào? Driver Java nào? Có một bên dùng bản release candidate không?
- A chạy trên ba máy 32 vCPU, B chạy trên ba máy 8 vCPU hay không?
- A ghi với acknowledgment yếu hơn, còn B phải xác nhận nhiều replica trước khi trả lời?
- Dataset có vừa RAM của A nhưng không vừa RAM của B?
- B có đang build index/compact dữ liệu trong lúc đo?
- Đã chạy query đúng kiểu nghiệp vụ, hay chỉ thử GET theo khóa?
- Kết quả là median của năm lần chạy hay kết quả tốt nhất được chọn?
- “60.000 requests/giây” gồm requests thành công, timed out, throttled hay retry?
- Cấu hình và giả định nào chưa được ghi lại?

Nếu không trả lời được, phép so sánh không đủ bằng chứng để đưa ra quyết định kiến trúc. **Một con số benchmark thiếu bối cảnh không thể được diễn giải như năng lực cố hữu của sản phẩm.**

Bài học thuộc module **Database No SQL**, chương **Đánh giá và lựa chọn**, trình bày cách lập báo cáo so sánh có khả năng kiểm chứng và tái lập: ghi rõ **phiên bản**, **cấu hình**, **workload**, **phương pháp đo**, **giả định**, **giới hạn** và **mức chắc chắn của kết luận**.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Giải thích vì sao phải gắn kết quả benchmark với phiên bản chính xác và cấu hình tại thời điểm chạy.
2. Lập inventory của database engine, managed service, driver, JDK, OS, client SDK, schema, indexes và các dependencies ảnh hưởng kết quả.
3. Mô tả topology, consistency, durability, replication, partitioning, storage, cache, read/write limits và pricing assumptions.
4. Ghi lại dataset và workload đủ để người khác tái hiện hoặc nhận diện điểm khác biệt.
5. Phân biệt thông số quan sát thực tế, thông số được khai báo và giả định chưa kiểm chứng.
6. Báo latency distribution, throughput, errors, resource use, cost và độ bất định một cách minh bạch.
7. So sánh MongoDB, DynamoDB, Cassandra/ScyllaDB, Redis và Elasticsearch/OpenSearch mà không đánh đồng các guarantees khác nhau.
8. Biết cách viết kết luận có điều kiện và decision record, tránh quảng bá sản phẩm từ kết quả quá hẹp.
9. Dùng manifest YAML/JSON, cấu trúc bảng kết quả và ví dụ mã Java để lưu dấu thí nghiệm.
10. Thiết kế checklist bàn giao, bài tập và tiêu chí tái lập cho quyết định lựa chọn NoSQL.

## 2. Kết quả benchmark là một mệnh đề có điều kiện

Một cách diễn đạt chính xác:

> Với dataset D, workload W, cấu hình C, phiên bản V, môi trường E và phương pháp M, hệ A đạt p99 = X ms tại throughput Y requests/giây, với tỷ lệ lỗi Z trong khoảng thời gian T.

Có thể biểu diễn khái niệm:

\[
\mathrm{Result}=f(V,C,E,D,W,M,T,\mathrm{OperationalState}).
\]

Mọi thành phần trong công thức có thể thay đổi kết quả. Đó không phải công thức dự báo chính xác hiệu năng mà là **danh sách điều kiện cần ghi lại khi công bố**.

### 2.1. Không có “NoSQL nhanh nhất” cho mọi ứng dụng

Một key-value lookup nhỏ, truy vấn aggregation nhiều fields, traversal đồ thị, search full-text và scan một partition rộng có access patterns khác nhau. Từ một điểm đo không thể suy ra mọi workload.

### 2.2. So sánh sản phẩm hay so sánh giải pháp?

Một managed DynamoDB table với on-demand capacity và một cụm Cassandra tự vận hành khác không chỉ database engine mà cả vận hành, placement, cost model và failure model. Báo cáo cần nêu đang so **khả năng cung cấp một SLO** hay chỉ so engine trong môi trường tối ưu hóa.

### 2.3. Giả định không phải lỗi

Mọi thử nghiệm đều có giả định: dữ liệu tăng 30%/năm, 90% GET, một Region, 99,9% uptime mục tiêu. Điều sai là **giấu** giả định hoặc trình bày chúng như sự thật đã đo.

### 2.4. Tái lập không nhất thiết cho ra cùng một con số

Thực nghiệm trên cloud có nhiễu. Người khác tái lập đúng thủ tục có thể ra phân bố khác một ít; yêu cầu hợp lý là có đủ thông tin để kiểm tra, định lượng sai khác và xác nhận kết luận trong khoảng sai số chấp nhận.

## 3. Phân biệt bốn lớp thông tin phải ghi

| Lớp | Nội dung | Câu hỏi được trả lời |
|---|---|---|
| Version | Engine, service feature, driver, runtime, công cụ đo | Ta chạy những phần mềm nào? |
| Configuration | Topology, consistency, indexes, replication, cache, limits | Chúng được cấu hình như thế nào? |
| Assumptions | Quy mô, tăng trưởng, availability, cost, data residency | Kết luận dựa trên điều gì chưa hoặc không thể đo trực tiếp? |
| Evidence | Raw results, scripts, metrics, experiment ID, thời gian | Bằng chứng nào hỗ trợ kết luận? |

### 3.1. Version là định danh của hành vi

Hai major/minor releases có thể thay query planner, indexing, consistency API, concurrency control, compaction, serialization hoặc behavior khi failover.

### 3.2. Configuration là một phần của “sản phẩm được thử”

MongoDB với writeConcern=majority khác MongoDB với acknowledgment yếu hơn; Redis AOF appendfsync everysec khác Redis không persistence; DynamoDB Query base table khác Scan/GSI eventual read.

### 3.3. Assumption là một ranh giới suy luận

Nếu định lượng chi phí dựa trên 1 TB data, tỷ lệ cache hit 95%, một Region và workload 80/20, kết luận về “rẻ hơn” chỉ đúng với các giả định ấy và biên độ biến động được xét.

### 3.4. Evidence giúp phản biện và tái lập

Đính kèm hoặc tham chiếu công cụ đo, query manifests, mẫu dữ liệu tổng hợp, kết quả nhiều runs và nguồn metrics. Không dùng ảnh dashboard không có tên bài đo/timestamp làm bằng chứng duy nhất.

## 4. Sơ đồ chuỗi từ giả định tới quyết định

~~~mermaid
flowchart TD
    A["Business goals / SLO / constraints"] --> B["Workload and data model"]
    B --> C["Versioned configurations"]
    C --> D["Reproducible experiment"]
    D --> E["Raw observations and telemetry"]
    E --> F["Analysis / uncertainty / fairness"]
    F --> G["Conditional comparison"]
    G --> H["Decision and rollback criteria"]
    I["Assumptions register"] --> B
    I --> F
    J["Change log / versions"] --> C
    K["Limitations and untested cases"] --> G
~~~

### 4.1. Quyết định đi từ bài toán nghiệp vụ

Mục tiêu là chọn mô hình đáp ứng access patterns và SLO với chi phí/rủi ro chấp nhận được, không phải thi xem hệ nào đạt QPS cao nhất ở truy vấn dễ nhất.

### 4.2. Dữ liệu được sinh cũng là thiết kế thử nghiệm

Một generator tạo toàn khóa ngẫu nhiên khác workload 1% hot keys nhận 70% traffic. Phải lưu seed/distribution, nếu không người khác không tái hiện hot-partition behavior.

### 4.3. Kết luận phải có phạm vi

“Trong workload point-read và dataset 200 GB ở một Region, A đạt p99 thấp hơn” có cơ sở hơn “A luôn nhanh hơn B”.

## 5. Danh mục phiên bản tối thiểu

Khi chạy bằng Java, các phiên bản thường cần ghi:

| Thành phần | Ví dụ thông tin cần lưu | Lý do |
|---|---|---|
| Database engine | product, exact version/build, storage engine | Query/compaction/durability behavior |
| Managed service | provider, region, tier, engine-compatible version, feature mode | Dịch vụ có lớp quản lý riêng |
| Cluster/operator | Kubernetes operator/chart version, deployment method | Topology, resource limits và upgrades |
| Java runtime | JDK vendor, version, GC, heap flags | Connection handling, GC và throughput |
| Database driver | Artifact coordinates và exact version | Retry, pooling, protocol, serialization |
| SDK/core libraries | AWS SDK, Jackson, Netty, reactive runtime | HTTP, retry, event loop |
| Load generator | YCSB/k6/Gatling/custom version, Git commit | Cách phát requests và đo số liệu |
| OS/kernel | OS image, kernel version | IO/network scheduling |
| Container image | Immutable digest, không chỉ tag latest | Tránh image bị thay |
| Query/schema | Migration version, index definitions và data model revision | Plan và selectivity |
| Automation scripts | Git commit/tag, config hash | Tái tạo procedure |
| Observability | Collector/agent version, metric definitions | Khác biệt cách lấy mẫu đo |

### 5.1. Không chỉ viết “MongoDB 7”

Ghi exact patch/build và storage engine nếu có; patch có thể sửa một bug/behavior ảnh hưởng benchmark.

### 5.2. Tag latest không phải định danh ổn định

Một image tag có thể được publish lại. Khi dùng containers, lưu image digest; với artifacts, lưu dependency lockfile và build commit.

### 5.3. Rolling upgrade tạo mixed-version state

Nếu cluster có nodes vX và vY trong lúc benchmark, phải nêu tỷ lệ, compatibility mode, feature flags và thời điểm rolling upgrade; thường nên tránh so kết quả ở trạng thái chuyển tiếp không chủ đích.

### 5.4. Managed service không lộ hết phiên bản internals

Khi provider không công bố internal build/node placement, ghi phần đã biết từ API/console và đánh dấu phần không thể quan sát là **unknown/provider-managed**, không bịa một phiên bản.

## 6. Ghi cấu hình NoSQL ở nhiều tầng

### 6.1. Logical model

Collections/tables, partition keys, clustering/sort keys, documents, secondary indexes, TTL, materialized views, GSI và schema/index versions.

### 6.2. Consistency và durability

Read/write consistency levels, quorum/majority, acknowledgment, journal/WAL/AOF/persistence, transactions, conditional writes, staleness policy.

### 6.3. Replication và placement

Replication factor, number of zones, Region, leader/replica layout, automatic failover, cross-region replication và phân phối hot partitions.

### 6.4. Capacity

Node count/size, vCPU/RAM, storage size/IOPS/throughput, provisioned RCUs/WCUs hoặc on-demand, autoscaling limits, reserved capacity và disk headroom.

### 6.5. Network/client

Region của load generator so với DB, TLS, compression, connection pool, max in-flight, timeouts, retry policies và consistency của client.

### 6.6. Operational background

Compaction, backup/snapshot, index build, reshard/rebalance, repair, checkpointing, TTL cleanup, cold caches, autoscaling và failover experiments.

### 6.7. Security

Encryption at rest/in transit, auth mode, IAM/ACL, audit logs và network policies khi chúng ảnh hưởng overhead/capability. Không ghi secrets vào báo cáo.

## 7. Nhất quán và độ bền phải so trên hợp đồng tương đương

Đọc/ghi một lần không có nghĩa các hệ cung cấp cùng guarantee.

| Lựa chọn | Cần ghi | Hệ quả khi so |
|---|---|---|
| Majority/quorum write | Acknowledgment và số replicas cần xác nhận | Có thể tăng latency, đổi durability |
| Eventual read | Có thể thấy version cũ trong một khoảng | Đổi latency và độ mới |
| Strong read nơi được hỗ trợ | Read mode và API cụ thể | Có thể tăng cost/latency |
| Single-item atomic write | Scope của atomicity | Khác transaction nhiều items |
| Multi-item transaction | Isolation, failure/size limits | Extra coordination |
| Async geo replication | Lag, conflict resolution | Không như synchronous cross-region |
| WAL/AOF/journaling | fsync policy, ACK semantics | Độ bền ghi khi crash |

### 7.1. Một bên nhanh hơn vì làm ít việc hơn

Nếu A trả ACK khi nhận trên một node, B chỉ ACK sau khi quorum durable, A có thể nhanh hơn nhưng không được gọi là superior durability-and-latency result.

### 7.2. Không buộc hai engine có cùng nút cấu hình

Không phải hai sản phẩm đều có một tùy chọn QUORUM giống nhau. Hãy so **observable business guarantees** và nêu khác biệt không quy đổi được.

### 7.3. Kiểm chứng claim bằng fault behavior

Không chỉ mô tả “majority enabled”. Nếu quyết định phụ thuộc RPO/availability, cần thử crash/failover theo phương pháp phù hợp trong môi trường được phép và ghi observed behavior cùng giới hạn.

### 7.4. Không dùng read preference như một chi tiết nhỏ

Đọc từ primary so với replica có thể thay p99 và staleness. Trong báo cáo, nó là một cấu hình **quan trọng bậc nhất**.

## 8. Topology và tài nguyên máy

Một mô tả kiểu “3 nodes” là thiếu:

~~~yaml
environment:
  provider: ExampleCloud
  region: example-region-1
  availabilityZones: 3
  dbNodes: 3
  instanceClass: example-8vcpu-32gib
  vcpuPerNode: 8
  memoryGiBPerNode: 32
  volume:
    type: example-ssd
    capacityGiBPerNode: 800
    provisionedIops: 6000
    throughputMiBps: 250
  workloadClient:
    instanceClass: example-4vcpu-16gib
    placement: same-region-different-subnet
  networking:
    tls: true
    compression: false
~~~

Các giá trị ở đây **thuần minh họa**, không đại diện một máy/cloud instance cụ thể. Khi làm báo cáo thật, thay bằng values được đo/xác nhận.

### 8.1. vCPU/RAM chưa đủ

Storage IOPS, throughput, disk type, network limits, CPU oversubscription, noisy neighbors và autoscaling thường quyết định tail latency.

### 8.2. Client máy phát tải cũng có thể nghẽn

Nếu load generator chạm 100% CPU, nó không tạo đủ offered load và hệ DB trông như hết capacity; phải đo cả client.

### 8.3. Placement có thể tạo lợi thế không công bằng

A ở cùng AZ với load generator còn B khác Region: RTT network khác lớn. Nếu mô hình production sẽ cross-region, khác biệt là thực tế; nếu không, phải chuẩn hóa placement.

### 8.4. Cần biết scale unit là gì

So 3 nodes A với một managed table B không có node visibility nên quy đổi qua throughput/availability/cost SLO, không cố tạo số “nodes tương đương” không có căn cứ.

## 9. Data model và indexes là một phần của thử nghiệm

NoSQL thường tối ưu theo access patterns, nên benchmark chịu ảnh hưởng lớn từ schema/keys.

### 9.1. Partition/shard key

Chọn tenantId thuần có thể tạo hot tenant; tenantId#bucket có thể phân tải nhưng yêu cầu fan-out cho range queries. Cần ghi key design và cardinality.

### 9.2. Secondary indexes

Một bên có index đúng filter/sort, bên kia phải scan: không thể kết luận engine thua mà không giải thích query plan/data model.

### 9.3. Denormalization

A ghi một document nhúng items; B ghi header + item rows. B có thể chịu write amplification nhưng query một loại aggregate khác tốt hơn. Phải nêu operations được tính và không được tính.

### 9.4. Caching

So cached Redis GET với cold MongoDB query không đo hai database cùng nhiệm vụ. Nếu caching là kiến trúc giải pháp, ghi đầy đủ cache hit ratio, TTL, miss path, invalidation và chi phí.

### 9.5. Query plan evidence

Khi engine hỗ trợ, lưu explain/profile/index statistics cho những access patterns quan trọng, tránh chỉ nói “có index”.

## 10. Dataset phải được mô tả đủ chi tiết

Một báo cáo nên có:

| Đặc tính | Ví dụ | Tại sao cần |
|---|---|---|
| Số records | 30 triệu orders | Quy mô |
| Raw/logical size | 200 GB | Độ lớn payload |
| Physical storage | 450 GB gồm indexes/replicas theo cách tính | Footprint |
| Key distribution | Zipfian, hot 1% keys | Hotspots |
| Value size | p50=1 KiB, p99=32 KiB | Network/serialization |
| Nested fields | items p50=3, p99=30 | Document hydration |
| Tenant skew | Top 10 tenants = 60% requests | Hot tenants |
| Time distribution | 90% data cũ, 10% recent | Index and cache locality |
| Missing/nullable fields | 8% legacy documents | Mapping/index paths |
| TTL/expiration | Sessions expire after 24h | Churn/background cleanup |
| Updates/deletes | 20% mutation workload | Tombstone/compaction cost |
| Compression | Enabled, codec | Physical IO |
| Generator | Version/seed | Reproducibility |

### 10.1. “1 triệu records” chưa nói toàn bộ

Một triệu keys 100 bytes khác một triệu documents 100 KiB. Tổng size và phân bố sizes ảnh hưởng cache, disk, serialization và network.

### 10.2. Skew quyết định partition hotspots

Uniform random keys làm phân tải dễ hơn một ứng dụng có một celebrity user hoặc một tenant rất lớn.

### 10.3. Dữ liệu synthetic phải được công bố

Nếu dùng synthetic data, ghi generator, seed, schema, sampling assumptions và các khác biệt đã biết so với dữ liệu thực; không khẳng định nó đại diện đầy đủ production chỉ vì số lượng giống.

### 10.4. Privacy và dữ liệu production

Khi test bằng dữ liệu thật, cần quyền sử dụng, masking/encryption và retention. Không đưa PII hoặc credentials vào manifest/public benchmark artifacts.

## 11. Ghi workload bằng operations và access patterns

Một cấu hình workload giả định:

~~~yaml
workload:
  description: Orders API representative mix
  durationSeconds: 900
  offeredRatePerSecond: 25000
  concurrency: 256
  operations:
    - name: getOrderById
      share: 0.55
      resultLimit: 1
    - name: listOrdersByTenantAndTime
      share: 0.20
      limit: 20
      order: createdAtDescendingThenOrderId
    - name: createOrder
      share: 0.15
      result: acknowledgedWrite
    - name: updateOrderStatus
      share: 0.08
      condition: expectedVersion
    - name: deleteExpiredOrder
      share: 0.02
  keyDistribution: zipfian
  randomSeed: 5742026
~~~

Các tỷ trọng phải khớp quan sát/giả định nghiệp vụ được công bố; không chọn tỷ lệ chỉ để đạt kết quả đẹp.

### 11.1. Logical operation hay physical request?

Một getOrderById có thể gồm một MongoDB find hoặc nhiều DynamoDB Query/GetItem để hydrate kết quả. Báo logical business operations và physical database calls riêng, không che read amplification.

### 11.2. Tỷ lệ operations chưa đủ

Cần nêu key distribution, concurrency, payload sizes, paging, query filters, fan-out, update contention và số tenants.

### 11.3. Read-heavy khác write-heavy

Hệ tối ưu point GET có thể giảm hiệu năng khi updates gây index maintenance/compaction. Ghi read/write mix và operational state trong lúc đo.

### 11.4. Transactions và conditional writes

CreateOrder/updateStatus cần atomicity/version checks theo contract. Không thay bằng blind upserts chỉ để tăng QPS rồi dùng kết quả cho nghiệp vụ cần optimistic concurrency.

### 11.5. Query semantics

ListOrders phải có cùng filter, boundaries, sorting, pagination và consistency. Trả cùng 20 records nhưng sai thứ tự cũng có thể vi phạm API contract.

## 12. Offered load khác achieved throughput

Hai khái niệm:

- **Offered load:** số requests mà bộ phát tải dự kiến gửi mỗi giây.
- **Achieved throughput:** số logical operations hoàn tất thành công mỗi giây trong khoảng đo.

~~~text
Offered:           30,000 operations/s
Success completed: 24,000 operations/s
Failed/timeout:     4,000 operations/s
In flight:          2,000 operations at snapshot instant
~~~

Các con số minh họa không thể cộng trực tiếp vì in-flight là số lượng tại một thời điểm, không phải rate.

### 12.1. Attempts khác throughput nghiệp vụ

Nếu 10.000 commands bị retry thành 12.000 physical attempts, throughput nghiệp vụ vẫn tính theo logical commands completed.

### 12.2. Retry policy phải ghi

Max attempts, backoff, jitter, timeout, SDK/framework retry, error types triggering retry và per-operation deadline.

### 12.3. Timeout cũng là kết quả

Không loại timeout khỏi p99 rồi báo latency thấp mà giấu error rate. Công bố latency measurement scope và tỷ lệ lỗi riêng.

### 12.4. Open-loop so với closed-loop

Closed-loop virtual users gửi request mới sau khi response trước kết thúc; khi DB chậm, offered rate có thể giảm. Open-loop gửi theo lịch arrival định sẵn nhưng cần giới hạn queue/backlog. Ghi chế độ.

### 12.5. Coordinated omission

Nếu load generator ngừng phát lúc server treo, latency histogram chỉ đo các requests thực sự phát và có thể bỏ sót các yêu cầu lẽ ra phải đến. Ghi chính sách generator/latency correction và giới hạn số liệu.

## 13. Latency phải được báo dưới dạng phân bố

| Hệ | p50 | p95 | p99 | p99.9 | Thành công mỗi giây | Error rate |
|---|---:|---:|---:|---:|---:|---:|
| A cấu hình X | 8 ms | 25 ms | 80 ms | 210 ms | 21.000 | 0,12% |
| B cấu hình Y | 10 ms | 22 ms | 65 ms | 190 ms | 20.500 | 0,09% |

**Số giả định**, chỉ minh họa báo cáo, không phải benchmark sản phẩm thật.

### 13.1. Mean có thể che tail

Mean 10 ms nhưng có nhiều outlier 500 ms có thể gây tác động hơn mean 12 ms với p99 ổn định.

### 13.2. Ghi cỡ mẫu và histogram method

p99.9 trên vài trăm observations không đáng tin. Nêu sample count, sampling, HDR histogram hoặc quantile implementation.

### 13.3. Latency đo từ đâu?

Client-observed latency gồm serialization, network, pool waits và server; server execution time là đại lượng khác. Đừng trộn hai hệ đo khác tầng.

### 13.4. Saturation làm p99 phi tuyến

Một DB p99 tốt ở 10k QPS nhưng tăng vọt ở 20k. Thể hiện throughput-latency theo nhiều mức tải.

### 13.5. Per-operation percentiles

p99 chung có thể bị dominated bởi point GET; báo riêng GET, list/filter, update, delete và transaction.

## 14. So đường cong throughput-latency, không chọn một điểm đẹp

~~~text
Stage 1:  5k offered ops/s
Stage 2: 10k offered ops/s
Stage 3: 15k offered ops/s
Stage 4: 20k offered ops/s
Stage 5: 25k offered ops/s
~~~

Tại mỗi mức, ghi achieved throughput, p99, error rate, CPU, IO, queue depth, memory và autoscaling events.

### 14.1. SLO-constrained capacity

Một đại lượng hữu dụng: throughput tối đa trong khi p99 dưới 100 ms và error rate dưới 0,1%. Ngưỡng là ví dụ và phải do nghiệp vụ xác định.

### 14.2. QPS với lỗi cao không hữu ích

Hệ A “xử lý” 40k attempts/s nhưng 20% timeout, B hoàn tất 30k/s với 0,01% lỗi: raw attempts không đủ chứng minh A tốt hơn.

### 14.3. Stop condition

Ghi max duration, spending budget, error threshold và saturation criterion. Run ngừng do quota/cost không chứng minh đó là giới hạn tối đa của engine.

### 14.4. Nhiều trạng thái vận hành

Báo low utilization, expected peak và near saturation, thay vì một throughput trung bình.

## 15. Warmup và cold cache là hai bài đo riêng

### 15.1. Cold start

Sau restart, OS page cache, DB buffer pools, JVM JIT và connection pools có thể chưa warm.

### 15.2. Warm steady state

Sau khi warm cache và JIT, latency có thể giảm. Cả cold và warm đều quan trọng tùy mục tiêu production/DR.

### 15.3. Quy trình warmup

~~~text
Import data and build indexes
Wait for replication/catch-up
Warmup: 15 minutes, excluded from measurement
Measured steady state: 15 minutes
Reset policy before next run
~~~

Thời gian chỉ minh họa, không phải chuẩn chung.

### 15.4. Randomize run order

Nếu chạy A trước B hoặc ngược lại cố định, cache/host background state có thể thiên lệch. Ghi cách reset dataset/caches và thứ tự runs.

### 15.5. Không suy cold workload từ in-memory results

Nếu phần lớn dataset vừa RAM thì test có thể chủ yếu đo cached lookup, không đại diện data lớn gấp nhiều lần bộ nhớ.

## 16. Background tasks ảnh hưởng kết quả

Các tác vụ:

- Compaction hoặc SSTable merges.
- TTL cleanup/tombstone processing.
- Index build/refresh.
- Repair/anti-entropy.
- Checkpoint/snapshot/backup.
- Reshard/balancing và replica catch-up.
- JVM GC và runtime compilation.
- Autoscaling hoặc thay đổi throughput limits.

### 16.1. Không luôn tắt background jobs

Nếu production luôn có compaction/backup, một bài đo tắt hết sẽ kém đại diện. Có thể chạy clean baseline và realistic operational run riêng.

### 16.2. Timeline biến cố

Gắn timestamps của index build, compaction và failover lên metric graphs để giải thích spikes.

### 16.3. Test failover riêng

Steady-state benchmark không chứng minh RPO/RTO. Nếu reliability là tiêu chí chọn sản phẩm, chạy kịch bản lỗi riêng và ghi exact conditions.

## 17. Thống kê: nhiều lần chạy thay một kết quả đẹp nhất

Giả sử p99 của năm runs độc lập là:

~~~text
Run 1: 70 ms
Run 2: 78 ms
Run 3: 72 ms
Run 4: 101 ms
Run 5: 75 ms
~~~

Báo duy nhất 70 ms vì đó là run tốt nhất gây hiểu sai. Lưu từng run, timestamp, seed, tải và trạng thái hệ, rồi tóm tắt phân bố/hệ số biến thiên theo cách phù hợp.

### 17.1. Warmup không phải measurement

Tách warmup samples khỏi steady-state histogram nếu báo cáo mục tiêu steady state; nhưng nếu đo cold-start thì giữ và đặt tên kịch bản tương ứng.

### 17.2. Khoảng tin cậy

Có thể dùng bootstrap hoặc phương pháp thống kê phù hợp để ước lượng uncertainty của chênh lệch A/B. Khi requests có tương quan theo thời gian hoặc cùng hot key, bootstrap từng request như observations độc lập có thể đánh giá confidence quá cao; cân nhắc run/block-level resampling.

### 17.3. Percentiles không cộng đơn giản

Không lấy trung bình p99 của nodes/minutes làm p99 chung nếu số observations khác nhau. Cần histogram/raw samples được hợp nhất theo semantics tương ứng.

### 17.4. Ý nghĩa nghiệp vụ khác p-value

Chênh 1 ms có thể có ý nghĩa thống kê nhưng không đáng rủi ro migration. Một lỗi tenant isolation có thể loại ứng viên dù throughput cao.

### 17.5. Cỡ mẫu và lỗi hiếm

Một chạy 3 phút với zero errors không chứng minh “không bao giờ lỗi”. Công bố duration, sample size và giới hạn khả năng phát hiện sự kiện hiếm.

## 18. Mô hình chi phí phải có nguồn và ngày giá

Chi phí vận hành mỗi tháng có thể gồm:

~~~text
Compute / provisioned capacity
+ storage and replica/index footprint
+ read/write request charges
+ network transfer / cross-region egress
+ backups/PITR and retention
+ observability, support
+ operations/on-call assumptions
+ migration and recovery costs (when in scope)
~~~

### 18.1. Measured khác estimated

Measured là số read units, bytes, disk occupancy, CPU, storage footprint. Estimated là đơn giá, discounts, growth forecast, staffing cost. Đánh dấu nguồn của từng mục.

### 18.2. Giá phụ thuộc Region, tier, timestamp

Ghi price snapshot date, currency, Region, pricing tier, reserved capacity, taxes/discounts và yếu tố không bao gồm. Không dùng đơn giá không rõ thời điểm làm kết luận chắc chắn.

### 18.3. On-demand và provisioned

Chế độ capacity có thể thay cả latency/throttling và billing. Ghi mode chính xác và autoscaling settings thay vì ghi một chi phí của sản phẩm nói chung.

### 18.4. Physical storage amplification

Indexes, replicas, tombstones, compaction headroom và backup có thể khiến physical bytes lớn hơn logical dataset. Cần giải thích cách đo và các thành phần đã tính.

### 18.5. Công vận hành không mặc định bằng 0

Self-managed engine có thể giảm tiền instance nhưng cần upgrades, backup, pager/on-call và security patching. Nếu không định giá được, phân loại unknown/qualitative factor.

## 19. Reliability, vận hành và security là trục riêng

Đừng rút gọn mọi thứ về p99/QPS.

### 19.1. Availability

Phân biệt node/AZ/Region outage, failover time, brownout, eventual read và SLO theo business function. Số replicas không phải uptime proof.

### 19.2. Backup và restore

Ghi tính năng snapshot/PITR, retention, independence/immutability, RPO/RTO và measured restore drill; không suy có backup là đã thử restore.

### 19.3. Security

IAM/ACL, encryption, audit, tenant isolation, data residency, key management và compliance. Phải nêu những yêu cầu bắt buộc không được bỏ.

### 19.4. Developer experience

Schema evolution, query flexibility, Java driver/SDK maturity, data migration tooling, tracing và local integration tests.

### 19.5. Lock-in và portability

Managed APIs, export/import formats, backup portability, migration cost, operator expertise và strategic constraints có thể quan trọng hơn chênh p50 1 ms.

## 20. Cấu hình có thể thay ngay giữa một run

Một benchmark 30 phút có thể đi qua autoscaling event, index rebuild, connection pool expansion hoặc shard rebalance. Ghi “config ban đầu” chưa đủ.

### 20.1. Snapshot đầu và cuối

Chụp topology, capacity, indexes, feature flags, limits tại start/end, và timeline mọi thay đổi xảy ra giữa chừng.

### 20.2. Runtime state

Ghi GC, CPU throttling, compaction backlog, cache hit rate, active connections, replication lag, disk occupancy và queue depths theo timestamp.

### 20.3. Config động

Các giới hạn capacity/pool/query timeout có thể được áp runtime. Nếu thay đổi, gắn event và phân biệt pre/post phase.

### 20.4. Không loại run bất lợi vô cớ

Nếu autoscaling làm p99 tăng, đó có thể là behavior thực của mode được chọn. Chỉ loại run theo invalidity criteria đã công bố và nói rõ lý do.

## 21. Protocol kiểm thử có thể tái lập

1. Định nghĩa access patterns, business SLO và correctness invariants.
2. Đóng băng versions và config snapshots.
3. Provision topology/hardware theo plan.
4. Seed dữ liệu với generator version, seed và distribution.
5. Kiểm dữ liệu, indexes và replica readiness.
6. Thực hiện cold/warm procedure như đã khai báo.
7. Chạy load stages, duration và concurrency nhất quán.
8. Thu raw observations, errors, retries, server/client resource telemetry.
9. Lặp runs, luân phiên run order để giảm bias.
10. Tách fault/recovery experiments nếu nằm trong scope.
11. Phân tích throughput/latency/errors/cost/uncertainty.
12. Viết conclusion cùng assumptions, unknowns và alternatives.

### 21.1. Invalid-run policy định nghĩa trước

Ví dụ: run không hợp lệ khi generator CPU saturated kéo dài quá ngưỡng đã công bố. Không đặt rule loại bỏ sau khi đã thấy phía nào kém.

### 21.2. Lưu raw artifacts

Scripts, config manifest, seed, histograms, results, logs/metrics đã loại secrets, event timelines và report commit.

### 21.3. UTC timestamps

Lưu start/end UTC và timezone/địa điểm nếu cần. “Test hôm qua” không có giá trị lưu trữ dài hạn.

### 21.4. Observations khác recommendations

Số liệu mô tả điều quan sát trong conditions; recommendation thêm đánh giá constraints, risks và business context.

## 22. Dấu vết tái lập: Experiment ID và immutable artifacts

Một experiment nên có ID ổn định:

~~~text
experimentId: nosql-orders-2026-11-14-run05
candidate: db-a
gitCommit: 1a2b3c4-placeholder
runStartUtc: 2026-11-14T07:00:00Z
reportRevision: 2
~~~

### 22.1. Artifact manifest

Mỗi report dẫn tới versioned config, workload code, sanitized dataset generator, raw metrics files và summary figures. Cần integrity digest khi báo cáo dùng cho audit/decision.

### 22.2. Không chỉ dẫn tới dashboard sống

Dashboard có thể bị xóa/retention hoặc queries đổi. Xuất raw aggregated statistics, histogram snapshots và source query definitions vào artifact storage theo policy.

### 22.3. Pin dependencies

Maven/Gradle lock/version, JDK vendor/build, Docker image digest, driver/SDK versions, YCSB plugin commit và IaC commit phải được lưu.

### 22.4. Có thể tái lập nhưng không lộ secrets

Manifest nên lưu reference tới secret policy/role, không chứa access keys, database passwords, customer payloads hay credentials trong URI.

### 22.5. Provenance

Ghi ai/CI job nào đã chạy, hạ tầng theo config version nào và timestamps. Evidence có provenance tốt giúp phân biệt run mới thật với số liệu chép từ benchmark cũ.

## 23. Manifest YAML cho một run NoSQL

Mẫu dưới đây là đề xuất **cấu trúc lưu dữ liệu thí nghiệm**, không phải format chuẩn của bất kỳ benchmark framework nào:

~~~yaml
schemaVersion: 1
experiment:
  id: nosql-orders-experiment-01
  purpose: evaluate GET/write SLO under mixed workload
  createdAtUtc: 2026-11-14T07:00:00Z
  ownerRole: platform-engineering
candidate:
  name: example-document-db
  engineVersion: 0.0-example
  edition: example
  deploymentMode: self-managed
  buildDigest: sha256-placeholder
javaClient:
  jdk: vendor-jdk-xx-example
  driverArtifact: org.example:db-driver
  driverVersion: 0.0-example
  loadGeneratorCommit: 1a2b3c4-placeholder
environment:
  provider: ExampleCloud
  region: example-region-1
  zones: 3
  nodeCount: 3
  vcpuPerNode: 8
  memoryGiBPerNode: 32
  storage:
    type: ssd-example
    iops: 6000
    capacityGiB: 800
databaseConfig:
  replicationFactor: 3
  writeAcknowledgement: majority-example
  readConsistency: example-policy
  shardingKey: tenantId/orderId
  indexesRevision: indexes-v4
  cachePolicy: warm-steady-state
  tls: enabled
dataset:
  generatorCommit: d3c0de-placeholder
  seed: 5742026
  recordCount: 30000000
  logicalSizeGiB: 200
  keyDistribution: zipfian
workload:
  definitionRef: workload-orders-v3.yml
  durationSeconds: 900
  warmupSeconds: 900
  offeredRatePerSecond: 25000
  concurrency: 256
method:
  mode: open-loop
  iterations: 5
  errorInThroughput: exclude-failures
  latencyScope: end-to-end-client
artifacts:
  resultsRef: results-run05.json
  metricsRef: metrics-run05.json
  logsRef: sanitized-logs-run05.txt
limitations:
  - Single region only
  - No cross-region failover tested
assumptionsRef: assumptions-v2.yml
~~~

### 23.1. Dùng placeholders có chủ đích

Các giá trị ExampleCloud, 0.0-example, SHA placeholder ở trên không phải thông số sản phẩm thật. Khi báo cáo chính thức, unknown phải ghi unknown chứ không giữ nguyên placeholder.

### 23.2. Schema version

Manifest có version để các tool đọc được nhiều thế hệ cấu trúc. Khi thêm fields hoặc thay cách định nghĩa metric, tăng schemaVersion và mô tả migration.

### 23.3. Configuration snapshot là ảnh tại thời điểm chạy

Không thay manifest của run cũ khi tinh chỉnh config cho run mới. Tạo immutable new run ID và liên kết thông qua experiment group.

### 23.4. Không nhầm declared với observed

nodeCount=3 trong file IaC không đảm bảo lúc chạy thực sự có ba nodes healthy. Manifest nên đi kèm observed topology/capacity metrics và drift report.

## 24. Assumptions register: mỗi giả định phải có nguồn và rủi ro

| ID | Giả định | Cơ sở | Mức tin cậy | Nếu sai sẽ ảnh hưởng gì? |
|---|---|---|---|---|
| A-01 | 80% reads, 20% writes | Logs 30 ngày | Trung bình | IO, index và chi phí |
| A-02 | Dữ liệu tăng 30%/năm | Forecast nghiệp vụ | Thấp | Storage, hot partitions |
| A-03 | Một Region là đủ | Requirement hiện tại | Trung bình | DR architecture |
| A-04 | Cache hit trên 90% | Staging simulation | Thấp | Backend QPS |
| A-05 | 99% queries dùng một index | Logs 7 ngày | Trung bình | Full scan cost |

Các hàng chỉ là ví dụ, không mô tả một ứng dụng thật.

### 24.1. ID và owner

Mỗi giả định nên có ID, owner, review date, nguồn, mức tin cậy và cách xác minh. Khi conclusion đổi, biết giả định nào cần cập nhật.

### 24.2. Nguồn khác nhau

Production observations, business forecast, tài liệu provider và ý kiến chuyên gia có độ tin cậy khác nhau; không trình bày tất cả như facts đã đo.

### 24.3. Confidence không phải số bịa

Nếu không có phân tích định lượng, ghi high/medium/low với tiêu chí hoặc unverified. Không tự tuyên bố xác suất 95% chỉ dựa trên cảm giác.

### 24.4. Giả định có thời hạn

Growth forecast một năm trước có thể không còn phù hợp sau khi mô hình kinh doanh đổi. Ghi khi nào phải review lại.

## 25. Facts, assumptions, hypotheses và unknowns

~~~text
OBSERVED: A p99 was 73 ms at 20k successful ops/s in run #5.
CONFIGURED: Write concern was set to policy X.
VERIFIED: Observed server property matched configuration X.
ASSUMED: Next-year request mix remains 80/20.
HYPOTHESIS: Hot-tenant bucketing may reduce contention.
UNKNOWN: Provider internal node placement at run time.
NOT_TESTED: Cross-region failover and long-range scans.
~~~

### 25.1. Declared không đồng nghĩa observed

IaC khai ba nodes chưa chứng minh cả ba healthy trong measurement window. Phải lấy observed topology và ghi drift nếu có.

### 25.2. Unknowns vẫn quan trọng

Managed service có thể không công bố internal build hoặc shard placement. Ghi phần không nhìn thấy, không suy đoán phiên bản.

### 25.3. Hypothesis chưa phải finding

“Compaction gây p99 spike” cần metrics đối chứng hoặc test kiểm soát. Nếu mới phỏng đoán, đánh dấu hypothesis.

### 25.4. Tương quan không luôn là nhân quả

CPU tăng cùng latency không chứng minh CPU là bottleneck nếu disk queue và contention cũng thay đổi. Phải thừa nhận giới hạn suy luận.

## 26. Sensitivity analysis: giả định đổi thì lựa chọn có đổi?

| Kịch bản | GET share | Dataset | Tình huống |
|---|---:|---:|---|
| Base | 80% | 1 TB | Forecast hiện tại |
| Read peak | 95% | 1 TB | Cache/RCU sensitive |
| Write peak | 50% | 1 TB | Index/compaction pressure |
| Growth | 80% | 4 TB | RAM misses và disk IO |
| Hot tenant | 80% | 1 TB | 1% keys nhận 70% requests |

Đây là scenarios minh họa.

### 26.1. Robust recommendation

Nếu A tốt hơn B ở nhiều scenarios và đạt constraints, mức tin cậy tăng. Nếu thứ hạng đảo khi cache hit xuống 70%, report phải nêu breakpoint.

### 26.2. Ưu tiên giả định có ảnh hưởng lớn

Những assumption dễ làm đảo quyết định (Region pricing, growth, hot tenants, write ratio) nên được đo kỹ hơn.

### 26.3. Không thể đo mọi tổ hợp

Có thể dùng sensitivity sweep/factorial design hoặc mô hình có uncertainty. Gắn nhãn estimated vs measured, không ghép lẫn.

### 26.4. Chi phí tương lai có range

Khi volume/discount/Region pricing chưa chắc chắn, đưa best/base/worst hoặc khoảng, không làm tròn đến một số quá chính xác.

## 27. MongoDB: các cấu hình cần ghi

### 27.1. Phiên bản

Exact MongoDB server build, edition/deployment, storage engine và Java driver version. Với managed service, ghi engine version được công bố, tier và Region.

### 27.2. Topology

Replica set members, shard count, config servers, mongos routing, AZ placement, chunk distribution, hashed/ranged shard key và balancer status nếu liên quan.

### 27.3. Read/write contract

readPreference, readConcern, writeConcern, journaling, retryable writes, transaction mode. Không lấy secondary eventual read so với primary strong read rồi cho là cùng semantics.

### 27.4. Indexes

Lưu compound/partial/TTL/multikey/text indexes, query explain, selectivity và index sizes. Index tồn tại không có nghĩa planner luôn dùng nó.

### 27.5. Operational state

WiredTiger cache, replica lag, index build, checkpoints, compression, storage IO, active transactions và client pool.

### 27.6. Báo một claim có điều kiện

“MongoDB cấu hình A, majority write acknowledgment, indexed point lookup, 200 GB dataset, ba AZ, warm state đạt throughput X và p99 Y trong window Z” chỉ hợp lệ khi X/Y được đo và manifest gắn kèm.

## 28. DynamoDB: ghi table, index và capacity mode

DynamoDB là managed service nên không nhất thiết quan sát được node count nội bộ.

### 28.1. Data model

Table PK/SK, GSI/LSI definitions, Query vs Scan, item-size distribution, conditional writes, transactions, TTL, streams/global tables nếu dùng.

### 28.2. Capacity

On-demand/provisioned RCU/WCU, autoscaling limits/targets, consumed capacity, throttling, burst behavior và quotas.

### 28.3. Consistency

GetItem/Query strong read nơi được hỗ trợ hoặc eventual; GSI eventual read, global table cross-Region propagation. Ghi per operation.

### 28.4. Cost

Request units, storage, GSIs, backups/PITR, streams, data transfer, mode, Region và ngày đơn giá.

### 28.5. SDK retries

AWS SDK for Java version, HTTP client, retries, max attempts, timeouts, connection pools; đo physical attempts kể cả SDK tự retry.

### 28.6. Internal version unknown

Khi provider không công bố build nội bộ, ghi managed internal version unknown, không bịa.

## 29. Cassandra/ScyllaDB: token, compaction và CL

### 29.1. Versions/topology

Exact engine version, Java driver, nodes/DC/AZ, RF, token distribution, vnode/tablet feature khi áp dụng, repair/bootstrap state.

### 29.2. Schema

Partition key, clustering order, table options, compaction strategy, compression, TTL, indexes/materialized views và partition-size distribution.

### 29.3. Consistency

Read/write CL, serial consistency/LWT nếu dùng, counter semantics và acknowledgment policy.

### 29.4. Background activity

Compaction backlog, tombstones, SSTable count, pending repairs, memtable flush và GC/cache. Dataset mới sạch tombstones không đại diện production cũ.

### 29.5. Hot partitions

Uniform keys có thể che wide partition hoặc tenant nóng; ghi key cardinality và partition sizes p50/p99.

### 29.6. Không quy đổi RF máy móc sang dịch vụ managed

Cassandra RF=3 không tự tương đương replicas ẩn của một managed table. So observable business guarantees và test failure behavior theo contract.

## 30. Redis: durability và eviction thay đổi phép đo

### 30.1. Version/deployment

Exact Redis version/edition, client library (Jedis/Lettuce/Redisson) version, standalone/sentinel/cluster mode, Redis-compatible service nếu có.

### 30.2. Persistence

RDB schedule, AOF mode/fsync policy, rewrite và replication. GET/SET QPS khi không persistence có thể khác khi business cần AOF durability.

### 30.3. Memory

maxmemory, eviction policy, fragmentation, TTL/expiration distribution, memory headroom và key-size distribution. Redis đủ RAM khác Redis liên tục eviction.

### 30.4. Client behavior

Pipelining, batching, multiplexing, serialization, compression, pool size và in-flight requests. GET pipelined không cùng latency path với GET tuần tự.

### 30.5. Workload type

GET/SET/INCR/streams/Lua/transactions/SCAN/sorted sets có costs khác; không dùng benchmark PING làm bằng chứng throughput của stream consumer groups.

### 30.6. Data authority

Redis chỉ làm cache thì mất keys có thể rebuild, nhưng authoritative counters/sessions cần backup, failover và recovery tests riêng.

## 31. Elasticsearch/OpenSearch: search semantics riêng

### 31.1. Versions

Exact distribution/version, plugins, analyzers, index mappings, lifecycle policies và Java REST client version.

### 31.2. Topology

Primary/replica shard count, shard sizes, data tiers, refresh interval, merge policy, cache và node roles.

### 31.3. Query class

Term/filter/range/full-text/vector queries, aggregations, sort, size, search_after/PIT, relevance settings và total-hit settings.

### 31.4. Freshness

Đo source-to-index lag, refresh và write visibility. Search 20 ms nhưng data trễ 30 giây chưa chắc đáp ứng OrderStatus contract.

### 31.5. Query correctness

Nếu analyzers/tokenizers khác, exact ranking có thể không phải oracle phù hợp. Cần relevance metrics/ground truth thay vì chỉ p99.

### 31.6. Indexing load

Read-only benchmark trên index tĩnh khác production vừa index vừa search. Ghi ingestion rate, merges và search p99 đồng thời.

## 32. Không so các loại việc khác nhau

MongoDB document query, Cassandra partition query, DynamoDB key access, Redis cache GET và OpenSearch full-text search không mặc nhiên giải cùng bài toán.

### 32.1. Logical business operation

“Trả top 20 products theo filter/relevance” có thể cần thêm search index cho DynamoDB. So giải pháp hoàn chỉnh, không chỉ primitive API nhanh nhất.

### 32.2. Pipeline phụ có cost

Nếu giải pháp dùng CDC→search projection, tính write amplification, lag, replay handling, storage và vận hành.

### 32.3. Hai bảng kết quả

Engine-level microbenchmark giải thích primitives; end-to-end business workload phục vụ decision. Chúng trả lời câu hỏi khác nhau.

### 32.4. Không hỗ trợ cũng là thông tin

Nếu candidate không cung cấp query contract trong constraints, ghi NOT_SUPPORTED/REQUIRES_REDESIGN, không chế tạo QPS bằng 0.

## 33. Ví dụ so sánh không công bằng

~~~text
System A: 3 nodes, 16 vCPU each, all keys in RAM, async ACK.
System B: 3 nodes, 8 vCPU each, disk bound, quorum ACK.
A workload: 100% GET.
B workload: 70% GET / 30% writes.
A run: after warmup.
B run: during index build.
A result: 50k QPS.
B result: 20k QPS.
~~~

### 33.1. Số đo không sai nhưng suy luận sai

Kết quả có thể chính xác dưới hai điều kiện đó, song không cô lập được engine, hardware, workload, durability hoặc background tasks.

### 33.2. Hai hướng so sánh

- **Controlled comparison:** chuẩn hóa các yếu tố có ý nghĩa, đánh dấu khác biệt không thể chuẩn hóa.
- **Solution comparison:** cấu hình mỗi giải pháp để đạt cùng business SLO rồi so cost/reliability/operations; không cần ép số nodes giống nhau giữa các managed models.

### 33.3. Không có winner tuyệt đối

A thắng point-read latency, B có thể thắng durability hoặc managed operations. Báo nhiều dimensions thay vì ép thứ hạng tổng thiếu cơ sở.

## 34. Fairness: cùng tiêu chí, không nhất thiết cùng internals

### 34.1. Functional equivalence

Truy vấn trả cùng fields, filter, sort, pagination, tenant scope và freshness/consistency theo business contract.

### 34.2. Operational equivalence

Khi so solution, các ứng viên đều phải xét HA, backup, encryption, audit, recovery và availability goals.

### 34.3. Resource equivalence

Có thể so tại cùng cost budget, cùng instance class hoặc cùng target SLO; mỗi phương án trả lời câu hỏi khác.

### 34.4. Tuning effort

A được chuyên gia tuning một tuần, B dùng defaults: có bias. Ghi tuning window, allowed changes và owner.

### 34.5. Evaluation plan trước khi xem số

Nếu workload đổi sau khi nhìn results của một ứng viên, tăng protocol revision và thử lại các candidates liên quan.

### 34.6. Vendor benchmark

Benchmark từ vendor có thể tối ưu cho thế mạnh sản phẩm. Dùng làm tham khảo nhưng kiểm tra bằng workload/constraints của mình.

## 35. Báo kết quả đa chiều thay cho xếp hạng một dòng

| Dimension | Candidate A | Candidate B | Evidence |
|---|---|---|---|
| Point GET p99 at target load | 65 ms | 73 ms | Histogram/run IDs |
| Range query p99 | 210 ms | 150 ms | Query contract Q2 |
| Write error rate | 0,02% | 0,03% | Outcome counters |
| Data freshness | Within 2s | Within 1s | Watermark experiment |
| Estimated monthly cost | 10.000 đơn vị | 9.000 đơn vị | Price model dated |
| Recovery | Drill thực hiện | Chưa thử | Restore evidence |
| Operations | Self-managed | Managed | Staffing assumptions |

**Toàn bộ số liệu là ví dụ giả định**, không đại diện sản phẩm nào.

### 35.1. Số đo, estimate và assessment

p99 là observation; cost tương lai là estimate; “vận hành dễ hơn” có thể là qualitative assessment. Đặt evidence level riêng để người đọc không nhầm.

### 35.2. Hard constraints không phải điểm cộng/trừ

Data residency, encryption, RPO/RTO hoặc tenant isolation là yêu cầu bắt buộc. Điểm throughput cao không bù được vi phạm điều kiện loại.

### 35.3. Weighted scoring phải được duyệt trước

Điểm tổng có thể giúp ra quyết định nếu weights được stakeholder chấp nhận và công thức minh bạch. Không sửa weights sau khi biết sản phẩm nào thắng.

### 35.4. UNKNOWN khác zero

Chưa thử recovery không có nghĩa không hỗ trợ, nhưng cũng không được đánh dấu đạt. Ghi NOT_TESTED và risk/action.

## 36. Báo độ bất định chứ không chỉ trung bình

~~~text
A p99 across five runs: 65, 67, 70, 66, 68 ms
B p99 across five runs: 70, 73, 71, 75, 74 ms
~~~

Report nên có median p99 qua runs, min/max hoặc scatter, số samples mỗi run và variation. Nếu tính confidence intervals, giải thích phương pháp và assumptions.

### 36.1. Requests có tương quan

Một triệu requests trên cùng hot key không tương đương một triệu independent random samples. Tránh đưa ra confidence interval quá hẹp dựa trên giả định sai.

### 36.2. Cùng target load

Không đặt A p99 ở 50k QPS cạnh B p99 ở 10k QPS như hai phép thử tương đương mà không ghi rõ.

### 36.3. Không gắn p-value nếu chưa tính

Nếu chưa có statistical test thích hợp, nói “observed difference” và “run variation”, không tuyên bố statistically significant.

### 36.4. Ý nghĩa kinh doanh

A nhanh hơn 3% nhưng cần gấp đôi chi phí vận hành chưa chắc là lựa chọn tốt nếu cả hai đã đạt SLO.

## 37. Limitations phải được liệt kê cụ thể

- Chưa thử dataset lớn hơn RAM.
- Chưa đo cross-region latency.
- Chưa thử AZ/Region failover.
- B chưa được index tuning bằng A.
- Synthetic data thiếu legacy fields.
- Chưa đo batch writes/high-cardinality aggregates.
- Chưa bật production audit logging.
- Price model chưa gồm support/egress.
- Không đủ runs đo p99.9 ổn định.
- Chưa thấy extreme hot-tenant skew.

### 37.1. Limitations giúp dùng report đúng

Một báo cáo scoped vẫn rất hữu ích nếu người đọc biết phần nào đã chứng minh và phần nào còn rủi ro.

### 37.2. Không gọi “ổn định tuyệt đối”

“Không quan sát lỗi trong 5 runs, mỗi run 15 phút thuộc workload Q1” là chính xác hơn tuyên bố hệ không bao giờ lỗi.

### 37.3. Thiếu bằng chứng về điểm quyết định

Nếu kiến trúc phụ thuộc hot-tenant performance nhưng test chưa có hot tenants, đây có thể là blocker trước khi chọn, không chỉ câu ghi chú.

## 38. Định dạng báo cáo so sánh có thể tái sử dụng

Một báo cáo ngắn nhưng đầy đủ nên có các phần:

1. **Câu hỏi quyết định:** lựa chọn giải pháp để giải bài toán gì?
2. **Business constraints:** access patterns, SLO, durability, RPO/RTO, residency.
3. **Candidates và versions:** engine, managed service, driver, JDK, toolchain.
4. **Environment/topology:** CPU/RAM/disk/network/Region/zones/placement.
5. **Database configuration:** indexes, schema, consistency, replication, capacity, cache.
6. **Dataset:** records, bytes, skew, field distributions, seed/generator.
7. **Workload protocol:** operation mix, offered load, clients, duration, warmup.
8. **Observed results:** multiple runs, latency percentiles, successes/errors, resource metrics.
9. **Cost/reliability/security:** measured or estimated with provenance.
10. **Assumptions và unknowns:** source, confidence, review date.
11. **Limits/sensitivity:** untested scenarios và khi nào thứ hạng đảo.
12. **Conclusion/decision record:** recommendation, conditions, owners, next validation.

### 38.1. Executive summary không tự đứng một mình

Tóm tắt nên link tới evidence và điều kiện; không đổi một kết quả scoped thành tagline tuyệt đối.

### 38.2. Trình tự đọc

Đặt business question và constraints trước bảng hiệu năng để người đọc hiểu điều gì là bắt buộc.

### 38.3. Phụ lục kỹ thuật

Các cấu hình dài, histogram exports và manifest có thể nằm trong appendix/artifact store, miễn là report dẫn rõ path/version và giữ quyền truy cập.

## 39. Ví dụ đoạn executive summary có điều kiện

> Trong workload 55% point GET, 20% tenant-time list, 23% writes/updates và 2% deletes, trên dataset synthetic 200 GiB, Candidate A đáp ứng mục tiêu p99 và error rate tại tải mục tiêu, còn Candidate B có chi phí ước lượng thấp hơn. Tuy nhiên phép đo chưa bao gồm failover đa Region và độ lệch tenant thực tế. Đề xuất chạy thêm hai thí nghiệm còn thiếu trước quyết định cuối.

### 39.1. Tránh từ tuyệt đối

Thay “A có hiệu năng tốt nhất” bằng “A đạt p99 thấp hơn trong workload W ở tải Y và hai cấu hình được mô tả”.

### 39.2. Không nhầm threshold đạt SLO với sản phẩm tốt nhất

Hai hệ đều đáp ứng latency SLO có thể phân biệt qua cost, support, recovery và developer effort.

### 39.3. Nêu recommendation status

Provisional, recommended with conditions, rejected due to hard constraint, hoặc insufficient evidence. Một report trung thực không nhất thiết có winner ngay.

## 40. Decision record: lưu tại sao chọn, không chỉ chọn gì

~~~yaml
decision:
  id: ADR-DB-042
  status: proposed
  date: 2026-11-14
  question: choose NoSQL storage for Orders read/write workload
  options:
    - Candidate A, configuration A-3
    - Candidate B, configuration B-2
  recommendation: Candidate A, conditional
  reasons:
    - Meets target point-read latency at tested peak load
    - Query contract coverage is higher for current application
  constraints:
    - Tenant isolation verified
    - Backup RPO/RTO must be validated separately
  assumptions:
    - A-01
    - A-02
  outstandingEvidence:
    - Hot-tenant load test
    - Cross-region recovery drill
  rollbackCriteria:
    - New model violates data correctness invariant
  benchmarkRefs:
    - experiment-orders-group-01
  owners:
    - platform-tech-lead
    - product-owner
~~~

Đây là mẫu minh họa. “Recommendation: Candidate A” không nói đã chọn thật; status proposed thể hiện quyết định chưa phê duyệt.

### 40.1. ADR là tài liệu sống có revision

Khi đổi constraint hoặc engine version, tạo revision/superseding ADR theo quy trình, không âm thầm ghi đè evidence cũ.

### 40.2. Ghi alternative đã bị loại

Nếu một ứng viên không hỗ trợ range query trong ngân sách được phép, nêu lý do rõ, không chỉ bỏ nó khỏi kết quả.

### 40.3. Ghi những điều kiện đảo quyết định

Ví dụ nếu actual cache hit dưới 70% hoặc traffic tăng gấp bốn, cần chạy lại các kịch bản và xem lại lựa chọn.

## 41. Java: ghi runtime metadata an toàn

Một chương trình Java 17+ có thể thu metadata JDK không nhạy cảm:

~~~java
import java.time.Instant;
import java.util.Map;
import java.util.TreeMap;

public final class BenchmarkRuntimeSnapshot {
    public static Map<String, String> capture(String runId) {
        Map<String, String> info = new TreeMap<>();
        info.put("runId", runId);
        info.put("recordedAtUtc", Instant.now().toString());
        info.put("javaVersion", System.getProperty("java.version"));
        info.put("javaVendor", System.getProperty("java.vendor"));
        info.put("runtimeVersion", System.getProperty("java.runtime.version"));
        info.put("vmName", System.getProperty("java.vm.name"));
        info.put("osName", System.getProperty("os.name"));
        info.put("osArch", System.getProperty("os.arch"));
        info.put("availableProcessors",
                 String.valueOf(Runtime.getRuntime().availableProcessors()));
        return Map.copyOf(info);
    }
}
~~~

### 41.1. Không dump toàn bộ system properties

Một số system properties/environment variables chứa API tokens, proxy passwords, DB URIs có credentials hoặc secrets. Dùng **allowlist** fields đã duyệt.

### 41.2. System.getProperty chỉ cho runtime view

availableProcessors phản ánh JVM/container effective view, không là toàn bộ CPU quota/host topology. Thu node/container resource metrics ở infrastructure side.

### 41.3. Driver metadata riêng

JDK properties không cung cấp exact MongoDB/AWS SDK/Cassandra driver versions đáng tin. Lấy từ dependency lock/build manifests hoặc client/library metadata phù hợp và gắn vào artifact.

### 41.4. Runtime flags

Heap/GC JVM flags ảnh hưởng benchmark; ghi flags đã whitelist/sanitize, không in toàn bộ command line nếu có secrets.

## 42. Java: tạo fingerprint cho cấu hình đã được cho phép

Một benchmark harness có thể chuẩn hóa các trường cấu hình **không nhạy cảm** rồi tính digest để nhận biết khi hai runs dùng config khác nhau.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Map;
import java.util.TreeMap;

public final class ConfigFingerprint {
    public static String sha256(Map<String, String> safeConfig) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            TreeMap<String, String> ordered = new TreeMap<>(safeConfig);
            for (Map.Entry<String, String> entry : ordered.entrySet()) {
                byte[] key = entry.getKey().getBytes(StandardCharsets.UTF_8);
                byte[] value = entry.getValue().getBytes(StandardCharsets.UTF_8);
                digest.update(intToBytes(key.length));
                digest.update(key);
                digest.update(intToBytes(value.length));
                digest.update(value);
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }

    private static byte[] intToBytes(int n) {
        return new byte[] {
                (byte) (n >>> 24), (byte) (n >>> 16),
                (byte) (n >>> 8), (byte) n
        };
    }
}
~~~

### 42.1. Dùng explicit safeConfig

Ví dụ safeConfig chỉ gồm engineVersion, readConcern, writeConcern, shardCount, region, queryContractVersion và driverVersion. Không truyền toàn bộ environment variables hoặc raw URI/credentials.

### 42.2. Fingerprint không thay manifest

Hai configs có digest khác cho biết có khác biệt, nhưng digest không mô tả khác ở đâu. Phải giữ cấu hình được phép trong artifact manifest.

### 42.3. Config hash không phải chữ ký bảo mật

SHA-256 checksum không chứng minh ai đã tạo file và có bị attacker thay cả file/digest hay không. Nếu yêu cầu audit chống sửa, dùng artifact signing, IAM và provenance chain phù hợp.

### 42.4. Quan tâm canonicalization

Lưu thứ tự trường ổn định, encoding rõ và độ dài key/value để tránh ambiguity. Không hash raw JSON với order không ổn định rồi báo configs khác nhau giả.

## 43. Ghi lại database config từ nguồn có thẩm quyền

Với mỗi config, ghi ba giá trị khi có:

~~~text
DECLARED: value in IaC / application config
OBSERVED: value returned by database/management APIs
EFFECTIVE: value applied to the specific operation
~~~

### 43.1. “Effective” có thể khác default

Client có thể override timeout/read preference/consistency theo request; database defaults không phản ánh operations đã benchmark.

### 43.2. Không đọc secret chỉ để chứng minh config

Config extractor nên lấy tên/mode/policy reference, không lấy raw access tokens, password, KMS material. Dùng role chỉ có quyền đọc metadata cần thiết.

### 43.3. Gắn nguồn và thời gian

Ghi API/query/provenance (sanitized) và capturedAtUtc. Console screenshot một ngày khác không chứng minh setting đúng trong measurement window.

### 43.4. Drift detection

So IaC manifest với server observed configuration theo fields quan trọng. Nếu khác, report drift và quyết định experiment invalid hay một observed scenario mới.

## 44. Phiên bản benchmark report cũng cần version

Một report có nhiều vòng:

~~~text
Experiment group: orders-db-eval-2026
Run group v1: baseline query mix
Run group v2: corrected tenant skew
Report rev 1: preliminary
Report rev 2: cost model updated
Decision ADR rev 1: conditional
~~~

### 44.1. Đổi workload thì phải đổi version

Một báo cáo rev 2 không được thay đổi 80/20 thành 60/40 nhưng giữ nguyên các số p99 của rev 1 như thể cùng thử nghiệm.

### 44.2. Đổi cách tính metric cũng phải có revision

Nếu rev 1 tính QPS từ physical SDK calls, rev 2 tính logical operations, không được đặt hai con số cạnh nhau thiếu chú thích.

### 44.3. Source-of-truth của report

Giữ một manifest/experiment catalog mà mỗi run ID dẫn tới đúng versions/config/results. Tránh copy bảng Excel/Markdown mà không có provenance.

### 44.4. Chú thích sửa lỗi

Nếu phát hiện latency histogram từng bị tính sai do coordinated omission, phát hành correction/retraction, không âm thầm ghi đè cả kết luận cũ.

## 45. Các biến nhiễu cần loại hoặc đưa vào phân tích

| Biến nhiễu | Tác động có thể xảy ra | Cách xử lý |
|---|---|---|
| Noisy neighbor cloud | CPU/network tranh chấp | Lặp runs, theo dõi steal/throttle |
| Data chưa index xong | Query chậm bất thường | Ghi index state, đo đúng scenario |
| Autoscale trễ | Tail latency spike | Log autoscale events |
| Cold client pool | Connection setup overhead | Warmup hoặc đo cold scenario riêng |
| Cache khác tỷ lệ hit | Một bên đọc RAM nhiều hơn | Ghi cache hit/miss |
| Load generator nghẽn | Không đạt offered load | Theo dõi client CPU/network |
| Retry policy khác | Tăng calls và che errors | Báo logical/physical attempts |
| Replica lag | Read trả stale | Báo freshness/consistency |
| Compaction hoặc repair | IO latency spike | Ghi background tasks |
| Cross-AZ networking | RTT khác | Placement/latency budget |
| TLS disabled ở một bên | Chênh chi phí crypto | Ghi security mode |
| Data size khác | Caching và selectivity khác | Giữ data profile tương đương |

### 45.1. Biến nhiễu không tự bị loại bởi phép đo dài

Một run dài có thể trải qua nhiều đợt autoscaling/compaction; cần timeline thay vì giả định mọi nhiễu được trung bình hóa.

### 45.2. Khi nhiễu là hiện thực production

Nếu production thường có index refresh hoặc repair, không nên loại khỏi tất cả thí nghiệm. Có thể phân biệt baseline và realistic operations run.

### 45.3. Bằng chứng khi loại run

Nếu loại run do generator CPU bottleneck, ghi run ID, tiêu chí đã định và evidence; không xóa artifacts.

## 46. Báo failure tests và durability assumptions

Một bài đánh giá không chỉ có performance. Nếu cần lựa chọn hệ chịu lỗi, bổ sung kịch bản có kiểm soát:

~~~text
F1: kill one database node during 80% GET / 20% write load
F2: disconnect one AZ temporarily
F3: introduce 100ms inter-region latency
F4: restart client and replay ambiguous write outcomes
F5: restore from backup into isolated environment
~~~

### 46.1. Ghi điều kiện trước khi fault

Node health, replication lag, cluster topology, quorum settings và outstanding writes tại thời điểm fault.

### 46.2. Ghi timeline

Fault injection start, first errors, failover/recovery, catch-up, cutover và recovery complete theo UTC.

### 46.3. Không khẳng định “zero data loss” không có oracle

Theo dõi acknowledged logical writes và verify sau recovery theo consistency/transaction semantics; đừng chỉ nhìn API health.

### 46.4. RPO/RTO theo business operation

Database khởi động nhưng indexes hoặc API chưa phục vụ đúng chưa thể coi business recovered.

### 46.5. Test scope và safety

Fault injection chỉ trên môi trường được duyệt, với stop conditions và owner. Không thực hiện destructive tests trên production ngoài quy trình đã phê duyệt.

## 47. Cost per successful business operation

Giả sử hai configs phục vụ cùng 100 triệu successful operations/tháng:

\[
\mathrm{CostPerMillionSuccessfulOps}
=\frac{\mathrm{MonthlyCost}}{\mathrm{SuccessfulOps}/10^6}.
\]

### 47.1. Lựa chọn mẫu số

Không chia bằng tổng attempted SDK requests nếu một logic operation cần 5 calls hoặc có retry. Dùng successful business operations khi muốn so giá trị cung cấp.

### 47.2. Cost gắn workload

Cost per million operations không có ý nghĩa chung khi operations khác size, query complexity hoặc Region. Gắn nó với workload/version và rate assumptions.

### 47.3. Chi phí có phần cố định

Một reserved cluster có chi phí cố định dù QPS thấp; cost per operation giảm theo utilization. So ở cả expected load và peak.

### 47.4. Cost không nên đổi correctness

Một giải pháp rẻ nhưng không đạt read freshness, durability hoặc tenant isolation là không phù hợp; không dùng chi phí bù hard constraints.

## 48. Không nhầm giá niêm yết với hóa đơn thực

### 48.1. Price snapshot

Ghi nguồn price page/calculator, Region, ngày truy cập và currency. Báo cáo dùng giá hôm nay không nên coi đúng mãi khi cloud pricing thay đổi.

### 48.2. Discounts

Reserved/savings-plan/enterprise discounts có thể riêng tổ chức. Nếu chưa biết, tạo scenario public list price và discounted estimate, không giả một giá chắc chắn.

### 48.3. Egress

Cross-AZ/cross-Region và client traffic costs có thể ảnh hưởng so sánh; nêu có bao gồm hay không.

### 48.4. Backup/PITR

Retention 30 ngày, snapshots và recovery drills có thể thêm storage/data transfer. Không chỉ lấy giá “active data”.

### 48.5. Human operations

On-call, security patching, upgrades và incident recovery có uncertainty lớn nhưng không phải miễn phí.

## 49. Một mẫu bảng kết luận có nguồn chứng cứ

| Claim | Observation | Evidence ref | Assumption | Limitation |
|---|---|---|---|---|
| A đáp ứng p99 mục tiêu | p99 ở target load | run-group-A | Workload W1 representative | Không test peak holiday |
| B chi phí thấp hơn ở base scenario | Cost estimate model v2 | pricing-snapshot-P | Dataset grows 30%/year | Discounts unknown |
| A có operations overhead cao | Self-managed duties listed | ops-assessment-O | Team staffing unchanged | Chưa đo person-hours |
| B hỗ trợ query Q3 theo contract | Integration test outcomes | contract-Q3 | Index mode retained | Không test very large tenants |

### 49.1. Claim-level traceability

Mỗi claim quan trọng dẫn được tới result/artifact hoặc analysis, không chỉ một bảng tổng.

### 49.2. Assumption reference

Gắn A-01/A-02 từ assumptions register để có thể làm impact analysis khi thay đổi forecast.

### 49.3. Không có evidence thì đừng diễn đạt như fact

Nếu chưa test long-term storage, nói “expected based on documentation/model”, không “đã đo thực tế”.

## 50. Checklist trước khi phát hành báo cáo so sánh

### 50.1. Identification

- [ ] Có experiment ID, report revision, UTC run timestamps và owner.
- [ ] Đã pin exact engine/managed API versions, Java runtime, SDK/driver, benchmark generator.
- [ ] Có config/IaC revision và image digest.

### 50.2. Environment/config

- [ ] Node class/capacity/Region/zones/network được ghi.
- [ ] Replication, consistency, durability, index, partition, TTL, cache được mô tả.
- [ ] Client retries/timeouts/pools và load generator constraints được ghi.
- [ ] Observed configs/drift và background activity được ghi.

### 50.3. Dataset/workload

- [ ] Schema/query contract, records/bytes/distribution/seed được ghi.
- [ ] GET/write mix, payload size, hot keys, tenants và page limits đại diện mục tiêu.
- [ ] Cold/warm, open/closed loop, offered-load stages và duration được mô tả.

### 50.4. Measurement

- [ ] Có counts thành công/lỗi/timeout/retry theo logical operation.
- [ ] Có latency p50/p95/p99/p99.9 (nếu đủ mẫu), achieved throughput và saturation.
- [ ] Có client/server CPU, IO, cache, memory, capacity throttles và metrics nguồn.
- [ ] Có nhiều runs và cỡ mẫu, thống kê uncertainty phù hợp.

### 50.5. Conclusions

- [ ] So cùng functional/operational contract hoặc nêu khác biệt rõ.
- [ ] Đã phân loại measured/configured/assumed/unknown/not tested.
- [ ] Có price snapshot, sensitivity assumptions và limitations.
- [ ] Có evidence links, hard constraints, decision owner và next steps.
- [ ] Không có credentials/PII trong artifacts/logs.

Đây là checklist dành cho **người lập báo cáo benchmark**, không phải bước đánh giá nội dung của chính bài học này.

## 51. Bài tập 1 — đọc một tuyên bố benchmark thiếu bối cảnh

Một slide ghi: “NoSQL A nhanh hơn NoSQL B 2,5 lần, nên chọn A.”

1. Liệt kê tối thiểu 12 câu hỏi cần trả lời trước khi chấp nhận claim.
2. Phân nhóm câu hỏi theo version, configuration, dataset, workload, measurement, assumptions.
3. Thế nào là phép so cùng một logical business operation?
4. Nếu một bên dùng ACK yếu hơn, có được nói “A nhanh hơn trong cùng durability contract” không?
5. Viết lại claim thành một câu có điều kiện và không overclaim.
6. Những evidence nào cần đính kèm cho kiến nghị quyết định?

## 52. Bài tập 2 — lập inventory phiên bản Java/NoSQL

Một nhóm dùng Java 21, MongoDB Java driver, Cassandra Java driver, AWS SDK và YCSB, nhưng report chỉ ghi “Java mới, database ổn định”.

1. Tạo bảng inventory từng component và exact version/commit.
2. Giải thích vì sao driver retry/pool version có thể ảnh hưởng QPS.
3. Nêu cách pin container image digest và dependency versions.
4. Khi cluster đang rolling upgrade, cần ghi những thông tin nào?
5. Nếu provider không lộ internal engine build, nên báo thế nào?
6. Thử thay đổi một driver minor version và lập kế hoạch A/B runs tránh confounders.

## 53. Bài tập 3 — cấu hình consistency không tương đương

Ứng viên A dùng acknowledged write ở một replica; B dùng majority/quorum durability.

1. Cấu hình nào cần ghi trước khi so latency?
2. Vì sao kết quả QPS chênh lệch không tự chứng minh engine A tối ưu hơn?
3. Thiết kế business durability target độc lập với tên config.
4. Có thể tạo một phép so cùng durability objective như thế nào?
5. Nếu không thể normalize, cần nêu caveat gì?
6. Đề xuất fault test kiểm outcome sau node failure.

## 54. Bài tập 4 — dataset vừa cache của một ứng viên

Dataset 100 GB; ứng viên A có 128 GiB RAM/node, B có 32 GiB RAM/node. Report chỉ ghi 10 triệu records.

1. Tại sao record count không đủ?
2. Cần lưu physical size/index size, cache hit ratio và hot-key distribution thế nào?
3. Đề xuất cold/warm scenarios.
4. Dataset tăng lên 2 TB sẽ thay đổi khả năng suy luận ra sao?
5. Nếu muốn so cùng cost budget, cấu hình hai bên cần được chọn thế nào?
6. Viết một limitation không thiên vị ứng viên nào.

## 55. Bài tập 5 — workload skew theo tenant

80% requests đến 2% tenants; trong đó một tenant có partition rất rộng.

1. Vì sao uniform random benchmark có thể đánh giá sai?
2. Thiết kế generator theo Zipfian hoặc empirical distribution.
3. Ghi size distribution per tenant và hot-key concentration.
4. Chọn metrics nào cho p99 per tenant tier/hot bucket?
5. Đề xuất sensitivity test khi hot tenant tăng gấp bốn traffic.
6. Nếu một hệ dùng bucketing còn hệ kia dùng fan-out, làm sao so business query cost công bằng?

## 56. Bài tập 6 — load generator làm nghẽn phép thử

Bộ phát tải có 4 vCPU, sử dụng 100% CPU khi đạt 15.000 requests/giây; database CPU chỉ 20%.

1. Có thể kết luận database capacity tối đa là 15k QPS không?
2. Ghi metrics client/generator nào?
3. Đặt invalid-run criterion trước thế nào?
4. Khi scale bộ phát tải, điều gì phải giữ nguyên?
5. Open-loop khác closed-loop thế nào khi server chậm?
6. Giải thích coordinated omission và cách phát hiện.

## 57. Bài tập 7 — p99 nhưng giấu timeout

Ứng viên A báo p99=40 ms trên requests thành công, nhưng 5% requests timeout ở deadline 2 giây; B báo p99=90 ms với 0,01% timeout.

1. Chỉ nhìn p99 thì chọn ứng viên nào, và vì sao không đủ?
2. Nên báo error/timeout rates riêng hay trộn tất cả vào latency?
3. Định nghĩa achieved successful throughput và offered load.
4. Với SLO p99 dưới 100 ms và error rate dưới 0,1%, cấu hình nào đạt?
5. Nếu SDK retry timeout ba lần, logical vs physical latency thay đổi thế nào?
6. Viết đoạn kết luận đúng phạm vi.

## 58. Bài tập 8 — multiple runs và khoảng tin cậy

Năm lần chạy p99:

~~~text
A: 65, 68, 64, 70, 66 ms
B: 72, 69, 73, 71, 74 ms
~~~

1. Tính median/min/max p99 qua runs của mỗi bên.
2. Vì sao không chỉ chọn 64 ms từ A?
3. Có được lấy trung bình p99 của từng phút làm p99 chung không?
4. Nếu một triệu requests cùng hot key, assumptions về độc lập của samples có thể sai thế nào?
5. Lập phương án bootstrap theo run/block khi có tương quan.
6. Sự khác biệt này có tự đáng giá migration hay cần business cost/risk assessment?

## 59. Bài tập 9 — MongoDB version và index plan

Hai cụm MongoDB cùng tên engine, nhưng một cụm có compound index và đọc primary, cụm kia chỉ có single-field index và đọc secondary.

1. Những fields nào phải xuất hiện trong manifest?
2. Explain/query plan và selectivity hỗ trợ diễn giải ra sao?
3. Read preference/concern ảnh hưởng freshness/latency thế nào?
4. Nếu replica lag 10 giây, có được nói một kết quả “nhanh hơn” tương đương business requirement không?
5. Đề xuất cùng query contract và indexes tương ứng để so.
6. Ghi topology và balancing/compaction state như thế nào?

## 60. Bài tập 10 — DynamoDB capacity mode và pricing

Một ứng viên dùng DynamoDB on-demand, ứng viên khác dùng provisioned capacity với autoscaling. QPS có spikes theo giờ.

1. Ghi tất cả capacity mode/limits và consumed/throttled units.
2. Vì sao không so một con số cost ở traffic thấp mà suy ra cost ở peak?
3. GSI read eventual semantics có thể thay fairness khi so GetItem strong thế nào?
4. SDK retry policy làm physical requests và billing khác ra sao?
5. Thiết kế cost sensitivity khi requests tăng 3 lần.
6. Nếu không biết internal server build, làm sao vẫn báo kết quả reproducible?

## 61. Bài tập 11 — Cassandra/ScyllaDB với compaction backlog

Ứng viên A là Cassandra có bảng đã chạy 30 ngày với nhiều tombstones; ứng viên B là ScyllaDB vừa được seed lại với dữ liệu sạch. Cả hai chạy cùng QPS.

1. Vì sao trạng thái dữ liệu không tương đương?
2. Ghi engine versions, CL, RF, partitioner, compaction strategy và SSTable count.
3. Đề xuất một phép so clean baseline và một production-like run.
4. Làm sao đánh giá wide partitions và hot tenants?
5. Ghi repair/compaction timeline để diễn giải tail latency.
6. Nếu hai engines có tính năng khác nhau, giải thích guarantee differences như thế nào?

## 62. Bài tập 12 — Redis không persistence so với AOF

Nhóm benchmark Redis A không persistence, Redis B bật AOF với fsync theo yêu cầu nghiệp vụ.

1. Cần ghi exact persistence settings nào?
2. Kết quả write latency so như vậy có công bằng về durability không?
3. Thử failover/restart để xác định mất dữ liệu thực nghiệm thế nào?
4. Client pipelining làm throughput cao nhưng latency interpretation thay đổi ra sao?
5. Nếu dataset gần maxmemory và eviction xảy ra, metric nào cần báo?
6. Viết executive summary nói rõ giới hạn của hai cấu hình.

## 63. Bài tập 13 — Search index mới có analyzer khác

OpenSearch index B dùng synonyms mới, Elasticsearch index A dùng tokenizer cũ. Kết quả top-K không giống nhau nhưng B p99 thấp hơn.

1. Có hợp lý so raw p99 mà không so result quality không?
2. Ghi mappings, analyzers, plugins, refresh interval, shard count và index versions.
3. Nên dùng recall@K, precision@K, NDCG hoặc ground-truth labels khi nào?
4. Nếu B chưa index hết source events, phải báo freshness ra sao?
5. Search đồng thời indexing khác read-only search test thế nào?
6. Nếu candidate cần CDC pipeline riêng, tính những costs nào?

## 64. Bài tập 14 — manifest chưa đủ thông tin

Một file ghi:

~~~yaml
database: nosql
nodes: 3
threads: 100
qps: 50000
latency: 12
~~~

1. Liệt kê trường còn thiếu về version và environment.
2. latency=12 là đơn vị, percentile nào và đo tại đâu?
3. qps=50000 là attempts hay successful logical operations?
4. Nodes:3 thiếu những gì về CPU, RAM, disk và placement?
5. Bổ sung dataset/workload/seed/consistency như thế nào?
6. Viết manifest có schemaVersion và artifactRefs.
7. Làm sao tránh ghi secrets trong manifest?

## 65. Bài tập 15 — cấu hình bị đổi trong lúc chạy

Run 30 phút: phút 12 autoscaler tăng từ 2 lên 6 nodes, phút 20 index build hoàn tất.

1. Có thể báo “cấu hình 2 nodes đạt 50k QPS” không?
2. Cần ghi event timeline và observed node count theo thời gian.
3. Nên chia analysis thành phases nào?
4. Autoscale latency spike thuộc scenario thật hay invalid run?
5. Nếu IaC ghi 2 nodes nhưng observed lúc bắt đầu là 3, dùng giá trị nào?
6. Đề xuất rule trước test cho trường hợp config drift.

## 66. Bài tập 16 — chi phí với giả định thay đổi

Report dùng 80/20 GET/write, dataset 1 TB, cache hit 95% và một Region. Business dự kiến write share 45%, dataset 4 TB sau 18 tháng.

1. Những giả định nào bị thay đổi?
2. Cost model cần thêm indexes, backup, egress, capacity ở mức nào?
3. Chạy sensitivity scenarios nào để thấy rank reversal?
4. Nếu một candidate self-managed, mô tả on-call/upgrade cost thế nào?
5. Vì sao cost per million successful operations phải gắn workload?
6. Viết recommendation with conditions và một kế hoạch đo tiếp.

## 67. Bài tập 17 — confidence nhưng chỉ một lần chạy

Một benchmark có một run 3 phút, 100.000 requests và zero observed errors. Team kết luận “99,9999% reliability”.

1. Vì sao claim không được suy ra như vậy?
2. Error budget/SLO và độ tin cậy thống kê khác nhau thế nào?
3. Cần thêm runs, duration và failure scenarios nào?
4. Nếu data points tương quan theo hot keys, effective sample size thay đổi thế nào?
5. Viết câu mô tả zero observed errors mà không overclaim.
6. Tách steady-state error rate khỏi durability khi node failover.

## 68. Bài tập 18 — truy vết từng claim tới evidence

Report khuyến nghị B vì “rẻ hơn, ổn định hơn, query linh hoạt hơn”, nhưng chỉ có một bảng QPS.

1. Chuyển ba nhận định thành claims có thể kiểm chứng.
2. Mỗi claim cần metric/test/artifact nào?
3. Phân biệt measured cost và estimated future pricing.
4. Định nghĩa “ổn định hơn” bằng SLO, variance, error rate hoặc failover metric.
5. “Query linh hoạt” cần query corpus/contracts và coverage ra sao?
6. Tạo ma trận claim–evidence–assumption–limitation.
7. Claims không đủ evidence cần status gì?

## 69. Bài tập 19 — review báo cáo của người khác

Bạn nhận report có kết quả chi tiết nhưng không đính kèm config digest, driver version hoặc raw histograms.

1. Soạn danh sách 10 câu hỏi reviewer phải gửi.
2. Nếu chỉ có dashboard screenshot, xác minh được gì và không được gì?
3. Yêu cầu immutable artifacts thế nào mà không lộ credentials?
4. Nếu managed provider internal version unknown, vẫn kiểm end-to-end outcome ra sao?
5. Đề xuất report revision tiếp theo và danh sách gaps.
6. Khi nào report đủ cho prototype nhưng chưa đủ production cutover?
7. Nếu tác giả chỉ chọn best-of-ten runs, ghi nhận selection bias nào?

## 70. Bài tập 20 — thiết kế báo cáo lựa chọn NoSQL hoàn chỉnh

Một SaaS nhiều tenants cân nhắc document DB, wide-column DB và managed key-value DB. Ứng dụng Java có:

~~~text
GetOrderById:            55%
ListOrdersByTenantTime:  20%
CreateOrder:             15%
UpdateOrderStatus:        8%
DeleteExpiredOrder:       2%

Peak logical load:   25,000 operations/s
Data now:            200 GiB
Business need:       No cross-tenant leakage
Required RPO/RTO:    To be supplied by owners
~~~

Hãy tạo một báo cáo thực nghiệm:

1. Viết mục tiêu quyết định, business queries và correctness contracts.
2. Đặt hard constraints về tenant isolation, durability, RPO/RTO và data residency.
3. Lập exact version inventory cho engine, JDK, drivers, OS, images và benchmark tools.
4. Lập topology/config table cho từng candidate, gồm consistency và indexes.
5. Sinh synthetic dataset với stable seed, tenant skew và value-size distribution.
6. Lập offered-load stages, cold/warm scenarios và fault/recovery experiments.
7. Định nghĩa latency/throughput/errors/cost metrics cùng mẫu số.
8. Lặp tests, chọn statistics/uncertainty và log biến nhiễu.
9. Viết assumptions register có owner, source, confidence, review date.
10. Chạy sensitivity cho workload mix, growth và hot-tenant traffic.
11. Gắn từng claim quan trọng với evidence ref/limitation.
12. Lập ma trận nhiều dimensions, không tự chọn winner bằng QPS cao nhất.
13. Viết ADR conditional với next experiments, sign-off và rollback criteria.
14. Kiểm bảo mật artifact package không chứa secrets/PII.
15. Giải thích cách tái lập sau sáu tháng khi engine/SDK nâng cấp.

## 71. Tổng kết: báo cáo so sánh là bằng chứng có điều kiện, không phải khẩu hiệu

Khi lựa chọn database NoSQL, con số throughput hoặc latency chỉ có ý nghĩa khi biết **mô hình dữ liệu nào, phiên bản nào, cấu hình nào, workload nào và tiêu chuẩn đo nào** đã tạo ra nó.

Những nguyên tắc trọng tâm:

1. **Ghi chính xác versions.** Engine build, managed-service feature mode, Java/JDK, driver/SDK, tool versions và commit/image digest đều có thể đổi kết quả.
2. **Ghi config đang thực sự có hiệu lực.** Replication, consistency, durability, indexes, sharding, TTL, cache, connection pools, retries và capacity mode không phải chi tiết phụ.
3. **Mô tả topology.** CPU/RAM/storage/IOPS, Region/AZ placement, network và load generator là một phần của thí nghiệm.
4. **Dataset và workload quyết định ý nghĩa benchmark.** Rows/bytes, skew, hot tenants, document sizes, query mix và concurrency phải đại diện access patterns của ứng dụng.
5. **Phân biệt attempts với successful logical operations.** SDK retries và timeout có thể biến một command thành nhiều requests, gây sai QPS/cost.
6. **Báo latency phân bố và failures.** p50/p95/p99, offered load, achieved throughput, errors/timeouts, resource saturation và measurement scope cần cùng xuất hiện.
7. **Warm/cold state phải rõ.** JIT, cache, index build, compaction, background tasks và autoscaling ảnh hưởng tail latency.
8. **Lặp runs và nêu uncertainty.** Một best run không đại diện typical/peak behavior; cỡ mẫu và correlations ảnh hưởng confidence.
9. **Đừng ép hai engine có cùng internals.** So business capabilities và guarantees tương đương; khi không tương đương, ghi sự khác biệt.
10. **Dùng nhiều trục đánh giá.** Cost, reliability, backup/RPO/RTO, security, operations, lock-in và development effort có thể quyết định lựa chọn dù QPS gần nhau.
11. **Giả định phải được nêu rõ.** Mỗi assumption có nguồn, confidence, owner và sensitivity khi điều kiện thay đổi.
12. **Tách observed, configured, estimated, hypothesized, unknown và not tested.** Đừng biến điều chưa đo thành fact.
13. **Lưu manifest, raw artifacts và evidence lineage.** Mỗi claim quan trọng cần truy về run IDs, config, scripts và metrics.
14. **Giữ report có revision.** Khi đổi workload, tính metric khác hoặc phát hiện lỗi thống kê, cập nhật revision/correction minh bạch.
15. **Ghi rõ limitations và next experiments.** Một kết luận conditional có ích hơn một tuyên bố tuyệt đối không được hỗ trợ.
16. **Đặt correctness và hard constraints lên trước winner.** Một hệ nhanh nhưng sai tenant isolation, durability hay RTO không được đánh giá tốt chỉ vì p99 thấp.
17. **So chi phí theo workload và thời điểm giá.** Giá niêm yết, on-demand/provisioned, backup, egress, growth và on-call assumptions phải minh bạch.
18. **Tránh tuning/sampling bias.** Giữ evaluation protocol rõ, luân phiên run order và không chọn result tốt nhất rồi bỏ run còn lại.
19. **ADR lưu lý do quyết định.** Recommendation có owner, điều kiện, unknowns, alternatives và rollback/review triggers.
20. **Tái lập là khả năng kiểm tra lại tuyên bố.** Không cần hai run giống tuyệt đối từng mili giây, nhưng phải đủ thông tin để người khác xác nhận phạm vi và nguyên nhân sai khác.

Khi đọc bất kỳ bảng so sánh NoSQL nào, hãy tự hỏi:

> **“Các con số này được tạo ra bởi những phiên bản, cấu hình và giả định nào; chúng có tương đương với yêu cầu thực tế của hệ thống mình hay không; và nếu một giả định thay đổi thì kết luận có còn đứng vững?”**









