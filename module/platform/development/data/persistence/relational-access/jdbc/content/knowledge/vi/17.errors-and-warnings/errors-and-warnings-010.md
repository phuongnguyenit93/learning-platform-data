# Chuyển ngoại lệ JDBC thành lỗi của lớp truy cập dữ liệu

Khi Java truy cập cơ sở dữ liệu quan hệ qua **JDBC**, lỗi có thể xảy ra tại `DataSource.getConnection()`, `PreparedStatement.executeUpdate()`, `ResultSet.next()`, `Connection.commit()` hoặc lúc đóng tài nguyên. JDBC chủ yếu biểu diễn lỗi bằng `SQLException` và các lớp con. Nếu tầng nghiệp vụ phải đọc trực tiếp `SQLState` hoặc mã của từng driver, ứng dụng sẽ khó bảo trì, khó thay đổi hệ quản trị và dễ để lộ chi tiết kỹ thuật ra API.

Trong chương **Lỗi và cảnh báo**, bài này hướng dẫn **chuyển ngoại lệ JDBC thành lỗi thống nhất của lớp truy cập dữ liệu** (*exception translation*). Ta sẽ thiết kế ranh giới giữa DAO/repository và service, phân loại lỗi từ `SQLException`, giữ nguyên nguyên nhân gốc để chẩn đoán, đồng thời quản lý rollback, retry, batching và `SQLWarning` đúng trách nhiệm. Ví dụ sử dụng API chuẩn của Java, JDBC, `DataSource`, `PreparedStatement` và `ResultSet`; không cần ORM.

## 1. Tại sao không truyền thẳng `SQLException` qua mọi tầng?

Xem chữ ký sau:

```java
public Customer findById(long id) throws SQLException {
    // JDBC query...
}
```

Nếu các service, controller và API gọi phương thức trên đều phải xử lý `SQLException`, chúng sẽ phụ thuộc trực tiếp vào cách driver báo lỗi. Có thể có mã `SQLState` riêng, mã số của database và thông điệp chứa SQL hoặc tên bảng. Một controller không nên quyết định “email đã tồn tại” chỉ vì tìm thấy từ `duplicate` trong `SQLException.getMessage()`.

Mô hình phù hợp hơn:

```text
Ứng dụng / HTTP
       ▲    trả lỗi nghiệp vụ đã xác minh hoặc mã sự cố
       │
     Service
       ▲    xử lý quy tắc nghiệp vụ, transaction, retry
       │
  DataAccessFailure
       ▲    lỗi thống nhất + SQLException gốc trong cause
       │
DAO / Repository
       ▲    SQL tham số hóa, map ResultSet, chuyển lỗi
       │
JDBC driver / Database
       └──── SQLException, SQLState, vendorCode
```

DAO chuyển lỗi **kỹ thuật của thao tác dữ liệu**. Service hiểu **ý nghĩa nghiệp vụ** và quyết định có trả xung đột cho người dùng, tiếp tục hay thử lại. Chuyển đổi ngoại lệ **không tự rollback** hoặc tự chữa lỗi kết nối; đó là trách nhiệm tách biệt.

Cũng không phải mọi kết quả “không thành công” là ngoại lệ JDBC:

- `SELECT` không có dòng có thể trả `Optional.empty()`.
- `UPDATE` ảnh hưởng `0` dòng có thể là “không tìm thấy bản ghi” hoặc xung đột phiên bản. DAO nên trả số hàng hoặc lỗi nghiệp vụ đã được định nghĩa rõ.
- Dữ liệu nhập sai định dạng được phát hiện trước khi thực thi SQL thường thuộc phần xác thực đầu vào; không cần cố tạo `SQLException` để biểu diễn.

## 2. Những thông tin phải đọc từ `SQLException`

`SQLException` chứa nhiều thông tin hơn một thông điệp:

