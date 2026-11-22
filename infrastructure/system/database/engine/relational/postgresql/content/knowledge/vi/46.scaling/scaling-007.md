# Ngôn ngữ thủ tục bổ sung và rủi ro quyền thực thi trong PostgreSQL

PostgreSQL có thể thực thi logic bên trong database bằng SQL functions, procedures, triggers và các ngôn ngữ thủ tục như PL/pgSQL, PL/Python, PL/Perl hoặc PL/Tcl. Các ngôn ngữ này mở rộng khả năng xử lý dữ liệu, tự động hóa nghiệp vụ và tích hợp hệ thống. Tuy nhiên, một function không chỉ là một đoạn code được lưu trong database: nó chạy dưới một security context cụ thể, có thể được gọi bởi nhiều roles và trong một số trường hợp có thể truy cập tài nguyên của operating system.

Rủi ro lớn thường xuất hiện khi quyền tạo function, quyền dùng procedural language, quyền gọi function và quyền của function owner bị gộp thành một khái niệm. PostgreSQL quản lý chúng bằng các cơ chế khác nhau. Một role có thể không được phép tạo function nhưng vẫn được EXECUTE function do người khác tạo. Một function mặc định chạy với quyền của caller, nhưng function khai báo `SECURITY DEFINER` chạy với quyền của owner. Một function dùng dynamic SQL hoặc search_path không an toàn có thể mở ra SQL injection hoặc object-shadowing attacks.

Bài học thuộc chương **Mở rộng**, tập trung vào:

- Phân biệt SQL language, PL/pgSQL và các procedural languages bổ sung.
- Hiểu trusted/untrusted languages và giới hạn của language sandbox.
- Cài đặt, nâng cấp và gỡ procedural language extensions.
- Phân biệt database, schema, language và function privileges.
- Hiểu mặc định EXECUTE cho PUBLIC và cách giới hạn quyền gọi routines.
- Phân biệt `SECURITY INVOKER` với `SECURITY DEFINER`.
- Phòng tránh search_path hijacking, temporary-schema shadowing và SQL injection.
- Thiết kế dynamic SQL với identifier quoting và parameter binding.
- Giảm rủi ro từ C functions, untrusted languages và extension installation.
- Kiểm tra RLS, ownership, function configuration, volatility và parallel properties.
- Audit language/function privileges, routine owners và SECURITY DEFINER code.
- Xây dựng least-privilege model, deployment checklist và incident runbook.

> **Nguyên tắc bảo mật:** quyền tạo function, quyền gọi function và quyền mà function sử dụng khi chạy là ba câu hỏi riêng. Không cấp EXECUTE rộng cho function nhạy cảm, không dùng SECURITY DEFINER nếu không cần nâng quyền, và không để role không đáng tin có quyền CREATE trong schema nằm trên search_path của privileged function.

## 1. Các loại ngôn ngữ trong PostgreSQL

PostgreSQL hỗ trợ nhiều cách định nghĩa routines. Một routine có thể dùng SQL, PL/pgSQL hoặc một procedural language được cài bổ sung.

### 1.1. SQL language

SQL functions dùng các SQL statements/expressions để định nghĩa behavior:

```sql
CREATE FUNCTION app.order_total(p_order_id bigint)
RETURNS numeric
LANGUAGE SQL
STABLE
AS $function$
    SELECT COALESCE(sum(oi.quantity * oi.unit_price), 0)
    FROM app.order_items AS oi
    WHERE oi.order_id = p_order_id;
$function$;
```

SQL language phù hợp khi logic chủ yếu là một expression hoặc query. Nó có thể khai báo function properties như volatility, strictness, parallel safety và security mode.

### 1.2. PL/pgSQL

PL/pgSQL là ngôn ngữ thủ tục tích hợp chặt với PostgreSQL. Nó hỗ trợ variables, control flow, loops, exceptions, cursors và dynamic SQL.

```sql
CREATE FUNCTION app.calculate_discount(p_amount numeric)
RETURNS numeric
LANGUAGE plpgsql
IMMUTABLE
AS $function$
BEGIN
    IF p_amount < 0 THEN
        RAISE EXCEPTION 'amount must be nonnegative';
    END IF;

    IF p_amount >= 1000 THEN
        RETURN p_amount * 0.10;
    END IF;

    RETURN 0;
END;
$function$;
```

PL/pgSQL phù hợp cho business logic cần nhiều bước SQL và control flow. Nó vẫn chạy trong PostgreSQL backend process và chịu transaction/privilege rules của database.

### 1.3. Các procedural languages bổ sung

Các ngôn ngữ thường gặp:

| Language | Ví dụ extension/language name | Mục đích |
| --- | --- | --- |
| PL/pgSQL | `plpgsql` | Logic thủ tục gắn với SQL |
| PL/Python | `plpython3u` | Dùng Python trong routines |
| PL/Perl | `plperl`, `plperlu` | Dùng Perl trong routines |
| PL/Tcl | `pltcl`, `pltclu` | Dùng Tcl trong routines |
| PL/Java | Extension bên thứ ba | Dùng Java trong database |
| PL/R | Extension bên thứ ba | Phân tích thống kê bằng R |
| PL/V8 | Extension bên thứ ba | Dùng JavaScript/V8 trong database |
| C | `LANGUAGE C` | Gọi native shared library |

Tên chính xác, phiên bản, trusted status và cách đóng gói phụ thuộc PostgreSQL build, OS package và extension được cài. Không phải mọi language đều có sẵn trong mọi managed database service.

### 1.4. Language không đồng nghĩa extension

Procedural language thường được đóng gói và quản lý bằng extension. Một số language có thể được đăng ký bằng lệnh CREATE LANGUAGE cũ, nhưng cách quản lý hiện đại thường ưu tiên CREATE EXTENSION.

Extension có thể bao gồm:

- Language handler.
- Inline handler cho anonymous code blocks.
- Validator kiểm tra function body.
- Supporting functions/types/operators.
- Control file và SQL installation scripts.
- Shared library được nạp bởi PostgreSQL.

Một language có thể chỉ là một phần trong extension lớn hơn. Gỡ extension có thể ảnh hưởng các objects khác do extension sở hữu.

### 1.5. Ngôn ngữ không phải một process riêng

Procedural function thường chạy bên trong backend process phục vụ session. Nó không tự động chạy trong sandbox process độc lập. Vì vậy, một lỗi native code hoặc function chạy quá lâu có thể ảnh hưởng backend và tài nguyên server.

Một số extensions có thể khởi chạy hoặc giao tiếp với external runtime, nhưng không nên giả định mọi procedural language được cô lập ở cấp OS.

## 2. Trusted và untrusted procedural languages

PostgreSQL phân loại procedural languages theo thuộc tính trusted. Thuộc tính này thể hiện mức độ language handler giới hạn khả năng của code được viết bằng language đó.

### 2.1. Trusted language

Trusted language được thiết kế để cho phép users có quyền phù hợp tạo functions mà không cần superuser. Handler phải hạn chế các thao tác nguy hiểm theo contract của language.

PL/pgSQL là trusted language. PL/Perl có biến thể trusted `plperl`. PL/Tcl có biến thể trusted `pltcl`.

Trusted không có nghĩa code luôn an toàn. Function vẫn có thể:

- Đọc hoặc sửa dữ liệu mà caller có quyền truy cập.
- Gọi các functions khác.
- Chạy query tốn tài nguyên.
- Tạo lock contention.
- Gây lỗi nghiệp vụ.
- Thực thi với quyền owner nếu khai báo SECURITY DEFINER.
- Bị khai thác qua SQL injection hoặc logic authorization sai.

Trusted chỉ nói về language-level restrictions, không phải một security review cho mọi function.

### 2.2. Untrusted language

Untrusted languages không cung cấp sandbox đủ để cho phép users thường tự tạo code. Tạo functions bằng các language này thường chỉ dành cho superusers.

Ví dụ:

- `plpython3u` là PL/Python untrusted.
- `plperlu` là PL/Perl untrusted.
- `pltclu` là PL/Tcl untrusted.
- C language là native-code interface không được xem như trusted sandbox.

Untrusted code có thể có khả năng truy cập filesystem, process, network hoặc các API runtime theo quyền của OS account chạy PostgreSQL. Trên nhiều triển khai, process chạy dưới OS account của PostgreSQL service, thường là user postgres.

### 2.3. Superuser-only creation không đồng nghĩa caller phải là superuser

Một superuser có thể tạo function trong untrusted language rồi cấp EXECUTE cho role khác. Khi role đó gọi function, function body vẫn chạy.

Điều này đặc biệt nguy hiểm nếu function có thể thực hiện OS-level actions. Hãy coi EXECUTE trên untrusted-language functions là quyền gọi một capability đặc biệt, không phải quyền gọi một stored query thông thường.

