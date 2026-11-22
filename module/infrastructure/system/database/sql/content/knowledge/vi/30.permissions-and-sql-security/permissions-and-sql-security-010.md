# SQL động trong routine và cơ chế thực thi theo phương ngữ

**SQL động** (*dynamic SQL*) là câu SQL được tạo thành chuỗi khi chương trình đang chạy rồi được database phân tích và thực thi. SQL tĩnh có cấu trúc được viết sẵn; SQL động cho phép thay đổi một phần cấu trúc theo metadata hoặc lựa chọn hợp lệ của nghiệp vụ.

Ví dụ, một routine báo cáo cần đọc một trong các bảng lịch sử theo năm. Tên bảng có thể thay đổi giữa các lần gọi, còn mã khách hàng và khoảng ngày vẫn là **giá trị dữ liệu**. Thiết kế an toàn phải tách hai nhóm này: identifier được chọn từ allowlist và quote đúng theo DBMS; value được truyền bằng bind parameter.

Bài thuộc **Database SQL → Quyền và SQL an toàn → SQL động trong routine và cơ chế thực thi theo phương ngữ**. Nội dung tập trung vào PostgreSQL, SQL Server, MySQL, Oracle và SQLite: cú pháp thực thi, bind, identifier động, quyền routine, transaction, plan cache và SQL injection.

## 1. SQL tĩnh và SQL động

SQL tĩnh có cấu trúc cố định:

```sql
SELECT order_id, placed_at, total_amount
FROM orders
WHERE customer_id = :customer_id
  AND status = :status
ORDER BY placed_at DESC;
```

Nếu chỉ thay customer_id hoặc status, không cần SQL động. Driver hoặc routine bind giá trị vào câu lệnh đã có cấu trúc.

SQL động hữu ích khi **cấu trúc thật sự thay đổi**, ví dụ:

- Chọn một bảng trong nhóm bảng archive theo năm.
- Chọn cột sort trong một tập cột được phép.
- Tạo danh sách cột pivot thay đổi theo dữ liệu.
- Tạo DDL từ metadata tin cậy trong công cụ quản trị.
- Chạy một truy vấn báo cáo có tập biểu thức đã được cấu hình.

| Nhu cầu | Cách tiếp cận thường phù hợp |
| --- | --- |
| Thay customer_id, status, ngày | SQL tĩnh + bind |
| Thay tên bảng/schema | SQL động + allowlist + quote identifier |
| Thay tên cột sort | Allowlist cột + quote identifier |
| Thay ASC/DESC | Chọn từ hai hằng số cố định |
| Danh sách giá trị có số phần tử thay đổi | Array/table-valued parameter/temp table hoặc bind từng phần tử |
| Chỉ muốn né bind parameter | Không nên dùng SQL động vì lý do này |

SQL động không tự thân nguy hiểm. Rủi ro xuất hiện khi chương trình ghép dữ liệu không tin cậy vào cấu trúc SQL hoặc thực thi câu lệnh bằng quyền quá rộng.

## 2. Phân biệt value và identifier

Trong câu:

```sql
SELECT total_amount
FROM orders_2026
WHERE customer_id = 101
ORDER BY placed_at DESC;
```

- orders_2026 là identifier của bảng.
- total_amount, customer_id và placed_at là identifier của cột.
- 101 là value.
- SELECT, WHERE, ORDER BY và DESC là cú pháp SQL.

**Bind parameter thay value, không thay identifier.** Câu kiểu SELECT * FROM ? WHERE customer_id = ? không thể dùng placeholder đầu tiên làm tên bảng. Database hiểu placeholder là một giá trị, không phải một mảnh cú pháp.

Quy trình đúng khi tên bảng thay đổi:

1. Nhận lựa chọn nghiệp vụ, ví dụ năm báo cáo.
2. Map lựa chọn đó sang tên bảng từ allowlist phía server.
3. Quote identifier theo quy tắc của DBMS.
4. Tạo SQL template với tên bảng đã được kiểm soát.
5. Bind mọi giá trị như customer_id, status, date range.
6. Thực thi với quyền tối thiểu.

Quote identifier không thay thế allowlist. Một tên bảng có thể quote đúng cú pháp nhưng vẫn là bảng nhạy cảm mà người gọi không được quyền chọn.

## 3. SQL injection và bind parameter

Cách nối chuỗi nguy hiểm:

```text
sql = "SELECT * FROM users WHERE username = '" + input + "'";
```

Nếu input chứa dấu nháy và cú pháp SQL, nó có thể làm thay đổi cấu trúc câu lệnh. Hậu quả có thể là bỏ qua xác thực, đọc dữ liệu ngoài phạm vi, sửa/xóa dữ liệu hoặc gọi routine khác.

Dùng bind:

```sql
SELECT user_id, username
FROM users
WHERE username = ?;
```

Driver truyền input riêng khỏi SQL text. Dấu nháy và từ khóa bên trong input được coi là dữ liệu.

Các nguyên tắc:

- Bind mọi value thay vì tự escape chuỗi.
- Không nhận nguyên fragment WHERE, JOIN, ORDER BY hoặc biểu thức SQL từ người dùng.
- Không ghép input vào tên bảng/cột.
- Identifier động phải đến từ allowlist phía server.
- Log theo fingerprint/correlation ID; không ghi secret hoặc PII không cần thiết.

## 4. Quote identifier và allowlist

Mỗi DBMS có quy tắc quote identifier khác nhau:

| DBMS | Cơ chế thường dùng |
| --- | --- |
| PostgreSQL | format với %I |
| SQL Server | QUOTENAME |
| MySQL | Backtick theo quy tắc identifier của MySQL |
| Oracle | Quote identifier theo quy tắc Oracle; DBMS_ASSERT hỗ trợ kiểm tra/quote |
| SQLite | Dấu ngoặc kép cho identifier |

Nếu có schema và table, quote từng phần riêng rồi nối dấu chấm. Không quote cả chuỗi schema.table như một identifier duy nhất.

Ví dụ ý tưởng:

```text
schema = allowlisted_schema
table  = allowlisted_table
sql = "SELECT ... FROM " + quote(schema) + "." + quote(table)
bind(customer_id)
```

Allowlist trả lời câu hỏi “người gọi được chọn đối tượng nào?”. Quote identifier trả lời câu hỏi “đưa tên đã chọn vào câu SQL sao cho parser hiểu đúng?”. Cần cả hai.

