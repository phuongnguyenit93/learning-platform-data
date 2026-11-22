# Kiểm thử hàm, thủ tục và trigger với pgTAP hoặc SQL script trong PostgreSQL

Functions, procedures và triggers đưa logic nghiệp vụ vào bên trong PostgreSQL. Chúng có thể tính toán giá trị, thay đổi nhiều bảng, kiểm tra invariants, ghi audit records hoặc tự động chạy khi dữ liệu thay đổi. Vì logic nằm sát dữ liệu, một lỗi nhỏ trong routine có thể ảnh hưởng nhiều application paths cùng lúc. Kiểm thử trực tiếp trong database giúp phát hiện lỗi về kết quả, side effects, exceptions, privileges, trigger wiring và schema contract trước khi thay đổi được triển khai.

PostgreSQL không đi kèm một framework unit testing chuyên biệt trong core. Có thể viết test bằng SQL script thuần, dùng các assertions tự xây dựng, hoặc cài **pgTAP** để viết test theo Test Anything Protocol (TAP). pgTAP cung cấp assertions cho giá trị, query results, exceptions và metadata của database objects. SQL script thuần có ít dependencies hơn và phù hợp với integration tests nhỏ hoặc môi trường không cho cài extension.

Bài học thuộc chương **Kiểm thử**, tập trung vào:

- Phân biệt unit tests, database integration tests và migration/schema tests.
- Chuẩn bị test database, role, fixtures và dữ liệu có thể lặp lại.
- Cài đặt và chạy pgTAP bằng pg_prove hoặc psql.
- Dùng plan, finish, ok, is, throws_ok, lives_ok và results_eq.
- Kiểm thử function scalar, set-returning function, NULL, boundary values và errors.
- Kiểm thử procedure qua CALL, side effects và transaction behavior.
- Kiểm thử trigger definition, trigger function, event, timing và row-level effects.
- Xác nhận function/procedure metadata, security mode, volatility và trigger wiring.
- Kiểm tra permissions, SECURITY DEFINER, RLS và execution context bằng đúng runtime role.
- Viết SQL test harness thuần với DO block, assertions và transaction rollback.
- Quản lý fixtures, test isolation, deterministic results và parallel test execution.
- Tích hợp tests vào CI, migration pipeline và release verification.

> **Nguyên tắc:** test một routine cần kiểm tra cả kết quả trả về và trạng thái dữ liệu sau khi chạy. Với trigger, cần chứng minh đúng event đã kích hoạt đúng function và tạo đúng side effects. Với function/procedure có quyền đặc biệt, test phải chạy bằng role đại diện cho caller thật; chạy mọi thứ bằng superuser có thể che giấu lỗi permission và RLS.

## 1. Xác định đúng phạm vi kiểm thử

Functions, procedures và triggers có cách gọi và tác động khác nhau. Chọn loại test phù hợp giúp phát hiện lỗi ở đúng boundary.

### 1.1. Function

Function được gọi trong biểu thức SQL, SELECT, FROM, WHERE, DEFAULT, CHECK, index expression hoặc từ routine khác. Function có thể:

- Trả về một scalar value.
- Trả về một tập rows bằng SETOF hoặc RETURNS TABLE.
- Nhận IN/OUT/INOUT arguments.
- Phát sinh exception.
- Có side effects nếu function cho phép và được thiết kế như vậy.

Test function nên xác nhận signature, return type, kết quả, NULL semantics, boundary conditions, exceptions và side effects được phép.

### 1.2. Procedure

Procedure được gọi bằng CALL. Khác function, procedure không được dùng như một biểu thức trong SELECT và có thể hỗ trợ transaction control trong những điều kiện phù hợp.

Test procedure nên kiểm tra:

- CALL có thành công không.
- Rows/columns nào bị thay đổi.
- OUT/INOUT parameters nếu có.
- Behavior khi input không hợp lệ hoặc target row không tồn tại.
- Idempotency và retry behavior.
- Transaction boundaries nếu procedure có COMMIT/ROLLBACK.

Procedure thực hiện transaction control không thể được gọi trong một transaction block do test harness mở sẵn. Những trường hợp này cần integration test riêng trên database dùng riêng.

### 1.3. Trigger

Trigger được PostgreSQL gọi tự động khi xảy ra event như INSERT, UPDATE, DELETE hoặc TRUNCATE. Trigger có thể chạy:

- BEFORE hoặc AFTER.
- FOR EACH ROW hoặc FOR EACH STATEMENT.
- Theo WHEN condition.
- Trên table, view hoặc event DDL theo trigger type phù hợp.
- Trước/sau các triggers khác theo ordering rules của PostgreSQL.

Test trigger cần xác nhận cả cấu hình trigger và kết quả sau event. Chỉ gọi trigger function trực tiếp không chứng minh trigger đã được gắn đúng hoặc được kích hoạt đúng thời điểm.

### 1.4. Phân biệt các lớp test

| Lớp test | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Unit test routine | Kiểm tra behavior nhỏ, đầu vào/đầu ra rõ | calculate_discount(1000) trả 100 |
| Database integration test | Kiểm tra routine cùng tables, constraints, triggers và roles | CALL procedure cập nhật order và audit row |
| Schema contract test | Kiểm tra function, procedure, trigger tồn tại đúng signature/config | Function là SECURITY INVOKER, trigger gọi đúng function |
| Migration test | Kiểm tra schema mới sau khi áp dụng migrations | Routine và trigger vẫn tồn tại sau upgrade |
| Concurrency test | Kiểm tra race conditions, locks và isolation | Hai sessions cùng xử lý một order |
| Performance test | Đo latency/throughput dưới workload | Function chạy trong query 10.000 rows |

Một test suite có thể chứa nhiều lớp, nhưng cần biết mỗi test đang chứng minh điều gì.

## 2. pgTAP là gì?

pgTAP là extension kiểm thử cho PostgreSQL. Nó cung cấp các assertion functions trả kết quả theo TAP để test runner có thể phân tích.

### 2.1. TAP output

TAP là định dạng văn bản đơn giản. Một test suite có thể tạo output:

```text
1..3
ok 1 - function exists
ok 2 - discount is calculated
not ok 3 - negative amount is rejected
```

Mỗi dòng ok hoặc not ok tương ứng một assertion. Runner có thể tổng hợp kết quả, báo file test lỗi và làm CI thất bại.

### 2.2. pgTAP chạy trong database

pgTAP được cài như extension trong database:

```sql
CREATE EXTENSION IF NOT EXISTS pgtap;
```

Package/binary của pgTAP phải có trên host/container PostgreSQL trước khi chạy CREATE EXTENSION. Việc cài package trên máy developer không tự động cài extension vào server từ xa.

### 2.3. pgTAP không thay thế test runner

pgTAP cung cấp assertions và TAP output. Có thể dùng:

- pg_prove để chạy nhiều SQL test files và tổng hợp TAP.
- psql để chạy script trực tiếp.
- Build/CI tooling có hỗ trợ TAP.
- Hàm runtests() của pgTAP cho phong cách xUnit trong database.

pg_prove là client-side test runner được phân phối riêng, không phải lệnh SQL của PostgreSQL.

### 2.4. Khi nào chọn pgTAP?

pgTAP hữu ích khi:

- Cần nhiều assertions cho database objects.
- Muốn kiểm tra function signatures và trigger wiring.
- Cần test exceptions với SQLSTATE.
- Muốn kết quả TAP để CI phân tích.
- Muốn gom nhiều SQL files thành một suite có report.

SQL script thuần phù hợp khi:

- Môi trường không cho cài extension.
- Test đơn giản, số lượng nhỏ.
- Muốn giảm dependency ngoài PostgreSQL client.
- Cần kiểm thử một procedure transaction-control không chạy được trong pgTAP transaction wrapper.

## 3. Chuẩn bị môi trường test

Không chạy thử routines có side effects trên production data. Tạo database test riêng với schema, roles và fixtures có thể tái tạo.

### 3.1. Cài package pgTAP trên PostgreSQL host

Trên Debian/Ubuntu, package thường có tên pgtap; package version và tên có thể khác theo PostgreSQL major version/distribution.

Ví dụ cài package tương thích với server:

```bash
sudo apt-get install postgresql-17-pgtap
```

Đây chỉ là ví dụ cho một major version. Kiểm tra repository/package manager của OS và phiên bản PostgreSQL thực tế. Với Docker, extension files phải nằm trong image/container đang chạy PostgreSQL.

### 3.2. Cài extension trong test database

Kết nối vào database test bằng role quản trị phù hợp:

```sql
CREATE EXTENSION IF NOT EXISTS pgtap;
```

Có thể cài trong schema riêng nếu extension và policy hỗ trợ:

```sql
CREATE SCHEMA IF NOT EXISTS test_support;
CREATE EXTENSION IF NOT EXISTS pgtap
    WITH SCHEMA test_support;
```

Nếu cài trong schema riêng, điều chỉnh search_path hoặc gọi pgTAP functions bằng schema qualification. Không thêm schema test vào search_path của application runtime chỉ để test dễ hơn.

### 3.3. Kiểm tra extension

