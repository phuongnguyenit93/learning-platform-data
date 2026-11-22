# Phân biệt nguyên nhân gốc và lỗi phát sinh khi dọn tài nguyên

> **Chương:** Lỗi và cảnh báo  
> **Ngữ cảnh:** Ứng dụng Java sử dụng **JDBC** qua `DataSource`, `Connection`, `PreparedStatement` và `ResultSet` để thực hiện SQL tham số hóa, CRUD, transaction và batching.

Một thao tác `INSERT` bị database từ chối vì trùng khóa. Khi chương trình rời khỏi khối `try`, driver lại báo lỗi trong `PreparedStatement.close()`; nếu đang dùng transaction, `Connection.rollback()` cũng có thể thất bại vì mất kết nối. **Lỗi nào cần báo cho người gọi?** Nếu chỉ log lỗi cuối cùng xuất hiện, ta có thể kết luận sai rằng việc đóng tài nguyên là nguyên nhân khiến đơn hàng không được tạo.

Trong JDBC, một thao tác có thể tạo ra **nhiều lỗi liên quan nhưng khác thời điểm và vai trò**:

- **Lỗi khi thực hiện nghiệp vụ (primary failure):** chẳng hạn `executeUpdate()` thất bại vì vi phạm ràng buộc, hoặc kết quả `executeUpdate() == 0` khiến ứng dụng chủ động ném exception.
- **Lỗi khi dọn tài nguyên (cleanup failure):** xảy ra trong `ResultSet.close()`, `Statement.close()`, `Connection.close()`, `rollback()` hoặc khi phục hồi trạng thái connection cho pool.
- **Lỗi dây chuyền của driver/database (linked SQL exceptions):** nhiều thông tin SQL có thể đi cùng một `SQLException` qua `getNextException()`, nhất là khi dùng batch.
- **Cảnh báo (warning):** `SQLWarning` thông báo tình huống cần xem xét nhưng thông thường không tự chấm dứt thao tác như một exception được ném.

Mục tiêu của bài này là **giữ nguyên thông tin về lỗi đầu tiên làm nghiệp vụ thất bại**, đồng thời không đánh mất dấu vết của lỗi xảy ra trong quá trình rollback/close. Đây cũng là kỹ năng cần thiết khi chẩn đoán transaction không hoàn tất, connection pool gặp trục trặc hoặc batch JDBC trả về nhiều lỗi.

## 1. Phân biệt lỗi theo vai trò, không chỉ theo tên exception

**Nguyên nhân gốc** trong điều tra sự cố là lỗi hoặc điều kiện ban đầu dẫn đến thất bại cần giải thích. **Exception chính (primary exception)** là exception được giữ làm đầu mối của đường truyền lỗi ở một phạm vi `try`. Hai khái niệm này thường trùng nhau, nhưng không tuyệt đối: một exception từ driver có thể chỉ là triệu chứng của sự cố mạng hoặc database ở tầng thấp hơn.

| Thời điểm | Ví dụ | Vai trò khi phân tích |
|---|---|---|
| Khi bind/gọi SQL | `executeUpdate()` ném `SQLException` do khóa unique trùng | Thường là lỗi chính của thao tác ghi |
| Khi xử lý kết quả | `ResultSet.getLong()` thất bại khi đọc dữ liệu | Lỗi chính của thao tác đọc |
| Khi xử lý nghiệp vụ | Ứng dụng ném `IllegalStateException` vì không đủ tồn kho | Lỗi chính của use case |
| Khi rollback sau lỗi chính | `Connection.rollback()` ném `SQLException` do kết nối hỏng | Lỗi phụ cần giữ lại; không được che lỗi trước |
| Khi đóng statement/result set | `close()` ném lỗi trong quá trình rời `try` | Lỗi phụ nếu đã có lỗi chính; có thể là lỗi chính nếu thân `try` thành công |
| Khi đóng connection sau commit | `Connection.close()` thất bại | Lỗi cleanup được quan sát đầu tiên; **không đồng nghĩa commit thất bại** |

Ví dụ trình tự:

```text
T0   PreparedStatement.executeUpdate()  -> SQLException: unique violation
T1   catch của transaction              -> rollback()
T2   Connection.rollback()              -> SQLException: connection lost
T3   try-with-resources                  -> close() cũng có thể lỗi
T4   caller nhận lỗi chính kèm các lỗi phát sinh khi cleanup
```

**Câu hỏi cần trả lời theo thứ tự:** Điều gì thất bại trước? Lỗi đó phát sinh ở thao tác nghiệp vụ nào? Các lỗi về sau xuất hiện khi cố hoàn tác/dọn dẹp hay trong một thao tác nghiệp vụ khác? Trạng thái transaction đã được xác nhận, đã rollback hay vẫn không rõ?

