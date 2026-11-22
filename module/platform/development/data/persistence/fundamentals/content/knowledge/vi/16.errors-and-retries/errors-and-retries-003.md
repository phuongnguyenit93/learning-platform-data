# Giữ nguyên nguyên nhân và ngữ cảnh của lỗi lưu trữ

Khi một thao tác lưu dữ liệu thất bại, điều quan trọng không chỉ là thông báo “database error”. Người vận hành và lập trình viên còn cần biết **thao tác nào thất bại, lỗi do DBMS/driver báo là gì, xảy ra trong transaction nào, hậu quả đến đâu và có thể thử lại an toàn không**. Nếu ứng dụng Java bọc ngoại lệ sai cách, nuốt lỗi khi rollback, hoặc trả về một thông báo chung chung mà đánh mất nguyên nhân, việc xác định sự cố có thể trở nên gần như không thể.

Ví dụ, hai request cùng trả HTTP 500 nhưng cần xử lý rất khác nhau:

- Một request gặp `SQLSTATE 23505` vì ghi trùng khóa duy nhất: có thể là xung đột nghiệp vụ hoặc thao tác đã được xử lý.
- Request khác gặp `SQLSTATE 40P01` vì deadlock: có thể retry **toàn bộ transaction** theo chính sách có giới hạn.
- Request thứ ba mất kết nối khi đang chờ phản hồi `COMMIT`: **chưa biết** DB đã commit hay chưa; retry mù có thể tạo dữ liệu trùng.

Nếu tất cả đều bị chuyển thành `throw new RuntimeException("Save failed")` thì ứng dụng đã đánh mất bằng chứng để phân biệt những tình huống này.

Bài thuộc chương **Lỗi và thử lại** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, liên kết xử lý ngoại lệ với ranh giới persistence cho Java, giao dịch, cô lập, kiểm soát đồng thời, bảo mật và vận hành. Trọng tâm là bảo toàn **chuỗi nguyên nhân (causal chain)** và **ngữ cảnh có cấu trúc**, đồng thời chỉ cho phép retry khi biết rõ ngữ nghĩa và trạng thái thao tác.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt thông điệp lỗi, nguyên nhân gốc, ngoại lệ bao bọc, ngoại lệ phụ và ngữ cảnh nghiệp vụ.
2. Bảo toàn `Throwable.getCause()`, `getSuppressed()` và chuỗi `SQLException.getNextException()` khi chuyển lỗi giữa các tầng Java.
3. Giữ lại SQLSTATE, vendor error code, tên thao tác, transaction boundary, giá trị retry attempt và correlation/trace ID mà không làm lộ bí mật.
4. Quyết định tầng nào nên chuyển `SQLException` thành lỗi persistence hoặc lỗi nghiệp vụ, và tầng nào nên ghi log.
5. Không để lỗi rollback/close/reset connection che mất lỗi ban đầu.
6. Phân biệt lỗi có thể retry, lỗi dữ liệu không nên retry và trường hợp kết quả `COMMIT` chưa chắc chắn.
7. Chẩn đoán lỗi bằng log/tracing có cấu trúc, giữ nguyên bằng chứng phục vụ vận hành và kiểm thử.

## 2. Một lỗi lưu trữ có nhiều lớp nguyên nhân

Xét API xác nhận một đơn hàng:

~~~text
HTTP POST /orders/{id}/confirm
        |
        v
OrderService.confirm(orderId)
        |
        v
OrderRepository.updateState(...)
        |
        v
JDBC PreparedStatement.executeUpdate()
        |
        v
Database: unique constraint / deadlock / timeout / connection failure
~~~

Ở mỗi tầng, cùng một sự cố có thể được mô tả theo góc nhìn khác:

- **DBMS** phát hiện vi phạm ràng buộc, tranh chấp khóa hoặc lỗi kết nối.
- **Driver JDBC** chuyển tín hiệu giao thức thành `SQLException` và các thuộc tính như SQLSTATE, mã lỗi vendor.
- **Repository** biết câu lệnh đang thực hiện thuộc thao tác gì, chẳng hạn `confirmOrder`.
- **Service** biết quy tắc nghiệp vụ, ranh giới transaction và liệu một lần retry có an toàn không.
- **API** biết cách trả HTTP status và thông báo an toàn cho client, nhưng không nên bộc lộ SQL hay stack trace.

Một mô hình xử lý hữu ích là:

~~~mermaid
flowchart TD
    A["DBMS / JDBC: SQLException"] --> B["Repository: lỗi persistence có cause"]
    B --> C["Service: ngữ cảnh thao tác, transaction, retry"]
    C --> D["Boundary: log có cấu trúc, trace"]
    C --> E["API: mã lỗi ổn định, thông điệp an toàn"]
    A -.->|SQLSTATE / vendor code / nextException| D
~~~

**Giữ nguyên nguyên nhân** nghĩa là không làm đứt đường truy ngược từ lỗi ở tầng API/service về `SQLException` hoặc lỗi driver ban đầu. **Giữ nguyên ngữ cảnh** nghĩa là có thông tin giải thích lỗi xảy ra trong *thao tác nào* và *điều kiện nào*, dù thông tin đó có thể không nằm trong thông điệp của DBMS.

### 2.1. Phân biệt các thuộc tính quan trọng

