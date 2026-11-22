# Tách kiểm thử schema, SQL, giao dịch và hiệu năng trong PostgreSQL

Một hệ thống PostgreSQL có thể khởi động thành công và vẫn chứa nhiều lỗi nghiêm trọng. Migration có thể tạo sai constraint; một câu SQL có thể trả kết quả sai khi gặp NULL; hai transaction đồng thời có thể ghi đè dữ liệu; một query nhanh trên máy development có thể chậm hàng chục lần khi dữ liệu tăng hoặc concurrency cao.

Vì vậy, kiểm thử database cần được chia thành các nhóm có mục tiêu và cách đo khác nhau. **Kiểm thử schema** xác nhận cấu trúc, constraints, indexes, dependencies và migration. **Kiểm thử SQL** xác nhận câu lệnh, function, view và kết quả nghiệp vụ. **Kiểm thử giao dịch** xác nhận tính đúng đắn khi commit, rollback, isolation và concurrency. **Kiểm thử hiệu năng** đo latency, throughput, resource usage và khả năng duy trì SLO dưới tải.

Các nhóm này liên quan với nhau nhưng không thể thay thế nhau. Một query trả đúng kết quả trong một session chưa chứng minh transaction an toàn khi chạy đồng thời. Một migration tạo đủ objects chưa chứng minh SQL cũ còn tương thích. Một benchmark tốt cũng không chứng minh dữ liệu đúng.

Bài học thuộc chương **Kiểm thử** của module *Database Engine Relational PostgreSQL*. Nội dung hướng dẫn cách tách test suite theo lớp, thiết kế fixture và môi trường, viết ví dụ SQL/PostgreSQL, kiểm tra concurrency, đo performance và tổ chức chúng trong CI/CD.

> **Nguyên tắc:** Mỗi test phải trả lời một câu hỏi rõ ràng, có dữ liệu đầu vào xác định, kết quả mong đợi và bằng chứng có thể lặp lại. Chọn đúng lớp kiểm thử giúp tìm lỗi ở nơi phát sinh và giảm thời gian chẩn đoán.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao cần tách schema, SQL, transaction và performance tests.
2. Xác định phạm vi và assertion phù hợp cho từng nhóm test.
3. Tạo database test cô lập với phiên bản PostgreSQL xác định.
4. Kiểm tra tables, columns, types, constraints, indexes, views, triggers và routines.
5. Kiểm tra migration từ schema cũ sang schema mới.
6. Viết SQL tests cho kết quả, NULL, boundary values và side effects.
7. Kiểm thử functions, procedures, triggers và permissions.
8. Thiết kế fixtures và seed data có thể tái lập.
9. Kiểm tra commit, rollback, savepoints và deferred constraints.
10. Kiểm tra isolation levels, lost updates, non-repeatable reads và serialization failures.
11. Tạo concurrency tests với nhiều database sessions.
12. Đo query plans, latency, throughput, CPU, I/O, WAL và lock waits.
13. Dùng EXPLAIN, pg_stat_statements và pgbench phù hợp.
14. Thiết kế performance tests có baseline và workload đại diện.
15. Tách smoke tests, regression tests, integration tests và load tests.
16. Đưa test phù hợp vào CI/CD mà không làm pipeline mất ổn định.
17. Chẩn đoán lỗi dựa trên loại test và evidence.
18. Xây dựng ma trận test coverage và tiêu chí release.

## 2. Vì sao phải tách các nhóm kiểm thử?

Database có nhiều lớp hành vi. Một thay đổi ở một lớp có thể ảnh hưởng lớp khác, nhưng cách phát hiện lỗi khác nhau.

| Nhóm test | Câu hỏi chính | Bằng chứng |
|---|---|---|
| Schema | Cấu trúc database có đúng contract không? | Catalog assertions, schema diff, migration result |
| SQL | Query/function có trả đúng kết quả và side effects không? | Expected rows, values, SQLSTATE, object state |
| Transaction | Nhiều thao tác có giữ consistency khi commit/rollback/concurrent không? | Commit state, isolation schedule, lock/serialization result |
| Performance | Hệ thống có đáp ứng SLO dưới workload dự kiến không? | Latency distribution, throughput, resource metrics |

### 2.1. Schema test không thay SQL test

Một bảng có đúng cột và constraint nhưng function vẫn có thể tính sai tổng tiền. Schema test xác nhận object tồn tại và định nghĩa đúng; SQL test xác nhận behavior.

### 2.2. SQL test không thay transaction test

Một câu UPDATE chạy đúng khi chỉ có một session có thể làm mất cập nhật khi hai sessions ghi đồng thời. Transaction test phải điều khiển thứ tự thao tác và kiểm tra kết quả sau commit.

### 2.3. Transaction test không thay performance test

Một giao dịch có thể đúng về consistency nhưng giữ lock quá lâu, gây queueing và làm p99 latency tăng. Performance test đo tác động dưới tải và thời gian.

### 2.4. Performance test không thay correctness test

Một query nhanh nhưng trả thiếu rows hoặc dùng phép tính sai vẫn là lỗi. Trước khi benchmark, xác nhận query semantics và dataset.

### 2.5. Các test có thể chạy chung pipeline nhưng cần report riêng

Một CI pipeline có thể chạy đủ bốn nhóm. Tuy nhiên, kết quả phải được phân loại rõ để biết lỗi nằm ở DDL, SQL, concurrency hay resource usage.

## 3. Phạm vi kiểm thử và test pyramid

Không phải mọi test cần chạy ở mọi pull request.

Một cách tổ chức phổ biến:

```text
                 End-to-end / Production-like
               Performance and resilience tests
             Transaction / concurrency integration
                 SQL behavior regression
                 Schema and migration tests
                 Static SQL/config checks
```

Các test ở đáy thường nhanh, ít phụ thuộc và chạy thường xuyên. Test ở phía trên cần môi trường gần production, dữ liệu lớn hoặc nhiều sessions nên chạy ít hơn nhưng phải được lên lịch và có gate phù hợp.

### 3.1. Static checks

Có thể kiểm tra migration naming, SQL lint, forbidden patterns, configuration syntax và dependency declarations mà chưa cần database.

### 3.2. Schema tests

Khởi tạo database rỗng, apply migrations và assert catalog. Có thể chạy trên mọi pull request nếu thời gian cho phép.

### 3.3. SQL behavior tests

Nạp fixtures nhỏ, gọi queries/functions và so sánh kết quả mong đợi. Nên chạy nhanh và deterministic.

### 3.4. Transaction tests

Cần ít nhất hai connections và một schedule có kiểm soát. Có thể chạy trong integration CI hoặc test suite chuyên biệt.

### 3.5. Performance/load tests

Cần tài nguyên ổn định, dataset đại diện và nhiều lần đo. Thường chạy trên dedicated runner, staging hoặc trước release; không nên dùng shared ephemeral CI host để kết luận chính xác về p99.

## 4. Thiết kế test environment

Một test chỉ đáng tin khi biết nó chạy trên PostgreSQL version, config và dữ liệu nào.

Ghi lại:
- PostgreSQL major/minor version.
- Image/package digest.
- Extensions và versions.
- Encoding, locale và collation.
- postgresql.conf settings quan trọng.
- Authentication và roles.
- Hardware/container CPU, memory và storage limits.
- Connection pool settings.
- Migration framework/version.
- Dataset seed và generator version.

