# Kiểm tra catalog, phụ thuộc và đối tượng không còn sử dụng trong PostgreSQL

Quản trị PostgreSQL lâu dài đòi hỏi phải biết database đang chứa những đối tượng nào, đối tượng nào phụ thuộc vào nhau và đối tượng nào có thể đã không còn được sử dụng. Khi hệ thống phát triển, schema thường tích lũy tables, indexes, views, functions, sequences, roles, extensions và các objects phục vụ những phiên bản ứng dụng cũ. Nếu không có inventory và quy trình dọn dẹp an toàn, database ngày càng khó quản lý, migration dễ gặp lỗi và việc xóa nhầm một đối tượng có thể làm gián đoạn ứng dụng.

PostgreSQL lưu metadata của database trong **system catalogs**. Các catalog cho biết object identity, owner, type, columns, constraints, indexes, privileges, extension membership và dependencies. **Information schema** cung cấp một lớp view chuẩn hóa, còn **pg_catalog** cung cấp thông tin chi tiết theo implementation của PostgreSQL. Các statistics views bổ sung bằng chứng về hoạt động thực tế, nhưng không thể chứng minh chắc chắn rằng một object không còn được dùng.

Bài học thuộc chương **Quản trị**, tập trung vào:

- Khám phá cấu trúc database bằng information_schema và pg_catalog.
- Lập inventory cho schemas, tables, columns, indexes, constraints, views, routines, sequences và extensions.
- Đọc dependency graph qua pg_depend và pg_shdepend.
- Hiểu object ownership, ACL, extension membership và system-generated objects.
- Phân biệt object không có statistics với object thực sự không còn được dùng.
- Tìm unused index/table/function/sequence candidates bằng nhiều nguồn evidence.
- Kiểm tra invalid indexes, unvalidated constraints và quan hệ sequence-column.
- Dùng DROP RESTRICT, dependency inspection và deprecation workflow để dọn dẹp an toàn.
- Theo dõi thay đổi catalog, quyền truy cập và drift giữa environments.
- Xây dựng inventory, audit queries, cleanup runbook và bài thực hành.

> **Nguyên tắc quan trọng:** catalog mô tả những gì PostgreSQL biết về database; statistics mô tả hoạt động đã được ghi nhận trong một khoảng thời gian. Không có một câu query duy nhất có thể chứng minh object không còn được ứng dụng, job định kỳ, report, migration hoặc hệ thống bên ngoài sử dụng. Hãy coi kết quả “unused” là candidate cần xác minh trước khi thay đổi.

## 1. PostgreSQL metadata được lưu ở đâu?

PostgreSQL lưu định nghĩa của database objects trong các system catalogs. Các catalog là các tables thuộc schema hệ thống pg_catalog. Những views như information_schema.tables hoặc pg_tables giúp truy vấn metadata thuận tiện hơn.

### 1.1. Information schema

information_schema là tập hợp các views theo chuẩn SQL, ví dụ:

- information_schema.schemata: schemas có thể nhìn thấy theo quyền hiện tại.
- information_schema.tables: tables và views.
- information_schema.columns: columns.
- information_schema.table_constraints: constraints.
- information_schema.key_column_usage: columns tham gia key constraints.
- information_schema.referential_constraints: foreign-key relationships.
- information_schema.views: view definitions ở dạng chuẩn hóa.
- information_schema.routines: routines.
- information_schema.sequences: sequences.
- information_schema.role_table_grants: một phần thông tin grants.

Ưu điểm:

- Tên view/columns quen thuộc với người dùng SQL.
- Dễ viết query có khả năng chuyển đổi giữa các hệ quản trị.
- Hạn chế phụ thuộc vào catalog internals.
- Thường chỉ hiển thị objects mà role hiện tại có quyền xem.

Hạn chế:

- Không chứa toàn bộ metadata đặc thù PostgreSQL.
- Một số fields không có hoặc không đủ chi tiết để quản trị.
- Kết quả có thể bị giới hạn theo quyền của current user.
- Không thay thế được dependency graph hoặc các flags nội bộ.

### 1.2. pg_catalog

pg_catalog chứa catalogs và system views đặc thù PostgreSQL. Một số catalog quan trọng:

| Catalog/view | Nội dung |
| --- | --- |
| pg_namespace | Schemas |
| pg_class | Relations: tables, indexes, sequences, views, materialized views và một số relation-like objects |
| pg_attribute | Columns/attributes của relations |
| pg_type | Data types, domains, composite types, enums |
| pg_proc | Functions, procedures, aggregates và window routines |
| pg_constraint | Constraints |
| pg_index | Index metadata |
| pg_inherits | Table/index inheritance và partition relationships |
| pg_depend | Dependencies giữa database objects |
| pg_shdepend | Dependencies tới shared objects như roles/tablespaces |
| pg_rewrite | Rewrite rules, bao gồm view rules |
| pg_trigger | Triggers |
| pg_extension | Extensions được cài trong database |
| pg_description | Comments/descriptions |
| pg_roles | Roles và role attributes |
| pg_database | Databases trong cluster |
| pg_default_acl | Default privileges |

Catalog columns và semantics có thể thay đổi theo major version. Truy vấn quản trị chạy trên nhiều phiên bản cần kiểm tra column availability thay vì giả định schema giống nhau.

### 1.3. Các views tiện ích

Ngoài catalogs, PostgreSQL có các views dễ dùng hơn:

- pg_tables và pg_views.
- pg_matviews.
- pg_indexes.
- pg_sequences.
- pg_stats.
- pg_stat_user_tables.
- pg_stat_user_indexes.
- pg_stat_user_functions.
- pg_stat_activity.
- pg_stat_database.

Các views thống kê có visibility rules riêng. User không có quyền giám sát phù hợp có thể chỉ thấy một phần thông tin hoặc không thấy query text của sessions khác.

### 1.4. Catalog là metadata, không phải business registry

Catalog có thể trả lời:

- Table tồn tại ở schema nào?
- Ai sở hữu table?
- Index có valid không?
- View phụ thuộc vào relation nào?
- Sequence có ownership dependency với column nào?
- Object thuộc extension nào?
- Role có quyền gì?

Catalog không nhất thiết trả lời:

- Ứng dụng nào còn gọi table?
- Một report chạy vào cuối tháng có dùng view này không?
- Một external service có gọi function qua dynamic SQL không?
- Một dashboard cũ có kết nối tới database không?
- Object có được dùng trong backup/restore hoặc migration workflow không?

Cần kết hợp catalog, runtime statistics, query logs, application code, job inventory và owner confirmation.

## 2. Quy tắc đặt tên và xác định object

Trước khi truy vấn dependency hoặc lên kế hoạch drop, cần xác định chính xác object.

### 2.1. Schema và object name

Tên object trong PostgreSQL được xác định trong namespace. Hai schemas có thể chứa objects cùng tên:

```sql
CREATE SCHEMA app;
CREATE SCHEMA reporting;

CREATE TABLE app.orders (
    id bigint PRIMARY KEY
);

CREATE VIEW reporting.orders AS
SELECT id FROM app.orders;
```

Luôn ghi đầy đủ schema khi inventory, kiểm tra dependency và viết migration. Tránh dựa vào search_path để xác định object trong script quản trị.

### 2.2. OID

Mỗi database object có một Object Identifier (OID) trong catalogs tương ứng. Với relation, OID nằm trong pg_class.oid. Với function, OID nằm trong pg_proc.oid.

OID hữu ích để join catalogs và xác định object trong một database. Không coi OID là business ID hoặc identifier ổn định qua dump/restore, drop/recreate hay migration.

```sql
SELECT
    c.oid,
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'app'
ORDER BY c.relname;
```

### 2.3. to_regclass và regclass

to_regclass chuyển tên relation thành OID nếu tìm thấy, hoặc trả NULL nếu không tồn tại:

```sql
SELECT to_regclass('app.orders') AS relation_oid;
```

Cast sang regclass có thể dùng trong query để tham chiếu object rõ ràng:

```sql
SELECT 'app.orders'::regclass;
```

Schema-qualified names giúp tránh nhầm lẫn khi nhiều schemas có object cùng tên. Với tên có chữ hoa hoặc ký tự đặc biệt, phải dùng double quotes đúng quy tắc identifier.

### 2.4. Không dùng OID lưu lâu dài qua môi trường

OID của table ở development không nhất thiết bằng OID ở staging/production. Dùng schema + object name + object type hoặc một inventory key do hệ thống quản trị định nghĩa khi so sánh environments.

## 3. Lập inventory schemas và relations

Bước đầu tiên khi audit là liệt kê objects trong phạm vi quản trị.

### 3.1. Liệt kê schemas

```sql
SELECT
    n.oid,
    n.nspname AS schema_name,
    pg_get_userbyid(n.nspowner) AS owner
FROM pg_namespace AS n
WHERE n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
ORDER BY n.nspname;
```

Không xóa schema chỉ vì không thấy tables. Schema có thể chứa functions, types, domains, operators, collations, policies hoặc objects được ứng dụng tham chiếu qua dynamic SQL.

