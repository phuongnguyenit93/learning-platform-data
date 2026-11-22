# Kiểm thử migration trên dữ liệu và schema phiên bản trước

Database migration thay đổi cấu trúc hoặc dữ liệu để đưa một database từ phiên bản ứng dụng/schema hiện tại sang phiên bản mới. Một migration có thể thêm hoặc đổi column, tạo index, thay constraint, chuyển đổi dữ liệu, cập nhật extension, hoặc loại bỏ cấu trúc cũ. Những thay đổi này thường đơn giản trên database trống, nhưng có thể thất bại hoặc gây gián đoạn khi chạy trên dữ liệu production đã tích lũy nhiều năm, có NULL, duplicates, giá trị bất thường, quan hệ phức tạp, transactions đang mở và workload đồng thời.

Kiểm thử migration phải bắt đầu từ **schema và dữ liệu thực tế của phiên bản trước**, sau đó chạy đúng chuỗi migration mà production sẽ thực hiện. Mục tiêu là chứng minh database có thể chuyển từ trạng thái cũ sang trạng thái mới, dữ liệu được bảo toàn hoặc biến đổi đúng, ứng dụng tương thích trong quá trình chuyển đổi, và hiệu năng/availability vẫn nằm trong giới hạn chấp nhận được. Chỉ kiểm thử migration trên database mới tạo không thể phát hiện các lỗi phụ thuộc vào data shape, historical values, table size, indexes, constraints hoặc transaction history.

Bài học thuộc chương **Kiểm thử** của module **Database Engine Relational PostgreSQL**. Nội dung trình bày cách tạo test baseline từ schema/data phiên bản cũ, chuẩn bị dataset đại diện, chạy migration rehearsal, kiểm chứng schema và data invariants, đo lock/performance, kiểm thử rollback/recovery và tích hợp migration tests vào CI/CD.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao phải test migration trên schema và dữ liệu phiên bản trước.
- Phân biệt schema baseline, data snapshot và migration target.
- Tạo bản sao test từ backup hoặc snapshot an toàn.
- Chuẩn bị dataset đại diện, gồm NULL, duplicates, skew, boundary values và historical records.
- Kiểm tra schema drift giữa các môi trường.
- Chạy toàn bộ migration chain theo đúng thứ tự production.
- Kiểm thử DDL, data backfill, constraints, indexes và extension changes.
- Xác minh dữ liệu trước/sau bằng counts, checksums và business invariants.
- Đo lock duration, query impact, WAL, disk growth và replication lag.
- Kiểm tra tương thích giữa application versions trong expand-and-contract.
- Xây dựng rollback, restore và forward-fix strategy.
- Tự động hóa migration rehearsal trong CI/CD và lưu evidence.

## 2. Vì sao migration phải chạy trên dữ liệu phiên bản trước?

Migration được thiết kế để biến đổi một trạng thái đã tồn tại. Các giả định đúng trên database rỗng có thể sai trên database cũ.

### 2.1. Historical data

Dữ liệu production chứa records từ nhiều phiên bản ứng dụng, quy tắc nghiệp vụ và định dạng cũ. Một column có thể chứa giá trị mà code hiện tại không còn tạo ra nhưng migration vẫn phải xử lý.

### 2.2. NULL và dữ liệu thiếu

Một migration thêm NOT NULL hoặc chuyển đổi giá trị có thể thất bại vì rows cũ có NULL. Test fixture mới thường chỉ chứa dữ liệu hợp lệ theo model hiện tại.

### 2.3. Duplicate và uniqueness

Tạo unique index/constraint có thể fail nếu dữ liệu lịch sử có duplicates. Những duplicates này có thể xuất hiện do bug cũ, import hoặc concurrency race.

### 2.4. Quy mô và phân phối

Migration chạy nhanh trên vài trăm rows nhưng có thể lock table hoặc tạo WAL lớn trên hàng trăm triệu rows. Data skew cũng ảnh hưởng query plans và backfill duration.

### 2.5. Dependencies và live workload

Foreign keys, views, triggers, functions, prepared statements và transactions đang mở có thể ảnh hưởng migration. Test trên prior-version database giúp tái hiện dependencies thật hơn.

## 3. Các trạng thái cần kiểm thử

Một migration test có thể mô hình hóa database như chuỗi trạng thái có thể tái hiện.

~~~text
Prior application + schema + data (N)
                  |
                  v
          Pre-migration checks
                  |
                  v
          Migration sequence
                  |
                  v
       Target schema + transformed data (N+1)
                  |
                  v
      Validation + application smoke tests
                  |
                  v
       Performance / recovery acceptance
~~~

### 3.1. Source state

Source state là schema/data phiên bản trước, tương ứng với production ngay trước migration. Ghi rõ PostgreSQL major/minor, application release và migration version hiện tại.

### 3.2. Intermediate state

Nếu migration có nhiều bước hoặc nhiều deployment phases, lưu trạng thái sau từng bước quan trọng. Điều này giúp xác định chính xác bước gây lỗi.

### 3.3. Target state

Target state gồm schema version mới, dữ liệu đã chuyển đổi, indexes/constraints hợp lệ, privileges và objects liên quan.

### 3.4. Runtime state

Migration có thể hoàn tất về mặt DDL nhưng application vẫn lỗi do query behavior, defaults, permissions hoặc background jobs. Test runtime behavior sau chuyển đổi.

### 3.5. Recovery state

Xác định trạng thái có thể khôi phục khi migration fail: transaction rollback, migration-specific compensation, restore snapshot hoặc forward fix.

## 4. Schema baseline phiên bản trước

Baseline phải mô tả schema thật trước khi chạy migration.

### 4.1. DDL inventory

Lưu CREATE TABLE, indexes, constraints, sequences, views, materialized views, functions, triggers, types, schemas và grants.

### 4.2. Migration version marker

Nếu ứng dụng dùng migration history table, ghi version hiện tại, applied timestamps và checksums. Không tự sửa history table để làm cho test pass.

### 4.3. Object ownership

Lưu owner, grants, default privileges và role memberships cần thiết. Migration chạy dưới role khác có thể thất bại dù schema giống nhau.

### 4.4. Extension inventory

Ghi tên/version extensions và dependencies. Target environment cần package/shared libraries phù hợp trước khi chạy migration phụ thuộc chúng.

### 4.5. Schema diff baseline

So sánh DDL của test snapshot với schema source được quản lý trong repository. Nếu có drift, ghi lại trước khi chạy migration để tránh nhầm lỗi cũ với lỗi mới.

## 5. Data baseline phiên bản trước

Data baseline cần đủ để tái hiện các điều kiện mà migration sẽ gặp.

### 5.1. Table row counts

Ghi counts hoặc estimates cho các tables quan trọng, theo schema/table và partition. Counts là baseline để đối chiếu sau backfill.

### 5.2. Distribution profiles

Ghi NULL fraction, distinct values, min/max, common values, date ranges và phân phối theo tenant/status/type.

### 5.3. Referential relationships

Ghi số rows có/không có parent, orphan candidates và quan hệ nhiều-nhiều. Foreign key migration có thể thất bại nếu historical rows vi phạm.

### 5.4. Data quality anomalies

Ghi nhận duplicates, malformed strings, invalid enum values, out-of-range numbers, invalid timestamps và legacy sentinel values.

### 5.5. Sensitive data handling

Production snapshot có thể chứa personal/customer/financial data. Dùng sanitization hoặc synthetic replacement theo policy, giữ lại cấu trúc phân phối cần thiết và kiểm soát quyền truy cập.

## 6. Chọn nguồn tạo test database

Có nhiều cách tạo source database cho migration rehearsal.

### 6.1. Logical backup

pg_dump/pg_restore tạo database clone ở mức logical. Cách này phù hợp khi cần portability và chọn lọc schemas/tables, nhưng thời gian dump/restore có thể dài và physical layout không giống production.

### 6.2. Physical backup

Base backup hoặc storage snapshot tạo bản sao physical của cluster theo quy trình PostgreSQL-aware. Cần đảm bảo consistency, WAL requirements và compatible PostgreSQL major version.

### 6.3. Storage snapshots

Snapshot volume có thể nhanh, nhưng cần đảm bảo database được snapshot theo phương thức consistent/crash-recovery-aware và có WAL đủ để phục hồi.

### 6.4. Sanitized clone

Có thể restore production backup rồi mask/tokenize sensitive fields trong isolated environment. Kiểm tra sanitization không phá uniqueness, relationships hoặc distribution cần cho migration test.

### 6.5. Synthetic data

Synthetic data hữu ích khi không thể dùng production snapshot. Phải tạo được volume, skew, historical edge cases và referential patterns tương đương; vài rows mẫu không đại diện cho production migration.