### 4.1. Cô lập database cho từng test run

Ưu tiên database riêng hoặc ephemeral PostgreSQL instance cho mỗi job/test suite. Tránh để test song song dùng chung schema và xóa dữ liệu của nhau.

### 4.2. Dùng cùng major version với production

Một test pass trên PostgreSQL 16 không chứng minh migration sẽ pass trên PostgreSQL 17. Dùng target version cho migration tests; nếu hỗ trợ nhiều versions, chạy compatibility matrix.

### 4.3. Container không tự động đồng nghĩa production-like

Container tiện cho CI, nhưng default memory, storage và kernel environment có thể khác production. Dùng container cho correctness/integration; performance gate cần giới hạn tài nguyên và môi trường được kiểm soát.

### 4.4. Không dùng production data không được xử lý

Tạo synthetic data hoặc mask/anonymize theo policy. Nếu cần giữ skew/cardinality, tạo dữ liệu có phân phối tương tự mà không để lộ thông tin nhạy cảm.

### 4.5. Test role và permissions

Không chạy mọi test bằng superuser. Tạo roles tương tự application, migration owner, read-only user và reporting user. Quyền quá rộng có thể che lỗi permission trong production.

## 5. Quản lý fixtures và dữ liệu kiểm thử

Fixture là dữ liệu đầu vào có kiểm soát để test có thể lặp lại.

Một fixture tốt:
- Nhỏ đủ để chạy nhanh.
- Có rows đại diện cho business rules.
- Bao gồm NULL và boundary cases.
- Có khóa ổn định.
- Không phụ thuộc thứ tự insert ngoài ý muốn.
- Có thể reset giữa test cases.
- Không chứa dữ liệu nhạy cảm.

### 5.1. Seed data xác định

Ví dụ:

```sql
INSERT INTO customers (id, email, status)
VALUES
    (101, 'a@example.test', 'active'),
    (102, 'b@example.test', 'inactive'),
    (103, NULL, 'pending');
```

Dùng domain .test cho địa chỉ minh họa. Với identity/sequence, nếu test tự cấp ID, phải đồng bộ sequence khi chuyển sang insert tự sinh.

### 5.2. Test data phải có trường hợp biên

Ví dụ với bảng đơn hàng:
- Không có item.
- Một item.
- Nhiều items.
- Quantity bằng 0 nếu schema cho phép.
- Giá trị sát giới hạn precision.
- NULL ở optional fields.
- Duplicate business key.
- Customer không tồn tại.
- Timestamp sát ranh giới ngày/tháng/DST.

### 5.3. Tạo fixtures qua migration và factory

Có thể dùng SQL files, test factories hoặc application fixtures. Tránh copy schema thủ công vào test vì schema test có thể lệch khỏi migration thật.

### 5.4. Reset dữ liệu

Một số lựa chọn:
- Rollback transaction cho test độc lập.
- Truncate tables trong database cô lập.
- Drop/recreate database giữa suites.
- Restore snapshot/template database.

TRUNCATE ... CASCADE có thể xóa nhiều bảng phụ thuộc; chỉ dùng khi test environment riêng và phạm vi rõ ràng.

### 5.5. Không phụ thuộc thứ tự rows

SQL không bảo đảm thứ tự rows nếu không có ORDER BY. Assertions nên so sánh tập hợp hoặc yêu cầu ordering rõ ràng.

## 6. Kiểm thử schema: xác nhận contract cấu trúc

Schema tests xác nhận database có đúng objects và properties mà ứng dụng kỳ vọng.

Phạm vi thường gồm:
- Schemas và ownership.
- Tables/partitioned tables.
- Columns, data types, defaults, generated/identity attributes.
- NULLability.
- Primary/foreign/unique/check constraints.
- Indexes và operator classes.
- Views/materialized views.
- Sequences.
- Functions/procedures và signatures.
- Triggers.
- Enums/domains/composite types.
- Grants, roles và row-level security.
- Extensions.
- Dependencies.

### 6.1. Kiểm tra object tồn tại

Ví dụ:

```sql
SELECT to_regclass('public.orders') IS NOT NULL AS orders_exists;
```

Trong test, assert kết quả là true. to_regclass trả NULL nếu relation không tồn tại.

### 6.2. Kiểm tra column definitions

```sql
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'orders'
ORDER BY ordinal_position;
```

So sánh các cột quan trọng với contract đã định. information_schema cung cấp view chuẩn hóa; khi cần PostgreSQL-specific details như identity/generated attributes, dùng pg_catalog.

### 6.3. Kiểm tra data type và typmod

data_type có thể không thể hiện đủ precision/scale hoặc length. Có thể dùng format_type với catalog metadata:

```sql
SELECT
    a.attname,
    format_type(a.atttypid, a.atttypmod) AS formatted_type,
    a.attnotnull
FROM pg_attribute AS a
JOIN pg_class AS c ON c.oid = a.attrelid
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname = 'orders'
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
```

### 6.4. Kiểm tra constraints

```sql
SELECT
    conname,
    contype,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'public.orders'::regclass
ORDER BY conname;
```

Kiểm tra convalidated để phát hiện constraint được thêm bằng NOT VALID nhưng chưa validate.

### 6.5. Kiểm tra indexes

```sql
SELECT
    indexrelid::regclass AS index_name,
    indisunique,
    indisprimary,
    indisvalid,
    indisready,
    pg_get_indexdef(indexrelid) AS definition
FROM pg_index
WHERE indrelid = 'public.orders'::regclass
ORDER BY indexrelid::regclass::text;
```

Index tồn tại nhưng indisvalid = false không thể được coi là index usable. Kiểm tra expression, predicate, included columns và operator class nếu chúng thuộc contract.

### 6.6. Kiểm tra foreign keys

Schema test nên xác nhận cả referenced table/columns, ON UPDATE, ON DELETE, match type và deferrability. Chỉ assert tên constraint có thể bỏ sót definition sai.

### 6.7. Kiểm tra defaults và generated columns

Xác nhận default expression đúng, sequence ownership phù hợp và generated expression đúng. Đừng chỉ kiểm tra cột có default hay không; kiểm tra expression được lưu.

### 6.8. Kiểm tra views và routines

Dùng pg_get_viewdef, pg_get_functiondef hoặc catalog signatures để kiểm tra định nghĩa cần thiết. Tránh snapshot toàn bộ catalog nếu không cần vì có thể tạo test brittle khi PostgreSQL version thay đổi.

### 6.9. Kiểm tra grants

```sql
SELECT
    grantee,
    privilege_type,
    is_grantable
FROM information_schema.role_table_grants
WHERE table_schema = 'public'
  AND table_name = 'orders'
ORDER BY grantee, privilege_type;
```

Chạy thêm tests bằng role ứng dụng để xác nhận quyền thực tế. Catalog query một mình không chứng minh mọi access path đều hoạt động.

## 7. Schema migration tests

Schema tests phải xác nhận cả schema cuối và đường đi tới schema đó.

### 7.1. Test từ database rỗng

Quy trình:
1. Tạo database mới.
2. Chạy toàn bộ migrations theo thứ tự.
3. Xác nhận migration history.
4. Assert tables, constraints, indexes, views, functions và grants.
5. Chạy SQL smoke tests.

