# Đọc nhiều `ResultSet` và số dòng cập nhật từ thủ tục trong JDBC

Một thủ tục lưu trữ (*stored procedure*) có thể làm nhiều việc trong một lần gọi: cập nhật trạng thái đơn hàng, trả bảng thông tin đơn hàng, cập nhật các dòng hàng và trả thêm một bảng chi tiết. Khi thực thi thủ tục đó, JDBC có thể nhận được **nhiều kết quả liên tiếp**: `ResultSet` từ `SELECT`, **update count** từ `INSERT`/`UPDATE`/`DELETE`, hoặc không có kết quả nào nữa. Nếu chỉ gọi `CallableStatement.executeQuery()` và đọc bảng đầu tiên, ứng dụng có nguy cơ bỏ qua các kết quả còn lại.

Trong module **JDBC**, chương **Thủ tục lưu trữ**, bài này hướng dẫn dùng `CallableStatement.execute()`, `getResultSet()`, `getUpdateCount()` và `getMoreResults()` để duyệt **toàn bộ luồng kết quả**. Ta sẽ dựng ví dụ về đơn hàng với hai `SELECT` xen giữa hai `UPDATE`, đọc giá trị qua `ResultSet`, quản lý transaction bằng `Connection`, và xử lý khác biệt giữa cơ sở dữ liệu và JDBC driver bằng các API chuẩn.

Sau bài học, bạn có thể:

- Phân biệt một bảng kết quả `ResultSet` với **số hàng bị tác động** của một lệnh SQL.
- Viết vòng lặp đọc kết quả hỗn hợp, kể cả khi `execute()` hoặc `getMoreResults()` trả `false`.
- Đóng từng `ResultSet` đúng lúc, không đọc tiếp sau khi con trỏ đã bị đóng.
- Ánh xạ các bảng kết quả khác cấu trúc thành những đối tượng Java khác nhau.
- Chọn chính sách transaction và xử lý update count, OUT parameter, lỗi driver và kết quả không như mong đợi.

## 1. Vì sao một lần gọi thủ tục có nhiều kết quả?

Giả sử ứng dụng quản lý đơn hàng cần thực hiện công việc sau:

1. Đổi trạng thái của một đơn thành `REVIEWED`.
2. Trả thông tin đơn hàng vừa xem xét.
3. Đánh dấu các dòng hàng là đã xem xét.
4. Trả danh sách dòng hàng sau cập nhật.

Thủ tục có thể thực thi một chuỗi lệnh SQL theo thứ tự:

```text
CALL review_order(101)
        |
        +-- UPDATE purchase_order        -> update count
        |
        +-- SELECT purchase_order        -> ResultSet #1
        |
        +-- UPDATE order_item            -> update count
        |
        +-- SELECT order_item            -> ResultSet #2
        |
        +-- Kết thúc thủ tục             -> không còn kết quả
```

**Update count** là số hàng mà driver báo bị tác động bởi một câu lệnh cập nhật, không phải một `ResultSet` có cột `count`. Ví dụ, `UPDATE ... WHERE order_id = 101` có thể tác động một hàng, còn `UPDATE order_item ... WHERE order_id = 101` có thể tác động ba hàng. Ngược lại, `SELECT ...` tạo một `ResultSet` dù truy vấn trả **0 hàng**. Không suy ra số lượng hàng trong `SELECT` từ update count của một câu lệnh khác.

Trong luồng trên, ứng dụng có thể nhận kết quả theo trình tự `1 → ResultSet #1 → 3 → ResultSet #2`. Đây chỉ là **trình tự minh họa**; việc driver có phát mọi update count hay không, có thêm count từ trigger hay không, và cách thực hiện stored procedure phụ thuộc DBMS, phiên bản driver và cấu hình. Vì thế, mã đọc cần nhận diện **loại của từng kết quả** thay vì giả định vị trí thứ hai luôn là bảng dữ liệu.

## 2. Bốn API quyết định cách duyệt kết quả

`CallableStatement` kế thừa các khả năng của `PreparedStatement` và `Statement`, do đó có những phương thức sau:

| API | Giá trị hoặc tác dụng | Cách dùng đúng |
| --- | --- | --- |
| `boolean execute()` | Thực thi thủ tục; `true` nếu kết quả đầu tiên là `ResultSet`, `false` nếu là update count hoặc chưa có kết quả | Gọi **một lần** để bắt đầu luồng kết quả |
| `ResultSet getResultSet()` | Lấy `ResultSet` hiện tại khi kết quả hiện tại là bảng dữ liệu | Chỉ đọc khi trạng thái hiện tại là `ResultSet` |
| `int getUpdateCount()` | Lấy số hàng bị tác động của kết quả hiện tại; `-1` nếu kết quả hiện tại không phải update count | Phân biệt `0` (có count hợp lệ) với `-1` (không phải count) |
| `boolean getMoreResults()` | Tiến tới kết quả tiếp theo; trả `true` nếu kết quả tiếp theo là `ResultSet`, `false` nếu là update count **hoặc** không còn kết quả | Sau khi gọi, kiểm tra `getUpdateCount()` nếu nhận `false` |

