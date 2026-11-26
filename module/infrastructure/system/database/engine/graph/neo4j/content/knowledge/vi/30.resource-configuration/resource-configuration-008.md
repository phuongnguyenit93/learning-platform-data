# Kiểm chứng thay đổi cấu hình bằng số liệu thay vì tăng tài nguyên tùy ý trong Neo4j

## 1. Vấn đề: truy vấn chậm không đồng nghĩa máy chủ thiếu RAM

Neo4j lưu **property graph** gồm node, relationship và thuộc tính; ứng dụng dùng Cypher để truy vấn đường đi, tìm các thực thể liên quan, tổng hợp kết quả và cập nhật graph. Neo4j có thể bị chậm vì nhiều nguyên nhân: một query phải duyệt quá nhiều relationship, page cache thiếu, JVM garbage collection (GC) gây ngắt quãng, transaction giữ khóa lâu, ổ đĩa nghẽn hoặc tầng Java Driver đang chờ connection.

Giả sử một API quản lý chuỗi cung ứng trả danh sách nhà cung cấp theo sản phẩm. Thời gian phản hồi p95 tăng từ 120 ms lên 900 ms sau khi lượng đơn hàng tăng. Có người đề xuất:

> “Tăng JVM heap từ 8 GiB lên 24 GiB, page cache từ 12 GiB lên 24 GiB, Bolt thread pool lên 800 là sẽ nhanh.”

Đề xuất trên **chưa có bằng chứng**. Nếu Neo4j chạy trên máy chỉ có 32 GiB RAM, việc phân bổ cùng lúc 24 GiB heap và 24 GiB page cache là bất khả thi khi tính cả hệ điều hành, native memory và các tiến trình khác. Nếu nguyên nhân chính là `Expand(All)` sinh hàng triệu dòng hoặc các transaction chờ cùng một khóa, thêm heap cũng không làm truy vấn tự động tối ưu.

**Nguyên tắc của chương “Cấu hình tài nguyên”: mọi thay đổi phải xuất phát từ một giả thuyết có thể kiểm chứng, có baseline, chỉ số đầu ra, điều kiện thử nghiệm, ngưỡng chấp nhận và phương án rollback.**

Bài này hướng dẫn:

1. Phân biệt các **vùng tài nguyên** mà Neo4j và Java Driver sử dụng.
2. Thiết lập **baseline** và một bộ metric đại diện.
3. Đọc dấu hiệu nghẽn từ query plan, page cache, GC, CPU, I/O, transaction và Bolt.
4. Xây dựng thí nghiệm thay đổi **một yếu tố mỗi lần**, so sánh trước/sau đúng cách.
5. Trình bày ví dụ đánh giá heap, page cache, transaction limit, thread pool và cách quyết định **không** tăng cấu hình.
6. Áp dụng quy trình cho môi trường tự quản lý, container/Kubernetes, Neo4j Enterprise và AuraDB.

> Các tên setting dưới đây dùng chuẩn cấu hình Neo4j 5.x/2025–2026 hiện hành. Hãy xác minh bằng `SHOW SETTINGS` và tài liệu **đúng phiên bản/edition**; không dùng tên setting của Neo4j 4.x trong cấu hình mới.

## 2. Phân biệt tài nguyên trước khi tối ưu

### 2.1. Mô hình sử dụng bộ nhớ

```text
RAM vật lý hoặc memory limit của container
|
+-- Neo4j process (JVM)
|   |
|   +-- JVM heap
|   |   +-- Object, query/transaction state
|   |   +-- Cypher runtime và aggregation/sort
|   |   +-- GDS projected graph (nếu cài Graph Data Science)
|   |   +-- Query/plan caches và GC headroom
|   |
|   +-- Page cache (ngoài Java heap)
|   |   +-- Data store và native indexes
|   |
|   +-- Native/direct memory
|       +-- Network buffers, metaspace, thread stacks, JVM overhead
|
+-- Hệ điều hành / filesystem / tiến trình khác
    +-- Kernel, container runtime, monitoring, agent, v.v.
```

| Vùng | Setting hoặc cách theo dõi | Công dụng | Không nên hiểu nhầm |
| --- | --- | --- | --- |
| **JVM heap** | `server.memory.heap.initial_size`, `server.memory.heap.max_size`; JVM/GC metrics | Bộ nhớ đối tượng Java, query/transaction state, một số plugin | Không phải tổng RAM Neo4j |
| **Neo4j page cache** | `server.memory.pagecache.size`, hit ratio, page faults | Cache dữ liệu graph và native index nhằm tránh truy cập đĩa | Không phải JVM heap; không tăng hiệu quả khi workload đã hit cao |
| **Transaction memory** | `dbms.memory.transaction.total.max`, `db.memory.transaction.total.max`, `db.memory.transaction.max` | Giới hạn memory tiêu thụ bởi các transaction | Không tạo thêm RAM; ngưỡng quá thấp có thể chấm dứt query |
| **Native/JVM overhead** | RSS, metaspace, direct buffers, thread stacks | Vùng ngoài heap cần thiết để Neo4j chạy | Không biến mất khi giảm kích thước heap |
| **I/O và storage** | IOPS, throughput, latency, checkpoint duration, page faults | Đọc/ghi dữ liệu, flush, checkpoint và transaction log | DB Hits không đồng nghĩa số lần đọc đĩa |
| **CPU và thread** | CPU process/host, run queue, Bolt thread pool | Xử lý Cypher, concurrency, GC, lập kế hoạch | Thêm thread không tạo thêm CPU |
| **Java client** | Connection pool, request latency, heap, GC, wait time | Gửi Cypher và tiêu thụ kết quả | Tăng pool client không giảm thời gian server chạy truy vấn |

**Đọc các tài nguyên như một hệ thống thống nhất.** Tăng heap có thể làm RAM khả dụng cho page cache giảm; tăng concurrent query có thể khiến CPU/GC và I/O cùng tăng. Cần tối ưu **toàn bộ request**, không tối ưu riêng một chỉ số mà bỏ qua các chỉ số khác.

### 2.2. Công cụ khuyến nghị không thay benchmark

Trên Neo4j tự quản lý, có thể xem gợi ý khởi điểm:

```bash
bin/neo4j-admin server memory-recommendation --memory=32g
```

Lệnh này cung cấp **heuristic** phân bổ heap/page cache với giả định một lượng RAM được dành cho Neo4j. Nó không biết đầy đủ phân bố bậc quan hệ, độ chọn lọc của truy vấn, yêu cầu p99, transaction concurrency hoặc các job GDS đồng thời. Vì vậy, **không lấy kết quả làm cấu hình tối ưu cuối cùng**.

Trong Docker/Kubernetes phải xét **memory limit thực tế của container/pod**, không chỉ RAM của host. Nếu pod có limit 16 GiB, không dùng khuyến nghị tính trên host 64 GiB. Nếu cùng máy chạy ứng dụng Java, agent monitoring hoặc nhiều Neo4j instance, phải trừ ngân sách của các tiến trình ấy.

