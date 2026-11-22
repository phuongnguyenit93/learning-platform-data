# Kiểm thử ràng buộc, NULL, múi giờ và ranh giới kiểu dữ liệu

Kiểm thử database không chỉ xác nhận rằng một câu lệnh SQL chạy thành công. Một schema đúng phải từ chối dữ liệu không hợp lệ, chấp nhận dữ liệu hợp lệ ở các ranh giới, xử lý NULL theo đúng semantics của SQL, lưu thời điểm nhất quán qua múi giờ và không làm tràn hoặc làm tròn dữ liệu ngoài ý muốn. Những lỗi này thường xuất hiện ở các giá trị ít gặp: chuỗi rỗng, NULL, ngày nhuận, thời điểm chuyển DST, số ngay sát giới hạn kiểu, số thập phân có nhiều chữ số, chuỗi nhiều byte hoặc hai transaction cùng ghi một khóa.

Trong PostgreSQL, constraint được thực thi ở server và bảo vệ dữ liệu bất kể dữ liệu đến từ ứng dụng, batch job, import hay SQL console. Tuy nhiên, constraint chỉ đúng khi được thiết kế theo business rule và được kiểm thử với cả giá trị hợp lệ, không hợp lệ, NULL, biên dưới, biên trên và thao tác đồng thời.

Quy trình kiểm thử trong bài này xoay quanh bốn nhóm:

1. **Constraints:** NOT NULL, CHECK, UNIQUE, PRIMARY KEY, FOREIGN KEY, exclusion và deferrable constraints.
2. **NULL:** three-valued logic, NULL trong UNIQUE/FK/CHECK, NULL trong expressions, arrays và JSON.
3. **Time:** date/time/timestamp/timestamptz, UTC, timezone conversion, DST gaps/folds và interval.
4. **Type boundaries:** integer/numeric/floating-point, text/byte length, date/time ranges, casts, rounding và overflow.

Bài thuộc chương **Kiểm thử** của module *Database Engine Relational PostgreSQL*. Mục tiêu là thiết kế test cases có thể chạy lặp lại, giải thích được vì sao một input phải được chấp nhận hoặc từ chối và phát hiện những lỗi chỉ xuất hiện ở boundary hoặc concurrency.

Sau bài học, bạn có thể:

- Xây dựng test matrix cho từng constraint.
- Phân biệt SQL NULL, chuỗi rỗng, zero và JSON null.
- Dự đoán kết quả của biểu thức TRUE/FALSE/UNKNOWN.
- Kiểm thử UNIQUE với NULL và NULLS NOT DISTINCT.
- Kiểm thử FOREIGN KEY với NULL và composite keys.
- Kiểm thử deferred constraints ở cuối transaction.
- Kiểm thử timezone conversion và DST transitions.
- Chọn timestamp type đúng cho instant, local time và calendar date.
- Kiểm tra overflow, rounding, precision/scale và text length.
- Dùng transaction/savepoint để cô lập expected errors.
- Kiểm tra race conditions bằng hai sessions.
- Tổ chức test SQL và pgTAP thành regression suite.

---

## 1. Nguyên tắc kiểm thử dữ liệu

### 1.1. Test business rule tại database boundary

Ứng dụng có thể validate input trước khi gửi SQL, nhưng validation ở application layer không thay thế database constraints. Nhiều writers có thể cùng truy cập database; một import script hoặc service khác có thể bỏ qua application validation.

Ví dụ, ứng dụng kiểm tra email chưa tồn tại rồi mới INSERT. Hai requests đồng thời có thể cùng đọc thấy email chưa tồn tại và cùng INSERT. UNIQUE constraint là lớp bảo vệ cuối cùng để chỉ một transaction thành công.

### 1.2. Phân biệt test chấp nhận và test từ chối

Mỗi rule cần ít nhất hai nhóm:

- **Positive test:** giá trị hợp lệ được lưu và đọc lại đúng.
- **Negative test:** giá trị không hợp lệ bị từ chối với constraint/error mong đợi.

Một test chỉ kiểm tra câu lệnh INSERT thành công chưa đủ. Cần xác nhận dữ liệu được lưu đúng representation, không bị truncate, round hoặc timezone-shift ngoài ý muốn.

### 1.3. Kiểm thử boundary values

Với mỗi kiểu/rule, xác định:

- Giá trị nhỏ nhất hợp lệ.
- Giá trị lớn nhất hợp lệ.
- Giá trị ngay dưới minimum.
- Giá trị ngay trên maximum.
- NULL nếu cột/rule cho phép.
- Empty string/empty array/empty range nếu có ý nghĩa.
- Giá trị lặp lại hoặc xung đột.
- Giá trị có precision/length sát giới hạn.

Ví dụ CHECK quantity BETWEEN 1 AND 100 cần test 0, 1, 2, 99, 100, 101 và NULL. Đừng chỉ test một giá trị bình thường như 10.

### 1.4. Xác định layer đang được test

Một test database có thể kiểm tra nhiều lớp:

| Layer | Câu hỏi |
|---|---|
| Parser/type input | Literal có được parse thành type không? |
| Cast/conversion | Chuyển đổi có đúng và không mất dữ liệu? |
| Constraint | Database có chấp nhận/từ chối đúng không? |
| Transaction | Lỗi có rollback đúng scope không? |
| Concurrency | Hai transactions đồng thời có vi phạm invariant không? |
| Client/driver | Giá trị gửi/nhận có giữ đúng timezone/precision không? |

Khi test fail, tách các layer để tìm nguyên nhân. Ví dụ timestamp bị lệch có thể do session TimeZone, driver serialization hoặc application đã chuyển instant sai trước khi gửi SQL.

### 1.5. Dùng fixture độc lập và test có thể lặp lại

Test nên tự tạo dữ liệu cần thiết, không phụ thuộc thứ tự chạy test khác. Dùng schema/database test riêng, transaction rollback hoặc fixture setup/teardown. Tránh dựa vào sequence value cụ thể nếu sequence không được reset trong fixture.

### 1.6. Kiểm tra SQLSTATE và constraint name

Negative test nên xác nhận loại lỗi, không chỉ xác nhận “có exception”. PostgreSQL có SQLSTATE ổn định hơn message text. Ví dụ:

| Lỗi | SQLSTATE |
|---|---|
| not_null_violation | 23502 |
| foreign_key_violation | 23503 |
| unique_violation | 23505 |
| check_violation | 23514 |
| exclusion_violation | 23P01 |
| numeric_value_out_of_range | 22003 |
| invalid_datetime_format | 22007 |
| datetime_field_overflow | 22008 |

Tên constraint giúp test rõ ràng hơn khi một table có nhiều constraints cùng loại. Không phụ thuộc vào nguyên văn error message nếu không cần thiết.

---

## 2. Chuẩn bị môi trường test

### 2.1. Xác nhận server và session settings

Một số kết quả phụ thuộc server version, collation, timezone database và session settings. Ghi lại môi trường:

```sql
SELECT
    version(),
    current_setting('server_version') AS server_version,
    current_setting('TimeZone') AS timezone,
    current_setting('DateStyle') AS date_style,
    current_setting('IntervalStyle') AS interval_style,
    current_setting('lc_numeric') AS lc_numeric;
```

Kiểm tra encoding và collation:

```sql
SHOW server_encoding;
SHOW client_encoding;

SELECT
    datname,
    pg_encoding_to_char(encoding) AS encoding,
    datcollate,
    datctype
FROM pg_database
WHERE datname = current_database();
```

### 2.2. Dùng schema test riêng

```sql
CREATE SCHEMA IF NOT EXISTS test_constraints;
SET search_path = test_constraints, public;
```

Trong test automation, nên schema-qualify object names hoặc đặt search_path rõ ràng. Không để test vô tình dùng table/function cùng tên trong schema khác.

### 2.3. Transaction và savepoint

Với test SQL thủ công, savepoint giúp tiếp tục sau một statement expected-to-fail:

```sql
BEGIN;

SAVEPOINT before_invalid_insert;
INSERT INTO test_constraints.accounts(account_id, balance)
VALUES (1, -10);

-- Sau khi quan sát lỗi, rollback tới savepoint:
ROLLBACK TO SAVEPOINT before_invalid_insert;

-- Tiếp tục các assertions khác:
SELECT count(*) FROM test_constraints.accounts;

ROLLBACK;
```

Khi statement lỗi trong transaction, transaction chuyển sang aborted state cho tới khi rollback hoặc rollback tới savepoint. Một harness tự động thường bắt exception ở client và rollback transaction tương ứng.

### 2.4. Test database không phải production

Negative tests cố ý tạo constraint violations, locks và transaction aborts. Chạy trong database test có fixture riêng. Không thử nghiệm bằng cách chèn dữ liệu giả vào bảng production rồi xóa sau.

---

## 3. Kiểm thử NOT NULL và CHECK constraints

### 3.1. NOT NULL

NOT NULL bảo đảm một cột không chứa SQL NULL:

```sql
CREATE TABLE test_constraints.products (
    product_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text NOT NULL,
    price numeric(12,2) NOT NULL
);
```

Test các trường hợp:

| Input | Kết quả mong đợi |
|---|---|
| sku = 'A-100', price = 10.00 | Chấp nhận |
| sku = NULL | Từ chối |
| price = NULL | Từ chối |
| sku = '', price = 0 | NOT NULL chấp nhận; rule khác quyết định |
| sku = '   ', price = 0 | NOT NULL chấp nhận; rule khác quyết định |

NOT NULL không đồng nghĩa với non-empty. Nếu empty string không hợp lệ, thêm CHECK:

```sql
ALTER TABLE test_constraints.products
ADD CONSTRAINT products_sku_not_blank
CHECK (length(btrim(sku)) > 0);
```

Với text chứa whitespace Unicode hoặc các ký tự space đặc biệt, btrim mặc định không nhất thiết loại bỏ mọi loại whitespace. Nếu business rule định nghĩa whitespace rộng hơn, cần function chuẩn hóa rõ ràng và test theo encoding/collation.

### 3.2. CHECK constraint

CHECK constraint chấp nhận row khi expression trả TRUE hoặc NULL/UNKNOWN; chỉ FALSE mới vi phạm. Đây là điểm dễ gây lỗi:

```sql
CREATE TABLE test_constraints.accounts (
    account_id bigint PRIMARY KEY,
    balance numeric(12,2),
    CONSTRAINT accounts_balance_nonnegative
        CHECK (balance >= 0)
);
```

INSERT balance = -1 bị từ chối, nhưng balance = NULL được chấp nhận vì NULL >= 0 trả UNKNOWN. Nếu balance bắt buộc phải có, cần khai báo NOT NULL riêng.

### 3.3. Test ba trạng thái của CHECK

```sql
SELECT
    (-1 >= 0) AS negative_check,
    (0 >= 0) AS zero_check,
    (NULL::numeric >= 0) AS null_check;
```

