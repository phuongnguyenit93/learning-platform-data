# Đối phó migration lỗi, lược đồ lệch và triển khai dở dang trong PostgreSQL

Một lần triển khai schema có thể thất bại ở bất kỳ thời điểm nào: trước khi chạy DDL, giữa một script nhiều bước, sau khi một phần lệnh đã commit, khi tạo index concurrently, hoặc sau khi database đã đổi schema nhưng ứng dụng chưa được triển khai tương thích. Khi đó, việc chạy lại migration ngay lập tức có thể làm trạng thái phức tạp hơn.

**Migration failure** là trường hợp một hoặc nhiều bước thay đổi schema/dữ liệu không hoàn thành theo kế hoạch. **Schema drift** là sự khác biệt giữa schema thực tế trong database và schema mà source code, migration repository hoặc môi trường chuẩn mong đợi. **Partial deployment** là triển khai chỉ hoàn thành một phần: database, application, worker, replica hoặc các môi trường chưa cùng đạt phiên bản tương thích.

Cách xử lý an toàn bắt đầu bằng việc xác định chính xác trạng thái hiện tại. Cần biết migration nào đã được ghi nhận, câu lệnh nào đã commit, object nào đã được tạo, dữ liệu nào đã biến đổi và ứng dụng nào đang phụ thuộc vào schema đó. Chỉ sau khi có trạng thái đáng tin cậy mới quyết định retry, rollback hoặc forward-fix.

~~~mermaid
flowchart TD
    A["Migration / deployment gặp lỗi"] --> B["Dừng các bước tiếp theo"]
    B --> C["Xác định target và migration state"]
    C --> D["Kiểm tra ledger, catalog, logs, data"]
    D --> E{"Trạng thái đã rõ?"}
    E -->|"Chưa"| F["Giữ nguyên trạng thái, thu thập evidence"]
    F --> D
    E -->|"Rồi"| G{"Có thể rollback an toàn?"}
    G -->|"Có"| H["Thực hiện rollback có kiểm soát"]
    G -->|"Không"| I["Forward-fix / repair / restore"]
    H --> J["Post-check schema, data, app"]
    I --> J
    J --> K{"Acceptance criteria đạt?"}
    K -->|"Không"| L["Escalate, giữ change mở"]
    K -->|"Có"| M["Đồng bộ migration ledger và đóng change"]
~~~

Bài học thuộc chương **Thay đổi lược đồ**, module **Database Engine Relational PostgreSQL**. Nội dung tập trung vào điều tra migration lỗi, phát hiện schema drift, khôi phục trạng thái triển khai dở dang, kiểm soát retry và xác minh trước khi đóng thay đổi.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt migration failure, schema drift và partial deployment.
2. Nhận diện các nguyên nhân phổ biến khiến migration thất bại.
3. Hiểu vì sao không nên retry một migration khi chưa xác định trạng thái thực tế.
4. Kiểm tra migration ledger và đối chiếu với database catalogs.
5. Phân biệt transactional DDL với các thao tác không thể chạy trong transaction block.
6. Xử lý index invalid sau CREATE INDEX CONCURRENTLY.
7. Điều tra constraint NOT VALID và validation chưa hoàn tất.
8. Phát hiện schema drift giữa các môi trường.
9. So sánh schema theo object definitions, owner, grants và settings.
10. Thiết kế migration idempotent hoặc có precondition rõ ràng.
11. Sử dụng migration lock để tránh hai deployment chạy đồng thời.
12. Chọn rollback, forward-fix hoặc restore theo mức độ thay đổi dữ liệu.
13. Áp dụng expand-contract để deploy schema tương thích nhiều phiên bản ứng dụng.
14. Xử lý migration data lớn theo batch và checkpoint.
15. Phục hồi partial deployment giữa database và application.
16. Thu thập evidence, xác minh và cập nhật migration ledger an toàn.
17. Xây dựng runbook và acceptance criteria cho migration recovery.

## 2. Phân biệt ba loại sự cố

### Migration failure

Một migration không hoàn thành như dự kiến. Ví dụ:

- ALTER TABLE bị lock timeout.
- CREATE INDEX CONCURRENTLY thất bại.
- Script lỗi cú pháp ở câu lệnh thứ ba.
- Data backfill gặp duplicate key.
- Migration tool mất kết nối sau khi server đã commit.
- Extension upgrade script thất bại.

Migration failure có thể để lại database nguyên trạng, thay đổi một phần hoặc hoàn tất toàn bộ nhưng client không nhận được phản hồi.

### Schema drift

Schema thực tế khác với schema mong đợi. Ví dụ:

- Một cột được DBA thêm thủ công nhưng không có migration.
- Migration đã chạy ở staging nhưng chưa chạy ở production.
- Một index bị drop trong incident và chưa được tạo lại.
- Default privilege khác nhau giữa hai database.
- Một environment có extension version khác.
- Migration ledger nói đã chạy nhưng object tương ứng không tồn tại.

Drift có thể xuất hiện do thay đổi thủ công, migration bị bỏ qua, restore từ backup cũ, hotfix, công cụ deploy lỗi hoặc khác biệt cấu hình giữa môi trường.

### Partial deployment

Một phần hệ thống đã chuyển phiên bản, phần còn lại chưa. Ví dụ:

- Database schema mới đã triển khai nhưng application binary cũ vẫn chạy.
- Application mới đã deploy nhưng migration chưa chạy.
- Một số worker đã restart, một số worker cũ vẫn giữ connection.
- Primary đã nâng schema nhưng standby/consumer hoặc downstream chưa bắt kịp.
- Một số tenant/database đã migrate, số khác chưa.

Partial deployment nguy hiểm khi hai phiên bản ứng dụng cần schema khác nhau hoặc khi các service triển khai theo thứ tự không tương thích.

## 3. Vì sao migration có thể thất bại?

Nhóm nguyên nhân phổ biến:

| Nhóm | Ví dụ | Dấu hiệu |
| --- | --- | --- |
| SQL/schema | Column/table/type không tồn tại | undefined_table, undefined_column |
| Data quality | Duplicate, NULL, invalid value | unique_violation, check_violation |
| Locking | DDL chờ transaction dài | lock timeout, blocked backend |
| Capacity | Disk đầy, temp/WAL tăng | no space left, I/O errors |
| Permission | Role thiếu quyền | permission denied |
| Version/extension | SQL hoặc binary không tương thích | function/library/control file error |
| Network/client | Kết nối mất sau commit | client timeout, trạng thái không rõ |
| Concurrency | Hai migration chạy cùng lúc | duplicate object, deadlock |
| Application ordering | Code và schema không tương thích | runtime SQL errors |
| Operational | Sai target, config hoặc script | migration chạy nhầm environment |

Một lỗi được báo ở client không luôn chứng minh server chưa thực hiện lệnh. Ví dụ, client timeout ngay sau COMMIT có thể xảy ra khi transaction đã commit nhưng response bị mất trên network. Trạng thái cần được xác minh từ database.

## 4. Quy tắc đầu tiên: dừng và xác định trạng thái

Khi migration thất bại:

1. Dừng các migration step tiếp theo.
2. Không chạy lại cùng migration một cách tự động.
3. Ghi nhận command, migration ID, timestamp, target database và error output.
4. Xác định migration tool có giữ transaction hay không.
5. Kiểm tra session còn chạy hay đã disconnect.
6. Kiểm tra migration ledger.
7. Kiểm tra catalog objects và data changes.
8. Xác định application version nào đang chạy.
9. Xác định có deployment khác hoặc operator khác đang thao tác không.
10. Chọn recovery path sau khi trạng thái đã rõ.

Nếu command timeout, trước tiên kiểm tra server-side state. Không giả định timeout đồng nghĩa rollback.

### Xác nhận đúng target

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

Đối chiếu environment, cluster inventory và deployment record. Một kết nối thành công vào database cùng tên chưa đủ chứng minh đó là đúng cluster.

## 5. Migration ledger là gì?

Migration tool thường lưu lịch sử migration trong một bảng metadata/ledger. Tên bảng phụ thuộc tool, ví dụ:

- Flyway thường dùng `flyway_schema_history`.
- Liquibase thường dùng `databasechangelog` và `databasechangeloglock`.
- Alembic thường dùng `alembic_version`.
- Rails có `schema_migrations`.
- Prisma dùng `_prisma_migrations`.
- Công cụ nội bộ có thể dùng bảng riêng.

Ledger có thể ghi:

- Migration version/ID.
- Description.
- Checksum.
- Start/finish timestamp.
- Execution duration.
- Success/failure state.
- Installed rank hoặc batch.
- Tool version.