```sql
SELECT
    extname,
    extversion,
    extnamespace::regnamespace AS extension_schema
FROM pg_extension
WHERE extname = 'pgtap';
```

Kiểm tra phiên bản pgTAP đang cài:

```sql
SELECT pgtap_version();
```

### 3.4. Tạo database test riêng

Ví dụ:

```sql
CREATE DATABASE app_test;
```

Cài schema migrations và pgTAP vào database này. Nếu CI tạo database ephemeral cho mỗi job, mỗi job có thể chạy song song mà không tranh chấp fixtures.

### 3.5. Tách roles

Có thể dùng các roles riêng:

| Role | Mục đích |
| --- | --- |
| migration_owner | Tạo/alter schema objects |
| app_runtime | Chạy functions/procedures như application |
| test_runner | Kết nối và chạy test suite |
| test_admin | Tạo database/roles/extensions trong môi trường test |

Không dùng superuser cho toàn bộ assertions về permissions. Có thể dùng role quản trị để tạo fixtures, rồi chạy nhóm tests dưới runtime role cần kiểm tra.

## 4. Chuẩn bị schema minh họa

Các ví dụ sau dùng schema app và audit. Tạo chúng trong database test hoặc lab:

```sql
CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE app.orders (
    id bigint PRIMARY KEY,
    status text NOT NULL,
    total_amount numeric(12, 2) NOT NULL,
    review_required boolean NOT NULL DEFAULT false,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE audit.order_status_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL,
    old_status text NOT NULL,
    new_status text NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
```

Bảng audit ở ví dụ không có foreign key tới orders để giữ lịch sử ngay cả khi order được archive hoặc xóa. Thiết kế thực tế cần chọn retention và referential behavior phù hợp.

### 4.1. Function cần kiểm thử

```sql
CREATE OR REPLACE FUNCTION app.calculate_discount(p_amount numeric)
RETURNS numeric
LANGUAGE plpgsql
IMMUTABLE
STRICT
AS $function$
BEGIN
    IF p_amount < 0 THEN
        RAISE EXCEPTION
            USING ERRCODE = '22003',
                  MESSAGE = 'amount must be nonnegative';
    END IF;

    IF p_amount >= 1000 THEN
        RETURN round(p_amount * 0.10, 2);
    END IF;

    RETURN 0;
END;
$function$;
```

Function có contract:

- NULL input trả NULL vì STRICT.
- Amount âm tạo exception SQLSTATE 22003.
- Amount dưới 1000 không có discount.
- Amount từ 1000 trở lên nhận 10%.

### 4.2. Set-returning function

```sql
CREATE OR REPLACE FUNCTION app.open_order_ids()
RETURNS TABLE(order_id bigint)
LANGUAGE sql
STABLE
AS $function$
    SELECT o.id
    FROM app.orders AS o
    WHERE o.status = 'pending'
    ORDER BY o.id;
$function$;
```

### 4.3. Procedure cần kiểm thử

```sql
CREATE OR REPLACE PROCEDURE app.mark_order_reviewed(p_order_id bigint)
LANGUAGE plpgsql
AS $procedure$
BEGIN
    UPDATE app.orders
    SET review_required = true,
        updated_at = clock_timestamp()
    WHERE id = p_order_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            USING ERRCODE = 'P0002',
                  MESSAGE = 'order not found';
    END IF;
END;
$procedure$;
```

Procedure không tự COMMIT; nó tham gia transaction của caller. Vì vậy có thể kiểm thử trong transaction mà cuối script ROLLBACK để dọn fixture.

### 4.4. Trigger function và trigger

```sql
CREATE OR REPLACE FUNCTION audit.capture_order_status()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    INSERT INTO audit.order_status_events (
        order_id,
        old_status,
        new_status
    )
    VALUES (
        NEW.id,
        OLD.status,
        NEW.status
    );

    RETURN NEW;
END;
$function$;

CREATE TRIGGER orders_status_audit_trg
AFTER UPDATE OF status ON app.orders
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION audit.capture_order_status();
```

Trigger chỉ ghi audit khi column status nằm trong UPDATE target list và giá trị thực sự thay đổi. Trigger function sử dụng OLD/NEW nên được thiết kế cho UPDATE row-level trigger.

## 5. Cấu trúc một pgTAP test file

Một test file thường có ba phần:

1. Mở transaction và chuẩn bị fixture.
2. Khai báo số lượng assertions bằng plan().
3. Chạy assertions, gọi finish() và rollback.

Ví dụ:

```sql
BEGIN;

SELECT plan(3);

SELECT ok(true, 'basic assertion works');
SELECT is(1 + 1, 2, 'addition returns two');
SELECT isnt('pending', 'paid', 'statuses differ');

SELECT * FROM finish();

ROLLBACK;
```

### 5.1. plan()

plan(n) khai báo số assertions dự kiến. Nếu script chạy thiếu hoặc thừa test, pgTAP có thể báo mismatch.

```sql
SELECT plan(5);
```

Ưu tiên plan cố định khi số tests đã biết. Nó giúp phát hiện test branch không chạy hoặc file kết thúc sớm.

### 5.2. no_plan()

no_plan() cho phép không khai báo trước số test:

```sql
SELECT * FROM no_plan();
```

Dùng khi số assertions thực sự không biết trước. Hạn chế sử dụng vì có thể che việc một nhánh test bị bỏ qua.

### 5.3. finish()

Cuối suite gọi:

```sql
SELECT * FROM finish();
```

finish() tổng kết kết quả và phát hiện số assertions không khớp plan. Có thể dùng finish(true) để yêu cầu phát sinh exception khi test thất bại, hữu ích khi chạy bằng psql với ON_ERROR_STOP.

### 5.4. Transaction rollback

Test suite thường dùng:

```sql
BEGIN;
-- setup và assertions
SELECT * FROM finish();
ROLLBACK;
```

ROLLBACK dọn dữ liệu test và cả những DDL transactional trong suite. Không đặt thao tác transaction-control procedure vào wrapper này.

### 5.5. Test setup không được tính vào plan

CREATE TABLE, INSERT fixtures và SET LOCAL không phải assertions. Chỉ tính số calls tới test functions trong plan(n). Đếm kỹ các nhánh có skip() hoặc loop tạo test động.

## 6. Assertions cơ bản

### 6.1. ok()

Kiểm tra một biểu thức boolean:

```sql
SELECT ok(
    app.calculate_discount(1000) = 100,
    'discount for amount 1000 is 100'
);
```

Nếu expression trả NULL, test không được coi là pass. Khi kiểm tra nullable values, dùng is() hoặc predicate IS NULL.

### 6.2. is() và isnt()

So sánh hai giá trị:

```sql
SELECT is(
    app.calculate_discount(500),
    0::numeric,
    'amount below threshold has no discount'
);

SELECT isnt(
    app.calculate_discount(1200),
    0::numeric,
    'eligible amount has a discount'
);
```

Nên cast expected values về đúng type để tránh ambiguity của overloaded assertion functions.

### 6.3. cmp_ok()

So sánh theo operator:

```sql
SELECT cmp_ok(
    app.calculate_discount(1500),
    '>',
    0::numeric,
    'discount is positive'
);
```

Dùng khi muốn biểu đạt một điều kiện lớn hơn, nhỏ hơn hoặc bằng mà không cần tự tạo boolean expression.

### 6.4. isa_ok()

Kiểm tra type của giá trị:

```sql
SELECT isa_ok(
    app.calculate_discount(1000),
    'numeric',
    'discount result'
);
```

### 6.5. diag()

Ghi diagnostic text không làm nhiễu TAP result:

```sql
SELECT diag(
    'server version: ' || current_setting('server_version')
);
```

Diagnostic nên cung cấp context hữu ích khi fail, không ghi secrets hoặc dữ liệu nhạy cảm.

## 7. Kiểm thử function bằng pgTAP

Một function test cần xác nhận cả behavior và object contract.

### 7.1. Kiểm tra function tồn tại

```sql
SELECT has_function(
    'app',
    'calculate_discount',
    ARRAY['numeric'],
    'calculate_discount(numeric) exists'
);
```

Signature quan trọng vì PostgreSQL hỗ trợ function overloading. Chỉ kiểm tra tên có thể không phát hiện một overload sai hoặc function đúng signature bị thiếu.

### 7.2. Kiểm tra return type

```sql
SELECT function_returns(
    'app',
    'calculate_discount',
    ARRAY['numeric'],
    'numeric',
    'calculate_discount returns numeric'
);
```

Với set-returning function, type argument dùng dạng setof ... theo cú pháp pgTAP.

### 7.3. Kiểm tra language và volatility

```sql
SELECT function_lang_is(
    'app',
    'calculate_discount',
    ARRAY['numeric'],
    'plpgsql',
    'discount function uses PL/pgSQL'
);

SELECT volatility_is(
    'app',
    'calculate_discount',
    ARRAY['numeric'],
    'immutable',
    'discount function is immutable'
);
```

Volatility là contract với planner. Chỉ assert IMMUTABLE nếu implementation thật sự không phụ thuộc database state, clock, sequence hoặc mutable external state.