## 3. Bắt đầu bằng mục tiêu đo được, không bằng kích thước máy

### 3.1. Xác định SLO và phạm vi so sánh

Ví dụ use case: endpoint `GET /suppliers/{id}/products`.

| Yếu tố | Ví dụ mục tiêu | Cách xác minh |
| --- | --- | --- |
| **Tính đúng** | Danh sách SKU và thứ tự không thay đổi do tuning | So kết quả/đếm/khóa trước và sau |
| **p95 latency** | Dưới 250 ms khi 100 request/s | Đo request end-to-end nhiều khoảng thời gian |
| **p99 latency** | Dưới 500 ms | Theo dõi tail latency, không chỉ trung bình |
| **Throughput** | Đạt ít nhất 100 request/s ổn định | Không tăng error/timeout khi đạt tải |
| **Error rate** | Dưới 0,1% trên tập thử | Theo dõi timeout, transaction failures, pool errors |
| **Tài nguyên** | Không OOM, không swap, GC/CPU/I/O trong giới hạn vận hành | JVM, host/container, query log, metrics |
| **Độ bền** | Ổn định khi chạy lâu và ở tải đỉnh | So sánh nhiều cửa sổ, không lấy một request |

**Các giá trị 250 ms, 500 ms, 100 request/s là ví dụ SLO tự đặt**, không phải chuẩn Neo4j. Với API báo cáo 10 phút hay batch import ban đêm, mục tiêu thích hợp khác hoàn toàn với API tương tác.

### 3.2. Đo p95, p99 và throughput đúng cách

- **p95 latency**: 95% request trong tập đo có thời gian không lớn hơn giá trị này; đừng thay p95 bằng average.
- **p99 latency**: nhạy với GC pause, queueing, lock contention và tải đỉnh.
- **Throughput**: số request **hoàn tất hợp lệ** mỗi giây, không chỉ số request gửi đi.
- **Error rate**: tỷ lệ request thất bại; một bản cấu hình trả kết quả nhanh hơn nhưng timeout/503 nhiều hơn **không được coi là cải thiện**.
- **Offered load** so với **achieved throughput**: bộ tạo tải gửi 200 request/s nhưng máy chỉ hoàn tất 120 request/s thường cho thấy hệ thống quá tải/queueing, không phải throughput 200.

Quan sát thêm CPU, bộ nhớ, GC và I/O trong **cùng khoảng thời gian**. Không so p95 trong giờ thấp điểm với p95 giữa giờ cao điểm rồi quy mọi khác biệt cho cấu hình.

## 4. Thu thập baseline: bốn lớp số liệu

### 4.1. Lớp ứng dụng Java/Spring

Ghi tối thiểu:

1. Request rate, p50/p95/p99 của toàn endpoint.
2. Thời gian gọi Neo4j riêng, thời gian serialize/response, độ lớn payload.
3. Số truy vấn Neo4j cho mỗi request (phát hiện **N+1**).
4. Số timeout, retry, transaction failure và thời gian chờ connection.
5. Heap/GC của JVM ứng dụng, đặc biệt khi dùng `Result.list()` cho kết quả lớn.

Nếu ứng dụng Spring Data Neo4j hydrate cả một graph entity nhiều quan hệ chỉ để lấy hai thuộc tính, sửa **read query/DTO** có thể có lợi hơn tăng heap database.

### 4.2. Lớp truy vấn Cypher

Dùng `EXPLAIN` để xem plan **không chạy query** và `PROFILE` để đo **query chạy thật**:

```cypher
EXPLAIN
MATCH (s:Supplier {supplierId: $supplierId})-[:SUPPLIES]->(p:Product)
WHERE p.active = true
RETURN p.sku AS sku, p.name AS name
ORDER BY sku
LIMIT $limit;
```

```cypher
PROFILE
MATCH (s:Supplier {supplierId: $supplierId})-[:SUPPLIES]->(p:Product)
WHERE p.active = true
RETURN p.sku AS sku, p.name AS name
ORDER BY sku
LIMIT $limit;
```

**Lưu ý:** đây là pattern minh họa cho graph có label `Supplier`/`Product` và relationship `SUPPLIES`; muốn chạy cần có dữ liệu, tham số và quyền. Những operator có thể quan sát:

| Dấu hiệu trong plan | Diễn giải có thể | Hướng điều tra |
| --- | --- | --- |
| `NodeByLabelScan` trên nhãn rất lớn | Không có đường vào chọn lọc hoặc scan được planner đánh giá rẻ hơn | Kiểm tra index/constraint, predicate và số bản ghi |
| `Expand(All)` tạo rất nhiều `Rows` | Fan-out lớn từ một node `Supplier` | Ràng buộc loại/hướng, giảm phạm vi traversal hoặc thiết kế truy vấn khác |
| `Filter` loại phần lớn dòng sau expand | Lọc muộn | Xem cách bắt đầu từ đầu có index/chọn lọc hơn |
| `CartesianProduct` | Hai tập ứng viên bị nhân số dòng | Xem pattern có nhánh độc lập không mong muốn |
| `Sort`/`EagerAggregation` với đầu vào rất lớn | CPU/heap có thể cao | Cân nhắc index, giảm dữ liệu, read model |
| `DB Hits` cao | Nhiều thao tác storage engine | Không đánh đồng với disk I/O; đối chiếu page faults |
| `Estimated Rows` lệch xa `Rows` | Cardinality estimate chưa mô tả tốt dữ liệu | Xem skew, thống kê, plan và tham số |

**Không dùng `PROFILE` cho truy vấn ghi trên production chỉ để “xem trước”: nó thực thi `CREATE`/`MERGE`/`SET`/`DELETE` thật.** Dùng `EXPLAIN` hoặc môi trường thử nghiệm được kiểm soát.

### 4.3. Lớp Neo4j DBMS

Trên môi trường có quyền và tính năng giám sát tương ứng, nhóm chỉ số cần theo dõi:

| Nhóm | Metric/dấu hiệu | Khi đáng nghi |
| --- | --- | --- |
| Page cache | Hit ratio, usage ratio, page faults/s, evictions/s, bytes read | Hit giảm kéo dài và faults tăng, I/O disk tăng |
| JVM heap | Heap used/committed/max, GC time/pause, allocation rate | GC time cao, old-gen pressure, gần OOM |
| Transaction | Active transactions, `estimatedUsedHeapMemory`, lock/wait time | Transaction dài, chờ khóa, memory limit bị chạm |
| Bolt | Connection/thread counts, pool utilization, rejected jobs | Hết thread thực sự, nhiều connection/transaction giữ lâu |
| CPU | CPU busy, run queue, CPU quota/throttling | CPU chạm hạn khi throughput không tăng |
| Storage | Disk utilization, IOPS, await, throughput, checkpoint duration | Latency I/O tăng, checkpoint cạnh tranh với write |
| Reliability | Errors, timeouts, out-of-memory, restart, transaction termination | Xuất hiện sau thay đổi cấu hình |

