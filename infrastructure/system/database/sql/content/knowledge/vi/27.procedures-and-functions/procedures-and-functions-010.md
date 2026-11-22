# Ranh giới giao dịch trong thủ tục theo hệ quản trị

Một thủ tục lưu trữ (*stored procedure*) có thể thực hiện nhiều câu SQL: kiểm tra số dư, cập nhật hai tài khoản, ghi nhật ký, tạo thông báo. Nhưng câu hỏi quyết định tính nhất quán không chỉ là “thủ tục viết đúng SQL chưa?”, mà còn là **ai được phép bắt đầu, kết thúc hoặc hoàn tác giao dịch**.

Giả sử ứng dụng gọi:

```text
BEGIN transaction ở ứng dụng
    ├── UPDATE bảng A
    ├── CALL procedure cập nhật bảng B
    └── UPDATE bảng C
COMMIT transaction ở ứng dụng
```

Nếu thủ tục **không tự commit**, ứng dụng có thể mong đợi A, B và C **thành công cùng nhau hoặc cùng rollback**. Nếu thủ tục lại thực thi `COMMIT` ở giữa, kết quả rất khác nhau theo hệ quản trị:

- PostgreSQL có thể **từ chối thao tác kết thúc transaction** khi `CALL` nằm trong transaction block của caller.
- SQL Server có thể cho thủ tục tăng/giảm `@@TRANCOUNT`; `COMMIT` “bên trong” chưa chắc đã commit thực sự nếu caller còn transaction ngoài.
- MySQL có thể **kết thúc giao dịch đang mở của caller** khi thủ tục thực thi `START TRANSACTION`.
- Oracle có thể để `COMMIT` trong thủ tục **commit cả những thay đổi trước đó của caller trên cùng session**.
- SQLite cốt lõi **không cung cấp stored procedure SQL kiểu `CREATE PROCEDURE`**; transaction do ứng dụng quản lý.

Bài học thuộc module **Database SQL**, chương **Thủ tục và hàm**. Các ví dụ giải thích cơ chế theo từng DBMS, ranh giới giữa thủ tục và hàm, lỗi thường gặp khi ứng dụng sở hữu transaction, và cách thiết kế quy trình có thể thử lại an toàn.

> **Nguyên tắc quan trọng:** một thủ tục lưu trữ **không tự động** là một giao dịch riêng, độc lập, nguyên tử. Phạm vi commit/rollback phụ thuộc **cách gọi, ngôn ngữ thủ tục, DBMS và quyền sở hữu transaction**.

Các đoạn SQL minh họa dùng **cú pháp riêng của từng hệ**. Đừng sao chép nguyên cú pháp `CREATE PROCEDURE` của PostgreSQL sang MySQL, SQL Server hay Oracle.

## 1. Những khái niệm cần phân biệt

### 1.1. Thủ tục (*procedure*) và hàm (*function*)

Hàm thường được dùng để trả một giá trị hoặc tập kết quả, đôi khi xuất hiện trong biểu thức `SELECT`. Thủ tục thường được gọi theo một cú pháp riêng như `CALL` hoặc `EXEC` để thực hiện một đơn vị công việc.

Nhưng khả năng quản lý transaction **không chỉ phụ thuộc tên gọi**. Mỗi DBMS có các quy tắc khác nhau:

| DBMS | Cách gọi thủ tục thông dụng | Khả năng transaction control trong thủ tục |
|---|---|---|
| PostgreSQL | `CALL procedure_name(...)` | Có `COMMIT`/`ROLLBACK` trong **ngữ cảnh gọi đủ điều kiện**, nhưng nhiều hạn chế |
| SQL Server | `EXEC dbo.procedure_name ...` | Có `BEGIN TRAN`, `COMMIT`, `ROLLBACK`; dùng **cùng transaction context của connection** |
| MySQL | `CALL procedure_name(...)` | Có `START TRANSACTION`, `COMMIT`, `ROLLBACK` trong thủ tục, nhưng **không có nested transaction thật** |
| Oracle Database | Khối PL/SQL hoặc `CALL` | Thủ tục thường có thể `COMMIT`/`ROLLBACK`; cùng transaction session trừ khi dùng autonomous transaction |
| SQLite | Không có stored procedure SQL native | Application quản lý `BEGIN`/`COMMIT`/`ROLLBACK`; trigger không phải stored procedure |

Phần “hàm có thể hay không thể commit” cũng tùy DBMS, ngữ cảnh thực thi và ngoại lệ đặc biệt như Oracle autonomous transaction. Không suy từ cách PostgreSQL hoạt động rằng mọi hàm của mọi DBMS có cùng quyền.

### 1.2. Transaction ở connection, không phải mặc định ở mỗi thủ tục

Trong phần lớn mô hình thông thường, các câu SQL của thủ tục chạy trong **ngữ cảnh kết nối/giao dịch hiện tại**. Ví dụ:

```text
Connection C
  └── Transaction T
        ├── UPDATE accounts
        ├── CALL transfer_once(...)
        │    ├── UPDATE accounts
        │    └── INSERT ledger
        └── INSERT request_log
```

Nếu thủ tục không tự kết thúc transaction và mọi câu DML transactional nằm trong cùng transaction T, caller có thể commit hoặc rollback toàn bộ T theo quy tắc DBMS.

**Một lời gọi thủ tục không đồng nghĩa tự mở một giao dịch độc lập**. Muốn thiết kế atomicity, phải xác định rõ bên nào là **transaction owner**.

### 1.3. Ranh giới giao dịch và ranh giới khối lệnh

Trong nhiều ngôn ngữ thủ tục, từ `BEGIN` chỉ bắt đầu một **khối mã**, không phải bắt đầu transaction.

Ví dụ trong PL/pgSQL:

```sql
CREATE OR REPLACE PROCEDURE example_proc()
LANGUAGE plpgsql
AS $$
BEGIN
    -- Đây là BEGIN của khối PL/pgSQL.
    NULL;
END;
$$;
```

Trong MySQL cũng có `BEGIN ... END` bao bọc các câu lệnh của stored procedure, trong khi câu bắt đầu transaction là `START TRANSACTION`.

Trong Oracle, `BEGIN ... END;` thường là một khối PL/SQL; Oracle bắt đầu transaction theo thao tác DML tương ứng, chứ không vì từ `BEGIN` của khối.

SQL Server lại có `BEGIN ... END` dùng nhóm câu lệnh và `BEGIN TRANSACTION` dùng mở transaction. **Cần nhìn đầy đủ cú pháp**, không chỉ nhìn chữ BEGIN.

### 1.4. COMMIT, ROLLBACK và SAVEPOINT

- `COMMIT`: xác nhận các thay đổi của transaction hiện tại theo ngữ nghĩa của DBMS.
- `ROLLBACK`: hoàn tác transaction hoặc một phạm vi được phép chỉ định.
- `SAVEPOINT`: tạo mốc có thể hoàn tác **một phần** trong transaction, nhưng không phải luôn là một transaction commit độc lập.
- `AUTOCOMMIT`: chế độ client/connection hoặc engine quyết định các statement được commit tự động thế nào khi không có transaction tường minh.

Một **savepoint** không bảo đảm phần công việc bên trong đã được lưu bền vững độc lập với transaction ngoài. Nếu outer transaction rollback, phần thay đổi chưa commit sau savepoint cũng bị rollback.

## 2. Hai hợp đồng sở hữu transaction

Trước khi viết thủ tục, nên chọn một trong hai hợp đồng rõ ràng.

### 2.1. Caller-owned: thủ tục không tự commit

```text
Ứng dụng:
  BEGIN
  UPDATE A
  CALL procedure (UPDATE B, INSERT C)
  UPDATE D
  COMMIT

Nếu lỗi: ROLLBACK cả A, B, C, D.
```

Phù hợp với:

- Một request cần thay đổi nhiều bảng nguyên tử.
- Nhiều thao tác repository/DAO phối hợp.
- Giao dịch của ứng dụng đã quản lý bằng JDBC, ORM hoặc framework.
- Quy trình có retry từ đầu sau deadlock hoặc serialization failure.

Lợi ích: ứng dụng kiểm soát **đơn vị nghiệp vụ được commit**.

Nhược điểm: nếu caller giữ transaction quá lâu hoặc không rollback khi lỗi, thủ tục có thể giữ khóa lâu và tăng contention.

### 2.2. Procedure-owned: thủ tục chủ động commit/rollback

```text
Ứng dụng:
  CALL batch_procedure

Thủ tục:
  xử lý batch 1
  COMMIT
  xử lý batch 2
  COMMIT
```

Phù hợp trong một số quy trình batch độc lập, tác vụ quản trị hoặc xử lý theo checkpoint khi DBMS cho phép.

Nhược điểm:

- Caller không thể coi toàn bộ lời gọi là **một transaction duy nhất** nếu thủ tục commit từng phần.
- Lỗi ở batch sau không hoàn tác các batch đã commit.
- Một số DBMS/cách gọi không cho phép thủ tục điều khiển transaction.
- Khó tích hợp với ứng dụng đã mở transaction ngoài.
- Phải có checkpoint, idempotency và cách phục hồi khi chạy lại.

### 2.3. Không trộn hợp đồng một cách ngầm định

Một helper được viết để “chỉ insert một dòng phụ” nhưng lại có `COMMIT` bên trong có thể làm sụp đổ cam kết nguyên tử của caller, tùy DBMS.

Một thủ tục batch có `COMMIT` được gọi bên trong transaction của ORM có thể gây lỗi hoặc kết thúc transaction ngoài ngoài dự kiến.

**Hợp đồng giao dịch là một phần của API thủ tục**, cần được ghi rõ như kiểu tham số, dữ liệu đầu ra và ngoại lệ.

## 3. PostgreSQL: một function không tự kết thúc transaction

Trong PostgreSQL, **PL/pgSQL function** không được dùng `COMMIT` hoặc `ROLLBACK` để kết thúc transaction của caller.

Ví dụ bảng minh họa:

```sql
CREATE TABLE lesson344_pg_log (
    log_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
```

Một function hợp lệ **ghi dữ liệu mà không commit**:

```sql
CREATE OR REPLACE FUNCTION lesson344_pg_write_log(
    p_message TEXT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO lesson344_pg_log (message)
    VALUES (p_message);
END;
$$;
```

Caller có thể quản lý giao dịch:

```sql
BEGIN;

INSERT INTO lesson344_pg_log (message)
VALUES ('before function');

SELECT lesson344_pg_write_log('inside function');

ROLLBACK;

SELECT message
FROM lesson344_pg_log
WHERE message IN ('before function', 'inside function');
```

Nếu hai dòng chưa tồn tại trước thử nghiệm và mọi thay đổi ở transaction này được rollback, truy vấn cuối **không thấy hai dòng vừa ghi**.

### 3.1. Tại sao function không có transaction riêng?

`SELECT lesson344_pg_write_log(...)` chạy trong transaction của câu gọi. Function có thể thực hiện thay đổi được phép theo ngữ nghĩa ngôn ngữ/volatility, nhưng **không sở hữu quyền kết thúc transaction**.

Đừng dùng cách như:

```sql
-- Không dùng làm function hợp lệ để commit.
CREATE OR REPLACE FUNCTION lesson344_pg_bad()
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    COMMIT;
END;
$$;
```

Một function kiểu này có thể được chấp nhận ở một số bước phân tích/định nghĩa nhưng sẽ **không thể thực hiện transaction control hợp lệ khi gọi như function**, và có thể báo lỗi khi chạy.

### 3.2. Trigger cũng không được tự COMMIT

