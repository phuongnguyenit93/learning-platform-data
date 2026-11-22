# Phân tách quyền đọc, ghi, thay đổi cấu trúc và thực thi routine

Trong một hệ thống SQL, người xem báo cáo cần **đọc dữ liệu**, dịch vụ xử lý đơn hàng cần **ghi dữ liệu**, công cụ triển khai cần **thay đổi cấu trúc**, còn một ứng dụng đặc biệt có thể chỉ cần **gọi một hàm hoặc thủ tục đã được kiểm soát**. Nếu tất cả cùng đăng nhập bằng một tài khoản có toàn quyền, một lỗi phần mềm, câu SQL viết sai hoặc thông tin đăng nhập bị lộ có thể ảnh hưởng toàn bộ cơ sở dữ liệu.

Chủ đề **“Phân tách quyền đọc, ghi, thay đổi cấu trúc và thực thi routine”** thuộc chương **Quyền và SQL an toàn** của module Database SQL. Mục tiêu không chỉ là biết cú pháp `GRANT` và `REVOKE`, mà còn thiết kế được một hệ quyền thực tế:

- Người đọc không sửa được dữ liệu.
- Người ghi chỉ được thay đổi đúng những bảng và loại thao tác cần thiết.
- Quyền thay đổi cấu trúc được dành cho chủ sở hữu/migration, không cấp cho ứng dụng chạy hằng ngày.
- Người gọi routine có thể thực hiện **một nghiệp vụ đã định nghĩa** mà không phải nhận toàn quyền đối với bảng bên dưới.
- Các quyền được kiểm chứng trên **vai trò thực thi thật**, kể cả quyền mặc định, quyền qua nhóm và các đường truy cập gián tiếp.

Phần minh họa chính dùng **PostgreSQL**. Tên role, schema và bảng được đặt riêng cho bài học, đủ để tự thực hành trên một database thử nghiệm. Cuối bài có so sánh MySQL, SQL Server, Oracle và SQLite vì **tên quyền và cơ chế thực thi routine khác nhau giữa các hệ quản trị**.

## 1. Bốn nhóm quyền cần phân biệt

Đây là bốn nhóm quyền theo **mục đích nghiệp vụ**, không phải bốn từ khóa GRANT duy nhất của SQL.

| Nhóm quyền | Công việc tiêu biểu | Cơ chế PostgreSQL thường dùng | Không nên tự động bao gồm |
| --- | --- | --- | --- |
| **Đọc** | `SELECT` báo cáo, kiểm tra trạng thái | `GRANT SELECT ON TABLE ...` | `INSERT`, `UPDATE`, `DELETE`, DDL |
| **Ghi** | Thêm/sửa/xóa hàng nghiệp vụ | `INSERT`, `UPDATE`, `DELETE` với phạm vi hợp lý | `DROP TABLE`, `ALTER TABLE`, `CREATE FUNCTION` |
| **Thay đổi cấu trúc** | Tạo/sửa/xóa bảng, index, view, routine | Quyền sở hữu đối tượng, `CREATE` trên schema, vai trò triển khai | Quyền runtime của ứng dụng thường |
| **Thực thi routine** | Gọi function hoặc procedure có logic cố định | `GRANT EXECUTE ON FUNCTION/PROCEDURE ...` | Quyền truy cập trực tiếp toàn bộ bảng mà routine sử dụng |

Hai điểm đặc biệt:

1. **Quyền ghi không đương nhiên đồng nghĩa quyền thay đổi cấu trúc.** Trong PostgreSQL, `GRANT ALL PRIVILEGES ON TABLE` không biến người được cấp thành **chủ sở hữu** bảng để tùy ý `ALTER`/`DROP`.
2. **Quyền EXECUTE không phải quyền SELECT/UPDATE trên bảng nguồn.** Với routine chạy theo quyền của **người định nghĩa** (*security definer*), người gọi có thể hoàn thành một nghiệp vụ giới hạn mà không có quyền DML trực tiếp trên bảng.

Ví dụ một dịch vụ thanh toán chỉ cần chuyển tiền giữa hai tài khoản qua routine. Nếu ứng dụng có `UPDATE` trực tiếp trên cột `balance`, nó có thể bỏ qua quy tắc chuyển tiền. Nếu chỉ được `EXECUTE` một routine kiểm tra đầy đủ, bề mặt rủi ro nhỏ hơn.

### 1.1. Nguyên tắc quyền tối thiểu

**Least privilege**: chỉ cấp những quyền cần thiết cho công việc hiện tại, trong phạm vi đối tượng cần thiết và trong thời gian cần thiết.

Không có nghĩa “mọi tài khoản chỉ được SELECT”. Một chương trình cần ghi đơn hàng vẫn phải có quyền ghi, nhưng có thể chỉ cần `INSERT` ở bảng đơn và `SELECT` trên một số cột tham chiếu, **không cần DROP schema hoặc tạo superuser**.

### 1.2. Một danh tính có thể làm nhiều công việc, nhưng nên có đường quyền rõ

Một ứng dụng có thể cần cả đọc và ghi. Tuy nhiên, nên phân biệt:

- Nhóm vai trò `report_reader` cho công việc báo cáo.
- Nhóm `order_writer` cho thao tác ghi đơn.
- Tài khoản `migration` được cấp quyền DDL trong thời gian triển khai.
- Nhóm `routine_executor` chỉ được gọi những routine được cho phép.

Sự phân tách này giúp nhìn rõ **ai có thể làm gì**, thu hồi quyền dễ hơn và giảm thiệt hại nếu một credential bị lộ.

## 2. Principal, role, login và quyền thừa hưởng

Trong PostgreSQL, **role** là đơn vị quản lý quyền. Một role có thể:

- Có `LOGIN`: dùng để xác thực và kết nối vào database.
- Có `NOLOGIN`: thường dùng làm **nhóm quyền** hoặc vai trò sở hữu đối tượng.
- Là thành viên của role khác, qua `GRANT some_role TO another_role`.
- Có khả năng chuyển sang role khác bằng `SET ROLE` nếu membership và tùy chọn cấp quyền cho phép.
- Sở hữu schema, bảng, view, function và những đối tượng khác.

Một cấu trúc điển hình:

```text
                  Database
                     │
         ┌───────────┴────────────┐
         │                        │
     Roles ứng dụng          Role triển khai
         │                        │
  ┌──────┼────────┐          Owner/DDL
  │      │        │
Reader Writer  Routine Executor
  │      │        │
SELECT  DML     EXECUTE routine
         │        │
         └────┐   └──► function thực thi
              │        quyền có giới hạn
          Không có quyền
          ALTER/DROP bảng
```

### 2.1. Role nhóm khác tài khoản đăng nhập

Ví dụ **minh họa cấu trúc**:

```sql
CREATE ROLE app_reader NOLOGIN;
CREATE ROLE reporting_service LOGIN;
GRANT app_reader TO reporting_service;
```

`app_reader` là nhóm quyền; `reporting_service` là tài khoản đăng nhập có thể nhận quyền của nhóm theo cấu hình membership. Trong production, tài khoản LOGIN cần cơ chế xác thực, lưu secret và chính sách vòng đời phù hợp; ví dụ trên chưa thiết lập password/certificate/token hay hệ thống xác thực cụ thể.

**Lưu ý PostgreSQL hiện đại:** các tùy chọn membership như `INHERIT`, `SET` và `ADMIN` có ngữ nghĩa theo phiên bản. Không mặc định mọi role con đều tự động có thể `SET ROLE` sang role cha hoặc nhận tất cả quyền theo cùng một cách nếu cấu hình membership có tùy chọn giới hạn.

### 2.2. Quyền của role, quyền qua membership và quyền PUBLIC

Một tài khoản có thể được phép `SELECT` vì:

- Được `GRANT SELECT` trực tiếp.
- Thừa hưởng quyền từ một nhóm.
- Được cấp qua `PUBLIC`.
- Là chủ sở hữu của đối tượng hoặc có đặc quyền quản trị phù hợp.

Do đó, `REVOKE SELECT ON t FROM alice` có thể **không chặn được alice** nếu alice còn được SELECT qua role khác hoặc `PUBLIC`.

Phải kiểm tra **đường cấp quyền hiệu lực**, không chỉ một dòng GRANT.

### 2.3. Owner không giống grantee

Trong PostgreSQL, owner có các đặc quyền quản trị đối tượng quan trọng như thay đổi định nghĩa hoặc xóa đối tượng, theo các quy tắc sở hữu và membership. Người chỉ được `GRANT SELECT` hay `GRANT UPDATE` không tự biến thành owner.

Chủ sở hữu cũng không chỉ là một vai trò “có một bộ GRANT lớn”. Quyền sở hữu là một quan hệ riêng, có khả năng vượt ra ngoài những quyền DML có thể cấp trên bảng.

## 3. Quyền của database, schema và object là nhiều lớp khác nhau

PostgreSQL phân chia đối tượng theo tầng:

```text
database
└── schema
    ├── table
    ├── view / materialized view
    ├── sequence
    ├── function
    └── procedure
```

Một người muốn đọc `lab_acl_376.tickets` thường cần cả:

1. Có thể kết nối database theo cơ chế xác thực và quyền `CONNECT`.
2. Có `USAGE` trên schema `lab_acl_376` để truy cập đối tượng trong schema đó.
3. Có `SELECT` trên bảng `tickets`, hoặc quyền hiệu lực tương đương.

**Một quyền không tự suy ra các quyền còn lại.**

### 3.1. Quyền cấp database

PostgreSQL có những quyền ở cấp database như:

- `CONNECT`: cho phép kết nối tới database nếu những điều kiện xác thực khác cũng thỏa.
- `CREATE`: khả năng tạo schema hoặc các đối tượng cấp database được hỗ trợ theo quy tắc DBMS.
- `TEMPORARY`/`TEMP`: tạo bảng tạm trong database theo quy tắc tương ứng.

Ví dụ về cú pháp, **không chạy nguyên dạng** vì database và role chưa được tạo:

```sql
GRANT CONNECT ON DATABASE application_db TO report_login;
```

`CONNECT` không tự cấp SELECT trên mọi bảng trong database. Mặc định một số quyền database có thể được cấp cho `PUBLIC`; phải kiểm tra cấu hình thực tế.

### 3.2. Quyền cấp schema

Hai quyền rất quan trọng:

```sql
GRANT USAGE ON SCHEMA some_schema TO some_reader;

GRANT CREATE ON SCHEMA some_schema TO some_builder;
```

- `USAGE` cho phép định vị/truy cập những đối tượng trong schema **khi có thêm quyền trên đối tượng tương ứng**.
- `CREATE` cho phép tạo đối tượng trong schema theo các giới hạn và loại đối tượng hỗ trợ.

`CREATE ON SCHEMA` **không tự biến role thành owner của mọi bảng hiện hữu**; role có thể tạo và sở hữu đối tượng mới của chính nó mà vẫn không được `ALTER TABLE` một bảng do người khác sở hữu.

### 3.3. Quyền cấp bảng

PostgreSQL hỗ trợ các quyền bảng như:

| Quyền | Ví dụ sử dụng | Ghi chú |
| --- | --- | --- |
| `SELECT` | Đọc cột từ bảng | Có thể cấp trên toàn bảng hoặc theo cột |
| `INSERT` | Thêm hàng | Có thể giới hạn theo cột; `RETURNING` có yêu cầu đọc riêng |
| `UPDATE` | Sửa hàng | Có thể cấp theo cột; cột trong điều kiện đọc có thể cần SELECT |
| `DELETE` | Xóa hàng | Nên giới hạn rất chặt |
| `TRUNCATE` | Xóa nhanh mọi hàng | Quyền riêng, không đồng nghĩa DELETE |
| `REFERENCES` | Tạo FK tham chiếu theo điều kiện | Phân biệt với việc được đọc dữ liệu |
| `TRIGGER` | Tạo trigger trên bảng khi các điều kiện khác cho phép | Không phải quyền thực thi function dùng làm trigger |
| Các quyền bảo trì theo phiên bản | Thao tác bảo trì riêng | Kiểm tra phiên bản PostgreSQL |

`GRANT ALL PRIVILEGES ON TABLE` có thể cấp nhiều quyền bảng, nhưng **không có nghĩa người đó được sở hữu bảng để ALTER/DROP**.

### 3.4. Quyền cấp routine

Routine trong bài này gồm:

- **Function**: có thể được gọi bằng biểu thức SQL như `SELECT schema.function_name(...)`.
- **Procedure**: thường được gọi bằng `CALL schema.procedure_name(...)`.