| API | Giá trị trả về | Dùng để làm gì |
| --- | --- | --- |
| `getClass()` | Lớp chuyên biệt nếu driver dùng | Phân biệt timeout, constraint, lỗi kết nối, rollback transaction... |
| `getSQLState()` | Mã SQLState, có thể `null` | Phân loại lỗi theo lớp SQLState được driver báo |
| `getErrorCode()` | Số nguyên do nhà cung cấp định nghĩa | Nhận diện lỗi cụ thể **trong đúng driver/hệ quản trị** |
| `getNextException()` | Ngoại lệ tiếp theo trong chuỗi JDBC | Đọc nhiều lỗi liên quan, thường có ích với batch |
| `getCause()` | Nguyên nhân theo Java exception chaining | Giữ thông tin lỗi cấp thấp |
| `getSuppressed()` | Những lỗi phụ, chẳng hạn khi đóng resource | Không đánh mất lỗi cleanup của `try-with-resources` |
| `getMessage()` | Thông điệp do driver/server tạo | Chẩn đoán nội bộ; có thể chứa thông tin nhạy cảm |

**Hai ký tự đầu của SQLState** thường thể hiện lớp lỗi; tuy vậy mã có thể vắng mặt, tuân theo quy ước nhà cung cấp hoặc được driver ánh xạ khác nhau:

| SQLState class | Ý nghĩa thường gặp | Không nên suy diễn |
| --- | --- | --- |
| `08` | Connection exception | Mọi lần chạy lại đều an toàn |
| `22` | Data exception, sai kiểu hoặc chuyển đổi | Chắc chắn lỗi thuộc đầu vào người dùng |
| `23` | Integrity constraint violation | Chắc chắn trùng email/unique key |
| `40` | Transaction rollback | Mọi mã thuộc nhóm đều có thể retry vô điều kiện |
| `42` | SQL syntax **hoặc access rule** | Chỉ là sai cú pháp, không thể liên quan quyền |
| `0A` | Feature not supported | Có thể giải quyết bằng retry |
| `23505` | Unique violation, ví dụ với PostgreSQL | Mọi driver dùng cùng mã cho mọi unique violation |
| `40001` | Serialization failure ở nhiều hệ quản trị | Chỉ cần thử lại một câu SQL cuối |

Ví dụ khi `getSQLState()` bắt đầu bằng `23`: kết luận hợp lý là **vi phạm ràng buộc**; muốn kết luận **ràng buộc unique của cột email** cần biết lỗi cụ thể và schema đang dùng.

Một hàm chẩn đoán chuỗi ngoại lệ:

```java
import java.sql.SQLException;

public static void inspect(SQLException root) {
    int i = 0;
    for (SQLException current = root;
         current != null && i < 20;
         current = current.getNextException(), i++) {
        System.err.println(
                "JDBC[" + i + "] class="
                + current.getClass().getSimpleName()
                + ", SQLState=" + current.getSQLState()
                + ", vendorCode=" + current.getErrorCode());
    }

    for (Throwable suppressed : root.getSuppressed()) {
        System.err.println("Cleanup error: "
                + suppressed.getClass().getSimpleName());
    }
}
```

Đoạn in mã lỗi chỉ để minh họa. Ứng dụng sản phẩm nên dùng log nội bộ có phân quyền, request/trace ID và chính sách che dữ liệu; không tự in nguyên SQL, tham số nhạy cảm hay thông điệp database ra phản hồi công khai.

## 3. Các lớp con của `SQLException` và ý nghĩa thực tế

JDBC cung cấp hệ phân cấp giúp phân loại ngay cả khi `SQLState=null`:

| Kiểu ngoại lệ | Cách hiểu | Cần chú ý |
| --- | --- | --- |
| `SQLTransientException` | Có thể nguyên nhân tạm thời biến mất | Không bảo đảm retry thao tác có tác dụng phụ sẽ an toàn |
| `SQLTransientConnectionException` | Lỗi kết nối có tính tạm thời | Có thể cần một kết nối mới |
| `SQLNonTransientConnectionException` | Lỗi kết nối khó tự hết khi lặp y nguyên | Kiểm tra cấu hình, quyền hoặc trạng thái server |
| `SQLTransactionRollbackException` | Transaction bị hủy, ví dụ serialization/deadlock | Khi retry phải xét lại **toàn bộ transaction** |
| `SQLIntegrityConstraintViolationException` | Vi phạm ràng buộc dữ liệu | Chưa đủ để biết unique, foreign key, check, not null |
| `SQLDataException` | Dữ liệu/ép kiểu không hợp lệ | Có thể do schema hoặc tham số |
| `SQLSyntaxErrorException` | SQL hoặc quy tắc truy cập không hợp lệ | Sửa câu SQL/quyền, không retry giống hệt |
| `SQLTimeoutException` | JDBC operation vượt thời gian cho phép | Kết quả thao tác ở server có thể chưa xác định |
| `SQLFeatureNotSupportedException` | Tính năng/API không hỗ trợ | Thay cách làm hoặc driver |
| `SQLRecoverableException` | Cần bước khôi phục, thường như tái lập kết nối | Không mặc định dùng lại kết nối cũ |