Trigger PostgreSQL thực thi trong transaction của statement kích hoạt nó. Trigger function không được tự `COMMIT`/`ROLLBACK` để tách riêng một phần thay đổi.

Nếu transaction caller rollback, các thay đổi transactional mà trigger đã thực hiện trong database cũng rollback cùng.

**PostgreSQL không cung cấp autonomous transaction native theo cách `PRAGMA AUTONOMOUS_TRANSACTION` của Oracle.** Muốn ghi log không phụ thuộc transaction, phải thiết kế cơ chế riêng có đánh giá rủi ro; không coi trigger là một transaction mới.

## 4. PostgreSQL: PROCEDURE và CALL có thể điều khiển transaction

PostgreSQL hỗ trợ `CREATE PROCEDURE` và `CALL`. Không giống function, thủ tục có thể điều khiển transaction **khi được gọi trong ngữ cảnh phù hợp**.

### 4.1. Thủ tục commit hai bước

```sql
CREATE OR REPLACE PROCEDURE lesson344_pg_commit_steps()
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO lesson344_pg_log (message)
    VALUES ('pg-step-1');

    COMMIT;

    INSERT INTO lesson344_pg_log (message)
    VALUES ('pg-step-2');

    COMMIT;
END;
$$;
```

Gọi ở cấp trên cùng, khi client không bao `CALL` trong transaction block tường minh:

```sql
CALL lesson344_pg_commit_steps();
```

Trong ngữ cảnh hợp lệ, sau `COMMIT` đầu tiên, PostgreSQL tự bắt đầu transaction mới để thủ tục có thể tiếp tục xử lý các câu tiếp theo. Sau `COMMIT` thứ hai, bước tiếp theo (nếu có) lại thuộc transaction mới tương ứng.

**Lưu ý môi trường:** một số client, ORM hoặc công cụ migration tự động bọc lệnh vào transaction dù người dùng chỉ nhìn thấy `CALL`. Khi đó, thủ tục `COMMIT` có thể bị từ chối.

### 4.2. CALL trong transaction block của caller: không được tự commit

Trong PostgreSQL, ví dụ sau có vấn đề:

```sql
BEGIN;

CALL lesson344_pg_commit_steps();

ROLLBACK;
```

Vì `CALL` đang được thực hiện trong một transaction block tường minh, thao tác `COMMIT` **bên trong thủ tục** không được phép, thường dẫn đến lỗi kiểu `invalid transaction termination`.

Không nên mong `COMMIT` bên trong thủ tục “chỉ commit một giao dịch con” — PostgreSQL không có mô hình nested transaction commit như vậy trong PL/pgSQL.

**Điều quan trọng:** PostgreSQL **vẫn có thể gọi** thủ tục bên trong transaction block nếu thủ tục không cố điều khiển transaction. Chính thao tác `COMMIT`/`ROLLBACK` trong thủ tục mới chịu hạn chế.

### 4.3. Một thủ tục không tự COMMIT để caller sở hữu giao dịch

```sql
CREATE OR REPLACE PROCEDURE lesson344_pg_write_only(
    p_message TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO lesson344_pg_log (message)
    VALUES (p_message);
END;
$$;
```

Caller:

```sql
BEGIN;

INSERT INTO lesson344_pg_log (message)
VALUES ('caller-change');

CALL lesson344_pg_write_only('procedure-change');

ROLLBACK;
```

Hai dòng vừa ghi cùng nằm trong transaction của caller, nên rollback hoàn tác cả hai.

**Đây thường là hợp đồng dễ tích hợp nhất với transaction quản lý ở ứng dụng.**

## 5. PostgreSQL: những điều kiện giới hạn COMMIT/ROLLBACK trong procedure

Việc khai báo `CREATE PROCEDURE` **không tự động cho phép** `COMMIT` từ bất kỳ vị trí hoặc cách gọi nào.

### 5.1. CALL phải phù hợp ngữ cảnh transaction

PostgreSQL cho phép transaction control trong thủ tục khi gọi từ **`CALL` hoặc khối `DO` cấp trên cùng** trong ngữ cảnh thích hợp, không nằm trong transaction block tường minh của client.

Tương tự, một chuỗi gọi lồng nhau `CALL`/`DO` phù hợp có thể cho phép điều khiển transaction.

Nhưng một call stack có lệnh xen giữa theo cách không hợp lệ có thể làm mất khả năng này.

Ví dụ ý tưởng:

```text
CALL proc1()
  └── CALL proc2()
       └── COMMIT trong proc2   [có thể hợp lệ nếu đúng điều kiện]

CALL proc1()
  └── SELECT helper_function()
       └── CALL proc2()
            └── COMMIT          [không còn hợp lệ]
```

**Không phải “có CALL ở đâu đó trong call stack” là đủ**. Cấu trúc gọi và ngữ cảnh transaction quyết định.

### 5.2. PL/pgSQL BEGIN không phải BEGIN TRANSACTION

Trong:

```sql
CREATE OR REPLACE PROCEDURE lesson344_pg_example()
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO lesson344_pg_log (message)
    VALUES ('hello');
END;
$$;
```

`BEGIN` mở **khối PL/pgSQL**, không mở một transaction riêng. Không dùng `BEGIN` trong PL/pgSQL để diễn giải như `BEGIN TRANSACTION` ở client.

Các transaction được bắt đầu theo ngữ cảnh `CALL` và thao tác transaction control có hiệu lực.

### 5.3. Không thể kết thúc transaction trong block có EXCEPTION handler

PL/pgSQL thực hiện các khối có `EXCEPTION` như cơ chế subtransaction phục vụ xử lý ngoại lệ. Khi đang ở phạm vi khối có exception handler, **không được kết thúc transaction** bằng `COMMIT`/`ROLLBACK`.

Ví dụ thiết kế cần tránh:

```sql
-- Minh họa sai: không chạy như một thủ tục commit hợp lệ.
CREATE OR REPLACE PROCEDURE lesson344_pg_bad_exception()
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO lesson344_pg_log (message)
    VALUES ('inside guarded block');

    COMMIT; -- Không hợp lệ trong block có EXCEPTION.
EXCEPTION WHEN OTHERS THEN
    NULL;
END;
$$;
```

Muốn commit theo lô, hãy thiết kế lại phạm vi xử lý ngoại lệ, **không đặt COMMIT trong block đang có EXCEPTION**.

### 5.4. Thủ tục SECURITY DEFINER không được transaction control

Một thủ tục PostgreSQL khai báo `SECURITY DEFINER` **không được thực thi câu transaction control** bên trong.

Ngoài ra, thủ tục có **mệnh đề `SET` gắn với định nghĩa `CREATE PROCEDURE`** cũng có hạn chế cấm transaction control.

Đây là điểm dễ bỏ sót khi mang thủ tục từ môi trường thử nghiệm sang production rồi bổ sung bảo mật hoặc cấu hình session.

### 5.5. COMMIT AND CHAIN, ROLLBACK AND CHAIN

PostgreSQL có thể dùng:

```sql
COMMIT AND CHAIN;
```

hoặc:

```sql
ROLLBACK AND CHAIN;
```

trong ngữ cảnh transaction control được cho phép. Dạng `AND CHAIN` bắt đầu transaction tiếp theo với những đặc tính giao dịch tương ứng được giữ lại, khác với một số trường hợp tự bắt đầu transaction kế tiếp theo mặc định.

**Không giải quyết được hạn chế về ngữ cảnh gọi:** nếu `COMMIT` không được phép vì `CALL` nằm trong transaction block ngoài, đổi thành `COMMIT AND CHAIN` cũng không giúp.

### 5.6. Cursor loop khi có COMMIT

Trong PostgreSQL, commit trong vòng lặp `FOR ... IN SELECT ... LOOP` có thể dẫn đến việc cursor được chuyển thành **holdable cursor** ở lần commit đầu; kết quả truy vấn có thể được materialize thay vì tiếp tục đọc tuần tự như dự kiến.

Ngoài ra, transaction control có các hạn chế khi vòng lặp cursor được điều khiển bởi câu lệnh không chỉ đọc, ví dụ các dạng DML có `RETURNING`.

Với batch rất lớn, không nên mặc định:

```sql
FOR rec IN SELECT ... LOOP
    -- Xử lý một dòng.
    COMMIT;
END LOOP;
```

là một cách streaming an toàn, không tốn bộ nhớ. Cần xem cơ chế cursor, khóa và kích thước lô.

## 6. PostgreSQL: xử lý ngoại lệ không đồng nghĩa ROLLBACK toàn transaction

PL/pgSQL hỗ trợ:

```sql
CREATE OR REPLACE PROCEDURE lesson344_pg_exception_demo()
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO lesson344_pg_log (message)
    VALUES ('outer-before');

    BEGIN
        INSERT INTO lesson344_pg_log (message)
        VALUES ('inner-before-error');

        RAISE EXCEPTION 'demo error';
    EXCEPTION WHEN OTHERS THEN
        INSERT INTO lesson344_pg_log (message)
        VALUES ('caught-error');
    END;

    INSERT INTO lesson344_pg_log (message)
    VALUES ('outer-after');
END;
$$;
```

Gọi:

```sql
BEGIN;

CALL lesson344_pg_exception_demo();

SELECT message
FROM lesson344_pg_log
WHERE message IN (
    'outer-before',
    'inner-before-error',
    'caught-error',
    'outer-after'
);

ROLLBACK;
```

Trong transaction **trước rollback**:

- `outer-before` được ghi trong phạm vi ngoài.
- `inner-before-error` thuộc khối có lỗi được xử lý và thay đổi của khối đó được hoàn tác.
- `caught-error` được ghi trong handler sau khi khối có lỗi được khôi phục.
- `outer-after` tiếp tục được ghi.

Sau `ROLLBACK` của caller, các dòng transactional mới trong thử nghiệm đều bị hoàn tác.

**Ranh giới khối `EXCEPTION` khác ranh giới `COMMIT`.** Handler có thể xử lý lỗi cục bộ, nhưng không biến mọi thay đổi thành một transaction tự commit.

## 7. PostgreSQL: commit theo batch có nghĩa thành công một phần

Ta tạo bảng tiến độ để thấy từng commit độc lập:

```sql
CREATE TABLE lesson344_pg_batch_log (
    batch_no INTEGER PRIMARY KEY,
    completed_at TIMESTAMPTZ NOT NULL
        DEFAULT clock_timestamp()
);
```

Thủ tục minh họa:

```sql
CREATE OR REPLACE PROCEDURE lesson344_pg_commit_batches()
LANGUAGE plpgsql
AS $$
DECLARE
    v_batch INTEGER;
BEGIN
    FOR v_batch IN 1..3 LOOP
        INSERT INTO lesson344_pg_batch_log (batch_no)
        VALUES (v_batch)
        ON CONFLICT (batch_no) DO NOTHING;

        COMMIT;
    END LOOP;
END;
$$;
```

Gọi **ở top level** khi không nằm trong transaction block tường minh:

```sql
CALL lesson344_pg_commit_batches();
```

Sau mỗi `COMMIT`, một lô được kết thúc. Nếu một lỗi không được xử lý xuất hiện **trước commit của batch 3**:

- Những batch 1, 2 đã commit **không được rollback chỉ vì batch 3 lỗi**.
- Batch 3 chưa commit có thể bị rollback.
- Gọi lại cần thiết kế idempotency và xác định batch nào hoàn thành.

### 7.1. Commit theo batch không tương đương một thao tác nguyên tử toàn bộ

Nếu nghiệp vụ yêu cầu “cả ba batch cùng thành công hoặc cùng thất bại”, thủ tục commit từng batch **không phù hợp**. Khi đó để caller sở hữu một transaction lớn hoặc thiết kế hình thức xử lý/bù trừ riêng có kiểm soát.