## 7. Môi trường kiểm thử tương đồng production

Migration behavior phụ thuộc PostgreSQL version, configuration, hardware, storage và workload.

### 7.1. PostgreSQL version

Dùng cùng major/minor release hoặc ghi rõ khác biệt. DDL syntax, catalog behavior, locking và extension compatibility có thể thay đổi theo version.

### 7.2. Configuration

So sánh max_connections, work_mem, maintenance_work_mem, shared_buffers, autovacuum, WAL, checkpoint và timeout settings liên quan.

### 7.3. Hardware/storage

CPU, RAM, disk throughput/latency và filesystem ảnh hưởng migration duration. Một VM nhỏ có thể test correctness nhưng không dùng để dự đoán production duration.

### 7.4. Extensions và collation

Cài đúng extension versions, locales/collations và OS libraries cần thiết. Nếu khác, ghi rõ các tests không thể đại diện.

### 7.5. Network và topology

Nếu migration liên quan replication, FDW, logical subscribers hoặc remote services, dựng topology tương ứng và test network/authentication behavior.

## 8. Dataset đại diện và edge cases

Một dataset hữu ích phải chứa cả dữ liệu bình thường lẫn các trường hợp hiếm có thể làm migration fail.

| Nhóm dữ liệu | Ví dụ cần có | Rủi ro migration |
|---|---|---|
| NULL | Optional fields, missing dates | NOT NULL, casts |
| Duplicates | Same natural key | UNIQUE constraint/index |
| Boundary | Min/max, empty string, zero | Type/range conversion |
| Historical | Old enum/status values | CASE mapping |
| Skew | One tenant dominates | Backfill performance |
| Large values | Long text, large JSON | Memory/WAL/TOAST |
| Orphans | Missing parent candidates | Foreign key |
| Time data | DST/time zone boundaries | Timestamp conversion |
| Unicode | Accents, combining chars | Collation/encoding |
| Soft deleted | Archived/inactive rows | Filtered backfill |

### 8.1. NULL distributions

Tạo cả rows có NULL và non-NULL ở columns sẽ được đổi nullability/default.

### 8.2. Duplicate keys

Cố ý tạo duplicate natural keys để kiểm tra bước deduplication trước unique constraint.

### 8.3. Legacy values

Giữ các status/type codes cũ mà application mới không còn tạo. Migration cần map, preserve hoặc reject theo business rule rõ ràng.

### 8.4. Large objects và TOAST

Có records chứa text/JSON/binary lớn để kiểm tra rewrite, copy và WAL volume.

### 8.5. Boundary dates và numbers

Kiểm tra leap day, timezone offset, negative/zero/maximum values, decimal precision và values ngoài domain dự kiến.

## 9. Snapshot consistency và repeatability

Một test chỉ có giá trị so sánh khi source state được xác định và tái tạo.

### 9.1. Snapshot identifier

Ghi backup ID, timestamp, database identifier, source release và migration version. Với physical backup, lưu timeline/LSN metadata phù hợp.

### 9.2. Quiesce hoặc consistent snapshot

Chọn cách tạo snapshot đảm bảo data/schema ở trạng thái nhất quán. Nếu application còn writes, dùng backup mechanism bảo đảm snapshot consistency.

### 9.3. Immutable source artifact

Giữ bản backup/snapshot gốc read-only hoặc protected. Tạo working clone riêng cho mỗi lần rehearsal.

### 9.4. Repeat test

Chạy migration từ cùng source snapshot để so sánh duration, output và transformed data. Nếu mỗi lần dùng data khác, xác định rõ khác biệt.

### 9.5. No hidden manual edits

Mọi seed, sanitization và setup changes phải được script hóa/version control. Ghi lại thao tác thủ công nếu không thể tự động hóa.


## 10. Kiểm tra schema trước migration

Trước khi chạy migration, xác nhận clone thật sự ở source version mà migration mong đợi.

### 10.1. Migration history

Đọc bảng migration history và xác định version cuối cùng đã apply. Kiểm tra migration checksums nếu framework hỗ trợ.

### 10.2. Required objects

Xác nhận tables, columns, indexes, constraints, functions và extensions mà migration sẽ tham chiếu đang tồn tại.

### 10.3. Unexpected objects

Tìm objects thủ công hoặc drift ngoài source control. Một index trùng tên hoặc column đã được tạo trước có thể khiến migration fail.

### 10.4. Ownership và privileges

Chạy preflight bằng đúng deployment role. Kiểm tra CREATE/ALTER privileges, schema ownership và quyền trên sequences/functions.

### 10.5. Baseline query behavior

Lưu EXPLAIN plans và runtime của các queries liên quan trước migration. Sau migration, có thể cần phân biệt schema correctness với plan/performance changes.

## 11. Phân loại migration

Mỗi migration có risk profile khác nhau. Phân loại giúp chọn test cases và recovery strategy.

### 11.1. Additive DDL

Thêm table, nullable column, index hoặc function thường ít destructive hơn, nhưng vẫn có thể lock catalog/table và ảnh hưởng writes.

### 11.2. Destructive DDL

Drop/rename columns, drop tables, narrow data types và remove constraints có thể phá application compatibility hoặc làm mất dữ liệu.

### 11.3. Data migration

Backfill, normalization, split/merge records, convert units và remap codes cần business invariants cùng chiến lược xử lý partial progress.

### 11.4. Constraint migration

Thêm NOT NULL, CHECK, UNIQUE hoặc foreign keys cần kiểm tra toàn bộ existing rows và lock/validation behavior.

### 11.5. Operational migration

Extension updates, collation rebuild, partition reorganization và role/privilege changes cần environment-specific prerequisites.

## 12. Expand-and-contract migration

Expand-and-contract cho phép schema cũ và mới cùng tồn tại trong giai đoạn deploy.

~~~text
Old schema + old app
        |
        v
Expand: add compatible new objects
        |
        v
App supports old + new schema
        |
        v
Backfill and validate
        |
        v
Switch reads/writes to new shape
        |
        v
Contract: remove old objects later
~~~

### 12.1. Expand

Thêm columns/tables/indexes mới theo cách không phá code phiên bản cũ. Tránh drop/rename ngay trong bước đầu.

### 12.2. Compatibility release

Deploy application có thể đọc/ghi cả hai schema shapes hoặc thực hiện dual-write có kiểm soát.

### 12.3. Backfill

Chuyển historical rows theo batches, checkpoint progress và monitor locks/WAL/replication.

### 12.4. Cutover

Sau khi dữ liệu mới được validate, chuyển read path/write path sang cấu trúc mới. Theo dõi mismatch trong giai đoạn quan sát.

### 12.5. Contract

Chỉ drop legacy columns/tables sau khi không còn application instances/jobs sử dụng chúng và rollback window đã kết thúc.

## 13. Migration framework và version ordering

Dùng một migration framework có lịch sử/versioning rõ ràng để production và test chạy cùng chuỗi.

### 13.1. Versioned migrations

Mỗi migration có identifier/version duy nhất và được áp dụng theo thứ tự xác định. Tránh sửa nội dung migration đã được apply trên production.

### 13.2. Migration history table

Framework thường lưu migration version, checksum, execution time và trạng thái. Đây là evidence về những scripts đã chạy.

### 13.3. Repeatable migrations

Một số frameworks hỗ trợ scripts repeatable chạy lại khi checksum thay đổi. Chỉ dùng cho objects được thiết kế idempotent và hiểu semantics của framework.

### 13.4. Transaction mode

Kiểm tra framework chạy mỗi migration trong transaction, một transaction lớn hay autocommit. Các commands như CREATE INDEX CONCURRENTLY không được chạy trong transaction block.

### 13.5. Production command parity

Dùng cùng binary/tool version, configuration, environment variables, role và command flags như deployment. Chạy SQL thủ công khác quy trình production có thể bỏ sót lỗi orchestration.

## 14. Chạy migration trên clone từ đầu tới cuối

Rehearsal phải dùng đúng chuỗi migrations từ source version tới target.

### 14.1. Restore source clone

Khôi phục snapshot/schema/data phiên bản trước vào database isolated. Kiểm tra application release và migration marker.

### 14.2. Chạy preflight

Kiểm tra disk headroom, locks, active transactions, required extensions, schema drift và privileges.

### 14.3. Chạy migration runner

Thực hiện cùng command, role, connection settings và sequence như production. Capture stdout/stderr, exit code và server logs.

### 14.4. Không skip migration cũ

Nếu production sẽ chạy từ version N tới N+5, test chain đầy đủ từ N. Chỉ test migration cuối trên schema đã được dựng bằng tay có thể bỏ sót assumptions ở bước trung gian.

### 14.5. Record every phase