Một driver có thể ném lớp con chuyên biệt, hoặc ném `SQLException` thông thường kèm SQLState/vendor code. Translator nên dựa vào **loại ngoại lệ và SQLState**, rồi có thể bổ sung quy tắc riêng cho driver đã kiểm chứng. Phân loại theo chuỗi `getMessage()` rất dễ vỡ khi phiên bản server hoặc ngôn ngữ thông điệp thay đổi.

## 4. Xây dựng lỗi chung cho lớp truy cập dữ liệu

Có hai hướng thiết kế quen thuộc: một lớp `DataAccessException` với mã loại lỗi, hoặc hệ thống lớp con như `ConstraintViolationException`, `ConnectionFailureException`, `TransactionAbortedException`. Ví dụ sau chọn **một unchecked exception** có trường `Kind`. Điều này tránh bắt buộc tầng gọi khai báo `throws SQLException`, đồng thời cho phép giữ `SQLException` gốc.

Tạo tệp Java `SqlErrorTranslator.java` trong ứng dụng:

```java
import java.sql.SQLException;
import java.sql.SQLDataException;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.SQLIntegrityConstraintViolationException;
import java.sql.SQLNonTransientConnectionException;
import java.sql.SQLRecoverableException;
import java.sql.SQLSyntaxErrorException;
import java.sql.SQLTimeoutException;
import java.sql.SQLTransactionRollbackException;
import java.sql.SQLTransientConnectionException;
import java.util.Objects;

public final class SqlErrorTranslator {
    private SqlErrorTranslator() {
    }

    public enum Kind {
        CONNECTION_FAILURE,
        CONSTRAINT_VIOLATION,
        TRANSACTION_ABORTED,
        INVALID_DATA,
        INVALID_SQL_OR_ACCESS_RULE,
        TIMEOUT,
        UNSUPPORTED_FEATURE,
        OTHER
    }

    public static final class DataAccessFailure extends RuntimeException {
        private final Kind kind;
        private final String sqlState;
        private final int vendorCode;

        private DataAccessFailure(
                Kind kind, String operation, SQLException cause) {
            // operation là tên thao tác cố định do DAO cung cấp.
            super("Data access failure during " + operation
                    + " [" + kind + "]", cause);
            this.kind = kind;
            this.sqlState = cause.getSQLState();
            this.vendorCode = cause.getErrorCode();
        }

        public Kind getKind() {
            return kind;
        }

        public String getSqlState() {
            return sqlState;
        }

        public int getVendorCode() {
            return vendorCode;
        }
    }

    public static DataAccessFailure translate(
            String operation, SQLException cause) {
        Objects.requireNonNull(operation, "operation");
        Objects.requireNonNull(cause, "cause");

        Kind kind = classify(cause);
        SQLException next = cause.getNextException();
        int inspected = 0;

        // Một số driver chuyển chi tiết lỗi sang nextException.
        while (kind == Kind.OTHER && next != null && inspected < 20) {
            kind = classify(next);
            next = next.getNextException();
            inspected++;
        }

        // Cause giữ nguyên chuỗi nextException/suppressed gốc.
        return new DataAccessFailure(kind, operation, cause);
    }

    private static Kind classify(SQLException error) {
        String state = error.getSQLState();

        if (error instanceof SQLTimeoutException) {
            return Kind.TIMEOUT;
        }
        if (error instanceof SQLFeatureNotSupportedException
                || stateClass(state, "0A")) {
            return Kind.UNSUPPORTED_FEATURE;
        }
        if (error instanceof SQLTransientConnectionException
                || error instanceof SQLNonTransientConnectionException
                || error instanceof SQLRecoverableException
                || stateClass(state, "08")) {
            return Kind.CONNECTION_FAILURE;
        }
        if (error instanceof SQLTransactionRollbackException
                || stateClass(state, "40")) {
            return Kind.TRANSACTION_ABORTED;
        }
        if (error instanceof SQLIntegrityConstraintViolationException
                || stateClass(state, "23")) {
            return Kind.CONSTRAINT_VIOLATION;
        }
        if (error instanceof SQLDataException
                || stateClass(state, "22")) {
            return Kind.INVALID_DATA;
        }
        if (error instanceof SQLSyntaxErrorException
                || stateClass(state, "42")) {
            return Kind.INVALID_SQL_OR_ACCESS_RULE;
        }
        return Kind.OTHER;
    }

    private static boolean stateClass(String state, String prefix) {
        return state != null && state.startsWith(prefix);
    }
}
```

