# Lựa chọn cache, document, graph và time-series database

Một hệ thống thương mại điện tử có thể dùng **Amazon Aurora** để lưu đơn hàng, cần phản hồi danh sách sản phẩm nhanh bằng **cache**, cần lưu catalog sản phẩm với thuộc tính thay đổi thường xuyên theo **document model**, cần phát hiện nhóm tài khoản gian lận theo **graph relationships**, và cần phân tích nhiệt độ/độ trễ theo thời gian bằng **time-series database**. Bốn nhu cầu đó có thể xuất hiện cùng lúc, nhưng không nhất thiết nên dùng một loại cơ sở dữ liệu cho tất cả.

Bài thuộc chương **Cache và dữ liệu chuyên dụng** của mô-đun **CLOUD_PROVIDERS_AWS**. Mục tiêu là rèn khả năng chọn dịch vụ AWS dựa trên **access pattern**, mô hình dữ liệu, latency, consistency, khả năng mở rộng, durability, bảo mật, phục hồi và chi phí; đồng thời kết nối thiết kế với Region/AZ, IAM, VPC, compute, lưu trữ, database, tích hợp và serverless.

Các dịch vụ trọng tâm:

- **Cache:** Amazon ElastiCache (Valkey, Redis OSS, Memcached) và trường hợp cần durable in-memory primary database với **Amazon MemoryDB**.
- **Document:** **Amazon DocumentDB (with MongoDB compatibility)**; cân nhắc **Amazon DynamoDB** khi document-like JSON chủ yếu truy cập theo key/access patterns.
- **Graph:** **Amazon Neptune Database** cho graph application và **Neptune Analytics** cho khám phá/thuật toán graph.
- **Time series:** **Amazon Timestream for InfluxDB**, nhất là **InfluxDB 3 Core/Enterprise** cho bài toán mới; phân biệt với **Timestream for LiveAnalytics** hiện không mở cho khách hàng mới.

**Nguyên tắc xuyên suốt:** chọn database theo **câu hỏi ứng dụng cần trả lời**, không chọn chỉ vì dữ liệu có thể biểu diễn bằng JSON, graph hoặc timestamp.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Nhận diện **cache-aside, read-through, write-through, TTL, invalidation và cache stampede**.
2. So sánh **ElastiCache for Valkey/Redis OSS/Memcached**, **serverless/node-based**, và **MemoryDB** theo vai trò cache hay primary database.
3. Chọn **DocumentDB** hoặc **DynamoDB** theo mẫu truy vấn, indexes, document structure và nhu cầu tương thích MongoDB.
4. Phân biệt **property graph** và **RDF graph**, biết khi nào dùng **Neptune Database** hoặc **Neptune Analytics**.
5. Thiết kế **time-series schema** theo timestamp, measurements, tags/dimensions, retention và cardinality.
6. Hiểu trạng thái sản phẩm **Timestream for LiveAnalytics** đối với hệ thống mới và cách đánh giá **Timestream for InfluxDB 2/3**.
7. Thiết kế kiến trúc nhiều nguồn dữ liệu nhưng có **source of truth**, cơ chế đồng bộ, consistency và DR rõ ràng.
8. Lập ma trận đánh giá **latency, throughput, HA, backup, security, monitoring, cost** và kiểm chứng bằng benchmark.
9. Vận dụng AWS CLI/Java/pseudocode để xác minh dịch vụ, xử lý lỗi và thực hiện các tình huống thực hành.

## 2. Đặt câu hỏi đúng trước khi chọn cơ sở dữ liệu

Một tài liệu JSON có thể được lưu trong S3, DynamoDB, DocumentDB hoặc PostgreSQL JSONB. Một quan hệ giữa hai tài khoản có thể được lưu thành hai foreign keys trong RDS hoặc thành edge trong Neptune. Một điểm đo CPU có timestamp có thể xuất hiện trong CloudWatch, OpenSearch, S3 hoặc time-series DB. **Kiểu dữ liệu lưu trữ chưa đủ để quyết định.**

### 2.1. Sáu câu hỏi kiến trúc

| Câu hỏi | Dấu hiệu nên chú ý | Ảnh hưởng tới lựa chọn |
|---|---|---|
| **Access pattern** | Key lookup, nested filter, graph traversal, time-window aggregation | Quan trọng hơn tên data format |
| **Latency/SLO** | p95/p99 vài ms, dashboard vài giây, batch vài phút | Cache/in-memory, indexes hay analytics engine |
| **Consistency** | Có thể chấp nhận stale data? Cần đọc sau ghi? | Cache invalidation, read/write consistency, transactional DB |
| **Durability** | Cache mất có thể tái tạo? Có phải bản ghi gốc? | ElastiCache vs durable primary, backups/replication |
| **Scale/cardinality** | Keys/edges/series/attributes tăng thế nào? | Partitioning, high-cardinality indexing, cluster sizing |
| **Operations/cost** | Traffic biến động, data retention, HA, security | Serverless/node, storage tiers, Multi-AZ, observability |

### 2.2. Phân biệt source of truth và dữ liệu dẫn xuất

**Source of truth** là nơi bản ghi được quản lý có quy tắc và phục hồi dữ liệu. **Cache** thường là bản sao tối ưu tốc độ từ source of truth; có thể xóa/rebuild khi TTL hết hoặc bị eviction. **Graph projection** và **time-series analytics** cũng có thể là dữ liệu dẫn xuất từ events, nhưng vẫn cần cơ chế backfill và tái tạo nếu hệ thống gốc giữ lịch sử.

Không mặc định mọi in-memory service chỉ là cache: **MemoryDB** được thiết kế như durable in-memory database, và những tính năng durability của ElastiCache có thể thay đổi theo **engine/version/kiểu triển khai**. Vì vậy nên đánh giá **hợp đồng durability thực tế của phiên bản được chọn**, không dựa vào khẩu hiệu chung.

## 3. Ma trận lựa chọn dịch vụ AWS theo workload

| Nhu cầu | Dịch vụ nên đánh giá trước | Dạng dữ liệu/truy vấn | Cẩn trọng |
|---|---|---|---|
| Tăng tốc truy vấn sản phẩm / session / rate limit | **ElastiCache for Valkey** hoặc Redis OSS | Key-value, hash, set, sorted set và TTL | Invalidation, eviction, failover, hot keys |
| Cache key-value đơn giản, muốn đa luồng | **ElastiCache for Memcached** | Key-value ephemeral | Feature/data model ít hơn Valkey, HA/persistence khác |
| Primary database cần tốc độ in-memory, durability | **Amazon MemoryDB** | Valkey/Redis-compatible structures và queries | Durability/consistency, topology, write latency/cost |
| Catalog/hồ sơ linh hoạt, nested document filters | **Amazon DocumentDB** | JSON/BSON documents, MongoDB-compatible API | Tương thích MongoDB không 100%, query/index migration |
| Profile/order JSON nhưng truy cập theo partition/sort key rõ | **Amazon DynamoDB** | Key-value/document attributes, access patterns định trước | Query key/index design, hot partitions, scan cost |
| Quan hệ nhiều bước: fraud ring, social connections | **Amazon Neptune Database** | Property graph hoặc RDF, Gremlin/openCypher/SPARQL | Không biến mọi SQL JOIN thành graph |
| Thuật toán tìm cộng đồng, centrality trên graph lớn | **Neptune Analytics** | In-memory graph analytics, algorithms | Không mặc nhiên thay transaction graph database |
| Sensor/IoT/observability metrics, query theo thời gian | **Timestream for InfluxDB 3** | Timestamps, tags, fields, range/aggregation | Cardinality, retention, write batching, edition |
| Timestream LiveAnalytics đã triển khai | **Timestream for LiveAnalytics** (khách hàng hiện tại đủ điều kiện) | Time-series analytical queries | **Không nhận khách hàng mới kể từ 20/06/2025** |
| Batch dữ liệu rất cũ, truy vấn không thường xuyên | **Amazon S3 + Parquet + Athena** | Data lake/scan/analytics | Không thay OLTP/low-latency cache |
| Full-text search và log search | **Amazon OpenSearch Service** | Text relevance, inverted indexes, aggregation | Không mặc định là transactional source of truth |

**Ví dụ:** ứng dụng cần lấy giá sản phẩm theo ID p99 thấp ⇒ DynamoDB/Aurora làm nguồn dữ liệu, ElastiCache làm lớp tăng tốc. Ứng dụng cần tìm tài khoản kết nối với tài khoản gian lận qua **4 cấp quan hệ** ⇒ Neptune đáng thử hơn việc lưu hàng loạt mảng IDs trong một document.

### 3.1. Cây quyết định đơn giản

~~~mermaid
flowchart TD
    REQ["Định nghĩa workload + SLO"] --> Q{"Phần lớn truy vấn là gì?"}
    Q -->|"Key lookup rất nhanh,<br/>data có thể rebuild"| CACHE["ElastiCache<br/>Valkey / Redis OSS / Memcached"]
    Q -->|"Primary in-memory<br/>durable"| MEM["MemoryDB hoặc ElastiCache<br/>durability phù hợp"]
    Q -->|"Nested documents,<br/>rich filters/aggregation"| DOC["DocumentDB<br/>hoặc RDS JSONB"]
    Q -->|"Key-driven NoSQL<br/>JSON attributes"| DDB["DynamoDB"]
    Q -->|"N-hop graph<br/>traversal/relationships"| GRAPH["Neptune Database"]
    Q -->|"Graph algorithms<br/>exploration"| ANALYTICS["Neptune Analytics"]
    Q -->|"Timestamp + window<br/>aggregation"| TIME["Timestream for InfluxDB"]
    Q -->|"Cold historical<br/>data scans"| LAKE["S3 + Parquet + Athena"]
    CACHE --> SAFE["Kiểm chứng consistency,<br/>IAM/VPC, HA, benchmark, cost"]
    MEM --> SAFE
    DOC --> SAFE
    DDB --> SAFE
    GRAPH --> SAFE
    ANALYTICS --> SAFE
    TIME --> SAFE
    LAKE --> SAFE
~~~

Đây là **điểm xuất phát**, không phải công thức bắt buộc. Hệ thống có thể dùng **một database chính + một số projections chuyên biệt** nếu dữ liệu và SLO thật sự đòi hỏi. Mỗi database bổ sung làm tăng **sync complexity, credentials, KMS, backup và chi phí vận hành**.

## 4. Cache hoạt động ra sao và khi nào có ích?

Cache giúp giảm độ trễ và áp lực đọc trên database gốc. Trong mô hình phổ biến **cache-aside**, ứng dụng quyết định đọc cache, fallback sang DB và nạp lại cache sau miss.

~~~mermaid
sequenceDiagram
    participant U as API request
    participant APP as Java service
    participant C as ElastiCache
    participant DB as Aurora / DynamoDB
    U->>APP: GET /products/42
    APP->>C: GET product:42
    alt Cache hit
        C-->>APP: JSON / value đã cache
    else Cache miss
        C-->>APP: nil
        APP->>DB: Đọc product 42
        DB-->>APP: Bản ghi gốc
        APP->>C: SET product:42 TTL 120s
    end
    APP-->>U: Product response
~~~

### 4.1. Những pattern phổ biến

