# Quy trình vận hành và bàn giao sau phát hành

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chúng ta quản lý thay đổi schema và dữ liệu bằng **changelog**, **changeset**, **precondition**, **checksum** và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài thuộc chương **Vận hành** này tập trung vào quy trình sau khi một release database đã được triển khai: xác minh kết quả, theo dõi hệ thống, lưu bằng chứng, xử lý ngoại lệ và bàn giao đầy đủ cho đội vận hành tiếp nhận.

Một lệnh `liquibase update` kết thúc thành công chỉ cho biết Liquibase đã hoàn tất các thao tác mà nó xử lý trong lần chạy đó. Để release thực sự sẵn sàng vận hành, nhóm còn phải xác nhận **đúng database đã được cập nhật, đúng changeset được ghi nhận, schema và dữ liệu đạt trạng thái mong muốn, ứng dụng hoạt động, chỉ số vận hành ổn định và người trực có đủ thông tin để xử lý sự cố**.

Bàn giao sau phát hành không phải chỉ gửi thông báo “deploy xong”. Đó là quá trình chuyển giao trạng thái kỹ thuật, rủi ro còn lại, bằng chứng và trách nhiệm giữa nhóm phát triển, DBA, SRE, đội ứng dụng và on-call. Mục tiêu là để người tiếp nhận có thể trả lời nhanh: release nào đã chạy, chạy ở đâu, có gì thay đổi, đã kiểm tra gì, điều gì còn cần theo dõi và phải làm gì nếu có sự cố.

## 1. Vòng đời vận hành sau một lần phát hành

Một release database nên có các bước rõ ràng sau khi migration kết thúc:

~~~text
Liquibase update hoàn tất
          |
          v
Xác minh DATABASECHANGELOG và trạng thái changeset
          |
          v
Kiểm tra schema, dữ liệu, quyền và dependency
          |
          v
Kiểm tra ứng dụng và chỉ số vận hành
          |
          v
Theo dõi trong cửa sổ observation
          |
          v
Thu thập log, snapshot, truy vấn và approval
          |
          v
Cập nhật release record / runbook
          |
          v
Bàn giao DBA, SRE, ứng dụng và on-call
          |
          v
Đóng release hoặc giữ trạng thái có ngoại lệ
~~~

Trình tự này giúp phát hiện những lỗi mà log của Liquibase không thể phản ánh, chẳng hạn ứng dụng không tương thích, role runtime thiếu quyền hoặc replication lag tăng sau khi tạo index.

**Không đóng release khi còn trạng thái chưa rõ.** Nếu migration chạy thành công nhưng postflight chưa hoàn tất, trạng thái phù hợp là đang xác minh hoặc cần xử lý tiếp, không phải đã bàn giao hoàn tất.

## 2. Phân biệt kết quả migration với trạng thái sẵn sàng vận hành

Có ít nhất bốn lớp kết quả cần theo dõi:

| Lớp | Câu hỏi | Bằng chứng |
|---|---|---|
| **Liquibase execution** | Changeset đã được Liquibase xử lý chưa? | Log, exit code, DATABASECHANGELOG |
| **Database state** | Schema và dữ liệu thực tế có đúng không? | Metadata DBMS, data assertions, snapshot/diff |
| **Application state** | Ứng dụng và job nền có dùng schema mới được không? | Smoke test, error rate, log ứng dụng |
| **Operational readiness** | Đội vận hành có thể giám sát và phục hồi không? | Dashboard, alert, backup/restore plan, runbook, handoff |

Các lớp này bổ sung cho nhau. Ví dụ DATABASECHANGELOG có bản ghi changeset tạo index, nhưng DBA đã xóa index sau đó; execution history vẫn đúng theo lịch sử nhưng database state không còn đúng. Hoặc schema đúng nhưng ứng dụng mới truy cập bằng role thiếu quyền, khiến application state thất bại.

Release chỉ được coi là sẵn sàng khi mọi lớp bắt buộc trong phạm vi đã đạt tiêu chí đã thống nhất.

## 3. Chốt danh tính release và target đã triển khai

Trước khi kiểm tra sau release, cần có một release manifest hoặc record chứa:

- Release ID và phiên bản ứng dụng.
- Commit/tag Git và artifact build đã phát hành.
- Commit hoặc checksum của changelog artifact.
- Liquibase version và JDBC driver version.
- DBMS, server version, database/catalog và schema.
- Danh sách tenant/database trong phạm vi.
- Contexts, labels và các tham số ảnh hưởng tập changeset.
- Thời điểm bắt đầu/kết thúc theo UTC.
- Job ID, execution ID, người vận hành và người phê duyệt.