### 2.4. Trusted language không thay thế database privileges

Ví dụ PL/pgSQL trusted có thể chạy câu lệnh:

```sql
DELETE FROM app.customers;
```

Function SECURITY INVOKER chỉ thực hiện được nếu effective user có quyền DELETE trên table. Nếu function là SECURITY DEFINER và owner có quyền DELETE, caller có thể kích hoạt hành động đó dù bản thân caller không có DELETE privilege.

Language trust không thay đổi quy tắc này.

### 2.5. Kiểm tra trusted status

Catalog `pg_language` lưu metadata của procedural languages:

```sql
SELECT
    l.lanname AS language_name,
    l.lanpltrusted AS is_trusted,
    l.lanispl AS is_procedural,
    l.lanowner::regrole AS owner,
    l.lanacl AS language_acl,
    l.laninline::regproc AS inline_handler,
    l.lanvalidator::regproc AS validator
FROM pg_language AS l
ORDER BY l.lanname;
```

Một số system languages có catalog metadata đặc thù. Không giả định mọi field hoặc handler đều có giá trị giống nhau.

### 2.6. Trusted language không phải extension trusted flag

Có hai khái niệm khác nhau:

- `pg_language.lanpltrusted`: language handler được đánh dấu trusted hay không.
- Thuộc tính `trusted` trong extension control file: extension có cho phép non-superuser cài đặt theo cơ chế được PostgreSQL hỗ trợ hay không.

Một procedural language có thể là trusted trong khi extension cài nó vẫn có yêu cầu installation riêng. Ngược lại, extension trusted không biến mọi function code bên trong thành an toàn.

## 3. Cài đặt procedural language extensions

Trước khi tạo function, language handler và shared library cần có trên server.

### 3.1. Kiểm tra language đã có

```sql
SELECT
    lanname,
    lanpltrusted,
    lanispl
FROM pg_language
ORDER BY lanname;
```

Nếu PL/pgSQL đã được cài mặc định trong database, không cần cài lại. Các language khác có thể cần package hệ điều hành hoặc extension package riêng.

### 3.2. Cài PL/Python

Trên server đã cài package tương thích:

```sql
CREATE EXTENSION plpython3u;
```

Extension phải có mặt trên host và được build cho PostgreSQL major version đang chạy. Trên managed service, việc cài đặt có thể thông qua allowlist hoặc parameter/configuration của provider.

`plpython3u` là untrusted. Chỉ superuser hoặc cơ chế quản trị tương đương mới được tạo functions bằng language này.

### 3.3. Cài PL/Perl

Tên extension thường là `plperl`, nhưng language có thể cung cấp cả trusted và untrusted variants:

```sql
CREATE EXTENSION plperl;
```

Kiểm tra catalog sau installation để xác định language names và trusted flags. Đừng suy đoán trusted status chỉ từ tên package.

### 3.4. CREATE LANGUAGE và CREATE EXTENSION

Trong các PostgreSQL versions hiện đại, nên quản lý procedural languages bằng extension commands nếu extension cung cấp language đó.

```sql
CREATE EXTENSION IF NOT EXISTS plpgsql;
```

`IF NOT EXISTS` chỉ tránh lỗi khi extension đã có tên đó. Nó không chứng minh version, schema hoặc objects đang ở trạng thái mong muốn. Kiểm tra `pg_extension` và extension version.

### 3.5. Extension installation privileges

Extension không trusted thường yêu cầu superuser. Extension có `trusted = true` trong control file có thể cho phép non-superuser cài nếu role có CREATE privilege trên database, theo rules của PostgreSQL.

Không phải extension nào cũng được đánh dấu trusted. Đọc control file, installation scripts và tài liệu của extension trước khi cấp quyền CREATE database rộng rãi.

### 3.6. Extension scripts là code được thực thi

Khi cài/nâng cấp extension, PostgreSQL chạy SQL scripts của extension. Scripts có thể tạo functions, types, operators, casts, views và objects khác.

Với extension có native library, code có thể được load vào server process. Chỉ cài extension từ nguồn đáng tin cậy, kiểm tra version, package provenance và compatibility.

### 3.7. Nâng cấp extension

```sql
ALTER EXTENSION plpython3u UPDATE;
```

Lệnh cụ thể phụ thuộc extension có update path cho version hiện tại hay không. Kiểm tra:

```sql
SELECT
    extname,
    extversion,
    extnamespace::regnamespace AS extension_schema,
    extowner::regrole AS owner
FROM pg_extension
ORDER BY extname;
```

Không tự thay shared library trên host trong khi database đang dùng version cũ mà không có deployment/compatibility plan.

### 3.8. Gỡ extension

```sql
DROP EXTENSION plpython3u RESTRICT;
```

RESTRICT giúp từ chối nếu còn objects phụ thuộc. CASCADE có thể drop các objects thuộc dependency tree. Trước khi gỡ language extension, inventory functions đang dùng language đó và đánh giá applications/objects phụ thuộc.

## 4. Quyền cần thiết để tạo và gọi routines

PostgreSQL tách nhiều privilege layers. Một developer có thể cần quyền tạo function trong schema nhưng không cần quyền cài language hoặc extension.

### 4.1. Database CREATE

Để tạo schema mới, role cần CREATE privilege trên database. Tuy nhiên, để tạo function trong schema đã tồn tại, thường cần CREATE privilege trên schema đó và USAGE trên language.

Không cấp CREATE trên database chỉ để cho phép developer thêm một function vào schema đã có.

### 4.2. Schema USAGE và CREATE

- USAGE cho phép resolve/access objects trong schema theo quyền của object.
- CREATE cho phép tạo objects mới trong schema.

Ví dụ:

```sql
GRANT USAGE ON SCHEMA app TO app_runtime;
GRANT USAGE, CREATE ON SCHEMA app_dev TO app_developer;
```

Runtime role thường chỉ cần USAGE, không cần CREATE. Developer/migration role có thể được cấp CREATE trên schema được kiểm soát.

### 4.3. Language USAGE

Để tạo function bằng một trusted procedural language, role cần USAGE privilege trên language và CREATE privilege trên target schema.

```sql
GRANT USAGE ON LANGUAGE plpgsql TO app_developer;
```

Với untrusted languages, superuser restriction vẫn áp dụng dù có language ACL.

### 4.4. Function EXECUTE

Quyền gọi function được quản lý riêng:

```sql
GRANT EXECUTE
ON FUNCTION app.calculate_discount(numeric)
TO app_runtime;
```

Function overloads được phân biệt theo argument types. Cấp quyền cho đúng signature, không dựa vào tên function đơn thuần.

### 4.5. Procedure EXECUTE

Procedures được gọi bằng CALL và cũng có EXECUTE privilege:

```sql
GRANT EXECUTE
ON PROCEDURE app.rebuild_summary(date)
TO batch_runner;
```

Function và procedure khác nhau về cách gọi, return behavior và transaction control. Dùng đúng object kind khi grant/revoke.

### 4.6. Quyền thực thi không phải quyền sở hữu

Role có EXECUTE không thể tự động ALTER hoặc DROP function. Owner hoặc role có quyền thích hợp mới quản trị được object. Tránh dùng owner role như application runtime identity.

### 4.7. Bốn câu hỏi khi review quyền

Với mỗi routine, xác định:

1. Ai được phép tạo code bằng language này?
2. Ai sở hữu function/procedure sau khi tạo?
3. Ai được phép gọi routine?
4. Routine chạy với quyền của caller hay owner?

Nếu không trả lời riêng từng câu, privilege model chưa đủ rõ.

## 5. Quyền mặc định trên functions

PostgreSQL mặc định cấp EXECUTE trên functions và procedures mới cho `PUBLIC`. PUBLIC là pseudo-role đại diện mọi database roles.

### 5.1. Rủi ro của default EXECUTE

Nếu function mới có behavior nhạy cảm và developer quên thu hồi EXECUTE, mọi roles có thể gọi function đó, tùy schema visibility và các điều kiện khác.

Rủi ro tăng khi function:

- Chạy SECURITY DEFINER.
- Đọc dữ liệu nhạy cảm.
- Ghi dữ liệu với quyền cao hơn caller.
- Gọi untrusted-language code.
- Thực hiện administrative actions.
- Dùng dynamic SQL theo input của caller.

### 5.2. Thu hồi quyền PUBLIC trên functions hiện có

```sql
REVOKE EXECUTE
ON ALL FUNCTIONS IN SCHEMA app
FROM PUBLIC;
```

Lệnh này ảnh hưởng tất cả functions trong schema được chỉ định. Trước khi chạy, inventory callers và grants để không làm gián đoạn ứng dụng.

Nếu cần xử lý procedures, dùng cú pháp routines phù hợp với PostgreSQL version hoặc revoke trên từng procedure signature.