Các quyết định có chủ đích trong ví dụ:

- `DataAccessFailure` dùng `super(message, cause)`, vì vậy có thể truy lại **đối tượng `SQLException` gốc**, bao gồm `nextException` và `suppressed`. Không tạo một ngoại lệ mới rồi làm mất quan hệ `cause`.
- `Kind` là **nhóm kỹ thuật**, không khẳng định ý nghĩa nghiệp vụ. `CONSTRAINT_VIOLATION` không tự là “email đã tồn tại”.
- `SQLState` có thể `null` nên `stateClass(...)` phải kiểm tra trước khi dùng `startsWith(...)`.
- `OTHER` là nhóm chưa phân loại; không biến lỗi chưa hiểu thành lỗi “tạm thời”.
- Việc xem tối đa 20 `nextException` là giới hạn đơn giản cho ví dụ. Trong mã sản phẩm có thể thêm kiểm tra chuỗi vòng lặp và chi tiết vendor-specific.
- `operation` phải là nhãn cố định như `customer.insert`, không lấy nguyên câu SQL hay dữ liệu người dùng làm thông điệp exception.

Translator này mô tả **phân loại cơ bản**; mỗi hệ quản trị có thể cần thêm quy tắc dựa trên vendor code, tên ràng buộc hoặc lớp ngoại lệ cụ thể. Những quy tắc đó cần thử nghiệm trên phiên bản driver và schema thực tế, rồi ánh xạ về hợp đồng chung thay vì để service trực tiếp gọi mã vendor.

## 5. Áp dụng translator ở ranh giới DAO

Ví dụ `CustomerDao` sử dụng `DataSource`, SQL tham số hóa bằng `PreparedStatement`, đọc `ResultSet` và bắt `SQLException` **bên ngoài khối try-with-resources**:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import java.util.Optional;

public final class CustomerDao {
    private final DataSource dataSource;