### 7.4. Kiểm tra kết quả và boundary values

```sql
SELECT is(
    app.calculate_discount(0),
    0::numeric,
    'zero amount has zero discount'
);

SELECT is(
    app.calculate_discount(999.99),
    0::numeric,
    'amount just below threshold has no discount'
);

SELECT is(
    app.calculate_discount(1000),
    100::numeric,
    'threshold amount receives ten percent'
);

SELECT is(
    app.calculate_discount(1250),
    125::numeric,
    'larger amount receives ten percent'
);

SELECT is(
    app.calculate_discount(NULL::numeric),
    NULL::numeric,
    'strict function returns null for null input'
);
```

Boundary tests thường có giá trị cao hơn nhiều tests lặp lại một input thông thường.

### 7.5. Kiểm tra exception theo SQLSTATE

```sql
SELECT throws_ok(
    'SELECT app.calculate_discount(-1)',
    '22003',
    'amount must be nonnegative',
    'negative amount is rejected'
);
```

SQLSTATE ổn định hơn error text theo locale. Với PostgreSQL core errors có message phụ thuộc localization, có thể truyền NULL cho expected message và chỉ kiểm tra error code.

### 7.6. Kiểm tra query không phát sinh lỗi

```sql
SELECT lives_ok(
    'SELECT app.calculate_discount(250)',
    'normal amount does not raise an exception'
);
```

lives_ok() chỉ xác nhận statement chạy mà không phát sinh exception. Nó không chứng minh kết quả đúng; kết hợp với is() hoặc results_eq().

### 7.7. Kiểm tra set-returning function

Tạo fixtures:

```sql
INSERT INTO app.orders (
    id, status, total_amount
)
VALUES
    (91001, 'pending', 100),
    (91002, 'paid', 200),
    (91003, 'pending', 300);
```

So sánh query result với expected rows:

```sql
SELECT results_eq(
    'SELECT order_id FROM app.open_order_ids()',
    $$VALUES (91001::bigint), (91003::bigint)$$,
    'open_order_ids returns pending orders in id order'
);
```

results_eq() so sánh kết quả hai queries, gồm thứ tự rows. Nếu thứ tự không thuộc contract, dùng set_eq() để so sánh như tập hợp không phụ thuộc thứ tự. Nếu duplicates có ý nghĩa, cân nhắc bag_eq().

### 7.8. Kiểm tra empty results

```sql
SELECT is_empty(
    'SELECT order_id FROM app.open_order_ids() WHERE order_id = 999999',
    'unknown order is absent from result'
);
```

is_empty() phù hợp khi contract là không có rows. Với kết quả phải có dữ liệu, dùng isnt_empty().

## 8. Test function overloads và NULL semantics

### 8.1. Function overloads

Giả sử có:

```sql
CREATE FUNCTION app.format_code(p_value integer)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $function$
    SELECT 'I-' || p_value::text;
$function$;

CREATE FUNCTION app.format_code(p_value text)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $function$
    SELECT 'T-' || p_value;
$function$;
```

Test từng signature:

```sql
SELECT has_function('app', 'format_code', ARRAY['integer']);
SELECT has_function('app', 'format_code', ARRAY['text']);

SELECT is(
    app.format_code(7),
    'I-7',
    'integer overload is selected'
);

SELECT is(
    app.format_code('7'::text),
    'T-7',
    'text overload is selected'
);
```

### 8.2. NULL input

Phân biệt:

- Function STRICT: PostgreSQL không gọi function khi argument NULL và trả NULL.
- Function không STRICT: function body nhận NULL và tự quyết định behavior.

Test rõ contract:

```sql
SELECT is(
    app.calculate_discount(NULL::numeric),
    NULL::numeric,
    'NULL input is propagated'
);
```

### 8.3. Empty string và whitespace

NULL, empty string và whitespace không tương đương. Nếu function normalize text, test riêng:

```sql
SELECT is(app.normalize_code(NULL), NULL::text, 'NULL stays NULL');
SELECT is(app.normalize_code(''), '', 'empty string behavior is explicit');
SELECT is(app.normalize_code('  A-1  '), 'A-1', 'surrounding spaces are trimmed');
```

Các expected values phải theo business contract. Không tự coi empty string là NULL nếu application phân biệt hai trường hợp.

## 9. Kiểm thử procedure

Procedure được gọi bằng CALL. pgTAP có thể kiểm tra sự tồn tại, procedure kind, exceptions và side effects.

### 9.1. Kiểm tra object là procedure

```sql
SELECT has_function(
    'app',
    'mark_order_reviewed',
    ARRAY['bigint'],
    'mark_order_reviewed(bigint) exists'
);

SELECT is_procedure(
    'app',
    'mark_order_reviewed',
    ARRAY['bigint'],
    'mark_order_reviewed is a procedure'
);
```

pgTAP dùng tên assertion has_function() cho cả functions/procedures trong catalog; is_procedure() giúp xác nhận object kind.

### 9.2. Fixture cho procedure

```sql
INSERT INTO app.orders (
    id, status, total_amount, review_required
)
VALUES (
    92001, 'pending', 250, false
);
```

### 9.3. CALL và kiểm tra side effect

```sql
SELECT lives_ok(
    'CALL app.mark_order_reviewed(92001)',
    'existing order can be marked for review'
);

SELECT is(
    (SELECT review_required FROM app.orders WHERE id = 92001),
    true,
    'procedure updates review_required'
);
```

lives_ok() chỉ xác nhận CALL không lỗi. Assertion tiếp theo mới xác nhận dữ liệu đã thay đổi đúng.

### 9.4. Test error path

```sql
SELECT throws_ok(
    'CALL app.mark_order_reviewed(999999)',
    'P0002',
    'order not found',
    'procedure rejects missing order'
);
```

Test cả trường hợp target row không tồn tại, status không cho phép update, caller không đủ quyền và inputs không hợp lệ.

### 9.5. OUT và INOUT parameters

Procedure có thể khai báo OUT/INOUT arguments. Dùng CALL với variables trong PL/pgSQL hoặc client phù hợp để nhận output. Test output cùng side effects; đừng chỉ kiểm tra row updates nếu output là một phần API contract.

### 9.6. Procedure có transaction control

Một procedure có thể thực hiện COMMIT/ROLLBACK khi được gọi trong điều kiện cho phép. Không thể gọi procedure thực hiện transaction control bên trong pgTAP test transaction hoặc DO block có transaction wrapper.

Để test behavior này:

1. Tạo database test riêng.
2. Chạy CALL ở top level, không mở BEGIN bên ngoài.
3. Dùng fixtures có thể xóa/tái tạo.
4. Xác minh commit boundaries bằng một connection khác.
5. Dọn database hoặc fixture sau test.

Không giả định ROLLBACK ở cuối test sẽ undo các transactions mà procedure đã commit.

## 10. Kiểm thử trigger: cấu hình và behavior

Trigger có hai phần cần xác nhận: trigger object trên table và trigger function được gọi.

### 10.1. Kiểm tra trigger tồn tại

```sql
SELECT has_trigger(
    'app',
    'orders',
    'orders_status_audit_trg',
    'orders table has status audit trigger'
);
```

### 10.2. Kiểm tra trigger gọi đúng function

```sql
SELECT trigger_is(
    'app',
    'orders',
    'orders_status_audit_trg',
    'audit',
    'capture_order_status',
    'status trigger calls audit function'
);
```

Test này kiểm tra wiring. Nó không chứng minh trigger function xử lý OLD/NEW đúng; cần behavioral test riêng.

### 10.3. Kiểm tra danh sách triggers

```sql
SELECT triggers_are(
    'app',
    'orders',
    ARRAY['orders_status_audit_trg'],
    'orders table has only the expected user trigger'
);
```

triggers_are() kiểm tra tập trigger names trên table. Dùng khi muốn phát hiện cả trigger thừa lẫn trigger bị thiếu. Trên table có nhiều triggers, liệt kê đầy đủ những trigger thuộc contract của test.

### 10.4. Tạo fixture và kích hoạt trigger

```sql
INSERT INTO app.orders (
    id, status, total_amount
)
VALUES (
    93001, 'pending', 500
);

UPDATE app.orders
SET status = 'paid'
WHERE id = 93001;
```

Kiểm tra audit row:

```sql
SELECT is(
    (
        SELECT count(*)
        FROM audit.order_status_events
        WHERE order_id = 93001
    ),
    1::bigint,
    'status change creates one audit event'
);

SELECT results_eq(
    $query$
        SELECT old_status, new_status
        FROM audit.order_status_events
        WHERE order_id = 93001
    $query$,
    $$VALUES ('pending'::text, 'paid'::text)$$,
    'audit event records OLD and NEW status'
);
```

### 10.5. Kiểm tra WHEN condition

Trigger ví dụ chỉ ghi audit khi status thực sự đổi. Test UPDATE không đổi status:

```sql
UPDATE app.orders
SET status = 'paid'
WHERE id = 93001;

SELECT is(
    (
        SELECT count(*)
        FROM audit.order_status_events
        WHERE order_id = 93001
    ),
    1::bigint,
    'same status does not create another audit event'
);
```

