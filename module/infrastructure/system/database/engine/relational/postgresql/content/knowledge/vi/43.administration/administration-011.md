# Xây dựng runbook và bằng chứng kiểm tra sau thao tác trong PostgreSQL

Quản trị PostgreSQL không kết thúc khi một lệnh SQL trả về thành công. Sau thao tác như thay đổi cấu hình, tạo role, chạy migration, restore backup, vacuum bảng lớn hoặc chuyển primary, người vận hành cần chứng minh hệ thống đã đạt trạng thái mong muốn và các dịch vụ liên quan vẫn hoạt động.

**Runbook** là tài liệu hướng dẫn thực hiện một quy trình vận hành theo thứ tự rõ ràng. Nó xác định điều kiện bắt đầu, người chịu trách nhiệm, lệnh cần chạy, bằng chứng cần lưu, tiêu chí thành công, điều kiện dừng, phương án rollback và cách thông báo kết quả.

**Bằng chứng sau thao tác** là các dữ liệu có thể kiểm tra lại, chẳng hạn SQL output, system catalog, server logs, monitoring snapshots, backup metadata, checksum, application health check và change record. Bằng chứng phải gắn với đúng môi trường, thời điểm, đối tượng và người thực hiện.

Một runbook tốt giúp nhiều kỹ sư thực hiện cùng một quy trình nhất quán, giảm phụ thuộc vào trí nhớ cá nhân và rút ngắn thời gian điều tra khi kết quả không như dự kiến.

~~~mermaid
flowchart TD
    A["Yêu cầu thay đổi / sự cố"] --> B["Runbook và phạm vi"]
    B --> C["Pre-check: trạng thái ban đầu"]
    C --> D{"Điều kiện cho phép?"}
    D -->|"Không"| X["Dừng / escalation"]
    D -->|"Có"| E["Thực hiện từng bước"]
    E --> F["Thu thập bằng chứng"]
    F --> G{"Post-check đạt?"}
    G -->|"Không"| H["Rollback / recovery"]
    H --> I["Kiểm tra sau rollback"]
    G -->|"Có"| J["Xác nhận và đóng change"]
    I --> K["Ghi incident / handoff"]
    J --> L["Lưu evidence và cập nhật runbook"]
~~~

Bài học thuộc chương **Quản trị**, module **Database Engine Relational PostgreSQL**. Chúng ta sẽ tìm hiểu cách thiết kế runbook, phân quyền trách nhiệm, kiểm soát thay đổi, lưu bằng chứng, xác minh kết quả, rollback, escalation và các ví dụ vận hành PostgreSQL thường gặp.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích runbook là gì và vì sao cần dùng trong quản trị PostgreSQL.
2. Phân biệt runbook, checklist, SOP, change record và incident report.
3. Xác định phạm vi, mục tiêu và rủi ro của một thao tác.
4. Viết preconditions, execution steps, decision gates và postconditions.
5. Xác định người thực hiện, người phê duyệt và người xác minh.
6. Thu thập trạng thái trước thao tác để làm baseline.
7. Chọn bằng chứng phù hợp từ SQL, catalog, logs, metrics và hệ điều hành.
8. Kiểm tra tính đầy đủ, toàn vẹn và khả năng truy xuất của evidence.
9. Xây dựng rollback và recovery plan có điều kiện kích hoạt rõ ràng.
10. Thiết kế runbook cho backup, restore, migration, role, vacuum, config và failover.
11. Xác minh database/application sau thao tác.
12. Ghi lại kết quả, sai lệch và quyết định cuối cùng.
13. Quản lý phiên bản runbook và kiểm thử định kỳ.
14. Tránh các lỗi vận hành do lệnh thiếu kiểm soát hoặc bằng chứng không đầy đủ.

## 2. Runbook, checklist và change record

Các tài liệu vận hành có liên quan nhưng có mục đích khác nhau.

| Tài liệu | Mục đích | Ví dụ |
| --- | --- | --- |
| Runbook | Hướng dẫn quy trình từ đầu đến cuối | Chuyển primary, restore backup |
| Checklist | Xác nhận các điều kiện/bước đã hoàn thành | Kiểm tra backup trước migration |
| SOP | Quy trình vận hành chuẩn ở mức tổ chức | Quy tắc quản lý role và quyền |
| Change record | Ghi nhận thay đổi cụ thể, thời gian và phê duyệt | Nâng cấp PostgreSQL production |
| Incident report | Ghi nhận sự cố, tác động, nguyên nhân và khắc phục | Primary mất kết nối |
| Evidence package | Tập bằng chứng chứng minh trạng thái/kết quả | SQL output, logs, metrics, checksum |

Runbook mô tả cách thực hiện một loại công việc. Change record mô tả lần thực hiện cụ thể. Evidence package lưu bằng chứng của lần chạy đó.

Một runbook có thể được dùng nhiều lần, nhưng evidence phải thuộc một lần chạy cụ thể và có timestamp/environment rõ ràng.

## 3. Nguyên tắc thiết kế runbook

Một runbook cần đáp ứng các nguyên tắc sau:

**Có thể thực hiện:** Mỗi bước chỉ rõ ai làm, ở đâu, dùng quyền gì và chạy lệnh nào.

**Có thể xác minh:** Mỗi bước quan trọng có expected result và evidence source.

**Có điều kiện dừng:** Khi precondition không đạt, kết quả khác kỳ vọng hoặc rủi ro vượt ngưỡng, runbook phải chỉ rõ dừng ở đâu.

**Có phương án phục hồi:** Xác định rollback, forward-fix hoặc restore/recovery; không ghi chung chung “rollback nếu lỗi”.

**Có giới hạn phạm vi:** Nêu database, cluster, schema, table, role, host, environment và đối tượng bị ảnh hưởng.

**Có tính phiên bản:** Ghi PostgreSQL major version, OS, extension và phiên bản công cụ liên quan khi khác biệt có thể ảnh hưởng lệnh.

**Có thể bàn giao:** Kỹ sư khác đọc được và tiếp tục thực hiện mà không cần dựa vào trí nhớ của người viết.

**Có kiểm soát bảo mật:** Không lưu password, token, private key hoặc connection string chứa secret trong runbook/evidence.

## 4. Cấu trúc chuẩn của một runbook

Một mẫu runbook thực tế nên có các phần:

1. Metadata và mục đích.
2. Phạm vi và hệ thống bị ảnh hưởng.
3. Trigger và mức độ ưu tiên.
4. Roles và responsibilities.
5. Preconditions.
6. Rủi ro và tác động dự kiến.
7. Backup/restore readiness.
8. Execution steps.
9. Expected results và evidence.
10. Decision gates.
11. Rollback/recovery.
12. Post-operation verification.
13. Communication và escalation.
14. Closure criteria.
15. Revision history.

### Mẫu metadata

~~~yaml
runbook_id: RB-DB-014
title: PostgreSQL schema migration
owner: Database Operations
service: orders-db
environment: production
postgres_major_version: "16"
risk_level: high
estimated_duration: "30 minutes"
last_reviewed: "2026-10-01"
review_interval: "6 months"
approver_role: change_manager
operator_role: database_operator
verifier_role: application_owner
~~~

Metadata là ví dụ. Không đưa hostname/IP thật, credential hoặc thông tin bí mật vào tài liệu được chia sẻ rộng.

## 5. Xác định phạm vi và mục tiêu

Trước khi viết lệnh, cần trả lời:

- Cluster/database nào bị ảnh hưởng?
- Primary hay standby?
- Schema/table/index/role nào?
- Ứng dụng và service nào phụ thuộc?
- Thao tác có cần downtime không?
- Thay đổi có ảnh hưởng đến dữ liệu hay quyền truy cập không?
- Thao tác có thể chạy lại an toàn không?
- Phạm vi rollback là gì?

Ví dụ mục tiêu mơ hồ:

> Tối ưu bảng orders.

Mục tiêu có thể kiểm chứng:

> Tạo index concurrently trên orders(created_at, status) trong database sales, không khóa ghi dài hạn; xác nhận index hợp lệ, query plan sử dụng được khi phù hợp và không làm tăng error rate hoặc replication lag vượt ngưỡng trong 15 phút quan sát.

Mục tiêu càng cụ thể, bằng chứng và điều kiện kết thúc càng rõ.

## 6. Trigger và điều kiện bắt đầu

Runbook phải nói rõ khi nào được sử dụng.

Ví dụ:

- Change đã được phê duyệt.
- Backup gần nhất hoàn tất và restore test đáp ứng policy.
- Replication lag nằm trong giới hạn.
- Không có maintenance khác đang chạy.
- Disk còn đủ dung lượng.
- Có operator và verifier sẵn sàng.
- Application owner đã xác nhận maintenance window.
- Rollback/recovery path đã được chuẩn bị.

Với incident runbook, trigger có thể là alert cụ thể như connection failures, disk pressure, replication failure hoặc database unavailable.

Không dùng một runbook maintenance bình thường cho một sự cố có trạng thái dữ liệu chưa xác định nếu quy trình không bao phủ trường hợp đó.

## 7. Roles và trách nhiệm

Các vai trò thường gặp:

| Vai trò | Trách nhiệm |
| --- | --- |
| Requester | Mô tả nhu cầu và tác động mong muốn |
| Change owner | Chịu trách nhiệm thay đổi tổng thể |
| Operator | Thực hiện lệnh theo runbook |
| Approver | Xem xét và phê duyệt thay đổi theo policy |
| Verifier | Kiểm tra kết quả độc lập |
| Application owner | Xác nhận hành vi ứng dụng |
| Incident commander | Điều phối khi có sự cố |
| Security/Compliance | Xem xét quyền, audit và dữ liệu nhạy cảm |

Trong thao tác rủi ro cao, nên tách người thực hiện và người xác minh. Người chạy lệnh không nên tự đánh dấu thành công chỉ dựa trên việc command exit code bằng 0.

Runbook cần ghi role, không nhất thiết ghi tên cá nhân để tránh nhanh chóng lỗi thời. Change record của từng lần chạy mới ghi người thực hiện cụ thể.

## 8. Preconditions: kiểm tra trước thao tác

Pre-check xác nhận môi trường đang ở trạng thái đủ an toàn để bắt đầu.

Nhóm kiểm tra phổ biến:

### Database identity và version

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS database_user,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    version() AS server_version;
~~~

Kết hợp với inventory/cluster manager để xác định node là primary hay standby. Không dựa vào hostname đơn lẻ nếu endpoint có thể route tới nhiều node.

### Role và quyền

~~~sql
SELECT
    rolname,
    rolsuper,
    rolcreatedb,
    rolcreaterole,
    rolreplication,
    rolcanlogin
FROM pg_roles
WHERE rolname = current_user;
~~~

Không cần thu thập toàn bộ role attributes vào mọi evidence package. Chỉ ghi những quyền liên quan tới thao tác.

### Database size và disk

~~~sql
SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS database_size
FROM pg_database
WHERE datallowconn
ORDER BY pg_database_size(datname) DESC;
~~~

Dung lượng filesystem phải được kiểm tra ở OS/storage layer; SQL database size không bao gồm mọi WAL, archive, log và backup volume.

### Active sessions và transactions

~~~sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    state,
    xact_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
ORDER BY xact_start NULLS LAST;
~~~

Kiểm tra long-running transactions, idle-in-transaction, lock waits và maintenance jobs trước thao tác có thể cần exclusive lock hoặc restart.

### Replication state

Trên primary:

~~~sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

Trên standby:

~~~sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn() AS replayed_lsn;
~~~

Chỉ thu thập các query phù hợp với loại cluster. Single-node database không có standby vẫn có thể hợp lệ; ghi rõ topology thay vì coi không có rows là lỗi.

## 9. Baseline trước thao tác

Baseline là trạng thái tham chiếu để so sánh sau thay đổi.

Tùy công việc, baseline có thể gồm:

- Database/cluster identity và PostgreSQL version.
- Current primary/standby role.
- Database/table/index sizes.
- Active sessions và long transactions.
- Replication lag.
- Disk free space.
- CPU/memory/I/O utilization.
- Query latency và transaction throughput.
- Error rate.
- Checkpoint/WAL counters.
- Backup status và restore point.
- Application health checks.

### Lấy baseline có thể so sánh

Counters trong PostgreSQL thường tích lũy từ lần reset hoặc server start. Nếu muốn so sánh, lưu timestamp, stats_reset và giá trị tại thời điểm t1; lấy lại tại t2 rồi tính delta.

Không so sánh hai counters nếu chúng đã reset giữa hai lần lấy mẫu. Không lấy một snapshot sau thao tác rồi suy luận trạng thái trước đó.

## 10. Execution step phải có expected result

Một bước chỉ ghi “chạy lệnh ALTER TABLE” là chưa đủ.

Mẫu tốt:

| Trường | Nội dung |
| --- | --- |
| Step | 04 |
| Actor | Database operator |
| Target | sales.public.orders |
| Action | Thêm cột nullable |
| Command | ALTER TABLE ... ADD COLUMN ... |
| Expected result | Command thành công; column tồn tại với type/default mong muốn |
| Evidence | SQL output và catalog query |
| Stop condition | Lock wait vượt ngưỡng hoặc session bị block |
| Recovery | Đánh giá trạng thái DDL, chạy forward-fix hoặc rollback theo khả năng |

Mỗi bước quan trọng nên có command và verification query tương ứng. Nếu command không idempotent, ghi rõ không được chạy lại khi chưa xác định trạng thái hiện tại.

## 11. Evidence là gì?

Evidence là dữ liệu có thể kiểm tra lại để chứng minh một điều cụ thể.

Ví dụ:

| Bằng chứng | Chứng minh điều gì |
| --- | --- |
| SQL command output | Lệnh đã trả kết quả |
| Catalog query | Object/configuration tồn tại với thuộc tính mong muốn |
| Server logs | PostgreSQL đã ghi nhận sự kiện/lỗi |
| Monitoring snapshot | Metrics tại một khoảng thời gian |
| Backup metadata | Backup tool ghi nhận backup hoàn tất |
| Restore test output | Backup có thể được phục hồi trong test |
| Checksum/row counts | Một số thuộc tính dữ liệu được đối chiếu |
| Application smoke test | Ứng dụng thực hiện được luồng nghiệp vụ |
| Change record | Ai thực hiện, khi nào, theo phê duyệt nào |
| Reviewer sign-off | Người có trách nhiệm xác nhận kết quả |

Một ảnh chụp màn hình đơn lẻ thường không đủ nếu thiếu timestamp, environment, command context và nguồn dữ liệu.

## 12. Evidence phải gắn với context

Mỗi evidence quan trọng nên có metadata:

- Runbook ID và version.
- Change/incident ID.
- Environment.
- Cluster/database.
- Host/node hoặc endpoint.
- PostgreSQL version.
- Timestamp và timezone.
- Operator.
- Step number.
- Command/query hoặc dashboard panel.
- Expected result.
- Actual result.
- Evidence file/reference.
- Redaction status.

Ví dụ:

~~~yaml
evidence_id: EV-2026-1042-07
runbook_id: RB-DB-014
runbook_version: "2.1"
change_id: CHG-2026-1042
environment: production
database: sales
postgres_version: "16.4"
step: "07"
captured_at: "2026-11-14T08:30:00Z"
operator: db_operator_1
source: "psql query output"
purpose: "Verify new index validity"
result: pass
artifact: "CHG-2026-1042/07-index-validity.txt"
~~~

Không ghi secret, full connection URI có password, hoặc query parameter nhạy cảm vào metadata.

## 13. Evidence có thể truy xuất và toàn vẹn

Một evidence package cần:

- Có tên file nhất quán.
- Có timestamp/timezone.
- Có ID liên kết change/incident.
- Có nguồn tạo evidence.
- Có quyền đọc được kiểm soát.
- Có retention policy.
- Không bị ghi đè âm thầm.
- Có checksum hoặc immutable storage khi yêu cầu audit cao.
- Có thông tin redaction nếu đã che dữ liệu.