    public CustomerDao(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public Optional<Customer> findById(long id) {
        String sql = "SELECT id, email FROM customers WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }
                return Optional.of(new Customer(
                        rs.getLong("id"), rs.getString("email")));
            }
        } catch (SQLException failure) {
            throw SqlErrorTranslator.translate(
                    "customer.findById", failure);
        }
    }

    public void insert(long id, String email) {
        String sql = "INSERT INTO customers (id, email) VALUES (?, ?)";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);
            statement.setString(2, email);

            int affectedRows = statement.executeUpdate();
            if (affectedRows != 1) {
                throw new IllegalStateException(
                        "Expected one inserted customer, got "
                        + affectedRows);
            }
        } catch (SQLException failure) {
            throw SqlErrorTranslator.translate(
                    "customer.insert", failure);
        }
    }

    public static final class Customer {
        private final long id;
        private final String email;

        public Customer(long id, String email) {
            this.id = id;
            this.email = email;
        }

        public long getId() {
            return id;
        }

        public String getEmail() {
            return email;
        }
    }
}
```

Giả sử bảng `customers` có hai cột `id BIGINT PRIMARY KEY` và `email VARCHAR(...)`. Khi `SELECT` không có kết quả, DAO trả `Optional.empty()`. Khi `INSERT` gây `SQLException`, DAO chuyển lỗi thành `DataAccessFailure`. Khi số hàng bị tác động không đúng hợp đồng thao tác chèn một dòng, ví dụ chọn `IllegalStateException` riêng; điều đó không đồng nghĩa driver đã ném `SQLException`.

**Vì sao đặt `catch` ngoài `try-with-resources`?** Nếu một thao tác `close()` trên `ResultSet`, statement hoặc connection ném `SQLException`, ngoại lệ ấy cũng được xử lý. Nếu có một lỗi SQL chính trước đó, Java có thể giữ lỗi đóng tài nguyên trong `suppressed` của lỗi chính, và translator không làm mất chuỗi đó.

Khi DAO **tự lấy connection** và chạy một lệnh đơn, nó có thể để kết nối ở chế độ `autoCommit` mặc định do cấu hình cung cấp. Với nghiệp vụ nhiều bước trong **một transaction**, DAO nên có phương thức nhận `Connection` từ tầng sở hữu transaction; không tự lấy kết nối mới giữa các lệnh rồi phá vỡ tính nguyên tử.

## 6. Đừng nhầm lỗi dữ liệu với lỗi nghiệp vụ

Service có thể xử lý `Kind` của lỗi truy cập dữ liệu:

```java
try {
    customerDao.insert(101L, "lan@example.com");
} catch (SqlErrorTranslator.DataAccessFailure failure) {
    switch (failure.getKind()) {
        case CONSTRAINT_VIOLATION:
            // Chưa thể kết luận đây là trùng email:
            // có thể là PRIMARY KEY, CHECK, FOREIGN KEY...
            throw failure;
        case CONNECTION_FAILURE:
        case TIMEOUT:
            // Kết quả INSERT ở server có thể chưa rõ.
            throw failure;
        case TRANSACTION_ABORTED:
            // Có thể cần làm lại toàn bộ transaction
            // theo chính sách retry có giới hạn.
            throw failure;
        default:
            throw failure;
    }
}
```

Ví dụ này trình bày **cách nhận diện nhóm lỗi**, chưa thiết lập quy tắc trả HTTP. Muốn trả thông báo “email đã đăng ký”, service cần biết rõ lỗi xảy ra do **ràng buộc unique cụ thể của email**, qua quy tắc database-specific đã được kiểm chứng. Không thể suy ra điều đó chỉ từ SQLState class `23`.

Có thể phát triển hợp đồng thành các lớp con như `ConstraintViolationException`, `ConnectionFailureException`, `TransactionAbortedException`... nếu dự án muốn `catch` theo loại. Dù chọn enum hay phân cấp lớp, điểm nhất quán cần giữ là **không bắt tầng gọi xử lý `SQLException` trực tiếp và không làm mất nguyên nhân gốc**.

## 7. Chuyển lỗi phải phối hợp với rollback và retry

**Translation chỉ đổi cách biểu diễn lỗi.** Transaction vẫn phải được kết thúc ở tầng sở hữu `Connection`. Với `autoCommit=false`, nếu một lệnh `UPDATE` thứ hai lỗi sau khi lệnh thứ nhất thành công, chỉ `throw` ngoại lệ mới **không hoàn tác** các thay đổi đã thực hiện.

Minh họa thứ tự đúng trong một scope đã **sở hữu transaction và có `autoCommit=false`**:

```java
try {
    debitAndCredit(connection); // Có thể ném SQLException.
    connection.commit();
} catch (SQLException original) {
    try {
        connection.rollback();
    } catch (SQLException rollbackFailure) {
        original.addSuppressed(rollbackFailure);
    }
    throw SqlErrorTranslator.translate(
            "money.transfer", original);
}
```

Đây là **đoạn lõi** chứ chưa phải toàn bộ phần mở, đóng và phục hồi trạng thái kết nối. Nếu rollback thất bại, trạng thái transaction chưa rõ. Không bật lại `setAutoCommit(true)` một cách máy móc vì thao tác chuyển từ `false` sang `true` có thể commit transaction đang hoạt động. Kết nối đáng ngờ phải được pool vô hiệu hóa theo cơ chế riêng. Nếu `commit()` mất liên lạc sau khi server đã commit, một lời gọi rollback tiếp theo cũng không chứng minh thao tác ban đầu chưa diễn ra.

### Phân biệt nhóm lỗi và chính sách retry

| Lỗi | Xử lý mặc định | Retry khi nào |
| --- | --- | --- |
| Constraint violation (`23`) | Xác định ràng buộc và sửa dữ liệu/quy tắc nghiệp vụ | Chỉ khi điều kiện thực sự thay đổi; lặp cùng tham số thường tiếp tục lỗi |
| Syntax/access violation (`42`) | Kiểm tra SQL, schema và quyền | Không retry nguyên trạng khi SQL sai |
| Transaction rollback (`40`) | Rollback, đánh giá xung đột | Có thể retry **toàn bộ transaction** với giới hạn số lần và backoff |
| Connection failure (`08`) | Không dùng lại connection lỗi nếu chưa khôi phục | Chỉ khi biết trạng thái thao tác hoặc có idempotency/đối soát |
| Timeout | Điều tra thời điểm lỗi và trạng thái server | Không tự lặp lại `INSERT`/`UPDATE` khi kết quả commit chưa chắc chắn |
| Unsupported feature (`0A`) | Đổi API, SQL hoặc driver | Không retry y nguyên |
| Lỗi không rõ (`OTHER`) | Ghi nhận, báo lỗi phù hợp | Không mặc định có thể retry |

`SQLTransientException` là gợi ý có thể thử lại **sau khi nguyên nhân thay đổi**, nhưng không bảo đảm retry mọi thao tác là an toàn. Với nghiệp vụ có gửi email, thanh toán hoặc sự kiện, cần thiết kế idempotency key, outbox hoặc cơ chế tương đương trước khi retry. Tránh retry vô hạn ngay trong DAO; tầng service sở hữu transaction nên chạy lại phần **đọc dữ liệu → quyết định → ghi dữ liệu** trong một transaction mới, và đặt giới hạn rõ ràng.

## 8. Xử lý `BatchUpdateException` khi JDBC batching

`PreparedStatement.executeBatch()` có thể ném `BatchUpdateException`. Ngoài thông tin `SQLException` thường có, nó có mảng `getUpdateCounts()` với kết quả các phần tử batch theo thông tin driver cung cấp:

```java
import java.sql.BatchUpdateException;
import java.sql.Statement;

