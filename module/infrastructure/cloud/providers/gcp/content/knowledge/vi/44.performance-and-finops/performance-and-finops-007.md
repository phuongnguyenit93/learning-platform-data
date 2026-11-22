# Tối ưu Cloud SQL, AlloyDB và Spanner theo tải thực tế

Một ứng dụng thương mại điện tử chạy trên Google Cloud có thể phục vụ vài trăm request mỗi giây vào ngày thường, nhưng tăng gấp nhiều lần trong đợt khuyến mại. Nhóm phát triển thấy thời gian phản hồi API tăng từ 120 ms lên vài giây, số kết nối cơ sở dữ liệu tăng đột biến, CPU cao và một số giao dịch bị timeout. Phản ứng dễ gặp nhất là tăng vCPU hoặc mua một dịch vụ database đắt hơn. Cách này có thể che triệu chứng trong thời gian ngắn nhưng không sửa được câu SQL thiếu chỉ mục, transaction giữ khóa quá lâu hay một khóa dữ liệu đang bị ghi dồn.

**Tối ưu database theo tải thực tế** là quá trình đo lường, xác định điểm nghẽn, lựa chọn thay đổi nhỏ nhất có hiệu quả và kiểm chứng bằng workload đại diện. Với Google Cloud, ba dịch vụ quan hệ phổ biến có những cơ chế khác nhau: **Cloud SQL** cung cấp MySQL, PostgreSQL và SQL Server được quản lý; **AlloyDB for PostgreSQL** tập trung vào PostgreSQL hiệu năng cao với read pools và các khả năng chuyên biệt; **Spanner** là cơ sở dữ liệu SQL phân tán với mô hình phân vùng theo khóa và mở rộng compute theo quy mô instance.

Trong module **CLOUD_PROVIDERS_GCP**, bài học nối kiến thức triển khai Compute Engine, GKE, Cloud Run, IAM và mạng với phân tích độ tin cậy, hiệu năng và chi phí. Mục tiêu không phải chỉ làm benchmark nhanh hơn: ứng dụng cần đạt SLO dưới tải dự báo với chi phí hợp lý và quy trình thay đổi có thể rollback.

Sau bài học, bạn có thể:

- Phân loại workload theo OLTP, đọc nhiều, ghi nhiều, báo cáo và phân bố lưu lượng.
- Xây baseline bằng p50/p95/p99 latency, throughput, CPU, bộ nhớ, I/O, connection, lock và chi phí.
- Dùng Query Insights và execution plan để phân biệt query chậm với thiếu tài nguyên.
- Điều chỉnh connection pooling, timeout, index, transaction và read routing cho Cloud SQL.
- Sử dụng AlloyDB read pool, index advisor và columnar engine đúng loại workload.
- Nhận diện Spanner hotspots, thiết kế khóa phân tán tốt và điều chỉnh compute/autoscaling.
- Tổ chức load test có kiểm soát, tính chi phí trên mỗi giao dịch thành công và lập runbook sản xuất.

## 1. So sánh ba dịch vụ trước khi tối ưu

Không có quy tắc “AlloyDB luôn nhanh hơn Cloud SQL” hoặc “Spanner luôn rẻ hơn khi nhiều request”. Sự phù hợp phụ thuộc vào schema, tỷ lệ đọc/ghi, đặc tính transaction, vùng truy cập và nhu cầu mở rộng.

| Tiêu chí | Cloud SQL | AlloyDB for PostgreSQL | Spanner |
|---|---|---|---|
| Kiểu hệ quản trị | MySQL, PostgreSQL, SQL Server được quản lý | PostgreSQL tương thích, có các tối ưu riêng của AlloyDB | SQL phân tán; GoogleSQL hoặc PostgreSQL dialect |
| Tăng năng lực ghi | Chủ yếu scale up primary và tối ưu SQL | Scale up primary, tối ưu PostgreSQL | Phân phối dữ liệu/compute; scale instance và giảm hotspots |
| Mở rộng đọc | Read replicas, phụ thuộc engine/edition | Read pool với nhiều nodes và endpoint | Đọc phân tán theo splits/replicas của Spanner |
| HA và DR | HA, backup/PITR, replica theo khả năng | HA theo kiến trúc AlloyDB, backup/DR | Regional/multi-region configurations, replication |
| Đặc trưng tối ưu | Kích thước máy, index, cache, connections, I/O | Read pool, columnar engine, query/index insights | Key distribution, query plan, CPU, transaction contention |
| Thích hợp | Ứng dụng SQL truyền thống, muốn ít đổi mã | PostgreSQL cần throughput/query performance cao | SQL quan hệ cần quy mô phân tán và tính nhất quán mạnh |
| Tránh ngộ nhận | HA standby không phải read replica để chia tải | Read pool không biến primary thành multi-writer | Thêm nodes không giải quyết một hot key |

Việc chọn database là quyết định kiến trúc và chi phí dài hạn. Trước khi chuyển hệ quản trị, hãy thử tối ưu SQL, schema, connection management và cấu hình hiện tại để xác định giới hạn thực sự.

## 2. Định nghĩa workload và tiêu chí thành công

Tối ưu chỉ có ý nghĩa khi biết **tải thực tế** gồm những gì. Ghi lại ít nhất:

- **QPS/TPS:** số query hoặc transaction mỗi giây, phân biệt đọc và ghi.
- **Tỷ lệ đọc/ghi:** ví dụ 85% SELECT, 10% UPDATE, 5% INSERT.
- **Hình dạng query:** lookup theo khóa, join nhiều bảng, aggregate, scan, batch, truy vấn thời gian.
- **Concurrency:** số request đồng thời, số connection đang mở, kích thước pool ở mỗi ứng dụng.
- **Phân bố dữ liệu:** số row/table, độ lệch tenant, kích thước index, working set, tốc độ tăng trưởng.
- **Vị trí:** ứng dụng và database cùng region hay qua WAN; có client đa vùng không.
- **Tải đặc biệt:** peak theo giờ, bulk import, migration, backup, maintenance, báo cáo cuối tháng.
- **Chính sách nhất quán:** request nào bắt buộc read-after-write, request nào chấp nhận lag.

### Ví dụ SLO

Giả sử service checkout có mục tiêu:

| SLI | SLO minh họa |
|---|---|
| Tỷ lệ đơn hàng hoàn tất | Ít nhất 99,9% các request hợp lệ trong cửa sổ 28 ngày |
| p95 API latency | Dưới 300 ms trong tải bình thường |
| p99 database query latency | Dưới 120 ms cho đường checkout chính |
| Transaction abort/deadlock | Dưới ngưỡng được đội sản phẩm phê duyệt |
| Database connection checkout | p95 dưới 20 ms |
| Khả năng phục vụ peak | 3 lần tải nền mà không vượt error budget |