Điểm dễ nhầm nhất là **`false` có hai ý nghĩa**. Với cả `execute()` và `getMoreResults()`, `false` không đủ để kết luận rằng thủ tục đã hết kết quả: có thể kết quả hiện tại là số dòng cập nhật hợp lệ.

Quy tắc xác định trạng thái:

| Cờ kết quả hiện tại | `getUpdateCount()` | Diễn giải |
| --- | --- | --- |
| `true` | Không cần gọi | Kết quả hiện tại là `ResultSet`; đọc bằng `getResultSet()` |
| `false` | `0` hoặc số nguyên không âm | Kết quả hiện tại là update count; ghi nhận kể cả `0` |
| `false` | `-1` | Không còn kết quả của lần thực thi hiện tại |

**Không dùng `while (statement.getMoreResults())` làm vòng lặp duy nhất**. Cách đó sẽ dừng ngay khi gặp một update count, bỏ qua mọi `ResultSet` xuất hiện phía sau.

### Vòng lặp JDBC chuẩn cho kết quả hỗn hợp

```java
boolean isResultSet = call.execute();

while (true) {
    if (isResultSet) {
        try (ResultSet rs = call.getResultSet()) {
            while (rs.next()) {
                // Xử lý từng hàng của ResultSet hiện tại.
            }
        }
    } else {
        int count = call.getUpdateCount();
        if (count == -1) {
            break; // Chỉ lúc này mới biết không còn kết quả.
        }
        // Ghi nhận update count, kể cả count == 0.
    }

    isResultSet = call.getMoreResults();
}
```

Ở đây `call` là `CallableStatement` đã chuẩn bị với cú pháp gọi thủ tục và tham số hợp lệ. Vòng lặp không gọi `next()` trên `CallableStatement`; `next()` thuộc `ResultSet`. Chỉ khi đang xử lý `ResultSet` mới gọi `rs.next()` để chuyển tới từng hàng. **Cứ sau mỗi kết quả hiện tại**, `getMoreResults()` mới chuyển sang kết quả kế tiếp.

## 3. Tạo thủ tục ví dụ có hai bảng kết quả và update count

Vì cách viết thủ tục không được chuẩn hóa hoàn toàn giữa các DBMS, phần SQL dưới đây dùng **T-SQL của Microsoft SQL Server** làm ví dụ chạy thực tế. Phần Java gọi qua JDBC vẫn minh họa API chung; khi dùng PostgreSQL, MySQL, Oracle hoặc hệ quản trị khác, hãy thay định nghĩa thủ tục, cú pháp gọi và cách trả bảng kết quả cho đúng sản phẩm.

Tạo hai bảng:

```sql
-- Ví dụ T-SQL trên SQL Server.
CREATE TABLE dbo.purchase_order (
    order_id     BIGINT NOT NULL PRIMARY KEY,
    order_status VARCHAR(20) NOT NULL
);

CREATE TABLE dbo.order_item (
    order_id   BIGINT NOT NULL,
    line_no    INT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity   INT NOT NULL CHECK (quantity > 0),
    reviewed   BIT NOT NULL DEFAULT 0,
    PRIMARY KEY (order_id, line_no),
    FOREIGN KEY (order_id) REFERENCES dbo.purchase_order(order_id)
);
```

Giả sử môi trường kiểm thử đã thêm dữ liệu ban đầu:

```sql
INSERT INTO dbo.purchase_order (order_id, order_status)
VALUES (101, 'NEW');

INSERT INTO dbo.order_item
    (order_id, line_no, product_id, quantity, reviewed)
VALUES
    (101, 1, 501, 2, 0),
    (101, 2, 502, 1, 0),
    (101, 3, 503, 4, 0);
```

Định nghĩa thủ tục, chạy dưới dạng **một batch tạo thủ tục riêng** trên SQL Server (trong công cụ SSMS/sqlcmd có thể dùng `GO` để chia batch; `GO` không phải câu SQL gửi nguyên văn qua JDBC):

```sql
CREATE OR ALTER PROCEDURE dbo.usp_review_order
    @order_id BIGINT
AS
BEGIN
    -- SQL Server: cho phép gửi thông báo số hàng tác động.
    SET NOCOUNT OFF;

    UPDATE dbo.purchase_order
    SET order_status = 'REVIEWED'
    WHERE order_id = @order_id;

    SELECT order_id, order_status
    FROM dbo.purchase_order
    WHERE order_id = @order_id;

    UPDATE dbo.order_item
    SET reviewed = 1
    WHERE order_id = @order_id;

    SELECT line_no, product_id, quantity, reviewed
    FROM dbo.order_item
    WHERE order_id = @order_id
    ORDER BY line_no;
END;
```

Thủ tục không khai báo `OUT` parameter và không tự `COMMIT` hoặc `ROLLBACK`; ví dụ Java sẽ sở hữu transaction. Nó luôn thực hiện hai câu `SELECT` theo thứ tự cố định. Nếu `order_id` không tồn tại, mỗi `SELECT` vẫn là một bảng kết quả **rỗng**; đây không phải tình huống “thủ tục không trả `ResultSet`”.

