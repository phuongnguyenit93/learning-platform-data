# Phân biệt sẵn sàng cao, khôi phục thảm họa và mở rộng năng lực xử lý

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Sẵn sàng cao  
> **Mục tiêu:** Phân biệt High Availability (HA), Disaster Recovery (DR) và Scalability; hiểu các failure domain và mục tiêu RTO/RPO; lựa chọn các kiến trúc Oracle như RAC, Data Guard và RMAN; thiết kế service, client failover, load balancing và mở rộng tài nguyên; kết hợp các lớp bảo vệ thành kiến trúc phù hợp; kiểm thử và vận hành theo các kịch bản sự cố thực tế.

## 1. Ba mục tiêu thường bị nhầm lẫn

Một hệ thống database có thể cần đồng thời ba khả năng:

- **High Availability (HA) — Sẵn sàng cao:** duy trì hoặc nhanh chóng khôi phục dịch vụ khi một thành phần bị lỗi, với thời gian gián đoạn thấp.
- **Disaster Recovery (DR) — Khôi phục thảm họa:** khôi phục dịch vụ và dữ liệu khi một failure domain lớn bị mất, chẳng hạn toàn bộ site, storage hoặc vùng hạ tầng.
- **Scalability — Mở rộng năng lực xử lý:** tăng khả năng phục vụ khi số người dùng, request, dữ liệu hoặc workload tăng.

Ba mục tiêu có quan hệ nhưng không đồng nghĩa:

| Mục tiêu | Câu hỏi chính | Ví dụ giải pháp Oracle |
|---|---|---|
| HA | Một node hoặc instance hỏng thì dịch vụ tiếp tục thế nào? | Oracle RAC, Oracle Clusterware, service failover, Application Continuity |
| DR | Cả site hoặc database chính mất thì khôi phục ở đâu và mất bao nhiêu dữ liệu? | Oracle Data Guard, RMAN backup/restore, standby site |
| Scalability | Khi tải tăng, làm sao xử lý thêm request hoặc dữ liệu? | Scale-up, RAC scale-out, sharding, partitioning, connection/service design |

Một cluster RAC có thể tăng khả năng chịu lỗi node và mở rộng workload trong cùng cluster, nhưng không tự bảo vệ trước việc mất toàn bộ site. Một standby Data Guard có thể bảo vệ database ở site khác, nhưng không tự tăng throughput của primary. Tăng CPU hoặc thêm node có thể tăng capacity nhưng không tự tạo bản sao dữ liệu để phục hồi sau thảm họa.

**Thiết kế tốt thường kết hợp cả ba mục tiêu và backup/recovery.**

## 2. Xác định failure domain trước khi chọn công nghệ

Failure domain là phạm vi các thành phần có thể cùng bị ảnh hưởng bởi một sự cố. Kiến trúc HA/DR phải xác định rõ sự cố nào cần chịu được.

Ví dụ các failure domain tăng dần:

1. Một process hoặc session lỗi.
2. Một database service không hoạt động.
3. Một Oracle instance bị crash.
4. Một máy chủ/node bị mất.
5. Một rack, network switch hoặc storage array bị lỗi.
6. Một availability zone hoặc data center mất kết nối.
7. Một region/site gặp thảm họa.
8. Lỗi logic hoặc hành động con người làm hỏng/xóa dữ liệu trên nhiều bản sao.

Các công nghệ giải quyết những phạm vi khác nhau:

- Session recovery, retry và application connection management xử lý lỗi ở mức request/session.
- RAC và Clusterware xử lý một số lỗi instance/node trong cluster.
- Data Guard duy trì một database khác để chuyển role khi primary/site gặp sự cố.
- RMAN backup và recovery bảo vệ khả năng khôi phục khi dữ liệu bị hỏng, xóa nhầm hoặc các bản sao trực tuyến không còn đáng tin cậy.
- Immutable/offsite backups giúp chống lại một số tình huống xóa mã độc hoặc compromise cả môi trường production.

### 2.1. Không đặt hai bản sao trong cùng failure domain

Hai node RAC trong cùng rack có thể cùng mất nguồn điện. Hai database trên cùng storage array có thể cùng mất dữ liệu khi array hỏng. Primary và standby trong cùng data center có thể cùng bị ảnh hưởng bởi lũ, cháy hoặc mất mạng diện rộng.

Khi thiết kế DR, cần phân tách các failure domain thực sự:

- Host và rack.
- Power và cooling.
- Storage.
- Network path.
- Data center/availability zone.
- Region.
- Identity/credential và backup administration domain.

Tách địa lý nhưng dùng chung một hệ thống identity, một tài khoản quản trị hoặc một storage control plane có thể vẫn để lại điểm lỗi chung.

### 2.2. Phân loại sự cố theo phạm vi

| Sự cố | HA có thể giúp? | DR có thể cần? | Backup/recovery có thể cần? |
|---|---|---|---|
| Process/session lỗi | Có, thường retry/reconnect | Thường không | Thường không |
| Một RAC instance lỗi | Có, nếu cluster/service được cấu hình đúng | Không nhất thiết | Không nhất thiết |
| Một node lỗi | RAC có thể tiếp tục trên node còn lại | Có nếu toàn cluster/site mất | Có nếu dữ liệu bị hỏng |
| Storage primary hỏng | Redundancy phụ thuộc storage design | Data Guard có thể chuyển sang standby | RMAN có thể cần cho recovery |
| Mất cả site | HA nội site không đủ | Có | Backup có thể là phương án phục hồi |
| Xóa nhầm dữ liệu và lỗi được replicate | HA không giải quyết | Standby có thể cũng nhận thay đổi | PITR/backup hoặc logical recovery |
| Ransomware xóa cả bản sao trực tuyến | HA/replication có thể bị ảnh hưởng | DR online có thể bị ảnh hưởng | Immutable/offline backup rất quan trọng |

## 3. RTO, RPO, availability và các chỉ số vận hành

Trước khi chọn RAC, Data Guard hoặc backup strategy, cần xác định mục tiêu nghiệp vụ.

### 3.1. RTO — Recovery Time Objective

RTO là thời gian tối đa mà dịch vụ được phép ngừng trước khi phải khôi phục hoạt động.

Ví dụ:

- RTO 30 giây: cần cơ chế phát hiện và chuyển tiếp rất nhanh, client phải reconnect/replay phù hợp.
- RTO 15 phút: có thể chấp nhận quy trình failover có một số bước tự động và kiểm tra.
- RTO 4 giờ: restore/recovery từ backup có thể đáp ứng nếu đã đo và diễn tập.

RTO phải tính toàn bộ thời gian từ lúc sự cố bắt đầu đến lúc người dùng thực sự sử dụng lại được dịch vụ, không chỉ thời gian database báo OPEN.