Đây là mục tiêu **ví dụ**, không phải ngưỡng Google Cloud áp dụng cho mọi cơ sở dữ liệu. Nếu API còn gọi payment gateway hoặc dịch vụ vận chuyển, ngân sách database phải được chia từ deadline toàn request, thay vì cho database dùng hết 300 ms.

### Phân biệt latency và throughput

**Latency** là thời gian thực hiện một request; **throughput** là số request hoàn tất trên một đơn vị thời gian. Một hệ thống có thể tăng throughput nhưng p99 latency xấu đi do xếp hàng. CPU trung bình 40% cũng không bảo đảm không nghẽn nếu một thread, một khóa hoặc một Spanner split bị nóng.

Một phép phân rã có ích:

\[
T_{request} = T_{queue} + T_{connection} + T_{network} + T_{execution} + T_{serialization}
\]

Các số đo không nhất thiết có sẵn dưới cùng một metric; sử dụng application tracing và database metrics để ước lượng. Nếu `T_queue` chiếm đa số, thêm index có thể không giải quyết được; nếu `T_execution` cao do full scan thì cần xem query plan.

## 3. Quy trình chẩn đoán: đo rồi mới thay đổi

Một vòng điều tra có thể dùng bảy bước:

1. **Chốt thời gian:** xác định khung xảy ra sự cố và mốc deploy, migration, traffic peak.
2. **Phân loại lỗi:** latency, 5xx, deadlock, pool timeout, replication lag hay I/O saturation.
3. **Đối chiếu:** so với cùng loại workload ở giai đoạn ổn định, tránh chỉ nhìn một điểm.
4. **Tìm top contributors:** query nào chiếm tổng database load hoặc tail latency lớn nhất.
5. **Xem execution plan:** index scan, sequential scan, sort, join, temp spill, remote work.
6. **Kiểm tra tài nguyên:** CPU, memory, storage IOPS, cache hit, lock waits, connections và network.
7. **Thử một thay đổi:** benchmark A/B, quan sát effect, rollback nếu làm xấu SLO.

### Ma trận triệu chứng và giả thuyết

| Triệu chứng | Giả thuyết nên kiểm tra trước | Dữ liệu xác minh |
|---|---|---|
| p99 tăng, CPU thấp | Lock waits, pool exhaustion, network, I/O waits | Query Insights wait events, pg_stat_activity, Hikari metrics |
| CPU duy trì cao | Query scan, join kém, thiếu compute | Top SQL, execution plans, CPU trend |
| Latency cao khi peak | Pool/connection storm, queueing, quota | Active connections, checkout wait, QPS, concurrency |
| Chỉ một tenant chậm | Data skew, hot key/split, index skew | Query tags, tenant dimensions, Key Visualizer |
| Replica lag tăng | Primary ghi nhanh, replica thiếu tài nguyên, query dài trên replica | Replica lag, replica CPU, WAL/replication metrics |
| Write throughput không tăng dù thêm compute | Lock contention, hot key, serialized transaction | Transaction aborts, lock waits, split hotspots |
| Dùng nhiều bộ nhớ và OOM | Query hash/sort, cache pressure, quá nhiều connections | Working set, temp files, active sessions |
| Chi phí tăng nhưng TPS giữ nguyên | Overprovision, idle replicas, dữ liệu/index phình | Billing export, utilization và unit cost |

Không kết luận nguyên nhân chỉ từ CPU: lượng request, contention và tải query có thể đổi đồng thời.

## 4. Quan sát bằng Cloud Monitoring và Query Insights

Google Cloud cung cấp Cloud Monitoring, Cloud Logging và các công cụ truy vấn chuyên biệt. Theo dõi **metric ở database** và **metric phía ứng dụng**; một phía không phản ánh đầy đủ các lần đợi connection hoặc request bị hủy trước khi query bắt đầu.

### Dashboard tối thiểu

| Nhóm | Chỉ số |
|---|---|
| User experience | Success rate, p95/p99 latency, timeout count |
| Workload | Read/write QPS, TPS, request concurrency, rows examined |
| Compute | CPU high-priority/total khi có, memory pressure |
| Storage | IOPS/throughput, latency, disk used, temp spills, cache hit |
| Connections | Active/idle connections, pool wait, max connections |
| Transactions | Lock wait, deadlock, abort/retry, transaction duration |
| Replication | Replica lag, network lag, apply lag khi có |
| Query | Top SQL by total load/latency, plans, index usage |
| Costs | Instance compute, storage, replica/read pool, backup, data transfer |

### Cloud SQL Query Insights

Query Insights hỗ trợ xem database load, top queries, tags và drill-down. Một số khả năng nâng cao như wait event analysis, query plan capture hay index advisor phụ thuộc **database engine, edition và cấu hình**. Ví dụ, Cloud SQL MySQL Enterprise Plus có index advisor khi bật Query Insights Enterprise Plus; không nên giả định tất cả tính năng này có trên Enterprise hoặc mọi engine.

### AlloyDB Query Insights và Index Advisor

AlloyDB cung cấp Query Insights cho primary và read pools. Index Advisor có thể đề xuất index dựa trên workload SQL; cần bật và kiểm tra gợi ý. Một đề xuất index chỉ là tín hiệu: trước khi tạo, phải đánh giá chi phí ghi, dung lượng, maintenance và số truy vấn hưởng lợi.

### Spanner Query Insights, execution plans và Key Visualizer

Spanner cung cấp Query Insights cho query và DML, execution plans, thông tin CPU/latency và các công cụ phát hiện hotspots. Khi thấy một server/split nghẽn nhưng CPU instance trung bình không cao, cần xem key distribution/Key Visualizer thay vì chỉ tăng tổng processing units.

Ghi tag/query label một cách có kiểm soát để liên kết từ Java/Spring endpoint tới database query. Không log toàn bộ SQL chứa dữ liệu khách hàng hoặc secret vào telemetry; Query Insights có thể chứa query text và IP tùy lựa chọn cấu hình.

## 5. Tối ưu câu SQL và schema trước khi tăng máy

Một index phù hợp có thể giảm số row phải quét, giảm disk I/O và hạ p95 latency mà không phải tăng vCPU. Ngược lại, quá nhiều indexes làm INSERT/UPDATE/DELETE tốn chi phí hơn.

### Ví dụ truy vấn PostgreSQL

Giả sử bảng `orders` có 20 triệu row:

~~~sql
SELECT id, customer_id, status, created_at
FROM orders
WHERE customer_id = 'cust-001'
  AND created_at >= TIMESTAMPTZ '2026-10-01 00:00:00+00'
ORDER BY created_at DESC
LIMIT 50;
~~~

Đọc plan trên môi trường staging hoặc khi chi phí an toàn:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, customer_id, status, created_at
FROM orders
WHERE customer_id = 'cust-001'
  AND created_at >= TIMESTAMPTZ '2026-10-01 00:00:00+00'
ORDER BY created_at DESC
LIMIT 50;
~~~

