# JDBC trong Java: closeOnCompletion và vòng đời các ResultSet

## 1. Mục tiêu bài học

Trong JDBC, truy vấn thường tạo ra một chuỗi tài nguyên có liên hệ:

```text
Connection
    |
    +-- Statement / PreparedStatement / CallableStatement
              |
              +-- ResultSet (một hoặc nhiều kết quả phụ thuộc)
```

Một câu hỏi quyết định độ đúng và mức dùng tài nguyên của ứng dụng là: **Khi `ResultSet` được đóng, `Statement` nào phải đóng, và ai có trách nhiệm?**

Bài **“closeOnCompletion và vòng đời các ResultSet”** thuộc chủ đề **JDBC**, tập trung vào API có từ **Java 7 (JDBC 4.1)** và vẫn còn hiệu lực trong **Java 17+**. Cần hiểu:

- Mặc định, `ResultSet.close()` đóng chính result set; **không mặc nhiên đóng statement** tạo ra nó.
- `Statement.close()` đóng statement và result set phụ thuộc còn mở.
- `Statement.closeOnCompletion()` yêu cầu statement **tự đóng khi tất cả dependent ResultSet đã đóng**; phương thức này **không đóng ngay** và **không tự đóng Connection**.
- `Statement.isCloseOnCompletion()` phản ánh **cấu hình**, khác với `Statement.isClosed()` phản ánh **trạng thái đã đóng**.
- `closeOnCompletion` có hiệu lực với **các result sets đã mở** và các result sets tạo trong những execution tiếp theo; gọi nhiều lần không toggle thành off.
- Nếu một execution **không tạo ra ResultSet**, riêng `closeOnCompletion` **không có tác dụng**.
- Re-execute statement hoặc gọi `getMoreResults()` có thể **đóng ResultSet hiện tại ngầm**.
- Khi có nhiều ResultSets phụ thuộc, cần xem `KEEP_CURRENT_RESULT` và giới hạn hỗ trợ của driver.
- `try-with-resources` vẫn là lựa chọn quản lý tài nguyên dễ kiểm tra nhất; `closeOnCompletion` không thay nó ở mọi đường lỗi.

Phần ví dụ sử dụng **hai loại mã**: một bài demo Java 17+ tự chạy bằng *test double in-memory* để minh họa vòng đời, và một ví dụ JDBC thực đã **biên dịch** nhưng cần driver, database, credentials để chạy. Phân biệt rõ hai loại, không dùng mô hình tự xây để khẳng định compliance của mọi driver.

## 2. Phân biệt ba cấp đóng tài nguyên

### 2.1. `Connection`

`Connection` cung cấp môi trường thực thi SQL, transaction state và khả năng tạo `Statement`. Nó có vòng đời độc lập với từng statement. Ứng dụng có thể trực tiếp sở hữu connection hoặc nhận từ pool.

Trong pool, `Connection.close()` trên logical handle thường có nghĩa **trả về pool**, không nhất thiết đóng physical database socket. `closeOnCompletion()` chỉ thuộc statement, không thay đổi ownership này.

### 2.2. `Statement`

`Statement` dùng để thực thi SQL và nhận những kết quả liên quan. Trong Java:
- `Statement` thường dùng cho SQL cố định, không chứa tham số không đáng tin.
- `PreparedStatement` dùng bind parameters; thích hợp cho input bên ngoài để tránh SQL injection ở values.
- `CallableStatement` dùng cho stored procedures, có thể có cả result sets lẫn update counts.

`PreparedStatement` và `CallableStatement` **extends `Statement`**, vì thế kế thừa `closeOnCompletion` và `isCloseOnCompletion`. Khi gọi `stmt.close()`, các `ResultSet` do statement tạo ra sẽ bị đóng/invalidate theo contract. Thực tế vendor có thể còn quản lý server cursors/caches; không được bỏ qua `close()` chỉ vì JDBC objects sẽ có GC.

### 2.3. `ResultSet`

`ResultSet` là cursor; ban đầu thường đứng **trước dòng đầu tiên**, `next()` đưa tới row kế tiếp và trả boolean. `ResultSet.close()` giải phóng resources của result set; `isClosed()` cho biết result đã đóng tường minh hoặc tự động. Một vòng lặp `while (rs.next())` chạy đến `false` **không phải lời gọi `close`**.

Một result set có thể được đóng:
1. Tường minh bằng `rs.close()` / `try-with-resources`.
2. Ngầm khi statement tạo nó bị đóng.
3. Ngầm khi statement được thực thi lại.
4. Ngầm khi statement được dùng lấy next result trong chuỗi kết quả nhiều phần, theo mode `getMoreResults`.

Với `closeOnCompletion`, các sự kiện đóng ResultSet này còn có thể ảnh hưởng vòng đời của **statement**, nên tránh tiếp tục sử dụng statement sau khi dependent ResultSet cuối đã đóng.

## 3. Hợp đồng của `closeOnCompletion` theo Java SE 17

### 3.1. Chữ ký

```java
void closeOnCompletion() throws SQLException;
boolean isCloseOnCompletion() throws SQLException;
boolean isClosed() throws SQLException;
```

Các methods thuộc `java.sql.Statement`.

**`closeOnCompletion()`** kích hoạt việc đóng statement **khi tất cả dependent ResultSets đã đóng**. Đây là cấu hình của statement cụ thể, không phải lệnh `close()` ngay lúc gọi.

**`isCloseOnCompletion()`** trả `true` khi chế độ này đã được bật cho statement vẫn đang mở.

**`isClosed()`** trả `true` nếu statement đã đóng do explicit `close` hoặc tự động đóng; có thể dùng để xác minh sau khi ResultSet cuối đã đóng.

Theo Javadoc, `closeOnCompletion`/`isCloseOnCompletion` có thể ném `SQLException` nếu statement đã đóng. Vì vậy không gọi `isCloseOnCompletion()` sau khi statement đã auto-close để “xem đã đóng chưa”; dùng `isClosed()`.

### 3.2. Gọi hai lần không bật–tắt

```java
statement.closeOnCompletion();
statement.closeOnCompletion();
boolean enabled = statement.isCloseOnCompletion(); // true nếu còn mở
```

Tùy chọn này **không có toggle-off counterpart** trong API. Nếu muốn một statement không áp dụng auto-close, tạo statement khác hoặc chọn scope/resource policy phù hợp từ đầu.

