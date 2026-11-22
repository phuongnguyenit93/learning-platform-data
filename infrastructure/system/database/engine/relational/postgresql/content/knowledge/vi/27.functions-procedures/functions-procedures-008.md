# CALL và điều kiện được điều khiển giao dịch trong thủ tục PostgreSQL

Trong PostgreSQL, **procedure** (thủ tục) được gọi bằng lệnh `CALL`. Khác với function chạy trong câu `SELECT`, một procedure trong điều kiện thích hợp có thể dùng **`COMMIT`**, **`ROLLBACK`**, `COMMIT AND CHAIN` hoặc `ROLLBACK AND CHAIN` để kết thúc giao dịch trong lúc thực thi. Đây là tính năng hữu ích cho một số tác vụ như xử lý dữ liệu theo lô (*batch processing*), khi ta chủ ý không muốn giữ một giao dịch khổng lồ cho toàn bộ công việc.

Nhưng **khả năng điều khiển giao dịch không tự động có ở mọi lời gọi `CALL`**. Ví dụ:

~~~sql
-- Trường hợp có thể cho phép COMMIT trong procedure:
CALL my_batch_procedure();  -- CALL độc lập ở cấp cao nhất

-- Trường hợp KHÔNG cho phép procedure tự COMMIT:
BEGIN;
CALL my_batch_procedure();
COMMIT;
~~~

Nếu procedure thực thi `COMMIT` hoặc `ROLLBACK` trong trường hợp thứ hai, PostgreSQL sẽ báo lỗi như `invalid transaction termination`. Điều này thường làm lập trình viên bất ngờ: họ đã quen để ứng dụng Java/Spring mở transaction rồi gọi thủ tục, nhưng lại mong thủ tục được phép tự chia transaction thành nhiều phần.

Bài học thuộc chương **Hàm và thủ tục** của module **Database Engine Relational PostgreSQL**, tập trung vào câu hỏi: **khi nào `CALL` cho phép thủ tục điều khiển giao dịch, khi nào bị cấm, và phải thiết kế batch/ứng dụng ra sao để giữ đúng tính nhất quán?**

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt `CALL procedure(...)` với `SELECT function(...)`.
2. Tạo và gọi procedure bằng `CREATE PROCEDURE` và `CALL`.
3. Hiểu **ai sở hữu ranh giới transaction**: caller (ứng dụng) hay procedure.
4. Giải thích vì sao `CALL` ở cấp cao nhất có thể dùng transaction control, còn `CALL` nằm trong một explicit transaction block thì không.
5. Mô tả transaction mới được PostgreSQL tự bắt đầu sau mỗi `COMMIT` hoặc `ROLLBACK` bên trong procedure.
6. Dùng `COMMIT AND CHAIN`/`ROLLBACK AND CHAIN` khi cần tiếp nối đặc điểm giao dịch.
7. Nhận biết điều kiện của các chuỗi lời gọi lồng nhau `CALL → CALL` và việc một `SELECT function(...)` xen vào có thể chặn transaction control.
8. Giải thích hạn chế với procedure `SECURITY DEFINER` và procedure khai báo clause `SET`.
9. Không đặt `COMMIT`/`ROLLBACK` trong block PL/pgSQL có `EXCEPTION` handler.
10. Phân biệt exception subtransactions với giao dịch cấp cao nhất và hiểu giới hạn `SAVEPOINT` trong PL/pgSQL.
11. Phân tích tác động của commit trong cursor loop, holdable cursor và vòng lặp DML có `RETURNING`.
12. Thiết kế procedure batch theo lô với retry/idempotency và trạng thái partial completion.
13. Tích hợp đúng với JDBC `autoCommit` và Spring `@Transactional`.
14. Nhận diện những trường hợp nên để **ứng dụng** quản lý transaction thay vì cho procedure tự commit.
15. Chẩn đoán các lỗi giao dịch, lock, deadlock, trạng thái backend và câu lệnh DML nguy hiểm.

## 2. Nhắc lại giao dịch và tính nguyên tử

Giao dịch (*transaction*) là nhóm thao tác cơ sở dữ liệu có ranh giới commit/rollback. Một transaction thành công thì những thay đổi đã commit trở nên bền vững theo cơ chế PostgreSQL; nếu transaction chưa commit bị rollback, các thay đổi thuộc transaction đó không được ghi nhận như kết quả cuối.

~~~sql
BEGIN;

UPDATE wallets SET balance = balance - 100
WHERE wallet_id = 1;

UPDATE wallets SET balance = balance + 100
WHERE wallet_id = 2;

COMMIT;
~~~

Trong ví dụ chuyển tiền, **hai cập nhật phải thuộc cùng một transaction**. Không được cố “tối ưu batch” bằng cách thêm một `COMMIT` ở giữa phép trừ và phép cộng, vì khi đó một nửa giao dịch có thể tồn tại mà nửa kia thất bại.

### 2.1. Các lệnh transaction control phổ biến

| Lệnh | Tác dụng |
| --- | --- |
| `BEGIN` / `START TRANSACTION` | Mở explicit transaction block ở phía client/SQL |
| `COMMIT` | Kết thúc transaction, xác nhận thay đổi |
| `ROLLBACK` | Kết thúc transaction, hủy thay đổi chưa commit |
| `SAVEPOINT` | Đánh dấu một điểm để rollback một phần ở transaction do client quản lý |
| `ROLLBACK TO SAVEPOINT` | Quay lại savepoint trong cùng transaction |
| `COMMIT AND CHAIN` | Commit và tiếp tục transaction với một số đặc điểm transaction được giữ |
| `ROLLBACK AND CHAIN` | Rollback và tiếp tục transaction với những đặc điểm được giữ |

**Chú ý:** các lệnh có thể dùng ở tầng SQL phía client không có nghĩa tất cả đều sử dụng được bên trong một PL/pgSQL function/procedure.

### 2.2. Hai thiết kế transaction khác nhau

| Thiết kế | Ai quyết định kết thúc giao dịch? |
| --- | --- |
| **Caller-owned transaction** | Ứng dụng mở `BEGIN`, thực hiện một hoặc nhiều `CALL`/DML, rồi tự `COMMIT`/`ROLLBACK`. Procedure **không tự kết thúc giao dịch**. |
| **Procedure-owned transaction boundaries** | Client phát `CALL` độc lập, procedure tự `COMMIT` theo lô. Mỗi commit tạo một **mốc bền vững riêng**: rollback về sau không hủy các lô trước. |

Về SQL semantics, hai thiết kế khác nhau cả ở **atomicity**, cách retry, quan sát trạng thái lô và ứng xử khi có lỗi. Đừng chỉ chọn theo cú pháp nào thuận tiện.

### 2.3. Một CALL không có COMMIT bên trong vẫn là câu lệnh hợp lệ

~~~sql
BEGIN;
CALL update_one_order(101);
CALL update_another_order(102);
COMMIT;
~~~

Đây là cách gọi hợp lệ **nếu** các procedure trên không thực thi transaction control bị cấm. Bản thân từ khóa `CALL` **không bị cấm** trong `BEGIN...COMMIT`; điều bị hạn chế là procedure muốn **tự kết thúc transaction** ở trong bối cảnh đó.

## 3. Function và procedure không cùng transaction semantics

PostgreSQL hỗ trợ cả functions và procedures, nhưng có sự khác biệt quan trọng:

| Tiêu chí | Function | Procedure |
| --- | --- | --- |
| Tạo bằng | `CREATE FUNCTION` | `CREATE PROCEDURE` |
| Gọi từ SQL phổ biến | `SELECT my_func(...)`, có thể dùng trong biểu thức SQL | `CALL my_proc(...)` |
| Kiểu kết quả | Có return type, có thể trả scalar/row/set | Có thể có `OUT`/`INOUT` parameters theo cú pháp/phiên bản |
| Được sử dụng trong WHERE/SELECT expression | Có, tùy signature | Không phải SQL expression |
| Tự `COMMIT`/`ROLLBACK` | **Không** | **Có điều kiện nghiêm ngặt** |
| DML | Tùy ngôn ngữ/volatility/quyền và cách gọi | Có thể thực thi DML theo quyền |
| Quan hệ với transaction do ứng dụng mở | Chạy trong transaction của caller | Có thể chạy trong transaction của caller, nhưng không được tự commit nếu đang nằm trong explicit transaction block |

### 3.1. Function đơn giản

~~~sql
CREATE FUNCTION public.add_two_numbers(a integer, b integer)
RETURNS integer
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT a + b;
$$;

SELECT public.add_two_numbers(3, 5);  -- 8
~~~

Function là **biểu thức** có kiểu kết quả. `SELECT public.add_two_numbers(...)` không chuyển nó thành procedure chỉ vì function được viết bằng PL/pgSQL.

### 3.2. Procedure đơn giản

~~~sql
CREATE PROCEDURE public.print_greeting(p_name text)
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE 'Xin chào %', p_name;
END;
$$;

CALL public.print_greeting('An');
~~~

Lệnh `CALL` thực thi procedure; câu này không cần transaction control nên vẫn có thể được gọi trong một explicit transaction block.

### 3.3. Function không thể tự commit

~~~sql
-- Minh họa lỗi, KHÔNG dùng làm function hợp lệ để triển khai:
--
-- CREATE FUNCTION public.bad_commit()
-- RETURNS void
-- LANGUAGE plpgsql AS $$
-- BEGIN
--     COMMIT;  -- transaction control không hợp lệ cho function
-- END;
-- $$;
-- SELECT public.bad_commit();
~~~

Ngay cả khi function được gọi bên trong một procedure, việc **đi qua `SELECT function(...)`** có thể chặn transaction control ở procedure lồng sâu phía dưới, như phần chuỗi lời gọi sẽ giải thích.

### 3.4. Từ PostgreSQL 11

Tính năng SQL procedures và `CALL` được đưa vào PostgreSQL **11**. Trên các phiên bản PostgreSQL quá cũ, không thể áp dụng cú pháp procedure trong bài.

## 4. Cú pháp CREATE PROCEDURE và CALL

Mẫu cơ bản:

~~~sql
CREATE PROCEDURE schema_name.procedure_name(
    IN p_id bigint,
    IN p_label text
)
LANGUAGE plpgsql
AS $$
BEGIN
    -- các lệnh SQL, IF, LOOP ...
END;
$$;

CALL schema_name.procedure_name(1001, 'ready');
~~~

### 4.1. IN parameters

Tham số `IN` truyền giá trị từ client vào procedure. Nó là mode mặc định trong nhiều signature:

~~~sql
CREATE PROCEDURE public.report_status(p_status text)
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE 'status=%', p_status;
END;
$$;

CALL public.report_status('done');
~~~

### 4.2. INOUT parameters

`INOUT` dùng để nhận giá trị đầu vào và trả trạng thái sau khi procedure thực thi. Ví dụ:

~~~sql
CREATE PROCEDURE public.increment_counter(
    INOUT p_counter integer
)
LANGUAGE plpgsql
AS $$
BEGIN
    p_counter := p_counter + 1;
END;
$$;

CALL public.increment_counter(5);
~~~

Kết quả có thể được client nhận như một **hàng kết quả** chứa `p_counter=6`. Procedure không cần khai báo `RETURNS integer` như function.

### 4.3. OUT parameters và khác biệt phiên bản

Các PostgreSQL versions hiện đại hỗ trợ procedure output parameters, nhưng chi tiết cú pháp/cách truyền `OUT` đã thay đổi theo major version. Khi `CALL` có `OUT` parameter, client thường cần cung cấp một đối số placeholder (thường viết `NULL`) ở vị trí `OUT` theo cú pháp `CALL` của phiên bản đang dùng; đối số `OUT` không được đánh giá như input nghiệp vụ.

Ví dụ định hướng:

~~~sql
-- Đối chiếu với version PostgreSQL đang vận hành:
-- CREATE PROCEDURE public.read_counter(
--     IN p_input integer,
--     OUT p_output integer
-- )
-- LANGUAGE plpgsql AS $$
-- BEGIN
--     p_output := p_input + 1;
-- END;
-- $$;
-- CALL public.read_counter(5, NULL);
~~~

**Đừng suy ra CALL trả một giá trị SQL có thể dùng trực tiếp như biểu thức `SELECT fn(...)`.** Khi cần tổ hợp kết quả trong query SQL, function có return type thường phù hợp hơn.

### 4.4. Overloading và search_path

Procedure có thể được phân giải theo tên và kiểu tham số; nếu các schema hoặc overloads trùng tên, `search_path`/kiểu đối số có thể khiến PostgreSQL chọn signature khác. Trong ví dụ lab, luôn **schema-qualify** tên procedure và bảng để hạn chế nhầm lẫn.

### 4.5. CALL không đồng nghĩa “COMMIT”

~~~sql
CALL public.print_greeting('An');
~~~

Thao tác này chỉ gọi procedure. Nếu procedure không có transaction-control commands, lời gọi thực thi theo transaction context của client. **CALL không phải cú pháp rút gọn cho COMMIT.**

## 5. Điều kiện nền tảng để procedure tự kết thúc transaction

Quy tắc trung tâm:

> Procedure được gọi bằng **`CALL` ở cấp cao nhất** (hoặc trong một chuỗi các lời gọi `CALL`/`DO` hợp lệ, không có command xen giữa làm mất quyền transaction control) mới có thể `COMMIT`/`ROLLBACK`. Khi `CALL` được thực thi **bên trong một explicit transaction block**, procedure **không được phép** tự kết thúc transaction.

### 5.1. CALL độc lập

~~~sql
CALL proc_lab_349.commit_one('job-A');
~~~

Trong môi trường client như `psql` với autocommit thông thường và **không có explicit `BEGIN`**, transaction control của procedure có thể hợp lệ, nếu procedure còn đáp ứng các hạn chế khác như không có `SECURITY DEFINER`, không có procedure `SET` clause và không đặt `COMMIT` trong một block có `EXCEPTION` handler.

### 5.2. CALL trong explicit transaction

~~~sql
BEGIN;
CALL proc_lab_349.commit_one('job-B');
ROLLBACK;
~~~

Nếu `commit_one` thực thi `COMMIT` bên trong, PostgreSQL phát sinh lỗi do **procedure không có quyền kết thúc transaction mà client đã mở**. Sau lỗi, explicit transaction có thể chuyển sang trạng thái aborted; cần `ROLLBACK` để thoát, không tiếp tục thực hiện SQL bình thường trên cùng transaction đang lỗi.

### 5.3. Không phải chỉ cần client “không viết chữ BEGIN”

Một framework/driver có thể **mở explicit transaction thay bạn**, ví dụ JDBC `setAutoCommit(false)`, Spring `@Transactional` hoặc unit-of-work logic của ORM. Dù source application chỉ thấy `CALL`, bối cảnh thực thi vẫn có thể khiến internal `COMMIT` bị cấm.

### 5.4. CALL nested hợp lệ

~~~text
Top-level CALL parent_proc()
             |
             +-- CALL child_proc()
                          |
                          +-- CALL grandchild_proc()
~~~

Nếu chỉ có chuỗi lời gọi `CALL` (hoặc `DO`) được phép, những procedure phía trong **có thể thực hiện transaction control** theo quy tắc của PostgreSQL.

### 5.5. Command xen giữa làm mất quyền