---

## 5. PostgreSQL: EXECUTE trong PL/pgSQL

PL/pgSQL dùng EXECUTE để chạy command string:

```sql
EXECUTE command_string
[ INTO [STRICT] target ]
[ USING expression [, ...] ];
```

Trong command string, placeholder bind viết bằng $1, $2, ...; giá trị được truyền qua USING.

### 5.1. Bind value

```sql
CREATE OR REPLACE FUNCTION lab_customer_total_382(
    p_customer_id INTEGER
)
RETURNS NUMERIC
LANGUAGE plpgsql
AS $$
DECLARE
    v_total NUMERIC;
BEGIN
    EXECUTE
        'SELECT COALESCE(SUM(total_amount), 0)
         FROM orders
         WHERE customer_id = $1'
    INTO v_total
    USING p_customer_id;

    RETURN v_total;
END;
$$;
```

Đây là ví dụ dynamic SQL có bind. Nếu cấu trúc câu không đổi, SELECT tĩnh trong PL/pgSQL thường ngắn gọn và dễ kiểm tra hơn.

### 5.2. Tên bảng động, value vẫn bind

```sql
CREATE OR REPLACE FUNCTION lab_year_total_382(
    p_year INTEGER,
    p_customer_id INTEGER
)
RETURNS NUMERIC
LANGUAGE plpgsql
AS $$
DECLARE
    v_table_name TEXT;
    v_total NUMERIC;
BEGIN
    CASE p_year
        WHEN 2024 THEN v_table_name := 'orders_2024';
        WHEN 2025 THEN v_table_name := 'orders_2025';
        WHEN 2026 THEN v_table_name := 'orders_2026';
        ELSE
            RAISE EXCEPTION 'Năm không được hỗ trợ: %', p_year;
    END CASE;

    EXECUTE format(
        'SELECT COALESCE(SUM(total_amount), 0)
         FROM %I
         WHERE customer_id = $1',
        v_table_name
    )
    INTO v_total
    USING p_customer_id;

    RETURN v_total;
END;
$$;
```

CASE là allowlist. format('%I', ...) quote identifier. Customer ID vẫn được bind bằng USING.

Nếu bảng thuộc schema reporting, quote riêng hai phần:

```sql
format('%I.%I', 'reporting', v_table_name)
```

Không dùng format('%I', 'reporting.orders_2026'), vì nó quote toàn chuỗi thành một identifier duy nhất.

### 5.3. format: %I, %L và %s

| Placeholder | Ý nghĩa |
| --- | --- |
| %I | Quote identifier |
| %L | Quote SQL literal |
| %s | Chèn chuỗi nguyên dạng, không tự escape |

Ưu tiên USING cho value. %L hữu ích trong một số ngữ cảnh không thể bind, nhưng không nên ghép mọi giá trị thành literal. Không đưa chuỗi người dùng vào %s.

### 5.4. INTO STRICT và RETURN QUERY EXECUTE

INTO STRICT yêu cầu SELECT trả đúng một hàng; 0 hoặc nhiều hơn một hàng sẽ phát lỗi:

```sql
EXECUTE
    'SELECT email FROM staff WHERE staff_id = $1'
INTO STRICT v_email
USING p_staff_id;
```

Hàm trả tập hàng có thể dùng:

```sql
RETURN QUERY EXECUTE
    'SELECT order_id, total_amount
     FROM orders
     WHERE customer_id = $1'
USING p_customer_id;
```

### 5.5. Kế hoạch thực thi

SQL tĩnh trong PL/pgSQL có cơ chế chuẩn bị/tái sử dụng kế hoạch theo quy tắc PL/pgSQL. EXECUTE với command string được phân tích và lập kế hoạch lại mỗi lần chạy. Điều này hữu ích khi cấu trúc thay đổi hoặc cần kế hoạch theo tham số hiện tại, nhưng có chi phí parse/plan lặp lại. Đo trước khi chọn dynamic EXECUTE chỉ để thay đổi hành vi plan.

### 5.6. SECURITY DEFINER

PostgreSQL function thông thường mặc định dùng quyền invoker. SECURITY DEFINER chạy theo quyền owner trong phạm vi routine:

```sql
CREATE OR REPLACE FUNCTION reporting.read_customer_total(
    p_customer_id INTEGER
)
RETURNS NUMERIC
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, reporting
AS $$
DECLARE
    v_total NUMERIC;
BEGIN
    SELECT COALESCE(SUM(total_amount), 0)
    INTO v_total
    FROM reporting.orders
    WHERE customer_id = p_customer_id;

    RETURN v_total;
END;
$$;
```

Khi dùng SECURITY DEFINER:

- Giới hạn quyền EXECUTE và quyền owner.
- Qualify schema cho đối tượng quan trọng.
- Cố định search_path an toàn.
- Không nhận raw SQL fragment hoặc tên object tùy ý.
- Nếu có identifier động, allowlist phải nằm phía server và được kiểm soát trong routine.

Một routine quyền cao có thể trở thành cầu vượt quyền nếu caller điều khiển được bảng hoặc câu SQL được thực thi.

---

## 6. SQL Server: EXEC và sp_executesql

SQL Server hỗ trợ EXEC/EXECUTE với chuỗi và sys.sp_executesql. Khi cần truyền tham số, sp_executesql thường phù hợp hơn vì batch có thể khai báo kiểu tham số và hỗ trợ plan reuse.

### 6.1. EXEC chuỗi

```sql
DECLARE @sql NVARCHAR(MAX);

SET @sql = N'
    SELECT order_id, total_amount
    FROM dbo.Orders
    WHERE customer_id = 101;
';

EXEC(@sql);
```

Ví dụ chạy được nhưng literal 101 đã ghép vào SQL. Không dùng cách này với value do người dùng gửi.

### 6.2. sp_executesql với tham số

```sql
DECLARE @sql NVARCHAR(MAX);

SET @sql = N'
    SELECT order_id, total_amount
    FROM dbo.Orders
    WHERE customer_id = @customer_id
      AND status = @status;
';

EXEC sys.sp_executesql
    @sql,
    N'@customer_id INT, @status NVARCHAR(20)',
    @customer_id = 101,
    @status = N'PAID';
```

Các phần:

1. @sql là batch.
2. Chuỗi thứ hai khai báo tên và kiểu tham số.
3. Các đối số sau truyền giá trị theo tên.

