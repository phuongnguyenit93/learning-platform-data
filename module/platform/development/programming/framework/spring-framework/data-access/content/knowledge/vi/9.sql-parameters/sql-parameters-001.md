# PreparedStatement và cơ chế tách SQL khỏi giá trị

## Mục tiêu của bài học

Trong ứng dụng Spring dùng JDBC, một câu SQL thường gồm hai phần có vai trò hoàn toàn khác nhau:

1. **Cấu trúc câu lệnh**: từ khóa SQL, bảng, cột, phép toán và logic truy vấn do chương trình xác định.
2. **Giá trị dữ liệu**: email, mã sản phẩm, ID khách hàng, ngày tháng, nội dung tìm kiếm... có thể đến từ HTTP request, file, message queue hoặc database khác.

`PreparedStatement` giúp truyền **các giá trị** vào những vị trí tham số của SQL mà **không biến nội dung của giá trị thành cú pháp SQL**. Đây là kỹ thuật nền tảng để truy vấn đúng dữ liệu và chống SQL injection ở các vị trí có thể bind.

Sau bài này, bạn có thể:

- Phân biệt xây SQL bằng nối chuỗi với chuẩn bị câu SQL rồi bind tham số.
- Hiểu dấu `?`, chỉ số tham số bắt đầu từ **1**, và các hàm `setString`, `setInt`, `setLong`, `setNull`, `setObject`.
- Dùng `PreparedStatement` để `SELECT`, `INSERT`, `UPDATE`; quản lý `Connection`, `ResultSet`, `PreparedStatement` bằng try-with-resources trong JDBC thuần.
- Nhận ra giới hạn của bind parameter: không thay thế tên bảng, tên cột, `ASC/DESC` hay cả một đoạn SQL.
- Liên hệ cách Spring `JdbcTemplate` và `NamedParameterJdbcTemplate` sử dụng tham số, không tự viết mã JDBC mức thấp cho mọi truy vấn.
- Chạy một chương trình **Java 17+**, Spring JDBC + H2 để xác minh giá trị chứa dấu nháy đơn và chuỗi có hình dạng SQL vẫn được xử lý như dữ liệu.
- Tránh các lỗi thường gặp với `NULL`, `IN (...)`, `LIKE`, thứ tự tham số, statement reuse và suy luận sai về hiệu năng.

**Phạm vi:** Bài học nói về **tham số SQL và PreparedStatement trong JDBC/Spring data access**. Nó không thay thế giáo trình phân quyền database, ORM, transaction isolation hoặc tối ưu execution plan.

## 1. Khi ghép giá trị vào SQL, chuyện gì có thể xảy ra?

Giả sử ứng dụng muốn lấy tài khoản theo email do người dùng nhập:

```sql
SELECT id, email, balance
FROM accounts
WHERE email = 'alice@example.test';
```

Cách viết Java sau **không an toàn** khi `email` đến từ bên ngoài:

```java
// KHÔNG dùng với dữ liệu đầu vào không tin cậy.
String sql = "SELECT id, email, balance FROM accounts WHERE email = '"
        + email + "'";
```

Nếu giá trị chứa dấu nháy đơn, chẳng hạn `O'Reilly@example.test`, SQL sau khi nối chuỗi có thể không còn hợp lệ. Nghiêm trọng hơn, nếu dữ liệu chứa những ký tự có ý nghĩa như dấu nháy, toán tử SQL hay ký hiệu comment, nó có thể làm **thay đổi cấu trúc câu lệnh** thay vì được so sánh như một chuỗi email.

Ví dụ giá trị đầu vào cố tình có hình dạng cú pháp SQL:

```text
' OR 1=1 --
```

Nếu gắn nguyên văn vào vị trí có hai dấu nháy do lập trình viên tự thêm, điều kiện email có thể bị biến đổi thành biểu thức luôn đúng và phần còn lại bị comment; đó là một dạng **SQL injection**. Đây là ví dụ giải thích rủi ro, **không phải cách thực hiện truy vấn để kiểm thử trên hệ thống không được phép**.

Không nên cố sửa bằng cách tự thêm dấu `'`, tự thay `'` thành `''` hoặc lọc vài từ khóa như `OR`, `SELECT`, `DROP`. Quoting/escaping phụ thuộc SQL dialect và cấu hình; còn blocklist dễ bị lách và làm sai dữ liệu hợp lệ.

**Cách đúng:** giữ nguyên SQL có parameter marker, bind giá trị qua JDBC API.

## 2. Tư duy chuẩn: cấu trúc cố định, giá trị truyền riêng

Thay vì nối SQL:

```java
String sql = "SELECT id, email, balance FROM accounts WHERE email = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, email);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Xử lý mỗi dòng do DB trả về.
        }
    }
}
```

Đây là **đoạn trích**, giả định `connection` là một `java.sql.Connection` đang mở, `email` đã được xác định và các lớp `java.sql.PreparedStatement`/`ResultSet` đã import. Một chương trình đầy đủ được cung cấp ở phần 9.

Luồng ý tưởng:

```text
SQL do ứng dụng quyết định:
  SELECT id, email FROM accounts WHERE email = ?
                                      |
                                      v
PreparedStatement: tham số #1 có kiểu chuỗi
  setString(1, "O'Reilly@example.test")
                                      |
                                      v
JDBC driver / database:
  phần SQL là câu lệnh; phần tham số là dữ liệu
                                      |
                                      v
Database so sánh cột email với đúng chuỗi đã bind
```

Khi người dùng nhập `' OR 1=1 --`, JDBC vẫn truyền nó dưới dạng **giá trị string của tham số số 1**. Nội dung đó không được nâng thành phép `OR` hay SQL comment của câu truy vấn; kết quả là database tìm email bằng đúng chuỗi kỳ lạ ấy, thường không có dòng nào.

