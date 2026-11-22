# Hoàn thiện runbook với sơ đồ kiến trúc, chỉ số theo dõi và bằng chứng kiểm thử

Một runbook Oracle Database chỉ có thể dùng được trong sự cố khi người trực hiểu hệ thống đang chạy như thế nào, biết cần theo dõi những tín hiệu nào, có thể thực hiện các bước xử lý theo thứ tự và chứng minh rằng phương án phục hồi đã được kiểm thử. Tài liệu chỉ liệt kê lệnh SQL hoặc ghi “backup thành công” chưa đủ để vận hành một hệ thống production.

Runbook hoàn chỉnh kết nối bốn phần:

1. **Sơ đồ kiến trúc:** thể hiện ứng dụng, database, storage, backup, standby, network, monitoring và các failure domain.
2. **Chỉ số theo dõi:** xác định metric, nguồn dữ liệu, tần suất lấy mẫu, ngưỡng cảnh báo, người nhận và hành động tiếp theo.
3. **Quy trình vận hành:** mô tả pre-check, thao tác, xác minh, rollback/escalation và điều kiện kết thúc.
4. **Bằng chứng kiểm thử:** lưu lại môi trường, cấu hình, bước thực hiện, kết quả thực tế, timestamp, log, truy vấn và người xác nhận.

Bài học dùng Oracle Database 19c làm ví dụ chính. Các khái niệm cũng áp dụng cho những release mới hơn, RAC, Data Guard, multitenant và các triển khai on-premises/cloud. Tên service, view, quyền, lệnh Broker và cấu hình monitoring phải được xác nhận theo môi trường thật trước khi đưa vào runbook production.

## 1. Mục tiêu và phạm vi của runbook

Runbook là tài liệu thao tác dành cho DBA, SRE, vận hành ứng dụng, đội hạ tầng và người xử lý sự cố. Mỗi quy trình phải trả lời được:

- Khi nào cần thực hiện?
- Ai được phép thực hiện và ai phê duyệt?
- Hệ thống nào, database nào, service nào bị ảnh hưởng?
- Cần kiểm tra điều kiện gì trước khi bắt đầu?
- Thực hiện theo thứ tự nào?
- Kết quả mong đợi là gì?
- Dùng metric/log/query nào để xác nhận?
- Nếu bước nào thất bại thì dừng ở đâu, rollback hay escalation cho ai?
- Bằng chứng nào phải được lưu để kiểm toán và cải thiện lần sau?

### 1.1. Phạm vi ví dụ

Một hệ thống tham chiếu có thể gồm:
- Ứng dụng Java/API và connection pool.
- Oracle Database primary.
- Oracle Data Guard standby ở site khác.
- Storage cho datafiles, online redo và control files.
- Fast Recovery Area (FRA).
- RMAN backup trên storage độc lập.
- Monitoring, alerting, log collection và ticketing.
- DNS/service discovery, load balancer và network firewall.

Không phải mọi hệ thống đều có standby hoặc RAC. Runbook phải ghi rõ thành phần nào thực sự tồn tại và đánh dấu các quy trình không áp dụng. Không giữ sơ đồ mẫu nếu nó không đúng với topology đang chạy.

### 1.2. Định nghĩa trạng thái vận hành

| Trạng thái | Ý nghĩa | Hành động |
| --- | --- | --- |
| Healthy | Các thành phần hoạt động trong SLO | Tiếp tục giám sát |
| Warning | Metric lệch baseline nhưng chưa vượt ngưỡng sự cố | Điều tra xu hướng, tăng tần suất theo dõi |
| Degraded | Một thành phần lỗi hoặc năng lực dự phòng giảm | Mở incident, đánh giá rủi ro và khôi phục redundancy |
| Critical | Dịch vụ gián đoạn hoặc nguy cơ mất dữ liệu vượt chính sách | Kích hoạt incident commander và DR procedure |
| Recovering | Đang restore, failover hoặc phục hồi workload | Theo dõi bước recovery và ghi lại bằng chứng |
| Closed | Dịch vụ ổn định, dữ liệu được đối soát, incident có owner | Hoàn tất biên bản và action items |

Một database OPEN không đồng nghĩa toàn bộ dịch vụ Healthy. Phải kiểm tra service, PDB, listener, application connection, storage, standby và backup.

## 2. Sơ đồ kiến trúc tổng thể

Sơ đồ phải mô tả luồng request, luồng redo, luồng backup và luồng telemetry. Dùng tên logic nhất quán với inventory, ví dụ APP_SERVICE, ORCL_PRD, ORCL_STBY và FRA.

~~~mermaid
flowchart LR
    U[Users and batch clients] --> LB[Load balancer or API gateway]
    LB --> APP[Application nodes]
    APP --> POOL[JDBC connection pools]
    POOL --> SVC[Oracle database service]
    SVC --> PRI[(Primary database)]
    PRI --> STG[Datafiles and online redo storage]
    PRI --> FRA[(Fast Recovery Area)]
    PRI -->|Redo transport| STBY[(Data Guard standby)]
    PRI -->|RMAN backup| BKP[(Independent backup storage)]
    PRI --> MET[Metrics and alert collection]
    APP --> APM[Application logs and traces]
    MET --> OBS[Monitoring dashboard and alert manager]
    APM --> OBS
    STBY --> MET
    BKP --> CAT[Backup catalog and inventory]
    OBS --> ONCALL[On-call and incident process]
~~~

### 2.1. Các failure domain cần thể hiện

Sơ đồ production cần chỉ ra:
- Site/availability zone của primary và standby.
- Storage array, ASM disk group hoặc cloud volume chứa datafiles.
- Storage/FRA và backup repository.
- Network route giữa primary, standby, application và backup.
- DNS, listener, service name và load balancer.
- Monitoring plane và hệ thống log có nằm cùng failure domain hay không.
- Quyền truy cập DBA, OS, secret store và key management.

Nếu primary và backup nằm trên cùng storage array hoặc cùng site, sự cố storage/site có thể làm mất cả hai. Một bản backup chỉ được xem là độc lập khi failure domain và quyền xóa được kiểm soát phù hợp.

### 2.2. Sơ đồ luồng phục hồi

~~~mermaid
flowchart TD
    A[Incident detected] --> B{Primary database usable?}
    B -->|Yes| C{Datafiles healthy?}
    B -->|No| D{Standby available and eligible?}
    C -->|Yes| E[Resolve service or SQL issue]
    C -->|No| F[RMAN restore and recover]
    D -->|Yes| G[Validate lag and DR approval]
    D -->|No| H[Restore from independent backup]
    G --> I[Switchover or failover]
    F --> J[Open and validate database]
    H --> J
    I --> K[Validate new primary and application]
    E --> L[Monitor and reconcile]
    J --> L
    K --> L
    L --> M[Capture evidence and close incident]
~~~

Sơ đồ chỉ mô tả lựa chọn ở mức khái niệm. Quyết định failover phải dựa trên Data Guard state, redo gap, RPO, khả năng truy cập primary, quyền phê duyệt và runbook DR cụ thể. Không chuyển sang failover chỉ vì một dashboard báo đỏ.

## 3. Architecture inventory và thông tin bắt buộc

