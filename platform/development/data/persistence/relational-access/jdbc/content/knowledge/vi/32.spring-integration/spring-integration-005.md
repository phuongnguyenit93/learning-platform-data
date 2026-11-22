# Phân biệt quản lý kết nối thủ công và kết nối gắn với giao dịch Spring

Một ứng dụng Java dùng **JDBC** thường bắt đầu bằng cách gọi `DataSource.getConnection()`, tạo `PreparedStatement`, đọc `ResultSet` và đóng tài nguyên qua `try-with-resources`. Khi nhiều câu SQL phải thành công hoặc thất bại cùng nhau, ứng dụng còn phải quản lý `autoCommit`, `commit()` và `rollback()`. Đó là **quản lý kết nối và giao dịch thủ công**.

Khi tích hợp **Spring**, ta có thể đặt ranh giới giao dịch bằng `@Transactional` hoặc `TransactionTemplate`. Với một `DataSourceTransactionManager` phù hợp, Spring lấy một JDBC `Connection`, gắn nó với **ngữ cảnh giao dịch hiện tại**, rồi bảo đảm các lệnh JDBC tương thích như `JdbcTemplate` dùng **cùng kết nối**. Sau khi giao dịch kết thúc, framework commit/rollback và giải phóng tài nguyên theo hợp đồng.

Hai mô hình này không chỉ khác ở lượng mã cần viết. Điểm khác quan trọng nhất là **ai sở hữu kết nối, ai quyết định transaction boundary và ai có quyền đóng hoặc trả kết nối về pool**. Sự khác biệt trở nên đặc biệt nguy hiểm khi một service có `@Transactional` nhưng repository lại tự gọi `dataSource.getConnection()`: câu SQL của repository có thể chạy trên **kết nối vật lý khác** và không nằm trong transaction Spring mà lập trình viên tưởng đang sử dụng.

Bài thuộc chương **Tích hợp Spring** của module **JDBC**. Mục tiêu là nắm cách phối hợp `DataSource`, `Connection`, `PreparedStatement` và `ResultSet` với `@Transactional`, `JdbcTemplate`, `DataSourceUtils`, quản lý pool, propagation, xử lý ngoại lệ và kiểm thử. Đây vẫn là bài về JDBC: Spring hỗ trợ quản lý vòng đời và transaction, nhưng câu SQL, ràng buộc dữ liệu và ngữ nghĩa database vẫn phải được hiểu rõ.

## 1. Hai mô hình kết nối nhìn từ tầng service

**JDBC thủ công:** lớp ứng dụng tự xác định khi nào mượn kết nối, khi nào bắt đầu giao dịch và khi nào kết thúc.

```text
Service.transfer(...)
    │
    ├─ DataSource.getConnection()
    ├─ Connection.setAutoCommit(false)
    │      ├─ PreparedStatement: trừ tiền
    │      └─ PreparedStatement: cộng tiền
    ├─ commit() hoặc rollback()
    ├─ khôi phục trạng thái Connection
    └─ Connection.close() → thường trả về pool
```

**JDBC được Spring quản lý:** Spring quyết định transaction boundary, còn repository thực thi SQL qua một con đường có khả năng nhận **kết nối gắn với giao dịch**.

```text
Client → Spring transactional proxy
              │
              ▼
     @Transactional service.transfer(...)
              │
     PlatformTransactionManager
              │ mở/gắn transaction và Connection
              ▼
     TransactionSynchronizationManager
              │ giữ tài nguyên transaction trong context hiện hành
              ├───────────┐
              ▼           ▼
        JdbcTemplate  JdbcTemplate
          debit()      credit()
              │           │
              └─────┬─────┘
                    ▼
       Cùng Connection của transaction
                    │
              Service kết thúc
                    │
        TransactionManager commit/rollback
                    │
            trả Connection về pool
```

Bảng so sánh:

| Vấn đề | JDBC thủ công | Spring quản lý transaction |
| --- | --- | --- |
| Mở/lấy kết nối | Gọi `DataSource.getConnection()` trực tiếp | Transaction manager lấy kết nối; mã JDBC tương thích tham gia qua `DataSourceUtils` hoặc `JdbcTemplate` |
| Chuyển `autoCommit` | Ứng dụng tự thực hiện | Transaction manager xử lý khi cần |
| Giao dịch nhiều DAO | Truyền **cùng một `Connection`** qua các DAO | Các DAO dùng cùng `DataSource`/transaction manager và cơ chế transaction-aware |
| Commit/rollback | Ứng dụng tự gọi | Spring quyết định theo kết quả scope giao dịch |
| Đóng kết nối | Bên sở hữu kết nối đóng khi xong | Mã DAO không tự đóng kết nối đã được Spring gắn với transaction |
| Ngoại lệ JDBC | Xử lý `SQLException`; tự quyết định rollback | `JdbcTemplate` chuyển thành `DataAccessException` (unchecked) và Spring rollback theo quy tắc |
| Timeout/isolation | Ứng dụng tự cấu hình và phục hồi | Có thể khai báo ở `@Transactional`, song còn tùy driver/transaction manager |
| Test transaction | Xác minh thủ công rollback/cleanup | Test qua Spring proxy và DB thật; chú ý test tự dùng `@Transactional` có thể che lỗi |

**Spring không tạo ra một loại transaction SQL mới.** Với một `DataSourceTransactionManager` dùng JDBC thông thường, database vẫn thực hiện transaction trên một `Connection`. Spring chỉ điều phối việc sử dụng kết nối và ranh giới giao dịch của ứng dụng.

## 2. Quản lý thủ công: cần kiểm soát cả kết nối và trạng thái

Giả sử nghiệp vụ chuyển tiền giữa hai tài khoản. Một thao tác ghi trừ tiền thành công nhưng ghi cộng tiền thất bại phải **rollback toàn bộ**. Nếu mỗi DAO tự mượn một kết nối rồi thực hiện SQL ở `autoCommit=true`, hai thay đổi có thể bị commit độc lập.

Ví dụ sau dùng **một kết nối** cho cả hai `UPDATE`:

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.Objects;

public final class ManualTransferService {
    private final DataSource dataSource;