Có thể tạo SHA-256 checksum ở môi trường lưu trữ:

~~~bash
sha256sum evidence-file.txt
~~~

Trên Windows:

~~~powershell
Get-FileHash .\evidence-file.txt -Algorithm SHA256
~~~

Checksum giúp phát hiện file thay đổi sau khi hash được tạo; nó không chứng minh nội dung ban đầu là đúng. Cần bảo vệ cả checksum manifest và nguồn evidence.

## 14. Phân biệt bằng chứng thực hiện và bằng chứng kết quả

**Bằng chứng thực hiện** chứng minh một bước đã được chạy:

- psql command output.
- Deployment log.
- Migration tool log.
- Operator action record.

**Bằng chứng kết quả** chứng minh trạng thái sau thao tác đạt yêu cầu:

- Catalog xác nhận column/index/role tồn tại.
- Backup restore test thành công.
- Replication state đã ổn định.
- Query plan/latency đạt tiêu chí.
- Application smoke test thành công.
- Disk/connection metrics nằm trong ngưỡng.

Lệnh trả về “ALTER TABLE” chỉ chứng minh server chấp nhận DDL. Nó không chứng minh ứng dụng tương thích, query không bị chậm hoặc replication đã bắt kịp.

## 15. Decision gates và stop conditions

Runbook phải xác định các điều kiện khiến operator tiếp tục, dừng hoặc escalation.

Ví dụ:

| Điều kiện | Quyết định |
| --- | --- |
| Backup chưa hoàn tất | Dừng trước thao tác phá hủy dữ liệu |
| Không xác định đúng primary | Dừng, xác minh topology |
| Disk free dưới safety threshold | Dừng hoặc mở rộng storage theo plan |
| Replication lag vượt ngưỡng | Dừng migration/failover theo policy |
| Lock wait vượt thời gian tối đa | Dừng bước, xác định blocker |
| DDL output không như dự kiến | Không chạy bước tiếp theo |
| Post-check không đạt | Kích hoạt rollback/recovery decision |
| Application smoke test lỗi | Giữ change ở trạng thái chưa hoàn tất, escalation |

Ngưỡng phải do service owner định nghĩa dựa trên SLA/RPO/RTO và capacity. Không tự đặt một con số chung cho mọi cluster.

## 16. Rollback, recovery và forward-fix

Không phải mọi thay đổi đều có thể rollback bằng một câu SQL ngược.

### Rollback

Đưa hệ thống về trạng thái trước thay đổi, nếu hành động đảo ngược an toàn và dữ liệu chưa phát sinh phụ thuộc mới.

Ví dụ:

- Khôi phục giá trị cấu hình cũ.
- Revoke quyền vừa cấp.
- Drop index vừa tạo nếu không cần.
- Chuyển endpoint về node cũ sau khi xác minh node cũ an toàn.

### Recovery

Phục hồi từ backup, WAL archive hoặc bản sao phù hợp khi rollback thông thường không đủ.

Ví dụ:

- Restore database.
- PITR tới recovery target.
- Rebuild standby.
- Recreate object từ migration/backup.

### Forward-fix

Sửa trạng thái hiện tại bằng thay đổi tiếp theo, khi rollback có thể nguy hiểm hoặc không khả thi.

Ví dụ:

- Sửa migration đã chạy một phần.
- Thêm index/constraint tương thích để hoàn thiện schema.
- Cấp lại quyền đúng sau khi revoke nhầm.
- Chạy reconciliation cho dữ liệu đã chuyển đổi.

### Rollback plan cần có

1. Điều kiện kích hoạt.
2. Người có quyền quyết định.
3. Lệnh/thao tác cụ thể.
4. Tác động và downtime.
5. Data loss implications.
6. Backup/recovery point.
7. Verification sau rollback.
8. Điều kiện dừng rollback.
9. Escalation nếu rollback thất bại.

Không viết “nếu lỗi thì restore backup” mà không biết backup nào, ở đâu, thời gian restore bao lâu và data loss chấp nhận được là gì.

## 17. Vì sao rollback DDL cần thận trọng?

Một số DDL có thể đảo ngược về mặt cú pháp nhưng không khôi phục dữ liệu đã mất.

Ví dụ:

- DROP COLUMN rồi ADD COLUMN cùng tên không phục hồi giá trị cũ.
- DROP TABLE rồi CREATE TABLE mới không phục hồi rows, indexes, grants, triggers.
- ALTER TYPE có thể làm mất precision hoặc thông tin khi cast.
- DELETE/TRUNCATE không tự hoàn nguyên sau commit.
- Migration chạy một phần có thể để lại trạng thái trung gian.

Trước migration, phải xác định transactionality của từng DDL, lock impact, data transformation và phương án phục hồi dữ liệu.

## 18. Post-check: xác minh sau thao tác

Post-check nên có nhiều lớp.

### Lớp 1: Object state

- Object tồn tại.
- Schema/name/type đúng.
- Owner/grants đúng.
- Index valid/ready.
- Constraints đúng trạng thái.
- Configuration effective value đúng.

### Lớp 2: Data state

- Row counts hoặc aggregates phù hợp.
- Key uniqueness và referential integrity.
- Nullability/range checks.
- Data transformation sample.
- Reconciliation giữa source và target nếu migration/restore.

### Lớp 3: Database health

- PostgreSQL process và SQL health.
- Connection count.
- Long transactions và lock waits.
- Replication lag.
- WAL/archive health.
- Disk free space.
- Error logs.
- Checkpoint/vacuum activity.

### Lớp 4: Application health

- Kết nối thành công.
- Read path hoạt động.
- Write path hoạt động nếu có.
- Smoke test nghiệp vụ.
- Error rate và latency.
- Background jobs/queues.
- External integrations.

### Lớp 5: Operational readiness

- Monitoring và alert được bật.
- Backup schedule tiếp tục hoạt động.
- HA topology ổn định.
- Runbook/evidence được cập nhật.
- On-call team biết thay đổi đã diễn ra.

## 19. Evidence sau thay đổi cấu hình

Ví dụ thay đổi một tham số:

~~~sql
ALTER SYSTEM SET work_mem = '32MB';
SELECT pg_reload_conf();
~~~

Kiểm tra giá trị hiệu lực:

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    context,
    pending_restart
FROM pg_settings
WHERE name = 'work_mem';
~~~

Evidence nên gồm:

- Giá trị trước thay đổi.
- Giá trị được yêu cầu.
- File/config source liên quan.
- Kết quả reload.
- Giá trị effective sau reload.
- pending_restart.
- Workload metrics trước/sau.
- Error logs.
- Người thực hiện và change ID.

Không giả định pg_reload_conf() trả true đồng nghĩa mọi cấu hình đều đã được áp dụng. Một số tham số cần restart hoặc bị override bởi session/role/database settings.

## 20. Evidence sau thay đổi role và quyền

Ví dụ tạo role ứng dụng:

~~~sql
CREATE ROLE orders_reader
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE;
~~~

Cấp quyền đọc schema:

~~~sql
GRANT CONNECT ON DATABASE sales TO orders_reader;
GRANT USAGE ON SCHEMA reporting TO orders_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO orders_reader;
~~~

Xác minh role:

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper,
    rolcreatedb,
    rolcreaterole
FROM pg_roles
WHERE rolname = 'orders_reader';
~~~

Xác minh quyền trên relation:

~~~sql
SELECT
    has_database_privilege('orders_reader', 'sales', 'CONNECT') AS can_connect,
    has_schema_privilege('orders_reader', 'reporting', 'USAGE') AS can_use_schema,
    has_table_privilege('orders_reader', 'reporting.daily_orders', 'SELECT') AS can_select;
~~~

Evidence cần có:

- Role attributes.
- Database/schema/table privileges.
- Default privileges nếu role cần đọc object tạo trong tương lai.
- Test kết nối bằng role mới.
- Test SELECT được phép.
- Test DML bị từ chối nếu role chỉ đọc.
- Kiểm tra membership và inherited privileges.

