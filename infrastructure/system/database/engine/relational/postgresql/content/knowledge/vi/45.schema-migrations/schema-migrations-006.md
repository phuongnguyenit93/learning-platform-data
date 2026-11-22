# Thêm chỉ mục CONCURRENTLY ngoài giao dịch migration phù hợp trong PostgreSQL

Index là một phần quan trọng của thiết kế truy vấn, nhưng thêm index trên một table đang được ứng dụng sử dụng có thể tạo ra lock và làm gián đoạn writes nếu dùng cách xây dựng thông thường. PostgreSQL cung cấp CREATE INDEX CONCURRENTLY để xây dựng index trong khi các thao tác INSERT, UPDATE và DELETE vẫn có thể tiếp tục trên table.

Có một yêu cầu quan trọng: **CREATE INDEX CONCURRENTLY không được chạy bên trong transaction block**. Nhiều migration frameworks mặc định bọc mỗi migration trong một transaction để bảo đảm các thay đổi DDL cùng thành công hoặc cùng rollback. Vì vậy, một migration tạo index concurrently phải được cấu hình chạy ngoài transaction theo cơ chế mà framework hỗ trợ.

Đây là một thay đổi về cách triển khai schema. Khi bỏ transaction wrapper, migration không còn có tính nguyên tử như migration DDL thông thường. Index build có thể kéo dài, bị hủy hoặc thất bại và để lại một index invalid. Migration runner cần quản lý trạng thái, logs, retries và cleanup rõ ràng.

Bài học này giải thích lock behavior và các phase của concurrent index build, cách viết migration ngoài transaction với các framework phổ biến, cách kiểm tra tiến độ và index validity, cách xử lý lỗi, cách tạo unique indexes, cùng quy trình triển khai an toàn trong production.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích khác biệt giữa CREATE INDEX và CREATE INDEX CONCURRENTLY.
2. Hiểu vì sao concurrent index build cho phép DML tiếp tục.
3. Giải thích vì sao lệnh không thể chạy trong transaction block.
4. Xác định migration framework có transaction wrapper mặc định hay không.
5. Cấu hình migration chạy ngoài transaction theo đúng framework/version.
6. Tách migration tạo index khỏi các DDL cần transaction.
7. Theo dõi tiến độ bằng pg_stat_progress_create_index.
8. Kiểm tra index readiness, validity và definition.
9. Xử lý invalid indexes sau migration failure.
10. Xây dựng unique index concurrently và xử lý duplicate data.
11. Hiểu giới hạn với partitioned tables và constraint attachment.
12. Thiết kế lock_timeout, statement_timeout, retries và concurrency controls.
13. Triển khai schema thay đổi theo chiến lược expand-and-contract.
14. Xây dựng runbook, verification và 80 bài tập thực hành.

## 2. Vì sao cần CREATE INDEX CONCURRENTLY?

CREATE INDEX thông thường xây index bằng cách quét table. Trong quá trình này PostgreSQL lấy lock ngăn các thao tác ghi đồng thời trên table. Các reads thông thường vẫn có thể tiếp tục, nhưng INSERT, UPDATE và DELETE có thể bị chặn cho đến khi build hoàn tất.

Với table nhỏ, thời gian build có thể ngắn. Với table lớn đang phục vụ OLTP traffic, một index build có thể kéo dài nhiều phút hoặc lâu hơn. Nếu DML bị chặn, request latency tăng, connection pools đầy và các transaction phía sau có thể xếp hàng.

CREATE INDEX CONCURRENTLY cho phép các thao tác ghi tiếp tục trong phần lớn quá trình build. Đổi lại, PostgreSQL phải thực hiện nhiều phase, nhiều lần quét/đợi transaction hơn và có thể tốn thời gian, I/O và WAL nhiều hơn.

### 2.1. So sánh hai cách tạo index

| Đặc điểm | CREATE INDEX | CREATE INDEX CONCURRENTLY |
| --- | --- | --- |
| DML trong lúc build | Bị chặn bởi lock của index build | Có thể tiếp tục |
| Reads thông thường | Có thể tiếp tục | Có thể tiếp tục |
| Số lần quét table | Một scan chính | Hai scans chính cùng các phase validation |
| Thời gian | Thường ngắn hơn | Thường lâu hơn |
| Lock | Mạnh hơn, ngăn writes | Nhẹ hơn đối với DML nhưng vẫn có lock và waits |
| Transaction block | Có thể chạy trong transaction | Không được chạy trong transaction block |
| Failure | Transaction thường rollback index creation | Có thể để lại invalid index |
| Phù hợp | Table ít traffic hoặc maintenance window | Table production cần tiếp tục nhận writes |

### 2.2. "Concurrent" không có nghĩa không lock

CREATE INDEX CONCURRENTLY vẫn lấy lock trên table và phải chờ một số transactions/snapshots. Nó giảm blocking đối với DML thông thường, nhưng không loại bỏ mọi dạng lock contention.

### 2.3. Đánh đổi

Concurrent build thường:
- Chạy lâu hơn do hai scans và các bước validation.
- Có thể chờ transactions lâu.
- Tạo thêm I/O và WAL trong khi workload hiện hữu vẫn chạy.
- Tăng tải CPU/storage.
- Có thể để lại invalid index khi thất bại.

### 2.4. Khi nào nên dùng?

Cân nhắc CONCURRENTLY khi table đang phục vụ traffic và việc chặn writes trong thời gian build không chấp nhận được. Với table nhỏ, staging hoặc maintenance window có thể dừng writes, cách thông thường có thể đơn giản và nhanh hơn.

## 3. Lock behavior

CREATE INDEX CONCURRENTLY sử dụng lock cho phép các thao tác đọc/ghi thông thường tiếp tục, nhưng vẫn xung đột với một số DDL và maintenance operations.

### 3.1. DML tiếp tục hoạt động

INSERT, UPDATE và DELETE có thể tiếp tục trong quá trình concurrent build. PostgreSQL phải bảo đảm các thay đổi xảy ra trong lúc index đang được xây được phản ánh đầy đủ trước khi đánh dấu index valid.

### 3.2. DDL có thể bị block

Các thao tác thay đổi cấu trúc table/index khác có thể xung đột với lock của concurrent build. Không nên chạy nhiều schema migrations trên cùng table cùng lúc.

### 3.3. Một concurrent build mỗi table tại một thời điểm

PostgreSQL chỉ cho phép một CREATE INDEX CONCURRENTLY chạy trên một table tại cùng thời điểm. Lập lịch các index builds trên cùng table theo thứ tự.

### 3.4. Transactions lâu có thể kéo dài build

Concurrent build phải chờ các transactions có thể nhìn thấy trạng thái table/index cũ hoặc snapshot không tương thích với việc xác nhận index. Một transaction idle in transaction hoặc query chạy lâu có thể khiến phase chờ kéo dài.

### 3.5. Lock timeout

Có thể đặt lock_timeout để migration không chờ lock quá lâu:

~~~sql
SET lock_timeout = '5s';
CREATE INDEX CONCURRENTLY orders_created_at_idx
    ON app.orders (created_at);
~~~

Giá trị chỉ là ví dụ. Lock timeout ngắn giúp tránh chờ vô hạn nhưng có thể khiến migration fail nếu table đang có DDL/maintenance cạnh tranh. Runner cần ghi lỗi và retry theo policy.

### 3.6. Lock timeout không phải statement timeout

lock_timeout giới hạn thời gian chờ từng lock acquisition. statement_timeout giới hạn tổng thời gian statement. Một index build có thể cần nhiều phút hoặc hàng giờ; không dùng một statement_timeout ngắn theo thói quen của application requests.

### 3.7. Theo dõi blocker