Ghi start/end time, migration identifier, affected relations, rows processed, lock waits và result. Khi fail, giữ clone và logs để điều tra.

## 15. Transaction boundaries và atomicity

Một migration có thể gồm nhiều DDL/data statements. Transaction boundary quyết định rollback behavior.

### 15.1. Transactional migration

Nếu toàn bộ migration chạy trong một transaction, lỗi có thể rollback changes của transaction. Điều này không đảm bảo mọi side effects ngoài database cũng được rollback.

### 15.2. Non-transactional commands

Một số commands không được chạy trong transaction block, ví dụ CREATE INDEX CONCURRENTLY và VACUUM. Framework cần hỗ trợ migration non-transactional riêng.

### 15.3. Long transaction cost

Transaction migration lớn có thể giữ locks/snapshots lâu, làm autovacuum bị cản, tăng bloat và giữ WAL/resources.

### 15.4. Partial progress

Nếu backfill chia batches và mỗi batch commit riêng, failure có thể để lại một phần dữ liệu đã chuyển. Migration cần checkpoint/resume semantics.

### 15.5. External side effects

Migration gọi external service, gửi message hoặc sửa file không tự được PostgreSQL rollback. Tốt nhất tách side effects ra workflow có idempotency/outbox.

## 16. DDL lock testing

DDL có thể chờ lock lâu dù câu lệnh chỉ thay đổi metadata.

### 16.1. Lock mode

Tìm lock mode mà command cần và xác định queries/transactions nào có thể block nó. ALTER TABLE thường cần lock mạnh ở một số bước.

### 16.2. Lock timeout

Dùng lock_timeout để migration fail sớm khi không lấy được lock trong budget.

~~~sql
SET lock_timeout = '3s';
ALTER TABLE public.orders ADD COLUMN source_code text;
~~~

### 16.3. Statement timeout

Đặt statement_timeout phù hợp với operation. Một migration rewrite lớn cần deadline khác với metadata-only DDL.

### 16.4. Blocker test

Trong staging, tạo transaction giữ lock có chủ đích rồi chạy migration để quan sát wait, timeout, cancellation và recovery.

### 16.5. Queueing impact

Một DDL đang chờ ACCESS EXCLUSIVE có thể khiến các requests khác xếp hàng phía sau. Đo ảnh hưởng tới latency, không chỉ thời gian command thực thi.

## 17. Index migration

Index creation/rebuild cần test trên table có kích thước và distribution gần production.

### 17.1. CREATE INDEX

Index build thông thường có thể block writes vào table trong thời gian build. Đo lock duration và resource use.

### 17.2. CREATE INDEX CONCURRENTLY

Concurrent build cho phép DML tiếp tục trong phần lớn quá trình, nhưng có nhiều phases, waits và không chạy trong transaction block.

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_created_at
ON public.orders (created_at);
~~~

### 17.3. Invalid index after failure

Nếu concurrent build fail, kiểm tra pg_index.indisvalid/indisready. Không cho rằng index tồn tại nghĩa là planner có thể dùng nó.

### 17.4. Unique index

Unique index build có thể fail nếu duplicates tồn tại. Chạy duplicate detection trên prior-version data trước khi deploy.

### 17.5. Disk/WAL headroom

Index build cần storage cho index mới, temporary files và WAL. Test peak disk usage và replication/archive retention.

## 18. Constraint migration

Constraint mới phải đúng với toàn bộ historical data, không chỉ rows mới.

### 18.1. NOT NULL

Trước khi đặt NOT NULL, đếm NULLs và xác định cách backfill/default. Test concurrent writes để tránh rows mới tạo NULL trong lúc migration.

### 18.2. CHECK

Tìm rows vi phạm điều kiện trước khi validate constraint. PostgreSQL hỗ trợ NOT VALID cho một số constraints, rồi VALIDATE riêng để giảm impact.

### 18.3. FOREIGN KEY

Kiểm tra orphan rows và remote/local relationship assumptions. NOT VALID rồi VALIDATE CONSTRAINT có thể giúp chia giai đoạn.

### 18.4. UNIQUE

Tìm duplicates theo đúng collation/operator semantics và business key. Xử lý duplicate deterministically trước khi tạo constraint.

### 18.5. Constraint validation

Đo thời gian validation trên table lớn, lock behavior và ảnh hưởng tới writes/reads. Kiểm tra catalog để xác nhận constraint đã validated.

## 19. Data type conversion

ALTER COLUMN TYPE có thể rewrite table hoặc cần cast dữ liệu; risk phụ thuộc source/target types và PostgreSQL version.

### 19.1. Cast validity

Chạy thử cast trên toàn bộ historical values hoặc sample có boundary cases. Xác định rows không convert được trước production.

### 19.2. Precision loss

Numeric scale/precision narrowing, timestamp truncation hoặc string length changes có thể làm mất thông tin.

### 19.3. Time zone semantics

Phân biệt timestamp without time zone và timestamptz; xác định timezone assumptions cho historical values trước khi convert.

### 19.4. Collation/encoding

Text conversion có thể ảnh hưởng comparison, sort, indexes và uniqueness. Test Unicode, case/accent behavior và collation version.

### 19.5. Rewrite duration

Nếu type change rewrite table, đo disk headroom, WAL, lock duration, replication lag và recovery time trên clone có kích thước đại diện.

## 20. Backfill data theo batches

Backfill trên table lớn nên có tiến độ rõ ràng, giới hạn transaction size và khả năng resume.

### 20.1. Stable key ranges

Chia theo primary key ranges hoặc deterministic partition để mỗi batch xử lý tập rows không trùng và không bỏ sót.

### 20.2. Idempotent update

Update chỉ rows chưa được chuyển hoặc dùng deterministic transformation để chạy lại không làm sai kết quả.

~~~sql
UPDATE public.orders
SET normalized_status =
    CASE legacy_status
        WHEN 'A' THEN 'active'
        WHEN 'C' THEN 'cancelled'
        ELSE 'unknown'
    END
WHERE normalized_status IS NULL
  AND order_id >= 1
  AND order_id < 10001;
~~~

### 20.3. Commit từng batch

Commit batches riêng để giới hạn lock duration, rollback cost và WAL bursts. Lưu last processed key/checkpoint.

### 20.4. Throttle

Giới hạn batch size/concurrency và nghỉ giữa batches nếu CPU, I/O, replication lag hoặc foreground latency vượt ngưỡng.

### 20.5. Concurrent application writes

Trong lúc backfill, application có thể tiếp tục sửa rows. Dùng dual-write, triggers, version columns hoặc freeze window theo thiết kế; không để backfill ghi đè cập nhật mới hơn.


## 21. Kiểm thử tính idempotent và khả năng resume

Migration data lớn thường cần chạy theo batches hoặc retry sau transient failures.

### 21.1. Idempotency

Chạy lại một batch không được tạo duplicate hoặc biến đổi giá trị lần thứ hai ngoài dự kiến. Thiết kế WHERE predicates/unique keys để xác định rows chưa xử lý.

### 21.2. Checkpoint

Lưu batch identifier, key range, rows attempted/updated và trạng thái commit. Checkpoint phải phản ánh transaction đã commit thật.

### 21.3. Resume after failure

Dừng migration ở giữa, khởi động lại runner và xác nhận nó tiếp tục từ trạng thái an toàn. Không bỏ qua batch chưa rõ outcome.

### 21.4. Concurrent inserts

Tạo rows mới trong lúc backfill để kiểm tra chúng có nhận schema mới/default/dual-write và không bị bỏ sót.

### 21.5. Concurrent updates/deletes

Thay đổi hoặc xóa rows đang nằm trong batch window. Kiểm tra migration có ghi đè dữ liệu mới hơn hoặc tái tạo rows đã xóa hay không.

## 22. Dual-write và dữ liệu đồng bộ tạm thời

Khi ứng dụng phải hỗ trợ schema cũ và mới cùng lúc, dual-write có thể duy trì cả hai representations trong giai đoạn chuyển đổi.

### 22.1. Dual-write

Application ghi vào cả old và new columns/tables. Mọi code paths, workers, imports và admin tools phải theo cùng contract.

### 22.2. Partial failure

Nếu write vào old structure thành công nhưng new structure thất bại, dữ liệu bị lệch. Dùng transaction chung khi cả hai nằm trong cùng database và cùng transaction boundary.

### 22.3. Backfill race

Backfill có thể chạy đồng thời với dual-write. Cần xác định thứ tự update, compare version/timestamp hoặc dùng conditional updates để không overwrite giá trị mới.

### 22.4. Reconciliation

Định kỳ so sánh old/new representations, tìm missing/mismatched rows và sửa theo quy tắc deterministic.

### 22.5. End dual-write