Kết quả tương ứng FALSE, TRUE và NULL. Vì vậy CHECK không tự biến UNKNOWN thành violation.

### 3.4. Kết hợp CHECK và NOT NULL

```sql
CREATE TABLE test_constraints.inventory (
    item_id bigint PRIMARY KEY,
    quantity integer NOT NULL,
    CONSTRAINT inventory_quantity_range
        CHECK (quantity BETWEEN 0 AND 100000)
);
```

Test NULL, -1, 0, 1, 100000 và 100001. Hai rule có mục đích riêng: NOT NULL cấm absence; CHECK giới hạn miền giá trị.

### 3.5. CHECK nhiều cột

```sql
CREATE TABLE test_constraints.discount (
    regular_price numeric(12,2) NOT NULL,
    sale_price numeric(12,2) NOT NULL,
    CONSTRAINT discount_price_order
        CHECK (sale_price <= regular_price),
    CONSTRAINT discount_price_nonnegative
        CHECK (sale_price >= 0 AND regular_price >= 0)
);
```

Kiểm thử:

- Giá sale bằng giá thường.
- Giá sale nhỏ hơn giá thường.
- Giá sale lớn hơn giá thường.
- Giá bằng 0.
- Giá âm.
- NULL ở từng cột.

Nếu cả hai cột NOT NULL, NULL cases bị chặn bởi NOT NULL trước khi CHECK được xét.

### 3.6. CHECK không phải cross-row constraint

CHECK nên kiểm tra row hiện tại. PostgreSQL không bảo đảm CHECK constraint có thể duy trì invariant dựa trên rows khác hoặc thay đổi theo thời gian. Ví dụ CHECK phụ thuộc vào SELECT max từ table khác không được hỗ trợ như một cách bảo đảm dữ liệu liên hàng.

Đối với invariant liên hàng, xem xét UNIQUE, FOREIGN KEY, EXCLUDE, transaction logic hoặc trigger được thiết kế cẩn thận.

### 3.7. Kiểm thử constraint hiện có

Liệt kê constraints:

```sql
SELECT
    conname,
    contype,
    convalidated,
    condeferrable,
    condeferred,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'test_constraints.inventory'::regclass
ORDER BY conname;
```

convalidated = false cho biết constraint chưa được validate trên toàn bộ dữ liệu cũ. Khi test migration, xác nhận validation hoàn tất theo kỳ vọng.

---

## 4. Kiểm thử UNIQUE và PRIMARY KEY

### 4.1. UNIQUE cơ bản

```sql
CREATE TABLE test_constraints.customer_email (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL,
    CONSTRAINT customer_email_unique UNIQUE (email)
);
```

Positive test: insert email mới. Negative test: insert cùng email lần thứ hai. Xác nhận lỗi SQLSTATE 23505 và constraint name customer_email_unique.

### 4.2. NULL trong UNIQUE mặc định

Theo mặc định, PostgreSQL xem các NULL values là distinct trong unique constraint/index. Do đó, một cột UNIQUE nullable có thể chứa nhiều NULL rows:

```sql
CREATE TABLE test_constraints.external_identity (
    identity_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider_subject text UNIQUE
);

INSERT INTO test_constraints.external_identity(provider_subject)
VALUES (NULL), (NULL);
```

Hai rows trên được chấp nhận theo mặc định. Điều này có thể phù hợp nếu NULL nghĩa là “chưa có external identity”.

### 4.3. NULLS NOT DISTINCT

Nếu business rule cho phép tối đa một row không có value, PostgreSQL hỗ trợ:

```sql
CREATE TABLE test_constraints.optional_code (
    row_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text,
    CONSTRAINT optional_code_unique
        UNIQUE NULLS NOT DISTINCT (code)
);
```

Test:

1. Insert một NULL: thành công.
2. Insert NULL thứ hai: unique violation.
3. Insert hai code khác nhau: thành công.
4. Insert code đã tồn tại: unique violation.

NULLS NOT DISTINCT là option của unique constraints/indexes trên các PostgreSQL versions hỗ trợ; kiểm tra target major trước khi dùng.

### 4.4. Composite UNIQUE

```sql
CREATE TABLE test_constraints.membership (
    tenant_id bigint NOT NULL,
    username text NOT NULL,
    CONSTRAINT membership_tenant_username_uq
        UNIQUE (tenant_id, username)
);
```

Test cùng username ở hai tenants khác nhau phải được chấp nhận; cùng tenant và username phải bị từ chối. Đây là lý do test từng cột riêng lẻ không đủ: invariant nằm trên tuple của nhiều columns.

### 4.5. Composite UNIQUE và NULL

Với UNIQUE mặc định, rows (1, NULL) và (1, NULL) có thể cùng tồn tại vì NULL được xem là distinct. Nếu cần một semantics khác, dùng NULLS NOT DISTINCT hoặc chuẩn hóa dữ liệu thành một key không nullable theo business rule.

### 4.6. PRIMARY KEY

PRIMARY KEY tương đương unique và not-null cho tập cột:

```sql
CREATE TABLE test_constraints.document_key (
    tenant_id bigint,
    document_id bigint,
    PRIMARY KEY (tenant_id, document_id)
);
```

Test duplicate composite key và NULL ở từng thành phần. PRIMARY KEY không cho phép bất kỳ thành phần nào NULL.

### 4.7. Case sensitivity và collation

UNIQUE trên text tuân theo equality semantics của type/collation/index opclass. Alice@example.test và alice@example.test có thể được xem là hai values khác nhau với collation thông thường.

Nếu business rule cần case-insensitive uniqueness, hãy định nghĩa semantics tường minh, ví dụ:

```sql
CREATE UNIQUE INDEX customer_email_lower_uq
ON test_constraints.customer_email (lower(email));
```

Test case variants, Unicode case folding và collation provider phù hợp với yêu cầu. lower() theo collation không giống mọi thuật toán Unicode normalization/case folding của application.

### 4.8. Partial unique index

```sql
CREATE TABLE test_constraints.users (
    user_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL,
    deleted_at timestamptz
);

CREATE UNIQUE INDEX users_active_email_uq
ON test_constraints.users (lower(email))
WHERE deleted_at IS NULL;
```

Test hai active users cùng email phải bị từ chối; sau khi một user được soft-delete, row active mới có thể dùng email đó. Query predicate cần tương thích với predicate của partial index để planner dùng index.

### 4.9. UNIQUE và concurrency

Không thể test uniqueness chỉ bằng một session tuần tự. Hai sessions có thể cùng kiểm tra “không tồn tại” rồi cùng insert. UNIQUE index giải quyết race ở database.

Test bằng hai sessions:

1. Session A bắt đầu transaction và insert key K.
2. Session B insert cùng key K trước khi A commit.
3. Session B có thể chờ kết quả transaction A.
4. Nếu A commit, B nhận unique violation.
5. Nếu A rollback, B có thể insert thành công.

Test phải xác nhận invariant cuối cùng, không phụ thuộc timing cụ thể hoặc message text.

---

## 5. Kiểm thử FOREIGN KEY, exclusion và deferrable constraints

### 5.1. FOREIGN KEY cơ bản

```sql
CREATE TABLE test_constraints.departments (
    department_id bigint PRIMARY KEY,
    name text NOT NULL
);

CREATE TABLE test_constraints.employees (
    employee_id bigint PRIMARY KEY,
    department_id bigint,
    CONSTRAINT employees_department_fk
        FOREIGN KEY (department_id)
        REFERENCES test_constraints.departments(department_id)
);
```

Test insert employee với department_id tồn tại: thành công. Insert department_id không tồn tại: foreign key violation. Delete department đang được tham chiếu: kết quả phụ thuộc ON DELETE action.

### 5.2. NULL trong FOREIGN KEY

Mặc định MATCH SIMPLE, nếu bất kỳ thành phần nào của foreign key là NULL thì row không cần match một referenced row. Vì vậy, nullable FK có thể chứa NULL.

Nếu quan hệ bắt buộc phải tồn tại, khai báo FK column NOT NULL. FK và NOT NULL là hai rules riêng.

### 5.3. Composite foreign keys và MATCH SIMPLE

```sql
CREATE TABLE test_constraints.tenant_users (
    tenant_id bigint NOT NULL,
    user_id bigint NOT NULL,
    PRIMARY KEY (tenant_id, user_id)
);

CREATE TABLE test_constraints.audit_events (
    event_id bigint PRIMARY KEY,
    tenant_id bigint,
    user_id bigint,
    FOREIGN KEY (tenant_id, user_id)
        REFERENCES test_constraints.tenant_users(tenant_id, user_id)
);
```

Với MATCH SIMPLE, nếu tenant_id hoặc user_id là NULL, FK check được bỏ qua. Điều này có thể cho phép trạng thái partial-null mà business rule không muốn.

### 5.4. MATCH FULL

MATCH FULL yêu cầu tất cả các FK columns NULL hoặc tất cả non-NULL và match referenced row:

```sql
ALTER TABLE test_constraints.audit_events
ADD CONSTRAINT audit_events_tenant_user_fk
FOREIGN KEY (tenant_id, user_id)
REFERENCES test_constraints.tenant_users(tenant_id, user_id)
MATCH FULL;
```

Test:

- (NULL, NULL): chấp nhận.
- (10, 20) có parent: chấp nhận.
- (10, 20) không có parent: từ chối.
- (10, NULL): từ chối.
- (NULL, 20): từ chối.

Không thể dùng MATCH PARTIAL trong PostgreSQL.

### 5.5. ON DELETE và ON UPDATE

Các actions phổ biến:

| Action | Ý nghĩa |
|---|---|
| NO ACTION | Báo lỗi nếu constraint vẫn vi phạm khi kiểm tra |
| RESTRICT | Từ chối thao tác tham chiếu ngay, không cho trì hoãn theo cách NO ACTION có thể |
| CASCADE | Xóa/cập nhật rows con tương ứng |
| SET NULL | Đặt FK columns thành NULL |
| SET DEFAULT | Đặt FK columns về default |

Test từng action ở cả parent delete và parent key update. Với SET NULL/SET DEFAULT, kiểm tra thêm NOT NULL, CHECK và default của child table; action có thể vẫn fail nếu trạng thái sau update vi phạm rule khác.

### 5.6. Deferrable constraints

Một số constraints có thể trì hoãn kiểm tra tới cuối transaction:

```sql
CREATE TABLE test_constraints.nodes (
    node_id integer PRIMARY KEY,
    parent_id integer,
    CONSTRAINT nodes_parent_fk
        FOREIGN KEY (parent_id)
        REFERENCES test_constraints.nodes(node_id)
        DEFERRABLE INITIALLY DEFERRED
);
```

Điều này cho phép transaction tạo/cập nhật nhiều rows mà intermediate state tạm thời vi phạm FK, miễn là cuối transaction hợp lệ.