Trong lúc build, kiểm tra pg_stat_activity, pg_blocking_pids và pg_locks nếu phase chờ lâu. Xác định blocker trước khi cân nhắc cancel/terminate; không kill transactions tùy tiện.

## 4. Vì sao CREATE INDEX CONCURRENTLY không chạy trong transaction block?

PostgreSQL phải commit các trạng thái trung gian của concurrent index build và chờ transactions khác ở những thời điểm cụ thể. Nếu toàn bộ lệnh nằm trong một transaction block, server không thể thực hiện lifecycle đó theo yêu cầu.

Ví dụ không hợp lệ:

~~~sql
BEGIN;

CREATE INDEX CONCURRENTLY orders_created_at_idx
    ON app.orders (created_at);

COMMIT;
~~~

PostgreSQL trả lỗi cho biết CREATE INDEX CONCURRENTLY không thể chạy bên trong transaction block.

### 4.1. Transaction block có thể đến từ đâu?

Không chỉ câu lệnh BEGIN do người viết migration tạo ra. Transaction wrapper có thể được thêm bởi:
- Migration framework.
- Test harness.
- Database client hoặc deployment runner.
- Stored procedure/DO block hoặc script wrapper.
- Một transaction đã mở từ trước trong connection pool.

### 4.2. Autocommit

Một statement chạy độc lập trong psql với autocommit mặc định không nằm trong explicit transaction block:

~~~sql
CREATE INDEX CONCURRENTLY orders_created_at_idx
    ON app.orders (created_at);
~~~

Không thêm BEGIN/COMMIT quanh statement.

### 4.3. Tách migration

Nếu migration framework mặc định transactional, tạo migration riêng được đánh dấu non-transactional. Đừng chỉ đặt CREATE INDEX CONCURRENTLY vào giữa một file migration mà framework vẫn bọc toàn file trong transaction.

### 4.4. Không thể sửa bằng SAVEPOINT

SAVEPOINT vẫn nằm trong transaction block. Nó không giải quyết giới hạn này.

### 4.5. Không dùng DO block

Đặt CREATE INDEX CONCURRENTLY bên trong DO block hoặc function không biến nó thành một statement chạy ngoài transaction. Dùng migration runner/connection thực thi statement trực tiếp.

## 5. Tách migration non-transactional

Một schema change có thể cần nhiều thao tác, nhưng các thao tác không nhất thiết phải nằm trong cùng một migration.

Ví dụ:
1. Migration transactional tạo bảng/cột cần thiết.
2. Migration non-transactional tạo index concurrently.
3. Migration transactional thêm constraint hoặc thay đổi metadata sau khi index đã valid.
4. Migration tiếp theo cập nhật application behavior.

### 5.1. Vì sao nên tách?

- Framework có thể bật/tắt transaction ở cấp migration.
- Nếu index build thất bại, các thay đổi khác không bị giữ ở trạng thái nửa chừng trong cùng file.
- Retry và cleanup có scope rõ.
- Deployment logs dễ đọc hơn.
- Có thể chạy index build ở thời điểm ít tải hơn.

### 5.2. Không trộn transactional DDL

Một migration non-transactional có thể chạy từng statement riêng. Nếu file chứa nhiều DDL, một statement giữa file thất bại thì những statement trước đó có thể đã commit. Vì vậy, nên giữ migration non-transactional ngắn, tập trung vào một index hoặc một nhóm index có thể quản lý độc lập.

### 5.3. Migration state

Framework thường ghi migration version sau khi migration hoàn tất. Nhưng khi không có transaction bao trùm, cần hiểu chính xác thời điểm ghi migration record và cách framework xử lý failure. Không giả định index creation và migration metadata được commit nguyên tử cùng nhau.

### 5.4. Một index mỗi migration?

Đây là lựa chọn an toàn, dễ retry và dễ xác định trạng thái. Có thể nhóm nhiều index nếu chúng độc lập và runner có logging/cleanup tốt, nhưng phải tính rằng migration có thể hoàn thành một phần.

## 6. Ví dụ SQL trực tiếp

Một migration file chỉ chứa một statement:

~~~sql
CREATE INDEX CONCURRENTLY orders_created_at_idx
    ON app.orders (created_at);
~~~

Với psql:

~~~bash
psql "service=appdb" \
  -v ON_ERROR_STOP=1 \
  -c "CREATE INDEX CONCURRENTLY orders_created_at_idx ON app.orders (created_at);"
~~~

### 6.1. Không truyền BEGIN

Không dùng script:

~~~sql
BEGIN;
CREATE INDEX CONCURRENTLY orders_created_at_idx
    ON app.orders (created_at);
COMMIT;
~~~

### 6.2. Session settings

Có thể đặt session-level settings trước câu lệnh nếu runner giữ cùng connection:

~~~sql
SET application_name = 'migration_create_orders_index';
SET lock_timeout = '5s';
SET statement_timeout = '0';

CREATE INDEX CONCURRENTLY orders_created_at_idx
    ON app.orders (created_at);
~~~

Các SET statements chạy ở autocommit riêng nếu client đang bật autocommit. Nếu framework tự bọc toàn bộ migration trong transaction, các SET không giải quyết được vấn đề.

### 6.3. Statement timeout

statement_timeout=0 có nghĩa không giới hạn thời gian cho session trong ví dụ trên. Chỉ dùng nếu job runner có timeout/monitoring bên ngoài và có runbook dừng job. Một timeout hữu hạn dài hơn expected duration cũng có thể phù hợp.

### 6.4. psql ON_ERROR_STOP

Khi chạy bằng script, bật ON_ERROR_STOP để psql trả lỗi khi statement thất bại. Scheduler cần nhận exit code và lưu logs.

## 7. Migration framework: Rails

Active Record migrations mặc định thường được chạy trong transaction nếu adapter/database hỗ trợ transactional DDL. PostgreSQL adapter hỗ trợ transactional DDL, nên CREATE INDEX CONCURRENTLY cần tắt migration transaction cho migration đó.

~~~ruby
class AddCreatedAtIndexToOrders < ActiveRecord::Migration[7.1]
  disable_ddl_transaction!

  def change
    add_index :orders, :created_at, algorithm: :concurrently
  end
end
~~~

### 7.1. disable_ddl_transaction!

Khai báo ở cấp migration class. Không áp dụng như một lệnh SQL; đây là directive của Rails migration framework.

### 7.2. algorithm: :concurrently

Rails adapter chuyển yêu cầu tạo index thành SQL phù hợp với PostgreSQL concurrent index build.

### 7.3. Không dùng transaction callback

Vì migration không có transaction bao trùm, callbacks/operations khác trong migration không được bảo vệ nguyên tử. Giữ migration đơn giản và tránh trộn những thay đổi không liên quan.

### 7.4. Version compatibility

Cú pháp migration class version và adapter behavior phụ thuộc Rails version. Kiểm tra Rails documentation/source của version project đang dùng trước khi áp dụng.

### 7.5. Revert

Một migration dùng change/add_index có thể cho Rails suy ra cách revert, nhưng kiểm tra SQL được tạo và behavior thực tế. Drop index concurrently cũng phải chạy ngoài transaction.

## 8. Migration framework: Liquibase

Liquibase cho phép khai báo changeset không chạy trong transaction bằng runInTransaction=false.

Ví dụ XML:

~~~xml
<changeSet id="2026-11-add-orders-created-index"
           author="database-team"
           runInTransaction="false">
    <sql>
        CREATE INDEX CONCURRENTLY orders_created_at_idx
        ON app.orders (created_at)
    </sql>
</changeSet>
~~~

### 8.1. Một changeset riêng

Đặt CREATE INDEX CONCURRENTLY trong changeset riêng và không trộn các statements transactional khác.

### 8.2. Failure state