Không nên suy luận rằng lỗi có stack trace xuất hiện *cuối cùng* hoặc message dài nhất là nguyên nhân gốc.

## 2. Vì sao `finally` có thể che mất lỗi ban đầu?

Trong Java, nếu `finally` ném một exception khác khi đang có exception từ `try`, exception trong `finally` có thể thay thế exception ban đầu trên đường thoát của phương thức.

### 2.1. Cách dễ làm mất lỗi chính

```java
// Ví dụ cố ý SAI: close() có thể che lỗi executeUpdate().
Connection connection = dataSource.getConnection();

try {
    PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO customers (id, name) VALUES (?, ?)"
    );
    try {
        ps.setLong(1, 10L);
        ps.setString(2, "An");
        ps.executeUpdate();            // Có thể lỗi trùng khóa.
    } finally {
        ps.close();                    // Có thể ném SQLException khác.
    }
} finally {
    connection.close();                // Có thể tiếp tục che lỗi trước.
}
```

Nếu `executeUpdate()` đã ném lỗi, rồi `ps.close()` cũng ném lỗi, đối tượng exception nhận được ở caller có thể là lỗi đóng statement. Lỗi của câu `INSERT` bị mất nếu không được lưu lại một cách chủ động. Thêm `catch` để log lỗi trước khi ném lại cũng không bảo đảm hệ thống giám sát hoặc tầng gọi nhìn thấy đúng lỗi.

Không viết cleanup kiểu sau trong `finally` nếu nó có thể ném:

```java
finally {
    connection.rollback(); // Nếu ném, có thể che exception gây rollback.
    connection.close();    // Nếu rollback ném, câu này còn không được chạy.
}
```

### 2.2. Ưu tiên `try-with-resources` cho tài nguyên JDBC

`try-with-resources` xử lý đóng tài nguyên theo cơ chế của Java: khi thân `try` đã ném exception, các exception từ `close()` sẽ được lưu trong danh sách **suppressed** của exception chính.

```java
String sql = "INSERT INTO customers (id, name) VALUES (?, ?)";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, 10L);
    statement.setString(2, "An");
    statement.executeUpdate();

} catch (SQLException primary) {
    System.err.println("Primary: " + primary.getMessage());

    for (Throwable cleanup : primary.getSuppressed()) {
        System.err.println("Suppressed cleanup: " + cleanup.getMessage());
    }

    throw primary; // Giữ nguyên stack trace và metadata của SQLException.
}
```

Thứ tự đóng ở đây là **ngược** thứ tự khai báo: `statement.close()` rồi `connection.close()`. Nếu `executeUpdate()` ném exception, các lỗi `close()` được gắn qua `getSuppressed()`; ngoại lệ ban đầu vẫn là exception được ném lên caller.

Những trường hợp cần phân biệt:

1. **Thân `try` lỗi; `close` cũng lỗi:** lỗi từ thân `try` là chính, lỗi đóng được suppressed.
2. **Thân `try` thành công; `close` lỗi:** lỗi đóng là exception chính vì tại thời điểm đó chưa có lỗi trước. Không được giả định SQL thất bại.
3. **Có nhiều tài nguyên; nhiều `close` lỗi:** lỗi đóng đầu tiên trở thành chính nếu thân `try` thành công; các lỗi đóng tiếp theo được suppressed.
4. **Khởi tạo tài nguyên phía sau lỗi:** các tài nguyên đã khởi tạo thành công trước đó vẫn được đóng; lỗi đóng trong quá trình này có thể được suppressed trên lỗi khởi tạo.

Với `ResultSet`, mẫu sở hữu rõ ràng là:

```java
String sql = "SELECT customer_name FROM customers WHERE id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, 10L);

    try (ResultSet rs = statement.executeQuery()) {
        if (rs.next()) {
            System.out.println(rs.getString("customer_name"));
        }
    }
}
```

DAO tạo `ResultSet` thì DAO đóng `ResultSet`; DAO tạo `PreparedStatement` thì DAO đóng statement. Nếu `Connection` được **service cho mượn để tham gia một transaction chung**, DAO **không** đưa connection đó vào `try-with-resources` và không gọi `close()`, `commit()` hay `rollback()`. Chỉ chủ sở hữu connection/transaction mới quyết định việc hoàn tất và đóng connection.

## 3. Tự chứng minh cách suppressed exception hoạt động

Có thể kiểm tra cơ chế Java bằng ví dụ tự chứa sau, không cần database. Cả thao tác chính lẫn thao tác đóng đều cố ý ném lỗi:

```java
import java.sql.SQLException;

public class SuppressedDemo {
    public static void main(String[] args) {
        try (AutoCloseable resource = () -> {
            throw new SQLException("close failed", "08006");
        }) {
            throw new SQLException("insert violated unique constraint", "23505");
        } catch (Exception failure) {
            System.out.println("MAIN: " + failure.getMessage());
            for (Throwable suppressed : failure.getSuppressed()) {
                System.out.println("SUPPRESSED: " + suppressed.getMessage());
            }
        }
    }
}
```

Kết quả kỳ vọng:

```text
MAIN: insert violated unique constraint
SUPPRESSED: close failed
```

Ở đây các SQLState chỉ là **dữ liệu minh họa**; không có database nào thực thi câu SQL thật. Điểm quan trọng là `failure` còn giữ lỗi `INSERT` làm primary, và lỗi `close` được lưu để điều tra.

Nếu bỏ dòng `throw new SQLException(...)` bên trong thân `try` và chỉ để resource ném lúc đóng, `close failed` sẽ trở thành exception chính. Vì vậy **không gọi mọi exception trong `getSuppressed()` là “lỗi vô hại”**: chúng có thể báo hiệu connection hỏng, rollback bất thành hoặc leak tài nguyên có hệ thống.

## 4. Ba đường liên kết khác nhau trong thông tin lỗi Java/JDBC

JDBC có nhiều cơ chế liên kết exception. Khi chẩn đoán, cần xem **cả ba**:

| Cơ chế | API | Nội dung thường gặp |
|---|---|---|
| Quan hệ nhân quả Java | `Throwable.getCause()` | Exception ở tầng thấp được wrap thành exception tầng cao |
| Exception khi dọn tài nguyên | `Throwable.getSuppressed()` | Lỗi `close()` từ try-with-resources; lỗi `rollback()`/reset thêm thủ công |
| Chuỗi SQL của JDBC | `SQLException.getNextException()` | Thông tin SQL liên kết do driver/DBMS cung cấp, có thể gồm nhiều lỗi từ batch |

Ba cơ chế này **không đồng nghĩa** và không phải lúc nào cũng biểu diễn cùng một cây nhân quả. `getNextException()` là danh sách liên kết bổ sung của JDBC, không phải danh sách lỗi bị suppressed. `getCause()` phản ánh nguyên nhân được lưu bằng cơ chế của Java. Một lần gọi `getMessage()` trên exception đầu tiên sẽ không trình bày đầy đủ các nhánh đó.

Ví dụ error wrapping:

```java
try {
    customerDao.insert(connection, customer);
} catch (SQLException sqlFailure) {
    throw new CustomerPersistenceException(
        "Could not create customer", sqlFailure
    );
}
```

Khi dùng constructor giữ `cause`, tầng ngoài có thể đọc:

```java
Throwable cause = error.getCause();
if (cause instanceof SQLException sql) {
    System.err.println(sql.getSQLState());
    System.err.println(sql.getErrorCode());
}
```

Nếu chỉ tạo exception mới bằng message rồi bỏ qua cause, người điều tra sẽ mất SQLState, vendor code, SQL exception chain và thông tin suppressed của lỗi gốc.

### 4.1. Đọc `SQLException` đúng cách

Các thuộc tính thường cần khi triage:

- `getSQLState()`: mã trạng thái theo quy ước SQLState, nếu driver cung cấp.
- `getErrorCode()`: mã lỗi của nhà cung cấp (vendor-specific), có thể bằng `0` nếu không được cung cấp.
- `getMessage()`: mô tả dành cho chẩn đoán; không nên dùng chuỗi message làm API phân loại lỗi.
- `getNextException()`: lỗi SQL được liên kết với exception hiện tại.
- `getCause()` và `getSuppressed()`: ngữ cảnh Java và lỗi cleanup.

Ví dụ đọc chuỗi SQL:

```java
static void printSqlChain(SQLException first) {
    for (SQLException current = first;
         current != null;
         current = current.getNextException()) {

        System.err.printf(
            "SQLState=%s vendorCode=%d message=%s%n",
            current.getSQLState(),
            current.getErrorCode(),
            current.getMessage()
        );
    }
}
```

Đoạn này dành cho chuỗi JDBC thông thường, không áp dụng cho đồ thị liên kết bị lỗi có vòng lặp. Trong logging sản xuất, nên thêm giới hạn độ sâu/đếm và cơ chế phát hiện vòng lặp để một driver lỗi không khiến log chạy vô hạn.

SQLState class `23` thường liên quan đến vi phạm ràng buộc toàn vẹn; `08` thường liên quan đến kết nối; `40` thường liên quan đến rollback transaction. Nhưng giá trị cụ thể và khả năng phân loại vẫn tùy driver/DBMS. **SQLState gần nhất về mặt kỹ thuật chưa chắc là nguyên nhân nghiệp vụ**: một lỗi kết nối có thể xảy ra *trong rollback sau khi INSERT đã bị từ chối*.

