# Migration có phiên bản và quản lý lịch sử thay đổi trong PostgreSQL

## 1. Vì sao cần version hóa database migrations?

Một ứng dụng thay đổi theo thời gian: thêm bảng, đổi kiểu dữ liệu, tạo index, thêm constraint, tách cột, backfill dữ liệu hoặc xóa cấu trúc cũ. Những thay đổi đó cần được triển khai nhất quán qua môi trường development, test, staging và production.

Nếu mỗi lần deploy phải nhớ chạy một danh sách SQL thủ công, hệ thống rất dễ lệch trạng thái. Một môi trường có thể đã thêm cột, môi trường khác chưa có; một script có thể bị chạy hai lần; người vận hành không biết thay đổi nào đã áp dụng; rollback có thể không khôi phục được dữ liệu.

**Versioned migration** giải quyết vấn đề bằng cách lưu mỗi thay đổi database thành một migration có định danh và thứ tự rõ ràng. Công cụ migration đọc lịch sử đã áp dụng, xác định migration còn thiếu, kiểm tra tính toàn vẹn và thực thi theo thứ tự.

Quản lý lịch sử thay đổi cần trả lời được:
- Migration nào đã chạy trên database này?
- Chạy theo thứ tự nào, khi nào và bởi ai?
- File/script nào đã được áp dụng?
- Nội dung script có bị thay đổi sau khi triển khai không?
- Migration có thành công hay thất bại?
- Database schema thực tế có còn khớp với lịch sử không?
- Có thể phục hồi hoặc triển khai tiếp an toàn không?

```text
Source control
   |
   +-- V001__create_customers.sql
   +-- V002__add_customer_status.sql
   +-- V003__create_orders.sql
   |
   v
Migration runner
   |
   +-- Read migration files
   +-- Compare version/checksum with history
   +-- Serialize concurrent runners
   +-- Execute pending migrations
   +-- Record successful changes
   |
   v
PostgreSQL database
   |
   +-- Application schema
   +-- Migration history table
```

Migration versioning biến thay đổi schema thành một phần có thể review, test, audit và tái tạo của quy trình phát triển phần mềm.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích versioned migration và migration history.
2. Thiết kế cách đặt tên, đánh số và sắp thứ tự migration.
3. Phân biệt versioned migration, repeatable migration và baseline.
4. Hiểu checksum, immutability và validation.
5. Thiết kế bảng lịch sử migration và biết khi nào nên dùng công cụ chuyên dụng.
6. Đảm bảo migration chỉ chạy một lần trong nhiều deployment runners.
7. Quản lý migration transactional và non-transactional.
8. Hiểu lock, table rewrite và downtime do DDL.
9. Thiết kế expand-contract cho deployment không gián đoạn.
10. Backfill dữ liệu theo batch và có thể tiếp tục sau lỗi.
11. Kiểm tra migration trong CI/CD và nhiều môi trường.
12. Xử lý schema drift, failed migration và repair.
13. Lập kế hoạch rollback, roll-forward và recovery.
14. Quản lý roles, ownership, privileges và secrets.
15. Xây audit, monitoring, runbook và checklist cho migration.

---

## 2. Migration là gì?

Migration là một thay đổi có chủ đích đối với database schema hoặc dữ liệu, được lưu dưới dạng script hoặc change set có thể chạy lại trong các môi trường.

Ví dụ migration:
- Tạo bảng customers.
- Thêm cột status.
- Tạo index cho truy vấn thường dùng.
- Thêm foreign key.
- Chuyển dữ liệu từ cột cũ sang cột mới.
- Tách một bảng lớn thành hai bảng.
- Tạo view/materialized view.
- Thay đổi quyền truy cập.
- Xóa cột cũ sau khi ứng dụng đã chuyển sang cột mới.

### 2.1. Schema migration

Thay đổi cấu trúc database: tables, columns, indexes, constraints, types, functions, triggers, views, schemas và permissions.

### 2.2. Data migration

Thay đổi hoặc chuyển đổi dữ liệu hiện có, ví dụ chuẩn hóa phone numbers, backfill giá trị mới hoặc chuyển records sang cấu trúc khác.

### 2.3. Migration có thể kết hợp schema và data

Ví dụ thêm cột mới, backfill từ cột cũ rồi tạo constraint. Tuy nhiên nên cân nhắc chia thành nhiều bước để giới hạn lock, transaction duration và rủi ro.

### 2.4. Migration là một artifact được quản lý

Script cần nằm trong source control, được review, test, version hóa và có owner. Thay đổi trực tiếp production mà không ghi lại vào migration source tạo ra schema drift.

## 3. Migration history là gì?

Migration history là metadata ghi lại những migration đã được áp dụng vào một database.

Một history record thường có:
- Version hoặc change ID.
- Description.
- Tên file/script hoặc changelog.
- Checksum của nội dung.
- Người/công cụ thực thi.
- Thời điểm chạy.
- Thời gian thực thi.
- Trạng thái thành công/thất bại hoặc execution type.
- Phiên bản migration tool.

Công cụ có thể dùng bảng riêng trong schema quản trị, ví dụ schema flyway/liquibase hoặc schema do tổ chức quy định.

### 3.1. History trả lời trạng thái triển khai

Runner so sánh migrations trong source repository với history table để xác định việc cần làm.

### 3.2. History không phải bản sao của schema

Bảng history chỉ ghi nhận tool đã áp dụng script nào. Nó không chứng minh một DBA chưa sửa bảng thủ công hoặc một script đã tạo đúng cấu trúc dự kiến.

### 3.3. History là dữ liệu vận hành quan trọng

Không tùy tiện xóa, sửa hoặc truncate history table. Thao tác đó có thể khiến runner chạy lại migrations hoặc tin rằng migration chưa được áp dụng.

### 3.4. Mỗi database có lịch sử riêng

Development, staging và production thường có cùng migration source nhưng history khác nhau do tiến độ deploy. Không copy history table giữa môi trường để “làm cho giống nhau”.

## 4. Đánh số và đặt tên migration

Một naming convention rõ ràng giúp con người và tool đọc được thứ tự.

Ví dụ:

```text
V001__create_customers.sql
V002__add_customer_status.sql
V003__create_orders.sql
V004__add_orders_customer_index.sql
V005__backfill_customer_status.sql
```

Một convention khác dùng timestamp:

```text
V2026111401__create_customers.sql
V2026111402__add_customer_status.sql
V2026111501__create_orders.sql
```

### 4.1. Version phải duy nhất

Không để hai scripts có cùng version. Nếu có hai branches tạo cùng version, cần giải quyết collision trước khi merge/deploy.

### 4.2. Không sắp xếp version dưới dạng text tùy tiện

Nếu tool so sánh version theo numeric components, 1.10 có thể được hiểu sau 1.9. Nếu tự viết runner và so sánh text lexicographically, thứ tự có thể sai. Dùng version parser đúng quy tắc.

### 4.3. Chọn một convention và giữ ổn định

Có thể dùng sequence tăng dần, timestamp hoặc semantic components. Tránh trộn nhiều kiểu mà không có quy tắc.

### 4.4. Description nên ngắn và thể hiện mục đích

Tên như add_customer_status rõ hơn update_db_2. Không đưa secrets hoặc thông tin nhạy cảm vào tên file.

### 4.5. File name là một phần identity

Khi tool lưu script name trong history, rename file sau khi deploy có thể làm validation fail hoặc gây khó audit. Giữ tên ổn định.

## 5. Versioned migrations và repeatable migrations

Hai nhóm migration thường gặp trong công cụ như Flyway:

| Loại | Đặc điểm | Ví dụ |
|---|---|---|
| Versioned | Có version duy nhất, chạy một lần theo thứ tự | Tạo bảng, thêm cột, đổi constraint |
| Repeatable | Không có version tuần tự, chạy lại khi checksum thay đổi | Tạo lại view/function/procedure |

### 5.1. Versioned migration

Sau khi đã áp dụng ở một môi trường dùng chung, coi file là immutable. Thay đổi tiếp theo được ghi bằng migration version mới.

### 5.2. Repeatable migration

Phù hợp với objects có thể tạo lại theo định nghĩa mới, như một số views hoặc functions. Cần thiết kế script idempotent hoặc dùng cơ chế replace phù hợp.

### 5.3. Không dùng repeatable để che giấu data migration

Một script backfill dữ liệu không nên tự chạy lại chỉ vì checksum thay đổi. Dùng versioned migration hoặc job có checkpoint/idempotency rõ ràng.

### 5.4. Công cụ có terminology khác nhau

