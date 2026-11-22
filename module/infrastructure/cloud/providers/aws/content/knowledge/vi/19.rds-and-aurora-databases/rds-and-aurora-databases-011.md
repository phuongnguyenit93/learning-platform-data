# Giám sát truy vấn chậm, connection và tài nguyên database

> **Chương:** Cơ sở dữ liệu RDS và Aurora  
> **Module:** CLOUD_PROVIDERS_AWS — tìm hiểu hệ sinh thái AWS từ Region/Availability Zone (AZ), IAM, VPC đến compute, storage, database, tích hợp và serverless; rèn khả năng chọn dịch vụ, triển khai ứng dụng an toàn, giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Xây dựng chiến lược quan sát **Amazon RDS và Amazon Aurora** theo bốn lớp: trải nghiệm ứng dụng, database load/query, hệ điều hành và storage/replication.
2. Đọc và phân tích chính xác **CloudWatch AWS/RDS metrics**: CPUUtilization, DatabaseConnections, FreeableMemory, FreeStorageSpace khi áp dụng, IOPS, latency, queue, throughput, replica lag và các metric dành cho Aurora Serverless.
3. Giải thích **CloudWatch Database Insights**, DB Load đo theo **Average Active Sessions (AAS)**, phân tích top SQL, waits, locks, plan và sự khác biệt giữa Standard/Advanced.
4. Cấu hình và đọc **slow query logs** của PostgreSQL, MySQL và Aurora theo cơ chế parameter group, lưu ý log overhead và nguy cơ lộ SQL parameters.
5. Sử dụng **pg_stat_activity, pg_stat_statements, pg_locks** cho PostgreSQL và **performance_schema, SHOW PROCESSLIST, EXPLAIN** cho MySQL để khoanh vùng SQL chậm.
6. Phân biệt **connections, active queries, idle connections, connection churn, pool exhaustion**; tính pool capacity cho Spring Boot/HikariCP, Lambda/ECS và RDS Proxy.
7. Chẩn đoán các nút nghẽn **CPU, RAM, I/O, storage, locking, autovacuum, replication** mà không suy diễn từ một metric riêng.
8. Thiết kế CloudWatch dashboards/alarms, runbook, quyền IAM/KMS/CloudWatch Logs và chi phí giám sát.
9. Thực hiện truy vấn kiểm tra bằng **AWS CLI chỉ đọc** và SQL chẩn đoán không thay đổi dữ liệu nghiệp vụ.
10. Đưa ra quyết định tối ưu theo số liệu trước/sau: index, query plan, pool, instance class, storage, reader endpoint hoặc RDS Proxy.

## 1. Tình huống thực tế: API Java chậm, database có lỗi gì?

Một dịch vụ **Spring Boot Orders API** chạy trên Amazon ECS/EC2 hoặc Lambda, kết nối tới **Amazon RDS for PostgreSQL** hay **Amazon Aurora PostgreSQL**. Người dùng báo:

- API **GET /orders** từ 200 ms tăng lên 3 giây.
- HikariCP log xuất hiện **Connection is not available, request timed out**.
- CloudWatch cho thấy **DatabaseConnections** tăng, còn CPU chỉ khoảng 45%.
- Đôi khi đơn hàng bị cập nhật chậm hoặc transaction timeout.
- Sau khi tăng số lượng ECS tasks/Lambda concurrency, tình hình trở nên tệ hơn.

Không thể kết luận “DB thiếu CPU” hoặc “cứ nâng instance size” dựa trên các dấu hiệu đó. Các giả thuyết có thể khác nhau:

1. Một truy vấn thiếu index, quét hàng triệu bản ghi.
2. Long transaction giữ lock, làm các truy vấn khác **chờ**, dù CPU vẫn còn.
3. Java app mở quá nhiều DB connections; mỗi worker/tác vụ có pool riêng.
4. Database storage latency hoặc queue tăng.
5. DB proxy đang thiếu connection headroom hoặc bị session pinning.
6. Replica lag làm API read endpoint thấy dữ liệu trễ.
7. DNS/TLS/IAM/SG hoặc connection churn tạo chi phí thiết lập kết nối lớn.
8. Công cụ logging đang ghi quá nhiều, làm tăng CPU và I/O.

Mục tiêu của quan sát database không chỉ là **thấy một đường biểu diễn đỏ** mà là nối các bằng chứng để trả lời: **chậm ở đâu, vì sao, bao nhiêu yêu cầu bị ảnh hưởng và cần sửa ở lớp nào**.

~~~mermaid
flowchart TB
    CLIENT["Người dùng"] --> API["API Gateway / ALB"]
    API --> JAVA["Spring Boot / ECS / Lambda"]
    JAVA --> POOL["HikariCP / RDS Proxy"]
    POOL --> WRITER["RDS/Aurora writer"]
    WRITER --> STORAGE[("EBS hoặc Aurora storage")]
    WRITER --> READER["Aurora readers / RDS read replica"]
    JAVA -.-> APPMET["App metrics: p95, errors, pool wait"]
    WRITER -.-> CW["CloudWatch AWS/RDS"]
    WRITER -.-> DBI["CloudWatch Database Insights"]
    WRITER -.-> EM["Enhanced Monitoring / Logs"]
    READER -.-> CW
    CW --> DASH["Dashboard và alarms"]
    DBI --> DASH
    EM --> DASH
    APPMET --> DASH
~~~

Sơ đồ là kiến trúc **tham khảo**. RDS thông thường sử dụng kiến trúc storage khác Aurora; không phải mọi RDS instance có read replica, RDS Proxy hoặc Enhanced Monitoring.

### 1.1. Định nghĩa mục tiêu quan sát

Với API Orders, có thể chọn:

| SLI/SLO | Ví dụ tham khảo | Tín hiệu cần xem |
| --- | --- | --- |
| **API latency p95** | Dưới 500 ms cho request đọc thông thường. | Spring Actuator/APM và ALB/API Gateway latency. |
| **DB query latency p95** | Truy vấn quan trọng dưới 100 ms theo dữ liệu thực tế. | Tracing, Database Insights, slow query logs, pg_stat_statements. |
| **Connection acquisition wait** | Phần lớn requests không phải chờ connection. | HikariCP pending/wait metrics và RDS Proxy borrow latency. |
| **Transaction correctness** | Không trừ tồn kho/ghi đơn sai khi retry. | Business audit, database constraints, idempotency. |
| **Replica freshness** | Dữ liệu cần đọc không trễ vượt ngưỡng. | Replica lag và yêu cầu read-after-write consistency. |
| **Availability** | DB endpoint và ứng dụng sẵn sàng. | Failover events, connection errors, app error rate. |
| **Chi phí/hiệu suất** | Chi phí trên mỗi 1.000 đơn hợp lệ. | DB instance/ACU/storage/IO/logs/Proxy và throughput. |

Các ngưỡng chỉ là ví dụ; chúng không phải mức mặc định AWS.

## 2. Hiểu đúng RDS, Aurora, instance, cluster và replica

### 2.1. RDS DB instance so với Aurora DB cluster

| Khía cạnh | **RDS MySQL/PostgreSQL DB instance** | **Aurora MySQL/PostgreSQL DB cluster** |
| --- | --- | --- |
| Compute | DB instance. | Một hoặc nhiều DB instances trong cluster; writer và có thể có readers. |
| Storage | Storage volume EBS được RDS quản lý theo engine/storage type. | Aurora shared cluster volume phân tán và replicated bởi dịch vụ. |
| HA | Multi-AZ DB instance hoặc Multi-AZ DB cluster theo lựa chọn. | Storage HA theo cluster design; writer failover sang reader/instance phù hợp. |
| Read scaling | Read replicas theo engine/cấu hình. | Aurora Replicas đọc trên shared cluster volume, dùng reader endpoint. |
| Metrics | AWS/RDS instance metrics, DB Insights, logs. | AWS/RDS **instance-level và cluster-level metrics**; thêm Aurora-specific metrics. |
| Capacity | DB class và storage type/IOPS throughput. | Provisioned instances hoặc **Aurora Serverless** bằng ACU theo cấu hình. |
| Chi phí | Instances, storage/IOPS/backup/network/logs. | Instances hoặc ACU, storage/I/O hoặc I/O-Optimized, backup/network/logs. |

**Không đánh đồng** RDS Multi-AZ **standby** với **read replica** có thể phục vụ SELECT. Với triển khai Multi-AZ DB instance truyền thống, standby dùng cho HA, không phải endpoint đọc cho ứng dụng. Multi-AZ DB cluster và Aurora có topology đọc khác, cần xác minh cụ thể.

### 2.2. Quan sát writer và reader riêng

Một cluster có:

- **Writer endpoint** để ghi và các truy vấn cần tính nhất quán ngay.
- **Reader endpoint** để phân tải đọc trên readers khi phù hợp.
- **Instance endpoints** để chẩn đoán một member cụ thể.

Nếu chỉ nhìn CPU/DatabaseConnections của writer, bạn có thể bỏ sót reader đang quá tải hoặc replica lag. Nếu chỉ nhìn cluster average, một reader bị bottleneck có thể bị che khuất.

~~~mermaid
flowchart LR
    APP["Java application"] -->|"Ghi / read-after-write"| WEP["Cluster writer endpoint"]
    APP -->|"Đọc chấp nhận replica lag"| REP["Reader endpoint"]
    WEP --> W["Writer instance"]
    REP --> R1["Reader AZ-1"]
    REP --> R2["Reader AZ-2"]
    W --> S[("Aurora shared cluster volume")]
    R1 --> S
    R2 --> S
~~~

**Reader endpoint không đảm bảo mọi lần đọc đều thấy write mới tức thì.** Thiết kế read-after-write có thể cần route về writer hoặc kiểm soát consistency theo trường hợp.

### 2.3. Region/AZ trong giám sát

- **CloudWatch metrics, RDS/DB Insights và logs** được xem trong Region nơi DB hoạt động.
- Một RDS/Aurora cluster có thể có members ở nhiều AZ, nhưng **không** mặc định multi-Region DR.
- Khi có failover, writer role/endpoint chuyển member; dashboard gắn vào **DB instance identifier cũ** có thể tiếp tục đo member đã thành reader.
- Aurora Global Database có cross-Region replication metrics và cấu hình riêng; cần quan sát **replication lag** theo Region, không dùng một đồ thị địa phương để kết luận toàn hệ thống khỏe.

## 3. Bốn lớp observability của database

| Lớp | Công cụ/tín hiệu | Trả lời gì? | Hạn chế |
| --- | --- | --- | --- |
| **Ứng dụng** | Java p95/p99, HikariCP pool, traces, errors, transaction outcome. | Người dùng đang bị chậm ở API nào? | Không cho biết chính xác DB wait event nếu thiếu instrumentation. |
| **Database activity** | **CloudWatch Database Insights**, DB Load/AAS, top SQL/waits/plans, views SQL. | Query/lock/CPU nào làm database bận? | Chỉ có những trường tính năng và retention hỗ trợ. |
| **Infrastructure/OS** | **CloudWatch AWS/RDS**, **Enhanced Monitoring**, OS process metrics. | CPU, RAM, disk queue, network, storage có nghẽn? | Một metric đơn lẻ không xác định nguyên nhân SQL. |
| **Logs/events** | PostgreSQL log, MySQL slow log, CloudWatch Logs, RDS events. | Câu SQL nào chậm, DB restart/failover ra sao? | Có overhead, có thể chứa dữ liệu nhạy cảm. |

**Chẩn đoán đúng thứ tự:** xác nhận tác động người dùng → tìm DB instance/cluster và time window → xem DB Load/waits/connections → kiểm tra SQL plan/logs → đối chiếu CPU/memory/IO/replica lag → thử thay đổi trên môi trường kiểm soát.

## 4. CloudWatch AWS/RDS: những metrics cần thuộc

RDS/Aurora phát metric vào **AWS/RDS**. CloudWatch cơ bản có độ phân giải thông thường **1 phút**, dữ liệu và thống kê theo thời gian/dimension, ví dụ **DBInstanceIdentifier** hoặc **DBClusterIdentifier** tùy metric.

### 4.1. Compute và memory

| Metric | Ý nghĩa | Khi bất thường |
| --- | --- | --- |
| **CPUUtilization** | % CPU được sử dụng ở DB instance. | CPU cao kéo dài, CPU credits cạn, SQL CPU-bound, background work. |
| **FreeableMemory** | Lượng bộ nhớ có thể giải phóng/sử dụng; không đồng nghĩa RAM trống hoàn toàn. | Cache/connection/work_mem pressure, swap, OOM risk. |
| **SwapUsage** | Bytes swap đang dùng, khi metric được hỗ trợ. | Memory pressure; kiểm tra biến động và OS metrics. |
| **CPUCreditBalance** | Số CPU credits còn lại cho các burstable DB classes được hỗ trợ. | Hiệu năng giảm khi credits cạn, dù peak CPU trước đó cao. |
| **DatabaseConnections** | Số client network connections tới DB theo semantics engine/service. | Pool phình, connection storm, max_connections, idle churn. |

Một **FreeableMemory thấp** chưa chắc là lỗi, vì database tận dụng memory cho cache. Cần quan sát xu hướng, swap, DB Load, errors và memory trong Enhanced Monitoring trước khi kết luận thiếu RAM.

