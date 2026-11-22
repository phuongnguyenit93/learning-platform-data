# Tránh tự commit hoặc đóng sai kết nối do Spring framework sở hữu

Trong chương **Tích hợp Spring**, ứng dụng Java vẫn thực hiện CRUD bằng JDBC: tạo `PreparedStatement`, bind tham số SQL, đọc `ResultSet` và xử lý lỗi. Điểm khác biệt là **quyền sở hữu `Connection` và transaction** có thể đã được Spring quản lý. Khi dùng `@Transactional` cùng `JdbcTemplate` hoặc `DataSourceUtils`, một lời gọi `connection.commit()`, `rollback()`, `setAutoCommit(...)` hay `close()` đặt sai chỗ có thể phá vỡ giao dịch nhiều bước, trả kết nối về pool quá sớm hoặc khiến SQL thực thi ngoài giao dịch mà lập trình viên tưởng đang có.

Ví dụ, service chuyển tiền ghi hai lệnh `UPDATE`: trừ số dư nguồn và cộng số dư đích. Tầng service mở một transaction bằng `@Transactional`; repository dùng `JdbcTemplate` để chạy SQL. Nếu repository tự commit sau lệnh trừ tiền, rồi lệnh cộng tiền ném lỗi, Spring không còn khả năng rollback toàn bộ công việc như mong đợi. Ngược lại, nếu DAO dùng `dataSource.getConnection()` trực tiếp trên một pool thông thường, nó có thể mượn **kết nối khác** với kết nối đang được Spring gắn vào transaction, khiến `@Transactional` không bao phủ câu SQL đó.

Bài học tập trung vào **hợp đồng sở hữu tài nguyên** trong Spring JDBC: ai bắt đầu và kết thúc transaction, ai mượn/trả `Connection`, khi nào đóng `PreparedStatement`/`ResultSet`, dùng `DataSourceUtils` ra sao nếu phải viết JDBC thuần, và cách kiểm thử để chứng minh rollback thật sự diễn ra.

## 1. Ai sở hữu điều gì trong một giao dịch Spring JDBC?

Khi một phương thức Spring được gọi qua proxy có `@Transactional` và transaction manager phù hợp, luồng xử lý thông thường là:

```text
Caller
  |
  v
Spring transaction proxy / interceptor
  | bắt đầu hoặc tham gia transaction
  v
PlatformTransactionManager
  | lấy/bind JDBC Connection vào ngữ cảnh transaction của thread
  v
@Transactional Service
  |
  +--> Repository A --> JdbcTemplate --> SQL UPDATE
  |
  +--> Repository B --> JdbcTemplate --> SQL INSERT
  |
  v
Service kết thúc hoặc ném exception
  |
  v
Transaction manager --> COMMIT hoặc ROLLBACK
  |
  v
Giải phóng/reset Connection và trả về DataSource/pool
```

Sơ đồ này là mô hình **transaction JDBC cục bộ** với `DataSourceTransactionManager` hoặc `JdbcTransactionManager` và các thành phần cùng dùng một nguồn dữ liệu được cấu hình đúng. Với JTA, JPA, nhiều data source hoặc proxy/lazy connection khác, cách triển khai chi tiết có thể khác; không tự suy diễn mô hình này cho mọi transaction manager.

| Tài nguyên hoặc quyết định | Bên chịu trách nhiệm trong Spring JDBC |
| --- | --- |
| Bắt đầu transaction, chọn isolation, trạng thái `autoCommit` | Transaction manager |
| `commit()` hoặc `rollback()` của transaction đang được Spring quản lý | Transaction manager |
| Bind/reuse connection đúng ngữ cảnh transaction | Spring thông qua `DataSourceUtils` hoặc lớp tích hợp |
| Đóng `PreparedStatement`, `ResultSet` của một thao tác | `JdbcTemplate` hoặc code sở hữu chúng |
| Giải phóng connection sau khi kết thúc transaction | Hạ tầng transaction/Spring và pool |
| Quyết định rollback dựa trên lỗi nghiệp vụ | Tầng service và chính sách `@Transactional` |

**Quy tắc cốt lõi:** Nếu một `Connection` thuộc transaction do framework quản lý, DAO **không** được tự quyết định `commit`, `rollback`, đổi `autoCommit` hoặc đóng trực tiếp kết nối ấy. Đóng statement/result set của chính DAO vẫn là điều cần làm.

## 2. Vì sao `DataSource.getConnection()` trực tiếp có thể nguy hiểm?

