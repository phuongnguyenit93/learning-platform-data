# SECURITY INVOKER, SECURITY DEFINER và search_path an toàn trong PostgreSQL

## 1. Vì sao một hàm nhỏ có thể trở thành ranh giới bảo mật của database?

Hãy tưởng tượng ứng dụng có bảng `customers` chứa hạn mức tín dụng, email và dữ liệu nội bộ. Người dùng ứng dụng không được quyền `SELECT` trực tiếp trên bảng này, nhưng được phép gọi một hàm để lấy **hạn mức được phê duyệt** của đúng khách hàng trong phạm vi mình được ủy quyền.

PostgreSQL hỗ trợ hai cơ chế chính để xác định **quyền của ai** được dùng khi thực thi hàm hoặc thủ tục:

- `SECURITY INVOKER`: thực thi với quyền của **người đang gọi**; đây là mặc định.
- `SECURITY DEFINER`: thực thi với quyền của **chủ sở hữu hàm/thủ tục** trong phạm vi thực thi đối tượng đó.

`SECURITY DEFINER` hữu ích để cấp quyền thông qua API database có kiểm soát. Tuy nhiên, một hàm definer chứa `SELECT ... FROM customers` không định danh schema, hoặc gọi một function khác bằng tên không định danh, có thể bị **thay đổi ý nghĩa bởi `search_path`**. Nếu đối tượng không tin cậy được ưu tiên khi tra tên, mã chạy bằng quyền nâng cao có thể truy cập sai bảng/hàm/toán tử.

```text
                      Ứng dụng / vai trò gọi
                               |
                         GRANT EXECUTE
                               |
                 +-------------+-------------+
                 |                           |
           SECURITY INVOKER           SECURITY DEFINER
                 |                           |
         Quyền người gọi             Quyền chủ sở hữu hàm
                 |                           |
          SELECT trực tiếp?        Chỉ thao tác cho phép
                 |                           |
                 +-------------+-------------+
                               |
                      Phân giải tên object
                         qua search_path
                               |
          +--------------------+-------------------+
          |                                        |
    Path không an toàn                     Path an toàn
  schema attacker / pg_temp          pg_catalog, trusted, pg_temp
          |                                        |
  Có thể shadow object                       Object lookup được kiểm soát
          |                                        |
  Nguy cơ lộ/sai dữ liệu                   Least-privilege routine API
```

**Bài toán cốt lõi:** cấp đủ quyền để ứng dụng làm được việc cần làm, **nhưng không cho người gọi chọn đối tượng nào sẽ được truy cập bằng quyền của hàm**.

> **Quy tắc quan trọng nhất:** `SECURITY DEFINER` là một ranh giới đặc quyền. Hãy dùng chủ sở hữu ít quyền nhất, định danh đối tượng tin cậy, đặt `SET search_path` an toàn ngay trong định nghĩa hàm, thu hồi `EXECUTE` mặc định khỏi `PUBLIC` và kiểm tra quyền/logic nghiệp vụ ở mọi đầu vào.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt người dùng đăng nhập, role đang có hiệu lực, chủ sở hữu hàm và quyền của bảng.
2. Hiểu `CURRENT_USER`, `SESSION_USER`, `SET ROLE`, kế thừa quyền và membership ở mức cần thiết.
3. Giải thích vì sao mặc định `SECURITY INVOKER` cần quyền trên các objects mà hàm truy cập.
4. Giải thích cách `SECURITY DEFINER` cho phép thực hiện thao tác có kiểm soát mà caller không được quyền trực tiếp.
5. Phân biệt quyền `USAGE` trên schema, `EXECUTE` trên routine và `SELECT/UPDATE` trên bảng.
6. Đọc và đặt `search_path`; phân biệt `current_schema()`, `current_schemas(true)`.
7. Hiểu vì sao `pg_catalog` và `pg_temp` đặc biệt quan trọng trong hàm definer.
8. Nhận diện schema shadowing, temporary-table shadowing và hijacking tên hàm/toán tử.
9. Viết `CREATE FUNCTION ... SECURITY DEFINER SET search_path = ...` an toàn.
10. Viết các truy vấn bên trong hàm với tên bảng/schema được định danh rõ.
11. Thu hồi `EXECUTE` khỏi `PUBLIC` mà không để cửa sổ cấp quyền ngẫu nhiên.
12. Sử dụng owner role chuyên biệt, `NOLOGIN` và cấp quyền tối thiểu.
13. Phân tích tác động Row-Level Security (RLS) khi chạy dưới definer owner.
14. Thiết kế dynamic SQL với `format('%I', ...)` và `EXECUTE ... USING`, nhưng vẫn kiểm tra authorization.
15. Phân biệt function và procedure, đặc biệt hạn chế transaction control trong `SECURITY DEFINER` procedures.
16. Viết kiểm thử permissions, search-path shadowing, tenant isolation và negative cases.
17. Kiểm kê các routines có `prosecdef`, `proconfig` và các đặc quyền thực tế bằng system catalogs.
18. Tổ chức migration, logging và vận hành routine đặc quyền với rủi ro thấp.

## 3. Mô hình quyền: ai đang gọi, ai sở hữu, ai được cấp EXECUTE?

Các thành phần tham gia:

| Thành phần | Ví dụ | Tác dụng |
| --- | --- | --- |
| Login role | `app_login` | Role mở kết nối PostgreSQL |
| Effective role | Sau `SET ROLE app_reader` | Role đang được dùng cho phần lớn privilege checks |
| Routine owner | `sec348_owner` | Chủ sở hữu hàm/procedure |
| Routine caller | `sec348_reader` | Bên yêu cầu thực thi routine |
| Data owner | `sec348_owner` hoặc role khác | Quyền trên bảng mà routine truy cập |
| Schema owner | `sec348_owner` | Có quyền quản lý objects trong schema |
| `PUBLIC` | Nhóm pseudo-role đặc biệt | Đại diện mọi role trong các GRANT phù hợp |
| `pg_temp` | Temporary schema của session | Có thể tham gia name resolution |

Một kết nối có thể sử dụng `SET ROLE` để thay đổi effective role, nhưng điều đó không biến mọi thuộc tính của session thành một người dùng đăng nhập mới.

### 3.1. `CURRENT_USER`

`CURRENT_USER` trả role đang có hiệu lực cho quyền và resolution tại điểm biểu thức được đánh giá. Bên trong hàm `SECURITY DEFINER`, nó thể hiện **owner của hàm** trong khoảng thời gian thực thi dưới definer context.

### 3.2. `SESSION_USER`

`SESSION_USER` thường là role lúc thiết lập session (hoặc có thể được thay đổi bằng cơ chế quản trị được phép), **không tự đổi khi một client chạy `SET ROLE`**.

### 3.3. `CURRENT_ROLE`

Trong PostgreSQL, `CURRENT_ROLE` thường tương ứng với `CURRENT_USER`. Không nên dùng nó như “user gốc” khi gọi vào definer routine.

### 3.4. `SET ROLE` và kiểm thử

```sql
SELECT
    current_user,
    session_user,
    current_role;

-- Trong session đủ quyền chuyển role:
SET ROLE some_app_role;

SELECT current_user, session_user, current_role;

RESET ROLE;
```

Sau `SET ROLE`, `current_user` đổi thành role đã chọn, nhưng `session_user` thường vẫn là login role ban đầu.

**Hệ quả quan trọng:** kiểm thử authorization dựa trên `SESSION_USER` không thể chỉ mô phỏng bằng `SET ROLE` rồi giả định session_user đã đổi. Muốn kiểm thử chính xác mô hình “mỗi người dùng một DB login”, cần đăng nhập qua connection tương ứng.

## 4. SECURITY INVOKER là mặc định

Một SQL function khai báo:

```sql
CREATE FUNCTION sample_read()
RETURNS integer
LANGUAGE sql
AS $body$
    SELECT 1
$body$;
```

mặc định hoạt động như:

```sql
CREATE FUNCTION sample_read()
RETURNS integer
LANGUAGE sql
SECURITY INVOKER
AS $body$
    SELECT 1
$body$;
```

Nếu hàm invoker truy cập một bảng, caller thường cần những quyền phù hợp trên bảng đó, trừ khi cơ chế quyền/view/routine khác trong call chain tạo context được phép.

### 4.1. Khi nào nên dùng INVOKER?

- Logic biến đổi chuỗi, số và thời gian không cần đặc quyền thêm.
- Các hàm tính toán/validation trên dữ liệu mà caller đã được phép dùng.
- Truy vấn nên tuân thủ quyền trực tiếp và RLS của caller.
- Khi không có lý do nghiệp vụ để routine nâng quyền.

### 4.2. Những quyền vẫn cần để gọi hàm

`EXECUTE` trên routine không có nghĩa caller đã có:

- `USAGE` trên schema chứa những objects được tham chiếu từ ứng dụng.
- `SELECT` trên bảng bí mật.
- Quyền tự ý `CREATE` function/schema.
- Quyền thay đổi role hoặc bypass RLS.

Phải phân biệt **quyền gọi hàm** và **quyền hoạt động bên trong hàm**.

### 4.3. INVOKER không làm một truy vấn tự an toàn

Một invoker function dùng dynamic SQL ghép input sai vẫn có thể bị SQL injection theo quyền caller, làm hỏng hoặc đọc những objects caller có quyền. Bảo mật vẫn cần parameterization và kiểm soát đầu vào.

## 5. SECURITY DEFINER: dùng quyền chủ sở hữu để thực thi có kiểm soát

Ví dụ mục đích:

- Caller không có `SELECT` trực tiếp trên bảng tài chính.
- Caller chỉ được gọi một API trả về trường đã chọn.
- API chạy dưới owner role chỉ có quyền đọc đúng bảng cần thiết.
- Hàm áp dụng điều kiện nghiệp vụ không cho caller tự chọn tenant khác.

Với `SECURITY DEFINER`:

```sql
CREATE FUNCTION some_schema.some_api(...)
RETURNS ...
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, some_schema, pg_temp
AS $body$
BEGIN
    -- Kiểm tra input và điều kiện cấp quyền.
    -- Chỉ thao tác trên objects đã được phép.
END
$body$;
```

### 5.1. Owner không phải superuser

Một sai lầm là tạo definer function bằng superuser/role có `BYPASSRLS` hay quyền rộng chỉ vì “cho tiện”.

Nếu logic bị lạm dụng, khả năng thiệt hại của owner sẽ quyết định phạm vi ảnh hưởng.

**Nên dùng một NOLOGIN owner role** chỉ có đúng những quyền cần cho hàm, đặc biệt khi chỉ cần đọc một bảng hoặc cập nhật một tập hàng được kiểm soát.

### 5.2. SECURITY DEFINER không tự biết ai có quyền xem khách hàng nào

Nếu routine viết:

```sql
SELECT credit_limit
FROM private_customers
WHERE customer_id = p_id;
```

mà caller được quyền truyền bất kỳ `p_id`, nó có thể trở thành API đọc thông tin của người khác.

Nâng quyền thực thi **không thay thế kiểm tra business authorization**. Điều kiện dữ liệu theo tenant/user và mapping quyền phải được kiểm chứng từ nguồn tin cậy.

### 5.3. Đặc quyền trong chuỗi lời gọi

Một invoker helper được gọi từ definer function có thể thực thi trong effective-role context đang được sử dụng. Một helper khác cũng là definer có thể chuyển sang owner của chính nó.

Không suy rằng quyền chỉ phụ thuộc một cặp caller/owner ở điểm vào; hãy kiểm tra toàn bộ call chain và các routines có quyền cao.

## 6. Lab nhiều role: chuẩn bị môi trường kiểm thử

Các thao tác tạo role/schema cần role quản trị có quyền phù hợp. **Chỉ chạy trong database thử nghiệm**. Không copy lệnh `GRANT`/`REVOKE` sang production khi chưa có kế hoạch.

Sử dụng ba vai trò:

- `sec348_owner`: NOLOGIN, sở hữu bảng và functions đặc quyền.
- `sec348_reader`: NOLOGIN, đại diện caller chỉ được cấp quyền gọi API.
- `sec348_other`: NOLOGIN, đại diện role không được phép gọi API bí mật.

Trong môi trường lab, DBA hoặc role có quyền cần thiết tạo:

```sql
CREATE ROLE sec348_owner NOLOGIN;
CREATE ROLE sec348_reader NOLOGIN;
CREATE ROLE sec348_other NOLOGIN;

CREATE SCHEMA sec348 AUTHORIZATION sec348_owner;

REVOKE ALL ON SCHEMA sec348 FROM PUBLIC;
GRANT USAGE ON SCHEMA sec348 TO sec348_reader;
GRANT USAGE ON SCHEMA sec348 TO sec348_other;
```

