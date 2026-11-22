# Bao định danh và giá trị bằng dấu nháy để phòng tránh SQL injection trong PL/pgSQL

## 1. Bài toán: khi câu lệnh SQL được tạo từ chuỗi

Trong PostgreSQL, PL/pgSQL cho phép xây dựng và chạy câu lệnh SQL động:

```sql
EXECUTE v_sql;
```

Khả năng này hữu ích khi một phần cấu trúc SQL thay đổi tại thời điểm chạy: tên bảng lưu trữ theo kỳ, cột được chọn trong danh sách cho phép, tên schema của một ứng dụng quản trị, hoặc loại sắp xếp. Tuy nhiên, **SQL injection** có thể xuất hiện nếu lập trình viên nối dữ liệu không tin cậy trực tiếp vào câu SQL.

Ví dụ không an toàn:

```sql
v_sql :=
    'SELECT count(*) FROM quote_lab.orders ' ||
    'WHERE customer_code = ''' || p_customer_code || '''';

EXECUTE v_sql INTO v_count;
```

Nếu `p_customer_code` có dấu nháy đơn, câu lệnh có thể bị lỗi hoặc thay đổi ý nghĩa. Một giá trị chứa ký tự đặc biệt không được tự động hiểu là dữ liệu chỉ vì nó đến từ biến PL/pgSQL.

PostgreSQL cung cấp nhiều công cụ để xử lý đúng ba loại thành phần:

- **Định danh (identifier):** tên schema, bảng, cột, index, sequence, function.
- **Giá trị (data value):** mã khách hàng, số tiền, ngày, từ khóa, chuỗi ghi chú.
- **Cấu trúc SQL (SQL syntax):** `ORDER BY`, `ASC`/`DESC`, toán tử, tên relation hay phần DDL mà ứng dụng chủ động chọn.

```text
                  Giá trị đến từ request
                           |
               +-----------+------------+
               |                        |
       Giá trị dữ liệu              Tên object/cột
               |                        |
          Dùng USING            Kiểm tra allowlist
               |                        |
        $1, $2, $3...                %I / quote_ident
               |                        |
               +------------+-----------+
                            |
                   SQL text đã kiểm soát
                            |
                   PL/pgSQL EXECUTE
                            |
                 Còn phải kiểm tra QUYỀN
```

> **Ưu tiên số một:** với giá trị trong câu `SELECT`/`INSERT`/`UPDATE`/`DELETE` động, sử dụng `EXECUTE ... USING` thay vì chèn literal vào chuỗi. Với tên object/cột không thể truyền bằng parameter, dùng `format('%I', ...)` hoặc `quote_ident(...)`, **sau khi xác thực danh sách được phép**. Quoting chống nhầm cú pháp, không tự tạo ra quyền truy cập an toàn.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận biết ba lớp: SQL text, identifiers và data values.
2. Giải thích vai trò của `quote_ident`, `quote_literal` và `quote_nullable`.
3. Sử dụng đúng `format('%I')`, `format('%L')` và `format('%s')`.
4. Hiểu vì sao `%I` và `%L` không thể dùng thay thế nhau.
5. Hiểu xử lý `NULL` của `quote_literal`, `quote_nullable` và `format`.
6. Viết `EXECUTE ... USING` để bind giá trị có kiểu, tránh nối chuỗi.
7. Biết giới hạn: bind parameter không đại diện tên bảng, cột hoặc SQL keyword.
8. Tạo câu SQL với **schema và table name riêng biệt**, không quote dấu chấm như một tên đơn.
9. Dùng allowlist để bảo vệ dynamic table/column/sort direction.
10. Phân biệt injection qua literal, identifier, keyword và SQL pattern.
11. Tránh các sai lầm khi viết `LIKE`, `ILIKE` và regular expression với input người dùng.
12. Sử dụng `IS NOT DISTINCT FROM` khi cần so sánh `NULL` theo nghĩa “bằng”.
13. Xử lý dynamic `ORDER BY` và giới hạn `LIMIT` mà không cho phép SQL tùy ý.
14. Phân biệt PL/pgSQL `EXECUTE` và SQL `EXECUTE` của prepared statements.
15. Hiểu các đặc điểm plan caching của SQL tĩnh và dynamic SQL.
16. Viết PL/pgSQL function minh họa có đầy đủ kiểm tra input và câu lệnh an toàn.
17. Bảo vệ các `SECURITY DEFINER` routines bằng `search_path` tin cậy.
18. Kiểm thử với dấu nháy, ký tự Unicode, `NULL` và các chuỗi có ý định thay đổi cấu trúc SQL.
19. Nhận biết các tình huống utility DDL không cho bind values.
20. Áp dụng checklist review và bài tập trong ứng dụng Java/JDBC.

## 3. Đầu tiên: SQL text khác SQL value như thế nào?

Một câu SQL có cấu trúc cố định:

```sql
SELECT order_id, customer_code
FROM quote_lab.orders
WHERE customer_code = 'O''Reilly';
```

Ở đây:

- `SELECT`, `FROM`, `WHERE` là cú pháp SQL.
- `quote_lab.orders`, `order_id`, `customer_code` là định danh.
- `'O''Reilly'` là **một string literal**.

Chuỗi dữ liệu `O'Reilly` được biểu diễn trong literal SQL bằng **hai dấu nháy đơn** tại vị trí một dấu nháy nội dung.

Trong PL/pgSQL, thay vì tự tạo các cặp nháy đó, nên bind:

```sql
EXECUTE
    'SELECT count(*)
     FROM quote_lab.orders
     WHERE customer_code = $1'
INTO v_count
USING p_customer_code;
```

Giá trị `p_customer_code` không được nối thành source code SQL. PostgreSQL nhận nó như **parameter value** với type semantics phù hợp.

### 3.1. Identifier không phải string literal

```sql
SELECT order_id FROM quote_lab.orders;
```

Nếu viết:

```sql
SELECT 'order_id' FROM quote_lab.orders;
```

thì PostgreSQL trả **một giá trị text cố định** `order_id` trên mỗi row, không đọc cột `order_id`.

### 3.2. Double quotes và single quotes có vai trò khác nhau

- `'customer_code'`: literal chuỗi.
- `"customer_code"`: định danh cột.
- `"Customer Code"`: định danh giữ nguyên chữ hoa và dấu cách.
- `customer_code`: định danh không quote, chịu quy tắc gấp chữ thường của PostgreSQL.

### 3.3. “Đúng cú pháp” chưa chắc “đúng quyền”

`format('%I', 'salary')` có thể tạo tên cột SQL hợp lệ. Nhưng nếu người dùng không được phép truy cập cột `salary`, quote tên đó **không bảo vệ dữ liệu**.

**Quoting xử lý cấu trúc cú pháp. Authorization xử lý đối tượng và hàng được phép.**

## 4. Tạo phòng thí nghiệm PL/pgSQL

Chỉ chạy các lệnh này trong **database thử nghiệm**. Các ví dụ injection không yêu cầu và không khuyến khích tác động đến dữ liệu production.

### 4.1. Tạo schema và bảng

```sql
CREATE SCHEMA IF NOT EXISTS quote_lab;

CREATE TABLE quote_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL,
    customer_code text NOT NULL,
    status text NOT NULL
        CHECK (status IN (
            'NEW', 'PAID', 'CANCELLED'
        )),
    amount numeric(12,2) NOT NULL
        CHECK (amount >= 0),
    note text,
    created_at timestamptz NOT NULL
        DEFAULT clock_timestamp()
);
```

### 4.2. Nạp dữ liệu có dấu nháy và Unicode

```sql
INSERT INTO quote_lab.orders (
    tenant_id,
    customer_code,
    status,
    amount,
    note,
    created_at
)
VALUES
    (10, 'ALICE', 'NEW', 120.00, 'First order',
        timestamptz '2026-01-02 09:00:00+00'),
    (10, 'O''Reilly', 'PAID', 320.00, 'Customer''s note',
        timestamptz '2026-01-03 10:00:00+00'),
    (10, 'VN-ĐỎ', 'NEW', 42.00, NULL,
        timestamptz '2026-01-04 11:00:00+00'),
    (10, 'A%_B', 'PAID', 51.00, 'Contains wildcard characters',
        timestamptz '2026-01-05 12:00:00+00'),
    (20, 'ALICE', 'PAID', 999.00, 'Other tenant',
        timestamptz '2026-01-06 13:00:00+00'),
    (20, 'O''Reilly', 'CANCELLED', 777.00, NULL,
        timestamptz '2026-01-07 14:00:00+00');
```

Có hai tenants (10 và 20), các giá trị customer trùng tenant, dữ liệu Unicode, dấu nháy đơn, các wildcard `%`/`_` và `NULL`.

### 4.3. Tạo bảng dữ liệu lưu trữ để thực hành identifier động

```sql
CREATE TABLE quote_lab.orders_archive (
    order_id bigint PRIMARY KEY,
    tenant_id integer NOT NULL,
    customer_code text NOT NULL,
    status text NOT NULL,
    amount numeric(12,2) NOT NULL,
    note text,
    created_at timestamptz NOT NULL
);

INSERT INTO quote_lab.orders_archive (
    order_id, tenant_id, customer_code,
    status, amount, note, created_at
)
VALUES
    (1001, 10, 'ALICE', 'PAID', 10.00,
        'Old data', timestamptz '2025-01-01 00:00:00+00'),
    (1002, 20, 'BOB', 'PAID', 20.00,
        'Old data', timestamptz '2025-01-02 00:00:00+00');
```

Dữ liệu này minh họa hai table names **được hệ thống cho phép**, không phải mọi bảng trong database.

### 4.4. Thống kê cơ bản

```sql
ANALYZE quote_lab.orders;
ANALYZE quote_lab.orders_archive;

SELECT
    tenant_id,
    COUNT(*) AS orders_count,
    SUM(amount) AS total_amount
FROM quote_lab.orders
GROUP BY tenant_id
ORDER BY tenant_id;
```

Từ đây các ví dụ dùng schema `quote_lab` để dễ nhận biết đối tượng thật.

## 5. `quote_ident(text)`: quote tên SQL identifier

Hàm `quote_ident` nhận **một identifier** và trả về biểu diễn text có thể sử dụng an toàn ở vị trí định danh trong SQL text.

```sql
SELECT
    quote_ident('orders') AS regular_name,
    quote_ident('Order Details') AS spaced_name,
    quote_ident('select') AS keyword_name,
    quote_ident('CustomerCode') AS mixed_case;
```

Về ý nghĩa:

- `orders` có thể được trả nguyên nếu không cần double quotes.
- `Order Details` được đặt trong double quotes vì chứa khoảng trắng.
- `select` cần double quotes vì là từ khóa.
- `CustomerCode` cần double quotes để giữ chữ hoa, nếu muốn dùng đúng identifier đó.

### 5.1. `quote_ident` không nhất thiết luôn thêm dấu nháy

Đây là điểm quan trọng. `quote_ident('orders')` có thể trả `orders` thay vì `"orders"`.

Công dụng của nó là tạo **identifier hợp lệ về cú pháp**, không phải bảo đảm output luôn bắt đầu/kết thúc bằng ký tự double quote.

### 5.2. Identifier chứa double quote

```sql
SELECT quote_ident('has"quote') AS escaped_identifier;
```

Một double quote trong identifier phải được nhân đôi trong quoted identifier, để nó không kết thúc tên sớm.

### 5.3. Identifier có dấu chấm

```sql
SELECT quote_ident('quote_lab.orders');
```

Đây là **một** identifier chứa dấu chấm, không phải hai components schema + table. Kết quả sẽ tương ứng một quoted identifier như `"quote_lab.orders"`.

Nếu muốn fully qualified relation:

```sql
SELECT
    quote_ident('quote_lab') || '.' ||
    quote_ident('orders') AS qualified_name;
```

