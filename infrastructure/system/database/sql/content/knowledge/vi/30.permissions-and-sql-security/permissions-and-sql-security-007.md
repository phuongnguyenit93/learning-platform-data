# Vị trí không thể bind tham số: tên bảng, cột và hướng sắp xếp

**Bind tham số (parameter binding)** là một biện pháp quan trọng để viết SQL an toàn. Thay vì nối giá trị người dùng nhập vào chuỗi SQL, chương trình gửi câu lệnh có placeholder và truyền dữ liệu riêng. Driver/database xử lý giá trị đó như **dữ liệu**, giúp tránh việc một chuỗi đầu vào bất ngờ trở thành cú pháp SQL.

Nhưng placeholder không thể thay thế mọi thành phần trong câu SQL. Ví dụ:

```sql
SELECT order_id, created_at, total_amount
FROM sales_orders
WHERE tenant_id = ?
ORDER BY created_at DESC;
```

`?` có thể đại diện cho **giá trị của tenant_id**. Nó không thể đại diện cho tên bảng sales_orders, tên cột created_at, hướng sắp xếp DESC hoặc từ khóa SELECT, WHERE, JOIN.

Nếu chương trình muốn cho người dùng chọn cột sắp xếp, nó phải lựa chọn **một cấu trúc SQL đã được kiểm soát** hoặc tạo SQL động từ những thành phần được cho phép. Nối trực tiếp đầu vào vào câu SQL có thể dẫn tới **SQL injection**, truy cập nhầm bảng, đọc dữ liệu ngoài phạm vi hoặc thay đổi dữ liệu trái phép.

Bài học thuộc chương **Quyền và SQL an toàn** của **Database SQL**. Nội dung tập trung vào ranh giới giữa **giá trị có thể bind** và **cấu trúc SQL phải được xác định trước**, cách dùng allowlist, cách quote identifier đúng theo DBMS, cách viết dynamic SQL an toàn trong PostgreSQL, JDBC, Python, SQL Server và MySQL, cùng các lỗi thường gặp khi xử lý tên bảng, tên cột, ASC/DESC, LIMIT, danh sách IN và truy vấn tìm kiếm.

> **Nguyên tắc cốt lõi:** bind mọi giá trị dữ liệu có thể bind; với identifier hoặc phần cú pháp cần thay đổi, chỉ chọn từ allowlist do ứng dụng kiểm soát, sau đó quote identifier theo đúng DBMS. **Quote không thay thế allowlist**, và allowlist không thay thế phân quyền database.

## 1. Hai loại thành phần khác nhau trong câu SQL

Trước khi viết code, cần phân biệt **cấu trúc câu lệnh** với **giá trị mà câu lệnh xử lý**.

### 1.1. Cấu trúc SQL

Ví dụ:

```sql
SELECT order_id, created_at
FROM sales_orders
WHERE tenant_id = 10
ORDER BY created_at DESC;
```

Các thành phần cấu trúc gồm:

- Từ khóa SELECT, FROM, WHERE, ORDER BY.
- Tên bảng sales_orders.
- Tên cột order_id, created_at, tenant_id.
- Toán tử, hướng sắp xếp, cấu trúc JOIN, GROUP BY, biểu thức và alias.

Database cần hiểu các thành phần này để **parse** câu SQL thành cấu trúc truy vấn.

### 1.2. Giá trị dữ liệu

Các giá trị 10, PAID và mốc thời gian có thể được truyền riêng:

```sql
SELECT order_id, created_at
FROM sales_orders
WHERE tenant_id = $1
  AND status = $2
  AND created_at >= $3;
```

PostgreSQL nhận ba giá trị tương ứng. Chúng không được diễn giải thành từ khóa, tên bảng hoặc mệnh đề SQL mới.

### 1.3. Bảng phân biệt

| Thành phần | Ví dụ | Có thể bind như giá trị? |
|---|---|---|
| ID tenant | tenant_id = ? | Có |
| Email, status, timestamp | email = ?, status = ? | Có |
| Giá trị LIMIT/OFFSET | LIMIT ? | Thường có, tùy DB/driver |
| Tên bảng | FROM ? | Không |
| Tên schema | ?.sales_orders | Không |
| Tên cột | SELECT ? FROM ... | Không; placeholder là giá trị |
| Hướng sắp xếp | ORDER BY created_at ? | Không |
| Từ khóa JOIN | ? JOIN ... | Không |
| Biểu thức SQL | ORDER BY ? | Không thể bind thành grammar |

Khả năng bind LIMIT/OFFSET có khác biệt theo DBMS, driver và vị trí câu lệnh; cần kiểm tra hệ đang dùng. Dù bind được, chúng vẫn là **giá trị số**, không phải identifier hay cú pháp.

## 2. Vì sao placeholder không thể thay tên bảng hoặc cột?

### 2.1. Database parse cấu trúc trước khi nhận giá trị

Một câu lệnh tham số hóa có thể hình dung theo hai bước:

1. Ứng dụng gửi cấu trúc SQL: SELECT ... WHERE tenant_id = ?.
2. Ứng dụng gửi giá trị cho placeholder.

Database/driver biết placeholder nằm ở **vị trí biểu thức nhận giá trị**. Nó không yêu cầu database parse lại một tên bảng mới từ chuỗi giá trị.

Ví dụ:

```sql
SELECT *
FROM ?
WHERE tenant_id = ?;
```

Placeholder thứ nhất không có nghĩa “hãy lấy chuỗi tôi gửi rồi dùng nó làm tên bảng”. Sau FROM phải là một quan hệ hoặc biểu thức bảng hợp lệ; tham số bind là một giá trị, không phải identifier trong cây cú pháp.