Các thành phần của RTO:

- Detection time.
- Decision/approval time.
- Failover hoặc restore time.
- Database open/recovery time.
- Service/listener/client reconnection.
- Application validation.
- Business reconciliation.

### 3.2. RPO — Recovery Point Objective

RPO là lượng dữ liệu tối đa được phép mất, thường biểu diễn bằng thời gian hoặc điểm giao dịch.

Ví dụ:

- RPO 0 theo nghĩa nghiệp vụ yêu cầu không mất giao dịch đã commit trong failure model đã xác định.
- RPO 1 phút cho phép mất tối đa khoảng một phút dữ liệu trong tình huống được định nghĩa.
- RPO 24 giờ có thể phù hợp với dữ liệu ít quan trọng và backup theo ngày.

RPO phụ thuộc cách bảo vệ redo/data:

- Synchronous redo transport có thể giảm hoặc loại bỏ mất dữ liệu đã commit trong failure assumptions phù hợp.
- Asynchronous transport có thể có transport lag và mất redo chưa tới standby.
- Backup theo lịch có thể có RPO lớn hơn khoảng thời gian giữa các backup nếu archived logs không được bảo vệ đầy đủ.

Không hứa RPO 0 chỉ vì hệ thống có standby. Phải xác định protection mode, commit semantics, network failure behavior và failure scenario.

### 3.3. Availability và downtime budget

Availability thường được biểu diễn bằng tỷ lệ thời gian dịch vụ sẵn sàng:

\[
Availability = \frac{Uptime}{Uptime + Downtime}
\]

Ví dụ downtime lý thuyết trong một năm 365 ngày:

| Availability | Downtime xấp xỉ mỗi năm |
|---:|---:|
| 99% | 3 ngày 15 giờ 36 phút |
| 99,9% | 8 giờ 45 phút 36 giây |
| 99,95% | 4 giờ 22 phút 48 giây |
| 99,99% | 52 phút 34 giây |
| 99,999% | 5 phút 15 giây |

Đây là phép quy đổi lý thuyết. SLO thực tế cần xác định maintenance window, planned/unplanned downtime, cách đo request success và phạm vi dịch vụ.

### 3.4. MTTR và MTBF

- **MTTR (Mean Time To Repair/Recover):** thời gian trung bình để khôi phục sau sự cố, tùy cách tổ chức định nghĩa.
- **MTBF (Mean Time Between Failures):** thời gian trung bình giữa các sự cố.

HA thường giảm thời gian gián đoạn khi lỗi thành phần xảy ra. DR giảm thời gian và mức mất dữ liệu khi failure domain lớn bị ảnh hưởng. Monitoring, automation và runbook tốt giúp giảm detection time và MTTR.

## 4. High Availability với Oracle RAC

Oracle Real Application Clusters (RAC) cho phép nhiều instance trên nhiều node cùng truy cập một database dùng chung storage theo kiến trúc cluster được hỗ trợ.

Mô hình khái quát:

~~~text
             Application clients
                     |
             Oracle Services
                     |
          +----------+----------+
          |                     |
       Node 1                Node 2
     +---------+           +---------+
     | Instance|           | Instance|
     | RAC1    |           | RAC2    |
     +----+----+           +----+----+
          |                     |
          +----------+----------+
                     |
              Shared storage
               Database files
~~~

Nếu một instance/node lỗi, các instance còn lại có thể tiếp tục phục vụ workload theo cấu hình và capacity còn lại.

### 4.1. RAC xử lý lỗi nào?

RAC có thể tăng khả năng chịu lỗi đối với:

- Một instance bị crash.
- Một node bị mất.
- Một số process/service lỗi.
- Bảo trì node theo rolling procedure được hỗ trợ.
- Phân phối workload giữa các instance.

RAC không tự bảo vệ trước mọi lỗi:

- Mất toàn bộ shared storage nếu không có redundancy thích hợp.
- Mất cả data center.
- Lỗi logic hoặc DML sai được ghi vào database.
- Xóa nhầm bảng.
- Ransomware hoặc compromise quyền quản trị.
- Lỗi ứng dụng khiến mọi node cùng nhận workload bất thường.

### 4.2. Cache Fusion và interconnect

Các RAC instance có buffer cache riêng nhưng cùng truy cập database. Cache Fusion dùng cluster interconnect để chuyển block giữa các instance khi cần.

Interconnect latency, packet loss, bandwidth và node membership ảnh hưởng trực tiếp đến hiệu năng và ổn định RAC.

Workload có nhiều block contention hoặc hot blocks có thể tăng global cache waits. RAC không làm mọi SQL nhanh hơn; ứng dụng và data access pattern cần được thiết kế để hạn chế contention xuyên instance.

### 4.3. Service là đơn vị kết nối ứng dụng

Ứng dụng nên kết nối qua database service được quản lý thay vì hardcode một instance cụ thể.

Service có thể xác định:

- Instance preferred/available.
- Workload role.
- Failover behavior.
- Connection load balancing.
- Runtime load balancing.
- PDB/service association.

Trong RAC, service giúp đưa workload tới instance phù hợp và hỗ trợ chuyển service khi node lỗi.

Kiểm tra service:

~~~sql
SELECT inst_id,
       name,
       network_name,
       con_id
FROM gv$services
ORDER BY name, inst_id;
~~~

Lệnh Clusterware để xem service status, tùy kiến trúc:

~~~text
srvctl status service -db <db_unique_name>
srvctl status database -db <db_unique_name>
~~~

### 4.4. Connection load balancing và runtime load balancing

Connection load balancing phân phối connection mới giữa các instance/service theo cấu hình. Runtime load balancing dùng thông tin workload/performance để hướng request tới nơi phù hợp khi driver và service configuration hỗ trợ.

Cần phân biệt:

- Connection balancing: quyết định connection ban đầu.
- Runtime balancing: định tuyến workload/request đang chạy hoặc connection theo thông tin runtime.
- Failover: xử lý khi instance/service không còn sẵn sàng.

Không mặc định mọi JDBC/OCI client tự động có đầy đủ khả năng này. Driver, connect descriptor, service goal và pool configuration phải tương thích.

### 4.5. FAN, FCF và Application Continuity

Oracle có các cơ chế client-side hỗ trợ HA:

- **Fast Application Notification (FAN):** thông báo sự kiện service/instance tới client hoặc connection pool.
- **Fast Connection Failover (FCF):** giúp pool loại bỏ connection lỗi và phản ứng với FAN event khi được cấu hình hỗ trợ.
- **Application Continuity:** có thể replay một số request/database calls sau lỗi theo điều kiện được hỗ trợ.
- **Transparent Application Continuity:** mở rộng khả năng replay trong một số cấu hình/driver/service.