Vì changeset không chạy trong transaction, một lỗi giữa nhiều statements có thể để database ở trạng thái đã áp dụng một phần. Giữ changeset chỉ có một statement quan trọng và kiểm tra DATABASECHANGELOG sau failure.

### 8.3. Rollback

Khai báo rollback rõ ràng nếu framework yêu cầu. Nếu rollback dùng DROP INDEX CONCURRENTLY, rollback changeset cũng phải chạy ngoài transaction block.

### 8.4. runInTransaction=false không phải bảo đảm cho mọi tool wrapper

Xác minh Liquibase version, executor và database extension behavior. Kiểm tra logs để bảo đảm framework không mở transaction ngoài changeset.

## 9. Migration framework: Flyway

Flyway có transaction handling theo migration/database support và cho phép cấu hình executeInTransaction theo version/configuration được hỗ trợ.

Một cách cấu hình có thể là đặt thuộc tính non-transactional cho migration riêng theo cơ chế per-migration configuration của Flyway version đang dùng:

~~~properties
executeInTransaction=false
~~~

### 9.1. Xác minh cú pháp theo version

Cách đặt per-script configuration và tên file config phụ thuộc Flyway version/edition. Kiểm tra tài liệu version đang cài. Nếu framework không hỗ trợ per-migration transaction override trong cấu hình hiện tại, dùng một migration runner/command riêng được kiểm soát.

### 9.2. Một migration chỉ tạo index

Ví dụ migration SQL:

~~~sql
CREATE INDEX CONCURRENTLY orders_created_at_idx
    ON app.orders (created_at);
~~~

Không thêm BEGIN/COMMIT.

### 9.3. Migration history

Khi statement thất bại, kiểm tra schema history và index catalog. Không chỉ chạy migrate lại ngay lập tức; một invalid index có thể còn tồn tại và trùng tên.

### 9.4. Undo

Nếu dùng Flyway undo migrations, cấu hình transaction của undo script cũng cần phù hợp nếu có DROP INDEX CONCURRENTLY. Kiểm tra behavior của edition/version.

## 10. Migration framework: Django

Django migrations mặc định có thể chạy trong transaction trên PostgreSQL. Migration chứa CREATE INDEX CONCURRENTLY cần tắt atomic wrapper cho migration.

~~~python
from django.db import migrations

