# Lựa chọn Cloud SQL, AlloyDB và cơ sở dữ liệu tự quản lý

Một doanh nghiệp xây dựng nền tảng học trực tuyến trên Google Cloud: Cloud Run phục vụ API, GKE chạy tác vụ nền, còn dữ liệu đơn hàng, tiến độ học tập và thanh toán cần được lưu bền vững. Nhóm có ba hướng: dùng **Cloud SQL**, dùng **AlloyDB for PostgreSQL**, hoặc tự vận hành hệ quản trị cơ sở dữ liệu trên **Compute Engine/GKE**. Cả ba đều có thể chạy SQL, nhưng khác nhau đáng kể về **động cơ cơ sở dữ liệu, mức kiểm soát, tính khả dụng, hiệu năng, chi phí và trách nhiệm vận hành**.

Trong chương **Cloud SQL và AlloyDB** của module **CLOUD_PROVIDERS_GCP**, bài học này đưa ra một quy trình ra quyết định thực tế, kết nối kiến thức project/IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ, giám sát độ tin cậy và ngân sách. Mục tiêu không phải chọn sản phẩm “mạnh nhất”, mà chọn giải pháp **đúng nhu cầu, đo được và vận hành được**.

**Sau bài học, bạn có thể:**

1. Phân biệt phạm vi quản lý và các engine được hỗ trợ của Cloud SQL, AlloyDB và self-managed database.
2. Đánh giá compatibility, workload OLTP/analytics, scaling, HA, backup, RPO/RTO, kết nối và quyền truy cập.
3. Xây dựng bảng quyết định dựa trên số liệu thay vì các tuyên bố hiệu năng chung.
4. Lập kế hoạch migration, benchmark và kiểm thử failover phù hợp với rủi ro dữ liệu.
5. Ước tính tổng chi phí sở hữu (TCO) gồm tài nguyên và công sức vận hành.
6. Đọc cấu hình bằng gcloud, thực hiện bài tập lựa chọn và giải thích trade-off trước kiến trúc sư.

## 1. Ba mô hình cung cấp cơ sở dữ liệu quan hệ

### 1.1. Cloud SQL: dịch vụ managed cho ba engine phổ biến

**Cloud SQL** là dịch vụ cơ sở dữ liệu quan hệ được Google Cloud quản lý cho **PostgreSQL, MySQL và Microsoft SQL Server**. Google quản lý nhiều công việc hạ tầng như cấp phát instance, bản vá nền tảng, cơ chế backup, replica, giám sát và failover theo cấu hình.

Điểm quan trọng:

- Ứng dụng vẫn giao tiếp qua giao thức/driver SQL quen thuộc của **engine được chọn**; chuyển từ MySQL sang PostgreSQL không phải chỉ đổi một flag Cloud SQL.
- Cloud SQL có **Enterprise** và **Enterprise Plus** với đặc tính hiệu năng, khả dụng, máy, storage và giá khác nhau tùy engine/phiên bản. Cần chỉ rõ edition trong bảng dự toán.
- Một instance mặc định có thể chỉ **zonal**; muốn khả năng chịu lỗi zone phải cấu hình **high availability (regional)** phù hợp.
- **Read replica** tăng năng lực đọc và phục vụ một số chiến lược DR, nhưng không tự trở thành automatic HA standby.
- Managed không đồng nghĩa không cần DBA: nhóm ứng dụng vẫn quản lý schema, indexes, query plans, connection pools, phân quyền dữ liệu và kiểm thử restore.

**Ví dụ:** sản phẩm dùng MySQL 8 với quy trình backup đơn giản và tải giao dịch vừa phải thường nên đánh giá Cloud SQL for MySQL trước, thay vì đổi toàn bộ application sang PostgreSQL chỉ để dùng một dịch vụ khác.

### 1.2. AlloyDB for PostgreSQL: managed PostgreSQL cho workload đòi hỏi cao

**AlloyDB for PostgreSQL** là dịch vụ **tương thích PostgreSQL**, được thiết kế cho workload giao dịch quan trọng, đọc nhiều và một số truy vấn phân tích kết hợp với OLTP. Khác với Cloud SQL, AlloyDB có kiến trúc **tách compute và distributed storage**, cung cấp primary instance và tùy chọn **read pool instances**.

- **Primary instance:** nhận ghi và có thể phục vụ đọc. Cấu hình HA thường dùng các node dự phòng ở hai zone trong một region với failover tự động.
- **Read pool instance:** nhóm một hoặc nhiều node phục vụ truy vấn **read-only**; dùng để mở rộng đọc hoặc tách tải truy vấn.
- **Columnar engine:** tăng tốc một số truy vấn scan/join/aggregate bằng lưu cột trong bộ nhớ; không phải mọi câu SQL đều hưởng lợi.
- **Backup/continuous backup, PITR và các lựa chọn replication/DR:** hỗ trợ bảo vệ dữ liệu nhưng cần bật/cấu hình, kiểm thử theo RPO/RTO.

AlloyDB **không phải managed MySQL hoặc SQL Server**. Dù tương thích PostgreSQL, không mặc nhiên hỗ trợ tất cả extensions, quyền superuser, hook hoặc cách vận hành của một bản PostgreSQL tự quản lý. Phải kiểm thử **driver, extension, SQL dialect, migration, replication và query behavior** với phiên bản đích.

**Ví dụ:** một hệ thống PostgreSQL có hàng nghìn giao dịch/giây và dashboard phân tích đọc nặng trên cùng dữ liệu có thể đánh giá AlloyDB primary + read pool + columnar engine, nhưng chỉ chọn sau benchmark đo **p95/p99, CPU, lock, I/O, lag và chi phí**.

### 1.3. Self-managed database: tự quản lý engine trên hạ tầng cloud

**Self-managed** nghĩa là doanh nghiệp tự cài và vận hành PostgreSQL/MySQL/SQL Server hoặc engine khác trên **Compute Engine VM**, hoặc chạy trong **GKE** với operator/StatefulSet và persistent volumes. Google quản lý lớp hạ tầng cloud theo dịch vụ IaaS/Kubernetes, còn đội vận hành chịu trách nhiệm lớn hơn đối với database.