### 5.3. Default privileges cho functions mới

Đặt default privileges cho role tạo routines:

```sql
ALTER DEFAULT PRIVILEGES
FOR ROLE app_owner
IN SCHEMA app
REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
```

Default privileges chỉ áp dụng cho objects được tạo bởi role được chỉ định trong phạm vi tương ứng. Nếu nhiều owner roles tạo functions, phải cấu hình cho từng creator role.

### 5.4. Grant cho runtime role

Sau khi thu hồi PUBLIC, cấp quyền cụ thể:

```sql
GRANT EXECUTE
ON FUNCTION app.calculate_discount(numeric)
TO app_runtime;
```

Có thể dùng group roles để quản lý quyền theo application capability thay vì grant trực tiếp cho nhiều login roles.

### 5.5. Kiểm tra quyền thực tế

```sql
SELECT
    has_function_privilege(
        'app_runtime',
        'app.calculate_discount(numeric)',
        'EXECUTE'
    ) AS runtime_can_execute;
```

Có thể kiểm tra language/schema/database privileges bằng các helper functions tương ứng:

```sql
SELECT
    has_language_privilege('app_developer', 'plpgsql', 'USAGE')
        AS can_use_plpgsql,
    has_schema_privilege('app_developer', 'app_dev', 'CREATE')
        AS can_create_in_schema,
    has_database_privilege('app_developer', current_database(), 'CREATE')
        AS can_create_schema;
```

### 5.6. Function ACL inventory

```sql
SELECT
    n.nspname AS schema_name,
    p.oid::regprocedure AS routine_identity,
    p.proowner::regrole AS owner,
    p.prosecdef AS security_definer,
    p.proacl AS explicit_acl
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname = 'app'
ORDER BY p.oid::regprocedure::text;
```

`proacl` có thể NULL khi object đang dùng default ACL behavior. NULL không có nghĩa là không có quyền nào. Dùng privilege helper functions hoặc mở rộng ACL với acldefault/aclexplode khi cần audit chính xác.

## 6. SECURITY INVOKER và SECURITY DEFINER

Đây là khác biệt quan trọng nhất khi đánh giá function execution context.

### 6.1. SECURITY INVOKER

Mặc định, function chạy với quyền của user gọi function:

```sql
CREATE FUNCTION app.get_my_orders()
RETURNS SETOF app.orders
LANGUAGE sql
SECURITY INVOKER
AS $function$
    SELECT *
    FROM app.orders
    WHERE customer_id = current_user_id();
$function$;
```

Caller cần các privileges cần thiết để thực hiện underlying statements. Đây thường là lựa chọn an toàn nhất cho functions không cần nâng quyền.

### 6.2. SECURITY DEFINER

Function khai báo SECURITY DEFINER chạy với quyền của function owner:

```sql
CREATE FUNCTION app_private.close_expired_orders()
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
AS $function$
DECLARE
    affected_rows integer;
BEGIN
    UPDATE app.orders
    SET status = 'expired'
    WHERE status = 'pending'
      AND expires_at < clock_timestamp();

    GET DIAGNOSTICS affected_rows = ROW_COUNT;
    RETURN affected_rows;
END;
$function$;
```

Nếu owner có quyền UPDATE trên table, caller có thể kích hoạt UPDATE mà không cần trực tiếp có quyền đó.

Đây là một capability boundary. Function body phải giới hạn rõ hành động, input và rows có thể bị tác động.

### 6.3. SECURITY DEFINER không tự động an toàn vì caller có EXECUTE

Khi cấp EXECUTE cho caller, caller có thể truyền arguments và kích hoạt code dưới quyền owner. Nếu function nhận table name, SQL fragment hoặc role name từ input, attacker có thể biến function thành một confused deputy.

Chỉ expose những operation có contract nhỏ, validation rõ và không cho caller kiểm soát SQL tùy ý.

### 6.4. Dùng owner role riêng

Một SECURITY DEFINER function không nên thuộc superuser nếu chỉ cần quyền trên một vài tables.

Tạo role owner không có LOGIN:

```sql
CREATE ROLE app_function_owner NOLOGIN;
GRANT USAGE ON SCHEMA app_private TO app_function_owner;
GRANT UPDATE ON app.orders TO app_function_owner;
```

Chuyển ownership:

```sql
ALTER FUNCTION app_private.close_expired_orders()
OWNER TO app_function_owner;
```

Role owner chỉ nhận privileges cần thiết. Không cấp role này cho application login hoặc developer role không cần thiết.

### 6.5. Owner không nên có quyền cao hơn nhu cầu

Tránh:

- SUPERUSER.
- CREATEROLE.
- CREATEDB.
- BYPASSRLS.
- Quyền ghi vào mọi schemas.
- Membership vào broad administrative roles.

Nếu function cần đọc/ghi một table, cấp quyền đúng trên table đó. Nếu cần sequence, schema hoặc type, cấp thêm chính xác những privileges tương ứng.

## 7. Search path và object-shadowing attacks

`search_path` quyết định thứ tự PostgreSQL tìm unqualified object names. Một SECURITY DEFINER function có thể bị đánh lừa nếu attacker tạo object cùng tên trong schema được tìm trước object đáng tin cậy.

### 7.1. Ví dụ nguy hiểm

Giả sử function dùng unqualified function call:

```sql
CREATE FUNCTION app_private.transfer_credit(
    p_from bigint,
    p_to bigint,
    p_amount numeric
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $function$
BEGIN
    PERFORM validate_transfer(p_from, p_to, p_amount);

    UPDATE app.accounts
    SET balance = balance - p_amount
    WHERE id = p_from;
END;
$function$;
```

Nếu attacker có CREATE privilege trong schema nằm trước schema chứa function thật, họ có thể tạo một function hoặc operator cùng tên để được resolve thay thế theo search_path.

Function privileged có thể vô tình gọi object do attacker kiểm soát.

### 7.2. Gắn search_path vào function

Một cách bảo vệ là đặt function-local search_path chỉ gồm schemas đáng tin và đưa pg_temp ở cuối:

```sql
CREATE FUNCTION app_private.safe_transfer(
    p_from bigint,
    p_to bigint,
    p_amount numeric
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app_private, app, pg_temp
AS $function$
BEGIN
    PERFORM app_private.validate_transfer(
        p_from,
        p_to,
        p_amount
    );

    UPDATE app.accounts
    SET balance = balance - p_amount
    WHERE id = p_from;
END;
$function$;
```

`pg_catalog` được đặt rõ ở đầu. Các schemas `app_private` và `app` chỉ an toàn nếu roles không đáng tin không thể CREATE/REPLACE objects ở đó. `pg_temp` được đặt cuối để temporary objects không được ưu tiên hơn trusted objects.

Danh sách schemas phải được chọn theo routine thực tế. Không thêm schema do application users có thể ghi vào.

### 7.3. Schema-qualify object names

Trong privileged functions, ưu tiên:

```sql
UPDATE app.accounts
SET balance = balance - p_amount
WHERE id = p_from;
```

thay vì:

```sql
UPDATE accounts
SET balance = balance - p_amount
WHERE id = p_from;
```

Schema qualification giảm phụ thuộc search_path. Với built-in functions, đặt pg_catalog trong path hoặc qualify function nhạy cảm khi phù hợp.

### 7.4. Temporary schema

PostgreSQL có temporary schema cho mỗi session. Nếu pg_temp không được đặt rõ ở cuối search_path của SECURITY DEFINER function, temporary objects có thể được ưu tiên khi resolve relation/type names theo search-path rules.

Đừng cho rằng attacker cần CREATE trên schema app mới có thể shadow object; temporary objects cũng cần được xem xét.

### 7.5. Quyền CREATE trên schema

Kiểm tra ai có thể tạo objects trong các schemas mà privileged function dùng:

```sql
SELECT
    n.nspname AS schema_name,
    pg_get_userbyid(n.nspowner) AS owner,
    has_schema_privilege(
        'app_runtime',
        n.oid,
        'CREATE'
    ) AS runtime_can_create,
    has_schema_privilege(
        'app_runtime',
        n.oid,
        'USAGE'
    ) AS runtime_can_use
FROM pg_namespace AS n
WHERE n.nspname IN ('public', 'app', 'app_private')
ORDER BY n.nspname;
```

Không giả định PUBLIC luôn có hoặc không có CREATE trên public schema. Default đã thay đổi theo PostgreSQL version và lịch sử upgrade; kiểm tra ACL thực tế.

### 7.6. Bảo vệ public schema

Nếu policy yêu cầu, thu hồi CREATE từ PUBLIC:

```sql
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
```

Cần kiểm tra extension installers, migration tools và applications có phụ thuộc vào quyền CREATE ở public hay không trước khi áp dụng.

## 8. SQL injection trong procedural functions