### 7.2. Checkpoint nên được commit cùng dữ liệu của batch

Nếu batch cập nhật 5.000 dòng rồi commit, nhưng dấu “batch hoàn tất” được ghi **ở transaction khác**, có nguy cơ:

- Dữ liệu đã commit nhưng checkpoint chưa ghi.
- Retry xử lý lại 5.000 dòng.
- Cập nhật/cộng dồn bị thực hiện hai lần nếu không idempotent.

Vì vậy dữ liệu và tiến độ của **cùng một batch** nên được bảo vệ bằng ranh giới transaction được thiết kế đúng.

## 8. SQL Server: transaction ở session và @@TRANCOUNT

SQL Server sử dụng `BEGIN TRANSACTION`, `COMMIT TRANSACTION`, `ROLLBACK TRANSACTION` và bộ đếm `@@TRANCOUNT`.

`@@TRANCOUNT` cho biết số mức transaction `BEGIN TRANSACTION` chưa được cân bằng ở session.

Các ví dụ sau là **T-SQL**, không chạy trong PostgreSQL.

### 8.1. Tạo bảng và procedure không tự commit

```sql
CREATE TABLE dbo.lesson344_log (
    log_id INT IDENTITY(1,1) PRIMARY KEY,
    message NVARCHAR(200) NOT NULL
);
GO

CREATE OR ALTER PROCEDURE dbo.lesson344_write_log
    @message NVARCHAR(200)
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO dbo.lesson344_log (message)
    VALUES (@message);
END;
GO
```

**`GO` không phải câu SQL giao dịch**. Đây là dấu phân tách batch được một số công cụ như SSMS hoặc `sqlcmd` xử lý ở phía client. Nó không tự `COMMIT`.

Caller:

```sql
BEGIN TRANSACTION;

INSERT INTO dbo.lesson344_log (message)
VALUES (N'caller');

EXEC dbo.lesson344_write_log
    @message = N'procedure';

ROLLBACK TRANSACTION;

SELECT *
FROM dbo.lesson344_log
WHERE message IN (N'caller', N'procedure');
```

Nếu không có dữ liệu cũ trùng giá trị và các statement thực hiện bình thường, rollback hoàn tác cả hai thay đổi.

### 8.2. Nested BEGIN TRAN không phải nested commit độc lập

SQL Server có thể cho:

```sql
BEGIN TRANSACTION;  -- @@TRANCOUNT = 1

BEGIN TRANSACTION;  -- @@TRANCOUNT = 2

COMMIT TRANSACTION; -- @@TRANCOUNT = 1

-- Dữ liệu vẫn thuộc transaction ngoài chưa commit.
ROLLBACK TRANSACTION; -- Hoàn tác toàn bộ transaction ngoài.
```

Điểm quan trọng:

> `COMMIT` ở mức trong chủ yếu giảm `@@TRANCOUNT`; việc commit bền vững thực sự gắn với mức ngoài cùng khi bộ đếm về 0.

Nếu thủ tục gọi `BEGIN TRAN` và `COMMIT TRAN` trong khi caller đang mở transaction, `COMMIT` bên trong thủ tục **không phải autonomous transaction**.

### 8.3. Procedure có BEGIN/COMMIT khi caller cũng BEGIN

Ví dụ ý tưởng:

```sql
CREATE OR ALTER PROCEDURE dbo.lesson344_inner_transaction
AS
BEGIN
    BEGIN TRANSACTION;

    INSERT INTO dbo.lesson344_log (message)
    VALUES (N'inner transaction');

    COMMIT TRANSACTION;
END;
GO
```

Caller:

```sql
BEGIN TRANSACTION;            -- @@TRANCOUNT = 1

EXEC dbo.lesson344_inner_transaction;
-- Trong proc, @@TRANCOUNT lên 2 rồi xuống 1.

SELECT @@TRANCOUNT AS transaction_depth; -- 1

ROLLBACK TRANSACTION;         -- Rollback cả INSERT từ proc.
```

**Thủ tục chưa tự lưu dữ liệu vĩnh viễn** vì outer transaction còn mở. Không được coi `COMMIT` bên trong là một checkpoint độc lập.

### 8.4. ROLLBACK không chỉ giảm bộ đếm một bậc

Trong SQL Server, `ROLLBACK TRANSACTION` không chỉ tương tự một lần `COMMIT` theo chiều ngược lại. Một rollback không chỉ định savepoint thường hoàn tác toàn bộ transaction và đưa `@@TRANCOUNT` về 0.

Điều này có thể **hoàn tác cả những thay đổi của caller** khi thủ tục “tự rollback” dưới một transaction ngoài.

Vì vậy, thủ tục dùng chung nên nêu rõ có thể nhận transaction ngoài hay không, và ai chịu trách nhiệm rollback khi gặp lỗi.

## 9. SQL Server: TRY/CATCH và XACT_STATE()

SQL Server cung cấp `TRY...CATCH` và `XACT_STATE()` để đánh giá trạng thái transaction sau lỗi.

| `XACT_STATE()` | Ý nghĩa |
|---:|---|
| `0` | Không có transaction đang hoạt động |
| `1` | Có transaction đang hoạt động và vẫn có thể commit |
| `-1` | Có transaction đang hoạt động nhưng **uncommittable**; phải rollback toàn bộ theo quy tắc |

### 9.1. Ví dụ procedure tự sở hữu transaction

Ví dụ sau **chỉ dành cho cách gọi standalone, không có outer transaction**:

```sql
CREATE OR ALTER PROCEDURE dbo.lesson344_atomic_write
    @message NVARCHAR(200)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRY
        BEGIN TRANSACTION;

        INSERT INTO dbo.lesson344_log (message)
        VALUES (@message);

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0
            ROLLBACK TRANSACTION;

        THROW;
    END CATCH
END;
GO
```

`SET XACT_ABORT ON` khiến nhiều lỗi thực thi có tác động hủy transaction mạnh hơn, nhưng không phải mọi loại lỗi đều có cùng ngữ nghĩa. `THROW` tái phát lỗi để caller biết tác vụ không thành công.

**Cảnh báo về transaction ngoài:** nếu caller đã mở transaction trước khi gọi thủ tục này, `BEGIN TRAN` bên trong chỉ tăng `@@TRANCOUNT`; khi gặp lỗi, `ROLLBACK` không chỉ undo “transaction trong” mà có thể **rollback cả transaction của caller**.

### 9.2. Thiết kế hỗ trợ ambient transaction

Khi một stored procedure có thể chạy cả standalone và bên trong transaction của caller, pattern tổng quát là:

1. Đọc `@@TRANCOUNT` lúc vào.
2. Nếu `@@TRANCOUNT = 0`, procedure **tự mở transaction và sở hữu commit/rollback**.
3. Nếu `@@TRANCOUNT > 0`, procedure **tham gia transaction ngoài**, cân nhắc savepoint để rollback một phần khi hợp lệ.
4. Trong `CATCH`, kiểm tra `XACT_STATE()`.
5. Nếu transaction ở `-1`, **không thể chỉ rollback về savepoint** rồi tiếp tục như bình thường. Cần để owner xử lý rollback toàn transaction.
6. Không được `COMMIT` transaction của caller khi procedure không phải owner.

Ví dụ cú pháp savepoint T-SQL:

```sql
SAVE TRANSACTION lesson344_save;

-- Thao tác DML có thể lỗi.

ROLLBACK TRANSACTION lesson344_save;
```

`ROLLBACK TRANSACTION savepoint_name` khác với `ROLLBACK TRANSACTION` không chỉ định savepoint.

**Không xây transaction helper dùng chung chỉ dựa vào “BEGIN TRAN ở đầu, COMMIT ở cuối”.** Phải xác định quyền sở hữu và trạng thái lỗi, đặc biệt khi ứng dụng đã quản lý transaction.

### 9.3. Tại sao @@TRANCOUNT không đủ?

`@@TRANCOUNT > 0` cho biết tồn tại transaction, nhưng không cho biết transaction ấy **có còn commit được không**. Một transaction ở trạng thái `XACT_STATE() = -1` phải được xử lý theo quy tắc uncommittable; việc cố commit hoặc rollback về savepoint không phải giải pháp hợp lệ.

Do đó T-SQL thường cần cả `@@TRANCOUNT` và `XACT_STATE()`, mỗi hàm trả lời một câu hỏi khác nhau.

## 10. MySQL/InnoDB: START TRANSACTION bên trong procedure

MySQL cho phép transaction control trong stored **procedure** theo điều kiện hệ thống hỗ trợ, nhưng có điểm khác rất quan trọng so với SQL Server.

Ví dụ MySQL:

```sql
CREATE TABLE lesson344_mysql_log (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    message VARCHAR(200) NOT NULL
) ENGINE = InnoDB;
```

### 10.1. Procedure tự mở transaction

Đoạn sau dùng `DELIMITER` theo cú pháp client MySQL CLI/Workbench quen thuộc; `DELIMITER` **không phải lệnh SQL được server xử lý như DML**.

```sql
DELIMITER //

CREATE PROCEDURE lesson344_mysql_atomic(
    IN p_message VARCHAR(200)
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    INSERT INTO lesson344_mysql_log (message)
    VALUES (p_message);

    COMMIT;
END //

DELIMITER ;
```

Gọi khi không có transaction ngoài đang mở:

```sql
CALL lesson344_mysql_atomic('standalone call');
```

Nếu insert thành công, thủ tục commit. Nếu có lỗi SQL và handler bắt được, nó rollback transaction mà procedure đã bắt đầu rồi `RESIGNAL` báo lỗi ra caller.

### 10.2. MySQL không hỗ trợ nested transaction độc lập

Đây là cạm bẫy lớn:

```sql
START TRANSACTION;

INSERT INTO lesson344_mysql_log (message)
VALUES ('caller-before');

CALL lesson344_mysql_atomic('inner');

ROLLBACK;
```

Không được cho rằng outer `ROLLBACK` sẽ hoàn tác cả `caller-before` và `inner`.

Trong MySQL, **`START TRANSACTION` bắt đầu một transaction mới và ngầm commit transaction đang hoạt động trước đó**, nếu có. Vì thủ tục `lesson344_mysql_atomic` chứa `START TRANSACTION`, lời gọi từ một caller đang có transaction có thể **commit công việc trước CALL của caller** ngoài mong muốn.

Sau đó `COMMIT` trong thủ tục lại commit phần công việc thủ tục. Outer `ROLLBACK` sau lời gọi **không thể thu hồi những phần đã commit trước đó**.

**Không dùng `START TRANSACTION` trong helper được thiết kế để tham gia transaction caller.**

### 10.3. MySQL BEGIN trong stored program là khối lệnh

Trong MySQL:

```sql
CREATE PROCEDURE example()
BEGIN
    -- BEGIN ở đây mở khối chương trình, không phải
    -- khởi đầu một transaction bằng lệnh BEGIN WORK.
END;
```

Muốn mở transaction trong stored procedure, dùng `START TRANSACTION` khi đúng thiết kế.

### 10.4. Procedure không tự commit để caller sở hữu transaction

```sql
DELIMITER //

CREATE PROCEDURE lesson344_mysql_write_only(
    IN p_message VARCHAR(200)
)
BEGIN
    INSERT INTO lesson344_mysql_log (message)
    VALUES (p_message);
END //

DELIMITER ;
```

Caller:

```sql
START TRANSACTION;

INSERT INTO lesson344_mysql_log (message)
VALUES ('mysql-caller');

CALL lesson344_mysql_write_only('mysql-procedure');

ROLLBACK;
```