Chỉ dừng dual-write khi backfill hoàn tất, mismatch bằng zero hoặc đã được giải thích, và toàn bộ application instances đã chuyển sang schema mới.

## 23. Kiểm chứng dữ liệu sau migration

Data validation cần đo cả số lượng lẫn ý nghĩa nghiệp vụ.

### 23.1. Row counts

So sánh counts trước/sau theo table, partition và logical group. Nếu migration split/merge rows, dùng expected transformation formula thay vì đòi counts bằng nhau.

### 23.2. Aggregate checks

So tổng tiền, số lượng, balances, min/max, counts theo status/tenant/date và các aggregate nghiệp vụ quan trọng.

### 23.3. Key coverage

Đối chiếu primary keys hoặc stable business keys để phát hiện missing/duplicate records.

### 23.4. Checksums

Có thể tạo deterministic checksums trên normalized column sets hoặc key ranges. Chuẩn hóa NULL, timezone, numeric formatting và ordering trước khi hash.

### 23.5. Business invariants

Xác minh điều kiện nghiệp vụ như tổng allocations bằng total, order lines khớp order totals, balances không âm nếu policy yêu cầu, và trạng thái chuyển đổi hợp lệ.

## 24. Đối chiếu dữ liệu trước và sau

Một phép so sánh có ý nghĩa cần biết dữ liệu nào phải giữ nguyên và dữ liệu nào được phép biến đổi.

### 24.1. Preserve set

Liệt kê columns/records phải giữ nguyên chính xác, ví dụ identifiers, audit timestamps hoặc external references.

### 24.2. Transform set

Với columns được đổi format/unit/status, định nghĩa mapping cũ sang mới và test mọi historical values.

### 24.3. Derived set

Với columns được tính lại, xác định formula, rounding, timezone và null semantics.

### 24.4. Deleted/merged set

Nếu migration loại bỏ duplicates hoặc merge records, lưu mapping source keys sang target key và reason để audit.

### 24.5. Exception set

Rows không thể chuyển đổi cần được quarantine/report với owner và remediation. Không silently drop lỗi dữ liệu.

## 25. Kiểm tra referential integrity

Migration có thể thay đổi keys, split tables hoặc thêm foreign keys.

### 25.1. Orphan detection

Trước khi add foreign key, tìm child rows không có parent tương ứng.

~~~sql
SELECT c.parent_id, count(*)
FROM public.child_records AS c
LEFT JOIN public.parents AS p
  ON p.id = c.parent_id
WHERE c.parent_id IS NOT NULL
  AND p.id IS NULL
GROUP BY c.parent_id
ORDER BY count(*) DESC;
~~~

### 25.2. Key remapping

Nếu primary key đổi, tạo mapping old_id -> new_id và xác minh mọi referencing tables đã cập nhật.

### 25.3. Cascading effects

Kiểm tra ON DELETE/ON UPDATE behavior. Một migration có thể tạo cascade path mới và thay đổi tác động của application deletes.

### 25.4. Deferred constraints

Nếu dùng DEFERRABLE constraints, test cả transaction-level deferred validation và commit-time failures.

### 25.5. Catalog validation

Kiểm tra pg_constraint, convalidated, condeferrable và các metadata liên quan sau migration.

## 26. Kiểm tra sequences và generated identifiers

Data migration có thể copy rows với explicit IDs trong khi sequence vẫn giữ giá trị cũ.

### 26.1. Sequence state

So sánh sequence last_value/is_called với MAX(primary_key) trên table. Không để nextval tạo duplicate key sau cutover.

### 26.2. setval

Cập nhật sequence theo procedure phù hợp sau import/backfill:

~~~sql
SELECT setval(
    pg_get_serial_sequence('public.orders', 'order_id'),
    COALESCE((SELECT max(order_id) FROM public.orders), 1),
    EXISTS (SELECT 1 FROM public.orders)
);
~~~

Đây là ví dụ cần điều chỉnh theo sequence/identity thực tế và trạng thái table.

### 26.3. Identity columns

Kiểm tra GENERATED ALWAYS/BY DEFAULT semantics và cách import explicit values. Migration phải giữ behavior mà application kỳ vọng.

### 26.4. Concurrent inserts

Freeze hoặc điều phối writers khi đồng bộ sequence để tránh race với nextval. Thực hiện trong cutover step có kiểm soát.

### 26.5. Multi-table sequences

Inventory tất cả sequences/identity columns, gồm sequences không có default dependency rõ ràng hoặc được dùng từ nhiều tables.

## 27. Kiểm tra indexes và query plans sau migration

Schema mới có thể thay query plans dù data vẫn đúng.

### 27.1. Index definitions

So index columns, expressions, predicates, opclasses, collations và INCLUDE columns với target schema.

### 27.2. Index validity

Xác nhận indisvalid và indisready sau concurrent builds. Index invalid không đáp ứng mục đích production.

### 27.3. Planner statistics

Chạy ANALYZE sau bulk backfill/data transformation để planner nhận distribution mới.

### 27.4. Query plan baseline

So EXPLAIN plans của critical queries trước/sau, đặc biệt join order, estimates, scans, sort/hash và buffers.

### 27.5. Runtime acceptance

Benchmark p50/p95/p99, throughput và resource usage trên dataset representative. Plan shape change tự nó không chứng minh regression.

## 28. Views, functions, triggers và stored procedures

Migration schema thường ảnh hưởng objects phụ thuộc vào tables/columns.

### 28.1. View dependencies

Tìm views/materialized views tham chiếu columns đổi tên/drop. CREATE OR REPLACE VIEW cần giữ output contract nếu application phụ thuộc.

### 28.2. Function signatures

Thay function argument/return types có thể phá callers, grants và dependent objects. Kiểm tra overloaded functions và search_path.

### 28.3. Trigger behavior

Thêm/đổi trigger có thể làm dual-write hoặc backfill thực hiện side effects ngoài dự kiến. Test ordering, recursion và transition behavior.

### 28.4. Materialized views

Xác định refresh strategy và thời gian rebuild. Migration có thể làm materialized view stale hoặc không còn query được.

### 28.5. Dependency graph

Dùng catalogs/dependency inspection và staging deployment để phát hiện object không được quản lý bởi migration scripts.

## 29. Privileges, roles và row-level security

Migration có thể thay owner, grants, policies hoặc security semantics.

### 29.1. Role inventory

So roles, memberships, ownership và attributes như LOGIN, BYPASSRLS, CREATEDB/SUPERUSER theo policy.

### 29.2. Grants

Kiểm tra table/schema/sequence/function privileges trước/sau. CREATE TABLE mới có thể không nhận default privileges như mong đợi nếu owner khác.

### 29.3. Row-level security

Test policies với từng application role và data tenant. Migration thay columns/functions trong policy có thể làm users thấy quá ít hoặc quá nhiều rows.

### 29.4. SECURITY DEFINER

Kiểm tra owner và search_path cố định cho security-definer functions. Schema changes có thể tạo object shadowing risk.

### 29.5. Negative tests

Thử truy cập trái phép để xác nhận migration không vô tình mở quyền. Kiểm thử positive path và negative path bằng roles thực tế.

## 30. Extension và collation changes trong migration

Migration có thể thêm/upgrade extensions hoặc thay đổi text semantics.

### 30.1. Extension prerequisites

Cài package/shared library đúng PostgreSQL version trên test environment trước khi chạy CREATE/ALTER EXTENSION.

### 30.2. Extension update scripts

Test ALTER EXTENSION UPDATE từ version trước trên clone chứa extension data/config tables thật.

### 30.3. Collation version

Nếu OS/ICU/libc version thay đổi, kiểm tra collation version mismatch và index rebuild requirements.

### 30.4. Type/operator behavior

Extension types, operators và casts có thể thay behavior hoặc planner semantics. Test application queries và indexes phụ thuộc chúng.

### 30.5. Restore compatibility

Kiểm tra pg_dump/restore hoặc physical recovery với extension packages và versions mà migration target yêu cầu.

## 31. Partitioned tables và migration

Partitioned tables có các thao tác DDL/data khác với một table đơn.

### 31.1. Parent/child schema

Đảm bảo columns, types, constraints và indexes được áp dụng phù hợp cho parent và partitions hiện có.

### 31.2. New partitions

Nếu migration tạo partition mới, test partition bounds, default partition và routing của inserts.

### 31.3. Attach/detach

ATTACH PARTITION có thể scan/validate constraint và lấy locks. Test với table lớn và concurrent writes.

### 31.4. Partition indexes

Xác nhận partitioned index và child indexes hợp lệ, đầy đủ trên mọi partitions.

### 31.5. Historical partitions