### 5.7. SET CONSTRAINTS

```sql
BEGIN;
SET CONSTRAINTS nodes_parent_fk DEFERRED;

INSERT INTO test_constraints.nodes(node_id, parent_id)
VALUES (2, 1);

INSERT INTO test_constraints.nodes(node_id, parent_id)
VALUES (1, NULL);

SET CONSTRAINTS nodes_parent_fk IMMEDIATE;
COMMIT;
```

Lệnh SET CONSTRAINTS ... IMMEDIATE kiểm tra các deferred violations ngay tại thời điểm chuyển mode. Test cả commit-time failure và explicit SET CONSTRAINTS failure.

### 5.8. UNIQUE deferrable

PostgreSQL hỗ trợ deferrable UNIQUE constraints:

```sql
CREATE TABLE test_constraints.display_order (
    item_id integer PRIMARY KEY,
    position integer,
    CONSTRAINT display_order_position_uq
        UNIQUE (position)
        DEFERRABLE INITIALLY DEFERRED
);
```

Có thể dùng deferrable uniqueness khi hoán đổi positions trong một transaction. Tuy nhiên, deferrable unique constraints không thể được dùng làm ON CONFLICT arbiters; kiểm tra semantics của ứng dụng trước khi chọn.

### 5.9. Exclusion constraints

Exclusion constraint đảm bảo với mọi cặp rows, ít nhất một operator comparison được chỉ định phải trả FALSE hoặc NULL. Nó thường được dùng để ngăn overlap:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE test_constraints.reservations (
    room_id integer NOT NULL,
    during tstzrange NOT NULL,
    EXCLUDE USING gist (
        room_id WITH =,
        during WITH &&
    )
);
```

Test cùng room với khoảng overlap: từ chối. Cùng room nhưng khoảng liền kề, không overlap: chấp nhận nếu bounds được định nghĩa phù hợp. Khác room với cùng khoảng: chấp nhận.

### 5.10. Exclusion và NULL

Exclusion semantics có thể cho phép pair khi một operator comparison trả NULL. Nếu room_id hoặc range có thể NULL, cần test rõ và thường đặt NOT NULL nếu business rule yêu cầu giá trị. Không cho rằng exclusion tự thay thế NOT NULL.

### 5.11. Exclusion và concurrency

Hai sessions cùng đặt một resource/time range có thể chạy đồng thời. Exclusion constraint phải đảm bảo không có hai conflicting reservations cùng commit. Test bằng hai sessions và xác nhận một transaction bị từ chối hoặc chờ tùy interleaving.

---

## 6. NULL và three-valued logic

### 6.1. NULL không phải một giá trị thông thường

NULL biểu diễn absence/unknown theo SQL semantics. Nó khác:

- Zero: số 0 là giá trị số hợp lệ.
- Empty string: text có độ dài zero.
- Empty array: array không có elements.
- Empty range: range rỗng.
- JSON null: một JSON value có tên null.

Ứng dụng thường gộp các khái niệm này thành một “blank” nhưng database phân biệt chúng.

### 6.2. TRUE, FALSE và UNKNOWN

SQL boolean expressions có ba kết quả logic. So sánh NULL với giá trị bằng các operators thông thường trả UNKNOWN:

```sql
SELECT
    NULL = NULL AS eq,
    NULL <> NULL AS ne,
    NULL < 10 AS less_than,
    NULL IS NULL AS is_null,
    NULL IS NOT NULL AS is_not_null;
```

Ba biểu thức đầu trả NULL; hai biểu thức IS NULL/IS NOT NULL trả TRUE/FALSE.

### 6.3. AND truth table

| A | B | A AND B |
|---|---|---|
| TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE |
| TRUE | NULL | NULL |
| FALSE | NULL | FALSE |
| NULL | NULL | NULL |

### 6.4. OR truth table

| A | B | A OR B |
|---|---|---|
| TRUE | NULL | TRUE |
| FALSE | NULL | NULL |
| NULL | NULL | NULL |
| FALSE | FALSE | FALSE |
| TRUE | FALSE | TRUE |

### 6.5. NOT

NOT TRUE = FALSE; NOT FALSE = TRUE; NOT NULL = NULL. Vì vậy điều kiện WHERE chỉ giữ rows có predicate TRUE. FALSE và UNKNOWN đều không được chọn.

### 6.6. WHERE và NULL

```sql
SELECT *
FROM test_constraints.products
WHERE price > 0;
```

Rows có price NULL không được trả về vì predicate là UNKNOWN. Nếu muốn giữ NULL rows, viết rõ:

```sql
SELECT *
FROM test_constraints.products
WHERE price > 0 OR price IS NULL;
```

### 6.7. IS DISTINCT FROM

IS DISTINCT FROM và IS NOT DISTINCT FROM cung cấp comparison NULL-safe:

```sql
SELECT
    NULL IS DISTINCT FROM NULL AS same_nulls,
    NULL IS DISTINCT FROM 1 AS null_vs_value,
    1 IS NOT DISTINCT FROM 1 AS equal_values;
```

Hai NULL được xem là not distinct; NULL và non-NULL là distinct. Đây là cách hữu ích để so sánh nullable values trong tests, UPSERT logic và change detection.

### 6.8. COALESCE và NULLIF

COALESCE trả argument đầu tiên không NULL:

```sql
SELECT COALESCE(NULL::text, '', 'fallback');
```

Kết quả là empty string, không phải fallback. NULLIF trả NULL khi hai arguments bằng nhau:

```sql
SELECT NULLIF('', '') IS NULL;
```

Test các biểu thức này khi application chuyển empty strings thành NULL hoặc dùng default values.

### 6.9. NOT IN và NULL trap

```sql
SELECT 5 NOT IN (1, 2, NULL);
```

Kết quả là UNKNOWN, không phải TRUE, vì không thể kết luận 5 khác NULL. Vì vậy NOT IN với subquery có thể chứa NULL thường cho kết quả bất ngờ. NOT EXISTS với correlation predicate thường là cách biểu đạt anti-join an toàn hơn.

### 6.10. NULL trong aggregate

COUNT(*) đếm mọi rows; COUNT(column) bỏ qua NULL. SUM/AVG/MIN/MAX thường bỏ qua NULL inputs và trả NULL khi không có non-NULL input.

```sql
SELECT
    count(*) AS all_rows,
    count(price) AS rows_with_price,
    sum(price) AS total_price,
    avg(price) AS average_price
FROM test_constraints.products;
```

Test cả empty table, toàn NULL, mixed NULL/non-NULL và zero values. SUM trên empty/all-NULL input trả NULL; dùng COALESCE nếu business rule muốn zero.

### 6.11. NULL trong DISTINCT và GROUP BY

Trong GROUP BY và DISTINCT, NULLs được gom thành một nhóm/equivalence class cho mục đích loại trùng. Điều này khác với default UNIQUE semantics, nơi nhiều NULLs được phép. Test từng context riêng, không suy luận từ behavior của context khác.

### 6.12. NULL trong arrays

Array có thể là NULL, empty array hoặc chứa NULL elements:

```sql
SELECT
    NULL::integer[] AS null_array,
    ARRAY[]::integer[] AS empty_array,
    ARRAY[1, NULL, 3] AS array_with_null;
```

Các biểu thức ANY/ALL và array operators có thể tạo UNKNOWN khi NULL elements tham gia:

```sql
SELECT
    2 = ANY (ARRAY[1, NULL, 3]) AS any_result,
    2 = ALL (ARRAY[1, NULL, 3]) AS all_result;
```

Test array NULL, empty, contains NULL, duplicate elements và array dimensions.

### 6.13. SQL NULL và JSON null

JSONB có JSON null value khác SQL NULL:

```sql
SELECT
    'null'::jsonb IS NULL AS json_null_is_sql_null,
    NULL::jsonb IS NULL AS sql_null_is_sql_null,
    jsonb_typeof('null'::jsonb) AS json_value_type;
```

JSON null không phải SQL NULL. Với cột JSONB, test column SQL NULL, JSON scalar null, missing key và key có value null. JSON extraction có thể trả SQL NULL khi key không tồn tại, nên cần kiểm tra presence riêng nếu business rule phân biệt missing với explicit null.

### 6.14. NULL trong UNIQUE, FK và CHECK

Không áp dụng một semantics chung:

- UNIQUE mặc định cho phép nhiều NULLs.
- UNIQUE NULLS NOT DISTINCT xem NULLs là bằng nhau cho uniqueness.
- FOREIGN KEY MATCH SIMPLE bỏ qua check nếu có bất kỳ FK column nào NULL.
- CHECK chấp nhận expression TRUE hoặc UNKNOWN; chỉ FALSE bị từ chối.
- NOT NULL cấm SQL NULL.

Mỗi rule cần test riêng với single-column và composite cases.

---

## 7. Kiểu ngày giờ và múi giờ trong PostgreSQL

### 7.1. Chọn đúng type theo ý nghĩa dữ liệu

| Type | Ý nghĩa | Ví dụ nghiệp vụ |
|---|---|---|
| date | Ngày lịch, không có giờ/múi giờ | Ngày sinh, ngày hóa đơn |
| time | Giờ trong ngày, không có ngày/múi giờ | Giờ mở cửa |
| time with time zone | Giờ trong ngày kèm offset | Ít dùng cho dữ liệu nghiệp vụ |
| timestamp without time zone | Local date-time, không xác định instant | Giờ hẹn địa phương chưa gắn zone |
| timestamp with time zone (timestamptz) | Một instant trên timeline | Thời điểm payment/event xảy ra |
| interval | Khoảng thời gian/độ dài lịch | 2 giờ, 3 tháng |

Đừng dùng timestamp without time zone để lưu một instant toàn cầu. Đừng dùng timestamptz cho ngày sinh hoặc ngày lịch chỉ vì application có timezone.

### 7.2. timestamp without time zone

Timestamp without time zone lưu các thành phần calendar date/time, không chuyển đổi theo session TimeZone. Nếu literal có offset nhưng được ép thành timestamp without time zone, offset bị bỏ qua:

```sql
SELECT
    timestamp '2026-06-01 09:00:00' AS local_time,
    timestamp '2026-06-01 09:00:00+07' AS offset_ignored;
```

Hai literals có thể cho cùng local timestamp. Test này quan trọng vì input có vẻ chứa offset nhưng target type không giữ nó.

### 7.3. timestamptz

Timestamptz biểu diễn một instant. PostgreSQL chuyển input có offset/zone thành UTC-based internal instant; khi hiển thị, server chuyển instant sang session TimeZone.

```sql
SET TIME ZONE 'UTC';
SELECT timestamptz '2026-06-01 09:00:00+07';