### 4.2. Storage, I/O và network

| Metric | Ý nghĩa | Cần lưu ý |
| --- | --- | --- |
| **FreeStorageSpace** | Dung lượng còn lại trên storage DB instance **khi áp dụng**, thường quan trọng với RDS storage cấp phát. | Aurora shared cluster storage có metrics/cơ chế khác, không dùng nguyên cảnh báo FreeStorageSpace của RDS EBS. |
| **ReadIOPS / WriteIOPS** | Tốc độ đọc/ghi I/O theo engine/storage metric. | IOPS cao không tự đồng nghĩa lỗi; so với baseline và latency. |
| **ReadLatency / WriteLatency** | Latency của thao tác I/O theo định nghĩa service. | Kết hợp với queue/throughput, không dùng như SQL query latency. |
| **DiskQueueDepth** | Số requests chờ I/O theo service/engine. | Queue tăng cùng latency có thể báo bottleneck I/O. |
| **ReadThroughput / WriteThroughput** | Bytes đọc/ghi mỗi giây. | So storage bandwidth và dữ liệu workload. |
| **NetworkReceiveThroughput / NetworkTransmitThroughput** | Bytes qua network của DB instance. | Cần xem read fan-out, replication, client fetch size. |
| **BurstBalance** | Burst credits của storage type như gp2 khi áp dụng. | Không áp dụng mọi storage class, ví dụ gp3 không dùng gp2 burst bucket. |
| **EBSByteBalance% / EBSIOBalance%** | Cân bằng throughput/IO credits cho những DB classes/storage phù hợp. | Phụ thuộc instance/storage/engine; không nhất thiết phát cho mọi Aurora engine. |

**Đơn vị rất quan trọng.** AWS/RDS console có thể hiển thị MB trong khi CloudWatch trả **Bytes**. Không vội đặt threshold 1000 cho “GB” nếu metric dùng Bytes.

### 4.3. Connections không bằng running queries

Giả sử DatabaseConnections = 250, nhưng DB Load chỉ 4 AAS. Điều đó có thể nghĩa **rất nhiều connections đang idle**, và vài sessions đang active. Nếu CPU 80% và DB Load 20 AAS, có thể bị query CPU pressure hoặc wait; cần xem top wait types.

Ngược lại, DatabaseConnections = 30, DB Load 25 AAS và phần lớn chờ locks có thể là một bottleneck transaction, không phải hết slot kết nối.

**DatabaseConnections ≠ Concurrent SQL queries ≠ DB Load.** Đây là ba đại lượng khác nhau.

## 5. CloudWatch Database Insights: quan sát DB Load, top SQL, waits

**CloudWatch Database Insights** là hướng quan sát chính trong CloudWatch cho RDS/Aurora. AWS đã chuyển trải nghiệm **Performance Insights console** sang Database Insights; theo tài liệu CloudWatch hiện hành, mốc kết thúc Performance Insights standalone là **31/07/2026**. Một số API/metric names vẫn chứa từ **PerformanceInsights** vì khả năng tương thích; đừng nhầm API name với console UI hiện đại.

### 5.1. Standard và Advanced

| Khả năng | **Standard** | **Advanced** |
| --- | --- | --- |
| Database load, top dimensions (SQL, waits, host, user) | Có theo engine hỗ trợ. | Có. |
| Retention chi tiết | Thường **7 ngày** không tính phí retention; có tùy chọn trả phí dài hơn. | Retention dài hơn theo cấu hình và pricing plan. |
| Per-query statistics và guided slow SQL analysis | Hạn chế hơn. | Có, theo engine và **CloudWatch Logs export** khi cần. |
| Guided lock/plan analysis | Không phải cùng đầy đủ như Advanced. | Có trên một số engines, ví dụ Aurora/RDS PostgreSQL lock, execution plan theo hỗ trợ. |
| OS process breakdown / fleet analytics | Hạn chế. | Có các khả năng nâng cao khi bật Enhanced Monitoring/feature tương ứng. |
| Chi phí | Standard feature baseline; retention dài/các tính năng thêm có thể tính phí. | Mode/retention và CloudWatch/logs có mô hình giá riêng. |

AWS có thể cập nhật retention và pricing; khi quyết định production, đọc **Database Insights pricing và engine compatibility tại Region** thay vì coi bảng này như hợp đồng giá cố định. Không bật Advanced chỉ để xem CPUUtilization nếu CloudWatch metric cơ bản đã đủ.

### 5.2. DB Load = Average Active Sessions (AAS)

Database Insights lấy **DB Load** làm tín hiệu chính: số sessions **đang active**, gồm chạy CPU hoặc đang chờ những resources như locks/I/O. Chỉ số được tính theo **average active sessions** trong time window.

\[
\text{DB Load (AAS)}
=\frac{\text{Tổng thời gian active của tất cả sessions}}{\text{Thời gian cửa sổ quan sát}}
\]

Ví dụ trong 60 giây, tổng cộng các sessions hoạt động/chờ đủ **480 giây phiên**:

\[
\text{AAS}=480/60=8
\]

Kết quả AAS = 8 nghĩa tương đương **8 sessions active liên tục**, không phải “8 queries đã được gọi”. Nếu load chủ yếu CPU và DB có 4 vCPU, DBLoadCPU vượt khoảng 4 có thể gợi ý CPU contention; nếu load chủ yếu wait/lock thì tăng CPU chưa chắc giải quyết.

### 5.3. DB Load theo nhóm wait

~~~mermaid
flowchart TD
    LOAD["DB Load (AAS) tăng"] --> Q{"Top wait type?"}
    Q -->|"CPU"| CPU["Xem CPUUtilization, hot SQL, execution plan"]
    Q -->|"Lock"| LOCK["Tìm blocking session, transaction duration"]
    Q -->|"I/O"| IO["Xem storage latency, cache hit, read scans, IOPS"]
    Q -->|"Client/network"| NET["Xem client fetch, network, connection pooling"]
    Q -->|"Commit/log"| COMMIT["Xem write pressure, WAL/redo, storage"]
~~~

**Cần hiểu tên wait event theo database engine.** PostgreSQL có wait_event_type/wait_event khác MySQL Performance Schema events. Một DBLoad = 12 AAS với 10 AAS chờ Lock khác hẳn 12 AAS chạy CPU.

### 5.4. Top SQL và dimensions

Database Insights có thể nhóm DB Load theo:

- **SQL** hoặc SQL digest/normalized statement.
- **Waits** (CPU, Lock, I/O, commit...).
- **Host**, **User**, **Database**.
- **Blocking session/SQL/object**, khi engine/mode hỗ trợ.
- **Execution plan**, khi bật advanced plan analysis trên engine hỗ trợ.

Ví dụ DB Load từ 5 lên 20 và 15 AAS đều tập trung vào **SELECT orders WHERE customer_id = ? ORDER BY created_at DESC**. Cần kiểm tra index/customer cardinality/plan thay vì nâng 4 lên 16 vCPU ngay.

### 5.5. DBLoad, DBLoadCPU, DBLoadNonCPU

Một số metrics có thể được đưa vào CloudWatch, như **DBLoad**, **DBLoadCPU**, **DBLoadNonCPU** và **DBLoadRelativeToNumVCPUs**. Chúng giúp đặt alarms nhưng cần chú ý:

- Các metrics có thể chỉ phát khi DB có load theo tài liệu.
- Chọn **Average** để xem DB Load; **Sum** không phải tổng số SQL queries.
- **DBLoadCPU** liên quan AAS đang dùng CPU; đừng đồng nhất với **CPUUtilization %**.
- DBLoadNonCPU là phần load đang chờ, không có nghĩa server đứng yên hoặc hoàn toàn khỏe.
- Với Aurora Serverless v2, năng lực vCPU/memory thay đổi theo ACU nên so tương quan với capacity đang cấp.

## 6. Enhanced Monitoring: OS processes, memory và I/O

**RDS Enhanced Monitoring** giúp thấy chi tiết OS-level processes/threads và memory/disk/network trên DB instances.

- Có thể cấu hình chu kỳ **1, 5, 10, 15, 30, 60 giây**.
- Dữ liệu Enhanced Monitoring được gửi tới **CloudWatch Logs**, log group thường là **RDSOSMetrics**, không phải một metric AWS/RDS thông thường có cùng data retention.
- Các log streams gắn với **DbiResourceId**, không nhất thiết tên DB instance hiển thị.
- Cần **MonitoringRoleArn** cho IAM role được RDS assume, cùng permissions phù hợp.
- Mức granularity càng nhỏ, dữ liệu logs nhiều hơn và chi phí CloudWatch Logs có thể tăng.

### 6.1. Khi nào cần Enhanced Monitoring?

| Dấu hiệu | Enhanced Monitoring giúp gì? |
| --- | --- |
| CPUUtilization tăng nhưng DB Load wait không giải thích hết | Xem OS processes, system vs user CPU, background tasks. |
| FreeableMemory giảm, swap tăng | Xem cache, RSS, dirty pages, swap pressure và các tiến trình. |
| Storage latency cao | Xem disk I/O await/utilization, device-level metrics khi engine/instance có. |
| Kết nối bị chậm mà CPU thấp | Xem network/OS và liên hệ với DB locks/connections. |
| Đợt maintenance/analyze/vacuum | Phân biệt background processes với workload ứng dụng. |

**Enhanced Monitoring không thay SQL profiler**. Nó cho biết tầng OS bị nghẽn, nhưng để tìm câu SQL cần sửa vẫn phải dùng Database Insights/slow-query logs/engine views.

## 7. Slow query logging PostgreSQL (RDS và Aurora PostgreSQL)

PostgreSQL có hệ thống log dựa trên các tham số như:

- **log_min_duration_statement**: log những statements đạt ngưỡng duration, tính bằng **milliseconds**.
- **log_statement**: all/ddl/mod/none; **none** giúp tránh logging mọi statement không cần.
- **log_destination = stderr**: cách cấu hình dùng cho RDS/Aurora PostgreSQL log export.
- **log_lock_waits** và **deadlock_timeout**: hỗ trợ điều tra lock waits theo cấu hình.
- **log_connections / log_disconnections**: điều tra connection churn, nhưng tăng log volume.
- **log_min_duration_sample / log_statement_sample_rate**: sampling statements chậm trên các versions được hỗ trợ.

### 7.1. Ví dụ parameter-group cho slow SQL

Các giá trị tham khảo:

~~~text
log_min_duration_statement = 1000
log_statement = none
log_destination = stderr
log_lock_waits = on
~~~

- **1000 ms = 1 giây**: log các SQL statements đủ chậm.
- **log_statement = none**: tránh ghi toàn bộ DML/queries không cần.
- **log_lock_waits = on**: phát hiện các tình huống chờ lock quá ngưỡng cấu hình.
- Phần lớn cấu hình nên được quản trị trong **custom DB parameter group** hay **DB cluster parameter group** phù hợp engine; dynamic/static và reboot requirement phụ thuộc từng tham số/version.

**Không đổi trực tiếp parameter trong production nếu chưa có approval, baseline và kế hoạch rollback.** Một số tham số dùng AWS RDS managed controls, cần chọn parameter group đúng DB instance/cluster.

### 7.2. Export PostgreSQL logs tới CloudWatch Logs

Trong RDS console/CLI/IaC có thể bật **CloudWatch log exports** cho log type **postgresql** tùy engine. Khi enabled, CloudWatch Logs nhận **logs mới** từ thời điểm cấu hình; không mặc định backfill tất cả log lịch sử.

Log group ví dụ:

~~~text
/aws/rds/instance/orders-postgres/postgresql
/aws/rds/cluster/orders-aurora/postgresql
~~~

Đường dẫn thực tế phụ thuộc RDS/Aurora instance/cluster và service naming.

### 7.3. Tác động hiệu năng và bảo mật của logging

**Không** đặt log_min_duration_statement = 0 và log_statement = all cho toàn bộ production trong thời gian dài nếu chưa đo impact:

- Database phải format và ghi nhiều log lines.
- Export tới CloudWatch Logs dùng thêm CPU/I/O.
- Log records có thể chứa SQL text, literals, PII, passwords/tokens nếu ứng dụng ghép giá trị trực tiếp vào câu SQL.
- CloudWatch Logs charges tăng theo ingest, storage và query scanning.
- App error logs có thể vô tình nhân bản cùng một statement nhiều lần.

AWS Database Blog tháng **11/2026** cảnh báo tác động của verbose logging lên Aurora PostgreSQL: excessive query/audit logs có thể trở thành bottleneck riêng. Dùng **threshold và sampling có chủ đích**, kiểm tra performance trước/sau và hạn chế retention.

### 7.4. Phân biệt SQL duration và lock wait

Một truy vấn chậm có thể chạy CPU 20 ms nhưng chờ lock 3 giây. Slow log ghi elapsed time, không tự nói nguyên nhân.

Quy trình:

1. Từ slow log lấy statement, thời điểm, session identifiers có sẵn.
2. So với Database Insights **top waits**.
3. Xem pg_stat_activity/pg_locks của thời điểm phù hợp.
4. Nếu Lock wait chiếm ưu thế, tìm **blocking transaction** và code giữ transaction quá lâu.
5. Nếu CPU/I/O, kiểm tra **EXPLAIN, indexes, table stats, buffer cache**.