Đừng chỉ test partition hiện tại. Historical partitions có thể chứa schema/data anomalies hoặc khác distribution đáng kể.

## 32. Large objects, JSON và specialized data

Một số types/objects có behavior riêng khi migration.

### 32.1. JSON/JSONB

Kiểm tra malformed legacy JSON, key casing, numeric/string distinctions, missing keys và transformation cost.

### 32.2. Arrays và composites

Test empty arrays, NULL arrays, nested values, composite types và type casts.

### 32.3. Large objects

Nếu dùng PostgreSQL large objects, kiểm tra lo metadata, ownership/privileges và reference integrity. pg_dump options phải bao gồm objects cần thiết.

### 32.4. TOAST

Large text/JSON/BYTEA có thể làm table rewrite, storage và WAL tăng mạnh. Dùng records có kích thước thực tế trong rehearsal.

### 32.5. Full-text/geospatial types

Extension-backed types/indexes cần package/version tương thích và migration test riêng cho operators, casts và index rebuilds.

## 33. Compatibility giữa application versions

Schema migration có thể diễn ra trong lúc nhiều application instances chạy các releases khác nhau.

### 33.1. Old application on expanded schema

Xác nhận app cũ vẫn chạy khi columns/tables mới được thêm. Defaults, triggers và NOT NULL changes không được làm code cũ fail.

### 33.2. New application on old schema

Nếu rollout yêu cầu, xác nhận app mới có thể hoạt động trước khi migration hoàn tất hoặc có feature flag để tránh truy cập object chưa tồn tại.

### 33.3. Mixed-version period

Chạy đồng thời old/new application instances trên expanded schema và test read/write consistency.

### 33.4. Worker compatibility

Background workers, scheduled jobs, ETL, admin tools và scripts có thể deploy chậm hơn web application. Đưa chúng vào compatibility matrix.

### 33.5. Contract gate

Chỉ contract schema cũ khi không còn clients/transactions/jobs sử dụng và telemetry xác nhận legacy access đã về zero trong thời gian quan sát.


## 34. Kiểm thử migration dưới tải đồng thời

Một migration có thể pass khi database idle nhưng gây outage khi production traffic tiếp tục chạy.

### 34.1. Representative concurrency

Chạy các read/write transactions tương tự production trong lúc migration. Bao gồm requests ngắn, long transactions và batch jobs.

### 34.2. Lock contention

Theo dõi pg_stat_activity, pg_locks và pg_blocking_pids để biết migration chờ ai và migration đang block những sessions nào.

### 34.3. Query latency

Đo p50/p95/p99 và error rate của critical endpoints trong lúc migration, không chỉ thời gian chạy migration command.

### 34.4. Connection pool behavior

Test pool exhaustion, waiting clients, reconnect behavior và application retries khi DDL hoặc remote operation gây delays.

### 34.5. Deadlocks và serialization errors

Tạo concurrent transactions có thể đụng cùng rows/constraints để xác định deadlock, serialization failure và retry behavior của application.

## 35. Kiểm thử WAL, disk và replication impact

Data migration và index build có thể tạo lượng WAL lớn, làm tăng storage usage và replica lag.

### 35.1. WAL generation

Ghi wal_bytes/LSN progression trước, trong và sau migration. Backfill lớn có thể làm WAL generation vượt baseline.

### 35.2. Disk headroom

Theo dõi data directory, pg_wal, temporary files, index growth và filesystem free space. Ước lượng peak usage chứ không chỉ final table size.

### 35.3. Replication lag

Theo dõi write/flush/replay lag và slot retained WAL. Migration có thể làm standby chậm hoặc giữ WAL lâu.

### 35.4. Archive throughput

Nếu dùng WAL archiving/PITR, kiểm tra archive queue và destination capacity trong migration. Không để archive backlog tăng vượt recovery budget.

### 35.5. Checkpoint pressure

Bulk writes/index builds có thể tăng checkpoint activity và I/O. Ghi checkpoint frequency, write time và storage latency.

## 36. Kiểm thử autovacuum và bloat sau migration

Large updates/deletes tạo dead tuples và có thể làm table/index bloat.

### 36.1. Dead tuples

Theo dõi n_dead_tup, vacuum history và table size trước/sau backfill.

### 36.2. Long snapshots

Long-running transactions có thể ngăn vacuum reclaim dead tuples. Test transaction duration và idle-in-transaction behavior.

### 36.3. Autovacuum catch-up

Xác nhận autovacuum có thể xử lý tables sau migration mà không cạnh tranh quá mức với foreground workload.

### 36.4. Analyze after backfill

Chạy ANALYZE sau data distribution changes và kiểm tra planner estimates/critical query plans.

### 36.5. Post-migration maintenance

Tính thời gian vacuum/analyze/reindex cần thiết sau migration vào change window hoặc stabilization plan.

## 37. Kiểm thử hiệu năng và thời gian migration

Thời gian trên clone giúp estimate production window nếu environment tương đồng.

### 37.1. Baseline duration

Đo từng migration step, gồm lock acquisition, execution, validation và cleanup. Không chỉ đo tổng command duration.

### 37.2. Scaling behavior

Chạy trên dataset nhiều kích cỡ để hiểu chi phí tăng theo row count/table size. Một số operations rewrite toàn table, một số phụ thuộc index/lock.

### 37.3. Resource profile

Ghi CPU, memory, disk IOPS/latency, network, WAL, temp files và replication lag.

### 37.4. Concurrency profile

So thời gian khi database idle và khi workload đại diện chạy. Dùng kết quả để tính impact budget.

### 37.5. Window estimate

Cộng durations theo sequence, dependencies, buffer cho retry/rollback và validation. Dùng percentile từ nhiều rehearsals thay vì một run.

## 38. Kiểm thử failure injection

Chủ động làm migration fail trong môi trường test để hiểu recovery behavior.

### 38.1. SQL error giữa migration

Chèn một failing statement trên clone hoặc tạo fixture khiến constraint validation fail. Xác nhận transaction rollback/partial progress như dự kiến.

### 38.2. Connection loss

Ngắt client connection trong một migration dài và kiểm tra server transaction state, migration history và retry safety.

### 38.3. Disk pressure

Trong môi trường cô lập, giới hạn disk để quan sát behavior của index build/backfill và đảm bảo monitoring/stop conditions hoạt động.

### 38.4. Lock timeout

Tạo blocker có kiểm soát và xác nhận migration fail nhanh, logs đủ thông tin và không để request queue kéo dài.

### 38.5. Worker/application crash

Dừng migration runner hoặc worker giữa batches để xác nhận checkpoint, idempotency và resume path.

## 39. Rollback chiến lược

Rollback cần được thiết kế theo loại thay đổi và data đã phát sinh sau cutover.

### 39.1. Transaction rollback

Với migration nằm trong một transaction chưa commit, ROLLBACK có thể hoàn tác DDL/data changes hỗ trợ transactional behavior.

### 39.2. Compensating migration

Sau khi migration commit, có thể cần migration ngược riêng. Migration ngược phải bảo toàn dữ liệu mới được ghi sau cutover.

### 39.3. Forward fix

Trong nhiều trường hợp, sửa lỗi bằng migration tiến về phía trước an toàn hơn rollback schema/data đã có writes mới.

### 39.4. Restore/PITR

Nếu thay đổi destructive hoặc data corruption không thể đảo ngược, restore/PITR có thể cần thiết. Tính RPO, RTO và reconciliation của writes sau recovery point.

### 39.5. Rollback boundary

Ghi thời điểm sau đó không còn rollback đơn giản, ví dụ khi application ghi dữ liệu theo format mới hoặc contract migration đã drop legacy columns.


## 40. Kiểm thử restore và recovery

Migration test nên chứng minh recovery plan hoạt động, không chỉ có backup file.

### 40.1. Pre-migration backup

Tạo backup/restore point trước destructive migration theo policy. Ghi backup identifier và WAL coverage.

### 40.2. Restore isolated clone

Restore vào isolated environment, xác nhận source schema/data và chạy migration lại từ đầu.

### 40.3. PITR target

Nếu cần rollback về một thời điểm, rehearsal PITR tới thời điểm ngay trước migration/cutover và kiểm tra database consistency.

### 40.4. Data after restore

Định nghĩa cách reconcile transactions được commit sau backup/recovery point: replay events, reprocess queue hoặc manual business reconciliation.

### 40.5. Recovery timing

Đo thời gian restore, WAL replay, application validation và traffic restore. RTO phải tính cả các bước này.

## 41. Không nhầm migration rollback với application rollback

Application code và database schema có lifecycle khác nhau.

### 41.1. Code rollback

Quay application về phiên bản cũ chỉ an toàn nếu schema mới vẫn tương thích với code cũ.