### Ledger không phải nguồn sự thật duy nhất

Ledger cho biết tool nghĩ rằng migration đã chạy như thế nào. Catalog và dữ liệu cho biết database hiện đang ở trạng thái nào.

Hai nguồn có thể lệch nhau:

| Ledger | Database objects/data | Diễn giải có thể |
| --- | --- | --- |
| Đã thành công | Đúng như mong đợi | Trạng thái bình thường |
| Chưa ghi nhận | Thay đổi đã tồn tại | DDL chạy thủ công, commit rồi mất response hoặc ledger update thất bại |
| Ghi thành công | Object thiếu | Drift, object bị xóa sau migration hoặc ledger không đáng tin |
| Đang chạy/failed | Một phần object tồn tại | Migration bị ngắt giữa các bước hoặc có DDL non-transactional |
| Checksum mismatch | Schema có thể vẫn đúng | File migration đã bị chỉnh sau khi triển khai |

Không sửa ledger bằng UPDATE/DELETE trực tiếp chỉ để làm công cụ hết báo lỗi. Trước tiên phải xác định trạng thái database và quy trình repair/baseline chính thức của tool.

## 6. Kiểm tra migration ledger

Ví dụ với một bảng lịch sử đơn giản do ứng dụng tự quản lý:

~~~sql
SELECT
    version,
    description,
    installed_on,
    execution_time,
    success
FROM app_schema_migrations
ORDER BY version;
~~~

Đây chỉ là schema minh họa. Không giả định mọi migration tool dùng cùng tên bảng hoặc cột.

Với Flyway, Liquibase, Alembic hoặc Prisma, dùng đúng CLI/API và tài liệu phiên bản để:

- Xem migration history.
- Xem trạng thái pending/applied/failed.
- Kiểm tra checksum.
- Kiểm tra lock đang được giữ.
- Thực hiện repair/baseline nếu tool hỗ trợ và có phê duyệt.

Không chạy lệnh repair trước khi database đã được đối chiếu. Một lệnh repair có thể đánh dấu metadata là hợp lệ mà không sửa schema thực tế.

## 7. Kiểm tra session và migration đang chạy

Nếu migration có vẻ treo, xem session:

~~~sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
~~~

Tìm blocker:

~~~sql
SELECT
    waiting.pid AS waiting_pid,
    waiting.application_name AS waiting_app,
    now() - waiting.query_start AS wait_age,
    left(waiting.query, 180) AS waiting_query,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_app,
    blocker.state AS blocker_state,
    now() - blocker.xact_start AS blocker_xact_age,
    left(blocker.query, 180) AS blocker_query
FROM pg_stat_activity AS waiting
JOIN LATERAL unnest(pg_blocking_pids(waiting.pid)) AS p(blocker_pid)
    ON true
JOIN pg_stat_activity AS blocker
    ON blocker.pid = p.blocker_pid
WHERE waiting.datname = current_database()
ORDER BY waiting.query_start;
~~~

Một blocker ở trạng thái idle in transaction vẫn có thể giữ lock. Kiểm tra transaction age và application logs trước khi quyết định terminate.

### Không terminate backend theo PID cũ

PID có thể đã kết thúc hoặc được tái sử dụng. Trước khi cancel/terminate, xác minh lại PID, user, database, application_name, query và tác động. Ưu tiên yêu cầu migration tool hoặc operator sở hữu session dừng đúng cách.

`pg_cancel_backend(pid)` yêu cầu hủy query hiện tại. `pg_terminate_backend(pid)` kết thúc session và có thể làm transaction rollback nếu chưa commit. Cả hai đều có tác động; dùng theo runbook và quyền được phê duyệt.

## 8. Transactional DDL trong PostgreSQL

Nhiều thao tác DDL của PostgreSQL có thể chạy bên trong transaction block. Nếu một statement lỗi trong transaction, transaction thường chuyển sang trạng thái aborted và cần ROLLBACK.

Ví dụ:

~~~sql
BEGIN;

ALTER TABLE public.orders
    ADD COLUMN source_channel text;

CREATE TABLE public.migration_audit_demo (
    id bigint PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now()
);

COMMIT;
~~~

Nếu CREATE TABLE thất bại trước COMMIT, có thể ROLLBACK toàn transaction và các thay đổi transactional sẽ không được commit.

### Transactional migration

Ưu điểm:

- Nhiều DDL có thể commit cùng nhau.
- Nếu một bước lỗi, rollback transaction có thể đưa schema về trạng thái trước.
- Ledger có thể được cập nhật cùng transaction nếu tool thiết kế như vậy.

Giới hạn:

- Transaction lớn giữ locks lâu.
- DDL có thể chờ blockers.
- Data backfill lớn làm transaction kéo dài, tăng WAL và giữ dead tuples.
- Không phải mọi lệnh đều được phép trong transaction block.
- Tool có thể chia migration thành nhiều transaction hoặc chạy statement riêng.

Không suy luận migration có tính atomic chỉ từ việc tool gọi nó là “migration”.

## 9. DDL không chạy trong transaction block

Một số thao tác PostgreSQL không được phép chạy bên trong transaction block. Ví dụ điển hình:

- `CREATE INDEX CONCURRENTLY`.
- `DROP INDEX CONCURRENTLY`.
- `VACUUM`.
- `CREATE DATABASE`.
- `DROP DATABASE`.
- `REINDEX ... CONCURRENTLY` trong các phiên bản có hỗ trợ.
- Một số thao tác quản trị hoặc extension-specific.

Danh sách chính xác phụ thuộc command và PostgreSQL version.

Nếu migration chứa non-transactional statement, một script nhiều bước có thể để lại trạng thái một phần khi statement sau thất bại.

### Ví dụ

~~~sql
CREATE INDEX CONCURRENTLY orders_created_at_idx
ON public.orders (created_at);

ALTER TABLE public.orders
ADD CONSTRAINT orders_channel_check
CHECK (source_channel IS NULL OR source_channel IN ('web', 'mobile'));
~~~

Index có thể đã được tạo thành công trước khi ALTER TABLE lỗi. Chạy lại toàn script có thể gặp lỗi index đã tồn tại. Cần kiểm tra từng object trước khi retry.

## 10. Index invalid sau CREATE INDEX CONCURRENTLY

`CREATE INDEX CONCURRENTLY` giảm thời gian giữ lock ngăn ghi so với tạo index thông thường, nhưng quy trình build phức tạp và có thể để lại index invalid nếu thất bại.

Kiểm tra:

~~~sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indrelid::regclass AS table_name,
    i.indisvalid,
    i.indisready,
    i.indislive,
    pg_get_indexdef(i.indexrelid) AS definition
FROM pg_index AS i
WHERE i.indrelid = 'public.orders'::regclass
ORDER BY i.indexrelid::regclass::text;
~~~

Nếu index invalid:

1. Xác nhận migration ID và log lỗi.
2. Kiểm tra có session CREATE INDEX còn chạy hay không.
3. Xác định index có được ứng dụng/query phụ thuộc không.
4. Kiểm tra definition và tablespace.
5. Lập kế hoạch drop/rebuild theo lock/capacity.
6. Xác minh index valid/ready sau khi build.
7. Chỉ cập nhật migration ledger sau khi trạng thái đúng.

Ví dụ drop invalid index:

~~~sql
DROP INDEX CONCURRENTLY IF EXISTS public.orders_created_at_idx;
~~~

Lệnh này không chạy trong transaction block thông thường. Chỉ thực hiện sau khi xác nhận đúng index và đã đánh giá dependency.

Không xóa mọi index invalid tự động. Một số trạng thái cần phân tích kỹ, đặc biệt khi build còn đang chạy hoặc index được tạo bởi quy trình khác.

## 11. Constraint NOT VALID và validation dở dang

PostgreSQL cho phép thêm một số CHECK/FOREIGN KEY constraints bằng `NOT VALID`, sau đó validate riêng:

~~~sql
ALTER TABLE public.orders
ADD CONSTRAINT orders_amount_nonnegative
CHECK (total_amount >= 0) NOT VALID;
~~~

Constraint mới được áp dụng cho các rows mới/được cập nhật theo semantics của PostgreSQL, trong khi dữ liệu cũ chưa được kiểm tra đầy đủ.

Sau đó:

~~~sql
ALTER TABLE public.orders
VALIDATE CONSTRAINT orders_amount_nonnegative;
~~~

Kiểm tra trạng thái:

~~~sql
SELECT
    conname,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'public.orders'::regclass;
~~~