// Đoạn mã minh họa trong DAO; statement đã addBatch().
try {
    statement.executeBatch();
} catch (BatchUpdateException failure) {
    int[] counts = failure.getUpdateCounts();

    for (int i = 0; i < counts.length; i++) {
        int count = counts[i];
        if (count == Statement.EXECUTE_FAILED) {
            System.err.println("Batch item failed: " + i);
        } else if (count == Statement.SUCCESS_NO_INFO) {
            System.err.println("Batch item succeeded; count unknown");
        } else {
            System.err.println("Affected rows: " + count);
        }
    }

    throw SqlErrorTranslator.translate(
            "customer.batchInsert", failure);
}
```

Tùy driver, batch có thể dừng ngay khi một phần tử lỗi hoặc tiếp tục thực thi các phần tử khác. Vì vậy, `counts.length` không nhất thiết bằng số lệnh được thêm vào batch. Hệ quản trị cũng có thể báo thêm lỗi qua `getNextException()`; translator phải giữ `cause` để người chẩn đoán truy cập chuỗi lỗi.

Nếu batch thuộc transaction chủ động, bên sở hữu phải xác định `rollback()` hoặc `commit()`. Không xem `executeBatch()` là thao tác nguyên tử trong mọi driver và chế độ `autoCommit=true`.

## 9. `SQLWarning` khác `SQLException` ném ra như thế nào?

`SQLWarning` là lớp con của `SQLException` nhưng JDBC thường **cung cấp cảnh báo để đọc riêng** qua `Connection.getWarnings()`, `Statement.getWarnings()` hoặc `ResultSet.getWarnings()`. Thao tác SQL có thể thành công nhưng phát sinh cảnh báo về chuyển đổi dữ liệu, làm tròn hoặc vấn đề không khiến driver ném exception.

Ví dụ đọc cảnh báo statement ngay sau `executeUpdate()`:

```java
import java.sql.SQLWarning;

