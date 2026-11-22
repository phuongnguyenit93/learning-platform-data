# Cấu trúc khối DECLARE, BEGIN, EXCEPTION và END trong PL/pgSQL

Trong PostgreSQL, **PL/pgSQL** là ngôn ngữ thủ tục giúp viết hàm (`FUNCTION`), thủ tục (`PROCEDURE`), trigger function và khối thực thi ẩn danh (`DO`). Nếu SQL thuần mô tả **tập dữ liệu cần đọc hoặc thay đổi**, PL/pgSQL cung cấp thêm biến, rẽ nhánh, vòng lặp, khối lồng nhau và xử lý ngoại lệ.

Nền tảng của PL/pgSQL là một **block**:

~~~sql
[ <<label>> ]
[ DECLARE
    -- Khai báo biến
]
BEGIN
    -- Các câu lệnh thực thi
[ EXCEPTION
    -- Các nhánh bắt và xử lý lỗi
]
END [label];
~~~

Bốn từ khóa quan trọng của bài này là:

- **`DECLARE`:** khai báo biến, hằng, kiểu dữ liệu và giá trị khởi tạo.
- **`BEGIN`:** đánh dấu bắt đầu phần câu lệnh **của khối PL/pgSQL**.
- **`EXCEPTION`:** phần tùy chọn để xử lý các lỗi phát sinh trong khối.
- **`END`:** đánh dấu kết thúc khối, thường đi kèm dấu chấm phẩy `;`.

Điểm dễ nhầm nhất: **`BEGIN ... END` trong PL/pgSQL không tương đương với `BEGIN; ... COMMIT;` trong SQL transaction**. Và khi một khối có `EXCEPTION` bắt lỗi, PostgreSQL sử dụng cơ chế **subtransaction nội bộ** để hoàn tác thay đổi database trong phần được bảo vệ trước khi chạy handler.

Bài học thuộc chương **PL/pgSQL** của module **Database Engine Relational PostgreSQL**. Các ví dụ dùng một schema lab riêng và có thể tự thực hành từ đầu.

## 1. Mục tiêu sau bài học

Sau bài, bạn có thể:

1. Viết đúng cú pháp khối `DECLARE–BEGIN–END` và khối có `EXCEPTION`.
2. Dùng `DO` để chạy một khối PL/pgSQL mà không cần lưu function.
3. Khai báo biến, hằng, kiểu `%TYPE`, `%ROWTYPE` và `RECORD`.
4. Phân biệt thứ tự thực thi phần khai báo, phần lệnh và phần bắt lỗi.
5. Dùng nhãn khối (`label`), khối lồng nhau và phạm vi biến để tránh nhầm tên.
6. Truy vấn dữ liệu vào biến bằng `SELECT ... INTO`, xử lý `STRICT`.
7. Dùng `IF`, vòng lặp, `PERFORM`, `FOUND` và `GET DIAGNOSTICS` trong block.
8. Bắt lỗi cụ thể như `unique_violation`, `no_data_found`, `division_by_zero`.
9. Đọc `SQLSTATE`, `SQLERRM` và `GET STACKED DIAGNOSTICS`.
10. Hiểu **cái gì được rollback** và **cái gì còn giữ** sau một exception handler.
11. Biết khi nào nên bắt lỗi, khi nào phải `RAISE;` để truyền lỗi lên caller.
12. Tránh nhầm ranh giới block với transaction, savepoint và procedure có `COMMIT`.
13. Viết logic nhiều bước bảo vệ tính nhất quán thay vì nuốt lỗi vô điều kiện.
14. Nhận diện tác động hiệu năng và concurrency của các khối có `EXCEPTION`.

## 2. Một khối PL/pgSQL tối thiểu

Ví dụ một block ẩn danh:

~~~sql
DO $do$
BEGIN
    RAISE NOTICE 'Hello from a PL/pgSQL block';
END;
$do$;
~~~

Dòng ý nghĩa:

- `DO` gửi một khối PL/pgSQL để thực thi **một lần**.
- `$do$...$do$` là **dollar-quoted string** chứa phần thân.
- `BEGIN` bắt đầu các câu lệnh của PL/pgSQL.
- `RAISE NOTICE` in thông điệp mức NOTICE tới client/log theo cấu hình.
- `END;` kết thúc khối.
- Dấu `;` sau `$do$` kết thúc **câu SQL DO**.

Đây là **một statement SQL DO**, bên trong chứa **một block PL/pgSQL**.

### Dollar-quote khác dấu nháy đơn

Có thể dùng `$$ ... $$` hoặc một tag như `$do$ ... $do$`. Tag giúp tránh xung đột với những chuỗi dollar-quote khác trong nội dung.

~~~sql
DO $block$
BEGIN
    RAISE NOTICE 'An apostrophe: it''s valid SQL quoting';
END;
$block$;
~~~

Dấu nháy đơn ở thông điệp `it''s` là escape trong SQL string. Dollar-quote chỉ tránh phải escape **toàn thân hàm/khối** như một chuỗi SQL nháy đơn lớn; nó không tự thay mọi quy tắc viết SQL string bên trong.

## 3. Sơ đồ một block đầy đủ

~~~mermaid
flowchart TD
    A["Đi vào block"] --> D["DECLARE: tạo biến, tính giá trị khởi tạo"]
    D --> B["BEGIN: chạy statements theo thứ tự"]
    B --> C{"Có lỗi trong phần được bảo vệ?"}
    C -->|"Không"| E["Bỏ qua EXCEPTION"]
    C -->|"Có, khớp handler"| R["Rollback thay đổi DB trong protected block"]
    R --> H["EXCEPTION: chạy handler"]
    C -->|"Có, không khớp"| U["Truyền lỗi lên block/caller bên ngoài"]
    H --> F["END: rời block"]
    E --> F
~~~

**`DECLARE` và `EXCEPTION` đều tùy chọn.** `BEGIN` và `END` là phần bắt buộc trong cấu trúc block chuẩn.

### Ví dụ có đầy đủ thành phần

~~~sql
DO $do$
DECLARE
    v_numerator numeric := 10;
    v_denominator numeric := 2;
    v_result numeric;
BEGIN
    v_result := v_numerator / v_denominator;

    RAISE NOTICE 'Result = %', v_result;
EXCEPTION
    WHEN division_by_zero THEN
        RAISE NOTICE 'Cannot divide by zero';
END;
$do$;
~~~

Với `v_denominator = 2`, không có lỗi; handler bị bỏ qua. Nếu đổi thành `0`, `division_by_zero` được bắt và thông điệp tương ứng được phát ra.

### Thứ tự các nhánh

Một block có nhiều `WHEN` sẽ xét các điều kiện lỗi được khai báo theo thứ tự. Khi handler phù hợp được chọn, PostgreSQL chạy handler đó; không tự chạy tiếp tất cả các nhánh `WHEN` còn lại.

## 4. DECLARE là phần khai báo, không phải câu SQL DECLARE cursor

Trong PL/pgSQL:

~~~sql
DECLARE
    v_count integer := 0;
    v_name text;
    v_active boolean DEFAULT true;
~~~

là phần khai báo biến thuộc block.

Trong SQL thuần có câu `DECLARE` dùng để khai báo cursor theo ngữ cảnh riêng; **đừng nhầm hai cú pháp**.

### Không viết DECLARE sau khi đã vào BEGIN

Sai:

~~~sql
DO $do$
BEGIN
    -- CỐ Ý SAI về cú pháp block:
    DECLARE v_total integer := 0;
END;
$do$;
~~~

Đúng là đưa declarations lên trước `BEGIN`, hoặc mở **một block lồng** có `DECLARE` riêng:

~~~sql
DO $do$
BEGIN
    RAISE NOTICE 'Outer block';

    DECLARE
        v_total integer := 0;
    BEGIN
        v_total := v_total + 1;
        RAISE NOTICE 'Inner total = %', v_total;
    END;
END;
$do$;
~~~

Khối lồng hợp lệ bên trong phần statements của khối ngoài.

## 5. Cú pháp khai báo biến

Mẫu:

~~~sql
variable_name [CONSTANT] data_type
    [COLLATE collation_name]
    [NOT NULL]
    [{ DEFAULT | := | = } expression];
~~~

Ví dụ thực dụng:

~~~sql
DO $do$
DECLARE
    v_id bigint := 1001;
    v_customer_name text DEFAULT 'Lan';
    v_amount numeric(12,2) := 125.50;
    v_active boolean := true;
    v_created_at timestamptz := clock_timestamp();
    v_note text;
BEGIN
    RAISE NOTICE 'id=%, name=%, amount=%, active=%',
        v_id, v_customer_name, v_amount, v_active;
    RAISE NOTICE 'created_at=%, note=%',
        v_created_at, v_note;
END;
$do$;
~~~

`v_note` không có khởi tạo nên mặc định là SQL `NULL`, nếu không có ràng buộc/khai báo đặc biệt.

### Dùng tên biến dễ nhận diện

Một quy ước hữu ích:

- `p_` cho tham số function/procedure.
- `v_` cho biến local.
- `r_` cho record.
- `c_` cho hằng.

Đây là quy ước đặt tên trong bài, không phải yêu cầu cú pháp PostgreSQL.

## 6. Phân biệt :=, DEFAULT và = trong DECLARE

Trong khai báo PL/pgSQL, các cú pháp sau có thể dùng để chỉ giá trị khởi tạo:

~~~sql
DO $do$
DECLARE
    v_a integer := 10;
    v_b integer DEFAULT 10;
    v_c integer = 10;
BEGIN
    RAISE NOTICE 'a=%, b=%, c=%', v_a, v_b, v_c;
END;
$do$;
~~~

Cả ba biến được khởi tạo bằng 10.

Tuy nhiên khi **gán biến trong phần statements**, dùng `:=` hoặc `=` theo cú pháp PL/pgSQL phù hợp:

~~~sql
v_a := v_a + 1;
~~~

Đừng nhầm toán tử gán biến trong PL/pgSQL với `UPDATE ... SET column = expression` của SQL hoặc với phép so sánh `=` trong một biểu thức điều kiện.

## 7. Khai báo hằng bằng CONSTANT

~~~sql
DO $do$
DECLARE
    c_tax_rate numeric CONSTANT := 0.10;
    v_price numeric(12,2) := 200.00;
    v_total numeric(12,2);
BEGIN
    v_total := v_price * (1 + c_tax_rate);

    RAISE NOTICE 'Total = %', v_total;
END;
$do$;
~~~

`CONSTANT` là biến không được gán lại sau khởi tạo trong block.

Ví dụ cố ý sai:

~~~sql
DO $do$
DECLARE
    c_tax_rate numeric CONSTANT := 0.10;
BEGIN
    -- CỐ Ý SAI: không được gán lại CONSTANT.
    c_tax_rate := 0.12;
END;
$do$;
~~~

Hằng giúp diễn đạt một giá trị cố định trong logic function. Với chính sách nghiệp vụ thường xuyên thay đổi, nên cân nhắc bảng cấu hình có version thay vì hard-code trong nhiều function.

## 8. NOT NULL và giá trị khởi tạo

PL/pgSQL cho phép khai báo biến với `NOT NULL`:

~~~sql
DO $do$
DECLARE
    v_attempt integer NOT NULL := 0;
BEGIN
    v_attempt := v_attempt + 1;
    RAISE NOTICE 'Attempt = %', v_attempt;
END;
$do$;
~~~

Nếu khai báo biến `NOT NULL` mà giá trị khởi tạo là NULL hoặc sau đó gán NULL, hệ thống báo lỗi theo quy tắc PL/pgSQL.

### Khởi tạo không phải chỉ chạy một lần cho toàn connection

Khi một block được **đi vào**, biểu thức khởi tạo biến trong `DECLARE` được đánh giá theo quy tắc PL/pgSQL. Một block lồng trong vòng lặp có thể được đi vào nhiều lần; biến local của block ấy được khởi tạo cho mỗi lần vào block.

