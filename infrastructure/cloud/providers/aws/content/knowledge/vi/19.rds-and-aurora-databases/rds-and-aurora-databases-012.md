# Bảo trì, nâng cấp phiên bản và triển khai database blue/green

> **Chương:** Cơ sở dữ liệu RDS và Aurora  
> **Học phần:** `CLOUD_PROVIDERS_AWS` — khám phá AWS từ Region/AZ, IAM, VPC, tính toán và lưu trữ tới cơ sở dữ liệu, tích hợp và serverless; thực hành lựa chọn dịch vụ, xây hệ thống an toàn, giám sát, phục hồi và kiểm soát chi phí.

Một ứng dụng Java Spring Boot đang sử dụng PostgreSQL trong **Amazon RDS**. Database hoạt động ổn định nhiều tháng, nhưng phiên bản engine sắp hết vòng đời hỗ trợ, bản vá bảo mật cần được áp dụng và ứng dụng có ràng buộc thư viện JDBC, extension, stored procedures. Chỉ cần chọn “Upgrade” trong Console là có thể khiến database phải restart, kết nối trong pool bị cắt, câu SQL không còn tương thích hoặc thời gian ngừng ghi kéo dài ngoài dự kiến.

**Amazon RDS** và **Amazon Aurora** giảm công quản trị hạ tầng database nhưng **không loại bỏ trách nhiệm lập kế hoạch bảo trì, kiểm thử nâng cấp, quản lý phiên bản, sao lưu và khôi phục**. Một kỹ thuật hữu ích là **Blue/Green Deployments**: tạo môi trường *green* đồng bộ từ production *blue*, thử phiên bản/cấu hình mới tại green và thực hiện **switchover có kiểm tra an toàn** khi sẵn sàng.

Bài này trình bày hành trình từ **bảo trì định kỳ → nâng cấp minor/major → chạy thử blue/green → switchover → hậu kiểm → xử lý sự cố**. Nội dung dành cho cả **RDS DB instances** và **Aurora DB clusters**, có chỉ rõ chỗ khác nhau. Tên tài nguyên, ARN, endpoint, tài khoản và số liệu trong ví dụ đều là giả định; không chạy lệnh thay đổi database production khi chưa có phê duyệt và runbook.

**Lưu ý về thời điểm và hỗ trợ:** Danh sách engine, phiên bản, Region, tính năng Aurora Global Database, RDS Proxy, replication method và hạn chế Blue/Green thay đổi theo thời gian. Luôn kiểm tra tài liệu AWS của **đúng engine, version và Region** trước khi triển khai. Những số downtime hoặc timeout được nhắc đến là kỳ vọng/cấu hình, không phải SLA bất biến.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Phân biệt **system maintenance**, **engine minor/major version upgrades**, **parameter/option group changes** và **DB instance class/storage changes**.
2. Giải thích **preferred maintenance window**, pending maintenance, `ApplyImmediately`, auto minor version upgrade, reboot và ảnh hưởng của **Multi-AZ**.
3. Lập kế hoạch nâng cấp dựa trên compatibility matrix, extension, JDBC driver, schema, performance baseline và kế hoạch rollback/restore.
4. Mô tả Blue/Green Deployments: **blue đang phục vụ production; green là staging đồng bộ**; giải thích replication lag, guardrails, switchover và endpoint changes.
5. Nhận biết những hạn chế quan trọng của **RDS for MySQL/MariaDB/PostgreSQL** và **Aurora MySQL/PostgreSQL**, đặc biệt **PostgreSQL logical replication không đồng bộ DDL/DCL như DML**.
6. Thiết kế runbook cho **preflight, rehearsal, switchover, post-cutover** và giải pháp khôi phục khi xảy ra lỗi.
7. Sử dụng AWS CLI **chỉ đọc** để kiểm tra cấu hình database, engine upgrade targets, pending maintenance, blue/green deployment và CloudWatch.
8. Đánh giá tác động đến **RPO/RTO, lịch sử PITR, chi phí nhân đôi môi trường, IAM, bảo mật và ứng dụng Java**.

## 2. Tại sao database maintenance luôn cần kế hoạch?

Database là hệ thống **stateful**: nếu có thay đổi về engine hoặc nơi ghi dữ liệu, không thể khôi phục bằng cách đơn giản khởi động thêm container như nhiều stateless web services.

~~~mermaid
flowchart LR
  USERS["Users"] --> ALB["ALB / API"]
  ALB --> APPS["Java Spring Boot\nECS / EKS / EC2"]
  APPS --> POOL["JDBC / HikariCP\nconnection pools"]
  POOL --> PROXY["RDS Proxy (nếu dùng)"]
  PROXY --> DB["RDS/Aurora writer"]
  DB --> ST["Persistent database data"]
  DB -.-> MON["CloudWatch / Database Insights"]
  DB -.-> BACK["Automated backup / snapshot"]
~~~

Khi database restart hoặc writer endpoint đổi đích, chuỗi ảnh hưởng có thể gồm:

- TCP connections cũ bị đóng, các transaction đang chạy phải retry hoặc được rollback theo engine.
- Connection pool giữ stale connections, ứng dụng phát sinh `SQLTransientConnectionException` hoặc timeout.
- DNS/JVM/client cache địa chỉ đích cũ, request tiếp tục đến node sai trong thời gian chuyển đổi.
- Read replicas/replication lag, replication slots, CDC hoặc job ETL có thể cần cấu hình lại.
- Một thao tác schema không tương thích khiến bản ứng dụng hiện tại đọc/ghi sai.
- Backup/PITR hoặc cross-account audit có thể tham chiếu **resource IDs** thay vì tên hiển thị sau switchover.

Vì vậy, mục tiêu không chỉ là “nâng cấp thành công” mà là:

~~~text
Database version mới được hỗ trợ và an toàn
        + dữ liệu toàn vẹn
        + ứng dụng tương thích
        + thời gian gián đoạn nằm trong SLO
        + khả năng phục hồi và kiểm toán được
~~~

### 2.1. Bốn câu hỏi đặt trước khi thay đổi

| Câu hỏi | Ví dụ trả lời cần có |
| --- | --- |
| **Thay đổi cái gì?** | Aurora PostgreSQL minor patch hay major PostgreSQL upgrade? |
| **Phạm vi lỗi?** | Single-AZ instance, RDS Multi-AZ instance hay Aurora cluster với writer/readers? |
| **Gián đoạn chấp nhận được?** | RTO 5 phút, write outage dưới 60 giây, p99 API dưới 1 giây sau phục hồi |
| **Quay lại/khôi phục thế nào?** | Giữ blue, snapshot, PITR, export, restore test và chiến lược dữ liệu phát sinh sau cutover |

Đặc biệt, **không thể định nghĩa rollback thật nếu chưa trả lời câu hỏi “dữ liệu ghi sau khi switchover đi đâu?”**. Đây là khác biệt lớn nhất giữa blue/green cho ứng dụng stateless và database stateful.

## 3. Các loại thay đổi trong Amazon RDS và Aurora

| Thay đổi | Ví dụ | Có thể gây gián đoạn? | Điểm kiểm tra |
| --- | --- | --- | --- |
| **System/host maintenance** | OS patch, security update, host replacement | Có thể cần reboot hoặc failover | Pending maintenance, event, Multi-AZ |
| **Minor engine upgrade** | PostgreSQL 15.x → 15.y theo target hỗ trợ | Thường cần restart; có thể outage | Release notes, bug fixes, extensions |
| **Major engine upgrade** | PostgreSQL 15 → 16, Aurora major family | Có thay đổi compatibility; downtime có thể lớn | Upgrade path, prechecks, app schema |
| **Parameter group** | `max_connections`, logging, extensions | Dynamic hoặc pending-reboot | Parameter apply type, pending reboot |
| **Option group (RDS engine phù hợp)** | Các engine-specific options | Có thể có ảnh hưởng engine/OS | Option compatibility theo engine/version |
| **Instance class** | Tăng vCPU/RAM | Có thể restart/failover | CPU, memory, EBS throughput, DNS |
| **Storage configuration** | IOPS, storage type, size | Theo thao tác được hỗ trợ; có thể ảnh hưởng I/O | Limits và khả năng sửa online |
| **Certificate/CA rotation** | Cập nhật CA cho TLS database | Client truststore có thể cần sửa; phương thức rotation quyết định outage | Driver/JVM truststore, DB cert expiry |
| **Topology** | Multi-AZ/reader/add replica | Có thể đổi endpoints/connection behavior | Quota, replication, failover |

Một nhóm thay đổi có thể được xử lý cùng maintenance window, nhưng **không suy ra rằng gom nhiều thay đổi luôn giảm downtime hoặc an toàn hơn**. Khi gặp lỗi rất khó cô lập root cause nếu vừa nâng major version, vừa đổi instance class, vừa thay CA và cập nhật ORM trong cùng một đợt.

## 4. Maintenance window, pending actions và `ApplyImmediately`

### 4.1. Preferred maintenance window là gì?

**Preferred maintenance window** là khoảng thời gian mà RDS/Aurora ưu tiên **bắt đầu** những hoạt động bảo trì liên quan, thường là một cửa sổ ít nhất khoảng 30 phút theo cấu hình dịch vụ. **Không được hiểu là AWS cam kết kết thúc mọi công việc trong 30 phút**; một thao tác lớn có thể kéo dài hơn.

~~~mermaid
flowchart LR
  A["AWS thông báo maintenance"] --> P["Pending maintenance action"]
  P --> D{"Bắt buộc / tùy chọn?\nCó thể defer?"}
  D -->|"Chủ động chọn"| NOW["Apply vào thời điểm đã lên lịch"]
  D -->|"Theo lịch dịch vụ"| W["Preferred maintenance window"]
  NOW --> I["Database maintenance\ncó thể reboot/failover"]
  W --> I
  I --> O["Kiểm tra engine / app / metrics"]
~~~

Điều cần nhớ:

- **System updates và engine updates không phải luôn cùng cơ chế áp dụng**.
- Có loại maintenance **required** với deadline; trì hoãn quá hạn có thể bị AWS áp dụng theo chính sách.
- **Maintenance window không phải “thời gian duy nhất DB có thể restart”**: failover, sự cố hạ tầng, lựa chọn `ApplyImmediately` hoặc thao tác thủ công có thể gây restart ngoài giờ đó.
- Với **Aurora**, maintenance window của **DB cluster** và với **RDS instance**, maintenance window của **DB instance** phải được kiểm tra theo resource type.
- **Pending modification** khác **pending maintenance action**; cần xem cả hai.

### 4.2. `ApplyImmediately` và chọn “next maintenance window”

Khi sửa database qua Console/API, bạn thường chọn:

- **Apply immediately:** RDS bắt đầu áp dụng thay đổi đủ điều kiện sớm, có thể gây gián đoạn ngay thay vì đợi kỳ bảo trì.
- **Apply during next maintenance window:** lưu các thay đổi vào pending modifications và áp dụng theo lịch tương ứng.

**Không hiểu “Apply immediately” là luôn không downtime hay thực hiện trong vài giây**. Tùy thao tác, RDS có thể thực hiện ngay, lên lịch công việc hoặc kết hợp nhiều pending modifications; phải xem bảng ảnh hưởng của từng loại thay đổi.

### 4.3. Pending-reboot không tự biến mất

Một số **static parameters** cần **reboot** để có hiệu lực. Khi parameter group có trạng thái **`pending-reboot`**, không nên giả định thay đổi sẽ tự áp dụng trong maintenance window kế tiếp; tùy cơ chế RDS/Aurora, có thể cần reboot rõ ràng và lên kế hoạch outage/failover.

| Tham số | Đặc điểm | Hành động đúng |
| --- | --- | --- |
| **Dynamic** | Có thể áp dụng khi database còn chạy theo hỗ trợ | Kiểm tra apply method và hiệu lực thực |
| **Static** | Cần database engine restart | Ghi nhận pending-reboot, lên lịch và kiểm thử |
| **Cluster parameter group** | Ảnh hưởng cấu hình cấp cluster/engine | Xem trạng thái theo Aurora DB cluster/instances |
| **DB instance parameter group** | Ảnh hưởng DB instance cụ thể | Kiểm tra writer/readers đều dùng group phù hợp |