### 3.2. Liệt kê relations theo schema

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    CASE c.relkind
        WHEN 'r' THEN 'table'
        WHEN 'p' THEN 'partitioned table'
        WHEN 'i' THEN 'index'
        WHEN 'I' THEN 'partitioned index'
        WHEN 'S' THEN 'sequence'
        WHEN 'v' THEN 'view'
        WHEN 'm' THEN 'materialized view'
        WHEN 'f' THEN 'foreign table'
        WHEN 't' THEN 'TOAST table'
        WHEN 'c' THEN 'composite type relation'
        ELSE c.relkind::text
    END AS object_type,
    CASE c.relpersistence
        WHEN 'p' THEN 'permanent'
        WHEN 'u' THEN 'unlogged'
        WHEN 't' THEN 'temporary'
    END AS persistence,
    pg_get_userbyid(c.relowner) AS owner
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
ORDER BY n.nspname, c.relkind, c.relname;
```

pg_class chứa nhiều loại relation-like objects, không chỉ ordinary tables. Khi viết inventory, cần phân biệt relation kind thay vì đặt tên chung là table.

### 3.3. Đếm objects theo schema và loại

```sql
SELECT
    n.nspname AS schema_name,
    CASE c.relkind
        WHEN 'r' THEN 'table'
        WHEN 'p' THEN 'partitioned table'
        WHEN 'i' THEN 'index'
        WHEN 'I' THEN 'partitioned index'
        WHEN 'S' THEN 'sequence'
        WHEN 'v' THEN 'view'
        WHEN 'm' THEN 'materialized view'
        WHEN 'f' THEN 'foreign table'
        ELSE 'other relation'
    END AS object_type,
    count(*) AS object_count
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
GROUP BY n.nspname, c.relkind
ORDER BY n.nspname, object_type;
```

Dùng counts để theo dõi schema growth giữa các lần release hoặc giữa environments. Counts không thể hiện đầy đủ object complexity hoặc data volume.

### 3.4. Kích thước tables và indexes

```sql
SELECT
    schemaname,
    relname AS table_name,
    pg_size_pretty(pg_relation_size(
        format('%I.%I', schemaname, relname)::regclass
    )) AS main_fork_size,
    pg_size_pretty(pg_table_size(
        format('%I.%I', schemaname, relname)::regclass
    )) AS table_size,
    pg_size_pretty(pg_total_relation_size(
        format('%I.%I', schemaname, relname)::regclass
    )) AS total_size
FROM pg_tables
WHERE schemaname NOT LIKE 'pg\_%'
  AND schemaname <> 'information_schema'
ORDER BY pg_total_relation_size(
    format('%I.%I', schemaname, relname)::regclass
) DESC;
```

- pg_relation_size đo fork được yêu cầu, mặc định là main fork.
- pg_table_size bao gồm table storage và các thành phần liên quan như TOAST nhưng không bao gồm toàn bộ indexes.
- pg_total_relation_size bao gồm table, TOAST và indexes.

Kích thước lớn không đồng nghĩa object không còn được dùng. Ngược lại, table nhỏ vẫn có thể là bảng cấu hình quan trọng.

## 4. Kiểm tra columns, defaults và types

Một inventory hữu ích cần thể hiện schema contract của table.

### 4.1. Liệt kê columns

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    a.attnum AS ordinal_position,
    a.attname AS column_name,
    format_type(a.atttypid, a.atttypmod) AS data_type,
    a.attnotnull AS not_null,
    a.attidentity AS identity_kind,
    a.attgenerated AS generated_kind,
    pg_get_expr(ad.adbin, ad.adrelid) AS default_expression
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
JOIN pg_attribute AS a
    ON a.attrelid = c.oid
LEFT JOIN pg_attrdef AS ad
    ON ad.adrelid = c.oid
   AND ad.adnum = a.attnum
WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
  AND a.attnum > 0
  AND NOT a.attisdropped
  AND n.nspname = 'app'
ORDER BY c.relname, a.attnum;
```

attisdropped cho biết column đã bị drop về mặt logic nhưng catalog vẫn giữ placeholder nội bộ. Không hiển thị những attributes này như columns đang tồn tại.

### 4.2. Kiểm tra custom types và domains

```sql
SELECT
    n.nspname AS schema_name,
    t.typname AS type_name,
    t.typtype,
    t.typcategory,
    pg_get_userbyid(t.typowner) AS owner
FROM pg_type AS t
JOIN pg_namespace AS n
    ON n.oid = t.typnamespace
WHERE n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
ORDER BY n.nspname, t.typname;
```

Một type có thể được dùng trong table columns, function signatures, arrays, composite types hoặc application serialization. Không drop type chỉ vì không xuất hiện trực tiếp trong một bảng.

### 4.3. Enum values

```sql
SELECT
    n.nspname AS schema_name,
    t.typname AS enum_type,
    e.enumsortorder,
    e.enumlabel
FROM pg_type AS t
JOIN pg_namespace AS n
    ON n.oid = t.typnamespace
JOIN pg_enum AS e
    ON e.enumtypid = t.oid
ORDER BY n.nspname, t.typname, e.enumsortorder;
```

Enum labels có thể được ứng dụng dùng trong code và API contract. Catalog dependencies chỉ cho biết một phần quan hệ; application code và serialized data cũng cần được kiểm tra trước khi thay đổi.

## 5. Inventory constraints và foreign keys

Constraints thể hiện các quy tắc toàn vẹn dữ liệu và có thể gắn với indexes.

### 5.1. Liệt kê constraints

```sql
SELECT
    n.nspname AS schema_name,
    t.relname AS table_name,
    con.conname AS constraint_name,
    CASE con.contype
        WHEN 'p' THEN 'primary key'
        WHEN 'u' THEN 'unique'
        WHEN 'f' THEN 'foreign key'
        WHEN 'c' THEN 'check'
        WHEN 'x' THEN 'exclusion'
        WHEN 'n' THEN 'not null'
        ELSE con.contype::text
    END AS constraint_type,
    con.convalidated AS validated,
    pg_get_constraintdef(con.oid, true) AS definition,
    NULLIF(con.conindid, 0)::regclass AS supporting_index
FROM pg_constraint AS con
JOIN pg_class AS t
    ON t.oid = con.conrelid
JOIN pg_namespace AS n
    ON n.oid = t.relnamespace
WHERE n.nspname = 'app'
ORDER BY t.relname, con.conname;
```

Một số loại constraints không gắn với table theo cùng cách; query trên tập trung constraints có relation được xác định qua conrelid.

### 5.2. Foreign-key relationships

```sql
SELECT
    child_ns.nspname AS child_schema,
    child.relname AS child_table,
    fk.conname AS foreign_key_name,
    parent_ns.nspname AS parent_schema,
    parent.relname AS parent_table,
    pg_get_constraintdef(fk.oid, true) AS definition,
    fk.convalidated AS validated
FROM pg_constraint AS fk
JOIN pg_class AS child
    ON child.oid = fk.conrelid
JOIN pg_namespace AS child_ns
    ON child_ns.oid = child.relnamespace
JOIN pg_class AS parent
    ON parent.oid = fk.confrelid
JOIN pg_namespace AS parent_ns
    ON parent_ns.oid = parent.relnamespace
WHERE fk.contype = 'f'
ORDER BY child_ns.nspname, child.relname, fk.conname;
```

Foreign key tạo dependency tới referenced table và thường dựa trên unique/primary key index ở phía referenced table. PostgreSQL không tự động tạo index trên columns phía referencing table; việc có cần index đó hay không phụ thuộc delete/update workload và query patterns.

### 5.3. Constraints chưa validate

```sql
SELECT
    n.nspname AS schema_name,
    t.relname AS table_name,
    con.conname AS constraint_name,
    con.contype,
    pg_get_constraintdef(con.oid, true) AS definition
FROM pg_constraint AS con
JOIN pg_class AS t
    ON t.oid = con.conrelid
JOIN pg_namespace AS n
    ON n.oid = t.relnamespace
WHERE NOT con.convalidated
ORDER BY n.nspname, t.relname, con.conname;
```

Constraint chưa validate có thể là kết quả của migration dùng NOT VALID. Đây không tự động là lỗi: PostgreSQL vẫn áp dụng constraint cho rows mới theo semantics tương ứng, trong khi dữ liệu cũ chưa được kiểm tra đầy đủ. Xác nhận lý do và kế hoạch validation.

## 6. Inventory indexes và trạng thái hợp lệ

Indexes tiêu thụ storage và tạo write overhead. Index inventory giúp tìm invalid indexes, index không có scans và các indexes gắn với constraints.

### 6.1. Liệt kê indexes

```sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisprimary AS is_primary,
    i.indisunique AS is_unique,
    i.indisvalid AS is_valid,
    i.indisready AS is_ready,
    i.indisreplident AS is_replica_identity,
    pg_size_pretty(pg_relation_size(idx.oid)) AS index_size,
    pg_get_indexdef(idx.oid) AS index_definition
FROM pg_index AS i
JOIN pg_class AS idx
    ON idx.oid = i.indexrelid
JOIN pg_class AS tbl
    ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns
    ON ns.oid = tbl.relnamespace
WHERE ns.nspname = 'app'
ORDER BY tbl.relname, idx.relname;
```

### 6.2. Index không valid hoặc chưa ready

```sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisvalid,
    i.indisready,
    i.indislive,
    pg_get_indexdef(i.indexrelid) AS definition
FROM pg_index AS i
JOIN pg_class AS idx
    ON idx.oid = i.indexrelid
JOIN pg_class AS tbl
    ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns
    ON ns.oid = tbl.relnamespace
WHERE NOT i.indisvalid
   OR NOT i.indisready
   OR NOT i.indislive
ORDER BY ns.nspname, tbl.relname, idx.relname;
```

Invalid index có thể xuất hiện sau failed concurrent index build hoặc một thao tác DDL bị gián đoạn. Đừng drop/rebuild ngay khi chưa kiểm tra operation đang chạy, constraints phụ thuộc và log của lần build.

### 6.3. Index backing constraints

```sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    con.conname AS constraint_name,
    con.contype AS constraint_type,
    pg_get_constraintdef(con.oid, true) AS constraint_definition
FROM pg_constraint AS con
JOIN pg_class AS tbl
    ON tbl.oid = con.conrelid
JOIN pg_namespace AS ns
    ON ns.oid = tbl.relnamespace
JOIN pg_class AS idx
    ON idx.oid = con.conindid
WHERE con.conindid <> 0
ORDER BY ns.nspname, tbl.relname, con.conname;
```

Index hỗ trợ primary key, unique hoặc exclusion constraint có vai trò bảo đảm tính đúng đắn dữ liệu. Không xóa index loại này chỉ vì statistics cho thấy idx_scan bằng 0.

### 6.4. Index không có scans là candidate, không phải kết luận