Không lưu password trong evidence. Nếu dùng credential test, dùng secret manager và xóa/rotate theo policy sau khi kiểm tra.

## 21. Evidence sau migration schema

Ví dụ migration thêm column:

~~~sql
ALTER TABLE public.orders
ADD COLUMN source_channel text;
~~~

Xác minh catalog:

~~~sql
SELECT
    table_schema,
    table_name,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'orders'
  AND column_name = 'source_channel';
~~~

Nếu migration tạo index:

~~~sql
CREATE INDEX CONCURRENTLY orders_created_at_idx
ON public.orders (created_at);
~~~

Xác minh:

~~~sql
SELECT
    indexrelid::regclass AS index_name,
    indisvalid,
    indisready,
    indisunique
FROM pg_index
WHERE indexrelid = 'public.orders_created_at_idx'::regclass;
~~~

Evidence bổ sung:

- Migration tool version và migration ID.
- Start/end timestamp.
- SQL output và logs.
- Catalog state.
- Lock waits và replication lag trong lúc chạy.
- Query plan trên query đại diện.
- Application smoke test.
- Rollback/forward-fix result nếu cần.

Với CREATE INDEX CONCURRENTLY, index có thể tồn tại nhưng invalid nếu thao tác thất bại. Không chỉ kiểm tra tên index; cần kiểm tra indisvalid và xử lý index invalid theo runbook.

## 22. Evidence sau backup

Một lệnh backup kết thúc exit code 0 chưa đủ để chứng minh có thể phục hồi.

Evidence nên gồm:

- Backup ID.
- Backup tool/version.
- Cluster/database identity.
- Backup start/end time.
- Backup type và mode.
- Backup size.
- WAL range/required WAL metadata.
- Exit status.
- Backup manifest.
- Checksum/validation result nếu công cụ hỗ trợ.
- Storage location và retention.
- Encryption status.
- Restore test result.

Với pg_basebackup, kiểm tra output/manifest và kết quả validate theo version. Với backup tool chuyên dụng, lưu metadata do chính công cụ tạo.

### Backup consistency

Physical backup cần WAL đủ để đưa cluster về trạng thái nhất quán. Nếu dùng continuous archiving, kiểm tra archive success và WAL continuity.

Không đánh đồng backup file tồn tại với backup có thể restore. Restore test là bằng chứng mạnh hơn về khả năng phục hồi.

## 23. Evidence sau restore và PITR

Restore là thao tác rủi ro cao vì có thể thay thế dữ liệu hiện tại.

Trước restore:

- Xác định source backup và checksum/manifest.
- Xác định target cluster/database.
- Xác nhận target không phải production đang nhận writes nếu chưa có phê duyệt.
- Xác định recovery target và timezone.
- Xác định expected data loss window.
- Ghi lại trạng thái target trước thao tác.
- Có approval và rollback path.

Sau restore:

- PostgreSQL khởi động và recovery hoàn tất.
- Database/object inventory phù hợp.
- Data counts/aggregates phù hợp.
- Extensions và roles cần thiết có mặt.
- Application smoke tests đạt.
- WAL archiving/backup schedule được thiết lập.
- Access controls được xác minh.
- Recovery timeline/target được ghi lại.

Evidence gồm backup ID, restore logs, recovery target, timeline, server logs, SQL verification và application tests.

## 24. Evidence sau VACUUM và maintenance

Ví dụ theo dõi vacuum:

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count
FROM pg_stat_progress_vacuum;
~~~

Sau thao tác, xem table statistics:

~~~sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC;
~~~

Post-check có thể gồm:

- Vacuum command/log completion.
- Table và index sizes trước/sau.
- Dead tuple estimates.
- Long transaction horizon.
- Query latency.
- Disk I/O.
- Replication lag.
- Lock impact.

Không dùng n_dead_tup như số chính xác tuyệt đối; đây là thống kê ước lượng. VACUUM thường không trả dung lượng file về OS ngay; VACUUM FULL có behavior khác và cần lock/access planning riêng.

## 25. Evidence sau failover hoặc switchover

Sau chuyển primary, cần chứng minh cả role lẫn topology.

Kiểm tra node mới:

~~~sql
SELECT
    pg_is_in_recovery() AS in_recovery,
    pg_current_wal_lsn() AS current_lsn;
~~~

Primary mới phải có in_recovery = false.

Kiểm tra standby:

~~~sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

Evidence cần gồm:

- Incident/change ID.
- Lý do failover/switchover.
- Node primary cũ/mới.
- Timeline và promotion time.
- LSN candidate được chọn.
- Fencing confirmation.
- pg_is_in_recovery() trên primary mới.
- Replication state của standby còn lại.
- Endpoint/routing change.
- Application reconnect/smoke tests.
- WAL archiving và backup state.
- Kế hoạch rejoin node cũ.

Một node mới writable không chứng minh toàn bộ HA đã phục hồi. Cần xác minh standby follow primary mới và backup/monitoring tiếp tục hoạt động.

## 26. Evidence sau thay đổi network và authentication

Khi thay pg_hba.conf, TLS hoặc connection settings:

- Ghi config version trước/sau.
- Ghi vị trí file và change ID.
- Xác minh syntax/reload result.
- Kiểm tra pg_hba_file_rules.
- Test kết nối được phép.
- Test kết nối bị từ chối.
- Xem authentication logs.
- Kiểm tra certificate expiry và TLS parameters.
- Kiểm tra application reconnect.

Ví dụ:

~~~sql
SELECT
    line_number,
    type,
    database,
    user_name,
    address,
    auth_method,
    error
FROM pg_hba_file_rules
ORDER BY line_number;
~~~

Không lưu private key hoặc password trong evidence. Connection test nên ghi user/database/client context và kết quả, không ghi credential.

## 27. Kiểm tra sau restart

Sau restart PostgreSQL:

- Xác nhận service active.
- Kiểm tra server version và role.
- Kiểm tra logs từ lần startup mới.
- Xác minh recovery/primary state.
- Kiểm tra listeners và connection.
- Kiểm tra extension preload nếu có.
- Kiểm tra effective configuration.
- Kiểm tra replication.
- Kiểm tra backup/WAL archiving.
- Chạy application smoke tests.

Ví dụ kiểm tra startup time và role:

~~~sql
SELECT
    pg_postmaster_start_time() AS postmaster_started_at,
    pg_is_in_recovery() AS in_recovery,
    current_database() AS database_name,
    current_user AS database_user;
~~~

Một service manager báo process active chỉ xác nhận process đang chạy. PostgreSQL có thể chưa sẵn sàng nhận traffic, đang recovery hoặc application chưa thể truy cập.

## 28. Bằng chứng từ logs

Logs là bằng chứng lịch sử cho các sự kiện đã xảy ra.

Các nguồn:

- PostgreSQL server logs.
- OS/service manager logs.
- HA manager logs.
- Backup tool logs.
- Migration tool logs.
- Application logs.
- Proxy/load balancer logs.
- Cloud storage/control plane logs.

Khi lưu log excerpt:

- Giữ timestamp và timezone.
- Giữ PID/session/application context.
- Giữ SQLSTATE và severity.
- Giữ đủ dòng trước/sau để hiểu ngữ cảnh.
- Redact secret/PII.
- Ghi query/filter đã dùng.
- Không chỉ lưu ảnh chụp một dòng ERROR tách khỏi context.

Không thay thế raw evidence bằng một câu tóm tắt do người thực hiện tự viết.

## 29. Bằng chứng từ metrics

Metrics giúp chứng minh hệ thống ổn định theo thời gian, không chỉ ở một thời điểm.

Ví dụ:

- Connection count.
- Query latency p50/p95/p99.
- TPS/transaction rate.
- Error rate.
- CPU/memory.
- Disk IOPS/throughput/latency.
- WAL generation.
- Checkpoint duration.
- Replication lag.
- Deadlocks/lock waits.
- Temporary files.
- Autovacuum progress.