## 8. Slow query logging MySQL và Aurora MySQL

MySQL/Aurora MySQL sử dụng các tham số:

- **slow_query_log = 1**: bật slow query log.
- **long_query_time**: ngưỡng query duration bằng **giây**, ví dụ 1.0 = một giây.
- **log_output = FILE**: cần khi export slow query log vào CloudWatch Logs.
- **log_queries_not_using_indexes**: ghi queries không dùng indexes, có thể tạo nhiều log hơn dự kiến.
- **min_examined_row_limit**: điều kiện về lượng rows examined, tùy engine/version.

### 8.1. Tham số mẫu

~~~text
slow_query_log = 1
long_query_time = 1.0
log_output = FILE
log_queries_not_using_indexes = 0
~~~

Một truy vấn dài **0,8 giây** sẽ **không được ghi** nếu long_query_time = 1.0. Điều đó không nghĩa query không chậm so với SLO p95 của API, ví dụ 200 ms.

RDS for MySQL có thể có default log_output = TABLE, còn Aurora MySQL version tương ứng có default FILE; **đọc parameter thực tế** thay vì giả định mọi engine giống nhau.

### 8.2. FILE vs TABLE

| Kiểu log | Ưu điểm | Rủi ro |
| --- | --- | --- |
| **FILE** | Phù hợp export tới CloudWatch Logs; dễ phân tích tập trung. | File/log volume và CPU/I/O overhead vẫn cần kiểm soát. |
| **TABLE** | Có thể query mysql.slow_log trong database theo engine. | Thêm write load, bảng log tăng, không phải dạng cần cho CloudWatch slow log export. |
| **NONE** | Không ghi slow/general logs. | Không có slow log để phân tích. |

Để có slow logs trong CloudWatch Logs theo AWS RDS/Aurora MySQL, phải đồng thời:

1. Bật **slow_query_log**.
2. Chọn **log_output = FILE**.
3. Bật export **slowquery** sang CloudWatch Logs theo engine.
4. Đảm bảo query vượt **long_query_time**.
5. Kiểm tra Region/log group và IAM đọc logs.

### 8.3. Phát hiện query không dùng index

**log_queries_not_using_indexes = 1** có thể giúp phát hiện full scans, nhưng đừng bật vô thời hạn ở workload nhiều queries nhỏ: có thể tạo rất nhiều log, kể cả queries nhanh mà không có index. Không phải mọi query không dùng index là xấu; table vài chục rows có thể quét hợp lý hơn dùng index.

### 8.4. MySQL slow log minh họa

~~~text
# Time: 2026-11-20T03:10:00.123456Z
# User@Host: app_user[app_user] @  [10.0.2.42]
# Query_time: 3.240000  Lock_time: 0.010000
# Rows_sent: 20  Rows_examined: 1500000
SELECT id, total, created_at
FROM orders
WHERE customer_id = 123
ORDER BY created_at DESC
LIMIT 20;
~~~

**Dữ liệu là ví dụ**, không phải log production thật. Đáng chú ý **Rows_examined lớn hơn nhiều Rows_sent**: có thể thiếu composite index trên (customer_id, created_at) hoặc optimizer chọn plan chưa tốt. Nhưng trước khi tạo index phải xác nhận distribution, write costs và EXPLAIN thực tế.

## 9. PostgreSQL: chẩn đoán session, slow SQL và locks bằng SQL

SQL dưới đây nhằm **đọc trạng thái và thống kê**. Chỉ chạy trên database được cấp quyền; ngay cả SELECT chẩn đoán cũng có thể tiêu thụ CPU/I/O và lộ SQL text của session khác nếu principal đủ quyền.

### 9.1. Xem sessions hiện tại qua pg_stat_activity

~~~sql
SELECT
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    count(*) AS sessions
FROM pg_stat_activity
WHERE datname IS NOT NULL
GROUP BY datname, usename, application_name,
         state, wait_event_type, wait_event
ORDER BY sessions DESC;
~~~

Từ đây phân biệt:

- **active**: session đang thực thi query.
- **idle**: session không chạy query nhưng vẫn giữ connection.
- **idle in transaction**: transaction đang mở và chờ client, có thể giữ locks/snapshot.
- **wait_event_type = Lock**: chờ lock.
- **wait_event_type = IO/Client/...**: loại chờ tùy PostgreSQL version/engine.

**Rủi ro:** nhiều idle sessions không chắc có vấn đề nếu pool được sizing đúng; **idle in transaction lâu** nguy hiểm hơn vì có thể giữ locks và cản trở vacuum.

### 9.2. Top running queries theo tuổi

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE state = 'active'
  AND pid <> pg_backend_pid()
ORDER BY query_start ASC
LIMIT 20;
~~~

**query_age** có thể bao gồm thời gian chờ (lock/I/O/network), không đồng nghĩa toàn bộ đang dùng CPU. SQL text có thể chứa dữ liệu nhạy cảm; hạn chế quyền và redaction khi chụp log.

### 9.3. Nhận diện transaction mở lâu

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start ASC
LIMIT 20;
~~~

Nếu một Java request mở transaction rồi gọi external HTTP service trong nhiều giây, transaction có thể giữ locks không cần thiết. Cần sửa boundary của transaction ở ứng dụng, không chỉ tăng DB pool size.

### 9.4. Tìm blocker một cách an toàn

PostgreSQL có hàm **pg_blocking_pids(pid)** để xác định sessions nào đang block một PID:

~~~sql
SELECT
    a.pid AS waiting_pid,
    a.usename,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids,
    now() - a.query_start AS wait_or_query_age
FROM pg_stat_activity a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY wait_or_query_age DESC;
~~~

Dùng kết quả để điều tra **blocking transaction**. Không tự gọi **pg_terminate_backend** trên production vì đó là tác động thay đổi state, có thể rollback transaction và ảnh hưởng khách hàng.

### 9.5. Thống kê tích lũy với pg_stat_statements

Nếu extension **pg_stat_statements** đã được enabled và đủ quyền:

~~~sql
SELECT
    queryid,
    calls,
    round(total_exec_time::numeric, 2) AS total_ms,
    round(mean_exec_time::numeric, 2) AS avg_ms,
    round(max_exec_time::numeric, 2) AS max_ms,
    rows,
    shared_blks_hit,
    shared_blks_read,
    left(query, 160) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Lưu ý:

- **total_exec_time cao** có thể do query gọi nhiều lần, không nhất thiết mỗi lần rất chậm.
- **mean_exec_time/max_exec_time** giúp phân biệt hot path với outliers.
- **shared_blks_read** cao so với hit có thể gợi ý I/O; cần cân nhắc cache/interval.
- Query text thường được **normalized**; không đồng nghĩa log đầy đủ mọi câu SQL.
- pg_stat_statements chỉ có dữ liệu nếu extension/module đã được cài đúng; cấu hình preload có thể cần restart theo engine/version.
- Dữ liệu tích lũy có thể reset khi restart hoặc gọi stats reset theo quyền; kiểm tra khoảng đo, không so hai periods chỉ bằng số lifetime.

### 9.6. EXPLAIN và EXPLAIN ANALYZE

Ví dụ:

~~~sql
EXPLAIN
SELECT id, total, created_at
FROM orders
WHERE customer_id = 123
ORDER BY created_at DESC
LIMIT 20;
~~~

**EXPLAIN không ANALYZE** thường chỉ hiển thị ước lượng plan, không chạy SELECT theo cách EXPLAIN ANALYZE. Dùng để xem Seq Scan, Index Scan, Sort và rows estimates.

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, total, created_at
FROM orders
WHERE customer_id = 123
ORDER BY created_at DESC
LIMIT 20;
~~~

**EXPLAIN ANALYZE THỰC SỰ THỰC THI truy vấn**, có CPU/I/O, locks và có thể gọi functions có side effects. **Không chạy EXPLAIN ANALYZE với DML** trên production khi chưa đánh giá tác động. Với truy vấn SELECT lớn hoặc chứa volatile functions cũng phải kiểm soát tải. Thực hành tốt là test trên staging/snapshot với dữ liệu đại diện trước.

### 9.7. Ví dụ kế hoạch index

Nếu API thường thực hiện:

~~~sql
SELECT id, total, created_at
FROM orders
WHERE customer_id = 123
ORDER BY created_at DESC
LIMIT 20;
~~~

Một index tiềm năng:

~~~sql
-- Chỉ để minh họa thiết kế; không tự chạy trong bài quan sát.
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at DESC);
~~~

Lý do: lọc theo customer_id và trả theo created_at mới nhất. Nhưng index còn phải xét độ chọn lọc, số writes, dung lượng, MVCC, cách planner dùng index và lock/online migration. **CREATE INDEX là thao tác thay đổi database**, không thuộc phần SQL read-only.

## 10. MySQL: Performance Schema, processlist và execution plan

### 10.1. Xem connection state

~~~sql
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Connections';
SHOW GLOBAL STATUS LIKE 'Aborted_connects';
SHOW VARIABLES LIKE 'max_connections';
~~~

- **Threads_connected:** current open connections.
- **Threads_running:** các threads đang xử lý, không đơn giản bằng số connections.
- **Connections:** tổng attempts từ khi server started/reset.
- **Aborted_connects:** kết nối thất bại theo server semantics.
- **max_connections:** ngưỡng cấu hình, có chỗ dành cho maintenance/admin tùy engine.

Cần lưu ý Global Status counters tích lũy phải so **delta/time interval**, không dùng giá trị lifetime làm requests per second.

### 10.2. SHOW PROCESSLIST

~~~sql
SHOW FULL PROCESSLIST;
~~~

Kết quả có thể cho thấy threads ở trạng thái **Sleep**, **Query**, waiting for locks hoặc sending data. Chỉ user có quyền phù hợp mới xem đầy đủ sessions khác.

**Không tự động KILL** những session đang chạy trong production để làm giảm Threads_connected; cần phân loại transaction, tác động và chủ sở hữu kết nối.

### 10.3. Performance Schema top SQL digests

Nếu **performance_schema** và thống kê tương ứng được bật:

~~~sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1e12, 2) AS total_seconds,
    ROUND(AVG_TIMER_WAIT / 1e12, 3) AS avg_seconds,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST_TEXT IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

**Đơn vị timer** thường là picoseconds ở các trường TIMER_WAIT, nhưng engine/version/plugin cần được kiểm tra. Table có thể không tồn tại hoặc chưa thu thập nếu Performance Schema instruments/consumers chưa bật. Không chuyển thẳng query này sang PostgreSQL.

### 10.4. Explain MySQL

~~~sql
EXPLAIN FORMAT=JSON
SELECT id, total, created_at
FROM orders
WHERE customer_id = 123
ORDER BY created_at DESC
LIMIT 20;
~~~

Đọc plan để tìm:

- Full table scan vs index range/ref lookup.
- Rows estimates và filtered fraction.
- Filesort/temporary table operations.
- Join order và join method.
- Index được chọn so với index đã kỳ vọng.

**EXPLAIN ANALYZE** ở MySQL versions hỗ trợ cũng có thể thực thi query; không xem nó là command không tác động tài nguyên chỉ vì bắt đầu bằng EXPLAIN.

## 11. SQL chậm không chỉ vì thiếu index

~~~mermaid
flowchart TD
    S["Query latency tăng"] --> Q{"DB Insights top wait / plan?"}
    Q -->|"CPU"| CPU["Query plan, scan/join/sort, dữ liệu/hot SQL"]
    Q -->|"Lock"| LOCK["Blocking transaction, isolation level, idle-in-transaction"]
    Q -->|"I/O"| IO["Cache misses, storage throughput, query access pattern"]
    Q -->|"Network/client"| NET["Rows trả về, client fetch, pool, DB driver"]
    Q -->|"Commit/log"| WAL["WAL/redo pressure, checkpoints, write workload"]
    CPU --> VERIFY["Đo lại p95, DBLoad, CPU, business correctness"]
    LOCK --> VERIFY
    IO --> VERIFY
    NET --> VERIFY
    WAL --> VERIFY
~~~

### 11.1. Thiếu index và plan không tối ưu

Dấu hiệu: **Rows_examined rất lớn**, seq scan tốn I/O, ORDER BY cần sort lớn. Phân tích:

- Query predicates, composite index order.
- Table statistics, PostgreSQL ANALYZE/autovacuum hoặc MySQL optimizer stats.
- Index selectivity theo distribution thực tế.
- N+1 queries từ ORM/Hibernate.
- Fetch quá nhiều columns/rows thay vì pagination.

Tạo thêm index cũng có trade-off: write amplification, storage, maintenance và ảnh hưởng lock trong lúc triển khai.

### 11.2. Lock contention

Dấu hiệu: **DB Load NonCPU tăng, top wait = Lock, CPU không cao**.

Nguyên nhân thường gặp:

- Transaction mở lâu do Java method gắn **@Transactional** bao cả HTTP call.
- Concurrent updates tới cùng một row hot.
- DDL/schema migration chặn bảng.
- Deadlocks hoặc lock timeout.
- Isolation level quá mạnh so với nhu cầu.