### Vai trò của `SET NOCOUNT` và driver SQL Server

Trong SQL Server, `SET NOCOUNT ON` thường được dùng để **không gửi thông báo số hàng tác động** của các câu DML trong thủ tục. Ở ví dụ này dùng `SET NOCOUNT OFF` để minh họa update count xen kẽ các bảng. Tuy nhiên, JDBC driver có thể có chính sách khác đối với thông báo số hàng từ stored procedure, trigger hoặc nhiều lệnh cập nhật (chẳng hạn các tùy chọn về việc trả count cuối cùng). **Đừng xem `[1, 3]` là một cam kết độc lập với driver** chỉ vì thủ tục có hai `UPDATE`. Hãy kiểm tra phiên bản driver, cấu hình trả update count và thực hiện integration test.

Một số DBMS còn không cung cấp update count theo đúng luồng “mỗi lệnh DML trong procedure → một count” như SQL Server. Mã Java nên đọc những update count thực tế được driver công bố, còn nghiệp vụ cần **số hàng chính xác và ổn định** có thể phải yêu cầu thủ tục trả số đếm qua `OUT` parameter hoặc một bảng `SELECT` chuyên biệt.

## 4. Ví dụ Java đầy đủ: đọc hai `ResultSet` và mọi update count

Đoạn mã sau dùng Java 17 trở lên (để có `record`). Nó bao bọc lần gọi trong **một transaction**, đọc lần lượt hai bảng và lưu các update count phát hiện được. Nếu gặp lỗi JDBC, lỗi ánh xạ, thiếu bảng kết quả hoặc không thấy đơn hàng, ứng dụng cố gắng `rollback()`.

```java
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import javax.sql.DataSource;

public final class OrderProcedureRepository {
    public record OrderSummary(long orderId, String status) {
        public OrderSummary {
            Objects.requireNonNull(status, "status");
        }
    }

    public record ItemSummary(
            int lineNo, long productId, int quantity, boolean reviewed) {}

    public record ReviewResult(
            OrderSummary order,
            List<ItemSummary> items,
            List<Integer> updateCounts) {
        public ReviewResult {
            Objects.requireNonNull(order, "order");
            items = List.copyOf(Objects.requireNonNull(items, "items"));
            updateCounts = List.copyOf(
                    Objects.requireNonNull(updateCounts, "updateCounts"));
        }
    }

    private final DataSource dataSource;

    public OrderProcedureRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource, "dataSource");
    }

    public ReviewResult reviewOrder(long orderId) throws SQLException {
        if (orderId <= 0) {
            throw new IllegalArgumentException("orderId must be positive");
        }

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                ReviewResult report;
                try (CallableStatement call = connection.prepareCall(
                        "{call dbo.usp_review_order(?)}")) {
                    call.setLong(1, orderId);
                    report = readAllResults(call);
                }

                // Chỉ xác nhận thay đổi khi toàn bộ luồng đã được đọc hợp lệ.
                connection.commit();
                return report;
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

    private static ReviewResult readAllResults(CallableStatement call)
            throws SQLException {
        boolean isResultSet = call.execute();
        int resultSetIndex = 0;
        OrderSummary order = null;
        List<ItemSummary> items = new ArrayList<>();
        List<Integer> counts = new ArrayList<>();

        while (true) {
            if (isResultSet) {
                resultSetIndex++;
                try (ResultSet rs = call.getResultSet()) {
                    if (rs == null) {
                        throw new SQLException("Expected a ResultSet");
                    }

                    if (resultSetIndex == 1) {
                        order = readOrder(rs);
                    } else if (resultSetIndex == 2) {
                        items = readItems(rs);
                    } else {
                        throw new SQLException(
                                "Unexpected ResultSet #" + resultSetIndex);
                    }
                }
            } else {
                int updated = call.getUpdateCount();
                if (updated == -1) {
                    break; // Không còn ResultSet hoặc update count.
                }
                counts.add(updated); // 0 cũng là count hợp lệ.
            }

            // false có thể biểu thị update count kế tiếp, chưa chắc đã hết.
            isResultSet = call.getMoreResults();
        }

        if (resultSetIndex != 2) {
            throw new SQLException(
                    "Expected two ResultSets, got " + resultSetIndex);
        }
        if (order == null) {
            throw new SQLException("Order not found");
        }

        // counts chỉ chứa những update count driver thực sự báo.
        return new ReviewResult(order, items, counts);
    }

    private static OrderSummary readOrder(ResultSet rs) throws SQLException {
        if (!rs.next()) {
            return null; // ResultSet tồn tại nhưng có 0 hàng.
        }

        OrderSummary result = new OrderSummary(
                rs.getLong("order_id"),
                rs.getString("order_status"));

        if (rs.next()) {
            throw new SQLException("Expected at most one order row");
        }
        return result;
    }

    private static List<ItemSummary> readItems(ResultSet rs)
            throws SQLException {
        List<ItemSummary> results = new ArrayList<>();
        while (rs.next()) {
            results.add(new ItemSummary(
                    rs.getInt("line_no"),
                    rs.getLong("product_id"),
                    rs.getInt("quantity"),
                    rs.getBoolean("reviewed")));
        }
        return results;
    }
}
```