### 4.4. Automatic minor version upgrades

RDS có tùy chọn **`AutoMinorVersionUpgrade`** cho nhiều engine/instance loại hỗ trợ. Khi bật, dịch vụ có thể tự lên lịch minor version upgrade **được chỉ định theo cơ chế tự động**, không nhất thiết là minor mới nhất vừa phát hành.

Kiến trúc có kiểm soát thay đổi nên ghi rõ:

1. Khi nào cho phép tự nâng minor?
2. Khi nào phải kiểm thử trước trên staging?
3. Có alert về scheduled/mandatory upgrade không?
4. Có đối chiếu engine/driver/extension compatibility không?
5. Có thực hành restore và failover không?

Ở Aurora, việc cập nhật engine và auto-minor behavior cần xem theo **cluster engine family/instance settings và khả năng engine hiện hành**; không mặc định RDS PostgreSQL và Aurora PostgreSQL áp dụng chính xác cùng một cách.

## 5. Minor version và major version: rủi ro khác nhau

### 5.1. Minor upgrade

**Minor version** thường chủ yếu gồm security fixes, bug fixes, stability/performance improvements. Dù ít breaking changes hơn major, vẫn có thể:

- Thay đổi query planner và hiệu năng truy vấn.
- Ảnh hưởng extension, driver hoặc native clients.
- Yêu cầu restart/failover, tạm thời gián đoạn kết nối.
- Thay đổi hành vi đã được ứng dụng phụ thuộc ngoài ý muốn.

Đừng bỏ integration tests chỉ vì tên bản cập nhật chứa số minor.

### 5.2. Major upgrade

**Major version upgrade** có thể thay đổi catalog, data formats, feature support, SQL semantics, query optimizer và compatibility của extensions/plugins. Đặc biệt PostgreSQL major cần kiểm tra:

- Extensions: `pg_stat_statements`, `pg_cron`, `postgis` và extension bên thứ ba theo version đích.
- Những option/parameter bị đổi tên hoặc bỏ hỗ trợ.
- Stored functions, materialized views, logical replication, foreign data wrappers và client driver.
- Schema migration: tránh thêm DDL breaking change trong đúng cửa sổ có replication hạn chế.
- **Valid upgrade path**: không phải bất kỳ version nguồn nào cũng được nâng thẳng lên bất kỳ version đích nào.

Với MySQL/Aurora MySQL, xem charset/collation, reserved keywords, authentication, SQL modes, indexes và query plans theo release notes engine tương ứng.

### 5.3. SQL compatibility không đồng nghĩa performance compatibility

Một câu SQL vẫn chạy sau upgrade nhưng trở nên chậm vì planner statistics hoặc parameter thay đổi. Vì thế baseline cần:

~~~text
Trước nâng cấp:
  p95/p99 query latency
  Queries per second, write throughput
  CPU / FreeableMemory / DB connections
  Top SQL by DB load
  Lock wait, deadlocks, replication lag
  Disk IOPS, read/write latency

Sau nâng cấp:
  Cùng workload, cùng connection pool
  So sánh kế hoạch truy vấn và latency/throughput
  Kiểm tra memory pressure và error logs
~~~

Chỉ `SELECT version()` thành công **chưa đủ** xác nhận upgrade không làm suy giảm hiệu năng.

## 6. Multi-AZ, backups và các khái niệm dễ nhầm

| Cơ chế | Giải quyết tốt nhất | **Không** tự giải quyết |
| --- | --- | --- |
| **RDS Multi-AZ DB instance** | Dự phòng/failover ở AZ khác với standby | Test major version mới độc lập trước release |
| **Aurora cluster với writer/readers** | Tách read workload, failover topology theo thiết kế | Rollback schema, dữ liệu bị xóa nhầm |
| **Read replica** | Read scale, một số nhu cầu DR hoặc replication | Backup độc lập/zero data loss trong mọi tình huống |
| **Automated backups/PITR** | Restore dữ liệu về thời điểm được hỗ trợ | Chuyển traffic production tức thì mà không downtime |
| **Manual snapshot** | Recovery point rõ ràng, giữ lâu hơn khi cần | Catch-up mọi ghi sau snapshot |
| **Blue/Green Deployment** | Test version/cấu hình trên một môi trường sync trước cutover | Zero downtime/instant reversal sau cutover |

### 6.1. Multi-AZ có làm upgrade không gián đoạn?

Không. Multi-AZ giúp giảm ảnh hưởng một số hỏng hóc và thao tác maintenance nhờ standby/failover theo thiết kế, nhưng **không có cam kết mọi engine upgrade đều không gián đoạn**. Major upgrade có thể cần thời gian bổ sung; tiến trình DB restart, repl health và DNS/cache có thể khiến ứng dụng bị lỗi thoáng qua.

### 6.2. Backup và RPO trước nâng cấp

Trước thao tác không dễ đảo ngược:

- Kiểm tra backup retention, `LatestRestorableTime` và khả năng `Point-in-Time Restore` của đúng instance/cluster.
- Cân nhắc **manual snapshot** trước nâng major hoặc khi có yêu cầu giữ recovery point.
- Không coi snapshot vừa tạo là đạt RTO nếu chưa thực hành restore và đo thời gian thực.
- Giữ quyền IAM/KMS cần thiết để truy cập snapshot/backup khi phục hồi.
- Với dữ liệu lớn, đánh giá thời gian restore, phục hồi indexes/caches và chi phí dựng hệ thống mới.

**RPO = mức mất dữ liệu tối đa chấp nhận, RTO = thời gian cần để phục hồi chức năng.** Có snapshot chưa chứng minh cả hai mục tiêu đều đạt.

## 7. Blue/Green Deployments: ý tưởng và vòng đời

**Blue/Green** là một phương pháp giảm rủi ro của thay đổi database bằng cách **tách môi trường production hiện tại khỏi môi trường thử thay đổi**, trong khi vẫn giữ dữ liệu mới ở green được đồng bộ từ blue theo cơ chế replication hỗ trợ.

~~~mermaid
flowchart TB
    APP["Application\nDB endpoint production"] --> BLUE["BLUE\nRDS / Aurora production\nwriter + readers theo topology"]
    BLUE -->|"Replication được quản lý\nBlue → Green"| GREEN["GREEN\nStaging synchronized\nnew version / parameters"]
    TEST["Read-only compatibility\nchecks & load test an toàn"] -.-> GREEN
    HEALTH["CloudWatch / RDS monitoring\nReplication lag + DB health"] -.-> BLUE
    HEALTH -.-> GREEN
    GATE{"Go / No-Go\nGuardrails + approved window"} --> CUT["Managed switchover"]
    CUT -->|"Đổi đích endpoint production"| GREEN
~~~

**Thuật ngữ không đổi trong suốt quy trình:**

- **Blue:** production database **đang** phục vụ ứng dụng.
- **Green:** môi trường staging được tạo từ blue, đồng bộ dữ liệu thông qua replication được dịch vụ hỗ trợ.
- **Switchover:** thao tác được quản lý để **green trở thành production mới** sau khi kiểm tra trạng thái đồng bộ và sức khỏe.
- **Old blue:** database production cũ, được giữ lại sau switchover theo quy tắc dịch vụ và chính sách dọn tài nguyên.

### 7.1. Vòng đời theo từng pha

~~~mermaid
stateDiagram-v2
    [*] --> Planning
    Planning --> Creating: Validate prerequisites
    Creating --> Replicating: Green created
    Replicating --> Testing: Sync healthy
    Testing --> Replicating: Fix / retest
    Testing --> Ready: Change approved
    Ready --> Switching: Switchover request
    Switching --> Complete: Guardrails pass and switch
    Switching --> Replicating: Switch failed/timed out; state recovered
    Complete --> PostCutover: Application validation
    PostCutover --> Retired: Retention and cleanup policy
    Retired --> [*]
~~~

*Sơ đồ là mô hình vận hành, không phải danh sách trạng thái API chính xác của AWS. Tên trạng thái thực tế được lấy từ `DescribeBlueGreenDeployments` và các sự kiện RDS/Aurora.*

### 7.2. Những thay đổi thường áp dụng lên green

- **Minor/major engine version upgrade** theo đường nâng cấp được hỗ trợ.
- Thay đổi DB instance class hoặc cấu hình storage/cluster phù hợp với tài nguyên.
- Điều chỉnh **parameter groups**, kiểm tra tác động của static parameters sau reboot.
- Thử cấu hình khác nhằm giảm rủi ro khi nâng cấp production.
- Thử SQL/JDBC/ORM compatibility và baseline performance.

Không phải mọi thao tác có thể thực hiện an toàn trên green khi còn replication. **Thay schema trên green** có thể xung đột với replication; **viết dữ liệu vào green** có thể gây lệch với blue. Việc muốn nâng cấp schema bằng blue/green cần đọc kỹ **replication compatibility** theo engine/mode và sử dụng migration pattern phù hợp.

### 7.3. Switchover nhanh không đồng nghĩa zero downtime

AWS mô tả Blue/Green switchover thường hoàn tất **dưới một phút** trong điều kiện phù hợp và được thiết kế để tránh mất dữ liệu trong switchover hợp lệ. Tuy nhiên, thao tác thực tế:

1. Chạy guardrail checks.
2. Tạm dừng **writes**, cắt các kết nối database nhất định và ngăn kết nối mới trong thời gian chuyển.
3. Đợi green bắt kịp replication.
4. Chuyển tên database/endpoints tương ứng để endpoint production tiếp tục trỏ tới database mới.
5. Cho phép kết nối/ghi trở lại sau khi chuyển xong.

Ứng dụng phải chịu được **khoảng gián đoạn ngắn**, reconnect và retry an toàn. Thời lượng có thể vượt kỳ vọng hoặc switchover bị hủy nếu các điều kiện không đạt; không ghi “zero downtime” vào SLA chỉ vì dùng Blue/Green.

## 8. AWS hỗ trợ Blue/Green trên engine nào?

| Dịch vụ | Phạm vi hỗ trợ chính | Cần kiểm tra khi lập kế hoạch |
| --- | --- | --- |
| **RDS for MySQL** | Blue/Green Deployments theo Region/version hỗ trợ | Binlog/replication, parameter groups, option groups, replicas |
| **RDS for MariaDB** | Blue/Green Deployments theo Region/version hỗ trợ | Engine version, binary logs, topology, dependencies |
| **RDS for PostgreSQL** | Blue/Green theo version/mode replication | Physical vs logical replication, DDL/DCL, slots, sequences, extensions |
| **Aurora MySQL** | Aurora Blue/Green theo version/Region được hỗ trợ | Cluster topology, engine upgrade path, binlog và những tính năng Aurora |
| **Aurora PostgreSQL** | Aurora Blue/Green theo version/Region được hỗ trợ | Logical replication caveats, cluster/reader behavior, statistics |
| **Aurora Global Database** | Có hỗ trợ Blue/Green theo **phiên bản và cấu hình đủ điều kiện** | Global topology, secondary Regions, đặc tính cụ thể và giới hạn |
| **RDS engines khác** | Không tự suy luận có Blue/Green tương đương | Kiểm tra support matrix; cân nhắc snapshot/restore, DMS hoặc kỹ thuật engine-specific |

**Quan trọng:** Tài liệu RDS Blue/Green và Aurora Blue/Green là **hai hướng dẫn riêng**. Nếu đọc một trang nói chỉ hỗ trợ MySQL/MariaDB/PostgreSQL cho RDS, đừng suy ra Aurora không được hỗ trợ; Aurora có hướng dẫn riêng, bao gồm Aurora Global Database theo điều kiện hiện hành.

### 8.1. Không suy support chỉ từ engine name

