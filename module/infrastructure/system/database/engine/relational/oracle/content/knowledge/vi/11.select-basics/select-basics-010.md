# Biến bind, literal và phân biệt giá trị với tên đối tượng

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** SELECT cơ bản  
> **Mục tiêu:** Phân biệt giá trị dữ liệu với cấu trúc SQL; sử dụng literal và bind variable đúng cách trong Oracle SQL, PL/SQL và Java/JDBC; xây dựng dynamic SQL an toàn khi cần thay đổi tên bảng/cột; tránh SQL injection, lỗi NLS và các vấn đề tái sử dụng cursor.

## 1. Một câu SQL gồm giá trị và cấu trúc

Xét câu lệnh:

```sql
SELECT employee_id, first_name, salary
FROM employees
WHERE department_id = 50;
```

Trong câu lệnh này:

- `SELECT`, `FROM`, `WHERE` là từ khóa và cấu trúc SQL.
- `EMPLOYEES`, `EMPLOYEE_ID`, `FIRST_NAME`, `SALARY`, `DEPARTMENT_ID` là tên đối tượng (identifier).
- `50` là một giá trị dữ liệu, được viết trực tiếp dưới dạng numeric literal.

Nếu ứng dụng cần lọc theo phòng ban người dùng chọn, có thể viết:

```sql
SELECT employee_id, first_name, salary
FROM employees
WHERE department_id = :p_department_id;
```

`:p_department_id` là bind variable. Client truyền giá trị thực khi thực thi câu SQL.

Hai loại thông tin cần được tách riêng:

1. **Giá trị cần tìm:** ví dụ department ID bằng 50. Đây là dữ liệu, có thể bind.
2. **Đối tượng cần truy vấn:** ví dụ bảng EMPLOYEES và cột DEPARTMENT_ID. Đây là cấu trúc SQL, được xác định khi Oracle parse câu lệnh.

Bind variable thay thế giá trị, không thay thế tên bảng, tên cột, schema, từ khóa hoặc một đoạn cú pháp SQL tùy ý.

## 2. Literal trong Oracle SQL

**Literal** là giá trị được ghi trực tiếp trong SQL text. Oracle hỗ trợ literal theo nhiều kiểu dữ liệu.

### 2.1. Chuỗi ký tự

Chuỗi được đặt trong dấu nháy đơn:

```sql
SELECT *
FROM employees
WHERE first_name = 'Steven';
```

Để biểu diễn dấu nháy đơn bên trong chuỗi, nhân đôi dấu nháy:

```sql
SELECT 'O''Brien' AS customer_name
FROM dual;
```

Kết quả là `O'Brien`. Không dùng quy tắc escape của Java hoặc JavaScript để thay cho cú pháp literal SQL.

Oracle còn hỗ trợ alternative quoting với tiền tố `q`:

```sql
SELECT q'[Customer's note: "call back"]' AS note_text
FROM dual;
```

Cặp dấu phân cách có thể là `[]`, `{}`, `()`, `<>` hoặc ký tự phù hợp khác. Cách này hữu ích khi chuỗi có nhiều dấu nháy đơn.

National character literal có thể viết với tiền tố `N`:

```sql
SELECT N'Nguyễn Văn An' AS full_name
FROM dual;
```

Việc lưu Unicode còn phụ thuộc character set và kiểu cột; tiền tố N không thay thế việc thiết kế charset đúng.

### 2.2. Số

Numeric literal dùng dấu chấm làm dấu thập phân:

```sql
SELECT 125, -42, 12.75, 1.25E3
FROM dual;
```

Không viết literal theo định dạng hiển thị địa phương như `1.234,56` rồi mong mọi session hiểu giống nhau. Nếu ứng dụng truyền số, dùng bind có kiểu số. Nếu phải parse chuỗi từ nguồn ngoài, dùng `TO_NUMBER` với format mask và NLS rõ ràng.

### 2.3. DATE và TIMESTAMP literal

ANSI DATE literal có dạng `DATE 'YYYY-MM-DD'`:

```sql
SELECT *
FROM orders
WHERE order_date >= DATE '2026-11-14';
```

Literal này không phụ thuộc `NLS_DATE_FORMAT` và đại diện thời điểm 00:00:00 của ngày đó. Oracle DATE có cả giờ, phút và giây, không chỉ có ngày.

Nếu muốn lấy mọi hàng trong ngày, dùng khoảng nửa mở:

```sql
SELECT order_id, order_date
FROM orders
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15';
```

Timestamp literal:

```sql
SELECT TIMESTAMP '2026-11-14 09:30:45.123456'
FROM dual;
```