Cách dùng:

```java
OrderProcedureRepository repository =
        new OrderProcedureRepository(dataSource);

OrderProcedureRepository.ReviewResult result =
        repository.reviewOrder(101L);

System.out.println(result.order().status()); // REVIEWED
System.out.println(result.items().size());    // 3 với dữ liệu minh họa.
System.out.println(result.updateCounts());    // Các count driver báo.
```

Nếu driver báo đầy đủ các update count của ví dụ T-SQL, danh sách có thể là `[1, 3]`. Nếu driver không báo mọi count, danh sách có thể khác; phương thức **không giả định số phần tử hoặc giá trị cố định** trong `updateCounts`. Trường hợp thủ tục trả thêm một `ResultSet` bất ngờ, mã cố ý ném lỗi thay vì ánh xạ nhầm bảng vào cấu trúc của bảng thứ hai.

### Các quyết định thiết kế trong ví dụ

| Quyết định | Lý do |
| --- | --- |
| Gọi `prepareCall("{call ...(?)}")` | Dùng cú pháp gọi thủ tục JDBC với tham số, không ghép ID vào SQL |
| `call.execute()` thay vì `executeQuery()` | Thủ tục trả cả bảng lẫn update count |
| Duyệt `getMoreResults()` sau **mỗi** kết quả | Không dừng nhầm khi một count nằm giữa hai bảng |
| Đếm riêng `resultSetIndex` | Update count không làm thay đổi thứ tự **bảng** thứ nhất/thứ hai |
| Đọc `order_id`/`order_status` và `line_no`/`product_id` theo tên | Hợp đồng ánh xạ dễ đọc, không phụ thuộc vị trí cột |
| Trả `record` và `List.copyOf` | Dữ liệu sử dụng được sau khi `CallableStatement`/`ResultSet` đóng |
| Kiểm tra đúng hai `ResultSet` | Phát hiện thay đổi hợp đồng thủ tục trước khi commit |
| Đóng `ResultSet` trong từng nhánh | Không giữ con trỏ tới bảng cũ khi chuyển sang kết quả mới |
| `commit()` sau khi đọc hết | Lỗi ở kết quả sau vẫn có cơ hội làm rollback thao tác ghi |

Việc `reviewOrder` đọc kết quả và xác nhận transaction trong cùng phương thức chỉ phù hợp khi repository **sở hữu kết nối và transaction**. Nếu tầng dịch vụ đã quản lý một transaction lớn hơn, hãy truyền `Connection` đang dùng vào phương thức và để tầng chủ sở hữu quyết định commit/rollback; thủ tục và các câu SQL liên quan cần dùng cùng kết nối đó.

## 5. Không nhầm kết quả của `SELECT` với số hàng cập nhật

Có ba trường hợp cần phân biệt:

| Trạng thái nhận được | Ví dụ | Cách diễn giải |
| --- | --- | --- |
| `ResultSet` có 3 hàng | `SELECT ... FROM order_item` trả 3 dòng | Phải lặp `rs.next()` để đọc **3 hàng dữ liệu** |
| `ResultSet` có 0 hàng | `SELECT ... WHERE order_id = 999` | Vẫn là một `ResultSet` hợp lệ; `rs.next()` trả `false` |
| Update count bằng 0 | `UPDATE ... WHERE order_id = 999` không khớp hàng | Một kết quả cập nhật hợp lệ có count **0**, không phải dấu hiệu kết thúc |

Một câu `SELECT COUNT(*) FROM order_item WHERE order_id = ?` lại tạo **`ResultSet` có một hàng** chứa số lượng đếm theo SQL. Nó không phải update count của JDBC. Tương tự, `getUpdateCount()` không cho biết có bao nhiêu hàng được trả về trong một `ResultSet` trước đó.

Nếu cần kết quả dễ kiểm thử và không phụ thuộc việc driver có phát update count hay không, có thể thiết kế thủ tục trả **một bảng thống kê**:

```sql
-- Một SELECT trong thủ tục, cú pháp SQL Server.
SELECT
    @order_id AS order_id,
    (SELECT COUNT(*) FROM dbo.order_item WHERE order_id = @order_id)
        AS item_count;
```

Khi thêm `SELECT` này vào thủ tục, hợp đồng đầu ra thay đổi thành **ba bảng kết quả**; phải cập nhật mapper tương ứng. Đây là ví dụ về cách trả một số đếm như **dữ liệu rõ ràng**, khác hoàn toàn update count mà driver phát cho `UPDATE`.

### Update count lớn và `getLargeUpdateCount()`

`getUpdateCount()` trả `int`. JDBC còn có `getLargeUpdateCount()` trả `long`, hữu ích khi một lệnh có thể tác động nhiều hơn phạm vi `int`. Mã dùng `getLargeUpdateCount()` nên đi cùng `getMoreResults()` và kiểm tra `-1L` tương tự; có thể cần xác minh hỗ trợ của driver. Không dùng `executeLargeBatch()` để xử lý nhiều bảng trả về từ stored procedure: API đó dành cho **batch update**, không phải duyệt luồng kết quả hỗn hợp.

