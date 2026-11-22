# Quyền gọi, chủ thể thực thi và phạm vi truy cập đối tượng trong thủ tục và hàm SQL

Một ứng dụng thường cần cho nhân viên xem số dư, cập nhật trạng thái đơn hàng hoặc tính một chỉ số, nhưng **không muốn cấp trực tiếp quyền đọc hay sửa toàn bộ bảng nhạy cảm**. Stored procedure và stored function có thể tạo ra một giao diện truy cập dữ liệu được kiểm soát:

- Người dùng được phép **gọi** một routine cụ thể.
- Routine thực hiện một số câu `SELECT`, `INSERT`, `UPDATE` hoặc `DELETE` đã được thiết kế.
- Hệ quản trị quyết định **quyền của ai được dùng khi routine truy cập đối tượng bên trong**.
- Kết quả được phép trả về có thể hẹp hơn nhiều so với quyền đọc cả bảng.

Tuy nhiên, một câu `GRANT EXECUTE` chưa đủ để kết luận người gọi có thể đọc bảng bên trong, và một routine chạy bằng quyền của người tạo có thể trở thành **lỗ hổng leo thang quyền** nếu không giới hạn tham số, câu SQL động và phạm vi tenant.

Bài học thuộc chương **Thủ tục và hàm** trong module **Database SQL**, tập trung vào ba câu hỏi:

1. **Quyền gọi:** ai có quyền gọi procedure/function, gọi bằng `CALL`, `EXEC` hay `SELECT function(...)`?
2. **Chủ thể thực thi:** trong lúc routine chạy, hệ quản trị kiểm tra quyền với **người gọi** (*invoker/caller*) hay **người định nghĩa/chủ sở hữu** (*definer/owner*)?
3. **Phạm vi truy cập đối tượng:** routine được tìm và truy cập bảng, view, schema, routine khác, hàng dữ liệu, cơ sở dữ liệu khác theo cơ chế nào?

Đây là kiến thức vừa liên quan bảo mật vừa liên quan kiến trúc: **một routine đúng cú pháp không đương nhiên đúng về quyền**. Ta sẽ dùng PostgreSQL làm bộ ví dụ chi tiết, sau đó so sánh MySQL/MariaDB, SQL Server, Oracle và SQLite.

> Các ví dụ quản lý role, schema và GRANT cần tài khoản quản trị hoặc tài khoản có quyền tương ứng. Chỉ chạy trên **database thử nghiệm**, không tự tạo role, cấp quyền hay dùng `SECURITY DEFINER`/`EXECUTE AS OWNER` ở production nếu chưa có chính sách phân quyền và đánh giá bảo mật.

## 1. Bốn khái niệm phải tách riêng

### 1.1. Routine là đối tượng có thể được gọi

Một **stored function** thường trả giá trị hoặc tập hàng, ví dụ:

```sql
-- PostgreSQL: function trả một giá trị.
SELECT api.calculate_fee(1000.00);
```

Một **stored procedure** thường được gọi như một thao tác:

```sql
-- PostgreSQL: procedure được gọi bằng CALL.
CALL api.close_order(101);
```

Cú pháp khác theo hệ:

- PostgreSQL: `SELECT schema.function(args)` hoặc `CALL schema.procedure(args)`.
- MySQL/MariaDB: `CALL schema.procedure(args)`; function thường dùng trong biểu thức như `SELECT schema.function(args)`.
- SQL Server: `EXEC schema.procedure @param = ...`, `EXECUTE ...`; scalar function thường dùng trong `SELECT schema.function(args)`.
- Oracle: procedure qua PL/SQL hoặc `CALL` theo ngữ cảnh; function qua SQL/PLSQL khi được phép.
- SQLite: không có stored procedure do SQL engine quản lý như các DBMS trên; hàm do ứng dụng đăng ký theo API có cơ chế khác.

Đặt một routine trong schema không có nghĩa mọi người đã được gọi nó. Ngược lại, một người được phép gọi không nhất thiết được sửa định nghĩa routine.

### 1.2. Quyền gọi routine

**Quyền gọi** là phép kiểm tra ở cổng vào của routine. Thường gặp:

```sql
-- PostgreSQL, ví dụ về cú pháp:
GRANT EXECUTE ON FUNCTION api.get_balance(bigint) TO app_reader;

-- PostgreSQL:
GRANT EXECUTE ON PROCEDURE api.close_order(bigint) TO app_operator;
```

Ở SQL Server, procedure và scalar function thường dùng quyền `EXECUTE`. Với **table-valued function**, quyền truy cập qua `SELECT` là điểm khác cần lưu ý.

### 1.3. Chủ thể thực thi và kiểm tra quyền bên trong

Routine có thể chứa:

```sql
SELECT balance
FROM private.accounts
WHERE account_id = ...;
```

DBMS phải quyết định **quyền `SELECT` của ai** cho `private.accounts` được kiểm tra.

Hai mô hình chính:

- **Invoker/caller rights:** sử dụng quyền của chủ thể đang gọi routine.
- **Definer/owner rights:** sử dụng quyền của chủ thể định nghĩa hoặc sở hữu routine theo quy tắc DBMS.

SQL Server còn có **ownership chaining**: trong những tình huống module và bảng cùng chủ sở hữu, quyền trên bảng có thể không được kiểm tra riêng, ngay cả khi module dùng context caller mặc định.

### 1.4. Phạm vi truy cập đối tượng

Không chỉ quyền `SELECT` trên một bảng. Một lệnh bên trong routine có thể phải đi qua nhiều lớp:

```text
Phiên kết nối / DB principal
             |
             v
Xác định database + schema + routine
             |
             v
Quyền gọi routine: EXECUTE / SELECT tương ứng
             |
             v
Thiết lập execution context (caller / owner / definer)
             |
             v
Giải quyết tên đối tượng bên trong routine
             |
             v
Quyền schema, bảng, cột, view, routine khác
             |
             v
RLS, chính sách hàng, trigger, ràng buộc và logic nghiệp vụ
             |
             v
Kết quả hoặc lỗi
```

Đây là **sơ đồ tư duy**, không phải thứ tự kiểm tra vật lý tuyệt đối của mọi DBMS. Một số bước có thể được bỏ qua theo ownership chaining hoặc cơ chế quyền đặc thù.

## 2. Vì sao chỉ GRANT EXECUTE chưa đủ?

Giả sử có bảng `private.accounts`:

| account_id | owner_name | balance |
|---:|---|---:|
| 101 | An | 3500.00 |
| 102 | Bình | 7200.00 |
| 103 | Chi | 1400.00 |

Một function:

```sql
-- Mô tả ý tưởng, chưa gắn vào DBMS cụ thể.
get_balance(account_id) =
    SELECT balance FROM private.accounts
    WHERE account_id = account_id_input;
```

Cấp quyền gọi:

```sql
GRANT EXECUTE ON FUNCTION api.get_balance(bigint) TO report_reader;
```

Có ít nhất ba tình huống:

1. **Routine invoker rights:** report_reader gọi được function, nhưng nếu không có quyền trên `private.accounts` thì phần SELECT bên trong có thể bị từ chối.
2. **Routine definer rights:** report_reader được gọi, còn phần SELECT sử dụng quyền của chủ routine có quyền đọc bảng; lời gọi có thể thành công.
3. **SQL Server với ownership chain đủ điều kiện:** caller có `EXECUTE` trên procedure, không có `SELECT` bảng, nhưng truy vấn tĩnh trong procedure vẫn có thể thành công vì quyền bảng không được kiểm tra lại trong chuỗi sở hữu chung.

Do đó, không có quy tắc phổ quát “GRANT EXECUTE là cấp SELECT bảng” hoặc “muốn gọi routine luôn phải GRANT SELECT bảng”.

## 3. Ba loại danh tính: login, role hiệu lực và chủ routine

Các hệ có nhiều cách biểu diễn identity:

| Loại danh tính | Ý nghĩa |
|---|---|
| **Session/login principal** | Tài khoản đăng nhập hoặc kết nối tới DB |
| **Effective execution principal** | Chủ thể có quyền được dùng tại thời điểm thực thi một câu hoặc routine |
| **Routine owner/definer** | Chủ thể gắn với routine, có thể được dùng làm context khi routine chạy |

Một hệ có role activation, `SET ROLE` hoặc `EXECUTE AS` có thể làm **identity hiệu lực** khác identity của phiên đăng nhập.

### 3.1. PostgreSQL CURRENT_USER và SESSION_USER

Trong PostgreSQL:

```sql
SELECT
    session_user AS login_identity,
    current_user AS effective_identity;
```

- `session_user` thường là identity đăng nhập ban đầu của phiên (có những tình huống đổi được bởi chủ thể đủ quyền).
- `current_user` là role hiệu lực để kiểm tra quyền tại thời điểm gọi.
- `SET ROLE another_role` có thể làm `current_user` khác `session_user`.
- Bên trong function `SECURITY DEFINER`, `current_user` được đổi theo **chủ function** trong phạm vi thực thi.

Trong ứng dụng có connection pool, cả hai giá trị có thể chỉ là **tài khoản dịch vụ chung**, không phải user đăng nhập web/app. Đừng dùng `SESSION_USER` làm ID khách hàng cuối nếu nhiều người cùng dùng một DB login.

### 3.2. MySQL USER() và CURRENT_USER()

MySQL phân biệt thông tin client kết nối và tài khoản/quyền hiệu lực. Trong routine `SQL SECURITY DEFINER`, `CURRENT_USER()` có thể phản ánh account definer theo cơ chế thực thi. `USER()` phản ánh thông tin đăng nhập/kết nối. Cách nhận diện này không thay thế hệ thống xác thực người dùng cuối ở API.

### 3.3. SQL Server và Oracle

SQL Server có các hàm như `ORIGINAL_LOGIN()`, `SUSER_SNAME()`, `USER_NAME()` và context `EXECUTE AS`. Các hàm này có phạm vi server/database khác nhau; tránh xem chúng là đồng nghĩa.

Oracle có `SYS_CONTEXT('USERENV', 'SESSION_USER')`, `CURRENT_USER` và `CURRENT_SCHEMA`, chịu ảnh hưởng của ngữ cảnh definer/invoker. Trong các chương trình PL/SQL, giá trị current user và cách phân giải schema có thể thay đổi theo `AUTHID`.

## 4. PostgreSQL: mặc định SECURITY INVOKER

PostgreSQL mặc định chạy function/procedure với quyền **người gọi**:

```sql
CREATE FUNCTION api.example()
RETURNS integer
LANGUAGE sql
SECURITY INVOKER
AS $$
    SELECT 1;
$$;
```

Có thể bỏ hẳn `SECURITY INVOKER` vì đó là mặc định. Nhưng viết tường minh giúp người đọc biết routine **không cố ý nâng quyền**.

Với một function invoker có SQL:

```sql
SELECT amount FROM private.payments WHERE payment_id = p_id;
```

caller cần quyền thích hợp để phần SQL thực thi. Nếu không có quyền `USAGE` trên schema hoặc `SELECT` trên bảng, câu gọi có thể lỗi dù caller được cấp `EXECUTE` trên function.

### 4.1. SECURITY DEFINER

PostgreSQL cho phép:

```sql
CREATE FUNCTION api.example()
RETURNS integer
LANGUAGE sql
SECURITY DEFINER
AS $$
    SELECT 1;
$$;
```

Routine chạy với quyền của **chủ sở hữu function**, không phải quyền tùy ý của người gọi.

