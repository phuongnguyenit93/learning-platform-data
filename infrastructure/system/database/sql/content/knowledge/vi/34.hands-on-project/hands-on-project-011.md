# Gọi truy vấn tham số hóa từ ứng dụng và kiểm thử đầu vào

Ứng dụng thường nhận dữ liệu từ form, API, file import, message queue hoặc một service khác rồi gửi truy vấn đến database. Nếu chương trình ghép trực tiếp input vào chuỗi SQL, dữ liệu có thể làm thay đổi cấu trúc câu lệnh, gây SQL injection, lỗi chuyển kiểu hoặc ghi dữ liệu ngoài quy tắc nghiệp vụ.

Cách làm nền tảng là **parameterized query**: viết câu SQL với placeholder cho các giá trị, sau đó truyền giá trị qua API bind của driver. Database nhận cấu trúc SQL và dữ liệu theo hai phần riêng biệt. Ứng dụng vẫn phải validate đầu vào theo hợp đồng nghiệp vụ; database tiếp tục bảo vệ dữ liệu bằng kiểu, constraint và transaction.

Bài này đi từ ứng dụng đến database:

- Chuẩn bị và gọi câu SQL có tham số.
- Placeholder khác nhau giữa JDBC, Python DB-API, PostgreSQL driver, MySQL driver và SQL Server.
- Bind NULL, chuỗi, số thập phân, ngày giờ và danh sách.
- Xử lý optional filter, ORDER BY và identifier động.
- Kiểm thử hợp lệ, không hợp lệ, boundary, SQL injection và concurrency.
- Kiểm tra kết quả, lỗi, row count, transaction và dữ liệu sau khi ghi.
- Thiết kế integration test có thể chạy lặp lại và tái hiện lỗi.

Bài thuộc **Database SQL → Thực hành tổng hợp → Gọi truy vấn tham số hóa từ ứng dụng và kiểm thử đầu vào**. Ví dụ tập trung vào SQL quan hệ và driver phổ biến; cú pháp placeholder phải được điều chỉnh theo driver thực tế.

---

## 1. Luồng từ input đến database

Một request thường đi qua các bước:

```text
HTTP / Form / File / Queue
          |
          v
  Parse request và kiểu dữ liệu
          |
          v
  Validate cú pháp và miền nghiệp vụ
          |
          v
  Tạo SQL template cố định
          |
          v
  Bind values qua driver
          |
          v
  Database parse / execute
          |
          v
  Constraint + transaction
          |
          v
  Đọc kết quả và map lỗi
          |
          v
  Response cho caller
```

| Lớp | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Parse | Chuyển biểu diễn input thành kiểu ứng dụng | Chuỗi "42" thành integer 42 |
| Validation | Kiểm tra hợp đồng và miền nghiệp vụ | Quantity từ 0 đến 100 |
| SQL template | Xác định cấu trúc câu lệnh | WHERE customer_id = ? |
| Binding | Truyền value đúng kiểu | setInt(1, customerId) |
| Database constraints | Bảo vệ tính toàn vẹn cuối cùng | NOT NULL, CHECK, UNIQUE, FK |
| Transaction | Gom các thay đổi nguyên tử | Order + order items |
| Error mapping | Chuyển lỗi kỹ thuật thành lỗi API phù hợp | Duplicate key thành conflict |

Parameterized query không thay thế validation. Input -100 có thể được bind an toàn nhưng vẫn vi phạm quantity không âm. Ngược lại, validation không thay parameter binding: input hợp lệ về nghiệp vụ vẫn có thể chứa dấu nháy hoặc chuỗi khiến SQL bị injection nếu ghép trực tiếp.

## 2. SQL ghép chuỗi và SQL tham số hóa

### 2.1. Cách ghép chuỗi nguy hiểm

```java
String sql =
    "SELECT user_id, username " +
    "FROM users " +
    "WHERE username = '" + username + "'";

Statement statement = connection.createStatement();
ResultSet rs = statement.executeQuery(sql);
```

Nếu username là input không tin cậy, nó có thể chứa dấu nháy và cú pháp SQL. Câu lệnh cuối cùng không còn giữ cấu trúc mà lập trình viên dự định.

Tấn công có thể dẫn đến bỏ qua xác thực, đọc hàng của user khác, thay đổi hoặc xóa dữ liệu, vượt tenant, gọi routine khác hoặc làm lộ schema và dữ liệu nhạy cảm.

Không cần input phải đến trực tiếp từ người dùng cuối. Dữ liệu import, webhook, file CSV, message queue và trường trong database khác đều có thể không đáng tin cậy.

### 2.2. Dùng PreparedStatement

```java
String sql = """
    SELECT user_id, username
    FROM users
    WHERE username = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, username);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long userId = rs.getLong("user_id");
            String name = rs.getString("username");
        }
    }
}
```

Placeholder `?` là vị trí của value. Giá trị username được gửi qua `setString`, không được nối vào SQL text. Driver/database biết đâu là SQL và đâu là dữ liệu. Input chứa dấu nháy, comment marker hoặc từ khóa SQL được xử lý như giá trị chuỗi.

### 2.3. Parameterized query không phải chỉ là escape

Tự thay dấu nháy trong chuỗi không phải giải pháp tương đương. Escape phụ thuộc quoting mode, encoding, kiểu dữ liệu và phương ngữ. Một lỗi nhỏ trong cách escape có thể mở lại injection. Dùng API bind chính thức của driver.

Mẫu parameterized query:

```sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = ?
  AND status = ?;
```

Các lần gọi chỉ thay customer_id và status. SQL template vẫn giữ nguyên. Điều này giúp tách dữ liệu khỏi cú pháp, đồng thời có thể giúp database/driver tái sử dụng prepared statement hoặc execution plan tùy cơ chế và cấu hình.

---

## 3. Placeholder khác nhau giữa các driver

Một khái niệm giống nhau có cú pháp placeholder khác nhau. Không lấy placeholder của một driver rồi dùng cho driver khác mà không kiểm tra tài liệu.

| Driver / API | Placeholder phổ biến | Ví dụ |
| --- | --- | --- |
| JDBC PreparedStatement | ? theo vị trí | WHERE id = ? |
| Python sqlite3 | ? hoặc named placeholder | WHERE id = ? |
| Python psycopg | %s theo vị trí hoặc named style theo driver | WHERE id = %s |
| Python pyodbc | ? theo vị trí | WHERE id = ? |
| Node.js node-postgres | $1, $2 | WHERE id = $1 |
| Node.js mysql2 | ? | WHERE id = ? |
| SQL Server T-SQL sp_executesql | @parameter_name | WHERE id = @id |
| Oracle PL/SQL dynamic SQL | :1 hoặc tên bind | WHERE id = :1 |

Một số lưu ý:

- JDBC dùng ? và đánh số setter từ 1.
- Python DB-API có thuộc tính paramstyle; qmark, format, pyformat, named và numeric là các kiểu có thể gặp.
- Psycopg dùng %s cho value positional; đây không phải Python string interpolation.
- Node-postgres dùng $1, $2.
- MySQL driver có thể cung cấp API execute với placeholder ?.
- SQL Server trong T-SQL thường khai báo tham số có tên cho sp_executesql.
- Oracle placeholder binding phụ thuộc loại dynamic statement và quy tắc positional/named của NDS.

**Luôn truyền tham số vào API execute/prepare của driver.** Đừng dùng toán tử định dạng chuỗi của ngôn ngữ để thay placeholder trước khi gửi SQL.

---

## 4. Java JDBC: gọi truy vấn có tham số

JDBC là API phổ biến trong Java để làm việc với database quan hệ.

### 4.1. SELECT có hai tham số

```java
String sql = """
    SELECT order_id, placed_at, total_amount
    FROM orders
    WHERE customer_id = ?
      AND status = ?
    ORDER BY placed_at DESC
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);
    ps.setString(2, status);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            Timestamp placedAt = rs.getTimestamp("placed_at");
            BigDecimal total = rs.getBigDecimal("total_amount");
        }
    }
}
```

Thứ tự setter khớp vị trí placeholder: vị trí 1 nhận customerId, vị trí 2 nhận status. Nếu đảo thứ tự, query có thể lỗi kiểu hoặc trả kết quả sai.

### 4.2. INSERT có generated key