## 6. Đóng và giữ nhiều ResultSet như thế nào?

Theo cách dùng thông thường, `getMoreResults()` chuyển sang kết quả kế tiếp và **đóng `ResultSet` hiện tại** theo hợp đồng JDBC. Ví dụ chính còn dùng `try-with-resources` cho từng `ResultSet`, bảo đảm mỗi con trỏ được đóng ngay sau khi ánh xạ xong. Sau khi chuyển kết quả, không nên giữ `ResultSet` cũ để gọi `next()` thêm; hãy lưu dữ liệu đã ánh xạ vào record, list hoặc cấu trúc độc lập.

JDBC hỗ trợ biến thể:

```java
call.getMoreResults(java.sql.Statement.CLOSE_CURRENT_RESULT);
call.getMoreResults(java.sql.Statement.KEEP_CURRENT_RESULT);
call.getMoreResults(java.sql.Statement.CLOSE_ALL_RESULTS);
```

| Tùy chọn | Ý nghĩa mong muốn |
| --- | --- |
| `CLOSE_CURRENT_RESULT` | Đóng bảng kết quả hiện tại khi chuyển sang kết quả kế tiếp |
| `KEEP_CURRENT_RESULT` | Cố giữ bảng hiện tại mở khi chuyển sang bảng tiếp theo |
| `CLOSE_ALL_RESULTS` | Đóng toàn bộ các bảng kết quả đang mở của statement |

Giữ nhiều `ResultSet` mở đồng thời đòi hỏi driver hỗ trợ khả năng tương ứng. Có thể hỏi `DatabaseMetaData.supportsMultipleOpenResults()`, nhưng cần kiểm tra hành vi thực tế. Với đa số nghiệp vụ, **đọc xong, ánh xạ thành đối tượng rồi đóng từng bảng** đơn giản và ổn định hơn so với giữ con trỏ mở đồng thời.

Khi thủ tục có nhiều bảng rất lớn, việc gom tất cả hàng thành danh sách có thể gây tốn bộ nhớ. Cân nhắc phân trang ở DB, đọc theo callback trong thời gian kết nối còn mở, giới hạn số hàng và cấu hình `fetchSize` theo driver. `fetchSize` là gợi ý tới driver, không phải cam kết mỗi lần tải đúng số hàng. Đừng trả một `ResultSet` đang gắn với statement vừa bị đóng ra ngoài repository.

## 7. OUT parameter và return status khác với update count

Thủ tục có thể khai báo **`OUT` hoặc `INOUT` parameter**, hoặc cơ chế trả trạng thái qua giá trị trả về theo DBMS. Các giá trị này **không phải** update count và không phải tự động là một `ResultSet`.

JDBC dùng `CallableStatement.registerOutParameter(...)` để đăng ký tham số đầu ra trước khi thực thi:

```java
// Giả sử procedure của DB có một tham số IN và một tham số OUT INTEGER.
try (CallableStatement call = connection.prepareCall(
        "{call usp_with_status(?, ?)}")) {
    call.setLong(1, orderId);
    call.registerOutParameter(2, java.sql.Types.INTEGER);

    boolean isResultSet = call.execute();
    while (true) {
        if (isResultSet) {
            try (ResultSet rs = call.getResultSet()) {
                while (rs.next()) {
                    // Ánh xạ bảng kết quả.
                }
            }
        } else if (call.getUpdateCount() == -1) {
            break;
        }
        isResultSet = call.getMoreResults();
    }

    int status = call.getInt(2); // OUT parameter, không phải update count.
    if (call.wasNull()) {
        // Xử lý trạng thái OUT = SQL NULL theo hợp đồng thủ tục.
    }
}
```

`usp_with_status` là thủ tục giả định để minh họa API, không phải thủ tục `dbo.usp_review_order` đã định nghĩa ở phần trước. Để tăng khả năng tương thích với nhiều driver, nên **duyệt hết các result set và update count trước khi đọc OUT parameter** khi thủ tục trả nhiều kết quả. Cách driver truyền, đánh chỉ số và cung cấp OUT parameter/return status có thể phụ thuộc DBMS; hãy dựa trên chữ ký thực tế của thủ tục.

Với một số hệ quản trị, có cú pháp gọi hàm hoặc nhận return status như `{? = call ...(?)}`. Không tự gán số trả về của `executeUpdate()` hay `getUpdateCount()` cho “mã trạng thái nghiệp vụ” nếu thủ tục không quy định như vậy. Nếu cần số lượng cập nhật **chính xác** từ từng bước, có thể khai báo các `OUT` parameter rõ ràng như `updated_orders` và `updated_items`, hoặc trả một bảng tổng hợp thay vì phụ thuộc thông báo count của driver.

## 8. Transaction và lỗi khi thủ tục vừa đọc vừa ghi

Một stored procedure chứa nhiều câu lệnh **không tự bảo đảm** tất cả thay đổi là một thao tác nguyên tử theo mọi DBMS và cấu hình. Nếu `Connection` đang có `autoCommit = true`, các câu lệnh DML trong thủ tục và cách commit/rollback có thể chịu ngữ nghĩa riêng của DB. Khi nghiệp vụ yêu cầu “cập nhật đơn và dòng hàng cùng thành công”, hãy xác định **ai sở hữu transaction** và kiểm chứng với DB cụ thể.