### 6.1. Tại sao reader được USAGE nhưng không được CREATE?

`USAGE` cho phép tra tên objects trong schema ở những điều kiện phù hợp. Nó **không trao quyền tạo đối tượng**.

Không dùng:

```sql
GRANT CREATE ON SCHEMA sec348 TO sec348_reader;
```

khi schema chứa các đối tượng mà definer function sẽ tra tên.

### 6.2. Tạo bảng bằng owner

Trong một phiên quản trị đủ quyền `SET ROLE sec348_owner`:

```sql
SET ROLE sec348_owner;

CREATE TABLE sec348.customers (
    tenant_id integer NOT NULL,
    customer_id integer NOT NULL,
    full_name text NOT NULL,
    credit_limit numeric(12,2) NOT NULL,
    PRIMARY KEY (tenant_id, customer_id)
);

INSERT INTO sec348.customers
    (tenant_id, customer_id, full_name, credit_limit)
VALUES
    (10, 1, 'Tenant 10 - Customer 1', 1000.00),
    (10, 2, 'Tenant 10 - Customer 2', 2500.00),
    (20, 1, 'Tenant 20 - Customer 1', 9000.00);

RESET ROLE;
```

Nếu login quản trị không phải superuser, nó phải được phép chuyển sang `sec348_owner` theo membership/role-administration rules của phiên bản PostgreSQL.

### 6.3. Không cấp quyền đọc bảng cho reader

Trong lab, bảng do `sec348_owner` tạo; `sec348_reader` không tự có quyền `SELECT`.

Có thể kiểm tra:

```sql
SELECT
    has_table_privilege(
        'sec348_reader',
        'sec348.customers',
        'SELECT'
    ) AS reader_can_select,
    has_schema_privilege(
        'sec348_reader',
        'sec348',
        'USAGE'
    ) AS reader_schema_usage;
```

Kỳ vọng trong lab không có GRANT khác:

- `reader_can_select = false`.
- `reader_schema_usage = true`.

Nếu database có role memberships hoặc quyền đã được thêm ở ngoài lab, kết quả có thể khác; cần kiểm tra môi trường thực tế.

## 7. Demo SECURITY INVOKER: caller không thể đọc bảng bí mật

Tạo routine invoker bằng owner:

```sql
SET ROLE sec348_owner;

BEGIN;

CREATE FUNCTION sec348.invoker_limit(
    p_customer_id integer
)
RETURNS numeric
LANGUAGE sql
SECURITY INVOKER
SET search_path = pg_catalog, sec348, pg_temp
AS $fn$
    SELECT c.credit_limit
    FROM sec348.customers AS c
    WHERE c.tenant_id = 10
      AND c.customer_id = p_customer_id
$fn$;

REVOKE ALL ON FUNCTION sec348.invoker_limit(integer)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION sec348.invoker_limit(integer)
TO sec348_reader;

COMMIT;

RESET ROLE;
```

### 7.1. Thử caller

Trong một phiên quản trị có thể `SET ROLE`:

```sql
SET ROLE sec348_reader;

SELECT current_user, session_user;

SELECT sec348.invoker_limit(1);

RESET ROLE;
```

Vì `sec348_reader` có `USAGE` trên schema và `EXECUTE` trên function nhưng **không có SELECT trên `sec348.customers`**, lời gọi có thể nhận lỗi `permission denied for table customers`.

Đây là **hành vi mong đợi** để minh họa `SECURITY INVOKER`.

Nếu lỗi xảy ra trong một transaction tường minh, cần `ROLLBACK` trước khi chạy các lệnh khác trong transaction đó.

### 7.2. Điều gì sẽ khác nếu GRANT SELECT?

```sql
GRANT SELECT ON sec348.customers TO sec348_reader;
```

Khi reader có SELECT trực tiếp, invoker function có thể truy cập bảng theo quyền caller. Nhưng đây **không phải điều ta muốn** trong lab minh họa API hạn chế quyền, nên **không chạy GRANT này** nếu muốn giữ mô hình owner-only table.

### 7.3. Vì sao mặc định INVOKER thường là lựa chọn tốt?

Nếu caller được phép đọc bảng tương ứng theo chính sách và RLS, invoker function không cần gia tăng đặc quyền. Chỉ khi có mục đích nghiệp vụ rõ mới xem xét definer.

## 8. Demo SECURITY DEFINER: caller chỉ gọi API giới hạn

Tạo hàm definer trả **một** hạn mức của tenant 10:

```sql
SET ROLE sec348_owner;

BEGIN;

CREATE FUNCTION sec348.definer_limit(
    p_customer_id integer
)
RETURNS numeric
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, sec348, pg_temp
AS $fn$
    SELECT c.credit_limit
    FROM sec348.customers AS c
    WHERE c.tenant_id = 10
      AND c.customer_id = p_customer_id
$fn$;

REVOKE ALL ON FUNCTION sec348.definer_limit(integer)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION sec348.definer_limit(integer)
TO sec348_reader;

COMMIT;

RESET ROLE;
```

### 8.1. Kiểm thử bằng reader

```sql
SET ROLE sec348_reader;

SELECT sec348.definer_limit(1) AS allowed_limit;

RESET ROLE;
```

Trong schema/dữ liệu lab và quyền đã thiết lập, kết quả kỳ vọng là `1000.00`.

Reader **không được SELECT bảng**, nhưng có `EXECUTE` trên một API do owner định nghĩa.

### 8.2. Vì sao API này chưa phải mô hình multi-tenant tổng quát?

Hàm hardcode:

```sql
WHERE c.tenant_id = 10
```

để minh họa quyền definer dễ kiểm chứng. Nếu muốn phục vụ nhiều tenant, phải có cách **đáng tin cậy** xác định tenant mà caller thực sự được phép truy cập.

Không sửa thành:

```sql
WHERE c.tenant_id = p_tenant_id
```

rồi cho mọi caller truyền `p_tenant_id` tùy ý mà không kiểm tra quyền. Khi ấy, chức năng trở thành **bộ đọc hạn mức của mọi tenant**.

### 8.3. Thứ mà EXECUTE trao quyền

Reader được quyền thực hiện **logic đúng như mã hàm**, không được trở thành owner toàn session sau khi hàm kết thúc.

Chủ sở hữu và privilege context được PostgreSQL xử lý trong khoảng thực thi routine; lời gọi kết thúc thì caller trở lại context bên ngoài theo semantics tương ứng.

### 8.4. Quyền INVOKER/DEFINER không phải sự khác nhau về số rows

Hai hàm trả cùng một giá trị khi caller đủ quyền. Khác biệt chính là **identity được dùng để kiểm tra quyền** khi đọc bảng.

## 9. `CURRENT_USER` bên trong INVOKER và DEFINER

Tạo hai hàm đo identity:

```sql
SET ROLE sec348_owner;

BEGIN;

CREATE FUNCTION sec348.who_invokes()
RETURNS name
LANGUAGE sql
SECURITY INVOKER
AS $fn$
    SELECT current_user
$fn$;

CREATE FUNCTION sec348.who_defines()
RETURNS name
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, sec348, pg_temp
AS $fn$
    SELECT current_user
$fn$;

REVOKE ALL ON FUNCTION sec348.who_invokes()
FROM PUBLIC;

REVOKE ALL ON FUNCTION sec348.who_defines()
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION sec348.who_invokes()
TO sec348_reader;

GRANT EXECUTE ON FUNCTION sec348.who_defines()
TO sec348_reader;

COMMIT;

RESET ROLE;
```

Kiểm thử:

```sql
SET ROLE sec348_reader;

SELECT
    current_user AS caller_now,
    session_user AS session_login,
    sec348.who_invokes() AS invoker_sees,
    sec348.who_defines() AS definer_sees;

RESET ROLE;
```

Kỳ vọng trong lab:

| Biểu thức | Vai trò điển hình |
| --- | --- |
| `current_user` bên ngoài | `sec348_reader` |
| `session_user` bên ngoài | Login thực tế của kết nối, không nhất thiết reader |
| `who_invokes()` | `sec348_reader` |
| `who_defines()` | `sec348_owner` |

### 9.1. Không dùng CURRENT_USER trong definer để nhận diện caller

Ví dụ nguy hiểm:

```sql
-- Bên trong SECURITY DEFINER:
SELECT current_user;
```

Kết quả là owner, không phải caller bên ngoài. Nếu cần xác định identity của người gọi, phải thiết kế một nguồn identity **không thể bị caller giả mạo** và hiểu ranh giới trust của session/proxy/pool.

### 9.2. SESSION_USER không tự giải quyết authentication của app

Nếu mọi người dùng web chia sẻ một database login, `SESSION_USER` luôn là login chung, không phân biệt hàng nghìn end users.

Một hàm definer không thể dựa riêng vào `SESSION_USER` để nhận diện người dùng web nếu kiến trúc pool dùng shared role. Phải có authorization context được bảo vệ ở tầng ứng dụng/database bằng cơ chế phù hợp.

## 10. Ba tầng privilege cần xét đồng thời

Gọi một function tên `sec348.definer_limit(1)` thường liên quan:

1. Quyền kết nối vào database.
2. Quyền `USAGE` trên schema `sec348` và `EXECUTE` trên function.
3. Quyền bên trong hàm để truy cập `sec348.customers`.

### 10.1. Kiểm tra quyền schema và routine

```sql
SELECT
    has_schema_privilege(
        'sec348_reader',
        'sec348',
        'USAGE'
    ) AS schema_usage,
    has_function_privilege(
        'sec348_reader',
        'sec348.definer_limit(integer)',
        'EXECUTE'
    ) AS can_execute,
    has_table_privilege(
        'sec348_reader',
        'sec348.customers',
        'SELECT'
    ) AS can_select_table;
```

Kỳ vọng:

```text
schema_usage    = true
can_execute     = true
can_select_table= false
```

### 10.2. Vì sao kiểm tra EXECUTE không đủ?

Một role có thể có EXECUTE nhưng không USAGE schema. Hoặc có USAGE/EXECUTE nhưng routine là invoker và không đủ quyền đọc dữ liệu.

Đừng kết luận “function hỏng” nếu chưa xác định thiếu đặc quyền ở tầng nào.

### 10.3. Schema CREATE là đặc quyền nguy hiểm với definer

Nếu caller có `CREATE` trên một schema được tìm kiếm **trước những trusted objects**, caller có thể tạo functions, operators hoặc tables có tên gây nhầm lẫn.

Ngay khi caller không có SELECT bảng thật, một definer function tin vào tên không định danh có thể bị chi phối bởi object do caller tạo.

## 11. `search_path` là gì?

`search_path` là danh sách schemas PostgreSQL dùng để tra những object names không được định danh schema đầy đủ trong những tình huống phù hợp.

Kiểm tra:

```sql
SHOW search_path;

SELECT
    current_schema() AS first_usable_schema,
    current_schemas(true) AS effective_schema_list;
```

Giả sử:

```sql
SET search_path = app, public;
```

thì một truy vấn:

```sql
SELECT *
FROM customers;
```

có thể tham chiếu `app.customers` nếu object phù hợp tồn tại và visible theo quy tắc resolution.

Trong khi:

```sql
SELECT *
FROM sec348.customers;
```

định danh bảng rõ ràng trong `sec348`, không tùy thuộc việc `sec348` có đứng đầu path hay không.

### 11.1. Search path không chỉ áp dụng cho tables

Nó liên quan đến tên các đối tượng khác như:

- Functions và procedures.
- Operators.
- Types.
- Sequences.
- Một số objects khác theo loại và cú pháp SQL.

Chính vì vậy, khóa tên bảng thôi chưa đủ nếu routine còn gọi hàm hoặc toán tử không tin cậy.

### 11.2. Search path là quy tắc resolution, không phải GRANT

Chỉ vì một schema nằm trong path, caller **không tự có quyền SELECT/EXECUTE** các objects bên trong nó.

Ngược lại, dù một schema không nằm trong path, caller có thể tham chiếu object bằng tên fully qualified nếu có đủ quyền.

### 11.3. Path được session thay đổi

```sql
SET search_path = sec348, public;

SHOW search_path;

RESET search_path;
```

Một connection pool có thể tái sử dụng session sau request khác. Nếu session state không được đặt/reset đúng, search_path từ request trước có thể ảnh hưởng query sau.

Đối với definer functions, vì vậy cần **SET search_path ngay trong định nghĩa**.

## 12. `pg_catalog`: ưu tiên các built-in objects

`pg_catalog` chứa nhiều built-in functions, operators, types và system catalogs của PostgreSQL.