    public ManualTransferService(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public void transfer(long fromId, long toId, BigDecimal amount)
            throws SQLException {

        if (fromId == toId || amount == null
                || amount.signum() <= 0) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        try (Connection connection = dataSource.getConnection()) {
            boolean originalAutoCommit = connection.getAutoCommit();
            if (!originalAutoCommit) {
                throw new SQLException(
                        "Expected a connection outside an existing transaction");
            }

            connection.setAutoCommit(false);
            boolean transactionEnded = false;
            Throwable primaryFailure = null;

            try {
                String debitSql =
                        "UPDATE accounts SET balance = balance - ? " +
                        "WHERE id = ? AND balance >= ?";

                try (PreparedStatement debit =
                             connection.prepareStatement(debitSql)) {
                    debit.setBigDecimal(1, amount);
                    debit.setLong(2, fromId);
                    debit.setBigDecimal(3, amount);

                    if (debit.executeUpdate() != 1) {
                        throw new SQLException(
                                "Source account missing or insufficient funds");
                    }
                }

                String creditSql =
                        "UPDATE accounts SET balance = balance + ? " +
                        "WHERE id = ?";

                try (PreparedStatement credit =
                             connection.prepareStatement(creditSql)) {
                    credit.setBigDecimal(1, amount);
                    credit.setLong(2, toId);

                    if (credit.executeUpdate() != 1) {
                        throw new SQLException(
                                "Destination account missing");
                    }
                }

                connection.commit();
                transactionEnded = true;

            } catch (SQLException | RuntimeException | Error failure) {
                primaryFailure = failure;
                if (!transactionEnded) {
                    try {
                        connection.rollback();
                        transactionEnded = true;
                    } catch (SQLException rollbackFailure) {
                        failure.addSuppressed(rollbackFailure);
                    }
                }
                throw failure;

            } finally {
                // Không reset autoCommit nếu rollback chưa thành công.
                if (transactionEnded) {
                    try {
                        connection.setAutoCommit(originalAutoCommit);
                    } catch (SQLException restoreFailure) {
                        if (primaryFailure != null) {
                            primaryFailure.addSuppressed(restoreFailure);
                        } else {
                            throw restoreFailure;
                        }
                    }
                }
            }
        }
    }
}
```

Lý do mã thủ công tương đối dài:

1. Cần xác định **phương thức này sở hữu transaction**, không vô tình xen vào transaction do bên khác sở hữu.
2. Gọi `setAutoCommit(false)` trước các thao tác cần tính nguyên tử.
3. Dùng **cùng `Connection`** cho `debit` và `credit`; không tự lấy kết nối mới giữa các DAO.
4. Sau thành công phải `commit()`; khi thất bại phải cố `rollback()`.
5. Nếu rollback thất bại, trạng thái transaction có thể không rõ. Không bật `autoCommit=true` một cách máy móc vì thao tác chuyển từ `false` sang `true` có thể commit transaction đang mở.
6. Với connection pool, `close()` thường trả kết nối logic cho pool; khi connection nghi vấn, ứng dụng cần cách **loại bỏ kết nối vật lý không còn đáng tin** theo cơ chế pool.
7. Nếu `commit()` mất liên lạc với server, một lời gọi rollback sau đó **không chứng minh** giao dịch chưa commit. Cần đối soát và idempotency khi nghiệp vụ quan trọng.

Đây là minh họa quản lý transaction chủ động, chưa phải mô hình xử lý lỗi nghiệp vụ tối ưu: lỗi “không đủ tiền” nên có kiểu hoặc kết quả nghiệp vụ riêng. Dù vậy, nó cho thấy nhiều việc lặp lại mà transaction manager có thể điều phối nhất quán.

### Khi nào quản lý thủ công vẫn hợp lý?

- Ứng dụng Java thuần không dùng Spring hay transaction framework.
- Công cụ ngắn, test hoặc tác vụ độc lập với một `Connection` và phạm vi giao dịch rất rõ.
- Cần xử lý JDBC đặc biệt mà transaction manager hiện tại không cung cấp.

Nếu chọn thủ công, **mỗi transaction phải có một bên sở hữu rõ ràng**. Các DAO cấp thấp thường chỉ nhận `Connection` từ service, không tự `commit()`, `rollback()` hoặc `close()` kết nối mà chúng không sở hữu.

## 3. Spring gắn Connection vào transaction như thế nào?

Trong ứng dụng JDBC đồng bộ dùng Spring, `DataSourceTransactionManager` là một implementation của `PlatformTransactionManager` cho giao dịch cục bộ với **một `DataSource`**.

Luồng điển hình khi gọi một phương thức `@Transactional` thông qua Spring proxy:

1. Proxy chặn lời gọi và tra cứu định nghĩa transaction.
2. Transaction manager lấy một `Connection` từ `DataSource`, chuẩn bị transaction (ví dụ `autoCommit=false` khi cần).
3. Spring gắn tài nguyên kết nối với **ngữ cảnh thực thi hiện tại**, qua cơ chế `TransactionSynchronizationManager`.
4. Các lời gọi `JdbcTemplate` hoặc `DataSourceUtils.getConnection(dataSource)` tương thích cùng `DataSource` lấy ra **kết nối đã gắn**, không tự tạo transaction riêng.
5. Khi phương thức kết thúc, transaction manager quyết định commit/rollback theo trạng thái và quy tắc exception.
6. Spring dọn trạng thái transaction, giải phóng kết nối và trả về pool nếu cần.

Trong mô hình JDBC imperative thông thường, ngữ cảnh transaction gắn với **thread hiện tại**. Đây là điểm thiết kế then chốt: gọi code JDBC bằng thread khác mà không có cơ chế truyền context được framework hỗ trợ sẽ không mặc nhiên tham gia transaction của thread gốc.

**Không xem `TransactionSynchronizationManager` như API để repository tự sửa tài nguyên.** Nó là cơ chế nội bộ cần hiểu để tránh dùng connection sai; repository nên dùng `JdbcTemplate` hoặc `DataSourceUtils` thay vì thao tác trực tiếp với thread-local resource.

### Một DataSource, một ranh giới giao dịch

Để những DAO tham gia cùng transaction, cần dùng **cùng datasource được transaction manager quản lý** (hoặc wrapper có quan hệ được Spring hỗ trợ). Nếu một DAO dùng `ordersDataSource`, DAO khác dùng `auditDataSource`, một `DataSourceTransactionManager` thông thường **không tự tạo giao dịch nguyên tử xuyên hai database**.

Cần phân biệt:

- **Local JDBC transaction:** một JDBC `Connection` tới một resource.
- **Giao dịch phân tán:** nhiều resource cần cơ chế phối hợp riêng (ví dụ XA/JTA nếu môi trường hỗ trợ), không tự có vì đặt `@Transactional`.
- **Tác động ngoài database:** email, HTTP, queue hoặc thanh toán không tự rollback cùng JDBC transaction; có thể cần outbox/saga/idempotency.

## 4. Cấu hình cơ bản của Spring JDBC và transaction manager

Ví dụ Java configuration đơn giản, khi ứng dụng đã có `DataSource` được khai báo hoặc tự cấu hình:

```java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class JdbcConfiguration {

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    public PlatformTransactionManager transactionManager(
            DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
```

Điều kiện:

- `DataSource` phải được cấu hình hợp lệ (thường là pooled datasource) và thuộc phạm vi Spring container.
- Trong Spring Boot, nhiều bean có thể đã được **auto-configure** tùy starter/dependency và transaction manager có sẵn; không nên thêm bean trùng mà không xác minh cấu hình thực tế.
- Nếu ứng dụng có nhiều `DataSource` hoặc transaction manager, phải chọn đúng bean qua tên/qualifier, `@Transactional(transactionManager = "...")` hoặc cấu hình tương đương.
- `@EnableTransactionManagement` kích hoạt quản lý transaction bằng annotation trong cấu hình Spring phù hợp; các ứng dụng Boot thường đã có cơ chế tự kích hoạt khi điều kiện được đáp ứng.
- Có thể dùng `JdbcTransactionManager` trong các phiên bản Spring hỗ trợ để có hành vi phù hợp hơn với JDBC exception translation ở commit/rollback; cần kiểm tra phiên bản framework của ứng dụng. Nguyên tắc ràng buộc connection vẫn tương tự.

Để dùng `JdbcTemplate` và quản lý giao dịch, cần module Spring JDBC và Spring transaction phù hợp với phiên bản Spring của dự án. Các import và cơ chế proxy thuộc Spring, **không phải API của JDBC chuẩn**.

## 5. `JdbcTemplate`: thao tác SQL trên kết nối gắn với giao dịch

`JdbcTemplate` giúp giảm boilerplate của `Connection`, `PreparedStatement`, `ResultSet`. Quan trọng hơn trong ngữ cảnh này, nó lấy và giải phóng connection theo cơ chế Spring transaction-aware, nên có thể **tham gia transaction hiện hành**.

Giả sử có bảng:

```sql
CREATE TABLE inventory (
    product_id BIGINT PRIMARY KEY,
    available INTEGER NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL
);

CREATE TABLE order_audit (
    order_id BIGINT NOT NULL,
    action VARCHAR(40) NOT NULL
);
```

Ví dụ Spring repository dùng `JdbcTemplate`:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public final class JdbcOrderRepository {
    private final JdbcTemplate jdbc;

    public JdbcOrderRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public boolean reserveStock(long productId, int quantity) {
        int changed = jdbc.update(
                "UPDATE inventory SET available = available - ? " +
                "WHERE product_id = ? AND available >= ?",
                quantity, productId, quantity);
        return changed == 1;
    }

    public void insertOrder(long orderId, long productId, int quantity) {
        int changed = jdbc.update(
                "INSERT INTO orders (id, product_id, quantity) " +
                "VALUES (?, ?, ?)",
                orderId, productId, quantity);

        if (changed != 1) {
            throw new IllegalStateException(
                    "Expected exactly one inserted order");
        }
    }

    public void insertAudit(long orderId) {
        jdbc.update(
                "INSERT INTO order_audit (order_id, action) " +
                "VALUES (?, ?)",
                orderId, "CREATED");
    }
}
```

`JdbcTemplate.update(...)` dùng SQL tham số hóa; các giá trị được gán qua cơ chế JDBC `PreparedStatement` phù hợp. Mặc định nó xử lý việc mở/đóng statement và result set; Spring vẫn cần được cấu hình đúng `DataSource`.

Tầng service quyết định **ranh giới nghiệp vụ**:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final JdbcOrderRepository repository;

    public OrderService(JdbcOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void placeOrder(
            long orderId, long productId, int quantity) {

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be positive");
        }

        boolean reserved =
                repository.reserveStock(productId, quantity);

        if (!reserved) {
            throw new IllegalStateException(
                    "Product is missing or stock is insufficient");
        }

        repository.insertOrder(orderId, productId, quantity);
        repository.insertAudit(orderId);

        // Không gọi connection.commit() ở đây:
        // transaction manager kết thúc giao dịch sau phương thức.
    }
}
```

Khi phương thức `placeOrder(...)` được gọi **qua Spring transaction proxy** và repository dùng đúng `JdbcTemplate/DataSource`, ba lệnh SQL cùng thuộc transaction. Nếu `insertOrder(...)` vi phạm primary key hoặc `insertAudit(...)` thất bại với ngoại lệ unchecked, Spring mặc định đánh dấu rollback cho transaction.

**Cần phân biệt:**

- `@Transactional` không thay thế điều kiện `WHERE` để bảo vệ tồn kho. Mã vẫn phải kiểm tra `quantity > 0` và `executeUpdate()` trả `1`.
- Mã không yêu cầu kết nối mới trong mỗi phương thức repository, dù chúng được gọi liên tiếp.
- `JdbcTemplate` chuyển `SQLException` thông thường thành hệ ngoại lệ Spring `DataAccessException` (unchecked); ứng dụng có thể thêm tầng ánh xạ lỗi nghiệp vụ nếu cần.
- Nếu không có transaction active, các `JdbcTemplate.update(...)` vẫn có thể chạy riêng theo mặc định của datasource (thường là auto-commit). Vì vậy test phải xác minh `@Transactional` **thực sự được áp dụng**, không chỉ thấy annotation trong code.
- Một ví dụ dùng `@Transactional` với một `DataSource` không bảo đảm những hành động ngoài JDBC như gửi email hoặc gọi REST endpoint được rollback.

## 6. Bẫy lớn: `@Transactional` nhưng vẫn gọi raw `dataSource.getConnection()`

Một service có thể đã được đặt `@Transactional`:

```java
@Transactional
public void placeOrder(...) {
    stockDao.reserve(...); // JdbcTemplate: tham gia transaction.
    auditDao.write(...);   // Tự gọi raw DataSource.getConnection().
}
```

Giả sử `auditDao` tự viết:

```java
// CẢNH BÁO: không bảo đảm tham gia transaction Spring hiện hành
// khi dataSource là pool/target DataSource thông thường.
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "INSERT INTO order_audit (order_id, action) VALUES (?, ?)")) {

    statement.setLong(1, orderId);
    statement.setString(2, "CREATED");
    statement.executeUpdate();
}
```

**Điều có thể xảy ra:** `DataSourceTransactionManager` đã lấy và gắn một connection A cho giao dịch. Nhưng `dataSource.getConnection()` gọi thẳng vào pool có thể mượn connection B; kết nối B có thể ở `autoCommit=true`, nên audit được commit độc lập. Nếu service thất bại và Spring rollback connection A, audit trên B vẫn tồn tại.

Vì vậy **không được suy rằng annotation bao trùm mọi lời gọi JDBC trong cùng method**. Đường đi lấy connection và danh tính `DataSource` quyết định câu SQL có dùng connection gắn với transaction hay không.

Ngoại lệ quan trọng: nếu code nhận **`TransactionAwareDataSourceProxy`** (được cấu hình đúng) thì lời gọi `getConnection()` và `close()` qua proxy có thể được điều hướng để tham gia transaction hiện hành. Nhưng điều này là **đặc tính của proxy Spring**, không phải của raw pooled `DataSource`, và phải được cấu hình, kiểm thử rõ ràng.

### Ba con đường an toàn

1. **Ưu tiên:** dùng `JdbcTemplate`/`NamedParameterJdbcTemplate` với `DataSource` được transaction manager quản lý.
2. **Khi cần API JDBC cấp thấp:** lấy connection qua `DataSourceUtils.getConnection(dataSource)` và giải phóng bằng `DataSourceUtils.releaseConnection(...)`.
3. **Với thư viện legacy chỉ biết `DataSource.getConnection()`:** cân nhắc cấp cho thư viện `TransactionAwareDataSourceProxy` bọc **target DataSource**, thay vì sửa toàn bộ mã; cần kiểm tra tính tương thích và không dùng proxy sai phía transaction manager.

Không trộn các con đường trên tùy tiện. Trong dự án có nhiều datasource, xác định cùng một target pool và cùng transaction manager trước khi tin rằng chúng sẽ dùng chung transaction.

## 7. `DataSourceUtils`: làm JDBC thủ công nhưng vẫn tôn trọng transaction Spring

Khi cần kiểm soát `PreparedStatement`/`ResultSet` ở mức thấp, Spring cung cấp `DataSourceUtils`:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import org.springframework.jdbc.datasource.DataSourceUtils;

public final class LowLevelProductDao {
    private final DataSource dataSource;

    public LowLevelProductDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public int readStock(long productId) throws SQLException {
        Connection connection =
                DataSourceUtils.getConnection(dataSource);

        try {
            String sql =
                    "SELECT available FROM inventory WHERE product_id = ?";

            try (PreparedStatement statement =
                         connection.prepareStatement(sql)) {

                statement.setLong(1, productId);

                try (ResultSet rs = statement.executeQuery()) {
                    if (!rs.next()) {
                        throw new SQLException("Product not found");
                    }
                    return rs.getInt(1);
                }
            }
        } finally {
            DataSourceUtils.releaseConnection(
                    connection, dataSource);
        }
    }
}
```