~~~sql
DO $do$
DECLARE
    v_i integer;
BEGIN
    FOR v_i IN 1..3 LOOP
        DECLARE
            v_counter integer := 0;
        BEGIN
            v_counter := v_counter + 1;
            RAISE NOTICE 'Iteration %, inner counter %',
                v_i, v_counter;
        END;
    END LOOP;
END;
$do$;
~~~

`v_counter` được tạo/khởi tạo lại khi đi vào inner block, nên có thể in 1 ở mỗi vòng, không tự tích lũy thành 3.

## 9. Khai báo biến dựa vào kiểu cột với %TYPE

Khi một cột bảng có kiểu `numeric(12,2)`, biến liên quan có thể khai báo theo kiểu của cột thay vì sao chép thủ công.

Ví dụ giả định có bảng `plpgsql_lab.accounts`:

~~~sql
DECLARE
    v_balance plpgsql_lab.accounts.balance%TYPE;
~~~

`%TYPE` tham chiếu kiểu dữ liệu của cột hoặc biến theo cơ chế PL/pgSQL. Điều này hữu ích khi schema thay đổi và muốn logic bám theo kiểu đã khai báo.

### Lưu ý

- `%TYPE` nói về **kiểu dữ liệu**, không tự mang ý nghĩa của mọi ràng buộc/trigger của table.
- Khi code phụ thuộc precision hoặc casts, vẫn phải kiểm thử schema migration.
- Đừng dùng `%TYPE` từ một bảng chưa được tạo ở thời điểm tạo function: function có thể cần quan hệ đó tồn tại để resolve declaration.

Phần lab sau sẽ tạo bảng trước khi dùng `%TYPE`.

## 10. %ROWTYPE và RECORD

Hai cách biểu diễn một hàng:

~~~sql
DECLARE
    v_account plpgsql_lab.accounts%ROWTYPE;
    r_any record;
~~~

**`%ROWTYPE`** gắn với cấu trúc hàng của một relation đã biết.

**`RECORD`** linh hoạt; cấu trúc trường được xác định theo bản ghi được gán từ một query phù hợp.

Ví dụ sau khi đã tạo bảng lab:

~~~sql
DO $do$
DECLARE
    v_account plpgsql_lab.accounts%ROWTYPE;
    r_summary record;
BEGIN
    SELECT a.*
    INTO STRICT v_account
    FROM plpgsql_lab.accounts AS a
    WHERE a.account_id = 1;

    SELECT
        COUNT(*) AS account_count,
        SUM(balance) AS total_balance
    INTO r_summary
    FROM plpgsql_lab.accounts;

    RAISE NOTICE 'Owner=%, balance=%',
        v_account.owner_name, v_account.balance;

    RAISE NOTICE 'Accounts=%, total=%',
        r_summary.account_count, r_summary.total_balance;
END;
$do$;
~~~

`%ROWTYPE` giúp truy cập trường được biết theo schema. `RECORD` hữu ích khi kết quả có nhiều cột tính toán, nhưng rủi ro lỗi field name/type chỉ xuất hiện lúc chạy cao hơn nếu cấu trúc chưa được gán đúng.

## 11. BEGIN ... END là block, không phải transaction

Đây là phân biệt quan trọng nhất của bài:

| Cú pháp | Ngữ cảnh | Ý nghĩa |
| --- | --- | --- |
| `BEGIN ... END;` | PL/pgSQL | Giới hạn **khối lệnh** |
| `BEGIN;` | SQL bên ngoài PL/pgSQL | Bắt đầu **transaction SQL** |
| `COMMIT;` | SQL transaction | Xác nhận transaction |
| `ROLLBACK;` | SQL transaction | Hủy transaction |
| `EXCEPTION WHEN ...` | PL/pgSQL block | Bắt lỗi trong block, có rollback nội bộ phần được bảo vệ |

Ví dụ chạy SQL bên ngoài:

~~~sql
BEGIN; -- SQL transaction, không phải khối PL/pgSQL.

DO $do$
BEGIN
    RAISE NOTICE 'Inside a PL/pgSQL block';
END;
$do$;

ROLLBACK; -- Kết thúc/hủy SQL transaction.
~~~

`END;` bên trong `DO` **không commit** transaction. Nếu DO thực hiện thay đổi dữ liệu trong SQL transaction bên ngoài, những thay đổi ấy vẫn tuân theo `COMMIT`/`ROLLBACK` của transaction.

### Tại sao tên BEGIN trùng nhau?

Hai ngữ cảnh cú pháp khác nhau dùng cùng một từ khóa. PostgreSQL biết đang parse SQL statement hay phần thân PL/pgSQL. Đừng đọc code theo quy tắc “thấy BEGIN là có transaction mới”.

## 12. Hàm PL/pgSQL cũng là một block

Tạo một function đơn giản:

~~~sql
CREATE OR REPLACE FUNCTION plpgsql_lab.add_tax(
    p_price numeric,
    p_rate numeric
)
RETURNS numeric
LANGUAGE plpgsql
AS $fn$
DECLARE
    v_total numeric;
BEGIN
    IF p_price IS NULL OR p_rate IS NULL THEN
        RETURN NULL;
    END IF;

    v_total := p_price * (1 + p_rate);

    RETURN v_total;
END;
$fn$;
~~~

Gọi:

~~~sql
SELECT plpgsql_lab.add_tax(100.00, 0.10);
~~~

Kết quả là 110 theo phép tính numeric.

### Điểm khác giữa DO và function

- `DO` chạy block một lần, không khai báo kiểu giá trị trả về cho caller.
- `FUNCTION` có chữ ký, tên, tham số và `RETURNS`.
- Function kiểu `RETURNS numeric` cần trả giá trị phù hợp qua `RETURN` trên các đường đi cần thiết.
- Function có thể gọi từ SQL theo quy tắc loại hàm và volatility/side effect.
- Function không được tự ý dùng SQL `COMMIT`/`ROLLBACK` để điều khiển transaction mà caller đang quản lý.

Khai báo trong `DECLARE` của function vẫn là biến local, không phải cột table hay session variable.

## 13. Thực hành lab: tài khoản và nhật ký

Từ đây các ví dụ dùng dữ liệu cụ thể. Chỉ chạy trong database lab riêng.

**Cảnh báo:** `DROP SCHEMA IF EXISTS plpgsql_lab CASCADE` xóa toàn bộ đối tượng trong schema `plpgsql_lab`. Không dùng lệnh này trên production.

~~~sql
-- CHỈ CHẠY TRÊN DATABASE THỰC HÀNH.
DROP SCHEMA IF EXISTS plpgsql_lab CASCADE;

CREATE SCHEMA plpgsql_lab;