```java
String sql = """
    INSERT INTO customers (email, display_name)
    VALUES (?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(
        sql, Statement.RETURN_GENERATED_KEYS)) {

    ps.setString(1, email);
    ps.setString(2, displayName);

    int affected = ps.executeUpdate();
    if (affected != 1) {
        throw new SQLException("Unexpected insert row count: " + affected);
    }

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (keys.next()) {
            long customerId = keys.getLong(1);
        }
    }
}
```

`getGeneratedKeys` phụ thuộc driver/database. Nếu ứng dụng cần generated key, kiểm tra khả năng hỗ trợ và cấu hình của driver thay vì giả định mọi database trả cùng cách.

### 4.3. UPDATE và kiểm tra row count

```java
String sql = """
    UPDATE inventory
    SET quantity = ?
    WHERE sku = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, newQuantity);
    ps.setString(2, sku);

    int affected = ps.executeUpdate();

    if (affected == 0) {
        // Không có hàng nào được cập nhật.
    } else if (affected == 1) {
        // Đúng một hàng được cập nhật.
    } else {
        throw new IllegalStateException(
            "Expected at most one inventory row"
        );
    }
}
```

Nếu sku không phải unique, row count có thể lớn hơn 1. Nếu nghiệp vụ yêu cầu một hàng, cần unique constraint và test row count.

### 4.4. Bind SQL NULL

Không bind chuỗi "NULL". Dùng API NULL có kiểu:

```java
ps.setNull(1, Types.VARCHAR);
ps.setNull(2, Types.INTEGER);
ps.setNull(3, Types.DECIMAL);
```

Kiểu SQL phải tương thích cột/parameter. Một số driver cần kiểu rõ ràng để suy luận đúng khi giá trị là NULL. Nếu dùng setObject, xác nhận driver và target type hỗ trợ cách bind đó. Test NULL riêng vì nó có thể đi qua code path khác với value không NULL.

### 4.5. Bind DECIMAL chính xác

```java
BigDecimal amount = new BigDecimal("123.45");
ps.setBigDecimal(1, amount);
```

Tránh tạo BigDecimal từ double cho tiền:

```java
new BigDecimal(0.1)
```

Vì double là số nhị phân xấp xỉ; constructor có thể giữ biểu diễn nhị phân đó thành nhiều chữ số. Dùng chuỗi thập phân hoặc API tạo từ minor units theo thiết kế.

### 4.6. Bind ngày giờ

JDBC hỗ trợ các kiểu Java thời gian hiện đại qua setter tương ứng theo driver:

```java
ps.setObject(1, LocalDate.of(2026, 5, 1));
ps.setObject(2, LocalDateTime.of(2026, 5, 1, 9, 30));
ps.setObject(3, OffsetDateTime.parse("2026-05-01T09:30:00+07:00"));
```

Không truyền ngày dưới dạng chuỗi phụ thuộc locale như 01/05/2026. Dùng kiểu date/time và thống nhất timezone/instant giữa ứng dụng và database.

---

## 5. Python DB-API: sqlite3, psycopg và pyodbc

Python DB-API 2.0 định nghĩa giao diện chung cho connection/cursor/execute, nhưng placeholder style có thể khác theo driver. Kiểm tra thuộc tính paramstyle hoặc tài liệu driver.

### 5.1. sqlite3 với qmark

```python
import sqlite3

connection = sqlite3.connect("app.db")

sql = """
    SELECT order_id, total_amount
    FROM orders
    WHERE customer_id = ?
      AND status = ?
"""

rows = connection.execute(
    sql,
    (customer_id, status)
).fetchall()
```

Tuple chứa giá trị theo đúng thứ tự placeholder.

### 5.2. sqlite3 với named parameters

```python
sql = """
    SELECT order_id, total_amount
    FROM orders
    WHERE customer_id = :customer_id
      AND status = :status
"""

rows = connection.execute(
    sql,
    {
        "customer_id": customer_id,
        "status": status,
    }
).fetchall()
```

Named parameters giúp đọc query dễ hơn khi có nhiều điều kiện. Tên placeholder phải khớp key được truyền.

### 5.3. psycopg cho PostgreSQL

```python
import psycopg

with psycopg.connect(connection_string) as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT order_id, total_amount
            FROM orders
            WHERE customer_id = %s
              AND status = %s
            """,
            (customer_id, status),
        )
        rows = cur.fetchall()
```

Trong psycopg, %s là placeholder của driver, không phải yêu cầu giá trị phải là Python string. Driver truyền kiểu dữ liệu qua protocol của nó.

Không viết:

```python
cur.execute(
    "SELECT * FROM users WHERE name = '%s'" % username
)
```

Đây là Python string formatting trước khi database nhận câu lệnh, không phải parameter binding.

### 5.4. pyodbc cho SQL Server

```python
import pyodbc

sql = """
    SELECT order_id, total_amount
    FROM dbo.Orders
    WHERE customer_id = ?
      AND status = ?
"""

cursor.execute(sql, customer_id, status)
rows = cursor.fetchall()
```

pyodbc dùng placeholder positional qmark trong ví dụ thông dụng. Kiểu dữ liệu được driver suy luận từ object Python; khi cần, kiểm tra kiểu và conversion của driver.

### 5.5. Bind NULL và Decimal trong Python

```python
from decimal import Decimal

cur.execute(
    """
    INSERT INTO products (sku, description, price)
    VALUES (%s, %s, %s)
    """,
    ("BK-01", None, Decimal("12.50")),
)
```

Python None được driver map sang SQL NULL trong các driver hỗ trợ DB-API. Dùng Decimal cho giá trị thập phân chính xác thay vì float khi lưu tiền.

### 5.6. Connection và transaction

Một số driver quản lý transaction qua context manager; một số cần gọi commit/rollback rõ ràng. Xác định rõ autocommit, semantics của context manager, rollback khi exception và trạng thái connection pool sau khi trả connection. Đừng dựa vào hành vi ngầm mà không kiểm tra tài liệu driver.

---

## 6. Node.js: PostgreSQL và MySQL

### 6.1. node-postgres

node-postgres dùng placeholder đánh số:

```javascript
const result = await client.query(
  "SELECT order_id, total_amount " +
  "FROM orders " +
  "WHERE customer_id = $1 AND status = $2",
  [customerId, status]
);

const rows = result.rows;
```

Giá trị thứ nhất bind vào $1, giá trị thứ hai bind vào $2. Không nội suy input vào SQL text:

```javascript
// Không an toàn nếu customerId đến từ input:
const sql = "SELECT * FROM orders WHERE customer_id = " + customerId;
```

### 6.2. mysql2

```javascript
const [rows] = await pool.execute(
  "SELECT order_id, total_amount " +
  "FROM orders " +
  "WHERE customer_id = ? AND status = ?",
  [customerId, status]
);
```

Dùng execute với placeholder/parameter array theo API của mysql2. Không dùng format string tự nối dữ liệu vào câu SQL.

### 6.3. Kiểu số trong JavaScript

JavaScript Number biểu diễn số nguyên chính xác chỉ tới Number.MAX_SAFE_INTEGER. Với BIGINT database, ID lớn có thể vượt miền an toàn của Number.

Dùng BigInt hoặc biểu diễn chuỗi theo khả năng driver, nhưng không chuyển BIGINT thành Number nếu có nguy cơ mất chính xác. JSON không hỗ trợ BigInt nguyên bản; API cần quy định cách serialize ID lớn, thường là chuỗi decimal.

### 6.4. Decimal và tiền

JavaScript Number dùng IEEE 754 double. Với tiền, cân nhắc gửi decimal dưới dạng chuỗi có định dạng kiểm soát rồi bind vào DECIMAL/NUMERIC, dùng thư viện decimal, hoặc biểu diễn integer minor units nếu miền và đơn vị nghiệp vụ phù hợp. Không dùng phép cộng/trừ float rồi giả định kết quả thập phân chính xác.

---

## 7. Parameter binding bảo vệ điều gì?

Bind parameter tách value khỏi SQL syntax. Nó bảo vệ các vị trí giá trị như:

```sql
WHERE email = ?
  AND created_at >= ?
  AND amount < ?
```

Input có thể chứa dấu nháy đơn/kép, dấu chấm phẩy, comment marker, từ khóa SQL hoặc Unicode. Khi bind đúng, các ký tự này được coi là dữ liệu.

### 7.1. Bind không thay tên bảng

Câu sau không biến placeholder thành table identifier:

```sql
SELECT * FROM ? WHERE id = ?;
```

Placeholder chỉ đại diện value. Nếu tên bảng/cột thay đổi, phải chọn từ allowlist và quote identifier theo DBMS.

Ví dụ Java:

```java
String tableName = switch (reportType) {
    case "daily" -> "daily_orders";
    case "monthly" -> "monthly_orders";
    default -> throw new IllegalArgumentException("Invalid report type");
};

String sql =
    "SELECT report_date, total_amount FROM " +
    quoteIdentifierForKnownDatabase(tableName) +
    " WHERE customer_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);
    // Execute...
}
```

Trong ví dụ, lựa chọn table đến từ mapping cố định phía server. Hàm quote phải được triển khai theo đúng database; không có một hàm quoting portable cho mọi dialect.

### 7.2. ORDER BY động

Không thể bind cột hoặc ASC/DESC bằng value placeholder:

```sql
SELECT * FROM orders ORDER BY ? ?;
```

Hãy map lựa chọn đầu vào sang fragment cố định:

```java
String sortColumn = switch (sortKey) {
    case "date" -> "placed_at";
    case "total" -> "total_amount";
    default -> throw new IllegalArgumentException("Invalid sort key");
};

String direction = switch (sortDirection.toLowerCase(Locale.ROOT)) {
    case "asc" -> "ASC";
    case "desc" -> "DESC";
    default -> throw new IllegalArgumentException("Invalid direction");
};

String sql = "SELECT order_id, placed_at, total_amount " +
             "FROM orders ORDER BY " + sortColumn + " " + direction;
```

Các fragment được chọn từ allowlist. Nếu tên identifier không phải hằng số do ứng dụng kiểm soát, quote theo dialect.

### 7.3. Không nhận raw SQL fragment

Tránh API như:

```text
GET /orders?where=<raw SQL>
GET /report?orderBy=<raw SQL>
```

Thay bằng contract có kiểu:

```json
{
  "status": "PAID",
  "sort": "date",
  "direction": "desc",
  "from": "2026-05-01",
  "to": "2026-06-01"
}
```

Ứng dụng validate các lựa chọn và tự tạo SQL template.

---

## 8. Optional filters và NULL semantics

Một API tìm kiếm có thể nhận các bộ lọc tùy chọn: customerId, status, fromDate/toDate, keyword và includeArchived. Cần phân biệt **không gửi field**, **gửi null**, **gửi empty string** và **gửi giá trị cụ thể**.

### 8.1. Mẫu điều kiện tùy chọn

Một mẫu SQL:

```sql
SELECT order_id, customer_id, status, placed_at
FROM orders
WHERE (? IS NULL OR customer_id = ?)
  AND (? IS NULL OR status = ?);
```

Ứng dụng bind customerId hai lần và status hai lần.

Cách này dễ đọc nhưng có thể làm optimizer khó chọn plan tối ưu trong một số workload, tùy DBMS và statistics. Với nhiều filter, có thể tạo SQL template theo tổ hợp filter có kiểm soát, nhưng mọi value vẫn bind.

### 8.2. Tạo WHERE động an toàn

Ví dụ Java:

```java
List<String> predicates = new ArrayList<>();
List<Object> parameters = new ArrayList<>();

StringBuilder sql = new StringBuilder(
    "SELECT order_id, customer_id, status FROM orders WHERE 1 = 1"
);

if (customerId != null) {
    predicates.add("customer_id = ?");
    parameters.add(customerId);
}

if (status != null) {
    predicates.add("status = ?");
    parameters.add(status);
}

if (fromDate != null) {
    predicates.add("placed_at >= ?");
    parameters.add(fromDate);
}

if (toDateExclusive != null) {
    predicates.add("placed_at < ?");
    parameters.add(toDateExclusive);
}

for (String predicate : predicates) {
    sql.append(" AND ").append(predicate);
}

try (PreparedStatement ps = connection.prepareStatement(sql.toString())) {
    for (int i = 0; i < parameters.size(); i++) {
        ps.setObject(i + 1, parameters.get(i));
    }
    // Execute...
}
```

Các fragment trong predicates là chuỗi hằng do code tạo, không đến từ input. Giá trị nằm trong parameters và được bind.

### 8.3. Empty string trong filter

Nếu keyword là empty string, API có thể định nghĩa:

- Không gửi keyword: không áp dụng filter.
- Empty string: tìm tên rỗng.
- Whitespace-only: trim rồi coi là không filter.
- Hoặc từ chối empty/whitespace.

Đừng tự trim hoặc chuyển empty thành NULL nếu contract chưa quy định. Oracle còn có semantics empty string thành NULL trong kiểu ký tự.

### 8.4. NULL có thể có nghĩa “lọc các hàng NULL”

Nếu client muốn tìm hàng có status NULL, không dùng cùng ý nghĩa với “không áp dụng filter”. Có thể cần filter mode tường minh:

```json
{"statusFilter": {"mode": "IS_NULL"}}
```

hoặc:

```json
{"statusFilter": {"mode": "EQUALS", "value": "PAID"}}
```

Cách biểu diễn này tránh nhập nhằng giữa bỏ filter và tìm giá trị NULL.

---

## 9. Dynamic IN list

Một request có thể truyền nhiều ID. Không nối trực tiếp danh sách input thành IN (101, 102, 103). Thay vào đó, bind từng phần tử hoặc dùng kiểu tham số danh sách phù hợp DBMS.

### 9.1. JDBC tạo placeholder theo số phần tử

```java
List<Long> customerIds = List.of(101L, 102L, 103L);

if (customerIds.isEmpty()) {
    return List.of();
}

String placeholders = String.join(
    ",",
    Collections.nCopies(customerIds.size(), "?")
);

String sql =
    "SELECT order_id, customer_id FROM orders " +
    "WHERE customer_id IN (" + placeholders + ")";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (int i = 0; i < customerIds.size(); i++) {
        ps.setLong(i + 1, customerIds.get(i));
    }

    try (ResultSet rs = ps.executeQuery()) {
        // Map rows...
    }
}
```

Chỉ số lượng dấu ? được sinh từ kích thước danh sách. Mỗi ID vẫn được bind riêng.

### 9.2. Danh sách rỗng

Không tạo IN () rồi hy vọng mọi DBMS xử lý giống nhau. Xác định contract:

- Danh sách rỗng có nghĩa không chọn customer nào: trả 0 hàng.
- Hoặc danh sách rỗng có nghĩa bỏ filter: chỉ khi nghiệp vụ định nghĩa rõ.
- Hoặc từ chối request.

Giới hạn số phần tử để tránh query quá lớn, vượt số parameter tối đa hoặc tạo plan/cache không cần thiết.

### 9.3. Array và table-valued parameters

Một số lựa chọn theo DBMS:

- PostgreSQL có array parameter và unnest.
- SQL Server hỗ trợ table-valued parameters qua user-defined table type.
- Có thể dùng temporary/staging table cho batch lớn.
- MySQL có thể dùng temporary table hoặc JSON table expansion tùy phiên bản.
- SQLite có thể insert ID vào temporary table rồi JOIN.

Chọn cách phù hợp kích thước batch, driver và query plan.

---

## 10. Validation đầu vào theo nhiều lớp

Validation nên thực hiện theo thứ tự dễ hiểu và có lỗi cụ thể.

### 10.1. Parse và kiểm tra kiểu

Ví dụ quantity API nhận một giá trị JSON:

- Integer JSON hợp lệ.
- Decimal 1.5 không phải integer nếu contract yêu cầu số nguyên.
- Chuỗi "10" chỉ chấp nhận nếu API cho phép coercion.
- Boolean không được tự chuyển thành 0/1 nếu contract không cho phép.
- NULL chỉ hợp lệ nếu field optional.

Đặc biệt trong Python, bool là subclass của int; kiểm tra kiểu quá rộng có thể chấp nhận True như số 1. Trong JavaScript, Number có thể là số nguyên hoặc float; cần kiểm tra Number.isInteger khi yêu cầu integer.

### 10.2. Kiểm tra miền nghiệp vụ

```java
if (quantity < 0 || quantity > 100) {
    throw new ValidationException("quantity must be between 0 and 100");
}
```

Database cũng nên có:

```sql
quantity INTEGER NOT NULL
    CHECK (quantity BETWEEN 0 AND 100)
```

Validation trả lỗi sớm, constraint bảo vệ dữ liệu kể cả khi có đường ghi khác bỏ qua ứng dụng.

### 10.3. Kiểm tra chuỗi

Xác định empty có hợp lệ không, whitespace-only có hợp lệ không, max length tính theo ký tự hay byte, Unicode normalization có cần không, có cho phép newline/control character không và có phân biệt hoa/thường không.