| Pattern | Đọc | Ghi/cập nhật | Đánh đổi |
|---|---|---|---|
| **Cache-aside / lazy loading** | App đọc cache; miss thì đọc DB và cache lại | App cập nhật DB rồi invalidate cache | Miss penalty, dễ stale data nếu invalidate thiếu |
| **Read-through** | Cache layer tự lấy từ source khi miss theo kiến trúc client/provider | Tùy layer | Phức tạp tích hợp, không phải mọi engine tự hỗ trợ |
| **Write-through** | Đọc từ cache hoặc source tùy thiết kế | Đồng bộ cache và source trong write path | Có thể tăng write latency, cần xử lý failure atomicity |
| **Write-behind / write-back** | Cache phục vụ trước | Ghi source bất đồng bộ về sau | Có nguy cơ mất/chậm ghi, không phù hợp dữ liệu tài chính quan trọng nếu thiếu durability |
| **TTL** | Key tự hết hạn | Không cần invalidate thủ công cho mọi trường hợp | Có thể stale đến hết TTL |
| **Explicit invalidation** | Cache hit cho dữ liệu còn hợp lệ | Xóa/update key ngay sau DB commit | Cần quản lý race, event delivery và namespace |
| **Negative caching** | Cache “not found” ngắn hạn | Hết hạn nhanh khi data xuất hiện | Dễ che dữ liệu mới nếu TTL quá dài |

### 4.2. Khi nào cache không làm mọi thứ nhanh hơn?

- **Cache hit ratio thấp:** data hiếm khi được truy cập lại, memory dùng không hiệu quả.
- **Payload quá lớn:** serialize/deserialize và network transfer có thể lớn hơn DB lookup đã index.
- **Key nóng (hot key):** một key nhận rất nhiều request, tạo nghẽn shard/node.
- **Cache miss đồng loạt:** cache stampede khiến DB nhận lượng truy vấn lớn.
- **Dữ liệu thay đổi liên tục:** invalidation phức tạp, stale data không chấp nhận được.
- **Mất cache gây sự cố:** nếu ứng dụng coi cache là source of truth nhưng chưa thiết kế durability/backup, failover có thể làm mất dữ liệu quan trọng.

### 4.3. Cache stampede và kỹ thuật bảo vệ

Một key phổ biến hết hạn khi có 10.000 requests; tất cả request cùng miss và gọi database. Các kỹ thuật phổ biến:

1. **TTL jitter:** thêm ngẫu nhiên có kiểm soát để các keys không cùng hết hạn.
2. **Request coalescing / single-flight:** chỉ một request nạp từ DB cho cùng key tại một thời điểm.
3. **Stale-while-revalidate:** trả giá trị hơi cũ nếu nghiệp vụ cho phép, refresh nền có giới hạn.
4. **Rate limiting/backpressure:** giới hạn số DB fallbacks khi cache lỗi.
5. **Warm-up chọn lọc:** làm nóng các keys hay truy cập khi deploy/failover, không quét toàn bộ DB vô tội vạ.
6. **Circuit breaker:** cache timeout không được treo toàn bộ API; nhưng fallback cũng phải giới hạn áp lực DB.

### 4.4. Phép tính cache hit ratio

**Hit ratio** = cache hits / (cache hits + misses) trong một cửa sổ đo. Ví dụ 9.000 hits và 1.000 misses ⇒ tỷ lệ **90%**. SLO cần đo cả **p95/p99 khi hit và khi miss**, không chỉ average latency. Không kết luận hit ratio 90% luôn đủ: 10% misses tại 20.000 RPS vẫn là 2.000 RPS tới database.

## 5. ElastiCache: Valkey, Redis OSS hay Memcached?

**Amazon ElastiCache** hỗ trợ **Valkey, Redis OSS, Memcached** với những khả năng khác nhau theo engine version, node type và deployment option.

| Tiêu chí | **Valkey** | **Redis OSS** | **Memcached** |
|---|---|---|---|
| Mô hình dữ liệu | Key-value, hashes, lists, sets, sorted sets và những tính năng theo version | Redis data structures tương ứng với phiên bản được hỗ trợ | Key-value đơn giản |
| TTL/eviction | Có | Có | Có |
| Replication/failover | Có theo configuration | Có theo configuration | Kiến trúc đơn giản, HA/replication khác |
| Cluster/sharding | Có theo engine deployment | Có | Có phân phối keys theo client/cluster |
| Pub/Sub | Có | Có | Không |
| Multi-threaded engine | Nhiều tính năng I/O threading theo version, execution semantics cần đo | Tùy version | Kiến trúc multi-threaded |
| Rich data types / atomic commands | Rộng | Rộng | Hạn chế hơn |
| Persistence/durability | Phụ thuộc engine/version/cấu hình; **đánh giá tính năng ElastiCache durability mới** | Phụ thuộc hỗ trợ và cấu hình | Cache ephemeral, không như primary durable DB |
| Dùng khi | Cache tổng quát, rate limit, rankings, sessions | Workload sẵn Redis OSS với compatibility cụ thể | Cache đơn giản, muốn giảm complexity |

AWS hiện phát triển **Valkey** với nhiều tính năng mới (ví dụ vector/full-text/durability theo version). **Không lấy bảng trên làm cam kết mọi feature đều có trong tất cả Regions và engine versions**. Với code đang dùng Redis OSS modules/commands, kiểm tra **compatibility và supported commands** trước khi chuyển Valkey hoặc Memcached.

### 5.1. ElastiCache Serverless và node-based khác gì?

| Tiêu chí | **ElastiCache Serverless** | **Node-based cluster** |
|---|---|---|
| Capacity management | Dịch vụ tự điều chỉnh capacity | Tự chọn node family/count, shards và replicas |
| Billing | Theo mô hình storage/processing units hiện hành | Node-hours/capacity theo loại node |
| Vận hành | Ít phải quản lý scale chi tiết | Kiểm soát topology, placement, hardware |
| Engine support | Theo engine/version serverless được hỗ trợ | Phạm vi engine/version/node rộng hơn |
| Client behavior | Valkey/Redis OSS serverless sử dụng cluster mode enabled | Có thể chọn cluster mode tùy cấu hình |
| Khi phù hợp | Traffic biến động, đơn giản hóa operations | Workload ổn định, sizing đặc thù hoặc tối ưu giá |

**Serverless không có nghĩa không có giới hạn**: vẫn có service quotas, memory/compute pricing, networking requirements và giới hạn client compatibility. Với Valkey/Redis OSS serverless, client cần **cluster-mode support**; một thư viện Java cũ dùng connection string cho single node có thể không hoạt động như kỳ vọng.

### 5.2. TTL và eviction không đồng nghĩa với durability

**TTL** là quy tắc hết hạn key theo thời gian. **Eviction** là việc engine loại một số keys khi memory pressure theo policy cấu hình. **Durability** là cam kết lưu được dữ liệu qua failures/replication/persistence theo engine feature. Một key TTL 24 giờ vẫn có thể bị eviction trước đó nếu cache đầy.

Đừng dùng session token/giỏ hàng/locks có yêu cầu khôi phục nghiêm ngặt chỉ dựa vào mặc định cache; trước khi lưu durable state ở in-memory service, đánh giá tính năng **ElastiCache durability** hoặc **MemoryDB** theo version/SLA và thử failure scenarios.

## 6. MemoryDB và vai trò durable in-memory primary database

**Amazon MemoryDB** được thiết kế cho những ứng dụng cần **database in-memory có durability**, sử dụng các API/data structures tương thích **Valkey/Redis OSS** trong phạm vi hỗ trợ. Nó không chỉ là một lớp cache trước một nguồn dữ liệu khác: ứng dụng có thể xem MemoryDB là **primary database** cho một số workloads.

| Câu hỏi | **ElastiCache** | **MemoryDB** |
|---|---|---|
| Vai trò mặc định | Cache tăng tốc trước DB/source of truth | Durable in-memory primary database |
| Khi mất key/cache | Thường có thể rebuild từ DB | Phải xem backup/replication/recovery như hệ thống dữ liệu chính |
| Data durability | Có nhiều mức/tính năng tùy Valkey engine, version, deployment | Được thiết kế để giữ dữ liệu bền vững theo hợp đồng dịch vụ |
| Read latency | Rất thấp khi data trong memory | Rất thấp khi data trong memory |
| Write latency | Phụ thuộc async/sync durability, topology | Có overhead của durable writes theo cơ chế |
| Multi-Region | Tùy tính năng/version | Có các lựa chọn active-active theo tính năng hỗ trợ |
| Phí/TCO | Cache capacity/processing, có thể cần DB gốc | DB capacity, replication/durability và khả năng loại bỏ DB gốc nếu phù hợp |

**Không đưa ra quy tắc cứng “ElastiCache luôn không durable, MemoryDB luôn cần cho mọi persistence”.** AWS đã bổ sung khả năng durability cho một số cấu hình **ElastiCache for Valkey**. Hãy dùng yêu cầu **RPO, consistency, replica failover, write acknowledgment, backup và cross-Region recovery** để chọn, và kiểm tra tính năng theo đúng engine version hiện tại.

### 6.1. Khi MemoryDB hợp lý hơn cache-aside

- Ứng dụng có **working set hoàn toàn trong memory**, truy vấn nhanh trên hashes/sets/sorted sets.
- **Dữ liệu là bản ghi gốc** và không thể đơn giản xóa rồi rebuild từ một Aurora/DynamoDB khác.
- Muốn dùng Valkey/Redis-compatible data types cho **real-time scoring, session/state quan trọng hoặc microservices**, với durability và HA được thiết kế.
- Có nhu cầu **replication/multi-Region active-active** theo các tính năng tương thích, sau khi kiểm tra conflict resolution semantics.

**Ví dụ:** bảng xếp hạng game có thể lưu trong cache nếu có thể tái tạo từ event log. Nếu điểm số chỉ tồn tại trong in-memory store và phải khôi phục sau failure, kiến trúc phải có **durable primary storage** (MemoryDB hoặc một hệ thống durable khác), không chỉ một TTL cache.

### 6.2. Những câu hỏi phải kiểm thử trước production

1. Một acknowledged write có được phục hồi sau primary node failure không?
2. Điều gì xảy ra khi write vượt khả năng replica/transaction log?
3. RPO/RTO và region failure strategy là gì?
4. Khi client reconnect, read-your-writes/consistency có đáp ứng nghiệp vụ không?
5. Khi chuyển từ Redis OSS/Valkey hiện tại, có dùng commands/modules không được engine hỗ trợ?
6. Chi phí replication, memory overhead, backup và operations so với DynamoDB/Aurora + cache thế nào?

## 7. Document database: vì sao dữ liệu JSON chưa đủ để chọn?

**Document model** gom những thông tin liên quan thành document linh hoạt với nested objects/arrays. Thích hợp khi các bản ghi **khác nhau về thuộc tính**, thường được đọc/ghi theo một đơn vị logic, và ứng dụng cần **truy vấn những trường nằm trong document**.

Ví dụ **catalog sản phẩm**:

~~~json
{
  "_id": "sku-2048",
  "name": "Wireless headset",
  "category": "audio",
  "attributes": {
    "batteryHours": 24,
    "color": "black",
    "connectivity": ["bluetooth", "usb-c"]
  },
  "offers": [
    {"seller": "seller-a", "price": 79.9, "currency": "USD"}
  ],
  "status": "ACTIVE",
  "updatedAt": "2026-11-20T02:00:00Z"
}
~~~

