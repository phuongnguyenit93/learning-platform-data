# SQL động với EXECUTE, USING và format

Một hệ thống bán hàng có bảng đơn hàng, bảng đơn hàng lưu trữ và nhiều loại báo cáo. Hầu hết truy vấn đều biết tên bảng, tên cột và cấu trúc từ lúc viết code. Nhưng một số tác vụ cần **xây câu lệnh SQL tại thời điểm chạy**: chọn bảng đích theo cấu hình hợp lệ, chọn cột sắp xếp theo yêu cầu người dùng, áp dụng một thao tác bảo trì trên nhiều bảng hoặc tạo các đối tượng database theo một quy tắc đã được kiểm soát.

Trong PL/pgSQL, câu lệnh **`EXECUTE`** cho phép thực thi một chuỗi SQL được xây động. Hai công cụ đi cùng nó đặc biệt quan trọng:

- **`USING`**: truyền **giá trị dữ liệu** vào placeholders `$1`, `$2`, ... bên trong câu lệnh động; giúp tránh việc nối/escape giá trị bằng tay.
- **`format(...)`**: dựng chuỗi SQL có **identifiers** như tên schema/bảng/cột với `%I`, hoặc literals với `%L` khi thực sự cần; `%s` chỉ chèn text thô và phải được kiểm soát chặt.

Đây là một chủ đề vừa về **cú pháp và lập kế hoạch truy vấn**, vừa về **bảo mật và quyền truy cập**. Viết được một câu SQL động là chưa đủ: cần biết khi nào nó thực sự cần thiết, đối số nào được truyền như dữ liệu, cách bảo vệ identifiers, cách nhận kết quả và ảnh hưởng đến transaction/concurrency.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt SQL **tĩnh** với SQL **động** trong PL/pgSQL và chọn đúng trường hợp.
2. Viết cú pháp `EXECUTE command-string [INTO [STRICT] target] [USING ...]`.
3. Sử dụng placeholders `$1`, `$2` để bind các giá trị vào câu SQL động.
4. Dùng `format('%I', ...)`, `format('%L', ...)` và `format('%s', ...)` đúng ngữ nghĩa.
5. Phân biệt **giá trị dữ liệu**, **tên đối tượng**, **SQL keyword** và **SQL fragment**.
6. Xây truy vấn động SELECT/INSERT/UPDATE/DELETE với lọc tenant, conditions và tên bảng.
7. Nhận một giá trị bằng `INTO`, phát hiện 0/nhiều rows bằng `INTO STRICT`.
8. Dùng `GET DIAGNOSTICS ... ROW_COUNT` và hiểu giới hạn của `FOUND` sau `EXECUTE`.
9. Dùng `RETURN QUERY EXECUTE` và `FOR ... IN EXECUTE` để xử lý nhiều hàng.
10. Xây dynamic ORDER BY/DDL an toàn với whitelist và quyền thực thi phù hợp.
11. Hiểu vì sao `EXECUTE` lập kế hoạch lại mỗi lần, và khi nào điều này có lợi/hại.
12. Vận dụng với JDBC/Spring, error handling, observability và bài tập thực hành.

> **Môi trường:** Các ví dụ nhắm tới PostgreSQL hiện đại, dùng `LANGUAGE plpgsql` trong schema thực hành. `EXECUTE` được giải thích ở đây là **câu lệnh bên trong PL/pgSQL**, không nên nhầm với lệnh SQL cấp server `EXECUTE prepared_statement(...)`. Các ví dụ DDL/DML có tác dụng thay đổi database; chỉ chạy trên database lab. Không thực thi tên bảng hoặc SQL fragment không đáng tin dưới role đặc quyền.

## 2. SQL tĩnh là lựa chọn mặc định

Giả sử cần đếm đơn hàng:

```sql
SELECT count(*)
FROM sales.orders
WHERE tenant_id = 10;
```

Nếu tên bảng luôn là `sales.orders`, **không cần** SQL động.

Trong PL/pgSQL:

```sql
SELECT count(*)
INTO v_count
FROM sales.orders
WHERE tenant_id = p_tenant_id;
```

Đây là truy vấn tĩnh: PostgreSQL biết cấu trúc SQL và PL/pgSQL có thể quản lý kế hoạch thực thi theo cơ chế cache/generic-custom plan.

### Khi nào mới cần SQL động?

Ví dụ:

- Tên bảng thay đổi trong một danh sách đã được kiểm soát.
- Tên cột sắp xếp hoặc cột báo cáo thay đổi theo lựa chọn hợp lệ.
- Tạo bảng/index/constraint bằng DDL cho công việc migration/admin.
- Tạo điều kiện SQL khác nhau về **cấu trúc** theo những tính năng được bật.
- Một truy vấn cần kế hoạch riêng mỗi lần vì giá trị đầu vào có selectivity khác biệt lớn, sau khi đã benchmark.

Đừng dùng SQL động chỉ vì muốn truyền `tenant_id` hay `status`: câu SQL tĩnh với parameters bình thường đã giải quyết.

## 3. Bức tranh tổng quát về SQL động

```text
                         PL/pgSQL function
                                  │
                ┌─────────────────┴───────────────────┐
                │                                     │
          SQL structure                          Data values
       schema/table/column                       tenant/status
                │                                     │
      whitelist + format('%I')                      USING
        hoặc keyword đã                         $1, $2, $3...
          được validate                             │
                │                                     │
                └─────────────────┬───────────────────┘
                                  │
                                  ▼
                      EXECUTE dynamic SQL
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
               SELECT result               DML/DDL effect
                    │                           │
            INTO / RETURN QUERY          ROW_COUNT / constraint
             FOR IN EXECUTE                transaction
```

**Ranh giới quan trọng:** `USING` dành cho các giá trị xuất hiện tại vị trí **data values** trong các câu lệnh được hỗ trợ. Nó không thể biến một string thành tên bảng hoặc một từ khóa SQL. Với identifiers, cần dựng cú pháp SQL bằng quote đúng kiểu.

## 4. Cú pháp EXECUTE của PL/pgSQL

Mẫu:

```sql
EXECUTE command_string
    [ INTO [STRICT] target ]
    [ USING expression [, ...] ];
```

Trong đó:

- `command_string`: biểu thức SQL tạo ra một chuỗi `text` chứa câu lệnh cần thực thi.
- `INTO target`: lấy một hàng kết quả vào biến, record hoặc danh sách biến.
- `STRICT`: yêu cầu đúng **một hàng**, nếu không sẽ phát sinh exception.
- `USING expression...`: truyền giá trị cho `$1`, `$2`,... trong command string.

Ví dụ tối giản:

```sql
DO $$
DECLARE
    v_result integer;
BEGIN
    EXECUTE 'SELECT $1::integer + $2::integer'
    INTO v_result
    USING 7, 5;

    RAISE NOTICE 'Result = %', v_result;
END;
$$;
```

Về mặt giá trị, kết quả là 12.

### `$1` trong câu SQL động là gì?

`$1`, `$2` trong **command string** là placeholders tương ứng các biểu thức ở mệnh đề `USING` của chính lần `EXECUTE` đó. Đừng tự cho rằng chúng luôn trực tiếp tham chiếu các tham số thứ nhất/thứ hai của function PL/pgSQL bao quanh.

## 5. Phân biệt hai lệnh EXECUTE dễ nhầm

Trong PostgreSQL có ít nhất hai ngữ cảnh:

**PL/pgSQL dynamic EXECUTE:**

```sql
DO $$
DECLARE v_value integer;
BEGIN
    EXECUTE 'SELECT $1 + 1'
    INTO v_value
    USING 5;
END;
$$;
```

**SQL PREPARE/EXECUTE ở cấp SQL:**

```sql
PREPARE add_one(integer) AS
SELECT $1 + 1;

EXECUTE add_one(5);

DEALLOCATE add_one;
```

| PL/pgSQL `EXECUTE` | SQL `PREPARE`/`EXECUTE` |
|---|---|
| Nhận chuỗi SQL động | Dùng một tên prepared statement đã định nghĩa |
| Dùng `USING` trong PL/pgSQL | Truyền đối số vào `EXECUTE name(...)` |
| Parse/plan cho câu lệnh động mỗi lần gọi | Có cơ chế reuse prepared statement/plan theo quy tắc PostgreSQL |
| Kết quả có thể nhận bằng PL/pgSQL `INTO` | Kết quả là SQL result set của lệnh cấp server |
| Phù hợp khi **cấu trúc SQL** thay đổi | Phù hợp khi **cấu trúc SQL giữ cố định** qua nhiều lần gọi |

Không trộn cú pháp `EXECUTE 'SELECT ...' USING ...` của PL/pgSQL với `EXECUTE prepared_name(...)` trong ví dụ SQL thông thường.

## 6. Tạo schema và dữ liệu lab

Tạo schema riêng để không ảnh hưởng dữ liệu ứng dụng:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_dynamic_sql;