class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("orders", "0042_previous_migration"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE INDEX CONCURRENTLY orders_created_at_idx
                ON app_orders (created_at)
            """,
            reverse_sql="""
                DROP INDEX CONCURRENTLY IF EXISTS orders_created_at_idx
            """,
        ),
    ]
~~~

### 10.1. atomic = False

Khai báo ở migration class. Mỗi operation không còn được bao bởi một transaction duy nhất của migration.

### 10.2. Reverse SQL

DROP INDEX CONCURRENTLY cũng không thể chạy trong transaction block. Reverse operation phải được thực thi trong cùng điều kiện non-atomic.

### 10.3. Schema qualification

Tên table/index trong ví dụ phải khớp schema/table thực tế và Django database search path. Dùng schema-qualified names khi cần.

### 10.4. State vs database operation

Nếu migration chỉ dùng RunSQL, bảo đảm Django migration state phản ánh đúng indexes/constraints cần thiết. Có thể dùng SeparateDatabaseAndState hoặc operation phù hợp nếu framework model state cần index tương ứng.

## 11. Migration framework: Alembic/SQLAlchemy

Alembic thường chạy migrations trong transaction. Có thể dùng autocommit_block để thực hiện lệnh yêu cầu autocommit mode.

~~~python
from alembic import op

def upgrade():
    with op.get_context().autocommit_block():
        op.execute("""
            CREATE INDEX CONCURRENTLY orders_created_at_idx
            ON app.orders (created_at)
        """)

def downgrade():
    with op.get_context().autocommit_block():
        op.execute("""
            DROP INDEX CONCURRENTLY IF EXISTS app.orders_created_at_idx
        """)
~~~

### 11.1. autocommit_block

Alembic autocommit block có thể commit transaction đang mở trước khi vào block. Những operations trước đó trong cùng migration có thể đã commit riêng. Vì vậy, đặt concurrent index build trong migration độc lập là cách dễ kiểm soát hơn.

### 11.2. SQLAlchemy connection

Đảm bảo connection thực sự ở autocommit isolation behavior trong block. Không tự mở transaction wrapper bên ngoài.

### 11.3. Downgrade

Downgrade cũng cần autocommit block cho DROP INDEX CONCURRENTLY. Kiểm tra object name/schema chính xác.

### 11.4. Version compatibility

API và behavior phụ thuộc Alembic/SQLAlchemy version. Kiểm tra tài liệu project và test trên database clone.

## 12. Framework khác hoặc migration runner tự viết

Nếu framework không có directive non-transactional:
- Tạo một deployment step riêng.
- Mở một connection autocommit riêng.
- Gửi trực tiếp CREATE INDEX CONCURRENTLY.
- Đợi command hoàn tất.
- Kiểm tra index valid.
- Chỉ sau đó mới đánh dấu migration step complete.

### 12.1. Không dùng connection pool transaction mặc định

Một số application libraries tự mở transaction hoặc giữ connection trong transaction scope. Dùng connection chuyên biệt và xác nhận transaction state.

### 12.2. Kiểm tra transaction state

Trong session có thể kiểm tra:

~~~sql
SELECT
    pid,
    state,
    xact_start,
    application_name
FROM pg_stat_activity
WHERE pid = pg_backend_pid();
~~~

xact_start NULL là một tín hiệu session không có transaction đang mở tại thời điểm quan sát; hãy kết hợp với runner behavior và server logs.

### 12.3. Runner contract

Runner nên hỗ trợ:
- Non-transactional migration metadata.
- Timeout có thể cấu hình.
- Logging stdout/stderr.
- Exit status rõ.
- Không retry mù.
- Concurrency lock giữa deployment instances.
- Index validity check trước khi đánh dấu complete.

## 13. Theo dõi tiến độ bằng pg_stat_progress_create_index

PostgreSQL cung cấp pg_stat_progress_create_index để quan sát index build đang chạy.

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS table_name,
    index_relid::regclass AS index_name,
    command,
    phase,
    lockers_total,
    lockers_done,
    current_locker_pid,
    blocks_total,
    blocks_done,
    tuples_total,
    tuples_done
FROM pg_stat_progress_create_index
ORDER BY pid;
~~~

Các cột có thể thay đổi theo PostgreSQL major version. Dùng SELECT * hoặc kiểm tra catalog view definition trên version cụ thể trước khi viết dashboard dùng cố định.

### 13.1. Các phase thường gặp

Một concurrent index build có thể đi qua các phase như:
- initializing.
- waiting for writers before build.
- building index.
- waiting for writers before validation.
- index validation: scanning index.
- index validation: sorting tuples.
- index validation: scanning table.
- waiting for old snapshots.

Tên/phase cụ thể phụ thuộc version và loại index.

### 13.2. blocks_done và blocks_total

Cho biết tiến độ scan blocks ở phase tương ứng. Không phải mọi phase đều có progress denominator hữu ích.

### 13.3. tuples_done và tuples_total

Có thể cho biết tuple processing progress trong một số phases. Không diễn giải phần trăm tiến độ toàn job từ một cặp counters nếu phase thay đổi.

### 13.4. lockers_total và lockers_done

Cho biết số lượng lockers/transactions cần chờ theo phase. Nếu job đứng lâu ở phase waiting, tìm current_locker_pid và transaction liên quan.

### 13.5. Không thấy row

Nếu view không có row, có thể không có index build đang chạy, command đã kết thúc hoặc quyền visibility không đủ. Không kết luận job đã thành công chỉ vì view rỗng; kiểm tra pg_index.

## 14. Hiểu các phase concurrent build

Concurrent build có các bước bổ sung để DML tiếp tục trong khi index được tạo.

### 14.1. Initializing

PostgreSQL chuẩn bị catalog/index build state và xác định các điều kiện cần thiết.

### 14.2. Waiting for writers before build

Chờ các transactions đang ghi phù hợp hoàn tất để bắt đầu scan ở một trạng thái nhất quán.

### 14.3. Building index

PostgreSQL quét table và tạo index entries cho dữ liệu hiện có. DML vẫn có thể tiếp tục; các thay đổi đồng thời được theo dõi theo cơ chế concurrent build.

### 14.4. Waiting for writers before validation

Chờ transactions có thể ảnh hưởng tới validation phase hoàn tất.

### 14.5. Index validation

PostgreSQL kiểm tra index contents với table và xử lý các entries thay đổi trong lúc build. Đây là lý do có scan/validation bổ sung.

### 14.6. Waiting for old snapshots

PostgreSQL có thể phải chờ snapshots cũ không còn được sử dụng trước khi đánh dấu index valid. Long-running transactions có thể khiến phase này kéo dài.

### 14.7. Job có thể lâu dù phần trăm blocks đã 100%

Một số phase là wait phase hoặc catalog transition. blocks_done/blocks_total đạt 100% không có nghĩa toàn bộ command đã hoàn tất.

## 15. Kiểm tra index sau khi build

pg_index lưu metadata về trạng thái index.

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisready,
    i.indisvalid,
    i.indislive,
    i.indisunique,
    i.indisprimary
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
JOIN pg_class AS tbl ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
WHERE idx.relname = 'orders_created_at_idx';
~~~

### 15.1. indisready

Cho biết index đã sẵn sàng để được duy trì bởi INSERT/UPDATE/DELETE hay chưa.

### 15.2. indisvalid

Cho biết planner có thể sử dụng index như một index hợp lệ hay không. Sau build thành công, index phải có indisvalid=true.

### 15.3. indislive

Cho biết index còn live theo lifecycle. Index đang trong quá trình drop có thể có trạng thái khác.

### 15.4. Kiểm tra definition

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'app'
  AND indexname = 'orders_created_at_idx';
~~~

Đừng chỉ kiểm tra tên index. Xác nhận columns, expressions, predicate, access method, uniqueness và included columns đúng như migration mong đợi.

### 15.5. Index valid không chứng minh query dùng nó

Planner có thể chọn sequential scan nếu table nhỏ hoặc query đọc nhiều rows. Kiểm tra EXPLAIN plans và workload thực tế.

## 16. Xử lý invalid index sau failure

CREATE INDEX CONCURRENTLY có thể thất bại do duplicate keys, cancellation, deadlock/lock timeout, server restart, disk full hoặc lỗi I/O. Khi đó PostgreSQL có thể để lại index invalid.

### 16.1. Tìm invalid indexes

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisready,
    i.indisvalid,
    i.indislive,
    i.indisunique
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
JOIN pg_class AS tbl ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
WHERE NOT i.indisvalid
ORDER BY 1, 2, 3;
~~~

### 16.2. Invalid index vẫn chiếm storage

Index invalid có thể vẫn tồn tại và chiếm disk. Nếu indisready=true, PostgreSQL có thể tiếp tục duy trì index khi DML xảy ra, dù planner không dùng nó.

### 16.3. Unique invalid index cần đặc biệt cẩn trọng

Với CREATE UNIQUE INDEX CONCURRENTLY, uniqueness checks có thể bắt đầu trước khi index được đánh dấu valid. Nếu build thất bại ở phase muộn, index invalid có thể vẫn tiếp tục enforce uniqueness. Kiểm tra indisready, indisvalid và lỗi gốc trước khi drop.

### 16.4. Không retry mù

Nếu migration chạy lại với cùng index name, lệnh có thể báo relation already exists. Xác định index đó valid/invalid, definition có đúng không và migration history ở trạng thái nào.

### 16.5. Cleanup

Nếu quyết định loại bỏ invalid index, có thể dùng:

~~~sql
DROP INDEX CONCURRENTLY IF EXISTS app.orders_created_at_idx;
~~~

Lệnh DROP INDEX CONCURRENTLY cũng không được chạy trong transaction block. Nó có các restrictions riêng, bao gồm không thể dùng CASCADE và không thể drop index backing constraint theo cách thông thường.

### 16.6. Sau cleanup

- Xác nhận index không còn trong pg_class/pg_indexes.
- Xác nhận migration state.
- Xác định nguyên nhân failure.
- Sửa duplicate data hoặc capacity/lock issue.
- Chạy lại migration trong một non-transactional session.
- Xác minh index valid.

## 17. Unique index concurrently

Unique index thường cần thiết để enforce business key. Có thể tạo unique index concurrently để giảm write blocking.

~~~sql
CREATE UNIQUE INDEX CONCURRENTLY users_email_key_idx
    ON app.users (email);
~~~

### 17.1. Dữ liệu trùng

Nếu table đã có duplicate values theo unique key, build sẽ thất bại. Trước khi chạy, kiểm tra:

~~~sql
SELECT
    email,
    count(*) AS occurrences
FROM app.users
GROUP BY email
HAVING count(*) > 1
ORDER BY occurrences DESC
LIMIT 100;
~~~

Query này cần được điều chỉnh cho composite keys, expressions, collation, NULL semantics và partial predicate tương ứng với index definition.

### 17.2. Race conditions

Pre-check duplicates không bảo đảm build chắc chắn thành công. Application writes vẫn diễn ra trong lúc concurrent build; unique index sẽ kiểm tra các changes theo lifecycle của nó và có thể báo lỗi nếu xuất hiện duplicate.

### 17.3. Uniqueness enforcement timing

Trong concurrent unique build, PostgreSQL bắt đầu enforce uniqueness đối với các transactions khác trước khi index được đánh dấu valid. Vì vậy, ứng dụng có thể nhận unique violation trong khi migration vẫn đang ở phase build/validation.

### 17.4. NULL semantics

Unique indexes mặc định cho phép nhiều NULL values theo SQL semantics thông thường. PostgreSQL có tùy chọn NULLS NOT DISTINCT ở các versions hỗ trợ để coi NULL là equal cho mục đích uniqueness. Xác minh version và yêu cầu nghiệp vụ.

### 17.5. Composite unique index

~~~sql
CREATE UNIQUE INDEX CONCURRENTLY orders_tenant_external_id_idx
    ON app.orders (tenant_id, external_id);
~~~

Uniqueness được áp dụng trên tổ hợp columns. Pre-check duplicates cần group by cùng danh sách columns.

## 18. Tạo constraint từ unique index

Một số schema changes cần unique constraint trong catalog, không chỉ unique index. Có thể tạo unique index concurrently trước rồi gắn constraint bằng ALTER TABLE ... ADD CONSTRAINT ... USING INDEX.

~~~sql
CREATE UNIQUE INDEX CONCURRENTLY users_email_key_idx
    ON app.users (email);

ALTER TABLE app.users
    ADD CONSTRAINT users_email_key
    UNIQUE USING INDEX users_email_key_idx;
~~~

### 18.1. Hai bước có transaction behavior khác nhau

CREATE UNIQUE INDEX CONCURRENTLY chạy ngoài transaction block. ALTER TABLE ADD CONSTRAINT USING INDEX có thể chạy trong migration transactional riêng, theo lock behavior và framework phù hợp.

### 18.2. Lock khi attach

ALTER TABLE vẫn cần lock để thay đổi catalog/constraint state. Thời gian thường ngắn hơn build index nhưng có thể chờ lock. Đặt lock_timeout và theo dõi blocker.

### 18.3. Index requirements

Index phải đáp ứng điều kiện để dùng làm constraint, ví dụ unique B-tree index phù hợp, không phải partial index hoặc expression index trong các trường hợp constraint không hỗ trợ. Đọc documentation của version và constraint type.

### 18.4. Tên index/constraint

PostgreSQL có thể đổi tên index theo tên constraint khi attach nếu tên khác. Chọn tên rõ ràng và xác minh sau DDL.

### 18.5. Primary key

Để tạo primary key từ index, index phải đáp ứng thêm yêu cầu về NOT NULL trên key columns và các quy tắc của primary key. Nếu columns chưa NOT NULL, cần thiết kế migration riêng để tránh scan/lock bất ngờ.

## 19. Partial indexes và expression indexes

Concurrent build hỗ trợ nhiều loại index definitions như cách tạo index thông thường, nhưng cần cân nhắc semantics và query patterns.

### 19.1. Partial index

~~~sql
CREATE INDEX CONCURRENTLY orders_open_created_idx
    ON app.orders (created_at)
    WHERE status = 'open';
~~~

Index chỉ chứa rows thỏa predicate. Planner cần chứng minh query predicate tương thích để dùng index.

### 19.2. Expression index

~~~sql
CREATE INDEX CONCURRENTLY users_lower_email_idx
    ON app.users (lower(email));
~~~

Application query nên dùng expression tương thích, ví dụ WHERE lower(email) = lower($1).

### 19.3. Unique partial index

~~~sql
CREATE UNIQUE INDEX CONCURRENTLY active_users_email_idx
    ON app.users (email)
    WHERE deleted_at IS NULL;
~~~

Unique enforcement chỉ áp dụng cho rows thỏa predicate.

### 19.4. Included columns

~~~sql
CREATE INDEX CONCURRENTLY orders_customer_created_idx
    ON app.orders (customer_id, created_at)
    INCLUDE (status, total_amount);
~~~

INCLUDE có thể hỗ trợ index-only scans trong một số workload, nhưng tăng index size và write cost. Benchmark trước khi thêm nhiều included columns.

### 19.5. Collation và operator class

Index behavior phụ thuộc data type, collation và operator class. Dùng definition phù hợp với query operators và locale semantics.

## 20. Partitioned tables

Concurrent index creation trên partitioned parent có giới hạn phụ thuộc PostgreSQL major version. Trong nhiều phiên bản, CREATE INDEX CONCURRENTLY trực tiếp trên partitioned table không được hỗ trợ.

Một chiến lược thường dùng là:
1. Tạo index concurrently trên từng leaf partition.
2. Kiểm tra các child indexes hợp lệ và có definition khớp.
3. Tạo partitioned index trên parent bằng thao tác attach phù hợp.
4. Xác minh parent/child index hierarchy.

### 20.1. Ví dụ leaf partition

~~~sql
CREATE INDEX CONCURRENTLY orders_2026_10_customer_idx
    ON app.orders_2026_10 (customer_id);
~~~

### 20.2. Tạo parent index

~~~sql
CREATE INDEX orders_customer_idx
    ON ONLY app.orders (customer_id);
~~~

ONLY tạo parent partitioned index chưa tự build trên partitions. Sau đó attach các child indexes:

~~~sql
ALTER INDEX app.orders_customer_idx
    ATTACH PARTITION app.orders_2026_10_customer_idx;
~~~

Khi tất cả required partitions có indexes phù hợp và được attach, parent index có thể trở thành valid theo semantics của PostgreSQL.

### 20.3. Tên và definition

Child indexes phải tương thích với parent index definition: key columns, expressions, operator classes, collations, sort options và predicate theo yêu cầu. Kiểm tra trước attach.

### 20.4. Nhiều cấp partitioning

Nếu có subpartitioning, lập kế hoạch cho từng leaf index và hierarchy. Đừng chỉ kiểm tra một cấp parent-child.

### 20.5. Partition mới sau migration

Partition mới cần có index tương ứng. Tự động hóa partition provisioning phải tạo/attach indexes trước khi partition nhận workload quan trọng.

### 20.6. Version caveat

Khả năng concurrent build trực tiếp trên partitioned tables và các tiện ích hỗ trợ có thể thay đổi theo major version. Đọc tài liệu đúng server version trước khi chọn chiến lược.

## 21. IF NOT EXISTS và idempotency

Có thể viết:

~~~sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS orders_created_at_idx
    ON app.orders (created_at);
~~~

Nhưng IF NOT EXISTS chỉ tránh lỗi nếu relation cùng tên đã tồn tại. Nó không xác nhận index hiện có có cùng definition.

### 21.1. Wrong index with same name

Nếu index cùng tên nhưng khác columns/predicate/uniqueness, lệnh có thể bỏ qua và migration tưởng đã thành công. Sau đó application query vẫn không được tối ưu hoặc uniqueness requirement không được enforce.

### 21.2. Verify definition

Dùng pg_get_indexdef:

~~~sql
SELECT
    c.oid::regclass AS index_name,
    pg_get_indexdef(c.oid) AS definition,
    i.indisready,
    i.indisvalid
FROM pg_class AS c
JOIN pg_index AS i ON i.indexrelid = c.oid
WHERE c.oid = 'app.orders_created_at_idx'::regclass;
~~~

Nếu object không tồn tại, cast regclass sẽ lỗi; dùng to_regclass để query an toàn:

~~~sql
SELECT to_regclass('app.orders_created_at_idx');
~~~

### 21.3. Migration idempotency

Idempotency phải gồm:
- Kiểm tra migration history.
- Kiểm tra index existence.
- Kiểm tra definition.
- Kiểm tra validity/readiness.
- Xử lý invalid leftover.
- Chỉ đánh dấu complete sau verification.

### 21.4. Không dùng IF NOT EXISTS để che failure

Nếu build lần trước thất bại và để lại invalid index, IF NOT EXISTS có thể làm migration runner bỏ qua index đó. Luôn kiểm tra pg_index.

## 22. Lock và statement timeout cho migration

Chọn timeout theo mục tiêu vận hành, không dùng một giá trị cố định cho mọi index.

### 22.1. lock_timeout

Ngăn migration chờ lock acquisition quá lâu. Nếu timeout, job thất bại sớm để retry ở window khác.

### 22.2. statement_timeout

Concurrent build trên table lớn có thể chạy lâu. Timeout quá ngắn sẽ cancel build giữa chừng và có thể để invalid index. Chọn giá trị theo measured build duration, hoặc quản lý timeout ở job runner.

### 22.3. idle_in_transaction_session_timeout

Migration runner không nên để session idle trong transaction. Dù concurrent build cần chạy ngoài transaction, một wrapper lỗi có thể để transaction/session mở và giữ locks/snapshots. Theo dõi runner connections.

### 22.4. application_name

Đặt application_name dễ nhận diện, ví dụ schema-migration:create-orders-index, để quan sát pg_stat_activity và logs.

### 22.5. Cancel behavior

Nếu hủy command, kiểm tra pg_index sau đó. Đừng giả định cancellation đã xóa mọi catalog/file artifacts.

## 23. Theo dõi blocker và long-running transactions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event,
    clock_timestamp() - xact_start AS transaction_age,
    left(query, 500) AS query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

### 23.1. Idle in transaction

Một session idle in transaction có thể giữ snapshot cũ và khiến concurrent index build chờ ở phase waiting for old snapshots.

### 23.2. Blocking PID

~~~sql
SELECT
    waiting.pid AS waiting_pid,
    blocking.pid AS blocking_pid,
    blocking.application_name,
    blocking.state,
    blocking.xact_start,
    left(blocking.query, 500) AS blocking_query
FROM pg_stat_activity AS waiting
CROSS JOIN LATERAL unnest(pg_blocking_pids(waiting.pid)) AS p(blocking_pid)
JOIN pg_stat_activity AS blocking
  ON blocking.pid = p.blocking_pid;
~~~

Query này tìm lock blockers tại thời điểm chụp; một concurrent build có thể chờ snapshot/transaction mà không xuất hiện như lock wait đơn giản. Kết hợp phase trong pg_stat_progress_create_index.

### 23.3. Không terminate blocker tùy tiện

Terminate có thể rollback transaction ứng dụng và tạo retry storm. Xác định owner/business impact, rồi yêu cầu commit/rollback hoặc xử lý theo incident policy.

## 24. WAL, disk và I/O trong concurrent build

CREATE INDEX CONCURRENTLY đọc table nhiều lần, ghi index pages và tạo WAL. Workload DML tiếp tục đồng thời, nên peak I/O có thể cao hơn so với index build trong maintenance window.

### 24.1. Disk headroom

Tính dung lượng index mới, temporary sort files, WAL, archive backlog và replication retention. Không chạy khi volume gần đầy.

### 24.2. WAL generation

~~~sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    stats_reset
FROM pg_stat_wal;
~~~

Lấy snapshots trước/sau và tính delta wal_bytes. pg_stat_wal có từ PostgreSQL 14; kiểm tra version.

### 24.3. Replication lag

Concurrent index build có thể tạo WAL làm standby/CDC consumers chậm lại. Theo dõi pg_stat_replication, replication slots và archive.

### 24.4. Temporary files

Index build có thể cần sort/temp storage tùy access method và settings. Theo dõi temp_bytes, temp_files và filesystem usage.

### 24.5. I/O scheduling

Không xếp nhiều concurrent index builds, backup full và bulk loads trên cùng storage nếu chưa benchmark. Chỉ chạy một build mỗi table; nhiều tables vẫn có thể tranh chấp I/O.

## 25. Migration ordering trong expand-and-contract

Khi thêm index để hỗ trợ query mới, triển khai theo thứ tự an toàn.

### 25.1. Expand

1. Kiểm tra query pattern và index definition.
2. Tạo index concurrently bằng migration non-transactional.
3. Xác minh index valid.
4. Kiểm tra query plan và latency.

### 25.2. Deploy application

Deploy code dùng query mới sau khi index đã sẵn sàng nếu query phụ thuộc performance của index. Với unique index, application cần sẵn sàng xử lý unique violations ngay khi enforcement bắt đầu.

### 25.3. Contract

Nếu index cũ không còn cần:
1. Xác minh index mới được sử dụng.
2. Quan sát đủ workload cycle.
3. Kiểm tra constraints/dependencies.
4. Drop index cũ bằng DROP INDEX CONCURRENTLY trong migration non-transactional riêng.

### 25.4. Tránh deploy đồng thời

Nếu application deployment và index build chạy song song, query mới có thể chạy trước khi index valid. Thiết kế deployment dependency hoặc feature flag.

### 25.5. Index không phải contract logic

Index thường thay đổi performance/uniqueness behavior, nhưng không tự thay thế application validation, data migration hoặc business constraints.

## 26. Tạo index concurrently cho foreign key lookup

PostgreSQL không tự động tạo index trên referencing columns khi khai báo foreign key. Query joins/deletes/updates ở referenced table có thể cần index trên foreign-key columns.

~~~sql
CREATE INDEX CONCURRENTLY orders_customer_id_idx
    ON app.orders (customer_id);
~~~

### 26.1. Không phải mọi foreign key đều cần index

Đánh giá query patterns, table size, parent deletes/updates và write overhead. Index thêm vào sẽ tăng storage và chi phí DML.

### 26.2. Composite foreign key

Tạo index theo thứ tự columns phù hợp với predicates/joins. Foreign key column order và query access patterns cần được xem xét.

### 26.3. Unique constraints

Foreign key referenced columns cần unique/primary key phù hợp; index trên referencing columns chỉ hỗ trợ lookup/joins, không tự tạo constraint.

## 27. Concurrent index build trong môi trường production

Trước khi chạy:
- Xác định table size và expected build duration.
- Kiểm tra active transactions/long snapshots.
- Kiểm tra index cùng table đang build hay không.
- Kiểm tra disk/WAL/replication headroom.
- Xác nhận framework non-transactional setting.
- Xác định timeout và cancel policy.
- Thông báo owner và maintenance window.
- Bảo đảm logs/monitoring đang hoạt động.

Trong khi chạy:
- Theo dõi pg_stat_progress_create_index.
- Theo dõi pg_stat_activity, blockers và wait events.
- Theo dõi disk, I/O, WAL và replication lag.
- Không bắt đầu DDL cạnh tranh trên cùng table.
- Không đánh dấu migration complete khi command chưa kết thúc.

Sau khi chạy:
- Kiểm tra pg_index indisready/indisvalid.
- Kiểm tra pg_get_indexdef.
- Kiểm tra migration history.
- Kiểm tra query plans và application behavior.
- Theo dõi storage/replication sau khi build.
- Ghi kết quả vào change record.

## 28. Failure modes và cách xử lý

| Failure | Dấu hiệu | Hướng xử lý |
| --- | --- | --- |
| Transaction block | Server báo command không chạy trong transaction | Tắt wrapper, chạy riêng |
| Lock timeout | Lock acquisition timeout | Tìm blocker, retry có kiểm soát |
| Statement timeout/cancel | Client/server báo cancel | Kiểm tra invalid index và build state |
| Duplicate key | Unique index build thất bại | Tìm và xử lý duplicate rows |
| Disk full | No space left / I/O errors | Dừng workload phù hợp, mở rộng/giải phóng storage an toàn |
| Server restart | Connection mất, job interrupted | Kiểm tra index state và migration history |
| Invalid index leftover | indisvalid=false | Xác định readiness/uniqueness, cleanup hoặc repair |
| Same-name index | Relation already exists hoặc IF NOT EXISTS skip | So sánh definition/validity |
| Long snapshot wait | Progress phase chờ old snapshots | Tìm transaction cũ và xử lý theo policy |
| Replica lag | Standby/CDC lag tăng | Giảm concurrent load, xử lý consumer/storage |

### 28.1. Migration runner timeout nhưng server command vẫn chạy?

Một client timeout hoặc connection loss không luôn chứng minh backend đã dừng ngay. Kiểm tra pg_stat_progress_create_index và pg_stat_activity trước khi retry.

### 28.2. Job complete nhưng migration record thiếu

Có thể command thành công nhưng runner mất kết nối trước khi ghi history. Kiểm tra index definition/validity rồi reconcile migration state theo framework. Không chạy lại mù.

### 28.3. Migration record complete nhưng index invalid

Điều này cần xử lý như deployment incident. Xác định framework có ghi record trước khi operation hoàn tất hay không, kiểm tra index state và application impact.

## 29. Runbook: tạo index concurrently

1. Review index definition, columns, predicate, access method và expected benefit.
2. Kiểm tra duplicate data nếu index unique.
3. Kiểm tra index cùng table chưa có concurrent build khác.
4. Xem long-running transactions và idle-in-transaction sessions.
5. Kiểm tra free disk, WAL/archive, temp storage và replication lag.
6. Tạo migration riêng không transactional.
7. Cấu hình lock_timeout và job timeout phù hợp.
8. Chạy CREATE INDEX CONCURRENTLY.
9. Theo dõi progress phases.
10. Chờ command hoàn tất và kiểm tra exit status.
11. Xác minh indisready=true và indisvalid=true.
12. Xác minh pg_get_indexdef đúng.
13. Chạy EXPLAIN/query smoke tests.
14. Cập nhật migration history/change record.
15. Theo dõi query latency, WAL và replica lag.

## 30. Runbook: migration thất bại và để lại invalid index

1. Không retry ngay.
2. Xác định backend còn chạy hay đã kết thúc.
3. Đọc migration logs và PostgreSQL logs.
4. Kiểm tra pg_index flags.
5. Kiểm tra index definition và size.
6. Với unique index, đánh giá uniqueness enforcement hiện tại.
7. Tìm duplicate rows nếu lỗi liên quan uniqueness.
8. Xác định migration history đã được ghi hay chưa.
9. Chọn drop invalid index concurrently hoặc phương án repair được hỗ trợ.
10. Xác minh cleanup hoàn tất.
11. Sửa nguyên nhân gốc.
12. Chạy lại non-transactional migration.
13. Xác minh index valid và application behavior.

## 31. Runbook: migration bị block

1. Xác định PID và phase trong pg_stat_progress_create_index.
2. Xem current_locker_pid nếu có.
3. Kiểm tra pg_stat_activity và transaction age.
4. Xác định blocker owner/application.
5. Kiểm tra có DDL hoặc maintenance cạnh tranh không.
6. Đánh giá impact nếu cancel migration hoặc blocker.
7. Yêu cầu blocker kết thúc transaction nếu phù hợp.
8. Dùng cancel/terminate chỉ theo incident policy.
9. Theo dõi index state sau khi build dừng.
10. Điều chỉnh schedule/timeout và retry.

## 32. Kiểm thử migration trên staging

Một rehearsal tốt cần gần production về:
- PostgreSQL major version.
- Table size và row distribution.
- Index definitions và collations.
- Concurrent write rate.
- Long-running transactions.
- Storage IOPS/throughput.
- Replication/CDC topology.
- Migration framework/version/config.
- Deployment orchestration.

### 32.1. Đo duration

Ghi thời gian từng phase nếu có, tổng duration, wait time, scan time và verification time.

### 32.2. Đo application impact

So p50/p95/p99 latency, error rate, connection pool wait và throughput trước/trong/sau build.

### 32.3. Đo storage impact

Theo dõi IOPS, throughput, disk free, WAL bytes/sec, temp files và replica lag.

### 32.4. Failure rehearsal

Thử cancellation, lock timeout hoặc runner interruption trong staging để hiểu invalid-index cleanup và migration history reconciliation.

## 33. Những anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Đặt CREATE INDEX CONCURRENTLY trong migration transaction | PostgreSQL từ chối | Đánh dấu migration non-transactional |
| Tắt transaction cho cả file nhiều DDL | Có thể để lại state áp dụng một phần | Một migration ngắn cho index |
| Dùng IF NOT EXISTS rồi bỏ qua validation | Có thể giữ wrong/invalid index | Kiểm tra definition và indisvalid |
| Retry ngay sau timeout | Có thể đụng build còn chạy hoặc invalid index | Kiểm tra backend/catalog trước |
| Chạy nhiều concurrent builds trên cùng table | PostgreSQL không cho build đồng thời trên cùng table | Tuần tự hóa |
| Giả định concurrent không lock | DDL/transactions vẫn có thể block | Theo dõi locks và snapshots |
| Statement timeout quá ngắn | Build bị cancel, invalid index còn lại | Dùng runtime budget phù hợp |
| Không kiểm tra duplicate trước unique build | Migration có thể thất bại | Pre-check và xử lý duplicates |
| Tin pre-check uniqueness là bảo đảm | DML đồng thời vẫn có thể tạo duplicate | Để unique build enforce và xử lý race |
| Drop invalid unique index mà không đánh giá | Có thể bỏ uniqueness enforcement | Kiểm tra phase/readiness và business risk |
| Quên migration history | Database và migration metadata lệch | Reconcile theo catalog |
| Tạo parent partitioned index concurrently không hỗ trợ | Migration thất bại | Build leaf indexes và attach parent theo version |
| Drop index backing constraint | DDL bị chặn hoặc làm thay đổi constraint ngoài ý muốn | Gỡ constraint theo plan |
| Không tính WAL/disk | Volume đầy giữa build | Capacity gate |
| Không theo dõi replica lag | Consumer/standby tụt lại | Monitor WAL và slots |
| Chạy index build cùng backup lớn | Storage contention | Lập lịch và I/O budget |
| Deploy query trước index valid | Query plan/latency xấu | Dependency giữa schema và app deploy |
| Không test rollback | Rollback migration lỗi vì transaction wrapper | Test DROP INDEX CONCURRENTLY ngoài transaction |

## 34. Bài tập thực hành PostgreSQL

Thực hiện trên lab/staging hoặc database clone. Không tạo index lớn hoặc hủy migration trên production chỉ để thử nghiệm.

1. **Baseline:** tạo table lớn vừa phải và ghi nhận DML throughput.
2. **Regular build:** chạy CREATE INDEX trong lab khi writes tạm dừng.
3. **Concurrent build:** chạy CREATE INDEX CONCURRENTLY trên cùng dataset.
4. **Compare:** so sánh duration và DML availability.
5. **Transaction error:** thử CREATE INDEX CONCURRENTLY trong BEGIN/COMMIT và đọc lỗi.
6. **Autocommit:** chạy cùng lệnh ở psql autocommit mode.
7. **Progress:** mở pg_stat_progress_create_index trong session khác.
8. **Phases:** quan sát các phase của concurrent build.
9. **Lock:** tạo long transaction và xem build có phải chờ không.
10. **Blocker:** dùng pg_blocking_pids để tìm blocker khi có lock wait.
11. **Old snapshot:** tạo transaction snapshot lâu và quan sát waiting phase.
12. **Lock timeout:** đặt lock_timeout ngắn trong lab và quan sát failure.
13. **Statement timeout:** đặt timeout đủ ngắn để cancel test build.
14. **Invalid index:** xác định index invalid còn lại sau failure.
15. **Readiness:** so sánh indisready và indisvalid.
16. **Definition:** đọc pg_get_indexdef sau build.
17. **IF NOT EXISTS:** tạo index cùng tên với definition khác và quan sát behavior.
18. **Idempotency:** viết preflight kiểm tra existence/definition/validity.
19. **Rails:** tạo migration dùng disable_ddl_transaction!.
20. **Rails adapter:** xác nhận algorithm: :concurrently tạo SQL đúng.
21. **Liquibase:** viết changeset runInTransaction=false.
22. **Liquibase failure:** mô phỏng lỗi và kiểm tra DATABASECHANGELOG.
23. **Flyway:** cấu hình executeInTransaction=false theo version đang dùng.
24. **Flyway history:** mô phỏng command success nhưng runner connection loss và reconcile history.
25. **Django:** tạo migration atomic=False với RunSQL.
26. **Django reverse:** viết reverse_sql dùng DROP INDEX CONCURRENTLY.
27. **Alembic:** dùng autocommit_block cho CREATE INDEX CONCURRENTLY.
28. **Alembic downgrade:** dùng autocommit_block cho DROP INDEX CONCURRENTLY.
29. **Custom runner:** viết script psql không mở transaction.
30. **Exit status:** cấu hình ON_ERROR_STOP và kiểm tra scheduler exit code.
31. **Unique index:** tạo unique index concurrently trên column không có duplicate.
32. **Duplicate check:** tạo duplicate rows và viết pre-check.
33. **Concurrent race:** thử insert duplicate trong lúc unique build ở lab.
34. **Unique failure:** quan sát invalid unique index sau failure.
35. **Unique readiness:** xác định index còn enforce uniqueness khi indisvalid=false/indisready=true.
36. **Composite unique:** tạo unique index trên hai columns.
37. **NULL semantics:** thử unique index mặc định với nhiều NULL.
38. **NULLS NOT DISTINCT:** thử trên version hỗ trợ và so sánh.
39. **Partial index:** tạo partial index concurrently.
40. **Expression index:** tạo index trên lower(email).
41. **Included columns:** tạo covering index với INCLUDE.
42. **Foreign key lookup:** thêm index concurrently trên referencing columns.
43. **Constraint attach:** tạo unique index concurrently rồi ADD CONSTRAINT USING INDEX.
44. **Attach lock:** đo lock khi gắn constraint.
45. **Primary key:** nghiên cứu điều kiện dùng index để tạo primary key.
46. **Partition leaf:** tạo index concurrently trên một leaf partition.
47. **Parent index:** tạo partitioned index trên ONLY parent trong lab.
48. **Attach partition:** attach child index vào parent index.
49. **Partition version:** kiểm tra capability của major version đang chạy.
50. **Multiple builds:** thử chạy hai concurrent builds trên cùng table và quan sát behavior.
51. **Different tables:** benchmark concurrent builds trên hai tables khác nhau.
52. **WAL:** đo wal_bytes delta trong index build.
53. **Temp:** theo dõi temp_files/temp_bytes trong build.
54. **Disk:** đo filesystem free bytes trước/trong/sau build.
55. **Replication:** theo dõi pg_stat_replication trong concurrent build.
56. **Slot retention:** xem slot có giữ thêm WAL trong build không.
57. **I/O:** dùng pg_stat_io hoặc host metrics để đo I/O.
58. **Application latency:** benchmark p95/p99 khi build chạy.
59. **Index plan:** EXPLAIN query trước và sau khi index valid.
60. **Query use:** xác nhận planner có thể dùng index sau build.
61. **Cancel:** cancel build từ một session khác trong lab.
62. **Runner timeout:** mô phỏng client timeout và xác định server command còn chạy không.
63. **Cleanup:** DROP INDEX CONCURRENTLY invalid index.
64. **Drop transaction:** thử DROP INDEX CONCURRENTLY trong transaction và đọc lỗi.
65. **Constraint dependency:** thử drop index backing a constraint và quan sát restriction.
66. **Lock timeout retry:** viết retry policy có backoff.
67. **Advisory lock:** ngăn hai deployment instances cùng chạy migration.
68. **Migration history:** thiết kế reconciliation khi index valid nhưng migration record thiếu.
69. **Non-transactional batch:** cố ý tạo hai statements, làm statement thứ hai fail và phân tích partial state.
70. **Single-index migration:** tách hai concurrent index builds thành migrations riêng.
71. **Expand-contract:** triển khai index trước application query change.
72. **Drop old index:** viết non-transactional migration dùng DROP INDEX CONCURRENTLY.
73. **Capacity gate:** chặn build khi free disk dưới reserve.
74. **Timeout policy:** chọn lock_timeout/statement_timeout dựa trên staging measurements.
75. **Long transaction runbook:** tạo report sessions có thể kéo dài concurrent build.
76. **Failure runbook:** viết quy trình xử lý invalid index.
77. **Staging rehearsal:** chạy migration với table size gần production.
78. **Framework audit:** kiểm tra framework có transaction wrapper ngoài dự kiến không.
79. **Verification:** tự động kiểm tra index definition, indisready, indisvalid và migration history.
80. **Thiết kế tổng hợp:** xây quy trình deploy index production bằng migration non-transactional gồm preflight, framework config, concurrency control, progress monitoring, WAL/disk gates, failure cleanup, post-build verification và application rollout.

## 35. Checklist triển khai

### Trước migration

- [ ] Xác định đúng table, schema và index definition.
- [ ] Đánh giá query plan và lý do cần index.
- [ ] Kiểm tra duplicate data nếu index unique.
- [ ] Kiểm tra long-running transactions và DDL blockers.
- [ ] Kiểm tra table size, disk headroom, WAL và temp capacity.
- [ ] Kiểm tra replication/archive health.
- [ ] Xác định PostgreSQL major version và partition limitations.
- [ ] Tạo migration riêng cho concurrent index build.
- [ ] Cấu hình framework chạy ngoài transaction.
- [ ] Đặt timeout và retry/stop policy.
- [ ] Có staging rehearsal và owner.

### Trong migration

- [ ] Runner không mở transaction block.
- [ ] Chỉ một concurrent build trên table tại một thời điểm.
- [ ] application_name nhận diện migration.
- [ ] Theo dõi pg_stat_progress_create_index.
- [ ] Theo dõi blockers, I/O, WAL, disk và replication lag.
- [ ] Không đánh dấu migration complete trước khi command kết thúc.
- [ ] Lưu logs và exit status.

### Sau migration

- [ ] indisready=true.
- [ ] indisvalid=true.
- [ ] Definition đúng với yêu cầu.
- [ ] Migration history đồng bộ.
- [ ] Query plans/application smoke tests đạt.
- [ ] Replication/archive và disk ổn định.
- [ ] Invalid leftovers đã được xử lý.
- [ ] Change record có kết quả và duration.

### Nếu thất bại

- [ ] Xác nhận backend đã dừng.
- [ ] Kiểm tra index catalog state.
- [ ] Kiểm tra unique enforcement nếu index unique.
- [ ] Không retry mù.
- [ ] Cleanup ngoài transaction nếu cần.
- [ ] Xử lý nguyên nhân gốc.
- [ ] Reconcile migration metadata.
- [ ] Chạy lại và xác minh từ đầu.

## 36. Tổng kết

CREATE INDEX CONCURRENTLY là công cụ quan trọng để thay đổi schema trên table production đang nhận writes. Lệnh giảm blocking DML nhưng yêu cầu migration runner tôn trọng transaction boundary và có quy trình xử lý failure.

~~~text
PREPARE
  definition / duplicates / capacity / blockers
       |
       v
NON-TRANSACTIONAL MIGRATION
  CREATE INDEX CONCURRENTLY
       |
       v
MONITOR
  progress phases / waits / WAL / disk / replicas
       |
       v
VERIFY
  indisready = true
  indisvalid = true
  definition matches
       |
       v
DEPLOY DEPENDENT APPLICATION CHANGE
       |
       v
RECORD AND MONITOR
~~~

Những nguyên tắc quan trọng:

- **CREATE INDEX CONCURRENTLY không chạy trong transaction block.** Tắt transaction wrapper ở cấp migration/framework và chạy statement trực tiếp.
- **Tách concurrent index build thành migration riêng.** Khi non-transactional, các statements không còn rollback nguyên tử cùng nhau.
- **Concurrent không có nghĩa không lock.** Transactions lâu, snapshots cũ và DDL cạnh tranh vẫn có thể kéo dài hoặc block build.
- **Theo dõi progress phases.** pg_stat_progress_create_index giúp phân biệt scan với wait phases.
- **Xác minh indisready và indisvalid.** Chỉ tên index hoặc migration history không đủ chứng minh index đã usable.
- **Invalid index cần xử lý có chủ đích.** Với unique index, đánh giá uniqueness enforcement trước khi drop.
- **IF NOT EXISTS không kiểm tra definition.** Kiểm tra pg_get_indexdef và catalog state trước khi coi migration là complete.
- **Unique index có thể phát hiện duplicates trong lúc writes tiếp tục.** Pre-check hữu ích nhưng không loại bỏ race conditions.
- **Partitioned tables cần kế hoạch theo version.** Có thể phải tạo index concurrently trên từng leaf rồi attach vào parent.
- **Tính disk, WAL và replication impact.** Build có thể kéo dài, tạo I/O và làm lag consumers.
- **Rollback cũng phải non-transactional nếu dùng DROP INDEX CONCURRENTLY.** Test cả upgrade và downgrade paths.
- **Migration history phải được reconcile sau failure.** Client timeout không chứng minh backend đã dừng hoặc index đã bị xóa.

Một quy trình tốt đưa index vào production mà vẫn duy trì DML availability, kiểm soát transaction boundaries, phát hiện lỗi sớm và chỉ đánh dấu migration hoàn tất sau khi index đã được xác minh hợp lệ.