Với bảng `InnoDB` và không có thao tác gây implicit commit, cả hai dòng mới được rollback cùng nhau.

### 10.5. Stored function và trigger MySQL

MySQL có các hạn chế transaction control trong **stored function** và **trigger**: không thể tự thực hiện các câu commit/rollback rõ ràng hoặc ngầm theo cách bị cấm trong những ngữ cảnh này. Hạn chế có thể áp dụng cả khi function/trigger gọi một stored procedure có chứa transaction control.

Không cho rằng “bọc COMMIT trong procedure rồi gọi từ function” là cách vượt qua quy tắc.

## 11. MySQL: autocommit, handler và DDL implicit commit

### 11.1. Autocommit của session

MySQL thường dùng chế độ `autocommit` khi không mở transaction rõ ràng. Một statement DML thành công có thể được commit tự động theo chế độ session.

Khi ứng dụng dùng:

```sql
START TRANSACTION;
-- DML
COMMIT;
```

nó tạo ranh giới rõ hơn cho nhiều statement liên quan.

**Đừng thay đổi `autocommit` ở session dùng chung một cách tùy tiện**: với connection pool, thay đổi cấu hình có thể ảnh hưởng lời gọi về sau nếu không được khôi phục đúng.

### 11.2. Handler ROLLBACK có thể đụng transaction của caller

Một thủ tục có:

```sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    ROLLBACK;
    RESIGNAL;
END;
```

có thể rollback **transaction hiện tại của session**. Nếu procedure được gọi dưới transaction do caller sở hữu nhưng handler không xét quyền sở hữu, nó có thể rollback cả công việc ngoài phạm vi mong muốn.

Đừng suy rằng handler luôn hoàn tác “chỉ những câu trong procedure”.

### 11.3. DDL implicit commit

Trong MySQL, nhiều câu DDL như `CREATE TABLE`, `ALTER TABLE` và `TRUNCATE TABLE` gây **implicit commit** theo quy tắc engine/server, ngay cả khi được dùng trong luồng có vẻ đang bao bởi transaction.

Ví dụ **chỉ để cảnh báo, không chạy như giao dịch an toàn**:

```sql
START TRANSACTION;

INSERT INTO lesson344_mysql_log (message)
VALUES ('before ddl');

CREATE TABLE lesson344_mysql_new_table (
    id INT PRIMARY KEY
);

ROLLBACK;
```

Không được mặc định `ROLLBACK` cuối sẽ hoàn tác cả dữ liệu trước DDL và bản thân việc tạo bảng.

Một số thao tác DDL trong MySQL có tính **atomic DDL** theo nghĩa an toàn khi crash, nhưng **không đồng nghĩa DDL thuộc một user transaction có thể rollback như PostgreSQL**.

## 12. Oracle Database: transaction của session và COMMIT trong procedure

Oracle thường bắt đầu transaction theo thao tác DML đầu tiên cần transaction; không cần một lệnh `BEGIN TRANSACTION` giống PostgreSQL/MySQL để mở transaction.

Trong PL/SQL, `BEGIN ... END;` là khối chương trình.

### 12.1. Tạo bảng và procedure chỉ ghi

Ví dụ Oracle:

```sql
CREATE TABLE lesson344_oracle_log (
    log_id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    message VARCHAR2(200) NOT NULL
);
```

Procedure không commit:

```sql
CREATE OR REPLACE PROCEDURE lesson344_oracle_write(
    p_message IN VARCHAR2
)
AS
BEGIN
    INSERT INTO lesson344_oracle_log (message)
    VALUES (p_message);
END;
/
```

Dấu `/` là lệnh kết thúc/thi hành khối trong nhiều client Oracle như SQL*Plus hoặc SQLcl; không phải ký hiệu kết thúc transaction.

Caller:

```sql
INSERT INTO lesson344_oracle_log (message)
VALUES ('caller-before');

BEGIN
    lesson344_oracle_write('inside-procedure');
END;
/

ROLLBACK;
```

Nếu các lệnh được chạy trong cùng session và chưa có thao tác commit ngầm khác, rollback hoàn tác cả hai dòng mới.

### 12.2. COMMIT trong procedure tác động lên transaction caller

Thủ tục Oracle sau tự commit:

```sql
CREATE OR REPLACE PROCEDURE lesson344_oracle_commit
AS
BEGIN
    INSERT INTO lesson344_oracle_log (message)
    VALUES ('procedure-committed');

    COMMIT;
END;
/
```

Caller có thay đổi chưa commit:

```sql
INSERT INTO lesson344_oracle_log (message)
VALUES ('caller-pending');

BEGIN
    lesson344_oracle_commit;
END;
/

ROLLBACK;
```

Với transaction thông thường trong cùng session:

- Dòng `caller-pending` được ghi trước lời gọi nhưng chưa commit.
- Thủ tục thêm `procedure-committed`.
- `COMMIT` trong thủ tục **commit transaction session hiện tại**, bao gồm cả thay đổi của caller.
- `ROLLBACK` sau đó **không hoàn tác được hai dòng đã commit**.

Đây là khác biệt trọng yếu so với suy nghĩ “COMMIT chỉ lưu dữ liệu do procedure vừa tạo”.

**Không chạy ví dụ này trên dữ liệu nghiệp vụ thật**. Nó được thiết kế để minh họa tác động commit toàn transaction.

### 12.3. Oracle không tự tạo transaction lồng độc lập cho mọi procedure

Lời gọi một procedure Oracle thông thường dùng transaction hiện tại của session. `COMMIT` hoặc `ROLLBACK` bên trong có thể tác động đến công việc của caller trước khi procedure bắt đầu.

Không cần procedure phải biết mọi bảng caller đã sửa; thao tác commit là ở phạm vi **transaction**, không phải phạm vi “dòng code trong procedure”.

## 13. Oracle: PRAGMA AUTONOMOUS_TRANSACTION

Oracle có cơ chế đặc biệt cho **autonomous transaction**.

Ví dụ:

```sql
CREATE OR REPLACE PROCEDURE lesson344_oracle_audit(
    p_message IN VARCHAR2
)
AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO lesson344_oracle_log (message)
    VALUES (p_message);

    COMMIT;
END;
/
```

Procedure này thực hiện giao dịch độc lập với transaction của caller.

### 13.1. Hành vi minh họa

```sql
INSERT INTO lesson344_oracle_log (message)
VALUES ('outer-uncommitted');

BEGIN
    lesson344_oracle_audit('autonomous-audit');
END;
/

ROLLBACK;
```

Sau outer `ROLLBACK`:

- Dòng `outer-uncommitted` được hoàn tác.
- Dòng `autonomous-audit` có thể **vẫn tồn tại**, vì autonomous procedure đã commit transaction riêng.

Đây là chủ đích của autonomous transaction.

### 13.2. Vì sao autonomous transaction dễ gây sai nghiệp vụ?

Một log autonomous có thể ghi “chuyển tiền thành công” trước khi transaction chuyển tiền của caller sau đó thất bại và rollback. Khi ấy log đã commit **không phản ánh kết quả nghiệp vụ cuối cùng**.

Autonomous transaction cũng có thể vướng khóa khi cố đọc/sửa tài nguyên mà outer transaction đang giữ, và không được xem là một cách tránh mọi vấn đề đồng thời.

Dùng cơ chế này chỉ khi thực sự cần một thao tác độc lập, chẳng hạn một loại ghi nhận chẩn đoán phù hợp, với thông điệp không khẳng định sai trạng thái commit của nghiệp vụ ngoài.

### 13.3. Hàm và trigger Oracle có ngoại lệ riêng

Oracle có các giới hạn khi hàm được gọi trong câu SQL cố thực hiện DML hoặc transaction control. Một số ngữ cảnh có thể dùng autonomous transaction theo cơ chế riêng.

Vì vậy không phát biểu “mọi Oracle function/trigger đều được phép COMMIT” hoặc “mọi Oracle function/trigger luôn bị cấm COMMIT” mà không xét **ngữ cảnh và pragma**.

### 13.4. DDL Oracle và implicit commit

Nhiều câu DDL của Oracle như `CREATE TABLE` hoặc `ALTER TABLE` có implicit commit theo quy tắc DBMS. Chúng không được xem như một câu INSERT bình thường mà caller có thể rollback tùy ý.

Một procedure trộn DDL và DML cần được đánh giá transaction boundary riêng.

## 14. Oracle: exception và savepoint

Oracle hỗ trợ savepoint:

```sql
SAVEPOINT before_optional_step;

-- DML của một bước tùy chọn.

ROLLBACK TO before_optional_step;
```

Ví dụ một procedure có exception handler có thể chọn:

- `ROLLBACK TO savepoint` để hoàn tác một phần.
- `ROLLBACK` toàn transaction nếu có quyền sở hữu và đó là chủ đích.
- `RAISE` để báo lỗi về caller và để caller quyết định rollback.

**Bắt exception không tự tương đương rollback mọi DML trước đó của session.** Phải hiểu tính nguyên tử của từng statement, phạm vi transaction và cách lỗi được truyền qua khối PL/SQL.

Một thiết kế procedure dùng chung với ứng dụng nên có hợp đồng rõ: “thủ tục không commit/rollback; khi lỗi sẽ raise để caller quản lý”, trừ khi có lý do đặc biệt.

## 15. SQLite: không có stored procedure SQL native

SQLite cốt lõi hỗ trợ:

- Transaction với `BEGIN`, `COMMIT`, `ROLLBACK`.
- `SAVEPOINT`, `ROLLBACK TO` và `RELEASE`.
- Trigger theo ngôn ngữ SQL của SQLite.
- Các hàm mở rộng có thể đăng ký từ ứng dụng.

Nhưng **không có lệnh `CREATE PROCEDURE ... CALL ...` chuẩn native giống các hệ quản trị client/server nêu trên**.

Vì vậy ranh giới giao dịch của một nghiệp vụ “procedure-like” thường được viết ở **tầng ứng dụng** bằng một nhóm câu SQL dùng cùng connection.

### 15.1. Ví dụ SQLite transaction do ứng dụng điều khiển

```sql
CREATE TABLE lesson344_sqlite_accounts (
    account_id INTEGER PRIMARY KEY,
    balance INTEGER NOT NULL CHECK (balance >= 0)
);

INSERT INTO lesson344_sqlite_accounts (account_id, balance)
VALUES (10, 1000), (20, 1000);
```

Giao dịch thử:

```sql
BEGIN IMMEDIATE;

UPDATE lesson344_sqlite_accounts
SET balance = balance - 100
WHERE account_id = 10
  AND balance >= 100;

UPDATE lesson344_sqlite_accounts
SET balance = balance + 100
WHERE account_id = 20;

ROLLBACK;
```

Nếu muốn chuyển tiền thực tế, ứng dụng phải kiểm tra số dòng bị ảnh hưởng, đảm bảo tài khoản tồn tại và quy tắc nghiệp vụ, sau đó mới `COMMIT`. `ROLLBACK` trong ví dụ giữ nguyên dữ liệu.

### 15.2. BEGIN DEFERRED/IMMEDIATE/EXCLUSIVE

SQLite có các chế độ bắt đầu transaction như `BEGIN DEFERRED` hoặc `BEGIN IMMEDIATE`. Chúng liên quan đến thời điểm lấy quyền ghi/khóa và khả năng xảy ra `SQLITE_BUSY` khi cạnh tranh.

Chế độ và hành vi còn tùy journal mode, ví dụ WAL. Không suy rằng SQLite dùng cơ chế khóa và MVCC giống hệt PostgreSQL.

### 15.3. SAVEPOINT không phải nested COMMIT độc lập

