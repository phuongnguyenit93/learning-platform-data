# Đổi tên, xóa cột và quản lý phụ thuộc view hoặc hàm trong PostgreSQL

## 1. Vì sao đổi tên hoặc xóa cột cần được quản lý cẩn thận?

Trong PostgreSQL, một cột có thể được sử dụng bởi nhiều thành phần ngoài table chứa nó: view, materialized view, function, trigger, index, constraint, generated column, policy, application query, report và ETL job. Một thay đổi đơn giản như đổi tên hoặc xóa cột có thể làm hỏng những thành phần này nếu rollout không được phối hợp.

Hai lệnh thường dùng là:

~~~sql
ALTER TABLE app.customers
RENAME COLUMN full_name TO display_name;

ALTER TABLE app.customers
DROP COLUMN legacy_code;
~~~

Đổi tên cột thay đổi tên mà client dùng để tham chiếu. Xóa cột loại bỏ khả năng truy cập cột đó trong table definition và có thể làm mất các object phụ thuộc. PostgreSQL có dependency tracking trong system catalogs, nhưng không phải mọi tham chiếu nằm trong source code, dynamic SQL hoặc function body dạng chuỗi đều được theo dõi đầy đủ.

Vì vậy, quy trình an toàn phải làm rõ:
- Cột đang được dùng ở đâu?
- PostgreSQL có ghi nhận dependency của object đó không?
- View có tiếp tục hoạt động sau khi base column đổi tên không?
- Function body có được parse và dependency được ghi nhận lúc tạo không?
- DROP COLUMN RESTRICT có phát hiện mọi consumer không?
- CASCADE sẽ xóa thêm những objects nào?
- Ứng dụng cũ và mới có thể cùng hoạt động trong thời gian deploy không?
- Có thể rollback trước và sau khi data migration xảy ra không?

### 1.1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Dùng ALTER TABLE ... RENAME COLUMN và DROP COLUMN.
2. Phân biệt RESTRICT và CASCADE.
3. Hiểu PostgreSQL theo dõi dependency bằng pg_depend.
4. Kiểm tra view, materialized view, rule và các object phụ thuộc cột.
5. Phân biệt SQL-standard function body với function body dạng string và dynamic SQL.
6. Xử lý dependencies trong PL/pgSQL, trigger và application code.
7. Lập kế hoạch expand-and-contract để đổi tên hoặc xóa cột.
8. Hiểu lock, transaction, table rewrite và disk-space impact.
9. Test migration và kiểm soát rollback.
10. Viết runbook để triển khai schema change an toàn.

### 1.2. Nguyên tắc cốt lõi

- Đổi tên cột là thay đổi schema contract; mọi consumer gửi tên cột cũ có thể lỗi.
- View thường lưu dependency theo object/column identity, không đơn giản là chuỗi SQL được tìm-thay.
- Output column name của view là contract riêng; đổi tên base column không tự động đổi tên output column của view.
- Function body dạng string và dynamic SQL có thể chứa tham chiếu không được PostgreSQL ghi nhận như dependency.
- DROP COLUMN mặc định dùng RESTRICT; CASCADE có thể xóa nhiều objects phụ thuộc theo chuỗi.
- Thành công của DROP COLUMN RESTRICT không chứng minh không còn tham chiếu trong application code.
- DDL cần lock; thao tác metadata nhanh vẫn có thể chờ lock và gây queue.
- Thay đổi nên được rollout qua giai đoạn tương thích khi nhiều application versions cùng chạy.
- Luôn kiểm tra pg_depend, source code, application telemetry và tests trước khi xóa cột.

---

## 2. Đổi tên cột bằng ALTER TABLE

### 2.1. Cú pháp cơ bản

~~~sql
ALTER TABLE schema_name.table_name
RENAME COLUMN old_column_name TO new_column_name;
~~~

Ví dụ:

~~~sql
ALTER TABLE app.customers
RENAME COLUMN full_name TO display_name;
~~~

Sau lệnh này, table không còn column tên full_name; column hiện tại có tên display_name. Dữ liệu hiện có vẫn nằm trong cùng column. PostgreSQL không cần copy toàn bộ rows chỉ để đổi tên.

### 2.2. Đổi tên không phải thêm cột mới

Rename là thay đổi metadata của column hiện hữu:
- Giá trị trong rows không bị chuyển sang column khác.
- Column identity nội bộ (attribute number/attnum) vẫn được giữ.
- Indexes và constraints phụ thuộc column thường tiếp tục gắn với cùng column.
- SQL gửi tên cột cũ sau rename sẽ không resolve được trong table.
- Consumers tham chiếu qua view có thể tiếp tục hoạt động do view dependency lưu theo column identity.

Điểm cuối rất quan trọng: PostgreSQL có thể giữ view hoạt động sau rename, nhưng application query trực tiếp vào table bằng tên cũ sẽ lỗi.

### 2.3. Đổi tên table và đổi tên column

Tên table và tên column là hai thay đổi độc lập:

~~~sql
ALTER TABLE app.customer
RENAME TO customers;

ALTER TABLE app.customers
RENAME COLUMN name TO display_name;
~~~

Mỗi lệnh có thể ảnh hưởng các consumers khác nhau. Đổi tên table cũng không tự sửa mọi SQL string trong function hoặc application source.

### 2.4. Đổi tên cột trong schema khác

Tên table nên được schema-qualify để tránh thao tác nhầm object khi search_path có nhiều schemas:

~~~sql
ALTER TABLE accounting.invoices
RENAME COLUMN invoice_date TO issued_at;
~~~

Trước migration, xác nhận relation đúng bằng catalog hoặc \d+ accounting.invoices trong psql.

### 2.5. Đổi tên trong partitioned table

Với partitioned table, column là một phần của parent table schema. Thay đổi schema ở parent cần được xem cùng partition hierarchy và các partitions. PostgreSQL quản lý nhiều thay đổi schema trên partitions theo command semantics/version; kiểm tra mọi partitions và indexes sau migration, nhất là khi có foreign tables hoặc partitions được quản lý riêng.

Không tự chạy các lệnh rename độc lập trên từng child partition nếu parent partitioned table là object được ứng dụng sử dụng. Xác nhận DDL behavior trên major version đang chạy.

### 2.6. Đổi tên không đổi giá trị mặc định

Rename column không thay đổi expression của default hoặc identity property gắn với column. Tuy nhiên, function/application code tham chiếu column theo tên có thể cần sửa.

Kiểm tra:

~~~sql
SELECT
    a.attname,
    pg_get_expr(d.adbin, d.adrelid) AS column_default,
    a.attidentity,
    a.attgenerated
FROM pg_attribute AS a
LEFT JOIN pg_attrdef AS d
    ON d.adrelid = a.attrelid
   AND d.adnum = a.attnum
WHERE a.attrelid = 'app.orders'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

### 2.7. Đổi tên cột được view tham chiếu

Ví dụ tạo table và view:

~~~sql
CREATE TABLE app.accounts (
    account_id bigint PRIMARY KEY,
    account_name text NOT NULL
);

CREATE VIEW app.account_directory AS
SELECT account_id, account_name
FROM app.accounts;
~~~

Sau đó rename base column:

~~~sql
ALTER TABLE app.accounts
RENAME COLUMN account_name TO display_name;
~~~

View thường vẫn hoạt động vì PostgreSQL lưu dependency tới column identity. Output column của view vẫn có thể giữ tên account_name, vì tên cột của view là schema contract riêng.

~~~sql
SELECT * FROM app.account_directory;
~~~

Ứng dụng đọc app.account_directory.account_name vẫn có thể chạy trong khi ứng dụng đọc trực tiếp accounts.account_name sẽ lỗi. Nếu muốn đổi cả output name của view, hãy migration view riêng:

~~~sql
ALTER VIEW app.account_directory
RENAME COLUMN account_name TO display_name;
~~~

Đây là một thay đổi contract khác và có thể ảnh hưởng consumers của view.

### 2.8. Rename và application code

PostgreSQL không thể tự sửa:
- SQL query trong source code.
- ORM model/property mappings.
- Prepared statements đang được giữ ở connection pool.
- BI/report definitions.
- ETL scripts.
- Stored function bodies không có dependency tracking.
- Dynamic SQL strings.
- External services dùng database schema.

Search toàn repository và các query/report catalogs trước khi rename.

---

## 3. Xóa cột bằng ALTER TABLE DROP COLUMN

### 3.1. Cú pháp

~~~sql
ALTER TABLE schema_name.table_name
DROP COLUMN column_name;
~~~

Ví dụ:

~~~sql
ALTER TABLE app.customers
DROP COLUMN legacy_code;
~~~

Mặc định PostgreSQL dùng hành vi RESTRICT: không cho xóa nếu có object dependency được ghi nhận và cần được giữ lại.

Có thể viết rõ:

~~~sql
ALTER TABLE app.customers
DROP COLUMN legacy_code RESTRICT;
~~~

### 3.2. DROP COLUMN không giống DELETE dữ liệu

DELETE FROM table xóa rows theo điều kiện. DROP COLUMN loại bỏ một thuộc tính khỏi schema:
- Không xóa toàn bộ row.
- Không xóa các rows khác.
- Column không còn được truy cập qua SQL.
- Các object phụ thuộc được kiểm tra theo dependency rules.
- Không nhất thiết làm file table nhỏ đi ngay.

### 3.3. RESTRICT là lựa chọn mặc định an toàn

Nếu PostgreSQL biết một view/constraint/index hoặc object khác phụ thuộc column, lệnh DROP COLUMN có thể bị từ chối và nêu tên dependency. Đây là tín hiệu để kiểm tra và lên kế hoạch cập nhật consumer.

Ví dụ:

~~~sql
ALTER TABLE app.accounts
DROP COLUMN account_name RESTRICT;
~~~

Nếu view đang tham chiếu column, lệnh có thể báo dependency và yêu cầu CASCADE hoặc xóa dependency trước. Trong production migration, lỗi RESTRICT là thông tin hữu ích; đừng phản ứng bằng cách thêm CASCADE ngay lập tức.

### 3.4. CASCADE có thể xóa cả object phụ thuộc

~~~sql
ALTER TABLE app.accounts
DROP COLUMN account_name CASCADE;
~~~

CASCADE yêu cầu PostgreSQL xóa objects phụ thuộc vào column, ví dụ view/rule hoặc constraints liên quan, và có thể tiếp tục xóa các objects phụ thuộc vào những objects đó.

Một lệnh có thể làm biến mất:
- View.
- View khác phụ thuộc vào view đầu tiên.
- Materialized view/rule dependencies.
- Constraints hoặc indexes liên quan.
- Các objects khác được catalog dependency graph xác định.

Phạm vi cụ thể phụ thuộc dependency graph của database. Không dùng CASCADE như cách “sửa lỗi nhanh”; hãy xác định đầy đủ những object sẽ bị xóa và tạo lại chúng theo kế hoạch.

### 3.5. DROP COLUMN có thu hồi disk ngay không?

PostgreSQL thường đánh dấu column là dropped trong catalog; dữ liệu vật lý của column không được loại khỏi từng tuple ngay tại thời điểm DDL. Space không nhất thiết được trả về filesystem ngay.

