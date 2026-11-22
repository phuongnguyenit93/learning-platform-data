# Thực thi lô và quản lý `clearBatch` trong JDBC

Khi cần ghi hàng nghìn bản ghi vào cơ sở dữ liệu, việc lặp `executeUpdate()` cho từng hàng có thể tạo nhiều lần trao đổi giữa ứng dụng Java và database. **Batch processing** (xử lý theo lô) của JDBC cho phép gom các lệnh cập nhật hoặc các bộ tham số rồi gửi để driver thực thi qua `executeBatch()` hoặc `executeLargeBatch()`.

Tuy nhiên, batch có **hai trạng thái khác nhau cần quản lý**: *danh sách lệnh đang chờ trong `Statement`* và *những thay đổi đã được thực thi trong transaction của database*. `clearBatch()` chỉ xóa danh sách lệnh **chưa gửi**. Nó không thay thế `rollback()` và không hủy câu SQL đã chạy.

Bài học thuộc chương **Xử lý theo lô** của module JDBC. Mục tiêu là thực hiện batch đúng cách bằng `PreparedStatement`, hiểu chính xác thời điểm dùng `clearBatch()`, xử lý `BatchUpdateException` và quản lý commit/rollback, chia lô cùng hiệu năng một cách có kiểm soát.

## 1. Vòng đời của một JDBC batch

Với nhiều lệnh SQL có cùng cấu trúc, ta thường dùng:

1. `connection.prepareStatement(sql)`: chuẩn bị câu SQL có dấu `?`.
2. `ps.setXxx(index, value)`: gán tham số cho một bản ghi.
3. `ps.addBatch()`: thêm **một bộ tham số** vào danh sách batch.
4. Lặp bước 2–3 cho các bản ghi tiếp theo.
5. `ps.executeBatch()`: gửi danh sách tới driver để thực thi; nhận mảng kết quả.
6. `connection.commit()` hoặc `connection.rollback()`: kết thúc transaction theo kết quả của **toàn bộ nghiệp vụ**.

```text
PreparedStatement                         Database
       |                                      |
setXxx(...)                                 |
addBatch()  ---> [bộ tham số #1]             |
setXxx(...)                                 |
addBatch()  ---> [#1, #2]                    |
setXxx(...)                                 |
addBatch()  ---> [#1, #2, #3]                |
       |                                      |
executeBatch() ----------------------------> | chạy các lệnh
       | <------------------------------- int[] updateCounts
       |                                      |
connection.commit() ----------------------> | xác nhận transaction
       |
```

**`addBatch()` không đồng nghĩa với thực thi SQL hoặc commit**. Khi chỉ gọi `addBatch()`, các lệnh đang nằm trong hàng đợi do đối tượng `Statement`/driver quản lý. Dù driver có thể có chiến lược nội bộ để tối ưu, ứng dụng không được mặc định một thao tác `addBatch()` đã được áp dụng vào bảng.

**`executeBatch()` khác `commit()`**: lệnh đầu yêu cầu thực thi batch, còn lệnh thứ hai xác nhận transaction khi `autoCommit=false`. Việc execute thành công chưa chứng minh dữ liệu đã commit.

## 2. `Statement` và `PreparedStatement` khác nhau ở cách thêm lệnh

JDBC hỗ trợ hai hình thức batch thông dụng:

| API | Cách thêm | Phù hợp |
|---|---|---|
| `Statement.addBatch(String sql)` | Thêm một câu SQL hoàn chỉnh vào batch | Một nhóm lệnh cập nhật có SQL cố định, khác cấu trúc |
| `PreparedStatement.addBatch()` | Ghi nhận bộ giá trị tham số hiện tại cho SQL đã prepare | Rất nhiều hàng dùng **cùng cấu trúc SQL** |
| `Statement.executeBatch()` / `PreparedStatement.executeBatch()` | Thực thi những phần tử đang chờ, trả về `int[]` | Cả hai loại statement |
| `Statement.executeLargeBatch()` | Thực thi batch, trả về `long[]` | Khi giá trị đếm số hàng có thể vượt phạm vi `int` và driver hỗ trợ |
| `Statement.clearBatch()` | Loại bỏ các phần tử đang chờ | Muốn bỏ batch chưa thực thi |
| `PreparedStatement.clearParameters()` | Xóa các giá trị tham số hiện được gán | Cần reset **tham số hiện tại**, không phải batch đã gom |

Đối với `PreparedStatement`, viết:

```java
String sql = "INSERT INTO product_tags(product_id, tag) VALUES (?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 1001L);
    ps.setString(2, "java");
    ps.addBatch(); // bộ tham số thứ nhất

    ps.setLong(1, 1002L);
    ps.setString(2, "jdbc");
    ps.addBatch(); // bộ tham số thứ hai

    int[] counts = ps.executeBatch();
}
```

