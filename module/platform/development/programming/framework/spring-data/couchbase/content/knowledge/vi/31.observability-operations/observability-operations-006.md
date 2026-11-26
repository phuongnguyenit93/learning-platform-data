# Quan sát tải chỉ mục, bộ nhớ, dung lượng và dịch vụ truy vấn

## 1. Bài toán vận hành: KV vẫn nhanh nhưng danh sách đơn hàng rất chậm

Một dịch vụ Spring Boot dùng **Spring Data Couchbase** có hai endpoint:

- `GET /orders/{id}` đọc document trực tiếp bằng `CouchbaseRepository.findById`.
- `GET /customers/{id}/orders` tìm Orders theo `customerId`, thường được thực thi bằng SQL++ qua **Query Service** và **Index Service**.

Khi lượng Order được tạo tăng, endpoint thứ hai có p99 từ mức bình thường tăng lên vài giây hoặc timeout, trong khi endpoint đọc theo ID vẫn phản hồi nhanh. Dashboard chỉ có “Couchbase UP”, memory của một node cao và disk usage gần đầy. Cần biết nguyên nhân nằm ở **tải cập nhật GSI, chi phí quét index, Query Service, quota bộ nhớ hay dung lượng lưu trữ** — và liệu các tín hiệu đó có thực sự liên quan hay chỉ trùng thời điểm.

Đây là chủ đề của bài **“Quan sát tải chỉ mục, bộ nhớ, dung lượng và dịch vụ truy vấn”**, thuộc chương **Quan sát và vận hành** của module **SPRING_DATA_COUCHBASE**. Module tập trung xây tầng truy cập Couchbase bằng document mapping, Repository, `CouchbaseTemplate` và SQL++, thiết kế bucket/scope/collection, index, TTL, CAS, transaction, reactive API và hoạt động ổn định dưới tải.

**Sau bài này, bạn có thể:**

1. Phân biệt Data Service, Query Service và Index Service; biết mỗi API phụ thuộc vào dịch vụ nào.
2. Đọc tín hiệu **tải cập nhật chỉ mục**, **tải truy vấn quét chỉ mục**, **backlog**, **residency/bộ nhớ**, **disk/storage** và **Query Service admission/latency**.
3. Hiểu vì sao “index online”, “memory còn dư” hay “KV UP” đều chưa đủ chứng minh SQL++ query đạt SLO.
4. Sử dụng `EXPLAIN`, metadata/metrics SQL++, danh sách active/completed requests và các dashboards dịch vụ để điều tra slow query.
5. Thiết kế Micrometer metrics và tracing cho Java SDK/Spring Data; tránh gán tên metric SDK/Server khi phiên bản chưa xác nhận.
6. Đưa ra kế hoạch cảnh báo, capacity, kiểm thử/benchmark và runbook ứng phó mà không kích hoạt vòng lặp retry hay DDL trong health probe.

> **Quy tắc:** Mỗi đường biểu đồ cần ghi rõ **dịch vụ**, **node/index/query shape**, **đơn vị**, **nguồn metrics**, **cửa sổ thời gian** và **phiên bản Couchbase** trước khi dùng làm bằng chứng.

## 2. Kiến trúc vận hành: một cluster, nhiều loại tải

~~~mermaid
flowchart LR
    APP["Spring Data Couchbase application"] --> SDK["Java SDK"]
    SDK --> KV[("Data Service: KV")]
    SDK --> Q[("Query Service: SQL++")]
    Q --> IDX[("Index Service: GSI scans")]
    Q --> KV
    KV -.-> DCP["Mutation stream / index maintenance"]
    DCP --> IDX
    SDK --> S[("Search, nếu dùng")]
    IDX --> STORAGE["Index storage + cache"]
    KV --> DATASTORAGE["Bucket Data storage"]
~~~

Đây là sơ đồ phụ thuộc khái niệm, không thay sơ đồ giao thức mạng/topology của phiên bản triển khai. Với **Global Secondary Index (GSI)**, có hai hướng tải lớn:

- **Write/update path:** mutation trên Data Service làm công việc duy trì index; Index Service nhận/cập nhật dữ liệu index qua pipeline tương ứng.
- **Query/scan path:** Query Service chọn index trong plan, yêu cầu Index Service quét một phạm vi index, có thể fetch document từ Data Service, rồi lọc/sắp xếp và trả kết quả.

**KV get theo document ID thông thường không cần GSI.** Vì thế Index Service đang backlog vẫn có thể trùng với trạng thái KV get khỏe. Ngược lại, SQL++ không phải lúc nào đều quét GSI; chẳng hạn `SELECT RAW 1` không cần index của collection.

### 2.1. Không gộp các dịch vụ thành một CPU trung bình

Một cluster có thể có node Data riêng, node Query riêng, node Index riêng, hoặc đồng vị trí dịch vụ trên node tùy topology. CPU trung bình toàn cluster có thể bình thường dù **một node Query/Index đạt điểm nghẽn**. Hãy phân rã theo node, service, workload và index quan trọng.

### 2.2. Không phải cluster nào cũng có Search/Analytics/Eventing

Các dịch vụ phụ có thể được triển khai hoặc không. Bài này tập trung **Data/KV, Query/SQL++ và GSI Index**. Search index và Analytics dataset có metric/cơ chế indexing riêng; không lấy GSI residency hay Query request count để kết luận chúng khỏe.

## 3. Case study và các đường API cần phân loại

Giả sử bucket `shop`, scope `sales`, collection `orders` lưu các document:

~~~json
{
  "customerId": "customer-1001",
  "status": "PAID",
  "createdAt": "2026-11-25T08:00:00Z",
  "totalVnd": 485000
}
~~~

Key: `order::o-1001`.

| Use case | API | Phụ thuộc | Metric cần xem |
| --- | --- | --- | --- |
| Order detail | `findById(id)` | Data/KV | KV latency, timeout, Data node |
| Create Order | `repository.save(order)` | KV write, có thể CAS/durability | Write throughput/latency, conflict, durability |
| Customer Order list | Derived `findByCustomerId` | Query + GSI, đôi khi KV fetch | Query p95/p99, index scans, index backlog |
| Tìm Order theo filter động | `CouchbaseTemplate.findByQuery(...)` | Query/Index | Query shape, plan, result count |
| New Order xuất hiện ngay trong list | KV mutation → GSI → SQL++ | Consistency và GSI update | Index freshness, consistency wait |
| Aggregation/report | SQL++ aggregate | Query CPU/memory, index/fetch/sort | Query plan, temp/memory pressure, latency |

**Không nên dùng một meter “database latency” duy nhất**: KV get có workload khác SQL++ sorting, và transaction có nhiều hoạt động khác một write.

## 4. Bốn phạm vi phải kiểm tra trước khi nhìn đồ thị

| Phạm vi | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| **Service availability** | Query/Index Service có hoạt động không? | Endpoint health, service errors |
| **Service saturation** | Query/Index nodes có đang quá tải? | CPU, memory, queue/backlog, admission/rejections |
| **Per-index health** | Named GSI cần thiết có online, cập nhật và quét được? | Index state, resident ratio, scan/update stats |
| **Functional SLO** | SQL++ thật có trả dữ liệu đúng, đủ mới, đúng hạn? | App p95/p99, Query metadata/profile, `EXPLAIN` |

**Index Service process UP** chưa chắc một named index online. **Một index online** chưa chắc index update kịp mutation. **Query Service UP** chưa chắc một câu `WHERE customerId = ... ORDER BY ...` đạt SLO.

### 4.1. Một lỗi có thể bắt nguồn ở nhiều phạm vi

Ví dụ `Query p99 tăng` có thể do GSI index scan chậm, Query Service busy sort/aggregate, app waiting, SDK retry, network, mapping hoặc kết quả lớn. Cần đặt các tín hiệu cạnh nhau theo cùng cửa sổ thời gian để loại dần giả thuyết.

## 5. Dữ liệu quan sát theo Index Service: nhóm chỉ số quan trọng

Khi giám sát một GSI index cụ thể, các **nhóm** chỉ số cần tìm trong Server metrics/console/API của đúng phiên bản:

| Nhóm | Câu hỏi thực tế |
| --- | --- |
| **Trạng thái index** | Index online, đang build, deferred, lỗi hay trạng thái khác? |
| **Index items/keys** | Số entries tăng/giảm phù hợp dữ liệu và predicate không? |
| **Index data size** | Tổng bytes persistent của index là bao nhiêu, thay đổi ra sao? |
| **Memory usage/quota** | Index Service dùng bao nhiêu RAM so với ngân sách? |
| **Memory residency/cache** | Phần dữ liệu index cần phục vụ có được giữ trong memory/cache theo engine không? |
| **Mutation/update throughput** | Index đang áp dụng bao nhiêu updates/sec? |
| **Pending mutation/backlog** | Công việc cập nhật chờ xử lý có tăng liên tục không? |
| **Scan requests/latency** | Query Service yêu cầu index scan bao nhiêu, mất bao lâu? |
| **Disk I/O/read amplification** | Có nhiều reads/writes, IOPS/latency cao hoặc cache misses không? |
| **Storage fragmentation/compaction** | Có nhu cầu/đợt compaction hoặc disk-space pressure không? |
| **Build/rebalance progress** | Index có đang build, rebalance, failover hoặc di chuyển không? |
| **Errors/rejections** | Scan/update/index availability bị lỗi ở phạm vi nào? |

Đây là **tên nhóm metric ở mức khái niệm**, không phải danh sách tên time-series cố định. Couchbase Server phiên bản, edition, storage engine và hệ thống giám sát có thể dùng tên/đơn vị/trường khác nhau.

### 5.1. Tên metric phải được xác minh thay vì tự đặt