`EXPLAIN ANALYZE` **thực thi câu SQL**; không dùng vô tư với câu `UPDATE`/`DELETE` trên production. Khi đọc plan, chú ý rows ước lượng so với thực tế, sequential scan, sort, loop lặp quá nhiều, shared buffers, disk reads và thời gian từng bước.

Một index có thể phù hợp với truy vấn:

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_customer_created
  ON orders (customer_id, created_at DESC);
~~~

Trong PostgreSQL, `CREATE INDEX CONCURRENTLY` giảm mức khóa ghi so với cách tạo index thông thường, nhưng vẫn tiêu thụ I/O, CPU, thời gian và có thể thất bại để lại invalid index. Không chạy lệnh này trong transaction block. Phải đo lại plan và latency sau triển khai; việc optimizer chọn index còn phụ thuộc selectivity, thống kê và kích thước bảng.

### Truy vấn có điều kiện và phân trang

Các cách cải thiện phổ biến:

- Chỉ `SELECT` những cột cần thiết; không trả các cột JSON/blob lớn khi UI chỉ hiển thị tóm tắt.
- Đưa filter có chọn lọc vào SQL thay vì tải toàn bộ rồi lọc trong Java.
- Tránh vòng lặp N+1 queries của ORM; dùng batch loading/join có kiểm soát.
- Dùng keyset pagination thay vì OFFSET rất lớn cho dữ liệu nhiều trang.
- Giới hạn khoảng thời gian quét; cân nhắc partition theo thời gian khi dữ liệu và query shape phù hợp.
- Rút ngắn transaction, đặc biệt khi giữ row locks và gọi HTTP service bên ngoài.
- Kiểm tra dữ liệu skew và cập nhật statistics theo khả năng của engine.

### Không tối ưu một query làm hại cả hệ thống

Thêm một index trên cột cập nhật thường xuyên có thể giúp báo cáo đọc nhanh hơn nhưng làm throughput ghi giảm. Một thay đổi cần đánh giá **toàn bộ workload**, không chỉ thời gian của một SQL trong cửa sổ thử nghiệm.

## 6. Cloud SQL: tối ưu compute, storage và connection

Cloud SQL phù hợp nhiều ứng dụng SQL truyền thống. Tối ưu ở ba cấp: SQL/schema, cấu hình instance và luồng ứng dụng.

### Compute và memory

- Nếu CPU liên tục cao và query plans đã hợp lý, cân nhắc tăng vCPU hoặc chọn machine type phù hợp.
- Nếu workload cần working set lớn, tăng memory có thể giảm disk reads; xem hiệu quả cache trước và sau.
- Nếu disk I/O là bottleneck, kiểm tra storage type, capacity/throughput, query scans và temp files trước khi thay máy.
- Xem growth của storage và backup; tự động tăng storage ngăn hết dung lượng nhưng cũng tăng chi phí lâu dài.

Thay đổi cấu hình instance có thể gây restart hoặc thời gian không sẵn sàng tùy loại thao tác/edition. Phải kiểm tra tác động và có maintenance window, rollback và quan sát SLO.

### Cloud SQL Enterprise Plus và data cache

Một số edition, engine và machine type hỗ trợ **data cache** để cải thiện read performance khi working set vượt khả năng buffer pool. Tính năng này không chữa được lock contention hoặc truy vấn thiếu index. Dùng Cloud SQL recommendations/Query Insights để đánh giá workload có thực sự hưởng lợi và so sánh cost của Enterprise Plus.

Không giả định mọi Cloud SQL instance đều có cùng data cache và index advisor. Tài liệu cần đọc theo engine/edition (MySQL, PostgreSQL hoặc SQL Server).

### Cloud SQL HA khác read replica

**HA standby** phục vụ failover/availability, không phải một endpoint đọc mở rộng như read replica. **Read replica** có thể xử lý truy vấn đọc để giảm tải primary; replica thường **bất đồng bộ**, nên ứng dụng có thể đọc trạng thái cũ.

Đối với flow “tạo đơn xong đọc lại ngay”, gửi đọc về primary hoặc thiết kế cơ chế read-your-writes; không mặc định route toàn bộ SELECT sang replica. Giám sát `replica_lag`, `network_lag` và CPU của replica. Với PostgreSQL, workload đọc dài trên replica hoặc replica thiếu tài nguyên có thể làm lag tăng.

### Connection pooling

Khi Cloud Run/GKE autoscale từ 10 lên 100 instances, mỗi instance mở tối đa 20 connections có thể tạo hàng nghìn connections tới một database không tăng năng lực tương ứng. Tổng connection budget xấp xỉ:

\[
C_{max} = \sum_{service} replicas_{peak} \times poolSize_{perReplica}
\]

Cần giữ ngân sách cho quản trị, backup, monitoring và failover. Với Cloud SQL PostgreSQL Enterprise Plus, **Managed Connection Pooling** có các yêu cầu phiên bản/network/edition riêng và endpoint pool trực tiếp sử dụng port 6432; transaction pooling có thể khác session pooling về state/prepared statements. `Cloud SQL Auth Proxy` **không phải connection pool** dù giúp tạo kết nối an toàn.

### Cách xử lý connection storm

1. Đo số connection **thực tế**, bao gồm ứng dụng nền và jobs.
2. Xem pool checkout latency và số request đang chờ pool.
3. Giảm pool size nếu workload đang tạo connections không cần thiết.
4. Đặt giới hạn concurrency tại Cloud Run/GKE và batch workers.
5. Dùng retry/backoff có jitter khi kết nối lỗi; tránh retry vô hạn.
6. Chỉ nâng database connection limit/machine size khi đã kiểm tra memory cho mỗi connection.

## 7. Cloud SQL: read scaling và tính nhất quán

Ví dụ ứng dụng bán hàng:

~~~mermaid
flowchart LR
    API[Java/Spring API] --> R[Read/write routing]
    R -->|Write, read-after-write| P[Cloud SQL primary]
    R -->|Read chấp nhận lag| RR[Cloud SQL read replica]
    P -. async replication .-> RR
    Q[Query Insights và Monitoring] -. observe .-> P
    Q -. observe .-> RR
~~~

### Khi thêm read replica

Cân nhắc khi:

- Phần lớn traffic là truy vấn đọc có thể chịu độ trễ dữ liệu.
- Primary CPU/I/O bị chiếm nhiều bởi SELECT sau khi đã tối ưu query.
- Báo cáo/batch có thể tách khỏi giao dịch chính.
- Đội có thể vận hành routing, theo dõi lag và failover.

Không thêm replica để giải quyết ghi nặng trên primary hoặc deadlock do một hàng bị khóa. Replica còn tăng phí compute/storage/network và có thể gây chi phí quản lý môi trường.

### Routing theo độ nhạy dữ liệu