Liquibase dùng changelog và changeset; Flyway dùng versioned/repeatable migrations. Hiểu semantics của tool đang dùng, không áp tên gọi của tool này sang tool khác.

## 6. Migration phải immutable sau khi đã áp dụng

Một nguyên tắc cốt lõi: **không sửa migration versioned đã chạy trên môi trường dùng chung**.

Ví dụ:
- V001 đã tạo bảng customers trên staging.
- Sau đó phát hiện thiếu cột email.
- Không sửa V001 để thêm email.
- Tạo V006__add_customer_email.sql.

### 6.1. Vì sao sửa file cũ nguy hiểm?

Development mới có thể chạy file đã sửa, còn production đã chạy nội dung cũ. Hai database cùng ghi nhận V001 nhưng schema thực tế khác nhau.

### 6.2. Checksum phát hiện thay đổi

Tool có thể lưu checksum khi áp dụng. Khi file hiện tại khác nội dung đã chạy, validation báo checksum mismatch.

### 6.3. Không “fix checksum” để bỏ qua nguyên nhân

Repair/checksum update chỉ nên thực hiện theo quy trình có kiểm tra schema và history. Nó không tự làm schema trở lại đúng.

### 6.4. Migration mới sửa kết quả cũ

Tạo migration tiếp theo để bổ sung/correct schema. Giữ lịch sử nguyên vẹn để audit và tái tạo môi trường.

## 7. Checksum và validation

Checksum là fingerprint tính từ nội dung migration file. Công cụ có thể dùng checksum để xác định file đã thay đổi sau khi triển khai.

Một quy trình validation thường kiểm tra:
- Migration đã áp dụng còn tồn tại trong source.
- Version/description/file identity phù hợp.
- Checksum hiện tại khớp checksum đã lưu.
- Không có version trùng hoặc thứ tự sai.
- Không có trạng thái failed/pending bất thường.

### 7.1. Checksum không phải chữ ký bảo mật

Checksum giúp phát hiện nội dung thay đổi ngoài dự kiến, nhưng không chứng minh người tạo file đáng tin cậy hoặc nội dung an toàn.

### 7.2. Checksum phụ thuộc tool/version

Cách normalize line endings, encoding hoặc checksum algorithm có thể phụ thuộc công cụ. Đừng tự tính checksum khác với tool rồi ghi vào history.

### 7.3. Source control vẫn cần thiết

Checksum không thay thế Git review, branch protection, code ownership và release artifacts.

### 7.4. Validation phải chạy trước deploy

Chạy validate trên staging/production trước khi migrate để phát hiện checksum drift và history inconsistencies trước khi thay đổi schema.

## 8. Thiết kế bảng migration history

Migration tools thường tự quản lý bảng history. Nếu tự xây runner cho mục đích học tập, có thể hình dung một ledger tối giản:

```sql
CREATE SCHEMA IF NOT EXISTS migration_admin;

CREATE TABLE migration_admin.schema_history (
    version          text PRIMARY KEY,
    description      text NOT NULL,
    script_name      text NOT NULL,
    checksum         text NOT NULL,
    installed_by     text NOT NULL,
    installed_at     timestamptz NOT NULL DEFAULT now(),
    execution_ms     bigint,
    success          boolean NOT NULL
);
```

Đây là ví dụ minh họa về các trường dữ liệu, không phải schema thay thế trực tiếp cho Flyway hoặc Liquibase.

### 8.1. Version làm khóa duy nhất

Primary key trên version ngăn cùng migration được ghi nhận hai lần.

### 8.2. Checksum và script name

Giúp liên kết history với artifact cụ thể trong repository/release.

### 8.3. installed_by và installed_at

Hữu ích cho audit và incident timeline. Trong môi trường automation, installed_by nên là service identity rõ ràng.

### 8.4. Execution time

Giúp nhận diện migration bất thường chậm và lập kế hoạch maintenance window.

### 8.5. Success flag chưa đủ cho runner production

Một runner thực tế còn cần lock/concurrency control, execution state, error handling, transaction boundaries, tool version và repair semantics. Ưu tiên migration framework đã được kiểm chứng thay vì tự triển khai một hệ thống nửa vời.

## 9. Flyway schema history và Liquibase changelog

Hai công cụ phổ biến có cách quản lý history khác nhau.

### 9.1. Flyway

Flyway thường dùng schema history table để ghi version, description, type, script, checksum, installed_by, installed_on, execution_time và success. Tên bảng có thể được cấu hình.

Các khái niệm:
- Versioned migrations.
- Repeatable migrations.
- Validate.
- Migrate.
- Info.
- Repair.
- Baseline.

### 9.2. Liquibase

Liquibase lưu lịch sử changesets trong DATABASECHANGELOG và dùng DATABASECHANGELOGLOCK để điều phối việc chạy changelog.

Một changeset thường được định danh bằng id, author và file path; checksum giúp phát hiện nội dung thay đổi theo semantics của Liquibase.

### 9.3. Không trộn lẫn history tables

Không để Flyway và Liquibase cùng quản lý một schema bằng hai history systems mà không có migration architecture rõ ràng. Hai runner có thể không hiểu trạng thái của nhau.

### 9.4. Chọn tool theo team workflow

Xem xét SQL-first hay declarative changelog, rollback support, multi-database support, CI integration, license/edition, observability và operational expertise.

## 10. Migration SQL theo version

Một ví dụ ba migrations:

`V001__create_customers.sql`

```sql
CREATE TABLE public.customers (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

`V002__add_customer_status.sql`

```sql
ALTER TABLE public.customers
ADD COLUMN status text;
```

`V003__create_customer_status_index.sql`

```sql
CREATE INDEX idx_customers_status
ON public.customers (status);
```

### 10.1. Mỗi migration có một mục đích dễ review

Không bắt buộc một migration chỉ có một SQL statement, nhưng scope cần đủ nhỏ để hiểu, test và phục hồi.

### 10.2. Dependencies theo thứ tự

V003 phụ thuộc bảng customers và cột status do V001/V002 tạo. Version order phản ánh dependency.

### 10.3. Không dùng version đã tồn tại

Sau khi V003 đã deploy, thay đổi tiếp theo phải là V004 trở đi theo convention của repository.

### 10.4. Schema qualification

Dùng schema rõ ràng hoặc cấu hình search_path được kiểm soát để migration không tạo object nhầm schema.

## 11. Transactional migrations trong PostgreSQL

PostgreSQL hỗ trợ transactional DDL cho nhiều thao tác schema. Nếu migration tool chạy migration trong transaction, DDL và history record có thể commit cùng nhau.

Ví dụ:

```sql
BEGIN;

CREATE TABLE public.audit_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.audit_events
ADD COLUMN source text;

COMMIT;
```

Nếu statement thất bại trước COMMIT, transaction có thể rollback cả thay đổi DDL trong transaction.

### 11.1. Atomicity

Khi migration và history update cùng transaction, database không rơi vào trạng thái script đã commit nhưng history chưa ghi hoặc ngược lại, với điều kiện tool thực sự dùng cùng transaction và operations hỗ trợ transactional execution.

### 11.2. DDL không phải lúc nào cũng transactional

Một số commands không thể chạy trong transaction block, ví dụ CREATE INDEX CONCURRENTLY, VACUUM, CREATE DATABASE và một số thao tác quản trị khác. Kiểm tra từng command và version.

### 11.3. Tool có transaction policy riêng

Một số tools cho phép tắt transaction cho migration hoặc đánh dấu changeset không transactional. Không giả định mọi script tự động được bọc trong một transaction.

### 11.4. Transaction lớn có trade-off

Migration transaction kéo dài có thể giữ locks, snapshots và WAL lâu, gây replication lag hoặc vacuum pressure. Chia migration theo phase khi phù hợp.

## 12. Non-transactional migrations

Một số PostgreSQL commands yêu cầu chạy ngoài transaction block. Ví dụ phổ biến là:

```sql
CREATE INDEX CONCURRENTLY idx_orders_created_at
ON public.orders (created_at);
```

Không chạy statement này trong BEGIN/COMMIT thông thường.

### 12.1. Tách migration riêng

Đặt non-transactional operation vào migration riêng và cấu hình tool đúng cách. Đừng đặt thêm DDL transactional vào cùng file nếu runner không thể xác định boundary an toàn.

### 12.2. Failure có thể để lại trạng thái trung gian

CREATE INDEX CONCURRENTLY thất bại có thể để lại index invalid. Migration history có thể ghi failed; cần kiểm tra catalog và cleanup/retry theo runbook.

### 12.3. History update không còn atomic cùng DDL

Khi operation không transactional, runner phải xử lý trường hợp DDL đã thành công nhưng process crash trước khi history được ghi. Đây là một lý do cần framework và repair procedure đáng tin cậy.

### 12.4. Không tự chạy lại mù quáng

Trước retry, kiểm tra object có tồn tại, trạng thái valid/ready và script đã thực hiện tới đâu.

## 13. Migration lock và nhiều deploy runners

Hai CI jobs hoặc hai application instances có thể cùng phát hiện migration pending. Nếu cùng chạy, chúng có thể xung đột hoặc chạy DDL hai lần.

Migration runner cần serialization:
- Chỉ một runner được thực thi migrations tại một thời điểm.
- Runner thứ hai phải chờ hoặc dừng với thông báo rõ.
- Lock phải được giữ đúng phạm vi execution.
- Lock được giải phóng khi runner kết thúc/crash theo cơ chế của database/tool.

### 13.1. Liquibase lock table

Liquibase dùng DATABASECHANGELOGLOCK để đánh dấu changelog đang được thực thi và ngăn runner khác chạy song song.

### 13.2. Advisory lock

Một custom runner có thể dùng PostgreSQL advisory lock. Nếu migration chạy qua nhiều transaction, cần hiểu session-level lock và connection identity.

```sql
SELECT pg_advisory_lock(8421, 1);