Điều này phát hiện migration mới thiếu dependency hoặc thứ tự sai.

### 7.2. Test nâng cấp từ schema thực tế cũ

Database rỗng không đại diện cho production upgrade. Cần restore snapshot/schema fixture của phiên bản cũ rồi chạy các migrations mới nhất.

Test các source versions được hỗ trợ và những trạng thái dữ liệu có thể tồn tại.

### 7.3. Test migration có dữ liệu

Nạp rows với NULL, duplicate values, values ngoài domain mới, large tables, foreign key relationships, historical timestamps và extension-specific objects.

Sau migration, kiểm tra row counts, data mapping, constraints và application behavior.

### 7.4. Test idempotency theo đúng contract của framework

Migration versioned thường chỉ chạy một lần. Không cần ép mọi migration SQL phải chạy lặp vô hạn nếu framework đảm bảo versioning. Nhưng operational backfill/recovery scripts cần retry an toàn và kiểm tra trạng thái trước khi mutate.

### 7.5. Test failure giữa chừng

Nếu migration gồm nhiều transactions hoặc có lệnh không transactional, mô phỏng failure ở các điểm quan trọng:
- DDL thành công nhưng bước tiếp theo fail.
- CREATE INDEX CONCURRENTLY bị cancel.
- Backfill worker dừng giữa batch.
- Deployment dừng sau expand nhưng trước app release.

Xác nhận database ở trạng thái có thể tiếp tục hoặc có runbook recovery.

### 7.6. Schema diff

Có thể dump schema-only trước/sau và so sánh, nhưng raw diff cần normalize owner, privileges hoặc ordering không liên quan. Ưu tiên assertions về contract quan trọng hơn snapshot toàn bộ output.

### 7.7. Không chỉ test migration chạy nhanh

Một migration có thể pass trên fixture 20 rows nhưng block production table hàng tỷ rows. Schema correctness và operational safety cần test riêng trên dữ liệu có quy mô đại diện.

## 8. Kiểm thử SQL: xác nhận semantics và kết quả

SQL tests xác nhận statement trả đúng rows/values và tạo đúng side effects.

Phạm vi:
- SELECT filters, joins, aggregates.
- INSERT/UPDATE/DELETE.
- Upsert và conflict handling.
- Functions/procedures.
- Views.
- Triggers.
- Operators/casts.
- NULL semantics.
- Sorting/pagination.
- JSON/array/date/time/numeric behavior.
- SQLSTATE/error conditions.

### 8.1. Kiểm tra kết quả bằng expected rows

```sql
SELECT
    order_id,
    total_amount
FROM order_totals
WHERE order_id = 9001;
```

Test phải assert đúng số rows và giá trị total_amount, không chỉ assert query không phát sinh exception.

### 8.2. NULL semantics

SQL dùng three-valued logic: TRUE, FALSE và UNKNOWN. So sánh column = NULL không trả TRUE; dùng IS NULL hoặc IS NOT DISTINCT FROM theo mục tiêu.

Ví dụ:

```sql
SELECT count(*)
FROM customers
WHERE email IS NULL;
```

Test cases cần phân biệt NULL với empty string, zero và missing JSON key.

### 8.3. JOIN semantics

Kiểm tra INNER JOIN loại bỏ unmatched rows, LEFT JOIN giữ unmatched rows, predicate trong ON và WHERE có thể tạo kết quả khác nhau, duplicate keys làm tăng row count và NULL keys không match bằng equality thông thường.

### 8.4. Aggregate semantics

Test count(*), count(column), sum, avg, min/max với empty set, NULL và duplicate rows. sum có thể trả NULL trên tập rỗng; nếu business cần zero, dùng COALESCE có chủ đích.

### 8.5. ORDER BY và pagination

Nếu pagination yêu cầu thứ tự ổn định, thêm tie-breaker unique:

```sql
SELECT id, created_at
FROM events
ORDER BY created_at DESC, id DESC
LIMIT 50;
```

Không test ordering khi query không khai báo ORDER BY.

### 8.6. Upsert behavior

```sql
INSERT INTO inventory (sku, quantity)
VALUES ('SKU-01', 5)
ON CONFLICT (sku)
DO UPDATE SET quantity = inventory.quantity + EXCLUDED.quantity
RETURNING sku, quantity;
```

Test cả insert path, conflict path, concurrency và expected quantity. Đảm bảo unique constraint đúng là conflict target.

### 8.7. SQLSTATE và error behavior

Nếu ứng dụng phụ thuộc vào error category, assert SQLSTATE thay vì so sánh toàn bộ error message có thể thay đổi theo version/locale. Ví dụ unique violation thường có SQLSTATE 23505; foreign key violation 23503; serialization failure 40001.

### 8.8. Test side effects

Sau INSERT/UPDATE/DELETE, kiểm tra trigger side effects, audit rows, updated timestamps, related aggregates, outbox records, sequence state khi cần và foreign key cascades.

## 9. Kiểm thử functions, procedures và triggers

### 9.1. Function contract

Kiểm tra input types và defaults, return type/shape, NULL handling, volatility/strictness khi là một phần contract, error conditions, permissions và search path assumptions.

### 9.2. Function test bằng SQL

Ví dụ function tính thuế:

```sql
CREATE OR REPLACE FUNCTION calculate_tax(amount numeric, rate numeric)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT round(amount * rate, 2);
$$;
```

Một test có thể kiểm tra:

```sql
SELECT calculate_tax(100.00, 0.10) = 10.00 AS expected_result;
```

Cần thêm cases về NULL, số âm nếu được phép, precision/scale và rounding boundaries.

### 9.3. Procedure và transaction control

Procedure có thể được gọi bằng CALL. Transaction control bên trong procedure có các giới hạn phụ thuộc cách gọi và execution context. Test trong cùng cách ứng dụng sẽ gọi; không suy ra behavior từ một context khác.

### 9.4. Trigger test

Test từng event (INSERT/UPDATE/DELETE), conditional firing, OLD/NEW values, recursion risk và interaction với bulk operations. Assert dữ liệu sau trigger và behavior khi trigger raise exception.

### 9.5. SECURITY DEFINER

Chạy test bằng role không privileged để xác nhận permission boundaries. Kiểm tra owner, search_path an toàn và quyền execute. Một function chạy được dưới superuser không chứng minh app role có quyền đúng.

## 10. Kiểm thử type, collation và time behavior

### 10.1. Numeric

Test precision, scale, rounding, overflow và division. Với money-like values, quyết định rõ numeric scale và rounding policy.

### 10.2. Timestamp

Phân biệt timestamp without time zone với timestamptz. Test session TimeZone, daylight saving boundaries và serialization qua driver.

### 10.3. Text và collation

Test Unicode normalization, case sensitivity, accents, ordering và unique constraints theo collation. Kết quả có thể phụ thuộc provider/version của locale.

### 10.4. JSONB

Test missing key, JSON null, SQL NULL, arrays, nested objects, containment operators và index usage. JSON null và SQL NULL là hai trạng thái khác nhau.

### 10.5. Arrays và ranges

Test empty array, NULL array, NULL element, lower bounds nếu ứng dụng dùng, range inclusive/exclusive bounds, empty ranges và overlap/containment operators.

### 10.6. Enum và domain types