```sql
BEGIN;

SAVEPOINT unit_1;

UPDATE lesson344_sqlite_accounts
SET balance = balance + 1
WHERE account_id = 10;

RELEASE unit_1;

ROLLBACK;
```

`RELEASE unit_1` **không làm thay đổi bên trong bền vững độc lập** khi outer transaction vẫn còn; outer `ROLLBACK` vẫn hoàn tác cập nhật.

Khi dùng savepoint cấp ngoài cùng không có transaction khác, `RELEASE` có thể đóng giao dịch tương ứng theo quy tắc SQLite, nhưng không được suy rằng mọi `RELEASE` tương đương một `COMMIT` độc lập.

### 15.4. Trigger SQLite không phải procedure điều khiển transaction

SQLite trigger có ngữ nghĩa riêng, gồm hàm `RAISE(...)` với các kiểu hành vi lỗi. Nó không phải một stored procedure có thể đặt `BEGIN TRANSACTION`, `COMMIT` tùy ý trong thân trigger.

Với ứng dụng sử dụng SQLite, **caller quản lý transaction** là mô hình chính.

## 16. Bảng so sánh hành vi theo DBMS

| Câu hỏi | PostgreSQL | SQL Server | MySQL/InnoDB | Oracle Database | SQLite |
|---|---|---|---|---|---|
| Có native stored procedure? | Có | Có | Có | Có | Không theo SQL core |
| Gọi thủ tục | `CALL` | `EXEC` | `CALL` | PL/SQL call hoặc `CALL` | Application |
| Function thường được COMMIT? | Không | Không trong T-SQL UDF | Không | Bị giới hạn theo ngữ cảnh, có ngoại lệ autonomous | Không có stored SQL function tương đương |
| Thủ tục thường có thể commit? | **Có điều kiện về cách gọi** | Có | Có | Có | Không áp dụng |
| Có thể commit trong procedure khi caller đã mở transaction? | Transaction control bị chặn trong ngữ cảnh explicit transaction block | Inner COMMIT thường chỉ giảm `@@TRANCOUNT` | `START TRANSACTION` có thể commit transaction hiện hữu; `COMMIT` kết thúc transaction session | `COMMIT` thường commit transaction session của caller | Caller quyết định |
| Nested transaction commit độc lập mặc định? | Không | Không, dùng counter | Không | Không, trừ autonomous mechanism riêng | Không |
| Savepoint | SQL transaction và khối `EXCEPTION`; PL/pgSQL không hỗ trợ trực tiếp savepoint statements như SQL client | `SAVE TRANSACTION` | `SAVEPOINT` | `SAVEPOINT` | `SAVEPOINT` |
| Autonomous transaction native? | Không theo PL/pgSQL thường | Không theo mô hình procedure mặc định | Không theo mô hình procedure mặc định | Có `PRAGMA AUTONOMOUS_TRANSACTION` | Không có stored procedure native |
| DDL có thể implicit commit? | Nhiều DDL transactional, có ngoại lệ lệnh/cấu hình | Tùy DDL/ngữ cảnh | **Nhiều DDL implicit commit** | **Nhiều DDL implicit commit** | Thường transactional trong explicit transaction theo cơ chế SQLite |
| Ai nên sở hữu transaction của một request nhiều bước? | Caller nếu muốn một đơn vị nguyên tử | Caller hoặc proc theo hợp đồng rõ | Caller nếu muốn tránh implicit commit từ helper | Caller nếu muốn tránh commit ngầm của proc | Application |

Bảng là mô tả quy tắc khái quát. Cần đối chiếu **phiên bản, storage engine, transaction settings và driver** trước khi chuyển mã giữa các DBMS.

## 17. Ví dụ nghiệp vụ: một lần chuyển tiền phải nguyên tử

Một nghiệp vụ chuyển 100 từ tài khoản 10 sang tài khoản 20 có hai cập nhật:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10
  AND balance >= 100;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 20;
```

Nếu mỗi câu được commit riêng:

- Câu trừ tiền có thể thành công.
- Câu cộng tiền có thể lỗi.
- Kết quả chỉ một phía thay đổi.

Để toàn bộ giao dịch nguyên tử, cần:

1. Kiểm tra điều kiện và số dòng cập nhật.
2. Đảm bảo đúng tài khoản nguồn và đích.
3. Ghi thay đổi trong **cùng transaction**.
4. Ghi sổ/marker cần thiết trong cùng transaction.
5. Chỉ commit khi mọi bước hợp lệ.
6. Rollback tất cả nếu một bước không thành công.

### 17.1. Caller-owned thường dễ bảo vệ invariant nhiều bảng

Ví dụ kiến trúc:

```text
Service.transfer(request_key, from, to, amount)
  BEGIN transaction
    validate_account(...)
    CALL debit_without_commit(...)
    CALL credit_without_commit(...)
    CALL record_transfer_without_commit(...)
  COMMIT

Khi có lỗi:
  ROLLBACK toàn request
```

Các helper chỉ nên thực hiện thay đổi và báo lỗi, không tự commit hoặc rollback nếu **hợp đồng caller-owned**.

### 17.2. Tại sao không gọi procedure commit theo batch trong đây?

Nếu `CALL debit` đã commit tiền trừ, còn `CALL credit` lỗi, caller có thể không rollback được bước trừ. Đây là ví dụ về **sai ranh giới giao dịch** nghiêm trọng hơn khác biệt cú pháp.

## 18. Giao dịch lồng nhau, savepoint và autonomous transaction là ba khái niệm khác nhau

### 18.1. Giao dịch lồng theo bộ đếm

SQL Server cho phép nhiều `BEGIN TRAN` và theo dõi `@@TRANCOUNT`, nhưng không tự cung cấp một commit độc lập cho mức trong.

### 18.2. Savepoint

Savepoint đánh dấu vị trí trong **cùng một transaction** để có thể rollback một phần khi DBMS và trạng thái lỗi cho phép. Phần thay đổi chưa commit vẫn có thể bị hoàn tác khi outer transaction rollback.

### 18.3. Autonomous transaction

Oracle `PRAGMA AUTONOMOUS_TRANSACTION` tạo một giao dịch tách biệt có thể commit độc lập với transaction ngoài. Đó không phải savepoint hay `BEGIN TRAN` lồng theo bộ đếm.

### 18.4. Khác nhau qua ví dụ

```text
Outer transaction T:
  INSERT A

  Savepoint S:
    INSERT B
    RELEASE S

  ROLLBACK T
Kết quả: A và B đều rollback.
```

Trong autonomous transaction của Oracle:

```text
Outer T:
  INSERT A

  Autonomous U:
    INSERT B
    COMMIT U

  ROLLBACK T
Kết quả: A rollback, B có thể còn.
```

Đây là khác biệt quan trọng khi thiết kế audit, batch và tích hợp hệ thống.

## 19. Lỗi và rollback theo phạm vi nào?

### 19.1. PostgreSQL: transaction thất bại và EXCEPTION

Khi một statement lỗi bên trong transaction, PostgreSQL thường đánh dấu transaction ở trạng thái lỗi; các statement tiếp theo có thể nhận `25P02` cho đến khi rollback.

PL/pgSQL `EXCEPTION` có cơ chế subtransaction để hoàn tác những thao tác trong block lỗi, cho phép xử lý ngoại lệ cục bộ theo quy tắc đã nêu.

**Nhưng xử lý một exception không tự commit.**

### 19.2. SQL Server: transaction có thể ở trạng thái uncommittable

Một số lỗi và `XACT_ABORT` có thể làm transaction thành `XACT_STATE() = -1`. Trong trạng thái đó, không phải cứ gọi `COMMIT` hoặc `ROLLBACK TO SAVEPOINT` là được; owner cần xử lý rollback toàn transaction.

### 19.3. MySQL: handler không tạo transaction riêng

Một `DECLARE HANDLER` chạy trong bối cảnh session/transaction hiện tại. Nếu handler gọi `ROLLBACK` thì tác động rollback phải được xét theo transaction đang mở, không giới hạn tự động trong thủ tục.

### 19.4. Oracle: exception không tự có nghĩa rollback toàn caller

Trong PL/SQL, một lỗi có thể được xử lý, truyền tiếp hoặc làm statement/khối gọi thất bại tùy ngữ cảnh. Không mặc định rằng mọi DML từ trước trong cùng session đã được hoàn tác toàn bộ.

Phải có hợp đồng caller/procedure về `COMMIT`, `ROLLBACK`, `SAVEPOINT` và cách phát lỗi.

### 19.5. SQLite: xử lý lỗi còn phụ thuộc conflict resolution

Các cơ chế như `RAISE(ABORT)` hoặc `RAISE(ROLLBACK)` trong SQLite trigger có phạm vi ảnh hưởng khác nhau. Không đồng nhất mọi lỗi trigger với rollback toàn transaction mà không xem loại hành động và ngữ cảnh.

## 20. COMMIT trong vòng lặp: ưu và nhược điểm

Giả sử cần xử lý 1.000.000 sự kiện.

**Một transaction duy nhất:**

```text
BEGIN
  xử lý 1.000.000 sự kiện
COMMIT
```

Ưu điểm:

- Có thể bảo vệ một invariant bao trùm toàn bộ batch nếu thiết kế đúng.
- Dễ mô tả “all-or-nothing”.

Nhược điểm:

- Transaction có thể giữ khóa và snapshot lâu.
- Lỗi ở gần cuối khiến phải làm lại phần lớn công việc.
- Có thể tạo áp lực lên WAL/redo, log, bộ nhớ và bảo trì.

**Commit theo lô 10.000 sự kiện:**

```text
Batch 1: xử lý → COMMIT
Batch 2: xử lý → COMMIT
...
Batch 100: xử lý → COMMIT
```

Ưu điểm:

- Giới hạn phạm vi một transaction.
- Có điểm checkpoint phục hồi.
- Có thể giảm thời gian giữ một số khóa.

Nhược điểm:

- Không thể rollback những batch đã commit khi batch sau lỗi.
- Retry phải bỏ qua hoặc xử lý idempotent batch đã hoàn tất.
- Dữ liệu có thể ở trạng thái **hoàn thành một phần** giữa các batch.
- Khả năng transaction control trong stored procedure còn phụ thuộc DBMS.

### 20.1. Checkpoint và dữ liệu nên cùng transaction

Nếu batch 1 cập nhật dữ liệu thành công, nhưng checkpoint “batch 1 done” lại ghi ở transaction khác, có thể xuất hiện hai trạng thái sai:

- Data commit rồi, checkpoint chưa ghi → retry xử lý trùng.
- Checkpoint ghi rồi, data chưa commit → retry bỏ sót.

Vì vậy, thiết kế tốt thường ghi dữ liệu và checkpoint **trong cùng transaction của batch**, với khóa idempotency rõ ràng.

### 20.2. Batch không thể tránh tính đúng đắn của nghiệp vụ

Không được chia một phép chuyển tiền hai phía thành “batch trừ tiền” và “batch cộng tiền” với commit độc lập, trừ khi xây dựng hẳn mô hình bù trừ/chấp nhận nhất quán cuối cùng theo nghiệp vụ.

## 21. Transaction trong Java/JDBC và connection pool

Một ứng dụng Java thường làm:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        // Gọi những procedure KHÔNG tự điều khiển transaction.
        try (CallableStatement cs = connection.prepareCall(
                "{call lesson344_pg_write_only(?)}")) {
            cs.setString(1, "from-jdbc");
            cs.execute();
        }

        // Thực hiện DML bổ sung trong cùng connection.

        connection.commit();
    } catch (SQLException ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    }
}
```