### 2.2. SELECT ? không chọn một cột

```sql
SELECT ?
FROM sales_orders;
```

Nếu bind chuỗi total_amount, truy vấn thường trả **giá trị chuỗi total_amount cho mỗi hàng**, chứ không đọc cột total_amount.

Tương tự, ORDER BY ? với giá trị created_at có thể sắp theo một biểu thức hằng; nó không tự hiểu thành ORDER BY created_at.

### 2.3. ASC và DESC là cú pháp

```sql
ORDER BY created_at DESC;
```

Hướng sắp xếp thuộc grammar của câu lệnh. Câu ORDER BY created_at ? không thể dùng placeholder để thay ASC hoặc DESC.

### 2.4. Placeholder không phải macro thay văn bản

Parameter binding không phải tìm-thay-chuỗi:

```text
SQL: SELECT * FROM ? WHERE id = ?
Bind: ["sales_orders", 101]

Không có bước thay văn bản để biến placeholder đầu tiên thành tên bảng.
```

Bind không phải macro, không phải nối chuỗi và không phải cơ chế ghép tên SQL từ dữ liệu.

## 3. SQL injection khi nối tên bảng, cột và hướng sắp xếp

### 3.1. Nối giá trị dữ liệu

Code không an toàn:

```java
String sql =
    "SELECT order_id FROM sales_orders " +
    "WHERE status = '" + status + "'";
```

Nếu status chứa:

```text
PAID' OR '1'='1
```

SQL tạo ra có thể trở thành:

```sql
SELECT order_id
FROM sales_orders
WHERE status = 'PAID' OR '1'='1';
```

Điều kiện đã bị thay đổi. Cách đúng là bind:

```java
String sql =
    "SELECT order_id FROM sales_orders WHERE status = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, status);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Đọc kết quả.
        }
    }
}
```

Chuỗi PAID' OR '1'='1 khi được bind sẽ là **một giá trị status**, không thể tự đóng dấu nháy để thêm điều kiện SQL.

### 3.2. Nối tên cột để ORDER BY

Code không an toàn:

```java
String sql =
    "SELECT order_id, total_amount FROM sales_orders " +
    "WHERE tenant_id = ? ORDER BY " + sortBy;
```

Người gọi có thể gửi:

```text
total_amount DESC; DROP TABLE sales_orders; --
```

Chuỗi đó được ghép vào vị trí grammar. Ngay cả khi driver chặn nhiều statement, ứng dụng vẫn có thể bị ép sắp xếp theo biểu thức không mong muốn, truy vấn cột ngoài phạm vi hoặc gây lỗi.

### 3.3. Hướng sắp xếp cũng là đầu vào cấu trúc

Không thể bind DESC vào:

```sql
ORDER BY created_at ?
```

Phải xác định sortDirection có đúng một trong hai giá trị cho phép rồi mới dùng nó như cú pháp cố định.

### 3.4. SQL injection không chỉ là DROP TABLE

Đầu vào cấu trúc không an toàn có thể:

- Bỏ qua điều kiện tenant hoặc trạng thái.
- Đọc cột nhạy cảm ngoài danh sách cho phép.
- Thay đổi thứ tự, giới hạn hoặc cách JOIN.
- Làm truy vấn nặng để gây quá tải.
- Gọi hàm SQL hoặc biểu thức không được dự định.
- Gây lỗi để dò schema và thông tin hệ thống.
- Thay đổi dữ liệu nếu đường thực thi có quyền DML/DDL.

Mục tiêu không chỉ là ngăn payload DROP TABLE. Phải giữ quyền kiểm soát cấu trúc truy vấn và phạm vi dữ liệu.

## 4. Allowlist: chọn cấu trúc từ tập được phép

Giải pháp thông dụng cho lựa chọn tên cột/hướng sắp xếp là **allowlist**: ứng dụng định nghĩa rõ các lựa chọn được hỗ trợ và ánh xạ khóa API sang identifier SQL cố định.

### 4.1. Map khóa API sang tên cột cố định

```java
Map<String, String> sortColumns = Map.of(
    "created", "created_at",
    "total",   "total_amount",
    "order",   "order_id"
);

String sortColumn = sortColumns.get(sortBy);
if (sortColumn == null) {
    throw new IllegalArgumentException("Unsupported sort field");
}
```

Ứng dụng nhận sortBy như một **mã lựa chọn**. Chỉ khi khóa tồn tại trong map, nó mới lấy tên cột do code định nghĩa.

### 4.2. Kiểm tra hướng sắp xếp

```java
String direction;

if ("asc".equalsIgnoreCase(sortDirection)) {
    direction = "ASC";
} else if ("desc".equalsIgnoreCase(sortDirection)) {
    direction = "DESC";
} else {
    throw new IllegalArgumentException("Unsupported sort direction");
}
```

Sau kiểm tra, direction chỉ có thể là hai chuỗi cố định. Không sử dụng chuỗi đầu vào gốc.

### 4.3. Ghép SQL từ thành phần đã kiểm soát

```java
String sql = """
    SELECT order_id, tenant_id, status, created_at, total_amount
    FROM sales_orders
    WHERE tenant_id = ?
      AND status = ?
    ORDER BY %s %s, order_id ASC
    LIMIT ?
    """.formatted(sortColumn, direction);

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, tenantId);
    ps.setString(2, status);
    ps.setInt(3, limit);
    // Execute query...
}
```

Chỉ sortColumn lấy từ map và direction đã validation được ghép. tenantId, status và limit vẫn bind.

### 4.4. Vì sao thêm order_id ASC?

Nếu nhiều đơn có cùng created_at hoặc total_amount, thứ tự giữa chúng có thể thay đổi. Thêm khóa duy nhất:

```sql
ORDER BY created_at DESC, order_id ASC
```

giúp thứ tự ổn định hơn, đặc biệt khi phân trang. Nếu sort key chính là order_id, phần tie-breaker trùng cột không cần thiết.

### 4.5. Không nhận raw expression từ client

Allowlist nên ánh xạ khóa nghiệp vụ sang biểu thức được định nghĩa trong code, ví dụ:

```java
Map<String, String> sortExpressions = Map.of(
    "created", "o.created_at",
    "total", "o.total_amount",
    "customer", "o.customer_name"
);
```

Không cho client gửi LOWER(customer_name) NULLS LAST rồi đưa nguyên văn vào ORDER BY. Nếu muốn hỗ trợ sort theo biểu thức, hãy định nghĩa biểu thức đó trong map hoặc query builder có API an toàn.

## 5. Quote identifier: bảo vệ cú pháp, không cấp quyền truy cập

**Identifier quoting** giúp database hiểu đúng tên bảng/cột, kể cả khi tên chứa ký tự đặc biệt hoặc trùng từ khóa. Nhưng quote identifier **không tự xác nhận tên đó được phép sử dụng**.

### 5.1. PostgreSQL dùng dấu nháy kép

```sql
SELECT "order_id", "created_at"
FROM "public"."sales_orders";
```

Tên schema và tên bảng là hai identifier riêng. "public"."sales_orders" khác với "public.sales_orders", vốn là một identifier đơn có dấu chấm trong tên.

### 5.2. Quote không phải allowlist

Quote tên payroll_private đúng cú pháp không có nghĩa caller được phép đọc bảng payroll. Quote chỉ xử lý cách phân tích identifier, không ngăn truy cập đối tượng nhạy cảm.

Quy trình đúng:

1. Kiểm tra tên được chọn có thuộc tập đối tượng cho phép.
2. Kiểm tra người gọi có quyền nghiệp vụ tương ứng.
3. Quote từng identifier theo DBMS.
4. Bind mọi giá trị dữ liệu.
5. Chạy dưới database role có quyền tối thiểu.

### 5.3. Không tự quote bằng cách bọc dấu nháy

```java
String sql = "SELECT * FROM \"" + tableName + "\"";
```

không an toàn nếu tableName chứa dấu nháy kép. Việc quote đúng phải escape delimiter theo quy tắc DBMS và xử lý schema/table như từng identifier. Hãy dùng API quote identifier hoặc query builder của driver/ORM nếu có.

### 5.4. Quote schema và table riêng

PostgreSQL:

```sql
format('%I.%I', schema_name, table_name)
```

Không dùng format('%I', schema_name || '.' || table_name), vì kết quả là một identifier duy nhất chứa dấu chấm.

## 6. PostgreSQL: format('%I') và EXECUTE ... USING

PostgreSQL PL/pgSQL có câu lệnh EXECUTE để chạy SQL động.

### 6.1. Tạo bảng mẫu

```sql
CREATE TABLE public.sales_orders (
    order_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL
);

INSERT INTO public.sales_orders
    (order_id, tenant_id, status, created_at, total_amount)
VALUES
    (1001, 10, 'PAID', '2025-01-01 08:00:00+00', 120.00),
    (1002, 10, 'NEW',  '2025-01-02 08:00:00+00',  80.00),
    (1003, 10, 'PAID', '2025-01-03 08:00:00+00', 200.00),
    (2001, 20, 'PAID', '2025-01-01 09:00:00+00',  50.00);
```

Đây là schema thực hành riêng. Không tạo các bảng ví dụ trên database sản xuất nếu chưa có kế hoạch migration phù hợp.

### 6.2. Dynamic SQL với tên bảng và giá trị tenant

Giả sử hệ thống lưu bảng archive theo năm và cần đếm số hàng trong một bảng được chọn:

```sql
CREATE OR REPLACE FUNCTION count_archive_rows(
    p_table_name TEXT,
    p_tenant_id BIGINT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_count BIGINT;
    v_sql TEXT;
BEGIN
    IF p_table_name NOT IN (
        'sales_orders_2024',
        'sales_orders_2025'
    ) THEN
        RAISE EXCEPTION 'Unsupported archive table';
    END IF;

    v_sql := format(
        'SELECT count(*) FROM archive.%I WHERE tenant_id = $1',
        p_table_name
    );

    EXECUTE v_sql INTO v_count USING p_tenant_id;
    RETURN v_count;
END;
$$;
```

Giải thích:

- p_table_name được kiểm tra bằng allowlist.
- format('%I', p_table_name) quote tên bảng thành identifier PostgreSQL hợp lệ.
- $1 trong chuỗi SQL động là placeholder giá trị của câu lệnh được thực thi.
- USING p_tenant_id truyền tenant ID như dữ liệu, không nối số vào SQL.
- EXECUTE ... INTO lấy kết quả truy vấn động vào biến.

Allowlist quyết định **bảng nào được phép chọn**; %I bảo vệ cách tên hợp lệ được đưa vào grammar. Hai bảng archive phải tồn tại trong schema archive và có cột tenant_id tương thích.

### 6.3. Identifier có schema động

```sql
v_sql := format(
    'SELECT count(*) FROM %I.%I WHERE tenant_id = $1',
    p_schema_name,
    p_table_name
);
EXECUTE v_sql INTO v_count USING p_tenant_id;
```

Phải kiểm tra cặp schema/table có thuộc phạm vi được phép. Không cho người dùng tự chọn schema chỉ vì %I quote an toàn.

### 6.4. %I, %L và %s khác nhau