Trong ví dụ Java, ta chủ động gọi:

```java
connection.setAutoCommit(false);
try {
    // Gọi thủ tục và đọc hết kết quả bằng CallableStatement.
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

Điều này phù hợp khi thủ tục **không tự commit** và các bảng tham gia cùng transaction của kết nối. Nếu thủ tục chủ động bắt/nuốt lỗi SQL, tự `COMMIT` hoặc mở kết nối/giao dịch độc lập, `rollback()` ở phía caller có thể không đảo ngược những thay đổi đó. Đó là lý do cần thống nhất hợp đồng transaction giữa ứng dụng Java và mã thủ tục ở DB.

Đừng bỏ qua lỗi đọc bảng kết quả sau một cập nhật đã thực hiện. Nếu mapper ném `SQLException` vì tên cột thay đổi hoặc kiểu dữ liệu sai, hành vi phù hợp của ví dụ là rollback toàn bộ transaction, không trả về đối tượng chỉ chứa một phần dữ liệu nhưng lại commit những cập nhật đã xảy ra.

Khi mất kết nối đúng lúc `commit()`, kết quả commit có thể **không xác định được từ phía Java**; việc cố `rollback()` sau đó không chứng minh chắc chắn giao dịch chưa thành công. Nếu gọi lại thủ tục có thể tạo tác động lặp, cần cơ chế yêu cầu duy nhất, điều kiện cập nhật có chủ đích và đối soát trước khi retry. Điều này đặc biệt quan trọng với thủ tục có `INSERT`, tăng bộ đếm hoặc ghi giao dịch tài chính.

### `SQLException` và điều kiện phục hồi

- `CallableStatement.execute()`, `getMoreResults()`, `getResultSet()`, `getUpdateCount()` đều có thể phát sinh `SQLException` khi driver/DB lỗi.
- Tên thủ tục không tồn tại, chữ ký tham số sai, không đủ quyền thực thi hoặc kiểu cột thay đổi là lỗi hợp đồng cần sửa, không nên retry vô hạn.
- Lỗi timeout, khóa hoặc serialization có thể cần rollback và thử lại **toàn bộ giao dịch** nếu DB xác định đó là lỗi tạm thời và nghiệp vụ an toàn để thực thi lại.
- Một số thủ tục dùng `SELECT` để báo lỗi dưới dạng dữ liệu; ứng dụng phải đọc và kiểm tra theo hợp đồng thủ tục, không nhầm đó là exception JDBC tự động.
- Thông báo/warning từ DB có thể xuất hiện dưới dạng `SQLWarning` qua statement hoặc connection; warning không tự động tương đương một `ResultSet` hay update count.

`Statement.setQueryTimeout(...)` có thể giới hạn thời gian thực thi theo khả năng driver, nhưng không thay thế chính sách timeout mạng hoặc timeout khóa riêng của DB. Đừng đóng connection khi còn định dùng tiếp `ResultSet`; vòng đời kết quả luôn bị giới hạn bởi statement và connection tương ứng.

## 9. Khả năng hỗ trợ và sự khác biệt giữa driver

Trước khi dựa vào một luồng nhiều bảng, có thể hỏi một số khả năng mà driver công bố:

```java
try (Connection connection = dataSource.getConnection()) {
    var meta = connection.getMetaData();
    System.out.println("Stored procedures: "
            + meta.supportsStoredProcedures());
    System.out.println("Multiple ResultSets: "
            + meta.supportsMultipleResultSets());
    System.out.println("Multiple open ResultSets: "
            + meta.supportsMultipleOpenResults());
}
```

`supportsMultipleResultSets()` và `supportsMultipleOpenResults()` trả lời **hai câu hỏi khác nhau**: có thể nhận nhiều bảng kết quả từ một lần thực thi, và có thể giữ nhiều bảng mở cùng lúc. Ví dụ chính yêu cầu **nhiều bảng nhưng không cần giữ đồng thời**. Metadata chỉ phản ánh khả năng driver báo cáo; không thay thế integration test với thủ tục thật và cấu hình driver thật.

Các điểm cần xác minh theo DBMS:

| Khía cạnh | Tại sao có thể khác nhau? |
| --- | --- |
| Cú pháp tạo/gọi procedure | `CREATE PROCEDURE`, `CALL`, `EXEC`, anonymous block hoặc `REF CURSOR` không đồng nhất |
| Cách trả nhiều bảng | Có DB phát nhiều `ResultSet` từ `SELECT`, có DB cần cursor/OUT parameter hoặc API riêng |
| Thông báo update count | `SET NOCOUNT`, trigger, tùy chọn driver hoặc quy tắc DB có thể thay đổi lượng count được thấy |
| Thứ tự bảng và count | Phụ thuộc lệnh trong procedure, nhánh điều kiện và driver; thêm `SELECT` mới có thể đổi hợp đồng |
| OUT parameter | Cách đăng ký, chỉ số, kiểu SQL và thời điểm có thể đọc khác nhau |
| Transaction của procedure | Có DB cho thủ tục quản lý transaction, có DB đặt ràng buộc riêng khi caller đang có transaction |
| Timeout/streaming | Driver có thể đệm toàn bộ kết quả hoặc truyền dần; giới hạn và cấu hình không đồng nhất |

Với API công khai, nên **phiên bản hóa hợp đồng kết quả** nếu một thay đổi thủ tục có thể thêm/bớt `SELECT`, đổi alias cột hoặc đổi thứ tự bảng. Thêm một câu `SELECT` chỉ để chẩn đoán bên trong procedure có thể vô tình trở thành **`ResultSet` thứ ba** và khiến mapper hiện tại hiểu sai. Hãy dùng log hoặc cơ chế báo trạng thái phù hợp, không trộn kết quả debug vào giao diện dữ liệu mà caller đang dựa vào.

## 10. Lỗi phổ biến khi duyệt nhiều kết quả

| Cách làm sai | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Gọi `executeQuery()` cho thủ tục trả cả update count | Không xử lý đúng toàn bộ kết quả; driver có thể báo lỗi | Dùng `execute()` và vòng lặp kết quả hỗn hợp |
| Viết `while (call.getMoreResults())` | Dừng ngay khi gặp update count nằm giữa hai bảng | Sau `false`, kiểm tra `getUpdateCount() != -1` trước khi kết luận hết |
| Cho rằng `execute() == false` nghĩa là thủ tục không trả gì | Bỏ qua update count đầu tiên và các bảng phía sau | Đọc `getUpdateCount()` rồi tiếp tục bằng `getMoreResults()` |
| Dùng `getUpdateCount() == 0` làm dấu hiệu kết thúc | Mất kết quả tiếp theo khi `UPDATE` tác động 0 hàng | Chỉ `-1` ở trạng thái không phải `ResultSet` mới báo hết |
| Gộp `SELECT COUNT(*)` với update count | Hiểu nhầm số hàng truy vấn với số hàng DML | Đọc `SELECT COUNT(*)` như một `ResultSet` bình thường |
| Không đóng `ResultSet` trước khi chuyển kết quả | Dễ giữ tài nguyên quá lâu hoặc đọc vào con trỏ đã hết hiệu lực | Ánh xạ, đóng từng bảng rồi `getMoreResults()` |
| Ánh xạ mọi bảng bằng cùng một mapper | Sai kiểu khi bảng đơn hàng và bảng dòng hàng khác cột | Dùng mapper riêng dựa trên hợp đồng thứ tự bảng |
| Cố định số count mà driver phải trả | Mã dễ hỏng vì `NOCOUNT`, trigger hoặc cấu hình driver | Đọc và lưu count thực tế; dùng OUT parameter cho số đếm ổn định |
| Đọc OUT parameter trước khi tiêu thụ các bảng | Có thể làm driver phải đệm/bỏ qua kết quả; hành vi phụ thuộc DB | Ưu tiên đọc hết bảng/count trước rồi mới lấy OUT |
| `commit()` trước khi đọc xong | Lỗi mapper sau đó không thể rollback thay đổi đã commit | Kiểm tra và đọc đủ hợp đồng kết quả trước commit |

## 11. Kiểm thử với cơ sở dữ liệu và driver thực tế

Vì tính năng này phụ thuộc nhiều vào DBMS và driver, một **integration test** nên gọi stored procedure thật và xác minh cả dữ liệu DB lẫn kết quả Java:

| Trường hợp | Kết quả cần kiểm tra |
| --- | --- |
| Đơn 101 có ba dòng | Có hai bảng kết quả: bảng đơn một hàng, bảng chi tiết ba hàng |
| Update count xuất hiện trước bảng đầu tiên | Vòng lặp vẫn nhận diện bảng đầu tiên và đọc được nội dung |
| Update count xuất hiện giữa hai bảng | `getMoreResults() == false` không làm vòng lặp dừng sớm |
| `UPDATE` tác động 0 hàng | Count `0` được ghi nhận nếu driver cung cấp, không coi là hết kết quả |
| `SELECT` trả 0 hàng | `ResultSet` vẫn tồn tại; `rs.next()` trả `false` |
| Driver không phát đủ update count | Hai bảng vẫn được ánh xạ đúng; danh sách counts chỉ chứa những gì được phát |
| Thủ tục thêm bảng kết quả bất ngờ | Mã báo lỗi hợp đồng và rollback theo chính sách của ví dụ |
| Thủ tục thiếu bảng thứ hai | Mã phát hiện thiếu `ResultSet` và không commit |
| Alias cột thay đổi | Mapper phát sinh lỗi rõ ràng, transaction được rollback nếu chưa commit |
| Một câu `UPDATE` trong procedure bị lỗi | Caller nhận `SQLException`; giao dịch được rollback nếu DB còn cho phép |
| Gọi không đủ quyền hoặc sai chữ ký | Lỗi thực thi được trả đúng lên tầng gọi |
| Thủ tục dùng `OUT` parameter | Kiểm tra giá trị OUT sau khi đã đọc hết các bảng/count |

Để quan sát dữ liệu sau gọi thành công, dùng một kết nối mới và truy vấn:

```sql
SELECT order_id, order_status
FROM dbo.purchase_order
WHERE order_id = 101;