Ví dụ một tổ chức chạy PostgreSQL major cũ với extension không còn tương thích. Dù **RDS for PostgreSQL** có tính năng Blue/Green, đường nâng `PostgreSQL x → y` cụ thể có thể **không được hỗ trợ**. Cần xác minh:

- Exact source version/target version và danh sách **ValidUpgradeTarget**.
- Engine availability trong AWS Region.
- Instance/cluster topology, replicas, KMS/encryption, feature associations.
- Tình trạng extensions/parameters và những tích hợp dữ liệu bên ngoài.
- Cách replication được chọn khi version thay đổi.

Nếu support matrix không phù hợp, có thể đánh giá **AWS DMS**, logical export/import, snapshot restore/upgrade hoặc phương án migration khác với cutover riêng. Đừng gắn nhãn đó là “Blue/Green native” nếu workflow không dùng tính năng của RDS/Aurora.

## 9. Replication giữa blue và green: cơ chế quyết định rủi ro

### 9.1. Replication health và replication lag

**Replication lag** là độ trễ giữa thay đổi đã ghi tại blue và dữ liệu tương ứng xuất hiện tại green. Nếu lag cao, switchover có thể phải chờ lâu hoặc bị guardrails từ chối.

~~~text
10:00:00  Blue nhận order #900
10:00:02  Green đã áp dụng order #900
           → replication lag ở ví dụ khoảng 2 giây

10:00:30  Writer blue bùng nổ writes + DDL dài
10:00:50  Green vẫn đang áp dụng đến thay đổi 10:00:32
           → lag lớn; không nên switch chỉ vì green "Available"
~~~

Đây là ví dụ thời gian minh họa; metric thực tế phụ thuộc engine và loại replication. Trước cutover cần theo dõi **trạng thái replication, xu hướng lag và rate ghi** chứ không chỉ một datapoint bằng 0.

### 9.2. RDS PostgreSQL: physical vs logical replication

Theo tài liệu RDS PostgreSQL Blue/Green, phương pháp replication **phụ thuộc phiên bản nguồn và loại upgrade**:

- **Physical replication:** thường dùng khi **không có major version upgrade**, chẳng hạn cùng major version hoặc minor upgrade được hỗ trợ.
- **Logical replication:** được dùng trong các tình huống **major version upgrade đủ điều kiện**.

Điểm quyết định là **logical replication không tự đồng bộ mọi thay đổi metadata và object của PostgreSQL**. Với các triển khai dùng logical replication:

- **DDL** như `CREATE TABLE`, `ALTER TABLE`, `CREATE SCHEMA` và một số operations tạo partitions **không tự được đồng bộ từ blue sang green**.
- **DCL** như `GRANT`, `REVOKE`, `ALTER DEFAULT PRIVILEGES` cũng bị giới hạn; RDS có cơ chế phát hiện một số thay đổi và **có thể đưa replication sang `Replication degraded`, chặn switchover**.
- **Sequence** (`nextval`) không phát event như row changes; có cơ chế đồng bộ sequence vào thời điểm switchover theo hỗ trợ, có thể ảnh hưởng thời gian.
- **Large objects** mới/sửa sau lúc tạo B/G, **unlogged tables**, materialized views và extensions có hạn chế riêng.
- Những bảng có UPDATE/DELETE trong logical replication cần identity phù hợp, thường **primary key** hoặc thiết kế `REPLICA IDENTITY` được chấp thuận.
- Logical replication slots giữ WAL; backlog và số databases lớn có thể gây disk pressure nếu green không theo kịp.

**Không chuyển từ “DDL chưa replicate” sang “cứ làm DDL bên blue rồi áp lại ở green là xong”**. Với native B/G, những DDL/DCL không hỗ trợ có thể khiến deployment bị degraded và phải **xóa/recreate green**, không chỉ sửa script.

### 9.3. PostgreSQL upgrade checklist theo chế độ

| Hạng mục | Physical replication | Logical replication |
| --- | --- | --- |
| Nâng major engine trên green | Có giới hạn, không mặc định hỗ trợ | Dùng cho một số source→target major path |
| DDL/DCL ở blue | Cần tuân thủ thay đổi/hạn chế của cơ chế hiện hành | Tránh DDL/DCL không tương thích; có thể chặn switchover |
| Sequences và identity | Theo bản sao vật lý/engine semantics | Cần xem đồng bộ sequence khi switch |
| Extensions | Kiểm tra version/restart | Kiểm tra extension support và DDL do background jobs |
| Theo dõi WAL/replication slots | Quan trọng tùy topology | Rất quan trọng để tránh replication lag/storage pressure |
| Materialized views, large objects | Theo engine/feature | Có hạn chế cập nhật/replication cụ thể |

Trước **major upgrade**, phải đọc trang “PostgreSQL replication methods for blue/green deployments” và “Limitations and considerations”, vì AWS có thể thêm version đủ điều kiện hoặc thay đổi hành vi theo release.

### 9.4. MySQL/MariaDB và Aurora MySQL

Các môi trường MySQL/MariaDB thường liên quan **binary log/replication** và điều kiện khác nhau theo version và topology:

- Kiểm tra binary logging, retention, replica lag, GTID/binlog policies theo yêu cầu AWS.
- Tránh external replication/topology không được hỗ trợ.
- Kiểm tra **event scheduler**, triggers, scheduled jobs và background writes trên green để ngăn side effect hoặc replication conflicts.
- Thử character set/collation, SQL mode, reserved keywords và behavior JDBC sau major upgrade.
- Xác nhận parameter/option groups và extensions của đúng engine đã được sao chép/cập nhật.

Không suy rằng mọi Aurora MySQL major upgrade có thể dùng cùng đường đi và cùng thời lượng như RDS MySQL.

### 9.5. Vì sao không nên ghi vào green?

Trước switchover, green nhận thay đổi từ blue. Nếu app/test tool cùng **ghi dữ liệu riêng lên green**, có thể phát sinh:

~~~text
Blue:  order_id=101 status=PAID
Green: order_id=101 status=TESTING  (do QA ghi)
Replication tiếp theo → conflict / data divergence
~~~

Các bài test **read-only**, metadata checks và kiểm tra tính tương thích kết nối là lựa chọn ít rủi ro. Nếu cần chạy test **write-heavy**, tốt hơn là dựng **một bản sao tách biệt** không nằm trong replication path, hoặc dùng phương án kiểm thử được AWS và DBA chấp thuận. Không dùng green đang sync để nạp dữ liệu thử rồi xóa sau khi test.

## 10. Những hạn chế Blue/Green cần kiểm tra trước khi tạo

### 10.1. Các hạn chế chung

Một số điểm nổi bật trong tài liệu AWS:

- Blue/green resources của **RDS** có những ràng buộc về **cùng AWS account** và về các tính năng networking/topology; không mặc định dùng cross-account B/G.
- Những cấu hình **Multi-AZ DB instance** có thể được hỗ trợ trong RDS B/G, nhưng **RDS Multi-AZ DB cluster** là loại tài nguyên riêng và có những hạn chế hỗ trợ — phải phân biệt chính xác.
- **Cascading read replicas, cross-Region read replicas** hoặc các tích hợp khác có thể không tương thích trong RDS B/G tùy engine/config.
- **Aurora Global Database** có support riêng nhưng phải tra chính xác phiên bản/Region/topology; không lấy các quy tắc RDS DB instance áp nguyên vào global cluster.
- Quản lý **master user password bằng Secrets Manager** trong B/G có những giới hạn theo tài liệu hiện hành; phải có kế hoạch secret rotation/storage phù hợp.
- Tính năng gắn **zero-ETL integrations với Amazon Redshift** hoặc một số chức năng replication bên ngoài có thể yêu cầu tháo kết nối trước switchover rồi tạo lại sau.
- **RDS Proxy** có hỗ trợ tích hợp B/G theo một số điều kiện, nhưng proxy phải được cấu hình đúng thời điểm và nguồn; không suy rằng mọi proxy/topology tự cập nhật.
- Không đặt tùy ý AWS CloudFormation vào luồng quản lý native B/G nếu tính năng không hỗ trợ; giữ cơ chế IaC có kiểm tra drift và quản lý lifecycle.

Những hạn chế này **có thể thay đổi** theo AWS release. Tiêu chí kiểm tra thực tế là **support matrix của đúng resource** và kết quả preflight/guardrails, không phải một danh sách thuộc lòng.

### 10.2. RDS Proxy và JDBC clients

RDS Proxy hoặc driver thông minh có thể cải thiện quá trình reconnect/routing khi writer thay đổi, nhưng **không có nghĩa không gián đoạn**. RDS Proxy có thể đóng kết nối backend/proxy trong switchover và ứng dụng phải mở lại connection.

Với Java:

- Không hardcode IP của RDS endpoint.
- Thiết lập DNS TTL/caching phù hợp, không giữ IP mãi trong JVM, OS, connection pool hoặc proxy bên ngoài.
- Dùng HikariCP/driver hỗ trợ phát hiện stale connections; đặt connection timeout và retry policy có giới hạn.
- Không retry bừa **transaction không idempotent** sau lỗi `connection reset` khi không biết database đã commit hay chưa.
- Kết hợp retry ở application với business idempotency key/outbox cho payment/order workflows.

### 10.3. Rủi ro những tích hợp gắn resource ID

Sau switchover, **DB instance/cluster identifier và endpoint name** có thể được chuyển cho green, nhưng **resource ID bất biến của từng tài nguyên** không biến thành resource ID của máy cũ.

Những thành phần cần kiểm tra theo resource ID:

| Tích hợp | Rủi ro sau switchover |
| --- | --- |
| **IAM database authentication** | IAM policy ARN `rds-db:connect` tham chiếu DB resource ID cũ |
| **CloudTrail/audit pipeline** | Bộ lọc resource ID trỏ DB cũ |
| **Database Insights/Performance Insights** | Dashboard/API theo resource identifier cũ |
| **AWS Backup** | Backup selection/resources liên kết tài nguyên cũ |
| **DMS/CDC jobs** | Checkpoint và replication stream cũ không tự tiếp tục |
| **IAM roles associated with DB** | DB-associated roles có thể phải gắn lại ở green |
| **Aurora Auto Scaling** | Một số policies của blue không được copy sang green |
| **Tags** | Changes bên green có thể bị tags từ blue ghi đè lúc switch |

**Cùng endpoint string không đồng nghĩa mọi integration giữ nguyên identity**. Hãy có checklist resource IDs và tích hợp bên ngoài.

## 11. PITR và backup history sau Blue/Green switchover

Đây là rủi ro rất dễ bị bỏ qua.

### 11.1. Lịch sử PITR không “đi theo tên DB”

Theo tài liệu RDS/Aurora Blue/Green, **green giữ resource ID riêng và thời điểm earliest restorable time của nó bắt đầu từ lúc green được tạo**. Khi green thành production:

- Không thể mặc định restore **production mới** về một thời điểm **trước khi tạo green**.
- **PITR history của blue không tự chuyển thành history của green**.
- Blue cũ vẫn có history/automated backups riêng cho tới khi được xóa hoặc hết retention theo quy tắc.
- Để giữ khả năng phục hồi về thời điểm cũ hơn, AWS khuyến nghị cân nhắc **giữ blue cũ ít nhất trong khoảng recovery window cần thiết**, cùng bảo vệ snapshot theo chính sách.

~~~mermaid
gantt
    title Ví dụ giới hạn recovery history của Blue/Green
    dateFormat YYYY-MM-DD
    axisFormat %d/%m
    section Blue
    Lịch sử trước Green    :active, a1, 2026-11-01, 14d
    Giữ Blue để phục hồi   :a2, 2026-11-15, 15d
    section Green
    Tạo Green/PITR mới     :milestone, b1, 2026-11-15, 0d
    Switchover            :milestone, b2, 2026-11-20, 0d
    PITR của Green        :b3, 2026-11-15, 15d
~~~