Mỗi môi trường cần một inventory có version và owner. Không để địa chỉ, mật khẩu hoặc secret trực tiếp trong Markdown; tham chiếu tới secret vault/CMDB theo ID.

| Nhóm | Trường cần lưu | Ví dụ giá trị minh họa |
| --- | --- | --- |
| Environment | Environment, region, site | PROD / site-a |
| Database | DB_NAME, DB_UNIQUE_NAME, DBID | ORCL / ORCL_PRD / inventory reference |
| Release | Oracle version, RU, COMPATIBLE | 19c RU cụ thể |
| Topology | Single instance/RAC, CDB/PDB | RAC 2 nodes, CDB có APP_PDB |
| Role | PRIMARY/PHYSICAL STANDBY | PRIMARY |
| Service | Service name, PDB, preferred/available instances | APP_SERVICE |
| Network | Listener, SCAN, VIP, DNS, port | Theo CMDB |
| Storage | ASM disk group, volume, mount, capacity | DATA, FRA |
| Backup | RMAN device, repository, retention, encryption | Disk/SBT, recovery catalog |
| DR | Standby DB_UNIQUE_NAME, transport mode, apply mode | ORCL_STBY |
| Security | Wallet/keystore, credential vault reference | Secret IDs |
| Monitoring | Metric source, dashboard, alert route | Observability project |
| Ownership | DBA, application owner, storage, network, security | Team/on-call reference |

### 3.1. Thu thập thông tin database

~~~sql
SELECT
    name,
    dbid,
    db_unique_name,
    open_mode,
    database_role,
    log_mode,
    protection_mode,
    current_scn
FROM v$database;
~~~

Phiên bản và patch SQL:

~~~sql
SELECT banner
FROM v$version
ORDER BY banner;

SELECT
    patch_id,
    patch_type,
    action,
    status,
    action_time,
    description
FROM dba_registry_sqlpatch
ORDER BY action_time DESC;
~~~

Kiểm tra instance:

~~~sql
SELECT
    instance_name,
    host_name,
    version,
    status,
    database_status,
    startup_time
FROM v$instance;
~~~

Trong RAC, dùng GV$ views và giữ cột INST_ID để thấy trạng thái từng instance.

### 3.2. Cập nhật inventory

Cập nhật inventory khi:
- Thêm/bớt instance, PDB, service hoặc standby.
- Đổi listener, SCAN, DNS, firewall hoặc network route.
- Thay storage, ASM disk group, FRA hoặc backup target.
- Nâng Oracle Home/RU/COMPATIBLE.
- Đổi retention, encryption, keystore hoặc backup catalog.
- Đổi owner, on-call, escalation hoặc quyền truy cập.

Mỗi thay đổi cần ngày hiệu lực, người cập nhật và ticket/change ID. Sơ đồ cũ phải được đánh dấu obsolete để tránh người trực sử dụng nhầm.

## 4. RACI và quyền thực hiện

Một runbook không nên giao toàn bộ quyền quyết định cho người đang trực nếu thao tác ảnh hưởng dữ liệu hoặc DR.

| Hoạt động | DBA on-call | Incident commander | App owner | Infrastructure | Security |
| --- | --- | --- | --- | --- | --- |
| Điều tra database alert | R | I | C | C | I |
| Restart application pool | C | A | R | C | I |
| Thay đổi database parameter | R | A | C | C | I |
| RMAN restore/recover | R | A | C | C | C |
| Data Guard failover | R | A | C | C | I |
| Storage/network repair | C | A | I | R | I |
| Mở quyền/secret recovery | C | A | I | C | R |
| Đối soát dữ liệu sau recovery | R | A | R | C | I |
| Đóng incident | C | A | R | C | C |

R = Responsible, A = Accountable, C = Consulted, I = Informed. Tổ chức cần điền tên team, số trực, kênh escalation và người thay thế. Ma trận này là mẫu, không phải phân công mặc định.

### 4.1. Quyền tối thiểu

- Application user chỉ có quyền object cần thiết.
- Monitoring account chỉ đọc các view/metric được phê duyệt.
- RMAN operator có quyền backup/restore theo role.
- SYSDBA chỉ dùng khi quy trình yêu cầu.
- OS account quản lý Oracle Home/storage tách khỏi application account.
- Secret, wallet và encryption key được lấy từ secret management có audit.
- Quyền failover và thay đổi service được giới hạn theo vai trò.

Không đưa password, wallet password, private key hoặc chuỗi kết nối có credential vào runbook, log evidence hay screenshot chia sẻ.

## 5. RPO, RTO, SLO và điều kiện phục hồi

### 5.1. RPO

Recovery Point Objective là lượng dữ liệu tối đa tổ chức chấp nhận mất. RPO phải được đo bằng khoảng cách giữa thời điểm dữ liệu cuối cùng có thể phục hồi và thời điểm sự cố.

Ví dụ:
- RPO 5 phút: recovery point không được cũ hơn 5 phút.
- RPO 0 cho một số giao dịch đã xác nhận: cần giải pháp bảo đảm commit/redo theo kiến trúc phù hợp, không thể suy ra chỉ từ tần suất RMAN backup.

### 5.2. RTO

Recovery Time Objective là thời gian tối đa từ khi dịch vụ gián đoạn đến khi dịch vụ được khôi phục ở mức đã định nghĩa.

RTO cần nói rõ điểm bắt đầu/kết thúc:
- Bắt đầu: incident được xác nhận hay service health check fail?
- Kết thúc: database OPEN, service accept connection hay business transaction thành công?
- Có bao gồm DNS/cache, application warm-up và data reconciliation không?

### 5.3. SLO vận hành

Ví dụ SLO cần được tổ chức phê duyệt:
- Tỷ lệ thành công của transaction nghiệp vụ.
- P95/P99 response time của API.
- Database availability.
- Tối đa redo apply lag.
- Tuổi backup gần nhất.
- Thời gian phục hồi qua diễn tập.

Không dùng một SLO chung cho tất cả service. Ghi rõ cửa sổ đo, loại request, loại trừ bảo trì và nguồn đo.

### 5.4. Mục tiêu và kết quả đo

| Chỉ số | Target minh họa | Kết quả diễn tập | Pass condition |
| --- | --- | --- | --- |
| RPO | 5 phút | Điền sau test | Thực tế không vượt target |
| RTO | 60 phút | Điền sau test | Service business-ready trong target |
| Standby apply lag | 60 giây | Điền sau test | Không vượt chính sách khi chuyển vai trò |
| Backup age | Theo lịch backup | Điền sau test | Có recovery chain đầy đủ |
| Restore validation | Theo lịch tháng | Điền sau test | Tất cả file/redo cần thiết đọc được |
| Application smoke test | 100% test critical | Điền sau test | Không có critical failure |

Target trên chỉ là ví dụ để xây dựng runbook; phải thay bằng cam kết thực tế. Không tự coi giá trị minh họa là SLA production.

## 6. Danh mục chỉ số cần theo dõi

Chia metric theo lớp giúp người trực xác định nhanh lỗi nằm ở application, database, storage, network, standby hay backup.