| Luồng nghiệp vụ | Endpoint ưu tiên | Lý do |
|---|---|---|
| Ghi thanh toán/đơn hàng | Primary | Chấp nhận ghi và consistency của transaction |
| Đọc ngay sau khi xác nhận đơn | Primary | Tránh bản ghi chưa được replicate |
| Danh sách sản phẩm ít thay đổi | Replica nếu cho phép | Tăng khả năng đọc |
| Báo cáo tổng hợp lịch sử | Replica hoặc hệ thống analytics riêng | Tránh ảnh hưởng đường OLTP |
| Dashboard yêu cầu thời gian thực rất chặt | Primary hoặc thiết kế streaming dữ liệu riêng | Cần định nghĩa freshness rõ |

Read replica không tự tạo load balancer cho client; ứng dụng, proxy hoặc thành phần định tuyến cần trỏ tới đúng endpoint và xử lý unavailable/lag.

## 8. AlloyDB: đọc nhiều, read pool và mở rộng theo tải

AlloyDB for PostgreSQL có kiến trúc managed PostgreSQL và các khả năng tăng tốc query đặc thù. Nó phù hợp khi workload PostgreSQL gặp giới hạn throughput, cần read scaling hoặc có truy vấn phân tích trên cùng nền tảng dữ liệu.

### Primary và read pool

- **Primary instance** chịu write traffic; tăng vCPU/RAM là một cách scale dọc.
- **Read pool instance** có thể gồm nhiều node; đọc được phân phối qua read pool endpoint.
- Có thể scale **node count** của read pool thủ công hoặc dùng read pool autoscaling theo điều kiện được hỗ trợ.
- Thay đổi số node không đồng nghĩa mọi client connection hiện có lập tức được cân bằng lại; cần xem hành vi kết nối và reconnect khi node bị thu hồi.

Ví dụ:

~~~mermaid
flowchart LR
    APP[Application] -->|Transactions / writes| PRIMARY[AlloyDB primary]
    APP -->|Read-only queries| POOL[AlloyDB read pool endpoint]
    PRIMARY -. storage / replication .-> POOL
    POOL --> NODE1[Read node 1]
    POOL --> NODE2[Read node 2]
    POOL --> NODE3[Read node 3]
~~~

Mọi ví dụ sơ đồ chỉ mang tính logic. Với AlloyDB, không tự đặt giả định read pool có thể ghi, transaction đọc ở pool thấy ngay commit vừa được primary thực hiện hoặc mọi query tự động route đúng endpoint.

### Dấu hiệu nên mở rộng read pool

Tăng read nodes khi có kết quả rõ từ Query Insights/metrics:

- Read throughput tăng, mỗi node đã bị CPU hoặc memory pressure kéo dài.
- p95 read latency vượt SLO sau khi đã kiểm tra index/query plan.
- Read pool endpoint và client routing đang được dùng đúng.
- Read freshness yêu cầu có thể đáp ứng.
- Chi phí read nodes tăng thấp hơn giá trị throughput/latency thu được.

Nếu chỉ một SQL thực hiện full scan và chiếm phần lớn tài nguyên, sửa câu SQL thường tốt hơn thêm hai read nodes.

### Index Advisor

AlloyDB Index Advisor phân tích các câu query thường gặp để đề xuất `CREATE INDEX` và đánh giá tác động. Nó không tự bảo đảm index nào cũng có lợi. Thử trên staging và đo read latency, write throughput, storage growth, index maintenance và thời gian tạo index.

### AlloyDB Query Insights

Tách thông số primary và read pool; một query nhanh trên primary nhưng chậm trên read pool có thể do query mix, tài nguyên, caching hoặc dữ liệu vừa cập nhật. Dùng query tags để kết nối nhu cầu ứng dụng với top SQL và tránh đo cùng một workload ở các thời điểm khác nhau.

## 9. AlloyDB columnar engine cho mixed OLTP/analytics

**Columnar engine** giúp tăng tốc một số truy vấn quét, join và aggregate lớn bằng cách lưu các cột được chọn theo bố trí column-oriented trong bộ nhớ. Nó có thể hoạt động trên primary hoặc read pool theo cấu hình được hỗ trợ.

### Khi có lợi

- Truy vấn aggregate một số cột trên tập row lớn.
- Báo cáo cần `SUM`, `COUNT`, `AVG`, filter hoặc join đã phù hợp planner.
- Dashboard đọc nhiều và không nhất thiết phải dùng cùng đường transaction của OLTP.
- Muốn giảm thời gian query phân tích mà chưa tách dữ liệu sang warehouse.

### Khi không có lợi hoặc cần thận trọng

- Lookup theo primary key vốn đã nhanh.
- Dữ liệu có tỷ lệ update cao làm invalidation của column store tăng.
- Column store chiếm memory khiến buffer dành cho OLTP nhỏ đi.
- Query shape hoặc data type không được columnar planner hỗ trợ.
- Mức tăng tốc không bù được phí RAM/compute và vận hành.

Để sử dụng, cần bật cờ `google_columnar_engine.enabled` theo hướng dẫn của AlloyDB; thao tác bật là thay đổi cấu hình và **cần restart**. Có thể cho hệ thống tự chọn columns (auto-columnarization) hoặc cấu hình thủ công. Dùng `EXPLAIN` và metadata column store để xác nhận query thực sự sử dụng columnar engine; **bật tính năng không bảo đảm mọi query chạy columnar**.

### Một kịch bản có kiểm chứng

1. Đo baseline query `SELECT category, COUNT(*), SUM(amount) ... GROUP BY category`.
2. Xác nhận đây là một trong top queries gây tải cao.
3. Bật columnar trên môi trường staging với tập dữ liệu đại diện.
4. Kiểm tra plan và hiệu suất khi dữ liệu liên tục INSERT/UPDATE.
5. So sánh p95/p99, RAM pressure, CPU, throughput OLTP và chi phí.
6. Nếu OLTP bị ảnh hưởng, cân nhắc chuyển workload phân tích sang read pool hoặc BigQuery.

Không dùng AlloyDB columnar làm lý do bỏ qua kiến trúc analytics phù hợp cho truy vấn xuyên nhiều nguồn và batch cực lớn.

## 10. Spanner: mở rộng phân tán nhưng phải thiết kế khóa đúng

Spanner phân chia dữ liệu thành các key ranges (splits) và phân phối công việc trên compute resources. Điều này mang lại khả năng mở rộng nhưng tạo một yêu cầu mới: **phân bố khóa và traffic phải cho phép hệ thống phân phối tải**.

### Hotspot do primary key tăng tuần tự

Một thiết kế không tốt cho bảng ghi liên tục:

~~~sql
-- Ví dụ GoogleSQL Spanner: không khuyến nghị cho tải INSERT cao.
CREATE TABLE Events (
  EventTime TIMESTAMP NOT NULL,
  EventId STRING(36) NOT NULL,
  Payload STRING(MAX)
) PRIMARY KEY (EventTime, EventId);
~~~