### 3.3. Có tác dụng với ResultSet đã mở

```java
Statement stmt = connection.createStatement();
ResultSet rs = stmt.executeQuery("SELECT id FROM orders");
stmt.closeOnCompletion();
rs.close(); // Nếu là dependent result cuối, stmt sẽ tự đóng.
```

Đây là snippet trong method có `connection` và schema phù hợp. Tài liệu Java SE 17 nêu cụ thể lời gọi `closeOnCompletion` có tác dụng với **subsequent executions** và **currently open dependent result sets**. Không cần chờ đến query tiếp theo để tính năng có hiệu lực.

### 3.4. Không có ResultSet thì không có tác dụng

Javadoc còn ghi: nếu execution của statement **không tạo ra result sets**, `closeOnCompletion` **không có tác dụng**. Ví dụ chỉ làm `executeUpdate()` tạo update count thì không được dựa vào policy để đóng statement sau khi update.

### 3.5. Không có nghĩa Connection đóng theo

`Statement.closeOnCompletion()` không tự gọi `Connection.close()`. Nếu connection thuộc method, dùng scope ngoài. Nếu connection thuộc pool/transaction manager, trả lại đúng theo API của framework. Không đánh đồng “statement closed” với “database transaction committed”.

## 4. Bảng trạng thái minh họa

| Hành động | ResultSet | Statement | Connection |
| --- | --- | --- | --- |
| Tạo `stmt` | Chưa có | Mở | Mở |
| `stmt.closeOnCompletion()` | Chưa có | **Mở, đã bật policy** | Mở |
| `stmt.executeQuery(...)` | Mở | Mở | Mở |
| Đọc hết `rs.next()` | Thường vẫn cần close | Chưa chắc đóng | Mở |
| `rs.close()` khi **chưa bật policy** | Đóng | Thường vẫn mở | Mở |
| `rs.close()` khi **đã bật policy** và không còn dependent results | Đóng | **Tự đóng** | Mở |
| Còn một dependent ResultSet chưa đóng | Một số đã đóng | **Vẫn mở** | Mở |
| `stmt.close()` | Dependent results đóng | Đóng | Không tự đóng |
| `executeUpdate()` mà không có ResultSet | Không có | Không tự đóng bởi policy | Mở |
| `connection.close()` | Không thể tiếp tục dùng từ connection đó | Các statements không còn dùng được | Đóng/logically returned |

Bảng này phản ánh API contract và một flow dùng đúng ownership. Khi có stored procedures, generated keys hoặc nhiều results xen kẽ, thứ tự đóng và khả năng tiếp tục gọi các methods cần được kiểm tra trên driver thực.

### 4.1. Đọc hết rows không đồng nghĩa `rs.close()`

```java
ResultSet rs = stmt.executeQuery("SELECT id FROM orders");
while (rs.next()) {
    // Đọc rows.
}
// Lúc này phải close rs dù không còn rows.
rs.close();
```

Đừng dùng `rs.next()==false` làm bằng chứng server cursor đã giải phóng.

### 4.2. `rs.close()` trước khi đọc hết vẫn được phép

Không cần đọc mọi row trước khi `close()`. Nếu chỉ cần row đầu hoặc đã quyết định dừng sớm, đóng ngay ResultSet sẽ giải phóng resources sớm. Với statement bật `closeOnCompletion`, việc đóng sớm ResultSet cuối cũng có thể làm statement tự đóng.

## 5. Không bật `closeOnCompletion`: flow thông thường

```java
try (Statement stmt = connection.createStatement()) {
    try (ResultSet rs = stmt.executeQuery("SELECT id FROM orders")) {
        while (rs.next()) {
            long id = rs.getLong(1);
            // Dùng giá trị đã đọc.
        }
    }
    // rs đã đóng, nhưng stmt vẫn mở trong scope này.
}
// stmt đóng khi thoát try ngoài.
```

Đây là snippet cần bảng `orders` và một `connection` còn mở. Nó cho thấy:
- **Đóng `ResultSet`** chỉ đóng cursor.
- **Đóng `Statement`** nằm ở try ngoài; chưa bật policy nên statement không tự đóng khi đóng rs.
- Tách scope rõ giúp reviewer nhận biết lúc nào resources còn sống.

Nếu một statement được thiết kế để thực hiện nhiều query tuần tự, flow thường dùng **không bật `closeOnCompletion`**, và bảo đảm các ResultSets được đóng trước khi tái dùng statement. Nếu cần hai ResultSets cùng mở cho hai truy vấn độc lập, thường tạo **hai statements khác nhau**, không giữ ResultSet của query cũ rồi thực thi lại cùng statement.

## 6. Có `closeOnCompletion`: tự đóng Statement khi ResultSet cuối đóng

```java
Statement stmt = connection.createStatement();
try {
    stmt.closeOnCompletion();
    try (ResultSet rs = stmt.executeQuery("SELECT id FROM orders")) {
        while (rs.next()) {
            long id = rs.getLong(1);
        }
    }
    if (!stmt.isClosed()) {
        throw new IllegalStateException("Expected auto-close");
    }
} finally {
    stmt.close(); // No-op nếu đã auto-close.
}
```

Đây là snippet trong method có connection và SQL hợp lệ. **Giữ `finally` là có chủ ý:** nếu `executeQuery` thất bại trước khi tạo ResultSet, hoặc nếu driver không hỗ trợ feature, không có dependent ResultSet nào để kích hoạt auto-close. `Statement.close()` trên statement đã đóng là no-op theo Javadoc.

### 6.1. Khi nào dùng tùy chọn này?

Dùng khi flow có ý nghĩa “Statement được giữ mở cho đến khi toàn bộ ResultSets mà nó sinh ra được xử lý và đóng” và ownership được xác định rõ.

Tuy nhiên, nếu cả statement/result set đều do cùng method sở hữu, **nested try-with-resources thông thường đã đủ**, dễ kiểm tra hơn và ít bất ngờ hơn. `closeOnCompletion` là một cơ chế bổ sung chứ không phải yêu cầu mọi method JDBC đều phải gọi.

### 6.2. Khi nào không nên dùng?