Trong JDBC thuần, mẫu sau là hợp lệ khi **phương thức tự mượn và sở hữu connection**:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps =
             connection.prepareStatement("SELECT COUNT(*) FROM customer");
     ResultSet rs = ps.executeQuery()) {
    rs.next();
    long count = rs.getLong(1);
}
```

Nhưng trong một giao dịch Spring đã có kết nối gắn với thread, gọi trực tiếp `dataSource.getConnection()` trên `HikariDataSource` hoặc pool thông thường **không nhất thiết** lấy đúng connection đang tham gia transaction. Nó có thể mượn một connection độc lập đang `autoCommit=true`.

Ví dụ sai trong repository được gọi từ `@Transactional`:

```java
// SAI trong transaction Spring nếu DataSource này là pool thông thường:
public void insertAuditWrong(DataSource dataSource, long customerId)
        throws SQLException {
    try (Connection connection = dataSource.getConnection();
         PreparedStatement ps = connection.prepareStatement(
                 "INSERT INTO customer_audit(customer_id) VALUES (?)")) {
        ps.setLong(1, customerId);
        ps.executeUpdate();  // Có thể tự commit ngoài transaction service.
    }
}
```

Nếu service sau đó rollback, thay đổi ở `customer_audit` có thể **không được hoàn tác** vì đã ghi bằng connection khác. `try-with-resources` vẫn đóng đúng connection mà DAO đã tự mượn, nhưng vấn đề là **nó đã mượn sai connection** so với ranh giới transaction mong muốn.

Spring có `TransactionAwareDataSourceProxy` dành cho một số thành phần JDBC kế thừa cần gọi `DataSource.getConnection()` trực tiếp. Proxy này có thể chuyển lời gọi sang kết nối nhận biết transaction và điều chỉnh hành vi `close()`; tuy nhiên **không mặc định mọi `DataSource` đều là proxy đó**. Với code Spring hiện đại, thường nên dùng `JdbcTemplate` hoặc `DataSourceUtils` thay vì dựa vào proxy một cách ngầm định.

## 3. Cách ưu tiên: `@Transactional` ở service và `JdbcTemplate` ở DAO

Giả sử bảng `account` được định nghĩa bằng cột `id BIGINT PRIMARY KEY` và `balance DECIMAL(18,2) NOT NULL` trên một DB hỗ trợ transaction. Service phải chuyển số tiền từ nguồn sang đích theo nguyên tắc **cùng thành công hoặc cùng rollback**.

```java
import java.math.BigDecimal;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long fromId, long toId, BigDecimal amount) {
        if (fromId == toId || amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Yêu cầu chuyển tiền không hợp lệ");
        }

        int debit = jdbc.update("""
                UPDATE account
                SET balance = balance - ?
                WHERE id = ? AND balance >= ?
                """, amount, fromId, amount);

        if (debit != 1) {
            throw new IllegalStateException(
                    "Tài khoản nguồn không tồn tại hoặc số dư không đủ");
        }

        int credit = jdbc.update("""
                UPDATE account
                SET balance = balance + ?
                WHERE id = ?
                """, amount, toId);

        if (credit != 1) {
            throw new IllegalStateException("Tài khoản đích không tồn tại");
        }
    }
}
```

Đây là **ví dụ transaction**, không phải hệ thống thanh toán hoàn chỉnh. Dự án thật cần quy tắc tiền tệ, chống trùng yêu cầu, thứ tự khóa khi đồng thời, xử lý deadlock, quyền truy cập và kiểm toán. `jdbc.update(...)` dùng tham số `?` nên các giá trị không bị ghép vào cú pháp SQL; Spring quản lý statement, connection và chuyển `SQLException` sang hệ `DataAccessException`.

Với cấu hình transaction manager đúng:

1. Caller gọi `transfer(...)` **qua Spring proxy**, không phải gọi trực tiếp từ `this` bên trong cùng bean.
2. Spring bắt đầu transaction hoặc tham gia transaction hiện có.
3. Cả hai `jdbc.update(...)` lấy connection theo ngữ cảnh transaction thông qua hạ tầng Spring.
4. Nếu `debit` hoặc `credit` không đáp ứng bất biến, service ném `IllegalStateException` (unchecked).
5. Theo chính sách rollback mặc định thông dụng của `@Transactional`, unchecked exception và `Error` khiến giao dịch rollback.
6. Nếu phương thức hoàn thành bình thường, transaction manager quyết định commit theo phạm vi và propagation.

Không có lời gọi `connection.commit()`, `rollback()` hoặc `close()` nào trong repository/service. **Đó là chủ đích**, không phải thiếu bước xử lý.

### Cấu hình cần khớp đúng nguồn dữ liệu

Một ví dụ Spring Java configuration cho ứng dụng chỉ có **một `DataSource`**:

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
    public PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
```

Ví dụ giả định đã có một bean `DataSource` kết nối đúng DB. **Không tạo transaction manager trùng lặp** nếu Spring Boot hoặc hệ thống đã cấu hình một manager phù hợp; cần xem cấu hình thực tế. `JdbcTransactionManager` là một lựa chọn liên quan cho Spring JDBC, cung cấp khả năng dịch một số ngoại lệ khi commit/rollback. Dù dùng manager nào, nó phải quản lý **cùng nguồn kết nối thực tế** mà `JdbcTemplate` sử dụng; sự khác biệt về proxy/wrapper cần được cấu hình nhất quán.