```sql
SELECT
    s.schemaname,
    s.relname AS table_name,
    s.indexrelname AS index_name,
    s.idx_scan,
    s.idx_tup_read,
    s.idx_tup_fetch,
    i.indisprimary,
    i.indisunique,
    i.indisreplident,
    EXISTS (
        SELECT 1
        FROM pg_constraint AS con
        WHERE con.conindid = i.indexrelid
    ) AS backs_constraint,
    pg_size_pretty(pg_relation_size(i.indexrelid)) AS index_size,
    pg_get_indexdef(i.indexrelid) AS definition
FROM pg_stat_user_indexes AS s
JOIN pg_index AS i
    ON i.indexrelid = s.indexrelid
WHERE s.idx_scan = 0
ORDER BY pg_relation_size(i.indexrelid) DESC;
```

Kết quả chỉ là danh sách cần xem xét. Một index có idx_scan = 0 vẫn có thể:

- Được dùng bởi workload cuối tháng hoặc theo mùa.
- Được dùng ở database khác/environment khác.
- Có scans trước lần reset statistics.
- Bảo vệ uniqueness hoặc primary key.
- Được dùng làm replica identity.
- Hỗ trợ một migration, maintenance hoặc query rất hiếm.
- Chưa được sử dụng vì cache/plan behavior hiện tại nhưng vẫn cần trong tương lai.

Không tự động drop mọi index có idx_scan = 0.

### 6.5. Thời điểm reset statistics

Trước khi dùng index/table counters, kiểm tra thời điểm stats reset:

```sql
SELECT
    datname,
    stats_reset
FROM pg_stat_database
ORDER BY datname;
```

Stats có thể bị reset bởi administrator hoặc lifecycle events. Nếu statistics window chỉ bao phủ vài phút sau restart, idx_scan = 0 không có nhiều ý nghĩa. So sánh qua một chu kỳ business đầy đủ và kiểm tra logs/traces.

## 7. Đánh giá tables ít hoặc không có hoạt động

PostgreSQL cung cấp table statistics để theo dõi scans và row modifications.

### 7.1. Table statistics

```sql
SELECT
    schemaname,
    relname AS table_name,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY seq_scan + COALESCE(idx_scan, 0);
```

Một số fields có thể khác theo PostgreSQL major version. Nếu automation cần chạy trên version cũ, kiểm tra view definition trước.

### 7.2. Table không có scans

```sql
SELECT
    schemaname,
    relname AS table_name,
    seq_scan,
    idx_scan,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_live_tup,
    n_dead_tup
FROM pg_stat_user_tables
WHERE COALESCE(seq_scan, 0) = 0
  AND COALESCE(idx_scan, 0) = 0
ORDER BY n_live_tup DESC;
```

Đây là candidate inventory. Table có thể được đọc qua view/function hoặc truy vấn hiếm. Một bảng chỉ được ghi vào có thể vẫn là outbox, staging, audit hoặc queue table.

### 7.3. Writes không chứng minh có consumer

n_tup_ins, n_tup_upd và n_tup_del phản ánh hoạt động ghi, không chứng minh ứng dụng nào đang đọc. Tương tự, table có zero scans không chứng minh nó vô dụng.

Kiểm tra cả:

- Foreign keys và dependencies.
- Triggers/rules.
- Views/materialized views.
- Functions và procedures.
- Application repositories/ORM mappings.
- Scheduled jobs, ETL và BI queries.
- Audit, retention, backup và compliance requirements.

### 7.4. Table statistics là counters, không phải event history

Statistics views tổng hợp hoạt động trong một khoảng thời gian. Chúng không lưu mọi câu query hoặc caller. Nếu cần biết ai đã truy cập object, phải có logging/auditing/tracing phù hợp từ trước.

## 8. Kiểm tra views và materialized views

Views có thể phụ thuộc vào nhiều tables và views khác. Một view không được query trực tiếp vẫn có thể là API contract cho ứng dụng hoặc được gọi bởi view khác.

### 8.1. Inventory views

```sql
SELECT
    schemaname,
    viewname,
    viewowner,
    definition
FROM pg_views
WHERE schemaname NOT LIKE 'pg\_%'
  AND schemaname <> 'information_schema'
ORDER BY schemaname, viewname;
```

### 8.2. Inventory materialized views

```sql
SELECT
    schemaname,
    matviewname,
    matviewowner,
    ispopulated,
    definition
FROM pg_matviews
WHERE schemaname NOT LIKE 'pg\_%'
  AND schemaname <> 'information_schema'
ORDER BY schemaname, matviewname;
```

Materialized view lưu kết quả vật lý và có thể chiếm nhiều storage. Kiểm tra refresh schedule, consumer reports, owner và freshness requirements trước khi drop.

### 8.3. View definition

Có thể lấy definition bằng:

```sql
SELECT pg_get_viewdef('reporting.orders_summary'::regclass, true);
```

pg_get_viewdef trả về query definition đã được PostgreSQL lưu. Nó giúp đọc cấu trúc view nhưng không thay thế dependency graph hoặc kiểm tra runtime usage.

### 8.4. View không có usage counter trực tiếp

PostgreSQL không cung cấp một counter phổ quát cho số lần mỗi view được query. Có thể tìm query text trong logs hoặc pg_stat_statements, nhưng dynamic SQL, prepared statements, normalized query text và nested execution khiến việc mapping không hoàn hảo.

## 9. Inventory functions, procedures và triggers

Routine có thể được gọi trực tiếp, gián tiếp qua trigger, view, application code hoặc dynamic SQL.

### 9.1. Liệt kê routines

```sql
SELECT
    n.nspname AS schema_name,
    p.proname AS routine_name,
    pg_get_function_identity_arguments(p.oid) AS identity_arguments,
    CASE p.prokind
        WHEN 'f' THEN 'function'
        WHEN 'p' THEN 'procedure'
        WHEN 'a' THEN 'aggregate'
        WHEN 'w' THEN 'window function'
        ELSE p.prokind::text
    END AS routine_type,
    pg_get_userbyid(p.proowner) AS owner,
    l.lanname AS language,
    p.prosecdef AS security_definer,
    p.provolatile AS volatility
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
JOIN pg_language AS l
    ON l.oid = p.prolang
WHERE n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
ORDER BY n.nspname, p.proname, identity_arguments;
```

Function overloads có thể cùng tên nhưng khác argument types. Vì vậy, chỉ tên function không đủ để xác định object duy nhất.

### 9.2. Function definitions

```sql
SELECT
    n.nspname AS schema_name,
    p.proname AS function_name,
    pg_get_function_identity_arguments(p.oid) AS arguments,
    pg_get_functiondef(p.oid) AS definition
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname = 'app'
  AND p.prokind IN ('f', 'p')
ORDER BY p.proname, arguments;
```

Không xuất toàn bộ definitions vào log hoặc ticket có quyền truy cập rộng nếu function body chứa literal secrets hoặc logic nhạy cảm.

### 9.3. Function statistics

Khi track_functions được bật phù hợp, PostgreSQL có thể cung cấp thống kê trong pg_stat_user_functions:

```sql
SELECT
    schemaname,
    funcname,
    calls,
    total_time,
    self_time
FROM pg_stat_user_functions
ORDER BY total_time DESC;
```

Nếu function tracking tắt, calls có thể không được ghi nhận như mong đợi. Cần kiểm tra track_functions, thời gian stats window và version.

### 9.4. Trigger inventory

```sql
SELECT
    n.nspname AS schema_name,
    t.relname AS table_name,
    trg.tgname AS trigger_name,
    trg.tgenabled AS enabled_state,
    pg_get_triggerdef(trg.oid, true) AS definition
FROM pg_trigger AS trg
JOIN pg_class AS t
    ON t.oid = trg.tgrelid
JOIN pg_namespace AS n
    ON n.oid = t.relnamespace
WHERE NOT trg.tgisinternal
  AND n.nspname = 'app'
ORDER BY t.relname, trg.tgname;
```

Internal triggers thường phục vụ foreign keys hoặc các chức năng hệ thống. Không xóa trigger nội bộ như một object độc lập; quản lý constraint/feature sở hữu nó.

### 9.5. Dynamic SQL và dependencies không đầy đủ

Dependency catalog không thể luôn biết tên relation được ghép động thành chuỗi ở runtime. Ví dụ function tạo SQL bằng format() rồi EXECUTE có thể tham chiếu table mà catalog không lưu dependency tĩnh theo cách người quản trị mong đợi.

Vì vậy, dependency query không phải danh sách đầy đủ mọi object có thể được function sử dụng. Đọc routine bodies, application code, job definitions và runtime logs.

## 10. Sequence và quan hệ với columns

Sequence thường cấp giá trị cho serial/identity columns, nhưng cũng có thể được gọi trực tiếp bởi application hoặc function.

### 10.1. Inventory sequences

```sql
SELECT
    schemaname,
    sequencename,
    sequenceowner,
    data_type,
    start_value,
    min_value,
    max_value,
    increment_by,
    cycle,
    cache_size,
    last_value
FROM pg_sequences
WHERE schemaname NOT LIKE 'pg\_%'
  AND schemaname <> 'information_schema'
ORDER BY schemaname, sequencename;
```

last_value có thể NULL khi role không có quyền đọc sequence hoặc sequence chưa được sử dụng theo semantics của view. Cache có thể khiến giá trị đã cấp cho session chưa được phản ánh đầy đủ trong giá trị lưu trên disk. Không dùng last_value đơn lẻ để kết luận sequence unused.

### 10.2. Sequence ownership dependencies

Serial/identity sequences thường có dependency tới table column. Có thể xem bằng:

```sql
SELECT
    seq_ns.nspname AS sequence_schema,
    seq.relname AS sequence_name,
    tbl_ns.nspname AS table_schema,
    tbl.relname AS table_name,
    col.attname AS column_name,
    dep.deptype AS dependency_type
FROM pg_class AS seq
JOIN pg_namespace AS seq_ns
    ON seq_ns.oid = seq.relnamespace
JOIN pg_depend AS dep
    ON dep.classid = 'pg_class'::regclass
   AND dep.objid = seq.oid
   AND dep.refclassid = 'pg_class'::regclass
   AND dep.refobjsubid > 0
JOIN pg_class AS tbl
    ON tbl.oid = dep.refobjid
JOIN pg_namespace AS tbl_ns
    ON tbl_ns.oid = tbl.relnamespace
JOIN pg_attribute AS col
    ON col.attrelid = tbl.oid
   AND col.attnum = dep.refobjsubid
WHERE seq.relkind = 'S'
ORDER BY seq_ns.nspname, seq.relname;
```