Tránh bật khi code cần **tiếp tục dùng lại Statement sau khi đã đóng hết Results**. Statement có thể auto-close trước khi vòng xử lý tiếp theo chạy, dẫn tới `SQLException`. Hãy tạo Statement mới cho mỗi query scope hoặc chủ động quản lý statement trong toàn bộ method thay vì bật auto-close.

### 6.3. Không có tác dụng với DML thuần update count

```java
Statement stmt = connection.createStatement();
try {
    stmt.closeOnCompletion();
    int count = stmt.executeUpdate(
        "UPDATE orders SET archived = TRUE WHERE id = 10");
    // Không có ResultSet => policy không tự đóng stmt.
} finally {
    stmt.close();
}
```

Phụ thuộc schema, không có stdout cố định. Cần `finally`/try-with-resources để đóng.

## 7. Đóng ngầm khi thực thi lại hoặc lấy kết quả tiếp theo

Java SE 17 `ResultSet` Javadoc nói ResultSet bị đóng tự động khi `Statement` tạo nó **bị đóng**, **được thực thi lại**, hoặc **dùng để lấy next result trong chuỗi multiple results**.

### 7.1. Thực thi lại cùng một Statement

```java
ResultSet first = stmt.executeQuery("SELECT id FROM orders");
ResultSet second = stmt.executeQuery("SELECT id FROM users");
// first đã bị đóng ngầm do tái execute.
```

Đây là **phản ví dụ** nếu code vẫn muốn đọc `first`. Theo mặc định một Statement chỉ có một current ResultSet đang mở. Nếu cần xen kẽ hai query results, tạo hai Statements hoặc đọc/map result thứ nhất trước khi chạy result thứ hai.

Khi đã bật `closeOnCompletion`, việc đóng ngầm một result qua reexecute có thể khiến statement auto-close; không viết logic phụ thuộc vào việc tái sử dụng statement trong trường hợp ấy.

### 7.2. `getMoreResults()` không tham số

`stmt.getMoreResults()` chuyển sang result tiếp theo và mặc định **đóng current ResultSet**. Vì vậy, khi gọi nó, object result hiện tại có thể không dùng được nữa. `getMoreResults()==false` có thể có nghĩa result tiếp theo là **update count** chứ chưa phải hết mọi results.

Thông thường chuỗi results kết thúc khi:
- `getMoreResults() == false` **và**
- `getUpdateCount() == -1`.

Nếu `closeOnCompletion` tự đóng statement ngay trong quá trình đóng ResultSet cuối, code không được tiếp tục gọi getMoreResults trên statement đã closed. Với stored procedures trả nhiều loại results, thiết kế protocol theo DBMS/driver; đôi khi **không bật closeOnCompletion** và đóng statement sau khi duyệt hết sẽ đơn giản hơn.

### 7.3. `getMoreResults(int)` và ba flags

| Cách gọi | Ý nghĩa |
| --- | --- |
| `getMoreResults()` | Tiến đến result kế tiếp, đóng current result |
| `getMoreResults(Statement.CLOSE_CURRENT_RESULT)` | Đóng current result |
| `getMoreResults(Statement.KEEP_CURRENT_RESULT)` | Giữ current ResultSet mở khi tiến (nếu driver hỗ trợ) |
| `getMoreResults(Statement.CLOSE_ALL_RESULTS)` | Đóng những Results đã được giữ trước đó theo contract |

Không được coi ba modes đều hỗ trợ trên mọi driver. `DatabaseMetaData.supportsMultipleOpenResults()` giúp kiểm tra capability. Nếu không hỗ trợ mà gọi `KEEP_CURRENT_RESULT` / `CLOSE_ALL_RESULTS`, driver có thể ném `SQLFeatureNotSupportedException`.

### 7.4. “All dependent ResultSets” với nhiều kết quả

```text
Statement S: closeOnCompletion enabled
  |
  +-- ResultSet R1: OPEN
  |
  +-- ResultSet R2: OPEN (giữ qua KEEP_CURRENT_RESULT)

close(R1) => S vẫn OPEN (R2 còn mở)
close(R2) => S CLOSED
Connection vẫn OPEN
```

Đây là **mô hình chỉ áp dụng khi driver hỗ trợ multiple open results**. Không thể suy rằng hai resultsets đang mở cùng lúc nếu chưa kiểm tra driver capability.

## 8. `PreparedStatement`, `CallableStatement` và generated keys

### 8.1. PreparedStatement cũng có API này

`PreparedStatement extends Statement`, nên có thể dùng:

```java
try (PreparedStatement ps = connection.prepareStatement(
         "SELECT id, name FROM users WHERE id = ?")) {
    ps.setLong(1, requestedId);
    ps.closeOnCompletion();

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            String name = rs.getString("name");
        }
    }
}
```

Đây là snippet phụ thuộc bảng `users`, `connection` và `requestedId` đã định nghĩa. Dùng **bind parameters** cho input không tin cậy; close-on-completion **không phòng SQL injection**.

### 8.2. CallableStatement có thể có nhiều results

Stored procedure có thể trả ResultSets, update counts và out parameters với trình tự phụ thuộc DBMS. `closeOnCompletion` vẫn được kế thừa, nhưng cần cẩn trọng: sau khi dependent ResultSet cuối đóng, statement có thể đã đóng, không nên cố đọc thêm những thông tin từ statement. Tạo workflow lấy parameters/results có thứ tự và cleanup rõ theo driver specification.

### 8.3. `getGeneratedKeys()` trả ResultSet

Nếu dùng `Statement.RETURN_GENERATED_KEYS`, JDBC `getGeneratedKeys()` trả một ResultSet. Hãy đóng nó tường minh:

```java
try (PreparedStatement ps = connection.prepareStatement(
         "INSERT INTO users(name) VALUES (?)",
         Statement.RETURN_GENERATED_KEYS)) {
    ps.setString(1, "Alice");
    ps.executeUpdate();

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (keys.next()) {
            long id = keys.getLong(1);
        }
    }
}
```

SQL dialect, cách cấu hình khóa tự sinh và loại key khác nhau theo vendor; cần integration test trên DB thật. Nếu bật `closeOnCompletion`, những ResultSets phụ thuộc phát sinh từ generated keys có thể ảnh hưởng điều kiện auto-close. Không dựa vào thứ tự driver nội bộ chưa được verify; nested try-with-resources vẫn giúp cleanup đúng.