### 4.2. Batch có thể chứa nhiều thông tin lỗi

`PreparedStatement.executeBatch()` có thể ném `BatchUpdateException`. Exception này còn cho biết các số lượng cập nhật mà driver đã báo về:

```java
try {
    statement.executeBatch();
} catch (java.sql.BatchUpdateException failure) {
    int[] counts = failure.getUpdateCounts();
    System.err.println("Reported batch results: " + counts.length);

    for (int count : counts) {
        if (count == java.sql.Statement.EXECUTE_FAILED) {
            System.err.println("A reported batch item failed");
        }
    }

    printSqlChain(failure);
    throw failure;
}
```

Tùy driver và cách thực thi batch, `counts` có thể ngắn hơn số lệnh đã gửi hoặc có phần tử `SUCCESS_NO_INFO`/`EXECUTE_FAILED`. Với số hàng cập nhật rất lớn, có thể cân nhắc `getLargeUpdateCounts()` nếu driver hỗ trợ. **Không kết luận transaction đã commit** chỉ vì một số phần tử trong batch có kết quả dương: chủ sở hữu transaction vẫn phải rollback khi nhóm thao tác cần nguyên tử và một bước thiết yếu thất bại.

## 5. Rollback lỗi: lưu cả nguyên nhân và hậu quả cleanup

Trong transaction JDBC do service sở hữu, lỗi SQL thường dẫn đến quyết định `rollback()`. Nhưng **rollback cũng có thể thất bại**, ví dụ kết nối mạng đã hỏng hoặc database không còn phản hồi. Nếu viết:

```java
// Không nên làm: rollbackFailure có thể che originalFailure.
catch (SQLException originalFailure) {
    connection.rollback();
    throw originalFailure;
}
```

thì `rollback()` ném lỗi sẽ khiến `throw originalFailure` không bao giờ chạy. Cần chủ động gắn lỗi rollback vào original failure.

### 5.1. Mẫu rollback giữ exception ban đầu

```java
try {
    accountDao.debit(connection, fromId, amount);
    accountDao.credit(connection, toId, amount);
    connection.commit();

} catch (SQLException | RuntimeException failure) {
    try {
        connection.rollback();
    } catch (SQLException rollbackFailure) {
        failure.addSuppressed(rollbackFailure);
    }
    throw failure;
}
```

Mẫu trên giả định `connection` đang được chủ sở hữu đặt `autoCommit=false`, các DAO dùng **chính connection đó**, và caller quản lý thời điểm đóng connection. Lỗi do nghiệp vụ hoặc SQL tiếp tục là exception chính; lỗi rollback được giữ trong `getSuppressed()`.

Đây **chưa phải** bộ quản lý transaction hoàn chỉnh: chưa thể hiện khởi tạo `Connection`, dọn trạng thái pool, hay phân biệt lỗi `commit()`. Ví dụ đầy đủ hơn có ở mục 6.

**Không tự động xem `rollback()` thành công sau `commit()` lỗi là bằng chứng dữ liệu chưa commit.** Nếu mạng lỗi ngay lúc server đã commit nhưng trước khi client nhận phản hồi, transaction có thể đã hoàn tất trên server. Cần một khóa nghiệp vụ/idempotency key ổn định để đối soát kết quả trước khi retry.

### 5.2. Có cần `addSuppressed()` thủ công trong mọi trường hợp?

- Với lỗi xảy ra từ `AutoCloseable.close()` trong `try-with-resources`, **Java tự thêm suppressed** khi đã có exception chính.
- Với lỗi xảy ra từ lệnh `connection.rollback()` được gọi **bên trong `catch`**, Java **không tự thêm** vào exception đang được bắt. Lúc đó phải `addSuppressed()` thủ công nếu muốn giữ lỗi gốc làm exception chính.
- Với lỗi từ dọn trạng thái như `setAutoCommit(original)` hoặc khôi phục `readOnly`/isolation, cần xác định đó là lỗi chính đầu tiên hay lỗi phụ của thất bại trước; không đơn giản ném đè lên lỗi đã có.

`Throwable.addSuppressed()` yêu cầu đối tượng suppressed khác với đối tượng exception chính; nếu một adapter tùy biến trả về chính đối tượng đang bị bắt, không thêm self-suppression.

## 6. Ví dụ hoàn chỉnh: service quản lý transaction và cleanup an toàn

Giả sử database có hai bảng:

```sql
CREATE TABLE inventory (
    sku VARCHAR(80) PRIMARY KEY,
    available INTEGER NOT NULL CHECK (available >= 0)
);

CREATE TABLE reservations (
    reservation_id BIGINT PRIMARY KEY,
    sku VARCHAR(80) NOT NULL REFERENCES inventory(sku),
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);
```