Các metrics chính thức, gồm các chỉ số CSV/JMX/Prometheus, được tài liệu Neo4j liệt kê cho **Enterprise Edition**. Không mặc định Community hoặc Aura cung cấp cùng endpoint, tên metric hay quyền cấu hình. Với Community, vẫn có thể đo ở OS/JVM/ứng dụng và chạy `EXPLAIN`/`PROFILE` nếu được quyền; với Aura dùng các màn hình và số liệu do gói dịch vụ cho phép.

**Tỷ lệ page-cache hit cao thường là tốt**, và tài liệu Neo4j nêu vùng tham khảo gần 98–100% với workload phù hợp. Nhưng đây là **chỉ báo chẩn đoán**, không phải điều kiện đủ chứng minh query đang tối ưu. Cache hit 99,9% mà `DB Hits`/`Rows` rất lớn vẫn có thể chậm.

### 4.4. Lớp hệ điều hành/container

Ngoài bộ nhớ Neo4j, ghi:

- RAM được cấp, resident set size (RSS), swap activity và tình trạng OOM killer.
- CPU cores/CPU quota, CPU throttling, load average hoặc run queue.
- Disk read/write latency, IOPS, utilization, filesystem và dung lượng trống.
- Network RTT giữa Java service và Neo4j, lỗi kết nối, retransmission khi có.
- Số instance khác hoặc tiến trình ngoài Neo4j trên cùng host.

Một máy có 64 GiB RAM nhưng container Neo4j bị giới hạn 16 GiB có thể OOM do container dù host vẫn báo nhiều RAM còn trống.

## 5. Bật quan sát đúng mức và kiểm tra cấu hình hiệu lực

### 5.1. Xem setting đang có

Trên **Neo4j tự quản lý**, với quyền phù hợp:

```cypher
SHOW SETTINGS
YIELD name, value, isDynamic
WHERE name IN [
  'server.memory.heap.initial_size',
  'server.memory.heap.max_size',
  'server.memory.pagecache.size',
  'dbms.memory.transaction.total.max',
  'server.bolt.thread_pool_max_size'
]
RETURN name, value, isDynamic
ORDER BY name;
```

`SHOW SETTINGS` hiển thị các giá trị của **server đang thực thi câu lệnh**; trên cluster, nối tới một thành viên không chứng minh các thành viên khác cũng có cấu hình giống hệt. Lệnh này không khả dụng trên Aura theo Operations Manual hiện hành.

**Không ghi mật khẩu hoặc secret vào báo cáo cấu hình.** Mọi setting liên quan endpoint/credential phải được xử lý như dữ liệu vận hành nhạy cảm.

### 5.2. Neo4j Enterprise: dùng query log để điều tra

Với Enterprise và quy trình thay đổi đã được duyệt, có thể cấu hình file `neo4j.conf`:

```properties
# Ví dụ quan sát truy vấn chậm, KHÔNG phải bộ cài đặt mặc định.
db.logs.query.enabled=INFO
db.logs.query.threshold=200ms
db.logs.query.parameter_logging_enabled=false
db.logs.query.obfuscate_literals=true
```

Ở đây `INFO` ghi các query vượt ngưỡng; `VERBOSE` ghi bắt đầu và kết thúc các query bất kể ngưỡng. Chọn ngưỡng phù hợp với SLO và tránh log dữ liệu nhạy cảm. Bật log mọi truy vấn/plan trên hệ thống tải cao có thể làm log phình to hoặc tăng overhead. Đặc biệt, `db.logs.query.plan_description_enabled=true` có chi phí bổ sung và **không phù hợp bật thường xuyên**.

Query log có thể cho thấy **elapsed time, planning time, waiting time, page hits/faults và allocated bytes** tùy cấu hình/phiên bản. Đọc log theo **câu truy vấn cụ thể** và cửa sổ thời gian; không trộn các query plan khác nhau thành một mẫu thống kê.

### 5.3. Dynamic setting không phải là cấu hình lưu vĩnh viễn

Trên Neo4j Enterprise, một số setting có trường `isDynamic = true` và có thể chỉnh khi DBMS đang chạy:

```cypher
// Chỉ minh họa trong môi trường được phép thay đổi setting:
CALL dbms.setConfigValue('db.logs.query.threshold', '200ms');
```

**Điều kiện quan trọng:**

- Chỉ những setting **dynamic** mới thay được bằng procedure này; heap max và page cache size thông thường yêu cầu quy trình thay đổi/restart thích hợp.
- Thay đổi runtime bằng `dbms.setConfigValue` **không được ghi bền vững vào `neo4j.conf`**. Sau restart có thể trở lại giá trị file.
- Trong cluster, thay đổi này áp dụng **trên member đang kết nối**, không tự lan sang member khác.
- Việc ghi thay đổi lâu dài vào file/config management phải được quản lý riêng, đồng bộ trên các member phù hợp.

Trước và sau mọi thay đổi phải lưu được **giá trị thực tế** bằng `SHOW SETTINGS`, log start-up và các công cụ quản trị tương ứng.

## 6. Đặt giả thuyết và chọn một thay đổi có ý nghĩa

Một giả thuyết tốt có cấu trúc:

> **Nếu** tăng page cache thêm 4 GiB trong giới hạn RAM **vì** page faults duy trì cao ở steady state và disk read latency tăng, **thì** page faults/request và p95 latency của truy vấn đọc sẽ giảm; đồng thời không làm GC, RSS hoặc OOM xấu đi.

Đề xuất này khác câu “tăng RAM cho nhanh” vì có **dấu hiệu trước can thiệp và tiêu chí bác bỏ**.

| Triệu chứng quan sát | Giả thuyết | Thay đổi cần thử | Kết quả kỳ vọng và điều kiện dừng |
| --- | --- | --- | --- |
| Heap gần max, GC pause tăng, OOM/transaction failures | Heap không đủ cho live set | Tăng heap trong ngân sách RAM | GC pause/error giảm; không làm page faults/OS swap tăng |
| Page faults đều cao, hit ratio thấp ở steady state, disk bận | Page cache chưa chứa working set nóng | Tăng page cache có kiểm soát | Faults và I/O latency giảm, p95 tốt hơn |
| `SHOW TRANSACTIONS` cho thấy transaction rất lớn bị terminate | Query sinh state lớn hoặc ngưỡng per-transaction thấp | Tối ưu query/batch trước, xem xét transaction limit sau | Query chạy ổn định với memory bounded |
| Server log ghi Bolt thread pool hết thread | Quá nhiều active transaction so với pool | Rút ngắn transaction, kiểm tra pool rồi mới tăng limit | Rejections giảm mà CPU/GC vẫn an toàn |
| Driver connection acquisition timeout, server chưa bão hòa | Client connection pool quá nhỏ hoặc leak | Sửa leak, tăng pool driver hợp lý | Wait time giảm, throughput tăng mà error không tăng |
| Query plan có Cartesian product hoặc fan-out lớn | Truy vấn kém chọn lọc | Sửa Cypher, index, projection/DTO | `Rows`, `DB Hits`, latency giảm; có thể không cần đổi RAM |
| CPU quota 100%, heap/page cache đủ | CPU-bound hoặc oversubscription | Giảm concurrency, tối ưu query, đánh giá CPU | p95 tốt hơn hoặc throughput tăng trong cùng SLO |
| Checkpoint duration tăng cùng disk latency | I/O bị cạnh tranh | Kiểm tra storage/ghi và checkpoint policy | Checkpoint và commit ổn định, không tăng write latency |