-- Execute the serialized migration sequence
-- using the same database session.

SELECT pg_advisory_unlock(8421, 1);
```

Ví dụ chỉ minh họa cơ chế. Trong production, dùng key namespace riêng, cùng connection và đảm bảo unlock/connection cleanup.

### 13.3. Transaction-scoped advisory lock

Nếu toàn bộ migration và history update chạy trong một transaction, pg_advisory_xact_lock có thể giữ lock tới khi transaction kết thúc. Nó không phù hợp nếu operation cần commit giữa chừng nhưng vẫn cần giữ serialization.

### 13.4. Connection pooler

Session-level advisory lock yêu cầu cùng PostgreSQL session. Transaction pooling có thể đổi backend giữa transactions; không dùng session lock qua pooler theo cách không được bảo đảm.

## 14. Migration idempotency

Idempotent operation có thể được thực hiện nhiều lần mà vẫn đưa hệ thống tới cùng trạng thái cuối, hoặc không gây hại khi chạy lại.

Tuy nhiên không phải mọi migration nên được viết để tự chạy lặp lại.

### 14.1. Versioned migration chạy một lần

Versioned migration được quản lý bằng history; runner không chạy lại khi đã thành công. Tính immutable và history là hàng rào chính.

### 14.2. IF NOT EXISTS không giải quyết schema drift

CREATE TABLE IF NOT EXISTS có thể bỏ qua object đã tồn tại nhưng cấu trúc khác mong đợi. Lệnh thành công không chứng minh schema đúng.

### 14.3. Data backfill nên có thể resume

Một backfill lớn có thể dùng batches và điều kiện xác định records chưa xử lý, giúp tiếp tục sau interruption.

### 14.4. Repeatable scripts cần semantics rõ

View/function replacement có thể chạy lại, nhưng cần xác định dependencies, grants, ownership và side effects.

## 15. Expand-contract migration

Expand-contract giúp thay đổi schema trong khi nhiều phiên bản ứng dụng cùng hoạt động.

Ví dụ muốn đổi cột full_name thành display_name.

```text
Phase 1: EXPAND
  Add display_name
  Keep full_name
  Deploy app compatible with both

Phase 2: MIGRATE
  Backfill display_name in batches
  Dual-write or synchronize during transition
  Validate values

Phase 3: SWITCH
  Read from display_name
  Stop writing full_name
  Wait until old app versions are gone

Phase 4: CONTRACT
  Drop full_name in a later release
```

### 15.1. Expand

Thêm cấu trúc mới theo cách tương thích với code cũ. Ví dụ thêm nullable column hoặc bảng mới.

### 15.2. Migrate data

Backfill dữ liệu hiện có theo batch. Nếu application vẫn ghi trong lúc backfill, cần dual-write, trigger tạm thời hoặc change-capture strategy để không bỏ sót updates.

### 15.3. Switch

Triển khai application đọc/ghi cấu trúc mới. Theo dõi correctness và giữ khả năng quay lại trong một khoảng thời gian.

### 15.4. Contract

Chỉ xóa cột/bảng cũ sau khi không còn application version, job hoặc consumer nào sử dụng.

### 15.5. Không gộp cả bốn phase vào một deploy

Nếu thêm, backfill, switch và drop trong một migration lớn, rolling deployments có thể khiến phiên bản ứng dụng cũ lỗi ngay giữa quá trình.

## 16. Thêm column và NOT NULL an toàn

Một thay đổi tưởng đơn giản có thể yêu cầu lock mạnh hoặc rewrite tùy version, default và table size.

### 16.1. Expand trước bằng nullable column

```sql
ALTER TABLE public.customers
ADD COLUMN status text;
```

Application cũ vẫn có thể hoạt động nếu không phụ thuộc cột mới.

### 16.2. Backfill theo batch

Cập nhật các rows có status NULL theo batch và commit thường xuyên. Tránh một transaction update hàng trăm triệu rows nếu không cần.

### 16.3. Thêm constraint NOT VALID

```sql
ALTER TABLE public.customers
ADD CONSTRAINT customers_status_not_null_check
CHECK (status IS NOT NULL) NOT VALID;
```

NOT VALID cho phép constraint được áp dụng cho changes mới trong khi chưa scan toàn bộ rows cũ; xác minh semantics theo loại constraint và version.

### 16.4. Validate constraint

```sql
ALTER TABLE public.customers
VALIDATE CONSTRAINT customers_status_not_null_check;
```

Sau khi dữ liệu cũ hợp lệ, có thể thực hiện bước SET NOT NULL theo kế hoạch và version-specific locking behavior, rồi bỏ check constraint dư nếu phù hợp.

### 16.5. Default và table rewrite

Behavior của ADD COLUMN DEFAULT thay đổi theo PostgreSQL version và loại default. Đọc tài liệu target version, đo lock/rewrite risk trên table tương đương.

## 17. Tạo index an toàn trên bảng lớn

CREATE INDEX thông thường có thể chặn writes trong thời gian build theo lock mode của command. Với bảng đang phục vụ traffic, cân nhắc CREATE INDEX CONCURRENTLY.

```sql
CREATE INDEX CONCURRENTLY idx_orders_customer_created
ON public.orders (customer_id, created_at DESC);
```

### 17.1. Không chạy trong transaction block

CREATE INDEX CONCURRENTLY không thể chạy trong transaction block thông thường. Migration runner cần hỗ trợ non-transactional migration.

### 17.2. Concurrent không có nghĩa không tốn tài nguyên

Build vẫn tiêu thụ CPU, I/O, WAL và có thể kéo dài do transactions/old snapshots. Theo dõi progress view và production load.

### 17.3. Kiểm tra index validity

```sql
SELECT
    c.relname AS index_name,
    i.indisready,
    i.indisvalid
FROM pg_index AS i
JOIN pg_class AS c
  ON c.oid = i.indexrelid
WHERE c.relname = 'idx_orders_customer_created';
```

### 17.4. Failed build

Nếu index invalid còn lại, điều tra và drop/rebuild theo runbook. Không chỉ đổi history status để giả vờ migration thành công.

## 18. Foreign keys và constraints trên bảng lớn

Có thể thêm một số constraints ở trạng thái NOT VALID rồi validate riêng để giảm thời gian giữ lock mạnh.

Ví dụ:

```sql
ALTER TABLE public.orders
ADD CONSTRAINT orders_customer_fk
FOREIGN KEY (customer_id)
REFERENCES public.customers(customer_id)
NOT VALID;

ALTER TABLE public.orders
VALIDATE CONSTRAINT orders_customer_fk;
```

### 18.1. NOT VALID không bỏ kiểm tra dữ liệu mới

Constraint vẫn được áp dụng cho rows mới/updated theo semantics PostgreSQL; bước VALIDATE kiểm tra dữ liệu hiện có.

### 18.2. Kiểm tra orphan rows trước

Có thể query tìm foreign keys không có parent để dự báo validation failure.

### 18.3. Lock behavior

ADD CONSTRAINT và VALIDATE có lock modes khác nhau. Đọc tài liệu command và kiểm thử trên version/table size tương ứng.

### 18.4. Constraint naming

Đặt tên ổn định, dễ tìm trong logs/catalog và migration history.

## 19. Backfill dữ liệu theo batch

Một data migration lớn nên chia nhỏ để giới hạn lock duration, WAL bursts, replication lag và rollback cost.

Ví dụ dùng khóa tăng dần để cập nhật theo batch:

```sql
UPDATE public.customers
SET status = 'ACTIVE'
WHERE customer_id > 0
  AND customer_id <= 10000
  AND status IS NULL;