Ở mức triển khai, tùy JDBC driver, DBMS và cấu hình, driver có thể gửi SQL và tham số qua giao thức riêng, biên dịch phía server, cache statement hoặc dùng cách khác. **Không cần khẳng định mọi driver gửi hai gói mạng riêng biệt** để hiểu tính an toàn: hợp đồng quan trọng là parameter value vẫn được đối xử như **dữ liệu**, không phải cú pháp SQL mới.

### 2.1. Dấu hỏi không phải một phép thay chuỗi thủ công

Trong câu:

```sql
SELECT *
FROM accounts
WHERE id = ? AND email = ?;
```

có **hai parameter markers**. Chúng không phải chuỗi cần tìm và thay bằng `String.replace("?", ...)`. Người gọi dùng các setter của `PreparedStatement`; JDBC driver/DBMS chịu trách nhiệm biểu diễn giá trị theo kiểu SQL tương ứng.

`setLong(1, id)` gắn vào marker thứ nhất, `setString(2, email)` gắn vào marker thứ hai. Chỉ số bắt đầu từ **1**, không phải 0 như index mảng Java.

### 2.2. Đầu vào hợp lệ vẫn phải được bind

Kiểm tra định dạng email, độ dài title hay quyền của người dùng là việc cần thiết, nhưng không biến việc nối chuỗi thành an toàn. Ngay cả email đã được validate, **vẫn bind**:

```java
PreparedStatement ps = connection.prepareStatement(
        "SELECT id FROM accounts WHERE email = ?");
ps.setString(1, validatedEmail);
```

Đoạn trên chỉ minh họa cơ chế; trong code thực tế nên có try-with-resources và cơ chế lấy connection phù hợp.

Ngược lại, bind tham số **không tự cung cấp authorization**. Nếu người dùng chỉ được thấy dữ liệu tenant 7, SQL vẫn cần filter tenant tương ứng và backend phải xác minh quyền truy cập tenant:

```sql
SELECT id, email
FROM accounts
WHERE tenant_id = ? AND email = ?;
```

Hai giá trị đều được bind, nhưng **quy tắc người dùng được dùng tenant nào** vẫn thuộc thiết kế bảo mật ứng dụng.

## 3. API JDBC PreparedStatement quan trọng nhất

`PreparedStatement` thuộc package `java.sql`, được tạo từ `Connection`:

```java
PreparedStatement ps = connection.prepareStatement(
        "SELECT id FROM accounts WHERE email = ?");
```

`PreparedStatement` kế thừa `Statement` và có nhiều phương thức. Trong data access thông thường, cần nhớ những nhóm sau:

| Phương thức | Mục đích |
| --- | --- |
| `connection.prepareStatement(sql)` | Chuẩn bị đối tượng JDBC ứng với SQL chứa marker `?` |
| `ps.setString(index, value)` | Bind giá trị chuỗi |
| `ps.setInt(index, value)`, `setLong(...)` | Bind số nguyên phù hợp |
| `ps.setBoolean(index, value)` | Bind boolean |
| `ps.setBigDecimal(index, value)` | Bind số thập phân chính xác, ví dụ tiền với chính sách scale rõ ràng |
| `ps.setObject(index, value)` | Bind giá trị kiểu đối tượng; phải xét khả năng suy luận kiểu SQL của driver |
| `ps.setNull(index, java.sql.Types.VARCHAR)` | Bind SQL NULL với kiểu SQL tường minh |
| `ps.executeQuery()` | Chạy truy vấn trả `ResultSet` (thường là `SELECT`) |
| `ps.executeUpdate()` | Chạy DML hoặc lệnh phù hợp và trả số dòng chịu tác động |
| `ps.execute()` | Cơ chế tổng quát, trả boolean cho biết dạng kết quả đầu tiên |
| `ps.addBatch()`, `ps.executeBatch()` | Gom các lần thực thi phù hợp để xử lý theo batch |
| `ps.clearParameters()` | Xóa các giá trị bind hiện có trên statement |
| `ps.close()` | Giải phóng tài nguyên statement; nên dùng try-with-resources |

Khi `executeQuery()` trả `ResultSet`, JDBC đặt con trỏ trước dòng đầu. Bạn gọi `rs.next()` để chuyển tới mỗi dòng; các getter như `getLong("id")` đọc cột ở dòng hiện tại.

`executeUpdate()` trả **số dòng bị ảnh hưởng** theo hợp đồng JDBC/driver, không phải ID tự sinh. Khi cần generated key, sử dụng overload tạo statement yêu cầu generated keys và `getGeneratedKeys()`, hoặc tiện ích Spring hỗ trợ.

`execute()` của **JDBC `PreparedStatement`** không giống `void JdbcTemplate.execute(String sql)` của Spring: chúng là các phương thức ở lớp trừu tượng khác nhau. Với CRUD thông thường, ưu tiên rõ ràng `executeQuery` hoặc `executeUpdate`.

### 3.1. Thứ tự bind và kiểu dữ liệu phải khớp

SQL:

```sql
UPDATE accounts
SET balance = ?
WHERE id = ?;
```

Java:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE accounts SET balance = ? WHERE id = ?")) {
    ps.setInt(1, newBalance);
    ps.setLong(2, accountId);
    int affected = ps.executeUpdate();
}
```

Đây là đoạn trích, giả định `connection`, `newBalance` và `accountId` tồn tại. Đảo nhầm thứ tự hai setter có thể dẫn đến lỗi kiểu dữ liệu hoặc, nguy hiểm hơn, một câu SQL hợp lệ nhưng cập nhật sai dòng.

Mẹo: khi có nhiều marker, đặt chúng trên các dòng SQL dễ nhìn và kiểm tra tuần tự từ trái sang phải; tránh các câu có nhiều tham số cùng kiểu mà không có tên rõ ràng.

### 3.2. Chạy lại cùng PreparedStatement với giá trị mới

Một `PreparedStatement` có thể được thực thi nhiều lần với các tham số khác nhau. Giá trị đã bind **được giữ lại** cho đến khi bạn thay bằng setter hoặc gọi `clearParameters()`; không mặc định tự xóa sau `executeQuery()`.

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT id FROM accounts WHERE email = ?")) {
    ps.setString(1, "alice@example.test");
    try (ResultSet rs = ps.executeQuery()) {
        // Xử lý kết quả alice.
    }

    ps.setString(1, "bob@example.test");
    try (ResultSet rs = ps.executeQuery()) {
        // Xử lý kết quả bob.
    }
}
```