Nhóm có thể kiểm soát phiên bản, thông số OS/engine, extensions, công cụ replication và mô hình failover. Đổi lại phải tự xử lý:

- Patch/upgrade OS và database; tương thích version, bảo trì không gián đoạn nếu cần.
- Primary/standby, fencing/leader election, quorum, failover, split-brain và load balancing kết nối.
- Backup/PITR, mã hóa, kiểm tra restore, cross-region DR và kiểm thử mất zone.
- Disk sizing/IOPS, filesystem, disk latency, capacity, monitoring, alerts, on-call và quy trình sự cố.
- Lỗ hổng bảo mật, audit, license, quyền truy cập và trách nhiệm tuân thủ.

**Tự quản lý trên GKE không tự trở thành HA**: ba Pod có thể cùng một zone; volume zonal có thể không mount được ở zone khác; operator có lỗi cấu hình; database replication vẫn cần bảo vệ dữ liệu và leader.

## 2. So sánh nhanh trước khi đi sâu

| Tiêu chí | Cloud SQL | AlloyDB for PostgreSQL | Tự quản lý trên VM/GKE |
| --- | --- | --- | --- |
| Engine chính | **PostgreSQL, MySQL, SQL Server** | **PostgreSQL-compatible** | Engine/version theo năng lực đội vận hành |
| Trách nhiệm hạ tầng DB | Phần lớn managed | Phần lớn managed | Người dùng chịu nhiều trách nhiệm |
| Quyền tùy chỉnh OS/engine | Có giới hạn | Có giới hạn | Rộng, tùy VM/operator và license |
| Đối tượng ưu tiên | App quan hệ phổ biến, ít gánh nặng ops | PostgreSQL có đòi hỏi hiệu năng và khả dụng cao | Phụ thuộc OS/extension/tooling, quy định hoặc topology đặc biệt |
| Mở rộng đọc | Read replicas (độ trễ replication) | Read pool nodes; routing đọc riêng | Replica tự thiết kế và vận hành |
| Khả dụng một zone | Cấu hình **regional HA** | HA primary theo cấu hình | Tự thiết kế replica, chuyển vai và volume |
| Phục hồi cả region | Cấu hình DR/cross-region theo hỗ trợ | Cấu hình secondary/DR theo hỗ trợ | Tự xây DR và vận hành |
| Backup/PITR | Managed features, phải bật/kiểm tra | Managed features, phải bật/kiểm tra | Tự thiết kế toàn bộ |
| Chi phí | Instance + storage + network + backup + license/edition nếu áp dụng | Compute primary/read pool + storage + backup + network | VM + disk + network + license + công DBA/on-call |
| Rủi ro chính | Hạn chế engine/config, connection và maintenance | Chi phí và mức tương thích PostgreSQL thực tế | Lỗi vận hành, patching, HA/DR và nhân sự |

**Không suy rằng:** Cloud SQL luôn chậm hơn AlloyDB; AlloyDB luôn rẻ hơn; hay tự quản lý luôn tiết kiệm. Những kết luận này phải xuất phát từ **benchmark cùng workload và tổng chi phí**, không từ tên sản phẩm.

### 2.1. Sơ đồ ba phương án cho một ứng dụng

~~~mermaid
flowchart TB
    APP["Cloud Run / GKE<br/>Orders API"] --> CHOICE{"Yêu cầu engine,<br/>quy mô, ops, RTO/RPO?"}
    CHOICE --> SQL["Cloud SQL<br/>MySQL / PostgreSQL / SQL Server"]
    CHOICE --> ALLOY["AlloyDB<br/>Primary + read pool nếu cần"]
    CHOICE --> SELF["Compute Engine / GKE<br/>Self-managed DB"]
    SQL --> CTRL["Kết nối an toàn, HA,<br/>backup, monitoring, cost"]
    ALLOY --> CTRL
    SELF --> CTRL
~~~

Trước khi so sánh hạ tầng, hãy xác nhận **dữ liệu quan hệ có thực sự là lựa chọn đúng**: với object/video nên dùng Cloud Storage; với dữ liệu phân tích rất lớn có thể cân nhắc BigQuery; với nhu cầu ghi quy mô toàn cầu và mô hình consistency khác có thể xem xét Spanner. Bài này chỉ so sánh **ba cách triển khai database quan hệ** theo chủ đề được giao.

## 3. Tiêu chí ra quyết định theo thứ tự ưu tiên

### 3.1. Bắt đầu từ engine và compatibility

Đây thường là **điều kiện loại trừ**, quan trọng hơn hiệu năng được quảng bá:

| Hiện trạng/đòi hỏi | Ứng viên nên thử trước | Việc bắt buộc xác minh |
| --- | --- | --- |
| App dùng **MySQL** và không muốn đổi SQL/driver | Cloud SQL for MySQL | Version, collation, stored procedures, replication và license phụ thuộc |
| App dùng **SQL Server**, T-SQL hoặc hệ sinh thái Microsoft | Cloud SQL for SQL Server | SQL Server edition/feature/agent/jobs, licensing và migration dependencies |
| App PostgreSQL thông dụng, tải vừa, muốn giảm DBA | Cloud SQL for PostgreSQL | Extensions, major version, connection limit, HA và backup |
| App PostgreSQL, cần throughput/đọc phức tạp cao | Cloud SQL Enterprise Plus **và** AlloyDB | Benchmark trên cùng dữ liệu; read pool, columnar benefit, TCO |
| Cần extension/OS-level agent hoặc quyền rất sâu không được managed hỗ trợ | Self-managed PostgreSQL/engine tương ứng | Khả năng vận hành HA/DR, vá lỗi, audit và chi phí nhân sự |
| Chỉ cần tránh vận hành VM nhưng chưa có số liệu tải | Cloud SQL làm baseline hợp lý | Không nâng cấp vội sang AlloyDB chỉ dựa trên giả định |

**Khả năng tương thích PostgreSQL** không đồng nghĩa *mỗi extension, superuser operation, hệ thống tệp, replication hook hay phiên bản đều được hỗ trợ*. Một đánh giá migration tối thiểu phải chạy **DDL, queries quan trọng, extension inventory và regression tests** trên đích thật.