Kết quả tạo hai identifiers được nối bởi **dấu chấm cú pháp SQL**.

### 5.4. Identifier có phải đã được cho phép?

Không. `quote_ident('pg_authid')` chỉ quote một tên, không kiểm tra caller có được phép truy cập system catalog nhạy cảm hay không.

Nếu input tên bảng đến từ request, còn cần allowlist hoặc mapping từ lựa chọn nghiệp vụ sang object name đã cố định.

### 5.5. Nếu NULL?

`quote_ident(NULL::text)` không tạo một identifier sử dụng được. `format('%I', NULL)` còn có thể báo lỗi vì SQL không có “identifier NULL”.

Validation nên chặn NULL/rỗng **trước khi xây SQL**.

## 6. `quote_literal(anyelement)`: quote một giá trị thành SQL literal

`quote_literal` trả một chuỗi text biểu diễn literal SQL an toàn, ví dụ:

```sql
SELECT
    quote_literal('hello') AS simple_literal,
    quote_literal('O''Reilly') AS apostrophe_literal,
    quote_literal(42) AS numeric_literal,
    quote_literal(DATE '2026-01-01') AS date_literal;
```

Với `O'Reilly`, output biểu diễn một string literal có dấu nháy bên ngoài và dấu nháy bên trong được escape theo quy tắc PostgreSQL.

### 6.1. Chỉ dùng khi thật sự cần xây SQL text

Trong PL/pgSQL:

```sql
v_sql :=
    'SELECT count(*)
       FROM quote_lab.orders
      WHERE customer_code = ' ||
    quote_literal(p_customer_code);
```

về mặt quoting có thể xử lý dấu nháy trong `p_customer_code`, **nhưng đây chưa phải cách ưu tiên** nếu lệnh hỗ trợ bind values.

Cách nên dùng:

```sql
EXECUTE
    'SELECT count(*)
       FROM quote_lab.orders
      WHERE customer_code = $1'
INTO v_count
USING p_customer_code;
```

### 6.2. Giá trị và kiểu dữ liệu

`quote_literal` tạo biểu diễn **text** được nhúng lại vào SQL source, nên lần parse/ép kiểu tiếp theo có thể phụ thuộc vị trí literal, kiểu của cột, implicit casts và configuration.

`EXECUTE ... USING` truyền giá trị với kiểu dữ liệu gốc, thường đơn giản và an toàn hơn, đồng thời tránh parse/convert literal không cần thiết.

### 6.3. Không bao định danh bằng quote_literal

Sai về vị trí SQL:

```sql
SELECT quote_literal('orders');
```

đây là một SQL literal text, không phải identifier tên bảng.

Nếu tạo:

```sql
'SELECT * FROM ' || quote_literal('orders')
```

câu lệnh có thể thành `SELECT * FROM 'orders'`, vốn không hợp lệ để tham chiếu table bằng string literal.

**Tên bảng dùng `%I`/`quote_ident`; giá trị literal dùng `%L`/`quote_literal`.**

## 7. `quote_literal(NULL)`: bẫy nghiêm trọng khi nối chuỗi

`quote_literal` là hàm **STRICT**: nếu truyền SQL NULL, kết quả là **SQL NULL**.

```sql
SELECT
    quote_literal(NULL::text) IS NULL
        AS literal_returns_sql_null;
```

Kết quả là `true`.

### 7.1. Một phần NULL làm cả SQL text thành NULL

```sql
SELECT
    'SELECT * FROM quote_lab.orders WHERE note = ' ||
    quote_literal(NULL::text)
        AS generated_sql;
```

Do toán tử nối chuỗi `||` với NULL, kết quả `generated_sql` là SQL NULL.

Nếu truyền chuỗi này cho:

```sql
EXECUTE v_sql;
```

PostgreSQL có thể báo lỗi dạng **query string argument of EXECUTE is null**.

### 7.2. Đừng nhầm SQL NULL với chuỗi “NULL”

- SQL NULL: không có giá trị.
- Text `'NULL'`: bốn chữ cái N-U-L-L.
- SQL token `NULL` trong câu dynamic SQL: literal null ở SQL được parse tiếp.

Chúng khác nhau ở kiểu và ngữ nghĩa.

### 7.3. Có phải quote_nullable giải quyết hết?

`quote_nullable` xử lý cách **biểu diễn NULL trong SQL text**, nhưng không sửa tự động semantics của `= NULL` trong WHERE.

Cần hiểu cả hai phần — xây chuỗi đúng **và** viết so sánh NULL đúng.

## 8. `quote_nullable(anyelement)`: không làm SQL text bị NULL khi đầu vào NULL

`quote_nullable` trả một chuỗi SQL literal cho giá trị không NULL, còn với đầu vào SQL NULL, trả **text chứa token `NULL`**.

```sql
SELECT
    quote_nullable(NULL::text) AS null_token_text,
    quote_nullable('O''Reilly') AS quoted_text,
    quote_nullable(42) AS quoted_number;
```

Có thể quan sát:

```sql
SELECT
    quote_nullable(NULL::text) IS NULL
        AS returns_sql_null,
    quote_nullable(NULL::text) = 'NULL'
        AS returns_text_token;
```

Kỳ vọng:

- `returns_sql_null = false`.
- `returns_text_token = true`.

### 8.1. Xây câu SQL không bị NULL do dữ liệu trống

```sql
SELECT
    'SELECT count(*) FROM quote_lab.orders ' ||
    'WHERE note IS NOT DISTINCT FROM ' ||
    quote_nullable(NULL::text) AS sql_text;
```

Phần cuối là SQL token `NULL`, nên chuỗi câu lệnh vẫn tồn tại.

### 8.2. Cạm bẫy `= NULL`

Không dùng:

```sql
WHERE note = NULL
```

để tìm rows có `note IS NULL`. Biểu thức `note = NULL` là UNKNOWN, không TRUE.

### 8.3. So sánh null-safe

```sql
WHERE note IS NOT DISTINCT FROM NULL
```

trả TRUE khi `note` cũng NULL và FALSE khi chỉ một phía NULL.

Với dữ liệu được bind:

```sql
EXECUTE
    'SELECT count(*)
       FROM quote_lab.orders
      WHERE note IS NOT DISTINCT FROM $1'
INTO v_count
USING p_note;
```

Đây là mẫu **nên ưu tiên** khi cần so sánh theo nghĩa “bằng kể cả NULL”.

### 8.4. `IS DISTINCT FROM` cho so sánh khác nhau

`IS DISTINCT FROM` xem NULL như một giá trị có thể so sánh để trả Boolean TRUE/FALSE thay vì UNKNOWN.

```sql
SELECT
    NULL::text IS NOT DISTINCT FROM NULL::text
        AS both_null_equal,
    'abc'::text IS DISTINCT FROM NULL::text
        AS text_differs_from_null;
```

## 9. Bảng so sánh ba hàm quoting

| Hàm | Đầu vào | Output để ghép vào SQL | SQL NULL input |
| --- | --- | --- | --- |
| `quote_ident(text)` | Một identifier | Identifier hợp lệ, có thể thêm `"..."` | Không có identifier NULL hữu ích |
| `quote_literal(value)` | Một data value | SQL literal text có nháy/escape phù hợp | Trả SQL NULL |
| `quote_nullable(value)` | Một data value hoặc NULL | SQL literal text hoặc token `NULL` | Trả text `NULL` |
| `format('%I', value)` | Identifier | Tương đương mục đích `quote_ident` | Báo lỗi với NULL identifier |
| `format('%L', value)` | Data value | Tương đương mục đích `quote_nullable` | Text `NULL` |
| `format('%s', value)` | Text substitution thông thường | Không quote/escape cho SQL | Thay bằng chuỗi rỗng |

**Không có hàm nào trong bảng tự kiểm tra authorization.**

### 9.1. Một ví dụ đối chiếu

```sql
SELECT
    quote_ident('Order Details') AS identifier_sql,
    quote_literal('Order Details') AS literal_sql,
    quote_nullable('Order Details') AS nullable_sql,
    format('%I', 'Order Details') AS format_identifier,
    format('%L', 'Order Details') AS format_literal;
```

### 9.2. Đừng so sánh bằng mắt một cách tùy tiện

Khi console hiển thị chuỗi `'abc'` hoặc `"abc"`, các dấu nháy **nằm trong giá trị text được tạo**, không phải kiểu dữ liệu mới.

Kiểm tra giá trị output bằng `SELECT quote_* (...)` chỉ giúp hiểu cách xây source code SQL; không có nghĩa các hàm đó đã chạy câu SQL được tạo.

## 10. `format`: cách xây câu SQL dễ đọc hơn nối `||`

PostgreSQL hỗ trợ:

```sql
format(format_string, arguments...)
```

Những format specifiers đặc biệt quan trọng trong dynamic SQL:

- `%I`: chèn **identifier** được quote theo quy tắc PostgreSQL.
- `%L`: chèn **literal** SQL, có xử lý NULL.
- `%s`: chèn **text** trực tiếp, **không đảm bảo SQL quoting**.
- `%%`: ký tự percent literal trong format string.

### 10.1. Ví dụ identifier

```sql
SELECT format(
    'SELECT %I FROM %I.%I',
    'Customer Code',
    'quote_lab',
    'orders'
);
```

Kết quả là SQL text với một cột tên `"Customer Code"`, schema `quote_lab` và table `orders`. Cột demo không tồn tại trong bảng lab; câu này **chỉ sinh chuỗi**, không thực thi.

### 10.2. Ví dụ literal

```sql
SELECT format(
    'SELECT * FROM quote_lab.orders WHERE customer_code = %L',
    'O''Reilly'
);
```

`%L` tạo biểu diễn literal chứa dấu nháy đơn đúng quy tắc.

### 10.3. %I và %L khác nhau như thế nào?

```sql
SELECT
    format('%I', 'select') AS identifier_form,
    format('%L', 'select') AS literal_form;
```

Một bên biểu diễn identifier `"select"`, bên kia biểu diễn literal `'select'`.

### 10.4. %s không dành cho input SQL không tin cậy

```sql
SELECT format(
    'SELECT * FROM quote_lab.orders ORDER BY %s',
    'order_id DESC'
);
```

Kết quả là SQL hợp lệ, nhưng nếu giá trị thứ hai đến trực tiếp từ người dùng, họ có thể đưa vào **bất kỳ SQL syntax** nào.

`%s` chỉ phù hợp nếu text substitution là fragment **được chương trình tạo từ allowlist cố định**, không nhận raw user input.

### 10.5. Positional specifiers

```sql
SELECT format(
    'SELECT %1$I FROM %2$I.%3$I ORDER BY %1$I',
    'order_id',
    'quote_lab',
    'orders'
);
```

`%1$I` tái sử dụng tham số thứ nhất ở nhiều vị trí, giúp tránh lặp phần code quote.

### 10.6. Ký tự percent của format string

```sql
SELECT format('Progress: 50%% complete');
```

Kết quả chứa một dấu `%`. Không nhầm đây với wildcard của `LIKE`; `format` và `LIKE` là hai lớp ngôn ngữ khác nhau.

## 11. Schema và table name phải được quote riêng

Sai:

```sql
format('SELECT * FROM %I', 'quote_lab.orders')
```

Cách này biểu diễn một identifier tên `quote_lab.orders`; nó **không** có nghĩa schema `quote_lab`, table `orders`.

Đúng:

```sql
format(
    'SELECT * FROM %I.%I',
    'quote_lab',
    'orders'
)
```

### 11.1. Trong PL/pgSQL

```sql
EXECUTE format(
    'SELECT count(*) FROM %I.%I',
    'quote_lab',
    'orders'
)
INTO v_count;
```

Nếu tên bảng do hệ thống chọn từ danh sách đã được kiểm tra, cách này tạo identifier path đúng.