Table rewrite như VACUUM FULL, CLUSTER hoặc công cụ rewrite phù hợp có thể loại bỏ phần storage cũ, nhưng có yêu cầu disk, lock và downtime riêng. Không chạy rewrite chỉ để “hoàn tất” DROP COLUMN nếu chưa đánh giá tác động.

### 3.6. Xóa nhiều cột

~~~sql
ALTER TABLE app.customers
    DROP COLUMN old_code,
    DROP COLUMN obsolete_flag;
~~~

Gộp các thay đổi có thể giảm số lần lấy lock, nhưng chỉ làm khi dependencies và rollback đã được kiểm tra cho tất cả cột. Một cột có dependency có thể làm cả statement thất bại.

### 3.7. Xóa cột trong partitioned table

Xóa column khỏi parent partitioned table phải tương thích với partitions và các dependent objects. Kiểm tra constraints/indexes trên parent và child, foreign tables nếu có, cùng mọi consumer. Không giả định mọi partition được quản lý ngoài PostgreSQL sẽ tự thay đổi.

### 3.8. Không thể dùng DROP COLUMN để đổi tên

Không nên tạo column mới, drop column cũ rồi hy vọng dữ liệu tự chuyển. Muốn đổi tên, dùng RENAME COLUMN. Nếu cần thay đổi type/semantics hoặc migrate data, dùng expand-and-contract với backfill và validation.

---

## 4. Dependency tracking trong PostgreSQL

### 4.1. Object dependency là gì?

PostgreSQL lưu nhiều quan hệ phụ thuộc giữa database objects trong system catalogs. Dependency cho phép server:
- Ngăn xóa object còn được tham chiếu.
- Xóa object phụ thuộc khi dùng CASCADE.
- Quản lý thứ tự drop/recreate.
- Theo dõi references giữa relation, column, view, rule, constraint, type, function và các objects khác.

Dependency tracking là một graph: một object có thể phụ thuộc vào nhiều objects, và một object có thể được nhiều objects tham chiếu.

### 4.2. pg_depend

pg_depend là catalog chính lưu dependency records. Một số cột quan trọng:
- classid: catalog chứa object phụ thuộc.
- objid: OID của object phụ thuộc.
- objsubid: sub-object number, thường là column number đối với relation.
- refclassid: catalog chứa object được tham chiếu.
- refobjid: OID của referenced object.
- refobjsubid: sub-object number được tham chiếu, thường là column attnum.
- deptype: loại dependency.

Không nên hard-code OIDs vì OID thay đổi giữa databases/restores. Dùng regclass và catalog joins để truy vấn.

### 4.3. Dependency theo column identity

Column có attnum trong pg_attribute. View query, index expression, constraint và một số object definitions có thể tham chiếu column bằng identity nội bộ này. Vì vậy rename column không giống tìm-thay chuỗi SQL: dependency vẫn trỏ đến cùng column sau khi tên thay đổi.

Lấy attnum:

~~~sql
SELECT
    attrelid::regclass AS table_name,
    attname,
    attnum,
    attisdropped
FROM pg_attribute
WHERE attrelid = 'app.accounts'::regclass
  AND attname = 'account_name'
  AND attnum > 0;
~~~

### 4.4. Truy vấn direct dependencies của một column

Ví dụ truy vấn dependency records tham chiếu một column:

~~~sql
SELECT
    d.deptype,
    d.classid::regclass AS dependent_catalog,
    d.objid,
    d.objsubid,
    pg_describe_object(
        d.classid,
        d.objid,
        d.objsubid
    ) AS dependent_object
FROM pg_depend AS d
WHERE d.refclassid = 'pg_class'::regclass
  AND d.refobjid = 'app.accounts'::regclass
  AND d.refobjsubid = (
      SELECT a.attnum
      FROM pg_attribute AS a
      WHERE a.attrelid = 'app.accounts'::regclass
        AND a.attname = 'account_name'
        AND a.attnum > 0
        AND NOT a.attisdropped
  )
ORDER BY dependent_catalog::text, dependent_object;
~~~

Đây là inventory dựa trên catalog, không phải danh sách toàn bộ consumer có thể có trong application source. Kiểm tra kết quả trên đúng major version và quyền truy cập catalog.

### 4.5. Dependency type

deptype mô tả cách PostgreSQL xử lý dependency. Các loại phổ biến gồm:
- Normal dependency: object tham chiếu không thể bị drop khi object phụ thuộc còn tồn tại nếu dùng RESTRICT.
- Auto dependency: object có thể tự bị drop khi parent object bị drop.
- Internal dependency: object được quản lý như một phần của object khác.
- Extension dependency: object thuộc extension lifecycle.
- Pin dependency: object hệ thống được bảo vệ đặc biệt.

Không nên tự diễn giải mọi deptype như nhau. Dùng pg_describe_object và tài liệu catalog để hiểu object cụ thể.

### 4.6. pg_describe_object

pg_describe_object(classid, objid, objsubid) tạo mô tả dễ đọc cho object trong dependency record. Nó hữu ích khi classid có thể là pg_rewrite, pg_constraint, pg_class, pg_proc hoặc catalog khác.

### 4.7. Dependency graph không phải static code analyzer

Catalog chỉ biết dependencies được PostgreSQL ghi nhận. Nó không thể tự tìm:
- SQL string trong application repository.
- Dynamic SQL được tạo bằng concatenation.
- Query text trong external BI tool.
- Stored function body không có dependency metadata.
- Jobs chạy ở service khác.
- Client query dùng column name cũ.

Cần kết hợp catalog inventory, source search, telemetry và tests.

---

## 5. Views, materialized views và rules

### 5.1. View lưu query đã phân tích

View trong PostgreSQL không chỉ là một chuỗi SQL được chạy lại nguyên văn mỗi lần. PostgreSQL lưu query tree/rule và dependencies tới các objects, bao gồm relation và columns được tham chiếu.

Ví dụ:

~~~sql
CREATE VIEW app.customer_summary AS
SELECT customer_id, display_name
FROM app.customers;
~~~

View có dependency tới các columns của base table. Khi rename base column, PostgreSQL có thể giữ view hợp lệ vì dependency dựa vào column identity.

### 5.2. Đổi tên base column không tự đổi output column của view

Ví dụ:

~~~sql
CREATE TABLE app.people (
    person_id bigint PRIMARY KEY,
    full_name text NOT NULL
);

CREATE VIEW app.people_public AS
SELECT person_id, full_name
FROM app.people;

ALTER TABLE app.people
RENAME COLUMN full_name TO display_name;
~~~

View có thể tiếp tục trả output column tên full_name, trong khi base table có display_name:

~~~sql
SELECT full_name
FROM app.people_public;
~~~

Nếu muốn đổi contract của view, đổi tên output column riêng:

~~~sql
ALTER VIEW app.people_public
RENAME COLUMN full_name TO display_name;
~~~

Consumers của view cũng cần migration tương ứng.

### 5.3. View lồng nhau

Một view có thể được dùng bởi view khác:

~~~sql
CREATE VIEW app.people_names AS
SELECT person_id, full_name
FROM app.people_public;

CREATE VIEW app.people_report AS
SELECT person_id, upper(full_name) AS normalized_name
FROM app.people_names;
~~~

Dependency chain có thể là:

~~~text
app.people
   |
   v
app.people_public
   |
   v
app.people_names
   |
   v
app.people_report
~~~

Khi thay đổi base column, view tree có thể tiếp tục hoạt động nếu query tree vẫn tham chiếu đúng column identity. Khi DROP COLUMN CASCADE, PostgreSQL có thể xóa chuỗi view/rules phụ thuộc. Inventory tất cả levels trước khi dùng CASCADE.

### 5.4. Tìm view trực tiếp phụ thuộc vào column

Có thể tra pg_depend và pg_rewrite:

~~~sql
WITH target_column AS (
    SELECT attnum
    FROM pg_attribute
    WHERE attrelid = 'app.people'::regclass
      AND attname = 'display_name'
      AND attnum > 0
      AND NOT attisdropped
)
SELECT DISTINCT
    v.oid::regclass AS dependent_view,
    v.relkind,
    r.rulename,
    pg_describe_object(
        d.classid,
        d.objid,
        d.objsubid
    ) AS dependency
FROM pg_depend AS d
JOIN pg_rewrite AS r
    ON d.classid = 'pg_rewrite'::regclass
   AND d.objid = r.oid
JOIN pg_class AS v
    ON v.oid = r.ev_class
WHERE d.refclassid = 'pg_class'::regclass
  AND d.refobjid = 'app.people'::regclass
  AND d.refobjsubid = (SELECT attnum FROM target_column)
ORDER BY dependent_view::text;
~~~

relkind giúp phân biệt ordinary view và materialized view trên catalog versions tương ứng. Query này tìm direct rule dependencies; view chains có thể cần truy vấn đệ quy hoặc inspection thêm.

### 5.5. CREATE OR REPLACE VIEW có giới hạn

CREATE OR REPLACE VIEW phù hợp khi cập nhật query mà giữ nguyên các existing output columns theo thứ tự, tên và data types. PostgreSQL cho phép thêm output columns ở cuối trong các trường hợp được hỗ trợ; không dùng nó để âm thầm đổi tên, xóa hoặc reorder các output columns hiện có.

Ví dụ thay query nhưng giữ contract:

~~~sql
CREATE OR REPLACE VIEW app.people_public AS
SELECT
    person_id,
    display_name AS full_name
FROM app.people;
~~~

Alias full_name giữ compatibility cho consumers cũ trong giai đoạn chuyển đổi.

### 5.6. Materialized views

Materialized view lưu kết quả query dưới dạng dữ liệu vật lý và có dependency tới các source objects. Khi base column rename, stored query definition thường vẫn tham chiếu đúng column identity. Tuy nhiên:
- Output schema của materialized view vẫn là contract riêng.
- Data không tự refresh chỉ vì base data thay đổi.
- REFRESH MATERIALIZED VIEW cần được lên lịch sau migration khi cần.
- Drop/recreate materialized view có thể cần rebuild indexes và gây downtime/resource cost.
- CASCADE có thể xóa materialized view nếu dependency được ghi nhận.

Kiểm tra bằng pg_matviews, pg_class và dependency catalogs.

### 5.7. Rules và rewrite system

Ordinary views được triển khai qua rewrite rules, thường có rule _RETURN. Vì vậy dependency của view xuất hiện trong pg_depend với dependent object thuộc pg_rewrite. Không nên drop rule thủ công để “gỡ dependency” nếu chưa hiểu semantics của view.

### 5.8. View column compatibility strategy

Khi base column đổi tên:
1. Giữ output name cũ của view bằng alias.
2. Deploy application chuyển sang view contract mới nếu cần.
3. Tạo view version mới nếu muốn đổi output schema rõ ràng.
4. Migrate consumers.
5. Drop old view sau khi không còn consumer.

Đối với view được chia sẻ bởi nhiều teams, versioned view thường dễ phối hợp hơn một lần đổi tên output column đột ngột.

---

## 6. Function dependencies: SQL, PL/pgSQL và dynamic SQL