Timestamp có timezone có thể được tạo bằng `TO_TIMESTAMP_TZ` hoặc literal phù hợp. Khi nhận dữ liệu từ ứng dụng, bind đúng kiểu timestamp thường dễ kiểm soát hơn ghép chuỗi và parse.

### 2.4. NULL và INTERVAL

`NULL` là giá trị chưa biết/không có. Không viết `column = NULL`; phải dùng `IS NULL`:

```sql
SELECT *
FROM employees
WHERE commission_pct IS NULL;
```

Khoảng thời gian dùng kiểu INTERVAL:

```sql
SELECT TIMESTAMP '2026-11-14 09:00:00'
       + INTERVAL '45' MINUTE AS end_time
FROM dual;
```

Không nhầm mốc thời gian với khoảng thời gian. Một bind NULL trong điều kiện `column = :p_value` cũng không biến điều kiện đó thành phép tìm NULL; logic SQL trả UNKNOWN.

## 3. Bind variable là gì?

Bind variable là placeholder trong câu SQL, giá trị được truyền riêng lúc thực thi:

```sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE customer_id = :p_customer_id
  AND order_date >= :p_from_date
  AND order_date <  :p_to_date
  AND status = :p_status;
```

SQL text giữ nguyên khi các giá trị khách hàng, ngày hoặc trạng thái thay đổi. Client gửi các giá trị bind với datatype phù hợp.

| Đặc điểm | Literal | Bind variable |
|---|---|---|
| Ví dụ | `department_id = 50` | `department_id = :p_dept` |
| Vị trí giá trị | Nằm trực tiếp trong SQL text | Được truyền lúc thực thi |
| SQL text khi giá trị đổi | Thường đổi | Giữ nguyên nếu cấu trúc không đổi |
| Tái sử dụng cursor | Kém thuận lợi nếu mỗi giá trị tạo text khác | Có lợi cho cursor reuse |
| An toàn với input | Dễ sai nếu ghép chuỗi không kiểm soát | An toàn hơn khi bind đúng cách |
| Trường hợp phù hợp | Hằng số cố định trong logic SQL | Dữ liệu từ UI, API, batch hoặc ứng dụng |

Literal không xấu. Một điều kiện cố định như `status = 'ACTIVE'` trong view có thể hoàn toàn phù hợp. Vấn đề là không ghép dữ liệu bên ngoài vào SQL text khi có thể bind.

## 4. Vì sao bind variable quan trọng?

### 4.1. Parse và cursor reuse

Oracle phải parse câu SQL để hiểu cấu trúc, xác định đối tượng, kiểm tra quyền và xây dựng kế hoạch thực thi phù hợp.

Nếu ứng dụng tạo các câu lệnh khác nhau chỉ vì giá trị lọc đổi:

```sql
SELECT * FROM employees WHERE department_id = 10;
SELECT * FROM employees WHERE department_id = 20;
SELECT * FROM employees WHERE department_id = 30;
```

thì SQL text khác nhau. Điều này có thể làm tăng số lần hard parse và gây áp lực lên shared pool.

Dùng bind:

```sql
SELECT * FROM employees WHERE department_id = :p_dept;
```

giúp giữ nguyên SQL text và tạo điều kiện tái sử dụng cursor/statement. **Hard parse** là quá trình parse và tạo cursor/plan mới khi không thể dùng lại cursor phù hợp; **soft parse** có thể tái sử dụng cursor đã có và tránh một phần công việc đó.

Bind không bảo đảm mọi lần thực thi dùng đúng một child cursor. Khác biệt datatype, optimizer environment, metadata hoặc các điều kiện khác có thể khiến Oracle tạo child cursor riêng.

### 4.2. Bind không tự làm truy vấn nhanh

Một câu SQL có bind vẫn có thể đọc toàn bảng, dùng index không phù hợp, chuyển kiểu ngầm hoặc chờ I/O. Bind chủ yếu giúp tách dữ liệu khỏi SQL text và cải thiện khả năng chia sẻ cursor.

Ngoài ra, một cột có phân bố dữ liệu lệch có thể khiến một execution plan không phù hợp với mọi giá trị bind. Oracle có các cơ chế như **bind peeking** và **adaptive cursor sharing** để đánh giá một số trường hợp bind-sensitive và có thể dùng nhiều child cursor/plan.

Khi cùng SQL chạy nhanh với giá trị này nhưng chậm với giá trị khác, cần xem SQL ID, child cursor, bind datatype, statistics/histogram, execution plan, logical reads, physical reads và waits. Không bỏ bind hoặc ghép literal hàng loạt chỉ vì một plan chưa tốt.