| Specifier | Ý nghĩa | Cách dùng |
|---|---|---|
| %I | Quote identifier | Tên schema, bảng, cột đã được cho phép |
| %L | Quote literal SQL | Giá trị literal khi thực sự cần nhúng vào chuỗi |
| %s | Chèn chuỗi nguyên văn | Chỉ dùng cho thành phần tin cậy/đã kiểm tra rất chặt |

Trong dynamic SQL PL/pgSQL, ưu tiên USING cho giá trị:

```sql
v_sql := format(
    'SELECT * FROM %I WHERE status = $1',
    p_table_name
);
EXECUTE v_sql USING p_status;
```

%L có thể hữu ích khi phải tạo literal trong một số ngữ cảnh không hỗ trợ bind, nhưng không nên dùng nó thay cho USING khi USING có thể đáp ứng.

Không dùng %s cho input chưa tin cậy:

```sql
v_sql := format(
    'SELECT * FROM %s ORDER BY %s',
    p_table_name,
    p_sort_expression
);
```

%s chèn chuỗi nguyên văn, không quote identifier và không validate grammar.

### 6.5. Dynamic ORDER BY trong PostgreSQL

```sql
CREATE OR REPLACE FUNCTION list_sales_orders(
    p_tenant_id BIGINT,
    p_sort_key TEXT,
    p_sort_direction TEXT,
    p_limit INTEGER,
    p_offset INTEGER
)
RETURNS TABLE (
    result_order_id BIGINT,
    result_created_at TIMESTAMPTZ,
    result_total NUMERIC
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_sort_column TEXT;
    v_direction TEXT;
    v_sql TEXT;
BEGIN
    CASE p_sort_key
        WHEN 'created' THEN v_sort_column := 'created_at';
        WHEN 'total'   THEN v_sort_column := 'total_amount';
        WHEN 'id'      THEN v_sort_column := 'order_id';
        ELSE RAISE EXCEPTION 'Unsupported sort key';
    END CASE;

    v_direction := upper(p_sort_direction);
    IF v_direction NOT IN ('ASC', 'DESC') THEN
        RAISE EXCEPTION 'Unsupported sort direction';
    END IF;

    IF p_limit < 1 OR p_limit > 100 THEN
        RAISE EXCEPTION 'Limit must be between 1 and 100';
    END IF;
    IF p_offset < 0 THEN
        RAISE EXCEPTION 'Offset cannot be negative';
    END IF;

    v_sql := format(
        'SELECT o.order_id, o.created_at, o.total_amount
         FROM public.sales_orders AS o
         WHERE o.tenant_id = $1
         ORDER BY o.%I %s NULLS LAST, o.order_id ASC
         LIMIT $2 OFFSET $3',
        v_sort_column,
        v_direction
    );

    RETURN QUERY EXECUTE v_sql
    USING p_tenant_id, p_limit, p_offset;
END;
$$;
```

%I quote cột. %s chỉ nhận ASC/DESC sau validation. Tenant, limit và offset được bind. Không dùng format('%I', v_direction), vì "DESC" sẽ là identifier chứ không phải token hướng sắp xếp.

### 6.6. Có thể tránh dynamic SQL

Nếu danh sách cột ngắn, có thể dùng SQL tĩnh với CASE:

```sql
SELECT order_id, created_at, total_amount
FROM public.sales_orders
WHERE tenant_id = $1
ORDER BY
    CASE WHEN $2 = 'created' THEN created_at END DESC,
    CASE WHEN $2 = 'total' THEN total_amount END DESC,
    CASE WHEN $2 = 'id' THEN order_id END DESC,
    order_id ASC
LIMIT $3 OFFSET $4;
```

Đây là cách không ghép identifier. Ví dụ minh họa hướng DESC; khi kết hợp các kiểu timestamp, numeric và bigint phải đảm bảo biểu thức CASE có kiểu tương thích. Có thể tách nhánh theo kiểu hoặc dùng truy vấn riêng. Cách CASE cũng có thể ảnh hưởng khả năng tận dụng index cho ORDER BY.

### 6.7. Dynamic SQL trong function quyền cao

Function PL/pgSQL vẫn có thể bị SQL injection. Với SECURITY DEFINER:

- Chỉ cấp quyền EXECUTE cho đúng nhóm role.
- Kiểm soát search_path an toàn, ưu tiên schema-qualified object.
- Không để người gọi điều khiển đối tượng nhạy cảm qua tên bảng tùy ý.
- Giới hạn quyền owner của function theo nguyên tắc tối thiểu.
- Không dùng dynamic SQL từ chuỗi raw mà không allowlist/quote/bind.

## 7. JDBC: PreparedStatement chỉ bind giá trị

Trong Java JDBC, placeholder thông dụng là ?.

```java
String sql = """
    SELECT order_id, status, total_amount
    FROM sales_orders
    WHERE tenant_id = ?
      AND status = ?
    ORDER BY created_at DESC
    LIMIT ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, tenantId);
    ps.setString(2, status);
    ps.setInt(3, limit);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            String orderStatus = rs.getString("status");
            BigDecimal total = rs.getBigDecimal("total_amount");
        }
    }
}
```

Ví dụ giả định DB/driver hỗ trợ placeholder ở vị trí LIMIT. Với SQL Server, cú pháp phân trang khác; với một số driver/database, cần kiểm tra cách bind LIMIT/OFFSET.

Không viết:

```java
String sql = "SELECT * FROM ? WHERE tenant_id = ?";
PreparedStatement ps = connection.prepareStatement(sql);
ps.setString(1, "sales_orders");
ps.setLong(2, tenantId);
```

setString truyền một **giá trị chuỗi**, không thay vị trí tên bảng.

### 7.1. Map sort key trong Java