Cách xử lý: rút ngắn transaction, sắp thứ tự update, tránh external call trong transaction, chia hotspot, thêm retry có idempotency và migration windows đúng. Không mặc định tăng vCPU sẽ hết lock.

### 11.3. Storage I/O

Dấu hiệu: **ReadLatency/WriteLatency/DiskQueueDepth** tăng cùng p95 query và I/O waits.

Cần xem:

- Loại storage và giới hạn **IOPS/throughput** thực tế.
- RDS gp2 burst credits so với gp3 provisioned performance.
- Read/write transaction pattern, index/cache hits.
- Aurora I/O semantics khác RDS EBS và lựa chọn Aurora I/O-Optimized.
- Tác động maintenance, backups, long scans.
- Dữ liệu chéo AZ/Region hoặc network chậm.

### 11.4. DB server có CPU thấp vẫn chậm

CPU thấp có thể xảy ra khi:

- Sessions đang **chờ lock**.
- Pool chưa cấp được connection cho app.
- Query chờ network response/IO.
- Replica lag hoặc application retry loop.
- Java service đang chờ bên ngoài DB nhưng người dùng tưởng “database chậm”.

**Đừng nâng DB instance chỉ vì p95 API cao**. Cần trace endpoint → pool → SQL → backend wait.

## 12. Database connections: cột sống của hiệu năng Java

### 12.1. Một connection chiếm tài nguyên thật

Mỗi DB connection/session cần quản lý network socket, memory, authentication/session state và transaction. PostgreSQL dùng backend processes theo kiến trúc engine; MySQL dùng threads và server resources tương ứng.

Quá nhiều connections có thể dẫn tới:

- Lỗi **too many clients already** (PostgreSQL) hoặc **Too many connections** (MySQL).
- Tăng RAM, context switching hoặc contention.
- Connection establishment chậm do TLS/auth.
- Thời gian chờ **HikariCP connection acquisition** tăng, request timeout.
- Database failover làm nhiều app instances cùng reconnect (connection storm).

### 12.2. Pool size không bằng số requests/giây

Trong Spring Boot/HikariCP:

- **maximumPoolSize** là số DB connections tối đa mà **một application instance** có thể duy trì trong pool, không phải giới hạn toàn hệ thống.
- **minimumIdle** có thể quyết định số idle connections được giữ.
- **connectionTimeout** quy định thời gian app chờ lấy connection.
- **maxLifetime/idleTimeout/keepaliveTime** giúp quản lý connection lifecycle, phải phù hợp server/Proxy timeouts.
- **leakDetectionThreshold** có thể hỗ trợ chẩn đoán connection leak, nhưng không bật logging quá rộng trong production mà không cân nhắc.

### 12.3. Công thức sơ bộ cho connection capacity

Giả sử:

- 12 ECS tasks.
- Mỗi task có **maximumPoolSize = 15**.
- 2 admin/maintenance apps mỗi app giữ tối đa 10 connections.
- Database **max_connections = 300**.

Ước lượng upper bound connections từ app pools:

\[
12\times15+2\times10=200
\]

Cần thêm margin cho RDS/administration, ETL, BI, failover, RDS Proxy/internal sessions và bursts. Nếu Auto Scaling tăng từ 12 lên 24 tasks:

\[
24\times15+2\times10=380
\]

Con số có thể **vượt 300** ngay cả khi từng task hoạt động bình thường. Đây là lý do scale compute mà không scale/control DB connections có thể làm hệ thống lỗi nặng hơn.

**Không lấy max_connections - 0** làm toàn bộ capacity có thể cấp cho app. Để headroom theo thực tế, DB engine và maintenance requirements.

### 12.4. Little's Law và connection occupancy

Một ước lượng cho **concurrent DB query load**:

\[
L \approx \lambda\times W
\]

Trong đó:

- \(\lambda\): số DB operations/giây.
- \(W\): thời gian một operation giữ connection, tính bằng giây.
- \(L\): concurrent operations trung bình.

Ví dụ 200 queries/giây, mỗi query sử dụng connection trung bình 50 ms:

\[
L\approx200\times0.05=10
\]

Không có nghĩa chỉ cần đúng 10 connections cho production: traffic burst, transactions nhiều queries, CPU/lock tail latency, driver overhead, pool acquisition và database failover cần headroom. Hãy dùng **p95 pool pending/wait** và load test thay vì chọn pool bằng công thức duy nhất.

### 12.5. Kiểm tra kết nối trước khi tăng size

Khi **HikariPool - Connection is not available**:

1. Xem **HikariCP active, idle, pending, max** và **connection acquisition p95**.
2. Xem DB **DatabaseConnections**, engine max_connections và DB Load.
3. Xem queries/transactions dài, connection leak hoặc idle-in-transaction.
4. Xem network/TLS/authentication errors và DNS endpoint đúng hay không.
5. Xem số application instances và hệ số pool multiplicative.
6. Chỉ cân nhắc tăng pool nếu **database còn khả năng xử lý** và kết quả load test chứng minh tác dụng.

Tăng pool từ 10 lên 50 trên 20 ECS tasks có thể làm DB tối đa nhận tới **1.000 connections**, gây áp lực nặng hơn.

## 13. RDS Proxy: giảm connection churn và bảo vệ database

**Amazon RDS Proxy** là lớp proxy quản lý kết nối giữa ứng dụng và RDS/Aurora theo engine/Region được hỗ trợ. Nó đặc biệt hữu ích khi:

- Lambda có **burst concurrency** làm nhiều execution environments cùng tạo kết nối.
- ECS/EKS/EC2 scale out nhanh gây connection storm.
- Ứng dụng cần dùng lại database connections giữa những client sessions.
- Có failover và muốn application resilient hơn nhờ proxy routing/connection management.
- DB max_connections cần được bảo vệ trước burst.

~~~mermaid
flowchart LR
    subgraph APPS["Ứng dụng"]
      L1["Lambda #1"] --> P["RDS Proxy"]
      L2["Lambda #2"] --> P
      ECS["ECS tasks"] --> P
    end
    P -->|"Pooled DB connections"| W["RDS/Aurora writer"]
    P -->|"Reader role nếu hỗ trợ"| R["Aurora readers / Multi-AZ DB cluster readers"]
    W --> MET["AWS/RDS DatabaseConnections"]
    P --> PROXYMET["AWS/RDS Proxy metrics"]
~~~

**RDS Proxy không biến database thành vô hạn connections.** Nó quản lý và chia sẻ backend connections trong giới hạn pool; các session-state-dependent operations có thể gây **connection pinning** làm giảm hiệu quả multiplexing.

### 13.1. Các metrics của RDS Proxy

| Metric | Cần biết | Suy luận |
| --- | --- | --- |
| **ClientConnections** | Số client connections đến Proxy. | Tăng mạnh có thể do app scale hoặc reconnect storm. |
| **DatabaseConnections** | Backend connections từ Proxy đến DB. | So với client connections để xem mức reuse. |
| **MaxDatabaseConnectionsAllowed** | Trần backend connections Proxy được phép theo target. | Không phải luôn chính xác max_connections của engine vì còn headroom/internal usage. |
| **DatabaseConnectionsBorrowLatency** | Thời gian Proxy lấy được DB connection cho client. **Đơn vị microseconds** theo metric. | Tăng có thể báo pool contention/pinning. |
| **DatabaseConnectionsCurrentlyBorrowed** | Số backend connections đang được client mượn. | Gần trần lâu làm borrow latency tăng. |
| **DatabaseConnectionsCurrentlyInTransaction** | Connections có transaction đang hoạt động. | Transactions dài giảm cơ hội multiplexing. |
| **DatabaseConnectionsCurrentlySessionPinned** | Connections bị pin theo session state. | Tỷ lệ pin cao làm nhiều client cần backend connection riêng. |
| **ClientConnectionsSetupFailedAuth** | Client auth/TLS setup failures. | Kiểm tra Secrets Manager, IAM auth, TLS và configuration. |
| **QueryResponseLatency** | Thời gian proxy xử lý request đến response. | So với DB query latency và network. |

Tên metrics/statistics/available dimensions khác nhau theo proxy configuration, target group và engine; đối chiếu với danh sách CloudWatch **RDS Proxy metrics** trước khi tạo alarm. Một số gauge của Proxy được AWS hướng dẫn dùng **Sum** cho mỗi phút/dimension, không nên áp suy luận “mọi gauge đều phải Average” một cách máy móc.

### 13.2. DatabaseConnectionsBorrowLatency cao do đâu?

Có thể do:

- MaxConnectionsPercent quá thấp so với traffic.
- Backend DB sessions đang giữ transaction quá lâu.
- Nhiều sessions bị **pinning**.
- DB đã chạm max_connections hoặc thiếu resources.
- Reconnect/failover, auth/TLS timeout.
- Query/transaction duration tăng khiến connection lâu được trả về pool.

**Chẩn đoán:** so BorrowLatency + CurrentlyBorrowed + MaxDatabaseConnectionsAllowed + SessionPinned, rồi xem Database Insights top waits/SQL. Không tăng MaxConnectionsPercent lên 100% ngay: AWS khuyến nghị có headroom, tài liệu RDS Proxy nêu khoảng **30%** so peak usage để Proxy có thể tái phân phối connections.

### 13.3. Session pinning

Những thao tác thay đổi **session state** khiến Proxy không thể tự do reuse DB connection cho client khác. Tùy engine/protocol, pinning có thể liên quan:

- Temporary tables.
- Session variables hoặc SET statements.
- Prepared statements và session state.
- Transaction duration và locks.
- Những SQL statements/driver behaviors cụ thể.

Không áp danh sách pinning của MySQL nguyên xi cho PostgreSQL. Kiểm tra **pinning limitations và query patterns** theo engine. Nếu tỷ lệ pinning quá cao, Proxy có thể không đem lại lợi ích giảm DB connections như kỳ vọng.

### 13.4. IAM auth và secret rotation

RDS Proxy có thể hỗ trợ **AWS Secrets Manager** và **IAM authentication** trong các cấu hình tương ứng. Cần:

- IAM role của Proxy truy cập secret.
- KMS decrypt khi secret dùng customer managed key.
- Security Group ingress/egress từ app tới Proxy và từ Proxy tới DB.
- TLS certificates/client settings phù hợp.
- Secret rotation handling và connection lifetime.

**Proxy không tự giải quyết một DB bị thiếu index, lock contention hoặc SQL sai.** Nó là công cụ quản lý kết nối/failover, không phải query optimizer.

## 14. Aurora: quan sát writer, readers, replication và Serverless

### 14.1. Aurora metrics riêng

| Metric | Dành cho | Cách hiểu |
| --- | --- | --- |
| **AuroraReplicaLag** | Aurora read replica instance. | Độ trễ replication, thường tính bằng milliseconds theo metric. |
| **AuroraReplicaLagMaximum** | Cluster/writer theo dimension được hỗ trợ. | Độ trễ cao nhất trong tập replicas. |
| **ServerlessDatabaseCapacity** | Aurora Serverless. | Mức capacity hiện tại theo **ACU**. |
| **ACUUtilization** | Aurora Serverless. | Tỷ lệ ACU đang dùng so với **maximum ACU** được cấu hình. |
| **VolumeBytesUsed** | Aurora cluster storage. | Dữ liệu cluster volume đã dùng. |
| **VolumeReadIOPs** | Aurora storage read I/O. | I/O usage, liên quan lựa chọn pricing. |
| **VolumeWriteIOPs** | Aurora storage writes. | I/O usage, không đọc y hệt EBS WriteIOPS của RDS instance. |
| **BufferCacheHitRatio** | Engine/instance phù hợp. | Tỷ lệ đọc thỏa từ buffer cache, cần đặt trong ngữ cảnh workload. |
| **FreeLocalStorage** | Khi engine/instance phát metric. | Dung lượng local temporary storage, **không** bằng shared Aurora cluster storage. |

**Không sao chép mọi alert FreeStorageSpace của RDS instance vào Aurora.** Aurora dùng shared storage model và có các chỉ số local temp/cluster volume khác nhau.

### 14.2. Aurora replica lag

Một API đọc từ reader ngay sau khi ghi vào writer có thể tạm thời thấy state cũ. Khi replication lag tăng:

- Ứng dụng báo trạng thái order chưa cập nhật.
- Report/dashboard bị trễ so với dữ liệu writer.
- Failover/read routing phức tạp hơn.
- Client có thể retry tạo tải cao hơn.

**Giải pháp không chỉ là thêm readers.** Cần kiểm tra write rate, reader load, queries chặn replication, transaction semantics, instance class và replication configuration. Với các tác vụ đòi hỏi read-after-write, route đọc về writer hoặc dùng cơ chế consistency phù hợp.

### 14.3. Aurora Serverless v2 ACU và bottlenecks

**Aurora Serverless** thay đổi compute capacity theo ACU trong phạm vi **MinCapacity/MaxCapacity**.

Ví dụ:

- Min = 2 ACU, Max = 16 ACU.
- Lúc cao điểm **ServerlessDatabaseCapacity = 16**.
- **ACUUtilization = 100%**: capacity đã chạm trần đã cấu hình.
- DB Load, CPU/waits và p95 latency cùng tăng → khả năng scale bị giới hạn; cần xem cả queries và max ACU.