Một yêu cầu đặt hàng trừ tồn kho rồi ghi reservation. Hai câu SQL phải cùng thành công hoặc cùng rollback. Ví dụ sau dùng JDBC chuẩn, Java 17+, và giả định `DataSource` cấp connection **sạch, đang ở `autoCommit=true`** để service có toàn quyền quyết định transaction; DAO không sở hữu connection.

### 6.1. Hai DAO chỉ quản lý statement

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

final class InventoryDao {
    int reserve(Connection connection, String sku, int quantity)
            throws SQLException {

        String sql = """
            UPDATE inventory
            SET available = available - ?
            WHERE sku = ? AND available >= ?
            """;

        try (PreparedStatement statement =
                 connection.prepareStatement(sql)) {
            statement.setInt(1, quantity);
            statement.setString(2, sku);
            statement.setInt(3, quantity);
            return statement.executeUpdate();
        }
    }
}

final class ReservationDao {
    void insert(Connection connection, long id, String sku, int quantity)
            throws SQLException {

        String sql = """
            INSERT INTO reservations (reservation_id, sku, quantity)
            VALUES (?, ?, ?)
            """;

        try (PreparedStatement statement =
                 connection.prepareStatement(sql)) {
            statement.setLong(1, id);
            statement.setString(2, sku);
            statement.setInt(3, quantity);

            if (statement.executeUpdate() != 1) {
                throw new SQLException("Expected one reservation row");
            }
        }
    }
}
```

Nếu `statement.executeUpdate()` thất bại và `statement.close()` cũng thất bại, `try-with-resources` giữ exception SQL của lệnh DML làm primary. DAO **không catch-and-ignore** lỗi và **không tự rollback** transaction của service.

### 6.2. Service giữ lỗi chính xuyên suốt commit, rollback và close

```java
import java.sql.Connection;
import java.sql.SQLException;
import java.util.Objects;
import javax.sql.DataSource;

public final class ReservationService {
    private final DataSource dataSource;
    private final InventoryDao inventoryDao = new InventoryDao();
    private final ReservationDao reservationDao = new ReservationDao();

    public ReservationService(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public void reserve(long reservationId, String sku, int quantity)
            throws SQLException {

        Objects.requireNonNull(sku, "sku");
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        try (Connection connection = dataSource.getConnection()) {
            boolean previousAutoCommit = connection.getAutoCommit();
            if (!previousAutoCommit) {
                throw new SQLException("Expected an idle, auto-commit connection");
            }

            connection.setAutoCommit(false);

            Throwable primaryFailure = null;
            boolean transactionEnded = false;

            try {
                int updated = inventoryDao.reserve(connection, sku, quantity);
                if (updated != 1) {
                    throw new IllegalStateException(
                        "SKU absent or insufficient stock: " + sku
                    );
                }

                reservationDao.insert(
                    connection, reservationId, sku, quantity
                );

                connection.commit();
                transactionEnded = true;

            } catch (SQLException | RuntimeException | Error failure) {
                primaryFailure = failure;

                try {
                    connection.rollback();
                    transactionEnded = true;
                } catch (SQLException rollbackFailure) {
                    // Giữ lỗi đầu tiên, kèm bối cảnh rollback thất bại.
                    failure.addSuppressed(rollbackFailure);
                }

                throw failure;

            } finally {
                // Chỉ reset auto-commit nếu transaction đã kết thúc
                // bằng commit/rollback thành công theo phản hồi JDBC.
                if (transactionEnded) {
                    try {
                        connection.setAutoCommit(previousAutoCommit);
                    } catch (SQLException resetFailure) {
                        if (primaryFailure != null) {
                            primaryFailure.addSuppressed(resetFailure);
                        } else {
                            throw resetFailure;
                        }
                    }
                }
            }
            // Connection.close() do try-with-resources xử lý.
        }
    }
}
```

Diễn giải theo đường lỗi:

| Kịch bản | Exception chính đến caller | Thông tin cleanup |
|---|---|---|
| `inventoryDao.reserve()` báo không đủ hàng | `IllegalStateException` từ service | Rollback/close lỗi, nếu có, được suppressed |
| `reservations` vi phạm `PRIMARY KEY` | `SQLException` từ `executeUpdate()` | Rollback và close lỗi được giữ lại |
| `PreparedStatement.close()` lỗi sau SQL thành công | Lỗi `close()` trở thành exception chính của DAO | Service rollback vì chưa commit |
| `rollback()` lỗi sau `INSERT` lỗi | Exception của `INSERT` vẫn là chính | Exception rollback được suppressed |
| `commit()` lỗi | Exception commit là chính | Rollback được thử, nhưng kết quả commit có thể không rõ |
| `commit()` thành công, reset auto-commit lỗi | Exception reset là chính | Transaction có thể đã commit; không retry như thể SQL chưa chạy |
| `commit()` và reset thành công, `Connection.close()` lỗi | Exception close là chính | Thao tác nghiệp vụ có thể đã commit |

**Điểm giới hạn:** `transactionEnded=true` nghĩa JDBC đã trả về thành công từ `commit()` hoặc `rollback()`; nếu có lỗi mạng ngay tại `commit()`, kết quả thực tế trên server vẫn có thể không xác định. Một `rollback()` trả về thành công sau lỗi commit không đủ chứng minh lần commit trước đã không thành công. Việc phục hồi connection state là trách nhiệm chung của code sở hữu transaction và pool; pool phải loại bỏ connection hỏng theo cơ chế của nó.

Khối `catch` bao gồm `Error` nhằm cố gắng rollback ngay cả khi xảy ra lỗi nghiêm trọng của JVM, song không thể bảo đảm rollback thành công dưới mọi loại `Error` hoặc khi tiến trình bị dừng đột ngột. Tính nguyên tử cuối cùng dựa vào DBMS và phục hồi transaction của nó.

**Lưu ý về cách xử lý lỗi:** đừng biến mọi `SQLException` thành “đã rollback an toàn”. Nếu cả rollback và close đều báo lỗi, trạng thái connection hoặc transaction phải được xem là đáng nghi. Việc trả lỗi cho caller nên giữ thông tin gốc để service cấp trên có thể quyết định retry hay đối soát.

## 7. Đọc và log cây lỗi mà không mất thông tin

Khi muốn điều tra, chỉ log `ex.getMessage()` là chưa đủ. Một exception có thể chứa:

```text
SQLException: INSERT violates unique constraint
  ├── nextException: detailed database error from driver
  ├── cause: lower-level I/O failure (nếu có)
  └── suppressed:
       ├── SQLException: rollback failed
       └── SQLException: connection close failed
```

Các nhánh này không nhất thiết xuất hiện đồng thời hoặc theo đúng hình dạng trên. Một số driver có thể gắn các thông tin khác nhau ở `cause` và `getNextException()`.

Ví dụ helper ghi nhận **primary**, chuỗi JDBC và các lỗi suppressed một cách hữu hạn:

```java
import java.sql.SQLException;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

final class JdbcFailureReporter {
    private JdbcFailureReporter() {}