Nếu validation thất bại do dữ liệu cũ vi phạm, constraint có thể vẫn tồn tại ở trạng thái NOT VALID. Không drop constraint ngay nếu nó đang bảo vệ dữ liệu mới. Tìm rows vi phạm, sửa dữ liệu theo nghiệp vụ rồi chạy lại validation.

Ví dụ tìm rows không đạt CHECK:

~~~sql
SELECT *
FROM public.orders
WHERE total_amount < 0;
~~~

Với foreign key, tìm orphan rows bằng LEFT JOIN/NOT EXISTS theo key tương ứng. Sau khi xử lý, validate lại và xác nhận `convalidated = true`.

## 12. ENUM và các thao tác có giới hạn transaction

PostgreSQL hỗ trợ `ALTER TYPE ... ADD VALUE`, nhưng khả năng sử dụng giá trị enum mới trong cùng transaction phụ thuộc version và trạng thái transaction. Ở các version hiện đại, giá trị mới được thêm trong transaction chưa thể dùng cho tới khi transaction commit.

Ví dụ:

~~~sql
ALTER TYPE order_status ADD VALUE 'archived';
~~~

Nếu migration tiếp theo trong cùng transaction cố INSERT giá trị `archived`, có thể gặp lỗi theo version/transaction context.

Quy trình an toàn:

1. Kiểm tra PostgreSQL major version.
2. Tách bước thêm enum value khỏi bước dùng giá trị mới nếu cần.
3. Commit bước DDL trước.
4. Chạy data migration sau khi enum value đã khả dụng.
5. Xác minh `pg_enum` và application compatibility.

Không xóa/đổi enum label một cách tùy tiện; thao tác đó có thể không được hỗ trợ trực tiếp hoặc cần chuyển đổi type/cột có kế hoạch.

## 13. Phát hiện schema drift

Schema drift có thể được phát hiện bằng nhiều nguồn:

- Migration history.
- `pg_catalog` và `information_schema`.
- Schema dump.
- Migration tool diff.
- Configuration management.
- Deployment artifacts.
- Monitoring/extension inventory.

### Kiểm tra column inventory

~~~sql
SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type,
    udt_name,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, ordinal_position;
~~~

Đối chiếu column name/type/nullability/default. `data_type` không phải lúc nào cũng đủ phân biệt domain, enum, array và các type đặc biệt; dùng `udt_name` hoặc catalog khi cần.

### Kiểm tra table inventory

~~~sql
SELECT
    schemaname,
    tablename,
    tableowner
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename;
~~~

### Kiểm tra indexes

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename, indexname;
~~~

### Kiểm tra constraints

~~~sql
SELECT
    conrelid::regclass AS table_name,
    conname,
    contype,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE connamespace NOT IN (
    'pg_catalog'::regnamespace,
    'information_schema'::regnamespace
)
ORDER BY conrelid::regclass::text, conname;
~~~

### Schema dump

Có thể dùng `pg_dump --schema-only` với client tools phù hợp để tạo snapshot schema:

~~~bash
pg_dump --schema-only --no-owner --no-privileges -d appdb > schema.sql
~~~

Để so sánh chính xác, cần chuẩn hóa các yếu tố không liên quan như owner, grants, object ordering, version-specific formatting và environment-specific settings. Đừng xóa khác biệt quan trọng bằng cách normalize quá mạnh.

## 14. Schema drift không chỉ là tables và columns

Một schema có thể trông giống nhau ở cấp table nhưng vẫn khác ở các yếu tố:

- Index definition, predicate, included columns và validity.
- Constraint definitions và validation state.
- Sequence options/current state.
- Column identity/generated/default behavior.
- Trigger definitions và enable state.
- Function/procedure source, owner, SECURITY DEFINER và search_path.
- View/materialized view definitions.
- Type/domain/enum definitions.
- Collation/provider.
- Partition bounds và attachment state.
- RLS enable/force flags và policies.
- Ownership, grants, role memberships và default privileges.
- Extension names/versions.
- Tablespaces và storage parameters.
- Event triggers và publication/subscription definitions.

Schema comparison cần định nghĩa rõ scope. Nếu chỉ so sánh tables/columns, gọi đó là structural subset comparison, không phải full schema equivalence.

## 15. So sánh schema giữa environments

Một quy trình so sánh:

1. Xác định source/target environment và version.
2. Chụp schema snapshot ở cả hai phía.
3. Chọn scope: database, schema, table hay object class.
4. Chuẩn hóa khác biệt có chủ đích.
5. So sánh definitions và security metadata.
6. Nhóm drift thành missing, extra, modified và state mismatch.
7. Phân loại drift: expected, accidental, unknown.
8. Xác định nguồn thay đổi và change record.
9. Chọn repair migration hoặc documented exception.
10. Chạy verification lại sau khi đồng bộ.

Không tự động apply mọi diff từ staging sang production. Production có thể có dữ liệu, grants hoặc object đặc thù được quản lý riêng.

### Các loại drift

| Loại | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Missing object | Thiếu index/cột | Xác minh migration và tạo repair migration |
| Extra object | DBA tạo index thủ công | Xác định owner/purpose; đưa vào migration hoặc exception |
| Definition mismatch | Type/default/index predicate khác | Review tác động dữ liệu và query |
| State mismatch | Index invalid, constraint NOT VALID | Hoàn tất build/validation |
| Security drift | Grants/owner/RLS khác | Khôi phục least privilege |
| Version drift | Extension/config khác | Đồng bộ package/config theo plan |
| Data drift | Backfill thiếu rows | Reconciliation và repair data |

## 16. Vì sao không sửa schema trực tiếp rồi bỏ migration history?

Hotfix trực tiếp bằng SQL có thể cần thiết trong incident, nhưng nếu không được ghi lại, các môi trường sau sẽ tiếp tục drift.

Sau hotfix:

1. Lưu command và evidence.
2. Ghi change/incident ID.
3. Xác minh trạng thái database.
4. Tạo migration tương ứng hoặc repair migration có precondition phù hợp.
5. Đảm bảo migration không phá hủy thay đổi đã thực hiện.
6. Đồng bộ các environments còn lại theo thứ tự.
7. Cập nhật migration ledger bằng cơ chế chính thức nếu cần.
8. Review checksum và deployment pipeline.

Không tạo migration “giả” chỉ để làm ledger xanh nếu database chưa đạt trạng thái mong muốn.

## 17. Idempotency và retry safety

Một migration idempotent có thể chạy lại mà không tạo thêm tác động ngoài dự kiến. Tuy nhiên, `IF EXISTS`/`IF NOT EXISTS` không tự bảo đảm schema đúng.

Ví dụ:

~~~sql
ALTER TABLE public.orders
ADD COLUMN IF NOT EXISTS source_channel text;
~~~

Nếu column đã tồn tại nhưng type là integer hoặc default sai, lệnh không sửa mismatch đó.

### Kiểm tra definition sau IF NOT EXISTS

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

Migration cần precondition/postcondition rõ:

- Nếu object không tồn tại: tạo.
- Nếu tồn tại đúng definition: xem là đã đạt.
- Nếu tồn tại nhưng khác definition: dừng và điều tra.
- Nếu object ở trạng thái invalid/partial: dùng recovery branch riêng.

### Retry-safe data migration

Ví dụ backfill theo điều kiện:

~~~sql
UPDATE public.orders
SET source_channel = 'web'
WHERE source_channel IS NULL
  AND created_at < DATE '2026-01-01';
~~~

Điều kiện `IS NULL` giúp giảm việc ghi lại rows đã xử lý, nhưng chỉ phù hợp nếu NULL thực sự có nghĩa “chưa backfill” và giá trị `web` đúng theo business rule. Không dùng sentinel values tùy tiện nếu NULL là giá trị nghiệp vụ hợp lệ.

## 18. Migration locking và chạy đồng thời

Hai deployment chạy cùng migration có thể gây:

- Duplicate object errors.
- Deadlocks.
- Ledger race conditions.
- DDL lock contention.
- Data backfill chạy hai lần.
- Partial state khó xác định.

Migration framework nên có lock hoặc advisory lock để chỉ một migration runner hoạt động tại một thời điểm cho một database/schema.

PostgreSQL advisory locks có thể dùng để điều phối:

~~~sql
SELECT pg_advisory_lock(81420, 1);
-- Thực hiện migration orchestration theo quy trình.
SELECT pg_advisory_unlock(81420, 1);
~~~

Đây là ví dụ key minh họa. Chọn key namespace ổn định và kiểm tra lock ownership/session lifecycle. Session-level advisory lock được giữ tới khi unlock hoặc session kết thúc. Transaction-level advisory lock có semantics khác.

Advisory lock không thay thế migration ledger hoặc lock của tool; cần đảm bảo tất cả runner tuân thủ cùng một cơ chế.