Nếu dự án vừa dùng JPA vừa dùng JDBC, không mặc định rằng thêm một `DataSourceTransactionManager` mới là đúng. Cần xác định transaction manager đang sở hữu các thao tác và khả năng cho JDBC cùng tham gia transaction đó theo cấu hình JPA/provider, hoặc chủ động thiết kế ranh giới riêng.

## 4. Không tự `commit()`, `rollback()` hay đổi `autoCommit` trong DAO

Trong JDBC thuần, lập trình viên có thể làm:

```java
connection.setAutoCommit(false);
try {
    executeFirstUpdate(connection);
    executeSecondUpdate(connection);
    connection.commit();
} catch (SQLException failure) {
    connection.rollback();
    throw failure;
}
```

Đây là mô hình **tự sở hữu transaction** và có thể hợp lệ **ngoài** phạm vi framework. Nhưng khi `connection` do transaction manager của Spring quản lý, các lệnh trên không được đặt trong DAO:

- `commit()` có thể kết thúc transaction **trước** khi service hoàn tất các bước còn lại.
- `rollback()` có thể hủy thay đổi của nhiều DAO khác trong cùng transaction, trái với chính sách của tầng service.
- `setAutoCommit(true)` có thể gây commit ngầm theo quy tắc JDBC khi chuyển chế độ, hoặc thay đổi trạng thái connection mà manager đang quản lý.
- `setAutoCommit(false)`/`setTransactionIsolation(...)`/`setReadOnly(...)` có thể đè cấu hình do Spring đã áp dụng cho giao dịch.
- `close()` trên một connection do transaction quản lý có thể làm những câu SQL tiếp theo lỗi hoặc khiến trạng thái pool bị xử lý sai.

Với transaction Spring, **chỉ manager mới quyết định kết thúc giao dịch**. Nếu cần đổi isolation, timeout hoặc read-only của cả transaction, cấu hình trên ranh giới giao dịch:

```java
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(
        isolation = Isolation.READ_COMMITTED,
        timeout = 10,
        readOnly = true)
public void generateReport() {
    // Dùng JdbcTemplate để đọc; không tự sửa Connection.
}
```

Đây là ví dụ annotation trên phương thức hợp lệ trong một Spring bean có transaction manager. `readOnly=true` là một chỉ dẫn và có thể được driver/DB thực thi theo những cách khác nhau; **không thay thế tài khoản DB chỉ có quyền `SELECT`**. Mức cô lập và timeout khả dụng còn phụ thuộc database, driver và transaction manager.

## 5. Viết JDBC thuần trong Spring: dùng `DataSourceUtils` đúng cách

Đôi khi cần truy cập API driver hoặc dùng `PreparedStatement` theo cách `JdbcTemplate` chưa bao phủ thuận tiện. Trong phạm vi transaction do Spring quản lý, cách thông dụng là lấy connection qua **`DataSourceUtils.getConnection(dataSource)`** và giải phóng bằng **`DataSourceUtils.releaseConnection(connection, dataSource)`**.

Ví dụ DAO tự dùng JDBC chuẩn bên trong Spring:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;
import org.springframework.jdbc.UncategorizedSQLException;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.stereotype.Repository;

@Repository
public class AuditJdbcDao {
    private final DataSource dataSource;

    public AuditJdbcDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void insert(long customerId, String action) {
        String sql = """
                INSERT INTO customer_audit (customer_id, action)
                VALUES (?, ?)
                """;

        Connection connection = DataSourceUtils.getConnection(dataSource);
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, customerId);
            ps.setString(2, action);

            // Tùy chọn: áp dụng timeout của transaction hiện hành
            // cho statement khi viết JDBC thuần.
            DataSourceUtils.applyTransactionTimeout(ps, dataSource);

            if (ps.executeUpdate() != 1) {
                throw new IllegalStateException(
                        "Audit INSERT phải ảnh hưởng đúng một hàng");
            }
        } catch (SQLException failure) {
            throw new UncategorizedSQLException(
                    "Ghi customer_audit", sql, failure);
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }
}
```

**Hai điểm không được bỏ sót:**

1. `DataSourceUtils.getConnection` sử dụng quy tắc Spring để tìm/reuse connection đã gắn với transaction của thread, khi data source và manager được cấu hình phù hợp. Nó cũng có thể lấy connection mới nếu chưa có transaction.
2. `DataSourceUtils.releaseConnection` **không đóng connection đang thuộc transaction Spring**; khi ở ngoài transaction nó giải phóng connection theo cơ chế phù hợp. Dùng `connection.close()` thay thế trong code này là sai hợp đồng.

`PreparedStatement` thuộc DAO nên được đóng bằng `try-with-resources`. Nếu có `ResultSet`, đóng nó trước statement. `UncategorizedSQLException` ở ví dụ là ngoại lệ **unchecked** của Spring, giữ nguyên nguyên nhân `SQLException` và tương thích rollback mặc định khi lan ra ngoài phương thức `@Transactional`. Với ứng dụng thật, nên dùng bộ dịch lỗi `SQLExceptionTranslator` của Spring (hoặc `JdbcTemplate`) để phân loại đúng hơn theo DB, thay vì coi mọi lỗi JDBC là chưa phân loại.

**Không viết `try (Connection connection = DataSourceUtils.getConnection(dataSource))`** trong DAO đang tham gia transaction: khối đó sẽ gọi `close()` trực tiếp lên connection khi thoát, làm sai quyền sở hữu. `DataSourceUtils.releaseConnection(...)` ở `finally` mới là cặp thao tác tương ứng.

### `JdbcTemplate.execute(ConnectionCallback)` khi cần tùy biến

Một lựa chọn khác là dùng callback do `JdbcTemplate` quản lý:

```java
import java.sql.PreparedStatement;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;