Khi `EventTime` luôn tăng, insert mới tập trung vào một đầu key range. Một split có thể trở thành bottleneck dù tổng CPU của Spanner instance chưa đầy.

Một lựa chọn khác:

~~~sql
-- Ví dụ GoogleSQL: EventId phân tán ngẫu nhiên nếu tạo bằng UUIDv4.
CREATE TABLE Events (
  EventId STRING(36) NOT NULL,
  EventTime TIMESTAMP NOT NULL,
  TenantId STRING(36) NOT NULL,
  Payload STRING(MAX)
) PRIMARY KEY (EventId);
~~~

Với workload cần truy vấn theo thời gian/tenant, thiết kế secondary index có cân nhắc phân bố key. UUIDv4, bit-reversed sequences hoặc key có prefix hash là các cách được Spanner hỗ trợ/khuyến nghị trong tình huống thích hợp; không thay khóa mù quáng vì còn yêu cầu join và locality.

### Hotspot không chỉ đến từ khóa chính

Một bảng phân tán tốt vẫn có thể nghẽn nếu:

- Mọi request cập nhật một hàng counter duy nhất.
- Secondary index có leading key tăng dần như commit timestamp.
- Một tenant nhận 80% traffic và khóa tenant là prefix có độ phân biệt thấp.
- Nhiều transaction cùng cập nhật tập row nhỏ.

Khắc phục có thể là sharded counters, phân tán khóa, batch có kiểm soát, tách luồng ghi hoặc sửa transaction logic. Không dựa vào tăng nodes như giải pháp duy nhất.

### Key Visualizer và split hotspots

Khi p99 tăng dù CPU instance trung bình chưa cao, xem Key Visualizer và các thông tin lock/transaction để tìm key ranges hoặc index đang bị nóng. Thay đổi key schema thường khó hơn thêm index; cần kế hoạch migration/backfill, dual read/write hoặc công cụ phù hợp.

## 11. Spanner: CPU, processing units và autoscaling

Spanner dùng **processing units (PU)** hoặc **nodes** để thể hiện compute capacity; thông thường **1 node = 1.000 PU**. Với cấu hình theo processing units, số đơn vị hợp lệ và khả năng scale còn phụ thuộc giới hạn instance/edition; kiểm tra quota và region trước khi áp dụng.

### CPU recommendations không phải mục tiêu dùng tối đa 100%

Google Cloud công bố các ngưỡng tham khảo để duy trì khả năng phục vụ khi mất zone/region:

| Chỉ số | Regional instance | Dual-region hoặc multi-region (mỗi region) |
|---|---:|---:|
| High-priority total CPU utilization | Khuyến nghị tối đa 65% | Khuyến nghị tối đa 45% |
| 24-hour smoothed aggregate CPU | Khuyến nghị tối đa 90% | Khuyến nghị tối đa 90% |

Đây là **ngưỡng khuyến nghị để bảo đảm headroom**, không phải bảo đảm p99 latency cho mọi ứng dụng. Khi workload latency-sensitive, cần benchmark để đặt mục tiêu thấp hơn nếu cần.

### Managed autoscaler

Spanner có managed autoscaler giúp tăng/giảm compute theo CPU và storage objectives. Có thể cấu hình mục tiêu **high-priority CPU**, **total CPU** và/hoặc storage theo các giới hạn được hỗ trợ. Ví dụ định hướng:

- Regional: high-priority CPU target khoảng 65%, total CPU target khoảng 70%.
- Multi-region: high-priority CPU target khoảng 45%, total CPU target khoảng 50%.

Các giá trị là hướng dẫn bắt đầu từ tài liệu, không phải cấu hình cố định. Tăng tài nguyên có độ trễ và chi phí, và không giải quyết một hot split. Nếu autoscaler liên tục scale up/down, kiểm tra tính chu kỳ tải, minimum/maximum và target trước khi điều chỉnh.

### Scale thủ công

Ví dụ minh họa tăng năng lực instance đã tồn tại:

~~~bash
gcloud spanner instances update spanner-orders-prod \
  --project=orders-prod \
  --processing-units=2000
~~~

Lệnh có thể làm thay đổi chi phí và năng lực production; không chạy trước khi được phê duyệt. Scale up thường cần thời gian phân phối tài nguyên; scale down phải đủ headroom cho data size, number of splits và traffic dự kiến. Hãy kiểm tra yêu cầu storage capacity và giới hạn cụ thể trước khi giảm.

## 12. Spanner: query optimizer, index và transaction

Spanner có Query Insights, optimizer thống kê và query plans. Một truy vấn không tốt có thể tạo remote scans, scan nhiều rows hoặc distributed joins tốn compute dù schema khóa chính tốt.

### Query theo khách hàng và thời gian

Giả sử bảng:

~~~sql
-- GoogleSQL dialect
CREATE TABLE Orders (
  OrderId STRING(36) NOT NULL,
  CustomerId STRING(36) NOT NULL,
  CreatedAt TIMESTAMP NOT NULL,
  Status STRING(20) NOT NULL
) PRIMARY KEY (OrderId);
~~~

Với yêu cầu liệt kê 50 đơn mới nhất của một khách hàng:

~~~sql
SELECT OrderId, CreatedAt, Status
FROM Orders
WHERE CustomerId = @customer_id
ORDER BY CreatedAt DESC
LIMIT 50;
~~~

Một index có thể hỗ trợ truy vấn:

~~~sql
CREATE INDEX OrdersByCustomerTime
ON Orders(CustomerId, CreatedAt DESC)
STORING (Status);
~~~

Index này giúp lọc theo CustomerId và sắp thứ tự CreatedAt; `Status` được lưu kèm trong index. Lưu ý mọi secondary index đều tốn storage, tăng công việc write và có thể tạo hotspot nếu key distribution kém. `@customer_id` là query parameter, không phải cú pháp gán biến khi chạy trực tiếp trong SQL console.

### Đọc query plan và thống kê

Spanner query plans cho thấy scan, distributed work, rows returned và CPU/elapsed time theo operator. Query optimizer dùng statistics packages và có version; một thay đổi plan có thể đến từ biến động thống kê chứ không chỉ do release ứng dụng. Khi xảy ra regression, so sánh plans, query parameters, lượng dữ liệu và optimizer statistics/version.

### Transaction contention

- Giữ read-write transaction ngắn.
- Không đặt network call tới dịch vụ bên ngoài bên trong transaction.
- Thực hiện batch write theo hạn mức và payload được hỗ trợ; tránh một transaction chạm quá nhiều row nóng.
- Xử lý `ABORTED` theo retry semantics của Spanner client, với idempotency ở tầng nghiệp vụ.
- Với đọc không bắt buộc nhìn dữ liệu mới nhất, cân nhắc bounded staleness hoặc exact staleness **ở API client** theo contract.