Một document như vậy có thể được đọc bằng **_id**, lọc theo **category** và **attributes.color**, hoặc tổng hợp theo sellers. Nhưng hãy hỏi **query thật**: tìm bằng SKU ⇒ DynamoDB có thể đủ; cần nhiều filters/ad hoc aggregation/indexes trên nested fields ⇒ DocumentDB đáng thử.

### 7.1. Amazon DocumentDB (with MongoDB compatibility)

**Amazon DocumentDB** là dịch vụ document database do AWS quản lý, tương thích **MongoDB API** theo những phiên bản/tính năng được AWS công bố. DocumentDB hỗ trợ các thao tác CRUD, indexes, aggregations và transactions theo engine version cụ thể. Các phiên bản tương thích MongoDB được AWS công bố bao gồm **4.0, 5.0 và 8.0**, cùng phạm vi APIs và những khác biệt có tài liệu riêng.

**MongoDB-compatible không có nghĩa MongoDB chạy nguyên vẹn trên AWS**:

- Một số **commands, aggregation operators, transactions, TTL/indexes và driver behaviors** có khác biệt theo version.
- **Retryable writes** và query planner behavior có thể thay đổi theo DocumentDB engine version; không copy nguyên driver defaults mà bỏ qua compatibility matrix.
- Kết quả truy vấn **không được mặc nhiên bảo đảm thứ tự** nếu không có **sort** rõ ràng.
- Kết nối thường qua **TLS**, VPC security group và database credentials; backend cần credential rotation và role/privileges.
- Workload migration phải kiểm tra **functional differences** và performance thật, không chỉ test rằng CRUD cơ bản chạy.

### 7.2. Mô hình document: embedding hay referencing?

| Thiết kế | Ví dụ | Ưu điểm | Nhược điểm |
|---|---|---|---|
| **Embedding** | Product chứa vài variations hoặc recent reviews | Đọc một document nhanh, hợp aggregate | Document phình to, cập nhật đồng thời phức tạp |
| **Referencing** | Product riêng; reviews/orders tham chiếu productId | Đỡ tăng document vô hạn, tránh cập nhật cả khối | Nhiều queries/joins hoặc lookup aggregation |
| **Hybrid** | Product lưu summary và top 3 reviews; full reviews ở collection khác | Tối ưu hot read, dữ liệu lịch sử tách riêng | Phải đồng bộ summary và source |

**Không embed tất cả events, reviews hay transactions mãi vào một document.** Khi số phần tử trong array tăng liên tục, document size, index updates và write contention sẽ trở thành bottleneck. Thử trên dữ liệu có kích thước và phân phối thật.

### 7.3. MongoDB-style query minh họa

~~~javascript
// Ví dụ cú pháp mongosh; cần collection/index phù hợp.
db.products.find(
  {
    category: "audio",
    "attributes.color": "black",
    status: "ACTIVE"
  },
  {
    _id: 1,
    name: 1,
    "offers.price": 1
  }
).sort({updatedAt: -1}).limit(20);
~~~

Muốn tối ưu, cần đo **index selectivity, query plan/explain, document size và write amplification**. Kiểm tra tương thích với engine DocumentDB cụ thể trước khi áp dụng indexes/aggregation pipeline. Không assume MongoDB-specific vector, text hay TTL features giống nhau ở mọi release.

## 8. DynamoDB cũng lưu document, nhưng tối ưu access pattern khác

**Amazon DynamoDB** là NoSQL database quản lý hoàn toàn, lưu các **items** gồm attributes kiểu string/number/binary/Map/List, có thể biểu diễn nested JSON-like data. Dữ liệu được truy cập hiệu quả nhất khi truy vấn bằng **partition key**, **sort key** và **secondary indexes** đã thiết kế.

### 8.1. Một document-like item trong DynamoDB

~~~json
{
  "PK": "PRODUCT#sku-2048",
  "SK": "META",
  "category": "audio",
  "name": "Wireless headset",
  "attributes": {
    "color": "black",
    "batteryHours": 24
  },
  "status": "ACTIVE"
}
~~~

Một item có thể chứa **Map/List** phong phú, nhưng **FilterExpression không thay thế key design**: filter thường được áp dụng **sau khi dữ liệu đã được Query/Scan đọc**, nên không giảm read capacity tương tự một index phù hợp. DynamoDB giới hạn **item size 400 KiB** theo quota dịch vụ; document quá lớn nên tách thành nhiều items hoặc lưu blob ở S3.

### 8.2. DynamoDB và DocumentDB nên chọn cái nào?

| Tiêu chí | **DynamoDB** | **DocumentDB** |
|---|---|---|
| Mẫu truy vấn chính | Keys, sort keys, GSIs và access patterns biết trước | Nested field filters, Mongo-compatible queries và aggregations |
| Khả năng scale | Serverless-managed capacity/partitions | Cluster/instance/elastic deployment tùy engine và model |
| Mô hình document | Map/List attributes trong item | BSON-like documents/collections |
| Truy vấn ad hoc | Cần Scan hoặc schema/index cải tiến; không tối ưu mặc định | Mạnh hơn cho nhiều kiểu document query nhưng index vẫn quan trọng |
| Transactions | Có APIs transactional trong phạm vi quota | Có transactions theo engine version/phạm vi hỗ trợ |
| Consistency | Eventual/strong reads tùy API/table/index; Global Tables có semantics riêng | Primary/replica read semantics theo engine và topology |
| Drivers | AWS SDK DynamoDB APIs | MongoDB-compatible drivers trong phạm vi hỗ trợ |
| Migration từ MongoDB | Cần thiết kế lại keys và queries đáng kể | Có thể giảm thay đổi, nhưng cần compatibility assessment |

**Ví dụ 1:** tra giá theo SKU và lấy đơn hàng theo userId + timestamp ⇒ DynamoDB rất phù hợp khi partitioning/GSIs được thiết kế đúng. **Ví dụ 2:** admin portal cho phép lọc catalog theo hàng chục thuộc tính tùy ngành, cần aggregation pipelines và đã có MongoDB codebase ⇒ DocumentDB đáng đánh giá.

### 8.3. Khi nào vẫn nên chọn PostgreSQL JSONB?

Nếu workload có **SQL JOIN/transactions**, dữ liệu relational cốt lõi và chỉ thêm một phần metadata JSON linh hoạt, **Aurora/RDS PostgreSQL JSONB** có thể giảm số database phải vận hành. Không tạo DocumentDB riêng chỉ vì có vài trường JSON. Kiểm tra **SQL query plans/indexes, throughput, schema evolution và data consistency** trước khi thêm chuyên biệt hóa.

### 8.4. Migration checklist cho DocumentDB

1. Kiểm kê MongoDB commands, driver versions, aggregation operators, indexes, change streams và retry behaviors.
2. Chạy **AWS DocumentDB compatibility assessment** và kiểm tra release-specific functional differences.
3. Chọn cluster topology, reader replicas, backup/restore, storage encryption và VPC/TLS.
4. Migration bằng AWS DMS hoặc MongoDB tools được hỗ trợ, có **full load + change capture** khi phù hợp.
5. Chạy tests theo **query latency p95/p99**, explain plans, correctness và consistency ở workload thật.
6. Lập rollback/dual-read/migration cutover plan; đừng tuyên bố một lần import data là đã migration thành công.

## 9. Graph database: lưu mối quan hệ là thực thể hạng nhất

Trong mô hình quan hệ, các bảng **users, devices, orders, payment_methods** có foreign keys và JOIN. Nếu truy vấn chủ yếu là **“khách hàng này có những đơn hàng nào?”**, SQL hoặc DynamoDB key query có thể hiệu quả. Nhưng nếu câu hỏi trở thành:

> “Trong tối đa bốn bước kết nối, có những tài khoản nào dùng chung thiết bị, địa chỉ, thẻ thanh toán và liên quan tới tài khoản gian lận đã xác nhận?”

Khi đó, **relationships** mới là trung tâm bài toán. Một graph mô hình hóa **vertices/nodes** và **edges**, cho phép query đường đi, pattern và neighborhood.

~~~mermaid
flowchart LR
    U1["User A"] -->|"USES"| D1["Device X"]
    U2["User B"] -->|"USES"| D1
    U2 -->|"PAID_WITH"| CARD["Card Y"]
    U3["User C"] -->|"PAID_WITH"| CARD
    U3 -->|"FLAGGED_AS"| FRAUD["Fraud risk"]
    U1 -->|"PLACED"| ORDER["Order #123"]
~~~

### 9.1. Property graph và RDF graph

| Mô hình | Dạng dữ liệu | Query languages trong Neptune Database | Ví dụ |
|---|---|---|---|
| **Property graph** | Nodes/edges có labels và properties | **openCypher** hoặc **Apache TinkerPop Gremlin** | Fraud ring, social connections, recommendations |
| **RDF graph** | Triples **subject-predicate-object** | **SPARQL** | Knowledge graphs, ontology, semantic metadata |

**Không trộn hai mô hình trong cùng một query chỉ vì Neptune hỗ trợ cả ba query languages.** Với Neptune, **openCypher và Gremlin** truy vấn property graph; **SPARQL** dùng cho RDF graph. Phải chọn mô hình ngay khi thiết kế input/schema/query.

### 9.2. Mô hình dữ liệu graph cho fraud detection

| Node/edge | Thuộc tính | Ý nghĩa |
|---|---|---|
| **User** | userId, riskLevel, createdAt | Danh tính người dùng |
| **Device** | fingerprint hash, os | Thiết bị đã dùng |
| **Card** | tokenizedCardId (không lưu PAN) | Phương tiện thanh toán mã hóa/tokenized |
| **Order** | orderId, total, timestamp | Đơn hàng |
| **USES (User→Device)** | firstSeen, lastSeen | Người dùng dùng thiết bị |
| **PAID_WITH (User→Card)** | lastSeen | Tài khoản dùng thẻ |
| **PLACED (User→Order)** | timestamp | Tài khoản tạo đơn |

Không đưa card PAN, mật khẩu hoặc PII chưa bảo vệ vào vertex IDs/properties; vẫn phải thiết kế **IAM/VPC/TLS/KMS, tenant isolation, retention và quyền truy vấn**. Graph thuận tiện tìm liên kết nhưng cũng có nguy cơ làm lộ toàn bộ mạng quan hệ nếu query API thiếu authorization.

### 9.3. openCypher query minh họa

~~~cypher
// Tìm user khác có dùng cùng device với user-123.
MATCH (u:User {userId: 'user-123'})-[:USES]->(d:Device)<-[:USES]-(other:User)
WHERE other.userId <> u.userId
RETURN DISTINCT other.userId AS relatedUser, d.deviceId AS sharedDevice
LIMIT 25
~~~

Với Neptune Database, cần dùng endpoint/protocol của **openCypher** phù hợp và query syntax được phiên bản engine hỗ trợ. Không giả định mọi tính năng của **Neo4j Cypher** đều tương thích: Neptune hỗ trợ **openCypher** với danh sách limitations/functional differences riêng.

### 9.4. Gremlin và SPARQL dùng trong ngữ cảnh nào?

**Gremlin** là graph traversal API với các bước duyệt có tính chương trình, ví dụ concept:

~~~groovy
// Gremlin minh họa trên property graph, ID/labels chỉ để học.
g.V().has('User', 'userId', 'user-123').
  out('USES').
  in('USES').
  dedup().
  values('userId')
~~~

**SPARQL** dùng RDF triples:

~~~sparql
PREFIX ex: <https://example.org/>
SELECT ?related WHERE {
  ex:user123 ex:usesDevice ?device .
  ?related ex:usesDevice ?device .
  FILTER (?related != ex:user123)
}
LIMIT 25
~~~

Chọn Gremlin/openCypher cho property graph theo kinh nghiệm đội ngũ và query patterns; dùng RDF/SPARQL khi cần ontology, linked data hoặc reasoning/semantic representations phù hợp. **Đừng đẩy log events dài hạn vào Neptune chỉ vì chúng có quan hệ userId**; thường cần S3/time-series cho event history và chỉ projection edges có giá trị cho traversals.

## 10. Neptune Database hay Neptune Analytics?

**Amazon Neptune Database** phục vụ **application graph queries/transactions** với dữ liệu graph đang vận hành. **Neptune Analytics** thiên về **phân tích graph quy mô lớn**, thuật toán tìm cộng đồng, centrality, shortest path, anomaly/risk và các workload khám phá dữ liệu từ Neptune Database hoặc S3.

| Tiêu chí | **Neptune Database** | **Neptune Analytics** |
|---|---|---|
| Mục tiêu | Graph database cho ứng dụng | Graph analysis/algorithmic processing |
| Workload | Truy vấn nhiều bước trên graph đã lưu và cập nhật theo nghiệp vụ | Phân tích community, centrality, path, graph ML/analytics |
| Latency | Nhắm tới online graph queries theo SLO | Tối ưu graph analytics tùy kích thước và thuật toán |
| Input | Graph data vận hành | Graph snapshot/dataset từ Neptune hoặc S3 |
| Data lifetime | Long-lived database theo HA/backup | Đồ thị phân tích với lifecycle/capacity riêng |
| Nên chọn khi | Fraud alerts mỗi order, recommendation traversal | Hàng đêm tìm fraud communities hoặc network threats |

### 10.1. Một kiến trúc graph kết hợp

~~~mermaid
flowchart LR
    EVENTS["Orders / Payments / User events"] --> ETL["Stream / ETL transform"]
    ETL --> GRAPH["Neptune Database<br/>Operational property graph"]
    GRAPH --> API["Fraud detection API<br/>N-hop traversal"]
    GRAPH --> ANALYZE["Neptune Analytics<br/>Community / centrality"]
    ANALYZE --> INSIGHTS["Fraud risk score / patterns"]
    INSIGHTS --> GRAPH
    EVENTS --> RAW["S3 event archive"]
~~~

**Lưu ý consistency:** nếu graph projection được cập nhật từ events bất đồng bộ, có thể có **lag** so với transaction database. Không tự động chặn một giao dịch chỉ dựa trên graph còn chưa nhận đủ events mà thiếu xử lý trạng thái **unknown/outdated**. Thiết kế lastUpdated/version và backfill.

### 10.2. Khi không cần Neptune

- Relationships chỉ có 1–2 phép JOIN được index tốt trong PostgreSQL.
- Nhu cầu chủ yếu là lọc văn bản tự do, search relevance ⇒ cân nhắc OpenSearch.
- Nhu cầu là “đếm số lần nhấp theo phút” ⇒ time-series/analytics, không phải graph.
- Dữ liệu graph quá ít, query đơn giản và việc đồng bộ graph thứ hai tốn hơn lợi ích.

**Trước khi thêm graph DB**, benchmark **query complexity, number of hops, degree distribution, update rate, projection lag, hot vertices và graph storage cost** so với giải pháp SQL hiện có.

## 11. Time-series database: truy vấn theo thời gian thay vì key/document đơn lẻ

**Time-series data** là chuỗi các observations gắn timestamp, ví dụ CPU utilization của một server, nhiệt độ máy công nghiệp, telemetry của thiết bị, số giao dịch theo phút hoặc độ trễ API p99.

Một điểm đo gồm:

- **Measurement:** loại dữ liệu, ví dụ **temperature**, **http_request**, **cpu**.
- **Timestamp:** thời điểm observation, cần timezone/precision nhất quán.
- **Tags/dimensions:** metadata lọc và phân nhóm, ví dụ **deviceId, region, service**.
- **Fields/measures:** giá trị được đo như **temperatureC, latencyMs, count**.

Ví dụ conceptual record:

~~~json
{
  "measurement": "temperature",
  "time": "2026-11-20T03:00:00Z",
  "tags": {"site": "factory-2", "deviceId": "sensor-17"},
  "fields": {"temperatureC": 28.4, "humidityPercent": 67.2}
}
~~~

Các query thường là:

1. **Last value:** nhiệt độ mới nhất của một device.
2. **Time window:** trung bình/maximum mỗi 5 phút trong 24 giờ.
3. **Grouping:** p95 latency theo service/Region trong một giờ.
4. **Alerting:** phát hiện sensor quá ngưỡng trong 10 phút.
5. **Downsampling:** tổng hợp dữ liệu 1 giây thành 1 phút hoặc 1 giờ cho dài hạn.
6. **Retention:** giữ raw metrics 7–30 ngày, aggregates nhiều tháng/năm theo yêu cầu.

### 11.1. Tại sao không cứ ghi mọi điểm vào RDS?

RDS có thể lưu timestamped rows và chạy SQL tốt ở nhiều bài toán. Nhưng ingestion throughput lớn, retention theo thời gian, downsampling và truy vấn time-window trên hàng tỷ records có thể cần **partitioning, indexes, compression, data tiering và lifecycle** phức tạp. Time-series engines chuyên dụng có mô hình tối ưu cho các workload này.

**Không bắt buộc dùng time-series database** nếu mỗi ngày chỉ ghi vài trăm dòng và SQL time-window query đã đáp ứng SLO. Một hệ thống Postgres/Aurora hiện có có thể đủ và đơn giản hơn vận hành thêm dịch vụ mới.

## 12. Amazon Timestream for InfluxDB: lựa chọn mới theo InfluxDB 2/3

**Amazon Timestream for InfluxDB** cung cấp InfluxDB managed service trên AWS. Với **InfluxDB 3**, AWS phân biệt **Core** và **Enterprise**; kiến trúc InfluxDB 3 sử dụng Arrow/DataFusion, dữ liệu dạng **Parquet** và lớp lưu trữ dựa trên **Amazon S3** theo mô hình engine. Đây là sản phẩm khác với **Timestream for LiveAnalytics** truyền thống.

### 12.1. InfluxDB 3 Core và Enterprise

| Tiêu chí | **InfluxDB 3 Core** | **InfluxDB 3 Enterprise** |
|---|---|---|
| Node topology | Single-node | Có thể chọn single/multi-node theo cấu hình được hỗ trợ |
| Phù hợp | Dev/test, near-real-time recent data | Production HA, dài hạn và analytics phức tạp |
| Long-term data | Không phải lựa chọn tốt khi thiếu compaction | Có compaction và tối ưu lịch sử |
| HA | Single node có giới hạn availability | Multi-node có thể phân bố nhiều AZ |
| Read/write scaling | Theo single-node resources | Có khả năng scale theo roles/nodes và version |
| Chi phí | Đơn giản hơn cho workload nhỏ/ngắn hạn | Capacity/cluster/storage và networking cao hơn |

**Không chọn Core cho retention nhiều năm chỉ vì nó rẻ hơn tại thời điểm tạo.** AWS khuyến nghị Core cho dữ liệu gần đây do hạn chế compaction; Enterprise thích hợp hơn khi cần historical analytics, high-cardinality data và availability. Các giới hạn node count, instance classes và Regions thay đổi; xác minh console/docs hiện hành.

### 12.2. InfluxDB 2 và InfluxDB 3 không chỉ khác phiên bản

InfluxDB 2 thường liên quan InfluxQL/Flux và TSM engine theo phiên bản/cấu hình; InfluxDB 3 có architecture/query mechanisms khác. Khi migration, kiểm tra:

- **Write API/line protocol compatibility** và retention semantics.
- **Query language** hiện có trong application/dashboard (InfluxQL/Flux/SQL) theo phiên bản.
- **Tags/fields cardinality**, schema và precision.
- **Client libraries, authentication tokens, permissions**, endpoints và SSL/TLS.
- **Backup/restore, HA, compaction, plugin/extension** theo Core/Enterprise.

Không suy luận mọi Flux query từ InfluxDB 2 tự chạy nguyên trạng trên InfluxDB 3.

### 12.3. Line protocol minh họa

Một điểm đo InfluxDB line protocol có dạng:

~~~text
temperature,site=factory-2,deviceId=sensor-17 temperatureC=28.4,humidityPercent=67.2
~~~

Đây là **ví dụ line protocol không kèm explicit timestamp** (server có thể gán thời điểm ghi theo semantics của write API). Khi gửi telemetry thực, nên định nghĩa timestamp precision, clock synchronization, retry/deduplication và xử lý late-arriving data. Các ví dụ chỉ minh họa cú pháp dữ liệu, không phải lệnh truy cập production.

### 12.4. Tránh tag cardinality bùng nổ

**Cardinality** là số series hoặc tổ hợp tag values có thể xuất hiện theo engine/schema. Nếu đặt một tag duy nhất cho **requestId** của hàng tỷ requests, cardinality có thể tăng cực nhanh, làm index/cache/memory/cost tăng. Các tags như region/service/device thường hữu ích, nhưng vẫn phải đo thực tế. **Raw requestId** có thể thích hợp hơn ở logs/traces/S3 thay vì là một time-series tag phân nhóm.

Ví dụ:

| Tag | Cardinality xấp xỉ | Cân nhắc |
|---|---|---|
| **region** | 3–20 | Thường kiểm soát được |
| **service** | 20–500 | Có thể phù hợp cho aggregation |
| **deviceId** | 100.000+ | Cần sizing với high-cardinality workload |
| **requestId** | Hàng triệu/ngày | Rủi ro cardinality lớn, không nên dùng tùy tiện |

**Không có ngưỡng cardinality chung cho mọi time-series engine**. Dùng benchmark với lượng tags, retention, write throughput, query shape và instance size giống production.

## 13. Timestream for LiveAnalytics: trạng thái sản phẩm quan trọng

**Amazon Timestream for LiveAnalytics** là một dịch vụ time-series analytics trước đây được dùng rộng rãi để ingest, lưu và truy vấn dữ liệu timestamped với **memory/magnetic storage tiers** và các chức năng retention/scheduled queries theo tài liệu của dịch vụ.

**Cập nhật về lựa chọn dịch vụ:** AWS đã **đóng quyền truy cập Timestream for LiveAnalytics cho khách hàng mới từ ngày 20/06/2025**. Những khách hàng hiện hữu đủ điều kiện với payer account đã dùng dịch vụ có thể tiếp tục vận hành/đăng ký users hoặc linked accounts theo thông báo AWS. Đối với **khách hàng mới**, AWS khuyến nghị đánh giá **Amazon Timestream for InfluxDB**, và phiên bản **InfluxDB 3** phù hợp với nhiều workload analytics hiện đại.