public int updateWithCallback(JdbcTemplate jdbc, long id) {
    return jdbc.execute((ConnectionCallback<Integer>) connection -> {
        // Connection do JdbcTemplate cung cấp; không tự close/commit/rollback.
        String sql = "UPDATE job SET attempts = attempts + 1 WHERE id = ?";
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, id);
            return ps.executeUpdate();
        }
    });
}
```

Callback nhận một connection do Spring quản lý trong thời gian thực thi. `JdbcTemplate` lo lấy/trả connection thích hợp; code chỉ đóng những statement/result set tự tạo. Không lưu tham chiếu `connection` để dùng sau khi callback kết thúc hoặc gửi sang thread khác.

## 6. So sánh các cách lấy và trả connection

| Cách dùng | Phạm vi phù hợp | Quy tắc quan trọng |
| --- | --- | --- |
| `JdbcTemplate.query/update/execute` | Spring JDBC thông dụng | Không tự quản lý connection; viết callback/RowMapper đúng vòng đời |
| `DataSourceUtils.getConnection` + `releaseConnection` | JDBC thuần cần tham gia transaction Spring | Luôn ghép đúng cặp get/release; không `close()` trực tiếp |
| `DataSource.getConnection` + `close()` | JDBC thuần **tự sở hữu connection**, ngoài transaction Spring hoặc theo proxy đã được thiết kế | Đừng mặc định tham gia giao dịch `@Transactional` |
| `TransactionAwareDataSourceProxy` | Tích hợp mã kế thừa yêu cầu `DataSource.getConnection` | Cấu hình proxy/target đúng và kiểm thử; không phải thay thế chung cho `JdbcTemplate` |
| `Connection` được truyền từ service | DAO thấp hơn, theo transaction do service sở hữu | DAO đóng statement/result set, **không** commit/rollback/close connection |

Một repository không nên trộn tùy tiện những cách trên. Ví dụ, nếu service đã chọn `JdbcTemplate`, phần lớn truy vấn khác cũng nên dùng nó, để mọi thao tác đi qua cùng nguồn dữ liệu và transaction manager.

Đừng giữ một `Connection` trong field singleton `@Repository` để tái sử dụng giữa các request. Spring bean singleton có thể được nhiều thread gọi đồng thời; connection có trạng thái transaction, cursor và session nên cần vòng đời **theo đơn vị công việc**, không theo vòng đời bean.

## 7. Quy tắc rollback của `@Transactional` và ngoại lệ bị bắt

Mặc định phổ biến của Spring transaction theo annotation là rollback khi ngoại lệ **unchecked** (`RuntimeException` và lớp con) hoặc `Error` thoát ra khỏi ranh giới transaction. Ngoại lệ **checked** như `SQLException` có thể không gây rollback theo quy tắc mặc định, trừ khi cấu hình `rollbackFor` hoặc chính sách chung khác.

Ví dụ phương thức trực tiếp ném checked exception:

```java
import java.sql.SQLException;
import org.springframework.transaction.annotation.Transactional;