Giá trị được truyền tách khỏi SQL text.

### 6.3. OUTPUT parameter

```sql
DECLARE @sql NVARCHAR(MAX);
DECLARE @total DECIMAL(18, 2);

SET @sql = N'
    SELECT @result = COALESCE(SUM(total_amount), 0)
    FROM dbo.Orders
    WHERE customer_id = @customer_id;
';

EXEC sys.sp_executesql
    @sql,
    N'@customer_id INT, @result DECIMAL(18,2) OUTPUT',
    @customer_id = 101,
    @result = @total OUTPUT;

SELECT @total AS total_amount;
```

OUTPUT phải được khai báo trong định nghĩa tham số của batch và đánh dấu khi truyền biến bên ngoài.

### 6.4. QUOTENAME cho identifier

Không thể bind tên bảng bằng biến value. Nếu bảng được chọn từ allowlist:

```sql
DECLARE @table_name SYSNAME;
DECLARE @sql NVARCHAR(MAX);

SET @table_name =
    CASE @year
        WHEN 2024 THEN N'Orders_2024'
        WHEN 2025 THEN N'Orders_2025'
        WHEN 2026 THEN N'Orders_2026'
        ELSE NULL
    END;

IF @table_name IS NULL
    THROW 50001, 'Năm không được hỗ trợ', 1;

SET @sql =
    N'SELECT order_id, total_amount
      FROM dbo.' + QUOTENAME(@table_name) + N'
      WHERE customer_id = @customer_id;';

EXEC sys.sp_executesql
    @sql,
    N'@customer_id INT',
    @customer_id = 101;
```

Nếu schema cũng thay đổi, quote riêng từng phần:

```sql
QUOTENAME(@schema_name) + N'.' + QUOTENAME(@table_name)
```

QUOTENAME có giới hạn đầu vào theo độ dài identifier SQL Server (thông thường tối đa 128 ký tự); input quá dài có thể trả NULL. Kiểm tra kết quả và vẫn dùng allowlist: quote đúng không có nghĩa caller được quyền chọn bảng đó.

### 6.5. Scope và plan cache

Batch sp_executesql có scope riêng; biến bên ngoài không tự xuất hiện bên trong. Phải khai báo tham số và truyền giá trị.

Khi text và định nghĩa tham số ổn định, SQL Server có thể tái sử dụng execution plan. Nhưng parameter sniffing và data skew có thể làm một plan không phù hợp mọi giá trị. Đo Query Store/actual plan trước khi can thiệp.

### 6.6. Quyền

Dynamic SQL có thể làm thay đổi cách ownership chaining áp dụng so với SQL tĩnh trong module. Một procedure chạy được câu SQL tĩnh không có nghĩa dynamic batch tự động có cùng quyền truy cập. SQL Server có EXECUTE AS và module signing/certificate signing cho các thiết kế nâng quyền có chủ đích. Không dùng sysadmin làm cách chữa lỗi permission.

---

## 7. MySQL: PREPARE, EXECUTE và DEALLOCATE PREPARE

MySQL dùng prepared statement ở cấp SQL:

```sql
PREPARE stmt_name FROM @sql_text;
EXECUTE stmt_name USING @param1, @param2;
DEALLOCATE PREPARE stmt_name;
```

Ví dụ:

```sql
SET @sql_text = '
    SELECT order_id, total_amount
    FROM orders
    WHERE customer_id = ?
      AND status = ?
';

SET @p_customer_id = 101;
SET @p_status = 'PAID';

PREPARE stmt_orders FROM @sql_text;
EXECUTE stmt_orders USING @p_customer_id, @p_status;
DEALLOCATE PREPARE stmt_orders;
```

Dấu ? là placeholder theo vị trí. USING truyền user variables tương ứng.

### 7.1. Trong stored procedure

MySQL cho phép SQL prepared statements trong stored procedure. Có các giới hạn quan trọng:

- Prepared statement có scope theo session.
- Chuỗi PREPARE thường lấy từ literal hoặc user variable.
- Không thể tham chiếu trực tiếp local variable/parameter của routine trong prepared SQL như một câu SQL tĩnh.
- Thường copy parameter routine sang user variables trước khi EXECUTE.
- PREPARE không được dùng trong stored function hoặc trigger theo quy tắc MySQL.

Ví dụ:

```sql
DELIMITER $$

CREATE PROCEDURE lab_find_orders_382(
    IN p_customer_id INT,
    IN p_status VARCHAR(20)
)
BEGIN
    SET @sql_text = '
        SELECT order_id, total_amount
        FROM orders
        WHERE customer_id = ?
          AND status = ?
    ';

    SET @p1 = p_customer_id;
    SET @p2 = p_status;

    PREPARE stmt_orders FROM @sql_text;
    EXECUTE stmt_orders USING @p1, @p2;
    DEALLOCATE PREPARE stmt_orders;
END$$

DELIMITER ;
```

Bảng orders cần tồn tại với các cột tương ứng. DELIMITER là lệnh của client để nhập định nghĩa routine nhiều câu; không phải câu lệnh server được thực thi như SELECT.

### 7.2. Session variables và cleanup

User variables như @p1 có scope theo session, nên có thể còn tồn tại khi procedure kết thúc. Với connection pool, trạng thái session có thể được tái sử dụng.

Nếu EXECUTE lỗi trước DEALLOCATE, prepared statement có thể còn trong session. Routine thực tế nên có handler cleanup khi đã PREPARE, reset user variables cần thiết và RESIGNAL để caller biết lỗi. Tên prepared statement cũng cần tránh xung đột trong cùng session.

### 7.3. Identifier động

Dấu ? không thay tên bảng/cột. Chọn identifier từ allowlist rồi quote theo quy tắc MySQL (backtick); không nối raw tên do người dùng gửi.

MySQL không có INSTEAD OF trigger cho view; và không phải mọi statement đều được hỗ trợ trong PREPARE. Kiểm tra phiên bản và danh sách statement được hỗ trợ trước khi triển khai.

### 7.4. SQL SECURITY

Stored routine MySQL có SQL SECURITY DEFINER hoặc INVOKER. Khi dùng DEFINER, review account định nghĩa, quyền EXECUTE của caller, quyền trên object và mọi identifier động. Không cho caller chọn schema/tenant ngoài mục đích nghiệp vụ.

---

## 8. Oracle: EXECUTE IMMEDIATE và Native Dynamic SQL