Đây chỉ là đoạn minh họa; các ResultSet được đóng trước lần thực thi kế tiếp. Với câu SQL có ba marker, phải gán đúng cả ba cho mỗi lần dùng (hoặc hiểu chính xác những tham số nào cố ý giữ lại). Dữ liệu request cũ vô tình còn trên statement là lỗi rất khó phát hiện.

Không nên đưa cùng một `PreparedStatement` vào singleton bean rồi cho nhiều request/thread sử dụng chung. JDBC connection và statement có vòng đời/tính đồng thời riêng, thường **không nên chia sẻ** theo cách đó. Trong Spring, chia sẻ bean `JdbcTemplate` được cấu hình đúng là mô hình khác: nó điều phối các JDBC operations thông qua datasource, không có nghĩa các request chia sẻ một prepared statement tùy ý.

## 4. Tách SQL và giá trị ngăn SQL injection bằng cách nào?

### 4.1. So sánh hai cách xây truy vấn

**Không an toàn:**

```java
String sql = "SELECT id FROM accounts WHERE email = '" + userInput + "'";
// User input trở thành một phần cú pháp SQL cuối cùng.
```

**An toàn cho vị trí giá trị:**

```java
String sql = "SELECT id FROM accounts WHERE email = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, userInput);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Xử lý những row có email đúng bằng userInput.
        }
    }
}
```

Dữ liệu `userInput` có thể chứa dấu nháy đơn, comment marker hay chuỗi trông giống SQL; tại chỗ bind, chúng là dữ liệu. Đây là **nguyên tắc cốt lõi** của prepared statement chống SQL injection.

Tuy nhiên, không được khẳng định “dùng `PreparedStatement` thì mọi kiểu injection đều biến mất”. Nếu một phần cấu trúc SQL vẫn được nối từ input bên ngoài, đoạn đó vẫn có rủi ro.

### 4.2. Identifier và keyword không phải bind parameter

Không thể dùng dấu hỏi thay cho tên bảng, cột, danh sách từ khóa hay hướng sắp xếp:

```sql
-- Không có nghĩa là sắp xếp theo cột mà client chỉ định:
SELECT id, title FROM tasks ORDER BY ?;

-- Không dùng placeholder làm identifier:
SELECT * FROM ? WHERE id = ?;

-- Không biến giá trị "DESC" thành từ khóa SQL:
SELECT id FROM tasks ORDER BY created_at ?;
```

`?` đại diện **một giá trị** trong một biểu thức SQL, không đại diện thành phần cú pháp như tên bảng, `ASC` hay `DESC`.

Nếu client chọn kiểu sắp xếp, ánh xạ đầu vào sang một số **cấu trúc SQL cố định do ứng dụng sở hữu**:

```java
static String safeOrderBy(String requested) {
    return switch (requested) {
        case "newest" -> "created_at DESC, id DESC";
        case "oldest" -> "created_at ASC, id ASC";
        case "title"  -> "title ASC, id ASC";
        default -> throw new IllegalArgumentException("Unsupported sort");
    };
}
```

Khi gọi, chỉ nối **giá trị trả về từ allowlist** vào câu SQL cố định; vẫn bind các giá trị khác bằng `?`. Không đưa trực tiếp `request.getSort()` vào SQL. Với tên bảng động theo tenant, cần thiết kế schema/routing được kiểm soát, không thay identifier tùy ý bằng tham số.

### 4.3. Dynamic WHERE và các cấu trúc điều kiện

Nếu filter được bật/tắt theo request, bạn có thể xây cấu trúc SQL từng nhánh **do ứng dụng tự định nghĩa**, sau đó bind các giá trị tương ứng:

```java
String sql = "SELECT id, title FROM tasks WHERE tenant_id = ?";
if (status != null) {
    sql += " AND status = ?";
}
// Nếu thêm marker cho status, phải thêm giá trị bind tương ứng.
// Không nối trực tiếp status vào câu SQL.
```

Đây là đoạn minh họa, chưa có phần gọi JDBC, với mục đích phân biệt **cấu trúc** do code lựa chọn và **giá trị** từ request. Khi filter phức tạp, dùng builder có kiểm soát hoặc `NamedParameterJdbcTemplate` để giảm nguy cơ lệch thứ tự tham số.

### 4.4. IN (...) và danh sách giá trị

Câu như:

```sql
SELECT id, title FROM tasks WHERE id IN (?);
```

với một dấu `?` **không có nghĩa** là driver tự bung một `List<Long>` thành 4 markers. Đó vẫn là **một tham số**; truyền collection vào một marker có thể lỗi hoặc mang ý nghĩa DB-specific (ví dụ SQL array) khác kỳ vọng.

Với JDBC positional parameters, tạo chính xác số markers cho danh sách đã được validate, rồi bind từng ID:

```sql
SELECT id, title FROM tasks WHERE id IN (?, ?, ?);
```

Với Spring, `NamedParameterJdbcTemplate` thường đơn giản hơn vì có khả năng mở rộng collection parameter cho biểu thức `IN (:ids)` theo các giới hạn của JDBC/DBMS. Nhưng **danh sách rỗng** phải được xử lý có chủ đích: trả kết quả rỗng hoặc chọn một SQL phù hợp, không giả định `IN ()` được mọi DBMS chấp nhận. Cần giới hạn kích thước danh sách để tránh SQL quá dài hoặc quá nhiều bind parameters.