Không dùng một phép length duy nhất cho mọi hệ. Đơn vị độ dài của ứng dụng phải khớp contract và DBMS.

### 10.4. Kiểm tra số thập phân

Đối với DECIMAL(p,s), validation cần xác định miền giá trị, số chữ số phần nguyên tối đa, số chữ số thập phân cho phép, chính sách rounding/reject khi scale vượt, dấu âm và overflow trong phép tính trung gian.

Đừng dùng float để validate giá trị tiền nếu có thể parse trực tiếp sang decimal.

### 10.5. Kiểm tra ngày giờ

- Parse định dạng chuẩn, ưu tiên ISO 8601.
- Xác định date-only hay instant.
- Nếu là instant, yêu cầu offset/timezone hoặc quy định timezone mặc định.
- Kiểm tra from < to.
- Dùng khoảng nửa mở cho range timestamp.
- Kiểm tra min/max theo kiểu DBMS.

### 10.6. Validation không được thay constraint

Hai request có thể chạy đồng thời sau khi cùng vượt qua validation “SKU chưa tồn tại”. Chỉ unique constraint mới bảo vệ tính duy nhất ở database. Tương tự, check quantity ở ứng dụng không ngăn một batch job khác ghi số âm nếu database không có CHECK.

---

## 11. Kiểm thử SQL injection

Test injection phải chứng minh input được coi là data, không làm thay đổi câu lệnh.

Các chuỗi thử có thể gồm:

```text
'
''
' OR '1'='1
' OR 1=1 --
"; DROP TABLE ...
comment markers
Unicode quote lookalikes
very long input
```

Không cần chạy payload phá hoại trên database thật. Dùng schema/database test riêng và tài khoản ít quyền.

### 11.1. Test hành vi mong đợi

Giả sử endpoint tìm username:

1. Tạo một user bình thường.
2. Gửi username chứa dấu nháy.
3. Xác nhận query không lỗi cú pháp do input.
4. Xác nhận chỉ trả hàng có username khớp đúng giá trị dữ liệu.
5. Xác nhận số hàng và các bảng khác không thay đổi.
6. Kiểm tra log không ghi raw secret.

### 11.2. Test comment marker

Input chứa -- hoặc /* ... */ phải được lưu/tìm như chuỗi nếu kiểu dữ liệu cho phép, không được biến phần còn lại của SQL thành comment.

### 11.3. Test bằng quyền thấp

Tài khoản test chỉ nên có quyền SELECT/INSERT/UPDATE cần thiết. Nếu ứng dụng bị lỗi injection, least privilege giới hạn hậu quả. Test security không nên dựa vào tài khoản database quản trị.

### 11.4. Parameterized query không bảo vệ mọi phần SQL

Bind bảo vệ value placeholder. Nó không bảo vệ table/column name ghép từ input, ORDER BY fragment ghép trực tiếp, SQL expression/operator do client gửi, stored procedure tự ghép raw SQL hoặc quyền truy cập object ngoài phạm vi nghiệp vụ.

Các cấu trúc này phải được map từ allowlist và kiểm soát quyền.

---

## 12. Kiểm thử NULL, empty và field không được gửi

Một API JSON có thể có ba dạng:

```json
{}
```

```json
{"nickname": null}
```

```json
{"nickname": ""}
```

Ý nghĩa có thể là:

| Payload | Ý nghĩa tiềm năng |
| --- | --- |
| Không có key | Không thay đổi field khi PATCH hoặc dùng default khi CREATE |
| Key có null | Xóa giá trị/ghi SQL NULL |
| Key empty | Ghi chuỗi rỗng nếu cho phép |
| Key có text | Ghi text đó |

Không tự gộp các trường hợp.

### 12.1. PATCH khác PUT

Một endpoint PATCH có thể cần phân biệt field không xuất hiện với field xuất hiện và có null. Một DTO đơn giản chỉ có nullable property có thể không giữ được thông tin “missing” so với “explicit null”; cần wrapper/presence flag hoặc parse raw JSON object.

### 12.2. Test matrix

| Test | Input | Expected behavior |
| --- | --- | --- |
| M01 | Field không có | Không thay đổi khi PATCH |
| M02 | Field = null | Xóa/ghi NULL nếu contract cho phép |
| M03 | Field = empty string | Ghi empty hoặc reject theo contract |
| M04 | Field = whitespace | Trim/reject/preserve theo policy |
| M05 | Field = text hợp lệ | Cập nhật giá trị |
| M06 | Field vượt length | Validation error hoặc DB constraint error được map đúng |

Đối với Oracle, empty string ở kiểu ký tự được coi là NULL; nếu contract cần phân biệt, phải có cách biểu diễn bổ sung.

---

## 13. Kiểm thử số âm, zero và giá trị biên

Giả sử contract quantity là integer trong khoảng 0..100.

| Input | Kỳ vọng |
| ---: | --- |
| -1 | Reject |
| 0 | Accept |
| 1 | Accept |
| 99 | Accept |
| 100 | Accept |
| 101 | Reject |
| NULL | Reject nếu required |
| 1.5 | Reject nếu integer-only |
| abc | Reject khi parse/type validation |

Kiểm tra cả hai lớp:

1. API validation trả lỗi phù hợp.
2. Database constraint vẫn từ chối nếu gọi SQL trực tiếp hoặc qua một đường ghi khác.

### 13.1. Biên kiểu số

Với SMALLINT signed, test MIN, MAX, MIN-1 và MAX+1. Với BIGINT, kiểm tra ứng dụng có giữ chính xác số lớn hay không. JavaScript Number không biểu diễn chính xác mọi BIGINT; Java BigInteger/Long và Python int có semantics khác nhau.

### 13.2. Decimal

Với DECIMAL(8,2), test 0, -0.01, 0.01, 1.239, 999999.99, 1000000.00, NULL và chuỗi không phải số. Đọc lại giá trị lưu để xác nhận rounding/scale. Không chỉ kiểm tra execute thành công.

---

## 14. Kiểm thử chuỗi và Unicode từ ứng dụng

Đầu vào chuỗi phải test cả độ dài, encoding và nội dung:

- Empty string.
- Một dấu cách.
- Tab/newline.
- Chuỗi ở max length.
- Chuỗi dài hơn max một ký tự.
- Tiếng Việt có dấu.
- Emoji.
- Combining character.
- Dấu nháy và ký tự SQL đặc biệt.
- Ký tự điều khiển theo policy.

### 14.1. Ký tự không đồng nghĩa byte

Một chuỗi UTF-8 có thể chiếm nhiều byte cho một ký tự. SQL Server NVARCHAR dùng byte-pairs UTF-16; PostgreSQL VARCHAR(n) đếm ký tự theo định nghĩa PostgreSQL; MySQL phụ thuộc character set; Oracle có BYTE/CHAR length semantics; SQLite không tự enforce VARCHAR(n).

Validation phía ứng dụng phải hiểu giới hạn database thực tế, đặc biệt nếu cùng một API ghi vào nhiều DBMS.

### 14.2. Không trim mù quáng

Nếu ứng dụng tự trim tất cả chuỗi, nó có thể thay đổi password, mã định danh, nội dung văn bản hoặc giá trị có ý nghĩa khoảng trắng. Trim chỉ áp dụng theo field-specific policy.

Ví dụ display name có thể trim hai đầu; nội dung ghi chú có thể giữ newline; password không nên tự trim nếu contract không quy định.

### 14.3. Collation và unique

Hai chuỗi khác nhau về hoa/thường hoặc Unicode có thể được collation coi là bằng nhau. Test unique key bằng các cặp abc/ABC, tên có/không dấu, hai dạng Unicode normalization, dấu cách cuối, empty và NULL theo DBMS.

Kỳ vọng phải dựa vào collation/index thực tế, không dựa vào so sánh ở ứng dụng.

---

## 15. Kiểm thử ngày giờ và khoảng tìm kiếm

Một API lọc đơn hàng trong tháng nên gửi from/to có timezone hoặc date-only semantics rõ.

```sql
SELECT order_id, placed_at
FROM orders
WHERE placed_at >= ?
  AND placed_at < ?;
```

Bind đầu tháng và đầu tháng kế tiếp. Không tạo mốc 23:59:59.999 vì timestamp có thể lưu precision cao hơn milliseconds.

### 15.1. Ma trận ngày giờ