Oracle PL/SQL hỗ trợ Native Dynamic SQL (NDS) qua EXECUTE IMMEDIATE:

```sql
EXECUTE IMMEDIATE dynamic_string
    [INTO ...]
    [USING ...]
    [RETURNING INTO ...];
```

### 8.1. SELECT một hàng

```sql
DECLARE
    v_total NUMBER;
    v_customer_id NUMBER := 101;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT NVL(SUM(total_amount), 0)
         FROM orders
         WHERE customer_id = :1'
    INTO v_total
    USING v_customer_id;

    DBMS_OUTPUT.PUT_LINE(v_total);
END;
/
```

INTO nhận kết quả, USING truyền bind. Trong SQL statement động thông thường, bind placeholders được gắn theo vị trí.

### 8.2. Dynamic DML

```sql
DECLARE
    v_customer_id NUMBER := 101;
    v_status VARCHAR2(20) := 'PAID';
BEGIN
    EXECUTE IMMEDIATE
        'UPDATE orders
         SET status = :1
         WHERE customer_id = :2'
    USING v_status, v_customer_id;
END;
/
```

Thứ tự USING phải khớp thứ tự placeholder theo ngữ cảnh. Dynamic PL/SQL block và CALL có quy tắc binding theo tên trong những trường hợp tương ứng; đừng suy rộng quy tắc của SQL statement sang mọi loại dynamic statement.

### 8.3. RETURNING INTO và DDL

DML động có thể dùng RETURNING INTO để nhận giá trị được tạo/cập nhật theo cú pháp Oracle phù hợp. DDL động thường dùng EXECUTE IMMEDIATE:

```sql
BEGIN
    EXECUTE IMMEDIATE
        'CREATE TABLE lab_archive_382 (
            id NUMBER PRIMARY KEY,
            payload CLOB
        )';
END;
/
```

Nhiều DDL trong Oracle có implicit commit trước/sau thao tác. Không giả định ROLLBACK sẽ hoàn tác DDL giống UPDATE.

### 8.4. Identifier động và DBMS_ASSERT

Không thể bind tên bảng bằng USING. Oracle có package DBMS_ASSERT hỗ trợ kiểm tra/quote tên SQL:

- SIMPLE_SQL_NAME kiểm tra tên SQL đơn giản.
- QUALIFIED_SQL_NAME kiểm tra tên đủ điều kiện theo quy tắc.
- SQL_OBJECT_NAME kiểm tra tên object SQL.
- ENQUOTE_NAME và ENQUOTE_LITERAL hỗ trợ quote identifier/literal theo ngữ cảnh.

Ví dụ:

```sql
v_sql :=
    'SELECT COUNT(*) FROM ' ||
    DBMS_ASSERT.SQL_OBJECT_NAME(v_object_name) ||
    ' WHERE customer_id = :1';

EXECUTE IMMEDIATE v_sql
INTO v_count
USING p_customer_id;
```

DBMS_ASSERT không thay thế allowlist nghiệp vụ. Một object có tên hợp lệ vẫn có thể là object mà caller không được phép chọn.

### 8.5. DBMS_SQL khi result set không biết trước

EXECUTE IMMEDIATE phù hợp khi số cột và kiểu kết quả đã biết. Khi công cụ báo cáo cần xử lý số cột/kiểu chưa biết trước, DBMS_SQL cung cấp API cấp thấp:

```text
OPEN_CURSOR
    ↓
PARSE
    ↓
BIND_VARIABLE
    ↓
DESCRIBE_COLUMNS
    ↓
DEFINE_COLUMN
    ↓
EXECUTE / FETCH_ROWS
    ↓
COLUMN_VALUE
    ↓
CLOSE_CURSOR
```

DBMS_SQL cần quản lý cursor, kiểu dữ liệu và cleanup exception cẩn thận. Không dùng nó cho SELECT đơn giản mà NDS đã giải quyết được.

### 8.6. AUTHID DEFINER và CURRENT_USER

Oracle PL/SQL có definer's rights và invoker's rights. AUTHID CURRENT_USER chọn ngữ cảnh quyền invoker trong phạm vi quy tắc Oracle; definer rights chạy theo quyền chủ sở hữu routine.

Dynamic SQL trong routine quyền cao cần allowlist, bind value, giới hạn quyền và review kỹ. AUTHID thay đổi principal dùng để kiểm tra quyền, không tự ngăn SQL injection.

---

## 9. SQLite: dynamic SQL ở host application

SQLite là database nhúng. SQLite core không cung cấp stored procedure SQL native như PL/SQL, T-SQL hoặc MySQL stored procedure. SQL động thường được xây dựng ở ứng dụng bằng prepared statement API.

Lifecycle C thường gặp:

```text
sqlite3_prepare_v2
        ↓
sqlite3_bind_*
        ↓
sqlite3_step
        ↓
đọc hàng
        ↓
sqlite3_finalize
```

Ví dụ C:

```c
sqlite3_stmt *stmt = NULL;

const char *sql =
    "SELECT order_id, total_amount "
    "FROM orders "
    "WHERE customer_id = ?1 "
    "AND status = ?2";

int rc = sqlite3_prepare_v2(
    db, sql, -1, &stmt, NULL
);

if (rc == SQLITE_OK) {
    sqlite3_bind_int(stmt, 1, 101);
    sqlite3_bind_text(
        stmt, 2, "PAID", -1, SQLITE_TRANSIENT
    );

    while ((rc = sqlite3_step(stmt)) == SQLITE_ROW) {
        /* Đọc các cột từ hàng kết quả */
    }
}

sqlite3_finalize(stmt);
```

Đây là khung minh họa; ứng dụng thật cần kiểm tra lỗi ở prepare, bind, step và giải phóng statement đúng cách.

Python sqlite3:

```python
sql = """
SELECT order_id, total_amount
FROM orders
WHERE customer_id = ?
  AND status = ?
"""

rows = connection.execute(
    sql,
    (101, "PAID")
).fetchall()
```

Java JDBC:

```java
String sql = """
    SELECT order_id, total_amount
    FROM orders
    WHERE customer_id = ?
      AND status = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, 101);
    ps.setString(2, "PAID");

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            BigDecimal total = rs.getBigDecimal("total_amount");
        }
    }
}
```