```

Sau đó lặp batch với các range tiếp theo, commit từng batch.

### 19.1. Điều kiện idempotent

Điều kiện status IS NULL giúp chạy lại batch mà không ghi đè rows đã xử lý.

### 19.2. Keyset thay OFFSET

Với bảng lớn, key range/keyset thường ổn định hơn OFFSET lớn. Chọn key có index và thứ tự xác định.

### 19.3. Checkpoint

Ghi batch progress hoặc tính từ dữ liệu còn lại. Nếu job crash, có thể tiếp tục mà không cần chạy lại từ đầu.

### 19.4. Concurrency với application writes

Nếu application vẫn cập nhật row trong lúc backfill, thiết kế precedence và conflict policy. Không để backfill ghi đè giá trị mới hơn.

### 19.5. WAL và replication

Batch quá lớn có thể tạo WAL burst, replica lag và archive growth. Điều chỉnh batch size/concurrency theo metrics.

## 20. Migration và lock behavior

DDL có thể cần AccessExclusiveLock hoặc lock mode khác. Một migration chờ lock có thể tạo hàng đợi: các query mới xếp sau nó cũng có thể bị block tùy tình huống.

### 20.1. Lock acquisition là một phần downtime

Ngay cả ALTER TABLE rất nhanh cũng có thể chờ lâu nếu transaction khác giữ lock. Thời gian chờ có thể lớn hơn thời gian DDL thực thi.

### 20.2. lock_timeout

Có thể đặt lock_timeout ngắn cho migration để fail fast nếu không lấy được lock trong maintenance budget.

```sql
SET lock_timeout = '2s';
SET statement_timeout = '15min';
```

Đây là ví dụ; chọn values theo operation và tool transaction model.

### 20.3. Long-running transactions

Tìm sessions có xact_start cũ trước khi migration. Một transaction idle in transaction có thể giữ lock/snapshot và cản DDL.

### 20.4. NOWAIT

Một số DDL/lock operations hỗ trợ NOWAIT hoặc có cách kiểm tra lock trước. Dùng khi muốn migration fail nhanh thay vì tạo hàng đợi.

### 20.5. Không terminate blocker theo phản xạ

Xác định owner, transaction và business impact trước khi cancel/terminate. Một migration fail fast thường an toàn hơn việc phá transaction không rõ nguồn gốc.

## 21. Search path, schema và object ownership

Migration phải tạo objects đúng schema và đúng owner.

### 21.1. Schema qualification

Dùng public.table hoặc schema mục tiêu rõ ràng khi script có thể chạy trong môi trường search_path khác nhau.

### 21.2. search_path

Nếu tool dùng một role migration riêng, kiểm tra search_path của role/session và tránh schema shadowing.

### 21.3. Object owner

Objects tạo bởi migration role sẽ thuộc role đó trừ khi có owner transfer. Chọn owner role phù hợp để application không cần superuser.

### 21.4. Grants

Tạo grants/default privileges có chủ đích. Migration thêm table/sequence/function mới có thể cần grants để application hoạt động.

### 21.5. SECURITY DEFINER functions

Nếu migration tạo SECURITY DEFINER functions, đặt search_path an toàn, owner đáng tin cậy và revoke EXECUTE/public grants khi cần.

## 22. Roles và quyền chạy migration

Nên tách:
- Application runtime role: quyền tối thiểu để chạy nghiệp vụ.
- Migration role: quyền DDL cần thiết trong schema được quản lý.
- DBA/owner role: quản trị cluster và các thao tác đặc biệt.
- Read-only/reporting roles: quyền đọc theo policy.

### 22.1. Không chạy application bằng superuser

Ứng dụng runtime không cần quyền thay schema. Tách credential giúp giảm blast radius.

### 22.2. Migration role có quyền phù hợp

Migration role cần tạo/sửa objects trong schema mục tiêu và có thể cần ownership. Cấp quyền theo scope, không cấp superuser mặc định.

### 22.3. Credential management

Secrets lấy từ secret manager/CI secret store. Không commit password vào migration config hoặc repository.

### 22.4. Audit identity

History record và deployment logs nên cho biết service identity hoặc operator nào chạy migration.

## 23. Baseline cho database đã tồn tại

Khi đưa migration tool vào một database đã được tạo thủ công hoặc đã chạy từ lâu, không thể mặc định chạy lại toàn bộ migrations lịch sử.

Baseline ghi nhận rằng database hiện tại đã ở một version/schema state nhất định, để tool bắt đầu quản lý từ mốc đó.

### 23.1. Kiểm tra schema trước baseline

So sánh objects, constraints, indexes, extensions, owners và data assumptions với schema tương ứng version được chọn.

### 23.2. Baseline không tự tạo schema

Baseline thường chỉ ghi nhận mốc history. Nó không chạy lại mọi migration trước đó để tạo objects.

### 23.3. Chọn baseline version chính xác

Nếu chọn sai version, runner có thể bỏ qua migration cần thiết hoặc chạy migration cũ lên schema đã có.

### 23.4. Lưu bằng chứng

Lưu schema snapshot/diff, object counts, database identity, baseline version và approval. Baseline là quyết định có ảnh hưởng lâu dài.

## 24. Migration mới cho môi trường trống

Một repository migration tốt phải có khả năng dựng database mới từ đầu theo thứ tự.

### 24.1. Empty database test

Tạo database sạch, chạy toàn bộ migrations và xác minh application schema.

### 24.2. Seed/reference data

Phân biệt reference data cần thiết (lookup/status codes) với production data. Seed script cần idempotent và có owner.

### 24.3. Bootstrap roles/schema

Tạo roles, schemas, extensions và grants theo quy trình bootstrap phù hợp. Một số cluster-level objects không nằm trong database migrations thông thường.

### 24.4. Reproducibility

Cùng một migration artifact và tool version phải tạo ra schema tương đương trên các môi trường hỗ trợ.

## 25. CI/CD cho database migrations

Một pipeline điển hình:

```text
Pull request
    |
    v
Static review / lint
    |
    v
Create ephemeral PostgreSQL database
    |
    v
Run all migrations from empty state
    |
    v
Run application tests
    |
    v
Validate migration history/checksums
    |
    v
Build immutable release artifact
    |
    v
Deploy to staging
    |
    v
Backup + approval/change window
    |
    v
Run production migration once
    |
    v
Deploy compatible application
    |
    v