Đừng dựa vào tên pipeline hoặc tên connection để kết luận target. Hãy xác minh database thực tế bằng truy vấn phù hợp DBMS.

Ví dụ PostgreSQL:

~~~sql
SELECT
    current_database() AS database_name,
    current_schema() AS current_schema,
    current_user AS connected_role,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    current_setting('server_version') AS server_version;
~~~

Đối chiếu kết quả với target trong release manifest. Nếu chạy qua proxy hoặc dịch vụ database managed, địa chỉ server có thể không giống hostname JDBC; dùng thêm thông tin định danh từ nền tảng hạ tầng.

**Nếu target identity không khớp, dừng mọi kết luận post-release.** Trước hết phải xác định migration đã chạy ở đâu và có ảnh hưởng tới môi trường nào.

## 4. Xác minh DATABASECHANGELOG sau phát hành

DATABASECHANGELOG là nguồn lịch sử cho biết Liquibase đã ghi nhận những changeset nào. Với PostgreSQL và metadata nằm trong schema public, có thể kiểm tra:

~~~sql
SELECT
    id,
    author,
    filename,
    exectype,
    md5sum,
    dateexecuted,
    orderexecuted,
    tag,
    deployment_id
FROM public.databasechangelog
ORDER BY orderexecuted;
~~~

Tên bảng, schema metadata và một số cột có thể được cấu hình hoặc khác theo phiên bản; điều chỉnh truy vấn theo cấu hình thực tế.

Đối với release cụ thể, xác nhận:

1. Mọi changeset bắt buộc đều có bản ghi.
2. ID, author và filename/logical path khớp changelog artifact đã phát hành.
3. Checksum không có sai khác ngoài chính sách đã phê duyệt.
4. EXECTYPE phù hợp với kết quả mong đợi; phân biệt EXECUTED, RERAN và MARK_RAN.
5. Không có changeset ngoài phạm vi bất ngờ được ghi nhận.
6. Những changeset chưa thuộc release vẫn pending như dự kiến.
7. Tag hoặc deployment metadata được ghi nhận đúng nếu quy trình sử dụng.

Không chỉ lọc theo ID nếu dự án có nhiều file dùng ID giống nhau. Định danh changeset liên quan cả author và đường dẫn logic.

Ví dụ kiểm tra một changeset:

~~~sql
SELECT
    id, author, filename, exectype, md5sum, dateexecuted
FROM public.databasechangelog
WHERE id = '060-add-invoice-status'
  AND author = 'billing-team';
~~~

Nếu không tìm thấy bản ghi, đừng chạy lại update ngay. Kiểm tra đúng database/schema, changelog root, contexts/labels, log lần chạy và khả năng statement đã thay đổi database nhưng chưa ghi lịch sử.

## 5. Kiểm tra DATABASECHANGELOGLOCK và tiến trình còn hoạt động

Liquibase dùng **DATABASECHANGELOGLOCK** để điều phối các lần cập nhật metadata/database trên cùng một phạm vi metadata. Sau phát hành, cần xác nhận không còn một tiến trình migration ngoài dự kiến đang giữ lock.

Ví dụ trên PostgreSQL khi metadata nằm trong public:

~~~sql
SELECT id, locked, lockgranted, lockedby
FROM public.databasechangeloglock;
~~~

Thông thường chỉ có một dòng lock. Nếu `locked = true`, hãy xác minh:

- Job Liquibase có còn chạy không?
- Session database nào đang giữ kết nối?
- Có DDL hoặc transaction đang thực thi không?
- Job bị kill hay mất kết nối sau khi statement đã commit?
- Có tiến trình khác đang sử dụng cùng metadata table không?

Không tự ý cập nhật `locked = false` hoặc xóa bảng lock chỉ để giải phóng pipeline. Nếu session còn chạy, việc xóa lock có thể cho phép một tiến trình khác chạy đồng thời. Chỉ dùng cơ chế release lock được Liquibase hỗ trợ sau khi xác minh tiến trình giữ lock đã kết thúc và database ở trạng thái an toàn.

## 6. Kiểm tra schema thực tế

Lịch sử changeset không bảo đảm object vẫn tồn tại hoặc giữ đúng định nghĩa. Sau release, xác minh các đối tượng liên quan bằng metadata DBMS.

Ví dụ kiểm tra cột PostgreSQL qua information_schema:

~~~sql
SELECT
    column_name,
    data_type,
    character_maximum_length,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'invoice'
ORDER BY ordinal_position;
~~~

Kiểm tra constraint:

~~~sql
SELECT
    conname,
    contype,
    convalidated
FROM pg_constraint
WHERE conrelid = 'public.invoice'::regclass;
~~~

Kiểm tra index:

~~~sql
SELECT
    idx.relname AS index_name,
    i.indisready,
    i.indisvalid
FROM pg_class AS idx
JOIN pg_index AS i ON i.indexrelid = idx.oid
WHERE idx.relnamespace = 'public'::regnamespace;
~~~

Các truy vấn này dành cho PostgreSQL; MySQL, SQL Server, Oracle và SQLite có catalog khác. Với mỗi changeset, chỉ kiểm tra những object có liên quan nhưng phải đủ thuộc tính để xác nhận mục tiêu, không chỉ kiểm tra tên object.

Ví dụ index tồn tại nhưng `indisvalid = false` vẫn chưa đạt. Constraint có tên đúng nhưng gắn sai cột hoặc chưa validate cũng chưa đạt.

## 7. Kiểm tra dữ liệu và hậu điều kiện nghiệp vụ

Migration dữ liệu có thể hoàn tất về mặt SQL nhưng chưa đạt kết quả nghiệp vụ. Mỗi changeset có tác động dữ liệu nên có **postcondition** được xác định trước.

Ví dụ sau backfill cột invoice.status:

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE status IS NULL) AS null_rows
FROM public.invoice;
~~~

Nếu yêu cầu là mọi invoice hiện hữu đều có status, kỳ vọng `null_rows = 0`. Cú pháp FILTER là đặc trưng PostgreSQL; DBMS khác có thể dùng SUM(CASE WHEN ... THEN 1 ELSE 0 END).

Các assertion khác có thể gồm:

- Không có khóa ngoại mồ côi.
- Không có giá trị trùng trước khi thêm UNIQUE.
- Số hàng được chuyển đổi khớp phạm vi dự kiến.
- Giá trị tiền tệ/timestamp không bị mất precision.
- Các bản ghi tham chiếu hoặc dữ liệu danh mục cần thiết đã tồn tại.
- Tổng số hàng và các tổng kiểm tra nghiệp vụ nằm trong khoảng mong đợi.

Đối với bảng lớn, không nhất thiết chạy một truy vấn COUNT toàn bảng trong giờ cao điểm. Có thể dùng batch/checkpoint, thống kê được kiểm chứng hoặc truy vấn có index phù hợp. Phương pháp kiểm tra phải đủ tin cậy và không tạo tải vượt ngưỡng.

Nếu data assertion FAIL, không đánh dấu release hoàn tất dù Liquibase update đã trả mã 0.

## 8. Xác minh quyền và dependency

Migration có thể tạo object đúng nhưng ứng dụng không truy cập được. Kiểm tra:

- Role runtime có quyền SELECT/INSERT/UPDATE/DELETE phù hợp.
- Quyền trên sequence, function, procedure và schema.
- Default privileges hoặc grants cần thiết cho object mới.
- View, trigger, function và stored procedure phụ thuộc cột/bảng vừa thay đổi.
- Job nền, báo cáo, ETL, CDC và consumer khác dùng schema đó.
- Các ứng dụng hoặc dịch vụ chia sẻ database có phiên bản tương thích.

Không dùng tài khoản migration để thử toàn bộ luồng ứng dụng rồi kết luận quyền runtime đúng. Migration role thường có quyền DDL rộng hơn runtime role; smoke test phải dùng đúng danh tính ứng dụng.

Với thay đổi phá hủy hoặc đổi tên cột, rà soát consumer theo dependency graph. Một ứng dụng ít được sử dụng hoặc job chạy theo lịch có thể chỉ phát hiện lỗi nhiều giờ sau khi release.

## 9. Theo dõi ứng dụng trong cửa sổ quan sát

Sau khi postflight database đạt, theo dõi ứng dụng trong một khoảng thời gian phù hợp với workload và mức độ rủi ro.

Các chỉ số thường cần:

| Nhóm | Chỉ số |
|---|---|
| Ứng dụng | Error rate, p95/p99 latency, timeout, throughput |
| Database | Connection count, active sessions, lock waits, deadlocks |
| Tài nguyên | CPU, memory, I/O, disk free, transaction log/WAL |
| Replication | Replica lag, apply delay, CDC backlog |
| Query | Slow query, execution plan, rows scanned, buffer/cache |
| Job nền | Queue depth, retry count, batch duration, failed jobs |
| Toàn vẹn | Constraint violation, data assertion, lỗi ghi/đọc |

So sánh với baseline trước release và SLO của dịch vụ. Một con số đơn lẻ không đủ; cần xem xu hướng và cửa sổ đo.