Các tính năng này phụ thuộc Oracle release, driver, pool, service và license/option liên quan. Không phải mọi transaction đều có thể replay an toàn. Ứng dụng cần thiết kế idempotency, transaction boundary và xử lý side effect ngoài database.

### 4.6. RAC không phải DR

RAC thường dùng shared database storage trong một cluster/site. Nếu site bị mất hoàn toàn hoặc dữ liệu bị hỏng logic, các node RAC có thể cùng không hoạt động hoặc cùng nhìn thấy dữ liệu đã hỏng.

Vì vậy, RAC không thay thế Data Guard hoặc RMAN backup. Một hệ thống yêu cầu HA nội site và DR liên site thường dùng RAC ở primary và Data Guard tới site khác.

## 5. Disaster Recovery với Oracle Data Guard

Oracle Data Guard duy trì một hoặc nhiều standby database từ primary thông qua redo transport và redo apply.

Mô hình:

~~~text
                Application
                    |
               Primary service
                    |
             +--------------+
             | Primary DB   |
             | READ WRITE   |
             +------+-------+
                    |
              Redo transport
                    |
          WAN / DR network
                    |
             +------+-------+
             | Standby DB   |
             | MOUNTED or   |
             | READ ONLY*   |
             +--------------+

* Trạng thái mở phụ thuộc loại standby, cấu hình và option được cấp phép.
~~~

Primary ghi redo; redo được truyền tới standby và apply để cập nhật datafiles. Khi primary/site gặp sự cố, standby có thể được chuyển thành primary theo quy trình switchover/failover.

### 5.1. Physical standby

Physical standby duy trì bản sao vật lý của primary bằng redo apply. Nó phù hợp với nhiều kịch bản DR database-level.

Đặc điểm:

- Datafile và database structure được duy trì theo redo.
- Redo Apply cập nhật standby.
- Có thể dùng MRP (Managed Recovery Process) tùy chế độ.
- Standby thường ở MOUNTED hoặc READ ONLY WITH APPLY trong cấu hình hỗ trợ.
- Chuyển role bằng switchover/failover theo điều kiện.

Physical standby thường là lựa chọn phổ biến cho DR Oracle.

### 5.2. Logical standby

Logical standby áp dụng SQL tương đương từ redo vào database mở, cho phép một số khác biệt cấu trúc và hoạt động đọc/ghi theo giới hạn được hỗ trợ.

Nó có các hạn chế về datatype, object và thao tác DDL/DML so với physical standby. Không giả định mọi schema/object đều được hỗ trợ. Cần kiểm tra supported data types, SQL Apply restrictions và release.

### 5.3. Snapshot standby

Snapshot standby chuyển physical standby sang trạng thái mở read/write để thử nghiệm hoặc kiểm thử trong một khoảng thời gian; redo từ primary được nhận và lưu trữ nhưng chưa apply như physical standby bình thường. Khi convert lại, các thay đổi cục bộ bị loại bỏ và redo được apply.

Snapshot standby hữu ích cho test có dữ liệu gần production, nhưng không phải DR standby sẵn sàng failover ngay trong thời gian đang ở snapshot mode. Nó cần dung lượng và kế hoạch convert back.

### 5.4. Redo transport và apply

Hai giai đoạn cần theo dõi riêng:

- **Transport:** primary gửi redo tới standby.
- **Apply:** standby áp dụng redo vào datafiles.

Transport lag và apply lag có ý nghĩa khác nhau. Standby có thể nhận redo nhanh nhưng apply chậm; hoặc redo chưa tới standby do network/destination lỗi.

Query kiểm tra:

~~~sql
SELECT name,
       value,
       unit,
       time_computed,
       datum_time
FROM v$dataguard_stats
WHERE name IN (
    'transport lag',
    'apply lag',
    'apply finish time'
);
~~~

Xem destination:

~~~sql
SELECT dest_id,
       status,
       error,
       destination
FROM v$archive_dest_status
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
~~~

Giá trị lag cần được đọc cùng TIME_COMPUTED và DATUM_TIME. Một giá trị cũ không phải số đo realtime đáng tin cậy.

### 5.5. Protection modes

Data Guard có các protection mode chính:

- **Maximum Protection:** ưu tiên không mất dữ liệu đã commit trong failure assumptions; yêu cầu synchronous redo transport và có thể ảnh hưởng availability khi không thể bảo vệ redo theo yêu cầu.
- **Maximum Availability:** ưu tiên zero data loss trong điều kiện standby có thể đáp ứng; khi lỗi kết nối theo cơ chế được thiết kế, primary có thể tiếp tục ở mức protection thấp hơn tùy tình huống.
- **Maximum Performance:** thường dùng asynchronous transport để giảm ảnh hưởng latency lên primary; có thể mất redo chưa truyền tới standby trong sự cố.

Lựa chọn phụ thuộc RPO, network latency, khoảng cách site, băng thông và khả năng chịu gián đoạn. Synchronous transport qua khoảng cách xa có thể làm tăng commit latency.

Không chọn mode chỉ theo tên “maximum”. Kiểm tra protection level thực tế:

~~~sql
SELECT protection_mode,
       protection_level,
       database_role,
       switchover_status
FROM v$database;
~~~

### 5.6. Switchover và failover

- **Switchover:** chuyển role có kế hoạch, thường không mất dữ liệu khi thực hiện đúng điều kiện và standby đã đồng bộ.
- **Failover:** chuyển standby thành primary khi primary không thể tiếp tục phục vụ; có thể mất dữ liệu tùy transport/protection state.

Switchover phù hợp cho maintenance, diễn tập DR và chuyển đổi có kiểm soát. Failover là hành động khẩn cấp khi primary không thể được khôi phục trong thời gian chấp nhận.

Không chạy failover chỉ vì một probe tạm thời thất bại. Cần xác định primary thực sự không thể phục vụ, tránh split-brain và bảo đảm một primary duy nhất được phép nhận ghi.

### 5.7. Data Guard Broker

Broker quản lý cấu hình Data Guard và hỗ trợ giám sát/chuyển role.

Lệnh quan sát:

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE '<db_unique_name>';
DGMGRL> VALIDATE DATABASE VERBOSE '<db_unique_name>';
~~~

Cú pháp và output phụ thuộc release. Broker không thay thế monitoring của storage, network, application service và backup.

### 5.8. Active Data Guard và read-only standby

Một standby có thể được mở read-only trong các cấu hình được hỗ trợ. Việc vừa mở read-only vừa apply redo realtime (Active Data Guard) là tính năng có yêu cầu option/license riêng theo Oracle contract.

Không giả định chỉ cần mở standby READ ONLY là mọi khả năng query while apply đều có sẵn. Kiểm tra licensing, version và trạng thái apply.

Read workload trên standby có thể giảm tải primary nhưng cần đánh giá:

- Apply lag và độ mới dữ liệu.
- Query workload gây tranh chấp I/O/CPU với apply.
- Service routing và read-only enforcement.
- Transaction semantics và read-after-write consistency.
- License và feature restrictions.

## 6. Backup và recovery với RMAN: lớp bảo vệ độc lập

RMAN backup/restore giải quyết mục tiêu khác với RAC và Data Guard.

- RAC giúp tiếp tục hoạt động khi một số node/instance lỗi.
- Data Guard giúp chuyển sang database khác khi primary/site lỗi.
- RMAN giúp khôi phục database/datafile/control file hoặc point-in-time state khi cần.

Data Guard standby có thể nhận cả thao tác xóa nhầm hoặc dữ liệu bị corrupt logic nếu redo được apply. Do đó standby không phải bản backup độc lập.

### 6.1. Backup strategy

Một backup strategy cần xác định:

- Full/incremental backup schedule.
- Archived redo log backup frequency.
- Control file/SPFILE autobackup.
- Retention policy.
- Offsite/immutable copy.
- Encryption và key management.
- Restore validation và test.
- RPO/RTO thực tế.

Ví dụ kiểm tra inventory:

~~~text
RMAN> SHOW ALL;
RMAN> LIST BACKUP SUMMARY;
RMAN> REPORT NEED BACKUP;
~~~

### 6.2. Restore validation

~~~text
RMAN> RESTORE DATABASE VALIDATE;
~~~

Validate giúp kiểm tra khả năng đọc các backup cần thiết theo phạm vi lệnh. Nó không thay thế restore test hoàn chỉnh sang môi trường riêng.

Để biết RTO thực tế, phải thực hiện restore/recover test và đo:

- Thời gian chuẩn bị host/storage.
- Restore datafiles.
- Apply archived logs.
- Open database.
- Start services.
- Application validation.
- Business reconciliation.

### 6.3. Logical corruption và human error

Nếu user xóa nhầm dữ liệu, Data Guard thường replicate thao tác đó. RAC cũng cùng truy cập database đã bị thay đổi. Cần dùng:

- Flashback Query/Flashback Table nếu còn đủ undo và điều kiện phù hợp.
- Flashback Database nếu có flashback logs và restore point/retention phù hợp.
- RMAN point-in-time recovery.
- Export/backup hoặc logical recovery theo ứng dụng.

Không dùng standby failover như cách khôi phục dữ liệu đã bị xóa nhầm.

### 6.4. Immutable và isolated backup

Để chống ransomware hoặc compromise quyền quản trị:

- Giữ bản sao backup ở failure domain khác.
- Dùng immutable/object lock hoặc offline media theo policy.
- Tách credential backup khỏi credential production.
- Giới hạn quyền xóa backup.
- Bảo vệ recovery catalog và encryption keys.
- Diễn tập restore từ bản offsite.

## 7. Scalability: mở rộng năng lực xử lý

Scalability trả lời câu hỏi: khi workload tăng, hệ thống có thể xử lý thêm công việc với chi phí và độ trễ chấp nhận được không?

### 7.1. Vertical scaling — Scale-up

Scale-up tăng tài nguyên của một server/database:

- Thêm CPU core.
- Tăng RAM.
- Tăng storage IOPS/throughput.
- Tăng network bandwidth.
- Nâng cấp CPU/storage generation.

Ưu điểm:

- Kiến trúc đơn giản hơn.
- Không phải phân phối dữ liệu hoặc request giữa nhiều node ở tầng ứng dụng.
- Một số workload có thể hưởng lợi ngay nếu đang thiếu đúng tài nguyên.

Giới hạn:

- Phần cứng có trần.
- Chi phí tăng nhanh ở cấu hình lớn.
- Có thể tạo single failure domain lớn.
- Không giải quyết lỗi site hoặc logic corruption.
- Workload có thể bị giới hạn bởi lock, SQL plan hoặc serialization thay vì CPU/RAM.

### 7.2. Horizontal scaling — Scale-out

Scale-out thêm node/instance/service để xử lý workload song song.

Trong Oracle có thể gặp các mô hình:

- RAC nhiều instance trên một database.
- Sharding nhiều database theo shard key.
- Read replicas/standby cho read workload trong cấu hình hỗ trợ.
- Nhiều application server/connection pool.
- Partitioning để quản lý và truy cập tập dữ liệu lớn hiệu quả hơn.

Scale-out có thêm chi phí:

- Network/interconnect.
- Coordination và distributed transactions.
- Data placement và routing.
- Consistency và failover logic.
- Operational complexity.
- Monitoring và capacity balancing.

Thêm node không đảm bảo throughput tăng tuyến tính. Nếu bottleneck nằm ở một hot block, storage array, sequence contention hoặc một SQL không hiệu quả, thêm node có thể không giải quyết được.

### 7.3. RAC vừa hỗ trợ HA vừa có thể hỗ trợ scale-out

RAC có thể phân phối workload giữa nhiều instance và tăng năng lực xử lý khi workload có thể chạy song song trên các node.

Tuy nhiên, scale-out RAC phụ thuộc:

- Workload có đủ độc lập giữa session/transaction không.
- Global cache traffic.
- Interconnect bandwidth/latency.
- Shared storage throughput.
- Service placement và load balancing.
- CPU/memory capacity mỗi node.
- Hot blocks, sequence/index contention.
- License và cấu hình triển khai.

Một workload có nhiều truy cập vào cùng block hoặc cùng row có thể gặp contention mạnh hơn khi thêm instance.

### 7.4. Sharding

Oracle Sharding phân phối dữ liệu qua nhiều database shard theo shard key, nhằm mở rộng capacity và workload phân tán.

Ưu điểm:

- Mỗi shard quản lý một phần dữ liệu.
- Có thể scale-out bằng cách thêm shard.
- Workload theo shard key có thể định tuyến tới database chứa dữ liệu.
- Có thể giảm một số điểm nghẽn tập trung.

Thách thức:

- Chọn shard key và phân bố dữ liệu.
- Hot shard/skew.
- Cross-shard query và transaction.
- Rebalancing.
- Global uniqueness và sequence strategy.
- Backup/DR từng shard và catalog/configuration.
- Application routing và failure handling.

Sharding không tự động làm mọi query nhanh hơn. Query không có shard key có thể phải fan-out tới nhiều shard.

### 7.5. Partitioning không đồng nghĩa sharding

Partitioning chia bảng/index trong một database thành các partition để quản lý, pruning, maintenance và một số access pattern hiệu quả hơn.

Sharding phân phối dữ liệu qua nhiều database độc lập.