int affectedRows = statement.executeUpdate();

for (SQLWarning warning = statement.getWarnings();
     warning != null;
     warning = warning.getNextWarning()) {
    System.err.println(
            "Warning SQLState=" + warning.getSQLState()
            + ", vendorCode=" + warning.getErrorCode());
}

statement.clearWarnings();
```

Đoạn code giả sử `statement` vẫn mở. Một số cảnh báo có thể bị xóa khi chạy câu lệnh tiếp theo, nên đọc ở đúng thời điểm. Không tự chuyển mọi `SQLWarning` thành lỗi nghiệp vụ: phải biết cảnh báo nào nghiêm trọng theo tiêu chuẩn chất lượng dữ liệu của hệ thống. Nếu không cho phép cắt ngắn chuỗi, nên xác thực kích thước dữ liệu, ràng buộc cột và xử lý đúng loại cảnh báo thực tế của driver.

## 10. Ghi log giúp chẩn đoán mà không lộ dữ liệu

Khi báo lỗi ở ranh giới truy cập dữ liệu, nên có:

- Tên thao tác ổn định, ví dụ `customer.insert`, cùng trace ID hoặc transaction ID.
- `Kind`, `SQLState`, `vendorCode`, loại exception và thông tin lỗi rollback/đóng tài nguyên.
- Thông tin driver, database/version và thời điểm nếu cần điều tra; giới hạn quyền đọc log.
- Phân biệt log nội bộ và **thông điệp trả cho người dùng**; không phản hồi stack trace, connection string, raw SQL với tham số hoặc `getMessage()` nguyên văn.

Nếu sử dụng logger hỗ trợ placeholder dạng `{}`, lời gọi có thể là:

```java
logger.warn(
        "DB operation={} kind={} sqlState={} vendorCode={} traceId={}",
        "customer.insert",
        failure.getKind(),
        failure.getSqlState(),
        failure.getVendorCode(),
        traceId);
```

Đây là ví dụ với API logger kiểu SLF4J, **không phải phương thức của `java.util.logging`**. Tránh log cùng một exception đầy đủ ở mọi lớp; chọn một ranh giới log chính, tầng khác chuyển tiếp trace ID và lỗi có hợp đồng ổn định.

## 11. Kiểm thử logic chuyển đổi và tích hợp DAO

Có thể kiểm tra `SqlErrorTranslator` mà chưa cần database, bằng cách tạo `SQLException` giả:

```java
import java.sql.SQLException;
import java.sql.SQLTimeoutException;

