# Database Migration Service và đồng bộ cơ sở dữ liệu

Di chuyển ứng dụng lên Google Cloud thường dễ hơn di chuyển dữ liệu đang được ghi liên tục. Một API Java có thể được đóng gói và triển khai lại trong vài phút, nhưng cơ sở dữ liệu chứa hàng trăm gigabyte hoặc nhiều terabyte phải được chuyển với tính toàn vẹn, khả năng phục hồi và thời gian gián đoạn đáp ứng yêu cầu nghiệp vụ. Nếu chỉ copy một bản dump rồi đổi JDBC URL, dữ liệu phát sinh sau thời điểm dump có thể bị mất.

**Database Migration Service (DMS)** của Google Cloud giúp điều phối quá trình di chuyển database đến các đích được hỗ trợ như Cloud SQL và AlloyDB for PostgreSQL. Tùy cặp nguồn–đích, dịch vụ có thể thực hiện **one-time migration** hoặc **continuous migration**: tải dữ liệu ban đầu rồi theo dõi và sao chép những thay đổi tiếp theo qua cơ chế Change Data Capture (CDC). Khi đích bắt kịp nguồn, đội vận hành tiến hành **cutover** và đưa ứng dụng kết nối đến database mới.

Bài học thuộc chương **Di chuyển lên Google Cloud** của module **CLOUD_PROVIDERS_GCP**. Module hướng dẫn lựa chọn và vận hành các dịch vụ từ project, IAM, VPC, Compute Engine, GKE, Cloud Run đến lưu trữ và cơ sở dữ liệu, kết hợp bảo mật, tự động hóa, độ tin cậy và chi phí. Nội dung này tập trung vào việc chọn luồng di chuyển dữ liệu, hiểu cơ chế đồng bộ, chuẩn bị PostgreSQL/MySQL, kiểm chứng và chuyển đổi an toàn cho ứng dụng Java/Spring.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích DMS, migration job, connection profile, initial load, CDC và promote/cutover.
- Phân biệt one-time, continuous, homogeneous và heterogeneous database migration.
- Kiểm tra cặp database source–destination, phiên bản, tính năng và giới hạn được hỗ trợ.
- Xác định yêu cầu kết nối mạng, xác thực, quyền truy cập và cấu hình replication.
- Chuẩn bị nguồn PostgreSQL hoặc MySQL cho continuous migration theo kịch bản phù hợp.
- Tạo, kiểm thử, theo dõi và quản lý migration job trong Google Cloud Console.
- Đánh giá replication lag và đối soát dữ liệu trước khi chuyển traffic.
- Thực hiện runbook cutover, xác nhận ứng dụng Java và xây phương án rollback.
- Nhận biết những rủi ro về schema, DDL, identity, sequences, dữ liệu nhạy cảm và chi phí.

## 1. Database Migration Service giải quyết vấn đề gì?

DMS là dịch vụ có quản lý giúp chuyển dữ liệu từ một cơ sở dữ liệu nguồn sang hệ quản trị database đích trên Google Cloud. DMS đơn giản hóa quy trình thiết lập kết nối, điều phối initial snapshot/load, sao chép thay đổi và theo dõi trạng thái migration.

Ví dụ, công ty có PostgreSQL chạy trên VM trong data center và muốn chuyển sang Cloud SQL for PostgreSQL. Nếu database đang phục vụ nhiều ứng dụng, một bản backup khôi phục tại thời điểm T0 sẽ thiếu các giao dịch tạo sau T0. Continuous migration dùng nguồn thông tin thay đổi của database để đưa dữ liệu phát sinh sau snapshot sang đích, từ đó thu hẹp khoảng thời gian cần dừng ghi tại cutover.

DMS **không thay thế** các công việc sau:

- Khảo sát database source và những ứng dụng đang đọc/ghi.
- Kiểm tra version, extension, stored procedure, schema và application compatibility.
- Tạo hoặc cấu hình quyền truy cập mạng cho các thành phần liên quan.
- Xác nhận RTO, RPO, downtime window và backup/restore strategy.
- Đối soát dữ liệu, chạy integration tests, đánh giá query performance.
- Lập quy trình rollback sau khi application bắt đầu ghi vào database đích.

Trong continuous migration, DMS duy trì luồng dữ liệu **nguồn → đích** để phục vụ chuyển đổi. Dịch vụ **không cung cấp mô hình dual-write hai chiều** để ứng dụng đồng thời ghi vào cả nguồn và đích. Sau cutover, muốn quay lại nguồn cũ phải có kế hoạch riêng; không giả định DMS sẽ tự sao chép ngược các giao dịch mới.

## 2. Bốn khái niệm dễ nhầm

### One-time migration

One-time migration thực hiện snapshot/dump rồi load dữ liệu vào đích một lần. Không có luồng CDC tiếp tục cập nhật. Để không mất dữ liệu trong quá trình copy, thường phải chặn phát sinh giao dịch mới ở nguồn từ thời điểm nhất quán cho đến lúc chuyển ứng dụng.

Ưu điểm: đơn giản, phù hợp database nhỏ hoặc hệ thống có maintenance window dài.

Hạn chế: downtime có thể tăng theo kích thước dữ liệu, tốc độ mạng và thời gian kiểm chứng.

### Continuous migration

Continuous migration bắt đầu bằng **initial dump/load** rồi áp dụng các thay đổi được ghi lại tại nguồn. Mục tiêu là duy trì đích gần đồng bộ trong khi nguồn vẫn phục vụ sản xuất.

Ưu điểm: thời gian dừng ghi cuối cùng có thể ngắn hơn nhiều so với toàn bộ thời gian chuyển dữ liệu.

Hạn chế: cần log/replication tại nguồn, network ổn định, đủ capacity và theo dõi lag. Trong lúc migrate, việc ghi hoặc thay đổi schema không phù hợp ở đích có thể gây xung đột và hỏng tiến trình đồng bộ.

### Homogeneous migration

Cặp nguồn và đích cùng hệ quản trị database hoặc cùng họ tương thích được DMS hỗ trợ, ví dụ MySQL → Cloud SQL for MySQL hoặc PostgreSQL → Cloud SQL for PostgreSQL. Chuyển cùng engine không có nghĩa mọi phiên bản, extension, flag và tính năng đều tương thích.

### Heterogeneous migration