Ví dụ, index mới có thể làm truy vấn mục tiêu nhanh hơn nhưng tăng thời gian INSERT hoặc dung lượng disk. Thay đổi kiểu dữ liệu có thể không làm API lỗi ngay nhưng khiến một batch job chạy lâu hơn. Theo dõi cả tác động dự kiến và tác động phụ.

Nếu vượt ngưỡng dừng đã phê duyệt, tạm dừng rollout tiếp theo, điều tra và chọn phương án. Không chờ tới khi hết cửa sổ quan sát nếu đã có dấu hiệu mất dữ liệu hoặc lỗi nghiêm trọng.

## 10. Xử lý alert và sự cố sau release

Một quy trình incident nên thống nhất các bước:

1. Xác định release gần nhất và database/tenant bị ảnh hưởng.
2. Liên kết alert với changeset hoặc object thay đổi nếu có thể.
3. Kiểm tra ứng dụng, database session, lock và replication.
4. Đọc log Liquibase và DATABASECHANGELOG của đúng target.
5. So sánh schema thực tế với trạng thái trước/sau release.
6. Xác định lỗi do migration, ứng dụng, dữ liệu, hạ tầng hay thay đổi ngoài quy trình.
7. Dừng rollout hoặc traffic liên quan nếu blast radius còn mở rộng.
8. Chọn rollback ứng dụng, rollback database, forward-fix hoặc restore/PITR.
9. Kiểm tra hậu điều kiện sau phục hồi.
10. Ghi incident timeline, quyết định và hành động tiếp theo.

### Không tự động rollback chỉ vì có alert

Alert có thể xuất phát từ code, network hoặc workload không liên quan DDL. Rollback database có thể làm mất dữ liệu mới hoặc khiến code đang chạy không tương thích. Trước khi rollback, xác định quan hệ nhân quả, phạm vi dữ liệu và khả năng đảo ngược.

Nếu chưa rõ trạng thái database sau partial failure, chuyển sang **RECONCILIATION_REQUIRED**. Đọc lịch sử, object và dữ liệu thực tế trước khi retry hoặc rollback.

## 11. Chuẩn bị runbook phục hồi và rollback

Runbook sau phát hành cần mô tả cho từng migration quan trọng:

- Triệu chứng có thể gặp và cách nhận diện.
- Changeset ID/author/path liên quan.
- Database/schema/tenant trong phạm vi.
- Truy vấn kiểm tra trạng thái.
- Các lệnh Liquibase đã được xác minh theo version.
- SQL rollback dự kiến và tác động dữ liệu.
- Điều kiện không được rollback.
- Phương án forward-fix hoặc restore/PITR.
- Người có quyền phê duyệt và escalation path.
- Các postcondition phải chạy sau phục hồi.

Có thể preview rollback theo tag hoặc số changeset bằng các lệnh Liquibase tương ứng, nhưng cú pháp/options phụ thuộc phiên bản. Ví dụ minh họa:

~~~shell
liquibase rollback-sql --tag=release_2_4_0
~~~

Preview chỉ giúp review SQL dự kiến; nó không chứng minh rollback sẽ an toàn trên dữ liệu thật. Trước khi thực thi, kiểm tra changeset sau mốc, dữ liệu mới, dependency và tính tương thích ứng dụng.

Nếu migration đã xóa dữ liệu hoặc chuyển đổi một chiều, rollback SQL có thể không khôi phục giá trị ban đầu. Cần backup/PITR hoặc forward-fix được thiết kế riêng. Backup phải được kiểm tra khả năng restore, không chỉ xác nhận job backup báo thành công.

## 12. Backup, restore và bằng chứng phục hồi

Bàn giao phải nêu rõ:

- Backup gần nhất trước/sau release.
- Loại backup: full, incremental, snapshot, transaction log/WAL archive.
- Thời điểm và retention.
- RPO/RTO áp dụng.
- Người có quyền khởi chạy restore.
- Môi trường thử restore gần nhất.
- Các bước reconcile DATABASECHANGELOG sau restore/PITR.

PITR có thể đưa database về thời điểm trước migration, nhưng cũng có thể loại bỏ các giao dịch hợp lệ sau mốc phục hồi. Cần tính đến write freeze, capture dữ liệu phát sinh và quy trình replay nếu nghiệp vụ yêu cầu.

**Snapshot schema không thay thế backup.** Snapshot giúp so sánh cấu trúc; backup/PITR mới là cơ chế phục hồi dữ liệu theo khả năng của DBMS.