*Ngày chỉ minh họa để thấy hai dòng lịch sử khác nhau, không phải lịch bảo trì thực tế của người học. Đồ thị không biểu diễn chi tiết tính liên tục WAL/backup ở từng giây.*

### 11.2. Ví dụ RPO/RTO phải kiểm tra

Hệ thống yêu cầu có thể phục hồi dữ liệu trong **14 ngày**. Green tạo ngày 15, switch ngày 20. Nếu xóa blue ngay ngày 20, việc muốn restore production về ngày 10 **không thể dựa trên PITR history của green**.

Kế hoạch:

1. Xác định **ngày tạo green**, earliest restorable time và backup retention thực tế.
2. Tạo/kiểm tra manual snapshots và retention theo compliance.
3. Giữ blue cũ đủ lâu cho những thời điểm cần restore trước green creation, nếu cần và an toàn.
4. Sau cutover, cập nhật backup policies/resource IDs và chạy thử restore của production mới.
5. Có kế hoạch xóa blue sau khi khung lịch sử và thời hạn kiểm toán đã được đáp ứng.

**Giữ blue tốn phí** compute/storage/backup; phải gắn owner/expiry và theo dõi chi phí.

## 12. Switchover: guardrails, timeout, DNS và trạng thái sau chuyển

### 12.1. Switchover guardrails

Trước khi đổi môi trường, RDS/Aurora thực hiện các **readiness checks** như:

| Kiểm tra | Điều muốn chứng minh |
| --- | --- |
| **Green replication healthy** | Green đang sync được với blue, không bị degraded |
| **Replication lag trong mức chấp nhận** | Có cơ hội bắt kịp và chuyển trong khoảng timeout |
| **Green không bị ghi trái phép** | Tránh data divergence |
| **Blue không có long-running writes/DDL** | Không kéo dài cutover hoặc chặn switch |
| **External replication state hợp lệ** | Không vướng source/replica ngoài quy tắc được hỗ trợ |
| **PostgreSQL logical replication constraints** | Không có unsupported DDL/DCL/large-object changes làm degraded |
| **DB/cluster instances available** | Môi trường đáp ứng trạng thái sẵn sàng theo dịch vụ |
| **RDS Proxy readiness (nếu có)** | Proxy có thể định tuyến khi writer/topology thay đổi |

**Guardrails là lớp bảo vệ, không thay cho rehearsal**. Chúng không biết hết mọi ứng dụng Java, stored procedures, business SLA hoặc code JDBC đang chạy.

### 12.2. Switchover timeout

Tài liệu RDS và Aurora mô tả thời gian timeout có thể cấu hình **30–3.600 giây**, mặc định khoảng **300 giây**. Nếu vượt timeout, dịch vụ cố thực hiện **rollback những thay đổi của chính switchover chưa hoàn thành**, để blue/green vẫn trong trạng thái trước lúc switch theo semantics dịch vụ.

**Phân biệt hai khái niệm:**

- **Rollback của thao tác switchover đang thất bại:** một phần behavior được AWS quản lý.
- **Rollback sau khi switchover đã hoàn tất và green đã nhận production writes:** **không phải** một nút “undo” bảo đảm không mất dữ liệu. Cần phương án database migration ngược/cutover có dữ liệu mới.

### 12.3. DNS, endpoint và kết nối đang mở

Trong switchover, AWS thay đổi **identifiers/endpoints** để các tên endpoint production quen thuộc chuyển sang trỏ môi trường mới, giảm nhu cầu sửa connection string.

Điều đó **không đồng nghĩa kết nối TCP cũ tự di chuyển**:

- Existing DB connections có thể bị đóng.
- RDS Proxy có thể giúp routing nhưng connections trong quá trình switch vẫn cần tái thiết lập.
- JVM DNS cache, OS resolver và client/proxy custom TTL cao có thể giữ endpoint cũ lâu hơn mặc định (RDS docs có lưu ý tránh TTL cao hơn mức DNS của RDS, thường 5 giây).
- Ứng dụng nên retry **kết nối mới** có exponential backoff + jitter; không retry transaction non-idempotent mà không biết commit outcome.

### 12.4. Kiểm tra cutover xong chưa

Khi AWS báo completed:

1. Xác nhận **production endpoint** hiện trỏ green resource mới; ghi lại DB resource ID mới.
2. Xác minh app sử dụng **writer mới**, không phải old blue read-only.
3. Thực hiện canary read/write **trên dữ liệu test được phê duyệt**, có cleanup.
4. Đo p95/p99 query latency, error rates, connection pool, deadlocks, replication lag và business events.
5. Xác nhận read replicas, RDS Proxy, IAM DB auth, Secrets Manager integrations, DMS/CDC, monitoring và backup policies.
6. Ghi chính xác thời gian gián đoạn và các warnings, không coi việc AWS báo completed là nghiệm thu ứng dụng.

### 12.5. Đừng chỉnh tags chỉ trên green rồi mong giữ nguyên

Trong quy trình switchover, **tags trên blue có thể thay thế các tags trên green** theo behavior AWS. Tag IAM/billing/backup/ownership cần được đối chiếu, bảo đảm **production mới** mang đúng tags sau cutover.

## 13. Runbook tổng thể: bảo trì và nâng cấp database có kiểm soát

Một runbook cần xác định **người điều hành, người kiểm tra dữ liệu, người theo dõi ứng dụng, tiêu chí Go/No-Go, thời điểm ngừng ghi và kênh liên lạc sự cố**.

~~~mermaid
flowchart TD
    R["Yêu cầu nâng cấp"] --> BASE["Chụp baseline và xác định SLO"]
    BASE --> COMP["Kiểm tra engine versions,\nreplication limitations, extension/app"]
    COMP --> BACK["Backup/restore rehearsal"]
    BACK --> GREEN{"Native Blue/Green được hỗ trợ?"}
    GREEN -->|"Có"| CREATE["Tạo green / cấu hình nâng cấp"]
    GREEN -->|"Không"| ALT["Lập phương án khác:\nrestore, DMS hoặc rolling path"]
    CREATE --> TEST["Test read-only / compatibility\nđo metrics + replication lag"]
    TEST --> GATE{"Go / No-Go"}
    GATE -->|"Không"| FIX["Điều tra, hoãn, recreate green khi cần"]
    FIX --> TEST
    GATE -->|"Có"| SWITCH["Switchover trong giờ phê duyệt"]
    SWITCH --> POST["Validate new writer/app/PITR"]
    POST --> HOLD["Giữ old blue theo policy"]
    HOLD --> END["Audit, cleanup, postmortem"]
~~~

### 13.1. Pha A — Preflight: tối thiểu 1–2 kỳ release trước cutover

Mục tiêu không phải luôn chính xác số ngày; mà là **đủ thời gian kiểm tra trước khi làm change production**.

| Nhóm | Cần ghi nhận | Người xác nhận |
| --- | --- | --- |
| **Inventory** | Engine, version, Region/AZ, instance/cluster ARN, topology, Multi-AZ/readers | DBA/Cloud Engineer |
| **Upgrade path** | Source/target version, version compatibility, extensions, release notes | DBA/App Lead |
| **Connections** | RDS endpoints, RDS Proxy, DNS resolver, JDBC URL, connection pools | App/SRE |
| **Data** | DB size, largest tables, write rate, transactions, replication lag baseline | DBA/Data Lead |
| **Backups** | Earliest/latest restore points, retention, manual snapshots, restore drill | DBA/SRE |
| **Security** | IAM roles, KMS, DB auth, Security Groups, subnet group, TLS certs | Security |
| **Dependencies** | CDC/DMS, zero-ETL, cron jobs, replicas, ETL, report engines | Data/Integration |
| **SLO** | Write outage budget, RTO/RPO, canary check, rollback criteria | Product/Operations |
| **Billing** | Green compute/storage, extra replicas, backup, metrics, old blue retention | FinOps |

Ví dụ thông tin ký duyệt:

~~~text
Change ID:        DB-UPGRADE-2026-11-001 (minh họa)
Blue:             shop-db-prod / PostgreSQL 15.x
Green target:     major version trong valid upgrade target
Maintenance:      00:00–01:00 giờ theo timezone vận hành
Expected outage:  ưu tiên dưới 1 phút; giới hạn chấp nhận 5 phút
Abort criteria:   replication degraded / lag không giảm /
                  client test fail / guardrails fail
Owner:            DBA on-call + SRE + Application Lead
Backup:           snapshot/PITR + restore rehearsal đã PASS
~~~

**Không dùng “dưới 1 phút” như một bảo đảm tuyệt đối**. Số này thể hiện mục tiêu vận hành; phải có phương án khi AWS switchover không hoàn thành trong khung cho phép.

### 13.2. Pha B — Chuẩn bị môi trường staging/green

1. Kiểm tra **native Blue/Green support** cho đúng engine/version/Region/topology.
2. Xác nhận backup/PITR trước tạo green, và tạo recovery point khi cần.
3. Tạo green với cấu hình nguồn phù hợp, quan sát trạng thái provisioning.
4. Nâng engine version và chỉnh parameter groups ở green **theo thao tác được hỗ trợ**.
5. Bảo đảm replication **healthy**, không có unsupported changes hoặc conflicts.
6. So các thông số green với blue: instance class, storage, parameter groups, TLS, subnet, IAM roles, reader count, alarms.
7. Chạy test compatibility có kiểm soát, tránh ghi dữ liệu thử vào môi trường green đang đồng bộ.
8. Lưu log kết quả test, tên/ARN/resource IDs, metrics và ngày tạo green để tính PITR.

**Không sửa trực tiếp database schema trên blue trong khi dùng PostgreSQL logical replication B/G nếu thao tác thuộc nhóm không hỗ trợ.** Một DDL tưởng nhỏ có thể buộc phải dựng lại green và làm dời lịch release.

### 13.3. Pha C — Rehearsal trước giờ chuyển

Kiểm tra các trường hợp:

| Kịch bản | Điều cần quan sát |
| --- | --- |
| Kết nối JDBC với target engine | Có handshake, TLS, auth, driver compatibility |
| Chạy các câu query quan trọng | Đúng kết quả và latency trong SLO |
| Batch/cron job đang bật | Không chạy side effects trùng từ green |
| Stored procedures/extensions | Load được và hành vi không thay đổi ngoài kế hoạch |
| Application reconnect | Reopen connection sau restart/DNS switch, pool không deadlock |
| DB/cluster replica behavior | Read replica lag/endpoint phục hồi đúng |
| IAM DB auth/resource ID | Policies đủ quyền trên **green resource IDs** |
| Backup/PITR + restore | Restore được một bản sao phù hợp trong thời gian chấp nhận |
| DMS/CDC/zero-ETL | Có kế hoạch reconfigure sau cutover |

**Test hiệu năng trên green phải tránh write conflict**. Có thể dùng query read-only với bộ dữ liệu production-like đã che giấu theo chính sách, hoặc tạo một snapshot clone/test DB riêng để chạy write-heavy benchmark.

### 13.4. Pha D — Chuẩn bị switchover trong giờ bảo trì

Trước thao tác có thể ảnh hưởng production:

- Thông báo người dùng/đội kỹ thuật về **write interruption** dự kiến.
- Tạm dừng hoặc drain các background workers có ghi DB trong khoảng cutover theo runbook.
- Dừng long-running DDL/ETL/transactions nếu được chấp thuận; chờ hoạt động đang chạy hoàn tất.
- Xác minh **green replication healthy**, lag dưới ngưỡng đã đặt và có xu hướng ổn định.
- Xác minh endpoints, RDS Proxy, DNS caching, connection pools, tài nguyên phụ thuộc.
- Chốt **Go/No-Go** dựa trên **metrics, logs, business SLO**, không dựa vào cảm giác “có vẻ ổn”.
- Cập nhật communication channel và người chịu trách nhiệm nhấn nút switch.

### 13.5. Pha E — Switchover