`PreparedStatement` phù hợp hơn khi đầu vào đến từ người dùng vì tham số được truyền qua `setXxx(...)`, tránh tự nối giá trị vào chuỗi SQL. Cách dùng `Statement.addBatch("INSERT ... " + userInput)` vừa dễ tạo lỗi dữ liệu, vừa tạo nguy cơ SQL injection nếu dữ liệu không được xử lý đúng.

Batch thường dành cho các câu SQL trả về **số hàng bị ảnh hưởng**, chẳng hạn `INSERT`, `UPDATE` và `DELETE`. Không thêm `SELECT` trả về `ResultSet` vào batch rồi kỳ vọng lấy một danh sách tập kết quả. Driver có thể từ chối thao tác có kết quả dạng `ResultSet` trong batch.

## 3. `clearBatch()` thực sự xóa gì?

`clearBatch()` là phương thức của `java.sql.Statement`, được `PreparedStatement` thừa hưởng. Nó **xóa các lệnh/bộ tham số đang chờ thực thi trong batch của statement đó**. Nó không gửi câu SQL mới và không thay đổi transaction trên connection.

Ví dụ:

```java
String sql = "UPDATE products SET price = ? WHERE id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, new java.math.BigDecimal("120.00"));
    ps.setLong(2, 10L);
    ps.addBatch();                // Dự định sửa sản phẩm 10

    ps.setBigDecimal(1, new java.math.BigDecimal("150.00"));
    ps.setLong(2, 11L);
    ps.addBatch();                // Dự định sửa sản phẩm 11

    ps.clearBatch();              // Bỏ cả hai mục CHƯA được thực thi

    ps.setBigDecimal(1, new java.math.BigDecimal("175.00"));
    ps.setLong(2, 12L);
    ps.addBatch();                // Chỉ mục mới được đưa vào batch

    int[] counts = ps.executeBatch();
    // Batch này chỉ yêu cầu cập nhật sản phẩm 12.
}
```

Nếu hai mục đầu chưa được `executeBatch()`, `clearBatch()` ngăn chúng bị chạy trong lần execute tiếp theo. **Nó không hủy những thay đổi từ batch đã thực thi trước đó**.

### Phân biệt `clearBatch()`, `clearParameters()` và `rollback()`

| Thao tác | Phạm vi ảnh hưởng | Có hoàn tác SQL đã thực thi? |
|---|---|---|
| `ps.clearBatch()` | Danh sách phần tử **chưa thực thi** của statement | **Không** |
| `ps.clearParameters()` | Các tham số hiện được gán trên `PreparedStatement` | **Không** |
| `connection.rollback()` | Các thay đổi **chưa commit** trong transaction của connection, nếu DB hỗ trợ transaction | **Có**, theo phạm vi transaction |
| `connection.rollback(savepoint)` | Các thay đổi sau savepoint hợp lệ | **Có**, đối với phần transaction sau mốc |
| `connection.commit()` | Xác nhận transaction hiện tại | Không; đây là thao tác chốt thay đổi |

Ví dụ:

```java
ps.setLong(1, 100L);
ps.setString(2, "ACTIVE");
ps.addBatch();

ps.clearParameters();  // Không xóa mục đã addBatch().

ps.setLong(1, 101L);
ps.setString(2, "INACTIVE");
ps.addBatch();

ps.clearBatch();       // Xóa cả hai bộ tham số đã xếp hàng.
```

`clearParameters()` đặc biệt hữu ích khi bộ tham số của statement thay đổi có điều kiện, để tránh vô tình tái dùng một tham số cũ. Nhưng nó không thay thế việc **gán đầy đủ tất cả tham số bắt buộc** cho mỗi phần tử.

### Khi nào nên gọi `clearBatch()`?

- Khi đã gom một số mục nhưng **quyết định hủy batch trước khi execute**, chẳng hạn bước kiểm tra nghiệp vụ phát hiện toàn bộ lô không còn hợp lệ.
- Khi muốn **tạo một batch mới từ đầu trên cùng statement**, bỏ những phần tử đã thêm nhưng chưa chạy.
- Khi code định **tái sử dụng statement sau một tình huống bất thường**, cần loại bỏ dữ liệu batch còn chờ trước khi bắt đầu lượt mới; tuy nhiên phải kiểm soát cả trạng thái transaction và kết quả thực thi trước đó.