Dependency type thường cho biết sequence được tự động sở hữu bởi column hoặc gắn nội bộ với identity column. Kiểm tra semantics đúng version khi viết automation.

### 10.3. Sequence không có ownership dependency

Một sequence không có dependency tới column vẫn có thể được gọi trực tiếp bằng nextval() trong application, function hoặc dynamic SQL. Đây chỉ là candidate cần tra cứu.

Có thể kiểm tra defaults đang tham chiếu sequence bằng dependencies của default expressions, nhưng function bodies và dynamic SQL vẫn có thể không được bao phủ đầy đủ.

### 10.4. Không reset/drop sequence dựa trên tên hoặc last_value

Sequence có thể được dùng cho ID generation, ticket numbering, distributed coordination hoặc application logic. Trước khi drop/reset:

- Xác định owner.
- Tìm defaults và identity relationships.
- Tìm nextval, currval, setval trong code/functions.
- Kiểm tra jobs và integration services.
- Đánh giá concurrency và data collision.
- Lập backup/rollback plan.

## 11. Dependency graph với pg_depend

pg_depend là catalog quan trọng để hiểu quan hệ phụ thuộc giữa objects trong một database. Một dependency record mô tả object nào phụ thuộc vào object khác.

### 11.1. Cách đọc pg_depend

Các cột quan trọng:

| Cột | Ý nghĩa |
| --- | --- |
| classid | Catalog chứa object phụ thuộc |
| objid | OID của object phụ thuộc |
| objsubid | Sub-object ID, thường là attribute number với columns |
| refclassid | Catalog chứa referenced object |
| refobjid | OID của referenced object |
| refobjsubid | Sub-object ID của referenced object |
| deptype | Loại dependency |

Dependency direction rất quan trọng: object ở phía classid/objid phụ thuộc vào object ở phía refclassid/refobjid.

Ví dụ view phụ thuộc vào table: view là dependent object, table là referenced object. Khi xem “ai phụ thuộc vào table”, lọc theo referenced object.

### 11.2. Xem objects phụ thuộc vào một table

```sql
SELECT
    pg_describe_object(
        d.classid,
        d.objid,
        d.objsubid
    ) AS dependent_object,
    d.deptype AS dependency_type,
    pg_describe_object(
        d.refclassid,
        d.refobjid,
        d.refobjsubid
    ) AS referenced_object
FROM pg_depend AS d
WHERE d.refclassid = 'pg_class'::regclass
  AND d.refobjid = 'app.orders'::regclass
ORDER BY dependent_object;
```

Kết quả có thể gồm views, rules, constraints, indexes, defaults, triggers hoặc các object phụ thuộc khác tùy quan hệ. Đọc dependency type để hiểu cách PostgreSQL xử lý khi referenced object bị drop.

### 11.3. Xem objects mà một table phụ thuộc vào

```sql
SELECT
    pg_describe_object(
        d.refclassid,
        d.refobjid,
        d.refobjsubid
    ) AS referenced_object,
    d.deptype AS dependency_type
FROM pg_depend AS d
WHERE d.classid = 'pg_class'::regclass
  AND d.objid = 'app.orders'::regclass
ORDER BY referenced_object;
```

Query này giúp xem table object có dependency tới type, tablespace hoặc object khác không. Column-level dependencies có thể được biểu diễn bằng sub-object IDs; không bỏ qua objsubid/refobjsubid khi phân tích chi tiết.

### 11.4. Dependency type

Các dependency types thường gặp trong pg_depend:

- n — normal dependency: object phụ thuộc bình thường vào referenced object; DROP RESTRICT thường chặn việc xóa referenced object khi dependent object còn tồn tại.
- a — automatic dependency: dependent object được tự động drop khi referenced object bị drop.
- i — internal dependency: object được xem là thành phần nội bộ của object khác và thường không drop độc lập.
- e — extension dependency: object là thành viên của extension.
- P/S — dependency liên quan partition primary/secondary trên các PostgreSQL versions hỗ trợ.
- x — auto-extension dependency trên các versions có biểu diễn này.

Các mã và semantics có thể thay đổi theo version. Pinned objects được PostgreSQL bảo vệ bằng cơ chế riêng và không nên được xem như một dependency type thông thường. Đối chiếu tài liệu catalog đúng major version; không viết cleanup logic dựa trên một bảng mã tự suy đoán.

### 11.5. pg_describe_object

pg_describe_object biến bộ ba catalog OID/object OID/sub-object ID thành mô tả dễ đọc:

```sql
SELECT pg_describe_object(
    'pg_class'::regclass,
    'app.orders'::regclass,
    0
);
```

Dùng function này trong báo cáo dependency để tránh phải tự ghép tên object cho mọi catalog class.

### 11.6. pg_identify_object

pg_identify_object trả về loại object, schema, name và identity phù hợp cho object address:

```sql
SELECT *
FROM pg_identify_object(
    'pg_class'::regclass,
    'app.orders'::regclass,
    0
);
```

Trên các versions hỗ trợ, pg_identify_object_as_address cũng trả về object address dưới dạng các thành phần có thể dùng trong tooling. Các helper này phù hợp để xây inventory/reporting, nhưng vẫn cần xử lý version compatibility.

### 11.7. Dependencies tới columns

Một dependency có thể trỏ tới toàn relation hoặc một column cụ thể. Nếu refobjsubid lớn hơn 0, nó thường là attribute number của column.

Tra cứu column name:

```sql
SELECT
    pg_describe_object(
        d.classid,
        d.objid,
        d.objsubid
    ) AS dependent_object,
    d.refobjsubid AS referenced_attnum,
    a.attname AS referenced_column,
    d.deptype
FROM pg_depend AS d
LEFT JOIN pg_attribute AS a
    ON a.attrelid = d.refobjid
   AND a.attnum = d.refobjsubid
WHERE d.refclassid = 'pg_class'::regclass
  AND d.refobjid = 'app.orders'::regclass
ORDER BY dependent_object, d.refobjsubid;
```

Không giả định mọi refobjsubid đều là column number trong mọi catalog class; join này phù hợp với referenced relation objects.

## 12. Shared dependencies với pg_shdepend

Một số objects được chia sẻ ở cấp cluster, chẳng hạn roles và tablespaces. Dependencies tới shared objects được quản lý trong pg_shdepend.

### 12.1. pg_shdepend dùng để làm gì?

Nó lưu các quan hệ như:

- Object được sở hữu bởi role.
- Object có ACL/grant liên quan role.
- Object có dependency tới shared object.
- Một số quan hệ shared metadata khác theo version.

### 12.2. Xem objects phụ thuộc vào role

Ví dụ inventory dependency tới role:

```sql
SELECT
    d.dbid,
    CASE
        WHEN d.dbid = 0 THEN 'shared object'
        ELSE db.datname
    END AS database_name,
    pg_describe_object(
        d.classid,
        d.objid,
        d.objsubid
    ) AS dependent_object,
    d.deptype AS dependency_type
FROM pg_shdepend AS d
LEFT JOIN pg_database AS db
    ON db.oid = d.dbid
WHERE d.refclassid = 'pg_authid'::regclass
  AND d.refobjid = (
      SELECT oid
      FROM pg_roles
      WHERE rolname = 'legacy_app'
  )
ORDER BY database_name, dependent_object;
```

Role cần tồn tại để query trả kết quả có ý nghĩa. Quyền đọc shared dependency metadata có thể bị giới hạn; thực hiện bằng administrative role phù hợp.

### 12.3. Ownership và grants là hai vấn đề khác nhau

Một role có thể không sở hữu object nhưng vẫn có quyền SELECT/EXECUTE. Ngược lại, role có thể sở hữu object nhưng không có grant riêng trong ACL.

Trước khi drop role:

- Kiểm tra object ownership.
- Kiểm tra grants/default privileges.
- Kiểm tra memberships và role inheritance.
- Kiểm tra database-level privileges.
- Kiểm tra jobs, connection strings và external secrets.
- Xác định role có phải owner của extension hoặc schema không.

### 12.4. REASSIGN OWNED và DROP OWNED

REASSIGN OWNED chuyển ownership của objects trong database hiện tại và các shared objects liên quan theo semantics của command. DROP OWNED drop objects thuộc role và revoke privileges được cấp cho role trong database hiện tại; thao tác có thể ảnh hưởng rộng.

Các lệnh này có phạm vi tác động lớn và phải được chạy theo quy trình role decommission có inventory, review và backup. Chúng không thay thế việc xác minh role có còn được application dùng hay không.

## 13. Dependencies của extensions

Extension quản lý một nhóm objects như functions, types, operators, casts và views. PostgreSQL ghi membership dependency để biết object thuộc extension nào.

### 13.1. Liệt kê extensions

```sql
SELECT
    e.oid,
    e.extname,
    e.extversion,
    n.nspname AS extension_schema,
    pg_get_userbyid(e.extowner) AS owner,
    e.extrelocatable
FROM pg_extension AS e
JOIN pg_namespace AS n
    ON n.oid = e.extnamespace
ORDER BY e.extname;
```

### 13.2. Xem objects thuộc extension

```sql
SELECT
    e.extname,
    pg_describe_object(
        d.classid,
        d.objid,
        d.objsubid
    ) AS extension_member
FROM pg_extension AS e
JOIN pg_depend AS d
    ON d.refclassid = 'pg_extension'::regclass
   AND d.refobjid = e.oid
   AND d.deptype = 'e'
ORDER BY e.extname, extension_member;
```

Không xóa thủ công từng object thuộc extension khi extension vẫn quản lý nó. Dùng DROP EXTENSION ... RESTRICT hoặc quy trình upgrade/drop chính thức.

### 13.3. Extension dependencies

Một extension có thể phụ thuộc extension khác. Kiểm tra extension dependency trước khi drop:

```sql
SELECT
    pg_describe_object(
        d.classid,
        d.objid,
        d.objsubid
    ) AS dependent_object,
    d.deptype,
    pg_describe_object(
        d.refclassid,
        d.refobjid,
        d.refobjsubid
    ) AS referenced_object
FROM pg_depend AS d
WHERE d.refclassid = 'pg_extension'::regclass
ORDER BY referenced_object, dependent_object;
```

Extension có thể được dùng bởi nhiều schemas/objects. Đánh giá ứng dụng, migrations và các databases khác trong cluster trước khi remove package hoặc server library.

## 14. Dependencies tĩnh và runtime references

Dependency catalog rất hữu ích nhưng không thể quan sát mọi cách ứng dụng sử dụng database.

### 14.1. Dependencies PostgreSQL có thể ghi nhận

Ví dụ:

- View tham chiếu table/column.
- Constraint tham chiếu table/type/index.
- Default expression tham chiếu sequence.
- Function signature tham chiếu custom type.
- Object thuộc extension.
- Object được sở hữu bởi schema/role theo dependency type tương ứng.

### 14.2. References có thể không được ghi nhận đầy đủ

Ví dụ:

- Dynamic SQL tạo table name từ input.
- Application build SQL string ở runtime.
- ORM tạo query theo feature flag.
- BI tool gửi query từ dashboard ngoài database.
- Scheduled job nằm trong hệ thống orchestration khác.
- External service gọi function theo tên.
- Code dùng search_path và unqualified object names.
- SQL được lưu trong configuration repository hoặc secrets.

### 14.3. Catalog không phải call graph của ứng dụng

PostgreSQL không thể tự xây dựng đầy đủ call graph từ mọi application code và external systems. Dùng source search, application telemetry, database logs, audit records và owner confirmation để hoàn thiện bằng chứng.

### 14.4. Một dependency tồn tại không có nghĩa object đang được gọi

Dependency là quan hệ cấu trúc. Một view có thể phụ thuộc table nhưng không được query trong nhiều tháng. Ngược lại, object không có dependency catalog có thể vẫn được external client gọi trực tiếp.

Cần tách hai câu hỏi:

1. Object có phụ thuộc cấu trúc nào?
2. Object có được dùng trong workload thực tế không?

Hai câu hỏi cần hai loại bằng chứng khác nhau.

## 15. Xác định objects không còn sử dụng

Không có một flag chung unused trong PostgreSQL catalogs. Việc xác định unused cần kết hợp statistics, logs, code search và lifecycle knowledge.

### 15.1. Evidence theo mức độ tin cậy

| Evidence | Có thể kết luận gì? | Hạn chế |
| --- | --- | --- |
| Dependency catalog | Có object phụ thuộc tĩnh | Không đầy đủ dynamic/runtime references |
| Index/table stats | Có scans được ghi nhận trong stats window | Counters có thể reset; workload theo mùa |
| pg_stat_statements | Query fingerprints đã chạy và tần suất | Không phải object-level access audit hoàn chỉnh |
| Slow/general logs | Query text trong logging window | Chỉ có những statements được cấu hình ghi |
| Application code search | Có references trong repository được tìm | Có thể thiếu dynamic SQL/config/external code |
| Scheduler/job inventory | Job có thể truy cập object | Cần bao phủ mọi scheduler |
| Owner confirmation | Xác nhận business purpose và lifecycle | Cần owner phù hợp và bằng chứng |
| Staging deprecation | Không có regression trong thử nghiệm | Không chứng minh mọi production path |

### 15.2. Chọn observation window

Window phải bao phủ chu kỳ sử dụng thực tế:

- Daily jobs: ít nhất một hoặc nhiều chu kỳ ngày.
- Weekly reports: nhiều chu kỳ tuần.
- Monthly close: cần quan sát qua monthly close.
- Quarterly/year-end processing: cần kiểm tra lịch và owner, không thể kết luận từ một tuần statistics.
- Disaster recovery/rare maintenance: kiểm tra runbook và operational dependency.

Không có thời gian mặc định phù hợp cho mọi hệ thống. Dùng business calendar và RTO/RPO requirements.

### 15.3. Statistics reset và restart

Nếu counters mới reset, object có thể chưa có cơ hội được dùng trong observation window. Ghi lại stats_reset, restart/deploy timeline và thời gian collector hoạt động trước khi phân loại candidate.

### 15.4. Object được ghi nhưng không đọc

Table có thể là:

- Audit log.
- Outbox queue.
- Event inbox.
- Staging/import table.
- Retention archive.
- Materialized state cho downstream export.
- Buffer cho scheduled job.

Zero read scans không chứng minh table có thể xóa. Kiểm tra write path, cleanup policy, retention và external consumers.

### 15.5. Objects được gọi gián tiếp

Function có thể gọi table qua dynamic SQL; view có thể được query bởi report khác; trigger có thể chạy khi DML xảy ra. Kiểm tra trigger, rules, routines, dependencies và code paths.

## 16. Dùng pg_stat_statements làm bằng chứng workload

pg_stat_statements tổng hợp query execution theo normalized query. Nó có thể giúp tìm query references tới tables/functions nhưng không thay thế audit log.

### 16.1. Xem query fingerprints

Nếu extension đã được preload và tạo trong database:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    left(query, 1000) AS query_sample
FROM pg_stat_statements
ORDER BY calls DESC
LIMIT 100;
```

Query text có thể bị chuẩn hóa và không chứa literal values. Với dynamic SQL, query text có thể phản ánh câu lệnh đã được tạo nhưng vẫn cần ghép với caller.

### 16.2. Tìm references tới tên object

Ví dụ tìm các query text có nhắc tới một relation:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    left(query, 1000) AS query_sample
FROM pg_stat_statements
WHERE query ILIKE '%app.orders%'
ORDER BY calls DESC;
```

Đây là tìm kiếm text đơn giản. Nó có thể bỏ sót unqualified names, quoted identifiers, aliases, prepared statements hoặc query được xây dựng động. Nó cũng có thể match nhầm comment/string literal.

### 16.3. pg_stat_statements có thể reset/evict entries

Entries có thể bị reset hoặc bị thay thế khi giới hạn pg_stat_statements.max bị áp lực. Lưu snapshot định kỳ nếu cần lịch sử dài hạn.

### 16.4. Không dùng queryid làm identifier xuyên version

Query ID có thể phụ thuộc PostgreSQL version, parse tree và object identities. Lưu server version, database, schema context và query text đã chuẩn hóa khi cần so sánh lâu dài.

## 17. Phân loại unused candidates theo object type

Mỗi loại object có cách sử dụng và bằng chứng khác nhau.

### 17.1. Indexes

Bằng chứng:

- idx_scan thấp/0 trong window đủ dài.
- Không backing constraint.
- Không phải primary key/replica identity.
- Không được dùng bởi rare reporting jobs.
- Không được yêu cầu bởi query plans trong workload đại diện.

Rủi ro:

- Unique index có thể bảo đảm business invariant.
- Index có thể hỗ trợ foreign-key delete/update checks hoặc query hiếm.
- Index trên partitioned tables có quan hệ với child indexes.
- Index usage có thể thay đổi sau data growth hoặc query plan change.

### 17.2. Tables

Bằng chứng:

- Không có scans trong nhiều business cycles.
- Không có writes hoặc rows.
- Không có static dependencies.
- Không có application/job references.
- Owner xác nhận đã deprecate.

Rủi ro:

- Audit/retention.
- Outbox/inbox.
- Staging.
- External reporting.
- Seasonal jobs.
- Restore/DR procedures.

### 17.3. Views

Bằng chứng:

- Không tìm thấy query references trong logs/traces.
- Không có view nào khác phụ thuộc.
- Không được application/BI dùng.
- Owner xác nhận deprecated.

Rủi ro:

- Catalog không cung cấp direct view usage counter.
- View có thể là compatibility API.
- Dynamic SQL có thể gọi view.
- Security-barrier/security-invoker semantics có thể quan trọng.

### 17.4. Materialized views

Bằng chứng:

- Không có consumer.
- Refresh job không còn chạy.
- Không có downstream export.
- Data freshness không còn được yêu cầu.

Rủi ro:

- Dashboard chỉ mở theo tháng/quý.
- Refresh schedule có thể ở external scheduler.
- Materialized view có thể là cache quan trọng để giảm workload.

### 17.5. Functions/procedures

Bằng chứng:

- Function statistics không có calls trong window nếu tracking bật.
- Không có dependencies tĩnh.
- Không có application/job references.
- Không được trigger/rule gọi.

Rủi ro:

- Function được gọi từ external SQL.
- Function được gọi bởi dynamic SQL hoặc string-based RPC.
- Function có thể được migration/maintenance gọi hiếm.
- track_functions có thể tắt.

### 17.6. Sequences

Bằng chứng:

- Không có column ownership.
- Không có default expression dependency.
- Không có code reference tới nextval/currval/setval.
- Không có integration/job references.

Rủi ro:

- Sequence được gọi trực tiếp.
- Cache và last_value không phản ánh đầy đủ mọi lần cấp giá trị.
- Sequence có thể là counter nghiệp vụ.

### 17.7. Schemas, types và extensions

Schema rỗng về relations vẫn có thể chứa routines/types. Type có thể được dùng trong function signatures hoặc application contracts. Extension có thể cung cấp functions/types được nhiều objects khác dùng.

Audit toàn bộ object classes trước khi đánh giá schema/extension unused.

## 18. Tìm sequence candidates không gắn với column

Query dưới đây liệt kê sequences không có ownership dependency tới table column. Kết quả là candidate để kiểm tra:

```sql
SELECT
    n.nspname AS schema_name,
    s.relname AS sequence_name,
    pg_get_userbyid(s.relowner) AS owner
FROM pg_class AS s
JOIN pg_namespace AS n
    ON n.oid = s.relnamespace
WHERE s.relkind = 'S'
  AND n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
  AND NOT EXISTS (
      SELECT 1
      FROM pg_depend AS d
      WHERE d.classid = 'pg_class'::regclass
        AND d.objid = s.oid
        AND d.refclassid = 'pg_class'::regclass
        AND d.refobjsubid > 0
        AND d.deptype IN ('a', 'i')
  )
ORDER BY n.nspname, s.relname;
```