1. Người vận hành được ủy quyền thực hiện **Switch over** trong RDS Console/API hoặc CLI sau phê duyệt.
2. AWS chạy guardrails và thay đổi trạng thái deployment theo quy trình.
3. **Không can thiệp thủ công** vào tên endpoint/rename/promotion khi switchover đang chạy.
4. Quan sát RDS events, API/CloudWatch metrics, thời điểm ứng dụng nhận errors và tự reconnect.
5. Nếu switchover fail/timeout, dừng thao tác mới và điều tra trạng thái thực tế; **không retry mù**.

### 13.6. Pha F — Hậu kiểm và giữ old blue

Khi AWS báo switch completed:

- Kiểm tra **engine/version, resource ID, writer endpoint, reader endpoints**.
- Chạy canary transaction được phê duyệt; xác nhận dữ liệu được đọc lại từ **new writer**.
- Đo CPU, memory, query plans, DBLoad, network/IOPS, deadlocks, p95/p99 API, errors.
- Kiểm tra DMS/CDC, RDS Proxy, IAM database authentication, AWS Backup, alarms, tags và secrets integrations.
- Ghi **thời điểm switchover thực tế**, old/new resource IDs, earliest restorable times.
- Giữ old blue theo RPO/PITR retention và kế hoạch rollback dữ liệu; **không xóa ngay để tiết kiệm**.
- Sau khoảng quan sát và tuân thủ backup retention, mới xóa môi trường cũ theo quy trình review, đồng thời tránh để tài nguyên thừa tính phí vô thời hạn.

## 14. Ứng dụng Java Spring Boot: kiểm tra kết nối và retry an toàn

### 14.1. Vòng đời một kết nối JDBC khi đổi writer

~~~mermaid
sequenceDiagram
    participant API as Spring Boot
    participant POOL as HikariCP
    participant DNS as DNS/RDS Proxy
    participant DB as RDS writer (Blue → Green)
    API->>POOL: Borrow connection
    POOL->>DNS: Resolve endpoint / open socket
    DNS->>DB: Connect Blue
    DB-->>API: Transaction result
    Note over DB: Managed switchover
    DB--xPOOL: Connection closed/reset
    API->>POOL: New borrow / retry connection
    POOL->>DNS: Re-resolve endpoint
    DNS->>DB: Connect Green new writer
    DB-->>API: New session ready
~~~

Kết nối **đã được checkout từ pool** có thể lỗi trong switchover; không kỳ vọng HikariCP tự “tiếp nối” transaction đang dở.

### 14.2. Ví dụ cấu hình Spring Boot/HikariCP (minh họa)

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://shop-db-prod.example.rds.amazonaws.com:5432/shop
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 10000
      validation-timeout: 3000
      idle-timeout: 600000
      max-lifetime: 1800000
      keepalive-time: 120000
~~~

**Đây không phải “cấu hình tối ưu cho mọi ứng dụng”.** Tên endpoint là placeholder, các giá trị cần tuning theo **DB `max_connections`, số pods/tasks, application concurrency và network**. Không copy mật khẩu thực vào YAML/Git; dùng Secrets Manager hoặc phương thức quản lý secret phù hợp. Trong YAML minh họa, `${DB_USERNAME}` và `${DB_PASSWORD}` là cú pháp placeholder của Spring Boot để lấy thông tin kết nối từ môi trường; ứng dụng production nên quản lý secrets bằng cơ chế được phê duyệt.

### 14.3. DNS caching cho Java

JVM/OS có cơ chế DNS cache riêng. Với endpoint RDS/Aurora, **đừng cấu hình TTL vô hạn**. Cần kiểm tra:

- JVM security property `networkaddress.cache.ttl` và `networkaddress.cache.negative.ttl` theo JDK đang dùng.
- Resolver của container/OS, CoreDNS trong Kubernetes nếu có, corporate DNS, sidecar/proxy.
- RDS Proxy hoặc driver điều hướng endpoint theo topology.
- Idle/maximum lifetime của JDBC connections, health-check và failover behavior.

Không suy rằng chỉ thay Java DNS cache TTL bằng 5 giây là mọi in-flight connections được di chuyển; JDBC pool phải tạo **kết nối mới**. Tránh sửa cấu hình JVM production mà chưa kiểm thử.

### 14.4. Retry transaction: ngữ nghĩa commit chưa biết

Một ví dụ rủi ro:

~~~text
Ứng dụng: INSERT payment rồi COMMIT
Network:  TCP reset trước khi app nhận response
App:      Không biết commit đã thành công hay chưa

Nếu retry INSERT/charge ngay và không có idempotency key:
  → có thể xử lý trùng thanh toán.
~~~

Giải pháp:

- Giao dịch nghiệp vụ có **idempotency key** hoặc unique business transaction ID.
- Xử lý timeout như **outcome unknown**, kiểm tra trạng thái trong datastore/Payment provider khi cần.
- Tách retry **để mở connection mới** khỏi retry **thực thi lại nghiệp vụ**.
- Ghi persistent outbox cho các side effects ngoài DB khi phù hợp.
- Giới hạn retry với backoff/jitter; không tạo retry storm vào DB mới vừa phục hồi.

### 14.5. JDBC smoke tests

PostgreSQL (chỉ đọc):

~~~sql
SELECT version();
SELECT current_database(), current_user, current_timestamp;
SHOW server_version;
SHOW default_transaction_read_only;
SELECT 1 AS connectivity_ok;
~~~

MySQL/Aurora MySQL (chỉ đọc):

~~~sql
SELECT VERSION();
SELECT DATABASE(), CURRENT_USER(), NOW();
SHOW VARIABLES LIKE 'read_only';
SELECT 1 AS connectivity_ok;
~~~

Các câu SQL chỉ đọc giúp xác nhận version/session, **không chứng minh** writer mới cho phép một transaction business hoàn chỉnh. Canary ghi chỉ nên chạy trên **bảng/dữ liệu test đã được DBA phê duyệt** và có phương án cleanup/audit.

## 15. Khôi phục và rollback: trước hoặc sau switchover?

### 15.1. Trước khi bắt đầu switchover

Nếu green bị lỗi phiên bản hoặc compatibility, đơn giản nhất thường là **không switch**:

1. Tiếp tục phục vụ production từ blue.
2. Điều tra green và replication status.
3. Nếu replication degraded không khắc phục được theo hướng dẫn AWS, xóa/recreate green có kiểm soát.
4. Test lại và dời lịch cutover; không có lý do làm ảnh hưởng production chỉ để “giữ lịch”.

### 15.2. Switchover bị guardrails từ chối/timeout

Nếu guardrails chặn, không làm gì “bằng tay” để ép thành công:

- Xem state `Replication degraded`, lag, long transactions/DDL, external replication restrictions.
- Kiểm tra RDS events và tình trạng các DB instances/clusters.
- Xác nhận application vẫn dùng đúng blue production.
- Nếu AWS rollback phần switchover đã bắt đầu, verify trạng thái cuối; không giả định ngay sau một lỗi API là mọi thứ đã về normal.
- Chỉ retry khi đã xác định nguyên nhân và có người có thẩm quyền đồng ý.

### 15.3. Sau khi đã switchover thành công

Đây là tình huống khó hơn: **new green đã trở thành primary/writer và đã nhận dữ liệu mới**.

~~~mermaid
flowchart TD
    PROBLEM["Phát hiện lỗi sau cutover"] --> CLASS{"Mức độ tác động?"}
    CLASS -->|"Lỗi app/queries nhưng dữ liệu đúng"| APP["Rollback code/config\nhoặc fix forward"]
    CLASS -->|"Engine/storage không thể tiếp tục"| DATA["Phương án DB recovery/migration"]
    DATA --> FLOW{"Có bảo đảm đồng bộ dữ liệu mới về old blue?"}
    FLOW -->|"Không"| STOP["Không đảo endpoint thẳng\nXác định RPO & snapshot/PITR\nThiết kế migration ngược"]
    FLOW -->|"Có, đã kiểm chứng"| PLAN["Thực hiện cutover kế hoạch mới\nData consistency + downtime"]
    APP --> MON["Canary + metrics"]
    STOP --> MON
    PLAN --> MON
~~~

**Đừng “đổi endpoint về old blue” ngay sau cutover** nếu khách hàng đã phát sinh đơn hàng mới tại green; old blue không tự có những ghi mới. Một cú rollback vội có thể **mất dữ liệu giao dịch** hoặc tạo dual-write inconsistency.

Các lựa chọn cần DBA đánh giá: sửa cấu hình/app, khôi phục qua PITR/snapshot, chuyển dữ liệu có kiểm chứng, CDC/DMS migration ngược nếu khả thi, hoặc tạm chặn ghi chờ xử lý. **Không có một lệnh rollback chung bảo đảm zero data loss sau khi cutover đã hoàn tất**.

### 15.4. Rollback criteria phải có ngay từ đầu

Ví dụ:

~~~text
Trước Switch:
  replication lag không giảm / health degraded → NO-GO
  SQL compatibility test fail → NO-GO
  missing IAM DB auth grants → NO-GO

Trong Switch:
  switchover timeout / AWS guardrails fail → STOP, VERIFY CURRENT STATE

Sau Switch:
  app p99 > SLO 5 phút → phân loại, fix forward/rollback app
  data integrity issues → freeze writes theo playbook và điều tra
  không tự chuyển về old blue khi chưa giải quyết writes mới
~~~

## 16. Quan sát trước, trong và sau cutover

### 16.1. Tín hiệu RDS/Aurora cần theo dõi

| Layer | Metrics / signals | Cách sử dụng |
| --- | --- | --- |
| **Replication** | Replica lag / replication status theo engine | Quyết định readiness và switchover gate |
| **CPU / Memory** | CPUUtilization, FreeableMemory | Phát hiện tăng tải sau nâng version |
| **Connections** | DatabaseConnections, connection failures | Nhận diện reconnect storm và pool exhaustion |
| **IOPS / latency** | ReadIOPS, WriteIOPS, ReadLatency, WriteLatency | Thay đổi query plan/IO pressure |
| **Storage** | FreeStorageSpace hoặc Aurora storage metrics | Giám sát WAL/binlog, temp, free space |
| **Performance** | Database Insights, top SQL/DB Load, locks, deadlocks | Tìm query regression |
| **Availability** | RDS events, status/maintenance/pending-reboot | Xác nhận lifecycle và trạng thái sau switch |
| **Backup/PITR** | Earliest/LatestRestorableTime, backup retention, snapshot status | Bảo vệ recovery window sau cutover |
| **App** | HTTP error %, p95/p99, HikariCP active/pending connections | Đo trải nghiệm thật |
| **Cost** | DB instances x2, snapshots, backup, logs, replication | Dự toán green và giữ old blue |

Không phải mọi metric xuất hiện giống nhau trên **RDS instance**, **Aurora writer/reader** hoặc từng engine; cần chọn namespace/dimensions/đơn vị phù hợp và đo trước/sau cùng workload.

### 16.2. CloudWatch alarms theo pha

Trước switchover:

- Replication unhealthy hoặc replication lag liên tục vượt ngưỡng Go/No-Go.
- Free storage/memory quá thấp; replica apply không theo kịp write rate.
- Lỗi SQL/performance regression so với baseline.

Trong switchover:

- DB connections giảm/rớt và API lỗi tăng trong khoảng cho phép; alert nếu vượt outage budget.
- RDS event báo switchover error, timeout, invalid config.

Sau switchover:

- DBLoad/p95 query latency tăng, connection pool pending quá lâu.
- Error rate của Java API tăng, migration/CDC jobs ngừng hoạt động.
- PITR/automated backups/alerts không còn gắn đúng resource ID.

### 16.3. Quan sát logs đúng phạm vi

Nên bật log và retention theo chính sách cho:

- RDS/Aurora error logs, PostgreSQL logs hoặc MySQL slow query logs theo engine.
- CloudWatch Logs integration, CloudTrail API calls.
- Java application logs với correlation IDs, JDBC exceptions và circuit breaker metrics.
- Các automation events/notifications cho update/cutover.