### 3.2. Phân loại workload

| Dấu hiệu | Ý nghĩa | Hướng đánh giá |
| --- | --- | --- |
| OLTP nhỏ/vừa, transaction ngắn, ít truy vấn phức tạp | Công việc quản trị thường là rủi ro lớn hơn hạn chế engine | Ưu tiên benchmark Cloud SQL phù hợp |
| Write-heavy, lock contention hoặc hot rows | Có thể nghẽn ở schema/transaction, không chỉ CPU | Tối ưu SQL/index/partition trước khi tăng máy |
| Read-heavy với nhiều người dùng đồng thời | Có thể cần tách tải đọc | So Cloud SQL read replicas với AlloyDB read pool |
| SQL analytics scan/join/aggregate trên dữ liệu giao dịch | Query có thể tranh tài nguyên với OLTP | Thử AlloyDB columnar engine, read pool; cân nhắc BigQuery nếu là OLAP lớn |
| Bắt buộc root/OS tuning, plugin không hỗ trợ | Managed có giới hạn tính năng | Self-managed với runbook và staff đủ chuyên môn |
| Tài nguyên ngân sách rất nhỏ nhưng cần HA cao | Mâu thuẫn kinh tế/rủi ro | Tính chi phí HA, yêu cầu SLO và điều chỉnh kiến trúc |

**Thử nghiệm công bằng** phải đo cùng dataset, tỷ lệ đọc/ghi, độ đồng thời, transaction isolation, tỷ lệ cache hit, truy vấn p95/p99, checkpoint/vacuum và trạng thái replication. Không so benchmark một primary đang nhàn rỗi với một hệ thống tự quản lý đang chạy backup.

### 3.3. Đặt câu hỏi trước khi chọn dịch vụ

1. Có bắt buộc **MySQL, SQL Server hay PostgreSQL**? Những extensions/triggers/stored procedures nào không thể bỏ?
2. Số transaction/s, RPS, **p95/p99**, kích thước DB, tốc độ tăng trưởng và tỷ lệ đọc/ghi là bao nhiêu?
3. SLO, RTO, RPO đã được owner phê duyệt chưa? Có chấp nhận ngắt kết nối trong failover không?
4. Có cần **nhiều vùng** vì DR hoặc data residency, hay chỉ cần chịu lỗi một zone?
5. Số kết nối từ Cloud Run/GKE sẽ tăng thế nào khi autoscale? Có connection pool hợp lý không?
6. Nhóm có DBA trực/on-call, kiểm thử backup-restore và kỹ năng nâng cấp DB engine không?
7. Giá trị kinh tế của việc giảm công việc vận hành có lớn hơn phần compute/storage đắt hơn không?

## 4. High availability, read scaling và disaster recovery

### 4.1. Cloud SQL: zonal, regional HA và read replicas

Cloud SQL **zonal/standalone** là lựa chọn đơn giản, nhưng khi mất cả zone thường không có **automatic zonal failover**. Với **regional high availability**, Cloud SQL có primary và standby ở hai zone của cùng region; dữ liệu được sao chép đồng bộ theo cơ chế dịch vụ, và có automatic failover khi điều kiện cho phép.

**Ứng dụng vẫn có thể bị ngắt kết nối** trong lúc failover và phải reconnect/retry an toàn; HA không cam kết 0 giây downtime. Một query ghi đang dở cần được xử lý bằng transaction/idempotency thay vì retry vô điều kiện.

**Read replica** là bản sao phục vụ truy vấn đọc, thường có **replication lag**. Đừng dùng replica để đọc ngay một transaction vừa commit nếu nghiệp vụ yêu cầu đọc mới nhất mà chưa kiểm tra consistency. Đặc biệt, **read replica không tự thay cho HA standby** và không tự động nhận tất cả traffic ghi khi primary lỗi. Khi được dùng cho DR, cần quy trình promote, đổi routing, xác minh dữ liệu và chấp nhận RPO khác 0 theo thực tế.

### 4.2. AlloyDB: primary HA và read pool

AlloyDB có **cluster** trong region, **primary instance** và có thể thêm các **read pool instances**. Primary HA được thiết kế với redundant nodes ở nhiều zone; read pool có thể có một hay nhiều node để mở rộng đọc. Read pool **không nhận transaction ghi** của ứng dụng.

~~~mermaid
flowchart LR
    API["Cloud Run / GKE API"] -->|"Writes + consistent reads"| PRIMARY["AlloyDB primary<br/>HA trong region"]
    REPORT["Báo cáo / search API"] -->|"Read-only traffic"| POOL["Read pool<br/>nhiều node nếu cần"]
    PRIMARY <-. "Distributed storage / replication" .-> POOL
    POOL --> COL["Columnar engine<br/>nếu benchmark có lợi"]
~~~

Kiến trúc trên là **luồng logic**, không phải sơ đồ kết nối vật lý đầy đủ. Mở read pool **không tự chuyển** câu lệnh SELECT của ứng dụng sang endpoint đọc: phải cấu hình client routing/connection strings hoặc tính năng forwarding được hỗ trợ. Nếu truy vấn cần consistency ngay sau ghi, xem chính sách đọc primary, replica lag và transaction.

### 4.3. HA, backup, PITR và DR giải quyết bốn vấn đề khác nhau

| Cơ chế | Bảo vệ trước | Không bảo vệ chắc chắn |
| --- | --- | --- |
| **HA đa zone** | Hỏng VM/zone trong cùng region theo khả năng sản phẩm | Xóa nhầm bảng, ransomware, mất toàn region |
| **Read replica** | Tăng đọc, có thể tham gia kế hoạch DR | Thay thế automatic HA, đọc luôn đồng bộ tuyệt đối |
| **Backup** | Phục hồi dữ liệu từ bản lưu | Không tự giảm downtime tới 0; backup không test có thể không dùng được |
| **PITR** | Khôi phục tới thời điểm trước lỗi logic theo cửa sổ retention | Không phục hồi dữ liệu ngoài retention hoặc logs không còn |
| **Cross-region DR** | Mất region theo phương án replication/failover | Không đảm bảo zero-data-loss nếu bất đồng bộ, không có diễn tập |