PL/pgSQL cho phép tạo và thực thi SQL động. Nếu nối input không tin cậy vào SQL string, function có thể bị SQL injection.

### 8.1. Nối chuỗi trực tiếp là nguy hiểm

Ví dụ không an toàn:

```sql
EXECUTE 'SELECT * FROM app.customers WHERE email = '''
    || p_email
    || '''';
```

Input chứa quote hoặc SQL fragments có thể làm thay đổi câu lệnh.

### 8.2. Dùng USING cho values

Giải pháp an toàn cho data values:

```sql
EXECUTE
    'SELECT id FROM app.customers WHERE email = $1'
INTO customer_id
USING p_email;
```

USING bind parameters tách values khỏi SQL syntax. Không cần tự escape quote trong value.

### 8.3. Dùng format('%I') cho identifiers

Identifiers như schema/table/column names không thể truyền bằng bind parameter. Dùng identifier quoting:

```sql
EXECUTE format(
    'SELECT count(*) FROM %I.%I WHERE status = $1',
    p_schema,
    p_table
)
INTO row_count
USING p_status;
```

`%I` quote identifier an toàn. `%L` quote literal, nhưng với values nên ưu tiên USING parameters.

### 8.4. Quoting không thay thế allowlist

Nếu caller có thể yêu cầu function truy cập bất kỳ table nào, `format('%I')` chỉ ngăn thay đổi SQL syntax; nó không ngăn caller truy cập object ngoài phạm vi nghiệp vụ.

Dùng allowlist:

```sql
IF p_table NOT IN ('orders', 'order_items') THEN
    RAISE EXCEPTION 'table is not allowed';
END IF;
```

Schema/table allowlist phải do code kiểm soát, không lấy từ bảng mà caller có thể sửa.

### 8.5. Không nhận raw WHERE/ORDER BY fragments

Một function nhận `p_filter text` rồi nối trực tiếp vào WHERE là một SQL execution interface. Không expose raw SQL fragments cho runtime roles. Thay bằng parameters typed, enum choices hoặc các predicates được code xây dựng sẵn.

### 8.6. SQL injection trong other languages

PL/Python, PL/Perl và các procedural languages khác cũng có thể ghép SQL string. Dùng driver/parameter APIs của language nếu được hỗ trợ, hoặc gọi SPI/parameterized execution theo API của extension.

Nguyên tắc vẫn giống nhau: values phải được bind, identifiers phải được validate/quote, và quyền thực thi phải giới hạn.

## 9. Rủi ro của untrusted languages và C functions

Untrusted languages mở rộng quyền của code vượt ra ngoài database privilege model thông thường.

### 9.1. PL/PythonU

PL/PythonU có thể sử dụng Python runtime capabilities như import modules, truy cập files hoặc gọi APIs của OS, tùy environment và package được cài.

Ví dụ function:

```sql
CREATE FUNCTION admin.read_server_file(p_path text)
RETURNS text
LANGUAGE plpython3u
AS $python$
with open(p_path, "r", encoding="utf-8") as source:
    return source.read()
$python$;
```

Đây là ví dụ minh họa rủi ro. Nếu EXECUTE bị cấp rộng, caller có thể yêu cầu đọc file mà PostgreSQL OS account có quyền đọc. Không triển khai function kiểu này như tiện ích chung cho application users.

### 9.2. PL/PerlU và PL/TclU

Untrusted variants có thể truy cập capabilities mà trusted variants hạn chế. Review module loading, filesystem/network calls và process execution.

### 9.3. C-language functions

C functions chạy native code trong PostgreSQL backend process. Một bug có thể:

- Crash backend.
- Corrupt memory.
- Làm hỏng server process.
- Bypass assumptions của SQL-level validation.
- Truy cập tài nguyên OS theo quyền của server process.
- Tạo security vulnerabilities nghiêm trọng.

Chỉ dùng C functions từ source đã review, build tương thích và package provenance rõ. Không cho users thông thường tạo hoặc thay native code.

### 9.4. OS-level permissions vẫn áp dụng

Function chạy dưới OS account của PostgreSQL service, không chạy dưới OS account của database role gọi function. Database GRANT không giới hạn filesystem permissions của OS user.

Dùng OS sandboxing, container/VM isolation, filesystem permissions và network policy để giảm blast radius. Database privilege model là một lớp bảo vệ, không thay thế OS security.

### 9.5. EXECUTE trên untrusted function là capability

Một function untrusted có thể được superuser tạo nhưng được EXECUTE cấp cho role bình thường. Khi cấp quyền, hãy review từng input và giới hạn khả năng của function. Không cấp EXECUTE cho PUBLIC hoặc broad runtime roles chỉ vì function có vẻ là helper.

## 10. Function properties ảnh hưởng đến execution

Function có nhiều properties ngoài language và security mode. Chúng ảnh hưởng planner, runtime behavior và một số security assumptions.

### 10.1. Volatility

| Property | Ý nghĩa |
| --- | --- |
| IMMUTABLE | Kết quả chỉ phụ thuộc arguments và không đổi theo database state |
| STABLE | Kết quả ổn định trong một statement theo contract của PostgreSQL |
| VOLATILE | Có thể thay đổi giữa calls, có side effects hoặc phụ thuộc trạng thái thay đổi |

Không khai báo function VOLATILE là IMMUTABLE để ép planner tối ưu. Planner có thể constant-fold hoặc cache assumptions dựa trên property đã khai báo.

Volatility không phải privilege. Function IMMUTABLE vẫn có thể chứa bug hoặc SQL injection nếu implementation sai.

### 10.2. STRICT

`STRICT` (còn gọi RETURNS NULL ON NULL INPUT) khiến function không được gọi khi bất kỳ input argument nào là NULL; PostgreSQL trả NULL trực tiếp.

Dùng khi semantics đúng với mọi function inputs. Không dùng STRICT để thay thế validation cho complex business rules.

### 10.3. PARALLEL safety

- `PARALLEL SAFE`: function có thể chạy trong parallel worker theo contract.
- `PARALLEL RESTRICTED`: chỉ chạy trong parallel leader.
- `PARALLEL UNSAFE`: không được chạy trong parallel query.

Khai báo sai có thể gây lỗi hoặc behavior không an toàn. Parallel safety là execution property, không phải security sandbox.

### 10.4. LEAKPROOF

LEAKPROOF là lời cam kết function không làm lộ thông tin về arguments ngoài kết quả được định nghĩa, kể cả qua side effects/error behavior theo semantics planner. PostgreSQL chỉ cho superuser đánh dấu function leakproof.

Không gắn LEAKPROOF chỉ để cải thiện query plan. Một function leak thông tin có thể ảnh hưởng row-level security và security barrier view behavior.

### 10.5. COST và ROWS

`COST` và `ROWS` giúp planner ước tính chi phí/cardinality của functions. Khai báo sai có thể dẫn đến query plans kém hiệu quả, nhưng không trực tiếp thay đổi function privileges.

### 10.6. SET configuration per function

Function có thể khai báo settings áp dụng trong lúc chạy:

```sql
CREATE FUNCTION app_private.secure_lookup(p_id bigint)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app_private, app, pg_temp
SET statement_timeout = '3s'
AS $function$
BEGIN
    RETURN (
        SELECT customer_name
        FROM app.customers
        WHERE id = p_id
    );
END;
$function$;
```

Function-local configuration giúp giới hạn environment. Chọn settings phù hợp với behavior và không dùng SET tùy tiện làm thay đổi semantics của caller.

## 11. Row-level security và SECURITY DEFINER

Row-Level Security (RLS) kiểm soát rows mà role có thể nhìn thấy hoặc sửa. SECURITY DEFINER có thể làm thay đổi effective user và kết quả policy evaluation.

### 11.1. Table owner thường bypass RLS

Table owner thường bypass row security policies, trừ khi table bật FORCE ROW LEVEL SECURITY. Superusers và roles có BYPASSRLS cũng bypass RLS.

Nếu SECURITY DEFINER function owner là table owner, function có thể truy cập nhiều rows hơn caller dự kiến.

### 11.2. Kiểm tra RLS

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relrowsecurity AS rls_enabled,
    c.relforcerowsecurity AS force_rls
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname = 'app'
ORDER BY c.relname;
```

### 11.3. Policy evaluation

RLS policies thường dùng current_user/session context. Trong SECURITY DEFINER, current_user phản ánh effective owner trong quá trình thực thi; session_user vẫn là identity ban đầu của session. Chọn identity phù hợp với authorization design.

Không dựa vào current_user để xác định end-user nếu mọi requests dùng một shared database login.

### 11.4. Thiết kế function với RLS

Nếu function phải tuân theo RLS:

- Chọn owner role không sở hữu table khi phù hợp.
- Không cấp BYPASSRLS.
- Xem FORCE ROW LEVEL SECURITY.
- Kiểm tra policy với effective user thực tế.
- Test bằng role runtime, không chỉ superuser.
- Không cho caller giả mạo user identity qua input không được xác thực.

## 12. Trigger, event trigger và implicit execution

Function không chỉ chạy khi user gọi SELECT hoặc CALL. PostgreSQL có thể gọi function như một phần của các operations khác.

### 12.1. Trigger functions

Trigger function được gọi khi table events xảy ra:

```sql
CREATE FUNCTION app_private.audit_order_change()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    INSERT INTO audit.order_changes (
        order_id,
        changed_at,
        operation
    )
    VALUES (
        NEW.id,
        clock_timestamp(),
        TG_OP
    );

    RETURN NEW;