**Ưu tiên sửa nguồn gốc lãng phí trước khi nâng cấu hình**: một chỉ số tăng chưa chứng minh nguyên nhân; cần một câu giải thích *vì sao* tham số được chọn tác động đến nút nghẽn đã đo.

## 7. Thiết kế một thí nghiệm A/B có thể kết luận

### 7.1. Các điều kiện cần giữ nguyên

Giữa **A (baseline)** và **B (candidate)**, cố giữ nguyên:

1. Phiên bản Neo4j/JDK/Driver, schema, index, graph size và số database.
2. Câu Cypher, parameter distribution, tỷ lệ read/write và kích thước response.
3. Số người dùng ảo, request pattern, concurrency, tốc độ tạo request.
4. Phần cứng, container limit, network, disk, cluster topology.
5. Cùng chế độ warm-up và khoảng đo, thời gian đủ dài để thấy GC/checkpoint.
6. Không chạy một job import/GDS đột xuất trong riêng một pha.
7. **Chỉ thay đổi một biến mục tiêu**, hoặc nếu phải đổi nhiều biến liên quan thì ghi rõ là một **cấu hình tổ hợp** và không quy kết đóng góp riêng của từng biến.

Điều kiện test phải phản ánh production: nếu sản phẩm có node degree cực lệch hoặc các truy vấn path dài, dữ liệu mẫu 100 node có thể cho kết luận sai.

### 7.2. Ba pha đo

```text
Baseline A (ổn định)
  |
  +-- Warm-up --> đo nhiều cửa sổ đồng nhất --> lưu plan, metrics, errors
  |
  v
Thay đổi đúng 1 setting có kế hoạch restart (nếu cần)
  |
  +-- Xác minh setting hiệu lực --> warm-up lại --> đo cùng workload
  |
  v
Candidate B
  |
  +-- So p95/p99, throughput, error, GC, page faults, RSS, I/O
  |
  +-- Đạt tiêu chí? --Có--> giữ cấu hình + tiếp tục theo dõi
                    |
                    +-- Không --> rollback + kiểm tra lại
```

Đo **nhiều lần/cửa sổ**, vì số đo một lần có thể bị ảnh hưởng bởi GC, filesystem cache, client load generator hoặc biến động network. Nếu có thể, thực hiện nhiều chu kỳ A–B hoặc A–B–A trong môi trường staging, tránh đánh đồng hiệu ứng warm-up/restart với hiệu quả của setting.

**Không chạy thử tải phá hoại trên production.** Nếu bắt buộc canary production, phải giới hạn số request, có người chịu trách nhiệm quan sát, ngưỡng dừng và rollback sẵn.

### 7.3. Thiết kế tập tải đại diện

Ví dụ chia request thành:
- **70%**: tìm node khách/sản phẩm bằng index và trả một page nhỏ.
- **20%**: duyệt 1–2 bước relationship của customer, trả DTO ngắn.
- **8%**: aggregate doanh thu theo thời gian.
- **2%**: ghi đơn hàng bằng transaction/`MERGE`.

**Tỷ trọng chỉ minh họa**. Với sản phẩm thực, lấy phân bố từ telemetry và query logs; bổ sung trường hợp cao điểm, high-degree nodes, query không tìm thấy dữ liệu, nhiều concurrent writes và client chậm.

Để kiểm chứng tính đúng, giữ cùng version dữ liệu hoặc dựng snapshot tương đương. Với workload ghi, mỗi vòng test có thể thay graph và làm kết quả so sánh không công bằng; dùng reset snapshot hoặc quy tắc dữ liệu/idempotency được chuẩn hóa.

## 8. Thí nghiệm 1: tăng JVM heap có thực sự giúp?

### 8.1. Giả thuyết cần có số liệu GC

Giả sử baseline đo được:
- Heap đã dùng ở gần giới hạn trong giờ cao điểm.
- GC pause dài cùng lúc p99 tăng.
- Không có vấn đề I/O nghiêm trọng hay plan mới xuất hiện.

Đây là bằng chứng hợp lý để **cân nhắc** tăng heap, nhưng chưa đủ để quyết định số GiB: phải xem live set, tốc độ cấp phát, transaction memory và tổng RAM.

Các setting tự quản lý thường dùng:

```properties
# Chỉ là ví dụ khi host/container có đủ RAM.
server.memory.heap.initial_size=10G
server.memory.heap.max_size=10G
```

Neo4j khuyến nghị đặt initial/max heap bằng nhau để tránh một số khoảng dừng không mong muốn khi heap mở rộng. **Không tăng `max_size` vượt quá RAM còn lại sau page cache, native memory và OS**.

### 8.2. Vì sao tăng heap có thể không giải quyết vấn đề?

- **GC chưa phải bottleneck:** nếu tổng GC time rất nhỏ, đổi heap khó có tác dụng đáng kể.
- **Memory leak hoặc result khổng lồ:** tăng heap chỉ khiến lỗi xảy ra muộn hơn.
- **Page cache bị lấy mất RAM:** tăng heap nhưng phải giảm page cache có thể làm page faults tăng.
- **Tăng latency của GC hoặc tác động JVM:** heap rất lớn không bảo đảm p99 luôn tốt hơn.
- **Transaction đợi lock:** không được sửa bằng tăng heap.

Sau đổi, đo **GC time/pause distribution, heap occupancy sau GC, p95/p99, page faults, RSS và throughput**. Nếu GC đã cải thiện mà latency không đổi, nút nghẽn có thể ở nơi khác; đừng tiếp tục tăng heap không có giới hạn.

## 9. Thí nghiệm 2: page cache cần tăng hay query đang đọc quá nhiều?

### 9.1. Đọc hit ratio cùng page faults và working set

Neo4j page cache giữ page của graph store/native indexes. Để phân tích:

- **`hit_ratio`**: tỷ lệ yêu cầu tìm page được đáp ứng từ cache.
- **`usage_ratio`**: tỷ lệ dung lượng cache đã dùng.
- **`page_faults`**: tổng số page fault tích lũy; phải lấy **chênh lệch theo thời gian**.
- **`bytes_read`** và disk read latency: giúp quan sát nhu cầu đọc dữ liệu thực.

