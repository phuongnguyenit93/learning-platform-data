# Phối hợp batch với commit và rollback trong JDBC

Trong chương **Xử lý theo lô**, JDBC cho phép ứng dụng Java gửi nhiều thao tác SQL qua một `PreparedStatement` thay vì thực thi từng lệnh riêng biệt. Batch có thể giảm số lần trao đổi với cơ sở dữ liệu, nhưng **`executeBatch()` không đồng nghĩa `commit()`**. Nếu một lệnh trong batch thất bại, dữ liệu có bị lưu một phần hay toàn bộ có thể được hoàn tác sẽ phụ thuộc vào **ranh giới transaction**, cấu hình `autoCommit` và hành vi của DBMS/driver.

Bài này trình bày cách phối hợp `addBatch()`, `executeBatch()`, `commit()` và `rollback()` để thực hiện CRUD theo lô an toàn bằng API JDBC chuẩn, cách xử lý `BatchUpdateException` và cách chọn giữa một transaction bao trùm nhiều batch với commit riêng từng chunk.

## 1. Batch và transaction thực hiện hai nhiệm vụ khác nhau

Một **batch** là tập các câu SQL mà driver nhận và xử lý cùng một đợt. Một **transaction** là đơn vị công việc được DBMS xác nhận hoặc hủy theo ranh giới commit/rollback.

| API JDBC | Tác dụng | Điều cần nhớ |
| --- | --- | --- |
| `PreparedStatement.addBatch()` | Thêm bộ tham số hiện tại vào danh sách chờ | Chưa có nghĩa SQL đã được chạy |
| `PreparedStatement.executeBatch()` | Thực thi danh sách lệnh và trả về `int[]` update counts | Không tự xác lập tính nguyên tử cho *toàn bộ nghiệp vụ* |
| `PreparedStatement.clearBatch()` | Xóa các lệnh còn chờ trong danh sách của statement | **Không hoàn tác** lệnh đã chạy trong DB |
| `Connection.setAutoCommit(false)` | Để ứng dụng quyết định ranh giới transaction | Phải gọi `commit()` hoặc `rollback()` để kết thúc |
| `Connection.commit()` | Xác nhận các thay đổi chưa commit của transaction hiện tại | Không thể tự kiểm tra mọi quy tắc nghiệp vụ |
| `Connection.rollback()` | Hủy thay đổi chưa commit trong transaction hiện tại, nếu DBMS hỗ trợ | Không hủy những transaction đã commit trước |

Mẫu batch cơ bản:

~~~java
String sql = "INSERT INTO audit_events (id, message) VALUES (?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 101L);
    ps.setString(2, "created");
    ps.addBatch();

    ps.setLong(1, 102L);
    ps.setString(2, "updated");
    ps.addBatch();

    int[] counts = ps.executeBatch();
    // Batch đã được gửi đi. Transaction có commit hay chưa
    // phụ thuộc vào autoCommit và thao tác commit() của ứng dụng.
}
~~~

Với `PreparedStatement`, mỗi lần `addBatch()` lưu bộ tham số của lần thực thi đó. Phương thức `executeBatch()` thường làm rỗng danh sách lệnh chờ sau khi thực thi theo hợp đồng JDBC; nếu cần hủy dữ liệu đã chạy thì phải dùng transaction, không dùng `clearBatch()`.

Driver có thể gộp hoặc viết lại các lệnh batch để tối ưu. Vì vậy, đừng suy luận rằng “một lần gọi API” sẽ luôn tương ứng với “một SQL vật lý” hoặc “một transaction” ở phía DBMS.

## 2. `autoCommit` làm thay đổi kết quả khi batch lỗi

### 2.1. Khi `autoCommit = true`

Kết nối JDBC mới thông thường mặc định bật auto-commit, dù `DataSource` hoặc connection pool có thể điều chỉnh cấu hình. Với auto-commit bật, các câu SQL được xác nhận tự động khi hoàn tất theo quy tắc JDBC.

Ví dụ gửi 100 dòng bằng batch, đến một lệnh giữa batch gặp vi phạm `UNIQUE`. **Có thể đã có những câu lệnh trước đó được commit**. Driver và DBMS khác nhau có thể dùng các cách thực thi batch khác nhau; không được dựa vào auto-commit để bảo đảm “100 dòng cùng được ghi hoặc cùng bị hủy”.