### Kiểm tra advisory locks

~~~sql
SELECT
    pid,
    locktype,
    classid,
    objid,
    objsubid,
    granted
FROM pg_locks
WHERE locktype = 'advisory';
~~~

Nếu migration runner disconnect, session-level lock thường được giải phóng khi session kết thúc. Tuy nhiên, không giả định migration state đã rollback chỉ vì lock biến mất.

## 19. Lock timeout và migration timeout

DDL có thể chờ lock do transaction dài. Dùng timeout để migration fail nhanh và dễ kiểm soát:

~~~sql
SET lock_timeout = '5s';
SET statement_timeout = '15min';
~~~

Giá trị chỉ minh họa. Có thể đặt trong migration transaction hoặc session theo policy.

- `lock_timeout`: giới hạn thời gian chờ lock.
- `statement_timeout`: giới hạn thời gian thực thi statement.
- `idle_in_transaction_session_timeout`: giới hạn session idle trong transaction.

Nếu lock timeout xảy ra, statement có thể bị hủy. Kiểm tra transaction state và catalog trước khi retry.

Không đặt statement_timeout quá ngắn cho migration tạo index/backfill lớn. Ngược lại, không để DDL chờ vô hạn trong production mà không có stop condition.

## 20. Expand-contract: triển khai tương thích nhiều phiên bản

Expand-contract là chiến lược thay đổi schema theo nhiều giai đoạn để application cũ và mới cùng hoạt động trong thời gian chuyển tiếp.

Ví dụ đổi `customer_name` sang `display_name`.

### Giai đoạn Expand

- Thêm column mới nullable.
- Giữ column cũ.
- Application mới có thể đọc cả hai hoặc ghi song song theo policy.
- Backfill dữ liệu cũ theo batch.
- Theo dõi consistency.

### Giai đoạn Migrate

- Chuyển application đọc column mới.
- Đảm bảo mọi writer đã cập nhật column mới.
- Kiểm tra dữ liệu cũ/mới đồng nhất.
- Theo dõi các instance ứng dụng cũ còn tồn tại.

### Giai đoạn Contract

- Dừng đọc/ghi column cũ.
- Xác nhận không còn consumer phụ thuộc.
- Drop column cũ trong change riêng.
- Cập nhật schema contract và migration ledger.

~~~mermaid
flowchart LR
    A["Expand: add new column"] --> B["Backfill + dual compatibility"]
    B --> C["Migrate app reads/writes"]
    C --> D["Observe old app instances = 0"]
    D --> E["Contract: remove old column"]
~~~

Không drop column ngay trong cùng deployment đã thêm column mới. Các phiên bản ứng dụng cũ có thể vẫn chạy trong rolling deployment hoặc rollback window.

## 21. Backfill dữ liệu lớn theo batch

Một UPDATE toàn bảng có thể tạo transaction dài, WAL lớn, lock duration cao và replication lag. Chia batch giúp kiểm soát tải và có thể tiếp tục từ checkpoint.

Ví dụ theo khóa tăng dần:

~~~sql
UPDATE public.orders
SET normalized_code = upper(code)
WHERE order_id > 100000
  AND order_id <= 110000
  AND normalized_code IS NULL;
~~~

Đây là ví dụ range cố định; production runner cần truyền key range bằng bind parameters và tính progress từ rows thực tế.

Mỗi batch cần:

- Transaction ngắn.
- Batch range rõ.
- Row count cập nhật.
- Checkpoint/progress record.
- Retry policy.
- Throttle khi replication lag hoặc latency vượt ngưỡng.
- Reconciliation sau khi hoàn tất.

### Vì sao checkpoint của backfill phải bền vững?

Nếu runner ghi progress trước khi commit data, process crash có thể đánh dấu batch hoàn tất dù dữ liệu chưa commit. Nếu ghi progress sau commit nhưng không atomic, có thể phải chạy lại batch. Thiết kế idempotent và transaction coordination để đảm bảo retry an toàn.

Một pattern là cập nhật dữ liệu và migration progress trong cùng transaction nếu cả hai ở cùng database và không có non-transactional operation xen giữa.

## 22. Migration ledger và data progress

Với migration dài, tách migration version khỏi progress chi tiết:

- Migration ledger: migration đã hoàn thành hay chưa.
- Backfill progress table: batch/key range đã xử lý tới đâu.
- Reconciliation result: số rows còn thiếu hoặc sai.
- Deployment state: application version đã chuyển chưa.

Ví dụ progress table:

~~~sql
CREATE TABLE IF NOT EXISTS ops_migration_progress (
    migration_key text PRIMARY KEY,
    last_processed_id bigint,
    rows_processed bigint NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now()
);
~~~

Không dùng bảng ví dụ này thay ledger của framework nếu tool đã có cơ chế progress. Bảo vệ bảng ops khỏi application role thông thường.

## 23. Xử lý migration chạy một phần

Giả sử migration có ba bước:

1. Add column.
2. Backfill data.
3. Add constraint.

Nếu bước 3 lỗi, cần kiểm tra:

- Column đã tồn tại và definition đúng chưa?
- Backfill đã chạy toàn bộ hay một phần?
- Có rows vi phạm constraint không?
- Có trigger/default làm phát sinh dữ liệu mới không?
- Migration ledger ghi trạng thái nào?
- Application đang đọc/ghi column nào?

### Recovery branch

- Column đúng, backfill hoàn tất, constraint chưa có: chạy riêng bước tạo/validate constraint sau khi xử lý dữ liệu.
- Column đúng, backfill một phần: tiếp tục từ progress marker hoặc chạy lại batch idempotent.
- Column tồn tại nhưng type/default sai: dừng, đánh giá data conversion và tạo repair migration.
- Ledger ghi success nhưng constraint thiếu: schema drift; tạo repair migration có precondition.
- Không biết dữ liệu đã biến đổi ra sao: giữ writes/traffic theo incident plan, thu thập snapshot và escalate trước khi sửa.

Không xóa column và chạy lại từ đầu nếu application hoặc dữ liệu mới đã phụ thuộc vào nó.

## 24. Rollback hay forward-fix?

Chọn phương án dựa trên khả năng đảo ngược và dữ liệu đã phát sinh.

| Tình trạng | Hướng xử lý thường cân nhắc |
| --- | --- |
| Transactional migration lỗi trước commit | Rollback transaction và sửa migration |
| DDL đã commit, chưa có application phụ thuộc | Có thể rollback bằng migration ngược đã kiểm chứng |
| Backfill đã cập nhật dữ liệu | Forward-fix hoặc restore/reconcile; không giả định đảo ngược đơn giản |
| Index concurrently invalid | Drop/rebuild theo runbook |
| Constraint NOT VALID | Sửa dữ liệu rồi validate hoặc xử lý constraint theo policy |
| App mới chạy với schema cũ | Roll forward schema nếu tương thích, hoặc rollback app theo plan |
| Schema mới chạy với app cũ | Dùng expand-compatible design hoặc rollback app/database có kiểm soát |
| Target đã nhận writes mới | Cần reverse sync/reconciliation trước khi quay về source |
| Data corruption hoặc loss không xác định | Dừng thao tác, bảo toàn evidence, recovery từ backup/PITR theo incident command |

### Rollback migration không phải luôn là “down script”

Một down migration có thể:

- Drop column đã có dữ liệu mới.
- Mất dữ liệu đã backfill.
- Không khôi phục chính xác giá trị cũ.
- Không thể drop enum value.
- Không đảo ngược external side effects.
- Tạo lock/downtime lớn.

Trước khi chạy down migration, xác định rõ data loss và compatibility.

## 25. Khi nào dùng forward-fix?

Forward-fix thường phù hợp khi:

- Migration đã commit một phần và có dữ liệu mới phụ thuộc.
- DDL ngược có nguy cơ mất dữ liệu.
- Ứng dụng mới đã ghi dữ liệu theo schema mới.
- Việc restore sẽ làm mất các transaction hợp lệ.
- Schema có thể được đưa tới trạng thái đúng bằng một migration bổ sung.

Một forward-fix nên có version/ID riêng, preconditions, repair steps và postconditions. Không chỉnh file migration cũ đã triển khai để “sửa lịch sử”, vì checksum và reproducibility sẽ bị phá vỡ.

## 26. Schema drift do thao tác thủ công

Trong incident, DBA có thể thêm index hoặc column trực tiếp để khôi phục dịch vụ. Việc đó có thể hợp lý trong tình huống khẩn cấp, nhưng cần đưa thay đổi vào source of truth sau đó.

Quy trình:

1. Ghi lại exact SQL đã chạy.
2. Chụp catalog state sau hotfix.
3. Xác định lý do và change/incident ID.
4. So sánh với migration repository.
5. Tạo repair migration có precondition.
6. Đảm bảo migration chấp nhận object đã tồn tại đúng hoặc dừng nếu definition khác.
7. Test trên bản sao/staging.
8. Triển khai tới các environment còn drift.
9. Xác minh schema và ledger.
10. Ghi exception nếu production object được giữ ngoài migration ownership.

Không chạy lại DDL thủ công trên mọi environment mà không xác định khác biệt hiện tại.

## 27. Kiểm tra migration checksum mismatch

Migration checksum mismatch thường có nghĩa file migration đã thay đổi sau khi tool ghi nhận nó đã chạy, hoặc môi trường có artifact khác nhau.

Nguyên nhân:

- Developer chỉnh migration cũ.
- Build artifact không giống artifact đã deploy.
- Encoding/line endings thay đổi.
- Branch merge làm nội dung file khác.
- Tool version/algorithm thay đổi theo cấu hình.

Cách xử lý:

1. Lấy artifact đã deploy và repository version.
2. So sánh nội dung migration.
3. Xác định migration nào đã chạy ở môi trường nào.
4. Không sửa checksum trực tiếp trong database.
5. Tạo migration mới cho thay đổi mong muốn.
6. Dùng repair/baseline chính thức của tool chỉ khi trạng thái schema đã được xác minh và policy cho phép.

Checksum mismatch không nhất thiết chứng minh schema sai, nhưng là dấu hiệu lịch sử triển khai không còn reproducible.

## 28. Quản lý application version khi schema đang ở trạng thái trung gian

Rolling deployments có thể khiến nhiều phiên bản application cùng truy cập database.

Cần phân loại compatibility:

| Application version | Schema cũ | Schema expand | Schema contract |
| --- | --- | --- | --- |
| App cũ | Hỗ trợ | Phải tương thích | Có thể lỗi |
| App bridge | Có thể hỗ trợ | Hỗ trợ | Không nên dùng sau contract |
| App mới | Có thể hỗ trợ nếu thiết kế | Hỗ trợ | Hỗ trợ |

Trước khi contract:

- Xác nhận tất cả app instances đã nâng.
- Xác nhận worker/cron/ETL đã nâng.
- Xác nhận scripts và ad-hoc consumers.
- Kiểm tra prepared statements/long-lived sessions.
- Kiểm tra rollback window đã kết thúc.
- Kiểm tra metrics không còn truy cập column/object cũ.

Không chỉ dựa vào version tag của deployment controller; có thể còn process cũ hoặc scheduled job chưa restart.

## 29. Migration và connection pools

Connection pools giữ session lâu và có thể giữ prepared statements, cached metadata hoặc transaction state.

Sau schema migration:

- Kiểm tra app có thể prepare statement mới.
- Kiểm tra prepared statements cũ có lỗi do column/type thay đổi không.
- Kiểm tra pool recycle policy.
- Xác nhận session không ở trạng thái idle in transaction.
- Không terminate mọi connection theo cách đột ngột nếu không có plan.
- Nếu cần restart pool, phối hợp drain/reconnect để tránh connection storm.

Một số schema changes có thể khiến prepared statements bị invalidation/replan theo behavior PostgreSQL/driver. Kiểm tra bằng application logs và test đúng driver version.

## 30. Migration và replication

DDL trên primary thường được gửi qua physical WAL streaming tới physical standby. Logical replication có các giới hạn khác: DDL không tự động được replicate như row changes trong nhiều setup.

Sau migration:

- Kiểm tra physical standby replay và lag.
- Kiểm tra logical subscriber schema parity.
- Kiểm tra publication/subscription errors.
- Xác minh table sync state.
- Xác định sequence sync riêng.
- Kiểm tra replication slots và WAL retention.
- Xác minh failover candidate có schema/data state đúng.

Không promote standby đang lag hoặc chưa có schema state cần thiết mà không đánh giá RPO và tác động.

## 31. Dùng advisory lock để ngăn migration chạy đồng thời

Migration framework nên cung cấp lock. Nếu tự xây runner, có thể dùng PostgreSQL advisory locks.

Session-level example:

~~~sql
SELECT pg_advisory_lock(91002, 1);
-- Runner kiểm tra ledger và thực hiện migration.
SELECT pg_advisory_unlock(91002, 1);
~~~

Transaction-level example:

~~~sql
BEGIN;
SELECT pg_advisory_xact_lock(91002, 1);
-- Các bước transactional migration.
COMMIT;
~~~

Chọn đúng loại lock:

- Session-level lock giữ tới unlock hoặc session end.
- Transaction-level lock tự giải phóng khi transaction kết thúc.
- Tất cả runner cần dùng cùng key convention.
- Không để operator chạy migration thủ công ngoài lock policy.

Advisory lock không tự bảo đảm transaction safety, migration ordering hoặc schema correctness.

## 32. Migration precondition và postcondition

Một migration tốt kiểm tra trạng thái trước khi thay đổi và xác minh trạng thái sau thay đổi.

Ví dụ precondition:

~~~sql
SELECT
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'orders'
  AND column_name = 'source_channel';
~~~

Kết quả phải khớp trạng thái mong đợi trước migration.

Postcondition:

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

Kiểm tra index:

~~~sql
SELECT
    indexrelid::regclass,
    indisvalid,
    indisready,
    pg_get_indexdef(indexrelid)
FROM pg_index
WHERE indexrelid = 'public.orders_created_at_idx'::regclass;
~~~

Kiểm tra constraint:

~~~sql
SELECT
    conname,
    convalidated,
    pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'public.orders'::regclass;
~~~

Precondition/postcondition không nhất thiết phải là SQL trong migration file; có thể là tool assertion hoặc deployment gate. Điều quan trọng là trạng thái được kiểm tra và kết quả được lưu.

## 33. Migration data có tính idempotent

Một data migration nên được thiết kế để retry an toàn khi có thể.

Ví dụ backfill dùng key range và progress table:

~~~sql
BEGIN;

UPDATE public.orders
SET normalized_code = upper(code)
WHERE order_id > 100000
  AND order_id <= 110000
  AND normalized_code IS NULL;

INSERT INTO ops_migration_progress (
    migration_key,
    last_processed_id,
    rows_processed
)
VALUES ('orders-normalized-code-v1', 110000, 10000)
ON CONFLICT (migration_key)
DO UPDATE SET
    last_processed_id = EXCLUDED.last_processed_id,
    rows_processed = ops_migration_progress.rows_processed
                     + EXCLUDED.rows_processed,
    updated_at = now();

COMMIT;
~~~

Đây là ví dụ minh họa; `rows_processed` cần được tính từ số rows thực tế đã update thay vì dùng một con số cố định trong migration production. Dùng GET DIAGNOSTICS ROW_COUNT trong PL/pgSQL hoặc lấy command tag từ runner để ghi chính xác.

Đảm bảo progress update và data update nằm trong cùng transaction nếu muốn atomic checkpoint. Nếu không thể, thiết kế lại để chạy lại batch không gây sai dữ liệu.

## 34. Xử lý data migration có side effects

Một migration có thể gọi trigger, ghi audit rows, phát notification hoặc tương tác hệ thống ngoài database. Retry có thể lặp side effects.

Trước khi retry:

- Xác định triggers đang bật.
- Xác định function có external calls/notifications không.
- Xác định outbox/queue records đã được tạo chưa.
- Xác định consumer đã xử lý message chưa.
- Dùng idempotency key/deduplication.
- Có reconciliation cho side effects.

Tránh gọi external API trực tiếp trong transaction migration dài. Dùng outbox hoặc quy trình riêng nếu cần đồng bộ external systems.

## 35. Phục hồi partial deployment giữa database và application

Một quy trình deploy có thể gồm:

1. Expand schema.
2. Deploy application mới.
3. Backfill.
4. Chuyển reads/writes.
5. Contract schema.

Nếu bước 2 lỗi sau bước 1, schema expand thường được thiết kế để app cũ vẫn chạy. Khi đó có thể rollback application và giữ schema expand, miễn là tương thích.

Nếu bước 4 lỗi sau khi application mới đã ghi dữ liệu, rollback app cần bảo đảm code cũ hiểu được dữ liệu đã ghi. Nếu không, cần forward-fix app/schema hoặc restore/reconcile.

### Ma trận recovery