Trước khi tạo Prometheus alert, kiểm tra **metrics endpoint thực đang xuất gì** và schema của Server edition/version. Không giả định một tên như `couchbase_index_memory_used_bytes` luôn tồn tại hay một field `resident_percent` có cùng semantics ở mọi storage engine.

### 5.2. Per-node khác per-index

Tổng Index Service RAM trên node không chỉ ra index nào làm tải tăng; số scan/size per-index lại không mô tả đầy đủ CPU và disk saturation của node. Dashboard nên cho drill-down từ **cluster → service/node → named index → Query shape**.

## 6. Index update path: write rate và GSI maintenance

Khi ứng dụng ghi Order, mutation thành công ở KV không có nghĩa GSI đã cập nhật ngay. GSI cần xử lý stream thay đổi và cập nhật index entries phù hợp.

~~~mermaid
sequenceDiagram
    participant API as Orders API
    participant DATA as Data/KV
    participant PIPE as Index maintenance pipeline
    participant IDX as Index Service
    participant QUERY as Query Service

    API->>DATA: upsert Order / ACK
    DATA-->>API: mutation ACK
    DATA-->>PIPE: thông tin thay đổi
    PIPE->>IDX: cập nhật các GSI liên quan
    QUERY->>IDX: scan theo customerId
    IDX-->>QUERY: index results tại mốc phục vụ
~~~

Việc tạo nhiều index, index trên những field thay đổi thường xuyên hoặc mutation có payload lớn có thể tăng công việc cập nhật/index maintenance. **Không phải mọi mutation làm mọi index thay đổi như nhau**: index keys, partial predicates và dữ liệu thực quyết định lượng công việc.

### 6.1. Khi mutation input lớn hơn update capacity

Nếu tốc độ thay đổi cần index cao hơn tốc độ Index Service có thể xử lý trong thời gian dài, backlog/lag có thể tăng. Điều này có thể biểu hiện:

- Index memory/disk write pressure.
- Mutation queues tăng.
- Index freshness kém.
- Query dùng `REQUEST_PLUS` chờ lâu hoặc timeout.
- KV write vẫn có thể ACK bình thường vì consistency của GSI là một cơ chế khác.

### 6.2. Không tự tính “lag_seconds” từ một queue length

Một backlog 10.000 updates không tự nói “index trễ 10 giây”. Thời gian phụ thuộc throughput, distribution, compaction/build, concurrency, topology và mô hình ingestion. Muốn nói **freshness**, dùng metric lag/thời điểm đã xử lý hay synthetic write-then-query theo SLO phù hợp.

### 6.3. TTL và write-heavy workload

Document expiry/TTL làm thay đổi số document sống và cũng có thể tạo công việc duy trì trạng thái index theo cơ chế của Server. Đừng chỉ đo lượng `insert`; phải xem upsert/delete/expiration và thay đổi index entries trong workloads thực.

## 7. Index scan path: query rate khác update rate

Một index có thể không có nhiều mutation mà vẫn quá tải vì quá nhiều queries/scans. Cần tách:

| Loại tải | Tạo bởi | Điểm nghẽn thường xem |
| --- | --- | --- |
| **Update/ingest load** | KV mutation ảnh hưởng index | Update throughput, DCP pipeline, memory/disk writes |
| **Scan/read load** | SQL++ query dùng GSI | Scan latency/rate, cache residency, disk reads |
| **Build/rebuild load** | CREATE/BUILD INDEX, deploy/rebalance | Resource utilization, build progress, disk temp |
| **Background maintenance** | Compaction, recovery, rebalance | I/O, storage, CPU, completion state |

### 7.1. “Index Service CPU cao” chưa nói tải nào gây ra

Có thể Index Service đang tiêu CPU cho writes cập nhật index, scans từ query, build index hoặc compaction. Đối chiếu **mutation rate**, **scan requests/sec** và **maintenance events** cùng thời điểm.

### 7.2. Index scan latency có thể ảnh hưởng Query p99

Query Service gửi yêu cầu Index Scan; nếu Index Service phải đọc nhiều entries, cache misses hoặc disk I/O chậm, Query p99 tăng. Nhưng Query vẫn có thể chậm do sort/fetch sau scan — cần thêm `EXPLAIN`, profile hoặc server Query metrics để phân biệt.

### 7.3. Index covering và Data fetch

Một **covering index** có thể giúp một SQL++ query trả projection từ index mà không cần fetch body từng document, trong phạm vi optimizer/plan phù hợp. Repository query trả full entity có thể vẫn cần Data Service fetch. Do đó cần so **projection và generated SQL++ thực tế**, không chỉ benchmark `SELECT RAW META(o).id` rồi suy mọi query đều nhanh.

## 8. Quan hệ giữa backlog cập nhật và consistency wait

Spring Data/Java SDK SQL++ có các chính sách scan consistency liên quan trực tiếp đến độ mới của GSI:

| Chế độ | Ý nghĩa ở mức thực thi | Tác động quan sát |
| --- | --- | --- |
| `NOT_BOUNDED` | Không yêu cầu index bắt kịp mốc mutation gần nhất | Thường không đợi freshness, nhưng có thể thấy dữ liệu cũ |
| `REQUEST_PLUS` | Yêu cầu index đạt mốc nhất quán của request | Có thể phải đợi backlog, tăng latency/timeout |
| Mutation-based `consistentWith(...)` | Yêu cầu theo các mutation tokens do client cung cấp | Hữu ích khi cần read-after-specific-writes |

**Một GSI online vẫn có thể lag.** Không sửa p99 bằng cách chuyển mọi query sang `NOT_BOUNDED` nếu ứng dụng cần read-after-write hoặc độ mới cụ thể.

### 8.1. Query Engine ping không đo được index wait

`SELECT RAW 1` không đi qua named GSI Orders. Khi nó chạy nhanh nhưng Repository query timeout, kiểm tra index plan, GSI freshness, Query Service queue và request consistency.

### 8.2. Bài toán “dữ liệu mất” có thể chỉ là index chưa bắt kịp

Order đã được KV get theo ID nhưng chưa xuất hiện trong `findByCustomerId` sử dụng `NOT_BOUNDED`. Đừng tự khẳng định KV write thất bại. Kiểm tra Query consistency, index state và predicate/type mapping trước.

### 8.3. Không dùng health probe REQUEST_PLUS nặng mỗi vài giây

Kubernetes probes thường chạy trên mọi pod. Nếu mỗi probe đợi GSI cập nhật, khi Index Service nghẽn, probes làm Query/Index Service càng nhiều tải và có thể khiến **toàn bộ pods NotReady**. Readiness nên nhẹ, kiểm tra đúng dependency thiết yếu; freshness deep checks chạy ở synthetic monitor với tần suất giới hạn.

## 9. Bộ nhớ Index Service: quota, cache, residency và OS RAM

Một số khái niệm rất dễ bị nhập nhằng:

| Khái niệm | Câu hỏi đúng |
| --- | --- |
| **Index Service memory quota** | Ngân sách memory được cấu hình cho service, theo topology/Server version |
| **Process RSS/heap/native allocation** | Tiến trình Index Service đang dùng bao nhiêu physical RAM? |
| **Index cache usage** | Dữ liệu/index blocks có được cache và tái sử dụng hiệu quả? |
| **Residency metric** | Tỷ lệ dữ liệu liên quan đến index ở memory theo định nghĩa engine/metric |
| **OS page cache** | Hệ điều hành cache disk pages bao nhiêu, có pressure không? |
| **Node available memory** | Node còn headroom cho OS, SDK/network và các dịch vụ đồng vị trí không? |

**Không lấy một số “used RAM” làm toàn bộ kết luận.** Quota index là ngân sách dịch vụ; node RSS và OS page cache thuộc các lớp khác, có thể không cộng/trừ đơn giản thành “free RAM cho index”.

### 9.1. Residency thấp chưa chắc index hỏng

Một index lớn hơn cache có thể có residency thấp nhưng vẫn chạy được; chi phí query phụ thuộc working set, access pattern, storage backend, cache hit/miss và I/O latency. Residency thấp **cùng** p99 scan cao, disk read latency tăng và query selectivity thay đổi là bằng chứng mạnh hơn một điểm residency đơn lẻ.

### 9.2. Residency cao chưa chắc Query nhanh

Ngay cả khi index nằm phần lớn trong memory, Query Service có thể tốn CPU để sort/aggregate, xử lý nhiều rows hoặc fetch Data Service body. Cần xem Query plan/profile và row counts.

### 9.3. Khi quota bị áp sát

Tùy engine/version, áp lực memory có thể tăng disk access, eviction/caching behavior hoặc làm hoạt động index trở nên chậm. Đừng giả định tất cả trường hợp “quota 90%” đều dẫn tới cùng hành vi; kiểm tra Server metrics được hỗ trợ và benchmark trên topology thật.

## 10. Sizing bộ nhớ: working set quan trọng hơn con số tổng

Hãy tự hỏi:

1. Những index nào được quét thường xuyên nhất?
2. Dải key nào “nóng” theo query filters, customerId và time window?
3. Bao nhiêu GSI cùng được duy trì trên một node?
4. Chỉ mục composite/covering làm index data size tăng bao nhiêu?
5. Query có nhiều scans ngẫu nhiên khiến cache locality kém không?
6. Node có co-locate Index và Query/Data/other services không?
7. Rebalance/build/compaction có cần memory headroom tạm thời?
8. Có tăng trưởng khách hàng/Orders/retention horizon trong các tháng tới không?

### 10.1. Ví dụ tư duy working set

Một index persistent có dung lượng lớn nhưng queries tập trung vào Orders mới có thể có working set nhỏ; ngược lại index nhỏ hơn nhưng scan phân tán ngẫu nhiên có thể khiến cache misses cao. Vì thế **size_index_disk không bằng memory_working_set**.