Test valid values, invalid values, casts, defaults và application deserialization. Nếu enum có value mới, kiểm tra clients cũ xử lý unknown values ra sao.

## 11. Chọn framework và công cụ SQL tests

Một số lựa chọn:
- pgTAP: extension cung cấp assertion functions cho PostgreSQL objects và query results.
- pg_prove: runner phổ biến cho pgTAP test files.
- psql scripts: phù hợp smoke tests và test đơn giản có exit-on-error.
- Application test framework: dùng driver thật để kiểm tra SQL được application phát sinh.
- Migration framework: kiểm tra thứ tự/version và chạy schema migrations.
- SQL lint/parser: phát hiện syntax/style/patterns trước runtime.

### 11.1. pgTAP

Ví dụ minh họa:

```sql
BEGIN;
SELECT plan(2);

SELECT has_table('public', 'orders', 'orders table exists');
SELECT col_not_null('public', 'orders', 'id', 'orders id is not null');

SELECT * FROM finish();
ROLLBACK;
```

Tên assertions và argument order cần xác nhận theo pgTAP version đã cài. Test suite có thể chạy trong transaction để rollback test objects/data nếu các test không cần transaction boundary riêng.

### 11.2. psql smoke test

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/smoke.sql
```

ON_ERROR_STOP=1 giúp psql trả lỗi khi statement fail. CI cần kiểm tra exit code, lưu logs và không coi output có dòng ERROR là pass.

### 11.3. Application integration tests

Dùng cùng driver, connection pool và transaction boundary với application. SQL chạy trực tiếp bằng psql có thể khác prepared statement behavior hoặc type mapping trong driver.

### 11.4. Không bắt buộc dùng một framework cho mọi test

pgTAP phù hợp catalog/SQL assertions; application test framework phù hợp business flows; pgbench phù hợp workload. Chọn công cụ theo câu hỏi cần trả lời.

## 12. Kiểm thử giao dịch: mục tiêu và phạm vi

Transaction tests xác nhận nhiều statements được thực hiện như một đơn vị và giữ consistency khi có lỗi hoặc concurrency.

Kiểm tra:
- Atomicity: tất cả thay đổi commit hoặc rollback theo transaction boundary.
- Consistency: constraints/invariants vẫn đúng.
- Isolation: concurrent transactions quan sát hành vi theo isolation level.
- Durability: commit đã xác nhận tồn tại qua restart/failure theo durability configuration.

ACID là khung khái niệm; từng test phải xác định invariant cụ thể.

### 12.1. Atomicity

Nếu một workflow ghi order, order lines và payment record, lỗi ở bước cuối phải rollback những thay đổi nằm trong cùng transaction.

### 12.2. Consistency

Constraints, foreign keys, unique keys và business invariants phải được duy trì trước/sau transaction.

### 12.3. Isolation

Test xem concurrent transactions có tạo lost update, duplicate processing hoặc trạng thái không hợp lệ không.

### 12.4. Durability

Commit durability phụ thuộc cấu hình PostgreSQL, storage và replication policy. Test cần xác định đang kiểm tra local commit, synchronous replica acknowledgment hay disaster recovery guarantee.

## 13. Kiểm thử commit, rollback và savepoints

### 13.1. Commit

```sql
BEGIN;

INSERT INTO accounts (id, balance)
VALUES (1, 100.00);

COMMIT;
```

Sau commit, một connection khác phải nhìn thấy row đã được commit theo isolation semantics.

### 13.2. Rollback

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 25
WHERE id = 1;

ROLLBACK;
```

Sau rollback, balance phải giữ giá trị trước transaction.

### 13.3. Savepoint

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 10
WHERE id = 1;

SAVEPOINT before_optional_step;

UPDATE accounts
SET balance = balance - 1000
WHERE id = 1;

ROLLBACK TO SAVEPOINT before_optional_step;

COMMIT;
```

Test xác nhận phần trước savepoint được commit, phần sau savepoint bị rollback.

### 13.4. Deferred constraints

Một constraint DEFERRABLE có thể được kiểm tra ở cuối transaction thay vì từng statement. Test cả success và failure tại COMMIT; đừng chỉ kiểm tra kết quả statement trước commit.

### 13.5. Sequence behavior khi rollback

Sequence values từ nextval không được trả lại khi transaction rollback. Test không nên giả định ID liên tiếp không có gaps. Đây là behavior có chủ đích để hỗ trợ concurrency.

## 14. Isolation levels trong PostgreSQL

PostgreSQL hỗ trợ:
- Read Committed.
- Repeatable Read.
- Serializable.

READ UNCOMMITTED được xử lý như READ COMMITTED trong PostgreSQL.

### 14.1. Read Committed

Mỗi statement thường thấy snapshot mới tại thời điểm statement bắt đầu. Hai SELECT trong cùng transaction có thể thấy dữ liệu khác nhau nếu transaction khác commit ở giữa.

### 14.2. Repeatable Read

Transaction dùng snapshot ổn định cho các queries thông thường trong transaction. PostgreSQL triển khai theo snapshot isolation; một số anomaly vẫn có thể xảy ra trong các mô hình tổng quát, vì vậy không nên đồng nhất nó với Serializable.

### 14.3. Serializable

PostgreSQL dùng Serializable Snapshot Isolation để phát hiện các dependency có thể tạo anomaly. Một transaction có thể bị abort với serialization failure và cần retry toàn transaction.

### 14.4. Đặt isolation level

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM accounts
WHERE id = 1;

COMMIT;
```

Đặt level trước khi transaction thực hiện query. Test đúng isolation level mà application transaction sử dụng.

## 15. Kiểm thử concurrency bằng nhiều sessions

Một concurrency test cần ít nhất hai connections độc lập. Không thể mô phỏng interleaving thật bằng một connection chạy tuần tự.

### 15.1. Test lost update

Giả sử balance ban đầu là 100. Hai sessions cùng đọc 100, mỗi session trừ 10 rồi ghi lại 90. Kết quả cuối có thể là 90 thay vì 80 nếu ứng dụng dùng read-modify-write không an toàn ở Read Committed.

Schedule minh họa:

```text
Session A                 Session B
---------                 ---------
BEGIN                     BEGIN
SELECT balance = 100      SELECT balance = 100
compute 90                 compute 90
UPDATE balance = 90
                          UPDATE balance = 90
COMMIT                    COMMIT
Final balance may be 90
```

Giải pháp có thể là atomic update:

```sql
UPDATE accounts
SET balance = balance - 10
WHERE id = 1;
```

Hoặc lock row trước khi đọc/sửa, hoặc dùng optimistic concurrency với version column. Test cần xác nhận kết quả cuối đúng theo business rule.

### 15.2. SELECT FOR UPDATE

```sql
BEGIN;

SELECT balance
FROM accounts
WHERE id = 1
FOR UPDATE;

-- Application calculates and writes based on the locked row.

COMMIT;
```

Session thứ hai phải chờ lock hoặc theo behavior được định nghĩa. Test cần xác nhận timeout/retry policy và không giữ lock lâu khi application thực hiện công việc ngoài database.

### 15.3. Deadlock

Tạo hai transactions khóa hai rows theo thứ tự ngược nhau. PostgreSQL phát hiện deadlock và abort một transaction với SQLSTATE 40P01. Test xác nhận ứng dụng xử lý retry phù hợp và transaction retry toàn bộ logic cần thiết.