| Partitioning | Sharding |
|---|---|
| Chia object trong database | Chia dữ liệu qua nhiều database |
| Cùng database identity/transaction domain | Nhiều shard/database |
| Hỗ trợ partition pruning và maintenance | Hỗ trợ phân phối capacity |
| Không tự loại bỏ giới hạn một database | Có thể mở rộng qua nhiều database |
| Không tự tạo DR | Cần thiết kế HA/DR cho từng shard và metadata |

## 8. Scale read và scale write

Không phải mọi workload đều mở rộng theo cùng cách.

### 8.1. Read scaling

Các hướng phổ biến:

- Tối ưu SQL và index.
- Cache kết quả hoặc dữ liệu phù hợp.
- Dùng read-only standby khi cấu hình và license cho phép.
- Phân tách reporting workload.
- Dùng materialized views/summary tables.
- Partitioning và pruning.
- Sharding theo dữ liệu/query pattern.

Read scaling cần xem consistency. Một standby asynchronous có thể trả dữ liệu trễ so với primary. Nếu người dùng vừa ghi xong rồi đọc lại ngay, cần route về primary hoặc có cơ chế bảo đảm read-after-write.

### 8.2. Write scaling

Write scaling khó hơn vì ghi thường cần phối hợp transaction và uniqueness.

Các hướng:

- Giảm transaction duration và lock contention.
- Tối ưu index và redo generation.
- Partitioning để giảm contention/maintenance khi phù hợp.
- RAC khi workload phù hợp và contention xuyên instance chấp nhận được.
- Sharding để phân tán write theo shard key.
- Queue/batch để hấp thụ burst.
- Thiết kế idempotent operations và asynchronous processing.

Thêm read replica không tăng khả năng commit write trên primary. Một hệ thống có read scaling tốt vẫn có thể write bottleneck.

## 9. Load balancing không phải failover

Load balancing phân phối workload giữa các instance/service/node đang hoạt động. Failover chuyển workload khỏi thành phần không còn hoạt động.

| Khái niệm | Mục tiêu | Ví dụ |
|---|---|---|
| Load balancing | Tránh một node quá tải khi node khác còn capacity | RAC service connection balancing |
| Failover | Tiếp tục hoạt động sau lỗi | Service relocate, Data Guard role transition |
| Retry | Thực hiện lại request khi lỗi tạm thời | Application retry với backoff |
| Replay | Khôi phục một request/database interaction theo cơ chế hỗ trợ | Application Continuity |
| Scaling | Tăng tổng năng lực xử lý | Thêm CPU, RAC node, shard |

Một load balancer có thể tiếp tục gửi traffic tới node không khỏe nếu health check hoặc service registration sai. Failover không đảm bảo request đang chạy được hoàn tất; transaction có thể rollback hoặc client cần xử lý kết quả không xác định.

### 9.1. Retry và idempotency

Khi connection đứt trong lúc COMMIT, client có thể không biết transaction đã commit hay chưa. Retry mù có thể tạo giao dịch trùng.

Ứng dụng cần:

- Idempotency key cho thao tác nghiệp vụ phù hợp.
- Unique constraint hoặc deduplication.
- Xác định transaction outcome khi reconnect.
- Retry có giới hạn và exponential backoff.
- Phân loại lỗi retryable/non-retryable.
- Không retry thao tác có external side effect nếu không có cơ chế chống trùng.

### 9.2. Connection pool

Connection pool cần xử lý:

- Dead connection detection.
- FAN/FCF nếu được hỗ trợ.
- Connection validation.
- Reconnect storm.
- Pool size và database session capacity.
- Timeout, retry và backoff.
- Service role/instance preference.

Pool quá lớn có thể làm database quá tải; pool quá nhỏ có thể tạo queue ở application tier. Đo connection wait time cùng database active sessions.

## 10. Kết hợp HA, DR và scalability

Một kiến trúc doanh nghiệp có thể kết hợp các lớp:

~~~text
                    Applications
                         |
                 Database service
                         |
              Primary RAC cluster
             +-----------+-----------+
             |                       |
          Node A                  Node B
         Instance                Instance
             |                       |
             +----------+------------+
                        |
                  Primary storage
                        |
                 Redo transport
                        |
                Separate DR site
                        |
              Standby database
              (Data Guard)
                        |
                Standby storage

         Independent RMAN backup copies
              /                  \
       Local backup         Offsite/immutable
       repository             repository
~~~

Vai trò:

- RAC: chịu lỗi node/instance và phân phối workload trong primary site.
- Data Guard: duy trì standby tại failure domain khác và hỗ trợ role transition.
- RMAN: cung cấp backup/recovery cho media failure, logical error và PITR.
- Application services: định tuyến connection và phản ứng với failover.
- Monitoring/runbooks: phát hiện, quyết định, thực hiện và xác nhận phục hồi.

### 10.1. Không phải mọi hệ thống đều cần RAC

Một database đơn instance có thể đạt HA phù hợp bằng Oracle Restart, storage redundancy, service monitoring và Data Guard tới site khác, tùy RTO/RPO. RAC tăng chi phí license, hạ tầng và vận hành.

Chọn theo failure model và business objective, không theo việc công nghệ có sẵn.

### 10.2. Data Guard standby có thể có RAC hay không?

Primary và standby có thể có topology khác nhau trong các cấu hình được Oracle hỗ trợ. Ví dụ primary RAC và standby single-instance, hoặc cả hai RAC. Cần xác nhận support matrix, capacity khi failover và license.

Nếu standby chỉ có một server nhỏ, khi failover workload production đầy đủ có thể không đáp ứng SLA. DR site phải được sizing cho mức tải cần khôi phục, không chỉ cho khả năng nhận redo.

### 10.3. Backup độc lập vẫn cần thiết

Một kiến trúc RAC + Data Guard vẫn cần RMAN backup và bản sao tách biệt. RAC và Data Guard bảo vệ availability/replication; chúng không bảo đảm có thể quay lại trạng thái trước một thao tác xóa nhầm đã được replicate.

## 11. Chọn kiến trúc theo yêu cầu

| Nhu cầu | Hướng kiến trúc để đánh giá |
|---|---|
| Chịu lỗi instance/node trong một site | RAC hoặc phương án HA phù hợp với workload |
| Chịu lỗi toàn site | Data Guard tới site khác |
| Khôi phục sau xóa nhầm/corruption | RMAN PITR, Flashback hoặc logical recovery phù hợp |
| RPO thấp | Data Guard protection mode/transport phù hợp, backup archived logs |
| RTO rất thấp | Tự động hóa failover, service/client failover, diễn tập |
| Read workload lớn | SQL tuning, cache, reporting standby hoặc sharding |
| Write workload tăng | Tối ưu transaction, partitioning, RAC phù hợp hoặc sharding |
| Dữ liệu tăng rất lớn | Partitioning, archival, sharding hoặc data lifecycle |
| Chống ransomware | Immutable/offline backup, tách credential, recovery test |
| Bảo trì không downtime dài | Rolling maintenance/RAC/Data Guard theo support và runbook |