### 10.2. Capacity planning cần kiểm thử với dữ liệu đại diện

Index kích thước nhỏ trong integration test không phản ánh production với hàng triệu documents, cập nhật liên tục và nhiều tenants. Phải dùng dataset có distribution/selectivity đại diện, query shapes thật và write/read mix để đo latency cùng RAM/disk I/O.

## 11. Storage: phân biệt data size, index size và filesystem usage

| Chỉ số | Diễn giải | Điều cần tránh |
| --- | --- | --- |
| **Bucket Data storage** | Không gian data/replica/metadata theo Data Service | Coi nó là toàn bộ Index Service disk |
| **GSI index storage** | Không gian index structures theo engine và node | Cộng tổng sai khi có replicas/partitions |
| **Compaction/temp/maintenance space** | Khoảng trống cần cho công việc nền theo engine | Chỉ tính “index bytes” rồi cho ổ đĩa không cần buffer |
| **OS filesystem used/free** | Khả năng còn lại của volume thực | Nhầm với bucket quota hoặc allocated bytes |
| **Read/write IOPS và latency** | Tốc độ/chi phí I/O | Chỉ nhìn percent disk used |
| **Storage growth rate** | Xu hướng tăng theo retention/index count | Suy capacity từ snapshot một thời điểm |

### 11.1. Mô hình ổ đĩa thay đổi theo nền tảng

Self-managed cluster có thể dùng các filesystem/volumes cục bộ hoặc attached storage cho Index Service. Hosted/cloud deployments có thể trình bày storage, quotas và disk I/O theo cách khác. Hãy đọc topology/storage engine/version **đang chạy** thay vì áp một công thức dung lượng từ môi trường khác.

### 11.2. Disk đầy gây những hậu quả không chỉ là “chậm”

Nếu volume của Index Service gần cạn, index build, compaction, updates hoặc recovery có thể gặp hạn chế; query/index availability cũng có thể bị ảnh hưởng. Đừng đợi filesystem free = 0 mới cảnh báo, vì maintenance/rebalance có thể cần không gian tạm thời.

### 11.3. Một GSI được tạo mới có thể tăng gấp nhiều tải

Index `(customerId, createdAt)` tăng index storage/write maintenance, đặc biệt nếu index replicate/partition. Thêm index giúp Query plan nhưng cũng có **chi phí dung lượng và mutation maintenance**; chọn index dựa trên read SLO **cùng** write/storage budgets.

## 12. Fragmentation và compaction: cần biết storage engine

Theo phiên bản Couchbase Server/storage backend, chỉ mục có thể có fragmentation và cơ chế compaction/cleanup khác nhau. Không áp máy móc một “fragmentation percent 30% thì phải compact” cho mọi Index engine.

Cần xem:

- Storage engine của index và chế độ maintenance được hỗ trợ.
- Disk bytes hữu ích so với allocated/fragmented bytes **theo định nghĩa metric**.
- Compaction/cleanup có diễn ra, mất bao lâu, dùng thêm bao nhiêu I/O/space?
- Có index builds/rebalances đang chạy cạnh compaction không?
- Write rate và scan latency trước/trong/sau maintenance có đổi không?
- Có đủ disk headroom cho trường hợp failover/rebuild không?

### 12.1. Khi compaction cạnh tranh với Query

Nếu disk I/O bận vì compaction, SQL++/GSI scans có thể tăng latency. Nhưng cũng có thể Query Service đang chậm do sort hoặc network dù compaction đang chạy. Cần so timing và I/O metrics, không tự coi hai sự kiện đồng thời là quan hệ nhân quả.

### 12.2. Không gọi compaction như phản xạ khi p99 xấu

Một thao tác storage maintenance không sửa query thiếu index, query plan sai hoặc RBAC. Cần có ngưỡng/điều kiện và runbook phù hợp phiên bản/engine, rồi đánh giá tác động tới user traffic.

## 13. Query Service: nguồn tải khác Index Service

Query Service xử lý SQL++ parsing/planning/execution, điều phối GSI scan, fetch document, filter, join, sort, aggregate và trả results theo plan. Các nguồn tải cần quan sát:

| Nhóm | Câu hỏi |
| --- | --- |
| **Query request rate** | Có bao nhiêu SQL++ requests/s theo query shape? |
| **Active/running requests** | Có bao nhiêu request đang được thực thi? |
| **Queued/admission/waiting** | Có request chờ cơ chế tiếp nhận/concurrency? |
| **Errors/timeouts** | Tỷ lệ timeout/cancellation/permission/query errors bao nhiêu? |
| **Query elapsed/latency** | p50/p95/p99 theo loại query/phase nào? |
| **CPU / memory / allocation** | Parsing, sort, aggregation, operators có gây saturation? |
| **Result count/bytes** | Có truy vấn trả data quá lớn so với pagination? |
| **Prepared query behavior** | Có compile/plan churn hoặc invalidated plans? |
| **Index scan / fetch / sort operators** | Thời gian trong query plan nằm ở đâu? |
| **Endpoints/nodes** | Chỉ một Query node lỗi hay toàn service bị ảnh hưởng? |

### 13.1. “Query node memory cao” phải có thêm ngữ cảnh

Memory dùng cao có thể do nhiều sorts/aggregates đồng thời, nhiều results đang được xử lý, query plan hoặc resource pressure. Không kết luận “memory leak” từ một ảnh chụp. Cần xem tăng trưởng theo tải, garbage collection, allocations, quotas, errors và khả năng hồi phục khi giảm tải.

### 13.2. Query queue và GSI update backlog không phải một

- **Query request queue:** các yêu cầu SQL++ đang chờ admission/execution trên Query Service, nếu metric/version hỗ trợ.
- **GSI update backlog:** mutation cần được cập nhật vào index.
- **Application in-flight:** DB operations chưa hoàn tất tại code wrapper.
- **SDK pending:** requests trong các trạng thái client mà SDK expose.
  
Bốn loại không có quan hệ một-một và không nên đặt chung tên `pendingRequests`.

## 14. Query SQL++ đại diện và index composite

Một query lịch sử Orders có thể được viết:

~~~sql
SELECT META(o).id AS documentId,
       o.customerId, o.status, o.createdAt
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Một index thiết kế để hỗ trợ filter+sort này:

~~~sql
CREATE INDEX ix_orders_customer_created
ON `shop`.`sales`.`orders`(customerId, createdAt DESC);
~~~

**Các đoạn SQL++ là ví dụ cấu trúc**, không phải lệnh cần thực thi trực tiếp trên production. `CREATE INDEX` thuộc migration có phê duyệt/giới hạn tải, không phải routine của health handler.

### 14.1. EXPLAIN trả lời query đang dùng index nào

~~~sql
EXPLAIN
SELECT META(o).id AS documentId,
       o.customerId, o.status, o.createdAt
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = "example"
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Quan sát:

- Có dùng named index mong đợi?
- Index key order có phù hợp `WHERE`/`ORDER BY` không?
- Có nhiều scan rows hơn số rows trả về?
- Có fetch document body vì projection chưa covered?
- Có sort/aggregate tốn memory?
- Có thể push down filter/sort/limit theo plan/version không?
- Query generated từ Spring Data có type discriminator bổ sung không?

**`EXPLAIN` mô tả plan, không phải thời gian thực thi đầy đủ**. Muốn biết operator nào chậm, dùng Query Service profile/metrics của một execution có kiểm soát.

## 15. Xem index metadata và trạng thái mà không làm DDL

Trong những phiên bản Couchbase Server phù hợp, Query Service có system keyspace `system:indexes` để xem metadata/index state. Ví dụ **chỉ đọc**:

~~~sql
SELECT name, state
FROM system:indexes
LIMIT 20;
~~~

Với truy vấn discovery trước khi viết filter theo bucket/scope:

~~~sql
SELECT *
FROM system:indexes
LIMIT 3;
~~~

**Trước khi áp dụng:**

1. Xác minh quyền truy cập system metadata và schema field trên Server version thật.
2. Xác định index nào tương ứng `shop.sales.orders`; không lọc bằng tên field đoán từ release khác.
3. Kiểm tra online/đang build/deferred/error theo lifecycle phiên bản.
4. Đối chiếu index definition, partial predicate, index keys và replica/partition placements nếu có.
5. Đọc các index metrics/console cho **named index** chứ không chỉ state.
6. Không in toàn bộ metadata/topology ra public health endpoint.

### 15.1. Status online không thay scan test

Một index có thể online nhưng query plan chọn index khác, hoặc scan rất chậm. Phải chạy SQL++ đại diện, `EXPLAIN` và đối chiếu scan metrics.

### 15.2. Index không online là vấn đề triển khai, không phải tín hiệu sửa bằng tăng timeout

Nếu ứng dụng phụ thuộc GSI mà index chưa provision/online, retry query vô hạn không tạo index. Sửa migration/deployment, có cảnh báo và runbook recovery; không cấp quyền DDL cho business account chỉ để health check có thể tự sửa.

## 16. Query metadata, metrics và profile từ Java SDK

Khi cần nhìn một SQL++ request sâu hơn, Couchbase Java SDK 3.x có tùy chọn `QueryOptions.metrics(...)` và `QueryOptions.profile(...)` trong những phiên bản hỗ trợ.

~~~java
import java.time.Duration;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryProfile;
import com.couchbase.client.java.query.QueryResult;
import com.couchbase.client.java.query.QueryScanConsistency;

public class OrdersQueryDiagnostic {
    private final Cluster cluster;

    public OrdersQueryDiagnostic(Cluster cluster) {
        this.cluster = cluster;
    }