Không đổi toàn bộ query sang stale reads để giảm CPU nếu ứng dụng cần nhất quán mạnh, đặc biệt với thanh toán hoặc kiểm tra tồn kho.

## 13. So sánh hướng tối ưu theo loại nghẽn

| Điểm nghẽn | Cloud SQL | AlloyDB | Spanner |
|---|---|---|---|
| Một query scan quá nhiều | EXPLAIN/index/statistics | Query Insights, index advisor, columnar nếu thích hợp | Query plan, secondary index, predicate/selectivity |
| Nhiều SELECT chiếm CPU | Read replica, caching | Read pool và node autoscaling | Phân phối reads, tăng PU/nodes nếu không hotspot |
| Connections quá nhiều | Hikari/PgBouncer/managed pooling theo edition | Pool ứng dụng, read pool endpoint, connection limits | Client/session pool phù hợp, session exhaustion metrics |
| Ghi vào một row nóng | Tối ưu lock/transaction, shard counter khi cần | Tối ưu PostgreSQL transaction và data model | Thiết kế lại hot key/split, sharded counter |
| Working set lớn | Instance memory/data cache theo edition | Memory sizing, read pool và column store | Compute/data placement, index và scan |
| Region xa người dùng | Chọn region/kiến trúc read phù hợp | Read topology và data locality | Regional/multi-region config, routing/consistency |
| Peak tăng ngắn | Có kế hoạch scale/quản lý concurrency | Scale primary/read nodes theo chính sách | Managed autoscaler và headroom |
| Chi phí quá cao | Right-size và bỏ replica không cần | Tối ưu read pools/columnar | PU autoscale, tránh overprovision và hotspots |

Đừng chuyển từ Cloud SQL sang Spanner chỉ vì một bảng thiếu index; ngược lại, nếu mô hình ghi phân tán và latency nhiều vùng vượt giới hạn kiến trúc một primary, chỉ tăng instance size Cloud SQL cũng có thể không đáp ứng lâu dài.

## 14. Java và Spring: kết nối đúng trước khi tối ưu SQL

Với Spring Boot, HikariCP thường được dùng để quản lý connection pool. Cấu hình phải ăn khớp với autoscaling của Cloud Run/GKE và giới hạn database.

Ví dụ `application-prod.yml` cho PostgreSQL qua private endpoint hoặc connector/proxy đã được tổ chức cấu hình:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: orders_app
    # Password lấy từ Secret Manager hoặc cơ chế bí mật của nền tảng.
    hikari:
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 3000
      idle-timeout: 600000
      max-lifetime: 1800000
      validation-timeout: 2000
      pool-name: orders-pool
~~~

Không đặt password trực tiếp trong Git. Nếu ứng dụng có tối đa 80 replicas, mỗi replica tối đa 10 connections có thể tạo 800 connections cho riêng service này. Đây là giới hạn **đỉnh lý thuyết**, không phải số connections chắc chắn được tạo. Hãy cộng các services khác, admin users và failover margin.

### Ba loại timeout cần phân biệt

- **Pool checkout timeout:** chờ lấy connection từ Hikari; không đồng nghĩa SQL timeout.
- **Connection/network timeout:** giới hạn thiết lập kết nối và đọc/ghi socket theo driver.
- **Query/transaction timeout:** ngân sách cho một câu SQL hoặc transaction.

Không sửa lỗi pool timeout bằng cách tăng `maximum-pool-size` vô hạn; điều đó có thể làm database sụp nhanh hơn. Giảm thời gian giữ connection, tránh transaction mở qua HTTP calls và áp concurrency limits thích hợp.

### Theo dõi pool metrics

Spring Boot với Micrometer có thể theo dõi active, idle, pending và total Hikari connections. Khi checkout wait tăng mà DB CPU thấp, cần xem thread starvation, connection leak, transaction chậm và network. Khi DB CPU cao và queue tăng, giảm client concurrency có thể giúp hệ thống phục hồi hơn là thêm retry.

### Read/write routing cần rõ hợp đồng

Nếu Java service dùng primary và read replica/read pool, nên tách `DataSource` hoặc routing component theo mục đích. Các phương thức đọc ngay sau ghi hoặc nằm trong read-write transaction cần giữ consistency contract. Không để một annotation “readOnly” của Spring tự quyết định rằng mọi SELECT đều có thể chuyển sang replica bất đồng bộ.

## 15. Cache, batch và các tối ưu ở tầng ứng dụng

Không phải mọi cải thiện cần tác động database. Đối với dữ liệu ít thay đổi, cache ở tầng ứng dụng hoặc Memorystore có thể giảm load. Với thống kê nặng, precompute hoặc chuyển phân tích sang BigQuery có thể tốt hơn tăng instance.

### Những biện pháp thường đem lại hiệu quả

- **Cache có TTL và invalidation:** catalog, cấu hình, reference data.
- **Batch reads/writes:** giảm round-trips khi API cho phép.
- **Debounce hoặc coalesce:** tránh nhiều request đồng thời cùng tải một key.
- **Async events:** gửi công việc không cần đáp ứng tức thời qua Pub/Sub/queue.
- **Data archiving:** tách lịch sử không truy vấn thường xuyên để giảm working set.
- **Read model riêng:** precompute dashboard thay vì query join nặng mỗi lần mở màn hình.

### Rủi ro

Cache có thể trả dữ liệu cũ; batch lớn có thể giữ transaction/lock quá lâu; event-driven có thể tạo dữ liệu eventual consistency. Mọi thay đổi cần định nghĩa freshness, thứ tự xử lý, idempotency và điều kiện hoàn tất nghiệp vụ.

Một hệ thống checkout không nên cache số lượng hàng còn lại mà không có cơ chế bảo đảm tồn kho được kiểm soát. Cũng không nên chuyển đọc balance tài khoản sang replica chỉ vì thấy giảm CPU.

## 16. Benchmark đúng tải, không chỉ chạy một SQL

### Tạo workload đại diện

Một bài load test có ý nghĩa cần:

1. Dataset đủ lớn, thống kê gần production về kích thước, cardinality và skew.
2. Mix ước lượng từ telemetry: read/write/transaction/report/batch.
3. Concurrency và ramp-up giống ứng dụng thật.
4. Tỷ lệ cache warm/cold được kiểm soát.
5. Kết nối mạng và region gần topology production.
6. Thời gian chạy đủ dài để lộ memory pressure, compaction/vacuum, background I/O.
7. Xác suất lỗi, retry và timeouts được ghi nhận, không chỉ số request/giây.

Không dùng dữ liệu production có PII trong môi trường benchmark nếu chưa được phép; dữ liệu giả phải giữ được cấu trúc phân bố đủ gần.

### Ma trận thử nghiệm