### 11.1. Ví dụ lựa chọn

**Hệ thống A: ứng dụng nội bộ, tải vừa, chấp nhận RTO 4 giờ và RPO 24 giờ**

Có thể dùng single-instance database, RMAN backup định kỳ, archived log backup theo nhu cầu và restore test. RAC có thể không cần thiết nếu downtime budget và chi phí không biện minh.

**Hệ thống B: giao dịch quan trọng, cần RTO vài phút, RPO thấp**

Có thể đánh giá RAC trong primary site, Data Guard tới DR site với protection mode phù hợp, application service failover và backup độc lập. Cần diễn tập cả lỗi node lẫn mất site.

**Hệ thống C: workload đọc tăng mạnh, ghi vừa phải**

Có thể tối ưu SQL/index trước, phân tách reporting, dùng standby read-only trong điều kiện được hỗ trợ/licensed hoặc cache/materialized view. Kiểm soát lag và read-after-write.

**Hệ thống D: write throughput tăng theo nhiều tenant độc lập**

Có thể đánh giá sharding theo tenant key nếu query và transaction chủ yếu nằm trong tenant. Phải tính cross-tenant reporting, global uniqueness, rebalancing và DR từng shard.

## 12. Đo capacity và khả năng mở rộng

Scalability cần được chứng minh bằng load test và capacity test, không chỉ dựa vào số CPU/node.

### 12.1. Các metric cần theo dõi

- Transactions/sec và requests/sec.
- p50/p95/p99 latency.
- CPU utilization và CPU time per transaction.
- Active sessions và connection pool wait.
- Buffer gets per transaction.
- Physical I/O latency, IOPS và throughput.
- Redo bytes/sec và log file sync.
- Global cache waits trong RAC.
- Interconnect throughput/latency.
- Data Guard transport/apply lag.
- TEMP/PGA/UNDO usage.
- Error, timeout, retry và deadlock rate.

### 12.2. Throughput saturation

Khi tăng concurrency, throughput thường tăng tới một điểm rồi chậm lại hoặc giảm vì contention/resource saturation.

Dấu hiệu saturation:

- CPU gần mức tối đa kéo dài.
- p95/p99 tăng nhanh.
- Connection pool queue tăng.
- Lock/latch/global cache waits tăng.
- I/O latency tăng.
- Throughput không tăng dù concurrency tăng.
- Error/timeout/retry tăng.

Thêm node chỉ giúp nếu bottleneck có thể phân phối. Nếu bottleneck là một hot row, một sequence, một storage array hoặc một external dependency, scale-out có thể không hiệu quả.

### 12.3. Headroom và N+1 capacity

HA cluster phải còn đủ capacity khi một node mất. Nếu hai node đều chạy 90% CPU trong trạng thái bình thường, mất một node có thể làm node còn lại quá tải.

Capacity planning cần đánh giá:

- Normal load.
- Peak load.
- Load khi một node/site bị mất.
- Batch/reporting đồng thời.
- Growth trong kỳ dự báo.
- Maintenance window.
- Failover/recovery overhead.

N+1 là một nguyên tắc capacity: sau khi mất một thành phần, hệ thống còn đủ tài nguyên để phục vụ mức tải yêu cầu. Không phải mọi hệ thống cần N+1 tuyệt đối, nhưng phải biết degradation mode.

### 12.4. Benchmark scale-out

Một quy trình thử RAC hoặc scale-out:

1. Chạy baseline trên một node/instance hoặc cấu hình hiện tại.
2. Ghi workload mix và concurrency.
3. Thêm node/instance trong môi trường test.
4. Giữ data volume, SQL, bind profile và client behavior tương đương.
5. Đo throughput, latency, CPU, I/O và interconnect.
6. Quan sát global cache waits và hot blocks.
7. Thử workload khi một node không khả dụng.
8. So sánh hiệu năng bình thường và degraded mode.

Đừng chỉ đo throughput tổng ở trạng thái tất cả node đều khỏe. HA architecture phải được đo cả khi một node bị mất.

## 13. Kiểm thử HA và DR

Một kiến trúc chỉ được xem là sẵn sàng khi quy trình failover đã được thử trong điều kiện kiểm soát.

### 13.1. Kiểm thử HA

Các tình huống có thể diễn tập trong môi trường được phê duyệt:

- Kill test process trong lab.
- Stop/restart một instance theo runbook.
- Mô phỏng mất một node.
- Di chuyển service có kế hoạch.
- Kiểm tra connection pool phát hiện và loại connection lỗi.
- Kiểm tra application retry/replay.
- Đo thời gian request phục hồi.
- Kiểm tra transaction đang chạy và transaction outcome.

Không gây lỗi node hoặc shutdown instance production chỉ để test nếu chưa có change approval và kế hoạch tác động.

### 13.2. Kiểm thử DR

- Switchover có kế hoạch.
- Failover simulation theo runbook trong môi trường test.
- Mất network transport.
- Standby apply lag.
- Archive gap.
- Primary unavailable.
- Client reconnect tới standby service sau role transition.
- Reinstatement/rebuild former primary.
- Backup restore khi cả primary và standby không dùng được.

Đo RTO/RPO thực tế và lưu bằng chứng. Một lần switchover thành công không chứng minh mọi failure scenario đều được xử lý.

### 13.3. Kiểm thử backup recovery

- Restore database từ backup.
- Recover tới SCN/time.
- Restore control file khi cần.
- Khôi phục encryption wallet/key.
- Restore từ offsite/immutable copy.
- Kiểm tra dữ liệu nghiệp vụ và application startup.

Backup job success không đủ. Cần kiểm tra khả năng restore trong failure domain khác.

### 13.4. Kiểm thử scalability

- Tăng request rate từng bước.
- Tăng concurrency.
- Thử peak/burst.
- Thử một node down.
- Thử standby lag/read routing.
- Kiểm tra connection pool behavior.
- Đo saturation point và headroom.
- Kiểm tra dữ liệu và kết quả nghiệp vụ.

## 14. Những trade-off quan trọng

### 14.1. Synchronous transport và latency

Synchronous redo transport có thể giảm data loss nhưng tăng độ nhạy với network latency. Khoảng cách site và chất lượng network ảnh hưởng commit latency.

Đặt DR site quá xa có thể khiến synchronous protection không khả thi cho SLA latency. Chọn mode theo yêu cầu nghiệp vụ và đo trên network thật.

### 14.2. Asynchronous transport và data loss exposure

Asynchronous transport giảm ảnh hưởng commit latency nhưng có thể để lại redo chưa được ship khi primary mất đột ngột. Transport lag là một phần của RPO exposure.

Cần monitoring, network capacity và runbook xử lý lag.