### 4.5. LIKE: bind an toàn nhưng vẫn có wildcard

Ví dụ:

```sql
SELECT id FROM tasks WHERE title LIKE ?;
```

Nếu bạn bind `"%_"`, nó vẫn là **giá trị SQL LIKE pattern**; database có thể hiểu `%` là nhiều ký tự và `_` là một ký tự, không phải hai ký tự literal cần tìm. PreparedStatement ngăn nội dung đó phá cấu trúc SQL, nhưng **không tự escape wildcard của LIKE**.

Khi nghiệp vụ tìm chính xác substring do người dùng gõ, phải định nghĩa cách escape các ký tự `%`, `_` và ký tự escape theo SQL dialect, rồi dùng `ESCAPE` phù hợp hoặc lựa chọn full-text/search khác. Không nhầm “không bị SQL injection” với “kết quả tìm kiếm đúng từng ký tự”.

## 5. Chú ý NULL và kiểu SQL của tham số

### 5.1. Bind NULL có kiểu rõ ràng

Trong JDBC thuần, khi tham số là SQL NULL:

```java
ps.setNull(1, java.sql.Types.VARCHAR);
```

hoặc có thể dùng `setObject(...)` với thông tin SQL type phù hợp. Kiểu `NULL` có thể quan trọng khi driver/database không suy luận được kiểu từ biểu thức hoặc overload. Trong Spring JDBC, `SqlParameterValue`, `PreparedStatementSetter` và một số overload nhận SQL types giúp chỉ định rõ kiểu khi cần.

Không phải lúc nào `ps.setObject(1, null)` cũng hoạt động giống nhau trên mọi JDBC driver/SQL dialect. Với code được triển khai trên nhiều DB, đừng phụ thuộc việc đoán type nếu query có nhiều khả năng mơ hồ.

### 5.2. NULL trong SQL tuân theo logic ba giá trị

Bind `null` cho `WHERE nickname = ?` **không khiến** SQL chuyển thành `IS NULL`. Trong SQL thông thường, `col = NULL`/`col = ?` với tham số NULL cho kết quả UNKNOWN, nên không tìm ra các dòng có nickname NULL trong `WHERE`.

Nếu yêu cầu lọc trường IS NULL, hãy viết cấu trúc SQL tương ứng:

```sql
SELECT id FROM accounts WHERE nickname IS NULL;
```

Hoặc dùng biểu thức null-safe được DBMS hỗ trợ khi thiết kế cho cả NULL và non-NULL (ví dụ `IS NOT DISTINCT FROM` ở PostgreSQL). Chọn cấu trúc theo ý nghĩa nghiệp vụ, không mong JDBC tự viết lại logic SQL.

### 5.3. Ngày giờ, UUID, tiền và số thập phân

- Với tiền, ưu tiên `BigDecimal` và SQL `DECIMAL/NUMERIC` có precision/scale xác định hơn là cộng trừ bằng `double` khi cần độ chính xác thập phân.
- Với ngày giờ, quyết định rõ múi giờ và kiểu Java/JDBC phù hợp: `LocalDate`, `LocalDateTime`, `Instant`, `OffsetDateTime`, `java.sql.Timestamp`... phải được ánh xạ theo hỗ trợ của JDBC driver/DB.
- UUID có thể được lưu dưới kiểu riêng của DB hoặc chuỗi/binary; bind bằng kiểu mà driver hỗ trợ.
- Với `setObject` và kiểu Java không phổ thông, test với DBMS thật. Đừng tự khẳng định mọi driver hỗ trợ mọi kiểu JDBC 4.2 như nhau.
- Với `ResultSet.getInt(...)` trên cột nullable, kết quả 0 có thể đại diện SQL NULL; dùng `wasNull()` hoặc `getObject(..., Integer.class)` phù hợp nếu cần phân biệt.

Ví dụ bài tập chỉ dùng `VARCHAR`, `BIGINT` và `INT` để làm rõ binding; không cần ép người mới học giải quyết timezone hay decimal conversion ngay.

## 6. PreparedStatement và transaction, tài nguyên, hiệu năng

### 6.1. Luôn đóng JDBC resources đúng thứ tự

Trong JDBC thuần, pattern an toàn:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, email);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Xử lý row.
        }
    }
}
```

Các tài nguyên được đóng theo thứ tự ngược lúc khai báo trong try-with-resources; ResultSet được đóng trước statement/connection. Không giữ `ResultSet` để dùng sau khi đóng statement/connection.

Trong Spring `JdbcTemplate`, framework thực hiện phần lớn việc lấy và giải phóng tài nguyên, nên repository thường chỉ cung cấp SQL, tham số và `RowMapper`. **Đừng tự đóng connection do Spring đang quản lý transaction** khi viết callback JDBC tùy chỉnh; phải tuân thủ contract callback/Spring.

### 6.2. PreparedStatement không tự quyết định transaction

`PreparedStatement` **không phải một transaction**. Nếu muốn nhiều câu SQL cùng commit hoặc rollback, cần ranh giới transaction phù hợp:

- JDBC thuần: `connection.setAutoCommit(false)`, thực hiện các statement trên **cùng connection**, `commit()` khi thành công, `rollback()` khi thất bại và khôi phục cấu hình/đóng tài nguyên đúng cách.
- Spring: dùng `@Transactional` trên Spring-managed service với đúng transaction manager; các thao tác `JdbcTemplate` sử dụng datasource phù hợp tham gia connection do transaction quản lý.
- Nếu hai database khác nhau, một local JDBC transaction không bao trùm cả hai; đây là vấn đề distributed transaction/consistency khác.

Đừng nhầm dùng prepared statement với việc câu query sẽ không bị block, deadlock hoặc có thể bỏ qua constraint. Các quy tắc khóa/transaction/validation vẫn do database áp dụng.

### 6.3. Có phải PreparedStatement luôn nhanh hơn Statement?

**Không có cam kết luôn nhanh hơn.** Tùy driver, DBMS, số lần tái sử dụng, server-side prepare, statement cache, kế hoạch thực thi và khối lượng dữ liệu, statement có thể được parse/plan một hoặc nhiều lần. Một số driver có threshold để bắt đầu server-side preparation hoặc có thể mô phỏng một phần ở client.

Lợi ích **được đảm bảo ở mức API** là cách bind dữ liệu và tách cú pháp SQL khỏi giá trị ở các vị trí parameter; hiệu năng phụ thuộc môi trường cụ thể. Nếu cần tối ưu, hãy đo benchmark/query plan trong DBMS đang dùng; không coi `PreparedStatement` là cách tự động loại bỏ full scan hoặc giúp mọi query có index.

### 6.4. Batch nhiều giá trị cho cùng cấu trúc SQL

Nếu chèn nhiều dòng có cùng template:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO audit_events (id, message) VALUES (?, ?)")) {
    for (AuditEvent event : events) {
        ps.setLong(1, event.id());
        ps.setString(2, event.message());
        ps.addBatch();
    }
    int[] affectedCounts = ps.executeBatch();
}
```