Nếu `pg_catalog` **không được nêu rõ** trong `search_path`, PostgreSQL thường tìm nó trước các schemas liệt kê khi phân giải các loại objects phù hợp.

Nếu **nêu rõ**, vị trí của `pg_catalog` trong path có thể thay đổi thứ tự ưu tiên.

### 12.1. Cấu hình nguy hiểm

```sql
SET search_path = untrusted_schema, pg_catalog;
```

Ở đây một schema cho người dùng tạo objects có thể được xét **trước** pg_catalog trong những lookup tương ứng, tạo rủi ro shadowing.

### 12.2. Cấu hình dễ kiểm soát hơn

```sql
SET search_path = pg_catalog, sec348, pg_temp;
```

Thứ tự thể hiện ý định:

1. Built-in objects của PostgreSQL.
2. Trusted application schema.
3. Temporary namespace của session, đặt cuối.

Hàm definer còn nên **fully qualify** những bảng và routines nhạy cảm, thay vì chỉ dựa trên path.

### 12.3. Tên được định danh hoàn toàn

```sql
SELECT pg_catalog.current_user;
```

Đây không phải mọi built-in đều cần viết dạng schema-qualified. Nhưng với security-critical function, việc chỉ rõ định danh cho routines quan trọng và giữ `pg_catalog` trước untrusted schemas làm giảm rủi ro thay đổi name resolution.

### 12.4. Toán tử cũng có thể bị shadow

Một toán tử trông như ký hiệu thường ngày cũng là một object được lookup. Khi cần định danh toán tử:

```sql
SELECT 1 OPERATOR(pg_catalog.+) 2;
```

Trong code bình thường, ta không cần định danh từng toán tử nếu `search_path` đã khóa vào các schemas tin cậy. Mẫu `OPERATOR(schema.operator)` hữu ích để hiểu mặt tấn công qua custom operators.

## 13. `pg_temp`: điểm đặc biệt dễ bị bỏ sót

PostgreSQL có temporary schema của session (ví dụ namespace nội bộ `pg_temp_NNN`).

Một điểm quan trọng:

> Nếu temporary schema không được ghi rõ vị trí trong `search_path`, nó có thể được tìm kiếm **trước** các schemas khác khi phân giải **relation names và type names**.

Điều đó có nghĩa setting:

```sql
SET search_path = sec348;
```

**chưa đủ** để khẳng định các unqualified table names bên trong definer function sẽ luôn nhận `sec348.table`.

### 13.1. Cách đặt pg_temp

```sql
SET search_path = pg_catalog, sec348, pg_temp;
```

Khi `pg_temp` nằm ở cuối, một bảng cùng tên trong `sec348` có thể được xét trước temporary table trong path.

### 13.2. `pg_temp` không được tra như functions/operators thông thường

Temporary schema được sử dụng cho **relation và type names**, không được tìm trong cùng cơ chế dành cho unqualified function hoặc operator names.

Vì vậy cần phân biệt:

- Temporary-table shadowing: nguy cơ chính qua relations/types.
- Function/operator hijacking: thường qua **schema khác do attacker có CREATE** trong search_path.

### 13.3. Kiểm tra effective path

```sql
SHOW search_path;

SELECT current_schemas(true);
```

`SHOW` trả giá trị setting, còn `current_schemas(true)` phản ánh danh sách schemas được dùng trong resolution với implicit schemas theo cách PostgreSQL hỗ trợ.

### 13.4. Temporary table thuộc session

Temporary table không phải bảng công khai toàn database. Một backend khác không thấy table đó theo cách thông thường.

Nhưng chính **session đang gọi definer function** có thể tạo temporary object (nếu role có TEMP privilege), rồi gọi function trong cùng connection. Đó là lý do rủi ro shadowing vẫn thực tế.

## 14. Rủi ro đặt pg_temp không đúng vị trí

Xem function sau (mẫu **không an toàn**, chỉ để minh họa):

```sql
CREATE FUNCTION sec348.unsafe_limit(
    p_customer_id integer
)
RETURNS numeric
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = sec348
AS $fn$
DECLARE
    v_limit numeric;
BEGIN
    SELECT credit_limit
      INTO v_limit
    FROM customers
    WHERE tenant_id = 10
      AND customer_id = p_customer_id;

    RETURN v_limit;
END
$fn$;
```

Hai vấn đề:

1. `FROM customers` **không định danh schema**.
2. `SET search_path = sec348` **không ghi rõ pg_temp ở cuối**.

### 14.1. Tình huống đáng lo

Nếu caller có quyền tạo temporary tables trong session, caller có thể tạo một bảng tên `customers` trước khi gọi function. Trong các tình huống lookup/plan/cache/privilege phù hợp, unqualified relation name có thể giải quyết về temporary table, không phải bảng owner mong muốn.

Hệ quả có thể là:

- Function đọc dữ liệu khác với dữ liệu dự kiến.
- Function chạy sai logic/cho kết quả giả.
- Function lỗi quyền hoặc kiểu dữ liệu.
- Một chương trình nhiều bước bị điều khiển bằng nguồn dữ liệu attacker-controlled.

**Không tuyên bố mọi lần tạo temp table đều khiến attacker đọc trộm dữ liệu:** kết quả còn phụ thuộc quyền trên temporary table, thời điểm plan được lập/cache và mã function. Nhưng để một definer routine tra nhầm object là một lỗ hổng thiết kế.

### 14.2. Ví dụ tạo temporary object trong lab

Trong một session có TEMP privilege:

```sql
CREATE TEMP TABLE customers (
    tenant_id integer,
    customer_id integer,
    credit_limit numeric(12,2)
);

INSERT INTO customers
    (tenant_id, customer_id, credit_limit)
VALUES (10, 1, 999999.00);
```

**Chỉ là ví dụ minh họa shadowing:** không tự chạy `unsafe_limit` trên production. Một hàm definer truy cập unqualified `customers` mà thiếu `pg_temp` ở cuối là mô hình nguy hiểm.

### 14.3. Biện pháp phòng thủ

- `SET search_path = pg_catalog, sec348, pg_temp` trong function definition.
- Định danh trực tiếp `sec348.customers` cho bảng nhạy cảm.
- Không đưa schemas do người không tin cậy có `CREATE` vào path.
- Dùng least-privilege owner role.
- Thu hồi quyền EXECUTE khỏi PUBLIC.
- Kiểm thử tình huống attacker có temp table cùng tên.

### 14.4. Không chỉ sửa search_path của caller

```sql
SET search_path = sec348;
```

ở ứng dụng là setting session, có thể bị thay đổi/rò qua connection pool. Definer function cần **tự đặt môi trường resolution** của chính nó.

## 15. Viết function an toàn: SET search_path ở cấp routine

Định nghĩa kiểu an toàn:

```sql
CREATE FUNCTION sec348.safe_example(
    p_customer_id integer
)
RETURNS numeric
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, sec348, pg_temp
AS $fn$
    SELECT c.credit_limit
    FROM sec348.customers AS c
    WHERE c.tenant_id = 10
      AND c.customer_id = p_customer_id
$fn$;
```

Mẫu này thể hiện hai lớp bảo vệ:

1. **Định danh bảng:** `sec348.customers`.
2. **Search path khóa tại routine:** `pg_catalog, sec348, pg_temp`.

### 15.1. Vì sao dùng cả hai?

Fully qualified relation names giúp tránh nhầm bảng.

Nhưng mã SQL/PL/pgSQL có thể còn:

- Các function calls không fully qualified.
- Types hoặc operators.
- Các tên được tạo trong dynamic SQL.
- Helper routines hoặc object references được thêm trong các lần sửa sau.

Một `SET search_path` an toàn tạo mặc định phòng thủ tốt hơn cho toàn bộ function body.

### 15.2. Chỉ đưa schema tin cậy vào path

`SET search_path = pg_catalog, sec348, pg_temp` chỉ an toàn khi **sec348 thật sự là schema không cho attacker tạo/sửa objects**.

Nếu `sec348_reader` có quyền CREATE trong `sec348`, bản thân `sec348` không còn là trusted schema.

### 15.3. Có thể chỉ dùng `pg_catalog, pg_temp`

Nếu function định danh **mọi application object** đầy đủ, cấu hình chặt hơn là:

```sql
SET search_path = pg_catalog, pg_temp
```

Trong trường hợp đó, tất cả bảng, types/functions không built-in cần tên schema tường minh. Chọn path ngắn nhất có thể vận hành nhất quán.

### 15.4. Không đưa public vào path chỉ vì “quen dùng”

Nếu `public` có thể bị người không tin cậy tạo objects, nó không phù hợp làm schema được tìm kiếm trong definer function.

Một số PostgreSQL versions/database mới không cấp `CREATE` trên public cho PUBLIC mặc định, nhưng database cũ/đã upgrade/đã GRANT khác có thể vẫn cấp. **Kiểm tra quyền thực tế**, không dựa vào giả định từ phiên bản.

## 16. Tại sao schema qualification quan trọng hơn tên biến đẹp?

So sánh:

```sql
-- Khó kiểm soát nếu search_path thay đổi:
SELECT credit_limit
FROM customers
WHERE customer_id = p_customer_id;
```

và:

```sql
-- Rõ object đích:
SELECT c.credit_limit
FROM sec348.customers AS c
WHERE c.customer_id = p_customer_id;
```

### 16.1. Aliases không thay thế schema qualification

`customers AS c` chỉ tạo alias nội bộ; nếu `customers` đã được resolve sai object, alias `c` không cứu được.

### 16.2. Định danh không tự giải quyết row authorization

Ngay khi bảng là `sec348.customers` đúng, nếu WHERE chỉ có customer_id mà thiếu tenant/user checks, routine có thể đọc dữ liệu ngoài phạm vi.

Hai lớp khác nhau:

- **Object resolution:** chọn đúng bảng/hàm.
- **Row authorization:** chọn đúng những hàng mà caller được phép xem.

### 16.3. Không để table name do caller quyết định

Một definer function nhận `p_table_name text` rồi truy cập một bảng theo tên đó là API quyền rất rộng nếu không có allowlist rõ ràng.

Ngay cả khi tên được quote đúng và không có SQL injection, caller vẫn có thể chọn một **bảng hợp lệ nhưng không được phép**.

## 17. Schema do attacker có CREATE và function/operator hijacking

Giả sử có schema `untrusted`:

```sql
-- Chỉ là minh họa cấu hình không an toàn:
SET search_path = untrusted, pg_catalog, sec348;
```

Nếu untrusted user có `CREATE` trên schema đó, họ có thể tạo objects có tên/các signatures trùng hoặc cạnh tranh với những calls trong definer function.

### 17.1. Function name collision

Một lời gọi:

```sql
SELECT helper_process(value);
```

không chỉ là chuỗi tên; PostgreSQL còn xem:

- Schema search order.
- Argument types.
- Overloads/default arguments.
- Function visibility/privileges.
- Cơ chế resolution của phiên bản.

Một schema untrusted đứng trước có thể làm thay đổi function được chọn hoặc khiến câu SQL trở nên ambiguous/error.

### 17.2. Operators cũng là objects

Ví dụ:

```sql
a + b
```

dùng operator lookup phù hợp với types. PostgreSQL cho phép custom operators; khi untrusted schema nằm ở vị trí ưu tiên, operator resolution cũng cần được xem là một mặt tấn công.

### 17.3. `pg_catalog` nên được ưu tiên rõ

```sql
SET search_path = pg_catalog, sec348, pg_temp;
```

Điều này giảm rủi ro built-in hijacking và không để untrusted schemas trong path.

### 17.4. Đừng dựa vào một tên function “hiếm” để an toàn

Attacker không nhất thiết phải đoán chính xác tên mọi helper nếu code hoặc schema được đọc từ catalog/logs. Quy tắc bảo mật phải dựa vào ownership/CREATE privileges và object qualification, không dựa trên secret tên hàm.

### 17.5. PL/pgSQL plan cache là một yếu tố, không phải biện pháp bảo vệ

PL/pgSQL có thể cache plans cho SQL statements. Những thay đổi object/schema/search_path có thể ảnh hưởng thời điểm parse/replan tùy cơ chế invalidation.

Không suy rằng một câu SQL đã được plan một lần sẽ mãi không thể bị name shadowing. Hãy xử lý tận gốc bằng trusted path và explicit object references.

## 18. PUBLIC EXECUTE: mặc định dễ gây bất ngờ

Trong PostgreSQL, **một function mới tạo thường được cấp quyền EXECUTE cho PUBLIC theo default privileges**, nếu chưa có thay đổi defaults phù hợp.

Điều này rất quan trọng với `SECURITY DEFINER`, vì:

- Routine có thể được tạo bởi owner có nhiều quyền.
- Nếu caller có schema USAGE và EXECUTE, routine có thể gọi được dù developer chưa viết GRANT riêng.
- Trước khi REVOKE có thể tồn tại cửa sổ quyền nếu DDL thực hiện ở những transactions khác nhau.

### 18.1. Tạo, REVOKE, GRANT trong cùng transaction

Mẫu nên dùng:

```sql
BEGIN;

CREATE FUNCTION sec348.example_api(
    p_id integer
)
RETURNS integer
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, sec348, pg_temp
AS $fn$
    SELECT p_id
$fn$;

REVOKE ALL ON FUNCTION sec348.example_api(integer)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION sec348.example_api(integer)
TO sec348_reader;

COMMIT;
```

Đây là ví dụ nếu session hiện tại là owner role hoặc có quyền tạo routine trong schema. Đặt GRANT/REVOKE trong **cùng transaction** giúp tránh khoảng thời gian object mới đã công khai EXECUTE trước khi thu hồi quyền.

### 18.2. REVOKE trên đúng signature

PostgreSQL cho phép **overloaded functions** có cùng tên nhưng khác kiểu tham số.

```sql
REVOKE ALL ON FUNCTION sec348.example_api(integer)
FROM PUBLIC;
```

chỉ nhắm đúng function signature đó, không phải mọi overload cùng tên.

### 18.3. PUBLIC là pseudo-role

`PUBLIC` đại diện tập mọi roles cho những privilege được cấp. Nó **không phải** một role login tên “public”.

REVOKE khỏi PUBLIC không thu hồi những quyền được cấp riêng cho role hoặc được hưởng qua membership.

### 18.4. Kiểm tra quyền cuối cùng

```sql
SELECT
    has_function_privilege(
        'sec348_reader',
        'sec348.example_api(integer)',
        'EXECUTE'
    ) AS reader_allowed,
    has_function_privilege(
        'sec348_other',
        'sec348.example_api(integer)',
        'EXECUTE'
    ) AS other_allowed;
```

Cần kiểm tra cả schema usage/role memberships khi đánh giá khả năng gọi thực tế.

## 19. ALTER DEFAULT PRIVILEGES để giảm rủi ro trong tương lai

Nếu một owner role thường tạo nhiều routines, có thể cấu hình quyền mặc định:

```sql
-- Chạy với owner role phù hợp:
ALTER DEFAULT PRIVILEGES
REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
```

Điều này thay đổi default privileges cho **những functions tạo về sau** trong phạm vi role áp dụng, không tự thu hồi grants của các functions đang tồn tại.

### 19.1. Chú ý scope owner role

Default privileges gắn với role **tạo object**, không tự áp dụng như kỳ vọng chỉ vì owner của một schema là một role khác.

Khi migration chạy bằng một role và sau đó `ALTER OWNER`, phải hiểu default privileges tại thời điểm CREATE.

### 19.2. Per-schema REVOKE không thay thế global REVOKE

Một chi tiết dễ nhầm trong PostgreSQL: per-schema default privileges có thể **bổ sung** lên global defaults. Thu hồi theo schema không nhất thiết xóa quyền đã được cấp bởi default privileges toàn role.

Đối với EXECUTE mặc định cho PUBLIC, cân nhắc cấu hình REVOKE **ở global scope của creator role**, rồi cấp lại có chọn lọc.

### 19.3. Không bỏ REVOKE tường minh trong migration quan trọng

Với security-critical definer routines, vẫn nên có:

```sql
REVOKE ALL ON FUNCTION ...
FROM PUBLIC;
```

gần CREATE trong cùng transaction và kiểm chứng `has_function_privilege`, thay vì tin hoàn toàn vào một setting khó quan sát ở môi trường khác.

### 19.4. GRANT mặc định trên schema không giống EXECUTE

`GRANT USAGE ON SCHEMA` chỉ quyết định khả năng tham chiếu tên, trong khi `EXECUTE ON FUNCTION` quyết định khả năng chạy routine. Cả hai cần được thiết kế rõ.

## 20. Least-privilege owner: owner role nên có quyền gì?

Mẫu kiến trúc:

```text
app_reader (LOGIN / hoặc role của app)
          |
          | USAGE schema + EXECUTE API
          v
api_schema.get_balance(...)
          |
          | SECURITY DEFINER
          v
api_owner (NOLOGIN)
          |
          | SELECT đúng bảng, UPDATE đúng cột/đối tượng
          v
private_data.orders / balances
```

### 20.1. Owner không cần superuser

Nếu hàm chỉ cần đọc `private_data.customers.credit_limit`, đừng cho owner quyền `DROP DATABASE`, `CREATEROLE`, `BYPASSRLS` hoặc quyền trên nhiều schemas không liên quan.

### 20.2. Dùng role riêng cho nhóm nhiệm vụ

Một owner role có thể chỉ chuyên thực hiện:

- Đọc danh sách số dư đã được tổng hợp.
- Ghi audit event vào một bảng riêng.
- Cập nhật trạng thái theo business invariant.

Nếu cần quyền quá khác nhau, cân nhắc tách nhiều owner roles và API schemas thay vì dồn mọi privilege vào một role duy nhất.

### 20.3. Dùng NOLOGIN để giảm bề mặt

`CREATE ROLE sec348_owner NOLOGIN` không tự cấm DBA/role được cấp membership phù hợp dùng `SET ROLE`, nhưng giảm khả năng direct login bằng owner role.

### 20.4. Phân quyền cho app khác với quyền tạo code

Role gọi API không nên có:

- `CREATE` trên trusted schema.
- `ALTER FUNCTION`.
- Quyền thay owner.
- Quyền thay nội dung bảng bí mật.
- Membership có thể SET ROLE thành owner.

### 20.5. Privileges có thể được kế thừa

Các role memberships/inheritance settings có thể khiến một role có quyền ngoài những GRANT trực tiếp mà bạn nhìn thấy. Kiểm tra quyền thực tế bằng `has_*_privilege` và membership, không chỉ đọc lệnh GRANT trong migration.

## 21. Row-Level Security (RLS) và SECURITY DEFINER

RLS kiểm soát những hàng một role được phép thấy/sửa theo policies đã cấu hình.

Với `SECURITY INVOKER`, việc truy vấn bảng thường theo effective privileges và RLS context của caller (trừ những vai trò có cơ chế bypass tương ứng).

Với `SECURITY DEFINER`, truy vấn nội bộ có thể chạy với quyền **owner của hàm**. Khi owner cũng sở hữu bảng hoặc có quyền đặc biệt, **RLS có thể bị bypass** theo quy tắc PostgreSQL.

### 21.1. Chủ bảng thường bypass RLS

Theo quy tắc chung, table owner thường không chịu RLS, trừ khi table dùng `FORCE ROW LEVEL SECURITY` theo điều kiện phù hợp.

`SUPERUSER` và role có `BYPASSRLS` là những trường hợp quyền đặc biệt; `FORCE RLS` không làm mọi role trở thành bị ràng buộc như nhau.

### 21.2. Vì sao nguy hiểm?

Giả sử app gọi definer function:

```sql
SELECT credit_limit
FROM sec348.customers
WHERE customer_id = p_customer_id;
```

Nếu owner có thể bypass RLS và có nhiều tenants cùng `customer_id = 1`, một API có thể trả nhầm hoặc nhiều rows ngoài phạm vi caller.

Không có lý do để tin “RLS ở bảng nên function definer không cần WHERE tenant”.

### 21.3. Chọn kiến trúc một cách có ý thức

Có thể:

- Dùng INVOKER khi muốn caller RLS áp trực tiếp.
- Dùng DEFINER với explicit, **trusted authorization checks** và owner privileges tối thiểu.
- Thiết kế owner role không bypass RLS, đồng thời cấu hình policies phù hợp.
- Cân nhắc `FORCE ROW LEVEL SECURITY` theo nhu cầu, kiểm thử tất cả paths.

Không có một cờ duy nhất thay thế việc kiểm thử tenant isolation của API.

### 21.4. Custom GUC không tự đáng tin

Một policy như:

```sql
USING (
    tenant_id =
    current_setting('app.tenant_id')::integer
)
```

có thể là một phần giải pháp nếu app/database **bảo vệ được nguồn session context**. Nhưng nếu caller untrusted được chạy SQL hoặc `SET app.tenant_id` tùy ý, giá trị này có thể bị giả mạo.

**Dữ liệu trong custom session variable không tự là chứng cứ caller đã được phép truy cập tenant đó.**

## 22. Tenant authorization: kiểm chứng từ nguồn tin cậy

Đối với ứng dụng multi-tenant, một API definer thường cần biết “caller được xem tenant nào?”.

### 22.1. Sai: tin parameter tự khai báo

```sql
CREATE FUNCTION app_api.get_customer(
    p_tenant_id integer,
    p_customer_id integer
)
RETURNS ...
SECURITY DEFINER
...
```

Nếu function chỉ lọc `WHERE tenant_id = p_tenant_id`, caller có thể thử p_tenant_id của tenant khác.

### 22.2. Một thiết kế khi mỗi người dùng có DB login riêng

Một bảng mapping tin cậy:

```sql
-- Chỉ là thiết kế minh họa, không chạy trên lab nếu chưa tạo schema.
CREATE TABLE auth_private.login_tenants (
    login_name name NOT NULL,
    tenant_id integer NOT NULL,
    PRIMARY KEY (login_name, tenant_id)
);
```

Trong một definer function, có thể kiểm tra login role bằng `SESSION_USER` và join mapping đó **nếu mỗi principal thật sự có login riêng và SESSION_USER đáng tin trong kiến trúc này**.

### 22.3. Không áp dụng máy móc với shared app connection

Nếu cả triệu web users dùng cùng `app_database_login`, `SESSION_USER` đều là `app_database_login`.

Bạn cần một authorization design khác: ví dụ ứng dụng server chỉ dùng một trusted DB role, giữ business permissions trong bảng mapping và truyền principal identity từ security context đã xác thực, kết hợp giới hạn đường truy cập hoặc thêm một cơ chế session context có integrity phù hợp.

Chỉ truyền một `p_user_id` **tùy ý từ client** vào definer function không đủ để chứng minh quyền.

### 22.4. Secure-by-default khi thiếu context

Nếu không có identity/tenant context đáng tin, function nên **từ chối** hoặc trả dữ liệu công khai được định nghĩa rõ, không mặc định trả toàn bộ rows.

## 23. Thủ tục (PROCEDURE) và hàm (FUNCTION) có gì giống/khác?

PostgreSQL hỗ trợ:

- `CREATE FUNCTION`: gọi từ biểu thức SQL như `SELECT schema.func(args)`.
- `CREATE PROCEDURE`: thường gọi bằng `CALL schema.proc(args)`.

Cả hai có các khía cạnh quyền `SECURITY INVOKER`/`SECURITY DEFINER` theo định nghĩa được hỗ trợ.

### 23.1. Ví dụ procedure invoker

```sql
CREATE PROCEDURE some_schema.log_attempt(
    p_message text
)
LANGUAGE plpgsql
SECURITY INVOKER
AS $proc$
BEGIN
    -- Logic minh họa.
    RAISE NOTICE 'Event received';
END
$proc$;
```

Đây chỉ là ví dụ cú pháp, không phải routine production bảo mật vì chưa có điều kiện ghi/kiểm soát logs.

### 23.2. Ví dụ procedure definer

```sql
CREATE PROCEDURE some_schema.run_limited_task()
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, some_schema, pg_temp
AS $proc$
BEGIN
    -- Chỉ thao tác được ủy quyền.
    RAISE NOTICE 'Task started';
END
$proc$;
```

Cần owner/grants và schema thực tồn tại. Không tự cho rằng một procedure definer dùng được mọi lệnh quản trị server.

### 23.3. Hạn chế transaction control

Một điểm quan trọng của PostgreSQL:

> **SECURITY DEFINER procedure không được thực hiện các transaction control statements theo quy tắc tương ứng.**

Tức là đừng thiết kế:

```sql
-- KHÔNG dùng trong SECURITY DEFINER procedure:
COMMIT;
ROLLBACK;
```

ở bên trong procedure rồi kỳ vọng nó được phép điều khiển transaction như thủ tục invoker ngoài transaction context.

### 23.4. SET clause cũng ảnh hưởng transaction control

PostgreSQL có các hạn chế transaction control đối với procedure được khai báo `SET` clause, kể cả ngoài câu chuyện SECURITY DEFINER. Vì vậy, pattern `SECURITY DEFINER SET search_path = ...` càng nhấn mạnh việc không nên đưa transaction-control logic vào routine này.

### 23.5. Functions không dùng COMMIT/ROLLBACK như top-level transaction manager