Điều đó cho phép **đóng gói một phép truy cập hạn chế** vào bảng nhạy cảm. Nhưng cũng có nghĩa người được gọi routine có thể thực hiện gián tiếp những thao tác mà họ không đủ quyền làm trực tiếp.

**Câu hỏi bảo mật:** Có được phép cho caller chọn bất kỳ `account_id` nào để lấy số dư không? Nếu function chỉ có một tham số ID và không kiểm tra chủ sở hữu/tenant, một routine definer có thể vô tình tiết lộ nhiều tài khoản.

### 4.2. Không nhầm SECURITY DEFINER với quyền sở hữu bảng

Chủ function **không bắt buộc là chủ bảng**. Để thực hiện `SELECT` trong definer routine, chủ function cần quyền phù hợp trên bảng hoặc quyền kế thừa có hiệu lực.

Một role chuyên biệt `routine_owner` có thể được cấp **chỉ SELECT trên các cột cần thiết**, rồi sở hữu function. Cách này thường tốt hơn để function thuộc về superuser hoặc tài khoản quản trị có toàn quyền.

## 5. PostgreSQL: dựng môi trường thử hai role và hai schema

Bài thử sau mô tả rõ cổng vào, role thực thi và quyền bảng.

**Yêu cầu:** chạy bằng tài khoản quản trị/superuser **trên database thử**. Các role và schema có tên `lab_` để tránh nhầm với hệ thống thật. Nếu đã tồn tại thì cần dùng tên khác hoặc quy trình reset được phê duyệt. Không tự chạy `DROP ROLE/SCHEMA CASCADE` trên hệ thống chung.

### 5.1. Tạo role

```sql
-- PostgreSQL: tài khoản đủ quyền quản lý role.
CREATE ROLE lab_routine_owner NOLOGIN;
CREATE ROLE lab_routine_caller NOLOGIN;
```

- `lab_routine_owner`: role **không tự đăng nhập**, được dùng làm chủ routine có quyền đọc bảng.
- `lab_routine_caller`: role **không tự đăng nhập**, được dùng mô phỏng quyền của ứng dụng gọi routine.
- `NOLOGIN` không có nghĩa role không sở hữu đối tượng hoặc không được `SET ROLE` bởi tài khoản được phép.

Trong ứng dụng thật, role đăng nhập của service có thể nhận quyền qua membership, nhưng phải kiểm tra `INHERIT`/`SET ROLE` và cấu hình phiên bản PostgreSQL.

### 5.2. Tạo schema và bảng bí mật

```sql
CREATE SCHEMA lab_data;
CREATE SCHEMA lab_api;

CREATE TABLE lab_data.payments (
    payment_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    internal_note TEXT NOT NULL
);

INSERT INTO lab_data.payments
    (payment_id, tenant_id, amount, internal_note)
VALUES
    (1, 10, 3500.00, 'Internal account note A'),
    (2, 10, 7200.00, 'Internal account note B'),
    (3, 20, 1400.00, 'Internal account note C');
```

Bảng cố ý có `internal_note` nhạy cảm. Giao diện routine minh họa chỉ trả `amount`, không trả cả hàng.

### 5.3. Cấp quyền tối thiểu cho chủ routine

```sql
-- Hạn chế schema dữ liệu nếu có quyền PUBLIC ngoài ý định.
REVOKE ALL ON SCHEMA lab_data FROM PUBLIC;

-- Chủ routine cần tra cứu đối tượng trong schema dữ liệu.
GRANT USAGE ON SCHEMA lab_data TO lab_routine_owner;

-- Chỉ cấp các cột cần cho function.
GRANT SELECT (payment_id, amount)
ON lab_data.payments
TO lab_routine_owner;

-- Role này phải có thể sở hữu function trong schema API.
GRANT USAGE, CREATE
ON SCHEMA lab_api
TO lab_routine_owner;

-- Caller chỉ cần thấy schema API và có quyền gọi được cấp sau.
GRANT USAGE ON SCHEMA lab_api TO lab_routine_caller;
```

**Không cấp** `USAGE` trên `lab_data` hoặc `SELECT` trên `lab_data.payments` cho `lab_routine_caller`. Vì vậy caller không thể đọc bảng trực tiếp theo chính sách thử nghiệm.

### 5.4. Tạo function SECURITY DEFINER và giới hạn người được gọi

```sql
-- PostgreSQL: chạy bằng role quản trị đủ quyền.
BEGIN;

CREATE FUNCTION lab_api.payment_amount(p_payment_id bigint)
RETURNS numeric
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
    SELECT p.amount
    FROM lab_data.payments AS p
    WHERE p.payment_id = p_payment_id;
$$;

-- Chuyển ownership sang role đặc quyền tối thiểu.
ALTER FUNCTION lab_api.payment_amount(bigint)
OWNER TO lab_routine_owner;

-- PostgreSQL mặc định cấp EXECUTE cho PUBLIC trên function mới.
REVOKE ALL ON FUNCTION lab_api.payment_amount(bigint)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION lab_api.payment_amount(bigint)
TO lab_routine_caller;

COMMIT;
```

Giải thích các lựa chọn:

1. Function đặt trong `lab_api`: tách **API public cho role** khỏi schema chứa dữ liệu thật.
2. `SECURITY DEFINER`: phần SELECT chạy theo quyền của `lab_routine_owner`.
3. `SET search_path = pg_catalog, pg_temp`: tránh phụ thuộc schema do caller có thể điều khiển; `pg_temp` được liệt kê cuối, không bị tra cứu trước các schema đáng tin trong những trường hợp cần xử lý.
4. `lab_data.payments` được **schema-qualify** tường minh, tránh thay bảng thật bằng một đối tượng cùng tên trong search path.
5. Quyền `SELECT` của chủ routine chỉ bao gồm `payment_id` và `amount`, không có `internal_note`.
6. `REVOKE ... FROM PUBLIC` cùng transaction với `CREATE FUNCTION` để tránh cửa sổ routine vô tình có thể được gọi trước khi ACL được siết.
7. `GRANT EXECUTE` chỉ cấp cổng vào routine cho caller.

**Chú ý kỹ thuật:** `ALTER FUNCTION ... OWNER TO` yêu cầu đặc quyền thích hợp và owner mới có `CREATE` trên schema chứa function, trừ các ngoại lệ của tài khoản quản trị. Bài thử giả định một superuser hoặc role quản trị có quyền đầy đủ thực thi các bước.

### 5.5. Thử gọi bằng role hạn chế

Trong phiên quản trị được phép `SET ROLE`:

```sql
SET ROLE lab_routine_caller;

-- Hợp lệ: caller có USAGE schema API và EXECUTE function.
SELECT lab_api.payment_amount(1) AS amount;
-- 3500.00

RESET ROLE;
```

Bên trong function, quyền truy cập `lab_data.payments` được kiểm tra theo `lab_routine_owner`.

Thử đọc trực tiếp bằng caller:

```sql
SET ROLE lab_routine_caller;

-- THỬ RIÊNG: dự kiến bị từ chối.
SELECT *
FROM lab_data.payments;

RESET ROLE;
```

Câu SELECT trực tiếp không đi qua function definer, và caller không có quyền schema/bảng tương ứng.

**Lưu ý lỗi khi thử:** Nếu thực thi câu cố ý gây lỗi bên trong transaction PostgreSQL, transaction có thể chuyển sang trạng thái aborted. Hãy dùng các thử nghiệm riêng hoặc rollback/savepoint, tránh chạy nối tiếp mọi ví dụ lỗi trong một transaction rồi diễn giải các lỗi sau.

### 5.6. Điểm nguy hiểm còn lại trong ví dụ: tham số tùy ý

Function nhận `p_payment_id` do caller chọn. Caller có thể gọi:

```sql
SELECT lab_api.payment_amount(3);
```

và nhận số tiền của tenant 20, **dù caller được thiết kế chỉ phục vụ tenant 10**. Đây là ví dụ có chủ ý cho thấy việc ẩn bảng không bằng bảo vệ phạm vi hàng.

Ở production, routine cần kiểm tra **quyền đối với payment cụ thể** dựa vào identity/tenant đã được xác thực phía server, chẳng hạn bảng ánh xạ quyền được bảo vệ hoặc cơ chế RLS được thiết kế đúng. Không nhận `tenant_id` từ client rồi xem nó là bằng chứng quyền truy cập.

## 6. PostgreSQL: cùng truy vấn nhưng SECURITY INVOKER

Tạo function có cùng logic đọc dữ liệu, nhưng dùng quyền người gọi:

```sql
BEGIN;

CREATE FUNCTION lab_api.payment_amount_invoker(p_payment_id bigint)
RETURNS numeric
LANGUAGE sql
SECURITY INVOKER
SET search_path = pg_catalog, pg_temp
AS $$
    SELECT p.amount
    FROM lab_data.payments AS p
    WHERE p.payment_id = p_payment_id;
$$;

REVOKE ALL ON FUNCTION lab_api.payment_amount_invoker(bigint)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION lab_api.payment_amount_invoker(bigint)
TO lab_routine_caller;

COMMIT;
```

Thử:

```sql
SET ROLE lab_routine_caller;

-- THỬ RIÊNG: có EXECUTE nhưng thiếu USAGE/SELECT bảng gốc.
SELECT lab_api.payment_amount_invoker(1);

RESET ROLE;
```

Câu gọi được phép bước vào function, nhưng khi SQL bên trong cố đọc `lab_data.payments`, PostgreSQL có thể từ chối vì **role hiệu lực là caller**.

So sánh:

| Kiểm tra | `payment_amount` DEFINER | `payment_amount_invoker` INVOKER |
|---|---|---|
| Caller có EXECUTE? | Có | Có |
| Caller có USAGE schema API? | Có | Có |
| Caller có SELECT trực tiếp bảng dữ liệu? | Không | Không |
| Identity dùng khi truy cập bảng | `lab_routine_owner` | `lab_routine_caller` |
| Có thể đọc amount qua routine? | Có theo quyền owner | Không trong dữ liệu thử |
| Có tự kiểm tra tenant? | **Không** | **Không** |

Nếu cấp thêm `USAGE` trên `lab_data` và quyền `SELECT` các cột tương ứng cho caller, function invoker có thể chạy. Nhưng như vậy caller cũng có thể được đọc trực tiếp theo các quyền đã cấp, trái mục tiêu **chỉ đi qua API routine** của kịch bản.

## 7. PostgreSQL: EXECUTE mặc định cho PUBLIC là bẫy đáng nhớ

Một quy tắc quan trọng của PostgreSQL: **function và procedure mới được tạo thường có quyền EXECUTE mặc định cấp cho `PUBLIC`**.

`PUBLIC` không phải một role cá nhân do bạn tạo. Nó là phạm vi bao gồm **mọi role** theo quy tắc ACL.

Nếu bạn tạo:

```sql
CREATE FUNCTION lab_api.sensitive_operation(...)
RETURNS ...
LANGUAGE ...
SECURITY DEFINER
AS ...;
```

và quên thu hồi quyền EXECUTE mặc định, routine có thể được gọi rộng hơn dự kiến, miễn caller còn có quyền truy cập schema cần thiết và không bị hạn chế khác.

### 7.1. Cách làm an toàn khi tạo

```sql
BEGIN;

-- CREATE FUNCTION / PROCEDURE tại đây.

REVOKE ALL ON FUNCTION lab_api.sensitive_operation(bigint)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION lab_api.sensitive_operation(bigint)
TO trusted_role;

COMMIT;
```