`EXECUTE` là đặc quyền đặc trưng cho việc gọi routine:

```sql
GRANT EXECUTE
ON FUNCTION some_schema.compute_value(integer)
TO some_role;

GRANT EXECUTE
ON PROCEDURE some_schema.perform_action(integer)
TO some_role;
```

Ví dụ ở đây là cú pháp khái niệm với object chưa được tạo. Khi routine bị **overload**, tên và **danh sách kiểu tham số đầu vào** giúp xác định chữ ký đích. Không được chỉ đọc tên rồi giả định đã cấp EXECUTE cho mọi biến thể.

## 4. Chuẩn bị phòng thực hành PostgreSQL

Ta sẽ tạo một phòng thử nghiệm có các role sau:

| Role | Loại | Nhiệm vụ |
| --- | --- | --- |
| `lab376_owner` | `NOLOGIN` | Sở hữu schema, bảng và routines; đại diện đường triển khai DDL |
| `lab376_reader` | `NOLOGIN` | Chỉ đọc bảng cho phép |
| `lab376_writer` | `NOLOGIN` | Đọc/thêm/sửa bảng tickets, không sửa balances |
| `lab376_executor` | `NOLOGIN` | Gọi hai routine được cấp, không đọc/ghi trực tiếp bảng nguồn |

Ta dùng **một kết nối quản trị trong database sandbox**, có đủ quyền tạo role và schema, rồi `SET ROLE` để mô phỏng quyền của từng nhóm. Để toàn bộ ví dụ đơn giản và nhất quán, giả định tài khoản thao tác là một **superuser PostgreSQL chỉ trong môi trường thử nghiệm** hoặc môi trường quản trị được cấp quyền tương đương thích hợp. Không dùng superuser của production cho ứng dụng.

Các role `NOLOGIN` ở đây **không thể tự đăng nhập trực tiếp**; dùng `SET ROLE` từ tài khoản quản trị để kiểm chứng. Trong triển khai thực, tạo các role `LOGIN` riêng rồi cấp membership phù hợp, không cấp superuser cho ứng dụng.

### 4.1. Tạo các vai trò

Chạy dưới tài khoản quản trị của **database sandbox**:

```sql
CREATE ROLE lab376_owner NOLOGIN;
CREATE ROLE lab376_reader NOLOGIN;
CREATE ROLE lab376_writer NOLOGIN;
CREATE ROLE lab376_executor NOLOGIN;
```

Những tên này chỉ phục vụ bài học. Nếu chúng đã tồn tại, lệnh `CREATE ROLE` sẽ báo lỗi; hãy dùng sandbox mới hoặc xem xét quyền sở hữu trước khi thay đổi, không xóa role đang có của người khác.

### 4.2. Tạo schema có owner rõ ràng

```sql
CREATE SCHEMA lab_acl_376 AUTHORIZATION lab376_owner;
```

Sau đó chuyển role để các bảng và routines được tạo **bởi owner chuyên biệt**, không phải thuộc riêng login superuser:

```sql
SET ROLE lab376_owner;
```

Để xem danh tính hiệu lực:

```sql
SELECT
    current_user AS effective_role,
    session_user AS login_role;
```

`current_user` là role đang có hiệu lực khi xử lý câu SQL; `session_user` là danh tính login gốc của session. Với `SET ROLE`, hai giá trị có thể khác nhau.

### 4.3. Tạo bảng tài khoản có số dư

```sql
CREATE TABLE lab_acl_376.accounts (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_label TEXT NOT NULL,
    balance NUMERIC(14,2) NOT NULL
        CHECK (balance >= 0)
);
```

Dữ liệu học tập:

```sql
INSERT INTO lab_acl_376.accounts (account_label, balance)
VALUES
    ('Lan', 200.00),
    ('Minh', 80.00);
```

Vì schema vừa tạo và bảng còn rỗng, các ID identity được sinh theo thứ tự chèn, thường là **1** và **2** trong môi trường mới nguyên vẹn. Các ví dụ chuyển tiền dưới đây dựa trên trạng thái này; nếu đã chạy lại nhiều lần, cần xem ID thật thay vì giả định sequence không có khoảng trống.

### 4.4. Tạo bảng tickets để ứng dụng ghi

```sql
CREATE TABLE lab_acl_376.tickets (
    ticket_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'done'))
);

INSERT INTO lab_acl_376.tickets (title, status)
VALUES
    ('Cần hỗ trợ truy cập', 'open'),
    ('Cập nhật tài liệu', 'open');
```

Ta cố ý tách:

- Bảng `accounts`: chứa số dư nhạy cảm; routine xử lý chuyển tiền.
- Bảng `tickets`: role writer được phép thao tác trực tiếp ở phạm vi xác định.

Nếu dùng cùng bảng accounts để cấp `UPDATE` trực tiếp cho writer, writer có thể bypass routine chuyển tiền, không còn minh họa được giới hạn quan trọng.

### 4.5. Kiểm tra bảng do role nào sở hữu

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    pg_get_userbyid(c.relowner) AS owner_name
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'lab_acl_376'
  AND c.relname IN ('accounts', 'tickets')
ORDER BY c.relname;
```

Cả hai bảng phải thuộc `lab376_owner` khi được tạo sau `SET ROLE lab376_owner`.

## 5. Cấp quyền đọc và ghi đúng phạm vi

Đang ở role `lab376_owner`, thực hiện:

### 5.1. Cho phép truy cập tên đối tượng trong schema

```sql
GRANT USAGE ON SCHEMA lab_acl_376
TO lab376_reader, lab376_writer, lab376_executor;
```

Không cấp `CREATE ON SCHEMA` cho ba role runtime. Như vậy các role runtime không được tạo đối tượng tùy ý trong schema này chỉ dựa trên các GRANT của bài.

### 5.2. Chỉ cấp SELECT cho reader

```sql
GRANT SELECT
ON lab_acl_376.accounts,
   lab_acl_376.tickets
TO lab376_reader;
```

Reader có quyền đọc hai bảng. Nó **không được cấp** `INSERT`, `UPDATE`, `DELETE` hay `TRUNCATE` từ các lệnh trên.

### 5.3. Chỉ cấp DML cần thiết trên tickets cho writer

```sql
GRANT SELECT, INSERT, UPDATE
ON lab_acl_376.tickets
TO lab376_writer;
```

Writer có thể:

- Xem tickets.
- Chèn tickets.
- Cập nhật tickets.

Writer **không được cấp**:

- `DELETE` trên tickets.
- `SELECT` hoặc `UPDATE` trên accounts.
- `CREATE` trên schema.
- Quyền sở hữu các bảng hay routines.

**Vì sao có SELECT đi cùng UPDATE?** Một câu `UPDATE ... WHERE ticket_id = ...` đọc giá trị cột ở điều kiện; `RETURNING ticket_id, status` cũng đọc các cột đầu ra. PostgreSQL có thể yêu cầu `SELECT` tương ứng cho những phần đó. Cấp SELECT trên tickets ở bài học giúp viết truy vấn thực hành đơn giản.

Trong production, nên cân nhắc quyền **theo cột**, việc chỉ cấp quyền ghi qua routine và Row-Level Security nếu cần hạn chế theo từng hàng.

### 5.4. Không cấp quyền bảng trực tiếp cho executor

Ta chưa cấp `SELECT`/`UPDATE` trên accounts hoặc tickets cho `lab376_executor`. Executor mới chỉ có `USAGE` trên schema, **chưa có quyền đọc hoặc ghi bảng**.

Ở phần tiếp theo, ta sẽ cấp riêng quyền gọi routine cho executor để thấy sự khác biệt.

## 6. Tạo function chuyển tiền được kiểm soát

Giả sử một ứng dụng chỉ được phép chuyển số dư thông qua function:

```text
transfer_funds(sender_id, receiver_id, amount)
```

Yêu cầu:

1. Sender và receiver khác nhau.
2. Mỗi tài khoản đều tồn tại.
3. Số tiền dương, hợp lệ tới hai chữ số thập phân.
4. Không cho sender bị âm số dư.
5. Ghi nợ và ghi có trong **cùng transaction**.
6. Role executor chỉ có `EXECUTE`, không có `UPDATE` trực tiếp trên accounts.
7. Function hoạt động với quyền của một owner đã được kiểm soát, không phải superuser.

### 6.1. SECURITY INVOKER và SECURITY DEFINER

PostgreSQL phân biệt:

- `SECURITY INVOKER` (**mặc định**): function kiểm tra quyền truy cập các bảng bên trong theo quyền của **người gọi**.
- `SECURITY DEFINER`: function chạy với quyền của **người sở hữu function** khi thực thi các câu lệnh bên trong.

`SECURITY DEFINER` là cách để người gọi có thể được phép thực hiện **một nghiệp vụ cụ thể** dù không có quyền sửa bảng trực tiếp.

Nhưng quyền được nâng theo owner cũng là một điểm nhạy cảm: function phải hạn chế đầu vào, không dùng SQL động không an toàn, không có `search_path` bị người lạ thao túng và không được sở hữu bởi superuser nếu không cần.

### 6.2. Tạo function an toàn theo phạm vi bài học

Đang ở `lab376_owner`, dùng một transaction để tạo function và ngay lập tức thu hồi quyền EXECUTE mặc định từ `PUBLIC` trước khi cấp cho executor:

```sql
BEGIN;