### 10.6. Kiểm tra event khác không kích hoạt trigger

Trigger được khai báo AFTER UPDATE OF status, vì vậy UPDATE column khác không nên tạo audit event:

```sql
UPDATE app.orders
SET total_amount = 600
WHERE id = 93001;

SELECT is(
    (
        SELECT count(*)
        FROM audit.order_status_events
        WHERE order_id = 93001
    ),
    1::bigint,
    'updating amount does not fire status audit trigger'
);
```

Lưu ý UPDATE OF status xét column có nằm trong SET target list hay không. Điều kiện WHEN mới xác định OLD.status và NEW.status có khác nhau hay không.

## 11. Test các loại trigger khác nhau

### 11.1. BEFORE ROW trigger

BEFORE ROW trigger có thể sửa NEW trước khi row được ghi.

Ví dụ normalize code:

```sql
CREATE OR REPLACE FUNCTION app.normalize_customer_code()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    NEW.customer_code := upper(trim(NEW.customer_code));
    RETURN NEW;
END;
$function$;

CREATE TRIGGER customers_normalize_code_biu
BEFORE INSERT OR UPDATE OF customer_code
ON app.customers
FOR EACH ROW
EXECUTE FUNCTION app.normalize_customer_code();
```

Test phải insert/update qua table, sau đó SELECT giá trị đã lưu. Gọi trực tiếp normalize_customer_code() không mô phỏng đầy đủ trigger context vì function cần NEW/TG_OP do PostgreSQL cung cấp.

### 11.2. AFTER ROW trigger

AFTER ROW trigger thường phù hợp audit, outbox hoặc side effects transactional. Test xác nhận row đã được ghi và side effect tương ứng được tạo trong cùng transaction.

### 11.3. Statement-level trigger

Statement-level trigger chạy một lần cho statement, bất kể statement tác động bao nhiêu rows. Test với:

- Statement tác động zero rows.
- Statement tác động một row.
- Statement tác động nhiều rows.

Đừng giả định statement-level trigger chỉ chạy khi có row thay đổi; kiểm tra semantics của event và trigger definition.

### 11.4. Transition tables

Một số AFTER statement triggers có thể dùng transition relations để xem tập rows đã thay đổi. Test bulk UPDATE/DELETE để xác nhận toàn bộ changed rows được xử lý đúng và không chỉ xử lý một row.

### 11.5. DELETE trigger

DELETE trigger dùng OLD, không có NEW row như INSERT/UPDATE. Tạo fixture, DELETE và kiểm tra audit snapshot lưu giá trị trước khi xóa.

### 11.6. TRUNCATE trigger

TRUNCATE có trigger event riêng và statement-level behavior. Nếu ứng dụng có thể TRUNCATE table, test riêng vì DELETE triggers không thay thế TRUNCATE trigger.

### 11.7. Trigger order

Khi có nhiều triggers cùng event/timing trên cùng relation, PostgreSQL có quy tắc ordering theo tên trigger. Không dựa vào thứ tự tình cờ trong test fixture; nếu thứ tự là một phần thiết kế, đặt tên có chủ đích và test kết quả cuối.

## 12. Kiểm thử function metadata và security properties

pgTAP có assertions để kiểm tra object contract, giúp migration test phát hiện thay đổi ngoài ý muốn.

### 12.1. SECURITY DEFINER

```sql
SELECT is_definer(
    'app_private',
    'expire_one_order',
    ARRAY['bigint'],
    'maintenance function is SECURITY DEFINER'
);
```

Nếu function phải chạy dưới quyền caller, dùng isnt_definer().

### 12.2. Language

```sql
SELECT function_lang_is(
    'app',
    'calculate_discount',
    ARRAY['numeric'],
    'plpgsql',
    'discount function uses expected language'
);
```

### 12.3. Volatility

```sql
SELECT volatility_is(
    'app',
    'calculate_discount',
    ARRAY['numeric'],
    'immutable',
    'discount function volatility is immutable'
);
```

### 12.4. Procedure kind và return type

```sql
SELECT is_procedure(
    'app',
    'mark_order_reviewed',
    ARRAY['bigint'],
    'routine remains a procedure'
);

SELECT function_returns(
    'app',
    'mark_order_reviewed',
    ARRAY['bigint'],
    'void',
    'procedure has void return type'
);
```

### 12.5. Privileges

Có thể dùng PostgreSQL privilege helper functions trong pgTAP assertions:

```sql
SELECT ok(
    has_function_privilege(
        'app_runtime',
        'app.calculate_discount(numeric)',
        'EXECUTE'
    ),
    'runtime role can execute discount function'
);

SELECT ok(
    NOT has_function_privilege(
        'app_runtime',
        'app_private.expire_one_order(bigint)',
        'EXECUTE'
    ),
    'runtime role cannot execute maintenance function'
);
```

Test này kiểm tra privilege hiệu lực tại thời điểm chạy. Cần chạy bằng role có thể kiểm tra catalog/privilege metadata và xác nhận tên role/object đúng.

### 12.6. Test bằng role thật

Để kiểm tra behavior thực tế:

- Kết nối bằng app_runtime.
- Gọi function/procedure được phép.
- Xác nhận function bị từ chối khi không có EXECUTE.
- Xác nhận schema USAGE và underlying table privileges.
- Kiểm tra SECURITY DEFINER chỉ cấp đúng capability.
- Test RLS bằng role không phải superuser/table owner khi policy cần áp dụng.

Superuser có thể bypass nhiều security checks. Không dùng kết quả chạy bằng superuser để kết luận runtime authorization đúng.

## 13. Test trigger function có security context

Trigger function có thể là SECURITY INVOKER hoặc SECURITY DEFINER. Test cần xác định effective privileges và RLS behavior.

### 13.1. Kiểm tra function owner và mode

Dùng pgTAP is_definer() hoặc catalog query để xác nhận mode. Nếu trigger function là SECURITY DEFINER, owner nên là role chuyên biệt có quyền tối thiểu.

### 13.2. Chạy DML bằng runtime role

Kết nối bằng role tương tự application và thực hiện INSERT/UPDATE/DELETE. Xác nhận:

- Caller có quyền DML trên source table.
- Trigger thực hiện side effect được thiết kế.
- Caller không thể trực tiếp sửa audit table nếu không được phép.
- Trigger không tạo quyền truy cập ngoài ý muốn.
- RLS policies có behavior đúng trong effective user context.

### 13.3. Không chỉ test bằng owner

Table owner có thể bypass RLS theo rules của PostgreSQL, trừ khi FORCE ROW LEVEL SECURITY được bật. Test bằng owner có thể cho kết quả khác application runtime role.

### 13.4. Kiểm tra lỗi trong trigger

Nếu trigger function raise exception, statement DML thường thất bại cùng transaction. Test SQLSTATE, message của exception do ứng dụng định nghĩa và xác nhận source row không bị ghi một phần.

```sql
SELECT throws_ok(
    $$INSERT INTO app.orders (id, status, total_amount)
      VALUES (93002, 'invalid', 100)$$,
    '23514',
    NULL,
    'invalid order is rejected by constraint or trigger'
);
```

Nếu cần phân biệt constraint error với trigger error, dùng SQLSTATE và message đặc trưng do routine chủ động phát sinh.

## 14. Một pgTAP suite hoàn chỉnh

Ví dụ dưới đây kiểm tra function, procedure và trigger trong một transaction. Giả định schema, routines và trigger từ phần chuẩn bị đã được cài trong database test.

```sql
BEGIN;

SELECT plan(18);

-- Function contract.
SELECT has_function(
    'app', 'calculate_discount', ARRAY['numeric'],
    'discount function exists'
);
SELECT function_returns(
    'app', 'calculate_discount', ARRAY['numeric'], 'numeric',
    'discount function returns numeric'
);
SELECT function_lang_is(
    'app', 'calculate_discount', ARRAY['numeric'], 'plpgsql',
    'discount function uses PL/pgSQL'
);
SELECT volatility_is(
    'app', 'calculate_discount', ARRAY['numeric'], 'immutable',
    'discount function is immutable'
);

-- Function behavior.
SELECT is(app.calculate_discount(0), 0::numeric, 'zero has no discount');
SELECT is(app.calculate_discount(999.99), 0::numeric, 'below threshold');
SELECT is(app.calculate_discount(1000), 100::numeric, 'threshold discount');
SELECT is(app.calculate_discount(1250), 125::numeric, 'larger discount');
SELECT is(
    app.calculate_discount(NULL::numeric),
    NULL::numeric,
    'NULL propagates through STRICT function'
);
SELECT throws_ok(
    'SELECT app.calculate_discount(-1)',
    '22003',
    'amount must be nonnegative',
    'negative input is rejected'
);

-- Procedure contract and behavior.
SELECT is_procedure(
    'app', 'mark_order_reviewed', ARRAY['bigint'],
    'review routine is a procedure'
);
INSERT INTO app.orders (id, status, total_amount)
VALUES (92001, 'pending', 250);

SELECT lives_ok(
    'CALL app.mark_order_reviewed(92001)',
    'procedure accepts existing order'
);
SELECT is(
    (SELECT review_required FROM app.orders WHERE id = 92001),
    true,
    'procedure updates the order'
);
SELECT throws_ok(
    'CALL app.mark_order_reviewed(999999)',
    'P0002',
    'order not found',
    'procedure rejects missing order'
);

-- Trigger contract and behavior.
SELECT has_trigger(
    'app', 'orders', 'orders_status_audit_trg',
    'status audit trigger exists'
);
SELECT trigger_is(
    'app', 'orders', 'orders_status_audit_trg',
    'audit', 'capture_order_status',
    'status trigger calls expected function'
);

INSERT INTO app.orders (id, status, total_amount)
VALUES (93001, 'pending', 500);

UPDATE app.orders
SET status = 'paid'
WHERE id = 93001;

SELECT is(
    (SELECT count(*) FROM audit.order_status_events WHERE order_id = 93001),
    1::bigint,
    'status change writes one audit event'
);
SELECT results_eq(
    'SELECT old_status, new_status FROM audit.order_status_events WHERE order_id = 93001',
    $$VALUES ('pending'::text, 'paid'::text)$$,
    'audit event contains expected old and new values'
);

SELECT * FROM finish();
ROLLBACK;
```