Với thay đổi rủi ro cao, lưu snapshot trước, trong và sau thao tác. Xác định observation window và ngưỡng chấp nhận trước khi thực hiện.

Ví dụ, nếu policy yêu cầu query p95 không tăng quá 10% so với baseline trong 15 phút, runbook phải nói rõ dashboard/query nào cung cấp số liệu và cách tính baseline.

## 30. Kiểm tra dữ liệu sau migration

Đếm rows là bước đầu nhưng không đủ nếu dữ liệu được transform.

Có thể so sánh:

~~~sql
SELECT
    count(*) AS row_count,
    min(created_at) AS min_created_at,
    max(created_at) AS max_created_at,
    sum(total_amount) AS total_amount
FROM public.orders;
~~~

Có thể kiểm tra duplicate keys:

~~~sql
SELECT
    order_id,
    count(*) AS duplicate_count
FROM public.orders
GROUP BY order_id
HAVING count(*) > 1;
~~~

Kiểm tra NULL/range:

~~~sql
SELECT
    count(*) FILTER (WHERE order_id IS NULL) AS null_order_ids,
    count(*) FILTER (WHERE total_amount < 0) AS negative_amounts
FROM public.orders;
~~~

Khi đối chiếu hai hệ thống, cần bảo đảm cùng snapshot hoặc một watermark nhất quán. Nếu dữ liệu vẫn đang thay đổi trong lúc lấy counts, chênh lệch có thể chỉ phản ánh thời điểm khác nhau.

Với dataset lớn, checksum toàn bảng có thể tốn tài nguyên. Chọn key range/partition/sample hoặc công cụ reconciliation phù hợp, đồng thời ghi rõ mức độ kiểm chứng.

## 31. Evidence và audit trail

Audit trail ghi lại ai đã làm gì, lúc nào, trên đối tượng nào và theo quyền/phê duyệt nào.

Một audit record nên có:

- Change/incident ID.
- Operator identity.
- Approver identity.
- Timestamp bắt đầu/kết thúc.
- Host/cluster/database.
- Command/action.
- Result/exit code.
- Evidence reference.
- Exception/deviation.
- Rollback/recovery action.
- Reviewer sign-off.

PostgreSQL logs không thay thế hoàn toàn audit trail của tổ chức. Database log có thể không ghi mọi thao tác ngoài database, ví dụ thay DNS, thay firewall, update secret manager hoặc đổi cloud volume.

Kết hợp database logs với infrastructure audit logs và change management records.

## 32. Quản lý secrets và dữ liệu nhạy cảm trong evidence

Không đưa vào runbook/evidence:

- Password.
- API token.
- Private key.
- Full connection string chứa password.
- Customer PII không cần thiết.
- Query parameters nhạy cảm.
- Backup encryption keys.

Dùng placeholder như:

~~~text
host=<db-endpoint> dbname=<database> user=<service-role>
~~~

Credential thực tế lấy từ secret manager hoặc cơ chế xác thực được phê duyệt. Khi evidence cần chứng minh authentication thành công, lưu kết quả, role, database, timestamp và auth method phù hợp, không lưu secret.

Redaction cần bảo toàn thông tin đủ để điều tra. Không xóa timestamp, SQLSTATE hoặc object name nếu các trường đó không nhạy cảm và cần thiết.

## 33. Versioning và ownership của runbook

Mỗi runbook cần:

- ID ổn định.
- Version.
- Owner/team.
- Created/reviewed date.
- Last tested date.
- Supported PostgreSQL versions.
- Change history.
- Link tới dashboard/tooling.
- Reviewer/approver.

Khi thay đổi PostgreSQL major version, backup tool, HA manager, storage platform hoặc authentication method, review runbook liên quan.

### Runbook drift

Runbook drift xảy ra khi tài liệu không còn khớp hệ thống thực tế:

- Hostname/endpoint thay đổi.
- Setting đổi nhưng tài liệu cũ.
- Script bị xóa hoặc đổi tham số.
- Tool version khác.
- Role/permission thay đổi.
- Dashboard bị chuyển.
- Recovery procedure không còn hoạt động.

Định kỳ chạy tabletop exercise hoặc diễn tập trên staging để phát hiện drift.

## 34. Kiểm thử runbook

Không đợi incident thật mới kiểm tra runbook.

Các cách kiểm thử:

**Tabletop exercise:** Đội vận hành đi qua từng bước trên giấy, mô phỏng quyết định và escalation.

**Staging rehearsal:** Thực hiện quy trình trên môi trường staging với data size/workload tương tự trong giới hạn an toàn.

**Restore drill:** Phục hồi backup và đo RTO/RPO thực tế.

**Failover drill:** Thử chuyển primary, kiểm tra fencing, routing và rejoin.

**Permission test:** Dùng role thực tế để xác nhận runbook có đủ quyền nhưng không quá quyền.

**Evidence review:** Người khác kiểm tra evidence package mà không tham gia thao tác, xem có thể kết luận kết quả hay không.

Mỗi lần kiểm thử cần ghi kết quả, thời gian, lỗi, bước chưa rõ và thay đổi tài liệu.

## 35. Mẫu runbook hoàn chỉnh: tạo index concurrently

### Mục tiêu

Tạo index trên bảng lớn mà giảm thời gian giữ lock ghi so với cách tạo index thông thường.

### Phạm vi

- Database: sales.
- Table: public.orders.
- Index: orders_created_at_idx.
- Column: created_at.
- Môi trường: staging hoặc production theo change approval.

### Preconditions

- Đã xác định query cần index.
- Kiểm tra index tương tự đã tồn tại hay chưa.
- Có đủ disk cho index build.
- Replication lag và disk pressure trong ngưỡng.
- Không có migration khác chạy đồng thời trên cùng table.
- Có query plan baseline.
- Có rollback plan.

Kiểm tra index hiện có:

~~~sql
SELECT
    indexrelid::regclass AS index_name,
    indisvalid,
    indisready
FROM pg_index
WHERE indrelid = 'public.orders'::regclass;
~~~

### Execution

~~~sql
CREATE INDEX CONCURRENTLY orders_created_at_idx
ON public.orders (created_at);
~~~

CREATE INDEX CONCURRENTLY không chạy bên trong transaction block thông thường. Công cụ migration phải hỗ trợ non-transactional migration.

### Post-check

~~~sql
SELECT
    indexrelid::regclass AS index_name,
    indisvalid,
    indisready
FROM pg_index
WHERE indexrelid = 'public.orders_created_at_idx'::regclass;
~~~

Expected: một dòng, index valid và ready.

Kiểm tra query plan:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM public.orders
WHERE created_at >= now() - interval '7 days';
~~~

Query plan không bắt buộc phải dùng index trong mọi tình huống; planner chọn plan theo selectivity và cost. Kiểm tra query workload đại diện và latency.

### Rollback

Nếu index không cần hoặc gây write overhead:

~~~sql
DROP INDEX CONCURRENTLY IF EXISTS public.orders_created_at_idx;
~~~

Lệnh DROP INDEX CONCURRENTLY cũng không chạy trong transaction block thông thường. Xác minh index đã biến mất và query/application vẫn hoạt động.

### Evidence

- Index inventory trước/sau.
- Command output.
- indisvalid/indisready.
- Build duration và logs.
- Disk usage.
- Replication lag.
- Query plan/latency.
- Application error rate.

## 36. Mẫu runbook: thay đổi PostgreSQL configuration

### Preconditions

- Xác định parameter và context.
- Lưu giá trị hiện tại.
- Xác định config source và override.
- Đánh giá memory/disk/durability impact.
- Xác định reload hay restart.
- Xác định rollback value.
- Có maintenance window nếu restart.

### Baseline

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    context,
    pending_restart
FROM pg_settings
WHERE name = 'max_connections';
~~~

### Execution

Ví dụ thay đổi persistent:

~~~sql
ALTER SYSTEM SET max_connections = '300';
~~~

Tham số này cần restart vì context là postmaster. Không dùng pg_reload_conf() rồi kết luận đã có hiệu lực.