`rollback()` không thể hoàn tác phần đã commit. Hơn nữa, gọi `rollback()` khi auto-commit đang bật không phải cách dùng hợp lệ theo API JDBC.

### 2.2. Khi `autoCommit = false`

Ứng dụng kiểm soát transaction:

~~~java
connection.setAutoCommit(false);
try {
    int[] counts = statement.executeBatch();
    // Kiểm tra counts và các bước nghiệp vụ khác.
    connection.commit();
} catch (SQLException error) {
    connection.rollback();
    throw error;
}
~~~

Trong ví dụ, batch có thể đã thực thi thành công nhưng các thay đổi **chưa commit**. Nếu một bước sau thất bại, `rollback()` có thể hủy các thay đổi chưa commit của toàn transaction. Điều này phụ thuộc bảng/engine có hỗ trợ transaction; một số DDL và hệ quản trị có quy tắc implicit commit.

Đoạn trên là mô hình ngắn để nắm ý chính. Mã thực tế còn phải quản lý connection, xử lý lỗi rollback, kết quả commit chưa chắc chắn và khôi phục trạng thái pool.

| Nhu cầu | Chính sách phù hợp |
| --- | --- |
| Một batch phải thành công toàn bộ | `setAutoCommit(false)`, kiểm tra, `commit()` hoặc `rollback()` |
| Nhiều batch cùng thuộc một đơn hàng | Một transaction bao trùm mọi batch và các lệnh SQL liên quan |
| Import cực lớn, chấp nhận một phần đã lưu | Commit theo chunk, lưu checkpoint, thiết kế idempotency |
| Một nhóm phụ không bắt buộc có thể lỗi | Cân nhắc `Savepoint` khi DBMS hỗ trợ và nghiệp vụ cho phép |

## 3. Ví dụ nghiệp vụ: tạo dòng đơn hàng rồi chuyển trạng thái

Giả sử có đơn hàng `id = 700` ở trạng thái `DRAFT`. Quy trình gồm hai bước bắt buộc:

1. Thêm toàn bộ dòng sản phẩm vào `order_lines` bằng JDBC batch.
2. Chuyển `orders.status` từ `DRAFT` sang `READY` khi tất cả dòng đã được thêm.

Nếu một dòng chi tiết bị lỗi hoặc đơn hàng không còn ở trạng thái `DRAFT`, cần **rollback cả quy trình**. Nếu chỉ commit các dòng nhưng không đổi trạng thái, dữ liệu có thể không nhất quán.

Lược đồ minh họa, với DBMS hỗ trợ transaction:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE order_lines (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    FOREIGN KEY (order_id) REFERENCES orders(id)
);
~~~

Lệnh batch dùng các placeholder được tham số hóa:

~~~sql
INSERT INTO order_lines (id, order_id, product_id, quantity)
VALUES (?, ?, ?, ?);
~~~

Lệnh xác nhận trạng thái:

~~~sql
UPDATE orders
SET status = ?
WHERE id = ? AND status = ?;
~~~

Nếu câu `UPDATE` tác động `0` hàng, ứng dụng coi là **lỗi nghiệp vụ** vì trạng thái không còn phù hợp hoặc đơn hàng không tồn tại, dù SQL không ném `SQLException`.

~~~mermaid
flowchart TD
    A["Lấy Connection và tắt autoCommit"] --> B["addBatch các dòng đơn hàng"]
    B --> C["executeBatch một hoặc nhiều lần"]
    C --> D{"Kết quả batch hợp lệ?"}
    D -- "Không" --> R["rollback toàn transaction"]
    D -- "Có" --> E["UPDATE đơn hàng thành READY"]
    E --> F{"Đúng một hàng thay đổi?"}
    F -- "Không" --> R
    F -- "Có" --> G["commit toàn transaction"]
    R --> H["Không giữ dữ liệu chưa commit"]
    G --> I["Lưu cả chi tiết và trạng thái"]
~~~

**Ranh giới nghiệp vụ là một đơn hàng**, dù xử lý hàng nghìn dòng và thực thi nhiều batch.