### 11.2. Không cần dynamic SQL khi object cố định

Nếu luôn đọc `quote_lab.orders`, viết SQL tĩnh:

```sql
SELECT count(*)
INTO v_count
FROM quote_lab.orders;
```

Thường đơn giản, dễ kiểm tra permission và dễ tối ưu hơn dynamic SQL.

### 11.3. Schema qualification còn liên quan bảo mật

Một identifier đã được quote chính xác nhưng **không định danh schema** vẫn phụ thuộc `search_path`. Với routine có quyền cao, điều này có thể tạo rủi ro shadowing.

Ưu tiên `schema.table` rõ ràng cho objects nhạy cảm.

## 12. `EXECUTE ... USING`: lựa chọn ưu tiên cho data values

Cú pháp PL/pgSQL:

```sql
EXECUTE command_string
    [INTO [STRICT] target]
    [USING expression [, ...]];
```

Ví dụ:

```sql
EXECUTE
    'SELECT count(*)
       FROM quote_lab.orders
      WHERE tenant_id = $1
        AND customer_code = $2'
INTO v_count
USING p_tenant_id, p_customer_code;
```

### 12.1. `$1` / `$2` là gì?

Trong **command string của PL/pgSQL EXECUTE**, `$1` nhận giá trị đầu tiên trong `USING`, `$2` nhận giá trị thứ hai.

Chúng không phải cách nối text tên parameter và không phải tên cột.

### 12.2. Không có lớp SQL string literal thủ công

Giá trị `O'Reilly` có thể được bind nguyên vẹn. Không cần gọi `quote_literal` hoặc tự nhân đôi dấu nháy.

### 12.3. Giữ type gốc

`USING` giữ dữ liệu ở dạng parameter có type, hỗ trợ lập kế hoạch/casts đúng hơn việc ép mọi giá trị thành một SQL literal text.

### 12.4. NULL là một parameter hợp lệ

```sql
EXECUTE
    'SELECT count(*)
       FROM quote_lab.orders
      WHERE note IS NOT DISTINCT FROM $1'
INTO v_count
USING NULL::text;
```

Khác với nối `quote_literal(NULL)` làm mất cả command string.

### 12.5. Có thể kết hợp identifier và parameters

```sql
EXECUTE format(
    'SELECT count(*)
       FROM %I.%I
      WHERE tenant_id = $1 AND status = $2',
    'quote_lab',
    'orders'
)
INTO v_count
USING 10, 'PAID';
```

Đây là mô hình tiêu biểu:

- `%I.%I` cho identifiers.
- `$1`/`$2` cho values.
- Allowlist/authorization riêng cho object selection.

## 13. Phân biệt SQL `EXECUTE` và PL/pgSQL `EXECUTE`

PostgreSQL có hai tình huống mang từ khóa `EXECUTE`.

### 13.1. SQL prepared statements

```sql
PREPARE find_order(integer) AS
SELECT order_id, status
FROM quote_lab.orders
WHERE tenant_id = $1;

EXECUTE find_order(10);

DEALLOCATE find_order;
```

Ở đây `EXECUTE find_order(10)` là một **SQL command chạy prepared statement theo tên**.

### 13.2. Dynamic command trong PL/pgSQL

```sql
EXECUTE
    'SELECT count(*) FROM quote_lab.orders WHERE tenant_id = $1'
INTO v_count
USING p_tenant_id;
```

Đây là **PL/pgSQL statement** chạy một text command và có cú pháp `INTO ... USING` của PL/pgSQL.

### 13.3. Vì sao cần phân biệt?

Bạn không thể tùy ý copy cú pháp `INTO variable USING ...` từ PL/pgSQL vào một SQL statement ngoài function và kỳ vọng hoạt động giống nhau.

### 13.4. EXECUTE động lập kế hoạch lại

Với `EXECUTE command_string` trong PL/pgSQL, PostgreSQL thường parse/plan lại dynamic command cho từng lần thực thi, trái với những SQL statements tĩnh trong PL/pgSQL có thể được cache plans theo cơ chế riêng.

Điều này có thể hữu ích khi tham số có selectivity khác biệt, nhưng làm tăng planning overhead nếu gọi liên tục trong vòng lặp lớn.

**Dynamic SQL không phải cách tăng tốc mặc định.** Dùng khi cấu trúc cần linh hoạt hoặc có lý do plan-sensitive được đo.

## 14. Identifier không thể bind bằng `USING`

Ví dụ không hợp lệ về ý định:

```sql
-- Không thể dùng $1 làm tên table:
EXECUTE 'SELECT count(*) FROM $1'
INTO v_count
USING p_table_name;
```

`$1` đại diện **giá trị biểu thức**, không phải vị trí tên bảng trong grammar của câu SQL.

### 14.1. Tên cột cũng vậy

```sql
-- Không thay tên cột bằng data parameter:
EXECUTE 'SELECT $1 FROM quote_lab.orders'
USING 'status';
```

Ở đây `$1` có nghĩa một giá trị text không đổi `status` cho mỗi row (nếu câu lệnh được dùng ở ngữ cảnh cho phép), **không đọc cột status**.

### 14.2. Cách đúng khi phải chọn cột

```sql
EXECUTE format(
    'SELECT %I FROM quote_lab.orders WHERE tenant_id = $1',
    v_column_name
)
USING p_tenant_id;
```

Nhưng chỉ nên cho phép `v_column_name` sau khi kiểm tra against allowlist.

### 14.3. SQL keyword không bind bằng parameter

```sql
ORDER BY created_at $1
```

không cho truyền `$1 = 'DESC'` như một keyword định hướng sắp xếp.

Cần chọn một fragment cố định `ASC` hoặc `DESC` từ logic ứng dụng rồi ghép trong câu SQL có kiểm soát.

## 15. Quoting không thay thế allowlist

Giả sử người dùng chọn một trong hai bảng:

- `quote_lab.orders`.
- `quote_lab.orders_archive`.

Nếu họ truyền `pg_catalog.pg_user` thì `format('%I.%I', ...)` vẫn tạo một reference cú pháp hợp lệ tới object đó, chứ không tự hỏi “user có được phép chọn bảng này không?”.

### 15.1. Allowlist từ lựa chọn nghiệp vụ

```sql
IF p_source IS NULL
   OR p_source NOT IN ('current', 'archive')
THEN
    RAISE EXCEPTION 'Unsupported source'
        USING ERRCODE = '22023';
END IF;

v_table_name :=
    CASE p_source
        WHEN 'current' THEN 'orders'
        WHEN 'archive' THEN 'orders_archive'
    END;
```

Mapping này ngăn user chọn table name tùy ý.

### 15.2. Quote tên sau khi chọn object

```sql
EXECUTE format(
    'SELECT count(*)
       FROM %I.%I
      WHERE tenant_id = $1',
    'quote_lab',
    v_table_name
)
INTO v_count
USING p_tenant_id;
```

### 15.3. Cấp tenant_id tùy ý không phải authorization

Một routine `SECURITY DEFINER` nhận `p_tenant_id integer` và cho caller gọi với tenant bất kỳ có thể làm lộ số liệu mọi tenant, **dù toàn bộ SQL quoting đúng**.

Đối với API multi-tenant, tenant scope phải đến từ **identity/authorization context đáng tin cậy** hoặc mapping được xác minh, không chỉ từ parameter do caller tự khai báo.

### 15.4. Identifier limit và tên giả mạo

PostgreSQL giới hạn độ dài identifier theo cấu hình compile-time (mặc định thường 63 bytes). Một tên quá dài có thể bị cắt theo quy tắc parser/object creation.

Nếu nghiệp vụ tự tạo nhiều objects từ input, cần validation tên, collisions và quyền ownership; `quote_ident` không tự xử lý quản trị namespace.

## 16. Hàm hoàn chỉnh: lựa chọn bảng trong allowlist và bind tenant

Hàm dưới đây chỉ dùng SQL động vì tên bảng phải đổi giữa hai nguồn được định nghĩa sẵn.

```sql
CREATE OR REPLACE FUNCTION quote_lab.count_orders(
    p_source text,
    p_tenant_id integer
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, quote_lab, pg_temp
AS $fn$
DECLARE
    v_table_name text;
    v_count bigint;
BEGIN
    IF p_source IS NULL
       OR p_source NOT IN ('current', 'archive')
    THEN
        RAISE EXCEPTION 'Unsupported source: %', p_source
            USING ERRCODE = '22023';
    END IF;

    IF p_tenant_id IS NULL OR p_tenant_id <= 0 THEN
        RAISE EXCEPTION 'Invalid tenant id'
            USING ERRCODE = '22023';
    END IF;

    v_table_name :=
        CASE p_source
            WHEN 'current' THEN 'orders'
            WHEN 'archive' THEN 'orders_archive'
        END;

    EXECUTE format(
        'SELECT count(*) FROM %I.%I
         WHERE tenant_id = $1',
        'quote_lab',
        v_table_name
    )
    INTO v_count
    USING p_tenant_id;

    RETURN v_count;
END;
$fn$;
```

Kiểm tra:

```sql
SELECT quote_lab.count_orders('current', 10)
    AS current_tenant_10;

SELECT quote_lab.count_orders('archive', 10)
    AS archived_tenant_10;

SELECT quote_lab.count_orders('current', 20)
    AS current_tenant_20;
```

Kỳ vọng với dữ liệu lab:

| Lời gọi | Kết quả |
| --- | ---: |
| `count_orders('current', 10)` | 4 |
| `count_orders('archive', 10)` | 1 |
| `count_orders('current', 20)` | 2 |

### 16.1. Vì sao INVOKER?

Hàm này không cần nâng quyền. Caller được phép gọi và đọc những bảng tương ứng theo các quyền trực tiếp/RLS trong lab.

Nếu muốn giấu bảng và chỉ cấp kết quả aggregate qua definer API, phải bổ sung authorization và owner role phù hợp. Không đổi `SECURITY INVOKER` sang `DEFINER` một cách máy móc.

### 16.2. Vì sao có `SET search_path`?

Thể hiện ý định chỉ dùng built-ins và schema đáng tin cậy. Lệnh dynamic cũng định danh `quote_lab` cụ thể, giảm rủi ro lookup nhầm table.

### 16.3. Nếu caller không có SELECT?

`SECURITY INVOKER` sử dụng quyền caller; việc có EXECUTE trên hàm không tự cấp quyền SELECT hai bảng.

Đây là lỗi quyền bình thường cần tách khỏi lỗi quoting.

## 17. Hàm hoàn chỉnh: chọn một cột cho phép rồi bind giá trị

Một endpoint muốn đếm sản phẩm theo `status` hoặc `customer_code`, nhưng không cho phép truy vấn cột `note` hay `amount` tùy ý.

```sql
CREATE OR REPLACE FUNCTION quote_lab.count_by_field(
    p_tenant_id integer,
    p_field text,
    p_value text
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, quote_lab, pg_temp
AS $fn$
DECLARE
    v_count bigint;
BEGIN
    IF p_tenant_id IS NULL OR p_tenant_id <= 0 THEN
        RAISE EXCEPTION 'Invalid tenant id'
            USING ERRCODE = '22023';
    END IF;

    IF p_field IS NULL
       OR p_field NOT IN ('status', 'customer_code')
    THEN
        RAISE EXCEPTION 'Unsupported field'
            USING ERRCODE = '22023';
    END IF;

    EXECUTE format(
        'SELECT count(*)
         FROM quote_lab.orders
         WHERE tenant_id = $1
           AND %I = $2',
        p_field
    )
    INTO v_count
    USING p_tenant_id, p_value;

    RETURN v_count;
END;
$fn$;
```

Kiểm thử:

```sql
SELECT quote_lab.count_by_field(
    10, 'status', 'PAID'
);

SELECT quote_lab.count_by_field(
    10, 'customer_code', 'O''Reilly'
);
```