END;
$function$;
```

Khi tạo trigger, function phải đáp ứng trigger-function contract. Nếu trigger function là SECURITY DEFINER, mọi DML event có thể kích hoạt behavior dưới quyền owner.

### 12.2. Event triggers

Event triggers có thể chạy khi DDL events xảy ra. Chúng có phạm vi ảnh hưởng rộng vì một DDL statement có thể kích hoạt code tự động.

Chỉ role quản trị đáng tin cậy mới nên quản lý event triggers. Audit function body, owner, search_path và các event tags được xử lý.

### 12.3. Functions trong expressions

Functions có thể được gọi qua:

- DEFAULT expressions.
- CHECK constraints.
- Generated columns.
- Index expressions.
- Views.
- RLS policies.
- Operators và casts.
- Triggers.
- Rules.

Một function có thể chạy trong query mà operator không nhìn thấy tên function rõ ràng trong application code. Khi review function EXECUTE và security context, tìm các dependencies tĩnh lẫn runtime call paths.

### 12.4. Function EXECUTE privilege và trigger setup

PostgreSQL kiểm tra EXECUTE privilege phù hợp khi tạo trigger để gắn trigger function. Runtime behavior sau đó phụ thuộc function security mode và quyền của trigger execution context.

Không dùng quyền tạo trigger rộng rãi như cách cho application users kiểm soát privileged code.

## 13. Security-definer function an toàn: mẫu thiết kế

Một privileged routine nên có interface hẹp và các assumptions rõ ràng.

### 13.1. Tạo owner role chuyên biệt

```sql
CREATE ROLE order_maintenance_owner NOLOGIN;

GRANT USAGE ON SCHEMA app_private TO order_maintenance_owner;
GRANT SELECT, UPDATE ON app.orders TO order_maintenance_owner;
```

Owner không cần LOGIN. Chỉ migration/admin role được phép SET ROLE hoặc thay đổi ownership theo policy.

### 13.2. Tạo function trong schema được bảo vệ

```sql
CREATE FUNCTION app_private.expire_one_order(p_order_id bigint)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app_private, app, pg_temp
AS $function$
DECLARE
    changed_count integer;
BEGIN
    IF p_order_id IS NULL THEN
        RAISE EXCEPTION 'order id is required';
    END IF;

    UPDATE app.orders
    SET status = 'expired',
        updated_at = clock_timestamp()
    WHERE id = p_order_id
      AND status = 'pending'
      AND expires_at < clock_timestamp();

    GET DIAGNOSTICS changed_count = ROW_COUNT;

    RETURN changed_count = 1;
END;
$function$;

ALTER FUNCTION app_private.expire_one_order(bigint)
OWNER TO order_maintenance_owner;
```

Function giới hạn operation vào một order ID và kiểm tra trạng thái hiện tại. Business authorization vẫn cần xác định caller nào được phép expire order nào.

### 13.3. Thu hồi PUBLIC EXECUTE

```sql
REVOKE ALL
ON FUNCTION app_private.expire_one_order(bigint)
FROM PUBLIC;

GRANT EXECUTE
ON FUNCTION app_private.expire_one_order(bigint)
TO order_job_runner;
```

Schema cũng cần được bảo vệ để runtime role không thể CREATE/REPLACE objects trong đó.

### 13.4. Test bằng runtime role

Test:

- Caller được phép và không được phép.
- NULL/invalid inputs.
- Order đã paid/canceled.
- Concurrent calls.
- RLS behavior.
- Lock waits và transaction rollback.
- Search_path thay đổi.
- Temporary objects cùng tên.
- Function owner có đúng privileges tối thiểu.

### 13.5. Function không phải authorization policy tự động

Nếu mọi authenticated users đều có EXECUTE trên function, function cần tự kiểm tra caller có quyền thao tác target row hay không. Không dựa vào việc caller không có direct table privileges nếu function không kiểm tra business authorization.

## 14. Kiểm tra functions và security configuration

Audit định kỳ giúp tìm routines có elevated execution context hoặc configuration bất thường.

### 14.1. SECURITY DEFINER inventory

```sql
SELECT
    n.nspname AS schema_name,
    p.oid::regprocedure AS routine_identity,
    p.proowner::regrole AS owner,
    l.lanname AS language,
    p.prosecdef AS security_definer,
    p.proconfig AS function_settings,
    p.proacl AS acl
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
JOIN pg_language AS l
    ON l.oid = p.prolang
WHERE p.prosecdef
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, p.oid::regprocedure::text;
```

### 14.2. Functions theo language

```sql
SELECT
    l.lanname AS language_name,
    l.lanpltrusted AS trusted_language,
    n.nspname AS schema_name,
    count(*) AS routine_count
FROM pg_proc AS p
JOIN pg_language AS l
    ON l.oid = p.prolang
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
GROUP BY l.lanname, l.lanpltrusted, n.nspname
ORDER BY l.lanname, n.nspname;
```

### 14.3. SECURITY DEFINER không có function-local search_path

```sql
SELECT
    n.nspname AS schema_name,
    p.oid::regprocedure AS routine_identity,
    p.proowner::regrole AS owner,
    p.proconfig
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE p.prosecdef
  AND NOT EXISTS (
      SELECT 1
      FROM unnest(COALESCE(p.proconfig, ARRAY[]::text[])) AS setting
      WHERE setting LIKE 'search_path=%'
  )
ORDER BY n.nspname, p.oid::regprocedure::text;
```

Đây là review queue, không phải bằng chứng function chắc chắn vulnerable. Function có thể schema-qualify mọi objects và không dùng untrusted search path. Tuy nhiên, đặt function-local search_path tường minh thường giúp giảm rủi ro.

### 14.4. Routines dùng untrusted language

```sql
SELECT
    n.nspname AS schema_name,
    p.oid::regprocedure AS routine_identity,
    p.proowner::regrole AS owner,
    l.lanname AS language_name,
    l.lanpltrusted AS is_trusted,
    p.prosecdef AS security_definer,
    p.proacl
FROM pg_proc AS p
JOIN pg_language AS l
    ON l.oid = p.prolang
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE NOT l.lanpltrusted
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY l.lanname, n.nspname, p.oid::regprocedure::text;
```

Các functions trong untrusted language cần owner review và EXECUTE ACL review. Không grant EXECUTE rộng theo schema nếu schema chứa untrusted routines.

### 14.5. Routine properties

```sql
SELECT
    n.nspname AS schema_name,
    p.oid::regprocedure AS routine_identity,
    p.provolatile,
    p.proisstrict,
    p.proparallel,
    p.proleakproof,
    p.prosecdef,
    p.proconfig
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname = 'app'
ORDER BY p.oid::regprocedure::text;
```

Catalog columns có thể thay đổi theo major version. Với automation đa phiên bản, kiểm tra server version và catalog definitions trước khi chạy query.

## 15. Kiểm tra language privileges

Language ACL nằm trong pg_language.lanacl. Dùng helper function để xác nhận privilege hiệu lực.

### 15.1. Language ACL

```sql
SELECT
    lanname,
    lanpltrusted,
    lanacl
FROM pg_language
ORDER BY lanname;
```

`lanacl` NULL có thể biểu thị default ACL behavior. Đừng diễn giải NULL như không ai có quyền.

### 15.2. Kiểm tra USAGE

```sql
SELECT
    rol.rolname,
    lang.lanname,
    has_language_privilege(
        rol.rolname,
        lang.lanname,
        'USAGE'
    ) AS can_use_language