Cặp nguồn và đích khác công nghệ, ví dụ Oracle → Cloud SQL for PostgreSQL hoặc SQL Server → AlloyDB for PostgreSQL. Ngoài việc chuyển dữ liệu, cần chuyển đổi schema, kiểu dữ liệu, stored procedure, SQL dialect và logic của ứng dụng. DMS có conversion workspace cho các kịch bản được hỗ trợ; kết quả vẫn cần review và kiểm thử nghiệp vụ.

| Khía cạnh | One-time | Continuous |
|---|---|---|
| Dữ liệu ban đầu | Snapshot/dump rồi load | Snapshot/dump rồi load |
| Thay đổi sau snapshot | Không tự sao chép tiếp | CDC/replication theo luồng được hỗ trợ |
| Downtime | Thường bao trùm giai đoạn chuyển và kiểm chứng | Tập trung ở bước chặn ghi, bắt kịp và cutover |
| Độ phức tạp | Thấp hơn | Cao hơn: log retention, CDC, lag, promotion |
| Kiểu ứng dụng phù hợp | Batch hoặc dữ liệu có thể ngừng ghi lâu | OLTP và hệ thống cần hạn chế gián đoạn |

**Tính liên tục không đồng nghĩa downtime bằng 0.** Khi chuyển writer cuối cùng sang database đích, vẫn cần khoảng thời gian khóa ghi, chờ đuổi kịp, promote và đổi cấu hình ứng dụng.

## 3. Các nguồn và đích được hỗ trợ

Các kịch bản DMS được công bố trong tài liệu hiện hành gồm:

| Kiểu | Nguồn | Đích ví dụ |
|---|---|---|
| Homogeneous | MySQL tương thích | Cloud SQL for MySQL |
| Homogeneous | PostgreSQL tương thích | Cloud SQL for PostgreSQL |
| Homogeneous | PostgreSQL tương thích | AlloyDB for PostgreSQL |
| Homogeneous | SQL Server tương thích | Cloud SQL for SQL Server |
| Heterogeneous | Oracle | Cloud SQL for PostgreSQL hoặc AlloyDB for PostgreSQL |
| Heterogeneous | SQL Server | Cloud SQL for PostgreSQL hoặc AlloyDB for PostgreSQL |

Nguồn có thể nằm on-premises, trên VM ở cloud khác hoặc dịch vụ database có quản lý được DMS hỗ trợ. **Cụ thể loại nguồn, phiên bản, edition, topology, network và tính năng** phụ thuộc từng migration scenario. Trước khi thiết kế, đối chiếu trang **Supported source and destination databases** và **Known limitations** của scenario, thay vì coi bảng trên là cam kết mọi phiên bản đều chạy được.

Một số phương án có tính năng Pre-GA, phương thức kết nối khác hoặc giới hạn riêng. Đối với database không nằm trong danh sách, cần đánh giá công cụ khác như native backup/restore, công cụ vendor, data replication pipeline hoặc dịch vụ migration phù hợp; không cố đưa vào DMS khi không hỗ trợ.

### Ví dụ quyết định công cụ

- PostgreSQL tự quản lý → Cloud SQL for PostgreSQL: đánh giá DMS continuous migration và giới hạn replication.
- MySQL trên VM → Cloud SQL for MySQL: đánh giá binlog-based CDC.
- Oracle → PostgreSQL: đánh giá schema/code conversion trước khi chạy migration.
- MongoDB hoặc hệ quản trị không nằm trong scenario hỗ trợ: khảo sát phương án khác và yêu cầu nhất quán.
- Nhu cầu đồng bộ hai chiều dài hạn: thiết kế kiến trúc replication chuyên biệt; **không dùng DMS như một active-active replication service**.

## 4. Kiến trúc DMS và luồng đồng bộ

Một continuous migration thường gồm:

1. **Source database:** database đang phục vụ giao dịch.
2. **Connection profile:** thông tin kết nối nguồn, endpoint, loại engine, authentication và bảo mật.
3. **Connectivity method:** đường mạng để thành phần migration và đích truy cập được nguồn.
4. **Migration job:** tài nguyên điều phối quá trình snapshot, load và CDC.
5. **Destination database:** Cloud SQL hoặc AlloyDB được chuẩn bị theo scenario.
6. **Metrics/logs:** trạng thái job, log, lỗi và độ trễ replication để quyết định cutover.

~~~mermaid
flowchart LR
  A[Java/Spring API đang ghi nguồn] --> B[(Source DB)]
  B --> C[Initial dump / snapshot]
  B --> D[Change logs: binlog / WAL / CDC]
  C --> E[Database Migration Service job]
  D --> E
  E --> F[(Cloud SQL / AlloyDB destination)]
  E --> G[Migration job metrics và logs]
  F --> H[Validation: schema, rows, queries]
  G --> I{Lag gần bằng 0?}
  H --> I
  I -->|Chưa| J[Tiếp tục đồng bộ]
  I -->|Đủ điều kiện| K[Dừng source writes và promote]
  K --> L[Java/Spring API chuyển sang đích]
~~~

Sơ đồ khái quát logic. Tùy engine và scenario, DMS điều phối kết nối giữa database đích và database nguồn theo đường mạng được cấu hình; không phải lúc nào mọi byte dữ liệu cũng đi qua một proxy DMS duy nhất.

### Trạng thái các giai đoạn

| Giai đoạn | Mô tả | Điều cần theo dõi |
|---|---|---|
| Job validation | Kiểm tra cấu hình, endpoint, quyền và mạng | Test job thành công |
| Initial load | Copy dữ liệu lịch sử theo snapshot/dump | Throughput, disk capacity, lỗi import |
| CDC / replication | Áp dụng thay đổi mới | Replication delay/lag, log retention, backlog |
| Cutover preparation | Kiểm chứng và chuẩn bị đóng nguồn ghi | Row counts, dữ liệu, app readiness |
| Promotion | Dừng luồng replication và đưa đích thành primary độc lập | Promote thành công, source writes đã dừng |
| Post-cutover | Ứng dụng chuyển endpoint, theo dõi và backup | Error rate, latency, data integrity |

Tên state chi tiết trên Console/API có thể thay đổi theo engine. Hãy dùng trạng thái thực tế của job và hướng dẫn từng kịch bản để điều hành.

## 5. Preflight: khảo sát database và workload liên quan

Trước khi tạo migration job, nhóm DBA và application owner cần thống nhất:

| Hạng mục | Câu hỏi cần trả lời |
|---|---|
| Source | Engine, version, edition, hosting, topology, HA, replica |
| Destination | Engine/version, region, CPU/RAM, storage, HA, network |
| Data | Dung lượng, số DB/schema, tables, large objects, tăng trưởng |
| Workload | TPS/QPS, connections, transaction duration, peak time |
| Schema | Extension, trigger, function, stored procedure, collation, sequence |
| Security | TLS, encryption, account privileges, secret rotation, audit |
| Dependencies | Ứng dụng đọc/ghi, ETL/BI, reporting, batch, CDC consumer |
| Recovery | Backup, PITR, RTO/RPO, snapshot khôi phục, DR |
| Cutover | Thời gian chặn ghi, DNS/JDBC URL, credential, rollback |
| Validation | Row counts, checksum, chức năng, query latency |
| Ownership | DBA, app, network, security, business owner, on-call |

**Không được dùng một database làm đích chỉ vì tên giống engine nguồn.** Ví dụ PostgreSQL extensions hoặc Oracle stored procedures có thể không được hỗ trợ tương đương trên hệ thống đích. Khi chuyển SQL Server/Oracle sang PostgreSQL, cần đánh giá cả SQL trong Java code, ORM mappings và batch scripts.

### Tạo bảng bằng chứng

~~~csv
item,source,destination,check,owner,status
orders-db,postgresql-self-managed,cloud-sql-postgresql,version-and-extensions,dba,pending
orders-db,postgresql-self-managed,cloud-sql-postgresql,wal-and-replication,dba,pending
orders-db,postgresql-self-managed,cloud-sql-postgresql,network-and-tls,network,pending
orders-api,spring-boot,cloud-run,jdbc-and-pooling,app-team,pending
orders-db,postgresql-self-managed,cloud-sql-postgresql,cutover-and-rollback,sre,pending
~~~

Đây là checklist ví dụ; thông tin nhạy cảm như hostname nội bộ, mật khẩu và dữ liệu khách hàng phải lưu riêng trong hệ thống được bảo vệ.

## 6. Chuẩn bị nguồn MySQL cho continuous migration

DMS dùng dữ liệu thay đổi từ **binary log (binlog)** trong nhiều kịch bản MySQL. Muốn nguồn tiếp tục phục vụ giao dịch khi chạy migration, cần đảm bảo binlog và retention phù hợp.

### Kiểm tra cấu hình đọc-only

Trên MySQL nguồn được phép quản trị:

~~~sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW VARIABLES LIKE 'server_id';
SHOW VARIABLES LIKE 'gtid_mode';
~~~

Các kiểm tra quan trọng:

- Binary logging phải được bật theo yêu cầu scenario.
- `binlog_format` cần `ROW` khi DMS yêu cầu row-based binlog.
- Retention phải đủ dài để DMS bắt kịp nếu mạng chậm hoặc job tạm gián đoạn.
- `server_id` cần được cấu hình hợp lệ.
- `GTID_MODE` phải nằm trong các trạng thái được scenario hỗ trợ; một số trường hợp đích có read replica hoặc dump thủ công cần GTID ON.
- Tài khoản migration có quyền snapshot/replication đúng danh sách chính thức cho nguồn đang dùng.

**Không** copy lệnh cấu hình hoặc GRANT từ hệ thống khác mà không xem phiên bản MySQL, mô hình managed/on-premises và yêu cầu cụ thể. Với Cloud SQL for MySQL nguồn, binlog liên quan đến PITR và database flags; với Amazon RDS/Aurora, retention và privilege được kiểm soát khác với MySQL tự quản lý.

### Rủi ro binlog retention

Nếu quá trình initial load kéo dài hoặc CDC lag nhiều giờ, nguồn có thể xoay vòng/xóa binlog trước khi DMS đọc kịp. Điều này có thể làm job thất bại hoặc phải khởi động lại quá trình migration. Vì vậy:

1. Ước lượng tốc độ ghi và khoảng thời gian copy dữ liệu.
2. Đặt retention đủ cho peak, outage và recovery.
3. Theo dõi dung lượng log trên nguồn.
4. Giảm tải ở thời điểm cao điểm khi phù hợp.
5. Thử phương án phục hồi nếu DMS mất vị trí CDC.

### Quyền migration

Tạo một danh tính **riêng cho migration**, giới hạn quyền theo tài liệu DMS và xóa/thu hồi sau khi hoàn tất. Đừng dùng tài khoản root của ứng dụng hoặc đưa password vào command history; lưu secret bằng công cụ bảo vệ phù hợp. Các đặc quyền chính xác phụ thuộc phương thức snapshot, binlog và database provider.

## 7. Chuẩn bị nguồn PostgreSQL cho continuous migration

Với nhiều luồng PostgreSQL homogeneous migration, DMS sử dụng **Write-Ahead Log (WAL)** và logical replication để truyền các thay đổi. Một số kịch bản sử dụng extension `pglogical`, trong khi những phương thức mới có thể dùng native PostgreSQL logical replication. Kiểm tra đúng tài liệu scenario và phiên bản, tránh áp đặt một công thức cho mọi trường hợp.

### Kiểm tra cấu hình nguồn

Ví dụ SQL đọc cấu hình:

~~~sql
SHOW server_version;
SHOW wal_level;
SHOW max_wal_senders;
SHOW max_replication_slots;
SHOW max_worker_processes;

SELECT extname, extversion
FROM pg_extension
ORDER BY extname;
~~~

Điểm cần đánh giá:

- Logical replication đã được bật và server có cấu hình phù hợp.
- Số replication slots và WAL senders đủ cho migration job, table sync và consumer khác.
- Tài khoản migration có quyền replication và quyền đọc schema/table theo hướng dẫn.
- Extension và kiểu dữ liệu của nguồn được đích hỗ trợ.
- Replication slot/WAL retention không tăng vô hạn khi destination chậm.
- Có đủ disk cho WAL, nhất là khi initial load lớn hoặc mạng gián đoạn.

Nếu dùng Amazon RDS PostgreSQL, cần kiểm tra tham số như `rds.logical_replication` và các yêu cầu về slot, worker, timeout theo tài liệu DMS. Với self-managed PostgreSQL, việc chỉnh cấu hình có thể yêu cầu reload hoặc restart; phải lập change request vì ảnh hưởng production.

### Thông tin replication và lag

SQL tham khảo để xem replication slots trên nguồn PostgreSQL:

~~~sql
SELECT slot_name, plugin, slot_type, active,
       restart_lsn, confirmed_flush_lsn
FROM pg_replication_slots;
~~~

Các cột và ý nghĩa chi tiết có thể khác theo version/slot type. Không xóa replication slot đang được DMS hoặc consumer khác sử dụng chỉ vì thấy giữ WAL lâu; cần xác định owner và trạng thái job.