| Biến thể | Thay đổi duy nhất | Đo |
|---|---|---|
| Baseline A | Cấu hình đang chạy | p50/p95/p99, TPS, CPU, I/O, cost |
| B | Thêm composite index | Query plan, write overhead, index size |
| C | Pool 20 → 10 connections/replica | Pool wait, DB CPU, throughput, timeouts |
| D | Thêm read replica/read pool | Read p95, write p95, lag, phí |
| E | Tăng CPU hoặc processing units | Throughput, headroom, cost |
| F | Bật columnar / thay key schema trong staging | Query acceleration, memory, hotspot, write costs |

Đừng thay index, số nodes, concurrency và SQL trong cùng một thử nghiệm rồi gán toàn bộ cải thiện cho một yếu tố. Khi bắt buộc kết hợp, ghi lại phương pháp và kiểm thử lại từng thành phần.

### Công thức hiệu quả

\[
CostPer1000SuccessfulTxn =
\frac{TotalDatabaseCost}{SuccessfulTransactions} \times 1000
\]

Ví dụ, database tốn 2.000 USD/tháng cho 4 triệu giao dịch thành công: 0,50 USD/1.000 giao dịch. Sau tối ưu, chi phí 2.200 USD nhưng xử lý 6 triệu giao dịch và vẫn đạt p99 SLO: khoảng 0,37 USD/1.000 giao dịch. Tổng hóa đơn tăng nhưng unit economics tốt hơn.

Không chỉ tối ưu trung bình khi đuôi p99 hoặc tỷ lệ thất bại xấu đi. Có thể đặt mục tiêu đồng thời: cost per successful transaction giảm **và** error budget không bị vượt.

## 17. FinOps: so sánh chi phí một cách công bằng

Chi phí database không chỉ là vCPU:

- Compute của primary, replicas/read pools hoặc Spanner processing units.
- Data storage, indexes, backups, PITR/transaction logs và retention.
- Egress giữa region/VPC/cloud và kết nối ứng dụng tới database.
- Query Insights, logging và monitoring theo mô hình định giá hiện hành.
- HA/DR, maintenance, migration và nhân công vận hành.

### Đặt cùng đơn vị so sánh

Cloud SQL, AlloyDB và Spanner có mô hình định giá và giới hạn kiến trúc khác nhau. Khi so sánh, phải cố định:

1. Tập workload, dữ liệu và độ phân bố tenant.
2. Yêu cầu SLA/SLO, RPO/RTO, region và HA.
3. Chất lượng query, business success rate và latency.
4. Tỷ lệ read/write, peak concurrency và mức tăng trưởng dự báo.
5. Tổng chi phí hoàn chỉnh (TCO) và chi phí migration.

Một Spanner instance đa vùng đắt hơn database một vùng không nhất thiết là lựa chọn kém nếu bài toán yêu cầu bảo vệ trước mất vùng và nhất quán xuyên vùng; ngược lại, không nên chọn multi-region cho ứng dụng nội bộ nhỏ không có nhu cầu.

### Quyết định scale hay tối ưu

| Quan sát | Thử tối ưu trước | Khi nào scale hợp lý |
|---|---|---|
| CPU cao vì query scan | Index, query rewrite | Sau khi query đã hợp lý mà throughput vẫn thiếu |
| Lock wait cao | Rút transaction, giảm contention | Scale ít giúp nếu cùng một hot row |
| Pool wait cao | Giảm thời gian giữ connection, kiểm tra leaks | Scale DB khi concurrency thực cần và DB có headroom |
| Read demand tăng | Cache, route read pool/replica | Tăng read capacity sau khi đo lag/consistency |
| Spanner hot split | Thiết kế key/secondary indexes | Tăng compute sau khi load phân bố đủ tốt |
| Working set > cache | Giảm scan, cache, storage design | Tăng RAM/data cache nếu lợi ích đo được |

Tối ưu phải gắn với mục tiêu kinh doanh: giảm latency để tăng conversion, giảm lỗi để giữ SLA hoặc giảm cost per unit mà không làm giảm khả năng phục vụ.

## 18. Runbook xử lý database chậm trong production

### Giai đoạn 0: không làm hại dữ liệu

Không chạy DDL lớn, reindex toàn bộ, thay transaction isolation hoặc đổi primary key trong lúc sự cố nếu chưa đánh giá tác động. Chốt người chỉ huy sự cố, mức độ khẩn cấp và quyền thay đổi.

### Từ phút 0 đến 10

1. Xác định dịch vụ và tuyến request đang lỗi; kiểm tra SLO/error budget.
2. So sánh peak traffic, số replicas ứng dụng và database CPU/I/O/connections.
3. Kiểm tra Cloud Monitoring, Query Insights và sự kiện deploy/maintenance gần nhất.
4. Nếu connection storm, giới hạn concurrency/rate và tắt retry không an toàn.
5. Nếu một query mới gây tải, cân nhắc rollback phiên bản ứng dụng thay vì đổi database ngay.

### Từ phút 10 đến 30

6. Xem top SQL, wait events, lock contention và query plans.
7. Kiểm tra replica lag hoặc Spanner hotspots nếu liên quan.
8. Chọn biện pháp ít rủi ro: giảm batch concurrency, chuyển báo cáo sang read pool, tắt feature nặng.
9. Nếu cần scale, xác minh quota, chi phí, thời gian thực thi và điều kiện rollback.
10. Theo dõi p95/p99, error rate và transaction success sau mỗi thay đổi.

### Sau sự cố

11. Lưu timeline, metrics, query plans và cấu hình trước/sau.
12. Tạo thử nghiệm tái hiện với workload đại diện.
13. Fix root cause: index, connection strategy, hot key hoặc capacity policy.
14. Bổ sung alert, runbook, rollback procedure và cost review.

Không dùng “restart database” như biện pháp đầu tiên; restart có thể làm mất cache, cắt kết nối và khiến mọi service cùng reconnect.

## 19. Bài tập: tối ưu ba hệ thống khác nhau

### Tình huống A: Cloud SQL PostgreSQL

Ứng dụng Spring trên Cloud Run tăng từ 20 lên 120 instances trong giờ cao điểm; mỗi instance có Hikari pool tối đa 20 connections. Cloud SQL CPU chỉ khoảng 55%, nhưng nhiều request báo hết hạn chờ connection.

**Câu hỏi:** nguyên nhân khả dĩ nhất là gì và nên đo gì trước khi tăng vCPU? Gợi ý: tính connection budget đỉnh (120 × 20 = 2.400), so sánh với giới hạn DB, theo dõi pool pending, thời gian giữ connection và transaction duration. Thử giảm pool size, giới hạn concurrency và loại bỏ transaction bao quanh các call HTTP.

### Tình huống B: AlloyDB read pool

Ứng dụng báo cáo chạy mỗi phút; read pool gồm hai nodes có p95 3 giây và CPU cao. Top query thực hiện aggregate trên 30 triệu rows, trong khi primary write vẫn ổn.