Điểm cần chú ý:

- `DataSourceUtils.getConnection(dataSource)` tham gia cơ chế gắn tài nguyên của Spring. Nếu một transaction thích hợp đang hoạt động, nó có thể trả **connection đang gắn với transaction đó**.
- `DataSourceUtils.releaseConnection(connection, dataSource)` **không đóng physical/logic connection đang thuộc transaction active** như việc đóng trực tiếp. Nó chỉ giải phóng tài nguyên khi Spring xác định nên giải phóng.
- **Không đặt `Connection` lấy từ `DataSourceUtils` trong `try (Connection c = ...)` rồi tự gọi `c.close()`. Lệnh close có thể kết thúc quyền sử dụng kết nối khi transaction vẫn đang cần nó.
- `PreparedStatement` và `ResultSet` **vẫn thuộc quyền của DAO**, cần đóng bằng `try-with-resources` ngay trong scope.
- Nếu phương thức `readStock()` khai báo `throws SQLException` và service bên ngoài dùng `@Transactional`, **checked `SQLException` không tự kích hoạt rollback theo mặc định**. Cần quy tắc exception rõ ràng ở tầng transaction (xem phần 10).
- Nếu không có Spring transaction, `DataSourceUtils` vẫn có thể lấy connection và release theo cơ chế quản lý của Spring; nó không tự mở một transaction nghiệp vụ dài chỉ vì được gọi.