Câu khung trên giả định function có chữ ký `(bigint)` và đã được tạo trong transaction. Lưu trong **cùng một transaction** giúp tránh khoảng thời gian đối tượng đã xuất hiện cho các phiên khác nhưng ACL chưa được siết, khi việc triển khai transaction của PostgreSQL và công cụ migration phù hợp.

### 7.2. Cấp quyền cho mọi routine trong schema là quyền rộng

PostgreSQL có cú pháp ở phạm vi nhiều routine:

```sql
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA lab_api
TO some_role;
```

Đây là quyền **rộng**: có thể bao gồm cả function nhạy cảm không được dự định cho role đó. Tương tự, `ALTER DEFAULT PRIVILEGES` có thể cấu hình quyền mặc định cho routine tương lai, nhưng cần phân biệt quyền mặc định **toàn cục** với quyền **theo schema**, vai trò của role tạo đối tượng và những grant cho PUBLIC.

Không tự động cấp toàn bộ quyền EXECUTE trong schema chỉ để sửa một lỗi “permission denied” duy nhất. Với API bảo mật, nên chia schema theo chức năng và cấp quyền theo **chữ ký routine** cụ thể.

## 8. PostgreSQL: quyền USAGE trên schema, quyền trên bảng và quyền EXECUTE là các cổng khác nhau

Cùng một lời gọi:

```sql
SELECT lab_api.payment_amount(1);
```

có thể thất bại ở những tầng riêng:

| Quyền bị thiếu | Hậu quả thường gặp |
|---|---|
| `USAGE` trên `lab_api` | Không tham chiếu được function trong schema API bằng đường này |
| `EXECUTE` trên function `(bigint)` | Không được gọi function dù schema nhìn thấy |
| `USAGE` trên `lab_data` trong context hiệu lực | Function có thể không tìm/truy cập được bảng nguồn theo quyền đang chạy |
| `SELECT` trên bảng/cột nguồn trong context hiệu lực | SQL bên trong bị từ chối |
| Role chạy bị RLS chặn | Có thể chỉ thấy 0/một phần hàng dù có SELECT bảng |
| Routine kiểm tra tenant/tham số và từ chối | Lỗi nghiệp vụ, độc lập với GRANT |

**Kết luận:** quyền được gọi **không** bao hàm quyền xem mọi đối tượng bên trong, và quyền bảng **không** tự bao hàm quyền gọi routine trong schema khác.

### 8.1. Phân giải tên và search_path

Trong PostgreSQL:

```sql
SELECT payment_amount(1);
```

chỉ hoạt động nếu engine tìm được function trong search path thích hợp và caller có các quyền liên quan. Cách rõ ràng hơn:

```sql
SELECT lab_api.payment_amount(1);
```

Nêu schema không tự cấp quyền, nhưng tránh vô tình gọi một routine cùng tên thuộc schema khác.

Bên trong `SECURITY DEFINER`, tên không có schema như:

```sql
SELECT amount FROM payments WHERE payment_id = p_payment_id;
```

có thể là rủi ro nếu caller điều khiển `search_path` hoặc tạo đối tượng trong schema có độ ưu tiên cao. Hãy dùng:

```sql
FROM lab_data.payments
```

và thiết lập `SET search_path` an toàn cho routine, đặc biệt lưu ý `pg_temp`.

### 8.2. Schema writable và function shadowing

Nếu một schema do người dùng không tin cậy có quyền `CREATE` xuất hiện trước schema đáng tin trong `search_path`, người dùng đó có thể đặt tên một function/operator/object trùng để ảnh hưởng cách SQL bên trong routine được phân giải.

Chỉ **schema-qualify bảng** là một biện pháp quan trọng, nhưng các routine nhạy cảm còn phải xét **hàm và toán tử** không được ghi schema tường minh, search path của type và dynamic SQL. Một khung an toàn là đặt `pg_catalog`/schema tin cậy theo thứ tự rõ, `pg_temp` ở cuối, đồng thời không cho caller tạo đối tượng trong schema tin cậy.

### 8.3. Không tin tham số tên bảng

Ví dụ nguy hiểm về mặt thiết kế:

```text
SECURITY DEFINER function:
    input = tên bảng bất kỳ
    thực hiện SELECT * FROM bảng đó
```

Nếu caller được chọn tên tùy ý, function có thể trở thành **cổng đọc mọi bảng mà owner có quyền**. Dùng tham số bind/quote identifier đúng cách giúp tránh SQL injection, nhưng **không tự giải quyết authorization**.

Nếu bắt buộc dùng SQL động, cần **allowlist các đối tượng được phép**, schema qualification, kiểm tra role/tenant và quyền tối thiểu của owner. Không nhận arbitrary SQL string từ người gọi để thực thi trong definer routine.

## 9. PostgreSQL: quyền gọi function quá tải theo chữ ký

PostgreSQL hỗ trợ **function overloading**: nhiều function cùng tên với kiểu tham số khác nhau.

```sql
CREATE FUNCTION lab_api.format_id(p_id integer)
RETURNS text
LANGUAGE sql
AS $$ SELECT p_id::text; $$;

CREATE FUNCTION lab_api.format_id(p_id bigint)
RETURNS text
LANGUAGE sql
AS $$ SELECT p_id::text; $$;
```

Hai routine là hai **chữ ký khác nhau**. Khi cấp quyền:

```sql
GRANT EXECUTE ON FUNCTION lab_api.format_id(integer)
TO lab_routine_caller;
```

không nên hiểu rằng bạn đã cấp đúng cùng quyền cho `lab_api.format_id(bigint)`.

Cách gọi với literal/kiểu cụ thể có thể chọn overload tương ứng:

```sql
SELECT lab_api.format_id(42::integer);
SELECT lab_api.format_id(42::bigint);
```

Đối với routine nhạy cảm, ghi **đầy đủ schema và kiểu tham số trong GRANT/REVOKE**. Việc thêm một overload sau này có thể mở ra một đường gọi khác với ACL/default privileges riêng.

### 9.1. Quyền trên procedure không dùng cú pháp SELECT function

PostgreSQL:

```sql
-- Function
GRANT EXECUTE ON FUNCTION lab_api.format_id(integer)
TO lab_routine_caller;

-- Procedure giả định đã tồn tại
GRANT EXECUTE ON PROCEDURE lab_api.process_batch(integer)
TO lab_routine_caller;
```

Gọi tương ứng:

```sql
SELECT lab_api.format_id(42);
CALL lab_api.process_batch(42);
```

Các chữ ký và return type khác nhau theo loại routine. Khi xem SQL GRANT, không được nhầm số lượng tham số default, `IN`/`OUT` và tên overload.

## 10. PostgreSQL: procedure SECURITY DEFINER và giao dịch

PostgreSQL phân biệt **function** và **procedure** về cách gọi và giới hạn quản lý transaction.

Một function SQL/PLpgSQL thông thường không thể tùy ý `COMMIT`/`ROLLBACK` transaction của caller.

Procedure được gọi qua `CALL` có khả năng điều khiển transaction trong **một số điều kiện nhất định**, như cách gọi ở top level và các giới hạn khác của PostgreSQL. Nhưng tài liệu PostgreSQL có quy tắc quan trọng:

> **Procedure được khai báo `SECURITY DEFINER` không được thực thi các câu điều khiển transaction như `COMMIT`/`ROLLBACK`.**

Ngoài ra, procedure có một mệnh đề `SET configuration_parameter` được gắn trong định nghĩa cũng bị giới hạn về transaction control.

Vì thế, không làm:

```sql
-- Chỉ là mô tả ý định không được phép:
-- CREATE PROCEDURE api.do_everything()
-- SECURITY DEFINER
-- AS ... COMMIT ...;
```

rồi kỳ vọng nó vừa nâng quyền vừa tự commit các bước. Thiết kế nên tách **quyền nghiệp vụ** và **ranh giới transaction**: caller hoặc tầng điều phối kiểm soát commit/rollback theo các quy tắc PostgreSQL.

## 11. RLS: có quyền SELECT bảng vẫn có thể không thấy mọi hàng

**Row-Level Security (RLS)** của PostgreSQL giới hạn các hàng mà một role được phép đọc hoặc sửa theo policy.

Ví dụ ý tưởng về bảng nhiều tenant:

```sql
ALTER TABLE app_data.orders ENABLE ROW LEVEL SECURITY;
```

Sau đó DBMS cần các policy phù hợp với role, thao tác và tenant context. Người dùng có `SELECT` bảng nhưng không có policy cho các hàng nhất định có thể chỉ thấy một tập con.

### 11.1. SECURITY DEFINER có thể làm thay đổi role áp RLS

Một function `SECURITY DEFINER` chạy với quyền của **chủ function**. Vì vậy RLS được đánh giá theo execution context tương ứng, có thể rất khác caller.

Điểm đặc biệt:

- **Chủ sở hữu bảng** trong PostgreSQL thường **bỏ qua RLS**, trừ khi bảng dùng `FORCE ROW LEVEL SECURITY` trong phạm vi áp dụng.
- Role có quyền `BYPASSRLS` hoặc superuser có thể bỏ qua RLS theo quy tắc PostgreSQL.
- Một routine definer có owner rất mạnh có thể vô tình trả hàng vượt giới hạn của caller.

Nếu hệ thống dựa vào RLS để tách tenant, phải kiểm tra **owner của bảng**, **owner của routine**, **FORCE RLS**, **BYPASSRLS** và cách routine xác minh identity. Đừng nghĩ chỉ cần bật RLS là mọi `SECURITY DEFINER` tự tuân thủ policy của người gọi.

### 11.2. Không dựa vào custom setting do client tự chọn

Một mẫu thường thấy:

```sql
SELECT current_setting('app.tenant_id', true);
```

Nếu ứng dụng cho client tùy ý gửi `SET app.tenant_id = ...`, giá trị đó **không phải bằng chứng tenant đã được xác thực**. Một custom GUC chỉ an toàn làm tenant context khi đường thiết lập/ủy quyền được kiểm soát chặt chẽ và người dùng không có đường tự đặt giá trị tùy ý.

Trong connection pool, cũng cần đặt lại context mỗi request/transaction để tránh rò tenant giữa những lần tái sử dụng kết nối.

### 11.3. RLS và CHECK OPTION không phải cùng chuyện

`WITH CHECK OPTION` trên view kiểm tra một hàng sau INSERT/UPDATE qua view có còn thuộc tập view không. RLS `USING`/`WITH CHECK` áp các chính sách truy cập hàng ở **bảng** theo role tương ứng.

Một SECURITY DEFINER function có thể tương tác với view, bảng và RLS theo nhiều cơ chế. Vì vậy phải phân tích **từng lớp** thay vì gọi chung tất cả là “check quyền”.

## 12. MySQL: SQL SECURITY DEFINER và INVOKER

MySQL hỗ trợ stored routines với thuộc tính:

```sql
SQL SECURITY DEFINER
```

hoặc:

```sql
SQL SECURITY INVOKER
```

**Mặc định MySQL là `DEFINER`** nếu không ghi thuộc tính, khác với mặc định `INVOKER` của PostgreSQL.

### 12.1. Tài khoản DEFINER là user@host

MySQL dùng định danh account dạng:

```text
'api_owner'@'localhost'
'app_caller'@'%'
```

Phần host có ý nghĩa trong mô hình account của MySQL. Không suy rằng `'api_owner'@'localhost'` và `'api_owner'@'%'` là một tài khoản.

Khi tạo stored routine:

```sql
CREATE DEFINER = 'api_owner'@'localhost'
PROCEDURE demo_app.read_payment(IN p_payment_id BIGINT)
SQL SECURITY DEFINER
BEGIN
    SELECT amount
    FROM demo_app.payments
    WHERE payment_id = p_payment_id;
END;
```