    public QueryResult run(String customerId) {
        String sql = """
            SELECT META(o).id AS documentId,
                   o.status, o.createdAt
            FROM `shop`.`sales`.`orders` AS o
            WHERE o.customerId = $customerId
            ORDER BY o.createdAt DESC
            LIMIT 20
            """;

        return cluster.query(
                sql,
                QueryOptions.queryOptions()
                        .parameters(JsonObject.create()
                                .put("customerId", customerId))
                        .scanConsistency(
                                QueryScanConsistency.NOT_BOUNDED)
                        .metrics(true)
                        .profile(QueryProfile.TIMINGS)
                        .timeout(Duration.ofSeconds(3)));
    }
}
~~~

Sau khi nhận kết quả:

~~~java
QueryResult result = diagnostic.run("customer-fixture");

// Query metadata có thể có ID, metrics và profile.
var meta = result.metaData();
String queryServerRequestId = meta.requestId();
var metrics = meta.metrics();
var profile = meta.profile();

// Chỉ đọc các field có thật theo SDK version đang dùng;
// không log profile nguyên vẹn hoặc SQL parameters công khai.
~~~

### 16.1. Tách Query Service elapsed time với SDK/client elapsed time

Server Query metadata đo theo semantics của Query engine. `System.nanoTime()` quanh SDK call đo quãng khác, có thể gồm bootstrap, network, retry, response parsing, application code tùy vị trí đặt timer. **Không lấy chênh giữa hai đồng hồ/metric khác ranh giới rồi gọi chính xác là network latency.**

### 16.2. Profile có chi phí và có thể nhạy cảm

Operator timings giúp tìm index scan/fetch/sort đắt, nhưng bật `profile(TIMINGS)` trên mọi request production có thể tăng payload và chi phí xử lý. Dùng trace sampling/synthetic monitor có kiểm soát và kiểm tra quyền/retention.

### 16.3. Timeout có thể không trả QueryResult

Khi SDK throw trước khi nhận metadata, không ép lấy `result.metaData()`. Ghi log với client context ID đã tạo trước dispatch, error class và thời điểm; tra Query Service active/completed requests nếu có và được phép.

## 17. Theo dõi active/completed requests của Query Service

Trong nhiều phiên bản Couchbase Server, Query Service cung cấp các system keyspaces như `system:active_requests` và `system:completed_requests`. Khi được cấp quyền đúng và trong môi trường được kiểm soát, chúng giúp tìm những SQL++ requests đang chạy và các request đã hoàn thành được lưu theo chính sách.

~~~sql
SELECT *
FROM system:active_requests
LIMIT 10;
~~~

~~~sql
SELECT *
FROM system:completed_requests
LIMIT 10;
~~~

**Những điều cần ghi nhớ:**

- System keyspaces này chứa **thông tin chẩn đoán**, không phải business tables.
- Trường `requestId`, `clientContextID`, state, elapsed/phase times hoặc statement có thể khác tên, nội dung, availability theo Server version.
- Completed-request records có retention/threshold/size limit; không mặc định mọi SQL++ request đều được lưu.
- Một request không xuất hiện **chưa chứng minh** request không đến Query Service.
- Có thể có nhiều Query Service nodes; dữ liệu cần được nhìn trong phạm vi phù hợp với cách Server lưu/chia sẻ.
- Raw records có thể chứa SQL text, parameters/endpoint/topology, phải hạn chế quyền truy cập và redaction.

### 17.1. Request ID dùng để nối dữ liệu, không phải chỉ số tải

Mỗi Query request có thể có server request ID, còn SDK có thể gửi `clientContextId`. Các mã này giúp tìm **một** query cụ thể; chúng không nên là labels Prometheus vì cardinality cao.

Để đo tải, dùng **request rate, active/queued counts, duration histogram, errors**. Để điều tra một sự cố, dùng **request ID + query shape + time window** để tra profile và logs.

### 17.2. Thông tin active requests không phải Query queue size đầy đủ

Danh sách đang active/được theo dõi không mặc định bằng tất cả các hàng đợi nội bộ Query Service hay SDK. Nếu cần queue depth, lấy đúng metric mà phiên bản hỗ trợ và kiểm tra định nghĩa của nó.

## 18. Instrument Query latency tại application boundary bằng Micrometer

Bên cạnh server metrics, một Timer quanh DB call cho biết ứng dụng phải chờ bao lâu để nhận kết quả ở ranh giới code đó.

~~~java
import java.util.List;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class OrdersDbTiming {
    private final MeterRegistry meters;
    private final OrderRepository repository;

    public OrdersDbTiming(
            MeterRegistry meters,
            OrderRepository repository) {
        this.meters = meters;
        this.repository = repository;
    }

    public List<OrderDocument> byCustomer(String customerId) {
        Timer.Sample sample = Timer.start(meters);
        String outcome = "success";

        try {
            return repository.findByCustomerId(customerId);
        } catch (RuntimeException failure) {
            outcome = "error";
            throw failure;
        } finally {
            sample.stop(
                    Timer.builder("app.couchbase.query.duration")
                            .description("Repository query call duration")
                            .tags("service", "query",
                                  "shape", "orders_by_customer",
                                  "outcome", outcome)
                            .publishPercentileHistogram()
                            .register(meters));
        }
    }
}
~~~

*Giả thiết:* `OrderRepository.findByCustomerId` trả về `List<OrderDocument>` đồng bộ và method hoàn tất materialization trước khi trả. Nếu Repository trả `Flux`/`Mono`, timer này **chỉ đo lúc tạo Publisher**, chưa đo I/O thật.

### 18.1. Tags nên là một tập hữu hạn

Dùng tags `service=query`, `shape=orders_by_customer`, `outcome=error/success`. Không dùng `customerId`, Order ID, raw SQL++ hoặc exception message làm tags; chúng tạo high cardinality và có thể lộ dữ liệu.

### 18.2. Timer không tự biết nơi nào gây chậm

Timer của Repository có thể bao gồm SDK request, mapping/converter và các xử lý trong method. Nếu thấy p99 tăng, đối chiếu SDK spans, Query Service metrics và `EXPLAIN`. Không kết luận “Index disk chậm” chỉ từ Timer wrapper.

### 18.3. Lỗi “0 rows” có thể là success

Một query SQL++ với `WHERE` không match trả danh sách rỗng có thể là kết quả hợp lệ. Ngược lại, SDK timeout không được bị catch rồi chuyển thành empty list/HTTP 200; nếu làm vậy, error rate và latency metrics sẽ không phản ánh đúng outage.

## 19. Phân biệt request rate, active, queued, pending và backlog

Những chỉ số nhìn giống nhau nhưng có semantics khác:

| Chỉ số | Phạm vi | Đặt câu hỏi |
| --- | --- | --- |
| **HTTP requests in-flight** | Web server/app | Bao nhiêu HTTP requests chưa kết thúc? |
| **DB operations in-flight** | Wrapper Spring/SDK | Bao nhiêu lời gọi DB đang xử lý/chờ kết quả? |
| **Application admission waiting** | Semaphore/rate limiter của app | Có bao nhiêu callers đang đợi permit? |
| **SDK pending** | SDK operation lifecycle nếu version expose | Những request nào đang chờ ở client theo semantics SDK? |
| **Query Service queued** | Query engine nếu metric có | Có SQL++ requests đợi admission/execution? |
| **Query Service active** | Query engine | Có bao nhiêu requests đang được theo dõi/running? |
| **Index scan requests** | Index Service | Có bao nhiêu scans gửi tới named indexes? |
| **GSI mutation backlog** | Index maintenance | Có bao nhiêu updates chưa áp dụng/đã chậm? |

**Không đồng nhất** “GSI pending mutations = 10.000” với “10.000 Query requests đang đợi”. Cũng không lấy một Gauge in-flight của ứng dụng làm số Query Service concurrent requests nếu code có nhiều DB calls per HTTP request.

### 19.1. Cùng một Query có nhiều thời gian chờ

~~~text
HTTP request
  -> đợi application admission permit
  -> SDK dispatch / retry / network
  -> Query Service admission / execution
  -> GSI scan hoặc chờ freshness
  -> Data Service fetch
  -> Java SDK nhận rows
  -> Spring Data converter/serialization
~~~

Nếu server Query execution time nhỏ mà end-to-end lớn, vấn đề có thể ở trước/sau server. Nếu Query Service queue tăng, xem capacity/admission và query mix, không chỉ memory quota index.

### 19.2. Queues có thể bằng 0 khi hệ thống vẫn quá tải

Nếu rate limiter từ chối ngay khi hết permits, queue waiting có thể 0 nhưng rejected count tăng. Cần quan sát **accept/reject/timeout/active/waiting** cùng lúc.

## 20. Query memory pressure và những operator tiêu tốn bộ nhớ

Query Service có thể phải sử dụng bộ nhớ đáng kể khi:

- Thực hiện `ORDER BY` trên lượng dữ liệu lớn mà sort không được xử lý thuận lợi bởi index.
- `GROUP BY`/aggregation có nhiều groups.
- `JOIN`, nested processing hoặc working set lớn.
- Materialize result lớn hoặc nhiều requests đồng thời.
- Có nhiều prepared statements/plans và lifecycle churn.
- Có các đợt traffic tăng khiến active Query requests tăng.

Tùy phiên bản Couchbase Server có các cấu hình/quota/limits khác nhau cho Query Service. **Không tự khẳng định một property quota tồn tại hoặc áp dụng giống nhau ở mọi release.** Tìm đúng cấu hình Server/edition và quan sát memory allocation/usage cùng errors.

### 20.1. Query CPU cao nhưng Index CPU bình thường

Có thể Query Service đang sort/aggregate/fetch nhiều data hoặc mất thời gian lập kế hoạch. Phải xem operator profile và row counts. Việc tăng Index quota không giải quyết một Query plan sort lớn ở Query node.