**Ưu tiên `JdbcTemplate`** cho CRUD thông thường, vì template đã dùng các cơ chế giao dịch và chuyển exception phù hợp, giảm nguy cơ quên release hoặc xử lý sai timeout. Dùng `DataSourceUtils` khi thực sự cần thao tác JDBC cấp thấp mà `JdbcTemplate` không che phủ thuận tiện.

## 8. `TransactionAwareDataSourceProxy` dành cho thư viện legacy

Có mã thư viện cũ chỉ nhận `javax.sql.DataSource` rồi gọi:

```java
try (Connection c = suppliedDataSource.getConnection()) {
    // Thực thi SQL bằng c.
}
```

Thư viện không biết `JdbcTemplate` hay `DataSourceUtils`. Spring có `TransactionAwareDataSourceProxy` để bọc một target datasource nhằm giúp code kiểu này **thấy được kết nối tương thích với transaction**.

Ví dụ ý tưởng cấu hình:

```java
import javax.sql.DataSource;
import org.springframework.jdbc.datasource.TransactionAwareDataSourceProxy;

// targetDataSource là pool được transaction manager quản lý.
DataSource legacyFacingDataSource =
        new TransactionAwareDataSourceProxy(targetDataSource);

// Truyền legacyFacingDataSource cho library legacy.
// Transaction manager vẫn quản lý targetDataSource.
```

Một số lưu ý:

- Proxy can thiệp hành vi `getConnection()` và `close()` để tương thích với cơ chế Spring transaction; nó không tạo ra một distributed transaction.
- **Transaction manager cần tham chiếu đến target DataSource phù hợp**, không thiết kế vòng proxy tùy tiện. Theo hướng sử dụng thông thường, cấp wrapper cho mã legacy cần API standard `DataSource`.
- Những phương thức mà thư viện gọi để tự `commit()`, `rollback()` hoặc thay session state vẫn cần được đánh giá. Proxy không biến một thư viện chủ động sở hữu transaction thành “vô hại”.
- Phải kiểm thử bằng **rollback thật trên database** để chứng minh thao tác của thư viện tham gia transaction; chỉ nhìn interface `DataSource` là không đủ.
- Không dùng proxy làm cớ để trộn `getConnection()` trực tiếp và `DataSourceUtils` mà không hiểu dependency injection thực tế.

## 9. Các lỗi proxy khiến `@Transactional` không hoạt động

Với cơ chế proxy transaction phổ biến của Spring, annotation được áp dụng khi lời gọi **đi qua Spring proxy**, không phải cứ có annotation trên source code là đủ.

### Tự gọi phương thức trong cùng bean

```java
@Service
public class CheckoutService {

    public void checkout() {
        this.persistOrder(); // Self-invocation: bỏ qua transaction proxy.
    }

    @Transactional
    public void persistOrder() {
        // JDBC operations...
    }
}
```

Trong proxy mode thông thường, lời gọi `this.persistOrder()` không đi qua transaction interceptor. Nếu không có một transaction đang hoạt động từ nơi khác, câu SQL có thể chạy riêng lẻ. Sửa bằng cách đặt ranh giới transaction ở **phương thức được gọi từ bên ngoài qua proxy**, hoặc chuyển nghiệp vụ vào một Spring bean khác được inject đúng cách.

### Tự tạo đối tượng bằng `new`

```java
CheckoutService service = new CheckoutService();
service.persistOrder(); // Không phải Spring-managed bean/proxy.
```

Ví dụ trên còn không có dependency được inject. Spring không quản lý transaction cho object tự tạo ngoài container bằng cách này.

### Method visibility, class/method `final` và kiểu proxy

Khả năng intercept method có thể khác theo **kiểu proxy** (JDK interface proxy hoặc class-based proxy), phiên bản Spring và cấu hình. Không dựa vào transaction annotation trên `private` method hay self-invocation; những phương thức `final`/class `final` cũng có giới hạn với class-based proxy. Cách an toàn, dễ hiểu là đặt `@Transactional` lên **public service method** được gọi thông qua bean do Spring quản lý, rồi kiểm thử nó bằng integration test.

### Chuyển thread hoặc dùng tác vụ bất đồng bộ

Một transaction imperative của JDBC thường gắn với thread. Khi service mở `@Transactional` rồi khởi chạy:

```java
new Thread(() -> repository.insertAudit(...)).start();
```

transaction context của thread gốc **không tự truyền** sang thread mới. Tương tự, khi kết hợp `@Async`, `CompletableFuture` hoặc thread pool, phải thiết kế transaction riêng cho công việc ở thread đích nếu cần. Không chia sẻ `Connection` đang thuộc transaction giữa các thread như giả định nó an toàn.

Spring có các mô hình transaction khác cho reactive stack, nhưng bài này nói về **JDBC đồng bộ**, không áp dụng các giả định thread-bound này một cách máy móc sang R2DBC/reactive context.

## 10. Ngoại lệ kiểm soát rollback: checked và unchecked khác nhau