**Câu hỏi:** cần thêm node ngay hay tối ưu query? Gợi ý: xem plan, index/Query Insights, benchmark columnar engine trên read pool, đo CPU và memory. Chỉ scale node count khi đã biết việc thêm read capacity giải quyết tải thực.

### Tình huống C: Spanner

Một hệ thống log ghi 20.000 sự kiện/giây. CPU instance trung bình 35% nhưng p99 write latency tăng mạnh. Primary key bắt đầu bằng timestamp tăng liên tục.

**Câu hỏi:** tăng nodes có giải quyết không? Gợi ý: kiểm tra Key Visualizer, split hotspots và cấu trúc secondary index; thử thiết kế EventId phân tán UUIDv4 hoặc hash prefix, giữ khả năng query theo thời gian qua index thích hợp.

## 20. Troubleshooting nhanh

| Triệu chứng | Nguyên nhân thường gặp | Hành động có kiểm chứng |
|---|---|---|
| p99 tăng dù CPU thấp | Lock/pool/network waits | Query Insights waits, active connections, tracing |
| Thêm read replica nhưng lag cao | Replica thiếu tài nguyên hoặc query đọc dài | Replica lag metrics, replica sizing, query tuning |
| Cloud SQL quá nhiều connections | Autoscaling ứng dụng × pool size | Hikari metrics, connection budget, pooling strategy |
| AlloyDB read pool vẫn chậm | Một SQL scan lớn hoặc routing sai endpoint | Top SQL, query plan, index/columnar validation |
| Bật columnar không nhanh hơn | Query không dùng column store hoặc invalidation cao | EXPLAIN, column store usage, update rate |
| Spanner thêm PU nhưng vẫn timeout | Hot key/split hoặc transaction contention | Key Visualizer, split/lock analysis, redesign key |
| Spanner CPU tăng theo query mới | Plan regression hoặc index không phù hợp | Query Insights, optimizer plan, statistics |
| Giá database tăng nhưng throughput không đổi | Overprovision, idle read nodes, storage growth | FinOps cost/unit, utilization và resource inventory |
| Batch gây lỗi cho checkout | Report giữ lock/IO hoặc chiếm primary | Schedule/budget batch, read pool hoặc analytics platform |
| Tối ưu query xong write chậm hơn | Index mới làm tăng write amplification | Benchmark TPS read/write, index maintenance |
| Load test tốt nhưng production kém | Dataset/skew/peak khác, cache không tương đồng | Recreate realistic traffic, p99, tenant skew |

## 21. Checklist trước khi thay đổi production

- [ ] Có baseline SLO, traffic mix, p95/p99, error rate và unit cost.
- [ ] Phân biệt CPU saturation với I/O, network, connection và lock waits.
- [ ] Đã xem top SQL và execution plans, không chỉ nhìn CPU instance.
- [ ] Index mới được thử cả read benefit lẫn write overhead.
- [ ] Connection pool tính theo số replica ứng dụng ở peak.
- [ ] Cloud SQL HA standby không bị hiểu nhầm là read replica.
- [ ] Read replica/read pool có freshness contract và theo dõi replication lag.
- [ ] AlloyDB columnar chỉ dùng nếu query shape phù hợp và memory đủ.
- [ ] Spanner primary/secondary keys được rà soát nguy cơ hotspot.
- [ ] Spanner CPU headroom và autoscaler được đặt theo topology và SLO.
- [ ] Có load test với dữ liệu và traffic mix đại diện.
- [ ] Thử nghiệm thay đổi từng yếu tố, có cách rollback và owner phê duyệt.
- [ ] Đánh giá ảnh hưởng HA/DR, bảo mật, network và chi phí.
- [ ] Có alert về pool pending, query latency, replica lag, transaction aborts.
- [ ] Đã thống nhất đơn vị chi phí, số giao dịch thành công và kỳ đo.
- [ ] Không đặt credentials hoặc SQL chứa dữ liệu nhạy cảm vào log.

## 22. Kết luận

Tối ưu Cloud SQL, AlloyDB và Spanner cần bắt đầu từ **đặc tính tải thực tế**, không phải từ kích thước máy. Cùng một dấu hiệu p99 tăng có thể do những nguyên nhân rất khác: connection storm trên Cloud SQL, read pool chạy query scan lớn trên AlloyDB hoặc một hot key trên Spanner. Biện pháp đúng được quyết định bởi dữ liệu đo, execution plan, mô hình concurrency và hợp đồng nhất quán của ứng dụng.

Quy trình bền vững là **baseline → xác định top bottleneck → tối ưu query/schema/connections → cân nhắc scale → benchmark → đối soát SLO và cost per unit → rollout có giám sát**. Khi có thể chứng minh rằng mỗi thay đổi cải thiện kết quả nghiệp vụ với chi phí hợp lý, việc tối ưu database trở thành một phần của SRE và FinOps thay vì một chuỗi phản ứng khi hệ thống chậm.

## Tài liệu tham khảo

- [Cloud SQL for PostgreSQL: Best practices](https://docs.cloud.google.com/sql/docs/postgres/best-practices)
- [Cloud SQL: Manage database connections](https://docs.cloud.google.com/sql/docs/postgres/manage-connections)
- [Cloud SQL: Managed Connection Pooling](https://docs.cloud.google.com/sql/docs/postgres/managed-connection-pooling)
- [Cloud SQL: Query Insights](https://docs.cloud.google.com/sql/docs/postgres/using-query-insights)
- [Cloud SQL: Replication lag](https://docs.cloud.google.com/sql/docs/postgres/replication/replication-lag)
- [Cloud SQL: High availability](https://docs.cloud.google.com/sql/docs/postgres/high-availability)
- [AlloyDB: Query Insights](https://docs.cloud.google.com/alloydb/docs/using-query-insights)
- [AlloyDB: Index Advisor](https://docs.cloud.google.com/alloydb/docs/use-index-advisor)
- [AlloyDB: Scale an instance and read pool](https://docs.cloud.google.com/alloydb/docs/instance-read-pool-scale)
- [AlloyDB: About the columnar engine](https://docs.cloud.google.com/alloydb/docs/columnar-engine/about)
- [Spanner: CPU utilization](https://docs.cloud.google.com/spanner/docs/cpu-utilization)
- [Spanner: Managed autoscaler](https://docs.cloud.google.com/spanner/docs/managed-autoscaler)
- [Spanner: Compute capacity and processing units](https://docs.cloud.google.com/spanner/docs/compute-capacity)
- [Spanner: Primary key design](https://docs.cloud.google.com/spanner/docs/schema-design)
- [Spanner: Query Insights](https://docs.cloud.google.com/spanner/docs/using-query-insights)
- [Spanner: Query execution plans](https://docs.cloud.google.com/spanner/docs/query-execution-plans)
- [Cloud Monitoring overview](https://docs.cloud.google.com/monitoring/docs)