### 20.2. Query memory tăng cùng concurrency

Nếu memory tăng theo active requests và giảm sau khi tải hết, có thể đó là working memory hợp lệ. Nếu không giảm theo workload, cần kiểm tra caches, memory management/GC, metrics theo thời gian và server logs trước khi gọi là “memory leak”.

### 20.3. Không điều chỉnh concurrency mù

Giảm concurrency có thể giảm overload/tail latency nhưng cũng giảm throughput. Tăng concurrency khi Query Service đã saturation có thể gây queueing và timeout nặng hơn. Thử nghiệm bậc tải có kiểm soát và theo dõi throughput, p95/p99, memory/CPU, rejects để chọn giới hạn.

## 21. Storage capacity và tăng trưởng: từ snapshot tới dự báo

Một dashboard chỉ báo “disk used 72%” tại thời điểm T không nói khi nào hết chỗ. Cần tốc độ tăng, reserved headroom và các hoạt động làm tăng data/index.

Giả sử trên **một volume cụ thể**:

\[
S_{\mathrm{free}}=S_{\mathrm{capacity}}-S_{\mathrm{used}}
\]

Nếu tốc độ tăng sử dụng ổn định `g` (bytes/day), ước tính lý thuyết:

\[
T_{\mathrm{fill}}\approx \frac{S_{\mathrm{free}}-S_{\mathrm{reserve}}}{g}
\]

**Chỉ có nghĩa khi** `g>0`, dữ liệu/quota/volume cùng phạm vi, trend đủ ổn định, và reserve đã bao gồm maintenance, rebalance/build/failover theo policy. Không dùng công thức này làm bảo đảm cluster còn sống đúng `T` ngày.

### 21.1. Dung lượng index không bằng document bytes

GSI lưu cấu trúc index keys và metadata theo storage engine; kích thước phụ thuộc index keys, partial/array indexes, số documents, phân bố và replica/partition design. Index covering có thể giảm Query fetch nhưng tăng bytes/index maintenance.

### 21.2. Replica, partition và rebalance làm thay đổi storage footprint

Index replicas có thể tăng khả năng chịu lỗi và phân phối scan load trong topology hỗ trợ, nhưng cũng cần thêm storage, memory/cache và work cập nhật. Rebalance/build cần headroom; không chỉ lấy size của một index rồi nhân số replica mà bỏ metadata/temp/placement.

### 21.3. Chọn ngưỡng theo headroom chứ không chỉ phần trăm

“Disk free 10%” có thể đủ cho volume nhỏ workload ổn định nhưng quá ít cho index rebuild lớn; ngược lại volume lớn còn nhiều bytes dù phần trăm cao. Alert nên kết hợp **bytes free, growth rate, reserve và workload schedule**.

## 22. Tương quan Query p99 với Index Service và disk I/O

Một ví dụ giả định:

~~~text
09:00  Write rate bắt đầu tăng
09:05  Index update backlog bắt đầu tăng
09:08  REQUEST_PLUS Query latency tăng
09:10  Index disk write utilization/latency tăng
09:11  Orders list timeout rate tăng
09:15  KV get p95 vẫn gần baseline
~~~

Các số trên là **timeline minh họa**, không phải dữ liệu đo thật.

Khả năng: Index Service không xử lý update đủ nhanh, SQL++ có consistency wait. Nhưng cần kiểm tra thêm:

- Index scan request rate có tăng đồng thời không?
- Query Service queued requests, CPU, memory có tăng không?
- Storage device đã đạt IOPS/throughput/latency limit hay chỉ ghi nhiều hơn bình thường?
- Có index build/compaction/rebalance đang chạy?
- Query plan có đổi hoặc query result size tăng không?
- Index lag metrics đo mốc freshness thực tế ra sao?
- Timeout/retry ở application có khuếch đại load không?

**Không kết luận nhân quả từ correlation đơn lẻ.** Cần query plan/profile, resource metrics và thử nghiệm giảm tải/tối ưu có kiểm soát.

## 23. Dashboard đề xuất: 5 nhóm biểu đồ theo thứ tự điều tra

| Nhóm | Panels nên có | Đặc biệt lưu ý |
| --- | --- | --- |
| **A. User impact** | HTTP throughput, 5xx, p95/p99 theo route | Tránh global average che một endpoint |
| **B. SDK/app access** | KV/query latency, timeout/retry, in-flight/waiting | Phạm vi timer phải được ghi |
| **C. Query Service** | Requests/s, active/queued, p95/p99, CPU/memory, errors | Theo Query node và query shape |
| **D. Index Service** | Named index state, scans/s, updates/s, mutation backlog, residency/cache | Tách per-index và per-node |
| **E. Storage/capacity** | Index/data disk bytes, filesystem free, disk I/O latency, compaction/build/rebalance | Tách Data và Index volumes |

### 23.1. Dùng common time window và annotations

Một request trong Spring, index backlog và Query CPU phải được xem **trong cùng cửa sổ thời gian**. Annotate deployments, DDL/migration, index build, rebalance, volume resize và server upgrades để không gán sự kiện không liên quan cho traffic.

### 23.2. Mỗi panel ghi nguồn, units và dimensions

Ví dụ panel “Index cache residency” cần ghi dữ liệu từ **Index Service metric** nào, đơn vị percent/ratio ra sao, storage engine nào, aggregation là per-index hay per-node. Đừng để người xem nhầm `0.7` thành `0.7%` hoặc `70%`.

### 23.3. Dùng drill-down, không nhân labels vô hạn

Có thể drill theo bucket/scope/collection/named index nếu cardinality quản lý được. Không gắn per-document ID, customerId, raw SQL++ parameters hay Query server requestId vào Prometheus labels; các ID riêng từng request nên nằm trong traces/logs.

## 24. Prometheus: minh họa meter ứng dụng, không giả nhận là Server metrics

Giả sử code ứng dụng đăng ký một Micrometer Timer:

~~~java
Timer.builder("app.couchbase.query.duration")
    .tags("service", "query",
          "shape", "orders_by_customer",
          "outcome", "success")
    .publishPercentileHistogram()
    .register(meterRegistry);
~~~

Nếu Prometheus exporter sinh các series điển hình (cần xác minh theo version):

~~~text
app_couchbase_query_duration_seconds_bucket
app_couchbase_query_duration_seconds_count
app_couchbase_query_duration_seconds_sum
~~~

**Query throughput**:

~~~promql
sum by (shape) (
  rate(app_couchbase_query_duration_seconds_count[5m])
)
~~~

**p95 query duration**:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, shape) (
    rate(app_couchbase_query_duration_seconds_bucket[5m])
  )
)
~~~

**p99 của shape Orders**:

~~~promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(app_couchbase_query_duration_seconds_bucket{
      shape="orders_by_customer"
    }[5m])
  )
)
~~~

### 24.1. App Timer không phải server Index backlog

PromQL trên dựa trên **metric do app tự đăng ký**, không tự hiện ra Index storage size hay Query Service queued requests. Các chỉ số server phải lấy từ Couchbase Server exporter/metrics API hoặc observability stack tương ứng sau khi xác minh tên field, đơn vị, quyền và phiên bản.

### 24.2. Histogram percentiles không được lấy trung bình

Không lấy average p99 của nhiều pods để thành fleet p99. Nếu dùng histogram buckets tương thích, tổng hợp buckets theo `le` và dimensions rồi áp `histogram_quantile`. Percentile có thể không ổn định nếu số mẫu ít, bucket quá thô hoặc window không phù hợp.

### 24.3. Timeout không được biến mất khỏi dashboard

Nếu Timer chỉ đo successful queries, p99 có thể trông tốt khi nhiều requests timeout và bị loại khỏi mẫu. Đo error/timeout/cancellation rate độc lập, và định nghĩa SLO theo logical request/application contract.

## 25. Cảnh báo: kết hợp tải, lỗi, thời gian và xu hướng dung lượng

Cảnh báo tốt có **chủ thể, triệu chứng, ngưỡng, thời gian duy trì và runbook**. Ví dụ nhóm cảnh báo (không áp số cố định cho mọi cluster):

| Cảnh báo | Tín hiệu nên kết hợp | Tác động cần đánh giá |
| --- | --- | --- |
| **SQL++ SLO violation** | Query p95/p99, timeout/errors, đủ số samples | Orders list có bị ảnh hưởng? |
| **Index update lag** | Mutation backlog tăng bền, update rate và consistency waits | Query read-after-write có timeout? |
| **Index scan saturation** | Scan rate/latency, disk reads, residency/cache và Query p99 | Named index nào nóng? |
| **Index disk capacity risk** | Bytes free, growth rate, compaction/build reserve | Khi nào cần capacity action? |
| **Query memory/CPU pressure** | Process memory/CPU, active/queued, errors | Nhiều queries/plan nào tạo tải? |
| **Index state degraded** | Named GSI offline/đang build lâu, affected query failures | Capability nào mất? |
| **Readiness flapping** | Pod Ready transitions, shared DB errors | Probes có tạo cascading outage? |

### 25.1. Không cảnh báo từ một mẫu đơn lẻ

Một spike CPU 95% thoáng qua khi query burst không chắc là incident. Xem time window, backlog growth, queue length, user impact và error budget. Ngưỡng nên được hiệu chỉnh từ baseline tải và capacity thực.

### 25.2. Cảnh báo phải hành động được

Alert “Index disk gần đầy” cần ghi node/volume, index/service, free bytes, growth và runbook. Alert “Query slow” nên gắn route/query shape, p99, error rate và link trace/log chẩn đoán **đã kiểm soát quyền**.

### 25.3. Tách capacity alert với immediate failure alert

Disk growth trend thường là capacity planning; named GSI offline kèm Query failures là sự cố hiện tại. Không dùng cùng một severity/chu kỳ phản hồi cho hai loại.