Monitor and verify
```

### 25.1. Test full migration chain

Không chỉ test migration mới nhất trên một database đã có schema gần giống. Test từ empty database để phát hiện dependency bị thiếu.

### 25.2. Test upgrade path từ production-like state

Dựng snapshot/schema/data đại diện và chạy migrations pending. Một script có thể chạy trên database trống nhưng timeout trên table production lớn.

### 25.3. Test application compatibility

Với rolling deployments, kiểm tra cả old application version và new application version trong các phase expand-contract.

### 25.4. Release artifact bất biến

Deploy cùng một migration artifact đã test. Không build lại script khác nhau giữa staging và production.

### 25.5. Migration runner tách khỏi mọi application replica

Tránh mỗi web instance tự chạy migrations khi khởi động. Dùng một deployment job/runner được serialize và có audit.

## 26. Promotion qua development, test, staging và production

Cùng một migration file nên được promote qua các môi trường theo cùng thứ tự.

### 26.1. Development

Cho phép thử nghiệm nhanh, nhưng khi migration đã được chia sẻ với người khác, giữ file ổn định và tạo version mới cho sửa đổi.

### 26.2. Test/CI

Chạy full chain, schema validation, integration tests và performance tests phù hợp.

### 26.3. Staging

Dùng cấu hình và data volume gần production. Đo locks, duration, WAL, replication lag và downtime.

### 26.4. Production

Dùng artifact đã kiểm thử, backup/restore evidence, change window, migration lock và rollback/forward plan.

### 26.5. Không sửa script riêng theo môi trường

Dùng configuration/variables được kiểm soát cho values khác nhau. Schema migration nên có behavior nhất quán, tránh các file cùng version nhưng nội dung khác nhau.

## 27. Migration history qua nhiều môi trường

Mỗi database có history table riêng. Một migration có thể:
- Đã chạy trên development.
- Đã chạy trên CI database.
- Đã chạy trên staging.
- Chưa chạy trên production.

### 27.1. Không copy history table để đồng bộ

History phải phản ánh migration thực sự đã chạy trên database đó. Copy rows giữa environments có thể che giấu schema mismatch.

### 27.2. Compare pending migrations

Trước deploy, xem danh sách migrations pending và version hiện tại. Review đúng danh sách sắp chạy.

### 27.3. Same artifact

Đảm bảo checksum/file content của migration giống nhau giữa các environments. Không dùng branch-specific script drift.

### 27.4. Environment-specific data

Migration schema nên nhất quán; data seeds hoặc tenant-specific setup cần được quản lý riêng có kiểm soát.

## 28. Schema drift là gì?

Schema drift xảy ra khi schema thực tế khác với trạng thái mà migration history/source code mô tả.

Nguyên nhân:
- DBA sửa trực tiếp production.
- Migration bị chạy thủ công ngoài tool.
- Tool history bị sửa/xóa.
- Script đã áp dụng bị thay đổi.
- Một môi trường bỏ sót migration.
- Extension hoặc provider tự tạo objects.
- Restore từ backup cũ nhưng history/artifacts không đồng bộ.

### 28.1. History không phát hiện mọi drift

Checksum có thể phát hiện file migration bị sửa. Nó không tự phát hiện mọi thay đổi thủ công trên catalogs.

### 28.2. Schema diff

Dùng schema comparison/introspection để so objects thực tế với expected schema. Review diff trước khi sửa.

### 28.3. Không tự động xóa object lạ

Drift tool có thể đề xuất DROP hoặc ALTER. Kiểm tra dependencies, data và ownership trước khi apply.

### 28.4. Ghi drift thành migration mới

Sau khi xác minh thay đổi thủ công là hợp lệ, đưa nó vào source control bằng migration phù hợp hoặc reconcile schema theo quy trình.

## 29. Failed migration và recovery

Khi migration lỗi, trước tiên xác định:
- Transactional hay non-transactional?
- Script đã thực hiện được phần nào?
- History record đã được ghi chưa?
- Object nào đã được tạo hoặc thay đổi?
- Có locks/transactions còn mở không?
- Application đang ở version/schema state nào?

### 29.1. Transactional failure

Nếu tool chạy toàn bộ script trong một transaction và rollback thành công, thay đổi DDL trong transaction được rollback. Kiểm tra history và catalog trước khi retry.

### 29.2. Non-transactional failure

Một phần operation có thể đã hoàn thành. Ví dụ index invalid có thể còn lại. Kiểm tra catalog và dọn trạng thái trung gian.

### 29.3. Không sửa history bằng SQL tùy tiện

Dùng validate/repair hoặc recovery procedure của tool sau khi hiểu trạng thái thực. History edit thủ công có thể khiến runner bỏ qua migration chưa hoàn tất.

### 29.4. Roll-forward thường an toàn hơn

Với production data, tạo migration sửa lỗi tiếp theo thường an toàn hơn cố rollback một migration đã có side effects hoặc data transformation.

## 30. Rollback và roll-forward

Rollback database không luôn đơn giản như revert Git commit.

### 30.1. DDL rollback

Một số DDL có thể được rollback trong transaction. Nhưng sau khi commit và application đã ghi data theo schema mới, đảo ngược có thể mất dữ liệu hoặc không còn khả thi.

### 30.2. Data migration rollback

Nếu chuyển đổi mất thông tin, ví dụ gộp hai cột thành một, không thể luôn khôi phục dữ liệu ban đầu. Cần backup hoặc giữ source columns trong transition.

### 30.3. Compensating migration

Tạo migration mới để đưa schema về trạng thái tương thích, thay vì sửa/xóa lịch sử đã áp dụng.

### 30.4. Roll-forward

Sửa lỗi bằng migration mới và deploy tiếp thường giữ history tuyến tính. Đánh giá business impact và recovery point trước.

### 30.5. Migration down scripts

Một số tool hỗ trợ rollback/undo scripts, nhưng phải test và hiểu data loss. Không mặc định down migration luôn an toàn hoặc khả nghịch.

## 31. Migration và backup/PITR

Trước migration có rủi ro cao:
- Xác minh base backup gần nhất.
- Xác minh WAL archive liên tục.
- Kiểm tra restore procedure.
- Thực hiện snapshot/backup theo policy.
- Ghi recovery point và owner.
- Rehearse restore cho thay đổi có blast radius lớn.

### 31.1. Backup không thay migration history

Backup phục hồi database state tại thời điểm. Migration history cho biết thay đổi nào đã áp dụng. Cần giữ cả artifacts lẫn backup metadata.

### 31.2. Restore kéo history lùi

Nếu restore backup cũ, history table cũng quay về trạng thái tại thời điểm backup. Đảm bảo application version và migration artifacts tương thích với restored schema.

### 31.3. PITR sau migration

Nếu cần quay về trước migration, phục hồi cluster sang thời điểm trước thay đổi theo quy trình PITR. Không thể chỉ delete history row.

### 31.4. Test recovery

Một backup chưa restore test chưa chứng minh migration có recovery path.

## 32. Migration và zero-downtime deployment

Database và application thường được deploy riêng. Rolling deployments có thể chạy đồng thời old/new application versions.

Expand-contract giúp duy trì compatibility:
1. Expand schema.
2. Deploy code có thể đọc/ghi schema cũ và mới.
3. Backfill dữ liệu.
4. Chuyển traffic/code sang cấu trúc mới.
5. Xác minh không còn consumers cũ.
6. Contract schema trong release sau.

### 32.1. Backward compatibility

Migration đầu tiên không nên xóa/rename cột mà old app vẫn đang sử dụng.

### 32.2. Forward compatibility

New app không nên yêu cầu schema mới trước khi migration expand đã hoàn tất.

### 32.3. Deploy ordering

Một thứ tự thường dùng: expand migration → deploy compatible application → backfill → switch application → contract migration sau khi old versions đã biến mất.

### 32.4. Worker/background jobs

Không quên scheduled jobs, consumers và long-lived workers. Một worker cũ có thể vẫn đọc column sắp bị xóa.

## 33. Migration cho functions, views và triggers

Database code cũng cần version hóa:
- Functions/procedures.
- Views/materialized views.
- Triggers.
- Types/domains.
- Operators.
- Policies.
- Grants/default privileges.

### 33.1. CREATE OR REPLACE

Có thể phù hợp với functions/views khi signature/semantics cho phép. Một số thay đổi về return type, dependencies hoặc object kind cần DROP/CREATE hoặc migration riêng.

### 33.2. Dependencies

Thay đổi function signature có thể ảnh hưởng views, triggers, generated columns hoặc application calls. Inventory dependencies trước khi sửa.

### 33.3. Grants và ownership

CREATE OR REPLACE có thể giữ một số ownership/privilege state nhưng không nên giả định mọi quyền được bảo toàn theo cách mong muốn. Kiểm tra grants sau migration.

### 33.4. Materialized views

Refresh dữ liệu có thể tốn thời gian và lock. REFRESH MATERIALIZED VIEW CONCURRENTLY có điều kiện riêng và không chạy trong transaction block thông thường.

## 34. Migration cho enums và data types

PostgreSQL có các type changes cần lập kế hoạch:
- ALTER TYPE ADD VALUE.
- Domain constraints.
- Composite types.
- Enum labels.
- Column type conversion.
- Collation changes.

### 34.1. Enum value addition

ALTER TYPE ... ADD VALUE có transactional behavior phụ thuộc PostgreSQL version; ở các version hiện đại có thể chạy trong transaction nhưng giá trị mới không dùng được trước khi transaction commit trong một số contexts. Kiểm tra docs đúng version.

### 34.2. Enum removal/rename

Xóa enum value không có thao tác đơn giản tương đương ADD VALUE. Thường cần tạo type mới, chuyển columns/data, cập nhật dependencies rồi xóa type cũ.

### 34.3. Type conversion

ALTER COLUMN TYPE có thể rewrite table và giữ lock đáng kể. Đánh giá USING expression, indexes, constraints, WAL và disk.

### 34.4. Large table strategy

Với table lớn, cân nhắc cột mới + batch backfill + dual-write + switch + drop cột cũ.

## 35. Migration cho partitioned tables

Partitioned tables có thêm dependencies:
- Parent partitioned table.
- Child partitions.
- Partition bounds.
- Indexes/constraints trên parent và children.
- Default partition.
- Attach/detach workflow.

### 35.1. Tạo partition trước khi dữ liệu tới

Nếu application ghi theo time range, cần lịch tạo partitions và monitoring cho default partition.

### 35.2. Attach partition

Có thể cần validation/locks và điều kiện matching constraints. Pre-create check constraints phù hợp để giảm scan trong một số workflows.

### 35.3. Index consistency

Đảm bảo partitioned indexes và child indexes tương ứng. Kiểm tra trạng thái valid sau migration.

### 35.4. Detach/drop partition

Đây là thay đổi dữ liệu có tác động lớn. Xác nhận retention policy, backup và consumer dependencies trước.

## 36. Migration với logical replication và CDC

DDL và migration history không tự được replicate đầy đủ như row data.

### 36.1. Schema phải được triển khai ở subscriber

Nếu publisher thêm column mà subscriber schema chưa tương thích, apply behavior phụ thuộc column mapping và publication. Lập kế hoạch DDL hai bên.

### 36.2. Migration history table có thể được replicate?

Có thể tùy publication/table selection, nhưng không nên dùng việc replicate history như cách điều phối migration runner. Mỗi database/cluster cần state và ownership rõ ràng.

### 36.3. CDC consumers

Schema changes có thể ảnh hưởng downstream schemas, event contracts và deserialization. Phối hợp versioning của database và event schema.

### 36.4. Ordering

Đảm bảo consumer biết schema mới trước khi event chứa field mới tới. Dùng compatibility rollout và schema registry/pipeline contract khi có.

## 37. Migration script và data safety

Một migration có thể gây mất dữ liệu nếu:
- DROP COLUMN trước khi code ngừng đọc.
- ALTER TYPE làm truncate/cast sai.
- UPDATE thiếu WHERE.
- DELETE không có filter đúng.
- Backfill ghi đè concurrent updates.
- Rebuild object làm mất grants/owner.
- Drop/recreate table làm mất dependent objects.

### 37.1. Review destructive statements

DROP, TRUNCATE, DELETE, type conversion và table rewrite cần review kỹ, có backup/recovery plan và explicit impact.

### 37.2. Dry run/plan

Một số thay đổi có thể ước lượng affected rows hoặc locks trước. Dùng SELECT preview và transaction thử nghiệm trên staging.

### 37.3. Row counts và invariants

Trước/sau migration, kiểm tra row counts, null counts, uniqueness, foreign-key coverage và business aggregates.

### 37.4. Data retention

Không xóa dữ liệu cũ trước khi xác nhận retention/legal/business requirements và downstream consumers.

## 38. Naming, repository structure và ownership

Ví dụ repository:

```text
db/
  migrations/
    V001__create_customers.sql
    V002__add_customer_status.sql
    V003__create_orders.sql
    V004__create_orders_customer_index.sql
    R__customer_reporting_views.sql
  callbacks/
  seed/
  tests/
  README.md