- Đúng tại from: phải được lấy.
- Ngay trước from: bị loại.
- Ngay trước to: được lấy.
- Đúng tại to: bị loại.
- Ngày nhuận.
- Cuối tháng.
- Timestamp có offset khác nhau nhưng cùng instant.
- Giá trị thiếu timezone nếu API yêu cầu offset.
- Timestamp có microseconds khi cột chỉ lưu milliseconds.

### 15.2. Typed parameter

Bind kiểu Date/Time của driver thay vì gửi chuỗi phụ thuộc locale. Với timestamp instant, thống nhất UTC hoặc quy tắc timezone đã được định nghĩa. Đọc lại để xác nhận precision và timezone semantics.

---

## 16. Transaction khi ứng dụng gọi nhiều câu lệnh

Một nghiệp vụ có thể gồm nhiều statement:

```text
BEGIN
  INSERT order header
  INSERT order items
  UPDATE inventory
  INSERT outbox event
COMMIT
```

Nếu một bước lỗi, rollback toàn bộ thay đổi trong transaction.

### 16.1. JDBC transaction

```java
try {
    connection.setAutoCommit(false);

    // Insert order header.
    // Insert order items.
    // Update inventory.
    // Insert outbox event.

    connection.commit();
} catch (SQLException | RuntimeException ex) {
    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        ex.addSuppressed(rollbackError);
    }
    throw ex;
} finally {
    // Restore connection state if this connection is reused.
}
```

Trong connection pool, cần bảo đảm connection được trả về với autocommit/isolation/read-only state đúng. Driver/pool có thể reset một số trạng thái, nhưng ứng dụng không nên dựa vào giả định không kiểm chứng.

### 16.2. Python transaction

Một số driver hỗ trợ context manager để commit khi thành công và rollback khi exception. Cần đọc tài liệu cụ thể: semantics của connection context manager và cursor context manager không giống nhau giữa mọi driver.

### 16.3. Test rollback

Một integration test nên cố tình làm bước cuối thất bại, sau đó query lại xác nhận các bước trước cũng không để lại thay đổi nếu yêu cầu atomicity.

Không chỉ assert exception. Assert database state sau rollback.

### 16.4. External side effect

Không gửi email hoặc gọi API ngoài trước khi transaction commit thành công. Database rollback không thể hoàn tác một HTTP request đã gửi. Dùng transactional outbox nếu cần phát event đáng tin cậy sau commit.

---

## 17. Kiểm thử kết quả và lỗi từ database

Một test tích hợp cần xác nhận nhiều hơn status HTTP:

- Số hàng được tác động.
- Khóa được tạo.
- Giá trị đọc lại.
- Constraint có được thực thi.
- Transaction có commit/rollback đúng.
- Không có hàng duplicate.
- Lỗi được map đúng loại.
- Không lộ SQL text hoặc dữ liệu nhạy cảm trong response.

### 17.1. Phân biệt lỗi validation và lỗi database

| Tình huống | Lớp phát hiện thường phù hợp | API response minh họa |
| --- | --- | --- |
| Thiếu field required | Request validation | 400 |
| Quantity ngoài miền | Validation và CHECK | 400 hoặc 422 |
| Email duplicate | UNIQUE constraint | 409 |
| Foreign key không tồn tại | FK constraint | 409/422 tùy contract |
| Database unavailable | Connection/infra layer | 503 |
| SQL syntax bug | Application defect | 500 |
| Deadlock/serialization failure | Transaction layer | Retry có giới hạn hoặc lỗi tạm thời |

HTTP status chỉ là ví dụ. API contract cần định nghĩa cụ thể. Không trả stack trace, connection string, SQL text hoặc parameter nhạy cảm cho client.

### 17.2. Không nuốt lỗi

Không viết:

```java
try {
    ps.executeUpdate();
} catch (SQLException ex) {
    return 0;
}
```

Cách này làm caller tưởng không có hàng nào được ghi, trong khi statement có thể thất bại. Phân loại lỗi có chủ đích, ghi log correlation ID và truyền lỗi phù hợp lên tầng gọi.

### 17.3. SQLSTATE/vendor code

Test nên kiểm tra mã lỗi cụ thể khi muốn xác nhận constraint. Ví dụ PostgreSQL có SQLSTATE 23505 cho unique violation, 23502 cho NOT NULL, 23503 cho foreign key và 23514 cho CHECK. Driver của DBMS khác có mã riêng.

Không coi bất kỳ exception nào là “pass” cho test mong constraint violation.

---

## 18. Kiểm thử với nhiều lớp

Một chiến lược tốt có nhiều tầng:

| Tầng test | Mục tiêu | Có cần database thật? |
| --- | --- | --- |
| Unit test validation | Parse, type, range, required/optional | Không |
| Unit test query builder | Chỉ tạo fragment từ allowlist, placeholder đúng | Thường không |
| Driver test | Binding và type conversion thực tế | Có |
| Repository integration test | SQL, constraint, mapping và transaction | Có |
| API integration test | Request-to-database behavior và error mapping | Có |
| Security test | Injection, authorization, tenant isolation | Môi trường cô lập |
| Concurrency test | Race, lock, unique và retry | Có nhiều connection |
| Migration test | Schema và semantics trên DBMS đích | Có |

Unit test không chứng minh driver bind đúng kiểu hoặc DBMS có semantics như giả định. Integration test mới kiểm tra được những hành vi này.

### 18.1. Unit test validation

Test các trường hợp biên trực tiếp: required missing, explicit null, empty string, whitespace, min-1/min/max/max+1, decimal quá scale, date không hợp lệ và Unicode vượt length.

### 18.2. Repository integration test

Dùng database test cùng engine/version với production khi có thể. Tạo schema fixture, chạy repository method, đọc lại giá trị và rollback/dọn dữ liệu.

Nếu dùng database container, pin image/version để tránh test chạy trên một phiên bản khác giữa máy dev và CI.

### 18.3. API integration test

Gửi request HTTP thực qua validation/controller/service/repository đến database test. Xác nhận status, response schema và persisted state.

### 18.4. Contract test cross-database

Nếu ứng dụng hỗ trợ nhiều DBMS, cùng một test suite nghiệp vụ có thể chạy qua adapter riêng cho mỗi engine. Những semantics khác nhau (empty string, unique NULL, timestamp, length) phải có expected behavior riêng hoặc được chuẩn hóa bằng contract ứng dụng.

---

## 19. Ví dụ JUnit cho repository JDBC

Một test minh họa dùng JUnit 5 và datasource test đã cấu hình:

```java
@Test
void insertsAndReadsBackBoundaryQuantity() throws Exception {
    String insertSql = """
        INSERT INTO inventory (sku, quantity)
        VALUES (?, ?)
        """;

    try (Connection connection = dataSource.getConnection();
         PreparedStatement insert = connection.prepareStatement(insertSql)) {

        insert.setString(1, "TEST-BK-01");
        insert.setInt(2, 0);

        int affected = insert.executeUpdate();
        assertEquals(1, affected);

        try (PreparedStatement select = connection.prepareStatement(
                "SELECT quantity FROM inventory WHERE sku = ?")) {

            select.setString(1, "TEST-BK-01");

            try (ResultSet rs = select.executeQuery()) {
                assertTrue(rs.next());
                assertEquals(0, rs.getInt("quantity"));
                assertFalse(rs.next());
            }
        }
    }
}
```

Test cần fixture/cleanup hoặc transaction rollback để không để lại dữ liệu. Nếu test chạy song song, dùng key duy nhất theo test run hoặc schema/database riêng.

### 19.1. Test CHECK violation

```java
@Test
void rejectsNegativeQuantity() throws Exception {
    String sql = """
        INSERT INTO inventory (sku, quantity)
        VALUES (?, ?)
        """;

    try (Connection connection = dataSource.getConnection();
         PreparedStatement ps = connection.prepareStatement(sql)) {

        ps.setString(1, "TEST-NEGATIVE");
        ps.setInt(2, -1);

        SQLException error = assertThrows(
            SQLException.class,
            ps::executeUpdate
        );

        // Assert SQLState/vendor code theo DBMS đang test.
        assertNotNull(error.getSQLState());
    }
}
```

Trong test thực tế, không chỉ assert SQLState khác NULL; hãy assert đúng mã CHECK violation của DBMS/driver. Đồng thời xác nhận không có hàng được ghi.

### 19.2. Test NULL và empty tách riêng

Viết hai test độc lập: một bind SQL NULL bằng setNull, một bind empty bằng setString(1, ""). Đọc lại bằng IS NULL và phép so sánh empty theo DBMS.

---

## 20. Ví dụ pytest cho repository Python

Ví dụ SQLite:

```python
def test_optional_value_distinguishes_null_and_empty(db):
    db.execute(
        "INSERT INTO sample (id, note) VALUES (?, ?)",
        (1, None),
    )
    db.execute(
        "INSERT INTO sample (id, note) VALUES (?, ?)",
        (2, ""),
    )

    null_rows = db.execute(
        "SELECT id FROM sample WHERE note IS NULL"
    ).fetchall()

    empty_rows = db.execute(
        "SELECT id FROM sample WHERE note = ?",
        ("",),
    ).fetchall()

    assert null_rows == [(1,)]
    assert empty_rows == [(2,)]
```

Đây là test semantics SQLite; khi chạy với Oracle, expected behavior của empty string sẽ khác.

### 20.1. Parametrize boundary values

```python
import pytest

@pytest.mark.parametrize(
    "quantity, accepted",
    [
        (-1, False),
        (0, True),
        (1, True),
        (100, True),
        (101, False),
    ],
)
def test_quantity_boundary(db, quantity, accepted):
    if accepted:
        db.execute(
            "INSERT INTO inventory (sku, quantity) VALUES (?, ?)",
            (f"SKU-{quantity}", quantity),
        )
    else:
        with pytest.raises(Exception):
            db.execute(
                "INSERT INTO inventory (sku, quantity) VALUES (?, ?)",
                (f"SKU-{quantity}", quantity),
            )
```

Ví dụ trên minh họa cách tham số hóa test, nhưng bộ test thực tế cần assert đúng loại exception/SQLSTATE thay vì bắt Exception tổng quát. Mỗi case cũng cần cleanup hoặc transaction fixture.

---

## 21. Kiểm thử SQL injection bằng test case cụ thể

Giả sử repository có method tìm user theo email. Test:

1. Insert một user có email hợp lệ.
2. Gọi method với email bình thường; xác nhận đúng một user.
3. Gọi method với chuỗi có dấu nháy và SQL comment marker; xác nhận kết quả là tìm literal đó hoặc không tìm thấy.
4. Xác nhận không có user khác bị trả về.
5. Xác nhận số hàng và schema không thay đổi ngoài dự kiến.

Ví dụ payload test:

```text
x' OR '1'='1
admin'--
' OR 1=1 /*
```

Với parameterized query, các chuỗi này không được diễn giải thành điều kiện SQL.

### 21.1. Không chỉ test payload nổi tiếng

Một implementation lỗi có thể bị lộ bởi dấu nháy đơn/kép, backslash theo SQL mode, Unicode quote, comment marker, chuỗi rất dài, null byte hoặc ký tự điều khiển tùy driver/encoding.

Nhưng test chính vẫn là kiểm tra kiến trúc: mọi value được bind, identifier được allowlist, quyền database tối thiểu.

### 21.2. Test authorization riêng

Parameterized query ngăn thay đổi cú pháp, nhưng không ngăn người dùng hợp lệ hỏi dữ liệu tenant khác nếu query thiếu điều kiện tenant. Test phải xác nhận mọi truy vấn tenant-scoped đều bind tenant ID từ principal đã xác thực, không tin tenant ID tùy ý trong request.

---

## 22. Kiểm thử optional filters và query plan

Một query có nhiều filter tùy chọn có thể có nhiều plan khác nhau:

```sql
WHERE (? IS NULL OR customer_id = ?)
  AND (? IS NULL OR status = ?)
  AND (? IS NULL OR placed_at >= ?)
```

Các test nên gồm không có filter, chỉ customerId, chỉ status, chỉ date range, tất cả filter, value NULL, giá trị hiếm và giá trị phổ biến.

Đối với bảng lớn, kiểm tra EXPLAIN/actual plan với các tổ hợp thực tế. Một query parameterized không tự bảo đảm plan luôn tối ưu cho mọi tổ hợp.

Có thể xây dựng các template SQL theo tổ hợp filter để tránh điều kiện OR rộng, miễn là cấu trúc fragment do code kiểm soát và value vẫn bind.

### 22.1. Paging

Paging cũng cần validate:

- pageSize phải lớn hơn 0.
- pageSize có max cap.
- offset không âm.
- phép tính offset = page * size không overflow.
- sort key và direction phải allowlist.
- tie-break bằng unique key để thứ tự ổn định.

Bind pageSize/offset nếu DBMS/driver hỗ trợ ở vị trí đó. Không nhận raw ORDER BY từ client.

---

## 23. Kiểm thử dữ liệu đầu vào theo ma trận

Một ma trận thực tế cho API tạo product:

| Field | Input | Expected |
| --- | --- | --- |
| sku | missing | Reject |
| sku | NULL | Reject |
| sku | empty | Reject |
| sku | whitespace-only | Reject sau policy trim |
| sku | đúng max length | Accept |
| sku | max + 1 | Reject |
| displayName | NULL | Theo contract |
| displayName | Unicode tiếng Việt | Accept |
| displayName | emoji | Theo contract/schema |
| quantity | -1 | Reject |
| quantity | 0 | Theo nghiệp vụ |
| quantity | max | Accept |
| quantity | max + 1 | Reject |
| price | 0 | Theo nghiệp vụ |
| price | âm | Reject nếu không cho phép |
| price | nhiều chữ số thập phân | Reject hoặc round theo contract |
| active | missing | DEFAULT hoặc validation |
| active | NULL | Theo contract |
| createdAt | ngày sai | Reject |
| createdAt | timestamp không offset | Theo contract timezone |

Đừng dùng một rule chung cho tất cả field. Mỗi field có requiredness, type, length, range, normalization và null semantics riêng.

---

## 24. Error mapping và log an toàn

Khi database từ chối input, API nên trả lỗi đủ hữu ích nhưng không lộ chi tiết nội bộ.

| Lỗi database | Mapping có thể dùng |
| --- | --- |
| Unique violation | Conflict, nêu field trùng nếu an toàn |
| FK violation | Conflict hoặc validation error theo contract |
| CHECK violation | Validation/domain error |
| NOT NULL violation | Bad request/domain validation |
| Deadlock | Retry có giới hạn hoặc transient error |
| Connection timeout | Service unavailable |
| Syntax/permission bug | Internal server error, log cho operator |

Không đưa raw SQL, parameter nhạy cảm, stack trace, hostname hoặc connection string vào response client.

Log có thể gồm request/correlation ID, tên repository operation, query fingerprint/template ID, SQLSTATE/vendor code, thời gian và row count, loại tham số/trạng thái validation và giá trị đã mask nếu thực sự cần.

Không log password, token, session secret, dữ liệu thanh toán hoặc PII không cần thiết.

---

## 25. Test retry, idempotency và concurrency

Một request có thể được gửi lại do timeout dù database đã commit. Nếu thao tác INSERT order không có idempotency key, retry có thể tạo hai order.

### 25.1. Idempotency key

```sql
CREATE TABLE payment_requests (
    idempotency_key VARCHAR(80) PRIMARY KEY,
    payment_id BIGINT,
    status VARCHAR(20) NOT NULL
);
```

Ứng dụng bind idempotency key và xử lý duplicate theo contract. Test gửi cùng request nhiều lần và xác nhận chỉ một kết quả nghiệp vụ.

### 25.2. Concurrency test

Dùng hai connection:

1. Cùng đọc một version.
2. Cùng gửi update theo expected version.
3. Một update thành công.
4. Update còn lại không ghi đè âm thầm.
5. Đọc lại version cuối.
6. Kiểm tra không tạo duplicate hoặc mất dữ liệu.

### 25.3. Retry có giới hạn

Không retry mọi lỗi. Unique violation có thể là kết quả nghiệp vụ; syntax error không tự hết; deadlock/serialization failure có thể retry toàn transaction nếu operation idempotent và policy cho phép.

Backoff, giới hạn số lần retry và log correlation ID để tránh retry storm.

---