| Database | Application | Trạng thái | Hướng cân nhắc |
| --- | --- | --- | --- |
| Schema cũ | App cũ | Bình thường | Tiếp tục deploy theo plan |
| Schema expand | App cũ | Chưa deploy app mới | Có thể giữ expand, điều tra deploy |
| Schema expand | App mới | Bridge phase | Xác minh dual-read/write |
| Schema contract | App cũ | Không tương thích | Dừng traffic/roll forward hoặc recovery |
| Schema mới | App deploy một phần | Mixed versions | Giữ compatibility hoặc drain old instances |
| Schema mới | App mới nhưng lỗi | Partial cutover | Forward-fix hoặc rollback theo data compatibility |

## 36. DDL lock impact và migration failure

Một DDL có thể chờ hoặc yêu cầu lock mạnh. Trước migration:

- Kiểm tra long-running transactions.
- Xác định lock mode cần thiết.
- Ước lượng table size.
- Xác định rewrite behavior.
- Đặt lock_timeout hợp lý.
- Chạy trong maintenance window nếu cần.
- Theo dõi pg_stat_activity và pg_locks.
- Có stop condition khi wait vượt ngưỡng.

Không cho rằng ALTER TABLE luôn tức thời. Một số thay đổi metadata-only trong version/điều kiện nhất định, nhưng một số thay đổi cần rewrite table hoặc scan dữ liệu.

### Theo dõi lock

~~~sql
SELECT
    a.pid,
    a.application_name,
    a.state,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name,
    a.wait_event_type,
    a.wait_event,
    left(a.query, 180) AS query_sample
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
    ON a.pid = l.pid
WHERE l.relation IS NOT NULL
ORDER BY l.granted, a.pid;
~~~

Kết quả cần được diễn giải theo lock mode và relation. Không terminate blocker chỉ vì nó xuất hiện trong query; xác định owner và business impact.

## 37. Phân loại lỗi bằng SQLSTATE và logs

Một số SQLSTATE hữu ích:

| SQLSTATE | Ý nghĩa | Hướng điều tra |
| --- | --- | --- |
| 42P01 | undefined_table | Object thiếu hoặc search_path sai |
| 42703 | undefined_column | Migration chưa chạy hoặc code/schema lệch |
| 42701 | duplicate_column | Column đã tồn tại hoặc migration chạy một phần |
| 42P07 | duplicate_table | Table đã tồn tại |
| 42P16 | invalid_table_definition | DDL definition không hợp lệ |
| 23505 | unique_violation | Duplicate data/index/constraint |
| 23503 | foreign_key_violation | Referential integrity |
| 23514 | check_violation | Dữ liệu vi phạm CHECK |
| 40P01 | deadlock_detected | Transaction lock cycle |
| 55P03 | lock_not_available | Lock không lấy được |
| 57014 | query_canceled | Statement bị cancel/timeout |
| 53100 | disk_full | Filesystem/storage capacity |
| 42501 | insufficient_privilege | Role thiếu quyền |
| 55006 | object_in_use | Object đang được sử dụng |

SQLSTATE là căn cứ phân loại tốt hơn việc parse message text. Message, detail và context vẫn cần lưu để hiểu object và câu lệnh cụ thể.

## 38. Kiểm tra disk, WAL và temporary files khi migration lỗi

Migration có thể thất bại do storage exhaustion. Kiểm tra:

~~~sql
SELECT
    pg_size_pretty(pg_database_size(current_database())) AS current_database_size;
~~~

Xem temp usage:

~~~sql
SELECT
    datname,
    temp_files,
    pg_size_pretty(temp_bytes) AS temp_written
FROM pg_stat_database
ORDER BY temp_bytes DESC;
~~~

Kiểm tra WAL archive:

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

Filesystem free space phải được xác minh ở OS/storage layer cho data, WAL, temp, logs và backup volumes. Không xóa file trong pg_wal bằng filesystem command để giải phóng dung lượng; xử lý replication slots/archive và WAL retention theo runbook.

## 39. Migration và extension upgrades

Extension upgrade có thể thất bại vì:

- Extension package cho target major version chưa được cài.
- Shared library không tương thích.
- Upgrade SQL script thiếu hoặc không có đường upgrade trực tiếp.
- Dependency extension chưa nâng.
- Object ownership/permission không đủ.
- Extension update chạy một phần hoặc có transaction behavior riêng.

Kiểm tra:

~~~sql
SELECT
    extname,
    extversion,
    extnamespace::regnamespace AS extension_schema
FROM pg_extension
ORDER BY extname;
~~~

Xem các version có sẵn:

~~~sql
SELECT
    name,
    default_version,
    installed_version
FROM pg_available_extensions
ORDER BY name;
~~~

Không drop/recreate extension để “sửa nhanh” nếu extension sở hữu objects hoặc lưu metadata. Dùng upgrade path chính thức của extension và backup/restore plan.

## 40. Migration trong nhiều database hoặc nhiều tenant

Một ứng dụng có thể có nhiều database, schema-per-tenant hoặc tenant databases riêng. Migration có thể thành công ở một nhóm và thất bại ở nhóm khác.

Cần một deployment inventory:

| Tenant/DB | Current version | Target version | Status | Last result |
| --- | --- | --- | --- | --- |
| tenant_a | 041 | 042 | complete | success |
| tenant_b | 041 | 042 | failed | lock timeout |
| tenant_c | 041 | 042 | pending | not started |

Các trạng thái phải lấy từ ledger/tool và verification query. Không chỉ dựa vào deployment controller đã gửi command.

Quy trình:

1. Freeze hoặc giới hạn migration concurrency theo capacity.
2. Ghi danh sách target.
3. Chạy từng batch tenant.
4. Lưu kết quả riêng từng database.
5. Dừng batch khi lỗi vượt ngưỡng.
6. Phân loại tenant complete/partial/pending.
7. Recovery theo từng trạng thái.
8. Chỉ bật feature toàn bộ khi coverage đạt acceptance criteria.

Không giả định một migration thành công trên tenant đầu tiên có nghĩa các tenant khác cũng tương tự.

## 41. Repair migration an toàn

Repair migration là migration mới để đưa schema/data từ trạng thái hiện tại về trạng thái mong muốn.

Một repair migration nên có:

- ID/version mới.
- Mô tả drift cần sửa.
- Preconditions chứng minh trạng thái đầu vào.
- Thao tác sửa.
- Postconditions.
- Lock/downtime impact.
- Data loss implications.
- Retry/idempotency policy.
- Evidence và owner.
- Rollback/forward-fix plan.

Ví dụ, nếu index đúng definition đã tồn tại nhưng migration ledger chưa ghi nhận, repair process có thể kiểm tra definition/validity trước rồi dùng migration tool baseline/repair theo policy. Không chỉ dùng CREATE INDEX IF NOT EXISTS, vì index cùng tên có thể khác definition.

## 42. Quy trình điều tra schema drift

1. **Freeze thay đổi:** dừng migration runner/deployment có thể làm drift tăng.
2. **Identify:** xác định database, schema, object và application version.
3. **Collect:** lưu migration ledger, schema snapshot, logs và deployment artifacts.
4. **Compare:** so sánh catalog với source of truth.
5. **Classify:** missing, extra, modified, invalid state, security drift hoặc data drift.
6. **Trace:** tìm change record, operator, commit và thời điểm thay đổi.
7. **Decide:** giữ, xóa, sửa hoặc tạo repair migration.
8. **Test:** chạy repair trên staging/clone có trạng thái tương tự.
9. **Apply:** thực hiện theo change plan.
10. **Verify:** so sánh lại schema/data/security.
11. **Reconcile ledger:** dùng cơ chế chính thức của tool.
12. **Prevent:** khóa DDL thủ công hoặc ghi nhận exception có kiểm soát.

## 43. Runbook xử lý migration thất bại

### Giai đoạn A: Contain

- Dừng migration runner.
- Dừng bước deployment phụ thuộc.
- Giữ application ở phiên bản tương thích.
- Không chạy lại script.
- Bảo toàn logs và output.

### Giai đoạn B: Determine state

- Xác nhận target database/cluster.
- Xác định session và transaction.
- Đọc migration ledger.
- Kiểm tra catalog objects.
- Kiểm tra dữ liệu đã backfill.
- Kiểm tra index/constraint validity.
- Kiểm tra application versions.
- Kiểm tra replication/backup.

### Giai đoạn C: Choose recovery

- Rollback transaction nếu chưa commit.
- Retry đúng step nếu operation idempotent và precondition đạt.
- Drop/rebuild invalid index theo plan.
- Resume backfill từ progress checkpoint.
- Forward-fix schema/data nếu đã có dependency.
- Restore/PITR nếu data integrity không thể đảm bảo.
- Escalate nếu trạng thái không rõ.

### Giai đoạn D: Verify and close