**Sau `executeBatch()`, danh sách batch được reset về rỗng theo hợp đồng JDBC.** Vì vậy, trong vòng lặp chia lô thông thường không cần gọi thêm `clearBatch()` sau mỗi lần execute thành công. Cũng không nên coi `clearBatch()` là biện pháp hồi phục transaction sau `BatchUpdateException`: lúc đó có thể đã có lệnh chạy ở DB; phải xử lý rollback và trạng thái connection.

Nếu một batch đã thất bại và kết quả chưa rõ, cách dễ kiểm soát thường là **rollback, đóng statement/connection của lượt đó, rồi bắt đầu một transaction mới** nếu được phép retry, thay vì chỉ `clearBatch()` và chạy lại trên cùng transaction.

## 4. Chuẩn bị ví dụ: ghi nhiều đơn hàng

Dùng bảng quan hệ đơn giản:

```sql
CREATE TABLE order_imports (
    order_id     BIGINT PRIMARY KEY,
    customer_id  BIGINT NOT NULL,
    amount       DECIMAL(18, 2) NOT NULL,
    status       VARCHAR(20) NOT NULL
);
```

Mỗi bản ghi có `order_id` duy nhất; việc ghi trùng khóa sẽ gây lỗi trên DBMS có ràng buộc khóa chính. Trong Java, ta biểu diễn một hàng cần import bằng lớp dữ liệu:

```java
import java.math.BigDecimal;

public final class OrderImport {
    private final long orderId;
    private final long customerId;
    private final BigDecimal amount;

    public OrderImport(long orderId, long customerId, BigDecimal amount) {
        if (amount == null || amount.signum() < 0) {
            throw new IllegalArgumentException("Số tiền không hợp lệ");
        }
        this.orderId = orderId;
        this.customerId = customerId;
        this.amount = amount;
    }

    public long getOrderId() {
        return orderId;
    }

    public long getCustomerId() {
        return customerId;
    }

    public BigDecimal getAmount() {
        return amount;
    }
}
```

Khi import nhiều hàng, ta chọn `PreparedStatement` vì mỗi hàng dùng cùng SQL, chỉ khác dữ liệu tham số.

## 5. Ví dụ hoàn chỉnh: `executeBatch()`, chia lô và transaction

Để tránh giữ hàng chục nghìn bộ tham số trong memory của driver, ví dụ sau **thực thi mỗi 250 hàng** rồi tiếp tục thêm lô kế tiếp. Toàn bộ lượt import vẫn nằm trong **một transaction**: chỉ commit khi tất cả các lô đều thành công.

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;

public final class OrderBatchImporter {
    private static final int CHUNK_SIZE = 250;

    private OrderBatchImporter() {
    }