**RTO** là thời gian khôi phục được chấp nhận; **RPO** là khoảng mất dữ liệu tối đa được chấp nhận. Chúng phải đo qua **restore/failover drill**, không suy trực tiếp từ tên “regional” hay từ một dòng quảng cáo SLA.

Ví dụ giao dịch học phí có RPO rất thấp cần cơ chế dữ liệu/consistency và đối soát phù hợp; có thể cần ngăn ghi trong giai đoạn failover thay vì chấp nhận hai primary cùng hoạt động.

### 4.4. Với self-managed, HA là một hệ thống cần vận hành

Tối thiểu phải thiết kế:

- Replication mode (đồng bộ/bất đồng bộ), lag, quorum/leader election, fencing để chống **split-brain**.
- Chuyển hướng kết nối (DNS, virtual IP, proxy hoặc service discovery), retry và xử lý transaction dở.
- Phân bố replica/disk across zones theo khả năng sản phẩm; **Persistent Disk zonal** không tự mount ở zone khác sau outage.
- Backup độc lập, retention, PITR, checksum/restore validation và quyền xóa backup có kiểm soát.
- Region DR, diễn tập failover/failback, người trực, monitoring và mục tiêu RTO/RPO có bằng chứng.

Chạy PostgreSQL primary trong một Pod kèm PVC và hai Pod replica không phải bằng chứng HA nếu chưa xác minh failover, dữ liệu và consistency.

## 5. Kết nối, IAM và bảo vệ dữ liệu

### 5.1. Thiết kế đường mạng trước khi tạo instance

Với Cloud SQL, cần chọn **private IP**, **public IP với kiểm soát phù hợp** hoặc **Private Service Connect** trong những cấu hình được hỗ trợ. Nếu dùng **Cloud SQL Auth Proxy** hay **Cloud SQL Language Connector**:

- Connector hỗ trợ xác thực theo IAM cho việc **kết nối tới instance** và tạo kênh được bảo vệ; **không tự thay thế** quyền database-level của PostgreSQL/MySQL/SQL Server.
- Để dùng **private IP**, client/proxy vẫn phải có **đường mạng tới VPC** chứa private endpoint; proxy không tự tạo VPN/VPC route.
- Không mở Auth Proxy trên `0.0.0.0` hoặc cổng công khai nếu không có thiết kế bảo vệ tương ứng; mặc định chỉ cần bind vào loopback/local socket.
- Cloud Run/GKE phải được cấp service identity, quyền connector và networking phù hợp; tránh lưu service account JSON key trong image.

Với AlloyDB, ứng dụng thường kết nối qua **private networking** và giao thức PostgreSQL; cấu hình networking/connector và quyền truy cập phù hợp với phiên bản sản phẩm. Với self-managed, đội vận hành phải tự thiết kế firewall, TLS, certificate rotation, service discovery và khả năng cách ly mạng.

### 5.2. Danh tính cloud khác danh tính database

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Google Cloud IAM** | Principal nào được tạo/quản lý instance hoặc dùng connector? | Service account của Cloud Run có quyền kết nối tới Cloud SQL. |
| **Database login/role** | Ứng dụng được SELECT/INSERT/UPDATE bảng nào? | Role `orders_app` chỉ truy cập schema giao dịch được cấp. |
| **Network access** | Đường IP/VPC/firewall có cho phép kết nối không? | GKE workload chạy trong subnet có route tới DB private IP. |
| **Application authorization** | Người học nào được đọc đơn hàng nào? | Backend kiểm tra `student_id`/tenant trước khi truy vấn. |

Một service account có quyền kết nối Cloud SQL **không mặc nhiên là PostgreSQL superuser**. Dùng IAM database authentication nếu engine/version hỗ trợ và đáp ứng nhu cầu, hoặc quản lý database credentials qua Secret Manager theo quy trình xoay vòng; không hardcode mật khẩu trong source và Kubernetes manifest công khai.

### 5.3. Checklist bảo mật vận hành

- Phân tách **dev/staging/prod** bằng danh tính và phạm vi dữ liệu; không tái dùng tài khoản DB quyền rộng.
- Dùng TLS và kênh kết nối an toàn; cấu hình **private connectivity** khi phù hợp residency/security policy.
- Áp dụng IAM tối thiểu, DB roles theo schema, audit logs/query logs có redaction; không ghi dữ liệu nhạy cảm hoặc password.
- Quản lý encryption at rest/KMS/CMEK **nếu tính năng và chính sách hỗ trợ**, cùng vòng đời khóa và khôi phục.
- Kiểm tra backup access, retention và bảo vệ khỏi xóa nhầm; backup nên độc lập với một tài khoản vận hành có quyền rộng.
- Có quy trình vulnerability patch, maintenance window, upgrade test và incident response.
- Giám sát connection count: autoscaling Cloud Run/GKE có thể tạo hàng trăm instance, mỗi instance mở nhiều connection làm DB hết slot.

## 6. Scaling, hiệu năng và connection management

### 6.1. Scale đọc khác scale ghi

**Tăng CPU/RAM** có thể giúp khi query thật sự CPU-bound, nhưng nhiều hệ thống nghẽn ở index, lock, I/O, connection hoặc transaction kéo dài. Read replica/read pool có thể giảm tải đọc, **không tự tăng write throughput** của primary trong mô hình một writer.

| Nút thắt | Bằng chứng cần xem | Hướng tối ưu |
| --- | --- | --- |
| CPU cao và query compute-bound | CPU utilization, query plan, p99 | Tối ưu SQL/index, sau đó thử machine sizing |
| Disk I/O và read latency | IOPS/throughput, cache hit, buffer miss | Index, query, storage tuning/class theo sản phẩm |
| Lock/contention | Lock wait, slow transactions, deadlock logs | Rút transaction, giảm hot rows, phân vùng workload |
| Quá nhiều connections | Active/idle connections, max connections, DB memory | Pooling, giới hạn concurrency, tối ưu idle timeouts |
| Đọc phân tích làm chậm ghi | Read-vs-write latency, large scans, pool utilization | Read replicas/pool, columnar engine hoặc tách analytics |
| Replica lag | Replication delay, stale reads, data consistency | Điều hướng truy vấn nhạy consistency về primary |