Cả hai đầu vào đều được bind như giá trị dữ liệu, còn tên cột được chọn từ hai lựa chọn có sẵn và đi qua `%I`.

### 17.1. Vì sao field dùng `%I`?

`status` và `customer_code` là **tên cột**, nên không thể thay bằng `USING p_field`.

### 17.2. Vì sao value dùng `$2`?

`p_value` là **dữ liệu**, không phải source SQL.

### 17.3. Khi p_value NULL?

Điều kiện `field = $2` không match khi `$2` là SQL NULL. Nếu API muốn “field là NULL”, cần định nghĩa một thao tác riêng hoặc dùng `IS NOT DISTINCT FROM` cho trường hợp cần semantics null-safe.

### 17.4. Vì sao không cho mọi cột?

Nếu cho p_field='amount' nhưng p_value kiểu text, implicit casts/operator choices có thể gây lỗi hoặc semantic bugs. Quan trọng hơn, tùy ứng dụng người dùng có thể **không được phép truy vấn dựa trên một số trường nhạy cảm**.

### 17.5. Query này còn thiếu authorization cho API công khai

Hàm invoker kỳ vọng database role/RLS có quyền phù hợp. Nếu đưa vào definer API, tenant ID phải được xác minh từ nguồn tin cậy.

## 18. Hàm trả nhiều hàng với RETURN QUERY EXECUTE

`RETURN QUERY EXECUTE` dùng được trong hàm PL/pgSQL trả một tập kết quả.

```sql
CREATE OR REPLACE FUNCTION quote_lab.find_orders(
    p_tenant_id integer,
    p_field text,
    p_value text
)
RETURNS TABLE (
    order_id bigint,
    customer_code text,
    status text
)
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, quote_lab, pg_temp
AS $fn$
BEGIN
    IF p_tenant_id IS NULL OR p_tenant_id <= 0 THEN
        RAISE EXCEPTION 'Invalid tenant'
            USING ERRCODE = '22023';
    END IF;

    IF p_field IS NULL
       OR p_field NOT IN ('status', 'customer_code')
    THEN
        RAISE EXCEPTION 'Unsupported search column'
            USING ERRCODE = '22023';
    END IF;

    RETURN QUERY EXECUTE format(
        'SELECT o.order_id, o.customer_code, o.status
         FROM quote_lab.orders AS o
         WHERE o.tenant_id = $1
           AND o.%I = $2
         ORDER BY o.order_id',
        p_field
    )
    USING p_tenant_id, p_value;
END;
$fn$;
```

Thử:

```sql
SELECT *
FROM quote_lab.find_orders(
    10, 'customer_code', 'O''Reilly'
);

SELECT *
FROM quote_lab.find_orders(
    10, 'status', 'NEW'
);
```

### 18.1. Rủi ro nếu bỏ allowlist

Nếu hàm cho phép bất kỳ tên cột nào, caller có thể thử các columns khác, suy luận sự tồn tại của dữ liệu hoặc gây lỗi type. `%I` chỉ tránh phá vỡ syntax SQL, không bảo đảm API contract.

### 18.2. Rủi ro nếu bỏ tenant filter

Một tham số text chứa `' OR true --` không vượt được parameter binding, nhưng nếu code quên tenant predicate, kết quả vẫn có thể lộ dữ liệu tenant khác. Đây là **lỗi authorization**, không phải injection.

### 18.3. Khai báo RETURNS TABLE phải khớp output

Với `RETURN QUERY EXECUTE`, số cột và kiểu trả về phải khớp định nghĩa `RETURNS TABLE`. Quote đúng không giúp sửa lỗi mismatch kiểu dữ liệu.

## 19. Dynamic ORDER BY an toàn

Một API có thể cho sort theo:

- `created_at`.
- `amount`.
- `order_id`.

Và chiều `ASC` hoặc `DESC`.

### 19.1. Không đưa nguyên `p_sort` vào %s

Sai:

```sql
EXECUTE format(
    'SELECT * FROM quote_lab.orders ORDER BY %s',
    p_sort_from_user
);
```

Vì `%s` không quote SQL syntax, input có thể chèn biểu thức/phần SQL không được phép.

### 19.2. Chọn column từ allowlist

```sql
IF p_sort_column IS NULL
   OR p_sort_column NOT IN (
       'created_at', 'amount', 'order_id'
   )
THEN
    RAISE EXCEPTION 'Unsupported sort column'
        USING ERRCODE = '22023';
END IF;
```

### 19.3. Chọn direction từ một Boolean

```sql
v_direction :=
    CASE WHEN p_descending
        THEN 'DESC'
        ELSE 'ASC'
    END;
```

Khi p_descending NULL, CASE ELSE chọn ASC theo ví dụ. Production có thể chọn từ chối NULL nếu muốn.

### 19.4. Ghép SQL

```sql
EXECUTE format(
    'SELECT order_id, amount, created_at
     FROM quote_lab.orders
     WHERE tenant_id = $1
     ORDER BY %I %s, order_id DESC
     LIMIT $2',
    p_sort_column,
    v_direction
)
USING p_tenant_id, p_page_size;
```

Đoạn minh họa này phải nằm trong ngữ cảnh PL/pgSQL thích hợp; nếu cần trả result set thì dùng `RETURN QUERY EXECUTE`.

- `%I` quote tên cột đã allowlist.
- `%s` chỉ chèn **chuỗi ASC/DESC do code tạo ra**.
- `$1` là tenant value.
- `$2` là page-size value.

### 19.5. Giới hạn page size

`LIMIT $2` bind giá trị nhưng không tự giới hạn tài nguyên. Phải validate:

```sql
IF p_page_size IS NULL
   OR p_page_size < 1
   OR p_page_size > 100
THEN
    RAISE EXCEPTION 'Invalid page size'
        USING ERRCODE = '22023';
END IF;
```

### 19.6. Tie-breaker và thứ tự NULL

Với sort column là `order_id`, thêm tie-breaker cùng `order_id` có thể dư thừa nhưng không sai. Với columns khác, một unique key cuối giúp phân trang ổn định. Nếu sort column nullable, quyết định `NULLS FIRST`/`LAST` rõ ràng; không cho raw input quyết định SQL clause này.

## 20. LIKE/ILIKE: parameter binding không escape wildcard

Một vấn đề khác với SQL injection là **pattern injection**.

Giả sử người dùng nhập:

```text
A%_B
```

Nếu dùng:

```sql
EXECUTE
    'SELECT count(*)
     FROM quote_lab.orders
     WHERE customer_code LIKE $1'
INTO v_count
USING '%' || p_search || '%';
```

thì `%` và `_` bên trong p_search **vẫn là LIKE wildcards**.

Bind parameter chống SQL syntax injection, nhưng không tự biến input thành chuỗi literal cần tìm.

### 20.1. Dùng escape character tường minh

Chọn `!`:

- `!` -> `!!`.
- `%` -> `!%`.
- `_` -> `!_`.

Trong PL/pgSQL:

```sql
v_literal_search := replace(
    replace(
        replace(p_search, '!', '!!'),
        '%', '!%'
    ),
    '_', '!_'
);

v_pattern := '%' || v_literal_search || '%';

EXECUTE
    'SELECT count(*)
     FROM quote_lab.orders
     WHERE customer_code LIKE $1 ESCAPE ''!'''
INTO v_count
USING v_pattern;
```

Trong string literal PL/pgSQL, `''!''` giúp tạo SQL clause `ESCAPE '!'`. Với source code cố định, có thể dùng dollar-quoted command text thay vì nhiều lớp nháy:

```sql
EXECUTE $sql$
    SELECT count(*)
    FROM quote_lab.orders
    WHERE customer_code LIKE $1 ESCAPE '!'
$sql$
INTO v_count
USING v_pattern;
```

### 20.2. Test ký tự literal

Khi p_search = `A%_B`, code escape đúng sẽ tìm văn bản chứa **literal** `A%_B`, thay vì match nhiều dạng chuỗi khác.

### 20.3. Nếu người dùng được phép nhập wildcard?

Đó là một search feature khác. Cần định nghĩa rõ UX và bảo vệ chi phí truy vấn bằng length/rate/timeout/index, không ngầm coi nó là plain-text search.

### 20.4. Regex cũng là một ngôn ngữ pattern riêng

Bind:

```sql
WHERE note ~ $1
```

ngăn SQL injection qua regex parameter, nhưng vẫn cho regex engine diễn giải metacharacters. Nếu muốn tìm literal substring, đừng tự dùng regex do người dùng cung cấp mà không có policy.

## 21. `quote_literal` và `standard_conforming_strings`

Trong PostgreSQL, SQL string escaping có chi tiết về backslash. Setting:

```sql
SHOW standard_conforming_strings;
```

thường được bật ở các PostgreSQL hiện đại, nên backslash trong string literal thông thường không cần xử lý như escape của SQL parser theo cách `E'...'`.

### 21.1. Tự thêm dấu backslash dễ lỗi

Không nên dùng các thay thế kiểu:

```text
replace(input, "'", "\'")
```

và tin rằng đã an toàn cho mọi SQL literal. Quy tắc backslash/quote còn phụ thuộc cách literal được parser hiểu.

### 21.2. Dùng PostgreSQL quoting primitives

`quote_literal` / `format('%L')` tạo biểu diễn SQL literal theo cơ chế PostgreSQL. Với values trong dynamic query vẫn ưu tiên `EXECUTE ... USING` để khỏi phải xây literal từ đầu.

### 21.3. Dollar quoting không dành cho input runtime không tin cậy

Dollar-quoted strings như:

```sql
DO $body$
BEGIN
    RAISE NOTICE 'Hello';
END
$body$;
```

rất hữu ích để viết **source code cố định** chứa dấu nháy. Nhưng đừng lấy input tùy ý rồi ghép vào giữa delimiter `$tag$ ... $tag$` như một cách escape runtime. Input có thể chứa delimiter mà bạn chọn, làm thay đổi nơi chuỗi kết thúc.

### 21.4. Ba lớp escape dễ nhầm

Trong Java gọi PostgreSQL PL/pgSQL, có thể có:

1. Java source string escaping.
2. SQL command text escaping.
3. Regex/LIKE pattern escaping.

Bind parameters giúp loại bỏ một lớp tự chế nguy hiểm, nhưng pattern semantics vẫn phải được xác định riêng.

## 22. `format('%L')` khi buộc phải chèn literal vào utility statements

`EXECUTE ... USING` dùng parameter placeholders cho **optimizable SQL commands** trong những trường hợp PostgreSQL hỗ trợ, chẳng hạn `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `MERGE` tùy phiên bản.

Nhiều **utility statements** như một số `CREATE`/`ALTER`/`COMMENT` không chấp nhận data parameters ở vị trí muốn tạo DDL text.

### 22.1. Ví dụ DDL comment

Nếu hệ thống quản trị có quyền gán comment cho bảng được allowlist:

```sql
EXECUTE format(
    'COMMENT ON TABLE %I.%I IS %L',
    'quote_lab',
    'orders',
    p_comment
);
```

- `%I.%I` cho schema + table.
- `%L` cho SQL literal comment, kể cả dấu nháy.
- `p_comment` có thể NULL; `%L` tạo token `NULL` để xóa comment theo semantics `COMMENT`.

### 22.2. Đây là ví dụ dành cho admin, không phải public API

`COMMENT ON TABLE` là DDL cần quyền phù hợp. Không cho người dùng không tin cậy tùy chọn arbitrary table comments chỉ vì `format` đã quote chuỗi.

### 22.3. Quote đúng object path

Sai:

```sql
format('COMMENT ON TABLE %I IS %L',
       'quote_lab.orders',
       'Example');
```

Đúng:

```sql
format('COMMENT ON TABLE %I.%I IS %L',
       'quote_lab', 'orders', 'Example');