### 6.1. Vì sao function cần được kiểm tra riêng?

Function có thể tham chiếu table/column trong body. Nhưng PostgreSQL không thể theo dõi mọi dạng tham chiếu trong mọi ngôn ngữ. Cách viết function body quyết định liệu dependencies trong body có được parse và ghi nhận lúc tạo hay chỉ được resolve khi function chạy.

Do đó:
- Một view có thể chặn DROP COLUMN vì dependency được ghi nhận.
- Một function body dạng string có thể không chặn DROP COLUMN dù vẫn chứa tên column cũ.
- Function đó có thể chỉ lỗi khi được gọi sau migration.

### 6.2. SQL function dùng string literal body

Ví dụ:

~~~sql
CREATE FUNCTION app.get_person_name(p_id bigint)
RETURNS text
LANGUAGE sql
AS $$
    SELECT full_name
    FROM app.people
    WHERE person_id = p_id
$$;
~~~

Với dạng body string truyền thống, parser không phân tích đầy đủ body để tạo dependency records như SQL-standard body. Vì vậy không được dựa vào DROP COLUMN RESTRICT để chứng minh function không dùng column.

Sau khi rename full_name, function body vẫn chứa identifier cũ. Khi được parse/execute lại, function có thể lỗi vì column không còn tồn tại.

### 6.3. SQL-standard function body

Các PostgreSQL versions hỗ trợ SQL-standard body syntax cho phép body được parse khi tạo function:

~~~sql
CREATE FUNCTION app.person_name(p_id bigint)
RETURNS text
LANGUAGE SQL
BEGIN ATOMIC
    SELECT display_name
    FROM app.people
    WHERE person_id = p_id;
END;
~~~

Với SQL-standard body được parse tại definition time, PostgreSQL có thể ghi nhận dependencies của referenced objects. Cú pháp này được hỗ trợ từ PostgreSQL 14; xác nhận version đích trước khi dùng.

Đây là một trong những lý do SQL-standard body có lợi cho dependency tracking. Tuy vậy, vẫn cần test function behavior và không coi dependency catalog là static analyzer cho toàn bộ application.

### 6.4. PL/pgSQL function

Ví dụ:

~~~sql
CREATE FUNCTION app.lookup_person(p_id bigint)
RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    result_name text;
BEGIN
    SELECT full_name
    INTO result_name
    FROM app.people
    WHERE person_id = p_id;

    RETURN result_name;
END;
$$;
~~~

PL/pgSQL body được lưu dưới dạng source text và các SQL statements được phân tích/chuẩn bị khi function được thực thi. Table/column references trong body thường không được ghi thành dependency records giống view hoặc SQL-standard function body.

Sau rename/drop, function có thể chỉ lỗi khi nhánh code tương ứng chạy hoặc khi statement được compile lại. Vì thế phải search và test mọi PL/pgSQL function dùng cột.

### 6.5. Dynamic SQL

Ví dụ:

~~~sql
EXECUTE
    'SELECT full_name FROM app.people WHERE person_id = '
    || p_id;
~~~

Dynamic SQL được tạo lúc runtime; catalog dependency tracking không thể biết chắc tên relation/column cuối cùng. Rename/drop có thể không phát hiện function này. Dùng parameter binding với USING để tránh SQL injection và làm code rõ hơn:

~~~sql
EXECUTE
    'SELECT display_name
     FROM app.people
     WHERE person_id = $1'
INTO result_name
USING p_id;
~~~

Parameter binding bảo vệ giá trị, nhưng identifier động vẫn cần được quản lý riêng. Tên table/column động phải được allowlist và quote đúng bằng format('%I', identifier).

### 6.6. Function body tham chiếu qua view

Function có thể chỉ query view thay vì base table:

~~~sql
CREATE FUNCTION app.get_public_name(p_id bigint)
RETURNS text
LANGUAGE sql
AS $$
    SELECT full_name
    FROM app.people_public
    WHERE person_id = p_id
$$;
~~~

Nếu view giữ output column full_name, function có thể tiếp tục hoạt động dù base table column đổi tên. Đây là cách tạo compatibility boundary, nhưng function body dạng string vẫn cần test và application contracts phải được duy trì.

### 6.7. Tìm function body có thể chứa tên cột

Có thể tìm text trong pg_proc.prosrc:

~~~sql
SELECT
    n.nspname AS schema_name,
    p.proname AS function_name,
    pg_get_function_identity_arguments(p.oid) AS arguments,
    l.lanname AS language,
    p.prosrc
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
JOIN pg_language AS l
    ON l.oid = p.prolang
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND p.prosrc ILIKE '%full_name%'
ORDER BY n.nspname, p.proname;
~~~

Đây chỉ là text search:
- Có thể false positive trong comments hoặc string literals không liên quan.
- Có thể bỏ sót tên được tạo động, quoted/case-sensitive identifiers hoặc SQL fragments từ bảng config.
- Function body có thể được viết trong language khác.
- Overloaded functions cần nhận diện bằng identity arguments.

Dùng pg_get_functiondef(oid) để lấy definition đầy đủ và review từng candidate.

### 6.8. Tìm function dependency được catalog ghi nhận

Query dependency trực tiếp tới column có thể chứa objects thuộc pg_proc hoặc dependency gián tiếp qua view. Dùng pg_depend với pg_describe_object để xem các records thực tế. Nhưng không có kết quả không chứng minh không function nào sử dụng column; string body và dynamic SQL là khoảng trống quan trọng.

### 6.9. Trigger function

Trigger gắn với table và gọi trigger function. Trigger definition có dependency tới function và relation, nhưng source body của trigger function vẫn có thể chứa tham chiếu cột không được track. Kiểm tra cả:
- Trigger definitions trong pg_trigger.
- Function definition trong pg_proc.
- UPDATE OF column trigger declarations.
- OLD.column/NEW.column trong PL/pgSQL.
- Dynamic SQL trong trigger function.
- Application side effects được trigger gọi.

### 6.10. Function overload và API contract

Function cùng tên có thể có nhiều signatures. Khi thay đổi tham số/return type hoặc function name:
- Dùng pg_get_function_identity_arguments.
- Kiểm tra callers theo signature.
- Tạo overload/version mới khi cần compatibility.
- Không DROP FUNCTION chỉ theo tên nếu có overload.
- Kiểm tra grants/ownership/security definer settings.
- Test mọi callers và permissions.

---

## 7. Các object khác có thể phụ thuộc vào column

### 7.1. Indexes

Index expression hoặc index key có thể phụ thuộc column. Khi xóa column, indexes liên quan trong cùng table thường được PostgreSQL tự xử lý như một phần của ALTER TABLE. Trước migration, vẫn nên inventory để biết index nào sẽ mất và query nào đang dựa vào index đó.

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'app'
  AND tablename = 'people'
ORDER BY indexname;
~~~

Nếu index là expression index, kiểm tra biểu thức trong indexdef để phát hiện column reference.

### 7.2. Constraints

Các constraints có thể tham chiếu column:
- PRIMARY KEY.
- UNIQUE.
- FOREIGN KEY.
- CHECK.
- NOT NULL (thuộc column metadata).
- Exclusion constraints.

Index/constraint thuộc table có thể được tự động drop hoặc bị ảnh hưởng khi xóa column. Foreign key ở table khác tham chiếu tới unique/primary key column cần được xem như dependency liên quan. Không giả định chỉ nhìn constraint của table nguồn là đủ.

~~~sql
SELECT
    conrelid::regclass AS table_name,
    conname,
    contype,
    pg_get_constraintdef(oid) AS definition,
    convalidated
FROM pg_constraint
WHERE connamespace = 'app'::regnamespace
ORDER BY conrelid::regclass::text, conname;
~~~

### 7.3. Generated columns và default expressions

Generated column hoặc default expression có thể sử dụng column khác. PostgreSQL ghi nhận nhiều expression dependencies trong catalogs và có thể ngăn thay đổi làm expression không còn hợp lệ.

Kiểm tra generated/default expressions:

~~~sql
SELECT
    a.attname,
    a.attgenerated,
    pg_get_expr(d.adbin, d.adrelid) AS expression
FROM pg_attribute AS a
LEFT JOIN pg_attrdef AS d
    ON d.adrelid = a.attrelid
   AND d.adnum = a.attnum
WHERE a.attrelid = 'app.people'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

### 7.4. Triggers

Trigger có thể:
- Được khai báo chạy khi UPDATE OF một column.
- Đọc OLD.column hoặc NEW.column.
- Ghi giá trị column sang audit/history table.
- Gọi function chứa SQL tham chiếu column.
- Gửi events tới hệ thống khác.

Inventory triggers:

~~~sql
SELECT
    t.tgname,
    t.tgenabled,
    pg_get_triggerdef(t.oid, true) AS trigger_definition,
    t.tgfoid::regprocedure AS trigger_function
FROM pg_trigger AS t
WHERE t.tgrelid = 'app.people'::regclass
  AND NOT t.tgisinternal
ORDER BY t.tgname;
~~~

Sửa trigger definition và trigger function cùng đợt deploy. Trigger event có thể không còn chạy nếu column được đổi tên/xóa hoặc function lỗi khi truy cập OLD/NEW field.

### 7.5. Row-level security policies

Policy expression có thể tham chiếu column để kiểm soát row visibility hoặc write permissions. Kiểm tra:

~~~sql
SELECT
    schemaname,
    tablename,
    policyname,
    permissive,
    roles,
    cmd,
    qual,
    with_check
FROM pg_policies
WHERE schemaname = 'app'
  AND tablename = 'people'
ORDER BY policyname;
~~~

Một migration thay đổi policy có thể mở rộng hoặc thu hẹp dữ liệu mà application role nhìn thấy. Test bằng đúng role và row-level security state.

### 7.6. Foreign keys ở table khác

Nếu column được referenced bởi foreign key từ table khác, DROP COLUMN có thể bị chặn do constraint phụ thuộc. Xác định cả referencing và referenced relations:

~~~sql
SELECT
    conrelid::regclass AS referencing_table,
    conname,
    confrelid::regclass AS referenced_table,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE contype = 'f'
  AND (
      conrelid = 'app.people'::regclass
      OR confrelid = 'app.people'::regclass
  )
ORDER BY referencing_table::text, conname;
~~~

Khi drop một referenced key, phải xử lý foreign keys ở các bảng con theo business rules, không chỉ drop constraint để DDL chạy qua.

### 7.7. Partition keys và indexes

Nếu column là partition key, primary/unique key component hoặc index key quan trọng, xóa nó có thể không được phép hoặc yêu cầu thay đổi partition/index structure trước. Kiểm tra partition key definition, constraints, indexes và application routing logic trước khi migration.

### 7.8. Views, functions và consumers bên ngoài

Catalog queries chỉ là một phần inventory. Bổ sung:
- Stored procedures và functions.
- Event triggers.
- Materialized views.
- BI/report tools.
- ETL/ELT jobs.
- Application repositories.
- ORM mappings.
- Prepared statements.
- Scheduled SQL.
- Data export contracts.
- External services và scripts.

### 7.9. Dependency inventory table

Tạo bảng theo dõi migration:

| Consumer | Loại | Dependency tracked? | Owner | Kế hoạch |
|---|---|---|---|---|
| customer_summary | View | Có | Data team | Giữ alias, migrate sau |
| person_lookup | PL/pgSQL | Body refs thường không track | Backend team | Sửa và test |
| people_audit | Trigger | Trigger tracked, body cần review | DBA | Update function |
| BI customer report | External | Không | Analytics | Update report |
| ORM Customer.fullName | Application | Không | App team | Deploy compatibility release |

Đánh dấu trạng thái và owner cho từng consumer. Không xóa cột khi còn consumer chưa được xử lý.

---

## 8. Xử lý view và function khi đổi tên cột

### 8.1. Chọn compatibility boundary

Có thể để application truy cập trực tiếp table hoặc thông qua views/functions. Nếu database được nhiều services dùng, view/function API giúp tách physical schema khỏi consumer contract.

Ví dụ giữ output column cũ trong view:

~~~sql
CREATE OR REPLACE VIEW app.people_api AS
SELECT
    person_id,
    display_name AS full_name
FROM app.people;
~~~

Ứng dụng cũ vẫn đọc full_name từ view, trong khi schema table đã dùng display_name.

### 8.2. Migration view output column

Nếu muốn consumer chuyển sang tên mới:
1. Tạo view version mới với output name mới.
2. Deploy consumer đọc view mới.
3. Theo dõi usage của view cũ.
4. Chờ tất cả consumers chuyển.
5. Drop view cũ khi dependency graph và telemetry cho phép.

Ví dụ:

~~~sql
CREATE VIEW app.people_api_v2 AS
SELECT
    person_id,
    display_name
FROM app.people;
~~~

Không đổi contract view dùng chung mà không thông báo các teams đang tiêu thụ.

### 8.3. Sửa SQL function body

Với SQL-standard function body có dependency tracking, thay đổi base column có thể làm migration bị chặn hoặc cần recreate/update function theo dependency rules. Dùng CREATE OR REPLACE FUNCTION khi signature và return contract cho phép.

Với string body hoặc PL/pgSQL:
- Search function definitions.
- Sửa tên column.
- Kiểm tra mọi branch và dynamic SQL.
- Deploy function trước khi application gọi path mới.
- Chạy tests bằng application role.
- Kiểm tra function owner, grants và SECURITY DEFINER behavior.

### 8.4. Function wrapper để tương thích

Có thể giữ function API ổn định và thay implementation:

~~~sql
CREATE OR REPLACE FUNCTION app.person_display_name(p_id bigint)
RETURNS text
LANGUAGE sql
AS $$
    SELECT display_name
    FROM app.people
    WHERE person_id = p_id
$$;
~~~

Consumers gọi function không cần biết tên column vật lý. Tuy nhiên, thay đổi return type, volatility, security attributes hoặc function signature vẫn có thể phá API.

### 8.5. PL/pgSQL OLD và NEW

Trigger function dùng OLD/NEW records. Khi xóa hoặc đổi tên field, code như OLD.full_name hoặc NEW.full_name có thể lỗi khi trigger chạy. Trigger definition có thể vẫn tồn tại, vì body source không được rewrite tự động.

Test các DML paths thực sự kích hoạt trigger:
- INSERT.
- UPDATE từng loại column.
- UPDATE nhiều columns.
- DELETE.
- Bulk load/import nếu triggers được bật.
- ON CONFLICT DO UPDATE.

### 8.6. Dynamic SQL và identifier

Khi identifier được ghép từ text:
- Tìm mọi nơi tạo SQL statement.
- Dùng allowlist cho schema/table/column names.
- Dùng format('%I', identifier) để quote identifier.
- Dùng USING cho values.
- Không thay tên bằng search/replace toàn bộ chuỗi mà không hiểu quoting và case.
- Test từng branch dynamic query.

### 8.7. Materialized view refresh/rebuild

Nếu migration thay đổi materialized view query hoặc output schema, có thể phải drop/recreate hoặc tạo version mới. Xem:
- Dependency chain.
- Refresh duration.
- Unique index cần cho REFRESH CONCURRENTLY.
- Disk space cho materialized data và indexes.
- Lock và application read availability.
- Consumers của output columns.

---

## 9. Đổi tên và xóa cột theo expand-and-contract

### 9.1. Vì sao cần nhiều giai đoạn?

Trong rolling deployment, application instances không được cập nhật cùng lúc. Có thể đồng thời tồn tại:
- Instance cũ đọc/ghi column cũ.
- Instance mới đọc/ghi column mới.
- Background worker chưa restart.
- BI/ETL chạy theo lịch.
- Prepared connection giữ plan/session cũ.

Nếu rename/drop ngay, một nhóm consumer có thể lỗi giữa rollout. Expand-and-contract giữ schema tương thích trong giai đoạn chuyển đổi.

### 9.2. Pattern thêm column mới

Giả sử đổi full_name thành display_name. Một cách ít downtime là thêm column mới:

~~~sql
ALTER TABLE app.people
ADD COLUMN display_name text;
~~~

Sau đó:
1. Deploy application hỗ trợ cả full_name và display_name.
2. Dual-write hai columns hoặc dùng trigger đồng bộ trong giai đoạn chuyển tiếp.
3. Backfill dữ liệu cũ sang column mới theo batches.
4. Kiểm tra parity.
5. Chuyển readers sang display_name.
6. Dừng writes vào full_name.
7. Xác nhận không còn consumers dùng full_name.
8. Drop full_name trong migration riêng.

Đây là migration dữ liệu và schema; nó không phải một lệnh rename trực tiếp.

### 9.3. Dual-write và trigger

Dual-write ở application có thể đảm bảo cả hai columns nhận cùng giá trị, nhưng cần tránh một client cũ chỉ cập nhật cột cũ trong khi client mới chỉ cập nhật cột mới.

Trigger đồng bộ có thể làm compatibility layer trong giai đoạn rollout, nhưng phải định nghĩa rõ nguồn authoritative và xử lý trường hợp cả hai cột được cung cấp khác nhau. Tránh tạo vòng lặp trigger hoặc overwrite giá trị mới bằng dữ liệu cũ.

### 9.4. Backfill theo batches

Ví dụ backfill có giới hạn:

~~~sql
UPDATE app.people
SET display_name = full_name
WHERE display_name IS NULL
  AND person_id > 0
  AND person_id <= 10000;
~~~

Chạy nhiều batches với key ranges hoặc primary-key cursor. Sau mỗi batch:
- Commit.
- Ghi nhận progress.
- Theo dõi WAL/replication lag.
- Kiểm tra lock/latency.
- Retry an toàn.
- Tránh một transaction khổng lồ.

Điều kiện WHERE cần phù hợp với dữ liệu thực tế; ví dụ trên chỉ minh họa.

### 9.5. Xác nhận parity

~~~sql
SELECT count(*) AS mismatched_rows
FROM app.people
WHERE display_name IS DISTINCT FROM full_name;
~~~

Nếu có quy tắc normalize/case/trim, so sánh theo business transformation thay vì so sánh raw strings. Xác nhận null semantics và mọi rows được tạo/updated trong lúc backfill.

### 9.6. Chuyển reader trước khi drop

Deploy application đọc display_name trong khi dual-write còn hoạt động. Đợi:
- Tất cả instances mới đã chạy.
- Background workers đã cập nhật.
- Connection pools cũ đã drain.
- Scheduled jobs/report/ETL đã cập nhật.
- Telemetry không còn query full_name.
- Rollback window cho application đã qua.

Sau đó mới dừng dual-write và drop old column.

### 9.7. Dùng view làm compatibility layer

Nếu consumers truy cập qua view, có thể thay implementation view để giữ output contract cũ. Ví dụ view tiếp tục expose full_name từ display_name mới. Cách này giảm số clients cần deploy đồng thời, nhưng không bảo vệ clients truy cập table trực tiếp.

### 9.8. Contract phase

Contract là giai đoạn loại bỏ old column và old compatibility objects:
1. Xác nhận old consumers bằng zero-use window đủ dài.
2. Kiểm tra dependency catalogs.
3. Kiểm tra function bodies và source code.
4. Drop/replace dependent views/functions theo plan.
5. Thử DROP COLUMN RESTRICT trong staging.
6. Đặt lock_timeout và chạy DDL trong maintenance window phù hợp.
7. Xác minh schema sau commit.
8. Theo dõi errors và query failures.

### 9.9. Rollback trước contract

Trước khi drop old column, rollback thường là chuyển application reader về column cũ và tiếp tục dual-write. Sau khi drop old column, rollback cần restore column/data hoặc forward migration; chỉ đổi application version không khôi phục được dữ liệu đã mất.

### 9.10. Thay đổi nhỏ có downtime cho phép

Nếu có thể dừng toàn bộ writers/readers:
- Freeze application traffic.
- Drain transactions/connections.
- Update views/functions/application SQL.
- Rename/drop column.
- Validate.
- Deploy/start application.
- Reopen traffic.

Đây có thể là phương án đơn giản cho database nhỏ hoặc maintenance window rõ ràng, nhưng phải tính lock acquisition và validation time.

---

## 10. Locking, transactions và tác động vận hành

### 10.1. Rename/drop cần lock trên table

Các dạng ALTER TABLE như RENAME COLUMN và DROP COLUMN cần lock mạnh trên relation, thường là ACCESS EXCLUSIVE. Lock này có thể xung đột với cả queries đang đọc table.

DDL có thể chỉ thay đổi catalog và hoàn tất nhanh khi lấy được lock, nhưng vẫn phải chờ transactions đang giữ conflicting locks. Vì vậy một lệnh “nhanh” có thể bị kẹt lâu trong production.

### 10.2. Lock được giữ đến hết transaction

Nếu DDL chạy trong transaction block, relation lock thường được giữ tới COMMIT/ROLLBACK. Không đặt DDL giữa một transaction dài đang thực hiện nhiều công việc không liên quan.

Ví dụ:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE app.people
RENAME COLUMN full_name TO display_name;

COMMIT;
~~~

Nếu không lấy được lock trong 3 giây, statement fail thay vì chờ vô hạn. Chọn timeout theo maintenance policy và workload thực tế.

### 10.3. lock_timeout và statement_timeout

- lock_timeout giới hạn thời gian chờ lock cho mỗi lần lấy lock.
- statement_timeout giới hạn tổng thời gian statement chạy.
- idle_in_transaction_session_timeout giới hạn session idle trong transaction nếu được cấu hình.

Đặt timeout có thể làm migration fail nhanh và dễ retry. Không đặt quá thấp khiến DDL liên tục thất bại trong lúc traffic bình thường; cũng không để migration chờ lock vô hạn.

### 10.4. Kiểm tra blocker trước DDL

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    clock_timestamp() - a.xact_start AS transaction_age,
    pg_blocking_pids(a.pid) AS blocking_pids,
    a.query
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
ORDER BY a.xact_start NULLS LAST;
~~~

Nếu DDL đang chờ, tìm sessions giữ lock. Xác định owner, query và transaction age trước khi cancel/terminate.

### 10.5. Xem locks của relation

~~~sql
SELECT
    l.pid,
    l.mode,
    l.granted,
    a.application_name,
    a.state,
    a.query
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
    ON a.pid = l.pid