### 41.2. Schema rollback

Schema rollback có thể làm mất columns/data mà code mới đã ghi. Cần kiểm tra write patterns sau cutover.

### 41.3. Backward compatibility

Expand phase thường giữ schema cũ đủ lâu để app rollback được. Contract phase thường đóng rollback path đơn giản.

### 41.4. Data format compatibility

Nếu code mới ghi enum/status/JSON format mà code cũ không hiểu, rollback application có thể fail dù schema vẫn còn.

### 41.5. Rollback rehearsal

Thực hiện app rollback và schema/data recovery trên clone có writes sau cutover để chứng minh procedure.

## 42. Migration test trong CI

CI nên kiểm tra migration chain trên database khởi tạo từ prior-version schema.

### 42.1. Build source-version database

Khởi tạo PostgreSQL service/container đúng version và apply schema/migration history trước đó hoặc restore fixture snapshot.

### 42.2. Seed representative data

Nạp fixture có NULL, duplicates, historical values, boundary cases và references. Giữ seed deterministic.

### 42.3. Apply pending migrations

Chạy migration runner từ current source version tới target như deployment command.

### 42.4. Assert schema/data

Chạy SQL assertions cho columns/types/constraints/indexes, row counts, mappings, invariants và migration history.

### 42.5. Test matrix

Chạy trên các PostgreSQL major versions được hỗ trợ, extension versions và application versions liên quan. Không dùng một version duy nhất nếu sản phẩm hỗ trợ nhiều versions.

## 43. Migration test trong staging

Staging cần kiểm thử quy mô và topology gần production hơn CI.

### 43.1. Restore recent sanitized snapshot

Dùng snapshot đủ mới và đủ lớn. Ghi source timestamp và sanitization version.

### 43.2. Rehearse production command

Dùng cùng release artifact, credentials model, runner, flags và environment variables.

### 43.3. Load test

Chạy traffic representative trong khi migration, gồm peak/steady workloads và scheduled jobs liên quan.

### 43.4. Observe full topology

Kiểm tra primary/standby, logical subscribers, archive, poolers, application services và monitoring.

### 43.5. Sign-off evidence

Lưu duration, impact, validation outputs, unresolved risks, stop conditions và approval theo change process.

## 44. Production rehearsal và canary

Trước production cutover, có thể chạy migration trên canary database hoặc một tenant/subset nếu kiến trúc cho phép.

### 44.1. Canary scope

Chọn subset có data shape đại diện nhưng blast radius nhỏ. Không chọn chỉ tenant nhỏ dễ migrate.

### 44.2. Compare behavior

So schema, data invariants, query latency và application errors giữa canary và baseline.

### 44.3. Gradual rollout

Mở traffic từng phần, theo dõi mismatch/error/latency và dừng tăng traffic nếu threshold bị vượt.

### 44.4. Full cutover gate

Chỉ chuyển toàn bộ khi canary validation đạt và migration sequence đã được kiểm chứng cho phần data còn lại.

### 44.5. Limits of canary

Nếu migration cần global uniqueness, cross-tenant references hoặc shared tables, canary một tenant có thể không đại diện. Test clone full database vẫn cần thiết.


## 45. Observability trong migration

Một migration cần telemetry cho cả command progress và tác động lên service.

### 45.1. Migration runner logs

Ghi migration ID, start/end, duration, step, affected rows, error code và retry count.

### 45.2. Database activity

Theo dõi active sessions, wait events, locks, blockers, long transactions và idle-in-transaction.

### 45.3. Resource metrics

Theo dõi CPU, memory, disk latency/IOPS, free space, WAL, checkpoints và temp files.

### 45.4. Application metrics

Request rate, error rate, p95/p99, connection pool wait, queue depth và retries.

### 45.5. Replication/recovery metrics

Theo dõi replay lag, slot retained WAL, archive backlog và backup status. Alert thresholds phải được xác định trước migration.

## 46. Tổ chức migration test suite

Một test suite nên phân lớp để CI chạy nhanh và staging kiểm thử sâu.

### 46.1. Unit-level transformation tests

Test các transformation functions/SQL expressions trên edge cases nhỏ, dễ chạy và dễ debug.

### 46.2. Schema migration integration tests

Khởi tạo prior-version schema, seed fixture và chạy migration chain trên PostgreSQL thật. Test syntax/catalog behavior mà mock không thể đại diện.

### 46.3. Data reconciliation tests

Chạy counts, key coverage, checksums và business invariants trên dataset có kích thước đủ lớn.

### 46.4. Performance tests

Đo thời gian, locks, resource use và query latency trên clone đại diện. Thực hiện ở staging/nightly thay vì mọi commit nếu chi phí cao.

### 46.5. Recovery tests

Test resume, transaction rollback, forward fix, restore/PITR và application rollback theo risk level.

## 47. SQL assertions sau migration

Các assertions nên thất bại rõ ràng khi schema/data không đạt target.

### 47.1. Kiểm tra column

~~~sql
SELECT
    table_schema,
    table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'orders'
ORDER BY ordinal_position;
~~~

### 47.2. Kiểm tra constraints

~~~sql
SELECT
    conname,
    contype,
    convalidated,
    condeferrable
FROM pg_constraint
WHERE conrelid = 'public.orders'::regclass
ORDER BY conname;
~~~

### 47.3. Kiểm tra indexes

~~~sql
SELECT
    indexrelid::regclass AS index_name,
    indisvalid,
    indisready,
    indisunique
FROM pg_index
WHERE indrelid = 'public.orders'::regclass
ORDER BY indexrelid::regclass::text;
~~~

### 47.4. Kiểm tra migration marker

Đọc version/checksum từ migration history table theo framework. Assert target version đã apply đúng một lần.

### 47.5. Assertions phải có expected values

Không chỉ in kết quả ra log. Test runner phải so sánh với expected result và trả non-zero khi invariant thất bại.

## 48. Data validation queries

Ví dụ các truy vấn kiểm tra dữ liệu sau migration.

### 48.1. NULL còn lại

~~~sql
SELECT count(*) AS missing_status
FROM public.orders
WHERE normalized_status IS NULL;
~~~

### 48.2. Unexpected values

~~~sql
SELECT normalized_status, count(*)
FROM public.orders
GROUP BY normalized_status
ORDER BY count(*) DESC;
~~~

### 48.3. Duplicate business keys

~~~sql
SELECT external_order_id, count(*)
FROM public.orders
GROUP BY external_order_id
HAVING count(*) > 1;
~~~

### 48.4. Aggregate reconciliation

~~~sql
SELECT
    count(*) AS rows_total,
    count(DISTINCT order_id) AS unique_orders,
    sum(total_amount) AS amount_total,
    min(created_at) AS first_order,
    max(created_at) AS last_order
FROM public.orders;
~~~

### 48.5. Cross-table invariant

~~~sql
SELECT o.order_id
FROM public.orders AS o
LEFT JOIN public.customers AS c
  ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL;
~~~

Các truy vấn cần điều chỉnh theo business rules và expected transformations. Nếu migration hợp lệ có merge/delete rows, xây expected reconciliation thay vì dùng invariant cũ một cách máy móc.

## 49. Test artifacts và báo cáo migration rehearsal

Báo cáo phải cho phép người khác tái hiện test và hiểu quyết định release.

### 49.1. Source identity

Ghi source backup/snapshot ID, database name, PostgreSQL version, application release và migration version.

### 49.2. Environment identity

Ghi CPU/RAM/storage, PostgreSQL configuration, extensions, collations và network topology.

### 49.3. Migration evidence

Lưu runner logs, SQL output, start/end timestamps, rows processed, lock waits, failures và retries.

### 49.4. Validation evidence

Lưu schema diff, row counts, checksums, business invariants, constraints/index validity và application smoke test results.

### 49.5. Performance evidence

Lưu durations theo bước, p95/p99, CPU/I/O, WAL, disk peak, replication lag và query plans liên quan.

## 50. Acceptance criteria và release gate

Acceptance criteria phải được định nghĩa trước khi rehearsal.

### 50.1. Correctness gate

Migration chain hoàn tất; schema/objects đúng target; data transformations và business invariants đạt.

### 50.2. Compatibility gate

Old/new application compatibility đáp ứng rollout plan; privileges, triggers, jobs và integrations hoạt động.

### 50.3. Performance gate

Migration duration, lock time, query latency, resource usage, disk headroom và replication lag nằm trong budget.

### 50.4. Recovery gate

Backup/restore, rollback/forward fix, resume behavior và operational ownership đã được chứng minh.

### 50.5. Decision

Pass/fail phải dựa trên evidence. Nếu có exception, ghi rõ risk, owner, mitigation và approval trước production.

## 51. Runbook rehearsal từ prior-version database