- Schema khớp source of truth.
- Data reconciliation đạt.
- Ledger phản ánh đúng trạng thái.
- App/worker versions tương thích.
- Replication và backup hoạt động.
- Metrics và logs ổn định.
- Evidence và deviation được lưu.
- Reviewer sign-off.

## 44. Mẫu decision record

Khi chọn rollback hay forward-fix, ghi lại:

~~~yaml
change_id: CHG-2026-0579
migration_id: V042__add_order_channel
environment: production
database: sales
failure_at: "step 3 - validate constraint"
ledger_state: "failed"
observed_schema_state:
  column_exists: true
  column_type: text
  backfill_complete: true
  constraint_exists: true
  constraint_validated: false
observed_application_state:
  old_instances: 0
  new_instances: 24
decision: "forward_fix"
reason: "new application instances already write the new column"
recovery_action: "repair invalid rows, then validate constraint"
verification:
  data_check: pending
  constraint_validation: pending
  application_smoke_test: pending
owner: database_operations
~~~

Đây là ví dụ minh họa. Không đưa credentials, customer data hoặc hostnames nhạy cảm vào record. Cập nhật decision record theo kết quả thực tế, không ghi trước là thành công.

## 45. Evidence cần lưu

Một evidence package cho migration recovery nên gồm:

- Change/incident ID.
- Migration ID/version và checksum.
- Source control commit/build artifact.
- PostgreSQL version và cluster identity.
- Migration tool/version.
- Command, timestamp và operator.
- Error SQLSTATE/message/context.
- Migration ledger trước/sau.
- Catalog snapshot trước/sau.
- Data progress/reconciliation.
- Index/constraint state.
- Role/permission state nếu liên quan.
- Application versions và deployment status.
- Replication/backup status.
- Recovery decision và approvals.
- Rollback/forward-fix output.
- Post-checks và application smoke tests.
- Deviations và reviewer sign-off.

Evidence phải có timestamp/timezone, target environment và nguồn. Redact password, token, private key và query parameters nhạy cảm.

## 46. Ngăn schema drift trong tương lai

Các biện pháp phòng ngừa:

- Quản lý schema changes bằng version-controlled migrations.
- Chặn DDL thủ công bằng role separation, trừ break-glass process.
- Ghi lại hotfix và chuyển thành repair migration.
- Chạy migration trong deployment pipeline có single-runner lock.
- Thêm schema diff vào CI/staging gates.
- Kiểm tra migration từ version production thực tế, không chỉ từ empty database.
- Test upgrade path qua các version đang được hỗ trợ.
- Dùng expand-contract cho rolling deployments.
- Có migration ownership rõ.
- Theo dõi checksum/history.
- Định kỳ so sánh schema giữa environments.
- Duy trì backup/restore test.
- Có alert cho migration failure và schema drift quan trọng.

### CI migration testing

Pipeline có thể:

1. Tạo database từ baseline version.
2. Restore fixture hoặc representative dataset.
3. Chạy toàn bộ pending migrations.
4. Chạy schema assertions.
5. Chạy data assertions.
6. Chạy application integration tests.
7. Kiểm tra migration runtime/lock behavior.
8. Kiểm tra rollback hoặc recovery branch ở những migration có hỗ trợ.

Test từ empty database không đủ nếu production đang ở version N-3 và migration chỉ được thử từ latest baseline.

## 47. Những sai lầm thường gặp

1. **Retry migration ngay sau timeout**, trong khi server có thể đã commit một phần hoặc toàn bộ.
2. **Coi migration ledger là nguồn sự thật duy nhất**, bỏ qua catalog và dữ liệu.
3. **Sửa migration cũ đã triển khai**, phá checksum và reproducibility.
4. **UPDATE/DELETE ledger thủ công để hết lỗi**, làm metadata không phản ánh trạng thái schema.
5. **Cho rằng toàn bộ DDL đều transactional**, bỏ qua CREATE INDEX CONCURRENTLY và các lệnh bị cấm trong transaction block.
6. **Không kiểm tra index validity**, để index invalid tồn tại.
7. **Drop index invalid ngay lập tức**, không kiểm tra session/build/dependency.
8. **Coi constraint NOT VALID là hoàn tất**, bỏ qua dữ liệu cũ chưa được validate.
9. **Thêm enum value rồi dùng ngay trong cùng transaction**, không xét version/commit boundary.
10. **Dùng IF NOT EXISTS để che drift**, không kiểm tra object definition thực tế.
11. **Chạy hai migration runner đồng thời**, gây race/duplicate/lock conflicts.
12. **Không dùng lock_timeout**, để DDL chờ vô hạn và ảnh hưởng traffic.
13. **Terminate blocker mà không xác định owner và tác động**, có thể rollback transaction nghiệp vụ.
14. **Backfill toàn bảng trong một transaction**, tạo WAL, bloat, replication lag và lock pressure.
15. **Ghi progress trước commit dữ liệu**, khiến migration bỏ sót rows sau crash.
16. **Retry data migration có side effects**, tạo duplicate events hoặc external actions.
17. **Drop column cũ ngay trong rolling deployment**, làm app version cũ lỗi.
18. **Rollback application sau khi schema contract**, khiến code không còn tương thích.
19. **Quay về source sau khi target đã nhận writes**, làm mất dữ liệu mới.
20. **So sánh schema chỉ theo tables/columns**, bỏ qua grants, triggers, indexes, constraints và RLS.
21. **Apply toàn bộ schema diff từ staging sang production**, ghi đè khác biệt có chủ đích.
22. **Không kiểm tra replication và logical subscriptions**, để downstream schema/data lệch.
23. **Không ghi hotfix vào migration repository**, tạo drift tái diễn.
24. **Không giữ evidence và decision record**, khiến người nhận incident không biết trạng thái.
25. **Đóng deployment khi ledger xanh nhưng app chưa được kiểm tra**, bỏ sót lỗi runtime.
26. **Không test migration từ production baseline**, chỉ test database trống.
27. **Không phân biệt partial state với unknown state**, tiếp tục thao tác khi chưa đủ bằng chứng.

## 48. Bài tập thực hành có đáp án

### Bài 1. Migration failure là gì?

**Đáp án:** Migration không hoàn thành theo kế hoạch; database có thể chưa đổi, đổi một phần hoặc đã đổi nhưng client không nhận được kết quả.

### Bài 2. Schema drift là gì?

**Đáp án:** Schema thực tế khác schema được migration repository hoặc environment chuẩn mong đợi.

### Bài 3. Partial deployment là gì?

**Đáp án:** Database, application, worker hoặc environment chỉ triển khai được một phần và chưa đạt trạng thái tương thích cuối.

### Bài 4. Vì sao không retry ngay sau client timeout?

**Đáp án:** Server có thể đã commit lệnh trước khi response bị mất; retry có thể gây duplicate hoặc conflict.

### Bài 5. Migration ledger có phải nguồn sự thật duy nhất không?

**Đáp án:** Không. Phải đối chiếu ledger với catalogs, dữ liệu và application state.

### Bài 6. Flyway thường lưu history ở bảng nào?

**Đáp án:** Thường là flyway_schema_history, theo cấu hình/tool version.

### Bài 7. Vì sao không UPDATE migration ledger thủ công?

**Đáp án:** Có thể làm history/checksum/status không còn phản ánh schema thực tế; dùng repair/baseline chính thức sau khi xác minh.

### Bài 8. Nêu một DDL thường không chạy trong transaction block.

**Đáp án:** CREATE INDEX CONCURRENTLY.

### Bài 9. CREATE INDEX CONCURRENTLY thất bại có thể để lại gì?

**Đáp án:** Index invalid hoặc chưa ready trong catalog.

### Bài 10. Query nào kiểm tra index validity?

**Đáp án:** pg_index, đặc biệt indisvalid và indisready.

### Bài 11. NOT VALID constraint có nghĩa gì?

**Đáp án:** Constraint tồn tại nhưng dữ liệu cũ chưa được validate toàn bộ; hành vi áp dụng với dữ liệu mới theo constraint semantics.

### Bài 12. Làm sao hoàn tất validation?

~~~sql
ALTER TABLE public.orders
VALIDATE CONSTRAINT orders_amount_nonnegative;
~~~

**Đáp án:** Sau khi sửa dữ liệu vi phạm, chạy VALIDATE CONSTRAINT và xác minh convalidated = true.

### Bài 13. Vì sao cần commit trước khi dùng enum value mới vừa thêm?

**Đáp án:** Ở các version/transaction contexts liên quan, enum value mới chưa khả dụng cho tới khi transaction thêm nó commit.

### Bài 14. IF NOT EXISTS có bảo đảm object đúng definition không?