```java
private static final Map<String, String> SORT_COLUMNS = Map.of(
    "created", "created_at",
    "total", "total_amount",
    "id", "order_id"
);

String column = SORT_COLUMNS.get(sortBy);
if (column == null) {
    throw new IllegalArgumentException("Unsupported sort key");
}
```

Sau đó validate direction thành ASC hoặc DESC rồi ghép hai giá trị đã kiểm soát vào ORDER BY. Các giá trị tenant/status/limit vẫn dùng setLong, setString, setInt.

Có thể dùng enum để biểu diễn sort key và direction thay cho chuỗi tùy ý. Điều đó giúp lỗi input bị phát hiện trước khi tạo SQL.

## 8. Python DB-API: placeholder theo driver, identifier dùng composition

Placeholder khác nhau tùy driver:

| Driver | Placeholder thường gặp |
|---|---|
| SQLite sqlite3 | ? |
| psycopg PostgreSQL | %s |
| Một số driver khác | :name hoặc %(name)s |

Đọc tài liệu driver thay vì tự đổi dấu placeholder.

SQLite:

```python
cursor.execute(
    """
    SELECT order_id, status
    FROM sales_orders
    WHERE tenant_id = ?
      AND status = ?
    """,
    (tenant_id, status),
)
```

Với psycopg, có thể dùng SQL composition:

```python
from psycopg import sql

query = sql.SQL(
    "SELECT order_id, total_amount "
    "FROM {} "
    "WHERE tenant_id = %s"
).format(
    sql.Identifier("public", "sales_orders")
)

cursor.execute(query, (tenant_id,))
```

sql.Identifier quote identifier theo quy tắc PostgreSQL và hỗ trợ tên schema/table riêng biệt. Giá trị tenant vẫn bind qua %s.

Allowlist trước khi tạo Identifier:

```python
ALLOWED_TABLES = {
    "current": ("public", "sales_orders"),
    "archive": ("archive", "sales_orders_2025"),
}

choice = request.args.get("source", "current")
parts = ALLOWED_TABLES.get(choice)
if parts is None:
    raise ValueError("Unsupported source")

query = sql.SQL(
    "SELECT order_id FROM {} WHERE tenant_id = %s"
).format(sql.Identifier(*parts))
cursor.execute(query, (tenant_id,))
```

sql.Identifier đảm bảo tên được quote đúng. ALLOWED_TABLES quyết định người gọi được phép chọn đối tượng nào. Không dùng sql.SQL(user_input) cho raw chuỗi không tin cậy và không dùng f-string để nhúng giá trị dữ liệu.

## 9. SQL Server: QUOTENAME và sp_executesql

SQL Server dùng QUOTENAME để quote identifier và sp_executesql để truyền giá trị:

```sql
DECLARE @schemaName sysname = N'dbo';
DECLARE @tableName sysname = N'sales_orders';
DECLARE @sql nvarchar(max);
DECLARE @tenantId bigint = 10;

IF @schemaName <> N'dbo'
   OR @tableName NOT IN (N'sales_orders', N'sales_orders_archive')
BEGIN
    THROW 50001, 'Unsupported table', 1;
END;

SET @sql =
    N'SELECT order_id, total_amount FROM ' +
    QUOTENAME(@schemaName) + N'.' + QUOTENAME(@tableName) +
    N' WHERE tenant_id = @p_tenant_id';

EXEC sys.sp_executesql
    @sql,
    N'@p_tenant_id bigint',
    @p_tenant_id = @tenantId;
```

Schema và table được quote riêng. Tenant ID được bind trong sp_executesql.

Với ORDER BY:

```sql
DECLARE @sortColumn sysname = N'created_at';
DECLARE @direction nvarchar(4) = N'DESC';
DECLARE @sql nvarchar(max);

IF @sortColumn NOT IN (
    N'created_at', N'total_amount', N'order_id'
)
    THROW 50002, 'Unsupported sort column', 1;

IF @direction NOT IN (N'ASC', N'DESC')
    THROW 50003, 'Unsupported sort direction', 1;

SET @sql =
    N'SELECT order_id, created_at, total_amount ' +
    N'FROM dbo.sales_orders ' +
    N'ORDER BY ' + QUOTENAME(@sortColumn) + N' ' +
    @direction + N', order_id ASC';

EXEC sys.sp_executesql @sql;
```

QUOTENAME dùng cho identifier; direction là token cú pháp đã được kiểm tra, không phải identifier. QUOTENAME không thay thế allowlist và có giới hạn độ dài identifier đầu vào.

## 10. MySQL: PREPARE/EXECUTE và identifier

MySQL prepared statement bind giá trị:

```sql
PREPARE stmt FROM
    'SELECT order_id, total_amount
     FROM sales_orders
     WHERE tenant_id = ?
       AND status = ?';

SET @p_tenant_id = 10;
SET @p_status = 'PAID';

EXECUTE stmt USING @p_tenant_id, @p_status;
DEALLOCATE PREPARE stmt;
```

MySQL thường dùng dấu backtick để quote identifier:

```sql
SELECT `order_id`, `total_amount`
FROM `sales_orders`;
```