### 15.4. Serialization failure

Với Serializable, test các schedule có thể gây serialization failure. SQLSTATE 40001 là tín hiệu để retry transaction theo policy. Không retry chỉ statement cuối nếu logic trước đó phụ thuộc snapshot đã bị abort.

### 15.5. Unique conflict

Hai sessions cùng insert một business key. Xác nhận unique constraint bảo vệ invariant và application xử lý 23505 hoặc ON CONFLICT đúng.

### 15.6. Lock timeout và statement timeout

Test khi lock không được cấp trong giới hạn và khi query chạy quá lâu. Phân biệt:
- lock_timeout: thời gian chờ mỗi lần lấy lock.
- statement_timeout: thời gian chạy statement.
- idle_in_transaction_session_timeout: giới hạn session idle trong transaction.

Không đặt timeout toàn cục trong test mà không hiểu tác động tới các statements khác.

## 16. Kiểm thử giao dịch nghiệp vụ

Thay vì chỉ test isolation primitives, viết tests theo workflow.

Ví dụ chuyển tiền giữa hai accounts:
1. Debit account nguồn.
2. Credit account đích.
3. Ghi ledger/audit record.
4. Commit.

Invariant: tổng balance không đổi nếu không có fee, và không account nào vượt quy tắc business.

### 16.1. Concurrent transfers

Chạy nhiều transfers ngược chiều. Lock accounts theo thứ tự ID nhất quán để giảm deadlocks. Test balance, ledger sum và retry behavior.

### 16.2. Idempotency

Một request có thể được gửi lại do timeout/network retry. Dùng idempotency key với unique constraint để cùng một business operation không bị thực hiện hai lần.

### 16.3. Outbox pattern

Nếu transaction vừa cập nhật business rows vừa phát event, ghi outbox row trong cùng transaction. Test rằng rollback không để event giả và retry publisher không làm mất hoặc nhân đôi logical event.

### 16.4. Deferred business validation

Nếu invariant chỉ có thể kiểm tra cuối transaction, cân nhắc deferred constraint hoặc application validation. Test commit boundary và các transaction interleavings.

### 16.5. External side effects

Một transaction PostgreSQL rollback không thể tự thu hồi email, HTTP request hoặc message đã gửi ra ngoài. Kiểm thử workflow phải xác định side effects được phát sau commit qua outbox/worker hay được bù trừ bằng saga.

## 17. Kiểm thử hiệu năng: xác định SLO và workload

Performance test bắt đầu từ yêu cầu, không bắt đầu từ một query benchmark tùy ý.

Xác định expected throughput, p50/p95/p99 latency, peak concurrency, read/write mix, data volume và growth, burst pattern, connection count, lock contention, replication topology, resource limits, maintenance windows và error budget.

### 17.1. Latency percentile

Mean latency có thể che giấu tail latency. Một hệ thống có average 20 ms nhưng p99 2 giây có thể gây timeout ở một nhóm requests. Đo p50, p95 và p99 cùng error rate.

### 17.2. Throughput

Ghi transactions/second, queries/second hoặc business operations/second. Phân biệt throughput ổn định với burst ngắn.

### 17.3. Workload mix

Một benchmark chỉ SELECT không đại diện cho hệ thống có insert/update, vacuum, index maintenance và replication. Dùng mix gần production.

### 17.4. Capacity headroom

Đạt SLO ở 100% CPU trong test không có nhiều headroom cho traffic spike, autovacuum hoặc failover. Xác định mức sử dụng tài nguyên tối đa được chấp nhận.

## 18. Dùng EXPLAIN để hiểu chi phí query

### 18.1. EXPLAIN cơ bản

```sql
EXPLAIN
SELECT *
FROM orders
WHERE customer_id = 42;
```

Plan ước tính cho biết planner dự định thực hiện query như thế nào, không thực thi query.