### 14.3. RAC và shared storage/interconnect

RAC tăng khả năng chịu lỗi node nhưng tạo dependency vào cluster interconnect, shared storage, voting/cluster infrastructure và clusterware. Những thành phần này cần redundancy và monitoring riêng.

### 14.4. Standby read workload và apply lag

Read query nặng trên standby có thể cạnh tranh tài nguyên với redo apply. Nếu standby lag tăng, ứng dụng đọc dữ liệu stale hơn.

Cần giới hạn/reporting window, workload service riêng và chính sách route primary cho read-after-write.

### 14.5. Scale-out và distributed complexity

Sharding có thể tăng capacity nhưng làm phức tạp query, transaction, backup, schema changes, monitoring và incident response. Chi phí vận hành cần được tính trong tổng chi phí sở hữu.

## 15. Các query quan sát thường dùng

### 15.1. Database role và open mode

~~~sql
SELECT name,
       db_unique_name,
       database_role,
       open_mode,
       protection_mode,
       protection_level,
       switchover_status
FROM v$database;
~~~

### 15.2. Instance status

~~~sql
SELECT inst_id,
       instance_name,
       host_name,
       status,
       startup_time
FROM gv$instance
ORDER BY inst_id;
~~~

Trong single-instance có thể dùng V$INSTANCE.

### 15.3. RAC services

~~~sql
SELECT inst_id,
       name,
       network_name,
       con_id
FROM gv$services
ORDER BY name, inst_id;
~~~

### 15.4. Data Guard lag

~~~sql
SELECT name,
       value,
       unit,
       time_computed,
       datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag');
~~~

### 15.5. Resource utilization

~~~sql
SELECT resource_name,
       current_utilization,
       max_utilization,
       limit_value
FROM v$resource_limit
WHERE resource_name IN ('processes', 'sessions', 'transactions')
ORDER BY resource_name;
~~~

### 15.6. Top SQL

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       ROUND(elapsed_time / 1e6, 2) AS elapsed_seconds,
       ROUND(cpu_time / 1e6, 2) AS cpu_seconds,
       buffer_gets,
       disk_reads,
       rows_processed
FROM v$sql
WHERE executions > 0
ORDER BY elapsed_time DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Các counter V$SQL thường tích lũy theo child cursor; dùng snapshot/delta hoặc công cụ execution-level để đánh giá một lần chạy. Với RAC, dùng GV$ khi cần xem mọi instance.

## 16. Runbook chuyển role và phục hồi dịch vụ

Mỗi tổ chức cần runbook chi tiết theo topology, Oracle release, Broker, client driver và approval policy. Các bước dưới đây là khung quy trình, không phải lệnh failover dùng trực tiếp cho production.

### 16.1. Precheck

- Xác nhận primary DB_UNIQUE_NAME, DBID và role.
- Xác nhận standby identity, role và open mode.
- Xác nhận transport/apply lag, archive gap và protection level.
- Xác nhận primary thực sự không thể phục vụ nếu là failover.
- Xác định có nguy cơ primary cũ vẫn nhận write hay không.
- Xác nhận người phê duyệt và incident/change.
- Xác nhận service/client routing và DNS/network.
- Ghi SCN/sequence và trạng thái trước thao tác.
- Xác nhận backup/recovery option nếu role transition thất bại.

### 16.2. Chọn switchover hay failover

- Switchover khi primary còn hoạt động và có thể phối hợp chuyển role.
- Failover khi primary không thể tiếp tục và thời gian chờ vượt ngưỡng business.
- Không dùng failover để xử lý một lỗi application đơn lẻ nếu primary database vẫn khỏe.
- Không để primary cũ và standby mới cùng nhận ghi.

### 16.3. Postcheck

- Standby mới trở thành primary với role/open mode đúng.
- Database service được mở/đăng ký ở nơi đúng.
- Application reconnect và query/write smoke test thành công.
- RPO thực tế được ghi lại.
- Error rate, latency và throughput trở về mức chấp nhận.
- Monitoring, backup và redo transport được thiết lập lại.
- Former primary được reinstate/rebuild theo quy trình.
- Incident timeline và root cause được lưu.

## 17. Ma trận lựa chọn theo mục tiêu

| Yêu cầu | HA | DR | Scalability |
|---|---|---|---|
| Một instance lỗi | RAC/service failover | Không nhất thiết | Không phải mục tiêu chính |
| Mất một node | RAC có thể tiếp tục | Không nhất thiết | RAC có thể phân phối tải |
| Mất toàn site | Không đủ nếu chỉ nội site | Data Guard hoặc restore ở site khác | Không giải quyết |
| Xóa nhầm dữ liệu | Không giải quyết | Standby có thể replicate lỗi | Không giải quyết |
| Tăng read requests | Load balancing/cache/standby read | Standby có thể hỗ trợ read trong cấu hình phù hợp | Read scaling |
| Tăng write requests | HA giúp continuity, không tự tăng write capacity | DR không tăng write capacity primary | RAC phù hợp hoặc sharding/scale-up |
| Cần PITR | Không | Standby không thay backup | Không |
| Cần giảm latency | Service routing và tối ưu | Khoảng cách standby có thể tăng latency | Scale tài nguyên/kiến trúc theo bottleneck |

## 18. Bài thực hành

Thực hiện trên lab hoặc môi trường được phê duyệt.

### Bài 1 — Xác định failure domain

Vẽ topology hiện tại: application, service, node, instance, storage, site, standby, backup và network. Đánh dấu thành phần dùng chung có thể gây lỗi đồng thời.

### Bài 2 — Viết RTO/RPO

Chọn một ứng dụng, xác định RTO/RPO và tính downtime budget tương ứng. Ghi rõ failure scenario mà cam kết áp dụng.

### Bài 3 — RAC service

Trong lab RAC, xem service placement và status. Thực hiện planned service relocation theo tài liệu release và đo client reconnection.

### Bài 4 — Instance failure

Trong lab, mô phỏng một instance không khả dụng. Quan sát service, surviving instance, active session và application behavior.

### Bài 5 — Data Guard lag

Tạo workload redo trong lab. Theo dõi transport lag và apply lag. Phân biệt tình huống transport chậm với apply chậm.

### Bài 6 — Switchover

Thực hiện planned switchover theo runbook lab. Đo thời gian role transition, service start và application recovery.

### Bài 7 — Failover

Trong lab riêng, mô phỏng primary unavailable và thực hiện failover theo tài liệu. Ghi redo chưa apply, RPO thực tế và các bước reinstate/rebuild.

### Bài 8 — RMAN restore

Restore database sang host/schema test từ backup và archived logs. Đo thời gian restore/recover/open/validate.

### Bài 9 — Logical error

Mô phỏng thao tác xóa nhầm trong lab. So sánh khả năng của standby với Flashback/PITR để hiểu vì sao replication không thay backup.