Một PostgreSQL function được gọi trong một statement không phải một transaction controller. Việc commit/rollback thuộc session/client hoặc các thủ tục đáp ứng đúng điều kiện PostgreSQL.

### 23.6. Chọn function hay procedure theo nhiệm vụ

Dùng function khi cần trả một scalar/row/set và tham gia SQL expressions. Dùng procedure cho workflow được gọi bằng `CALL`. Trong cả hai, `SECURITY DEFINER` chỉ nên dùng khi có mục đích cấp quyền rõ và thỏa các hạn chế riêng.

## 24. Viết PL/pgSQL definer function để cập nhật có kiểm soát

Một trường hợp thực tế: cho phép cập nhật hạn mức của customer trong tenant cụ thể **nhưng không cho UPDATE trực tiếp bảng**.

### 24.1. Sai: update tùy ý customer

```sql
-- Mẫu nguy hiểm về authorization:
UPDATE sec348.customers
SET credit_limit = p_new_limit
WHERE customer_id = p_customer_id;
```

Nếu một customer_id có ở nhiều tenant, câu này có thể cập nhật nhiều rows.

### 24.2. Đúng hơn: kiểm tra phạm vi và invariant

```sql
-- Đoạn minh họa bên trong routine đã được bảo vệ:
IF p_new_limit < 0 THEN
    RAISE EXCEPTION
        'Invalid credit limit';
END IF;

UPDATE sec348.customers AS c
SET credit_limit = p_new_limit
WHERE c.tenant_id = 10
  AND c.customer_id = p_customer_id;
```

Trong lab, tenant 10 là phạm vi cứng để minh họa. Production cần xác minh quyền đổi hạn mức bằng nguồn tin cậy, kiểm soát hạn mức tối đa, audit và các invariants.

### 24.3. Không coi RAISE EXCEPTION là authorization

`RAISE EXCEPTION` chỉ là cách từ chối request khi điều kiện không hợp lệ. Bảo mật nằm ở **logic kiểm tra điều kiện thật** và quyền trên data.

### 24.4. Kiểm tra số dòng bị ảnh hưởng

Trong PL/pgSQL:

```sql
GET DIAGNOSTICS v_rows = ROW_COUNT;
```

giúp biết UPDATE vừa xử lý bao nhiêu rows. Với routine kỳ vọng đúng một customer, cần xử lý riêng 0 và >1 theo nghiệp vụ.

### 24.5. Đừng tin một lần SELECT rồi UPDATE vô điều kiện

Dữ liệu có thể thay đổi đồng thời giữa các statements. Với invariant cần bảo vệ, dùng UPDATE có WHERE điều kiện, locking hoặc transaction isolation phù hợp.

## 25. Dynamic SQL: nơi search_path và SQL injection cùng xuất hiện

PL/pgSQL hỗ trợ dynamic SQL:

```sql
EXECUTE dynamic_sql;
```

Trong `SECURITY DEFINER`, đây là vùng rủi ro cao vì dynamic SQL chạy trong privileged context theo cơ chế phù hợp.

### 25.1. Sai: ghép input vào SQL string

```sql
-- Không dùng với input từ người dùng:
EXECUTE
    'SELECT credit_limit FROM sec348.customers ' ||
    'WHERE customer_id = ' || p_customer_id;
```

Dù ví dụ p_customer_id là số, pattern nối chuỗi dễ mở rộng sai sang text/table name và đánh mất type-safe binding.

### 25.2. Đúng hơn: EXECUTE ... USING cho values

```sql
EXECUTE
    'SELECT c.credit_limit ' ||
    'FROM sec348.customers AS c ' ||
    'WHERE c.tenant_id = $1 ' ||
    'AND c.customer_id = $2'
INTO v_limit
USING 10, p_customer_id;
```

Các `$1`/`$2` trong dynamic command là placeholders cho `USING` của PL/pgSQL EXECUTE.

### 25.3. Value parameters khác identifiers

Không thể dùng `USING` để thay tên bảng/schema/cột trong câu SQL:

```sql
-- Không phải cách bind table identifier:
EXECUTE 'SELECT * FROM $1' USING p_table_name;
```

Tên object là **identifier**, không phải SQL value.

### 25.4. Quote identifiers khi thật sự cần dynamic object names

```sql
EXECUTE format(
    'SELECT COUNT(*) FROM %I.%I',
    v_schema_name,
    v_table_name
)
INTO v_count;
```

`%I` trong `format` quote identifier theo quy tắc PostgreSQL, giúp tránh identifier-based SQL injection.

### 25.5. Quote đúng chưa phải authorization

Nếu caller có thể chọn:

```text
schema = finance_private
table  = salaries
```

thì format `%I.%I` vẫn tạo SQL **hợp lệ** truy cập một bảng caller có thể không được xem, khi definer owner có quyền.

Vì vậy, phải kiểm tra **allowlist các objects được phép**, không chỉ escape identifier.

### 25.6. Tránh `%s` cho input không tin cậy

`format('%s', input)` không quote identifier/literal theo cùng cách `%I`/`%L`. Nếu input chứa SQL syntax, dùng nó trong dynamic SQL một cách thiếu kiểm soát vẫn có thể injection.

### 25.7. Dùng %L hay USING?

`%L` giúp quote SQL literal khi phải xây chuỗi SQL, nhưng khi dynamic SQL hỗ trợ bind values bằng `USING`, thường ưu tiên `USING` để tách data và SQL structure.

### 25.8. Schema-qualify trong dynamic SQL

```sql
EXECUTE
    'UPDATE sec348.customers ' ||
    'SET credit_limit = $1 ' ||
    'WHERE tenant_id = $2 AND customer_id = $3'
USING p_new_limit, 10, p_customer_id;
```

Đừng để dynamic command phụ thuộc một unqualified table name mà caller có thể shadow.

## 26. SECURITY DEFINER và function overloading

PostgreSQL cho phép nhiều functions cùng tên khác signature:

```sql
some_schema.get_value(integer)
some_schema.get_value(text)
```

### 26.1. Privilege theo exact signature

`GRANT EXECUTE ON FUNCTION some_schema.get_value(integer)` không nhất thiết cấp quyền cho overload `get_value(text)`.

### 26.2. Resolver và implicit casts

Một câu SQL:

```sql
SELECT get_value('123');
```

có thể cần type resolution và có khả năng ambiguous hoặc chọn overload khác kỳ vọng tùy các signatures/path.

Trong privileged SQL, nên:

- Dùng schema-qualified function names.
- Dùng argument types rõ ràng.
- Tránh untrusted schemas trong path.
- Kiểm tra overload/default/variadic arguments.
- Không tin rằng “hàm cùng tên trong pg_catalog luôn được chọn” khi path bị đặt sai.

### 26.3. Default arguments có thể tạo nhầm lẫn

Một overload với default arguments có thể cạnh tranh với một lời gọi ít tham số hơn. Đây là một lý do không đưa schemas attacker-writable vào path của privileged routine.

### 26.4. Kiểm kê signature thay vì tên thuần

```sql
SELECT
    p.oid::regprocedure AS routine_identity,
    pg_get_function_identity_arguments(p.oid)
        AS identity_arguments
FROM pg_proc AS p
JOIN pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE n.nspname = 'sec348'
ORDER BY routine_identity::text;
```

Dùng exact OID/signature khi audit hoặc thay đổi grants.

## 27. Routines, trigger functions và quyền ngầm

Một trigger function có thể chạy khi người dùng INSERT/UPDATE một bảng, dù caller không trực tiếp gọi `SELECT my_trigger_func()`.

### 27.1. Definer trigger là ranh giới quyền quan trọng

Nếu trigger function là `SECURITY DEFINER` và update bảng audit/financial, nó có thể thực hiện thao tác theo quyền owner.

Điều này hữu ích để ghi audit không cho app role sửa audit rows tùy ý, nhưng cũng tạo rủi ro nếu:

- Trigger nhận dữ liệu đầu vào không tin cậy.
- Tên bảng/hàm được tra qua unsafe search_path.
- Owner có quyền quá rộng.
- Có dynamic SQL.
- Thông báo lỗi làm lộ dữ liệu.

### 27.2. Không cho caller tự tạo trigger trên bảng nhạy cảm

Một role có quyền tạo/đổi trigger hoặc sửa function definition có thể mở rộng bề mặt ảnh hưởng đáng kể. Các quyền DDL cần được kiểm soát riêng với quyền INSERT/UPDATE nghiệp vụ.

### 27.3. Audit không được xem là bất khả sửa chỉ nhờ trigger

Bảo vệ audit trail còn cần ownership, INSERT-only privileges, kiểm soát retention, log transport và cơ chế chống sửa phù hợp.

### 27.4. Function SECURITY DEFINER không tự được miễn mọi kiểm tra

Nó vẫn chịu ràng buộc constraints, transaction semantics và privileges của owner, cũng như policies/triggers khác theo điều kiện cụ thể. Nó không phải “bật superuser tạm thời”.

## 28. `SET search_path` được lưu ở đâu?

PostgreSQL lưu routine configuration trong catalog `pg_proc.proconfig`.

Ví dụ:

```sql
SELECT
    p.oid::regprocedure AS routine_name,
    p.prosecdef AS security_definer,
    p.proconfig AS routine_settings
FROM pg_proc AS p
JOIN pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE n.nspname = 'sec348'
ORDER BY routine_name::text;
```

### 28.1. `prosecdef`

- `true`: routine có thuộc tính `SECURITY DEFINER`.
- `false`: routine là `SECURITY INVOKER` theo mode tương ứng.

### 28.2. `proconfig`

Mảng cấu hình lưu `SET` options gắn với routine, nếu có.

Với definer function:

```text
{search_path=pg_catalog, sec348, pg_temp}
```

có thể xuất hiện dưới dạng biểu diễn text của setting.

### 28.3. NULL proconfig đáng điều tra

Một `SECURITY DEFINER` có `proconfig IS NULL` không tự chứng minh khai thác được, nhưng là dấu hiệu cần review search_path và object qualification.

### 28.4. Không chỉ audit mã text qua grep

Search path rủi ro có thể đến từ:

- Function body.
- Routine-level SET config.
- Owner role/session defaults.
- Nested helpers.
- Dynamic SQL.
- Quyền CREATE trên schemas.

Cần xem toàn bộ threat model.

## 29. Kiểm kê tất cả SECURITY DEFINER routines

Trong database hiện tại, một truy vấn hữu ích cho audit:

```sql
SELECT
    n.nspname AS routine_schema,
    p.proname AS routine_name,
    p.oid::regprocedure AS identity,
    r.rolname AS owner_role,
    p.prosecdef AS security_definer,
    p.proconfig AS settings
FROM pg_proc AS p
JOIN pg_namespace AS n
  ON n.oid = p.pronamespace
JOIN pg_roles AS r
  ON r.oid = p.proowner
WHERE p.prosecdef
  AND n.nspname NOT IN (
      'pg_catalog',
      'information_schema'
  )
ORDER BY routine_schema, identity::text;
```

### 29.1. Những câu hỏi khi rà soát

1. Hàm có cần DEFINER không?
2. Owner có superuser hoặc `BYPASSRLS` không?
3. Owner có quá nhiều schema/table privileges không?
4. Function có `SET search_path` riêng không?
5. Path có `pg_temp` ở cuối không?
6. Path có schema nào attacker-writable không?
7. Body có tên bảng/hàm chưa schema-qualified không?
8. Có dynamic SQL không?
9. Có input nào được dùng chọn object không?
10. Có kiểm tra tenant/user authorization không?
11. Có `EXECUTE` cấp PUBLIC không?
12. Có tồn tại overload với default args không?
13. Có trigger/procedure gọi routine này không?
14. Có RLS bị bypass không?
15. Có integration tests cho negative cases không?

### 29.2. Đọc định nghĩa function

```sql
SELECT pg_get_functiondef(
    'sec348.definer_limit(integer)'::regprocedure
);
```

`pg_get_functiondef` hiển thị DDL-like definition của routine và giúp xem `SECURITY DEFINER`, `SET search_path`, body khi có quyền phù hợp.

### 29.3. Giới hạn quyền quan sát

Thông tin schema/catalog và function source có thể bị giới hạn theo môi trường/quyền. Khi audit bảo mật, dùng role quản trị phù hợp và không đưa nội dung chứa bí mật vào log/report công khai.

## 30. Kiểm tra quyền CREATE trên schemas

Một schema được đưa vào definer search_path chỉ đáng tin khi untrusted roles **không có CREATE** ở đó.

Ví dụ:

```sql
SELECT
    n.nspname,
    has_schema_privilege(
        'sec348_reader',
        n.oid,
        'USAGE'
    ) AS reader_usage,
    has_schema_privilege(
        'sec348_reader',
        n.oid,
        'CREATE'
    ) AS reader_create,
    has_schema_privilege(
        'sec348_other',
        n.oid,
        'CREATE'
    ) AS other_create
FROM pg_namespace AS n
WHERE n.nspname IN ('sec348', 'public')
ORDER BY n.nspname;
```

### 30.1. Bắt đầu từ quyền hiện tại, không từ mặc định lịch sử

Trong những database cũ hoặc đã upgrade, schema `public` có thể vẫn có quyền CREATE rộng. PostgreSQL 15 thay đổi một số defaults của schema public trên database mới, nhưng không thể suy mọi hệ thống từ phiên bản server.

### 30.2. REVOKE CREATE trên public khi phù hợp

```sql
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
```

Đây là **thao tác quản trị có thể ảnh hưởng ứng dụng/migrations khác**. Chỉ thực hiện sau khi xác định ai đang tạo objects trong public và có kế hoạch chuyển họ sang schema phù hợp.

### 30.3. Một schema trusted có thể bị phá bởi membership

Ngay cả khi PUBLIC không có CREATE, một role có thể hưởng CREATE qua membership/grants riêng. Cần kiểm tra role hierarchy và owner privileges.

### 30.4. Không cấp quyền thay object definition cho caller

Ngoài CREATE, attacker có quyền sở hữu/ALTER một helper function được gọi bởi definer cũng có thể thay đổi hành vi. Trusted path phải đi cùng trusted **object ownership**.

## 31. Thay đổi search_path của function đã tồn tại

PostgreSQL hỗ trợ:

```sql
ALTER FUNCTION sec348.definer_limit(integer)
SET search_path = pg_catalog, sec348, pg_temp;
```

Câu này thường cần owner hoặc role quản trị phù hợp.

### 31.1. Không tự kết luận ALTER SET là sửa xong

Nếu body có `EXECUTE` dynamic SQL ghép identifiers từ caller, hoặc cho quyền EXECUTE quá rộng, chỉ sửa search_path chưa xóa hết rủi ro.

### 31.2. Luôn kiểm tra đúng signature

Nếu có overloads, dùng exact argument types trong `ALTER FUNCTION` để tránh sửa nhầm routine.

### 31.3. Với PROCEDURE

```sql
ALTER PROCEDURE some_schema.some_proc(integer)
SET search_path = pg_catalog, some_schema, pg_temp;
```

Dùng syntax tương ứng routine kind; `ALTER FUNCTION` không phải luôn thay thế `ALTER PROCEDURE`.

### 31.4. Quan sát sau migration

Kiểm tra:

```sql
SELECT
    p.oid::regprocedure,
    p.prosecdef,
    p.proconfig
FROM pg_proc AS p
WHERE p.oid =
    'sec348.definer_limit(integer)'::regprocedure;
```

Cùng với `has_function_privilege` và negative tests.

## 32. Không tin search_path từ connection pool

Một backend được pool dùng lại qua nhiều HTTP requests có thể giữ session settings như:

```sql
SET search_path = tenant_schema, public;
```

Nếu code quên `RESET` hoặc connection không được reset thích hợp, request kế tiếp có thể tra nhầm table/function.

### 32.1. Dùng SET LOCAL khi hợp với transaction

```sql
BEGIN;

SET LOCAL search_path = pg_catalog, some_schema;

-- Các statement trong cùng transaction.

COMMIT;
```

`SET LOCAL` hết hiệu lực khi transaction kết thúc theo cơ chế PostgreSQL. Nó **không tự bảo vệ** definer function trước mọi đối tượng attacker-writable; routine-level `SET search_path` mới là điểm quan trọng.

### 32.2. Không dùng SET LOCAL ngoài transaction riêng

Nếu mỗi statement chạy autocommit và app gửi `SET LOCAL` riêng, setting có thể không tồn tại trong scope của SELECT/CALL kế tiếp như kỳ vọng.

### 32.3. SECURITY DEFINER nên tự khóa path

Một function có:

```sql
SECURITY DEFINER
SET search_path = pg_catalog, sec348, pg_temp
```

không dựa trên session search_path mà web request đã thay đổi.

### 32.4. Dùng connection pool không đồng nghĩa SESSION_USER là web user

Nhiều HTTP users có thể dùng cùng DB login. `SESSION_USER` thể hiện kết nối database, không tự là email/user ID trong JWT.

### 32.5. Đừng dùng SET ROLE như API “giả mạo definer”

Caller có quyền `SET ROLE sec348_owner` sẽ có đặc quyền owner ở ngoài routine, phá ranh giới bảo mật. Cấu hình role membership phải bảo đảm app không thể chuyển sang privileged owner role.

## 33. Lỗi và exception không được làm lộ dữ liệu

Một definer function có thể trả lỗi chứa chi tiết:

- Giá trị khóa bí mật.
- SQL text có input nhạy cảm.
- Table names/private schema.
- Exception messages từ nested helper.
- Nội dung row hoặc trạng thái authorization.

### 33.1. Không in toàn bộ SQL động

```sql
RAISE NOTICE 'SQL: %', v_dynamic_sql;
```

có thể lộ thông tin nếu dynamic command chứa secrets.

### 33.2. Phân biệt lỗi permission và lỗi not found

Một API public có thể trả cùng thông báo “không tìm thấy hoặc không được phép” khi không muốn tiết lộ sự tồn tại của một customer ID ở tenant khác.

Chính sách error semantics thuộc business/security requirements; phải kiểm thử cả timing/side channels nếu dữ liệu cực nhạy.

### 33.3. Không nuốt mọi exception rồi trả dữ liệu mặc định

Mẫu:

```sql
EXCEPTION WHEN OTHERS THEN
    RETURN 0;
```

có thể che lỗi quyền, sai search_path hoặc cơ sở dữ liệu không nhất quán. Chỉ xử lý các loại lỗi dự kiến và có logging bảo mật/observability phù hợp.

### 33.4. Privileged routine phải có error strategy

Một hàm ghi tài chính nên xác định rõ atomicity, rollback/error codes, audit event, retry semantics và trường hợp duplicate requests. `SECURITY DEFINER` không sửa được business transaction design.

## 34. Hiệu năng: SECURITY DEFINER không phải “đường tắt” tối ưu truy vấn

Khi gọi:

```sql
SELECT sec348.definer_limit(1);
```

server vẫn phải:

- Kiểm tra quyền gọi routine.
- Thiết lập/restoring security context và routine GUCs theo cơ chế.
- Thực thi SQL bên trong.
- Đọc các bảng/index cần thiết.
- Tuân thủ MVCC.
- Trả kết quả.

### 34.1. Security boundary có thể ảnh hưởng inlining

Một số SQL functions đơn giản có thể được PostgreSQL inline trong những điều kiện hỗ trợ. `SECURITY DEFINER` và một số routine-level `SET` options là những yếu tố có thể khiến inlining không áp dụng như ở một invoker SQL function thuần đơn giản.

Không giả định function có một plan y hệt câu SQL inline ngoài routine. Cần đo khi routine được gọi hàng triệu lần.

### 34.2. Function được gọi mỗi row

```sql
SELECT
    c.customer_id,
    sec348.definer_limit(c.customer_id)
FROM sec348.customers AS c;
```

có thể gọi function theo từng row và tạo overhead, thậm chí N+1 style repeated lookups. Không dùng cách này để truy xuất hàng triệu rows nếu có query/set-based API phù hợp hơn.

### 34.3. Index vẫn quan trọng

Ví dụ `sec348.customers` có primary key trên `(tenant_id, customer_id)` phù hợp với query tenant+customer. Không nên kỳ vọng definer function tự tạo khả năng dùng index.

### 34.4. EXPLAIN và quan sát function

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sec348.definer_limit(1);
```

Đối với một function gọi query nội bộ, EXPLAIN ở câu ngoài không nhất thiết hiển thị chi tiết toàn bộ nested SQL plans theo cách bạn muốn. Có thể cần instrumentation/logging hoặc công cụ chuyên dụng trong môi trường thử nghiệm.

### 34.5. Theo dõi function calls nếu được cấu hình

PostgreSQL có `pg_stat_user_functions`; việc thu thập function-level statistics phụ thuộc `track_functions` và loại routine/cấu hình.

```sql
SELECT
    funcid::regprocedure AS function_name,
    calls,
    total_time,
    self_time