CREATE FUNCTION lab_acl_376.transfer_funds(
    p_sender_id BIGINT,
    p_receiver_id BIGINT,
    p_amount NUMERIC
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, lab_acl_376, pg_temp
AS $func$
DECLARE
    v_found_accounts INTEGER;
BEGIN
    IF p_sender_id IS NULL
       OR p_receiver_id IS NULL
       OR p_sender_id = p_receiver_id
    THEN
        RAISE EXCEPTION 'Invalid sender or receiver';
    END IF;

    IF p_amount IS NULL
       OR p_amount <= 0
       OR p_amount <> ROUND(p_amount, 2)
    THEN
        RAISE EXCEPTION 'Amount must be positive with at most two decimals';
    END IF;

    -- Khóa cả hai tài khoản theo thứ tự khóa xác định.
    PERFORM 1
    FROM lab_acl_376.accounts AS a
    WHERE a.account_id IN (p_sender_id, p_receiver_id)
    ORDER BY a.account_id
    FOR UPDATE;

    SELECT COUNT(*)
    INTO v_found_accounts
    FROM lab_acl_376.accounts AS a
    WHERE a.account_id IN (p_sender_id, p_receiver_id);

    IF v_found_accounts <> 2 THEN
        RAISE EXCEPTION 'One or both accounts do not exist';
    END IF;

    UPDATE lab_acl_376.accounts
    SET balance = balance - p_amount
    WHERE account_id = p_sender_id
      AND balance >= p_amount;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Insufficient funds';
    END IF;

    UPDATE lab_acl_376.accounts
    SET balance = balance + p_amount
    WHERE account_id = p_receiver_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Receiver account not found';
    END IF;
END;
$func$;

REVOKE ALL
ON FUNCTION lab_acl_376.transfer_funds(BIGINT, BIGINT, NUMERIC)
FROM PUBLIC;

GRANT EXECUTE
ON FUNCTION lab_acl_376.transfer_funds(BIGINT, BIGINT, NUMERIC)
TO lab376_executor;

COMMIT;
```

**Điểm cốt lõi về quyền:**

- Function được tạo khi `current_user=lab376_owner`, nên role này là owner của routine.
- Function có thể cập nhật `accounts` nhờ quyền của owner.
- `lab376_executor` được gọi routine nhưng **không được cấp** quyền `UPDATE accounts`.
- `REVOKE ... FROM PUBLIC` tránh việc mọi role đều được quyền EXECUTE function theo mặc định trong PostgreSQL.
- Việc **tạo → REVOKE → GRANT trong cùng transaction** giúp không có khoảng thời gian đã commit mà function nhạy cảm còn cho `PUBLIC` gọi trước khi quyền được thu hồi.

### 6.3. Vì sao cố định search_path?

`SECURITY DEFINER` chạy với quyền cao hơn người gọi. Nếu nó tìm tên bảng/function/operator qua một schema mà người gọi có thể tạo đối tượng giả mạo, attacker có thể tìm cách làm routine thực thi mã không mong muốn với quyền definer.

Trong function mẫu:

```sql
SET search_path = pg_catalog, lab_acl_376, pg_temp
```

- `pg_catalog` chứa các đối tượng hệ thống tin cậy.
- `lab_acl_376` là schema do owner được kiểm soát sở hữu; role runtime **không có CREATE**.
- `pg_temp` được đặt cuối cho các tình huống tra tên quan hệ tạm theo cơ chế PostgreSQL.
- Tên bảng quan trọng còn được viết **đầy đủ schema**: `lab_acl_376.accounts`.

Một routine SECURITY DEFINER production cần được kiểm toán cẩn thận hơn nữa về những object nó gọi, tham số đầu vào, RLS, hàm mở rộng, ownership và những schema có thể bị thay đổi bởi role kém tin cậy.

### 6.4. Vì sao không đặt COMMIT trong function?

Function chuyển tiền không tự gọi `COMMIT`. Nó thực hiện hai `UPDATE` trong **transaction của caller**.

Nếu một bước phát sinh lỗi chưa được xử lý, những thay đổi transactional của statement bị rollback. Nếu caller đang quản lý một transaction gồm nhiều statement, nó cần xử lý lỗi và quyết định commit/rollback toàn công việc.

Một function không phải “giao dịch độc lập” chỉ vì có `SECURITY DEFINER`.

### 6.5. Giới hạn của ví dụ chuyển tiền

Đây là mô hình học quyền, không phải giải pháp core banking hoàn chỉnh. Hệ thống tài chính thật còn cần ledger bất biến, idempotency key, quản lý tiền tệ/đơn vị, kiểm toán giao dịch, xử lý nghiệp vụ đồng thời phức tạp, kiểm thử khóa và vận hành lỗi.

Đặc biệt, giá trị `NUMERIC` được dùng để tránh sai lệch nhị phân của `FLOAT`, nhưng chọn scale, rounding và quy tắc tiền tệ vẫn là một quyết định nghiệp vụ.

## 7. Tạo procedure với quyền EXECUTE riêng

Ngoài function, PostgreSQL hỗ trợ `PROCEDURE` được gọi bằng `CALL`. Ta tạo một procedure giới hạn: đóng một ticket tồn tại.

### 7.1. Tạo procedure SECURITY DEFINER

Vẫn ở role `lab376_owner`:

```sql
BEGIN;

CREATE PROCEDURE lab_acl_376.close_ticket(
    p_ticket_id BIGINT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, lab_acl_376, pg_temp
AS $proc$
BEGIN
    UPDATE lab_acl_376.tickets
    SET status = 'done'
    WHERE ticket_id = p_ticket_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Ticket % does not exist', p_ticket_id;
    END IF;
END;
$proc$;

REVOKE ALL
ON PROCEDURE lab_acl_376.close_ticket(BIGINT)
FROM PUBLIC;

GRANT EXECUTE
ON PROCEDURE lab_acl_376.close_ticket(BIGINT)
TO lab376_executor;

COMMIT;
```

`lab376_executor` có thể gọi:

```sql
CALL lab_acl_376.close_ticket(1);
```

mà không cần quyền `UPDATE` trực tiếp trên tickets, vì procedure thực thi với quyền của `lab376_owner`.

Tuy nhiên, nó **chỉ có thể đóng ticket theo logic procedure cho phép**, không được tùy ý đổi status sang giá trị khác hay sửa title bằng câu `UPDATE` trực tiếp.

### 7.2. Procedure và quản lý transaction

PostgreSQL có những tình huống procedure có thể thực hiện transaction control, nhưng **procedure có thuộc tính `SECURITY DEFINER` không được dùng các câu điều khiển transaction như `COMMIT` và `ROLLBACK`**. Procedure mẫu không dùng chúng.

Đừng hiểu `CALL` có nghĩa procedure chắc chắn tạo một transaction độc lập hoặc tự commit. Câu gọi vẫn chịu ngữ nghĩa transaction của DBMS và context caller.

### 7.3. Chữ ký function và procedure

Hai lệnh sau xác định hai routine khác nhau:

```sql
GRANT EXECUTE
ON FUNCTION lab_acl_376.transfer_funds(BIGINT, BIGINT, NUMERIC)
TO lab376_executor;

GRANT EXECUTE
ON PROCEDURE lab_acl_376.close_ticket(BIGINT)
TO lab376_executor;
```

Không nên thay bằng:

```sql
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA lab_acl_376 TO lab376_executor;
```

nếu role chỉ nên được gọi **một function được duyệt**. Cấp cho mọi functions trong schema có thể bao gồm routine quản trị hoặc debug về sau, trái mục tiêu quyền tối thiểu.

## 8. Kiểm thử quyền bằng SET ROLE

Từ đây, trở lại login quản trị của sandbox:

```sql
RESET ROLE;
```

Tài khoản quản trị có đủ quyền `SET ROLE` sang các role bài học. Với triển khai thật, nên kiểm thử bằng **tài khoản ứng dụng thực tế**, có login, membership và pool settings thật. Việc một superuser tạm `SET ROLE` chỉ là mô phỏng hữu ích, không thay thế kiểm thử đầy đủ mọi đường xác thực.

### 8.1. Kiểm thử reader

```sql
SET ROLE lab376_reader;

SELECT ticket_id, title, status
FROM lab_acl_376.tickets
ORDER BY ticket_id;

SELECT account_id, account_label, balance
FROM lab_acl_376.accounts
ORDER BY account_id;

RESET ROLE;
```

Cả hai `SELECT` thành công.

Thử **lệnh cố ý phải lỗi**, chạy riêng khi đang là reader:

```sql
-- CỐ Ý LỖI: lab376_reader không có UPDATE trên tickets.
SET ROLE lab376_reader;

UPDATE lab_acl_376.tickets
SET status = 'done'
WHERE ticket_id = 1;

RESET ROLE;
```

PostgreSQL báo không đủ quyền trên bảng. Nếu chạy trong transaction tường minh và gặp lỗi, cần rollback/khôi phục trước khi tiếp tục; nếu đang autocommit theo từng statement, có thể gửi `RESET ROLE` sau statement bị từ chối.

### 8.2. Kiểm thử writer

```sql
SET ROLE lab376_writer;

INSERT INTO lab_acl_376.tickets (title, status)
VALUES ('Kiểm tra quyền ghi', 'open')
RETURNING ticket_id, title, status;

UPDATE lab_acl_376.tickets
SET status = 'done'
WHERE title = 'Kiểm tra quyền ghi';

SELECT ticket_id, title, status
FROM lab_acl_376.tickets
ORDER BY ticket_id;

RESET ROLE;
```

Vì writer được cấp `SELECT, INSERT, UPDATE` trên tickets, cả ba thao tác hợp lệ.

Các thử nghiệm **cố ý lỗi** (thực hiện riêng):

```sql
SET ROLE lab376_writer;

-- CỐ Ý LỖI: chưa được cấp DELETE.
DELETE FROM lab_acl_376.tickets
WHERE ticket_id = 1;

-- CỐ Ý LỖI: không được quyền trên accounts.
UPDATE lab_acl_376.accounts
SET balance = 9999
WHERE account_id = 1;

-- CỐ Ý LỖI: không phải owner của tickets.
ALTER TABLE lab_acl_376.tickets
ADD COLUMN secret_flag BOOLEAN;

RESET ROLE;
```

Các lệnh này có thể báo lỗi quyền khác nhau tùy quá trình kiểm tra: thiếu `DELETE`, `UPDATE`/`SELECT` trên accounts hoặc không sở hữu bảng. Không nên chạy cả ba trong **một transaction chưa được phục hồi** rồi tưởng mọi lỗi sẽ được báo riêng; PostgreSQL có thể từ chối các câu tiếp theo do transaction đã thất bại.

### 8.3. Kiểm thử executor

```sql
SET ROLE lab376_executor;

SELECT lab_acl_376.transfer_funds(
    1::BIGINT, 2::BIGINT, 25::NUMERIC
);

CALL lab_acl_376.close_ticket(1);

RESET ROLE;
```

Khi trạng thái ban đầu là số dư 200 và 80, sau khi gọi function thành công:

| Tài khoản | Trước | Sau |
| --- | ---: | ---: |
| 1 — Lan | 200.00 | 175.00 |
| 2 — Minh | 80.00 | 105.00 |
| **Tổng** | **280.00** | **280.00** |

Procedure đóng ticket 1 về `status='done'`.

Chú ý: `SELECT lab_acl_376.transfer_funds(...)` là một câu `SELECT` để **gọi function**, nhưng **không** đồng nghĩa executor được `SELECT` các bảng bên dưới. EXECUTE và SELECT bảng là hai loại quyền khác nhau.

Thử nghiệm cố ý lỗi:

```sql
SET ROLE lab376_executor;

-- CỐ Ý LỖI: executor không có SELECT trực tiếp trên accounts.
SELECT account_id, balance
FROM lab_acl_376.accounts;

-- CỐ Ý LỖI: executor không có UPDATE trực tiếp.
UPDATE lab_acl_376.accounts
SET balance = balance + 100
WHERE account_id = 1;

RESET ROLE;
```

Cả hai thao tác trực tiếp phải bị từ chối theo mô hình cấp quyền của bài.

### 8.4. Kiểm thử chức năng từ chối nghiệp vụ

Với số dư ban đầu sau lần chuyển đầu là 175 ở tài khoản 1, thử một lệnh chuyển vượt số dư:

```sql
SET ROLE lab376_executor;

-- CỐ Ý LỖI: sender không đủ tiền.
SELECT lab_acl_376.transfer_funds(
    1::BIGINT, 2::BIGINT, 10000::NUMERIC
);

RESET ROLE;
```

Function phát lỗi `Insufficient funds`. Không có chuyện tài khoản 2 được cộng 10.000 trong khi tài khoản 1 không bị trừ: logic cập nhật nằm trong cùng statement/transaction.

Nếu gọi dưới một transaction tường minh mà bị lỗi, PostgreSQL thường cần `ROLLBACK` hoặc savepoint trước khi tiếp tục thao tác.

### 8.5. Người quản lý cấu trúc

Role `lab376_owner` sở hữu hai bảng và routines. Một phiên quản trị được phép `SET ROLE lab376_owner` có thể làm:

```sql
SET ROLE lab376_owner;

-- Chỉ minh họa quyền DDL, không bắt buộc chạy.
ALTER TABLE lab_acl_376.tickets
ADD COLUMN internal_note TEXT;

RESET ROLE;
```

Nếu thực thi, câu `ALTER TABLE` thay đổi định nghĩa tickets thật. Chỉ thực hiện khi muốn mở rộng dữ liệu demo. Không để ứng dụng thường xuyên có membership cho phép chuyển sang role sở hữu này, nếu không việc tách quyền DDL sẽ mất ý nghĩa.

## 9. Những kết quả mong đợi của mô hình quyền

| Thao tác | Reader | Writer | Executor | Owner |
| --- | --- | --- | --- | --- |
| `SELECT tickets` | Có | Có | Không | Có |
| `INSERT tickets` | Không | Có | Không trực tiếp | Có |
| `UPDATE tickets` | Không | Có | Không trực tiếp | Có |
| `DELETE tickets` | Không | Không | Không | Có |
| `SELECT accounts` | Có | Không | Không | Có |
| `UPDATE accounts` | Không | Không | Không trực tiếp | Có |
| `EXECUTE transfer_funds` | Không | Không | Có | Có |
| `CALL close_ticket` | Không | Không | Có | Có |
| `ALTER TABLE tickets` | Không | Không | Không | Có |
| `CREATE object trong schema` | Không | Không | Không | Có |

Dấu “✓” biểu thị quyền **dự kiến từ bộ GRANT của bài**, không phải kết luận phổ quát khi role còn nhận quyền qua `PUBLIC` hoặc membership khác. Đối với database mới sạch, đây là ma trận thiết kế mục tiêu.

Đặc biệt, executor có thể **gián tiếp** thay đổi accounts hoặc tickets qua routine được duyệt, dù không thể thực hiện DML tùy ý trên bảng. Đó là bản chất của việc phân tách **quyền thực thi nghiệp vụ** với **quyền thao tác trực tiếp trên dữ liệu**.

## 10. GRANT, REVOKE và đường quyền thực tế

`GRANT` và `REVOKE` quản lý quyền trên đối tượng, nhưng chúng không tạo một mô hình “ALLOW/DENY” tuyệt đối theo từng user.

### 10.1. Cấp quyền đúng đối tượng

```sql
-- Các câu này đã được dùng trong bài:
GRANT SELECT ON lab_acl_376.accounts TO lab376_reader;
GRANT SELECT, INSERT, UPDATE
ON lab_acl_376.tickets TO lab376_writer;
```

Dùng tên đầy đủ `schema.object` giúp giảm khả năng nhắm sai bảng khi có nhiều schema và `search_path` khác nhau.

Ví dụ thu hồi quyền UPDATE, **không chạy nếu muốn giữ nguyên ma trận thực hành**:

```sql
REVOKE UPDATE
ON lab_acl_376.tickets
FROM lab376_writer;
```

Nếu thực hiện, writer mất quyền UPDATE được cấp trực tiếp trong bộ ví dụ. Tuy nhiên, nếu writer nhận UPDATE qua một role khác hoặc `PUBLIC`, quyền hiệu lực có thể vẫn tồn tại. `REVOKE` không tạo một lệnh **DENY** phủ định mọi con đường khác.

### 10.2. PUBLIC không phải schema public

Trong PostgreSQL:

- `PUBLIC` (viết hoa trong tài liệu để dễ nhận biết) là **nhóm giả định bao gồm mọi role**.
- `public` là **tên của một schema** thường có trong database.

Hai câu khác nhau hoàn toàn:

```sql
REVOKE EXECUTE
ON FUNCTION lab_acl_376.transfer_funds(BIGINT, BIGINT, NUMERIC)
FROM PUBLIC;

-- Một ví dụ quản trị rộng, KHÔNG tự chạy ở production:
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
```

Câu đầu ngăn quyền gọi function được cấp chung. Câu sau thay đổi quyền tạo object trong schema tên `public`, có thể ảnh hưởng nhiều ứng dụng, đặc biệt khi nâng cấp từ phiên bản PostgreSQL cũ với mặc định khác.

### 10.3. Membership và quyền gián tiếp

Giả sử một tài khoản nhận SELECT bằng hai đường:

```text
report_login
  ├── GRANT SELECT trực tiếp
  └── thành viên report_group
        └── GRANT SELECT trên bảng
```

`REVOKE SELECT FROM report_login` có thể không loại đường qua `report_group`. Kiểm tra quyền hiệu lực phải xem:

- Grant trực tiếp.
- Quyền của những role được thừa hưởng/được SET.
- Quyền được cấp cho `PUBLIC`.
- Quyền sở hữu hoặc đặc tính quản trị.
- View/routine được cấp quyền, có thể tạo đường truy cập **gián tiếp**.

Một câu `REVOKE` cũng không xóa dữ liệu người dùng đã xuất ra hoặc rollback các giao dịch đã commit trước đó.

## 11. Cấp quyền SELECT và UPDATE theo cột

Không phải lúc nào reader cũng cần thấy mọi cột của bảng. Bảng liên hệ có thể chứa thông tin hiển thị công khai và ghi chú chỉ nhân viên nội bộ được biết.

### 11.1. Thêm bảng liên hệ trong schema thực hành

```sql
SET ROLE lab376_owner;

CREATE TABLE lab_acl_376.customer_contacts (
    contact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    display_name TEXT NOT NULL,
    email TEXT NOT NULL,
    internal_note TEXT
);

INSERT INTO lab_acl_376.customer_contacts
    (display_name, email, internal_note)
VALUES
    ('An', 'an@example.test', 'Chỉ dùng cho vận hành'),
    ('Binh', 'binh@example.test', 'Thông tin nội bộ');

GRANT SELECT (contact_id, display_name)
ON lab_acl_376.customer_contacts
TO lab376_reader;

RESET ROLE;
```

Reader chỉ có quyền đọc hai cột:

```sql
SET ROLE lab376_reader;

SELECT contact_id, display_name
FROM lab_acl_376.customer_contacts
ORDER BY contact_id;

RESET ROLE;
```

Truy vấn này thành công. Nhưng các truy vấn sau **cố ý bị từ chối**:

```sql
SET ROLE lab376_reader;

SELECT email FROM lab_acl_376.customer_contacts;
SELECT * FROM lab_acl_376.customer_contacts;

RESET ROLE;
```

`SELECT *` tham chiếu cả cột `email` và `internal_note` chưa được cấp quyền. Không được lách quyền bằng cách chỉ trả `display_name` nhưng lọc `WHERE email LIKE ...`: cột đọc trong điều kiện cũng phải có quyền phù hợp.

### 11.2. UPDATE theo cột

Một role sửa trạng thái ticket có thể được cấp:

```sql
-- Ví dụ cú pháp: limited_editor là role giả định,
-- không nằm trong danh sách role được tạo ở phần 4.
GRANT UPDATE (status)
ON lab_acl_376.tickets
TO limited_editor;
```

Quyền này chỉ cho phép cập nhật cột `status` trong phạm vi phù hợp. Tuy nhiên:

- Câu `WHERE ticket_id = ...` cần quyền đọc các cột được tham chiếu theo quy tắc PostgreSQL.
- `RETURNING ticket_id, status` cũng có thể cần `SELECT` tương ứng.
- Quyền trên cột không tự giới hạn **hàng nào** được sửa.

Nếu mục tiêu chỉ cho phép hành động “đóng ticket”, routine `close_ticket` với `EXECUTE` hạn chế đôi khi rõ nghĩa hơn một bộ quyền UPDATE theo cột và các điều kiện ứng dụng tự ghép.

## 12. Sequence có quyền riêng, đặc biệt với SERIAL

Một lỗi phổ biến: người dùng đã có `INSERT` trên bảng nhưng vẫn bị báo `permission denied for sequence`.

### 12.1. Tạo bảng dùng BIGSERIAL

Bổ sung ví dụ:

```sql
SET ROLE lab376_owner;

CREATE TABLE lab_acl_376.legacy_jobs (
    job_id BIGSERIAL PRIMARY KEY,
    job_title TEXT NOT NULL
);

GRANT SELECT, INSERT
ON lab_acl_376.legacy_jobs
TO lab376_writer;

RESET ROLE;
```

`BIGSERIAL` của PostgreSQL là cú pháp thuận tiện tạo một sequence và default expression gọi `nextval(...)`. Sequence thường có tên `lab_acl_376.legacy_jobs_job_id_seq`. Có thể xác định chính xác:

```sql
SELECT pg_get_serial_sequence(
    'lab_acl_376.legacy_jobs', 'job_id'
);
```

Nếu writer thử:

```sql
SET ROLE lab376_writer;

-- Có thể lỗi quyền sequence trong cấu hình mặc định.
INSERT INTO lab_acl_376.legacy_jobs (job_title)
VALUES ('Lập báo cáo')
RETURNING job_id;

RESET ROLE;
```

thì default `nextval` cần quyền thích hợp trên sequence, **khác** với quyền INSERT trên bảng.

### 12.2. Cấp USAGE đúng sequence

```sql
SET ROLE lab376_owner;

GRANT USAGE
ON SEQUENCE lab_acl_376.legacy_jobs_job_id_seq
TO lab376_writer;

RESET ROLE;
```

Sau đó INSERT sử dụng default sinh ID có thể thành công theo những quyền bảng đã cấp.

Sequence có những quyền như `USAGE`, `SELECT`, `UPDATE` liên quan đến thao tác `nextval`, `currval`, `setval` theo quy tắc cụ thể của PostgreSQL. `UPDATE ON SEQUENCE` không đồng nghĩa `UPDATE ON TABLE`.

### 12.3. Identity và SERIAL không hoàn toàn như nhau

Bảng `tickets`/`accounts` dùng `GENERATED ALWAYS AS IDENTITY`. Cơ chế sinh ID ở cột identity không có hoàn toàn cùng yêu cầu quyền sequence với default gọi `nextval` của `SERIAL`. Vì vậy không nên tự cấp `USAGE ON ALL SEQUENCES` rộng khắp chỉ vì một ứng dụng gặp lỗi ở bảng SERIAL.

Khoảng trống trong sequence/identity không nhất thiết là dữ liệu bị mất: rollback và cấp phát trước có thể khiến ID không liên tục.

## 13. Quyền REFERENCES, TRIGGER và TRUNCATE là những khả năng riêng

| Quyền | Phạm vi trong PostgreSQL | Vì sao cần tách |
| --- | --- | --- |
| `REFERENCES` | Sử dụng bảng/cột làm đích tham chiếu FK theo điều kiện phù hợp | Không đồng nghĩa SELECT |
| `TRIGGER` | Tạo trigger trên bảng nếu đáp ứng các điều kiện khác | Không đồng nghĩa EXECUTE routine |
| `TRUNCATE` | Chạy TRUNCATE trên bảng | Khác DELETE và có ảnh hưởng lớn |
| `DELETE` | Xóa hàng thỏa điều kiện | Không mặc định được TRUNCATE |
| `EXECUTE` | Gọi function/procedure được cấp | Không đồng nghĩa tạo trigger hoặc đọc bảng bên trong |

Một role chỉ cần gọi `close_ticket` **không cần** `TRIGGER ON tickets`. Một role chỉ cần `DELETE` một số hàng **không nên mặc nhiên nhận TRUNCATE**, vì thao tác này có thể xóa hàng loạt dữ liệu.

Việc tạo trigger hoặc FK thường còn đòi những quyền trên object liên quan. Không xem bảng này như lời hứa chỉ cần một GRANT là có thể làm mọi thao tác cấu trúc.

## 14. Quyền DDL: CREATE không đồng nghĩa sở hữu bảng đã có

Với PostgreSQL, owner có khả năng quản trị định nghĩa đối tượng, còn người được `GRANT` quyền bảng chủ yếu thực hiện thao tác trên dữ liệu và các quyền liên quan.

### 14.1. GRANT ALL ON TABLE vẫn không phải owner

```sql
-- Ví dụ rất rộng, không áp dụng vào ma trận bài học.
GRANT ALL PRIVILEGES
ON lab_acl_376.tickets
TO lab376_writer;
```

Ngay cả khi nhận quyền bảng rộng, writer **không vì thế trở thành owner** của `tickets` để tùy ý `ALTER TABLE` hoặc `DROP TABLE`. Quyền sở hữu và các quyền quản trị theo membership là một khái niệm khác.

### 14.2. CREATE ON SCHEMA chỉ cho phép tạo đối tượng

```sql
-- Ví dụ cấu trúc, limited_builder chưa tồn tại:
GRANT CREATE ON SCHEMA lab_acl_376 TO limited_builder;
```

Nếu được cấp hợp lệ, role có thể tạo đối tượng thuộc loại phù hợp trong schema. Điều này không tự cấp quyền ALTER/DROP bảng `tickets` do `lab376_owner` sở hữu.

Không nên cấp CREATE trên schema chứa các object được SECURITY DEFINER gọi bằng tên không bảo vệ, vì khả năng tạo object trong đường tìm tên có thể mở lỗ hổng `search_path`.

### 14.3. Migration có đường quyền tách riêng

Mô hình thường phù hợp:

```text
App runtime        → reader / writer / routine_executor
CI/CD migration    → owner/DDL role có kiểm soát
Support vận hành   → role theo nhiệm vụ, cấp tạm khi cần
```

Role owner `NOLOGIN` có thể được sử dụng qua `SET ROLE` bởi account triển khai có membership phù hợp. Không đưa membership owner vào account ứng dụng chỉ để tránh lỗi permission.

Một migration cần được kiểm soát bằng review, backup/migration plan, secret management và logging; quyền DDL rộng thường không nên tồn tại trong mọi instance dịch vụ hằng ngày.

## 15. Quyền mặc định cho object tương lai

Cấp quyền trên các bảng hiện có **không đồng nghĩa** bảng mới sẽ tự nhận những quyền ấy.

### 15.1. ON ALL TABLES IN SCHEMA chỉ áp dụng các bảng đã có

```sql
-- Ví dụ quyền rộng, KHÔNG chạy nếu muốn giữ
-- bảo vệ cột email/internal_note ở phần 11:
GRANT SELECT
ON ALL TABLES IN SCHEMA lab_acl_376
TO lab376_reader;
```

Lệnh cấp trên các bảng hiện hữu ở thời điểm chạy. Nó có thể vô tình mở quyền toàn bộ cột của `customer_contacts`, nên không phù hợp mô hình cấp quyền theo cột của bài.

### 15.2. ALTER DEFAULT PRIVILEGES áp dụng về sau

```sql
-- Ví dụ chính sách, không chạy trong mô hình chính.
ALTER DEFAULT PRIVILEGES
FOR ROLE lab376_owner
IN SCHEMA lab_acl_376
GRANT SELECT ON TABLES TO lab376_reader;
```

Điều này thiết lập quyền mặc định cho bảng **sẽ được tạo về sau** trong schema, bởi **role tạo đối tượng được chỉ định** theo quy tắc PostgreSQL. Nó:

- Không hồi tố với bảng cũ.
- Không mặc định áp dụng cho object do một role khác tạo dù role đó thuộc nhóm owner, nếu current role tạo object khác.
- Có nguy cơ công bố bảng nhạy cảm mới nếu mọi bảng cùng schema nhận SELECT.

Với dữ liệu nhiều mức nhạy cảm, tách schema `reporting`/`finance` hoặc duyệt từng GRANT trong migration có thể tốt hơn một default SELECT áp dụng toàn bộ.

### 15.3. Routine mới thường có EXECUTE cho PUBLIC

Theo mặc định PostgreSQL, khi một function được tạo, `PUBLIC` thường có thể EXECUTE nếu chưa thay default privileges. Đó là lý do phần 6 và 7 thực hiện:

```sql
BEGIN;
CREATE FUNCTION ...;
REVOKE ALL ON FUNCTION ... FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ... TO approved_role;
COMMIT;
```

Các câu có dấu `...` chỉ minh họa luồng, không phải SQL chạy trực tiếp.

Khi các bước tạo và thu hồi ở **cùng transaction**, không xuất hiện khoảng thời gian đã commit mà routine nhạy cảm vẫn được EXECUTE rộng trước khi bị REVOKE.

### 15.4. Chặn default PUBLIC cho routine của một owner

Một chính sách riêng có thể là:

```sql
-- Ví dụ tùy chọn, ảnh hưởng future routines được
-- tạo bởi lab376_owner trong database hiện tại.
ALTER DEFAULT PRIVILEGES
FOR ROLE lab376_owner
REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
```

Phạm vi của thao tác mặc định cần được hiểu theo **role tạo object và database**, không chỉ theo schema. Trong PostgreSQL, default privileges theo schema là phần bổ sung vào mặc định toàn cục, nên một `REVOKE ... IN SCHEMA ... FROM PUBLIC` không phải lúc nào cũng phủ định được một grant PUBLIC từ mặc định toàn cục.

Nếu đang vận hành owner dùng chung nhiều schema, cần review tác động trước khi thay đổi mặc định.

### 15.5. Xem default privileges

Trong psql:

```text
\ddp
```

Đây là meta-command của psql, không phải câu SQL dùng trực tiếp trong JDBC. Có thể xem catalog `pg_default_acl` khi cần công cụ kiểm toán tự động.

## 16. SECURITY INVOKER: có EXECUTE vẫn có thể thiếu quyền đọc

Function `transfer_funds` dùng `SECURITY DEFINER`. Nếu function dùng `SECURITY INVOKER` (mặc định), quyền trên bảng bên trong được xét theo người gọi.

### 16.1. Tạo function đọc dưới quyền invoker

```sql
SET ROLE lab376_owner;

BEGIN;

CREATE FUNCTION lab_acl_376.count_open_tickets()
RETURNS BIGINT
LANGUAGE SQL
SECURITY INVOKER
AS $$
    SELECT COUNT(*)
    FROM lab_acl_376.tickets
    WHERE status = 'open'
$$;

REVOKE ALL
ON FUNCTION lab_acl_376.count_open_tickets()
FROM PUBLIC;

GRANT EXECUTE
ON FUNCTION lab_acl_376.count_open_tickets()
TO lab376_reader, lab376_executor;

COMMIT;

RESET ROLE;
```

### 16.2. Reader có đủ EXECUTE và SELECT

```sql
SET ROLE lab376_reader;

SELECT lab_acl_376.count_open_tickets();

RESET ROLE;
```

Câu gọi hợp lệ vì reader có `EXECUTE` trên function và `SELECT` trên tickets.

### 16.3. Executor có EXECUTE nhưng không có SELECT

```sql
SET ROLE lab376_executor;

-- CỐ Ý LỖI: SECURITY INVOKER cần SELECT trên tickets.
SELECT lab_acl_376.count_open_tickets();

RESET ROLE;
```

Executor **được gọi** function, nhưng câu SQL bên trong vẫn đụng bảng theo quyền executor và có thể bị từ chối.

| Mode routine | Quyền nào được dùng cho thao tác bên trong? |
| --- | --- |
| `SECURITY INVOKER` | Quyền của người gọi |
| `SECURITY DEFINER` | Quyền của chủ sở hữu routine, trong giới hạn và cơ chế DBMS |

**GRANT EXECUTE chỉ mở quyền gọi routine**; nó không tự cấp SELECT/UPDATE cho câu SQL bên trong khi routine là invoker.

## 17. SECURITY DEFINER cần bảo vệ như một API quyền cao

SECURITY DEFINER giúp ứng dụng thực hiện một nghiệp vụ giới hạn, nhưng nếu routine nhận đầu vào tùy ý, nó có thể trở thành cánh cửa vượt rào bảo mật.

### 17.1. Không dùng owner superuser khi không cần

`transfer_funds` chỉ cần cập nhật `accounts`. Owner của function nên là role có quyền vừa đủ trên bảng này, không mặc định là superuser.

Trong bài, `lab376_owner` là `NOLOGIN` và sở hữu những object mẫu. Ở hệ thống lớn, có thể tách **owner routine** ra khỏi **owner DDL toàn schema** để giới hạn thêm các quyền mà SECURITY DEFINER có thể dùng.

### 17.2. search_path và object giả mạo

Một function quyền cao dùng tên không đủ schema:

```sql
SELECT * FROM accounts;
```

có thể bị ảnh hưởng bởi `search_path` nếu caller hoặc một role khác có thể tạo object trong schema nằm trên đường tìm tên.

Mẫu tốt hơn:

```sql
SECURITY DEFINER
SET search_path = pg_catalog, trusted_schema, pg_temp
```

cùng việc chỉ dùng schema đáng tin cậy và viết đầy đủ `schema.table` với các object nhạy cảm. Trong bộ demo, `lab_acl_376` chỉ do owner có CREATE.

### 17.3. Dynamic SQL không được ghép trực tiếp từ đầu vào

**Ví dụ không an toàn** bên trong PL/pgSQL:

```sql
EXECUTE 'DELETE FROM ' || user_supplied_table_name;
```

Nếu một caller được tự chọn bảng và function chạy với quyền definer, đây là một bề mặt nguy hiểm.

Với dynamic SQL không thể tránh:

- Chỉ cho phép tên bảng/schema nằm trong **allowlist**.
- Quote tên định danh bằng `format('%I', ...)` hoặc hàm quoting thích hợp.
- Dùng bind parameters cho **giá trị**, ví dụ `EXECUTE ... USING`.
- Không dùng quote identifier như sự thay thế cho authorization nghiệp vụ.

Mẫu ý tưởng:

```sql
-- Phải validate tên schema/bảng theo allowlist trước.
EXECUTE format(
    'SELECT COUNT(*) FROM %I.%I WHERE status = $1',
    requested_schema,
    requested_table
)
INTO result_count
USING requested_status;
```

Ngay cả một identifier được quote đúng vẫn có thể là **bảng mà caller không nên được yêu cầu function quyền cao đọc**. Vì vậy cần cả kiểm tra quyền nghiệp vụ.

### 17.4. SECURITY DEFINER không tự xác minh chủ tài khoản

Function `transfer_funds` minh họa mô hình mà toàn bộ `lab376_executor` là **dịch vụ đáng tin cậy, được cho phép chuyển tiền giữa mọi tài khoản trong dữ liệu mẫu**. Nó **không** xác minh một người dùng cuối cụ thể có sở hữu tài khoản 1 hay không.

Trong ứng dụng thật, cần bổ sung xác thực danh tính, hạn mức, trạng thái tài khoản, phê duyệt, audit, ledger, idempotency và chống replay. Không được lấy tham số `p_sender_id` do client tự gửi làm bằng chứng client là chủ tài khoản.

### 17.5. Routine có thể làm lộ dữ liệu dù không có SELECT trên bảng

Một SECURITY DEFINER function trả danh sách số dư từ bảng accounts có thể cho người được EXECUTE **đọc dữ liệu qua kết quả function** dù họ không có SELECT trực tiếp trên accounts.

Vì thế, phải review **cả đầu ra, tác dụng phụ và SQL bên trong routine** khi cấp EXECUTE, không chỉ nhìn bảng GRANT.

## 18. View và Row-Level Security: kiểm soát dữ liệu được nhìn thấy

`GRANT SELECT ON TABLE` trả lời câu hỏi role có thể đọc **bảng nào**. Hai câu hỏi khác cũng quan trọng:

- Role được xem **cột nào**?
- Role được xem **hàng nào**?

Quyền theo cột giải quyết một phần câu hỏi thứ nhất. View và Row-Level Security (RLS) có thể hỗ trợ ràng buộc thêm ở cấp dữ liệu.

### 18.1. View như một giao diện đọc hẹp

Role owner tạo view chỉ công bố ID và nhãn tài khoản, không trả số dư:

```sql
SET ROLE lab376_owner;

CREATE VIEW lab_acl_376.v_account_labels AS
SELECT account_id, account_label
FROM lab_acl_376.accounts;

GRANT SELECT ON lab_acl_376.v_account_labels
TO lab376_executor;

RESET ROLE;
```

Executor chưa có `SELECT` trực tiếp trên `accounts`, nhưng với quyền SELECT trên view mới, nó có thể:

```sql
SET ROLE lab376_executor;

SELECT account_id, account_label
FROM lab_acl_376.v_account_labels
ORDER BY account_id;

RESET ROLE;
```

Trong PostgreSQL, view thông thường mặc định sử dụng quyền của **owner view** khi truy cập bảng nền theo cơ chế của PostgreSQL, vì thế user chỉ có quyền trên view có thể được phép đọc kết quả view mà không có quyền SELECT trên bảng nguồn.

**Đây là một khả năng truy cập gián tiếp cần kiểm toán.** Nếu sau này sửa view để xuất thêm `balance`, executor có thể nhìn thấy số dư mà trước đây không được thấy. Thay đổi định nghĩa view đôi khi cũng là thay đổi chính sách công bố dữ liệu.

### 18.2. security_invoker của view trong PostgreSQL 15+

PostgreSQL có tùy chọn:

```sql
SET ROLE lab376_owner;

CREATE VIEW lab_acl_376.v_account_labels_invoker
WITH (security_invoker = true) AS
SELECT account_id, account_label
FROM lab_acl_376.accounts;

GRANT SELECT
ON lab_acl_376.v_account_labels_invoker
TO lab376_executor;

RESET ROLE;
```

Với `security_invoker=true`, quyền truy cập bảng nền được xét theo **người gọi**. Vì executor vẫn không có SELECT trên accounts, nó có thể bị từ chối khi truy vấn view invoker dù đã có SELECT trên chính view.

Đừng suy luận từ tên `VIEW` rằng nó luôn chạy bằng quyền owner hoặc luôn chạy bằng quyền invoker: phải xem tùy chọn, phiên bản PostgreSQL và các vai trò thực tế.

### 18.3. RLS bảo vệ theo hàng

Một bảng nhiều tenant có thể cần bảo đảm role tenant 1 không đọc dữ liệu tenant 2. GRANT SELECT trên bảng **không tự lọc tenant**.

Minh họa RLS bằng một bảng độc lập trong schema bài học:

```sql
SET ROLE lab376_owner;

CREATE TABLE lab_acl_376.tenant_notes (
    note_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    note_text TEXT NOT NULL
);

INSERT INTO lab_acl_376.tenant_notes (tenant_id, note_text)
VALUES
    (1, 'Ghi chú tenant 1'),
    (2, 'Ghi chú tenant 2');

ALTER TABLE lab_acl_376.tenant_notes
ENABLE ROW LEVEL SECURITY;

CREATE POLICY read_tenant1_notes
ON lab_acl_376.tenant_notes
FOR SELECT
TO lab376_reader
USING (tenant_id = 1);

GRANT SELECT
ON lab_acl_376.tenant_notes
TO lab376_reader;

RESET ROLE;
```

Thử với reader:

```sql
SET ROLE lab376_reader;

SELECT tenant_id, note_text
FROM lab_acl_376.tenant_notes
ORDER BY tenant_id;

RESET ROLE;
```

Trong mô hình này, reader chỉ thấy **hàng của tenant 1**, dù bảng nguồn có thêm hàng tenant 2.

### 18.4. RLS không thay GRANT

RLS không tự cấp `SELECT`. Một user phải có quyền object thích hợp rồi các policy liên quan mới quyết định những hàng có thể nhìn thấy/thay đổi.

Các điểm cần lưu ý:

- Chủ sở hữu bảng thường có thể vượt RLS theo mặc định, trừ khi dùng cơ chế như `FORCE ROW LEVEL SECURITY` phù hợp.
- Superuser và role có `BYPASSRLS` có quyền đặc biệt đối với RLS.
- SECURITY DEFINER routine hoặc view dùng quyền owner có thể thay đổi cách RLS áp dụng so với quyền caller trực tiếp.
- Một biến session như `app.tenant_id` chỉ an toàn làm nguồn chính sách nếu thiết kế bảo đảm người gọi **không thể tự giả mạo định danh tenant**; không tin hoàn toàn giá trị do client SQL có thể tùy ý thiết lập.

RLS phù hợp với **phạm vi hàng**, GRANT phù hợp với **loại thao tác và đối tượng**, còn routine có thể đóng gói **quy tắc nghiệp vụ**. Một giải pháp bảo mật thường cần phối hợp các lớp này.

## 19. Quyền trong transaction, connection pool và ứng dụng Java

Quyền database phải được thực thi qua **đúng tài khoản kết nối**. Nếu mọi request từ người đọc lẫn người quản trị đều dùng cùng một DB credential có toàn quyền, việc ứng dụng tự phân biệt user ở giao diện không thay thế được kiểm soát ở database.

### 19.1. Tách DataSource theo công việc

Một ứng dụng Java có thể cấu hình các connection pool khác nhau:

```text
reportDataSource    → login có quyền reader
commandDataSource   → login có quyền writer
routineDataSource   → login có quyền executor
migrationDataSource → login triển khai (không dùng cho runtime)
```

Không nhất thiết mỗi method phải dùng một database user riêng, nhưng các luồng tin cậy khác nhau nên có đường quyền rõ. Nếu ứng dụng có pool quyền cao và vô tình dùng nó cho truy vấn từ input không tin cậy, quyền SQL hẹp của pool khác sẽ không cứu được thao tác.

### 19.2. PreparedStatement bảo vệ giá trị, không thay GRANT

Ví dụ JDBC:

```java
String sql = """
    SELECT ticket_id, title, status
    FROM lab_acl_376.tickets
    WHERE ticket_id = ?
    """;

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setLong(1, requestedTicketId);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString("title"));
        }
    }
}
```

`PreparedStatement` bind **giá trị** thay vì nối chuỗi từ người dùng, giúp chống SQL injection cho tham số dữ liệu. Nhưng nó không tự cấp SELECT cho connection; truy vấn vẫn cần role có quyền.

Ngược lại, role chỉ có SELECT cũng không miễn trừ nhu cầu parameterization: SQL injection có thể đọc dữ liệu ngoài dự kiến **trong phạm vi quyền mà connection sở hữu**, ví dụ thay đổi bộ lọc hoặc truy vấn vào bảng khác được phép.

### 19.3. Tên bảng/column không phải tham số dữ liệu

Không thể dùng một dấu `?` thông thường để thay thế tên bảng theo cách bind giá trị:

```sql
-- Không phải ý tưởng đúng để bind tên bảng:
SELECT * FROM ? WHERE ticket_id = ?;
```

Khi cần chọn đối tượng động, phải dùng **allowlist** tên bảng/cột được phép, định dạng identifier đúng chuẩn DBMS và không cung cấp quyền rộng cho query builder.

### 19.4. Transaction READ ONLY không phải tài khoản chỉ đọc

Trong PostgreSQL:

```sql
BEGIN READ ONLY;
SELECT * FROM lab_acl_376.tickets;
COMMIT;
```

`READ ONLY` của transaction là một lớp hạn chế thao tác ghi ở transaction hiện tại. Nó **không thay thế role chỉ có quyền SELECT**, và một application role có UPDATE vẫn có thể ghi trong transaction khác nếu không còn READ ONLY.

Nếu mục tiêu là bảo đảm credential báo cáo không thể cập nhật dữ liệu, hãy **thu hồi quyền ghi ở cấp role** chứ không chỉ gọi `Connection.setReadOnly(true)` hoặc `BEGIN READ ONLY`.

### 19.5. SET ROLE và connection pool

Nếu một pool dùng session lâu dài và ứng dụng gọi:

```sql
SET ROLE lab376_owner;
```

để chạy migration hay thao tác quyền cao, rồi trả connection vào pool mà không reset, request sau có thể thừa hưởng vai trò cao theo cấu hình/session. Đây là rủi ro nghiêm trọng.

Tốt hơn là **tách migration credentials khỏi pool runtime**, quản lý role changes và bảo đảm reset state khi trả connection. `RESET ROLE` trong ví dụ học tập không thay thế toàn bộ cơ chế an toàn của pool production.

## 20. Đặc quyền role cao và đường leo thang quyền

Một số thuộc tính của role trong PostgreSQL mở khả năng rất rộng:

| Đặc tính | Vì sao nhạy cảm |
| --- | --- |
| `SUPERUSER` | Vượt nhiều kiểm tra quyền database |
| `CREATEROLE` | Có khả năng quản trị role trong phạm vi được cấp |
| `CREATEDB` | Có thể tạo database |
| `BYPASSRLS` | Vượt cơ chế Row-Level Security |
| `REPLICATION` | Truy cập các chức năng phục vụ replication |
| Membership có `SET ROLE` sang owner | Có thể nhận quyền quản trị đối tượng của owner |
| `CREATE` trong schema trusted của SECURITY DEFINER | Có thể ảnh hưởng object lookup nếu routine không được bảo vệ |

Không tạo app login `SUPERUSER` chỉ để giải quyết một lỗi `permission denied`.

### 20.1. Owner NOLOGIN là một ranh giới hữu ích

Trong bộ demo, `lab376_owner` không có LOGIN. Account vận hành chỉ được dùng owner qua đường triển khai được phép; các role runtime không là thành viên owner.

Cách này làm rõ ai có quyền DDL. Tuy nhiên, NOLOGIN không tự biến object hoàn toàn an toàn nếu owner membership bị cấp quá rộng hoặc SECURITY DEFINER function có lỗi.

### 20.2. Membership là một grant có tác động thực

Một cấu trúc triển khai có thể viết:

```sql
-- Ví dụ tên login giả định, không thuộc bộ sandbox:
GRANT lab376_reader TO reporting_login;
```

Account `reporting_login` có thể nhận quyền nhóm theo chế độ membership của phiên bản PostgreSQL. Khi kiểm toán, phải xem cả quan hệ role cha–con, `INHERIT`, `SET` và `ADMIN` theo phiên bản, không chỉ các câu GRANT trên bảng.

## 21. Kiểm tra quyền hiệu lực trong PostgreSQL

### 21.1. Kiểm tra quyền bảng

```sql
SELECT
    r.role_name,
    has_table_privilege(
        r.role_name, 'lab_acl_376.tickets', 'SELECT'
    ) AS can_select_tickets,
    has_table_privilege(
        r.role_name, 'lab_acl_376.tickets', 'INSERT'
    ) AS can_insert_tickets,
    has_table_privilege(
        r.role_name, 'lab_acl_376.accounts', 'UPDATE'
    ) AS can_update_accounts