### Các đối tượng cần xác minh sau migration

Với PostgreSQL, cần kiểm tra:

- Extensions, custom types, functions và procedures.
- Owner, roles, GRANT, row-level security và chính sách audit.
- Sequences, identity columns, default values.
- Large objects và bảng có primary key/unique constraint.
- Materialized views, foreign tables và external extensions.
- Scheduled jobs, background workers và phần mềm truy cập database.

Không nên giả định mọi DDL phát sinh trong lúc CDC đều tự được replicate. Một số schema change có thể cần thao tác thủ công hoặc có giới hạn theo kịch bản. Chốt quy trình **schema-change freeze** hoặc review trước khi chạy migration.

## 8. Heterogeneous migration: chuyển schema và logic ứng dụng

Chuyển Oracle hoặc SQL Server sang PostgreSQL có thể đòi hỏi thay đổi lớn hơn chuyển dữ liệu cùng engine.

### Các điểm không tương thích thường gặp

| Nhóm | Ví dụ cần kiểm tra |
|---|---|
| Data types | NUMBER/DECIMAL, timestamp with timezone, Unicode, LOB |
| Schema | Namespace, quoted identifiers, collation, index type |
| Constraints | Primary/foreign key, uniqueness, cascade behavior |
| SQL | Dialect, pagination, join hints, proprietary functions |
| Logic trong DB | Stored procedures, packages, triggers, jobs |
| Transaction | Isolation level, locking, savepoints, retry semantics |
| Identity | Sequence, auto-increment, default values |
| Security | Users, roles, GRANT, auditing, encryption |
| Application | JDBC driver, Hibernate dialect, native query, transaction mapping |

DMS có **conversion workspace** cho các migration heterogeneous được hỗ trợ và có tính năng hỗ trợ chuyển đổi schema/code. Công cụ giúp phát hiện và chuyển một phần object, nhưng không thay thế DBA và ứng dụng test nghiệp vụ.

### Quy trình chuyển đổi

1. Thu schema DDL và thống kê object từ source.
2. Chạy assessment khả năng chuyển đổi và phân nhóm object.
3. Dùng conversion workspace theo tài liệu scenario.
4. Xác nhận type mapping, index, constraints và data semantics.
5. Review stored procedures, triggers, jobs và application SQL.
6. Chạy integration tests với database đích.
7. Đo query plan/performance; không coi SQL chạy được là tương đương hiệu năng.
8. Chốt danh sách manual fixes và người chịu trách nhiệm.

Hãy đặc biệt cẩn trọng với tiền tệ, timestamp/timezone, Unicode và NULL semantics. Một thay đổi nhỏ về kiểu dữ liệu có thể không gây lỗi migration job nhưng làm báo cáo tài chính hoặc nghiệp vụ sai.

## 9. Kết nối mạng, xác thực và quyền truy cập

DMS phải có đường đi mạng được hỗ trợ giữa source và destination. Tùy engine và nơi đặt nguồn, có thể cần public connectivity có allowlist, private connectivity, VPN/Interconnect, peering hoặc phương thức tunnel tương ứng.

### Kiểm tra connectivity

- Source hostname/IP có thể resolve từ phía thành phần cần kết nối không?
- Port database có được firewall cho phép từ đúng source IP/network không?
- TLS certificate có hợp lệ và hostname khớp không?
- Network route có đi đúng đường và không bị NAT/overlapping CIDR gây lỗi không?
- Thông lượng và RTT có đủ cho initial load và CDC không?
- Có proxy, bastion hoặc policy chặn long-running connections không?
- Dịch vụ có nằm trong VPC Service Controls perimeter không?
- Có tài khoản và quyền DB/Cloud IAM tương ứng không?

Không mở database ra Internet với rule 0.0.0.0/0 chỉ để migration test thành công. Ưu tiên phương án riêng tư/được giới hạn theo nhu cầu và xác thực TLS. Mọi thông tin kết nối phải được bảo quản như secret.

### Phân biệt ba lớp quyền

| Lớp | Ví dụ | Hậu quả khi thiếu |
|---|---|---|
| Google Cloud IAM | Quyền tạo/xem migration job, connection profile, destination | Không tạo hoặc quản lý được job |
| Network | Firewall, route, DNS, TLS, private connectivity | Không kết nối được tới source |
| Database privileges | Replication, snapshot, đọc schema/data | Job kết nối được nhưng không dump hoặc CDC được |

Không cấp quyền quá rộng chỉ để “chữa” lỗi connection. Bắt đầu từ thông báo lỗi của DMS và kiểm tra từng lớp riêng.

## 10. Tạo và thử migration job trong Console

Ví dụ quy trình tổng quát cho PostgreSQL → Cloud SQL for PostgreSQL. Giao diện và trường cần nhập có thể khác theo scenario hoặc release.

### Bước 1: Chuẩn bị project đích

1. Chọn project và region được phê duyệt.
2. Bật Database Migration API và các API đích cần thiết.
3. Kiểm tra billing, quotas, VPC, DNS và quyền IAM.
4. Chốt nguồn, đích, engine, database version và downtime requirement.
5. Chuẩn bị Cloud SQL destination mới hoặc hiện có theo phương thức DMS hỗ trợ.

Ví dụ bật API:

~~~bash
gcloud services enable datamigration.googleapis.com sqladmin.googleapis.com --project=PROJECT_ID
~~~

Trong một số môi trường, cần bật thêm Service Networking API và cấu hình private connectivity. Không dùng lệnh này như một thay thế cho các bước cấu hình riêng của từng scenario.

### Bước 2: Tạo connection profile

Trong **Database Migration > Connection profiles**, tạo profile nguồn với:

- Engine và version của source.
- Host/IP/port và database identification.
- Migration user và cơ chế bảo vệ credentials.
- TLS/SSL parameters nếu cần.
- Đường mạng được hỗ trợ.

Kiểm thử connection profile theo hướng dẫn. Dữ liệu secret không nên xuất hiện trong screenshot, ticket hoặc tài liệu đào tạo.

### Bước 3: Tạo migration job

1. Mở **Database Migration > Migration jobs**.
2. Chọn **Create migration job**.
3. Đặt job ID, region, source engine và destination engine.
4. Chọn migration type (continuous hoặc one-time nếu scenario cho phép).
5. Chọn source connection profile.
6. Chọn hoặc tạo destination được hỗ trợ.
7. Cấu hình connectivity method và database selection.
8. Kiểm tra summary, region, account, schema và các lựa chọn ảnh hưởng đến dữ liệu.
9. Chạy **Test job** để phát hiện lỗi network/permissions/config.
10. Chỉ khi test đạt và có phê duyệt, chọn **Create and start job** hoặc tạo job rồi start sau.