```text
page_faults_per_sec ≈
  (counter tại t2 - counter tại t1) / (t2 - t1, giây)

page_faults_per_request ≈
  số fault tăng trong cửa sổ / số request hoàn tất trong cửa sổ
```

Một tổng counter lớn sau nhiều ngày uptime **không đồng nghĩa hiện tại cache thiếu**. Sau restart, cache lạnh hoặc page-cache warmup sẽ tạo spike faults; phải so phần **steady state sau warm-up**.

### 9.2. Ví dụ thay page cache

```properties
# Baseline A — ví dụ:
server.memory.pagecache.size=8G
```

```properties
# Candidate B — chỉ khi ngân sách RAM cho phép:
server.memory.pagecache.size=12G
```

Giữ heap, data, load, storage và query không đổi nếu có thể. Kiểm tra:

- Faults/s và faults/request giảm có hệ thống không?
- p95/p99 latency có tốt lên trong **cùng offered load** không?
- Disk I/O wait, bytes read có giảm không?
- Host có swap/OOM hoặc JVM RSS tăng bất thường không?

**Nếu hit ratio đã 99,9%, page faults gần như bằng 0 và `PROFILE` có hàng triệu DB Hits do một query quá rộng**, tăng page cache không phải bước đầu. Hãy sửa Cypher, index hoặc giới hạn traversal.

### 9.3. Working set khác tổng dung lượng database

Không bắt buộc page cache phải chứa toàn bộ store mới có hiệu năng tốt. Nếu graph lớn 500 GiB nhưng 95% request chỉ chạm vùng “nóng” 30 GiB, mục tiêu là chứa **working set được truy cập thực tế** và giữ vùng đệm phù hợp; không đơn giản mua 500 GiB RAM.

Ngược lại, nếu hầu hết graph được đọc ngẫu nhiên, working set có thể gần bằng toàn store và storage latency quan trọng hơn. Đo theo use case, không chỉ nhìn tổng kích thước trên ổ đĩa.

## 10. Thí nghiệm 3: giới hạn transaction memory và lỗi OOM

### 10.1. Ba setting không có cùng phạm vi

| Setting | Phạm vi | Tác dụng |
| --- | --- | --- |
| `dbms.memory.transaction.total.max` | Tổng transaction memory trong DBMS | Giới hạn tổng để bảo vệ server |
| `db.memory.transaction.total.max` | Transaction memory của một database | Tránh một database chiếm quá nhiều |
| `db.memory.transaction.max` | Một transaction | Hạn chế một query/transaction quá lớn |

Các giới hạn không phải “RAM bổ sung”. Nếu chạm giới hạn, Neo4j có thể **terminate transaction** nhằm bảo vệ hệ thống. Không giải quyết bằng cách đặt toàn bộ limit bằng 0 (unlimited) trên production.

### 10.2. Tìm transaction gây vấn đề

Trong môi trường có quyền:

```cypher
SHOW TRANSACTIONS;
```

Có thể xem các trường như `estimatedUsedHeapMemory`, `currentQueryAllocatedBytes`, thời gian chờ và câu truy vấn đang chạy tùy phiên bản/quyền. Neo4j cũng có:

```cypher
CALL dbms.listPools();
```

Các số đo bộ nhớ transaction là **ước lượng**, có thể khác bộ nhớ thực tế hoặc đếm bảo thủ khi có cấu trúc dùng chung. Không kết luận “database thiếu 8 GiB” chỉ từ một lỗi transaction memory limit.

### 10.3. Thay đổi quy mô transaction trước

Ví dụ một importer thực hiện:

```cypher
// Có thể tạo transaction quá lớn nếu $rows là cả triệu bản ghi:
UNWIND $rows AS row
MERGE (n:Product {sku: row.sku})
SET n.name = row.name;
```

Thay vì cố tăng giới hạn vô hạn, chia batch, dùng index/uniqueness constraint cho khóa và retry có kiểm soát. Với `LOAD CSV` theo lô, dùng `CALL { ... } IN TRANSACTIONS` đúng ngữ cảnh **implicit transaction**; không bọc trong managed transaction của Java Driver.

Nếu vẫn cần nâng limit cho một nghiệp vụ đã được tối ưu, đo memory/transaction, concurrent transaction count, GC, OOM và các thao tác bị terminate trước/sau. Việc nâng limit một transaction mà 100 transaction khác cũng mở rộng có thể khiến **tổng heap vượt sức chịu tải**.

## 11. Thí nghiệm 4: Bolt thread pool và Java Driver connection pool

### 11.1. Hai pool ở hai phía khác nhau

```text
Java/Spring Service                           Neo4j Server
   |                                                |
Driver connection pool  -- Bolt connections --> Bolt thread pool
   |                                                |
Session / tx lifecycle                      Cypher runtime / locks / I/O
```

| Dấu hiệu | Có thể nghẽn ở đâu? | Việc kiểm tra trước khi tăng pool |
| --- | --- | --- |
| Java báo connection acquisition timeout | Driver pool hết connection hoặc session leak | Số session mở, tx duration, pool setting, retry, load |
| Neo4j ghi nhận Bolt thread pool hết worker/reject job | Bolt server thread pool | Active transactions, transaction leak, số worker và CPU |
| Pool có chỗ nhưng p95 tăng | Query/lock/CPU/I/O thay vì pool | `PROFILE`, waiting time, GC, CPU, I/O |
| Tăng concurrency làm throughput giảm | Contention/oversubscription | Kiểm tra lock, CPU saturation, page cache, disk |
| Nhiều connection nhàn rỗi | Connection count cao nhưng work thấp | Không tăng thread pool chỉ vì thấy nhiều connection |

Neo4j có các setting phía server:

```properties
# Ví dụ kiểm soát Bolt server pool; không phải mặc định tối ưu:
server.bolt.thread_pool_min_size=5
server.bolt.thread_pool_max_size=100
server.bolt.thread_pool_keep_alive=10m
```

Tài liệu Neo4j cho biết **mặc định Bolt pool thường phù hợp với phần lớn workload**. Một transaction explicit/implicit đang hoạt động giữ worker thread theo cơ chế server; cần **đóng transaction sớm và đúng** trước khi tăng số thread.

Java Driver có connection pool riêng với các lựa chọn như maximum connection pool size và acquisition timeout. Giữ **một `Driver` dùng chung**, tạo session ngắn theo operation, consume result và đóng session. **Đừng tạo một Driver mới cho mỗi HTTP request**.

### 11.2. Tăng pool có thể làm tệ hơn

Giả sử CPU server đã gần hết nhưng ứng dụng tăng max client pool từ 100 lên 1.000. Thêm 900 request đồng thời có thể khiến:
- More context switching.
- Nhiều transaction giữ object/lock và heap.
- GC và page cache pressure tăng.
- p99 xấu đi, timeout nhiều hơn.
- Throughput hoàn tất **không tăng**, dù số connection tăng.