### 4.3. CURSOR_SHARING không thay thế bind trong ứng dụng

Oracle có tham số `CURSOR_SHARING` với các lựa chọn như `EXACT` và `FORCE`. `FORCE` có thể thay một số literal bằng bind do hệ thống tạo để tăng khả năng chia sẻ cursor. Tuy nhiên, nó không thay thế PreparedStatement, không bảo vệ identifier được ghép động và không sửa SQL injection. Đây là cấu hình DBA cần đánh giá tác động toàn hệ thống.

## 5. Bind trong SQL*Plus, SQLcl và SQL Developer

SQL*Plus/SQLcl hỗ trợ khai báo bind variable bằng `VARIABLE`:

```sql
VARIABLE p_department_id NUMBER

EXEC :p_department_id := 50;

SELECT employee_id, first_name, department_id
FROM employees
WHERE department_id = :p_department_id;

PRINT p_department_id;
```

- `VARIABLE` tạo bind variable trong session client.
- `EXEC` gán giá trị cho bind.
- Dấu hai chấm dùng để tham chiếu bind trong SQL.
- `PRINT` hiển thị giá trị bind.

Ví dụ với ngày:

```sql
VARIABLE p_from_date DATE
EXEC :p_from_date := DATE '2026-11-01';

SELECT order_id, order_date
FROM orders
WHERE order_date >= :p_from_date;
```

Trong SQL Developer Worksheet, cách chạy script có các lệnh SQL*Plus như `VARIABLE` và `EXEC` có thể khác Run Statement. Hãy dùng chế độ script khi cần xử lý cả khối lệnh.

## 6. Bind trong Java/JDBC

Trong JDBC, `PreparedStatement` dùng dấu hỏi `?` làm placeholder theo vị trí:

```java
String sql = """
    SELECT employee_id, first_name, salary
    FROM employees
    WHERE department_id = ?
      AND salary >= ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, departmentId);
    ps.setBigDecimal(2, minimumSalary);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            int employeeId = rs.getInt("EMPLOYEE_ID");
            String firstName = rs.getString("FIRST_NAME");
            BigDecimal salary = rs.getBigDecimal("SALARY");
            System.out.println(employeeId + " " + firstName + " " + salary);
        }
    }
}
```

Chỉ số placeholder bắt đầu từ 1. Setter phải khớp kiểu dữ liệu:

| Kiểu Oracle | Setter JDBC thường dùng |
|---|---|
| NUMBER tiền/thập phân | `setBigDecimal` |
| NUMBER nguyên trong miền int/long | `setInt` hoặc `setLong` |
| VARCHAR2/CHAR | `setString` |
| DATE/TIMESTAMP | API JDBC hoặc Java time tương ứng với ngữ nghĩa cột |
| TIMESTAMP WITH TIME ZONE | `setObject` với `OffsetDateTime` nếu driver hỗ trợ, hoặc API Oracle JDBC |
| BLOB/CLOB | `setBlob`/`setClob` hoặc stream phù hợp |

Không chuyển mọi giá trị thành String rồi để Oracle implicit conversion. Điều này có thể phụ thuộc NLS, gây lỗi hoặc làm phát sinh chuyển đổi trên cột.

### 6.1. Bind NULL đúng kiểu

Nếu cột có thể NULL, JDBC có thể truyền NULL với datatype:

```java
String sql = """
    INSERT INTO employees_stage (employee_id, commission_pct)
    VALUES (?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, employeeId);
    ps.setNull(2, java.sql.Types.NUMERIC);
    ps.executeUpdate();
}
```

`setNull(index, sqlType)` giúp driver biết kiểu của giá trị NULL. Với LOB, UDT hoặc kiểu đặc thù, có thể cần API riêng.

### 6.2. Không ghép ngày giờ thành chuỗi SQL

Không nên:

```java
String sql = "SELECT * FROM orders WHERE order_date = '"
             + inputDate + "'";
```

Nên dùng PreparedStatement và bind kiểu ngày giờ phù hợp. Oracle DATE có cả phần giờ đến giây; nếu cột chứa giờ thì không nên dùng Java LocalDate rồi vô ý bỏ mất phần thời gian. Với TIMESTAMP WITH TIME ZONE, xác định mapping tương thích với JDBC driver.

PreparedStatement tách SQL text khỏi tham số và hỗ trợ statement/cursor reuse, nhưng không có nghĩa một đối tượng Java luôn tương ứng một cursor duy nhất vĩnh viễn. Connection pool, statement cache, child cursor và invalidation đều ảnh hưởng vòng đời thực tế.

