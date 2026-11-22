# DDL trong giao dịch và các lệnh có ngoại lệ trong PostgreSQL

PostgreSQL hỗ trợ transactional DDL cho phần lớn thao tác thay đổi schema. Điều đó có nghĩa một nhóm lệnh như CREATE TABLE, ALTER TABLE, CREATE VIEW hoặc DROP INDEX thông thường có thể nằm trong một transaction; nếu transaction rollback, các thay đổi catalog tương ứng cũng được hoàn tác. Đây là lợi thế quan trọng khi triển khai migration: schema và dữ liệu có thể được thay đổi như một đơn vị nhất quán.

Tuy nhiên, **không phải mọi lệnh quản trị hoặc DDL đều chạy được trong transaction block**. Một số lệnh cần tác động tới database cluster, filesystem, server configuration hoặc replication slot ở bên ngoài transaction hiện tại. Các lệnh như CREATE DATABASE, CREATE TABLESPACE, ALTER SYSTEM, VACUUM và các biến thể CREATE INDEX CONCURRENTLY có quy tắc riêng. Nếu migration framework tự động bọc toàn bộ script trong BEGIN/COMMIT, những lệnh này sẽ thất bại.

Bên cạnh đó, cần phân biệt hai loại ngoại lệ:

- **Lệnh không được phép chạy trong transaction block:** PostgreSQL từ chối ngay khi phát hiện transaction block đang mở.
- **Lệnh chạy được nhưng có thể thất bại trong transaction:** lỗi SQL làm transaction chuyển sang trạng thái aborted. Muốn tiếp tục cần ROLLBACK toàn transaction hoặc ROLLBACK TO SAVEPOINT đã tạo trước đó.

Một migration an toàn phải biết lệnh nào có thể gộp nguyên tử, lệnh nào cần chạy độc lập, cách xử lý lỗi và cách kiểm tra trạng thái sau khi một thao tác dài hoặc concurrent thất bại.

~~~text
                  Schema migration
                         |
              +----------+-----------+
              |                      |
              v                      v
       Transactional DDL       Non-transactional
       BEGIN / COMMIT          command / operation
              |                      |
       +------+-------+         +----+------+
       |              |         |           |
       v              v         v           v
    Success          Error    Run outside   External
       |              |       transaction   side effects
       v              v         |           |
     COMMIT      ROLLBACK /     v           v
                 SAVEPOINT   Verify state, cleanup,
                             retry or continue
~~~

Bài học thuộc module **Database Engine Relational PostgreSQL**, chương **Thay đổi lược đồ**, với đề tài **“DDL trong giao dịch và các lệnh có ngoại lệ”**. Nội dung giải thích transactional DDL, savepoints, transaction-aborted state, danh sách lệnh có ngoại lệ, concurrent index operations, PL/pgSQL exception blocks, transaction control trong procedures và cách tổ chức migration production.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích transactional DDL trong PostgreSQL.
2. Phân biệt transaction block, implicit transaction và autocommit.
3. Thực hiện CREATE/ALTER/DROP schema objects trong transaction.
4. Rollback DDL khi migration thất bại.
5. Dùng SAVEPOINT và ROLLBACK TO SAVEPOINT để phục hồi một phần transaction.
6. Giải thích vì sao một SQL error làm transaction chuyển sang aborted state.
7. Nhận diện các lệnh không được phép chạy trong transaction block.
8. Phân biệt CREATE INDEX thông thường với CREATE INDEX CONCURRENTLY.
9. Hiểu failure modes và invalid indexes sau concurrent index build.
10. Biết các giới hạn của DROP INDEX CONCURRENTLY và REINDEX CONCURRENTLY.
11. Xử lý VACUUM, CREATE DATABASE, TABLESPACE và ALTER SYSTEM trong migration.
12. Hiểu ngoại lệ liên quan CREATE/DROP SUBSCRIPTION và replication slots.
13. Nhận biết thay đổi theo phiên bản với ALTER TYPE ADD VALUE.
14. Dùng PL/pgSQL EXCEPTION blocks và hiểu subtransaction semantics.
15. Thu thập SQLSTATE, message, detail, hint và constraint information.
16. Phân biệt function, procedure và DO block khi điều khiển transaction.
17. Thiết kế migration atomic và non-atomic.
18. Tổ chức migration tool để không bọc lệnh đặc biệt trong transaction.
19. Quản lý locks, timeouts và transaction duration trong DDL.
20. Kiểm tra trạng thái catalog sau migration và sau lỗi.
21. Xây dựng rollback, retry và recovery procedures.
22. Thực hành transactional DDL, savepoint, concurrent index và exception handling trong lab.

**Phạm vi:** PostgreSQL hiện đại. Danh sách lệnh và một số giới hạn có thể thay đổi theo major version. Luôn kiểm tra documentation của server target, đặc biệt với replication commands, enum changes, concurrent index operations và migration framework. Các ví dụ dùng database lab; không chạy thao tác phá hủy hoặc long-running DDL trên production nếu chưa có kế hoạch.

---

## 2. Transaction block và autocommit

Transaction xác định ranh giới mà các thay đổi database được commit hoặc rollback.

### 2.1. Explicit transaction

Một transaction rõ ràng bắt đầu bằng BEGIN hoặc START TRANSACTION và kết thúc bằng COMMIT hoặc ROLLBACK.

~~~sql
BEGIN;

