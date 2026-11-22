# Gộp lệnh và xử lý theo lô theo khả năng công nghệ

Trong ứng dụng Java, một nghiệp vụ có thể cần ghi hàng nghìn dòng chi tiết đơn hàng, cập nhật trạng thái cho một tập bản ghi hoặc nhập một lượng dữ liệu lớn từ hệ thống khác. Cách đơn giản nhất là chạy một câu SQL cho từng phần tử. Tuy nhiên, nếu mỗi lời gọi phải đi qua driver, mạng, bộ xử lý SQL và một lượt nhận kết quả, hàng nghìn thao tác nhỏ có thể bị chi phối bởi chi phí lặp đi lặp lại hơn là thời gian thực sự thay đổi dữ liệu.

**Gộp lệnh (batching)** và **xử lý theo lô (batch processing)** là những kỹ thuật tổ chức nhiều thao tác thành các nhóm hợp lý để giảm overhead, tăng thông lượng và kiểm soát tài nguyên. Nhưng “gộp” có nhiều mức: gom nhiều lệnh vào một JDBC batch, viết một câu SQL thao tác theo tập, gửi nhiều hàng bằng một `INSERT ... VALUES`, dùng cơ chế nạp dữ liệu riêng như PostgreSQL `COPY`, hoặc chia một job lớn thành các transaction nhỏ. Những lựa chọn này **không có cùng đặc tính nguyên tử, bộ nhớ, mạng, khóa và xử lý lỗi**.

Bài thuộc chương **Hiệu năng** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Mục tiêu là hiểu những kỹ thuật có thể áp dụng cho persistence trong Java, lựa chọn theo **khả năng thực tế của JDBC driver, ORM và DBMS**, đồng thời giữ đúng dữ liệu, ranh giới giao dịch, kiểm soát đồng thời và khả năng phục hồi sau lỗi.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **JDBC batching**, **multi-row SQL**, **set-based SQL**, **bulk loading** và **batch job**.
2. Giải thích batch giúp giảm chi phí lượt đi mạng, parse, tạo statement và overhead, nhưng không loại bỏ chi phí thực thi SQL hay ghi dữ liệu bền vững.
3. Viết `PreparedStatement.addBatch()`/`executeBatch()` và đọc đúng kết quả `updateCounts`.
4. Dùng transaction, rollback và `BatchUpdateException` để xử lý lỗi từng phần mà không báo thành công sai.
5. Hiểu khi nào Spring JDBC, JPA/Hibernate hoặc công cụ SQL-centric có thể hoặc không thể thực sự batch.
6. Chọn kích thước lô phù hợp với giới hạn tham số, payload, memory, khóa, log giao dịch và độ trễ.
7. Tách kích thước **nhóm gửi lệnh** khỏi kích thước **transaction commit** và **lô công việc nền**.
8. Tối ưu thao tác đọc N+1, nhập hàng loạt, cập nhật theo tập và retry/idempotency có kiểm soát.
9. Kiểm thử bằng số lượng SQL thực tế và đo throughput, p95/p99, rollback, áp lực DB thay vì chỉ dựa vào cấu hình.

## 2. Những khái niệm cần phân biệt

| Khái niệm | Cách thực hiện | Đơn vị được tối ưu | Điều **không** tự bảo đảm |
|---|---|---|---|
| **JDBC batch** | `addBatch()` rồi `executeBatch()` trên `Statement`/`PreparedStatement` | Gộp nhiều lượt thực thi ở giao diện JDBC; driver có thể tối ưu cách gửi | Một SQL duy nhất, một transaction, hoặc tất cả thành công |
| **Multi-row INSERT** | `INSERT ... VALUES (...), (...), (...)` | Một câu SQL chứa nhiều hàng | Idempotency hoặc phù hợp giới hạn tham số |
| **Set-based SQL** | `UPDATE ... WHERE`, `UPDATE ... FROM`, `INSERT ... SELECT`, `DELETE ... WHERE` | Một phép toán trên một tập hàng tại DBMS | Không ảnh hưởng hàng ngoài ý định hoặc không giữ khóa |
| **Bulk load** | PostgreSQL `COPY` hoặc API bulk của DBMS | Đưa lượng dữ liệu lớn qua đường nhập chuyên dụng | Dễ xử lý xung đột từng hàng hoặc dùng được trên mọi DB |
| **ORM batching** | ORM gom các SQL phát sinh khi flush | Giảm round-trip khi ghi entity | `saveAll` luôn gom SQL, có thể dùng cho mọi ID strategy |
| **Batch job** | Đọc/biến đổi/ghi theo chunk có checkpoint | Kiểm soát memory, thời gian chạy, restart và transaction | Toàn bộ job là một transaction nguyên tử |
| **Batch fetch/read** | Truy vấn một tập ID hoặc fetch plan | Giảm N+1 lượt SELECT | Không tải dư dữ liệu hoặc không vượt giới hạn câu SQL |

Bài này xem xét cả hai ý nghĩa của “lô”: **gộp các lệnh trong một lượt thực thi** và **chia công việc lớn thành các đơn vị có thể kiểm soát**. Có lúc cần kết hợp cả hai, nhưng không được nhập chúng thành một khái niệm.

### 2.1. Những tầng có thể gộp

~~~mermaid
flowchart TD
    A["Danh sách thao tác Java"] --> B{"Chọn chiến lược"}
    B --> C["Một SQL set-based / multi-row"]
    B --> D["JDBC PreparedStatement batch"]
    B --> E["ORM flush với batch"]
    B --> F["Bulk loader / COPY"]
    C --> G["DBMS: thực thi, khóa, WAL"]
    D --> H["JDBC driver: protocol / rewrite"]
    E --> H
    H --> G
    F --> G
    G --> I["COMMIT / ROLLBACK theo transaction"]
~~~

Với JDBC batch, ứng dụng vẫn yêu cầu thực hiện nhiều tham số hoặc nhiều statement. **Driver quyết định** có thể gửi theo một hình thức giao thức/SQL tối ưu nào hay không. Một JDBC batch 100 hàng không mặc nhiên tương đương **một SQL INSERT nhiều hàng** tại server.

### 2.2. Vì sao gộp có thể nhanh hơn?

Giả sử có 2.000 thao tác nhỏ, mỗi lượt đi-về mạng tốn khoảng 4 ms. **Chỉ riêng chi phí round-trip theo giả định**:

~~~text
Không gộp: 2.000 × 4 ms = 8.000 ms.

Nếu công nghệ thực sự giảm số lượt đi-về còn 40:
  40 × 4 ms = 160 ms.
~~~

Đây là phép tính minh họa **riêng phần mạng**, không phải benchmark hay cam kết “nhanh gấp 50 lần”. Tổng thời gian thực tế còn có parse, lập kế hoạch thực thi, ghi WAL/redo, kiểm tra unique/FK, index maintenance, I/O, replication, khóa và xử lý kết quả. Một driver có thể không giảm lượt đi-về đúng như ví dụ.

Bởi vậy phải xác minh tối ưu có xảy ra **tại tầng nào**, trên driver/database phiên bản nào, thay vì chỉ thấy tên `batch` trong code rồi kết luận hệ thống đã tăng tốc.

## 3. Cách chọn thao tác SQL trước khi chọn thư viện

Tư duy đầu tiên nên là: **bài toán có thể diễn đạt như một phép toán trên tập dữ liệu tại DB hay không?**

### 3.1. N lần UPDATE so với một UPDATE theo tập

Ví dụ cần đóng toàn bộ các phiên làm việc hết hạn.

Cách lặp trên Java:

~~~java
for (Long sessionId : expiredIds) {
    // Mỗi lần repository.updateExpired(sessionId) có thể gửi một UPDATE.
    repository.markExpired(sessionId);
}
~~~

Nếu quy tắc thực sự là “đóng mọi session đang mở và quá hạn”, SQL có thể rõ hơn:

~~~sql
UPDATE user_sessions
SET state = 'EXPIRED'
WHERE state = 'ACTIVE'
  AND expires_at < CURRENT_TIMESTAMP;
~~~

Đây là **một lệnh thao tác theo tập**. Nó có thể tránh tải danh sách ID sang Java chỉ để gửi ngược từng lệnh UPDATE. Tuy nhiên, phạm vi ảnh hưởng phải khớp nghiệp vụ: nếu job được giao một **tập ID xác định**, không được thay bằng UPDATE mọi session hết hạn khi hợp đồng chỉ cho sửa một tập nhỏ.

Nếu cần giới hạn tập:

~~~sql
UPDATE user_sessions
SET state = 'EXPIRED'
WHERE state = 'ACTIVE'
  AND id IN (101, 102, 103);
~~~

Trong ứng dụng, hãy bind tham số đúng cách thay cho nối chuỗi ID không kiểm soát. Với danh sách động lớn, có thể dùng mảng/tham số theo DBMS hoặc nạp ID vào bảng tạm/staging, không tự tạo một câu SQL có hàng triệu literal.

### 3.2. Một INSERT nhiều hàng

Ví dụ PostgreSQL:

~~~sql
INSERT INTO order_items (
    order_id, line_no, sku, quantity, unit_price
) VALUES
    (42, 1, 'BOOK-01', 2, 125000.00),
    (42, 2, 'PEN-04',  3,   5000.00),
    (42, 3, 'BAG-02',  1, 150000.00);
~~~

Tất cả nằm trong **một câu INSERT**, DBMS xử lý ràng buộc và báo lỗi cho câu SQL đó. Tuy nhiên:

- Số tham số trong prepared statement, chiều dài SQL và kích thước bản tin có giới hạn tùy driver/DBMS.
- Một câu SQL khổng lồ có thể tốn nhiều memory, parse/plan và chiếm tài nguyên lâu.
- Vi phạm một constraint có thể khiến câu INSERT thất bại; không được giả định tự động bỏ qua hàng lỗi.
- Lượng index/WAL cần ghi vẫn tương ứng dữ liệu thật.
- Không mặc định rằng multi-row INSERT luôn tốt hơn `COPY` hoặc JDBC batch ở mọi tải.

### 3.3. `INSERT ... SELECT` và `UPDATE ... FROM`

Khi dữ liệu đã nằm trong database, chuyển đổi theo tập thường tránh vòng đi mạng sang Java:

~~~sql
INSERT INTO shipment_candidates (order_id, created_at)
SELECT id, CURRENT_TIMESTAMP
FROM orders
WHERE status = 'PAID'
  AND shipping_required = TRUE
ON CONFLICT (order_id) DO NOTHING;
~~~

Ví dụ yêu cầu bảng đích có unique/primary key phù hợp trên `order_id`. `ON CONFLICT DO NOTHING` làm việc gửi lại có thể an toàn **cho thao tác chèn cùng khóa**, nhưng vẫn phải xác minh nội dung và quy tắc nghiệp vụ: một bản ghi đã tồn tại không chứng minh dữ liệu đó đúng.

Với dữ liệu cần đối chiếu từ staging:

~~~sql
UPDATE products AS p
SET price = s.new_price
FROM product_price_staging AS s
WHERE p.id = s.product_id
  AND s.validated = TRUE;
~~~

Cần thiết kế staging sao cho tối đa một hàng ứng viên hợp lệ cho mỗi `product_id`. Nếu nguồn có nhiều hàng khớp một đích, hành vi chọn giá trị có thể khó dự đoán hoặc không phù hợp nghiệp vụ. Hãy áp unique, chọn hàng theo version/thời gian và kiểm thử theo DBMS.

### 3.4. Một bulk SQL cũng có thể là lựa chọn sai

Đừng dùng một `UPDATE` thay đổi hàng triệu bản ghi trong lúc cao điểm chỉ vì nó là “một câu SQL”. Nó có thể:

- Giữ khóa nhiều hàng trong thời gian dài.
- Tạo WAL/redo lớn và replication lag.
- Tăng thời gian rollback khi lỗi.
- Gây bloat/MVCC pressure.
- Chặn các giao dịch nghiệp vụ khác.

Khi một phép toán set-based có phạm vi quá lớn, **chia thành các chunk có commit riêng** có thể phù hợp hơn nếu ngữ nghĩa cho phép kết quả cập nhật từng phần.

## 4. JDBC batching: hợp đồng API và giới hạn khả năng

Giao diện JDBC hỗ trợ:

~~~java
PreparedStatement ps = connection.prepareStatement(
    "INSERT INTO audit_events(event_id, event_type) VALUES (?, ?)");

ps.setLong(1, 1001L);
ps.setString(2, "CREATED");
ps.addBatch();

ps.setLong(1, 1002L);
ps.setString(2, "APPROVED");
ps.addBatch();

int[] counts = ps.executeBatch();
~~~

Đoạn mã trên chỉ thể hiện API. Trong code thực phải đóng `PreparedStatement`/`Connection`, xác định transaction, xử lý ngoại lệ và kiểm tra `counts`. Với `PreparedStatement`, mỗi `addBatch()` lưu tập tham số của lượt thực thi, còn `executeBatch()` gửi nhóm thao tác qua driver. Sau khi thực thi, nên biết rõ vòng đời dữ liệu batch và không vô tình gửi lại nhóm cũ.

### 4.1. Kiểm tra hỗ trợ của JDBC driver

Có thể truy vấn metadata:

~~~java
boolean supported =
    connection.getMetaData().supportsBatchUpdates();
~~~

Kết quả chỉ nói driver tuyên bố hỗ trợ batch update. Nó **không** nói rằng:

- Driver luôn rewrite thành một câu `INSERT` nhiều hàng.
- Driver bảo đảm latency giảm theo tỷ lệ số phần tử.
- DBMS xử lý batch như một đơn vị nguyên tử nếu không mở transaction.
- Chỉ cần bật batch là mọi ORM sẽ sử dụng nó.

Khả năng tối ưu còn tùy driver/version, giao thức, loại SQL, cách gọi `getGeneratedKeys`, transaction, prepared statement và cấu hình.

### 4.2. Phân biệt `Statement.addBatch(sql)` và `PreparedStatement.addBatch()`

`Statement` có thể chứa nhiều chuỗi SQL khác nhau. `PreparedStatement` có một mẫu SQL cố định và nhiều bộ tham số:

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE products SET name = ? WHERE id = ?")) {
    for (ProductRename rename : renames) {
        ps.setString(1, rename.newName());
        ps.setLong(2, rename.productId());
        ps.addBatch();
    }
    int[] counts = ps.executeBatch();
}
~~~

Với dữ liệu từ người dùng, ưu tiên `PreparedStatement` để bind giá trị thay vì tự nối chuỗi SQL. Việc dùng prepared statement cũng giúp code rõ cấu trúc lệnh, nhưng không tự xóa hết chi phí parse/plan hay bảo đảm mọi backend tái sử dụng plan theo cùng cách.

### 4.3. `executeBatch()` trả về gì?

Theo JDBC, `executeBatch()` trả `int[]` tương ứng các lệnh đã đưa vào batch. Giá trị thường là:

- Một số không âm: số hàng bị ảnh hưởng, theo khả năng driver.
- `Statement.SUCCESS_NO_INFO`, giá trị `-2`: lệnh thành công nhưng không có số hàng chính xác.
- `Statement.EXECUTE_FAILED`, giá trị `-3`: có lệnh thất bại nếu driver báo kết quả theo cách này.

Nếu một lệnh lỗi, JDBC có thể ném `BatchUpdateException`. `getUpdateCounts()` có thể chứa thông tin về một phần lệnh trước lỗi, hoặc tiếp tục có các mục đánh dấu thất bại, tùy driver tiếp tục hay dừng. **Không được giả định array luôn dài bằng số phần tử batch hoặc chỉ dựa vào một kiểu hành vi trên mọi driver.**

`BatchUpdateException` là một `SQLException`: giữ nguyên SQLSTATE, vendor code, `getCause()` và chuỗi `getNextException()` khi ghi log/ánh xạ lỗi. Đừng biến nó thành `RuntimeException("Batch failed")` mà đánh mất nguyên nhân.

### 4.4. Số hàng được báo không phải bằng chứng transaction đã commit

Một batch có thể thực thi thành công trong transaction, sau đó một bước nghiệp vụ khác lỗi và toàn transaction rollback. Hoặc lỗi mạng có thể xảy ra lúc `COMMIT` khiến client không biết chắc kết quả. Cần phân biệt:

~~~text
addBatch()      -> chuẩn bị phần tử cho driver
executeBatch()  -> driver gửi và nhận kết quả thực thi
commit()        -> yêu cầu DBMS kết thúc transaction thành công
close()         -> trả/tắt tài nguyên kết nối
~~~

Đừng ghi nhận “đã lưu bền vững N hàng” chỉ vì `executeBatch()` trả counts dương trong transaction chưa commit.

## 5. Ví dụ Java JDBC đầy đủ: insert theo batch

Giả sử muốn ghi các dòng hàng của một đơn. Schema minh họa PostgreSQL:

~~~sql
CREATE TABLE order_items (
    order_id   BIGINT NOT NULL,
    line_no    INTEGER NOT NULL CHECK (line_no > 0),
    sku        TEXT NOT NULL,
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(14, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Khóa chính `(order_id, line_no)` ngăn cùng một đơn có hai dòng trùng vị trí. Việc tham chiếu tới bảng orders thực tế cần foreign key nếu bài toán yêu cầu; ví dụ lược bớt phần đó để tập trung vào batch.

### 5.1. Một transaction cho tất cả dòng của một đơn

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;
import javax.sql.DataSource;

public final class OrderItemBatchWriter {
    private static final int BATCH_SIZE = 200;
    private final DataSource dataSource;

    public record Line(
        int lineNo, String sku, int quantity, BigDecimal unitPrice) {}

    public OrderItemBatchWriter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void insertAll(long orderId, List<Line> lines)
            throws SQLException {
        for (Line line : lines) {
            if (line.lineNo() <= 0
                    || line.sku() == null || line.sku().isBlank()
                    || line.quantity() <= 0
                    || line.unitPrice() == null
                    || line.unitPrice().signum() < 0) {
                throw new IllegalArgumentException("Invalid order line");
            }
        }

        try (Connection connection = dataSource.getConnection()) {
            boolean originalAutoCommit = connection.getAutoCommit();
            Throwable originalFailure = null;

            try {
                connection.setAutoCommit(false);

                try (PreparedStatement ps = connection.prepareStatement(
                        """
                        INSERT INTO order_items (
                            order_id, line_no, sku, quantity, unit_price
                        ) VALUES (?, ?, ?, ?, ?)
                        """)) {
                    int pending = 0;

                    for (Line line : lines) {
                        ps.setLong(1, orderId);
                        ps.setInt(2, line.lineNo());
                        ps.setString(3, line.sku());
                        ps.setInt(4, line.quantity());
                        ps.setBigDecimal(5, line.unitPrice());
                        ps.addBatch();
                        pending++;

                        if (pending == BATCH_SIZE) {
                            validateCounts(ps.executeBatch());
                            pending = 0;
                        }
                    }
                    if (pending > 0) {
                        validateCounts(ps.executeBatch());
                    }
                }

                connection.commit();
            } catch (SQLException | RuntimeException failure) {
                originalFailure = failure;
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            } finally {
                try {
                    connection.setAutoCommit(originalAutoCommit);
                } catch (SQLException restoreFailure) {
                    if (originalFailure != null) {
                        originalFailure.addSuppressed(restoreFailure);
                    } else {
                        throw restoreFailure;
                    }
                }
            }
        }
    }

    private static void validateCounts(int[] counts)
            throws SQLException {
        for (int count : counts) {
            if (count == Statement.EXECUTE_FAILED) {
                throw new SQLException("One JDBC batch item failed");
            }
            if (count != Statement.SUCCESS_NO_INFO && count != 1) {
                throw new SQLException(
                    "Unexpected affected-row count: " + count);
            }
        }
    }
}
~~~

**Giới hạn của ví dụ:** danh sách `lines` được giữ trong bộ nhớ và được giả định đã thuộc cùng một đơn; `lineNo` phải duy nhất trong nghiệp vụ. Với dữ liệu quá lớn nên đọc từ stream/phân đoạn, không materialize toàn bộ job thành một `List`. Đoạn này không phải ví dụ đầy đủ về chuyển tiền, hóa đơn hay cơ chế chống xử lý trùng request ở cấp API.

### 5.2. Vì sao vẫn chỉ commit một lần?

Chúng ta đã gửi các nhóm `executeBatch()` có tối đa 200 phần tử. Nhưng vì `connection.setAutoCommit(false)`, tất cả nhóm vẫn ở **một transaction**:

~~~text
BEGIN transaction
    executeBatch(200 rows)
    executeBatch(200 rows)
    executeBatch(37 rows)
COMMIT once
~~~

Nếu câu INSERT trong nhóm cuối vi phạm ràng buộc, ứng dụng rollback toàn bộ **437 dòng của lần gọi**, không chỉ 37 dòng cuối, miễn là DBMS/tables hỗ trợ transaction theo phạm vi đó và kết nối chưa thực sự commit.

Đây là điều phù hợp nếu một đơn phải có **tất cả dòng hoặc không có dòng nào**. Với job nhập độc lập hàng triệu bản ghi, có thể cần mỗi chunk commit riêng. Thay đổi kích thước batch **không tự thay đổi ranh giới transaction**.

### 5.3. Cẩn thận với lỗi ngay sau commit

Ví dụ khôi phục `autoCommit` trong `finally`. Nếu `commit()` đã thành công nhưng reset connection thất bại, caller có thể nhận một `SQLException` dù dữ liệu đã commit. Nếu mạng đứt trong lúc commit, kết quả còn có thể **không chắc chắn**.

Không tự retry `insertAll` chỉ vì nhận một `SQLException`: lần đầu có thể đã commit. Thiết kế nghiệp vụ thực cần mã lệnh duy nhất, ràng buộc khóa, khả năng đọc lại kết quả/đối soát và chính sách retry theo từng lỗi.

### 5.4. Kết quả batch và `BatchUpdateException`

Nếu `executeBatch()` ném `BatchUpdateException`, cách ghi chẩn đoán có thể là:

~~~java
catch (java.sql.BatchUpdateException error) {
    int[] partialCounts = error.getUpdateCounts();

    // Quan sát số phần tử driver báo, nhưng không kết luận đã commit.
    logger.warn(
        "Batch failed; reportedItems={}, sqlState={}, vendorCode={}",
        partialCounts.length, error.getSQLState(), error.getErrorCode(),
        error
    );
    throw error; // Giữ nguyên cause, nextException và stack trace.
}
~~~

Đây là đoạn minh họa tại nơi đã có `logger`; không nên log cùng một stack trace ở mọi tầng. Khi xử lý retry, sử dụng toàn bộ SQLSTATE/vendor code và ngữ cảnh transaction, **không suy diễn kết quả thành công cuối cùng từ `partialCounts`**.

## 6. Giao dịch và lỗi từng phần: ba phạm vi độc lập

Phải tách rõ:

1. **Batch gửi lệnh:** một nhóm `executeBatch()` hoặc một bulk SQL.
2. **Transaction:** số thao tác cùng `COMMIT` hoặc `ROLLBACK`.
3. **Job/checkpoint:** phạm vi công việc được coi là hoàn tất khi có thể restart.

Ví dụ cùng 1.000 hàng:

| Chiến lược | Gửi lệnh | Commit | Nếu hàng 750 lỗi |
|---|---|---|---|
| Không batch, một transaction | 1.000 lần execute | Một lần | Có thể rollback cả 1.000 |
| JDBC batch 100, một transaction | 10 `executeBatch()` | Một lần | Có thể rollback cả 1.000 |
| JDBC batch 100, commit mỗi chunk | 10 `executeBatch()` | 10 lần | 700 hàng đầu có thể đã commit |
| Một multi-row INSERT 1.000 hàng | Một SQL | Tùy transaction | Câu SQL thất bại theo ngữ nghĩa DBMS |
| COPY vào staging, rồi merge | Nạp bulk + một hay nhiều SQL | Do ứng dụng thiết kế | Tùy ranh giới staging/merge |

“Có thể rollback” ở bảng trên giả định dùng DBMS/tables giao dịch và thiết kế rollback đúng. Với `autoCommit=true`, một số driver/DBMS có thể đã commit nhiều thao tác trong batch trước khi lỗi được báo. Không hứa atomicity toàn batch chỉ vì API mang tên `executeBatch`.

### 6.1. PostgreSQL và transaction bị lỗi

Trong PostgreSQL, khi một câu lệnh gây lỗi SQL bên trong transaction thông thường, transaction có thể chuyển sang trạng thái thất bại cho tới khi rollback (hoặc xử lý savepoint phù hợp). Vì vậy cố gửi tiếp các câu SQL sau một lỗi unique/deadlock trong cùng transaction không phải chiến lược “bỏ qua một dòng rồi tiếp tục” tổng quát.

Nếu mục tiêu là “nhập các hàng tốt, cách ly hàng xấu”, hãy thiết kế trước:

- Validate dữ liệu trước khi batch.
- Nạp vào staging và phân loại hàng lỗi.
- Chia chunk có transaction riêng nếu nghiệp vụ cho phép.
- Sử dụng constraint và chính sách xử lý xung đột rõ.
- Ghi kết quả từng chunk/checkpoint và xử lý ngoại lệ theo ngữ nghĩa.

**Savepoint cho từng hàng** có thể hỗ trợ cô lập lỗi trong vài trường hợp, nhưng chi phí overhead tăng và không phải kỹ thuật tối ưu mặc định cho lượng dữ liệu lớn.

### 6.2. `getGeneratedKeys` và batch INSERT

Khi DB tự sinh khóa, Java có thể cần trả khóa về để tạo bản ghi liên quan. `getGeneratedKeys()` hỗ trợ một số đường đọc khóa, nhưng cách driver ánh xạ khóa trả về tới từng phần tử batch, kết hợp SQL rewrite/`RETURNING`, và ảnh hưởng của lỗi/xung đột **phụ thuộc driver, DBMS và loại SQL**.

Nếu cần chắc chắn mapping ID:

- Cân nhắc cấp ID ở ứng dụng (UUID hoặc chiến lược đã thiết kế).
- Dùng cơ chế sinh ID hỗ trợ batching của ORM/provider.
- Hoặc dùng `RETURNING` và ánh xạ kết quả theo khóa nghiệp vụ rõ ràng nếu DBMS/driver hỗ trợ cách truy vấn đó.

Không dựa vào một ví dụ driver duy nhất để khẳng định mọi JDBC batch đều trả generated keys đầy đủ theo thứ tự chèn.

## 7. Spring JDBC: batch update không đồng nghĩa transaction

Với Spring `JdbcTemplate`, có thể truyền một danh sách bộ tham số:

~~~java
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;

public final class ProductPriceWriter {
    private final JdbcTemplate jdbcTemplate;

    public ProductPriceWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void updatePrices(List<Object[]> rows) {
        jdbcTemplate.batchUpdate(
            "UPDATE products SET price = ? WHERE id = ?",
            rows
        );
    }
}
~~~

Trong ví dụ, mỗi phần tử `Object[]` chứa hai tham số `price` và `id`. Cần validate kiểu và giá trị trước khi gọi. API `batchUpdate` có thể tận dụng batching theo khả năng JDBC driver, nhưng **không tự đặt đúng transaction boundary của một use case**.

Nếu nghiệp vụ yêu cầu nhiều bảng cùng commit/rollback, đặt transaction ở application service:

~~~java
@Service
public class ProductImportService {
    private final ProductPriceWriter prices;
    private final AuditWriter audit;

    public ProductImportService(ProductPriceWriter prices, AuditWriter audit) {
        this.prices = prices;
        this.audit = audit;
    }

    @Transactional
    public void importChunk(List<Object[]> changes) {
        prices.updatePrices(changes);
        audit.recordPriceImport(changes.size());
    }
}
~~~

Đoạn trên minh họa cấu trúc: cần định nghĩa `AuditWriter` và cấu hình bean/transaction manager. Để cùng transaction, hai repository phải dùng đúng `DataSource`/transaction manager. Nếu `audit` gửi HTTP sang hệ ngoài, `@Transactional` không bảo đảm rollback cả tác dụng phụ đó.

Nếu cần **mỗi chunk commit riêng**, orchestration nên gọi một service có `@Transactional` qua Spring proxy cho từng chunk. Không tự gọi method annotated trong cùng bean rồi mặc định interceptor sẽ mở transaction mới; self-invocation có thể bỏ qua proxy.

## 8. ORM/JPA/Hibernate: gộp SQL cần hiểu persistence context

Khi dùng Jakarta Persistence, code có thể trông như:

~~~java
for (OrderItemEntity item : items) {
    entityManager.persist(item);
}
~~~

Nhiều lời gọi `persist()` không nhất thiết có nghĩa một SQL cho mỗi lần gọi ngay lập tức. Provider có thể giữ entity trong persistence context rồi phát SQL khi `flush`. Nhưng điều đó **không đồng nghĩa** driver sẽ gộp các SQL được phát thành JDBC batch.

### 8.1. Cấu hình batching minh họa

Trong Hibernate, cấu hình thường gặp có dạng:

~~~properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
hibernate.order_updates=true
~~~

Ý nghĩa khái quát:

- `hibernate.jdbc.batch_size` đặt kích thước nhóm JDBC batch mà Hibernate có thể dùng.
- `order_inserts`/`order_updates` cho phép provider sắp xếp thao tác thích hợp nhằm tăng cơ hội gom cùng SQL template.
- Provider vẫn có quyền không batch trong một số trường hợp, tùy dạng entity, ID generation, driver, các ràng buộc và cấu hình khác.

Đây là tên property minh họa của Hibernate; cách khai báo trong Spring Boot hoặc Hibernate version cụ thể có thể khác. Cần kiểm tra cấu hình hiệu lực và SQL thực tế, không xem ví dụ là bảo đảm hiệu năng cố định.

### 8.2. Chiến lược IDENTITY có thể làm mất cơ hội batch INSERT

Với `@GeneratedValue(strategy = GenerationType.IDENTITY)`, provider có thể cần thực hiện INSERT sớm để lấy ID do DB sinh. Hibernate thường **không thể sử dụng JDBC insert batching theo cách thông thường** cho entity dùng identity generator. Cách chọn ID còn liên quan DBMS:

- Sequence với cấp phát theo block có thể cho phép giảm số lần round-trip lấy ID.
- UUID do ứng dụng sinh có thể tránh phải chờ DB cấp ID nhưng có các đánh đổi về kích thước khóa, tính phân bố và index.
- Không chuyển ID strategy trên bảng production chỉ để tăng tốc batch nếu chưa đánh giá schema, foreign key, thứ tự ID và migration.

`saveAll(...)` trong một repository framework **không phải bằng chứng** các INSERT đã được gửi bằng một batch hiệu quả. Phải bật metric/SQL tracing phù hợp và quan sát số thao tác trên DB.

### 8.3. Flush và clear theo chunk để hạn chế bộ nhớ

Một ví dụ JPA dùng `EntityManager`:

~~~java
import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.List;

@Service
public class ImportPersistenceService {
    private final EntityManager entityManager;

    public ImportPersistenceService(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Transactional
    public void persistItems(List<OrderItemEntity> items) {
        final int flushSize = 100;
        int count = 0;

        for (OrderItemEntity item : items) {
            entityManager.persist(item);
            if (++count % flushSize == 0) {
                entityManager.flush();
                entityManager.clear();
            }
        }

        entityManager.flush();
        entityManager.clear();
    }
}
~~~

Việc `flush()` giúp gửi thay đổi xuống DB và `clear()` giải phóng managed entity khỏi persistence context; nó **không tự commit**. Trong ví dụ, một annotation `@Transactional` bao toàn method nên toàn bộ danh sách vẫn là **một transaction**.

Cần đặc biệt chú ý:

- `clear()` làm **detach tất cả managed entities** trong context, không chỉ nhóm item vừa persist. Đừng gọi tùy tiện giữa một use case đang dựa vào dirty checking hoặc cascade của các entity khác.
- Flush có thể ném lỗi constraint trước commit; rollback vẫn cần được transaction manager thực hiện.
- Cascading, orphan removal, versioning và lazy references có thể khiến việc `clear()` trong lúc quản lý object graph trở nên phức tạp.
- Nếu danh sách rất lớn, phương thức vẫn giữ toàn bộ `List` do caller cung cấp; muốn tiết kiệm memory toàn tuyến cần đọc/generate dữ liệu theo trang/stream.
- Số lần flush không bằng số lần round-trip SQL; batching thật sự phải được đo.

### 8.4. Bulk JPQL khác dirty checking entity

JPA hỗ trợ các phép cập nhật hàng loạt trên tập bản ghi:

~~~java
int changed = entityManager.createQuery(
    """
    update ProductEntity p
    set p.archived = true
    where p.lastSeenAt < :cutoff
      and p.archived = false
    """)
    .setParameter("cutoff", cutoff)
    .executeUpdate();
~~~

Bulk JPQL có thể giúp tránh tải từng entity để chỉnh sửa. Nhưng nó **bỏ qua một số cơ chế vòng đời/dirty checking như khi cập nhật entity managed**, có thể không đồng bộ first-level persistence context và không tự áp dụng `@Version` theo cách entity update thông thường. Khi trộn bulk SQL với ORM, cần chủ động `flush` trước và `clear/refresh` sau nếu phù hợp, đồng thời thiết kế concurrency/locking riêng.

Nếu business invariant yêu cầu entity callback, kiểm tra từng đối tượng hoặc audit theo thay đổi, không thể thay bằng bulk UPDATE thiếu kiểm soát chỉ vì nhanh hơn.

## 9. Các framework và driver có khả năng khác nhau

Cùng một ý định “ghi 10.000 bản ghi” có thể được thực hiện rất khác nhau tùy công nghệ. Cần biết **đường SQL cuối cùng** từ framework đến DBMS.

### 9.1. MyBatis và công cụ SQL-centric

MyBatis có chế độ executor kiểu batch (`ExecutorType.BATCH`) cho phép gom các lệnh mapper thích hợp và flush theo hợp đồng framework. Nhưng cần phân biệt:

- Thao tác mapper đã được đưa vào hàng đợi của executor.
- Khi nào executor flush lệnh xuống driver.
- Khi nào transaction thật được commit.
- Một batch có cùng SQL template hay xen kẽ nhiều dạng SQL.
- Cách mapper xử lý generated keys và kết quả số hàng.

Tương tự, jOOQ hoặc lớp JDBC trực tiếp có thể cung cấp API batch hoặc sinh các câu SQL theo tập. **Tên phương thức** không thay thế xác minh database driver và số SQL phát ra. Một hệ thống có thể kết hợp ORM cho logic entity và SQL-centric access cho job bulk nếu transaction/concurrency được tổ chức đúng.

### 9.2. PostgreSQL JDBC driver và rewrite batch

Một số phiên bản/cấu hình PostgreSQL JDBC driver hỗ trợ tối ưu các batch INSERT tương thích bằng cách **rewrite** thành câu INSERT chứa nhiều nhóm `VALUES`, ví dụ property có tên `reWriteBatchedInserts`.

Điều này phụ thuộc:

- Cấu hình/phiên bản pgjdbc và cách ứng dụng tạo statement.
- Dạng SQL có phù hợp để rewrite không.
- Generated keys, `RETURNING`, constraint và cách đọc kết quả.
- Giới hạn kích thước SQL và parameter binding.
- Thực tế server nhận bao nhiêu statement.

Không đặt giả định “chỉ cần bật `reWriteBatchedInserts` là mọi batch đều nhanh”. Cần đọc tài liệu phiên bản driver được triển khai và **đo SQL/round-trip thực**. Với DBMS/driver khác, tên property và cách tối ưu có thể hoàn toàn khác.

### 9.3. Đặc tính transaction và khóa phụ thuộc DBMS

PostgreSQL, MySQL/InnoDB, SQL Server và Oracle đều hỗ trợ cơ chế thực thi hàng loạt, nhưng không đồng nhất:

- Cách xử lý lỗi giữa batch và khả năng tiếp tục câu sau.
- Quy tắc auto-commit và transaction.
- Giới hạn số parameter, độ dài câu SQL và packet.
- Cách lấy generated keys.
- Cú pháp upsert/merge, bulk load và các cơ chế lock.
- Cách ghi log và quản lý undo/MVCC.

Trước khi chọn kỹ thuật đặc thù, xác định chính xác **DBMS + phiên bản + JDBC driver + framework**. Khi chuyển DBMS, không copy nguyên SQL `ON CONFLICT` hoặc PostgreSQL `COPY` rồi mặc định chạy được.

## 10. PostgreSQL `COPY` và mô hình staging cho nhập dữ liệu lớn

Đối với dữ liệu nhập lớn như file CSV hàng triệu dòng, một cơ chế nạp dữ liệu chuyên dụng của DBMS có thể tiết kiệm overhead hơn nhiều `INSERT`. Với PostgreSQL, `COPY` là một lựa chọn cần xem xét.

### 10.1. Vì sao không đổ trực tiếp vào bảng nghiệp vụ?

Ví dụ một file chứa giá sản phẩm từ nhà cung cấp có thể có:

- Sản phẩm không tồn tại.
- Giá âm hoặc sai đơn vị tiền tệ.
- Nhiều dòng cùng mã sản phẩm, với version khác nhau.
- Dữ liệu không đúng encoding hoặc định dạng.
- Dòng trùng do gửi lại file.

Nếu nạp thẳng vào bảng có nhiều index, foreign key và business invariant, một hàng lỗi có thể khiến cả lần nạp thất bại hoặc làm khóa kéo dài.

Một kiến trúc thường hữu ích:

~~~text
CSV / dữ liệu bên ngoài
          |
          v
Parse, normalize, validate đầu vào
          |
          v
COPY / bulk loader -> staging table
          |
          v
SQL kiểm tra và loại dữ liệu sai
          |
          v
Deduplicate theo business key/version
          |
          v
INSERT ... SELECT hoặc UPDATE ... FROM
          |
          v
Bảng chính -> xác minh kết quả, checkpoint
~~~

**Staging** cho phép tách chi phí nạp dữ liệu thô khỏi việc cập nhật các bảng quan trọng. Tuy nhiên, staging cũng phải có retention, quyền truy cập và xử lý dữ liệu nhạy cảm phù hợp.

### 10.2. Cú pháp `COPY` minh họa

~~~sql
CREATE TEMP TABLE price_import_staging (
    product_id     BIGINT NOT NULL,
    price          NUMERIC(14, 2) NOT NULL,
    source_version BIGINT NOT NULL
) ON COMMIT PRESERVE ROWS;
~~~

Dùng lệnh PostgreSQL:

~~~sql
COPY price_import_staging (
    product_id, price, source_version
)
FROM STDIN
WITH (FORMAT csv, HEADER true);
~~~

`COPY ... FROM STDIN` cần luồng dữ liệu đi qua giao thức/công cụ tương ứng; trong Java thường dùng API PostgreSQL CopyManager hoặc cơ chế do driver hỗ trợ, **không** coi nó là một câu `PreparedStatement.executeUpdate()` thông thường trên mọi JDBC driver. Dữ liệu CSV thực tế cần header đúng, encoding và escaping được kiểm soát.

Lựa chọn `TEMP TABLE` có ý nghĩa về vòng đời **session**. Với connection pool, bảng tạm có thể gắn với physical DB session và không tồn tại hoặc còn sót khi mượn một connection khác. Một job dùng staging phải giữ đúng connection/session hoặc dùng staging table bền vững có khóa `import_id` và quy trình cleanup. Không sử dụng tên bảng tạm cố định rồi chia sẻ tùy tiện giữa các request.

### 10.3. Merge theo tập và kiểm tra version

Giả sử bảng chính:

~~~sql
CREATE TABLE products (
    id      BIGINT PRIMARY KEY,
    price   NUMERIC(14, 2) NOT NULL CHECK (price >= 0),
    version BIGINT NOT NULL
);
~~~

Sau khi xác minh dữ liệu staging và xác định giá/version hợp lệ, có thể chọn **version mới nhất** của mỗi sản phẩm rồi upsert:

~~~sql
WITH latest AS (
    SELECT DISTINCT ON (product_id)
        product_id,
        price,
        source_version
    FROM price_import_staging
    WHERE price >= 0
    ORDER BY product_id, source_version DESC
)
INSERT INTO products (id, price, version)
SELECT product_id, price, source_version
FROM latest
ON CONFLICT (id)
DO UPDATE SET
    price = EXCLUDED.price,
    version = EXCLUDED.version
WHERE products.version < EXCLUDED.version;
~~~

Đây là SQL PostgreSQL minh họa **chỉ áp dụng version lớn hơn**, không ghi đè giá mới bằng dữ liệu cũ. Nhưng có một điều kiện quan trọng: nếu có **nhiều dòng cùng product_id và cùng source_version nhưng giá khác nhau**, thứ tự `ORDER BY product_id, source_version DESC` chưa chọn một kết quả nghiệp vụ xác định. Cần thêm nguồn ưu tiên/tie-breaker hoặc báo lỗi dữ liệu trùng mâu thuẫn **trước khi merge**.

Trong hệ thống thực còn phải kiểm tra quyền cập nhật giá, currency, khoảng giá, nguồn phát hành và quy tắc version. Bỏ qua hàng không hợp lệ bằng `WHERE price >= 0` chỉ là minh họa, không đủ thay thế báo cáo sai dữ liệu.

### 10.4. Bulk load không tự cho exactly-once

Nếu file được nhập lại, cần định danh lô như `import_id`, ràng buộc theo khóa nghiệp vụ và kết quả đã commit. Ngay cả khi `COPY` nhanh, nó không giải quyết:

- File bị gửi lại.
- Một lô commit thành công nhưng client mất kết nối trước khi nhận phản hồi.
- Một phần dữ liệu đã được merge ở chunk trước.
- Nhiều nguồn cập nhật cùng product với thứ tự khác nhau.
- Job crash sau khi merge nhưng trước khi ghi checkpoint.

Do đó bulk ingestion cần thiết kế **idempotency, checkpoint, reconciliation và cơ chế xác định nguồn dữ liệu có thẩm quyền** giống mọi đường persistence khác.

## 11. Gộp thao tác đọc: tránh N+1 và quá nhiều truy vấn nhỏ

Batching không chỉ có ý nghĩa cho ghi. Một service lấy 500 đơn rồi truy vấn khách hàng một lần cho từng đơn có thể phát sinh N+1 SELECT:

~~~text
1 SELECT tìm 500 orders.
500 SELECT riêng lấy customer của từng order.
~~~

Với yêu cầu chỉ cần tên khách hàng, có thể chọn một truy vấn JOIN/projection:

~~~sql
SELECT o.id, o.status, c.display_name
FROM orders AS o
JOIN customers AS c
  ON c.id = o.customer_id
WHERE o.created_at >= ?;
~~~

Nếu cần dữ liệu khách cho một tập ID có sẵn, có thể query theo nhóm:

~~~sql
SELECT id, display_name
FROM customers
WHERE id IN (?, ?, ?, ?);
~~~

Những dấu `?` là placeholder JDBC; khi số ID thay đổi cần xây số placeholder từ tập dữ liệu **được kiểm soát** và bind từng ID, không nối trực tiếp giá trị người dùng. Với tập rất lớn, cân nhắc bảng staging/temporary table, tham số mảng hỗ trợ theo driver hoặc kỹ thuật JOIN khác.

### 11.1. ORM batch fetching và fetch join có đánh đổi

Hibernate có cơ chế batch fetching cho lazy associations, giúp gom truy vấn lấy nhiều object cùng loại. Tuy nhiên:

- Batch fetching có thể giảm số SQL nhưng vẫn tải nhiều dữ liệu hơn API cần.
- Fetch join một collection có thể nhân số dòng trả về theo số phần tử con.
- Phân trang trên JOIN nhiều collection có thể làm số hàng cha/trang không như kỳ vọng.
- Một projection chỉ lấy vài cột đôi khi phù hợp hơn việc materialize cả object graph.

Chọn fetch plan **theo use case** rồi đo SQL và số row thật, thay vì đặt mọi quan hệ `EAGER`. N+1 là dấu hiệu cần thay cách truy cập dữ liệu, không phải lý do tăng batch size ghi.

### 11.2. Batch đọc có thể thay đổi độ mới dữ liệu

Nếu job đọc từng trang trong các transaction riêng, mỗi trang có thể thấy snapshot dữ liệu khác nhau tùy isolation và DBMS. Nếu báo cáo yêu cầu một ảnh chụp nhất quán toàn bộ, phải thiết kế transaction/snapshot phù hợp, chấp nhận chi phí giữ snapshot lâu hoặc dùng bản xuất dữ liệu có cơ chế nhất quán.

Đừng nhầm “đọc theo trang” với “đọc một snapshot”. Kỹ thuật chia trang giải quyết kích thước dữ liệu và memory, không tự tạo nhất quán theo thời điểm.

## 12. Chọn kích thước batch bằng dữ liệu đo

Không có con số cố định như “batch size 1.000 luôn tối ưu”. Kích thước phù hợp phụ thuộc:

- Độ trễ giữa ứng dụng và DB.
- Số cột/kiểu dữ liệu và số lượng bind parameters.
- Kích thước mỗi row hoặc payload LOB/JSON.
- Khả năng rewrite/gom lệnh của driver.
- Tải SQL, index, trigger, FK và WAL/redo.
- Giới hạn bộ nhớ của JVM và DBMS.
- Thời gian giữ transaction/khóa.
- Mức cạnh tranh của các service khác.
- Khả năng chịu lỗi và chi phí chạy lại một chunk.

### 12.1. Tách ba tham số cấu hình

Một job nhập 100.000 dòng có thể chọn:

~~~text
JDBC batch size = 200 statements / executeBatch
Transaction chunk size = 1.000 rows / COMMIT
Reader page size = 500 rows / page

Mỗi transaction:
  đọc/xử lý tới 1.000 rows
  gửi 5 JDBC batches x 200
  COMMIT một lần
  ghi checkpoint bền vững
~~~

Các số trên **chỉ là cấu hình để thử nghiệm**, không phải giá trị mặc định tối ưu. Nếu một nghiệp vụ yêu cầu toàn bộ 100.000 dòng cùng commit, chia thành transaction 1.000 hàng sẽ **thay đổi atomicity** và không thể tùy tiện sử dụng.

### 12.2. Giới hạn câu SQL và bind parameter

Với một multi-row INSERT có 12 cột và 2.000 hàng, có thể cần **24.000 giá trị bind**. Driver/DBMS có giới hạn số parameter, kích thước thông điệp hoặc câu SQL. Một số PostgreSQL driver/protocol có giới hạn đáng kể đối với số bind parameters; không nên sao chép một con số chung cho mọi phiên bản và mọi đường thực thi.

Lô quá lớn còn làm tăng:

- SQL parse/plan và memory cần thiết.
- Chi phí truyền một payload lớn khi mạng bất ổn.
- Thời gian giữ khóa và log giao dịch.
- Số thao tác phải thử lại khi một phần lỗi.
- Lượng dữ liệu có thể bị trùng hoặc cần đối soát sau commit mơ hồ.

Giới hạn **theo số hàng lẫn tổng byte**, đặc biệt với JSON, BLOB và văn bản lớn. Một batch 100 hàng chứa payload 2 MB mỗi hàng có thể nặng hơn batch 2.000 hàng nhỏ.

### 12.3. Phép đo đúng

Một thí nghiệm tối thiểu:

1. Chọn tập dữ liệu có phân bố tương tự production: số hàng, size, unique/FK và index.
2. Dùng cùng DBMS, driver, connection pool và cấu hình transaction.
3. Chạy các batch size như 1, 20, 100, 500 (giá trị chỉ để so sánh).
4. Giữ tương đương số hàng, concurrency và trạng thái database giữa các lần thử.
5. Đo throughput, thời gian hoàn tất, p95/p99, row/sec, lock wait, DB CPU/I/O/WAL và retry.
6. Kiểm tra **số SQL thực tế** và cơ chế driver rewrite nếu có.
7. Chọn vùng ổn định phù hợp SLA, không chỉ kết quả nhanh nhất của một lần chạy.

Một cấu hình nhanh ở tải một worker có thể quá tải khi 20 worker đồng thời chạy. Thử cả đỉnh concurrency và tác động lên truy vấn nghiệp vụ khác dùng chung DB.

### 12.4. Khi nào batch size lớn làm chậm hơn?

Có thể xảy ra nếu:

- DB đang chạm trần I/O hoặc CPU, batch lớn tạo burst tải.
- Một transaction giữ nhiều khóa, tăng lock waits/deadlock.
- SQL quá lớn làm parse/plan chậm.
- Nhiều batch cùng chạy gây cạnh tranh index hot pages.
- Driver/server phải phân bổ bộ nhớ lớn để giữ tham số và kết quả.
- Retry batch lớn làm nhiều công việc bị lặp sau một lỗi nhỏ.

Đường cong hiệu năng có thể tăng rồi chững hoặc giảm. **Đo ở điểm nghẽn thực**, không chỉ giảm số lần gọi Java method.

## 13. Batch job dài: checkpoint, partition và giới hạn transaction

Một job xuất/nhập hàng triệu dòng cần khả năng dừng, chạy tiếp và xử lý lỗi. Batch size của driver chỉ giải quyết một phần nhỏ của thiết kế này.

### 13.1. Keyset paging và chunk commit

Ví dụ đọc các ID cần xử lý:

~~~sql
SELECT id, status
FROM orders
WHERE id > ?
ORDER BY id
LIMIT ?;
~~~

Sau mỗi chunk, cập nhật trạng thái/đích và commit, rồi lưu mốc tiến độ đã hoàn tất theo một quy tắc an toàn. So với `OFFSET` trên bảng đang biến động, keyset paging thường ổn định hơn cho nhiều workload, nhưng vẫn cần xét:

- Có thể xuất hiện ID thấp sau checkpoint không?
- Các hàng cũ có thể thay đổi điều kiện lọc trong khi job chạy không?
- Mốc checkpoint được lưu trước hay sau transaction?
- Có thể chạy lại chunk mà không nhân đôi kết quả không?
- Cần catch-up/reconciliation cho hàng bị bỏ sót không?

Một checkpoint chỉ có ý nghĩa khi gắn với **công việc đã commit** hoặc cơ chế xử lý lặp được thiết kế có chủ đích. Nếu job ghi checkpoint trước khi dữ liệu đích commit, crash có thể làm mất việc.

### 13.2. Spring Batch và ý nghĩa chunk

Trong Spring Batch, một step có thể dùng `ItemReader` → `ItemProcessor` → `ItemWriter` và chính sách chunk với transaction manager, checkpoint và retry/skip được cấu hình.

Mô hình tư duy:

~~~text
read up to N items
    -> process
    -> write in batch
    -> commit chunk
    -> checkpoint state
    -> next chunk
~~~

**Chunk size** xác định phạm vi xử lý/commit theo cấu hình step, không tự nói JDBC driver sẽ gom SQL hiệu quả. `ItemWriter` cần được triển khai bằng đường JDBC/ORM có batching phù hợp nếu đây là mục tiêu.

Khi cho phép skip một hàng lỗi, cần xác định:

- Lỗi dữ liệu hay lỗi tạm thời?
- Có thể skip mà vẫn bảo vệ bất biến nghiệp vụ không?
- Dữ liệu đã ghi trong chunk được rollback hay không?
- Retry một chunk có sinh side effect ngoài DB lặp không?
- Có lưu audit và bản ghi bị cách ly để sửa sau không?

Không cấu hình retry vô hạn cho sự cố constraint hoặc sai schema. Với lỗi commit mơ hồ, cần đối soát bằng khóa nghiệp vụ trước khi chạy lại.

### 13.3. Nhiều worker xử lý hàng đợi DB

Nếu database cũng giữ bảng công việc, PostgreSQL `FOR UPDATE SKIP LOCKED` có thể giúp nhiều worker **claim** những hàng chưa bị khóa:

~~~sql
BEGIN;

WITH picked AS (
    SELECT id
    FROM import_jobs
    WHERE state = 'READY'
    ORDER BY priority DESC, id
    LIMIT 50
    FOR UPDATE SKIP LOCKED
)
UPDATE import_jobs AS j
SET state = 'CLAIMED',
    claimed_at = CURRENT_TIMESTAMP
FROM picked
WHERE j.id = picked.id
RETURNING j.id, j.payload;

COMMIT;
~~~

Đây là cơ chế claim minh họa, không phải job runner hoàn chỉnh. Sau khi commit, job đã được đánh dấu `CLAIMED` và worker có thể xử lý ngoài DB transaction, rồi ack theo token/lease thích hợp.

Cần thiết kế thêm:

- Lease timeout và cách reclaim job khi worker chết.
- Claim token/owner để ngăn worker cũ ack nhầm.
- Idempotency cho công việc được xử lý hai lần.
- Giới hạn concurrency và backpressure.
- Phát hiện job stuck, retry có backoff và dead-letter xử lý thủ công.
- Fairness: `SKIP LOCKED` không tự bảo đảm mỗi job sẽ được chọn kịp thời.

Không giữ transaction/connection đang khóa hàng trong suốt một tác vụ HTTP hoặc chuyển file kéo dài.

## 14. Batch, khóa và cạnh tranh giữa các giao dịch

Batch lớn có thể giảm lượt đi mạng nhưng cũng khiến nhiều hàng được ghi trong một transaction và giữ khóa lâu hơn.

### 14.1. Deadlock khi nhiều lô cập nhật các hàng theo thứ tự khác nhau

~~~text
T1: UPDATE product 1 -> giữ lock 1
T2: UPDATE product 2 -> giữ lock 2
T1: UPDATE product 2 -> chờ lock 2
T2: UPDATE product 1 -> chờ lock 1

=> Vòng chờ, DBMS có thể phát hiện deadlock và hủy một transaction.
~~~

Giảm rủi ro bằng cách:

- Thống nhất thứ tự cập nhật theo khóa, ví dụ `ORDER BY product_id` trong bộ dữ liệu ứng dụng trước khi gửi từng UPDATE.
- Giữ transaction ngắn và tránh gọi network bên ngoài khi đang giữ connection/khóa.
- Thiết kế chỉ mục giúp câu SQL tìm đúng hàng thay vì quét nhiều dữ liệu.
- Retry **toàn transaction bị hủy** với giới hạn và backoff nếu nghiệp vụ cho phép.
- Giới hạn số worker đồng thời trên cùng tập khóa nóng.

Cần lưu ý: sắp xếp dữ liệu đầu vào không bảo đảm engine luôn khóa theo một thứ tự đã đoán trước khi dùng một bulk SQL phức tạp. Kiểm tra SQL plan và cách khóa thật theo DBMS.

### 14.2. Một bảng có index đắt hơn bảng trống

Mỗi INSERT/UPDATE phải duy trì các index liên quan và kiểm tra constraint. Bulk ingest vào bảng có nhiều index lớn có thể tốn CPU/I/O đáng kể. Với một lần nạp lịch sử vào bảng riêng, đôi khi có thể:

1. Bulk load dữ liệu vào staging hoặc bảng đích mới.
2. Validate và loại trùng.
3. Tạo các index cần thiết theo quy trình có kiểm soát.
4. Chuyển giao đường đọc khi dữ liệu đã sẵn sàng.

Không được tùy tiện tắt/bỏ unique, foreign key hoặc audit của bảng production để lấy tốc độ nếu điều đó cho phép ghi dữ liệu sai. Những tối ưu dạng “nạp trước, tạo index sau” phù hợp hơn cho đường nhập được cô lập và có bước kiểm chứng.

### 14.3. Giữ ngân sách connection trên toàn hệ thống

Một job có 20 worker, mỗi worker giữ một connection trong nhiều giây, sẽ tranh tài nguyên với HTTP service. Nếu mỗi application replica còn có pool riêng, tổng connection có thể chạm giới hạn DB. Batch job cần:

- Giới hạn concurrency riêng.
- Pool/cấu hình kết nối phù hợp ngân sách DB toàn hệ thống.
- Giới hạn transaction duration và statement timeout thích hợp.
- Theo dõi active/idle/pending ở pool và CPU/I/O/lock wait tại DB.
- Cơ chế giảm tải hoặc hoãn khi hệ thống sản xuất có đỉnh traffic.

“Gộp giúp ít lượt đi mạng” không có nghĩa có thể tăng vô hạn số worker chạy song song.

## 15. Idempotency, retry và kết quả commit không chắc chắn

Batch processing thường gặp tình huống **đã làm một phần công việc nhưng caller không nhận được xác nhận**.

### 15.1. Lỗi giữa các chunk đã commit

Giả sử job gồm ba chunk 1.000 hàng:

~~~text
Chunk 1: COMMIT success
Chunk 2: COMMIT success
Chunk 3: fail, rollback

Trạng thái đích:
  2.000 hàng đầu đã commit.
  Chunk 3 chưa hoàn thành.
~~~

Retry toàn job không thể tự coi là “chưa có gì xảy ra”. Cần checkpoint và thiết kế thao tác có thể chạy lại, ví dụ unique trên `(import_id, source_row_id)` hoặc khóa nghiệp vụ phù hợp.

### 15.2. Mất kết nối quanh COMMIT

Nếu ứng dụng gửi `COMMIT` nhưng mạng đứt trước khi nhận phản hồi, database **có thể đã commit hoặc chưa**. Việc gọi rollback hoặc nhận `SQLException` về network không chứng minh kết quả đã bị đảo.

Với dữ liệu nhạy cảm như chuyển tiền, tồn kho và thanh toán, phải có:

- Operation/import ID ổn định.
- Ràng buộc unique hoặc ledger ghi nhận lệnh đã xử lý.
- Khả năng kiểm tra trạng thái transaction ở cấp nghiệp vụ trên connection mới.
- Quy tắc trả cùng kết quả cho request lặp khi hợp đồng cho phép.
- Retry có giới hạn, không làm lặp side effect như gửi email/thu tiền.

### 15.3. `ON CONFLICT DO NOTHING` không giải quyết mọi chuyện

Ví dụ:

~~~sql
INSERT INTO inventory_adjustments (
    adjustment_id, sku, delta
) VALUES (?, ?, ?)
ON CONFLICT (adjustment_id) DO NOTHING;
~~~

Unique `adjustment_id` có thể ngăn cùng lệnh được insert hai lần. Nhưng nếu request lặp dùng cùng ID với **nội dung khác**, `DO NOTHING` có thể che một xung đột nghiêm trọng. Cần so sánh payload/fingerprint hoặc lưu kết quả xử lý ban đầu để từ chối lệnh mâu thuẫn.

Nếu một lần insert adjustment kéo theo UPDATE inventory, cả hai phải nằm trong **cùng transaction** và được điều phối qua operation ID; không chỉ insert adjustment idempotent còn phép cộng tồn kho chạy lại ngoài transaction.

### 15.4. Phân biệt lỗi đáng retry và lỗi dữ liệu

| Lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Retry candidate | Deadlock, serialization failure | Rollback và retry toàn transaction nếu idempotent |
| Tạm thời từ hạ tầng | DB ngắn hạn không sẵn sàng, pool timeout | Điều tra tình trạng DB, retry có backoff/budget |
| Không hợp lệ | Negative quantity, sai field, kiểu không parse | Cách ly bản ghi, không retry y nguyên |
| Constraint violation | Duplicate business key/FK | Xử lý theo ngữ nghĩa; không retry mù |
| COMMIT không chắc chắn | Network đứt sau khi gửi COMMIT | Đối soát/operation ID trước khi gửi lại |
| Bị hủy do timeout | Query timeout hoặc lock wait timeout | Xác định điểm nghẽn và trạng thái transaction |

SQLSTATE/vendor code và chuỗi `SQLException.getNextException()` giúp điều tra, nhưng quyết định retry phải thêm **ngữ nghĩa nghiệp vụ và thời điểm xảy ra lỗi**.

## 16. Quan sát và benchmark: bằng chứng batch thật sự có lợi

Một hệ thống có batching tốt cần nhìn thấy cả hoạt động của ứng dụng, driver và DB.

| Metric | Dùng để đánh giá |
|---|---|
| Rows processed / second | Thông lượng thực |
| Rows per JDBC batch, batches per transaction | Cấu hình có được áp dụng hay không |
| `executeBatch()` duration p50/p95/p99 | Độ trễ gửi lệnh |
| Transaction commit/rollback duration | Chi phí giao dịch và log |
| SQL statement count / DB round trips | Có giảm số lượt thực thi/đi-về thật không |
| Update counts / rejected rows | Khả năng xử lý thành công, lỗi dữ liệu |
| Batch/transaction retry rate | Lãng phí công việc và mức tranh chấp |
| Connection pool active/pending | Có cạn pool vì giữ transaction lâu không |
| DB CPU, I/O, WAL/redo, replication lag | DB có bị quá tải không |
| Row/table locks, deadlocks | Batch có tăng tranh chấp không |
| JVM heap/GC pressure | Buffer batch và persistence context có gây memory pressure không |
| Backlog/oldest chunk age | Job có đang bắt kịp tốc độ sinh dữ liệu không |

### 16.1. Kiểm tra driver có thực sự gộp lệnh

Cấu hình batching không đủ bằng chứng. Có thể:

- Bật logging/statistics có kiểm soát ở ORM/driver.
- Dùng metric về số SQL và thời gian thực thi.
- Kiểm tra statement/query log phù hợp trên DBMS.
- So sánh `rows/sec` cùng số lượt đi-về giữa các cấu hình.
- Quan sát JDBC metadata và phiên bản driver.
- Kiểm tra tác động của ID strategy, `RETURNING` và flush ordering.

Cẩn thận: log từ ORM có thể in **một SQL template cho nhiều lần bind**, hoặc ngược lại log nhiều thao tác dù driver rewrite trước khi gửi. Cần hiểu log đang quan sát tầng nào.

### 16.2. Benchmark đúng điều kiện

Một benchmark có ý nghĩa phải kiểm soát:

1. **Cùng dữ liệu:** số hàng, kích thước payload, phân bố unique/FK, trạng thái index.
2. **Cùng DB:** DBMS/version, driver, connection pool, cấu hình transaction.
3. **Cùng tải:** số worker, p95/p99 của truy vấn nghiệp vụ khác cùng DB.
4. **Cùng semantics:** batch size thay đổi nhưng bất biến và mức atomicity không bị thay đổi âm thầm.
5. **Cùng số lần thử:** lỗi, retry, cleanup staging/checkpoint được tính vào tổng thời gian.
6. **Đủ số lần đo:** làm nóng hệ thống, tránh một phép thử tình cờ nhanh do cache hoặc khác biệt dữ liệu.

Nếu tăng batch từ 100 lên 500 giảm thời gian job 10% nhưng đẩy p99 của checkout tăng gấp đôi, đó có thể là **tối ưu cục bộ không phù hợp hệ thống**.

## 17. Kiểm thử correctness và failure injection

Batch processing là nơi một bài test “ghi đủ N dòng khi mọi thứ thành công” không đủ phát hiện lỗi. Các ca cần ưu tiên:

### 17.1. Kiểm thử tầng JDBC

- Đối chiếu `addBatch()`/`executeBatch()` với dữ liệu được ghi thật.
- Kiểm tra batch cuối có ít hơn `BATCH_SIZE` vẫn được thực thi.
- Kiểm tra không gửi một batch cũ thêm lần nữa ngoài ý muốn.
- Thử `BatchUpdateException` và các dạng `updateCounts` mà driver hỗ trợ.
- Kiểm tra `SUCCESS_NO_INFO`, `EXECUTE_FAILED` và count bất thường.
- Kiểm tra `getGeneratedKeys` nếu bài toán cần ánh xạ ID.
- Đảm bảo connection/statement đóng và transaction rollback khi lỗi.

### 17.2. Kiểm thử transaction và chunk

| Trường hợp | Kết quả kỳ vọng |
|---|---|
| 437 dòng trong một transaction, nhiều JDBC batch | Tất cả commit hoặc rollback cùng nhau |
| Chunk 1 commit, chunk 2 lỗi | Chunk 1 còn; chunk 2 rollback |
| Lỗi unique ở giữa batch | Không báo success sai; transaction được xử lý đúng |
| Worker dừng sau commit, trước checkpoint | Chạy lại không nhân đôi dữ liệu |
| Hai worker claim cùng thời điểm | Không xử lý trùng ngoài hợp đồng |
| Mất mạng khi commit | Đối soát kết quả trước retry |
| Lỗi ở `close()`/`rollback()` | Giữ nguyên cause chính và lỗi cleanup phụ |
| Payload lớn vượt giới hạn | Batch được tách/điều tiết; không OOM |
| Nhiều worker cùng đụng khóa nóng | Có giới hạn/retry khi deadlock |
| Hibernate entity dùng IDENTITY | Cấu hình batch thực tế được đo, không chỉ giả định |
| Import staging có row trùng cùng version | Phát hiện xung đột thay vì chọn tùy ý |

Không chỉ mock `PreparedStatement.executeBatch()`. Nên có integration test với DBMS/driver thực tế để quan sát rollback, constraint, generated key, lock và cú pháp bulk load.

### 17.3. Kiểm thử race với hai session

Ví dụ hai job cùng cập nhật hai product theo thứ tự trái nhau:

~~~text
T1: UPDATE product 1; giữ transaction
T2: UPDATE product 2; giữ transaction
T1: UPDATE product 2; chờ
T2: UPDATE product 1; chờ

Kỳ vọng:
  DB phát hiện deadlock hoặc có chính sách timeout phù hợp;
  transaction bị hủy rollback toàn bộ;
  application không ghi nhận chunk đã hoàn tất;
  retry (nếu được phép) bắt đầu với transaction mới.
~~~

Tình huống này giúp kiểm chứng **cách xử lý lỗi và thứ tự khóa**, không chỉ hiệu năng không tải.

## 18. Những sai lầm thường gặp

| Sai lầm | Tại sao sai | Cách sửa |
|---|---|---|
| “Gọi `saveAll` là đã batch” | ORM có thể phát SQL từng hàng | Kiểm tra flush, ID strategy, driver và SQL thực |
| Batch size = transaction size | Hai phạm vi độc lập | Thiết kế và cấu hình riêng |
| Một transaction cho toàn job hàng triệu hàng | Khóa/log lâu, khó restart | Commit theo chunk nếu nghiệp vụ cho phép |
| `autoCommit=true` nhưng mong rollback cả batch | Một phần có thể đã commit | Quản lý transaction rõ ràng |
| Tin `updateCounts` là đã bền vững | Count trước commit không chứng minh commit | Theo dõi kết quả transaction |
| Retry nguyên job sau mọi exception | Lặp các chunk đã commit và side effect | Checkpoint, idempotency, đối soát |
| Batch rất lớn chỉ vì ít round-trip | Vượt limit/memory và tăng lock | Giới hạn rows/bytes/time, benchmark |
| Dùng vòng Java cập nhật từng row dù có SQL set-based | Thêm round-trip và work không cần | Chọn set-based SQL nếu đúng ngữ nghĩa |
| Dùng `COPY` trực tiếp vào bảng chính với dữ liệu bẩn | Lỗi constraint/mapping và khó xử lý riêng | Staging, validate, deduplicate, merge |
| Bỏ qua duplicate/stale version | Dữ liệu cũ ghi đè mới | Unique business key và conditional version |
| Flush nhưng không clear ORM trong job lớn | Persistence context phình to | Flush/clear có kiểm soát |
| Clear ORM tùy tiện giữa nghiệp vụ | Mất managed state/dirty checking | Chọn đúng transaction và entity lifecycle |
| Tăng worker vô hạn | DB/pool quá tải dù mỗi batch nhanh | Giới hạn concurrency, backpressure |
| Chỉ đo thời gian job | Che tác động lên API khác | Đo hệ thống và DB p95/p99 |
| Gộp mọi SELECT bằng cách tải cả object graph | Tải dư và JOIN phình to | DTO projection, query theo tập |
| Coi batch luôn hoạt động giống nhau trên DBMS | Driver, protocol, DDL/SQL khác nhau | Xác minh khả năng công nghệ thực tế |

## 19. Bài tập vận dụng

### Bài 1. Gộp và transaction có giống nhau không?

Một service gọi `executeBatch()` năm lần, mỗi lần 200 hàng, với `autoCommit=false` và chỉ một `commit()` ở cuối. Nếu batch cuối lỗi và service rollback, bốn batch đầu có còn dữ liệu không?

**Gợi ý:** Trong transaction DB hỗ trợ rollback, bốn batch trước thuộc cùng transaction và bị rollback cùng batch cuối. “Đã gửi lên DB” chưa phải “đã commit”.

### Bài 2. `SUCCESS_NO_INFO` có phải lỗi?

`executeBatch()` trả `[1, -2, 1]`. Có nên xem dòng thứ hai thất bại không?

**Gợi ý:** Không. `-2 = Statement.SUCCESS_NO_INFO` biểu thị lệnh thành công nhưng không có update count chính xác; `-3` mới là `EXECUTE_FAILED` theo JDBC.

### Bài 3. Tính overhead mạng

Giả sử có 3.000 câu INSERT, chi phí RTT 3 ms mỗi lượt và chưa tính mọi chi phí khác. Nếu phương án mới thực sự giảm xuống 30 lượt, phần chi phí RTT thay đổi thế nào?

**Gợi ý:** Mô hình lý tưởng: `3.000 × 3 = 9.000 ms` so với `30 × 3 = 90 ms`. Đây **không** phải tổng latency đã đo; cần quan sát DB và driver để xác thực.

### Bài 4. `saveAll` nhưng vẫn chậm

Hibernate có `hibernate.jdbc.batch_size=50` nhưng SQL log vẫn cho thấy nhiều INSERT riêng; entity dùng `GenerationType.IDENTITY`. Cần điều tra gì?

**Gợi ý:** Cách lấy generated ID có thể cản batching INSERT. Kiểm tra ID strategy, provider/version, generated keys, driver và SQL thực tế, không chỉ tăng batch size.

### Bài 5. Bật `autoCommit=true`

Một job JDBC batch 500 hàng, có constraint violation ở hàng 301. Có chắc 300 hàng trước được rollback không?

**Gợi ý:** Không. Không có transaction được quản lý rõ, tùy driver/DBMS một số thao tác có thể đã commit. Cần dùng transaction đúng phạm vi và xử lý `BatchUpdateException`.

### Bài 6. Chọn SQL theo tập

Một service đọc mọi ID session hết hạn rồi chạy từng UPDATE qua Java. Có thể cải thiện bằng cách nào?

**Gợi ý:** Nếu nghiệp vụ cho phép tác động tất cả session theo điều kiện, dùng một `UPDATE ... WHERE state = 'ACTIVE' AND expires_at < ...` và chỉ mục phù hợp. Nếu cần giới hạn phạm vi hoặc lock duration, chia chunk.

### Bài 7. Import lớn có nhiều dòng lỗi

CSV có 1 triệu dòng, trong đó vài nghìn sản phẩm sai mã hoặc trùng version. Có nên `COPY` thẳng vào bảng sản phẩm production không?

**Gợi ý:** Cân nhắc nạp staging, validate, deduplicate, ghi bảng lỗi và merge set-based với version/idempotency. `COPY` tăng tốc nạp nhưng không quyết định cách xử lý dữ liệu sai.

### Bài 8. Chọn batch size

Với batch 100, job đạt 30.000 rows/s và checkout p99 ổn. Với batch 2.000, job đạt 33.000 rows/s nhưng checkout p99 tăng mạnh và replica lag kéo dài. Phương án nào phù hợp?

**Gợi ý:** Không chọn theo throughput job đơn thuần. Cân nhắc SLA ứng dụng, DB contention, áp lực I/O/log và điều chỉnh concurrency/kích thước lô.

### Bài 9. Job crash sau commit

Chunk đã commit thành công nhưng worker chết trước khi cập nhật checkpoint ở một hệ thống khác. Khi chạy lại, làm sao tránh chèn trùng?

**Gợi ý:** Unique business key/operation ID, idempotent write hoặc kiểm tra trạng thái đã commit. Checkpoint và ghi dữ liệu cần được điều phối đúng; không thể mặc định có transaction chung hai hệ thống.

### Bài 10. N+1 là vấn đề batch nào?

Một API tải 200 đơn, sau đó chạy 200 `SELECT` lấy khách hàng. Có nhất thiết tăng `hibernate.jdbc.batch_size` không?

**Gợi ý:** Không. Đây là bài toán đọc/fetch, cần JOIN/DTO projection, batch fetching hoặc một truy vấn theo tập. Cấu hình JDBC **write batching** không tự sửa N+1 SELECT.

### Bài 11. Chờ khóa và deadlock

Hai worker update hai bản ghi theo thứ tự trái nhau. Mỗi worker gửi batch lớn. Vì sao có thể xảy ra deadlock và cần xử lý ra sao?

**Gợi ý:** Hai transaction giữ khóa vòng chờ. Có thể thống nhất thứ tự khóa, giảm thời gian giao dịch, giới hạn concurrency; khi DB hủy transaction, rollback và retry **toàn transaction** nếu nghiệp vụ cho phép.

### Bài 12. Tốc độ và tính đúng đắn

Một lệnh import upsert giá sản phẩm theo `source_version` nhưng staging có hai bản ghi cùng product/version khác giá. Có an toàn nếu chọn tùy một hàng để tránh lỗi?

**Gợi ý:** Không. Phải phát hiện xung đột và xác định quy tắc chọn nguồn/tie-breaker dựa trên nghiệp vụ, thay vì dùng lệnh SQL tạo kết quả ngẫu nhiên.

## 20. Ghi nhớ

- **Gộp lệnh có nhiều cấp độ.** JDBC batch, multi-row SQL, set-based query, COPY và batch job là những lựa chọn khác nhau về giao thức, transaction và xử lý lỗi.
- **Khả năng của công nghệ quyết định tối ưu thực tế.** Driver có thể rewrite SQL hoặc không; ORM có thể bị giới hạn bởi IDENTITY, generated keys và lifecycle entity.
- **Đừng nhầm batch với commit.** Một transaction có thể chứa nhiều batch; một job có thể chứa nhiều transaction. Ranh giới phải xuất phát từ bất biến nghiệp vụ.
- **Lỗi batch có thể là lỗi từng phần.** Giữ `BatchUpdateException`, đọc update counts đúng, rollback khi cần, đối soát kết quả commit mơ hồ và không retry mù.
- **Chọn set-based SQL trước khi viết vòng lặp** nếu thao tác và ràng buộc nghiệp vụ phù hợp. Dùng staging/`COPY` cho dữ liệu nhập lớn cần làm sạch.
- **Batch size không càng lớn càng tốt.** Giới hạn bởi tham số, payload, memory, lock, WAL, concurrency và độ trễ của các service khác.
- **Batch job cần restartability.** Chunk, idempotency, checkpoint, lease và retry có giới hạn giúp khôi phục sau lỗi mà không nhân đôi dữ liệu.
- **Đo từ Java tới DBMS.** Xác minh số SQL/round-trip thật, throughput, p95/p99, pool saturation, lock wait và tính đúng đắn dưới tải.

Gộp lệnh và xử lý theo lô là công cụ tăng hiệu năng quan trọng trong lớp persistence Java, nhưng hiệu quả đến từ **việc chọn đúng cấp độ gộp cho đúng công nghệ và giữ nguyên hợp đồng dữ liệu**. Thiết kế tốt không chỉ chạy nhanh hơn khi mọi thứ thành công; nó còn giữ được transaction, không mất cập nhật, phục hồi được sau lỗi và không đẩy chi phí sang những tác vụ khác của cơ sở dữ liệu.