## 7. Bind trong PL/SQL và dynamic SQL

Trong PL/SQL, biến cục bộ có thể được dùng trong SQL tĩnh:

```sql
DECLARE
    l_department_id NUMBER := 50;
BEGIN
    FOR r IN (
        SELECT employee_id, first_name
        FROM employees
        WHERE department_id = l_department_id
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            r.employee_id || ': ' || r.first_name
        );
    END LOOP;
END;
/
```

Với dynamic SQL, truyền giá trị qua `USING`:

```sql
DECLARE
    l_department_id NUMBER := 50;
    l_min_salary    NUMBER := 5000;
    l_count         NUMBER;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM employees
         WHERE department_id = :1
           AND salary >= :2'
    INTO l_count
    USING l_department_id, l_min_salary;

    DBMS_OUTPUT.PUT_LINE('Count = ' || l_count);
END;
/
```

SQL text quyết định cấu trúc; `USING` truyền giá trị. Với SQL statement thông thường trong Native Dynamic SQL, bind arguments được liên kết theo vị trí placeholder. Khi dùng anonymous PL/SQL block hoặc dynamic call, quy tắc placeholder có khác biệt; cần tham khảo SQL Reference và không dựa vào việc đặt cùng tên placeholder để bỏ qua thứ tự.

Dynamic SQL không đồng nghĩa phải nối mọi thứ. Hãy bind mọi giá trị có thể bind; chỉ phần cấu trúc thực sự cần thay đổi mới được tạo động.

## 8. Vì sao không thể bind tên bảng hoặc tên cột?

Ví dụ:

```sql
VARIABLE table_name VARCHAR2(30)
EXEC :table_name := 'EMPLOYEES';

SELECT *
FROM :table_name;
```

`:table_name` là một giá trị bind, không phải identifier. Parser cần biết bảng nào được tham chiếu khi parse câu SQL; bind được xử lý sau bước xác định cấu trúc.

Tương tự:

```sql
SELECT :column_name
FROM employees;
```

Câu lệnh không đọc cột có tên được truyền vào. Nó trả về giá trị bind như một biểu thức cho các hàng, không thay thế tên cột.

`ORDER BY :sort_column` cũng không sắp theo cột có tên trong bind. Nếu bind là chuỗi `'SALARY'`, đó là một giá trị cố định, không phải token identifier SALARY.

| Thành phần | Bind trực tiếp được? | Cách xử lý |
|---|---|---|
| Giá trị `salary = ?` | Có | Bind số |
| Giá trị chuỗi `name = ?` | Có | Bind chuỗi |
| Ngày bắt đầu/kết thúc | Có | Bind DATE/TIMESTAMP có kiểu |
| Tên bảng sau FROM | Không | Allowlist/validate identifier rồi tạo dynamic SQL |
| Tên cột sau SELECT/ORDER BY | Không | Allowlist hoặc dùng query cố định |
| ASC/DESC, JOIN, WHERE | Không | Chọn token/cấu trúc cố định đã kiểm soát |
| Tên schema/sequence | Không | Kiểm soát identifier và quyền |
| Giá trị LIKE | Có | Bind pattern; xử lý wildcard nếu cần |
| Phần tử trong IN list | Có | Một placeholder mỗi phần tử hoặc collection strategy |

Quy tắc: **bind dữ liệu; kiểm soát riêng cấu trúc SQL**.

## 9. SQL injection và cách ngăn chặn

SQL injection xảy ra khi dữ liệu đầu vào bị diễn giải thành cú pháp SQL. Ví dụ ứng dụng nối username:

```java
String sql =
    "SELECT * FROM app_users WHERE username = '"
    + username
    + "'";
Statement st = connection.createStatement();
ResultSet rs = st.executeQuery(sql);
```

Nếu người dùng nhập `' OR '1'='1`, SQL có thể trở thành:

```sql
SELECT *
FROM app_users
WHERE username = '' OR '1'='1';
```

Điều kiện luôn đúng và có thể trả về nhiều tài khoản ngoài dự kiến.

Sửa bằng bind:

```java
String sql =
    "SELECT user_id, username " +
    "FROM app_users " +
    "WHERE username = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, username);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Xử lý kết quả.
        }
    }
}
```

Chuỗi đầu vào được truyền như một giá trị username, không trở thành cú pháp SQL.