Các ký hiệu ` quanh identifier trong ví dụ này được chuyển thành dấu backtick trong tệp Markdown. Nếu identifier có backtick bên trong, cần escape theo quy tắc MySQL; không tự bọc mà không xử lý nội dung.

Dynamic identifier phải được allowlist rồi quote/escape theo quy tắc MySQL. Hàm QUOTE(str) của MySQL dùng cho chuỗi literal, **không phải hàm quote identifier**.

Trong stored procedure, nếu cần chọn bảng động, chỉ cho phép tên từ allowlist server-side, quote identifier theo MySQL rồi ghép vào chuỗi PREPARE. Các giá trị như tenant ID vẫn truyền qua placeholder của EXECUTE ... USING. Không nối giá trị request vào chuỗi SQL. PREPARE statement có vòng đời session; cần DEALLOCATE và quản lý trạng thái khi dùng connection pool.

## 11. IN, LIKE và các vị trí dễ nhầm

### 11.1. IN một placeholder không nhận danh sách CSV

```sql
SELECT *
FROM sales_orders
WHERE order_id IN (?);
```

Bind chuỗi 1001,1002,1003 chỉ truyền **một giá trị**, không tự biến thành ba phần tử.

Với JDBC, sinh đúng số dấu hỏi theo số phần tử rồi bind từng ID. Chuỗi ghép chỉ gồm dấu placeholder do code tạo, không chứa dữ liệu. Nếu danh sách rỗng, xử lý rõ ràng thay vì sinh IN ().

PostgreSQL có thể bind một mảng typed:

```sql
SELECT order_id
FROM sales_orders
WHERE order_id = ANY($1::BIGINT[]);
```

Ở đây $1 là giá trị mảng, không phải identifier.

### 11.2. LIKE và wildcard

```sql
SELECT order_id
FROM sales_orders
WHERE customer_name LIKE $1;
```

Bind giá trị an toàn khỏi SQL injection. Nhưng % và _ bên trong giá trị vẫn là wildcard của LIKE. Nếu nghiệp vụ muốn tìm literal, phải escape chúng theo quy tắc LIKE riêng.

### 11.3. Các vị trí cấu trúc khác

Không thể bind tên cột trong SELECT, GROUP BY, JOIN, alias, tên constraint/index/sequence, tên function/operator hoặc token NULLS FIRST/LAST. Khi cần lựa chọn động, map sang cấu trúc do code định nghĩa.

Một JSON path có thể là giá trị truyền vào hàm như jsonb_path_query(document, $1::jsonpath), nếu DBMS hỗ trợ. Đó là tham số của hàm, không phải identifier SQL; vẫn cần kiểm soát path có được phép truy cập trường nhạy cảm hay không.

## 12. Phân trang và giới hạn tài nguyên

PostgreSQL:

```sql
SELECT order_id, created_at, total_amount
FROM sales_orders
WHERE tenant_id = $1
ORDER BY created_at DESC, order_id ASC
LIMIT $2 OFFSET $3;
```

Tenant, limit và offset là giá trị bind. Tên cột và hướng sort vẫn cố định. SQL Server dùng cú pháp phân trang khác:

```sql
SELECT order_id, created_at, total_amount
FROM dbo.sales_orders
WHERE tenant_id = @tenant_id
ORDER BY created_at DESC, order_id ASC
OFFSET @offset ROWS
FETCH NEXT @page_size ROWS ONLY;
```

Dù bind được, limit vẫn cần giới hạn tối đa hợp lý và offset không âm. Offset quá lớn có thể tốn kém; cân nhắc keyset pagination với cursor gồm giá trị sort và khóa tie-breaker.

## 13. Quyền truy cập và dynamic SQL

Quote tên bảng payroll_private đúng cú pháp không chứng minh caller được phép đọc nó. Kiểm tra allowlist theo nghiệp vụ, quyền người gọi, tenant context đáng tin cậy và database privileges.

Không ghép tenant ID từ request thành hậu tố tên bảng. Nếu phải chọn bảng theo tenant, ánh xạ tenant sang đối tượng từ metadata server-side và kiểm tra quyền. Nhiều hệ thống có thể dùng một bảng chung với tenant_id và chính sách phân quyền thay vì hàng nghìn bảng động.

Trong PostgreSQL, tên không schema-qualified phụ thuộc search_path. Với function quyền cao, hãy kiểm soát search_path, dùng schema-qualified object, hạn chế quyền CREATE trong schema đáng tin cậy và review SECURITY DEFINER.

Lỗi SQL chi tiết có thể tiết lộ schema. Trả thông báo validation phù hợp cho client, ghi chi tiết nội bộ có kiểm soát và không gửi raw SQL/stack trace ra ngoài.

## 14. Query builder và ORM

Query builder thường có API tách identifier và value, ví dụ where(column, value) và orderBy(column, direction). Hãy dùng API chuyên biệt của thư viện và vẫn map tên cột theo allowlist.

Tránh truyền request vào các API raw như orderByRaw, whereRaw hoặc selectRaw. Những API này có thể bỏ qua cơ chế quote/bind thông thường.

ORM không xóa bỏ khác biệt giữa DBMS. SQL được sinh ra có thể khác về placeholder, quoting, LIMIT/OFFSET, RETURNING/OUTPUT và cú pháp phân trang. Kiểm tra SQL thực tế được sinh ra khi điều tra lỗi hoặc tối ưu.

## 15. Những lỗi thường gặp

### Lỗi 1 — Dùng placeholder cho tên bảng

FROM ? không thay placeholder bằng relation name. Identifier phải được compose riêng.

### Lỗi 2 — Dùng placeholder cho tên cột

SELECT ? thường trả một giá trị hằng, không chọn cột có tên bằng giá trị bind.

### Lỗi 3 — Dùng placeholder cho ASC/DESC

Hướng sort là token grammar, không phải giá trị dữ liệu.

### Lỗi 4 — Nghĩ PreparedStatement an toàn dù nối raw SQL

PreparedStatement bảo vệ các placeholder, không sửa chuỗi raw đã nối từ request trước đó.

### Lỗi 5 — Nối sortBy trực tiếp

Map khóa API sang tên cột cố định, không nối raw input.

### Lỗi 6 — Validate direction nhưng vẫn dùng chuỗi gốc

Sau validation phải dùng token hằng đã chuẩn hóa ASC hoặc DESC.

### Lỗi 7 — Quote identifier rồi bỏ qua allowlist

Quote bảo vệ grammar, không quyết định đối tượng được phép truy cập.

### Lỗi 8 — Quote schema.table như một identifier

format('%I','archive.sales_orders') quote một tên đơn có dấu chấm. Dùng format('%I.%I', schema, table).

### Lỗi 9 — Dùng %s cho input không tin cậy

%s chèn nguyên văn. Dùng %I cho identifier và USING cho giá trị.

### Lỗi 10 — Dùng %L thay USING mọi lúc

%L quote literal, nhưng USING thường phù hợp hơn cho giá trị trong PL/pgSQL dynamic SQL.

### Lỗi 11 — Dùng %I cho ASC/DESC

"DESC" là identifier, không phải token hướng sort. Validate và dùng token cố định.

### Lỗi 12 — Tự quote bằng cách thêm dấu nháy

Identifier có delimiter bên trong có thể phá chuỗi. Dùng API quote chuyên dụng và allowlist.

### Lỗi 13 — Nghĩ identifier quoting cấp quyền

Quote đúng không thay thế quyền nghiệp vụ/database.

### Lỗi 14 — Bind danh sách IN thành một chuỗi

Một placeholder là một giá trị. Sinh placeholder theo số phần tử hoặc dùng array/table-valued parameter.

### Lỗi 15 — Sinh IN () khi danh sách rỗng

Xử lý danh sách rỗng rõ ràng; không giả định mọi DBMS chấp nhận cú pháp này.

### Lỗi 16 — Nhầm wildcard LIKE với injection

Bind ngăn thay đổi grammar SQL; escape LIKE kiểm soát wildcard bên trong pattern.

### Lỗi 17 — Cho phép mọi cột vì cột đó tồn tại

Chỉ cho phép cột phù hợp hợp đồng API và quyền người dùng.

### Lỗi 18 — Không thêm tie-breaker

Nhiều hàng cùng giá trị sort cần khóa phụ duy nhất để phân trang ổn định.

### Lỗi 19 — Cho limit không giới hạn

Bind không ngăn lạm dụng tài nguyên. Validate limit/offset.

### Lỗi 20 — Dùng tên bảng động từ tenant ID

Ánh xạ server-side và kiểm tra quyền; không nối input thành tên bảng.

### Lỗi 21 — Tin ORM tự bảo vệ raw fragment

Không truyền request trực tiếp vào orderByRaw/whereRaw/selectRaw.

### Lỗi 22 — Không kiểm soát search_path trong function quyền cao

Schema qualification và search_path an toàn quan trọng với dynamic SQL có quyền cao.

### Lỗi 23 — Dùng QUOTE của MySQL cho identifier

QUOTE() xử lý literal string, không quote tên bảng/cột.

### Lỗi 24 — Nghĩ QUOTENAME thay allowlist

QUOTENAME quote identifier, không chứng minh caller được chọn đối tượng.

### Lỗi 25 — Nối giá trị tenant vào dynamic SQL

Ngay cả số nguyên cũng nên truyền qua USING hoặc sp_executesql parameters.

### Lỗi 26 — Không test ký tự đặc biệt

Test tên trùng keyword, dấu nháy, dấu chấm, backtick, Unicode và payload độc hại.

## 16. Bài tập thực hành có đáp án

### Bài 1 — Phân loại tenant_id

Trong WHERE tenant_id = $1, $1 là cấu trúc hay giá trị?

**Đáp án:** Giá trị dữ liệu; có thể bind tenant ID.

### Bài 2 — Tên bảng

Có thể viết FROM $1 rồi bind sales_orders trong PostgreSQL không?

**Đáp án:** Không. $1 là biểu thức giá trị, không phải identifier.

### Bài 3 — Tên cột

Bind total_amount vào SELECT ? FROM sales_orders có lấy cột đó không?

**Đáp án:** Không. Nó thường trả chuỗi total_amount cho mỗi hàng.

### Bài 4 — Hướng sort

Có thể bind DESC vào ORDER BY created_at ? không?

**Đáp án:** Không. Validate direction thành ASC/DESC rồi dùng token cố định.

### Bài 5 — Giá trị status

Viết JDBC an toàn cho WHERE status = ?.

```java
PreparedStatement ps = connection.prepareStatement(
    "SELECT order_id FROM sales_orders WHERE status = ?"
);
ps.setString(1, status);
```

**Đáp án:** status được bind riêng.

### Bài 6 — Allowlist sort key

API nhận total. Ánh xạ sang cột nào?

**Đáp án:** Theo map server-side, ví dụ total → total_amount.

### Bài 7 — Cột nhạy cảm

API nhận password_hash nhưng cột đó tồn tại. Có nên cho phép?

**Đáp án:** Không nếu không nằm trong danh sách được công khai.

### Bài 8 — Direction hợp lệ

**Đáp án:** ASC và DESC; mọi giá trị khác phải từ chối.

### Bài 9 — Quote schema/table PostgreSQL

```sql
format('%I.%I', 'archive', 'sales_orders_2025')
```

**Đáp án:** quote hai identifier riêng biệt.

### Bài 10 — Sai một %I

Tại sao format('%I','archive.sales_orders') không giống %I.%I?

**Đáp án:** %I đầu quote một identifier đơn chứa dấu chấm.

### Bài 11 — %I hay %L?

**Đáp án:** %I cho identifier; bind giá trị qua USING khi có thể. %L quote literal khi cần nhúng.

### Bài 12 — %s có an toàn?

**Đáp án:** Không cho input thô; %s chèn nguyên văn.

### Bài 13 — Dynamic SQL PostgreSQL

```sql
v_sql := format(
    'SELECT count(*) FROM %I.%I WHERE tenant_id = $1',
    p_schema, p_table
);
EXECUTE v_sql INTO v_count USING p_tenant_id;
```

**Đáp án:** quote identifier riêng, bind tenant và allowlist cặp schema/table.

### Bài 14 — LIMIT

PostgreSQL có thể dùng LIMIT $1 OFFSET $2 không?

**Đáp án:** Có; đây là giá trị số, vẫn cần validation.

### Bài 15 — IN một placeholder

IN (?) bind "1001,1002" có phải hai ID không?

**Đáp án:** Không, đó là một giá trị. Sinh hai placeholder hoặc dùng array.

### Bài 16 — ANY

```sql
WHERE order_id = ANY($1::BIGINT[])
```

**Đáp án:** $1 là giá trị mảng, không phải identifier.

### Bài 17 — QUOTENAME

QUOTENAME(@tableName) có thay thế allowlist không?

**Đáp án:** Không. Nó quote identifier, không cấp quyền.

### Bài 18 — sp_executesql

Tenant ID nên nối vào chuỗi hay truyền qua tham số?

**Đáp án:** Truyền qua tham số sp_executesql.

### Bài 19 — MySQL identifier

MySQL thường quote identifier bằng gì?

**Đáp án:** Backtick. QUOTE() dành cho chuỗi literal.

### Bài 20 — LIKE wildcard

Bind %admin% vào LIKE ? có phải injection?

**Đáp án:** Không phải SQL injection do parameter binding, nhưng % vẫn là wildcard LIKE.

### Bài 21 — ORDER BY hằng

ORDER BY ? bind created_at có sắp theo cột không?

**Đáp án:** Không; nó là biểu thức giá trị hằng.

### Bài 22 — Alias

Có thể bind alias bằng AS ? không?

**Đáp án:** Không. Alias là cấu trúc SQL; dùng tên cố định/map.

### Bài 23 — Dynamic schema

Có nên truyền archive.sales_orders thẳng vào một %I không?

**Đáp án:** Không nếu muốn schema và table riêng. Dùng %I.%I sau allowlist.

### Bài 24 — ASC; DROP

API nhận ASC; DROP TABLE ... khi chỉ cho ASC/DESC. Xử lý thế nào?

**Đáp án:** Từ chối vì không khớp allowlist.

### Bài 25 — Quote và quyền

Một bảng payroll được quote đúng. Người dùng thường có được đọc không?

**Đáp án:** Chỉ khi quyền nghiệp vụ và database cho phép.

## 17. Bảng ghi nhớ nhanh

| Thành phần | Cách xử lý an toàn |
|---|---|
| Giá trị ID, status, email, ngày | Bind parameter |
| LIMIT/OFFSET | Bind khi DB/driver hỗ trợ; validate |
| Danh sách IN | Sinh placeholder hoặc array/table-valued parameter |
| Tên schema/bảng/cột | Allowlist + identifier quoting |
| ASC/DESC | Allowlist/enum và token cố định |
| NULLS FIRST/LAST | Allowlist hoặc cố định |
| Biểu thức ORDER BY | Map sang biểu thức do code định nghĩa |
| PostgreSQL identifier | format('%I') hoặc API Identifier |
| PostgreSQL giá trị dynamic | EXECUTE ... USING |
| PostgreSQL schema.table | format('%I.%I') |
| SQL Server identifier | QUOTENAME + allowlist |
| SQL Server giá trị | sp_executesql parameters |
| MySQL identifier | Backtick đúng quy tắc + allowlist |
| Java JDBC | PreparedStatement cho giá trị; map identifier |
| Python psycopg | sql.Identifier cho identifier; params cho giá trị |
| ORM | API identifier/value riêng; tránh raw fragment |
| Tên hợp lệ nhưng không được phép | Từ chối theo authorization |
| Function quyền cao | Schema qualification, search_path an toàn, quyền tối thiểu |

## Kết luận

**Parameter binding bảo vệ giá trị dữ liệu, nhưng không thay thế tên bảng, tên cột hoặc token cú pháp SQL.** Database cần biết cấu trúc câu lệnh trước, sau đó mới nhận các giá trị được gắn vào vị trí biểu thức.

Khi cần cấu trúc truy vấn động:

- **Giá trị luôn bind khi có thể**: tenant ID, status, thời gian, ID, search term, limit và offset.
- **Tên bảng, schema và cột phải được chọn từ allowlist** do ứng dụng/server định nghĩa; quote đúng theo DBMS bằng %I, QUOTENAME, sql.Identifier hoặc API tương ứng.
- **ASC/DESC và token grammar khác phải được validate thành lựa chọn cố định**; không dùng placeholder hay quote identifier cho hướng sắp xếp.
- **Quote identifier không phải authorization**: tên được quote đúng vẫn có thể là đối tượng người gọi không được phép truy cập.
- **Dynamic SQL phải tách cấu trúc khỏi giá trị**: PostgreSQL dùng format + EXECUTE ... USING, SQL Server dùng QUOTENAME + sp_executesql, còn driver/ORM có API composition riêng.
- **SQL tĩnh/query builder thường tốt hơn** khi chỉ có một số ít cấu trúc được hỗ trợ. Chỉ dùng dynamic SQL khi thực sự cần thay đổi identifier hoặc đối tượng.

Thói quen cần giữ là **không nối dữ liệu người dùng vào SQL, không nhận raw identifier hoặc raw expression từ client, và không nhầm quote với quyền truy cập**. Khi ranh giới giữa cấu trúc và giá trị được giữ rõ ràng, truy vấn động có thể linh hoạt mà vẫn kiểm soát được injection, phạm vi dữ liệu và quyền thực thi.