Đây là ví dụ cho PostgreSQL procedure **không có `COMMIT`/`ROLLBACK`**.

### 21.1. PostgreSQL: autocommit=false thường là transaction ngoài

Nếu ứng dụng tắt autocommit rồi gọi một procedure PostgreSQL có `COMMIT` bên trong, lời gọi có thể thất bại vì thủ tục không được kết thúc transaction trong transaction block do caller kiểm soát.

Muốn gọi procedure commit theo batch hợp lệ, cần một connection/cách gọi đáp ứng quy tắc `CALL` top-level. **Không cố lách lỗi bằng cách cho ứng dụng bắt đầu thêm BEGIN.**

### 21.2. MySQL: helper có START TRANSACTION có thể phá transaction JDBC

JDBC đặt `autoCommit=false`, rồi gọi stored procedure MySQL có `START TRANSACTION`. Theo quy tắc MySQL, câu đó có thể commit transaction đang mở trước đó, trái với mong đợi “service sẽ rollback toàn request khi lỗi”.

Cần thiết kế thủ tục caller-owned **không START TRANSACTION/COMMIT** khi nó được gọi dưới transaction ứng dụng.

### 21.3. Oracle: helper COMMIT có thể commit cả thay đổi DAO trước đó

Ứng dụng JDBC đã sửa bảng A rồi gọi procedure Oracle có `COMMIT`. Procedure có thể xác nhận toàn bộ transaction session, bao gồm A.

Sau đó `connection.rollback()` **không thể lấy lại những thay đổi đã commit**.

### 21.4. SQL Server: @@TRANCOUNT và XACT_STATE cần được hiểu ở tầng procedure

Khi ứng dụng quản lý transaction, stored procedure cần tránh commit/rollback transaction của caller nếu không có chủ đích.

Một inner `COMMIT` trong SQL Server chưa chắc commit ngoài vì `@@TRANCOUNT` còn > 0, nhưng một inner `ROLLBACK` không đặt savepoint có thể hủy transaction ngoài. Vì vậy không nên cho rằng hành vi của SQL Server “an toàn” chỉ vì có nested counter.

### 21.5. Connection pool cần trả connection ở trạng thái sạch

Khi dùng pool:

- Kết thúc transaction trước khi trả connection.
- Khôi phục các thiết lập cần thiết theo hợp đồng pool.
- Không giữ connection lỗi/aborted để dùng cho request tiếp.
- Không trộn các helper có hợp đồng transaction khác nhau trên cùng connection mà không kiểm soát.
- Không giữ transaction mở khi gọi API mạng không liên quan.

## 22. Framework @Transactional và thủ tục lưu trữ

Trong Spring hoặc framework tương tự, annotation `@Transactional` thường tạo transaction ở ranh giới service/DAO theo cấu hình transaction manager.

Nếu một method như:

```java
@Transactional
public void checkout(Order order) {
    inventoryRepository.reserve(order);
    paymentRepository.record(order);
    procedureRepository.callUpdateSummary(order);
}
```

mong muốn mọi thay đổi là một transaction, thì thủ tục được gọi **không nên tự COMMIT** theo cách có thể phá hợp đồng đó.

### 22.1. @Transactional không áp đặt cùng nghĩa lên mọi DBMS

Annotation Java không thay đổi quy tắc server:

- PostgreSQL có thể từ chối procedure tự commit trong transaction block.
- MySQL có thể implicit commit ở `START TRANSACTION` trong procedure.
- Oracle có thể commit transaction caller.
- SQL Server đòi hỏi hiểu nested count và rollback scope.

**Không thể chỉ thêm @Transactional để bảo đảm thủ tục tự commit trở thành một phần an toàn của transaction ứng dụng.**

### 22.2. Retry phải bao quanh ranh giới transaction thật

Nếu một giao dịch lỗi do deadlock/serialization, cần retry **cả phần đọc, kiểm tra, cập nhật, gọi thủ tục và commit**, trong transaction mới theo chính sách DBMS.

Không nên retry một thủ tục đã tự commit các phần trước mà giả định mọi thao tác lần đầu chưa có tác động.

### 22.3. Self-invocation và proxy

Trong Spring cấu hình proxy thông dụng, gọi một phương thức annotated `@Transactional` qua `this.method()` bên trong cùng đối tượng có thể không đi qua proxy tạo transaction. Đó là một lý do ranh giới ở tầng ứng dụng không như lập trình viên dự kiến.

Thiết kế transaction owner phải được xác nhận trên **đường gọi thật**, không chỉ tên annotation.

## 23. Deadlock, lỗi tuần tự hóa và partial commit

Một procedure xử lý nhiều bước có thể gặp:

- Deadlock.
- Serialization failure.
- Vi phạm unique/FK/check.
- Timeout.
- Kết nối mất.
- Lỗi nghiệp vụ.

### 23.1. Một transaction duy nhất

Nếu toàn bộ công việc trong transaction chưa commit và thất bại, có thể rollback toàn bộ thay đổi transactional theo quy tắc DBMS.

Khi retry, nên đọc lại dữ liệu và chạy lại toàn bộ logic nếu lỗi có thể retry.

### 23.2. Procedure commit nhiều lần

Giả sử:

```text
Batch 1 → COMMIT thành công
Batch 2 → COMMIT thành công
Batch 3 → deadlock và rollback
```

Không thể xem toàn bộ procedure là một request “chưa làm gì”. Batch 1 và 2 **đã hoàn tất**.

Retry phải:

- Xác minh checkpoint.
- Bỏ qua hoặc chạy idempotent những batch đã hoàn thành.
- Tiếp tục từ phạm vi hợp lệ.
- Không cộng đôi, trừ đôi hoặc phát sự kiện trùng.

### 23.3. Mất kết nối tại COMMIT: kết quả có thể chưa rõ

Nếu client gửi `COMMIT` rồi mất mạng trước khi nhận phản hồi, DBMS có thể đã commit hoặc chưa. Không tự kết luận rollback chỉ vì phía ứng dụng nhận exception.

Một `request_key`/`batch_id` ổn định cùng ràng buộc unique và bảng kết quả có thể giúp tra trạng thái trước khi quyết định retry.

### 23.4. Không đưa tác dụng phụ ngoài DB vào vòng retry mù

Một thủ tục có thể gọi extension, hàm ngoại hoặc cơ chế tích hợp; ứng dụng cũng có thể gửi SMS trước `COMMIT`.

Nếu transaction rollback nhưng SMS đã gửi, retry sẽ gây gửi lặp. Cần thiết kế idempotency hoặc outbox/consumer phù hợp.

## 24. Transactional outbox cho procedure

**Transactional outbox** là cách tách “ghi trạng thái cần phát sự kiện” khỏi “thực sự gửi sự kiện ra ngoài”.

Trong cùng transaction do caller hoặc procedure sở hữu:

1. Cập nhật bảng nghiệp vụ.
2. Ghi mã yêu cầu/batch.
3. Ghi dòng outbox.
4. Commit.

Một worker riêng sau commit phát sự kiện từ outbox.

```text
Transaction T:
  UPDATE orders
  INSERT order_events_outbox
  COMMIT

Dispatcher:
  SELECT outbox chưa gửi
  gửi message/API
  đánh dấu đã gửi
```

Nếu T rollback, dòng outbox transactional cũng rollback. Nhưng nếu dispatcher đã phát sự kiện rồi chết trước khi đánh dấu gửi, sự kiện có thể phát lại. **Consumer cần idempotency**; outbox không tự bảo đảm exactly-once end-to-end.

Trong procedure commit theo batch, hãy bảo đảm outbox của **mỗi batch** được commit cùng dữ liệu của batch đó. Không để outbox ghi nhận thành công trước khi nghiệp vụ được commit.

## 25. Bảo mật và quyền quản lý transaction

Thủ tục có thể chạy với quyền của người gọi hoặc quyền được cấp theo cấu hình DBMS. Điều đó không đồng nghĩa nó được tự kết thúc transaction tùy ý.

Ví dụ:

- PostgreSQL có hạn chế transaction control trong procedure `SECURITY DEFINER`.
- SQL Server sử dụng các cơ chế thực thi theo ngữ cảnh bảo mật, nhưng `COMMIT`/`ROLLBACK` vẫn tác động transaction của session.
- Oracle autonomous transaction có thể ghi độc lập, nhưng phải được kiểm soát quyền và dữ liệu.
- MySQL `SQL SECURITY DEFINER` không biến `START TRANSACTION` thành nested transaction độc lập.

**Phân quyền thực thi procedure và quyền sở hữu transaction là hai vấn đề khác nhau.**

Không dùng quyền cao hơn để bỏ qua giới hạn ranh giới giao dịch mà DBMS đặt ra.

## 26. Quan sát và xác minh ranh giới giao dịch

Khi một lời gọi thủ tục có hành vi bất ngờ, cần hỏi:

1. Caller đang ở chế độ autocommit nào?
2. Client/ORM có bọc `CALL`/`EXEC` trong transaction tường minh không?
3. Procedure có `COMMIT`, `ROLLBACK` hoặc `START TRANSACTION` bên trong không?
4. Có procedure khác được gọi lồng nhau không?
5. Có DDL gây implicit commit không?
6. Có exception handler tự rollback không?
7. Có savepoint, autonomous transaction hoặc nested counter không?
8. Lỗi xảy ra trước hay sau một lần commit?
9. Connection bị mất tại commit hay trước commit?
10. Có mã request/batch để tránh xử lý lặp không?

### 26.1. PostgreSQL: xem trạng thái transaction

Có thể quan sát transaction hiện tại và các session qua các view như `pg_stat_activity` hoặc các hàm transaction ID nếu phù hợp quyền và mục tiêu chẩn đoán.

Không suy ra “thủ tục có transaction riêng” chỉ vì mỗi dòng log có transaction ID khác nhau trong thủ tục batch; đó có thể là kết quả của nhiều lần commit trong cùng `CALL` hợp lệ.

### 26.2. SQL Server: xem @@TRANCOUNT và XACT_STATE

```sql
SELECT
    @@TRANCOUNT AS transaction_depth,
    XACT_STATE() AS transaction_state;
```

Quan sát trước và sau lời gọi để xác định procedure có để lại transaction depth ngoài dự kiến hay không. Nhưng cần nhớ `@@TRANCOUNT` là **bộ đếm**, không phải danh sách transaction độc lập.

### 26.3. MySQL: kiểm tra autocommit và statement

```sql
SELECT @@autocommit;
```

Giá trị này chỉ cho biết chế độ session, không đủ để kết luận mọi statement trong procedure không thể gây implicit commit. Phải kiểm tra thân procedure, `START TRANSACTION` và những DDL có liên quan.

### 26.4. Oracle: ghi nhận COMMIT ở đâu

Nếu caller có một transaction mở, `COMMIT` của procedure có thể kết thúc nó. Cần xem code procedure, nested call, autonomous pragma và DDL.

### 26.5. Đừng dựa vào số ID liên tiếp để suy rollback

Nhiều DBMS có identity/sequence/auto-increment không bảo đảm hoàn tác các giá trị đã cấp khi transaction rollback. **Khoảng trống ID không phải bằng chứng transaction commit hay thất bại.**

## 27. Cách thiết kế API thủ tục dễ tích hợp

Có thể dùng một bản mô tả hợp đồng:

| Thuộc tính | Mô tả nên ghi |
|---|---|
| Tên thủ tục | `process_order_once` |
| DBMS/phiên bản | PostgreSQL X, MySQL Y, v.v. |
| Ai sở hữu transaction? | Caller hoặc procedure |
| Có commit/rollback bên trong? | Có/Không, vị trí nào |
| Có thể gọi trong transaction ngoài? | Có/Không, giới hạn |
| Nếu lỗi, đã commit phần nào chưa? | Không hoặc các batch cụ thể |
| Có idempotency key? | Khóa và phạm vi uniqueness |
| Side effect bên ngoài | Có/Không, thông qua outbox hay API |
| Cơ chế retry | Toàn transaction hoặc theo checkpoint |
| Có DDL hoặc autonomous transaction? | Nêu rõ |
| Phân quyền | Invoker/definer và quyền cần thiết |

### 27.1. Hợp đồng caller-owned minh họa

> Thủ tục chỉ đọc/ghi dữ liệu trong transaction hiện tại; không `COMMIT`/`ROLLBACK`; khi lỗi không thể xử lý nội bộ sẽ báo lỗi để caller quyết định. Caller chịu trách nhiệm đảm bảo transaction, idempotency và retry.

### 27.2. Hợp đồng procedure-owned minh họa

> Thủ tục tự quản lý giao dịch và có thể commit từng batch; chỉ được gọi trong ngữ cảnh được DBMS hỗ trợ, không được mặc định gọi dưới outer transaction. Caller phải xử lý khả năng thành công một phần và có checkpoint để chạy lại.

Hợp đồng thứ hai cần đặc biệt rõ trên PostgreSQL, MySQL và Oracle vì những khác biệt được trình bày.

## 28. Những lỗi thường gặp

### Lỗi 1. Tưởng BEGIN trong thủ tục là BEGIN TRANSACTION

`BEGIN ... END` trong PL/pgSQL, PL/SQL hoặc compound statement MySQL thường mở khối lệnh. Không đồng nhất với `BEGIN TRANSACTION`/`START TRANSACTION`.

### Lỗi 2. Tưởng mỗi procedure có transaction riêng

Một procedure thường chạy trong ngữ cảnh transaction của connection. Không tự có nested atomic boundary chỉ vì lời gọi tách thành procedure.

### Lỗi 3. Gọi PostgreSQL procedure có COMMIT dưới BEGIN của caller

`CALL` có thể chạy nhưng `COMMIT` bên trong bị từ chối trong ngữ cảnh transaction block không cho phép. Dùng thủ tục không commit để caller quản lý nếu muốn một transaction nguyên tử.

### Lỗi 4. Tưởng PostgreSQL function có thể COMMIT như procedure

Function PostgreSQL không được tự kết thúc transaction. Không chuyển `CALL` thành `SELECT function()` rồi giữ nguyên COMMIT.

### Lỗi 5. Đặt COMMIT trong PL/pgSQL EXCEPTION block

Khối có `EXCEPTION` mang ngữ nghĩa subtransaction; không được kết thúc transaction tại phạm vi đó.

### Lỗi 6. Bỏ qua hạn chế SECURITY DEFINER/SET của PostgreSQL

Một procedure thêm `SECURITY DEFINER` hoặc `SET` trong định nghĩa có thể mất khả năng transaction control.

### Lỗi 7. Nghĩ SQL Server inner COMMIT đã lưu bền vững

Nếu outer transaction còn hoạt động, `COMMIT` bên trong chủ yếu giảm `@@TRANCOUNT`, không commit độc lập.

### Lỗi 8. Dùng ROLLBACK SQL Server trong helper mà không xét caller

`ROLLBACK TRAN` không đặt savepoint thường hủy toàn transaction, có thể bao gồm công việc caller.

### Lỗi 9. Chỉ nhìn @@TRANCOUNT mà quên XACT_STATE

`@@TRANCOUNT > 0` không nói transaction có còn commit được. `XACT_STATE() = -1` yêu cầu xử lý riêng.

### Lỗi 10. MySQL procedure START TRANSACTION dưới outer transaction

`START TRANSACTION` có thể implicit commit transaction trước đó. Đây không phải nested transaction.

### Lỗi 11. Dùng BEGIN của MySQL stored program để bắt đầu transaction

`BEGIN ... END` là compound statement. Cần `START TRANSACTION` nếu thủ tục tự sở hữu transaction theo đúng thiết kế.

### Lỗi 12. Tưởng DDL MySQL và Oracle rollback như DML thông thường

Nhiều DDL gây implicit commit. Không đặt DDL trong quy trình transactional mà không hiểu ngữ nghĩa engine.

### Lỗi 13. Oracle procedure COMMIT và tưởng chỉ commit dòng của procedure

COMMIT thông thường của Oracle tác động transaction session, bao gồm thay đổi trước đó của caller.

### Lỗi 14. Lạm dụng Oracle autonomous transaction cho audit “thành công”

Outer transaction có thể rollback, audit đã commit độc lập. Log có thể mô tả sai kết quả nghiệp vụ.

### Lỗi 15. Tưởng SQLite hỗ trợ CREATE PROCEDURE native

SQLite core không có stored procedure SQL như PostgreSQL/MySQL; transaction boundary nằm ở ứng dụng.

### Lỗi 16. Tưởng RELEASE SAVEPOINT tương đương COMMIT độc lập

Trong outer transaction, `RELEASE` không ngăn outer rollback hoàn tác thay đổi.

### Lỗi 17. Commit theo batch nhưng không lưu checkpoint

Nếu lỗi giữa các batch, retry có thể xử lý lại dữ liệu đã commit. Cần checkpoint/idempotency phù hợp.

### Lỗi 18. Đặt checkpoint khác transaction với dữ liệu batch

Data và checkpoint có thể lệch trạng thái. Nên commit cùng nhau khi cùng một đơn vị công việc.

### Lỗi 19. Gửi email/API ngoài DB trước COMMIT rồi tự retry

DB rollback không thu hồi tác dụng phụ bên ngoài. Thiết kế outbox/idempotency thay vì retry mù.

### Lỗi 20. Dùng @Transactional để “vô hiệu hóa” COMMIT server

Framework phía ứng dụng không thay đổi hành vi transaction control của stored procedure trong DBMS.

### Lỗi 21. Tưởng mất kết nối tại COMMIT nghĩa là rollback

Client có thể không biết DB đã commit. Dùng request key và cơ chế đối chiếu thay vì làm lại yêu cầu với key mới.

### Lỗi 22. Dùng chung một procedure cho hai hợp đồng transaction đối nghịch

Một helper vừa muốn caller rollback toàn bộ, vừa tự commit từng phần tạo mâu thuẫn. Nên tách API hoặc định nghĩa hợp đồng rõ.

## 29. Bài tập thực hành có lời giải

Các bài tập dưới đây có thể dùng cho thảo luận, hoặc thực hiện trên **database thử nghiệm tương ứng**. Đoạn SQL của mỗi DBMS dùng ngữ pháp riêng; đừng chạy chéo.

### Bài 1. BEGIN là khối hay transaction?

Trong PostgreSQL:

```sql
CREATE OR REPLACE PROCEDURE p()
LANGUAGE plpgsql
AS $$
BEGIN
    NULL;
END;
$$;
```

**Câu hỏi:** `BEGIN` có mở transaction mới cho `p()` không?

**Đáp án:** Không. Đây là `BEGIN` của khối PL/pgSQL, không phải `BEGIN TRANSACTION` của client.

### Bài 2. PostgreSQL function ghi dữ liệu

```sql
BEGIN;

SELECT lesson344_pg_write_log('function-call');

ROLLBACK;
```

**Đáp án:** function ghi trong transaction của caller. Nếu rollback thành công, dòng mới được hoàn tác. Function không commit riêng.

### Bài 3. Gọi procedure PostgreSQL có COMMIT trong BEGIN

```sql
BEGIN;
CALL lesson344_pg_commit_steps();
ROLLBACK;
```

**Đáp án:** thủ tục cố `COMMIT` trong ngữ cảnh `CALL` nằm trong transaction block tường minh nên PostgreSQL từ chối transaction control. Không coi đó là nested transaction.

### Bài 4. Gọi procedure PostgreSQL không COMMIT trong BEGIN

```sql
BEGIN;
CALL lesson344_pg_write_only('hello');
ROLLBACK;
```

**Đáp án:** lời gọi phù hợp vì procedure không tự kết thúc transaction. Dòng hello được rollback cùng caller.

### Bài 5. Tại sao không đặt COMMIT trong EXCEPTION?

**Đáp án:** block PL/pgSQL có `EXCEPTION` mang cơ chế subtransaction. PostgreSQL không cho kết thúc transaction trong phạm vi block đó. Cần tách phạm vi và hợp đồng xử lý ngoại lệ.

### Bài 6. COMMIT sau batch 1, lỗi batch 2

Một procedure PostgreSQL chạy top-level:

```text
INSERT batch 1
COMMIT
INSERT batch 2
ERROR
```

**Đáp án:** batch 1 đã commit không được hoàn tác chỉ vì batch 2 lỗi. Retry cần checkpoint và idempotency; cả procedure không còn all-or-nothing.

### Bài 7. SQL Server @@TRANCOUNT

```sql
BEGIN TRAN;
BEGIN TRAN;
COMMIT TRAN;

SELECT @@TRANCOUNT;
ROLLBACK TRAN;
```

**Đáp án:** trước rollback, `@@TRANCOUNT = 1`. Outer transaction vẫn hoạt động; rollback sau đó hủy toàn transaction.

### Bài 8. SQL Server rollback trong helper

Caller đã `BEGIN TRAN`, helper thực hiện `ROLLBACK TRAN` không có savepoint.

**Đáp án:** có thể hủy cả transaction của caller, không chỉ công việc helper. Cần hợp đồng và chiến lược savepoint/`XACT_STATE` phù hợp.

### Bài 9. XACT_STATE bằng -1

**Câu hỏi:** có thể rollback về savepoint rồi commit phần còn lại một cách mặc định không?

**Đáp án:** Không. Transaction ở trạng thái uncommittable, phải xử lý rollback toàn transaction theo quy tắc SQL Server; không coi savepoint là cách thoát.

### Bài 10. MySQL START TRANSACTION trong procedure

Caller:

```sql
START TRANSACTION;
INSERT INTO lesson344_mysql_log(message) VALUES('caller');
CALL lesson344_mysql_atomic('procedure');
ROLLBACK;
```

**Đáp án:** `START TRANSACTION` trong procedure có thể commit transaction đang hoạt động của caller; `COMMIT` trong procedure commit phần riêng tiếp theo. `ROLLBACK` cuối không khôi phục được phần đã commit.

### Bài 11. MySQL helper không transaction control

```sql
START TRANSACTION;
CALL lesson344_mysql_write_only('part-of-caller');
ROLLBACK;
```

**Đáp án:** với bảng InnoDB và không có implicit commit ở nơi khác, thay đổi của helper thuộc transaction caller và bị rollback.

### Bài 12. DELIMITER của MySQL

**Câu hỏi:** `DELIMITER //` có commit transaction không?

**Đáp án:** Không. Đây là chỉ thị client dùng để gửi định nghĩa stored program chứa nhiều dấu chấm phẩy; không phải `COMMIT` và không tạo transaction.

### Bài 13. DDL MySQL trong transaction

Caller chạy `START TRANSACTION`, `INSERT`, `CREATE TABLE`, `ROLLBACK`.

**Đáp án:** nhiều DDL MySQL gây implicit commit, nên không được mặc định INSERT và CREATE TABLE cùng rollback được. Cần xem quy tắc cụ thể của statement và engine.

### Bài 14. Oracle COMMIT trong procedure

Caller INSERT A, procedure INSERT B và COMMIT, caller ROLLBACK.

**Đáp án:** COMMIT thông thường trong procedure Oracle commit transaction session gồm cả A và B. Caller rollback sau đó không hoàn tác hai dòng đã commit.