    public static void importAll(
            DataSource dataSource, List<OrderImport> orders)
            throws SQLException {

        if (dataSource == null || orders == null) {
            throw new IllegalArgumentException("Thiếu dữ liệu import");
        }

        String sql = "INSERT INTO order_imports " +
                "(order_id, customer_id, amount, status) " +
                "VALUES (?, ?, ?, ?)";

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try (PreparedStatement ps = connection.prepareStatement(sql)) {
                int pending = 0;

                for (OrderImport order : orders) {
                    ps.setLong(1, order.getOrderId());
                    ps.setLong(2, order.getCustomerId());
                    ps.setBigDecimal(3, order.getAmount());
                    ps.setString(4, "NEW");
                    ps.addBatch();
                    pending++;

                    if (pending == CHUNK_SIZE) {
                        executeAndCheck(ps, pending);
                        pending = 0;
                    }
                }

                if (pending > 0) {
                    executeAndCheck(ps, pending);
                }

                // CHỈ commit nếu mọi chunk đều hoàn tất hợp lệ.
                connection.commit();

            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }

    private static void executeAndCheck(
            PreparedStatement ps, int expectedCommands)
            throws SQLException {

        int[] counts = ps.executeBatch();
        if (counts.length != expectedCommands) {
            throw new SQLException(
                    "Số lượng kết quả batch không như dự kiến");
        }

        for (int count : counts) {
            if (count == Statement.EXECUTE_FAILED || count == 0) {
                throw new SQLException(
                        "Có lệnh INSERT không ghi được hàng");
            }
            if (count != 1 && count != Statement.SUCCESS_NO_INFO) {
                throw new SQLException(
                        "Số hàng cập nhật bất thường: " + count);
            }
        }
    }
}
```

Gọi từ tầng service:

```java
List<OrderImport> orders = List.of(
        new OrderImport(1001L, 501L,
                new java.math.BigDecimal("125000.00")),
        new OrderImport(1002L, 502L,
                new java.math.BigDecimal("89000.00"))
);

OrderBatchImporter.importAll(dataSource, orders);
```

`List.of(...)` yêu cầu Java 9+. Các lớp `OrderImport` và `OrderBatchImporter` ở trên có thể đặt vào hai file Java tương ứng trong cùng package. `dataSource` là đối tượng đã được ứng dụng cấu hình.

### Các điểm quan trọng của ví dụ

1. **Gán mọi tham số trước từng `addBatch()`.** Với `PreparedStatement`, `addBatch()` ghi lại bộ tham số cho một lần thực thi SQL.
2. **`pending` đếm số phần tử của batch đang chờ.** Sau `executeBatch()` thành công, JDBC reset hàng đợi; biến đếm của ứng dụng phải reset theo.
3. **Phần dư cuối cùng phải được flush.** Nếu danh sách có 620 hàng, ta có hai lô 250 và lô cuối 120. Không gọi `executeBatch()` cho phần dư sẽ bỏ sót 120 hàng.
4. **Không cần `clearBatch()` sau execute thành công.** Nếu gọi `clearBatch()` *trước* `executeBatch()` nhầm chỗ, toàn bộ lệnh đang chờ sẽ bị loại bỏ.
5. **Một transaction bao quanh tất cả chunk.** Dù có nhiều lần `executeBatch()`, chỉ một `commit()` ở cuối. Nếu lô thứ ba lỗi, `rollback()` hủy cả thay đổi lô một và hai, nếu DBMS/storage engine hỗ trợ giao dịch.
6. **Mảng trống không tạo công việc.** Nếu `orders` rỗng, vòng lặp không add/execute batch; transaction không có DML và kết thúc bình thường.

Đoạn kiểm tra yêu cầu mỗi lệnh `INSERT` thông thường ghi đúng một hàng hoặc driver trả `SUCCESS_NO_INFO`. Quy tắc này **gắn với SQL cụ thể**; không nên sao chép nguyên sang `UPDATE` hoặc `INSERT ... ON CONFLICT DO NOTHING`, nơi số hàng cập nhật bằng 0 có thể là kết quả hợp lệ.

### Vì sao không `commit()` ngay sau mỗi chunk?

Commit từng chunk giúp giữ transaction nhỏ hơn, nhưng **thay đổi ngữ nghĩa nghiệp vụ**: nếu chunk thứ tư lỗi, ba chunk đã commit không thể được rollback cùng lượt import. Ví dụ trên chọn *all-or-nothing* cho toàn bộ danh sách.

Nếu yêu cầu nghiệp vụ chấp nhận **thành công từng phần**, có thể commit theo chunk, ghi lại tiến độ và có cơ chế chạy lại/idempotency. Đây phải là quyết định thiết kế rõ ràng, không phải hệ quả tình cờ của việc chia batch.

## 6. Đọc mảng `updateCounts` đúng cách

`executeBatch()` trả về `int[]`. Theo hợp đồng JDBC, các phần tử tương ứng thứ tự các lệnh được thêm vào batch. Giá trị có thể là:

| Giá trị | Nghĩa |
|---|---|
| Số nguyên không âm (như `0`, `1`, `5`) | Số hàng bị ảnh hưởng được báo cho phần tử đó |
| `Statement.SUCCESS_NO_INFO` = `-2` | Lệnh thành công nhưng driver không cung cấp số hàng |
| `Statement.EXECUTE_FAILED` = `-3` | Lệnh thất bại; thường xuất hiện trong `BatchUpdateException.getUpdateCounts()` khi driver tiếp tục sau lỗi |

Vì vậy, không nên cộng mọi phần tử trong mảng để tính tổng số hàng khi chứa `-2` hay `-3`. Và không nên diễn giải `SUCCESS_NO_INFO` là “thành công với -2 hàng”.

Ví dụ hàm tổng hợp chỉ khi **biết chính xác** số hàng:

```java
import java.sql.SQLException;
import java.sql.Statement;

public static long countAffectedRows(int[] counts) throws SQLException {
    long total = 0L;

    for (int count : counts) {
        if (count == Statement.SUCCESS_NO_INFO) {
            throw new SQLException(
                    "Driver không cung cấp số hàng chính xác");
        }
        if (count == Statement.EXECUTE_FAILED || count < 0) {
            throw new SQLException("Có lệnh batch thất bại");
        }
        total += count;
    }

    return total;
}
```

Nếu nghiệp vụ chỉ cần biết **toàn bộ câu SQL thành công**, có thể chấp nhận `SUCCESS_NO_INFO` tùy driver và yêu cầu. Nếu nhất thiết cần chính xác số hàng, phải kiểm tra tính năng driver và/hoặc xác nhận kết quả bằng khóa, mã nghiệp vụ, truy vấn kiểm chứng phù hợp.

### `executeLargeBatch()` khác gì?

`executeLargeBatch()` (JDBC 4.2) trả `long[]`, giúp tránh giới hạn `int` cho số hàng cập nhật rất lớn. Cơ chế batch và nguyên tắc transaction tương tự, và các hằng `SUCCESS_NO_INFO` / `EXECUTE_FAILED` vẫn cần được nhận diện khi giải thích kết quả. Khả năng hỗ trợ và lợi ích thực tế phụ thuộc phiên bản driver/DB.

## 7. Khi `executeBatch()` lỗi: đọc `BatchUpdateException`

Một lô có thể gồm ba lệnh: thêm đơn hàng 1001, 1002 và lại thêm 1001 (vi phạm khóa chính). Tùy driver/DBMS, vài lệnh đầu có thể đã được thực thi trước khi driver phát hiện lỗi. Vì vậy, **batch không mặc nhiên là một transaction atomic**.

JDBC có ngoại lệ chuyên dụng:

```java
import java.sql.BatchUpdateException;
import java.sql.SQLException;
import java.sql.Statement;

public static void logBatchFailure(BatchUpdateException error) {
    int[] counts = error.getUpdateCounts();

    for (int i = 0; i < counts.length; i++) {
        int count = counts[i];
        if (count == Statement.EXECUTE_FAILED) {
            System.err.println("Phần tử " + i + ": thất bại");
        } else if (count == Statement.SUCCESS_NO_INFO) {
            System.err.println("Phần tử " + i +
                    ": thành công, không rõ số hàng");
        } else {
            System.err.println("Phần tử " + i +
                    ": cập nhật " + count + " hàng");
        }
    }

    for (SQLException next = error; next != null;
         next = next.getNextException()) {
        System.err.println("SQLState=" + next.getSQLState() +
                ", vendorCode=" + next.getErrorCode() +
                ", message=" + next.getMessage());
    }
}
```

Driver có thể chọn một trong hai cách hành xử khi một phần tử batch gặp lỗi:

- **Dừng ở phần tử lỗi:** mảng trong `BatchUpdateException` có thể chỉ chứa kết quả các lệnh đã xử lý trước lỗi.
- **Tiếp tục sau lỗi:** mảng có thể chứa kết quả tương ứng tất cả phần tử, đánh dấu phần tử thất bại bằng `Statement.EXECUTE_FAILED`.

Dù có `updateCounts`, kết quả này phản ánh tiến độ thực thi/khả năng cập nhật chứ **không khẳng định transaction đã commit**. Trên PostgreSQL chẳng hạn, một lỗi SQL trong transaction có thể đưa transaction vào trạng thái lỗi, yêu cầu rollback trước khi tiếp tục.

Nếu yêu cầu là *all-or-nothing*, hướng xử lý phổ biến là:

1. Bắt `BatchUpdateException` (một loại `SQLException`) và ghi nhận SQLState, mã lỗi, các `updateCounts` để chẩn đoán.
2. **Rollback toàn bộ transaction**; giữ nguyên lỗi gốc nếu rollback cũng lỗi.
3. Đóng/từ bỏ statement/connection hiện tại theo quy tắc của pool.
4. Chỉ retry **toàn bộ nghiệp vụ** khi đã xác định lỗi có thể retry, transaction trước chưa commit và nghiệp vụ an toàn khi chạy lại.

Ví dụ sử dụng trong khối `catch`:

```java
catch (BatchUpdateException batchFailure) {
    logBatchFailure(batchFailure);

    try {
        connection.rollback();
    } catch (SQLException rollbackFailure) {
        batchFailure.addSuppressed(rollbackFailure);
    }

    throw batchFailure;
}
```

Đây là nhánh `catch` minh họa, phải được đặt bên trong phương thức có `connection` và khối `try` tương ứng. Trong mã hoàn chỉnh của phần 5, `catch (SQLException | RuntimeException)` đã thực hiện rollback cho cả `BatchUpdateException`; không cần thêm một rollback lần hai.

**`clearBatch()` sau lỗi không đủ để dọn dữ liệu**: nó chỉ xử lý hàng đợi chưa chạy, không đưa các hàng đã INSERT/UPDATE về trạng thái trước giao dịch. `rollback()` mới có vai trò hoàn tác những thay đổi chưa commit của transaction.

## 8. Minh họa rõ ràng: `clearBatch()` trước hay sau `executeBatch()`

Giả sử bảng `products(id, price)` đã có dữ liệu.

**Tình huống A — quyết định bỏ lô trước khi gửi:**

```java
try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE products SET price = ? WHERE id = ?")) {