### Restart và verify

Sau khi restart theo service manager/runbook:

~~~sql
SHOW max_connections;

SELECT
    pg_postmaster_start_time(),
    pg_is_in_recovery();
~~~

Xác minh:

- PostgreSQL active.
- Parameter effective value đúng.
- pending_restart không còn cho parameter đó.
- Connection capacity đủ.
- Application health đạt.
- Logs không có startup/config errors.

### Rollback

Khôi phục giá trị cũ bằng ALTER SYSTEM hoặc config management tương ứng, sau đó restart nếu cần. Ghi rõ giá trị cũ lấy từ đâu và ai phê duyệt.

## 37. Mẫu runbook: tạo role và cấp quyền

### Preconditions

- Có yêu cầu quyền được phê duyệt.
- Xác định database/schema/table cụ thể.
- Xác định login/no-login.
- Xác định role membership.
- Xác định default privileges cho object tương lai.
- Dùng least privilege.

### Execution

~~~sql
CREATE ROLE reporting_reader
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE;

GRANT CONNECT ON DATABASE sales TO reporting_reader;
GRANT USAGE ON SCHEMA reporting TO reporting_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO reporting_reader;
~~~

### Post-check

- Role attributes đúng.
- Membership đúng.
- Database/schema/table grants đúng.
- Test login.
- SELECT thành công.
- INSERT/UPDATE/DELETE bị từ chối nếu role read-only.
- Default privileges đúng nếu cần.

### Rollback

Revoke grants đã cấp. Drop role chỉ sau khi xác minh không còn object ownership, membership hoặc dependency. Nếu role đã tạo object, cần chuyển ownership hoặc xử lý object trước.

## 38. Mẫu runbook: backup và restore test

### Backup

1. Xác định cluster/database và backup type.
2. Kiểm tra dung lượng destination.
3. Kiểm tra WAL archive health.
4. Chạy backup bằng công cụ được phê duyệt.
5. Lưu backup ID, start/end time, size và tool exit status.
6. Validate manifest/checksum.
7. Xác minh retention và encryption.
8. Đăng ký backup trong inventory.

### Restore test

1. Chọn backup ID cụ thể.
2. Chọn target cô lập.
3. Xác định recovery target.
4. Restore theo công cụ.
5. Chờ PostgreSQL recovery hoàn tất.
6. Xác minh database/object inventory.
7. Chạy data checks và application smoke tests.
8. Đo restore duration và recovery point.
9. Xóa môi trường test theo policy sau khi evidence được lưu.

### Evidence

- Backup metadata.
- WAL coverage.
- Restore logs.
- Recovery target/timeline.
- SQL checks.
- Application test results.
- Actual RTO/RPO.
- Reviewer sign-off.

## 39. Mẫu runbook: migration dữ liệu

### Preconditions

- Source và target đã xác định.
- Mapping/schema được review.
- Data volume và duration ước lượng.
- Cutover/watermark strategy rõ.
- Backup/rollback path đã kiểm tra.
- Dual-write hoặc write freeze policy đã xác định.
- Reconciliation query được chuẩn bị.

### Execution

- Capture source baseline.
- Chạy initial copy.
- Đồng bộ incremental changes.
- Dừng/drain writes nếu cần.
- Ghi final watermark/LSN.
- Apply phần dữ liệu cuối.
- Chuyển ứng dụng.
- Mở writes ở target.
- Giữ source theo retention/rollback window.

### Post-check

- Row counts theo partition/key range.
- Aggregate totals.
- Missing/duplicate keys.
- Null/range constraints.
- Referential integrity.
- Query/application smoke tests.
- Error rate và latency.
- Replication/CDC lag nếu có.

### Rollback

Quyết định rollback phụ thuộc target đã nhận writes hay chưa. Nếu target đã nhận writes mới, quay về source có thể làm mất dữ liệu; cần reverse sync hoặc reconciliation. Runbook phải mô tả điều kiện này trước cutover.

## 40. Mẫu runbook: failover và switchover

### Preconditions

- HA manager health/quorum.
- Candidate standby state.
- Replication LSN/lag.
- RPO policy.
- Fencing mechanism.
- Endpoint/routing path.
- Backup/WAL archive state.
- Operator/incident commander.

### Execution

1. Detect và confirm primary failure hoặc maintenance event.
2. Xác nhận quorum và quyền quyết định.
3. Fence primary cũ.
4. Chọn candidate theo WAL/LSN và health.
5. Promote đúng một standby.
6. Kiểm tra pg_is_in_recovery() = false.
7. Chuyển endpoint.
8. Xác nhận application reconnect/write.
9. Kiểm tra replication slots, WAL archive và backup.
10. Rejoin node cũ bằng rewind/rebuild theo điều kiện.

### Post-check evidence

- Failure timeline.
- Fence confirmation.
- Candidate LSN.
- Promotion logs.
- Primary role query.
- Endpoint update.
- Application smoke tests.
- Replication state.
- Timeline/backup status.
- Actual RTO và estimated/actual data loss.

Không coi failover hoàn tất chỉ vì node mới writable. Topology, application và backup cần được xác minh.

## 41. Runbook cho thao tác có thể chạy lại

Một số lệnh có thể chạy lại an toàn; một số không.

| Loại thao tác | Tính chạy lại | Cách kiểm soát |
| --- | --- | --- |
| SELECT verification | Thường an toàn | Chạy lại khi cần |
| CREATE TABLE IF NOT EXISTS | Có điều kiện | Vẫn phải kiểm tra schema tương thích |
| CREATE INDEX | Không luôn an toàn | Kiểm tra index state trước khi retry |
| CREATE INDEX CONCURRENTLY | Có thể để invalid index khi fail | Kiểm tra catalog và dọn index invalid |
| ALTER SYSTEM SET | Có thể ghi lại giá trị | Xác minh source/effective value |
| INSERT migration data | Có thể duplicate | Dùng idempotency key/upsert hoặc checkpoint |
| DROP TABLE | Phá hủy dữ liệu | Cần explicit approval và recovery path |
| RESTORE | Có thể ghi đè target | Xác định target và backup ID rõ ràng |
| PROMOTE standby | Chuyển timeline/role | Không chạy lặp trên nhiều candidate |

Mỗi runbook phải phân loại command là idempotent, conditionally idempotent hay destructive. Khi command timeout, không tự chạy lại trước khi xác định server đã thực hiện tới đâu.

## 42. Kiểm soát thao tác thủ công

Trong production, command nên được lưu cùng change record. Có thể dùng psql với ON_ERROR_STOP cho script:

~~~bash
psql -X -v ON_ERROR_STOP=1 -d sales -f migration.sql
~~~

Điều này khiến psql dừng khi gặp SQL error trong script. Tuy nhiên, nó không tự rollback các lệnh đã commit trước đó, đặc biệt khi script chứa các lệnh ngoài transaction block.

Nên:

- Review script trước.
- Chạy trên staging.
- Xác nhận database/host.
- Sử dụng role least privilege.
- Ghi command output.
- Không paste secret vào shell history.
- Không dùng shell script che giấu target hoặc bỏ qua lỗi.
- Kiểm tra trạng thái sau timeout/disconnect.

## 43. Quản lý evidence package

Một cấu trúc thư mục ví dụ:

~~~text
CHG-2026-1042/
  00-change-record.md
  01-prechecks/
    database-identity.txt
    replication-state.txt
    disk-capacity.txt
    baseline-metrics.json
  02-execution/
    command-output.txt
    migration-tool.log
    operator-actions.csv
  03-postchecks/
    catalog-verification.txt
    data-reconciliation.txt
    application-smoke-test.txt
    monitoring-snapshot.json
  04-recovery/
    rollback-decision.md
    rollback-output.txt
  05-closure/
    reviewer-signoff.md
    checksums.txt
~~~

Cấu trúc chỉ là ví dụ. Dùng storage/records repository được tổ chức phê duyệt, có access control và retention. Không lưu evidence vào thư mục tạm trên database host rồi quên chuyển tới kho lưu trữ.