## 26. Hướng điều chỉnh tài nguyên khi xác định đúng nút thắt

| Nút thắt đã có bằng chứng | Hành động có thể cân nhắc | Kiểm chứng sau thay đổi |
| --- | --- | --- |
| Query plan dùng scan không phù hợp | Thiết kế index theo filter/order/projection | `EXPLAIN`, p95/p99, index size |
| GSI update backlog dưới write load | Cân nhắc Index capacity/resources/topology | Update rate, lag, Query REQUEST_PLUS wait |
| Index scan misses/disk I/O cao | Rà working set, quota, storage IOPS/latency | Scan p99, cache/residency, I/O |
| Query Service CPU/memory saturated | Giảm query cost, điều chỉnh Query resources/concurrency | Throughput, queued, p99/errors |
| Index disk/headroom thấp | Capacity expansion/retention/index cleanup theo plan | Bytes free/growth, maintenance success |
| Too many indexes | Loại index không dùng qua change management | Query plans còn dùng index nào? |
| Query result quá lớn | Pagination/projection/index covering phù hợp | Result bytes, converter time, client p99 |
| Retry storm | Thêm backoff/rate limits/circuit breaker | Retry rate, errors, recovery |
| Build/rebalance gây suy giảm | Lập lịch, bố trí resources, giảm concurrency theo runbook | Progress và user SLO |

### 26.1. Thêm Index replica không có nghĩa tải biến mất

Replicas có thể tăng resilience và hỗ trợ đọc/scans tùy layout/Server capabilities, nhưng mỗi replica cần thêm storage/memory và update maintenance. Phải kiểm tra routing/placement, sizing và SLA sau khi thêm.

### 26.2. Tăng quota không sửa index sai

Nếu Query planner phải scan hàng triệu entries cho một `customerId`, thêm RAM có thể giảm một số I/O nhưng không giải quyết triệt để query/index design. `EXPLAIN` và data distribution phải được xem trước quyết định capacity.

### 26.3. Dọn index phải có xác minh phụ thuộc

Một index “ít được dùng tuần này” có thể phục vụ batch/reports theo tháng. Không xóa index production chỉ vì scan count thấp ở một thời điểm; cần lịch workload, query inventory, rollback và quyền change management.

## 27. Reactive WebFlux: đo operation khi được subscribe

Trong Spring WebFlux, `ReactiveCouchbaseTemplate`/Repository thường trả `Mono`/`Flux`. Nếu đặt Timer lúc **tạo** Publisher, duration có thể gần 0 khi I/O chưa bắt đầu.

~~~java
// Sai ranh giới đo: tạo Publisher chưa chắc chạy DB.
long start = System.nanoTime();
Mono<OrderDocument> mono = reactiveRepo.findById(id);
long elapsedNs = System.nanoTime() - start;
~~~

Một mẫu đo phù hợp hơn:

~~~java
import java.util.concurrent.atomic.AtomicReference;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import reactor.core.publisher.Mono;

public final class ReactiveDbTimer {
    private final MeterRegistry meters;

    public ReactiveDbTimer(MeterRegistry meters) {
        this.meters = meters;
    }

    public <T> Mono<T> measure(String shape, Mono<T> source) {
        return Mono.defer(() -> {
            Timer.Sample sample = Timer.start(meters);
            AtomicReference<String> outcome =
                    new AtomicReference<>("success");

            return source
                    .doOnError(error -> outcome.set("error"))
                    .doOnCancel(() -> outcome.set("cancelled"))
                    .doFinally(signal ->
                            sample.stop(
                                    Timer.builder(
                                            "app.couchbase.reactive.duration")
                                            .tags("service", "query",
                                                  "shape", shape,
                                                  "outcome", outcome.get())
                                            .register(meters)));
        });
    }
}
~~~

**Điều kiện:** `shape` là tên template cố định, không lấy từ input. Mã đo **một subscription** tại boundary này; khi có retry/cancellation, vị trí wrapper quyết định nó đếm attempt hay logical operation. Với `Flux`, cần thêm time-to-first-row/stream completion/rows-consumed.

### 27.1. Không block event loop để chờ query

`reactiveRepository.find...().block()` trong request WebFlux có thể chặn event loop và làm HTTP p99 tăng, dù Couchbase Query Service không phải nút thắt. Dùng reactive chain và kiểm soát backpressure/concurrency; đồng thời tránh gọi blocking SDK diagnostics trên event loop.

### 27.2. Không gán Reactor in-flight = Query queue

Một subscription đang đợi I/O thuộc application scope; nó không chứng minh Query Service đã nhận hoặc đang xếp hàng request. Cần SDK/server metrics riêng để biết queue thực.

## 28. Kế hoạch load test và benchmark capacity có kiểm soát

Trên cluster lab có topology/version được ghi nhận, chuẩn bị:

1. Dataset với document count/size, phân phối `customerId`, write/read mix đại diện.
2. Bucket/scope/collection và named indexes online.
3. Danh sách Query shapes và `EXPLAIN` trước thử nghiệm.
4. Warm-up JVM, SDK/cluster connections và caches riêng với cold-start.
5. Xác định consistency mode và durability level của write, tránh so khác semantics.
6. Tăng rate và concurrency theo các bậc có giới hạn, không tạo overload nguy hiểm.
7. Ghi HTTP/SDK Query p50/p95/p99, timeout, errors, throughput.
8. Ghi Index update rate/backlog, scans, residency/cache, memory/CPU/disk I/O.
9. Ghi Query active/queued, memory/CPU, profile của một số queries mẫu.
10. Phân tích Index Service có bị ảnh hưởng bởi scan-heavy và write-heavy load khác nhau không.
11. Hạ tải, đo backlog drain và latency recovery.
12. Lặp lại thí nghiệm và lưu dataset/version/resource config để so sánh.

### 28.1. Ma trận workload minh họa

| Bài test | Workload | Mục tiêu |
| --- | --- | --- |
| KV baseline | `get` theo ID | Tách Data latency khỏi Query/Index |
| Query baseline | `WHERE customerId` + LIMIT | Quan sát Query/GSI path chuẩn |
| Write-heavy | KV upsert/replace với tần suất tăng | Mutation backlog/update I/O |
| Read-heavy | Nhiều SQL++ scans đồng thời | Index scan/cache/Query queues |
| Mixed | Đồng thời create và list Orders | Consistency wait, capacity tradeoff |
| Index build | Trong lab/maintenance window | Build I/O, temporary storage/headroom |
| Recovery | Hạ tải về baseline | Backlog có giảm, p99 có hồi phục? |

### 28.2. Không che lỗi bằng cách bỏ timeout samples

Một benchmark có 99% requests thành công với p99 thấp nhưng 1% timeout nghiêm trọng không thể coi “toàn bộ workload nhanh”. Ghi tổng attempts, completed, timeout, cancelled, retries, offered rate, achieved rate và errors.

### 28.3. Lưu ý coordinated omission

Load generator chạy closed-loop chỉ gửi request mới sau response có thể giảm offered load khi server chậm, làm phân phối latency đẹp giả. Trong performance evaluation nghiêm túc, ghi rõ open-loop/closed-loop, expected arrival schedule và phương pháp đo.

## 29. Unit test instrumentation: đo đúng boundary, không cần Couchbase thật

Trước khi kết nối một dashboard vào hệ thống live, kiểm tra những metric **do ứng dụng tự định nghĩa**. Ví dụ với Micrometer `SimpleMeterRegistry`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class TimerContractTest {
    @Test
    void timerCountsOneCompletedOperation() {
        try (var registry = new SimpleMeterRegistry()) {
            Timer timer = Timer.builder(
                    "app.couchbase.query.duration")
                    .tags("service", "query",
                          "shape", "orders_by_customer",
                          "outcome", "success")
                    .register(registry);

            Timer.Sample sample = Timer.start(registry);
            // Fake operation, không gọi Couchbase thật.
            String response = "OK";
            sample.stop(timer);

            assertEquals("OK", response);
            assertEquals(1L, timer.count());
        }
    }
}
~~~

Đây là test **contract của meter** chứ không xác nhận SDK/Query Service latency. Một test thực cho wrapper ở mục 18 cần inject Repository fake/mock rồi kiểm tra:

- Khi query trả danh sách: Timer count tăng, `outcome=success`.
- Khi query throw: Timer vẫn ghi duration và `outcome=error`.
- Empty list hợp lệ không trở thành database failure.
- Không có `customerId` hoặc raw SQL++ trong metric labels.
- Khi nhiều attempts/retries, số samples khớp **boundary đã định nghĩa**, không bị double-count.
- Đồng hồ/time unit nhất quán; instrumentation không tạo workload Couchbase mới.

### 29.1. Test lỗi cũng quan trọng như test thành công

Nếu code chỉ ghi Timer trong nhánh success, thời gian chờ tới timeout không vào histogram. Dashboard latency lúc outage có thể đẹp bất thường. Dùng `finally` cho synchronous code và terminal signal cho reactive code; đồng thời đo timeout/error rate riêng.

### 29.2. Không dùng fake backlog làm server metric thật

Một `AtomicInteger waiting` do app tạo không phải số Query Service queued requests hoặc GSI pending mutations. Unit test chỉ chứng minh biến/gauge được quản lý đúng, không xác nhận những hàng đợi nội bộ của Couchbase.

## 30. Integration test trên cluster lab: đo KV, SQL++ và index path riêng