## 26. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nối input vào SQL string | SQL injection | Prepared/parameterized query |
| Dùng string formatting để thay placeholder | Không có binding thực sự | Truyền parameter riêng qua driver |
| Dùng sai placeholder của driver | Lỗi syntax hoặc bind sai | Đọc paramstyle/tài liệu driver |
| Đảo thứ tự JDBC setter | Sai dữ liệu hoặc lỗi kiểu | Đánh số placeholder và test |
| Bind chuỗi "NULL" | Lưu text NULL thay vì SQL NULL | setNull/None/null theo driver |
| Bind float cho tiền | Sai số thập phân | Decimal/BigDecimal/minor units |
| Không kiểm tra integer range | Overflow hoặc mất chính xác | Validate min/max và kiểu ứng dụng |
| Dùng Number cho BIGINT trong JS | Mất precision | BigInt/chuỗi theo driver contract |
| Dùng placeholder cho tên bảng | Không hoạt động như identifier | Allowlist + quote identifier |
| Ghép raw ORDER BY | Injection | Allowlist column/direction |
| Dùng IN () với list rỗng | SQL không portable | Xác định semantics empty list |
| Nối value trong IN list | Injection | Bind từng value/array/table parameter |
| Gộp missing, NULL và empty | PATCH/CREATE sai | Presence-aware request model |
| Trim mọi chuỗi | Làm thay đổi password/nội dung | Policy theo từng field |
| Chỉ validation ở API | Đường ghi khác phá constraint | Database constraints |
| Chỉ dựa constraint để validate | Lỗi trả về muộn, UX kém | Validate sớm và constraint cuối |
| Nuốt SQLException | Caller tưởng thành công | Phân loại và truyền lỗi |
| Bắt mọi exception trong test | Test pass giả | Assert đúng SQLSTATE/vendor code |
| Không đọc lại dữ liệu | Bỏ sót rounding/truncation | Assert persisted value |
| Không rollback fixture | Test ảnh hưởng lẫn nhau | Transaction/cleanup |
| Gửi side effect trước commit | Side effect không rollback | Transactional outbox |
| Chỉ test một connection | Bỏ sót race | Concurrency test |
| Tin tenant ID từ request | Truy cập chéo tenant | Lấy tenant từ principal và bind |
| Không cap page size/list size | Query quá lớn, cạn tài nguyên | Giới hạn request |
| Log raw parameter | Lộ PII/secret | Mask/fingerprint |

---

## 27. Bài tập thực hành

### Bài 1. PreparedStatement

Viết JDBC SELECT tìm order theo customer_id và status. Bind đúng kiểu và đọc order_id/total_amount.

### Bài 2. SQL injection

Một repository nối username vào WHERE. Hãy viết lại bằng PreparedStatement và nêu test chứng minh input chỉ được coi là dữ liệu.

### Bài 3. Placeholder style

So sánh placeholder của JDBC, Python sqlite3, psycopg, pyodbc, node-postgres và SQL Server sp_executesql. Vì sao không thể copy nguyên query giữa các driver?

### Bài 4. SQL NULL qua JDBC

Viết cách bind NULL cho VARCHAR và INTEGER. Vì sao chuỗi "NULL" không tương đương SQL NULL?

### Bài 5. Decimal

Viết JDBC bind BigDecimal cho amount. Vì sao new BigDecimal(0.1) có thể tạo kết quả không mong đợi?

### Bài 6. Optional filter

API nhận customerId tùy chọn. Mô tả hai cách viết query: điều kiện OR với NULL và xây WHERE fragment có kiểm soát. Nêu trade-off.

### Bài 7. PATCH semantics

Phân biệt JSON không có field nickname, nickname null và nickname empty string. Thiết kế model để không mất thông tin missing/null.

### Bài 8. Dynamic ORDER BY

API nhận sort=date/total và direction=asc/desc. Viết allowlist. Vì sao không bind trực tiếp hai giá trị này bằng dấu hỏi?

### Bài 9. Dynamic IN

Ứng dụng JDBC nhận list 3 ID. Sinh placeholder và bind từng ID. Xử lý list rỗng như thế nào?

### Bài 10. Python sqlite3

Viết query với qmark placeholders và tuple parameters. Viết lại bằng named parameters.

### Bài 11. Psycopg

Viết psycopg query dùng %s. Vì sao không dùng Python %-formatting để ghép input?

### Bài 12. Node PostgreSQL

Viết node-postgres query dùng $1 và $2. Nêu rủi ro khi nội suy input vào SQL text.

### Bài 13. BIGINT trong JavaScript

Vì sao Number có thể mất chính xác với BIGINT? Đề xuất cách truyền ID lớn qua JSON/API.

### Bài 14. Validation và constraint

Một API validate quantity >= 0 nhưng database không có CHECK. Một batch job khác ghi quantity = -5. Vì sao validation API không đủ? Viết constraint phù hợp.

### Bài 15. SQL injection test

Đề xuất bộ input có dấu nháy, comment marker, Unicode và chuỗi dài. Nêu expected behavior của parameterized query.

### Bài 16. Error mapping

Phân biệt unique violation, check violation, connection timeout và SQL syntax bug. Vì sao không trả raw SQL exception cho client?

### Bài 17. Transaction rollback

Một service insert order header rồi insert order item lỗi. Thiết kế transaction và test xác nhận không còn order header sau rollback.

### Bài 18. External side effect

Vì sao không gửi email ngay sau INSERT nhưng trước COMMIT? Mô tả transactional outbox.

### Bài 19. Boundary input

Thiết kế test quantity trong miền 0..100 với NULL, -1, 0, 1, 99, 100, 101, 1.5 và abc.

### Bài 20. Chuỗi Unicode

Với VARCHAR(20), đề xuất test tiếng Việt, emoji, combining mark và chuỗi dài 21 ký tự. Vì sao cần biết length semantics của DBMS?

### Bài 21. Date range

Viết query lấy tháng 5/2026 bằng from-inclusive/to-exclusive. Nêu test tại đúng mốc to.

### Bài 22. Test SQLSTATE

Test mong CHECK violation nhưng driver báo lỗi kết nối. Kết quả test phải là gì? Cần assert những trường nào?

### Bài 23. Concurrency

Hai connection cùng cập nhật quantity đang là 1 với điều kiện quantity > 0. Nêu kết quả mong đợi và invariant.

### Bài 24. Multi-database contract

Ứng dụng hỗ trợ PostgreSQL và Oracle. Một API nhận empty string. Làm thế nào để contract không phụ thuộc semantics empty string khác nhau?

### Bài 25. Test repository hoàn chỉnh

Thiết kế integration test cho method tạo customer gồm email unique, display_name nullable, amount decimal và generated ID. Nêu setup, execute, assertions, error case và cleanup.

---

## 28. Gợi ý lời giải

### Bài 1

```java
String sql = """
    SELECT order_id, total_amount
    FROM orders
    WHERE customer_id = ?
      AND status = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);
    ps.setString(2, status);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("order_id");
            BigDecimal total = rs.getBigDecimal("total_amount");
        }
    }
}
```

### Bài 2

Dùng WHERE username = ?, rồi setString(1, input). Test input có dấu nháy và payload giống SQL; xác nhận query chỉ tìm literal value, không trả user khác và không thay đổi bảng.

### Bài 3

JDBC/pyodbc thường dùng ?, sqlite3 hỗ trợ ? và named forms, psycopg dùng %s, node-postgres dùng $1/$2, T-SQL sp_executesql dùng @name. Placeholder là contract của driver/engine nên phải dùng đúng dialect.

### Bài 4

```java
ps.setNull(1, Types.VARCHAR);
ps.setNull(2, Types.INTEGER);
```

"NULL" là chuỗi bốn ký tự; SQL NULL là null marker.

### Bài 5

```java
ps.setBigDecimal(1, new BigDecimal("0.10"));
```

0.1 dạng double là số nhị phân xấp xỉ; chuyển từ double có thể giữ nhiều chữ số không mong muốn. Tạo từ chuỗi decimal hoặc minor units.

### Bài 6

Cách OR:

```sql
WHERE (? IS NULL OR customer_id = ?)
```

Cách xây WHERE: chỉ thêm predicate nếu customerId có mặt, nhưng fragment là hằng do code tạo và value bind. OR dễ viết nhưng có thể ảnh hưởng plan; dynamic template tăng số dạng query và cần quản lý allowlist.

### Bài 7

Không có key = missing; key null = explicit null; key empty = chuỗi rỗng. Dùng presence flag, wrapper type hoặc parse JSON object để giữ trạng thái field có xuất hiện hay không.

### Bài 8

Map date → placed_at, total → total_amount; map asc/desc sang hai literal cố định. Không bind được identifier/keyword vì placeholder chỉ đại diện value.

### Bài 9

Sinh ba dấu ? từ list size, bind từng ID bằng setLong. Nếu list rỗng, trả 0 hàng hoặc reject theo contract; không tạo IN ().

### Bài 10

```python
rows = connection.execute(
    "SELECT * FROM orders WHERE customer_id = ? AND status = ?",
    (customer_id, status),
).fetchall()
```

Named:

```python
rows = connection.execute(
    "SELECT * FROM orders WHERE customer_id = :customer_id AND status = :status",
    {"customer_id": customer_id, "status": status},
).fetchall()
```

### Bài 11

```python
cur.execute(
    "SELECT * FROM users WHERE username = %s",
    (username,),
)
```

%s là placeholder của psycopg. Python string formatting ghép input trước khi gửi database, làm mất separation giữa SQL và value.

### Bài 12

```javascript
const result = await client.query(
  "SELECT * FROM orders WHERE customer_id = $1 AND status = $2",
  [customerId, status]
);
```

Nội suy input vào SQL text có thể gây injection.

### Bài 13

Number chỉ chính xác mọi integer tới Number.MAX_SAFE_INTEGER. Dùng BigInt/chuỗi theo driver và serialize BIGINT thành chuỗi trong JSON nếu cần giữ chính xác.

### Bài 14

Batch job bỏ qua API validation nên có thể ghi số âm. Thêm CHECK quantity >= 0 và NOT NULL nếu required. Validation API vẫn giữ để trả lỗi sớm.

### Bài 15

Dùng dấu nháy, chuỗi OR 1=1, comment marker, Unicode quote và input dài. Parameterized query coi chúng là literal value; không thay đổi cấu trúc, không trả dữ liệu ngoài điều kiện.

### Bài 16

Unique violation là conflict nghiệp vụ; CHECK violation là dữ liệu ngoài miền; timeout là lỗi hạ tầng; syntax bug là lỗi ứng dụng. Map có chủ đích, log correlation ID và không lộ SQL/stack trace.

### Bài 17

Tắt autocommit, BEGIN transaction, insert header và items, COMMIT nếu tất cả thành công; catch lỗi thì ROLLBACK. Test gây lỗi item rồi query xác nhận header không tồn tại.

### Bài 18

Email không rollback khi transaction database rollback. Ghi outbox event trong cùng transaction, worker chỉ gửi sau khi event đã commit.

### Bài 19

- NULL: reject nếu required.
- -1: reject.
- 0, 1, 99, 100: accept.
- 101: reject.
- 1.5: reject nếu integer-only.
- abc: reject ở parse/type validation.

Kiểm tra cả API response và CHECK constraint ở database.

### Bài 20

Test tiếng Việt, emoji, combining mark, 19/20/21 ký tự. PostgreSQL đếm ký tự; SQL Server VARCHAR tính byte và NVARCHAR dùng byte-pairs; MySQL/Oracle có charset/length semantics; SQLite không cưỡng chế VARCHAR(n) mặc định.

### Bài 21

```sql
WHERE placed_at >= ?
  AND placed_at < ?
```

Bind 2026-05-01 00:00 và 2026-06-01 00:00 theo timezone đã định. Mốc đúng to bị loại.

### Bài 22

Test phải fail vì connection timeout không chứng minh CHECK constraint. Assert SQLSTATE/vendor code, operation, row count và dữ liệu không được ghi.

### Bài 23

Chỉ một update thành công từ 1 xuống 0; update còn lại tác động 0 hàng. Invariant quantity không âm được giữ, có CHECK làm lớp bảo vệ.

### Bài 24

Định nghĩa API field rõ: missing, null và empty là ba trạng thái khác nhau hoặc chuẩn hóa chúng theo policy ở tầng ứng dụng. Với Oracle, không thể lưu empty string phân biệt như PostgreSQL; nếu cần phân biệt phải dùng cờ/trạng thái bổ sung.

### Bài 25

Setup schema và datasource test; tạo fixture hoặc transaction; gọi repository bằng email mới, display_name NULL/empty theo case, BigDecimal và đọc generated ID; query lại assert đúng giá trị/scale; test duplicate email và SQLSTATE unique; rollback hoặc cleanup theo test fixture. Chạy trên cùng engine/version với production.

---

## 29. Quy trình thiết kế test cho một repository method

Trước khi hoàn thành một method truy cập database, hãy xác định:

1. **Input contract:** kiểu, requiredness, null semantics, empty semantics và range của từng field.
2. **SQL template:** cấu trúc cố định; placeholder theo driver.
3. **Binding:** thứ tự/tên parameter, SQL type và cách bind NULL.
4. **Dynamic structure:** table/column/order chỉ đến từ allowlist.
5. **Constraint:** NOT NULL, CHECK, UNIQUE và FK ở database.
6. **Transaction:** statement đơn hay nhiều bước; rollback khi lỗi.
7. **Output:** result set, generated key, row count hoặc RETURNING/OUTPUT.
8. **Error mapping:** validation, constraint, timeout, deadlock và bug.
9. **Test matrix:** valid, invalid, NULL, empty, min/max, Unicode, precision và injection.
10. **Integration:** đúng driver, DBMS và version.
11. **Concurrency:** unique race, lost update, version và retry.
12. **Observability:** correlation ID, query fingerprint, error code, row count; mask dữ liệu nhạy cảm.

Một method chỉ được kiểm thử đầy đủ khi test xác nhận cả dữ liệu đầu vào, câu SQL thực sự được bind, kết quả database và trạng thái sau lỗi.

## 30. Checklist trước khi phát hành

- [ ] Mọi value từ request/file/queue đều được bind qua driver.
- [ ] Không có string formatting nối input vào SQL.
- [ ] Placeholder đúng dialect và đúng thứ tự.
- [ ] NULL được bind bằng API NULL có kiểu.
- [ ] Decimal dùng kiểu chính xác, không dùng float cho tiền nếu cần exactness.
- [ ] BIGINT không mất precision ở tầng ứng dụng.
- [ ] Missing, NULL, empty và whitespace có contract rõ.
- [ ] Identifier/ORDER BY/IN structure được allowlist.
- [ ] Input có type, length, range và timezone validation.
- [ ] Database có constraint bảo vệ invariant quan trọng.
- [ ] Test đúng min, max, min-1, max+1, zero và số âm.
- [ ] Test Unicode, whitespace, empty và NULL.
- [ ] Test SQL injection bằng input được bind.
- [ ] Test generated key, row count và dữ liệu đọc lại.
- [ ] Test SQLSTATE/vendor code đúng.
- [ ] Test transaction rollback và cleanup.
- [ ] Test nhiều connection cho race condition.
- [ ] Không phát side effect trước commit.
- [ ] Test trên DBMS/version và driver giống production.
- [ ] Log không lộ secret, PII hoặc raw parameter không cần thiết.

## 31. Tổng kết

Gọi truy vấn tham số hóa từ ứng dụng là ranh giới quan trọng giữa input không tin cậy và database. SQL template mô tả cấu trúc; parameter binding truyền value; validation kiểm tra hợp đồng nghiệp vụ; constraint bảo vệ dữ liệu cuối cùng; transaction quản lý tính nguyên tử.

Những nguyên tắc cần giữ:

1. **Luôn bind value bằng API của driver.** JDBC, Python DB-API, psycopg, pyodbc và Node.js có placeholder riêng.
2. **Không dùng string formatting để tạo value trong SQL.** Escape thủ công không thay thế parameter binding.
3. **Identifier không phải value.** Table, column, ORDER BY và keyword phải được allowlist rồi quote theo DBMS.
4. **Phân biệt missing, NULL, empty và whitespace.** Đặc biệt khi API hỗ trợ PATCH hoặc nhiều DBMS.
5. **Bind đúng kiểu.** Dùng BigDecimal/Decimal cho số thập phân chính xác, kiểu date/time cho thời gian và xử lý BIGINT đúng ở JavaScript.
6. **Validate sớm, bảo vệ cuối.** Ứng dụng trả lỗi dễ hiểu; database constraint giữ invariant kể cả khi có đường ghi khác.
7. **Test cả dữ liệu và lỗi.** Assert giá trị đọc lại, row count, SQLSTATE, rollback và transaction state.
8. **Kiểm thử đúng môi trường.** Driver, DBMS, version, collation, timezone và SQL mode đều có thể làm thay đổi hành vi.
9. **Test security và concurrency.** Parameterization ngăn injection ở value nhưng không tự cấp quyền đúng, ngăn tenant leak hay giải quyết race.
10. **Chỉ phát side effect sau commit.** Dùng transactional outbox nếu cần gửi sự kiện đáng tin cậy.

Một repository an toàn không chỉ có câu SQL đúng. Nó cần một hợp đồng input rõ ràng, binding đúng kiểu, quyền truy cập có giới hạn và test chứng minh database nhận đúng dữ liệu trong cả trường hợp bình thường lẫn biên.