## 44. Evidence matrix

Một evidence matrix giúp reviewer biết mỗi mục tiêu được chứng minh bằng gì.

| Mục tiêu | Evidence trước | Evidence thực hiện | Evidence sau |
| --- | --- | --- | --- |
| Thêm column | Schema snapshot | DDL output | information_schema.columns |
| Tạo index | Index inventory/query plan | CREATE INDEX output | pg_index validity + plan |
| Cấp role | Role/grant snapshot | GRANT output | privilege checks + login test |
| Restore | Backup ID/manifest | Restore logs | SQL/data/application checks |
| Failover | Topology/LSN/health | Fence/promote logs | role/routing/replication checks |
| Config change | pg_settings/config source | ALTER SYSTEM/reload/restart logs | effective setting + health metrics |
| Vacuum | Table stats/size | VACUUM logs/progress | dead tuple estimates, latency, I/O |

Nếu một mục tiêu không có evidence sau, runbook chưa có cách chứng minh thành công.

## 45. Closure criteria

Không đóng change chỉ vì tất cả command đã chạy.

Điều kiện đóng có thể gồm:

- Tất cả required steps đã hoàn thành.
- Không còn step ở trạng thái unknown.
- Post-checks đạt.
- Application owner xác nhận.
- Monitoring không có regression vượt ngưỡng.
- Replication/backup/HA ở trạng thái mong muốn.
- Không có rollback đang chờ.
- Deviations được ghi nhận và chấp thuận.
- Evidence package được lưu.
- Reviewer sign-off hoàn tất.
- Runbook/documentation được cập nhật nếu có thay đổi quy trình.

Nếu chỉ một số mục tiêu đạt, ghi trạng thái partial/accepted risk theo policy; không đánh dấu complete mà bỏ qua ngoại lệ.

## 46. Incident handoff và escalation

Khi runbook dừng do lỗi:

1. Ghi chính xác bước đã hoàn tất.
2. Ghi bước đang lỗi và command/output.
3. Ghi thời điểm, timezone, environment và target.
4. Ghi trạng thái hiện tại của database.
5. Ghi tác động ứng dụng.
6. Ghi các quyết định đã thực hiện.
7. Nêu thao tác nào chưa được chạy.
8. Đính kèm evidence và logs đã redact.
9. Xác định người/nhóm nhận handoff.
10. Giữ hệ thống ở trạng thái an toàn đã định nghĩa.

Không chỉ gửi thông báo “migration failed”. Người tiếp nhận cần biết có thể retry không, DDL đã commit chưa, có object dở dang không và dữ liệu đã bị thay đổi tới đâu.

## 47. Những sai lầm thường gặp

1. **Runbook chỉ liệt kê command**, không có precondition, expected result hoặc verification.
2. **Không ghi rõ database/host/role**, dễ chạy nhầm môi trường.
3. **Dùng một runbook chung cho mọi PostgreSQL major version**, bỏ qua thay đổi syntax/catalog.
4. **Không ghi baseline**, khiến không thể so sánh trước/sau.
5. **Coi exit code 0 là bằng chứng duy nhất**, bỏ qua trạng thái thực tế.
6. **Không phân biệt execution evidence với outcome evidence**, dẫn tới đóng change quá sớm.
7. **Không có stop conditions**, operator tiếp tục dù điều kiện an toàn đã mất.
8. **Viết rollback chung chung**, không xác định data loss, target và thời gian phục hồi.
9. **Cho rằng mọi DDL đều rollback được**, bỏ qua DDL đã commit hoặc dữ liệu đã mất.
10. **Chạy lại command sau timeout mà không kiểm tra trạng thái**, tạo object/data trùng.
11. **Không xác minh CREATE INDEX CONCURRENTLY**, để index invalid tồn tại.
12. **Dùng row count đơn lẻ để chứng minh migration đúng**, bỏ qua missing/duplicate/aggregate mismatch.
13. **Không test application**, chỉ kiểm tra database object.
14. **Không kiểm tra replication sau DDL/restore/failover**, để standby lag hoặc lỗi.
15. **Lưu password/connection URI trong evidence**, làm lộ credential.
16. **Lưu ảnh chụp màn hình không có timestamp/context**, không truy xuất được nguồn.
17. **Không lưu raw output/log**, chỉ giữ kết luận do operator tự viết.
18. **Không có retention/access policy**, evidence bị mất hoặc người không có quyền đọc được.
19. **Không version hóa runbook**, tài liệu drift khỏi hệ thống thực tế.
20. **Không diễn tập restore/failover**, RTO và các bước phục hồi chỉ tồn tại trên giấy.
21. **Không tách operator và verifier cho thao tác rủi ro cao**, thiếu kiểm tra độc lập.
22. **Không ghi deviation/exception**, reviewer không biết quy trình đã bị thay đổi.
23. **Đóng change khi monitoring window chưa đủ**, bỏ sót regression xuất hiện muộn.
24. **Không bàn giao trạng thái khi runbook dừng**, người tiếp nhận có thể chạy sai bước tiếp theo.

## 48. Bài tập thực hành có đáp án

### Bài 1. Runbook là gì?

**Đáp án:** Tài liệu hướng dẫn một quy trình vận hành từ điều kiện bắt đầu tới xác minh và đóng công việc.

### Bài 2. Runbook khác checklist thế nào?

**Đáp án:** Runbook giải thích cách thực hiện và xử lý nhánh; checklist xác nhận các mục đã hoàn thành.

### Bài 3. Evidence sau thao tác dùng để làm gì?

**Đáp án:** Chứng minh trạng thái/kết quả có thể kiểm tra lại, gắn với đúng môi trường và lần thực hiện.

### Bài 4. Vì sao cần pre-check?

**Đáp án:** Xác nhận target, health, quyền, backup, capacity và các điều kiện an toàn trước khi thay đổi.

### Bài 5. Baseline là gì?

**Đáp án:** Snapshot trạng thái trước thao tác để so sánh với kết quả sau thao tác.

### Bài 6. Exit code 0 có đủ chứng minh thành công không?

**Đáp án:** Không. Cần kiểm tra catalog, data, database health và application behavior.

### Bài 7. Execution evidence và outcome evidence khác gì?

**Đáp án:** Execution evidence chứng minh lệnh đã chạy; outcome evidence chứng minh trạng thái mong muốn đã đạt.

### Bài 8. Một runbook cần stop condition không?

**Đáp án:** Có. Phải biết khi nào dừng/escalate nếu precondition hoặc expected result không đạt.

### Bài 9. Vì sao không thể rollback mọi DDL?

**Đáp án:** Một số DDL commit riêng, thao tác phá hủy dữ liệu hoặc không thể khôi phục giá trị cũ chỉ bằng lệnh ngược.

### Bài 10. Bằng chứng kiểm tra column mới?

~~~sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'orders';
~~~

**Đáp án:** Catalog xác nhận tên, kiểu và nullability của column.

### Bài 11. Kiểm tra index valid bằng gì?

**Đáp án:** pg_index, đặc biệt indisvalid và indisready.

### Bài 12. Vì sao CREATE INDEX CONCURRENTLY cần post-check riêng?

**Đáp án:** Index có thể còn tồn tại nhưng invalid nếu build thất bại.

### Bài 13. Bằng chứng role read-only cần gì?

**Đáp án:** Role attributes, grants và test SELECT thành công/DML bị từ chối.

### Bài 14. Backup hoàn tất có đồng nghĩa restore được không?

**Đáp án:** Không. Cần validate backup metadata và restore test.

### Bài 15. Evidence sau restore nên có gì?

**Đáp án:** Backup ID, restore logs, recovery target, catalog/data checks và application smoke tests.

### Bài 16. Vì sao cần ghi PostgreSQL version?

**Đáp án:** Syntax, catalog views, settings và behavior có thể khác giữa major versions.

### Bài 17. Một evidence record cần timestamp và timezone không?

**Đáp án:** Có, để liên kết với logs, metrics và các hệ thống khác.