public final class SqlErrorTranslatorCheck {
    public static void main(String[] args) {
        SQLException constraint = new SQLException(
                "constraint violation", "23505", 0);

        SqlErrorTranslator.DataAccessFailure error =
                SqlErrorTranslator.translate(
                        "customer.insert", constraint);

        if (error.getKind()
                != SqlErrorTranslator.Kind.CONSTRAINT_VIOLATION) {
            throw new AssertionError("Wrong classification");
        }
        if (error.getCause() != constraint) {
            throw new AssertionError("Original SQLException lost");
        }
        if (!"23505".equals(error.getSqlState())) {
            throw new AssertionError("SQLState lost");
        }

        SQLException timeout = new SQLTimeoutException(
                "timeout", null, 0);
        if (SqlErrorTranslator.translate(
                "customer.findById", timeout).getKind()
                != SqlErrorTranslator.Kind.TIMEOUT) {
            throw new AssertionError("Timeout not recognized");
        }

        SQLException unknown = new SQLException("unknown", null, 17);
        if (SqlErrorTranslator.translate(
                "other", unknown).getKind()
                != SqlErrorTranslator.Kind.OTHER) {
            throw new AssertionError("Unknown error misclassified");
        }
    }
}
```

Những trường hợp nên bổ sung trong kiểm thử:

| Trường hợp | Điều kiện đạt |
| --- | --- |
| SQLState `null`, lỗi thường | `OTHER` và không có `NullPointerException` |
| Ngoại lệ gốc `OTHER` nhưng `getNextException()` mang SQLState `23` | Translator nhận diện constraint và vẫn giữ `cause` gốc |
| `SQLException` chứa suppressed exception | Có thể lấy lại các lỗi cleanup từ cause |
| `findById()` không có hàng | Trả `Optional.empty()`, không báo lỗi |
| `INSERT` vi phạm unique trên database thật | DAO ném `DataAccessFailure` với `SQLException` gốc |
| Batch có phần tử lỗi | Giữ `BatchUpdateException` và `getUpdateCounts()` |
| Rollback hoặc đóng kết nối lỗi | Không mất lỗi chính; lưu lỗi phụ và xử lý connection nghi vấn |

Kiểm thử bằng ngoại lệ giả xác minh **hợp đồng Java**, còn kiểm thử tích hợp xác minh **hành vi của driver thật**. Cần thử trên chính hệ quản trị, phiên bản driver, schema, isolation và cấu hình `DataSource` sẽ triển khai.

### Bài thực hành

1. Tạo bảng `products(id BIGINT PRIMARY KEY, sku VARCHAR(40) UNIQUE, price DECIMAL(12,2))` và viết DAO dùng `PreparedStatement` để thêm sản phẩm. Bao bọc `SQLException` bằng translator ở trên.
2. Chèn cùng một `sku` hai lần. Ghi nhận loại `SQLException`, SQLState và vendor code thực tế. So sánh với nhóm `CONSTRAINT_VIOLATION` mà translator trả về.
3. Chạy một câu SQL sai tên cột. Kiểm tra lỗi có rơi vào nhóm `INVALID_SQL_OR_ACCESS_RULE` hay driver dùng mã khác.
4. Với `executeBatch()`, tạo một phần tử vi phạm ràng buộc trong cơ sở dữ liệu thử nghiệm, kiểm tra `getUpdateCounts()`, `getNextException()` và rollback.
5. Giả lập một `SQLTimeoutException`, kiểm tra translator **không tự retry** và service không báo người dùng chắc chắn câu SQL chưa thực thi.
6. Thử `SELECT` không tìm thấy hàng và `UPDATE` ảnh hưởng `0` dòng. Thiết kế kết quả hợp đồng phù hợp mà không ép chúng thành ngoại lệ database.

## 12. Các nguyên tắc quan trọng

| Mục tiêu | Quy tắc thiết kế |
| --- | --- |
| API DAO ổn định | Trả kết quả dữ liệu hoặc lỗi `DataAccessFailure`; tránh rò rỉ phụ thuộc vào driver sang service |
| Chẩn đoán đầy đủ | Giữ `SQLException` trong `cause` cùng SQLState, vendor code, nextException và suppressed |
| Phân loại có căn cứ | Dùng loại ngoại lệ/SQLState đã xác minh; thêm quy tắc vendor khi thật sự cần |
| Xử lý nghiệp vụ chính xác | Chỉ kết luận trùng email hoặc xung đột cụ thể khi biết đúng ràng buộc/ngữ cảnh |
| An toàn giao dịch | Bên sở hữu connection phải `commit()` hoặc `rollback()`; translation không thay thế cleanup |
| Retry có giới hạn | Đánh giá khả năng retry và idempotency, luôn xét toàn bộ transaction |
| Phân biệt cảnh báo | `SQLWarning` được xử lý theo mức độ quan trọng, không tự coi mọi cảnh báo là lỗi |
| Bảo vệ thông tin | Phản hồi công khai ổn định; log chi tiết chỉ ở nơi được phân quyền |

**Ghi nhớ:** Chuyển lỗi JDBC là thiết kế **hợp đồng của lớp truy cập dữ liệu**, không phải thao tác bắt `SQLException` rồi ném một `RuntimeException` chung chung. Một DAO tốt phân loại đủ để tầng gọi quyết định cách xử lý, luôn giữ lỗi gốc cho chẩn đoán, quản lý tài nguyên đúng và không đưa chi tiết cơ sở dữ liệu vào thông điệp công khai.