## 4. Đọc update counts đúng cách

Sau khi một batch thành công, `executeBatch()` trả về `int[]` tương ứng với các lệnh đã thực thi:

| Giá trị | Ý nghĩa |
| --- | --- |
| `0` hoặc số nguyên không âm | Số hàng bị tác động, nếu driver trả số lượng chính xác |
| `Statement.SUCCESS_NO_INFO`, tức `-2` | Lệnh thành công nhưng không có thông tin chính xác về số hàng |
| `Statement.EXECUTE_FAILED`, tức `-3` | Lệnh thất bại khi driver tiếp tục xử lý sau một lỗi |

Khi một lệnh bị lỗi, JDBC có thể ném `BatchUpdateException`, là lớp con của `SQLException`. Theo hợp đồng JDBC, driver có thể **dừng ngay khi gặp lỗi** hoặc **tiếp tục thử các lệnh còn lại**:

~~~text
Batch 5 câu, câu thứ ba lỗi:

Driver dừng ở câu 3:
  getUpdateCounts() = [1, 1]

Driver tiếp tục xử lý:
  getUpdateCounts() = [1, 1, EXECUTE_FAILED, 1, 1]
~~~

Các mảng trên là ví dụ, không phải cam kết cho mọi driver. Đặc biệt, giá trị `1` **không chứng minh transaction đã commit**; nó chỉ mô tả kết quả thực thi đã biết.

Có thể ghi log thông tin kỹ thuật:

~~~java
import java.sql.BatchUpdateException;
import java.sql.SQLException;
import java.sql.Statement;

static void inspectBatchError(BatchUpdateException error) {
    int[] counts = error.getUpdateCounts();

    for (int i = 0; i < counts.length; i++) {
        int count = counts[i];
        String result =
            count == Statement.EXECUTE_FAILED ? "FAILED" :
            count == Statement.SUCCESS_NO_INFO ? "SUCCESS_NO_INFO" :
            "updatedRows=" + count;
        System.err.println("Batch item " + i + ": " + result);
    }

    for (SQLException item = error;
         item != null;
         item = item.getNextException()) {
        System.err.printf(
            "SQLState=%s, vendorCode=%d%n",
            item.getSQLState(), item.getErrorCode()
        );
    }
}
~~~

Không ghi trực tiếp tham số chứa dữ liệu nhạy cảm vào log. Dùng `SQLState` và vendor code để chẩn đoán; không tự suy ra từ update counts rằng đã thành công toàn bộ.

Nếu batch có thể cập nhật số hàng vượt giới hạn `int`, JDBC còn có `executeLargeBatch()` và `BatchUpdateException.getLargeUpdateCounts()`. Với trường hợp phổ biến, `executeBatch()` và `int[]` đủ dùng.

**Định nghĩa thành công thuộc về nghiệp vụ.** Ví dụ một batch `UPDATE WHERE id = ?` bắt buộc sửa đúng một bản ghi thì count `0` là lỗi, dù JDBC không ném ngoại lệ. Nếu driver chỉ trả `SUCCESS_NO_INFO`, bạn không có bằng chứng về số hàng cụ thể; cần kiểm tra hậu điều kiện bổ sung nếu nghiệp vụ đòi hỏi.

## 5. Mẫu Java hoàn chỉnh: nhiều batch, một transaction

Ví dụ sau dùng Java 17+, `DataSource` và `PreparedStatement`. Để giới hạn số bộ tham số giữ trong bộ nhớ, chương trình gọi `executeBatch()` sau mỗi 250 dòng. **Toàn bộ các batch và câu `UPDATE orders` vẫn thuộc một transaction**, chỉ commit khi tất cả bước thành công.

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;
import java.util.Objects;

public final class OrderBatchService {
    private static final int BATCH_SIZE = 250;
    private final DataSource dataSource;