| Thành phần | Ví dụ | Công dụng |
|---|---|---|
| Loại lỗi | `SQLException`, `SQLIntegrityConstraintViolationException` | Phân biệt nhóm lỗi ở tầng Java, nhưng ánh xạ phụ thuộc driver |
| Message | “duplicate key value violates unique constraint” | Cung cấp mô tả từ driver/DBMS; có thể chứa dữ liệu nhạy cảm |
| SQLSTATE | `23505`, `40001`, `40P01` | Mã chuẩn hóa một phần; cần xét DBMS và phiên bản |
| Vendor code | `getErrorCode()` | Mã cụ thể do DBMS/driver cung cấp |
| Cause | `getCause()` | Đường truy ngược tới ngoại lệ đã gây ra ngoại lệ hiện tại |
| Next exception | `getNextException()` | Chuỗi ngoại lệ SQL liên quan do driver cung cấp, khác causal chain |
| Suppressed | `getSuppressed()` | Lỗi phụ trong cleanup, rollback, close hoặc try-with-resources |
| Operation | `confirmOrder` | Ngữ cảnh do ứng dụng đặt, không phụ thuộc thông báo DB |
| Correlation/trace ID | ID yêu cầu do hệ thống cấp | Nối log giữa HTTP, service, repository và DB |
| Transaction/retry context | attempt 2/3, transaction scope | Giải thích lỗi xảy ra ở lần thử nào và trạng thái có thể đã thay đổi |

Một thông điệp duy nhất không thể thay thế tất cả thành phần trên.

## 3. Ba kênh lưu giữ bằng chứng ngoại lệ trong Java

### 3.1. `getCause()`: chuỗi nguyên nhân chính

Khi chuyển một ngoại lệ sang loại lỗi có ý nghĩa ở tầng trên, hãy truyền **ngoại lệ gốc làm cause**:

~~~java
try {
    statement.executeUpdate();
} catch (SQLException cause) {
    throw new PersistenceFailure("confirmOrder", cause);
}
~~~

Ngoại lệ bao bọc:

~~~java
public final class PersistenceFailure extends RuntimeException {
    private final String operation;
    private final String sqlState;
    private final int vendorCode;

    public PersistenceFailure(String operation, SQLException cause) {
        super(
            "Persistence operation failed: " + operation
                + " [SQLState=" + cause.getSQLState()
                + ", vendorCode=" + cause.getErrorCode() + "]",
            cause
        );
        this.operation = operation;
        this.sqlState = cause.getSQLState();
        this.vendorCode = cause.getErrorCode();
    }

    public String getOperation() {
        return operation;
    }

    public String getSqlState() {
        return sqlState;
    }

    public int getVendorCode() {
        return vendorCode;
    }
}
~~~

`operation` nên đến từ **danh mục tên thao tác do ứng dụng định nghĩa** (ví dụ `"confirmOrder"`), không được đưa thẳng đầu vào tùy ý của người dùng vào thông báo hoặc metric label.

Đoạn mã trên giữ `cause` và các thông tin phân loại cần thiết. Nó không buộc client phải nhận thông điệp chi tiết của DBMS. API có thể ánh xạ lỗi sang phản hồi ngắn gọn trong khi hệ thống nội bộ vẫn có đường truy ngược kỹ thuật.

**Sai lầm thường gặp:**

~~~java
catch (SQLException error) {
    // Sai: tạo exception mới nhưng làm mất cause và stack trace gốc.
    throw new RuntimeException("Database unavailable");
}

catch (SQLException error) {
    // Sai: chỉ chép message, làm mất loại lỗi, SQLSTATE, cause, stack gốc.
    throw new RuntimeException(error.getMessage());
}
~~~

Một biến thể khác là `throw new RuntimeException(error.toString())`, vẫn chỉ tạo chuỗi văn bản. Đúng hơn là `throw new RuntimeException("...", error)` khi cần chuyển ngoại lệ. Nếu cùng tầng có thể xử lý/khai báo `SQLException` thì `throw error` bảo toàn nguyên dạng, nhưng phải cân nhắc hợp đồng API của tầng trên.

### 3.2. `getNextException()`: chuỗi chẩn đoán riêng của JDBC

`SQLException` có hai đường nối khác nhau:

- `getCause()` thuộc hệ thống `Throwable`.
- `getNextException()` thuộc `SQLException`, cho phép driver lưu một chuỗi lỗi SQL liên quan.

Không nên giả định rằng gọi `getCause()` sẽ duyệt đầy đủ chuỗi `getNextException()` hoặc rằng công cụ log luôn in hết mọi lỗi SQL phụ theo cùng cách trên mọi driver. Khi sự cố cần điều tra sâu, có thể trích **mã chẩn đoán** từ chuỗi này.

Ví dụ helper chỉ lấy mã, hạn chế đưa message chưa kiểm soát vào log:

~~~java
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

public final class SqlErrorDiagnostics {
    private SqlErrorDiagnostics() {}

    public static List<String> codes(SQLException first) {
        List<String> result = new ArrayList<>();
        for (SQLException current = first;
             current != null;
             current = current.getNextException()) {
            result.add(
                "SQLState=" + current.getSQLState()
                + ", vendorCode=" + current.getErrorCode()
            );
        }
        return result;
    }
}
~~~

Ví dụ minh họa cho driver bình thường. Nếu xây dựng công cụ duyệt tổng quát trên mọi ngoại lệ không đáng tin cậy, cần bảo vệ trước chuỗi tham chiếu vòng/bất thường và giới hạn số mục để tránh log quá lớn.