Đây là mẫu **logic SQL của MySQL**; trong mysql command-line client, routine body có dấu chấm phẩy thường cần đổi delimiter tạm:

```sql
-- Chạy bằng mysql CLI; DELIMITER là lệnh của client, không phải SQL server.
DELIMITER //

CREATE DEFINER = 'api_owner'@'localhost'
PROCEDURE demo_app.read_payment(IN p_payment_id BIGINT)
SQL SECURITY DEFINER
BEGIN
    SELECT amount
    FROM demo_app.payments
    WHERE payment_id = p_payment_id;
END//

DELIMITER ;
```

Giả định:

- Tài khoản `api_owner` tồn tại và có quyền `SELECT` bảng `demo_app.payments`.
- Người tạo procedure có quyền tạo routine và đặt DEFINER phù hợp theo phiên bản MySQL.
- Tài khoản definer có `EXECUTE` nếu quy tắc engine yêu cầu; MySQL thường có cơ chế tự cấp một số routine privileges khi tạo, tùy cấu hình.

### 12.2. GRANT EXECUTE cho người gọi

```sql
-- MySQL: người quản trị cấp quyền trên PROCEDURE.
GRANT EXECUTE
ON PROCEDURE demo_app.read_payment
TO 'app_caller'@'%';
```

Sau đó caller có thể:

```sql
CALL demo_app.read_payment(1);
```

Nếu procedure dùng `SQL SECURITY DEFINER`, phần SELECT bên trong được kiểm tra theo quyền của definer. Caller không nhất thiết cần `SELECT` trực tiếp bảng nguồn.

**Tuy nhiên**, procedure ví dụ có cùng vấn đề với PostgreSQL: caller có thể gửi ID bất kỳ. Cần kiểm tra quyền đối với bản ghi/tenant trong routine.

### 12.3. SQL SECURITY INVOKER

```sql
-- MySQL, biểu diễn cấu trúc.
CREATE PROCEDURE demo_app.read_payment_as_caller(IN p_payment_id BIGINT)
SQL SECURITY INVOKER
BEGIN
    SELECT amount
    FROM demo_app.payments
    WHERE payment_id = p_payment_id;
END;
```

Người gọi cần:

- Quyền `EXECUTE` trên procedure.
- Quyền thích hợp trên bảng và đối tượng được truy cập lúc thực thi theo quy tắc MySQL.

Nếu thiếu quyền đọc bảng, câu `CALL` có thể lỗi trong thân routine dù quyền EXECUTE đã được cấp.

### 12.4. Khi tài khoản DEFINER không còn tồn tại

Một routine `SQL SECURITY DEFINER` phụ thuộc vào tài khoản definer theo định nghĩa của nó. Nếu tài khoản bị xóa/đổi trong quá trình migration hoặc restore từ môi trường khác, routine có thể trở thành **orphan stored object** và gặp lỗi khi chạy vì definer không còn tồn tại hoặc không hợp lệ.

Do đó, backup/restore schema cần có chính sách tài khoản dịch vụ và definer rõ ràng; đừng sao chép routine có `DEFINER='root'@'old-host'` từ production cũ rồi mong nó hoạt động và an toàn trên môi trường mới.

### 12.5. Chỉ được chỉ định DEFINER khi có quyền

Không phải ai cũng được tạo routine với `DEFINER` là tài khoản khác hoặc tài khoản có quyền đặc biệt. MySQL 8.x có các quyền như `SET_USER_ID` (và thay đổi/các privilege tương ứng theo phiên bản) cùng kiểm tra liên quan `SYSTEM_USER`.

Đối với người học, nguyên tắc là: **việc chỉ định chủ thể thực thi không phải cách tự ý leo thang quyền**; DBMS phải kiểm tra người tạo có quyền chọn definer đó không.

### 12.6. Triggers/events không giống routines

MySQL cho `SQL SECURITY DEFINER/INVOKER` với procedures, functions và views phù hợp. Triggers và events **không có cùng lựa chọn SQL SECURITY**; chúng thường chạy trong definer context theo quy tắc MySQL.

Không suy từ cú pháp của stored procedure sang mọi stored object khác.

## 13. MariaDB: cũng có DEFINER/INVOKER, nhưng đừng đồng nhất mọi phiên bản

MariaDB hỗ trợ những ý tưởng tương tự:

```sql
SQL SECURITY DEFINER
SQL SECURITY INVOKER
```

và có khái niệm definer account cho routines. Trong nhiều cấu hình, mặc định là definer context nếu không ghi rõ.

Ví dụ:

```sql
-- MariaDB: cấu trúc minh họa, cần phù hợp schema và tài khoản.
CREATE PROCEDURE demo_app.read_payment(IN p_payment_id BIGINT)
SQL SECURITY INVOKER
BEGIN
    SELECT amount
    FROM demo_app.payments
    WHERE payment_id = p_payment_id;
END;
```

Cũng có thể dùng `GRANT EXECUTE ON PROCEDURE ...`/`ON FUNCTION ...` theo cú pháp MariaDB.

Những điểm cần kiểm tra khi chuyển MySQL sang MariaDB:

- Quyền tạo/đổi definer.
- Tài khoản definer có tồn tại trong môi trường đích không.
- Vai trò của **role đang active** và quyền đối tượng.
- Phiên bản và cú pháp stored routine.
- Quyền metadata như xem định nghĩa routine.
- Tác động khi restore/dump mang theo definer của môi trường nguồn.

Kể cả khi hai DBMS nhận cùng một câu `SQL SECURITY DEFINER`, phiên bản và mô hình account/role có thể khác. Hãy đối chiếu tài liệu DBMS đang vận hành thay vì coi MariaDB chỉ là một nhãn khác của MySQL.

## 14. SQL Server: GRANT EXECUTE, EXECUTE AS và ownership chaining

SQL Server Database Engine có một mô hình quan trọng: **permissions trên module**, **execution context** và **ownership chaining** tương tác với nhau.

### 14.1. Cấp quyền gọi stored procedure

Giả sử đã có procedure:

```sql
EXEC app.usp_GetPayment @payment_id = 1;
```

Cấp quyền:

```sql
GRANT EXECUTE ON OBJECT::app.usp_GetPayment
TO app_reader;
```

`OBJECT::app.usp_GetPayment` xác định routine trong schema. Có thể cấp quyền phạm vi rộng hơn:

```sql
-- SQL Server: quyền rất rộng, chỉ dùng nếu thật sự chủ đích.
GRANT EXECUTE ON SCHEMA::app
TO app_reader;
```

Nhưng grant cấp schema có thể cho gọi **nhiều procedure/function hiện tại và tương lai** trong schema, nên không nên dùng như giải pháp nhanh cho một routine cụ thể nhạy cảm.

### 14.2. Mặc định EXECUTE AS CALLER

Với procedure thông thường, SQL Server dùng context caller nếu không chỉ định execution context khác.

Ví dụ:

```sql
-- SQL Server: giả sử schema app và data đã tồn tại.
CREATE OR ALTER PROCEDURE app.usp_GetPayment
    @payment_id BIGINT
WITH EXECUTE AS CALLER
AS
BEGIN
    SET NOCOUNT ON;

    SELECT p.amount
    FROM data.payments AS p
    WHERE p.payment_id = @payment_id;
END;
```

Tuy nhiên, **không** được kết luận rằng caller luôn phải có `SELECT` trên `data.payments` để câu SQL tĩnh bên trong chạy: SQL Server có **ownership chaining**.

### 14.3. Ownership chaining: vì sao caller thiếu SELECT vẫn gọi được?

Giả sử:

- Procedure `app.usp_GetPayment` thuộc cùng owner với bảng `data.payments` (dù khác schema).
- Caller được cấp `EXECUTE` trên procedure.
- Procedure sử dụng một câu `SELECT` tĩnh hợp lệ tới bảng.
- Ownership chain giữa module và bảng **không bị đứt**.

Trong trường hợp này, SQL Server có thể **bỏ qua kiểm tra quyền riêng trên bảng nguồn** cho câu DML đó. Caller được phép thực thi logic trong module dù không có `SELECT` trực tiếp bảng.

Đây là cơ chế *ownership chaining*, **không phải** ý nghĩa giống `SECURITY DEFINER` của PostgreSQL hoặc `SQL SECURITY DEFINER` của MySQL.

Giới hạn quan trọng:

- Chuỗi sở hữu phải thỏa quy tắc **cùng owner** của các đối tượng.
- Quy tắc này chủ yếu áp với truy cập DML thông qua chuỗi module.
- **Dynamic SQL** trong module **không được tự động bảo vệ bởi ownership chaining** theo cùng cách.
- Các thao tác/đối tượng ngoài chuỗi sở hữu cần kiểm tra quyền riêng theo execution context.

Một thay đổi owner/schema của một bảng có thể làm **đứt ownership chain** và khiến procedure vốn chạy trước đây bắt đầu báo lỗi permission.

### 14.4. EXECUTE AS OWNER

SQL Server có thể khai báo:

```sql
CREATE OR ALTER PROCEDURE app.usp_GetPaymentAsOwner
    @payment_id BIGINT
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;

    SELECT p.amount
    FROM data.payments AS p
    WHERE p.payment_id = @payment_id;
END;
```

Caller vẫn cần `EXECUTE` trên procedure, nhưng mã bên trong chạy với execution context được thiết lập theo **owner**.

Các tùy chọn context SQL Server có thể gồm `CALLER`, `SELF`, `OWNER` hoặc một database user được chỉ định, tùy loại module. Không phải mọi đối tượng SQL Server đều hỗ trợ mọi tùy chọn; inline table-valued functions có ngoại lệ đáng chú ý đối với `EXECUTE AS`.

**Nguy cơ:** nếu owner có quyền rộng và procedure cho caller điều khiển arbitrary SQL, schema hoặc tên bảng, caller có thể vượt phạm vi nghiệp vụ.

### 14.5. Dynamic SQL làm thay đổi kiểm tra quyền

```sql
-- SQL Server: ví dụ chống chỉ định nếu dùng với input không tin cậy.
DECLARE @sql nvarchar(max) = N'SELECT * FROM ' + @table_name;
EXEC(@sql);
```

Một chuỗi dynamic SQL không tự thừa hưởng ownership chain của câu `SELECT` tĩnh. Khi thực thi, SQL Server kiểm tra quyền theo context có hiệu lực (`EXECUTE AS` nếu có) và các cơ chế khác.

Để an toàn:

- Không cho người gọi gửi một đoạn SQL tùy ý.
- Dùng `sp_executesql` và tham số cho **giá trị**.
- Dùng `QUOTENAME` và danh sách cho phép cho **định danh bảng/cột**, nhưng nhớ quoting không phải authorization.
- Cấp quyền tối thiểu cho owner/context.
- Cân nhắc **module signing bằng certificate** khi cần thêm quyền có phạm vi hẹp mà không đổi execution context của toàn module.

### 14.6. Cross-database access là lớp riêng

Một procedure trong database A cần đọc bảng của database B có thể gặp những giới hạn của execution context, trust boundary và quyền cross-database. Không bật `TRUSTWORTHY ON` hay cross-database ownership chaining rộng chỉ để chữa lỗi quyền.

Cơ chế module signing bằng certificate, quyền được cấp đúng phạm vi hoặc thiết kế API/staging có thể phù hợp hơn. Những lựa chọn đó cần người quản trị đánh giá theo topology SQL Server đang dùng.

### 14.7. Scalar function và table-valued function không giống quyền gọi

Trong SQL Server:

| Đối tượng | Quyền thông dụng |
|---|---|
| Stored procedure | `EXECUTE` |
| Scalar user-defined function | `EXECUTE` |
| Table-valued function được query như một quan hệ | `SELECT` trên object |
| Bảng/view | `SELECT`, `INSERT`, `UPDATE`, `DELETE` tùy nhu cầu |

Ví dụ:

```sql
-- Scalar function: quyền EXECUTE.
GRANT EXECUTE ON OBJECT::app.fn_CalculateTax
TO app_reader;

-- Table-valued function: quyền SELECT.
GRANT SELECT ON OBJECT::app.fn_VisibleOrders
TO app_reader;
```

Đừng cấp `EXECUTE` cho mọi function chỉ vì các DBMS khác dùng từ EXECUTE rộng hơn; kiểm tra **loại routine** và cách gọi trong SQL Server.

## 15. Oracle Database: AUTHID DEFINER và AUTHID CURRENT_USER

Oracle PL/SQL dùng thuộc tính:

```sql
AUTHID DEFINER
```

hoặc:

```sql
AUTHID CURRENT_USER
```

- **`AUTHID DEFINER`:** definer's rights; mặc định phổ biến của stored PL/SQL routines.
- **`AUTHID CURRENT_USER`:** invoker's rights; context thực thi theo người gọi và các quy tắc role/name resolution tương ứng.

### 15.1. Một function definer's rights

Giả sử có bảng `API_OWNER.PAYMENTS`. Khi đăng nhập bằng schema owner hoặc thực thi bằng quyền thích hợp:

```sql
-- Oracle Database
CREATE OR REPLACE FUNCTION api_owner.payment_amount (
    p_payment_id IN NUMBER
)
RETURN NUMBER
AUTHID DEFINER
IS
    v_amount NUMBER;
BEGIN
    SELECT amount
      INTO v_amount
      FROM api_owner.payments
     WHERE payment_id = p_payment_id;

    RETURN v_amount;
END;
/
```

Trong SQL*Plus/SQLcl, dấu `/` ở cuối là lệnh client gửi block PL/SQL vừa nhập, không phải dấu cú pháp routine có thể đưa nguyên vào mọi JDBC statement.

Cấp quyền gọi:

```sql
GRANT EXECUTE ON api_owner.payment_amount
TO app_caller;
```

Người gọi có thể:

```sql
SELECT api_owner.payment_amount(1) AS amount
FROM dual;
```

Nếu function có quyền và hành vi phù hợp, `app_caller` không nhất thiết cần `SELECT` trực tiếp bảng `api_owner.payments`.

### 15.2. Role được cấp gián tiếp thường không đủ cho definer's rights PL/SQL

Oracle có quy tắc bảo mật quan trọng: khi chạy **named PL/SQL unit** ở chế độ **definer's rights**, các role thông thường bị **disable** trong thân unit. Quyền cần thiết để đọc bảng của schema khác thường phải được **GRANT trực tiếp cho owner** của routine, không chỉ qua một role.

Ví dụ:

```sql
-- Oracle: được thực hiện bởi chủ bảng data_owner.
GRANT SELECT ON data_owner.payments
TO api_owner;
```

Nếu chỉ:

```sql
GRANT SELECT ON data_owner.payments
TO reporting_role;

GRANT reporting_role TO api_owner;
```

thì user `api_owner` có thể SELECT khi tương tác trực tiếp trong session với role đang bật, nhưng PL/SQL definer-rights unit của `api_owner` vẫn có thể **không compile/chạy được** cho truy cập tĩnh do thiếu **direct object grant**.

Điểm này khác một số hệ có mô hình role inheritance/ownership chaining; không áp một quy tắc permission chung cho mọi stored program.

### 15.3. AUTHID CURRENT_USER: dùng quyền invoker

```sql
-- Oracle: ví dụ function invoker's rights.
CREATE OR REPLACE FUNCTION api_owner.payment_amount_as_caller (
    p_payment_id IN NUMBER
)
RETURN NUMBER
AUTHID CURRENT_USER
IS
    v_amount NUMBER;
BEGIN
    SELECT amount
      INTO v_amount
      FROM api_owner.payments
     WHERE payment_id = p_payment_id;

    RETURN v_amount;
END;
/
```

Khi `app_caller` gọi, phần truy cập bảng có thể yêu cầu **quyền tương ứng của app_caller**, không phải quyền đọc bảng chỉ có ở api_owner.

Phân giải tên ở Oracle còn phụ thuộc `CURRENT_SCHEMA` và bối cảnh lập trình. Bài dùng `api_owner.payments` tường minh để giảm nhầm lẫn giữa tên bảng ở schema người gọi và schema người định nghĩa.

**Lưu ý:** `AUTHID` ảnh hưởng quyền và name resolution **ở runtime**; quá trình **compile** chương trình PL/SQL vẫn có những yêu cầu về đối tượng mẫu/metadata và direct grants cho chủ routine.

### 15.4. INHERIT PRIVILEGES trong Oracle 12c+

Oracle 12c trở lên có cơ chế **`INHERIT PRIVILEGES`** và `INHERIT ANY PRIVILEGES` để bảo vệ tình huống invoker-rights unit dùng quyền của một chủ thể gọi có nhiều quyền hơn.

Ví dụ cấp khả năng kế thừa từ một user cho chủ routine:

```sql
-- Oracle: cú pháp ý tưởng, thực hiện bởi người có quyền cấp.
GRANT INHERIT PRIVILEGES ON USER app_caller
TO api_owner;
```

Nếu owner của invoker-rights unit không được phép kế thừa quyền của caller theo quy tắc đang áp dụng, lời gọi có thể lỗi như `ORA-06598`. Quy tắc này nhằm ngăn owner của mã do người khác gọi **âm thầm chạy dưới những quyền không được phép kế thừa**.

Không cấp `INHERIT ANY PRIVILEGES` quá rộng chỉ để một function chạy; ưu tiên giải quyết theo user/nhu cầu cụ thể.

### 15.5. Package: quyền thường cấp ở cấp package

Oracle có **package** chứa nhiều thủ tục/hàm công khai:

```text
api_owner.billing_api
    .get_summary(...)
    .refund_payment(...)
    .export_history(...)
```

Một `GRANT EXECUTE ON api_owner.billing_api TO app_caller` thường cho phép gọi các thành viên công khai của package theo phạm vi quyền package, **không có cơ chế GRANT EXECUTE tách riêng từng procedure nằm bên trong package như các đối tượng độc lập thông thường**.

Nếu chỉ muốn bộ phận báo cáo gọi `get_summary` nhưng không được gọi `refund_payment`, cần thiết kế **package/API phân tách trách nhiệm** hoặc wrapper có điều kiện và role/privilege phù hợp. Đừng đặt mọi tác vụ nhạy cảm cùng một package rồi cấp EXECUTE cho mọi người.

### 15.6. Oracle: định nghĩa definer là contract vận hành

Khi schema owner bị đổi, quyền direct grants bị thu hồi hoặc object phụ thuộc thay đổi, routine có thể invalid hoặc thất bại khi chạy. Những tình huống này không được xử lý chỉ bằng việc giữ `GRANT EXECUTE` trên tên function.

Kiểm tra dependency, object invalidation/recompile, privilege compile và quyền runtime khi deploy migration.

## 16. SQLite: không có GRANT EXECUTE cho stored procedure thuần SQL

SQLite là thư viện cơ sở dữ liệu nhúng, **không có hệ thống account/role và stored procedure được quản lý bởi server SQL giống PostgreSQL/MySQL/Oracle/SQL Server**.

SQLite hỗ trợ:

- Câu SQL thông thường, view và trigger.
- **Application-defined SQL functions** do chương trình đăng ký trên connection bằng API, chẳng hạn `sqlite3_create_function()`.
- Hooks/authorizer như `sqlite3_set_authorizer()` để ứng dụng kiểm soát một số hành vi theo connection.
- Quyền truy cập file/database do hệ điều hành, sandbox và ứng dụng quản lý.

Vì vậy, không dùng:

```sql
-- Không phải cú pháp SQL SQLite:
GRANT EXECUTE ON FUNCTION calculate_fee TO app_reader;
```

Một ứng dụng mở file SQLite thường có khả năng đọc/sửa dữ liệu theo quyền truy cập file và chính sách do ứng dụng áp dụng, chứ không được engine cấp role SQL độc lập cho mỗi người dùng.

### 16.1. Application-defined function không tự có ACL SQL

Giả sử ứng dụng C/Python/Java đăng ký hàm `calculate_fee(amount)` với SQLite. Khi connection thực hiện:

```sql
SELECT calculate_fee(100);
```

hàm chạy trong **tiến trình và môi trường của ứng dụng** đã đăng ký nó, với những quyền hệ điều hành và tài nguyên ứng dụng có. Không có tương đương trực tiếp với `AUTHID CURRENT_USER` hay `SQL SECURITY DEFINER` của stored routine server.

### 16.2. Đánh giá rủi ro hàm có side effect

Nếu một app-defined function có thể đọc file, gọi mạng hoặc thay đổi trạng thái ngoài DB, người dùng có quyền gửi SQL tùy ý có thể tìm cách gọi nó trong những biểu thức/view/trigger mà ứng dụng không ngờ đến.

SQLite hỗ trợ các cờ/khả năng như `SQLITE_DIRECTONLY`, `SQLITE_INNOCUOUS` và cấu hình `trusted_schema` trong những phiên bản phù hợp để hạn chế nơi function được gọi. Các cơ chế này không thay thế việc **không cho người dùng không tin cậy gửi SQL tùy ý** và không tự tạo ACL per-user tại lớp engine.

### 16.3. Muốn API có phân quyền trên SQLite thì thiết kế ở ứng dụng

Một kiến trúc phổ biến:

```text
Người dùng -> API xác thực -> kiểm tra role/tenant
           -> dịch vụ nghiệp vụ -> SQL tham số hóa
           -> tệp SQLite được app quản lý
```

Không để người dùng cuối truy cập trực tiếp tệp SQLite chứa dữ liệu của người khác nếu mục tiêu là tách quyền theo tenant. Chỉ thêm view và trigger không cung cấp đầy đủ phân quyền từng user khi người dùng có thể mở file và chạy SQL trực tiếp.

## 17. Bảng so sánh mặc định theo hệ quản trị

| DBMS | Quyền gọi thường gặp | Mặc định execution context của stored routine | Cơ chế đặc biệt |
|---|---|---|---|
| **PostgreSQL** | `EXECUTE` trên function/procedure, thêm `USAGE` schema | **`SECURITY INVOKER`** | `SECURITY DEFINER`, ACL `PUBLIC`, `search_path`, RLS |
| **MySQL** | `EXECUTE` trên procedure/function | **`SQL SECURITY DEFINER`** | Account `user@host`, definer tồn tại ở runtime, role |
| **MariaDB** | `EXECUTE` | Thông thường **`SQL SECURITY DEFINER`** | Quyền/definer theo phiên bản MariaDB |
| **SQL Server** | `EXECUTE` trên procedure/scalar function; `SELECT` trên TVF | **`EXECUTE AS CALLER`** thông thường | **Ownership chaining**, `EXECUTE AS OWNER/SELF/user`, module signing |
| **Oracle** | `EXECUTE` trên function/procedure/package | **`AUTHID DEFINER`** | Direct grants/roles disabled trong definer PL/SQL, `INHERIT PRIVILEGES` |
| **SQLite** | Không có GRANT EXECUTE server-side tương đương | Không áp dụng | Hàm do ứng dụng đăng ký, OS/app controls |