DMS có thể tạo/điều chỉnh database destination trong quá trình setup. Nếu destination được Terraform quản lý, việc migration thay đổi một số thông số có thể gây **configuration drift**; không tự chạy lại `terraform apply` vào lúc migration đang hoạt động mà chưa kiểm tra hướng dẫn scenario.

### Bước 4: Theo dõi trạng thái

Trong **Migration jobs**, kiểm tra:

- Job state hiện hành.
- Initial load progress.
- CDC phase và replication delay.
- Thông báo lỗi/diagnostics.
- Sức khỏe source/destination và network.
- Disk storage, transaction logs, CPU và connection count.

Không bắt đầu cutover chỉ vì job hiện chữ “running”. Cần có dữ liệu validation và xác nhận đã bắt kịp nguồn.

## 11. CDC và các giới hạn cần hiểu rõ

CDC theo dõi các thay đổi tạo ra sau initial snapshot. Tuy nhiên, CDC khác hoàn toàn với hai cơ sở dữ liệu độc lập được ghi song song.

### Một writer source cho tới cutover

Trước cutover, coi **source là nơi ghi chính**. Tránh dùng destination như một database production độc lập và thực hiện INSERT/UPDATE/DELETE hoặc DDL trên những dữ liệu đang migrate. Điều này có thể gây replication conflict hoặc sai dữ liệu.

Ngay cả khi destination của một scenario không bị ép read-only về kỹ thuật, **quy trình vận hành vẫn phải cấm write vào tập dữ liệu đang replicate** trừ các thao tác được tài liệu cho phép.

### Schema changes trong thời gian CDC

Không giả định mọi thay đổi DDL tự động truyền sang đích. Một số scenario có hạn chế với table definition, extension, trigger hoặc partition changes. Lập quy trình quản lý thay đổi: review, kiểm tra compatibility và freeze trước cutover.

### Transaction consistency

Hãy hiểu điểm nhất quán của initial load và luồng CDC. Một row count khớp tại T1 không đảm bảo dữ liệu khớp tại T2 nếu source vẫn đang ghi. Khi đối soát, phải đồng bộ **điểm thời gian kiểm chứng** hoặc dùng phương pháp nhất quán phù hợp.

### Replication lag

**Replication lag** là chênh lệch giữa tiến độ commit ở nguồn và tiến độ áp dụng ở đích. Có thể tăng khi:

- Source ghi mạnh hơn tốc độ apply.
- Network delay, packet loss hoặc database kết nối gián đoạn.
- Destination thiếu CPU, memory, I/O.
- Transaction lớn, batch hoặc schema lock.
- CDC bị lỗi quyền hoặc mất log cần thiết.

Lag giảm về gần 0 là điều kiện quan trọng nhưng **không đủ** để kết luận database đã sẵn sàng cho production. Còn phải xác nhận dữ liệu, schema, security, hiệu năng và ứng dụng.

## 12. Quan sát migration và đặt ngưỡng cảnh báo

Một migration production nên có dashboard và runbook riêng. Tối thiểu theo dõi:

| Chỉ số | Ý nghĩa | Hành động khi bất thường |
|---|---|---|
| Job state | Job running, failed, stopped hoặc CDC | Kiểm tra diagnostics và owner |
| Initial load progress | Tiến độ copy lịch sử | Xem throughput và bottleneck |
| Replication delay | Mức đích chậm hơn nguồn | Kiểm tra source log, network và destination |
| Source log growth | Binlog/WAL retention tăng | Bảo vệ dung lượng, kiểm tra stalled replication |
| Destination CPU/I/O | Tải apply và query | Điều chỉnh capacity theo hướng dẫn |
| Source DB connections | Ảnh hưởng tài khoản replication | Kiểm tra connection limits |
| Storage used | Dung lượng đích và logs | Kiểm tra quota, disk growth |
| Error logs | Lỗi authentication, schema, timeout | Phân loại và khắc phục |

Các metric name cụ thể khác nhau theo engine và sản phẩm. Dùng trang **Migration job metrics** của scenario thực tế thay vì copy một filter không đúng sang môi trường khác.

### Quy trình phản ứng khi lag tăng

1. Xác minh job vẫn ở CDC.
2. Đo lag hiện tại, tốc độ tăng và thời gian kéo dài.
3. Kiểm tra nguồn có batch/large transaction hay không.
4. Kiểm tra log retention và dung lượng disk.
5. Kiểm tra network, SSL, retries và trạng thái destination.
6. Xác định có cần điều chỉnh capacity, lịch batch hoặc tốc độ ghi.
7. Chỉ đặt lịch cutover khi lag ổn định và đáp ứng điều kiện đã phê duyệt.

Đừng vô hiệu hóa retention hoặc xóa replication slot/binlog khi job đang sử dụng. Các thao tác đó có thể làm mất khả năng tiếp tục đồng bộ.

## 13. Đối soát dữ liệu trước khi cutover

Một job đạt trạng thái CDC không có nghĩa mọi yêu cầu nghiệp vụ đều đã được thỏa mãn. Nhóm DBA và application owner phải đối soát dữ liệu.

### Tầng 1: schema

- Database, schema, table, column và data types được tạo đúng.
- Primary keys, unique indexes, foreign keys và constraints phù hợp.
- Views, functions, procedures, triggers và extensions được xử lý.
- Roles, grants, sequences, defaults và encryption được kiểm tra.

### Tầng 2: dữ liệu

- Row counts theo bảng lớn và bảng nghiệp vụ quan trọng.
- Checksums/hashes trên các tập dữ liệu được chọn với cùng thời điểm nhất quán.
- Tổng giá trị tài chính, số lượng đơn hàng và trạng thái giao dịch.
- Null counts, min/max timestamps, unique constraints.
- Large objects, Unicode, timezone và decimal precision.

Ví dụ truy vấn PostgreSQL để đối chiếu sau khi nguồn đã vào điểm nhất quán cho kiểm chứng:

~~~sql
SELECT COUNT(*) AS order_count
FROM orders;

SELECT status, COUNT(*) AS total
FROM orders
GROUP BY status
ORDER BY status;

SELECT MIN(created_at), MAX(created_at)
FROM orders;
~~~