Quy tắc mặc định thông thường của Spring `@Transactional`:

- Ném **`RuntimeException`** hoặc **`Error`** ra khỏi phương thức transactional → transaction được đánh dấu rollback.
- Ném **checked exception** như `SQLException` → **không tự rollback theo quy tắc mặc định** nếu không có cấu hình khác.

Đây là điểm rất quan trọng khi trộn raw JDBC với Spring.

### `JdbcTemplate` và `DataAccessException`

`JdbcTemplate` thường bắt `SQLException`, dùng `SQLExceptionTranslator` của Spring rồi ném `DataAccessException`, một **unchecked exception**. Ví dụ khi `INSERT` vi phạm ràng buộc, lớp repository có thể ném `DataIntegrityViolationException`; exception ra khỏi `@Transactional` và Spring rollback mặc định.

Không suy rằng mọi lỗi được dịch luôn cùng một subclass giữa các driver. Hệ phân loại của Spring và SQLState/vendor code có thể khác theo driver/version, vì vậy cần integration test.

### Raw JDBC với `throws SQLException`

Nếu service nhận checked `SQLException` từ DAO sử dụng `DataSourceUtils`, muốn rollback khi ngoại lệ đó thoát ra có thể khai báo:

```java
import java.sql.SQLException;
import org.springframework.transaction.annotation.Transactional;

@Transactional(rollbackFor = SQLException.class)
public void runJdbcSteps() throws SQLException {
    lowLevelDao.stepOne();
    lowLevelDao.stepTwo();
}
```

Đây là đoạn minh họa nằm trong một Spring-managed service. `rollbackFor` áp quy tắc rollback cho ngoại lệ loại đó thoát khỏi phương thức. Không nên bắt `SQLException` rồi nuốt lỗi, trả thành công giả.

Một lựa chọn khác là chuyển nó thành unchecked exception của tầng truy cập dữ liệu **giữ nguyên cause**, để service và transaction manager có thể xử lý nhất quán.

### Nuốt exception khiến Spring tưởng thành công

```java
@Transactional
public void saveSomething() {
    try {
        repository.insert();
    } catch (RuntimeException failure) {
        logger.warn("Insert failed", failure);
        // Nếu chỉ log rồi return, proxy có thể thấy kết thúc bình thường.
    }
}
```

Nếu không có thành phần khác đã đánh dấu transaction rollback-only, Spring có thể **commit** thay đổi trước lỗi. Nếu đó là lỗi cần hủy toàn bộ nghiệp vụ, hãy **ném lại exception**, hoặc đánh dấu rollback-only rõ ràng khi xử lý có chủ đích.

Ví dụ trong code do transaction manager sở hữu:

```java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

TransactionAspectSupport.currentTransactionStatus()
        .setRollbackOnly();
```

Đây là cơ chế gắn chặt với Spring transaction context hiện hành; không nên dùng tùy tiện thay cho việc thiết kế kết quả/exception rõ ràng. Nếu không có transaction aspect đang hoạt động, việc truy cập trạng thái có thể thất bại.

**Không biến lỗi business hợp lệ thành ngoại lệ DB một cách tùy tiện.** “Không đủ tồn kho” có thể là kết quả nghiệp vụ; nếu đã trừ tiền/ghi các bước khác trong cùng transaction và muốn hủy, service phải đưa ra quyết định rollback phù hợp.

## 11. Propagation: không phải mọi `@Transactional` đều dùng chung một transaction

Một phương thức `@Transactional` có thể gọi một phương thức cũng có annotation đó. Hành vi phụ thuộc **propagation** và việc lời gọi có đi qua proxy thích hợp hay không.

| Propagation | Ý nghĩa thường gặp trong Spring | Điều phải lưu ý |
| --- | --- | --- |
| `REQUIRED` (mặc định) | Tham gia transaction hiện có; nếu chưa có thì tạo mới | Nhiều DAO/service trong cùng transaction khi gọi đúng qua proxy |
| `REQUIRES_NEW` | Tạm treo transaction hiện tại và tạo **transaction độc lập** | Có thể cần thêm kết nối; commit bên trong không bị rollback bởi transaction ngoài |
| `NESTED` | Dùng savepoint trong một transaction vật lý nếu transaction manager/driver hỗ trợ | Không giống `REQUIRES_NEW`; phải kiểm tra hỗ trợ savepoint |
| `SUPPORTS` | Tham gia transaction nếu có; nếu không có thì chạy không transaction | Mã ghi dữ liệu có thể tự commit khi không có transaction |
| `MANDATORY` | Yêu cầu đã có transaction hiện hành | Hữu ích để chặn gọi API thao tác dữ liệu quan trọng ngoài transaction |
| `NOT_SUPPORTED` | Tạm treo transaction hiện có, chạy không transaction | Các truy vấn/ghi bên trong không cùng transaction ngoài |
| `NEVER` | Chỉ chạy khi không có transaction | Báo lỗi nếu gọi trong transaction |

Ví dụ:

```java
@Transactional
public void placeOrder(...) {
    repository.reserve(...);
    auditService.saveAuditIndependently(...);
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void saveAuditIndependently(...) {
    auditRepository.write(...);
}
```

Đoạn này giả định `auditService` là **bean khác** được gọi qua Spring proxy. Với `REQUIRES_NEW`, việc ghi audit có transaction riêng. Nếu transaction ngoài rollback nhưng audit đã commit, audit có thể **vẫn còn**. Điều đó có thể đúng với một số loại nhật ký kỹ thuật, nhưng thường **sai** nếu audit phải phản ánh chính xác đơn hàng chỉ khi đơn hàng thành công.

### `REQUIRES_NEW` ảnh hưởng connection pool

Trong mô hình JDBC local transaction, transaction ngoài đang giữ kết nối; khi tạo transaction độc lập bên trong, nó có thể cần **một kết nối khác**. Nếu mọi thread đều đang giữ connection ngoài và cùng chờ connection mới cho `REQUIRES_NEW`, pool có nguy cơ cạn kết nối hoặc deadlock do resource starvation.

Do đó, không thêm `REQUIRES_NEW` chỉ vì muốn “phương thức con chắc chắn có transaction”. `REQUIRED` đã là mặc định để tham gia transaction đang hoạt động. Nếu thực sự cần transaction độc lập, phải tính cả số kết nối đồng thời và khả năng phục hồi khi pool chờ mượn quá lâu.

### `NESTED` và savepoint

Với `DataSourceTransactionManager` và driver hỗ trợ savepoint, `NESTED` có thể tạo một savepoint trong cùng transaction vật lý. Rollback phần nested có thể trở lại savepoint, nhưng transaction ngoài vẫn quyết định commit cuối cùng.

Không giả định `NESTED` được hỗ trợ mọi nơi, nhất là khi ứng dụng dùng transaction manager khác hoặc có sự kết hợp ORM/resource phức tạp. Hãy kiểm tra driver, platform transaction manager và test hành vi thật.

## 12. Isolation, read-only và timeout thuộc transaction scope

Spring cho phép khai báo:

```java
@Transactional(
        isolation = Isolation.READ_COMMITTED,
        readOnly = true,
        timeout = 5)
public List<Product> listProducts() {
    return productDao.findVisibleProducts();
}
```