```

### 22.4. Không mở rộng DDL “tùy ý” quá mức

Dù có %I/%L, một hàm definer cho phép user tạo/xóa/đổi tên object trong bất kỳ schema nào vẫn nguy hiểm về authorization và vận hành.

Chỉ expose các operations được xác định rõ cùng privilege model.

## 23. Quoting identifiers có trường hợp đặc biệt nào?

### 23.1. Chữ hoa và case folding

```sql
SELECT
    quote_ident('CustomerCode'),
    quote_ident('customercode');
```

Trong PostgreSQL:

- Unquoted identifiers được gấp về chữ thường.
- Quoted identifiers giữ đúng spelling/case.

Do đó `"CustomerCode"` khác `customercode` nếu hai names tồn tại.

### 23.2. Khoảng trắng và từ khóa

```sql
SELECT
    quote_ident('Order Details'),
    quote_ident('user'),
    quote_ident('select');
```

`quote_ident` quyết định khi nào double quote cần thiết cho cú pháp SQL.

### 23.3. Dấu chấm trong tên

Tên đơn `"a.b"` khác fully qualified `a.b`.

### 23.4. Schema name từ caller

`quote_ident` giúp biểu diễn schema name chính xác, **không xác minh schema đó thuộc tenant của caller**. Nếu app multi-schema theo tenant, cần ánh xạ tenant đã xác thực sang schema được phép ở phía server.

### 23.5. Tên object rỗng và NULL

SQL identifier rỗng thường không hợp lệ để tham chiếu object. Validate trước `format('%I')`, không để lỗi parser trở thành validation chính.

### 23.6. Reserved words

`quote_ident('select')` có thể tạo identifier `"select"` hợp lệ, nhưng tên cột/bảng trùng SQL keywords vẫn có thể gây khó đọc, khó vận hành. Khi thiết kế schema mới, ưu tiên tên đơn giản, ổn định.

## 24. Dùng `regclass` để phân giải tên bảng: lợi ích và giới hạn

PostgreSQL có type `regclass` biểu diễn relation OID và cho phép parser phân giải tên relation.

```sql
SELECT
    'quote_lab.orders'::regclass AS orders_relation,
    'quote_lab.orders_archive'::regclass
        AS archive_relation;
```

### 24.1. Vì sao regclass hữu ích?

- Có thể xác nhận một relation tồn tại.
- Dễ làm việc với catalog/OIDs.
- Trong một số APIs quản trị, giảm nhầm lẫn giữa chuỗi tên và relation object.

### 24.2. Nhưng regclass không tự kiểm tra authorization

Một caller có thể cố phân giải tên một relation mà họ không được phép thao tác. Nếu một definer routine nhận `regclass` rồi thực thi quyền của owner trên object đó, cần **allowlist/ownership checks** y như khi nhận tên text.

### 24.3. Không tự tin vào search_path khi parse tên regclass

Một chuỗi regclass không fully qualified có thể chịu object name resolution theo path. Với privileged code, ưu tiên tên schema-qualified, OID/catalog checks phù hợp.

### 24.4. Nếu object bị thay đổi đồng thời

Giữa bước lookup và DDL tiếp theo, object có thể được drop/rename/replace bởi giao dịch khác theo lock/DDL semantics. Với APIs quản trị có quyền cao, cần thiết kế locking và error handling, không coi regclass là khóa authorization bất biến.

## 25. `SECURITY DEFINER` làm tăng rủi ro từ dynamic SQL

Một hàm được khai báo:

```sql
SECURITY DEFINER
```

thực thi với quyền owner trong phạm vi routine.

Nếu caller có thể chọn tên bảng từ parameter, quoting chỉ giúp tên bảng **không chứa phần SQL injection về cú pháp**, nhưng owner vẫn có thể truy cập một relation caller không được phép.

### 25.1. Ví dụ nguy hiểm dù quote đúng

```sql
EXECUTE format(
    'SELECT count(*) FROM %I.%I',
    p_schema,
    p_table
)
INTO v_count;
```

Nếu owner có SELECT trên nhiều bảng, caller có thể chọn một bảng nhạy cảm hợp lệ và lấy count.

### 25.2. Giải pháp

- Không cho caller điều khiển arbitrary schema/table.
- Mapping các lựa chọn nghiệp vụ sang object fixed names.
- Owner role chuyên biệt `NOLOGIN` và least privilege.
- Kiểm tra authorization đối với tenant/row/object.
- Không tin custom GUC hay parameter caller tự khai báo mà chưa xác minh.
- Định danh objects và khóa `search_path`.
- Thu hồi `EXECUTE` của routine khỏi `PUBLIC` nếu không muốn tất cả roles gọi.

### 25.3. Search path an toàn

Mẫu definer:

```sql
CREATE FUNCTION quote_lab.safe_admin_api(...)
RETURNS ...
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, quote_lab, pg_temp
AS $fn$
BEGIN
    -- Chỉ truy cập object đã allowlist/authorized.
END;
$fn$;
```

Đây là **khung minh họa**, không phải function executable đầy đủ vì dấu `...` đại diện phần chưa khai báo.

### 25.4. Vì sao `pg_temp` ở cuối?

Temporary schema có thể được tìm trước trusted schemas với **relation/type names** khi không được liệt kê rõ vị trí. Đặt `pg_temp` ở cuối path và schema-qualify bảng làm giảm rủi ro temporary-table shadowing trong SECURITY DEFINER.

### 25.5. Vì sao `pg_catalog` ở đầu?

Giữ built-in functions/operators/types được ưu tiên so với schemas có nguy cơ cho tạo objects không tin cậy.

### 25.6. Chỉ đặt search_path chưa đủ

Nếu code dùng `format('%I', p_table)` cho một tên bảng tùy ý, nó vẫn có thể tham chiếu object không được phép trong trusted schema. Search path bảo vệ **resolution**, còn allowlist bảo vệ **authorization**.

## 26. Không bao giờ để untrusted schema đứng trước trong definer search_path

Nếu caller có `CREATE` trong schema `public` hoặc schema chung khác, definer routine có unqualified table/function/operator names có thể bị ảnh hưởng bởi object shadowing.

Cấu hình nguy hiểm:

```sql
SET search_path = untrusted, pg_catalog, quote_lab;
```

Trong đó `untrusted` giả định là một schema attacker có thể CREATE.

Cấu hình an toàn hơn:

```sql
SET search_path = pg_catalog, quote_lab, pg_temp;
```

với điều kiện `quote_lab` thực sự là trusted schema không cho caller CREATE/ALTER objects nhạy cảm.

### 26.1. Không nên tin schema `public` từ mặc định lịch sử

Quyền `CREATE` trên public khác nhau theo phiên bản/database đã upgrade/grants. Kiểm tra quyền thực tế:

```sql
SELECT
    has_schema_privilege(
        'public',
        'CREATE'
    ) AS current_role_can_create;
```

Ở đây tham số 'public' đầu tiên trong `has_schema_privilege(name, privilege)` có thể được hiểu như schema name trong overload hai tham số; kết quả là quyền **role đang có hiệu lực** trên schema public, không phải quyền của pseudo-role PUBLIC. Muốn kiểm tra quyền của một role cụ thể, dùng overload ba tham số:

```sql
SELECT has_schema_privilege(
    'quote_lab_reader',
    'public',
    'CREATE'
);
```

Lệnh cuối chỉ thực thi nếu role `quote_lab_reader` tồn tại. Trong lab đơn giản có thể chưa tạo role đó.

### 26.2. RLS cũng cần kiểm tra

Definer owner có thể bypass RLS trong những điều kiện PostgreSQL áp dụng, đặc biệt khi owner là table owner, superuser hoặc role có `BYPASSRLS`. Quoting không khôi phục policies bị bypass.

### 26.3. Không thể lấy “user cuối” bằng CURRENT_USER trong definer

`CURRENT_USER` trong definer context thể hiện function owner theo semantics PostgreSQL. Với shared application login, `SESSION_USER` cũng không tự phân biệt các web users. Cần authorization context được bảo vệ.

## 27. `PUBLIC EXECUTE` và cấp quyền trên function có dynamic SQL

Một PostgreSQL function mới thường có EXECUTE cho `PUBLIC` theo default privileges nếu không thay đổi cấu hình.

Khi tạo definer function có dynamic SQL, cần tránh cửa sổ cấp quyền quá rộng:

```sql
BEGIN;