Chỉ tăng pool khi chứng minh **pool là bottleneck** và server vẫn có khả năng xử lý thêm tải. Thử từng mức nhỏ, đo đỉnh concurrency và hiệu quả thực; không chọn setting theo một con số “càng lớn càng tốt”.

## 12. Thí nghiệm 5: CPU, I/O, checkpoint và storage

### 12.1. Dấu hiệu CPU-bound

Khi CPU process/host hoặc container CPU quota bị bão hòa, throughput đạt trần nhưng các request tiếp tục xếp hàng:

- Xác định phần CPU là Cypher, GC, Java runtime hay tiến trình khác.
- Xem query plan có sort, aggregation, path search hoặc tính toán biểu thức tốn kém.
- Giảm fan-out/Rows trước; cân nhắc index và read model.
- Điều chỉnh concurrency để tránh CPU thrashing; **thêm thread không tự tăng CPU quota**.
- Chỉ tăng CPU sau khi đã đo độ cải thiện của các cách sửa có chi phí thấp hơn.

### 12.2. Dấu hiệu I/O-bound

Khi page faults và disk read latency cùng tăng, xem:
- Working set có lớn hơn page cache không.
- Storage throughput/IOPS có đạt giới hạn không.
- Đọc tuần tự hay ngẫu nhiên, dữ liệu nóng có được cache không.
- Có checkpoint, index rebuild, backup, import, GDS projection trùng giờ không.

Khi write throughput cao, phải quan sát **checkpoint duration**, flush và transaction log. Nếu checkpoint gần bằng khoảng cách giữa các checkpoint, disk có thể trở thành nút nghẽn. Chỉ chỉnh các setting như `db.checkpoint.iops.limit` hay `server.memory.pagecache.flush.buffer.*` khi đã xác định storage budget và tài liệu version; nâng IOPS limit không đúng lúc có thể làm **commit latency xấu đi**.

### 12.3. DB Hits không phải physical I/O

`DB Hits` trong `PROFILE` là đơn vị thao tác với storage engine, không phải số read vật lý từ SSD. Một query có 50.000 DB Hits có thể chạy khá nhanh nếu dữ liệu nằm trong page cache, nhưng 50.000 thao tác cũng có thể là dấu hiệu query không cần thiết duyệt rộng. Luôn xem **Rows + DB Hits + page faults + latency** trong bối cảnh.

## 13. Kịch bản đánh giá: tăng RAM hay sửa truy vấn?

Xét một kết quả **hoàn toàn giả định** để luyện phân tích, không phải benchmark của Neo4j:

| Chỉ số | Baseline A | B: tăng page cache 8 → 12 GiB | C: giữ cache, sửa query |
| --- | ---: | ---: | ---: |
| p95 latency | 900 ms | 860 ms | 190 ms |
| p99 latency | 1.900 ms | 1.870 ms | 380 ms |
| Throughput hoàn tất | 95 req/s | 98 req/s | 130 req/s |
| `DB Hits` cho query chính | 75.000 | 75.000 | 2.200 |
| Page-cache hit ratio | 99,2% | 99,4% | 99,4% |
| Page faults/request | 0,5 | 0,4 | 0,1 |
| Error rate | 0,1% | 0,1% | 0,05% |

Điều kiện so sánh: cùng snapshot dữ liệu, cùng load generator và offered load/điều kiện đo tương đương. Nếu `achieved throughput` ở pha C tăng, cần làm rõ **bài thử đang đẩy đủ tải** để phân biệt hệ thống đã xử lý nhiều hơn với đơn thuần giảm requested load.

**Diễn giải:**

- Page cache ban đầu đã tương đối hiệu quả, nên tăng 4 GiB tạo lợi ích nhỏ.
- Query B vẫn có 75.000 DB Hits vì đường duyệt không đổi.
- Query C giảm DB Hits/Rows bằng cách bắt đầu từ khóa có index và giới hạn traversal, nên p95 giảm mạnh.
- Phương án hợp lý là **giữ sửa query**, không vội cấp thêm RAM cho mọi node; sau đó mới xác minh với workload lớn hơn.

**Nhưng cần tránh kết luận vội:** B và C là hai thay đổi **khác bản chất**, nên để xác định đóng góp mỗi yếu tố, đo trên cùng một cấu hình gốc, không thay cùng lúc cả query lẫn page cache rồi khẳng định một thay đổi là nguyên nhân duy nhất.

## 14. Java Driver: thu thập latency có phân tách

Ví dụ Java Driver 6.x, với `Driver driver` được tạo một lần ở ứng dụng, đo **thời gian trả danh sách kết quả ngắn**:

```java
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

record ProductView(String sku, String name) {}

static List<ProductView> loadProducts(
        Driver driver, String supplierId, int requestedLimit) {
    int limit = Math.max(1, Math.min(requestedLimit, 50));

    String cypher = """
        MATCH (s:Supplier {supplierId: $id})-[:SUPPLIES]->(p:Product)
        WHERE p.active = true
        RETURN p.sku AS sku, p.name AS name
        ORDER BY sku
        LIMIT $limit
        """;

    long started = System.nanoTime();

    try (Session session = driver.session(
            SessionConfig.forDatabase("neo4j"))) {
        List<ProductView> result = session.executeRead(tx ->
            tx.run(cypher, Map.of("id", supplierId, "limit", limit))
              .list(r -> new ProductView(
                  r.get("sku").asString(),
                  r.get("name").asString()
              ))
        );

        long durationMs = TimeUnit.NANOSECONDS.toMillis(
            System.nanoTime() - started
        );

        System.out.printf("neo4j_read_ms=%d, count=%d%n",
            durationMs, result.size());

        return result;
    }
}
```

Đây là **đo đoạn truy cập Neo4j bằng wall-clock phía client** gồm lấy session, chạy transaction, truyền dữ liệu và mapping; không phải chỉ thời gian server thực thi Cypher. Trong production, dùng metric library/tracing có histogram thay vì `System.out` cho từng request và đo **cả khi exception** bằng `try/finally`/instrumentation. Không log supplier ID nhạy cảm hay nội dung record tùy ý.

Khi so API đồng bộ, bất đồng bộ và reactive, giữ **cùng Cypher, cùng dữ liệu và kiểu result consumption tương đương**. Reactive có backpressure nhưng không tự làm giảm DB Hits; async không giúp khi bottleneck là query plan hoặc transaction lock.

## 15. Cấu hình trong Docker, Kubernetes, cluster và AuraDB

### 15.1. Container: tính từ giới hạn thực

Ví dụ biểu diễn setting Neo4j trong Docker:

```yaml
services:
  neo4j:
    image: neo4j:2026.10
    environment:
      NEO4J_server_memory_heap_initial__size: "6G"
      NEO4J_server_memory_heap_max__size: "6G"
      NEO4J_server_memory_pagecache_size: "6G"
    mem_limit: 16g
```

**Đây chỉ là minh họa cú pháp**, không phải một Docker Compose production hoàn chỉnh (thiếu volume, authentication, backup, network security, v.v.). Trong Neo4j Docker, dấu chấm trong setting chuyển thành dấu gạch dưới và dấu gạch dưới gốc thành hai dấu gạch dưới. Kiểm tra version image thực tế có tồn tại và dùng định dạng setting tương ứng.

Với limit 16 GiB, heap + page cache = 12 GiB trong ví dụ, để lại khoảng 4 GiB cho native memory, OS/container process và headroom. **Không coi 4 GiB là mức dự phòng luôn đủ**; phải đo RSS và kiểm thử workload thực, nhất là khi có nhiều thread, GDS hoặc cấu hình khác.

Kubernetes bổ sung rủi ro **CPU throttling, OOMKilled, eviction, thay đổi request/limit và persistent volume latency**. Phải so số liệu trước/sau theo từng pod và chú ý đợt restart có thể làm page cache lạnh.

### 15.2. Cluster: không chỉ kiểm tra một server

Trong cluster, kiểm tra:
- Các thành viên có **cấu hình và bộ nhớ hiệu lực** tương ứng không.
- Read requests đang được route đến member nào, write/leader load có khác nhau không.
- Page cache, GC, CPU và I/O **theo từng member**, tránh chỉ nhìn trung bình toàn cluster.
- Restart/rolling change có tác động đến availability, cache warmup và rebalancing/routing không.
- Dynamic setting thay đổi ở một member không tự lan sang các member khác.

Nếu một replica p99 xấu hơn do disk chậm, việc tăng RAM trên member khác có thể không giải quyết request được route tới replica chậm.

### 15.3. AuraDB: tối ưu trong giới hạn dịch vụ quản lý

Trên AuraDB, người dùng **không tự chỉnh `neo4j.conf` và chạy `neo4j-admin` theo cách của self-hosted**. Các số liệu, quyền quan sát và lựa chọn instance size/phương thức scaling phụ thuộc gói dịch vụ.

Quy trình phù hợp:
1. Đo request/Cypher và dùng các metrics Aura cung cấp.
2. Sửa query plan, index, batch và cách Java Driver sử dụng pool trước.
3. Khi giới hạn tài nguyên được chứng minh, đánh giá nâng tier/instance size.
4. So trước/sau với cùng workload, tính cả chi phí mới và khả năng rollback theo chính sách dịch vụ.

Không đưa lệnh thay `server.memory.pagecache.size` hoặc `dbms.setConfigValue` cho người dùng Aura như một thao tác họ có thể tùy ý chạy.

## 16. Quy trình vận hành và rollback có thể kiểm toán

Trước mọi thay đổi tài nguyên, lập một bản ghi ngắn:

| Trường | Ví dụ |
| --- | --- |
| Change ID | `neo4j-perf-2026-11-25-01` |
| Vấn đề | p95 đọc đơn hàng tăng > 600 ms ở 100 req/s |
| Baseline | Truy vấn X, p95, p99, errors, `Rows`/`DB Hits`, GC, page faults, disk |
| Giả thuyết | Page faults/request cao kéo dài ở steady state |
| Một biến cần đổi | `server.memory.pagecache.size`: 8G → 12G |
| Phạm vi | Staging một thành viên, cùng dữ liệu/load; sau đó canary nếu được phép |
| Điều kiện đạt | p95 tốt hơn đáng kể, error không tăng, GC/RSS ổn định |
| Điều kiện dừng | OOM, swap, p99/error tăng, không đạt lợi ích dự kiến |
| Rollback | Khôi phục 8G, restart theo kế hoạch, verify setting, warm-up và đo lại |
| Kết luận | Giữ/bỏ thay đổi và lý do kèm số đo |

**Rollback không chỉ là thay một dòng config.** Nếu setting yêu cầu restart, rollback cũng có thể yêu cầu restart, ảnh hưởng cache warmup/availability. Với cluster, phải xác định thứ tự rolling change, thời gian ổn định và khả năng khôi phục. Với thay đổi index hoặc query, cần kế hoạch tương ứng để bảo toàn dữ liệu và kết quả nghiệp vụ.

Đừng so ngay **một phút sau restart** với hệ thống đã chạy nhiều ngày; cache/JIT/GC và workload chưa ở điều kiện tương đương. Luôn đánh dấu thời điểm restart, failover, deployment và import trong dashboard đo.

## 17. Những ngộ nhận thường gây điều chỉnh sai

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Neo4j chậm thì cứ tăng heap.” | Chỉ tăng khi số liệu heap/GC/transaction cho thấy heap là nút nghẽn |
| “RAM 32 GiB thì heap 24G và page cache 24G vẫn được.” | Tổng đã vượt RAM; còn native/OS và memory limit |
| “Page cache hit ratio 99% chứng minh query nhanh.” | Query vẫn có thể nhiều `DB Hits`, CPU, sort hoặc lock |
| “Page faults counter rất lớn nghĩa là cache thiếu ngay lúc này.” | Phải xem tốc độ theo thời gian; sau restart/warmup thường fault cao |
| “`DB Hits` là số lần đọc SSD.” | Là phép đếm thao tác storage engine, khác page faults/I/O |
| “`PROFILE` không sửa graph.” | PROFILE chạy thật, cả với write query |
| “Tăng `db.memory.transaction.max` tạo thêm bộ nhớ.” | Chỉ nới giới hạn; có thể làm OOM khi nhiều transaction đồng thời |
| “Dùng `--memory=32g` từ memrec là đủ tối ưu.” | Đây là heuristic khởi điểm, cần thử trên workload thật |
| “Pool client lớn bằng số user là tốt.” | Pool quá lớn có thể làm contention và p99 xấu đi |
| “Nhiều Bolt connection nghĩa là thiếu Bolt thread.” | Connection idle không giống active transaction; phải xem rejections/worker utilization |
| “Tăng CPU giúp query full scan có index tốt.” | Query plan/index phải được xử lý riêng |
| “`SHOW SETTINGS` của một cluster member đại diện tất cả.” | Setting phản ánh member đang thực thi lệnh |
| “Dynamic setting đã chỉnh sẽ giữ sau restart.” | Runtime change không tự ghi vào file cấu hình |
| “p50 giảm, p99/error tăng vẫn là thắng.” | Phải thỏa SLO và tính ổn định của hệ thống |
| “Benchmark một lần là đủ.” | Cần nhiều cửa sổ, warm-up, dữ liệu và tải đại diện |
| “Trên Aura cũng có thể sửa `neo4j.conf`.” | Khả năng điều chỉnh phụ thuộc dịch vụ; không có quyền file self-host |
| “Tăng tài nguyên mà không thay query vẫn luôn nhanh.” | Truy vấn kém chọn lọc có thể ăn thêm tài nguyên mà không cải thiện đáng kể |