Với dữ liệu lớn, `COUNT(*)` có thể rất tốn tài nguyên. Hãy chạy trong cửa sổ được DBA phê duyệt, dùng thống kê, chunking hoặc phương pháp reconciliation tối ưu; không chạy full scan nặng trên production trong giờ cao điểm.

### Tầng 3: ứng dụng

- Java/Spring JDBC/Hibernate kết nối được tới destination.
- Transactions và isolation level hoạt động đúng.
- Query performance trong giới hạn SLO.
- Các read/write flow nghiệp vụ quan trọng thành công.
- Batch, ETL, reporting và background workers hoạt động.
- Hành vi timezone, collation, sequence và transaction retry không bị thay đổi ngoài ý muốn.

### Tầng 4: vận hành

- Backup/PITR và HA/DR đã bật theo chính sách khi destination trở thành primary.
- Monitoring, logs, alerts và on-call đã được thiết lập.
- Security controls/IAM, audit và secret rotation đã được kiểm chứng.
- Có biên bản kết quả và người chấp nhận cutover.

## 14. Runbook cutover cho continuous migration

**Cutover** là thời điểm ứng dụng ngừng ghi vào source và bắt đầu sử dụng destination. Mục tiêu là đảm bảo chỉ có **một nguồn ghi chính** ở mỗi thời điểm.

### Trước cửa sổ cutover

1. Kiểm tra job đã vào CDC và replication delay ổn định.
2. Hoàn tất rehearsal trong staging hoặc môi trường thử nghiệm tương tự.
3. Xác nhận backup/source recovery và kiểm thử restore nếu phù hợp.
4. Chuẩn bị config, DNS/JDBC endpoint, secret, firewall, connection pool, monitoring.
5. Phê duyệt downtime, owner, communication và rollback criteria.
6. Đóng các outstanding issues critical.
7. Xác định bước freeze mọi producer ghi dữ liệu, kể cả batch, ETL, cron, API và admin scripts.

### Trong cửa sổ cutover

~~~mermaid
flowchart TD
  A[Thông báo bắt đầu cutover] --> B[Dừng mọi ghi vào source]
  B --> C[Drain app connections và batch jobs]
  C --> D[Chờ CDC backlog / lag gần 0]
  D --> E{Validation đạt?}
  E -->|Không| F[Giữ source là primary; xử lý vấn đề]
  E -->|Có| G[Promote destination]
  G --> H[Cập nhật endpoint / secret / routing]
  H --> I[Khởi động app, kiểm thử đọc-ghi]
  I --> J{SLO và dữ liệu đúng?}
  J -->|Có| K[Theo dõi tăng cường]
  J -->|Không| L[Kích hoạt runbook sự cố / rollback được thiết kế]
~~~

Các bước thực hiện:

1. Chặn ingress hoặc đặt ứng dụng vào maintenance mode.
2. Dừng worker, scheduler, ETL, integration và mọi client có quyền ghi.
3. Đợi transaction đang chạy hoàn thành hoặc xử lý theo runbook.
4. Đo replication lag tới mức gần 0 và xác nhận điểm dữ liệu đã bắt kịp.
5. Đối soát các bảng critical lần cuối.
6. **Promote** migration job/destination theo hướng dẫn engine.
7. Cập nhật JDBC connection string, secret, DNS, egress rule và credential.
8. Redeploy/restart hoặc refresh connection pool để bỏ kết nối cũ.
9. Kiểm thử create/read/update và các nghiệp vụ chính trên destination.
10. Theo dõi log, error rate, latency, connection count và dữ liệu mới.

DMS có thể cho phép promote khi replication lag chưa bằng 0, nhưng điều đó có nguy cơ mất tính chính xác dữ liệu. Không dùng lựa chọn này như lối tắt để kết thúc migration nhanh.

### Ví dụ gcloud để kiểm tra job

~~~bash
gcloud database-migration migration-jobs list --region=REGION --project=PROJECT_ID

gcloud database-migration migration-jobs describe MIGRATION_JOB_ID --region=REGION --project=PROJECT_ID
~~~

Với promote, dùng Console hoặc lệnh `gcloud database-migration migration-jobs promote` sau khi kiểm tra cú pháp phiên bản gcloud và đủ điều kiện cutover. **Không chạy promote chỉ để thử** trên job production; promote là bước thay đổi vai trò database và thường không thể đảo ngược bằng một thao tác đơn giản.

## 15. Rollback: vì sao phải thiết kế từ trước?

Trước promote, rollback thường có thể dừng tiến trình chuyển đổi và tiếp tục dùng source, với điều kiện source vẫn là writer chính và chưa bị thay đổi phá hủy.

**Sau khi destination bắt đầu nhận write**, nguồn cũ đã lỗi thời. DMS không tự đồng bộ ngược những giao dịch mới từ destination. Vì vậy rollback có thể cần một trong các phương án:

- Chuyển traffic về source **chỉ khi** chắc chắn chưa có write mới trên destination.
- Dùng một quy trình reverse migration/replication riêng đã được thử nghiệm.
- Khôi phục từ backup và replay những giao dịch phù hợp.
- Tạm dừng dịch vụ và sửa lỗi trên destination thay vì chuyển về source.
- Thực hiện forward fix cho các lỗi có thể khắc phục an toàn.

Chọn phương án theo RPO, loại dữ liệu và business impact. Đặt **point of no return** rõ ràng: sau bước nào rollback về source không còn an toàn nếu không có reconciliation. Không ghi chung chung “rollback bằng cách đổi JDBC URL trở lại”.

### Runbook rollback tối thiểu

| Yêu cầu | Câu hỏi |
|---|---|
| Trigger | Lỗi nào buộc phải rollback? |
| Decision maker | Ai phê duyệt trong incident bridge? |
| Data | Có write mới ở đích chưa, sẽ bảo toàn bằng cách nào? |
| Routing | Cấu hình, DNS, credential, pool và network đổi lại thế nào? |
| Recovery | Backup, PITR, replica hoặc reverse sync đã thử chưa? |
| Verification | Các nghiệp vụ nào cần kiểm thử lại? |
| Communication | Khi nào thông báo user và bên liên quan? |

## 16. Ảnh hưởng tới ứng dụng Java và Spring Boot

Sau khi promote, ứng dụng không nên chỉ đổi hostname rồi coi việc di chuyển hoàn tất. Cần xem xét:

- Driver JDBC tương thích engine/version destination.
- JDBC URL, SSL mode, certificate chain và connection timeout.
- HikariCP pool size và connection lifecycle.
- Transaction isolation/locking và retry policy.
- Schema migration tool như Flyway/Liquibase.
- Hibernate dialect, native SQL và data type mapping.
- Timezone/locale/collation và handling of timestamps.
- Read replicas và routing read-only nếu có.
- Identity và Secret Manager cho database credentials.
- Cloud SQL connector/Auth Proxy hoặc private IP theo kiến trúc được phê duyệt.

Ví dụ cấu hình Spring Boot tối giản (placeholder, không chứa mật khẩu thật):

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://DB_HOST:5432/orders
    username: DB_USER
    password: DB_PASSWORD_FROM_SECRET
    hikari:
      maximum-pool-size: 10
      connection-timeout: 30000
  jpa:
    open-in-view: false
~~~

Không commit `DB_PASSWORD_FROM_SECRET` dưới dạng giá trị thật. Với production, đọc secret từ môi trường/kho bí mật được phê duyệt và sử dụng xác thực database phù hợp. Số connection pool là giá trị minh họa, phải sizing theo số instance và giới hạn connections của database.

### Cutover và connection pool

Khi JDBC endpoint đổi:

1. Đảm bảo ứng dụng không còn connection đang mở tới source.
2. Redeploy hoặc làm mới pool theo phương án được kiểm thử.
3. Chạy health check có thao tác database thực, không chỉ trả HTTP 200.
4. Thử đường read/write và transaction.
5. Theo dõi số connections ở destination và old source.
6. Kiểm tra session/transaction timeout và TLS errors.

Nếu dùng DNS làm alias database, TTL thấp giúp giảm cache ở một số thành phần nhưng **không buộc mọi JVM hoặc connection pool cập nhật lập tức**. Xác nhận cơ chế DNS caching và lifecycle của ứng dụng.

### Không đổi schema cùng lúc nếu không cần

Khi mục tiêu trước tiên là di chuyển hạ tầng database, nên hạn chế đồng thời nâng major version, thay đổi ORM, thêm migration script lớn và đổi logic nghiệp vụ. Nếu bắt buộc phải thay đổi schema, phải có kế hoạch version compatibility và migration rehearsal riêng.

## 17. Thực hành có kiểm soát: PostgreSQL → Cloud SQL for PostgreSQL

Đây là bài lab về quy trình, không yêu cầu hoặc khuyến khích thao tác trên database production. Chọn project sandbox, dữ liệu giả và chi phí có thể kiểm soát.

### Đầu vào

- PostgreSQL source thuộc phiên bản được DMS hỗ trợ.
- Một bảng mẫu `orders` chứa dữ liệu thử nghiệm.
- Source có logical replication được cấu hình theo scenario.
- Destination Cloud SQL for PostgreSQL tương thích.
- Network connectivity/TLS và migration user.
- Quyền Google Cloud IAM để tạo connection profile/job.
- Runbook tạo/dừng job, cleanup và kiểm tra billing.

### Các bước

1. Tạo dữ liệu ban đầu trong source sandbox.
2. Kiểm tra phiên bản, extensions, replication parameters và privileges.
3. Tạo source connection profile.
4. Tạo destination và connectivity method.
5. Tạo continuous migration job và chạy **Test job**.
6. Bắt đầu job, quan sát initial load hoàn thành.
7. Thêm/cập nhật/xóa một số bản ghi thử nghiệm ở **source**.
8. Quan sát CDC progress và replication delay.
9. Đối soát bản ghi giữa hai database tại thời điểm kiểm chứng phù hợp.
10. Dừng mọi write vào source.
11. Chờ lag gần 0, kiểm tra kết quả lần cuối.
12. Promote destination theo hướng dẫn scenario.
13. Trỏ một ứng dụng Spring Boot lab tới destination và thử read/write.
14. Quan sát metrics/logs; ghi lại các kết quả và chi phí.
15. Xóa migration job, connection profile và tài nguyên sandbox khi không còn cần thiết, theo đúng thứ tự an toàn.

### Tiêu chí PASS

- Connection test và migration job không báo lỗi critical.
- Initial load có dữ liệu đầy đủ theo phạm vi đã chọn.
- CDC đưa các thay đổi nguồn sau snapshot sang destination.
- Replication lag giảm về ngưỡng được phê duyệt trước promote.
- Đối soát row counts và giá trị nghiệp vụ mẫu đạt.
- Ứng dụng Java kết nối được và xử lý transaction đúng.
- Backup, monitoring và IAM cho destination đã được cấu hình.
- Không còn tài nguyên lab không cần thiết sau cleanup.

## 18. Các lỗi migration thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| Test job không kết nối được source | Sai DNS, firewall, route, TLS hoặc port | Kiểm tra connectivity theo đường thực tế |
| Authentication failed | Sai user/password hoặc privilege | Xác minh tài khoản migration và quyền tối thiểu |
| MySQL CDC không bắt đầu | Binlog chưa bật, sai format hoặc retention | Xem cấu hình ROW binlog và log retention |
| PostgreSQL CDC lỗi | Logical replication, slot hoặc extension chưa đúng | Đối chiếu scenario và cấu hình nguồn |
| Initial load quá chậm | Throughput/network/destination I/O chưa đủ | Đo bottleneck, điều chỉnh capacity |
| CDC lag tăng liên tục | Tốc độ ghi cao, transaction lớn, đích chậm | Đo lag và tài nguyên hai đầu |
| Source disk đầy | Binlog/WAL bị giữ vì replication chậm | Khắc phục lag, xem retention/slot an toàn |
| Destination thiếu object | Extension, schema/DDL hoặc đối tượng không được hỗ trợ | Review known limitations, thực hiện thủ công có kiểm chứng |
| Row count không khớp | So sánh sai thời điểm, source còn ghi hoặc lỗi migration | Chốt consistent point và đối soát lại |
| Sequence lệch sau cutover | Sequence/identity chưa được kiểm tra | Xác minh giá trị và quyền sau promotion |
| App lỗi khi trỏ đích | JDBC/SSL/permissions/connection pool | Test driver, cert, secret, network và pool |
| Query chậm sau migration | Index/statistics/query planner khác | ANALYZE/tuning và benchmark theo DBA |
| Promote khi còn backlog | Source writes chưa dừng, lag chưa về gần 0 | Không cutover cho tới khi đạt tiêu chí |
| Rollback về nguồn làm mất giao dịch | Destination đã nhận write nhưng source không có reverse sync | Dùng phương án rollback dữ liệu đã rehearsal |
| Terraform drift | DMS đã điều chỉnh destination trong migration | Không re-apply mù; reconcile sau migration |