Bảng chỉ mô tả **stored routines trong phạm vi mỗi engine**. View, trigger, event, DDL, linked server, external function hoặc ngôn ngữ mở rộng có thể dùng cơ chế khác.

## 18. Quyền gọi không phải quyền sửa định nghĩa routine

Một role có `EXECUTE` thường có thể **gọi** routine theo hợp đồng, nhưng không đồng nghĩa có quyền:

- `CREATE OR REPLACE FUNCTION/PROCEDURE`.
- `ALTER` owner, security context hoặc cấu hình.
- `DROP` routine.
- `GRANT EXECUTE` cho người khác.
- `CREATE` một routine mới trong schema tin cậy.
- Đọc mọi dữ liệu bảng nền hoặc xem toàn bộ source code nếu quyền metadata được hạn chế.

Tùy DBMS, chủ đối tượng hoặc role có đặc quyền cao hơn có thể sửa định nghĩa và phân quyền. Vì vậy bảo vệ **quyền ALTER/DROP/CREATE trên schema API** là quan trọng ngang bảo vệ cổng EXECUTE.

### 18.1. Rủi ro “được CREATE trong schema đáng tin”

Trong PostgreSQL, nếu caller được tạo object trong schema xuất hiện trong `search_path` của definer function, họ có thể tạo object trùng tên để ảnh hưởng name resolution. Nếu được tạo/đổi routine API cùng tên, đó còn có thể là một vấn đề integrity/deployment.

Hạn chế `CREATE` trong schema chứa các đối tượng đặc quyền; dùng tài khoản triển khai riêng, không dùng tài khoản request của ứng dụng để chạy migration DDL.

## 19. Nested routines: khi một routine gọi routine khác

Một ứng dụng có thể có chuỗi:

```text
app_user
   |
   +--> api.get_summary()      -- người dùng được gọi
              |
              +--> private.calc_balance()
                         |
                         +--> private.payments table
```

Không suy rằng quyền **người đăng nhập ban đầu** được dùng ở mọi tầng.

### 19.1. PostgreSQL: context có thể thay đổi trong stack

Khi `api.get_summary()` là `SECURITY DEFINER`, trong function đó `current_user` phản ánh chủ routine. Nếu function tiếp tục gọi một function `SECURITY INVOKER`, invoker context có thể là **effective user hiện tại**, tức chủ của definer function ngoài, không nhất thiết là session login ban đầu.

Vì vậy, một function invoker nằm sâu trong call stack không tự bảo đảm đang áp quyền của người dùng API gốc. Cần xem **chuỗi lời gọi**, không chỉ thuộc tính của routine cuối cùng.

### 19.2. SQL Server: ownership chain có thể bị đứt

Khi procedure A gọi procedure B, rồi B truy cập bảng, SQL Server xét quyền/ownership chain của các đối tượng liên quan. Một khâu khác owner hoặc SQL động có thể làm permission check thay đổi.

Đừng chữa lỗi bằng cấp `db_owner` hoặc `sysadmin` cho tài khoản ứng dụng; xác định đúng mắt xích thiếu quyền.

### 19.3. Oracle: AUTHID và nested calls

Trong Oracle, `AUTHID DEFINER`/`CURRENT_USER` có ảnh hưởng đến `CURRENT_USER`, `CURRENT_SCHEMA` và quyền trong các unit được gọi tiếp. Khi refactor package/procedure, cần kiểm tra contract của mỗi tầng và đặc biệt là role behavior.

## 20. SQL động: ba loại rủi ro cần phân biệt

Routine quyền cao thường cần xây câu SQL động. Có ba vấn đề độc lập:

1. **SQL injection:** dữ liệu người dùng trở thành cú pháp SQL.
2. **Object selection abuse:** dù tên bảng được quote đúng, caller vẫn có thể yêu cầu truy cập đối tượng không được phép.
3. **Privilege context abuse:** câu SQL chạy dưới chủ thể quyền cao hơn caller.

Ví dụ pseudocode không an toàn:

```text
function export_table(table_name):
    sql = "SELECT * FROM " + table_name
    execute(sql)  -- bên trong routine definer
```

Một caller có thể chọn bảng `private.salary` nếu routine owner có quyền. Đây vẫn là lỗi **ủy quyền đối tượng** dù escaping không cho SQL injection.

### 20.1. Nguyên tắc xử lý

- **Không nhận arbitrary SQL** từ người gọi ở một definer routine.
- **Giới hạn đối tượng cho phép** bằng danh sách rõ ràng và mapping tên nghiệp vụ → tên schema.table được kiểm soát.
- Dùng tham số bind cho **giá trị**, không nối literal tùy ý.
- Dùng cơ chế quote identifier của DBMS cho **tên đối tượng** khi thực sự cần dynamic identifier.
- Kiểm tra tenant/record authorization bằng identity được xác thực.
- Cấp owner quyền **hẹp nhất**, không dùng superuser nếu không cần.
- Không dùng dynamic SQL nếu SQL tĩnh đã giải quyết được bài toán.

### 20.2. PostgreSQL: format và USING không tự giải quyết quyền

Một ví dụ an toàn hơn về cú pháp PL/pgSQL:

```sql
-- Minh họa kỹ thuật, không phải hàm cho phép chọn bảng tùy ý.
EXECUTE format(
    'SELECT count(*) FROM %I.%I WHERE tenant_id = $1',
    trusted_schema_name, allowlisted_table_name
)
INTO row_count
USING authorized_tenant_id;
```

`%I` quote định danh và `USING` bind **giá trị**. Nhưng `trusted_schema_name` và `allowlisted_table_name` **vẫn phải được authorization/allowlist**, và `authorized_tenant_id` phải có nguồn tin cậy. Quote đúng không biến một SELECT trên bảng cấm thành hợp lệ về nghiệp vụ.

## 21. Nguyên tắc least privilege khi thiết kế routine

**Least privilege**: cấp chỉ những quyền tối thiểu cần để routine hoàn thành nhiệm vụ.

Một mô hình tốt cho hệ thống nhiều dịch vụ:

```text
role app_login
  |
  +-- USAGE api schema
  +-- EXECUTE api.get_my_balance()
  +-- EXECUTE api.submit_order()
  |
  x-- không SELECT private.accounts trực tiếp
  x-- không UPDATE private.payments trực tiếp
  x-- không CREATE trong api/private schema

role api_owner (NOLOGIN / chủ routine)
  |
  +-- SELECT các cột cần từ private.accounts
  +-- UPDATE những cột cụ thể ở private.orders
  |
  x-- không SUPERUSER/sysadmin
  x-- không CREATE ROLE
  x-- không truy cập ngoài phạm vi nhiệm vụ
```

### 21.1. Phân role đọc và ghi

Một role chỉ xem số dư không nên có quyền gọi routine hoàn tiền hoặc cập nhật tài khoản:

| Role | Routine được gọi | Quyền bảng trực tiếp |
|---|---|---|
| `report_reader` | `api.get_summary` | Không cần nếu definer wrapper đúng |
| `order_operator` | `api.submit_order` | Không cần mở rộng tùy tiện |
| `payment_operator` | `api.refund_payment` theo hạn mức | Không phải mọi role |
| `migration_owner` | Không dùng trong request thông thường | Quyền DDL khi triển khai |

Nếu tất cả đều được `EXECUTE ON ALL ROUTINES IN SCHEMA api`, nguyên tắc phân quyền theo API có thể bị phá vỡ.

### 21.2. Đầu vào routine phải có authorization cụ thể

Đây là một bài học quan trọng: **khả năng gọi function không đồng nghĩa quyền xử lý mọi đối tượng mà tham số chỉ tới**.

Ví dụ:

```sql
-- Function nguy hiểm về logic nếu không xác thực phạm vi:
SELECT api.refund_payment(999999, 1000000);
```

Caller có EXECUTE trên `refund_payment` không có nghĩa họ được hoàn tiền bất kỳ giao dịch hay số tiền nào.

Routine cần:

- Kiểm tra identity/tenant được xác thực.
- Xác định bản ghi đích thuộc phạm vi caller được phép.
- Kiểm tra trạng thái hợp lệ, hạn mức, chống replay/idempotency.
- Giới hạn số hàng tác động và kiểm tra affected rows.
- Ghi audit actor, request ID và kết quả.
- Thực thi transaction/locking phù hợp khi có cạnh tranh ghi.

Không lấy `user_id` do client đưa vào làm bằng chứng “người gọi là user_id đó”.

## 22. Kiểm tra quyền và audit theo DBMS

### 22.1. PostgreSQL: kiểm tra quyền cụ thể

```sql
-- PostgreSQL: sau khi tạo các role/schema trong phần lab.
SELECT has_schema_privilege(
    'lab_routine_caller',
    'lab_api',
    'USAGE'
) AS can_use_api_schema;

SELECT has_function_privilege(
    'lab_routine_caller',
    'lab_api.payment_amount(bigint)',
    'EXECUTE'
) AS can_call_function;

SELECT has_table_privilege(
    'lab_routine_caller',
    'lab_data.payments',
    'SELECT'
) AS can_read_table;
```

Trong bối cảnh lab, ba kết quả kỳ vọng: **TRUE**, **TRUE**, **FALSE** (với điều kiện không có grant/role kế thừa ngoài bài thử).

Có thể kiểm tra owner và cờ definer:

```sql
SELECT
    n.nspname AS schema_name,
    p.proname AS routine_name,
    pg_get_userbyid(p.proowner) AS routine_owner,
    p.prosecdef AS is_security_definer
FROM pg_proc AS p
JOIN pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE n.nspname = 'lab_api'
ORDER BY p.proname;
```

`prosecdef = TRUE` cho biết function/procedure dùng definer security context theo metadata PostgreSQL.

### 22.2. MySQL/MariaDB: xem định nghĩa và grants

```sql
-- MySQL/MariaDB: tùy quyền metadata.
SHOW CREATE PROCEDURE demo_app.read_payment;

SHOW GRANTS FOR 'app_caller'@'%';
```

Có thể tra các trường như `DEFINER`, `SECURITY_TYPE` trong các views metadata `information_schema.ROUTINES` khi role đủ quyền. Không hiển thị danh sách definer/quyền nhạy cảm cho người dùng cuối nếu không cần.

### 22.3. SQL Server: permissions và execute context

```sql
-- SQL Server: xem module đã chỉ định EXECUTE AS user nào.
SELECT
    s.name AS schema_name,
    o.name AS object_name,
    m.execute_as_principal_id
FROM sys.sql_modules AS m
JOIN sys.objects AS o ON o.object_id = m.object_id
JOIN sys.schemas AS s ON s.schema_id = o.schema_id
WHERE s.name = 'app'
  AND o.name = 'usp_GetPayment';
```

`execute_as_principal_id` có ý nghĩa metadata riêng (`NULL` thường tương ứng CALLER, các giá trị khác dùng context chỉ định; `-2` có nghĩa OWNER trong tài liệu SQL Server). Phải xem cùng ownership chain và grant thực tế, không chỉ một cột.

SQL Server có các catalog như `sys.database_permissions`, `sys.database_principals` và hàm xem quyền như `fn_my_permissions` để điều tra theo role.

### 22.4. Oracle: AUTHID và object privileges

Trong Oracle, những views dictionary như `USER_PROCEDURES`, `ALL_PROCEDURES`, `DBA_PROCEDURES` và views về object grants như `ALL_TAB_PRIVS`/`DBA_TAB_PRIVS` giúp kiểm tra `AUTHID`, owner và EXECUTE grants. Quyền xem metadata phụ thuộc role quản trị.