CREATE FUNCTION quote_lab.protected_api(
    p_customer_code text
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, quote_lab, pg_temp
AS $fn$
DECLARE
    v_count bigint;
BEGIN
    EXECUTE
        'SELECT count(*)
         FROM quote_lab.orders
         WHERE customer_code = $1'
    INTO v_count
    USING p_customer_code;

    RETURN v_count;
END;
$fn$;

REVOKE ALL ON FUNCTION
    quote_lab.protected_api(text)
FROM PUBLIC;

-- Chỉ GRANT role được xác minh và thực sự tồn tại:
-- GRANT EXECUTE ON FUNCTION quote_lab.protected_api(text)
-- TO trusted_api_role;

COMMIT;
```

**Ví dụ này chỉ bảo vệ SQL quoting**, chưa là API đa tenant an toàn: bất kỳ caller được GRANT mà không có row authorization có thể lấy count theo customer_code của mọi tenant.

### 27.1. Kết hợp CREATE/REVOKE/GRANT trong transaction

Giúp tránh một khoảng thời gian function đã tồn tại và được PUBLIC EXECUTE trước khi REVOKE diễn ra.

### 27.2. Vì sao function owner quan trọng?

Nếu `protected_api` được tạo bởi superuser/owner có nhiều quyền, lỗi authorization trong body có phạm vi tác động lớn. Hãy tạo bằng owner role ít quyền nhất theo nhiệm vụ.

### 27.3. Không cho caller tạo objects trong trusted schema

Quyền `USAGE` cho phép tra tên; `CREATE` cho phép tạo. Không cấp `CREATE` rộng vào schema mà definer đặt trong search_path.

## 28. Thực hành với một injection string an toàn để quan sát

Giả sử input text:

```text
O'Reilly
```

Nếu cố tạo literal bằng:

```sql
SELECT
    'SELECT * FROM quote_lab.orders
     WHERE customer_code = ''' ||
    'O''Reilly' ||
    '''' AS wrongly_concatenated;
```

Chuỗi SQL được tạo có thể có dấu nháy không được escape đúng ở lớp SQL mới.

### 28.1. Quoting literal

```sql
SELECT format(
    'SELECT * FROM quote_lab.orders
     WHERE customer_code = %L',
    'O''Reilly'
) AS correctly_quoted;
```

### 28.2. Quoting identifier

```sql
SELECT format(
    'SELECT %I FROM quote_lab.orders',
    'customer_code'
) AS column_sql;
```

### 28.3. Giá trị có ý định thay đổi điều kiện SQL

Giả sử input là:

```text
O'Reilly' OR TRUE --
```

Nếu dùng bind:

```sql
SELECT order_id, tenant_id
FROM quote_lab.orders
WHERE customer_code = 'O''Reilly'' OR TRUE --';
```

Trong câu SQL tĩnh trên, các dấu nháy được nhân đôi, nên toàn bộ chuỗi là **một literal data value**. Nó không chuyển thành `OR TRUE` như cấu trúc SQL.

Trong ứng dụng, thay vì viết literal bằng tay:

```sql
EXECUTE
    'SELECT count(*)
     FROM quote_lab.orders
     WHERE customer_code = $1'
INTO v_count
USING p_untrusted_text;
```

### 28.4. Tập trung vào phòng thủ, không cần chạy payload nguy hiểm

Không cần gửi các lệnh phá hủy dữ liệu hoặc thay đổi quyền để chứng minh nguy cơ. Đối chiếu **chuỗi query unsafe** với **query có bind** đủ cho bài học về lớp dữ liệu/cú pháp.

## 29. Dynamic UPDATE: bảo vệ data values và nghiệp vụ

Một PL/pgSQL routine có thể cần cập nhật trạng thái của một order.

### 29.1. Mẫu dùng USING

```sql
EXECUTE
    'UPDATE quote_lab.orders
     SET status = $1
     WHERE tenant_id = $2
       AND order_id = $3'
USING p_new_status, p_tenant_id, p_order_id;
```

Các values vẫn được bind, kể cả `p_new_status` có chứa dấu nháy hoặc ký tự lạ. Constraints trên `status` sẽ từ chối những giá trị không hợp lệ.

### 29.2. Kiểm tra quyền và phạm vi

Nếu đây là definer function, một client có thể truyền p_tenant_id bất kỳ nếu API không kiểm tra. Cần xác nhận p_tenant_id thuộc caller hoặc được server chỉ định đáng tin cậy.

### 29.3. Kiểm tra số row thay đổi

```sql
GET DIAGNOSTICS v_affected = ROW_COUNT;
```

Chạy ngay sau lệnh cần kiểm tra để lấy số rows bị ảnh hưởng. Nếu kỳ vọng đúng một order, xử lý riêng 0 và >1.

### 29.4. Tính nguyên tử

Bất biến như “đơn chỉ được chuyển NEW -> PAID” nên được đặt trong WHERE:

```sql
EXECUTE
    'UPDATE quote_lab.orders
     SET status = $1
     WHERE tenant_id = $2
       AND order_id = $3
       AND status = $4'
USING 'PAID', p_tenant_id, p_order_id, 'NEW';
```

Mẫu này giúp điều kiện cập nhật được đánh giá tại thời điểm thực thi UPDATE, thay vì kiểm tra riêng rồi UPDATE vô điều kiện.

## 30. `quote_nullable` không thay thế logic NULL trong DELETE/UPDATE

Giả sử muốn xóa/đếm các rows có `note` bằng một giá trị, kể cả NULL.

Sai về SQL semantics:

```sql
WHERE note = NULL
```

Đúng cho so sánh null-safe:

```sql
WHERE note IS NOT DISTINCT FROM $1
```

### 30.1. Trong câu SQL động

```sql
EXECUTE
    'SELECT count(*)
     FROM quote_lab.orders
     WHERE tenant_id = $1
       AND note IS NOT DISTINCT FROM $2'
INTO v_count
USING p_tenant_id, p_note;
```

### 30.2. Nếu buộc dùng literal text

```sql
v_sql := format(
    'SELECT count(*)
     FROM quote_lab.orders
     WHERE tenant_id = %L
       AND note IS NOT DISTINCT FROM %L',
    p_tenant_id,
    p_note
);
```

`%L` trả token `NULL` khi p_note NULL, nên câu SQL vẫn parse được.

### 30.3. Nhưng đừng chuyển thói quen sang nối literal

Nếu câu SQL hỗ trợ `USING`, hãy dùng nó. `format('%L')` là công cụ khi phải tạo text SQL, không phải lựa chọn tốt hơn mọi trường hợp.

## 31. DDL và object names: không có “bind tất cả”

Khi xây SQL DDL, có những phần phải đặt vào câu lệnh dưới dạng identifiers hoặc syntax:

```sql
CREATE TABLE some_schema.some_table (...);
```

Không thể dùng bind parameter cho `some_table` hoặc `CREATE TABLE` keyword.

### 31.1. Tên schema/table từ mapping tin cậy

```sql
EXECUTE format(
    'CREATE TABLE %I.%I (id bigint PRIMARY KEY)',
    v_admin_schema,
    v_new_table
);
```

Chỉ thực hiện khi:

- Người gọi đã được phép tạo bảng trong schema này.
- `v_admin_schema`/`v_new_table` lấy từ mapping hoặc validation chặt.
- Không tạo trùng hoặc vượt quota objects.
- DDL được triển khai trong phạm vi quyền/transaction phù hợp.

### 31.2. Không tự tạo schema mới theo mọi request

Một API cho khách hàng tạo tùy ý hàng nghìn tables sẽ gây catalog bloat, khó backup, locks và governance, dù identifiers đều quote đúng.

### 31.3. DDL utility cần quoting literal riêng

Với `COMMENT ON`, default expressions hoặc statements tương ứng, có thể cần `%L`. Không truyền dữ liệu qua `%s` raw khi đưa vào SQL text.

### 31.4. Schema-qualified names và quyền

Một tên `trusted_schema.some_table` quote đúng vẫn phải có quyền DDL/SELECT/UPDATE thích hợp. Quote không nâng cấp vai trò hay bảo đảm được thao tác.

## 32. `format` với identifiers có dấu chấm, ký tự Unicode

PostgreSQL cho phép quoted identifiers có chữ hoa, dấu cách và nhiều ký tự Unicode hợp lệ.

```sql
SELECT format(
    'SELECT %I FROM %I.%I',
    'Tên cột',
    'quote_lab',
    'Báo Cáo'
);
```

Lệnh chỉ tạo **SQL text**; bảng và cột demo chưa tồn tại.

### 32.1. Unicode identifier khác Unicode literal

- `%I` quote tên cột `Tên cột`.
- `%L` quote giá trị string `Tên cột`.

Người dùng nhìn thấy cùng văn bản nhưng SQL parser hiểu khác.

### 32.2. Không dùng dấu nháy đơn cho identifier Unicode

`'Tên cột'` là string literal chứ không là tên cột.

### 32.3. Kiểm tra tên tồn tại

`quote_ident`/`format('%I')` chỉ xử lý text; nó không tạo object. Nếu tên không tồn tại, dynamic statement sẽ lỗi `relation does not exist` hoặc `column does not exist` khi được chạy.

### 32.4. Schema qualification giảm nhầm lẫn

Nếu có nhiều schemas chứa table `orders`, dùng `%I.%I` với schema được xác minh thay vì phụ thuộc `search_path` của caller.

## 33. Trong Java/JDBC, PreparedStatement là đối tác của USING

Khi ứng dụng Java gọi database, thường nên dùng JDBC `PreparedStatement` cho data values:

```java
String sql = """
    SELECT order_id, customer_code, status
    FROM quote_lab.orders
    WHERE tenant_id = ?
      AND customer_code = ?
    ORDER BY order_id
    """;

try (var ps = conn.prepareStatement(sql)) {
    ps.setInt(1, authenticatedTenantId);
    ps.setString(2, userInput);

    try (var rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(
                rs.getLong("order_id")
            );
        }
    }
}
```

### 33.1. Parameterization ở hai tầng

- JDBC `?` giữ input là value đối với SQL statement do Java gửi.
- PL/pgSQL `EXECUTE ... USING` giữ input là value khi PL/pgSQL tạo dynamic command.

Nếu Java gọi một PL/pgSQL function, lớp bên trong function vẫn phải được viết an toàn; bind ở JDBC **không tự sửa dynamic SQL nối chuỗi trong function body**.

### 33.2. Không truyền raw SQL fragment qua function parameter

Mẫu nguy hiểm:

```java
ps.setString(1, "status = 'PAID' OR TRUE");
```

Nếu function được gọi sau đó nối parameter này vào `WHERE` dynamic SQL dưới dạng raw fragment, nó vẫn có lỗ hổng về thiết kế, dù JDBC call đã bind một value an toàn ở lớp ngoài.

### 33.3. Sort options phải allowlist

Trong Java:

```java
String sortColumn = switch (requestedSort) {
    case "newest" -> "created_at";
    case "amount" -> "amount";
    default -> "order_id";
};
```

`sortColumn` là fragment cố định từ code. Nếu phải gửi tên column vào PL/pgSQL function, function vẫn nên kiểm tra allowlist tại DB boundary.

### 33.4. Không nhúng user-controlled schema names tùy ý

Khi hệ thống multi-tenant sử dụng schema-per-tenant, app cần ánh xạ tenant đã xác thực sang schema name trong kho cấu hình đáng tin, không dùng trực tiếp request parameter.

## 34. Performance: SQL tĩnh thường là lựa chọn đầu tiên

Với schema/table/column cố định, không cần dynamic SQL:

```sql
SELECT count(*)
INTO v_count
FROM quote_lab.orders
WHERE tenant_id = p_tenant_id
  AND customer_code = p_customer_code;
```

### 34.1. Lợi ích của SQL tĩnh

- Đọc và review dễ hơn.
- Planner/PL/pgSQL có thể dùng cached plans theo cơ chế phù hợp.
- Ít chi phí tạo chuỗi.
- Dễ xác định dependencies và privileges.
- Giảm bề mặt injection.

### 34.2. Khi nào dynamic thực sự cần?

- Object identifiers thay đổi có kiểm soát.
- DDL administration tooling.
- Query shape cần điều khiển linh hoạt.
- Cần custom plan theo parameters trong trường hợp đo được.
- Metadata-driven tasks có allowlist rõ.

### 34.3. Dynamic SQL không mặc định nhanh hơn

Mỗi `EXECUTE command_string` có thể cần lập plan lại. Nếu chạy trong vòng lặp 100.000 iterations, planning overhead có thể lớn.

### 34.4. Không chạy một câu SQL động cho từng hàng nếu có set-based solution

Thay vì loop qua rows và `EXECUTE SELECT count(*)` cho từng row, cân nhắc một JOIN/aggregate duy nhất.

### 34.5. EXPLAIN khi có function

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT quote_lab.count_orders('current', 10);
```

Đầu ra EXPLAIN của câu gọi function **không nhất thiết hiển thị chi tiết SQL bên trong function**. Có thể cần instrumentation khác nếu đánh giá nested dynamic statements.

## 35. Debug dynamic SQL mà không log secrets

Khi phát triển, bạn có thể muốn xem chuỗi SQL được tạo.

### 35.1. Lệnh minh họa log

```sql
RAISE NOTICE 'Generated command: %', v_sql;
```

Nhưng nếu v_sql chứa data literals/identifiers nhạy cảm, log có thể vô tình lộ:

- Mã khách hàng.
- Token hoặc thông tin cá nhân.
- Tên bảng/schema nội bộ.
- Dynamic DDL.
- Những giá trị mà caller không được xem.

### 35.2. Logging an toàn hơn

- Log loại operation/template identifier thay vì full command text.
- Log số lượng/loại parameters, không nhất thiết log giá trị.
- Dùng correlation ID cho request.
- Redact/hash khi thật sự cần và có chính sách bảo mật phù hợp.
- Dùng quyền truy cập/retention cho logs.

### 35.3. Exception handling

Bắt lỗi ở mức ứng dụng/routine cần phân biệt:

- Invalid input/unsupported identifier.
- Permission denied.
- Object not found.
- Constraint violation.
- Unexpected internal error.

Đừng bắt `WHEN OTHERS THEN RETURN 0` cho mọi lỗi và làm kết quả nghiệp vụ bị sai âm thầm.

### 35.4. Error messages và quote escaping

Một query dùng `format('%I')` có thể vẫn lỗi vì object không tồn tại hoặc user không có quyền. Đây là lỗi hợp lệ, không có nghĩa `%I` bị hỏng.

## 36. Bộ kiểm thử input cho quoting

Với lab, thử các giá trị sau bằng prepared/bound parameters:

| Input | Tình huống cần kiểm tra |
| --- | --- |
| `ALICE` | Giá trị đơn giản |
| `O'Reilly` | Một dấu nháy đơn |
| `A%_B` | LIKE wildcard literal |
| `VN-ĐỎ` | Unicode |
| `NULL` (SQL NULL) | Null parameter |
| `''` | Chuỗi rỗng |
| `'  spaced  '` | Khoảng trắng có ý nghĩa |
| `'select'` | SQL keyword nếu được dùng làm identifier |
| `'Order Details'` | Identifier có khoảng trắng |
| `'a"b'` | Identifier có double quote |
| `'quote_lab.orders'` | Tên chứa dấu chấm |
| `'x'' OR TRUE --'` | Text có thể thay đổi SQL nếu nối sai |
| Một chuỗi rất dài | Giới hạn input và tài nguyên |
| Chuỗi nhiều dấu `\` | Lớp escaping của string/regex |
| `pg_temp` | Không dùng như schema không tin cậy cho privileged references |
| Tên bảng không có trong allowlist | Phải từ chối |
| NULL sort column | Phải từ chối hoặc dùng default rõ |

### 36.1. Không chỉ test return values

Cần xác nhận:

- Hàm trả đúng tập rows.
- Không truy vấn ngoài tenant.
- Không thay đổi data ngoài ý muốn.
- Không lộ internal SQL trong logs.
- SQL không bị lỗi vì NULL command string.
- Không nhận arbitrary identifier/SQL syntax.
- Quyền `SECURITY DEFINER` đúng nếu có.
- Performance vẫn chấp nhận được với pattern rộng.

### 36.2. Negative tests quan trọng

Một input không hợp lệ nên bị **từ chối rõ ràng**, không được rơi sang query toàn bảng hoặc bảng mặc định có quyền lớn hơn.

### 36.3. Kiểm thử connection pool

Nếu routine dùng session-level `search_path` hay custom context, cần test nhiều request liên tiếp trên cùng connection; tránh rò state từ request A sang B.

## 37. Những lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Nối input vào dấu nháy đơn thủ công | Có thể phá SQL literal | `EXECUTE ... USING` |
| Dùng `quote_literal` với NULL rồi nối `||` | Cả command thành NULL | `USING` hoặc `quote_nullable` |
| Viết `column = NULL` | UNKNOWN, không match NULL | `IS NOT DISTINCT FROM`/`IS NULL` |
| Dùng `quote_literal` cho tên bảng | Tạo string literal, không phải identifier | `%I` / `quote_ident` |
| Dùng `quote_ident` cho giá trị | Tạo identifier, không phải data literal | `USING` / `%L` |
| Quote `schema.table` bằng một %I | Thành một identifier chứa dấu chấm | `%I.%I` |
| Dùng `%s` với user input | Không SQL-escape | Allowlist/fixed fragments hoặc `USING` |
| Bind $1 làm tên cột | Parameters là values | Identifier `%I` + allowlist |
| Bind $1 thành ORDER BY DESC | Keywords không bind như values | ASC/DESC từ code |
| Cho caller chọn bảng tùy ý | Quote không kiểm tra quyền | Mapping allowlist |
| Cho caller chọn tenant tùy ý | Authorization bypass | Trusted context + validation |
| Chỉ bảo vệ JDBC outer call | Function nội bộ vẫn nối chuỗi | Bind cả trong PL/pgSQL |
| `LIKE $1` coi input literal | % và _ còn là wildcards | ESCAPE pattern riêng |
| Truyền regex tự do vô hạn | Pattern có thể tốn CPU | Policy/timeout/index |
| Ghép input vào dollar quote | Delimiter có thể bị phá | Bind/quote values |
| Đặt untrusted schema trong search_path | Object/function hijacking | Trusted path |
| Bỏ pg_temp trong definer path | Temp relation có thể được xét trước | Liệt kê pg_temp cuối |
| SECURITY DEFINER owner superuser | Impact rất rộng | Least-privilege owner |
| PUBLIC EXECUTE còn mở | Nhiều role có thể gọi | REVOKE trong transaction |
| Schema tên đã quote nên an toàn | Vẫn có thể chọn object nhạy cảm | Authorization |
| Dùng `EXECUTE` mỗi row | Tốn planning overhead | SQL set-based |
| Nối text số/ngày bằng cast tùy tiện | Type/timezone semantics dễ sai | Bind typed parameters |
| DDL name quote đúng nhưng không có rights | Permission vẫn áp dụng | Quản lý GRANT/owner |
| Log toàn bộ v_sql | Có thể lộ PII/secrets | Structured sanitized logging |

## 38. Bài tập thực hành có đáp án

Bài tập sử dụng schema `quote_lab`. Những đoạn `EXECUTE` dạng statement cần đặt trong PL/pgSQL function/DO block có khai báo biến tương ứng; không gửi trực tiếp cú pháp `INTO variable USING ...` như một SQL command ngoài PL/pgSQL.

### Bài 1. Identifier và literal khác nhau thế nào?

**Đáp án:** identifier đặt tên cho object/cột; literal là dữ liệu trong một biểu thức SQL. Double quotes thường dành cho quoted identifiers, single quotes dành cho string literals.

### Bài 2. `quote_ident` dùng cho loại gì?

**Đáp án:** một SQL identifier như tên schema, bảng hoặc cột.

### Bài 3. `quote_literal` dùng cho loại gì?

**Đáp án:** giá trị dữ liệu cần biểu diễn thành một literal trong SQL text; nếu câu SQL hỗ trợ parameters, ưu tiên `USING`.

### Bài 4. `quote_nullable` khác `quote_literal` ở đâu?

**Đáp án:** `quote_nullable(NULL)` trả text chứa token `NULL`, còn `quote_literal(NULL)` trả SQL NULL.

### Bài 5. `format('%I')` tương tự hàm nào?

**Đáp án:** `quote_ident` về mục đích quote identifier.

### Bài 6. `format('%L')` tương tự hàm nào?

**Đáp án:** `quote_nullable` về cách biểu diễn literal và NULL trong dynamic SQL text.

### Bài 7. `format('%s')` có tự escape SQL không?

**Đáp án:** không. Không dùng với text tùy ý ở vị trí SQL syntax.

### Bài 8. Quote hai thành phần schema/table thế nào?

```sql
SELECT format('%I.%I', 'quote_lab', 'orders');
```

**Đáp án:** quote từng component riêng rồi nối dấu chấm cú pháp.

### Bài 9. Vì sao `format('%I','quote_lab.orders')` sai ý định?

**Đáp án:** nó tạo một identifier chứa dấu chấm, không phải fully qualified `schema.table`.

### Bài 10. `quote_ident('orders')` có luôn thêm double quotes không?

**Đáp án:** không. Chỉ thêm khi cần để biểu diễn identifier đúng.

### Bài 11. Vì sao `quote_ident('Order Details')` phải dùng quotes?

**Đáp án:** identifier có khoảng trắng không thể viết unquoted theo cú pháp thông thường.

### Bài 12. Giá trị `O'Reilly` nên đưa vào dynamic SELECT ra sao?

```sql
EXECUTE
    'SELECT count(*) FROM quote_lab.orders
     WHERE customer_code = $1'
INTO v_count
USING p_customer_code;
```

**Đáp án:** bind `p_customer_code`, không tự nối dấu nháy.

### Bài 13. Vì sao `quote_literal(NULL)` tạo lỗi khi nối SQL?

**Đáp án:** hàm STRICT trả SQL NULL, kéo cả chuỗi nối `||` thành NULL.

### Bài 14. `quote_nullable(NULL)` có tạo string literal `'NULL'` không?

**Đáp án:** nó trả một text chứa token SQL `NULL` không có nháy literal bao quanh, không phải string value `'NULL'`.

### Bài 15. `column = NULL` có match rows NULL không?

**Đáp án:** không. So sánh ra UNKNOWN; dùng `IS NULL` hoặc `IS NOT DISTINCT FROM`.

### Bài 16. Viết null-safe comparison trong dynamic SQL

```sql
EXECUTE
    'SELECT count(*) FROM quote_lab.orders
     WHERE note IS NOT DISTINCT FROM $1'
INTO v_count
USING p_note;
```

**Đáp án:** xử lý đúng cả khi p_note NULL và không NULL.

### Bài 17. `EXECUTE ... USING` bind được tên bảng không?

**Đáp án:** không; parameter placeholders là values, không phải identifiers.

### Bài 18. Làm sao chọn tên bảng an toàn?

**Đáp án:** mapping allowlist từ lựa chọn hợp lệ sang tên bảng cố định, sau đó `format('%I.%I')`.

### Bài 19. Vì sao quote tên bảng đúng vẫn có thể lộ dữ liệu?

**Đáp án:** user có thể chọn một tên bảng hợp lệ nhưng không được phép; quoting không thực hiện authorization.

### Bài 20. Dùng format tạo SELECT cột nào?

```sql
SELECT format(
    'SELECT %I FROM %I.%I',
    'customer_code',
    'quote_lab',
    'orders'
);
```

**Đáp án:** tạo SQL text với column identifier và fully qualified table.

### Bài 21. `%I` và `%L` dùng ngược được không?

**Đáp án:** không. Một bên là name, một bên là value literal; dùng sai có thể tạo SQL lỗi hoặc sai nghĩa.

### Bài 22. Identifier chứa double quote được xử lý thế nào?

**Đáp án:** `quote_ident` nhân đôi dấu double quote khi cần bên trong quoted identifier.

### Bài 23. Tại sao keyword `select` phải quote khi là tên cột?

**Đáp án:** `select` là SQL keyword; quoted identifier `"select"` giúp parser hiểu đó là tên object/cột.

### Bài 24. Sử dụng `%s` cho DESC an toàn khi nào?

**Đáp án:** khi fragment được tạo từ Boolean/enum đã allowlist, ví dụ code chọn đúng một trong `'ASC'` hoặc `'DESC'`.

### Bài 25. Có nên chấp nhận sort string kiểu `'amount DESC, secret'` từ user?

**Đáp án:** không. User phải chọn sort mode đã định nghĩa, không cung cấp raw SQL fragment.

### Bài 26. Page size đã bind có cần validate không?

**Đáp án:** có. Bind chống injection nhưng không giới hạn rows/CPU; ví dụ chỉ cho phép 1–100.

### Bài 27. SQL EXECUTE của PREPARE khác PL/pgSQL EXECUTE thế nào?

**Đáp án:** SQL EXECUTE chạy prepared statement theo tên; PL/pgSQL EXECUTE chạy command_string dynamic, hỗ trợ INTO/USING.

### Bài 28. Dynamic SQL PL/pgSQL có cache plan giống static SQL không?

**Đáp án:** thông thường nó lập plan lại cho mỗi EXECUTE, có thể tốn overhead nhưng đôi khi hữu ích với tham số lệch.

### Bài 29. Để đọc bảng cố định có nên dùng EXECUTE không?

**Đáp án:** thường không cần; SQL tĩnh dễ review, có thể dùng cached plan và ít injection surface.

### Bài 30. Vì sao bind ở JDBC không đủ nếu PL/pgSQL nối chuỗi?

**Đáp án:** outer JDBC chỉ bảo vệ câu SQL gọi routine; bên trong function có thể vẫn tái biến data thành SQL syntax khi nối string.

### Bài 31. Dùng dollar quoting để chèn input người dùng có an toàn tuyệt đối?

**Đáp án:** không. Delimiter có thể xuất hiện trong input; dollar quoting thích hợp cho source code cố định, không thay parameterization.

### Bài 32. `LIKE $1` có tự escape `%` và `_` không?

**Đáp án:** không; chúng vẫn là pattern wildcards. Khi tìm literal, escape theo `ESCAPE '!'` và bind pattern.

### Bài 33. Test literal `A%_B` trong customer_code?

**Đáp án:** tạo pattern contains `%A!%!_B%` với `ESCAPE '!'` sau khi escape input đúng thứ tự, rồi bind; không để %/_ từ input là wildcard.

### Bài 34. Regex bind có tự biến metacharacters thành literal không?

**Đáp án:** không. Nó chỉ giữ regex source là parameter của SQL, còn regex engine vẫn diễn giải pattern; cần policy/regex quoting hoặc đổi sang LIKE literal.

### Bài 35. Với utility `COMMENT ON` nên quote value thế nào?

