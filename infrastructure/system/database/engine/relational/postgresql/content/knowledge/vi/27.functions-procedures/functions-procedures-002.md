# Kiểu tham số IN, OUT, INOUT và VARIADIC

Trong PostgreSQL, **hàm (function)** và **thủ tục (procedure)** là những đối tượng cơ sở dữ liệu có thể nhận tham số để xử lý dữ liệu. Một hàm tính giá sau thuế có thể cần giá và tỷ lệ thuế; một hàm thống kê có thể trả đồng thời số hàng và tổng doanh thu; một thủ tục kiểm tra hạn mức có thể nhận một giá trị rồi trả lại giá trị đã điều chỉnh; một hàm tính tổng lại cần nhận **số lượng đối số thay đổi**. Bốn kiểu tham số `IN`, `OUT`, `INOUT` và `VARIADIC` giải quyết các nhu cầu này.

Tuy tên gọi giống khái niệm tham chiếu trong một số ngôn ngữ lập trình, cách chúng hoạt động trong PostgreSQL không hoàn toàn giống việc truyền con trỏ hoặc đối tượng Java có thể sửa trực tiếp. Bạn cần phân biệt **chữ ký dùng để gọi**, **giá trị đi vào**, **giá trị trả ra** và **cách client nhận kết quả**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích ý nghĩa `IN`, `OUT`, `INOUT` và `VARIADIC` trong khai báo routine.
2. Viết hàm `LANGUAGE SQL` và `LANGUAGE plpgsql` với tham số đầu vào/đầu ra đúng cú pháp.
3. Trả về một hay nhiều kết quả bằng `OUT` và so sánh với `RETURNS TABLE`.
4. Viết hàm/thủ tục có `INOUT` và hiểu giá trị được nhận và xuất trở lại.
5. Gọi procedure bằng `CALL`, function bằng `SELECT` và nhận các giá trị trả về phù hợp.
6. Tạo hàm có `VARIADIC` để nhận nhiều giá trị hoặc nhận trực tiếp SQL array.
7. Hiểu tên tham số, đối số mặc định, positional/named notation và giới hạn overloading.
8. Nhận biết SQL NULL, input validation, exception/transaction behavior và bảo mật.
9. Xem chữ ký, modes và return types từ `pg_proc` hoặc các hàm hỗ trợ của catalog.
10. Viết Java/JDBC/Spring code gọi routine một cách an toàn, có xử lý lỗi và kiểm thử.

> **Môi trường:** Bài tập sử dụng PostgreSQL có hỗ trợ `CREATE PROCEDURE` (PostgreSQL 11+), `PL/pgSQL` và JDBC. Chi tiết về tham số `OUT` của procedure, cách hiện kết quả và điều kiện transaction control có thể khác giữa các phiên bản; hãy xem version của server trước khi áp dụng các ví dụ phụ thuộc tính năng ấy. SQL ví dụ chạy trong schema lab, không dùng dữ liệu production.

## 2. Function và procedure khác nhau

Hai đối tượng đều có tên, danh sách tham số và body. Tuy nhiên:

| Tiêu chí | Function | Procedure |
|---|---|---|
| Tạo bằng | `CREATE FUNCTION` | `CREATE PROCEDURE` |
| Gọi thông thường | `SELECT function(...)` hoặc trong biểu thức SQL | `CALL procedure(...)` |
| Dùng làm biểu thức trong SELECT, WHERE | Có khi return type/phép dùng phù hợp | Không |
| Trả kết quả | `RETURNS`, `OUT`, `INOUT`, `RETURNS TABLE`, `SETOF` | Tham số output của `CALL` |
| Transaction control nội bộ | Không cho phép `COMMIT`/`ROLLBACK` transaction | Có thể được phép trong điều kiện gọi cụ thể |
| Dùng `IN` | Có | Có |
| Dùng `OUT` | Có | Có ở các phiên bản PostgreSQL hỗ trợ |
| Dùng `INOUT` | Có | Có |
| Dùng `VARIADIC` | Có | Có khi được hỗ trợ trong định nghĩa tương ứng |

### Một nguyên tắc thiết kế

**Function** phù hợp khi cần trả kết quả có thể tham gia query khác. **Procedure** phù hợp khi thực hiện một thao tác có ý nghĩa nghiệp vụ và dùng `CALL`, có thể nhận các tham số đầu ra. Không chọn procedure chỉ vì muốn sửa dữ liệu: function cũng có thể thực hiện side effects trong những điều kiện cho phép, nhưng không có quyền transaction control như procedure.

Đừng nhầm `CALL` với `SELECT`: PostgreSQL không tự chuyển một function thành procedure chỉ vì hai đối tượng có tên/đối số tương tự.

## 3. Tổng quan bốn chế độ tham số

| Chế độ | Có nhận giá trị từ người gọi? | Có đóng góp vào kết quả đầu ra? | Ý tưởng |
|---|---|---|---|
| `IN` | Có | Không tự động | Chỉ truyền dữ liệu vào |
| `OUT` | Không phải input có ý nghĩa | Có | Ô nhận kết quả |
| `INOUT` | Có | Có | Nhận giá trị ban đầu và trả giá trị cuối |
| `VARIADIC` | Có, nhận nhiều đối số cùng kiểu phần tử hoặc một mảng | Không tự động | Danh sách đầu vào có độ dài thay đổi |

Ví dụ hình dung:

```text
IN:
  caller 7 -----> function(p_value=7)
                function RETURN ...

OUT:
  caller inputs -----> function
                        ├── OUT total
                        └── OUT average
  caller nhận các cột/giá trị kết quả

INOUT:
  caller 7 -----> routine(p_value=7) -----> caller nhận giá trị mới

VARIADIC:
  caller (2, 4, 6, 8) -----> routine(p_values int[]) 
```

### Chú ý: default mode là IN

Khai báo:

```sql
CREATE FUNCTION demo(p_number integer) ...
```

tương đương về chế độ với:

```sql
CREATE FUNCTION demo(IN p_number integer) ...
```

Không viết `OUT` trong chữ ký khi thật sự chỉ cần một tham số đầu vào.

## 4. Chuẩn bị schema học tập

```sql
CREATE SCHEMA IF NOT EXISTS lesson_param_modes;
```

Tất cả đối tượng trong bài dùng tên có schema để tránh lẫn với hàm của ứng dụng hoặc functions cùng tên từ `search_path`.

Kiểm tra server:

```sql
SELECT
    current_database() AS database_name,
    current_setting('server_version') AS server_version,
    current_setting('server_version_num') AS version_num;
```

Nếu đã thử bài trước và tạo các routines cùng tên nhưng khác định nghĩa, hãy quản lý bằng migration rõ ràng; không tự dùng `DROP SCHEMA ... CASCADE` trong môi trường có dữ liệu quan trọng.

## 5. IN: nhận giá trị đầu vào