## 9. Transaction và connection pooling là chuyện khác

### 9.1. Đóng Statement không commit

Nếu `connection.setAutoCommit(false)`, transaction cần `commit()` hoặc `rollback()` theo policy. Không lấy trạng thái `stmt.isClosed()==true` làm bằng chứng thay đổi database đã được commit.

```java
connection.setAutoCommit(false);
try {
    // SQL trong transaction.
    connection.commit();
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
}
```

Đây là snippet minh họa transaction, chưa bao gồm policy cleanup connection/rollback failure của production. `closeOnCompletion` không thay phần xử lý giao dịch.

### 9.2. Holdability qua commit

JDBC có hai modes liên quan:
- `ResultSet.HOLD_CURSORS_OVER_COMMIT`;
- `ResultSet.CLOSE_CURSORS_AT_COMMIT`.

`Statement.getResultSetHoldability()` cho biết cursor có bị đóng khi commit hay không theo configuration/capability. Nếu cursor bị đóng ở commit, việc đó có thể làm điều kiện auto-close statement xảy ra nếu đã bật `closeOnCompletion`.

Holdability **không phải một cách thay thế** để tự động cleanup các ResultSets tùy ý; hành vi thực tế còn phụ thuộc driver, DBMS và transaction boundary.

### 9.3. Connection pool

Connection có thể là logical wrapper của pool. Lúc `Statement` tự đóng, **logical Connection vẫn mở** trong scope. Nếu request xong, trả connection về pool bằng `connection.close()` đúng ownership. Không để connection lưu trong shared static field chỉ vì đã đóng Statements.

### 9.4. Streaming và fetch size

Với result set lớn, driver có thể stream/cursor-fetch. `Statement.setFetchSize` là **hint**, không hứa giữ tối đa N row trong RAM ở mọi DB. Đóng result set trước khi đọc đủ dữ liệu sẽ cắt phạm vi đọc; đóng sau khi xong giúp giải phóng cursor/network resources sớm.

### 9.5. Blob/Clob có tài nguyên riêng

Javadoc `ResultSet.close()` lưu ý nó **không tự đóng các `Blob`, `Clob` hoặc `NClob`** được tạo từ ResultSet. Những object đó có vòng đời và `free()` riêng; nếu đọc LOB, cần cleanup theo API và driver. Đừng suy “ResultSet auto-closed => mọi loại tài nguyên liên quan đã biến mất”.

## 10. `try-with-resources` vẫn là ưu tiên

### 10.1. Pattern mặc định

```java
try (Connection conn = DriverManager.getConnection(url, user, password);
     PreparedStatement ps = conn.prepareStatement(
             "SELECT id FROM users WHERE active = ?")) {
    ps.setBoolean(1, true);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong(1);
        }
    }
}
```

Đây là snippet cần database URL, driver, schema phù hợp. Resources được đóng ở đúng scope, kể cả khi `next()` hoặc code xử lý row ném exception. Không cần dùng `closeOnCompletion` nếu statement đã nằm gọn trong try-with-resources.

### 10.2. Dùng cả hai có sao không?

Không nhất thiết là lỗi:

```java
try (Statement stmt = connection.createStatement()) {
    stmt.closeOnCompletion();
    try (ResultSet rs = stmt.executeQuery("SELECT id FROM users")) {
        // Đọc result.
    }
    // stmt có thể đã auto-close.
}
// try ngoài gọi stmt.close() lần nữa: no-op nếu đã closed.
```

Nhưng nếu code muốn dùng `stmt` sau khi inner try đóng ResultSet, thì nó có thể đã closed. Để tránh bất ngờ, chỉ bật khi bạn chủ đích chấm dứt vòng đời statement cùng dependent results.

### 10.3. Lỗi trước khi tạo ResultSet

Nếu `executeQuery` ném `SQLException` trước khi trả ResultSet, không có resource result set để kích hoạt auto-close. Outer `try (Statement ...)` hoặc `finally { stmt.close(); }` vẫn cần thiết. Đây là lý do **`closeOnCompletion` không thay thế toàn bộ quản lý tài nguyên**.

### 10.4. Suppressed exceptions

`Statement.close` và `ResultSet.close` có thể ném SQLException. Khi cả code trong try và đóng resource cùng ném exception, `try-with-resources` giữ exception khi close trong `getSuppressed()`. Với cleanup thủ công, tránh để lỗi khi close che root cause. Có thể xem thêm `SQLException.getNextException()`, `getSQLState()`, vendor error code khi phân tích.

### 10.5. Không trông chờ GC/finalizer

GC không có deadline đóng server cursors/connections. Không để JDBC resources rời scope rồi hy vọng JVM sẽ giải phóng ngay. Dùng explicit close, try-with-resources và ownership rõ ràng.

## 11. Demo Java 17+ chạy không cần database: test double JDBC

Vì JDK có `java.sql` interfaces nhưng không cung cấp sẵn database driver/server phổ quát, chương trình này tạo một **in-memory test double** bằng `java.lang.reflect.Proxy`, chỉ implement vài methods cần kiểm tra. Nó **mô phỏng các quy tắc vòng đời đã nêu**, không thực thi SQL thật, không chứng minh một driver thực hiện đúng `closeOnCompletion`. Tên `MULTI` bên dưới là tín hiệu mô phỏng, **không phải câu SQL**.

Demo kiểm tra:
- Đóng ResultSet thông thường không tự đóng Statement.
- Khi đã bật close-on-completion, Statement còn mở nếu ResultSet đang mở.
- Đóng result cuối sẽ tự đóng Statement, **Connection vẫn mở**.
- Bật close-on-completion sau khi đã có ResultSet.
- Chỉ có update count, không có result set, statement không tự đóng.
- Giữ hai results (mô phỏng `KEEP_CURRENT_RESULT`): đóng result thứ nhất chưa đủ; đóng thứ hai mới auto-close.
- Đóng Statement tường minh đóng ResultSet.
- Outer try đóng Connection cuối cùng.

### 11.1. Mã `JdbcCloseOnCompletionDemo.java`