Số assertions trong plan(18) phải khớp đúng số test calls. Khi thêm/bớt assertion, cập nhật plan cùng lúc. Dữ liệu fixtures và procedure side effects được rollback ở cuối vì procedure ví dụ không thực hiện transaction control.

## 15. SQL script thuần khi không dùng pgTAP

Có thể xây một test harness nhỏ bằng PL/pgSQL. Cách này không tạo TAP output chuẩn, nhưng đủ để làm script fail-fast khi assertion không đúng.

### 15.1. Tạo assertion helper tạm thời

```sql
CREATE FUNCTION pg_temp.assert_true(
    p_condition boolean,
    p_description text
)
RETURNS text
LANGUAGE plpgsql
AS $function$
BEGIN
    IF p_condition IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'ASSERTION FAILED: %', p_description;
    END IF;

    RETURN 'ok - ' || p_description;
END;
$function$;
```

Helper trả về dòng ok khi đúng và raise exception khi false hoặc NULL.

### 15.2. Chạy test bằng psql

Lưu thành tests/routines.sql:

```sql
\set ON_ERROR_STOP on
\pset format unaligned
\pset tuples_only on
\pset pager off

BEGIN;

CREATE FUNCTION pg_temp.assert_true(
    p_condition boolean,
    p_description text
)
RETURNS text
LANGUAGE plpgsql
AS $function$
BEGIN
    IF p_condition IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'ASSERTION FAILED: %', p_description;
    END IF;

    RETURN 'ok - ' || p_description;
END;
$function$;

SELECT pg_temp.assert_true(
    app.calculate_discount(1000) = 100,
    'discount threshold'
);

SELECT pg_temp.assert_true(
    app.calculate_discount(NULL::numeric) IS NULL,
    'strict function propagates NULL'
);

INSERT INTO app.orders (id, status, total_amount)
VALUES (94001, 'pending', 100);

CALL app.mark_order_reviewed(94001);

SELECT pg_temp.assert_true(
    (SELECT review_required FROM app.orders WHERE id = 94001),
    'procedure updates order'
);

UPDATE app.orders
SET status = 'paid'
WHERE id = 94001;

SELECT pg_temp.assert_true(
    (SELECT count(*) = 1
     FROM audit.order_status_events
     WHERE order_id = 94001),
    'trigger writes audit event'
);

ROLLBACK;
```

Chạy:

```bash
psql -X -v ON_ERROR_STOP=1 -d app_test -f tests/routines.sql
```

-X bỏ qua psqlrc để output và behavior nhất quán. ON_ERROR_STOP=1 khiến psql dừng khi SQL error. Khi script thất bại trong transaction, connection kết thúc và PostgreSQL rollback transaction chưa commit.

### 15.3. Kiểm tra exception bằng DO block

Nếu không có pgTAP, có thể bắt SQLSTATE mong đợi:

```sql
DO $test$
BEGIN
    PERFORM app.calculate_discount(-1);

    RAISE EXCEPTION
        'expected calculate_discount to reject a negative amount';
EXCEPTION
    WHEN SQLSTATE '22003' THEN
        -- Expected exception.
        NULL;
END;
$test$;
```

Nếu function không raise exception, câu RAISE do test tạo ra có SQLSTATE khác và không bị handler bắt, nên script fail.

### 15.4. Hạn chế của custom assertions

Custom helper cần được duy trì và không có đầy đủ diagnostics/TAP ecosystem. Khi test suite lớn, pgTAP thường giúp giảm code lặp và tăng khả năng tích hợp CI.

## 16. Test xUnit-style trong pgTAP

pgTAP hỗ trợ tổ chức test thành functions trả về SETOF TEXT, sau đó chạy bằng runtests().

### 16.1. Test function

```sql
CREATE SCHEMA IF NOT EXISTS tests;

CREATE OR REPLACE FUNCTION tests.test_calculate_discount()
RETURNS SETOF text
LANGUAGE plpgsql
AS $function$
BEGIN
    RETURN NEXT is(
        app.calculate_discount(1000),
        100::numeric,
        'threshold discount'
    );

    RETURN NEXT throws_ok(
        'SELECT app.calculate_discount(-1)',
        '22003',
        'amount must be nonnegative',
        'negative input is rejected'
    );
END;
$function$;
```

### 16.2. Chạy tests

```sql
SELECT * FROM runtests('tests');
```

Cú pháp và cách chọn test functions cần theo pgTAP version đang dùng. pgTAP có quy ước cho setup/teardown và cách tìm test routines; đọc tài liệu của phiên bản cài trước khi chuẩn hóa tên functions.

### 16.3. Khi nào dùng xUnit style?

Phù hợp khi:

- Muốn gom tests theo module/schema.
- Muốn setup/teardown dùng chung.
- Có nhiều assertions trong mỗi test function.
- Muốn chạy suite bằng một lệnh.

SQL test files thường dễ review hơn khi test là các workflow SQL dài hoặc cần transaction setup rõ ràng.

## 17. Fixtures và test data

Test đáng tin cậy cần fixtures xác định và có thể tái tạo.

### 17.1. Dữ liệu độc lập

Mỗi test nên sở hữu fixture IDs hoặc dùng một namespace dữ liệu riêng. Tránh dùng IDs có thể trùng dữ liệu do developer khác tạo.

### 17.2. Setup và teardown

Có thể:

- Tạo fixture trong transaction rồi ROLLBACK.
- Dùng schema test riêng rồi DROP schema sau suite.
- Dùng database ephemeral cho mỗi CI job.
- Dùng helper setup/teardown có thứ tự rõ.

Transaction rollback là lựa chọn tốt cho tests không thực hiện commit bên trong procedure và không có external side effects.

### 17.3. Tránh phụ thuộc vào sequence state

Sequence increments không rollback theo cách thông thường như table rows. Nếu test phụ thuộc vào exact generated ID, dùng explicit fixture IDs hoặc truy xuất ID bằng RETURNING thay vì giả định sequence luôn bắt đầu từ một số.

### 17.4. Clock và timezone

Nếu routine phụ thuộc clock:

- Dùng clock injection parameter khi thiết kế cho test.
- So sánh khoảng thời gian với tolerance hợp lý.
- Set timezone rõ ràng bằng SET LOCAL nếu behavior phụ thuộc timezone.
- Tránh assert timestamp bằng equality chính xác khi function dùng clock_timestamp().

### 17.5. Randomness

Nếu function dùng random UUID hoặc random number, test contract thay vì hard-code output. Có thể assert format, uniqueness hoặc range. Với thuật toán cần deterministic test, inject seed/source of randomness phù hợp.

### 17.6. Test không phụ thuộc thứ tự

Nếu query không có ORDER BY, kết quả không có thứ tự được bảo đảm. Dùng set_eq() hoặc thêm ORDER BY trong query khi thứ tự là một phần contract.

## 18. Kiểm thử trigger không bị false positive

Một test trigger có thể pass vì dữ liệu fixture sai hoặc assertion quá yếu.

### 18.1. Chứng minh trigger thực sự chạy

Đừng chỉ kiểm tra audit table có một row bất kỳ. Lọc theo fixture key và xác nhận old/new values đúng.

### 18.2. Chứng minh trigger không chạy sai event

Nếu trigger chỉ áp dụng UPDATE OF status, test UPDATE total_amount và xác nhận không có event mới.

### 18.3. Test multi-row DML

UPDATE nhiều rows trong một statement và xác nhận row-level trigger tạo đúng số audit rows. Test statement-level trigger bằng một statement tác động nhiều rows và xác nhận chỉ một statement event.

### 18.4. Test rollback atomicity

Trong cùng transaction:

1. UPDATE source row.
2. Trigger tạo audit row.
3. ROLLBACK.
4. Kiểm tra cả source update và audit insert đều không tồn tại.

Điều này chứng minh side effect trong database cùng transaction. Nó không áp dụng cho HTTP call, email hoặc external queue mà trigger/function gọi ra ngoài.