SET TIME ZONE 'Asia/Ho_Chi_Minh';
SELECT timestamptz '2026-06-01 09:00:00+07';
```

Hai SELECT hiển thị cùng một instant ở hai timezone khác nhau. Giá trị lưu không đổi khi SET TIME ZONE; chỉ representation khi output thay đổi.

### 7.4. Input không có timezone cho timestamptz

Nếu input timestamptz không chứa offset hoặc zone, PostgreSQL diễn giải theo session TimeZone tại thời điểm parse:

```sql
SET TIME ZONE 'UTC';
SELECT timestamptz '2026-06-01 09:00:00';

SET TIME ZONE 'Asia/Ho_Chi_Minh';
SELECT timestamptz '2026-06-01 09:00:00';
```

Hai kết quả là hai instants khác nhau. Vì vậy, test phải kiểm soát session TimeZone và application nên gửi instant có offset rõ ràng hoặc bind một instant đã được driver biểu diễn đúng.

### 7.5. AT TIME ZONE hai chiều

AT TIME ZONE có hai semantics tùy input type:

```sql
-- Một instant được hiển thị thành local timestamp trong zone:
SELECT timestamptz '2026-06-01 02:00:00+00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh';

-- Một local timestamp được diễn giải trong zone thành instant:
SELECT timestamp '2026-06-01 09:00:00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh';
```

- Timestamptz AT TIME ZONE zone trả về timestamp without time zone.
- Timestamp without time zone AT TIME ZONE zone trả về timestamptz.

Test kiểu dữ liệu của output cùng giá trị; hai chiều không phải phép cast giống nhau.

### 7.6. TimeZone setting

```sql
SHOW TimeZone;
SELECT current_setting('TimeZone');
SELECT current_setting('TimeZone') = 'UTC';
```

TimeZone có thể được đặt ở server, database, role, connection hoặc session. Test automation nên SET TIME ZONE rõ trong từng connection thay vì dựa vào default của máy chạy test.

### 7.7. Time zone names và fixed offsets

IANA zone như Asia/Ho_Chi_Minh hoặc America/New_York có rules thay đổi theo lịch sử và DST. Fixed offset như +07 không có lịch sử/DST. Nếu nghiệp vụ cần giờ địa phương của một địa điểm, lưu zone name hoặc reference zone theo business rule; offset đơn lẻ không đủ để tái tạo mọi local-time behavior.

### 7.8. Kiểm tra timezone names

```sql
SELECT name, abbrev, utc_offset, is_dst
FROM pg_timezone_names
WHERE name IN (
    'UTC',
    'Asia/Ho_Chi_Minh',
    'America/New_York',
    'Europe/Berlin'
)
ORDER BY name;
```

Không dựa vào abbreviation mơ hồ như CST. Một abbreviation có thể đại diện cho nhiều offsets/regions; dùng IANA zone names cho logic lịch địa phương.

### 7.9. DateStyle và input ambiguity

DateStyle ảnh hưởng cách PostgreSQL diễn giải một số date strings không rõ định dạng:

```sql
SHOW DateStyle;
SET DateStyle = 'ISO, MDY';
SELECT date '01/02/2026';

SET DateStyle = 'ISO, DMY';
SELECT date '01/02/2026';
```

Tránh date strings mơ hồ trong test và application. Dùng ISO 8601 như YYYY-MM-DD hoặc typed parameters để không phụ thuộc DateStyle.

---

## 8. Kiểm thử DST: giờ bị bỏ qua và giờ lặp lại

### 8.1. DST gap

Ở nơi áp dụng daylight saving time, đồng hồ có thể nhảy qua một khoảng local time vào mùa xuân. Ví dụ một zone chuyển từ 01:59:59 sang 03:00:00; local time 02:30 không tồn tại.

Input local timestamp không mang zone vẫn có thể được lưu như một calendar value vì PostgreSQL không biết nó đại diện cho zone nào. Khi diễn giải local timestamp trong IANA zone thành timestamptz, cần test cách PostgreSQL giải quyết giờ không tồn tại.

### 8.2. DST fold

Vào mùa thu, đồng hồ có thể lùi lại, khiến một khoảng local time xuất hiện hai lần. Ví dụ 01:30 có thể tương ứng với hai instants khác nhau. Một timestamp without time zone không đủ thông tin để phân biệt hai lần xuất hiện.

### 8.3. Ví dụ America/New_York

```sql
SET TIME ZONE 'UTC';

SELECT
    timestamp '2026-03-08 02:30:00'
        AT TIME ZONE 'America/New_York' AS spring_gap,
    timestamp '2026-11-01 01:30:00'
        AT TIME ZONE 'America/New_York' AS autumn_fold;
```

Ngày cụ thể phụ thuộc lịch DST của năm. PostgreSQL áp dụng quy tắc timezone database khi diễn giải local time; với thời điểm ambiguous hoặc invalid, PostgreSQL dùng standard-time offset. Với spring gap, điều này có thể tạo instant mà khi hiển thị lại trong zone sẽ ra một local time khác với input.

### 8.4. Test hai instants trong fold

Đưa offset tường minh để phân biệt hai lần 01:30:

```sql
SELECT
    timestamptz '2026-11-01 01:30:00-04' AS first_occurrence,
    timestamptz '2026-11-01 01:30:00-05' AS second_occurrence,
    timestamptz '2026-11-01 01:30:00-04'
      <> timestamptz '2026-11-01 01:30:00-05' AS different_instants;
```

Hai giá trị khác nhau một giờ dù phần local clock text giống nhau.

### 8.5. Test round-trip

Một test quan trọng là chuyển local timestamp sang instant rồi trở lại local time:

```sql
WITH input(local_time) AS (
    VALUES
        (timestamp '2026-03-08 02:30:00'),
        (timestamp '2026-11-01 01:30:00')
)
SELECT
    local_time,
    local_time AT TIME ZONE 'America/New_York' AS instant,
    (local_time AT TIME ZONE 'America/New_York')
        AT TIME ZONE 'America/New_York' AS round_trip
FROM input;
```

Ở gap/fold, round-trip có thể không bảo toàn local timestamp ban đầu hoặc không thể xác định duy nhất instant. Test phải xác định business policy: reject nonexistent times, chọn occurrence sớm/muộn, hoặc yêu cầu user cung cấp offset.

### 8.6. Local appointment và global event

Hai loại dữ liệu cần semantics khác nhau:

- **Appointment lúc 09:00 tại clinic:** có thể lưu local date/time cộng IANA zone, vì giờ hẹn gắn với lịch địa phương.
- **Payment đã xảy ra lúc một instant:** lưu timestamptz, vì đó là điểm duy nhất trên timeline.

Với appointment, chỉ lưu timestamptz có thể làm mất ý nghĩa “09:00 local” khi timezone rules thay đổi trong tương lai. Với event instant, chỉ lưu timestamp without time zone làm mất zone/offset cần để xác định thời điểm.

### 8.7. Test timezone database updates

Timezone rules có thể thay đổi do luật pháp. Khi OS/tzdata hoặc PostgreSQL timezone data được cập nhật, test các future appointments và recurring schedules có liên quan. Phân biệt:

- Instant đã xảy ra: không được thay đổi.
- Future local appointment: có thể cần được diễn giải lại theo policy mới.
- Recurring schedule: nên giữ local time và zone, rồi tính từng occurrence theo rules hiện hành.

---

## 9. Kiểm thử date, time và interval boundaries

### 9.1. Date boundaries

Date hỗ trợ một phạm vi rộng hơn các business dates thông thường. Test domain của ứng dụng thay vì chỉ dựa vào giới hạn của PostgreSQL:

- Ngày đầu/cuối kỳ nghiệp vụ.
- Ngày nhuận 29/02.
- Ngày trước/sau ngày nhuận.
- Ngày đầu/cuối tháng.
- Ngày đầu/cuối năm.
- Giá trị vô hạn nếu application không cho phép.

```sql
SELECT
    date '2024-02-28' + 1 AS leap_day,
    date '2024-02-29' + 1 AS next_day,
    date '2026-01-31' + interval '1 month' AS month_arithmetic;
```

Lưu ý phép cộng interval month với ngày cuối tháng có quy tắc calendar, không tương đương cộng một số ngày cố định.

### 9.2. Invalid dates

```sql
SELECT date '2024-02-29';
```

Đây là ngày hợp lệ. Các giá trị như 2023-02-29 hoặc tháng 13 phải bị từ chối. Test cả leap year chia hết cho 4, century year không chia hết cho 400 và century year chia hết cho 400.

### 9.3. Time boundaries

Test:

- 00:00:00.
- 23:59:59.999999.
- Fractional seconds ở precision cao hơn target column.
- 24:00:00 nếu input format/type cho phép theo PostgreSQL.
- Leap-second input nếu ứng dụng có yêu cầu đặc biệt.

Không giả định mọi client parser và mọi timezone library xử lý các edge values giống nhau.

### 9.4. Timestamp precision

Timestamp PostgreSQL lưu microsecond resolution. Column typmod có thể giới hạn fractional precision từ 0 tới 6:

```sql
CREATE TABLE test_constraints.timestamp_precision (
    ts0 timestamp(0),
    ts3 timestamp(3),
    ts6 timestamp(6)
);

INSERT INTO test_constraints.timestamp_precision
VALUES (
    timestamp '2026-01-01 12:00:00.123456',
    timestamp '2026-01-01 12:00:00.123456',
    timestamp '2026-01-01 12:00:00.123456'
);

SELECT * FROM test_constraints.timestamp_precision;
```

Test rounding/truncation behavior ở các fractional boundaries. Đừng so sánh timestamp sau khi chuyển sang milliseconds ở application nếu database giữ microseconds.

### 9.5. Interval không phải duration cố định trong mọi trường hợp

Interval có các thành phần months, days và time. Một month không có số ngày cố định; một day theo calendar không luôn tương đương 24 elapsed hours khi áp dụng DST.

```sql
SET TIME ZONE 'America/New_York';

SELECT
    timestamptz '2026-03-07 12:00:00-05' + interval '1 day'
        AS same_local_time_next_day,
    timestamptz '2026-03-07 12:00:00-05' + interval '24 hours'
        AS twenty_four_elapsed_hours;
```

Quanh DST, hai kết quả có thể khác nhau. Nếu business rule là “cùng giờ địa phương ngày mai”, dùng calendar arithmetic với timezone rõ. Nếu là “sau đúng 24 giờ”, dùng duration semantics rõ ràng.

### 9.6. Infinity

Date/timestamp PostgreSQL hỗ trợ infinity và -infinity. Nếu application không mong đợi các giá trị này, thêm CHECK hoặc validation:

```sql
CREATE TABLE test_constraints.validity_period (
    valid_until timestamptz NOT NULL,
    CHECK (isfinite(valid_until))
);
```

Test cả finite minimum/maximum trong domain nghiệp vụ và infinity. Đừng để special values đi vào driver/client mà không có mapping rõ.

### 9.7. Half-open intervals

Đối với thời gian hiệu lực, thường dùng khoảng [start, end) — bao gồm start, không bao gồm end:

```sql
SELECT
    tstzrange(
        timestamptz '2026-01-01 00:00:00+00',
        timestamptz '2026-02-01 00:00:00+00',
        '[)'
    ) @> timestamptz '2026-02-01 00:00:00+00' AS includes_end;