Thông tin `getNextException()` có thể đặc biệt hữu ích khi batch execution có nhiều lỗi liên quan. Nhưng tính sẵn có, thứ tự và chi tiết của chuỗi do driver quyết định.

### 3.3. `getSuppressed()`: lỗi phụ xảy ra khi dọn tài nguyên

Giả sử truy vấn thất bại, rồi khi Java đóng `ResultSet`, `Statement` hoặc `Connection` lại phát sinh lỗi khác. Với `try-with-resources`, Java có cơ chế giữ **ngoại lệ đầu tiên** làm ngoại lệ chính và gắn ngoại lệ phát sinh khi đóng tài nguyên vào `getSuppressed()`.

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement("SELECT id FROM orders WHERE id = ?")) {
    statement.setLong(1, orderId);
    try (ResultSet rows = statement.executeQuery()) {
        // Xử lý kết quả.
    }
}
~~~

Nếu `executeQuery()` là nơi xảy ra lỗi chính và `close()` sau đó cũng lỗi, try-with-resources thường bảo vệ lỗi chính bằng cách giữ lỗi close như **suppressed exception**.

Không nên chỉ log `error.getMessage()` rồi bỏ qua toàn bộ stack/cause/suppressed; cách đó làm mất các manh mối liên quan cả truy vấn lẫn cleanup.

## 4. Giữ ngữ cảnh theo thao tác, tránh chỉ truyền message

Một lỗi “không thể thực thi câu lệnh” thiếu thông tin về hành động người dùng. Ngữ cảnh nên được **cấu trúc hóa** và có trách nhiệm rõ ràng ở từng tầng:

| Tầng | Ngữ cảnh nên có | Không nên gắn |
|---|---|---|
| Repository | Tên operation, tên nguồn dữ liệu logic, SQLSTATE/vendor code | Password, chuỗi kết nối có credential, toàn bộ SQL chứa giá trị nhạy cảm |
| Service | Loại nghiệp vụ, trạng thái transaction, attempt, điều kiện ra quyết định | Dữ liệu thẻ, nội dung hồ sơ, token xác thực |
| Transaction manager | Commit/rollback outcome, isolation, timeout, lỗi phụ | Khẳng định đã rollback thành công nếu không nhận được xác nhận |
| API boundary | Correlation ID, mã lỗi ổn định, HTTP status | Stack trace, SQL nội bộ, thông báo thô của DBMS |
| Observability | Tên thao tác hữu hạn, elapsed time, stage, loại lỗi | Dữ liệu cá nhân trong label có cardinality cao |

Ví dụ một bản ghi sự cố có cấu trúc:

~~~json
{
  "event": "storage_operation_failed",
  "operation": "confirmOrder",
  "trace_id": "req-7f12c9",
  "attempt": 2,
  "db_role": "primary",
  "sql_state": "40P01",
  "vendor_code": 0,
  "transaction_outcome": "rolled_back",
  "elapsed_ms": 482,
  "retry_decision": "retry_entire_transaction"
}
~~~

Đây là **dữ liệu minh họa**, không phải log thật. Mỗi trường chỉ nên được ghi khi ứng dụng có bằng chứng. Chẳng hạn `transaction_outcome = "rolled_back"` chỉ hợp lệ khi đã nhận xác nhận rollback; nếu rollback thất bại do mất mạng, cần biểu diễn `unknown` hoặc trạng thái tương đương.

### 4.1. “Nguyên nhân gốc” không phải lúc nào cũng là exception cuối cùng

Một `SocketException` nằm sâu trong `cause` có thể giải thích kết nối bị đứt. Tuy nhiên nguyên nhân nghiệp vụ cần giải quyết có thể nằm ở transaction bị giữ quá lâu, lỗi network ngắt sau khi COMMIT, hay cấu hình pool sai. Vì vậy giữ **toàn bộ chuỗi cause cùng ngữ cảnh thời gian và thao tác** tốt hơn chỉ tìm exception sâu nhất rồi bỏ phần còn lại.

Tương tự, cùng `SQLSTATE 23505` có thể có ý nghĩa khác nhau:

- Thêm người dùng với email trùng: báo xung đột dữ liệu hợp lệ.
- Xử lý lại request với idempotency key đã ghi trước đó: cần truy vấn lại kết quả đã lưu, có thể trả kết quả trước.
- Tạo dữ liệu nội bộ với khóa do ứng dụng sinh bị trùng bất thường: có thể là lỗi thiết kế hoặc phân phối ID.

Mã lỗi là tín hiệu kỹ thuật, **không đủ để kết luận cách xử lý nghiệp vụ**.

## 5. Chuyển ngoại lệ ở đúng tầng

Không phải mọi tầng đều nên bắt mọi lỗi. Một thiết kế có chủ đích thường có các trách nhiệm sau:

1. **Repository** bắt lỗi driver cần thiết, gắn tên thao tác và bảo toàn ngoại lệ bằng `cause`. Repository không quyết định retry HTTP request hoặc giả định transaction đã rollback.
2. **Service/use case** biết ranh giới nghiệp vụ, idempotency và các thao tác đã thực hiện; quyết định có retry, trả xung đột hoặc dừng.
3. **Infrastructure/transaction manager** quản lý `commit`, `rollback`, trạng thái connection và cleanup.
4. **API boundary** chuyển lỗi sang HTTP response và ghi log ở nơi có đủ trace ID, tránh lặp log vô ích ở mọi tầng.