Đây là đoạn minh họa giả định `connection`, `AuditEvent`, `events` và schema tồn tại. Batch giúp giảm số lần đi-về tùy driver/config, nhưng không bảo đảm tất cả câu lệnh thành một giao dịch. Nếu cần tất cả cùng thành công hoặc rollback, phải cấu hình transaction. Mảng kết quả batch có thể chứa các giá trị đặc biệt như `Statement.SUCCESS_NO_INFO`; không phải tất cả phần tử đều là số dòng cụ thể.

Spring JDBC có `JdbcTemplate.batchUpdate(...)` và overload nhận `BatchPreparedStatementSetter` để giảm code boilerplate, vẫn giữ nguyên nguyên tắc gán giá trị qua setter.

## 7. Spring JdbcTemplate dùng PreparedStatement thế nào?

Trong ứng dụng Spring Framework data access, repository thường dùng `JdbcTemplate` thay vì trực tiếp lấy `Connection`. Khi gọi overload có tham số bind, `JdbcTemplate` tạo prepared statement/setter thích hợp và giải phóng tài nguyên theo quy trình của Spring JDBC.

Ví dụ:

```java
List<Account> accounts = jdbc.query(
        """
        SELECT id, email, balance
        FROM accounts
        WHERE balance >= ? AND email <> ?
        ORDER BY id
        """,
        (rs, rowNum) -> new Account(
                rs.getLong("id"),
                rs.getString("email"),
                rs.getInt("balance")),
        minimumBalance, excludedEmail);
```

Đây chỉ là đoạn trích, với `jdbc`, `Account`, `minimumBalance` và `excludedEmail` đã định nghĩa ở nơi khác. `JdbcTemplate.query(String, RowMapper<T>, Object... args)` ánh xạ các giá trị theo thứ tự markers. Bạn không cần viết `ps.setInt(1, ...)`/`ps.setString(2, ...)` khi các giá trị được bind tự động đủ rõ kiểu.

Những thao tác tương ứng:

```java
Long count = jdbc.queryForObject(
        "SELECT COUNT(*) FROM accounts WHERE balance >= ?",
        Long.class,
        minimumBalance);

int affected = jdbc.update(
        "UPDATE accounts SET balance = balance + ? WHERE id = ?",
        delta, accountId);
```

`queryForObject` dùng khi query dự kiến đúng một dòng; `COUNT(*)` không có `GROUP BY` trả một dòng chứa 0 khi không có bản ghi. `update` trả số dòng ảnh hưởng, thường là 0 khi WHERE không khớp. **Không ghép giá trị thành SQL trước khi gọi `JdbcTemplate`**, vì như vậy bạn đã phá cách tách SQL/giá trị ngay ở tầng Java.

### 7.1. JDBC API và JdbcTemplate: phần nào giống nhau?

| JDBC thuần | Với JdbcTemplate | Trách nhiệm giữ lại của ứng dụng |
| --- | --- | --- |
| `connection.prepareStatement(sql)` | `jdbc.query(sql, mapper, args...)` | Viết SQL đúng và chọn dữ liệu cần trả |
| `ps.setString(...)` / `setLong(...)` | Tham số `Object... args` hoặc `PreparedStatementSetter` | Bind đúng thứ tự/kiểu |
| `ps.executeQuery()`, `rs.next()` | `query(...)` gọi `RowMapper` cho từng dòng | Ánh xạ từng row đúng |
| `ps.executeUpdate()` | `jdbc.update(sql, args...)` | Kiểm tra affected rows theo nghiệp vụ |
| try-with-resources đóng statement/result set | Spring quản lý tài nguyên qua template | Không giữ result set/connection vượt vòng đời |
| `SQLException` | Phân cấp unchecked `DataAccessException` | Phân loại và xử lý lỗi có ý nghĩa |

**Cần phân biệt:** không phải *mọi overload* của `JdbcTemplate` đều bắt buộc dùng `PreparedStatement`. Một số overload nhận SQL không có bind có thể dùng JDBC `Statement`. Khi người dùng cung cấp giá trị, hãy chọn overload nhận bind arguments hoặc setter để đảm bảo đúng cơ chế tham số.

### 7.2. PreparedStatementSetter khi cần kiểm soát chi tiết

Khi muốn tự set giá trị có SQL type cụ thể hoặc cấu hình statement, Spring cung cấp `PreparedStatementSetter`:

```java
int updated = jdbc.update(
        "UPDATE accounts SET nickname = ? WHERE id = ?",
        ps -> {
            ps.setNull(1, java.sql.Types.VARCHAR);
            ps.setLong(2, accountId);
        });
```

Đây là đoạn trích, giả định `jdbc` và `accountId` tồn tại. Overload nhận `PreparedStatementSetter` được chọn vì lambda có một tham số là `PreparedStatement`. `setNull` mang SQL type rõ, tránh mơ hồ khi cập nhật cột nullable.

Trong phương thức callback, **không gọi `ps.executeUpdate()`** nếu contract yêu cầu chỉ bind tham số: chính `JdbcTemplate` sẽ thực thi statement và thu kết quả; gọi execute hai lần có thể gây ghi dữ liệu trùng.

Với các giá trị NULL hoặc kiểu đặc biệt, một phương án khác là `SqlParameterValue`:

```java
int affected = jdbc.update(
        "UPDATE accounts SET nickname = ? WHERE id = ?",
        new SqlParameterValue(java.sql.Types.VARCHAR, null),
        accountId);
```

Đoạn trích cần import `org.springframework.jdbc.core.SqlParameterValue`. Nó chỉ rõ SQL type của giá trị NULL, phù hợp khi muốn dùng overload `Object... args` mà không viết setter callback.

### 7.3. NamedParameterJdbcTemplate: đặt tên thay vì nhớ vị trí

Với câu SQL có nhiều tham số, Spring hỗ trợ `NamedParameterJdbcTemplate`:

```java
var named = new NamedParameterJdbcTemplate(dataSource);

var params = new MapSqlParameterSource()
        .addValue("minBalance", 200)
        .addValue("email", "bob@example.test");

List<Long> ids = named.query(
        """
        SELECT id FROM accounts
        WHERE balance >= :minBalance AND email <> :email
        ORDER BY id
        """,
        params,
        (rs, rowNum) -> rs.getLong("id"));
```

Đây là đoạn trích, không phải chương trình độc lập; cần import `NamedParameterJdbcTemplate`, `MapSqlParameterSource` và có `dataSource`. `:minBalance`/`:email` **không phải cú pháp tham số chuẩn của SQL engine**; Spring chuyển tên thành JDBC placeholders và bind giá trị tương ứng trước khi thực thi. Một câu SQL có cùng tên xuất hiện nhiều lần giúp tránh lặp nhớ thứ tự tham số.

`NamedParameterJdbcTemplate` có thể mở rộng tham số collection cho `IN (:ids)`, nhưng vẫn phải xử lý list rỗng và giới hạn số phần tử phù hợp. Dùng named parameters giúp dễ đọc, **không làm việc nối identifier từ user input trở nên an toàn**.

### 7.4. Repository nên dùng binding tại nơi sở hữu SQL

Trong thiết kế tốt, repository sở hữu cả SQL cấu trúc và cách bind tham số; service truyền các giá trị đã kiểm tra và thực thi quyền truy cập. Controller không nên lắp SQL bằng chuỗi từ request. Ví dụ method dưới đây chỉ là một đoạn mã trong repository đã có bean `JdbcTemplate`:

```java
public Optional<Account> findByEmail(String email) {
    List<Account> found = jdbc.query(
            """
            SELECT id, email, balance
            FROM accounts
            WHERE email = ?
            """,
            ACCOUNT_MAPPER,
            email);
    return found.stream().findFirst();
}
```

Mẫu này giả định cột `email` có ràng buộc UNIQUE (hoặc query được đảm bảo trả tối đa một dòng); nếu không, `findFirst()` có thể che lỗi dữ liệu trùng. Với “phải có đúng một dòng”, `queryForObject` và xử lý `EmptyResultDataAccessException` có ý nghĩa khác. Bind tham số giải quyết **an toàn cú pháp SQL**, không giải quyết tự động **cardinality**.

## 8. Các lỗi thường gặp với PreparedStatement

| Hiểu nhầm | Cách hiểu/giải quyết |
| --- | --- |
| “`?` thay được mọi thứ trong SQL.” | Chỉ thay **giá trị** ở vị trí tham số; identifier, keyword, hướng sort phải từ cấu trúc kiểm soát. |
| “Chỉ số tham số bắt đầu từ 0.” | JDBC `setXxx(index,...)` bắt đầu từ **1**. |
| “`setString(1, "123")` và `setLong(1, 123)` luôn tương đương.” | Kiểu dữ liệu và kế hoạch chuyển đổi của DB/driver có thể khác; bind đúng SQL type. |
| “PreparedStatement tự escape cả LIKE wildcard.” | Dữ liệu vẫn là LIKE pattern; `%`, `_` vẫn mang nghĩa wildcard. |
| “`IN (?)` nhận một Java List và tự bung.” | Không theo JDBC positional markers thông thường; mở rộng markers hoặc dùng named parameters hỗ trợ collection. |
| “Bind NULL tương đương điều kiện IS NULL.” | `WHERE col = NULL` không khớp NULL theo SQL three-valued logic; cần cấu trúc `IS NULL` phù hợp. |
| “Chỉ cần validate input, rồi nối SQL là an toàn.” | Validation và parameter binding giải quyết mục tiêu khác nhau; vẫn bind dữ liệu. |
| “PreparedStatement luôn nhanh hơn Statement.” | Tùy driver, caching, DB và query plan; lợi ích đúng nghĩa là tách cấu trúc/giá trị. |
| “Dùng JdbcTemplate là mọi SQL injection đều bị chặn.” | Nối user input thành SQL trước khi gọi template vẫn nguy hiểm; phải dùng overload tham số và allowlist cho cấu trúc động. |
| “Chạy lại PreparedStatement tự xóa tham số cũ.” | Bind values thường được giữ cho đến khi thay/clear; cập nhật đầy đủ tham số cho lần chạy mới. |
| “PreparedStatement tự commit/rollback nhiều câu SQL.” | Transaction cần cấu hình riêng trên connection hoặc Spring service. |
| “Một PreparedStatement dùng chung cho mọi request là tốt.” | Không chia sẻ statement/connection tùy tiện giữa threads; để connection pool và JdbcTemplate quản lý vòng đời phù hợp. |