Trong SQLite, dấu ? chỉ bind value, không bind tên bảng. Identifier động phải đến từ allowlist của ứng dụng, quote theo quy tắc SQLite và được ghép vào template. SQLite có trigger DML nhưng trigger không phải stored procedure và không cung cấp EXECUTE IMMEDIATE tổng quát để chạy chuỗi SQL tùy ý bên trong trigger.

---

## 10. Bảng so sánh cơ chế theo phương ngữ

| DBMS | Thực thi SQL động | Bind value | Identifier động | Mô hình routine |
| --- | --- | --- | --- | --- |
| PostgreSQL | PL/pgSQL EXECUTE | USING với $1, $2 | format('%I', ...) + allowlist | Function/procedure |
| SQL Server | sp_executesql hoặc EXEC(@sql) | Tham số khai báo trong sp_executesql | QUOTENAME + allowlist | T-SQL stored procedure/function, theo giới hạn ngữ cảnh |
| MySQL | PREPARE/EXECUTE/DEALLOCATE | ? + user variables | Allowlist + quote identifier | Stored procedure; PREPARE không dùng trong function/trigger |
| Oracle | EXECUTE IMMEDIATE, OPEN FOR, DBMS_SQL | USING | Allowlist + DBMS_ASSERT/quote | PL/SQL procedure/function/package |
| SQLite | API prepare/bind/step | ?, ?NNN, :name tùy API | Allowlist + quote identifier | Không có stored procedure SQL native |

Placeholder và lifecycle khác nhau. Không copy nguyên cú pháp một hệ sang hệ khác chỉ bằng đổi dấu placeholder.

---

## 11. Dynamic ORDER BY và danh sách IN

### 11.1. ORDER BY động

Không thể bind tên cột hoặc keyword:

```sql
ORDER BY ? ?
```

Thay vào đó, map lựa chọn sang giá trị cố định:

```text
sort = "date"  → column = placed_at
sort = "total" → column = total_amount
direction = "asc"  → ASC
direction = "desc" → DESC
```

Ví dụ PostgreSQL:

```sql
v_column := CASE p_sort
    WHEN 'date' THEN 'placed_at'
    WHEN 'total' THEN 'total_amount'
    ELSE NULL
END;

IF v_column IS NULL THEN
    RAISE EXCEPTION 'Cột sắp xếp không hợp lệ';
END IF;

v_direction := CASE lower(p_direction)
    WHEN 'asc' THEN 'ASC'
    WHEN 'desc' THEN 'DESC'
    ELSE NULL
END;

IF v_direction IS NULL THEN
    RAISE EXCEPTION 'Hướng sắp xếp không hợp lệ';
END IF;

v_sql := format(
    'SELECT order_id, placed_at, total_amount
     FROM orders
     WHERE customer_id = $1
     ORDER BY %I %s',
    v_column,
    v_direction
);

RETURN QUERY EXECUTE v_sql USING p_customer_id;
```

Tên cột lấy từ allowlist và quote bằng %I. Direction chỉ nhận hai hằng số ASC/DESC nên có thể chèn như fragment cố định. Không đưa raw input vào %s.

### 11.2. Dynamic IN list

Không nối các giá trị đầu vào thành IN (1,2,3). Có thể:

- Dùng array parameter nếu DBMS/driver hỗ trợ.
- Dùng table-valued parameter trong SQL Server.
- Dùng temporary/staging table.
- Dùng JSON parameter và bung thành hàng.
- Sinh số lượng dấu ? theo kích thước list rồi bind từng phần tử.

Ví dụ Java JDBC:

```java
List<Integer> ids = List.of(101, 102, 103);

String placeholders = String.join(
    ",",
    Collections.nCopies(ids.size(), "?")
);

String sql = """
    SELECT order_id, customer_id
    FROM orders
    WHERE customer_id IN (%s)
    """.formatted(placeholders);

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (int i = 0; i < ids.size(); i++) {
        ps.setInt(i + 1, ids.get(i));
    }
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Xử lý hàng
        }
    }
}
```

Chỉ số lượng placeholder được tạo từ kích thước list; giá trị vẫn bind. Giới hạn kích thước list và xử lý danh sách rỗng riêng.

---

## 12. Quyền routine và nguyên tắc least privilege

Một routine có thể được gọi bởi user không có quyền trực tiếp trên bảng, trong khi routine chạy bằng quyền owner/definer. Đây là tính năng hữu ích nhưng có thể trở thành **confused deputy** nếu routine có quyền cao và nhận input điều khiển object.

Các câu hỏi cần trả lời:

- Ai được EXECUTE routine?
- Routine chạy theo quyền invoker hay definer?
- Dynamic SQL truy cập object nào?
- Identifier có thể được caller chọn không?
- Có thể truy cập schema hoặc tenant khác không?
- Có quyền UPDATE/DELETE/DDL ngoài mục tiêu không?
- Search path hoặc object resolution có thể bị thay đổi không?
- Có thể gọi routine khác với quyền cao hơn không?

| DBMS | Mô hình/quy tắc cần xem |
| --- | --- |
| PostgreSQL | SECURITY INVOKER/DEFINER; search_path và schema qualification |
| SQL Server | Ownership chaining, EXECUTE AS, module signing và quyền dynamic batch |
| MySQL | SQL SECURITY DEFINER/INVOKER; quản lý tài khoản DEFINER |
| Oracle | AUTHID DEFINER/CURRENT_USER; quyền object và ngữ cảnh invoker |
| SQLite | Quyền thường do host application, file access và authorizer API quản lý |

Quyền tối thiểu có nghĩa routine chỉ nhận quyền cần cho nhiệm vụ. Không dùng tài khoản quản trị toàn hệ chỉ để routine chạy được.

---

## 13. Transaction và DDL động

Dynamic SQL vẫn chịu transaction semantics của câu lệnh được thực thi. Việc câu lệnh được tạo thành chuỗi không làm thay đổi quy tắc commit/rollback của DBMS.

| DBMS | Lưu ý |
| --- | --- |
| PostgreSQL | DML động tuân theo transaction; một số utility command có giới hạn bind; CREATE INDEX CONCURRENTLY không chạy trong transaction block |
| SQL Server | Dynamic batch chạy theo ngữ cảnh transaction hiện hành; DDL, lock và trạng thái transaction vẫn cần xử lý |
| MySQL | Nhiều loại DDL gây implicit commit; prepared statement có lifecycle session riêng |
| Oracle | Nhiều DDL có implicit commit trước/sau; không giả định rollback DDL giống DML |
| SQLite | Prepared DML tham gia transaction của connection; ứng dụng quản lý statement và transaction |