| Lớp | Chỉ số | Nguồn chính | Tác động |
| --- | --- | --- | --- |
| Application | Request rate, error rate, P95/P99 latency | APM/API gateway | Người dùng có bị ảnh hưởng không |
| Connection pool | Active/idle/waiting, timeout, borrow latency | JVM/pool metrics | Ứng dụng có lấy được connection không |
| Database | Availability, active sessions, DB time, CPU | V$INSTANCE, V$SYSMETRIC | Database có đang phục vụ không |
| SQL | Top SQL, elapsed, buffer gets, executions | AWR/ASH theo quyền và license | Query nào gây tải |
| Concurrency | Blocking sessions, lock wait, deadlock | V$SESSION, alert log | Transaction bị chặn |
| Storage | Tablespace, ASM, filesystem, IOPS/latency | DBA views và OS/storage monitoring | Nguy cơ hết dung lượng hoặc I/O chậm |
| Recovery | FRA, archive destination, redo generation | V$RECOVERY_FILE_DEST, V$ARCHIVE_DEST_STATUS | Khả năng archive/recover |
| Backup | Last successful backup, duration, bytes, validation | V$RMAN_BACKUP_JOB_DETAILS | Có thể restore không |
| Data Guard | Transport lag, apply lag, gap, role | V$DATAGUARD_STATS, V$ARCHIVE_DEST_STATUS | RPO và DR readiness |
| Security | Failed logon, privilege change, audit events | Unified audit/monitoring | Rủi ro truy cập |
| Platform | Host CPU, memory, filesystem, network | OS/cloud monitoring | Tài nguyên ngoài database |

### 6.1. Availability và role

~~~sql
SELECT
    name,
    open_mode,
    database_role,
    log_mode,
    protection_mode,
    switchover_status
FROM v$database;
~~~

~~~sql
SELECT
    instance_name,
    host_name,
    status,
    database_status,
    logins,
    active_state
FROM v$instance;
~~~

Với CDB:

~~~sql
SELECT
    name,
    open_mode,
    restricted
FROM v$pdbs
ORDER BY name;
~~~

Một CDB có thể OPEN nhưng PDB ứng dụng chưa OPEN hoặc service không đăng ký. Dashboard cần hiển thị cả PDB/service readiness.

### 6.2. System metrics

~~~sql
SELECT
    metric_name,
    value,
    metric_unit,
    begin_time,
    end_time
FROM v$sysmetric
WHERE metric_name IN (
    'Database CPU Time Ratio',
    'Database Wait Time Ratio',
    'Average Active Sessions',
    'Executions Per Sec',
    'Physical Reads Per Sec',
    'Redo Generated Per Sec',
    'User Transaction Per Sec',
    'Current Logons Count'
)
ORDER BY metric_name, end_time DESC;
~~~

V$SYSMETRIC chứa các metric theo interval. Metric có thể xuất hiện cho các nhóm interval khác nhau; collector nên ghi nhận interval/group phù hợp và không cộng/trộn mẫu ngắn với mẫu dài.

### 6.3. Session đang chờ và blocking

~~~sql
SELECT
    sid,
    serial#,
    username,
    status,
    blocking_session_status,
    blocking_instance,
    blocking_session,
    wait_class,
    event,
    seconds_in_wait,
    sql_id
FROM v$session
WHERE blocking_session IS NOT NULL
   OR (status = 'ACTIVE' AND wait_class <> 'Idle')
ORDER BY seconds_in_wait DESC;
~~~

Trong RAC, dùng GV$SESSION và thêm INST_ID. Không kết luận mọi wait đều là lỗi; xem thời lượng, wait class, SQL, blocking chain và tác động tới transaction nghiệp vụ.

### 6.4. Tablespace usage

~~~sql
WITH free_space AS (
    SELECT tablespace_name, SUM(bytes) AS free_bytes
    FROM dba_free_space
    GROUP BY tablespace_name
),
file_space AS (
    SELECT
        tablespace_name,
        SUM(bytes) AS allocated_bytes,
        SUM(
            CASE
                WHEN autoextensible = 'YES' THEN maxbytes
                ELSE bytes
            END
        ) AS potential_max_bytes
    FROM dba_data_files
    GROUP BY tablespace_name
)
SELECT
    f.tablespace_name,
    ROUND(f.allocated_bytes / 1024 / 1024) AS allocated_mb,
    ROUND(NVL(s.free_bytes, 0) / 1024 / 1024) AS free_mb,
    ROUND(
        (f.allocated_bytes - NVL(s.free_bytes, 0))
        / NULLIF(f.allocated_bytes, 0) * 100,
        1
    ) AS used_allocated_pct,
    ROUND(
        (f.allocated_bytes - NVL(s.free_bytes, 0))
        / NULLIF(f.potential_max_bytes, 0) * 100,
        1
    ) AS used_potential_max_pct
FROM file_space f
LEFT JOIN free_space s
    ON s.tablespace_name = f.tablespace_name
ORDER BY used_allocated_pct DESC;
~~~

Đây là truy vấn cho permanent datafiles. TEMP tablespace, undo, bigfile tablespace, PDB và autoextend policy cần dashboard/queries riêng. Phải theo dõi cả dung lượng filesystem/ASM chứa datafile vì autoextend không thể vượt storage thực tế.

### 6.5. TEMP usage

~~~sql
SELECT
    tablespace_name,
    ROUND(tablespace_size / 1024 / 1024) AS tablespace_mb,
    ROUND(allocated_space / 1024 / 1024) AS allocated_mb,
    ROUND(free_space / 1024 / 1024) AS free_mb
FROM dba_temp_free_space;
~~~

Nếu TEMP tăng bất thường, xác định session/SQL sử dụng TEMP, sort/hash spill, parallel query và thời gian tồn tại. Không chỉ tăng tempfile mà không xác định nguyên nhân.

### 6.6. Fast Recovery Area

~~~sql
SELECT
    name,
    ROUND(space_limit / 1024 / 1024 / 1024, 2) AS limit_gb,
    ROUND(space_used / 1024 / 1024 / 1024, 2) AS used_gb,
    ROUND(space_reclaimable / 1024 / 1024 / 1024, 2) AS reclaimable_gb,
    number_of_files,
    ROUND(space_used / NULLIF(space_limit, 0) * 100, 1) AS used_pct
FROM v$recovery_file_dest;
~~~

Theo dõi tốc độ tăng FRA, archived log generation và reclaimable space. Space reclaimable không có nghĩa mọi file có thể xóa ngay bằng OS; RMAN/FRA quản lý file theo retention và backup policy.

### 6.7. Archive destination

~~~sql
SELECT
    dest_id,
    status,
    type,
    destination,
    error,
    gap_status,
    synchronization_status
FROM v$archive_dest_status
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
~~~

Cột có thể khác theo release/configuration; xác nhận view definition ở target. Alert nếu destination ERROR, có gap hoặc transport không đồng bộ theo policy.

### 6.8. Data Guard lag

~~~sql
SELECT
    name,
    value,
    unit,
    time_computed,
    datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag', 'apply finish time');
~~~