SELECT order_id, line_no, reviewed
FROM dbo.order_item
WHERE order_id = 101
ORDER BY line_no;
```

Kỳ vọng trạng thái đơn là `REVIEWED` và ba dòng đều có `reviewed = 1`. Đối với test rollback, tạo một lỗi **bên trong transaction sau khi một câu `UPDATE` đã chạy**, hoặc cố ý thay đổi hợp đồng số bảng kết quả trong một môi trường test riêng, sau đó kiểm tra dữ liệu bằng kết nối khác. Không chỉ kiểm tra `SQLException` mà bỏ qua trạng thái dữ liệu cuối cùng.

Khi cần thử nghiệm các biến thể driver, bật/tắt cấu hình trả update count ở môi trường kiểm thử, quan sát `getMoreResults()` và `getUpdateCount()` sau từng kết quả. Lưu nhận diện driver/DB và phiên bản vào kết quả test để tránh kết luận sai khi nâng cấp. Không dựa vào số kết quả của một DB để khẳng định tất cả DB khác đều có cùng luồng.

## 12. Bài tập tự kiểm tra

**Bài 1 — Duyệt đúng luồng kết quả.** Một thủ tục trả lần lượt `update count = 1`, bảng A, `update count = 0`, bảng B. Nếu mã dùng `while (call.getMoreResults())`, bảng nào có thể bị bỏ qua? Viết điều kiện dừng đúng.

**Gợi ý:** Có thể dừng ngay tại count đầu tiên hoặc count giữa hai bảng. Duyệt `execute()`/`getMoreResults()` và chỉ kết thúc khi **không phải `ResultSet` và `getUpdateCount() == -1`**.

**Bài 2 — Phân biệt hai số không.** Một `UPDATE` báo update count `0` và một `SELECT` trả `ResultSet` rỗng. Vì sao chúng không tương đương, và nên xử lý bằng API nào?

**Gợi ý:** Count `0` là kết quả DML; `ResultSet` rỗng vẫn có metadata cột và `rs.next() == false`. Dùng `getUpdateCount()` cho trường hợp đầu, `getResultSet()` cho trường hợp sau.

**Bài 3 — Hai bảng khác cấu trúc.** Bảng thứ nhất trả `order_id, order_status`, bảng thứ hai trả `line_no, product_id, quantity, reviewed`. Hãy thiết kế hai `record` riêng và xác định `resultSetIndex` nên tăng ở những trường hợp nào.

**Gợi ý:** Chỉ tăng chỉ số khi nhận một **`ResultSet`**; update count không phải bảng và không làm tăng `resultSetIndex`.

**Bài 4 — Kiểm tra giả định driver.** Một driver không trả update count của các lệnh `UPDATE` trong stored procedure. Làm sao vẫn xác nhận đúng số dòng đơn hàng đã được xử lý?

**Gợi ý:** Thay đổi hợp đồng procedure để trả số đếm tường minh qua `OUT` parameter hoặc bảng `SELECT`, rồi kiểm thử trên DB đích.

**Bài 5 — Thêm `SELECT` chẩn đoán.** Một người sửa procedure bằng cách thêm `SELECT 'DEBUG' AS message` trước câu truy vấn đơn hàng. Điều gì có thể xảy ra với mapper đang coi `ResultSet #1` là thông tin đơn?