FROM pg_roles AS rol
CROSS JOIN pg_language AS lang
WHERE rol.rolname IN (
    'app_developer',
    'app_runtime',
    'migration_runner'
)
ORDER BY rol.rolname, lang.lanname;
```

Kết quả cho biết privilege hiệu lực theo PostgreSQL. Với untrusted languages, superuser-only restrictions vẫn cần được xem xét riêng.

### 15.3. Thu hồi language USAGE

```sql
REVOKE USAGE ON LANGUAGE plpython3u FROM PUBLIC;
```

Câu lệnh chỉ có ý nghĩa khi language/ACL hỗ trợ và không thay thế superuser restriction. Kiểm tra owner/ACL trước khi sửa; một số language có default grants khác nhau.

### 15.4. Tạo function cần nhiều quyền cùng lúc

Một role có thể cần:

- USAGE trên target schema để resolve referenced objects.
- CREATE trên schema nơi function được tạo.
- USAGE trên language.
- EXECUTE trên functions được gọi trong function body theo execution context.
- Các table/sequence/type privileges cần thiết nếu SECURITY INVOKER.
- Quyền sở hữu hoặc quyền quản trị nếu thay đổi owner/security properties.

Không giải quyết lỗi CREATE FUNCTION bằng cách cấp SUPERUSER cho developer.

## 16. Default privileges và deployment ownership

Một privilege model bền vững cần quy định role nào tạo objects và quyền mặc định của objects mới.

### 16.1. Creator role

Chọn một role sở hữu schema/functions, ví dụ app_owner. Migration runner có thể SET ROLE app_owner trong deployment process nếu policy cho phép.

Runtime role chỉ nhận USAGE/EXECUTE cần thiết. Không để mỗi developer tạo routines bằng personal login và trở thành owner production.

### 16.2. Default privileges

```sql
ALTER DEFAULT PRIVILEGES
FOR ROLE app_owner
IN SCHEMA app
REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

ALTER DEFAULT PRIVILEGES
FOR ROLE app_owner
IN SCHEMA app
GRANT EXECUTE ON FUNCTIONS TO app_runtime;
```

Default privileges không áp dụng hồi tố cho functions đã tồn tại. Chúng cũng không tự áp dụng cho objects do một role khác tạo.

### 16.3. Audit default ACL

```sql
SELECT
    defaclrole::regrole AS creator_role,
    defaclnamespace::regnamespace AS schema_name,
    defaclobjtype,
    defaclacl
FROM pg_default_acl
ORDER BY creator_role, schema_name, defaclobjtype;
```

Nếu schema-specific default privileges được thiết lập, chúng được kết hợp với global defaults theo rules của PostgreSQL. Kiểm tra cả hai scopes khi audit.

### 16.4. Existing objects cần revoke riêng

Sau khi thiết lập defaults, review/revoke quyền trên functions hiện tại:

```sql
REVOKE EXECUTE
ON ALL FUNCTIONS IN SCHEMA app
FROM PUBLIC;
```

Sau đó grant cho runtime roles theo danh sách function signature đã được phê duyệt.

### 16.5. CREATE OR REPLACE FUNCTION

CREATE OR REPLACE FUNCTION giữ nguyên identity của function và có thể giữ ownership/permissions hiện có. Nhưng code body hoặc properties có thể thay đổi. Deployment review phải kiểm tra SECURITY DEFINER, SET clauses, language, volatility và ACL sau replace.

Không cho runtime roles quyền CREATE trong production schema chỉ để họ tự cập nhật function body.

## 17. Extension installation và supply-chain risk

Extension có thể thêm native code, procedural languages và functions chạy với quyền cao. Vì vậy extension management là một phần của security boundary.

### 17.1. Kiểm tra extensions đã cài

```sql
SELECT
    e.extname,
    e.extversion,
    e.extowner::regrole AS owner,
    n.nspname AS extension_schema
FROM pg_extension AS e
JOIN pg_namespace AS n
    ON n.oid = e.extnamespace
ORDER BY e.extname;
```

### 17.2. Kiểm tra extension availability

```sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_available_extensions
ORDER BY name;
```

`pg_available_extensions` phản ánh extensions có sẵn cho server/package environment hiện tại. Không phải tất cả đều được phép cài trên managed services.

### 17.3. Trusted extension installation

Extension control file có thể khai báo `trusted = true`. Điều đó cho phép non-superuser có CREATE privilege trên database cài extension theo cơ chế PostgreSQL hỗ trợ.

Trusted extension vẫn cần được review. Một extension có quyền cài đặt đặc biệt phải được đánh giá theo installation scripts và code thực thi của nó.

### 17.4. Extension package provenance

Kiểm tra:

- Publisher/source repository.
- Release tags và checksums.
- Build tương thích PostgreSQL major version.
- Shared library dependencies.
- Security advisories.
- Update/rollback path.
- OS package owner và installation permissions.

Không cài extension từ file không rõ nguồn chỉ vì nó cung cấp một function tiện dụng.

### 17.5. Extension ownership và dependencies

Extension objects thường được đánh dấu membership dependency. Không drop member objects riêng lẻ bằng catalog edits hoặc DDL tùy tiện. Dùng extension update/drop commands và review CASCADE impact.

### 17.6. Managed database restrictions

Cloud provider có thể giới hạn procedural languages/extensions và thay thế superuser bằng managed administrative role. Kiểm tra provider allowlist, parameter groups và supported versions. Không giả định quyền superuser của self-hosted PostgreSQL có sẵn.

## 18. Function owner và quyền thay đổi code

Một function có thể có quyền EXECUTE rộng nhưng chỉ owner mới có thể thay đổi code hoặc security properties.

### 18.1. Owner inventory

```sql
SELECT
    n.nspname AS schema_name,
    p.oid::regprocedure AS routine_identity,
    p.proowner::regrole AS owner,
    l.lanname AS language,
    p.prosecdef AS security_definer
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
JOIN pg_language AS l
    ON l.oid = p.prolang
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY owner, routine_identity::text;
```

### 18.2. Owner role không nên là login runtime

Một owner role NOLOGIN giảm khả năng application session trở thành owner. Migration runner được cấp membership có kiểm soát để deploy objects.

### 18.3. Ownership transfer

```sql
ALTER FUNCTION app.calculate_discount(numeric)
OWNER TO app_owner;
```

Thay owner cần các quyền phù hợp trên function và role mới. Ownership change không tự động thiết kế lại grants của callers; kiểm tra ACL sau chuyển đổi.

### 18.4. Drop/recreate và grants

DROP rồi CREATE lại function có thể làm mất grants/comments/dependencies hoặc thay đổi OID. CREATE OR REPLACE thường phù hợp hơn khi cần giữ identity, nhưng vẫn phải kiểm tra signature và properties.

## 19. Function code review checklist

Review routine như một security-sensitive code path.

### 19.1. Identity và ownership

- Schema có phải schema được bảo vệ không?
- Owner có phải role NOLOGIN tối thiểu quyền không?
- Language có trusted không?
- Function có thật sự cần SECURITY DEFINER không?
- Ai có quyền ALTER/REPLACE function?

### 19.2. Caller privileges

- Ai có EXECUTE?
- PUBLIC có EXECUTE không?
- Runtime role có cần function này không?
- Có grant theo signature chính xác không?
- Function có bị gọi gián tiếp qua trigger/view/policy không?

### 19.3. Execution context

- Search_path có được cố định an toàn không?
- pg_temp có được đặt ở vị trí phù hợp không?
- Objects có schema-qualified không?
- Function có SET configuration nhạy cảm không?
- RLS behavior có đúng effective user không?

### 19.4. Input handling

- Có dynamic SQL không?
- Values có dùng bind parameters/USING không?
- Identifiers có quote bằng %I và allowlist không?
- Có nhận raw SQL fragments không?
- NULL/range/format validation đã có chưa?

### 19.5. Side effects và resources

- Function có ghi dữ liệu hoặc gọi external APIs không?
- Có thể chạy quá lâu hoặc tạo unbounded loops không?
- Có transaction/lock side effects không?
- Có thể được gọi nhiều lần hoặc đồng thời không?
- Có idempotency/authorization checks không?

## 20. Monitoring và auditing routine execution

PostgreSQL có statistics cho functions khi tracking được bật. Logs và audit extensions có thể bổ sung thông tin về caller/query behavior.

### 20.1. Function statistics

```sql
SHOW track_functions;
```

Các giá trị có thể gồm none, pl và all tùy version/configuration. PL/pgSQL và các procedural functions có thể được theo dõi khi setting phù hợp.

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

Statistics là aggregate counters trong stats window, không phải security audit log hoàn chỉnh.

### 20.2. Function statistics limitations

- Stats có thể reset.
- Function calls nested có thể làm total/self time khác nhau.
- Function tracking có overhead.
- Không phải mọi language/extension đều được thống kê giống nhau.
- Caller identity không nhất thiết có trong view.

### 20.3. Logging

Có thể dùng log settings như log_min_duration_statement để ghi statements chậm. pg_stat_statements giúp tổng hợp query fingerprints. Nếu cần audit ai gọi routine nào, dùng logging/audit design phù hợp và kiểm soát dữ liệu nhạy cảm trong logs.

### 20.4. Security audit extension

Một số environments dùng pgAudit hoặc database activity monitoring tools. Extension/audit configuration phải được review riêng; audit logs có thể chứa SQL, parameters hoặc identifiers nhạy cảm.

### 20.5. Không ghi secrets vào function errors

Tránh đưa credentials, tokens hoặc raw sensitive inputs vào RAISE EXCEPTION, NOTICE hay application logs. Error context có thể được lưu ở nhiều nơi.

## 21. Common privilege patterns

### 21.1. Runtime role chỉ gọi routines

```sql
CREATE ROLE app_runtime NOLOGIN;