Chạy ở standby theo cách Oracle tài liệu hóa. Nếu metric không có giá trị hoặc timestamp cũ, đó cũng là tín hiệu cần điều tra. Đối chiếu Broker status, archive gap và alert log trước khi kết luận standby khỏe.

### 6.9. RMAN backup history

~~~sql
SELECT
    session_key,
    input_type,
    status,
    start_time,
    end_time,
    elapsed_seconds,
    output_bytes_display,
    output_device_type
FROM v$rman_backup_job_details
ORDER BY start_time DESC
FETCH FIRST 30 ROWS ONLY;
~~~

Job thành công không tự chứng minh restore được. Cần kiểm tra backup piece, archived redo, control file autobackup, encryption key và validation/restore drill.

### 6.10. Invalid objects

~~~sql
SELECT
    owner,
    object_type,
    COUNT(*) AS invalid_count
FROM dba_objects
WHERE status = 'INVALID'
GROUP BY owner, object_type
ORDER BY invalid_count DESC;
~~~

Theo dõi baseline invalid object trước/sau release. Không coi mọi INVALID là incident; một số object có thể invalid có chủ ý hoặc được compile on demand. Cần phân biệt object mới invalid, object critical và lỗi compile thực tế.

## 7. Alert threshold và cách tránh cảnh báo giả

Threshold phải được hiệu chỉnh theo baseline, dung lượng, workload, RPO/RTO và khả năng xử lý. Các con số dưới đây chỉ là điểm bắt đầu để thiết kế alert, không phải ngưỡng Oracle bắt buộc.

| Metric | Warning minh họa | Critical minh họa | Hành động đầu tiên |
| --- | --- | --- | --- |
| Tablespace used | Trên 80% | Trên 90% hoặc dự báo đầy trong cửa sổ vận hành | Kiểm tra growth, free space, autoextend và storage |
| FRA used | Trên 80% | Trên 90% hoặc archive bị chặn | Kiểm tra reclaimable, backup và archive destination |
| Data Guard apply lag | Trên 30 giây | Vượt RPO hoặc trên 5 phút theo policy | Kiểm tra transport/apply, network và standby workload |
| Backup age | Gần tới hạn job kế tiếp | Quá RPO hoặc không có recovery chain | Kiểm tra RMAN job, media và archived logs |
| Blocking | Block kéo dài trên 30 giây | Critical transaction bị block trên 2 phút | Xác định blocker, SQL và business owner |
| API error rate | Vượt baseline | Vượt SLO/critical transaction failure | Correlate APM, pool và DB |
| API P95 latency | Vượt baseline trong nhiều interval | Vượt SLO liên tục | Phân tích trace và SQL |
| Invalid objects | Tăng so với baseline | Critical package/view invalid | Xem compile errors và release change |
| Archive destination | Có dấu hiệu chậm/gap | STATUS ERROR hoặc không archive được | Kiểm tra storage, network và alert log |
| Host storage | Dự báo hết trong maintenance window | Filesystem/ASM gần đầy | Mở rộng hoặc giải phóng theo quy trình |

### 7.1. Dùng nhiều điều kiện thay vì một điểm đo

Alert tốt thường yêu cầu:
- Vượt threshold trong nhiều sample liên tiếp.
- Có duration tối thiểu.
- Loại trừ maintenance window đã đăng ký.
- Có recovery threshold thấp hơn alert threshold để tránh flap.
- Correlate với error rate, queue hoặc user impact.
- Có owner, severity và runbook link.

Ví dụ, tablespace 85% có thể bình thường nếu autoextend còn nhiều và growth thấp; 70% có thể critical nếu tốc độ tăng khiến đầy trước lần bảo trì kế tiếp.

### 7.2. Capacity forecast

Theo dõi growth rate theo ngày/tuần:

~~~text
days_to_full = usable_capacity_remaining / average_daily_growth
~~~

Dùng growth trung bình và percentile cao trong giai đoạn peak. Nếu storage tăng đột biến theo batch, forecast theo average đơn thuần có thể đánh giá thấp rủi ro.

## 8. Dashboard vận hành

Một dashboard chính nên có các vùng:

| Vùng dashboard | Nội dung | Câu hỏi cần trả lời |
| --- | --- | --- |
| Service health | API success, error, latency, availability | Người dùng có bị ảnh hưởng? |
| Database state | Role, open mode, instance, PDB, service | Database có sẵn sàng? |
| Load | DB time, AAS, CPU, transactions, executions | Tải có tăng bất thường? |
| Wait/concurrency | Blocking, top wait, deadlock | Có tranh chấp? |
| Capacity | Tablespace, TEMP, undo, FRA, ASM/filesystem | Có nguy cơ hết tài nguyên? |
| Recovery | Backup age, backup status, archive gap | Có thể phục hồi? |
| Data Guard | Role, transport/apply lag, gap | DR có đáp ứng RPO? |
| Change | Release, RU, invalid objects, deployment events | Có thay đổi gần đây? |
| Evidence | Last restore drill, test result, runbook version | Khả năng phục hồi đã được chứng minh? |

### 8.1. Dashboard theo service

Không chỉ hiển thị database-wide metric. Nếu CDB có nhiều PDB hoặc nhiều service, cần phân biệt:
- Service name.
- PDB.
- Instance.
- Application module/action.
- Business transaction.
- Database user/schema.

Dùng MODULE/ACTION/CLIENT_IDENTIFIER từ ứng dụng để correlate SQL/session với request nghiệp vụ khi có thể. Tránh ghi PII hoặc secret vào client identifier.

### 8.2. AWR/ASH và license

AWR, ASH và một số tính năng Diagnostic/Tuning Pack có điều kiện cấp phép. Trước khi đưa truy vấn/report vào runbook, xác nhận license của tổ chức. Có thể dùng V$SYSMETRIC, V$SESSION, SQL monitoring hoặc công cụ observability được phê duyệt tùy quyền và license.

## 9. Quy trình vận hành hàng ngày

### 9.1. Đầu ca

1. Xem dashboard service health và active alert.
2. Xác nhận database role/open mode, instance và PDB.
3. Xem lỗi alert log kể từ lần bàn giao trước.
4. Kiểm tra tablespace, TEMP, FRA, ASM/filesystem.
5. Kiểm tra archive destination và Data Guard lag.
6. Kiểm tra RMAN job gần nhất và backup age.
7. Kiểm tra invalid object mới phát sinh.
8. Xác nhận change/maintenance đang diễn ra.
9. Ghi timestamp, người trực và trạng thái vào shift log.

### 9.2. Cuối ca

- Ghi alert chưa xử lý và owner.
- Ghi transaction/job dài hoặc storage growth bất thường.
- Ghi backup/standby issue và thời hạn cần khắc phục.
- Ghi thay đổi đã thực hiện, command log và ticket.
- Chuyển giao incident có severity và next action rõ ràng.
- Xác nhận người nhận bàn giao.

### 9.3. Shift log mẫu

~~~text
Date/time (timezone):
Environment / DB_UNIQUE_NAME:
Current role / open mode:
On-call owner:
Service health:
Active incidents:
Backup last success:
Archive / FRA status:
Data Guard lag:
Capacity risks:
Changes in progress:
Actions performed:
Next action / due time:
Evidence references:
Handover accepted by:
~~~