Sequence standalone có thể là thiết kế hợp lệ. Query này chỉ phát hiện thiếu ownership dependency, không chứng minh sequence không được gọi.

## 19. Tìm schemas có vẻ trống

Có thể liệt kê schemas không có relations:

```sql
SELECT
    n.nspname AS schema_name,
    pg_get_userbyid(n.nspowner) AS owner
FROM pg_namespace AS n
WHERE n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
  AND NOT EXISTS (
      SELECT 1
      FROM pg_class AS c
      WHERE c.relnamespace = n.oid
  )
ORDER BY n.nspname;
```

Kết quả chỉ có nghĩa schema không có entries trong pg_class. Nó có thể vẫn chứa routines, types, operators, collations hoặc other objects. Trước khi drop schema, inventory thêm catalogs phù hợp và kiểm tra dependencies.

## 20. Tìm object ownership và owner cũ

Object owner là người có quyền quản trị object, nhưng role đó có thể đã rời tổ chức hoặc không còn được sử dụng.

### 20.1. Relation owners

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind,
    pg_get_userbyid(c.relowner) AS owner
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
ORDER BY owner, n.nspname, c.relname;
```

### 20.2. Schema owners

```sql
SELECT
    n.nspname AS schema_name,
    pg_get_userbyid(n.nspowner) AS owner
FROM pg_namespace AS n
WHERE n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
ORDER BY owner, schema_name;
```

### 20.3. Role inventory

```sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper,
    rolcreatedb,
    rolcreaterole,
    rolreplication,
    rolconnlimit,
    rolvaliduntil
FROM pg_roles
ORDER BY rolname;
```

Role có LOGIN false vẫn có thể là group role dùng cho grants. Không xóa role chỉ vì nó không đăng nhập trực tiếp.

### 20.4. Default privileges

```sql
SELECT
    defaclrole::regrole AS creator_role,
    defaclnamespace::regnamespace AS schema_name,
    defaclobjtype AS object_type,
    defaclacl
FROM pg_default_acl
ORDER BY creator_role, schema_name, object_type;
```

Khi decommission role, kiểm tra default ACL để tránh grants cũ tiếp tục được áp dụng hoặc role còn là creator role cho objects mới.

## 21. Kiểm tra privileges và ACL

Object có thể được sử dụng bởi role khác owner. Dependency/ownership inventory phải đi cùng grants.

### 21.1. Table privileges

```sql
SELECT
    table_schema,
    table_name,
    grantee,
    privilege_type,
    is_grantable
FROM information_schema.role_table_grants
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, grantee, privilege_type;
```

View này phản ánh grants theo visibility rules của information schema. Với audit sâu, cần xem ACL catalog và default privileges.

### 21.2. Function privileges

```sql
SELECT
    routine_schema,
    routine_name,
    grantee,
    privilege_type,
    is_grantable
FROM information_schema.routine_privileges
WHERE routine_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY routine_schema, routine_name, grantee;
```

Function overloads có thể cùng tên. Dùng identity arguments khi cần phân biệt signature.

### 21.3. PUBLIC privileges

Quyền cấp cho role PUBLIC áp dụng rộng cho mọi roles. Kiểm tra default privileges và object ACL khi database có security requirements nghiêm ngặt.

### 21.4. Không sửa ACL trực tiếp trong catalogs

Dùng GRANT/REVOKE, ALTER DEFAULT PRIVILEGES và object ownership commands. Không UPDATE system catalog rows bằng SQL để thay ACL hoặc owner.

## 22. DROP RESTRICT và DROP CASCADE

PostgreSQL hỗ trợ dependency-aware DDL. Hiểu rõ khác biệt là yêu cầu bắt buộc trước khi cleanup.

### 22.1. RESTRICT

RESTRICT từ chối drop nếu có dependent objects cần được giữ. Đây là behavior mặc định của nhiều DROP commands.

Ví dụ:

```sql
DROP TABLE app.orders RESTRICT;
```

Nếu view hoặc object khác phụ thuộc vào table, PostgreSQL sẽ báo lỗi và liệt kê dependency. Dùng RESTRICT trong cleanup workflow để ngăn xóa dây chuyền ngoài dự kiến.

### 22.2. CASCADE

CASCADE cho phép drop object cùng các objects phụ thuộc theo dependency rules:

```sql
DROP TABLE app.orders CASCADE;
```

Lệnh có thể drop views, rules, constraints hoặc objects khác tùy dependency graph. Một lệnh CASCADE có thể gây ảnh hưởng rộng hơn dự kiến. Không dùng CASCADE như cách “dọn cho sạch” khi chưa đọc danh sách dependent objects.

### 22.3. CASCADE không phát hiện mọi runtime reference

Nếu application gọi table qua dynamic SQL, external BI hoặc job scheduler, PostgreSQL có thể không biết dependency đó. CASCADE không thể cảnh báo đầy đủ những callers nằm ngoài catalog graph.

### 22.4. Dry-run bằng transaction trong môi trường kiểm thử

Với DDL transactional, có thể thử thao tác trong transaction rồi rollback ở lab/staging:

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';

DROP VIEW reporting.orders_summary RESTRICT;

ROLLBACK;
```

Cần hiểu lock và event-trigger side effects. Transaction rollback không làm cho mọi external side effects của extension/event trigger trở nên vô hại. Không chạy thử destructive DDL trên production chỉ vì định rollback.

### 22.5. DROP IF EXISTS không phải safety check

DROP ... IF EXISTS chỉ tránh lỗi khi object không tồn tại. Nó không xác nhận object có thể xóa an toàn và không ngăn mất dữ liệu.

## 23. Quy trình deprecation trước khi drop

Đối tượng có thể đã lỗi thời nhưng vẫn cần một giai đoạn deprecation có kiểm soát.

### 23.1. Inventory

Ghi lại:

- Object type, schema, name và owner.
- OID/identity tại thời điểm audit.
- Size và dependencies.
- Constraints/indexes liên quan.
- Extension membership.
- Grants và callers đã biết.
- Statistics reset time và observation window.

### 23.2. Xác định owner

Mỗi object candidate cần owner kỹ thuật và owner nghiệp vụ. Owner phải xác nhận purpose, consumer, retention và deprecation timeline.

### 23.3. Tìm references ngoài catalog

Search application repositories, migration files, ORM mappings, SQL templates, dashboard/report definitions, scheduled jobs và integration configurations.

### 23.4. Thông báo deprecation

Tạo migration/change request có:

- Object sẽ deprecate.
- Consumer/owner cần xác nhận.
- Thời gian ngừng sử dụng.
- Cách rollback.
- Metrics/logs cần theo dõi.
- Người phê duyệt.

### 23.5. Ngừng callers trước

Deploy code ngừng gọi object, disable job hoặc chuyển consumer sang object thay thế. Theo dõi lỗi và logs qua một observation window phù hợp.

### 23.6. Drop với RESTRICT

Sau khi dependencies và runtime references đã được xử lý, drop object bằng RESTRICT. Nếu lệnh báo dependency, quay lại inventory để hiểu object nào còn liên quan.

### 23.7. Post-change verification

Sau drop:

- Xác nhận migration hoàn tất.
- Kiểm tra application errors và scheduled jobs.
- Kiểm tra dependent views/functions còn hoạt động.
- Theo dõi database logs và metrics.
- Cập nhật inventory/ownership registry.
- Giữ rollback/restore path theo policy.

## 24. Kiểm tra partitioning và inheritance dependencies

Partitioned tables tạo nhiều quan hệ giữa parent và child relations. Cleanup một partition cần hiểu dữ liệu và indexes liên quan.

### 24.1. Liệt kê inheritance/partition relationships

```sql
SELECT
    parent_ns.nspname AS parent_schema,
    parent.relname AS parent_table,
    child_ns.nspname AS child_schema,
    child.relname AS child_table,
    inh.inhseqno,
    inh.inhdetachpending
FROM pg_inherits AS inh
JOIN pg_class AS parent
    ON parent.oid = inh.inhparent
JOIN pg_namespace AS parent_ns
    ON parent_ns.oid = parent.relnamespace
JOIN pg_class AS child
    ON child.oid = inh.inhrelid
JOIN pg_namespace AS child_ns
    ON child_ns.oid = child.relnamespace
ORDER BY parent_ns.nspname, parent.relname, inh.inhseqno;
```

Một số columns như inhdetachpending có thể không có trên versions cũ. Nếu query cần chạy đa phiên bản, kiểm tra catalog schema trước.

### 24.2. Partition không có traffic

Một partition cũ có thể không nhận inserts nữa nhưng vẫn lưu historical data phục vụ reporting, compliance hoặc query range scans. Không đánh giá unused chỉ theo write activity.

### 24.3. Detach và drop

DETACH PARTITION và DROP TABLE có semantics/locking khác nhau tùy version và options. Kiểm tra foreign keys, partitioned indexes, constraints, retention requirements và concurrent operations trước khi detach/drop.

### 24.4. Partitioned index

Parent partitioned index có child indexes. Kiểm tra trạng thái và definitions trên toàn hierarchy trước khi remove index hoặc partition.

## 25. Kiểm tra object descriptions và comments

Comments giúp duy trì owner/purpose trong catalog.

### 25.1. Relation comments

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    col_description(c.oid, 0) AS relation_comment
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'app'
ORDER BY c.relname;
```

### 25.2. Column comments

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    a.attname AS column_name,
    col_description(c.oid, a.attnum) AS column_comment
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
JOIN pg_attribute AS a
    ON a.attrelid = c.oid
WHERE n.nspname = 'app'
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY c.relname, a.attnum;
```

### 25.3. Comment như metadata quản trị

Có thể chuẩn hóa comment format để ghi owner team, purpose, data classification, retention và ticket/reference. Không đặt secrets hoặc dữ liệu cá nhân vào comments; catalog có thể được đọc bởi nhiều roles.

## 26. Schema drift giữa environments

Development, staging và production có thể lệch nhau sau các lần migration hoặc hotfix.

### 26.1. So sánh bằng object identity