GRANT CONNECT ON DATABASE appdb TO app_runtime;
GRANT USAGE ON SCHEMA app TO app_runtime;
GRANT EXECUTE ON FUNCTION app.calculate_discount(numeric)
TO app_runtime;
```

Application login role có thể là member của group role app_runtime. Không cấp CREATE trên schema hoặc USAGE trên untrusted languages nếu không cần.

### 21.2. Developer role tạo functions trong development schema

```sql
CREATE ROLE app_developer NOLOGIN;

GRANT USAGE, CREATE ON SCHEMA app_dev TO app_developer;
GRANT USAGE ON LANGUAGE plpgsql TO app_developer;
```

Developer role không cần SUPERUSER, CREATEROLE hoặc quyền cài extension trên production.

### 21.3. Migration owner quản lý production functions

```sql
CREATE ROLE app_owner NOLOGIN;

GRANT USAGE, CREATE ON SCHEMA app TO app_owner;
GRANT USAGE ON LANGUAGE plpgsql TO app_owner;
```

Migration runner được cấp membership có kiểm soát vào app_owner và deploy qua reviewed migration scripts.

### 21.4. Privileged maintenance function

Tạo dedicated NOLOGIN owner, cấp quyền trên đúng tables, cố định search_path, revoke PUBLIC EXECUTE và grant cho một job role chuyên biệt.

### 21.5. Không cấp quyền toàn schema nếu có mixed sensitivity

`GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA app TO app_runtime` có thể vô tình cấp quyền trên routine mới hoặc nhạy cảm đã tồn tại. Ưu tiên explicit grants hoặc schema separation theo trust boundary.

## 22. Phân tách schemas theo trust boundary

Tổ chức schemas giúp giảm rủi ro search_path và quyền CREATE.

### 22.1. Ví dụ phân chia

| Schema | Nội dung | Runtime access |
| --- | --- | --- |
| app | Tables/views nghiệp vụ | USAGE, table grants phù hợp |
| app_api | Functions được phép gọi | USAGE, EXECUTE chọn lọc |
| app_private | Helpers nội bộ và SECURITY DEFINER | Không cho runtime CREATE; EXECUTE hạn chế |
| audit | Audit records/functions | Access rất hạn chế |
| extensions | Extension objects nếu policy yêu cầu | Theo extension owner/ACL |

### 22.2. Schema private không có nghĩa tự động an toàn

Nếu runtime role có CREATE trên app_private, attacker có thể thay objects mà privileged functions resolve. Bảo vệ schema ACL và owner.

### 22.3. search_path defaults

Cấu hình search_path theo role/database cho convenience, nhưng privileged functions vẫn nên đặt function-local search_path và schema-qualify objects. Không dựa hoàn toàn vào session configuration của caller.

## 23. Các lỗi thường gặp

| Giả định hoặc triệu chứng | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Trusted language nghĩa function an toàn | Trusted chỉ nói về language sandbox | Review code, owner, ACL và execution context |
| Chỉ superuser mới có thể gọi PL/PythonU | Superuser restriction chủ yếu kiểm soát creation; EXECUTE có thể được grant | Audit callers và EXECUTE ACL |
| SECURITY DEFINER chỉ là tối ưu quyền | Function chạy với owner privileges | Dùng owner NOLOGIN tối thiểu quyền và interface hẹp |
| Function không có EXECUTE grant thì không ai gọi được | PUBLIC default có thể có EXECUTE | Revoke PUBLIC và kiểm tra ACL |
| search_path của caller luôn đáng tin | Caller có thể shadow unqualified names | Function-local search_path, trusted schemas và pg_temp cuối |
| Quote identifier là đủ an toàn | Caller vẫn có thể chọn object ngoài phạm vi | Identifier allowlist và authorization |
| Bind parameter dùng được cho table name | Bind parameters chỉ dành cho values | format('%I') cho identifier |
| C language giống PL/pgSQL | Native code chạy trong backend process | Review binary/source và chỉ cấp cho superuser |
| RLS luôn giới hạn SECURITY DEFINER | Owner/BYPASSRLS có thể bypass | Review owner, FORCE RLS và policy context |
| Extension trusted là code đã được audit | trusted flag chỉ điều khiển installation eligibility | Review source, scripts và package provenance |
| CREATE OR REPLACE không ảnh hưởng security | Body/properties có thể thay đổi | Review diff, owner, ACL và SET clauses |
| Runtime cần CREATE schema để gọi function | EXECUTE và schema USAGE là đủ trong nhiều trường hợp | Không cấp CREATE không cần thiết |
| Function stats là audit log | Counters aggregate và có thể reset | Dùng audit/logging nếu cần caller history |
| Drop language sẽ chỉ xóa handler | Extension có thể quản lý nhiều objects | Inventory dependencies, dùng RESTRICT |
| Search_path public luôn giống mọi version | Default ACL thay đổi theo version/upgrade | Kiểm tra ACL thực tế |

## 24. Incident response cho function privilege abuse

Nếu phát hiện function bị gọi ngoài ý muốn hoặc SECURITY DEFINER có nguy cơ bị khai thác:

**Bước 1 — Contain.** Thu hồi EXECUTE trên function hoặc disable entry point theo change procedure. Đánh giá ảnh hưởng callers và background jobs.

**Bước 2 — Preserve evidence.** Lưu function definition, owner, ACL, language, proconfig, grants, logs và timestamps trước khi sửa.

**Bước 3 — Determine execution context.** Xác định SECURITY INVOKER/DEFINER, effective owner, language trust và OS-level capabilities.

**Bước 4 — Identify callers.** Kiểm tra logs, application traces, pg_stat_statements, audit extension và scheduled jobs.

**Bước 5 — Inspect dependencies.** Tìm triggers, views, policies, defaults, operators và other routines gọi function.

**Bước 6 — Check impact.** Xác định rows/files/network resources đã bị đọc hoặc sửa. Kiểm tra external side effects và credentials có thể đã lộ.

**Bước 7 — Repair privileges/code.** Chuyển owner về NOLOGIN role phù hợp, giới hạn search_path, sửa dynamic SQL, revoke PUBLIC và cấp lại EXECUTE theo allowlist.

**Bước 8 — Rotate exposed secrets.** Nếu function có thể đọc secrets hoặc credentials, đánh giá rotation và revoke các credentials liên quan.

**Bước 9 — Verify.** Test bằng runtime roles, kiểm tra RLS/ownership và xác nhận caller không thể truy cập ngoài phạm vi.

**Bước 10 — Record and monitor.** Lưu incident record, update inventory và theo dõi unexpected EXECUTE activity.

Không chỉ sửa function body rồi bỏ qua grants/owner/search_path. Một privileged routine có nhiều security dimensions cần được phục hồi đồng bộ.

## 25. Bài thực hành

Thực hiện trên PostgreSQL lab riêng. Không cài untrusted language, tạo C function hoặc thử privilege escalation trên production.

### Bài 1 — Liệt kê languages

Query pg_language, giải thích lanpltrusted, lanispl, owner và ACL.

### Bài 2 — SQL và PL/pgSQL

Tạo một SQL function và một PL/pgSQL function thực hiện cùng phép tính. So sánh code, planner behavior và use cases.

### Bài 3 — Language USAGE

Tạo developer role, cấp USAGE trên plpgsql và CREATE trên schema lab. Xác nhận role có thể tạo function.

### Bài 4 — Schema CREATE

Thu hồi CREATE trên schema và thử CREATE FUNCTION. Giải thích sự khác nhau giữa USAGE và CREATE.

### Bài 5 — Function EXECUTE

Tạo function, revoke EXECUTE từ PUBLIC, grant cho một role và xác nhận bằng has_function_privilege.

### Bài 6 — Default privileges

Cấu hình ALTER DEFAULT PRIVILEGES cho function owner. Tạo function mới và kiểm tra ACL.

### Bài 7 — Existing grants

Revoke EXECUTE ON ALL FUNCTIONS IN SCHEMA trong lab. Kiểm tra những callers nào mất quyền.

### Bài 8 — Function overloads

Tạo hai functions cùng tên khác argument types. Grant/revoke theo signature và xác nhận quyền riêng biệt.

### Bài 9 — SECURITY INVOKER

Tạo function đọc table. Gọi bằng role không có SELECT và quan sát permission error.

### Bài 10 — SECURITY DEFINER

Tạo dedicated NOLOGIN owner có SELECT trên table. Tạo function SECURITY DEFINER và kiểm tra caller có thể gọi mà không có direct SELECT hay không.

### Bài 11 — Least-privilege owner

Tạo owner có quyền trên một table. Thử truy cập table khác để chứng minh function owner không có broad privileges.

### Bài 12 — Search path

Tạo trusted schema và untrusted schema có function cùng tên. Thay đổi search_path và quan sát name resolution trong lab.

### Bài 13 — Temporary object shadowing

Tạo temporary table/function có tên trùng object được gọi unqualified. So sánh function không cố định search_path với function có pg_temp ở cuối.

### Bài 14 — Schema qualification

Sửa function dùng unqualified names thành schema-qualified names. Thử lại với search_path khác nhau.

### Bài 15 — Dynamic SQL injection

Tạo function ghép value vào SQL string trong lab. Thử input có quote, sau đó sửa bằng USING parameter.

### Bài 16 — Identifier quoting

Tạo function truy vấn table theo input identifier. Dùng format('%I') và allowlist; thử schema/table name có ký tự đặc biệt.

### Bài 17 — Raw SQL fragment

Thiết kế một function không nhận raw WHERE clause. Thay bằng typed parameters và predicates có sẵn.

### Bài 18 — Trusted vs untrusted

Kiểm tra package/language availability trên lab. Đọc documentation về trusted status; không cần thực thi OS commands để hoàn thành bài.

### Bài 19 — Extension inventory

Query pg_extension và pg_available_extensions. So sánh installed version với default version.

### Bài 20 — Extension dependencies

Cài extension lab an toàn, xem pg_depend membership và thử DROP EXTENSION RESTRICT trong database test.

### Bài 21 — Function language inventory

Liệt kê routines theo pg_language và xác định untrusted-language candidates.

### Bài 22 — SECURITY DEFINER audit

Query pg_proc.prosecdef, owner và proconfig. Tìm routines thiếu function-local search_path.

### Bài 23 — RLS context

Tạo table có RLS, policy theo current_user và SECURITY DEFINER function. Quan sát effective user và FORCE ROW LEVEL SECURITY.

### Bài 24 — Trigger function

Tạo trigger function ghi audit row. Thử SECURITY INVOKER/DEFINER và kiểm tra owner privileges.

### Bài 25 — Function in CHECK constraint

Tạo immutable function dùng trong CHECK constraint. Thay đổi function trong lab và tìm hiểu vì sao function semantics có thể ảnh hưởng dữ liệu đã validate.

### Bài 26 — Volatility

Tạo functions IMMUTABLE/STABLE/VOLATILE và quan sát planner behavior. Không khai báo sai volatility để ép optimization.

### Bài 27 — Parallel safety

Tạo function có side effect và tìm hiểu vì sao không được đánh dấu PARALLEL SAFE.

### Bài 28 — LEAKPROOF

Đọc documentation và catalog property. Giải thích vì sao chỉ superuser được đánh dấu và liên hệ với RLS/security barrier views.

### Bài 29 — Owner transfer

Chuyển function owner sang NOLOGIN role. Kiểm tra ACL, EXECUTE và SECURITY DEFINER behavior sau chuyển đổi.

### Bài 30 — Default privilege across owners

Tạo hai creator roles với default privileges khác nhau. Xác nhận cấu hình của một role không tự áp dụng cho role kia.

### Bài 31 — Extension installation trust

Đọc control file của một extension có sẵn trong lab. Xác định trusted flag và installation privilege requirements.

### Bài 32 — Search path ACL audit

Query schema owners và CREATE grants cho các schemas trong privileged functions' search_path. Viết report cho các schemas có untrusted writers.

### Bài 33 — Function code review

Review một SECURITY DEFINER function mẫu. Ghi owner, language, ACL, search_path, dynamic SQL, RLS behavior và input validation.

### Bài 34 — Incident containment

Mô phỏng function có EXECUTE cấp quá rộng trong lab. Thu hồi quyền, kiểm tra callers và cấp lại allowlist.

### Bài 35 — Production security runbook

Viết runbook triển khai procedural language extension và privileged function, gồm package provenance, trusted status, owner, schema ACL, language USAGE, EXECUTE, search_path, RLS, monitoring và rollback.

## 26. Tổng kết

Những điểm cốt lõi khi quản lý **ngôn ngữ thủ tục bổ sung và rủi ro quyền thực thi**:

1. PostgreSQL hỗ trợ SQL, PL/pgSQL và nhiều procedural languages bổ sung.
2. Procedural languages thường được cài/quản lý qua extensions; package availability phụ thuộc server build và environment.
3. Trusted language chỉ cung cấp language-level restrictions; nó không đảm bảo function code an toàn.
4. Untrusted languages và C functions có thể mở rộng khả năng tới filesystem, process, network hoặc native code dưới quyền OS account của PostgreSQL.
5. Superuser restriction cho việc tạo untrusted functions không ngăn non-superuser gọi function nếu EXECUTE được cấp.
6. Tạo function cần privileges trên schema và language; cài extension là một privilege boundary riêng.
7. Function/procedure EXECUTE mặc định được cấp cho PUBLIC, vì vậy cần revoke và cấu hình default privileges.
8. SECURITY INVOKER dùng quyền caller; SECURITY DEFINER dùng quyền function owner.
9. SECURITY DEFINER cần owner NOLOGIN tối thiểu quyền, interface hẹp, search_path an toàn và EXECUTE allowlist.
10. Search_path hijacking và temporary-schema shadowing có thể làm privileged function gọi nhầm object.
11. Dynamic SQL phải bind values bằng USING, quote identifiers bằng %I và validate allowlist.
12. RLS có thể bị ảnh hưởng bởi owner/BYPASSRLS context trong SECURITY DEFINER functions.
13. Functions có thể được gọi gián tiếp qua triggers, policies, defaults, views, constraints và operators.
14. Volatility, parallel safety và leakproof là execution/planner contracts, không phải cơ chế authorization.
15. Audit routine owner, language, ACL, proconfig, dependencies và extension provenance định kỳ.

Một procedural function an toàn cần được review như một API có quyền thực thi. Language xác định cách code chạy; owner và security mode xác định quyền hiệu lực; EXECUTE ACL xác định ai có thể kích hoạt; search_path và input handling xác định code sẽ resolve và thực thi những objects nào. Quản lý riêng từng lớp này giúp mở rộng PostgreSQL mà không biến stored routines thành đường tắt vượt qua privilege boundaries.

## 27. Tài liệu PostgreSQL chính thức

- [Procedural Languages](https://www.postgresql.org/docs/current/xplang.html)
- [PL/pgSQL](https://www.postgresql.org/docs/current/plpgsql.html)
- [PL/Python](https://www.postgresql.org/docs/current/plpython.html)
- [PL/Perl](https://www.postgresql.org/docs/current/plperl.html)
- [PL/Tcl](https://www.postgresql.org/docs/current/pltcl.html)
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html)
- [CREATE PROCEDURE](https://www.postgresql.org/docs/current/sql-createprocedure.html)
- [Function Security](https://www.postgresql.org/docs/current/perm-functions.html)
- [Privileges](https://www.postgresql.org/docs/current/ddl-priv.html)
- [GRANT](https://www.postgresql.org/docs/current/sql-grant.html)
- [ALTER DEFAULT PRIVILEGES](https://www.postgresql.org/docs/current/sql-alterdefaultprivileges.html)
- [Schemas and Search Path](https://www.postgresql.org/docs/current/ddl-schemas.html)
- [Writing SECURITY DEFINER Functions Safely](https://www.postgresql.org/docs/current/sql-createfunction.html)
- [CREATE EXTENSION](https://www.postgresql.org/docs/current/sql-createextension.html)
- [Extension Packaging](https://www.postgresql.org/docs/current/extend-extensions.html)
- [pg_language](https://www.postgresql.org/docs/current/catalog-pg-language.html)
- [pg_proc](https://www.postgresql.org/docs/current/catalog-pg-proc.html)
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [Function Volatility Categories](https://www.postgresql.org/docs/current/xfunc-volatility.html)
- [Parallel Safety](https://www.postgresql.org/docs/current/parallel-safety.html)
- [Dynamic SQL in PL/pgSQL](https://www.postgresql.org/docs/current/plpgsql-statements.html#PLPGSQL-STATEMENTS-EXECUTING-DYN)

Các liên kết current trỏ tới tài liệu PostgreSQL hiện hành. Procedural language names, trusted flags, extension availability, privilege behavior và catalog fields có thể thay đổi theo PostgreSQL major version, OS packages và managed-service policy. Trước khi cài language hoặc cấp quyền production, kiểm tra server version, pg_language, pg_extension, extension control files và privilege behavior trên đúng environment.