~~~text
Top-level CALL parent_proc()
             |
             +-- SELECT helper_function()
                          |
                          +-- CALL nested_proc()
~~~

Trong ví dụ minh họa của tài liệu PostgreSQL, **`SELECT` xen giữa** làm cho procedure gọi sâu hơn **không còn được phép transaction control**, dù bên ngoài có một top-level `CALL`.

Điều cần nhớ là **call stack và command context**, không chỉ việc “procedure có được tạo đúng hay chưa”.

### 5.6. DO cũng có điều kiện tương tự

Một khối `DO` top-level có thể điều khiển giao dịch khi thỏa điều kiện được PostgreSQL cho phép; nhưng `DO` nằm trong explicit transaction block không được dùng `COMMIT`/`ROLLBACK` để thoát transaction của caller.

### 5.7. Điều kiện khác ngoài cấp lời gọi

Ngay cả với top-level `CALL`:

- Procedure `SECURITY DEFINER` **không** được thực thi transaction-control statements.
- Procedure được định nghĩa với clause `SET configuration_parameter ...` **không** được thực thi transaction-control statements.
- Không thể kết thúc transaction trong block PL/pgSQL có `EXCEPTION` handler đang hoạt động.
- Cursor loops và query drive bởi DML có thêm những giới hạn.

Những hạn chế này **độc lập** với việc client dùng autocommit.

## 6. Sơ đồ chọn người sở hữu transaction

~~~mermaid
flowchart TD
    A["Cần gọi procedure"] --> B{"Procedure có COMMIT/ROLLBACK nội bộ?"}
    B -->|Không| C["Caller quản lý transaction bình thường"]
    B -->|Có| D{"CALL thực sự ở top level, không trong BEGIN?"}
    D -->|Không| E["Sửa thiết kế: bỏ COMMIT nội bộ hoặc gọi ngoài transaction"]
    D -->|Có| F{"Call stack CALL/DO hợp lệ?"}
    F -->|Không| E
    F -->|Có| G{"SECURITY DEFINER / SET clause / EXCEPTION block?"}
    G -->|Có| H["Điều chỉnh thiết kế và ranh giới transaction"]
    G -->|Không| I["Có thể dùng transaction control có điều kiện"]
    I --> J["Đảm bảo partial commits, retry, idempotency và giám sát"]
~~~

Đây là sơ đồ quyết định **kiến trúc**, không phải một cách chạy tự động mọi statement. Cùng một procedure có thể hợp lệ trong môi trường `psql` và thất bại trong framework nếu transaction context khác.

## 7. Bộ dữ liệu lab để quan sát ranh giới COMMIT

Các ví dụ dưới đây tạo schema riêng `proc_lab_349` và ghi một số dòng để phân biệt phần đã commit với phần chưa commit. **Chỉ chạy trên database lab**, không chạy thử transaction-control commands trên bảng nghiệp vụ production.

### 7.1. Tạo schema và bảng nhật ký

~~~sql
CREATE SCHEMA proc_lab_349;

CREATE TABLE proc_lab_349.event_log (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_key text NOT NULL,
    phase text NOT NULL,
    recorded_at timestamptz NOT NULL
        DEFAULT clock_timestamp()
);

CREATE TABLE proc_lab_349.jobs (
    job_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_key text NOT NULL UNIQUE,
    state text NOT NULL
        CHECK (state IN ('pending', 'done')),
    processed_at timestamptz,
    last_note text
);
~~~

### 7.2. Tạo một số jobs

~~~sql
INSERT INTO proc_lab_349.jobs(job_key, state)
VALUES
    ('job-001', 'pending'),
    ('job-002', 'pending'),
    ('job-003', 'pending'),
    ('job-004', 'pending'),
    ('job-005', 'pending'),
    ('job-006', 'pending');

SELECT job_id, job_key, state
FROM proc_lab_349.jobs
ORDER BY job_id;
~~~

### 7.3. Thủ tục có hai commit points

~~~sql
CREATE PROCEDURE proc_lab_349.commit_two_phases(p_key text)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO proc_lab_349.event_log(event_key, phase)
    VALUES (p_key, 'phase-1');

    COMMIT;

    INSERT INTO proc_lab_349.event_log(event_key, phase)
    VALUES (p_key, 'phase-2');

    COMMIT;
END;
$$;
~~~

Thủ tục cố ý có **hai transactions** để minh họa:

~~~text
CALL bắt đầu
    |
    +-- INSERT phase-1
    +-- COMMIT             ← phase-1 đã được commit
    |
    +-- PostgreSQL tự bắt đầu transaction mới
    +-- INSERT phase-2
    +-- COMMIT             ← phase-2 đã được commit
    |
CALL kết thúc
~~~

### 7.4. Thực thi CALL độc lập

~~~sql
-- Chạy độc lập, KHÔNG đặt trong BEGIN ... COMMIT:
CALL proc_lab_349.commit_two_phases('case-top-level');

SELECT
    event_key,
    phase,
    recorded_at
FROM proc_lab_349.event_log
WHERE event_key = 'case-top-level'
ORDER BY event_id;
~~~

Kết quả về ngữ nghĩa là **hai hàng** `phase-1` và `phase-2`. Chúng đã được commit ở hai thời điểm riêng.

### 7.5. Đọc điểm commit bằng session khác

Nếu procedure tạm dừng giữa hai transaction (ví dụ một tác vụ công việc thực tế kéo dài), session khác có thể thấy `phase-1` **sau khi commit thứ nhất**, trong khi `phase-2` chưa xuất hiện. Đây là hệ quả **partial visibility**; những thay đổi đã commit không bị hoàn tác bởi lỗi ở transaction sau.

Không chèn `pg_sleep(...)` dài trên production chỉ để quan sát; môi trường lab và quyền truy cập phù hợp là đủ để học.

## 8. Explicit BEGIN làm transaction-control CALL thất bại

### 8.1. Ví dụ cố ý gây lỗi

~~~sql
BEGIN;

CALL proc_lab_349.commit_two_phases('case-inside-begin');

-- Nếu procedure cố COMMIT, transaction báo lỗi.
ROLLBACK;
~~~

Một thông báo thường gặp là:

~~~text
ERROR: invalid transaction termination
CONTEXT: PL/pgSQL function ... line ... at COMMIT
~~~

Nội dung `CONTEXT`/số dòng phụ thuộc server version và procedure definition.

### 8.2. Có mất dữ liệu chưa commit không?

Trong transaction explicit trên, `INSERT phase-1` đã chạy trước khi gặp `COMMIT` bị từ chối, nhưng transaction bị lỗi. Sau `ROLLBACK`:

~~~sql
SELECT *
FROM proc_lab_349.event_log
WHERE event_key = 'case-inside-begin';
~~~

Không có hai hàng được commit từ lượt gọi lỗi ấy. Đây là khác biệt lớn với việc top-level `CALL` cho phép commit thật.

### 8.3. Vì sao chỉ bỏ BEGIN có thể không đủ?

Nếu ứng dụng dùng JDBC với `autoCommit=false`, driver/framework vẫn có thể mở transaction. Bạn phải thay **bối cảnh giao dịch tại tầng caller**, không chỉ xóa câu `BEGIN` khỏi chuỗi SQL.

### 8.4. Đừng chạy COMMIT trên transaction đã aborted

Trong `psql` sau lỗi bên trong một explicit transaction block, prompt có thể báo trạng thái transaction lỗi. Hãy dùng `ROLLBACK` để kết thúc rõ ràng. Không cố thực thi các bước kế tiếp rồi kỳ vọng PostgreSQL bỏ qua lỗi ban đầu.

### 8.5. Không “sửa” bằng BEGIN bên trong procedure

Trong PL/pgSQL, `BEGIN ... END` là **khối cú pháp** của ngôn ngữ, **không** phải `BEGIN TRANSACTION` của SQL client.

~~~sql
CREATE PROCEDURE proc_lab_349.demo_block()
LANGUAGE plpgsql
AS $$
BEGIN                 -- bắt đầu PL/pgSQL block, KHÔNG mở transaction
    RAISE NOTICE 'ok';
END;                  -- kết thúc PL/pgSQL block
$$;
~~~

PostgreSQL sẽ tự bắt đầu transaction mới sau một `COMMIT`/`ROLLBACK` hợp lệ bên trong procedure. Không có một lệnh `START TRANSACTION` riêng cần gọi trong thân PL/pgSQL.

## 9. COMMIT trong procedure và transaction mới tự bắt đầu

Trong PL/pgSQL procedure, khi một `COMMIT` hợp lệ được thực thi:

1. Transaction hiện tại kết thúc và các thay đổi của nó được commit.
2. PostgreSQL **tự bắt đầu transaction mới** khi procedure tiếp tục chạy những câu lệnh sau.
3. Các thay đổi sau `COMMIT` thuộc transaction **mới**, không còn chung atomicity với phần trước.
4. Nếu một transaction sau bị rollback, các transaction trước đã commit **không bị hoàn tác**.

Điều này khác với một function được gọi từ `SELECT`, vốn không thể chia transaction của mình bằng `COMMIT`.

### 9.1. Biến PL/pgSQL không tự biến mất sau COMMIT

~~~sql
CREATE PROCEDURE proc_lab_349.count_phases()
LANGUAGE plpgsql
AS $$
DECLARE
    v_counter integer := 0;
BEGIN
    v_counter := v_counter + 1;
    COMMIT;

    v_counter := v_counter + 1;
    RAISE NOTICE 'counter=%', v_counter;
    COMMIT;
END;
$$;

-- CALL độc lập:
CALL proc_lab_349.count_phases();
~~~

`v_counter` là **biến trong frame thực thi procedure**, không phải một hàng dữ liệu đang được commit. Nó tiếp tục giữ giá trị giữa những transaction boundaries khi cùng invocation vẫn đang chạy.

Điều này **không** có nghĩa mọi thứ trong transaction cũ sống tiếp: row locks của transaction đã commit được giải phóng, trạng thái snapshots và các đặc tính transaction-level khác thay đổi theo transaction mới.

### 9.2. Temporary tables và session state

Một số đối tượng/trạng thái có vòng đời **session**, không phải chỉ một transaction. Nhưng cấu hình như `ON COMMIT DELETE ROWS` hoặc `ON COMMIT DROP` của temporary table có thể làm dữ liệu/bảng thay đổi ở mỗi `COMMIT` nội bộ.

Nếu procedure xử lý nhiều lô qua temp table, phải đọc rõ **`ON COMMIT` behavior** trước khi thêm transaction control.

### 9.3. Locks, snapshots, cursor

`COMMIT` thả các transaction-level locks và chấm dứt snapshot của transaction cũ. Một transaction mới có thể quan sát dữ liệu khác do các session khác vừa commit. Vì thế batch processing **không tự đảm bảo một snapshot nhất quán** cho toàn bộ khoảng thời gian chạy procedure.

Cursor loops là một ngoại lệ đáng chú ý vì có thể được chuyển thành holdable cursor; phần sau sẽ phân tích riêng.

## 10. ROLLBACK trong procedure: chỉ hủy transaction hiện tại

Tương tự `COMMIT`, một `ROLLBACK` hợp lệ bên trong top-level procedure:

- Hủy thay đổi **chưa commit** của transaction hiện tại;
- Không hủy dữ liệu đã commit ở các transaction trước;
- Cho phép procedure tiếp tục bằng transaction mới được PostgreSQL bắt đầu tự động.

### 10.1. Lab với một ROLLBACK giữa hai lần ghi

~~~sql
CREATE PROCEDURE proc_lab_349.rollback_middle(p_key text)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO proc_lab_349.event_log(event_key, phase)
    VALUES (p_key, 'before-rollback');

    ROLLBACK;

    INSERT INTO proc_lab_349.event_log(event_key, phase)
    VALUES (p_key, 'after-rollback');

    COMMIT;
END;
$$;

-- Chạy là một CALL độc lập:
CALL proc_lab_349.rollback_middle('case-rollback');

SELECT event_key, phase
FROM proc_lab_349.event_log
WHERE event_key = 'case-rollback'
ORDER BY event_id;
~~~

Kết quả logic: chỉ có `after-rollback`. `before-rollback` bị hủy bởi `ROLLBACK` nội bộ.

### 10.2. ROLLBACK không phải lệnh "bỏ qua lỗi rồi tiếp tục" tự động

Nếu một statement gây lỗi SQL thông thường, transaction bị đánh dấu lỗi và luồng thực thi procedure có thể bị dừng. Bạn không nên chờ procedure cứ chạy tới `ROLLBACK` tiếp theo để tự cứu. Muốn xử lý lỗi trong PL/pgSQL, cần hiểu **`EXCEPTION` blocks** và subtransaction semantics. Hãy thiết kế recovery theo logic rõ ràng, không dựa vào một `ROLLBACK` nằm sau statement có khả năng đã abort.

### 10.3. Không dùng ROLLBACK để làm "dry run" vô điều kiện

Một procedure có thể làm nhiều `COMMIT` trước khi tới `ROLLBACK`. Khi đó `ROLLBACK` cuối **không** hoàn tác được các commit trước. Nếu ứng dụng cần mô phỏng mà không thay đổi dữ liệu bền vững, nên dùng dữ liệu lab, bản sao hoặc thiết kế dry-run riêng — không giả định cuối procedure có `ROLLBACK` thì mọi thay đổi đều biến mất.

## 11. Một lỗi sau COMMIT không rollback được phần đã commit

Đây là tình huống cốt lõi khi lựa chọn có cho procedure tự điều khiển transaction hay không.

### 11.1. Procedure có lỗi có chủ ý

~~~sql
CREATE PROCEDURE proc_lab_349.fail_after_first_commit(p_key text)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO proc_lab_349.event_log(event_key, phase)
    VALUES (p_key, 'already-committed');

    COMMIT;

    INSERT INTO proc_lab_349.event_log(event_key, phase)
    VALUES (p_key, 'not-committed');

    RAISE EXCEPTION
        'Demo failure after first commit for %', p_key;
END;
$$;
~~~

### 11.2. Gọi ở top-level

~~~sql
-- Câu này CỐ Ý báo lỗi; chỉ chạy trên lab:
CALL proc_lab_349.fail_after_first_commit('case-partial');
~~~

Phần ghi `already-committed` đã hoàn tất transaction thứ nhất. Sau đó procedure ném exception trong transaction kế tiếp. Lệnh `CALL` sẽ báo lỗi cho client, nhưng **đó không có nghĩa toàn bộ lịch sử thay đổi đã bị hủy**.

Kiểm tra trong một câu SQL mới:

~~~sql
SELECT event_key, phase
FROM proc_lab_349.event_log
WHERE event_key = 'case-partial'
ORDER BY event_id;
~~~

**Kỳ vọng:** có `already-committed`, không có `not-committed`.

### 11.3. Hệ quả của atomicity bị chia

~~~text
CALL bắt đầu
   |
   +-- Transaction #1: INSERT A
   +-- COMMIT             ← A bền vững
   |
   +-- Transaction #2: INSERT B
   +-- RAISE EXCEPTION    ← B bị rollback
   |
Client nhận ERROR, nhưng A vẫn tồn tại.
~~~

**Một procedure trả ERROR không đồng nghĩa tất cả các transaction trước đó đều rollback.**

### 11.4. Vì sao retry toàn bộ có thể nguy hiểm?