Sau restore, không mặc định DATABASECHANGELOG và schema đã khớp với release record trước đó. Kiểm tra cả hai, xác định changeset nào thực sự có hiệu lực tại thời điểm phục hồi và quyết định update/forward-fix tiếp theo.

## 13. Lưu bằng chứng triển khai và provenance

Bằng chứng sau release nên đủ để người khác tái dựng điều gì đã xảy ra mà không phải suy đoán.

Một gói evidence có thể gồm:

- Release ID, Git commit và artifact version.
- Changelog file/changeset IDs.
- Liquibase/JDBC/DBMS version.
- Target database/schema/tenant identity.
- Contexts, labels và tham số chạy.
- SQL preview đã review và approval.
- Log thực thi cùng execution/job ID.
- Truy vấn DATABASECHANGELOG sau deploy.
- Kết quả schema/data postflight.
- Smoke test và metrics trong observation window.
- Snapshot trước/sau nếu chính sách yêu cầu.
- Backup reference và kết quả kiểm tra restore.
- Ngoại lệ, sự cố và quyết định xử lý.

Ví dụ cấu trúc release record:

~~~text
RELEASE_ID: billing-2.4.1
APPLICATION_ARTIFACT: billing-service:2.4.1
CHANGELOG_COMMIT: <reviewed-commit>
LIQUIBASE_VERSION: <pinned-version>
DBMS: PostgreSQL <server-version>
TARGET:
  database: customer_db
  schema: public
  environment: production

MIGRATION:
  changesets:
    - billing-team:060-add-invoice-status
    - billing-team:061-create-invoice-status-index
  execution_id: <pipeline-job-id>
  result: SUCCEEDED

POSTFLIGHT:
  history: PASS
  schema: PASS
  data_assertions: PASS
  application_smoke: PASS
  observation: PASS

RECOVERY:
  backup_reference: <backup-id>
  runbook: <runbook-reference>
  rollback_review: <approval-reference>

HANDOFF:
  owner_team: database-operations
  on_call: <rotation-reference>
  open_items: NONE
~~~

Đây là mẫu nội dung minh họa. Không ghi password, token, chuỗi kết nối chứa secret, dữ liệu khách hàng hoặc thông tin cá nhân vào release record. Artifact có thể tiết lộ topology và cấu trúc nội bộ, vì vậy cần phân quyền lưu trữ.

## 14. Bàn giao giữa các nhóm

Một lần bàn giao tốt nêu rõ ai tiếp nhận trách nhiệm nào:

| Nhóm | Nội dung cần nhận |
|---|---|
| Development | Changeset, lý do thay đổi, dependency và giới hạn tương thích |
| DBA | SQL đã chạy, lock/resource impact, schema/data state, backup/restore |
| SRE/Platform | Dashboard, alert, deployment job, rollback/escalation |
| Application operations | Phiên bản code, smoke test, quyền runtime, luồng nghiệp vụ cần theo dõi |
| Security | Credential/role changes, quyền mới, audit và secret rotation nếu có |
| On-call | Triệu chứng, truy vấn kiểm tra, người liên hệ và quyết định khi vượt ngưỡng |
| Release manager | Release status, approval, evidence và ngoại lệ còn mở |

Không bàn giao bằng cách gửi toàn bộ log mà không có tóm tắt. Hãy nêu những thay đổi quan trọng, kết quả kiểm tra, rủi ro còn lại và đường dẫn tới evidence/runbook được phân quyền phù hợp.

### Nội dung bàn giao tối thiểu

1. Release nào, commit nào, đã triển khai lúc nào.
2. Database/schema/tenant nào đã được cập nhật.
3. Changeset nào đã chạy và trạng thái nào được xác nhận.
4. Những kiểm tra schema, data và ứng dụng đã thực hiện.
5. Dashboard/alert nào cần theo dõi và trong bao lâu.
6. Những thay đổi có rủi ro hoặc giới hạn rollback.
7. Backup/PITR và runbook phục hồi ở đâu.
8. Ngoại lệ còn mở, owner và thời hạn.
9. Ai là người escalation và ai có quyền quyết định hành động khẩn cấp.

## 15. Handoff checklist và mẫu thông báo

Một checklist thực tế:

~~~text
[ ] Release ID / commit / artifact đã ghi
[ ] Target DB/schema/tenant đã xác nhận
[ ] Liquibase và DBMS version đã ghi
[ ] DATABASECHANGELOG đã đối chiếu
[ ] DATABASECHANGELOGLOCK không còn job ngoài dự kiến
[ ] Schema postflight đạt
[ ] Data assertions đạt
[ ] Runtime permissions và dependency đạt
[ ] Application smoke tests đạt
[ ] Metrics trong observation window đạt
[ ] Backup/restore reference được ghi
[ ] Runbook rollback/forward-fix đã review
[ ] Evidence được lưu và có quyền truy cập
[ ] On-call đã nhận rủi ro và escalation path
[ ] Ngoại lệ có owner và thời hạn
~~~