Ví dụ dùng `org.springframework.transaction.annotation.Isolation`. Ý nghĩa:

- `isolation` yêu cầu mức cô lập transaction phù hợp, nhưng mức đó phải được driver/database hỗ trợ; cùng tên isolation không bảo đảm hành vi khóa/snapshot giống nhau trên mọi hệ quản trị.
- `readOnly=true` thường là **hint/định hướng cấu hình** cho transaction và các công cụ truy cập dữ liệu. Nó **không thay thế quyền database**, không tự bảo đảm không thể chạy `INSERT`.
- `timeout=5` khai báo thời gian giới hạn cho transaction theo cơ chế Spring/transaction manager. Với JDBC, việc áp giới hạn lên statement có thể phụ thuộc công cụ truy cập và driver; nó **không phải cam kết deadline end-to-end chính xác** cho mượn pool, fetch, commit, rollback và API bên ngoài.

`JdbcTemplate` và các công cụ Spring transaction-aware thường có khả năng áp timeout của transaction lên `Statement`. Khi dùng JDBC thấp hơn với `DataSourceUtils`, có thể dùng helper phù hợp để áp timeout transaction hiện hành cho statement nếu cần:

```java
import org.springframework.jdbc.datasource.DataSourceUtils;

PreparedStatement statement = connection.prepareStatement(sql);

DataSourceUtils.applyTransactionTimeout(
        statement, dataSource);
```

Đoạn này chỉ minh họa thao tác trên statement đã được tạo từ connection đang dùng đúng `DataSource`. Phải đặt trong scope đóng statement và xử lý exception phù hợp. Nếu không dùng Spring helper, raw JDBC code tự đặt `setQueryTimeout(...)` có thể bỏ qua deadline transaction được framework quản lý.

**Chú ý propagation:** nếu một phương thức `@Transactional(REQUIRED)` tham gia transaction đã tồn tại, việc khai báo isolation/timeout/read-only ở phương thức bên trong không nhất thiết tạo một transaction vật lý mới hay ghi đè mọi thuộc tính của transaction ngoài. Hãy xác định transaction boundary thật và kiểm thử cấu hình.

## 13. `TransactionTemplate`: chủ động giới hạn phạm vi mà vẫn giao quản lý cho Spring

Không phải dự án nào cũng phù hợp với annotation transaction trên cả phương thức. Khi muốn mở một transaction chỉ cho **một đoạn code cụ thể**, Spring cung cấp `TransactionTemplate`.

```java
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public final class ProgrammaticOrderService {
    private final TransactionTemplate transactions;
    private final JdbcOrderRepository repository;

    public ProgrammaticOrderService(
            PlatformTransactionManager manager,
            JdbcOrderRepository repository) {
        this.transactions = new TransactionTemplate(manager);
        this.repository = repository;
    }

    public void placeOrder(
            long orderId, long productId, int quantity) {

        transactions.executeWithoutResult(status -> {
            if (quantity <= 0) {
                throw new IllegalArgumentException("Invalid quantity");
            }

            if (!repository.reserveStock(productId, quantity)) {
                throw new IllegalStateException(
                        "Insufficient stock or unknown product");
            }

            repository.insertOrder(orderId, productId, quantity);
            repository.insertAudit(orderId);
        });
    }
}
```

`TransactionTemplate` vẫn dùng `PlatformTransactionManager`, nên các `JdbcTemplate` cùng datasource tham gia transaction như khi dùng `@Transactional`. Nó giúp thể hiện ranh giới ở vị trí gọi, giảm rủi ro **self-invocation** liên quan proxy khi transaction được mở bằng lời gọi template trực tiếp.

Lưu ý:

- `TransactionTemplate` không phải JDBC API chuẩn.
- Template dùng quy tắc rollback và propagation phù hợp với cấu hình; có thể cấu hình isolation/timeout riêng trên template nếu cần.
- Bên trong callback **không tự gọi `Connection.commit()`** nếu đã giao quyền kết thúc transaction cho Spring.
- Mặc định ví dụ trên throw unchecked exception để báo thất bại; các exception checked trong callback cần được xử lý theo API callback đã chọn.
- Nếu đặt callback quá rộng, transaction có thể giữ connection qua những phần xử lý Java hoặc gọi mạng ngoài DB; cần giữ transaction scope gọn.

## 14. Vì sao sử dụng `JdbcTemplate` không tự bảo đảm transaction đúng?

Một số trường hợp vẫn có thể sai dù đã dùng Spring:

1. **Service không được gọi qua proxy:** annotation tồn tại nhưng không có transaction hiện hành.
2. **Repository và transaction manager dùng DataSource khác nhau:** câu SQL chạy trên pool/connection không thuộc transaction đó.
3. **Method con dùng `REQUIRES_NEW` hoặc `NOT_SUPPORTED` không đúng ý định:** thao tác tách khỏi transaction ngoài.
4. **DAO bắt và nuốt exception:** transaction manager không nhận được tín hiệu thất bại.
5. **Tác vụ ghi chạy trên thread khác:** không tự dùng thread-bound connection của transaction gốc.
6. **Dùng `@Transactional(readOnly=true)` như một cơ chế phân quyền:** database role vẫn có thể cho ghi.
7. **Dựa vào Spring để chống lost update:** transaction manager không tự tạo điều kiện `WHERE version=?` hoặc bảo vệ mọi bất biến giữa nhiều hàng.
8. **Tạo nhiều transaction độc lập với cùng nghiệp vụ:** service trả thành công dù dữ liệu đã commit một phần.
9. **Gọi HTTP, email hoặc queue trong transaction:** DB rollback không đảo ngược tác dụng của hệ thống bên ngoài.
10. **Giữ ResultSet/Connection ra ngoài scope:** tài nguyên có thể không còn hợp lệ sau khi Spring hoàn tất transaction.

Vì thế, annotation và template là **cơ chế điều phối**, không thay thế thiết kế SQL có điều kiện, ràng buộc dữ liệu, idempotency, kiểm thử đồng thời và quan sát hệ thống.

## 15. Kiểm thử hai mô hình trên database thật

Một unit test dùng mock `JdbcTemplate` hoặc mock `Connection` có thể kiểm tra lời gọi, nhưng **không chứng minh** các bước SQL thực sự cùng transaction. Hãy dùng **integration test** với datasource, transaction manager và database thật hoặc môi trường test tương ứng.

### Tình huống kiểm thử rollback qua Spring

Sử dụng chính `OrderService.placeOrder(...)` ở phần 5. Chuẩn bị:

```text
inventory: product_id=101, available=10
orders: đã có id=900
order_audit: chưa có audit cho thử nghiệm này
```

Gọi:

```java
orderService.placeOrder(900L, 101L, 2);
```

Thứ tự:

1. `reserveStock(...)` cập nhật `available` từ `10` còn `8`.
2. `insertOrder(900, ...)` vi phạm primary key vì `id=900` đã tồn tại; `JdbcTemplate` ném lỗi truy cập dữ liệu unchecked.
3. Transaction proxy của service rollback các thay đổi đã thực thi trong transaction.
4. Test lấy **một connection mới** hoặc đọc lại ngoài transaction thử nghiệm để xác minh `inventory.available` vẫn là `10`, không phải `8`.