Giả sử procedure gửi yêu cầu tạo hóa đơn, cập nhật số dư và ghi lịch sử qua nhiều commits. Nếu client thấy lỗi rồi retry mọi bước không kiểm tra trạng thái đã commit:

- Có thể ghi trùng log;
- Có thể xử lý lại một giao dịch tiền;
- Có thể gửi email/webhook lặp;
- Có thể gặp unique violation ở lần thứ hai;
- Có thể để trạng thái nửa hoàn thành khó khôi phục.

Thiết kế batch procedure cần **idempotency key, trạng thái bước đã hoàn tất, transaction boundaries có chủ đích** và chiến lược retry theo phần còn thiếu.

## 12. COMMIT AND CHAIN và ROLLBACK AND CHAIN

Trong transaction control của procedures, PostgreSQL hỗ trợ:

~~~sql
COMMIT AND CHAIN;
ROLLBACK AND CHAIN;
~~~

Mục tiêu là **tiếp tục với một transaction mới có đặc điểm giao dịch tương tự** transaction trước, chẳng hạn isolation level và các transaction characteristics được PostgreSQL hỗ trợ duy trì qua `AND CHAIN`.

### 12.1. So sánh với COMMIT thường

~~~text
COMMIT:
  Kết thúc transaction hiện tại.
  Procedure tiếp tục trong transaction mới theo cơ chế mặc định.

COMMIT AND CHAIN:
  Kết thúc transaction hiện tại.
  Tiếp nối một transaction mới, giữ transaction characteristics
  được hỗ trợ từ transaction vừa kết thúc.
~~~

Trong PL/pgSQL, cả hai cách đều có thể dùng ở vị trí hợp lệ của transaction-controlling procedure. `AND CHAIN` không biến một lời gọi bị cấm (ví dụ `CALL` trong `BEGIN`) thành hợp lệ.

### 12.2. Procedure minh họa AND CHAIN

~~~sql
CREATE PROCEDURE proc_lab_349.commit_chain_demo(p_key text)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO proc_lab_349.event_log(event_key, phase)
    VALUES (p_key, 'chain-first');

    COMMIT AND CHAIN;

    INSERT INTO proc_lab_349.event_log(event_key, phase)
    VALUES (p_key, 'chain-second');

    COMMIT;
END;
$$;

-- Phải gọi độc lập:
CALL proc_lab_349.commit_chain_demo('case-chain');
~~~

### 12.3. Khi nào cần?

Một thủ tục chạy nhiều giao dịch liên tiếp có yêu cầu về transaction characteristics nhất quán có thể dùng `AND CHAIN` thay vì để transaction sau trở về những đặc điểm mặc định không mong muốn.

**Không nên coi `AND CHAIN` là cách duy trì cùng một snapshot/MVCC view xuyên qua nhiều commits.** Mỗi transaction vẫn có ranh giới riêng và có thể quan sát changes của concurrent sessions tùy isolation level.

### 12.4. Không có START TRANSACTION riêng trong thân PL/pgSQL

~~~sql
-- Không phải mẫu đúng để "mở transaction mới" trong PL/pgSQL:
-- COMMIT;
-- START TRANSACTION;
~~~

Sau `COMMIT`/`ROLLBACK` hợp lệ, PostgreSQL bắt đầu transaction mới tự động khi tiếp tục. Không cần (và không dùng) `START TRANSACTION` ở trong thân PL/pgSQL procedure như cách client điều khiển transaction.

## 13. Lời gọi lồng nhau: CALL → CALL được, SELECT xen giữa có thể chặn

### 13.1. Tạo một procedure con có COMMIT

~~~sql
CREATE PROCEDURE proc_lab_349.child_commit(p_key text)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO proc_lab_349.event_log(event_key, phase)
    VALUES (p_key, 'child');

    COMMIT;
END;
$$;
~~~

### 13.2. Procedure cha gọi con trực tiếp bằng CALL

~~~sql
CREATE PROCEDURE proc_lab_349.parent_call(p_key text)
LANGUAGE plpgsql
AS $$
BEGIN
    CALL proc_lab_349.child_commit(p_key);
END;
$$;

-- CALL độc lập:
CALL proc_lab_349.parent_call('case-nested-call');
~~~

Khi call stack chỉ là `CALL parent_call() → CALL child_commit()` bắt đầu từ top-level, transaction control ở procedure con có thể hợp lệ.

### 13.3. Một function chen giữa

Ví dụ khái niệm:

~~~text
CALL parent_procedure()
  └── SELECT helper_function()
        └── CALL child_commit()
              └── COMMIT  → không hợp lệ trong call context này
~~~

Ngay cả khi function bên trong có thể gọi một procedure (theo cơ chế ngôn ngữ), việc **đường gọi đi qua một câu lệnh SELECT** là một giới hạn được mô tả rõ trong tài liệu PostgreSQL `PL/pgSQL Transaction Management`.

### 13.4. Không chỉ nhìn tên hàm/thủ tục

Khi thấy `invalid transaction termination` từ procedure con:

- Ai gọi procedure cha?
- Caller đã mở transaction chưa?
- Chuỗi lời gọi có qua `SELECT function(...)` hay command xen giữa không?
- Procedure con có `SECURITY DEFINER`/`SET` clause không?
- `COMMIT` nằm trong exception block hay cursor loop bị hạn chế không?

Thay đổi vị trí một lệnh `COMMIT` mà không hiểu call context có thể chỉ chuyển lỗi sang vị trí khác.

### 13.5. Chạy CALL từ application không bảo đảm "top-level"

Một ORM có thể bọc lời gọi bằng transaction hoặc qua function/helper. Vì thế phải kiểm tra **câu lệnh thực sự PostgreSQL nhận** và trạng thái transaction của session, không chỉ nhìn method Java tên `executeProcedure`.

## 14. Hạn chế SECURITY DEFINER

Một procedure tạo với:

~~~sql
CREATE PROCEDURE public.privileged_operation()
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RAISE NOTICE 'Run with definer privileges';
END;
$$;
~~~

chạy với đặc tính quyền của owner theo cơ chế `SECURITY DEFINER`. PostgreSQL **không cho procedure `SECURITY DEFINER` thực thi transaction-control statements**.

### 14.1. Không nên thêm SECURITY DEFINER vào procedure có COMMIT

~~~sql
-- Ý tưởng sai:
-- CREATE PROCEDURE public.bad_privileged_commit()
-- LANGUAGE plpgsql
-- SECURITY DEFINER
-- AS $$
-- BEGIN
--     COMMIT; -- không được phép
-- END;
-- $$;
~~~

Không thể "sửa" bằng cách đảm bảo client autocommit: **hạn chế SECURITY DEFINER vẫn còn**.

### 14.2. Quyền và transaction control là hai trục khác nhau

Nếu cần một nghiệp vụ có quyền cao **và** batch commits:

- Xem lại quyền bảng/role của **SECURITY INVOKER** procedure;
- Thiết kế một interface quyền rõ với transaction boundaries ở tầng caller;
- Cân nhắc việc tách phần công việc cần quyền đặc biệt khỏi phần điều phối batches;
- Không dùng quyền cao để vòng tránh restriction hoặc vô tình mở quyền rộng cho client.

### 14.3. SECURITY DEFINER cần search_path an toàn

Ngay cả những procedure không commit nhưng được khai báo `SECURITY DEFINER`, cần bảo đảm `search_path`/schema references và quyền EXECUTE an toàn, tránh object-name shadowing bởi schema không đáng tin. Bài này không thay thế một review đầy đủ về bảo mật definer rights.

## 15. Hạn chế clause SET trên CREATE PROCEDURE

PostgreSQL cho phép procedure có **`SET configuration_parameter ...` clause**:

~~~sql
CREATE PROCEDURE public.read_with_setting()
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    RAISE NOTICE 'A procedure with a SET clause';
END;
$$;
~~~

Nhưng **procedure có `SET` clause trong định nghĩa không được phép thực thi transaction-control statements**, dù được gọi độc lập ở cấp cao nhất.

### 15.1. Ví dụ cần tránh

~~~sql
-- Ý tưởng không hợp lệ khi muốn COMMIT nội bộ:
--
-- CREATE PROCEDURE public.bad_configured_commit()
-- LANGUAGE plpgsql
-- SET work_mem = '64MB'
-- AS $$
-- BEGIN
--     COMMIT;
-- END;
-- $$;
~~~

### 15.2. Phân biệt SET clause với SET LOCAL của caller

`CREATE PROCEDURE ... SET search_path ...` là **thuộc tính được khai báo trong definition**. `SET LOCAL ...` là lệnh thay đổi GUC trong transaction của session.

Đừng vội kết luận chúng đồng nhất: restriction được ghi cho **procedure đã gắn SET clause**. Việc dùng một statement `SET LOCAL` bên trong caller còn phụ thuộc transaction context, phạm vi hiệu lực và câu SQL cụ thể. Khi một procedure cần transaction control, nên schema-qualify các bảng/objects và quản lý cấu hình ở tầng phù hợp.

### 15.3. Không dùng SET clause như một cách “cố định ngữ cảnh” rồi thêm COMMIT

Nếu yêu cầu là transaction-level work_mem/timezone/search_path, xác định rõ ai sở hữu config và transaction, sau đó kiểm tra restriction. **Transaction boundaries không nên bị thay đổi ngầm** bởi một thủ thuật cấu hình.

## 16. EXCEPTION blocks: subtransaction không phải transaction độc lập

PL/pgSQL có hỗ trợ:

~~~sql
BEGIN
    -- statements
EXCEPTION
    WHEN unique_violation THEN
        -- xử lý lỗi
END;
~~~

Block có `EXCEPTION` được vận hành với cơ chế **subtransaction** để có thể hủy các thay đổi trong block khi exception xảy ra và tiếp tục ở handler.

**Bạn không được kết thúc transaction bằng `COMMIT`/`ROLLBACK` khi đang ở trong block có exception handler như vậy.**

### 16.1. Mẫu sai: COMMIT trong EXCEPTION block

~~~sql
-- Không dùng làm procedure hợp lệ để commit:
--
-- CREATE PROCEDURE proc_lab_349.bad_exception_commit()
-- LANGUAGE plpgsql
-- AS $$
-- BEGIN
--     BEGIN
--         INSERT INTO proc_lab_349.event_log(event_key, phase)
--         VALUES ('bad', 'before');
--         COMMIT;    -- không được phép trong block có EXCEPTION
--     EXCEPTION WHEN OTHERS THEN
--         RAISE NOTICE 'error';
--     END;
-- END;
-- $$;
~~~

### 16.2. Mẫu đúng: kết thúc EXCEPTION block trước COMMIT

~~~sql
CREATE PROCEDURE proc_lab_349.exception_then_commit(p_key text)
LANGUAGE plpgsql
AS $$
BEGIN
    BEGIN
        INSERT INTO proc_lab_349.event_log(event_key, phase)
        VALUES (p_key, 'attempted');
    EXCEPTION WHEN unique_violation THEN
        RAISE NOTICE 'Duplicate key in protected operation';
    END;

    -- Đã RA KHỎI block có EXCEPTION handler.
    COMMIT;
END;
$$;

-- CALL độc lập:
CALL proc_lab_349.exception_then_commit('case-exception');
~~~

Trong ví dụ này, phần bắt lỗi đã kết thúc trước `COMMIT`. Nếu handler chạy, những thay đổi của block lỗi được rollback ở **subtransaction của block**, còn transaction bên ngoài vẫn có thể tiếp tục.

### 16.3. Điều gì được rollback khi EXCEPTION xảy ra?

Khi một statement trong block lỗi và được handler bắt:

- Các thay đổi dữ liệu persistent thực hiện **trong block lỗi** được rollback tới trạng thái khi block bắt đầu;
- Các biến PL/pgSQL có thể giữ giá trị đã gán trước lỗi theo ngữ nghĩa exception handling;
- Những thay đổi đã commit từ transaction trước **không** bị rollback.

Vì vậy **EXCEPTION handler không thay thế transaction-level ROLLBACK** và không thể biến các batch commits trước đó thành atomic transaction.

### 16.4. Không dùng WHEN OTHERS để nuốt mọi lỗi

~~~sql
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'ignored';
~~~

có thể khiến ứng dụng tưởng đã xử lý thành công, trong khi lỗi database quan trọng bị che đi. Chỉ bắt những mã lỗi được phép phục hồi, ghi log đủ ngữ cảnh, và `RAISE` trở lại khi không thể bảo đảm tính đúng.

### 16.5. SAVEPOINT trong PL/pgSQL

PostgreSQL PL/pgSQL **không hỗ trợ trực tiếp `SAVEPOINT` / `ROLLBACK TO SAVEPOINT` / `RELEASE SAVEPOINT`** như một cách lập trình thủ tục thông thường. Khi cần phục hồi một phần trong block, **`BEGIN ... EXCEPTION ... END`** là cơ chế PL/pgSQL tương ứng, với hạn chế không commit/rollback transaction trong exception-handling block.

Ở tầng caller, một explicit transaction có thể dùng savepoints theo SQL bình thường; điều này không làm procedure được quyền tự `COMMIT` trong transaction ấy.

## 17. Vòng lặp cursor và COMMIT: hiệu ứng holdable cursor

Một procedure đôi khi duyệt kết quả của một `SELECT`:

~~~sql
CREATE PROCEDURE proc_lab_349.cursor_loop_demo()
LANGUAGE plpgsql
AS $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT job_id, job_key
        FROM proc_lab_349.jobs
        ORDER BY job_id
    LOOP
        RAISE NOTICE 'job=%', r.job_key;
        COMMIT;
    END LOOP;
END;
$$;
~~~

Với transaction-control procedure được gọi đúng bối cảnh, PostgreSQL có thể cho phép `COMMIT` trong **cursor loop driven by a read-only SELECT**. Nhưng có một hệ quả rất quan trọng.

### 17.1. Cursor được chuyển thành holdable ở COMMIT đầu tiên

Khi procedure `COMMIT`/`ROLLBACK` trong vòng lặp cursor, cursor thường được chuyển thành **holdable cursor** tại lần kết thúc transaction đầu tiên. PostgreSQL phải **đánh giá và materialize đầy đủ các hàng còn lại của query** ở thời điểm đó.

Như vậy:

- Vòng lặp không còn stream và lock rows theo cách có thể bạn kỳ vọng ban đầu;
- Một result set lớn có thể tiêu tốn nhiều RAM/temp storage;
- Locks do cursor query giữ không còn duy trì sau commit như trước;
- Dữ liệu duyệt có thể là tập đã materialize ở thời điểm commit đầu, không phản ánh các transaction sau.

### 17.2. Vì sao cursor loop commit mỗi hàng không luôn tốt?

Nếu có 10 triệu dòng, việc materialize kết quả ở lần commit đầu có thể nặng và gây temp spill. Commit mỗi row còn tăng WAL/transaction overhead. Thường nên dùng **batching theo khóa/limit** thay vì stream một cursor khổng lồ rồi commit mỗi hàng.

### 17.3. Giới hạn với cursor loop dựa trên DML

PostgreSQL **không cho phép transaction commands trong cursor loops được điều khiển bởi command không read-only**, ví dụ `UPDATE ... RETURNING`.

~~~sql
-- Ý tưởng không hợp lệ:
-- FOR r IN UPDATE ... RETURNING ... LOOP
--     COMMIT;   -- transaction control bị hạn chế
-- END LOOP;
~~~