FROM (
    VALUES
        ('lab376_reader'),
        ('lab376_writer'),
        ('lab376_executor')
) AS r(role_name)
ORDER BY r.role_name;
```

Kết quả dự kiến nếu chỉ thực hiện grants của ví dụ:

| Role | SELECT tickets | INSERT tickets | UPDATE accounts |
| --- | --- | --- | --- |
| Reader | true | false | false |
| Writer | true | true | false |
| Executor | false | false | false |

`has_table_privilege` giúp xác định quyền ở cấp bảng, nhưng một câu SQL vẫn có thể lỗi vì thiếu `USAGE` schema, quyền theo cột, RLS, CHECK, trigger hoặc transaction mode.

### 21.2. Kiểm tra quyền schema

```sql
SELECT
    has_schema_privilege(
        'lab376_reader', 'lab_acl_376', 'USAGE'
    ) AS reader_can_resolve_schema,
    has_schema_privilege(
        'lab376_writer', 'lab_acl_376', 'CREATE'
    ) AS writer_can_create_objects;
```

Mong đợi: `true`, `false`.

### 21.3. Kiểm tra quyền gọi function

```sql
SELECT
    has_function_privilege(
        'lab376_executor',
        'lab_acl_376.transfer_funds(bigint,bigint,numeric)',
        'EXECUTE'
    ) AS executor_can_transfer,
    has_function_privilege(
        'lab376_reader',
        'lab_acl_376.transfer_funds(bigint,bigint,numeric)',
        'EXECUTE'
    ) AS reader_can_transfer;