    ps.setBigDecimal(1, new java.math.BigDecimal("100.00"));
    ps.setLong(2, 1L);
    ps.addBatch();

    ps.setBigDecimal(1, new java.math.BigDecimal("200.00"));
    ps.setLong(2, 2L);
    ps.addBatch();

    // Bỏ cả hai lệnh chưa thực thi.
    ps.clearBatch();

    // Không có UPDATE nào từ hai mục đã bị bỏ.
}
```

**Tình huống B — đã chạy lô và cần hoàn tác:**

```java
connection.setAutoCommit(false);

try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE products SET price = price + ? WHERE id = ?")) {

    ps.setBigDecimal(1, new java.math.BigDecimal("10.00"));
    ps.setLong(2, 1L);
    ps.addBatch();

    ps.executeBatch();    // SQL đã được yêu cầu thực thi.

    ps.clearBatch();      // Không undo giá mới của sản phẩm 1.
    connection.rollback(); // Hoàn tác thay đổi chưa commit.
}
```

Đoạn B minh họa thao tác thành công trên DB hỗ trợ transaction. Trong code sản xuất, phải có `try/catch/finally` hoặc `try-with-resources` bao quanh transaction để rollback khi bất kỳ bước nào thất bại; không sao chép đoạn ngắn như một mẫu xử lý lỗi hoàn chỉnh.

**Tình huống C — clear batch để xây lại danh sách trước khi execute:**

```java
ps.addBatch();   // Mục 1 đã được thiết lập tham số.
ps.addBatch();   // Mục 2 đã được thiết lập tham số.