Escape chuỗi thủ công không phải giải pháp chính: ứng dụng có nhiều datatype, charset, format và vị trí cú pháp. Dùng bind cho giá trị, allowlist cho identifier, giới hạn quyền database account theo least privilege và không cho người dùng gửi một đoạn SQL tùy ý để thực thi.

### 9.1. Bind không bảo vệ phần identifier ghép động

Đoạn sau vẫn nguy hiểm:

```java
String sql =
    "SELECT * FROM " + userSuppliedTable +
    " WHERE department_id = ?";

PreparedStatement ps = connection.prepareStatement(sql);
ps.setInt(1, departmentId);
```

`DEPARTMENT_ID` được bind an toàn, nhưng `userSuppliedTable` vẫn được ghép vào SQL text. Phải kiểm soát tên bảng riêng.

## 10. Dynamic identifier: allowlist và DBMS_ASSERT

### 10.1. Allowlist ở tầng ứng dụng

Giả sử màn hình chỉ cho phép chọn ba báo cáo:

```text
EMPLOYEES
ORDERS
PAYMENTS
```

Ánh xạ lựa chọn UI sang identifier cố định:

```java
Map<String, String> allowedTables = Map.of(
    "employees", "EMPLOYEES",
    "orders", "ORDERS",
    "payments", "PAYMENTS"
);

String tableName = allowedTables.get(requestedReport);
if (tableName == null) {
    throw new IllegalArgumentException("Unsupported report");
}

String sql =
    "SELECT * FROM " + tableName +
    " WHERE created_at >= ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setTimestamp(1, fromTimestamp);
    // Execute query...
}
```

Tên bảng chỉ đến từ danh sách đã phê duyệt; giá trị ngày vẫn bind. Một identifier hợp lệ về cú pháp vẫn có thể là đối tượng người dùng không được phép truy cập, vì vậy allowlist còn bảo vệ quyền nghiệp vụ.

### 10.2. DBMS_ASSERT trong PL/SQL

Oracle cung cấp package `DBMS_ASSERT` để kiểm tra hoặc quote một số dạng identifier/literal trong dynamic SQL.

```sql
DECLARE
    l_table_name VARCHAR2(261) := 'EMPLOYEES';
    l_safe_name  VARCHAR2(261);
    l_count      NUMBER;
BEGIN
    l_safe_name := DBMS_ASSERT.SQL_OBJECT_NAME(l_table_name);

    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM ' || l_safe_name
        INTO l_count;

    DBMS_OUTPUT.PUT_LINE('Rows = ' || l_count);
END;
/
```

Một số hàm:

- `DBMS_ASSERT.SQL_OBJECT_NAME`: xác thực tên đối tượng SQL phù hợp và yêu cầu đối tượng tồn tại.
- `DBMS_ASSERT.SIMPLE_SQL_NAME`: xác thực simple SQL name.
- `DBMS_ASSERT.QUALIFIED_SQL_NAME`: xác thực tên đủ điều kiện theo cú pháp được hỗ trợ.
- `DBMS_ASSERT.ENQUOTE_NAME`: quote identifier.
- `DBMS_ASSERT.ENQUOTE_LITERAL`: quote string literal.

DBMS_ASSERT không thay thế allowlist nghiệp vụ, phân quyền hoặc kiểm tra người dùng có được phép chọn đối tượng đó hay không.

### 10.3. Quoted identifier không giống bind

Oracle cho phép tên đối tượng được quote:

```sql
CREATE TABLE "Monthly Sales" (
    "Order ID" NUMBER
);

SELECT "Order ID"
FROM "Monthly Sales";
```

Tên có khoảng trắng/chữ hoa thường đặc biệt làm SQL khó viết và tích hợp. Schema ứng dụng thường nên dùng identifier đơn giản, không quote. Quote tên cũng không làm cho identifier trở thành bind variable.

## 11. ORDER BY động

Nếu người dùng chọn cột và hướng sắp xếp, hãy allowlist các token:

```java
Map<String, String> sortColumns = Map.of(
    "name", "FIRST_NAME",
    "salary", "SALARY",
    "hireDate", "HIRE_DATE"
);

String sortColumn = sortColumns.get(requestedSort);
if (sortColumn == null) {
    throw new IllegalArgumentException("Invalid sort field");
}

String direction;
if ("asc".equalsIgnoreCase(requestedDirection)) {
    direction = "ASC";
} else if ("desc".equalsIgnoreCase(requestedDirection)) {
    direction = "DESC";
} else {
    throw new IllegalArgumentException("Invalid sort direction");
}

String sql =
    "SELECT employee_id, first_name, salary " +
    "FROM employees " +
    "WHERE department_id = ? " +
    "ORDER BY " + sortColumn + " " + direction;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, departmentId);
    // Execute...
}
```