CREATE TABLE lesson_dynamic_sql.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    amount NUMERIC(14,2) NOT NULL
        CHECK (amount >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_orders_tenant_status_created
ON lesson_dynamic_sql.orders (
    tenant_id, status, created_at DESC
);

INSERT INTO lesson_dynamic_sql.orders (
    tenant_id, customer_id, status, amount, created_at
)
VALUES
    (10, 101, 'NEW',       120000.00, TIMESTAMPTZ '2026-10-01 09:00:00+07'),
    (10, 101, 'PAID',      350000.00, TIMESTAMPTZ '2026-10-02 09:00:00+07'),
    (10, 102, 'PAID',      990000.00, TIMESTAMPTZ '2026-10-03 09:00:00+07'),
    (10, 103, 'CANCELLED', 150000.00, TIMESTAMPTZ '2026-10-04 09:00:00+07'),
    (20, 201, 'PAID',      870000.00, TIMESTAMPTZ '2026-10-05 09:00:00+07'),
    (20, 202, 'NEW',       210000.00, TIMESTAMPTZ '2026-10-06 09:00:00+07');
```

### Vì sao có tenant_id?

Một hệ thống đa tenant phải kiểm soát truy cập theo người dùng và tổ chức. Trong các lab, `p_tenant_id` minh họa cách filter; trong production, giá trị tenant phải xuất phát từ **ngữ cảnh ủy quyền đáng tin**, không chỉ một số nguyên do client tùy ý gửi.

### Quy tắc khi thử lại

Các lệnh tạo bảng và insert trên được thiết kế để chạy khi schema/table chưa có. Nếu đã chạy một lần, hãy dùng database lab mới hoặc dọn dữ liệu có kiểm soát; không chạy lại `CREATE TABLE` cùng tên rồi coi báo lỗi “already exists” là vấn đề của `EXECUTE`.

## 7. Cách tĩnh: không cần EXECUTE khi cấu trúc cố định

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.total_paid_static(
    p_tenant_id BIGINT
)
RETURNS NUMERIC
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_total NUMERIC;
BEGIN
    SELECT COALESCE(SUM(amount), 0)
    INTO v_total
    FROM lesson_dynamic_sql.orders
    WHERE tenant_id = p_tenant_id
      AND status = 'PAID';

    RETURN v_total;
END;
$$;

SELECT lesson_dynamic_sql.total_paid_static(10);
-- 1340000.00 (350000 + 990000)
```

Ưu điểm:

- SQL đọc được trực tiếp.
- Phụ thuộc bảng/cột rõ hơn.
- Không phải tự dựng command string.
- Dễ quản lý kiểu dữ liệu và kiểm thử.
- PL/pgSQL có thể tận dụng cơ chế quản lý plan cho SQL tĩnh.

Nếu nghiệp vụ chỉ truy vấn `lesson_dynamic_sql.orders`, đây là phương án thường nên chọn.

## 8. Chuyển sang SQL động khi tên bảng thay đổi

Giả sử có nhiều bảng báo cáo với cùng cấu trúc `tenant_id`, `status` và `amount`, được chọn theo cấu hình hợp lệ.

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.total_by_table(
    p_table_name TEXT,
    p_tenant_id BIGINT,
    p_status TEXT
)
RETURNS NUMERIC
LANGUAGE plpgsql
AS $$
DECLARE
    v_total NUMERIC;
    v_sql TEXT;
BEGIN
    IF p_table_name IS DISTINCT FROM 'orders' THEN
        RAISE EXCEPTION 'Unsupported source table: %', p_table_name;
    END IF;

    v_sql := format(
        'SELECT COALESCE(SUM(amount), 0)
           FROM %I.%I
          WHERE tenant_id = $1 AND status = $2',
        'lesson_dynamic_sql',
        p_table_name
    );

    EXECUTE v_sql
    INTO v_total
    USING p_tenant_id, p_status;

    RETURN v_total;
END;
$$;

SELECT lesson_dynamic_sql.total_by_table(
    'orders',
    10,
    'PAID'
);
-- 1340000.00
```

### Phân tích

`format('%I.%I', 'lesson_dynamic_sql', p_table_name)` tạo tên đối tượng SQL theo hai thành phần schema/table, mỗi thành phần được quote đúng.

`$1` là `p_tenant_id`, `$2` là `p_status` do `USING` truyền vào. Không nối trực tiếp các giá trị này vào SQL string.

### Vì sao có whitelist?

Dù `%I` giúp **quote tên** chống phá cấu trúc câu SQL, nó không chứng minh người gọi **được phép** đọc bảng đó. Một function nhận tên bảng tùy ý có thể vô tình biến thành API đọc những đối tượng khác mà role chủ function có quyền.

Ví dụ lab chỉ cho `orders`; khi mở rộng, hãy dùng danh sách bảng cho phép theo nghiệp vụ, quyền và cấu trúc dữ liệu.

## 9. Ba loại thành phần cần xử lý khác nhau

| Thành phần | Ví dụ | Cách đưa vào dynamic SQL |
|---|---|---|
| **Giá trị dữ liệu** | `tenant_id = 10`, `status = 'PAID'` | `$1`/`$2` + `USING` |
| **Tên đối tượng** | `lesson_dynamic_sql.orders` | `format('%I.%I', schema, table)` |
| **SQL keyword cố định** | `ASC`, `DESC` | Validate/whitelist rồi mới dùng text vào cấu trúc |
| **SQL fragment phức tạp** | `WHERE ... AND ...` | Sinh từ các thành phần đã kiểm soát, không nhận nguyên raw text từ client |

### Ví dụ ranh giới

Không dùng:

```sql
-- Sai: placeholder không thay được tên bảng.
EXECUTE 'SELECT count(*) FROM $1'
INTO v_count
USING p_table_name;
```

PostgreSQL cần biết **relation identifier** tại thời điểm parse SQL. `$1` đại diện một **giá trị**, không phải một mảnh cú pháp có thể thay bảng/cột.

Ngược lại, không nên dùng `format('%I', p_status)` vì `p_status` là **giá trị text** trong điều kiện `WHERE`, không phải tên cột.

## 10. format('%I'): quote identifier

`%I` đưa một argument thành SQL identifier được quote khi cần:

```sql
SELECT format('%I', 'orders');
-- orders

SELECT format('%I', 'Order Detail');
-- "Order Detail"

SELECT format('%I', 'order');
-- "order" nếu cần tránh keyword/đảm bảo cú pháp

SELECT format('%I.%I', 'sales reports', 'Order Detail');
-- "sales reports"."Order Detail"
```

### Tên schema.table không phải một identifier đơn

Điểm dễ sai:

```sql
SELECT format('%I', 'lesson_dynamic_sql.orders');
-- "lesson_dynamic_sql.orders"
```

Kết quả là **một tên đối tượng có dấu chấm bên trong tên**, không phải `schema.table`.

Muốn tên qualified, tách thành hai phần:

```sql
SELECT format(
    '%I.%I',
    'lesson_dynamic_sql',
    'orders'
);
-- lesson_dynamic_sql.orders
```

Với schema, table và column được lấy từ input, hãy áp dụng `%I` **cho từng thành phần**.

## 11. quote_ident và format('%I')

PostgreSQL cung cấp `quote_ident(text)`:

```sql
SELECT quote_ident('Order Detail');
-- "Order Detail"

SELECT format('%I', 'Order Detail');
-- "Order Detail"
```

Hai cách cùng phục vụ việc tạo identifier hợp lệ, nhưng `format` thường dễ đọc hơn khi cần lắp nhiều phần:

```sql
SELECT format(
    'SELECT %I FROM %I.%I',
    'amount',
    'lesson_dynamic_sql',
    'orders'
);
```

Thay vì nối chuỗi nhiều lần:

```sql
SELECT
    'SELECT ' || quote_ident('amount')
    || ' FROM '
    || quote_ident('lesson_dynamic_sql')
    || '.'
    || quote_ident('orders');
```

### %I không phải authorization

Nếu một role có quyền tạo bảng tên bất kỳ, `%I` chỉ làm tên đó được parse như identifier. Nó không hạn chế role nào có quyền xem/sửa bảng. Dùng whitelist, schema-qualified names và grants/RLS khi thiết kế routine có quyền.

## 12. format('%L'): quote SQL literal

`%L` biến một giá trị thành SQL literal có quoting phù hợp:

```sql
SELECT format('SELECT %L', 'O''Reilly');
-- SELECT 'O''Reilly'

SELECT format('SELECT %L', NULL::text);
-- SELECT NULL
```

`%L` tương đương việc quote theo semantics `quote_nullable`: giá trị NULL được biểu diễn thành text `NULL`, không làm cả câu chuỗi thành SQL NULL.

### Khi nào dùng?

Khi một utility statement hoặc vị trí cú pháp không chấp nhận bound parameter từ `USING`, bạn có thể cần chèn literal **đã quote đúng**.

Nhưng trong những lệnh data SQL như SELECT/INSERT/UPDATE/DELETE, **ưu tiên USING**: rõ kiểu dữ liệu, không phải convert giá trị thành text rồi parse lại.

Ví dụ:

```sql
-- Cách khuyến nghị:
EXECUTE
    'SELECT count(*) FROM lesson_dynamic_sql.orders
      WHERE status = $1'
INTO v_count
USING p_status;
```

Không phải mọi giá trị đều nên chuyển thành literal chỉ vì `%L` tồn tại.

## 13. format('%s'): chèn text thô

`%s` chèn text mà **không quote thành identifier hay literal**:

```sql
SELECT format(
    'ORDER BY amount %s',
    'DESC'
);
-- ORDER BY amount DESC
```

### Cảnh báo

Nếu `p_direction` do client gửi là một chuỗi tùy ý, dùng:

```sql
format('ORDER BY amount %s', p_direction)
```

có thể tạo ra SQL syntax ngoài mong đợi. **Chỉ sử dụng `%s` để chèn thành phần đã được whitelist** hoặc chuỗi SQL cấu trúc do ứng dụng tự sinh an toàn.

Ví dụ chọn hướng sắp xếp:

```sql
IF p_direction IS NULL
   OR upper(p_direction) NOT IN ('ASC', 'DESC') THEN
    RAISE EXCEPTION 'Invalid sort direction';
END IF;

v_direction := upper(p_direction);
-- Chỉ sau khi validate mới format(..., v_direction)
```

Với tên cột hãy dùng `%I`, không dùng `%s`; với giá trị dữ liệu hãy dùng `USING`, không dùng `%s`.

## 14. Bảng ghi nhớ %I, %L, %s và USING

| Cú pháp | Dùng cho | Input ví dụ | Kết quả/ý nghĩa |
|---|---|---|---|
| `%I` | Identifier | `'Order Detail'` | `"Order Detail"` |
| `%I.%I` | Schema và table | `'s', 't'` | `s.t` |
| `%L` | SQL literal | `'O''Reilly'` | `'O''Reilly'` trong SQL text |
| `%s` | Chuỗi thô đã validate | `'DESC'` | `DESC` |
| `$1` + `USING` | Giá trị parameter | `p_tenant_id` | Dữ liệu bound, không là SQL text |

### Quy tắc thực hành

> **Tên đối tượng dùng %I. Giá trị dùng USING. SQL keyword dùng danh sách cho phép. Không nhận nguyên SQL fragment từ người dùng.**

Đây là quy tắc quan trọng nhất khi bạn viết dynamic SQL có dữ liệu nhập từ application.

## 15. Những ký hiệu nâng cao của format

`format` hỗ trợ lựa chọn vị trí argument và một số width/flags:

```sql
SELECT format(
    '%2$I.%1$I',
    'orders',
    'lesson_dynamic_sql'
);
-- lesson_dynamic_sql.orders
```

`%2$I` dùng argument thứ hai làm identifier; `%1$I` dùng argument thứ nhất.

Khi tạo một câu SQL dài nhiều identifiers, positional placeholders có thể tránh việc lặp lại cùng đối số, nhưng cũng có thể làm code khó đọc. Với PL/pgSQL bình thường, thứ tự rõ ràng thường tốt hơn tối ưu số ký tự.

`format` không phải một cơ chế SQL AST builder: bạn vẫn phải hiểu cấu trúc query và kiểm tra input.

## 16. NULL trong format và quote functions

`%L` có thể xử lý SQL NULL để tạo literal `NULL`. `%I` không thể dùng một identifier NULL vì không tồn tại một tên bảng/cột “NULL identifier”.

```sql
SELECT format('%L', NULL::text);
-- NULL dưới dạng text trong chuỗi kết quả

SELECT format('%s', NULL::text);
-- Chuỗi rỗng tại vị trí %s
```

Thử:

```sql
-- Câu này phát sinh lỗi vì %I không chấp nhận NULL:
-- SELECT format('%I', NULL::text);
```

### quote_literal và quote_nullable

`quote_literal(NULL)` trả SQL NULL theo tính strict của function, nên nối chuỗi bằng `||` có thể khiến **toàn bộ câu SQL thành NULL**.

`quote_nullable(NULL)` tạo text `NULL`, phù hợp hơn khi thật sự cần dựng literal động.

`format('%L', value)` thuận tiện hơn nhiều trường hợp nối chuỗi thủ công.

## 17. USING placeholders và kiểu dữ liệu

Một câu SQL động:

```sql
DO $$
DECLARE
    v_count BIGINT;
BEGIN
    EXECUTE
        'SELECT count(*)
           FROM lesson_dynamic_sql.orders
          WHERE tenant_id = $1
            AND amount >= $2'
    INTO v_count
    USING 10::bigint, 200000::numeric;

    RAISE NOTICE 'Matches: %', v_count;
END;
$$;
```

`USING` truyền **giá trị có kiểu**, PostgreSQL không phải nhúng chúng thành các đoạn string SQL để parse lại.

### Thứ tự

`$1` ứng với biểu thức thứ nhất ở `USING`, `$2` là biểu thức thứ hai. Nếu đảo thứ tự, bạn có thể gặp lỗi ép kiểu hoặc truy vấn trả kết quả sai.

### Có thể dùng cùng placeholder nhiều lần

```sql
EXECUTE
    'SELECT count(*)
       FROM lesson_dynamic_sql.orders
      WHERE tenant_id = $1
        AND (customer_id = $2 OR order_id = $2)'
INTO v_count
USING 10::bigint, 101::bigint;
```

Các vị trí dùng lại `$2` cùng tham chiếu một bound value. Nhưng logic kiểm tra ở ví dụ chỉ mang tính minh họa; không nên ghép điều kiện khó hiểu nếu có query tĩnh rõ ràng hơn.

## 18. USING tránh lỗi nháy đơn và SQL injection

Giả sử input text:

```text
O'Reilly
```

Nếu code tự ghép:

```sql
v_sql := 'SELECT ... WHERE customer_name = '''
         || p_name || '''';
```

dấu nháy trong `O'Reilly` sẽ làm vỡ SQL literal, thậm chí có thể mở cơ hội SQL injection nếu input cố ý được tạo để thay đổi cú pháp.

Thay vào đó:

```sql
v_sql := 'SELECT count(*)
          FROM some_allowed_table
          WHERE customer_name = $1';

EXECUTE v_sql INTO v_count USING p_name;
```

Đoạn cuối là mẫu minh họa về bảng có cột customer_name; không chạy nguyên văn nếu database lab không có bảng đó.

### Một hiểu nhầm

`USING` bảo vệ **giá trị**, nhưng nếu bạn vẫn nối trực tiếp một `p_table_name` hoặc `p_sort_expression` vào SQL string thì câu lệnh vẫn có thể bị thay đổi. Phải bảo vệ cả **cấu trúc**.

## 19. Có thể dùng USING với những lệnh nào?

Bound parameter symbols của `EXECUTE ... USING` được hỗ trợ tại các vị trí **giá trị dữ liệu** trong các lệnh tối ưu hóa như `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `MERGE` và một số câu lệnh chứa chúng theo quy tắc PostgreSQL.

Các **utility statements** như phần lớn DDL không hỗ trợ thay schema/table/column bằng `$1`.

Ví dụ sai:

```sql
-- Sai: $1 không trở thành tên bảng:
-- EXECUTE 'ALTER TABLE $1 ADD COLUMN notes text'
-- USING p_table_name;
```

Cách đúng phải tạo identifier trong SQL string bằng `%I`:

```sql
EXECUTE format(
    'ALTER TABLE %I.%I ADD COLUMN IF NOT EXISTS %I text',
    'lesson_dynamic_sql',
    p_table_name,
    'notes'
);
```

**Nhưng** đối tượng cần được allowlist và caller phải có DDL privileges thích hợp. Quote an toàn không thay authorization hay việc đánh giá lock/downtime.

## 20. EXECUTE và SELECT INTO: hai chỗ đặt INTO

Trong PL/pgSQL, câu SELECT tĩnh có thể:

```sql
SELECT amount
INTO v_amount
FROM lesson_dynamic_sql.orders
WHERE order_id = p_order_id;
```

Với EXECUTE, vị trí đúng:

```sql
EXECUTE
    'SELECT amount
       FROM lesson_dynamic_sql.orders
      WHERE order_id = $1'
INTO v_amount
USING p_order_id;
```

**Đừng viết `SELECT ... INTO v_amount` bên trong dynamic command string** để mong PL/pgSQL bắt nó thành biến. Trong SQL cấp server, `SELECT INTO` có nghĩa tạo bảng mới trong một số ngữ cảnh, khác với `SELECT ... INTO` của PL/pgSQL.

Cách nhận một hàng qua dynamic SQL là đặt `INTO target` **bên ngoài chuỗi**, thuộc cú pháp `EXECUTE`.

## 21. Trả về một giá trị bằng EXECUTE INTO

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.count_by_status(
    p_tenant_id BIGINT,
    p_status TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_count BIGINT;
BEGIN
    EXECUTE
        'SELECT count(*)
           FROM lesson_dynamic_sql.orders
          WHERE tenant_id = $1
            AND status = $2'
    INTO v_count
    USING p_tenant_id, p_status;

    RETURN v_count;
END;
$$;

SELECT lesson_dynamic_sql.count_by_status(10, 'PAID');
-- 2
```

Đây là một ví dụ đúng cú pháp `EXECUTE` và `USING`, nhưng **không phải lý do tốt để dùng SQL động**: tên bảng/cột đều cố định. Bản tĩnh thường gọn hơn và giúp PL/pgSQL quản lý plan caching.

Việc một đoạn code chạy được không chứng minh nó là kiến trúc phù hợp.

## 22. Truy vấn không trả hàng với INTO

`EXECUTE ... INTO target` không có `STRICT`:

- Nếu query trả ít nhất một hàng, PostgreSQL lấy **hàng đầu tiên** vào target.
- Nếu query không trả hàng, target nhận các giá trị SQL NULL tương ứng.
- Nếu query trả nhiều hàng, các hàng còn lại không được gán vào target.

Ví dụ:

```sql
DO $$
DECLARE
    v_amount NUMERIC;
BEGIN
    EXECUTE
        'SELECT amount
           FROM lesson_dynamic_sql.orders
          WHERE order_id = $1'
    INTO v_amount
    USING -1::bigint;

    RAISE NOTICE 'Amount: %', v_amount;
END;
$$;
```

Ở lab, order_id = -1 không tồn tại nên `v_amount` là NULL.

### Nếu có nhiều hàng

Không viết SELECT không có `ORDER BY` rồi tin “hàng đầu tiên” luôn là một bản ghi cụ thể. SQL không bảo đảm thứ tự nếu không có điều kiện sắp xếp hợp lệ.

## 23. INTO STRICT: đòi đúng một hàng

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.find_order_amount(
    p_order_id BIGINT
)
RETURNS NUMERIC
LANGUAGE plpgsql
AS $$
DECLARE
    v_amount NUMERIC;
BEGIN
    EXECUTE
        'SELECT amount
           FROM lesson_dynamic_sql.orders
          WHERE order_id = $1'
    INTO STRICT v_amount
    USING p_order_id;

    RETURN v_amount;
END;
$$;
```

Với `INTO STRICT`:

- **0 rows** → exception `NO_DATA_FOUND` (SQLSTATE thường `P0002`).
- **1 row** → gán đúng dữ liệu.
- **Nhiều hơn 1 row** → exception `TOO_MANY_ROWS` (SQLSTATE thường `P0003`).

### Khi nào nên STRICT?

Khi hợp đồng API yêu cầu **đúng một hàng**. Ví dụ lookup theo primary key với business assumption bản ghi phải tồn tại.

Với query `count(*)`, kết quả aggregate luôn gồm một hàng ngay cả khi không có bản ghi nguồn, nên `STRICT` không giúp phát hiện “không tìm thấy đơn”; cần phân biệt giá trị count=0 với số hàng aggregate.

## 24. Bắt lỗi STRICT có chọn lọc

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.find_order_amount_or_null(
    p_order_id BIGINT
)
RETURNS NUMERIC
LANGUAGE plpgsql
AS $$
DECLARE
    v_amount NUMERIC;
BEGIN
    BEGIN
        EXECUTE
            'SELECT amount
               FROM lesson_dynamic_sql.orders
              WHERE order_id = $1'
        INTO STRICT v_amount
        USING p_order_id;

        RETURN v_amount;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RETURN NULL;
    END;
END;
$$;
```

Lỗi nhiều rows vẫn phát sinh, không được âm thầm chuyển thành NULL. Đây là lựa chọn hợp đồng: “không tồn tại” được xem là kết quả hợp lệ; “nhiều kết quả” là vi phạm.

### Không bắt WHEN OTHERS rồi giả làm dữ liệu không có

Nếu tất cả exceptions đều bị thay bằng NULL/0, ứng dụng có thể che lỗi quyền, tên bảng, schema drift hoặc truy vấn không hợp lệ. Catch những loại lỗi có semantics cụ thể, ghi log an toàn và để phần còn lại được xử lý ở transaction boundary.

## 25. EXECUTE có thay đổi FOUND không?

Một chi tiết PL/pgSQL dễ sai: **`EXECUTE` không thay đổi biến đặc biệt `FOUND`** theo cách mà nhiều câu SQL tĩnh trong PL/pgSQL làm.

Vì thế không nên viết:

```sql
EXECUTE v_sql USING p_value;
IF FOUND THEN
    -- Không bảo đảm đây là trạng thái từ EXECUTE vừa chạy.
END IF;
```

Thay vào đó, sau dynamic DML, dùng `GET DIAGNOSTICS ... ROW_COUNT`; với `EXECUTE ... INTO`, dùng `INTO STRICT` hoặc kiểm tra kết quả/semantics theo yêu cầu.

## 26. GET DIAGNOSTICS ROW_COUNT sau EXECUTE

Ví dụ UPDATE theo tenant:

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.cancel_new_orders(
    p_tenant_id BIGINT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_affected BIGINT;
BEGIN
    EXECUTE
        'UPDATE lesson_dynamic_sql.orders
            SET status = $1
          WHERE tenant_id = $2
            AND status = $3'
    USING 'CANCELLED', p_tenant_id, 'NEW';

    GET DIAGNOSTICS v_affected = ROW_COUNT;
    RETURN v_affected;
END;
$$;
```

Gọi trong transaction lab:

```sql
BEGIN;

SELECT lesson_dynamic_sql.cancel_new_orders(10);

SELECT status, count(*)
FROM lesson_dynamic_sql.orders
WHERE tenant_id = 10
GROUP BY status;

ROLLBACK;
```

### Vì sao rollback?

Để bài lab không làm thay đổi dữ liệu cho các ví dụ phía sau. Function có dynamic UPDATE thực hiện thay đổi transactional; `ROLLBACK` hoàn nguyên dữ liệu.

`ROW_COUNT` là số hàng được xử lý bởi câu SQL gần nhất theo cơ chế `GET DIAGNOSTICS`. Hãy đọc nó **ngay sau EXECUTE**; câu SQL khác chạy ở giữa có thể thay đổi thông tin diagnostic.

## 27. EXECUTE với INSERT và RETURNING

Ví dụ chèn một đơn hàng rồi lấy ID:

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.insert_order_dynamic(
    p_tenant_id BIGINT,
    p_customer_id BIGINT,
    p_amount NUMERIC
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_order_id BIGINT;
BEGIN
    IF p_amount IS NULL OR p_amount < 0 THEN
        RAISE EXCEPTION 'Amount must be nonnegative';
    END IF;

    EXECUTE
        'INSERT INTO lesson_dynamic_sql.orders
             (tenant_id, customer_id, status, amount)
         VALUES ($1, $2, $3, $4)
         RETURNING order_id'
    INTO v_order_id
    USING p_tenant_id, p_customer_id, 'NEW', p_amount;

    RETURN v_order_id;
END;
$$;

BEGIN;
SELECT lesson_dynamic_sql.insert_order_dynamic(
    10, 104, 75000.00
);
ROLLBACK;
```

Vì SQL command là `INSERT ... RETURNING`, output có thể được nhận bằng `EXECUTE ... INTO`.

### Lưu ý RETURNING nhiều hàng

Các câu DML có `RETURNING` mà đưa ra nhiều rows nhưng lại cố gán vào **một target** là trường hợp cần xử lý cẩn thận; PL/pgSQL có thể báo lỗi khi `INSERT/UPDATE/DELETE/MERGE ... RETURNING` trả nhiều hàng cho một `INTO`, kể cả không ghi `STRICT`. Nếu cần tất cả rows, sử dụng `RETURN QUERY EXECUTE` hoặc một thiết kế khác có xử lý tập.

## 28. Dynamic DELETE có điều kiện

```sql
DO $$
DECLARE
    v_deleted BIGINT;
BEGIN
    EXECUTE
        'DELETE FROM lesson_dynamic_sql.orders
          WHERE tenant_id = $1
            AND status = $2'
    USING 10::bigint, 'CANCELLED'::text;

    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RAISE NOTICE 'Deleted rows: %', v_deleted;
END;
$$;
```

**Cảnh báo:** Block này xóa dữ liệu thật trong transaction đang chạy. Nếu chỉ muốn thử:

```sql
BEGIN;
-- Chạy DO block phía trên ở đây.
ROLLBACK;
```

Trong thực tế, xóa dữ liệu phải có chính sách retention, quyền, audit và transaction phù hợp. `USING` không ngăn được một `DELETE` thiếu WHERE hoặc một điều kiện quá rộng do người viết SQL mắc lỗi.

## 29. Dynamic MERGE với dữ liệu đầu vào

Ở các phiên bản PostgreSQL hỗ trợ `MERGE`, câu lệnh tối ưu hóa này có thể sử dụng bound values trong vị trí phù hợp theo cơ chế `EXECUTE ... USING`.

Ý tưởng:

```text
MERGE INTO target
USING (SELECT $1 AS id, $2 AS status) source
ON target.id = source.id
WHEN MATCHED THEN UPDATE...
WHEN NOT MATCHED THEN INSERT...
```

Trên các phiên bản hoặc trường hợp không hỗ trợ `MERGE`, dùng `INSERT ... ON CONFLICT` phù hợp. Đừng ghép values thủ công chỉ vì câu lệnh phức tạp; dùng parameters và kiểm tra semantics isolation/concurrency.

Ví dụ `MERGE` sẽ chỉ nên được viết khi đã xác nhận phiên bản PostgreSQL và hình dạng bảng thực; các ví dụ chính trong bài dùng SELECT/INSERT/UPDATE/DELETE có thể chạy độc lập.

## 30. RETURN QUERY EXECUTE: trả nhiều hàng

Một `EXECUTE ... INTO` thường lấy một hàng. Với function trả tập:

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.orders_for_tenant(
    p_tenant_id BIGINT,
    p_status TEXT
)
RETURNS TABLE (
    order_id BIGINT,
    amount NUMERIC,
    created_at TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_sql TEXT;
BEGIN
    v_sql :=
        'SELECT o.order_id, o.amount, o.created_at
           FROM lesson_dynamic_sql.orders AS o
          WHERE o.tenant_id = $1
            AND o.status = $2
          ORDER BY o.created_at DESC, o.order_id DESC';

    RETURN QUERY EXECUTE v_sql
    USING p_tenant_id, p_status;
END;
$$;

SELECT *
FROM lesson_dynamic_sql.orders_for_tenant(10, 'PAID');
```

### Những điểm cần khớp

- `RETURNS TABLE` khai báo **cột và kiểu kết quả**.
- Dynamic SELECT trả đúng **ba cột**, theo đúng thứ tự và kiểu tương thích.
- `RETURN QUERY EXECUTE` bổ sung các hàng vào kết quả function.
- Khi không có hàng match, tập kết quả có thể rỗng.

`RETURN QUERY EXECUTE` hữu ích khi **cấu trúc nguồn** thay đổi nhưng hình dạng output vẫn là một contract cố định. Nếu output columns cũng thay đổi tùy input, ứng dụng SQL/JDBC sẽ khó biết cấu trúc nhận; cần một API khác hoặc kiểu `record` kèm khai báo khi gọi.

## 31. Vì sao SELECT thường đủ thay vì RETURN QUERY EXECUTE?

Hàm `orders_for_tenant` vừa viết có cấu trúc SQL hoàn toàn cố định. Có thể đơn giản hóa bằng một `LANGUAGE sql` function hoặc `RETURN QUERY SELECT ...` tĩnh:

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.orders_for_tenant_static(
    p_tenant_id BIGINT,
    p_status TEXT
)
RETURNS TABLE (
    order_id BIGINT,
    amount NUMERIC,
    created_at TIMESTAMPTZ
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT
        o.order_id,
        o.amount,
        o.created_at
    FROM lesson_dynamic_sql.orders AS o
    WHERE o.tenant_id = p_tenant_id
      AND o.status = p_status
    ORDER BY o.created_at DESC, o.order_id DESC;
END;
$$;
```

### Khác biệt

- `RETURN QUERY SELECT`: câu query tĩnh, rõ dependencies, plan được quản lý theo cơ chế PL/pgSQL.
- `RETURN QUERY EXECUTE`: chuỗi query tạo lúc chạy và lập kế hoạch mỗi lần.

Nếu không có lý do thay đổi SQL structure, không cần `EXECUTE`.

## 32. FOR ... IN EXECUTE: duyệt từng hàng

PL/pgSQL cho phép chạy truy vấn động rồi lặp qua các hàng:

```sql
DO $$
DECLARE
    v_order RECORD;
    v_tenant_id BIGINT := 10;
BEGIN
    FOR v_order IN EXECUTE
        'SELECT order_id, status, amount
           FROM lesson_dynamic_sql.orders
          WHERE tenant_id = $1
          ORDER BY order_id'
        USING v_tenant_id
    LOOP
        RAISE NOTICE 'Order %, status %, amount %',
            v_order.order_id,
            v_order.status,
            v_order.amount;
    END LOOP;
END;
$$;
```

### Khi nào dùng?

- Xử lý các bản ghi được chọn động bằng tên bảng/cột hợp lệ.
- Thực hiện logic PL/pgSQL theo từng hàng khi SQL thuần không diễn tả đơn giản.
- Xử lý tác vụ bảo trì nhỏ, có logging và validation.

Nhưng vòng lặp theo từng hàng không phải cách mặc định để cập nhật hàng trăm nghìn records. SQL set-based `UPDATE ... WHERE ...` thường giảm overhead và dễ tận dụng executor.

## 33. FOR ... IN EXECUTE và FOUND

Vòng lặp `FOR ... IN EXECUTE` xử lý các hàng từ query. Sau khi vòng lặp kết thúc, `FOUND` có semantics của vòng lặp, khác câu `EXECUTE` đơn lẻ.

```sql
DO $$
DECLARE
    v_row RECORD;
BEGIN
    FOR v_row IN EXECUTE
        'SELECT order_id
           FROM lesson_dynamic_sql.orders
          WHERE tenant_id = $1'
        USING -1::bigint
    LOOP
        NULL; -- Không có hàng trong lab.
    END LOOP;

    RAISE NOTICE 'Loop produced rows: %', FOUND;
END;
$$;
```

Ở ví dụ này, vòng lặp không chạy nên `FOUND` thường là false sau vòng lặp.

### So với EXECUTE INTO

Đừng suy diễn quy tắc này sang `EXECUTE ... INTO`: **câu EXECUTE tự nó không thay đổi FOUND**, nên cách xác nhận kết quả nên dùng `STRICT`, giá trị output hoặc diagnostics phù hợp.

## 34. FOR record IN EXECUTE hay dùng RETURN QUERY EXECUTE?

| Mục tiêu | Cách phù hợp |
|---|---|
| Trả toàn bộ tập kết quả cho caller | `RETURN QUERY EXECUTE` |
| Cần xử lý từng hàng bằng PL/pgSQL | `FOR record IN EXECUTE ... LOOP` |
| Lấy một giá trị | `EXECUTE ... INTO` |
| Thực thi dynamic UPDATE và lấy số hàng | `EXECUTE ... USING` + `GET DIAGNOSTICS ROW_COUNT` |
| Thực thi DDL | `EXECUTE format(...)` |

Nếu có thể viết một câu SELECT/UPDATE set-based thay cho loop, nên ưu tiên nó trừ khi yêu cầu thật sự là xử lý tuần tự.

### Khi dùng loop để thay đổi database

Cần nghĩ về transaction size, lock duration, exception behavior và partial work khi lỗi. Một vòng lặp bên trong function không tạo transaction riêng cho từng hàng.

## 35. Record và target có hình dạng động

`RECORD` trong PL/pgSQL có thể nhận một hàng với cấu trúc được xác định lúc chạy:

```sql
DO $$
DECLARE
    v_row RECORD;
BEGIN
    EXECUTE
        'SELECT order_id, status, amount
           FROM lesson_dynamic_sql.orders
          ORDER BY order_id
          LIMIT 1'
    INTO v_row;

    RAISE NOTICE 'Order = %, amount = %',
        v_row.order_id,
        v_row.amount;
END;
$$;
```

### Ưu điểm

Record linh hoạt khi column list thay đổi. Nhưng một API trả cấu trúc không ổn định sẽ khó gọi từ Java hoặc SQL queries khác.

### Rủi ro

Nếu dynamic query không trả cột `amount`, truy cập `v_row.amount` có thể lỗi lúc chạy. PL/pgSQL không thể kiểm tra đầy đủ mọi tên field của `RECORD` ngay lúc tạo function.

Khi giao diện trả cho ứng dụng có hình dạng cố định, nên dùng biến typed hoặc `RETURNS TABLE` với alias/casts rõ ràng.

## 36. Dynamic ORDER BY: vì sao cần đặc biệt cẩn thận

Một màn hình danh sách đơn hàng cho phép:

- Sort theo `created_at`, `amount` hoặc `order_id`.
- Chọn `ASC` hoặc `DESC`.
- Có giới hạn số rows và tenant scope.

Sai:

```sql
v_sql := 'SELECT ... ORDER BY ' ||
         p_sort_column || ' ' || p_direction;
```

Nếu input do client điều khiển, đây là **SQL fragment injection**. `USING` không thể bind tên cột hoặc keyword `ASC/DESC`; phải **map input về tập giá trị được cho phép**.

## 37. Xây dynamic ORDER BY an toàn

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.search_orders(
    p_tenant_id BIGINT,
    p_sort_column TEXT DEFAULT 'created_at',
    p_direction TEXT DEFAULT 'DESC',
    p_limit INTEGER DEFAULT 20
)
RETURNS TABLE (
    order_id BIGINT,
    amount NUMERIC,
    created_at TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_column TEXT;
    v_direction TEXT;
    v_sql TEXT;
BEGIN
    v_column := CASE p_sort_column
        WHEN 'amount' THEN 'amount'
        WHEN 'created_at' THEN 'created_at'
        WHEN 'order_id' THEN 'order_id'
        ELSE NULL
    END;

    IF v_column IS NULL THEN
        RAISE EXCEPTION 'Unsupported sort column: %',
            p_sort_column;
    END IF;

    IF p_direction IS NULL
       OR upper(p_direction) NOT IN ('ASC', 'DESC') THEN
        RAISE EXCEPTION 'Unsupported sort direction';
    END IF;
    v_direction := upper(p_direction);

    IF p_limit IS NULL OR p_limit < 1 OR p_limit > 100 THEN
        RAISE EXCEPTION 'Limit must be between 1 and 100';
    END IF;

    v_sql := format(
        'SELECT o.order_id, o.amount, o.created_at
           FROM lesson_dynamic_sql.orders AS o
          WHERE o.tenant_id = $1
          ORDER BY o.%I %s, o.order_id DESC
          LIMIT $2',
        v_column,
        v_direction
    );

    RETURN QUERY EXECUTE v_sql
    USING p_tenant_id, p_limit;
END;
$$;
```

### Chỗ nào được kiểm soát?

- Cột sắp xếp: `CASE` whitelist, sau đó `%I`.
- Hướng: whitelist `ASC/DESC`, sau đó `%s`.
- Tenant: bound `$1` từ `USING`.
- Limit: bound `$2` và giới hạn 1–100.
- Tên bảng: cố định bằng schema-qualified name.

`ORDER BY ... order_id DESC` cung cấp tie-breaker khi cột sort đầu tiên có giá trị trùng, giúp thứ tự ổn định hơn.

## 38. Gọi search_orders theo nhiều thứ tự

```sql
-- Mặc định: created_at DESC
SELECT *
FROM lesson_dynamic_sql.search_orders(10);

-- Giá tăng dần
SELECT *
FROM lesson_dynamic_sql.search_orders(
    10,
    'amount',
    'ASC',
    10
);

-- ID giảm dần
SELECT *
FROM lesson_dynamic_sql.search_orders(
    p_tenant_id => 10,
    p_sort_column => 'order_id',
    p_direction => 'DESC'
);
```

### Những input phải bị từ chối

```sql
-- Không cho phép tên cột không trong danh sách:
-- SELECT * FROM lesson_dynamic_sql.search_orders(
--     10, 'customer_id', 'ASC', 10
-- );

-- Không cho phép SQL fragment do client cung cấp:
-- SELECT * FROM lesson_dynamic_sql.search_orders(
--     10, 'amount', 'DESC NULLS LAST', 10
-- );
```

Không chuyển các lỗi này thành “thử lại bằng nối chuỗi”; hãy mở rộng whitelist hoặc thêm một sort mode mới với semantics đã thiết kế.

## 39. Vì sao không dùng ORDER BY $1?

Một lỗi thường gặp:

```sql
EXECUTE
    'SELECT order_id, amount
       FROM lesson_dynamic_sql.orders
      ORDER BY $1'
USING p_sort_column;
```

`$1` là một **giá trị text cố định trong mỗi hàng**, không phải tham chiếu động tới cột tên `p_sort_column`. Sắp xếp theo một constant value không tạo được thứ tự như mong muốn.

Tên cột là **identifier**, nên phải dùng `%I` và chỉ nhận lựa chọn từ whitelist. Không dùng `USING` để cố thay identifier.

## 40. CASE trong ORDER BY có thể thay SQL động

Nếu chỉ có hai lựa chọn sắp xếp, đôi khi query tĩnh đủ:

```sql
SELECT order_id, amount, created_at
FROM lesson_dynamic_sql.orders
WHERE tenant_id = 10
ORDER BY
    CASE WHEN 'amount' = 'amount' THEN amount END ASC,
    order_id DESC;
```

Ví dụ trên minh họa một nhánh sort cố định; trong function có thể thay `'amount'` đầu tiên bằng tham số. Nhưng nếu các cột có kiểu khác nhau (numeric và timestamptz), một `CASE` duy nhất không thể tùy tiện trả các kiểu không tương thích, nên thường cần các expression/branches riêng.

### Khi nào chọn cách tĩnh?

- Có ít biến thể và SQL ngắn.
- Muốn tránh tái lập kế hoạch do EXECUTE.
- Không cần cấu trúc SELECT khác.
- Có thể kiểm soát ORDER BY rõ ràng.

### Khi nào dynamic tốt hơn?

- Có nhiều biến thể cột/hướng với whitelist rõ.
- SQL tĩnh dùng CASE phức tạp, khó đọc hoặc ảnh hưởng index plan.
- Planner cần một biểu thức ORDER BY cụ thể để cân nhắc index/sort.

Phải kiểm tra `EXPLAIN` với dữ liệu thật, không kết luận chỉ từ độ ngắn của code.

## 41. Sử dụng whitelist cho tên bảng

Một API tùy chọn đọc dữ liệu hiện tại hoặc dữ liệu archive:

```text
source = 'current' → lesson_dynamic_sql.orders
source = 'archive' → lesson_dynamic_sql.orders_archive
```

Nếu archive chưa được tạo, không nên để function chạy bừa. Một mapping có kiểm soát:

```sql
v_table_name := CASE p_source
    WHEN 'current' THEN 'orders'
    WHEN 'archive' THEN 'orders_archive'
    ELSE NULL
END;

IF v_table_name IS NULL THEN
    RAISE EXCEPTION 'Unsupported source';
END IF;
```

Rồi:

```sql
v_sql := format(
    'SELECT count(*) FROM %I.%I WHERE tenant_id = $1',
    'lesson_dynamic_sql',
    v_table_name
);
```

**Whitelist giới hạn tập bảng có thể được truy cập**, còn `%I` bảo đảm tên được quote đúng. Cả hai giải quyết những vấn đề khác nhau.

## 42. Schema name, table name và case sensitivity

PostgreSQL folds unquoted identifiers về lowercase theo quy tắc của nó:

```sql
SELECT format('%I.%I', 'lesson_dynamic_sql', 'orders');
```

không cần dấu nháy cho tên đơn giản.

Với tên có chữ hoa hoặc khoảng trắng:

```sql
SELECT format('%I.%I', 'Sales Data', 'Order Detail');
```

kết quả có quotes cho từng identifier.

### Vì sao không tự lowercase mọi input?

Nếu database đã có tên quoted với chữ hoa, việc lower-case thay đổi định danh. Tốt nhất là dùng naming conventions nhất quán và lấy tên object từ metadata/whitelist đáng tin, thay vì chấp nhận mọi kiểu đặt tên do người dùng nhập vào.

## 43. Dùng regclass khi có lý do

PostgreSQL có kiểu `regclass` để biểu diễn OID của relation. Một giá trị `regclass` được resolve theo cơ chế tên đối tượng và có cách hiển thị an toàn cho SQL:

```sql
SELECT 'lesson_dynamic_sql.orders'::regclass;
```

Trong một số thủ tục bảo trì tin cậy, truyền tham số `p_relation regclass` có thể rõ hơn truyền tên bảng text tùy ý.

### Nhưng regclass không tự phân quyền

Một `regclass` cho biết một relation được resolve, **không chứng minh caller được quyền đọc/sửa nó**. Routine `SECURITY DEFINER` nhận regclass tùy ý vẫn có thể gây confused-deputy nếu dùng quyền owner trên object không được phép.

Nếu dựng câu SQL từ `regclass`, vẫn phải đánh giá:

- Schema chứa relation.
- Loại relation (table/view/partition...).
- ACL/ownership.
- Tập đối tượng cho phép.
- Quoting và resolution theo search_path.

Không dùng regclass như một “lá chắn bảo mật” thay allowlist.

## 44. Dynamic DDL với format('%I')

Một migration tool hoặc admin routine đôi khi cần thêm một cột tên thay đổi theo cấu hình:

```sql
CREATE OR REPLACE PROCEDURE lesson_dynamic_sql.add_notes_column(
    p_table_name TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_table_name IS DISTINCT FROM 'orders' THEN
        RAISE EXCEPTION 'Only orders table is allowed';
    END IF;

    EXECUTE format(
        'ALTER TABLE %I.%I ADD COLUMN IF NOT EXISTS %I text',
        'lesson_dynamic_sql',
        p_table_name,
        'notes'
    );
END;
$$;
```

Gọi:

```sql
-- Chỉ chạy nếu chủ ý thay schema của bảng lab:
-- CALL lesson_dynamic_sql.add_notes_column('orders');
```

### Vì sao không dùng USING cho tên cột?

DDL cần identifiers trong cú pháp SQL; bound parameters không thay thế được. Dùng `%I` cho từng tên và whitelist những tên/mode được phép.

### Cảnh báo production

`ALTER TABLE` có thể cần locks và tác động hiệu năng. Một procedure DDL không tự làm migration “online” hoặc không downtime. Cần kế hoạch concurrency/deploy/rollback.

## 45. Dynamic CREATE INDEX

Đôi khi một công cụ bảo trì tạo index trên cột được chỉ định. Cú pháp mẫu:

```sql
DO $$
DECLARE
    v_index_name TEXT := 'ix_orders_amount_lab';
    v_table_name TEXT := 'orders';
    v_column_name TEXT := 'amount';
BEGIN
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS %I ON %I.%I (%I)',
        v_index_name,
        'lesson_dynamic_sql',
        v_table_name,
        v_column_name
    );
END;
$$;
```

Vì tên bảng/cột trong ví dụ là constants do code sở hữu, `%I` giúp dựng cú pháp hợp lệ. Nếu chúng đến từ input, cần whitelist và kiểm tra quyền/loại bảng.

### Không dùng CREATE INDEX CONCURRENTLY trong DO/function

`CREATE INDEX CONCURRENTLY` không thể chạy trong transaction block; khối PL/pgSQL `DO`/function không phải nơi phù hợp để thực thi nó. Công cụ migration bên ngoài có thể gửi `CREATE INDEX CONCURRENTLY` như câu SQL top-level trong điều kiện phù hợp.

Trước khi tạo index trên production, hãy kiểm tra index đã có, write overhead, thời gian xây dựng, locks và disk/WAL.

## 46. Dynamic DDL và định kiểu cột

Giả sử một công cụ muốn tạo cột mới với kiểu được người dùng chỉ định:

```text
type = text
type = numeric
type = timestamptz
```

Không nối trực tiếp raw string thành:

```sql
format('ALTER TABLE ... ADD COLUMN data %s', p_type)
```

trừ khi `p_type` đã được **map sang một biểu thức type hợp lệ từ whitelist**.

Ví dụ:

```sql
v_type_sql := CASE p_type
    WHEN 'text' THEN 'text'
    WHEN 'money' THEN 'numeric(14,2)'
    WHEN 'timestamp' THEN 'timestamptz'
    ELSE NULL
END;

IF v_type_sql IS NULL THEN
    RAISE EXCEPTION 'Unsupported type';
END IF;
```

Sau đó `%s` chỉ chèn một **constant SQL type fragment do code sở hữu**, không nhận raw user input.

### Nguyên tắc chung

Keywords, operators, data types, ORDER BY directions và cấu trúc expression cần được chọn từ **một ngôn ngữ đầu vào được kiểm soát**, không thể chỉ quote mọi thứ với `%I` rồi nghĩ SQL luôn đúng.

## 47. DDL và giá trị literal

Đối với một utility statement cần một giá trị hằng trong SQL text, `USING` có thể không áp dụng được; dùng `%L`/`quote_nullable` khi thật sự cần.

Ví dụ tạo comment cho một bảng được phép:

```sql
DO $$
DECLARE
    v_comment TEXT := 'Dữ liệu lab: O''Reilly examples';
BEGIN
    EXECUTE format(
        'COMMENT ON TABLE %I.%I IS %L',
        'lesson_dynamic_sql',
        'orders',
        v_comment
    );
END;
$$;
```

`COMMENT ON TABLE` là utility statement, nên tên bảng là `%I.%I`, phần comment là **SQL literal đã quote** bằng `%L`.

### Vì sao không dùng %s cho comment?

Nếu chèn text comment thô, dấu nháy/punctuation có thể làm sai SQL. `%L` tạo literal theo quoting rules. Trong các câu SELECT/DML tối ưu hóa, khi value có thể bind, hãy dùng `USING` thay vì `%L`.

## 48. Dynamic CREATE TABLE theo chính sách đặt tên

Một tác vụ lưu trữ dữ liệu hàng tháng có thể tạo bảng đích có tên theo kỳ:

```text
orders_2026_10
orders_2026_11
orders_2026_12
```

Không lấy `p_table_name` raw bất kỳ từ client. Xây tên từ giá trị **đã được kiểm tra** như năm/tháng rồi dùng `%I`:

```sql
CREATE OR REPLACE PROCEDURE lesson_dynamic_sql.create_monthly_stage(
    p_year INTEGER,
    p_month INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_table_name TEXT;
BEGIN
    IF p_year IS NULL OR p_year < 2000 OR p_year > 2100
       OR p_month IS NULL OR p_month < 1 OR p_month > 12 THEN
        RAISE EXCEPTION 'Invalid year/month';
    END IF;

    v_table_name := format(
        'orders_stage_%s_%s',
        p_year,
        lpad(p_month::text, 2, '0')
    );

    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I.%I (
             stage_id bigint PRIMARY KEY,
             tenant_id bigint NOT NULL,
             amount numeric(14,2) NOT NULL
         )',
        'lesson_dynamic_sql',
        v_table_name
    );
END;
$$;
```

Đây là minh họa về tên bảng an toàn, **không phải một hệ thống partitioning hoàn chỉnh**. Nếu cần partitioning thực, dùng `PARTITION BY`, `ATTACH PARTITION`, bounds, constraints và automation theo tài liệu PostgreSQL; đừng tạo vô hạn bảng thông thường mà không có chính sách retention.

## 49. Dynamic SQL và multi-tenant database

Hai kiến trúc phổ biến:

**Shared table:**

```text
orders(tenant_id, order_id, ...)
```

Đây thường là trường hợp **không cần** table-name dynamic; truy vấn tĩnh theo `tenant_id` và RLS/index phù hợp.

**Schema per tenant:**

```text
tenant_a.orders
tenant_b.orders
```

Lúc này tên schema có thể biến thiên. Tuy nhiên, một function nhận `p_schema` từ client rồi `format('%I.orders',p_schema)` chưa tự có authorization.

### Thiết kế an toàn hơn

- Mapping tenant đã xác thực sang schema trong registry đáng tin.
- Whitelist hoặc lookup schema owner/metadata.
- SQL dùng `%I` để quote schema.
- Role permissions/RLS phù hợp.
- Audit các truy vấn đặc quyền.
- Không dựa hoàn toàn vào tên schema để chống truy cập chéo tenant.

Nếu toàn bộ dữ liệu nằm ở một bảng chung, dynamic schema nhiều khi chỉ tăng độ phức tạp và nguy cơ bảo mật.

## 50. SECURITY INVOKER và SECURITY DEFINER

Mặc định routine dùng cơ chế **`SECURITY INVOKER`**: quyền thực thi thao tác dữ liệu được kiểm tra theo caller trong các điều kiện tương ứng.

**`SECURITY DEFINER`** chạy với quyền của owner; đôi khi cần cho một API hạn chế nhưng đặc biệt nguy hiểm nếu routine dựng SQL động từ tên bảng/cột do người dùng chọn.

### Rủi ro confused deputy

Ví dụ nguy hiểm:

```sql
-- Anti-pattern minh họa; đừng tạo trong database:
-- CREATE FUNCTION privileged_count(table_name text)
-- RETURNS bigint SECURITY DEFINER AS $$
-- BEGIN
--   EXECUTE format('SELECT count(*) FROM %I', table_name);
-- END;
-- $$ LANGUAGE plpgsql;
```

Nếu owner có quyền với nhiều bảng, caller có thể thử dùng function như một con đường thao tác dữ liệu mà bình thường họ không có quyền.

### Cách thiết kế

- Chỉ dùng SECURITY DEFINER khi có lý do cụ thể.
- Giới hạn quyền owner.
- Validate/whitelist tên object và các thao tác được phép.
- Sử dụng schema-qualified names.
- Đặt `search_path` an toàn.
- Bảo vệ quyền `EXECUTE`.
- Kiểm tra những table owners có thể bypass RLS theo quy tắc PostgreSQL.

`%I` chống lỗi parsing/injection trong identifier, **không chống lạm dụng quyền của owner**.

## 51. search_path trong SECURITY DEFINER

Một ví dụ về cấu hình bảo vệ hơn:

```sql
-- Đây là mẫu cấu hình cho routine có đặc quyền;
-- chỉ áp dụng khi đã kiểm toán toàn bộ body:
-- CREATE FUNCTION admin.some_function(...)
-- RETURNS ...
-- LANGUAGE plpgsql
-- SECURITY DEFINER
-- SET search_path = pg_catalog, trusted_schema, pg_temp
-- AS $$ ... $$;
```

### Vì sao cần chú ý?

Tên đối tượng không được schema-qualify có thể resolve qua `search_path`. Nếu có schema không đáng tin trong path mà caller có thể tạo object, routine đặc quyền có nguy cơ gọi nhầm object do kẻ khác tạo.

Các nguyên tắc:

- Schema-qualify tables/functions quan trọng.
- Chỉ để schemas đáng tin trong search_path của SECURITY DEFINER.
- Xem vị trí `pg_temp` theo khuyến nghị an toàn phù hợp.
- Không cho untrusted roles CREATE vào schemas mà routine đặc quyền tin cậy.
- Hạn chế dynamic SQL chỉ tới tập đối tượng cần thiết.

### Quyền RLS

`SECURITY DEFINER` có thể thay đổi vai trò áp dụng RLS và owner có thể bypass theo cấu hình; đừng xem `WHERE tenant_id = $1` với tenant lấy từ client là kiểm soát quyền đầy đủ.

## 52. Dynamic SQL không làm thay đổi ranh giới transaction

`EXECUTE` chạy câu lệnh bên trong transaction hiện tại của function/procedure/caller.

```sql
BEGIN;

SELECT lesson_dynamic_sql.cancel_new_orders(10);

SELECT status, count(*)
FROM lesson_dynamic_sql.orders
WHERE tenant_id = 10
GROUP BY status;

ROLLBACK;
```

Các thay đổi DML dynamic được rollback theo transaction, giống SQL tĩnh.

### EXECUTE không phải một transaction độc lập

Việc thực thi một chuỗi SQL qua PL/pgSQL `EXECUTE` không tự tạo transaction riêng hay tự commit. PostgreSQL có các giới hạn transaction control trong functions/procedures; riêng `EXECUTE` không vượt qua chúng.

### DDL transactional

Nhiều lệnh DDL PostgreSQL cũng chịu transaction semantics, nhưng có ngoại lệ/điều kiện đặc biệt như `CREATE INDEX CONCURRENTLY`. Đừng giả định “mọi DDL đều rollback được trong mọi điều kiện” hoặc “mọi DDL cần autocommit”; kiểm tra từng loại.

## 53. Exception handling và rollback trong PL/pgSQL

`EXECUTE` có thể phát sinh:

- `undefined_table` nếu object không tồn tại.
- `undefined_column` nếu column không đúng.
- `insufficient_privilege` nếu role thiếu quyền.
- `syntax_error` nếu command string sai cú pháp.
- `unique_violation`, `check_violation`, `foreign_key_violation` khi DML sai dữ liệu.
- `deadlock_detected` hoặc serialization failures trong concurrency.

Ví dụ chỉ bắt lỗi không tìm thấy table:

```sql
DO $$
DECLARE
    v_count bigint;
BEGIN
    BEGIN
        EXECUTE
            'SELECT count(*) FROM lesson_dynamic_sql.nonexistent_table'
        INTO v_count;
    EXCEPTION
        WHEN undefined_table THEN
            RAISE NOTICE 'Table does not exist';
    END;
END;
$$;
```

### Đừng bắt mọi lỗi rồi tiếp tục mù quáng

Nếu dùng `WHEN OTHERS THEN RETURN 0`, bạn có thể biến lỗi bảo mật/DB outage thành “0 đơn hàng”, gây sai số liệu. Phân biệt business result bình thường và system failure.

Khối `EXCEPTION` dùng subtransaction theo cơ chế PL/pgSQL để hoàn nguyên các tác động của phần block bị lỗi trong phạm vi tương ứng; vẫn phải thiết kế transaction boundary và rollback policy rõ ràng ở application.

## 54. Lấy SQLSTATE, SQLERRM và diagnostics khi lỗi

```sql
DO $$
DECLARE
    v_state text;
    v_message text;
BEGIN
    BEGIN
        EXECUTE
            'SELECT * FROM lesson_dynamic_sql.table_does_not_exist';
    EXCEPTION
        WHEN OTHERS THEN
            GET STACKED DIAGNOSTICS
                v_state = RETURNED_SQLSTATE,
                v_message = MESSAGE_TEXT;

            RAISE NOTICE 'SQLSTATE = %, message = %',
                v_state, v_message;
    END;
END;
$$;
```

Đây là ví dụ minh họa đọc diagnostics; trong production không nên catch `OTHERS` chỉ để che lỗi. Có thể log có kiểm soát rồi `RAISE;` để đẩy exception lên caller nếu lỗi thực sự phải làm transaction fail.

### Phân biệt ROW_COUNT và GET STACKED DIAGNOSTICS

- `GET DIAGNOSTICS ... ROW_COUNT` lấy số hàng xử lý từ statement gần nhất.
- `GET STACKED DIAGNOSTICS` dùng trong exception handler để lấy thông tin lỗi đã được bắt.

Không dùng `ROW_COUNT` để đo số hàng “đáng lẽ tìm được” khi truy vấn không thực thi thành công.

## 55. Guard trước khi truy cập tên đối tượng

Nếu một admin utility cần kiểm tra bảng tồn tại:

```sql
SELECT to_regclass('lesson_dynamic_sql.orders');
-- regclass hoặc NULL nếu không resolve được
```

Trong PL/pgSQL:

```sql
DO $$
DECLARE
    v_table_name text := 'orders';
    v_relation regclass;
BEGIN
    IF v_table_name IS DISTINCT FROM 'orders' THEN
        RAISE EXCEPTION 'Unsupported table';
    END IF;

    v_relation := to_regclass(
        format('%I.%I', 'lesson_dynamic_sql', v_table_name)
    );

    IF v_relation IS NULL THEN
        RAISE EXCEPTION 'Required relation missing';
    END IF;

    RAISE NOTICE 'Resolved relation: %', v_relation;
END;
$$;
```

### Một giới hạn

Kiểm tra tồn tại rồi truy cập sau đó có thể chịu thay đổi schema đồng thời (TOCTOU). Quyền, locking và xử lý exceptions tại thời điểm thực thi vẫn cần thiết. `to_regclass` không thay authorization.

## 56. Đường dựng SQL có thể kiểm soát và debug

Khi query động dài, hãy giữ câu SQL trong một biến rõ ràng:

```sql
v_sql := format(
    'SELECT count(*)
       FROM %I.%I
      WHERE tenant_id = $1
        AND status = $2',
    'lesson_dynamic_sql',
    v_table_name
);

EXECUTE v_sql INTO v_count USING p_tenant_id, p_status;
```

Việc này giúp:

- Đọc được phần SQL structure.
- Có thể quan sát query shape trong log/diagnostics.
- Kiểm tra đúng số placeholders.
- Tránh nối nhiều đoạn SQL không rõ nguồn.

### Không log giá trị nhạy cảm

`USING` không nhúng bound values vào `v_sql`, giúp log câu SQL template mà không tự lộ input. Tuy nhiên giá trị parameter có thể chứa thông tin nhạy cảm trong logs khác; cần thiết kế chính sách logging/redaction phù hợp.

Không dùng `RAISE NOTICE 'SQL = %', v_sql` trên production với dynamic SQL chứa literal bí mật được chèn qua `%L` mà chưa kiểm soát quyền xem log.

## 57. EXPLAIN với câu SQL động

Để hiểu kế hoạch của SQL động, hãy lấy **câu lệnh cuối cùng và parameter values đại diện** trong môi trường an toàn, rồi chạy `EXPLAIN` trên một truy vấn tương đương:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COALESCE(SUM(amount), 0)
FROM lesson_dynamic_sql.orders
WHERE tenant_id = 10
  AND status = 'PAID';
```

### Vì sao cần dữ liệu đại diện?

- Trên sáu hàng lab, Seq Scan có thể rẻ hơn Index Scan.
- Trên bảng triệu hàng, tenant/status có selectivity khác.
- Partitioning và statistics ảnh hưởng plan.
- Biến động `work_mem`, cache, parallelism cũng ảnh hưởng.

**`EXPLAIN ANALYZE` thực thi câu lệnh thật**, nên không dùng trực tiếp với dynamic UPDATE/DELETE trên production mà không có biện pháp bảo vệ/rollback phù hợp.

## 58. EXECUTE và cơ chế lập kế hoạch

Trong PL/pgSQL, các câu SQL tĩnh có thể được chuẩn bị/lưu kế hoạch và PostgreSQL chọn generic/custom plan theo cơ chế của engine.

Ngược lại, `EXECUTE` dynamic SQL **không cache plan theo cùng cách cho command string trong PL/pgSQL**: câu SQL được parse/plan mỗi lần thực thi.

### Khi có lợi

Một query có plan nhạy với giá trị đầu vào: tenant 1 có 100 bản ghi, tenant 2 có hàng triệu bản ghi. Replan có thể giúp planner chọn đường đi phù hợp với giá trị của lần gọi.

### Khi có hại

Một query đơn giản chạy hàng nghìn lần với cùng cấu trúc nhưng chỉ thay ID có thể tốn thêm chi phí parse/plan không cần thiết.

### Không suy diễn tuyệt đối

`EXECUTE` không đảm bảo plan nhanh hơn, cũng không luôn chậm hơn. Nó đổi trade-off: **planning overhead** đối lại khả năng lựa chọn plan dựa trên command/value hiện tại. Benchmark p95 latency, throughput và CPU của application workload.

## 59. Khi nào intentionally dùng EXECUTE để replan?

Một query tĩnh trong PL/pgSQL có thể được lập generic plan không lý tưởng với phân bố dữ liệu cực lệch. Có thể dùng dynamic `EXECUTE` cùng SQL text cố định và `USING`:

```sql
EXECUTE
    'SELECT count(*)
       FROM lesson_dynamic_sql.orders
      WHERE tenant_id = $1
        AND status = $2'
INTO v_count
USING p_tenant_id, p_status;
```

Đây là một trường hợp **có thể có chủ ý** dù cấu trúc không đổi, để yêu cầu replanning mỗi invocation.

### Điều kiện áp dụng

- Đã chứng minh vấn đề từ generic/custom plan bằng dữ liệu và EXPLAIN.
- Đã cân nhắc statistics và index design.
- Planning cost không lấn át lợi ích.
- Không tạo SQL string bằng nối raw input.

Không dùng `EXECUTE` như “mẹo tối ưu” mặc định cho mọi câu SELECT.

## 60. Parameter type và implicit casts

Bound values từ `USING` có kiểu PostgreSQL cụ thể. Parser của query động suy luận/so sánh kiểu của `$1`/`$2` theo vị trí:

```sql
DO $$
DECLARE
    v_number numeric;
BEGIN
    EXECUTE 'SELECT $1::numeric * $2::numeric'
    INTO v_number
    USING 12.5, 2;

    RAISE NOTICE 'Result = %', v_number;
END;
$$;
```

### Vì sao nên cast rõ đôi khi?

- Đảm bảo overload operator/function được chọn đúng.
- Tránh implicit cast từ text sang number không hợp lệ.
- Hữu ích khi `NULL` khiến type inference mơ hồ.
- Làm hợp đồng đầu vào/đầu ra rõ ràng hơn.

Nhưng không nên cast mọi text từ người dùng sang numeric rồi mặc định luôn hợp lệ; validation vẫn cần thiết.

## 61. NULL và điều kiện WHERE

Truy vấn:

```sql
EXECUTE
    'SELECT count(*)
       FROM lesson_dynamic_sql.orders
      WHERE status = $1'
INTO v_count
USING NULL::text;
```

không tìm được hàng có `status NULL` bằng phép `= NULL`, vì SQL dùng three-valued logic. Với cột `status` của lab là NOT NULL, kết quả count bằng 0.

Nếu nghiệp vụ muốn coi hai NULL là bằng nhau, có thể dùng:

```sql
WHERE some_nullable_column IS NOT DISTINCT FROM $1
```

trong dynamic SQL tương ứng.

### `%L` cũng không tự sửa semantics NULL

`format('WHERE x = %L', NULL)` có thể tạo `WHERE x = NULL`, vẫn không match theo equality. Quoting an toàn và logic SQL NULL là hai vấn đề tách biệt.

## 62. Xây bộ lọc động có nhiều điều kiện tùy chọn

Đây là một bài toán phổ biến: có thể lọc status, mức tiền tối thiểu và tối đa. **Không cần** SQL động trong mọi trường hợp:

```sql
SELECT order_id, amount
FROM lesson_dynamic_sql.orders
WHERE tenant_id = 10
  AND ('PAID'::text IS NULL OR status = 'PAID')
  AND (NULL::numeric IS NULL OR amount >= NULL::numeric)
  AND (1000000::numeric IS NULL OR amount <= 1000000::numeric);
```

Trong SQL tĩnh, đây là dạng điều kiện tùy chọn bằng `p IS NULL OR ...`. Nó dễ viết nhưng có thể ảnh hưởng selectivity/plan khi nhiều predicates.

### Nếu muốn query structure tối giản theo input

Có thể xây một `WHERE` động gồm chỉ các điều kiện thực sự được bật, nhưng **không bao giờ chèn giá trị trực tiếp vào chuỗi**:

```text
base: WHERE tenant_id = $1
if status present: AND status = $2
if min present:    AND amount >= $3
```

Với implementation thực, cần quản lý vị trí placeholders và danh sách USING nhất quán. Nếu số tổ hợp ít, cân nhắc nhánh `IF` với SQL tĩnh hoặc một vài câu `EXECUTE` xác định trước; đừng tự xây một query-builder string dễ sai để “tối ưu” vô điều kiện.

## 63. Một function chọn cột nhưng trả về type ổn định

Đôi khi API muốn đọc một trong ba fields `status`, `amount` hoặc `customer_id` của một đơn hàng. Những cột có kiểu gốc khác nhau, nên chọn một **return type ổn định** nếu function cần dễ gọi từ JDBC.

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.order_field_text(
    p_tenant_id BIGINT,
    p_order_id BIGINT,
    p_field TEXT
)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    v_column TEXT;
    v_value TEXT;
BEGIN
    v_column := CASE p_field
        WHEN 'status' THEN 'status'
        WHEN 'amount' THEN 'amount'
        WHEN 'customer_id' THEN 'customer_id'
        ELSE NULL
    END;

    IF v_column IS NULL THEN
        RAISE EXCEPTION 'Unsupported field';
    END IF;

    EXECUTE format(
        'SELECT (o.%I)::text
           FROM lesson_dynamic_sql.orders AS o
          WHERE o.tenant_id = $1
            AND o.order_id = $2',
        v_column
    )
    INTO v_value
    USING p_tenant_id, p_order_id;

    RETURN v_value;
END;
$$;

SELECT lesson_dynamic_sql.order_field_text(
    10, 1, 'status'
);
```

### Tại sao return text?

Vì status là text, amount là numeric và customer_id là bigint, function này chọn cách **hiển thị chung** cho cả ba. Nhưng nếu caller cần phép cộng tiền/tính toán numeric, return text không còn lý tưởng; nên dùng API typed riêng.

### Điểm bảo mật

Whitelist các cột còn ngăn caller yêu cầu những fields ngoài hợp đồng API. `%I` tự quote column đúng nhưng không tự biết field nào được phép xem.

## 64. RETURN QUERY EXECUTE với bảng nguồn được chọn có kiểm soát

Nếu cần truy vấn trên một số bảng cùng schema:

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.read_order_source(
    p_source TEXT,
    p_tenant_id BIGINT
)
RETURNS TABLE (
    order_id BIGINT,
    status TEXT,
    amount NUMERIC
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_table TEXT;
    v_sql TEXT;
BEGIN
    v_table := CASE p_source
        WHEN 'current' THEN 'orders'
        ELSE NULL
    END;

    IF v_table IS NULL THEN
        RAISE EXCEPTION 'Unsupported source';
    END IF;

    v_sql := format(
        'SELECT o.order_id, o.status, o.amount
           FROM %I.%I AS o
          WHERE o.tenant_id = $1
          ORDER BY o.order_id',
        'lesson_dynamic_sql',
        v_table
    );

    RETURN QUERY EXECUTE v_sql USING p_tenant_id;
END;
$$;

SELECT *
FROM lesson_dynamic_sql.read_order_source('current', 10);
```

Sau này nếu có `orders_archive` với cùng column contract, bạn có thể thêm source `archive` vào mapping. Nhưng cần bảo đảm table tồn tại, permissions, kiểu cột và trạng thái dữ liệu phù hợp. Đừng cho caller tự truyền mọi tên bảng không hạn chế.

## 65. Chọn operator động: không chèn raw input

Ví dụ user muốn lọc amount:

```text
mode = gt → >
mode = ge → >=
mode = lt → <
mode = le → <=
```

Một cách an toàn là mapping:

```sql
v_operator := CASE p_mode
    WHEN 'gt' THEN '>'
    WHEN 'ge' THEN '>='
    WHEN 'lt' THEN '<'
    WHEN 'le' THEN '<='
    ELSE NULL
END;

IF v_operator IS NULL THEN
    RAISE EXCEPTION 'Unsupported comparison mode';
END IF;

v_sql := format(
    'SELECT count(*) FROM lesson_dynamic_sql.orders
      WHERE tenant_id = $1 AND amount %s $2',
    v_operator
);

EXECUTE v_sql INTO v_count
USING p_tenant_id, p_threshold;
```

Toàn bộ code trên là **đoạn thân function minh họa** với các biến đã được khai báo ở ngoài, không phải một statement chạy độc lập.

### Tại sao dùng %s ở đây?

`>` hoặc `>=` là **SQL operators**, không phải identifiers hoặc data values. `%s` chỉ an toàn vì `v_operator` được chọn từ constants do code sở hữu.

Không cho phép `p_mode` là chuỗi raw SQL như `'OR true'` rồi chèn thẳng vào `%s`.

## 66. Dynamic WHERE và mảng filter

Nếu user muốn lọc nhiều statuses, không cần tạo một chuỗi:

```text
status IN ('PAID','NEW','CANCELLED')
```

bằng cách nối literals.

Dùng array parameter:

```sql
DO $$
DECLARE
    v_count BIGINT;
    v_statuses TEXT[] := ARRAY['PAID', 'NEW'];
BEGIN
    EXECUTE
        'SELECT count(*)
           FROM lesson_dynamic_sql.orders
          WHERE tenant_id = $1
            AND status = ANY($2)'
    INTO v_count
    USING 10::bigint, v_statuses;

    RAISE NOTICE 'Matches: %', v_count;
END;
$$;
```

`ANY($2)` giúp truyền một danh sách giá trị với kiểu text[] rõ ràng. Đừng viết `format('status IN (%s)', p_statuses)` vì một array được in ra thành text không tự là danh sách SQL literals hợp lệ và có rủi ro nếu nối không kiểm soát.

### Lưu ý NULL/empty array

- Array rỗng không cho match nào với `= ANY`.
- Array chứa NULL có thể ảnh hưởng three-valued logic.
- Array hoàn toàn NULL khác empty array.

Application cần định nghĩa ngữ nghĩa “không chọn status nào”: trả tất cả, trả rỗng hay báo lỗi.

## 67. Dynamic LIMIT và OFFSET: cũng là data values

`LIMIT` và `OFFSET` không phải identifiers. Nếu câu query hỗ trợ placeholders, dùng `USING`:

```sql
EXECUTE
    'SELECT order_id, amount
       FROM lesson_dynamic_sql.orders
      WHERE tenant_id = $1
      ORDER BY order_id
      LIMIT $2 OFFSET $3'
USING p_tenant_id, p_limit, p_offset;
```

Đây là đoạn statement trong PL/pgSQL; nếu muốn xử lý các rows, dùng `FOR ... IN EXECUTE` hoặc `RETURN QUERY EXECUTE` thay vì chỉ gọi EXECUTE rồi bỏ kết quả.

### Validate giới hạn

`p_limit` nên được giới hạn trên, ví dụ 1–100 hoặc theo policy API. `p_offset` không âm và không quá lớn theo SLA. Với bảng lớn, deep pagination có chi phí; cân nhắc keyset pagination.

Truyền LIMIT qua USING không tự bảo vệ khỏi request lấy hàng triệu rows nếu application không giới hạn giá trị.

## 68. Dynamic SQL với bảng có tên trùng keyword

Giả sử bảng tên `"Order"` chứa chữ hoa và trùng một từ ngữ nhạy với SQL parser. Không bao giờ tự đoán cách thêm quotes:

```sql
SELECT format(
    'SELECT count(*) FROM %I.%I',
    'lesson_dynamic_sql',
    'Order'
);
```

`%I` quote khi cần để tạo `"Order"`.

### Quoting không phải “escape toàn bộ SQL”

Nhiều developers có thói quen đặt double quotes quanh nguyên chuỗi `schema.table.column`:

```text
"schema.table.column"
```

Đây là **một identifier**, không phải ba phần qualified. Hãy phân tách từng identifier với `%I.%I.%I` khi cấu trúc yêu cầu.

## 69. Kiểm tra cấu trúc output và schema drift

Nếu dynamic query trả:

```sql
SELECT order_id, amount, created_at ...
```

nhưng function khai:

```sql
RETURNS TABLE (
    order_id integer,
    amount text,
    created_at date
)
```

thì PostgreSQL có thể báo lỗi về cấu trúc trả về không tương thích, không tự biến mọi giá trị thành type bất kỳ chỉ vì text SQL được dựng lúc chạy.

### Cách xử lý

- Viết output columns và types rõ.
- Dùng casts/aliases có chủ đích.
- Khi đọc nhiều nguồn, yêu cầu các nguồn tuân thủ một **data contract**.
- Nếu schema thay đổi, migration phải đồng bộ function và clients.
- Không dùng `SELECT *` trên bảng có schema biến thiên rồi kỳ vọng `RETURNS TABLE` luôn ổn định.

Dynamic SQL trì hoãn một số lỗi đến runtime; nó không bỏ qua hệ thống kiểu của PostgreSQL.

## 70. Batch operations: ưu tiên câu lệnh set-based

Giả sử cần đánh dấu tất cả đơn NEW thành CANCELLED trong một tenant. Một dynamic UPDATE duy nhất:

```sql
EXECUTE
    'UPDATE lesson_dynamic_sql.orders
        SET status = $1
      WHERE tenant_id = $2
        AND status = $3'
USING 'CANCELLED', p_tenant_id, 'NEW';
```

thường phù hợp hơn:

```text
FOR mỗi order:
  EXECUTE UPDATE theo order_id
```

vì vòng lặp tạo nhiều lần parse/plan/execution và có thể kéo dài transaction/locks.

### Khi loop còn hợp lý?

Khi mỗi hàng cần logic ngoài SQL khó biểu diễn set-based, có exception handling riêng hoặc cần chia lô có kiểm soát. Nhưng ngay cả khi đó, phải quản lý lock ordering, retry và transaction scope.

## 71. SQL dynamic và quyền dữ liệu đa tenant

Một hàm:

```sql
CREATE FUNCTION read_any_table(
    p_table text,
    p_tenant_id bigint
) ...
```

nếu chạy `SECURITY DEFINER` và cho user tự chọn table có thể thành đường lộ dữ liệu.

Để thiết kế an toàn:

1. Không nhận tên schema/bảng tùy ý nếu API chỉ cần hai nguồn xác định.
2. Mapping source key sang danh sách table names đáng tin.
3. Schema-qualify identifiers bằng `%I.%I`.
4. Xác thực/ủy quyền tenant ở backend hoặc bằng cơ chế RLS.
5. Không cho quyền EXECUTE rộng hơn nhu cầu.
6. Không cho attacker tạo object trong search_path có thể bị gọi bằng quyền owner.
7. Kiểm tra role ownership và RLS bypass.

Một SQL statement syntactically safe vẫn có thể vi phạm authorization nếu routine được cấp quá nhiều quyền.

## 72. JDBC: bind tham số vào PL/pgSQL function

Ứng dụng Java không cần tự xây SQL động ở client chỉ vì function dùng SQL động bên trong. Gọi function qua prepared statement:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class OrderReports {
    public static BigDecimal total(
            Connection conn,
            long authorizedTenantId,
            String status
    ) throws SQLException {
        String sql = """
            SELECT lesson_dynamic_sql.total_by_table(
                'orders',
                ?,
                ?
            )
            """;

        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setLong(1, authorizedTenantId);
            ps.setString(2, status);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException(
                        "Expected one aggregate row"
                    );
                }
                return rs.getBigDecimal(1);
            }
        }
    }
}
```

### Điểm cốt lõi

- Java bind các **giá trị** bằng JDBC placeholders `?`.
- Function PL/pgSQL dựng bảng bằng `format('%I')` và truyền tenant/status bằng `USING`.
- `authorizedTenantId` phải đến từ quyền truy cập đã được xác thực, không từ một tham số request tùy ý.
- JDBC không cần biết SQL command string nội bộ của function.

Nhưng backend vẫn phải kiểm tra function không cho chọn các tables trái phép.

## 73. JDBC: dynamic ORDER BY qua API có kiểm soát

Có thể gọi function `search_orders`:

```java
String sql = """
    SELECT order_id, amount, created_at
    FROM lesson_dynamic_sql.search_orders(?, ?, ?, ?)
    """;

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setLong(1, authorizedTenantId);
    ps.setString(2, sortColumn);
    ps.setString(3, sortDirection);
    ps.setInt(4, Math.min(Math.max(pageSize, 1), 100));

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("order_id");
            BigDecimal amount = rs.getBigDecimal("amount");
            java.time.OffsetDateTime created =
                rs.getObject(
                    "created_at",
                    java.time.OffsetDateTime.class
                );
            // Map row sang DTO.
        }
    }
}
```

Đoạn code là skeleton; giả định có `conn`, `authorizedTenantId`, `sortColumn`, `sortDirection`, `pageSize` và driver hỗ trợ mapping timestamp phù hợp.

### Vì sao validate cả ở database?

Frontend có thể hạn chế sortColumn qua dropdown, nhưng API vẫn có thể bị gọi trực tiếp. Function `search_orders` dùng whitelist và max LIMIT, nên không phụ thuộc hoàn toàn UI.

### Tránh lạm dụng generic search API

Đừng cho ứng dụng gửi một chuỗi `ORDER BY foo DESC; ...` như parameter. Truyền **giá trị lựa chọn có cấu trúc** (column enum, direction enum), để backend/database mapping.

## 74. Spring/JdbcTemplate

Một service dùng Spring có thể gọi function qua `JdbcTemplate`:

```java
String sql = """
    SELECT order_id, amount, created_at
    FROM lesson_dynamic_sql.search_orders(?, ?, ?, ?)
    """;

var results = jdbcTemplate.query(
    sql,
    (rs, rowNum) -> new OrderSummary(
        rs.getLong("order_id"),
        rs.getBigDecimal("amount"),
        rs.getObject(
            "created_at",
            java.time.OffsetDateTime.class
        )
    ),
    authorizedTenantId,
    sortColumn,
    sortDirection,
    20
);
```

Giả định lớp/record `OrderSummary` và `JdbcTemplate` đã có. Ứng dụng nên có transaction boundary rõ ràng đối với các routines cập nhật dữ liệu và mapping SQLSTATE thành lỗi API phù hợp.

Nếu Spring gọi procedure DML qua `CALL`, cần cân nhắc transaction manager; PL/pgSQL `EXECUTE` bên trong procedure không tự tạo transaction riêng.

## 75. SQLSTATE và phân loại lỗi ở Java

Lỗi dynamic SQL có thể được trả về client qua `SQLException.getSQLState()`:

```java
try {
    // Gọi function/procedure có dynamic SQL.
} catch (SQLException ex) {
    String state = ex.getSQLState();

    if ("42P01".equals(state)) {
        // undefined_table: lỗi schema/contract,
        // không nên coi là "0 kết quả".
    } else if ("42501".equals(state)) {
        // insufficient_privilege:
        // lỗi quyền cần được xử lý bảo mật.
    } else if ("40P01".equals(state)) {
        // deadlock_detected:
        // có thể retry toàn transaction theo policy.
    } else {
        throw ex;
    }
}
```

Đây là ví dụ phân loại. Trong ứng dụng thật, không nên catch rồi bỏ qua exception mà không trả lỗi hoặc rollback theo ngữ cảnh. Các transaction errors như serialization failure/deadlock thường cần retry **cả đơn vị transaction**, không chỉ chạy lại một statement tùy tiện.

### Đừng lộ SQL text nội bộ

Exception messages từ database có thể chứa tên schema/table hoặc dữ liệu. Public API nên hiển thị mã lỗi/chi tiết phù hợp, không tự gửi nguyên SQL command string và stack trace cho người dùng cuối.

## 76. Bảo vệ khỏi query nặng dù đã chống injection

Một câu SQL động có whitelist hoàn hảo vẫn có thể chạy rất nặng nếu:

- User yêu cầu 100 triệu rows mà không có LIMIT.
- Chọn sort trên cột không có index và không lọc đủ.
- Chọn bảng khổng lồ cho `count(*)` nhiều lần.
- Truy vấn theo tenant lớn trong giờ cao điểm.
- Function chạy lặp lại từng hàng thay vì set-based.

Các biện pháp:

- Giới hạn page size và các lựa chọn sort/filter.
- Timeout và query budgets.
- Kiểm tra indexes/statistics.
- Rate limiting.
- Benchmark trên dữ liệu đại diện.
- Theo dõi temp I/O, buffer reads và concurrency.

`USING` bảo vệ cú pháp/giá trị, **không tự đặt hạn mức tài nguyên**.

## 77. Quan sát lệnh SQL động ở môi trường thật

Những dữ liệu nên theo dõi:

| Dấu hiệu | Gợi ý điều tra |
|---|---|
| Tỷ lệ lỗi `42P01` tăng | Tên bảng/timing migration/schema drift |
| Lỗi `42703` | Tên cột không còn tồn tại |
| Lỗi `42501` | Role/GRANT/search_path/SECURITY DEFINER |
| Runtime cao | Plan, input selectivity, index và sort |
| Lặp nhiều query shapes | Có thể cấu trúc SQL bị biến thiên không cần thiết |
| CPU planning tăng | EXECUTE lập kế hoạch lại quá thường xuyên |
| Lock waits | Dynamic UPDATE/DDL giữ khóa lâu |
| Temp reads/writes | Sort/hash spill trong câu query động |

### Logging

Ghi query shape/fingerprint, routine name, tenant scope đã được kiểm soát và elapsed time. Tránh log raw parameters nhạy cảm, secrets hoặc toàn bộ SQL literals do người dùng cung cấp.

`pg_stat_statements` có thể giúp quan sát các statement patterns ở những môi trường đã được cài/cấu hình extension; nhưng nó không thay thế việc đọc plan của trường hợp cụ thể.

## 78. Khi nào nên dùng công cụ migration thay dynamic DDL?

Nếu một thay đổi schema luôn được biết từ lúc release, hãy ưu tiên **versioned migrations**:

```sql
ALTER TABLE lesson_dynamic_sql.orders
ADD COLUMN IF NOT EXISTS source_channel TEXT;
```

Thay vì tạo một admin function nhận tên bảng/cột/kiểu rồi dùng `EXECUTE format(...)`.

### Lợi ích migration

- Review DDL trước deploy.
- Theo dõi phiên bản và rollback.
- Đánh giá locks/index size/backfill.
- Tách quyền migration khỏi quyền application runtime.
- Không cấp API quyền thay đổi schema tùy ý.

Dynamic DDL thích hợp khi thật sự cần sinh đối tượng có **tên/cấu trúc biến thiên theo dữ liệu** và có governance. Không dùng nó để tránh viết migration script.

## 79. Case study: báo cáo theo nhiều bảng cùng cấu trúc

Một dịch vụ báo cáo có hai nguồn:

```text
orders_current
orders_archive
```

Nếu hai bảng có cùng cột `tenant_id`, `amount`, `status`, một function chọn nguồn theo whitelist có thể dùng:

```text
source 'current' → table current
source 'archive' → table archive
```

SQL structure:

```sql
v_sql := format(
    'SELECT COALESCE(SUM(amount), 0)
       FROM %I.%I
      WHERE tenant_id = $1 AND status = $2',
    v_schema,
    v_table
);

EXECUTE v_sql INTO v_total
USING p_tenant_id, p_status;
```

Đây là đoạn thân PL/pgSQL, không phải một function độc lập. `v_schema/v_table` phải đến từ mapping đáng tin và caller phải được cấp quyền trên nguồn phù hợp.

### Có nhất thiết phải SQL động?

Nếu hai bảng cùng cấu trúc và cần query cả hai, một `UNION ALL` view có thể giúp ứng dụng dùng SQL tĩnh. Nếu nguồn được partitioning theo thời gian, PostgreSQL partition pruning có thể là giải pháp tốt hơn chọn table thủ công.

Chỉ dùng SQL động khi **lợi ích chọn cấu trúc lúc chạy** vượt chi phí complexity/planning/permissions.

## 80. Case study: sắp xếp theo cột người dùng chọn

Yêu cầu:

- Client chọn `amount`, `created_at` hoặc `order_id`.
- Client chọn ASC/DESC.
- Tối đa 100 rows.
- Chỉ được xem tenant của mình.

Hàm `search_orders` ở phần trước đáp ứng bằng:

1. Whitelist tên cột.
2. Whitelist hướng sắp xếp.
3. `format('... %I %s ...')` cho phần cấu trúc.
4. `USING p_tenant_id, p_limit` cho giá trị.
5. Stable ORDER BY có tie-breaker.

### Bổ sung trong production

- Authorization của tenant từ session/roles.
- Filter status được phép.
- Các trường sort được map đúng indexes.
- Pagination (OFFSET hoặc keyset) phù hợp.
- Test SQL injection, NULL và invalid values.
- Đo throughput/p95 latency theo cột sort.

Một hàm an toàn về injection vẫn có thể là API không tối ưu nếu mọi sort mới đều dẫn đến full scan + disk sort.

## 81. Case study: công cụ admin chọn cột để thống kê

Một admin tool cần tính `count(distinct ...)` trên cột được chọn:

```sql
CREATE OR REPLACE FUNCTION lesson_dynamic_sql.distinct_count(
    p_column TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_column TEXT;
    v_count BIGINT;
BEGIN
    v_column := CASE p_column
        WHEN 'tenant_id' THEN 'tenant_id'
        WHEN 'customer_id' THEN 'customer_id'
        WHEN 'status' THEN 'status'
        ELSE NULL
    END;

    IF v_column IS NULL THEN
        RAISE EXCEPTION 'Unsupported column';
    END IF;

    EXECUTE format(
        'SELECT count(DISTINCT %I)
           FROM lesson_dynamic_sql.orders',
        v_column
    )
    INTO v_count;

    RETURN v_count;
END;
$$;
```

### Điểm bảo mật

Function cố định bảng `orders`, whitelist columns và chỉ trả aggregate. Nhưng aggregate vẫn có thể tiết lộ thông tin tùy data/scope; khi đưa cho user đa tenant, cần thêm `tenant_id = $1` và authorization. **Chỉ trả count không mặc định biến truy vấn thành an toàn về quyền riêng tư.**

## 82. Case study: table-per-tenant là một quyết định kiến trúc

Một hệ thống đôi khi chọn:

```text
orders_tenant_10
orders_tenant_20
orders_tenant_30
```

Việc dựng table name bằng:

```sql
format('orders_tenant_%s', p_tenant_id)
```

vẫn cần:

- Kiểm tra tenant ID hợp lệ và mapping thực.
- `%I` khi dùng tên thành identifier.
- Quản lý migrations đồng loạt.
- Indexes/constraints giống nhau.
- Hạn chế số lượng relations để tránh catalog growth.
- Role isolation và permissions.

Không coi “mỗi tenant một bảng” luôn an toàn hơn shared table + RLS. PostgreSQL partitioning, shared-schema multi-tenancy và schema-per-tenant có trade-offs khác nhau; dynamic SQL chỉ là một công cụ thực thi kiến trúc đã chọn.

## 83. Những sai lầm phổ biến

**“Dùng EXECUTE cho mọi SELECT sẽ nhanh hơn.”** Không. PL/pgSQL EXECUTE lập kế hoạch mỗi lần và có planning overhead.

**“EXECUTE của PL/pgSQL là SQL PREPARE/EXECUTE.”** Không. Hai cơ chế có cú pháp và plan caching khác nhau.

**“USING có thể bind tên bảng và cột.”** Không. Nó truyền dữ liệu, không thay identifiers.

**“ORDER BY $1 sẽ sắp theo cột được truyền.”** Không. `$1` là giá trị chứ không phải column reference.

**“%I và %L dùng như nhau.”** Không. `%I` quote identifier, `%L` quote literal.

**“%s luôn an toàn vì dùng format().”** Không. `%s` chèn chuỗi thô và có thể gây injection.

**“format('%I','schema.table') tạo tên schema.table.”** Không. Nó tạo một identifier chứa dấu chấm; dùng `%I.%I`.

**“format('%I',input) chứng minh user được quyền truy cập bảng.”** Không. Quoting và authorization khác nhau.

**“format('%L',NULL) tự biến WHERE x = NULL thành đúng.”** Không. SQL NULL so sánh với equality theo three-valued logic.

**“quote_literal(NULL) luôn nối chuỗi an toàn.”** Không. Strict NULL có thể khiến cả expression nối chuỗi ra NULL; dùng quote_nullable khi cần literal.

**“SELECT ... INTO var nằm trong dynamic SQL string.”** Không. `INTO` cho PL/pgSQL EXECUTE phải đặt ở ngoài command string.

**“EXECUTE INTO luôn bắt đúng một hàng.”** Không. Dùng `STRICT` khi muốn đúng một hàng.

**“EXECUTE tự cập nhật FOUND.”** Không. Dùng `GET DIAGNOSTICS ROW_COUNT` hoặc semantics khác phù hợp.

**“INSERT RETURNING INTO có thể lặng lẽ bỏ qua vô hạn hàng.”** Không nên giả định; DML RETURNING nhiều rows vào một target có thể gây lỗi.

**“RETURN QUERY EXECUTE chỉ trả một hàng.”** Không. Nó có thể bổ sung nhiều rows cho set-returning function.

**“FOR IN EXECUTE luôn tốt hơn UPDATE set-based.”** Không. Loop theo hàng có overhead và tăng lock duration.

**“Dynamic SQL trả mọi cấu trúc cột mà RETURNS TABLE tự ép đúng.”** Không. Return type vẫn được PostgreSQL kiểm tra.

**“CREATE INDEX CONCURRENTLY chạy trong PL/pgSQL DO.”** Không. Câu lệnh này không được dùng trong transaction block phù hợp.

**“DDL qua EXECUTE tự động online.”** Không. DDL vẫn có locking và deployment trade-offs.

**“SECURITY DEFINER + %I là hoàn toàn an toàn.”** Không. Quyền owner, search_path, allowlist, RLS và input validation vẫn phải xem xét.

**“regclass chứng minh quyền truy cập relation.”** Không. Nó hỗ trợ resolve object, không thay ACL.

**“Lỗi undefined_table luôn có nghĩa 0 rows.”** Không. Đây là lỗi schema/runtime cần xử lý rõ.

**“USING thay validation của LIMIT/filters.”** Không. Bound values vẫn có thể tạo query cực rộng.

**“Dynamic SQL cần được log cả values để debug.”** Không mặc định; cần bảo vệ dữ liệu nhạy cảm trong logs.

**“Một query chạy nhanh trên sáu rows lab đại diện production.”** Không. Cần dữ liệu và phân bố đại diện.

## 84. Checklist thiết kế SQL động

Trước khi đưa một routine dynamic SQL vào production, tự hỏi:

1. Có thể dùng SQL tĩnh thay không?
2. Phần **cấu trúc** nào thực sự phải thay đổi khi chạy?
3. Tất cả identifiers đã được quote bằng `%I` cho đúng từng thành phần chưa?
4. Tất cả data values có thể bind bằng `USING` chưa?
5. Có dùng `%s` với dữ liệu raw không đáng tin không?
6. SQL keywords/operators/type fragments có whitelist không?
7. Các bảng/cột nguồn có được map từ danh sách cho phép không?
8. Tenant/authorization có được lấy từ nguồn đáng tin không?
9. Function có chạy SECURITY DEFINER không; owner và search_path đã an toàn chưa?
10. Cần nhận một hàng, nhiều hàng hay row count?
11. Có dùng đúng `INTO STRICT`, `RETURN QUERY EXECUTE`, `FOR IN EXECUTE` hoặc `GET DIAGNOSTICS` không?
12. Có xử lý NULL và zero rows đúng nghiệp vụ không?
13. Có đảm bảo return columns/typed contract ổn định không?
14. Có giới hạn query cost, LIMIT và thời gian thực thi không?
15. Có benchmark plan/latency với giá trị rất phổ biến và rất hiếm không?
16. Có xử lý exception/rollback thay vì che lỗi không?
17. DDL đã được review về locks, privileges và khả năng rollback chưa?
18. Có test đổi schema/index và query callers từ JDBC/Spring không?

Đây là checklist **thiết kế sử dụng SQL động**, không thay cho vòng Content QA riêng của quy trình sản xuất tài liệu học.

## 85. Quy trình xây SQL động an toàn

### Bước 1 — Phát biểu nhu cầu

Ví dụ: “Cho phép sắp xếp danh sách đơn hàng theo một trong ba cột, giới hạn tối đa 100 rows”.

### Bước 2 — Tách cấu trúc và giá trị

**Cấu trúc:** cột sort, hướng.

**Giá trị:** tenant ID, LIMIT, status filter.

### Bước 3 — Mapping cấu trúc

Dùng `CASE`/whitelist xác định đúng SQL identifier/keyword cho phép; không nhận nguyên SQL string.

### Bước 4 — Dựng SQL bằng format

`%I` cho tên cột/table/schema, `%s` cho từ khóa đã validate.

### Bước 5 — Bind data bằng USING

`$1`, `$2` tương ứng với typed values; dùng casts/validation khi cần.

### Bước 6 — Chọn cách nhận kết quả

`INTO`/`STRICT`, `RETURN QUERY EXECUTE`, `FOR ... IN EXECUTE` hoặc `ROW_COUNT`.

### Bước 7 — Kiểm soát quyền

Schema-qualified names, safe role/`search_path`, tenant scope và EXECUTE privileges.

### Bước 8 — Kiểm tra runtime characteristics

Plan, indexes, sort, buffers, WAL/locks khi DML/DDL.

### Bước 9 — Test edge cases

Missing/NULL, tên cột không hợp lệ, keywords, Unicode, quoting, no rows, multiple rows, query quá rộng.

### Bước 10 — Triển khai có observability

Ghi error classes và query shapes an toàn, theo dõi p95 latency, quyền và migrations.

## 86. Bài tập thực hành

### Bài 1 — SQL tĩnh hay động?

Một function luôn đọc `lesson_dynamic_sql.orders` và lọc theo `tenant_id`. Viết một phiên bản SQL tĩnh. Giải thích vì sao không cần EXECUTE.

### Bài 2 — PL/pgSQL EXECUTE cơ bản

Viết `DO` block dùng `EXECUTE 'SELECT $1 + $2' INTO v_result USING 7,5`. In kết quả.

### Bài 3 — Phân biệt hai EXECUTE

So sánh PL/pgSQL `EXECUTE command-string USING ...` với SQL `PREPARE ...; EXECUTE prepared_name(...)`. Cơ chế plan của hai cách khác nhau thế nào?

### Bài 4 — USING hai values

Đếm đơn hàng theo tenant và status bằng dynamic SELECT với `$1`, `$2`. Không nối trực tiếp input vào SQL string.

### Bài 5 — %I cho tên bảng

Dựng `SELECT count(*) FROM lesson_dynamic_sql.orders` bằng `format('%I.%I',...)`. Thử tên bảng có dấu cách.

### Bài 6 — Dấu chấm trong identifier

So sánh `format('%I', 'lesson_dynamic_sql.orders')` với `format('%I.%I','lesson_dynamic_sql','orders')`. Vì sao kết quả thứ nhất sai khi muốn qualified table?

### Bài 7 — %L và dấu nháy

Dựng `SELECT 'O''Reilly'` bằng `format('%L', value)`. Quan sát cách PostgreSQL escape dấu nháy.

### Bài 8 — %s chỉ dùng cho dữ liệu đã validate

Xây một dynamic ORDER BY direction với whitelist ASC/DESC. Vì sao không dùng trực tiếp `p_direction` từ API?

### Bài 9 — quote_ident và format

Viết hai cách tạo SQL chọn cột `"Order Date"` của bảng `"Sales Report"`. Cách nào dễ đọc hơn?

### Bài 10 — quote_nullable

So sánh `quote_literal(NULL)` và `quote_nullable(NULL)` khi nối SQL string. Tại sao `%L` là lựa chọn thuận tiện cho literal có thể NULL?

### Bài 11 — Không bind identifier bằng USING

Thử giải thích vì sao `EXECUTE 'SELECT count(*) FROM $1' USING 'orders'` không được. Viết cách thay bằng `%I` và whitelist.

### Bài 12 — Không bind ORDER BY column

Giải thích vì sao `ORDER BY $1` không sort theo tên cột từ parameter. Viết phiên bản dùng `%I`.

### Bài 13 — EXECUTE INTO

Viết dynamic SELECT lấy `amount` theo order ID vào biến numeric. Kết quả khi không tìm thấy hàng là gì?

### Bài 14 — INTO STRICT

Viết hàm tìm amount bắt buộc có đúng một hàng. Thử ID không tồn tại và một query thiếu uniqueness dẫn tới nhiều rows. Quan sát SQLSTATE tương ứng.

### Bài 15 — STRICT và aggregate

Vì sao `SELECT count(*)` có thể trả đúng một hàng ngay cả khi bảng không có bản ghi match? `STRICT` có phát hiện “không tồn tại đơn” trong trường hợp này không?

### Bài 16 — FOUND và EXECUTE

Chạy dynamic UPDATE rồi kiểm tra `FOUND`; giải thích vì sao không nên dùng nó để kết luận số rows affected bởi EXECUTE. Viết cách dùng `GET DIAGNOSTICS ROW_COUNT`.

### Bài 17 — Dynamic UPDATE

Viết function đổi trạng thái NEW thành CANCELLED cho một tenant và trả số hàng cập nhật. Chạy trong BEGIN/ROLLBACK.

### Bài 18 — INSERT RETURNING

Viết dynamic INSERT đơn hàng trả `order_id` qua `EXECUTE ... INTO`. Truyền tất cả values bằng USING.

### Bài 19 — Dynamic DELETE

Viết DELETE những đơn CANCELLED của một tenant; dùng GET DIAGNOSTICS và ROLLBACK lab để kiểm tra số rows.

### Bài 20 — RETURN QUERY EXECUTE

Tạo function trả nhiều đơn hàng của tenant với order_id, amount, created_at. Giải thích vì sao dùng `RETURNS TABLE`.

### Bài 21 — FOR IN EXECUTE

Dùng record trong vòng `FOR ... IN EXECUTE` để in order ID và amount bằng NOTICE. Với tập không có hàng, vòng lặp làm gì?

### Bài 22 — RECORD runtime

Một query động trả status, amount; sau đó code đọc `record.nonexistent_field`. Vì sao lỗi chỉ xuất hiện ở runtime?

### Bài 23 — Dynamic ORDER BY

Gọi `search_orders(10, 'amount','ASC',10)`. Giải thích cột/hướng đã được validate ra sao và LIMIT được bind bằng gì.

### Bài 24 — Invalid sort input

Thử truyền một chuỗi cột không thuộc danh sách cho phép. Function nên trả lỗi gì thay vì tự chạy biểu thức bất kỳ?

### Bài 25 — Bound LIMIT

Thử LIMIT âm, 0 và 10000. Cách nào để function từ chối request vượt ngân sách của API?

### Bài 26 — Whitelist source table

Thiết kế mapping `current`/`archive` sang các bảng có cấu trúc tương thích. Tại sao `format('%I')` chưa đủ để bảo vệ quyền truy cập?

### Bài 27 — regclass

Sử dụng `to_regclass` để kiểm tra một relation tồn tại. Vì sao kiểm tra tồn tại không thay quyền và không loại hoàn toàn race với DDL concurrent?

### Bài 28 — Dynamic DDL

Viết procedure chỉ cho phép thêm cột `notes text` vào bảng orders trong schema lab. Sử dụng `%I.%I` và whitelist.

### Bài 29 — CREATE INDEX

Dùng `EXECUTE format(...)` để tạo index amount trong lab. Vì sao không chạy `CREATE INDEX CONCURRENTLY` bên trong một DO block?

### Bài 30 — SQL type keyword

Một người dùng chọn kiểu `text`, `numeric(14,2)` hoặc `timestamptz`. Viết mapping allowlist cho data type, không chèn raw string vào `%s`.

### Bài 31 — COMMENT ON TABLE

Dùng `format('COMMENT ON TABLE %I.%I IS %L',...)` với comment có dấu nháy đơn. Vì sao comment cần `%L`?

### Bài 32 — Tên bảng theo năm/tháng

Tạo procedure `create_monthly_stage` với year/month đã validate. Giải thích khác biệt với partitioning thật.

### Bài 33 — Security Definer

Một function SECURITY DEFINER nhận tên bảng tùy ý. Nêu ba cách caller có thể lợi dụng quyền owner và ba biện pháp bảo vệ.

### Bài 34 — search_path

Giải thích rủi ro dùng tên bảng không schema-qualified trong routine đặc quyền nếu user có quyền tạo object trong một schema thuộc search_path.

### Bài 35 — SQLSTATE

Chạy dynamic SELECT trên bảng không tồn tại trong exception block, dùng GET STACKED DIAGNOSTICS để lấy SQLSTATE/MESSAGE_TEXT. Vì sao không nên trả 0 cho mọi lỗi?

### Bài 36 — Replanning

So sánh PL/pgSQL SQL tĩnh và EXECUTE động khi tenant A có vài hàng, tenant B có hàng triệu hàng. Lập kế hoạch benchmark để quyết định có nên replan mỗi lần không.

### Bài 37 — NULL-aware filter

Viết điều kiện `IS NOT DISTINCT FROM $1` cho một cột nullable, so sánh với `= $1` khi input NULL.

### Bài 38 — SQL array với ANY

Truyền `ARRAY['PAID','NEW']::text[]` bằng USING, dùng `status = ANY($2)`. Vì sao cách này tốt hơn tự nối chuỗi `IN (...)`?

### Bài 39 — JDBC/Spring

Viết PreparedStatement gọi `search_orders` với các tham số bound, thêm timeout/limit policy. Backend phải lấy tenant ID từ đâu?

### Bài 40 — Tổng hợp kiến trúc

Một hệ thống báo cáo đa tenant yêu cầu:

- Dữ liệu có bảng hiện tại và lưu trữ.
- User chọn ba cột sort và ASC/DESC.
- Có thể lọc một danh sách statuses.
- Hệ thống quản trị cần tạo bảng staging tháng mới.
- Truy vấn chạy qua Spring/JDBC.
- Một số routines chạy với quyền cao hơn caller.

Hãy thiết kế:

1. Những phần nào phải dùng SQL tĩnh và phần nào thực sự cần `EXECUTE`?
2. Map source/column/direction/type như thế nào qua whitelist?
3. Dùng `%I`, `%L`, `%s` và `USING` ở đâu?
4. Kết quả được nhận qua `INTO`, `ROW_COUNT` hay `RETURN QUERY EXECUTE`?
5. Thiết kế bảo mật tenant/roles/SECURITY DEFINER/search_path ra sao?
6. Những SQLSTATE nào cần phân biệt với trường hợp 0 rows?
7. Chiến lược benchmark/replan/index/timeout/pagination nào đáp ứng SLA?
8. Dynamic DDL staging có lock/migration/retention controls gì?

## Kết luận

**PL/pgSQL `EXECUTE` cho phép xây và thực thi một câu SQL vào thời điểm chạy.** Đây là công cụ mạnh khi **cấu trúc câu lệnh** thay đổi, ví dụ tên bảng, tên cột, hướng sắp xếp hoặc đối tượng DDL. Tuy nhiên, nó không nên thay SQL tĩnh khi chỉ có các giá trị `WHERE` thay đổi.

Quy tắc then chốt là **phân tách cấu trúc SQL khỏi dữ liệu**: dùng `format('%I', ...)` cho identifiers, `USING` để bind typed values qua `$1`/`$2`, `%L` cho literals khi thật sự phải dựng chuỗi và `%s` chỉ với keywords/operators đã được whitelist. `format` không tự biến raw SQL fragments thành an toàn; identifier quoting cũng không thay kiểm tra quyền.

Để nhận kết quả, dùng **`EXECUTE ... INTO`** cho một hàng, **`INTO STRICT`** khi yêu cầu đúng một hàng, **`GET DIAGNOSTICS ROW_COUNT`** sau dynamic DML, **`RETURN QUERY EXECUTE`** khi cần trả tập và **`FOR ... IN EXECUTE`** khi cần duyệt kết quả. Nhớ rằng **EXECUTE tự nó không cập nhật FOUND**, và `SELECT ... INTO` cho biến phải nằm ở cú pháp PL/pgSQL bên ngoài chuỗi dynamic.

Cuối cùng, SQL động được **lập kế hoạch mỗi lần**, nên có thể giúp với query nhạy giá trị nhưng cũng tăng planning overhead. Hãy ưu tiên SQL set-based, phân quyền chặt khi dùng SECURITY DEFINER, kiểm soát `search_path`, không tin input tenant từ client, tránh DDL/runtime privileges không cần thiết và đo `EXPLAIN` trên workload thật. Khi được sử dụng có chủ đích, `EXECUTE`, `USING` và `format` giúp xây các routines linh hoạt mà vẫn có kiểu dữ liệu, bảo mật và khả năng bảo trì tốt.