Một quy trình mẫu để chạy rehearsal có thể theo thứ tự sau.

1. Chọn source snapshot đúng application/schema version hiện tại.
2. Restore snapshot vào isolated PostgreSQL environment.
3. Áp dụng sanitization/seed bổ sung theo script đã version control.
4. Xác nhận schema, extensions, roles và migration marker đúng source state.
5. Chụp baseline counts, invariants, query plans và resource metrics.
6. Chạy preflight: disk, locks, connections, replication và permissions.
7. Chạy migration runner với cùng artifact/flags/role như production.
8. Ghi thời gian, logs, rows processed, locks, WAL và failures.
9. Chạy schema/data/business assertions.
10. Chạy application smoke tests và mixed-version compatibility tests.
11. Chạy load/performance/replication checks.
12. Thử recovery path phù hợp với migration risk.
13. Lưu artifacts và so với acceptance thresholds.
14. Cập nhật runbook hoặc migration scripts nếu có lỗi; chạy lại từ source snapshot sạch.

## 52. Ví dụ: thêm NOT NULL column vào bảng lớn

Giả sử bảng orders ở source version có hàng triệu rows và column mới normalized_status phải luôn có giá trị.

### 52.1. Source inspection

Đếm rows, NULL distribution của legacy_status, status values hiếm và tốc độ insert/update. Xác định mapping cho mọi legacy values.

### 52.2. Expand

Thêm normalized_status nullable. Kiểm tra DDL lock duration và old application compatibility.

### 52.3. Backfill

Cập nhật theo key ranges nhỏ bằng CASE mapping. Commit từng batch và ghi checkpoint.

### 52.4. Dual-write

Deploy app ghi cả legacy_status và normalized_status; test concurrent writes để không phát sinh mismatch.

### 52.5. Validate và contract

Xác nhận không còn NULL/unknown ngoài policy, thêm CHECK/NOT NULL theo chiến lược phù hợp, chuyển reads sang column mới và drop legacy column ở release sau.

## 53. Ví dụ: tạo unique constraint sau khi chuẩn hóa dữ liệu

### 53.1. Xác định business key

Làm rõ normalization rules: trim, case folding, Unicode normalization và collation. Unique key phải theo đúng business semantics.

### 53.2. Detect duplicates

Tạo expression query theo normalization rule để nhóm duplicate candidates. Lưu mapping rows cần merge/resolve.

### 53.3. Resolve conflicts

Chọn record canonical theo business rule, chuyển references và lưu audit trail. Không xóa duplicate tùy tiện.

### 53.4. Build unique index

Sau khi dữ liệu sạch, tạo unique index theo lock/downtime budget; cân nhắc CREATE UNIQUE INDEX CONCURRENTLY và xử lý invalid index nếu fail.

### 53.5. Validate

Kiểm tra index valid/unique, thử duplicate insert bị reject và test application behavior khi concurrent create/update key.

## 54. Ví dụ: đổi type và chuẩn hóa timezone

### 54.1. Profile source values

Lấy min/max, NULL, malformed strings, timezone offsets và các records ở DST boundaries.

### 54.2. Dry-run conversion

Chạy conversion expression trên clone, ghi rows không convert được và so giá trị mẫu với expected business time.

### 54.3. Expand representation

Nếu cần, thêm column mới với target type thay vì rewrite/destructive change ngay. Backfill và dual-write trong giai đoạn tương thích.

### 54.4. Reconcile

So sánh normalized timestamps theo UTC/expected timezone và kiểm tra reports/date partitions.

### 54.5. Cutover

Chuyển app đọc column mới, theo dõi errors và chỉ drop legacy representation khi hết rollback window.


## 55. Những lỗi thường gặp khi kiểm thử migration

1. Chỉ test trên database rỗng hoặc vài rows seed.
2. Dùng schema mới dựng bằng tay thay vì restore prior-version schema.
3. Bỏ qua migration chain và chỉ chạy script mới nhất.
4. Test bằng PostgreSQL major version khác production mà không ghi nhận khác biệt.
5. Không cài đúng extensions/collations trước rehearsal.
6. Dùng dataset đã sanitize quá mức làm mất skew/duplicates/NULLs quan trọng.
7. Chỉ so row counts mà không kiểm tra business invariants.
8. Bỏ qua sequence state sau import explicit identifiers.
9. Thêm NOT NULL/UNIQUE/FK mà không profile historical violations.
10. Tạo index trên table nhỏ rồi suy ra production lock/duration.
11. Chạy backfill một transaction khổng lồ không có checkpoint.
12. Không test backfill với concurrent application writes.
13. Giả định migration rollback được chỉ vì DDL nằm trong transaction.
14. Không kiểm tra external side effects của triggers/functions/jobs.
15. Bỏ qua application instances/worker chạy phiên bản cũ.
16. Không đo WAL, disk peak và replication lag.
17. Không test failed concurrent index hoặc invalid index cleanup.
18. Không test restore/PITR từ trước migration.
19. Sửa migration đã apply trên production thay vì tạo migration mới.
20. Không lưu source snapshot ID và logs để tái hiện kết quả.
21. Không đặt acceptance/stop thresholds trước rehearsal.
22. Chỉ monitor migration command, bỏ qua latency/error rate của application.
23. Dùng canary nhỏ không có cross-tenant/global constraints rồi coi là đủ.
24. Đánh dấu migration pass dù có rows bị quarantine nhưng chưa có owner.
25. Mở contract migration khi legacy clients vẫn còn hoạt động.

## 56. Bài tập thực hành

### Bài 1 — Prior-version baseline

Vì sao cần bắt đầu test từ schema/data phiên bản trước?

**Đáp án:** Vì migration biến đổi trạng thái đã tồn tại; historical values, constraints, table size và dependencies có thể làm migration fail.

### Bài 2 — Schema baseline

Nêu bốn loại objects cần inventory ngoài tables.

**Gợi ý:** Indexes, constraints, sequences, views, functions, triggers, types, grants, extensions.

### Bài 3 — Data baseline

Vì sao row count không đủ mô tả dataset?

**Đáp án:** Nó không mô tả NULLs, duplicates, skew, ranges, historical values và relationships.

### Bài 4 — Snapshot

Vì sao cần ghi snapshot identifier?

**Đáp án:** Để tái tạo cùng source state và so sánh các lần rehearsal.

### Bài 5 — Sanitization

Sanitize production data có thể gây hại cho migration testing như thế nào?

**Đáp án:** Có thể phá uniqueness, referential links, skew và edge cases mà migration phải xử lý.

### Bài 6 — Expand-and-contract

Vì sao không drop column cũ trong cùng release đầu tiên?

**Gợi ý:** Old application instances/workers cần thời gian tương thích và rollback window.

### Bài 7 — Migration history

Có nên sửa migration history table để bỏ qua migration fail không?

**Đáp án:** Không; cần xác định state và sửa bằng migration/recovery có kiểm soát.

### Bài 8 — Transaction boundaries

CREATE INDEX CONCURRENTLY có thể chạy trong transaction block không?

**Đáp án:** Không; migration framework cần hỗ trợ non-transactional step.

### Bài 9 — Lock timeout

lock_timeout giúp kiểm soát điều gì?

**Đáp án:** Giới hạn thời gian chờ lấy lock để migration fail nhanh thay vì chờ không hạn định.

### Bài 10 — Unique constraint

Cần kiểm tra gì trước khi tạo unique index?

**Đáp án:** Duplicate candidates theo đúng business key/normalization/collation rules.

### Bài 11 — NOT NULL

Cần làm gì trước khi đặt NOT NULL trên column cũ?

**Gợi ý:** Profile NULLs, backfill/default, kiểm soát concurrent writes và validate.

### Bài 12 — Foreign key

Vì sao phải tìm orphan rows trước khi thêm FK?

**Đáp án:** Historical child rows có thể tham chiếu parent không tồn tại.

### Bài 13 — Backfill

Vì sao chia backfill thành batches?

**Đáp án:** Giảm lock duration, rollback cost, WAL burst và cho phép resume/throttle.

### Bài 14 — Idempotency

Một batch idempotent nghĩa là gì?

**Đáp án:** Retry cùng batch không làm sai kết quả hoặc tạo duplicate side effects.

### Bài 15 — Concurrent writes

Backfill có thể ghi đè application update mới hơn không?

**Đáp án:** Có nếu không có conditional/versioning/dual-write strategy phù hợp.

### Bài 16 — Sequence state

Sau import IDs explicit cần kiểm tra gì?

**Đáp án:** Sequence/identity next value phải lớn hơn giá trị đã dùng để tránh duplicate keys.

### Bài 17 — Checksums

Vì sao checksum cần normalize data?