### 17.4. Bẫy vòng lặp SELECT FOR UPDATE

Kể cả khi phần ngoài trông như SELECT, dùng `FOR UPDATE` và commit trong loop không tự bảo đảm rows tiếp theo vẫn được khóa xuyên transaction. Hãy thiết kế thuật toán **claim jobs theo batch** rồi xử lý trước commit; đừng dựa vào cursor/locks còn tồn tại như cũ sau commit.

### 17.5. Query SELECT read-only vs thuật toán phân lô an toàn

Với hàng triệu jobs, một chiến lược rõ ràng hơn là:

1. Chọn tối đa `N` jobs chưa xử lý trong transaction hiện tại;
2. Khóa/đánh dấu chúng theo quy tắc concurrency;
3. Cập nhật trạng thái và ghi kết quả;
4. `COMMIT`;
5. Lặp lại bằng truy vấn mới, không giữ cursor lớn xuyên nhiều transactions.

Phần sau xây một procedure cụ thể cho kiểu này.

## 18. Batch processing: COMMIT sau từng nhóm công việc

Một lý do hợp lý để procedure tự điều khiển transaction là xử lý một lượng lớn jobs mà không muốn giữ locks/WAL/transaction snapshot trong một giao dịch cực dài.

Nhưng chia thành nhiều transaction làm thay đổi **tính nguyên tử của toàn bộ công việc**. Nếu procedure đã xử lý 300 jobs, rồi lỗi ở job 301, thì 300 jobs đã commit không tự quay về trạng thái pending.

### 18.1. Mẫu thuật toán mong muốn

~~~text
CALL process_pending_jobs(2)
    |
    +-- Batch 1: chọn tối đa 2 jobs pending
    |      UPDATE trạng thái → COMMIT
    |
    +-- Batch 2: chọn tối đa 2 jobs pending
    |      UPDATE trạng thái → COMMIT
    |
    +-- Batch 3: chọn tối đa 2 jobs pending
    |      UPDATE trạng thái → COMMIT
    |
    +-- Kiểm tra: không còn jobs pending đang có thể claim
           → kết thúc
~~~

### 18.2. Procedure xử lý jobs theo lô