FROM pg_stat_user_functions
WHERE schemaname = 'sec348'
ORDER BY total_time DESC;
```

Không suy “không có row thống kê” nghĩa function chưa từng được gọi nếu tracking chưa bật hoặc các điều kiện instrumentation khác chưa thỏa.

## 35. Quy trình migration của SECURITY DEFINER

Một migration an toàn thường cần:

1. Xác định owner role và quyền tối thiểu.
2. Tạo private/trusted schema hoặc xác minh schema hiện tại không attacker-writable.
3. Tạo các objects nền với ownership/grants rõ ràng.
4. Viết function với `SECURITY DEFINER` và routine-level `SET search_path`.
5. Schema-qualify các bảng/helper functions nhạy cảm.
6. Tránh dynamic SQL hoặc kiểm soát allowlist/`USING`.
7. **CREATE + REVOKE FROM PUBLIC + GRANT** trong cùng transaction.
8. Kiểm tra chính xác signature, owner và proconfig.
9. Kiểm thử invoker/definer bằng roles không có quyền trực tiếp trên bảng.
10. Kiểm thử caller không có EXECUTE.
11. Kiểm thử temp table shadowing/schema shadowing.
12. Kiểm thử row/tenant authorization.
13. Kiểm thử RLS và pool/session state.
14. Đo performance để tránh routine per-row overhead.
15. Triển khai theo cơ chế canary/rollback phù hợp.

### 35.1. Tránh replace routine mà không kiểm tra grants

`CREATE OR REPLACE FUNCTION` giữ một số thuộc tính/quyền của function hiện có theo cơ chế PostgreSQL. Không giả định replace sẽ reset mọi GRANT hoặc đổi owner.

Sau bất kỳ migration thay đổi body/owner/signature/security mode nào, phải re-audit effective privileges.

### 35.2. Đổi signature có thể tạo overload mới

Nếu thêm một tham số và dùng `CREATE OR REPLACE FUNCTION` với signature khác, PostgreSQL có thể tạo **function mới** thay vì thay definition cũ; function mới lại có default EXECUTE considerations.

Vì vậy cần kiểm tra catalog sau migration.

### 35.3. Bảo vệ CREATE FUNCTION credentials

Migration nên chạy bằng role có quyền tạo routine tại trusted schema, nhưng không cấp khả năng sửa definer functions cho app runtime role.

### 35.4. Rollback phải xét dữ liệu và grants

Đổi security mode hoặc owner không chỉ tác động source code. Rollback cần biết schema ownership, default privileges, grants và API compatibility.

## 36. Checklist nhanh: khi nào dùng SECURITY INVOKER?

Chọn INVOKER theo mặc định nếu:

- Caller đã được phép truy cập dữ liệu cần thiết.
- RLS theo caller là điều mong muốn.
- Routine chỉ tính toán hoặc bọc câu SQL để dùng lại.
- Không cần che quyền trực tiếp trên bảng.
- Không cần thực hiện thao tác đặc quyền hẹp.

Một invoker function vẫn cần mã an toàn, schema qualification phù hợp và kiểm thử input.

## 37. Checklist nhanh: khi nào dùng SECURITY DEFINER?

Chỉ chọn DEFINER nếu:

- Có nhu cầu cấp quyền **gián tiếp, có giới hạn** vào một thao tác.
- Caller không nên có quyền bảng trực tiếp.
- API kiểm tra được những điều kiện authorization bắt buộc.
- Owner role có quyền tối thiểu.
- Trusted schemas và pg_temp placement được kiểm soát.
- EXECUTE chỉ cấp cho những roles cần gọi.
- Code không chứa SQL động/overloads nguy hiểm chưa được kiểm soát.
- RLS semantics được hiểu và test.
- Có audit/logging/monitoring phù hợp.
- Có migration và regression tests.

Nếu không trả lời được “caller bị giới hạn ở những hàng và thao tác nào?”, chưa nên dùng DEFINER để mở quyền.

## 38. Những hiểu lầm và lỗi phổ biến

| Ngộ nhận/lỗi | Thực tế |
| --- | --- |
| Function mặc định là DEFINER | Mặc định là INVOKER |
| Cấp EXECUTE nghĩa là cấp SELECT trên bảng | Không; hai privilege khác nhau |
| SECURITY DEFINER chạy như superuser | Chạy dưới quyền owner, không tự là superuser |
| Owner là superuser thì không sao | Tạo bề mặt đặc quyền cực rộng |
| NOLOGIN owner không thể bị SET ROLE | Membership/role permissions vẫn cần kiểm tra |
| CURRENT_USER trong definer là caller | Nó biểu thị owner trong definer context |
| SESSION_USER đổi khi SET ROLE | Không tự đổi theo SET ROLE |
| SESSION_USER luôn là web user | Shared connection pool thường dùng một DB login |
| Chỉ cần WHERE customer_id | Có thể thiếu tenant/authorization |
| search_path chỉ áp dụng cho table | Còn nhiều objects khác như function/operator/type |
| SET search_path=trusted_schema đã an toàn | pg_temp có thể được tìm trước nếu không đặt rõ |
| pg_temp luôn ở cuối path | Không; cần explicit placement |
| pg_temp tìm functions/operators như tables | Temporary schema lookup khác theo loại object |
| pg_catalog không cần quan tâm | Vị trí explicit trong path có thể ảnh hưởng resolution |
| public mặc định luôn an toàn | Phụ thuộc schema ACL, phiên bản và upgrade |
| Schema USAGE đồng nghĩa CREATE | Đây là hai quyền riêng |
| Definer function để tên bảng không định danh cũng được | Có thể bị shadowing |
| Alias bảng thay schema qualification | Không |
| SET search_path của caller đủ bảo vệ definer | Nên SET ở routine definition |
| Function name hiếm đủ an toàn | Không; dựa vào privileges/namespace |
| GRANT EXECUTE chỉ cho app sau CREATE là luôn an toàn | Có thể có PUBLIC EXECUTE trước khi REVOKE nếu khác transaction |
| PUBLIC là một login role | Là pseudo-role đại diện mọi roles |
| REVOKE PUBLIC thu hồi hết membership GRANT | Không; quyền riêng/membership vẫn tồn tại |
| ALTER DEFAULT PRIVILEGES hồi tố | Chỉ tác động objects tạo về sau |
| Per-schema REVOKE xóa mọi global default GRANT | Không phải luôn vậy |
| Definer luôn tuân RLS caller | Effective role/owner có thể bypass RLS |
| FORCE RLS khiến superuser cũng chịu policies | Không tự làm vậy |
| Custom GUC luôn chứng minh user identity | Caller có thể giả mạo nếu quyền/session không bảo vệ |
| `format('%I')` là đủ an toàn | Chỉ quote identifier, không kiểm tra được phép chọn object |
| `EXECUTE ... USING` bind được tên bảng | Chỉ values trong vị trí hỗ trợ |
| Procedure DEFINER có thể COMMIT tùy ý | Có hạn chế transaction control |
| SET clause của procedure không ảnh hưởng transaction | Có các giới hạn liên quan |
| CTE/VIEW/hàm là security boundary mặc định | Cần hiểu quyền/semantics từng object |
| EXPLAIN ngoài function luôn hiện SQL bên trong | Không nhất thiết |
| Replacing function luôn xóa GRANT cũ | Không được giả định |
| Chỉ cần kiểm thử happy path | Phải thử quyền âm tính, RLS, path shadowing |
| Hàm không xuất hiện trong pg_stat_user_functions nghĩa chưa chạy | Tracking phụ thuộc config |

## 39. Bài tập thực hành có đáp án

Các bài dựa trên schema `sec348`. Chỉ chạy DDL và role changes trên database lab, với role quản trị phù hợp. Những đoạn SQL ghi “không an toàn” là **anti-pattern để phân tích**, không dùng trong production.

### Bài 1. Mode mặc định của function là gì?

**Đáp án:** `SECURITY INVOKER`.

### Bài 2. SECURITY INVOKER dùng quyền ai?

**Đáp án:** quyền của caller/effective role khi thực thi routine, theo các quy tắc PostgreSQL áp dụng cho lời gọi đó.

### Bài 3. SECURITY DEFINER dùng quyền ai?

**Đáp án:** chủ sở hữu function/procedure trong lúc thực thi routine.

### Bài 4. Một caller có EXECUTE nhưng không SELECT bảng bí mật sẽ thế nào với invoker?

**Đáp án:** thường bị lỗi quyền khi routine cố đọc bảng đó, trừ khi có quyền qua vai trò/cơ chế khác.

### Bài 5. Cùng caller đó có thể dùng definer không?

**Đáp án:** có, nếu owner đủ quyền, function code cho phép và caller có quyền EXECUTE; các điều kiện khác như schema USAGE cũng cần đúng.

### Bài 6. Vì sao không nên tạo definer function bằng superuser?

**Đáp án:** một lỗi logic/name-resolution có thể có tác động dưới quyền quá rộng. Nên dùng owner role tối thiểu.

### Bài 7. CURRENT_USER bên trong definer là ai?

**Đáp án:** owner của routine khi definer context đang có hiệu lực.

### Bài 8. SESSION_USER có đổi khi SET ROLE không?

**Đáp án:** không tự đổi; nó thường vẫn là login role của session.

### Bài 9. Dùng SET ROLE có kiểm thử đúng login mapping theo SESSION_USER không?

**Đáp án:** không đầy đủ. Cần test bằng DB login thật nếu logic phụ thuộc SESSION_USER.

### Bài 10. Quyền USAGE ON SCHEMA khác CREATE thế nào?

**Đáp án:** USAGE cho phép name lookup phù hợp; CREATE cho phép tạo objects trong schema. Caller của definer API thường chỉ cần USAGE.

### Bài 11. Kiểm tra quyền SELECT của reader

```sql
SELECT has_table_privilege(
    'sec348_reader',
    'sec348.customers',
    'SELECT'
);
```

**Đáp án:** lab mong đợi false nếu không có role membership/GRANT bổ sung.

### Bài 12. Kiểm tra EXECUTE của reader

```sql
SELECT has_function_privilege(
    'sec348_reader',
    'sec348.definer_limit(integer)',
    'EXECUTE'
);
```

**Đáp án:** true nếu đã thực hiện GRANT như phần 8.

### Bài 13. Vì sao không chỉ nhìn has_function_privilege?

**Đáp án:** còn schema USAGE, table privileges theo invoker/definer, role memberships và business authorization.

### Bài 14. SET search_path có tác dụng gì?

**Đáp án:** ảnh hưởng cách PostgreSQL resolve unqualified object names theo loại object, schemas được phép và resolution rules.

### Bài 15. Vì sao `SELECT * FROM customers` rủi ro trong definer?

**Đáp án:** có thể resolve về một bảng khác khi path chứa untrusted/temporary objects.

### Bài 16. Fully qualified table name là gì?

```sql
SELECT c.credit_limit
FROM sec348.customers AS c;
```

**Đáp án:** `sec348.customers` chỉ rõ schema và relation.

### Bài 17. `SET search_path = sec348` đã đặt pg_temp cuối chưa?

**Đáp án:** chưa. Khi không liệt kê rõ, temporary namespace có thể được tìm trước cho relation/type names.

### Bài 18. Cấu hình definer path thường nên dùng?

**Đáp án:** `SET search_path = pg_catalog, sec348, pg_temp` nếu sec348 là trusted schema và routines được viết phù hợp.

### Bài 19. Vì sao pg_catalog nên nằm trước schema untrusted?

**Đáp án:** giảm rủi ro functions/operators built-in bị shadow hoặc thay đổi resolution bởi objects của attacker.

### Bài 20. pg_temp có được tìm cho function names giống table names không?

**Đáp án:** không. Temporary schema lookup chủ yếu liên quan relation/type, không tìm theo cách đó cho unqualified functions/operators.

### Bài 21. CREATE TEMP TABLE có tạo bản sao tables toàn database không?

**Đáp án:** không. Nó tạo temporary table trong session tương ứng, nhưng có thể shadow unqualified relation names trong session đó.

### Bài 22. Nếu definer function luôn dùng sec348.customers, temp customers có ảnh hưởng direct table reference không?

**Đáp án:** không làm thay đổi tên fully qualified `sec348.customers`. Nhưng phải kiểm tra các unqualified helpers/types/dynamic SQL khác trong routine.

### Bài 23. Schema attacker-writable trong path gây rủi ro nào?

**Đáp án:** attacker có thể tạo objects cùng tên/overloads/operators làm thay đổi function/type/operator/table resolution theo cơ chế thích hợp.

### Bài 24. Có nên đưa public vào definer search_path không?

**Đáp án:** chỉ khi public thực sự trusted và cần thiết. Thường ưu tiên schema chuyên dụng được kiểm soát.

### Bài 25. Phiên bản PostgreSQL 15 có đảm bảo mọi public schema đã an toàn không?

**Đáp án:** không; database mới, database upgrade và GRANT lịch sử có thể khác nhau. Kiểm tra ACL thực tế.

### Bài 26. PUBLIC EXECUTE có ý nghĩa gì?

**Đáp án:** mặc định function mới có thể có EXECUTE cho pseudo-role PUBLIC, tức mọi role đủ điều kiện khác có thể gọi khi có schema USAGE.

### Bài 27. Thu hồi đúng một function overload thế nào?

```sql
REVOKE ALL ON FUNCTION sec348.definer_limit(integer)
FROM PUBLIC;
```

**Đáp án:** dùng đúng signature để nhắm function cần thu hồi.

### Bài 28. Vì sao nên CREATE/REVOKE/GRANT trong một transaction?

**Đáp án:** tránh cửa sổ object đã được công khai EXECUTE trước khi các GRANT được giới hạn.

### Bài 29. ALTER DEFAULT PRIVILEGES có tác động đến functions cũ không?

**Đáp án:** không. Nó áp dụng cho objects tạo về sau trong scope tương ứng.

### Bài 30. Per-schema default REVOKE có tự hủy global GRANT cho PUBLIC không?

**Đáp án:** không được giả định; cần hiểu quan hệ giữa global defaults và per-schema defaults.

### Bài 31. Nếu definer nhận p_tenant_id tự do mà không xác minh thì sao?

**Đáp án:** có thể cho caller tra dữ liệu tenant khác nếu owner có quyền rộng; phải kiểm tra authorization từ nguồn tin cậy.

### Bài 32. SECURITY DEFINER có tự áp dụng RLS của caller không?

**Đáp án:** không mặc định. Definer dùng effective privileges/role owner, và table owner hoặc role bypass có thể không chịu RLS như caller.

### Bài 33. FORCE RLS có ép superuser chịu policy không?

**Đáp án:** không tự làm vậy; superuser/BYPASSRLS có ngoại lệ quyền đặc biệt.

### Bài 34. Custom setting app.tenant_id có phải chứng cứ phân quyền không?

**Đáp án:** chỉ khi kiến trúc bảo đảm caller không thể giả mạo; một custom GUC tự do không phải security boundary.

### Bài 35. Dùng dynamic SQL với values an toàn hơn thế nào?

```sql
EXECUTE
    'SELECT credit_limit ' ||
    'FROM sec348.customers ' ||
    'WHERE tenant_id = $1 AND customer_id = $2'