### Bài 18. Checksum có chứng minh nội dung đúng không?

**Đáp án:** Không. Nó chỉ giúp phát hiện file thay đổi sau khi checksum được tạo.

### Bài 19. Khi nào cần tách operator và verifier?

**Đáp án:** Đặc biệt với thao tác rủi ro cao hoặc có tác động production, để có xác minh độc lập.

### Bài 20. Khi nào không nên retry command?

**Đáp án:** Khi chưa biết command trước đã thực hiện tới đâu hoặc thao tác không idempotent/destructive.

### Bài 21. Post-check cần kiểm tra những lớp nào?

**Đáp án:** Object, data, database health, application health và operational readiness.

### Bài 22. Vì sao application smoke test quan trọng?

**Đáp án:** Database object đúng không bảo đảm ứng dụng có thể kết nối và thực hiện nghiệp vụ.

### Bài 23. Vì sao phải ghi deviation?

**Đáp án:** Reviewer và người nhận handoff cần biết quy trình thực tế khác runbook ở đâu và vì sao.

### Bài 24. Khi migration có target writes mới, rollback về source có luôn an toàn không?

**Đáp án:** Không. Cần reverse sync/reconciliation hoặc chấp nhận rõ data loss.

### Bài 25. Evidence package cần retention/access control không?

**Đáp án:** Có, vì log/evidence có thể chứa thông tin vận hành và dữ liệu nhạy cảm.

### Bài 26. Runbook drift là gì?

**Đáp án:** Runbook không còn khớp hệ thống, tool, endpoint, permission hoặc cấu hình thực tế.

### Bài 27. Tabletop exercise dùng để làm gì?

**Đáp án:** Mô phỏng quy trình và quyết định mà không cần thực hiện thay đổi thật trên database.

### Bài 28. Vì sao không nên chỉ lưu screenshot?

**Đáp án:** Screenshot có thể thiếu nguồn, timestamp, raw output và khả năng truy vấn/đối chiếu.

### Bài 29. Closure criteria nên gồm gì?

**Đáp án:** Post-check đạt, application/monitoring ổn định, evidence lưu đủ, ngoại lệ được xử lý và reviewer sign-off.

### Bài 30. Handoff khi runbook thất bại cần ghi gì?

**Đáp án:** Bước đã chạy, command/output, trạng thái hiện tại, tác động, việc chưa làm, evidence và next owner.

## 49. Checklist xây dựng và thực hiện runbook

### Trước thao tác

- [ ] Runbook ID/version/owner rõ ràng.
- [ ] Change hoặc incident ID tồn tại.
- [ ] Mục tiêu và phạm vi cụ thể.
- [ ] Đúng environment/cluster/database/host.
- [ ] PostgreSQL major version đã xác định.
- [ ] Operator/approver/verifier được phân công.
- [ ] Preconditions và stop conditions rõ.
- [ ] Backup/recovery readiness được xác nhận.
- [ ] Baseline database/application/OS được lưu.
- [ ] Rủi ro, downtime và RPO/RTO được đánh giá.
- [ ] Lệnh và script đã review/test.
- [ ] Rollback/forward-fix plan có thể thực hiện.

### Trong thao tác

- [ ] Chạy đúng thứ tự.
- [ ] Ghi timestamp và operator cho từng bước quan trọng.
- [ ] Lưu command output và tool logs.
- [ ] Kiểm tra expected result trước bước tiếp theo.
- [ ] Theo dõi lock, connection, disk, WAL và replication.
- [ ] Dừng khi stop condition xảy ra.
- [ ] Ghi mọi deviation/exception.
- [ ] Không lưu secret trong evidence.
- [ ] Không retry command chưa xác định trạng thái.

### Sau thao tác

- [ ] Catalog/object state đúng.
- [ ] Data checks/reconciliation đạt.
- [ ] Database health đạt.
- [ ] Application smoke tests đạt.
- [ ] Replication/backup/monitoring tiếp tục hoạt động.
- [ ] Metrics nằm trong ngưỡng observation window.
- [ ] Rollback/recovery không còn pending.
- [ ] Evidence có timestamp, context và source.
- [ ] Evidence được lưu đúng nơi và có quyền phù hợp.
- [ ] Reviewer sign-off.
- [ ] Change/incident record được đóng đúng trạng thái.
- [ ] Runbook được cập nhật nếu phát hiện drift.

## 50. Tài liệu PostgreSQL chính thức

Đọc tài liệu theo major version đang triển khai:

- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — các system views dùng để xác minh session, database, I/O và replication.
- [System Catalogs](https://www.postgresql.org/docs/current/catalogs.html) — catalog metadata về database objects và trạng thái.
- [Information Schema](https://www.postgresql.org/docs/current/information-schema.html) — metadata SQL chuẩn cho tables, columns và privileges.
- [Database Roles](https://www.postgresql.org/docs/current/user-manag.html) — quản lý role và quyền.
- [Privileges](https://www.postgresql.org/docs/current/ddl-priv.html) — database/schema/table privileges.
- [ALTER SYSTEM](https://www.postgresql.org/docs/current/sql-altersystem.html) — thay đổi cấu hình persistent.
- [Configuration Settings](https://www.postgresql.org/docs/current/config-setting.html) — reload, restart và setting context.
- [Backup and Restore](https://www.postgresql.org/docs/current/backup.html) — các phương pháp backup và restore.
- [Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html) — WAL archive và point-in-time recovery.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html) — tạo physical base backup.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) — index creation và CONCURRENTLY.
- [VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html) — vacuum và các option.
- [pg_stat_progress](https://www.postgresql.org/docs/current/progress-reporting.html) — theo dõi tiến độ một số thao tác dài.
- [Logging Configuration](https://www.postgresql.org/docs/current/runtime-config-logging.html) — server logs và log context.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html) — kiểm tra query plan và execution behavior.

Các URL /current/ trỏ tới tài liệu PostgreSQL hiện hành. Catalog columns, statistics views, DDL behavior và backup tooling có thể khác theo major version; đối chiếu tài liệu đúng phiên bản và công cụ thực tế trước khi chạy runbook production.

## 51. Tổng kết

**Runbook mô tả cách thực hiện; evidence chứng minh trạng thái và kết quả; post-check xác nhận dịch vụ vẫn hoạt động sau thay đổi.** Ba thành phần này cần được thiết kế cùng nhau cho mọi thao tác quản trị quan trọng.

1. **Runbook phải có phạm vi, trigger, roles, preconditions, execution steps và stop conditions.**
2. **Baseline trước thao tác giúp xác định thay đổi đã tác động điều gì.**
3. **Mỗi bước quan trọng cần expected result và evidence source.**
4. **Exit code thành công chỉ chứng minh command trả về thành công.** Catalog, data và application checks mới xác nhận outcome.
5. **Rollback cần điều kiện, lệnh và recovery point cụ thể.** Không giả định mọi DDL hoặc data change đều đảo ngược được.
6. **Evidence phải có context:** change ID, environment, database, version, timestamp, operator và source.
7. **Bảo vệ secrets và PII trong log/evidence.** Dùng access control, redaction, retention và checksum khi phù hợp.
8. **Post-check cần bao gồm object, data, database, application và operational readiness.**
9. **Backup cần restore test.** File tồn tại không chứng minh khả năng phục hồi.
10. **Migration cần reconciliation và watermark nhất quán.** Row count đơn lẻ không đủ.
11. **Failover cần xác minh fencing, role, routing, replication và backup.**
12. **Runbook phải được version hóa và diễn tập.** Runbook chưa được thử trong môi trường phù hợp có thể không dùng được khi incident xảy ra.
13. **Change chỉ được đóng khi evidence đủ, ngoại lệ được ghi nhận và người có trách nhiệm xác nhận.**

Một quy trình quản trị PostgreSQL đáng tin cậy không dừng ở việc chạy xong lệnh. Nó để lại bằng chứng đủ rõ để người khác có thể xác minh điều gì đã xảy ra, hệ thống đang ở trạng thái nào và vì sao có thể tiếp tục vận hành.