**Không xuất full SQL parameters, passwords, PII hoặc connection strings chứa secrets** vào logs. Performance investigation phải tôn trọng quyền truy cập dữ liệu của DBA/security.

## 17. AWS CLI chỉ đọc: kiểm tra bản hiện có và khả năng nâng cấp

Các lệnh bên dưới **chỉ đọc**, không tạo, sửa, reboot, switch hoặc xóa database. Tên `shop-db-prod`, `shop-aurora-prod`, tài khoản, Region đều là **placeholders**; chạy trong account/Region bạn có quyền xem và không công bố output chứa endpoint/ARN nhạy cảm.

### 17.1. Xem caller, DB instances và pending modifications

~~~bash
aws sts get-caller-identity

aws rds describe-db-instances \
  --region ap-southeast-1 \
  --query "DBInstances[].{Id:DBInstanceIdentifier,Engine:Engine,Version:EngineVersion,Status:DBInstanceStatus,MultiAZ:MultiAZ,Maintenance:PreferredMaintenanceWindow,AutoMinor:AutoMinorVersionUpgrade,Pending:PendingModifiedValues,ResourceId:DbiResourceId}" \
  --output json
~~~

Trong output:

- `PendingModifiedValues` có thể cho biết những thay đổi đã yêu cầu nhưng chưa áp dụng.
- `DBInstanceStatus` giúp kiểm tra tình trạng hiện tại, **không chứng minh application query khỏe**.
- `DbiResourceId` quan trọng khi xác định resource identity sau B/G switchover.
- Nếu DB instance thuộc Aurora cluster, xem cả **cluster information**, không chỉ từng instance.

### 17.2. Xem Aurora clusters

~~~bash
aws rds describe-db-clusters \
  --region ap-southeast-1 \
  --query "DBClusters[].{Id:DBClusterIdentifier,Engine:Engine,Version:EngineVersion,Status:Status,Endpoint:Endpoint,ReaderEndpoint:ReaderEndpoint,Maintenance:PreferredMaintenanceWindow,Members:DBClusterMembers,ResourceId:DbClusterResourceId}" \
  --output json
~~~

**Đừng lấy `Endpoint` và `ReaderEndpoint` rồi suy rằng reader luôn không có độ trễ**. Với Aurora, replication lag/reader consistency vẫn cần được kiểm tra theo engine và workload.

### 17.3. Liệt kê pending maintenance

~~~bash
aws rds describe-pending-maintenance-actions \
  --region ap-southeast-1 \
  --query "PendingMaintenanceActions[].{Resource:ResourceIdentifier,Actions:PendingMaintenanceActionDetails[].{Name:Action,AutoAfter:AutoAppliedAfterDate,Current:CurrentApplyDate,ForcedAfter:ForcedApplyDate,OptIn:OptInStatus}}" \
  --output json
~~~

Đọc `Action`, `CurrentApplyDate`, `AutoAppliedAfterDate` và `ForcedApplyDate` nếu có. Một ngày apply bắt buộc cần được lên lịch như thay đổi có tác động — không mặc định mọi sự kiện đều chờ đến khi team ấn nút.

### 17.4. Kiểm tra engine upgrade targets

~~~bash
aws rds describe-db-engine-versions \
  --region ap-southeast-1 \
  --engine postgres \
  --engine-version 15.4 \
  --query "DBEngineVersions[].{Version:EngineVersion,Targets:ValidUpgradeTarget[].{Version:EngineVersion,Major:IsMajorVersionUpgrade}}" \
  --output json
~~~

`postgres`/`15.4` chỉ là engine và source version minh họa. Với Aurora PostgreSQL, thay `--engine` thành `aurora-postgresql` và source version đúng; **không giả định version tồn tại hoặc upgrade path giống RDS**.

Nếu một target không xuất hiện, đừng ép bằng lệnh `modify-db-instance`; hãy tra release notes và các đường nâng trung gian được hỗ trợ.

### 17.5. Xem parameter groups và pending reboot

~~~bash
aws rds describe-db-instances \
  --region ap-southeast-1 \
  --db-instance-identifier shop-db-prod \
  --query "DBInstances[0].DBParameterGroups" \
  --output json

aws rds describe-db-clusters \
  --region ap-southeast-1 \
  --db-cluster-identifier shop-aurora-prod \
  --query "DBClusters[0].DBClusterParameterGroup" \
  --output text
~~~

Khi tìm tham số cần reboot, xem parameter group apply type và status tại instance/cluster, cùng docs của engine. **Không dùng reboot như bước “refresh status” vô hại** trên production.

## 18. AWS CLI chỉ đọc: quan sát Blue/Green và sự kiện

### 18.1. Xem danh sách deployments

~~~bash
aws rds describe-blue-green-deployments \
  --region ap-southeast-1 \
  --query "BlueGreenDeployments[].{Id:BlueGreenDeploymentIdentifier,Name:BlueGreenDeploymentName,Status:Status,Source:Source,Target:Target,Details:StatusDetails}" \
  --output json
~~~

Xem đúng **`BlueGreenDeploymentIdentifier`** (ID dạng do API trả), trạng thái deployment, Source/Target và StatusDetails. Đừng suy một B/G không xuất hiện ở Region này là nó không tồn tại ở Region khác.

### 18.2. Xem một deployment theo ID

~~~bash
aws rds describe-blue-green-deployments \
  --region ap-southeast-1 \
  --blue-green-deployment-identifier bgd-EXAMPLE123 \
  --output json
~~~

Với API response thật, đọc các resource mappings và switchover details nếu có. Khi đang chuyển, quan sát trạng thái của **cả deployment và DB instances/clusters**, không chỉ API response ban đầu của thao tác Switch.

### 18.3. Xem các sự kiện RDS liên quan

~~~bash
aws rds describe-events \
  --region ap-southeast-1 \
  --source-type db-instance \
  --duration 60 \
  --output json

aws rds describe-events \
  --region ap-southeast-1 \
  --source-type db-cluster \
  --duration 60 \
  --output json
~~~

`--duration 60` là **60 phút** theo API, không phải 60 giây. Với Blue/Green, event categories và EventBridge notifications phụ thuộc resource type; rà soát theo cả source và application monitoring.

### 18.4. Kiểm tra snapshot/backup settings

~~~bash
aws rds describe-db-snapshots \
  --region ap-southeast-1 \
  --db-instance-identifier shop-db-prod \
  --output json

aws rds describe-db-cluster-snapshots \
  --region ap-southeast-1 \
  --db-cluster-identifier shop-aurora-prod \
  --output json
~~~

Các API trên liệt kê snapshots theo filter được cung cấp. **Không thể chỉ nhìn thấy một snapshot `available` rồi khẳng định restore được trong RTO**; phải có diễn tập restore, IAM/KMS và application validation.

### 18.5. Kiểm tra RDS Proxy (nếu có)

~~~bash
aws rds describe-db-proxies \
  --region ap-southeast-1 \
  --output json

aws rds describe-db-proxy-targets \
  --region ap-southeast-1 \
  --db-proxy-name shop-db-proxy \
  --output json
~~~

Nếu dùng Proxy, kết quả targets sau switch có thể cần thời gian phản ánh thay đổi; monitor actual app traffic và database connections chứ không chỉ một snapshot của CLI.

## 19. Lệnh thay đổi production: học cú pháp nhưng không tự chạy

**Những thao tác dưới đây có thể làm database restart, ngừng ghi, đổi endpoint hoặc phát sinh chi phí. Đây là mẫu runbook để review, không phải lệnh thực thi trong bài học.**

### 19.1. Nâng major RDS instance trực tiếp (mẫu minh họa)

~~~bash
# KHÔNG CHẠY nếu chưa có change approval, backup và app compatibility test.
# Thay TARGET_VERSION bằng version đã xác minh trong ValidUpgradeTarget.
aws rds modify-db-instance \
  --region ap-southeast-1 \
  --db-instance-identifier shop-db-prod \
  --engine-version TARGET_VERSION \
  --allow-major-version-upgrade \
  --no-apply-immediately
~~~

**`--no-apply-immediately` không biến nâng cấp thành zero downtime**; nó yêu cầu xếp lịch áp dụng các pending modifications theo cơ chế của RDS. Cần lên kế hoạch bảo trì, xác nhận pending status và kiểm thử bản sau khi nâng.

### 19.2. Switchover native Blue/Green (mẫu minh họa)

~~~bash
# CHỈ LÀ MẪU, không chạy ngoài giờ phê duyệt.
# Cảnh báo: thao tác cắt kết nối/ghi và đổi production writer.
aws rds switchover-blue-green-deployment \
  --region ap-southeast-1 \
  --blue-green-deployment-identifier bgd-EXAMPLE123 \
  --switchover-timeout 600
~~~

Thời gian `600` là 10 phút **timeout cho thao tác** theo cấu hình minh họa, không phải dự báo chắc chắn downtime 10 phút. Trước khi gọi lệnh này, yêu cầu DBA/SRE xác nhận **Go**, replication lag, app readiness, backups và kênh phản ứng sự cố.

### 19.3. Vì sao không dùng lệnh “promote green”?

AWS phân biệt **managed Blue/Green switchover** với **manual promote** của green. **Promote green thủ công** có thể phá replication/đưa deployment vào trạng thái invalid, không thay thế guardrails hay endpoint orchestration. Chỉ dùng API **`switchover-blue-green-deployment`** hoặc Console **Switch over** theo quy trình tương ứng.

## 20. SQL preflight và so sánh phiên bản (chỉ đọc)

Thực hiện những câu SQL sau **chỉ khi có quyền đọc metadata trên database hợp lệ**. Trên production, không dùng query full-table scan để “kiểm tra nhanh” vì có thể làm tăng CPU/IO, lock wait hoặc lộ dữ liệu khách hàng.

### 20.1. PostgreSQL/RDS PostgreSQL/Aurora PostgreSQL

~~~sql
-- Phiên bản máy chủ
SELECT version();
SHOW server_version;

-- Extensions và version đang cài
SELECT extname, extversion
FROM pg_extension
ORDER BY extname;

-- Các transaction tồn tại lâu (chỉ metadata được phân quyền)
SELECT pid, usename, application_name, state,
       clock_timestamp() - xact_start AS transaction_age
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY transaction_age DESC
LIMIT 20;
~~~

Tại sao cần quan sát `pg_stat_activity`? **Long-running writes/DDL/transactions** có thể làm replication lag tăng hoặc cản trở switchover. Trước khi terminate một session, **phải xác nhận owner/transaction**, không giết kết nối production chỉ vì nó xuất hiện ở đầu bảng.

### 20.2. MySQL/RDS MySQL/Aurora MySQL

~~~sql
SELECT VERSION();
SHOW VARIABLES LIKE 'version%';
SHOW VARIABLES LIKE 'read_only';
SHOW VARIABLES LIKE 'sql_mode';
SHOW VARIABLES LIKE 'character_set_server';
SHOW VARIABLES LIKE 'collation_server';
~~~

Khi major version thay đổi, đối chiếu SQL mode, collation và driver behavior với application tests. Query cho biết cấu hình, **không thay thế so sánh dữ liệu/hiệu năng**.

### 20.3. Kiểm tra dữ liệu giữa blue và green

So sánh nhanh `SELECT COUNT(*)` toàn bảng lớn có thể chậm và tạo load không cần thiết. Với bảng rất lớn:

- Dùng phương pháp **sampling/batching theo primary key** và kiểm tra quyền.
- Đo row count theo thống kê khi phù hợp, hiểu đó là ước lượng.
- Kiểm tra đối chiếu nghiệp vụ theo business IDs và các cửa sổ thời gian đã biết.
- Khi replica có lag, không so hai hệ thống ở **hai thời điểm khác nhau** rồi kết luận có data loss.
- Nếu phải checksum dữ liệu, chọn công cụ/algorithm và bandwidth phù hợp, không chạy đồng thời trên production và green trước giờ switch mà không được duyệt.