if (!isImportStillAllowed()) {
    ps.clearBatch();
    // Có thể chọn không chạy SQL hoặc xếp một batch khác.
}
```

Đoạn C là mã giả để giải thích quyết định trước khi execute; khi dùng `PreparedStatement` thực tế, hãy gán tham số phù hợp trước mỗi `addBatch()`. Phương thức `isImportStillAllowed()` là kiểm tra nghiệp vụ do ứng dụng cung cấp.

Nếu đã gọi `executeBatch()` thành công, danh sách cũ đã được reset. Thêm batch mới bằng `addBatch()` sẽ tạo nhóm phần tử mới; `clearBatch()` lúc này chỉ tác động đến **nhóm mới chưa thực thi**.

## 9. Phân chia batch tối ưu mà không làm sai transaction

Batch quá nhỏ gây nhiều lần trao đổi với DB; batch quá lớn tăng bộ nhớ, độ dài câu SQL nội bộ, thời gian giữ khóa và chi phí xử lý lỗi. Chọn kích thước là **bài toán đo đạc**, không có một con số luôn đúng.

Một số biến số cần đánh giá:

- **Đặc tính driver:** một số driver có cấu hình *rewrite batched statements* hoặc tối ưu `INSERT` nhiều giá trị; một số driver gửi lần lượt các lệnh. Không mặc định tất cả driver đóng gói mọi batch thành một lần đi mạng.
- **Giới hạn DBMS:** giới hạn số tham số/lệnh, kích thước packet, kích thước SQL, statement timeout hoặc độ lớn transaction có thể khác nhau.
- **Kích thước bản ghi:** hàng chứa JSON/văn bản lớn có chi phí khác hàng chỉ vài số nguyên.
- **Index, trigger, FK:** batch insert có thể vẫn phải duy trì index, chạy trigger và kiểm tra ràng buộc cho từng hàng.
- **Transaction:** nhiều lần `executeBatch()` trong một transaction giúp all-or-nothing, nhưng transaction lớn có thể giữ khóa, tăng WAL/redo log và ảnh hưởng tài nguyên.
- **Kiểu phản hồi:** muốn biết chính xác hàng nào lỗi đòi hỏi chẩn đoán bổ sung; batch lớn có thể làm việc khôi phục phức tạp hơn.

Có thể bắt đầu thử nghiệm với 100, 250 hoặc 500 phần tử mỗi chunk và đo throughput, p95 latency, số lượt network, mức dùng memory, thời gian lock và tỷ lệ lỗi trên hệ thống thật. Đây chỉ là **giá trị khởi điểm để benchmark**, không phải chuẩn JDBC.

**Nhớ phân biệt “chunk” và “transaction”:**

```text
Một transaction toàn bộ import
  chunk 1: addBatch * 250 -> executeBatch()
  chunk 2: addBatch * 250 -> executeBatch()
  chunk 3: addBatch * 120 -> executeBatch()
  -------------------------------------------------
  commit() một lần khi cả 620 hàng thành công