### 5.1. Ví dụ repository có ngữ cảnh nhưng giữ cause

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderRepository {
    private final DataSource dataSource;

    public OrderRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean markPaid(long orderId) {
        String sql = """
            UPDATE orders
            SET status = 'PAID'
            WHERE id = ? AND status = 'PENDING'
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, orderId);
            return statement.executeUpdate() == 1;
        } catch (SQLException cause) {
            throw new PersistenceFailure("markOrderPaid", cause);
        }
    }
}
~~~

Ở đây, kết quả `0` hàng được cập nhật **không mặc nhiên là lỗi hạ tầng**: hàng có thể không tồn tại hoặc không còn trạng thái `PENDING`. Service phải xác định liệu đây là xung đột nghiệp vụ, request lặp, hay cần đọc lại trạng thái.

Đoạn mã minh họa một thao tác SQL độc lập trong chế độ giao dịch của `DataSource`. Khi một use case cần nhiều bước nguyên tử, **không tự mở connection riêng ở từng repository** rồi tưởng rằng chúng cùng một transaction. Phải dùng transaction manager hoặc truyền cùng connection trong toàn đơn vị công việc.

### 5.2. Khi có nhiều transaction: giữ original failure và lỗi rollback

Trong JDBC, khi một transaction thất bại giữa chừng, `rollback()` bản thân nó cũng có thể thất bại vì connection đã hỏng. Nếu chỉ viết:

~~~java
catch (SQLException original) {
    connection.rollback(); // rollback cũng có thể throw, làm mất original
    throw original;
}
~~~

lỗi rollback có thể **che mất lỗi SQL chính**. Cách xử lý an toàn hơn:

~~~java
catch (SQLException original) {
    try {
        connection.rollback();
    } catch (SQLException rollbackFailure) {
        original.addSuppressed(rollbackFailure);
    }
    throw original;
}
~~~

Nếu code cũng bắt `RuntimeException` trong transaction, nên áp dụng nguyên tắc tương tự: rollback rồi giữ ngoại lệ nghiệp vụ ban đầu, gắn lỗi rollback vào `addSuppressed()`.

Cần phân biệt **lỗi rollback** với **kết quả commit mơ hồ**: việc gọi rollback sau lỗi `commit()` không chứng minh rằng transaction trước đó chưa commit. Không ghi `rollback_success` nếu không có bằng chứng phù hợp.

### 5.3. Ví dụ transaction đầy đủ: không để cleanup che nguyên nhân

Ví dụ sau minh họa một transaction JDBC tự quản lý, rollback khi một bước bắt buộc thất bại và khôi phục `autoCommit` trước khi trả connection. Các framework như Spring có transaction manager riêng; không trộn hai cơ chế tùy tiện.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class PaymentWriter {
    private final DataSource dataSource;

    public PaymentWriter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void confirm(long paymentId) {
        try (Connection connection = dataSource.getConnection()) {
            boolean previousAutoCommit = connection.getAutoCommit();
            Throwable primary = null;

            try {
                connection.setAutoCommit(false);

                try (PreparedStatement statement = connection.prepareStatement(
                        "UPDATE payments SET status = 'CONFIRMED' "
                      + "WHERE id = ? AND status = 'PENDING'")) {
                    statement.setLong(1, paymentId);
                    if (statement.executeUpdate() != 1) {
                        throw new IllegalStateException(
                            "Payment not found or state changed");
                    }
                }

                connection.commit();
            } catch (SQLException | RuntimeException failure) {
                primary = failure;
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            } finally {
                try {
                    connection.setAutoCommit(previousAutoCommit);
                } catch (SQLException restoreFailure) {
                    if (primary != null) {
                        primary.addSuppressed(restoreFailure);
                    } else {
                        throw restoreFailure;
                    }
                }
            }
        } catch (SQLException cause) {
            throw new PersistenceFailure("confirmPayment", cause);
        }
    }
}
~~~

Ví dụ xử lý ngoại lệ để minh họa, chưa phải logic thanh toán sản xuất. Những điểm cần đọc kỹ:

- `primary` lưu lỗi chính khi có lỗi lúc chạy transaction. Lỗi rollback/khôi phục kết nối được gắn vào `suppressed` nếu đã có lỗi chính.
- `try-with-resources` bảo đảm `Connection.close()` được gọi; nếu đóng thất bại trong lúc đã có ngoại lệ, Java tiếp tục giữ lỗi đóng như suppressed.
- Nếu không có lỗi nghiệp vụ mà **khôi phục autoCommit thất bại**, nó trở thành một lỗi cần báo lên, không được nuốt.
- `PersistenceFailure` chỉ bọc `SQLException` với `cause`. Một `IllegalStateException` nghiệp vụ vẫn được ném nguyên dạng để tầng trên quyết định xử lý.
- Nếu `commit()` đã gửi nhưng trả lỗi do mạng, **kết quả commit có thể không chắc chắn**. Đừng tự kết luận rollback đã xóa toàn bộ thay đổi chỉ vì đã gọi `rollback()` sau đó.
- Trong hệ thống có connection pool, cần kiểm tra chính sách reset session và loại bỏ connection lỗi của pool. Đoạn mã không thể thay thế toàn bộ yêu cầu về lifecycle, logging và retry.

Với code thực, có thể đóng gói việc quản lý transaction vào lớp dùng chung để tránh mỗi repository tự thực hiện các nhánh rollback/cleanup phức tạp. Điều kiện quan trọng là lớp dùng chung **không làm mất exception ban đầu**.

## 6. SQLSTATE và mã lỗi: giữ nguyên nhưng không suy diễn quá mức

`SQLException.getSQLState()` trả mã chẩn đoán, thường dùng chuỗi năm ký tự theo quy ước SQLSTATE. `SQLException.getErrorCode()` trả mã riêng do vendor cung cấp. SQLSTATE có các nhóm thường được dùng để phân loại lỗi, nhưng chi tiết và mức hỗ trợ thay đổi theo DBMS, driver, kiểu thao tác và phiên bản.

Một số ví dụ **PostgreSQL**:

| SQLSTATE | Tình huống | Phản ứng ban đầu |
|---|---|---|
| `23505` | Vi phạm unique constraint | Kiểm tra xung đột nghiệp vụ hoặc idempotency; không retry mù |
| `23503` | Vi phạm foreign key | Xem dữ liệu và quy tắc tham chiếu; thường không phải lỗi tạm thời |
| `23502` | Vi phạm not-null | Kiểm tra dữ liệu đầu vào/mapping và schema |
| `40001` | Serialization failure | Có thể retry trọn transaction nếu nghiệp vụ cho phép |
| `40P01` | Deadlock detected | Có thể retry trọn transaction với giới hạn và backoff |
| `55P03` | Lock not available/lock timeout | Có thể báo đang bận hoặc retry theo SLA |
| `57014` | Query canceled (ví dụ statement timeout hoặc hủy từ bên ngoài) | Xác định nguồn hủy trước khi quyết định retry |
| `08006` | Connection failure | Điều tra kết nối; nếu xảy ra quanh COMMIT cần xử lý trạng thái không chắc chắn |
| `42P01` | Undefined table | Thường là lỗi schema/deployment, retry cùng SQL không sửa được |

Các mã này **không phải hợp đồng chung** cho MySQL, SQL Server và Oracle. Ví dụ SQL Server có vendor code riêng cho deadlock victim; MySQL/InnoDB thường dùng error 1213 cho deadlock. Cách xử lý phải dựa trên **DBMS + phiên bản + driver + vị trí xảy ra lỗi + ngữ nghĩa nghiệp vụ**.

### 6.1. Phân biệt phân loại kỹ thuật và quyết định retry

Một bộ phân loại chỉ nên trả về **gợi ý kỹ thuật**, còn service phải quyết định retry theo idempotency và trạng thái transaction:

~~~text
SQLException + DB metadata
         |
         v
classifier -> CONCURRENCY_RETRY_CANDIDATE / CONSTRAINT / CONNECTION / UNKNOWN
         |
         v
business use case:
  - Có thể lặp lại toàn transaction không?
  - Có tác dụng phụ nào đã thực hiện không?
  - Kết quả COMMIT đã xác định chưa?
  - Có ngân sách thời gian và số lần thử lại không?
         |
         v
RETRY / RECONCILE / REPORT CONFLICT / FAIL FAST
~~~

Chẳng hạn **connection failure** không có nghĩa retry an toàn trong mọi tình huống. Nếu nó xảy ra sau khi client gửi `COMMIT`, một lần retry có thể ghi trùng.

## 7. Retry cần giữ nguyên nguyên nhân của từng lần thất bại

Để xử lý lỗi tạm thời, ứng dụng có thể retry transaction có giới hạn:

~~~text
for attempt in 1..MAX_ATTEMPTS:
    begin new transaction
    try:
        read fresh business state
        validate conditions
        write changes
        commit
        return success
    catch recognized retryable concurrency failure:
        rollback if appropriate
        record attempt + original cause/diagnostic code
        if attempt == MAX_ATTEMPTS:
            propagate final failure with attempt context
        backoff with jitter
        start the whole transaction again
~~~

Chỉ retry **bước cuối** trong transaction đã thất bại thường không đúng: transaction có thể bị đánh dấu aborted, dữ liệu đã đọc trước đó đã cũ, hoặc các ràng buộc nghiệp vụ cần được đánh giá lại.

### 7.1. Có nên giữ toàn bộ lỗi của các lần thử?

Nếu retry thất bại nhiều lần, ngoại lệ cuối vẫn là bằng chứng gần thời điểm trả lỗi nhất. Ngoài ra, có thể giữ ngữ cảnh của những lần trước:

- Ghi một **sự kiện có cấu trúc cho mỗi attempt** ở mức log/tracing phù hợp, cùng trace ID và attempt number.
- Hoặc gắn các failure trước vào `suppressed` của lỗi cuối sau khi **lọc/giới hạn** số lượng, để có thể tra cứu chuỗi nguyên nhân.
- Không tạo một chuỗi exception vô hạn hoặc log toàn bộ stack ở mọi attempt khi lỗi lặp hàng nghìn lần; điều đó gây log storm và làm chậm hệ thống.

**Tuyệt đối tránh**:

~~~java
// Sai: exception cuối không giữ nguyên nhân thực tế.
throw new RuntimeException(
    "Retried three times and failed"
);
~~~

Nếu tạo ngoại lệ tổng hợp:

~~~java
// "lastFailure" là Throwable của lần cuối, đã bảo toàn cause.
throw new IllegalStateException(
    "Storage operation failed after 3 attempts",
    lastFailure
);
~~~

Đối với những lần thử trước, có thể ghi một sự kiện ngắn gồm SQLSTATE, mã vendor, thời điểm, độ trễ, loại lỗi. Chỉ giữ/ghi stack trace chi tiết ở một điểm quan sát có kiểm soát nếu cần. Đừng đưa lỗi thô vào response công khai.

### 7.2. Retry có thể đổi nghĩa nghiệp vụ

Giả sử thao tác “trừ tồn kho một đơn vị” đã commit, nhưng phản hồi `COMMIT` bị mất. Nếu request tự retry, kho có thể bị trừ hai lần. Khả năng retry phải phụ thuộc **tính idempotent** và một cơ chế xác nhận trạng thái.

Một thiết kế thường dùng:

~~~sql
CREATE TABLE processed_commands (
    operation_id UUID PRIMARY KEY,
    result_code TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Ý tưởng là gắn một `operation_id` ổn định theo lệnh nghiệp vụ, ghi nhận kết quả **cùng transaction** với các thay đổi dữ liệu. Khi retry/đối soát, truy vấn theo `operation_id` để xác định lệnh đã xử lý hay chưa.

Bảng ví dụ chỉ minh họa điểm móc idempotency, **chưa đủ** để triển khai hoàn chỉnh: cần thiết kế trình tự claim/ghi, ràng buộc unique, khả năng cạnh tranh, trạng thái lỗi, lưu kết quả và chính sách cleanup. Nếu kết quả mơ hồ, ứng dụng phải **đối soát** thay vì khẳng định rollback thành công.

## 8. Bảo mật: giữ ngữ cảnh không đồng nghĩa ghi mọi dữ liệu

Thông điệp của driver có thể chứa:

- SQL với literal/giá trị tham số.
- Tên bảng, cột, constraint hoặc tên schema nội bộ.
- Địa chỉ host, tên database, tên user hoặc chuỗi kết nối.
- Dữ liệu có khả năng nhận dạng người dùng.
- Thông tin về topology hoặc cấu hình bảo mật.

Do đó cần tách **bằng chứng kỹ thuật nội bộ** khỏi **thông tin trả cho client**.

### 8.1. Ví dụ log an toàn và response gọn

Mẫu log phía server (minh họa):

~~~text
event=storage_failure
trace_id=req-9ab27
operation=confirmPayment
db_role=primary
sql_state=40P01
vendor_code=0
attempt=1
retry_candidate=true
elapsed_ms=482
~~~

API trả phản hồi có mã lỗi ổn định:

~~~json
{
  "code": "STORAGE_TEMPORARILY_UNAVAILABLE",
  "message": "Không thể hoàn tất thao tác lúc này.",
  "traceId": "req-9ab27"
}
~~~

**Client không cần nhận `SQLException.toString()` hoặc stack trace.** Tầng vận hành cần đủ thông tin để truy vết, nhưng nên kiểm soát quyền truy cập log, thời gian lưu, che thông tin nhạy cảm và chính sách dữ liệu cá nhân.

### 8.2. Không đặt dữ liệu người dùng vào metric label

Với metric/timeseries, các nhãn nên có số lượng giá trị hữu hạn, ví dụ `operation=confirmPayment`, `error_class=deadlock`, `db_role=primary`. Không dùng `customer_id`, SQL nguyên văn, exception message, request ID hoặc stack trace làm label có cardinality cao.

Trace ID có thể nằm trong log/span sự kiện để truy vết cá thể, nhưng thường không nên là nhãn metric.

### 8.3. SQL text và tham số

Trong log ở mức sản xuất, nên ưu tiên **query name/fingerprint** (cấu trúc SQL không chứa giá trị người dùng) thay cho câu SQL có nhúng giá trị. `PreparedStatement` giảm nguy cơ SQL injection khi dùng đúng, nhưng không tự bảo đảm mọi driver log sẽ ẩn tham số. Đừng mặc định thông điệp lỗi của DBMS đã được làm sạch.

## 9. Logging một lần ở ranh giới hợp lý

Một lỗi đi qua repository, service, controller và exception handler. Nếu mỗi tầng đều gọi `logger.error(..., exception)` rồi ném tiếp, ta có thể nhận **bốn stack trace cho cùng một sự cố**. Điều này:

- Làm tăng dung lượng log và gây nhiễu khi điều tra.
- Khiến dashboard đếm nhầm một request thành nhiều lỗi độc lập.
- Có thể bộc lộ thêm thông tin ở các tầng không nên ghi dữ liệu.

Cách tiếp cận thường tốt hơn:

1. Ở tầng thấp, **bọc lỗi với cause và bổ sung ngữ cảnh** khi thực sự cần.
2. Ở service, xác định chính sách xử lý và retry; có thể ghi log ngắn cho attempt nếu cần.
3. Ở ranh giới request/job, ghi **một sự kiện đầy đủ** cho lỗi cuối (cùng trace ID và exception chain), ánh xạ ra kết quả an toàn cho caller.

Đây là hướng thiết kế phổ biến, không phải quy tắc cứng. Có lúc tầng thấp cần log sự kiện không còn được ném ra ngoài, chẳng hạn lỗi background cleanup, nhưng phải có mục đích rõ ràng.

### 9.1. Lỗi bị nuốt gây nguy hiểm hơn log trùng

Ví dụ sai:

~~~java
try {
    repository.save(entity);
} catch (Exception error) {
    logger.warn("Ignored storage error");
}
return Success.INSTANCE;
~~~

Nếu persistence thất bại nhưng API vẫn trả thành công, hệ thống đã vi phạm hợp đồng nghiệp vụ. Nếu buộc phải áp dụng *best effort* (ví dụ cập nhật cache phụ), cần xác định rõ kết quả không bắt buộc, ghi metric/thông báo phù hợp và tránh trả một trạng thái thành công sai cho phần dữ liệu chính.

Không bắt `Exception` hoặc `Throwable` quá rộng chỉ để biến mọi lỗi thành một giá trị mặc định. Những lỗi lập trình như `NullPointerException` cần được xử lý khác với lỗi tạm thời của DB.

## 10. Những điểm dễ mất nguyên nhân ở môi trường bất đồng bộ

Trong Java, lỗi từ tác vụ bất đồng bộ có thể được bao bởi `CompletionException` hoặc `ExecutionException`. Khi chuyển lỗi, đừng bỏ qua `cause`:

~~~java
try {
    future.join();
} catch (java.util.concurrent.CompletionException failure) {
    Throwable cause = failure.getCause();
    // Quyết định chuyển lỗi và log đúng ngữ cảnh.
    // Không tạo exception mới chỉ bằng cause.getMessage().
    throw failure;
}
~~~

Ở trường hợp gọi blocking `Future.get()`, `InterruptedException` có nghĩa luồng bị yêu cầu ngắt. Nếu quyết định không ném tiếp ở giao diện hiện tại, cần khôi phục cờ ngắt qua `Thread.currentThread().interrupt()` và kết thúc công việc theo chính sách phù hợp; không biến interruption thành một lỗi DB ngẫu nhiên rồi retry.

Phần bất đồng bộ còn cần **truyền trace/correlation context** qua thread và task boundaries. Không mặc định MDC/ThreadLocal được kế thừa qua mọi executor. Nếu thiếu context propagation, stack trace vẫn tồn tại nhưng mất liên hệ với request ban đầu.

## 11. Chẩn đoán theo nguyên nhân và ngữ cảnh

Ví dụ production incident:

~~~text
14:02:07  POST /payments/confirm   trace=req-81b
14:02:07  attempt=1; operation=confirmPayment
14:02:08  SQLException SQLSTATE=40P01 deadlock
14:02:08  rollback completed; retry scheduled
14:02:08  attempt=2 starts new transaction
14:02:09  SQLException SQLSTATE=23505 unique violation
14:02:09  operation failed; no blind retry
~~~

Nếu chỉ giữ lỗi cuối, người xem biết có `23505`. Nếu giữ ngữ cảnh attempt và cause, người xem còn biết đã xảy ra deadlock ở attempt đầu rồi một xung đột unique ở attempt kế tiếp. Điều này có thể chỉ ra hai đường code cùng tạo dữ liệu, thiếu idempotency hoặc ngữ nghĩa retry chưa phù hợp.

**Quy trình điều tra gợi ý:**

1. Xác định trace ID, operation, thời gian và phiên bản ứng dụng đang chạy.
2. Đọc ngoại lệ cuối, `cause`, `suppressed`, `getNextException()` và mã SQLSTATE/vendor theo DBMS.
3. Đặt lỗi vào đúng thời điểm: lấy connection, chuẩn bị statement, thực thi SQL, commit, rollback hay close?
4. Kiểm tra transaction đã kết thúc, bị rollback hay có kết quả **chưa chắc chắn**.
5. So sánh với DB logs, thời gian chờ khóa, deadlock, pool metric, network và deployment gần thời điểm lỗi.
6. Xác định giải pháp: sửa dữ liệu/schema/query, thay ranh giới transaction, giảm tranh chấp, xử lý kết nối, hay thiết kế idempotency.
7. Chỉ sau khi có cơ sở mới đưa ra retry policy hoặc mapping lỗi cho caller.

Không kết luận mọi `SQLSTATE 08xxx` đều có thể retry y nguyên thao tác: ở ranh giới `COMMIT`, cần xác định hậu quả của lần thử trước.

## 12. Bảng xử lý tình huống

| Tình huống | Lỗi ban đầu | Ngữ cảnh cần giữ | Hành động thường phù hợp |
|---|---|---|---|
| Ghi trùng email | Unique violation | Constraint/operation, user-facing code an toàn | Trả xung đột, không retry mù |
| Giao dịch bị deadlock | Deadlock SQLSTATE/vendor | Transaction scope, attempt, rollback result | Retry **toàn transaction** có giới hạn |
| SERIALIZABLE bị abort | Serialization failure | Lịch cạnh tranh, attempt, dữ liệu đọc lại | Rollback và đánh giá lại từ đầu |
| Lệnh bị statement timeout | Query canceled | Query name, elapsed, DB load, wait type | Điều tra SQL/DB; retry tùy SLA |
| Không lấy được connection | Pool acquisition timeout | Active/idle/pending, pool size, request context | Điều tra pool/transaction dài, kiểm soát tải |
| Driver mất kết nối trước query | Connection failure | Giai đoạn lỗi, endpoint, vendor code | Có thể mở lại kết nối theo chính sách |
| Mất kết nối lúc COMMIT | Network/connection error | Operation ID, trạng thái commit chưa biết | Đối soát/idempotency trước khi gửi lại |
| Rollback cũng lỗi | Lỗi SQL chính và rollback failure | Cause và suppressed | Báo lỗi chính, giữ lỗi rollback làm bằng chứng |
| Lỗi cleanup | Close/reset failure | Connection/session state, suppressed | Kiểm tra pool/driver, không che lỗi nghiệp vụ |

## 13. Bài tập tự kiểm tra

### Bài 1: Chọn cách ném lỗi

Repository có đoạn:

~~~java
catch (SQLException e) {
    throw new RuntimeException(e.getMessage());
}
~~~

**Câu hỏi:** Lỗi gì bị mất? Hãy sửa.

**Gợi ý:** Mất `cause`, stack của `SQLException`, thông tin driver có thể truy ngược qua đối tượng và chuỗi `nextException`. Sửa thành `throw new PersistenceFailure("saveOrder", e)` hoặc `new RuntimeException("saveOrder failed", e)`.

### Bài 2: Lỗi rollback che lỗi chính

Câu SQL đầu thất bại với `23503`, sau đó `connection.rollback()` báo connection failure. Nếu code chỉ ném ngoại lệ rollback, người vận hành sẽ thấy gì? Sửa thế nào?

**Gợi ý:** Người xem không biết lỗi vi phạm foreign key đầu tiên. Giữ lỗi SQL ban đầu làm primary và gắn rollback failure qua `addSuppressed()`.

### Bài 3: Có thể retry 40P01 không?

PostgreSQL báo `40P01` cho một transaction cập nhật tồn kho. Service đang chạy thêm việc gửi thông báo bên ngoài trước commit.

**Gợi ý:** Deadlock là ứng viên retry **trọn transaction**, nhưng gửi thông báo trong phạm vi có thể retry gây tác dụng phụ lặp. Chuyển thông báo sang outbox/idempotent delivery rồi áp dụng retry có giới hạn.

### Bài 4: SQLSTATE 23505 trong request lặp

Hai request cùng dùng operation ID tạo đơn. Request đầu đã commit; request thứ hai gặp unique violation trên operation ID.

**Gợi ý:** Không tự động kết luận request thứ hai thất bại nghiệp vụ. Có thể đọc kết quả đã lưu của operation ID và trả lại nếu nội dung request tương đương và hợp đồng idempotency cho phép.

### Bài 5: Mất kết nối sau COMMIT

Ứng dụng gửi `COMMIT` rồi mất mạng trước phản hồi. Lỗi có `SQLSTATE` lớp `08`. Có chắc giao dịch bị rollback không?

**Gợi ý:** Không. Trạng thái là chưa chắc chắn. Cần đối soát theo operation ID và cơ chế idempotency, không retry ghi mù.

### Bài 6: Ngữ cảnh log

Một log chứa cả mật khẩu DB trong JDBC URL và số thẻ khách hàng trong SQL parameters. Log có đầy đủ thông tin chẩn đoán nhưng có đạt yêu cầu không?

**Gợi ý:** Không. Giữ SQLSTATE, mã vendor, operation, trace ID và query fingerprint; xóa/che bí mật, giảm chi tiết tham số, kiểm soát quyền truy cập và thời gian lưu log.

### Bài 7: Cùng lỗi được log bốn lần

Một `SQLException` được repository, service, controller và global exception handler cùng ghi `logger.error` với stack trace.

**Gợi ý:** Giữ cause khi chuyển tầng; ưu tiên log chi tiết tại một ranh giới phù hợp, dùng span/metric có cấu trúc để theo dõi các lần retry hoặc kết quả được xử lý trung gian.

## 14. Ghi nhớ

- **Không chỉ giữ message.** Hãy bảo toàn exception object thông qua `cause`; dùng `suppressed` để giữ lỗi rollback/close và xem cả `SQLException.getNextException()` khi cần.
- **Lỗi cần ngữ cảnh.** Tên operation, trace ID, SQLSTATE, vendor code, attempt, ranh giới transaction và giai đoạn xảy ra lỗi làm cho việc chẩn đoán có cơ sở.
- **Bảo toàn không đồng nghĩa phơi bày.** Log nội bộ có kiểm soát phải tách khỏi response client; không ghi credential, tham số nhạy cảm hoặc SQL chứa dữ liệu cá nhân một cách vô tội vạ.
- **Phân loại lỗi trước khi retry.** Unique/constraint violation thường cần xử lý dữ liệu/nghiệp vụ; deadlock/serialization có thể thử lại **cả transaction**; mất kết nối quanh COMMIT cần đối soát.
- **Không che lỗi ban đầu bằng cleanup.** Nếu rollback, reset trạng thái hay close cũng thất bại, lưu những lỗi phụ để điều tra nhưng giữ được lỗi gây sự cố chính.
- **Quan sát theo transaction.** Một chuỗi lỗi đầy đủ cùng trạng thái commit/rollback và các lần thử lại giúp phục hồi chính xác hơn một thông báo “Database failed” chung chung.

Giữ nguyên nguyên nhân và ngữ cảnh của lỗi lưu trữ giúp hệ thống Java vừa **dễ vận hành và dễ kiểm chứng**, vừa tránh các quyết định retry làm thay đổi dữ liệu sai. Khi có sự cố, hãy để ngoại lệ giữ bằng chứng kỹ thuật, service giữ quyết định nghiệp vụ, và API chỉ công bố thông tin mà client thực sự cần.