Ví dụ Oracle:

```sql
EXECUTE IMMEDIATE
    'CREATE TABLE archive_2026 (id NUMBER)';
```

Không thể mặc định ROLLBACK sau đó sẽ xóa bảng như thể vừa hoàn tác một UPDATE. DDL động cần kế hoạch triển khai riêng, quyền phù hợp và kiểm tra transactional behavior.

---

## 14. Plan cache và hiệu năng

Nếu mỗi lần gọi tạo SQL text khác nhau bằng cách nối literal:

```sql
SELECT * FROM orders WHERE customer_id = 101;
SELECT * FROM orders WHERE customer_id = 102;
SELECT * FROM orders WHERE customer_id = 103;
```

DBMS có thể coi đây là các statement khác nhau, giảm cơ hội tái sử dụng kế hoạch hoặc tăng số plan trong cache.

Parameterized SQL giữ template ổn định:

```sql
SELECT * FROM orders WHERE customer_id = @customer_id;
```

và truyền value riêng.

Tuy nhiên, plan reuse không phải lúc nào cũng tối ưu. SQL Server có parameter sniffing; PostgreSQL có generic/custom plans; các DBMS khác có cơ chế cursor sharing riêng. Data skew có thể khiến plan phù hợp giá trị này nhưng chậm với giá trị khác.

Khi đo SQL động, cần quan sát:

- Parse/compile time.
- Execution time và số lần gọi.
- Plan shape.
- Estimated/actual rows.
- Data skew theo tham số.
- Lock waits, I/O và tài nguyên.
- Số dạng statement text được tạo.

Không dùng SQL động để né plan cache một cách mù quáng.

---

## 15. Xử lý lỗi và cleanup

SQL động có thể lỗi do:

- SQL text không hợp cú pháp.
- Tên bảng/cột không tồn tại.
- Kiểu hoặc thứ tự bind sai.
- Caller thiếu quyền.
- Prepared statement/cursor chưa được giải phóng.
- DDL có tác động transaction khác dự kiến.
- Kết quả trả về không đúng số hàng hoặc kiểu mong đợi.

PostgreSQL:

```sql
BEGIN
    EXECUTE v_sql USING p_customer_id;
EXCEPTION
    WHEN undefined_table THEN
        RAISE NOTICE 'Bảng báo cáo không tồn tại';
        RAISE;
    WHEN OTHERS THEN
        RAISE;
END;
```

SQL Server:

```sql
BEGIN TRY
    EXEC sys.sp_executesql
        @sql,
        N'@customer_id INT',
        @customer_id = 101;
END TRY
BEGIN CATCH
    THROW;
END CATCH;
```

MySQL cần handler để cleanup prepared statement nếu đã PREPARE, rồi RESIGNAL nếu caller phải nhận lỗi. Oracle cần đóng cursor DBMS_SQL trong cả normal path và exception path. SQLite/JDBC cần finalize/close statement và result set.

Không nuốt mọi exception bằng cách bỏ qua lỗi. Caller cần biết statement có thất bại hay không. Log phải đủ để chẩn đoán nhưng không làm lộ SQL secret hoặc giá trị nhạy cảm.

---

## 16. Khi nào nên tránh SQL động?

Nếu cấu trúc câu lệnh không thay đổi, SQL tĩnh thường tốt hơn:

```sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = p_customer_id;
```

Không cần tạo chuỗi dynamic chỉ để thay một giá trị có thể bind.

SQL động không cần thiết làm tăng:

- Số nhánh code và lỗi parse.
- Khó kiểm tra quyền và phụ thuộc object.
- Nguy cơ SQL injection khi thêm tính năng.
- Chi phí parse/plan khi text biến thiên.
- Độ khó logging, tracing và debugging.
- Rủi ro schema drift khi tên bảng/cột ghép từ chuỗi.

Dùng SQL động khi cấu trúc thật sự thay đổi: tên bảng được chọn có kiểm soát, dynamic pivot, DDL quản trị hoặc công cụ báo cáo có metadata đáng tin.

---

## 17. Bài tập thực hành

### Bài 1. Identifier và value

Trong câu SELECT total_amount FROM orders_2026 WHERE customer_id = 101 ORDER BY placed_at DESC, hãy phân loại tên bảng, tên cột, literal 101 và keyword DESC. Thành phần nào bind được?

### Bài 2. SQL injection

Một ứng dụng nối input vào điều kiện username. Hãy mô tả cách sửa bằng prepared statement và giải thích vì sao bind ngăn input thay đổi cấu trúc SQL.

### Bài 3. PostgreSQL USING

Viết PL/pgSQL dynamic SELECT tính SUM(total_amount) theo customer_id, nhận kết quả INTO và bind tham số bằng USING.

### Bài 4. PostgreSQL identifier

Routine nhận năm. Chỉ cho phép 2024, 2025, 2026; map sang tên bảng bằng CASE, quote bằng format('%I',...) và bind customer_id bằng $1.

### Bài 5. PostgreSQL format

Nêu khác biệt %I, %L và %s. Vì sao không đưa raw input vào %s? Khi nào nên ưu tiên USING hơn %L?

### Bài 6. SECURITY DEFINER

Một function quyền cao nhận tên bảng từ caller rồi ghép vào EXECUTE. Nêu ba rủi ro và biện pháp giảm.

### Bài 7. SQL Server sp_executesql

Viết dynamic SELECT theo customer_id và status, khai báo kiểu tham số và truyền giá trị theo tên.

### Bài 8. QUOTENAME

Vì sao QUOTENAME('dbo.Orders') không tương đương QUOTENAME('dbo') + '.' + QUOTENAME('Orders')? Vì sao vẫn cần allowlist?

### Bài 9. OUTPUT

Dùng sp_executesql lấy tổng doanh thu vào biến bên ngoài bằng OUTPUT parameter.

### Bài 10. MySQL lifecycle

Viết thứ tự PREPARE, EXECUTE USING và DEALLOCATE cho SELECT có hai placeholder.

### Bài 11. MySQL local variable

Vì sao prepared statement trong MySQL stored procedure không tham chiếu trực tiếp local parameter như SQL tĩnh? Cần làm gì?

### Bài 12. MySQL cleanup

Nếu EXECUTE lỗi trước DEALLOCATE, điều gì có thể còn tồn tại trong session? Đề xuất cách xử lý.