**Đáp án:** NULL, timezone, numeric formatting và row ordering có thể tạo hash khác dù dữ liệu tương đương.

### Bài 18 — Query plans

Vì sao cần so EXPLAIN sau migration?

**Đáp án:** Schema/index/data changes có thể làm planner chọn plan khác và ảnh hưởng performance.

### Bài 19 — Application compatibility

Mixed-version testing kiểm tra điều gì?

**Đáp án:** Old/new application instances và workers có thể cùng hoạt động trong expanded schema window.

### Bài 20 — RLS

Vì sao cần test migration bằng nhiều application roles?

**Đáp án:** Grants và row-level security có thể khiến từng role nhìn thấy hoặc thay đổi tập rows khác nhau.

### Bài 21 — WAL

Backfill lớn có thể ảnh hưởng gì tới replication?

**Đáp án:** Tăng WAL generation, replay lag, slot retention và archive backlog.

### Bài 22 — Failure injection

Tại sao nên tạo SQL error/lock timeout trong clone?

**Đáp án:** Để chứng minh rollback, partial progress, logging và recovery behavior.

### Bài 23 — Rollback boundary

Điều gì có thể làm application rollback không còn an toàn?

**Đáp án:** New code đã ghi data format mà old code không hiểu hoặc contract đã xóa legacy objects.

### Bài 24 — PITR

Vì sao phải rehearsal restore/PITR?

**Đáp án:** Backup file tồn tại không chứng minh restore có thể hoàn tất trong RTO hoặc dữ liệu đúng.

### Bài 25 — CI vs staging

CI và staging có vai trò khác nhau thế nào?

**Đáp án:** CI kiểm tra nhanh correctness/migration chain; staging kiểm tra scale, topology, concurrency và operational impact.

### Bài 26 — Canary

Canary một tenant có thể bỏ sót điều gì?

**Đáp án:** Global uniqueness, cross-tenant references, shared tables và data distributions khác.

### Bài 27 — Acceptance criteria

Khi nào rehearsal được coi là pass?

**Gợi ý:** Correctness, compatibility, performance, recovery và evidence đều đạt thresholds đã đặt.

### Bài 28 — Migration duration

Vì sao một lần rehearsal không đủ estimate window?

**Đáp án:** Runtime biến động theo cache, load, storage, data distribution và background tasks.

### Bài 29 — Source snapshot

Nếu schema drift trước migration đã tồn tại, xử lý thế nào?

**Đáp án:** Ghi nhận/reconcile drift và xác định source state hợp lệ trước khi đánh giá migration.

### Bài 30 — Forward fix

Khi nào forward fix có thể an toàn hơn rollback?

**Đáp án:** Khi đã có writes mới theo schema/format mới hoặc rollback có nguy cơ mất dữ liệu.

## 57. Checklist chuẩn bị source database

- [ ] Đã xác định application release, PostgreSQL version và migration marker?
- [ ] Snapshot/backup source có consistency và identifier rõ?
- [ ] Schema DDL, indexes, constraints, sequences, functions/triggers đã inventory?
- [ ] Extensions, collations, roles, grants và ownership đã ghi?
- [ ] Row counts và data distribution profiles đã lưu?
- [ ] NULLs, duplicates, legacy values, boundary values và orphan candidates có fixtures?
- [ ] Sensitive data được sanitize theo policy mà vẫn giữ relationships/skew?
- [ ] Snapshot gốc được bảo vệ và working clone được tạo riêng?
- [ ] Restore source state đã được kiểm tra trước khi chạy migration?

## 58. Checklist chạy migration rehearsal

- [ ] Dùng đúng migration runner/version/flags/role?
- [ ] Chạy toàn bộ migration chain từ source version?
- [ ] Preflight disk, locks, sessions, extensions và privileges đạt?
- [ ] DDL lock_timeout/statement_timeout phù hợp?
- [ ] Non-transactional commands được xử lý đúng?
- [ ] Backfill có batch/checkpoint/idempotency/throttle?
- [ ] Concurrent application writes/workers đã được mô phỏng?
- [ ] Start/end duration, rows, locks, WAL và errors được ghi?
- [ ] Failure/resume path đã được thử ở clone?
- [ ] Source clone/logs được giữ lại khi có failure?

## 59. Checklist validation sau migration

- [ ] Target schema và migration history đúng?
- [ ] Columns/types/defaults/nullability đã xác nhận?
- [ ] Constraints validated và indexes valid/ready?
- [ ] Row counts/key coverage/checksums đạt expected transformations?
- [ ] Business aggregates/invariants đạt?
- [ ] Sequences/identity values an toàn?
- [ ] Views/functions/triggers/extensions/partitions hoạt động?
- [ ] Grants/RLS/security negative tests đạt?
- [ ] Application smoke tests và mixed-version compatibility đạt?
- [ ] Critical query plans/latency đạt?
- [ ] WAL/disk/autovacuum/replication/archive ổn định?

## 60. Checklist release và recovery gate

- [ ] Migration duration nằm trong approved window?
- [ ] Lock impact/error rate/latency nằm trong budget?
- [ ] Backup/PITR restore test và RTO/RPO evidence có sẵn?
- [ ] Rollback boundary và forward-fix strategy rõ?
- [ ] Canary/full rollout gates và stop conditions được định nghĩa?
- [ ] Owners/on-call/escalation contacts đã xác nhận?
- [ ] Artifacts, source snapshot ID, logs và validation reports được lưu?
- [ ] Exceptions có risk owner/mitigation/approval?
- [ ] Legacy app/workers không còn phụ thuộc trước contract phase?

## 61. Bảng tra cứu nhanh

| Thành phần | Mục đích |
|---|---|
| Prior-version schema | Source structure trước migration |
| Data snapshot | Source rows nhất quán để tái hiện |
| Schema baseline | Inventory DDL/objects/privileges |
| Data profile | NULL/skew/range/duplicates/relationships |
| Migration history | Version/checksum đã apply |
| Expand-and-contract | Chuyển schema theo giai đoạn tương thích |
| DDL lock | Lock ảnh hưởng concurrent sessions |
| lock_timeout | Giới hạn thời gian chờ lock |
| statement_timeout | Giới hạn thời gian statement |
| CREATE INDEX CONCURRENTLY | Tạo index giảm blocking DML |
| NOT VALID | Thêm một số constraints trước khi validate |
| VALIDATE CONSTRAINT | Kiểm tra historical rows theo constraint |
| Backfill | Chuyển đổi dữ liệu đã tồn tại |
| Checkpoint | Ghi nhận batch progress đã commit |
| Idempotency | Retry không tạo sai lệch |
| Dual-write | Ghi đồng thời old/new representations |
| Reconciliation | So sánh và sửa mismatch |
| Sequence state | Next identifier sau import/backfill |
| pg_stat_activity | Session/query state |
| pg_locks | Lock state |
| pg_stat_replication | Replication progress |
| WAL | Write-ahead log generation/retention |
| PITR | Point-in-time recovery |
| Canary | Rollout/migration thử trên phạm vi nhỏ |
| Acceptance criteria | Điều kiện pass/fail đã định trước |

## 62. Kết luận

**Migration cần được kiểm thử trên một bản sao nhất quán của schema và dữ liệu phiên bản trước, rồi chạy toàn bộ migration chain giống production.** Database trống không đại diện cho historical values, NULLs, duplicates, skew, relationships, table size, extensions và object dependencies đã tích lũy. Source snapshot cần có identity rõ, được bảo vệ và có thể restore lại để mỗi rehearsal bắt đầu từ cùng một trạng thái.

Một rehearsal đầy đủ kiểm tra DDL locks, constraints/indexes, data backfill, sequences, dependent objects, privileges/RLS và compatibility giữa application versions. Data validation phải bao gồm row/key coverage, checksums đã normalize và business invariants; performance validation phải đo lock waits, query latency, CPU/I/O, WAL, disk peak, autovacuum và replication lag. Backfills cần batches, checkpoints, idempotency và xử lý concurrent writes.

Rollback không phải lúc nào cũng đơn giản sau khi migration commit hoặc ứng dụng đã ghi dữ liệu theo format mới. Test transaction rollback, compensating/forward migrations, application rollback và restore/PITR theo risk. CI kiểm tra correctness trên prior-version fixtures; staging rehearsal xác nhận scale, topology, concurrency và recovery; production chỉ được triển khai khi acceptance criteria, stop conditions và owners đã rõ.

Nguyên tắc kiểm thử: **khôi phục đúng trạng thái cũ, chạy đúng chuỗi migration, chứng minh dữ liệu mới giữ đúng ý nghĩa nghiệp vụ, đo tác động dưới tải và diễn tập recovery trước khi chạm production.**