Với Couchbase **test cluster** được cấp quyền, có đúng bucket/scope/collection và GSI đã provision trước, kiểm tra theo từng lớp:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class QueryAndIndexPathIT {
    @Autowired
    private Cluster cluster;

    @Test
    void queryEngineResponds() {
        var result = cluster.query("SELECT RAW 1");
        assertNotNull(result.metaData());
    }

    @Test
    void queryCanReadOrdersIndexPath() {
        String sql = """
            SELECT RAW META(o).id
            FROM `shop`.`sales`.`orders` AS o
            WHERE o.customerId = $customerId
            LIMIT 1
            """;

        var result = cluster.query(
                sql,
                QueryOptions.queryOptions()
                        .parameters(JsonObject.create()
                                .put("customerId", "it-no-match")));

        assertNotNull(result.metaData());
        // Empty results là hợp lệ nếu keyspace/query có index
        // nhưng customerId sentinel không match document.
    }
}
~~~

**Giới hạn:**

1. `SELECT RAW 1` chỉ kiểm tra Query Engine; không chứng minh GSI Orders online.
2. Query theo field có thể dùng một index khác index mong muốn; cần `EXPLAIN` để xác minh plan.
3. Trả 0 rows không mặc định là query lỗi.
4. Dùng test-only dataset/credential. Không dùng DDL hoặc tắt Index Service trong production để kiểm tra.
5. Nếu muốn test read-after-write, chuẩn bị mutation fixture, consistency mode phù hợp và cleanup có kiểm soát.
6. Assert “query phải dưới X ms” trong CI có thể flaky do tải môi trường; tách **functional smoke test** khỏi **benchmark/SLO test**.

### 30.1. Test từng loại partial failure trong lab

| Sự cố thử nghiệm | KV | Query Engine | Named index path | Điều kỳ vọng |
| --- | --- | --- | --- | --- |
| Query node unavailable | Có thể UP | Có thể DOWN | DOWN khi thiếu Query path | KV không cần GSI |
| Index offline/missing | UP | `SELECT RAW 1` có thể UP | DOWN/không dùng được | Đừng đánh dấu Query Engine DOWN thay |
| GSI backlog tăng | UP | Có thể UP | Query freshness/latency xấu | Cần đo consistency |
| Index volume thiếu headroom | Có thể UP | Có thể UP | Index maintenance/scan có thể lỗi | Kiểm tra storage risk |
| Query node CPU/memory pressure | KV có thể UP | Một số requests chậm | Query path xấu | Kiểm tra admission/plan |
| App Reactor event loop nghẽn | Server services có thể UP | Query Server bình thường | HTTP p99 vẫn tăng | Phân tách client/app latency |

Không gây sự cố node/network/storage thật trên production. Nếu cần fault injection, phải có quyền vận hành, cluster cô lập và rollback/runbook.

## 31. Phân tích incident A: write tăng, index lag, REQUEST_PLUS timeout

**Triệu chứng giả định:**

~~~text
10:00  KV upsert Order tăng mạnh
10:02  Index update throughput tăng
10:05  GSI pending mutations/backlog tăng liên tục
10:07  REQUEST_PLUS query latency tăng
10:08  Query timeouts tăng
10:09  KV get vẫn ổn, Data Service health UP
~~~

**Giả thuyết:** Index Service không cập nhật GSI đủ nhanh so với mutation stream; Query yêu cầu freshness phải đợi. Nhưng cần kiểm chứng bằng:

1. Index nào phục vụ `WHERE customerId`, có replica/partition nào liên quan?
2. `EXPLAIN` có đổi query plan không?
3. Index update rate, backlog và disk/memory/CPU có liên hệ với write rate không?
4. Query Service queued requests tăng độc lập hay chỉ query execution wait tăng?
5. Có index build/compaction/rebalance đang cạnh tranh resources không?
6. Có quá nhiều GSI bị maintain cho cùng mutation?
7. Có application retry storm tăng Query load không?
8. Query dùng `REQUEST_PLUS` vì business contract nào?

**Các hành động có thể cân nhắc:** Giảm tải/retry có kiểm soát; tối ưu index count/definition; phân bổ Index Service capacity/storage; thay đổi lịch build/rebalance; điều chỉnh query workload theo hợp đồng consistency. **Không** tự chuyển `REQUEST_PLUS` → `NOT_BOUNDED` nếu nghiệp vụ bắt buộc đọc thấy Order vừa ghi.

**Điều kiện phục hồi:** Mutation backlog được kiểm soát, latency Query và timeout trở lại SLO, dữ liệu đủ mới, không làm tăng mức lỗi write/KV.

## 32. Phân tích incident B: Query Service nghẽn nhưng GSI vẫn online

**Triệu chứng giả định:**

~~~text
KV p95          gần baseline
Index state     online
Index backlog   không tăng đáng kể
Query CPU       cao
Query memory    tăng theo concurrent reports
Query p99       xấu khi chạy báo cáo
HTTP 5xx        tăng ở report endpoints
~~~

Khả năng cần kiểm tra:

- Query `GROUP BY`/aggregation/sort tạo working set lớn.
- Query không có `LIMIT` phù hợp hoặc trả hàng chục nghìn rows.
- Query plan dùng index nhưng fetch nhiều documents/không cover.
- Query Service capacity/admission không đủ cho số reports đồng thời.
- Queries SQL++ báo cáo cạnh tranh tài nguyên với Orders list.
- Network/SDK retries hoặc app mapping cũng góp phần.

**Hướng xử lý:** So query profile/`EXPLAIN`, concurrency, result size, sort/aggregate, Query CPU/memory/queue. Cân nhắc giảm report concurrency, tối ưu projection/index, tách workload/Query resources hoặc precompute báo cáo theo kiến trúc được chấp thuận. Không tăng Index cache quota chỉ vì thấy “một index đang online”.

**Điều kiện phục hồi:** Query p95/p99, timeouts và active/queued trở lại phạm vi mục tiêu mà không vi phạm resource quotas hay tính đúng đắn kết quả.

## 33. Runbook điều tra theo cây quyết định

~~~mermaid
flowchart TD
    A["SQL++ chậm hoặc timeout"] --> B["Tách KV vs SQL++ và phạm vi node/route"]
    B --> C{"Index state đúng và Query Engine có phản hồi?"}
    C -->|Không| D["Kiểm tra Service/topology/RBAC/index provisioning"]
    C -->|Có| E["Xem EXPLAIN và Query profile/metrics"]
    E --> F{"Index update backlog tăng?"}
    F -->|Có| G["Write rate, Index CPU/memory/disk, consistency wait"]
    F -->|Không| H{"Index scan latency/misses cao?"}
    H -->|Có| I["Working set, resident/cache, I/O, scan selectivity"]
    H -->|Không| J["Query CPU/memory/queued, sort/fetch/mapping"]
    D --> K["Sửa nguyên nhân, đo lại"]
    G --> K
    I --> K
    J --> K
~~~

**Trình tự on-call có thể áp dụng:**

1. Chốt thời điểm và user impact: route, query shape, error/timeout rate, p95/p99.
2. Tách KV operations và SQL++ path; tránh gọi toàn bộ Couchbase “DOWN”.
3. Lấy request/trace/client context ID nếu có, đối chiếu Query Service request diagnostics và logs có kiểm soát.
4. Kiểm tra Query Service nodes, Index Service nodes, endpoint errors, network/TLS/RBAC.
5. Kiểm tra named index state, index definition và `EXPLAIN` của query thực.
6. Lấy Index per-index/per-node: scans, updates, backlog, residency/cache, memory/disk.
7. Lấy Query per-node: active/queued, CPU/memory, latency, profile operators và result count.
8. So Data write rate, KV get/write p95, CAS conflicts và durability/TTL behavior.
9. Kiểm tra deployments, index DDL, build/rebalance/compaction và volume events cùng thời điểm.
10. Phân biệt application admission/SDK pending từ Query queue và Index mutation backlog.
11. Xem consistency mode, nhất là `REQUEST_PLUS` chờ Index Service.
12. Xem quota vs RSS, OS memory, filesystem bytes free và disk I/O latency.
13. Hạn chế retries/concurrency hoặc traffic non-critical nếu overload; không tạo heavy diagnostics loops.
14. Quyết định tối ưu index, query, capacity, topology hay storage theo bằng chứng.
15. Sau sửa, đo recovery của latency, error, backlog, disk headroom và freshness SLO.
16. Ghi lại nguồn/đơn vị/phiên bản của metrics, điều chưa chắc chắn và hành động phòng ngừa.

**Không khởi đầu bằng restart đồng loạt pods hoặc rebuild indexes**. Hai hành động này có thể khuếch đại outage, làm mất headroom và không sửa query plan/RBAC sai.

## 34. Bảo mật và an toàn vận hành khi lấy diagnostics

Các nguồn `system:indexes`, `system:active_requests`, `system:completed_requests`, Query profile và metrics quản trị có thể chứa statement text, host/topology, index definitions và dữ liệu liên quan tới tenants.

Quy tắc:

1. Dùng quyền tối thiểu cho monitoring identity, không cấp admin toàn cluster cho Orders API.
2. Không trả raw Query profile/management data từ HTTP endpoint công khai.
3. Bind SQL++ parameters; không nối raw customerId để tạo statement.
4. Dùng query shape cố định thay cho SQL text/parameter trong logs thường ngày.
5. Không gắn document IDs, customer IDs, server request IDs vào Prometheus labels.
6. Hạn chế log/debug/profile sampling và thời gian lưu; bảo đảm audit quyền truy cập.
7. Khi cần synthetic queries, dùng read-only, giới hạn số rows/timeout/frequency.
8. Không đưa index build/drop/compact/rebalance vào Kubernetes readiness handler.
9. Không thu thập/stress test cluster production ngoài quy trình được phép.
10. Giữ tài liệu runbook không chứa credential, tokens, hostnames nhạy cảm hay raw profile có PII.

### 34.1. Health probe không phải dashboard capacity