## 21. Chi phí của Blue/Green: hai môi trường song song

**Blue/Green giảm rủi ro thay đổi nhưng không miễn phí.** Trong khoảng tồn tại đồng thời, green tiêu thụ tài nguyên riêng.

| Hạng mục | Chi phí có thể tăng | Gợi ý kiểm soát |
| --- | --- | --- |
| **Compute** | Green DB instances/cluster với size tương đương hoặc cao hơn | Ghi rõ thời gian giữ green và owner |
| **Storage/IO** | Storage mới và replication writes; Aurora storage/IO model tùy cấu hình | Theo dõi dung lượng, IOPS, buffer pressure |
| **Backups/snapshots** | Snapshots, retention, storage backup ngoài allowance | Theo dõi lifecycle/PITR window |
| **Read replicas** | Green copies của topology được hỗ trợ | Kiểm tra số replicas thực tế |
| **Logs/insights** | Enhanced Monitoring, Database Insights, CloudWatch Logs | Đặt retention/log verbosity hợp lý |
| **Data transfer/replication** | Lưu lượng phát sinh theo topology và billing rules | Đối chiếu Region/engine/pricing |
| **Old blue sau cutover** | Còn tính phí khi giữ để bảo vệ lịch sử PITR | Có ngày rà soát/xóa theo chính sách |
| **Kiểm thử** | App staging workers, RDS Proxy, test Lambda/ECS, load generators | Dọn tài nguyên lab khi hoàn thành |

Mô hình dự toán:

~~~text
Tổng chi phí thay đổi
  ≈ chi phí blue production (đang có)
  + chi phí green (compute + storage + I/O)
  + backups / monitoring / data transfer phát sinh
  + chi phí giữ old blue sau switchover
  + công kỹ thuật thử nghiệm và phục hồi khi lỗi
~~~

**Không nhất thiết đúng 2× hóa đơn trong mọi cấu hình**, vì Aurora pricing, DB instance classes, storage, backups, read replicas và thời gian tồn tại khác nhau. Nhưng với staging có cấu hình gần production, phần compute/IO/storage của green thường là một khoản đáng kể cần được phê duyệt.

### 21.1. Tối ưu chi phí mà không giảm an toàn

Nên:

1. Tạo green gần với lịch rehearsal/cutover có thể thực hiện, không để nhiều tháng vô lý.
2. Nhưng **không cắt ngắn thời gian test** chỉ vì chi phí.
3. Chọn right-sized green phục vụ đúng performance test; tránh dùng instance quá nhỏ khiến benchmark sai lệch.
4. Giữ old blue đủ lâu theo recovery window đã duyệt, sau đó xóa có kiểm soát.
5. Đặt tags như `Project`, `Environment`, `ChangeId` và giám sát chi phí theo resource IDs thực.

## 22. IAM, bảo mật và phân quyền thay đổi

### 22.1. Tách quyền quan sát và quyền tác động production

| Nhóm | API/hoạt động chính | Ai nên sở hữu |
| --- | --- | --- |
| **Read-only inventory** | `rds:DescribeDBInstances`, `rds:DescribeDBClusters`, `rds:DescribeBlueGreenDeployments` | SRE/DBA/operator được phép |
| **Maintenance decision** | `rds:ApplyPendingMaintenanceAction`, Modify DB/cluster | DBA/Change approver |
| **Blue/Green create/modify** | `rds:CreateBlueGreenDeployment` và các quyền tài nguyên phụ trợ | DB platform operator |
| **Switchover** | `rds:SwitchoverBlueGreenDeployment` | Change executor được cấp quyền tạm thời |
| **Delete resources** | `rds:DeleteBlueGreenDeployment`, `rds:DeleteDBInstance`/`rds:DeleteDBCluster` | Người có phê duyệt cleanup riêng |
| **Backups/restore** | Snapshot/restore APIs, KMS | DBA/DR operator |
| **App DB credentials** | Database login/IAM DB auth với đúng resource ID | Application service identity |

Đây là định hướng quyền; **tên API và IAM actions phải tra Service Authorization Reference** theo engine và API hiện hành. RDS Blue/Green còn có những permissions phụ thuộc vào các resources được tạo/rename và service-linked roles. Không cấp `rds:*`/`AdministratorAccess` rộng khi chỉ cần Describe.

### 22.2. Chống thay đổi ngoài quy trình

- Bật MFA và audit CloudTrail cho thao tác RDS API.
- Kiểm soát **separation of duties** giữa người yêu cầu, người phê duyệt và người thực hiện switchover.
- Tách các tài khoản/role staging và production; không để script kiểm thử có quyền đổi DB production.
- Giữ KMS key policies, security groups, subnet groups, DB users/roles và secrets phù hợp khi chuyển resource identity.
- Gắn change ID và lưu source/target ARN/resource IDs trong hồ sơ vận hành.
- Hạn chế truy cập dữ liệu green giống production; staging synchronized **chứa dữ liệu thật** và cần cùng mức bảo mật/compliance.

### 22.3. Green không phải nơi thử nghiệm dữ liệu công khai

Green thường là bản sao của dữ liệu production đang đồng bộ. Không cho intern/dev truy cập green chỉ vì nhãn “staging”. Thử code với dữ liệu thật có thể vi phạm quy định dữ liệu cá nhân, log SQL parameters không cần thiết, hoặc gây nhiễu replication.

## 23. Bảng lỗi thường gặp và cách điều tra

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| **Upgrade target không xuất hiện** | Engine/version/Region không hỗ trợ hoặc thiếu bước trung gian | `describe-db-engine-versions`, release notes, support matrix |
| **Pending-reboot kéo dài** | Static parameter chưa được áp dụng qua restart phù hợp | Kiểm tra parameter apply type, lên kế hoạch reboot |
| **Bảo trì vượt maintenance window** | Window chỉ là thời điểm bắt đầu; thao tác lớn hơn dự kiến | Theo dõi RDS events và downtime budget, thông báo stakeholders |
| **Green tạo thất bại** | Engine/version/feature/topology/permissions không tương thích | Đọc trạng thái lỗi, support matrix, IAM và quota |
| **Replication degraded (PG)** | DDL/DCL, large objects hoặc thay đổi logical replication không hỗ trợ | Không switch, làm theo hướng dẫn recreate green |
| **Replication lag liên tục tăng** | High write rate, WAL/binlog pressure, green under-sized | Đo lag/CPU/IO, giảm writes hợp lệ, điều chỉnh capacity |
| **Switchover bị từ chối** | Guardrails: lag, long transactions, active writes green, external replication | Dừng thao tác, xử lý điều kiện chưa đạt |
| **Switchover timeout** | Replication catch-up chậm, connections/long DDL, outage | Xác minh state, rollback của switchover và liên hệ support khi cần |
| **App vẫn nối old writer** | JVM/OS DNS cache, hardcoded IP, stale pool, proxy mapping | Re-resolve endpoint, restart pool/app theo runbook |
| **JDBC read-only errors sau switch** | Đang nối old blue/read endpoint hoặc application session state | Kiểm tra resource IDs, writer endpoint, RDS Proxy và session |
| **SQL query p99 chậm sau upgrade** | Planner/statistics/parameter/extension thay đổi | EXPLAIN theo quyền, ANALYZE khi phù hợp, compare baseline |
| **Không truy cập DB bằng IAM auth** | Policy `rds-db:connect` gắn old resource ID | Cập nhật role/policy cho green identity |
| **DMS/CDC job ngừng chạy** | Checkpoint/source identity thay đổi | Tái cấu hình/khởi tạo replication theo tài liệu DMS |
| **Backup policy không theo resource mới** | AWS Backup selection/ARN/resource ID cũ | Cập nhật selection và xác minh snapshot/PITR |
| **Không PITR về ngày trước khi tạo green** | Lịch sử green không có thời điểm đó | Xem retained blue backups, manual snapshots và DR plan |
| **Old blue tiếp tục tính phí** | Sau switch vẫn giữ instances/backup để phục hồi | Review retention và xóa đúng lúc, không xóa quá sớm |
| **Tags green bị ghi đè** | Behavior đồng bộ tags của Blue/Green lúc switch | Cập nhật tags đúng nguồn/sau cutover, kiểm tra IAM/billing |
| **Downtime thấp nhưng duplicate payments** | App retry unknown-commit transaction không idempotent | Điều tra business logs, idempotency keys và payment reconciliation |

### 23.1. Thứ tự chẩn đoán tránh làm sự cố nặng hơn

1. Xác định chính xác **blue hay green đang phục vụ writes** và status deployment.
2. Thu thập **RDS events, engine logs, application errors, replication metrics**.
3. Phân loại vấn đề: **syntax/version**, **IAM/network**, **replication**, **data integrity**, **performance** hoặc **client reconnect**.
4. So với Runbook Go/No-Go. Không sửa schema/reboot/promote tùy ý khi B/G đang chạy.
5. Nếu có rủi ro mất dữ liệu, ưu tiên **bảo vệ dữ liệu và hạn chế writes** theo phê duyệt hơn là khôi phục traffic bằng một kết nối ngẫu nhiên.
6. Ghi quyết định, người duyệt, timestamps, endpoints và resource IDs để hậu kiểm.

## 24. Case study: nâng major PostgreSQL cho hệ thống đơn hàng

### 24.1. Bối cảnh

Một hệ thống thương mại điện tử:

~~~text
App:                   Java 21 / Spring Boot, ECS Fargate
DB:                    RDS PostgreSQL production, Multi-AZ DB instance
Workload:              300 reads/s, 80 writes/s (giả định)
Critical tables:       orders, payments, inventory_reservations
SLO:                   write outage < 60 giây mục tiêu
RPO:                   không chấp nhận mất đơn hàng được xác nhận
Version mục tiêu:      major mới, phải xác minh target được hỗ trợ
Change window:         giờ traffic thấp
~~~

Những thông số này chỉ phục vụ bài toán; không phải lời đảm bảo rằng Blue/Green sẽ đạt mục tiêu 60 giây với workload thật.

### 24.2. Kiểm tra trước

Đội DBA/SRE làm:

1. Đọc danh sách **ValidUpgradeTarget**, extension versions và RDS PostgreSQL Blue/Green support matrix.
2. Xác định nâng major có yêu cầu **logical replication** hay không và chính sách **cấm DDL/DCL trên blue** trong thời gian tồn tại B/G.
3. Kiểm tra các bảng nhận UPDATE/DELETE có primary key hoặc replica identity phù hợp.
4. Kiểm tra các job `pg_cron`, partition creation, large objects, sequences và foreign replication integrations.
5. Thực hành restore snapshot và ghi thời gian thực.
6. Lấy baseline query plans, API latency và HikariCP pool metrics.

### 24.3. Tạo green và chạy rehearsal

- Tạo B/G theo API/Console của RDS, chọn target version hợp lệ.
- Theo dõi replication lag, disk/WAL pressure và các warning `Replication degraded`.
- Kiểm thử schema/version, JDBC connectivity, top business queries **không ghi vào green**.
- Dựng bản sao độc lập để chạy migration/write benchmark khi cần.
- Chuẩn bị iam-db-auth role để nhận **green DB resource ID**, test connection readiness.
- Kiểm tra Aurora-specific requirements nếu kiến trúc thực tế là Aurora thay vì RDS instance.

### 24.4. Switchover và hậu kiểm

~~~text
T-30 phút   : rà soát lag, long transactions, backup, app/DB health
T-10 phút   : xác nhận approvals, drain long-running jobs an toàn
T-00 phút   : người được ủy quyền thực hiện switchover
T+01 phút   : xác nhận trạng thái từ AWS, test canary read/write
T+05 phút   : so p95/p99 API, DB errors, connections, event logs
T+30 phút   : kiểm tra business reconciliation và backup/PITR
T+24 giờ    : review performance/CDC/tags, quyết định giữ old blue
~~~