| Tình huống | Khuyến nghị |
|---|---|
| **Ứng dụng time series mới, tài khoản chưa từng dùng LiveAnalytics** | **Không thiết kế phụ thuộc LiveAnalytics mới**; đánh giá InfluxDB 3 Core/Enterprise và lựa chọn khác |
| **Hệ thống hiện có đang dùng LiveAnalytics** | Có thể tiếp tục theo điều kiện AWS; rà soát support, quota, retention, lifecycle và migration readiness |
| **Cần long-term analytics với compression/historical queries** | Đánh giá **InfluxDB 3 Enterprise** hoặc S3/Parquet/Athena theo SLO |
| **Chỉ cần dashboard metrics mới nhất trong vài ngày** | Cân nhắc **InfluxDB 3 Core** nếu single-node availability phù hợp |
| **Cần CloudWatch application metrics/alerts** | Xem **Amazon CloudWatch** trước khi tự vận hành một time-series DB khác |

**Không coi LiveAnalytics và InfluxDB là hai tên gọi của cùng API.** Chúng có **ingestion/query APIs, IAM/auth, pricing và migration semantics khác nhau**. Khi chuyển từ LiveAnalytics, phải xây **data export/backfill, query translation, retention và validation**; không chỉ thay endpoint.

### 13.1. Khi nào S3/Athena hoặc OpenSearch hợp hơn?

| Workload | Thường nên đánh giá |
|---|---|
| **Observability metrics/alarms** sẵn trong AWS | CloudWatch metrics/alarms, exporter pipeline nếu cần |
| **Raw events giữ nhiều năm, query vài lần mỗi tháng** | S3 Parquet partitioned + Athena |
| **Full-text log search và exploratory log dashboards** | OpenSearch / CloudWatch Logs Insights |
| **High-throughput timestamped measurements, last-value, windows** | Timestream for InfluxDB phù hợp SLO |

Một hệ thống thường dùng **Timestream for InfluxDB cho near-real-time queries** và **S3 cho dữ liệu lịch sử dài hạn**. Cần thống nhất timestamps, retention, data ownership và replay pipeline để tránh kết quả không khớp.

## 14. Kiến trúc kết hợp: một source of truth, nhiều read models

Ví dụ một marketplace vận hành theo mô hình **polyglot persistence**:

~~~mermaid
flowchart TD
    USER["Web / Mobile / Partner API"] --> API["Java API<br/>Lambda / ECS"]
    API --> MAIN["Aurora / DynamoDB<br/>Orders & user source of truth"]
    API --> CACHE["ElastiCache Valkey<br/>Product/session hot reads"]
    API --> DOC["DocumentDB<br/>Flexible catalog projection"]
    MAIN --> OUTBOX["Transactional outbox<br/>hoặc DynamoDB Streams / CDC"]
    OUTBOX --> BUS["EventBridge / SQS / Kinesis"]
    BUS --> PROJECT["Idempotent projection workers"]
    PROJECT --> CACHE
    PROJECT --> DOC
    PROJECT --> GRAPH["Neptune Database<br/>User-device-payment links"]
    BUS --> TS["Timestream for InfluxDB<br/>Operational metrics"]
    BUS --> ARCHIVE["S3 Parquet<br/>Immutable event archive"]
    GRAPH --> ANALYTICS["Neptune Analytics<br/>Fraud graph algorithms"]
    ANALYTICS --> API
~~~

### 14.1. Vì sao không ghi trực tiếp năm database trong một HTTP transaction?

Một API cố gắng ghi cùng một event vào Aurora, cache, DocumentDB, Neptune và time-series DB **không có distributed transaction chung tự động**. Nếu ghi thứ ba lỗi, hệ thống có thể bị lệch dữ liệu. Thay vào đó:

1. Ghi **business transaction** vào source of truth.
2. Phát event bằng **transactional outbox, DynamoDB Streams hoặc CDC** tùy nguồn dữ liệu.
3. Gửi event vào **EventBridge/SQS/Kinesis** với retries, DLQ, schema version.
4. Các projection workers cập nhật DocumentDB, Neptune, cache hoặc time-series DB theo **idempotency key**.
5. Ghi **lastProcessedEventId/version/timestamp** để đo **projection lag**.
6. Có khả năng **rebuild projections** từ event archive hoặc snapshot source.

**Eventual consistency phải được nói rõ với người dùng:** vừa cập nhật sản phẩm thành công tại source nhưng cache/catalog projection có thể chưa cập nhật. Nếu nghiệp vụ cần **read-your-writes**, API có thể đọc source theo session/version hoặc chờ projection đạt version đã commit.

### 14.2. Consistency policy cho từng lớp

| Dữ liệu | Nguồn chính | Bản dẫn xuất | SLA nhất quán |
|---|---|---|---|
| Giá/stock thực hiện checkout | Aurora/DynamoDB theo transaction design | Cache, catalog read model | Checkout đọc/cập nhật nguồn đáng tin, không dựa vào stale cache |
| Product description | Catalog DocumentDB hoặc source rõ ràng | ElastiCache/CDN | Có thể stale vài giây/phút tùy yêu cầu |
| Fraud relationships | Events/source graph cập nhật | Neptune/Neptune Analytics | Có lag, ghi rõ thời điểm cập nhật |
| Telemetry IoT | Stream/event archive hoặc time-series authoritative store | Aggregated dashboards | Late-arriving data/backfill được xử lý |
| User sessions | Theo contract durable/cache của hệ thống | Local cache | Expiry, logout/revocation và failover được thiết kế |

**Không đặt cùng một field có hai nơi được sửa độc lập mà thiếu cơ chế conflict resolution.** Chọn ownership rõ ràng cho giá, stock, status và rules; các projections chỉ nên được thay đổi thông qua events/commands đã định nghĩa.

### 14.3. Failure recovery và backfill

Nếu Neptune gặp sự cố trong 2 giờ, API orders vẫn có thể hoạt động khi graph là projection. Sau khi Neptune phục hồi, worker đọc **event backlog hoặc archive** và apply những updates còn thiếu; phải có **idempotency** để cùng event không tạo duplicate edges. Nếu time-series sink lỗi, lưu events trong SQS/Kinesis/S3 theo retention phù hợp, giám sát DLQ/iterator age và backfill.

**Không dựa vào TTL của SQS như backup dài hạn.** Với những dữ liệu cần rebuild được sau nhiều tháng, event archive ở S3 hoặc data source durable riêng phải có retention và chính sách bảo vệ.

## 15. Bảo mật và network cho bốn nhóm dữ liệu

### 15.1. Phân biệt IAM control plane với data plane

| Dịch vụ | Control plane authorization | Data plane authorization |
|---|---|---|
| **ElastiCache** | IAM tạo/sửa/xóa cluster/cache | Valkey/Redis ACL, AUTH/TLS hoặc cơ chế IAM-auth hỗ trợ theo engine/config; Memcached theo engine networking/security |
| **MemoryDB** | IAM quản lý cluster/users/ACL | Database ACL/users, TLS, credentials theo cơ chế engine |
| **DocumentDB** | IAM Create/Describe/Modify cluster | MongoDB-compatible database users/roles, TLS |
| **DynamoDB** | IAM AWS APIs | IAM GetItem/Query/UpdateItem trên table/index, conditions |
| **Neptune Database** | IAM quản lý DB resources | IAM database authentication khi được bật, graph endpoint/query permissions |
| **Timestream for InfluxDB** | IAM quản lý instances/clusters | InfluxDB auth tokens/users, TLS/network theo phiên bản/edition |

**IAM quyền tạo ElastiCache không tự cho phép GET một cache key.** Tương tự, **rds:DescribeDBClusters** cho DocumentDB/Neptune không phải quyền query data plane. Thiết kế rõ **principal của Java app** và phương thức authentication của database engine.

### 15.2. VPC, security groups và TLS

- Đặt databases/cache trong **private subnets** và security groups chỉ cho phép traffic từ **application security group** hoặc nguồn được duyệt.
- Sử dụng **TLS in transit** và **at-rest encryption** theo hỗ trợ từng engine/version, quản lý certificates và key policy.
- Không bật public access hoặc mở **0.0.0.0/0** cho database ports vì muốn test nhanh.
- Với Lambda/ECS/EKS trong VPC, kiểm tra **subnet placement, DNS, NAT/VPC endpoints, IP capacity, network routing** và **connection pooling**.
- Đối với time-series ingestion từ IoT/internet, nên dùng một **ingestion API/gateway có auth và rate limiting**, không mặc định mở trực tiếp DB endpoint ra Internet.
- Tách quyền admin, application read/write và read-only analytics; ghi lại ownership, resource ARNs, secrets và rotation policy.

### 15.3. Quản lý secrets và authentication

**AWS Secrets Manager** giúp lưu, rotate credentials của các database engines được hỗ trợ; một số dịch vụ có user/ACL/secret management riêng. Với Java application:

1. Dùng **Lambda execution role, ECS task role, EKS Pod Identity/IRSA hoặc EC2 instance profile**.
2. Cấp **secretsmanager:GetSecretValue** chỉ trên secret được phép; thêm **kms:Decrypt** nếu customer managed key và policy yêu cầu.
3. Lấy secret qua cache có **TTL/refresh-on-failure** và không log password/token.
4. Đảm bảo **TLS verification** và không tắt certificate validation để “sửa timeout”.
5. Đổi secrets/ACL theo maintenance plan, kiểm tra reconnect/failover.

**IAM database authentication** của Aurora/RDS không áp dụng tự động cho DocumentDB/Neptune/Valkey/InfluxDB. Mỗi engine có đường auth riêng; luôn đọc tài liệu data plane phù hợp.

### 15.4. Mã hóa, KMS và dữ liệu dẫn xuất

KMS keys của nguồn RDS/Aurora, DocumentDB, Neptune, backups, S3 archive và Secrets Manager **có thể là những keys khác nhau**. Không cấp **kms:* cho mọi application role**. Database managed storage encryption thường do dịch vụ sử dụng key theo grants/policy; Java app không cần trực tiếp kms:Decrypt storage key chỉ để truy vấn data đã được DB cho phép.

**Data minimization:** các graph nodes, cache keys, logs, tags time series và object names có thể chứa dữ liệu nhạy cảm ngoài data body; tránh dùng email/số thẻ/ngày sinh dạng rõ trong key/tag. Dùng internal IDs, tokenize/salt/hash theo threat model và quyền truy cập phù hợp.

## 16. Availability, consistency, backup và recovery

| Dịch vụ | Chú ý HA/replication | Backup/recovery và consistency |
|---|---|---|
| **ElastiCache Valkey/Redis OSS** | Shards, replicas, Multi-AZ/failover theo deployment | Cache rebuild hoặc durable mode/snapshots theo engine/version |
| **ElastiCache Memcached** | Phân phối keys across nodes; khả năng mất cache khi node failure | Thiết kế cache miss recovery, không coi là durable DB |
| **MemoryDB** | Multi-AZ durable log/replication theo tính năng | Backups, point-in-time considerations, RPO/RTO và active-active theo mode |
| **DocumentDB** | Cluster/replica topology, failover | Backups/snapshots, engine consistency, read preference |
| **DynamoDB** | Managed availability trong Region | PITR, on-demand backup, Global Tables nếu cần Multi-Region |
| **Neptune Database** | Multi-AZ instances/serverless deployment theo tính năng | Continuous backup/snapshots, reader endpoint, graph versioning |
| **Neptune Analytics** | Graph lifecycle/analytics capacity | Khả năng reload data từ Neptune/S3 và bảo vệ kết quả |
| **Timestream for InfluxDB 3** | Core single node; Enterprise multi-node HA theo config | Backups, S3 persistence/compaction theo engine, thử restore |

### 16.1. Tính nhất quán phải đo theo query cụ thể