WHERE l.relation = 'app.people'::regclass
ORDER BY l.granted, l.pid;
~~~

Đây là một snapshot. Dùng cùng pg_stat_activity và pg_blocking_pids để tìm blocker chain.

### 10.6. DDL queue có thể ảnh hưởng traffic

Một ALTER TABLE chờ ACCESS EXCLUSIVE có thể tạo lock queue. Các queries mới muốn lấy locks xung đột có thể phải chờ phía sau DDL, khiến latency tăng dù DDL chưa thực thi. Nếu thấy waiters tăng:
- Xem DDL PID và lock mode.
- Xem blockers hiện tại.
- Hủy/retry migration nếu queue impact vượt ngưỡng.
- Chạy lại trong window phù hợp.
- Không để nhiều DDL tương tự chờ cùng lúc.

### 10.7. Transaction và prepared statements

Application connection pools có thể giữ sessions/prepared statements qua migration. PostgreSQL có cơ chế invalidation/replanning cho cached plans khi schema thay đổi, nhưng application-level SQL text dùng tên cột cũ vẫn lỗi khi được parse lại.

Sau rename:
- Drain/recycle connections nếu framework cần.
- Kiểm tra prepared statements.
- Xem application logs.
- Chạy query path thực tế.
- Không dựa vào việc một session đã cache plan cũ để coi migration tương thích.

### 10.8. Table rewrite và disk reclaim

DROP COLUMN thường là metadata operation nhanh, nhưng dữ liệu của column bị đánh dấu dropped. Existing row versions có thể vẫn chứa bytes cũ; các inserts/updates tiếp theo lưu giá trị NULL cho dropped attribute. Space được thu hồi dần khi rows được cập nhật, hoặc triệt để hơn qua table rewrite.

VACUUM thường làm space có thể tái sử dụng trong table, nhưng không nhất thiết trả space cho filesystem. VACUUM FULL/CLUSTER hoặc rewrite tool có thể reclaim storage nhưng cần thêm disk space, lock và maintenance window.

### 10.9. Không trộn schema change với rewrite lớn

Đổi tên/xóa cột và table rewrite là hai loại thay đổi khác nhau. Nếu vừa drop column vừa chạy VACUUM FULL/CLUSTER trong cùng maintenance window, hãy đánh giá:
- Thời gian lock.
- Disk space cần cho bản rewrite.
- WAL/replication impact.
- Backup window.
- Application downtime.
- Rollback procedure.

### 10.10. Kiểm tra sau DDL

Sau COMMIT:
- Query information_schema.columns/pg_attribute để xác nhận schema.
- Kiểm tra views/materialized views/functions/triggers.
- Kiểm tra indexes/constraints.
- Chạy smoke tests bằng application role.
- Theo dõi errors, locks và query latency.
- Xác nhận migration tool đã ghi version thành công.

---

## 11. Inventory dependencies trước khi đổi tên hoặc xóa

### 11.1. Xác nhận table và column

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    a.attname AS column_name,
    a.attnum,
    format_type(a.atttypid, a.atttypmod) AS data_type,
    a.attnotnull,
    a.attisdropped
FROM pg_attribute AS a
JOIN pg_class AS c
    ON c.oid = a.attrelid
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.oid = 'app.people'::regclass
  AND a.attnum > 0
ORDER BY a.attnum;
~~~

Kiểm tra column hiện hữu, type và nullability trước khi lấy attnum để tra dependencies.

### 11.2. Inventory views/materialized views

Dùng query pg_depend/pg_rewrite ở phần trước để tìm direct dependencies. Sau đó:
- Đọc definition bằng pg_get_viewdef.
- Kiểm tra output columns bằng information_schema.columns.
- Tìm views phụ thuộc vào view đó.
- Kiểm tra materialized view refresh policy.
- Xác định consumers ngoài database.

### 11.3. Inventory functions/procedures

~~~sql
SELECT
    n.nspname,
    p.proname,
    pg_get_function_identity_arguments(p.oid) AS identity_arguments,
    l.lanname,
    pg_get_functiondef(p.oid) AS definition
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
JOIN pg_language AS l
    ON l.oid = p.prolang
WHERE n.nspname = 'app'
ORDER BY p.proname, identity_arguments;
~~~

Review source cho tên column cũ. Có thể xuất definitions để tìm kiếm, nhưng bảo vệ output nếu function chứa literals/secrets.

### 11.4. Inventory triggers và policies

Sử dụng pg_trigger/pg_get_triggerdef và pg_policies. Đừng quên trigger function body, policy roles và command scope. Test cả SELECT, INSERT, UPDATE và DELETE với RLS-enabled application role.

### 11.5. Inventory constraints và indexes

Sử dụng pg_constraint, pg_indexes và indexdef. Xem các bảng khác tham chiếu column qua foreign keys. Kiểm tra expression indexes, partial-index predicates và INCLUDE columns.

### 11.6. Search application repositories

Search exact column identifier trong:
- SQL migrations.
- ORM entities/models.
- Query builders.
- Raw SQL.
- Reports/dashboards.
- ETL pipelines.
- Stored function definitions.
- Test fixtures.
- Configuration-driven SQL.
- Deployment scripts.

Tìm cả quoted identifiers và alias. Một tên column phổ biến có thể có false positives; review context thay vì thay thế hàng loạt.

### 11.7. Query telemetry

Nếu có pg_stat_statements hoặc query logging:
- Tìm queryid/query text dùng tên cũ.
- Kiểm tra application_name.
- Xem tần suất theo giờ/ngày.
- Chú ý jobs chạy hàng tuần/tháng/quý.
- Kiểm tra query logs trong thời gian đủ dài.
- Xác nhận prepared statements/connection pools đã chuyển.

pg_stat_statements chỉ lưu aggregate query texts theo configuration/normalization; nó không phải lịch sử đầy đủ mọi SQL đã từng chạy.

### 11.8. Owner và sign-off

Mỗi consumer cần:
- Owner/team.
- Môi trường sử dụng.
- Thời điểm deploy.
- Test evidence.
- Cách rollback.
- Ngày hết compatibility window.

Không thực hiện contract/drop khi chưa có owner cho các consumer quan trọng.

---

## 12. Runbook: đổi tên cột

### 12.1. Trường hợp downtime được chấp nhận

1. Inventory dependencies và consumers.
2. Deploy code/view/function definitions dùng tên mới hoặc giữ compatibility alias.
3. Dừng writers/readers theo maintenance plan.
4. Drain long-running transactions và connection pools nếu cần.
5. Chạy ALTER TABLE ... RENAME COLUMN với lock_timeout.
6. Cập nhật view output names nếu đó là mục tiêu.
7. Cập nhật functions/triggers/policies có body tham chiếu tên cũ.
8. Chạy smoke tests và business tests.
9. Reopen traffic và theo dõi.
10. Ghi migration version và owner.

### 12.2. Trường hợp rolling deployment

1. Add new column hoặc tạo compatibility view/function.
2. Deploy code đọc/ghi được cả schema cũ và mới.
3. Dual-write hoặc đồng bộ qua trigger trong thời gian chuyển tiếp.
4. Backfill dữ liệu cũ theo batches.
5. Validate parity và null semantics.
6. Chuyển toàn bộ readers sang tên mới.
7. Dừng old writes và chờ consumer window.
8. Rename/drop old column trong contract phase.
9. Gỡ compatibility layer sau khi không còn consumers.
10. Theo dõi query errors và data correctness.

### 12.3. Trước khi chạy DDL

~~~sql
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE app.people
RENAME COLUMN full_name TO display_name;

COMMIT;
~~~

Chỉ chạy sau khi application/view/function plan đã sẵn sàng. Nếu lock timeout hoặc DDL fail, transaction cần rollback và migration phải được retry theo quy trình.

### 12.4. Xác minh sau rename

~~~sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'app'
  AND table_name = 'people'
ORDER BY ordinal_position;
~~~

Sau đó test:
- Direct table reads/writes.
- Compatibility views.
- SQL functions.
- PL/pgSQL functions.
- Triggers.
- RLS policies.
- Application code và scheduled jobs.

---

## 13. Runbook: xóa cột

### 13.1. Deprecation phase

1. Đánh dấu column deprecated trong schema contract.
2. Thông báo consumer owners.
3. Deploy code không còn đọc/ghi column.
4. Dừng ETL/report/job sử dụng column.
5. Giữ column trong thời gian compatibility window.
6. Theo dõi query telemetry và application errors.
7. Archive dữ liệu nếu retention/business requirements cần.

### 13.2. Dependency phase

1. Query pg_depend theo table/attnum.
2. Inventory views/materialized views/rules.
3. Search function/procedure bodies.
4. Kiểm tra trigger definitions và trigger functions.
5. Kiểm tra indexes/constraints/foreign keys.
6. Kiểm tra generated/default expressions và policies.
7. Search application repositories và external consumers.
8. Có owner sign-off cho từng dependency.

### 13.3. Drop với RESTRICT

~~~sql
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE app.people
DROP COLUMN legacy_code RESTRICT;

COMMIT;
~~~

RESTRICT là lựa chọn phù hợp để migration fail khi catalog có dependency cần được giữ. Nếu fail, đọc object được nêu trong error và xử lý dependency có chủ đích.

### 13.4. CASCADE chỉ khi đã inventory

Nếu thiết kế yêu cầu drop các views/rules phụ thuộc, review dependency graph và export definitions trước. Có thể drop/recreate dependent objects theo migration script rõ ràng. Chỉ dùng CASCADE khi toàn bộ objects sẽ bị xóa đã được chấp thuận.

Không đưa CASCADE vào migration mặc định chỉ để tránh xử lý dependency errors.

### 13.5. Sau DROP COLUMN

- Kiểm tra column không còn trong information_schema.columns.
- Kiểm tra dependent views/functions/triggers.
- Kiểm tra index/constraint definitions.
- Chạy application smoke/regression tests.
- Theo dõi SQL errors và query latency.
- Kiểm tra table size theo thời gian; đừng kỳ vọng disk usage giảm ngay.
- Đánh giá table rewrite riêng nếu storage reclamation là yêu cầu.

---

## 14. Mẫu migration: rename có compatibility window

### 14.1. Tình huống

Table app.people có full_name. Ứng dụng cần chuyển sang display_name nhưng nhiều application instances và reports không thể deploy cùng lúc.

Mục tiêu:
- Không làm hỏng phiên bản ứng dụng cũ trong thời gian rollout.
- Giữ dữ liệu nhất quán giữa hai columns.
- Có thể chuyển reader theo từng service.
- Chỉ xóa column cũ sau khi xác nhận hết consumers.

### 14.2. Expand: thêm column mới

~~~sql
ALTER TABLE app.people
ADD COLUMN display_name text;
~~~

Column mới ban đầu nullable để không buộc phải backfill toàn bộ table trong một DDL transaction. Xác nhận default/nullability semantics theo ứng dụng.

### 14.3. Dual-write ở application

Trong giai đoạn chuyển tiếp, application writes cả hai columns với cùng giá trị. Đặt một nguồn authoritative và bảo đảm mọi writers tuân thủ quy tắc.