```

Kết quả FALSE. Half-open intervals cho phép hai khoảng liền kề mà không overlap. Test exact start, just-before-end, exact end và zero-length ranges.

---

## 10. Kiểm thử integer và numeric boundaries

### 10.1. Integer ranges

PostgreSQL integer types có các giới hạn:

| Type | Minimum | Maximum |
|---|---:|---:|
| smallint | -32,768 | 32,767 |
| integer | -2,147,483,648 | 2,147,483,647 |
| bigint | -9,223,372,036,854,775,808 | 9,223,372,036,854,775,807 |

Test min, max, min-1 và max+1:

```sql
SELECT
    '-32768'::smallint AS smallint_min,
    '32767'::smallint AS smallint_max,
    '-2147483648'::integer AS integer_min,
    '2147483647'::integer AS integer_max,
    '-9223372036854775808'::bigint AS bigint_min,
    '9223372036854775807'::bigint AS bigint_max;
```

Thử các values ngoài phạm vi trong negative tests và xác nhận numeric_value_out_of_range (22003).

### 10.2. Arithmetic overflow

Một giá trị có thể hợp lệ trong column nhưng phép tính trên nó vẫn overflow:

```sql
SELECT 2147483647::integer + 1;
```

Test arithmetic, casts và aggregates riêng. Ví dụ SUM(integer) trả bigint, còn SUM(bigint) trả numeric trong PostgreSQL; đừng giả định aggregate giữ nguyên input type.

### 10.3. Cast từ text

Test input parser với:

- Chuỗi số hợp lệ.
- Leading/trailing whitespace.
- Dấu + và -.
- Empty string.
- Chuỗi chỉ có whitespace.
- Decimal vào integer.
- Exponent notation.
- Ký tự không phải số.
- Giá trị vượt range.

```sql
SELECT
    ' 42 '::integer,
    '+42'::integer,
    '4.2'::numeric;
```

Các cast không hợp lệ cần được kiểm tra bằng SQLSTATE phù hợp. Đừng dùng regex validation ở application thay cho việc test database parser và type conversion.

### 10.4. Numeric precision và scale

Numeric(p,s) giới hạn precision tổng thể và số digits sau decimal point. Với numeric(5,2), tối đa có 5 significant decimal digits, trong đó 2 digits sau dấu thập phân; miền số dương lớn nhất là 999.99.

```sql
CREATE TABLE test_constraints.money_amount (
    amount numeric(5,2) NOT NULL
);

INSERT INTO test_constraints.money_amount VALUES
    (-999.99),
    (-0.01),
    (0),
    (0.01),
    (999.99);
```

Test 1000.00 phải overflow. Test 1.234 để xác nhận scale handling. Numeric scale coercion có thể round input về scale của column trước khi lưu; kiểm tra giá trị đọc lại.

### 10.5. Numeric rounding

PostgreSQL numeric round ties away from zero:

```sql
SELECT
    round( 1.235::numeric, 2) AS positive_tie,
    round(-1.235::numeric, 2) AS negative_tie,
    round( 1.234::numeric, 2) AS below_tie;
```

Test cả số dương/âm, tie values và values ngay hai phía của tie. Không giả định rounding của numeric và floating-point giống nhau.

### 10.6. Numeric column scale coercion

```sql
TRUNCATE test_constraints.money_amount;

INSERT INTO test_constraints.money_amount(amount)
VALUES (12.345), (-12.345);

SELECT amount FROM test_constraints.money_amount ORDER BY amount;
```

Kết quả được coercion theo scale column. Xác định rõ business rule muốn round, reject hay giữ precision cao hơn; nếu muốn reject extra fractional digits, cần validation riêng trước khi coercion làm mất thông tin.

### 10.7. Unconstrained numeric

Numeric không khai báo precision/scale có thể lưu nhiều digits và scale lớn hơn fixed numeric(p,s). Nó phù hợp với arbitrary-precision decimal nhưng tốn storage/CPU hơn integer hoặc floating-point. Test giới hạn nghiệp vụ bằng CHECK nếu không muốn chấp nhận mọi scale.

### 10.8. Numeric special values

PostgreSQL numeric hỗ trợ NaN và trên các versions hiện đại có Infinity/-Infinity. Các special values có behavior riêng trong comparison và arithmetic; constrained numeric columns có scale không nhất thiết chấp nhận infinity. Nếu domain chỉ cho finite numbers:

```sql
CREATE TABLE test_constraints.finite_measure (
    value numeric NOT NULL,
    CHECK (value <> 'NaN'::numeric),
    CHECK (value NOT IN ('Infinity'::numeric, '-Infinity'::numeric))
);
```

Hoặc dùng isfinite cho types có function tương ứng. Xác nhận function/operator có sẵn cho type/version; viết explicit checks và test từng special value.

### 10.9. Money

Money là type locale-sensitive về input/output và có fractional precision phụ thuộc build/configuration. Nó thường không phải lựa chọn tốt cho interchange/API values vì formatting có thể phụ thuộc lc_monetary.

Nếu dùng money, test input/output dưới locale thực tế và không parse formatted money string như một decimal độc lập ở application. Với hệ thống tài chính, numeric(p,s) hoặc integer minor units thường cho contract rõ ràng hơn.

### 10.10. Identity và sequence boundaries

Identity/serial columns dựa trên sequence. Sequence có type/range, increment, min/max, cycle và cache. Test khi sequence gần giới hạn, khi increment âm, khi dùng CYCLE và khi application tự truyền identity value.

```sql
CREATE SEQUENCE test_constraints.small_sequence
    AS smallint
    START WITH 32766
    INCREMENT BY 1
    NO CYCLE;

SELECT nextval('test_constraints.small_sequence');
SELECT nextval('test_constraints.small_sequence');
-- Lần gọi tiếp theo vượt max của smallint và phải lỗi.
```

Không test sequence exhaustion trên production. Sequence values không transactional giống table rows; rollback transaction không hoàn tác nextval.

---

## 11. Kiểm thử floating-point và các kiểu số khác

### 11.1. real và double precision

Real (float4) và double precision (float8) lưu binary floating-point approximation. Nhiều decimal fractions không thể biểu diễn chính xác, ví dụ 0.1.

```sql
SELECT
    0.1::double precision + 0.2::double precision
        = 0.3::double precision AS exact_equal,
    0.1::double precision + 0.2::double precision
        AS actual_sum;
```

Test numeric equality bằng tolerance khi semantics là approximate:

```sql
SELECT abs(
    (0.1::double precision + 0.2::double precision) - 0.3
) < 1e-12 AS within_tolerance;
```

Tolerance phải dựa trên magnitude, precision và domain; một epsilon cố định không phù hợp cho mọi scale.

### 11.2. NaN

PostgreSQL có behavior đặc biệt cho NaN để hỗ trợ sorting/indexing: NaN được xem bằng NaN và lớn hơn mọi non-NaN values trong ordering của PostgreSQL. Đây khác với phép so sánh IEEE thông thường trong một số ngôn ngữ.

```sql
SELECT
    'NaN'::double precision = 'NaN'::double precision AS nan_equal,
    'NaN'::double precision > 'Infinity'::double precision AS nan_order;
```

Test NaN khi dùng UNIQUE, ORDER BY, MIN/MAX, CHECK và application serialization. Nếu domain không chấp nhận NaN, cấm tường minh.

### 11.3. Infinity

Floating-point types có thể lưu Infinity và -Infinity. Test chúng cùng finite max/min values, arithmetic và comparisons. Một validation chỉ kiểm tra value >= 0 có thể chấp nhận positive infinity.

### 11.4. So sánh numeric và float

Numeric là decimal arbitrary precision; float là approximate binary. Cast giữa chúng có thể làm tròn hoặc thay đổi representation. Không dùng float cho currency hoặc quantity cần decimal exactness.

### 11.5. Signed zero

Floating-point có +0 và -0 representations. Chúng thường so sánh bằng nhau trong PostgreSQL, nhưng có thể khác ở textual representation hoặc một số computations. Nếu application phụ thuộc dấu của zero, test riêng và xác định có cần normalize hay không.

### 11.6. Rounding và formatting

Không so sánh formatted strings thay cho numeric values. Formatting phụ thuộc locale, scale và client. Test:

- Value lưu trong database.
- Value trả qua text protocol.
- Value trả qua binary protocol nếu driver dùng.
- Value deserialize trong application.

### 11.7. Bit strings và binary values

Với bit(n), varbit, bytea, kiểm tra:

- Độ dài bit/byte.
- Empty value.
- Leading zero bits.
- Binary zero bytes.
- Hex/base64 encode/decode.
- Equality sau round-trip.

Byte length và character length là hai đại lượng khác nhau.

---

## 12. Kiểm thử text, Unicode và length boundaries

### 12.1. varchar(n) tính characters, không phải bytes

Với database UTF-8, varchar(n) giới hạn số characters theo character count, không phải số bytes. Một ký tự Unicode có thể chiếm nhiều bytes.

```sql
SELECT
    char_length('é') AS characters,
    octet_length('é') AS bytes,
    char_length('😀') AS emoji_characters,
    octet_length('😀') AS emoji_bytes;
```

Kết quả bytes phụ thuộc encoding. Trong UTF-8, các ký tự trên dùng nhiều bytes hơn một ASCII character.

### 12.2. varchar(n) boundary

```sql
CREATE TABLE test_constraints.short_text (
    value varchar(3)
);

INSERT INTO test_constraints.short_text VALUES ('abc');
```

Test đúng n characters, n+1 characters, multibyte characters và trailing spaces. Khi gán một string vượt length, PostgreSQL thường báo value too long; nếu phần dư chỉ là spaces, có trường hợp được phép bỏ phần spaces dư theo quy tắc varchar.

### 12.3. Explicit cast có thể truncate

Explicit cast sang varchar(n) có thể truncate chuỗi dài hơn n characters:

```sql
SELECT 'abcdef'::varchar(3);
```

Điều này khác với việc INSERT trực tiếp chuỗi quá dài vào varchar(3), thường bị từ chối. Test cast path và assignment path riêng để không vô tình mất dữ liệu.

### 12.4. char(n) và trailing spaces

Char(n) (bpchar) blank-pads values tới độ dài n; so sánh bỏ qua trailing spaces theo semantics của type. Varchar/text giữ trailing spaces.

```sql
SELECT
    'a'::char(3) = 'a  '::char(3) AS char_equal,
    'a'::varchar = 'a '::varchar AS varchar_equal;