### 18.2. EXPLAIN ANALYZE

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT *
FROM orders
WHERE customer_id = 42;
```

Lệnh này thực thi statement và báo actual timing/rows/buffers. Chỉ chạy trên query an toàn và môi trường phù hợp. Với UPDATE/DELETE, statement thực sự thay đổi dữ liệu; có thể dùng transaction rollback trong test environment nhưng cần nhớ các side effects ngoài transaction hoặc sequence advancement không nhất thiết được hoàn tác.

### 18.3. Estimated rows và actual rows

Sai lệch lớn giữa estimated và actual rows có thể làm planner chọn join/order/index không phù hợp. Kiểm tra statistics, data skew, correlated columns và expression statistics khi cần.

### 18.4. Buffers và I/O

BUFFERS giúp phân biệt cache hits, reads và temp blocks. Nếu bật track_io_timing, có thể quan sát I/O timing ở các reports hỗ trợ.

### 18.5. Không assert plan text cứng

Planner có thể thay đổi theo PostgreSQL version, statistics và cost settings. Test thường nên assert latency/rows/resource budget hoặc property quan trọng, không buộc plan text giống từng dòng.

### 18.6. Query plan không phải benchmark đầy đủ

Một lần EXPLAIN ANALYZE không đại diện concurrency, cache state, connection pool, network hoặc mixed workload. Dùng nó để chẩn đoán và bổ sung workload benchmark.

## 19. Dùng pg_stat_statements và database statistics

Nếu workload cần theo dõi query-level, pg_stat_statements cung cấp thống kê các normalized statements.

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_written
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Tên cột có thể khác giữa extension versions. Kiểm tra schema thực tế trước khi viết dashboard/test.

### 19.1. Snapshot trước và sau

Lưu counters trước test, chạy workload, lưu counters sau test rồi tính delta. Không so sánh tổng counters tích lũy nếu extension stats chưa reset hoặc test interval khác nhau.

### 19.2. pg_stat_database

Có thể dùng để quan sát transactions, blocks, temp files và conflicts ở mức database. Đây là counters tổng hợp, không thay thế tracing từng request.

### 19.3. pg_stat_activity

Dùng để quan sát active sessions, waits, transaction age và query state trong lúc load test. Cần quyền phù hợp để xem query text/session details.

### 19.4. Lock metrics

Kết hợp pg_locks, pg_stat_activity và application tracing để xác định lock contention. Một query chậm có thể đang chờ lock chứ không tốn CPU.

## 20. Dùng pgbench cho load tests

pgbench là công cụ benchmark đi kèm PostgreSQL. Nó hỗ trợ built-in TPC-B-like workload và custom scripts.

### 20.1. Khởi tạo test data

Ví dụ trên database test riêng:

```bash
pgbench -i -s 10 testdb
```

Scale factor quyết định kích thước dữ liệu built-in. Chọn size theo mục tiêu và storage budget.

### 20.2. Chạy benchmark

```bash
pgbench -c 20 -j 4 -T 120 -P 10 testdb
```

Các tham số ví dụ:
- -c: số clients đồng thời.
- -j: số worker threads phía client.
- -T: thời lượng test.
- -P: chu kỳ in progress.

### 20.3. Custom script

Có thể viết file SQL cho workload nghiệp vụ:

```sql
\set customer_id random(1, 100000)
BEGIN;
SELECT balance
FROM accounts
WHERE id = :customer_id;
COMMIT;
```

Đây chỉ là workload minh họa. Để test write paths, thêm statements có transaction semantics và cleanup/reset phù hợp.

### 20.4. Chuẩn hóa benchmark

Ghi version pgbench, PostgreSQL, command line, client host, dataset scale, settings, connection topology và result logs. Chạy warm-up trước khi lấy số liệu.

### 20.5. Không so sánh hai môi trường không tương đương

Nếu CPU, storage, network hoặc cache khác nhau, ghi rõ. Dùng normalized workload và nhiều runs; không kết luận query engine chậm hơn chỉ từ hai con số trên máy khác nhau.

## 21. Performance tests cho write-heavy workloads

Write workload có chi phí khác read workload:
- WAL generation.
- Index maintenance.
- Foreign key checks.
- Trigger execution.
- Row locks.
- Checkpoint pressure.
- Vacuum/dead tuples.
- Synchronous replication acknowledgment.

### 21.1. Batch insert

So sánh single-row inserts, multi-row inserts và COPY khi chúng phản ánh application path. Đừng tối ưu bằng COPY nếu application thực tế phải xử lý từng transaction nhỏ.

### 21.2. Update amplification

Một update có thể tạo new tuple version, cập nhật indexes và WAL. Đo lượng rows updated, WAL bytes, bloat và vacuum work.

### 21.3. HOT updates

Nếu update chỉ thay đổi columns không thuộc index và page có free space phù hợp, PostgreSQL có thể thực hiện HOT update. Index design và fillfactor ảnh hưởng khả năng này. Không giả định mọi update đều HOT.

### 21.4. Checkpoints và WAL

Load test dài hơn một checkpoint cycle giúp thấy behavior ổn định hơn. Theo dõi WAL generation, checkpoint write/sync time và replication lag.

### 21.5. Vacuum

Chạy write-heavy test đủ lâu để quan sát autovacuum. Test ngắn có thể kết thúc trước khi maintenance pressure xuất hiện.

## 22. Kiểm thử connection pooling và concurrency capacity

Database performance phụ thuộc số connections và cách pooler phân phối sessions.

Kiểm tra application connection pool size, PgBouncer mode, max connections, queueing ở pool, transaction duration, prepared statements, idle-in-transaction sessions, connection churn và failover reconnect storm.

### 22.1. Đừng tăng max_connections để giải quyết mọi vấn đề

Nhiều connections tiêu thụ memory và tăng scheduling/lock contention. Kiểm tra pool sizing, query duration và backpressure trước khi tăng.

### 22.2. Transaction pooling

Transaction pooling có thể hạn chế session-level features. Test prepared statements, temporary tables, session variables, advisory locks và SET assumptions theo pooler mode.

### 22.3. Connection saturation

Load test phải đo thời gian chờ lấy connection ở application pool, không chỉ query execution time trong PostgreSQL.

### 22.4. Reconnect storms

Sau failover/restart, nhiều clients có thể reconnect cùng lúc. Test jitter/backoff và giới hạn connection attempts.

## 23. Kiểm thử hiệu năng cho indexes và planner

### 23.1. Index effectiveness

So sánh query với/không có index trên dataset đại diện. Kiểm tra planner có sử dụng index trong điều kiện thực tế hay không.

### 23.2. Index size và cache

Index lớn có thể chiếm buffer cache và storage. Một index cải thiện một query nhưng làm cache hit của workload khác giảm.

### 23.3. Composite indexes

Thứ tự cột ảnh hưởng query predicates/order. Test query patterns thật; không tạo index theo danh sách columns một cách máy móc.

### 23.4. Partial/expression indexes

Test predicate/expression khớp với query và semantics của function. Expression volatility và collation có thể ảnh hưởng khả năng dùng index.

### 23.5. Statistics

Sau load/restore/backfill, chạy ANALYZE phù hợp. Test cả data skew và correlated columns; average distribution có thể làm estimates sai.

## 24. Thiết kế performance test ổn định

Một benchmark đáng tin cần kiểm soát biến số.

1. Pin PostgreSQL/extension versions.
2. Dùng hardware/storage hoặc resource limits tương đương.
3. Tạo dataset đại diện.
4. Chạy ANALYZE và trạng thái vacuum phù hợp.
5. Xác định cold/warm cache strategy.
6. Warm-up trước khi đo.
7. Chạy nhiều lần.
8. Ghi p50/p95/p99 và throughput.
9. Ghi CPU, memory, I/O, WAL, locks và replica lag.
10. Định nghĩa regression budget.
11. Lưu raw logs và command lines.
12. So sánh cùng workload và cùng duration.

### 24.1. Cold cache và warm cache

Cold-cache testing có thể cần restart/clear caches ở môi trường chuyên dụng; không có cách an toàn phổ quát để xóa toàn bộ OS cache trên mọi platform. Ghi rõ phương pháp. Warm-cache test cần warm-up nhất quán.

### 24.2. Data scale

Dùng nhiều scale points nếu growth là yếu tố quan trọng: nhỏ, hiện tại và dự kiến. Query plan và index/cache behavior có thể thay đổi khi dataset vượt memory.

### 24.3. Load shape

Kiểm tra constant load, ramp-up, burst và soak test. Soak test phát hiện bloat, memory growth, worker leaks và degradation theo thời gian.

### 24.4. Regression budget

Ví dụ team có thể đặt ngưỡng:
- p95 critical query không tăng quá 10%.
- Throughput không giảm quá 5%.
- Error rate không vượt SLO.
- Replica lag không vượt replication budget.

Đây là ví dụ. Chọn ngưỡng dựa trên baseline, SLO và business impact.

## 25. Kết hợp bốn nhóm test trong một feature change

Giả sử feature mới thêm orders.status và query tổng hợp doanh thu theo status.

**Schema tests**
- Cột status đúng type/default/nullability.
- Check constraint hoặc enum đúng.
- Index phù hợp tồn tại và valid.
- Migration từ source schema có dữ liệu chạy được.

**SQL tests**
- Query aggregate trả đúng tổng.
- NULL/unknown status được xử lý theo policy.
- Filter theo time range và status đúng.
- Function/view trả đúng shape.

**Transaction tests**
- Order state transition không tạo trạng thái bất hợp lệ.
- Hai workers không xử lý cùng order hai lần.
- Rollback khi payment step fail.
- Concurrent update được serialize hoặc conflict xử lý đúng.

**Performance tests**
- Aggregate query đạt latency budget.
- Index không làm write throughput giảm quá budget.
- Query vẫn ổn ở peak concurrency và dataset lớn.
- WAL/replica lag nằm trong giới hạn.

Một feature chỉ hoàn tất khi mỗi lớp có evidence phù hợp.

## 26. Kiểm thử data migration và backfill

Backfill là workload ghi dữ liệu lớn, nên cần kết hợp schema, SQL, transaction và performance tests.

### 26.1. Correctness

Assert mapping đúng cho mọi category và edge cases. Với bảng lớn, dùng reconciliation theo key ranges hoặc checksums đã canonicalize.

### 26.2. Idempotency

Chạy lại batch hoặc restart worker giữa chừng. Kết quả phải đúng và không ghi đè changes mới hơn.

### 26.3. Transaction boundaries

Mỗi batch nên có commit boundary rõ. Test crash sau commit nhưng trước progress marker, hoặc ngược lại, để bảo đảm resume logic không bỏ sót/nhân đôi.

### 26.4. Concurrency

Chạy backfill cùng application writes. Test race condition giữa row snapshot và update mới. Dùng predicate/versioning/locking theo design.

### 26.5. Performance

Đo batch duration, WAL, replica lag, lock waits, dead tuples và vacuum. Tạo pause/resume thresholds.

### 26.6. Recovery

Test khi worker fail, connection mất, replica chậm hoặc disk gần ngưỡng. Không chỉ test happy path hoàn tất từ đầu tới cuối.

## 27. Security và permission tests

Dù bài học tập trung vào bốn nhóm chính, permissions là một phần của schema và SQL contract.

Kiểm tra:
- Application role chỉ có quyền cần thiết.
- Read-only role không thể mutate.
- Migration role có DDL permissions phù hợp.
- Function execution grants đúng.
- RLS policies lọc rows đúng.
- SECURITY DEFINER không mở privilege escalation.
- search_path không cho phép object shadowing.
- Sensitive columns không bị lộ qua views/logs.

Chạy tests bằng role thực tế, không chỉ bằng database owner.

## 28. CI/CD: tổ chức các stage

Một pipeline tham khảo:

```text
Commit / Pull Request
        |
        v