## 9. Thực hành đầy đủ: Java 17 + Spring JDBC + H2

Ví dụ này cho thấy **cùng cơ sở dữ liệu** được truy vấn qua JDBC `PreparedStatement` thuần và `JdbcTemplate`; giá trị chứa dấu nháy đơn và chuỗi có hình dạng SQL được đối xử như dữ liệu. Sử dụng H2 in-memory để chạy độc lập, không cần một database server bên ngoài.

**Yêu cầu:** JDK 17+, Gradle tương thích Java 17 (hoặc Gradle Wrapper tương ứng), quyền tải dependencies từ Maven Central khi lần đầu chạy.

### 9.1. Cấu trúc thư mục

```text
prepared-statement-demo/
├── build.gradle
└── src/main/java/example/PreparedStatementDemo.java
```

### 9.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.PreparedStatementDemo'
}
```

Không cần tạo Spring `ApplicationContext` vì ví dụ trực tiếp xây `JdbcTemplate` từ datasource để minh họa SQL/binding. Trong ứng dụng thực, datasource thường do Spring container quản lý và repository nhận `JdbcTemplate` qua DI.

### 9.3. File Java hoàn chỉnh

Tạo `src/main/java/example/PreparedStatementDemo.java`:

```java
package example;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class PreparedStatementDemo {
    public static void main(String[] args) throws Exception {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:prepared_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(ds);

        // DDL demo: bảng có một email có dấu nháy đơn.
        jdbc.execute("""
                CREATE TABLE accounts (
                    id BIGINT PRIMARY KEY,
                    email VARCHAR(120) NOT NULL UNIQUE,
                    balance INT NOT NULL
                )
                """);

        // Spring JdbcTemplate bind bốn giá trị bằng placeholders.
        jdbc.update(
                "INSERT INTO accounts (id, email, balance) VALUES (?, ?, ?)",
                1L, "alice@example.test", 100);
        jdbc.update(
                "INSERT INTO accounts (id, email, balance) VALUES (?, ?, ?)",
                2L, "bob@example.test", 200);
        jdbc.update(
                "INSERT INTO accounts (id, email, balance) VALUES (?, ?, ?)",
                3L, "O'Reilly@example.test", 300);

        String sql = """
                SELECT id, balance
                FROM accounts
                WHERE email = ?
                """;

        // JDBC thuần: chính chúng ta quản lý PreparedStatement.
        try (Connection connection = ds.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            // Giá trị có dấu ' được so sánh chính xác.
            ps.setString(1, "O'Reilly@example.test");
            try (ResultSet rs = ps.executeQuery()) {
                if (rs.next()) {
                    System.out.println(
                            "found=" + rs.getLong("id")
                            + ":" + rs.getInt("balance"));
                }
            }

            // Không thay SQL, chỉ đổi giá trị của marker số 1.
            ps.setString(1, "' OR 1=1 --");
            try (ResultSet rs = ps.executeQuery()) {
                System.out.println("strangeInputFound=" + rs.next());
            }

            // Statement vẫn có thể được sử dụng lại với giá trị mới.
            ps.setString(1, "bob@example.test");
            try (ResultSet rs = ps.executeQuery()) {
                if (rs.next()) {
                    System.out.println(
                            "reusedId=" + rs.getLong("id"));
                }
            }
        }

        // Spring queryForObject: một dòng/giá trị scalar.
        Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM accounts WHERE balance >= ?",
                Long.class,
                200);
        System.out.println("countAtLeast200=" + count);

        // Spring query: danh sách và RowMapper.
        List<String> emails = jdbc.query(
                """
                SELECT email
                FROM accounts
                WHERE balance >= ?
                ORDER BY id
                """,
                (rs, rowNum) -> rs.getString("email"),
                200);
        System.out.println("matchingEmails=" + emails);

        // Spring update: số dòng bị tác động, không phải generated ID.
        int changed = jdbc.update(
                "UPDATE accounts SET balance = balance + ? WHERE id = ?",
                25, 1L);
        System.out.println("changed=" + changed);

        Integer aliceBalance = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = ?",
                Integer.class, 1L);
        System.out.println("aliceBalance=" + aliceBalance);

        int missing = jdbc.update(
                "UPDATE accounts SET balance = balance + ? WHERE id = ?",
                25, 999L);
        System.out.println("missingChanged=" + missing);
    }
}
```

Một số chi tiết cần thấy rõ:

- Chuỗi SQL `SELECT id, balance FROM accounts WHERE email = ?` **không thay đổi** giữa ba lần tìm kiếm; chỉ `ps.setString(1, ...)` thay giá trị.
- String có dấu nháy đơn được chèn và đọc thành công vì `JdbcTemplate` cũng bind dữ liệu cho `INSERT`.
- Chuỗi `' OR 1=1 --` không được thực thi như điều kiện SQL, nên không khớp email nào trong bảng.
- `PreparedStatement`/`ResultSet` được đóng qua try-with-resources; `Connection` được đóng sau cùng.
- `JdbcTemplate` thao tác trên cùng database H2 với JDBC thuần; vì vậy hai cách truy cập thấy cùng dữ liệu.
- `JdbcTemplate.query(...)` nhận `RowMapper`, trong mapper không gọi `rs.next()`; template đã duyệt từng row.
- `DriverManagerDataSource` thích hợp cho demo nhưng **không phải connection pool tối ưu cho production**. `DB_CLOSE_DELAY=-1` giữ in-memory database sống qua nhiều lần đóng connection trong cùng JVM.

### 9.4. Chạy chương trình