`sortColumn` và `direction` được chọn từ danh sách cố định; `departmentId` vẫn là bind.

Với một số ít kiểu sort, có thể dùng CASE trong ORDER BY để giữ SQL text cố định:

```sql
SELECT employee_id, first_name, salary
FROM employees
WHERE department_id = :p_department
ORDER BY
    CASE WHEN :p_sort = 'NAME' THEN first_name END,
    CASE WHEN :p_sort = 'SALARY' THEN salary END;
```

Cách này cần chú ý datatype, NULL, chiều sort và execution plan. Nó không phải lúc nào cũng tận dụng index ordering tốt như ORDER BY trực tiếp.

## 12. Bind trong IN list

Một bind variable là một giá trị, không phải một đoạn SQL chứa nhiều giá trị.

```sql
SELECT *
FROM employees
WHERE employee_id IN (:p_ids);
```

Nếu `:p_ids` nhận chuỗi `'10,20,30'`, Oracle xem đó là một chuỗi; nó không tự tách thành ba số.

### 12.1. Một placeholder cho mỗi phần tử

Với danh sách ngắn:

```sql
SELECT *
FROM employees
WHERE employee_id IN (:id1, :id2, :id3);
```

Mỗi placeholder nhận một giá trị riêng. Nếu ứng dụng tạo số placeholder theo kích thước danh sách, chỉ tạo cấu trúc dấu hỏi/placeholder; mọi ID thực tế vẫn bind. JDBC không tự mở rộng một tham số ? thành nhiều tham số vì được truyền Java List.

### 12.2. Collection, temporary table hoặc JSON_TABLE

Oracle hỗ trợ collection/table expression trong những trường hợp phù hợp:

```sql
SELECT e.employee_id, e.first_name
FROM employees e
WHERE e.employee_id IN (
    SELECT column_value
    FROM TABLE(sys.odcinumberlist(10, 20, 30))
);
```

Ví dụ dùng literal để minh họa. Việc bind SQL collection từ Java phụ thuộc Oracle JDBC API và SQL collection type; không giả định `setObject(List)` tự động biến Java List thành collection Oracle.

Với danh sách lớn hoặc được tái sử dụng, có thể nạp ID vào global temporary table rồi join. Một lựa chọn khác ở phiên bản hỗ trợ là bind JSON document và chuyển thành hàng bằng `JSON_TABLE`. Cần kiểm tra kích thước, định dạng và hiệu năng theo workload.

## 13. LIKE, wildcard và NULL

### 13.1. LIKE pattern

Bind pattern trong LIKE là hợp lệ:

```sql
SELECT employee_id, first_name
FROM employees
WHERE first_name LIKE :p_pattern;
```

`%` khớp chuỗi bất kỳ; `_` khớp một ký tự. Đây là quy tắc pattern của LIKE, không phải SQL injection. Nếu muốn tìm chính xác input nhưng input chứa % hoặc _, cần escape wildcard theo một ký tự escape đã chọn và cú pháp Oracle.

Ví dụ:

```sql
SELECT employee_id, first_name
FROM employees
WHERE first_name LIKE :p_pattern ESCAPE '\';
```

Pattern nên được tạo ở ứng dụng theo thứ tự escape ký tự escape trước, rồi escape % và _. Tìm kiếm dạng `LIKE '%text%'` thường khó tận dụng B-tree index thông thường; nếu cần tìm kiếm văn bản lớn, xem xét Oracle Text hoặc giải pháp phù hợp.

### 13.2. Optional filter với NULL

Có thể viết:

```sql
SELECT employee_id, first_name
FROM employees
WHERE (:p_department_id IS NULL
       OR department_id = :p_department_id);
```

Nếu bind NULL, predicate cho phép mọi phòng ban; nếu có giá trị thì lọc theo phòng ban. Tuy nhiên OR có thể khiến optimizer khó chọn access path tốt cho mọi trường hợp. Với vài tổ hợp filter rõ ràng, tạo một số SQL text cố định cho từng cấu hình và bind các giá trị thường dễ kiểm soát hơn.

Không dùng `= NULL`. Dùng `IS NULL` hoặc `IS NOT NULL`.

## 14. Bind và NLS

### 14.1. Ngày giờ

Không nên phụ thuộc vào chuyển kiểu ngầm:

```sql
SELECT *
FROM orders
WHERE order_date >= '14/11/2026';
```