Nếu ACU đạt max nhưng DB Load chủ yếu chờ **row locks**, tăng max ACU chưa chắc giải quyết. Nếu ACU còn thấp nhưng API latency cao, vấn đề có thể ở connection pool, network hoặc query waits.

### 14.4. Tối ưu Aurora không chỉ chọn ACU/instance class

- Tách truy vấn ghi nóng và đọc báo cáo khi kiến trúc hỗ trợ.
- Thử hiệu quả reader endpoint và routing consistency.
- Đo DB Load/top SQL trên **writer và từng reader**.
- Dùng index đúng, tránh full scans trên reader làm storage/cache thrash.
- Cân nhắc Aurora I/O-Optimized khi tỉ trọng I/O cost cao theo pricing calculator.
- Xem global replication lag nếu Aurora Global Database, không lẫn với AuroraReplicaLag nội Region.
- Đảm bảo backup/restore, failover và disaster recovery objectives (RPO/RTO).

### 14.5. RDS Multi-AZ: sự sẵn sàng khác hiệu năng

Multi-AZ giúp khả dụng khi instance/AZ lỗi; nhưng không mặc nhiên tăng query throughput cho ứng dụng. Đặc biệt với triển khai **RDS Multi-AZ DB instance** truyền thống, standby không phục vụ read queries; Multi-AZ DB cluster có khả năng readers theo model khác.

Khi failover, cần giám sát:

- **RDS events** liên quan failover/reboot.
- DB endpoint DNS resolution và JDBC reconnect time.
- HikariCP stale connections.
- RDS Proxy target health/borrow latency khi dùng.
- Transaction retry và idempotency (đừng xử lý lại charge/payment mà không có guard).

## 15. Dashboard và cảnh báo: tối thiểu nhưng đúng trọng tâm

Một dashboard tốt cho Orders production nên chia khu vực:

~~~mermaid
flowchart TB
    SLO["API SLI: p95, error rate, success orders"] --> DASH["RDS/Aurora dashboard"]
    DBI["DB Insights: DBLoad, top SQL, waits"] --> DASH
    CONN["Connections, pool pending, Proxy borrow latency"] --> DASH
    HOST["CPU, memory, IOPS, latency, storage"] --> DASH
    HA["Replica lag, events/failover, backup"] --> DASH
    COST["ACU/instances, I/O, logs, Proxy cost"] --> DASH
    DASH --> ALARM["CloudWatch Alarms + SNS/incident runbook"]
~~~

### 15.1. Gợi ý alarms (ngưỡng chỉ để minh họa)

| Metric | Ngưỡng ví dụ | Hành động khi vượt |
| --- | --- | --- |
| **API p95** | > 500 ms trong 10 phút. | Tách ứng dụng/DB latency bằng trace. |
| **CPUUtilization** | > 80% liên tục 10–15 phút. | Xem DBLoadCPU, top SQL, credits và background tasks. |
| **FreeableMemory** | Giảm bền vững dưới baseline an toàn. | Xem Enhanced Monitoring, swap, connections/cache. |
| **DatabaseConnections** | > 80% giới hạn connections hiệu dụng. | Xem pool fan-out, long transactions, app scaling. |
| **DBLoad / vCPU** | Vượt năng lực CPU tương ứng kèm CPU waits. | Xem hot SQL, CPU, query plans; không tự nâng instance. |
| **ReadLatency / WriteLatency** | Tăng so baseline/SLO trong nhiều periods. | Kiểm tra storage/IOPS/queue và query behavior. |
| **FreeStorageSpace** | Dưới 15–20% hoặc giá trị tối thiểu theo dự báo tăng dữ liệu **trên RDS instance phù hợp**. | Quy hoạch storage/autoscaling/cleanup trước khi hết. |
| **AuroraReplicaLag** | Vượt freshness SLO. | Kiểm tra readers, write workload, read routing. |
| **ACUUtilization** | Gần 100% lâu và latency tăng. | Xem Max ACU, DB Load/waits, cost. |
| **RDS Proxy borrow latency** | Tăng gấp nhiều lần baseline hoặc vượt SLO. | Xem pinning, pool utilization, DB max_connections. |
| **Slow-query count** | Tăng cùng thời gian đáp ứng xấu. | Tìm SQL top total time, locks/plan. |
| **RDS failover events** | Bất kỳ event impact production. | Runbook reconnect, multi-AZ health, data consistency. |

Không có một threshold **DatabaseConnections = 100** đúng cho mọi instance. max_connections khác theo engine, instance memory, parameter group, users và app topology.

### 15.2. Chọn statistic phù hợp

- **CPUUtilization:** Average/Maximum tùy mục tiêu.
- **DatabaseConnections:** thường dùng Average/Maximum để xem số kết nối đang mở; không dùng Sum làm tổng kết nối trong giờ.
- **IOPS/throughput:** Average/Maximum theo time series/đơn vị.
- **FreeStorageSpace:** Minimum để phát hiện gần đầy.
- **Replica lag:** Maximum khi mục tiêu freshness là worst-case.
- **DB Load:** Average (AAS); so DBLoadCPU với số vCPU.
- **RDS Proxy metrics:** tuân hướng dẫn statistic của từng metric, không áp một mẫu chung cho mọi gauge.

Tùy engine, một metric không có datapoint có thể là **not emitted/not applicable**, không phải chắc chắn bằng 0.

### 15.3. Alarm missing data và action

Với các workload low-traffic, CloudWatch metrics có thể thiếu datapoints. Chọn **treatMissingData** phù hợp:

- “No traffic” có thể bình thường với DB dev ngủ/không tải.
- “DB phải chạy phục vụ liên tục” nên kết hợp health checks và heartbeat.
- “DBLoad metric không emit khi idle” không được dùng missing làm bằng chứng failure.

Alarm nên có owner, severity, runbook, rollback route và lịch review. **Không bật Auto Scaling database/storage hoặc reboot RDS trực tiếp từ mọi alarm** khi chưa có guardrails.

## 16. Spring Boot/HikariCP: instrument connection pool và truy vấn

### 16.1. Cấu hình tham khảo

~~~properties
spring.datasource.url=jdbc:postgresql://orders-db.internal.example:5432/orders
spring.datasource.username=orders_app

# Password nhận từ secret injection/Secrets Manager, không commit.
spring.datasource.hikari.maximum-pool-size=12
spring.datasource.hikari.minimum-idle=4
spring.datasource.hikari.connection-timeout=3000
spring.datasource.hikari.idle-timeout=600000
spring.datasource.hikari.max-lifetime=1800000
spring.datasource.hikari.leak-detection-threshold=0

management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.metrics.tags.application=orders-api
management.metrics.tags.environment=prod
~~~

Đây là **ví dụ cho Spring Boot**, không phải cấu hình mặc định an toàn cho mọi hệ thống. **metrics/prometheus endpoints** cần được bảo vệ bằng network/authorization; không công khai metadata nội bộ ra Internet. Hikari pool settings cần test với DB connection lifetime, NAT/proxy, failover, readiness và số application replicas.

### 16.2. Metrics HikariCP thường gặp

Khi kết hợp Micrometer/Spring Boot Actuator có thể có các metrics như:

- **hikaricp.connections.active**: connections đang được mượn.
- **hikaricp.connections.idle**: connections nhàn rỗi.
- **hikaricp.connections.pending**: threads đang đợi lấy connection.
- **hikaricp.connections.max**: maximum pool size.
- **hikaricp.connections.acquire**: thời gian lấy connection.
- **hikaricp.connections.usage**: thời gian một connection được giữ.
- **hikaricp.connections.timeout**: số lần timeout khi lấy connection.

Tên metrics/tags và cách xuất hiện phụ thuộc Micrometer/Spring Boot versions/registry. Từ p95 acquire và pending, biết **app chờ pool** hay đã được cấp connection rồi chờ **SQL execution**.

### 16.3. Đặt nhãn ứng dụng vào DB sessions

PostgreSQL hỗ trợ JDBC connection parameter **ApplicationName** trong driver phù hợp. Ví dụ URL dành cho lab:

~~~text
jdbc:postgresql://orders-db.internal.example:5432/orders?ApplicationName=orders-api
~~~

Khi đó pg_stat_activity có thể nhóm theo **application_name**, giúp truy tìm service mở quá nhiều connections.

Không gắn customer/user ID vào application_name: gây high cardinality, rò rỉ dữ liệu, thậm chí ảnh hưởng monitoring.

### 16.4. Connection leaks và long transactions

Nếu Hikari active luôn bằng max, pending tăng nhưng DB CPU thấp, có thể:

- Code không trả connection về pool sau exception (nếu dùng JDBC raw không đóng try-with-resources).
- Transaction giữ connection trong khi chờ HTTP call.
- Query bị lock/timeout.
- JDBC streaming ResultSet giữ connection lâu.
- Pool timeout quá ngắn so workload hoặc DB đang chịu failover.

Java ví dụ đúng cách với JDBC raw:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import javax.sql.DataSource;

public final class OrderRepository {
    private final DataSource dataSource;

    public OrderRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean exists(String orderId) throws Exception {
        String sql = "SELECT 1 FROM orders WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, orderId);
            statement.setQueryTimeout(2);

            try (ResultSet rs = statement.executeQuery()) {
                return rs.next();
            }
        }
    }
}
~~~

Code minh họa **try-with-resources** đảm bảo JDBC connection được trả về pool khi kết thúc block, kể cả exceptions. Không tự chạy query nếu chưa có table/schema/DB credentials được phép. Với Spring Data JPA, framework quản lý connection/transaction theo context; vẫn cần audit transaction boundaries.

### 16.5. ORM N+1 problem

Một Spring Data/JPA API có thể thực hiện:

1. Một SELECT lấy 100 orders.
2. 100 SELECT lấy orderItems cho từng order.
3. 100 SELECT lấy customer cho từng order.

Tổng cộng **201 queries** cho một request. Dù mỗi SQL mất 5 ms, chỉ network/DB processing cộng dồn đã trên 1 giây. Giải pháp có thể là **join fetch/batch fetching/projections**, phù hợp pagination và memory. DB Insights top SQL sẽ cho thấy một SQL digest có rất nhiều calls và total execution time lớn.

**Tối ưu toàn request**, không chỉ tìm truy vấn chậm nhất theo max duration.

## 17. Bảo mật monitoring, logs và truy vấn chẩn đoán

### 17.1. Ranh giới IAM và DB privileges

| Principal | Quyền cần | Hạn chế |
| --- | --- | --- |
| **App runtime role** | Secrets Manager/KMS, AWS APIs theo nghiệp vụ; DB user privileges tối thiểu. | Không cấp rds:* hoặc DB SUPERUSER. |
| **Monitoring read-only role** | rds:Describe*, cloudwatch:GetMetricData, logs:GetQueryResults, pi:GetResourceMetrics theo scope. | Không cấp ModifyDBInstance, StartDBInstance hoặc DeleteDBInstance. |
| **DB monitoring SQL user** | Views thống kê và EXPLAIN được phép. | Không cấp toàn bộ quyền đọc business PII nếu không cần. |
| **DBA/operator** | Có quyền sửa parameter/index/query theo change management. | Tách khỏi quyền xem metrics/làm incident triage. |
| **Security/Audit** | CloudTrail, log retention, KMS, IAM role review. | Không làm lộ SQL literals, thông tin người dùng. |

**IAM read-only AWS không tự cấp quyền SELECT vào database.** SQL chẩn đoán yêu cầu một DB login/role thích hợp; **rds:DescribeDBInstances** không cho phép chạy SELECT qua JDBC.

### 17.2. SQL text có thể chứa secrets và PII

Ví dụ SQL không an toàn:

~~~sql
SELECT * FROM users
WHERE email = 'customer.private@example.invalid'
  AND password = 'plain-text-example';
~~~

Đây là ví dụ **cần tránh**. Nếu ứng dụng ghép literals trực tiếp, slow logs, Database Insights top SQL text, pg_stat_activity và error logs có thể ghi dữ liệu nhạy cảm.

Nên:

- Dùng **prepared statements/bind parameters** để ngăn SQL injection và giảm nguy cơ lộ literals.
- Tránh logging toàn bộ query parameters trong app/proxy.
- Chỉ chia sẻ normalized SQL digests và plan đã redacted.
- Đặt CloudWatch Logs retention/permissions, encryption, audit phù hợp.
- Phân quyền truy vấn các views có SQL text/queries của người khác.
- Không tải log thật sang máy cá nhân không được phê duyệt.

### 17.3. Log overhead là một phần của incident

Khi tăng log_statement = all hoặc long_query_time = 0, database phải format và xuất nhiều logs; CPU/I/O/CloudWatch ingest tăng, có thể làm sự cố hiệu năng **nặng thêm**. Với production:

1. Bắt đầu bằng ngưỡng 1 giây hoặc mức phù hợp SLO.
2. Thử sampling trước.
3. Theo dõi query p95 và DB CPU/IO khi bật.
4. Giới hạn thời gian debug và log group retention.
5. Giảm lại verbosity sau incident.
6. Bảo vệ logs khi truy cập/chia sẻ.

### 17.4. CloudTrail và RDS events không giống SQL audit log