    static void report(Throwable failure) {
        Set<Throwable> seen = Collections.newSetFromMap(
            new IdentityHashMap<>()
        );
        describe("primary", failure, seen, 0);
    }

    private static void describe(
            String role,
            Throwable failure,
            Set<Throwable> seen,
            int depth
    ) {
        if (failure == null || depth > 20 || !seen.add(failure)) {
            return;
        }

        String sqlDetails = "";
        if (failure instanceof SQLException sql) {
            sqlDetails = " sqlState=" + sql.getSQLState()
                       + " vendorCode=" + sql.getErrorCode();
        }

        System.err.printf(
            "%s: %s: %s%s%n",
            role,
            failure.getClass().getSimpleName(),
            failure.getMessage(),
            sqlDetails
        );

        // Không giả định nextException là cause hoặc suppressed.
        if (failure instanceof SQLException sql) {
            describe("sql-next", sql.getNextException(), seen, depth + 1);
        }

        for (Throwable suppressed : failure.getSuppressed()) {
            describe("suppressed", suppressed, seen, depth + 1);
        }

        describe("cause", failure.getCause(), seen, depth + 1);
    }
}
```

Helper này phục vụ **minh họa đường liên kết**, không phải thư viện logging hoàn chỉnh. Trong production, ưu tiên hệ thống log có hỗ trợ stack trace và suppressed exception; giới hạn recursion/độ dài log, dùng correlation ID và tránh ghi trực tiếp tham số SQL nhạy cảm (mật khẩu, token, thông tin cá nhân, dữ liệu thanh toán).

Nếu wrap lỗi bằng exception nghiệp vụ, hãy truyền `cause` vào constructor. Khi cần giữ lỗi rollback phát sinh trong quá trình xử lý thêm, gắn vào **exception được propagate** phù hợp và giữ các liên kết của exception gốc; không “dịch” sang một exception mới chỉ chứa chuỗi message.

## 8. `SQLWarning` không phải lỗi cleanup

`SQLWarning` kế thừa `SQLException` nhưng được JDBC thiết kế để biểu diễn **cảnh báo có thể truy xuất** trên connection, statement hoặc result set. Nó thường không xuất hiện trong `catch (SQLException)` vì driver không nhất thiết ném warning như lỗi; mã cần chủ động truy vấn:

```java
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLWarning;

try (PreparedStatement statement =
         connection.prepareStatement("SELECT id FROM customers")) {

    try (ResultSet rs = statement.executeQuery()) {
        // Tiêu thụ kết quả truy vấn theo yêu cầu nghiệp vụ.
        while (rs.next()) {
            System.out.println(rs.getLong("id"));
        }

        for (SQLWarning warning = rs.getWarnings();
             warning != null;
             warning = warning.getNextWarning()) {
            System.err.println("ResultSet warning: " + warning.getMessage());
        }
    }

    for (SQLWarning warning = statement.getWarnings();
         warning != null;
         warning = warning.getNextWarning()) {
        System.err.println("Statement warning: " + warning.getMessage());
    }
}
```

Có thể đọc `connection.getWarnings()` khi cần. Khả năng warning nào được ghi nhận, nơi được gắn và thời điểm chúng bị xóa phụ thuộc driver. Nếu warning quan trọng với nghiệp vụ, đọc chúng **trong thời gian tài nguyên còn mở**; `clearWarnings()` dùng để xóa danh sách cảnh báo đã lưu theo API phù hợp.

Đừng coi `SQLWarning` là `getSuppressed()` của một exception SQL. `getNextWarning()` là chuỗi cảnh báo, còn `getNextException()` là chuỗi SQL exception nói chung. Đừng tự động rollback mọi warning; hãy dựa trên chính sách nghiệp vụ và mức độ ảnh hưởng của cảnh báo cụ thể.

## 9. Chẩn đoán lỗi khi dùng batch và connection pool

### 9.1. Batch: phân biệt lỗi từng statement với lỗi kết thúc transaction

Giả sử một batch có 100 bản ghi, 60 bản ghi được báo thành công rồi statement thứ 61 vi phạm ràng buộc. `BatchUpdateException` có thể đi kèm `updateCounts` và SQL exception chain. Nếu use case yêu cầu ghi **100 bản ghi như một đơn vị**, chủ sở hữu phải rollback trên **cùng connection**, bất kể đã có một số phần tử thành công trước đó.

Lỗi trong `PreparedStatement.close()` sau khi batch thất bại là lỗi cleanup. Nó cần được suppressed để không làm mất thông tin bản ghi/constraint gây thất bại. Nếu connection đã mất và rollback không thực hiện được, cần đánh giá trạng thái commit/transaction thay vì tự suy luận từ số phần tử thành công.

### 9.2. Pool: đóng connection là hoàn trả tài nguyên

Trong nhiều pool, `connection.close()` gọi trên wrapper nghĩa là trả connection về pool, không đóng TCP socket vật lý ngay. Những sai lầm phổ biến:

- DAO tự đóng connection mà service đang dùng chung giữa nhiều thao tác CRUD.
- `finally` gọi `setAutoCommit(true)` trước khi rollback, vô tình xác nhận các thay đổi chưa kết thúc.
- Dọn dẹp lỗi nhưng bỏ qua và trả connection có trạng thái transaction không rõ về pool.
- Service chỉ log lỗi `Connection.close()` rồi kết luận câu `INSERT` trước đó không hề được commit.

Nếu connection ở trạng thái không chắc chắn, hệ thống cần dựa vào pool/driver để loại bỏ hoặc reset connection không dùng lại được. Khi cấu hình pool, hãy kiểm tra timeout, cơ chế validation và chính sách phục hồi trạng thái; một ví dụ JDBC thuần không thể cam kết mọi pool hoạt động giống nhau.

### 9.3. Thứ tự xử lý lỗi và phản hồi API

Bảng quyết định thực hành:

| Lỗi đầu tiên được xác định | Cleanup phát sinh thêm | Hướng xử lý |
|---|---|---|
| SQL constraint violation trước commit | Rollback/close có thể lỗi | Báo nghiệp vụ hoặc xung đột theo constraint, lưu cleanup để điều tra; xem xét trạng thái giao dịch nếu rollback không rõ |
| Lỗi mất kết nối trước commit | Rollback/close có thể lỗi | Ghi lại toàn chuỗi lỗi; trạng thái transaction có thể không rõ nếu đang ở ranh giới commit |
| Lỗi khi `commit()` | Rollback/close có thể lỗi | Không retry mù; đối soát bằng idempotency key/ID yêu cầu |
| Không có lỗi SQL, chỉ statement close lỗi trước commit | Rollback có thể lỗi | Đây là lỗi đầu tiên quan sát được; transaction chưa commit nếu service chủ động rollback thành công |
| Commit thành công, sau đó close lỗi | Không nhất thiết có lỗi khác | Phân biệt lỗi cleanup với kết quả nghiệp vụ đã commit; không tạo bản ghi mới khi retry |

## 10. Chiến lược kiểm thử để nhận ra lỗi bị che

Kiểm thử nên có **hai cấp độ**: thử cơ chế xử lý exception của Java mà không cần database và integration test với driver/database thật để kiểm tra hành vi SQL/rollback.

| Kịch bản | Lỗi gây ra | Điều cần khẳng định |
|---|---|---|
| Body lỗi, close thành công | `executeUpdate()` ném `SQLException` | Exception SQL được giữ làm primary |
| Body lỗi, close cũng lỗi | `executeUpdate()` và `close()` đều ném | Lỗi body là primary, lỗi close xuất hiện trong `getSuppressed()` |
| Body thành công, close lỗi | Chỉ `close()` ném | Lỗi close là primary, không được diễn giải thành lỗi execute |
| SQL lỗi, rollback lỗi | DAO ném trước, `rollback()` ném sau | Exception SQL không bị thay; rollback được suppressed |
| SQL lỗi, rollback thành công | DAO ném, service rollback thành công | Dữ liệu không còn thay đổi từ transaction thất bại |
| Commit thành công, close lỗi | `commit()` thành công rồi `close()` lỗi | Bản ghi có thể đã tồn tại; API không tự tạo lại bản ghi |
| Batch vi phạm constraint | `BatchUpdateException` | Giữ update counts, next exceptions và rollback của cả transaction nếu yêu cầu nguyên tử |
| Error được wrap ở tầng service | Service tạo exception nghiệp vụ với cause | Có thể truy lại cause, SQLState và suppressed của SQL exception |

### 10.1. Một bài kiểm thử đơn giản, không cần mock framework

Thay vì gây lỗi thật lên connection pool, có thể mô phỏng nguyên tắc bằng `AutoCloseable`:

```java
import java.io.IOException;

public class CleanupOrderCheck {
    static class Broken implements AutoCloseable {
        private final String name;