```java
import java.lang.reflect.*;
import java.sql.*;
import java.util.*;

public final class JdbcCloseOnCompletionDemo {
    static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }
    static <T> T proxy(Class<T> api, InvocationHandler h) {
        return api.cast(Proxy.newProxyInstance(
                JdbcCloseOnCompletionDemo.class.getClassLoader(),
                new Class<?>[]{api}, h));
    }

    // Educational in-memory TEST DOUBLE, not a real JDBC driver.
    static final class FakeConnection {
        boolean closed;
        final List<FakeStatement> statements = new ArrayList<>();
        final Connection api = proxy(Connection.class, this::invoke);

        Object invoke(Object p, Method m, Object[] a) throws SQLException {
            return switch (m.getName()) {
                case "isClosed" -> closed;
                case "close" -> {
                    if (!closed) {
                        closed = true;
                        for (FakeStatement s : statements) s.close();
                    }
                    yield null;
                }
                case "createStatement" -> {
                    if (closed) throw new SQLException("connection closed");
                    FakeStatement s = new FakeStatement(this);
                    statements.add(s);
                    yield s.api;
                }
                default -> throw new SQLFeatureNotSupportedException(
                        "fake connection: " + m.getName());
            };
        }
    }

    static final class FakeStatement {
        final FakeConnection owner;
        final Statement api = proxy(Statement.class, this::invoke);
        final List<FakeResultSet> results = new ArrayList<>();
        FakeResultSet current;
        boolean closed, closeOnCompletion, producedRows, nextPending;

        FakeStatement(FakeConnection owner) {
            this.owner = owner;
        }
        void ensureOpen() throws SQLException {
            if (closed || owner.closed) throw new SQLException("statement closed");
        }
        FakeResultSet newResult() {
            FakeResultSet r = new FakeResultSet(this);
            results.add(r);
            current = r;
            producedRows = true;
            return r;
        }
        void close() {
            if (!closed) {
                closed = true;
                for (FakeResultSet r : results) r.closed = true;
            }
        }
        void onResultClose() {
            if (closeOnCompletion && producedRows
                    && results.stream().allMatch(r -> r.closed)) {
                close();
            }
        }
        Object invoke(Object p, Method m, Object[] a) throws SQLException {
            String method = m.getName();
            if (method.equals("isClosed")) return closed;
            if (method.equals("close")) {
                close();
                return null;
            }
            ensureOpen();
            return switch (method) {
                case "closeOnCompletion" -> {
                    closeOnCompletion = true;
                    yield null;
                }
                case "isCloseOnCompletion" -> closeOnCompletion;
                case "executeQuery" -> newResult().api;
                case "executeUpdate" -> 1;
                case "execute" -> {
                    nextPending = "MULTI".equals(a[0]);
                    newResult();
                    yield true;
                }
                case "getResultSet" ->
                        current == null ? null : current.api;
                case "getMoreResults" -> {
                    int flag = a == null || a.length == 0
                            ? Statement.CLOSE_CURRENT_RESULT : (Integer) a[0];
                    if (flag != Statement.KEEP_CURRENT_RESULT
                            && flag != Statement.CLOSE_CURRENT_RESULT
                            && flag != Statement.CLOSE_ALL_RESULTS)
                        throw new SQLException("bad getMoreResults flag");
                    boolean more = nextPending;
                    nextPending = false;
                    FakeResultSet old = current;
                    if (more) newResult(); else current = null;
                    if (flag == Statement.CLOSE_ALL_RESULTS) {
                        for (FakeResultSet r : List.copyOf(results)) {
                            if (r != current) r.close();
                        }
                    } else if (flag == Statement.CLOSE_CURRENT_RESULT
                            && old != null) {
                        old.close();
                    }
                    yield more;
                }
                default -> throw new SQLFeatureNotSupportedException(
                        "fake statement: " + method);
            };
        }
    }

    static final class FakeResultSet {
        final FakeStatement owner;
        final ResultSet api = proxy(ResultSet.class, this::invoke);
        boolean closed;
        int cursor;
        FakeResultSet(FakeStatement owner) {
            this.owner = owner;
        }
        void close() {
            if (!closed) {
                closed = true;
                owner.onResultClose();
            }
        }
        Object invoke(Object p, Method m, Object[] a) throws SQLException {
            String method = m.getName();
            if (method.equals("isClosed")) return closed;
            if (method.equals("close")) {
                close();
                return null;
            }
            if (closed) throw new SQLException("result set closed");
            return switch (method) {
                case "next" -> ++cursor == 1;
                case "getInt" -> {
                    if (cursor != 1) throw new SQLException("no current row");
                    yield 42;
                }
                case "getStatement" -> owner.api;
                default -> throw new SQLFeatureNotSupportedException(
                        "fake result set: " + method);
            };
        }
    }

    public static void main(String[] args) throws Exception {
        FakeConnection fake = new FakeConnection();
        try (Connection connection = fake.api) {
            Statement regular = connection.createStatement();
            try (ResultSet rs = regular.executeQuery("SELECT 42")) {
                check(rs.next() && rs.getInt(1) == 42, "regular row");
            }
            check(!regular.isClosed(), "regular must remain open");
            System.out.println("regular.statementOpenAfterResult=true");
            regular.close();

            Statement automatic = connection.createStatement();
            automatic.closeOnCompletion();
            check(automatic.isCloseOnCompletion(), "flag");
            ResultSet rows = automatic.executeQuery("SELECT 42");
            check(rows.next() && rows.getInt(1) == 42, "row");
            check(!automatic.isClosed(), "too early");
            System.out.println("automatic.flagEnabled=true");
            System.out.println("automatic.openWhileRowsOpen=true");
            rows.close();
            check(automatic.isClosed(), "not closed when result closed");
            check(!connection.isClosed(), "should not close connection");
            System.out.println("automatic.closedAfterResult=true");
            System.out.println("automatic.connectionRemainsOpen=true");

            Statement late = connection.createStatement();
            ResultSet already = late.executeQuery("SELECT 42");
            late.closeOnCompletion();
            already.close();
            check(late.isClosed(), "existing result ignored");
            System.out.println("late.closedAfterExistingResult=true");

            Statement noResult = connection.createStatement();
            noResult.closeOnCompletion();
            noResult.executeUpdate("UPDATE x SET y = 1");
            check(!noResult.isClosed(), "no result should not close");
            System.out.println("noResult.remainsOpen=true");
            noResult.close();

            Statement multi = connection.createStatement();
            multi.closeOnCompletion();
            check(multi.execute("MULTI"), "first result");
            ResultSet one = multi.getResultSet();
            check(multi.getMoreResults(Statement.KEEP_CURRENT_RESULT),
                    "second result");
            ResultSet two = multi.getResultSet();
            one.close();
            check(!multi.isClosed(), "second remains open");
            System.out.println("multiple.afterFirstStillOpen=true");
            two.close();
            check(multi.isClosed(), "last result should close statement");
            System.out.println("multiple.afterLastClosed=true");

            Statement explicit = connection.createStatement();
            ResultSet open = explicit.executeQuery("SELECT 42");
            explicit.close();
            check(explicit.isClosed() && open.isClosed(), "close cascade");
            System.out.println("explicit.statementClosesResult=true");
        }
        check(fake.closed, "connection must close");
        System.out.println("connection.closedAtEnd=true");
        System.out.println("checks=PASS");
    }
}
```