## 10. Runbook xử lý database unavailable

### Trigger

- Application không kết nối được database service.
- Health check database thất bại liên tục.
- Listener/service không đăng ký.
- Database/instance không ở trạng thái phục vụ.
- PDB hoặc service ứng dụng đóng.

### Quy trình

1. Xác nhận phạm vi ảnh hưởng từ APM/API và nhiều client.
2. Kiểm tra DNS, network route, listener và service registration.
3. Kết nối DBA bằng kênh quản trị đã phê duyệt.
4. Kiểm tra V$INSTANCE, V$DATABASE và PDB state.
5. Đọc alert log/ADR để tìm lỗi đầu tiên.
6. Kiểm tra storage, ASM, filesystem, FRA và archive destination.
7. Xác định lỗi là database, instance, service, host hay network.
8. Nếu instance còn hoạt động, xử lý service/PDB theo procedure đã duyệt.
9. Nếu database không thể phục hồi tại site, kích hoạt DR decision.
10. Sau khi service lên, chạy application smoke test và đối soát transaction.

### Bằng chứng cần lưu

- Timestamp đầu tiên phát hiện và xác nhận.
- Alert log/incident trace liên quan.
- Kết quả instance/database/PDB/service.
- Network/listener check.
- Thời điểm service accept connection.
- API success/error và P95 sau phục hồi.
- Business transaction test.
- Tổng RTO đo được.

Không restart database liên tục khi chưa đọc alert log; restart lặp có thể làm mất bằng chứng và kéo dài thời gian recovery.

## 11. Runbook tablespace/FRA/archive destination gần đầy

### Trigger

- Tablespace/FRA vượt threshold.
- Archive destination có ERROR.
- Database không thể archive redo hoặc session bị ảnh hưởng.
- Filesystem/ASM không còn dung lượng.

### Quy trình

1. Xác định container, tablespace, datafile, destination và filesystem/ASM liên quan.
2. Xem growth rate và dự báo thời điểm đầy.
3. Kiểm tra autoextend, maxbytes và storage thực tế.
4. Kiểm tra RMAN retention, backup status và archived log coverage.
5. Xác định file có thể reclaim theo Oracle/RMAN metadata.
6. Chọn hành động được phê duyệt: mở rộng storage/datafile, điều chỉnh backup destination hoặc cleanup qua RMAN.
7. Không xóa archived log/backup piece trực tiếp bằng OS.
8. Theo dõi archive tiếp tục hoạt động và FRA giảm/tăng ổn định.
9. Xác minh database không còn lỗi liên quan.
10. Ghi lại dung lượng trước/sau và nguyên nhân growth.

### Truy vấn xác nhận

~~~sql
SELECT
    name,
    space_limit,
    space_used,
    space_reclaimable,
    number_of_files
FROM v$recovery_file_dest;
~~~

~~~sql
SELECT
    dest_id,
    status,
    destination,
    error
FROM v$archive_dest
WHERE status <> 'INACTIVE';
~~~

Mọi thao tác xóa backup phải theo retention/recovery policy. Kiểm tra đủ backup copy và archived redo trước khi xóa input.

## 12. Runbook blocking session

### Trigger

- Transaction nghiệp vụ bị chờ lâu.
- Connection pool hết connection do session không kết thúc.
- Lock wait tăng và API latency vượt SLO.

### Quy trình

1. Xác định request/transaction bị ảnh hưởng và mức độ nghiệp vụ.
2. Lấy blocking chain, SID/SERIAL#, INST_ID trong RAC.
3. Thu thập SQL_ID, module, action, username và thời gian chờ.
4. Xác định blocker có phải batch/DDL/deployment không.
5. Liên hệ application owner nếu transaction thuộc ứng dụng.
6. Ưu tiên để transaction hoàn tất hoặc ứng dụng xử lý theo policy.
7. Chỉ terminate session sau khi đánh giá rollback time, dữ liệu và approval.
8. Theo dõi lock wait, active session và API latency sau xử lý.
9. Ghi SQL, session identifiers, thời gian và người phê duyệt.

Không kill session chỉ vì nó đứng đầu danh sách. Session có thể đang chạy transaction quan trọng; rollback có thể mất nhiều thời gian hơn chờ xử lý tự nhiên.

## 13. Runbook backup failure và xác minh recovery

### Trigger

- RMAN job FAILED/COMPLETED WITH WARNINGS.
- Backup age vượt lịch.
- Backup piece không truy cập được.
- Control file autobackup hoặc archived log backup thiếu.
- RESTORE VALIDATE thất bại.

### Quy trình

1. Lưu RMAN log đầy đủ và job key.
2. Xác định input type, channel, device, piece và lỗi đầu tiên.
3. Kiểm tra storage, media manager, credential và encryption wallet.
4. Kiểm tra archived log sequence/thread coverage.
5. Kiểm tra control file autobackup và SPFILE.
6. Sửa nguyên nhân, chạy lại phần backup cần thiết.
7. LIST BACKUP và CROSSCHECK theo quy trình.
8. Chạy RESTORE PREVIEW/VALIDATE trên phạm vi được chọn.
9. Lập kế hoạch restore drill nếu backup chain bị ảnh hưởng.
10. Cập nhật backup age/RPO status và incident.

### Kiểm tra RMAN

~~~text
SHOW ALL;
LIST BACKUP SUMMARY;
LIST BACKUP OF DATABASE;
LIST BACKUP OF CONTROLFILE;
LIST BACKUP OF SPFILE;
LIST BACKUP OF ARCHIVELOG ALL;
RESTORE DATABASE PREVIEW;
RESTORE DATABASE VALIDATE;
~~~

RESTORE VALIDATE xác minh khả năng đọc backup pieces mà RMAN dự kiến dùng. Nó không thay thế việc restore database lên host riêng và chạy kiểm thử ứng dụng.

## 14. Runbook Data Guard lag và DR readiness

### 14.1. Điều tra lag

1. Xác nhận primary/standby role.
2. Kiểm tra transport lag và apply lag cùng timestamp.
3. Kiểm tra archive destination, gap và network.
4. Xác định standby redo log và managed recovery state.
5. Kiểm tra standby storage/CPU/I/O.
6. Đọc Broker status và alert log trên hai site.
7. Xác định lag tăng do transport, apply throughput hay workload.
8. So sánh lag với RPO; thông báo owner nếu có nguy cơ vi phạm.
9. Ghi nhận thời điểm lag trở lại bình thường.

### 14.2. Switchover có kế hoạch

Trước switchover:
- Xác nhận change window và approval.
- Xác nhận cả primary và standby healthy.
- Xác nhận transport/apply không có gap theo policy.
- Kiểm tra standby sẵn sàng chuyển role.
- Kiểm tra application connection/service routing.
- Xác nhận backup và rollback/reversal plan.
- Thông báo application owner.

Dùng Data Guard Broker nếu kiến trúc đã cấu hình Broker. Cú pháp minh họa trong DGMGRL:

~~~text
SHOW CONFIGURATION;
SHOW DATABASE VERBOSE '<standby_db_unique_name>';
VALIDATE DATABASE VERBOSE '<standby_db_unique_name>';
SWITCHOVER TO '<standby_db_unique_name>';
SHOW CONFIGURATION;
~~~