Mẫu thông báo bàn giao:

~~~text
Release: <release-id>
Environment: <environment>
Target: <database>/<schema>
Changesets: <id/author list>
Deployment window: <start UTC> - <end UTC>
Result: COMPLETED / PARTIAL / BLOCKED

Verified:
- Liquibase history: <PASS/FAIL>
- Schema and data: <PASS/FAIL>
- Application smoke: <PASS/FAIL>
- Operational observation: <PASS/FAIL>

Watch items:
- <metric or behavior>
- <threshold and observation window>

Recovery:
- Backup/PITR: <reference>
- Runbook: <reference>
- Rollback/forward-fix constraints: <summary>

Owner / on-call: <team or rotation>
Open issues: <none or list>
Next review: <time>
~~~

Chỉ dùng trạng thái COMPLETED khi mọi điều kiện bắt buộc đã đạt. Nếu một tenant hoặc môi trường bị hoãn có phê duyệt, báo cáo là PARTIAL hoặc COMPLETED WITH APPROVED EXCEPTIONS theo quy ước tổ chức; không mô tả sai rằng toàn bộ phạm vi đã thành công.

## 16. Vận hành nhiều môi trường và nhiều tenant

Với database-per-tenant hoặc schema-per-tenant, phải ghi nhận trạng thái sau phát hành theo từng đơn vị. Không dùng một DATABASECHANGELOG chung để kết luận mọi tenant đã chạy.

Ví dụ bảng theo dõi:

| Tenant | Changeset release | Schema postflight | App smoke | Trạng thái |
|---|---|---|---|---|
| tenant_001 | PASS | PASS | PASS | SUCCEEDED |
| tenant_002 | PASS | FAIL | Chưa chạy | BLOCKED |
| tenant_003 | Chưa chạy | Chưa chạy | Chưa chạy | QUEUED |

Bộ điều phối có thể rollout theo canary/wave. Khi tenant_002 thất bại, cần dừng wave tiếp theo theo chính sách, reconcile trạng thái tenant đó và đánh giá blast radius trước khi tiếp tục các tenant khác.

Với shared schema/shared tables, DDL thường chỉ chạy một lần trên schema vật lý chung. Các data job theo tenant vẫn cần trạng thái và hậu kiểm riêng nếu chúng xử lý dữ liệu từng tenant.

Bàn giao phải chỉ rõ:

- Tổng tenant/database trong scope.
- Số đã thành công, thất bại, pending, blocked hoặc cần reconcile.
- Tenant được miễn/hoãn và lý do.
- Release version từng tenant đã xác minh.
- Điều kiện để mở wave tiếp theo.

## 17. Vận hành Spring Boot sau migration

Nếu Spring Boot tự chạy Liquibase khi khởi động, cần xác định rõ hành vi này trong mô hình vận hành:

- Ứng dụng hay CI/CD là migration owner?
- Có bao nhiêu replica có thể khởi động cùng lúc?
- Profile production có bật `spring.liquibase.enabled` không?
- Changelog root và datasource nào được sử dụng?
- Runtime role có quyền DDL hay chỉ quyền nghiệp vụ?
- Startup readiness có chờ migration hoàn tất không?
- Có cách ngăn application traffic vào instance khi schema chưa sẵn sàng không?

Nếu pipeline chạy Liquibase riêng, thường nên cấu hình ứng dụng không tự chạy lại migration ngoài kế hoạch, ví dụ profile runtime:

~~~yaml
spring:
  liquibase:
    enabled: false
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Đây chỉ là cấu hình minh họa cho mô hình CI/CD sở hữu migration. Nếu ứng dụng được thiết kế để chạy Liquibase lúc startup, giữ cấu hình phù hợp và điều phối replica theo đúng kiến trúc. Không để cả pipeline lẫn ứng dụng tự ý sở hữu migration mà thiếu coordination.

Sau release, kiểm tra startup log, schema validation, datasource, role runtime và smoke test. Một migration thành công không đảm bảo mọi instance cũ/mới đều tương thích.

## 18. Quản lý changeset, checksum và hotfix sau release

Sau khi phát hành, xem changeset đã chạy là một phần của lịch sử bất biến. Nếu phát hiện lỗi:

- Không sửa nội dung changeset đã triển khai chỉ để sửa schema.
- Tạo changeset mới forward-fix.
- Giữ id/author/path ổn định khi backport cùng một thay đổi.
- Kiểm tra checksum và DATABASECHANGELOG ở từng môi trường.
- Ghi liên kết giữa incident, hotfix commit và release record.
- Cập nhật runbook và postflight assertions.

Nếu DBA phải sửa trực tiếp production trong tình huống khẩn cấp, cần ghi lại SQL, thời điểm, người thực hiện và lý do; sau đó tạo migration hoặc quy trình baseline/reconcile phù hợp để đưa thay đổi vào lịch sử mã nguồn. Không để hotfix thủ công trở thành trạng thái lâu dài không được quản lý.

Checksum giúp phát hiện thay đổi định nghĩa changeset, nhưng không chứng minh schema thực tế chưa drift. Sau hotfix, kiểm tra cả DATABASECHANGELOG và metadata object.

## 19. Xử lý trạng thái không đồng nhất giữa log, history và schema

Một số tình huống thường gặp:

| Quan sát | Khả năng | Hành động |
|---|---|---|
| Log báo update thành công, changeset có trong DBCL, object đúng | Migration có thể đạt | Chạy data/app/operations postflight và đóng khi đủ |
| Log báo lỗi, changeset chưa có, object cũng chưa đổi | Có thể lỗi trước thực thi | Sửa nguyên nhân, preflight lại rồi retry |
| Log báo lỗi, object đã xuất hiện, DBCL chưa có | Partial/non-transactional execution | RECONCILIATION_REQUIRED; xác minh object và quyết định cleanup/retry |
| DBCL có changeset nhưng object thiếu | Drift sau migration hoặc thao tác ngoài Liquibase | Điều tra log/DBA change; tạo forward-fix |
| DBCL checksum mismatch | Changelog đã thay đổi hoặc identity khác | So sánh artifact/path/version; không clear-checksums tùy tiện |
| DBCL lock còn true nhưng job không rõ | Có thể process còn chạy hoặc lock stale | Kiểm tra session và worker trước khi release lock |
| Schema đúng nhưng app lỗi | Permission, mapping, code hoặc dependency | Kiểm tra runtime role và ứng dụng |
| Một số tenant đạt, một số tenant lỗi | Rollout chưa đồng nhất | Báo partial, reconcile từng tenant |

Không ép mọi nguồn dữ liệu về cùng trạng thái bằng cách sửa tay DATABASECHANGELOG hoặc xóa object. Trước hết xác định trạng thái thật và lịch sử thao tác; sau đó chọn hành động được review.

## 20. Đóng release và lưu tri thức vận hành

Release có thể được đóng khi:

### Điều kiện kỹ thuật

- Các changeset bắt buộc đã được xác minh trong DATABASECHANGELOG.
- Checksum và định danh changeset khớp artifact đã phát hành.
- Schema và data assertions đạt.
- Không có partial failure hoặc lock chưa giải quyết.
- Ứng dụng và các dependency quan trọng hoạt động.

### Điều kiện vận hành

- Metrics và alert trong ngưỡng trong cửa sổ quan sát.
- Backup/restore plan có tham chiếu rõ.
- Runbook và escalation path sẵn sàng.
- Các tenant/database trong scope đã có trạng thái rõ.
- Ngoại lệ có owner, lý do và thời hạn.
- On-call hoặc đội tiếp nhận đã xác nhận bàn giao.

### Điều kiện quản trị

- Release record và evidence được lưu.
- Approval và người thực hiện có thể truy vết.
- Hotfix/backport hoặc follow-up được ghi thành công việc có owner.
- Thay đổi thủ công được đưa vào kế hoạch reconcile.
- Tài liệu vận hành được cập nhật.

Sau release, ghi nhận bài học: thời gian thực tế so với ước tính, lock/resource impact, truy vấn postflight hiệu quả, alert còn thiếu, bước runbook khó thực hiện và thay đổi cần chuẩn hóa. Những thông tin này giúp release tiếp theo dự đoán tốt hơn.

## 21. Ví dụ quy trình bàn giao sau release thêm index

Giả sử release billing thêm index `idx_invoice_status_created` trên PostgreSQL production.

**Trước khi bàn giao:**

1. Ghi release ID, commit, Liquibase version và target database/schema.
2. Xác minh changeset tạo index có trong DATABASECHANGELOG.
3. Kiểm tra index trong pg_index, xác nhận `indisready` và `indisvalid` đều true.
4. Xác minh định nghĩa index đúng cột status và created_at.
5. Theo dõi query plan hoặc metric truy vấn mục tiêu để xác nhận hiệu quả.
6. Theo dõi insert/update latency, disk usage, replication lag.
7. Chạy smoke test API và job nền sử dụng invoice.
8. Lưu SQL preview, log, query results và dashboard window.