- **CloudTrail** ghi các AWS API control-plane activities theo phạm vi cấu hình; ví dụ ModifyDBInstance, RebootDBInstance.
- **RDS events** ghi lifecycle events như failover, maintenance, backup, parameter change theo engine.
- **Slow query logs** ghi SQL vượt ngưỡng.
- **Database audit logs / pgAudit / MySQL audit** có mục đích audit operations khác và có overhead riêng.
- **App audit/business events** ghi thao tác thành công và actor/tenant theo chính sách.

Không coi CloudTrail tự ghi **mọi SELECT query** của database.

## 18. Cost: Database Insights, logs, storage và proxy

### 18.1. Các khoản chi phí cần nhìn

| Khoản | Drivers |
| --- | --- |
| **RDS/Aurora compute** | Instance class, số instances, giờ chạy, Aurora Serverless ACUs. |
| **Storage và I/O** | EBS size, gp3/provisioned IOPS, Aurora volume/I/O pricing model, snapshots. |
| **CloudWatch Database Insights** | Mode Standard/Advanced, retention, per-query/advanced features theo giá hiện hành. |
| **Enhanced Monitoring** | Tần suất OS metrics gửi tới CloudWatch Logs, log ingest/storage. |
| **Slow query/general/audit logs** | Log volume, CPU/I/O overhead, CloudWatch Logs ingestion/query. |
| **CloudWatch alarms/dashboards** | Metrics/alarms, custom metrics, Logs Insights query scan. |
| **RDS Proxy** | Proxy capacity/usage theo bảng giá, thêm networking và Secrets Manager. |
| **Data transfer** | Cross-AZ/Region data paths và replication theo dịch vụ, cần xem bảng giá cụ thể. |
| **Backup/snapshot** | Storage retention và cross-Region backup khi cấu hình. |

**Không có mặc định “Enhanced Monitoring 1-second luôn miễn phí”.** Dữ liệu càng dày, CloudWatch Logs charges có thể càng tăng. Database Insights Standard có retention baseline, còn Advanced/extended retention cần tính phí đúng feature plan và Region.

### 18.2. Không tối ưu chi phí bằng cách tắt tất cả monitoring

Một DB production có giá trị nghiệp vụ lớn có thể thiệt hại đáng kể khi:

- Mất khả năng xác định SQL gây incident.
- Không phát hiện storage sắp đầy.
- Không biết replica lag, dẫn đến đọc sai dữ liệu.
- Không theo dõi failures và high connection counts.
- Không có dữ liệu làm baseline trước/sau nâng instance.

Ưu tiên **cost-effective observability**: giữ metrics cơ bản và alerts, tối ưu retention/log volume, chỉ bật profiling sâu khi cần, và xác định các database quan trọng cần Advanced.

### 18.3. Ví dụ chi phí trên mỗi giao dịch

Giả sử theo tháng một dịch vụ có:

- DB compute + storage + I/O: 500 đơn vị chi phí.
- Monitoring/logs: 40 đơn vị.
- RDS Proxy: 60 đơn vị.
- Xử lý thành công **2.000.000 orders**.

\[
\text{Cost per 1000 orders}
=\frac{500+40+60}{2{,}000{,}000}\times1000
=0.3\ \text{đơn vị chi phí}
\]

Nếu một query tuning làm giảm DB compute/storage demand nhưng không làm tăng tỉ lệ lỗi và đủ SLO, đây là tối ưu có thể đo. **Con số không phải đơn giá AWS**, chỉ để minh họa KPI.

## 19. AWS CLI chỉ đọc: RDS và Aurora

Các ví dụ chỉ **mô tả/đọc metrics và logs**, không tạo hoặc sửa resource. Trước khi chạy, xác minh IAM principal, Region, DB identifier. **Không dùng lệnh modify-db-instance, reboot-db-instance, modify-db-parameter-group** trong bài.

### 19.1. Account và Region

~~~bash
aws sts get-caller-identity
aws configure get region
~~~

Nếu DB không xuất hiện, kiểm tra account/Region và permissions trước khi kết luận DB đã bị xóa.

### 19.2. Xem RDS DB instances

~~~bash
aws rds describe-db-instances \
  --region ap-southeast-1 \
  --query "DBInstances[].{Name:DBInstanceIdentifier,Engine:Engine,Class:DBInstanceClass,Status:DBInstanceStatus,AZ:AvailabilityZone,Cluster:DBClusterIdentifier,ResourceID:DbiResourceId,MonitoringInterval:MonitoringInterval,DatabaseInsights:DatabaseInsightsMode,PerfInsights:PerformanceInsightsEnabled}"
~~~

Quan trọng:

- **DbiResourceId** có dạng resource identifier dùng khi gọi **pi:GetResourceMetrics** hoặc DescribeDimensionKeys.
- **DBClusterIdentifier** cho biết instance thuộc cluster nào.
- **MonitoringInterval** = 0 nếu Enhanced Monitoring không bật.
- **DatabaseInsightsMode/PerformanceInsightsEnabled** tùy engine/CLI version.

### 19.3. Xem cluster members và endpoints

~~~bash
aws rds describe-db-clusters \
  --region ap-southeast-1 \
  --query "DBClusters[].{Cluster:DBClusterIdentifier,Engine:Engine,Status:Status,Endpoint:Endpoint,ReaderEndpoint:ReaderEndpoint,Members:DBClusterMembers,Capacity:ServerlessV2ScalingConfiguration,Insights:DatabaseInsightsMode}"
~~~

Đối chiếu **IsClusterWriter** trong DBClusterMembers khi chẩn đoán failover. Đừng đo metrics của reader cũ rồi coi nó vẫn là writer sau khi roles chuyển.

### 19.4. Parameter groups và log exports

~~~bash
aws rds describe-db-parameters \
  --db-parameter-group-name orders-postgres-custom \
  --region ap-southeast-1 \
  --query "Parameters[?contains(['log_min_duration_statement','log_statement','log_lock_waits','shared_preload_libraries'], ParameterName)].{Name:ParameterName,Value:ParameterValue,Apply:ApplyType,Source:Source}"

aws rds describe-db-cluster-parameters \
  --db-cluster-parameter-group-name orders-aurora-custom \
  --region ap-southeast-1 \
  --query "Parameters[?contains(['log_min_duration_statement','log_statement','slow_query_log','long_query_time','log_output'], ParameterName)].{Name:ParameterName,Value:ParameterValue,Apply:ApplyType,Source:Source}"
~~~

Parameter group nào áp dụng ở **DB instance** hay **DB cluster** phụ thuộc engine và parameter; các command trả về giá trị **cấu hình parameter group**, không nhất thiết đảm bảo runtime đã áp dụng nếu status pending-reboot. Đối chiếu **PendingModifiedValues/DBParameterGroups.ParameterApplyStatus** hoặc engine query SELECT current_setting/SHOW VARIABLES phù hợp.

### 19.5. Đọc RDS logs thông qua API

~~~bash
aws rds describe-db-log-files \
  --db-instance-identifier orders-postgres-prod \
  --region ap-southeast-1
~~~

Với DB log có sẵn, có thể dùng **download-db-log-file-portion** để đọc một phần:

~~~bash
aws rds download-db-log-file-portion \
  --db-instance-identifier orders-postgres-prod \
  --log-file-name "error/postgresql.log" \
  --number-of-lines 100 \
  --region ap-southeast-1
~~~

**Tên log file là placeholder**; lấy đúng tên từ describe-db-log-files. API này đọc logs nhưng output có thể chứa SQL text/PII; không chia sẻ raw output không được phép.

### 19.6. CloudWatch CPU và DatabaseConnections

~~~bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name CPUUtilization \
  --dimensions Name=DBInstanceIdentifier,Value=orders-postgres-prod \
  --start-time 2026-11-19T00:00:00Z \
  --end-time 2026-11-20T00:00:00Z \
  --period 300 \
  --statistics Average Maximum \
  --region ap-southeast-1

aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name DatabaseConnections \
  --dimensions Name=DBInstanceIdentifier,Value=orders-postgres-prod \
  --start-time 2026-11-19T00:00:00Z \
  --end-time 2026-11-20T00:00:00Z \
  --period 300 \
  --statistics Average Maximum \
  --region ap-southeast-1
~~~

Time window ở đây là **ví dụ UTC cho ngày 19/11/2026**; thay bằng sự cố cần nghiên cứu. Kết quả CloudWatch không mặc định sắp xếp Datapoints theo timestamp; khi phân tích cần sort time.

### 19.7. CloudWatch Database Insights / PI API

Tùy engine và Database Insights mode, AWS vẫn dùng **Performance Insights API namespace (pi)** để đọc detailed DB load metrics.

~~~bash
aws pi get-resource-metrics \
  --service-type RDS \
  --identifier db-EXAMPLEDBRESOURCEID \
  --start-time 2026-11-19T00:00:00Z \
  --end-time 2026-11-20T00:00:00Z \
  --period-in-seconds 300 \
  --metric-queries '[{"Metric":"db.load.avg"}]' \
  --region ap-southeast-1
~~~

**Identifier là DbiResourceId**, không phải DBInstanceIdentifier như orders-postgres-prod. Lệnh này chỉ trả dữ liệu khi mode, engine, permissions và retention phù hợp. Nếu CLI báo InvalidParameter/AccessDenied, đừng tự động chuyển sang lệnh sửa DB: kiểm tra Identifier, Region, IAM và mode.

### 19.8. RDS events/failover

~~~bash
aws rds describe-events \
  --source-type db-instance \
  --source-identifier orders-postgres-prod \
  --duration 1440 \
  --region ap-southeast-1
~~~

RDS events có thể cho thấy reboot/maintenance/failover/low storage events tùy source. Không thay thế CloudWatch metrics/traces và database engine logs.

### 19.9. Read-only kiểm tra RDS Proxy

~~~bash
aws rds describe-db-proxies \
  --region ap-southeast-1

aws rds describe-db-proxy-target-groups \
  --db-proxy-name orders-db-proxy \
  --region ap-southeast-1
~~~

Cần xem **RequireTLS, Auth, VpcSubnetIds, VpcSecurityGroupIds** và target group connection pool config; tránh in ra những secret ARNs/identifiers không cần thiết trong public ticket.

### 19.10. CloudWatch Logs

~~~bash
aws logs describe-log-groups \
  --log-group-name-prefix "/aws/rds/" \
  --region ap-southeast-1

aws logs describe-log-groups \
  --log-group-name-prefix "RDSOSMetrics" \
  --region ap-southeast-1

aws cloudwatch describe-alarms \
  --alarm-name-prefix "orders-db-" \
  --region ap-southeast-1
~~~

Log groups có thể không tồn tại nếu exports/Enhanced Monitoring chưa bật. Chọn log group và range đúng trước khi đọc SQL text, giữ tuân thủ data handling policy.

## 20. Runbook điều tra DB chậm theo thứ tự

~~~mermaid
flowchart TD
    A["API latency/DB errors tăng"] --> B{"Ứng dụng có chờ pool?"}
    B -->|"Có"| C["Hikari active/pending/acquire; RDS Proxy BorrowLatency"]
    B -->|"Không"| D{"DBLoad top wait?"}
    C --> D
    D -->|"CPU"| E["Top SQL, EXPLAIN, indexes, CPU credits"]
    D -->|"Lock"| F["Blocking sessions, xact age, transactions"]
    D -->|"I/O"| G["Read/WriteLatency, throughput, queue, cache"]
    D -->|"N/A hoặc thấp"| H["Network/DNS/TLS, API tier, tracing"]
    E --> I["Tối ưu và load-test, so p95/DBLoad/cost"]
    F --> I
    G --> I
    H --> I
~~~

### 20.1. Bước 1: xác định phạm vi và tác động

Ghi lại:

- AWS **Account/Region**, DB instance/cluster/endpoint, writer hay reader.
- App/version/deploy time, request path, p95/p99, error rate.
- Time window UTC và traffic baseline.
- DB failover/maintenance events gần thời điểm.
- Hikari pool active/pending và connection acquisition.
- Số ECS tasks/Lambda concurrency/web instances.

### 20.2. Bước 2: đối chiếu metrics

- DatabaseConnections tăng trong khi app count tăng → pool fan-out.
- DBLoad CPU tăng, CPUUtilization cao → CPU pressure.
- DBLoad lock cao, CPU thấp → lock waits/transaction issues.
- ReadLatency/queue tăng → storage I/O.
- FreeStorageSpace giảm → storage capacity.
- Aurora ACUUtilization chạm 100% → max ACU có thể giới hạn scale, nhưng phải xem waits.
- AuroraReplicaLag tăng → stale reads/replication issues.

### 20.3. Bước 3: top SQL và execution plan

- Xác định SQL digest đóng góp **total load/time lớn nhất**.
- Đọc slow log và pg_stat_statements/Performance Schema.
- Kiểm tra rows examined vs rows returned, predicates, sort, join order, indexes.
- Không tạo index dựa chỉ vào một query sample mà bỏ qua write overhead.
- Với locks, tìm blocker/transaction boundary trước khi thay index.

### 20.4. Bước 4: chọn hành động an toàn