Một document replica có thể đọc chậm hơn writer. Cache có TTL có thể trả stale data. Một graph update qua event queue có thể có lag. Một time-series point có thể đến muộn, dẫn tới tổng hợp theo phút bị sửa khi query lại. **Không áp một từ “eventually consistent” cho tất cả**; phải xác định:

- Source write commit acknowledgment có nghĩa gì?
- Read sau write có cần thấy ngay không?
- Có replica lag, cache invalidation lag hoặc stream processing lag không?
- Sau failover, retry có làm duplicated side effects không?
- Có thể rebuild từ snapshot/event log và kiểm tra RPO/RTO không?

### 16.2. Thử lỗi thay vì chỉ cấu hình HA

Thực hành failover/restart/rescale trong staging: quan sát p95/p99, error rate, connection retries, DNS refresh, cache miss burst và keyspace. Với document/graph/time-series, thử restore từ snapshot/backups và xác minh **schema, indexes, grants, data integrity**. Multi-AZ không đồng nghĩa **automatic Multi-Region disaster recovery**.

## 17. Hiệu năng, sizing và chi phí: xây bằng phép đo

### 17.1. Khác nhau giữa cache capacity và database capacity

**ElastiCache:** memory working set, average key/value size, eviction, hot keys, throughput, replication, ECPUs/serverless hoặc node size quyết định chi phí. **DocumentDB:** document/index size, query plans, reader/writer instances, IO và cluster topology. **Neptune:** số nodes/edges, traversal depth, query cardinality, graph instance capacity. **InfluxDB:** points/second, tag cardinality, time range, downsampling, query concurrency, retention và compaction.

| Dịch vụ | Sizing variable cần đo | Tình huống làm chi phí tăng bất ngờ |
|---|---|---|
| **ElastiCache** | Hot key count, average value, hit ratio, eviction, network bytes, ECPUs/node count | Cache toàn bộ DB nhưng ít hit, key churn, overprovisioned nodes |
| **MemoryDB** | Working set + persistence/replication, write rate, replicas | Giữ mọi transient event trong expensive in-memory primary |
| **DocumentDB** | Document/index sizes, aggregation/scan, replicas, I/O | Ad hoc queries không có index, writes gây index amplification |
| **DynamoDB** | RCU/WCU hoặc on-demand requests, item size, GSIs, hot partitions | Scans, GSIs không cần, item lớn, retry/throttling |
| **Neptune Database** | Vertices/edges, degrees, query depth, NCUs/instances | Traversals không giới hạn, graph scans, oversizing |
| **Neptune Analytics** | Graph load size, algorithm count, runtime/capacity | Duy trì graph analytics capacity khi không chạy jobs |
| **Timestream for InfluxDB** | Ingest points, tag cardinality, retention, node topology/storage | Tag series explosion, quá nhiều tiny writes/queries, historical retention không có policy |
| **S3 + Athena** | Storage bytes, scan bytes, requests/queries | CSV không partition/Parquet, mỗi query scan toàn bộ lịch sử |

### 17.2. Hiệu năng p95/p99 quan trọng hơn benchmark mẫu

Một hệ thống cache có **average read = 1 ms** nhưng **p99 = 300 ms** khi eviction hoặc CPU contention có thể vi phạm SLO. DocumentDB với query median tốt nhưng query **$lookup/aggregation** có p99 cao cần xem **index/query plans**. Neptune traversals có cost phụ thuộc **node degree, path length, filtering**; time-series queries có cost phụ thuộc **tag selectivity và time-range scan**.

Hãy benchmark với:

- Phân phối key/document/edge/series giống production, bao gồm **hot keys/hot vertices/hot partitions**.
- Read/write ratio, burst traffic, retry rate, failover/rebalance.
- Dữ liệu đủ lớn để vượt working set/cache và mô phỏng retention thật.
- Tham số serverless/node, AZ topology, instance class, versions và security configs thực.
- So **p50/p95/p99, errors, throttles, cost per 1.000 requests hoặc cost per GB stored/year**, không chọn theo peak benchmark marketing.

### 17.3. Chi phí không chỉ là giá database

**TCO = phí dịch vụ + data storage + replication/backups + network + logs/metrics + migration/development + on-call incidents.**

Ví dụ 1: thêm cache có thể tăng hóa đơn ElastiCache nhưng **giảm RDS reads** và giúp giảm DB class. Ví dụ 2: tách DocumentDB khỏi Aurora có thể làm truy vấn catalog nhanh hơn nhưng cần **CDC pipeline, SQS, DLQ, data consistency monitor**. Ví dụ 3: dùng Neptune cho một JOIN đơn giản có thể tăng chi phí và complexity mà không có lợi ích.

**Không gán đơn giá cố định** vì AWS pricing khác theo Region, engine version, serverless/node mode, resource size và thời gian. Dùng **AWS Pricing Calculator** và số liệu thực nghiệm để chọn.

## 18. Thực hành Java: cache-aside an toàn với source of truth

Ví dụ dưới dùng các interfaces tự định nghĩa để tập trung vào logic; **không phải code có thể compile độc lập** nếu chưa có Product, CacheClient, ProductRepository và JSON serialization implementations. Các nguyên tắc áp dụng cho Java service dùng ElastiCache và Aurora/DynamoDB.

~~~java
import java.time.Duration;
import java.util.Optional;
import java.util.concurrent.ThreadLocalRandom;

public final class ProductReadService {
    private final CacheClient cache;
    private final ProductRepository repository;

    public ProductReadService(CacheClient cache, ProductRepository repository) {
        this.cache = cache;
        this.repository = repository;
    }

    public Optional<Product> findProduct(String productId) {
        // Không dùng email/PII làm tên key.
        String cacheKey = "product:v4:" + productId;

        try {
            Optional<Product> hit = cache.getProduct(cacheKey);
            if (hit.isPresent()) {
                return hit;
            }
        } catch (RuntimeException cacheError) {
            // Cache là lớp tối ưu: ghi metric cảnh báo, fallback có giới hạn.
            recordCacheFailure();
        }

        // Repository là source of truth của sản phẩm.
        Optional<Product> product = repository.findById(productId);

        if (product.isPresent()) {
            // TTL jitter để tránh nhiều keys cùng hết hạn.
            long ttlSeconds = 120 + ThreadLocalRandom.current().nextLong(0, 30);
            try {
                cache.putProduct(cacheKey, product.get(), Duration.ofSeconds(ttlSeconds));
            } catch (RuntimeException cacheError) {
                recordCacheFailure();
            }
        }

        return product;
    }

    public void updateProduct(Product product) {
        repository.updateTransactional(product);
        // Chỉ invalidate sau khi source-of-truth commit thành công.
        cache.delete("product:v4:" + product.id());
    }

    private void recordCacheFailure() {
        // Thay bằng Micrometer/CloudWatch metric/log đã redaction.
    }
}
~~~

**Điểm đúng:** đọc cache trước, fallback DB sau cache miss, TTL có jitter, cập nhật DB trước rồi invalidation cache, tách cache failures khỏi quyền truy cập dữ liệu gốc. **Điểm còn thiếu để production:** cache timeout, bounded retry/circuit breaker, single-flight per key, negative caching hợp lý, idempotent invalidation, xử lý race giữa read/update, authentication/TLS, schema versioning và tracing.

### 18.1. Cache invalidation race condition

Ví dụ:

1. Request A miss cache, đọc giá cũ từ DB nhưng chưa set cache.
2. Request B cập nhật giá mới và xóa cache key.
3. Request A đến trễ, ghi **giá cũ** vào cache với TTL 120 giây.

**Chỉ “DB update rồi DEL cache” chưa đủ để loại bỏ mọi stale-write race.** Với giá/stock quan trọng, có thể sử dụng **version numbers, conditional cache writes, compare-and-set, event sequence checks**, hoặc không đọc cache khi ra quyết định checkout. Chọn sự phức tạp theo mức độ consistency yêu cầu.

### 18.2. Negative caching và dữ liệu không tồn tại

Nếu một productId không tồn tại và traffic cao, cache tạm một **not-found marker** với TTL ngắn có thể giảm DB reads. Nhưng khi product mới được tạo, cần invalidate marker; không để missing ID được cache vô hạn. Tránh cache lỗi 403 như “not found” chung cho mọi user vì có thể làm lộ dữ liệu hoặc che quyền khác nhau.

### 18.3. Không dùng cache làm distributed lock một cách tùy tiện

Một lệnh **SET NX EX** có thể hữu ích cho short-lived coordination, nhưng việc dựa trên lock đó để bảo đảm **exactly-once payment** là nguy hiểm nếu process pause, lease hết hạn, failover hoặc network split. Với giao dịch quan trọng, dùng **conditional writes/transactions** ở source of truth và idempotency keys. Cache lock chỉ nên là một phần của hợp đồng concurrency đã phân tích.

## 19. AWS CLI: kiểm kê dịch vụ mà không thay đổi tài nguyên

Những lệnh dưới đây **chỉ đọc metadata**. Chúng không kết nối trực tiếp đến data plane và **không chứng minh** user/password/ACL có thể truy vấn dữ liệu. Thay Region và tên tài nguyên theo môi trường thật, dùng IAM role đọc giới hạn. Cần AWS CLI v2 đủ mới để có các lệnh cho **Timestream for InfluxDB 3**.

### 19.1. Xác định caller, Region và ElastiCache

~~~bash
aws sts get-caller-identity --output json

# Node-based Valkey/Redis OSS replication groups.
aws elasticache describe-replication-groups \
  --region ap-southeast-1 \
  --output json

# ElastiCache Serverless (Valkey/Redis OSS/Memcached theo hỗ trợ).
aws elasticache describe-serverless-caches \
  --region ap-southeast-1 \
  --output json

# Memcached/other node-based cache clusters metadata.
aws elasticache describe-cache-clusters \
  --region ap-southeast-1 \
  --output json
~~~

Đọc **Engine, EngineVersion, CacheNodeType, Status, cluster/shard/replica count, endpoint, TLS/at-rest encryption flags** theo loại tài nguyên. **DescribeReplicationGroups** dành cho Valkey/Redis OSS, không thay thế **DescribeCacheClusters** cho Memcached. Một cluster tồn tại không bảo đảm app có quyền **GET/SET**: cần kiểm tra engine ACL/auth và network.

### 19.2. MemoryDB

~~~bash
aws memorydb describe-clusters \
  --region ap-southeast-1 \
  --output json

aws memorydb describe-acls \
  --region ap-southeast-1 \
  --output json
~~~

Đọc metadata cluster, node/shard, engine, endpoints, ACL và encryption, không xuất passwords. Trước khi dùng như durable primary, cần xác minh **backup/restore, replication và dữ liệu sau failover** bằng thử nghiệm có kiểm soát.

### 19.3. DocumentDB và DynamoDB

~~~bash
# DocumentDB clusters and engine versions.
aws docdb describe-db-clusters \
  --region ap-southeast-1 \
  --output json

# DynamoDB: inspect a table's key schema and indexes.
aws dynamodb describe-table \
  --region ap-southeast-1 \
  --table-name products \
  --query 'Table.{Name:TableName,Status:TableStatus,KeySchema:KeySchema,GSIs:GlobalSecondaryIndexes}' \
  --output json
~~~

**Không đọc collections/table rows trong bước kiểm kê** nếu không có mục đích và quyền phù hợp. DocumentDB là **DB data plane** với MongoDB-compatible users/TLS; DynamoDB dùng AWS IAM APIs. Kiểm tra IAM và VPC endpoints riêng, không dùng một loại access key chung cho mọi engine.