    public OrderBatchService(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public record LineInput(long id, long productId, int quantity) {}

    public void insertLinesAndFinalize(
            long orderId, List<LineInput> lines
    ) throws SQLException {
        if (orderId <= 0 || lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException(
                "Đơn hàng hoặc danh sách dòng không hợp lệ"
            );
        }
        for (LineInput line : lines) {
            if (line == null || line.id() <= 0 ||
                    line.productId() <= 0 || line.quantity() <= 0) {
                throw new IllegalArgumentException("Dòng không hợp lệ");
            }
        }

        try (Connection conn = dataSource.getConnection()) {
            boolean originalAutoCommit = conn.getAutoCommit();
            conn.setAutoCommit(false);

            boolean transactionEnded = false;
            Throwable originalFailure = null;

            try {
                String insertSql = """
                    INSERT INTO order_lines
                        (id, order_id, product_id, quantity)
                    VALUES (?, ?, ?, ?)
                    """;

                try (PreparedStatement insert =
                         conn.prepareStatement(insertSql)) {
                    int pending = 0;

                    for (LineInput line : lines) {
                        insert.setLong(1, line.id());
                        insert.setLong(2, orderId);
                        insert.setLong(3, line.productId());
                        insert.setInt(4, line.quantity());
                        insert.addBatch();

                        if (++pending == BATCH_SIZE) {
                            int[] counts = insert.executeBatch();
                            validateCounts(counts, pending);
                            pending = 0;
                        }
                    }

                    if (pending > 0) {
                        int[] counts = insert.executeBatch();
                        validateCounts(counts, pending);
                    }
                }

                String updateSql = """
                    UPDATE orders SET status = ?
                    WHERE id = ? AND status = ?
                    """;

                try (PreparedStatement update =
                         conn.prepareStatement(updateSql)) {
                    update.setString(1, "READY");
                    update.setLong(2, orderId);
                    update.setString(3, "DRAFT");

                    if (update.executeUpdate() != 1) {
                        throw new SQLException(
                            "Đơn hàng không còn ở trạng thái DRAFT"
                        );
                    }
                }

                conn.commit();
                transactionEnded = true;

            } catch (SQLException | RuntimeException error) {
                originalFailure = error;
                try {
                    conn.rollback();
                    transactionEnded = true;
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;

            } finally {
                // Chỉ đổi autoCommit khi commit/rollback đã kết thúc.
                if (transactionEnded) {
                    try {
                        conn.setAutoCommit(originalAutoCommit);
                    } catch (SQLException restoreError) {
                        if (originalFailure != null) {
                            originalFailure.addSuppressed(restoreError);
                        } else {
                            // Lỗi khôi phục sau commit không có nghĩa
                            // toàn bộ công việc chưa được lưu.
                            throw restoreError;
                        }
                    }
                }
            }
        }
    }

    private static void validateCounts(
            int[] counts, int expected
    ) throws SQLException {
        if (counts.length != expected) {
            throw new SQLException("Số kết quả batch bất thường");
        }

        for (int count : counts) {
            if (count == Statement.SUCCESS_NO_INFO) {
                // Driver xác nhận thành công nhưng không báo số hàng.
                continue;
            }
            if (count != 1) {
                // Ví dụ yêu cầu mỗi INSERT thêm đúng một hàng.
                throw new SQLException(
                    "Kết quả INSERT không đúng mong đợi: " + count
                );
            }
        }
    }
}
~~~

Các điểm cần chú ý:

1. **Cùng connection:** tầng service nhận một `Connection` và mọi `PreparedStatement` trong quy trình dùng nó. DAO nhận connection từ service không tự `commit()` hoặc đóng connection đó.
2. **Batch size khác transaction size:** 600 dòng với batch size 250 sẽ chạy ba lần `executeBatch()` (250, 250, 100), sau đó mới `commit()` một lần.
3. **Bắt cả lỗi SQL và lỗi Java:** một ngoại lệ runtime trước commit cũng khiến transaction cần rollback.
4. **Kiểm tra kết quả:** count `0` hoặc `EXECUTE_FAILED` không thỏa yêu cầu, nên ném lỗi để rollback. `SUCCESS_NO_INFO` được xem là thành công nhưng không đủ để xác nhận số hàng chính xác.
5. **Rollback rồi mới khôi phục auto-commit:** nếu rollback cũng lỗi, không chuyển về `true` để tránh vô tình commit phần transaction còn tồn tại.
6. **`try-with-resources`:** đóng statement và trả/đóng connection đúng lúc; việc đóng không thay thế `rollback()` tường minh.

Mã giả định `DataSource` cung cấp kết nối riêng cho đơn vị nghiệp vụ, bảng có hỗ trợ transaction và dịch vụ có quyền quản lý transaction. Trong ứng dụng thực tế cần bổ sung giới hạn tài nguyên, timeout, khả năng tương thích driver, kiểm tra idempotency và chính sách khôi phục connection lỗi.

### Nếu một batch sau cùng thất bại?

Giả sử có 600 dòng:

~~~text
Chunk 1: 250 INSERT → executeBatch thành công → chưa commit
Chunk 2: 250 INSERT → executeBatch thành công → chưa commit
Chunk 3: 100 INSERT → một lệnh vi phạm UNIQUE
          → BatchUpdateException
          → rollback toàn transaction

Kết quả: không giữ lại dữ liệu chưa commit của cả 600 dòng.
~~~

Nếu chunk 3 thành công nhưng lệnh `UPDATE orders` trả `0`, kết quả cũng phải rollback vì nghiệp vụ yêu cầu đơn hàng phải chuyển sang `READY` cùng với dữ liệu chi tiết.

**Cần phân biệt:** việc `executeBatch()` trả thành công không tự xác nhận transaction; một lỗi ở bước nghiệp vụ tiếp theo vẫn có thể khiến mọi thay đổi từ batch bị rollback.

## 6. Nên làm gì khi `BatchUpdateException` xảy ra?

Với yêu cầu **tất cả hoặc không có gì**, dừng xử lý, ghi nhận lỗi và yêu cầu tầng sở hữu transaction rollback.

~~~java
try {
    int[] counts = insert.executeBatch();
    validateCounts(counts, expectedCount);
} catch (java.sql.BatchUpdateException error) {
    inspectBatchError(error);
    throw error; // Caller rollback cả transaction.
}
~~~

Không nên lọc các kết quả `1` rồi tiếp tục commit, vì chính sách nguyên tử bị phá vỡ. Ngoài ra, một số DBMS có thể đánh dấu transaction là *aborted* sau một lỗi SQL, khiến câu lệnh kế tiếp bị từ chối. Chỉ tiếp tục khi có chiến lược phục hồi rõ ràng cho DBMS cụ thể.

### Khi nghiệp vụ cho phép bỏ qua một phần

Không phải mọi batch đều yêu cầu tất cả thành công. Với công việc độc lập, có thể:

- Kiểm tra dữ liệu và loại bỏ bản ghi trùng trước khi gửi.
- Chia nhóm thành các transaction độc lập; lưu trạng thái thành công/thất bại theo nhóm.
- Sử dụng SQL có ngữ nghĩa bỏ qua trùng hoặc upsert theo DBMS, nếu đó là hợp đồng mong muốn.
- Tạo `Savepoint` trước một phần **tùy chọn**, rollback phần đó nếu lỗi được phép bỏ qua, rồi mới tiếp tục transaction lớn.

**Không nên nuốt mọi lỗi unique:** chỉ bỏ qua loại xung đột được nghiệp vụ xác định chính xác. Với lỗi deadlock hoặc serialization, thường phải kết thúc transaction cũ và retry cả đơn vị nghiệp vụ trong transaction mới.

## 7. Hai chiến lược commit khi dữ liệu rất lớn

### A. Một transaction cho nhiều chunk

~~~text
setAutoCommit(false)
  executeBatch(chunk 1)
  executeBatch(chunk 2)
  ...
  executeBatch(chunk 20)
commit()
~~~

Nếu chunk 20 lỗi, ứng dụng rollback toàn bộ 20 chunk chưa commit. Phù hợp khi **cả tập nhập phải nguyên tử**, chẳng hạn một đơn hàng không được có thiếu dòng chi tiết.

Đánh đổi: transaction dài có thể giữ khóa, phiên bản MVCC, dung lượng log và tài nguyên kết nối lâu hơn. Giảm batch size chỉ giảm số lệnh chờ mỗi đợt, **không làm transaction ngắn hơn** nếu vẫn commit cuối cùng.

### B. Một transaction cho mỗi chunk

~~~text
Chunk 1: begin → executeBatch → commit
Chunk 2: begin → executeBatch → commit
...
Chunk 20: begin → executeBatch → commit
~~~

Nếu chunk 13 lỗi, 12 chunk đã commit trước đó **không thể rollback** bằng giao dịch của chunk 13. Đổi lại mỗi transaction nhỏ hơn, có thể cho phép ghi checkpoint và tiếp tục từ một đoạn chưa hoàn thành.

| Tiêu chí | Một transaction bao trùm | Commit theo chunk |
| --- | --- | --- |
| Tính nguyên tử toàn bộ | Đáp ứng nếu DBMS hỗ trợ | Không |
| Rollback khi chunk cuối lỗi | Hủy tất cả thay đổi chưa commit | Chỉ hủy transaction chunk hiện tại |
| Giữ khóa/tài nguyên | Có thể lâu hơn | Thường ngắn hơn |
| Phục hồi sau ngắt quãng | Thường chạy lại cả đơn vị | Tiếp tục từ checkpoint đã commit |
| Yêu cầu idempotency | Cần khi commit có outcome chưa rõ | Cần cho từng chunk và quy trình resume |
| Phù hợp | Dữ liệu liên quan chặt chẽ | Dữ liệu độc lập, chấp nhận thành công một phần |

**Batch size** là số lệnh trong một lần gửi; **transaction size** là lượng công việc giữa hai lần commit/rollback. Một transaction có thể chứa nhiều lần `executeBatch()`.

### Chọn kích thước batch thế nào?

Không có con số cố định tốt cho mọi DBMS. Bắt đầu với vài trăm lệnh và đo thực tế:

- Thời gian `executeBatch()` và round-trip tới DBMS.
- Bộ nhớ driver giữ cho các bộ tham số.
- Thời gian transaction, lock waits, deadlock và rollback cost.
- Kích thước tham số, giới hạn packet/SQL parameter của driver.
- Khả năng rewrite batch của driver và cách nó trả update counts.
- Nhu cầu lấy generated keys và đối chiếu bản ghi đầu vào/đầu ra.

Một SQL đa hàng hoặc công cụ bulk-load chuyên biệt của DBMS có thể nhanh hơn batch JDBC, nhưng cần đánh giá lại transaction semantics và cách xử lý lỗi.

## 8. Checkpoint và idempotency khi commit từng chunk

Nếu ứng dụng import 10.000 dòng theo 20 chunk, cần có cơ chế biết chunk nào **đã commit**, chunk nào còn phải xử lý.

Ví dụ:

~~~text
import_id = IMP-2026-001
chunk 1 = COMMITTED
chunk 2 = COMMITTED
chunk 3 = FAILED
chunk 4 = NOT_STARTED
~~~

Một thiết kế đáng tin cậy:

1. Mỗi dòng có khóa ổn định như `(import_id, source_row_number)` và ràng buộc `UNIQUE` trong DB.
2. Ghi checkpoint **trong cùng transaction** với dữ liệu chunk, để tránh checkpoint báo thành công trước khi dữ liệu thực sự được lưu.
3. Nếu mất kết nối lúc `commit()`, dùng connection mới đối chiếu checkpoint và khóa nghiệp vụ.
4. Retry an toàn nhờ khóa chống ghi trùng hoặc logic idempotency, không chạy lại mù.
5. Khi cần hủy công việc đã commit ở chunk trước, phải dùng cơ chế bù trừ hoặc sửa dữ liệu rõ ràng; `rollback()` không quay ngược transaction đã hoàn tất.

Đây cũng là lý do không nên chỉ dùng bộ đếm Java trong bộ nhớ làm checkpoint lâu dài: tiến trình có thể chết sau khi DB commit nhưng trước khi bộ đếm được lưu.

## 9. Có thể dùng savepoint để bỏ qua chunk tùy chọn không?

Có thể, nhưng chỉ khi DBMS/driver hỗ trợ và **nghiệp vụ cho phép hủy riêng phần tùy chọn**.

~~~java
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Savepoint;

static void tryOptionalPart(Connection conn) throws SQLException {
    if (conn.getAutoCommit()) {
        throw new SQLException("Savepoint yêu cầu manual transaction");
    }

    Savepoint beforePart = conn.setSavepoint();

    try {
        executeOptionalBatch(conn);
    } catch (SQLException expectedOptionalFailure) {
        // Chỉ bắt lỗi đã được nghiệp vụ cho phép bỏ qua.
        conn.rollback(beforePart);
    }

    // Tầng gọi vẫn quyết định commit/rollback transaction lớn.
}
~~~

Hàm `executeOptionalBatch(conn)` là hàm minh họa dùng cùng connection, không tự commit. Trong code thật, cần kiểm tra loại lỗi thay vì bỏ qua mọi `SQLException`. Nếu rollback tới savepoint thất bại hoặc toàn transaction bị DBMS hủy (ví dụ một số deadlock), **không được tiếp tục commit**.

Có thể kiểm tra `DatabaseMetaData.supportsSavepoints()` và sử dụng `releaseSavepoint()` khi phù hợp. `releaseSavepoint()` không commit transaction.

Đối với các dòng **bắt buộc**, savepoint không phải lối thoát để bỏ qua lỗi rồi vẫn commit các phần còn lại.

## 10. Lỗi rollback và kết quả commit chưa xác định

Một lỗi tại `executeBatch()` và một lỗi tại `commit()` có ý nghĩa rất khác nhau:

- **Batch lỗi trước commit:** nếu connection còn hoạt động và rollback thành công, có thể hủy những thay đổi chưa commit của transaction.
- **Rollback cũng lỗi:** không thể tự khẳng định DBMS đã hủy toàn bộ dữ liệu; cần ghi nhận lỗi và xử lý connection không còn đáng tin.
- **Commit lỗi do mất mạng:** DBMS có thể đã commit nhưng phản hồi không tới Java. `SQLException` từ `commit()` không chứng minh transaction chưa được lưu.

~~~text
Ứng dụng Java           Mạng                    CSDL
      |                   |                       |
      |---- COMMIT ------>|---- COMMIT ---------->|
      |                   |                 Đã commit
      |                   X   Mất phản hồi       |
      |<--- SQLException -|                       |
~~~

Do đó, **không retry toàn batch ngay lập tức** khi outcome của commit chưa rõ. Cần đối soát bằng idempotency key hoặc khóa nghiệp vụ trên kết nối mới.

Ngoài ra, `Connection.setAutoCommit(true)` khi vẫn có transaction chưa kết thúc có thể khiến transaction được commit. Không đặt lệnh đó vô điều kiện trong `finally` sau khi `rollback()` thất bại.

Một local JDBC transaction chỉ kiểm soát những SQL tham gia vào transaction trên connection đó. Nó **không tự hủy** email đã gửi, yêu cầu HTTP đã xử lý hoặc tác động đến hệ thống ngoài. Với công việc xuyên hệ thống, cần transactional outbox, idempotency hoặc quy trình bù trừ phù hợp.

## 11. Những lỗi thiết kế hay gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Cho rằng một lần `executeBatch()` tự nguyên tử | Dữ liệu có thể lưu một phần sau lỗi | Quản lý transaction rõ ràng |
| Gọi `clearBatch()` sau lỗi để “rollback” | Chỉ xóa hàng đợi, không hủy dữ liệu đã chạy | `Connection.rollback()` |
| Bỏ qua `BatchUpdateException.getUpdateCounts()` | Thiếu thông tin chẩn đoán | Đọc counts, SQLState, vendor code |
| Coi `SUCCESS_NO_INFO` là lỗi | Đánh giá sai kết quả | Hiểu đó là thành công không biết số hàng |
| Không kiểm tra update count `0` | Bỏ qua lỗi nghiệp vụ | Xác thực hậu điều kiện |
| Tưởng mọi chunk dùng cùng transaction | Chunks trước có thể đã commit | Xác định vị trí `commit()` |
| Để DAO mở connection riêng | Rollback không bao phủ toàn quy trình | Truyền chung connection từ service |
| Luôn trả `autoCommit` về true trong `finally` | Có thể commit transaction chưa được rollback | Kết thúc transaction an toàn trước |
| Retry ngay sau lỗi ở `commit()` | Có thể nhập bản ghi hai lần | Đối soát và dùng khóa idempotency |
| Dồn hàng triệu bản ghi vào một batch | Tăng memory và rủi ro giới hạn driver | Chia batch/chunk theo đo đạc |
| Giữ transaction trong khi gọi HTTP chậm | Tăng giữ khóa, timeout, deadlock | Rút ngắn transaction |

## 12. Tình huống luyện tập

**Tình huống 1.** Batch 100 câu `INSERT` chạy khi `autoCommit = true`, câu 40 thất bại. Có thể gọi `rollback()` để chắc chắn hủy 39 câu trước không?

**Đáp án:** Không. Một số câu trước có thể đã commit; rollback không thể hủy giao dịch đã hoàn tất. Muốn nguyên tử, cần mở manual transaction trước lệnh đầu tiên.

**Tình huống 2.** Có ba lần `executeBatch()` trong cùng transaction; lần ba lỗi, yêu cầu cả ba cùng thành công. Cần xử lý thế nào?

**Đáp án:** Rollback toàn bộ transaction, bao gồm kết quả chưa commit của hai batch đầu. Không chỉ gọi `clearBatch()` hay bỏ qua câu lỗi.

**Tình huống 3.** `executeBatch()` trả `SUCCESS_NO_INFO` cho một lệnh. Có thể kết luận lệnh thất bại không?

**Đáp án:** Không. Driver đã báo thành công nhưng không cung cấp số hàng chính xác. Nếu nghiệp vụ cần đếm, phải kiểm chứng thêm.

**Tình huống 4.** Một batch `UPDATE` trả `0` hàng ở một phần tử; quy tắc yêu cầu mọi phần tử phải sửa đúng một hàng. Làm gì?

**Đáp án:** Coi đây là lỗi nghiệp vụ, ném ngoại lệ và rollback toàn transaction nếu muốn tất cả hoặc không có gì.

**Tình huống 5.** 12 chunk đầu đã commit, chunk 13 gặp lỗi. Có thể rollback 12 chunk đầu không?

**Đáp án:** Không. Mỗi chunk đã commit là giao dịch hoàn tất; cần checkpoint, thiết kế chấp nhận một phần và cơ chế bù trừ nếu phải quay về trạng thái trước đó.

**Tình huống 6.** 600 dòng được chia batch size 250 nhưng chỉ gọi `commit()` cuối cùng. Có bao nhiêu transaction?

**Đáp án:** Nếu tất cả dùng một connection với `autoCommit = false`, cả 600 dòng có thể thuộc **một transaction** dù `executeBatch()` được gọi ba lần.

**Tình huống 7.** Sau `commit()`, ứng dụng nhận lỗi mạng. Có nên chạy lại ngay toàn batch không?

**Đáp án:** Không. Kết quả có thể chưa rõ; DBMS có thể đã commit. Cần đối soát khóa nghiệp vụ hoặc checkpoint và áp dụng idempotency trước khi retry.

**Tình huống 8.** Có thể dùng savepoint để bỏ qua một chunk lỗi mà vẫn commit transaction lớn không?

**Đáp án:** Chỉ khi phần lỗi thật sự tùy chọn, savepoint được lập trước lỗi, DBMS hỗ trợ phục hồi và rollback tới savepoint thành công. Không dùng cách này để bỏ qua bước bắt buộc.

## Ghi nhớ

- **`addBatch()` xếp lệnh, `executeBatch()` thực thi, `commit()` xác nhận giao dịch**. Batch size và transaction size là hai khái niệm khác nhau.
- Để **nhiều batch cùng nguyên tử**, dùng một `Connection` với `autoCommit = false`, kiểm tra kết quả rồi commit; gặp lỗi bắt buộc thì rollback toàn transaction.
- **`BatchUpdateException` không chứng minh chưa có lệnh nào chạy**. Update counts hỗ trợ chẩn đoán, còn transaction quyết định phần thay đổi nào được giữ lại.
- **`clearBatch()` không rollback dữ liệu** và `SUCCESS_NO_INFO` không đồng nghĩa thất bại.
- **Commit từng chunk** chỉ phù hợp khi chấp nhận thành công một phần và có checkpoint/idempotency.
- **Sau lỗi commit không rõ kết quả, không retry mù**; cần đối soát và bảo vệ chống ghi lặp.