Nếu nhiều services có versions khác nhau, trigger có thể đồng bộ để bảo vệ các writes từ clients chưa được nâng cấp. Trigger phải được test cho insert/update, nulls và conflict cases.

### 14.4. Ví dụ trigger đồng bộ hai cột

Đây là một pattern minh họa cho table lab; cần điều chỉnh theo business rules:

~~~sql
CREATE OR REPLACE FUNCTION app.sync_people_name_columns()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.display_name IS NULL THEN
            NEW.display_name := NEW.full_name;
        ELSIF NEW.full_name IS NULL THEN
            NEW.full_name := NEW.display_name;
        ELSIF NEW.display_name IS DISTINCT FROM NEW.full_name THEN
            RAISE EXCEPTION 'full_name and display_name differ';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.display_name IS DISTINCT FROM OLD.display_name
       AND NEW.full_name IS NOT DISTINCT FROM OLD.full_name THEN
        NEW.full_name := NEW.display_name;
    ELSIF NEW.full_name IS DISTINCT FROM OLD.full_name
       AND NEW.display_name IS NOT DISTINCT FROM OLD.display_name THEN
        NEW.display_name := NEW.full_name;
    ELSIF NEW.display_name IS DISTINCT FROM NEW.full_name THEN
        RAISE EXCEPTION 'conflicting name updates';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER people_sync_name_columns
BEFORE INSERT OR UPDATE OF full_name, display_name
ON app.people
FOR EACH ROW
EXECUTE FUNCTION app.sync_people_name_columns();
~~~

Trigger này chỉ là ví dụ. Nếu cả hai columns thay đổi đồng thời thành giá trị khác nhau, nó từ chối write để tránh chọn nhầm giá trị. Nếu business cần ưu tiên một nguồn, thay logic conflict resolution một cách tường minh.

### 14.5. Backfill theo batches

~~~sql
UPDATE app.people
SET display_name = full_name
WHERE display_name IS NULL
  AND person_id >= 1
  AND person_id < 10001;
~~~

Lặp lại cho từng key range. Mỗi batch nên commit riêng, ghi progress và theo dõi WAL/replication lag. Trigger hoặc application dual-write cần được cài trước backfill để rows mới không bị bỏ sót.

### 14.6. Validate

~~~sql
SELECT
    count(*) FILTER (
        WHERE display_name IS DISTINCT FROM full_name
    ) AS mismatch_count,
    count(*) FILTER (
        WHERE display_name IS NULL
    ) AS missing_new_value
FROM app.people;
~~~

Nếu có mismatch, xác định source of truth và reconcile; không tự động overwrite toàn bộ dữ liệu bằng một phía.

### 14.7. Switch readers

Deploy readers dùng display_name. Có thể chuyển theo service/tenant/canary. Theo dõi:
- Query errors.
- Null values.
- API response differences.
- Reports/exports.
- Trigger exceptions.
- Background jobs.
- Prepared statements/connection pools.

### 14.8. Stop old writes

Khi mọi writers đã dùng display_name:
1. Tắt dual-write code cũ.
2. Xác nhận trigger không còn cần thiết.
3. Drop trigger/function compatibility layer.
4. Theo dõi zero usage của full_name qua đủ chu kỳ jobs.
5. Xác nhận owners sign-off.

### 14.9. Contract: bỏ column cũ

~~~sql
ALTER TABLE app.people
DROP COLUMN full_name RESTRICT;
~~~

Sau khi drop:
- Kiểm tra schema.
- Kiểm tra functions/views/triggers.
- Chạy application tests.
- Giữ rollback data/backup theo policy.
- Không chạy table rewrite nếu chưa có yêu cầu reclaim storage và kế hoạch riêng.

### 14.10. Alternative: giữ physical column, đổi view contract

Nếu ứng dụng truy cập qua view, có thể đổi underlying table column rồi giữ alias cũ trong view. Đây thường là compatibility approach đơn giản hơn dual-write, nhưng chỉ áp dụng khi consumers không truy cập base table trực tiếp và view vẫn updatable/đáp ứng write semantics.

---

## 15. Test strategy cho schema changes

### 15.1. Catalog tests

Trong staging, chạy:
- Inventory columns và attnum.
- Direct dependencies trong pg_depend.
- Views/materialized views.
- Functions/procedures.
- Triggers và policies.
- Constraints/indexes.
- Foreign keys từ các tables khác.

So sánh expected objects trước và sau migration.

### 15.2. Function tests

Gọi từng function path có sử dụng cột:
- SQL functions.
- PL/pgSQL functions.
- Trigger functions.
- Dynamic SQL branches.
- Functions chạy theo scheduled jobs.
- Functions gọi bởi application roles khác nhau.

Một function không được gọi trong smoke test vẫn có thể lỗi ở branch hiếm.

### 15.3. View tests

Test:
- View trực tiếp.
- View lồng nhau.
- Materialized view query/refresh.
- Output column names/types.
- Permissions và security barrier/security invoker behavior nếu liên quan.
- Application queries sử dụng view.

### 15.4. DML tests

Với trigger/constraint/policy, test:
- INSERT.
- UPDATE column cũ.
- UPDATE column mới.
- UPDATE cả hai columns.
- DELETE.
- ON CONFLICT.
- Bulk import/copy.
- RLS với từng role.

### 15.5. Compatibility tests

Chạy cả application version cũ và mới trong staging trong cùng schema window. Xác nhận phiên bản cũ vẫn đọc/ghi được trong giai đoạn expand và phiên bản mới không cần column cũ sau switch.

### 15.6. Lock tests

Chạy migration khi có transaction đọc/ghi table để đo lock wait. Kiểm tra lock_timeout, queue behavior và thời gian DDL. Dùng workload gần production nhưng không gây ảnh hưởng hệ thống thật.

### 15.7. Rollback tests

Test rollback ở từng phase:
- Trước backfill.
- Sau một phần backfill.
- Sau full backfill nhưng trước reader switch.
- Sau reader switch nhưng trước drop old column.
- Sau drop old column.

Rollback sau contract cần restore column/data hoặc forward migration; không chỉ revert code.

### 15.8. Migration idempotency

Migration runner có thể đảm bảo mỗi migration chỉ chạy một lần. Nếu cần script có thể retry, thiết kế explicit guards và state checks. Không dùng IF EXISTS/IF NOT EXISTS để che một schema state không mong muốn mà không validate.

### 15.9. Observability

Trong rollout, theo dõi:
- Application error rate.
- Query errors chứa undefined_column.
- Function execution failures.
- View/report failures.
- Lock waits.
- Trigger exceptions.
- Backfill progress/mismatch counts.
- Database CPU/WAL/replication lag.
- Consumer usage của old column.

### 15.10. Readiness gate

Chỉ chuyển contract phase khi:
- Tất cả critical consumers đã migrate.
- Old column usage bằng zero trong thời gian quan sát đủ dài.
- Data parity đạt.
- Views/functions/triggers/policies đã được test.
- Rollback path và owner đã rõ.
- DDL lock window được phê duyệt.

---

## 16. Rollback và phục hồi

### 16.1. Rollback rename

Nếu rename trực tiếp và chưa có writes/schema changes khác, có thể rename lại:

~~~sql
ALTER TABLE app.people
RENAME COLUMN display_name TO full_name;
~~~

Nhưng rollback code và database phải được phối hợp. Nếu ứng dụng mới đã ghi dữ liệu theo semantics mới hoặc view contracts đã đổi, rename ngược có thể không đủ.

### 16.2. Rollback expand phase

Nếu đã thêm column mới nhưng chưa chuyển readers:
- Dừng dual-write/trigger theo kế hoạch.
- Giữ column mới để điều tra hoặc drop nếu chắc chắn không còn dependency.
- Source column cũ vẫn là authoritative.
- Không xóa dữ liệu mới nếu chưa biết có consumer nào đã sử dụng.

### 16.3. Rollback sau backfill

Backfill có thể đã tạo dữ liệu mới hoặc normalize values. Nếu source vẫn còn, có thể dừng migration và giữ cả hai columns. Không copy ngược tự động nếu có writes khác nhau ở hai phía.

### 16.4. Rollback sau reader switch

Chuyển readers về cột cũ nếu dual-write còn hoạt động và parity vẫn đúng. Nếu dual-write đã tắt, cần xác định cột nào là source of truth và đồng bộ trước khi revert application.

### 16.5. Rollback sau DROP COLUMN

Sau khi drop old column, PostgreSQL không thể đơn giản RENAME lại vì column definition/data đã không còn khả dụng qua SQL. Muốn rollback:
- Restore từ backup/PITR vào môi trường phù hợp rồi trích dữ liệu.
- Re-add column và backfill từ new column nếu semantics tương đương.
- Reconstruct từ audit/event history.
- Forward fix trên schema mới.

Nếu dữ liệu old column đã khác semantics hoặc đã mất, re-add column không tự khôi phục giá trị cũ.

### 16.6. CASCADE rollback

CASCADE có thể drop nhiều views/rules/constraints. Rollback cần definitions, ownership, grants, indexes và materialized data/refresh plan. Lưu definitions trước migration và ưu tiên migration scripts có thể recreate objects.

### 16.7. Backup trước contract

Trước DROP COLUMN quan trọng:
- Xác nhận backup gần nhất có thể restore.
- Ghi lại table/column metadata.
- Lưu view/function/trigger definitions.
- Lưu grants/owners.
- Xác nhận retention/legal requirements.
- Xác định PITR window nếu cần.

Backup chỉ có giá trị nếu đã test restore path; không dùng backup chưa xác minh làm lý do bỏ qua validation.

---

## 17. Những lỗi thường gặp

### 17.1. Nghĩ rằng rename tự sửa application SQL

PostgreSQL chỉ quản lý dependencies được ghi nhận trong database. Source code, ORM, BI và dynamic SQL phải được cập nhật riêng.

### 17.2. Nghĩ rằng view output name tự đổi theo base column

View output columns là schema contract riêng. Base column rename có thể giữ view chạy nhưng output name vẫn cũ.

### 17.3. Dùng CASCADE để vượt qua lỗi RESTRICT

CASCADE có thể xóa nhiều dependent objects. Trước hết inventory dependencies và xác định consumer owner.

### 17.4. Dựa vào DROP RESTRICT để phát hiện mọi function

Function body dạng string, PL/pgSQL source và dynamic SQL có thể không có body dependencies trong catalog. Phải search/test riêng.

### 17.5. Drop column khi application cũ còn chạy

Một instance cũ hoặc scheduled job có thể gọi tên column sau khi drop và gặp undefined_column. Đợi đủ compatibility window và kiểm tra telemetry.

### 17.6. Cho rằng DROP COLUMN giải phóng disk ngay

Column bị đánh dấu dropped; existing tuples có thể còn bytes cũ. Space được thu hồi dần khi rows được cập nhật hoặc qua table rewrite.

### 17.7. DDL nhanh nên không cần maintenance window

Rename/drop cần lock mạnh. Transaction dài có thể khiến DDL chờ và tạo queue cho queries khác.

### 17.8. Đổi view và function trong thứ tự sai