### Bài 13. Oracle NDS

Viết anonymous PL/SQL block dùng EXECUTE IMMEDIATE SELECT theo customer_id, INTO tổng và USING tham số.

### Bài 14. DBMS_ASSERT

Nêu mục đích SIMPLE_SQL_NAME và SQL_OBJECT_NAME. Vì sao không thay thế allowlist nghiệp vụ?

### Bài 15. DBMS_SQL

Khi nào nên dùng DBMS_SQL thay vì EXECUTE IMMEDIATE? Kể ba bước trong lifecycle.

### Bài 16. Oracle AUTHID

Phân biệt AUTHID DEFINER và CURRENT_USER. Vì sao dynamic SQL trong routine quyền cao cần review?

### Bài 17. SQLite

SQLite có stored procedure SQL native và EXECUTE IMMEDIATE không? Nêu API prepare/bind/step/finalize.

### Bài 18. JDBC

Viết PreparedStatement lọc theo customer_id và status. Vì sao dấu ? không thể bind tên bảng?

### Bài 19. ORDER BY

Ứng dụng nhận sort key date/total và direction asc/desc. Mô tả cách allowlist cả cột và direction.

### Bài 20. IN list

Ứng dụng nhận ba customer ID. Vì sao không nối giá trị vào IN (...)? Nêu hai cách bind an toàn.

### Bài 21. Plan cache

So sánh nối literal khác nhau mỗi lần với một template bind. Lợi ích và giới hạn của plan reuse?

### Bài 22. DDL Oracle

Procedure tạo bảng bằng EXECUTE IMMEDIATE, sau đó caller ROLLBACK. Vì sao không mặc định DDL được hoàn tác như DML?

### Bài 23. MySQL SQL SECURITY

Procedure SQL SECURITY DEFINER được cấp cho user báo cáo. Nêu các quyền và rủi ro cần review khi routine tạo SQL động.

### Bài 24. SQLite identifier

Ứng dụng SQLite chọn một trong ba bảng archive theo năm và lọc customer_id. Mô tả allowlist identifier và bind value.

### Bài 25. Thiết kế hoàn chỉnh

Thiết kế routine báo cáo có bảng thay đổi theo năm, filter customer_id, sort theo một trong hai cột. Mô tả allowlist, quote, bind, quyền, lỗi và kiểm thử.

---

## 18. Gợi ý lời giải

### Bài 1

orders_2026 là identifier bảng; customer_id và placed_at là identifier cột; 101 là value; DESC là keyword. Chỉ value bind trực tiếp. Identifier/keyword phải được chọn và ghép an toàn.

### Bài 2

Dùng PreparedStatement với WHERE username = ?, rồi setString(1, input). Driver truyền giá trị tách khỏi SQL text nên dấu nháy và cú pháp bên trong input không được diễn giải như SQL.

### Bài 3

```sql
EXECUTE
    'SELECT COALESCE(SUM(total_amount), 0)
     FROM orders
     WHERE customer_id = $1'
INTO v_total
USING p_customer_id;
```

### Bài 4

```sql
v_table := CASE p_year
    WHEN 2024 THEN 'orders_2024'
    WHEN 2025 THEN 'orders_2025'
    WHEN 2026 THEN 'orders_2026'
    ELSE NULL
END;

IF v_table IS NULL THEN
    RAISE EXCEPTION 'Năm không hợp lệ';
END IF;

EXECUTE format(
    'SELECT COALESCE(SUM(total_amount),0)
     FROM %I WHERE customer_id=$1',
    v_table
)
INTO v_total
USING p_customer_id;
```

### Bài 5

%I quote identifier; %L quote literal; %s chèn chuỗi nguyên dạng. Raw input trong %s có thể chèn cú pháp SQL. USING giữ value tách khỏi SQL text, hỗ trợ kiểu và tránh tự quote.

### Bài 6

Caller có thể chọn object ngoài mục đích; ghép raw tên gây injection; routine quyền cao có thể trở thành cầu vượt quyền. Dùng allowlist server-side, %I, schema qualification, search_path an toàn, bind values và quyền tối thiểu.

### Bài 7

```sql
DECLARE @sql NVARCHAR(MAX) = N'
    SELECT order_id, total_amount
    FROM dbo.Orders
    WHERE customer_id = @customer_id
      AND status = @status;';

EXEC sys.sp_executesql
    @sql,
    N'@customer_id INT, @status NVARCHAR(20)',
    @customer_id = 101,
    @status = N'PAID';
```

### Bài 8

QUOTENAME('dbo.Orders') quote toàn chuỗi thành một identifier. Quote riêng dbo và Orders rồi nối dấu chấm mới tạo schema.table. Allowlist vẫn cần vì identifier hợp lệ về cú pháp chưa chắc được phép truy cập.

### Bài 9

```sql
DECLARE @sql NVARCHAR(MAX) = N'
    SELECT @result = COALESCE(SUM(total_amount), 0)
    FROM dbo.Orders
    WHERE customer_id = @customer_id;';

DECLARE @total DECIMAL(18,2);

EXEC sys.sp_executesql
    @sql,
    N'@customer_id INT, @result DECIMAL(18,2) OUTPUT',
    @customer_id = 101,
    @result = @total OUTPUT;

SELECT @total;
```

### Bài 10

```sql
SET @sql_text =
    'SELECT order_id FROM orders WHERE customer_id = ? AND status = ?';

PREPARE stmt FROM @sql_text;
EXECUTE stmt USING @p_customer_id, @p_status;
DEALLOCATE PREPARE stmt;
```

### Bài 11

Prepared statement MySQL có session scope và không thể tham chiếu trực tiếp local variable/parameter của routine như SQL tĩnh. Copy parameter sang user variables rồi dùng EXECUTE ... USING.

### Bài 12

Prepared statement có thể còn trong session nếu lỗi xảy ra trước DEALLOCATE. Dùng handler theo dõi đã PREPARE hay chưa, cleanup khi cần, reset user variables và RESIGNAL.

### Bài 13

```sql
DECLARE
    v_total NUMBER;
    v_customer_id NUMBER := 101;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT NVL(SUM(total_amount), 0)
         FROM orders WHERE customer_id = :1'
    INTO v_total
    USING v_customer_id;
END;
/
```

### Bài 14