~~~sql
CREATE PROCEDURE proc_lab_349.process_pending_jobs(
    p_batch_size integer
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_batch_rows integer;
    v_total_rows bigint := 0;
    v_batch_number integer := 0;
BEGIN
    IF p_batch_size IS NULL OR p_batch_size < 1
       OR p_batch_size > 1000 THEN
        RAISE EXCEPTION
            'batch size must be between 1 and 1000';
    END IF;

    LOOP
        WITH next_jobs AS (
            SELECT j.job_id
            FROM proc_lab_349.jobs AS j
            WHERE j.state = 'pending'
            ORDER BY j.job_id
            LIMIT p_batch_size
            FOR UPDATE SKIP LOCKED
        )
        UPDATE proc_lab_349.jobs AS j
        SET state = 'done',
            processed_at = clock_timestamp(),
            last_note = 'Processed in batch'
        FROM next_jobs AS n
        WHERE j.job_id = n.job_id;

        GET DIAGNOSTICS v_batch_rows = ROW_COUNT;

        EXIT WHEN v_batch_rows = 0;

        v_batch_number := v_batch_number + 1;
        v_total_rows := v_total_rows + v_batch_rows;

        INSERT INTO proc_lab_349.event_log(event_key, phase)
        VALUES (
            format('batch-%s', v_batch_number),
            format('updated=%s', v_batch_rows)
        );

        COMMIT;

        RAISE NOTICE
            'Committed batch %, rows=%, total=%',
            v_batch_number, v_batch_rows, v_total_rows;
    END LOOP;
END;
$$;
~~~

Đây là ví dụ cho **các bước thuần database** trên cùng bảng. Nó không gọi dịch vụ ngoài hay giả định mọi tác vụ có thể được xử lý một cách an toàn chỉ bằng một UPDATE.

### 18.3. Chạy CALL ở cấp cao nhất

~~~sql
-- Không dùng BEGIN ... CALL ... COMMIT:
CALL proc_lab_349.process_pending_jobs(2);

SELECT
    state,
    COUNT(*) AS job_count
FROM proc_lab_349.jobs
GROUP BY state
ORDER BY state;
~~~

Với sáu jobs ban đầu đều `pending` và không có worker nào khác cạnh tranh, kết quả mong đợi là **6 jobs `done`**. Procedure dự kiến commit ba batches, mỗi batch tối đa hai jobs.

### 18.4. Vì sao dùng GET DIAGNOSTICS ROW_COUNT?

~~~sql
GET DIAGNOSTICS v_batch_rows = ROW_COUNT;
~~~

Lấy số rows bị tác động bởi statement SQL gần nhất (ở đây là UPDATE). Dựa vào số thực tế này thay vì giả định cứ `LIMIT 2` là luôn update đủ 2 rows: concurrency và số jobs còn lại có thể làm kết quả ít hơn.

### 18.5. Vì sao dùng SKIP LOCKED?

~~~sql
FOR UPDATE SKIP LOCKED
~~~

giúp một worker chọn các rows **chưa bị transaction khác khóa** mà không phải chờ từng row lock của đối thủ. Nó thường hữu ích cho kiểu work queue có nhiều workers, nhưng **cho một cái nhìn không nhất quán tạm thời**: có rows còn pending nhưng đang bị worker khác lock nên bị bỏ qua.

Vì vậy nếu một lượt SELECT trả 0 jobs trong khi có workers khác đang xử lý, **không chứng minh toàn hệ thống hết jobs**. Hãy có retry/reconciliation hoặc scheduler gọi lại khi cần.

### 18.6. COMMIT giải phóng locks

Ngay sau mỗi `COMMIT`:

- Các row locks của batch đó được giải phóng;
- Những updates đã commit có thể được các transactions khác quan sát;
- Transaction mới bắt đầu khi vòng lặp tiếp tục;
- Procedure giữ các biến `v_total_rows`/`v_batch_number` như state của invocation.

### 18.7. Ranh giới idempotency trong lab

Điều kiện:

~~~sql
WHERE j.state = 'pending'
~~~

giúp một lần `CALL` sau không update lại những jobs đã `done`. Đây là một dạng **idempotent database state transition** cho lab.

Nhưng nếu real job có side effect bên ngoài (gửi email, thanh toán, ghi external API), chỉ cập nhật `state='done'` không đủ đảm bảo *exactly once*. Cần idempotency key, outbox/inbox, retry semantics và transaction boundary rõ.

### 18.8. Hiểm họa commit sau mỗi row

Nếu p_batch_size=1 trên một triệu jobs:

- Có thể phát sinh một triệu commits;
- Commit/WAL flush overhead tăng lớn;
- Worker queue scheduling/locking lặp nhiều;
- Quan sát giữa các transaction trở nên phức tạp;
- Resume dễ nhưng throughput có thể kém.

Batch size nên được đo theo thời gian giao dịch, row lock contention, WAL, memory, latency và yêu cầu phục hồi, **không chọn 1 hay 1000 như công thức chung**.

### 18.9. Nếu cần all-or-nothing, không dùng batch COMMIT

Ví dụ chuyển tiền hoặc cập nhật nhiều bảng phải đồng bộ:

~~~sql
BEGIN;
CALL proc_lab_349.atomic_work_no_internal_commit(...);
COMMIT;
~~~

Đây chỉ là mẫu định hướng: thực tế cần một procedure **không có COMMIT/ROLLBACK nội bộ** và bảo toàn tất cả invariants. Không thay batch commits bằng cách cố rollback ở cuối nếu đã commit các lô trước đó.

## 19. Viết procedure atomic và để caller quyết định COMMIT

Để minh họa thiết kế đối lập, viết procedure chỉ cập nhật một job và log, **không** tự kết thúc transaction:

~~~sql
CREATE PROCEDURE proc_lab_349.complete_job_atomic(
    p_job_key text
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_updated integer;
BEGIN
    UPDATE proc_lab_349.jobs
    SET state = 'done',
        processed_at = clock_timestamp(),
        last_note = 'Completed atomically'
    WHERE job_key = p_job_key
      AND state = 'pending';

    GET DIAGNOSTICS v_updated = ROW_COUNT;

    IF v_updated <> 1 THEN
        RAISE EXCEPTION
            'Job % not found or not pending', p_job_key;
    END IF;

    INSERT INTO proc_lab_349.event_log(event_key, phase)
    VALUES (p_job_key, 'complete-job');
END;
$$;
~~~

### 19.1. Dùng trong explicit transaction

~~~sql
-- Trước khi chạy, cần có job mới pending trong lab.
INSERT INTO proc_lab_349.jobs(job_key, state)
VALUES ('job-atomic-1', 'pending');

BEGIN;
CALL proc_lab_349.complete_job_atomic('job-atomic-1');
COMMIT;
~~~

Hai thay đổi UPDATE và INSERT thuộc **một transaction do caller sở hữu**. Nếu INSERT log lỗi và transaction bị rollback, UPDATE job không bị commit một mình.

### 19.2. ROLLBACK ở caller

~~~sql
INSERT INTO proc_lab_349.jobs(job_key, state)
VALUES ('job-atomic-2', 'pending');

BEGIN;
CALL proc_lab_349.complete_job_atomic('job-atomic-2');
ROLLBACK;

SELECT job_key, state
FROM proc_lab_349.jobs
WHERE job_key = 'job-atomic-2';
~~~

Kết quả `job-atomic-2` vẫn `pending`, vì UPDATE đã nằm trong transaction bị caller rollback.

### 19.3. Vì sao thiết kế này thường phù hợp với request HTTP?

Một HTTP request có thể phải cập nhật đơn hàng, kho, thanh toán nội bộ và audit log như **một đơn vị**. Framework có thể mở transaction và rollback khi một bước lỗi. Procedure không có internal `COMMIT` tương thích với cách quản lý giao dịch ấy.

### 19.4. Quyền sở hữu transaction phải được ghi trong interface

Ví dụ API:

~~~text
complete_job_atomic(job_key)
  - Không commit/rollback nội bộ.
  - Caller chịu trách nhiệm transaction.
  - Có thể dùng trong @Transactional.

process_pending_jobs(batch_size)
  - Tự commit sau mỗi batch.
  - Phải được CALL độc lập, không trong transaction của caller.
  - Có thể hoàn thành một phần khi lỗi.
  - Phải được gọi lại/reconcile an toàn.
~~~

Hai thủ tục nên có tên/tài liệu thể hiện khác biệt. Không để developer phát hiện giữa production outage rằng một procedure tự commit còn procedure khác thì không.

## 20. Điều phối transaction: ai có quyền thay đổi ranh giới?

Một API có thể được thiết kế theo hai kiểu:

### 20.1. Kiểu A — Caller-controlled

~~~text
BEGIN (caller)
    |
    +-- CALL step_1_no_commit()
    +-- CALL step_2_no_commit()
    +-- INSERT audit
    |
COMMIT (caller)
~~~

Ưu điểm: atomicity của cả chuỗi, caller có thể phối hợp nhiều lệnh. Nhược điểm: transaction dài có thể giữ locks/snapshot lâu, tăng contention và cản VACUUM.

### 20.2. Kiểu B — Procedure-controlled

~~~text
CALL process_batch()
    |
    +-- DML batch 1 → COMMIT
    +-- DML batch 2 → COMMIT
    +-- DML batch 3 → COMMIT
~~~

Ưu điểm: mỗi batch ngắn, locks được giải phóng từng đợt, có checkpoint tiến độ. Nhược điểm: mất all-or-nothing, partial success, retry/reconciliation phức tạp.

### 20.3. Nguyên tắc lựa chọn

**Dữ liệu bất biến/kinh doanh trước, hiệu năng sau.** Không chia transaction chỉ vì có thể làm như vậy, nếu logic yêu cầu cập nhật đồng bộ toàn bộ các bảng.

### 20.4. Không gọi cả hai kiểu trong một explicit transaction mà kỳ vọng giống nhau

~~~sql
BEGIN;
CALL proc_lab_349.complete_job_atomic('job-atomic-1');
CALL proc_lab_349.process_pending_jobs(2);
COMMIT;
~~~

Mẫu này không hợp lệ nếu `process_pending_jobs` thực sự tới `COMMIT` bên trong. Khi có explicit transaction, batch procedure sẽ không được quyền kết thúc nó. Cần thiết kế điều phối khác, không cố “bắt” procedure con vượt quyền caller.

## 21. JDBC: autoCommit và lệnh CALL

Trong JDBC, thuộc tính `Connection.getAutoCommit()` quyết định cách driver xử lý transaction ở phía client. **Một procedure có internal COMMIT cần được gọi trong ngữ cảnh không bị ứng dụng đặt trong explicit transaction block.**

### 21.1. Mẫu phù hợp khi procedure tự commit

~~~java
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class BatchProcedureCaller {
    private final DataSource dataSource;

    public BatchProcedureCaller(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void runBatch(int batchSize) throws SQLException {
        try (Connection conn = dataSource.getConnection()) {
            conn.setAutoCommit(true);

            try (CallableStatement call = conn.prepareCall(
                    "CALL proc_lab_349.process_pending_jobs(?)")) {
                call.setInt(1, batchSize);
                call.execute();
            }
        }
    }
}
~~~

Trong kết nối mới sử dụng `autoCommit=true` và không có transaction wrapper khác, một top-level `CALL` cho phép procedure quyết định commit nếu đáp ứng mọi hạn chế khác.

**Lưu ý driver/framework:** các wrapper như ORM transaction manager, proxies, session settings hoặc middleware có thể tạo bối cảnh khác. Vì vậy cần thử nghiệm thực tế bằng chính **JDBC driver version** và datasource config được triển khai.

### 21.2. Mẫu gây lỗi

~~~java
try (Connection conn = dataSource.getConnection()) {
    conn.setAutoCommit(false);

    try (CallableStatement call = conn.prepareCall(
            "CALL proc_lab_349.process_pending_jobs(?)")) {
        call.setInt(1, 2);
        call.execute();  // Có thể lỗi invalid transaction termination.
    }

    conn.commit();
}
~~~

`autoCommit=false` nghĩa caller kiểm soát transaction. Trên PostgreSQL, thủ tục không được dùng `COMMIT`/`ROLLBACK` nội bộ khi gọi trong explicit transaction context đó.

### 21.3. Mẫu phù hợp cho procedure atomic

~~~java
try (Connection conn = dataSource.getConnection()) {
    conn.setAutoCommit(false);

    try {
        try (CallableStatement call = conn.prepareCall(
                "CALL proc_lab_349.complete_job_atomic(?)")) {
            call.setString(1, "job-atomic-3");
            call.execute();
        }

        // Có thể gọi thêm các câu SQL cùng transaction.
        conn.commit();
    } catch (SQLException e) {
        conn.rollback();
        throw e;
    }
}
~~~

Vì `complete_job_atomic` không commit bên trong, caller có thể quyết định commit/rollback sau khi tất cả các bước hoàn tất. Ví dụ giả định đã có `job-atomic-3` ở trạng thái pending.

### 21.4. Đừng sửa lỗi bằng cách gọi conn.commit() sau khi CALL bị lỗi

Nếu internal `COMMIT` báo lỗi và transaction đã ở trạng thái aborted, gọi `conn.commit()` không làm cho procedure tự hoàn tất các bước còn lại. Cần rollback transaction, tìm transaction ownership mismatch rồi đổi thiết kế.

### 21.5. Khôi phục connection state

Khi code dùng connection pool, thay `autoCommit`/isolation/readOnly/schema/GUC phải tuân thủ contract của pool. Đừng thay trạng thái trên một connection đang được framework sở hữu rồi trả về pool mà không bảo đảm reset. Một số framework giữ state ở proxy hoặc mở transaction tự động ngay cả khi code không gọi `BEGIN` trực tiếp.

### 21.6. Một API method có thể đã mở transaction từ tầng trên

Ngay cả nếu code trong method:

~~~java
callableStatement.execute();
~~~

không thấy câu `BEGIN` nào, nó có thể đang chạy bên trong transaction được mở bởi service method khác hoặc transaction interceptor. Cần trace call path từ HTTP/controller đến datasource, không chỉ nhìn câu SQL.

## 22. Spring @Transactional và CALL tự COMMIT

Trong Spring, `@Transactional` thông thường khiến transaction manager mở transaction cho method được bao:

~~~java
@Transactional
public void processJobsInOneRequest() {
    jdbcTemplate.update(
        "CALL proc_lab_349.process_pending_jobs(?)",
        2
    );
}
~~~

Đoạn code minh họa này **không phù hợp** với một procedure thực thi `COMMIT` nội bộ, vì lời gọi nằm trong transaction do Spring quản lý.

### 22.1. Hai hướng xử lý

**Hướng A — Caller sở hữu transaction:** dùng procedure **không có `COMMIT`** bên trong, rồi gọi trong `@Transactional`.

**Hướng B — Procedure sở hữu transaction boundaries:** gọi `CALL` độc lập qua một connection **không tham gia transaction hiện tại** và được cấu hình phù hợp. Một số codebases dùng service boundary không transaction hoặc propagation phù hợp, nhưng phải hiểu transaction manager và datasource cụ thể.

### 22.2. Không dùng @Transactional(propagation=...) như một mẹo mù

Các propagation values như `NOT_SUPPORTED` hoặc `REQUIRES_NEW` có ngữ nghĩa khác nhau:

- `REQUIRES_NEW` thường **mở transaction mới**, điều này vẫn không phù hợp với internal `COMMIT`.
- `NOT_SUPPORTED` có thể tạm không tham gia transaction đang tồn tại, nhưng cần xác nhận connection/driver thực sự gửi top-level `CALL` trong autocommit context.

Chọn propagation dựa trên **hợp đồng transaction của procedure**, không đoán từ tên enum.

### 22.3. Self-invocation và proxy boundaries

Với Spring proxy-based transaction management, lời gọi một method `@Transactional` từ **chính cùng object** có thể không đi qua interceptor như bạn kỳ vọng. Đây là một nguồn khác biệt giữa test và production. Khi điều tra `invalid transaction termination`, kiểm tra transaction state thực tế, không chỉ annotation.

### 22.4. Nguyên tắc API

Một service method chuyên gọi procedure tự commit nên:

- Có mục đích batch độc lập, không nằm giữa một workflow ACID nhiều bước;
- Không mở transaction ở tầng ngoài;
- Dùng datasource/connection semantics đã được kiểm chứng;
- Bắt lỗi và trả trạng thái **có thể hoàn thành một phần**;
- Có cơ chế kiểm tra tiến độ trước khi retry;
- Không giả định exception từ `CALL` nghĩa chưa có gì được commit.

## 23. psql, autocommit và cách thực hành

`psql` mặc định thường bật autocommit: mỗi câu SQL độc lập không nằm trong explicit `BEGIN` được xử lý theo transaction context do PostgreSQL/psql xác lập. Khi top-level `CALL` được gửi như một statement độc lập, procedure có thể tự commit.

### 23.1. Kiểm tra autocommit trong psql

~~~text
\echo :AUTOCOMMIT
~~~

Nếu cần thực hành một procedure có internal `COMMIT`, bảo đảm `psql` đang ở chế độ autocommit thích hợp và không nằm trong một explicit transaction block.

~~~text
\set AUTOCOMMIT on
~~~

Hai dòng bắt đầu bằng backslash là **psql meta-commands**, không phải SQL chuẩn để chạy từ JDBC hoặc một SQL client bất kỳ.

### 23.2. Một script BEGIN ... CALL sẽ không phù hợp

~~~sql
BEGIN;
CALL proc_lab_349.process_pending_jobs(2);
COMMIT;
~~~

Nếu procedure đi tới transaction-control command, lệnh sẽ lỗi. Một số migration/ETL runners tự **wrap toàn script trong transaction**, nên cần tách job batch thành step phù hợp hoặc đổi procedure sang kiểu caller-controlled.

### 23.3. Khi gọi nhiều lệnh CALL

~~~sql
CALL proc_lab_349.commit_two_phases('first');
CALL proc_lab_349.commit_two_phases('second');
~~~

Hai lệnh này là **hai top-level statements độc lập**, mỗi procedure còn có thể chia nhiều transaction bên trong. Không được suy ra cả hai CALL là một transaction chỉ vì cùng nằm trong một file .sql.

### 23.4. JDBC và psql khác nhau về transaction wrappers

Một phép thử thành công ở `psql` không chứng minh code Spring/JDBC cũng thành công, nếu code ấy đã tham gia transaction. Hãy test bằng cùng driver, pool, framework và cấu hình production-like.

## 24. Transaction isolation và tính nhất quán giữa các batch

Transaction isolation của PostgreSQL quy định một transaction được nhìn thấy những thay đổi nào từ các transactions khác. Khi procedure tự commit nhiều lần, **mỗi batch là transaction khác nhau**.

### 24.1. READ COMMITTED

Ở isolation `READ COMMITTED` (mặc định trong nhiều hệ thống PostgreSQL), mỗi statement có thể nhìn snapshot phù hợp theo thời điểm statement. Nếu procedure:

1. Query những jobs đang pending;
2. Commit batch;
3. Query những jobs pending lần nữa;

thì batch thứ hai có thể thấy các jobs mới do session khác vừa insert/commit, hoặc không còn thấy jobs đã được session khác hoàn tất.

### 24.2. REPEATABLE READ và SERIALIZABLE

Trong một transaction, những mức isolation cao hơn đặt ra những bảo đảm khác về snapshot và anomaly. Nhưng nếu procedure tự kết thúc transaction rồi bắt đầu transaction mới, **không có một snapshot duy nhất giữ nguyên qua toàn procedure**. `COMMIT AND CHAIN` giữ transaction characteristics được hỗ trợ, không có nghĩa giữ nguyên transaction identity/snapshot từ trước commit.

### 24.3. Phân lô theo checkpoint và high-water mark

Nếu nghiệp vụ yêu cầu xử lý một tập dữ liệu xác định tại thời điểm bắt đầu:

- Ghi nhận một mốc đầu vào như `max(job_id)`/batch generation;
- Chỉ xử lý những rows nằm trong tập đó;
- Lưu cursor/checkpoint đã commit;
- Phân biệt những công việc mới đến sau mốc;
- Kiểm tra tính hợp lệ của khóa/điều kiện theo isolation.

Nếu chỉ liên tục đọc `state='pending'`, một luồng ingest liên tục có thể khiến procedure không bao giờ kết thúc hoặc kết thúc không ở mốc dự kiến.

### 24.4. Không nhầm SKIP LOCKED với đúng thứ tự tuyệt đối

`ORDER BY job_id ... FOR UPDATE SKIP LOCKED` ưu tiên một thứ tự tại thời điểm truy vấn, nhưng những rows bị khóa có thể bị bỏ qua. Đây là mô hình work queue có **out-of-order processing** hợp lý trong một số hệ thống, không phải bảo đảm jobs hoàn tất theo đúng job_id.

### 24.5. SERIALIZABLE có thể yêu cầu retry

Nếu transaction ở mức `SERIALIZABLE` gặp `serialization_failure` hoặc deadlock, ứng dụng có thể phải retry **đơn vị transaction thất bại**, không mặc định chạy lại tất cả batches đã commit. Để làm đúng cần idempotency và checkpoint.

## 25. Lock và VACUUM: vì sao không giữ transaction quá lâu?

Một transaction rất dài có thể:

- Giữ row/table locks lâu, khiến sessions khác phải chờ;
- Giữ snapshot làm ảnh hưởng cơ hội cleanup dead tuples của VACUUM;
- Tăng khả năng deadlock/lock contention;
- Tích lũy nhiều công việc chưa commit/WAL;
- Làm rollback sau lỗi tốn thời gian.

Batch commits có thể giảm thời gian giữ locks của **từng lô**, nhưng cũng:

- Tăng tổng số transaction commits/WAL flushes;
- Mở ra trạng thái partial progress;
- Yêu cầu retry và kiểm soát concurrency chặt chẽ;
- Không tự loại bỏ mọi deadlock/lock wait.

### 25.1. Không chỉ theo dõi elapsed time

Một procedure chạy 30 phút có thể:

~~~text
Kiểu A: 1 transaction 30 phút → giữ locks/snapshot dài.
Kiểu B: 180 transactions mỗi 10 giây → locks ngắn hơn,
        nhưng cần xử lý partial completion.
~~~

Không có lựa chọn mặc định đúng cho mọi nghiệp vụ. Với chuyển khoản ngân hàng gồm nhiều bước phụ thuộc nhau, atomicity có thể quan trọng hơn thời gian lock; với cleanup logs cũ theo từng đợt, chia transaction có thể phù hợp.

### 25.2. Giám sát những sessions đang chạy

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    query_start,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blockers
FROM pg_catalog.pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

`xact_start` phản ánh transaction hiện tại của backend; nếu procedure commit nhiều lần thì giá trị ấy có thể thay đổi giữa các batches. **Không lấy transaction_age của một snapshot duy nhất để suy ra tổng thời gian CALL.**

### 25.3. Lock wait

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids,
    query
FROM pg_catalog.pg_stat_activity
WHERE wait_event_type = 'Lock';
~~~

Quyền xem query của sessions khác phụ thuộc PostgreSQL role. `pg_blocking_pids` giúp nhận diện PIDs có thể đang chặn, không tự cho phép bạn hủy transaction của người khác.

### 25.4. SKIP LOCKED và deadlock

`SKIP LOCKED` giúp tránh chờ **những row locks được skip** trong cơ chế claim jobs, nhưng không bảo đảm toàn bộ procedure không có lock wait/deadlock ở những tables/indexes khác. Cần phân tích tất cả objects được đọc/ghi và thứ tự locking.

### 25.5. Đừng tự động terminate backend

`pg_cancel_backend` và `pg_terminate_backend` có thể dừng query hoặc session nhưng tác động tới transaction đang chạy và các ứng dụng khác. Trên production cần xác định owner, hậu quả rollback, khả năng partial commits và quyền vận hành. Không dùng chúng như bước “debug mặc định” khi CALL chậm.

## 26. Thủ tục không phải công cụ thay thế hệ thống workflow

Một procedure có thể xử lý nhiều batches trong database, nhưng workflow thực tế còn có:

- Network errors khi gọi external API;
- Message brokers và giao hàng trễ;
- Idempotency keys;
- Dead-letter queues;
- Compensation, reconciliation;
- Trạng thái retry với backoff;
- Monitoring/alerting;
- Quyền hạn ứng dụng và audit.

### 26.1. Không gọi dịch vụ bên ngoài như một phần ACID của PostgreSQL

Nếu procedure cập nhật database rồi gửi email qua một extension/UDF hoặc một cơ chế ngoài transaction:

~~~text
DB COMMIT thành công
External email thất bại
→ database và email không đồng bộ.
~~~

Ngược lại:

~~~text
External API thành công
DB ROLLBACK
→ side effect bên ngoài đã xảy ra.
~~~

Một cách tiếp cận phổ biến là **transactional outbox**: trong cùng transaction ghi dữ liệu nghiệp vụ và một bản ghi message/outbox, rồi worker riêng giao thông điệp có retry/idempotency. Khi procedure có nhiều commits, mỗi commit có thể làm một nhóm outbox events sẵn sàng được gửi.

### 26.2. Partial commits và bước hoàn tất

Một pipeline có thể cần trạng thái:

~~~text
PENDING → CLAIMED → PROCESSED → PUBLISHED
                   ↘ FAILED_RETRYABLE
                   ↘ FAILED_PERMANENT
~~~

Không nhất thiết chỉ có `pending/done` như lab. Khi business có external side effects, trạng thái rõ giúp tránh "job đã hoàn tất trong DB nhưng email vẫn chưa gửi".

### 26.3. Idempotency có nhiều lớp

| Lớp | Ví dụ bảo vệ |
| --- | --- |
| Database | Unique constraint trên `job_key`, state transitions |
| Batch checkpoint | `last_processed_id`/batch ID đã commit |
| External request | Idempotency key được service đích hỗ trợ |
| Messaging | Consumer inbox/dedup table |
| Reconciliation | Job định kỳ dò phần còn thiếu và sửa trạng thái |

Không chỉ dựa vào `CALL` không trả exception để xác định toàn bộ công việc đã hoàn tất; cần xem **bằng chứng trạng thái bền vững**.

### 26.4. Sự cố kết nối ngay sau COMMIT

Client có thể mất mạng đúng sau khi PostgreSQL commit nhưng trước khi client nhận kết quả. Lúc đó phía ứng dụng thấy timeout/connection error và **không biết chắc commit đã thành công hay chưa**. Đây là lý do cần idempotency key và truy vấn kiểm tra trạng thái thay vì retry mù.

## 27. Tránh các thao tác DDL không được phép trong transaction

Một số lệnh PostgreSQL yêu cầu chạy ngoài transaction block hoặc có điều kiện đặc biệt, ví dụ `CREATE INDEX CONCURRENTLY`.

Không mặc định rằng vì top-level `CALL` có thể `COMMIT`, ta sẽ được phép chạy mọi lệnh yêu cầu outside-transaction ở bên trong procedure.

### 27.1. Ví dụ không nên làm

~~~sql
-- Ý tưởng cần tránh:
--
-- CREATE PROCEDURE proc_lab_349.build_index()
-- LANGUAGE plpgsql
-- AS $$
-- BEGIN
--     COMMIT;
--     CREATE INDEX CONCURRENTLY ...; -- không được dùng trong procedure
-- END;
-- $$;
~~~

`CREATE INDEX CONCURRENTLY` có quy tắc thực thi riêng không phù hợp với việc chạy trong PL/pgSQL procedure transaction context. Với index builds online, hãy để **migration runner/client** chạy câu lệnh đúng bối cảnh và theo dõi invalid indexes nếu build thất bại.

### 27.2. Transaction control không xóa transaction rules của DDL

Mỗi SQL statement bên trong procedure vẫn tuân theo những restrictions của chính nó. Procedure không phải cách vượt qua requirement về isolation, lock mode, quyền hoặc lệnh bị cấm trong transaction.

### 27.3. Hậu quả của DDL đã commit

Nếu procedure có những DDL hợp lệ được commit từng giai đoạn, rollback về sau không đảo ngược DDL đã commit ở transaction trước. Với migration schema, cần change management, kiểm tra dependencies và rollback plan ở mức migration, không dựa vào một `ROLLBACK` duy nhất cuối job.

## 28. Chẩn đoán invalid transaction termination

Khi thấy:

~~~text
ERROR: invalid transaction termination
CONTEXT: PL/pgSQL function ... at COMMIT
~~~

đừng bắt đầu bằng cách thay `COMMIT` thành `ROLLBACK`: hai lệnh đều bị giới hạn bởi transaction context. Hãy xác định **mình đang vi phạm điều kiện nào**.

### 28.1. Checklist nguyên nhân

1. `CALL` có nằm trong `BEGIN ... COMMIT` không?
2. JDBC `autoCommit` đang `false`?
3. Spring `@Transactional`/ORM transaction manager có đang mở transaction?
4. Procedure có được gọi ở top-level hay qua một `SELECT`/function trung gian?
5. Procedure/child procedure có `SECURITY DEFINER`?
6. Definition có `SET ...` clause?
7. `COMMIT` nằm bên trong `BEGIN ... EXCEPTION ... END`?
8. Procedure đang chạy vòng lặp cursor từ DML `... RETURNING`?
9. Có migration/SQL client tự wrap lệnh CALL trong transaction?
10. Có phiên bản PostgreSQL/driver không phù hợp với cú pháp và behavior cần dùng?

### 28.2. Kiểm tra thủ tục đã được định nghĩa thế nào

~~~sql
SELECT
    p.oid::regprocedure AS procedure_signature,
    p.prokind,
    p.prosecdef,
    p.proconfig
FROM pg_catalog.pg_proc AS p
WHERE p.pronamespace = 'proc_lab_349'::regnamespace
  AND p.prokind = 'p'
ORDER BY p.oid::regprocedure::text;
~~~

Giải thích:

- `prokind = 'p'` cho procedure;
- `prosecdef` cho biết đặc tính `SECURITY DEFINER`;
- `proconfig` thể hiện settings gắn với definition (nếu có).

Lưu ý code dùng `p.oid::regprocedure` biểu diễn signature; procedure overloaded cần xem tham số/namespace để nhận diện đúng đối tượng.

### 28.3. Xem cấu hình client

Trong psql:

~~~text
\echo :AUTOCOMMIT
~~~

Trong JDBC:

~~~java
System.out.println(connection.getAutoCommit());
~~~

Trong Spring: xem transaction interceptor và transaction manager được dùng, propagation/call stack. **Không dựa vào một giá trị cấu hình tĩnh để chứng minh backend không ở trong explicit transaction** nếu code đã có các wrappers khác.

### 28.4. Cách sửa tùy nhu cầu

| Nhu cầu thật | Hướng xử lý |
| --- | --- |
| Toàn bộ logic phải atomic | Bỏ COMMIT/ROLLBACK trong procedure, để caller quản lý |
| Cần commit theo từng batch | CALL độc lập ngoài explicit transaction, thỏa mọi hạn chế |
| Procedure cần SECURITY DEFINER | Thiết kế lại quyền/ranh giới hoặc giữ caller-owned transaction |
| Procedure có SET clause | Không dùng transaction control trong procedure đó; xem lại nơi cấu hình |
| Bắt lỗi từng row | EXCEPTION block riêng, COMMIT sau khi block kết thúc |
| Cần lưu progress khi một batch fail | Bảng trạng thái/idempotency, retry/reconciliation |
| Cursor loop lớn | Chia query thành batches không giữ cursor dài |

### 28.5. Một lỗi khác: current transaction is aborted

Sau một statement lỗi trong explicit transaction, các câu SQL tiếp theo có thể báo:

~~~text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
~~~

Đây là **trạng thái hậu quả của lỗi trong transaction**, không nhất thiết là nguyên nhân gốc. Xem **lỗi đầu tiên** trước dòng này, và kết thúc transaction bằng `ROLLBACK` khi cần.

### 28.6. Trường hợp procedure thông thường không gặp lỗi

~~~sql
BEGIN;
CALL proc_lab_349.demo_block();
COMMIT;
~~~

Nếu procedure không có internal transaction control, ví dụ chỉ `RAISE NOTICE`, lời gọi hợp lệ. Đừng kết luận mọi `CALL` trong `BEGIN` đều bị cấm.

## 29. Theo dõi batch procedure mà không giả định tính nguyên tử

### 29.1. Đếm trạng thái jobs

~~~sql
SELECT
    state,
    COUNT(*) AS jobs
FROM proc_lab_349.jobs
GROUP BY state
ORDER BY state;
~~~

### 29.2. Xem các lần commit được ghi log theo batch

~~~sql
SELECT
    event_id,
    event_key,
    phase,
    recorded_at
FROM proc_lab_349.event_log
WHERE event_key LIKE 'batch-%'
ORDER BY event_id;
~~~

**Cẩn thận:** bảng lab chỉ ghi một log record trước `COMMIT` của từng batch. Trong hệ thống production, một log record không tự chứng minh mọi side effect ngoài database đã thành công; cần quan sát trạng thái riêng của từng hành động.

### 29.3. Track run ID để phân biệt lần gọi

Nếu chạy procedure nhiều lần, các chuỗi `batch-1`, `batch-2` có thể bị lặp giữa runs. Một hệ thống production nên dùng `run_id`/`batch_id` duy nhất, lưu:

- Thời điểm bắt đầu/kết thúc;
- Jobs đã nhận/xử lý/thất bại;
- Last committed checkpoint;
- Error code/message đã sanitize;
- Retry count và owner;
- Phiên bản procedure/migration.

Không dựa vào `event_id` của identity sequence để suy ra mọi transaction đã commit theo số thứ tự liên tục: sequence values **có thể bị tiêu thụ ngay cả khi transaction rollback**, vì sequences có semantics riêng.

### 29.4. Thời gian chạy của CALL vs từng transaction

Một `CALL` có thể kéo dài 10 phút và tự commit mỗi 10 giây. `pg_stat_activity.xact_start` của backend có thể chỉ phản ánh transaction đang chạy, không phải **thời điểm bắt đầu CALL**. Ở tầng ứng dụng cần ghi **duration tổng của CALL** và có thể thêm metric per-batch.

### 29.5. pg_stat_statements và logging

Khi đã bật `pg_stat_statements` trong môi trường phù hợp, có thể quan sát tổng thời gian/calls của một dạng statement, nhưng extension không thay thế bảng progress hoặc log từng batch nội bộ. Logging chi tiết có thể tăng overhead/lộ dữ liệu; tuân thủ chính sách giám sát.

### 29.6. EXPLAIN ANALYZE với CALL

Đừng coi `EXPLAIN (ANALYZE) CALL ...` như một công cụ đọc-only để phân tích procedure tự commit. `EXPLAIN` chủ yếu mô tả những câu lệnh SQL có plan được hỗ trợ; `CALL` không được xem như SELECT scan/join plan trực tiếp. Để đo những truy vấn nặng **bên trong procedure**, tách câu SQL tương ứng và benchmark trên lab hoặc dùng logging/auto_explain theo quyền/cấu hình.

Đặc biệt, **không dùng công cụ ghi plan có thực thi dữ liệu trên production mà chưa đánh giá side effects**.

## 30. Những ngộ nhận dễ gây lỗi về CALL và transaction control

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| Mọi procedure đều được `COMMIT` | Chỉ khi được gọi trong transaction context cho phép và không vướng hạn chế khác |
| `CALL` trong `BEGIN` bị cấm | `CALL` hợp lệ; điều bị cấm là internal transaction control |
| Một procedure chỉ có `INSERT` không khác gì procedure có `COMMIT` | Khác hoàn toàn về người sở hữu transaction |
| `CALL` từ Java luôn là top-level | Framework/driver có thể mở transaction |
| `autoCommit=false` vẫn cho procedure tự commit | Thường tạo explicit transaction context, internal `COMMIT` bị cấm |
| Spring `@Transactional` làm procedure tự COMMIT an toàn hơn | Transaction của Spring có thể xung đột với COMMIT nội bộ |
| `REQUIRES_NEW` cho phép procedure kết thúc transaction của chính nó | REQUIRES_NEW thường mở transaction mới ở caller, không cho procedure vượt giới hạn |
| Procedure COMMIT xong phải `START TRANSACTION` | PostgreSQL tự bắt đầu transaction mới trong PL/pgSQL |
| `BEGIN` trong PL/pgSQL là SQL transaction BEGIN | `BEGIN ... END` là block ngôn ngữ, không mở transaction |
| `COMMIT` trong procedure giúp tất cả công việc atomic | Nhiều COMMIT chia atomicity |
| Lỗi ở cuối CALL rollback mọi bước | Những batches đã commit vẫn tồn tại |
| `ROLLBACK` trong procedure hủy cả lô trước đã commit | Chỉ rollback transaction hiện tại |
| `ROLLBACK` cuối procedure là dry-run toàn cục | Các commits trước đó không bị đảo ngược |
| Procedure báo error nghĩa chưa có side effects | Side effects của transaction đã commit vẫn có |
| Retry toàn bộ CALL luôn an toàn | Có thể ghi/gửi/tính phí lặp nếu thiếu idempotency |
| Mỗi COMMIT mở transaction mới bằng câu START TRANSACTION | PostgreSQL tự bắt đầu trong procedure |
| `COMMIT AND CHAIN` giữ cùng snapshot xuyên các commits | Giữ một số transaction characteristics, **không** giữ nguyên snapshot |
| `CALL parent → CALL child` luôn không thể commit ở child | Chuỗi CALL/DO hợp lệ có thể transaction control |
| Có top-level CALL ở bên ngoài là đủ cho mọi function chen giữa | `SELECT function` xen giữa có thể chặn transaction control ở procedure sâu hơn |
| `SECURITY DEFINER` chỉ thay quyền, không tác động COMMIT | Procedure SECURITY DEFINER bị cấm transaction control |
| `SET search_path` clause trong procedure không ảnh hưởng COMMIT | Procedure có SET clause bị cấm transaction control |
| Thêm `SET LOCAL` ở bất kỳ chỗ nào cũng giống SET clause | Là cơ chế khác; phải xem transaction context |
| `COMMIT` trong block có EXCEPTION là hợp lệ vì có handler | Exception block là subtransaction, không được commit/rollback ở trong |
| Handler `WHEN OTHERS` có thể hủy các batch đã commit | Không, chỉ xử lý lỗi tại subtransaction thích hợp |
| PL/pgSQL `SAVEPOINT` giống SQL client savepoint | PL/pgSQL không hỗ trợ trực tiếp savepoint statements theo kiểu đó |
| `FOR r IN SELECT` + COMMIT luôn stream nhẹ | Cursor có thể thành holdable/materialize ở commit đầu |
| Commit mỗi row nhanh nhất | Có thể quá nhiều WAL/transaction overhead |
| Cursor từ `UPDATE RETURNING` cũng cho commit mỗi row | Transaction control bị cấm trong non-read-only cursor loops |
| `SKIP LOCKED` bảo đảm tuyệt đối không còn jobs khi query trả 0 | Có thể còn jobs đang bị worker khác lock |
| `SKIP LOCKED` bảo đảm thứ tự xử lý | Rows bị khóa có thể bị bỏ qua |
| `SKIP LOCKED` loại mọi khả năng deadlock | Chỉ tránh chờ một số row locks, không giải quyết mọi lock |
| `COMMIT` xong locks/snapshot vẫn giữ nguyên | Transaction-level locks được giải phóng; snapshot/visibility thay đổi |
| `COMMIT AND CHAIN` làm transaction thành phần của một ACID unit lớn | Mỗi COMMIT vẫn là ranh giới atomicity riêng |
| Sequence identity sẽ liên tục nếu rollback | Sequence values có thể bị tiêu thụ dù transaction rollback |
| Không thấy BEGIN trong source nghĩa không có explicit transaction | ORM/interceptor/pool có thể tạo transaction |
| Một psql CALL thành công bảo đảm Spring CALL thành công | Transaction wrappers có thể khác |
| `CREATE INDEX CONCURRENTLY` chạy được bên trong procedure nếu COMMIT trước | Có restrictions riêng, không được dùng theo cách đó |
| `pg_stat_activity.xact_start` là thời điểm toàn bộ CALL bắt đầu | Khi nhiều commits, nó chỉ phản ánh transaction hiện tại |
| Có thể dùng EXPLAIN ANALYZE CALL như một preview không thay đổi dữ liệu | Không coi CALL là read-only plan query; phải kiểm soát tác động ghi |
| Chỉ cần đổi `COMMIT` thành `ROLLBACK` để hết invalid transaction termination | Cả hai đều bị cấm trong explicit transaction context |
| Mọi lỗi trong transaction đều nên bị bắt bằng WHEN OTHERS | Có thể che mất lỗi và làm sai trạng thái |
| Partial commits luôn là giải pháp hiệu năng tốt | Cần so trade-off với atomicity, WAL, retry, lock contention |
| Không cần bảo vệ quyền EXECUTE vì procedure đã schema-qualified | EXECUTE privileges và quyền trên dữ liệu vẫn cần quản lý |

## 31. Bài tập thực hành

Các bài tập sử dụng schema `proc_lab_349`. Một số ví dụ **cố ý gây lỗi**; chỉ chạy trong database lab và quan sát trạng thái transaction. Đối với các câu SQL mẫu có `...`, đó là placeholder cần thay bằng tên/câu lệnh hợp lệ, không phải SQL hoàn chỉnh. Trước mỗi thử nghiệm có DML, xác định những rows sẽ thay đổi và không dùng bảng nghiệp vụ production.

### Bài 1 — Phân biệt CALL và SELECT

Viết hai câu gọi:

~~~sql
SELECT public.add_two_numbers(2, 3);
CALL public.print_greeting('An');
~~~

**Câu hỏi:** vì sao không thể viết `SELECT print_greeting('An')` để coi procedure như một SQL function trả giá trị?

### Bài 2 — Định nghĩa procedure

Tạo procedure nhận `IN p_message text` và `RAISE NOTICE`. Gọi bằng `CALL` từ psql. **Câu hỏi:** nó có cần `COMMIT` để in notice không?

### Bài 3 — INOUT

Tạo procedure `INOUT p_counter integer` cộng thêm 1. Gọi `CALL(...5)` và quan sát giá trị kết quả. **Câu hỏi:** khác thế nào với function `RETURNS integer`?

### Bài 4 — CALL không tự là COMMIT

~~~sql
BEGIN;
CALL public.print_greeting('Bình');
ROLLBACK;
~~~

**Câu hỏi:** tại sao `CALL` vẫn hợp lệ trong transaction block khi procedure không tự `COMMIT`/`ROLLBACK`?

### Bài 5 — Gọi độc lập có hai COMMIT

~~~sql
CALL proc_lab_349.commit_two_phases('exercise-05');
~~~

**Câu hỏi:** đã có mấy transaction được commit trong procedure, và hai rows log có cùng transaction không?

**Đáp án:** hai transaction riêng biệt.

### Bài 6 — CALL trong BEGIN bị từ chối

~~~sql
BEGIN;
CALL proc_lab_349.commit_two_phases('exercise-06');
ROLLBACK;
~~~

**Bài tập:** ghi lỗi đầu tiên, giải thích vì sao `COMMIT` nội bộ bị cấm, xác nhận không có logs được commit cho key `exercise-06`.

### Bài 7 — JDBC autoCommit

Một connection gọi `setAutoCommit(false)` rồi `CALL commit_two_phases`.

**Câu hỏi:** vì sao việc driver/application tự mở transaction làm internal `COMMIT` lỗi? Khác gì `autoCommit(true)` khi không có wrapper?

### Bài 8 — BEGIN trong PL/pgSQL

Trong:

~~~sql
CREATE PROCEDURE public.demo()
LANGUAGE plpgsql AS $$
BEGIN
    RAISE NOTICE 'hi';
END;
$$;
~~~

**Câu hỏi:** `BEGIN` này có phải mở SQL transaction không?

**Đáp án:** không, đây là block delimiter của PL/pgSQL.

### Bài 9 — Tự bắt đầu transaction mới

Procedure thực thi `INSERT A; COMMIT; INSERT B; COMMIT;`.

**Bài tập:** vẽ ranh giới transaction và giải thích vì sao không có `START TRANSACTION` riêng trong thân procedure.

### Bài 10 — Lỗi sau commit đầu

~~~sql
CALL proc_lab_349.fail_after_first_commit('exercise-10');
~~~

**Câu hỏi:** dù CALL báo lỗi, row nào đã commit? Kiểm tra bằng `SELECT` mới.

**Đáp án:** `already-committed` tồn tại; `not-committed` không được commit.

### Bài 11 — ROLLBACK giữa chừng

~~~sql
CALL proc_lab_349.rollback_middle('exercise-11');
~~~

**Câu hỏi:** vì sao sau CALL chỉ còn log `after-rollback`?

### Bài 12 — Retry và idempotency

Một procedure có hai transaction: ghi hóa đơn rồi gửi email. Lượt đầu commit hóa đơn nhưng lỗi ở email, client retry toàn CALL.

**Bài tập:** thiết kế khóa idempotency, trạng thái đã gửi và outbox để không tạo trùng hóa đơn/email.

### Bài 13 — COMMIT AND CHAIN

Viết procedure dùng `COMMIT AND CHAIN` giữa hai batches.

**Câu hỏi:** `AND CHAIN` giữ những gì và **không** giữ những gì về transaction identity/snapshot?

### Bài 14 — Isolation level

Giả sử procedure ở `READ COMMITTED`: giữa batch 1 và batch 2, session khác insert một job mới và commit.

**Câu hỏi:** batch 2 có thể thấy job mới không? Nếu muốn xử lý tập dữ liệu cố định, nên dùng high-water mark/snapshot strategy thế nào?

### Bài 15 — Nested CALL

~~~sql
CALL proc_lab_349.parent_call('exercise-15');
~~~

**Câu hỏi:** tại sao internal COMMIT trong `child_commit` có thể hợp lệ dù nó không được gọi trực tiếp từ client?

### Bài 16 — SELECT function xen giữa

Cho call stack:

~~~text
CALL parent()
  → SELECT f()
    → CALL child()
      → COMMIT
~~~

**Bài tập:** giải thích vì sao child có thể bị cấm COMMIT, dù parent được gọi top-level.

### Bài 17 — SECURITY DEFINER

Tạo procedure `SECURITY DEFINER` chỉ `RAISE NOTICE`. Sau đó xem điều gì sẽ xảy ra nếu thêm `COMMIT`.

**Câu hỏi:** restriction do quyền hay transaction context? Có tự hết khi dùng autocommit không?

### Bài 18 — SET clause

Vì sao `CREATE PROCEDURE ... SET search_path = ...` khiến transaction control bị hạn chế? Nếu cần schema qualification và commit, nên thiết kế thay thế thế nào?

### Bài 19 — EXCEPTION block

Một developer viết:

~~~text
BEGIN
    INSERT ...
    COMMIT;
EXCEPTION WHEN OTHERS THEN
    ...
END;
~~~

**Câu hỏi:** vì sao COMMIT không hợp lệ khi block có exception handler?

### Bài 20 — COMMIT sau EXCEPTION block

Viết một inner block `BEGIN ... EXCEPTION ... END` chỉ xử lý SQL lỗi, sau đó đặt `COMMIT` **bên ngoài** inner block.

**Câu hỏi:** subtransaction rollback phạm vi nào, transaction lớn rollback phạm vi nào?

### Bài 21 — SAVEPOINT

Một function PL/pgSQL muốn chạy `SAVEPOINT s1; ROLLBACK TO s1;`.

**Bài tập:** giải thích giới hạn và mô tả cách dùng block với `EXCEPTION` để rollback những thay đổi trong block.

### Bài 22 — Cursor loop

Trong `FOR r IN SELECT ... LOOP ... COMMIT; END LOOP`, câu lệnh `COMMIT` đầu tiên có thể khiến cursor được chuyển thành dạng gì?

**Đáp án:** holdable cursor, với query result được materialize.

### Bài 23 — DML RETURNING loop

Một procedure muốn `FOR r IN UPDATE jobs ... RETURNING ... LOOP COMMIT; END LOOP`.

**Câu hỏi:** có được phép kết thúc transaction trong vòng lặp do non-read-only command điều khiển không? Nêu cách chia batch bằng truy vấn UPDATE riêng.

### Bài 24 — GET DIAGNOSTICS

Sau một UPDATE nhiều rows, dùng:

~~~sql
GET DIAGNOSTICS v_count = ROW_COUNT;
~~~

**Câu hỏi:** tại sao số này hữu ích hơn giả định `LIMIT 100` luôn đồng nghĩa update 100 jobs?

### Bài 25 — Xử lý theo batch size 2

Reset/tạo sáu jobs pending trong lab rồi gọi:

~~~sql
CALL proc_lab_349.process_pending_jobs(2);
~~~

**Kỳ vọng trong môi trường không cạnh tranh:** ba batches, mỗi batch tối đa hai rows được update và commit.

### Bài 26 — Batch size invalid

~~~sql
CALL proc_lab_349.process_pending_jobs(0);
~~~

**Câu hỏi:** procedure cần phát lỗi trước khi update để bảo vệ điều gì? Tại sao nên có upper bound cho batch size?

### Bài 27 — SKIP LOCKED

Session A đang giữ lock trên job 1; session B chạy query `FOR UPDATE SKIP LOCKED LIMIT 2`.

**Câu hỏi:** B có nhất thiết chọn job 1 không? Nếu không chọn, có thể suy ra job 1 đã hoàn thành chưa?

### Bài 28 — Trả 0 rows chưa chắc hết việc

Một worker chạy `SKIP LOCKED` nhưng nhận 0 rows, dù có 10 rows pending đang bị các workers khác khóa.

**Bài tập:** đề xuất scheduler/retry/reconciliation để không bỏ sót jobs nếu những workers kia rollback.

### Bài 29 — At-most-once và exactly-once

Procedure đánh dấu `state='done'` và gọi external email API.

**Câu hỏi:** vì sao trạng thái database không tự bảo đảm email chỉ gửi đúng một lần? Nêu vai trò outbox/idempotency.

### Bài 30 — Atomic vs partial progress

Một giao dịch chuyển 100 từ ví A sang ví B; team đề xuất commit sau bước trừ tiền để giảm thời gian lock.

**Bài tập:** giải thích vi phạm atomicity và chọn procedure không commit để caller quản lý transaction.

### Bài 31 — Spring @Transactional

Một method có `@Transactional` gọi procedure tự `COMMIT`.

**Câu hỏi:** nguyên nhân lỗi có thể là gì? Vì sao đổi sang `REQUIRES_NEW` không tự khắc phục?

### Bài 32 — Spring NOT_SUPPORTED

`NOT_SUPPORTED` có thể giúp không tham gia transaction đã mở, nhưng trước khi kết luận internal commit hợp lệ cần kiểm tra những gì?

**Gợi ý:** transaction manager, datasource, connection autocommit, driver CALL syntax, call stack, security/SET/EXCEPTION restrictions.

### Bài 33 — psql autocommit

Chạy trong psql:

~~~text
\echo :AUTOCOMMIT
~~~

**Câu hỏi:** nếu autocommit off và psql tự mở transaction, procedure tự commit có thể gặp lỗi gì?

### Bài 34 — Migration runner

Một migration tool chạy mọi file SQL bên trong một transaction rồi chứa `CALL process_pending_jobs(2)`.

**Bài tập:** mô tả vì sao thất bại và hai cách tổ chức lại: tách job độc lập hoặc để caller quản lý transactions.

### Bài 35 — CREATE INDEX CONCURRENTLY

Một procedure chạy `COMMIT; CREATE INDEX CONCURRENTLY ...`.

**Câu hỏi:** vì sao không nên dùng procedure như cách chạy online index build? Nên cho migration runner/client trực tiếp gọi lệnh thế nào?

### Bài 36 — Locks

Một batch procedure commit mỗi 10.000 rows, p95 latency của web service tăng vì lock waits.

**Bài tập:** đo `pg_stat_activity`, `pg_blocking_pids`, transaction duration, số rows per batch và retry contention; đề xuất giảm batch size/điều phối thời điểm phù hợp nếu nghiệp vụ cho phép.

### Bài 37 — Một triệu commits

Nếu procedure commit mỗi row với một triệu rows, có thể tốn những loại chi phí nào?

**Gợi ý:** WAL flush, transaction setup, lock acquisition, context switching, CPU, throughput, replication lag theo workload.

### Bài 38 — pg_stat_activity xact_start

Một `CALL` chạy 20 phút và commit mỗi 10 giây; `xact_start` hiện transaction mới chỉ 2 giây.

**Câu hỏi:** có thể nói toàn CALL chỉ chạy 2 giây không? Cần metric nào theo dõi duration toàn CALL?

### Bài 39 — Sequence gaps

Một `INSERT` vào bảng dùng identity sequence được rollback.

**Câu hỏi:** vì sao `event_id` có thể bị khuyết số dù không có row tương ứng? Tại sao không dùng việc thiếu ID làm bằng chứng thiếu transaction đã commit?

### Bài 40 — Invalid transaction termination runbook

Ứng dụng báo:

~~~text
ERROR: invalid transaction termination
CONTEXT: PL/pgSQL function ... at COMMIT
~~~

**Bài tập:** lập checklist tối thiểu gồm explicit transaction, JDBC autoCommit, Spring transaction manager, nested CALL/SELECT, SECURITY DEFINER, SET clause, EXCEPTION block và cursor loops.

### Bài 41 — Production incident đã partial commit

Một CALL batch trả timeout; dashboard thấy 75% jobs `done`. Cần làm gì trước khi retry?

**Đáp án định hướng:** kiểm tra checkpoint/trạng thái đã commit, xác minh external effects, đảm bảo idempotency, chỉ claim jobs còn pending hoặc có retry policy rõ.

### Bài 42 — COMMIT AND CHAIN và SERIALIZABLE

Một procedure dùng `COMMIT AND CHAIN` sau từng batch ở isolation SERIALIZABLE.

**Câu hỏi:** các batches có cùng snapshot không? Nếu một transaction gặp serialization failure, retry toàn CALL có an toàn không?

### Bài 43 — Kiểm tra metadata procedure

Truy vấn `pg_proc` lấy `prokind`, `prosecdef`, `proconfig` của procedures trong `proc_lab_349`.

**Câu hỏi:** mỗi trường giúp chẩn đoán restriction transaction control nào?

### Bài 44 — Permission và schema

Một procedure cần quyền cập nhật bảng khác schema.

**Bài tập:** nêu vì sao việc chuyển sang SECURITY DEFINER để có quyền có thể làm internal COMMIT không hợp lệ; thiết kế phân quyền thay thế có đánh giá an toàn.

### Bài 45 — Deadlock

Hai transactions cập nhật jobs theo thứ tự khóa ngược nhau và deadlock.

**Câu hỏi:** internal `COMMIT` có giải quyết hoàn toàn deadlocks không? Lập quy tắc thứ tự khóa, batch size và retry như thế nào?

### Bài 46 — Error handling không nuốt lỗi

Procedure dùng `WHEN OTHERS THEN RAISE NOTICE 'ignored'` rồi tiếp tục commit.

**Bài tập:** mô tả rủi ro mất tính đúng. Nên bắt SQLSTATE cụ thể và re-raise các lỗi nào?

### Bài 47 — Quản lý transaction ownership

Thiết kế hai API:

~~~text
complete_job_atomic(job_key)
process_pending_jobs(batch_size)
~~~

**Câu hỏi:** API nào cho phép chạy trong `@Transactional`? API nào cần top-level `CALL` riêng? Ghi contract cho rollback/retry.

### Bài 48 — Monitoring sau triển khai

Viết danh sách chỉ số cần quan sát sau khi thay transaction batch size: transaction duration, locks, deadlocks, jobs pending/done, retries, WAL/replication, p95, error count và checkpoint.

### Bài 49 — Trạng thái caller bị aborted

Trong explicit transaction, một CALL phát lỗi. Lệnh kế tiếp báo `current transaction is aborted`.

**Câu hỏi:** đâu là lỗi gốc, đâu là lỗi thứ cấp? Bước phục hồi ở client là gì?

### Bài 50 — Capstone: workflow xử lý đơn hàng

Thiết kế hai phần:

**Phần A — Thao tác ACID của một đơn hàng:** cập nhật trạng thái đơn, kho và audit cùng transaction. Chọn procedure **không internal COMMIT** được ứng dụng gọi trong transaction.

**Phần B — Job nền xử lý 50.000 đơn độc lập:** chọn batch size, checkpoint và procedure top-level có thể `COMMIT` theo lô. Mỗi đơn dùng unique business key, có retry và outbox cho external notifications.

Yêu cầu nộp:

1. Sơ đồ transaction boundaries cho hai phần.
2. SQL signature của các procedures.
3. Nêu chỗ dùng `CALL` và chỗ không được bao trong `BEGIN`.
4. Thiết kế exception handling không đặt COMMIT trong subtransaction block.
5. Mô tả idempotency và cách xử lý timeout sau khi commit.
6. Chiến lược tránh lock contention và bỏ sót jobs với `SKIP LOCKED`.
7. Cách gọi từ JDBC/Spring cho cả hai kiểu.
8. Bộ test cho lỗi giữa batch, deadlock, retry, bad input và partial progress.
9. Metric vận hành và rollback/fix-forward.
10. Giải thích vì sao các giao dịch đã commit không thể được hủy bằng một `ROLLBACK` cuối procedure.

## 32. Checklist trước khi triển khai procedure điều khiển transaction

### 32.1. Thiết kế transaction

- [ ] Có xác định rõ **caller hay procedure sở hữu transaction boundaries**.
- [ ] Nếu cần all-or-nothing, procedure **không** tự `COMMIT`/`ROLLBACK`.
- [ ] Nếu cần batch commits, đã chấp nhận **partial progress** có chủ đích.
- [ ] Mỗi `COMMIT` có mô tả rõ dữ liệu nào trở nên bền vững.
- [ ] Có cơ chế idempotency/retry không xử lý lại work đã commit.
- [ ] Có checkpoint/run ID và cách phân biệt các lần chạy.
- [ ] Có chính sách khi connection lỗi ngay sau commit.
- [ ] Có quy trình reconciliation cho trạng thái nửa hoàn tất.
- [ ] Không trông đợi một `ROLLBACK` cuối hoàn tác các commits trước.

### 32.2. Điều kiện CALL hợp lệ

- [ ] `CALL` có transaction control được gọi top-level, không nằm trong `BEGIN`.
- [ ] Framework không tạo explicit transaction ngoài ý muốn.
- [ ] Nếu nested, call stack là chuỗi `CALL`/`DO` hợp lệ cho transaction control.
- [ ] Không có `SELECT function(...)` xen giữa chặn quyền transaction control.
- [ ] Procedure cần commit **không** là `SECURITY DEFINER`.
- [ ] Procedure cần commit **không** khai báo `SET` clause.
- [ ] `COMMIT`/`ROLLBACK` không nằm trong block có `EXCEPTION` handler.
- [ ] Nếu có cursor loop, hiểu giới hạn holdable cursor và DML `RETURNING`.
- [ ] Không gọi DDL bị cấm trong transaction như `CREATE INDEX CONCURRENTLY` theo cách không hợp lệ.
- [ ] Đã kiểm tra version PostgreSQL và quyền EXECUTE.

### 32.3. Tích hợp ứng dụng

- [ ] JDBC `autoCommit` và transaction manager đã được kiểm chứng.
- [ ] Spring `@Transactional`/propagation được cấu hình theo contract của procedure.
- [ ] Không dựa vào `REQUIRES_NEW` để vượt giới hạn COMMIT nội bộ.
- [ ] Connection pool reset transaction/session state an toàn.
- [ ] Lệnh `CALL` có error handling và rollback ở caller khi cần.
- [ ] Client phân biệt **call failed** với **all work rolled back**.
- [ ] API ghi rõ return/OUT semantics và hiệu lực partial completion.
- [ ] External side effects có outbox/idempotency/reconciliation.
- [ ] Quyền truy cập bảng, schema và procedure được cấp tối thiểu cần thiết.

### 32.4. Hiệu năng và vận hành

- [ ] Batch size có giới hạn và số liệu benchmark.
- [ ] Có đo WAL, commit rate, lock wait và total duration.
- [ ] Không giữ cursor khổng lồ xuyên commit hoặc giả định streaming mãi.
- [ ] Các rows được claim có chiến lược concurrency và starvation rõ.
- [ ] Đã xử lý trường hợp `SKIP LOCKED` trả 0 dù còn pending jobs bị khóa.
- [ ] Có timeout/rate limit phù hợp, không giữ transaction chờ network.
- [ ] Có metrics số batches, rows, retries, failed jobs, checkpoint.
- [ ] Có test deadlock/serialization failure, connection drop, process crash.
- [ ] Có monitoring sau deploy và rollback/fix-forward.
- [ ] Không chạy DML/commit demo trực tiếp trên dữ liệu production.

## 33. Quy trình đánh giá một procedure hiện có

Khi tiếp nhận một thủ tục cũ chưa rõ được quản lý transaction bởi ai, nên dùng quy trình sau trước khi chỉnh code:

### Bước 1 — Đọc signature và definition

~~~sql
SELECT
    p.oid::regprocedure AS procedure_signature,
    pg_catalog.pg_get_functiondef(p.oid) AS definition
FROM pg_catalog.pg_proc AS p
WHERE p.pronamespace = 'proc_lab_349'::regnamespace
  AND p.prokind = 'p'
ORDER BY p.oid::regprocedure::text;
~~~

Đây là câu truy vấn **đọc metadata**; quyền quan sát definition có thể phụ thuộc role/cài đặt. Xác định có `COMMIT`, `ROLLBACK`, `EXCEPTION`, `SECURITY DEFINER` hoặc `SET` clause không.

### Bước 2 — Ghi call path từ ứng dụng

~~~text
HTTP / scheduler
  |
  +-- Service method (@Transactional?)
  |
  +-- Repository/JDBC
  |
  +-- Connection (autoCommit ?)
  |
  +-- CALL procedure()
        |
        +-- CALL child()?
        +-- SELECT helper()?
        +-- COMMIT?
~~~

Không đủ khi chỉ xem SQL body; quyền kết thúc transaction phụ thuộc **cách gọi thực tế**.

### Bước 3 — Kiểm tra semantics khi lỗi giữa chừng

Trong database lab:

1. Cho batch đầu thành công và commit.
2. Cố ý gây lỗi ở batch sau.
3. Kiểm tra các rows đã commit.
4. Chạy lại procedure.
5. Xác minh không tạo duplicate/side effect lặp.
6. Kiểm tra không bị stuck ở trạng thái in-progress.

### Bước 4 — Kiểm tra transaction count và locks

Quan sát transaction durations, lock waits, WAL volume, tiến độ batches và external side effects; không chỉ đo thời gian của một `CALL` duy nhất.

### Bước 5 — Quyết định contract

| Dấu hiệu | Quyết định thường phù hợp |
| --- | --- |
| Procedure chạy cho một HTTP request cần atomicity | Bỏ internal COMMIT, để framework/caller quản lý |
| Job nền xử lý từng batch độc lập | Top-level CALL với internal commits + idempotency |
| Procedure cần `SECURITY DEFINER` | Không dùng internal transaction control trong chính procedure đó |
| Caller đã mở explicit transaction | Procedure phải không tự commit |
| Một query cực lớn đang giữ cursor quá lâu | Thiết kế batch theo khóa thay vì commit bên trong cursor |
| Nhiều side effects ngoài database | Dùng outbox/workflow + retry semantics |
| Dữ liệu phải có snapshot nhất quán xuyên toàn tác vụ | Xem xét một transaction hoặc thiết kế snapshot/checkpoint rõ, không giả định COMMIT AND CHAIN giữ nguyên snapshot |

### Bước 6 — Ghi tài liệu vận hành

Trong API/module documentation, cần ghi:

- Cách gọi bắt buộc (top-level hay trong transaction).
- Vai trò/permissions cần thiết.
- Các commit points.
- Ý nghĩa kết quả khi success/failure.
- Idempotency/retry behavior.
- Các giới hạn batch/concurrency.
- Mã lỗi quan trọng và cách khôi phục.
- Version PostgreSQL được hỗ trợ.

## 34. Câu hỏi thường gặp

### 34.1. Tôi gọi CALL trong BEGIN và thấy invalid transaction termination. Có phải PostgreSQL không hỗ trợ procedure không?

Không. PostgreSQL hỗ trợ procedure, và `CALL` trong explicit transaction cũng hợp lệ nếu procedure không tự kết thúc transaction. Lỗi ở đây đến từ việc **internal COMMIT/ROLLBACK** muốn đóng transaction mà **caller** đang sở hữu.

### 34.2. Tôi dùng psql chạy CALL thành công nhưng Spring lỗi. Tại sao?

`psql` có thể gửi một top-level CALL độc lập, còn Spring `@Transactional`/JDBC `autoCommit=false` tạo explicit transaction. Cần kiểm tra transaction context thực tế và thiết kế interface thống nhất.

### 34.3. Procedure không có COMMIT thì ai commit những INSERT bên trong?

Nếu caller đang trong explicit transaction, caller quyết định `COMMIT`/`ROLLBACK`. Nếu client gửi một `CALL` độc lập theo autocommit bình thường và procedure không điều khiển transaction, câu lệnh được xử lý trong transaction do statement/session context quản lý và hoàn tất theo quy tắc autocommit.

### 34.4. Tôi có thể gọi COMMIT bên trong IF không?

Một `COMMIT` trong nhánh `IF` về mặt vị trí PL/pgSQL có thể hợp lệ **nếu toàn bộ bối cảnh transaction control cho phép**. `IF` tự nó không biến lời gọi thành transaction riêng. Nhưng `COMMIT` nằm trong một block `EXCEPTION` đang hoạt động vẫn bị cấm.

### 34.5. Tôi có thể COMMIT trong loop không?

Có điều kiện, với procedure top-level hợp lệ. Nhưng vòng lặp cursor có thể bị chuyển thành holdable/materialized tại commit đầu, và cursor loop được điều khiển bởi non-read-only commands (ví dụ `UPDATE ... RETURNING`) không cho transaction control.

### 34.6. Tôi có thể ROLLBACK đến SAVEPOINT trong procedure không?

PL/pgSQL không hỗ trợ trực tiếp các lệnh savepoint theo cách SQL client dùng. Hãy dùng **block `BEGIN ... EXCEPTION ... END`** cho nhu cầu xử lý lỗi cục bộ và nhớ rằng không thể `COMMIT`/`ROLLBACK` khi ở trong block có exception handler.

### 34.7. COMMIT AND CHAIN có giữ cùng transaction ID không?

Không nên hiểu vậy. Đây là transaction mới; một số transaction characteristics được tiếp nối, còn identity/snapshot/locks của transaction trước không giữ nguyên xuyên commits.

### 34.8. CREATE PROCEDURE với SECURITY DEFINER giúp code COMMIT quyền cao được không?

Không. PostgreSQL cấm transaction-control statements trong procedure `SECURITY DEFINER`.

### 34.9. Thêm SET work_mem trong CREATE PROCEDURE có ảnh hưởng không?

Có. Procedure có `SET` clause trong definition không được thực thi transaction-control statements, kể cả khi top-level CALL.

### 34.10. Procedure báo lỗi thì tôi có nên retry toàn bộ CALL?

Chỉ khi workflow được thiết kế **idempotent** và bạn có thể xác định phần đã commit. Một lỗi sau internal COMMIT có thể để lại dữ liệu đã được xác nhận trong các transaction trước.

### 34.11. SKIP LOCKED giúp mọi queue tuyệt đối exactly once?

Không. Nó giúp worker không chờ các rows đang bị khóa trong một số trường hợp. Exactly-once external effects còn cần idempotency, transaction state, retry semantics và reconciliation.

### 34.12. Làm sao lựa chọn batch size?

Từ yêu cầu độ trễ/locks/throughput/WAL và dữ liệu thật. Bắt đầu với kích thước có thể chấp nhận, đo nhiều lần dưới tải đại diện, quan sát lỗi và giới hạn tối đa; không có một con số đúng cho mọi bảng.

## 35. Tài liệu PostgreSQL chính thức

Các liên kết dưới đây tham chiếu tài liệu **PostgreSQL hiện hành**; trước khi sử dụng trên hệ thống thật, chọn **đúng major version** đang vận hành:

- [SQL CALL](https://www.postgresql.org/docs/current/sql-call.html): cú pháp gọi procedure, input/output parameters và giới hạn transaction control khi `CALL` nằm trong explicit transaction block.
- [CREATE PROCEDURE](https://www.postgresql.org/docs/current/sql-createprocedure.html): định nghĩa procedure, `SECURITY DEFINER` và `SET` clause cùng các hạn chế transaction.
- [PL/pgSQL — Transaction Management](https://www.postgresql.org/docs/current/plpgsql-transactions.html): tài liệu trọng tâm về `COMMIT`, `ROLLBACK`, `AND CHAIN`, top-level/nested `CALL` và `DO`, cursor loops, subtransactions.
- [PL/pgSQL — Errors and Messages](https://www.postgresql.org/docs/current/plpgsql-errors-and-messages.html): `RAISE NOTICE`, `RAISE EXCEPTION` và SQLSTATE.
- [PL/pgSQL — Trapping Errors](https://www.postgresql.org/docs/current/plpgsql-control-structures.html#PLPGSQL-ERROR-TRAPPING): `BEGIN ... EXCEPTION ... END`, subtransaction semantics.
- [PL/pgSQL — Cursors](https://www.postgresql.org/docs/current/plpgsql-cursors.html): cursor usage và vòng đời result sets.
- [SQL BEGIN](https://www.postgresql.org/docs/current/sql-begin.html): explicit transaction block của client.
- [SQL COMMIT](https://www.postgresql.org/docs/current/sql-commit.html): hoàn tất giao dịch, `AND CHAIN`.
- [SQL ROLLBACK](https://www.postgresql.org/docs/current/sql-rollback.html): hủy thay đổi transaction và `AND CHAIN`.
- [SAVEPOINT](https://www.postgresql.org/docs/current/sql-savepoint.html): savepoint SQL ở transaction do caller quản lý.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): READ COMMITTED, REPEATABLE READ, SERIALIZABLE và snapshot semantics.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): row locks, table locks, deadlocks.
- [SELECT ... FOR UPDATE / SKIP LOCKED](https://www.postgresql.org/docs/current/sql-select.html): locking clauses và cách SKIP LOCKED bỏ qua rows đang bị khóa.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity` và wait events.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): `CONCURRENTLY` và các hạn chế transaction riêng.
- [SQL DO](https://www.postgresql.org/docs/current/sql-do.html): anonymous code block và transaction restrictions.
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html): đối chiếu function với procedure.

Đặc biệt, **mục `PL/pgSQL Transaction Management`** là tài liệu cần đối chiếu trực tiếp khi gặp lỗi `invalid transaction termination`. Các chi tiết về quyền, procedural language, output parameter và driver behavior có thể khác giữa các phiên bản.

## 36. Tổng kết

**`CALL` là lệnh gọi một PostgreSQL procedure**, không phải lệnh để tự động commit. Procedure có thể thực thi `COMMIT` hoặc `ROLLBACK` để chia công việc thành nhiều transactions, nhưng **chỉ khi được gọi trong bối cảnh cho phép**: top-level `CALL`/chuỗi nested `CALL`/`DO` hợp lệ, không nằm trong explicit transaction block do caller mở và không vi phạm những restriction khác.

Trong một procedure:

- **`COMMIT`** làm dữ liệu transaction hiện tại trở nên bền vững; phần tiếp theo chạy trong transaction mới.
- **`ROLLBACK`** hủy phần chưa commit của transaction hiện tại, không ảnh hưởng phần đã commit từ trước.
- **`COMMIT AND CHAIN`/`ROLLBACK AND CHAIN`** cho phép tiếp tục một transaction mới giữ những characteristics được hỗ trợ, **không** tạo cùng một snapshot xuyên các transaction.
- **`SECURITY DEFINER`**, **`SET` clause**, **`EXCEPTION` blocks** và **cursor loops** áp thêm những điều kiện hạn chế riêng.

Hai kiểu thiết kế không thể trộn lẫn một cách tùy tiện:

| Nhu cầu | Cách thiết kế phù hợp |
| --- | --- |
| Một nghiệp vụ cần all-or-nothing | Procedure **không tự commit**, caller mở transaction và quyết định COMMIT/ROLLBACK |
| Một job dài gồm các lô độc lập | Procedure **tự commit theo batch**, được gọi top-level và có checkpoint/idempotency/retry |

Với Java/JDBC/Spring, **transaction context thực tế** quan trọng hơn việc source có viết chữ `BEGIN` hay không. `setAutoCommit(false)` hoặc `@Transactional` có thể khiến internal `COMMIT` của một top-level-looking `CALL` bị cấm. Nếu bắt buộc batch commits, hãy dành một call boundary thích hợp, tránh caller-owned transaction và kiểm tra toàn bộ restriction của procedure.

Cuối cùng, **một CALL báo lỗi không có nghĩa mọi thao tác đã được rollback** nếu procedure đã commit trước đó. Hãy thiết kế transaction boundaries từ yêu cầu nhất quán, quản lý partial progress, locks, retries, external side effects và quan sát vận hành trước khi bật transaction control. Khi ranh giới rõ ràng, `CALL` là một công cụ mạnh để đóng gói xử lý dữ liệu; khi ranh giới mơ hồ, nó có thể trở thành nguồn của những lỗi transaction khó phục hồi.