Dependent views/functions có thể không compile nếu base objects đã đổi trước khi compatibility layer được tạo. Lập dependency order và deploy wrapper/view trước khi chuyển consumer.

### 17.9. Backfill một transaction quá lớn

Một UPDATE toàn bảng có thể tạo WAL lớn, bloat, replication lag và lock/latency. Chia batches, commit thường xuyên và theo dõi progress.

### 17.10. Không kiểm tra RLS và trigger

Query superuser có thể chạy thành công trong khi application role bị policy/trigger chặn. Test bằng đúng role và DML paths.

---

## 18. Bài lab: rename column và view dependency

Thực hiện trên database lab. Không đổi schema production để quan sát dependency.

### 18.1. Tạo table và views

~~~sql
CREATE SCHEMA IF NOT EXISTS schema_change_lab;

CREATE TABLE schema_change_lab.people (
    person_id bigint PRIMARY KEY,
    full_name text NOT NULL
);

INSERT INTO schema_change_lab.people
VALUES
    (1, 'An Nguyen'),
    (2, 'Binh Tran');

CREATE VIEW schema_change_lab.people_v1 AS
SELECT person_id, full_name
FROM schema_change_lab.people;

CREATE VIEW schema_change_lab.people_v1_report AS
SELECT person_id, upper(full_name) AS normalized_name
FROM schema_change_lab.people_v1;
~~~

### 18.2. Kiểm tra definitions

~~~sql
SELECT
    schemaname,
    viewname,
    definition
FROM pg_views
WHERE schemaname = 'schema_change_lab'
ORDER BY viewname;
~~~

### 18.3. Rename base column

~~~sql
ALTER TABLE schema_change_lab.people
RENAME COLUMN full_name TO display_name;
~~~

### 18.4. Test view output

~~~sql
SELECT * FROM schema_change_lab.people_v1;
SELECT * FROM schema_change_lab.people_v1_report;
~~~

Quan sát view vẫn trả output name cũ theo definition. Kiểm tra direct query vào people.full_name sẽ không còn resolve.

### 18.5. Rename view output

~~~sql
ALTER VIEW schema_change_lab.people_v1
RENAME COLUMN full_name TO display_name;
~~~

Kiểm tra dependent view people_v1_report và điều chỉnh nếu cần. Thử query cả hai views sau migration.

### 18.6. Xem dependencies

Chạy query pg_depend/pg_rewrite ở phần 5.4 với schema/table/column của lab. Đối chiếu direct dependent views.

---

## 19. Bài lab: function dependency và DROP COLUMN

### 19.1. Tạo function string-body

~~~sql
CREATE FUNCTION schema_change_lab.person_name(p_id bigint)
RETURNS text
LANGUAGE sql
AS $$
    SELECT display_name
    FROM schema_change_lab.people
    WHERE person_id = p_id
$$;
~~~

### 19.2. Tạo PL/pgSQL function

~~~sql
CREATE FUNCTION schema_change_lab.person_name_plpgsql(p_id bigint)
RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    v_name text;
BEGIN
    SELECT display_name
    INTO v_name
    FROM schema_change_lab.people
    WHERE person_id = p_id;

    RETURN v_name;
END;
$$;
~~~

### 19.3. Test functions

~~~sql
SELECT schema_change_lab.person_name(1);
SELECT schema_change_lab.person_name_plpgsql(1);
~~~

### 19.4. Search function source

~~~sql
SELECT
    p.oid::regprocedure AS function_signature,
    l.lanname,
    p.prosrc
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
JOIN pg_language AS l
    ON l.oid = p.prolang
WHERE n.nspname = 'schema_change_lab'
  AND p.prosrc ILIKE '%display_name%';
~~~

### 19.5. Thử DROP RESTRICT trong lab riêng

Tạo một view phụ thuộc vào display_name rồi thử DROP COLUMN RESTRICT. Quan sát PostgreSQL báo dependency. Sau đó drop/recreate view theo kế hoạch rồi thử lại.

Không dùng CASCADE trước khi đã ghi lại mọi dependent definitions. Function body dạng string có thể không chặn DROP dù vẫn chứa tên column; test function sau drop để thấy lỗi runtime nếu còn tham chiếu.

### 19.6. Dọn lab

Sau khi lưu kết quả, drop schema lab trong môi trường test. Không chạy lệnh dọn dẹp nếu schema có objects cần giữ.

---

## 20. Bài lab: expand-and-contract

### 20.1. Tạo table lab

~~~sql
CREATE TABLE schema_change_lab.contacts (
    contact_id bigint PRIMARY KEY,
    old_label text
);

INSERT INTO schema_change_lab.contacts
SELECT g, 'Contact ' || g
FROM generate_series(1, 10000) AS g;
~~~

### 20.2. Expand

~~~sql
ALTER TABLE schema_change_lab.contacts
ADD COLUMN new_label text;
~~~

### 20.3. Backfill theo batches

~~~sql
UPDATE schema_change_lab.contacts
SET new_label = old_label
WHERE new_label IS NULL
  AND contact_id BETWEEN 1 AND 1000;
~~~

Lặp lại với các ranges khác. Trong production, bổ sung dual-write/trigger trước khi backfill để writes đồng thời không bị bỏ sót.

### 20.4. Validate parity

~~~sql
SELECT
    count(*) FILTER (
        WHERE new_label IS DISTINCT FROM old_label
    ) AS mismatch_count,
    count(*) FILTER (
        WHERE new_label IS NULL
    ) AS null_count
FROM schema_change_lab.contacts;
~~~

### 20.5. Switch reader và contract

Trong lab, thay queries sang new_label. Sau khi xác nhận không còn consumers dùng old_label:

~~~sql
ALTER TABLE schema_change_lab.contacts
DROP COLUMN old_label RESTRICT;
~~~

### 20.6. Quan sát physical storage

So sánh pg_total_relation_size trước/sau DROP COLUMN. Đừng kỳ vọng size giảm ngay; thử table rewrite chỉ trong lab riêng và quan sát lock/disk impact.

---

## 21. Bài tập thực hành

Các bài tập dùng PostgreSQL lab. Không chạy DROP COLUMN CASCADE trên production chỉ để kiểm tra dependency.

### Bài 1 — Rename

Viết lệnh đổi cột full_name thành display_name trong app.people.

### Bài 2 — Drop

Viết lệnh xóa legacy_code với RESTRICT được ghi rõ.

### Bài 3 — CASCADE

CASCADE khác RESTRICT thế nào? Nêu hai loại dependent objects có thể bị xóa.

### Bài 4 — Column identity

Vì sao view vẫn có thể hoạt động sau khi base table column được rename?

### Bài 5 — View output

Sau khi rename base column, output column name của view có tự đổi không? Cách đổi output name?

### Bài 6 — pg_depend

Nêu ý nghĩa classid, objid, refobjid và refobjsubid.

### Bài 7 — attnum

attnum là gì? Vì sao dependency theo attnum vẫn hợp lệ sau rename?

### Bài 8 — Function string body

Vì sao SQL function dùng string literal body có thể không chặn DROP COLUMN RESTRICT?

### Bài 9 — SQL-standard body

SQL-standard function body khác string body ở dependency tracking như thế nào?

### Bài 10 — PL/pgSQL

Function PL/pgSQL tham chiếu old_column có thể lỗi ở thời điểm nào sau rename?

### Bài 11 — Dynamic SQL

Vì sao dynamic SQL khó được catalog dependency tracking phát hiện?

### Bài 12 — Trigger

Nêu những chỗ cần kiểm tra khi trigger function dùng OLD.old_column hoặc NEW.old_column.

### Bài 13 — Materialized view

Rename base column ảnh hưởng materialized view thế nào? Khi nào cần refresh?

### Bài 14 — Indexes

Vì sao cần inventory expression indexes trước khi drop column?

### Bài 15 — Foreign key

Vì sao phải tìm cả referencing tables khi xóa referenced key column?

### Bài 16 — RLS

Policy có thể phụ thuộc column thế nào? Test bằng role nào?

### Bài 17 — DROP storage

DROP COLUMN có trả disk space cho filesystem ngay không?

### Bài 18 — Lock

Vì sao một ALTER TABLE rename/drop nhanh vẫn có thể gây downtime?

### Bài 19 — lock_timeout

lock_timeout khác statement_timeout như thế nào?

### Bài 20 — Expand-contract

Nêu các giai đoạn thêm new column, dual-write, backfill, switch reader và drop old column.

### Bài 21 — Backfill

Vì sao nên chia backfill thành batches?

### Bài 22 — Parity

Viết query đếm rows có new_value khác old_value, bao gồm cả NULL semantics.

### Bài 23 — View compatibility

Khi nào nên dùng view alias để giữ old column name cho consumers?

### Bài 24 — Rollback

Vì sao rollback dễ hơn trước khi drop old column? Sau drop cần phương án nào?

### Bài 25 — CASCADE review

Trước khi dùng CASCADE cần thu thập và review những thông tin gì?

### Bài 26 — Query telemetry

pg_stat_statements có thể giúp tìm old column usage thế nào? Giới hạn của nó là gì?

### Bài 27 — Prepared statements

Rename/drop có thể ảnh hưởng prepared statements/application pools như thế nào?

### Bài 28 — Multi-team ownership

Một column được 3 services, 2 reports và 1 trigger sử dụng. Cần quản lý migration ra sao?

### Bài 29 — DDL rollout

Nêu một trình tự migration rename column với rolling deployment không downtime dài.

### Bài 30 — Incident tổng hợp

DROP COLUMN RESTRICT thành công nhưng một PL/pgSQL function lỗi undefined_column khi chạy đêm. Giải thích vì sao catalog không chặn và cách ngăn tái diễn.

---

## 22. Lời giải — bài 1 đến 15

### Bài 1 — Rename

~~~sql
ALTER TABLE app.people
RENAME COLUMN full_name TO display_name;
~~~

### Bài 2 — Drop

~~~sql
ALTER TABLE app.people
DROP COLUMN legacy_code RESTRICT;
~~~

### Bài 3 — CASCADE

RESTRICT từ chối drop nếu có dependency được catalog ghi nhận cần được giữ. CASCADE drop object được chỉ định và các dependent objects theo dependency graph. Ví dụ view và rule phụ thuộc có thể bị drop; views phụ thuộc tiếp vào chúng cũng có thể bị ảnh hưởng.

### Bài 4 — Column identity

View query tree lưu reference tới relation/column identity, thường qua attnum. Rename chỉ đổi tên hiển thị của column, không tạo column identity mới, nên view có thể tiếp tục tham chiếu đúng cột.

### Bài 5 — View output

Không. Output column của view là contract riêng và có thể giữ tên cũ. Dùng ALTER VIEW ... RENAME COLUMN để đổi tên output column, sau đó migrate consumers của view.

### Bài 6 — pg_depend

classid xác định catalog chứa dependent object; objid là OID object đó; refobjid là OID object được tham chiếu; refobjsubid xác định sub-object/column được tham chiếu.

### Bài 7 — attnum

attnum là attribute number của column trong relation. Rename không đổi attnum, nên dependency theo column identity tiếp tục hợp lệ dù attname thay đổi.