**Đáp án:** Không. Nó chỉ tránh lỗi tồn tại; cần kiểm tra type, default, owner và definition.

### Bài 15. Schema drift có những dạng nào?

**Đáp án:** Missing, extra, definition mismatch, invalid state, security drift, version drift và data drift.

### Bài 16. Vì sao cần migration lock?

**Đáp án:** Ngăn nhiều runner thực hiện cùng migration đồng thời và tạo race/partial state.

### Bài 17. lock_timeout khác statement_timeout thế nào?

**Đáp án:** lock_timeout giới hạn thời gian chờ lock; statement_timeout giới hạn tổng thời gian statement.

### Bài 18. Expand-contract có mấy giai đoạn chính?

**Đáp án:** Expand schema tương thích, migrate application/data, rồi contract loại bỏ schema cũ sau khi không còn consumer.

### Bài 19. Vì sao backfill lớn nên chia batch?

**Đáp án:** Giảm transaction duration, WAL burst, replication lag và tạo checkpoint để retry/resume.

### Bài 20. Progress marker nên commit cùng data batch khi nào?

**Đáp án:** Khi muốn bảo đảm dữ liệu và checkpoint progress được ghi atomic trong cùng database transaction.

### Bài 21. Khi nào forward-fix phù hợp hơn rollback?

**Đáp án:** Khi dữ liệu mới đã phụ thuộc schema mới hoặc rollback có thể làm mất dữ liệu/side effects.

### Bài 22. Vì sao không sửa migration file cũ đã deploy?

**Đáp án:** Thay đổi checksum và làm lịch sử triển khai không reproducible; dùng migration mới.

### Bài 23. Khi target đã nhận writes mới, đổi endpoint về source có an toàn không?

**Đáp án:** Không mặc định; cần reverse sync/reconciliation hoặc recovery strategy để tránh mất writes.

### Bài 24. Vì sao schema comparison cần kiểm tra grants và RLS?

**Đáp án:** Hai schema có table definitions giống nhau vẫn có thể có security behavior khác.

### Bài 25. pg_blocking_pids dùng để làm gì?

**Đáp án:** Tìm PID đang chặn một backend, hỗ trợ điều tra migration lock waits.

### Bài 26. Khi nào terminate backend?

**Đáp án:** Chỉ sau khi xác minh PID/session, owner, transaction state và tác động theo runbook/approval.

### Bài 27. Logical replication có tự replicate DDL không?

**Đáp án:** Không mặc định; schema changes cần được triển khai riêng ở subscriber.

### Bài 28. Vì sao cần kiểm tra application versions trước contract migration?

**Đáp án:** Instance cũ hoặc worker cũ có thể còn truy cập column/object sắp bị xóa.

### Bài 29. Repair migration cần có gì?

**Đáp án:** ID mới, preconditions, repair steps, postconditions, retry policy, risk và evidence.

### Bài 30. Khi nào được đóng migration incident?

**Đáp án:** Khi schema/data/ledger/app/replication/backup đạt acceptance criteria, evidence đầy đủ và reviewer sign-off.

## 49. Checklist xử lý migration lỗi và schema drift

### Containment và xác định trạng thái

- [ ] Dừng migration/deployment tiếp theo.
- [ ] Xác nhận đúng cluster/database/environment.
- [ ] Ghi migration ID, checksum, tool version và timestamp.
- [ ] Lưu error output, SQLSTATE và server logs.
- [ ] Kiểm tra session/transaction còn chạy.
- [ ] Xác định DDL transactional hay non-transactional.
- [ ] Đọc migration ledger.
- [ ] Kiểm tra objects và definitions trong catalog.
- [ ] Kiểm tra data backfill/progress.
- [ ] Xác định application versions và writers.

### Recovery decision

- [ ] Phân loại trạng thái: unchanged, partial, committed, drift hoặc unknown.
- [ ] Kiểm tra index validity/ready state.
- [ ] Kiểm tra constraint validation.
- [ ] Kiểm tra sequence và data integrity.
- [ ] Đánh giá rollback/data loss.
- [ ] Chọn retry, resume, rollback, forward-fix hoặc restore.
- [ ] Xác định owner/approver.
- [ ] Test repair trên staging/clone nếu phù hợp.
- [ ] Bảo đảm migration runner lock và retry safety.

### Verification và closure

- [ ] Schema khớp source of truth.
- [ ] Data reconciliation đạt.
- [ ] Migration ledger phản ánh đúng.
- [ ] Application/worker versions tương thích.
- [ ] Replication/subscriptions/slots ổn định.
- [ ] Backup/WAL archive tiếp tục.
- [ ] Smoke tests đạt.
- [ ] Metrics/error rate trong ngưỡng.
- [ ] Evidence được lưu và redact.
- [ ] Repair migration được version hóa.
- [ ] Exception/deviation được ghi nhận.
- [ ] Reviewer sign-off và change closure.

## 50. Tài liệu PostgreSQL chính thức

Đọc tài liệu theo major version đang triển khai:

- [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) — thay đổi bảng, constraint và validation.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) — index creation và CONCURRENTLY.
- [DROP INDEX](https://www.postgresql.org/docs/current/sql-dropindex.html) — xóa index và CONCURRENTLY.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — lock modes và deadlocks.
- [Lock Management](https://www.postgresql.org/docs/current/runtime-config-locks.html) — deadlock_timeout và lock settings.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_activity, pg_locks và các statistics views.
- [System Catalogs](https://www.postgresql.org/docs/current/catalogs.html) — schema metadata và object state.
- [Information Schema](https://www.postgresql.org/docs/current/information-schema.html) — metadata chuẩn cho columns, tables và grants.
- [ALTER TYPE](https://www.postgresql.org/docs/current/sql-altertype.html) — enum/type changes.
- [Transactions](https://www.postgresql.org/docs/current/tutorial-transactions.html) — transaction boundaries và rollback.
- [Advisory Locks](https://www.postgresql.org/docs/current/explicit-locking.html#ADVISORY-LOCKS) — application-defined locking.
- [pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html) — tạo schema/data snapshot.
- [pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html) — restore archive.
- [Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html) — recovery nếu migration làm hỏng dữ liệu.
- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html) — schema/DDL và replication behavior.
- [SQLSTATE Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html) — phân loại lỗi PostgreSQL.

Tên catalog columns, DDL behavior và các command options có thể thay đổi theo major version. Đối chiếu tài liệu của server đang chạy và migration tool cụ thể trước khi áp dụng runbook.

## 51. Tổng kết

**Khi migration lỗi, trạng thái database thực tế quyết định cách phục hồi.** Migration ledger, command output và application deployment record đều cần được đối chiếu với PostgreSQL catalogs và dữ liệu trước khi retry hoặc rollback.

1. **Migration failure, schema drift và partial deployment là ba trạng thái khác nhau.** Xác định đúng loại sự cố trước khi hành động.
2. **Dừng các bước tiếp theo và xác minh trạng thái.** Client timeout không chứng minh server đã rollback.
3. **Ledger không thay thế catalog và data checks.** Cả lịch sử migration lẫn trạng thái database đều cần được kiểm tra.
4. **Không phải mọi DDL đều transactional.** CREATE INDEX CONCURRENTLY và các thao tác đặc biệt có thể để lại trạng thái một phần.
5. **Kiểm tra index validity và constraint validation.** Object tồn tại chưa có nghĩa object sẵn sàng.
6. **IF NOT EXISTS không sửa definition mismatch.** Kiểm tra precondition/postcondition cụ thể.
7. **Dùng migration lock và timeout.** Ngăn runner cạnh tranh và giới hạn lock waits.
8. **Expand-contract giữ tương thích giữa các application versions.** Chỉ contract sau khi không còn consumer cũ.
9. **Backfill lớn cần batch, progress checkpoint và retry-safe logic.**
10. **Rollback không luôn an toàn.** Dữ liệu mới, external side effects và partial cutover có thể yêu cầu forward-fix hoặc restore.
11. **Repair migration phải là thay đổi mới, có precondition và evidence.** Không sửa lịch sử migration đã triển khai.
12. **Schema drift bao gồm security và object state.** Kiểm tra grants, RLS, triggers, indexes, constraints và extension versions.
13. **Chỉ đóng incident khi schema, data, ledger, application, replication và backup đã được xác minh.**

Một quy trình recovery đáng tin cậy không cố gắng làm migration chạy lại càng nhanh càng tốt. Nó xác định chính xác điều gì đã xảy ra, giữ nguyên bằng chứng, chọn phương án phù hợp với dữ liệu hiện tại và đưa database cùng application trở lại trạng thái nhất quán có thể kiểm chứng.