### 11.2. Biên dịch và chạy

```bash
javac -encoding UTF-8 JdbcCloseOnCompletionDemo.java
java JdbcCloseOnCompletionDemo
```

Mã **đã được biên dịch và chạy thành công** trên JDK 17+, exit code 0, không có database server, không tải JDBC driver bên thứ ba.

### 11.3. Stdout chính xác của chương trình đã chạy

```text
regular.statementOpenAfterResult=true
automatic.flagEnabled=true
automatic.openWhileRowsOpen=true
automatic.closedAfterResult=true
automatic.connectionRemainsOpen=true
late.closedAfterExistingResult=true
noResult.remainsOpen=true
multiple.afterFirstStillOpen=true
multiple.afterLastClosed=true
explicit.statementClosesResult=true
connection.closedAtEnd=true
checks=PASS
```

### 11.4. Đọc kết quả có trách nhiệm

- `regular.statementOpenAfterResult=true`: test double minh họa không tự đóng statement nếu chưa bật policy.
- `automatic.flagEnabled=true` và `automatic.openWhileRowsOpen=true`: đã cấu hình nhưng statement vẫn mở cho tới khi result đóng.
- `automatic.closedAfterResult=true`: ResultSet cuối đóng làm statement đóng.
- `automatic.connectionRemainsOpen=true`: statement close không đóng connection.
- `late.closedAfterExistingResult=true`: bật policy lúc dependent ResultSet đang mở vẫn có tác dụng.
- `noResult.remainsOpen=true`: không có result set thì policy không kích hoạt.
- `multiple.afterFirstStillOpen=true` rồi `multiple.afterLastClosed=true`: nhiều dependents trong mô hình.
- `explicit.statementClosesResult=true`: close statement đóng result liên quan.
- `connection.closedAtEnd=true`: outer try cleanup connection.

**Ranh giới kiểm chứng:** Các kết quả là hành vi của **test double được lập trình để phản ánh contract**, không phải bằng chứng thực nghiệm cho Oracle/PostgreSQL/MySQL/SQL Server/H2 driver cụ thể. Để kiểm chứng driver, dùng chương trình mục 12 và integration tests.

## 12. Ví dụ JDBC driver thật: đã biên dịch, cần database để chạy

Mã dưới đây dùng JDBC API thật và **đã biên dịch** bằng JDK 17+. Cần driver, URL, user, password và một `SELECT` hợp lệ mới có thể chạy, vì JDK không tự cung cấp một database đầy đủ để kiểm thử mọi driver.

### 12.1. `RealJdbcCloseOnCompletionExample.java`

```java
import java.sql.*;

public final class RealJdbcCloseOnCompletionExample {
    public static void main(String[] args) throws SQLException {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: <jdbcUrl> <username> <trustedSelectSql>");
        }
        String password = System.getenv("DB_PASSWORD");
        if (password == null) {
            throw new IllegalArgumentException("DB_PASSWORD not set");
        }
        try (Connection connection = DriverManager.getConnection(
                args[0], args[1], password)) {
            Statement statement = connection.createStatement();
            try {
                statement.closeOnCompletion();
                int rowsRead = 0;
                try (ResultSet rs = statement.executeQuery(args[2])) {
                    while (rs.next()) {
                        rowsRead++;
                    }
                }
                System.out.println("rowsRead=" + rowsRead);
                System.out.println("statementClosed=" + statement.isClosed());
            } finally {
                statement.close(); // Safe even if already auto-closed.
            }
            System.out.println("connectionStillOpen=" + !connection.isClosed());
        }
    }
}
```

### 12.2. Cách sử dụng

```bash
javac -encoding UTF-8 RealJdbcCloseOnCompletionExample.java
```

Thiết lập biến môi trường `DB_PASSWORD` theo hệ điều hành, thêm JDBC driver tương ứng vào runtime classpath, rồi gọi với ba arguments `<jdbcUrl>`, `<username>` và câu SELECT **do developer tin cậy**.

Dạng minh họa, **không phải lệnh đã thực thi với DB**:

```text
java -cp "<driver-jar><platform-classpath-separator>." \
  RealJdbcCloseOnCompletionExample "<jdbc-url>" "<username>" "<select-sql>"
```

Trên Windows classpath separator là `;`, trên Unix-like là `:`. Không đưa password lên command line/log. Trong ứng dụng production, **không cho người dùng chưa tin cậy truyền thẳng SQL string** như một đoạn truy vấn được thực thi; dùng SQL do code kiểm soát và `PreparedStatement` với bind parameters.

### 12.3. Kết quả mong đợi khi driver tuân thủ API

```text
rowsRead=<actual row count>
statementClosed=true
connectionStillOpen=true
```

`rowsRead` phụ thuộc dữ liệu thực, **không phải stdout cố định đã chạy**. Nếu driver không hỗ trợ `closeOnCompletion` hoặc query fail, method có thể ném `SQLException` / `SQLFeatureNotSupportedException`; statement vẫn được cleanup trong finally.

### 12.4. Integration test nên làm trên driver thực

- Tạo connection bằng driver mà production đang sử dụng.
- `stmt.closeOnCompletion()` thành công; `isCloseOnCompletion()==true` khi statement còn mở.
- Khi ResultSet còn mở, `stmt.isClosed()==false`.
- Sau khi đóng ResultSet cuối, `stmt.isClosed()==true`.
- `connection.isClosed()==false` cho tới khi owner đóng connection.
- `executeUpdate` không tạo ResultSet thì policy không thay cleanup tường minh.
- Nếu có stored procedures/multiple results, thử `supportsMultipleOpenResults` và flags.
- Kiểm tra cả failure paths, generated keys và transaction/holdability với driver đó.