Các lệnh và validation option phụ thuộc Broker version/configuration. Chỉ chạy sau khi kiểm tra đúng database unique name, role, state và approval.

Sau switchover:
- Xác nhận role mới ở cả hai database.
- Xác nhận service/PDB mở và đăng ký.
- Xác nhận application pool kết nối site mới.
- Chạy business smoke test.
- Kiểm tra transport/apply theo chiều mới.
- Ghi thời gian bắt đầu/kết thúc và RPO/RTO đo được.

### 14.3. Failover ngoài kế hoạch

Failover có thể làm mất dữ liệu chưa được transport/apply tới standby. Incident commander và DBA phải đánh giá:
- Primary còn có thể truy cập không?
- Standby có redo gap không?
- Data Guard protection mode và transport state?
- RPO thực tế có thể bảo đảm?
- Có nguy cơ split-brain hoặc primary cũ vẫn phục vụ?
- Có thể reinstate primary cũ hay cần rebuild?

Không dùng lệnh failover như một bước chữa lỗi listener/service thông thường. Thực hiện theo DR runbook đã được diễn tập và lưu approval.

## 15. Runbook restore/recover database

### 15.1. Điều kiện trước restore

- Xác định DBID, DB_UNIQUE_NAME và target SCN/time.
- Xác nhận backup pieces và archived redo cần thiết.
- Có control file/SPFILE hoặc PFILE tạm.
- Có password/keystore nếu backup encrypted/TDE.
- Chuẩn bị Oracle Home và storage đích.
- Xác nhận mapping file name/ASM/OMF.
- Xác nhận recovery catalog và autobackup format.
- Cô lập database restore khỏi production service.
- Xác nhận người phê duyệt và business owner.

### 15.2. Luồng restore/recover

~~~mermaid
flowchart TD
    A[Identify incident and recovery target] --> B[Locate DBID, control file and SPFILE]
    B --> C[Verify backup pieces and keys]
    C --> D[Prepare host, Oracle Home and storage]
    D --> E[Restore control file and mount]
    E --> F[Restore datafiles]
    F --> G[Apply archived redo to target]
    G --> H[Open according to recovery path]
    H --> I[Validate files, objects and application]
    I --> J[Record RPO/RTO and evidence]
~~~

### 15.3. Lệnh RMAN minh họa

~~~text
STARTUP MOUNT;
RESTORE DATABASE;
RECOVER DATABASE;
ALTER DATABASE OPEN;
~~~

Đây là luồng khái quát khi control file hiện tại và recovery path cho phép. Khi restore control file từ backup, incomplete recovery hoặc PITR, lệnh open có thể cần RESETLOGS. Chọn đúng procedure theo tình trạng thực tế; không chạy OPEN RESETLOGS tùy tiện.

### 15.4. Sau restore

- Kiểm tra database role/open mode và incarnation.
- Kiểm tra datafile online/read-write phù hợp.
- Kiểm tra invalid objects và compile errors.
- Kiểm tra sequence, job, database link và credential dependencies.
- Xác minh PDB/service.
- Chạy transaction nghiệp vụ thử.
- Đối soát dữ liệu theo checkpoint.
- Tạo backup mới sau recovery theo policy.
- Cập nhật Data Guard/replication nếu có.

## 16. Kế hoạch kiểm thử và bằng chứng

Mỗi test case phải có ID, mục tiêu, prerequisite, bước thực hiện, expected result, actual result và evidence reference. Kết quả PASS chỉ được ghi sau khi bằng chứng đã lưu.

### 16.1. Test matrix

| Test ID | Nhóm | Mục tiêu | Expected result | Evidence |
| --- | --- | --- | --- | --- |
| DB-AV-01 | Availability | Kết nối service/PDB | Login và query health thành công | SQL output, app log |
| DB-AV-02 | Availability | Restart instance theo change plan | Instance/service trở lại trong RTO | Alert log, timestamps |
| DB-BK-01 | Backup | RMAN backup database | Job hoàn tất, pieces được catalog | RMAN log, LIST BACKUP |
| DB-BK-02 | Backup | Control file/SPFILE autobackup | Có autobackup đọc được | RMAN log, backup listing |
| DB-BK-03 | Backup | Restore validate | Tất cả backup piece cần thiết đọc được | RMAN validate log |
| DB-RC-01 | Recovery | Restore database ở host lab | Database mở và business test pass | Restore log, smoke test |
| DB-RC-02 | Recovery | Point-in-time recovery | Khôi phục tới target SCN/time | RMAN log, SCN query |
| DB-DG-01 | Data Guard | Redo transport/apply | Lag trong target, không gap | Broker output, lag metrics |
| DB-DG-02 | DR | Switchover diễn tập | Role/service đổi đúng, app hoạt động | Broker log, app test |
| DB-CAP-01 | Capacity | Cảnh báo tablespace/FRA | Alert đúng severity và owner | Alert event, dashboard |
| DB-PERF-01 | Performance | Peak workload | Latency/throughput trong SLO | APM report, DB metrics |
| DB-SEC-01 | Security | Least privilege | User không có quyền ngoài phạm vi | Grant report, audit |
| DB-CHG-01 | Change | Apply RU trong staging | Component valid, regression pass | Patch inventory, test report |
| DB-APP-01 | Application | Critical business flow | Create/read/update/commit đúng | API trace, SQL evidence |

### 16.2. Evidence package

Một test evidence package nên gồm:
- Test ID và test case version.
- Environment, DB_UNIQUE_NAME, release/RU, COMPATIBLE.
- Host/instance/PDB/service.
- Thời điểm bắt đầu/kết thúc có timezone.
- Người thực hiện và reviewer.
- Change/ticket ID.
- Precondition và dữ liệu test.
- Lệnh/script đã chạy.
- Expected và actual result.
- Exit code và log đầy đủ.
- Query output/metric snapshot.
- Screenshot/dashboard link khi có ích.
- File checksum và artifact location.
- PASS/FAIL/BLOCKED cùng lý do.
- Defect/incident link và retest reference.

Không chỉ lưu screenshot màu xanh. Bằng chứng cần cho phép người khác tái hiện hoặc xác minh kết quả.

### 16.3. Mẫu biên bản test

~~~text
TEST ID:
Test name:
Runbook version:
Environment:
DB_UNIQUE_NAME / PDB / Service:
Oracle release / RU / COMPATIBLE:
Host / Instance:
Change or incident ID:
Executor:
Reviewer:
Start time (timezone):
End time (timezone):
Preconditions:
Test data:
Steps and commands:
Expected result:
Actual result:
Metrics before:
Metrics during:
Metrics after:
Log/artifact references:
Checksum:
Result: PASS / FAIL / BLOCKED
Defect or follow-up:
Approval:
~~~

### 16.4. Quy tắc đặt tên evidence

Dùng một quy ước dễ tìm và không chứa secret:

~~~text
<environment>/<year>/<month>/<test-id>/<run-id>/
    metadata.txt
    commands.log
    database-state.txt
    metrics-before.csv
    metrics-during.csv
    metrics-after.csv
    application-smoke-test.log
    rman-output.log
    broker-status.log
    screenshots/
    checksums.sha256
