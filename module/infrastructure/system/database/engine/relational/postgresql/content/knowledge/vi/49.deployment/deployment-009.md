# Đưa migration, giám sát và kiểm tra sau triển khai vào quy trình PostgreSQL

Một bản phát hành ứng dụng có thể thành công ở tầng binary nhưng vẫn thất bại ở database: migration chưa chạy, schema chỉ thay đổi một phần, index chưa valid, backfill còn dang dở, quyền truy cập sai hoặc query mới làm tải hệ thống tăng mạnh. Ngược lại, migration có thể hoàn tất nhưng application, worker, scheduled job hay subscriber vẫn đang chạy phiên bản cũ và không tương thích với schema mới.

Vì vậy, migration cần được quản lý như một phần của release lifecycle. Pipeline phải biết migration nào sẽ chạy, trên cluster nào, từ schema version nào tới version nào, cần lock hay maintenance window gì, tiêu chí dừng là gì và sau khi deploy phải chứng minh điều gì. Monitoring cung cấp tín hiệu vận hành; post-deployment verification cung cấp bằng chứng rằng database và ứng dụng đã đạt trạng thái mong muốn.

Bài học này trình bày cách đưa migration, monitoring và post-deployment checks vào quy trình triển khai PostgreSQL, từ preflight tới release closure. Mục tiêu là có thể triển khai lặp lại, phát hiện lỗi sớm, hạn chế blast radius và phục hồi có kiểm soát.

~~~mermaid
flowchart TD
    A["Build release artifact"] --> B["Preflight: version, backup, capacity, locks"]
    B --> C{"Preflight passed?"}
    C -->|"No"| X["Stop release / resolve blocker"]
    C -->|"Yes"| D["Acquire migration lock"]
    D --> E["Run expand-compatible migrations"]
    E --> F{"Migration succeeded?"}
    F -->|"No"| R["Contain + recovery decision"]
    F -->|"Yes"| G["Deploy application / workers"]
    G --> H["Canary + monitor"]
    H --> I{"Health and data checks passed?"}
    I -->|"No"| R
    I -->|"Yes"| J["Backfill / validate / reconcile"]
    J --> K["Post-deploy acceptance checks"]
    K --> L{"All criteria passed?"}
    L -->|"No"| R
    L -->|"Yes"| M["Release sign-off and close"]
~~~

Bài học thuộc chương **Triển khai**, module **Database Engine Relational PostgreSQL**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao database migration phải nằm trong release lifecycle.
2. Thiết kế pipeline migration có preflight, lock, execution và verification gates.
3. Xác định schema baseline, target version và migration artifact.
4. Đánh giá backup, restore readiness, capacity và lock risk trước deploy.
5. Phân biệt transactional DDL với thao tác không chạy trong transaction block.
6. Tích hợp migration runner vào CI/CD mà không chạy song song ngoài ý muốn.
7. Triển khai expand-contract để hỗ trợ rolling deployment.
8. Quản lý backfill, validation và long-running operations.
9. Xây monitoring cho database, migration runner và application.
10. Định nghĩa SLI/SLO và release thresholds phù hợp.
11. Viết post-deployment checks cho schema, data, permissions, replication và application behavior.
12. Phân biệt rollback application, rollback schema và forward-fix.
13. Thu thập evidence và tạo audit trail cho change.
14. Thiết kế canary, staged rollout và stop conditions.
15. Tạo runbook cho migration failure, lag, query regression và data mismatch.
16. Tự động hóa các kiểm tra lặp lại nhưng giữ remediation trong change control.
17. Đóng release chỉ sau khi acceptance criteria được xác minh.

## 2. Vì sao migration phải thuộc release process?

Migration thay đổi contract mà application sử dụng. Những thay đổi này có thể ảnh hưởng:

- Cấu trúc bảng, cột, type và constraints.
- Indexes và query plans.
- Roles, ownership, grants và RLS policies.
- Triggers, functions, views và extensions.
- Data representation và backfill state.
- Replication, CDC và downstream consumers.
- Locking, WAL generation, disk usage và latency.

Nếu migration được chạy ngoài pipeline, release artifact và database state có thể mất liên kết. Một environment có thể chạy code mới với schema cũ; environment khác có schema mới nhưng code chưa deploy. Khi xảy ra sự cố, team khó biết lệnh nào đã chạy, ai chạy, artifact nào được dùng và trạng thái nào là chuẩn.

Release process cần một nguồn sự thật có version cho:

- Application artifact.
- Migration artifact/checksum.
- Source schema version.
- Target schema version.
- Deployment target.
- Migration execution result.
- Post-deployment verification result.

Không coi dòng log “migration command exited 0” là bằng chứng đầy đủ rằng release đã thành công.

## 3. Release lifecycle cho database changes

Một release có migration nên có các giai đoạn:

| Giai đoạn | Mục tiêu | Kết quả cần lưu |
| --- | --- | --- |
| Plan | Xác định scope và compatibility | Change plan, migration list |
| Build | Đóng gói code và migrations | Immutable artifact, checksum |
| Preflight | Xác nhận target/capacity/backup | Preflight report |
| Migrate | Chạy schema/data changes | Migration logs, ledger |
| Deploy | Đưa app/worker lên phiên bản mới | Deployment versions |
| Observe | Theo dõi behavior và load | Metrics, logs, traces |
| Verify | Kiểm tra schema/data/business | Post-deploy report |
| Close | Ghi nhận acceptance/sign-off | Change closure evidence |

Các bước có thể được tổ chức thành một pipeline tự động hoặc nhiều stages có approval. Nhưng thứ tự và dependency phải rõ. Ví dụ, không chạy contract migration xóa cột cũ trước khi tất cả application instances và workers đã ngừng sử dụng cột đó.

## 4. Nguồn sự thật và schema version

Mỗi môi trường cần biết schema hiện tại và schema mục tiêu.

Migration framework thường duy trì metadata table, ví dụ Flyway, Liquibase, Alembic, Rails hoặc công cụ nội bộ. Tên bảng và semantics khác nhau, vì vậy pipeline cần gọi CLI/API chính thức của framework.

Một schema version record có thể chứa:

- Migration version hoặc ID.
- Description.
- Checksum.
- Installed timestamp.
- Execution duration.
- Success/failure state.
- Tool version.
- Release/build identifier nếu framework hỗ trợ.

Kiểm tra bảng history theo đúng framework. Ví dụ minh họa với một bảng do ứng dụng quản lý:

~~~sql
SELECT
    version,
    description,
    checksum,
    installed_on,
    execution_time,
    success
FROM app_schema_migrations
ORDER BY version;
~~~

Không giả định bảng ví dụ này tồn tại trong mọi project.

### Source schema và target schema

Trước deploy, pipeline nên xác định:

- Current schema version.
- Pending migration IDs.
- Target version.
- Migration order.
- Checksum đã được duyệt.
- Có migration nào bị sửa sau khi deploy không.
- Có migration nào bị skip/failed/repair không.

Không tự động đánh dấu migration thành applied chỉ để làm pipeline xanh. Ledger phải phản ánh trạng thái database thực tế.

## 5. Immutable migration artifact

Migration file đã được deploy nên được xem là immutable. Nếu sửa nội dung sau khi môi trường đã chạy, checksum và reproducibility có thể sai lệch.

Quy tắc:

1. Migration mới có ID/version mới.
2. Artifact được build một lần và promote giữa environments.
3. Checksum được lưu cùng build metadata.
4. Không generate migration khác nhau tùy environment.
5. Không chỉnh sửa migration cũ để sửa lỗi đã triển khai.
6. Nếu cần repair, tạo migration mới hoặc dùng repair mechanism chính thức sau khi xác minh state.