## 19. Bảo mật, chi phí và vận hành dài hạn

### Bảo mật

- Giới hạn quyền DMS và IAM vào đúng project, region và service.
- Dùng tài khoản DB riêng cho migration, xóa/thu hồi sau khi hoàn tất.
- Bảo vệ connection profiles, secrets và TLS certificates.
- Chọn private connectivity hoặc mạng được giới hạn khi khả thi.
- Không lưu dump chứa dữ liệu nhạy cảm ở bucket công khai hoặc file chia sẻ.
- Ghi nhận quyền truy cập, audit logs và thay đổi firewall.
- Đánh giá data residency, retention và quy định tuân thủ trước khi di chuyển.

### Chi phí

Một migration có thể phát sinh chi phí từ:

- Cloud SQL/AlloyDB destination được tạo và chạy trong thời gian đồng bộ.
- Storage, network traffic, backup và data egress từ nguồn/cloud khác.
- Migration service hoặc tính năng có phí theo pricing hiện hành.
- Thời gian giữ cả hai hệ thống hoạt động song song.
- Logging/Monitoring và công cụ kiểm thử/đối soát.

Dù migration job chưa bắt đầu, destination đã được tạo có thể phát sinh chi phí. Hãy theo dõi thời gian chạy và cleanup tài nguyên sau khi xác nhận.

### Vận hành sau cutover

Sau khi destination thành primary:

1. Xác nhận backup, PITR và HA theo yêu cầu.
2. Kiểm tra database flags, maintenance window, storage autoscaling.
3. Thiết lập monitoring, alerts và audit.
4. Cập nhật CMDB, diagrams, runbook và owner.
5. Xác minh không còn client ghi vào source cũ.
6. Chỉ decommission source sau khi hoàn tất thời gian quan sát và có phê duyệt.
7. Thu hồi quyền migration, đóng firewall tạm và xoay vòng credential.

## 20. Checklist trước khi đánh dấu migration thành công

- [ ] Source/destination nằm trong danh sách scenario và version được hỗ trợ.
- [ ] Schema, extensions, triggers, procedures và compatibility đã được đánh giá.
- [ ] Có migration user/IAM least privilege và kết nối mạng an toàn.
- [ ] Initial load thành công, CDC chạy ổn định khi áp dụng.
- [ ] Không có replication error và log retention đủ.
- [ ] Có dashboard theo dõi lag, job state và disk usage.
- [ ] Đã đối soát dữ liệu bằng kiểm tra thích hợp.
- [ ] Tất cả producer ghi ở source đều có kế hoạch dừng.
- [ ] Có downtime window, người phê duyệt và communication plan.
- [ ] Lag tại cutover đạt ngưỡng được phê duyệt.
- [ ] Promotion thành công và destination ở trạng thái phục vụ độc lập.
- [ ] Ứng dụng Java/Spring đã chuyển endpoint và kiểm thử read/write.
- [ ] Backup/PITR, bảo mật, monitoring và on-call của destination hoạt động.
- [ ] Rollback/runbook nêu rõ rủi ro sau khi destination có write mới.
- [ ] Source chưa bị xóa trước khi có phê duyệt decommission.

## Câu hỏi ôn tập

1. Vì sao continuous migration vẫn cần thời gian cutover dù DMS đã copy dữ liệu bằng CDC?
2. Phân biệt one-time migration với continuous migration trong trường hợp source vẫn ghi.
3. DMS có phù hợp để vận hành hai database cùng được ứng dụng ghi song song không?
4. Vì sao cần kiểm tra `binlog_format=ROW` khi migrate MySQL liên tục?
5. Với PostgreSQL, replication slots và WAL retention có liên hệ thế nào với disk growth?
6. Tại sao replication lag gần 0 chưa đủ để đảm bảo migration đã thành công?
7. Khi nào heterogeneous migration cần conversion workspace và kiểm thử SQL ứng dụng?
8. Vì sao không nên ghi dữ liệu mới vào destination khi CDC vẫn áp dụng thay đổi từ source?
9. Nếu Java API đã ghi giao dịch ở destination rồi mới phát hiện sự cố, vì sao rollback bằng cách trỏ lại nguồn cũ không an toàn?
10. Sau promotion, đội DBA và SRE phải xác minh những khả năng vận hành nào?

## Kết luận

Database Migration Service giúp chuyển database tới Cloud SQL và AlloyDB for PostgreSQL theo các scenario được hỗ trợ, gồm initial load và khả năng đồng bộ thay đổi liên tục khi thích hợp. Continuous migration có thể giảm downtime bằng cách duy trì CDC trong khi nguồn vẫn phục vụ, nhưng không thay thế bước **dừng ghi, đợi replication bắt kịp, đối soát dữ liệu, promote và chuyển ứng dụng**.

Đối với ứng dụng Java/Spring, migration chỉ hoàn thành khi dữ liệu đúng, JDBC/transactions hoạt động, query performance đạt yêu cầu và đội vận hành đã có backup, IAM, monitoring và rollback rõ ràng. Chìa khóa là khảo sát và kiểm chứng trước, chỉ có một writer chính tại mỗi thời điểm và không nhầm DMS với công cụ active-active replication hai chiều.

## Tài liệu tham khảo

- [Database Migration Service overview](https://cloud.google.com/database-migration/docs/overview)
- [Database Migration Service documentation](https://cloud.google.com/database-migration/docs)
- [Supported source and destination databases](https://cloud.google.com/database-migration/docs/supported-databases)
- [Known limitations by migration scenario](https://cloud.google.com/database-migration/docs/known-limitations)
- [Database Migration Service for PostgreSQL — Migration flow](https://cloud.google.com/database-migration/docs/postgres/migration-types)
- [Configure PostgreSQL source database](https://cloud.google.com/database-migration/docs/postgres/configure-source-database)
- [Configure MySQL source for continuous migrations](https://cloud.google.com/database-migration/docs/mysql/configure-source-database-continuous)
- [Create a PostgreSQL migration job](https://cloud.google.com/database-migration/docs/postgres/create-migration-job)
- [Promote a PostgreSQL migration job](https://cloud.google.com/database-migration/docs/postgres/promote-migration)
- [Cloud SQL for PostgreSQL documentation](https://cloud.google.com/sql/docs/postgres)
- [AlloyDB for PostgreSQL documentation](https://cloud.google.com/alloydb/docs)