CREATE TABLE public.customer_note (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    note TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.customer_note
    ADD CONSTRAINT customer_note_note_not_empty
    CHECK (length(note) > 0);

COMMIT;
~~~

Nếu mọi lệnh thành công, transaction commit toàn bộ thay đổi. Nếu có lỗi và transaction rollback, bảng cùng constraint được tạo trong transaction sẽ không còn.

### 2.2. Autocommit

Trong psql, autocommit mặc định được bật. Mỗi statement ngoài transaction block được thực thi trong một transaction ngầm riêng.

~~~sql
CREATE TABLE public.audit_event (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_name TEXT NOT NULL
);

ALTER TABLE public.audit_event
    ADD COLUMN created_at TIMESTAMPTZ DEFAULT now();
~~~

Hai statements trên thường commit độc lập. Nếu statement thứ hai thất bại, statement đầu tiên vẫn đã commit.

### 2.3. Implicit transaction và explicit transaction

- Implicit transaction: client gửi một statement khi không có transaction block; PostgreSQL tự quản lý begin/commit cho statement đó.
- Explicit transaction: client mở transaction và gom nhiều statements vào cùng một đơn vị.
- Transaction block: trạng thái mà server đang ở trong một transaction do client điều khiển.

Một lệnh bị cấm trong transaction block vẫn có thể chạy nếu được gửi độc lập với autocommit bật.

### 2.4. Client có thể tự bọc transaction

Migration tool, ORM hoặc application driver có thể tự gửi BEGIN trước khi chạy SQL. Vì vậy một lệnh chạy được trong psql autocommit có thể thất bại khi được gọi từ migration framework.

### 2.5. Kiểm tra trạng thái từ client

Trong psql, có thể xem trạng thái autocommit:

~~~text
\echo :AUTOCOMMIT
~~~

Có thể bật/tắt bằng:

~~~text
\set AUTOCOMMIT on
~~~

Autocommit là behavior của psql client, không phải một GUC server dùng chung cho mọi connection.

---

## 3. Transactional DDL là gì?

Transactional DDL là khả năng thực hiện thay đổi schema bên trong transaction và rollback thay đổi đó nếu transaction không commit.

### 3.1. Các DDL thường hỗ trợ transaction

Phần lớn các lệnh sau có thể chạy trong transaction block:

- CREATE TABLE, ALTER TABLE, DROP TABLE.
- CREATE VIEW, ALTER VIEW, DROP VIEW.
- CREATE SEQUENCE, ALTER SEQUENCE, DROP SEQUENCE.
- CREATE SCHEMA, ALTER SCHEMA, DROP SCHEMA.
- CREATE TYPE, ALTER TYPE, DROP TYPE, với một số version/operation-specific caveats.
- CREATE FUNCTION, ALTER FUNCTION, DROP FUNCTION.
- CREATE TRIGGER, ALTER TRIGGER, DROP TRIGGER.
- CREATE INDEX và DROP INDEX thông thường.
- CREATE EXTENSION, ALTER EXTENSION UPDATE, DROP EXTENSION trong các điều kiện extension hỗ trợ.
- CREATE/ALTER/DROP nhiều loại constraints và policies.

Danh sách này không có nghĩa mọi option hoặc extension script đều an toàn trong transaction. Một extension update script có thể gọi một command bị cấm trong transaction block.

### 3.2. Ví dụ rollback CREATE TABLE

~~~sql
BEGIN;

CREATE TABLE public.rollback_demo (
    id INTEGER PRIMARY KEY,
    description TEXT
);

INSERT INTO public.rollback_demo(id, description)
VALUES (1, 'temporary schema change');

ROLLBACK;
~~~

Sau ROLLBACK, table và row vừa tạo không còn.

### 3.3. Ví dụ rollback ALTER TABLE

~~~sql
BEGIN;

ALTER TABLE public.orders
    ADD COLUMN migration_marker BOOLEAN DEFAULT false;

ROLLBACK;
~~~

Cột mới được tạo trong transaction sẽ bị rollback.

### 3.4. Ví dụ rollback DROP TABLE

~~~sql
BEGIN;

DROP TABLE public.old_reporting_table;

-- Phát hiện migration còn thiếu bước.
ROLLBACK;
~~~

Nếu DROP TABLE chưa commit, rollback khôi phục catalog state và table vẫn tồn tại.

### 3.5. DDL và catalog visibility

Các thay đổi catalog chưa commit không được xem như schema change đã công bố cho những transaction khác. Khi commit, các session khác có thể quan sát schema mới theo transaction visibility và lock rules.

### 3.6. Transactional DDL không loại bỏ lock

DDL vẫn phải lấy lock cần thiết. Ví dụ ALTER TABLE thường cần lock mạnh; lock được giữ tới cuối transaction. Một transaction migration mở lâu có thể block application queries hoặc làm DDL khác phải chờ.

### 3.7. Atomicity có giới hạn ở database transaction

Các side effects ngoài transaction, ví dụ HTTP request, ghi file tùy biến từ external process hoặc thay đổi ở remote system, không tự động rollback cùng PostgreSQL transaction. Sequence operations như nextval cũng không được rollback theo cách thông thường.

Không nên giả định mọi side effect phát sinh khi chạy DDL đều được hoàn tác.

---

## 4. Vì sao transactional DDL hữu ích?

### 4.1. Schema và data change có thể nhất quán

Một migration có thể thêm column, backfill một tập nhỏ, tạo constraint và cập nhật migration ledger trong cùng transaction. Nếu một bước thất bại, toàn bộ nhóm thay đổi có thể rollback.

### 4.2. Tránh schema ở trạng thái nửa chừng

Nếu ALTER TABLE thành công nhưng bước tiếp theo thất bại, transactional migration có thể rollback ALTER TABLE thay vì để schema mới thiếu constraint hoặc function.

### 4.3. Deployment có thể kiểm soát

Migration runner có thể chỉ đánh dấu migration đã hoàn tất sau khi COMMIT thành công. Điều này giúp schema state và migration history nhất quán.

### 4.4. Dễ thử nghiệm và phục hồi

Trong staging, có thể chạy migration, kiểm tra kết quả và rollback để xác nhận hành vi. Tuy nhiên, không thay thế backup hoặc rehearsal trên dữ liệu tương đương production.

### 4.5. Không phải mọi migration đều nên là một transaction lớn

Một transaction DDL kéo dài có thể giữ locks, snapshot và tài nguyên. Backfill hàng tỷ rows, concurrent index build hoặc vacuum thường cần quy trình riêng, chia batch hoặc chạy độc lập.

---

## 5. SQL error và trạng thái aborted transaction

Khi một statement trong explicit transaction thất bại, PostgreSQL thường đánh dấu transaction là aborted. Các statements tiếp theo không được thực thi thành công cho tới khi rollback.

### 5.1. Ví dụ unique violation

~~~sql
BEGIN;

CREATE TABLE public.unique_demo (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE
);

INSERT INTO public.unique_demo VALUES
    (1, 'a@example.test');

INSERT INTO public.unique_demo VALUES
    (2, 'a@example.test');

-- Statement thứ hai gây unique_violation.
SELECT count(*) FROM public.unique_demo;
~~~

Sau lỗi, SELECT cuối sẽ nhận lỗi vì transaction đang ở trạng thái aborted. Cần ROLLBACK hoặc ROLLBACK TO SAVEPOINT.

### 5.2. SQLSTATE

PostgreSQL gắn SQLSTATE code cho lỗi. Ví dụ:

| SQLSTATE | Condition | Ý nghĩa |
| --- | --- | --- |
| 23505 | unique_violation | Trùng unique key |
| 23503 | foreign_key_violation | Vi phạm foreign key |
| 23514 | check_violation | Vi phạm CHECK |
| 42P07 | duplicate_table | Relation cùng tên đã tồn tại |
| 42701 | duplicate_column | Column đã tồn tại |
| 25001 | active_sql_transaction | Lệnh không được chạy trong transaction block |
| 40001 | serialization_failure | Serialization conflict |
| 40P01 | deadlock_detected | Deadlock |
| 55P03 | lock_not_available | Không lấy được lock |
| 57014 | query_canceled | Query bị cancel/timeout trong nhiều tình huống |

SQLSTATE class/code cụ thể và message cần được lấy từ server, không nên suy luận chỉ từ text.

### 5.3. Khôi phục transaction

~~~sql
ROLLBACK;
~~~

ROLLBACK kết thúc transaction aborted và hoàn tác mọi thay đổi chưa commit.

### 5.4. Vì sao không thể chạy tiếp?

PostgreSQL phải giữ tính nhất quán transaction. Sau lỗi, nó không thể đơn giản bỏ qua statement thất bại rồi commit các câu lệnh sau như thể transaction không có vấn đề.

### 5.5. Client behavior

Một số client tự rollback khi exception; một số để transaction ở trạng thái aborted cho tới khi application gọi rollback. Application code cần luôn cleanup transaction trong error path.

---

## 6. SAVEPOINT và ROLLBACK TO SAVEPOINT

Savepoint tạo một điểm khôi phục bên trong transaction. Nếu statement sau savepoint thất bại, có thể rollback phần sau savepoint mà vẫn giữ các thay đổi trước đó.

### 6.1. Ví dụ

~~~sql
BEGIN;

CREATE TABLE public.savepoint_demo (
    id INTEGER PRIMARY KEY,
    value TEXT
);

SAVEPOINT before_optional_change;

ALTER TABLE public.savepoint_demo
    ADD COLUMN status TEXT;

-- Giả sử bước sau gặp lỗi:
INSERT INTO public.savepoint_demo(id, value, status)
VALUES (1, 'one', 'active');

-- Nếu cần phục hồi:
ROLLBACK TO SAVEPOINT before_optional_change;

-- CREATE TABLE vẫn còn trong transaction.
-- ALTER TABLE và INSERT sau savepoint bị hoàn tác.

COMMIT;
~~~

### 6.2. Savepoint không commit transaction

ROLLBACK TO SAVEPOINT chỉ hoàn tác phần thay đổi sau savepoint. Transaction ngoài vẫn mở và cần COMMIT hoặc ROLLBACK.

### 6.3. RELEASE SAVEPOINT

~~~sql
RELEASE SAVEPOINT before_optional_change;
~~~

RELEASE bỏ mốc savepoint. Nó không commit transaction.

### 6.4. Savepoint lồng nhau

Có thể tạo nhiều savepoints để phục hồi theo từng tầng. Khi rollback tới một savepoint, các savepoints được tạo sau nó bị hủy.

### 6.5. Savepoint và locks

Rollback to savepoint có thể giải phóng một số locks được lấy sau savepoint, theo semantics PostgreSQL. Locks được lấy trước savepoint vẫn có thể còn tới transaction end.

### 6.6. Khi nào dùng?

- Một migration có bước tùy chọn.
- Thử DDL có thể thất bại và muốn giữ phần setup.
- Xử lý lỗi có kiểm soát trong script quản trị.
- Batch operations cần rollback một phần.

Không dùng savepoint để che giấu migration lỗi hoặc commit một schema state không được xác định.

---

## 7. Các lệnh không được phép trong transaction block

Một số lệnh cần được chạy độc lập vì chúng tác động tới tài nguyên hoặc trạng thái bên ngoài transaction thông thường.

### 7.1. Bảng tổng hợp

| Lệnh/nhóm lệnh | Trong transaction block? | Lý do/ghi chú |
| --- | --- | --- |
| CREATE DATABASE | Không | Tạo database ở cấp cluster |
| DROP DATABASE | Không | Xóa database ở cấp cluster |
| CREATE TABLESPACE | Không | Tạo tablespace và filesystem directory |
| DROP TABLESPACE | Không | Xóa tablespace |
| ALTER SYSTEM | Không | Ghi server configuration file |
| VACUUM | Không | Thực hiện maintenance với transaction semantics riêng |
| CREATE INDEX CONCURRENTLY | Không | Xây index qua nhiều transaction/phase |
| DROP INDEX CONCURRENTLY | Không | Drop index theo quy trình concurrent |
| REINDEX CONCURRENTLY | Không | Rebuild index qua nhiều phase |
| CREATE SUBSCRIPTION với connect=true | Không | Có thể tạo replication slot trên remote publisher |
| DROP SUBSCRIPTION khi cần drop remote slot | Không | Có side effect với replication slot |

Đây là các trường hợp quan trọng thường gặp, không phải danh sách đầy đủ cho mọi PostgreSQL release và extension. Với lệnh replication, cần kiểm tra option và version cụ thể.

### 7.2. CREATE DATABASE

~~~sql
CREATE DATABASE app_reporting;
~~~

Chạy độc lập, không bọc trong BEGIN/COMMIT.

Nếu cần tạo database rồi chạy schema migration:
1. Tạo database trong một bước riêng.
2. Kết nối vào database mới.
3. Chạy schema DDL trong transaction phù hợp.

### 7.3. DROP DATABASE

~~~sql
DROP DATABASE app_reporting;
~~~

Cũng chạy ngoài transaction block. Cần kiểm tra connections, ownership và destructive impact trước khi drop.

### 7.4. CREATE TABLESPACE

~~~sql
CREATE TABLESPACE fast_space
    LOCATION '/srv/postgresql/tablespaces/fast_space';
~~~

Lệnh tạo tablespace phụ thuộc filesystem path và permissions. Directory phải đáp ứng yêu cầu của PostgreSQL và thường phải tồn tại trước khi lệnh chạy.

### 7.5. DROP TABLESPACE

~~~sql
DROP TABLESPACE fast_space;
~~~

Tablespace phải rỗng theo điều kiện PostgreSQL. Kiểm tra objects còn sử dụng tablespace trước khi xóa.

### 7.6. ALTER SYSTEM

~~~sql
ALTER SYSTEM SET work_mem = '16MB';
~~~

ALTER SYSTEM ghi cấu hình vào postgresql.auto.conf. Nó không phải một schema change được rollback cùng transaction. Sau đó cần reload hoặc restart tùy parameter context.

### 7.7. VACUUM

~~~sql
VACUUM (ANALYZE) public.orders;
~~~

VACUUM không chạy trong transaction block. VACUUM FULL cũng có cùng giới hạn transaction block và có lock/space requirements riêng. ANALYZE độc lập có thể chạy trong transaction; không nhầm ANALYZE với VACUUM ANALYZE.

### 7.8. Vì sao phải tách riêng?

Nếu migration runner đang bọc script bằng BEGIN, server có thể trả SQLSTATE 25001. Hãy chuyển command sang migration non-transactional hoặc bước triển khai riêng, không cố lồng nó vào transaction bằng savepoint.

---

## 8. CREATE INDEX và CREATE INDEX CONCURRENTLY

Đây là ví dụ điển hình về khác biệt giữa DDL transactional thông thường và lệnh có ngoại lệ.

### 8.1. CREATE INDEX thông thường

~~~sql
BEGIN;

CREATE INDEX orders_created_at_idx
    ON public.orders (created_at);

COMMIT;
~~~

CREATE INDEX thông thường có thể chạy trong transaction. Nếu transaction rollback, index creation cũng rollback.

### 8.2. Lock behavior

CREATE INDEX thông thường thường lấy lock ngăn DML writes vào table trong lúc build. Nó có thể làm INSERT/UPDATE/DELETE phải chờ. Với table lớn, thời gian lock có thể ảnh hưởng availability.

### 8.3. CREATE INDEX CONCURRENTLY

~~~sql
CREATE INDEX CONCURRENTLY orders_created_at_idx
    ON public.orders (created_at);
~~~

Lệnh này cho phép reads/writes tiếp tục trong phần lớn quá trình build, nhưng cần nhiều phase, scans và waits. Nó không thể chạy trong transaction block.

### 8.4. Vì sao không nằm trong một transaction?

Concurrent build cần nhiều transaction/phase để phối hợp với các transactions đang hoạt động và đảm bảo index hợp lệ khi build hoàn tất. Do đó server từ chối khi client đang ở trong explicit transaction block.

### 8.5. Hạn chế

- Không chạy được trong transaction block.
- Không chạy nhiều concurrent index builds trên cùng một table cùng lúc.
- Có thể phải chờ transactions/snapshots cũ.
- Tốn I/O và CPU trong quá trình build.
- Unique index build có thể phát hiện duplicate values và thất bại.
- Nếu thất bại, có thể để lại invalid index.

### 8.6. Invalid index sau failure

Kiểm tra index catalog:

~~~sql
SELECT
    ns.nspname AS schema_name,
    idx.relname AS index_name,
    tbl.relname AS table_name,
    i.indisready,
    i.indisvalid,
    i.indislive
FROM pg_catalog.pg_index AS i
JOIN pg_catalog.pg_class AS idx
    ON idx.oid = i.indexrelid
JOIN pg_catalog.pg_class AS tbl
    ON tbl.oid = i.indrelid
JOIN pg_catalog.pg_namespace AS ns
    ON ns.oid = idx.relnamespace
WHERE NOT i.indisvalid
ORDER BY ns.nspname, idx.relname;
~~~

indisvalid=false có nghĩa planner không xem index là index hợp lệ để sử dụng bình thường. indisready cho biết index có được duy trì bởi writes hay chưa; cần đọc cả flags và trạng thái thực tế.

### 8.7. Cleanup invalid index

Sau khi xác minh đúng index và nguyên nhân failure, có thể drop concurrent:

~~~sql
DROP INDEX CONCURRENTLY public.orders_created_at_idx;
~~~

Lệnh này cũng không chạy trong transaction block. Sau cleanup, sửa nguyên nhân rồi thử lại.

### 8.8. IF NOT EXISTS không tự sửa invalid index

Nếu index cùng tên đã tồn tại nhưng invalid, CREATE INDEX CONCURRENTLY IF NOT EXISTS có thể chỉ cảnh báo rằng relation đã tồn tại và bỏ qua. Cần kiểm tra catalog, drop invalid index theo cách phù hợp rồi mới tạo lại.

### 8.9. Unique index và constraint

CREATE UNIQUE INDEX CONCURRENTLY có thể phát hiện duplicates trong lúc build. Nếu cần tạo UNIQUE constraint, xem quy trình build unique index trước rồi attach constraint theo khả năng/version phù hợp. Không giả định mọi constraint có thể tạo concurrent trực tiếp.

---

## 9. DROP INDEX CONCURRENTLY và REINDEX CONCURRENTLY

### 9.1. DROP INDEX thông thường

~~~sql
BEGIN;

DROP INDEX public.orders_old_idx;

ROLLBACK;
~~~

DROP INDEX thông thường có thể nằm trong transaction. Rollback sẽ hoàn tác thao tác drop.

### 9.2. DROP INDEX CONCURRENTLY

~~~sql
DROP INDEX CONCURRENTLY public.orders_old_idx;
~~~

Không được chạy trong transaction block. Nó cho phép giảm blocking đối với concurrent activity theo quy trình nhiều phase.

### 9.3. Các giới hạn cần nhớ

DROP INDEX CONCURRENTLY:
- Chỉ drop một index trong một lệnh.
- Không hỗ trợ CASCADE.
- Không thể dùng để drop index đang backing một constraint.
- Có các giới hạn relation/index riêng theo version.

Nếu index thuộc constraint, phải xử lý constraint theo đúng DDL path thay vì cố drop index trực tiếp.

### 9.4. REINDEX thông thường

~~~sql
REINDEX INDEX public.orders_created_at_idx;
~~~

REINDEX thông thường có thể được dùng trong transaction block theo các điều kiện hỗ trợ, nhưng có thể block reads/writes đáng kể tùy object và operation.

### 9.5. REINDEX CONCURRENTLY

~~~sql
REINDEX INDEX CONCURRENTLY public.orders_created_at_idx;
~~~

Không chạy trong transaction block. Nó xây index replacement theo nhiều phase để giảm blocking, nhưng tốn thêm thời gian, I/O và storage.

### 9.6. Chọn phương thức

| Phương thức | Transaction block | Blocking | Chi phí |
| --- | --- | --- | --- |
| CREATE INDEX | Có | Có thể block writes trong build | Thường ít phase hơn |
| CREATE INDEX CONCURRENTLY | Không | Cho phép DML trong phần lớn quá trình | Nhiều phase, waits và I/O |
| DROP INDEX | Có | Có thể cần lock mạnh | Thao tác catalog ngắn hơn |
| DROP INDEX CONCURRENTLY | Không | Giảm blocking với concurrent sessions | Nhiều phase |
| REINDEX | Theo operation/version | Có thể block hoạt động | Rebuild index |
| REINDEX CONCURRENTLY | Không | Giảm blocking | Cần nhiều thời gian/storage |

Luôn xem PostgreSQL version và object type trước khi chọn.

---

## 10. CREATE DATABASE, TABLESPACE và ALTER SYSTEM trong migration

Những lệnh này thuộc phạm vi cluster/host configuration hơn là schema transaction của một database.

### 10.1. Tách provisioning khỏi schema migration

Một quy trình triển khai có thể chia:
1. Provision database/tablespace.
2. Cấu hình server settings.
3. Kết nối vào database.
4. Chạy transactional schema migration.
5. Chạy non-transactional operations.
6. Kiểm tra application và operational state.

### 10.2. Database creation

~~~sql
CREATE DATABASE appdb
    OWNER app_owner
    ENCODING 'UTF8';
~~~

Lệnh phải chạy ở database khác, không phải transaction block. Cấu hình locale/template cũng cần được quyết định trước khi tạo.

### 10.3. Tablespace provisioning

~~~sql
CREATE TABLESPACE archive_space
    OWNER dba_role
    LOCATION '/srv/postgresql/archive_space';
~~~

Filesystem path và OS ownership phải sẵn sàng. Backup/restore và failover hosts cần có storage mapping tương ứng.

### 10.4. ALTER SYSTEM

~~~sql
ALTER SYSTEM SET shared_buffers = '4GB';
SELECT pg_reload_conf();
~~~

shared_buffers cần restart để có hiệu lực; reload không đủ. pg_settings.pending_restart giúp xác nhận. ALTER SYSTEM không nằm trong transaction block và không rollback cùng schema migration.

### 10.5. Quản lý configuration như infrastructure

Trong production, nhiều tổ chức quản lý parameter qua config management, container environment hoặc managed-service parameter groups. Không nên để migration SQL âm thầm thay đổi server-wide configuration mà không có owner/change record.

---

## 11. VACUUM và ANALYZE

### 11.1. VACUUM

~~~sql
VACUUM public.orders;
~~~

VACUUM không được chạy trong transaction block. Nó thực hiện maintenance để xử lý dead tuples, visibility map và các công việc liên quan.

### 11.2. VACUUM ANALYZE

~~~sql
VACUUM (ANALYZE) public.orders;
~~~

Cũng không chạy trong transaction block vì có VACUUM.

### 11.3. ANALYZE độc lập

~~~sql
ANALYZE public.orders;
~~~

ANALYZE có thể chạy trong transaction block. Nó thu thập statistics cho planner; không thực hiện toàn bộ công việc cleanup của VACUUM.

### 11.4. VACUUM FULL

~~~sql
VACUUM FULL public.orders;
~~~

VACUUM FULL rewrite table và cần lock mạnh, storage bổ sung. Nó không chạy trong transaction block. Đánh giá downtime, disk space và bloat trước khi sử dụng.

### 11.5. Autovacuum

Autovacuum là background process do PostgreSQL điều phối. Nó không phải lệnh DDL của migration và có lifecycle riêng. Không cố gọi VACUUM trong migration transaction để thay thế autovacuum.

---

## 12. Subscription và replication slot: ngoại lệ có side effects bên ngoài

Logical replication có một số command cần chú ý vì chúng tương tác với publisher và replication slots.

### 12.1. CREATE SUBSCRIPTION

Ví dụ:

~~~sql
CREATE SUBSCRIPTION orders_sub
CONNECTION 'host=publisher.example.test dbname=appdb user=repl_user'
PUBLICATION orders_pub;
~~~

Với connect=true mặc định, CREATE SUBSCRIPTION kết nối tới publisher và tạo replication slot theo cấu hình. Do có side effect ở remote server, command không được thực hiện trong transaction block.

### 12.2. connect=false

Một số quy trình tạo subscription với connect=false để tránh kết nối/tạo slot ngay trong command. Khi đó cần tự quản lý slot và các bước đồng bộ tiếp theo theo documentation. Không coi đây là cách bỏ qua mọi replication setup requirements.

### 12.3. DROP SUBSCRIPTION

Nếu subscription cần xóa remote replication slot, DROP SUBSCRIPTION có thể không chạy trong transaction block vì thao tác remote side effect. Cần kiểm tra slot state và version-specific instructions.

### 12.4. Slot không thể liên hệ

Nếu publisher không reachable hoặc slot đã được xử lý riêng, cần theo hướng dẫn để detach subscription khỏi slot trước khi drop local subscription. Không xóa slot trên publisher khi chưa xác nhận consumer state.

### 12.5. External state không rollback cùng local transaction

Remote replication slot creation/drop không thể được coi như một thay đổi catalog local thông thường. Rehearsal phải kiểm tra cả subscriber lẫn publisher.

---

## 13. ALTER TYPE ADD VALUE và khác biệt phiên bản

Enum type là ví dụ về một DDL có quy tắc thay đổi theo major version.

### 13.1. Thêm enum value

~~~sql
ALTER TYPE order_status
    ADD VALUE 'awaiting_review';
~~~

### 13.2. PostgreSQL 11 và cũ hơn

Ở các phiên bản cũ, ALTER TYPE ... ADD VALUE không được thực hiện trong transaction block. Migration cần tách command thành bước độc lập.

### 13.3. PostgreSQL 12 trở lên

Các version này cho phép thêm enum value trong transaction block. Tuy nhiên, giá trị mới không được dùng cho tới khi transaction chứa ALTER TYPE commit.

Ví dụ:

~~~sql
BEGIN;

ALTER TYPE order_status
    ADD VALUE 'awaiting_review';

-- Không dùng giá trị vừa thêm trong cùng transaction.
COMMIT;

INSERT INTO public.orders(status)
VALUES ('awaiting_review');
~~~

### 13.4. Vì sao cần tách bước?

Nếu migration thêm enum value rồi lập tức insert hoặc cast sang value đó trước COMMIT, server có thể từ chối vì enum value chưa được commit.

### 13.5. Enum label ordering

ADD VALUE có thể đặt BEFORE/AFTER một label hiện có. Thứ tự enum ảnh hưởng comparison/sort semantics; kiểm tra application assumptions và migration order.

### 13.6. Không xóa enum label trực tiếp

Nếu cần loại bỏ hoặc đổi label, thường phải tạo type mới và migrate dependencies/data. Đây là migration nhiều bước, không phải thao tác đổi tên chuỗi đơn giản.

---

## 14. Lệnh có ngoại lệ không đồng nghĩa DDL không transactional

Cần phân biệt:
- DDL thay đổi catalog và có thể rollback.
- Lệnh bị cấm trong transaction block.
- Lệnh chạy được nhưng gây external side effects.
- Lệnh cần nhiều transaction/phase.
- Lệnh có behavior thay đổi theo version.

### 14.1. Ví dụ CREATE INDEX

CREATE INDEX thường transactional; CREATE INDEX CONCURRENTLY thì không chạy trong transaction block.

### 14.2. Ví dụ VACUUM

VACUUM không phải schema DDL, nhưng thường xuất hiện trong migration/maintenance scripts và không được chạy trong transaction block.

### 14.3. Ví dụ ALTER SYSTEM

ALTER SYSTEM là command quản trị configuration, không phải thay đổi schema của database. Nó ghi file config và không tham gia rollback transaction.

### 14.4. Ví dụ CREATE SUBSCRIPTION

Có thay đổi catalog local và có thể tạo replication slot trên remote publisher. External effect làm command có transaction restrictions.

### 14.5. Cần phân loại theo command cụ thể

Không thể suy luận từ tên DDL rằng command có thể hoặc không thể chạy trong transaction. Kiểm tra documentation và thử trên đúng target major version.

---

## 15. PL/pgSQL EXCEPTION blocks và subtransactions

PL/pgSQL cho phép xử lý lỗi bên trong block bằng EXCEPTION. Block có EXCEPTION được thực thi với subtransaction semantics.

### 15.1. Cấu trúc cơ bản

~~~sql
DO $$
BEGIN
    INSERT INTO public.audit_event(event_name)
    VALUES ('migration_started');

EXCEPTION
    WHEN unique_violation THEN
        RAISE NOTICE 'Duplicate event ignored';
END;
$$;
~~~

DO block là một anonymous code block. Ví dụ trên minh họa handler; bảng cần tồn tại trước khi chạy.

### 15.2. Subtransaction behavior

Khi lỗi xảy ra bên trong block có EXCEPTION:
- Các database changes thực hiện trong block đó bị rollback.
- Control chuyển tới matching handler.
- Các changes trước khi vào block vẫn còn trong outer transaction.
- Sau handler, outer block có thể tiếp tục.

### 15.3. Ví dụ rollback một phần

~~~sql
DO $$
BEGIN
    INSERT INTO public.audit_event(event_name)
    VALUES ('before_inner_block');

    BEGIN
        INSERT INTO public.audit_event(event_name)
        VALUES ('duplicate_event');

        INSERT INTO public.audit_event(event_name)
        VALUES ('duplicate_event');

    EXCEPTION
        WHEN unique_violation THEN
            RAISE NOTICE 'Inner block rolled back';
    END;

    INSERT INTO public.audit_event(event_name)
    VALUES ('after_inner_block');
END;
$$;
~~~

Để minh họa đúng unique_violation, event_name cần có unique constraint. Khi lỗi xảy ra, insert đầu tiên trong inner block cũng bị rollback cùng subtransaction.

### 15.4. Biến PL/pgSQL

Giá trị biến PL/pgSQL không được rollback giống database changes. Handler có thể đọc các biến tại thời điểm exception được phát sinh.

### 15.5. Exception block có overhead

Subtransaction tốn chi phí quản lý. Tránh bọc mọi statement trong EXCEPTION chỉ để kiểm tra điều kiện có thể xử lý bằng INSERT ... ON CONFLICT hoặc kiểm tra metadata.

### 15.6. Không bắt lỗi quá rộng

WHEN OTHERS có thể che giấu lỗi schema nghiêm trọng nếu handler chỉ ghi NOTICE rồi tiếp tục. Chỉ bắt condition mà code biết cách phục hồi.

---

## 16. Bắt lỗi theo condition và SQLSTATE

### 16.1. Các conditions thường dùng

~~~sql
DO $$
BEGIN
    -- Thực hiện một thao tác có thể thất bại.
    PERFORM 1 / 0;

EXCEPTION
    WHEN division_by_zero THEN
        RAISE NOTICE 'Cannot divide by zero';

    WHEN OTHERS THEN
        RAISE;
END;
$$;
~~~

RAISE; trong handler phát lại lỗi hiện tại để outer caller xử lý.

### 16.2. Một số condition names

| Condition | SQLSTATE | Ý nghĩa |
| --- | --- | --- |
| unique_violation | 23505 | Unique constraint |
| foreign_key_violation | 23503 | Foreign key |
| check_violation | 23514 | CHECK constraint |
| not_null_violation | 23502 | NOT NULL |
| serialization_failure | 40001 | Serialization conflict |
| deadlock_detected | 40P01 | Deadlock |
| lock_not_available | 55P03 | Lock không sẵn sàng |
| query_canceled | 57014 | Query bị cancel |
| insufficient_privilege | 42501 | Thiếu quyền |
| undefined_table | 42P01 | Table không tồn tại |

### 16.3. SQLSTATE là interface ổn định hơn message text

Application/handler nên phân loại theo SQLSTATE hoặc condition name. Message text có thể khác theo locale, version hoặc detail của lỗi.

### 16.4. WHEN OTHERS có ngoại lệ

Trong PL/pgSQL, WHEN OTHERS không bắt tất cả condition. Query cancellation và assertion failure là các trường hợp được loại trừ theo semantics của PL/pgSQL. Đừng dựa vào OTHERS để nuốt mọi lỗi.

### 16.5. RAISE NOTICE không thay thế error handling

NOTICE chỉ gửi thông báo. Nếu handler bỏ qua lỗi và tiếp tục, phải chắc chắn database state đã được phục hồi và nghiệp vụ cho phép.

---

## 17. GET STACKED DIAGNOSTICS

Handler có thể đọc thông tin chi tiết của exception vừa xảy ra.

~~~sql
DO $$
DECLARE
    v_state TEXT;
    v_message TEXT;
    v_detail TEXT;
    v_hint TEXT;
    v_context TEXT;
BEGIN
    INSERT INTO public.unique_demo(id, email)
    VALUES (3, 'a@example.test');

EXCEPTION
    WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS
            v_state = RETURNED_SQLSTATE,
            v_message = MESSAGE_TEXT,
            v_detail = PG_EXCEPTION_DETAIL,
            v_hint = PG_EXCEPTION_HINT,
            v_context = PG_EXCEPTION_CONTEXT;

        RAISE NOTICE 'SQLSTATE=% MESSAGE=% DETAIL=% HINT=% CONTEXT=%',
            v_state, v_message, v_detail, v_hint, v_context;

        RAISE;
END;
$$;
~~~

### 17.1. Diagnostics fields

Có thể lấy:
- RETURNED_SQLSTATE.
- MESSAGE_TEXT.
- PG_EXCEPTION_DETAIL.
- PG_EXCEPTION_HINT.
- PG_EXCEPTION_CONTEXT.
- SCHEMA_NAME.
- TABLE_NAME.
- COLUMN_NAME.
- CONSTRAINT_NAME.
- DATATYPE_NAME.

Availability/meaning của field cụ thể phụ thuộc exception và version.

### 17.2. Không ghi secrets vào logs

Exception detail/context có thể chứa dữ liệu nhạy cảm hoặc query parameters. Mask theo policy trước khi đưa vào centralized logs.

### 17.3. RAISE lại sau khi ghi diagnostics

Nếu lỗi không được xử lý an toàn, RAISE; giúp giữ failure semantics và để caller/migration runner rollback transaction.

---

## 18. ON CONFLICT thay cho exception trong upsert

Một số lỗi có thể được xử lý bằng SQL semantics thay vì tạo exception.

### 18.1. Không cần bắt unique_violation cho upsert đơn giản

~~~sql
INSERT INTO public.feature_flag(flag_name, enabled)
VALUES ('new_checkout', true)
ON CONFLICT (flag_name)
DO UPDATE SET enabled = EXCLUDED.enabled;
~~~

### 18.2. DO NOTHING

~~~sql
INSERT INTO public.feature_flag(flag_name, enabled)
VALUES ('new_checkout', true)
ON CONFLICT (flag_name) DO NOTHING;
~~~

### 18.3. Lợi ích

- Code rõ mục đích.
- Tránh dùng exception như control flow thường xuyên.
- Có thể giảm subtransaction overhead.
- Xử lý concurrency theo unique constraint semantics của PostgreSQL.

### 18.4. Không thay thế mọi exception

Foreign key, check violations, permissions, serialization failures và các lỗi khác vẫn cần được xử lý theo nghiệp vụ. ON CONFLICT chỉ xử lý conflict mục tiêu được hỗ trợ.

---

## 19. Function, procedure và DO block: transaction control

Không phải mọi PL/pgSQL code đều có quyền COMMIT hoặc ROLLBACK.

### 19.1. Function

Function được gọi trong một SQL statement và chạy trong transaction của statement/caller. Function không được tự COMMIT hoặc ROLLBACK transaction.

~~~sql
CREATE OR REPLACE FUNCTION public.do_work()
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO public.audit_event(event_name)
    VALUES ('function_called');

    -- Không thể COMMIT transaction tại đây.
END;
$$;
~~~

### 19.2. Procedure

Procedure được gọi bằng CALL và có thể thực hiện transaction control trong các điều kiện được PostgreSQL cho phép.

~~~sql
CREATE OR REPLACE PROCEDURE public.batch_marker()
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO public.audit_event(event_name)
    VALUES ('batch_marker');

    COMMIT;
END;
$$;
~~~

Ví dụ minh họa transaction control trong procedure. CALL cần được thực hiện theo điều kiện cho phép, thường là ở top-level và không nằm trong explicit transaction block do caller mở.

### 19.3. CALL trong transaction block

~~~sql
BEGIN;
CALL public.batch_marker();
COMMIT;
~~~

Nếu procedure cố COMMIT trong trường hợp CALL đang chạy bên trong explicit transaction block, PostgreSQL sẽ từ chối transaction control.

### 19.4. DO block

DO có thể dùng transaction control trong trường hợp được gọi ở top-level và không có outer transaction block cản trở. Nếu DO chạy bên trong transaction block, COMMIT/ROLLBACK trong DO không được phép.

### 19.5. Exception block hạn chế transaction control

Transaction control không được thực hiện khi đang ở trong PL/pgSQL block có EXCEPTION handler vì block đó dùng subtransaction.

### 19.6. CALL stack

Transaction control trong procedure còn phụ thuộc cách các CALL/DO được lồng nhau. Một lời gọi trung gian qua SQL command khác có thể làm mất điều kiện top-level cần thiết.

### 19.7. COMMIT AND CHAIN

Procedure có thể dùng COMMIT AND CHAIN trong các version hỗ trợ để kết thúc transaction hiện tại và bắt đầu transaction mới với các characteristics được chain theo semantics PostgreSQL.

### 19.8. Dùng transaction control trong procedure có chủ đích

Ví dụ batch processing có thể commit từng nhóm để tránh transaction khổng lồ. Đổi lại, toàn bộ procedure không còn atomic như một transaction duy nhất. Cần thiết kế restart/idempotency.

---

## 20. DDL trong PL/pgSQL và dynamic SQL

### 20.1. DDL tĩnh trong function

DDL thông thường có thể được thực thi trong function nếu command được phép trong transaction hiện tại và không vi phạm restriction khác. Function vẫn không thể tự kết thúc transaction.

### 20.2. Dynamic SQL

~~~sql
DO $$
BEGIN
    EXECUTE
        'ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS source_tag TEXT';
END;
$$;
~~~

EXECUTE cho phép xây dựng command động. Nó không bỏ qua transaction restrictions: nếu command không được phép trong transaction block, chạy qua EXECUTE vẫn thất bại.

### 20.3. Identifier quoting

Khi xây DDL động, dùng format với %I cho identifiers và %L cho literals.

~~~sql
DO $$
DECLARE
    v_table_name TEXT := 'orders';
BEGIN
    EXECUTE format(
        'ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS migration_note TEXT',
        v_table_name
    );
END;
$$;
~~~

Không nối raw user input vào SQL command.

### 20.4. Dynamic command và permissions

Security definer functions cần kiểm soát search_path, ownership, schema qualification và identifier quoting. DDL động có thể mở ra privilege escalation nếu dùng input không tin cậy.

### 20.5. Lệnh non-transactional không thể được hợp thức hóa bằng EXECUTE

Không thể gọi CREATE INDEX CONCURRENTLY, VACUUM hoặc ALTER SYSTEM bên trong function/DO đang chạy trong transaction block rồi kỳ vọng command sẽ chạy độc lập.

---

## 21. Migration atomic và non-atomic

### 21.1. Atomic migration

Một migration được chạy trong một transaction và chỉ được đánh dấu applied sau COMMIT.

~~~sql
BEGIN;

ALTER TABLE public.orders
    ADD COLUMN source_system TEXT;

CREATE INDEX orders_source_system_idx
    ON public.orders(source_system);

INSERT INTO public.schema_migration_log(version, applied_at)
VALUES ('2026_11_add_source_system', clock_timestamp());

COMMIT;
~~~

Nếu bất kỳ bước nào thất bại, rollback cả schema changes và migration ledger update.

### 21.2. Non-atomic migration

Một migration chứa command không được chạy trong transaction block cần được cấu hình non-transactional hoặc chia thành các bước độc lập.

Ví dụ:

~~~sql
CREATE INDEX CONCURRENTLY orders_customer_id_idx
    ON public.orders(customer_id);
~~~

Migration runner không được tự bọc command này bằng BEGIN/COMMIT.

### 21.3. Không trộn hai kiểu một cách vô thức

Một script có CREATE INDEX CONCURRENTLY cùng nhiều ALTER TABLE transactional có thể thất bại nếu tool bọc toàn bộ script. Tách command ra migration riêng, ghi rõ transaction mode.

### 21.4. Migration ledger

Với non-atomic migration, cần xác định thời điểm ghi ledger:
- Chỉ đánh dấu hoàn tất sau khi command thành công và post-check pass.
- Nếu command fail nhưng để lại invalid object, ghi trạng thái failed/pending theo migration tool.
- Recovery script phải biết cách kiểm tra object đã tồn tại, valid hay đang ở trạng thái dở dang.

### 21.5. Idempotency

Migration non-atomic có thể cần chạy lại. Thiết kế precondition/postcondition, kiểm tra catalog và cleanup rõ ràng. IF NOT EXISTS không đảm bảo object hiện hữu ở trạng thái đúng.

### 21.6. Expand/contract

Với application deploy không downtime:
1. Expand schema theo hướng backward-compatible.
2. Deploy application đọc/ghi schema mới.
3. Backfill dữ liệu theo batches.
4. Validate.
5. Switch reads/writes.
6. Contract schema cũ trong release riêng.

Concurrent index và non-transactional steps thường nằm ở phase riêng.

---

## 22. DDL locks và transaction duration

Transactional DDL có thể an toàn về atomicity nhưng vẫn ảnh hưởng availability do locks.

### 22.1. ALTER TABLE

Nhiều ALTER TABLE forms cần ACCESS EXCLUSIVE lock. Một số operations có lock nhẹ hơn hoặc có thể thực hiện theo phase. Kiểm tra command cụ thể và version.

### 22.2. Lock giữ tới transaction end

Nếu ALTER TABLE lấy lock rồi transaction tiếp tục chạy backfill lâu, lock có thể được giữ suốt thời gian còn lại.

### 22.3. lock_timeout

Có thể đặt timeout trước DDL:

~~~sql
BEGIN;

SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '5min';

ALTER TABLE public.orders
    ADD COLUMN source_tag TEXT;

COMMIT;
~~~

Nếu lock không lấy được trong 3 giây, statement thất bại. Transaction cần được rollback hoặc xử lý theo savepoint.

### 22.4. SET LOCAL

SET LOCAL chỉ áp dụng trong transaction hiện tại và hết hiệu lực khi transaction kết thúc. Nó phù hợp để giới hạn migration session.

### 22.5. Long-running transactions

Một transaction DDL dài có thể:
- Giữ locks.
- Giữ snapshot.
- Block deploy/queries khác.
- Làm autovacuum cleanup bị trì hoãn.
- Tăng dead tuples và bloat.
- Tăng recovery/rollback duration.

### 22.6. Observe blockers

Dùng pg_stat_activity, pg_blocking_pids và pg_locks để xem migration đang chờ hoặc đang block ai.

---

## 23. Constraint migration theo nhiều phase

PostgreSQL hỗ trợ một số cách thêm constraint để giảm tác động lên table lớn.

### 23.1. ADD CONSTRAINT NOT VALID

~~~sql
ALTER TABLE public.orders
    ADD CONSTRAINT orders_amount_nonnegative
    CHECK (amount >= 0)
    NOT VALID;
~~~

Constraint được thêm nhưng dữ liệu hiện tại chưa được scan/validate đầy đủ. Các writes mới vẫn phải tuân theo constraint theo semantics của command.

### 23.2. VALIDATE CONSTRAINT

~~~sql
ALTER TABLE public.orders
    VALIDATE CONSTRAINT orders_amount_nonnegative;
~~~

Validation chạy riêng, thường cho phép concurrency tốt hơn so với việc thêm constraint đã validated ngay từ đầu, nhưng vẫn cần locks và resource planning.

### 23.3. Foreign key

Foreign key cũng hỗ trợ NOT VALID rồi VALIDATE CONSTRAINT trong các tình huống phù hợp. Đây là cách giảm thời gian giữ lock mạnh khi thêm constraint cho table lớn.

### 23.4. Chọn transaction boundary

ADD CONSTRAINT và VALIDATE CONSTRAINT có thể nằm trong transaction theo command semantics, nhưng nên tách migration phases để kiểm soát duration và lock impact.

### 23.5. Post-check

Kiểm tra pg_constraint.convalidated và constraint definition sau migration.

---

## 24. Backfill và batch transaction

Backfill dữ liệu lớn không nên luôn nằm trong một transaction duy nhất.

### 24.1. Vì sao batch?

- Giới hạn WAL burst.
- Giảm thời gian giữ locks/snapshots.
- Cho phép pause/resume.
- Giảm rollback cost.
- Có thể throttle theo application load.

### 24.2. Mẫu batch

~~~sql
WITH batch AS (
    SELECT id
    FROM public.orders
    WHERE source_tag IS NULL
    ORDER BY id
    LIMIT 1000
    FOR UPDATE SKIP LOCKED
)
UPDATE public.orders AS o
SET source_tag = 'legacy'
FROM batch
WHERE o.id = batch.id;
~~~

Application/job chạy lặp statement này trong các transactions nhỏ cho tới khi không còn rows cần xử lý.

### 24.3. Idempotency

Điều kiện WHERE source_tag IS NULL giúp chạy lại mà không ghi đè các rows đã backfill. Thực tế có thể cần checkpoint/progress table.

### 24.4. Transaction control

Mỗi batch commit riêng. Nếu một batch thất bại, rollback batch đó và retry theo policy; các batches trước vẫn đã commit.

### 24.5. Procedure có thể commit từng batch

Procedure có thể điều khiển transaction trong các điều kiện CALL phù hợp. Cần tránh EXCEPTION block quanh phần muốn COMMIT và kiểm thử restart semantics.

---

## 25. psql và migration runner

### 25.1. psql ON_ERROR_STOP

~~~text
\set ON_ERROR_STOP on
~~~

Khi một command lỗi, psql dừng script theo cấu hình. Với explicit transaction, client cần đảm bảo transaction được rollback và exit status được xử lý.

### 25.2. psql single-transaction

~~~bash
psql --single-transaction --file migration.sql appdb
~~~

psql option này bọc script trong một transaction duy nhất. Nó không phù hợp nếu file chứa command bị cấm trong transaction block như CREATE INDEX CONCURRENTLY hoặc VACUUM.

### 25.3. Autocommit

Với autocommit bật, command non-transactional có thể chạy độc lập. Tuy nhiên, migration runner có thể tự quản lý transaction riêng, nên phải đọc config của tool.

### 25.4. Migration framework

Nhiều frameworks hỗ trợ:
- Transaction per migration.
- Transaction per statement.
- Non-transactional migration marker.
- Explicit transaction control.
- Retry hoặc resume.
- Migration history table.

Dùng đúng cơ chế của framework thay vì chèn BEGIN/COMMIT tùy tiện.

### 25.5. Migration file tách riêng

Tạo file riêng cho concurrent index, vacuum hoặc cluster-level operation. Ghi chú rõ file không được chạy trong transaction.

### 25.6. Script fail giữa chừng

Ghi lại:
- Exit code.
- Command cuối cùng thành công.
- Transaction state.
- Object state trong catalogs.
- External side effects đã thực hiện.
- Có thể retry an toàn hay cần cleanup.

---

## 26. Phân biệt DDL rollback với sequence và external side effects

Transactional DDL không có nghĩa mọi thay đổi phát sinh từ một script đều quay lại.

### 26.1. Sequence values

nextval không rollback theo transaction thông thường. Nếu script lấy sequence value rồi rollback, giá trị đã dùng có thể bị bỏ qua.

~~~sql
BEGIN;

SELECT nextval('public.order_id_seq');

ROLLBACK;
~~~

Sequence có thể vẫn tăng dù transaction rollback.

### 26.2. External calls

Một function/extension có thể gửi request tới hệ thống ngoài, ghi file hoặc tạo side effect không nằm trong PostgreSQL transaction. Rollback local database không thể tự đảo ngược side effect đó.

### 26.3. Notifications

NOTIFY được gửi tới listeners theo transaction commit semantics; notification từ transaction rollback không được phát như một committed notification.

### 26.4. Advisory locks

Session-level advisory locks không tự giải phóng khi transaction rollback; transaction-level advisory locks có lifecycle theo transaction. Cần phân biệt khi migration script dùng advisory locks.

### 26.5. Temporary objects

Temporary table/object có lifecycle phụ thuộc ON COMMIT behavior và session. Rollback transaction có thể rollback việc tạo object; nhưng temp objects đã commit có thể tồn tại tới session end.

### 26.6. Kết luận thực hành

Khi thiết kế migration, liệt kê side effects theo hai nhóm:
- PostgreSQL transactional state.
- External/non-transactional state.

Mỗi external side effect cần retry/compensation plan riêng.

---

## 27. Xử lý lỗi trong migration script

### 27.1. Atomic transaction

~~~sql
BEGIN;

ALTER TABLE public.orders
    ADD COLUMN source_system TEXT;

CREATE INDEX orders_source_system_idx
    ON public.orders(source_system);

COMMIT;
~~~

Nếu CREATE INDEX thất bại, transaction abort và ALTER TABLE cũng không commit.

### 27.2. Savepoint quanh bước tùy chọn

~~~sql
BEGIN;

ALTER TABLE public.orders
    ADD COLUMN source_system TEXT;

SAVEPOINT optional_index;

CREATE INDEX orders_source_system_idx
    ON public.orders(source_system);

-- Nếu CREATE INDEX lỗi:
-- ROLLBACK TO SAVEPOINT optional_index;

COMMIT;
~~~

Trong script thực tế, client/PL block phải bắt lỗi và thực hiện ROLLBACK TO SAVEPOINT. SQL script thuần không tự chuyển tiếp sau error khi transaction đã aborted.

### 27.3. Không nuốt lỗi rồi đánh dấu migration thành công

Nếu handler bắt lỗi nhưng migration ledger vẫn ghi success, hệ thống sẽ tin rằng schema đã hoàn tất dù object còn thiếu.

### 27.4. Precondition và postcondition

Trước migration:
- Kiểm tra object tồn tại hay không.
- Kiểm tra version/state.
- Kiểm tra dependencies.
- Kiểm tra lock availability.

Sau migration:
- Kiểm tra schema definition.
- Kiểm tra index validity.
- Kiểm tra constraint validation.
- Kiểm tra application queries.
- Kiểm tra migration ledger.

### 27.5. Recovery script

Viết script riêng để xử lý trạng thái partial của non-atomic migration. Script phải phân biệt absent, valid, invalid, ready-but-invalid và object có definition sai.

---

## 28. Version-specific và extension-specific exceptions

### 28.1. ALTER TYPE ADD VALUE

Như đã trình bày, PostgreSQL 12+ cho phép thêm enum label trong transaction, nhưng không dùng được label mới cho tới khi commit. Version cũ có restriction khác.

### 28.2. CREATE/DROP SUBSCRIPTION

Các options liên quan connect và replication slot ảnh hưởng transaction restrictions. Kiểm tra docs đúng target major version và publisher state.

### 28.3. Extension scripts

CREATE EXTENSION hoặc ALTER EXTENSION UPDATE có thể chạy trong transaction, nhưng script của extension có thể chứa command không hỗ trợ transaction. Extension vendor cần mô tả quy trình riêng.

### 28.4. Concurrent operations

Các command có từ khóa CONCURRENTLY thường có transaction restrictions hoặc semantics đặc biệt. Không suy luận tất cả command có chữ CONCURRENTLY đều giống nhau; kiểm tra từng command.

### 28.5. New PostgreSQL releases

Các major releases có thể bổ sung command/option hoặc thay đổi transaction support. Compatibility matrix nên ghi command behavior theo source/target version.

---

## 29. Kiểm tra transaction state và command behavior

### 29.1. Xem transaction state trong client

psql hiển thị prompt khác nhau khi transaction mở hoặc aborted. Prompt có thể giúp nhận ra trạng thái, nhưng automation nên kiểm tra exit status và server errors.

### 29.2. SQLSTATE cho command restriction

Một command bị cấm trong transaction block thường trả SQLSTATE 25001 (active_sql_transaction). Ghi message đầy đủ để xác định command cụ thể.

### 29.3. Kiểm tra transaction ID/current state

PostgreSQL không cung cấp một SQL boolean đơn giản thay thế hoàn toàn trạng thái client transaction trong mọi context. Dùng client driver transaction API, psql prompt và server error diagnostics.

### 29.4. Kiểm tra DDL objects

Dùng pg_class, pg_index, pg_constraint, pg_extension và các catalog tương ứng để xác nhận kết quả thay đổi.

### 29.5. Không chỉ dựa vào command exit message

Một command concurrent có thể thất bại sau một số phase và để lại object cần cleanup. Luôn kiểm tra catalog postcondition.

---

## 30. Quy trình thiết kế migration có DDL

### Bước 1: Phân loại từng command

Đánh dấu transactional, non-transactional, version-specific và external side effect.

### Bước 2: Xác định transaction boundaries

Gom những DDL cần atomic vào transaction nhỏ. Tách concurrent index, VACUUM, database/tablespace provisioning và ALTER SYSTEM.

### Bước 3: Đánh giá lock behavior

Xem lock level, table size, traffic, transaction duration và blocker risk.

### Bước 4: Đặt timeout phù hợp

Dùng lock_timeout và statement_timeout trong migration session. Xác định retry policy.

### Bước 5: Thiết kế failure recovery

Với transactional steps, rollback toàn transaction hoặc savepoint. Với non-transactional steps, kiểm tra partial state và cleanup/retry.

### Bước 6: Quản lý migration ledger

Chỉ ghi migration success sau postconditions. Có trạng thái pending/failed rõ cho bước không atomic.

### Bước 7: Rehearsal

Chạy trên clone với dataset/extension/tool versions tương đương production. Đo duration, locks, WAL, I/O và application impact.

### Bước 8: Cutover

Chạy theo thứ tự dependency, xác nhận từng checkpoint và giữ rollback path.

### Bước 9: Verify

Kiểm tra schema, indexes, constraints, application compatibility, background jobs và monitoring.

### Bước 10: Record

Lưu command outputs, version, start/end time, migration ID, operator và recovery notes.

---

## 31. Runbook: lỗi 25001 do lệnh không được chạy trong transaction

### Bước 1: Xác định command

Đọc SQLSTATE và message. Xác định command có yêu cầu chạy ngoài transaction block không.

### Bước 2: Xác định ai mở transaction

Kiểm tra:
- BEGIN trong file SQL.
- psql --single-transaction.
- Migration framework transaction-per-migration.
- ORM/session transaction.
- Procedure/DO caller context.

### Bước 3: Tách migration

Chuyển command sang file/step non-transactional riêng. Đảm bảo runner không tự bọc transaction.

### Bước 4: Kiểm tra state trước khi retry

Với concurrent index, kiểm tra index có tồn tại và indisvalid/indisready. Với subscription, kiểm tra local subscription và remote slot. Với database/tablespace, kiểm tra object tồn tại.

### Bước 5: Chạy command độc lập

Dùng autocommit connection hoặc migration mode phù hợp. Không chạy qua function/DO đang ở transaction.

### Bước 6: Post-check

Xác nhận command hoàn tất và external side effects đúng. Chỉ sau đó đánh dấu migration applied.

---

## 32. Runbook: concurrent index build thất bại

### Bước 1: Ghi lỗi

Lưu SQLSTATE, message, query, table/index name và thời điểm.

### Bước 2: Kiểm tra index flags

~~~sql
SELECT
    c.oid::regclass AS index_name,
    i.indisready,
    i.indisvalid,
    i.indislive
FROM pg_catalog.pg_index AS i
JOIN pg_catalog.pg_class AS c
    ON c.oid = i.indexrelid
WHERE c.oid = to_regclass('public.orders_customer_id_idx');
~~~

### Bước 3: Kiểm tra nguyên nhân

- Duplicate values nếu unique index.
- Deadlock/lock timeout.
- Long-running transactions/snapshots.
- Storage full hoặc I/O error.
- Cancel signal hoặc statement timeout.
- Concurrent DDL conflict.

### Bước 4: Xác định write maintenance state

Nếu indisready=true nhưng indisvalid=false, index có thể vẫn được duy trì bởi writes dù planner không dùng như index hợp lệ. Đánh giá chi phí và cleanup.

### Bước 5: Cleanup

Sau khi xác nhận đúng index và không có dependency constraint, chạy DROP INDEX CONCURRENTLY ngoài transaction block.

### Bước 6: Sửa nguyên nhân và retry

Không lặp lại blind retry khi nguyên nhân chưa được xử lý.

### Bước 7: Verify

Xác nhận indisvalid=true, index definition đúng và query plan/application behavior phù hợp.

---

## 33. Runbook: migration transaction bị aborted

### Bước 1: Dừng các statements tiếp theo

Không tiếp tục gửi DDL/DML vào transaction aborted.

### Bước 2: Lấy lỗi đầu tiên

Ghi SQLSTATE, message, detail, hint, constraint/table và statement gây lỗi.

### Bước 3: Kiểm tra savepoint

Nếu script có savepoint trước command, ROLLBACK TO SAVEPOINT phù hợp. Nếu không, rollback toàn transaction.

### Bước 4: Xác nhận state

Kiểm tra transaction đã kết thúc hoặc quay về savepoint. Không giả định client tự rollback.

### Bước 5: Kiểm tra catalog

Xác nhận các objects trước transaction/after savepoint còn đúng và không có partial state ngoài transaction.

### Bước 6: Sửa migration

Sửa nguyên nhân và thử lại trên staging. Không sửa trực tiếp production catalog để làm migration runner "xanh" nếu không có recovery plan.

---

## 34. Lab 1: transactional DDL và rollback

Lab dùng database development.

### 34.1. Tạo object trong transaction

~~~sql
BEGIN;

CREATE TABLE public.ddl_tx_lab (
    id INTEGER PRIMARY KEY,
    value TEXT
);

INSERT INTO public.ddl_tx_lab VALUES (1, 'created in transaction');

SELECT to_regclass('public.ddl_tx_lab');

ROLLBACK;
~~~

### 34.2. Xác nhận rollback

~~~sql
SELECT to_regclass('public.ddl_tx_lab');
~~~

Kết quả là NULL nếu table không tồn tại trước lab.

### 34.3. Thử ALTER TABLE rollback

~~~sql
BEGIN;

CREATE TABLE public.ddl_alter_lab (id INTEGER PRIMARY KEY);

ALTER TABLE public.ddl_alter_lab ADD COLUMN note TEXT;

ROLLBACK;
~~~

### 34.4. Kết luận

DDL thông thường tham gia transaction và được rollback cùng các thay đổi khác.

---

## 35. Lab 2: savepoint và transaction-aborted state

### 35.1. Tạo bảng

~~~sql
CREATE TABLE public.savepoint_lab (
    id INTEGER PRIMARY KEY,
    code TEXT UNIQUE
);
~~~

### 35.2. Tạo savepoint

~~~sql
BEGIN;

INSERT INTO public.savepoint_lab VALUES (1, 'A');

SAVEPOINT before_duplicate;

INSERT INTO public.savepoint_lab VALUES (2, 'A');
~~~

Statement thứ hai vi phạm unique constraint.

### 35.3. Rollback to savepoint

~~~sql
ROLLBACK TO SAVEPOINT before_duplicate;

INSERT INTO public.savepoint_lab VALUES (2, 'B');

COMMIT;
~~~

### 35.4. Kiểm tra kết quả

~~~sql
TABLE public.savepoint_lab;
~~~

Row đầu còn; row duplicate thất bại được rollback; row B được insert sau khi phục hồi.

### 35.5. Kết luận

Savepoint cho phép phục hồi phần transaction sau mốc đã chọn mà không rollback toàn bộ transaction.

---

## 36. Lab 3: phân biệt CREATE INDEX và CREATE INDEX CONCURRENTLY

### 36.1. Tạo dữ liệu lab

~~~sql
CREATE TABLE public.index_tx_lab (
    id BIGINT PRIMARY KEY,
    category INTEGER NOT NULL,
    payload TEXT
);

INSERT INTO public.index_tx_lab(id, category, payload)
SELECT g, g % 100, repeat('x', 100)
FROM generate_series(1, 200000) AS g;
~~~

### 36.2. Tạo index thông thường trong transaction

~~~sql
BEGIN;

CREATE INDEX index_tx_lab_category_idx
    ON public.index_tx_lab(category);

ROLLBACK;
~~~

### 36.3. Xác nhận index không tồn tại

~~~sql
SELECT to_regclass('public.index_tx_lab_category_idx');
~~~

### 36.4. Tạo concurrent index độc lập

~~~sql
CREATE INDEX CONCURRENTLY index_tx_lab_category_idx
    ON public.index_tx_lab(category);
~~~

Chạy ngoài BEGIN/COMMIT.

### 36.5. Kiểm tra validity

~~~sql
SELECT
    c.oid::regclass AS index_name,
    i.indisready,
    i.indisvalid
FROM pg_catalog.pg_index AS i
JOIN pg_catalog.pg_class AS c
    ON c.oid = i.indexrelid
WHERE c.oid = to_regclass('public.index_tx_lab_category_idx');
~~~

### 36.6. Kết luận

Hai lệnh tạo cùng loại index nhưng transaction restrictions và concurrency behavior khác nhau.

---

## 37. Lab 4: quan sát lỗi CREATE INDEX CONCURRENTLY và cleanup

Lab này chỉ thực hiện trên bảng thử nghiệm. Không cố tình tạo lỗi trên production.

### 37.1. Tạo duplicate data

~~~sql
CREATE TABLE public.concurrent_failure_lab (
    id INTEGER,
    value TEXT
);

INSERT INTO public.concurrent_failure_lab VALUES
    (1, 'one'),
    (1, 'duplicate'),
    (2, 'two');
~~~

### 37.2. Thử unique concurrent index

~~~sql
CREATE UNIQUE INDEX CONCURRENTLY concurrent_failure_lab_id_uq
    ON public.concurrent_failure_lab(id);
~~~

Lệnh thất bại vì duplicate values và có thể để lại invalid index.

### 37.3. Kiểm tra catalog

~~~sql
SELECT
    c.oid::regclass AS index_name,
    i.indisready,
    i.indisvalid,
    i.indislive
FROM pg_catalog.pg_index AS i
JOIN pg_catalog.pg_class AS c
    ON c.oid = i.indexrelid
WHERE c.oid = to_regclass(
    'public.concurrent_failure_lab_id_uq'
);
~~~

### 37.4. Xóa duplicate

~~~DELETE FROM public.concurrent_failure_lab
WHERE ctid NOT IN (
    SELECT min(ctid)
    FROM public.concurrent_failure_lab
    GROUP BY id
);
~~~

### 37.5. Drop invalid index

~~~DROP INDEX CONCURRENTLY public.concurrent_failure_lab_id_uq;
~~~

### 37.6. Tạo lại và xác nhận

~~~sql
CREATE UNIQUE INDEX CONCURRENTLY concurrent_failure_lab_id_uq
    ON public.concurrent_failure_lab(id);
~~~

Kiểm tra indisvalid=true. Lab minh họa vì sao cần catalog post-check sau failure.

---

## 38. Lab 5: PL/pgSQL EXCEPTION và diagnostics

### 38.1. Chuẩn bị bảng

~~~sql
CREATE TABLE public.exception_lab (
    id INTEGER PRIMARY KEY,
    value TEXT UNIQUE
);
~~~

### 38.2. Tạo handler

~~~sql
DO $$
DECLARE
    v_state TEXT;
    v_message TEXT;
BEGIN
    INSERT INTO public.exception_lab VALUES (1, 'first');

    BEGIN
        INSERT INTO public.exception_lab VALUES (2, 'first');

    EXCEPTION
        WHEN unique_violation THEN
            GET STACKED DIAGNOSTICS
                v_state = RETURNED_SQLSTATE,
                v_message = MESSAGE_TEXT;

            RAISE NOTICE 'Caught %, %', v_state, v_message;
    END;

    INSERT INTO public.exception_lab VALUES (3, 'third');
END;
$$;
~~~

### 38.3. Kiểm tra rows

~~~sql
TABLE public.exception_lab;
~~~

Row duplicate trong inner block không được insert; outer block vẫn tiếp tục.

### 38.4. Thử RAISE lại

Thay handler bằng RAISE; để quan sát lỗi truyền ra caller và toàn DO statement thất bại.

### 38.5. Kết luận

EXCEPTION block tạo subtransaction, rollback database changes bên trong block bị lỗi và cho phép outer code tiếp tục nếu handler xử lý đúng.

---

## 39. Bài tập thực hành

### Bài 1 — Transactional DDL

Giải thích transactional DDL và nêu ít nhất năm DDL commands thường có thể rollback.

### Bài 2 — Autocommit

Phân biệt psql autocommit với explicit BEGIN/COMMIT.

### Bài 3 — Atomic migration

Viết migration tạo table, thêm constraint và ghi migration ledger trong một transaction.

### Bài 4 — Transaction aborted

Một INSERT gây unique_violation trong explicit transaction. Vì sao SELECT tiếp theo cũng lỗi?

### Bài 5 — Savepoint

Viết script tạo savepoint, gây lỗi constraint, rollback tới savepoint và tiếp tục.

### Bài 6 — SQLSTATE

Tra cứu SQLSTATE cho unique violation, foreign key, deadlock, serialization failure và active transaction restriction.

### Bài 7 — Non-transactional commands

Liệt kê các command không được chạy trong transaction block và phân nhóm theo cluster, filesystem, maintenance và concurrent index.

### Bài 8 — CREATE DATABASE

Thiết kế deployment tạo database rồi chạy schema migration. Vì sao cần hai bước?

### Bài 9 — TABLESPACE

Nêu filesystem prerequisites và rủi ro khi tạo/drop tablespace.

### Bài 10 — ALTER SYSTEM

Giải thích vì sao ALTER SYSTEM không rollback cùng DDL và vì sao shared_buffers cần restart.

### Bài 11 — VACUUM

Phân biệt VACUUM, VACUUM ANALYZE và ANALYZE về transaction restrictions.

### Bài 12 — CREATE INDEX

So sánh CREATE INDEX với CREATE INDEX CONCURRENTLY về locks và transaction support.

### Bài 13 — Concurrent index failure

Một CREATE UNIQUE INDEX CONCURRENTLY thất bại vì duplicate data. Viết query kiểm tra indisvalid/indisready và cleanup plan.

### Bài 14 — IF NOT EXISTS

Vì sao CREATE INDEX CONCURRENTLY IF NOT EXISTS không tự phục hồi invalid index cùng tên?

### Bài 15 — DROP INDEX CONCURRENTLY

Nêu các hạn chế của DROP INDEX CONCURRENTLY và xử lý khi index backing constraint.

### Bài 16 — REINDEX

So sánh REINDEX và REINDEX CONCURRENTLY. Nêu lý do chọn mỗi phương thức.

### Bài 17 — Subscription

Vì sao CREATE SUBSCRIPTION với connect=true có transaction restriction? External side effect nào cần kiểm tra?

### Bài 18 — Enum version

So sánh ALTER TYPE ADD VALUE trên PostgreSQL 11 và PostgreSQL 12 trở lên.

### Bài 19 — Enum visibility

Trên PostgreSQL 12+, vì sao enum label mới không thể dùng trước khi transaction chứa ALTER TYPE commit?

### Bài 20 — PL/pgSQL exception

Giải thích vì sao block có EXCEPTION tạo subtransaction.

### Bài 21 — Variables

Khi exception xảy ra trong PL/pgSQL block, database changes và PL/pgSQL variables có rollback giống nhau không?

### Bài 22 — WHEN OTHERS

Nêu các condition không được WHEN OTHERS bắt và rủi ro khi nuốt mọi lỗi.

### Bài 23 — Diagnostics

Viết handler dùng GET STACKED DIAGNOSTICS để lấy SQLSTATE, message, detail và constraint name.

### Bài 24 — ON CONFLICT

Khi nào nên dùng ON CONFLICT thay vì bắt unique_violation?

### Bài 25 — Function vs procedure

Phân biệt transaction control trong function, procedure và DO block.

### Bài 26 — Exception và COMMIT

Vì sao procedure không thể COMMIT khi đang nằm trong EXCEPTION block?

### Bài 27 — Dynamic SQL

Viết DDL động dùng format %I. Vì sao EXECUTE không bỏ qua transaction restrictions?

### Bài 28 — Migration runner

Một framework tự bọc mỗi migration trong BEGIN/COMMIT. Cách tổ chức migration có CREATE INDEX CONCURRENTLY?

### Bài 29 — psql -1

Vì sao psql --single-transaction không phù hợp với script có VACUUM hoặc CREATE INDEX CONCURRENTLY?

### Bài 30 — Lock timeout

Viết migration dùng SET LOCAL lock_timeout và statement_timeout. Giải thích cách xử lý khi lock timeout xảy ra.

### Bài 31 — Constraint NOT VALID

Thiết kế hai phase ADD CONSTRAINT NOT VALID và VALIDATE CONSTRAINT cho table lớn.

### Bài 32 — Batch backfill

Viết mẫu batch update dùng FOR UPDATE SKIP LOCKED và giải thích lợi ích transaction nhỏ.

### Bài 33 — Sequence rollback

Vì sao nextval có thể tăng dù transaction rollback?

### Bài 34 — External side effects

Một migration gọi external service rồi rollback. Vì sao remote side effect không tự biến mất?

### Bài 35 — Migration ledger

Thiết kế trạng thái migration cho một non-atomic concurrent index build có thể fail giữa chừng.

### Bài 36 — Invalid index recovery

Viết runbook từ failure message tới catalog inspection, duplicate cleanup, drop invalid index và retry.

### Bài 37 — Subscription recovery

Một subscription đã tạo local nhưng publisher slot state không như mong đợi. Nêu cách điều tra trước khi drop/recreate.

### Bài 38 — DDL blocking

Một ALTER TABLE đang chờ lock trong 2 phút. Những session/transaction nào cần xem và cách đặt lock_timeout?

### Bài 39 — Rehearsal

Thiết kế staging rehearsal cho migration gồm transactional ALTER TABLE, CREATE INDEX CONCURRENTLY, VACUUM và extension update.

### Bài 40 — End-to-end migration

Một release cần thêm enum label, tạo concurrent unique index, backfill hàng triệu rows, thêm CHECK constraint, chạy VACUUM và cập nhật migration ledger. Chia thành phases, transaction boundaries, validation, retry/cleanup và rollback plan. Nêu khác biệt nếu source server là PostgreSQL 11 so với PostgreSQL 12+.

---

## 40. Checklist trước khi chạy migration

| Hạng mục | Câu hỏi cần trả lời |
| --- | --- |
| PostgreSQL version | Source và target major version nào? |
| Command classification | Command transactional hay bị cấm trong transaction block? |
| Version-specific behavior | Có behavior thay đổi theo version không? |
| Migration runner | Tool có tự BEGIN/COMMIT không? |
| Autocommit | Client có autocommit hay single-transaction mode? |
| Transaction scope | Nhóm DDL nào cần atomic? |
| Savepoints | Có điểm phục hồi trước optional step không? |
| Error handling | SQLSTATE/condition nào được xử lý? |
| Non-transactional step | Đã tách file/runner mode chưa? |
| Concurrent index | Có kiểm tra validity và cleanup không? |
| Replication side effects | Slot/remote publisher state đã được kiểm tra? |
| ALTER SYSTEM | Config ownership và restart plan rõ chưa? |
| VACUUM | Có chạy ngoài transaction block không? |
| CREATE DATABASE | Có chạy riêng ở cluster scope không? |
| TABLESPACE | Filesystem path/owner/backup mapping sẵn sàng? |
| Lock behavior | Lock level và blockers dự kiến? |
| Timeouts | lock_timeout/statement_timeout phù hợp? |
| Backfill | Có chia batch và idempotent không? |
| DDL duration | Table size và maintenance window? |
| Data validation | Postconditions có thể kiểm chứng? |
| Migration ledger | Chỉ ghi success sau post-check? |
| Retry | Có thể chạy lại an toàn không? |
| Cleanup | Partial/invalid objects được xử lý ra sao? |
| External effects | Có compensation/reconciliation plan? |
| Backup | Restore point và rollback path? |
| Rehearsal | Đã chạy với dataset/tool versions tương đương? |
| Monitoring | Lock waits, WAL, I/O, latency được theo dõi? |
| Owner | Có người chịu trách nhiệm cho từng phase? |
| Audit | Command, timestamps, output và operator được lưu? |

## Kết luận

Transactional DDL cho phép PostgreSQL thay đổi schema theo cách nguyên tử: một transaction có thể tạo, sửa hoặc xóa nhiều objects rồi commit hoặc rollback cùng nhau. Tuy nhiên, một số commands như CREATE/DROP DATABASE, TABLESPACE, ALTER SYSTEM, VACUUM và concurrent index operations phải chạy ngoài transaction block. Các thao tác replication có side effects với remote slots và một số DDL có quy tắc phụ thuộc major version.

Những nguyên tắc cần nhớ:

1. **Phần lớn DDL thông thường là transactional.** Gom các thay đổi schema liên quan vào transaction nhỏ để giữ atomicity.
2. **SQL error làm transaction aborted.** Sau lỗi phải ROLLBACK hoặc ROLLBACK TO SAVEPOINT trước khi tiếp tục.
3. **Savepoint chỉ tạo điểm phục hồi.** Nó không commit transaction ngoài.
4. **Không phải command nào cũng chạy trong transaction block.** Tách CREATE/DROP DATABASE, TABLESPACE, ALTER SYSTEM, VACUUM và concurrent index operations.
5. **CREATE INDEX CONCURRENTLY không atomic theo cách DDL thường.** Nó có nhiều phase và có thể để lại invalid index sau failure.
6. **IF NOT EXISTS không đảm bảo object hiện có hợp lệ.** Kiểm tra catalog postconditions.
7. **Replication commands có external side effects.** Kiểm tra publisher slots và subscription state trước khi retry/drop.
8. **Enum DDL có khác biệt phiên bản.** PostgreSQL 12+ cho phép ADD VALUE trong transaction nhưng value mới chỉ dùng được sau commit.
9. **EXCEPTION block dùng subtransaction.** Database changes trong block lỗi được rollback, còn outer block có thể tiếp tục.
10. **Function và procedure có transaction permissions khác nhau.** Transaction control trong procedure/DO phụ thuộc call context và không được thực hiện bên trong exception subtransaction.
11. **Migration runner quyết định transaction boundary thực tế.** Kiểm tra framework, psql flags và autocommit.
12. **DDL có thể giữ locks tới COMMIT.** Giữ transaction ngắn, đặt timeout và quan sát blockers.
13. **Backfill lớn nên chia batch.** Thiết kế idempotency, progress và retry.
14. **External side effects cần recovery riêng.** Rollback PostgreSQL không đảo ngược remote calls hoặc mọi sequence effects.
15. **Post-check là bắt buộc với non-atomic steps.** Kiểm tra index validity, constraints, subscriptions, schema và migration ledger trước khi đánh dấu thành công.

Một migration an toàn bắt đầu bằng việc phân loại từng command, xác định transaction boundary, dự kiến locks và failure modes, rồi thiết kế cách xác minh hoặc phục hồi trạng thái. Khi biết rõ lệnh nào atomic và lệnh nào có ngoại lệ, bạn có thể triển khai thay đổi schema có kiểm soát mà không để migration runner vô tình biến một thao tác đặc biệt thành lỗi production.