@Transactional(rollbackFor = SQLException.class)
public void importOrders() throws SQLException {
    // Thao tác JDBC thuần có thể ném SQLException.
    // DAO phải dùng kết nối nhận biết transaction Spring.
}
```

Lưu ý: đặt `rollbackFor` **không tự sửa** việc DAO đã mượn connection ngoài transaction. Cần có cả hai: truy cập đúng tài nguyên transaction **và** quy tắc rollback đúng loại lỗi.

### Bắt lỗi rồi trả kết quả có thể khiến Spring cố commit

```java
// SAI nếu service muốn rollback toàn bộ khi lệnh UPDATE lỗi:
@Transactional
public boolean updateAndIgnoreFailure() {
    try {
        jdbc.update("UPDATE account SET balance = balance - 10 WHERE id = ?", 1L);
        return true;
    } catch (org.springframework.dao.DataAccessException failure) {
        // Lỗi đã bị nuốt, transaction interceptor không nhìn thấy exception.
        return false;
    }
}
```

Nếu ngoại lệ đã được bắt và phương thức hoàn thành bình thường, transaction interceptor có thể **cố commit**, trừ khi transaction đã bị đánh dấu rollback-only hoặc DB từ chối tiếp tục. Với PostgreSQL chẳng hạn, một lỗi SQL có thể khiến transaction ở trạng thái thất bại và yêu cầu rollback; không có bảo đảm việc “nuốt lỗi” khiến các thao tác sau chạy được.

Giải pháp thường đơn giản nhất là **để ngoại lệ thoát ra** và dịch lỗi nghiệp vụ ở **tầng ngoài** ranh giới giao dịch. Khi service cần trả một kết quả nghiệp vụ thay vì ném lỗi nhưng vẫn muốn rollback, có thể đánh dấu rollback-only trong một transaction thực sự đang hoạt động:

```java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Transactional
public boolean updateAndRollbackOnFailure() {
    try {
        jdbc.update("UPDATE account SET balance = balance - 10 WHERE id = ?", 1L);
        return true;
    } catch (org.springframework.dao.DataAccessException failure) {
        TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
        return false;
    }
}
```

Ví dụ dùng `TransactionAspectSupport` chỉ hợp lệ khi đang chạy trong transaction được Spring quản lý. Với mã nghiệp vụ phức tạp, ném một ngoại lệ miền ứng dụng có kiểu rõ ràng thường dễ hiểu hơn việc trả `false` và điều khiển rollback bằng trạng thái ẩn.

**Trường hợp lồng transaction:** nếu một phương thức con đánh dấu giao dịch dùng chung rollback-only, phương thức ngoài bắt lỗi rồi tiếp tục có thể gặp `UnexpectedRollbackException` khi cố commit. Điều này bảo vệ tính nguyên tử; không chữa bằng cách gọi `connection.commit()` thủ công.

## 8. `TransactionTemplate`: transaction lập trình nhưng vẫn do Spring quản lý

Nếu không muốn dùng annotation hoặc cần chọn ranh giới ở runtime, Spring cung cấp `TransactionTemplate`. Đây là cách quản lý transaction **bằng API Spring**, không phải bật/tắt `autoCommit` trực tiếp:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public class JobService {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate tx;

    public JobService(
            JdbcTemplate jdbc,
            PlatformTransactionManager transactionManager) {
        this.jdbc = jdbc;
        this.tx = new TransactionTemplate(transactionManager);
    }

    public boolean markProcessed(long jobId) {
        return Boolean.TRUE.equals(tx.execute(status -> {
            int updated = jdbc.update("""
                    UPDATE job
                    SET state = 'PROCESSED'
                    WHERE id = ? AND state = 'PENDING'
                    """, jobId);

            if (updated != 1) {
                status.setRollbackOnly();
                return false;
            }
            return true;
        }));
    }
}
```

`TransactionTemplate` sử dụng `PlatformTransactionManager` để begin/commit/rollback theo kết quả callback và trạng thái rollback-only. `JdbcTemplate` bên trong callback tham gia cùng ngữ cảnh transaction khi cùng nguồn dữ liệu. Ví dụ không cần lấy `Connection` và không dùng `commit()` thủ công.

**Không kết hợp cả `TransactionTemplate` và `@Transactional` một cách vô thức.** Việc gọi trong transaction có sẵn tuân theo propagation và các thuộc tính transaction đã cấu hình; cần biết thao tác đang **tham gia** hay **tạo transaction riêng**.

## 9. Propagation, thread và proxy: vì sao tưởng có transaction mà lại không?

### Gọi nội bộ trong cùng bean

Trong chế độ Spring transaction qua proxy, một lời gọi `this.transfer(...)` hoặc gọi phương thức nội bộ không đi qua proxy có thể **bỏ qua advice `@Transactional`** của phương thức được gọi:

```java
@Service
public class ImportService {
    public void runImport() {
        saveChunk(); // Self-invocation: không đi qua transactional proxy.
    }

    @Transactional
    public void saveChunk() {
        // Có thể không được bắt đầu transaction như mong muốn.
    }
}
```

Để bảo đảm ranh giới transaction, gọi một phương thức `@Transactional` qua Spring-managed bean/proxy ở tầng service khác, hoặc dùng `TransactionTemplate` khi thực sự cần self-invocation. Đừng chỉ đặt annotation lên một phương thức `private` rồi giả định proxy sẽ áp dụng.

### Giao dịch thường gắn với thread đang thực thi

`DataSourceTransactionManager` dùng cơ chế ràng buộc tài nguyên theo thread. Bởi vậy:

- `@Async`, `CompletableFuture.supplyAsync` hoặc một thread mới **không tự động thừa hưởng** transaction JDBC của thread gọi.
- Truyền `Connection` đang được Spring quản lý sang thread khác có thể gây lỗi vòng đời, race condition hoặc truy cập ngoài transaction.
- Nếu một tác vụ bất đồng bộ cần transaction, hãy đặt ranh giới transaction **bên trong tác vụ** thông qua Spring proxy hoặc `TransactionTemplate`.