Nếu chunk 3 lỗi: rollback() -> các thay đổi chưa commit
của chunk 1, 2, 3 đều bị hủy.
```

Nếu cần xử lý hàng triệu bản ghi và không thể giữ một transaction rất dài, hãy cân nhắc thiết kế import **từng chunk có checkpoint**. Khi ấy, phải mô tả rõ trạng thái thành công từng phần, mã nhận diện lô, cơ chế chạy tiếp và idempotency; không còn bảo đảm atomicity cho toàn bộ tệp import.

## 10. Sai lầm thường gặp khi dùng `clearBatch` và thực thi lô

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Gọi `clearBatch()` ngay trước `executeBatch()` vì nghĩ là “dọn bộ nhớ” | Xóa chính những phần tử chuẩn bị gửi | Chỉ clear khi thực sự muốn **bỏ** những phần tử chưa chạy |
| Nghĩ `clearBatch()` hoàn tác SQL đã execute | Dữ liệu đã thay đổi trong DB và có thể commit | Dùng `rollback()` nếu thay đổi thuộc transaction chưa commit |
| Nhầm `clearParameters()` với `clearBatch()` | Batch cũ vẫn tồn tại hoặc tham số mới bị thiếu | Chọn API theo trạng thái cần xóa |
| Bỏ quên flush phần dư | Những hàng chưa đủ chunk cuối không được thực thi | Nếu `pending > 0`, gọi `executeBatch()` |
| Không đặt `autoCommit(false)` khi cần all-or-nothing | Batch có thể thành công một phần rồi commit | Quản lý transaction ngoài toàn bộ batch |
| Giả định mảng updateCounts luôn toàn số dương | Đọc sai `SUCCESS_NO_INFO` và `EXECUTE_FAILED` | Kiểm tra hai hằng JDBC và diễn giải đúng |
| Khi batch lỗi, chỉ chạy lại lệnh thất bại | Dữ liệu có thể bị xử lý trùng hoặc không nhất quán | Rollback và đánh giá retry toàn nghiệp vụ |
| Commit sau từng chunk khi yêu cầu toàn bộ import phải thành công | Phần đầu đã commit không thể rollback | Một transaction bao quanh các chunk |
| Không đóng statement/connection | Rò rỉ tài nguyên, khóa giữ lâu | `try-with-resources` và transaction kết thúc rõ ràng |
| Batch `SELECT` cần tập kết quả | Driver có thể từ chối vì batch trả `ResultSet` | Dùng executeQuery theo cách riêng, không gộp SELECT trong DML batch |
| Xem `addBatch()` là đã lưu dữ liệu | Trả thành công trước khi SQL chạy | Chờ `executeBatch()`, kiểm tra kết quả, rồi commit |
| Dựa vào danh sách batch sau lỗi như trạng thái DB | Không biết lệnh nào đã chạy hoặc đã commit | Dùng `BatchUpdateException` để chẩn đoán và transaction để quyết định |

## 11. Ghi nhận khóa tự sinh và retry: những điểm nâng cao

### 11.1. Generated keys

Nếu bảng dùng khóa tự tăng, JDBC có `Statement.RETURN_GENERATED_KEYS` và `getGeneratedKeys()`. Khả năng trả đúng tất cả khóa khi batch, thứ tự và độ đầy đủ **phụ thuộc driver/DBMS**, đặc biệt khi bật chế độ rewrite. Vì vậy, trước khi thiết kế map ID theo thứ tự phần tử batch, hãy kiểm tra hành vi trên chính phiên bản driver đang dùng.

Một lựa chọn khác là ứng dụng sinh mã định danh ổn định hoặc lấy ID qua cơ chế DB được xác minh, nhưng phải tuân thủ yêu cầu kiến trúc và chống trùng.

### 11.2. Retry khi có lỗi

Trong các tình huống như deadlock hoặc serialization failure, đôi khi có thể thử lại toàn bộ transaction **sau khi xác nhận transaction cũ đã bị hủy** và dữ liệu nghiệp vụ có thể thực hiện lại. Không retry mù khi commit báo lỗi mạng vì lần trước **có thể đã commit**. Với import lớn, một `import_id` duy nhất và cơ chế kiểm tra kết quả giúp tránh insert lặp.

### 11.3. Câu SQL khác nhau trong một batch

`Statement.addBatch(String sql)` cho phép thêm các câu lệnh cập nhật khác nhau, nhưng việc trộn nhiều kiểu SQL trong một batch có thể làm giảm lợi ích tối ưu và khó hiểu kết quả. Với các thao tác khác cấu trúc nhưng thuộc cùng nghiệp vụ, có thể dùng **nhiều `PreparedStatement`, mỗi statement có batch riêng**, và đặt tất cả trong một `Connection`/transaction khi thích hợp. Không nhầm batch với transaction: một transaction có thể chứa nhiều statement/batch.

## 12. Kiểm thử trên driver và database thực tế

Một bài thực hành nên kiểm chứng cả **hàng đợi batch** và **trạng thái transaction**.

1. **Thực thi thành công:** thêm 3 bộ tham số rồi `executeBatch()`. Kiểm tra mảng updateCounts và số hàng sau `commit()`.
2. **`clearBatch()` trước execute:** thêm 3 mục, gọi `clearBatch()`, thêm 1 mục mới và execute. Chỉ mục mới được chạy.
3. **`clearParameters()`:** thêm bộ tham số thứ nhất vào batch, gọi `clearParameters()`, gán lại bộ mới rồi add. Cả hai mục đã add vẫn nằm trong hàng đợi.
4. **Nhiều chunk:** import 620 hàng với chunk 250. Xác nhận 620 hàng được commit, không bỏ phần dư.
5. **Lỗi ở chunk cuối:** tạo khóa trùng ở hàng 600 và chọn một transaction toàn bộ import. Kiểm tra sau rollback không còn các hàng của các chunk trước đó.
6. **Đếm số hàng:** dùng driver có thể trả `SUCCESS_NO_INFO`; logic kiểm tra không được hiểu `-2` là lỗi hoặc số hàng âm.
7. **Batch update một số hàng bằng 0:** thử `UPDATE` với ID không tồn tại để chứng minh 0 hàng có thể là kết quả hợp lệ tùy nghiệp vụ.
8. **Rollback thất bại:** giả lập `SQLException` khi rollback; đảm bảo giữ ngoại lệ gốc cùng lỗi rollback đính kèm.
9. **Auto-commit và partial success:** trong môi trường thử nghiệm riêng, đối chiếu kết quả khi `autoCommit=true` với `false`. Không giả định driver sẽ rollback toàn bộ batch trong chế độ auto-commit.
10. **Hiệu năng:** chạy cùng dữ liệu ở các kích thước chunk, đo thời gian end-to-end và kiểm tra độ chính xác/đồng nhất dữ liệu, tránh tối ưu chỉ theo số câu gọi API.

Nên ghi lại **DBMS**, **phiên bản JDBC driver**, **cấu hình batch/rewrite**, **autoCommit**, **kích thước chunk**, **SQL cụ thể** và **kết quả truy vấn sau commit/rollback** để đối chiếu. Một test chỉ kiểm tra `executeBatch()` không ném lỗi chưa đủ để chứng minh dữ liệu nghiệp vụ đúng.

## 13. Checklist trước khi dùng batch trong sản xuất

- Đã phân biệt rõ `addBatch()`, `executeBatch()`, `clearBatch()`, `clearParameters()` và `rollback()` chưa?
- Đã chọn `PreparedStatement` có tham số khi nhiều hàng cùng cấu trúc SQL chưa?
- Đã xác định **một batch là một phần của transaction** hay toàn bộ import là một transaction chưa?
- Có execute phần dư cuối cùng và đặt kích thước chunk hợp lý không?
- Có kiểm tra `updateCounts` và `BatchUpdateException` với `SUCCESS_NO_INFO`/`EXECUTE_FAILED` không?
- Khi lỗi có rollback các thay đổi chưa commit và đóng tài nguyên đúng cách không?
- Nếu cần retry, có đảm bảo lần trước chưa commit và chống xử lý trùng không?
- Đã đo throughput/latency và xác nhận hành vi trên driver, DBMS thật chưa?

## Ghi nhớ

- **`addBatch()`** xếp lệnh hoặc bộ tham số vào hàng đợi của statement.
- **`executeBatch()`** yêu cầu thực thi hàng đợi và trả mảng số hàng; sau khi gọi, danh sách batch được reset theo hợp đồng JDBC.
- **`clearBatch()`** loại bỏ các mục **chưa thực thi**; nó không hoàn tác dữ liệu đã ghi.
- **`clearParameters()`** chỉ xóa tham số đang gán, không phải các bộ tham số đã thêm vào batch.
- **`rollback()`** hoàn tác các thay đổi **chưa commit** trong transaction trên connection.
- **`BatchUpdateException`** có thể cho biết phần nào đã được driver xử lý; quyết định all-or-nothing vẫn cần transaction rõ ràng.
- **Chia chunk là tối ưu bộ nhớ/hiệu năng; chia transaction là thay đổi tính nguyên tử nghiệp vụ.**

Hiểu rõ thời điểm thực thi và vai trò của `clearBatch()` giúp ứng dụng JDBC nhập dữ liệu hàng loạt hiệu quả, tránh bỏ sót lệnh và không nhầm việc xóa hàng đợi với việc hoàn tác transaction.