        Broken(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            throw new IOException("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Broken first = new Broken("connection");
             Broken second = new Broken("statement")) {
            throw new IllegalStateException("business operation failed");
        } catch (Exception ex) {
            System.out.println(ex.getMessage());
            for (Throwable extra : ex.getSuppressed()) {
                System.out.println(extra.getMessage());
            }
        }
    }
}
```

Kết quả:

```text
business operation failed
close statement
close connection
```

Ví dụ cho thấy thứ tự đóng ngược với thứ tự khai báo và **hai lỗi close không che lỗi nghiệp vụ**. Khi chuyển sang JDBC thật, hãy dùng `DataSource` của môi trường thử nghiệm, chủ động tạo vi phạm `UNIQUE`/`FOREIGN KEY` và đọc dữ liệu sau rollback để kiểm chứng tính nguyên tử. Đừng cố làm hỏng connection sản xuất chỉ để kiểm thử suppressed exception.

### 10.2. Câu hỏi tự đánh giá

1. Một `INSERT` ném `SQLException`, `PreparedStatement.close()` cũng ném. Exception nào caller nhận trong `try-with-resources` và tìm lỗi còn lại bằng API nào?
2. Nếu mọi SQL chạy thành công nhưng `Connection.close()` thất bại sau `commit()`, có thể khẳng định giao dịch đã rollback không? Vì sao?
3. Vì sao gọi `connection.rollback()` trực tiếp trong `catch` rồi `throw original` có thể làm mất lỗi đầu tiên? Viết cách sửa với `addSuppressed()`.
4. Trong `BatchUpdateException`, `getUpdateCounts()` và `getNextException()` cho biết những thông tin khác nhau gì?
5. Phân biệt `getCause()`, `getSuppressed()` và `SQLException.getNextException()` bằng một sơ đồ exception của chính bạn.
6. DAO tham gia transaction do service sở hữu được đóng những tài nguyên nào, và phải giữ nguyên tài nguyên nào cho service?
7. Tại sao một `SQLWarning` từ `statement.getWarnings()` không tương đương lỗi `statement.close()` bị suppressed?
8. Khi mất kết nối ở thời điểm `commit()`, vì sao retry tạo đơn hàng phải sử dụng cùng idempotency key và kiểm tra kết quả đã lưu?

**Tiêu chí hoàn thành:** người học phân biệt được lỗi nghiệp vụ ban đầu với lỗi rollback/close phát sinh sau đó; biết dùng `try-with-resources` để tự động giữ suppressed exceptions, `addSuppressed()` cho cleanup thủ công, `getCause()` và `getNextException()` để đọc đủ ngữ cảnh; đồng thời có thể thiết kế transaction JDBC và cơ chế log/kiểm thử không làm mất nguyên nhân gốc khi dọn tài nguyên.