## 18. Checklist trước khi đồng ý tăng tài nguyên

1. **Xác định sự cố:** endpoint/query/job nào chậm, từ thời điểm nào, SLO nào bị vi phạm?
2. **Phân loại tải:** read/write, traversal sâu, batch import, GDS, concurrency, data skew.
3. **Ghi baseline:** p50/p95/p99, throughput, errors, pool wait, GC, page cache, CPU, I/O.
4. **Xác minh query:** `EXPLAIN`/`PROFILE`, index/constraint, fan-out, `Rows`, `DB Hits`, result size.
5. **Xác định giới hạn:** RAM host/container, heap, page cache, native, transaction, CPU quota, storage.
6. **Đặt giả thuyết:** “setting X giải quyết metric Y vì cơ chế Z”.
7. **Xác nhận khả năng thay đổi:** version, edition, setting dynamic hay static, quyền và downtime.
8. **Chuẩn bị đối chứng:** same data, parameters, concurrency, warm-up, khoảng đo, client.
9. **Thử một thay đổi:** ghi giá trị trước/sau và phạm vi member/pod/instance.
10. **Đánh giá đa chiều:** latency/throughput, error, correctness, GC, RSS, faults, CPU, I/O, cost.
11. **Rollback nếu cần:** có phương án quay lại và kiểm tra sau khi hoàn nguyên.
12. **Lưu bằng chứng:** biểu đồ, log đã khử thông tin nhạy cảm, plan, cấu hình, kết luận và owner.

## 19. Bài tập tự luyện

1. Một máy có 32 GiB RAM, heap 8 GiB, page cache 16 GiB, phần còn lại cho OS/native. Có đề xuất tăng heap lên 24 GiB mà giữ cache 16 GiB. Chỉ ra vấn đề và cách thiết kế kiểm chứng.
2. p95 tăng nhưng page-cache hit ratio là 99,9%, page faults/s gần 0. `PROFILE` cho thấy `Expand(All)` sinh 1 triệu `Rows` từ một khách hàng. Bạn ưu tiên đổi setting hay sửa Cypher? Vì sao?
3. Một JVM có GC pause tăng đúng lúc p99 tăng; page cache hit ratio vẫn ổn. Lập giả thuyết và kế hoạch thử heap 8G → 10G, nêu metric và điều kiện rollback.
4. Một transaction nhập dữ liệu khổng lồ bị chấm dứt bởi `db.memory.transaction.max`. So sánh cách tăng ngưỡng với việc chia batch và index khóa `MERGE`.
5. 100 connection từ Java Driver nhưng chỉ 10 active transaction; không có Bolt rejections. Có cần tăng `server.bolt.thread_pool_max_size` không? Cần kiểm tra thêm gì?
6. Vẽ pipeline A–B–A cho thay đổi page cache, nêu cách xử lý cold cache sau mỗi restart để không tạo kết luận sai.
7. Với Neo4j Enterprise cluster, bạn gọi `dbms.setConfigValue(...)` trên một member. Vì sao phải kiểm tra các member còn lại và file cấu hình?
8. Bạn đo được counter page faults tăng từ 8.000 lên 11.000 trong 60 giây, 1.500 request hoàn tất. Tính faults/s và faults/request; giải thích giới hạn của việc dùng riêng hai con số.
9. Lập một ma trận 6 metric để so sánh tác động của tăng CPU quota với tối ưu index của truy vấn `MATCH (s:Supplier)-[:SUPPLIES]->(p:Product)`.
10. Một workload tăng throughput 15% sau khi tăng pool, nhưng p99 tăng gấp đôi và error rate tăng. Có nên triển khai không? Liên hệ với SLO đã xác định.

## 20. Ghi nhớ

- **Tăng tài nguyên là một giả thuyết kỹ thuật cần được kiểm chứng**, không phải phản xạ mặc định khi query chậm.
- **Neo4j heap, page cache, transaction memory, Bolt pool, CPU và storage** là các nguồn lực khác nhau và có thể cạnh tranh nhau.
- **Đo baseline trước**: p95/p99, throughput, error, `EXPLAIN`/`PROFILE`, GC, page faults, I/O và client pool.
- **`DB Hits` không phải disk I/O**; page-cache hit cao không chứng minh query plan tốt. Xem cả cardinality/fan-out và latency.
- **Một thay đổi mỗi thí nghiệm**, workload/data/parameters tương đương, warm-up và chạy đủ lâu để thấy GC/checkpoint/tải đỉnh.
- **Đọc giá trị cấu hình hiệu lực**, kiểm tra static/dynamic, edition/tier và member/pod; thay runtime dynamic không tự ghi vào file.
- **Kết luận bằng kết quả đa chiều**: truy vấn đúng, latency và throughput đạt SLO, error không tăng, tài nguyên bền vững, chi phí hợp lý.
- **Khi thay đổi không hiệu quả hoặc gây rủi ro, rollback có kế hoạch** rồi điều tra nguyên nhân khác thay vì tiếp tục “tăng thêm chút nữa”.

### Tài liệu tham khảo chính thức

- [Neo4j Operations Manual — Memory configuration](https://neo4j.com/docs/operations-manual/current/performance/memory-configuration/)
- [Neo4j Operations Manual — Get initial memory recommendations](https://neo4j.com/docs/operations-manual/current/configuration/neo4j-admin-memrec/)
- [Neo4j Operations Manual — Configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/configuration-settings/)
- [Neo4j Operations Manual — Show configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/show-settings/)
- [Neo4j Operations Manual — Update dynamic settings](https://neo4j.com/docs/operations-manual/current/configuration/dynamic-settings/)
- [Neo4j Operations Manual — Essential metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/essential/)
- [Neo4j Operations Manual — Metrics reference](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/reference/)
- [Neo4j Operations Manual — Logging and query log](https://neo4j.com/docs/operations-manual/current/monitoring/logging/)
- [Neo4j Operations Manual — Bolt thread pool configuration](https://neo4j.com/docs/operations-manual/current/performance/bolt-thread-pool-configuration/)
- [Neo4j Operations Manual — Garbage collector tuning](https://neo4j.com/docs/operations-manual/current/performance/gc-tuning/)
- [Neo4j Operations Manual — Disks, RAM and other tips](https://neo4j.com/docs/operations-manual/current/performance/disks-ram-and-other-tips/)
- [Neo4j Operations Manual — Show and terminate transactions](https://neo4j.com/docs/operations-manual/current/database-internals/show-and-terminate-transactions/)
- [Neo4j Operations Manual — Docker-specific configuration settings](https://neo4j.com/docs/operations-manual/current/docker/ref-settings/)
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Neo4j Java Driver Manual — Connect to the database](https://neo4j.com/docs/java-manual/current/connect/)