Khi routine không compile, kiểm tra **direct grants** cho owner và object dependencies trước khi chỉ nhìn `EXECUTE` của caller.

## 23. Những thông báo lỗi thường gặp và cách chẩn đoán

| Biểu hiện | Nguyên nhân có thể | Bước xem tiếp |
|---|---|---|
| Không tìm thấy function/procedure | Sai schema, chữ ký, search path, object chưa tạo | Kiểm tra object và qualified name |
| PostgreSQL `permission denied for schema` | Thiếu `USAGE` trên schema liên quan | Kiểm tra `has_schema_privilege` |
| PostgreSQL `permission denied for function` | Thiếu `EXECUTE` trên chữ ký routine | Kiểm tra ACL và `PUBLIC` |
| PostgreSQL `permission denied for relation` | Invoker hoặc owner thiếu quyền bảng | Kiểm tra security context và table grants |
| Function definer trả dữ liệu của tenant khác | Logic authorization không lọc tenant đúng | Kiểm tra claim/role/row ownership và RLS |
| MySQL routine có definer không tồn tại | Môi trường đích thiếu account definer | Kiểm tra `SHOW CREATE` và quản lý account |
| SQL Server EXECUTE được nhưng SQL động lỗi | Ownership chain không áp cho dynamic SQL | Kiểm tra execute context và object permissions |
| SQL Server procedure gọi được dù caller không SELECT | Ownership chain cùng owner hoặc `EXECUTE AS` phù hợp | Xem owner của module và bảng |
| Oracle ORA-01031 | Thiếu quyền trực tiếp/hiệu lực hoặc compile quyền | Kiểm tra AUTHID, direct grants, roles |
| Oracle ORA-06598 | Thiếu quyền cho owner kế thừa quyền invoker | Xem `INHERIT PRIVILEGES` |
| Oracle package lộ thêm thao tác nhạy cảm | GRANT EXECUTE ở cấp package quá rộng | Tách package/API và quyền |
| SQLite GRANT EXECUTE lỗi cú pháp | SQLite không có server role/routine ACL như PG | Thiết kế authorization trong app |

Không “sửa lỗi quyền” bằng cấp `ALL PRIVILEGES` hoặc quyền quản trị ngay lập tức. Lỗi permission thường là tín hiệu cần xác định **cổng nào thiếu và liệu thực sự nên cấp hay không**.

## 24. Các sai lầm phổ biến

### 24.1. Đồng nhất người gọi với chủ sở hữu

`GRANT EXECUTE` cho role A không làm A thành owner của routine. Trong definer mode, routine dùng quyền của owner/definer, không phải của A.

### 24.2. Đồng nhất EXECUTE với SELECT bảng

Role có thể gọi wrapper với quyền definer mà vẫn không đọc bảng trực tiếp. Ngược lại, invoker routine có thể lỗi ở lệnh SELECT bên trong dù role có EXECUTE.

### 24.3. Mặc định PostgreSQL giống MySQL/Oracle

Sai: PostgreSQL mặc định SECURITY INVOKER; MySQL và Oracle mặc định definer context cho stored routines tương ứng.

### 24.4. Chỉ kiểm tra PUBLIC GRANT ở bảng

PostgreSQL function mới có thể được cấp EXECUTE cho PUBLIC. Với function definer nhạy cảm, cần thu hồi và cấp lại đúng role.

### 24.5. Để superuser sở hữu mọi routine definer

Một bug SQL injection/authorization trong routine có thể tận dụng quyền rất rộng. Dùng role owner chuyên biệt, không có quyền login nếu phù hợp.

### 24.6. Dùng SET search_path theo client trong definer routine

Một schema không tin cậy hoặc temporary schema có thể shadow tên đối tượng. Gắn `SET search_path` an toàn và schema-qualify các đối tượng nhạy cảm.

### 24.7. Coi tham số tenant_id là xác thực

Client có thể gửi tenant khác. Phải xác định tenant từ context được ứng dụng/DB xác thực, không chỉ từ tham số.

### 24.8. Cấp EXECUTE cả schema hoặc package không phân biệt

Một role cần gọi `get_balance` không có nghĩa được gọi `refund_payment`. Phân tách API và cấp quyền theo routine hoặc package thích hợp.

### 24.9. Bỏ qua ownership chaining của SQL Server

Cách suy “CALLER luôn cần SELECT bảng” không đúng khi có ownership chain cùng owner và các điều kiện phù hợp.

### 24.10. Bỏ qua direct grants trong Oracle PL/SQL

Role được cấp SELECT qua role không nhất thiết có tác dụng trong definer-rights named PL/SQL; owner cần direct privileges phù hợp.

### 24.11. Dùng invoker-rights unit Oracle mà không kiểm tra INHERIT PRIVILEGES

Có thể gặp ORA-06598. Không cấp global `INHERIT ANY PRIVILEGES` tùy tiện để tránh lỗi.

### 24.12. Tin rằng SQLite có cơ chế SQL role như server DBMS

SQLite không hỗ trợ `GRANT EXECUTE` per stored procedure. Bảo vệ phải ở application/OS/connection.

## 25. Kịch bản kiến trúc: chỉ cho lấy tổng chi tiêu của chính người dùng

Giả sử hệ thống lưu:

```text
accounts(account_id, tenant_id, user_id, ...)
payments(payment_id, account_id, amount, ...)
```

Yêu cầu: user chỉ xem tổng chi tiêu của **tài khoản thuộc mình**.

Một API an toàn có thể có giao diện:

```sql
-- Mẫu tên hàm, không phải code hoàn chỉnh:
SELECT api.my_total_spend();
```

Thay vì:

```sql
SELECT api.total_spend_for_user(p_any_user_id);
```

Vì sao?

- Dạng thứ hai cho phép caller chọn ID tùy ý nếu logic bên trong không kiểm tra.
- Dạng thứ nhất khuyến khích routine lấy identity từ context đã xác thực, rồi truy vấn các bảng với điều kiện quyền cụ thể.
- Tuy nhiên, nếu DB connection được chia sẻ giữa nhiều người dùng ứng dụng, routine **không thể chỉ dựa vào SESSION_USER** để phân biệt họ; cần bối cảnh xác thực được truyền/thiết lập an toàn bởi service hoặc giải pháp RLS riêng.
- Với definer routine, phải kiểm tra chính sách hàng của owner và mọi nhánh SQL động.

Quy tắc bảo mật nên được định nghĩa bằng bảng/quan hệ có thể kiểm chứng: ví dụ một mapping `user_account_access` được quản trị bởi dịch vụ, không phải một tham số “tôi có quyền” do client gửi.

### 25.1. Tối giản mặt tiếp xúc (*attack surface*)

Mỗi routine có quyền cao là một điểm vào có thể bị lạm dụng. Nên:

1. Chỉ có tham số được xác định kiểu rõ.
2. Không cho thực thi SQL tự do.
3. Cố định đối tượng và cột được truy cập.
4. Giới hạn tập hàng/kết quả.
5. Kiểm tra trạng thái nghiệp vụ và tenant.
6. Thực hiện transaction và audit đúng chỗ.
7. Dùng owner có quyền tối thiểu.
8. Có test phân quyền với role ít quyền thật, không chỉ test bằng superuser.

## 26. Checklist triển khai theo từng giai đoạn

### 26.1. Trước khi tạo routine

- Xác định **ai được gọi**, trên những tenant/bản ghi nào.
- Xác định **chủ thể thực thi** phù hợp: invoker hay definer.
- Liệt kê các **object dependencies**: schema, bảng, cột, view, routine con, dynamic SQL.
- Xác định các **quyền nhỏ nhất** của execution principal.
- Kiểm tra chính sách RLS, view, trigger và FK.
- Thiết kế error message không tiết lộ dữ liệu nhạy cảm.

### 26.2. Khi CREATE/GRANT

- Đặt tên schema tường minh, tránh routine trùng tên ngoài ý muốn.
- Chỉ rõ SECURITY DEFINER/INVOKER hoặc EXECUTE AS/AUTHID nếu quan trọng.
- Thu hồi mặc định PUBLIC nếu DBMS có quyền rộng mặc định.
- Cấp đúng EXECUTE/SELECT cho **đúng loại routine và chữ ký**.
- Bảo vệ quyền CREATE/ALTER/DROP ở schema API.
- Dùng owner không có quyền cao hơn cần thiết.
- Đảm bảo definer account tồn tại, ổn định qua backup/restore.

### 26.3. Khi test quyền

- Test bằng role **không phải admin**.
- Test cả một lời gọi được phép và một lời gọi bị từ chối.
- Test không có SELECT trực tiếp bảng nguồn.
- Test ID thuộc tenant khác.
- Test tham số NULL, ID không tồn tại, số tiền lớn/âm và chuỗi gây lỗi.
- Test lồng routine, SQL động, search_path và metadata privileges.
- Test concurrent calls, transaction rollback và log audit khi thay đổi dữ liệu.

### 26.4. Khi vận hành

- Theo dõi ai gọi routine, tần suất và số hàng tác động.
- Xoay vòng quyền/definer account khi đổi nhân sự/hạ tầng.
- Kiểm tra quyền mặc định khi tạo overload/routine mới.
- Kiểm tra dependency khi ALTER/DROP table, schema, role.
- Rà soát GRANT EXECUTE theo role định kỳ.
- Không phơi hàm nâng quyền như API công khai chỉ vì SQL gọi thành công.

## 27. Bài tập thực hành kèm đáp án

### Bài 1. Phân biệt quyền gọi và quyền bảng

**Tình huống:** PostgreSQL role `reporter` có `EXECUTE` trên `api.get_total()`, nhưng không có SELECT bảng `private.sales`. Routine là `SECURITY INVOKER` và dùng SELECT bảng đó.

**Đáp án:** quyền EXECUTE cho phép gọi function, nhưng câu SELECT bên trong có thể bị từ chối do thiếu quyền bảng/schema của reporter. Muốn ẩn bảng và chỉ cho gọi API, cần một giải pháp definer với quyền tối thiểu và validation thích hợp, không đơn giản cấp EXECUTE.

### Bài 2. PostgreSQL đổi sang SECURITY DEFINER

**Yêu cầu:** ghi thuộc tính để function chạy với quyền owner.

**Đáp án:**

```sql
CREATE FUNCTION api.get_total()
RETURNS numeric
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
    SELECT SUM(amount) FROM private.sales;
$$;
```

Tên bảng đã schema-qualified; owner phải có quyền cần thiết và quyền EXECUTE phải được giới hạn đúng role. Mẫu này chưa có tenant filter nên chỉ nên dùng nếu business thực sự cho tổng toàn bảng.

### Bài 3. PostgreSQL EXECUTE trên một chữ ký cụ thể

**Yêu cầu:** cấp quyền gọi function `api.get_balance(bigint)` cho `report_reader`.

**Đáp án:**

```sql
GRANT USAGE ON SCHEMA api TO report_reader;

GRANT EXECUTE ON FUNCTION api.get_balance(bigint)
TO report_reader;
```

`USAGE` trên schema và `EXECUTE` trên function là hai privilege khác nhau.

### Bài 4. PostgreSQL PUBLIC default

**Câu hỏi:** tạo mới một function SECURITY DEFINER nhạy cảm; vì sao phải xem `PUBLIC`?

**Đáp án:** PostgreSQL thường mặc định cấp EXECUTE trên function mới cho PUBLIC. Nên `REVOKE ALL ON FUNCTION ... FROM PUBLIC` và `GRANT EXECUTE` cho role tin cậy **trong cùng transaction tạo routine** nếu cần hạn chế tuyệt đối cửa sổ công khai.