~~~

Artifact có thể được lưu ở evidence repository, object storage hoặc hệ thống quản lý test đã phê duyệt. Runbook chỉ lưu reference, không nhúng dump database hoặc dữ liệu cá nhân.

## 17. Cách đo RPO và RTO trong diễn tập

### 17.1. RPO thực tế

Ghi:
- Timestamp giao dịch cuối đã được xác nhận ở primary trước sự cố.
- Timestamp/SCN cuối đã có mặt và có thể recover ở target.
- Data Guard transport/apply lag hoặc archive sequence.
- Kết quả reconciliation sau recovery.

RPO thực tế là chênh lệch giữa điểm dữ liệu cuối được xác nhận trước sự cố và điểm dữ liệu cuối được khôi phục. Với workload nghiệp vụ, cần kiểm tra transaction ID hoặc business sequence thay vì chỉ dựa trên SCN.

### 17.2. RTO thực tế

Chia RTO thành các mốc:
1. Detection.
2. Triage và declaration.
3. Decision/approval.
4. Database recovery hoặc role transition.
5. Service/network routing.
6. Application warm-up.
7. Business validation.
8. Service declared restored.

Ghi từng timestamp. Nhờ vậy có thể thấy thời gian mất nhiều nhất nằm ở chờ phê duyệt, restore datafile, apply redo, DNS, connection pool hay validation.

### 17.3. Mẫu timeline

| Mốc | Timestamp | Elapsed từ incident | Evidence |
| --- | --- | --- | --- |
| Alert fired | Điền | 0 | Monitoring event |
| Incident declared | Điền | Điền | Ticket |
| Recovery approved | Điền | Điền | Approval record |
| Database available | Điền | Điền | SQL health query |
| Service available | Điền | Điền | Listener/service check |
| Application smoke test pass | Điền | Điền | API test |
| Business owner accepts | Điền | Điền | Sign-off |
| Incident closed | Điền | Điền | Post-incident report |

## 18. Kiểm thử hiệu năng và capacity

### 18.1. Baseline

Thu thập baseline trong:
- Normal workload.
- Peak workload.
- Batch window.
- Backup window.
- Reporting/ETL window.
- Maintenance/recovery test.

Ghi throughput, P95/P99, error rate, DB time, AAS, CPU, I/O latency, redo rate, TEMP, active sessions và connection pool utilization.

### 18.2. Load test

Test cần mô tả:
- Workload mix và tỷ lệ read/write.
- Số virtual users/concurrent sessions.
- Ramp-up và duration.
- Dataset size và data distribution.
- Cache state.
- Background jobs.
- Warm-up.
- Success/error criteria.

Không chỉ test bằng một SELECT đơn giản. Dùng transaction nghiệp vụ đại diện, kiểm tra commit/rollback và concurrency.

### 18.3. Capacity forecast

Theo dõi:
- Datafile growth.
- FRA/archive growth.
- TEMP peak.
- Undo usage.
- ASM/filesystem headroom.
- Backup repository capacity.
- Connection pool maximum.
- Process/session limit.
- Standby apply throughput.

Capacity plan phải dự báo tới thời điểm mở rộng tiếp theo, có buffer cho peak và maintenance.

## 19. Kiểm thử security và change management

### 19.1. Security evidence

- Danh sách account/service account.
- Role và system privilege.
- Object grants.
- Failed logon và privileged access audit.
- Wallet/keystore status.
- TLS/network encryption.
- Backup encryption state.
- Quyền truy cập backup/evidence repository.
- Kết quả rà soát secret và credential trong script.

### 19.2. Change evidence

Mỗi thay đổi database cần:
- Change ID và owner.
- DDL/script version.
- Pre-change backup hoặc recovery point.
- Impact assessment.
- Maintenance window.
- Pre-check output.
- Execution log.
- Post-check output.
- Rollback/forward-fix criteria.
- Approval và sign-off.

### 19.3. Patch/RU runbook

Trước khi apply RU:
1. Kiểm tra Oracle Home inventory và SQL patch registry.
2. Kiểm tra component status và invalid object baseline.
3. Xác nhận backup/recovery readiness.
4. Kiểm tra Data Guard/standby compatibility.
5. Diễn tập trên staging.
6. Kiểm tra application/driver compatibility.
7. Xác định rollback/restore strategy.
8. Sau patch, chạy datapatch theo quy trình release.
9. Kiểm tra registry, component, invalid object và alert log.
10. Chạy regression, smoke test và performance comparison.

## 20. Runbook versioning và change history

Runbook cũng là một artifact được quản lý. Mỗi bản cần:
- Runbook ID và version.
- Owner và approver.
- Ngày hiệu lực.
- Database/environment áp dụng.
- Oracle release/RU.
- Link tới architecture diagram.
- Link dashboard/alert.
- Link test evidence.
- Change history.
- Review date tiếp theo.

Ví dụ change log:

| Version | Ngày | Thay đổi | Owner | Approval |
| --- | --- | --- | --- | --- |
| 1.0 | Điền | Bản đầu tiên | DBA team | Điền |
| 1.1 | Điền | Thêm metric FRA và archive lag | DBA/SRE | Điền |
| 1.2 | Điền | Cập nhật DR drill và RTO thực tế | DBA/App | Điền |

Sau một incident, runbook phải được cập nhật nếu phát hiện bước thiếu, metric sai hoặc evidence không đủ. Không sửa nội dung đã phê duyệt mà không tăng version/change record.

## 21. Post-incident review và cải tiến

Sau incident hoặc DR drill:
1. Xây timeline từ monitoring, alert log, application log và ticket.
2. Xác định impact và dữ liệu bị ảnh hưởng.
3. Tính RPO/RTO thực tế.
4. Xác định detection gap và thời gian chờ.
5. Xác định thao tác nào thành công/thất bại.
6. Xác định bằng chứng còn thiếu.
7. Tạo action item có owner/due date.
8. Cập nhật dashboard, alert và runbook.
9. Retest action item quan trọng.
10. Đóng incident khi business owner xác nhận.

Review tập trung vào hệ thống và quy trình, không chỉ tìm cá nhân gây lỗi. Action item phải đo được, có người chịu trách nhiệm và có ngày hoàn tất.

## 22. Ví dụ runbook hoàn chỉnh cho một sự cố FRA tăng nhanh

### Bối cảnh

Database ORCL_PRD ở ARCHIVELOG mode. FRA tăng nhanh trong batch window và có nguy cơ đầy. Ứng dụng ghi giao dịch liên tục; Data Guard standby đang apply redo.

### Trigger và impact

- FRA warning vượt ngưỡng nội bộ.
- Archive generation rate cao hơn baseline.
- Dung lượng reclaimable thấp.
- Archive destination có thể chuyển ERROR nếu không xử lý.

### Pre-check

~~~sql
SELECT
    name,
    space_limit,
    space_used,
    space_reclaimable
FROM v$recovery_file_dest;

SELECT
    dest_id,
    status,
    destination,
    error
FROM v$archive_dest
WHERE status <> 'INACTIVE';