Không coi một `@Transactional` trên controller đồng nghĩa mọi thao tác bất đồng bộ được gọi từ controller đều nằm trong cùng giao dịch.

### Các kiểu propagation đáng chú ý

| Propagation | Ý nghĩa đối với connection/transaction |
| --- | --- |
| `REQUIRED` (mặc định) | Tham gia transaction hiện tại nếu có; nếu không thì tạo mới |
| `REQUIRES_NEW` | Tạm treo transaction hiện tại và tạo transaction độc lập; thường cần thêm một connection từ pool |
| `NESTED` | Với JDBC manager và driver hỗ trợ savepoint, có thể tạo transaction lồng theo savepoint trong cùng transaction vật lý |
| `SUPPORTS` | Có transaction thì tham gia; không có thì chạy ngoài transaction |

**Cảnh báo `REQUIRES_NEW`:** nếu nhiều request đã giữ kết nối cho transaction ngoài và cùng gọi transaction mới, pool có thể phải cung cấp thêm kết nối. Pool quá nhỏ có thể gây chờ hoặc bế tắc tài nguyên. Ngoài ra, inner transaction đã commit thì outer rollback **không tự hủy** thay đổi inner transaction.

`NESTED` không đồng nghĩa mọi DB đều hỗ trợ savepoint hoặc mọi transaction manager đều cho phép nested transaction. Cần kiểm tra cấu hình và test rollback về savepoint.

## 10. Quản lý tài nguyên bên trong callback và thời gian giữ connection

Ngay cả khi không gọi `close()` thủ công, ứng dụng vẫn có thể khiến pool cạn vì giữ transaction quá lâu. Ví dụ:

```java
@Transactional
public void processPaymentWrongly(long paymentId) {
    jdbc.update("UPDATE payment SET state = 'PROCESSING' WHERE id = ?",
            paymentId);

    // Gọi HTTP ngoài DB trong lúc transaction vẫn mở.
    callRemotePaymentGateway(paymentId);

    jdbc.update("UPDATE payment SET state = 'DONE' WHERE id = ?",
            paymentId);
}
```

Trong đoạn minh họa, `callRemotePaymentGateway` là hàm giả định. Nếu gateway chậm, transaction và connection có thể bị giữ lâu; nếu gateway đã xử lý nhưng transaction rollback, DB và hệ thống bên ngoài có thể không nhất quán. Nên thiết kế quy trình có trạng thái, idempotency hoặc outbox/saga theo yêu cầu, và thu hẹp transaction quanh những thao tác DB thực sự phải nguyên tử.

### Đóng đúng thứ cần đóng

Khi dùng JDBC thuần bên trong `DataSourceUtils` hoặc callback:

```java
// Connection do Spring quản lý; ví dụ nằm trong callback/DAO phù hợp.
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT id, title FROM book WHERE id = ?")) {
    ps.setLong(1, bookId);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            consumeBook(rs.getLong("id"), rs.getString("title"));
        }
    } // Đóng ResultSet do code tạo.
} // Đóng PreparedStatement do code tạo.
// Không gọi connection.close() ở đây nếu connection thuộc Spring.
```

`consumeBook` là hàm xử lý do ứng dụng tự định nghĩa. Nếu `ResultSet.getBinaryStream()`/`getCharacterStream()` trả luồng BLOB/CLOB, phải tiêu thụ chúng **khi ResultSet còn mở**; không trả stream ra ngoài callback rồi đóng result set.

Trên pool, thời gian connection được mượn có thể kéo dài đến **cuối phương thức `@Transactional`** dù các statement đã đóng. Khi điều tra hiệu năng, đo cả acquisition/hold time, thời gian SQL và transaction duration; không chỉ nhìn số lượng câu lệnh.

## 11. Kiểm thử để phát hiện commit sớm và connection bị đóng sai

Unit test của DAO không đủ chứng minh mọi thao tác tham gia **cùng một transaction vật lý**. Cần integration test với Spring context, đúng transaction manager, nguồn dữ liệu và DB/driver mục tiêu.

### Test rollback hai bước