```

### 38.1. Ownership

Mỗi migration nên có author/team hoặc CODEOWNERS phù hợp. Database platform team có thể review migrations ảnh hưởng lock/availability.

### 38.2. Không lưu migration trong thư mục tạm

Migration phải nằm trong release artifact/source control được version hóa và deploy nhất quán.

### 38.3. Review SQL

Review plan, lock, table size, index build, data transformation, privileges và rollback/forward path.

### 38.4. Naming convention

Giữ quy tắc version, separator, description và encoding ổn định.

## 39. Observability cho migration execution

Ghi nhận:
- Migration version/script.
- Start/end timestamps.
- Duration.
- Runner identity.
- Database/cluster identity.
- Success/failure.
- Checksum.
- Lock wait.
- Rows affected hoặc progress cho backfill.
- WAL/replication lag.
- Error message/SQLSTATE.
- Deployment/change ID.

### 39.1. Migration duration

So sánh duration thực tế với rehearsal. Cảnh báo khi vượt maintenance budget.

### 39.2. Lock wait

Đo thời gian chờ lock và số sessions bị block. DDL ngắn nhưng chờ lock lâu vẫn có thể gây incident.

### 39.3. Backfill progress

Ghi batches completed, rows remaining, throughput và checkpoint. Không chỉ log một dòng “job running”.

### 39.4. Replica lag và WAL

Theo dõi WAL generation, archive retention và standby replay lag trong data migrations lớn.

## 40. Monitoring và alerting

Alert có thể bao gồm:
- Migration runner thất bại.
- Checksum validation mismatch.
- Version collision hoặc history inconsistency.
- Migration lock chờ quá lâu.
- DDL blocker vượt ngưỡng.
- Migration duration vượt budget.
- Replica lag tăng mạnh trong backfill.
- WAL filesystem gần đầy.
- Invalid index sau concurrent build failure.
- Application error/latency tăng sau migration.

### 40.1. Alert theo impact

Một migration failed trên database staging khác với production critical. Severity dựa trên môi trường và business impact.

### 40.2. Không alert chỉ vì migration đang chạy

Migration có thể dài theo thiết kế. Alert khi vượt expected duration, lock budget hoặc resource threshold.

### 40.3. Link runbook

Alert cần cho biết migration version, runner, database, logs và hướng xử lý tiếp theo.

### 40.4. Stop condition

Đặt ngưỡng dừng/rollback hoặc tạm ngưng traffic trước khi chạy migration lớn.

## 41. Repair và reconcile history

Các migration tools có lệnh repair để xử lý metadata sau tình huống đặc biệt. Repair không phải lệnh “sửa database schema”.

### 41.1. Validate trước repair

Đọc history, checksum, script và actual schema. Xác định migration nào chạy hết, chạy một phần hoặc chưa chạy.

### 41.2. Repair chỉ sửa metadata theo semantics của tool

Ví dụ có thể cập nhật checksum, xóa failed record hoặc reconcile history. Hành vi cụ thể phụ thuộc tool/version.

### 41.3. Không dùng repair để che drift

Nếu schema thiếu column, repair history không tạo column đó. Tạo corrective migration hoặc restore theo kế hoạch.

### 41.4. Audit repair

Ghi ai chạy, lý do, history trước/sau và bằng chứng schema. Repair trong production cần quy trình change control.

## 42. Migration và disaster recovery

Khi restore một backup, migration history quay về thời điểm backup. Source repository có thể chứa migrations mới hơn trạng thái restored.

### 42.1. Reconcile trước khi migrate tiếp

Xác định database version trong history sau restore, target application version và các migrations pending.

### 42.2. PITR target

Nếu restore tới thời điểm trước migration, history cũng phải phản ánh trạng thái đó. Không xóa riêng history rows để ép runner.

### 42.3. Recovery environment

Dùng cùng migration artifacts và tool version đã được kiểm thử. Tránh deploy một branch mới lên restored database khi chưa kiểm tra compatibility.

### 42.4. Disaster recovery exercise

Diễn tập restore, migration catch-up và application startup. Đo thời gian tới service recovery.

## 43. Security trong migration pipeline

Migration scripts có quyền DDL và có thể đọc/ghi nhiều dữ liệu. Bảo vệ pipeline:
- Secrets trong secret manager/CI variables.
- Không commit credentials.
- Runner identity riêng.
- Network access giới hạn.
- Least privilege.
- Signed/immutable artifacts khi cần.
- Branch protection và mandatory review.
- Audit deployment approvals.
- Redact sensitive data khỏi logs.
- Review extension/function security.

### 43.1. SQL injection trong migration tooling

Không ghép input không tin cậy vào dynamic SQL. Dùng parameterization/identifier quoting đúng cách trong procedural code.

### 43.2. Migration file là executable code

Review SQL như code production. Một script có thể DROP data hoặc cấp quyền rộng.

### 43.3. Production approvals

Thay đổi có rủi ro cao cần owner và approval theo policy. Automation không nên tự nâng quyền.

### 43.4. Secrets rotation

Nếu migration cần credential external, dùng secret reference và hạn chế thời gian tồn tại.

## 44. Runbook: deploy migrations cho một release

1. Chốt migration files và version uniqueness.
2. Review SQL, dependencies, locks và destructive operations.
3. Chạy lint/static checks.
4. Dựng database sạch và chạy full chain.
5. Test upgrade từ schema gần production.
6. Chạy application integration tests.
7. Rehearse duration/locks/WAL với data volume đại diện.
8. Validate migration checksums/history.
9. Build immutable artifact.
10. Deploy staging và kiểm tra.
11. Xác minh backup/restore readiness.
12. Mở change window và xác định owner.
13. Chạy một migration runner được serialize.
14. Theo dõi progress, logs, locks, replica lag và application metrics.
15. Kiểm tra history, schema và business invariants.
16. Deploy/enable application behavior tương thích.
17. Ghi change evidence và đóng release.

## 45. Runbook: migration thất bại giữa chừng

1. Dừng runner retry tự động nếu chưa rõ trạng thái.
2. Ghi migration version, checksum, tool version và error.
3. Xác định transactional/non-transactional.
4. Kiểm tra backend/session còn chạy và locks.
5. Kiểm tra history table và execution status.
6. Kiểm tra catalog/object state thực tế.
7. Kiểm tra data rows đã được backfill tới đâu.
8. Xác định application version có đang phụ thuộc schema trung gian không.
9. Chọn rollback, cleanup hoặc corrective migration.
10. Dùng tool repair chỉ sau khi schema/history đã được reconcile.
11. Test recovery trên bản sao.
12. Chạy tiếp theo runbook và xác minh invariants.

### 45.1. Không xóa history record trước khi biết DDL state

Nếu DDL đã thành công nhưng history bị thiếu, runner có thể chạy lại và fail hoặc phá schema.

### 45.2. Không sửa file versioned đã chạy

Tạo corrective migration mới nếu cần thay đổi.

### 45.3. Giữ evidence

Lưu logs, SQLSTATE, backend PID, locks, object states và history snapshots.

## 46. Runbook: kiểm tra schema drift

1. Lấy expected migration list từ release artifact.
2. Chạy validate/checksum.
3. Đọc migration history trên từng environment.
4. So sánh object inventory/catalogs.
5. Tìm objects thiếu, thừa hoặc definition khác.
6. Xác định thay đổi thủ công, extension/provider changes hay migration bị bỏ sót.
7. Đánh giá data/dependency impact.
8. Viết corrective migration hoặc reconcile theo tool.
9. Test trên staging/snapshot.
10. Deploy và kiểm tra history/schema lại.

### 46.1. Không tự động drop objects lạ

Một table có thể do extension/provider hoặc application khác sở hữu. Xác định owner trước.

### 46.2. Drift không chỉ là columns

Bao gồm indexes, constraints, triggers, functions, policies, owners, grants, extensions và collations.

### 46.3. So sánh nhiều môi trường

Staging/prod cùng history nhưng schema khác có thể là dấu hiệu drift. So sánh cả history lẫn actual catalog.

## 47. Các lỗi thường gặp

- Sửa migration versioned đã chạy.
- Dùng version trùng giữa hai branches.
- So sánh version dưới dạng text sai thứ tự.
- Chạy migrations đồng thời từ nhiều application replicas.
- Chạy DDL non-transactional bên trong transaction block.
- Retry migration failed mà không kiểm tra object state.
- Dùng IF NOT EXISTS để che schema mismatch.
- Ghi history trước khi DDL thực sự hoàn tất.
- Sửa/xóa history table bằng SQL tùy tiện.
- Coi checksum là bằng chứng schema không drift.
- Backfill toàn bảng trong một transaction quá lớn.
- Thêm NOT NULL/foreign key trên bảng lớn mà không rehearsal.
- Tạo index thường trong giờ cao điểm mà không đánh giá lock.
- Quên sequence/data/CDC dependencies.
- Drop cột trước khi old app/worker ngừng sử dụng.
- Deploy app mới trước migration expand.
- Không kiểm tra grants/ownership sau tạo object.
- Không test migration chain từ empty database.
- Dùng history copy từ staging sang production.
- Không có backup/restore test hoặc forward recovery plan.

## 48. Bài tập thực hành có đáp án

### Bài 1. Versioned migration là gì?

**Đáp án:** Script/change set có version duy nhất, được chạy theo thứ tự và ghi vào migration history.

### Bài 2. Migration history dùng để làm gì?

**Đáp án:** Ghi lại migration đã áp dụng, version, checksum, thời gian, người/công cụ chạy và execution outcome.

### Bài 3. History table có chứng minh schema thực tế không drift?

**Đáp án:** Không. Nó ghi nhận lịch sử tool; cần schema diff/catalog inspection để phát hiện thay đổi thủ công.

### Bài 4. Vì sao migration version phải duy nhất?

**Đáp án:** Để runner xác định thứ tự và tránh hai scripts cùng identity.

### Bài 5. Vì sao không nên sửa V001 sau khi production đã chạy?

**Đáp án:** Các môi trường có thể ghi nhận cùng version nhưng thực thi nội dung khác nhau.

### Bài 6. Checksum có tác dụng gì?

**Đáp án:** Phát hiện migration file đã thay đổi so với nội dung được ghi nhận khi áp dụng.

### Bài 7. Checksum có phải chữ ký bảo mật?

**Đáp án:** Không. Nó là fingerprint/validation mechanism, không chứng minh author hoặc nội dung an toàn.

### Bài 8. Repeatable migration phù hợp với gì?

**Đáp án:** Objects có thể tạo lại theo definition mới, như một số views/functions; không phù hợp với data backfill tùy tiện.

### Bài 9. Flyway versioned và Liquibase changeset có giống nhau hoàn toàn?

**Đáp án:** Không. Cùng quản lý change history nhưng identity, ordering và execution semantics khác nhau.

### Bài 10. Liquibase dùng bảng nào để lock changelog?

**Đáp án:** DATABASECHANGELOGLOCK.

### Bài 11. Vì sao migration runner cần lock?

**Đáp án:** Ngăn hai deployment runners cùng áp dụng migrations và tạo race conditions.

### Bài 12. PostgreSQL có hỗ trợ transactional DDL không?

**Đáp án:** Có cho nhiều DDL commands, nhưng không phải mọi command đều chạy được trong transaction block.

### Bài 13. CREATE INDEX CONCURRENTLY có chạy trong BEGIN/COMMIT thông thường không?

**Đáp án:** Không. Nó phải chạy ngoài transaction block.

### Bài 14. Nếu CREATE INDEX CONCURRENTLY thất bại có thể còn gì?

**Đáp án:** Một index invalid/not-ready có thể còn lại; kiểm tra catalog trước khi retry.

### Bài 15. Transactional migration giúp gì?

**Đáp án:** Có thể commit DDL và history update atomic trong cùng transaction nếu mọi operations hỗ trợ transaction.

### Bài 16. Vì sao non-transactional migration khó recovery hơn?

**Đáp án:** DDL có thể đã hoàn tất một phần trước khi runner ghi history hoặc process crash.

### Bài 17. pg_advisory_lock là gì?

**Đáp án:** Cơ chế application-defined lock của PostgreSQL, có thể serialize migration runners nếu dùng cùng session/key.

### Bài 18. pg_advisory_xact_lock giữ lock tới khi nào?

**Đáp án:** Tới khi transaction kết thúc.

### Bài 19. Vì sao session advisory lock có vấn đề với transaction pooling?

**Đáp án:** Backend session có thể thay đổi giữa transactions; lock gắn với session cụ thể.

### Bài 20. IF NOT EXISTS có đảm bảo object đúng schema?

**Đáp án:** Không. Nó chỉ bỏ qua khi object cùng tên tồn tại; definition có thể khác.

### Bài 21. Expand-contract gồm những phase nào?

**Đáp án:** Expand schema, migrate/backfill, switch application, contract/xóa cấu trúc cũ.

### Bài 22. Vì sao không drop cột cũ ngay khi thêm cột mới?

**Đáp án:** Old application versions và workers có thể vẫn dùng cột cũ trong rolling deployment.

### Bài 23. Backfill batch có lợi gì?

**Đáp án:** Giới hạn transaction duration, locks, WAL burst và cho phép resume sau interruption.

### Bài 24. Vì sao backfill cần xử lý concurrent writes?

**Đáp án:** Nếu application cập nhật cùng rows, backfill có thể ghi đè dữ liệu mới hoặc bỏ sót changes.

### Bài 25. NOT VALID constraint có tác dụng gì?

**Đáp án:** Cho phép thêm constraint mà chưa scan toàn bộ existing rows; dữ liệu cũ được validate ở bước riêng.

### Bài 26. VALIDATE CONSTRAINT dùng để làm gì?

**Đáp án:** Kiểm tra dữ liệu hiện có đáp ứng constraint.

### Bài 27. CREATE INDEX CONCURRENTLY có hoàn toàn không ảnh hưởng workload?

**Đáp án:** Không. Nó vẫn dùng CPU, I/O, WAL và có thể chờ transactions/snapshots.

### Bài 28. lock_timeout giới hạn gì?

**Đáp án:** Thời gian chờ acquire lock trước khi statement bị lỗi.

### Bài 29. Vì sao migration DDL ngắn vẫn có thể block traffic lâu?

**Đáp án:** Nó có thể chờ lock do transaction khác giữ; thời gian chờ lớn hơn thời gian thực thi DDL.

### Bài 30. Migration role có nên là superuser?

**Đáp án:** Không mặc định. Cấp quyền DDL cần thiết trong schema scope theo least privilege.

### Bài 31. Baseline có tự tạo schema cho database cũ?

**Đáp án:** Không. Nó ghi nhận một mốc history; cần xác minh schema hiện tại tương ứng mốc đó.

### Bài 32. Vì sao test migration từ empty database?

**Đáp án:** Phát hiện dependency thiếu hoặc migration chain không thể tái tạo schema mới.

### Bài 33. Vì sao test trên production-like data?

**Đáp án:** Để đo lock, duration, rewrite, WAL và data validation trên volume/skew tương tự thực tế.

### Bài 34. Có nên copy history table từ staging sang production?

**Đáp án:** Không. History phải phản ánh migrations thực sự đã chạy trên chính database đó.

### Bài 35. Schema drift là gì?

**Đáp án:** Schema thực tế khác trạng thái mà migration source/history mô tả.

### Bài 36. Checksum validation có phát hiện mọi schema drift?

**Đáp án:** Không. Nó chủ yếu phát hiện migration file thay đổi; cần catalog/schema diff cho drift thực tế.

### Bài 37. Khi migration failed, bước đầu tiên là gì?

**Đáp án:** Xác định transactional state, object/data changes, history state và locks trước khi retry.

### Bài 38. Repair command có tự sửa schema không?

**Đáp án:** Không. Nó điều chỉnh migration metadata theo tool semantics; schema cần corrective migration/recovery riêng.

### Bài 39. Rollback migration có luôn an toàn?

**Đáp án:** Không. Data transformations có thể mất thông tin và application đã ghi theo schema mới.

### Bài 40. Roll-forward là gì?

**Đáp án:** Tạo migration mới để sửa trạng thái hiện tại, giữ lịch sử đã áp dụng.

### Bài 41. Backup/PITR có thay migration history?

**Đáp án:** Không. Backup lưu database state; history mô tả thay đổi đã chạy.

### Bài 42. Sau PITR, history table có thể ở trạng thái nào?

**Đáp án:** Quay về trạng thái tại recovery target, có thể cũ hơn source migration repository hiện tại.

### Bài 43. Migration và application rolling deploy cần phối hợp ra sao?

**Đáp án:** Expand schema trước, deploy code tương thích, backfill/switch, rồi contract sau khi old consumers biến mất.

### Bài 44. Vì sao cần kiểm tra grants sau CREATE TABLE?

**Đáp án:** Object mới có thể thuộc migration role và application runtime role không tự có quyền truy cập.

### Bài 45. Sequence có tự được logical replication đồng bộ như rows?

**Đáp án:** Không. Cần quy trình đồng bộ sequence state riêng khi migration/cutover.

### Bài 46. Vì sao migration nên có owner và audit?

**Đáp án:** Để biết ai chịu trách nhiệm, khi nào chạy, thay đổi nào được áp dụng và hỗ trợ điều tra incident.

### Bài 47. Migration lock có thay source control review không?

**Đáp án:** Không. Lock chỉ serialize execution; review vẫn cần để kiểm tra correctness/risk.

### Bài 48. Khi nào cần migration runner riêng thay vì mỗi app replica tự chạy?

**Đáp án:** Trong hầu hết production deployments, runner riêng giúp kiểm soát thứ tự, quyền, locking, audit và rollout.

### Bài 49. Khi nào được xóa migration history record?

**Đáp án:** Không xóa tùy tiện. Chỉ theo repair/recovery procedure có kiểm chứng của tool và owner.

### Bài 50. Một migration process đáng tin cậy cần gì?

**Đáp án:** Versioning bất biến, checksum validation, serialized runner, transaction policy, backup/recovery, CI tests, schema drift detection, audit và post-deploy verification.

## 49. Checklist quản lý migration có phiên bản

| Giai đoạn | Câu hỏi |
|---|---|
| Design | Migration có mục đích và version duy nhất? |
| Source | File nằm trong source control và immutable sau deploy? |
| Naming | Version ordering và file naming ổn định? |
| History | History table/tool được quản lý đúng? |
| Checksum | Validate phát hiện thay đổi ngoài ý muốn? |
| Locking | Chỉ một runner thực thi tại một thời điểm? |
| Transaction | Script transactional hay non-transactional? |
| DDL | Lock/rewrite/index build đã được đánh giá? |
| Data | Backfill có batch, checkpoint và concurrency policy? |
| Compatibility | Old/new application versions cùng hoạt động được? |
| Permissions | Migration role theo least privilege? |
| CI | Full chain chạy từ database sạch? |
| Staging | Test trên data volume/schema gần production? |
| Backup | Backup/PITR và restore test sẵn sàng? |
| Deploy | Artifact giống nhau qua các môi trường? |
| Failure | Có runbook kiểm tra partial state và repair? |
| Drift | Có schema diff/catalog reconciliation? |
| Audit | Runner, version, checksum, time và outcome được ghi? |
| Recovery | Rollback/roll-forward và data-loss risk đã rõ? |
| Verify | History, schema và business invariants đã được xác nhận? |

## 50. Tài liệu tham khảo chính thức

- [PostgreSQL: ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) — lock, constraints, column changes và validation.
- [PostgreSQL: CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) — regular và concurrent index builds.
- [PostgreSQL: Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — lock modes và behavior.
- [PostgreSQL: Advisory Locks](https://www.postgresql.org/docs/current/explicit-locking.html#ADVISORY-LOCKS) — session/transaction advisory locks.
- [PostgreSQL: SET](https://www.postgresql.org/docs/current/sql-set.html) — session và transaction-local settings.
- [PostgreSQL: NOT VALID Constraints](https://www.postgresql.org/docs/current/sql-altertable.html) — add/validate constraints.
- [PostgreSQL: System Catalogs](https://www.postgresql.org/docs/current/catalogs.html) — inspect schema objects and metadata.
- [PostgreSQL: Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — sessions, locks, replication and database activity.
- [Flyway Documentation](https://documentation.red-gate.com/flyway) — versioned/repeatable migrations, schema history, validate and repair.
- [Liquibase Documentation](https://docs.liquibase.com/) — changelogs, changesets, DATABASECHANGELOG and DATABASECHANGELOGLOCK.

Các commands, locking behavior và tool features có thể thay đổi theo PostgreSQL major version và migration-tool version. Kiểm tra tài liệu đúng phiên bản, thử trên staging và xác nhận transaction support của từng DDL statement trước production deployment.

## 51. Tổng kết: migration là lịch sử có thể tái tạo

```text
Migration files in source control
             |
             v