SELECT
    name,
    value,
    unit,
    time_computed
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag');
~~~

### Hành động

1. Xác nhận alert và mức tăng dung lượng.
2. Kiểm tra RMAN job gần nhất, backup archived log và backup destination.
3. Kiểm tra Data Guard transport/apply và archive gap.
4. Kiểm tra retention policy và delete policy.
5. Xác định file reclaimable qua RMAN/FRA metadata.
6. Nếu cần tăng capacity, xác nhận storage còn headroom và thực hiện change được duyệt.
7. Nếu backup job lỗi, xử lý media/permission/space trước khi cleanup.
8. Dùng RMAN DELETE OBSOLETE theo retention policy sau khi DBA review report.
9. Không xóa file FRA bằng OS.
10. Theo dõi FRA và archive destination sau xử lý.

### Xác minh

- FRA utilization trở về mức an toàn hoặc có forecast đủ dài.
- Archive destination không ERROR.
- Archived redo tiếp tục được tạo.
- Data Guard lag trong target.
- RMAN backup mới hoàn tất.
- Application error rate/latency không tăng.
- Không có archived log gap ngoài chính sách.

### Evidence

- Dashboard trước/sau.
- Output V$RECOVERY_FILE_DEST.
- Output V$ARCHIVE_DEST_STATUS.
- RMAN SHOW ALL, REPORT OBSOLETE và log backup/delete.
- Data Guard lag snapshot.
- Ticket/change ID và người phê duyệt.
- Timestamp bắt đầu/kết thúc.
- Dung lượng giải phóng và growth rate sau xử lý.

## 23. Checklist bàn giao runbook

### Architecture
- [ ] Sơ đồ primary/standby và application path đúng với production.
- [ ] Có service, listener, PDB, storage và backup target.
- [ ] Failure domain và network dependency được ghi.
- [ ] Có owner và escalation contact.

### Metrics
- [ ] Metric có tên, nguồn, đơn vị và interval.
- [ ] Threshold có warning/critical và recovery condition.
- [ ] Có dashboard và alert route.
- [ ] Có baseline và capacity forecast.
- [ ] Metric được kiểm tra trên RAC/PDB nếu có.

### Procedures
- [ ] Có trigger, pre-check, steps, expected result.
- [ ] Có stop condition và escalation.
- [ ] Có rollback/forward-fix hoặc DR decision.
- [ ] Có verification và post-check.
- [ ] Có quyền/phê duyệt cho thao tác rủi ro.

### Evidence
- [ ] Test ID và test case version.
- [ ] Environment/version/RU/COMPATIBLE.
- [ ] Timestamp có timezone.
- [ ] Commands, logs, SQL output và metrics.
- [ ] Expected/actual và PASS/FAIL/BLOCKED.
- [ ] RPO/RTO đo được.
- [ ] Artifact có checksum và owner.
- [ ] Reviewer/approver sign-off.

### Governance
- [ ] Runbook có version, owner, approval và ngày review.
- [ ] Secret không nằm trong tài liệu.
- [ ] Có change history.
- [ ] Có post-incident update process.
- [ ] Có lịch diễn tập tiếp theo.

## 24. Lab: xây dựng runbook từ database lab

Thực hiện trong môi trường Oracle lab có quyền đọc dictionary và RMAN phù hợp. Không chạy thao tác phá hủy trên production.

### Bước 1: Ghi nhận baseline

~~~sql
SELECT name, dbid, db_unique_name, open_mode, database_role, log_mode
FROM v$database;

SELECT instance_name, host_name, status, startup_time
FROM v$instance;

SELECT name, space_limit, space_used, space_reclaimable
FROM v$recovery_file_dest;
~~~

Lưu output cùng timestamp và Oracle release/RU.

### Bước 2: Tạo architecture diagram

Vẽ application, service, database, storage, FRA, backup, standby và monitoring. Ghi rõ phần nào không tồn tại trong lab.

### Bước 3: Tạo metric inventory

Chọn ít nhất một metric cho:
- Availability.
- Database load.
- Blocking.
- Tablespace/FRA.
- Backup.
- Data Guard nếu lab có standby.
- Application success/latency nếu có API.

Với mỗi metric, ghi source, unit, interval, owner, threshold và runbook link.

### Bước 4: Kiểm tra backup evidence

Trong RMAN:

~~~text
SHOW ALL;
LIST BACKUP SUMMARY;
LIST BACKUP OF DATABASE;
RESTORE DATABASE PREVIEW;
RESTORE DATABASE VALIDATE;
~~~

Lưu log, thời gian và result. Nếu không có backup hoặc không có quyền validate, ghi BLOCKED kèm lý do; không tự ghi PASS.

### Bước 5: Thử alert path

Trong môi trường test, tạo một điều kiện cảnh báo an toàn đã được phê duyệt hoặc replay metric giả lập trong monitoring test project. Xác nhận alert có đúng severity, owner, route và runbook link.

Không cố tình làm đầy production tablespace/FRA để thử alert.

### Bước 6: Diễn tập restore hoặc Data Guard

Chọn một test phù hợp với môi trường:
- Restore database vào host/lab độc lập.
- Restore một datafile lab.
- Data Guard switchover trong maintenance window.
- Application reconnect sau service transition.

Ghi timestamps, RPO/RTO, SQL health và application smoke test.

### Bước 7: Hoàn thiện evidence package

Lưu metadata, logs, query output, metrics, checksum và reviewer. Liên kết evidence với test ID và runbook version.

### Bước 8: Bàn giao

DBA, application owner và infrastructure owner xác nhận:
- Sơ đồ đúng.
- Alert route hoạt động.
- Quy trình có thể thực hiện.
- Evidence đủ để review.
- Action item còn lại có owner và deadline.

## 25. Tài liệu Oracle tham khảo

- [Oracle Database 19c Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — quản trị database, instance, service, storage và vận hành.
- [Oracle Database 19c Backup and Recovery User's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/) — RMAN, backup, restore, recovery và validation.
- [Oracle Database 19c Data Guard Concepts and Administration](https://docs.oracle.com/en/database/oracle/oracle-database/19/sbydb/) — redo transport, apply, switchover, failover và Broker.
- [Oracle Database 19c Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — dynamic performance views, initialization parameters và dictionary reference.
- [Oracle Database 19c Performance Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/) — database performance monitoring và tuning.
- [Oracle Database 19c Licensing Information User Manual](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/) — điều kiện cấp phép cho các tính năng tùy chọn.
- [Oracle Database 19c Automatic Diagnostic Repository](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/diagnosing-and-resolving-problems.html) — alert log, incident và diagnostic data.
- [Oracle Data Guard Broker](https://docs.oracle.com/en/database/oracle/oracle-database/19/dgbkr/) — quản lý cấu hình Data Guard và thao tác chuyển role.

Khi hoàn thiện runbook cho production, hãy thay toàn bộ tên minh họa, threshold, RPO/RTO, service, owner và storage bằng dữ liệu đã xác nhận từ hệ thống. Mọi lệnh restore, failover, cleanup và thay đổi cấu hình phải theo đúng release, quyền, change approval và DR procedure của tổ chức.