Oracle có thể chuyển chuỗi theo `NLS_DATE_FORMAT` của session; session khác có thể dùng format khác và hiểu sai hoặc báo lỗi.

Ưu tiên:

- DATE literal `DATE '2026-11-14'` cho hằng số trong SQL.
- `TO_DATE(text, format_mask)` khi thực sự nhận chuỗi.
- Bind DATE/TIMESTAMP có kiểu trong ứng dụng.

### 14.2. Số

Chuỗi `'1,25'` có thể được hiểu khác theo `NLS_NUMERIC_CHARACTERS`. Với Java, bind `BigDecimal` thay vì format số thành chuỗi.

Bind không tự xác thực dữ liệu đầu vào. Ứng dụng vẫn phải parse, kiểm tra miền giá trị và truyền đúng datatype.

## 15. Literal trong SQL tĩnh hay bind trong ứng dụng?

Không cần biến mọi literal trong mã SQL thành bind.

**Literal cố định thuộc logic câu lệnh** có thể viết trực tiếp:

```sql
SELECT employee_id, first_name
FROM employees
WHERE status = 'ACTIVE';
```

Nếu ACTIVE là điều kiện cố định trong view/báo cáo, literal hợp lý.

**Giá trị thay đổi theo request** nên bind:

```sql
SELECT employee_id, first_name, salary
FROM employees
WHERE department_id = :p_department
  AND hire_date >= :p_from_date
  AND salary >= :p_min_salary;
```

**Cấu trúc câu lệnh thay đổi** như tên bảng, tên cột hoặc hướng sort thì không bind trực tiếp được. Xác định lựa chọn thuộc allowlist, ánh xạ sang identifier/token cố định, xây SQL text từ phần đã kiểm soát và bind tất cả giá trị dữ liệu.

## 16. Các anti-pattern thường gặp

| Anti-pattern | Vấn đề | Cách làm phù hợp |
|---|---|---|
| Nối giá trị người dùng vào SQL | SQL injection, SQL text biến đổi, lỗi quote | PreparedStatement/Bind |
| Bind tên bảng hoặc tên cột | Bind là value, không phải identifier | Allowlist và dynamic SQL có kiểm soát |
| `ORDER BY :column` | Không sắp theo identifier truyền vào | Allowlist cột/hướng sort |
| Một bind chứa `'10,20,30'` cho IN | Oracle nhận một chuỗi, không phải danh sách | Placeholder từng phần tử hoặc collection/table |
| Bind mọi thứ thành VARCHAR2 | Implicit conversion và NLS | Bind đúng datatype |
| So sánh `column = NULL` | Kết quả UNKNOWN | `IS NULL` |
| Parse ngày theo NLS mặc định | Khác biệt session | DATE literal, format mask hoặc bind |
| Escape input thủ công rồi nối SQL | Dễ thiếu escape ở ngữ cảnh khác | Bind dữ liệu |
| Dùng MAX(id) lấy ID vừa insert | Session khác có thể insert trước | RETURNING hoặc JDBC generated keys |
| Tắt bind để xử lý một plan chậm | Có thể tăng hard parse và rủi ro injection | Xem child cursor, bind peeking, statistics và plan |

## 17. Bài thực hành

Các bài dùng schema mẫu hoặc bảng lab; chỉ chạy trên môi trường bạn được phép truy cập.

### Bài 1 — Cùng SQL, nhiều giá trị bind

```sql
VARIABLE p_dept NUMBER
EXEC :p_dept := 10;

SELECT employee_id, first_name, department_id
FROM employees
WHERE department_id = :p_dept;

EXEC :p_dept := 20;

SELECT employee_id, first_name, department_id
FROM employees
WHERE department_id = :p_dept;
```

Quan sát: SQL text giống nhau, giá trị bind thay đổi. Giải thích vì sao cách này hỗ trợ cursor reuse.

### Bài 2 — Chuyển literal sang bind trong Java

Viết hai phiên bản truy vấn: một phiên bản nối department ID vào SQL text, một phiên bản dùng PreparedStatement và setInt. So sánh SQL text, datatype, nguy cơ injection và khả năng tái sử dụng statement.

### Bài 3 — Bind tên bảng

Thử:

```sql
SELECT COUNT(*) FROM :p_table;
```

Giải thích vì sao parser không hiểu bind như identifier. Thiết kế allowlist chỉ cho phép EMPLOYEES và DEPARTMENTS, rồi viết dynamic SQL trong PL/SQL với DBMS_ASSERT phù hợp.

### Bài 4 — Lọc một ngày có giờ