Không so OIDs giữa environments. So sánh:

- Schema name.
- Object name/type.
- Column order/name/type/nullability/default.
- Constraint definitions.
- Index definitions/validity.
- View/function definitions.
- Ownership và privileges.
- Extension names/versions.
- Partition hierarchy.
- Comments/metadata.

### 26.2. Dùng migration history

Catalog snapshot cho biết trạng thái hiện tại; migration history cho biết các bước dự kiến tạo trạng thái đó. Kiểm tra cả hai để tìm hotfix không được ghi vào migration repository hoặc migration chạy thiếu.

### 26.3. Drift report

Một report hữu ích chia thành:

- Missing object.
- Unexpected object.
- Definition mismatch.
- Owner/ACL mismatch.
- Extension version mismatch.
- Invalid/unvalidated object state.
- Dependency mismatch.

### 26.4. Không tự đồng bộ bằng cách copy catalog rows

Catalogs là internal implementation. Dùng DDL/migration scripts hoặc schema management tools. Không copy/update system catalog rows trực tiếp giữa databases.

## 27. Audit queries tổng hợp

Có thể lưu các query sau thành script audit read-only và chạy định kỳ với role có quyền phù hợp.

### 27.1. Object inventory cơ bản

```sql
SELECT
    current_database() AS database_name,
    n.nspname AS schema_name,
    c.relname AS object_name,
    c.relkind AS relation_kind,
    pg_get_userbyid(c.relowner) AS owner,
    pg_total_relation_size(c.oid) AS total_bytes
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname NOT LIKE 'pg\_%' ESCAPE '\'
  AND n.nspname <> 'information_schema'
  AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
ORDER BY n.nspname, c.relname;
```

### 27.2. Dependencies của một relation

```sql
SELECT
    pg_describe_object(
        d.classid,
        d.objid,
        d.objsubid
    ) AS dependent_object,
    d.deptype,
    pg_describe_object(
        d.refclassid,
        d.refobjid,
        d.refobjsubid
    ) AS referenced_object
FROM pg_depend AS d
WHERE d.refclassid = 'pg_class'::regclass
  AND d.refobjid = to_regclass('app.orders')
ORDER BY dependent_object;
```

Nếu to_regclass trả NULL, query không tìm thấy referenced object. Kiểm tra tên và schema trước khi diễn giải kết quả rỗng.

### 27.3. Unused index candidates

```sql
SELECT
    s.schemaname,
    s.relname AS table_name,
    s.indexrelname AS index_name,
    s.idx_scan,
    i.indisprimary,
    i.indisunique,
    i.indisreplident,
    EXISTS (
        SELECT 1
        FROM pg_constraint AS con
        WHERE con.conindid = i.indexrelid
    ) AS backs_constraint,
    pg_size_pretty(pg_relation_size(i.indexrelid)) AS index_size
FROM pg_stat_user_indexes AS s
JOIN pg_index AS i
    ON i.indexrelid = s.indexrelid
WHERE s.idx_scan = 0
ORDER BY pg_relation_size(i.indexrelid) DESC;
```

### 27.4. Tables không có scans trong stats window

```sql
SELECT
    schemaname,
    relname,
    seq_scan,
    idx_scan,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_live_tup
FROM pg_stat_user_tables
WHERE COALESCE(seq_scan, 0) = 0
  AND COALESCE(idx_scan, 0) = 0
ORDER BY n_live_tup DESC;
```

### 27.5. Invalid indexes và unvalidated constraints

```sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisvalid,
    i.indisready
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
JOIN pg_class AS tbl ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
WHERE NOT i.indisvalid OR NOT i.indisready
ORDER BY ns.nspname, tbl.relname, idx.relname;
```

```sql
SELECT
    ns.nspname,
    tbl.relname,
    con.conname,
    pg_get_constraintdef(con.oid, true) AS definition
FROM pg_constraint AS con
JOIN pg_class AS tbl ON tbl.oid = con.conrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
WHERE NOT con.convalidated
ORDER BY ns.nspname, tbl.relname, con.conname;
```

## 28. Automation cho catalog audit

Audit định kỳ giúp phát hiện drift và object candidates sớm hơn một lần cleanup lớn.

### 28.1. Chạy read-only

Role audit chỉ cần quyền đọc metadata/statistics cần thiết. Không cấp quyền DROP/ALTER cho job inventory.

### 28.2. Snapshot theo thời điểm

Lưu kết quả inventory cùng:

- Database identity/environment.
- PostgreSQL version.
- Timestamp.
- Migration version.
- Statistics reset timestamp.
- Query/script version.
- Role thực hiện audit.

Không lưu OID như identity xuyên environments; có thể giữ OID như diagnostic field trong snapshot cùng database identity.

### 28.3. Diff snapshots

So sánh snapshot hiện tại với snapshot trước để tìm:

- Object mới.
- Object bị xóa.
- Owner changes.
- Definition/ACL changes.
- Extension upgrades.
- Index validity changes.
- Dependency graph changes.
- Table/index size growth.

### 28.4. Không tự động drop theo report

Automation có thể gắn nhãn candidate, tạo ticket hoặc gửi báo cáo cho owner. Destructive DDL cần review và xác nhận theo lifecycle. Một job không nên xóa index/table chỉ vì counter bằng zero.

### 28.5. Catalog query cost

Catalog queries thường nhẹ hơn full table scans nhưng inventory toàn cluster/database lớn vẫn có thể tốn CPU, memory và thời gian. Tránh quét quá thường xuyên các definitions lớn hoặc gọi pg_total_relation_size cho mọi object trong từng scrape vài giây. Tách inventory định kỳ khỏi runtime metrics có tần suất cao.

## 29. Bảo mật khi audit catalogs

Catalogs có thể tiết lộ schema, role names, function definitions, ownership và security configuration.

### 29.1. Least privilege

Dùng role audit chuyên dụng chỉ có quyền đọc metadata cần thiết. Với các views chứa thông tin session khác, cần quyền monitoring phù hợp theo version.

### 29.2. Security definer routines

Khi inventory routines, đánh dấu prosecdef để nhận diện SECURITY DEFINER functions. Kiểm tra owner, search_path và execute grants. Một function security-definer có thể nâng quyền caller; không drop hoặc alter mà chưa đánh giá security contract.

### 29.3. Search path

Routines và application sessions có thể dùng search_path. Object name không schema-qualified có thể resolve tới object khác nếu search_path thay đổi. Kiểm tra routine definitions, role/database defaults và proconfig khi audit behavior.

### 29.4. Không xuất metadata nhạy cảm rộng rãi

Function body, grants, role names và schema layout có thể là thông tin nội bộ. Giới hạn quyền đọc audit reports và áp dụng retention/access controls.

## 30. Các lỗi thường gặp khi đọc catalogs

| Triệu chứng/giả định | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Table không có trong information_schema | Role không đủ visibility hoặc object type khác | Kiểm tra quyền và pg_catalog |
| Không thấy dependency | Runtime/dynamic SQL không được ghi nhận | Search code, logs, jobs và external callers |
| idx_scan = 0 nghĩa là unused | Stats window ngắn/reset hoặc workload hiếm | Quan sát qua business cycles và kiểm tra constraints |
| Table không có scans thì drop được | Có thể là audit/outbox/staging hoặc external consumer | Kiểm tra writes, owner, retention và jobs |
| Sequence last_value NULL nghĩa là unused | Có thể thiếu quyền hoặc chưa flush cache state | Kiểm tra ownership, defaults, code và permissions |
| View không có usage stats | PostgreSQL không có counter trực tiếp cho mọi view | Dùng logs, query stats và dependencies |
| Function calls = 0 nghĩa là dead code | track_functions có thể tắt; caller có thể external | Kiểm tra setting, code và runtime logs |
| DROP CASCADE chỉ xóa một object | Có thể xóa cả dependency tree | Inventory dependents, dùng RESTRICT |
| Schema không có tables là empty | Có thể có routines/types/operators | Inventory toàn bộ object classes |
| Role không LOGIN là unused | Có thể là group role/owner | Kiểm tra memberships, ownership và ACL |
| OID giống nhau ở hai môi trường | OID không phải stable cross-environment ID | So schema-qualified identity và definitions |
| Catalog columns giống mọi version | Catalogs thay đổi theo major version | Kiểm tra server_version và catalog schema |
| Extension object có thể drop riêng | Object thuộc extension lifecycle | Quản lý bằng extension commands |
| Statistics là audit log | Statistics chỉ là aggregate counters | Dùng audit/logging nếu cần lịch sử caller |

## 31. Quy trình audit và cleanup end-to-end

**Bước 1 — Xác định scope.** Chọn database, schemas, object types và mục tiêu audit: inventory, drift, security hay unused candidates.

**Bước 2 — Ghi baseline.** Lưu PostgreSQL version, database identity, migration version và statistics reset timestamps.

**Bước 3 — Lập inventory.** Thu schemas, relations, columns, constraints, indexes, routines, sequences, extensions, owners và ACL.

**Bước 4 — Xây dependency graph.** Dùng pg_depend/pg_shdepend và helper functions để liệt kê dependent objects, extension membership và role dependencies.

**Bước 5 — Phân tích runtime evidence.** Đọc table/index/function stats, pg_stat_statements, logs, tracing và scheduler inventory.

**Bước 6 — Xác minh với owners.** Xác nhận business purpose, seasonal usage, retention, external integrations và deprecation timeline.

**Bước 7 — Phân loại risk.** Gắn nhãn keep, investigate, deprecate hoặc approved-for-removal. Ghi evidence và confidence.

**Bước 8 — Deprecate callers.** Deploy application/job changes và theo dõi qua observation window phù hợp.

**Bước 9 — Kiểm tra dependencies lại.** Chạy inventory ngay trước DDL để phát hiện object được tạo/tham chiếu mới.

**Bước 10 — Drop với RESTRICT.** Dùng explicit schema-qualified names và lock timeout hợp lý. Nếu có dependency, dừng và review.

**Bước 11 — Verify sau cleanup.** Kiểm tra application errors, jobs, reports, catalog state và database metrics.