Một `/actuator/health` UP chỉ chứng minh phép thử health được định nghĩa đã thành công; không chứng minh Index Service còn đủ disk để rebuild hoặc Query p99 đạt SLO. Dùng monitoring liên tục và capacity forecast riêng.

## 35. Những ngộ nhận cần loại bỏ

1. **“KV GET nhanh thì Index Service chắc khỏe.”** KV theo ID thường không cần GSI.
2. **“Index online nghĩa cập nhật ngay lập tức.”** Index có thể còn backlog.
3. **“Query Engine SELECT RAW 1 nhanh nghĩa mọi SQL++ query nhanh.”** Business query có index/fetch/sort khác.
4. **“Index Service CPU cao chỉ do queries.”** Có thể do updates, builds, compaction.
5. **“Query Service CPU cao chỉ do Index scan.”** Có thể do sort/aggregate/plan.
6. **“Bộ nhớ còn trống nghĩa không có vấn đề I/O.”** Disk latency/cache misses vẫn có thể cao.
7. **“Residency thấp nghĩa index hỏng.”** Có thể index working set lớn hơn cache nhưng vẫn hoạt động.
8. **“Residency cao nghĩa query chắc nhanh.”** Query sorting/mapping vẫn có chi phí.
9. **“Disk size của index bằng tổng storage cần.”** Còn replicas/temp/maintenance/headroom.
10. **“Disk used percentage đủ để dự báo hết dung lượng.”** Cần bytes và growth trend.
11. **“Mọi storage engine dùng chung compaction threshold.”** Phải theo version/engine.
12. **“Index backlog bằng Query queue.”** Đây là hai dạng công việc khác nhau.
13. **“App in-flight bằng SDK pending.”** Phạm vi đo khác nhau.
14. **“Queue bằng 0 nghĩa không overload.”** Hệ thống có thể reject ngay.
15. **“REQUEST_PLUS chậm nên phải đổi NOT_BOUNDED.”** Có thể phá freshness contract.
16. **“EXPLAIN cho biết thời gian execution thật.”** Nó cho plan, cần profile/metrics.
17. **“Query profile trên mọi request hoàn toàn miễn phí.”** Có overhead/dữ liệu nhạy cảm.
18. **“Tăng memory quota sửa query thiếu index.”** Cần sửa plan/index trước.
19. **“Thêm GSI không có chi phí.”** Có write amplification/storage/update overhead.
20. **“Thêm index replica không tốn disk.”** Replicas cần resources và maintenance.
21. **“Xóa index scan count thấp là an toàn.”** Batch/report jobs có thể dùng theo chu kỳ.
22. **“Timeout có nghĩa dữ liệu chưa ghi.”** Write timeout có thể ambiguous.
23. **“404/not-found lúc TTL hết hạn là Data Service DOWN.”** Có thể là expiry hợp lệ.
24. **“Latency p99 của một pod có thể lấy trung bình ra fleet p99.”** Sai thống kê.
25. **“Reactive Mono được tạo là query đã chạy.”** I/O thường bắt đầu khi subscribe.
26. **“Tăng số pods luôn giải quyết Index overload.”** Có thể tăng cả load vào shared dependency.
27. **“SDK meter name giống nhau ở mọi version.”** Phải xác minh thực tế.
28. **“Health probe có thể chạy query REQUEST_PLUS nặng.”** Dễ gây probe storm/flapping.

## 36. Bài tập thực hành

### A. KV khỏe, SQL++ chậm

`findById` có p99 tốt nhưng `findByCustomerId` timeout.

**Gợi ý:** Xem Index/Query path, `EXPLAIN`, Query Service queues, index scan/update load và consistency mode. Không gọi Data Service down.

### B. Tăng write rate và backlog

Index update throughput tăng nhưng backlog tăng nhanh hơn, `REQUEST_PLUS` query cũng chậm.

**Gợi ý:** Phân tích write/index update capacity, resource pressure, mutation backlog/freshness và Index Service placement. Đừng thay policy consistency khi chưa xem nghiệp vụ.

### C. Index online nhưng Query report rất chậm

Query Service dùng nhiều CPU/memory, GSI state online.

**Gợi ý:** Profile sort/aggregate/fetch/result size, Query resource limits và concurrency, không chỉ Index health.

### D. Residency giảm

Residency index giảm từ mức baseline trong khi index size tăng.

**Gợi ý:** Kiểm tra working set, query scan pattern, cache misses, disk I/O và p99; không tự kết luận index broken.

### E. Disk usage tăng sau thêm covering index

**Gợi ý:** Index covering có thể giảm fetch nhưng tốn storage và maintenance. Đo gain Query p99 cùng storage/Index update cost trước khi quyết định.

### F. Mutation backlog lớn nhưng Query queue thấp

**Gợi ý:** Đó là hai loại backlog khác nhau; query có thể chờ Index freshness ngay trong execution, hoặc chưa có nhiều SQL++ requests. Xem cả GSI lag và `REQUEST_PLUS` latency.

### G. Query queue thấp nhưng HTTP timeout tăng

**Gợi ý:** App admission wait, SDK retry/network, mapping/result serialization, cached data hoặc fail-fast errors có thể gây lỗi. Dùng trace cùng time window.

### H. Disk còn 8% trống

**Gợi ý:** Không đủ dữ liệu để dự báo. Cần bytes free, growth rate, reserve cho build/compaction, topology/replicas và timeline.

### I. Hai Query pods có p99 khác nhau

**Gợi ý:** Không lấy trung bình p99. Tổng hợp histogram buckets nếu tương thích, hoặc so Query node/pod load distribution và đủ samples.

### J. Tối ưu index xong nhưng app p99 không đổi

**Gợi ý:** Kiểm tra query plan thực đã dùng index mới chưa, SDK/HTTP boundary, app queue, cache, result mapping và network. Index cải thiện chưa chắc là nút thắt chính.

## 37. Checklist trước khi đưa giám sát vào production

- [ ] Đã có bản đồ KV, Query và Index Service cho từng use case chính?
- [ ] Phân biệt service UP, per-index state và functional Query SLO?
- [ ] Có metrics Index Service per-node và per-named-index?
- [ ] Tách index update throughput, scan throughput và build/maintenance load?
- [ ] Mutation backlog có nguồn, đơn vị và freshness SLO được hiểu rõ?
- [ ] `REQUEST_PLUS`/`NOT_BOUNDED`/mutation-state được chọn theo nghiệp vụ?
- [ ] Không coi GSI online là index đã đủ mới?
- [ ] Có đo Index cache/residency và hiểu storage engine semantics?
- [ ] Phân biệt Index quota, process memory, OS page cache và node headroom?
- [ ] Query Service CPU/memory/active/queued, timeouts có dashboard riêng?
- [ ] App in-flight, SDK pending, Query queue và GSI backlog không bị gộp?
- [ ] Có Index storage size, filesystem bytes free, growth và disk I/O latency?
- [ ] Capacity forecast xét replicas, compaction, build/rebalance reserve?
- [ ] Các ngưỡng cảnh báo được hiệu chỉnh theo workload/version?
- [ ] Query metrics và profile được đọc đúng API/version, không bật vô hạn?
- [ ] `EXPLAIN` của SQL++ thật được ghi nhận khi điều tra?
- [ ] Spring Data generated queries/type discriminator được kiểm tra khi cần?
- [ ] SQL++ result size, fetch, sort và pagination nằm trong phân tích?
- [ ] SDK/client và Query/server duration có boundary rõ?
- [ ] Micrometer Timer có count/histogram, error/timeout rate đi kèm?
- [ ] Histogram p95/p99 không bị lấy trung bình giữa pods?
- [ ] Prometheus/Actuator metrics endpoints được bảo vệ theo network/RBAC?
- [ ] Không đặt user ID, document ID, raw SQL++/request ID vào metric labels?
- [ ] Reactive timing bắt đầu lúc subscription, kết thúc ở terminal signal?
- [ ] Reactive cancellation/retries được phân loại rõ?
- [ ] Benchmark có lab cluster, dataset, index plan, load mix và recovery?
- [ ] Không chạy mutation-heavy synthetic check trên mỗi readiness probe?
- [ ] Load tests không bỏ samples timeout/cancelled/rejected?
- [ ] Incident runbook có kiểm tra Query/Index CPU, memory, disk, plan, backlog?
- [ ] Có đo lại SLO và capacity headroom sau khi tối ưu?
- [ ] Không làm DDL/rebuild/compaction nguy hiểm ngoài change management?

## 38. Kết luận

**Quan sát tải chỉ mục, bộ nhớ, dung lượng và Query Service phải tách theo đúng công việc đang thực hiện.** Data Service phục vụ KV, Index Service duy trì GSI từ mutations và phục vụ scans, Query Service lập kế hoạch/thực thi SQL++ và có thể chịu tải lớn từ sort, aggregate, fetch hoặc consistency waits. Một chỉ số “database UP” không diễn tả nổi sự khác biệt đó.

Với **SPRING_DATA_COUCHBASE**, hãy ghép **Query p95/p99 và error rate** với **Index update/scan load**, **GSI mutation backlog**, **memory quota/residency**, **filesystem headroom/I/O** và **Query Service active/queued/CPU/memory**. Dùng `EXPLAIN` cùng profile/metadata để phân tích plan và operator cost; dùng Micrometer/tracing để hiểu quãng trước/sau SDK; dùng benchmark có kiểm soát để đánh giá những thay đổi index, storage và capacity.

Một hệ thống vận hành tốt không chỉ báo rằng cluster “sắp đầy” hoặc “đang chậm”, mà xác định được **index nào đang chịu tải, Query nào bị ảnh hưởng, giới hạn tài nguyên nào đang bị chạm, độ mới dữ liệu có còn đạt hợp đồng và hành động nào giúp phục hồi mà không hy sinh correctness**.