```

Test trailing spaces, explicit casts, length functions và unique indexes. Tránh char(n) nếu ứng dụng cần bảo toàn chính xác trailing whitespace.

### 12.5. Unicode normalization

Hai strings có thể nhìn giống nhau nhưng byte/code-point sequences khác nhau, ví dụ ký tự có dấu được biểu diễn dạng composed hoặc base character cộng combining mark. Equality không tự động áp dụng mọi Unicode normalization forms.

Nếu business rule yêu cầu canonical equivalence, normalize ở một layer được xác định rõ hoặc dùng extension/function phù hợp; test composed/decomposed inputs và uniqueness.

### 12.6. Case folding

lower() và case-insensitive collations có semantics phụ thuộc locale/Unicode implementation. Test các ký tự có case mapping đặc biệt, không chỉ ASCII A-Z. Nếu business rule cần case-insensitive identity, định nghĩa normalization policy rõ ràng và dùng cùng policy ở mọi writers.

### 12.7. Empty string và whitespace

Test:

- Empty string.
- One ASCII space.
- Tab/newline.
- Non-breaking space.
- Unicode whitespace.
- Leading/trailing spaces.

length(text) đếm characters, octet_length(text) đếm bytes. btrim mặc định trim space characters theo behavior của PostgreSQL; nó không phải full Unicode whitespace normalization.

### 12.8. Collation và ordering

Collation ảnh hưởng comparison, sorting, pattern matching và có thể ảnh hưởng index behavior. Test case/accent ordering, locale-specific comparisons và collation provider/version được dùng trên production. Khi collation version thay đổi, kiểm tra cảnh báo mismatch và reindex theo hướng dẫn.

---

## 13. Kiểm thử domains, ranges, arrays và JSON values

### 13.1. Domain constraints

Domain có thể kết hợp NOT NULL và CHECK:

```sql
CREATE DOMAIN test_constraints.positive_amount AS numeric(12,2)
    NOT NULL
    CHECK (VALUE > 0);

CREATE TABLE test_constraints.invoice_lines (
    line_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    amount test_constraints.positive_amount
);
```

Test positive amount, zero, negative, NULL và numeric overflow. Domain NOT NULL áp dụng khi value được dùng trong domain; column cũng có thể có thêm constraints riêng.

### 13.2. Domain CHECK và UNKNOWN

CHECK trong domain cũng theo SQL three-valued logic. Nếu domain cho phép NULL và CHECK trả UNKNOWN, giá trị có thể được chấp nhận. Khi cần required value, dùng domain NOT NULL hoặc column NOT NULL theo semantics mong muốn.

### 13.3. Range boundaries

Range type phân biệt inclusive/exclusive bounds, empty ranges, unbounded bounds và normalized representations:

```sql
SELECT
    int4range(1, 5, '[)') AS half_open,
    int4range(1, 5, '[]') AS closed,
    int4range(1, 1, '[)') AS empty_range,
    int4range(NULL, 5, '(]') AS unbounded_lower;
```

Test:

- Lower bound đúng tại boundary.
- Upper bound đúng tại boundary.
- Element ngay trước/sau boundary.
- Inclusive và exclusive endpoints.
- Empty range.
- Unbounded range.
- NULL range column.
- Overlap, adjacency, contains và contained-by.

### 13.4. Canonical range representations

Một số discrete range types có canonicalization; ví dụ integer ranges có thể chuẩn hóa thành lower-inclusive, upper-exclusive representation tương đương. Test equality/round-trip theo semantic range, không chỉ so sánh chuỗi output.

### 13.5. Multirange

Multirange là tập các ranges không overlap và được chuẩn hóa. Test empty multirange, một range, nhiều disjoint ranges, adjacent ranges và ranges được merge/canonicalize. Kiểm tra operators contains/overlap và aggregate operations nếu application dùng.

### 13.6. Arrays

Arrays có thể khác nhau về:

- SQL NULL array.
- Empty array.
- Array có NULL elements.
- Dimensions và lower bounds.
- Multidimensional arrays.
- Duplicate elements.

PostgreSQL cho phép array dimensions/lower bounds linh hoạt. Nếu application giả định array luôn bắt đầu từ index 1 hoặc luôn một chiều, hãy test constraint hoặc normalize dữ liệu theo contract đó.

```sql
SELECT
    array_length(ARRAY[]::integer[], 1) AS empty_length,
    cardinality(ARRAY[]::integer[]) AS empty_cardinality,
    array_lower('[0:2]={10,20,30}'::integer[], 1) AS lower_bound,
    array_dims(ARRAY[[1,2],[3,4]]) AS dimensions;
```

### 13.7. JSONB field presence

JSON object có thể phân biệt missing key và key có JSON null:

```sql
SELECT
    '{}'::jsonb ? 'nickname' AS key_missing,
    '{"nickname":null}'::jsonb ? 'nickname' AS key_present,
    '{"nickname":null}'::jsonb -> 'nickname' AS json_null_value,
    '{"nickname":null}'::jsonb ->> 'nickname' AS text_extraction;
```

JSON extraction operator ->> có thể trả SQL NULL cho key missing và JSON null, vì vậy dùng key-existence operator hoặc jsonb_typeof để phân biệt nếu nghiệp vụ cần.

### 13.8. JSON type validation

```sql
SELECT
    jsonb_typeof('null'::jsonb),
    jsonb_typeof('42'::jsonb),
    jsonb_typeof('"42"'::jsonb),
    jsonb_typeof('true'::jsonb),
    jsonb_typeof('[]'::jsonb),
    jsonb_typeof('{}'::jsonb);