**Bước 12 — Cập nhật registry.** Lưu DDL/migration, owner, audit result và rollback/restore information.

## 32. Bài thực hành

Thực hiện trên PostgreSQL lab riêng. Không drop objects, revoke roles hoặc chạy CASCADE trên production chỉ để thử.

### Bài 1 — Information schema

Liệt kê schemas, tables và columns bằng information_schema. So sánh visibility khi dùng hai roles có privileges khác nhau.

### Bài 2 — pg_class inventory

Dùng pg_class/pg_namespace liệt kê tables, indexes, sequences, views và materialized views. Phân biệt relkind.

### Bài 3 — OID và regclass

Lấy OID của một relation bằng pg_class và to_regclass. Giải thích vì sao OID không phải identifier ổn định giữa environments.

### Bài 4 — Column metadata

Dùng pg_attribute/pg_attrdef liệt kê type, nullability, identity, generated columns và defaults.

### Bài 5 — Constraints inventory

Liệt kê primary, unique, foreign-key, check và exclusion constraints bằng pg_constraint.

### Bài 6 — Foreign-key graph

Tạo hai tables có FK. Dùng pg_constraint để hiển thị child/parent relationships và constraint definitions.

### Bài 7 — Unvalidated constraint

Tạo constraint NOT VALID trong lab. Xem convalidated và tìm hiểu khi nào cần VALIDATE CONSTRAINT.

### Bài 8 — Index inventory

Dùng pg_index và pg_class lấy definitions, size, unique/primary/replica identity flags.

### Bài 9 — Invalid index

Mô phỏng failed concurrent index build trong môi trường lab nếu có thể. Tìm index invalid/not ready và xác định cách xử lý an toàn.

### Bài 10 — Constraint-backed index

Join pg_constraint.conindid với pg_index. Chứng minh vì sao index hỗ trợ PK/unique không được đánh dấu unused chỉ từ idx_scan.

### Bài 11 — Index scan statistics

Tạo workload dùng index và workload không dùng index. So idx_scan trước/sau và ghi lại stats reset time.

### Bài 12 — Zero-scan index candidate

Tạo một index ít dùng trong lab. Tạo report idx_scan = 0 và viết danh sách kiểm tra trước khi đề xuất drop.

### Bài 13 — Table scan statistics

Tạo table có SELECT/INSERT/UPDATE/DELETE. Quan sát pg_stat_user_tables counters.

### Bài 14 — Stats reset

Reset statistics trong lab nếu có quyền. Quan sát counters và giải thích vì sao zero scan sau reset không chứng minh unused.

### Bài 15 — View dependencies

Tạo view trên table. Dùng pg_depend và pg_describe_object tìm view phụ thuộc vào table.

### Bài 16 — Nested views

Tạo view phụ thuộc view khác. Xây dependency report và xác định thứ tự deprecation.

### Bài 17 — Materialized view

Tạo materialized view, refresh và kiểm tra pg_matviews. Viết inventory gồm owner, populated state và refresh consumer.

### Bài 18 — Function inventory

Tạo overloaded functions cùng tên nhưng khác arguments. Dùng pg_get_function_identity_arguments để phân biệt.

### Bài 19 — Function statistics

Bật track_functions trong lab nếu cần restart, gọi functions và quan sát pg_stat_user_functions. Tắt tracking và ghi nhận giới hạn.

### Bài 20 — Dynamic SQL

Tạo function dùng EXECUTE để truy vấn table theo tên động. So dependency catalog với references trong function body.

### Bài 21 — Trigger inventory

Tạo trigger và function trigger. Liệt kê bằng pg_trigger, phân biệt user triggers và internal triggers.

### Bài 22 — Sequence ownership

Tạo serial/identity column và sequence standalone. Dùng pg_depend tìm sequence-column ownership relationships.

### Bài 23 — Sequence usage

Gọi nextval trong lab, quan sát pg_sequences.last_value và giải thích giới hạn do permissions/cache.

### Bài 24 — Extension membership

Cài một extension có sẵn trong lab. Dùng pg_extension và pg_depend liệt kê members. Thử DROP EXTENSION RESTRICT trong database test.

### Bài 25 — Role ownership

Tạo role owner và một số objects. Dùng pg_shdepend để inventory dependencies tới role.

### Bài 26 — ACL inventory

Tạo GRANT/REVOKE trên tables và functions. So information_schema grants với catalog ACL/default privileges.

### Bài 27 — Schema không có relations

Tạo schema chỉ chứa function/type. Chạy query tìm schema không có pg_class relations và giải thích vì sao không thể drop ngay.

### Bài 28 — Partition dependencies

Tạo partitioned table, partitions và indexes. Dùng pg_inherits/pg_depend để inventory hierarchy.

### Bài 29 — Object descriptions

Dùng pg_describe_object, pg_identify_object và regclass để tạo report dễ đọc cho một dependency graph.

### Bài 30 — RESTRICT và CASCADE

Trong lab, tạo table/view dependency. Thử DROP TABLE RESTRICT và CASCADE trong database có thể rollback; ghi lại objects bị ảnh hưởng.

### Bài 31 — Unused candidate assessment

Tạo table/index/function có usage khác nhau. Kết hợp stats, dependencies và code search để phân loại keep/investigate/deprecate.

### Bài 32 — Seasonal workload

Thiết kế observation window cho một report chạy theo tháng/quý. Giải thích vì sao một tuần idx_scan = 0 không đủ để drop index.

### Bài 33 — Schema drift

Tạo hai databases lab có schema definitions khác nhau. So names, columns, constraints, indexes, owner và extension versions mà không so OIDs.

### Bài 34 — Catalog audit snapshot

Viết read-only script export object inventory và dependencies kèm server version, timestamp và stats reset time. Lưu snapshot và tạo diff lần chạy kế tiếp.

### Bài 35 — Cleanup runbook

Chọn một object lab làm unused candidate. Viết deprecation record, xác minh callers/dependencies, dùng RESTRICT, kiểm tra sau drop và ghi rollback path.

## 33. Tổng kết

Những điểm cốt lõi khi **kiểm tra catalog, phụ thuộc và đối tượng không còn sử dụng**:

1. Information schema cung cấp metadata chuẩn hóa; pg_catalog cung cấp chi tiết PostgreSQL.
2. pg_class, pg_namespace, pg_attribute, pg_type, pg_proc, pg_constraint và pg_index là nền tảng inventory.
3. OID hữu ích để join catalogs trong một database nhưng không ổn định xuyên environments hoặc object recreation.
4. pg_depend mô tả dependencies trong database; pg_shdepend mô tả dependencies tới shared objects như roles.
5. pg_describe_object và pg_identify_object giúp tạo dependency reports dễ đọc.
6. Dependency graph cho biết quan hệ cấu trúc, không phải call graph đầy đủ của application.
7. Index scan counters và table statistics chỉ có ý nghĩa trong observation window đã biết.
8. Index backing constraints, replica identity, seasonal indexes và audit/outbox tables cần được bảo vệ khỏi kết luận unused đơn giản.
9. Function/view/sequence usage có thể không có counters đầy đủ; dynamic SQL và external callers cần kiểm tra riêng.
10. Extension objects phải được quản lý theo extension lifecycle.
11. Ownership, ACL, default privileges và role memberships đều cần được xem xét khi decommission role.
12. DROP RESTRICT giúp phát hiện dependencies catalog; DROP CASCADE có thể xóa cả dependency tree.
13. Deprecation cần owner confirmation, code/job search, observation window và rollback plan.
14. Catalog audit nên được snapshot/diff định kỳ nhưng không tự động drop objects.
15. Cleanup an toàn dựa trên nhiều bằng chứng và thay đổi có kiểm soát.

Catalog cho biết PostgreSQL đang quản lý những object nào và chúng liên kết ra sao. Statistics và logs cho thấy một phần hoạt động đã quan sát được. Khi kết hợp các nguồn này với application code, job inventory và xác nhận từ owner, quản trị viên có thể tìm object candidates có cơ sở, giảm schema drift và dọn dẹp database mà vẫn bảo vệ các dependencies quan trọng.

## 34. Tài liệu PostgreSQL chính thức

- [System Catalogs](https://www.postgresql.org/docs/current/catalogs.html)
- [The Information Schema](https://www.postgresql.org/docs/current/information-schema.html)
- [pg_class](https://www.postgresql.org/docs/current/catalog-pg-class.html)
- [pg_namespace](https://www.postgresql.org/docs/current/catalog-pg-namespace.html)
- [pg_attribute](https://www.postgresql.org/docs/current/catalog-pg-attribute.html)
- [pg_depend](https://www.postgresql.org/docs/current/catalog-pg-depend.html)
- [pg_shdepend](https://www.postgresql.org/docs/current/catalog-pg-shdepend.html)
- [pg_constraint](https://www.postgresql.org/docs/current/catalog-pg-constraint.html)
- [pg_index](https://www.postgresql.org/docs/current/catalog-pg-index.html)
- [pg_proc](https://www.postgresql.org/docs/current/catalog-pg-proc.html)
- [pg_extension](https://www.postgresql.org/docs/current/catalog-pg-extension.html)
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html)
- [Statistics Views](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-STATS-VIEWS)
- [Object Information Functions](https://www.postgresql.org/docs/current/functions-info.html)
- [Dependency Tracking](https://www.postgresql.org/docs/current/ddl-depend.html)
- [DROP TABLE](https://www.postgresql.org/docs/current/sql-droptable.html)
- [DROP OWNED](https://www.postgresql.org/docs/current/sql-drop-owned.html)
- [REASSIGN OWNED](https://www.postgresql.org/docs/current/sql-reassign-owned.html)
- [Privileges](https://www.postgresql.org/docs/current/ddl-priv.html)
- [Extensions](https://www.postgresql.org/docs/current/extend-extensions.html)

Các liên kết current trỏ tới tài liệu PostgreSQL hiện hành. Catalog columns, dependency codes, statistics fields, partition metadata và predefined roles có thể thay đổi theo major version. Trước khi chạy audit automation, kiểm tra SHOW server_version, catalog definitions và quyền của audit role trên đúng môi trường.