**Gợi ý:** Mapper sẽ đọc sai alias cột hoặc sai loại bảng. Cần giữ hợp đồng đầu ra ổn định và chọn cơ chế log phù hợp.

**Bài 6 — Ranh giới transaction.** Procedure cập nhật một đơn và các dòng hàng; mapper đọc bảng thứ hai bị `SQLException`. Vì sao `commit()` cần nằm **sau** vòng lặp đọc hết kết quả nếu muốn thao tác không thành công một phần?

**Gợi ý:** Lỗi ở bảng sau phải còn cơ hội kích hoạt `rollback()` cho các cập nhật chưa commit của cùng transaction, với điều kiện procedure không tự commit độc lập.

## Tổng kết

Khi stored procedure trả nhiều bảng và số hàng cập nhật, hãy dùng **`CallableStatement.execute()`** để bắt đầu, **`getResultSet()`** cho kết quả dạng bảng, **`getUpdateCount()`** cho kết quả DML, rồi **`getMoreResults()`** để chuyển sang kết quả tiếp theo. Giá trị `false` của `execute()`/`getMoreResults()` chưa chắc nghĩa là hết kết quả; chỉ dừng khi không có `ResultSet` và update count bằng `-1`. Ánh xạ từng bảng theo đúng hợp đồng cột, đóng `ResultSet` kịp thời và quản lý `Connection`/transaction rõ ràng. Cuối cùng, kiểm chứng cách DBMS và driver cung cấp update count, OUT parameter, nhiều bảng và rollback trước khi phụ thuộc vào chúng trong mã sản xuất.