Cùng một artifact nên được dùng ở staging và production. Cấu hình environment được inject riêng, nhưng nội dung migration phải ổn định.

## 6. Thiết kế pipeline có các gate rõ ràng

Ví dụ stages:

~~~yaml
pipeline:
  stages:
    - validate_artifact
    - preflight
    - migrate_expand
    - deploy_application
    - canary_observation
    - backfill
    - validate_constraints
    - post_deploy_checks
    - release_signoff
~~~

Đây là cấu trúc khái niệm; cú pháp thực tế phụ thuộc CI/CD platform.

Mỗi stage cần:

- Input rõ.
- Owner rõ.
- Timeout.
- Retry policy.
- Success criteria.
- Failure behavior.
- Evidence output.

Không retry một migration command tự động chỉ vì job timeout. Trước tiên phải xác minh transaction, migration ledger và object state để biết command đã commit hay chưa.

## 7. Preflight: xác nhận đúng target

Một trong những lỗi nguy hiểm nhất là chạy migration vào nhầm database/cluster.

Preflight nên xác minh:

- Environment name.
- Cluster/system identifier.
- Database name.
- Server address/port.
- Primary hay standby.
- PostgreSQL major version.
- Current schema version.
- Application service/tenant scope.
- Release ID và artifact checksum.

SQL context:

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS database_user,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    version() AS server_version,
    pg_is_in_recovery() AS is_standby,
    pg_postmaster_start_time() AS server_started_at;
~~~

Có thể lấy cluster system identifier bằng pg_controldata ở host phù hợp hoặc provider metadata. Không dựa vào database name đơn lẻ vì nhiều cluster có thể dùng cùng tên.

Pipeline phải dừng nếu target không khớp allowlist hoặc environment metadata.

## 8. Preflight: xác nhận version và configuration

Kiểm tra version:

~~~sql
SHOW server_version;
SHOW server_version_num;
~~~

Kiểm tra settings liên quan migration:

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'max_connections',
    'lock_timeout',
    'statement_timeout',
    'maintenance_work_mem',
    'max_wal_size',
    'wal_level',
    'max_replication_slots',
    'max_wal_senders'
)
ORDER BY name;
~~~

Migration có thể phụ thuộc extension, collation, encoding, timezone, locale hoặc feature theo major version. Ghi nhận những yếu tố ảnh hưởng behavior.

Không thay đổi server settings trong cùng release một cách ngầm định. Setting cần restart phải có change plan riêng hoặc stage rõ ràng.

## 9. Preflight: backup và restore readiness

Trước migration có nguy cơ cao, xác định:

- Backup gần nhất.
- Backup completion state.
- WAL archive health.
- PITR coverage.
- Restore point mục tiêu.
- RPO/RTO.
- Restore test gần nhất.
- Người chịu trách nhiệm recovery.

Backup tồn tại không đồng nghĩa restore được. Cần biết backup tool, encryption key, archive location và restore procedure.

Kiểm tra WAL archiving:

~~~sql
SELECT
    archived_count,
    failed_count,
    last_archived_wal,
    last_archived_time,
    last_failed_wal,
    last_failed_time
FROM pg_stat_archiver;
~~~

View này có thể không phản ánh toàn bộ backup system của managed provider. Đối chiếu provider backup metrics và external backup tooling.

### Backup decision theo loại migration

| Migration | Mức chuẩn bị thường cần |
| --- | --- |
| Add nullable column metadata-only | Backup policy hiện hành và rollback/forward-fix |
| Add constraint hoặc index lớn | Capacity, lock impact, backup readiness |
| Rewrite table/type conversion | Restore/PITR plan, disk headroom, maintenance window |
| Destructive data migration | Verified backup, restore drill, explicit approval |
| Major version/cluster migration | Full migration and rollback plan, compatibility testing |

Không dùng một quy tắc backup chung cho mọi thay đổi. Đánh giá blast radius và khả năng đảo ngược.

## 10. Preflight: capacity và workload

Trước khi chạy DDL/backfill lớn, kiểm tra:

- Database/table/index sizes.
- Free disk trên data/WAL/temp/backup volumes.
- WAL generation rate.
- Replication lag và slot retention.
- Long-running transactions.
- Lock blockers.
- Active sessions.
- CPU, memory và storage latency.
- Autovacuum progress.
- Connection pool utilization.