INTO v_limit
USING 10, p_customer_id;
```

**Đáp án:** dùng placeholders và `USING`, không nối values vào SQL string.

### Bài 36. Có bind table name bằng EXECUTE USING được không?

**Đáp án:** không. Identifiers phải được kiểm soát/quote, ví dụ `format('%I.%I', schema, table)`.

### Bài 37. `format('%I.%I')` có đủ để caller tùy chọn bảng bí mật không?

**Đáp án:** không. Quote ngăn identifier injection nhưng không kiểm tra quyền chọn object; vẫn cần allowlist/authorization.

### Bài 38. Vì sao `format('%s', untrusted_input)` nguy hiểm?

**Đáp án:** không quote như identifier/literal, nên có thể đưa SQL syntax từ input vào dynamic command.

### Bài 39. PROCEDURE SECURITY DEFINER có được COMMIT tùy ý không?

**Đáp án:** không. PostgreSQL có hạn chế transaction control đối với definer procedures.

### Bài 40. PROCEDURE khai báo SET clause có thể COMMIT trong mọi ngữ cảnh không?

**Đáp án:** không. Procedure có SET clause cũng chịu hạn chế transaction control phù hợp.

### Bài 41. Có thể tạo SECURITY DEFINER trigger function không?

**Đáp án:** có, nhưng nó là privileged boundary cần owner/path/SQL/authorization/audit đúng, không được coi trigger tự an toàn.

### Bài 42. Xem danh sách definer routines bằng catalog nào?

**Đáp án:** `pg_proc` với `prosecdef = true`, join `pg_namespace` và `pg_roles` để xem schema/owner.

### Bài 43. `proconfig` có thể chứa thông tin gì?

**Đáp án:** các routine-level SET options như `search_path`; NULL có thể cho biết routine không khai báo options đó.

### Bài 44. Đọc định nghĩa một function thế nào?

```sql
SELECT pg_get_functiondef(
    'sec348.definer_limit(integer)'::regprocedure
);
```

**Đáp án:** đọc DDL-like definition và kiểm tra body, SECURITY mode, path.

### Bài 45. Thay đổi path của function đã có bằng lệnh nào?

```sql
ALTER FUNCTION sec348.definer_limit(integer)
SET search_path = pg_catalog, sec348, pg_temp;
```

**Đáp án:** dùng exact signature và xác minh proconfig sau thay đổi.

### Bài 46. CREATE OR REPLACE FUNCTION có reset mọi grants không?

**Đáp án:** không được giả định. Kiểm tra owner, privileges và security attributes sau migration.

### Bài 47. Vì sao đổi signature có thể nguy hiểm?

**Đáp án:** có thể tạo overload mới thay vì thay function cũ, và overload mới có default EXECUTE considerations.

### Bài 48. `pg_stat_user_functions` vắng một function có chứng minh nó chưa chạy không?

**Đáp án:** không. Thu thập statistics phụ thuộc track_functions/cấu hình và các điều kiện hỗ trợ.

### Bài 49. Vì sao gọi definer function mỗi row có thể chậm?

**Đáp án:** overhead routine call, context switch và repeated queries có thể tạo N+1 style work, dù truy cập qua index.

### Bài 50. Lập một checklist triển khai an toàn

**Đáp án gợi ý:**

1. Xác định tác vụ nào cần đặc quyền và dùng INVOKER mặc định khi đủ.
2. Tạo owner NOLOGIN ít quyền, không superuser/BYPASSRLS trừ lý do không thể tránh.
3. Đặt routines trong trusted schema, không cho callers CREATE/ALTER helper objects.
4. Dùng `SECURITY DEFINER SET search_path = pg_catalog, trusted, pg_temp`.
5. Schema-qualify tables và helpers nhạy cảm.
6. Thu hồi EXECUTE khỏi PUBLIC và chỉ GRANT roles cần thiết, trong cùng transaction khi tạo.
7. Không tin tenant/user ID do caller tự khai báo mà không xác thực.
8. Kiểm tra RLS, owner bypass và session identity.
9. Dùng `EXECUTE ... USING` cho values, quote identifiers và allowlist objects.
10. Kiểm tra negative cases: caller không quyền, tenant khác, temporary/schema shadowing.
11. Kiểm kê `pg_proc`/`proconfig`, quyền schema/EXECUTE và owner memberships.
12. Giám sát lỗi/latency, review migrations và chuẩn bị rollback.

## 40. Quy trình audit và hardening trong hệ thống thật

Một routine đã chạy ổn nhiều tháng không có nghĩa vẫn an toàn sau khi schema/roles thay đổi.

### Bước 1. Kiểm kê definer routines

```sql
SELECT
    p.oid::regprocedure,
    r.rolname AS owner,
    p.proconfig
FROM pg_proc AS p
JOIN pg_roles AS r
  ON r.oid = p.proowner
WHERE p.prosecdef
ORDER BY p.oid::regprocedure::text;
```

### Bước 2. Kiểm tra scope schemas

- Routines đang nằm trong schema nào?
- Có schema nào trong path cho untrusted roles CREATE không?
- Có public schema grants lịch sử không?
- Có temp relation shadowing nếu pg_temp không được liệt kê cuối không?
- Có search_path được đổi ở role/session level không?

### Bước 3. Kiểm tra quyền gọi

```sql
SELECT
    has_function_privilege(
        'sec348_reader',
        'sec348.definer_limit(integer)',
        'EXECUTE'
    ) AS allowed_reader,
    has_function_privilege(
        'sec348_other',
        'sec348.definer_limit(integer)',
        'EXECUTE'
    ) AS unapproved_reader;
```

Kỳ vọng true/false tương ứng sau các GRANT trong lab. Nếu khác, kiểm tra PUBLIC/role membership/ACL.

### Bước 4. Đọc body và nested dependencies

Tìm:

- Unqualified tables/functions/types.
- Dynamic SQL.
- Input có thể chọn tenant/table/column.
- Call tới helpers không trusted.
- Logic authorization.
- Exception handlers làm lộ secrets.
- Data writes và row-count assumptions.

### Bước 5. Sửa với scope nhỏ

- Khóa routine-level search_path.
- Qualify names.
- Revoke unneeded EXECUTE.
- Tách owner role quá rộng.
- Thêm explicit tenant authorization nếu thiếu.
- Thêm tests/observability.

### Bước 6. Kiểm thử negative scenarios

Các case quan trọng:

| Tình huống | Kết quả mong muốn |
| --- | --- |
| Caller không có schema USAGE | Không gọi được bằng tên trong schema |
| Caller không có EXECUTE | Không thực thi được routine |
| Caller có EXECUTE nhưng không SELECT table | INVOKER fail, DEFINER chỉ làm API cho phép |
| Caller tạo temp table trùng tên | Definer an toàn không đổi object đích |
| Caller thay session search_path | Definer an toàn giữ routine-level path |
| Caller truyền tenant khác | Không trả dữ liệu ngoài phạm vi |
| Caller truyền tên bảng khác | Không chạy object ngoài allowlist |
| Public/grants bị mở rộng | Kiểm tra và phát hiện hồi quy |
| RLS có owner bypass | Có explicit authorization đúng |
| Dynamic input chứa SQL syntax | Bind/quote và deny trái phép |
| Routine error | Không lộ dữ liệu nhạy cảm |
| Connection pool reuse | Không rò session context bất hợp lệ |

### Bước 7. Theo dõi sau deploy

Đo:

- Tỷ lệ permission errors.
- Function calls/latency.
- Thay đổi grants/owners/routine definitions.
- Mẫu query bất thường.
- Logging/anomaly reports.
- Tốc độ database/locks.
- Hiệu quả và ổn định của API contract.

Security review phải là một phần của **migration lifecycle**, không phải kiểm tra một lần khi tạo function đầu tiên.

## 41. Checklist trước khi phát hành function/procedure

| Câu hỏi | Cách xác minh |
| --- | --- |
| Thực sự cần SECURITY DEFINER? | Lý do đặc quyền cụ thể |
| INVOKER có đủ không? | Test quyền caller |
| Owner có NOLOGIN? | `pg_roles` |
| Owner có quá nhiều quyền? | Grants và memberships |
| Owner có superuser/BYPASSRLS? | Role attributes |
| Trusted schema có CREATE cho attacker? | `has_schema_privilege` |
| `search_path` đã khóa trong definition? | `pg_proc.proconfig` |
| `pg_catalog` ở vị trí ưu tiên? | Routine SET clause |
| `pg_temp` có được đặt cuối? | Routine SET clause |
| Sensitive objects fully qualified? | Review SQL/PLpgSQL body |
| Helpers cũng an toàn? | Call graph |
| Có overloaded functions? | Exact signatures |
| Có implicit casts/default args? | Resolution tests |
| Có dynamic SQL? | `EXECUTE` review |
| Data values có bind qua USING? | Test injection |
| Identifiers có quote đúng? | `format('%I')` |
| Identifiers có allowlist? | Authorization tests |
| Caller có tự chọn tenant khác? | Negative isolation tests |
| Identity có đáng tin? | DB login/app security context |
| RLS có bị bypass không? | Owner/role/policy tests |
| PUBLIC EXECUTE đã thu hồi? | ACL/`has_function_privilege` |
| GRANT có cùng transaction CREATE? | Migration review |
| App role có schema USAGE? | Privilege checks |
| App role có CREATE/ALTER không? | Privilege checks |
| Có procedure transaction control? | Security mode/SET restrictions |
| Có trigger sử dụng routine? | Dependencies |
| Có query per-row quá đắt? | EXPLAIN/metrics |
| Error có lộ secrets? | Exception/log review |
| Có tests caller không quyền? | Negative tests |
| Có tests pg_temp shadowing? | New-session tests |
| Có tests schema shadowing? | Untrusted CREATE tests |
| Có connection-pool isolation? | Multi-request tests |
| Có audit sau CREATE OR REPLACE? | Catalog diff |
| Có plan rollback? | Revert DDL/grants |
| Có monitoring sau deploy? | Alerts/latency/security events |

## 42. Tổng kết

PostgreSQL cho phép dùng functions/procedures như một tầng API bảo mật sát dữ liệu, nhưng chỉ an toàn khi thiết kế đủ **quyền, định danh objects và authorization**.

Những điều quan trọng nhất:

1. **`SECURITY INVOKER` là mặc định** và phù hợp khi caller nên dùng quyền của chính mình.
2. **`SECURITY DEFINER` chạy dưới quyền owner** trong phạm vi routine. Nó có thể cho phép caller thực hiện thao tác được định nghĩa dù không được truy cập bảng trực tiếp.
3. **Đặc quyền EXECUTE khác SELECT và schema USAGE**. Phải hiểu cả ba tầng.
4. **Chủ sở hữu routine nên ít quyền nhất**, ưu tiên role chuyên biệt NOLOGIN thay vì superuser.
5. **`CURRENT_USER` trong definer thể hiện owner**, không phải caller; `SESSION_USER` thường là DB login và không tự đổi theo `SET ROLE`.
6. **`search_path` ảnh hưởng phân giải object names**, gồm tables, functions, types và operators theo các quy tắc riêng.
7. **`pg_catalog` nên được ưu tiên** để tránh untrusted schemas shadow built-in functions/operators.
8. **`pg_temp` phải được xem xét rõ ràng**: với relation/type names, temporary schema có thể được tìm trước nếu không đặt cuối path.
9. **Định nghĩa definer function an toàn** thường dùng `SET search_path = pg_catalog, trusted_schema, pg_temp` và fully qualified table references.
10. **Không đưa schema attacker-writable vào path** hoặc cho app role sửa trusted helpers.
11. **Functions mới có thể có PUBLIC EXECUTE mặc định**; CREATE/REVOKE/GRANT trong cùng transaction giúp tránh cửa sổ quyền.
12. **Default privileges không hồi tố**, và per-schema/default grants cần hiểu theo đúng owner/scope.
13. **RLS có thể bị bypass trong definer context** nếu owner có quyền đặc biệt hoặc là table owner theo semantics tương ứng.
14. **Caller-provided tenant/ID không phải bằng chứng quyền truy cập**. Authorization phải dựa trên nguồn tin cậy và kiểm tra mỗi thao tác.
15. **Dynamic SQL cần `EXECUTE ... USING` cho values**, `format('%I')` cho identifiers khi thật sự cần và allowlist objects có thể truy cập.
16. **SECURITY DEFINER procedures có hạn chế transaction control**, không coi chúng như transaction manager tùy ý.
17. **Audit bằng `pg_proc.prosecdef`, `proconfig`, `pg_get_functiondef` và `has_*_privilege`** để thấy cấu hình thực, không chỉ source code dự kiến.
18. **Kiểm thử negative cases là bắt buộc**: temp shadowing, caller thiếu quyền, tenant khác, role/session state và RLS.
19. **Hiệu năng vẫn quan trọng**: definer không thay index/planner; routine per-row có thể gây overhead lớn.
20. **Vận hành lâu dài cần monitoring và migration review** khi role/schema/function definitions thay đổi.

Mẫu tạo definer API đáng nhớ:

```sql
SET ROLE sec348_owner;

BEGIN;

CREATE FUNCTION sec348.get_limit(
    p_customer_id integer
)
RETURNS numeric
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, sec348, pg_temp
AS $fn$
    SELECT c.credit_limit
    FROM sec348.customers AS c
    WHERE c.tenant_id = 10
      AND c.customer_id = p_customer_id
$fn$;

REVOKE ALL ON FUNCTION sec348.get_limit(integer)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION sec348.get_limit(integer)
TO sec348_reader;

COMMIT;

RESET ROLE;
```

Mẫu này dùng **tenant 10 cố định chỉ để minh họa kiểm soát privilege**. Một API multi-tenant thực phải thêm xác minh caller được phép truy cập tenant/customer tương ứng, không chỉ thay hằng 10 thành một parameter tùy ý.

**Quy tắc cuối cùng:** với mọi `SECURITY DEFINER`, luôn hỏi: **“Chủ sở hữu có quyền gì, caller có thể ảnh hưởng những object names/parameters nào, hàm đang tra tên qua search_path nào, và điều kiện gì ngăn caller vượt phạm vi dữ liệu được phép?”**. Khi trả lời rõ các câu này bằng DDL, ACL và kiểm thử thực tế, bạn mới có một routine đặc quyền có thể tin cậy trong PostgreSQL.