## 13. Ma trận kiểm thử

| Test | Kỳ vọng |
| --- | --- |
| Không bật close-on-completion | Đóng ResultSet không mặc nhiên đóng Statement |
| Bật policy trước execute | `isCloseOnCompletion()==true` |
| ResultSet còn mở | Statement chưa auto-close |
| Đóng dependent ResultSet duy nhất | Statement auto-close |
| Bật policy khi result đã mở | Khi result đóng, policy có hiệu lực |
| Gọi policy lặp lại | Không toggle off |
| Hai dependent ResultSets cùng mở | Đóng cái thứ nhất chưa đóng stmt nếu cái thứ hai còn mở |
| Đóng dependent ResultSet cuối | Statement đóng |
| ExecuteUpdate không tạo ResultSet | Statement không tự đóng do policy |
| ExecuteQuery thất bại trước khi trả result | Outer finally/try phải đóng stmt |
| `Statement.close()` | Dependent result sets đóng |
| Re-execute Statement | Current ResultSet trước bị đóng ngầm |
| `getMoreResults()` default | Current result bị đóng khi chuyển |
| `getMoreResults(KEEP_CURRENT_RESULT)` | Phụ thuộc driver support |
| `isClosed()` sau auto-close | True |
| `isCloseOnCompletion()` sau auto-close | Không dùng thay isClosed; có thể SQLException |
| `Connection` đang mở | Không tự đóng chỉ vì Statement đóng |
| `try-with-resources` lặp close | Statement.close trên closed statement no-op |
| Transaction | Auto-close statement không commit/rollback |
| LOB resources | Chú ý Blob/Clob/NClob lifecycle riêng |
| Connection pool | Trả logical Connection đúng owner |
| Driver không hỗ trợ feature | Cleanup bằng try/finally, không leak |
| Test double vs DB thật | Chỉ DB integration test xác minh driver |

## 14. Những lỗi thường gặp

| Sai lầm | Vấn đề | Cách sửa |
| --- | --- | --- |
| Nghĩ đọc hết `rs.next` là đã close | Cursor exhausted khác closed | `try-with-resources` |
| Nghĩ `rs.close` tự đóng stmt mặc định | Không có policy | `stmt.close`/outer try |
| Nghĩ `closeOnCompletion` đóng ngay | Chỉ bật chính sách | Kiểm tra isClosed sau khi đóng dependent cuối |
| Nhầm `isCloseOnCompletion` với `isClosed` | Config ≠ state | Dùng đúng method |
| Bật policy rồi reuse statement sau khi result đóng | Statement đã auto-close | Tạo Statement mới |
| Gọi policy lặp để tắt | API không toggle | Dùng statement mới nếu cần |
| Query không có ResultSet mà mong auto-close | Không có trigger | Explicit cleanup |
| Query fail trước khi tạo ResultSet | Không kích hoạt auto-close | try-with-resources/finally |
| Giữ ResultSet cũ và re-execute Statement | ResultSet cũ bị đóng ngầm | Hai statements |
| Gọi getMoreResults rồi vẫn dùng old result | Default closes current | Xử lý trước hoặc KEEP được hỗ trợ |
| Dùng KEEP khi driver không hỗ trợ | SQLFeatureNotSupportedException | Check metadata và fallback |
| Tưởng Statement đóng làm Connection đóng | Ownership khác nhau | Outer connection scope |
| Coi Statement.close là transaction commit | Cleanup không phải transaction control | Explicit commit/rollback |
| Không đóng generated keys ResultSet | Resource leak | Nested try-with-resources |
| Dùng `setFetchSize` làm bảo đảm RAM | Chỉ hint | Test driver streaming |
| Đọc ResultSet sau khi Statement đã close | SQLException | Map dữ liệu trước |
| Trả ResultSet ra khỏi method đã đóng stmt | ResultSet không còn hợp lệ | Trả DTO/list hoặc thiết kế ownership rõ |
| Bỏ qua SQLException khi close | Mất diagnosis/leak | Xử lý, giữ root cause |
| Dùng JDBC objects chung giữa nhiều threads | Không có safety contract phổ quát | Thread-confined usage |
| Trông chờ GC dọn resources kịp | Không có deadline | Explicit close |
| Xem mock test là driver certification | Fake mô phỏng semantics | Integration tests trên DB thật |

## 15. Chẩn đoán khi Statement “bỗng bị đóng”

Khi log `SQLException: Statement is closed` xuất hiện:

1. Xác định nơi `closeOnCompletion` được gọi; tính năng có thể đã được bật trong một helper khác.
2. Xem `ResultSet` cuối vừa được đóng bởi `try-with-resources`, bởi `rs.close` hoặc do implicit close.
3. Xem code có **tái thực thi cùng Statement** trong khi vẫn đang giữ ResultSet cũ không.
4. Với stored procedure, xem `getMoreResults` có làm current result bị đóng không.
5. Xem Statement còn được dùng sau inner try kết thúc hay không.
6. Xem Connection/transaction manager có đóng connection khi method return không.
7. Xem driver có hạn chế multiple results hoặc cursor holdability không.
8. Đọc `SQLException.getSQLState()`, `getErrorCode()`, `getNextException()` và suppressed exceptions; tránh in passwords, raw tokens hoặc PII.
9. Viết integration test tối thiểu với đúng driver và version, không lấy kết quả của test double làm bằng chứng.
10. Ưu tiên đơn giản hóa ownership: mỗi truy vấn có statement/result scope ngắn, không chuyển ResultSet ra ngoài nếu không có explicit lifecycle abstraction.

Không cố khắc phục bằng cách gọi `isClosed()` rồi tạo ra một busy loop hoặc cache một statement đã closed. Đóng là trạng thái kết thúc vòng đời object; hãy tạo object mới khi cần.

## 16. FAQ

**1. `closeOnCompletion()` có đóng Statement ngay không?**  
Không, nó bật policy và chờ dependent ResultSets đã đóng.

**2. `isCloseOnCompletion()==true` có nghĩa statement đã đóng?**  
Không. Dùng `isClosed()` để kiểm tra trạng thái.