| Nguyên nhân | Hướng xử lý |
| --- | --- |
| Hot query quét nhiều rows | Index hợp lý, query rewrite, phân trang, tránh N+1. |
| Lock wait do long transaction | Rút ngắn transaction, xử lý retry/idempotency, sửa migration process. |
| Connection storm | Giảm Hikari pool fan-out, reuse, RDS Proxy, giới hạn concurrency. |
| DB CPU-bound | Tối ưu top CPU SQL trước, sau đó đánh giá instance scaling. |
| EBS/storage latency | Kiểm tra IOPS/throughput/tầng storage và query access pattern. |
| Replica lag | Kiểm tra reader load/write rate, routing consistency và replication metrics. |
| Log flood | Giảm verbosity/đặt sampling, giữ logs cần điều tra. |
| Credential/network lỗi | Kiểm tra SG/DNS/TLS/secrets/IAM; không mở DB public. |

### 20.5. Bước 5: xác minh sau thay đổi

Mọi tối ưu cần có **before/after measurement**:

- p95/p99 API và query latency.
- Error rate, pool acquisition wait và retries.
- DB Load (AAS) theo wait type.
- CPU, memory, Read/WriteLatency, IOPS.
- Business correctness/transaction outcomes.
- Chi phí instance/ACU/logging/Proxy.
- Không có regression với traffic peak và failover.

## 21. Tình huống thực tế A — HikariCP quá tải khi ECS scale

**Bối cảnh:** Có 5 tasks, mỗi task max pool 20. Sau đợt sale tăng lên 20 tasks; DB max_connections 250.

Trước khi scale:

\[
5\times20=100\text{ connections lý thuyết}
\]

Sau khi scale:

\[
20\times20=400\text{ connections lý thuyết}
\]

Dấu hiệu:

- Hikari pending/acquire time tăng.
- DatabaseConnections tăng rồi chạm trần.
- DB CPU có thể vẫn thấp, vì app không lấy được connection để gửi query.
- Nếu clients liên tục mở connection rồi fail, TLS/auth overhead tăng.

**Xử lý:** giảm per-task pool theo capacity thực, đặt concurrency/backpressure, cân nhắc RDS Proxy; kiểm tra actual utilization và DB max_connections trước khi sửa. Không tăng max_connections vô hạn vì DB memory cũng có giới hạn.

## 22. Tình huống thực tế B — CPU thấp nhưng orders API timeout

**Bối cảnh:** DatabaseConnections ổn định, CPU 35%, DBLoad 22 AAS tập trung ở Lock; một SQL UPDATE orders giữ lock lâu.

**Điều tra:**

1. Database Insights hiển thị top wait Lock.
2. pg_stat_activity tìm session có transaction_age lớn.
3. pg_blocking_pids xác định blocker.
4. App trace cho thấy @Transactional method gọi external payment API trước commit.
5. Rút gọn transaction, tách external call, đảm bảo payment idempotency và outbox khi cần.

**Không nên:** tăng instance RAM/vCPU ngay khi vấn đề là lock held time.

## 23. Tình huống thực tế C — Aurora reader lag sau báo cáo cuối tháng

**Bối cảnh:** Query báo cáo chạy trên Aurora reader, read latency tăng, ReplicaLag tăng và khách hàng đọc trạng thái đơn chưa mới.

**Điều tra:**

- So **AuroraReplicaLag** từng reader, đừng chỉ xem cluster average.
- Xem top SQL và I/O load trên reader chạy report.
- Kiểm tra query có full scan, sort lớn, thiếu index hoặc dùng connection/transaction lâu không.
- So write workload/CPU writer và topology readers.
- Với tác vụ cần read-your-writes, đưa request về writer endpoint theo policy.
- Tách reporting workload hoặc tăng read capacity có kiểm chứng.

**Không nên:** nói “Aurora storage shared nên mọi replica luôn nhất quán tức thì”.

## 24. Tình huống thực tế D — Slow-query log làm DB chậm thêm

**Bối cảnh:** Team điều tra query slow và bật PostgreSQL **log_statement = all**, **log_min_duration_statement = 0**, export logs sang CloudWatch. Sau đó CPU tăng và logs cost tăng mạnh.

**Nguyên nhân có thể:** logging hầu như mọi statement tạo formatting/disk/log export overhead; SQL literals có thể bị lộ.

**Sửa:** chuyển sang **log_statement=none** và ngưỡng/sampling phù hợp theo change process, theo dõi CPU/p95 và logs volume, đặt retention/IAM phù hợp. Chỉ dùng verbose debug logging ngắn hạn có owner/rollback.

## 25. Tình huống thực tế E — RDS Proxy vẫn không giảm connections

**Bối cảnh:** Lambda dùng RDS Proxy nhưng Proxy **ClientConnections** và **DatabaseConnections** gần như bằng nhau; BorrowLatency tăng.

**Khả năng:** nhiều sessions bị **pinning** hoặc transactions giữ connection lâu.

**Điều tra:** xem SessionPinned/Borrowed/MaxAllowed, query patterns, long transaction, session variables, prepared statements theo engine. Tối ưu application session state và transaction boundaries. Không giả định Proxy luôn multiplex mọi truy vấn.

## 26. Sai lầm phổ biến

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “CPU 40% thì DB không thể là bottleneck.” | Locks, I/O, connection pool, replication có thể gây chậm dù CPU thấp. |
| “DatabaseConnections = số SQL đang chạy.” | Bao gồm connections idle; không đồng nghĩa active query count. |
| “DB Load = CPUUtilization.” | DB Load là **AAS**, gồm CPU và waits; CPUUtilization là %. |
| “DBLoad = 10 nghĩa có đúng 10 requests trong phút.” | Không; là trung bình số sessions active trong time window. |
| “FreeableMemory gần 0 nghĩa chắc chắn thiếu RAM.” | Cần xem buffer/cache, swap, OS metrics và xu hướng. |
| “Tất cả RDS/Aurora có FreeStorageSpace giống nhau.” | Aurora shared volume dùng các metrics storage khác RDS EBS. |
| “Multi-AZ standby luôn phục vụ SELECT.” | RDS Multi-AZ DB instance standby truyền thống không dùng như read replica. |
| “Aurora reader endpoint bảo đảm đọc thấy write mới ngay.” | Replica lag và read routing vẫn phải được xem xét. |
| “Performance Insights console là công cụ duy nhất phải học.” | Hướng hiện hành là **CloudWatch Database Insights**. |
| “Cần bật log_statement=all vĩnh viễn để tìm query chậm.” | Logging quá mức có overhead, phí và rủi ro lộ dữ liệu. |
| “PostgreSQL log_min_duration_statement dùng giây.” | Dùng **milliseconds**. |
| “MySQL long_query_time dùng milliseconds.” | Dùng **seconds**. |
| “MySQL log_output=TABLE đủ để CloudWatch export slow log.” | CloudWatch slow log export cần **FILE** theo hướng dẫn RDS/Aurora. |
| “EXPLAIN ANALYZE chỉ đọc plan nên vô hại.” | Nó thực thi query; có thể tốn tài nguyên và tạo side effects. |
| “pg_stat_statements là slow log nguyên văn mọi lần gọi.” | Là thống kê tích lũy/normalized SQL, không thay raw log. |
| “Tăng Hikari maximumPoolSize luôn làm app nhanh hơn.” | Có thể vượt max_connections và gây nghẽn. |
| “RDS Proxy tự sửa query thiếu index.” | Proxy quản lý connections, không tối ưu execution plan. |
| “RDS Proxy loại bỏ mọi database connections.” | Nó dùng connection pool; session pinning và transactions có giới hạn. |
| “CloudWatch metric missing = DB khỏe.” | Có thể do không applicable, không phát datapoint hoặc sai dimension. |
| “CloudTrail tự ghi mọi SQL query của DB.” | CloudTrail chủ yếu ghi AWS API events; query logging/audit khác. |
| “Chỉ cần tăng ACU khi Aurora Serverless chạm max.” | Phải xem DB Load/waits/locking và workload, rồi mới quyết định. |
| “Bật 1-second Enhanced Monitoring luôn miễn phí.” | CloudWatch Logs ingest/storage và chi phí vận hành có thể tăng. |

## 27. Bài tập thực hành có đáp án gợi ý

### Bài tập 1 — Phân biệt DBLoad và connections

**Đề:** RDS PostgreSQL có 250 DatabaseConnections, DB Load = 3 AAS, CPUUtilization = 20%.

**Câu hỏi:** Có thể kết luận database đang chạy 250 queries đồng thời?

**Đáp án:** Không. Có thể nhiều connections idle, chỉ khoảng 3 sessions active trung bình. Xem pg_stat_activity theo **state**, HikariCP active/idle và memory usage. Nếu không có pool wait/connection churn, 250 kết nối mở chưa chắc cần sửa ngay; cần so max_connections và xu hướng.

### Bài tập 2 — CPU thấp, Lock wait cao

**Đề:** p95 API tăng 10 lần, CPU DB 25%, DBLoadNonCPU 18 AAS và top wait là Lock.

**Đáp án:** Tập trung vào blocking transactions; xem pg_stat_activity, pg_blocking_pids, transaction_age và code Java @Transactional. Không mặc định tăng vCPU. Có thể cần rút ngắn transaction, bổ sung retries idempotent và thay cách cập nhật row hot.

### Bài tập 3 — Ngưỡng PostgreSQL vs MySQL

**Đề:** Muốn log các queries chạy từ 750 ms trở lên.

**Đáp án:** PostgreSQL dùng **log_min_duration_statement=750** (milliseconds). MySQL dùng **long_query_time=0.75** (seconds), với **slow_query_log=1**, **log_output=FILE** khi muốn export CloudWatch Logs.

### Bài tập 4 — HikariCP và ECS Auto Scaling

**Đề:** DB max_connections = 500, mỗi ECS task pool tối đa 24, có 30 tasks lúc peak.

**Tính:**

\[
30\times24=720
\]

**Đáp án:** Upper bound từ app pools đã vượt max_connections, chưa tính admin/maintenance. Cần sizing pool theo tổng tasks/concurrency, rút ngắn query/transaction, RDS Proxy khi phù hợp hoặc cân nhắc capacity database. Không chỉ sửa max_connections lên 1.000 nếu RAM/instance không đáp ứng.

### Bài tập 5 — SQL chậm do quá nhiều calls

**Đề:** Database Insights hiển thị query A trung bình 8 ms, gọi 100.000 lần/phút; query B trung bình 2.000 ms nhưng chỉ gọi một lần/phút.

**Đáp án:** Query A có tổng execution time lý thuyết khoảng **800.000 ms/phút** trước concurrency; query B khoảng **2.000 ms/phút**. A có thể là cơ hội tối ưu throughput/chi phí lớn hơn. Xem ORM N+1, caching và batching. Với SLO tail latency của endpoint cụ thể, B vẫn cần xử lý nếu làm người dùng chậm.

### Bài tập 6 — Slow query log không tới CloudWatch

**Đề:** RDS MySQL bật slow_query_log=1 nhưng không thấy log stream slowquery.

**Đáp án:** Kiểm tra **log_output=FILE**, long_query_time, query thực sự vượt ngưỡng, **EnabledCloudwatchLogsExports** có **slowquery**, đúng account/Region/log group và IAM log read permissions. Không coi slow query log TABLE tự được export.

### Bài tập 7 — Phân biệt EXPLAIN và EXPLAIN ANALYZE

**Đề:** Một DBA muốn dùng EXPLAIN ANALYZE cho UPDATE production đang lock nhiều hàng.

**Đáp án:** Dừng và đánh giá change risk; EXPLAIN ANALYZE **thực thi UPDATE**, có side effects. Đầu tiên dùng EXPLAIN plan phù hợp, logs/Database Insights, thử trên staging với dữ liệu đại diện và giao dịch rollback nếu được duyệt/đúng kỹ thuật.

### Bài tập 8 — FreeStorageSpace trên Aurora

**Đề:** Dashboard dùng cảnh báo FreeStorageSpace dưới 20 GiB cho mọi RDS instance và Aurora cluster.

**Đáp án:** Phân loại storage model. RDS EBS instance có **FreeStorageSpace**; Aurora shared cluster volume cần theo dõi **VolumeBytesUsed** và metrics local temp storage/cluster capacity có liên quan. Không áp cùng một alert vô điều kiện.

### Bài tập 9 — Aurora Serverless đạt max ACU

**Đề:** Aurora Serverless max 16 ACU, ACUUtilization 100%, DB Load cao nhưng 80% thời gian sessions chờ Lock.

**Đáp án:** Tăng Max ACU có thể không xử lý Lock contention. Tìm blocker/transaction duration, tối ưu concurrency/hot rows, sau đó load-test và xem có thiếu CPU/I/O thật sự không.

### Bài tập 10 — RDS Proxy pinning

**Đề:** DatabaseConnections của Proxy gần bằng ClientConnections, mặc dù đã bật connection pooling.

**Đáp án:** Xem DatabaseConnectionsCurrentlySessionPinned, BorrowLatency, transaction/session state và engine-specific pinning rules. Có thể app dùng session variables hoặc transactions dài khiến backend connections bị pin. Proxy không bảo đảm multiplex mọi client.

### Bài tập 11 — Replica lag và tính nhất quán