### 6.2. Ví dụ connection pool từ Cloud Run

Giả sử Cloud Run có thể scale tới **50 instances**, mỗi instance giữ pool tối đa **20 connections**:

\[
50 \times 20 = 1.000\ \text{connections tiềm năng}
\]

Trong khi DB chỉ đáp ứng ổn định khoảng **200 connections** cho workload thật, pool 20 mỗi instance là quá lớn. Cần **giảm pool**, dùng khả năng pooling/proxy được sản phẩm hỗ trợ, giới hạn scale/concurrency hoặc phân phối workload, rồi đo throughput. Không đơn giản tăng `max_connections` vì mỗi connection tiêu thụ bộ nhớ và có thể làm giảm hiệu năng.

**Độ trễ tổng** gồm thời gian chờ connection, query execution, network, serialization và retries. Benchmark p99 nên bao gồm **end-to-end request**, không chỉ thời gian SQL trên một kết nối có sẵn.

### 6.3. AlloyDB columnar engine không phải nút tăng tốc mọi query

Columnar engine hữu ích khi truy vấn phải đọc nhiều dòng, tổng hợp và join các cột được hỗ trợ. Với lookup đơn giản theo primary key, tác dụng có thể nhỏ hoặc không đáng kể. Việc bật/tắt và kích thước bộ nhớ column store cũng tiêu thụ tài nguyên; cần benchmark có **warm/cold cache, p95/p99 và tổng chi phí primary/read pool**.

Không đưa một dashboard phân tích rất lớn vào primary OLTP chỉ vì AlloyDB có columnar engine. Nếu pipeline cần BI/warehouse quy mô lớn, đánh giá phương án đẩy dữ liệu sang **BigQuery** để tách miền lỗi và chi phí xử lý.

## 7. Tổng chi phí sở hữu (TCO), không chỉ giá VM

### 7.1. Các hạng mục cần đưa vào bảng dự toán

| Hạng mục | Cloud SQL | AlloyDB | Self-managed |
| --- | --- | --- | --- |
| Compute | Machine/edition, primary, replica/HA | Primary + read pool instances | VM/GKE node và headroom |
| Storage | Disk, backup, logs, replication tùy cấu hình | Distributed storage, backups/logs | PD/Hyperdisk, snapshots, backup repository |
| Network | Egress, cross-region/zone theo bảng giá | Private networking, cross-region, ứng dụng | LB/proxy, replication, egress |
| License | SQL Server/edition nếu áp dụng | Theo giá dịch vụ | SQL Server/engine thương mại và hỗ trợ nếu áp dụng |
| DR | Replica vùng khác, backups, test restore | Secondary/replication, backup/restore | Cluster phụ, orchestration, replication tooling |
| Nhân sự | DBA cho schema, query, data ops | DBA và tuning nâng cao | DBA/SRE, patching, on-call, security |
| Rủi ro | Giới hạn managed, đổi engine | Compatibility, giá/perf không phù hợp | Downtime do lỗi vận hành và thiếu runbook |

**Công thức ước tính quản trị:**

\[
TCO = C_{\text{hạ tầng}} + C_{\text{dữ liệu/network}} +
C_{\text{nhân sự vận hành}} + C_{\text{DR/kiểm thử}} +
C_{\text{rủi ro gián đoạn}}
\]

Với tự quản lý, một VM rẻ hơn một dịch vụ managed không có nghĩa toàn bộ phương án rẻ hơn: phải cộng **replica, backup, patch, diễn tập DR, on-call, license và rủi ro downtime**. Với managed, ngược lại, luôn có công việc tối ưu query/backup/security của đội ứng dụng nên không thể coi chi phí vận hành bằng 0.

### 7.2. Ước tính theo ba mức tải

Đừng tính một cấu hình tại giờ nhàn rỗi rồi gọi đó là giá năm. Lập tối thiểu:

1. **Baseline:** kích thước DB, CPU/RAM, dung lượng và số kết nối ở tải thường.
2. **Peak:** số user/RPS, concurrent transactions, workload phân tích và tăng trưởng 12–24 tháng.
3. **Failure mode:** khi một zone/replica lỗi, hệ thống còn bao nhiêu capacity và tốn bao nhiêu tài nguyên dự phòng?

So sánh số liệu theo **cùng region, storage class, backup retention, HA/DR scope và mức hỗ trợ**. Pricing và edition có thể thay đổi; dùng **Google Cloud Pricing Calculator** và trang giá chính thức tại thời điểm ra quyết định.

## 8. Quy trình đánh giá và migration không dựa vào phỏng đoán

### 8.1. Bảy bước chọn database

1. **Kiểm kê:** engine/version, dữ liệu, bảng/index, extensions, stored procedures, jobs, kết nối hiện tại và tài nguyên phụ thuộc.
2. **Định lượng:** TPS/QPS, read/write ratio, p95/p99, peak concurrency, độ lớn DB, tăng trưởng, IOPS, replication lag và connection limits.
3. **Chốt yêu cầu:** availability SLO, RTO/RPO, residency, mã hóa, audit, ngân sách và kỹ năng đội vận hành.
4. **Loại trừ theo compatibility:** ví dụ SQL Server không thể chạy trực tiếp trên AlloyDB; một PostgreSQL extension không được hỗ trợ có thể buộc chọn khác.
5. **Lập shortlist:** Cloud SQL đúng engine/edition, AlloyDB khi là PostgreSQL có nhu cầu tương ứng, self-managed nếu cần kiểm soát sâu.
6. **Chạy proof of concept:** dùng dataset và query đại diện, đo performance **và** failover/restore, tổng chi phí.
7. **Ra quyết định có owner:** lưu lý do, trade-off, tiêu chí rollback và mốc đánh giá lại khi tải thay đổi.