```

Mong đợi: `true`, `false`.

Khi kiểm tra procedure hay function overload, phải xác định đúng **routine và chữ ký**. Không kết luận từ một tên routine trần nếu schema có nhiều phiên bản cùng tên nhưng kiểu tham số khác.

### 21.4. Meta-command hữu ích trong psql

```text
\du                 -- Vai trò và thuộc tính role
\dp lab_acl_376.*   -- Quyền trên các quan hệ
\dn+ lab_acl_376    -- Schema và thông tin quyền
\df+ lab_acl_376.*  -- Routines
\ddp                -- Default privileges
```

Đây là lệnh **riêng của psql**, không phải SQL có thể gửi nguyên dạng qua JDBC. Trong automation, dùng catalog/metadata SQL tương ứng như `pg_roles`, `pg_class`, `pg_namespace`, `pg_proc`, `pg_default_acl` hoặc hàm kiểm tra quyền có sẵn.

### 21.5. Permission denied khác constraint violation

Một role có `INSERT` trên tickets vẫn có thể bị từ chối vì:

- `title` thiếu, vi phạm `NOT NULL`.
- `status` nằm ngoài `('open', 'done')`, vi phạm `CHECK`.
- Trùng khóa.
- RLS không cho phép hàng mới.
- Trigger nghiệp vụ phát sinh lỗi.
- Transaction đang `READ ONLY`.

Không phải mọi lỗi từ database đều yêu cầu `GRANT` thêm. Hãy xác định đúng loại lỗi trước khi mở rộng quyền.

## 22. Quy trình vận hành và vòng đời quyền

Một mô hình quyền an toàn cần có người phụ trách và quy trình kiểm tra thường xuyên.

### 22.1. Trước khi đưa ứng dụng lên môi trường mới

Xác định:

1. Các tài khoản LOGIN/nhóm role của ứng dụng.
2. Tài khoản triển khai DDL.
3. Những bảng/view mỗi nhóm cần đọc.
4. Những bảng và cột mỗi nhóm cần sửa.
5. Những routine được phép gọi.
6. Các quyền schema/database/sequence cần thiết.
7. Quyền mặc định của object tương lai.
8. Grants từ PUBLIC và role membership.
9. RLS và những đường truy cập qua view/SECURITY DEFINER.
10. Cách kiểm thử từ **credential thực**.

### 22.2. Khi vai trò ứng dụng đổi

Nếu reporting không còn được xem balances, không chỉ `REVOKE SELECT ON accounts` mà còn phải kiểm tra liệu:

- Có view khác trả số dư không?
- Có routine definer trả số dư không?
- Reporting còn nhận SELECT qua role nhóm khác không?
- Dữ liệu đã được lưu ở dashboard, export hoặc cache nào không?

REVOKE bảo vệ truy cập tương lai theo phạm vi được thực thi, **không xóa bản sao dữ liệu đã ra ngoài database**.

### 22.3. Credential bị lộ

Quy trình thường cần: đổi/vô hiệu hóa credential, chấm dứt session không còn tin cậy, rà soát hoạt động, đánh giá dữ liệu đã đọc và tác động ghi, khôi phục khi cần và xem lại quyền quá rộng.

Không hardcode password của tài khoản DDL vào source code hoặc log. Demo dùng role `NOLOGIN` và không chứa secret thật; trong production phải dùng phương thức xác thực và secret management phù hợp.

### 22.4. Audit GRANT, REVOKE và thay đổi định nghĩa routine

Không chỉ lưu các lệnh DML. Một thay đổi như:

```sql
GRANT EXECUTE
ON FUNCTION lab_acl_376.transfer_funds(BIGINT, BIGINT, NUMERIC)
TO another_role;
```

có thể làm mở rộng phạm vi người được chuyển tiền. Tương tự, thay định nghĩa SECURITY DEFINER function mà giữ nguyên quyền EXECUTE có thể làm **mở rộng chức năng** của tất cả caller hiện có.

Vì vậy, migration review nên xem GRANT/REVOKE, OWNER, schema CREATE, search_path và routine body cùng với DDL, không coi chúng là chi tiết không ảnh hưởng bảo mật.

## 23. Khác biệt giữa PostgreSQL và các DBMS khác

Tư duy quyền tối thiểu áp dụng rộng rãi, nhưng cách tổ chức principal, schema, routine và quyền DDL không hoàn toàn giống nhau.

| DBMS | Phân quyền đọc và ghi | DDL và routine |
| --- | --- | --- |
| PostgreSQL | Role, `GRANT SELECT/INSERT/UPDATE/DELETE` trên bảng/cột; schema `USAGE` | Owner/schema `CREATE`; `EXECUTE` function/procedure; SECURITY DEFINER/INVOKER |
| MySQL | User/host; GRANT ở cấp database, table, column | DDL privileges; EXECUTE trên routine; `SQL SECURITY DEFINER/INVOKER` |
| SQL Server | Login/user/role; `GRANT` trên object, schema hoặc database | `ALTER`/`CONTROL` và ownership; `GRANT EXECUTE`; EXECUTE AS và ownership chaining |
| Oracle | System privileges và object privileges | Quyền schema/system; EXECUTE, `AUTHID DEFINER/CURRENT_USER` |
| SQLite | Không có hệ role/GRANT SQL tương đương PostgreSQL | Quyền file/app; không có cùng mô hình stored routine server-side |

### 23.1. MySQL

Ví dụ **cấu trúc**, các tài khoản phải tồn tại và được cấu hình xác thực trước:

```sql
-- Chỉ chạy trên MySQL, không phải PostgreSQL.
GRANT SELECT
ON appdb.tickets
TO 'app_reader'@'localhost';