Static SQL and migration checks
        |
        v
Create ephemeral PostgreSQL
        |
        v
Apply migrations
        |
        v
Schema assertions
        |
        v
SQL behavior tests
        |
        v
Transaction/concurrency tests
        |
        v
Build and package
        |
        v
Staging performance / load suite
        |
        v
Release gate
```

### 28.1. Pull request stage

Chạy static checks, schema creation, migration tests, SQL unit tests và transaction tests nhanh. Nếu cần nhiều PostgreSQL versions, dùng matrix jobs.

### 28.2. Nightly stage

Chạy dataset lớn hơn, randomized/property tests, concurrency schedules, soak tests và performance regression suite.

### 28.3. Pre-release stage

Chạy migration từ snapshot gần production, backup/restore, failover, peak load và operational acceptance.

### 28.4. Deployment gate

Không deploy khi schema migration fail hoặc critical SQL/transaction regression còn mở. Performance regressions cần severity/threshold rõ; tránh fail pipeline vì noise không có ý nghĩa.

### 28.5. Artifact và evidence

Lưu PostgreSQL version/image digest, migration logs, test report, SQLSTATE/error details, EXPLAIN plans quan trọng, benchmark command/result, environment settings và dataset seed/version.

## 29. Test parallelism và isolation

Test chạy song song có thể tạo contention và kết quả flaky.

### 29.1. Database per worker

Tạo database/schema riêng cho mỗi worker hoặc test shard. Không dùng cùng fixed IDs trong shared database.

### 29.2. Shared resources

Nếu tests cùng dùng cluster, chúng vẫn tranh CPU, I/O và connections. Không chạy performance tests song song với correctness suites trên cùng instance nếu kết quả performance cần ổn định.

### 29.3. Advisory locks

Có thể dùng advisory locks để điều phối test resource chung, nhưng cần namespace/key scheme rõ và luôn release đúng cách.

### 29.4. Flaky transaction tests

Dùng barriers/latches và explicit schedule thay vì sleep tùy tiện. Sleep-based tests dễ phụ thuộc tốc độ runner và gây flaky.

### 29.5. Cleanup khi test fail

Đảm bảo connections đóng, transactions rollback và test database được drop ngay cả khi assertion fail. Với process crash, dùng job cleanup/ephemeral instance lifecycle.

## 30. Test report: báo cáo riêng từng lớp

Một report hữu ích có thể trình bày:

| Nhóm | Passed | Failed | Skipped | Thời gian | Evidence |
|---|---:|---:|---:|---:|---|
| Schema |  |  |  |  | Migration/catalog assertions |
| SQL |  |  |  |  | Query/function results |
| Transaction |  |  |  |  | Multi-session schedules |
| Performance |  |  |  |  | Latency/throughput/resource logs |

Không gộp tất cả thành một dòng “database tests passed”. Một test suite có thể pass SQL nhưng transaction test chưa chạy; report phải thể hiện rõ.

### 30.1. Failure classification

- Schema failure: migration, object definition, dependency hoặc permission.
- SQL failure: syntax, semantics, data mapping hoặc expected result.
- Transaction failure: isolation, lock, deadlock, retry hoặc atomicity.
- Performance failure: latency, throughput, resource saturation hoặc regression.

### 30.2. Reproducibility

Ghi command, seed, version và environment. Nếu lỗi chỉ xảy ra ở concurrency test, lưu schedule và session logs.

### 30.3. Avoid false pass

Test bị skipped do thiếu extension hoặc permission không nên được báo chung là pass. Phân biệt skipped, not applicable và failed.

## 31. Chẩn đoán khi từng lớp thất bại

### 31.1. Schema test fail

Kiểm tra migration có chạy đúng thứ tự không, catalog definition có đúng PostgreSQL version không, search_path/schema owner có khác không, extension/package có sẵn không, constraint/index có valid/validated không và test đang kiểm tra đúng contract hay chi tiết nội bộ không ổn định.

### 31.2. SQL test fail

Kiểm tra fixture có đúng và deterministic không, NULL/duplicate/ordering semantics có được xác định không, session settings như timezone/search_path/collation có khác không, driver có type mapping khác psql không, trigger/function có side effects không và SQLSTATE có khác dự kiến không.

### 31.3. Transaction test fail

Kiểm tra isolation level thực tế, transaction boundaries/autocommit, lock order/blocker chain, retry policy cho 40001/40P01, idempotency/duplicate requests và test schedule có xác định hay dựa vào timing ngẫu nhiên.

### 31.4. Performance test fail

Kiểm tra dataset/statistics/cache state, query plan/estimated rows, CPU/memory/I/O saturation, lock waits/connection pool queue, WAL/checkpoint/vacuum và regression có tái lập ở nhiều runs không.

## 32. Những anti-patterns cần tránh

- Chỉ test database startup.
- Chỉ assert object tồn tại mà không kiểm tra definition.
- Chạy tất cả tests bằng superuser.
- Dùng fixtures khác schema production.
- Phụ thuộc row order không có ORDER BY.
- Không test NULL và boundary values.
- Dùng một session để tuyên bố transaction concurrency an toàn.
- Dùng sleep cố định để điều khiển concurrency.
- Chỉ đo average latency.
- Benchmark trên dataset quá nhỏ.
- Chạy performance suite trên shared runner đang tải không kiểm soát.
- Assert exact EXPLAIN text qua nhiều PostgreSQL versions.
- Chạy EXPLAIN ANALYZE trên destructive statement mà không cô lập.
- Coi rollback sẽ undo sequence values hoặc external side effects.
- Chỉ test migration từ database rỗng.
- Bỏ qua migration failure/retry.
- Coi test skipped là pass.
- Không lưu environment, seed và raw evidence.

## 33. Ví dụ test plan cho một release

Giả sử release thêm bảng payments, function tính phí và workflow capture payment.

| Test ID | Nhóm | Kịch bản | Kết quả mong đợi |
|---|---|---|---|
| DB-S-01 | Schema | Apply migration trên DB rỗng | Bảng, PK, FK, index đúng |
| DB-S-02 | Schema | Upgrade DB có orders cũ | Rows cũ được giữ nguyên |
| DB-Q-01 | SQL | Tính fee cho amount chuẩn | Giá trị đúng rounding rule |
| DB-Q-02 | SQL | Amount NULL/negative | Behavior theo domain |
| DB-Q-03 | SQL | Duplicate external reference | Unique violation/ON CONFLICT đúng |
| DB-T-01 | Transaction | Payment step fail | Order/payment changes rollback |
| DB-T-02 | Transaction | Hai workers capture cùng order | Chỉ một logical capture |
| DB-T-03 | Transaction | Serialization/deadlock retry | Workflow retry an toàn |
| DB-P-01 | Performance | Capture ở peak concurrency | p95/p99 trong SLO |
| DB-P-02 | Performance | Bulk payment ingest | Throughput và WAL trong budget |
| DB-P-03 | Performance | Reporting query | Plan và latency đạt budget |

### 33.1. Entry criteria

- Migrations đã review.
- Test database có đúng PostgreSQL target.
- Fixtures và seed được version hóa.
- Expected business rules được phê duyệt.
- Performance thresholds được xác định.

### 33.2. Exit criteria

- Không còn schema/SQL/transaction blocker.
- Performance đạt SLO hoặc có risk acceptance.
- Test report có evidence.
- Skipped tests có lý do và owner.
- Known issues có severity, mitigation và deadline.

## 34. Checklist schema tests

- [ ] Tạo database rỗng và apply toàn bộ migrations.
- [ ] Upgrade từ các source schema versions được hỗ trợ.
- [ ] Kiểm tra schemas, tables và partitions.
- [ ] Kiểm tra column types, defaults, identity/generated và nullability.
- [ ] Kiểm tra PK/FK/UNIQUE/CHECK và deferrability.
- [ ] Kiểm tra indexes, expressions, predicates và validity.
- [ ] Kiểm tra views/materialized views.
- [ ] Kiểm tra functions/procedures/signatures.
- [ ] Kiểm tra triggers và event behavior.
- [ ] Kiểm tra sequences, enums, domains và extensions.
- [ ] Kiểm tra grants, roles và RLS.
- [ ] Kiểm tra migration history và failure recovery.

## 35. Checklist SQL tests

- [ ] Test expected rows và values.
- [ ] Test NULL/empty/zero semantics.
- [ ] Test joins và duplicate cardinality.
- [ ] Test aggregates trên empty sets.
- [ ] Test ordering và pagination stability.
- [ ] Test INSERT/UPDATE/DELETE/UPSERT.
- [ ] Test functions, procedures và triggers.
- [ ] Test SQLSTATE/error behavior.
- [ ] Test numeric/date/time/JSON/array/collation edge cases.
- [ ] Test permissions bằng application roles.
- [ ] Test side effects và audit/outbox records.
- [ ] Test bằng driver thật của ứng dụng.

## 36. Checklist transaction tests

- [ ] Test commit và rollback.
- [ ] Test savepoints.
- [ ] Test deferred constraints tại commit.
- [ ] Test sequence behavior khi rollback.
- [ ] Test Read Committed/Repeatable Read/Serializable theo use case.
- [ ] Test lost update và concurrent upsert.
- [ ] Test row locks và lock timeout.
- [ ] Test deadlock detection/retry.
- [ ] Test serialization failure/retry.
- [ ] Test idempotency và duplicate request.
- [ ] Test outbox/external side effects.
- [ ] Test nhiều sessions với schedule xác định.

## 37. Checklist performance tests

- [ ] Xác định SLO, workload mix và concurrency.
- [ ] Ghi PostgreSQL version/config/hardware.
- [ ] Dùng dataset đại diện và có skew.
- [ ] Warm-up và nhiều lần đo.
- [ ] Ghi p50/p95/p99, throughput và error rate.
- [ ] Thu EXPLAIN ANALYZE/BUFFERS cho critical queries.
- [ ] Theo dõi CPU, memory, I/O và temp files.
- [ ] Theo dõi WAL, checkpoints, vacuum và replica lag.
- [ ] Đo connection pool queue và lock waits.
- [ ] Test read-heavy, write-heavy, mixed, burst và soak.
- [ ] Định nghĩa regression budget.
- [ ] Lưu raw results và benchmark commands.

## 38. Best practices

- Tách schema assertions, SQL behavior, transaction schedules và load benchmarks thành suites riêng.
- Chạy test trên PostgreSQL version thực tế/target.
- Dùng fixtures deterministic và database isolation.
- Assert behavior/contract quan trọng thay vì catalog internals không ổn định.
- Kiểm tra migrations từ schema cũ có dữ liệu.
- Dùng application roles và driver thật.
- Điều khiển concurrency bằng barriers thay vì sleep.
- Test retry cho SQLSTATE 40001 và 40P01 khi workflow có thể gặp.
- Đo tail latency, throughput và resource metrics.
- Tách correctness CI khỏi performance runners có môi trường kiểm soát.
- Lưu test evidence và phân loại skipped/failed.
- Cập nhật test plan khi schema, PostgreSQL major hoặc workload thay đổi.

## 39. Tài liệu chính thức tham khảo

- [PostgreSQL — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): constraint semantics.
- [PostgreSQL — Information Schema](https://www.postgresql.org/docs/current/information-schema.html): schema metadata views.
- [PostgreSQL — System Catalogs](https://www.postgresql.org/docs/current/catalogs.html): catalog definitions.
- [PostgreSQL — Transactions](https://www.postgresql.org/docs/current/tutorial-transactions.html): transaction basics.
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): isolation levels and anomalies.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): row/table locks and deadlocks.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): plan inspection and execution.
- [PostgreSQL — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): database and session statistics.
- [PostgreSQL — pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html): query-level statistics.
- [PostgreSQL — pgbench](https://www.postgresql.org/docs/current/pgbench.html): benchmark tool.
- [PostgreSQL — Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html): SQLSTATE categories.
- [pgTAP](https://pgtap.org/documentation.html): SQL testing assertions for PostgreSQL.

Các đường dẫn /current/ thay đổi theo tài liệu phiên bản hiện hành. Khi viết tests cho một production cluster, dùng manual đúng major version và version thực tế của extensions/frameworks liên quan.

## 40. Tổng kết

Tách kiểm thử schema, SQL, giao dịch và hiệu năng giúp xác định chính xác điều gì đang được chứng minh:

1. **Schema tests** xác nhận cấu trúc và migration tạo đúng contract.
2. **SQL tests** xác nhận statements, functions, triggers và business results đúng với dữ liệu biên.
3. **Transaction tests** xác nhận atomicity, isolation, locking, retry và consistency khi nhiều sessions cùng hoạt động.
4. **Performance tests** xác nhận latency, throughput và resource usage đạt yêu cầu trên workload đại diện.

Bốn nhóm cần dùng chung fixtures, version và business expectations nhưng giữ assertions và evidence riêng. Khi một release thay đổi schema hoặc SQL, chạy correctness tests trước; khi logic và consistency đã đúng, đo hiệu năng trong môi trường kiểm soát. Một release database đáng tin cậy cần chứng minh cả dữ liệu đúng, giao dịch an toàn và workload đáp ứng SLO.