Từ thư mục dự án:

```bash
gradle run
```

Nếu đã có Gradle Wrapper, dùng `./gradlew run` (Linux/macOS) hoặc `gradlew.bat run` (Windows). Gradle có thể in nhiều log build; **các dòng do Java System.out.println in ra** theo thứ tự là:

```text
found=3:300
strangeInputFound=false
reusedId=2
countAtLeast200=2
matchingEmails=[bob@example.test, O'Reilly@example.test]
changed=1
aliceBalance=125
missingChanged=0
```

Kiểm tra từng kết quả:

1. Ba `INSERT` tạo ID 1 (100), ID 2 (200), ID 3 (300).
2. Bind `O'Reilly@example.test` đúng literal string nên `found=3:300`.
3. Giá trị `' OR 1=1 --` không phải một email đã lưu; dùng prepared statement trả false, không tự biến câu SQL thành “trả mọi dòng”.
4. Đổi marker thành `bob@example.test` trên cùng statement tìm ID 2.
5. `balance >= 200` khớp Bob (200) và O'Reilly (300), nên `countAtLeast200=2` và list có hai email sắp theo ID.
6. `UPDATE ... WHERE id=1` thay Alice từ 100 thành 125, affected row = 1; ID 999 không tồn tại nên affected row = 0.

**Giới hạn của demo:** Code minh họa tách dữ liệu/cấu trúc SQL; chưa cấu hình pool, transaction/service, authorization, migration hay các ràng buộc nghiệp vụ của hệ thống thật.

## 10. Quy trình áp dụng cho Spring Repository

Một ví dụ repository có luồng tốt:

```text
Controller:
  nhận filter, sort, người dùng/tenant
    |
    v
Service:
  xác minh quyền, validate input, giao dịch nghiệp vụ
    |
    v
Repository:
  chọn SQL cấu trúc đã định nghĩa
  dùng @Qualifier nếu hệ thống có nhiều nguồn dữ liệu
  bind dữ liệu bằng ? hoặc named parameters
    |
    v
JdbcTemplate / NamedParameterJdbcTemplate
    |
    v
DataSource / JDBC Driver / Database
```

Trước khi gửi một SQL từ repository vào production, hãy tự kiểm tra:

1. Mỗi giá trị không tin cậy đã được bind bằng parameter chưa?
2. Có thành phần SQL cấu trúc nào vẫn ghép trực tiếp từ request như bảng, cột, direction, predicate? Nếu có, đã dùng allowlist hoặc query builder có kiểm soát chưa?
3. Thứ tự/kiểu giá trị có đúng với vị trí `?` và kiểu cột không?
4. Nếu input có `'`, `%`, `_`, Unicode hoặc NULL, query có đúng nghĩa không?
5. Nếu cần danh sách, `IN` có số markers hợp lý và xử lý empty list chưa?
6. SQL có giới hạn đúng tenant/quyền truy cập, tránh rò rỉ dữ liệu khác phạm vi không?
7. Các câu ghi dữ liệu có transaction boundary đúng và có kiểm tra affected rows không?
8. Với query nhiều kết quả, đã phân trang/sắp xếp khi cần chưa?
9. Có đang log giá trị cá nhân/secret nhạy cảm một cách không cần thiết không?
10. Integration test đã chạy với DBMS thực của production hoặc engine tương đương, không chỉ H2 chưa?

## 11. Câu hỏi tự kiểm tra

1. Vì sao `String sql = "SELECT ... WHERE email = '" + email + "'"` không an toàn dù email đã được kiểm tra định dạng?
2. Trong JDBC, `ps.setString(1, value)` gắn marker thứ mấy? Vì sao không dùng chỉ số 0?
3. Khi người dùng nhập `O'Reilly@example.test`, PreparedStatement giúp điều gì khác với tự nối chuỗi?
4. Giá trị `' OR 1=1 --` được bind vào `WHERE email = ?` có tác dụng gì đối với **cấu trúc SQL**?
5. Tại sao không dùng `ORDER BY ?` để chọn tên cột sort từ request? Thiết kế allowlist thế nào?
6. Nếu người dùng chọn ba ID, vì sao `IN (?)` với một Java `List<Long>` thường không tương đương `IN (?, ?, ?)`?
7. `setNull(1, Types.VARCHAR)` khác gì với `WHERE nickname IS NULL`?
8. Có thể tái sử dụng một `PreparedStatement` sau khi thực thi không? Giá trị parameter cũ còn lại hay tự mất?
9. Khi nào gọi `executeQuery`, `executeUpdate` và `execute` của JDBC?
10. Vì sao Spring `JdbcTemplate` giảm mã boilerplate nhưng **không làm** cách nối SQL từ user input trở nên an toàn?
11. Có thể khẳng định PreparedStatement luôn chạy nhanh hơn Statement không? Cần đo những yếu tố nào?
12. Việc dùng prepared statement có tự bảo đảm transaction, kiểm soát quyền truy cập hoặc khóa đồng thời không?

**Ghi nhớ:** PreparedStatement là **ranh giới giữa cú pháp SQL do code quyết định và giá trị do dữ liệu cung cấp**. Đánh dấu `?` ở vị trí giá trị rồi bind bằng JDBC/Spring; không thay các giá trị bằng nối chuỗi và không cố bind thành phần cấu trúc SQL. Bảo mật đầy đủ còn cần phân quyền, validation, transaction và kiểm thử với dữ liệu thực.

### Tài liệu tham khảo

- Oracle Java — [PreparedStatement: Creating and Supplying Parameters](https://docs.oracle.com/javase/tutorial/jdbc/basics/prepared.html).
- Java SE 17 — [java.sql.PreparedStatement API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html).
- Spring Framework 6.2 — [JDBC Core and JdbcTemplate](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html).
- Spring Framework 6.2 — [JdbcTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html).
- OWASP — [SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html).