GRANT INSERT, UPDATE
ON appdb.tickets
TO 'app_writer'@'localhost';

GRANT EXECUTE
ON PROCEDURE appdb.close_ticket
TO 'app_executor'@'localhost';
```

MySQL stored programs có thể có `SQL SECURITY DEFINER` hoặc `INVOKER` theo loại routine. Không tự chuyển nguyên cách dùng role owner, `SET ROLE`, default privileges và search_path của PostgreSQL sang MySQL.

### 23.2. SQL Server

Ví dụ T-SQL:

```sql
-- SQL Server, các database principal đã tồn tại.
GRANT SELECT ON OBJECT::dbo.tickets TO report_reader;
GRANT INSERT, UPDATE ON OBJECT::dbo.tickets TO ticket_writer;
GRANT EXECUTE ON OBJECT::dbo.CloseTicket TO routine_executor;
```

SQL Server có **ownership chaining**, `EXECUTE AS` và module signing cho những mô hình thực thi quyền theo module. Quyền DDL có các khái niệm `ALTER`/`CONTROL` và ownership theo SQL Server, không được suy luận hoàn toàn từ quy tắc owner của PostgreSQL.

### 23.3. Oracle Database

Ví dụ:

```sql
-- Oracle, các user/schema và đối tượng đã tồn tại.
GRANT SELECT ON app_owner.tickets TO report_reader;
GRANT INSERT, UPDATE ON app_owner.tickets TO ticket_writer;
GRANT EXECUTE ON app_owner.transfer_funds TO routine_executor;
```

Oracle PL/SQL có `AUTHID DEFINER` và `AUTHID CURRENT_USER`. Trong một số ngữ cảnh definer-rights named PL/SQL, các quyền được cấp qua role không có cùng hiệu lực với **direct grants** cho owner routine; phải kiểm tra trên Oracle thực tế.

### 23.4. SQLite

SQLite không hỗ trợ server roles và `GRANT`/`REVOKE` SQL giống PostgreSQL. Bảo vệ truy cập thường phụ thuộc quyền file/hệ điều hành, chế độ mở connection và lớp authorization của ứng dụng. `PRAGMA query_only` không phải thay thế hoàn toàn của một hệ ACL database server.

**Khi chuyển DBMS, phải kiểm chứng cả ngữ nghĩa quyền, không chỉ dịch cú pháp.**

## 24. Những lỗi phân quyền phổ biến

| Sai lầm | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Cho app chạy bằng superuser | SQL injection có thể mở rộng thành toàn quyền DB | Runtime role tối thiểu |
| Dùng owner/migration login cho request thông thường | Có thể ALTER/DROP hoặc đổi routine | Tách tài khoản DDL và runtime |
| `GRANT ALL ON ALL TABLES` để chữa một lỗi | Mở DELETE/TRUNCATE và nhiều quyền không cần | Xác định đúng object và privilege thiếu |
| Có SELECT bảng nhưng quên USAGE schema | Query bị từ chối vì thiếu quyền truy cập namespace | Cấp USAGE đúng schema |
| Có INSERT SERIAL nhưng quên sequence | `nextval` bị từ chối | Cấp USAGE đúng sequence |
| Cấp SELECT toàn bảng thay vì hai cột | Lộ email/ghi chú nhạy cảm | Column privileges hoặc view phù hợp |
| Chỉ kiểm tra direct grants | Bỏ quyền qua PUBLIC/membership | Kiểm tra quyền hiệu lực |
| Cho app membership owner để tiện migration | App có đường nâng quyền DDL | Deploy role riêng |
| Cấp EXECUTE cho tất cả functions | Gọi được routine chưa được duyệt | Cấp theo chữ ký cần thiết |
| Quên default EXECUTE của PUBLIC | Function mới bị gọi ngoài dự định | REVOKE trong transaction và default privileges đúng |
| Cho rằng EXECUTE luôn cho phép truy cập bảng trong routine | Function INVOKER vẫn cần quyền nguồn | Hiểu mode routine |
| SECURITY DEFINER dùng search_path không tin cậy | Object giả mạo có thể chạy bằng quyền definer | Trusted schema, qualify name |
| SECURITY DEFINER dùng SQL động ghép input | Mở quyền đọc/sửa bảng ngoài dự kiến | Allowlist, quote identifier, bind values |
| Function nhận account_id bất kỳ không xác minh chủ sở hữu | Caller lạm dụng quyền ứng dụng | Authorization nghiệp vụ trong routine |
| Cho rằng GRANT SELECT tự cách ly tenant | Người dùng có thể đọc mọi hàng được cấp | RLS/authorization phù hợp |
| Đọc qua view/routine mà bỏ qua đường gián tiếp | Có thể thấy dữ liệu dù không có SELECT bảng nguồn | Audit API dữ liệu và definer ownership |
| Dùng `BEGIN READ ONLY` thay role read-only | Request khác có thể ghi | Thu hồi DML ở credential |
| Quên reset `SET ROLE` trong pool | Request sau thừa hưởng role cao | Reset session, tách pools |
| Hiểu lỗi CHECK là lỗi thiếu GRANT | Mở rộng quyền không giải quyết dữ liệu sai | Phân loại lỗi chính xác |
| Default privileges không được xem cùng migration | Bảng/routine mới mở quyền ngoài dự định | Review GRANT và defaults khi deploy |

### 24.1. Không xem quyền trên bảng là toàn bộ mô hình bảo mật

Một role thiếu SELECT bảng nhưng có EXECUTE routine definer trả dữ liệu vẫn có thể đọc qua routine. Một user có SELECT bảng nhưng RLS chỉ cho xem một tenant không mặc nhiên nhìn thấy mọi hàng. Vì thế, phải kiểm tra **câu SQL thực tế và mọi đường truy cập**, không chỉ danh sách lệnh GRANT.

### 24.2. Không dùng quyền cao để bỏ qua lỗi nghiệp vụ

`CHECK`, `NOT NULL`, `UNIQUE`, `FOREIGN KEY` và trigger có thể chặn câu lệnh dù role đã có quyền INSERT/UPDATE. Cấp superuser để “sửa lỗi” thường làm tăng rủi ro mà không giải quyết nguyên nhân.

## 25. Bài tập thực hành có đáp án

Các bài dùng role và object trong schema `lab_acl_376` đã tạo ở phần 4–18, trừ khi nêu rõ là tình huống giả định. Với câu lệnh cố ý lỗi, nếu đang trong PostgreSQL transaction tường minh, cần khôi phục bằng `ROLLBACK`/savepoint trước khi thử câu khác.

### Bài 1 — Quyền đọc

Một nhóm chỉ cần xem tickets. Những quyền chính cần có?

**Đáp án:** Kết nối database và USAGE schema phù hợp, cộng `SELECT ON tickets`. Không cần INSERT/UPDATE/DELETE hay DDL.

### Bài 2 — Quyền ghi

Nhóm thêm ticket, sửa status, nhưng không xóa. Nên cấp?

**Đáp án:** `INSERT`, `UPDATE` và những quyền `SELECT` cần cho WHERE/RETURNING trên tickets; không cấp DELETE/TRUNCATE/owner.

### Bài 3 — Quyền DDL

Một app chỉ có `GRANT ALL PRIVILEGES ON TABLE tickets`. Nó chắc chắn ALTER/DROP bảng được không?

**Đáp án:** Không. PostgreSQL phân biệt quyền bảng với quyền owner/DDL.

### Bài 4 — Routine executor

Vì sao `lab376_executor` chuyển tiền được nhưng không trực tiếp UPDATE accounts?

**Đáp án:** Nó có EXECUTE trên `transfer_funds` SECURITY DEFINER. Câu SQL bên trong chạy theo quyền của owner; executor không có quyền UPDATE bảng trực tiếp.

### Bài 5 — Schema usage

Có SELECT trên tickets nhưng thiếu USAGE schema có thể gặp lỗi gì?

**Đáp án:** Không đủ quyền truy cập đối tượng trong namespace; cần cấp USAGE schema phù hợp.

### Bài 6 — Quyền cột

Viết lệnh chỉ cho reader đọc contact_id và display_name.

**Đáp án:**

```sql
GRANT SELECT (contact_id, display_name)
ON lab_acl_376.customer_contacts
TO lab376_reader;
```

### Bài 7 — SELECT *

Nếu reader chỉ có SELECT hai cột trên contacts, `SELECT *` có thành công không?

**Đáp án:** Không nếu `*` bao gồm email/internal_note chưa được cấp.

### Bài 8 — WHERE cần quyền đọc

Role chỉ có UPDATE(status) nhưng câu UPDATE dùng WHERE ticket_id. Có thể thiếu gì?

**Đáp án:** Có thể thiếu SELECT trên ticket_id trong điều kiện, hoặc các cột được RETURNING.

### Bài 9 — SERIAL

Writer có INSERT bảng legacy_jobs nhưng lỗi sequence. Cấp gì?

**Đáp án:**

```sql
GRANT USAGE
ON SEQUENCE lab_acl_376.legacy_jobs_job_id_seq
TO lab376_writer;
```

### Bài 10 — Identity và SERIAL

Có thể khẳng định mọi cột GENERATED ALWAYS AS IDENTITY đều cần quyền USAGE sequence như SERIAL không?

**Đáp án:** Không. Cơ chế identity và default `nextval` có khác biệt về xử lý quyền; phải xem DBMS/kiểu cột thực tế.

### Bài 11 — DELETE và TRUNCATE

Được DELETE trên bảng thì có tự được TRUNCATE không?

**Đáp án:** Không. PostgreSQL có quyền TRUNCATE riêng.

### Bài 12 — CREATE và ALTER

Có CREATE ON SCHEMA thì có tự ALTER bảng của owner khác không?

**Đáp án:** Không. Quyền tạo object và ownership của object hiện hữu là hai phạm vi khác nhau.

### Bài 13 — EXECUTE function

Viết GRANT cụ thể cho function transfer_funds.

**Đáp án:**

```sql
GRANT EXECUTE
ON FUNCTION lab_acl_376.transfer_funds(BIGINT, BIGINT, NUMERIC)
TO lab376_executor;
```

### Bài 14 — EXECUTE procedure

Viết GRANT cho close_ticket.

**Đáp án:**

```sql
GRANT EXECUTE
ON PROCEDURE lab_acl_376.close_ticket(BIGINT)
TO lab376_executor;
```

### Bài 15 — Overload

Vì sao trong GRANT FUNCTION phải quan tâm chữ ký?

**Đáp án:** Nhiều function cùng tên có thể khác danh sách kiểu tham số; cần cấp đúng routine định gọi, không tự mở rộng cho mọi overload.

### Bài 16 — PUBLIC

Một function mới có thể được PUBLIC EXECUTE. Phòng ngừa thế nào?

**Đáp án:** Dùng `REVOKE ... FROM PUBLIC` trong cùng transaction tạo function và chỉ GRANT EXECUTE cho nhóm được duyệt; hoặc cấu hình default privileges đúng owner/phạm vi.

### Bài 17 — REVOKE theo đường quyền

Tài khoản bị REVOKE SELECT trực tiếp nhưng vẫn thuộc nhóm có SELECT. Có thể tiếp tục đọc không?

**Đáp án:** Có, theo đường membership được kế thừa/SET phù hợp. Phải kiểm tra quyền hiệu lực, không chỉ direct GRANT.

### Bài 18 — Bảng tương lai

`GRANT SELECT ON ALL TABLES IN SCHEMA ...` có tự cấp SELECT cho bảng sẽ tạo tháng sau không?

**Đáp án:** Không. Nó cấp trên bảng đã có; cần `ALTER DEFAULT PRIVILEGES` nếu muốn chính sách cho object tương lai.

### Bài 19 — Default privilege có hồi tố không?

Bảng đã tạo trước khi ALTER DEFAULT PRIVILEGES có tự nhận quyền mới?

**Đáp án:** Không. Phải GRANT riêng nếu muốn đổi quyền bảng cũ.

### Bài 20 — Role tạo object

Một account là member `lab376_owner` nhưng tạo bảng với current_role khác. Default privileges FOR ROLE lab376_owner có tự áp dụng chắc chắn?

**Đáp án:** Không. Cần kiểm tra role **thực sự tạo đối tượng**, không chỉ membership.

### Bài 21 — SECURITY INVOKER

Executor có EXECUTE `count_open_tickets` nhưng không có SELECT tickets. Kết quả gọi?

**Đáp án:** Bị từ chối khi function invoker cố đọc tickets theo quyền executor.

### Bài 22 — SECURITY DEFINER

Function definer có thể giúp caller vượt thiếu quyền bảng trực tiếp không?

**Đáp án:** Có, nếu function owner có quyền và function được thiết kế cho phép. Vì vậy cần review body, input/output và quyền của owner.

### Bài 23 — search_path

Vì sao SECURITY DEFINER nên dùng trusted search_path và tên bảng có schema?

**Đáp án:** Tránh tên đối tượng bị một role khác giả mạo trong đường tìm kiếm khiến SQL thực thi với quyền definer.

### Bài 24 — SQL động

Chỉ dùng `format('%I', user_table)` mà không allowlist đã an toàn toàn bộ chưa?

**Đáp án:** Chưa. Quote đúng cú pháp không ngăn caller yêu cầu một bảng hợp lệ mà họ không có quyền được function đọc. Vẫn cần allowlist và authorization.

### Bài 25 — Quyền nghiệp vụ theo account

Executor có EXECUTE transfer_funds, điều này chứng minh người dùng cuối sở hữu tài khoản nguồn không?

**Đáp án:** Không. Function mẫu coi executor là dịch vụ tin cậy; production cần xác minh quyền theo account và danh tính caller.

### Bài 26 — View thường

Executor có SELECT view v_account_labels nhưng không SELECT accounts. Có thể xem nhãn qua view không?

**Đáp án:** Có trong mô hình owner-based view PostgreSQL mặc định khi quyền view được cấp và owner có quyền bảng nền.

### Bài 27 — View invoker

View dùng `security_invoker=true`. Executor chỉ có SELECT view, không SELECT accounts. Có thể gặp lỗi không?

**Đáp án:** Có, vì quyền bảng nền được kiểm tra theo caller.

### Bài 28 — RLS

Reader có SELECT tenant_notes nhưng RLS policy chỉ `tenant_id=1`. Kết quả?

**Đáp án:** Chỉ nhìn hàng tenant 1 trong mô hình ví dụ, không tự thấy tenant 2.

### Bài 29 — SET ROLE và pool

Một request SET ROLE owner rồi không reset trước khi trả connection về pool. Rủi ro?

**Đáp án:** Request sau có thể nhận quyền cao ngoài dự định. Tách migration và runtime credentials, reset role/session phù hợp.

### Bài 30 — READ ONLY transaction

Một tài khoản có UPDATE nhưng hiện tại chạy `BEGIN READ ONLY`. Nó trở thành user chỉ đọc vĩnh viễn chưa?

**Đáp án:** Chưa. READ ONLY là mode transaction, không thay đổi GRANT của role.

### Bài 31 — Constraint hay permission?

Writer có INSERT tickets nhưng gửi `status='deleted'`, trong khi CHECK chỉ cho `open`/`done`. Nên cấp thêm GRANT không?

**Đáp án:** Không. Đây là dữ liệu vi phạm CHECK, cần sửa giá trị hoặc chính sách nghiệp vụ.

### Bài 32 — MySQL/SQL Server/Oracle/SQLite

Có thể copy nguyên `GRANT EXECUTE ON FUNCTION ...` của PostgreSQL sang mọi DBMS không?

**Đáp án:** Không. Mỗi engine có cú pháp, mô hình principal/ownership và routine security khác nhau; SQLite còn không có hệ GRANT server-side tương đương.

## 26. Checklist triển khai quyền SQL an toàn

Trước khi cấp quyền cho một dịch vụ hoặc triển khai một schema mới, hãy trả lời các câu hỏi dưới đây.

### 26.1. Danh tính và phạm vi kết nối

1. **Role nào thật sự đăng nhập?** Phân biệt LOGIN account với NOLOGIN group/owner.
2. **Ai tạo bảng và function?** Kiểm tra `current_user` khi migration chạy, không chỉ tên login.
3. **Ứng dụng có dùng owner hoặc superuser không?** Nếu có, xem lại đường quyền runtime.
4. **Role có CONNECT database và USAGE schema cần thiết không?** Hai quyền này khác SELECT bảng.
5. **Có role membership nào mở khả năng SET ROLE sang owner không?** Kiểm tra INHERIT/SET/ADMIN theo phiên bản.
6. **Có quyền cho PUBLIC không?** Đặc biệt EXECUTE routine và các schema công cộng.
7. **Credential có được lưu, luân chuyển và kiểm soát theo môi trường không?** Không hardcode secret.

### 26.2. Quyền đọc và ghi

8. **Reader chỉ SELECT những bảng/view được phép chưa?**
9. **Có cột nào cần ẩn?** Cân nhắc column privileges hoặc view được thiết kế đúng.
10. **Có cần cách ly tenant theo hàng không?** Xem Row-Level Security và các đường bypass.
11. **Writer thật sự cần INSERT, UPDATE, DELETE hay TRUNCATE nào?** Không gộp cả bốn chỉ vì nó là “writer”.
12. **UPDATE/INSERT RETURNING có cần SELECT trên cột liên quan không?**
13. **Bảng SERIAL có cần USAGE trên sequence tương ứng không?** Kiểm tra kiểu sinh ID.
14. **Có quyền REFERENCES/TRIGGER không cần thiết không?**
15. **Một role bị từ chối do thiếu privilege hay do CHECK/FK/UNIQUE/RLS/trigger?** Phân loại lỗi trước khi GRANT thêm.

### 26.3. DDL và routines

16. **Quyền cấu trúc có tách khỏi app runtime không?** Owner/migration role không nên là tài khoản phục vụ request thường.
17. **GRANT CREATE ON SCHEMA có thực sự cần không?** Không mở schema trusted của SECURITY DEFINER cho role kém tin cậy.
18. **Function/procedure nào được EXECUTE?** Cấp theo chữ ký, tránh ALL FUNCTIONS khi không cần.
19. **Routine chạy INVOKER hay DEFINER?** Kiểm tra quyền của các bảng bên trong.
20. **SECURITY DEFINER có owner đủ hẹp không?** Tránh superuser nếu chỉ cần một bảng.
21. **search_path có cố định và schema có đáng tin cậy không?**
22. **Routine có SQL động hay output nhạy cảm không?** Allowlist identifier, bind values và authorization nghiệp vụ.
23. **Routine có thể thao tác trên account/tenant mà caller không sở hữu không?** Thiết kế kiểm tra riêng.
24. **Function mới có EXECUTE mặc định cho PUBLIC không?** Đặt REVOKE/GRANT trong cùng transaction.
25. **Procedure SECURITY DEFINER có đang cố COMMIT/ROLLBACK không?** Hiểu giới hạn transaction control của PostgreSQL.

### 26.4. Vận hành và xác nhận

26. **Default privileges có đúng theo role tạo object không?** Không giả định áp dụng cho mọi role member.
27. **Có GRANT rộng trên ALL TABLES vô tình lộ bảng/cột mới không?**
28. **View có dùng quyền owner hay security_invoker?** Cân nhắc tương tác với RLS.
29. **Đã kiểm thử bằng role hoặc credential thực sự chưa?** Không chỉ nhìn script migration.
30. **Đã chạy thử các thao tác phải bị từ chối chưa?** Ví dụ UPDATE accounts từ executor, ALTER tickets từ writer.
31. **Pool có reset transaction state, SET ROLE và session settings không?**
32. **Các thay đổi GRANT/REVOKE và body routine có được review/audit không?**
33. **Có kế hoạch thu hồi quyền và vô hiệu hóa credential khi thay đổi nhân sự/dịch vụ không?**
34. **Đã xem đúng DBMS/phiên bản chưa?** Các khái niệm quyền giống tên có thể khác ngữ nghĩa.

Một hệ quyền tốt không chỉ giúp các câu hợp lệ chạy thành công; nó phải **chứng minh các thao tác không được phép bị từ chối**, kể cả khi được gửi trực tiếp qua kết nối SQL, thay vì chỉ bị ẩn trên giao diện ứng dụng.

## 27. Dọn dẹp phòng thực hành

Các object mẫu đã được đặt trong schema `lab_acl_376` và các role bắt đầu bằng `lab376_`. **Chỉ dọn trên database sandbox riêng** sau khi đã xác nhận không có dữ liệu hoặc ứng dụng nào khác sử dụng những tên này.

### 27.1. Trở lại quyền quản trị

```sql
RESET ROLE;
```

Nếu đang ở trong transaction đã thất bại, cần `ROLLBACK` hoặc phục hồi transaction trước.

### 27.2. Xóa schema mẫu

```sql
DROP SCHEMA lab_acl_376 CASCADE;
```

**CẢNH BÁO:** `CASCADE` có thể xóa mọi đối tượng phụ thuộc trong schema. Chỉ chạy khi schema thật sự được tạo riêng cho bài và không chứa dữ liệu ngoài phạm vi học tập.

### 27.3. Xóa role mẫu nếu không còn dependency

Sau khi schema đã được dọn và bạn xác nhận không có grants/default privileges/dependencies khác do bài thực hành để lại, role quản trị có thể dọn role bài học:

```sql
DROP ROLE lab376_executor;
DROP ROLE lab376_writer;
DROP ROLE lab376_reader;
DROP ROLE lab376_owner;
```

Nếu đã thử các ví dụ `ALTER DEFAULT PRIVILEGES`, tạo object ở schema khác, cấp membership hoặc grant thêm quyền, việc xóa role có thể bị chặn bởi dependency còn tồn tại. **Không dùng các lệnh REASSIGN OWNED/DROP OWNED một cách rộng trên database thật chỉ để cưỡng ép xóa role**; phải kiểm tra dependency và phạm vi object một cách có chủ đích.

Trên hệ nhiều database, role PostgreSQL có phạm vi cluster, nên cần cân nhắc các object/quyền của role ở database khác trước khi xóa. Bộ ví dụ dành cho một sandbox mới để tránh rủi ro đó.

## 28. Tổng kết

**Phân tách quyền SQL** không chỉ là chia người dùng thành “đọc” và “ghi”. Một hệ thống an toàn cần phân biệt rõ bốn đường truy cập:

- **Đọc:** `SELECT` trên đúng bảng/view/cột, kết hợp `USAGE` schema và chính sách RLS nếu có.
- **Ghi:** `INSERT`/`UPDATE`/`DELETE` trên đúng đối tượng, không kèm quyền xóa hàng loạt hay thay đổi cấu trúc nếu không cần.
- **Thay đổi cấu trúc:** quyền tạo/sở hữu và migration role dành riêng cho việc triển khai, không trộn với credential ứng dụng.
- **Thực thi routine:** `EXECUTE` trên function/procedure được duyệt, phân biệt `SECURITY INVOKER` với `SECURITY DEFINER` và bảo vệ mọi đường quyền cao.

Trong PostgreSQL, `GRANT`/`REVOKE` trên bảng, schema, sequence và routine là các lớp khác nhau; owner, PUBLIC, membership và default privileges có thể mở đường truy cập mà một danh sách direct grants chưa phản ánh hết.

Thiết kế theo nguyên tắc **quyền tối thiểu** có nghĩa là vừa cấp đủ để nghiệp vụ hoạt động, vừa thử được những câu lệnh **phải thất bại**. Ranh giới ấy chỉ đáng tin cậy khi quyền DDL tách khỏi runtime, routine quyền cao có API hẹp và được kiểm toán, quyền theo tenant/cột được xem xét, connection được quản lý đúng, và mọi thay đổi quyền đều có quy trình kiểm tra.