CREATE TABLE plpgsql_lab.accounts (
    account_id integer PRIMARY KEY,
    owner_name text NOT NULL UNIQUE,
    balance numeric(14,2) NOT NULL
        CHECK (balance >= 0),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE plpgsql_lab.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_key text NOT NULL UNIQUE,
    detail text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE plpgsql_lab.transfers (
    transfer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    from_account integer NOT NULL
        REFERENCES plpgsql_lab.accounts(account_id),
    to_account integer NOT NULL
        REFERENCES plpgsql_lab.accounts(account_id),
    amount numeric(14,2) NOT NULL CHECK (amount > 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO plpgsql_lab.accounts (
    account_id, owner_name, balance
)
VALUES
    (1, 'Lan', 1000.00),
    (2, 'Minh',  500.00),
    (3, 'Hoa',  250.00);

INSERT INTO plpgsql_lab.events (
    event_key, detail
)
VALUES ('existing-event', 'Used to test unique violation');
~~~

Mọi ví dụ thay đổi tiền/sự kiện về sau được bọc SQL transaction và `ROLLBACK` nếu chỉ nhằm quan sát hành vi.

### Kiểm tra trạng thái ban đầu

~~~sql
SELECT account_id, owner_name, balance
FROM plpgsql_lab.accounts
ORDER BY account_id;

SELECT event_key, detail
FROM plpgsql_lab.events
ORDER BY event_id;
~~~

Tài khoản Lan có 1000.00, Minh 500.00 và Hoa 250.00. Bảng events đã có key `existing-event` để làm nguồn lỗi unique.

## 14. Đọc cột vào biến bằng SELECT ... INTO

Trong PL/pgSQL, `SELECT ... INTO variable` gán kết quả query vào biến:

~~~sql
DO $do$
DECLARE
    v_balance numeric(14,2);
BEGIN
    SELECT a.balance
    INTO v_balance
    FROM plpgsql_lab.accounts AS a
    WHERE a.account_id = 1;

    RAISE NOTICE 'Balance = %', v_balance;
END;
$do$;
~~~

**Không nhầm:** `SELECT ... INTO` bên trong PL/pgSQL là cách gán vào biến, không phải cú pháp SQL thông thường tạo bảng bằng `SELECT INTO new_table`. Để tạo bảng trong SQL hiện đại, dùng `CREATE TABLE ... AS SELECT ...`.

### Query không trả hàng

Nếu không có `STRICT`, một câu `SELECT ... INTO` không có hàng sẽ làm target nhận NULL theo quy tắc phù hợp, và biến `FOUND` thường thành false.

~~~sql
DO $do$
DECLARE
    v_balance numeric(14,2);
BEGIN
    SELECT a.balance
    INTO v_balance
    FROM plpgsql_lab.accounts AS a
    WHERE a.account_id = -1;

    IF NOT FOUND THEN
        RAISE NOTICE 'No account found';
    END IF;
END;
$do$;
~~~

### Query trả nhiều hàng

Nếu không `STRICT`, `SELECT ... INTO` thường lấy một hàng đầu theo kế hoạch và bỏ qua phần còn lại. Không nên dựa vào việc “hàng đầu” ổn định nếu không có `ORDER BY` rõ ràng.

## 15. SELECT INTO STRICT: kỳ vọng chính xác một hàng

~~~sql
DO $do$
DECLARE
    v_balance numeric(14,2);
BEGIN
    SELECT a.balance
    INTO STRICT v_balance
    FROM plpgsql_lab.accounts AS a
    WHERE a.account_id = 1;

    RAISE NOTICE 'Exact balance = %', v_balance;
END;
$do$;
~~~

Khi dùng `STRICT`:

- **Không có hàng** → `NO_DATA_FOUND`.
- **Nhiều hơn một hàng** → `TOO_MANY_ROWS`.
- **Chính xác một hàng** → gán biến.

Ví dụ bắt lỗi thiếu hàng:

~~~sql
DO $do$
DECLARE
    v_balance numeric(14,2);
BEGIN
    BEGIN
        SELECT a.balance
        INTO STRICT v_balance
        FROM plpgsql_lab.accounts AS a
        WHERE a.account_id = -1;
    EXCEPTION
        WHEN no_data_found THEN
            RAISE NOTICE 'Account does not exist';
    END;
END;
$do$;
~~~

### Tại sao STRICT quan trọng?

Khi nghiệp vụ yêu cầu **đúng một bản ghi**, việc âm thầm nhận NULL hoặc lấy một hàng bất kỳ có thể che dữ liệu bất thường. Dùng `STRICT` khi chính sách yêu cầu đúng một hàng và có cách xử lý rõ ràng cho missing/duplicate.

## 16. PERFORM và FOUND khi không cần giá trị trả về

Trong PL/pgSQL, nếu muốn thực thi một SQL query nhưng **không dùng kết quả**, dùng `PERFORM`:

~~~sql
DO $do$
BEGIN
    PERFORM 1
    FROM plpgsql_lab.accounts AS a
    WHERE a.account_id = 2;

    IF FOUND THEN
        RAISE NOTICE 'Account 2 exists';
    ELSE
        RAISE NOTICE 'Account 2 not found';
    END IF;
END;
$do$;
~~~

`FOUND` là biến trạng thái boolean do PL/pgSQL quản lý cho các câu lệnh nhất định như `SELECT INTO`, `PERFORM` và nhiều thao tác DML.

### Không dùng FOUND từ quá lâu trước đó

Sau những câu lệnh khác có khả năng cập nhật `FOUND`, giá trị của nó không nhất thiết còn mô tả statement bạn quan tâm ban đầu.

Ví dụ:

~~~sql
DO $do$
BEGIN
    PERFORM 1
    FROM plpgsql_lab.accounts
    WHERE account_id = 999;

    IF NOT FOUND THEN
        RAISE NOTICE 'Account not found';
    END IF;
END;
$do$;
~~~

Kiểm tra `FOUND` ngay sau câu lệnh liên quan sẽ dễ đọc và ít sai hơn.

## 17. GET DIAGNOSTICS và ROW_COUNT

Đôi khi cần biết bao nhiêu hàng đã bị tác động bởi một statement, dùng:

~~~sql
GET DIAGNOSTICS variable_name = ROW_COUNT;
~~~

Ví dụ:

~~~sql
BEGIN; -- SQL transaction cho lab.

DO $do$
DECLARE
    v_rows bigint;
BEGIN
    UPDATE plpgsql_lab.accounts AS a
    SET updated_at = clock_timestamp()
    WHERE a.account_id IN (1, 2);

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    RAISE NOTICE 'Updated rows = %', v_rows;
END;
$do$;

ROLLBACK;
~~~

Kết quả kỳ vọng là 2 nếu dữ liệu lab vẫn có tài khoản 1 và 2.

### Phân biệt hai loại diagnostics

- `GET DIAGNOSTICS ... ROW_COUNT`: lấy thông tin trạng thái thực thi statement liên quan.
- `GET STACKED DIAGNOSTICS`: dùng trong **exception handler** để lấy thông tin của lỗi hiện đang được xử lý.

Chúng không phải một câu lệnh thay thế cho nhau.

## 18. IF, LOOP và RETURN là câu lệnh bên trong BEGIN

`BEGIN` chứa các statement. Những cấu trúc rẽ nhánh có `END IF;` và vòng lặp có `END LOOP;` riêng.

~~~sql
DO $do$
DECLARE
    v_i integer;
    v_sum integer := 0;
BEGIN
    FOR v_i IN 1..5 LOOP
        IF v_i % 2 = 0 THEN
            v_sum := v_sum + v_i;
        END IF;
    END LOOP;

    RAISE NOTICE 'Sum of even numbers = %', v_sum;
END;
$do$;
~~~

Ở đây:

- `END IF;` đóng câu IF.
- `END LOOP;` đóng câu FOR LOOP.
- `END;` cuối cùng đóng khối PL/pgSQL ngoài.

**Đừng dùng `END;` để đóng `IF`**, vì sẽ làm sai cấu trúc cú pháp.

## 19. Block lồng nhau và phạm vi biến

PL/pgSQL cho phép tạo nhiều block lồng nhau:

~~~sql
DO $do$
DECLARE
    v_outer integer := 100;
BEGIN
    RAISE NOTICE 'Outer = %', v_outer;

    DECLARE
        v_inner integer := 20;
    BEGIN
        RAISE NOTICE 'Outer + inner = %',
            v_outer + v_inner;
    END;

    RAISE NOTICE 'Outer still = %', v_outer;
END;
$do$;
~~~

Biến `v_outer` của block ngoài có thể được truy cập từ block trong nếu không bị shadow. Biến `v_inner` chỉ thuộc phạm vi block trong, không còn truy cập hợp lệ khi block đó đã kết thúc.

### Phân biệt scope và transaction

Kết thúc block trong **không commit transaction**. Nó chỉ kết thúc phạm vi biến/câu lệnh của block đó; những thay đổi database vẫn thuộc SQL transaction đang chạy.

## 20. Shadowing: biến trong che biến ngoài

~~~sql
DO $do$
DECLARE
    v_status text := 'outer';
BEGIN
    DECLARE
        v_status text := 'inner';
    BEGIN
        RAISE NOTICE 'Inner status = %', v_status;
    END;

    RAISE NOTICE 'Outer status = %', v_status;
END;
$do$;
~~~

Trong block trong, tên `v_status` gần nhất là biến inner; nó **che** tên cùng dạng ở outer.

Việc shadowing đôi khi hữu ích nhưng có thể khiến một function dài khó đọc, đặc biệt khi dùng tên biến giống tên cột SQL.

### Quy tắc thiết kế

- Dùng tên biến rõ nghĩa thay vì cố tình lặp tên.
- Tránh biến local có tên giống cột table nếu không cần.
- Dùng table alias để chỉ rõ cột SQL.
- Có thể dùng nhãn khối nếu thật sự cần tham chiếu biến outer bị shadow.

## 21. Nhãn khối với <<label>> ... END label

Một block có thể có nhãn:

~~~sql
DO $do$
<<outer_block>>
DECLARE
    v_status text := 'outer';
BEGIN
    <<inner_block>>
    DECLARE
        v_status text := 'inner';
    BEGIN
        RAISE NOTICE 'Inside: %', v_status;
        RAISE NOTICE 'Outer qualified: %',
            outer_block.v_status;
    END inner_block;
END outer_block;
$do$;
~~~

Ý nghĩa:

- `<<outer_block>>` khai báo nhãn outer.
- `<<inner_block>>` khai báo nhãn inner.
- `outer_block.v_status` truy cập biến outer dù tên bị che.
- `END inner_block;` và `END outer_block;` kết thúc block tương ứng.

### Nhãn không phải object schema

`outer_block.v_status` là cú pháp phân giải tên trong ngữ cảnh PL/pgSQL, không phải tham chiếu tới một bảng `outer_block`.

Đặt nhãn đúng có thể giúp đọc code nhiều block lồng nhau, nhưng **không bắt buộc** cho mọi block đơn giản.

## 22. Tránh tên biến trùng tên cột SQL

Ví dụ dễ gây nhầm:

~~~sql
-- Minh họa lỗi thiết kế tên:
DECLARE
    balance numeric;
BEGIN
    SELECT balance INTO balance
    FROM plpgsql_lab.accounts;
END;
~~~

Khi một identifier vừa có thể là biến PL/pgSQL vừa là cột SQL, PostgreSQL có quy tắc phân giải xung đột và có thể báo lỗi ambiguous.

Cách rõ ràng hơn:

~~~sql
DO $do$
DECLARE
    v_balance numeric(14,2);
BEGIN
    SELECT a.balance
    INTO v_balance
    FROM plpgsql_lab.accounts AS a
    WHERE a.account_id = 1;

    RAISE NOTICE 'Balance = %', v_balance;
END;
$do$;
~~~

Dùng alias `a` để nhận diện cột và tiền tố `v_` cho biến. Không nên giải quyết mọi xung đột bằng cách bật cấu hình thiên về biến hoặc cột rồi chấp nhận SQL có thể đổi nghĩa khi schema thay đổi.

## 23. EXCEPTION là phần xử lý lỗi tùy chọn

Cấu trúc:

~~~sql
BEGIN
    statements;
EXCEPTION
    WHEN condition_a THEN
        handler_statements;
    WHEN condition_b OR condition_c THEN
        handler_statements;
    WHEN OTHERS THEN
        fallback_statements;
END;
~~~

`EXCEPTION` được khai báo **sau phần câu lệnh chính của block** và **trước `END`**.

### Bắt lỗi cụ thể

~~~sql
DO $do$
BEGIN
    PERFORM 10 / 0;
EXCEPTION
    WHEN division_by_zero THEN
        RAISE NOTICE 'Cannot divide by zero';
END;
$do$;
~~~

Lỗi `division_by_zero` được xử lý trong block.

### EXCEPTION không phải ELSE

Một lỗi chỉ được chuyển vào handler khi có **exception thực sự phát sinh**. Câu `IF ... ELSE` dùng để xử lý nhánh nghiệp vụ thông thường, còn `EXCEPTION` dùng để xử lý tình huống lỗi.

Không sử dụng `EXCEPTION` thay cho một điều kiện `IF` rõ ràng nếu dữ liệu “không thỏa điều kiện” là chuyện xảy ra thường xuyên.

## 24. Tên điều kiện lỗi và SQLSTATE

PostgreSQL định danh lỗi bằng mã `SQLSTATE` gồm năm ký tự. PL/pgSQL hỗ trợ tên điều kiện như `unique_violation`.

| Tên điều kiện | SQLSTATE | Ý nghĩa |
| --- | --- | --- |
| `unique_violation` | 23505 | Vi phạm UNIQUE/PRIMARY KEY |
| `foreign_key_violation` | 23503 | Vi phạm FOREIGN KEY |
| `check_violation` | 23514 | Vi phạm CHECK |
| `not_null_violation` | 23502 | Vi phạm NOT NULL |
| `division_by_zero` | 22012 | Chia cho 0 |
| `invalid_parameter_value` | 22023 | Tham số không hợp lệ |
| `no_data_found` | P0002 | `INTO STRICT` không tìm thấy hàng |
| `too_many_rows` | P0003 | `INTO STRICT` nhận nhiều hàng |
| `raise_exception` | P0001 | RAISE EXCEPTION mặc định |
| `serialization_failure` | 40001 | Transaction cần retry theo chính sách |
| `deadlock_detected` | 40P01 | Phát hiện deadlock |
| `lock_not_available` | 55P03 | Không lấy được lock theo cách được yêu cầu |

Ví dụ dùng SQLSTATE trực tiếp:

~~~sql
DO $do$
BEGIN
    RAISE EXCEPTION 'Intentional error'
        USING ERRCODE = 'P0001';
EXCEPTION
    WHEN SQLSTATE 'P0001' THEN
        RAISE NOTICE 'Caught custom exception';
END;
$do$;
~~~

### Khi nào dùng tên điều kiện?

Tên như `unique_violation` dễ đọc hơn `SQLSTATE '23505'`. Với mã do ứng dụng tự đặt như `P1001`, có thể dùng cú pháp `WHEN SQLSTATE 'P1001'`.

Đừng tự đặt các mã tùy ý rồi giả định mọi client/framework đã hiểu semantics của chúng; cần có hợp đồng lỗi trong ứng dụng.

## 25. Một block có thể có nhiều WHEN

~~~sql
DO $do$
DECLARE
    v_input integer := 0;
BEGIN
    PERFORM 100 / v_input;
EXCEPTION
    WHEN division_by_zero THEN
        RAISE NOTICE 'Specific: cannot divide by zero';
    WHEN invalid_parameter_value THEN
        RAISE NOTICE 'Input parameter is invalid';
    WHEN OTHERS THEN
        RAISE NOTICE 'Unexpected error';
END;
$do$;
~~~

PostgreSQL chọn handler phù hợp.

**Thứ tự và phạm vi handler phải có chủ đích.** Đặt một fallback `WHEN OTHERS` rộng có thể làm mất cơ hội phát hiện bug nếu nó chỉ log rồi im lặng tiếp tục.

### OTHERS không bắt tuyệt đối mọi exception

Trong PL/pgSQL, `OTHERS` không bắt những lỗi đặc biệt như `QUERY_CANCELED` và `ASSERT_FAILURE` theo cách thông thường, dù có thể chỉ định điều kiện riêng khi phù hợp.

Không viết tài liệu khẳng định `WHEN OTHERS` bảo đảm bắt được 100% mọi tình huống hệ thống.

## 26. Khi không có handler phù hợp

Nếu một lỗi xảy ra mà block không có nhánh `WHEN` phù hợp, lỗi được truyền tới **block ngoài hoặc caller**.

~~~sql
DO $do$
BEGIN
    BEGIN
        RAISE EXCEPTION 'Failure'
            USING ERRCODE = 'P1001';
    EXCEPTION
        WHEN division_by_zero THEN
            RAISE NOTICE 'This handler does not match';
    END;
EXCEPTION
    WHEN SQLSTATE 'P1001' THEN
        RAISE NOTICE 'Outer block caught P1001';
END;
$do$;
~~~

Lỗi `P1001` không bị handler `division_by_zero` bắt, nên chuyển lên block ngoài, nơi có handler phù hợp.

### Tại sao cấu trúc này hữu ích?

Nhiều ứng dụng muốn:

- Block trong chịu trách nhiệm nghiệp vụ cụ thể.
- Block ngoài chịu trách nhiệm log, chuyển đổi lỗi hoặc cleanup.
- Caller cuối cùng quyết định rollback/retry/response.

Không cần mọi block đều có `WHEN OTHERS`; **cho lỗi lan truyền** thường là hành vi đúng nếu block hiện tại không biết cách xử lý an toàn.

## 27. EXCEPTION tạo subtransaction nội bộ

Đây là phần quan trọng nhất khi học block.

Khi một block có `EXCEPTION` và lỗi được bắt, PostgreSQL có cơ chế **subtransaction nội bộ** cho phần câu lệnh được bảo vệ:

1. Các statement trong block bắt đầu thực thi.
2. Một statement gây lỗi.
3. Những thay đổi database do phần được bảo vệ của block thực hiện được rollback tới trạng thái ở đầu phần đó.
4. Handler tương ứng chạy.
5. Nếu handler hoàn thành bình thường, chương trình có thể tiếp tục sau block.
6. Những thay đổi trước block ở phạm vi ngoài không nhất thiết bị rollback chỉ vì exception bên trong được bắt.

~~~mermaid
flowchart TD
    O["Outer block: UPDATE A"] --> N["Inner block có EXCEPTION"]
    N --> I["INSERT event temp"]
    I --> X["INSERT event trùng UNIQUE -> lỗi"]
    X --> RB["Rollback thay đổi DB trong inner protected block"]
    RB --> H["Handler unique_violation"]
    H --> C["Tiếp tục outer block"]
    C --> T["SQL transaction quyết định COMMIT/ROLLBACK"]
~~~

**Không hiểu đây là lệnh `SAVEPOINT` do ứng dụng tự gửi**. Đây là cơ chế PL/pgSQL tự quản lý để thực thi exception block. Nó tương tự về ý tưởng rollback cục bộ, nhưng không biến `BEGIN ... EXCEPTION ... END` thành một transaction commit độc lập.

## 28. Thí nghiệm rollback trong inner block

Lab đã có event key `existing-event`. Ta cố tình chèn key này lần nữa.

~~~sql
BEGIN; -- SQL transaction ngoài, chỉ để thử lab.

DO $do$
DECLARE
    v_attempts integer := 0;
BEGIN
    -- Thay đổi ở outer block, trước inner exception block.
    UPDATE plpgsql_lab.accounts
    SET balance = balance + 1
    WHERE account_id = 1;

    BEGIN
        v_attempts := v_attempts + 1;

        -- INSERT thứ nhất sẽ thành công tạm thời.
        INSERT INTO plpgsql_lab.events (
            event_key, detail
        )
        VALUES (
            'temporary-inside',
            'Should disappear after inner rollback'
        );

        -- INSERT thứ hai gây unique_violation.
        INSERT INTO plpgsql_lab.events (
            event_key, detail
        )
        VALUES (
            'existing-event',
            'Intentional duplicate'
        );

    EXCEPTION
        WHEN unique_violation THEN
            RAISE NOTICE
                'Inner duplicate caught; attempts = %',
                v_attempts;
    END;

    RAISE NOTICE 'Outer block continues normally';
END;
$do$;

SELECT account_id, balance
FROM plpgsql_lab.accounts
WHERE account_id = 1;

SELECT event_key, detail
FROM plpgsql_lab.events
ORDER BY event_id;

ROLLBACK; -- Khôi phục seed lab.
~~~

Dự kiến **trước `ROLLBACK` của SQL transaction ngoài**:

- Tài khoản 1 tăng từ 1000.00 lên 1001.00 vì lệnh UPDATE nằm **trước inner block**.
- Event `temporary-inside` **không tồn tại**, vì INSERT đầu tiên trong inner protected block cũng bị rollback khi INSERT thứ hai lỗi.
- Event `existing-event` vẫn là bản seed duy nhất.
- Biến PL/pgSQL `v_attempts` vẫn có giá trị **1** trong handler.

Sau SQL `ROLLBACK` cuối, cả thay đổi outer account cũng được hoàn tác.

### Điều gì không được cam kết rollback?

Các tác động **ngoài transactional database state** như thông điệp NOTICE đã gửi hoặc side effect ngoài PostgreSQL không tự bị “thu hồi”. Sequence/identity có thể đã tăng và không hoàn nguyên số phát sinh, ngay cả khi INSERT bị rollback.

Vì vậy **không lấy khoảng trống của sequence làm bằng chứng transaction đã mất dữ liệu**.

## 29. Biến local không tự quay về giá trị cũ sau exception

Trong ví dụ trước, câu:

~~~sql
v_attempts := v_attempts + 1;
~~~

đã gán biến local bằng 1 trước khi xảy ra lỗi.

Sau khi rollback các thay đổi database trong inner block, giá trị **biến PL/pgSQL** có thể vẫn là giá trị tại thời điểm lỗi. Biến local không phải một row MVCC tự rollback giống bảng.

Ví dụ ngắn:

~~~sql
DO $do$
DECLARE
    v_message text := 'before';
BEGIN
    BEGIN
        v_message := 'changed';

        RAISE EXCEPTION 'Intentional';
    EXCEPTION
        WHEN raise_exception THEN
            RAISE NOTICE 'Value after catch: %',
                v_message;
    END;
END;
$do$;
~~~

Dự kiến in `changed`.

### Hệ quả thiết kế

Nếu một biến `v_total` được tăng trước khi INSERT thất bại, handler không nên mặc định `v_total` tự trở lại số cũ. Nếu nghiệp vụ cần đồng bộ biến với trạng thái database sau rollback, hãy tính lại biến hoặc thiết kế flow rõ ràng.

## 30. Handler chạy sau khi rollback phần được bảo vệ

Khi đã vào `EXCEPTION`, các thay đổi database **trong phần protected block trước lỗi** đã bị rollback theo cơ chế nội bộ.

Sau đó handler có thể thực hiện các statement mới, ví dụ ghi một dòng audit “thao tác thất bại”:

~~~sql
BEGIN;

DO $do$
BEGIN
    BEGIN
        INSERT INTO plpgsql_lab.events (event_key, detail)
        VALUES ('temporary', 'Will be rolled back');

        RAISE EXCEPTION 'Simulated failure';

    EXCEPTION
        WHEN raise_exception THEN
            INSERT INTO plpgsql_lab.events (
                event_key, detail
            )
            VALUES (
                'handler-audit',
                'Recorded after protected statements rolled back'
            );
    END;
END;
$do$;

SELECT event_key
FROM plpgsql_lab.events
WHERE event_key IN ('temporary', 'handler-audit')
ORDER BY event_key;

ROLLBACK;
~~~

Trong SQL transaction trước rollback, `handler-audit` có thể tồn tại còn `temporary` thì không.

**Nhưng handler-audit không tự commit riêng!** Nếu transaction ngoài rollback hoặc handler tiếp tục gây lỗi không được bắt, audit row cũng có thể bị rollback.

### Vì sao không dùng bảng audit để bảo đảm log bất chấp rollback?

Một INSERT thông thường vào bảng audit cùng transaction không bảo đảm ghi audit bền vững nếu caller rollback. Nếu cần ghi nhận lỗi ngay cả khi transaction thất bại, hãy thiết kế logging/outbox/monitoring với semantics phù hợp, không dựa vào `EXCEPTION` như một “autonomous transaction” mặc định.

## 31. EXCEPTION handler không chạy lại phần BEGIN

Khi một handler bắt lỗi, PostgreSQL **không tự nhảy trở lại đầu block** để chạy các statements còn lại.

~~~sql
DO $do$
BEGIN
    RAISE NOTICE 'Before error';

    RAISE EXCEPTION 'Stop here';

    RAISE NOTICE 'This will not be executed';

EXCEPTION
    WHEN raise_exception THEN
        RAISE NOTICE 'Caught at handler';
END;
$do$;
~~~

Dòng NOTICE sau câu `RAISE EXCEPTION` trong protected statements không được chạy.

Muốn retry, cần viết một vòng lặp/retry policy có giới hạn một cách rõ ràng, thường ở mức **toàn transaction** cho lỗi concurrency. Không có “auto retry” mặc định từ `WHEN`.

## 32. SQLSTATE và SQLERRM bên trong handler

Trong handler có thể dùng hai giá trị đặc biệt:

- `SQLSTATE`: mã lỗi 5 ký tự.
- `SQLERRM`: thông điệp lỗi.

~~~sql
DO $do$
BEGIN
    RAISE EXCEPTION 'Demonstration failure'
        USING ERRCODE = 'P0001';

EXCEPTION
    WHEN SQLSTATE 'P0001' THEN
        RAISE NOTICE 'SQLSTATE = %', SQLSTATE;
        RAISE NOTICE 'SQLERRM = %', SQLERRM;
END;
$do$;
~~~

### Phạm vi sử dụng

`SQLSTATE` và `SQLERRM` trong PL/pgSQL được dùng trong exception handler để xem lỗi đang xử lý. Đừng kỳ vọng những giá trị đó luôn có ý nghĩa trong một đoạn code bình thường không ở handler.

Nếu cần đưa thông tin lỗi ra ngoài hàm hoặc đưa vào bảng, nên lấy thông tin trong handler rồi lưu vào biến/log có cấu trúc khi phù hợp.

## 33. GET STACKED DIAGNOSTICS: đọc thông tin lỗi chi tiết

`GET STACKED DIAGNOSTICS` cho phép lấy các thuộc tính của lỗi đang được xử lý:

~~~sql
DO $do$
DECLARE
    v_state text;
    v_message text;
    v_detail text;
    v_hint text;
    v_context text;
BEGIN
    RAISE EXCEPTION 'Example validation error'
        USING
            ERRCODE = '22023',
            DETAIL = 'The input did not satisfy the contract',
            HINT = 'Pass a positive amount';

EXCEPTION
    WHEN invalid_parameter_value THEN
        GET STACKED DIAGNOSTICS
            v_state = RETURNED_SQLSTATE,
            v_message = MESSAGE_TEXT,
            v_detail = PG_EXCEPTION_DETAIL,
            v_hint = PG_EXCEPTION_HINT,
            v_context = PG_EXCEPTION_CONTEXT;

        RAISE NOTICE 'State: %, Message: %',
            v_state, v_message;
        RAISE NOTICE 'Detail: %, Hint: %',
            v_detail, v_hint;
        RAISE NOTICE 'Context: %', v_context;
END;
$do$;
~~~

Những mục hữu ích:

| Trường diagnostics | Ý nghĩa |
| --- | --- |
| `RETURNED_SQLSTATE` | Mã SQLSTATE |
| `MESSAGE_TEXT` | Thông điệp lỗi chính |
| `PG_EXCEPTION_DETAIL` | Nội dung DETAIL nếu có |
| `PG_EXCEPTION_HINT` | HINT nếu có |
| `PG_EXCEPTION_CONTEXT` | Context/call stack của lỗi |
| `CONSTRAINT_NAME` | Tên constraint khi lỗi cung cấp |
| `TABLE_NAME` | Tên bảng liên quan nếu có |
| `SCHEMA_NAME` | Schema liên quan nếu có |
| `COLUMN_NAME` | Cột liên quan nếu có |

Không phải loại lỗi nào cũng điền tất cả trường. Với lỗi không có detail/constraint, trường tương ứng có thể rỗng theo cách PostgreSQL trả lại.

**Không gửi nguyên exception diagnostics chứa dữ liệu nhạy cảm tới người dùng cuối**. Thông điệp, query context hoặc tên object có thể lộ thông tin cấu trúc database. Log nội bộ theo chính sách và trả error contract an toàn.

## 34. Bắt UNIQUE violation trong lab

Bảng events có UNIQUE constraint trên `event_key`.

~~~sql
DO $do$
DECLARE
    v_constraint text;
    v_state text;
    v_message text;
BEGIN
    INSERT INTO plpgsql_lab.events (
        event_key, detail
    )
    VALUES (
        'existing-event',
        'Intentional duplicate'
    );

EXCEPTION
    WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS
            v_constraint = CONSTRAINT_NAME,
            v_state = RETURNED_SQLSTATE,
            v_message = MESSAGE_TEXT;

        RAISE NOTICE 'State %, constraint %, message %',
            v_state, v_constraint, v_message;
END;
$do$;
~~~

Với dữ liệu seed, câu INSERT gặp SQLSTATE `23505`, handler chạy.

### Có nên bắt tất cả unique_violation?

Không phải lúc nào. Nếu function xử lý một nghiệp vụ nhiều bảng, lỗi UNIQUE có thể xuất hiện từ **constraint khác** với constraint bạn mong chờ. Bắt `unique_violation` rồi luôn coi là “event trùng bình thường” có thể che bug.

Khi xử lý trường hợp rất cụ thể, nên:

- Xem `CONSTRAINT_NAME` khi đáng tin và phù hợp.
- Chỉ bắt quanh câu lệnh cần thiết trong inner block hẹp.
- Rethrow nếu constraint/lỗi không nằm trong tập hợp mong đợi.
- Dùng `INSERT ... ON CONFLICT` khi duplicate là nhánh nghiệp vụ thường gặp và phù hợp semantics.

## 35. RAISE: NOTICE, WARNING và EXCEPTION

`RAISE` có nhiều mức:

~~~sql
DO $do$
BEGIN
    RAISE DEBUG 'Debug detail';
    RAISE LOG 'Log message';
    RAISE INFO 'Information';
    RAISE NOTICE 'Notice';
    RAISE WARNING 'Warning';
END;
$do$;
~~~

Mức độ thông điệp hiển thị/log phụ thuộc client/server settings.

### RAISE EXCEPTION

~~~sql
DO $do$
DECLARE
    v_amount numeric := -10;
BEGIN
    IF v_amount <= 0 THEN
        RAISE EXCEPTION 'Amount must be positive: %',
            v_amount
            USING ERRCODE = '22023';
    END IF;
END;
$do$;
~~~

Câu này **cố ý gây lỗi** khi chạy ngoài handler và có thể làm transaction SQL đang mở chuyển sang trạng thái aborted cho đến khi rollback phù hợp.

### Chọn thông điệp có cấu trúc

Ưu tiên:

- SQLSTATE phù hợp.
- Message rõ ràng, không lộ dữ liệu nhạy cảm.
- DETAIL/HINT khi hỗ trợ vận hành.
- Context do database sinh ra để log ở nơi phù hợp.

Đừng lạm dụng `RAISE NOTICE` để thay hệ thống observability. Nó chủ yếu hữu ích khi debug/lab hoặc truyền thông điệp ở mức đã thiết kế.

## 36. RAISE; để truyền lại chính lỗi đang xử lý

Nếu handler chỉ muốn ghi log rồi chuyển lỗi lên caller, dùng `RAISE;` **không có tham số** trong handler:

~~~sql
DO $do$
BEGIN
    BEGIN
        RAISE EXCEPTION 'Original failure'
            USING ERRCODE = 'P1001';

    EXCEPTION
        WHEN SQLSTATE 'P1001' THEN
            RAISE NOTICE 'Inner handler observed P1001';
            RAISE; -- Rethrow original exception.
    END;

EXCEPTION
    WHEN SQLSTATE 'P1001' THEN
        RAISE NOTICE 'Outer handler caught rethrown P1001';
END;
$do$;
~~~

`RAISE;` giữ nguyên lỗi gốc đang được xử lý theo semantics PL/pgSQL. Nó tốt hơn việc tự dựng lại một message nếu muốn caller thấy SQLSTATE/context gốc.

### Khi nào nên rethrow?

- Không chắc lỗi đã được xử lý an toàn.
- Chỉ muốn ghi nhận rồi để transaction rollback.
- Handler thấy constraint name/SQLSTATE không thuộc trường hợp dự kiến.
- Caller cần quyết định retry hoặc trả response thích hợp.

**Nuốt lỗi không có nghĩa nghiệp vụ đã thành công.**

## 37. Lỗi xảy ra bên trong chính handler

Một điểm quan trọng về cấu trúc:

> Handler của một block không tự bắt tiếp những exception phát sinh ngay trong các statement thuộc **chính handler đó**.

Ví dụ:

~~~sql
DO $do$
BEGIN
    BEGIN
        RAISE EXCEPTION 'First error'
            USING ERRCODE = 'P1001';

    EXCEPTION
        WHEN SQLSTATE 'P1001' THEN
            RAISE EXCEPTION 'Second error inside handler'
                USING ERRCODE = 'P1002';
    END;

EXCEPTION
    WHEN SQLSTATE 'P1002' THEN
        RAISE NOTICE 'Outer block caught handler failure';
END;
$do$;
~~~

Để bắt lỗi phát sinh từ handler, cần một block bao ngoài hoặc một inner block phù hợp. Đừng nghĩ `WHEN OTHERS` đặt cùng danh sách handler sẽ “bắt lần hai” bất kỳ lỗi nào trong handler trước.

## 38. Handler đặt hẹp hay rộng?

So sánh hai thiết kế.

**Rộng, dễ che lỗi:**

~~~sql
BEGIN
    -- Nhiều thao tác trên các bảng khác nhau.
    ...
EXCEPTION
    WHEN unique_violation THEN
        RAISE NOTICE 'Duplicate, ignore';
END;
~~~

Nếu UNIQUE bị vi phạm ở một bảng không dự kiến, handler này vẫn có thể nuốt lỗi.

**Hẹp, dễ kiểm soát:**

~~~sql
BEGIN
    -- Chỉ thao tác insert mà duplicate là trường hợp dự kiến.
    INSERT INTO plpgsql_lab.events (
        event_key, detail
    )
    VALUES ('existing-event', 'demo');

EXCEPTION
    WHEN unique_violation THEN
        RAISE NOTICE 'Duplicate event key';
END;
~~~

Vẫn cần chắc lỗi thuộc constraint mong muốn. Với duplicate thông thường, cú pháp `ON CONFLICT` có thể rõ và rẻ hơn:

~~~sql
INSERT INTO plpgsql_lab.events (
    event_key, detail
)
VALUES (
    'existing-event',
    'idempotent attempt'
)
ON CONFLICT (event_key)
DO NOTHING;
~~~

**Không dùng exception làm điều khiển luồng bình thường khi có lệnh SQL thích hợp hơn.**

## 39. Chi phí của block có EXCEPTION

PL/pgSQL phải thiết lập cơ chế xử lý lỗi/subtransaction cho một block có `EXCEPTION`. Vì vậy vào/ra khối có handler có thể tốn hơn block đơn giản.

Không có nghĩa mọi lần chạy đều chậm rất nhiều, nhưng trong vòng lặp hàng triệu dòng, chi phí có thể đáng kể.

### Anti-pattern

~~~sql
DO $do$
DECLARE
    v_i integer;
BEGIN
    FOR v_i IN 1..1000 LOOP
        BEGIN
            INSERT INTO plpgsql_lab.events (
                event_key, detail
            )
            VALUES ('existing-event', 'duplicate');

        EXCEPTION
            WHEN unique_violation THEN
                NULL; -- Chỉ demo anti-pattern.
        END;
    END LOOP;
END;
$do$;
~~~

Ví dụ **tạo 1000 duplicate errors có chủ đích** và nuốt chúng; không nên chạy để kiểm tra hiệu năng trên production.

Đối với idempotent insert dự kiến có nhiều key trùng, thường cân nhắc `ON CONFLICT DO NOTHING`, batch insert và ghi log phù hợp. Exception handler thích hợp cho trường hợp **lỗi không phổ biến** mà logic có thể xử lý rõ.

## 40. SQL transaction bên ngoài vẫn quyết định COMMIT/ROLLBACK

Ví dụ:

~~~sql
BEGIN; -- SQL transaction.

DO $do$
BEGIN
    UPDATE plpgsql_lab.accounts
    SET balance = balance + 5
    WHERE account_id = 3;

    RAISE NOTICE 'Updated Hoa balance';
END;
$do$;

SELECT balance
FROM plpgsql_lab.accounts
WHERE account_id = 3;

ROLLBACK; -- Hủy UPDATE.
~~~

Dù `END;` của DO đã chạy xong, UPDATE vẫn chưa thành dữ liệu bền vững cho đến khi transaction SQL được commit. `ROLLBACK` hủy thay đổi.

### Nếu DO không nằm trong BEGIN SQL explicit?

Ở chế độ autocommit thông thường của client, câu `DO` có thể chạy trong transaction tự quản lý của statement. Nhưng **đó vẫn không có nghĩa mỗi PL/pgSQL BEGIN tạo một transaction riêng**.

## 41. Function, procedure và quyền điều khiển transaction

### FUNCTION

Hàm PL/pgSQL được gọi trong một SQL statement/transaction do caller quản lý. Không dùng `COMMIT`/`ROLLBACK` bên trong function để tự kết thúc transaction caller.

~~~sql
CREATE OR REPLACE FUNCTION plpgsql_lab.touch_account(
    p_account_id integer
)
RETURNS boolean
LANGUAGE plpgsql
AS $fn$
BEGIN
    UPDATE plpgsql_lab.accounts
    SET updated_at = clock_timestamp()
    WHERE account_id = p_account_id;

    RETURN FOUND;
END;
$fn$;
~~~

### PROCEDURE

PostgreSQL có `CREATE PROCEDURE` và `CALL` (từ PostgreSQL 11). Một số ngữ cảnh `CALL`/`DO` được phép thực hiện transaction control, nhưng phải đáp ứng những giới hạn về call stack, transaction boundary và cấu trúc procedure.

**Không được suy ra: “Có procedure nên đặt COMMIT trong bất cứ BEGIN nào cũng được”.**

Ví dụ thủ tục *không* tự điều khiển transaction:

~~~sql
CREATE OR REPLACE PROCEDURE plpgsql_lab.mark_account(
    p_account_id integer
)
LANGUAGE plpgsql
AS $proc$
BEGIN
    UPDATE plpgsql_lab.accounts
    SET updated_at = clock_timestamp()
    WHERE account_id = p_account_id;
END;
$proc$;
~~~

Gọi trong lab:

~~~sql
BEGIN;

CALL plpgsql_lab.mark_account(1);

ROLLBACK;
~~~

`CALL` này tuân transaction ngoài.

### Hạn chế quan trọng với EXCEPTION

Không kết thúc transaction bằng `COMMIT` hoặc `ROLLBACK` ở bên trong một block có exception handlers đang bao quanh, vì khối có `EXCEPTION` dùng cơ chế subtransaction nội bộ và transaction control có giới hạn rõ ràng.

Khi thiết kế procedure cần commit nhiều lần, hãy đọc tài liệu transaction management đúng PostgreSQL major version và tách cấu trúc phù hợp. Trong function/trigger, không tự đưa transaction control vào phần thân.

## 42. Một ứng dụng nhiều bước: chuyển tiền an toàn trong transaction

Một function chuyển tiền gồm:

1. Kiểm tra đầu vào.
2. Khóa hai account theo thứ tự nhất quán.
3. Kiểm tra hai account tồn tại.
4. Kiểm tra đủ số dư.
5. Trừ tài khoản nguồn.
6. Cộng tài khoản đích.
7. Ghi nhật ký chuyển tiền.
8. Để caller quyết định `COMMIT`/`ROLLBACK`.

Ví dụ lab:

~~~sql
CREATE OR REPLACE FUNCTION plpgsql_lab.transfer_funds(
    p_from integer,
    p_to integer,
    p_amount numeric
)
RETURNS void
LANGUAGE plpgsql
AS $fn$
DECLARE
    v_count integer;
    v_source_balance plpgsql_lab.accounts.balance%TYPE;
BEGIN
    IF p_from IS NULL
       OR p_to IS NULL
       OR p_amount IS NULL
       OR p_amount <= 0
       OR p_from = p_to
    THEN
        RAISE EXCEPTION 'Invalid transfer arguments'
            USING ERRCODE = '22023';
    END IF;

    -- Khóa các hàng theo thứ tự ID để giảm nguy cơ deadlock.
    PERFORM a.account_id
    FROM plpgsql_lab.accounts AS a
    WHERE a.account_id IN (p_from, p_to)
    ORDER BY a.account_id
    FOR UPDATE;

    SELECT COUNT(*)
    INTO v_count
    FROM plpgsql_lab.accounts AS a
    WHERE a.account_id IN (p_from, p_to);

    IF v_count <> 2 THEN
        RAISE EXCEPTION 'Account not found'
            USING ERRCODE = 'P1002';
    END IF;

    SELECT a.balance
    INTO STRICT v_source_balance
    FROM plpgsql_lab.accounts AS a
    WHERE a.account_id = p_from;

    IF v_source_balance < p_amount THEN
        RAISE EXCEPTION
            'Insufficient balance in account %',
            p_from
            USING ERRCODE = 'P1001';
    END IF;

    UPDATE plpgsql_lab.accounts
    SET balance = balance - p_amount,
        updated_at = clock_timestamp()
    WHERE account_id = p_from;

    UPDATE plpgsql_lab.accounts
    SET balance = balance + p_amount,
        updated_at = clock_timestamp()
    WHERE account_id = p_to;

    INSERT INTO plpgsql_lab.transfers (
        from_account, to_account, amount
    )
    VALUES (p_from, p_to, p_amount);
END;
$fn$;
~~~

### Cần hiểu giới hạn demo

Đây là ví dụ học PL/pgSQL và atomicity trên lab, **không phải giải pháp thanh toán production hoàn chỉnh**. Hệ thống thật còn cần business IDs, idempotency key, authorization, currency precision, ledger bất biến, reconciliation, audit, kiểm soát lệnh retry và concurrency.

Câu `PERFORM ... ORDER BY account_id FOR UPDATE` cố gắng khóa account theo thứ tự nhất quán; đây là kỹ thuật giảm deadlock, không phải bảo đảm mọi workload không có deadlock khi còn truy cập các bảng/lock khác.

### Không bắt lỗi để âm thầm giữ một nửa thao tác

Function trên **không có `EXCEPTION` nuốt mọi lỗi**. Nếu một UPDATE/INSERT lỗi, exception được đưa lên caller; những thay đổi thuộc transaction bị rollback theo quy tắc. Điều đó thường an toàn hơn việc handler `WHEN OTHERS THEN RETURN;` rồi client nghĩ chuyển tiền đã thành công.

## 43. Thử chuyển tiền và rollback

~~~sql
BEGIN;

SELECT plpgsql_lab.transfer_funds(
    1,
    2,
    100.00
);

SELECT account_id, owner_name, balance
FROM plpgsql_lab.accounts
ORDER BY account_id;

SELECT from_account, to_account, amount
FROM plpgsql_lab.transfers
ORDER BY transfer_id;

ROLLBACK;
~~~

Trong transaction:

- Lan: 1000.00 → 900.00.
- Minh: 500.00 → 600.00.
- Hoa: giữ 250.00.
- Một dòng transfer log được tạo.

Sau `ROLLBACK`, tiền và transfer log trở về dữ liệu trước thử nghiệm. **Sequence identity có thể tăng dù transaction rollback**, điều này là bình thường.

### Vì sao function không chứa COMMIT?

Caller có thể cần thực hiện thêm các bước cùng nghiệp vụ trong một transaction. Function không được tự ý commit nửa chừng rồi làm caller mất quyền rollback cả transaction.

## 44. Thử bắt lỗi thiếu số dư ở block ngoài

Ta có thể chủ động gọi một chuyển tiền vượt số dư rồi bắt mã nghiệp vụ `P1001`:

~~~sql
DO $do$
BEGIN
    BEGIN
        PERFORM plpgsql_lab.transfer_funds(
            1,
            2,
            999999.00
        );

        RAISE NOTICE 'Transfer succeeded';

    EXCEPTION
        WHEN SQLSTATE 'P1001' THEN
            RAISE NOTICE 'Business error: insufficient funds';
    END;

    RAISE NOTICE 'Application flow continues';
END;
$do$;
~~~

Function `transfer_funds` phát exception trước khi UPDATE vì số dư không đủ. Handler ngoài nhận `P1001` và có thể báo lỗi nghiệp vụ thay vì làm client nhận SQL exception trực tiếp.

### Không coi “handler chạy xong” là đã chuyển tiền

Nếu một API gọi function bên trong handler như trên, nó phải phân biệt **successful transfer** và **insufficient funds**. Một handler chỉ in NOTICE rồi trả về bình thường là ví dụ minh họa điều khiển luồng; trong ứng dụng, nên trả status có cấu trúc hoặc để service xử lý lỗi có mã.

### Khi nào nên bắt exception trong function chuyển tiền?

Chỉ khi function có quy tắc phục hồi/cung cấp thông tin cụ thể và vẫn giữ atomicity. Bắt `WHEN OTHERS THEN NULL;` chỉ để “ứng dụng không báo lỗi” có thể che transaction thất bại và sai kết quả nghiệp vụ.

## 45. Exception là rollback cục bộ, không phải retry transaction

Một số lỗi cần retry từ caller:

- `40001` — `serialization_failure`.
- `40P01` — `deadlock_detected`.

Ví dụ quy tắc ứng dụng:

~~~text
For each attempt up to a bounded retry count:
  BEGIN transaction
  Read relevant state and validate conditions
  Call business function(s)
  COMMIT
On SQLSTATE 40001 or 40P01:
  ROLLBACK
  Apply backoff
  Restart the WHOLE transaction and recompute decisions
On unique/validation errors:
  Handle according to business contract; do not retry blindly
~~~

**Không chỉ retry câu UPDATE cuối** bằng dữ liệu tính từ snapshot/điều kiện cũ. Lỗi concurrency thường đòi kiểm tra lại toàn bộ logic trong transaction mới.

Cũng không nên viết vòng lặp PL/pgSQL bắt `40001` rồi tự lặp vô hạn trong cùng một call, vì còn phụ thuộc isolation level/snapshot và giới hạn transaction.

## 46. Khi nào dùng EXCEPTION thay vì ON CONFLICT?

Nếu mục tiêu là bỏ qua event_key đã tồn tại:

~~~sql
INSERT INTO plpgsql_lab.events (
    event_key, detail
)
VALUES (
    'existing-event',
    'Duplicate is an expected case'
)
ON CONFLICT (event_key)
DO NOTHING;
~~~

So với:

~~~sql
BEGIN
    INSERT INTO plpgsql_lab.events (
        event_key, detail
    )
    VALUES (
        'existing-event',
        'Duplicate is an expected case'
    );
EXCEPTION
    WHEN unique_violation THEN
        NULL;
END;
~~~

`ON CONFLICT` thường rõ hơn khi duplicate trên key cụ thể là nhánh nghiệp vụ phổ biến. Nó tránh dùng lỗi/exception như vòng điều khiển bình thường và giảm nguy cơ bắt nhầm UNIQUE violation ở nơi khác.

### Khi EXCEPTION thực sự hữu ích

- Cần rollback các thay đổi trong một block nhiều statement và chọn phương án thay thế.
- Cần thông tin `SQLSTATE`/DETAIL/CONSTRAINT_NAME của một lỗi bất thường.
- Cần phân loại lỗi để chuyển sang một error contract phù hợp.
- Cần một handler ở phạm vi hẹp mà câu SQL đơn lẻ không diễn đạt hết logic.

## 47. EXCEPTION không thay thế validation

Với số tiền:

~~~sql
IF p_amount IS NULL OR p_amount <= 0 THEN
    RAISE EXCEPTION 'Amount must be positive'
        USING ERRCODE = '22023';
END IF;
~~~

đây là validation rõ ràng. Không nên cứ thực hiện một `UPDATE` có thể vi phạm CHECK rồi dựa vào handler `check_violation` cho mọi giá trị âm nếu có thể kiểm tra đầu vào từ trước.

Tuy vậy, constraints của database vẫn phải tồn tại. Validation trong ứng dụng/function có thể bị bỏ qua khi có một đường ghi khác; `CHECK`/`UNIQUE`/`FK` là hàng rào bảo vệ cuối cùng.

### Thiết kế hai lớp

1. Kiểm tra đầu vào và quy tắc nghiệp vụ để trả lỗi dễ hiểu.
2. Giữ constraints trong database để chống lỗi từ mọi đường ghi.
3. Bắt exception cụ thể khi cần xử lý race condition hoặc convert lỗi.
4. Không nuốt lỗi constraints không thuộc tập hợp đã thiết kế.

## 48. Scope của EXCEPTION và nested blocks

Một block ngoài không tự rollback mọi thay đổi do inner block bị bắt lỗi, miễn là những thay đổi của outer nằm ngoài protected portion rollback của inner.

Ngược lại, nếu **block ngoài cũng có `EXCEPTION`** và một lỗi lan tới handler ngoài, thay đổi database trong protected portion của outer có thể bị rollback theo cơ chế của block ngoài, bao gồm những statement đã thành công ở các block con trước đó.

~~~text
Outer protected statements
  ├── INSERT A
  ├── Inner block
  │     └── INSERT B
  └── RAISE EXCEPTION
Outer EXCEPTION handler
  └── A và B có thể đã bị rollback khi vào handler outer
~~~

Quy tắc phải xét **block nào đang bắt lỗi**. Không chỉ nhìn statement “đã in NOTICE thành công” rồi kết luận row tương ứng được commit.

### Cẩn thận với các biến local

Trong lúc rollback database state, các biến PL/pgSQL đã được gán có thể còn giá trị. Khi code đi qua nhiều handler lồng nhau, biến có thể không phản ánh trạng thái database hiện tại nếu không được tính lại.

## 49. Không dùng EXCEPTION như autonomous transaction

Một số hệ quản trị có cơ chế autonomous transaction cho logging riêng. **PL/pgSQL exception block của PostgreSQL không tự trở thành autonomous transaction.**

Ví dụ:

~~~sql
BEGIN;

DO $do$
BEGIN
    BEGIN
        RAISE EXCEPTION 'Example failure';
    EXCEPTION
        WHEN raise_exception THEN
            INSERT INTO plpgsql_lab.events (
                event_key, detail
            )
            VALUES (
                'audit-attempt',
                'This is still in outer SQL transaction'
            );
    END;
END;
$do$;

ROLLBACK;
~~~

Dòng `audit-attempt` cũng bị rollback do transaction ngoài rollback.

Nếu yêu cầu “log thất bại vẫn tồn tại ngay cả khi transaction chính bị rollback”, cần thiết kế logging ở kênh phù hợp hoặc một cơ chế tách transaction được hỗ trợ với đánh đổi rõ ràng, chứ không mặc định `EXCEPTION` làm việc đó.

## 50. Đặt tên nhãn và chia nhỏ hàm

Một function quá lớn với hàng chục nested block rất khó đọc:

~~~text
Function
  DECLARE 20 biến
  BEGIN
    IF ...
      BEGIN
        LOOP ...
          BEGIN
            EXCEPTION ...
          END
        END LOOP
      EXCEPTION ...
      END
    END IF
  EXCEPTION ...
  END
~~~

Các biện pháp:

- Chia logic thành những function có trách nhiệm rõ.
- Dùng block lồng khi cần scope/hành vi rollback cục bộ thật.
- Dùng nhãn để kết thúc/tổ chức block phức tạp.
- Khai báo biến gần phạm vi thực sự cần.
- Bắt lỗi hẹp, tránh `WHEN OTHERS` không có tiêu chí.
- Để transaction boundary ở caller/service theo thiết kế.
- Có kiểm thử cả đường thành công và đường lỗi.

Không chia nhỏ chỉ để số dòng ngắn; điều quan trọng là phạm vi biến, dữ liệu và semantics exception dễ hiểu.

## 51. Phân biệt BEGIN, END IF, END LOOP và END CASE

| Cú pháp mở | Cú pháp đóng | Vai trò |
| --- | --- | --- |
| `BEGIN` | `END;` hoặc `END label;` | Khối PL/pgSQL |
| `IF ... THEN` | `END IF;` | Rẽ nhánh |
| `LOOP` | `END LOOP;` | Vòng lặp |
| `CASE ...` statement | `END CASE;` | Lệnh CASE của PL/pgSQL |
| `$fn$` | `$fn$;` | Kết thúc literal phần thân của CREATE FUNCTION |

Ví dụ:

~~~sql
DO $do$
DECLARE
    v_i integer := 0;
BEGIN
    LOOP
        v_i := v_i + 1;

        IF v_i >= 3 THEN
            EXIT;
        END IF;
    END LOOP;

    RAISE NOTICE 'Finished at %', v_i;
END;
$do$;
~~~

Số dấu `END` không phải số transaction. Mỗi keyword đóng đúng cấu trúc ngữ pháp của nó.

## 52. Dấu chấm phẩy trong PL/pgSQL

Ví dụ hợp lệ:

~~~sql
DO $do$
DECLARE
    v_count integer := 0;
BEGIN
    v_count := v_count + 1;
    RAISE NOTICE 'Count = %', v_count;
END;
$do$;
~~~

Cần hai vị trí kết thúc:

1. `END;`: kết thúc block trong thân DO.
2. `$do$;`: dấu `;` kết thúc statement SQL DO.

Với function:

~~~sql
CREATE OR REPLACE FUNCTION plpgsql_lab.identity_number(
    p_input integer
)
RETURNS integer
LANGUAGE plpgsql
AS $fn$
BEGIN
    RETURN p_input;
END;
$fn$;
~~~

Không bỏ `;` sau `RETURN` hoặc sau `END`.

### EXCEPTION không có dấu chấm phẩy ngay sau từ khóa

Đúng:

~~~sql
EXCEPTION
    WHEN division_by_zero THEN
        RAISE NOTICE 'Division by zero';
~~~

Không viết `EXCEPTION;` như một statement độc lập.

## 53. Những lỗi thường gặp

### 53.1. Nghĩ PL/pgSQL BEGIN bắt đầu SQL transaction

`BEGIN ... END` trong thân function/DO là block. Transaction do SQL caller quản lý theo quy tắc của môi trường.

### 53.2. Dùng COMMIT bên trong function

Hàm không được tự commit transaction caller; procedure/DO có quy định riêng và không cho transaction control trong exception block subtransaction.

### 53.3. Viết DECLARE giữa statements không mở block mới

Declarations phải đứng trước `BEGIN` của block tương ứng.

### 53.4. Nhầm dấu END IF và END

`END IF;` đóng IF, `END;` đóng block. Không thay thế nhau.

### 53.5. Khai báo biến có tên trùng cột

Có thể gây ambiguous reference hoặc truy vấn đổi nghĩa. Dùng alias cho cột và tiền tố biến.

### 53.6. Nghĩ biến local có phạm vi toàn session

Biến thuộc block/function execution, không phải session variable bền vững.

### 53.7. Nghĩ biến tự rollback sau EXCEPTION

Thay đổi DB trong protected portion có thể rollback, nhưng biến PL/pgSQL có thể giữ giá trị đã gán.

### 53.8. Nghĩ handler sẽ chạy tiếp những statement sau lỗi trong phần BEGIN

Khi chuyển vào handler, những statement còn lại trước `EXCEPTION` không được tự chạy tiếp.

### 53.9. Nghĩ EXCEPTION tự commit những gì handler ghi

Handler vẫn thuộc transaction SQL bao ngoài; rollback ngoài có thể hủy mọi thứ.

### 53.10. Bắt WHEN OTHERS rồi im lặng

Có thể che lỗi dữ liệu/logic và tạo response thành công giả.

### 53.11. Nghĩ OTHERS bắt mọi loại lỗi tuyệt đối

Có ngoại lệ đặc biệt như QUERY_CANCELED và ASSERT_FAILURE theo semantics PostgreSQL.

### 53.12. Không rethrow lỗi ngoài mong đợi

Nếu không có phương án phục hồi, `RAISE;` thường phù hợp hơn tự nuốt lỗi.

### 53.13. Bắt unique_violation quanh quá nhiều câu SQL

Có thể bắt UNIQUE của constraint khác và hiểu sai thành duplicate dự kiến.

### 53.14. Dùng exception cho duplicate bình thường

Nếu phù hợp, `ON CONFLICT` rõ hơn và có thể tránh chi phí exception/subtransaction lặp lại.

### 53.15. Dùng SELECT INTO không STRICT khi cần đúng một hàng

Có thể âm thầm nhận NULL hoặc một hàng không xác định nếu nhiều kết quả.

### 53.16. Nhầm SELECT INTO PL/pgSQL với SQL tạo bảng

Trong PL/pgSQL, `SELECT ... INTO variable` gán biến.

### 53.17. Dùng FOUND sau nhiều statement khác

Nó có thể đã được cập nhật bởi statement khác. Kiểm tra ngay sau câu lệnh quan tâm.

### 53.18. Nhầm GET DIAGNOSTICS với GET STACKED DIAGNOSTICS

Một cái đọc trạng thái statement, một cái đọc thông tin lỗi trong handler.

### 53.19. Dùng SQLSTATE/SQLERRM ngoài handler mà mong có lỗi hiện hành

Cần đọc trong ngữ cảnh exception hợp lệ.

### 53.20. Nghĩ RAISE NOTICE tương đương RAISE EXCEPTION

NOTICE thường chỉ thông báo; EXCEPTION gây lỗi và chuyển điều khiển theo cơ chế handler.

### 53.21. Nghĩ WHEN OTHERS là chiến lược retry

Handler không tự retry, và lỗi concurrency thường cần retry toàn transaction ở caller.

### 53.22. Dùng quá nhiều EXCEPTION trong vòng lặp

Có chi phí subtransaction và exception handling; tránh dùng lỗi như nhánh bình thường trên hàng triệu hàng.

### 53.23. Không phân biệt handler error với protected error

Exception phát sinh **trong handler** có thể cần block ngoài để bắt; cùng handler list không tự “bắt lần hai”.

### 53.24. Log nguyên diagnostics cho người dùng cuối

Có thể lộ schema, SQL context hoặc dữ liệu nhạy cảm; phải có error contract và logging policy.

### 53.25. Dùng block lồng phức tạp để che quy tắc nghiệp vụ không rõ

Nên chia logic thành các routine có trách nhiệm tường minh, kiểm thử đường lỗi và transaction.

## 54. Bài tập thực hành có đáp án

Thực hành sau khi chạy schema `plpgsql_lab`. Với các ví dụ có DML, nên bọc SQL `BEGIN; ... ROLLBACK;` và dùng một connection cố định. Những ví dụ cố ý gây lỗi ngoài handler cần được rollback trước khi tiếp tục.

### Bài 1. Block tối thiểu

**Yêu cầu:** In NOTICE “Hello PL/pgSQL”.

~~~sql
DO $do$
BEGIN
    RAISE NOTICE 'Hello PL/pgSQL';
END;
$do$;
~~~

**Giải thích:** Không cần `DECLARE` hoặc `EXCEPTION`; `BEGIN/END` vẫn bắt buộc.

### Bài 2. Khai báo và tính tổng

~~~sql
DO $do$
DECLARE
    v_a integer := 12;
    v_b integer := 8;
    v_total integer;
BEGIN
    v_total := v_a + v_b;
    RAISE NOTICE 'Total = %', v_total;
END;
$do$;
~~~

**Đáp án:** `v_total = 20`.

### Bài 3. Hằng CONSTANT

**Câu hỏi:** Có thể gán lại một biến khai báo `CONSTANT` sau BEGIN không?

**Đáp án:** Không. Hằng phải có giá trị khởi tạo phù hợp và không được gán lại.

### Bài 4. Biến không khai báo giá trị

**Câu hỏi:** `DECLARE v_note text;` có giá trị ban đầu là gì?

**Đáp án:** SQL NULL theo quy tắc mặc định.

### Bài 5. NOT NULL

**Câu hỏi:** Điều gì xảy ra nếu gán NULL cho biến `integer NOT NULL`?

**Đáp án:** PostgreSQL phát lỗi; biến NOT NULL không cho giá trị NULL.

### Bài 6. Scope của nested block

~~~sql
DO $do$
DECLARE
    v_outer integer := 5;
BEGIN
    DECLARE
        v_inner integer := 7;
    BEGIN
        RAISE NOTICE 'Sum=%', v_outer + v_inner;
    END;
END;
$do$;
~~~

**Đáp án:** Inner block có thể đọc v_outer; in 12. Sau inner END, v_inner không còn trong scope của outer statements.

### Bài 7. Shadowing

**Câu hỏi:** Nếu inner block khai báo `v_name` trùng outer, tên `v_name` không qualified bên trong trỏ tới biến nào?

**Đáp án:** Biến inner theo phạm vi gần nhất; biến outer bị shadow.

### Bài 8. Qualified label

~~~sql
DO $do$
<<outer_block>>
DECLARE
    v_name text := 'outer';
BEGIN
    DECLARE
        v_name text := 'inner';
    BEGIN
        RAISE NOTICE '% / %',
            v_name, outer_block.v_name;
    END;
END outer_block;
$do$;
~~~

**Đáp án:** In `inner / outer`.

### Bài 9. BEGIN ... END có COMMIT không?

**Đáp án:** Không. PL/pgSQL BEGIN/END xác định block; transaction SQL ngoài vẫn quyết định COMMIT/ROLLBACK.

### Bài 10. SELECT INTO không có hàng

~~~sql
DO $do$
DECLARE
    v_balance numeric;
BEGIN
    SELECT balance INTO v_balance
    FROM plpgsql_lab.accounts
    WHERE account_id = -1;

    RAISE NOTICE 'Found? %', FOUND;
END;
$do$;
~~~

**Đáp án:** `FOUND=false` nếu account -1 không tồn tại; target nhận NULL theo quy tắc non-STRICT.

### Bài 11. INTO STRICT không có hàng

~~~sql
DO $do$
DECLARE
    v_balance numeric;
BEGIN
    BEGIN
        SELECT balance INTO STRICT v_balance
        FROM plpgsql_lab.accounts
        WHERE account_id = -1;
    EXCEPTION
        WHEN no_data_found THEN
            RAISE NOTICE 'Not found';
    END;
END;
$do$;
~~~

**Đáp án:** `NO_DATA_FOUND` được bắt bởi handler.

### Bài 12. Khi nào có TOO_MANY_ROWS?

**Đáp án:** `SELECT ... INTO STRICT` nhận hơn một hàng thay vì đúng một hàng.

### Bài 13. PERFORM có tác dụng gì?

**Đáp án:** Chạy query nhưng không dùng giá trị trả về; có thể kiểm tra `FOUND` để biết có hàng theo semantics statement.

### Bài 14. ROW_COUNT

~~~sql
BEGIN;

DO $do$
DECLARE
    v_updated bigint;
BEGIN
    UPDATE plpgsql_lab.accounts
    SET updated_at = clock_timestamp()
    WHERE account_id IN (1, 2);

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RAISE NOTICE 'Rows=%', v_updated;
END;
$do$;

ROLLBACK;
~~~

**Đáp án:** Dự kiến `v_updated = 2` trên seed chuẩn.

### Bài 15. Bắt chia cho 0

~~~sql
DO $do$
BEGIN
    PERFORM 10 / 0;
EXCEPTION
    WHEN division_by_zero THEN
        RAISE NOTICE 'Handled division by zero';
END;
$do$;
~~~

**Đáp án:** Handler xử lý SQLSTATE `22012`.

### Bài 16. Bắt UNIQUE

**Câu hỏi:** INSERT `event_key='existing-event'` vào bảng events gây điều kiện nào?

**Đáp án:** `unique_violation`, SQLSTATE `23505`.

### Bài 17. Khi có hai WHEN

**Câu hỏi:** Nếu lỗi là division_by_zero và có nhánh cho division_by_zero lẫn OTHERS thì nhánh nào chạy?

**Đáp án:** Nhánh đặc hiệu phù hợp `division_by_zero`; không chạy tiếp OTHERS.

### Bài 18. OTHERS bắt được mọi lỗi không?

**Đáp án:** Không; có các tình huống đặc biệt như `QUERY_CANCELED` và `ASSERT_FAILURE`.

### Bài 19. Handler không phù hợp

**Câu hỏi:** Nếu inner block chỉ bắt division_by_zero nhưng phát unique_violation thì sao?

**Đáp án:** Lỗi truyền lên block/caller ngoài, nơi có thể có handler phù hợp; nếu không thì statement/transaction bị lỗi.

### Bài 20. EXCEPTION rollback cái gì?

**Đáp án:** Những thay đổi database trong protected portion của block được rollback khi exception được bắt; thay đổi DB trước inner block ngoài phạm vi đó không tự bị rollback chỉ vì inner exception.

### Bài 21. Biến local sau rollback nội bộ?

**Đáp án:** Giá trị biến đã gán có thể giữ nguyên. Biến PL/pgSQL không tự rollback như row trong database.

### Bài 22. Handler INSERT audit có commit độc lập?

**Đáp án:** Không. INSERT của handler vẫn thuộc SQL transaction ngoài; outer ROLLBACK có thể hủy nó.

### Bài 23. SQLSTATE và SQLERRM dùng ở đâu?

**Đáp án:** Trong exception handler để đọc mã và thông điệp lỗi đang xử lý.

### Bài 24. Lấy thông tin constraint gây lỗi

~~~sql
DO $do$
DECLARE
    v_constraint text;
BEGIN
    INSERT INTO plpgsql_lab.events(event_key)
    VALUES ('existing-event');

EXCEPTION
    WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS
            v_constraint = CONSTRAINT_NAME;

        RAISE NOTICE 'Constraint=%', v_constraint;
END;
$do$;
~~~

**Đáp án:** Handler nhận tên constraint từ exception diagnostics khi có.

### Bài 25. RAISE; có tác dụng gì?

**Đáp án:** Truyền lại chính exception đang được xử lý lên caller hoặc outer handler, giữ ngữ nghĩa lỗi gốc.

### Bài 26. Lỗi trong handler ai bắt?

**Đáp án:** Một outer block/handler phù hợp. Handler list của chính block không tự bắt lại lỗi vừa phát sinh trong handler.

### Bài 27. Khi duplicate là bình thường nên dùng gì?

**Đáp án:** `INSERT ... ON CONFLICT (event_key) DO NOTHING` thường rõ hơn và tránh dùng exception như nhánh điều khiển thông thường.

### Bài 28. Tại sao function chuyển tiền không bắt WHEN OTHERS THEN NULL?

**Đáp án:** Có thể biến một transaction nghiệp vụ thất bại thành kết quả trông như thành công, khiến caller không rollback/không xử lý đúng.

### Bài 29. Vì sao không retry vô hạn sau SQLSTATE 40001?

**Đáp án:** Cần rollback/retry **toàn transaction**, giới hạn số lần và tính lại điều kiện nghiệp vụ. Retry vô hạn hoặc chỉ một SQL cuối có thể sai/bị kẹt.

### Bài 30. Lỗi chi phí khi dùng EXCEPTION hàng triệu lần?

**Đáp án:** Handler có overhead do subtransaction; exception phát sinh thường xuyên còn tốn thêm xử lý lỗi. Nên dùng các câu SQL set-based, validation hoặc ON CONFLICT phù hợp.

## 55. Checklist thực hành đúng

- [ ] Block có `BEGIN ... END;` đúng vị trí.
- [ ] `DECLARE` đặt trước `BEGIN`, chỉ khai báo biến cần cho block.
- [ ] Khai báo kiểu và giá trị khởi tạo phù hợp, kiểm tra `NOT NULL`/`CONSTANT`.
- [ ] Dùng `%TYPE`/`%ROWTYPE` khi cần đồng bộ kiểu với schema.
- [ ] Dùng tiền tố biến và table alias để tránh ambiguous names.
- [ ] Chỉ tạo nested block khi cần scope hoặc rollback cục bộ.
- [ ] Dùng label `<<label>>` khi nested/shadowing phức tạp.
- [ ] Phân biệt `END;`, `END IF;`, `END LOOP;` và `END CASE;`.
- [ ] Dùng `SELECT INTO STRICT` khi cần đúng một hàng.
- [ ] Kiểm tra `FOUND`/`ROW_COUNT` ngay sau statement liên quan.
- [ ] Bắt lỗi cụ thể bằng condition name hoặc SQLSTATE.
- [ ] Không coi `WHEN OTHERS` là giải pháp cho mọi lỗi.
- [ ] Dùng `GET STACKED DIAGNOSTICS` trong handler khi cần dữ liệu lỗi.
- [ ] Không đưa nguyên context lỗi nhạy cảm ra API công khai.
- [ ] Hiểu exception block rollback **DB state**, nhưng không tự rollback **local variables**.
- [ ] Không coi handler/audit INSERT là autonomous transaction.
- [ ] Rethrow lỗi không xử lý an toàn bằng `RAISE;`.
- [ ] Ưu tiên `ON CONFLICT` cho duplicate dự kiến thay vì lạm dụng exceptions.
- [ ] Tránh exception blocks trong hot loops khi có phương án đơn giản hơn.
- [ ] Không gọi `COMMIT` trong function; procedure/DO có giới hạn riêng.
- [ ] Đặt SQL transaction boundaries ở caller/service đúng thiết kế.
- [ ] Bọc ví dụ thay đổi dữ liệu trong SQL transaction và rollback khi làm lab.
- [ ] Thử cả đường thành công, lỗi validation, UNIQUE, FK, insufficient funds.
- [ ] Với `40001`/`40P01`, thiết kế retry bounded toàn transaction khi an toàn.
- [ ] Khi code dài, tách routine/phạm vi trách nhiệm thay vì lồng handler tùy tiện.
- [ ] Không tự chạy exception demo hoặc DROP SCHEMA trên production.

## 56. Tài liệu PostgreSQL chính thức

Những nguồn cần đọc theo **major version của PostgreSQL server đang dùng**:

- [PL/pgSQL Structure](https://www.postgresql.org/docs/current/plpgsql-structure.html) — cấu trúc block, label, phạm vi biến.
- [PL/pgSQL Declarations](https://www.postgresql.org/docs/current/plpgsql-declarations.html) — DECLARE, CONSTANT, NOT NULL, %TYPE, %ROWTYPE.
- [PL/pgSQL Basic Statements](https://www.postgresql.org/docs/current/plpgsql-statements.html) — gán biến, SELECT INTO, PERFORM, EXECUTE, diagnostics.
- [PL/pgSQL Control Structures](https://www.postgresql.org/docs/current/plpgsql-control-structures.html) — IF/LOOP/RETURN, exception handling.
- [Errors and Messages](https://www.postgresql.org/docs/current/plpgsql-errors-and-messages.html) — RAISE levels, SQLSTATE, message/detail/hint.
- [Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html) — 23505, 23503, P0001, P0002, P0003, 40001.
- [DO](https://www.postgresql.org/docs/current/sql-do.html) — thực thi anonymous code block.
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html) — function signatures và LANGUAGE plpgsql.
- [CREATE PROCEDURE](https://www.postgresql.org/docs/current/sql-createprocedure.html) — procedure và CALL.
- [CALL](https://www.postgresql.org/docs/current/sql-call.html) — cách gọi procedure.
- [Transaction Management](https://www.postgresql.org/docs/current/plpgsql-transactions.html) — transaction control trong procedure/DO và các giới hạn.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — concurrency, snapshots và retry.
- [INSERT](https://www.postgresql.org/docs/current/sql-insert.html) — ON CONFLICT như một phương án không dùng exception.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — row locks và deadlocks.

Các URL `/current/` dẫn đến tài liệu PostgreSQL hiện hành; khi server chạy major version cụ thể, cần kiểm tra tài liệu tương ứng để biết cú pháp và các giới hạn áp dụng.

## 57. Tổng kết

**Block là đơn vị tổ chức điều khiển luồng và phạm vi trong PL/pgSQL.** Hiểu đúng `DECLARE`, `BEGIN`, `EXCEPTION` và `END` giúp viết function/procedure rõ ràng và xử lý lỗi mà không làm sai tính nhất quán dữ liệu.

Những ý chính:

1. **`DECLARE`** định nghĩa biến và giá trị khởi tạo; **`BEGIN`** bắt đầu statements; **`EXCEPTION`** là phần tùy chọn bắt lỗi; **`END`** đóng khối.
2. **`BEGIN ... END` của PL/pgSQL không phải SQL transaction.** `COMMIT`/`ROLLBACK` thuộc ngữ cảnh transaction do caller quản lý, với giới hạn riêng cho procedure/DO.
3. **Block có thể lồng nhau và có nhãn.** Scope/shadowing quyết định biến nào được đọc; `outer_block.variable` giúp truy cập biến ngoài bị che.
4. **`SELECT ... INTO STRICT`** giúp yêu cầu đúng một hàng và dùng các điều kiện `NO_DATA_FOUND`, `TOO_MANY_ROWS`.
5. **Khi handler bắt lỗi**, PostgreSQL rollback thay đổi database trong phần protected block theo cơ chế subtransaction nội bộ; nhưng biến PL/pgSQL đã gán có thể giữ giá trị.
6. **Handler không tự commit** và không tự chạy lại phần statements sau khi lỗi. Lỗi handler phát sinh có thể cần block ngoài xử lý.
7. **`SQLSTATE`, `SQLERRM` và `GET STACKED DIAGNOSTICS`** giúp phân loại/ghi nhận lỗi. `RAISE;` dùng để chuyển lại lỗi gốc khi không thể xử lý an toàn.
8. **Tránh bắt `WHEN OTHERS THEN NULL;` vô điều kiện**; nó có thể che bug, biến thao tác thất bại thành response thành công.
9. **Dùng exception cho lỗi thật**, còn các nhánh nghiệp vụ dự kiến nên dùng validation hoặc SQL như `ON CONFLICT` khi phù hợp.
10. **Thiết kế transaction và retry rõ ràng**, nhất là khi nghiệp vụ có nhiều bước, concurrency và side effects bên ngoài.

Khi phân biệt đúng **phạm vi block, phạm vi transaction và phạm vi xử lý ngoại lệ**, bạn có thể dùng PL/pgSQL để viết logic nhiều bước dễ kiểm thử, xử lý lỗi chính xác và bảo vệ tính nhất quán của dữ liệu PostgreSQL.