### 19.4. Neptune Database

~~~bash
aws neptune describe-db-clusters \
  --region ap-southeast-1 \
  --filters Name=engine,Values=neptune \
  --output json
~~~

Neptune Database có thể dùng provisioned hoặc serverless capacity theo cấu hình. Xác minh **graph model/query language, cluster endpoints, authentication mode, backup/reader topology và KMS**. Các lệnh AWS CLI chỉ trả configuration; để đánh giá đồ thị phải query bằng **Gremlin/openCypher/SPARQL** qua data plane đã cấp quyền.

### 19.5. Timestream for InfluxDB

~~~bash
# InfluxDB 3 cluster-based resources.
aws timestream-influxdb list-db-clusters \
  --region ap-southeast-1 \
  --output json

# InfluxDB instance-based resources.
aws timestream-influxdb list-db-instances \
  --region ap-southeast-1 \
  --output json
~~~

Trước khi tạo mới phải kiểm tra **AWS Region availability, EngineVersion, Core/Enterprise edition, cluster configuration, authentication, TLS, subnet groups, storage và pricing**. Control plane CLI không dùng thay InfluxDB query API/line protocol của data plane.

### 19.6. Quy trình read-only tốt

1. Xác minh caller IAM role/account và Region, tránh nhầm môi trường test/prod.
2. Đọc metadata: engine/version, serverless/node deployment, endpoints, encryption, HA, backup.
3. Đọc metrics/alarms và cost allocation tags bằng quyền được cấp.
4. Chỉ thử truy vấn dữ liệu với **read-only application principal** trong staging; không đưa dữ liệu nhạy cảm vào CLI logs.
5. Lưu bản đánh giá service choice và dependency contracts, không tự sửa cluster để “thử xem”.

## 20. Chẩn đoán sự cố theo từng mô hình

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| Cache hit ratio thấp | TTL quá ngắn, key schema lệch, working set lớn | Cache hits/misses, key distribution, request traces |
| Cache DB overload khi hết TTL | Cache stampede, đồng loạt expired | Single-flight, TTL jitter, DB connections, fallback limiter |
| Cache trả giá cũ | Thiếu invalidation, race giữa read và update | Key version, event delivery, source commit time |
| ElastiCache serverless client không kết nối | Client không hỗ trợ cluster mode, TLS/SG/DNS sai | Engine/client compatibility, endpoint, VPC |
| Cache bị eviction/OOM | Memory working set vượt capacity, hot keys | Evictions, memory utilization, key sizes/policy |
| MemoryDB write latency tăng | Durable write overhead/replication/capacity pressure | Node metrics, throughput, replicas, network |
| DocumentDB query chậm | Thiếu indexes, aggregation lớn, scan | Explain/query profiler, index stats, document sizes |
| MongoDB app không chạy trên DocumentDB | Unsupported command/operator, driver, retryable writes | Compatibility matrix đúng engine version |
| DynamoDB throttling | Hot partition, WCU/RCU/GSI capacity | Partition-key distribution, throttling metrics |
| Neptune traversal timeout | Dense vertices, không giới hạn depth/path, query plan | Query profile, traversal expansion, graph schema |
| Graph results bị thiếu | Projection events bị lag/fail hoặc schema mapping sai | Event backlog, lastProcessedEventId, DLQ |
| Neptune Analytics run quá lâu | Graph quá lớn hoặc algorithm/capacity chưa phù hợp | Graph size, algorithm, analytic capacity |
| InfluxDB ingestion chậm | Tiny writes, high cardinality, node capacity | Write batches, tags cardinality, CPU/memory |
| InfluxDB Core query historical chậm | Thiếu compaction/edition không hợp long-term | Retention, Core/Enterprise, old data sizes |
| LiveAnalytics không tạo được trong tài khoản mới | Dịch vụ đã đóng cho new customers từ 20/06/2025 | AWS availability notice, chọn InfluxDB |
| Multi-store không nhất quán | CDC/outbox stream lag, consumer lỗi | Source version, event DLQ, projection checkpoint |
| Data decrypt lỗi sau restore | KMS key thiếu quyền hoặc đã disabled | Key state/policy, backup encryption, account/Region |
| Chi phí tăng bất ngờ | Extra replicas, indexes, high cardinality, queries, logs | Cost Explorer, per-service metrics, tag costs |

### 20.1. Runbook chẩn đoán nhanh

~~~mermaid
flowchart TD
    A["SLO violation / dữ liệu không đúng"] --> CLASS{"Nguồn lỗi thuộc loại nào?"}
    CLASS -->|"Cache miss/stale"| C["Kiểm tra hit ratio,<br/>TTL, hot key, invalidation"]
    CLASS -->|"Document query"| D["Query plan/index,<br/>schema, driver/version"]
    CLASS -->|"Graph traversal"| G["N-hop depth, degree,<br/>projection lag, IAM"]
    CLASS -->|"Time-series"| T["Tags/cardinality,<br/>retention, node/compaction"]
    CLASS -->|"Network/auth"| S["VPC SG, TLS,<br/>data-plane ACL, KMS/secret"]
    C --> FIX["Sửa một nguyên nhân có đo lường"]
    D --> FIX
    G --> FIX
    T --> FIX
    S --> FIX
    FIX --> VERIFY["Load test + correctness<br/>p95/p99 + cost + rollback"]
~~~

Khi sự cố xảy ra:

1. Xác định **service/Region/engine/version** và endpoint, lấy **caller IAM identity** thực.
2. Đọc error code, traceId/correlationId và metrics **latency, errors, capacity, connection counts**.
3. Phân biệt **authentication/network/KMS** với **data/query/model**; đừng tăng IAM permissions để chữa index scan.
4. Đối chiếu source of truth và read model, ghi nhận **last-known-good record version**.
5. Với cache outage, bảo vệ DB gốc bằng **fallback rate limits**, không cho tất cả clients truy vấn DB đồng thời.
6. Với projection lag, tạm hiển thị trạng thái “đang cập nhật” hoặc đọc nguồn có thẩm quyền theo nghiệp vụ.
7. Sửa ở staging, kiểm chứng request/quota/cost và plan rollback, rồi mới thay production.

### 20.2. Backup/restore không chỉ là thấy nút “Automated backup”

Hãy diễn tập **restoring a backup**, mở kết nối bằng role/credentials mới, kiểm tra sample queries, data counts, indexes và performance. Với graph/time-series, cần xác nhận file schema, sampling/retention, timestamp precision và các projections có thể được tạo lại. Với cache, thử mất toàn bộ nodes để xem database source chịu được **cold-cache traffic** hay không.

## 21. Bài tập tình huống ra quyết định

### Tình huống A — API đọc sản phẩm p99 cao

Ứng dụng Spring Boot lưu sản phẩm trong Aurora PostgreSQL. Traffic 15.000 requests/giây, 95% đọc, 5% cập nhật. Cùng một tập 20.000 sản phẩm được đọc lặp lại. P99 hiện vượt SLO vì database read load.

**Yêu cầu:** có nên chuyển toàn bộ sản phẩm sang DocumentDB, hay thêm cache?

**Gợi ý:** đầu tiên benchmark **ElastiCache for Valkey/Redis OSS** với cache-aside, TTL và invalidation sau commit, vì dữ liệu đã có source of truth và hot read patterns rõ. Đo hit ratio, DB fallback QPS, p95/p99 và total cost. Không di chuyển source sang DocumentDB chỉ để giải quyết read latency nếu query document đặc biệt không có.

### Tình huống B — Giỏ hàng có cần durable in-memory?

Một dịch vụ giỏ hàng lưu toàn bộ trạng thái trong một cache key-value thông thường, không có database hoặc event log khác. Khi cache bị failover, một số giỏ hàng mất dữ liệu và khách hàng phàn nàn.

**Yêu cầu:** ElastiCache và MemoryDB nên được đánh giá ra sao?

**Gợi ý:** giỏ hàng đang là **primary business state**. Cần một storage contract có durability, backup, HA và RPO/RTO rõ ràng. Đánh giá **MemoryDB**, các khả năng durability mới của **ElastiCache for Valkey** theo engine version, hoặc DynamoDB/Aurora làm source với cache phía trước. Đừng giải quyết bằng cách tăng TTL.

### Tình huống C — Catalog sản phẩm có cấu trúc biến đổi

Một marketplace có các ngành electronics, furniture, clothing. Mỗi ngành có hàng chục trường đặc thù và admin cần nhiều filters trên nested attributes, aggregation theo seller/category; application trước đây dùng MongoDB.

**Yêu cầu:** DocumentDB hay DynamoDB?

**Gợi ý:** **DocumentDB** phù hợp để thử nếu cần MongoDB-compatible driver và rich document queries. Phải kiểm tra **engine/API compatibility, indexes, aggregation operators, query plans**. Nếu API thực tế chỉ GetByProductId và QueryBySellerId với access patterns ổn định, **DynamoDB** có thể đơn giản hơn. Nếu ứng dụng có SQL transactions và metadata JSON không phức tạp, thử Aurora PostgreSQL JSONB trước khi thêm DB mới.

### Tình huống D — Dùng DynamoDB Scan cho mọi bộ lọc

Một service lưu catalog dưới dạng DynamoDB Map/List, nhưng frontend cho phép lọc bất kỳ thuộc tính nào, backend liên tục **Scan + FilterExpression** qua hàng triệu items. Chi phí và latency tăng mạnh.

**Yêu cầu:** có thể chỉ tăng read capacity để sửa không?

**Gợi ý:** FilterExpression sau Scan không biến thành index query. Hãy phân tích tần suất bộ lọc, thiết kế **GSIs/materialized read models**, hoặc đánh giá DocumentDB/OpenSearch cho nhu cầu query/search khác. Tăng capacity có thể che triệu chứng nhưng không thay bản chất access pattern.

### Tình huống E — Phát hiện fraud ring qua nhiều lớp quan hệ

Hàng triệu users có quan hệ **USES device**, **PAID_WITH card token**, **REFERRED user**. Risk team muốn tìm accounts nối với một fraud account qua tối đa bốn hops, xem đường đi và các nhóm cộng đồng bất thường.

**Yêu cầu:** SQL joins, Neptune Database hay Neptune Analytics?

**Gợi ý:** thử **Neptune Database** cho online N-hop traversal trả về quyết định tại thời điểm order. Dùng **Neptune Analytics** cho community detection/centrality theo lịch hoặc điều tra. Chỉ cần SQL khi graph nhỏ và query có số joins hạn chế. Đo degree distribution, latency, projection freshness, IAM và thời gian backfill.

### Tình huống F — Metrics IoT với số series tăng nhanh

50.000 sensors gửi telemetry mỗi 5 giây. Mỗi điểm có **deviceId, location, firmwareVersion, requestId**. Yêu cầu dashboard time-window và retention 12 tháng, báo cáo hàng năm.

**Yêu cầu:** chọn time-series store và phân loại tags.

**Gợi ý:** đánh giá **Timestream for InfluxDB 3 Enterprise** nếu cần HA, compaction/historical queries; S3 Parquet/Athena cho archive dài hạn. Tag **deviceId** cần sizing high cardinality, nhưng **requestId** có thể gây series explosion nếu dùng làm tag. Dùng batching, timezone/precision, downsampling, retention và backfill.