Hàm tính diện tích hình chữ nhật:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.rectangle_area(
    IN p_width numeric,
    IN p_height numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT p_width * p_height;
$$;
```

Gọi:

```sql
SELECT lesson_param_modes.rectangle_area(4, 6) AS area;
-- area = 24

SELECT lesson_param_modes.rectangle_area(2.5, 8) AS area;
-- area = 20.0 về mặt giá trị numeric
```

### Ý nghĩa của IN

- `p_width` và `p_height` lấy giá trị từ phía người gọi.
- Trong SQL function, chúng có thể được tham chiếu theo tên hoặc vị trí theo cú pháp hợp lệ.
- Chế độ `IN` **không tự làm phát sinh một cột kết quả**.
- Giá trị kết quả ở đây đến từ `RETURNS numeric` và biểu thức cuối của SQL function.

`IMMUTABLE` có ý nghĩa khai báo tính chất hàm: với cùng inputs luôn cho cùng kết quả và không phụ thuộc state bên ngoài. `STRICT` yêu cầu trả NULL ngay khi bất kỳ đối số đầu vào thuộc diện áp dụng là SQL NULL; chỉ dùng các thuộc tính này khi logic thật sự đáp ứng.

## 6. IN là mặc định; ví dụ PL/pgSQL

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.discounted_price(
    p_price numeric,
    p_percent numeric
)
RETURNS numeric
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_price IS NULL OR p_percent IS NULL THEN
        RETURN NULL;
    END IF;

    IF p_price < 0 THEN
        RAISE EXCEPTION
            'Price must be nonnegative';
    END IF;

    IF p_percent < 0 OR p_percent > 100 THEN
        RAISE EXCEPTION
            'Percent must be between 0 and 100';
    END IF;

    RETURN round(p_price * (1 - p_percent / 100), 2);
END;
$$;
```

Gọi:

```sql
SELECT lesson_param_modes.discounted_price(100000, 15);
-- 85000.00

SELECT lesson_param_modes.discounted_price(100000, NULL);
-- NULL
```

Không dùng `STRICT` cho ví dụ này vì muốn minh họa kiểm tra `NULL` trong body. Nếu khai báo `STRICT`, PostgreSQL có thể bỏ qua body khi input NULL, nên một số điều kiện kiểm tra/ghi log trong body sẽ không được chạy.

## 7. IN không đồng nghĩa Java pass-by-reference

Trong PL/pgSQL, tham số có thể được tham chiếu và một số biến tham số có thể được gán lại trong phạm vi thực thi. Tuy nhiên, **gán lại một biến IN không làm tự động cập nhật biến Java hoặc biến SQL ở phía caller**.

Ví dụ:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.local_change(
    IN p_value integer
)
RETURNS integer
LANGUAGE plpgsql
AS $$
BEGIN
    p_value := p_value + 10;
    RETURN p_value;
END;
$$;

SELECT lesson_param_modes.local_change(5);
-- 15
```

Giá trị 15 được nhận nhờ **RETURN**, không phải vì PostgreSQL thay đổi một biến bên ngoài function. Để biểu diễn tham số đồng thời vào và ra như một giao diện, dùng `INOUT`.

## 8. IN với tên tham số và positional notation

Một lời gọi thông thường truyền đối số theo thứ tự:

```sql
SELECT lesson_param_modes.discounted_price(200000, 10);
```

Đối số thứ nhất vào `p_price`, thứ hai vào `p_percent`. Đây là **positional notation**.

Có thể gọi bằng tên:

```sql
SELECT lesson_param_modes.discounted_price(
    p_percent => 10,
    p_price => 200000
);
```

`=>` là named-argument notation, giúp giảm lỗi đảo thứ tự khi có nhiều input cùng kiểu. Tên tham số có thể trở thành phần của API routine; đổi tên bừa bãi có thể làm hỏng code gọi bằng tên.

### Không phải tên OUT cũng cần truyền

Với function, các tham số chỉ `OUT` không phải những đối số input cần đưa vào `SELECT function(...)`. Đó là khác biệt quan trọng ở phần tiếp theo.

## 9. OUT: một tham số kết quả

Function có thể khai báo kiểu trả về qua một tham số `OUT`:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.double_value(
    IN p_value integer,
    OUT p_double integer
)
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    p_double := p_value * 2;
END;
$$;
```

Gọi:

```sql
SELECT lesson_param_modes.double_value(7) AS result;
-- result = 14
```

### Điểm cần nhớ

- Caller **chỉ truyền** `p_value`.
- `p_double` là biến output và đồng thời xác định kiểu kết quả trả về.
- Không cần khai báo thêm `RETURNS integer` khi đã chọn lối khai báo trả về thông qua `OUT`.
- Khi PL/pgSQL function chạy đến cuối, giá trị output parameter xác định kết quả.

Với PL/pgSQL function có OUT parameters, `RETURN;` **không mang biểu thức** là cách kết thúc sớm và trả giá trị OUT hiện tại.

## 10. OUT: trả nhiều trường cùng lúc

Giả sử cần đồng thời tính tổng và tích của hai số:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.sum_and_product(
    IN p_a integer,
    IN p_b integer,
    OUT o_sum bigint,
    OUT o_product bigint
)
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    o_sum := p_a::bigint + p_b::bigint;
    o_product := p_a::bigint * p_b::bigint;
END;
$$;
```

Gọi như một bảng có cột kết quả:

```sql
SELECT *
FROM lesson_param_modes.sum_and_product(7, 4);

-- o_sum | o_product
-- ------+----------
-- 11    | 28
```

Hoặc lấy giá trị tổng hợp dưới dạng một composite value:

```sql
SELECT lesson_param_modes.sum_and_product(7, 4);
```

Với **nhiều OUT parameters**, return type có thể được biểu diễn là một composite/record với các trường được khai báo. Khi viết `SELECT * FROM function(...)`, các trường đó được trải thành cột.

### Khi nào nên dùng nhiều OUT?

- Một phép tính trả nhiều giá trị gắn liền.
- Kết quả có cấu trúc rõ và số trường nhỏ.
- Client thuận tiện đọc qua các cột SQL.

Không cố đưa một danh sách hàng không giới hạn vào nhiều OUT parameters cố định; khi cần trả nhiều hàng, xét `RETURNS TABLE`/`SETOF`.

## 11. Trả OUT sớm trong PL/pgSQL

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.describe_number(
    IN p_value integer,
    OUT o_label text,
    OUT o_absolute bigint
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_value IS NULL THEN
        o_label := 'missing';
        o_absolute := NULL;
        RETURN;
    END IF;

    IF p_value < 0 THEN
        o_label := 'negative';
    ELSIF p_value = 0 THEN
        o_label := 'zero';
    ELSE
        o_label := 'positive';
    END IF;

    o_absolute := abs(p_value::bigint);
END;
$$;
```

`RETURN;` không trả một expression mới; nó kết thúc với **giá trị hiện thời của các tham số đầu ra**.

Gọi:

```sql
SELECT *
FROM lesson_param_modes.describe_number(-9);

SELECT *
FROM lesson_param_modes.describe_number(NULL);
```

### Bẫy bỏ sót gán OUT

Nếu một OUT parameter chưa được gán trong đường thực thi, nó có thể vẫn có giá trị NULL. Một function trả kết quả thành công nhưng thiếu trường bắt buộc là **lỗi logic nghiệp vụ** cần validation/test, không phải PostgreSQL tự báo lỗi cho mọi trường hợp.

## 12. OUT không tham gia danh sách đầu vào của function

Hàm:

```sql
lesson_param_modes.sum_and_product(
    IN p_a integer,
    IN p_b integer,
    OUT o_sum bigint,
    OUT o_product bigint
)
```

được **gọi** bằng hai đối số:

```sql
SELECT *
FROM lesson_param_modes.sum_and_product(7, 4);
```

Không phải:

```sql
-- Không đúng cách gọi function có OUT-only:
SELECT *
FROM lesson_param_modes.sum_and_product(
    7, 4, NULL, NULL
);
```

### Vai trò với function identity

Trong PostgreSQL, chữ ký dùng để nhận diện/overload function dựa trên **các kiểu đối số đầu vào**, bao gồm `IN`/`INOUT` và phần tử `VARIADIC` theo quy tắc. Những `OUT`-only không tạo thành một overload khác chỉ vì trả về kiểu khác.

Điều này ảnh hưởng `DROP FUNCTION`, catalog, overloading và cách client chọn routine.

## 13. INOUT: nhận giá trị và trả kết quả cập nhật

`INOUT` kết hợp vai trò input với output.

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.increase_counter(
    INOUT p_counter bigint,
    IN p_delta bigint
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_counter IS NULL OR p_delta IS NULL THEN
        RAISE EXCEPTION 'Counter and delta are required';
    END IF;

    p_counter := p_counter + p_delta;
END;
$$;

SELECT lesson_param_modes.increase_counter(10, 5);
-- 15
```

Caller **truyền vào** 10 cho `p_counter` và **nhận lại** giá trị 15 làm kết quả function.

### Vì sao không chỉ dùng IN rồi RETURN?

Về khả năng tính toán, hai cách có thể tương đương với một output. `INOUT` thể hiện rõ giao diện “giá trị trạng thái vào/ra” trong chữ ký, hữu ích khi tương tác với procedures hoặc nhiều output. Tuy nhiên, không có nghĩa INOUT sửa trực tiếp biến Java caller như tham chiếu trong một số ngôn ngữ.

## 14. INOUT với nhiều kết quả

Một routine có thể có nhiều tham số `INOUT`:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.swap_numbers(
    INOUT p_first integer,
    INOUT p_second integer
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_temp integer;
BEGIN
    v_temp := p_first;
    p_first := p_second;
    p_second := v_temp;
END;
$$;

SELECT *
FROM lesson_param_modes.swap_numbers(12, 99);

-- p_first | p_second
-- --------+---------
-- 99      | 12
```

### INOUT tham gia cả chữ ký và kết quả

Khác `OUT`-only, hai kiểu `integer` của `p_first` và `p_second` là **input types**, nên tham gia định danh function và overload resolution.

Kết quả trả về là hai cột tương ứng giá trị cuối.

### Kịch bản dùng tốt

Việc swap ở đây chủ yếu để minh họa modes. Trong thiết kế ứng dụng thực, một function trả record/JSON rõ tên có thể dễ đọc hơn nếu input chỉ để tính toán chứ không thật sự là biến trạng thái cần cập nhật.

## 15. Kết hợp IN, OUT, INOUT trong một function

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.apply_fee(
    IN p_fee numeric,
    INOUT p_balance numeric,
    OUT o_applied boolean
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_fee IS NULL OR p_balance IS NULL THEN
        RAISE EXCEPTION 'Fee and balance cannot be NULL';
    END IF;

    IF p_fee < 0 OR p_balance < 0 THEN
        RAISE EXCEPTION 'Values must be nonnegative';
    END IF;

    IF p_balance < p_fee THEN
        o_applied := false;
    ELSE
        p_balance := p_balance - p_fee;
        o_applied := true;
    END IF;
END;
$$;
```

Gọi:

```sql
SELECT *
FROM lesson_param_modes.apply_fee(25, 100);

-- p_balance | o_applied
-- ----------+----------
-- 75        | true

SELECT *
FROM lesson_param_modes.apply_fee(250, 100);

-- 100       | false
```

### Diễn giải

`p_fee`: chỉ IN, không xuất trực tiếp.

`p_balance`: INOUT, nhận số dư ban đầu và trả số dư cuối.

`o_applied`: OUT-only, báo có áp dụng được hay không.

Hàm này **chỉ tính giá trị** chứ không trừ số dư trên một hàng tài khoản thực. Một hệ thống thanh toán thật cần transaction, locking/constraints, idempotency, ghi sổ và các quy tắc tài chính. Đừng dùng ví dụ function thuần tính toán này để thay atomic UPDATE trên bảng tài khoản.

## 16. Function với OUT và cách gọi SELECT

Có hai hình thức khác nhau:

```sql
-- Dạng giá trị composite:
SELECT lesson_param_modes.sum_and_product(3, 5);

-- Dạng các cột:
SELECT *
FROM lesson_param_modes.sum_and_product(3, 5);
```

Khi dùng function trong `FROM`, các output fields là cột có tên thuận tiện cho JDBC/SQL.

Nếu cần dùng kết quả trong một truy vấn khác:

```sql
SELECT
    s.o_sum,
    s.o_product,
    s.o_sum + s.o_product AS combined
FROM lesson_param_modes.sum_and_product(3, 5) AS s;
```

### Không gọi OUT-only như một đối số

Đối với function, số lượng giá trị truyền theo cách gọi dựa trên input parameters, không bao gồm OUT-only. Gọi `sum_and_product(3,5,NULL,NULL)` sẽ tìm một overload khác có bốn inputs và thường lỗi.

## 17. RETURNS TABLE so với nhiều OUT

PostgreSQL hỗ trợ:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.classify_values(
    p_min integer,
    p_max integer
)
RETURNS TABLE (
    value integer,
    parity text
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        g,
        CASE WHEN g % 2 = 0
             THEN 'even' ELSE 'odd' END
    FROM generate_series(p_min, p_max) AS g;
$$;
```

Gọi:

```sql
SELECT *
FROM lesson_param_modes.classify_values(2, 5);
```

Kết quả gồm **nhiều hàng**, mỗi hàng có `value` và `parity`. `RETURNS TABLE` ngụ ý set-returning result với những output column definitions.

### Khác với nhiều OUT thông thường

- Function `sum_and_product` với nhiều OUT trả **một record** cho một lần gọi.
- Function `classify_values` với `RETURNS TABLE` có thể trả **0, 1 hoặc nhiều rows**.
- Cú pháp `RETURNS TABLE(...)` không được trộn tùy tiện với khai báo `OUT`/`INOUT` cho cùng danh sách output; chọn một kiểu giao diện nhất quán.

Không dùng `OUT` cho một danh sách biến thiên chỉ vì muốn nhìn giống bảng. Khi cần nhiều hàng, thiết kế set-returning function phù hợp.

## 18. PL/pgSQL với RETURNS TABLE và RETURN QUERY

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.multiples_of(
    p_number integer,
    p_max_multiplier integer
)
RETURNS TABLE (
    multiplier integer,
    result bigint
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_max_multiplier IS NULL OR p_max_multiplier < 0 THEN
        RAISE EXCEPTION 'Max multiplier must be nonnegative';
    END IF;

    RETURN QUERY
    SELECT
        g,
        p_number::bigint * g
    FROM generate_series(1, p_max_multiplier) AS g;
END;
$$;

SELECT *
FROM lesson_param_modes.multiples_of(7, 4);
```

`RETURN QUERY` bổ sung rows vào tập kết quả mà function trả. `RETURN;` kết thúc việc sinh rows theo cú pháp PL/pgSQL thích hợp. Đừng nhầm `RETURN QUERY` với việc gán vào một biến OUT scalar.

### Hành vi khi p_max_multiplier = 0

`generate_series(1,0)` không tạo hàng với bước mặc định dương, nên function có thể trả **0 rows**, khác một function có nhiều OUT tạo một row với các giá trị NULL.

## 19. Procedure: cách gọi CALL

Function ở các mục trước được gọi qua `SELECT`. Procedure dùng `CALL`.

```sql
CREATE OR REPLACE PROCEDURE lesson_param_modes.log_message(
    IN p_message text
)
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE 'Message: %', p_message;
END;
$$;

CALL lesson_param_modes.log_message('Hello PostgreSQL');
```

`RAISE NOTICE` là thông báo do server phát ra; không phải một result set SQL giống `SELECT function(...)`. Không dựa vào NOTICE làm API trả dữ liệu nghiệp vụ ổn định cho ứng dụng.

### Tại sao không viết SELECT procedure?

`SELECT lesson_param_modes.log_message(...)` không phải cú pháp gọi đúng đối tượng procedure. PostgreSQL phân biệt loại routine function/procedure; câu `CALL` cũng không thay cho `SELECT` khi gọi function.

## 20. Procedure với INOUT

```sql
CREATE OR REPLACE PROCEDURE lesson_param_modes.add_to_counter(
    INOUT p_counter integer,
    IN p_delta integer
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_counter IS NULL OR p_delta IS NULL THEN
        RAISE EXCEPTION 'Counter and delta required';
    END IF;

    p_counter := p_counter + p_delta;
END;
$$;
```

Gọi từ SQL:

```sql
CALL lesson_param_modes.add_to_counter(10, 7);
```

Một `CALL` có output parameters trả **một result row** chứa các giá trị output. Trong ví dụ này, `p_counter` cuối cùng là 17.

### CALL không phải UPDATE table

Nếu `p_counter` là một giá trị literal đầu vào, PostgreSQL trả giá trị mới trong output row; nó không cập nhật vĩnh viễn một cột database hoặc biến của ứng dụng chỉ vì cùng tên.

## 21. Procedure với OUT-only

Ở những phiên bản PostgreSQL hỗ trợ khai báo `OUT` cho procedure:

```sql
CREATE OR REPLACE PROCEDURE lesson_param_modes.tax_quote(
    IN p_subtotal numeric,
    IN p_rate numeric,
    OUT o_tax numeric,
    OUT o_total numeric
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_subtotal IS NULL OR p_rate IS NULL THEN
        RAISE EXCEPTION 'Subtotal and rate required';
    END IF;

    o_tax := round(p_subtotal * p_rate / 100, 2);
    o_total := p_subtotal + o_tax;
END;
$$;
```

Khi gọi ở mức SQL, có thể truyền `NULL` làm placeholder cho **OUT-only** parameters:

```sql
CALL lesson_param_modes.tax_quote(
    1000::numeric,
    10::numeric,
    NULL,
    NULL
);
```

Kết quả gồm hai cột `o_tax` và `o_total`, lần lượt 100 và 1100 về mặt giá trị.

### Điểm rất dễ nhầm

Với **function OUT-only**, caller không cung cấp những tham số OUT trong `SELECT function(...)`.

Với **procedure OUT-only trong SQL CALL**, PostgreSQL yêu cầu một đối số tương ứng ở vị trí output ngay cả khi đối số đó không được đánh giá theo quy tắc gọi `CALL`; dùng `NULL` là cách được tài liệu khuyến nghị cho khả năng tương thích.

**Đây là khác biệt của cú pháp gọi**, không phải OUT trở thành một giá trị input thực sự.

## 22. CALL từ khối PL/pgSQL

Khi gọi procedure có output parameters bên trong PL/pgSQL, các đối số output phải tương ứng với **biến có thể được gán** để nhận kết quả, thay vì placeholder literal.

Ví dụ:

```sql
DO $$
DECLARE
    v_counter integer := 10;
BEGIN
    CALL lesson_param_modes.add_to_counter(v_counter, 7);
    RAISE NOTICE 'New counter: %', v_counter;
END;
$$;
```

Giá trị `v_counter` trong block trở thành 17 sau CALL.

Với procedure có `OUT`:

```sql
DO $$
DECLARE
    v_tax numeric;
    v_total numeric;
BEGIN
    CALL lesson_param_modes.tax_quote(
        1000::numeric,
        10::numeric,
        v_tax,
        v_total
    );
    RAISE NOTICE 'Tax: %, total: %', v_tax, v_total;
END;
$$;
```

**Không dùng literal `NULL` thay các biến output trong PL/pgSQL CALL** nếu procedure cần gán kết quả cho caller. PL/pgSQL quản lý output thông qua biến đích.

## 23. Procedure với INOUT và cập nhật trạng thái có ràng buộc

```sql
CREATE OR REPLACE PROCEDURE lesson_param_modes.normalize_score(
    INOUT p_score numeric,
    IN p_min numeric,
    IN p_max numeric
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_score IS NULL OR p_min IS NULL OR p_max IS NULL THEN
        RAISE EXCEPTION 'Arguments cannot be NULL';
    END IF;

    IF p_min > p_max THEN
        RAISE EXCEPTION 'Invalid score interval';
    END IF;

    p_score := greatest(p_min, least(p_score, p_max));
END;
$$;

CALL lesson_param_modes.normalize_score(
    120::numeric,
    0::numeric,
    100::numeric
);
-- p_score = 100
```

Điều cần quan sát: INOUT có input ban đầu 120, được thay đổi trong procedure, và output cuối là 100. Người gọi nhận giá trị kết quả, nhưng **nếu muốn lưu vào bảng** cần thao tác INSERT/UPDATE riêng hoặc procedure tự thực thi DML có kiểm soát.

## 24. Tham số OUTPUT không phải exception channel

Không phải routine nào cũng nên có:

```text
OUT success boolean
OUT error_code text
OUT error_message text
```

Khi lỗi phải **hủy transaction hoặc từ chối thao tác**, PostgreSQL có `RAISE EXCEPTION`/SQLSTATE để báo lỗi. Một tham số OUT status có thể hữu ích cho các tình huống **nghiệp vụ hợp lệ** như “không có dữ liệu” hay “hạn mức không đủ”, nhưng đừng lặng lẽ trả `success=false` rồi commit thay đổi dở dang.

### Hai cấp độ

- **Business result**: được chấp nhận/không đủ điều kiện, trạng thái dự đoán được; có thể biểu diễn bằng OUT.
- **Database/system failure**: vi phạm constraint, deadlock, timeout, lỗi SQL; dùng SQLSTATE và transaction rollback đúng cách.

Thiết kế API phải quy định rõ những kết quả nào là bình thường, kết quả nào là exception.

## 25. VARIADIC: danh sách đối số độ dài thay đổi

`VARIADIC` cho phép một parameter nhận nhiều đối số cùng **kiểu phần tử** dưới dạng một SQL array trong implementation.

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.sum_values(
    VARIADIC p_numbers integer[]
)
RETURNS bigint
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT COALESCE(
        SUM(v.value::bigint),
        0::bigint
    )
    FROM unnest(p_numbers) AS v(value);
$$;
```

Gọi với nhiều số:

```sql
SELECT lesson_param_modes.sum_values(1, 2, 3, 4);
-- 10

SELECT lesson_param_modes.sum_values(10, -5);
-- 5
```

### VARIADIC là gì ở bên trong?

Trong body, `p_numbers` vẫn là một giá trị **`integer[]`**. PostgreSQL gói các đối số dạng `1,2,3,4` thành mảng theo cơ chế gọi VARIADIC.

`SUM(...)` trả NULL khi không có hàng; `COALESCE(...,0)` quyết định chính sách tổng của mảng rỗng bằng 0.

## 26. Truyền một array với từ khóa VARIADIC

Giả sử ứng dụng đã có SQL array:

```sql
SELECT lesson_param_modes.sum_values(
    VARIADIC ARRAY[1, 2, 3, 4]::integer[]
);
-- 10
```

Từ khóa **`VARIADIC` tại điểm gọi** nói rằng toàn bộ array này là đối số variadic, thay vì liệt kê từng phần tử thành các đối số vị trí.

Với mảng rỗng:

```sql
SELECT lesson_param_modes.sum_values(
    VARIADIC ARRAY[]::integer[]
);
-- 0 theo định nghĩa hàm trong bài
```

### Vì sao không viết sum_values(ARRAY[1,2])?

Khi function được khai báo `VARIADIC integer[]`, cách gọi từ danh sách phần tử và cách gọi truyền thẳng một array không phải lúc nào cũng được hiểu giống nhau. Để rõ ý định truyền mảng đã có, hãy viết **`VARIADIC ARRAY[...]`**.

Phân biệt với một function thông thường nhận `integer[]` mà không khai báo variadic; function thông thường nhận đúng một array argument.

## 27. VARIADIC kết hợp một input cố định

Ví dụ nối các mảnh văn bản bằng dấu phân cách:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.join_parts(
    IN p_separator text,
    VARIADIC p_parts text[]
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT COALESCE(
        array_to_string(p_parts, p_separator),
        ''
    );
$$;
```

Gọi:

```sql
SELECT lesson_param_modes.join_parts(
    ' / ',
    'PostgreSQL',
    'Functions',
    'Parameters'
);
-- PostgreSQL / Functions / Parameters

SELECT lesson_param_modes.join_parts(
    ',',
    VARIADIC ARRAY['IN', 'OUT', 'INOUT']::text[]
);
-- IN,OUT,INOUT
```

### Thứ tự parameter

`VARIADIC` phải ở **vị trí cuối trong số các tham số input** theo quy tắc khai báo routine. Những OUT-only parameters có thể có quy tắc vị trí riêng theo cú pháp, nhưng không nên xây giao diện khó hiểu với variadic input xen giữa nhiều output nếu không thật sự cần.

## 28. VARIADIC và NULL

Có ít nhất ba tình huống:

1. Mảng có phần tử NULL.
2. Toàn bộ mảng là SQL NULL.
3. Mảng rỗng.

Ví dụ:

```sql
SELECT lesson_param_modes.sum_values(
    VARIADIC ARRAY[1, NULL, 3]::integer[]
);
-- 4 vì SUM bỏ qua NULL

SELECT lesson_param_modes.sum_values(
    VARIADIC ARRAY[]::integer[]
);
-- 0

SELECT lesson_param_modes.sum_values(
    VARIADIC NULL::integer[]
);
```

Với hàm `sum_values` đã định nghĩa, `unnest(NULL::integer[])` không sinh hàng; `SUM` là NULL và `COALESCE` thành 0. Đây là **quy tắc do người viết function lựa chọn**, không phải mọi function variadic đều xem NULL array như empty array.

### Nếu cần phân biệt NULL và empty

Viết function `LANGUAGE plpgsql` kiểm tra `p_numbers IS NULL` rồi chọn trả NULL/raise exception trước khi dùng `unnest`. Đừng dùng `COALESCE` vô điều kiện nếu nghiệp vụ cần phát hiện dữ liệu thiếu.

## 29. VARIADIC không phải SQL *splat* tùy ý

VARIADIC trong PostgreSQL có kiểu array ở định nghĩa, không phải “nhận một danh sách bất kỳ gồm mọi kiểu khác nhau rồi runtime tự xử lý”.

Ví dụ:

```sql
VARIADIC p_numbers integer[]
```

thì các phần tử đầu vào phải tương thích kiểu integer theo quy tắc ép kiểu của PostgreSQL.

Không coi VARIADIC là một cơ chế nhận vô hạn cả object JSON, số và text tùy ý mà không có kiểu. Nếu cần payload có cấu trúc hỗn hợp, xem `jsonb`/composite types hoặc thiết kế giao diện routine rõ hơn.

## 30. VARIADIC và rủi ro cardinality lớn

Ví dụ caller gửi hàng chục nghìn giá trị:

```sql
SELECT lesson_param_modes.sum_values(
    VARIADIC ARRAY(
        SELECT g
        FROM generate_series(1, 10000) AS g
    )
);
```

Cú pháp trên thể hiện việc truyền một array sinh bởi subquery. Đó là khác với việc gửi một câu SQL chứa 10.000 đối số riêng lẻ.

### Chi phí

- Xây và truyền array.
- Memory/context của function.
- `unnest` và aggregation.
- Parse/plan nếu application tạo câu SQL với quá nhiều placeholders.
- Network payload nếu danh sách đến từ JDBC.

Nếu danh sách IDs rất lớn và cần JOIN nhiều lần, có thể dùng `unnest`/temp table/staging rows theo workload thay vì đẩy toàn bộ logic vào một variadic function.

Không dùng `VARIADIC` như lối thoát mọi vấn đề truyền tập dữ liệu lớn từ ứng dụng.

## 31. So sánh VARIADIC với array parameter thông thường

Hai functions sau có cùng mục tiêu tính tổng nhưng **giao diện gọi khác**:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.sum_array(
    IN p_numbers integer[]
)
RETURNS bigint
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT COALESCE(SUM(x::bigint), 0)
    FROM unnest(p_numbers) AS t(x);
$$;

-- Một array là một đối số đầu vào:
SELECT lesson_param_modes.sum_array(ARRAY[1, 2, 3]::integer[]);

-- Nhiều đối số trực tiếp:
SELECT lesson_param_modes.sum_values(1, 2, 3);

-- Truyền nguyên array cho function VARIADIC:
SELECT lesson_param_modes.sum_values(
    VARIADIC ARRAY[1, 2, 3]::integer[]
);
```

### Quyết định API

**Array thường** phù hợp khi Java/query đã có một danh sách SQL array và bạn muốn một chữ ký rõ ràng: nhận đúng một collection.

**VARIADIC** thuận tiện khi người viết SQL muốn truyền danh sách nhiều literals/expressions mà không tự dựng array.

Nếu ứng dụng chủ yếu gọi qua JDBC với `createArrayOf`, một function nhận array thông thường thường đơn giản hơn, nhưng đây là lựa chọn thiết kế chứ không phải giới hạn PostgreSQL.

## 32. Named notation và VARIADIC

Named-argument notation giúp gọi input theo tên:

```sql
SELECT lesson_param_modes.discounted_price(
    p_percent => 20,
    p_price => 50000
);
```

Với VARIADIC, named notation và cách truyền cả array có **quy tắc cú pháp riêng**. Để tránh nhầm số lượng đối số, cách dễ đọc cho một array có sẵn thường là:

```sql
SELECT lesson_param_modes.join_parts(
    ' - ',
    VARIADIC ARRAY['A', 'B', 'C']::text[]
);
```

Khi API chỉ có vài tham số, positional notation thường đủ rõ. Khi có nhiều input dễ đảo nhầm, hãy dùng named notation cho các tham số thường và kiểm tra trường hợp VARIADIC trong phiên bản PostgreSQL sử dụng.

### Vì sao tên tham số là một phần giao diện?

Nếu client dùng `p_price => ...`, việc đổi tên parameter thành `price_value` có thể phá lời gọi dù kiểu dữ liệu không đổi. Cần quản lý sự thay đổi tên như thay đổi public API.

## 33. DEFAULT cho tham số IN

Ví dụ một hàm làm tròn số:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.round_to(
    IN p_value numeric,
    IN p_scale integer DEFAULT 2
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT round(p_value, p_scale);
$$;
```

Gọi:

```sql
SELECT lesson_param_modes.round_to(12.3456);
-- 12.35

SELECT lesson_param_modes.round_to(12.3456, 3);
-- 12.346

SELECT lesson_param_modes.round_to(
    p_scale => 1,
    p_value => 12.3456
);
-- 12.3
```

### Default là gì?

Default expression giúp caller bỏ qua input không bắt buộc. Nó không tự biến tham số `IN` thành `OUT`, cũng không phải giá trị mặc định của mọi biến PL/pgSQL.

Trong danh sách input parameters của PostgreSQL, sau khi một tham số có default, các input parameters tiếp theo cũng phải có default theo quy tắc khai báo. Không đưa một input bắt buộc sau một input đã có default rồi kỳ vọng positional call vẫn không mơ hồ.

## 34. DEFAULT với INOUT và kết quả

`INOUT` là một input parameter nên có thể có default theo quy tắc về tham số đầu vào.

Ví dụ:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.bump_default(
    INOUT p_counter integer DEFAULT 0
)
LANGUAGE plpgsql
AS $$
BEGIN
    p_counter := COALESCE(p_counter, 0) + 1;
END;
$$;
```

Gọi:

```sql
SELECT lesson_param_modes.bump_default();
-- 1

SELECT lesson_param_modes.bump_default(40);
-- 41
```

### Phân biệt default và SQL NULL

Không truyền `p_counter` thì PostgreSQL dùng default 0. Truyền **SQL NULL tường minh** thì input là NULL, không tự thay bằng default. Trong ví dụ, `COALESCE` được dùng để chọn xử lý NULL thành 0; đây là quyết định nghiệp vụ trong body.

Không nên dùng default trên mọi tham số chỉ để làm function “gọi cho ngắn” nếu giá trị thiếu phải được xem là lỗi.

## 35. OUT-only không phải input default tùy ý

Một tham số `OUT` chỉ nhận kết quả, không phải input tùy chọn của caller. Do đó đừng thiết kế giao diện theo kiểu:

```sql
-- Ý tưởng sai: caller chọn OUT value bằng default.
-- OUT o_total numeric DEFAULT 0
```

Nếu muốn bảo đảm output ban đầu 0, hãy khởi tạo trong body:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.safe_total(
    IN p_value numeric,
    OUT o_total numeric
)
LANGUAGE plpgsql
AS $$
BEGIN
    o_total := COALESCE(p_value, 0);
END;
$$;
```

### Mặc định giá trị trong PL/pgSQL

Các biến, kể cả OUT parameters, có thể mang SQL NULL nếu chưa được gán. Việc khai báo mode OUT không tự đặt giá trị 0, false hoặc chuỗi rỗng. Luôn gán rõ trong mọi nhánh nếu hợp đồng API không chấp nhận NULL.

## 36. Positional, named và mixed notation

Ví dụ:

```sql
SELECT lesson_param_modes.discounted_price(
    100000,
    p_percent => 15
);
```

Đây là dạng **mixed notation**: đối số vị trí trước, đối số theo tên sau. Nếu muốn trộn, hãy tuân thủ quy tắc cú pháp của PostgreSQL: tránh đặt positional arguments tùy ý **sau** các named arguments.

### Lợi ích của named

- Tự tài liệu hóa khi có nhiều tham số cùng kiểu.
- Không phụ thuộc thứ tự tham số khi gọi toàn bộ bằng tên.
- Có thể bỏ qua tham số có default mà không phải truyền toàn bộ những đối số ở giữa.

### Rủi ro

- Rename parameter có thể phá ứng dụng.
- Khi overloading nhiều routines cùng tên, named notation có thể làm resolution phức tạp.
- Không dùng tên tham số như dữ liệu tùy ý do người dùng nhập trực tiếp vào SQL.

## 37. Overloading: nhiều hàm cùng tên

PostgreSQL cho phép functions cùng tên nếu danh sách kiểu input tạo thành chữ ký khác nhau:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.describe(
    IN p_value integer
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'integer: ' || p_value::text;
$$;

CREATE OR REPLACE FUNCTION lesson_param_modes.describe(
    IN p_value text
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'text: ' || p_value;
$$;
```

Gọi tường minh:

```sql
SELECT lesson_param_modes.describe(42::integer);
-- integer: 42

SELECT lesson_param_modes.describe('42'::text);
-- text: 42
```

### Unknown literals

Một literal chuỗi chưa ép kiểu có thể được PostgreSQL xem ở kiểu `unknown` trong quá trình resolution. Với nhiều overload, lựa chọn có thể không giống ý định người viết hoặc báo ambiguity.

Hãy cast rõ khi muốn chọn overload cụ thể, nhất là trong migrations/tests/JDBC.

## 38. Không overload chỉ bằng OUT/return type

Giả sử đã có:

```sql
lesson_param_modes.double_value(
    IN integer,
    OUT integer
)
```

Không tạo một function khác **cùng tên và cùng input types** nhưng chỉ thay thành `OUT text` để coi đó là một overload hợp lệ. PostgreSQL không chọn function chỉ bằng kiểu kết quả mong đợi.

Tương tự:

```text
f(IN x integer, OUT y integer)
f(IN x integer, OUT y text)
```

không phải hai chữ ký đầu vào phân biệt.

### Tại sao?

Khi parser nhìn `f(10)`, nó phải xác định routine từ tên và input argument types, trước khi biết sẽ đặt kết quả vào đâu. Nếu chỉ khác output, việc chọn routine sẽ mơ hồ.

Muốn API khác hẳn kiểu kết quả, cân nhắc **đổi tên** hoặc tạo **signature đầu vào thực sự khác** với ý nghĩa rõ ràng, không chèn tham số giả để đánh lừa overloading.

## 39. Overloading với DEFAULT: dễ mơ hồ

Giả sử cùng một schema có:

```text
calculate(integer)
calculate(integer, integer DEFAULT 1)
```

Lời gọi `calculate(7)` có thể khớp nhiều định nghĩa theo quy tắc defaults và resolution.

### Cách tránh

- Không thêm default parameters tùy tiện vào một họ overload cùng tên.
- Dùng tên rõ ý nghĩa hơn khi function phục vụ nhiệm vụ khác.
- Với API quan trọng, kiểm tra calls hiện có trước migration.
- Cast input parameters khi cần chọn đúng overload.
- Tránh cho untrusted schemas tham gia `search_path` của các calls có thể bị hijack.

Một overload hợp lệ về cú pháp chưa chắc là API dễ dùng hoặc an toàn.

## 40. VARIADIC và overload resolution

`VARIADIC` có thể biến một chữ ký dạng array thành khả năng nhận nhiều arguments cùng element type. Nếu có một function khác nhận đúng số scalar arguments, việc phân giải calls cần xem quy tắc ưu tiên/kiểu và schema.

Ví dụ một họ APIs:

```text
score(integer, integer)
score(VARIADIC integer[])
```

Lời gọi `score(1,2)` có thể liên quan cả hai candidates; không thiết kế overload như thế nếu không thật sự cần. Nguy cơ còn tăng với `unknown` literals, default parameters và `search_path` không đáng tin.

### Đề xuất

Nếu function nhận một SQL array là giao diện chủ đạo của Java, dùng tên `score_array(integer[])`. Nếu muốn cú pháp SQL nhiều arguments, dùng tên `score_values(VARIADIC integer[])`. Hai tên rõ ràng thường tốt hơn overload phức tạp chỉ nhằm tiết kiệm vài ký tự.

## 41. Catalog: tra định nghĩa function/procedure

PostgreSQL lưu routines trong `pg_catalog.pg_proc` và schema trong `pg_catalog.pg_namespace`.

```sql
SELECT
    n.nspname AS schema_name,
    p.proname AS routine_name,
    p.prokind AS routine_kind,
    p.oid::regprocedure AS identity,
    pg_get_function_arguments(p.oid) AS all_arguments,
    pg_get_function_identity_arguments(p.oid)
        AS identity_arguments,
    pg_get_function_result(p.oid) AS function_result
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE n.nspname = 'lesson_param_modes'
ORDER BY
    p.proname,
    pg_get_function_identity_arguments(p.oid);
```

### Đọc các trường

- `prokind`: loại routine; `f` thường là function, `p` là procedure, các giá trị khác dành cho aggregate/window.
- `pg_get_function_arguments`: trình bày danh sách khai báo, gồm modes, names/defaults phù hợp.
- `pg_get_function_identity_arguments`: danh sách đối số xác định identity của routine, phục vụ thao tác như `ALTER/DROP`.
- `pg_get_function_result`: kết quả hàm; procedure không dùng `RETURNS` như function.
- `oid::regprocedure`: hiển thị routine kèm kiểu input để phân biệt overload.

Những hàm hỗ trợ này thường dễ đọc hơn việc tự diễn giải toàn bộ các arrays nội bộ của `pg_proc`.

## 42. proargtypes, proallargtypes, proargmodes

Catalog có các thông tin:

| Cột | Ý nghĩa |
|---|---|
| `proargtypes` | Các type OIDs của **input-bearing arguments** dùng trong routine identity/calling |
| `proallargtypes` | Các type OIDs của tất cả arguments nếu cần lưu riêng đầy đủ |
| `proargmodes` | Mã chế độ tương ứng với từng argument, nếu có |
| `proargnames` | Tên các arguments theo thứ tự |
| `pronargdefaults` | Số input args có default expressions |
| `proargdefaults` | Biểu diễn nội bộ của default expressions |

Các mode codes thường thấy:

- `i`: IN.
- `o`: OUT.
- `b`: INOUT.
- `v`: VARIADIC.
- `t`: một cột dạng TABLE trong output tương ứng.

Tham số chỉ có IN có thể không khiến `proargmodes` được lưu thành một mảng đầy đủ theo cách bạn mong chờ; hãy dùng catalog helper functions khi chỉ cần hiển thị declaration.

### Câu lệnh xem metadata thô

```sql
SELECT
    p.proname,
    p.proargtypes,
    p.proallargtypes,
    p.proargmodes,
    p.proargnames,
    p.pronargdefaults
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE n.nspname = 'lesson_param_modes'
ORDER BY p.proname;
```

Đây là thông tin hệ thống, không phải một bảng business data; kiểu nội bộ/biểu diễn có thể có chi tiết thay đổi theo phiên bản.

## 43. DROP FUNCTION và DROP PROCEDURE đúng identity

Muốn xóa function `sum_and_product` có hai IN integer và hai OUT bigint:

```sql
-- Ví dụ DDL có tác dụng xóa; chỉ chạy khi chủ ý dọn lab:
DROP FUNCTION IF EXISTS
    lesson_param_modes.sum_and_product(integer, integer);
```

Không cần đưa hai OUT bigint vào danh sách input identity của lệnh xóa function.

Với procedure:

```sql
DROP PROCEDURE IF EXISTS
    lesson_param_modes.add_to_counter(integer, integer);
```

Khi thao tác trên production, nên lấy identity thực tế bằng catalog/`pg_get_function_identity_arguments`, rà soát dependencies và dùng migration có kiểm soát. **Không chạy DROP chỉ vì muốn thử API**.

### Vì sao không dùng DROP ROUTINE tên chung?

Nếu có nhiều overload, việc xóa bằng tên không đủ rõ ràng có thể báo ambiguity hoặc tác động không đúng đối tượng. Hãy dùng schema và identity types cụ thể.

## 44. CREATE OR REPLACE không đổi tùy tiện kiểu trả về

Một function đã tồn tại có:

```text
sum_and_product(integer, integer)
  RETURNS record với o_sum bigint, o_product bigint
```

Muốn thay một OUT từ bigint thành text không phải một thao tác body-only. PostgreSQL có hạn chế đối với việc dùng `CREATE OR REPLACE FUNCTION` để đổi return type/định nghĩa output. Có thể cần:

1. Tạo function mới tên khác hoặc version suffix.
2. Chuyển client sang signature mới.
3. Kiểm tra dependencies/views/permissions.
4. Loại bỏ function cũ bằng migration hợp lệ khi không còn client.

Không coi thêm/sửa OUT parameter như thay đổi nội bộ “không ảnh hưởng ứng dụng”: số cột, tên cột, kiểu dữ liệu và cách JDBC map result đều có thể thay đổi.

## 45. Schema-qualified call và search_path

Nếu viết:

```sql
SELECT calculate_tax(100, 10);
```

PostgreSQL phải tìm function theo `search_path` và quyết định overload. Nếu trong path có một schema mà user không đáng tin có quyền tạo routine, lời gọi không được ràng buộc chặt có thể gặp rủi ro lựa chọn nhầm routine hoặc lạm dụng overloading.

Trong code server-side quan trọng, nên sử dụng:

```sql
SELECT lesson_param_modes.discounted_price(
    100000::numeric,
    10::numeric
);
```

và cấu hình quyền tạo object trên schemas phù hợp.

### SECURITY DEFINER

Function chạy với quyền owner qua `SECURITY DEFINER` cần đặc biệt kiểm soát `search_path` và các objects động. Đừng dùng parameter modes như cơ chế cấp quyền: chúng chỉ diễn tả interface dữ liệu.

## 46. NULL trong IN, OUT và INOUT

| Mode | Với NULL | Rủi ro |
|---|---|---|
| IN | Caller có thể truyền SQL NULL nếu chữ ký/ràng buộc body cho phép | Tính toán NULL hoặc validation thất bại |
| OUT | Chưa được gán có thể còn SQL NULL | Caller nhận thiếu kết quả mà không có lỗi |
| INOUT | Có thể nhận NULL và trả NULL/giá trị khác theo logic | Mơ hồ giữa “thiếu” và “muốn reset” |
| VARIADIC | Mảng có NULL elements, toàn mảng NULL hoặc empty | Tổng hợp/unnest có semantics riêng |

### Ví dụ phân biệt NULL và default

```sql
SELECT lesson_param_modes.bump_default();
-- p_counter mặc định 0 rồi tăng lên 1

SELECT lesson_param_modes.bump_default(NULL);
-- Body dùng COALESCE(NULL, 0), kết quả vẫn 1
```

Nếu bỏ `COALESCE`, NULL cộng 1 thường ra NULL. Đó là hệ quả của SQL NULL, không phải một hành vi đặc biệt “INOUT giữ nguyên giá trị cũ”.

### Khi nào dùng STRICT?

`STRICT` trên function có thể tránh body được chạy khi input NULL theo quy tắc của PostgreSQL. Chỉ dùng khi **mong muốn trả NULL** và không cần xử lý/ghi nhận input thiếu trong body. Với routines cần ném exception tùy biến, có thể không chọn STRICT.

## 47. Kiểm soát overflow và kiểu dữ liệu

Trong ví dụ tổng/tích:

```sql
p_a::bigint * p_b::bigint
```

ép integer sang bigint trước để mở rộng miền giá trị trung gian. Nhưng bigint vẫn có giới hạn; với input rất lớn, phép tính có thể overflow.

Một function xử lý tiền tệ nên dùng `NUMERIC` với scale và quy tắc rounding rõ ràng, không mặc định dùng floating point cho dữ liệu cần chính xác tuyệt đối.

### Đừng chọn OUT type tùy ý

Nếu cần trả số lượng rows lớn hơn giới hạn integer, dùng bigint. Nếu một phép chia có thể có phần thập phân, output numeric/decimal phù hợp hơn integer. Return type là phần hợp đồng API, không chỉ để hàm compile.

## 48. Exception và SQLSTATE

Ví dụ:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.positive_square(
    IN p_value numeric,
    OUT o_square numeric
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_value IS NULL OR p_value <= 0 THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = 'Positive input required';
    END IF;

    o_square := p_value * p_value;
END;
$$;
```

`22023` là SQLSTATE thường biểu diễn invalid_parameter_value. Dùng mã lỗi theo ý nghĩa thực tế và không lộ bí mật trong message.

### Transaction state sau lỗi

Trong transaction tường minh, nếu một statement lỗi và không được xử lý bằng cơ chế exception/savepoint phù hợp, transaction chuyển sang trạng thái aborted và cần rollback. Đừng tiếp tục gửi calls cùng transaction rồi bỏ qua SQLSTATE `25P02`.

### Không nuốt lỗi bằng OUT false nếu cần atomicity

Khi routine ghi nhiều bảng và một thao tác thất bại, việc trả `o_success=false` sau khi đã ghi một phần mà không rollback có thể làm trạng thái dữ liệu sai. Cần exception/transaction boundary hoặc xử lý rollback rõ ràng.

## 49. Function volatility, STRICT và parallel safety

PostgreSQL cho phép khai báo những tính chất ngoài parameter modes:

- `IMMUTABLE`: kết quả không phụ thuộc state thay đổi ngoài inputs; phù hợp với nhiều hàm tính toán thuần túy.
- `STABLE`: không thay đổi trong phạm vi statement theo định nghĩa, có thể đọc trạng thái nhất định.
- `VOLATILE`: có thể thay đổi theo từng lần gọi, hoặc có side effects.
- `STRICT`: không gọi function body khi input NULL trong các ngữ cảnh áp dụng.
- `PARALLEL SAFE/RESTRICTED/UNSAFE`: khả năng chạy trong parallel worker theo đặc tính routine.

Modes `IN/OUT/INOUT/VARIADIC` **không tự quyết định** những thuộc tính này.

### Một lỗi thiết kế

Không khai báo `IMMUTABLE` cho function đọc giá hiện tại từ bảng chỉ vì nó chỉ nhận một `IN product_id` và trả một `OUT price`. Giá trong bảng có thể thay đổi; việc khai báo sai volatility có thể khiến planner tối ưu theo giả định không đúng.

## 50. Procedure và transaction control

Khác function, procedure có thể thực hiện transaction control `COMMIT`/`ROLLBACK` **trong một số điều kiện được PostgreSQL cho phép**, chẳng hạn một lời gọi `CALL` ở top-level phù hợp.

Nhưng **không phải mọi procedure đều được quyền COMMIT**:

- `CALL` nằm trong transaction block tường minh có thể ngăn transaction control bên trong.
- Chuỗi lệnh gọi lồng nhau và các lệnh trung gian có ảnh hưởng.
- `SECURITY DEFINER` procedure hoặc procedure có `SET` clause có hạn chế.
- Client framework/JDBC có transaction manager có thể điều khiển scope.

### Khuyến nghị

Nếu application dùng Spring `@Transactional` hoặc JDBC `setAutoCommit(false)`, hãy để transaction boundary ở application trừ khi có yêu cầu đặc biệt và hiểu rõ các điều kiện PostgreSQL. Không đặt `COMMIT` trong procedure chỉ vì nghĩ “thủ tục tự quản transaction”.

Tham số `OUT`/`INOUT` không tạo đặc quyền transaction control; đó là hai tính năng độc lập.

## 51. Procedure với DML và OUT kết quả nghiệp vụ

Giả sử muốn cập nhật tồn kho và trả số lượng mới. Cần bảng:

```sql
CREATE TABLE lesson_param_modes.inventory (
    product_id bigint PRIMARY KEY,
    quantity integer NOT NULL CHECK (quantity >= 0)
);

INSERT INTO lesson_param_modes.inventory (
    product_id, quantity
)
VALUES (1001, 15);
```

Một procedure cập nhật tồn kho nguyên tử theo điều kiện:

```sql
CREATE OR REPLACE PROCEDURE lesson_param_modes.try_reserve(
    IN p_product_id bigint,
    IN p_units integer,
    OUT o_reserved boolean,
    OUT o_remaining integer
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_units IS NULL OR p_units <= 0 THEN
        RAISE EXCEPTION 'Units must be positive';
    END IF;

    UPDATE lesson_param_modes.inventory
    SET quantity = quantity - p_units
    WHERE product_id = p_product_id
      AND quantity >= p_units
    RETURNING quantity INTO o_remaining;

    o_reserved := FOUND;

    IF NOT o_reserved THEN
        o_remaining := NULL;
    END IF;
END;
$$;
```

Gọi từ SQL (ở server version hỗ trợ OUT-only procedures):

```sql
CALL lesson_param_modes.try_reserve(
    1001::bigint,
    3,
    NULL,
    NULL
);

-- Có thể trả o_reserved=true, o_remaining=12
```

### Vì sao đây là atomic UPDATE?

`UPDATE ... WHERE quantity >= p_units` thực thi dưới cơ chế concurrency control của PostgreSQL, nên việc kiểm tra và trừ trong cùng statement tốt hơn mô hình application đọc quantity rồi ghi giá trị mới từ snapshot cũ.

### Còn thiếu gì để dùng production?

- Kiểm tra tenant/scope ownership của product.
- Idempotency của reservation request.
- Giao dịch với đơn hàng/payment.
- Xử lý timeout/deadlock và retry policy.
- Tạo ledger/audit khi nghiệp vụ yêu cầu.
- Phân biệt product không tồn tại và không đủ số lượng nếu cần.

Ví dụ có chủ đích tập trung vào **OUT parameters + DML**, không phải triển khai checkout hoàn chỉnh.

## 52. Phân biệt OUT result và RETURNING

Trong procedure trước:

```sql
UPDATE ... RETURNING quantity INTO o_remaining;
```

`RETURNING` là cú pháp của DML để trả các giá trị từ hàng vừa sửa. `INTO o_remaining` trong PL/pgSQL gán giá trị đó vào **biến OUT**.

Sau khi procedure kết thúc, `CALL` trả giá trị `o_remaining` cho client.

Đây là ba tầng:

```text
UPDATE inventory
  └── RETURNING quantity
        └── INTO o_remaining (biến PL/pgSQL OUT)
              └── CALL result row (trả cho client)
```

Không nhầm `UPDATE ... RETURNING` với `RETURN` của function hoặc output mode của argument. Các cơ chế phối hợp nhưng không thay thế nhau.

## 53. OUT và INOUT có giúp tránh nhiều round-trip?

Một procedure có thể trả nhiều kết quả trong một `CALL`, giảm số lần client phải gửi các câu SQL riêng để lấy thông tin liên quan.

Ví dụ `try_reserve` vừa cập nhật vừa cho biết thành công và số tồn còn lại.

Tuy nhiên:

- Một result row có nhiều cột không có nghĩa network round-trip bằng 0.
- Kết quả nhận được phải nhất quán trong transaction.
- Cần cân nhắc logic nghiệp vụ bị đóng chặt vào database so với service.
- Đừng gom mọi bước hệ thống ngoài PostgreSQL vào procedure với kỳ vọng một CALL sẽ transactionally điều khiển HTTP/payment.

Chọn ranh giới application/database dựa trên **atomicity, latency, reuse, maintainability và quyền truy cập**, không chỉ số lượng parameters.

## 54. JDBC: function với IN parameters

Đối với một function trả scalar, JDBC thường dùng `PreparedStatement` với `SELECT`:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public static BigDecimal discount(
        Connection conn,
        BigDecimal price,
        BigDecimal percent
) throws SQLException {
    String sql = """
        SELECT lesson_param_modes.discounted_price(?, ?)
        """;

    try (PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setBigDecimal(1, price);
        ps.setBigDecimal(2, percent);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new SQLException("Function returned no row");
            }
            return rs.getBigDecimal(1);
        }
    }
}
```

Java truyền hai `IN` arguments qua placeholders; giá trị trả về lấy từ `ResultSet`. Không có đối số thứ ba đại diện cho scalar RETURN.

### Kiểu dữ liệu

Sử dụng `BigDecimal` cho `NUMERIC` cần tính chính xác, không ép qua `double` nếu nghiệp vụ tài chính không chấp nhận floating-point rounding.

## 55. JDBC: nhiều OUT của function

Function `sum_and_product` trả hai cột:

```java
String sql = """
    SELECT o_sum, o_product
    FROM lesson_param_modes.sum_and_product(?, ?)
    """;

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setInt(1, 7);
    ps.setInt(2, 4);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            long sum = rs.getLong("o_sum");
            long product = rs.getLong("o_product");
            // Sử dụng hai trường kết quả.
        }
    }
}
```

Đây thường là lựa chọn JDBC **rõ ràng nhất** khi function có OUT parameters: coi nó như một truy vấn SELECT trả các cột. Đừng cố truyền giá trị cho `OUT o_sum`/`OUT o_product` trong `PreparedStatement`.

### JDBC getLong và NULL

Nếu output integer/bigint có thể NULL, `ResultSet.getLong(...)` trả giá trị primitive 0 và cần gọi `rs.wasNull()` để phân biệt NULL với số 0. Với object types, có thể dùng `getObject` theo kiểu phù hợp driver.

## 56. JDBC: gọi procedure bằng SQL CALL

PostgreSQL JDBC driver có hỗ trợ `CALL`. Cách dễ hiểu là gửi câu `CALL` trực tiếp bằng `PreparedStatement`:

```java
String sql = """
    CALL lesson_param_modes.add_to_counter(?, ?)
    """;

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setInt(1, 10);
    ps.setInt(2, 7);

    boolean hasResultSet = ps.execute();
    if (hasResultSet) {
        try (ResultSet rs = ps.getResultSet()) {
            if (rs.next()) {
                int updated = rs.getInt("p_counter");
                // updated = 17
            }
        }
    }
}
```

### Vì sao dùng execute()?

`CALL` có thể trả result row nếu có output parameters, nhưng một procedure chỉ có `IN` có thể không trả row như vậy. `execute()` cho phép ứng dụng kiểm tra có result set hay không, thay vì mặc định mọi CALL trả một SELECT result.

### SQL CALL với OUT-only

Với procedure `tax_quote`, câu SQL có thể là:

```sql
CALL lesson_param_modes.tax_quote(?, ?, NULL, NULL)
```

Ứng dụng bind **hai input thực sự**, sau đó đọc output columns từ result row. Cách này tránh phải register OUT parameters qua một escape syntax có cấu hình driver riêng.

## 57. JDBC CallableStatement: điểm cần biết

JDBC có `CallableStatement` với `registerOutParameter`:

```java
CallableStatement call = conn.prepareCall(
    "{call lesson_param_modes.add_to_counter(?, ?)}"
);
```

Nhưng với **PostgreSQL JDBC**, cú pháp JDBC escape `{call ...}` có thể được driver ánh xạ thành `SELECT` hoặc `CALL` tùy **escapeSyntaxCallMode** và cấu hình phiên bản driver.

### Khuyến nghị

- Nếu định gọi **procedure**, bảo đảm driver cấu hình escape syntax tạo `CALL` thực.
- Một thiết lập thường dùng là `escapeSyntaxCallMode=callIfNoReturn` theo tài liệu pgJDBC phù hợp.
- Với function trả value, thường dễ dùng `SELECT` và `ResultSet`.
- Khi cần `registerOutParameter`, kiểm tra kiểu JDBC tương ứng và behavior của driver/connection settings.
- Không viết code coi mọi `{call ...}` đều tự có transaction semantics giống nhau trên mọi JDBC drivers.

Ví dụ ở mục trước dùng SQL `CALL` trực tiếp để ít phụ thuộc driver escape translation hơn.

## 58. JDBC và mảng VARIADIC

Trong Java, nếu đã có một mảng:

```java
Integer[] values = {1, 2, 3, 4};
```

Hãy tạo SQL array và truyền vào function VARIADIC bằng syntax rõ:

```java
import java.sql.Array;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

Array sqlArray = conn.createArrayOf(
    "integer",
    values
);

try {
    String sql = """
        SELECT lesson_param_modes.sum_values(VARIADIC ?::integer[])
        """;

    try (PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setArray(1, sqlArray);

        try (ResultSet rs = ps.executeQuery()) {
            if (rs.next()) {
                long total = rs.getLong(1);
            }
        }
    }
} finally {
    sqlArray.free();
}
```

### Vì sao không sinh SQL có 1.000 dấu hỏi?

Một SQL array parameter giữ câu SQL ổn định hơn, dễ tái sử dụng prepared statement và ít lỗi interpolation. Nhưng với tập dữ liệu rất lớn, vẫn cần đo memory/network và cân nhắc staging/temporary table hoặc batch processing.

Với SQL array rỗng, `createArrayOf("integer", new Integer[0])` truyền mảng rỗng; cần hiểu semantics function đã định nghĩa cho input rỗng.

## 59. Spring JdbcTemplate và function OUT

Một function có nhiều OUT có thể được gọi như query:

```java
String sql = """
    SELECT o_sum, o_product
    FROM lesson_param_modes.sum_and_product(?, ?)
    """;

var result = jdbcTemplate.queryForObject(
    sql,
    (rs, rowNum) -> new SumAndProduct(
        rs.getLong("o_sum"),
        rs.getLong("o_product")
    ),
    7,
    4
);
```

`SumAndProduct` là record/class do ứng dụng định nghĩa. Không cần đưa hai OUT parameters vào JDBC input binding.

### Spring transaction

Khi gọi procedure thay đổi nhiều bảng, Spring transaction manager quản lý commit/rollback theo `@Transactional` khi được cấu hình đúng. Không dùng procedure có `COMMIT` bên trong một transaction do Spring quản lý trừ khi đã xác nhận điều kiện PostgreSQL và ranh giới giao dịch.

## 60. Khác biệt giữa OUT row và result set nhiều hàng

Một thủ tục `CALL` có thể trả **một hàng với các output columns**.

Một function `RETURNS TABLE` có thể trả **nhiều hàng**:

```sql
SELECT *
FROM lesson_param_modes.classify_values(1, 100);
```

Đừng thiết kế các output parameters kiểu:

```text
OUT row1
OUT row2
OUT row3
...
```

để mô phỏng một collection. Nếu nghiệp vụ trả tập dữ liệu, set-returning function hoặc một truy vấn SELECT thông thường thường biểu diễn tự nhiên hơn.

Một `OUT jsonb` có thể trả document linh hoạt, nhưng nó không tự cung cấp schema/keys contract như một bảng có cột typed.

## 61. SQL functions với OUT

Không phải `OUT` chỉ dùng được trong PL/pgSQL. Một SQL-language function cũng có thể trả các trường kết quả:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.text_stats(
    IN p_text text,
    OUT o_characters integer,
    OUT o_uppercase text
)
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT
        char_length(p_text),
        upper(p_text);
$$;

SELECT *
FROM lesson_param_modes.text_stats('PostgreSQL');
```

Ở đây kết quả của câu SELECT trong body phải **tương thích với cấu trúc outputs**. Không có biến PL/pgSQL để gán từng trường, vì body là SQL expression/query.

### Khi nào dùng SQL-language function?

Nếu logic là một biểu thức/SQL statement đơn giản, `LANGUAGE sql` ngắn gọn. Nếu cần branching, exception handling, loops hoặc nhiều câu lệnh thủ tục, `PL/pgSQL` thường dễ viết hơn.

## 62. Tham số có tên khi SQL là biểu thức phức tạp

Trong SQL function, input parameters có thể được tham chiếu bằng tên hoặc positional markers theo cú pháp:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.with_tax(
    p_amount numeric,
    p_tax_rate numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT $1 * (1 + $2 / 100);
$$;
```

`$1` và `$2` trong body SQL function là vị trí input arguments, **không phải JDBC placeholders**. Với tên tham số:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.with_tax_named(
    p_amount numeric,
    p_tax_rate numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT p_amount * (1 + p_tax_rate / 100);
$$;
```

### Chú ý về ambiguity

Nếu tên input parameter trùng tên cột của một bảng được dùng trong SQL function, việc phân giải tên có thể gây nhầm hoặc báo lỗi. Ưu tiên prefix `p_` cho tham số, `v_` cho biến cục bộ và schema-qualified table references.

## 63. Tham số mode và security

Một function:

```sql
CREATE FUNCTION admin_operation(
    IN p_user_id bigint,
    OUT o_success boolean
) ...
```

không hề bảo vệ quyền chỉ vì có `OUT o_success`. Người gọi vẫn có thể cố truyền ID của user khác.

### Các lớp bảo vệ

1. Kiểm soát quyền `EXECUTE` trên routine.
2. Kiểm soát quyền bảng (hoặc áp dụng `SECURITY DEFINER` có lý do và kiểm toán).
3. Kiểm tra user/tenant authorization từ context đáng tin.
4. Thiết kế `search_path` an toàn trong SECURITY DEFINER.
5. Không ghép parameter vào dynamic SQL để tránh injection.
6. Ghi audit phù hợp, không log bí mật.

### Cấp quyền rõ ràng

Ví dụ:

```sql
-- Chỉ thực hiện khi role app_reader đã tồn tại và có kế hoạch quyền:
-- GRANT EXECUTE ON FUNCTION
--     lesson_param_modes.sum_and_product(integer, integer)
-- TO app_reader;
```

Không giả định việc đặt function trong schema riêng tự tạo sandbox quyền.

## 64. Dynamic SQL: modes không ngăn injection

PL/pgSQL có `EXECUTE` để chạy SQL động, nhưng việc truyền dữ liệu qua IN parameters không tự bảo vệ nếu body nối thẳng SQL string.

Ví dụ cần lọc theo giá trị:

```sql
CREATE OR REPLACE FUNCTION lesson_param_modes.inventory_quantity(
    IN p_product_id bigint
)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_quantity integer;
BEGIN
    EXECUTE
        'SELECT quantity
           FROM lesson_param_modes.inventory
          WHERE product_id = $1'
    INTO v_quantity
    USING p_product_id;

    RETURN v_quantity;
END;
$$;
```

Trong dynamic SQL, `USING` bind values an toàn hơn so với tự nối chuỗi. Nếu tên bảng/cột phải động, chúng là SQL identifiers nên cần whitelist/`format('%I', ...)` đúng cách, không đưa raw client input thành SQL fragment.

### Khi không cần dynamic SQL

Ví dụ trên được viết động để minh họa `USING`, nhưng một `SELECT ... INTO` tĩnh thông thường đơn giản và dễ kiểm soát hơn. Chỉ dùng EXECUTE khi có nhu cầu thực sự.

## 65. Cách đặt tên parameters để tránh nhầm

Một convention:

| Vai trò | Gợi ý | Ví dụ |
|---|---|---|
| Input | `p_` | `p_tenant_id`, `p_amount` |
| Output | `o_` | `o_total`, `o_success` |
| Input-output | `p_` hoặc `io_` | `p_balance`, `io_counter` |
| Biến cục bộ | `v_` | `v_tax`, `v_count` |

Đây là **quy ước đặt tên**, không phải PostgreSQL syntax rule. Nó giúp đọc code PL/pgSQL khi query có cột trùng tên.

### Không phụ thuộc tên OUT cho mọi client

Một ứng dụng đọc result set theo **index** có thể không thấy lỗi khi đổi tên cột, còn ứng dụng đọc `rs.getLong("o_total")` sẽ bị ảnh hưởng. Nên xem tên OUT columns là một phần của contract khi API được dùng rộng rãi.

## 66. Chọn modes theo yêu cầu

| Yêu cầu | Gợi ý |
|---|---|
| Tính một số từ một hoặc nhiều input | `IN` + `RETURNS type` |
| Trả một số nhưng muốn đặt tên kết quả ở chữ ký | `IN` + một `OUT` |
| Trả nhiều giá trị cố định | Nhiều `OUT` hoặc composite type |
| Nhận trạng thái và trả trạng thái đã biến đổi | `INOUT` |
| Trả một tập có số hàng thay đổi | `RETURNS TABLE` / `SETOF` |
| Nhận danh sách số lượng đối số thay đổi | `VARIADIC type[]` |
| Client đã có SQL array | `IN type[]` hoặc `VARIADIC type[]` có gọi explicit |
| Thực hiện thao tác nghiệp vụ với một output row | Procedure + `OUT`/`INOUT` phù hợp |
| Chỉ xử lý không cần result row | Procedure với `IN` có thể phù hợp |
| SQL report/aggregation thông thường | Một câu `SELECT`/view có thể đủ, không nhất thiết viết routine |

### Một lưu ý thiết kế

Đừng chọn `INOUT` chỉ để tránh viết `RETURNS`. Nếu caller thực chất truyền input và muốn nhận một **giá trị khác loại**, `IN` + `RETURNS` hoặc `OUT` thường biểu đạt tự nhiên hơn.

## 67. Runbook khi gọi routine lỗi

**Bước 1 — Xác định gọi function hay procedure.** `SELECT` khác `CALL`.

**Bước 2 — In chữ ký thực:** dùng `pg_get_function_arguments` và identity arguments từ catalog.

**Bước 3 — Kiểm tra số lượng input:** Function OUT-only không tính vào số đối số truyền; procedure OUT-only trong SQL CALL cần placeholder theo quy tắc.

**Bước 4 — Kiểm tra kiểu:** integer vs bigint vs numeric vs text; cast rõ khi overload hoặc NULL literal gây ambiguity.

**Bước 5 — Kiểm tra DEFAULT:** có callable overload trùng/khó phân giải không?

**Bước 6 — Kiểm tra VARIADIC:** người gọi truyền các phần tử hay một array? Có viết `VARIADIC ARRAY[...]` khi truyền array không?

**Bước 7 — Kiểm tra permission/search_path:** tên schema-qualified và quyền EXECUTE.

**Bước 8 — Kiểm tra NULL/body exceptions:** SQLSTATE và transaction state.

**Bước 9 — Kiểm tra JDBC:** SQL CALL thực hay JDBC escape syntax bị driver map sang SELECT? Có đọc result set đúng không?

**Bước 10 — Khi migration:** Có đổi OUT shape/return type hoặc tên tham số làm client cũ hỏng không?

## 68. Những lỗi thường gặp và cách hiểu

**“function ... does not exist”** có thể do:

- Gọi với sai số/kiểu input.
- Gọi function bằng các OUT-only values như inputs.
- Không có cast khi overload/unknown type.
- Routine nằm ở schema khác hoặc `search_path` không chứa schema.

**“procedure ... does not exist”** có thể do:

- Nhầm `CALL` sang một function.
- Sai chữ ký/procedure chưa được tạo.
- Dùng CALL của phiên bản không hỗ trợ dạng OUT mong muốn.

**“function return type cannot be changed”** có thể xảy ra khi dùng `CREATE OR REPLACE` đổi output definition/return type của function hiện có.

**“current transaction is aborted”** xuất hiện sau lỗi trước đó trong transaction tường minh; cần rollback/savepoint phù hợp, không tiếp tục gọi routine như thể transaction vẫn hợp lệ.

**“cannot commit while a subtransaction is active”** hoặc transaction-control errors có thể xuất hiện khi procedure quản lý transaction trong phạm vi không được phép; kiểm tra cách `CALL` được bao bởi transaction/framework.

**“permission denied for function/procedure”**: modes không phải cấp quyền; cần `EXECUTE`/quyền schema và kiểm soát security definer.

## 69. Thực hành kết hợp function và procedure

Giả sử cần một giao diện tính chi phí và một giao diện cập nhật tồn kho. Ta phân biệt:

- `discounted_price(IN price, IN percent) RETURNS numeric`: hàm tính toán.
- `sum_and_product(IN a, IN b, OUT sum, OUT product)`: hàm trả nhiều fields.
- `increase_counter(INOUT counter, IN delta)`: hàm trả trạng thái biến đổi.
- `sum_values(VARIADIC integer[])`: hàm nhận số lượng giá trị khác nhau.
- `try_reserve(IN product_id, IN units, OUT reserved, OUT remaining)`: procedure có thao tác DML và một output row.

### Thử nhanh

```sql
SELECT lesson_param_modes.discounted_price(
    100000::numeric,
    20::numeric
);

SELECT *
FROM lesson_param_modes.sum_and_product(2, 9);

SELECT lesson_param_modes.increase_counter(
    10::bigint,
    3::bigint
);

SELECT lesson_param_modes.sum_values(1, 2, 3, 4);

SELECT lesson_param_modes.sum_values(
    VARIADIC ARRAY[1, 2, 3, 4]::integer[]
);
```

### Điều cần quan sát

Không có output-only arguments nào được truyền khi gọi function bằng SELECT. `INOUT` tham gia input, nên `increase_counter` cần hai đối số input trong ví dụ. `VARIADIC` có thể gọi qua từng scalar hoặc truyền nguyên array bằng từ khóa VARIADIC.

## 70. Thử procedure DML trong transaction lab

Giả sử đã tạo `inventory` và `try_reserve`:

```sql
BEGIN;

SELECT product_id, quantity
FROM lesson_param_modes.inventory
WHERE product_id = 1001;

CALL lesson_param_modes.try_reserve(
    1001::bigint,
    2,
    NULL,
    NULL
);

SELECT product_id, quantity
FROM lesson_param_modes.inventory
WHERE product_id = 1001;

ROLLBACK;
```

### Vì sao dùng ROLLBACK?

Lab muốn quan sát kết quả trong transaction nhưng **không giữ thay đổi tồn kho** cho những lượt thực hành sau. Procedure ví dụ không tự `COMMIT`/`ROLLBACK`, nên transaction tường minh của caller điều khiển việc giữ/hủy kết quả.

### Nếu CALL bị lỗi?

Trong transaction tường minh, exception không được xử lý làm transaction fail; cần `ROLLBACK`. Đừng tiếp tục update nhiều hàng với transaction đã ở trạng thái aborted.

## 71. Viết assertion nhỏ bằng PL/pgSQL

Một khối `DO` có thể giúp người học kiểm tra giả định về giá trị kết quả:

```sql
DO $$
DECLARE
    v_sum bigint;
    v_product bigint;
    v_swapped_first integer;
    v_swapped_second integer;
BEGIN
    SELECT o_sum, o_product
    INTO v_sum, v_product
    FROM lesson_param_modes.sum_and_product(7, 4);

    IF v_sum <> 11 OR v_product <> 28 THEN
        RAISE EXCEPTION 'Unexpected sum/product result';
    END IF;

    SELECT p_first, p_second
    INTO v_swapped_first, v_swapped_second
    FROM lesson_param_modes.swap_numbers(12, 99);

    IF v_swapped_first <> 99
       OR v_swapped_second <> 12 THEN
        RAISE EXCEPTION 'Unexpected swap result';
    END IF;
END;
$$;
```

### Vì sao kiểm tra bằng SELECT?

Với function, output parameters đã trở thành cột kết quả khi gọi dưới dạng `FROM`. Ứng dụng/test có thể lấy chúng theo tên.

Trong procedure, các output parameters được nhận từ `CALL`. Bên trong PL/pgSQL, caller cần biến đích cho OUT/INOUT, như các ví dụ `DO` ở phần trước.

Các khối assertion này là **ví dụ học tập**, không thay một bộ test đầy đủ về nulls, errors, concurrent requests hoặc overload resolution.

## 72. Giao diện tốt không chỉ là số lượng OUT

Giả sử function cần trả:

```text
customer_id
order_count
total_paid
last_order_at
currency_code
```

Có ít nhất ba cách:

1. Nhiều `OUT` columns cố định.
2. `RETURNS TABLE` nếu cần một tập hàng theo khách hàng.
3. Composite type có tên hoặc view/query thông thường.

### Khi nào composite type đáng xem?

Nếu cấu trúc trả về được tái sử dụng ở nhiều routines, một named composite type có thể giúp diễn đạt một contract rõ ràng. Nhưng việc đổi kiểu này cũng là schema migration có thể ảnh hưởng dependencies.

### Khi nào RETURNS TABLE phù hợp hơn?

Khi cần nhiều rows của cùng một cấu trúc. Nếu function trả đúng một record với các tổng số của **một khách**, nhiều OUT có thể gọn. Nếu function trả thống kê cho **tất cả khách**, RETURNS TABLE/SETOF là mô hình đúng.

### Tránh routine quá nhiều tham số

Một procedure có 25 IN/OUT fields dễ gây:

- Sai thứ tự khi CALL.
- Khó tương thích ngược.
- Khó test giá trị NULL/default.
- Khó mapping trong JDBC.
- Khó giữ quyền/validation đồng bộ.

Cân nhắc chia giao diện theo nhiệm vụ nghiệp vụ, sử dụng composite input/output khi phù hợp, hoặc để SQL SELECT trực tiếp nếu routine không mang thêm giá trị.

## 73. Ghi tài liệu chữ ký của routine

Một routine public nên được mô tả bằng:

- Tên đã có schema.
- Input types và điều kiện bắt buộc.
- Mode của từng tham số.
- Default values nếu có.
- Return shape: scalar, composite, result row hay set of rows.
- Ngữ nghĩa NULL.
- SQLSTATE khi input sai.
- Side effects/transaction expectations.
- Quyền `EXECUTE` và scope tenant.
- Ví dụ gọi SQL và JDBC.

Một bản hợp đồng API đơn giản cho ví dụ:

| Trường | Giá trị |
|---|---|
| Routine | `lesson_param_modes.try_reserve` |
| Kind | Procedure |
| `p_product_id` | `IN bigint`, ID sản phẩm |
| `p_units` | `IN integer`, số lượng dương |
| `o_reserved` | `OUT boolean`, true khi UPDATE thành công |
| `o_remaining` | `OUT integer`, tồn sau khi đặt chỗ; NULL nếu không đặt |
| Gọi SQL | `CALL ... (product_id, units, NULL, NULL)` |
| Side effect | Trừ số lượng tồn khi đủ |
| Transaction | Do caller quản lý, không tự commit |

Nếu thay đổi `o_remaining` từ integer sang text, cần coi đó là breaking change cho client phụ thuộc kiểu dữ liệu, dù SQL body vẫn có thể tạo một kết quả “đọc được”.

## 74. Triển khai thay đổi routine an toàn

### Thay body mà không đổi interface

Nếu chỉ sửa cách tính trong khi **input identity và return shape** không đổi, `CREATE OR REPLACE` có thể phù hợp, sau khi xem xét volatility, permissions và dependencies.

### Thêm input parameter có default

Có thể giảm số calls cần sửa, nhưng cần kiểm tra:

- Input defaults và trật tự.
- Existing overloads.
- Named calls từ Java/SQL.
- Resolution với unknown/NULL arguments.
- Các trường hợp positional call cũ.

### Đổi OUT names/types/number of columns

Ảnh hưởng kết quả mà callers đọc. Nên tạo routine version mới hoặc migration rõ ràng, chuyển clients rồi mới xóa routine cũ, thay vì giả định `CREATE OR REPLACE` có thể đổi mọi return type tại chỗ.

### Đổi IN thành INOUT

Chữ ký input có thể giống về kiểu nhưng **return contract thay đổi**; việc gọi và cách nhận kết quả của JDBC/SQL cũng có thể khác. Cần đánh giá như thay đổi API.

### Đổi IN array thành VARIADIC array

Người gọi có thể phải đổi cách truyền array, thêm `VARIADIC` tại call site, hoặc thay logic overload resolution. Đây không phải phép đổi cú pháp luôn trong suốt.

## 75. Bảng ghi nhớ cú pháp

| Mục tiêu | Mẫu cú pháp | Cách gọi |
|---|---|---|
| Function trả scalar | `(IN x int) RETURNS int` | `SELECT f(5)` |
| Function một OUT | `(IN x int, OUT y int)` | `SELECT f(5)` |
| Function nhiều OUT | `(IN x int, OUT a int, OUT b text)` | `SELECT * FROM f(5)` |
| Function INOUT | `(INOUT x int)` | `SELECT f(5)` |
| Procedure IN | `(IN x int)` | `CALL p(5)` |
| Procedure INOUT | `(INOUT x int)` | `CALL p(5)`; trả output row |
| Procedure OUT | `(IN x int, OUT y int)` | `CALL p(5,NULL)` tại mức SQL, phiên bản hỗ trợ |
| Function VARIADIC | `(VARIADIC xs int[])` | `SELECT f(1,2,3)` |
| VARIADIC truyền array | `(VARIADIC xs int[])` | `SELECT f(VARIADIC ARRAY[1,2,3])` |
| Set-returning | `RETURNS TABLE (col type, ...)` | `SELECT * FROM f(...)` |

**Chú ý:** Bảng trên diễn đạt nguyên tắc, không phải các function/procedure có tên `f/p` đã được tạo. Khi chạy, dùng routine cụ thể trong schema lab.

## 76. Bộ bài tập thực hành

### Bài 1 — IN mặc định

Tạo `rectangle_area(width numeric, height numeric) RETURNS numeric` không viết `IN` tường minh. Gọi với 4 và 6 rồi giải thích vì sao cả hai vẫn là tham số IN.

### Bài 2 — Named input

Gọi `discounted_price` với `p_percent => 10` đứng trước `p_price => 200000`. Kết quả có giống positional notation đúng thứ tự không?

### Bài 3 — IN không phải pass-by-reference

Viết hàm tăng `p_number` trong body rồi `RETURN`. Chứng minh caller nhận giá trị mới qua kết quả, không phải vì một biến SQL ngoài function bị thay đổi.

### Bài 4 — Một OUT scalar

Viết `double_value(IN p_value integer, OUT p_double integer)`. Gọi bằng một đối số, không truyền `p_double`.

### Bài 5 — Hai OUT

Dùng `sum_and_product` trả tổng/tích của 9 và 4. Giải thích vì sao `SELECT * FROM function` trả hai cột.

### Bài 6 — OUT và composite

So sánh `SELECT sum_and_product(9,4)` với `SELECT * FROM sum_and_product(9,4)`. Khi nào JDBC dễ đọc kết quả hơn?

### Bài 7 — OUT chưa gán

Tạo function có hai OUT nhưng một nhánh quên gán trường thứ hai. Trường đó trả gì? Đề xuất cách validation/đường gán rõ ràng.

### Bài 8 — RETURN không biểu thức

Viết function có OUT label/value và dùng `RETURN;` trong nhánh input NULL. Tại sao không viết `RETURN (label,value)` theo kiểu tùy tiện khi đã khai báo OUT?

### Bài 9 — INOUT đơn

Viết function `increase_counter(INOUT counter bigint, IN delta bigint)` rồi gọi với 10 và 5. Giải thích vai trò input/output của counter.

### Bài 10 — INOUT đôi

Tạo function swap hai biến `INOUT integer`. Đọc hai cột sau khi gọi bằng `SELECT * FROM`.

### Bài 11 — Kết hợp IN/OUT/INOUT

Tạo function áp dụng một khoản phí lên số dư ban đầu, trả lại số dư và cờ boolean thành công. Viết hai test cho đủ/không đủ số dư.

### Bài 12 — Function vs procedure

Tạo function trả một số và procedure in NOTICE. Gọi bằng `SELECT` và `CALL` tương ứng. Điều gì xảy ra nếu dùng sai loại lệnh?

### Bài 13 — Procedure INOUT

Gọi `add_to_counter(10,7)` bằng `CALL`. Giá trị nào xuất hiện trong result row?

### Bài 14 — OUT của procedure

Ở PostgreSQL version hỗ trợ, tạo `tax_quote(IN subtotal, IN rate, OUT tax, OUT total)`. Gọi từ SQL bằng `NULL` placeholders và đọc hai output columns.

### Bài 15 — CALL trong PL/pgSQL

Viết `DO` block có biến counter, gọi `add_to_counter` rồi in kết quả. Vì sao phải đưa biến có thể gán vào vị trí INOUT?

### Bài 16 — Procedure OUT trong DO

Trong `DO` block, khai báo `v_tax`/`v_total` và gọi `tax_quote`. Vì sao không truyền literal `NULL` như ví dụ SQL CALL?

### Bài 17 — Set-returning function

Tạo `classify_values` bằng `RETURNS TABLE(value integer, parity text)` trả nhiều hàng. So với một function hai OUT scalar.

### Bài 18 — RETURN QUERY

Viết PL/pgSQL function có `RETURNS TABLE` và `RETURN QUERY SELECT FROM generate_series`. Kiểm tra trường hợp số hàng bằng 0.

### Bài 19 — VARIADIC scalar list

Tạo `sum_values(VARIADIC integer[])`, gọi với 1,2,3,4 và giải thích body thấy biến gì.

### Bài 20 — VARIADIC array

Gọi function ở bài 19 bằng `VARIADIC ARRAY[1,2,3,4]::integer[]`. Tại sao cần từ khóa VARIADIC ở call site khi muốn truyền cả array?

### Bài 21 — VARIADIC empty

Gọi `sum_values(VARIADIC ARRAY[]::integer[])`. Kết quả là bao nhiêu theo định nghĩa `SUM/COALESCE` trong bài?

### Bài 22 — NULL phần tử

Gọi `sum_values(VARIADIC ARRAY[1,NULL,3]::integer[])`. Giải thích `SUM` xử lý NULL như thế nào.

### Bài 23 — NULL array

Gọi `sum_values(VARIADIC NULL::integer[])`. Viết phiên bản PL/pgSQL nếu yêu cầu phân biệt NULL array với empty array.

### Bài 24 — VARIADIC có input trước

Tạo `join_parts(separator text, VARIADIC parts text[])`. Gọi bằng ba string values rồi bằng một SQL array.

### Bài 25 — Array thường hay VARIADIC?

So sánh `sum_array(IN integer[])` với `sum_values(VARIADIC integer[])` về declaration và cách gọi. Nếu Java luôn gửi SQL array, bạn sẽ chọn giao diện nào?

### Bài 26 — DEFAULT parameter

Tạo `round_to(value numeric, scale integer DEFAULT 2)`. Gọi có và không truyền scale; giải thích việc truyền explicit NULL khác bỏ qua argument ra sao.

### Bài 27 — INOUT default

Gọi `bump_default()`, `bump_default(40)` và `bump_default(NULL)`. Xác định giá trị nhờ DEFAULT và COALESCE ở từng trường hợp.

### Bài 28 — Positional/named/mixed

Tạo function có ba input, trong đó hai tham số cuối có default. Viết lời gọi positional, named và mixed hợp lệ; nêu trường hợp dễ đảo thứ tự.

### Bài 29 — Overload theo input

Tạo hai functions `describe(integer)` và `describe(text)`. Gọi có cast tường minh để chắc chắn dùng overload muốn chọn.

### Bài 30 — Không overload bằng OUT

Giải thích vì sao không tạo được hai functions cùng tên/cùng input types mà chỉ khác OUT integer và OUT text để chọn theo return type.

### Bài 31 — Overload và default ambiguity

Phân tích một họ functions `f(integer)` và `f(integer, integer DEFAULT 1)`. Vì sao lời gọi một argument có thể mơ hồ?

### Bài 32 — System catalog

Truy vấn `pg_proc`, `pg_get_function_arguments` và `pg_get_function_identity_arguments` cho schema lab. Tìm ít nhất một mode `i`, `o`, `b` và `v`.

### Bài 33 — DROP đúng chữ ký

Viết `DROP FUNCTION` cho `sum_and_product(integer,integer)` mà không đặt OUT types vào input identity. Không chạy nếu còn muốn dùng bài thực hành.

### Bài 34 — Migration return type

Một client đang đọc OUT integer; bạn muốn đổi thành text. Đề xuất migration có version mới, kiểm tra dependencies và chuyển caller.

### Bài 35 — SQLSTATE

Gọi `positive_square(-2)`. Phân loại lỗi dựa trên `SQLSTATE 22023` và giải thích transaction state khi có lỗi.

### Bài 36 — Transaction của procedure

Gọi `try_reserve` trong `BEGIN ... ROLLBACK`, so sánh inventory trước/sau. Vì sao không đưa COMMIT vào procedure khi caller quản lý transaction?

### Bài 37 — JDBC function nhiều OUT

Viết `PreparedStatement` dùng `SELECT o_sum,o_product FROM sum_and_product(?,?)`. Vì sao chỉ bind hai input và đọc hai result columns?

### Bài 38 — JDBC CALL

Dùng `PreparedStatement` gửi `CALL add_to_counter(?, ?)`, gọi `execute()` rồi đọc result row. Giải thích điểm khác với `CallableStatement` escape syntax.

### Bài 39 — JDBC VARIADIC

Tạo `java.sql.Array` từ `Integer[]`, bind vào `SELECT sum_values(VARIADIC ?::integer[])`, sau đó giải phóng resources. Khi nào nên chọn array input không variadic?

### Bài 40 — Thiết kế hệ thống nghiệp vụ

Một hệ thống quản lý đơn hàng cần:

- Tính chiết khấu từ price/rate.
- Trả đồng thời tổng tiền và thuế.
- Nhận danh sách nhiều product IDs.
- Trừ tồn kho nguyên tử nếu đủ hàng.
- Gọi qua Java/Spring.
- Chặn request không đúng tenant.

Hãy đề xuất:

1. Routine nào nên là function `IN+RETURNS`, routine nào dùng `OUT`?
2. Khi nào `INOUT` thực sự diễn đạt đúng nghiệp vụ?
3. Có nên dùng `VARIADIC` hay một SQL array cho danh sách product IDs?
4. Procedure DML nào cần output success/remaining và transaction scope?
5. Thiết kế rights/SQLSTATE/idempotency/JDBC mapping ra sao?
6. Nếu thêm một OUT column mới, làm sao triển khai mà không phá client cũ?

## Kết luận

**`IN`, `OUT`, `INOUT` và `VARIADIC` là bốn cách mô tả hướng và hình dạng dữ liệu trong chữ ký hàm/thủ tục PostgreSQL.** `IN` đưa giá trị vào routine và là chế độ mặc định. `OUT` mô tả giá trị trả ra, không thuộc danh sách input identity của function. `INOUT` vừa nhận giá trị ban đầu vừa trả giá trị cuối, nên được tính như input khi gọi và có vai trò output. `VARIADIC` cho phép truyền nhiều scalar arguments có kiểu phần tử tương thích hoặc truyền một SQL array bằng từ khóa `VARIADIC` tại call site.

**Đừng nhầm function với procedure:** function được gọi bằng `SELECT`/trong biểu thức và có thể trả scalar, composite hoặc set of rows; procedure gọi bằng `CALL` và có thể trả một output row khi có OUT/INOUT. Đặc biệt, function không yêu cầu caller truyền OUT-only arguments, trong khi SQL `CALL` đối với procedure có OUT-only có thể yêu cầu placeholders `NULL`. Khi CALL được thực hiện trong PL/pgSQL, những vị trí output tương ứng với **biến nhận kết quả**.

Chọn giao diện theo nghiệp vụ: một scalar thường dùng `RETURNS`; một vài kết quả cố định có thể dùng OUT; danh sách nhiều hàng cần `RETURNS TABLE/SETOF`; một danh sách input động có thể dùng VARIADIC hoặc SQL array thường. Hãy kiểm soát **NULL, kiểu dữ liệu, overloading/defaults, tên arguments, permissions, search_path, transaction và SQLSTATE**, vì parameter modes không tự cung cấp validation hay authorization.

Trong ứng dụng Java/JDBC, thường dễ đọc nhất khi gọi function bằng `SELECT` và lấy giá trị từ `ResultSet`, còn procedure bằng SQL `CALL` hoặc `CallableStatement` đã được cấu hình đúng. Luôn bind tham số, kiểm soát transaction và xem thay đổi OUT types/names như thay đổi contract. Khi những quy tắc này rõ ràng, PostgreSQL functions/procedures trở thành API dữ liệu có thể tái sử dụng, có kiểu và dễ bảo trì thay vì một tập các câu lệnh có cú pháp giống nhau nhưng hành vi khó đoán.