### 18.5. Test trigger exception

Khi trigger raise exception, kiểm tra source DML bị rollback. Nếu trigger ghi nhiều audit rows rồi lỗi ở bước cuối, tất cả transactional changes trong statement/transaction phải được kiểm tra theo expected atomicity.

### 18.6. Test trigger recursion

Trigger có thể cập nhật lại table đã kích hoạt nó. Kiểm tra recursion guard, pg_trigger_depth() nếu được dùng và termination behavior. Không chỉ test happy path một row.

### 18.7. Test disabled triggers và replication role

Trigger có thể bị disable hoặc chịu ảnh hưởng bởi session_replication_role. Nếu deployment/replication workflow thay đổi setting này, test bằng cấu hình tương ứng và xác nhận data integrity không phụ thuộc vào trigger bị bỏ qua ngoài dự kiến.

## 19. Kiểm thử privileges, SECURITY DEFINER và RLS

Security tests phải mô phỏng role thực tế.

### 19.1. Function EXECUTE grants

Dùng pgTAP function_privs_are() nếu cần assertion về ACL. Tên schema của pgTAP phụ thuộc nơi extension được cài; nếu pgTAP nằm trong public, gọi function không có prefix. Có thể dùng has_function_privilege() như assertion trực tiếp nếu muốn tránh phụ thuộc signature của ACL assertion.

### 19.2. Dùng privilege helper

```sql
SELECT ok(
    has_function_privilege(
        'app_runtime',
        'app.calculate_discount(numeric)',
        'EXECUTE'
    ),
    'runtime role has EXECUTE'
);
```

Kiểm tra cả role được phép và role không được phép.

### 19.3. Test SECURITY DEFINER

Kiểm tra is_definer() và owner. Sau đó gọi routine bằng runtime role để chứng minh function chỉ cho phép operation đã định nghĩa.

### 19.4. Search path

Với SECURITY DEFINER, test function-local search_path và xác nhận schema nằm trong path không cho untrusted roles CREATE. Test temporary objects có cùng tên nếu routine resolve unqualified identifiers.

### 19.5. RLS

Test bằng role không phải superuser và không phải table owner nếu muốn xác nhận policy áp dụng. Kiểm tra cả:

- SELECT chỉ thấy rows được phép.
- UPDATE/DELETE chỉ tác động rows được phép.
- SECURITY DEFINER có thay đổi effective user không.
- FORCE ROW LEVEL SECURITY có được bật khi cần không.

### 19.6. Không dùng SET ROLE như bằng chứng duy nhất

SET ROLE có thể hữu ích trong một test transaction, nhưng kết quả không luôn giống kết nối trực tiếp bằng login role, nhất là khi có session authorization, role memberships, connection settings hoặc authentication context. Với security-sensitive flows, mở connection riêng bằng role thực tế.

## 20. Test migration và schema contract

Routine tests cần chạy sau khi migrations tạo/cập nhật functions, procedures và triggers.

### 20.1. Test từ database trống

CI nên tạo database mới, áp dụng toàn bộ migrations theo thứ tự rồi chạy tests. Cách này phát hiện dependency thiếu hoặc migration không tái tạo được schema.

### 20.2. Test upgrade từ phiên bản trước

Một migration có thể chạy đúng trên database mới nhưng thất bại khi upgrade database cũ có data/indexes/triggers khác. Dùng snapshot hoặc fixture database từ version trước để kiểm tra upgrade path.

### 20.3. Contract assertions

Kiểm tra:

- Function/procedure signatures.
- Return type.
- Language và volatility.
- SECURITY DEFINER/INVOKER.
- Trigger tồn tại và gắn đúng function.
- Constraints/indexes phụ thuộc.
- Owner và EXECUTE grants.
- Function-local settings/search_path.

### 20.4. Migration không nên chỉ kiểm tra object tồn tại

Một function có thể tồn tại với signature đúng nhưng body behavior đã đổi. Kết hợp catalog assertions với behavioral tests.

### 20.5. Test sau CREATE OR REPLACE

CREATE OR REPLACE FUNCTION có thể thay body hoặc properties. Sau migration, kiểm tra lại owner, ACL, SECURITY mode, volatility và SET clauses. Không giả định test trước migration vẫn đại diện state mới.

## 21. Kiểm thử concurrency và transaction behavior

Unit tests tuần tự không phát hiện mọi race conditions.

### 21.1. Hai sessions cùng xử lý một row

Dùng hai connections để test procedure claim/lock row. Xác nhận chỉ một worker xử lý thành công nếu contract yêu cầu single claimant.

### 21.2. FOR UPDATE SKIP LOCKED

Nếu routine dùng SKIP LOCKED, test hai sessions đồng thời và xác nhận mỗi session nhận rows khác nhau. Tránh test dựa trên timing cố định; dùng barriers hoặc coordination table trong test harness.

### 21.3. Deadlock và retry

Test routines có thể lock nhiều tables. Kiểm tra thứ tự locks, SQLSTATE deadlock và application retry policy. Không viết test deadlock bằng sleep ngẫu nhiên rồi kỳ vọng thứ tự cố định.

### 21.4. Isolation level

Behavior có thể khác giữa READ COMMITTED, REPEATABLE READ và SERIALIZABLE. Test ở isolation level thực tế của application, đặc biệt với functions kiểm tra rồi mới cập nhật dữ liệu.

### 21.5. Advisory locks

Nếu procedure dùng advisory locks, test release/cleanup khi exception, transaction rollback và session disconnect. Phân biệt transaction-level với session-level advisory locks.

### 21.6. Test transaction control procedure riêng

Procedure có COMMIT/ROLLBACK phải được gọi ở top-level. Dùng script integration mở nhiều connections để kiểm tra visibility và commit boundaries; không gói trong pgTAP transaction.

## 22. Test performance có ý nghĩa

pgTAP có performs_ok() để kiểm tra query không vượt một ngưỡng thời gian. Dùng thận trọng trong CI.

### 22.1. performs_ok()

Ví dụ:

```sql
SELECT performs_ok(
    'SELECT app.open_order_ids()',
    250,
    'open order query completes within 250 ms'
);
```

Đây là assertion thời gian chạy tại thời điểm test. Nó không thay thế benchmark và dễ dao động theo CPU, cache, I/O, shared runners hoặc concurrency.

### 22.2. Không đặt threshold quá sát

Nếu baseline p95 là 100 ms, test không nên fail ở 101 ms trên một CI runner dùng chung. Đặt ngưỡng rộng để phát hiện regression lớn; dùng benchmark riêng cho performance acceptance.

### 22.3. Dữ liệu đại diện

Function query 10 rows trên table trống không chứng minh hiệu năng trên hàng chục triệu rows. Test performance cần dataset, indexes, statistics và concurrency tương tự production.

### 22.4. EXPLAIN

Có thể dùng EXPLAIN (ANALYZE, BUFFERS) trên workload test để xem execution time, buffers và plan. EXPLAIN ANALYZE thực sự chạy statement; với DML cần transaction rollback và lưu ý side effects ngoài database.

### 22.5. Phân biệt correctness và performance

Một function test đúng kết quả nhưng chậm vẫn là correctness pass, performance fail. Tách suite để không làm test behavior trở nên flaky vì resource contention.

## 23. Test dữ liệu lỗi và property-based cases

Một vài examples không bao phủ toàn bộ input space.

### 23.1. Boundary matrix

Với numeric input, test:

- NULL.
- Giá trị âm.
- Zero.
- Ngay dưới threshold.
- Đúng threshold.
- Ngay trên threshold.
- Giá trị rất lớn.
- Giá trị có scale/rounding.
- Giá trị gây overflow.

### 23.2. String input

Test:

- Empty string.
- Leading/trailing whitespace.
- Unicode.
- Mixed case.
- Quotes và delimiter.
- Ký tự không hợp lệ.
- String dài tối đa/vượt giới hạn.
- Collation-sensitive values.

### 23.3. Date/time

Test leap day, daylight saving transitions, timezone boundaries, NULL, future/past timestamps và inclusive/exclusive range endpoints.

### 23.4. Property-based testing

Có thể tạo nhiều inputs bằng SQL generate_series hoặc client-side property testing. Ví dụ kiểm tra invariant discount không âm:

```sql
SELECT ok(
    bool_and(app.calculate_discount(x) >= 0),
    'discount is nonnegative for all generated amounts'
)
FROM generate_series(0, 5000, 25) AS values(x);
```

Property test cần kiểm soát random seed và dữ liệu để có thể tái tạo khi fail.

### 23.5. Fuzzing dynamic SQL

Nếu function nhận identifiers hoặc text input, fuzz quote characters, Unicode, long identifiers, case folding và reserved words. Xác nhận input được reject hoặc xử lý đúng, không biến thành SQL syntax ngoài ý muốn.

## 24. Test failure diagnostics và TAP output

Một suite hữu ích cần giúp developer hiểu vì sao test fail.

### 24.1. Mô tả assertion cụ thể

Tốt:

```sql
SELECT is(
    app.calculate_discount(1000),
    100::numeric,
    'amount at discount threshold returns 10 percent'
);
```