**Đề:** Sau khi user cập nhật địa chỉ giao hàng, API đọc từ Aurora reader trả địa chỉ cũ trong vài trăm ms.

**Đáp án:** Đây có thể là replication lag; kiểm tra AuroraReplicaLag và read routing. Các request cần **read-after-write** nên đọc từ writer hoặc dùng cơ chế consistency thích hợp. Không mặc định reader endpoint là strongly consistent.

### Bài tập 12 — Nhận diện chỉ số cần alarm

**Đề:** Một database có CPU bình thường nhưng **FreeStorageSpace** giảm đều 3 GiB/ngày; còn 18 GiB.

**Tính:** 18 / 3 ≈ **6 ngày** theo giả định tăng đều.

**Đáp án:** Ngoài threshold tuyệt đối, cần **capacity forecast alarm** và plan mở rộng/cleanup đúng storage type. Không đợi tới ngày hết chỗ. Kiểm tra auto storage scaling settings, backup/retention và large objects/log tables.

### Bài tập 13 — Logging và PII

**Đề:** Team cần debug một truy vấn SELECT theo email khách hàng, muốn bật SQL log mức verbose trên toàn bộ database.

**Đáp án:** Ưu tiên Database Insights SQL digest/parameterized app logs và threshold/sampling theo time window. Kiểm soát access, redaction, CloudWatch retention/KMS; không bật log_statement=all dài hạn vì SQL text có thể chứa PII và tạo overhead.

### Bài tập 14 — Failover làm connections lỗi

**Đề:** Aurora writer failover khiến Java API bị lỗi vài chục giây dù cluster có nhiều AZ.

**Đáp án:** HA không đồng nghĩa mọi TCP connections còn sống. Cần xử lý stale JDBC connections, DNS endpoint, retry với backoff/idempotency, RDS Proxy khi phù hợp, transaction failures và application readiness. Giám sát RDS events/role changes và thử failover định kỳ có kiểm soát.

### Bài tập 15 — Giải thích Cost Explorer tăng

**Đề:** Database instance class không thay đổi, nhưng AWS bill tăng khi team bật logs/Advanced insights và thêm RDS Proxy.

**Đáp án:** Chi phí có thể đến từ **Database Insights mode/retention, CloudWatch Logs ingest/storage/queries, Enhanced Monitoring sampling và RDS Proxy**. So Cost Explorer/CUR theo Service/Usage Type và thời gian thay đổi, kết hợp metrics. Không kết luận instance pricing tăng khi chưa có dữ liệu.

## 28. Câu hỏi tự kiểm tra

**Câu 1.** DB Load được đo theo đơn vị nào?  
**Đáp án:** **Average Active Sessions (AAS)**.

**Câu 2.** DatabaseConnections = DBLoad đúng hay sai?  
**Đáp án:** Sai; có connections idle và sessions active/đợi resources.

**Câu 3.** DBLoadCPU liên quan gì?  
**Đáp án:** AAS dành cho CPU; không phải cùng đơn vị với CPUUtilization %.

**Câu 4.** Khi CPU thấp nhưng DB Load Lock cao cần làm gì?  
**Đáp án:** Tìm blocker và long-running transactions.

**Câu 5.** CloudWatch metric namespace phổ biến của RDS/Aurora?  
**Đáp án:** **AWS/RDS**.

**Câu 6.** Enhanced Monitoring đưa OS metrics tới đâu?  
**Đáp án:** **CloudWatch Logs**, thường ở log group **RDSOSMetrics**.

**Câu 7.** Enhanced Monitoring có thể lấy mẫu mỗi 1 giây không?  
**Đáp án:** Có với granularities được hỗ trợ, nhưng có log volume/chi phí và giới hạn hiển thị.

**Câu 8.** CloudWatch Database Insights Standard và Advanced khác chủ yếu ở đâu?  
**Đáp án:** Advanced cung cấp các công cụ phân tích SQL/waits/plans/locks và fleet/per-query views chuyên sâu hơn tùy engine; retention/pricing cũng khác.

**Câu 9.** Vì sao không chỉ dùng Average CPUUtilization để xác định root cause?  
**Đáp án:** Database có thể nghẽn locks, I/O, connections hoặc replica lag dù CPU thấp.

**Câu 10.** RDS for PostgreSQL log_min_duration_statement dùng đơn vị gì?  
**Đáp án:** **Milliseconds**.

**Câu 11.** MySQL long_query_time dùng đơn vị gì?  
**Đáp án:** **Seconds**, có thể nhận số thập phân theo storage log/engine.

**Câu 12.** Muốn MySQL slow logs xuất hiện trong CloudWatch cần log_output nào?  
**Đáp án:** **FILE**, đồng thời bật slow_query_log và log export.

**Câu 13.** pg_stat_activity dùng để làm gì?  
**Đáp án:** Quan sát sessions, state, wait events, query/transaction age.

**Câu 14.** pg_stat_statements cho biết gì?  
**Đáp án:** Thống kê tích lũy theo normalized SQL, số calls và execution time.

**Câu 15.** EXPLAIN ANALYZE có chạy câu SQL không?  
**Đáp án:** Có; vì thế cần đánh giá resource/side effects trước khi chạy.

**Câu 16.** MySQL SHOW PROCESSLIST có thể giúp gì?  
**Đáp án:** Xem sessions/threads và trạng thái hoạt động/chờ.

**Câu 17.** Điều gì có thể khiến Hikari pending tăng?  
**Đáp án:** Pool hết connections vì SQL chậm, long transaction, leak, burst hoặc backend lỗi.

**Câu 18.** 10 ECS tasks, mỗi task pool max=30 → upper bound?  
**Đáp án:** **300 DB connections**, chưa tính apps khác.

**Câu 19.** RDS Proxy có tự sửa query chậm không?  
**Đáp án:** Không; nó giúp quản lý/pool connections và failover, không tối ưu SQL plan.

**Câu 20.** RDS Proxy session pinning ảnh hưởng gì?  
**Đáp án:** Giảm multiplexing, có thể cần nhiều backend connections hơn.

**Câu 21.** DatabaseConnectionsBorrowLatency của RDS Proxy dùng đơn vị gì?  
**Đáp án:** **Microseconds** theo metric.

**Câu 22.** RDS Multi-AZ standby truyền thống có là read replica không?  
**Đáp án:** Không. Standby của Multi-AZ DB instance phục vụ HA, không phải read scaling.

**Câu 23.** AuroraReplicaLag cần dùng để đánh giá điều gì?  
**Đáp án:** Độ trễ replica, ảnh hưởng freshness của reads.

**Câu 24.** Aurora Serverless dùng chỉ số nào theo dõi mức ACU hiện tại?  
**Đáp án:** **ServerlessDatabaseCapacity**, cùng **ACUUtilization**.

**Câu 25.** Có nên áp FreeStorageSpace alarm của RDS EBS cho mọi Aurora cluster không?  
**Đáp án:** Không, vì Aurora shared storage metrics khác.

**Câu 26.** Khi một query xuất hiện hàng trăm nghìn lần, metric nào quan trọng?  
**Đáp án:** **Calls và total execution time**, không chỉ maximum time.

**Câu 27.** CloudTrail có ghi mọi SELECT SQL không?  
**Đáp án:** Không, CloudTrail chủ yếu ghi AWS API activities; SQL logging/audit là lớp khác.

**Câu 28.** Vì sao verbose logging có thể làm database chậm hơn?  
**Đáp án:** Tăng CPU/I/O log formatting/export và chi phí CloudWatch Logs.

**Câu 29.** Khi RDS Proxy BorrowLatency tăng cần kiểm tra gì?  
**Đáp án:** Backend pool usage/headroom, session pinning, transactions và max DB connections.

**Câu 30.** Vì sao phải xác minh KPI nghiệp vụ sau tối ưu query?  
**Đáp án:** Tốc độ tăng không được đánh đổi tính đúng đắn, transaction consistency hay availability.

## 29. Tổng kết và checklist production

Một hệ thống RDS/Aurora khỏe không thể được chứng minh bởi chỉ **CPUUtilization = 30%**. Cần liên kết:

- **Ứng dụng:** p95/p99, HTTP errors, transaction outcomes, HikariCP pool acquisition.
- **Database Insights:** DB Load/AAS, top SQL/waits, blocking và plans theo engine/mode hỗ trợ.
- **Infrastructure:** CPU, FreeableMemory, I/O latency/queue/throughput, storage headroom.
- **Connections:** DatabaseConnections, engine max_connections, RDS Proxy client/backend pool/pinning.
- **Aurora:** writer/reader topology, replica lag, Aurora Serverless ACU và storage metrics riêng.
- **Logs:** PostgreSQL slow logs/MySQL slowquery với thresholds, sampling, privacy/retention.
- **Recovery:** RDS events, failover/reconnect, backup/restore, RPO/RTO và regression tests.
- **Chi phí:** DB class/ACU/IO, Database Insights, Enhanced Monitoring, Logs, Proxy.

### Checklist sẵn sàng vận hành

1. Xác nhận đúng **account, Region, engine, DB instance/cluster, writer/reader**.
2. Có dashboard CloudWatch **AWS/RDS** và Database Insights **DBLoad/waits**.
3. App có **Hikari metrics, traces, transaction latency và business SLO**.
4. Tính **pool capacity = số app instances × maximumPoolSize** cộng services khác và headroom.
5. Sử dụng **slow-query logging** ngưỡng/sampling phù hợp, không log toàn bộ SQL vô thời hạn.
6. Bảo vệ SQL text/credentials trong CloudWatch Logs; đặt retention và IAM/KMS.
7. Định kỳ phân tích **top SQL by total time, avg/p95, waits, rows examined, execution plan**.
8. Có RDS Proxy metrics/pinning monitoring nếu Proxy được sử dụng.
9. Giám sát **storage/IO/replica lag/ACU** đúng theo RDS, Aurora và engine.
10. Alert có owner, severity, runbook và missing-data treatment phù hợp.
11. Test failover/reconnect và database migration; không phụ thuộc một DB connection sống mãi.
12. Mọi tối ưu đều có benchmark trước/sau gồm performance, business correctness và cost.
13. Không để người chỉ xem metrics có quyền reboot/sửa DB hoặc truy cập toàn bộ dữ liệu khách hàng.
14. So Cost Explorer/CUR để kiểm soát Database Insights, Enhanced Monitoring, logging và RDS Proxy.

**Kết luận:** Phát hiện “database chậm” mới là điểm bắt đầu. Để khắc phục hiệu quả, người học phải đi từ **triệu chứng người dùng** tới **DB Load/wait class**, từ đó xác định **câu SQL, transaction, connection pool hoặc tài nguyên** gây nghẽn, và chỉ triển khai thay đổi sau khi đo hiệu quả trên workload phù hợp. Đó là cách vận hành RDS/Aurora an toàn, có khả năng phục hồi và tránh chi phí tăng không kiểm soát.

### Tài liệu AWS chính thức

- [Amazon RDS metrics reference](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-metrics.html) — CPU, DatabaseConnections, storage, IOPS và latency.
- [Monitoring RDS with CloudWatch](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/monitoring-cloudwatch.html) — giám sát metrics chuẩn.
- [CloudWatch Database Insights](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Database-Insights.html) — Standard/Advanced, DB Load và công cụ quan sát.
- [Database Insights for RDS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_DatabaseInsights.html) — RDS metrics và query analysis.
- [Database Insights slow SQL configuration — RDS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_DatabaseInsights.SlowSQL.html) — slow SQL settings PostgreSQL/MySQL.
- [Database Insights slow SQL configuration — Aurora](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/USER_DatabaseInsights.SlowSQL.html) — parameter groups cho Aurora.
- [Enhanced Monitoring OS metrics](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_Monitoring.OS.html) — chi tiết OS processes, sampling, CloudWatch Logs.
- [Enhanced Monitoring OS metric access](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_Monitoring.OS.CloudWatchLogs.html) — RDSOSMetrics logs.
- [RDS PostgreSQL database logs](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_LogAccess.Concepts.PostgreSQL.html) — CloudWatch export, SQL query logging.
- [Aurora PostgreSQL query logging](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/USER_LogAccess.Concepts.PostgreSQL.Query_Logging.html) — parameters và log risks.
- [RDS MySQL slow query logs](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_LogAccess.MySQL.LogFileSize.html) — long_query_time, FILE/TABLE và export.
- [Aurora MySQL logging](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/USER_LogAccess.MySQL.LogFileSize.html) — slow query logging và default.
- [RDS Proxy metrics](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy.monitoring.html) — BorrowLatency, pinning, client/backend connections.
- [RDS Proxy connection considerations](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy-connections.html) — connection headroom, MaxConnectionsPercent.
- [Aurora CloudWatch metrics](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.AuroraMonitoring.Metrics.html) — AuroraReplicaLag, ServerlessDatabaseCapacity, ACUUtilization.
- [Aurora Serverless v2 monitoring](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2-administration.html) — capacity metrics và autoscaling.
- [AWS Database Blog — Performance impact of excessive logging in Aurora PostgreSQL](https://aws.amazon.com/blogs/database/performance-impact-of-excessive-logging-in-amazon-aurora-postgresql/) — ví dụ ảnh hưởng logging đã công bố 19/11/2026.