### Bài 10 — Scale-up

Tăng tài nguyên CPU/memory/storage trong môi trường test. Chạy cùng workload trước/sau và đo throughput, p95, CPU và I/O.

### Bài 11 — RAC scale-out

So sánh workload trên một node và nhiều node. Theo dõi global cache waits, interconnect, hot blocks và throughput.

### Bài 12 — Read scaling

Nếu môi trường có standby read-only phù hợp, chạy reporting workload và đo apply lag, query latency, primary load và read consistency.

### Bài 13 — Shard key

Thiết kế shard key cho bảng đơn hàng theo tenant. Xác định query local, cross-shard, uniqueness, rebalancing và DR.

### Bài 14 — Failure test report

Với mỗi thử nghiệm, ghi:
- Failure scenario.
- Expected behavior.
- Actual behavior.
- Detection time.
- Decision time.
- Recovery/failover time.
- RTO/RPO thực tế.
- Application validation.
- Data correctness.
- Follow-up action.

## 19. Checklist thiết kế và vận hành

### HA

- [ ] Xác định failure domain cần chịu được.
- [ ] Đánh giá RAC hoặc phương án HA phù hợp.
- [ ] Redundant network, storage và cluster infrastructure.
- [ ] Service được cấu hình cho workload đúng.
- [ ] Client driver/pool hỗ trợ failover behavior cần thiết.
- [ ] Retry/replay có idempotency và transaction contract.
- [ ] Capacity còn đủ khi mất một node.
- [ ] Diễn tập instance/node failure.

### DR

- [ ] Có site/failure domain độc lập.
- [ ] Chọn Data Guard hoặc backup/restore theo RTO/RPO.
- [ ] Chọn protection mode theo data loss tolerance và network latency.
- [ ] Theo dõi transport lag, apply lag, gap và datum freshness.
- [ ] Có runbook switchover/failover/reinstate.
- [ ] Service/client routing sau role transition được kiểm thử.
- [ ] Có RMAN backup độc lập, offsite/immutable khi cần.
- [ ] Restore test thực tế và đo RTO/RPO.
- [ ] Bảo vệ control file, SPFILE, wallet/keystore và recovery catalog.

### Scalability

- [ ] Xác định bottleneck trước khi scale.
- [ ] Đánh giá scale-up so với scale-out.
- [ ] Load test theo concurrency và workload mix.
- [ ] Theo dõi throughput, p95/p99, CPU, I/O và waits.
- [ ] Với RAC, theo dõi global cache/interconnect/hot blocks.
- [ ] Với sharding, kiểm tra shard key, skew và cross-shard query.
- [ ] Đánh giá read-after-write và standby lag nếu scale read.
- [ ] Kiểm tra N+1 capacity và degraded mode.
- [ ] Đánh giá license, hạ tầng và chi phí vận hành.

### Kiểm thử và quản trị

- [ ] Có RTO/RPO và SLO được business owner phê duyệt.
- [ ] Có failure scenario và expected behavior.
- [ ] Có change/incident approval cho test disruptive.
- [ ] Có telemetry từ application, database, OS và network.
- [ ] Có bằng chứng và timeline sau mỗi diễn tập.
- [ ] Có owner cho follow-up và runbook.
- [ ] Review sau patch, topology change và incident lớn.

## 20. Ghi nhớ cốt lõi

- HA duy trì dịch vụ khi một số thành phần lỗi; DR khôi phục dịch vụ/dữ liệu sau khi failure domain lớn bị mất; scalability tăng capacity khi workload tăng.
- RAC chủ yếu hỗ trợ HA ở mức instance/node và có thể scale-out trong cluster; nó không thay thế DR hoặc backup.
- Data Guard duy trì standby qua redo transport/apply và hỗ trợ chuyển role; nó không bảo vệ khỏi mọi lỗi logic được replicate.
- RMAN backup/restore cung cấp khả năng phục hồi độc lập, gồm media recovery và point-in-time recovery.
- RTO là thời gian tối đa để khôi phục dịch vụ; RPO là mức dữ liệu tối đa có thể mất.
- RTO phải tính cả detection, decision, failover/restore, service/client reconnect và application validation.
- Synchronous redo transport có thể giảm data loss nhưng nhạy với network latency; asynchronous transport có thể để lại redo chưa ship.
- Switchover là chuyển role có kế hoạch; failover là chuyển role khẩn cấp khi primary không thể tiếp tục.
- Load balancing phân phối tải; failover chuyển tải khỏi thành phần lỗi; retry/replay cần transaction semantics và idempotency.
- Scale-up tăng tài nguyên một hệ thống; scale-out phân phối workload qua nhiều node/database; không có cách nào tự sửa SQL kém hiệu quả hoặc hot block.
- RAC scale-out phụ thuộc Cache Fusion, interconnect, shared storage và workload distribution.
- Sharding có thể mở rộng write/read qua nhiều database nhưng tăng độ phức tạp routing, transaction và operation.
- Partitioning là chia object trong một database; sharding là phân phối dữ liệu qua nhiều database.
- Standby read workload có thể bị giới hạn bởi apply lag và license; read-after-write cần được thiết kế.
- HA/DR không thay thế immutable/offsite backup; replication có thể replicate cả thao tác xóa nhầm hoặc corruption logic.
- Thiết kế phải đo cả normal mode lẫn degraded mode khi mất node/site.
- Chọn công nghệ theo failure domain, RTO/RPO, workload, capacity, license và khả năng vận hành; diễn tập trước khi dựa vào cam kết.

### Tài liệu Oracle nên đối chiếu

- [Oracle Real Application Clusters Administration and Deployment Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/racad/) — RAC architecture, services, Cache Fusion, Clusterware and operations.
- [Oracle Data Guard Concepts and Administration](https://docs.oracle.com/en/database/oracle/oracle-database/19/sbydb/) — Physical/logical standby, redo transport/apply, protection modes, switchover and failover.
- [Oracle Database Backup and Recovery User's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/) — RMAN backup, restore, recovery and validation.
- [Oracle Database High Availability Overview](https://docs.oracle.com/en/database/oracle/oracle-database/19/haovw/) — Oracle HA architecture and solution selection.
- [Oracle Database Sharding Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/shard/) — Shard architecture, shard keys, routing and scaling.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — V$DATABASE, V$INSTANCE, V$DATAGUARD_STATS, GV$ services and performance views.
- [Oracle Database Licensing Information User Manual](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/) — RAC, Active Data Guard and other option/feature licensing.

Supported topology, failover behavior, driver capabilities and licensing vary by Oracle release and contract. Confirm the deployed version, platform support matrix and license entitlement; test instance failure, site failover, client reconnect, backup restore and degraded-mode capacity in a representative non-production environment.