SIMPLE_SQL_NAME kiểm tra tên SQL đơn giản; SQL_OBJECT_NAME kiểm tra tên object SQL. Chúng không quyết định object nào được phép theo nghiệp vụ, nên vẫn cần allowlist và quyền.

### Bài 15

Dùng DBMS_SQL khi số cột/kiểu result set không biết trước hoặc cần API parse/describe/fetch cấp thấp. Các bước gồm OPEN_CURSOR, PARSE, BIND_VARIABLE, DESCRIBE_COLUMNS, DEFINE_COLUMN, EXECUTE/FETCH, COLUMN_VALUE và CLOSE_CURSOR.

### Bài 16

DEFINER chạy theo quyền owner; CURRENT_USER dùng ngữ cảnh invoker theo quy tắc Oracle. Routine quyền cao có thể truy cập object caller không được phép nếu input không kiểm soát. Cần allowlist, bind và quyền tối thiểu.

### Bài 17

SQLite core không có stored procedure SQL native hoặc EXECUTE IMMEDIATE tổng quát. Dùng sqlite3_prepare_v2, sqlite3_bind_*, sqlite3_step và sqlite3_finalize ở host application.

### Bài 18

```java
String sql = """
    SELECT order_id, total_amount
    FROM orders
    WHERE customer_id = ?
      AND status = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, customerId);
    ps.setString(2, status);
}
```

Dấu ? là value placeholder, không phải cú pháp identifier. Tên bảng phải chọn từ allowlist rồi ghép an toàn.

### Bài 19

Map date → placed_at, total → total_amount; map asc → ASC, desc → DESC. Từ chối giá trị ngoài danh sách. Quote identifier theo DBMS nếu tên không phải hằng số tin cậy.

### Bài 20

Nối value có thể gây injection và lỗi quote/kiểu. Có thể sinh số placeholder theo độ dài list rồi bind từng ID, hoặc dùng array/table-valued parameter/temp table/JSON tùy DBMS. Xử lý list rỗng riêng.

### Bài 21

Nối literal tạo nhiều SQL text khác nhau, giảm cơ hội reuse. Bind giữ template ổn định. Nhưng plan reuse có thể không tốt với data skew/parameter sniffing; đo tham số đại diện trước khi can thiệp.

### Bài 22

Nhiều DDL Oracle có implicit commit. ROLLBACK sau DDL không có nghĩa object được tạo sẽ biến mất như một UPDATE chưa commit. Cần hiểu transactional behavior của DDL.

### Bài 23

Review DEFINER account, quyền EXECUTE, quyền trên object, allowlist identifier, bind values, schema/tenant có thể truy cập và khả năng DDL/UPDATE/DELETE ngoài mục tiêu. Dùng quyền tối thiểu.

### Bài 24

Map năm bằng switch/allowlist sang ba tên bảng cố định; quote identifier theo SQLite nếu cần; ghép tên bảng đã kiểm soát; bind customer_id bằng placeholder. Không nối raw input vào SQL.

### Bài 25

Một thiết kế đầy đủ:

1. Map năm sang bảng trong allowlist.
2. Map sort key sang cột cố định và direction sang ASC/DESC.
3. Quote schema/table/column theo DBMS.
4. Bind customer_id, status, date range và paging values.
5. Dùng routine với quyền tối thiểu và mô hình definer/invoker đã review.
6. Validate tham số, giới hạn page size và từ chối giá trị không hỗ trợ.
7. Bắt lỗi có phân loại, rethrow đúng, không lộ SQL/secret.
8. Đo plan/cache với tham số phổ biến và lệch phân bố.
9. Kiểm thử injection, tên bảng không hợp lệ, quyền thiếu, bảng thiếu và dữ liệu rỗng.

---

## 19. Quy trình quyết định trước khi triển khai

Trước khi viết dynamic SQL, trả lời:

1. Cấu trúc câu lệnh có thực sự thay đổi không?
2. Phần nào là value, phần nào là identifier hoặc keyword?
3. Có thể giải quyết bằng SQL tĩnh, array/table parameter hoặc temp table không?
4. Identifier có allowlist phía server không?
5. Quote identifier theo đúng DBMS chưa?
6. Mọi value có bind chưa?
7. Routine chạy bằng quyền ai? Có cần definer rights không?
8. Có giới hạn schema/tenant và quyền object không?
9. Prepared statement/cursor có cleanup ở cả normal và error path không?
10. DDL có implicit commit hoặc giới hạn transaction không?
11. Plan cache, parse cost và data skew đã được đo chưa?
12. Log có đủ chẩn đoán nhưng không lộ dữ liệu nhạy cảm không?
13. Đã kiểm tra trên đúng DBMS và phiên bản chưa?

## 20. Tổng kết

SQL động hữu ích khi **cấu trúc câu lệnh thật sự thay đổi** như tên bảng, danh sách cột pivot hoặc DDL. Nó không phải lý do để ghép giá trị dữ liệu vào chuỗi.

Các nguyên tắc cần giữ:

1. Ưu tiên SQL tĩnh khi cấu trúc không đổi.
2. Bind value bằng cơ chế DBMS/driver: PostgreSQL USING, SQL Server sp_executesql, MySQL EXECUTE ... USING, Oracle EXECUTE IMMEDIATE ... USING, SQLite prepared API.
3. Identifier không bind được như value: chọn từ allowlist và quote đúng phương ngữ.
4. Không nhận raw SQL fragment từ người dùng; kiểm soát sort key, direction, table và column riêng.
5. Hiểu lifecycle: MySQL cần DEALLOCATE và quản lý session variables; Oracle có NDS/DBMS_SQL; SQLite quản lý statement ở host API.
6. Review quyền routine: SECURITY DEFINER/INVOKER, ownership chaining, SQL SECURITY và AUTHID khác nhau giữa các hệ.
7. Xử lý transaction và DDL đúng DBMS; không giả định mọi DDL rollback giống DML.
8. Đo plan và lỗi thực tế; dynamic SQL có thể tăng parse/plan cost hoặc gặp data skew dù đã bind.
9. Log an toàn: lưu fingerprint/correlation/error code, mask dữ liệu nhạy cảm.
10. Kiểm thử theo phương ngữ và phiên bản trước khi triển khai.

Cách nghĩ an toàn nhất: **template SQL chỉ chứa cấu trúc được kiểm soát; mọi giá trị dữ liệu đi qua bind; mọi identifier động phải được allowlist và quote; quyền routine phải được giới hạn theo đúng nghiệp vụ.**