**Bàn giao:**

- DBA nhận tên index, schema, changeset identity và truy vấn xác minh.
- SRE nhận dashboard, alert và ngưỡng theo dõi.
- Đội ứng dụng nhận kết quả smoke test và thay đổi hiệu năng dự kiến.
- On-call nhận runbook xử lý index invalid, query chậm hoặc replication lag.
- Release manager nhận trạng thái completion và evidence.

Nếu index có tên nhưng `indisvalid = false`, không đánh dấu hoàn tất. Ghi trạng thái BLOCKED/RECONCILIATION_REQUIRED, điều tra lần tạo index và chỉ retry sau khi xử lý object không hợp lệ.

## 22. Các lỗi bàn giao thường gặp

| Lỗi | Hệ quả | Cách phòng tránh |
|---|---|---|
| Chỉ gửi thông báo deploy thành công | Đội vận hành không biết kiểm tra gì | Gửi release record và postflight evidence |
| Không ghi target database/schema | Điều tra nhầm môi trường | Gắn target identity vào log và handoff |
| Không lưu changeset identity | Khó liên kết sự cố với migration | Ghi id/author/path và changelog commit |
| Không nêu ngoại lệ | Người nhận tưởng mọi tenant đã thành công | Báo partial/blocked rõ ràng |
| Không bàn giao rollback constraint | On-call chọn hành động nguy hiểm | Ghi rollback/forward-fix/restore limitations |
| Không kiểm tra backup restore | Không biết khả năng phục hồi thật | Lưu restore test và RPO/RTO |
| Không bàn giao dashboard/alert | Phát hiện lỗi muộn | Ghi metric, threshold và observation window |
| Log chứa secret | Lộ credential | Redact log và dùng secret manager |
| Chỉ nhìn DATABASECHANGELOG | Bỏ sót schema drift | Đối chiếu metadata object thực tế |
| Không có owner follow-up | Ngoại lệ tồn tại vô thời hạn | Ghi owner và due date |

## 23. Checklist vận hành và bàn giao sau phát hành

**Danh tính và lịch sử**

- [ ] Release ID, commit, artifact và Liquibase version đã ghi.
- [ ] Database/schema/tenant và DBMS/version đã xác nhận.
- [ ] Changeset ID/author/filename/logical path đã đối chiếu.
- [ ] DATABASECHANGELOG/checksum/EXECTYPE khớp mong đợi.
- [ ] DATABASECHANGELOGLOCK không còn tiến trình ngoài dự kiến.

**Database và ứng dụng**

- [ ] Schema postflight đạt.
- [ ] Data assertions đạt.
- [ ] Index/constraint/sequence và dependency quan trọng hợp lệ.
- [ ] Runtime role có quyền đúng.
- [ ] Smoke test và job nền đạt.
- [ ] Metrics/SLO trong cửa sổ quan sát đạt.

**Phục hồi và bằng chứng**

- [ ] Backup/PITR reference và RPO/RTO được ghi.
- [ ] Rollback/forward-fix/restore runbook đã review.
- [ ] SQL preview, execution log và approval được lưu.
- [ ] Snapshot/query results được lưu khi policy yêu cầu.
- [ ] Không còn partial failure hoặc checksum conflict chưa giải quyết.

**Bàn giao**

- [ ] DBA/SRE/application/on-call nhận đúng phần trách nhiệm.
- [ ] Dashboard, alert, threshold và observation window đã chỉ rõ.
- [ ] Ngoại lệ/tenant chưa hoàn tất có owner và thời hạn.
- [ ] Escalation path và người có quyền quyết định được ghi.
- [ ] Release status phản ánh đúng COMPLETED, PARTIAL hoặc BLOCKED.
- [ ] Follow-up và bài học vận hành đã được tạo/ghi nhận.

Với **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, vận hành sau phát hành cần kết hợp lịch sử changeset, trạng thái schema/data, sức khỏe ứng dụng và bằng chứng phục hồi. Bàn giao chỉ hoàn tất khi người tiếp nhận biết chính xác release nào đã chạy ở đâu, những gì đã được xác minh, điều gì còn cần theo dõi và cách xử lý khi vượt ngưỡng. Một quy trình post-release rõ ràng giúp Liquibase trở thành một phần có thể truy vết của vận hành database, thay vì kết thúc ở dòng log báo update thành công.