```

Number 42 và string "42" là hai JSON types khác nhau. Test type coercion khi application deserialize JSON và khi dùng JSONPath.

### 13.9. JSONB numeric range

JSONB number được lưu theo numeric semantics của PostgreSQL. Test số rất lớn, decimal scale, exponent notation và giá trị không hợp lệ theo business domain. JSONB không tự enforce schema; dùng CHECK, generated columns, constraints hoặc validation function để enforce các invariants quan trọng.

### 13.10. UUID

UUID là fixed-size 128-bit identifier. Test:

- UUID canonical format.
- Upper/lowercase hex input.
- Hyphen positions.
- Invalid characters/length.
- NULL và duplicate values.
- Round-trip qua driver và JSON serialization.

UUID equality không phụ thuộc chữ hoa/thường của input textual representation; database lưu type UUID, không phải chuỗi format tùy ý.

### 13.11. Generated columns

Generated columns có thể phụ thuộc vào expression và type coercion:

```sql
CREATE TABLE test_constraints.line_totals (
    quantity integer NOT NULL,
    unit_price numeric(10,2) NOT NULL,
    total numeric(14,2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED
);
```

Test boundary multiplication, rounding, overflow và NULL propagation. Generated expression phải dùng functions/operators được phép và có volatility phù hợp theo yêu cầu của PostgreSQL.

### 13.12. Casts và implicit conversions

PostgreSQL có explicit casts, assignment casts và implicit casts. Query có thể resolve operator khác nhau tùy types của literals/parameters. Test prepared statements với parameter types đúng như driver gửi; một string parameter không luôn có semantics giống typed numeric parameter.

Không dựa vào implicit cast nếu có thể làm mất precision hoặc ngăn index usage. Cast cột trong WHERE có thể thay đổi operator resolution và indexability.

---

## 14. Kiểm thử transaction, concurrency và race conditions

### 14.1. Vì sao cần nhiều sessions?

Constraints như UNIQUE, FOREIGN KEY và EXCLUDE phải giữ invariant khi transactions đồng thời. Một test đơn session chỉ xác nhận sequential behavior; nó không phát hiện hết race conditions.

### 14.2. Unique insert race

Tạo một unique key và chạy hai sessions:

```sql
CREATE TABLE test_constraints.concurrent_keys (
    key text PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Trình tự:

1. Session A: BEGIN; INSERT key K; chưa COMMIT.
2. Session B: BEGIN; INSERT key K; statement thường chờ Session A.
3. Session A: COMMIT.
4. Session B nhận unique violation.
5. Rollback Session B.

Lặp lại với Session A ROLLBACK; khi đó Session B có thể insert thành công.

### 14.3. Foreign key parent delete race

Kiểm thử một transaction xóa parent trong khi transaction khác insert child tham chiếu parent đó. FK locking/checking phải bảo đảm không có orphan child commit. Xác định expected outcome theo transaction order và ON DELETE action.

### 14.4. Exclusion race

Hai sessions cùng insert reservation có cùng resource và overlapping ranges. Exclusion constraint phải bảo đảm không có hai conflicting rows cùng commit. Test cả overlapping và adjacent ranges, cũng như transaction rollback.

### 14.5. Write skew và cross-row invariants

Một invariant như “tổng allocations không vượt capacity” không thể được bảo vệ chỉ bằng CHECK trên từng row. Hai transactions có thể cùng đọc tổng hiện tại rồi insert allocations khác nhau vượt capacity.

Các lựa chọn gồm:

- Thiết kế schema để biểu diễn invariant bằng UNIQUE/FK/EXCLUDE.
- Lock một parent row hoặc resource row trong transaction.
- Dùng SERIALIZABLE isolation và retry serialization failures.
- Dùng trigger/transaction logic có locking phù hợp.

Test concurrency ở isolation level production và xác nhận application retry SQLSTATE 40001 nếu dùng SERIALIZABLE.

### 14.6. Deferred constraint failures

Một constraint INITIALLY DEFERRED có thể cho phép statements chạy thành công nhưng COMMIT thất bại. Test harness phải kiểm tra lỗi tại COMMIT, không chỉ kiểm tra từng INSERT/UPDATE.

### 14.7. Savepoint và error recovery

Trong transaction test, một lỗi statement aborts transaction cho tới khi rollback. Dùng SAVEPOINT để cô lập negative case, sau đó ROLLBACK TO SAVEPOINT. Kiểm tra transaction state trước khi tiếp tục assertions.

### 14.8. Idempotency và retries

Nếu application retry một transaction sau timeout, test:

- Client không biết transaction đã commit hay chưa.
- Duplicate request identifier.
- Unique idempotency key.
- Retry sau serialization/deadlock error.
- Partial work trong external systems.

Unique constraint trên idempotency key thường giúp chống xử lý lặp; test conflict path và cách application đọc kết quả đã tồn tại.

### 14.9. Deadlocks

Hai transactions lock rows theo thứ tự ngược nhau có thể deadlock. Tạo test có kiểm soát trong môi trường riêng, xác nhận một transaction bị abort với SQLSTATE 40P01 và application có retry policy giới hạn.

### 14.10. Lock timeout và statement timeout

Test hành vi khi lock_timeout và statement_timeout được cấu hình. Phân biệt timeout khi chờ lock với query execution timeout; ứng dụng phải rollback transaction và không tiếp tục dùng connection trong trạng thái aborted.

---

## 15. Kiểm thử qua client drivers và application

### 15.1. Timestamp serialization

Driver có thể serialize timestamp values khác nhau tùy language type và protocol. Test:

- Instant có explicit UTC offset.
- Instant với non-zero offset.
- Local timestamp không zone.
- Microsecond precision.
- DST gap/fold.
- Session TimeZone khác UTC.

Gửi parameter có type tường minh nếu driver hỗ trợ; không nối timestamp thành SQL text tùy ý.

### 15.2. Numeric serialization

Một số language runtimes dùng binary floating-point cho mọi số. Nếu gửi currency dưới dạng double, giá trị có thể đã mất precision trước khi PostgreSQL nhận. Dùng decimal type của driver hoặc integer minor units và test round-trip.

### 15.3. NULL parameter binding

SQL NULL không giống string "NULL". Driver phải bind null với parameter type phù hợp. Test:

- NULL parameter.
- Empty string.
- Zero.
- False.
- JSON null.
- Missing JSON property.

Kiểm tra generated SQL/parameter binding trong test diagnostics mà không log secrets.

### 15.4. Prepared statement type inference

Untyped NULL literal hoặc parameter có thể gây ambiguity khi PostgreSQL không suy ra được type. Dùng explicit cast hoặc parameter type rõ ràng trong prepared statements. Test cùng SQL được gọi lần đầu với NULL và lần sau với non-NULL để phát hiện vấn đề type inference.

### 15.5. Connection pool session state

Connection pools tái sử dụng sessions. Nếu một request SET TIME ZONE, SET DateStyle hoặc thay search_path mà không reset, request kế tiếp có thể nhận session state không mong muốn.

Test checkout/checkin connection và xác nhận session settings được reset hoặc transaction-local:

```sql
BEGIN;
SET LOCAL TIME ZONE 'UTC';
SELECT current_setting('TimeZone');
COMMIT;
```

SET LOCAL chỉ áp dụng trong transaction hiện tại. Với pooled connections, đây thường là cách an toàn hơn SET session-level cho request-scoped behavior.

### 15.6. Text encoding

Test client_encoding, server_encoding và Unicode characters. Xác nhận round-trip không làm mất combining marks, emoji hoặc supplementary-plane characters. Không chỉ test ASCII.

### 15.7. Error mapping

Application nên map SQLSTATE/constraint name thành lỗi domain phù hợp. Test rằng unique violation, FK violation, check violation, overflow và invalid datetime được phân biệt; tránh biến mọi lỗi thành HTTP 500 chung hoặc trả raw database message cho end users.

---

## 16. Tổ chức regression tests với SQL và pgTAP

### 16.1. SQL script thuần

Một script test đơn giản có thể tạo schema fixture, chạy assertions và rollback:

```sql
BEGIN;

CREATE TEMP TABLE test_values (
    id integer PRIMARY KEY,
    amount numeric(5,2) NOT NULL CHECK (amount >= 0)
);

INSERT INTO test_values VALUES (1, 0), (2, 999.99);

DO $$
BEGIN
    IF (SELECT count(*) FROM test_values) <> 2 THEN
        RAISE EXCEPTION 'unexpected row count';
    END IF;

    IF (SELECT max(amount) FROM test_values) <> 999.99 THEN
        RAISE EXCEPTION 'unexpected maximum amount';
    END IF;
END
$$;

ROLLBACK;
```

Negative tests cần savepoint hoặc harness bắt exception để transaction có thể tiếp tục.

### 16.2. DO block kiểm tra expected SQLSTATE

```sql
DO $$
BEGIN
    BEGIN
        INSERT INTO test_values(id, amount) VALUES (3, -1);
        RAISE EXCEPTION 'expected check violation did not occur';
    EXCEPTION
        WHEN check_violation THEN
            NULL; -- Expected error.
    END;
END
$$;
```

Trong production test suite, dùng exception condition hoặc SQLSTATE rõ ràng. Tránh bắt mọi exceptions bằng WHEN OTHERS rồi xem như test pass; điều đó có thể che lỗi không liên quan.

### 16.3. pgTAP

pgTAP là extension cung cấp assertion functions cho PostgreSQL tests. Ví dụ test schema/constraints:

```sql
CREATE EXTENSION IF NOT EXISTS pgtap;

BEGIN;
SELECT plan(5);

SELECT has_table('test_constraints', 'products');
SELECT col_not_null('test_constraints', 'products', 'sku');
SELECT col_type('test_constraints', 'products', 'price', 'numeric(12,2)');

SELECT lives_ok(
    $$INSERT INTO test_constraints.products(sku, price)
      VALUES ('T-100', 12.50)$$,
    'valid product is accepted'
);

SELECT throws_ok(
    $$INSERT INTO test_constraints.products(sku, price)
      VALUES (NULL, 12.50)$$,
    '23502',
    'null sku is rejected'
);

SELECT * FROM finish();
ROLLBACK;
```

Tên assertion và signature cần được đối chiếu với pgTAP version cài đặt. Test suite có thể dùng throws_ok với SQLSTATE, message và description theo signature được cung cấp bởi version đó.

### 16.4. Test fixture và isolation

Mỗi test nên có setup/teardown độc lập. Dùng transaction rollback khi test không cần kiểm tra commit-time behavior hoặc concurrency. Với test COMMIT/deferred constraints, có thể cần transaction riêng và harness bắt lỗi từ COMMIT.

### 16.5. Chia test suite theo semantics

Một cấu trúc có thể dùng:

```text
tests/
  constraints/
    not_null.sql
    check.sql
    unique.sql
    foreign_key.sql
    exclusion.sql
    deferred.sql
    concurrency/
  nulls/
    boolean_logic.sql
    unique_nulls.sql
    json_null.sql
    arrays.sql
  time/
    timestamp_types.sql
    timezone_conversion.sql
    dst_gap_fold.sql
    intervals.sql
  types/
    integer_boundaries.sql
    numeric_precision.sql
    floating_point.sql
    text_unicode.sql
```

### 16.6. CI matrix

Chạy tests trên các PostgreSQL major versions mà application hỗ trợ. Ghi rõ:

- Server major/minor.
- OS/container image.
- Timezone database/tzdata.
- Locale/collation provider.
- Client driver version.
- Extensions và versions.

Các tests dùng timezone rules hoặc collation có thể khác nhau giữa environments; pinning environment giúp tái hiện, còn matrix nhiều environments giúp phát hiện portability issues.

---

## 17. Xây dựng test matrix cho boundary cases

### 17.1. Ma trận constraint

Với mỗi table, ghi rõ rule, input class, expected result và SQLSTATE:

| Rule | Input | Expected result |
|---|---|---|
| NOT NULL | NULL | 23502 |
| NOT NULL | Empty string | Chấp nhận nếu không có rule khác |
| CHECK amount >= 0 | -0.01 | 23514 |
| CHECK amount >= 0 | 0 | Chấp nhận |
| CHECK amount >= 0 | NULL | UNKNOWN, được CHECK chấp nhận nếu không NOT NULL |
| UNIQUE | Duplicate non-NULL key | 23505 |
| UNIQUE mặc định | Nhiều NULL | Chấp nhận |
| UNIQUE NULLS NOT DISTINCT | NULL thứ hai | 23505 |
| FOREIGN KEY | Missing parent | 23503 |
| FOREIGN KEY MATCH SIMPLE | Một FK component NULL | Bỏ qua match check |
| FOREIGN KEY MATCH FULL | Partial NULL | 23503 |
| EXCLUDE | Overlap conflict | 23P01 |

### 17.2. Ma trận timezone

| Scenario | Input | Assertion |
|---|---|---|
| UTC instant | Timestamp có +00 | Đọc lại cùng instant |
| Offset input | Cùng instant với +07 | Equality với UTC representation |
| Session timezone đổi | SET TIME ZONE khác | Instant không đổi, display đổi |
| Timestamp without zone | Input có offset | Offset không được giữ |
| DST gap | Local time không tồn tại | Kết quả theo policy đã định |
| DST fold | Local time xuất hiện hai lần | Chọn occurrence bằng offset/policy |
| Calendar day | interval 1 day | Giữ calendar intent theo zone |
| Elapsed duration | interval 24 hours | Đúng 24 elapsed hours |
| Microseconds | Fractional precision 6 | Round-trip đúng precision |

### 17.3. Ma trận numeric

| Type | Boundary tests |
|---|---|
| smallint | -32768, 32767, -32769, 32768 |
| integer | -2147483648, 2147483647 và ngoài range |
| bigint | Min/max và ngoài range |
| numeric(5,2) | -999.99, 999.99, 1000.00, 1.234 |
| numeric unconstrained | Scale lớn, nhiều digits, special values |
| real/double | Approximation, NaN, Infinity, signed zero |
| sequence AS smallint | Last valid value và exhaustion |

### 17.4. Ma trận text

| Scenario | Assertion |
|---|---|
| varchar(n) đúng n chars | Chấp nhận |
| varchar(n) n+1 chars | Assignment bị từ chối nếu ký tự dư không phải spaces |
| Explicit cast varchar(n) | Có thể truncate |
| Multibyte Unicode | Character count khác byte count |
| Trailing spaces | Text/varchar giữ, char semantics khác |
| Composed/decomposed Unicode | Equality theo normalization policy |
| Case variants | Equality/unique theo case policy |
| Empty/whitespace | Tách biệt theo CHECK/validation |

### 17.5. Ma trận NULL

Với mỗi nullable column, test ít nhất:

1. SQL NULL.
2. Empty string hoặc empty collection nếu type hỗ trợ.
3. Zero/false nếu type là numeric/boolean.
4. JSON null nếu type là JSON/JSONB.
5. Missing key nếu value nằm trong JSON object.
6. Mixed NULL/non-NULL trong composite key, array và expression.

### 17.6. Ma trận driver

Chạy cùng một bộ input qua:

- SQL literal trực tiếp.
- Prepared statement với typed parameters.
- Prepared statement với NULL parameters.
- Text protocol.
- Binary protocol nếu driver dùng.
- Application serializer/deserializer.

So sánh type, value và precision sau round-trip. Test phải mô phỏng đúng driver/version mà production sử dụng.

### 17.7. Phân loại expected errors

Không gộp mọi negative cases vào một assertion “throws”. Dùng SQLSTATE/constraint name để phân biệt:

- Input parser error.
- Cast error.
- NOT NULL/CHECK/UNIQUE/FK/EXCLUDE violation.
- Overflow.
- Deferred failure ở COMMIT.
- Serialization failure/deadlock.
- Lock/statement timeout.

---

## 18. Ví dụ regression test end-to-end

### 18.1. Tạo schema mẫu

```sql
CREATE SCHEMA IF NOT EXISTS qa_boundary;

CREATE TABLE qa_boundary.bookings (
    booking_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id integer NOT NULL,
    customer_email text NOT NULL,
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    amount numeric(8,2) NOT NULL,
    CONSTRAINT bookings_amount_nonnegative
        CHECK (amount >= 0),
    CONSTRAINT bookings_time_order
        CHECK (ends_at > starts_at),
    CONSTRAINT bookings_email_uq
        UNIQUE (customer_email)
);
```

Schema mẫu kết hợp NOT NULL, CHECK, UNIQUE và timestamptz/numeric types. Trong môi trường test, có thể thêm exclusion constraint cho room/time overlap nếu business rule cấm booking trùng.

### 18.2. Positive boundary cases

```sql
INSERT INTO qa_boundary.bookings (
    room_id, customer_email, starts_at, ends_at, amount
)
VALUES (
    1,
    'a@example.test',
    timestamptz '2026-06-01 02:00:00+00',
    timestamptz '2026-06-01 03:00:00+00',
    0.00
);

INSERT INTO qa_boundary.bookings (
    room_id, customer_email, starts_at, ends_at, amount
)
VALUES (
    2,
    'b@example.test',
    timestamptz '2026-06-01 09:00:00+07',
    timestamptz '2026-06-01 10:00:00+07',
    999999.99
);
```

Hai rows nằm trong domain numeric(8,2), có time interval hợp lệ và email khác nhau.

### 18.3. Negative cases

Các test sau cần được chạy độc lập hoặc trong savepoints vì mỗi lỗi làm transaction hiện tại aborted:

```sql
-- NOT NULL
INSERT INTO qa_boundary.bookings
    (room_id, customer_email, starts_at, ends_at, amount)
VALUES
    (1, NULL, now(), now() + interval '1 hour', 10);

-- CHECK: end must be after start
INSERT INTO qa_boundary.bookings
    (room_id, customer_email, starts_at, ends_at, amount)
VALUES
    (1, 'bad-time@example.test', now(), now(), 10);

-- CHECK: amount must be nonnegative
INSERT INTO qa_boundary.bookings
    (room_id, customer_email, starts_at, ends_at, amount)
VALUES
    (1, 'negative@example.test', now(), now() + interval '1 hour', -0.01);

-- UNIQUE
INSERT INTO qa_boundary.bookings
    (room_id, customer_email, starts_at, ends_at, amount)
VALUES
    (1, 'a@example.test', now(), now() + interval '1 hour', 10);

-- Numeric precision overflow
INSERT INTO qa_boundary.bookings
    (room_id, customer_email, starts_at, ends_at, amount)
VALUES
    (1, 'overflow@example.test', now(), now() + interval '1 hour', 1000000.00);
```

Mỗi statement phải fail vì constraint/type tương ứng. Đừng chạy nguyên block trong một transaction rồi bỏ qua trạng thái aborted; dùng harness xử lý từng expected exception.

### 18.4. Kiểm tra timezone equality

```sql
SET TIME ZONE 'UTC';

SELECT
    timestamptz '2026-06-01 09:00:00+07'
    =
    timestamptz '2026-06-01 02:00:00+00'
    AS same_instant;
```

Assertion phải là TRUE. Đây là kiểm tra hai representations khác nhau cùng một instant.

### 18.5. Kiểm tra output timezone

```sql
SET TIME ZONE 'UTC';
SELECT starts_at FROM qa_boundary.bookings WHERE customer_email = 'a@example.test';

SET TIME ZONE 'Asia/Ho_Chi_Minh';
SELECT starts_at FROM qa_boundary.bookings WHERE customer_email = 'a@example.test';
```

Hai output text khác nhau nhưng underlying instant giống nhau.

### 18.6. Kiểm tra dữ liệu cuối cùng

```sql
SELECT
    count(*) AS rows,
    min(amount) AS minimum_amount,
    max(amount) AS maximum_amount,
    bool_and(ends_at > starts_at) AS all_time_ranges_valid,
    bool_and(amount >= 0) AS all_amounts_nonnegative
FROM qa_boundary.bookings;
```

Các assertions aggregate là lớp kiểm tra bổ sung. Chúng không thay thế constraints và không tự chứng minh test negative cases đã được thực hiện.

---

## 19. Những sai lầm thường gặp khi kiểm thử

1. **Chỉ test happy path:** bỏ qua NULL, empty, min/max và invalid inputs.
2. **Cho rằng CHECK cấm NULL:** CHECK expression UNKNOWN được chấp nhận.
3. **Đồng nhất NULL với empty string:** chúng là các values khác nhau.
4. **Cho rằng UNIQUE chỉ cho một NULL:** mặc định PostgreSQL cho phép nhiều NULLs.
5. **Quên composite FK MATCH SIMPLE:** một component NULL có thể bỏ qua toàn bộ FK check.
6. **Không test MATCH FULL:** partial-null composite key có thể vi phạm rule.
7. **Chỉ kiểm tra statement, không kiểm tra COMMIT:** deferred constraints có thể fail ở cuối transaction.
8. **Dùng SELECT trước INSERT để bảo đảm uniqueness:** race condition vẫn có thể xảy ra; cần UNIQUE constraint.
9. **Lưu instant vào timestamp without time zone:** mất offset/timezone context.
10. **Dựa vào session TimeZone mặc định:** kết quả phụ thuộc connection state.
11. **Dùng abbreviation mơ hồ:** ưu tiên IANA timezone names.
12. **Không test DST gap/fold:** local time có thể không tồn tại hoặc xuất hiện hai lần.
13. **Coi interval 1 day luôn là 24 hours:** calendar arithmetic có thể khác elapsed duration qua DST.
14. **Dùng float cho currency:** binary approximation có thể làm sai rounding/equality.
15. **Không test numeric coercion:** numeric(p,s) có thể round trước khi lưu.
16. **Chỉ test column range, bỏ arithmetic overflow:** phép tính có thể overflow dù operands hợp lệ.
17. **Nhầm varchar length với bytes:** varchar(n) giới hạn characters.
18. **Không test explicit casts:** cast có thể truncate khác với assignment.
19. **Bỏ qua Unicode normalization/collation:** strings nhìn giống nhau có thể không equal.
20. **Coi JSON null là SQL NULL:** đây là hai trạng thái khác nhau.
21. **Không test driver binding:** application có thể gửi timestamp/numeric/NULL khác với SQL literal.
22. **Bắt mọi exception như expected:** có thể che bug ngoài dự kiến.
23. **Chỉ test một session:** bỏ sót race conditions, deadlocks và write skew.
24. **Dựa vào message text:** SQLSTATE và constraint name ổn định hơn.
25. **Test phụ thuộc thứ tự:** fixtures không độc lập gây flaky tests.

---

## 20. Checklist và tổng kết

### Constraints

1. Test NOT NULL với NULL, empty string và whitespace.
2. Test CHECK với TRUE, FALSE và UNKNOWN.
3. Test UNIQUE với duplicate, NULL và NULLS NOT DISTINCT.
4. Test composite keys và case/collation semantics.
5. Test FOREIGN KEY với missing parent, NULL và MATCH mode.
6. Test ON DELETE/ON UPDATE actions.
7. Test deferred constraints ở SET CONSTRAINTS và COMMIT.
8. Test exclusion overlap, adjacency và concurrency.

### NULL semantics

9. Test TRUE/FALSE/UNKNOWN trong WHERE, AND, OR và NOT.
10. Test IS NULL, IS DISTINCT FROM, COALESCE và NULLIF.
11. Test NOT IN với NULL.
12. Test aggregates, DISTINCT và GROUP BY.
13. Phân biệt SQL NULL, JSON null, missing key, empty array và array chứa NULL.

### Timezone và date/time

14. Chọn date/time/timestamp/timestamptz theo domain.
15. Set TimeZone tường minh trong tests.
16. Test explicit offsets và input không có timezone.
17. Test AT TIME ZONE hai chiều.
18. Test DST gap/fold và local-time policy.
19. Test leap days, month ends, fractional seconds và infinity.
20. Phân biệt interval calendar day với elapsed hours.

### Type boundaries và application

21. Test integer min/max và overflow.
22. Test numeric precision/scale, rounding và special values.
23. Test floating-point tolerance, NaN, Infinity và signed zero.
24. Test varchar character count, byte length, casts, trailing spaces và Unicode.
25. Test UUID, arrays, ranges, JSONB, domains và generated expressions.
26. Test prepared statements, typed NULL parameters và connection pool session state.
27. Test driver round-trip với text/binary protocol theo production stack.

### Automation và concurrency

28. Dùng SQLSTATE/constraint name cho negative assertions.
29. Dùng savepoints hoặc harness để xử lý expected errors.
30. Test UNIQUE/FK/EXCLUDE với nhiều sessions.
31. Test serialization/deadlock retry behavior nếu application cần.
32. Chạy suite trên PostgreSQL versions, collations và timezone environments được hỗ trợ.
33. Giữ fixture độc lập, deterministic và có thể chạy lặp lại.

Kiểm thử ràng buộc, NULL, múi giờ và ranh giới kiểu dữ liệu cần tập trung vào semantics mà SQL thực sự áp dụng. CHECK không tự cấm NULL; UNIQUE mặc định xem NULLs là distinct; composite FK có MATCH behavior; timestamptz lưu instant nhưng hiển thị theo session timezone; DST có local times không tồn tại hoặc lặp lại; numeric/float/text có các quy tắc precision, rounding và length khác nhau.

Một regression suite tốt xác nhận cả dữ liệu được chấp nhận lẫn dữ liệu bị từ chối, kiểm tra trạng thái sau commit, mô phỏng concurrency và chạy qua đúng driver/session settings của production. Khi test được thiết kế theo boundary matrix và SQLSTATE, các lỗi dữ liệu khó tái hiện sẽ trở thành những trường hợp có thể kiểm tra tự động.

**Câu hỏi tự kiểm tra:** Một cột có CHECK (amount >= 0) nhưng không có NOT NULL. Test INSERT NULL thành công có phải chứng minh constraint bị lỗi không? Không. CHECK expression trả UNKNOWN cho NULL và PostgreSQL chấp nhận row; nếu business rule yêu cầu amount luôn tồn tại, cần thêm NOT NULL.

### Tài liệu PostgreSQL chính thức

- [Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html).
- [Comparison Functions and Operators](https://www.postgresql.org/docs/current/functions-comparison.html).
- [Logical Operators](https://www.postgresql.org/docs/current/functions-logical.html).
- [Date/Time Types](https://www.postgresql.org/docs/current/datatype-datetime.html).
- [Date/Time Functions and Operators](https://www.postgresql.org/docs/current/functions-datetime.html).
- [Numeric Types](https://www.postgresql.org/docs/current/datatype-numeric.html).
- [Character Types](https://www.postgresql.org/docs/current/datatype-character.html).
- [JSON Types](https://www.postgresql.org/docs/current/datatype-json.html).
- [Range Types](https://www.postgresql.org/docs/current/rangetypes.html).
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html).
- [pgTAP Documentation](https://pgtap.org/documentation.html).