Với `TransferService` ở phần 3, chuẩn bị tài khoản nguồn `id=101` có số dư ban đầu và chọn ID đích chắc chắn không tồn tại trong fixture. Ví dụ JUnit 5 với Spring Boot test:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class TransferServiceIT {
    @Autowired TransferService service;
    @Autowired JdbcTemplate jdbc;

    @Test
    void failedCreditRollsBackDebit() {
        // Fixture test: account 101 có tiền; 999999 không tồn tại.
        BigDecimal before = jdbc.queryForObject(
                "SELECT balance FROM account WHERE id = ?",
                BigDecimal.class, 101L);

        assertThrows(IllegalStateException.class,
                () -> service.transfer(
                        101L, 999999L, new BigDecimal("10.00")));

        BigDecimal after = jdbc.queryForObject(
                "SELECT balance FROM account WHERE id = ?",
                BigDecimal.class, 101L);
        assertNotNull(before);
        assertNotNull(after);
        assertEquals(0, before.compareTo(after),
                "Debit phải rollback khi credit không thành công");
    }
}
```

**Test này không nên tự gắn `@Transactional` lên method hoặc class test** nếu mục tiêu là quan sát commit/rollback thật do service quyết định. Một transaction bao quanh test có thể vô tình che việc service không tạo transaction riêng. Hãy dùng DB/schema kiểm thử cô lập, seed fixture rõ ràng và dọn dữ liệu an toàn sau test. Ngoài ra, kiểm tra rằng Spring thực sự sử dụng proxy và manager mong muốn.

### Test phát hiện DAO mượn sai connection

1. Bắt đầu transaction ở service qua `@Transactional`.
2. Trong service, gọi DAO ghi một bản ghi audit bằng `JdbcTemplate` hoặc `DataSourceUtils`.
3. Sau khi DAO ghi, cố tình ném một `RuntimeException` để buộc rollback.
4. Mở một connection/transaction độc lập sau khi service kết thúc và truy vấn audit.
5. Kỳ vọng bản ghi audit **không tồn tại**. Nếu nó vẫn tồn tại, điều tra việc DAO có dùng `dataSource.getConnection()` trực tiếp hoặc một data source/transaction manager khác hay không.

### Test ngoại lệ và quyền sở hữu

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Nhiều `JdbcTemplate.update` trong một `@Transactional`, bước sau lỗi | Mọi thay đổi trong transaction rollback |
| DAO dùng `DataSourceUtils` và `releaseConnection` | Không tự đóng connection transaction; SQL sau DAO vẫn chạy được |
| DAO gọi `connection.close()` sai chỗ | Test phải phát hiện lỗi tương tác/rollback, không coi đây là phương án hợp lệ |
| Service bắt và nuốt `DataAccessException` | Quan sát chính sách commit/rollback thật; chỉnh cách báo lỗi |
| Phương thức `@Transactional` bị gọi bằng `this.method()` | Xác minh proxy advice có thực sự chạy không |
| Phương thức có `REQUIRES_NEW` | Test inner commit/rollback độc lập với outer và tác động lên pool |
| Lời gọi từ `@Async` hoặc thread mới | Transaction của caller không tự động áp dụng |
| Runtime thay đổi DataSource hoặc transaction manager | Test lại sự tham gia giao dịch của tất cả DAO |

Có thể bật log giao dịch của Spring ở mức phù hợp trong môi trường test và đối chiếu thời điểm begin/commit/rollback với câu SQL. Không đưa SQL có thông tin cá nhân, credential hoặc toàn bộ giá trị tham số vào log production.

## 12. Chẩn đoán các lỗi thường gặp

| Triệu chứng | Nguyên nhân đáng nghi | Cách xử lý |
| --- | --- | --- |
| `@Transactional` có nhưng rollback không hủy một `INSERT` | DAO tự lấy connection ngoài transaction hoặc dùng DataSource khác | Dùng `JdbcTemplate`/`DataSourceUtils` và thống nhất manager/nguồn dữ liệu |
| `Connection is closed` ở bước thứ hai | DAO đóng connection do framework sở hữu | Không gọi `close()` trực tiếp; đóng statement/result set |
| Giao dịch chỉ rollback một phần | DAO tự `commit()`, `autoCommit=true` trên connection khác, `REQUIRES_NEW` | Xác định quyền sở hữu và propagation |
| `UnexpectedRollbackException` khi outer commit | Inner đã đánh dấu transaction dùng chung rollback-only | Không nuốt lỗi; thiết kế nhánh xử lý hoặc transaction riêng |
| SQL lỗi nhưng service trả thành công | Exception bị bắt/nuốt trong `@Transactional` | Ném lỗi hoặc đánh dấu rollback-only đúng phạm vi |
| Timeout mượn connection từ pool | Transaction dài, stream chưa tiêu thụ, `REQUIRES_NEW` thêm connection, leak | Đo hold duration, thu hẹp transaction, đóng đúng tài nguyên |
| `JdbcTemplate` không dùng cùng connection với service | Transaction manager/`DataSource` sai cấu hình hoặc không có proxy advice | Kiểm tra wiring, transaction active, integration test |
| `@Transactional` trên method tự gọi không có tác dụng | Proxy bị bypass | Gọi qua bean proxy hoặc dùng `TransactionTemplate` |
| Test pass nhưng production ghi ngoài transaction | Test thiếu Spring context hoặc khác cấu hình manager/DB | Chạy integration test production-like |
| `setReadOnly(true)` được dùng như phân quyền | Đây không phải ranh giới bảo mật | Cấp quyền SELECT thật ở DB |

## 13. Checklist và bài thực hành

### Checklist trước khi review repository Spring JDBC

1. **Xác định transaction owner:** `@Transactional`/`TransactionTemplate` nằm ở đâu? Có đúng một nơi quyết định commit/rollback không?
2. **Kiểm tra data source:** `JdbcTemplate`, `DataSourceUtils` và transaction manager có cùng nguồn kết nối thực tế không?
3. **Tìm lời gọi nguy hiểm:** trong DAO Spring-managed không có `connection.commit()`, `rollback()`, `setAutoCommit(...)` hoặc `connection.close()` thủ công.
4. **Kiểm tra vòng đời:** `PreparedStatement`/`ResultSet` được đóng đúng, nhưng connection Spring-managed được trả bởi framework.
5. **Kiểm tra exception:** loại ngoại lệ nào khiến transaction rollback? Có bắt và nuốt `DataAccessException` hay checked exception không?
6. **Kiểm tra proxy:** phương thức transactional có được gọi từ bean khác qua Spring proxy hay bị self-invocation?
7. **Kiểm tra propagation:** `REQUIRES_NEW`/`NESTED` có chủ đích, có kiểm thử tính độc lập hoặc savepoint không?
8. **Kiểm tra thời gian giữ:** có I/O mạng, sleep, xử lý báo cáo hoặc streaming BLOB trong transaction quá lâu không?
9. **Kiểm tra đa luồng:** code có gửi connection hoặc giả định transaction tự lan sang thread khác không?
10. **Kiểm tra hồi quy:** đã chạy test rollback nhiều bước trên DB/driver mục tiêu với fixture cô lập chưa?

### Bài thực hành

Hãy xây một service đặt hàng với hai DAO: `OrderDao.insert(...)` và `InventoryDao.decreaseStock(...)`. Mỗi DAO dùng `JdbcTemplate` hoặc `DataSourceUtils` đúng quy tắc, còn service có `@Transactional`.

- **Ca thành công:** tạo đơn hàng và giảm tồn kho đều thành công; kiểm tra hai thay đổi được commit.
- **Ca hết hàng:** DAO giảm tồn kho trả 0 hàng, service ném `IllegalStateException`; kiểm tra đơn hàng trước đó không còn trong DB sau rollback.
- **Ca lỗi SQL:** giả lập vi phạm khóa duy nhất và xác nhận exception được truyền đủ để rollback; không nuốt lỗi chỉ để trả `false`.
- **Ca DAO sai:** tạm thay một DAO bằng phiên bản gọi `dataSource.getConnection()` trực tiếp, kiểm tra integration test phát hiện cập nhật bị commit ngoài transaction rồi khôi phục DAO đúng.
- **Ca rollback-only:** thử nhánh service bắt lỗi, ghi nhận có thể commit/rollback như thế nào; sau đó sửa để ném exception hoặc đánh dấu rollback-only.
- **Ca propagation:** thử một thao tác `REQUIRES_NEW` để thấy khả năng commit độc lập và tác động đến số connection cần dùng.
- **Ca giữ lâu:** gọi API bên ngoài trong phạm vi transaction ở môi trường kiểm thử, đo hold duration rồi di chuyển bước ngoài DB khỏi transaction khi nghiệp vụ cho phép.

**Câu hỏi tự kiểm tra:**

- Vì sao `DataSource.getConnection()` trực tiếp trong `@Transactional` có thể tạo transaction **khác** với transaction do Spring quản lý?
- `DataSourceUtils.releaseConnection(...)` khác `connection.close()` như thế nào khi connection đã gắn với transaction?
- Trong `JdbcTemplate.execute(ConnectionCallback)`, phần nào code phải tự đóng và phần nào do Spring quản lý?
- Vì sao đặt `@Transactional(rollbackFor = SQLException.class)` chưa đủ nếu DAO vẫn tự commit?
- Nếu service bắt `DataAccessException` rồi trả `false`, Spring có luôn rollback không?
- Tại sao `@Transactional` trên một phương thức được gọi qua `this.method()` có thể không hoạt động?
- Một inner transaction `REQUIRES_NEW` đã commit có bị outer rollback hủy không?
- Vì sao test rollback cần chạy qua Spring proxy với dữ liệu độc lập thay vì chỉ mock `JdbcTemplate`?

**Ghi nhớ:** Trong Spring JDBC, khi framework sở hữu transaction, **đừng tự `commit()`, `rollback()`, thay `autoCommit` hay `close()` connection trong DAO**. Hãy đặt ranh giới transaction ở service bằng `@Transactional` hoặc `TransactionTemplate`, truy cập dữ liệu bằng `JdbcTemplate` hoặc cặp `DataSourceUtils.getConnection/releaseConnection`, và chỉ tự đóng `PreparedStatement`/`ResultSet` do code tạo. Kiểm tra cấu hình chung của transaction manager/`DataSource`, quy tắc rollback, proxy và propagation bằng **integration test thật**, để những lệnh SQL dự kiến nguyên tử thực sự cùng commit hoặc cùng rollback.