### Bài 5. PostgreSQL search_path

**Tình huống:** SECURITY DEFINER function dùng `SELECT * FROM balances` không nêu schema; caller được CREATE table cùng tên trong một schema xuất hiện trước bảng thật.

**Đáp án:** có nguy cơ **object shadowing**. Sửa bằng cách schema-qualify `private.balances`, cài search_path chỉ chứa schema tin cậy với `pg_temp` ở cuối, và không cấp CREATE trong schema tin cậy cho caller.

### Bài 6. PostgreSQL current_user và session_user

**Tình huống:** login gốc là `service_login`, function SECURITY DEFINER thuộc `api_owner`.

**Đáp án:** bên trong function, `current_user` có thể là `api_owner` trong khi `session_user` vẫn là login gốc. Điều đó không có nghĩa người dùng web cuối cùng là `api_owner` hoặc `service_login`.

### Bài 7. PostgreSQL RLS

**Tình huống:** bảng bật RLS cho tenant; SECURITY DEFINER function thuộc chủ bảng.

**Đáp án:** chủ bảng PostgreSQL thường bỏ qua RLS trừ khi có `FORCE ROW LEVEL SECURITY` phù hợp; role có BYPASSRLS hoặc superuser cũng có khả năng vượt RLS. Vì vậy definer function có thể thấy nhiều hàng hơn caller. Cần kiểm tra owner, policy và tenant validation.

### Bài 8. PostgreSQL procedure tự COMMIT

**Tình huống:** procedure `SECURITY DEFINER` muốn thực hiện `COMMIT` bên trong.

**Đáp án:** PostgreSQL không cho SECURITY DEFINER procedure thực thi transaction control statements. Cần thiết kế caller/tầng điều phối transaction theo quy tắc PostgreSQL.

### Bài 9. MySQL mặc định

**Hỏi:** MySQL stored procedure không ghi `SQL SECURITY` thì dùng DEFINER hay INVOKER?

**Đáp án:** mặc định **`SQL SECURITY DEFINER`**, không giống PostgreSQL.

### Bài 10. MySQL cấp quyền gọi

**Yêu cầu:** cấp quyền gọi `demo_app.recalculate` cho account `'app'@'%'`.

**Đáp án:**

```sql
GRANT EXECUTE
ON PROCEDURE demo_app.recalculate
TO 'app'@'%';
```

Account phải tồn tại, routine phải tồn tại và người cấp cần quyền thích hợp; việc thực thi SQL bên trong còn phụ thuộc `SQL SECURITY` và quyền của context.

### Bài 11. MySQL definer bị xóa

**Tình huống:** import dump routine có `DEFINER='old_admin'@'localhost'` nhưng account này không còn ở DB mới.

**Đáp án:** có nguy cơ routine thất bại ở runtime hoặc thành orphan object. Cần quản lý definer account và quyền migration, không đổi thành `root` bừa bãi.

### Bài 12. SQL Server CALLER và ownership chain

**Tình huống:** caller có EXECUTE trên procedure nhưng không SELECT bảng; procedure và bảng cùng owner, truy vấn trong procedure là SELECT tĩnh.

**Đáp án:** SQL Server có thể cho phép truy cập qua **ownership chaining** dù module ở context CALLER mặc định. Cần kiểm tra owner của các đối tượng và bảo đảm chain không bị đứt.

### Bài 13. SQL Server dynamic SQL

**Tình huống:** procedure chuyển SELECT tĩnh thành `EXEC(@sql)` và bắt đầu lỗi permission.

**Đáp án:** dynamic SQL không tự hưởng ownership chaining như truy vấn tĩnh. Phải xem execution context/quyền thực tế; không chữa bằng việc cấp quyền sysadmin hoặc mở TRUSTWORTHY bừa bãi.

### Bài 14. SQL Server table-valued function

**Câu hỏi:** caller query `SELECT * FROM app.fn_orders(10)`; quyền nào thường cần ở object?

**Đáp án:** SQL Server dùng **`SELECT`** privilege cho table-valued function, trong khi stored procedure và scalar function thường dùng `EXECUTE`. Không gộp mọi function vào một loại.

### Bài 15. Oracle quyền qua role

**Tình huống:** `api_owner` có SELECT bảng `data_owner.payments` chỉ qua role; function `AUTHID DEFINER` dùng static SELECT bảng đó.

**Đáp án:** named PL/SQL definer-rights unit thường disable roles; cần **GRANT SELECT trực tiếp cho api_owner** để compile/chạy theo quy tắc phù hợp.

### Bài 16. Oracle invoker rights

**Yêu cầu:** khai báo một stored function chạy theo quyền caller.

**Đáp án:**

```sql
CREATE OR REPLACE FUNCTION api_owner.example_func(
    p_id IN NUMBER
)
RETURN NUMBER
AUTHID CURRENT_USER
IS
BEGIN
    RETURN p_id;
END;
/
```

Trong ví dụ chỉ trả tham số nên chưa có quyền bảng để kiểm tra. Nếu thêm SQL đọc bảng, quyền runtime và cơ chế INHERIT PRIVILEGES phải được xét.

### Bài 17. Oracle INHERIT PRIVILEGES

**Tình huống:** lời gọi AUTHID CURRENT_USER báo ORA-06598.

**Đáp án:** xem quyền của owner routine được **kế thừa đặc quyền của invoker** theo quy tắc Oracle 12c+. Có thể cần một `GRANT INHERIT PRIVILEGES ON USER caller TO routine_owner` phù hợp thay vì cấp rộng `INHERIT ANY PRIVILEGES`.

### Bài 18. Oracle package

**Tình huống:** package có `get_summary` và `refund_payment`; chỉ muốn role xem báo cáo gọi `get_summary`.

**Đáp án:** `GRANT EXECUTE` trên package thường cho gọi các thành viên **công khai** của package; nên chia API/package theo đặc quyền hoặc đặt wrapper/cơ chế authorization, không cấp package nhiều quyền cho report role.

### Bài 19. SQLite

**Hỏi:** SQLite có thể `GRANT EXECUTE ON PROCEDURE p TO u` không?

**Đáp án:** không. SQLite không có server-side stored procedure ACL tương đương. Phân quyền cần do ứng dụng/OS/connection kiểm soát; hàm do ứng dụng đăng ký chạy trong context ứng dụng.

### Bài 20. Lỗi tenant trong routine definer

**Tình huống:** role A được gọi `api.get_balance(account_id)` nhưng account_id không được kiểm tra quyền sở hữu.

**Đáp án:** dù caller không SELECT bảng trực tiếp, role A vẫn có thể thử nhiều account_id để lấy dữ liệu ngoài phạm vi. Cần authorization trên **mỗi đối tượng/hàng**, không chỉ GRANT EXECUTE vào function.

### Bài 21. Đường truy cập qua nhiều routine

**Tình huống:** caller gọi routine SECURITY DEFINER A; A gọi routine SECURITY INVOKER B; B đọc bảng.

**Đáp án:** trên PostgreSQL, ngữ cảnh gọi B có thể là **effective role hiện tại của A**, tức owner A, không nhất thiết là session login ban đầu. Phải xét toàn bộ call stack và quyền của từng routine/bảng.

### Bài 22. Cấp quyền tối thiểu

**Yêu cầu:** đề xuất quyền cho một API chỉ trả phí vận chuyển từ bảng `private.shipping_rules`.

**Gợi ý đáp án:**

1. Role caller được `USAGE` trên schema API và `EXECUTE` đúng function.
2. Chủ definer routine dùng role riêng với `SELECT` chỉ các bảng/cột cần.
3. Caller không được SELECT bảng private, không có CREATE trong schema tin cậy.
4. Function cố định bảng, nhận input được kiểm tra, không chạy arbitrary SQL.
5. Có test giá trị đầu vào/tenant và nhật ký truy cập theo chính sách.

## 28. Tài liệu chính thức để đối chiếu

Những quy tắc permissions và execution context thay đổi theo sản phẩm, phiên bản và cấu hình. Tài liệu nên tra cứu khi triển khai:

- **PostgreSQL — CREATE FUNCTION / SECURITY DEFINER:** https://www.postgresql.org/docs/current/sql-createfunction.html
- **PostgreSQL — CREATE PROCEDURE / transaction control:** https://www.postgresql.org/docs/current/sql-createprocedure.html
- **PostgreSQL — GRANT / object privileges:** https://www.postgresql.org/docs/current/sql-grant.html
- **PostgreSQL — Row Security Policies:** https://www.postgresql.org/docs/current/ddl-rowsecurity.html
- **MySQL — Stored Object Access Control:** https://dev.mysql.com/doc/refman/8.4/en/stored-objects-security.html
- **MySQL — CREATE PROCEDURE and CREATE FUNCTION:** https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html
- **MariaDB — CREATE PROCEDURE:** https://mariadb.com/docs/server/reference/sql-statements/stored-routine-statements/create-procedure
- **SQL Server — EXECUTE AS Clause:** https://learn.microsoft.com/en-us/sql/t-sql/statements/execute-as-clause-transact-sql
- **SQL Server — GRANT Object Permissions:** https://learn.microsoft.com/en-us/sql/t-sql/statements/grant-object-permissions-transact-sql
- **Oracle — Invoker's Rights and Definer's Rights (AUTHID):** https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/invokers-rights-and-definers-rights-authid-property.html
- **Oracle — Managing Security for Definer's/Invoker's Rights:** https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/managing-security-for-definers-rights-and-invokers-rights.html
- **SQLite — Application-Defined SQL Functions:** https://www.sqlite.org/appfunc.html
- **SQLite — Authorizer API:** https://www.sqlite.org/c3ref/set_authorizer.html

Khi cần quyết định chính sách production, đọc đúng phiên bản DBMS và kiểm tra **thực nghiệm bằng role ít quyền** thay vì dựa vào một ví dụ chỉ chạy bằng admin.

## Kết luận

Trong stored procedure và stored function, **quyền gọi**, **chủ thể thực thi** và **phạm vi truy cập đối tượng** là ba khía cạnh khác nhau:

- `GRANT EXECUTE` (hoặc `SELECT` đối với loại function đặc thù của SQL Server) quyết định người dùng có thể **bước vào routine**.
- `SECURITY INVOKER/DEFINER`, `SQL SECURITY`, `EXECUTE AS`, `AUTHID` và ownership chaining quyết định **quyền của ai được dùng khi SQL bên trong chạy**.
- Quyền schema/bảng/cột, name resolution, RLS, tenant authorization, trigger, routine lồng nhau và SQL động quyết định **dữ liệu và đối tượng nào thực sự có thể bị truy cập**.

**Điểm ghi nhớ về mặc định:** PostgreSQL thường là **invoker**, MySQL/MariaDB và Oracle thường là **definer** cho stored routines, SQL Server thường là **caller** nhưng có **ownership chaining**, còn SQLite không có ACL stored procedure kiểu server DBMS.

Một thiết kế an toàn không chỉ cấp EXECUTE thành công. Nó cần **owner có quyền tối thiểu, schema được bảo vệ, định danh đối tượng rõ ràng, tham số được xác thực, giới hạn hàng theo tenant và thử nghiệm với caller không có quyền trực tiếp trên bảng nhạy cảm**. Routine có thể là một **cổng truy cập an toàn**, nhưng nếu chạy bằng quyền cao và không kiểm soát đầu vào, chính cổng ấy có thể trở thành đường vượt qua mọi giới hạn dữ liệu mà hệ thống dự định bảo vệ.