Thời điểm `T+01 phút` chỉ là checkpoint mục tiêu; khi switch chậm, **không kết luận lỗi hoặc success theo đồng hồ** mà dựa trạng thái dịch vụ và thực tế ứng dụng. Sau switch, source of truth là new production, không đảo lại old blue nếu chưa có dữ liệu tương ứng.

### 24.5. Bài học kiến trúc

RDS Blue/Green cho phép test trước, giúp cutover được quản lý và giảm rủi ro. Nhưng hệ thống vẫn cần:

- Idempotent business writes.
- JDBC reconnect và DNS caching đúng.
- Schema migration theo pattern tương thích replication.
- Backup/DR bảo vệ lịch sử cũ và dữ liệu mới.
- Observability theo DB resource ID, không chỉ endpoint string.
- Quy trình phê duyệt khi phải dừng/rollback sau cutover.

## 25. Bài tập thực hành và câu hỏi kiểm tra

### Bài 1 — Maintenance window có phải downtime tối đa 30 phút?

RDS có preferred maintenance window 01:00–01:30. Nâng cấp engine bắt đầu lúc 01:20 nhưng hoàn tất lúc 02:10. Hãy giải thích.

**Gợi ý:** window là khoảng **khởi đầu** công việc đủ điều kiện, không phải deadline tuyệt đối. Phải có outage budget và kế hoạch thông tin riêng.

### Bài 2 — `ApplyImmediately` vs pending maintenance

Một kỹ sư chỉnh static DB parameter, chọn “Apply during next maintenance window”, nhưng vài ngày sau status vẫn `pending-reboot`.

**Gợi ý:** một số static parameter changes không tự restart theo kỳ maintenance; cần kiểm tra parameter apply type và thực hiện reboot/failover theo quy trình được phê duyệt.

### Bài 3 — Minor hay major upgrade?

Team nâng PostgreSQL 15.x lên 15.y và 15.x lên 16.x. Trường hợp nào cần đánh giá compatibility sâu hơn?

**Gợi ý:** major upgrade 15→16 có nhiều rủi ro hơn, nhưng minor vẫn cần kiểm thử driver, extensions, performance và downtime.

### Bài 4 — MySQL/PostgreSQL khác nhau ở B/G replication thế nào?

Team dùng RDS PostgreSQL major upgrade và có cron tạo partition table trong blue mỗi đêm.

**Gợi ý:** PostgreSQL logical replication không tự hỗ trợ các DDL/DCL từ blue; thao tác tạo partition có thể làm replication degraded/chặn switch. Cần kế hoạch migration/cron phù hợp trước khi tạo B/G.

### Bài 5 — Green có được ghi dữ liệu test?

Một QA muốn dùng chính green đang replicate để chạy script tạo 100.000 đơn hàng test và xóa chúng sau đó.

**Gợi ý:** không phù hợp vì có thể xung đột replication hoặc tạo dữ liệu lệch. Dùng bản sao độc lập hoặc phương án test được DBA đánh giá.

### Bài 6 — Guardrail cảnh báo replica lag

Trước switch, lag tăng từ 2 giây lên 80 giây do blue có 1.000 writes/s. DBA nên làm gì?

**Gợi ý:** **NO-GO** cho đến khi hiểu và khắc phục nguyên nhân; xem apply throughput, WAL/binlog, green sizing, transactions và khả năng catch-up. Không tăng timeout để che lỗi mà chưa tính SLO.

### Bài 7 — RDS Proxy giúp zero downtime?

Ứng dụng dùng Proxy, nhưng có một số JDBC connections bị reset đúng lúc switchover.

**Gợi ý:** có thể xảy ra. Proxy/driver hỗ trợ routing/reconnect nhưng không bảo toàn transaction đang chạy; ứng dụng cần retry an toàn.

### Bài 8 — PITR sau cutover

Green tạo ngày 15, switch ngày 20, team xóa blue ngày 20. Ngày 22 cần restore về ngày 12.

**Gợi ý:** PITR của green không có thời điểm trước ngày green được tạo. Việc xóa blue quá sớm có thể phá yêu cầu recovery window; cần giữ blue/history/snapshots theo chính sách.

### Bài 9 — Rollback sau đã có writes mới

Sau switch, khách hàng thêm 500 đơn mới vào green. Team muốn đổi DNS về old blue để sửa lỗi query.

**Gợi ý:** không được đảo tùy tiện vì 500 đơn chưa có ở old blue. Đánh giá fix-forward/rollback ứng dụng trước; nếu đổi DB phải đồng bộ dữ liệu và có cutover/restore plan với RPO.

### Bài 10 — IAM database auth

Ứng dụng vẫn gọi cùng endpoint nhưng đăng nhập bằng IAM DB auth thất bại sau switch.

**Gợi ý:** kiểm tra policies `rds-db:connect` tham chiếu **DB resource ID** cũ; cập nhật quyền cho resource ID của green mới, không chỉ xem DB identifier.

### Bài 11 — RDS instance và Aurora cluster

Một engineer chỉ xem `describe-db-instances` rồi nâng cấp một Aurora DB cluster mà không kiểm tra cluster parameter group, reader topology và writer endpoint.

**Gợi ý:** thiếu thông tin. Aurora cần xem cluster-level engine version/maintenance/parameter groups và instance members, đặc biệt khi có readers/global topology.

### Bài 12 — Chi phí xanh lam/xanh lục

Blue đang dùng ba DB instances. Green cũng có ba instances và được giữ hai tuần, old blue tiếp tục được giữ 14 ngày sau switch. Cần dự toán những gì?

**Gợi ý:** compute/storage/I/O của green và old blue, read replicas, backups, log/monitoring, data transfer và chi phí nhân sự phục hồi. Không chỉ cộng thêm “phí switchover”.

### Bài 13 — Tại sao `SELECT version()` không đủ?

Green chạy đúng major version và SELECT 1 trả thành công nhưng latency sản xuất sau switch tăng gấp năm.

**Gợi ý:** query plans, statistics, parameters, indexes, extension hoặc pool behavior khác; cần baseline, load testing, Database Insights và p95/p99 trên top SQL.

### Bài 14 — Switchover báo timeout

RDS API trả lỗi timeout. Một kỹ sư muốn nhấn Switch liên tục cho đến khi thành công.

**Gợi ý:** trước hết kiểm tra deployment status, RDS events, writer identity, replication guardrails và trạng thái rollback của chính thao tác. Không retry không kiểm soát khi state chưa rõ.

## 26. Checklist production trước khi ký duyệt

- [ ] Đã xác định chính xác engine, source/target versions, Region, topology và support matrix.
- [ ] Release notes, extensions, stored procedures, JDBC/ORM compatibility và SQL modes đã được kiểm thử.
- [ ] Preferred maintenance window và pending maintenance/parameter reboot đã được ghi nhận.
- [ ] Backup/PITR/manual snapshot, retention và restore rehearsal đáp ứng RPO/RTO.
- [ ] Có baseline CloudWatch/Database Insights, business p95/p99 và capacity downstream.
- [ ] Blue/Green hỗ trợ đúng cấu hình; không có unsupported external replication/zero-ETL/feature constraints.
- [ ] PostgreSQL logical replication đã kiểm tra DDL/DCL, sequence, large objects, partitions, WAL/slots.
- [ ] Green replication healthy, lag ổn định, không có active test writes hoặc replication conflicts.
- [ ] Green đủ compute/storage/reader topology và không quá nhỏ để gây benchmark sai.
- [ ] App JDBC/connection pool, DNS caching, RDS Proxy và retry có idempotency được kiểm thử.
- [ ] Go/No-Go, owner, approved window, max outage và kênh liên lạc đã chốt.
- [ ] Có hậu kiểm new writer, đọc/ghi canary, business reconciliation và performance regression.
- [ ] IAM DB auth, resource IDs, CloudTrail, DMS/CDC, AWS Backup, tags và alarms đã có kế hoạch cập nhật.
- [ ] Đã hiểu rằng old blue **không nhận writes mới sau cutover**; rollback DB cần kế hoạch dữ liệu riêng.
- [ ] Đã tính PITR history của green và khoảng giữ blue cũ trước khi xóa.
- [ ] Đã dự toán chi phí green, old blue retention, snapshots, monitoring và thời gian kỹ sư.
- [ ] Có runbook dừng/hoãn, manual intervention policy và postmortem khi cutover lỗi.

## 27. Ghi nhớ

**Bảo trì và nâng cấp database là thay đổi có trạng thái, không chỉ là thao tác kỹ thuật trên Console.**

1. **Maintenance window** là thời gian ưu tiên bắt đầu công việc, không cam kết 30 phút là hết mọi outage. Minor/major upgrade, pending-reboot và `ApplyImmediately` có semantics khác nhau.
2. **RDS Multi-AZ và Aurora readers** cải thiện khả năng chịu lỗi, nhưng **không tự bảo đảm mọi nâng cấp zero downtime**; app phải chịu được reconnect.
3. **Blue/Green Deployments** tạo green synchronized để thử engine/parameter changes trước. AWS **switchover guardrails** giúp chuyển sang green an toàn hơn, nhưng vẫn có khoảng cắt writes/connections.
4. **PostgreSQL major upgrade** có thể dùng logical replication với giới hạn quan trọng: DDL/DCL, sequences, large objects, extensions và replication slots phải được kiểm tra kỹ.
5. **DNS endpoint giữ tên không có nghĩa resource ID không đổi**. IAM DB auth, metrics, backup/CDC/proxy/tags có thể cần cập nhật sau cutover.
6. **PITR history của green không tự nhận lịch sử trước khi tạo green**. Giữ old blue/snapshots theo recovery window và xác minh restore.
7. **Switchover thành công không có rollback database một nút** khi production mới đã nhận writes. Dữ liệu mới, idempotency, compensation và DR plan quyết định khả năng phục hồi.

Một quy trình tốt luôn có **preflight, compatibility test, backup drill, replication monitoring, Go/No-Go, cutover có kiểm soát và hậu kiểm**. Mục tiêu là giữ dữ liệu đúng và ứng dụng phục vụ ổn định, không chỉ nâng engine version lên số cao hơn.

### Tài liệu AWS chính thức

- [Maintaining a DB instance — Amazon RDS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_UpgradeDBInstance.Maintenance.html) — cửa sổ bảo trì, tác động và pending actions.
- [Upgrading a DB instance engine version](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_UpgradeDBInstance.Upgrading.html) — minor/major, target version và `ApplyImmediately`.
- [Amazon Aurora updates](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Updates.html) — bảo trì cluster và engine updates.
- [RDS Blue/Green Deployments overview](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/blue-green-deployments-overview.html) — kiến trúc blue và green.
- [RDS Blue/Green limitations and considerations](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/blue-green-deployments-considerations.html) — giới hạn, resource IDs và PITR.
- [RDS Blue/Green best practices](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/blue-green-deployments-best-practices.html) — staging và switchover preparation.
- [RDS Blue/Green switching](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/blue-green-deployments-switching.html) — guardrails, endpoint cutover và thời lượng.
- [PostgreSQL replication methods for RDS B/G](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/blue-green-deployments-replication-type.html) — physical/logical replication theo version.
- [Aurora Blue/Green overview](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/blue-green-deployments-overview.html) — engine hỗ trợ và Aurora Global Database.
- [Aurora Blue/Green limitations](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/blue-green-deployments-considerations.html) — cluster-specific constraints và PITR.
- [Aurora Blue/Green switching](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/blue-green-deployments-switching.html) — switchover, RDS Proxy và validation.
- [Amazon RDS AWS CLI reference](https://docs.aws.amazon.com/cli/latest/reference/rds/index.html) — describe, modify và switchover commands.
- [Amazon RDS Monitoring](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_Monitoring.html) — CloudWatch, events, logs.
- [Amazon RDS pricing](https://aws.amazon.com/rds/pricing/) và [Amazon Aurora pricing](https://aws.amazon.com/rds/aurora/pricing/) — kiểm soát chi phí khi chạy hai môi trường.