Ví dụ relation sizes:

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    pg_size_pretty(pg_relation_size(c.oid)) AS table_size,
    pg_size_pretty(pg_indexes_size(c.oid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_total_relation_size(c.oid) DESC
LIMIT 30;
~~~

Kiểm tra long-running transactions:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    left(query, 180) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Không terminate session tự động chỉ vì transaction lâu. Xác định owner và business impact trước.

## 11. Migration lock: chỉ một runner tại một thời điểm

Hai deployment cùng chạy migration có thể tạo duplicate objects, deadlocks, ledger races hoặc partial state. Dùng lock của migration framework hoặc một orchestration lock thống nhất.

Advisory lock có thể được dùng trong custom runner:

~~~sql
SELECT pg_advisory_lock(62501, 1);
-- Kiểm tra ledger, chạy migration và ghi kết quả.
SELECT pg_advisory_unlock(62501, 1);
~~~

Key chỉ là ví dụ. Tất cả runner phải dùng cùng convention. Session-level advisory lock được giữ tới khi unlock hoặc session kết thúc; transaction-level lock được giải phóng khi transaction kết thúc.

Một lock không thay thế ledger hoặc state verification. Nếu process crash, cần xác định migration đã commit tới đâu trước khi tiếp tục.

### Pipeline lock policy

- Lock scope theo database/schema/project.
- Có owner và timeout.
- Ghi thời điểm acquire/release.
- Không cho phép job khác bypass lock.
- Xử lý stale session theo runbook.
- Luôn release lock khi hoàn tất hoặc đóng session.
- Có alert nếu lock giữ quá lâu.

## 12. Lock timeout và statement timeout

Đặt timeout để DDL không chờ vô hạn:

~~~sql
SET lock_timeout = '5s';
SET statement_timeout = '20min';
~~~

Giá trị cần được chọn theo operation và workload. Không dùng cùng một timeout cho add column metadata-only, create index concurrently và backfill hàng tỷ rows.

- lock_timeout giới hạn thời gian chờ lock.
- statement_timeout giới hạn thời gian chạy statement.
- idle_in_transaction_session_timeout giới hạn session idle trong transaction.

Nếu statement bị timeout, transaction có thể chuyển sang aborted state. Migration runner cần rollback hoặc đóng transaction theo đúng semantics, sau đó kiểm tra trạng thái trước retry.

## 13. Transactional và non-transactional migrations

Nhiều DDL của PostgreSQL có thể chạy trong transaction. Nếu một bước lỗi trước COMMIT, rollback có thể hoàn tác toàn bộ thay đổi transactional.

Một số lệnh không chạy trong transaction block thông thường, ví dụ:

- CREATE INDEX CONCURRENTLY.
- DROP INDEX CONCURRENTLY.
- VACUUM.
- CREATE DATABASE.
- DROP DATABASE.

Một migration file có nhiều statement không tự động có nghĩa tất cả statements atomic. Framework có thể chia migration thành nhiều transactions hoặc chạy statement non-transactional riêng.

Pipeline phải biết migration nào:

- Transactional.
- Non-transactional.
- Có thể chạy lâu.
- Có lock mạnh.
- Có thể rewrite table.
- Có side effects.
- Có thể retry an toàn.

## 14. Phân loại migration theo rủi ro

Một taxonomy giúp pipeline chọn đúng gate:

| Nhóm | Ví dụ | Rủi ro chính |
| --- | --- | --- |
| Metadata change | Add nullable column | Lock acquisition, compatibility |
| Index build | CREATE INDEX CONCURRENTLY | I/O, invalid index, duration |
| Constraint | CHECK/FK validation | Scan, lock, legacy data violations |
| Data backfill | UPDATE theo batch | WAL, bloat, replication lag |
| Type/table rewrite | ALTER TYPE, rewrite | Disk, lock, downtime |
| Security | GRANT, RLS, owner | Access regression |
| Destructive | DROP/DELETE | Data loss, irreversible change |
| Extension | ALTER EXTENSION UPDATE | Binary/script/version compatibility |
| Partition | Attach/detach/reorganize | Lock, routing, data movement |

Risk score có thể dựa trên table size, lock mode, data loss, reversibility, runtime estimate, replication impact và number of consumers.

Không để developer tự chọn “low risk” mà không có rule/metadata hỗ trợ.

## 15. Expand-contract trong release pipeline

Expand-contract cho phép schema và application cùng chuyển đổi qua nhiều release.

Ví dụ đổi cột customer_name thành display_name.

**Release A — Expand:**
- Add display_name nullable.
- Giữ customer_name.
- Deploy app bridge có thể đọc/ghi tương thích.
- Bắt đầu backfill theo batch.

**Release B — Migrate:**
- Xác nhận backfill hoàn tất.
- Chuyển app sang đọc display_name.
- Có thể dual-write trong giai đoạn ngắn.
- Theo dõi app/worker còn dùng customer_name.

**Release C — Contract:**
- Dừng ghi/đọc customer_name.
- Xác nhận không còn consumer cũ.
- Drop customer_name trong migration riêng.

~~~mermaid
flowchart LR
    A["Release A: expand schema"] --> B["App bridge + backfill"]
    B --> C["Release B: switch reads/writes"]
    C --> D["Observe old consumers = 0"]
    D --> E["Release C: contract old schema"]
~~~

Không thêm cột mới và drop cột cũ trong cùng deployment nếu rolling deployment hoặc rollback window còn tồn tại.

## 16. Migration file và precondition/postcondition

Migration nên mô tả trạng thái đầu vào và kết quả kỳ vọng.

Precondition ví dụ: xác nhận cột chưa tồn tại hoặc đã tồn tại đúng definition.

~~~sql
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'orders'
  AND column_name = 'source_channel';
~~~

Postcondition tương ứng:

~~~sql
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'orders'
  AND column_name = 'source_channel';
~~~

Pipeline có thể dùng assertions trong migration framework hoặc custom verification scripts. Nếu object đã tồn tại nhưng definition khác, nên dừng thay vì coi IF NOT EXISTS là thành công.

Precondition/postcondition cần được ghi trong change metadata để reviewer biết migration sẽ thay đổi gì và bằng chứng nào xác nhận thành công.

## 17. Tích hợp migration vào CI

CI cần kiểm tra migration trước khi artifact được promote:

1. Validate SQL syntax và migration naming/order.
2. Kiểm tra migration không sửa lịch sử đã deploy.
3. Tạo database từ supported baseline.
4. Restore representative fixture nếu cần.
5. Chạy toàn bộ migration pending.
6. Kiểm tra schema assertions.
7. Kiểm tra data invariants.
8. Chạy application integration tests.
9. Kiểm tra rollback/recovery path khi có hỗ trợ.
10. Ghi runtime, logs và checksum.

Chỉ test từ database trống không đủ. Production có thể đang ở version N-3 với data distribution khác. Test upgrade path từ các baseline được hỗ trợ.

### CI không thể chứng minh production impact

CI test logic và compatibility trong môi trường kiểm soát. Nó không thể mô phỏng hoàn toàn production table size, concurrent transactions, I/O latency, lock contention và replication topology. Những yếu tố đó cần staging/load rehearsal và production rollout gates.

## 18. Tích hợp migration vào CD

Một CD flow điển hình:

1. Xác minh immutable artifact.
2. Resolve target database.
3. Acquire deployment/migration lock.
4. Chạy preflight.
5. Chạy expand migrations.
6. Xác minh migration ledger và schema.
7. Deploy application.
8. Deploy workers/schedulers.
9. Canary.
10. Theo dõi health.
11. Chạy backfill/validation.
12. Chạy post-deployment checks.
13. Release sign-off.
14. Contract migration ở release sau khi đủ điều kiện.

Với migration nhỏ và tương thích, một số bước có thể gộp. Với migration lớn hoặc destructive, tách stages và yêu cầu approval phù hợp.

## 19. Không chạy migration trong mọi application instance

Nếu mỗi pod/process khi start đều chạy migration, rolling deployment có thể tạo nhiều migration runners cạnh tranh.

Pattern thường tốt hơn:

- Một dedicated migration job.
- Chạy trước hoặc theo stage được định nghĩa.
- Dùng migration lock.
- Ghi output về deployment system.
- App instances chỉ kiểm tra schema compatibility khi khởi động.

Nếu framework buộc app tự migrate, phải bảo đảm framework có lock và behavior được kiểm chứng. Không giả định startup migration an toàn chỉ vì ứng dụng có thể restart nhiều lần.

## 20. Backfill trong deployment pipeline

Backfill lớn thường nên tách khỏi DDL migration:

- Schema expand trước.
- Application tương thích được deploy.
- Backfill chạy theo batch.
- Progress được ghi bền vững.
- Data reconciliation xác nhận completeness.
- Constraint validation diễn ra sau.
- Contract diễn ra ở release sau.

Mỗi batch nên có transaction ngắn, key range rõ, row count, checkpoint và throttle.

Ví dụ:

~~~sql
UPDATE public.orders
SET normalized_code = upper(code)
WHERE order_id > 100000
  AND order_id <= 110000
  AND normalized_code IS NULL;
~~~

Ví dụ range cố định chỉ minh họa. Production runner cần chọn range dựa trên key/index, đo rows thực tế và lưu progress.

Nếu progress marker và data update nằm trong cùng transaction, crash trước commit sẽ rollback cả hai. Nếu nằm ngoài transaction, cần idempotency để chạy lại an toàn.

## 21. Theo dõi migration progress

Migration runner nên xuất structured logs và metrics:

- migration_id.
- release_id.
- target database/cluster.
- start/end timestamp.
- current step.
- duration.
- rows processed.
- rows/sec.
- last key/checkpoint.
- lock wait duration.
- retry count.
- error SQLSTATE.
- success/failure.
- checksum.

Ví dụ log JSON:

~~~json
{
  "event": "migration_step_completed",
  "release_id": "release-2026.11.14.3",
  "migration_id": "V042__add_order_channel",
  "database": "sales",
  "step": "backfill_batch",
  "rows_processed": 10000,
  "last_key": 110000,
  "duration_ms": 842,
  "result": "success"
}
~~~

Không ghi raw customer values, secrets hoặc full payloads vào logs. Dùng IDs và aggregate counts.

## 22. Monitoring database trong release

Monitoring nên bao gồm bốn lớp:

**Availability:** connection success, server up, failover, connection pool exhaustion.

**Performance:** query latency, throughput, CPU, memory, I/O latency, locks, temp files.

**Storage/maintenance:** disk free, WAL growth, checkpoints, autovacuum, dead tuples, relation growth.

**Correctness/replication:** migration state, constraint validity, replication lag, slot retention, data reconciliation.

Một dashboard chỉ có CPU và database uptime không đủ để xác nhận release an toàn.

## 23. SLI/SLO cho release

Chọn SLI phản ánh hành vi người dùng và database:

| SLI | Ví dụ đo | Dùng để |
| --- | --- | --- |
| Availability | Successful requests / total requests | Xác nhận service usable |
| Latency | p50/p95/p99 query/API latency | Phát hiện regression |
| Error rate | Failed requests / total | Phát hiện lỗi runtime |
| DB saturation | CPU, connections, I/O queue | Phát hiện resource pressure |
| Lock impact | Lock wait duration/count | Phát hiện DDL contention |
| Replication lag | Replay/apply delay | Đánh giá downstream freshness |
| CDC lag | Source LSN to sink applied time | Đánh giá event freshness |
| Migration duration | Start-to-finish time | Capacity/plan accuracy |
| Data correctness | Reconciliation mismatch | Phát hiện missing/wrong data |

SLO threshold phải dựa trên baseline và business requirements. Không sao chép một con số latency chung cho mọi database.

### Baseline và comparison window

So sánh:

- Trước release.
- Trong migration.
- Canary window.
- Sau rollout.
- Cùng giờ/ngày workload nếu có seasonality.

Dùng cùng metric definitions và aggregation windows. Một p95 tăng ngắn do batch job có thể khác với regression kéo dài sau release.

## 24. Monitoring query latency và workload

Có thể dùng pg_stat_statements để theo dõi normalized query workload nếu extension đã được cấu hình.

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_read,
    temp_blks_written,
    left(query, 160) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

So sánh snapshots/deltas thay vì chỉ nhìn counter tích lũy. Ghi nhận stats_reset và server restart để tránh tính delta sai.

Khi query regression xuất hiện, dùng EXPLAIN (ANALYZE, BUFFERS) trên workload đại diện. ANALYZE thực thi query; không chạy tùy tiện trên statement ghi dữ liệu hoặc query rất nặng trong production.

## 25. Monitoring lock và blocking

Trong migration, lock wait có thể ảnh hưởng application traffic.

~~~sql
SELECT
    waiting.pid AS waiting_pid,
    waiting.application_name AS waiting_app,
    now() - waiting.query_start AS wait_age,
    left(waiting.query, 160) AS waiting_query,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_app,
    blocker.state AS blocker_state,
    now() - blocker.xact_start AS blocker_xact_age,
    left(blocker.query, 160) AS blocker_query
FROM pg_stat_activity AS waiting
JOIN LATERAL unnest(pg_blocking_pids(waiting.pid)) AS p(blocker_pid)
    ON true
JOIN pg_stat_activity AS blocker
    ON blocker.pid = p.blocker_pid
WHERE waiting.datname = current_database()
ORDER BY waiting.query_start;
~~~

Alert có thể dựa trên wait age, blocked session count và application latency. Đặt thresholds theo baseline.

Không tự động terminate blockers nếu chưa biết owner và tác động. Dừng migration runner hoặc cancel statement theo runbook có thể an toàn hơn terminate transaction nghiệp vụ.

## 26. Monitoring replication và WAL

Với physical replication:

~~~sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
~~~

Với logical slots:

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Theo dõi:

- Slot inactive.
- Restart LSN không tiến triển.
- Retained WAL vượt capacity.
- Standby replay lag.
- Logical subscriber errors.
- WAL archive failures.

Schema migration có thể tăng WAL mạnh, nhất là rewrite/backfill. Đưa replication/WAL metrics vào release dashboard.

## 27. Monitoring autovacuum và table health

Migration data lớn có thể tạo dead tuples và làm autovacuum tăng tải.

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

Theo dõi vacuum progress:

~~~sql
SELECT *
FROM pg_stat_progress_vacuum;
~~~

Counters có thể là estimates và reset. Dùng trends, relation size và vacuum logs để hiểu tình hình.

Không chạy VACUUM FULL tự động chỉ vì dead tuple estimate tăng. VACUUM FULL rewrite table và cần lock mạnh; cân nhắc standard VACUUM, autovacuum tuning hoặc table rewrite plan theo evidence.

## 28. Canary và staged rollout

Với hệ thống lớn, rollout theo từng nhóm:

- Một database/tenant canary.
- Một application instance.
- Một partition/consumer group.
- Một phần traffic.
- Một vùng/cluster.

Canary cần kiểm tra cả schema và behavior:

- Migration thành công.
- App đọc/ghi đúng.
- Error rate không tăng.
- Latency trong ngưỡng.
- Lock waits không bất thường.
- Data invariants đạt.
- Replication/CDC lag ổn định.
- Không có worker version cũ vi phạm compatibility.

Nếu canary không đạt, dừng rollout ở stage hiện tại. Không tiếp tục nhân rộng lỗi sang toàn bộ tenants.

## 29. Post-deployment verification: schema

Sau migration, xác nhận schema thực tế:

- Migration ledger đạt target version.
- Không còn migration failed/pending ngoài dự kiến.
- Columns/types/defaults/nullability đúng.
- Indexes tồn tại và valid.
- Constraints tồn tại và validated.
- Triggers/functions/views đúng version.
- Extensions đúng version.
- Ownership/grants/RLS đúng.
- Sequences/identity state hợp lệ.

### Kiểm tra indexes invalid

~~~sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indrelid::regclass AS table_name,
    i.indisvalid,
    i.indisready,
    i.indislive
FROM pg_index AS i
JOIN pg_class AS c
    ON c.oid = i.indexrelid
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND (NOT i.indisvalid OR NOT i.indisready)
ORDER BY i.indexrelid::regclass::text;
~~~

Không có rows là tín hiệu tốt cho phạm vi query, nhưng vẫn cần kiểm tra indexes cụ thể mà release thay đổi.

### Kiểm tra constraints chưa validate

~~~sql
SELECT
    conrelid::regclass AS table_name,
    conname,
    contype,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE NOT convalidated
ORDER BY conrelid::regclass::text, conname;
~~~

Một số constraint có thể được chủ đích để NOT VALID trong expand phase. So sánh với expected state của release, không đòi mọi constraint toàn cluster phải validated nếu hệ thống có ngoại lệ được quản lý.

## 30. Post-deployment verification: data

Schema đúng không chứng minh dữ liệu đúng.

Kiểm tra:

- Backfill completion.
- NULL/duplicate counts.
- Foreign key orphans.
- Check constraint violations.
- Aggregate totals.
- Sequence position.
- Row counts theo key ranges.
- Old/new column consistency trong expand-contract.
- CDC/outbox completeness.
- Data retention/partition coverage.

Ví dụ kiểm tra dữ liệu chưa backfill:

~~~sql
SELECT count(*) AS remaining_rows
FROM public.orders
WHERE normalized_code IS NULL
  AND code IS NOT NULL;
~~~

Ví dụ kiểm tra duplicate business key:

~~~sql
SELECT
    external_reference,
    count(*) AS duplicate_count
FROM public.orders
WHERE external_reference IS NOT NULL
GROUP BY external_reference
HAVING count(*) > 1
ORDER BY duplicate_count DESC;
~~~

Ví dụ so sánh hai cột trong giai đoạn chuyển đổi:

~~~sql
SELECT count(*) AS mismatched_rows
FROM public.customers
WHERE display_name IS DISTINCT FROM customer_name;
~~~

Các query này cần điều chỉnh theo business rules. NULL có thể hợp lệ; không sửa dữ liệu chỉ để làm số mismatch về 0 nếu chưa hiểu semantics.

## 31. Post-deployment verification: permissions và security

Migration có thể vô tình thay đổi owner, grants, default privileges hoặc RLS.

Kiểm tra:

- Application role có đúng quyền đọc/ghi không.
- Role không có quyền thừa.
- Schema/table owner đúng.
- Default privileges áp dụng cho future objects.
- RLS enabled/forced đúng.
- Policies có predicate đúng.
- SECURITY DEFINER functions có owner và search_path an toàn.
- Connector/replication role có scope phù hợp.

Ví dụ xem grants:

~~~sql
SELECT
    grantee,
    table_schema,
    table_name,
    privilege_type,
    is_grantable
FROM information_schema.role_table_grants
WHERE table_schema = 'public'
ORDER BY grantee, table_name, privilege_type;
~~~

Information schema có thể chỉ hiển thị quyền trong scope mà role hiện tại được phép thấy. Với audit toàn bộ, dùng catalog và role phù hợp.

Không chỉ kiểm tra app query thành công; cần xác nhận app role không vô tình có SUPERUSER, BYPASSRLS hoặc quyền DDL không cần thiết.

## 32. Post-deployment verification: application compatibility

Kiểm tra mọi process truy cập database:

- Web/API instances.
- Background workers.
- Cron/scheduled jobs.
- ETL/ELT jobs.
- Admin scripts.
- CDC connectors.
- Reporting/BI clients.
- Read replicas/subscribers.
- Long-running sessions và connection pools.

Theo dõi version thực tế của từng instance, không chỉ deployment controller state. Worker cũ có thể vẫn chạy và truy cập column đã contract.

Smoke tests nên xác nhận các hành vi nghiệp vụ quan trọng, không chỉ health endpoint.

## 33. Post-deployment verification: query plans

Schema migration có thể làm optimizer chọn plan khác do index, statistics hoặc data distribution thay đổi.

Kiểm tra query trọng yếu:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total_amount
FROM public.orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 50;
~~~

Đây là query minh họa; thay bằng query đại diện và parameter values phù hợp. EXPLAIN ANALYZE thực thi statement và có thể gây tải; không dùng với DML nếu chưa kiểm soát side effects.

Kiểm tra:

- Index scan/seq scan có phù hợp không.
- Estimated rows so với actual rows.
- Shared/local/temp blocks.
- Sort/hash spill.
- Nested loop behavior.
- Execution time.
- Planning time.
- Lock/wait behavior.

Nếu statistics stale sau bulk changes, cân nhắc ANALYZE theo kế hoạch:

~~~sql
ANALYZE public.orders;
~~~

Không chạy ANALYZE toàn database một cách tùy tiện trong peak hours nếu database lớn và cần resource planning.

## 34. Post-deployment verification: replication và CDC

Nếu database có replicas hoặc CDC:

- Physical standby replay lag trong ngưỡng.
- Logical subscriptions không có apply errors.
- Subscriber schema đã được triển khai.
- Replication slots active và tiến triển.
- Retained WAL trong budget.
- Connector source LSN tiến lên.
- Broker lag không tăng kéo dài.
- Consumer sink commit thành công.
- Outbox event được relay.
- Reconciliation không phát hiện gap.

DDL không tự động được áp dụng tới mọi logical subscriber hoặc downstream sink. Post-deploy check phải xác nhận schema parity và data parity theo topology thực tế.

## 35. Post-deployment verification: sequence và identity

Khi import, restore hoặc bulk load explicit IDs, sequence có thể thấp hơn max key và tạo duplicate key ở lần INSERT tiếp theo.

Kiểm tra sequence ownership và state. Với sequence cụ thể:

~~~sql
SELECT
    pg_get_serial_sequence('public.orders', 'order_id') AS sequence_name;
~~~

Sau khi xác định đúng sequence và policy, có thể so sánh với max key. Không tự setval mọi sequence bằng một script chung mà chưa kiểm tra increment, cycling, cache và concurrent writes.

Một sequence là object độc lập; native logical replication không mặc định đồng bộ sequence state như row changes. Với cutover, sequence sync phải là bước rõ ràng.

## 36. Health checks: readiness, liveness và startup

Application health endpoints có vai trò khác nhau:

- **Liveness:** process còn hoạt động; không nên phụ thuộc mọi downstream tạm thời.
- **Readiness:** instance có thể nhận traffic với dependency và schema compatibility cần thiết.
- **Startup:** process đã hoàn thành initialization.

Readiness check có thể xác nhận database connectivity và schema compatibility version. Không nên chạy migration trong mỗi readiness probe.

Schema compatibility check nên nhẹ, có timeout và đọc một metadata source ổn định. Nếu schema không tương thích, instance không nhận traffic và pipeline phát hiện deployment ordering issue.

## 37. Release thresholds và stop conditions

Mỗi release cần thresholds được định nghĩa trước:

- API/database error rate.
- p95/p99 latency.
- Connection pool saturation.
- Lock wait duration.
- Deadlocks.
- WAL growth.
- Replication/CDC lag.
- Disk free.
- Migration runtime.
- Backfill progress.
- Data mismatch count.
- Failed smoke tests.

Ví dụ policy khái niệm:

~~~yaml
release_gates:
  migration:
    status: success
    unexpected_pending: 0
  application:
    error_rate_delta: within_baseline
    p95_latency_delta: within_baseline
  database:
    lock_waits: below_threshold
    disk_free: above_reserve
    replication_lag: within_slo
  data:
    reconciliation_mismatches: 0
~~~

Đây là cấu trúc minh họa, không phải threshold mặc định. Chọn số đo và ngưỡng theo SLO, baseline và business risk.

## 38. Rollback application, rollback schema và forward-fix

Ba hành động này khác nhau:

**Rollback application:** đưa binary/config về phiên bản trước. Chỉ an toàn nếu schema hiện tại vẫn tương thích với code cũ.

**Rollback schema:** chạy migration ngược hoặc phục hồi schema/data. Có thể gây mất dữ liệu, lock mạnh hoặc không thể đảo ngược side effects.

**Forward-fix:** tạo migration/application change mới để đưa hệ thống từ trạng thái hiện tại tới trạng thái đúng.

| Tình trạng | Hướng cân nhắc |
| --- | --- |
| Expand migration thành công, app deploy lỗi | Rollback app; giữ schema expand nếu app cũ tương thích |
| App mới lỗi nhưng schema tương thích | Rollback app hoặc forward-fix |
| Data backfill đã tạo dữ liệu mới | Forward-fix/reconcile thường an toàn hơn down migration |
| Index concurrently invalid | Xử lý index theo runbook rồi retry step |
| Contract đã drop column | App cũ có thể không chạy; cần restore/forward recovery |
| Data corruption/loss | Incident recovery, backup/PITR và reconciliation |
| Target đã nhận writes mới | Đánh giá reverse sync trước khi chuyển về source |

Không giả định mọi migration đều có down script an toàn. Down migration cần được test và đánh giá data loss trước release.

## 39. Khi nào dừng rollout?

Dừng rollout khi:

- Migration failed hoặc ledger state không rõ.
- Schema postcondition không đạt.
- Index invalid/constraint state ngoài expected.
- Data reconciliation mismatch vượt policy.
- Application error rate/latency vượt threshold.
- Lock wait ảnh hưởng traffic.
- Disk/WAL capacity xuống dưới reserve.
- Replication/CDC lag vượt recovery budget.
- Worker cũ không tương thích với schema contract.
- Không có backup/restore path cho change rủi ro cao.

Stop rollout không tự động có nghĩa rollback ngay. Giữ hệ thống ở trạng thái tương thích, thu thập evidence và chọn recovery path dựa trên commit/data state.

## 40. Incident workflow khi migration thất bại

### Contain

- Dừng migration runner và deployment stage tiếp theo.
- Giữ app ở version tương thích.
- Không retry ngay.
- Bảo toàn logs, artifact và timestamps.
- Xác định có traffic/data writes tiếp tục không.

### Determine state

- Xác nhận target cluster/database.
- Xem active sessions và transaction.
- Đọc migration ledger.
- Kiểm tra catalog objects.
- Kiểm tra data changes/backfill.
- Kiểm tra index validity và constraints.
- Kiểm tra replication slots/WAL.
- Xác định app/worker versions.

### Recover

- Rollback transaction nếu chưa commit.
- Resume batch nếu progress/idempotency bảo đảm.
- Rebuild index nếu đúng diagnosis.
- Validate constraint sau khi sửa dữ liệu.
- Forward-fix nếu có dependencies.
- Restore/PITR nếu integrity không thể đảm bảo.
- Reconcile source/sink trước khi mở lại traffic.

### Verify

- Schema và ledger khớp.
- Data invariants đạt.
- App/worker compatibility đạt.
- Replication/CDC healthy.
- Metrics trở lại ngưỡng.
- Evidence và reviewer sign-off hoàn tất.

## 41. Change record và audit trail

Một change record nên có:

~~~yaml
change_id: CHG-2026-0625
release_id: release-2026.11.14.4
environment: production
database: sales
source_schema_version: "041"
target_schema_version: "042"
migration_artifact: "db-migrations-2026.11.14.4"
artifact_checksum: "sha256:example"
execution:
  started_at: "2026-11-14T09:00:00Z"
  finished_at: "2026-11-14T09:03:21Z"
  result: "success"
post_deploy:
  schema_checks: "passed"
  data_checks: "passed"
  application_smoke: "passed"
  replication: "passed"
decision: "release_accepted"
owner: "database_operations"
reviewer: "release_manager"
~~~

Đây là ví dụ; timestamp, IDs và checksum phải lấy từ hệ thống thật. Không ghi secrets hoặc customer data.

Audit trail cần trả lời:

- Ai tạo/duyệt migration?
- Artifact nào đã deploy?
- Vào environment nào?
- Khi nào bắt đầu/kết thúc?
- Có retry/repair nào?
- Kết quả verification nào?
- Ai quyết định rollback/forward-fix?
- Evidence ở đâu?

## 42. Runbook post-deployment

### Giai đoạn A: Migration

- Xác nhận đúng target.
- Acquire lock.
- Ghi current/target schema version.
- Chạy migration.
- Lưu output/checksum.
- Kiểm tra ledger.
- Kiểm tra postconditions.

### Giai đoạn B: Application rollout

- Deploy app bridge/compatible version.
- Deploy workers và scheduled jobs.
- Canary traffic.
- Kiểm tra error/latency.
- Kiểm tra schema compatibility.
- Mở rộng rollout theo waves.

### Giai đoạn C: Data and database health

- Theo dõi backfill progress.
- Validate constraints.
- Analyze nếu cần.
- Kiểm tra index validity.
- Kiểm tra data invariants.
- Kiểm tra replication/CDC.
- Kiểm tra disk/WAL/autovacuum.

### Giai đoạn D: Acceptance

- Smoke tests.
- Business reconciliation.
- SLO thresholds.
- Security/permissions.
- Evidence.
- Reviewer sign-off.
- Contract stage chỉ khi đủ điều kiện.

## 43. Tự động hóa post-deployment checks

Có thể tạo một verification job chạy read-only queries:

- Current database/cluster identity.
- Current schema version.
- Expected columns/types.
- Expected indexes and validity.
- Expected constraints and validation.
- Extension versions.
- Role/grant assertions.
- Data count/aggregate checks.
- Replication slot state.
- Application smoke endpoint.
- CDC lag and event freshness.

Kết quả nên được xuất structured JSON để pipeline parse:

~~~json
{
  "release_id": "release-2026.11.14.4",
  "database": "sales",
  "schema_version": "042",
  "checks": [
    {
      "name": "migration_version",
      "status": "passed"
    },
    {
      "name": "orders_index_valid",
      "status": "passed"
    },
    {
      "name": "backfill_complete",
      "status": "passed",
      "remaining_rows": 0
    },
    {
      "name": "replication_lag",
      "status": "passed"
    }
  ],
  "overall": "passed"
}
~~~

Output thực tế cần include timestamp, tool version, target identity và evidence references. Không chỉ trả một boolean mà không giải thích check nào fail.

## 44. Kiểm tra sau deploy không nên gây tải quá mức

Verification query cũng có thể làm production chậm. Thiết kế:

- Dùng catalog lookups cho schema assertions.
- Dùng indexed predicates cho data checks.
- Chia chunk cho reconciliation lớn.
- Giới hạn statement timeout.
- Chạy aggregate scan trong window phù hợp.
- Không chạy nhiều full-table scans song song.
- Cache kết quả checks ngắn hạn nếu phù hợp.
- Tách smoke checks nhanh khỏi deep audits dài.

Nếu cần deep data validation, chạy async job có progress và owner. Release có thể ở trạng thái “deployed, validation pending” nếu policy cho phép, nhưng không được ghi nhận fully accepted trước khi deep check đạt.

## 45. Observability và correlation

Mọi log/metric/event liên quan release nên gắn:

- release_id.
- change_id.
- migration_id.
- environment.
- database/cluster identity.
- service/version.
- tenant/wave nếu có.
- trace/correlation ID.

Điều này giúp nối migration runner logs với application errors, database waits, connector lag và incident records.

Không đưa raw SQL parameters chứa PII vào tracing. Dùng queryid/normalized query và sampled metadata.

## 46. Release metrics và dashboard layout

Một dashboard release nên có các nhóm:

| Nhóm | Metrics |
| --- | --- |
| Release progress | Stage, migration ID, duration, current version |
| Database health | Availability, CPU, memory, connections |
| Query behavior | p95/p99, error rate, top query deltas |
| Locking | Waiters, blocker age, deadlocks |
| Storage | Disk free, WAL rate, temp bytes |
| Maintenance | Autovacuum, dead tuples, analyze age |
| Replication | Replay lag, slot retained WAL |
| CDC | Source LSN, broker lag, sink applied time |
| Correctness | Schema assertions, reconciliation mismatches |
| Application | Error rate, request latency, worker health |

Dùng dashboard để hỗ trợ quyết định, không thay runbook. Alert cần có owner, severity và action.

## 47. Phòng tránh drift giữa environments

Mỗi environment cần chạy cùng migration artifact và cùng ordering. Kiểm soát:

- Không sửa schema thủ công ngoài break-glass.
- Hotfix phải được chuyển thành migration.
- So sánh schema snapshot theo scope.
- Kiểm tra extension versions.
- Quản lý grants/default privileges.
- Ghi exceptions có owner/expiry.
- Dùng same build artifact.
- Kiểm tra baseline versions được hỗ trợ.
- Không bỏ qua migration failed.
- Có reconciliation trước khi promote.

Production có thể có khác biệt được chủ đích như tablespace, replica topology hoặc grants. Schema diff cần phân loại expected vs accidental, không apply toàn bộ diff tự động.

## 48. Kiểm tra môi trường staging giống production

Staging nên gần production ở các khía cạnh ảnh hưởng migration:

- PostgreSQL major/minor version.
- Extensions và versions.
- Collation/encoding.
- Table/index size gần thực tế hoặc có scale model.
- Data distribution/skew.
- Replication topology.
- Parameter settings.
- Roles/grants.
- Connection pool behavior.
- Concurrent workload.

Nếu staging nhỏ hơn production nhiều, thời gian migration và lock behavior có thể khác hoàn toàn. Chạy rehearsal với dataset representative hoặc estimate bằng measured production metadata.

## 49. Release cadence và maintenance window

Không phải mọi migration cần maintenance window. Quyết định dựa trên:

- Lock mode.
- Table rewrite.
- Runtime estimate.
- Application compatibility.
- Replication/CDC impact.
- Data loss risk.
- Recovery complexity.
- Business traffic pattern.

Online DDL vẫn có thể gây lock acquisition waits hoặc I/O pressure. Maintenance window không loại bỏ rủi ro; nó chỉ giúp chọn thời điểm ít ảnh hưởng hơn.

## 50. Quản lý release nhiều tenant/database

Nếu ứng dụng có nhiều database/tenant, rollout cần inventory theo target:

| Tenant | Current | Target | Migration state | Verification |
| --- | --- | --- | --- | --- |
| tenant_a | 041 | 042 | complete | passed |
| tenant_b | 041 | 042 | failed | pending |
| tenant_c | 041 | 042 | pending | not started |

Quy trình:

1. Xác định danh sách target từ deployment inventory.
2. Chọn concurrency phù hợp.
3. Chạy canary tenant.
4. Dừng khi lỗi vượt policy.
5. Lưu trạng thái riêng từng tenant.
6. Resume chỉ tenant pending/failed sau khi xác minh.
7. Không chạy lại tenant complete trừ khi recovery plan yêu cầu.
8. Bật feature sau khi coverage đạt threshold.

Một tenant thành công không chứng minh toàn bộ fleet thành công.

## 51. Các anti-pattern trong deployment

1. Chạy migration ở mỗi application startup mà không có lock.
2. Chạy migration và deploy code song song khi code cần schema mới ngay lập tức.
3. Sửa migration cũ sau khi đã deploy.
4. Dùng timeout rồi retry tự động mà không xác minh commit state.
5. Đánh dấu ledger applied thủ công.
6. Gộp destructive DDL với application rollout không có compatibility phase.
7. Backfill toàn bảng trong một transaction dài.
8. Chạy CREATE INDEX CONCURRENTLY trong transaction block.
9. Không theo dõi invalid indexes sau index build.
10. Không theo dõi replication lag/WAL trong data migration.
11. Dùng staging dataset quá nhỏ rồi suy ra production runtime.
12. Coi health endpoint xanh là release acceptance.
13. Chỉ kiểm tra schema mà bỏ qua business data.
14. Chỉ kiểm tra database mà bỏ qua worker/cron/CDC consumers.
15. Drop column ngay khi app mới đã deploy một phần.
16. Rollback database khi target đã nhận writes mới mà không reverse-sync.
17. Dùng VACUUM FULL như phản ứng tự động khi bloat tăng.
18. Không giữ migration logs/checksum/release ID.
19. Chạy deep verification scan song song với peak workload.
20. Đóng change khi reconciliation hoặc restore readiness chưa đạt.

## 52. Bài tập thực hành có đáp án

### Bài 1. Vì sao migration cần thuộc release lifecycle?

**Đáp án:** Vì schema và application là một contract; phải biết artifact, target version, thứ tự triển khai và trạng thái sau deploy.

### Bài 2. Immutable migration artifact nghĩa là gì?

**Đáp án:** Artifact đã build và deploy không bị sửa nội dung; thay đổi sau đó được tạo bằng migration mới.

### Bài 3. Preflight cần xác nhận gì trước tiên?

**Đáp án:** Đúng environment, cluster/database identity, current schema version và target artifact.

### Bài 4. Vì sao backup chưa đủ nếu chưa restore test?

**Đáp án:** Backup file tồn tại không chứng minh restore procedure, keys, WAL chain và application recovery hoạt động.

### Bài 5. Vì sao chỉ một migration runner nên hoạt động tại một thời điểm?

**Đáp án:** Tránh duplicate DDL, race conditions, deadlocks và ledger inconsistency.

### Bài 6. lock_timeout khác statement_timeout thế nào?

**Đáp án:** lock_timeout giới hạn thời gian chờ lock; statement_timeout giới hạn tổng thời gian statement.

### Bài 7. Nêu một DDL không chạy trong transaction block thông thường.

**Đáp án:** CREATE INDEX CONCURRENTLY.

### Bài 8. Expand-contract có lợi ích gì?

**Đáp án:** Cho phép app cũ và mới cùng tồn tại trong rolling deployment bằng schema tương thích theo từng giai đoạn.

### Bài 9. Vì sao không drop column cũ ngay khi add column mới?

**Đáp án:** Instance cũ, worker hoặc scheduled jobs có thể vẫn đọc/ghi column cũ.

### Bài 10. Vì sao backfill nên chạy theo batch?

**Đáp án:** Giảm transaction duration, WAL burst, lock pressure và tạo checkpoint để resume.

### Bài 11. Migration runner nên log những metadata nào?

**Đáp án:** Release ID, migration ID, target, checksum, timestamps, duration, progress, retries và result.

### Bài 12. SLI nào giúp phát hiện query regression?

**Đáp án:** Query/API p95/p99 latency, error rate và workload statistics so với baseline.

### Bài 13. Vì sao monitoring CPU đơn lẻ không đủ?

**Đáp án:** Migration có thể gây lock waits, WAL growth, disk pressure, replication lag hoặc data errors mà CPU vẫn thấp.

### Bài 14. pg_stat_replication dùng để theo dõi gì?

**Đáp án:** Physical replication sender state và LSN/lag fields cho các connected standbys.

### Bài 15. pg_replication_slots giúp phát hiện gì?

**Đáp án:** Slot inactive, restart_lsn, confirmed_flush_lsn và trạng thái giữ WAL.

### Bài 16. Post-deploy schema checks nên xác minh gì?

**Đáp án:** Ledger, columns/types/defaults, indexes validity, constraints, extensions, owner/grants và RLS.

### Bài 17. Vì sao cần data checks ngoài schema checks?

**Đáp án:** Schema đúng không chứng minh backfill, data integrity hoặc business invariants đúng.

### Bài 18. Vì sao cần kiểm tra application workers sau deploy?

**Đáp án:** Worker cũ có thể tiếp tục truy cập schema đã thay đổi dù web/API instances đã nâng cấp.

### Bài 19. EXPLAIN ANALYZE có tác động gì?

**Đáp án:** Nó thực thi query; cần chọn query đại diện và kiểm soát side effects/tải.

### Bài 20. Khi nào rollback application có thể an toàn?

**Đáp án:** Khi schema hiện tại vẫn tương thích với code cũ và dữ liệu mới không làm code cũ lỗi.

### Bài 21. Khi nào forward-fix thường phù hợp hơn down migration?

**Đáp án:** Khi dữ liệu mới đã phụ thuộc schema mới hoặc rollback có nguy cơ mất dữ liệu/side effects.

### Bài 22. Vì sao health endpoint xanh chưa đủ để đóng release?

**Đáp án:** Nó không xác minh đầy đủ schema, data reconciliation, replication, permissions và business behavior.

### Bài 23. Release gate là gì?

**Đáp án:** Điều kiện bắt buộc phải đạt trước khi pipeline chuyển sang stage tiếp theo.

### Bài 24. Vì sao cần canary?

**Đáp án:** Giới hạn blast radius và quan sát behavior trên một phần traffic/tenant trước khi rollout rộng.

### Bài 25. Khi nào nên dừng rollout?

**Đáp án:** Khi migration state không rõ, postconditions fail, SLO vượt ngưỡng, disk/WAL thiếu, replication lag cao hoặc app không tương thích.

### Bài 26. Vì sao không retry migration chỉ vì CI job timeout?

**Đáp án:** Server có thể đã commit; cần xác minh transaction, ledger và catalog trước khi retry.

### Bài 27. Release evidence nên có gì?

**Đáp án:** Artifact/checksum, target identity, migration logs, ledger state, app versions, post-check results và sign-off.

### Bài 28. Vì sao cần cùng artifact giữa staging và production?

**Đáp án:** Để kết quả rehearsal áp dụng cho chính migration content sẽ được deploy.

### Bài 29. Một release nhiều tenant cần theo dõi ra sao?

**Đáp án:** Lưu current/target version, migration state và verification result riêng từng tenant/database.

### Bài 30. Khi nào được đóng change?

**Đáp án:** Khi migration, application, data, security, replication, monitoring và acceptance criteria đều đạt, evidence đầy đủ và reviewer sign-off.

## 53. Checklist đưa migration vào release process

### Plan và build

- [ ] Migration có ID/version mới.
- [ ] Artifact immutable và checksum được lưu.
- [ ] Current/target schema versions rõ.
- [ ] Migration risk và reversibility được phân loại.
- [ ] App/worker compatibility được đánh giá.
- [ ] Expand-contract được dùng khi cần.
- [ ] Upgrade path từ supported baselines đã test.
- [ ] Change owner/reviewer được xác định.

### Preflight

- [ ] Đúng cluster/database/environment.
- [ ] PostgreSQL/extension versions tương thích.
- [ ] Backup và PITR readiness được xác nhận.
- [ ] Disk/WAL/temp capacity đủ.
- [ ] Long-running transactions/blockers đã xem.
- [ ] Replication/CDC health đạt.
- [ ] Maintenance window/stop conditions rõ.
- [ ] Migration lock policy sẵn sàng.

### Execute

- [ ] Chỉ một migration runner.
- [ ] Timeout phù hợp.
- [ ] Transactional/non-transactional behavior đã biết.
- [ ] Migration logs có release/migration IDs.
- [ ] Backfill có batch/checkpoint.
- [ ] Không retry khi chưa xác minh state.
- [ ] Ledger được kiểm tra sau execution.
- [ ] Lock được giải phóng.

### Observe và verify

- [ ] Canary/rollout stage đạt.
- [ ] Error rate/latency trong ngưỡng.
- [ ] Lock waits/deadlocks không bất thường.
- [ ] Disk/WAL/replication lag trong budget.
- [ ] Indexes valid.
- [ ] Constraints đúng validation state.
- [ ] Backfill/reconciliation đạt.
- [ ] Permissions/RLS đúng.
- [ ] App/worker/scheduled jobs tương thích.
- [ ] Query plans trọng yếu không regression.
- [ ] CDC/downstream consumers healthy.
- [ ] Smoke tests và business checks đạt.

### Close

- [ ] Release artifact/checksum được lưu.
- [ ] Migration ledger đạt target.
- [ ] Post-deploy report được lưu.
- [ ] Exceptions có owner/expiry.
- [ ] Rollback/forward-fix decision được ghi.
- [ ] Reviewer sign-off.
- [ ] Contract migration được lên kế hoạch riêng nếu còn legacy schema.
- [ ] Change được đóng theo policy.

## 54. Tài liệu PostgreSQL chính thức

Đọc tài liệu theo major version đang triển khai:

- [SQL Commands](https://www.postgresql.org/docs/current/sql-commands.html) — tham chiếu các lệnh DDL và transaction behavior.
- [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) — thay đổi bảng, constraints và validation.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) — tạo index và CONCURRENTLY.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — lock modes và advisory locks.
- [Lock Management](https://www.postgresql.org/docs/current/runtime-config-locks.html) — lock timeout và deadlock settings.
- [Statement Behavior](https://www.postgresql.org/docs/current/runtime-config-client.html) — statement_timeout và session settings.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — activity, replication, I/O và progress views.
- [pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html) — query workload statistics.
- [pg_stat_io](https://www.postgresql.org/docs/current/monitoring-stats.html) — I/O statistics theo backend/context.
- [Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html) — backup, WAL archive và point-in-time recovery.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html) — tạo physical base backup.
- [pg_verifybackup](https://www.postgresql.org/docs/current/app-pgverifybackup.html) — kiểm tra backup manifest.
- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html) — publication, subscription và schema considerations.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html) — WAL sender, slots và replication parameters.
- [Statistics Configuration](https://www.postgresql.org/docs/current/runtime-config-statistics.html) — statistics collection settings.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — VACUUM, ANALYZE và autovacuum.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html) — query plan và ANALYZE behavior.
- [CREATE ROLE](https://www.postgresql.org/docs/current/sql-createrole.html) — role attributes.
- [Privileges](https://www.postgresql.org/docs/current/ddl-priv.html) — ownership và access control.

Các tài liệu /current/ có thể mô tả phiên bản mới hơn server đang chạy. Kiểm tra tài liệu đúng major version, migration framework và CI/CD platform trước khi đưa command vào production pipeline.

## 55. Tổng kết

**Migration, monitoring và post-deployment verification phải là một chuỗi có gate và bằng chứng trong cùng release lifecycle.** Migration thay đổi schema; application rollout thay đổi consumer behavior; monitoring cho biết hệ thống đang hoạt động thế nào; post-deployment checks xác nhận database và nghiệp vụ đã đạt trạng thái mong đợi.

1. **Đóng gói migration cùng release artifact.** Giữ migration immutable và ghi checksum.
2. **Preflight đúng target và schema version.** Xác minh cluster identity, backup, capacity, locks và replication.
3. **Chỉ một migration runner hoạt động tại một thời điểm.** Dùng lock và timeout có kiểm soát.
4. **Phân loại DDL và data changes theo risk.** Transactional behavior, lock impact, WAL và reversibility quyết định cách triển khai.
5. **Dùng expand-contract cho rolling deployment.** Chỉ xóa schema cũ khi không còn consumer phụ thuộc.
6. **Tách backfill dài khỏi DDL khi phù hợp.** Dùng batch, checkpoint và reconciliation.
7. **Theo dõi database và application cùng lúc.** Latency, errors, locks, disk, WAL, replication và CDC đều ảnh hưởng release.
8. **Canary và staged rollout giới hạn blast radius.** Dừng khi health hoặc correctness vượt threshold.
9. **Post-deployment checks phải xác minh schema, data, permissions, application và replication.**
10. **Rollback application không đồng nghĩa rollback schema.** Đánh giá compatibility và writes mới trước khi chọn recovery.
11. **Forward-fix thường phù hợp khi dữ liệu đã phụ thuộc schema mới.** Down migration có thể gây mất dữ liệu.
12. **Lưu release evidence và audit trail.** Artifact, ledger, metrics, checks và sign-off phải liên kết được.
13. **Chỉ đóng change khi acceptance criteria đạt.** Health endpoint xanh chưa đủ chứng minh release đúng.

Một quy trình triển khai tốt giúp team biết trước điều gì sẽ thay đổi, quan sát được điều gì đang diễn ra và chứng minh được trạng thái sau cùng. PostgreSQL migration khi đó trở thành một bước có kiểm soát trong release, thay vì một thao tác SQL rời rạc khó truy vết và khó phục hồi.