Tránh mô tả chung như function works.

### 24.2. Expected và actual values

Dùng is(), results_eq() và throws_ok() để pgTAP xuất diagnostics. Khi dùng custom DO blocks, exception nên nêu input/cohort liên quan nhưng không chứa secrets.

### 24.3. SQLSTATE trước error message

Message có thể thay đổi theo locale hoặc version. Ưu tiên SQLSTATE cho PostgreSQL errors. Với errors do ứng dụng định nghĩa, có thể kiểm tra message nếu message là contract.

### 24.4. Plan mismatch

Nếu plan khai báo 10 nhưng chỉ chạy 9 tests, kiểm tra nhánh IF/CASE, skip count và test loops. Plan mismatch là lỗi test harness cần xử lý, không bỏ qua.

### 24.5. TODO và SKIP

pgTAP có todo()/skip() cho cases có chủ đích. Dùng chúng có thời hạn và lý do cụ thể. Không biến một regression thành TODO vô thời hạn để CI xanh giả tạo.

## 25. Tổ chức test files và CI

Một cấu trúc đơn giản:

```text
project/
├── migrations/
├── tests/
│   ├── functions/
│   │   ├── calculate_discount.sql
│   │   └── open_order_ids.sql
│   ├── procedures/
│   │   └── mark_order_reviewed.sql
│   ├── triggers/
│   │   └── orders_status_audit.sql
│   ├── security/
│   │   └── routine_privileges.sql
│   └── integration/
│       └── transaction_boundaries.sql
└── scripts/
    └── create_test_database.sql
```

### 25.1. Chạy pgTAP suite

Ví dụ:

```bash
pg_prove -d app_test -U test_runner tests/functions/*.sql tests/procedures/*.sql tests/triggers/*.sql
```

Có thể chạy toàn bộ folder:

```bash
pg_prove -d app_test -U test_runner tests/
```

Cú pháp glob/path phụ thuộc shell và pg_prove version; xác nhận trong CI image.

### 25.2. Verbose output

Khi debug:

```bash
pg_prove --verbose -d app_test -U test_runner tests/
```

Verbose mode giúp xác định assertion fail và file liên quan.

### 25.3. psql script runner

Với SQL scripts thuần:

```bash
psql -X -v ON_ERROR_STOP=1 -d app_test -f tests/routines.sql
```

Không để CI chỉ kiểm tra exit code của shell pipeline mà vô tình bỏ qua exit code của psql. Cấu hình pipeline fail khi test process thất bại.

### 25.4. CI sequence

Một pipeline thường gồm:

1. Provision PostgreSQL test instance.
2. Cài extension packages cần thiết.
3. Tạo test database và roles.
4. Apply migrations.
5. Create pgTAP extension.
6. Run catalog/behavior tests.
7. Run security tests bằng runtime roles.
8. Run integration/concurrency tests.
9. Export TAP/JUnit-compatible report nếu tooling hỗ trợ.
10. Destroy ephemeral database.

### 25.5. Parallel test execution

Không chạy hai test suites song song trên cùng fixtures cố định nếu chúng cùng sửa một row/table. Dùng database/schema riêng cho từng worker hoặc fixture IDs không trùng.

### 25.6. CI credentials

Dùng secret manager/environment variables. Không commit database passwords vào test SQL files hoặc command lines có thể lộ trong process listings/logs. Test runner role chỉ nên có quyền cần thiết trong test database.

## 26. Những giới hạn cần hiểu

### 26.1. pgTAP không thay thế test runner ngoài database

pgTAP assertions chạy trong PostgreSQL, nhưng provisioning, package installation, environment orchestration và CI lifecycle vẫn cần tooling bên ngoài.

### 26.2. Transaction rollback không undo external side effects

Nếu routine gửi HTTP request, email hoặc message tới broker, ROLLBACK database không thu hồi side effect đó. Dùng mock adapter, test endpoint, transactional outbox hoặc isolated external service.

### 26.3. Test superuser có thể che giấu security bug

Superuser có thể bypass RLS và privilege checks. Chạy tests permission bằng runtime role.

### 26.4. Trigger function không thể test đầy đủ bằng cách gọi trực tiếp

Trigger context gồm NEW, OLD, TG_OP, TG_WHEN, TG_LEVEL và transition relations. Test bằng INSERT/UPDATE/DELETE/TRUNCATE thực tế để PostgreSQL kích hoạt trigger.

### 26.5. Test schema metadata không chứng minh behavior

has_function() hoặc trigger_is() chỉ xác nhận object tồn tại/wiring. Vẫn cần behavioral tests cho outputs và side effects.

### 26.6. Test local không chứng minh mọi PostgreSQL versions giống nhau

Nếu module hỗ trợ nhiều major versions, chạy compatibility matrix. Một số catalog fields, syntax và pgTAP assertions có thể khác theo version.

### 26.7. Test performance có thể flaky

Thời gian phụ thuộc shared resources, cache, background work và data distribution. Dùng benchmark environment riêng cho performance gates nghiêm ngặt.

## 27. Các lỗi thường gặp

| Triệu chứng/giả định | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| plan mismatch | Đếm sai assertions hoặc nhánh test không chạy | Cập nhật plan và kiểm tra conditional branches |
| pgTAP function không tồn tại | Extension chưa được cài trong database hoặc sai schema | Kiểm tra pg_extension/search_path |
| CREATE EXTENSION pgtap thất bại | Package/control files chưa có trên server | Cài package đúng PostgreSQL major |
| Test function pass nhưng app vẫn lỗi | Test chạy bằng owner/superuser | Chạy bằng runtime role và kiểm tra grants/RLS |
| Trigger có mặt nhưng không tạo audit row | Event/timing/WHEN sai hoặc trigger disabled | Test DML thật và inspect trigger definition |
| Trigger test pass sai | Assertion đếm mọi audit rows, không lọc fixture key | Assert theo primary key của fixture |
| Procedure CALL không chạy trong test | Procedure thực hiện COMMIT trong transaction wrapper | Test ở top-level bằng integration script riêng |
| Test phụ thuộc thứ tự rows | Query không có ORDER BY | Dùng set_eq hoặc ORDER BY |
| NULL assertion cho kết quả không rõ | Dùng boolean comparison trả NULL | Dùng is(value, NULL::type) hoặc IS NULL |
| Exception test flaky | So message theo locale/version | Ưu tiên SQLSTATE |
| Sequence ID khác dự kiến | Sequence state không rollback như table data | Dùng explicit IDs hoặc RETURNING |
| CI tests xung đột | Chia sẻ fixture IDs/database | Database/schema riêng hoặc IDs duy nhất |
| Test chạy chậm | Dataset nhỏ ở dev, lớn ở CI hoặc thiếu indexes | Chuẩn hóa fixtures và workload |
| RLS test luôn thấy mọi rows | Test bằng superuser/table owner | Dùng runtime role không bypass RLS |
| Function security test sai | Chỉ kiểm tra body, không kiểm tra owner/ACL/search_path | Test execution context và catalog metadata |
| SQL script báo pass nhưng CI vẫn xanh khi lỗi | Runner không bật ON_ERROR_STOP hoặc bỏ exit code | Dùng psql -v ON_ERROR_STOP=1 và fail pipeline |

## 28. Quy trình xây dựng test suite từ đầu

**Bước 1 — Liệt kê routines và triggers.** Ghi function/procedure signatures, return types, owners, security mode, trigger events và expected side effects.

**Bước 2 — Viết contract.** Với mỗi object, xác định inputs, outputs, SQLSTATE, invariants, permissions và performance expectations.

**Bước 3 — Tạo test database.** Dùng PostgreSQL version tương thích, cài extensions và tạo roles giống production ở mức cần thiết.

**Bước 4 — Tạo fixtures.** Dữ liệu nhỏ, deterministic, có keys rõ ràng và không phụ thuộc state bên ngoài.

**Bước 5 — Viết behavior tests.** Kiểm tra happy path, boundaries, NULL, exceptions, rows changed và side effects.

**Bước 6 — Viết trigger tests.** Kiểm tra catalog wiring, event, timing, row/statement level, WHEN conditions và rollback atomicity.

**Bước 7 — Viết security tests.** Chạy bằng runtime role, xác nhận EXECUTE, RLS, SECURITY DEFINER và search_path.

**Bước 8 — Viết schema contract tests.** Xác nhận signatures, return types, volatility, trigger functions và object counts.

**Bước 9 — Chạy qua migrations.** Test database trống và database upgrade từ version trước.

**Bước 10 — Tích hợp CI.** Chạy pg_prove/psql với fail-fast, lưu output và phân loại failure.

**Bước 11 — Bổ sung concurrency/performance.** Chỉ thêm các tests cần nhiều sessions hoặc dataset lớn vào suite phù hợp.

**Bước 12 — Duy trì test cùng code.** Khi contract thay đổi, sửa routine, migration và tests trong cùng change set.

## 29. Bài thực hành

Thực hiện trên database lab riêng. Không chạy test data mutation, trigger side effects hoặc privilege experiments trên production.

### Bài 1 — Cài pgTAP