**3. Đóng ResultSet có tự đóng Statement mặc định không?**  
Không. Chỉ khi có cơ chế như close-on-completion hoặc statement đã bị đóng theo lý do khác.

**4. Đóng Statement có đóng ResultSet không?**  
Có. Current/dependent ResultSet do statement tạo không còn tiếp tục dùng được.

**5. Đọc hết rows có đóng ResultSet không?**  
Không được giả định. Dùng `close()` hoặc try-with-resources.

**6. Bật policy sau khi đã mở ResultSet có tác dụng không?**  
Có, theo Javadoc Java SE 17.

**7. Gọi `closeOnCompletion` nhiều lần có tắt được không?**  
Không. Nó không phải toggle.

**8. Chỉ chạy UPDATE có làm auto-close không?**  
Nếu không tạo ResultSet, `closeOnCompletion` không có trigger.

**9. Có hai ResultSet còn mở, đóng một cái thì sao?**  
Statement chưa được đóng nếu dependent ResultSet khác vẫn đang mở (trong driver hỗ trợ multiple open results).

**10. `getMoreResults()` mặc định có đóng current ResultSet không?**  
Có.

**11. `getMoreResults(KEEP_CURRENT_RESULT)` luôn được hỗ trợ không?**  
Không. Kiểm tra `supportsMultipleOpenResults()`.

**12. Auto-close Statement có đóng Connection không?**  
Không. Connection có owner riêng.

**13. `PreparedStatement` có API này không?**  
Có, vì extends `Statement`.

**14. Auto-close Statement có commit transaction không?**  
Không.

**15. Có nên chỉ dùng closeOnCompletion để dọn resources không?**  
Không. `try-with-resources`/`finally` bảo vệ cả trường hợp lỗi trước khi có ResultSet hoặc không có ResultSet.

**16. `Statement.close()` sau khi statement đã auto-close có gây lỗi không?**  
Theo Javadoc, đóng statement đã closed là no-op.

**17. Đóng ResultSet có đóng Blob/Clob/NClob đã lấy ra không?**  
Không mặc nhiên; những objects đó có lifecycle riêng.

**18. Vì sao test double Java chạy đúng mà driver khác vẫn có thể khác?**  
Test double là mô hình tự xây; driver thực có hỗ trợ feature, server cursor, transaction và nhiều result khác nhau.

## 17. Checklist code review

- [ ] `Connection` có owner và scope riêng.
- [ ] Statement/ResultSet đóng rõ bằng try-with-resources.
- [ ] `closeOnCompletion` chỉ bật khi lifecycle thật sự cần.
- [ ] Phân biệt `isCloseOnCompletion` (policy) và `isClosed` (state).
- [ ] Không tự động cho rằng `closeOnCompletion` đóng ngay.
- [ ] Không coi đọc hết rows là đóng cursor.
- [ ] Không reuse Statement sau khi dependent ResultSet cuối đóng và auto-close.
- [ ] DML không trả ResultSet vẫn có explicit close.
- [ ] Query thất bại trước khi có ResultSet không leak statement.
- [ ] Biết policy áp dụng current/future results và không toggle.
- [ ] Nếu có multiple open results, check metadata và đóng toàn bộ.
- [ ] Không bỏ sót generated-key ResultSet.
- [ ] Không gọi `getMoreResults` khi vẫn cần current result trừ khi KEEP được hỗ trợ.
- [ ] Tránh re-execute cùng statement khi còn giữ prior result.
- [ ] Không đồng nhất Statement.close và Connection.close.
- [ ] Không đồng nhất cleanup và commit/rollback.
- [ ] Hiểu holdability khi commit/streaming.
- [ ] LOB resources có cleanup riêng.
- [ ] Không làm SQL injection khi dùng Statement.
- [ ] Không nuốt SQLException/suppressed exceptions.
- [ ] Không dùng GC làm phương pháp giải phóng JDBC resources.
- [ ] Có integration test với đúng database driver đang chạy.
- [ ] Không xem self-contained test double là test driver thật.
- [ ] Những điểm giải thích chỉ dùng API còn áp dụng trong Java 17+.

## 18. Kết luận và tài liệu chính thức

**Quy tắc quan trọng nhất:**

- `ResultSet.close()`: đóng result set.
- `Statement.close()`: đóng statement và results liên quan; không tự đóng Connection.
- `Statement.closeOnCompletion()`: cấu hình Statement **tự đóng khi tất cả dependent ResultSets đã đóng**; không đóng ngay, không tự đóng trong execution không tạo ResultSet.
- `Statement.isCloseOnCompletion()` khác `Statement.isClosed()`.
- Khi re-execute hoặc chuyển qua next result, ResultSet cũ có thể bị đóng ngầm và điều đó tương tác với policy auto-close.
- `try-with-resources` là lựa chọn dễ hiểu và an toàn cho resource scope; `closeOnCompletion` không thay thế mọi tình huống.
- Muốn khẳng định JDBC driver cụ thể, dùng **integration tests trên driver và DBMS thật**; test double chỉ chứng minh code logic minh họa.

Tính năng từ Java 7/JDBC 4.1 này **vẫn được hỗ trợ trong Java 17+**, không cần trông chờ GC hoặc các phương thức không còn phù hợp.

Tài liệu chính thức Java SE 17:

- [`java.sql.Statement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html): `closeOnCompletion`, `isCloseOnCompletion`, `isClosed`, `getMoreResults`, `execute`, `close`.
- [`java.sql.ResultSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html): `next`, `close`, implicit closing, cursor holdability, LOB resources.
- [`java.sql.Connection`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): connection ownership, transaction lifecycle, commit/rollback và holdability.
- [`java.sql.PreparedStatement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html): bind parameters, executeQuery và executeUpdate.
- [`java.sql.CallableStatement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/CallableStatement.html): stored procedures và nhiều kết quả.
- [`java.sql.DatabaseMetaData`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/DatabaseMetaData.html): `supportsMultipleOpenResults()`.
- [`java.sql.SQLFeatureNotSupportedException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLFeatureNotSupportedException.html): xử lý khi driver chưa hỗ trợ tính năng.
- [`java.sql.DriverManager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/DriverManager.html): lấy Connection qua registered JDBC driver.