Nếu repository đã tự mượn raw `dataSource.getConnection()` và commit độc lập, phép thử có thể phát hiện tồn kho vẫn bị trừ sau khi transaction ngoài rollback.

Ví dụ JUnit 5 minh họa trong một Spring Boot integration test đã cấu hình datasource/schema/fixture:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.dao.DataIntegrityViolationException;

@SpringBootTest
class OrderServiceTransactionIT {
    @Autowired
    private OrderService orderService;

    @Autowired
    private JdbcTemplate jdbc;

    @Test
    void rollsBackReservationWhenOrderInsertFails() {
        // Fixture được seed bởi setup/migration trước test:
        // product 101 có available=10, order 900 đã tồn tại.
        assertThrows(DataIntegrityViolationException.class,
                () -> orderService.placeOrder(900L, 101L, 2));

        Integer available = jdbc.queryForObject(
                "SELECT available FROM inventory WHERE product_id = ?",
                Integer.class,
                101L);

        assertEquals(10, available);
    }
}
```

Các giả định phải được đảm bảo: `@SpringBootTest` có các bean thật, test database hỗ trợ transaction, unique constraint, fixture được chuẩn bị trước và mỗi test được cách ly. Nếu hệ quản trị/driver ánh xạ duplicate key thành subclass `DataAccessException` khác, assertion có thể được điều chỉnh ở **hợp đồng phân loại đã kiểm chứng**, không nuốt lỗi hay bỏ kiểm tra rollback.

**Điểm rất quan trọng:** Không tùy tiện đặt `@Transactional` trên chính phương thức/class test này. Trong nhiều cấu hình Spring Test, một test transactional được **rollback khi test kết thúc**. Điều đó có thể che việc service thật ra không mở transaction riêng, hoặc làm khó quan sát dữ liệu sau khi commit. Để kiểm chứng transaction boundary của service, test nên tự kiểm soát setup/cleanup và gọi service **qua bean proxy** như production.

### Các ca integration test khác

| Ca thử | Điều cần xác minh |
| --- | --- |
| Spring `JdbcTemplate` gọi trong `@Transactional` | Nhiều repository dùng chung transaction; rollback một bước hoàn tác bước trước |
| Raw `DataSource.getConnection()` ở DAO | Phát hiện đường ghi tách transaction nếu target datasource không transaction-aware |
| `DataSourceUtils.getConnection/releaseConnection` | Thao tác low-level tham gia transaction và không đóng sớm connection |
| Checked `SQLException` từ DAO | Mặc định và `rollbackFor=SQLException.class` khác nhau đúng dự kiến |
| Service tự gọi method `@Transactional` | Phát hiện self-invocation không đi qua proxy theo mô hình đang dùng |
| `REQUIRES_NEW` | Inner transaction commit độc lập, outer rollback không hoàn tác inner |
| `NESTED` | Savepoint hoạt động khi driver/transaction manager hỗ trợ |
| Method chạy trên thread mới | Không vô tình sử dụng thread-bound transaction của thread gốc |
| Timeout transaction | Query/statement thực sự nhận timeout phù hợp, không suy từ annotation |
| Pool reuse | Sau rollback, connection không còn session state sai cho request sau |
| Deadlock/serialization failure | Rollback và retry toàn transaction theo chính sách có giới hạn |
| Nhiều DataSource | Xác định chính xác resource nào thuộc local transaction manager |

## 16. Connection pool, hiệu năng và thời gian giữ kết nối

Khi `@Transactional` bắt đầu, Spring transaction manager thường lấy một connection và có thể **giữ nó đến cuối phương thức transactional**, ngay cả khi các câu SQL chỉ chiếm một phần nhỏ thời gian đó. Ví dụ:

```java
@Transactional
public void checkout(Order order) {
    repository.reserveStock(...); // SQL: vài ms

    paymentClient.charge(...);    // HTTP bên ngoài: có thể nhiều giây

    repository.insertOrder(...);  // SQL: vài ms
}
```

Việc giữ transaction mở qua HTTP call gây một số rủi ro:

- Giữ `Connection` lâu hơn cần thiết và làm pool cạn khi tải cao.
- Giữ lock hoặc snapshot dài hơn, tăng lock wait/deadlock và giảm throughput.
- Nếu thanh toán bên ngoài thành công nhưng DB rollback, hệ thống có tác động không đồng bộ khó đối soát.
- Hết timeout của database không tự hoàn tác thao tác thanh toán.

Hướng cải tiến phụ thuộc nghiệp vụ: thiết kế ranh giới DB transaction ngắn, tách bước gọi ngoài, dùng outbox/saga/idempotency khi cần đảm bảo tính nhất quán qua hệ thống. Không đơn giản “đưa `@Transactional` lên controller” để bao toàn bộ request.

### Những metric cần theo dõi

- Connection pool `active/idle/pending`, thời gian chờ checkout, thời gian giữ connection.
- Thời gian giao dịch, số câu SQL trong transaction, độ trễ query p95/p99.
- Tỷ lệ rollback, serialization failure, deadlock, lock wait.
- Số transaction `REQUIRES_NEW` lồng nhau so với cấu hình pool.
- Lỗi sau commit/rollback, timeout, connection leak hoặc kết nối không được phục hồi trạng thái.
- Dữ liệu bị commit một phần do dùng raw connection ngoài transaction.

Nếu pool đã cạn kết nối vì các transaction giữ connection quá lâu, tăng `maximumPoolSize` có thể khiến database cạn tài nguyên nhanh hơn. Hãy điều tra transaction scope, SQL và tác vụ ngoài database trước.

## 17. Chọn phương án và quy tắc trách nhiệm

| Hoàn cảnh | Lựa chọn thường phù hợp | Điều kiện để an toàn |
| --- | --- | --- |
| Ứng dụng Java thuần | JDBC transaction thủ công | Một bên sở hữu connection, commit/rollback/reset/close đầy đủ |
| Spring service dùng nhiều DAO JDBC | `@Transactional` + `JdbcTemplate` | Các DAO dùng cùng target DataSource và transaction manager; proxy thực sự hoạt động |
| Spring cần kiểm soát transaction cho một khối code | `TransactionTemplate` | Callback ngắn, không tự commit/close connection thuộc transaction |
| Mã JDBC cấp thấp trong Spring | `DataSourceUtils` | `getConnection/releaseConnection` đúng cặp; quản lý statement/result set |
| Thư viện legacy chỉ nhận `DataSource` | `TransactionAwareDataSourceProxy` | Wrapper đúng target, kiểm thử rollback, không để thư viện tự sở hữu transaction trái phép |
| Tác vụ nền nhiều thread | Transaction scope riêng cho mỗi tác vụ | Không mặc định thread-bound context hoặc connection được chia sẻ |
| Nhiều DB hoặc external service | Thiết kế distributed consistency thích hợp | Không suy `@Transactional` local bao mọi resource |

### Checklist trước khi code

1. **Ai sở hữu transaction?** Service, transaction manager, hay DAO độc lập? Chỉ có một nguồn quyết định commit/rollback.
2. **Ai sở hữu `Connection`?** Bên lấy kết nối trực tiếp hay Spring đang gắn nó với transaction? Không đóng tài nguyên mình không sở hữu.
3. **Mọi DAO có cùng target `DataSource` không?** Nếu không, xác định rõ giao dịch nào áp dụng cho từng resource.
4. **Mọi lời gọi `@Transactional` có qua proxy không?** Đặc biệt với self-invocation, private/final methods và thread khác.
5. **Exception nào kích hoạt rollback?** `DataAccessException` unchecked khác `SQLException` checked; kiểm tra `rollbackFor` và nhánh bắt lỗi.
6. **Có propagation đặc biệt không?** `REQUIRES_NEW`, `NESTED` hoặc `NOT_SUPPORTED` làm thay đổi phạm vi atomicity.
7. **Có SQL điều kiện và ràng buộc đúng không?** `@Transactional` không tự ngăn lost update và bán quá tồn kho.
8. **Có gọi API ngoài DB trong transaction không?** Nếu có, xem lại thời gian giữ connection và kế hoạch đối soát.
9. **Có test rollback thật trên DB không?** Kết quả commit/rollback phải được đọc lại ngoài scope giao dịch thử nghiệm.
10. **Có cơ chế xử lý connection/commit không rõ trạng thái không?** Khi rollback thất bại hoặc mất kết nối, không trả connection nghi vấn vào pool như bình thường nếu có thể loại bỏ.

## 18. Bài thực hành

### Bài 1 — cùng nghiệp vụ ở hai mô hình

Viết hai phiên bản đặt hàng:

- **JDBC thuần:** một service lấy `Connection`, đặt `autoCommit=false`, thực thi `UPDATE inventory` và `INSERT orders` trên cùng connection, rollback khi lỗi.
- **Spring:** đặt `@Transactional` trên một Spring-managed service, gọi các DAO `JdbcTemplate` tương ứng, không tự commit.

Dùng cùng schema, input và ràng buộc, kiểm tra kết quả khi cả hai bước thành công, khi hết tồn kho và khi `INSERT` vi phạm unique key. So sánh số dòng code giao dịch nhưng **không đánh đổi khả năng kiểm soát lỗi**.

### Bài 2 — cố ý tạo lỗi dùng raw DataSource

Trong service `@Transactional`, dùng `JdbcTemplate` cho bước 1 nhưng dùng `dataSource.getConnection()` trực tiếp trên raw pool cho bước 2. Gây lỗi sau bước 2 và kiểm tra liệu có bản ghi nào bị commit độc lập. Sau đó sửa bằng `JdbcTemplate` hoặc `DataSourceUtils`; xác nhận rollback được cả hai bước.

Chỉ thực hiện trên database thử nghiệm. Không dựa vào việc “không thấy lỗi” để kết luận transaction đã đúng; phải đọc lại dữ liệu sau thất bại.

### Bài 3 — checked exception và propagation

Tạo DAO dùng `DataSourceUtils`, có thể ném `SQLException`. So sánh `@Transactional` mặc định và `@Transactional(rollbackFor = SQLException.class)`. Thử thêm một inner bean có `REQUIRES_NEW` rồi outer rollback; xác minh inner commit độc lập theo thiết kế.

### Bài 4 — proxy và luồng

Gọi một `@Transactional` method thông qua `this.method()`, rồi gọi cùng method từ một Spring bean khác. So sánh transaction status và hậu điều kiện DB. Thử thực thi DAO ở thread mới; xác định vì sao transaction của thread gốc không tự đi theo.

### Bài 5 — giữ connection và timeout

Đo thời gian giữ connection trong một service transaction có query nhanh nhưng lời gọi HTTP chậm. Chuyển lời gọi HTTP ra khỏi DB transaction theo thiết kế phù hợp; so sánh pool active/idle/pending, p95/p99 và khả năng xử lý lỗi. Không dùng một benchmark đơn luồng làm kết luận chung.

### Câu hỏi tự kiểm tra

- Tại sao `@Transactional` không bảo đảm `dataSource.getConnection()` trên raw pool trả cùng connection đang được Spring quản lý?
- `DataSourceUtils.releaseConnection(...)` khác `Connection.close()` như thế nào khi connection đã gắn với transaction hiện hành?
- Khi `JdbcTemplate` ném `DataAccessException`, vì sao Spring thường rollback mặc định? Còn `SQLException` checked thì sao?
- Vì sao self-invocation có thể làm `@Transactional` không được áp dụng trong proxy mode?
- `REQUIRES_NEW` khác `NESTED` ở phạm vi commit và tài nguyên kết nối như thế nào?
- Khi một service transaction gọi API thanh toán ngoài DB, rollback của DB có hoàn tác thanh toán không?
- Vì sao kiểm thử có `@Transactional` ở chính phương thức test đôi khi che lỗi transaction boundary của service?
- Cần kiểm tra những gì trước khi khẳng định hai `JdbcTemplate` tham gia cùng một transaction?
- `readOnly=true` có phải cơ chế phân quyền ghi ở DB không?
- Tại sao `TransactionTemplate` có thể tránh bẫy self-invocation của transaction annotation?

## 19. Tổng kết

1. **JDBC thủ công** cho phép kiểm soát trực tiếp transaction nhưng cũng buộc ứng dụng sở hữu toàn bộ logic `commit()`, `rollback()`, khôi phục connection state và cleanup.
2. **Spring transaction manager** điều phối cùng một JDBC connection cho các thao tác tương thích trong scope giao dịch; `JdbcTemplate` là lựa chọn mặc định tốt cho CRUD JDBC trong Spring.
3. **`@Transactional` không tự biến mọi lời gọi `getConnection()` thành transaction-aware.** Dùng đúng `JdbcTemplate`, `DataSourceUtils` hoặc proxy cho mã legacy; tránh raw pool checkout nằm ngoài transaction.
4. **Hiểu proxy, thread và propagation.** Self-invocation, `REQUIRES_NEW`, `NESTED` và tác vụ khác thread có thể làm thay đổi transaction boundary thật.
5. **Rollback phụ thuộc loại exception và chính sách khai báo.** `DataAccessException` unchecked thường kích hoạt rollback mặc định; checked `SQLException` cần quy tắc cụ thể hoặc translation phù hợp.
6. **Spring không thay thế quy tắc dữ liệu.** SQL có điều kiện, ràng buộc, concurrency control và chính sách idempotency vẫn cần được thiết kế.
7. **Kiểm thử trên database thật và đo thời gian giữ kết nối.** Đường thành công, rollback, xử lý lỗi và hành vi pool phải được xác minh, không chỉ nhìn annotation.

**Kết luận:** khác biệt giữa kết nối tự quản lý và kết nối gắn với giao dịch Spring nằm ở **quyền sở hữu và việc chia sẻ cùng JDBC Connection trong đúng phạm vi transaction**. Khi tầng service sở hữu ranh giới giao dịch, DAO dùng công cụ Spring transaction-aware và ứng dụng kiểm thử được rollback thật, ta có thể giảm boilerplate mà vẫn giữ tính nguyên tử và khả năng bảo trì của hệ thống JDBC.