### Bài 8 — Function string body

Body dạng string được lưu như source text và không được parse đầy đủ thành dependency records như SQL-standard body. PostgreSQL có thể không biết body chứa identifier column nào; function chỉ lỗi khi chạy sau DROP/RENAME.

### Bài 9 — SQL-standard body

SQL-standard body được parse tại function definition time, nên PostgreSQL có thể ghi nhận dependencies tới referenced objects. String body truyền thống không có cùng mức tracking cho references trong body.

### Bài 10 — PL/pgSQL

Function có thể lỗi khi branch chứa SQL dùng old_column được thực thi hoặc khi statement được compile/replan sau schema change. Vì body references thường không được ghi nhận như view dependencies, DROP có thể thành công trước khi runtime error xuất hiện.

### Bài 11 — Dynamic SQL

Tên relation/column được ghép thành text ở runtime. Catalog không thể biết chắc identifier cuối cùng từ source string; cần source search, allowlist và runtime tests.

### Bài 12 — Trigger

Kiểm tra trigger event definitions, UPDATE OF column list, OLD/NEW field references, trigger function source, dynamic SQL, application side effects và các DML paths kích hoạt trigger.

### Bài 13 — Materialized view

Materialized view có dependency tới source query objects và có thể tiếp tục tham chiếu column identity sau rename. Dữ liệu materialized không tự cập nhật khi base rows thay đổi; chạy REFRESH theo policy. Nếu đổi output schema, có thể cần version/recreate.

### Bài 14 — Indexes

Expression/partial indexes có thể dùng column trong key hoặc predicate. Drop column có thể làm mất index liên quan; phải biết workload nào phụ thuộc index và chuẩn bị index replacement nếu cần.

### Bài 15 — Foreign key

Column được referenced có thể được nhiều child tables tham chiếu. Phải inventory foreign keys ở cả referenced và referencing sides, xác định business integrity và thứ tự migration.

---

## 23. Lời giải — bài 16 đến 30

### Bài 16 — RLS

Policy USING/WITH CHECK có thể tham chiếu column để quyết định row visibility và quyền ghi. Test bằng application roles thực tế với row-level security bật, không chỉ bằng superuser.

### Bài 17 — DROP storage

Không. Column bị đánh dấu dropped; existing tuples có thể vẫn chứa bytes cũ. Space được thu hồi dần khi rows được cập nhật hoặc qua table rewrite. VACUUM thường không nhất thiết trả ngay space cho filesystem.

### Bài 18 — Lock

RENAME/DROP cần lock mạnh trên table. Nếu transaction khác giữ conflicting lock, DDL chờ; lock queue có thể làm queries mới chờ theo. DDL metadata nhanh vẫn có thể tạo latency/downtime.

### Bài 19 — lock_timeout

lock_timeout giới hạn thời gian chờ lấy lock. statement_timeout giới hạn tổng thời gian statement chạy, bao gồm cả thời gian chờ lock và thực thi.

### Bài 20 — Expand-contract

Thêm column mới; deploy dual-write/trigger; backfill theo batches; validate parity; chuyển readers; dừng old writes; chờ hết old consumers; drop old column bằng RESTRICT; gỡ compatibility layer.

### Bài 21 — Backfill

Batches giảm transaction size, WAL burst, lock duration, replication lag và khả năng tạo bloat. Có thể commit/retry từng range và theo dõi progress.

### Bài 22 — Parity

~~~sql
SELECT count(*)
FROM app.people
WHERE new_value IS DISTINCT FROM old_value;
~~~

IS DISTINCT FROM xử lý NULL semantics, coi NULL/NULL là bằng nhau và NULL/value là khác nhau.

### Bài 23 — View compatibility

Dùng khi nhiều consumers cần schema contract ổn định và có thể truy cập qua view thay vì base table. View alias có thể giữ output column name cũ trong khi table dùng tên mới. Nó không bảo vệ direct table access.

### Bài 24 — Rollback

Trước drop, old column vẫn còn dữ liệu nên có thể chuyển reader/writer về schema cũ hoặc tiếp tục dual-write. Sau drop, cần re-add/backfill, restore từ backup/PITR, audit/event history hoặc forward migration.

### Bài 25 — CASCADE review

Thu thập dependency graph, object definitions, owners, grants, materialized data/refresh requirements, indexes/constraints, application/report consumers, rollback scripts và sign-off. Xác định tất cả object sẽ bị drop đệ quy.

### Bài 26 — Query telemetry

pg_stat_statements có thể tìm query texts/queryids dùng tên cũ và tần suất/call counts theo retention/reset window. Nó không lưu mọi statement history, không thấy query chưa được ghi nhận và không phát hiện mọi dynamic SQL/external source.

### Bài 27 — Prepared statements

Schema change có thể làm cached plans bị invalidation/replan. Khi statement được parse lại, SQL text dùng old column name có thể lỗi. Recycle/drain pools nếu cần và test thực tế sau migration.

### Bài 28 — Multi-team ownership

Lập consumer inventory với owner cho 3 services, 2 reports và trigger. Thông báo deprecation, tạo compatibility window, cập nhật từng consumer, dual-write/backfill nếu cần, theo dõi usage, nhận sign-off rồi mới contract/drop. Trigger function cần sửa/test riêng.

### Bài 29 — DDL rollout

Thêm column mới hoặc view alias; deploy code tương thích cả cũ/mới; dual-write; backfill; validate; switch readers theo service; stop old writes; theo dõi zero usage đủ lâu; drop old column bằng RESTRICT trong window ngắn với lock_timeout; xác minh và monitor.

### Bài 30 — Incident tổng hợp

DROP COLUMN RESTRICT thành công vì body reference trong PL/pgSQL source thường không được ghi nhận như dependency column. Khi function chạy, SQL được parse/replan và không tìm thấy identifier đã drop. Sửa function body, test mọi branches/trigger callers, thêm source search và function tests vào migration pipeline, theo dõi query/function errors và yêu cầu owner sign-off trước contract phase.

---

## 24. Checklist triển khai

### Trước rename/drop
- [ ] Xác nhận schema/table/column đúng.
- [ ] Xác định business meaning và data retention.
- [ ] Inventory pg_depend và direct dependent objects.
- [ ] Kiểm tra views/materialized views/rules.
- [ ] Search SQL-standard, string-body và PL/pgSQL functions.
- [ ] Kiểm tra dynamic SQL và trigger OLD/NEW references.
- [ ] Inventory indexes, constraints, foreign keys, generated columns và RLS policies.
- [ ] Search application/ORM/BI/ETL/report consumers.
- [ ] Xác định owners, deployment order và rollback path.
- [ ] Chạy staging rehearsal với lock timeout.

### Trước contract/drop
- [ ] Old column usage bằng zero trong observation window đủ dài.
- [ ] Tất cả application instances/background jobs đã chuyển.
- [ ] Dual-write/backfill parity đạt.
- [ ] Views/functions/triggers/policies đã được cập nhật và test.
- [ ] Dependency graph được review.
- [ ] Dùng RESTRICT trước; không dùng CASCADE khi chưa sign-off.
- [ ] Backup/PITR/restore path đã xác nhận.
- [ ] Maintenance window, lock_timeout và decision owner đã rõ.

### Sau migration
- [ ] Schema và column metadata đúng.
- [ ] View output names/types đúng.
- [ ] Functions/procedures/triggers chạy thành công.
- [ ] Indexes/constraints/foreign keys hợp lệ.
- [ ] Application smoke/regression tests đạt.
- [ ] Query errors/undefined_column không tăng.
- [ ] Data parity/business invariants đạt.
- [ ] Compatibility objects được gỡ đúng thời điểm.
- [ ] Migration record và runbook được cập nhật.

---

## 25. Tài liệu tham khảo PostgreSQL

Ưu tiên tài liệu đúng major version:

- [PostgreSQL — ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html): RENAME COLUMN, DROP COLUMN, RESTRICT/CASCADE và lock behavior.
- [PostgreSQL — Dependency Tracking](https://www.postgresql.org/docs/current/ddl-depend.html): dependency rules và DROP behavior.
- [PostgreSQL — System Catalogs: pg_depend](https://www.postgresql.org/docs/current/catalog-pg-depend.html): dependency records.
- [PostgreSQL — System Catalogs: pg_attribute](https://www.postgresql.org/docs/current/catalog-pg-attribute.html): relation columns và attnum.
- [PostgreSQL — CREATE VIEW](https://www.postgresql.org/docs/current/sql-createview.html): view definitions và replace constraints.
- [PostgreSQL — CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html): function body syntax và SQL-standard body.
- [PostgreSQL — ALTER VIEW](https://www.postgresql.org/docs/current/sql-alterview.html): rename view output columns.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): table locks và conflicts.

Các trang /current/ có thể trỏ tới major version mới hơn. Kiểm tra syntax, catalog columns và function body behavior trên phiên bản đang vận hành.

---

## 26. Tổng kết

Đổi tên và xóa cột là schema changes có thể ảnh hưởng nhiều consumers. PostgreSQL dependency tracking bảo vệ nhiều object references được lưu trong catalogs, nhưng không thay thế việc kiểm tra function source, dynamic SQL, application code, reports và external jobs.

Các nguyên tắc cần nhớ:

1. RENAME COLUMN đổi tên column hiện hữu, không copy dữ liệu sang column mới.
2. View có thể tiếp tục hoạt động sau base column rename vì dependency theo column identity.
3. View output column name là contract riêng và không tự đổi theo base column.
4. DROP COLUMN mặc định RESTRICT; CASCADE có thể drop cả dependency chain.
5. Indexes/constraints nội bộ table có thể được tự xử lý khi drop column; vẫn phải inventory để biết workload impact.
6. pg_depend và pg_attribute giúp kiểm tra direct dependencies bằng relation OID và attnum.
7. SQL-standard function body có dependency tracking tốt hơn string body truyền thống.
8. PL/pgSQL và dynamic SQL có thể chứa references không được catalog phát hiện; runtime errors có thể xuất hiện sau DROP.
9. Trigger definitions, OLD/NEW references, policies, generated expressions và foreign keys cần được xem xét.
10. DROP COLUMN không nhất thiết trả disk space ngay; existing tuples có thể giữ bytes cũ.
11. RENAME/DROP cần lock mạnh; dùng lock_timeout và transaction ngắn.
12. Expand-and-contract giúp rolling deployments và nhiều consumers cùng tồn tại.
13. Dual-write/backfill cần nguồn authoritative và conflict rules rõ ràng.
14. Chỉ drop sau khi old usage bằng zero đủ lâu và owner sign-off.
15. Ưu tiên DROP RESTRICT; chỉ dùng CASCADE khi dependency graph đã được review.
16. Rollback sau DROP cần restore/rebuild data hoặc forward migration; không thể đơn giản rename lại.
17. Kiểm tra bằng application role và mọi function/view paths, không chỉ superuser smoke test.

Quy trình tổng quát: **inventory consumers → inspect catalog dependencies → design compatibility window → update views/functions/triggers → dual-write/backfill nếu cần → validate parity → switch readers/writers → observe zero old usage → DROP COLUMN RESTRICT → verify and monitor**.