Cho cột `ORDER_DATE DATE` có cả ngày và giờ. Viết câu lấy toàn bộ hàng ngày 14/11/2026 bằng DATE literal, sau đó viết phiên bản bind hai ranh giới ngày. Giải thích vì sao `ORDER_DATE = DATE '2026-11-14'` bỏ sót hàng sau 00:00:00.

### Bài 5 — NULL

Viết câu lọc `COMMISSION_PCT` NULL. Sau đó bind NULL trong JDBC và giải thích vì sao `commission_pct = ?` không tương đương `commission_pct IS NULL`.

### Bài 6 — IN list

API nhận ba employee ID. Đề xuất cách tạo ba placeholder và bind ba số; sau đó nêu lựa chọn collection/temporary table/JSON_TABLE cho danh sách lớn. Giải thích vì sao một chuỗi CSV không tự mở rộng thành nhiều bind.

### Bài 7 — Dynamic ORDER BY

Màn hình cho phép sort theo NAME hoặc SALARY, chiều ASC hoặc DESC. Viết logic allowlist, tạo SQL text từ lựa chọn đã xác nhận và bind department ID. Giải thích vì sao `ORDER BY :sort_column` không thực hiện sort theo cột.

### Bài 8 — SQL injection

Với truy vấn đăng nhập có username và password_hash, mô tả nguy cơ nếu hai input được nối chuỗi, sau đó viết lại bằng PreparedStatement có hai bind. Nêu thêm nguyên tắc least privilege và không ghi secret vào log.

## 18. Sơ đồ quyết định: bind hay tạo SQL động?

```text
Thành phần cần đưa vào câu SELECT là gì?
|
+-- Giá trị dữ liệu (NUMBER, DATE, STRING, TIMESTAMP, NULL)
|       └── BIND VARIABLE
|
+-- LIKE pattern
|       └── Bind pattern; xử lý wildcard nếu cần
|
+-- Tên bảng/cột/schema/sequence
|       └── Không bind như identifier
|              └── Allowlist + validate/quote + dynamic SQL
|
+-- ASC/DESC/từ khóa/toán tử/đoạn SQL
|       └── Chọn token/cấu trúc cố định từ allowlist
|
+-- Danh sách nhiều giá trị
        +-- Nhỏ, độ dài biết trước: một placeholder mỗi phần tử
        +-- Lớn/tái sử dụng: collection, temporary table hoặc JSON_TABLE
```

## 19. Ghi nhớ cốt lõi

- **Literal** là giá trị viết trực tiếp trong SQL, phù hợp với hằng số cố định.
- **Bind variable** truyền giá trị riêng lúc thực thi, giữ SQL text ổn định và giảm nguy cơ SQL injection.
- **Bind không thay thế tên bảng, tên cột, schema, từ khóa hoặc đoạn cú pháp SQL.**
- **PreparedStatement** là cách thông dụng trong JDBC để bind giá trị; dùng setter đúng kiểu.
- **Dynamic SQL** có thể an toàn nếu bind mọi giá trị và chỉ ghép identifier/token đã được allowlist, kiểm tra.
- **DBMS_ASSERT** hỗ trợ xác thực/quote identifier trong PL/SQL nhưng không thay thế allowlist nghiệp vụ và phân quyền.
- **NULL** cần logic riêng; phép so sánh bằng bind NULL không tương đương IS NULL.
- **IN list** không được mở rộng từ một bind chứa chuỗi CSV.
- **NLS** là lý do quan trọng để tránh chuyển ngày/số qua chuỗi không có format rõ.
- **Cursor reuse** hỗ trợ hiệu năng nhưng không bảo đảm một execution plan tối ưu cho mọi giá trị.
- **Không dùng MAX(id)** để lấy ID vừa insert; dùng RETURNING hoặc generated keys.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — Literals, bind variables, expressions, dynamic SQL và identifier.
- [Oracle Database PL/SQL Language Reference](https://docs.oracle.com/en/database/) — Native Dynamic SQL, `EXECUTE IMMEDIATE` và `USING`.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/) — `DBMS_ASSERT`.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/) — parsing, shared SQL area, library cache và cursor.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/) — bind peeking, adaptive cursor sharing và execution plan.
- [Oracle Database JDBC Developer's Guide](https://docs.oracle.com/en/database/) — PreparedStatement, bind datatypes và statement cache.

Cú pháp và khả năng cụ thể phụ thuộc phiên bản Oracle, JDBC driver và công cụ client. Khi triển khai, đối chiếu đúng release đang dùng; nguyên tắc không đổi là **bind giá trị, kiểm soát riêng cấu trúc SQL**.