Không dùng số TPS marketing của hai sản phẩm từ những benchmark khác điều kiện để kết luận ai nhanh hơn. Một phép thử đúng phải có **cùng quy mô dữ liệu và SLO**, kiểm tra cả trường hợp update/schema migration và mất kết nối.

### 8.2. Migration cần hai nhóm kiểm thử

| Kiểm thử kỹ thuật | Câu hỏi cần chứng minh |
| --- | --- |
| **Schema/data** | DDL, loại dữ liệu, encoding/collation, constraint, extension và stored procedure còn đúng không? |
| **Ứng dụng** | Driver, ORM, query semantics, transaction isolation, timezone và pagination có thay đổi không? |
| **Hiệu năng** | Query plans, index hit, throughput, p95/p99, database connections và storage I/O có đáp ứng peak? |
| **Độ tin cậy** | Failover/restore có đáp ứng RTO/RPO thật, app reconnect/retry có an toàn? |
| **Bảo mật** | IAM, DB roles, network, TLS, secrets, encryption, audit và residency có đạt yêu cầu? |
| **Vận hành** | Backups, PITR, alerting, database patching, rollback và người trực có sẵn? |

**Database Migration Service (DMS)** hỗ trợ những tuyến di chuyển cơ sở dữ liệu nhất định, bao gồm các nguồn PostgreSQL/MySQL/SQL Server phù hợp với đích được hỗ trợ. **Không suy mọi cặp engine/version hoặc extension đều được DMS hỗ trợ**; kiểm tra [danh sách source và destination chính thức](https://cloud.google.com/database-migration/docs/supported-databases) theo thời điểm migration.

Quy trình cutover có kiểm soát:

~~~mermaid
flowchart LR
    A["Inventory + compatibility tests"] --> B["Tạo DB đích<br/>với bảo mật/HA/backup"]
    B --> C["Load dữ liệu / replication<br/>theo tuyến hỗ trợ"]
    C --> D["So schema, row counts,<br/>checksum và lag"]
    D --> E["Chốt cửa sổ cutover,<br/>ngừng/điều phối writes"]
    E --> F["Chuyển connection<br/>và smoke test"]
    F --> G["Theo dõi SLO,<br/>sẵn kế hoạch rollback"]
~~~

Với migration có replication bất đồng bộ, **lag gần 0 không mặc định bằng 0**. Phải thiết kế thời điểm dừng ghi, đối soát transaction và quyết định khi nào chấp nhận cutover. Nếu đã cho phép ghi vào DB mới, rollback về DB cũ có thể yêu cầu **reverse replication hoặc reconciliation**, không chỉ sửa connection string.

## 9. Bài thực hành: lập inventory và quyết định có căn cứ

Lab này **không tạo database có tính phí**. Nếu project đã có Cloud SQL/AlloyDB và bạn được phân quyền đọc, dùng lệnh để khám phá cấu hình **không truy cập dữ liệu trong bảng**; nếu chưa có, dùng dữ liệu giả định ở phần bài tập. Không tự thử failover/restore hoặc tạo instance production trong bài này.

### 9.1. Gcloud chỉ đọc

~~~bash
# Chỉ dùng project, region và instance được chủ tài nguyên phê duyệt
export PROJECT_ID="YOUR_APPROVED_PROJECT"
export REGION="asia-southeast1"
export SQL_INSTANCE="YOUR_EXISTING_CLOUD_SQL_INSTANCE"
export ALLOY_CLUSTER="YOUR_EXISTING_ALLOYDB_CLUSTER"

gcloud config set project "$PROJECT_ID"
gcloud config get-value project

# Liệt kê và xem metadata Cloud SQL, không đọc nội dung database
gcloud sql instances list --project="$PROJECT_ID"
gcloud sql instances describe "$SQL_INSTANCE" \
  --project="$PROJECT_ID" \
  --format="yaml(name,databaseVersion,region,settings.edition,settings.availabilityType,settings.tier,settings.backupConfiguration,replicaNames)"

# Liệt kê AlloyDB cluster trong region
gcloud alloydb clusters list \
  --project="$PROJECT_ID" --region="$REGION"

# Chỉ chạy lệnh này nếu đúng cluster tồn tại và bạn có quyền xem
gcloud alloydb instances list \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --cluster="$ALLOY_CLUSTER"
~~~

Nếu một sản phẩm không có instance trong project, hoặc quyền liệt kê bị từ chối, **ghi nhận “chưa có dữ liệu/không có quyền”**, không coi là lý do tạo mới tài nguyên. Không xuất toàn bộ output có thông tin mạng hoặc cấu hình nhạy cảm vào báo cáo công khai.

### 9.2. Bảng inventory cần hoàn thành

| Trường | Cloud SQL hiện trạng | AlloyDB ứng viên | Self-managed ứng viên |
| --- | --- | --- | --- |
| Engine/version và extensions | Điền từ inventory | Kiểm tra tương thích | Có quyền kiểm soát đến mức nào? |
| Region/zone, network/TLS | Điền cấu hình hiện có | Thiết kế kết nối | Thiết kế VPC/firewall/proxy |
| HA và RTO/RPO | Zonal hay regional HA? | Primary HA + DR? | Replication/failover operator? |
| Backup/PITR, restore drill | Lịch và kết quả test | Lịch và kết quả test | Công cụ, lịch, người trực |
| CPU/RAM, TPS, p99 | Số liệu đo | Benchmark | Benchmark |
| Read scaling và consistency | Replica/lag | Read pool/lag | Replica và routing |
| IAM, DB roles, secrets | Xác minh | Xác minh | Xác minh |
| TCO 1 năm, tăng trưởng | Dự toán | Dự toán | VM + storage + SRE/DBA |
| Rủi ro hoặc blocker | Liệt kê | Liệt kê | Liệt kê |

### 9.3. Ví dụ SQL để hiểu tại sao phải benchmark

Trên một **database PostgreSQL lab** đã được cấp quyền và có bảng thử nghiệm, có thể đo **một SELECT** bằng `EXPLAIN (ANALYZE, BUFFERS)`:

~~~sql
-- CHỈ DÀNH CHO DB LAB: EXPLAIN ANALYZE thực sự thực thi query.
EXPLAIN (ANALYZE, BUFFERS)
SELECT student_id, COUNT(*) AS enrollments
FROM lab_enrollments
WHERE created_at >= TIMESTAMP '2026-01-01 00:00:00'
GROUP BY student_id;
~~~

Đây là **mẫu query**, cần có bảng `lab_enrollments` riêng; không chạy trên bảng lớn production mà chưa có đánh giá ảnh hưởng. So với câu query chỉ đọc dữ liệu nhỏ theo khóa chính, truy vấn `GROUP BY` có thể dùng nhiều CPU/buffer/I/O và hưởng lợi khác nhau từ index, cache, read pool hoặc columnar engine.

**Phải đo workload toàn diện**: một query nhanh hơn không chứng minh DB có throughput giao dịch tốt hơn, RTO thấp hơn hoặc TCO rẻ hơn.

## 10. Bài tập tình huống: chọn giải pháp theo yêu cầu

### A — Ứng dụng MySQL cho trung tâm đào tạo

Hiện trạng: ứng dụng dùng **MySQL**, khoảng 80 GiB dữ liệu, dưới 500 TPS vào peak, không dùng engine features đặc biệt; đội có hai lập trình viên nhưng không có DBA trực 24/7. Khách hàng muốn chịu lỗi một zone và restore được sau khi xóa nhầm dữ liệu.

**Yêu cầu:** chọn một trong ba giải pháp, liệt kê tính năng cần bật và ít nhất ba phép kiểm thử.

**Định hướng:** Cloud SQL for MySQL thường là ứng viên đầu tiên. Đánh giá **regional HA**, automated backups/PITR, private connectivity, connection pools và alerting. Diễn tập **reconnect sau failover**, **restore/PITR trên môi trường tách biệt**, và **load test peak**. Không chọn AlloyDB vì AlloyDB không phải MySQL; tự quản lý đòi khả năng DBA/DR mà nhóm chưa có.

### B — PostgreSQL có dashboard đọc rất nặng

Hiện trạng: 1,5 TiB dữ liệu PostgreSQL, API OLTP ổn định nhưng các truy vấn scan/aggregate đồng thời làm p99 tăng; tổ chức có ngân sách cải thiện và đội có thể thực hiện benchmark, kiểm thử cutover.

**Yêu cầu:** có nên chuyển ngay sang AlloyDB không?

**Định hướng:** **chưa thể kết luận ngay**. Trước hết đọc query plans/index/locks, thử tối ưu và **Cloud SQL Enterprise Plus/read replicas** nếu phù hợp. Song song, benchmark **AlloyDB primary + read pool**, bật columnar engine có kiểm soát cho query đại diện. Đo p99 OLTP, p99 analytics, replication freshness, chi phí compute/read pool, effort migration và khả năng rollback. Chỉ chuyển khi bằng chứng đáp ứng SLO/TCO.

### C — PostgreSQL cần extension đặc thù và quyền OS

Hiện trạng: phần mềm xử lý ảnh y khoa phụ thuộc PostgreSQL extension tự biên dịch và OS library riêng, extension này **chưa được xác minh hỗ trợ** trên các dịch vụ managed; dữ liệu có quy định residency và audit nghiêm ngặt.

**Yêu cầu:** quyết định sơ bộ và điều kiện để duyệt.

**Định hướng:** ưu tiên kiểm tra khả năng thay/đóng gói extension hoặc khả năng hỗ trợ chính thức trên Cloud SQL/AlloyDB. Nếu yêu cầu không thể đáp ứng, **self-managed trên VM hoặc GKE** là ứng viên kỹ thuật, nhưng chỉ được chọn khi có DBA/SRE, HA/backup/restore, patching, phân quyền, audit, network, legal/compliance review và DR drill. **Không** dùng dữ liệu thật để PoC khi chưa được phép.

### D — Sản phẩm yêu cầu RPO = 0 cả khi mất region

Yêu cầu kinh doanh: mất toàn region cũng không được mất một transaction đã báo commit; hệ thống phải tiếp tục ghi tại một region khác.

**Câu hỏi:** chọn Cloud SQL regional HA, AlloyDB HA primary hay self-managed 2-zone là đủ chưa?

**Đáp án:** **chưa đủ**. Các cơ chế nêu trên chủ yếu bảo vệ trong region, còn replication cross-region có thể bất đồng bộ và có RPO khác 0. Cần làm rõ độ mạnh của cam kết, phương án nhất quán dữ liệu across regions, synchronous/quorum nếu được hỗ trợ, ảnh hưởng latency/chi phí và tính khả thi. Có thể phải **xem xét lại dịch vụ hoặc thiết kế dữ liệu** ngoài ba lựa chọn của bài, thay vì hứa RPO=0 không có cơ sở.

### E — Ba API Cloud Run làm Cloud SQL quá nhiều kết nối

Ba service cùng kết nối một Cloud SQL PostgreSQL. Mỗi service scale tối đa 40 instances, mỗi instance giữ pool 15 connections. DB được đo chỉ vận hành an toàn với khoảng 300 connections tổng.

**Bài tính:**

\[
3 \times 40 \times 15 = 1.800\ \text{connections tiềm năng}
\]

**Yêu cầu:** nêu hướng xử lý ít rủi ro.

**Định hướng:** giảm pool theo workload, thiết kế giới hạn concurrency/scale, pooling hoặc connection management phù hợp, kiểm tra idle connections và profile SQL. Đo lại peak. Không đơn giản tăng `max_connections` lên 1.800 hoặc chuyển AlloyDB rồi giả định vấn đề biến mất.

### Mẫu bảng ra quyết định có thể điền

| Tiêu chí | Trọng số do tổ chức chọn | Cloud SQL | AlloyDB | Self-managed |
| --- | --- | --- | --- | --- |
| Engine và compatibility | Bắt buộc / loại trừ | Pass/Fail | Pass/Fail | Pass/Fail |
| RTO/RPO và HA/DR | Cao | Bằng chứng test | Bằng chứng test | Bằng chứng test |
| p99 và throughput theo workload | Cao | Benchmark | Benchmark | Benchmark |
| Quản trị và bảo mật | Cao | Review | Review | Review |
| TCO 1–3 năm | Theo ngân sách | Dự toán | Dự toán | Dự toán |
| Kỹ năng nhân sự/on-call | Theo tổ chức | Đủ/Thiếu | Đủ/Thiếu | Đủ/Thiếu |
| Migration và khả năng rollback | Theo mức rủi ro | Kế hoạch | Kế hoạch | Kế hoạch |

**Không cho điểm một ứng viên đã Fail điều kiện bắt buộc** chỉ vì giá rẻ hoặc benchmark tốt. Nếu tất cả chưa đạt RTO/RPO, kết quả đúng là **chưa có lựa chọn đạt yêu cầu**.

## 11. Câu hỏi tự kiểm tra

**1. Cloud SQL hỗ trợ những engine nào?**  
PostgreSQL, MySQL và Microsoft SQL Server; tính năng/edition/phiên bản hỗ trợ thay đổi theo engine.

**2. AlloyDB có chạy trực tiếp ứng dụng SQL Server mà không đổi engine không?**  
Không; AlloyDB là dịch vụ tương thích PostgreSQL.

**3. Cloud SQL read replica có tự thay thế primary khi zone lỗi không?**  
Không tự động như HA standby; primary cần regional HA hoặc kế hoạch DR/promote thích hợp.

**4. AlloyDB read pool có nhận ghi như primary không?**  
Không; read pool phục vụ truy vấn đọc, ứng dụng phải điều hướng kết nối đúng.

**5. Chọn Cloud SQL regional HA có đồng nghĩa có DR khi mất cả region không?**  
Không; vẫn cần kế hoạch cross-region, backup, phục hồi và kiểm thử.

**6. Cloud SQL Auth Proxy có tạo đường mạng private IP cho client không?**  
Không; client vẫn cần kết nối mạng thích hợp tới VPC/private endpoint.

**7. Managed database có miễn quản trị query và schema không?**  
Không; lập trình viên/DBA vẫn quản lý schema, index, transactions, pool, roles và data integrity.

**8. Tại sao backup phải được thử restore?**  
Vì backup tồn tại không chứng minh có thể khôi phục đúng dữ liệu trong RTO/RPO đã cam kết.

**9. Vì sao không chỉ so giá VM với giá AlloyDB?**  
Vì TCO còn gồm HA/replica, backup, license, operations, on-call, downtime risk và network.

**10. Khi PostgreSQL cần một extension không được hỗ trợ, nên làm gì?**  
Kiểm tra phương án thay thế/migration trước; nếu cần self-managed phải chứng minh đủ năng lực quản trị và bảo mật.

**11. Ba Pod database trên GKE có tự bảo đảm tính nhất quán/HA không?**  
Không; cần replication, leader election, fencing, storage topology và runbook được kiểm thử.

**12. Đọc dữ liệu ngay sau ghi trên read replica có chắc thấy dữ liệu mới nhất không?**  
Không; replica lag có thể gây stale reads, cần thiết kế read consistency phù hợp.

## 12. Tài liệu Google Cloud tham khảo

- [Cloud SQL overview](https://cloud.google.com/sql/docs/introduction) — hỗ trợ engine, thành phần managed và lựa chọn triển khai.
- [Cloud SQL PostgreSQL — Choose an edition](https://cloud.google.com/sql/docs/postgres/choose-edition) — so sánh Enterprise/Enterprise Plus, giá trị mặc định và tính năng.
- [Cloud SQL MySQL — Choose an edition](https://cloud.google.com/sql/docs/mysql/choose-edition) — lựa chọn edition theo version/tải.
- [Cloud SQL SQL Server — Choose an edition](https://cloud.google.com/sql/docs/sqlserver/choose-edition) — edition, SQL Server version và các giới hạn.
- [Cloud SQL high availability](https://cloud.google.com/sql/docs/postgres/high-availability) — zonal, regional, failover, downtime và read replicas.
- [Cloud SQL read replicas](https://cloud.google.com/sql/docs/postgres/replication) — read scaling, lag và hạn chế automatic failover.
- [Cloud SQL disaster recovery](https://cloud.google.com/sql/docs/postgres/intro-to-cloud-sql-disaster-recovery) — khôi phục sau sự cố toàn region.
- [Cloud SQL connection options](https://cloud.google.com/sql/docs/postgres/connection-options) — public/private IP, connector và database authentication.
- [Cloud SQL Auth Proxy](https://cloud.google.com/sql/docs/postgres/connect-auth-proxy) — secure channel và yêu cầu có network path khi dùng private IP.
- [AlloyDB overview](https://cloud.google.com/alloydb/docs/overview) — compute/storage tách rời, primary, read pools và HA.
- [AlloyDB columnar engine](https://cloud.google.com/alloydb/docs/columnar-engine/about) — tăng tốc một số query analytics.
- [AlloyDB sizing recommendations](https://cloud.google.com/alloydb/docs/use-sizing-recommendations) — chọn primary/read pool và benchmark.
- [Database Migration Service — Supported databases](https://cloud.google.com/database-migration/docs/supported-databases) — xác minh tuyến migration/engine/version hỗ trợ.
- [Cloud SQL pricing](https://cloud.google.com/sql/pricing), [AlloyDB pricing](https://cloud.google.com/alloydb/pricing), [Compute Engine pricing](https://cloud.google.com/compute/all-pricing) — lập TCO ở thời điểm ra quyết định.

**Kết luận:** chọn **Cloud SQL** khi cần engine quan hệ phổ biến và giảm công việc hạ tầng; đánh giá **AlloyDB** khi đã dùng PostgreSQL và có yêu cầu hiệu năng/khả dụng xứng đáng với benchmark cùng chi phí; chọn **self-managed** khi managed không đáp ứng ràng buộc kỹ thuật hoặc quyền kiểm soát, và đội ngũ thực sự có năng lực vận hành. Quyết định chỉ hoàn chỉnh khi đã có **compatibility evidence, SLO/RTO/RPO, bài test phục hồi, kế hoạch bảo mật/migration và dự toán TCO** — không chỉ tên sản phẩm.