```sql
SELECT format(
    'COMMENT ON TABLE %I.%I IS %L',
    'quote_lab',
    'orders',
    'Owner''s note'
);
```

**Đáp án:** `%I.%I` cho relation name, `%L` cho comment literal.

### Bài 36. Tên table có thể dùng `USING` trong `CREATE TABLE` không?

**Đáp án:** không. SQL grammar yêu cầu identifier; cần quote identifier, validate ownership/authorization và chỉ build DDL khi được phép.

### Bài 37. `quote_ident` có tạo bảng nếu tên chưa tồn tại không?

**Đáp án:** không. Nó chỉ trả text, không thao tác catalog.

### Bài 38. `regclass` có bảo đảm caller được phép dùng relation không?

**Đáp án:** không; nó hỗ trợ object resolution/OID, còn quyền và allowlist cần kiểm tra riêng.

### Bài 39. Vì sao `SECURITY DEFINER` đặc biệt rủi ro với dynamic table names?

**Đáp án:** SQL chạy theo quyền owner; caller có thể khiến owner truy cập object không được phép nếu không có mapping/authorization.

### Bài 40. Tại sao phải khóa search_path trong definer?

**Đáp án:** giảm rủi ro shadowing unqualified objects qua untrusted schema hoặc pg_temp. Dùng trusted path và fully qualified sensitive references.

### Bài 41. `pg_temp` nên nằm vị trí nào trong definer path?

**Đáp án:** thường đặt cuối path, ví dụ `pg_catalog, quote_lab, pg_temp` với quote_lab là schema đáng tin.

### Bài 42. `pg_catalog` nên đặt ở đâu?

**Đáp án:** ưu tiên trước những schemas ứng dụng để giảm rủi ro built-in lookup bị shadow bởi objects không tin cậy.

### Bài 43. SECURITY DEFINER có tự tuân thủ RLS của caller không?

**Đáp án:** không được giả định; effective owner role có thể bypass RLS theo quyền và ownership. Phải kiểm tra row authorization tường minh.

### Bài 44. Cấp EXECUTE cho PUBLIC có nguy hiểm không?

**Đáp án:** có thể nguy hiểm với privileged routine. Nên thu hồi PUBLIC EXECUTE và chỉ cấp roles cần thiết theo policy.

### Bài 45. Có cần kiểm tra quyền tenant sau khi đã quote bảng/cột không?

**Đáp án:** có. Quote chỉ bảo vệ syntax, còn tenant isolation phải dựa trên context đáng tin và ràng buộc query/RLS thích hợp.

### Bài 46. Dùng `GET DIAGNOSTICS ROW_COUNT` khi nào?

**Đáp án:** sau DML dynamic cần biết số rows bị ảnh hưởng để kiểm tra business invariants và phát hiện không có/nhân nhiều rows.

### Bài 47. Vì sao không log toàn bộ dynamic SQL?

**Đáp án:** command text có thể chứa literals, identifiers và thông tin nội bộ nhạy cảm; ưu tiên template IDs/metadata an toàn và masking.

### Bài 48. Vì sao cần test dấu nháy, NULL và Unicode?

**Đáp án:** những input này bộc lộ lỗi escaping, parse/type assumptions và normalization khác mà happy path không phát hiện.

### Bài 49. Vì sao SQL injection và pattern injection khác nhau?

**Đáp án:** SQL injection làm dữ liệu thay đổi **cấu trúc SQL**; pattern injection thay đổi **semantics của LIKE/regex** dù SQL syntax đã được bind an toàn.

### Bài 50. Liệt kê các bước review một dynamic SQL function

**Đáp án gợi ý:**

1. Có thật sự cần dynamic SQL không?
2. Tách identifiers, values và fixed SQL fragments.
3. Values dùng `USING`; DDL literal cần `%L` khi bắt buộc.
4. Identifiers dùng `%I` và allowlist.
5. Schema/table được quote riêng bằng `%I.%I`.
6. Không để raw user input vào `%s`.
7. Xử lý NULL rõ với `IS NOT DISTINCT FROM` hoặc branching.
8. Bảo đảm tenant/role/object authorization, nhất là trong definer routines.
9. Khóa trusted search_path và pg_temp placement.
10. Kiểm tra `PUBLIC EXECUTE` và owner privileges.
11. Test dấu nháy, Unicode, NULL, LIKE wildcards, identifiers lạ.
12. Đo performance, logs và behavior dưới concurrency.

## 39. Quy trình review trước khi đưa dynamic SQL vào production

### Bước 1. Phân loại dữ liệu đầu vào

Lập bảng:

| Input | Loại | Phương án |
| --- | --- | --- |
| `tenant_id` | Data value | Bind, kiểm tra authorization |
| `customer_code` | Data value | Bind `$1` |
| `amount` | Data value | Bind numeric |
| `table_selector` | Business choice | Allowlist -> fixed table identifier |
| `column_selector` | Business choice | Allowlist -> `%I` |
| `sort_order` | SQL syntax fragment | Enum -> fixed `ASC`/`DESC` |
| `comment_text` | DDL literal | `%L` khi không bind được |
| `search_text` | LIKE literal/pattern | Bind + wildcard escaping khi cần |
| `regex` | Regex pattern | Bind + validation/limits |

### Bước 2. Mặc định dùng static SQL

Hỏi “có thể viết một query tĩnh với parameters không?”. Nếu có, thường ưu tiên SQL tĩnh.

### Bước 3. Nếu buộc dynamic, xây từ trusted building blocks

```text
SQL template cố định
    |
+---+------------------+
|                      |
Identifiers        Data values
|                      |
Allowlist            USING
|                      |
%I + schema        $1, $2...
qualification
|                      |
+----------+-----------+
           |
        EXECUTE
```

### Bước 4. Kiểm thử negative cases

- Tên object không có trong allowlist.
- NULL object name.
- Identifier chứa dấu chấm.
- Value chứa dấu nháy đơn.
- Unicode/quotes/backslashes.
- LIKE pattern với literal %/_.
- User có quyền hạn chế.
- Multi-tenant unauthorized ID.
- Function definer owner có quyền rộng.
- Connection pool với search_path khác.
- Input quá dài và query quá nặng.

### Bước 5. Đánh giá plan và overhead

Dùng `EXPLAIN (ANALYZE, BUFFERS)` cho query tương ứng với tham số đại diện. Dynamic SQL không tự dùng index tốt hơn vì đã quote đúng.

### Bước 6. Quyền và logging

- Grants/ownership đúng.
- Không lộ data từ rows ngoài phạm vi.
- Không log raw values/secrets nếu không cần.
- Có timeout, giới hạn kết quả và rate limits phù hợp.
- Có rollback/migration plan cho DDL dynamic.

## 40. Checklist nhanh

| Câu hỏi | Trạng thái cần đạt |
| --- | --- |
| Câu SQL có nhất thiết phải dynamic? | Có lý do cụ thể |
| Các values được bind? | `EXECUTE ... USING` |
| Có nối quote_literal vào optimizable SQL không cần thiết? | Ưu tiên sửa sang USING |
| Có NULL values? | Không làm command string thành NULL |
| Cần null-safe equality? | `IS NOT DISTINCT FROM` |
| Các identifiers có quote đúng? | `%I`/`quote_ident` |
| Schema và table được quote riêng? | `%I.%I` |
| Identifier đã được allowlist? | Không chọn arbitrary object |
| Có user input vào %s? | Không |
| ORDER BY direction có enum? | Fixed ASC/DESC |
| Page size có giới hạn? | Validate và bind |
| DDL literal có %L khi cần? | Đúng loại placeholder |
| Caller có quyền trên object? | Permission + authorization |
| API có tenant isolation? | Trusted context |
| SECURITY DEFINER dùng least privilege? | Owner giới hạn |
| search_path có pg_catalog/trusted/pg_temp? | Đúng thứ tự, trusted schema |
| Có fully qualified references? | Với objects nhạy cảm |
| Có RLS owner bypass? | Đã kiểm tra |
| PUBLIC EXECUTE đã hạn chế? | Chỉ roles cần |
| Có input quote/NULL/Unicode tests? | Đã có |
| LIKE wildcard có ý nghĩa rõ? | Escape khi tìm literal |
| Có chống query quá đắt? | Timeout/limits/index |
| Dynamic SQL log có PII? | Redact/aggregate |
| DML kiểm tra affected rows? | Business invariant |
| Có chạy EXECUTE per-row quá nhiều? | Cân nhắc set-based |
| Có đo query plan thật? | EXPLAIN/metrics |
| Có test connection pool? | No cross-request state leakage |

## 41. Tổng kết

Để tránh SQL injection trong PL/pgSQL, phải phân biệt **tên đối tượng**, **giá trị dữ liệu** và **cấu trúc câu SQL**.

Các quy tắc cần nhớ:

1. **`EXECUTE ... USING` là lựa chọn ưu tiên cho values** trong các command có hỗ trợ parameters.
2. **`quote_ident` / `format('%I')` dành cho identifiers**, không dành cho values.
3. **`quote_literal` / `format('%L')` dành cho SQL literal text**, thường chỉ cần khi buộc phải tạo một chuỗi SQL.
4. **`quote_nullable` và `%L` xử lý SQL NULL** khi tạo literal text; `quote_literal(NULL)` trả SQL NULL và có thể khiến toàn bộ command string thành NULL.
5. **`= NULL` không tìm rows NULL**; dùng `IS NULL` hoặc `IS NOT DISTINCT FROM` theo semantics cần thiết.
6. **`format('%s')` không quote hay escape SQL**, không nhận raw user input ở vị trí cú pháp SQL.
7. **`%I.%I` đúng cho schema.table**, còn `%I` với chuỗi `schema.table` sẽ tạo một identifier chứa dấu chấm.
8. **Bind parameters không thay tên bảng/cột/keywords**. Với dynamic identifiers, dùng allowlist + `%I`.
9. **Quoting không phải authorization**: một tên object hợp lệ vẫn có thể là object mà caller không được xem.
10. **SQL injection khác pattern injection**: bind text vào LIKE/regex vẫn giữ các wildcard/metacharacters của pattern language.
11. **`SECURITY DEFINER` tăng hậu quả khi kiểm soát object names hoặc row scope sai**; owner cần least privilege, search_path an toàn và explicit authorization.
12. **SQL tĩnh thường tốt hơn khi cấu trúc không đổi**; dynamic EXECUTE có planning overhead và thêm bề mặt lỗi.
13. **JDBC PreparedStatement ở tầng Java không tự bảo vệ PL/pgSQL dynamic SQL ở tầng database** nếu hàm nội bộ vẫn nối chuỗi.
14. **Kiểm thử cả NULL, quote, Unicode, input dài, tenant khác và quyền thấp**, không chỉ happy path.
15. **Tối ưu và bảo mật phải đi cùng nhau**: đúng quoting chưa đủ nếu query quét toàn bảng hoặc trả dữ liệu không được phép.

Mẫu PL/pgSQL nên thuộc lòng:

```sql
-- Giả định v_schema/v_table/v_column đã qua allowlist,
-- p_tenant_id và p_value là data values.
EXECUTE format(
    'SELECT count(*)
       FROM %I.%I
      WHERE tenant_id = $1
        AND %I = $2',
    v_schema,
    v_table,
    v_column
)
INTO v_count
USING p_tenant_id, p_value;
```

**Quy tắc cuối cùng:** khi thấy `EXECUTE` trong PL/pgSQL, hãy hỏi lần lượt: **“Phần nào là SQL do lập trình viên kiểm soát, phần nào là tên object, phần nào là value, ai được phép chọn object đó, và SQL có thể chạy dưới quyền của ai?”**. Nếu mỗi phần đều có biện pháp tương ứng — **static template, bind, quote identifier, allowlist và authorization** — mã SQL động sẽ an toàn và dễ bảo trì hơn nhiều.