### Bài 15. Autonomous transaction Oracle

Outer INSERT A, autonomous procedure INSERT B và COMMIT, outer ROLLBACK.

**Đáp án:** A rollback; B có thể còn vì được commit trong transaction tự trị. Đó không phải savepoint.

### Bài 16. Audit autonomous đã ghi DONE trước khi outer rollback

**Câu hỏi:** log DONE có phản ánh đúng nghiệp vụ không?

**Đáp án:** Không chắc. Outer có thể thất bại; log tự trị đã commit không đồng nghĩa transaction nghiệp vụ thành công. Cần thiết kế thông điệp audit hoặc outbox hợp lý.

### Bài 17. SQLite RELEASE trong outer transaction

```sql
BEGIN;
SAVEPOINT s;
UPDATE lesson344_sqlite_accounts
SET balance = balance + 1
WHERE account_id = 10;
RELEASE s;
ROLLBACK;
```

**Đáp án:** thay đổi vẫn rollback vì outer transaction chưa commit. `RELEASE` không phải commit độc lập.

### Bài 18. SQLite có CREATE PROCEDURE không?

**Đáp án:** SQLite core không có stored procedure SQL native như `CREATE PROCEDURE`/`CALL`; ứng dụng thường quản lý nhiều statement và transaction qua connection.

### Bài 19. Một request cần cập nhật ba bảng nguyên tử

**Câu hỏi:** nên để caller hay ba helper tự commit?

**Đáp án:** thường để caller sở hữu một transaction và các helper **không tự commit/rollback**, trừ khi nghiệp vụ cố ý dùng mô hình khác. Nhờ đó cả ba bảng cùng commit/rollback.

### Bài 20. Retry sau procedure commit từng phần

Procedure commit batch 1 và 2, lỗi ở batch 3. Người dùng gửi lại request.

**Đáp án:** không làm lại toàn bộ như thể chưa xử lý gì; cần đọc checkpoint và chạy idempotent/bỏ qua phần đã commit.

### Bài 21. Mất kết nối đúng lúc COMMIT

**Đáp án:** outcome có thể không rõ. Giữ cùng `request_key`, kiểm tra trạng thái và áp dụng idempotency, không tạo request key mới rồi thực hiện lặp.

### Bài 22. So sánh hai mô hình

| Mô hình | Điểm cần nhớ |
|---|---|
| Caller-owned | Một transaction bao các helper không commit |
| Procedure-owned batch | Nhiều commit, có khả năng thành công một phần |
| SQL Server nested counter | Inner commit không tự bền vững khi outer còn mở |
| MySQL START TRANSACTION trong proc | Có thể implicit commit transaction trước |
| Oracle autonomous | Commit độc lập với caller |
| SQLite savepoint | Rollback một phần, không tự là transaction riêng |

**Đáp án:** mỗi mô hình có một loại ranh giới khác nhau; không được dùng cùng một giả định “commit trong thủ tục chỉ commit thủ tục”.

### Bài 23. Công việc nào không nên đặt trong transaction dài?

**Đáp án:** gọi API mạng chậm, đợi người dùng nhập liệu hoặc sleep để retry; chúng kéo dài thời gian giữ khóa. Cần thiết kế boundary transaction ngắn nhưng vẫn bao trọn invariant.

### Bài 24. Outbox có gửi chính xác một lần tuyệt đối không?

**Đáp án:** Không tự động. Dispatcher có thể gửi rồi chết trước khi đánh dấu đã gửi; consumer cần idempotency/dedup.

## 30. Quy trình chọn ranh giới giao dịch khi thiết kế thủ tục

1. **Xác định invariant:** những dòng/bảng nào phải được commit cùng nhau?
2. **Chọn transaction owner:** caller hay procedure?
3. **Chọn DBMS/phiên bản:** nắm rõ quy tắc `CALL`, transaction control và DDL.
4. **Phân biệt block và transaction:** `BEGIN ... END` chưa chắc mở transaction.
5. **Định nghĩa API helper:** helper có commit/rollback hay chỉ ghi và raise?
6. **Xử lý transaction ngoài:** có thể gọi dưới JDBC/ORM `@Transactional` không?
7. **Thiết kế ngoại lệ:** khi lỗi thì ai rollback, có savepoint hay exception handler không?
8. **Tránh implicit commit ngoài ý muốn:** đặc biệt MySQL/Oracle DDL và thủ tục tự commit.
9. **Nếu commit theo batch:** ghi checkpoint và dữ liệu batch cùng transaction, có idempotency.
10. **Nếu tích hợp ngoài DB:** dùng outbox hoặc cơ chế idempotency, không phát tác dụng phụ trong vòng retry mù.
11. **Thử failure path:** lỗi trước commit, sau một commit, và mất kết nối ngay lúc commit.
12. **Viết rõ hợp đồng:** caller cần biết thủ tục có thể commit một phần hay không.

## 31. Bảng ghi nhớ nhanh

| Câu hỏi | Câu trả lời ngắn |
|---|---|
| Stored procedure có transaction riêng mặc định không? | **Không** |
| BEGIN khối PL/pgSQL/MySQL/PLSQL là BEGIN transaction? | Không |
| PostgreSQL function có COMMIT không? | Không |
| PostgreSQL procedure có COMMIT không? | Có khi `CALL`/`DO` đúng ngữ cảnh |
| PostgreSQL CALL trong explicit BEGIN có cho procedure COMMIT? | Không |
| PostgreSQL EXCEPTION block có cho COMMIT? | Không |
| PostgreSQL SECURITY DEFINER procedure có transaction control? | Không |
| SQL Server @@TRANCOUNT phản ánh gì? | Độ sâu BEGIN TRAN đang mở |
| SQL Server inner COMMIT có commit độc lập không? | Không khi outer còn hoạt động |
| SQL Server ROLLBACK không savepoint ảnh hưởng gì? | Thường rollback toàn transaction |
| SQL Server XACT_STATE() = -1? | Transaction uncommittable |
| MySQL START TRANSACTION trong proc có thể làm gì? | Implicit commit transaction đang mở |
| MySQL stored function/trigger tự transaction control? | Bị hạn chế/cấm |
| MySQL DDL trong transaction có thể implicit commit? | Có, nhiều trường hợp |
| Oracle COMMIT trong proc ảnh hưởng ai? | Transaction của session/caller thông thường |
| Oracle autonomous transaction là gì? | Giao dịch riêng có thể commit độc lập |
| SQLite có stored procedure SQL native không? | Không |
| SQLite RELEASE SAVEPOINT dưới outer transaction có commit độc lập không? | Không |
| Savepoint có thay commit không? | Không |
| Commit batch rồi lỗi batch sau có rollback batch trước không? | Không |
| Ranh giới retry transaction? | Bao gồm đọc, kiểm tra, ghi, commit |
| Lỗi kết nối lúc COMMIT? | Outcome có thể chưa rõ |
| Idempotency key giúp gì? | Nhận diện cùng request logic khi retry |
| Outbox giúp gì? | Ghi sự kiện trong transaction, phát sau commit |
| Thiết kế dễ tích hợp ORM? | Helper không tự commit; caller quản lý một transaction |

## 32. Kết luận

**Ranh giới giao dịch của thủ tục là hợp đồng về quyền kiểm soát commit và rollback, không chỉ là nơi đặt dấu `BEGIN`/`END`.** Cùng một từ khóa `COMMIT` có thể:

- Bị PostgreSQL từ chối vì thủ tục được gọi trong transaction block của caller.
- Chỉ giảm `@@TRANCOUNT` ở SQL Server mà chưa commit outer transaction.
- Kết thúc một transaction do MySQL procedure mở, sau khi `START TRANSACTION` có thể đã implicit commit transaction trước đó.
- Commit toàn bộ công việc chưa commit của session Oracle, bao gồm thay đổi của caller.
- Không áp dụng dưới dạng stored procedure SQL native ở SQLite.

Vì vậy, trước khi triển khai một procedure, hãy trả lời rõ:

> **Ai là transaction owner? Thủ tục có tự commit/rollback không? Nếu lỗi sau một lần commit, những phần nào đã lưu? Khi caller dùng transaction ngoài thì hành vi ra sao?**

Nếu nghiệp vụ cần **all-or-nothing** trên nhiều bảng, hãy ưu tiên hợp đồng caller-owned với các helper không tự kết thúc transaction, trừ khi hệ thống có lý do và cơ chế khác được thiết kế đầy đủ. Nếu muốn **commit từng batch**, hãy công khai khả năng thành công một phần, checkpoint, retry và idempotency.

Quan trọng nhất, **đừng chuyển thủ tục giữa các hệ quản trị mà giữ nguyên giả định về transaction boundary**. Những khác biệt này có thể thay đổi kết quả dữ liệu mà không cần thay đổi logic nghiệp vụ bề ngoài.

## Tài liệu tham khảo

- [PostgreSQL — Transaction Management in PL/pgSQL](https://www.postgresql.org/docs/current/plpgsql-transactions.html): transaction control trong `CALL`/`DO`, chuỗi gọi lồng nhau, cursor và khối `EXCEPTION`.
- [PostgreSQL — CREATE PROCEDURE](https://www.postgresql.org/docs/current/sql-createprocedure.html): `SECURITY DEFINER` và hạn chế transaction control khi procedure có `SET`.
- [PostgreSQL — CALL](https://www.postgresql.org/docs/current/sql-call.html): điều kiện gọi thủ tục và transaction control.
- [PostgreSQL — PL/pgSQL Errors and Messages](https://www.postgresql.org/docs/current/plpgsql-errors-and-messages.html): xử lý exception và thông báo lỗi.
- [Microsoft Learn — BEGIN TRANSACTION](https://learn.microsoft.com/en-us/sql/t-sql/language-elements/begin-transaction-transact-sql): nested transaction trong SQL Server.
- [Microsoft Learn — @@TRANCOUNT](https://learn.microsoft.com/en-us/sql/t-sql/functions/trancount-transact-sql): bộ đếm transaction của session.
- [Microsoft Learn — XACT_STATE](https://learn.microsoft.com/en-us/sql/t-sql/functions/xact-state-transact-sql): kiểm tra transaction có thể commit hay không.
- [Microsoft Learn — TRY...CATCH](https://learn.microsoft.com/en-us/sql/t-sql/language-elements/try-catch-transact-sql): xử lý lỗi và transaction trong T-SQL.
- [MySQL — START TRANSACTION, COMMIT, and ROLLBACK](https://dev.mysql.com/doc/refman/8.4/en/commit.html): transaction control, autocommit và nested transaction.
- [MySQL — Stored Program Restrictions](https://dev.mysql.com/doc/refman/8.4/en/stored-program-restrictions.html): hạn chế câu transaction control trong function/trigger.
- [MySQL — Statements That Cause an Implicit Commit](https://dev.mysql.com/doc/refman/8.4/en/implicit-commit.html): implicit commit của DDL và các statement đặc biệt.
- [Oracle Database — AUTONOMOUS_TRANSACTION Pragma](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/AUTONOMOUS_TRANSACTION-pragma.html): transaction tự trị và tương tác với caller.
- [Oracle Database — Transaction Processing and Control](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/transaction-processing-and-control.html): commit, rollback và savepoint trong PL/SQL.
- [SQLite — Transaction](https://www.sqlite.org/lang_transaction.html): `BEGIN`, `COMMIT` và `ROLLBACK`.
- [SQLite — SAVEPOINT](https://www.sqlite.org/lang_savepoint.html): `SAVEPOINT`, `RELEASE` và `ROLLBACK TO`.