Unique versions + immutable content
             |
             v
Validate checksum and history
             |
             v
Acquire migration lock
             |
             v
Run transactional / non-transactional steps
             |
             v
Record execution outcome
             |
             v
Verify schema + data + application
             |
             v
Audit, monitor and recover if needed
```

Những nguyên tắc cần nhớ:

1. **Mỗi thay đổi có version và mục đích rõ ràng.** Version giúp xác định thứ tự và tránh chạy trùng.
2. **Migration đã áp dụng phải immutable.** Sửa đổi tiếp theo được ghi bằng version mới.
3. **History table là ledger, không phải bằng chứng schema không drift.** Kết hợp checksum validation và schema diff.
4. **Chỉ một runner thực thi tại một thời điểm.** Dùng migration tool lock hoặc cơ chế serialization được thiết kế rõ.
5. **Phân biệt transactional và non-transactional DDL.** CREATE INDEX CONCURRENTLY cần boundary riêng và recovery plan.
6. **Tính tới lock và table size.** DDL nhanh vẫn có thể chờ lock lâu.
7. **Dùng expand-contract cho rolling deployments.** Giữ old/new application versions tương thích trong transition.
8. **Backfill theo batch và có checkpoint.** Kiểm soát WAL, replication lag và concurrent writes.
9. **Baseline phải dựa trên schema đã xác minh.** Nó ghi nhận mốc, không tự dựng lại database cũ.
10. **Không sửa/xóa history để che lỗi.** Điều tra trạng thái thật rồi dùng repair/corrective migration theo tool.
11. **Backup, PITR và restore test là phần của migration plan.** Rollback schema không phải lúc nào cũng đảo ngược data changes.
12. **CI phải test cả database sạch và đường nâng cấp.** Staging rehearsal giúp dự báo locks, duration và performance.
13. **Migration role theo least privilege.** Application runtime không cần quyền DDL/superuser.
14. **Xác minh sau deploy.** Kiểm tra history, catalogs, constraints, indexes, data invariants và business flows.

**Một câu để nhớ:** *Version hóa mỗi thay đổi, giữ migration đã chạy bất biến, ghi history đáng tin cậy và xác minh schema thực tế; đó là nền tảng để database có thể được nâng cấp nhất quán qua mọi môi trường.*