### Tình huống G — Nhóm mới muốn tạo Timestream LiveAnalytics

Một dự án mới năm 2026 định chọn **Timestream for LiveAnalytics** vì một bài blog cũ hướng dẫn SQL queries và memory/magnetic tiers.

**Yêu cầu:** kế hoạch lựa chọn nên thay đổi thế nào?

**Gợi ý:** AWS đóng new-customer access từ **20/06/2025**. Không đặt kiến trúc mới vào một dịch vụ không mở cho tài khoản mới. Đánh giá **Timestream for InfluxDB 3** (Core/Enterprise theo retention/HA), CloudWatch/OpenSearch cho observability hoặc S3/Athena cho historical analytics, và kiểm tra Region/pricing hiện hành.

### Tình huống H — Cache invalidation xảy ra sau DB commit nhưng vẫn stale

Request A đọc giá cũ từ DB sau cache miss; request B ghi giá mới và xóa cache; request A ghi lại giá cũ vào cache sau B.

**Yêu cầu:** tại sao “write DB rồi DEL cache” chưa đủ?

**Gợi ý:** do race giữa read miss và cập nhật. Có thể dùng **versioned cache entries**, conditional set theo version, cập nhật event có sequence, hoặc tránh dùng cache cho giá khi checkout. Đo và định nghĩa stale tolerance theo nghiệp vụ, không hứa strong consistency cho cache-aside chỉ bằng TTL.

### Tình huống I — Projection graph không theo kịp sự kiện

Source of truth ghi user-device relationships đúng, nhưng worker nhận events qua SQS bị lỗi ba giờ. Online fraud API vẫn đọc Neptune như thể dữ liệu đầy đủ, nên bỏ sót nhiều liên kết mới.

**Yêu cầu:** điều phối khôi phục như thế nào?

**Gợi ý:** monitor **event lag/lastProcessedEventId**, DLQ và worker errors, có bounded retry/backpressure. Khi graph chưa đạt freshness SLO, API phải phân biệt kết quả unknown/stale; sau sửa lỗi, replay từ event archive và kiểm tra **idempotent edge updates**. Không tuyên bố kết quả graph luôn phản ánh nguồn ngay lập tức.

### Tình huống J — Cache mất trong giờ cao điểm

ElastiCache gặp failure khiến 30.000 requests/giây chuyển sang Aurora, database hết kết nối và API bắt đầu timeout.

**Yêu cầu:** bảo vệ hệ thống thế nào?

**Gợi ý:** cache là lớp tăng tốc nhưng backend cần **fallback limiter, request coalescing, warm-up, circuit breaker, read replicas/DB capacity** phù hợp. Dự đoán **cold-cache traffic** khi capacity planning; thử chaos/failover và alert theo cache hit ratio, DB connections, errors, p99.

### Tình huống K — MongoDB driver chạy nhưng aggregation sai

Nhóm dùng DocumentDB với code MongoDB đã migration. CRUD cơ bản chạy, nhưng một aggregation pipeline khác kết quả và các retryable writes báo lỗi theo engine version.

**Yêu cầu:** có phải dữ liệu bị mất do network không?

**Gợi ý:** không kết luận trước. Đối chiếu **DocumentDB compatibility matrix, functional differences, engine version, retryable writes support**, indexes và ordering. Kiểm thử correctness/query plans trên data thật, không coi MongoDB wire protocol compatibility là tương thích hành vi tuyệt đối.

### Tình huống L — Muốn dùng một database cho mọi thứ

Một startup muốn dùng ElastiCache cho cache, orders, document catalog, fraud relationships và metrics, với lý do tất cả “đều có thể lưu ở key-value”.

**Yêu cầu:** phản biện bằng decision matrix.

**Gợi ý:** có thể lưu biểu diễn dữ liệu nhưng không chắc query/consistency/durability/cost phù hợp. Phân loại **source of truth**, access patterns, multi-step graph traversals, time-window queries và backup requirements. Bắt đầu **đơn giản nhất** đáp ứng SLO, chỉ thêm specialized database khi benchmark chứng minh lợi ích; nếu in-memory store là primary, cần hợp đồng durability rõ ràng.

## 22. Checklist production khi lựa chọn database chuyên dụng

- [ ] Đã viết **top 5–10 access patterns**, không chọn dịch vụ chỉ theo data format.
- [ ] Đã xác định **source of truth**, read models, dữ liệu dẫn xuất và owner của từng trường.
- [ ] Đã định nghĩa **p95/p99, throughput, consistency, RPO/RTO, retention và data sensitivity**.
- [ ] Với cache, đã thử **cache-aside, TTL/invalidation, eviction, stampede, hot keys và cold-cache failure**.
- [ ] Đã chọn **ElastiCache Valkey/Redis OSS/Memcached** theo data structures/client/engine version.
- [ ] Đã so **serverless vs node-based** theo traffic, instance management, ECPUs/node hours và cost.
- [ ] Nếu dùng in-memory store làm **primary**, đã đánh giá **MemoryDB/ElastiCache durability** theo đúng engine/version và test recovery.
- [ ] Với documents, đã so **DocumentDB, DynamoDB và PostgreSQL JSONB** theo access patterns.
- [ ] Đã kiểm tra **DocumentDB MongoDB compatibility**, indexes, transactions, retryable writes và migration tests.
- [ ] Với graph, đã phân biệt **property graph/openCypher/Gremlin** và **RDF/SPARQL**.
- [ ] Đã chọn **Neptune Database** cho operational graph hoặc **Neptune Analytics** cho graph algorithms.
- [ ] Với time series, đã thiết kế timestamp precision, tags/fields, cardinality, retention, batching/downsampling.
- [ ] Với dự án mới, đã tránh phụ thuộc **Timestream for LiveAnalytics** khi new-customer access không còn.
- [ ] Đã chọn **InfluxDB 3 Core/Enterprise** theo recent-vs-historical data, HA/compaction và Region support.
- [ ] Đã kiểm tra khả năng thay thế bằng **S3/Parquet/Athena/OpenSearch/CloudWatch** khi phù hợp.
- [ ] Đã có **outbox/CDC/stream events, idempotency, projection lag alerts và backfill** khi dùng nhiều data stores.
- [ ] IAM/data-plane ACL, Secrets Manager, KMS, TLS, VPC/SG và least privilege đã được review.
- [ ] Đã test **multi-AZ/failover, backup/restore, key rotation, DNS/client reconnect** theo engine.
- [ ] Đã mô phỏng hot partitions, high-cardinality tags, dense graph vertices và long-tail query p99.
- [ ] Đã đo **cost per request/query/GB retained**, compute, replicas, logs, network và công vận hành.
- [ ] Có runbook rõ cho **cache outage, data lag, document query errors, graph traversal timeout, time-series ingestion backlog**.
- [ ] Đã xác định **migration rollback, schema/versioning và cutover plan** trước khi thay source of truth.

## 23. Ghi nhớ

**Cache** dùng để giảm latency/áp lực đọc bằng dữ liệu có thể refresh hoặc rebuild: chọn **ElastiCache** theo Valkey/Redis OSS/Memcached, serverless/node-based và chính sách TTL/invalidation. Nếu **in-memory là nguồn dữ liệu chính**, cần đánh giá **durability và consistency** thực tế của **MemoryDB** hoặc những cấu hình ElastiCache phù hợp — không chỉ nhìn tốc độ GET/SET.

**Document databases** như **DocumentDB** hợp với nested documents, rich filters và MongoDB-compatible APIs; **DynamoDB** phù hợp với những application data có **key/access patterns rõ ràng** dù có nested Map/List. **Graph databases** như **Neptune Database** hợp với many-hop relationship queries; **Neptune Analytics** hợp với thuật toán phân tích graph. **Time-series databases** như **Timestream for InfluxDB** hợp với timestamped measurements, time windows, retention và tag cardinality. **Timestream for LiveAnalytics không nhận khách hàng mới từ 20/06/2025**, nên kiến trúc mới phải tính tới lựa chọn đang được AWS hỗ trợ mở mới.

Một kiến trúc tốt thường **không cần nhiều database ngay từ đầu**. Dùng cơ sở dữ liệu đơn giản nhất đáp ứng workload, chỉ thêm cache/read models chuyên dụng khi có bằng chứng từ **SLO, query patterns, consistency, resilience và TCO**. Khi dùng nhiều data stores, phải thiết kế **source of truth, event delivery, idempotency, freshness và backfill** để dữ liệu không bị lệch.

### Tài liệu AWS chính thức để đối chiếu

- [AWS Decision Guide – Choosing an AWS database service](https://docs.aws.amazon.com/decision-guides/latest/decision-guides/databases-on-aws-how-to-choose.html) — chọn data model dựa theo access patterns.
- [Amazon ElastiCache – Choose engine](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/SelectEngine.html) — Valkey, Redis OSS và Memcached.
- [Amazon ElastiCache – Deployment options](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/WhatIs.deployment.html) — serverless và node-based.
- [Amazon ElastiCache – Related services/MemoryDB](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/related-services-choose-between-memorydb-and-redis.html) — so sánh cache và durable in-memory.
- [Amazon MemoryDB – Related services](https://docs.aws.amazon.com/memorydb/latest/devguide/related-services-choose-between-memorydb-and-redis.html) — database in-memory durable.
- [Amazon DocumentDB compatibility](https://docs.aws.amazon.com/documentdb/latest/devguide/compatibility.html) — MongoDB API/driver versions.
- [Amazon DocumentDB functional differences](https://docs.aws.amazon.com/documentdb/latest/devguide/functional-differences.html) — query/index/transaction differences.
- [Amazon DocumentDB migration runbook](https://docs.aws.amazon.com/documentdb/latest/devguide/docdb-migration-runbook.html) — kế hoạch migration và kiểm thử.
- [DynamoDB data types](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBMapper.DataTypes.html) — documents, Map/List và keys.
- [Accessing graph data in Amazon Neptune](https://docs.aws.amazon.com/neptune/latest/userguide/get-started-access-graph.html) — Gremlin, openCypher, SPARQL.
- [Neptune Database versus Neptune Analytics](https://docs.aws.amazon.com/neptune-analytics/latest/userguide/neptune-analytics-vs-neptune-database.html) — operational vs analytical graph.
- [Amazon Timestream for InfluxDB 3](https://docs.aws.amazon.com/timestream/latest/developerguide/influxdb3.html) — time-series engine, architecture và data model.
- [InfluxDB 3 Core and Enterprise](https://docs.aws.amazon.com/timestream/latest/developerguide/core-and-enterprise-versions.html) — compaction, HA và long-term data.
- [Timestream for LiveAnalytics availability change](https://docs.aws.amazon.com/timestream/latest/developerguide/AmazonTimestreamForLiveAnalytics-availability-change.html) — ngừng nhận khách hàng mới 20/06/2025.
- [Amazon ElastiCache pricing](https://aws.amazon.com/elasticache/pricing/), [Amazon MemoryDB pricing](https://aws.amazon.com/memorydb/pricing/), [Amazon DocumentDB pricing](https://aws.amazon.com/documentdb/pricing/), [Amazon Neptune pricing](https://aws.amazon.com/neptune/pricing/), [Amazon Timestream pricing](https://aws.amazon.com/timestream/pricing/) và [AWS Pricing Calculator](https://calculator.aws/) — kiểm soát chi phí theo Region/cấu hình.