Cài package pgTAP tương thích với PostgreSQL server, chạy CREATE EXTENSION trong database lab và xác nhận bằng pg_extension.

### Bài 2 — TAP plan

Viết file test có plan(3), ba assertions và finish(). Chạy bằng pg_prove và đọc output.

### Bài 3 — Assertion cơ bản

Dùng ok(), is(), isnt() và cmp_ok() để kiểm tra kết quả function đơn giản.

### Bài 4 — Function existence

Dùng has_function() với schema, name và argument types. Tạo overload để chứng minh signature quan trọng.

### Bài 5 — Return type

Dùng function_returns() kiểm tra scalar function và set-returning function.

### Bài 6 — Language và volatility

Dùng function_lang_is() và volatility_is() để kiểm tra contract của function.

### Bài 7 — STRICT/NULL

Tạo function STRICT và function không STRICT. Kiểm tra NULL input và ghi rõ semantics.

### Bài 8 — Boundary values

Viết test cho numeric function tại zero, negative, threshold, maximum và rounding boundaries.

### Bài 9 — Exception SQLSTATE

Tạo function raise exception với SQLSTATE tùy chỉnh. Dùng throws_ok() để kiểm tra code/message.

### Bài 10 — Exception localization

Thử kiểm tra error message của PostgreSQL core error. Chuyển sang assert SQLSTATE để tránh phụ thuộc locale.

### Bài 11 — Set-returning function

Tạo function trả nhiều rows. Dùng results_eq() kiểm tra values và ordering.

### Bài 12 — Set equality

Viết query không có ORDER BY và dùng set_eq() để so sánh kết quả không phụ thuộc thứ tự.

### Bài 13 — Empty result

Dùng is_empty() và isnt_empty() kiểm tra query có/không có rows.

### Bài 14 — Procedure kind

Tạo procedure và dùng is_procedure() cùng function_returns(..., 'void') để kiểm tra metadata.

### Bài 15 — Procedure side effects

Gọi procedure bằng lives_ok(), sau đó kiểm tra table state bằng is()/results_eq().

### Bài 16 — Procedure error path

Tạo procedure raise exception khi row không tồn tại. Test SQLSTATE và xác nhận dữ liệu không bị thay đổi.

### Bài 17 — OUT/INOUT

Tạo procedure có OUT hoặc INOUT parameter. Gọi bằng CALL trong PL/pgSQL/client và xác nhận output.

### Bài 18 — Transaction-control procedure

Tạo procedure có COMMIT trong lab. Chứng minh nó không thể chạy trong transaction wrapper và viết top-level integration test.

### Bài 19 — Trigger exists

Dùng has_trigger() kiểm tra trigger được gắn vào table.

### Bài 20 — Trigger wiring

Dùng trigger_is() để xác nhận trigger gọi đúng trigger function.

### Bài 21 — Trigger set

Dùng triggers_are() kiểm tra danh sách triggers mong đợi và thử thêm một trigger thừa để xem diagnostics.

### Bài 22 — AFTER UPDATE audit

Tạo trigger audit OLD/NEW status. UPDATE row và xác nhận audit record chính xác.

### Bài 23 — WHEN condition

Tạo trigger chỉ chạy khi OLD/NEW khác nhau. Update cùng value và xác nhận không tạo audit event mới.

### Bài 24 — UPDATE OF column

Tạo trigger UPDATE OF status. Update một column khác và xác nhận trigger không ghi event.

### Bài 25 — BEFORE trigger

Tạo trigger normalize text. Insert/update qua table và kiểm tra giá trị được lưu sau trigger.

### Bài 26 — DELETE trigger

Tạo audit trigger dùng OLD. Xóa row và xác nhận before-image được lưu.

### Bài 27 — Statement-level trigger

Tạo statement-level trigger và chạy DML tác động zero, one và multiple rows. So số lần trigger với expected contract.

### Bài 28 — Multi-row trigger

Tạo row-level trigger, update 100 rows và xác nhận đúng 100 audit events.

### Bài 29 — Trigger rollback

Update source row rồi ROLLBACK. Xác nhận cả source change và audit row đều bị rollback.

### Bài 30 — Trigger exception

Tạo trigger có thể raise exception. Xác nhận DML thất bại và không để lại partial database state.

### Bài 31 — SECURITY DEFINER

Tạo function SECURITY DEFINER với owner NOLOGIN. Dùng is_definer() và gọi bằng runtime role.

### Bài 32 — Privilege test

Dùng has_function_privilege() kiểm tra role được phép và bị từ chối EXECUTE. Chạy test bằng connection roles tương ứng.

### Bài 33 — RLS

Tạo table RLS và policies theo role. Test SELECT/UPDATE bằng runtime role, không dùng superuser.

### Bài 34 — SQL-only harness

Viết pg_temp.assert_true(), chạy tests bằng psql với ON_ERROR_STOP và rollback fixtures.

### Bài 35 — CI suite

Tạo pipeline provision database, apply migrations, cài pgTAP, chạy pg_prove, lưu TAP output và làm job thất bại khi assertion fail.

## 30. Tổng kết

Những điểm cốt lõi khi **kiểm thử hàm, thủ tục và trigger với pgTAP hoặc SQL script**:

1. Function, procedure và trigger có invocation model và side effects khác nhau; chọn đúng test approach.
2. pgTAP cung cấp assertions và TAP output; pg_prove giúp chạy nhiều SQL test files trong CI.
3. plan()/finish() kiểm soát số lượng assertions và xác nhận suite đã kết thúc.
4. has_function(), function_returns(), function_lang_is(), volatility_is() và is_definer() kiểm tra function/procedure contract.
5. throws_ok() kiểm tra exceptions bằng SQLSTATE; lives_ok() chỉ xác nhận statement không lỗi.
6. results_eq(), set_eq() và is_empty() giúp kiểm tra query results.
7. has_trigger(), trigger_is() và triggers_are() kiểm tra trigger existence/wiring; DML thật mới chứng minh behavior.
8. Procedure side effects phải được xác nhận sau CALL; transaction-control procedures cần integration test top-level riêng.
9. Fixtures deterministic, transaction rollback và test database riêng giúp suite lặp lại.
10. Security tests phải dùng runtime roles để xác nhận EXECUTE, SECURITY DEFINER và RLS.
11. Concurrency, performance và external side effects cần test strategy riêng.
12. SQL script thuần có thể dùng pg_temp assertion helper và psql ON_ERROR_STOP khi không thể cài pgTAP.
13. CI cần chạy migrations trước tests, lưu diagnostics và trả exit status thất bại khi assertions không đạt.
14. Test metadata không thay thế behavior tests; test function trực tiếp không thay thế trigger integration tests.
15. Một suite tốt bảo vệ cả output, data invariants, privileges, trigger side effects và migration compatibility.

Khi kiểm thử logic trong PostgreSQL, hãy coi routine là một API có contract rõ ràng: caller nào được gọi, input nào hợp lệ, output/side effect nào được tạo và lỗi nào phải xuất hiện. pgTAP giúp diễn đạt contract thành assertions có diagnostics; SQL script thuần cung cấp một lựa chọn nhẹ hơn khi môi trường hạn chế. Kết hợp cả hai với fixtures tái tạo được, runtime roles và migration tests sẽ giúp phát hiện lỗi trước khi routine tác động tới dữ liệu production.

## 31. Tài liệu tham khảo

- [pgTAP Documentation](https://pgtap.org/documentation.html) — cài đặt, TAP plans, assertions, query tests, schema tests và function/trigger assertions.
- [pgTAP on PGXN](https://pgxn.org/dist/pgtap/) — package, release và tài liệu phân phối.
- [Supabase: pgTAP Unit Testing](https://supabase.com/docs/guides/database/extensions/pgtap) — ví dụ tổ chức test functions và query assertions.
- [PostgreSQL: CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html) — function definition, volatility, security mode và attributes.
- [PostgreSQL: CREATE PROCEDURE](https://www.postgresql.org/docs/current/sql-createprocedure.html) — procedure definition và transaction control.
- [PostgreSQL: CALL](https://www.postgresql.org/docs/current/sql-call.html) — gọi procedure và transaction restrictions.
- [PostgreSQL: Trigger Definition](https://www.postgresql.org/docs/current/trigger-definition.html) — trigger events, timing và execution behavior.
- [PostgreSQL: CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html) — trigger syntax, row/statement level và WHEN.
- [PostgreSQL: PL/pgSQL Errors and Messages](https://www.postgresql.org/docs/current/plpgsql-errors-and-messages.html) — RAISE, SQLSTATE và exception handling.
- [PostgreSQL: Transaction Management](https://www.postgresql.org/docs/current/tutorial-transactions.html) — BEGIN, COMMIT và ROLLBACK.
- [PostgreSQL: Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) — RLS behavior và policy evaluation.
- [PostgreSQL: Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html) — SQLSTATE catalog.

Các URL /current/ trỏ tới tài liệu PostgreSQL hiện hành. pgTAP API, extension packaging và một số trigger/procedure features có thể khác theo version. Trước khi chuẩn hóa test suite, xác nhận PostgreSQL major version, pgTAP version, schema cài extension và command-line runner có trong CI image.
