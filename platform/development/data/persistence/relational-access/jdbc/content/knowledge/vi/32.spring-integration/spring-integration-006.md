# Vai trò của `DataSourceUtils` khi cần truy cập JDBC mức thấp trong Spring

Khi dùng JDBC trong một ứng dụng Spring, nhiều đội phát triển bắt đầu với `JdbcTemplate` vì nó xử lý phần lớn công việc lặp lại: lấy kết nối, tạo statement, đóng tài nguyên và chuyển đổi `SQLException`. Tuy nhiên, có những tình huống cần truy cập API JDBC trực tiếp: sử dụng `CallableStatement` đặc thù driver, thao tác với `ResultSet` nâng cao, điều khiển batch phức tạp hoặc tích hợp một thư viện vốn nhận `java.sql.Connection`.

Trong trường hợp đó, câu hỏi không chỉ là **lấy được `Connection` từ đâu**, mà còn là **làm thế nào để cùng tham gia transaction do Spring quản lý**. Nếu một service đã chạy bên trong `@Transactional` nhưng DAO lại tự gọi `dataSource.getConnection()` từ một pool thông thường, DAO có thể nhận một kết nối khác, thực thi SQL ngoài transaction dự kiến và commit riêng. Kết quả là một thao tác nghiệp vụ nhiều bước tưởng như nguyên tử nhưng thực tế không thể rollback cùng nhau.

**`org.springframework.jdbc.datasource.DataSourceUtils`** giải quyết phần quan trọng của vấn đề: lấy và trả một `Connection` theo cơ chế quản lý tài nguyên/giao dịch của Spring. Công cụ này không thay thế `JdbcTemplate`, không tự mở transaction và không tự quyết định commit hay rollback; nó là **cầu nối giữa mã JDBC mức thấp với transaction-bound connection**.

Bài học thuộc chương **Tích hợp Spring** của module JDBC. Ta sẽ nắm rõ `DataSourceUtils.getConnection()`, `releaseConnection()`, `isConnectionTransactional()` và `applyTransactionTimeout()`; triển khai DAO với `DataSource`, `PreparedStatement`, `ResultSet` và `@Transactional`; nhận diện lỗi thường gặp và kiểm thử transaction trên driver/database thật.

## 1. Vấn đề: cùng `DataSource` chưa chắc cùng transaction

Một transaction JDBC cục bộ gắn với **một `Connection`**. Hai câu SQL thực thi trên hai connection vật lý khác nhau không tự động thuộc cùng transaction chỉ vì cả hai đều lấy từ cùng connection pool.

Ví dụ nghiệp vụ chuyển tiền:

1. Trừ tiền tài khoản nguồn.
2. Cộng tiền tài khoản đích.
3. Chỉ xác nhận khi cả hai bước thành công.

Nếu Spring đã mở transaction cho service nhưng mỗi DAO tự mượn một connection từ pool, có thể xảy ra:

```text
TransferService.transfer()  [@Transactional]
        |
        | Spring transaction manager
        +-----------------------------> Connection A
        |                               transaction A
        |
        +--> AccountDao.debit()
        |       dataSource.getConnection()
        |                |
        |                +-------------> Connection B
        |                                autoCommit=true (có thể)
        |                                UPDATE nguồn -> commit riêng
        |
        +--> AccountDao.credit()
                dataSource.getConnection()
                         |
                         +-------------> Connection C
                                         UPDATE đích -> LỖI

Spring rollback transaction A
    nhưng thay đổi đã commit trên B không được hoàn tác.
```

Đây là tình huống **có thể xảy ra khi `dataSource` là pool/driver `DataSource` thông thường không có lớp proxy transaction-aware**. Với một `TransactionAwareDataSourceProxy`, hành vi `getConnection()/close()` có thể đã được điều chỉnh để tham gia Spring transaction; không nên áp dụng kết luận “mọi `DataSource.getConnection()` đều luôn sai” một cách tuyệt đối.

Điểm cần ghi nhớ: khi tự viết code JDBC trong hệ thống có transaction Spring, phải biết **ai sở hữu connection, transaction và thao tác đóng/trả connection**.

## 2. Spring liên kết connection với transaction như thế nào?

Khi ứng dụng cấu hình một JDBC transaction manager như `DataSourceTransactionManager` hoặc `JdbcTransactionManager` và một phương thức phù hợp được gọi qua cơ chế Spring `@Transactional`, transaction manager có thể:

1. Lấy `Connection` từ `DataSource` được cấu hình.
2. Thiết lập các thuộc tính transaction cần thiết, như `autoCommit=false`.
3. Liên kết tài nguyên JDBC tương ứng với **thread đang chạy** qua cơ chế `TransactionSynchronizationManager`.
4. Cho mã JDBC trong cùng transaction lấy lại connection liên kết ấy.
5. Khi phương thức transaction kết thúc, commit/rollback theo chính sách, khôi phục trạng thái cần thiết và trả connection về pool.

```text
Thread xử lý request
    |
    +-- @Transactional service
    |       |
    |       +-- Spring transaction manager
    |       |       |
    |       |       +-- lấy Connection X
    |       |       +-- bind ConnectionHolder theo DataSource
    |       |
    |       +-- DAO A: DataSourceUtils.getConnection(ds)
    |       |              |
    |       |              +--> Connection X
    |       |
    |       +-- DAO B: DataSourceUtils.getConnection(ds)
    |                      |
    |                      +--> Connection X
    |
    +-- Spring commit/rollback
    +-- unbind và dọn transaction-bound resource
```

Điều kiện của sơ đồ là **DAO sử dụng đúng `DataSource` gắn với transaction manager**, mã chạy trong ngữ cảnh transaction/synchronization tương ứng và transaction Spring thực sự đã được kích hoạt.

Spring quản lý tài nguyên transaction theo **ngữ cảnh thread truyền thống** của JDBC transaction manager. Không mặc định ngữ cảnh đó tự lan sang `new Thread(...)`, `CompletableFuture`, `@Async` hoặc executor khác. Nếu tách tác vụ sang thread khác, cần thiết kế transaction riêng và không chia sẻ `Connection` đang mở như một object dùng chung giữa các thread.

### `@Transactional` không phải một câu SQL

`@Transactional` chỉ là metadata. Nó có tác dụng khi Spring transaction interceptor thực sự bao quanh lời gọi và có transaction manager phù hợp. Tự tạo service bằng `new`, gọi phương thức nội bộ trên `this` trong kiểu proxy mặc định, hoặc dùng sai transaction manager đều có thể làm transaction không được kích hoạt như dự kiến.

Do đó, **`DataSourceUtils` không thể tự cứu một phương thức mà Spring chưa hề mở transaction**. Nó chỉ tương tác với trạng thái Spring transaction/synchronization đã tồn tại.

## 3. `DataSourceUtils` cung cấp những gì?

Các API cốt lõi từ Spring JDBC:

| API | Vai trò | Điều cần chú ý |
|---|---|---|
| `DataSourceUtils.getConnection(dataSource)` | Lấy `Connection` và tham gia cơ chế đồng bộ tài nguyên Spring nếu có | Có thể trả transaction-bound connection; lỗi lấy connection thường được bọc thành runtime exception của Spring |
| `DataSourceUtils.doGetConnection(dataSource)` | Phiên bản mức thấp hơn thực hiện việc lấy connection | Có thể ném `SQLException` trực tiếp |
| `DataSourceUtils.releaseConnection(connection, dataSource)` | Trả connection an toàn theo ngữ cảnh Spring | **Không đóng** connection đang được Spring giữ cho transaction; ngoài ngữ cảnh sẽ đóng/trả pool theo cơ chế `DataSource` |
| `DataSourceUtils.isConnectionTransactional(connection, dataSource)` | Kiểm tra connection có đang được liên kết với tài nguyên transaction của `DataSource` không | Dùng cho chẩn đoán/quyết định kỹ thuật, không thay việc kiểm chứng rollback |
| `DataSourceUtils.applyTransactionTimeout(statement, dataSource)` | Áp dụng timeout còn lại của transaction Spring lên JDBC `Statement` | Không tự tạo deadline; hiệu quả cuối phụ thuộc driver/DBMS |
| `DataSourceUtils.applyTimeout(statement, dataSource, timeoutSeconds)` | Xử lý query timeout và timeout transaction theo quy tắc Spring | Cần xem chính sách timeout của tầng gọi; không phải hard deadline cho mọi driver |

`DataSourceUtils` là lớp tiện ích **của Spring Framework**, không phải thành phần của JDBC chuẩn trong JDK. Trong code ứng dụng Spring, import:

```java
import org.springframework.jdbc.datasource.DataSourceUtils;
```

Các API JDBC mà nó hỗ trợ vẫn là chuẩn: `javax.sql.DataSource`, `java.sql.Connection`, `PreparedStatement`, `ResultSet`, `SQLException`.

### So sánh ngắn

| Cách lấy kết nối | Khi nào phù hợp? | Transaction Spring |
|---|---|---|
| `dataSource.getConnection()` từ pool thông thường | Code JDBC tự quản lý transaction hoặc ứng dụng không dùng Spring transaction | Không tự bảo đảm tham gia connection đang bound |
| `DataSourceUtils.getConnection(dataSource)` | Code JDBC mức thấp **có nhận biết Spring** | Có thể lấy đúng connection đã liên kết với transaction |
| `JdbcTemplate` | CRUD và truy vấn SQL thông thường | Đã tích hợp cơ chế lấy/trả connection theo Spring |
| `TransactionAwareDataSourceProxy.getConnection()` | Tích hợp mã legacy chỉ biết `DataSource.getConnection()/close()` | Proxy điều chỉnh hành vi cho mã không trực tiếp dùng `DataSourceUtils` |
| `DataSourceTransactionManager` / `JdbcTransactionManager` | Quản lý biên transaction JDBC | Quyết định commit, rollback và quản lý tài nguyên |

**Không dùng `DataSourceUtils` để tự thay thế một transaction manager.** Cũng không cần viết lại `JdbcTemplate` chỉ để có thể gọi `DataSourceUtils`: lựa chọn tốt nhất cho SQL đơn giản thường vẫn là `JdbcTemplate`.

## 4. Quy tắc lấy và trả `Connection` an toàn

Mẫu chuẩn trong một helper JDBC mức thấp:

```java
Connection connection =
        DataSourceUtils.getConnection(dataSource);

try {
    // Dùng connection để tạo PreparedStatement/ResultSet
    // và thực hiện SQL ở đây.
} finally {
    DataSourceUtils.releaseConnection(connection, dataSource);
}
```

Hai hàm dùng **cùng đối tượng `DataSource` về mặt cấu hình tài nguyên**. Đặc biệt trong Spring, không tự tạo một `DataSource` mới cùng JDBC URL rồi giả định đó là cùng khóa transaction đã bound.

Điều xảy ra khi gọi `releaseConnection(...)` phụ thuộc ngữ cảnh:

- **Trong transaction do Spring quản lý** và đúng `DataSource`: connection vẫn phải còn sống cho các DAO tiếp theo cũng như bước commit/rollback của transaction manager. Helper không nên đóng vật lý connection.
- **Ngoài transaction/synchronization thích hợp**: helper cần giải phóng connection. Với connection pool, đóng logical handle thường có nghĩa **trả về pool**, không nhất thiết ngắt kết nối vật lý.
- **Khi lỗi**: `finally` phải chạy để không giữ connection vô thời hạn. Tính đúng đắn của transaction vẫn do transaction manager hoặc tầng sở hữu transaction quyết định.

### Đừng dùng `try-with-resources` cho connection do `DataSourceUtils` lấy

Mẫu **cần tránh** trong code JDBC mức thấp có Spring-managed transaction:

```java
// Dễ đóng nhầm Connection mà transaction manager vẫn sở hữu.
try (Connection c = DataSourceUtils.getConnection(dataSource)) {
    // Thực thi các câu SQL...
}
```

Lý do: `try-with-resources` gọi trực tiếp `c.close()`, bỏ qua bước giải phóng có nhận biết transaction của `DataSourceUtils`. Đối với một connection bound thật, thao tác đóng nhầm có thể khiến các DAO sau hoặc transaction manager không thể dùng tiếp connection.

Thay bằng:

```java
Connection c = DataSourceUtils.getConnection(dataSource);
try {
    try (PreparedStatement ps = c.prepareStatement(
            "SELECT id FROM accounts WHERE id = ?")) {

        ps.setLong(1, 100L);
        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                System.out.println(rs.getLong("id"));
            }
        }
    }
} finally {
    DataSourceUtils.releaseConnection(c, dataSource);
}
```

**Nên dùng `try-with-resources` cho `PreparedStatement` và `ResultSet`**, vì DAO sở hữu chúng. Với `Connection` do transaction Spring sở hữu, DAO chỉ **mượn và release theo Spring**, không tự quyết định kết thúc transaction.

Nếu application không dùng Spring transaction, có thể dùng cách JDBC thuần `try (Connection c = ds.getConnection())`. Vấn đề không nằm ở việc `Connection.close()` luôn sai, mà ở **quyền sở hữu tài nguyên trong ngữ cảnh cụ thể**.

## 5. Ví dụ dữ liệu: giao dịch chuyển tiền giữa hai tài khoản

Để minh họa tại sao chia sẻ đúng `Connection` là quan trọng, dùng bảng:

```sql
CREATE TABLE accounts (
    id      BIGINT PRIMARY KEY,
    balance DECIMAL(18, 2) NOT NULL CHECK (balance >= 0)
);

INSERT INTO accounts (id, balance)
VALUES (1, 500000.00),
       (2, 200000.00);
```

Yêu cầu nghiệp vụ:

1. Số tiền chuyển phải dương.
2. Tài khoản nguồn và đích phải khác nhau.
3. Trừ tiền nguồn **chỉ khi số dư đủ**.
4. Cộng tiền đích **chỉ khi tài khoản tồn tại**.
5. Hai cập nhật phải thuộc **một transaction**: thành công cả hai hoặc rollback cả hai.

Thay vì mỗi DAO tự gọi `commit()`, ta đặt ranh giới transaction ở tầng service và giao cho một lớp gateway JDBC mức thấp thực thi câu lệnh SQL. Đây là cách phối hợp `DataSourceUtils` với `@Transactional`.

## 6. Định nghĩa gateway JDBC dùng `DataSourceUtils`

Gateway thực hiện hai câu lệnh `UPDATE`, không tự commit/rollback. Nó nhận `DataSource` do Spring inject và lấy connection có nhận biết transaction theo `DataSourceUtils`.

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.Objects;

import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.stereotype.Repository;

@Repository
public final class AccountJdbcGateway {
    private final DataSource dataSource;

    public AccountJdbcGateway(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(
                dataSource, "dataSource");
    }

    public int debit(long accountId, BigDecimal amount)
            throws SQLException {

        String sql = "UPDATE accounts "
                + "SET balance = balance - ? "
                + "WHERE id = ? AND balance >= ?";

        return executeUpdate(sql, ps -> {
            ps.setBigDecimal(1, amount);
            ps.setLong(2, accountId);
            ps.setBigDecimal(3, amount);
        });
    }

    public int credit(long accountId, BigDecimal amount)
            throws SQLException {

        String sql = "UPDATE accounts "
                + "SET balance = balance + ? "
                + "WHERE id = ?";

        return executeUpdate(sql, ps -> {
            ps.setBigDecimal(1, amount);
            ps.setLong(2, accountId);
        });
    }

    private int executeUpdate(String sql, Binder binder)
            throws SQLException {

        Connection connection =
                DataSourceUtils.getConnection(dataSource);

        try {
            try (PreparedStatement ps =
                         connection.prepareStatement(sql)) {

                binder.bind(ps);

                // Nếu Spring transaction có deadline,
                // áp dụng timeout còn lại khi driver hỗ trợ.
                DataSourceUtils.applyTransactionTimeout(
                        ps, dataSource);

                return ps.executeUpdate();
            }
        } finally {
            // Không close trực tiếp transaction-bound Connection.
            DataSourceUtils.releaseConnection(
                    connection, dataSource);
        }
    }

    @FunctionalInterface
    private interface Binder {
        void bind(PreparedStatement ps) throws SQLException;
    }
}
```

Những điểm quan trọng:

- Mỗi lời gọi gateway **lấy `Connection` qua `DataSourceUtils`**, nên trong cùng Spring transaction có thể nhận lại đúng connection đang bound.
- `PreparedStatement` dùng `?` và các phương thức `setXxx(...)` thay vì nối số tiền hoặc ID vào SQL.
- Điều kiện `balance >= ?` giúp lệnh trừ tiền bảo vệ số dư tại thời điểm cập nhật; cần kiểm tra số hàng bị ảnh hưởng.
- `releaseConnection(...)` chạy cả khi `prepareStatement`, bind tham số hoặc `executeUpdate()` ném lỗi.
- Gateway **không gọi `setAutoCommit(false)`, `commit()` hoặc `rollback()`**, vì biên transaction thuộc Spring service.
- `applyTransactionTimeout(...)` dùng deadline của Spring transaction nếu có; không tự biến một lệnh SQL thành transaction hoặc bảo đảm cứng về thời gian mạng.

`DataSourceUtils.getConnection(...)` là phương thức tiện dụng có thể chuyển lỗi lấy kết nối thành một runtime exception của Spring (chẳng hạn `CannotGetJdbcConnectionException`). Những câu `prepareStatement`/`executeUpdate` vẫn có thể ném `SQLException`, được gateway khai báo `throws SQLException`. Phần xử lý rollback cho loại lỗi này nằm ở service.

### Vì sao không giữ `Connection` trong field?

Không viết:

```java
@Repository
public class UnsafeGateway {
    private Connection connection; // Sai khi bean dùng chung nhiều request.
}
```

Một Spring `@Repository` thường là singleton bean. Nếu lưu connection đang mượn thành field, nhiều request hoặc thread có thể sử dụng lẫn nhau và vi phạm ranh giới transaction. Chỉ lưu **`DataSource`**, còn `Connection` phải là biến cục bộ trong phạm vi công việc.

## 7. Service quản lý transaction và xử lý checked `SQLException`

Spring theo mặc định rollback khi một `RuntimeException` hoặc `Error` thoát khỏi phương thức transactional; **checked exception như `SQLException` không luôn kích hoạt rollback theo mặc định**. Vì vậy, nếu DAO/gateway khai báo `throws SQLException`, cần chọn chính sách rõ ràng.

Ví dụ dưới đây dùng `rollbackFor = SQLException.class`:

```java
import java.math.BigDecimal;
import java.sql.SQLException;
import java.util.Objects;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class TransferService {
    private final AccountJdbcGateway accounts;

    public TransferService(AccountJdbcGateway accounts) {
        this.accounts = Objects.requireNonNull(accounts, "accounts");
    }

    @Transactional(
            rollbackFor = SQLException.class,
            timeout = 10)
    public void transfer(
            long fromAccountId,
            long toAccountId,
            BigDecimal amount) throws SQLException {

        if (fromAccountId == toAccountId) {
            throw new IllegalArgumentException(
                    "Tài khoản nguồn và đích phải khác nhau");
        }
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException(
                    "Số tiền chuyển phải dương");
        }

        int debited = accounts.debit(fromAccountId, amount);
        if (debited != 1) {
            throw new SQLException(
                    "Tài khoản nguồn không tồn tại hoặc không đủ tiền");
        }

        int credited = accounts.credit(toAccountId, amount);
        if (credited != 1) {
            throw new SQLException(
                    "Tài khoản đích không tồn tại");
        }

        // Không gọi commit() ở đây.
        // Spring transaction interceptor sẽ commit nếu hoàn tất;
        // sẽ rollback nếu SQLException thoát ra và rollbackFor khớp.
    }
}
```

Kết quả dự kiến với dữ liệu mẫu:

```java
transferService.transfer(
        1L, 2L, new BigDecimal("100000.00"));
```

Sau khi commit thành công, tài khoản 1 còn `400000.00` và tài khoản 2 có `300000.00`.

Nếu tài khoản đích không tồn tại:

1. Gateway debit có thể cập nhật tạm thời số dư tài khoản nguồn trong transaction.
2. Gateway credit trả số hàng thay đổi bằng `0`.
3. Service ném `SQLException`.
4. Spring nhận ngoại lệ và rollback transaction theo `rollbackFor`.
5. Cập nhật tạm thời ở tài khoản nguồn cũng bị hủy.

**Điều kiện cốt lõi:** phương thức `transfer(...)` phải được gọi **thông qua bean được Spring quản lý**, transaction manager JDBC phải sử dụng đúng `DataSource` với gateway và các bảng phải dùng database/storage engine hỗ trợ transaction.

### Một điểm tinh tế: lỗi checked và rollback

Nếu bỏ `rollbackFor = SQLException.class`:

```java
@Transactional
public void transfer(...) throws SQLException {
    // Gateway có thể ném checked SQLException.
}
```

thì trong cấu hình rollback mặc định của Spring, checked `SQLException` có thể khiến transaction **được commit dù phương thức thoát bằng ngoại lệ**. Đó là lỗi đặc biệt nghiêm trọng khi lệnh trừ tiền đã chạy nhưng lệnh cộng tiền thất bại.

Các phương án hợp lệ:

- Khai báo `@Transactional(rollbackFor = SQLException.class)` trên biên nghiệp vụ.
- Dùng một `DataAccessException` unchecked thích hợp, được tạo bằng cơ chế dịch ngoại lệ của Spring; lúc đó rollback mặc định áp dụng nếu ngoại lệ thoát ra.
- Cấu hình chính sách rollback chung của hệ thống nếu dự án đã chủ động lựa chọn và kiểm thử.

Không đơn thuần `catch(SQLException)` rồi trả `false`/`Optional.empty()` bên trong method transactional nếu điều đó làm Spring tưởng công việc đã hoàn tất thành công.

### Chú ý khác biệt giữa kiểm soát JDBC và thông điệp nghiệp vụ

Ví dụ ném `SQLException` khi tài khoản không tồn tại để minh họa tác động tới `rollbackFor`. Trong dự án lớn, trường hợp “không đủ số dư” có thể được biểu diễn bằng một **domain exception unchecked** hoặc một kết quả nghiệp vụ rõ ràng; còn `SQLException` nên chủ yếu dành cho lỗi cơ sở dữ liệu. Khi chọn domain exception, vẫn cần bảo đảm quy tắc rollback cho mọi nhánh đã ghi dữ liệu trước đó.

Ngoài ra, nếu `commit` thất bại do mất kết nối, kết quả có thể chưa rõ. Không retry mù một lệnh chuyển tiền: cần mã giao dịch/idempotency và đối soát kết quả trong ứng dụng thực tế.

## 8. Cấu hình transaction manager khớp với `DataSource`

Để `@Transactional` có hiệu lực, Spring phải có một transaction manager phù hợp.

Trong ứng dụng chỉ sử dụng JDBC, có thể cấu hình:

```java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;

@Configuration
@EnableTransactionManagement
public class JdbcTransactionConfiguration {

    @Bean
    public PlatformTransactionManager transactionManager(
            DataSource dataSource) {

        return new DataSourceTransactionManager(dataSource);
    }
}
```

Ví dụ giả định ứng dụng đã khai báo một `DataSource` bean phù hợp và dependency Spring JDBC/Transaction có trong classpath. Một số cấu hình Spring Boot có thể **tự tạo transaction manager**, vì vậy không nên thêm bean trùng một cách vô điều kiện vào dự án thật. Với nhiều `DataSource`/transaction manager, phải chỉ rõ manager tương ứng qua cấu hình hoặc `@Transactional(transactionManager = "...")`.

`JdbcTransactionManager` là biến thể dành cho JDBC với khả năng chuyển đổi các ngoại lệ khi commit/rollback theo hướng Spring JDBC; có thể dùng khi phù hợp phiên bản Spring và chiến lược exception của dự án. Cả hai đều cần đi cùng `DataSource` được quản lý đúng.

**Không mặc định rằng chỉ cần nhìn thấy `@Transactional` là transaction đã được bắt đầu.** Nếu ứng dụng có một manager khác (chẳng hạn JPA transaction manager hoặc một manager cho nguồn dữ liệu khác), khả năng phối hợp với JDBC phải được xác minh theo cấu hình thực tế. Đặc biệt, nếu DAO dùng `DataSource` bean khác với bean manager đang quản lý, `DataSourceUtils` có thể lấy connection độc lập.

### Quy tắc về `DataSource` và proxy

Khi dùng `TransactionAwareDataSourceProxy`, cần phân biệt **`DataSource` target của transaction manager** với **`DataSource` proxy cung cấp cho mã legacy**. Không tạo nhiều wrapper/bean khác nhau rồi giả định việc bind transaction tự nối chúng lại chỉ vì cùng trỏ tới một JDBC URL.

Một cách phổ biến là transaction manager quản lý một `DataSource` mục tiêu, còn mã Spring-aware gọi `DataSourceUtils` trên cùng tài nguyên logic đó. Nếu dùng `LazyConnectionDataSourceProxy` hoặc proxy khác, hãy làm theo hướng dẫn cấu hình của Spring và kiểm thử một transaction thật; không dùng tên bean hoặc URL như bằng chứng đủ về sự tương đương của resource key.

## 9. `JdbcTemplate` và `DataSourceUtils`: nên chọn gì?

`JdbcTemplate` được xây dựng để thực hiện những thao tác JDBC lặp lại một cách an toàn. Nó đã tích hợp với transaction resource synchronization của Spring, đóng statement/result set và chuyển `SQLException` thành một hệ thống `DataAccessException` unchecked.

Ví dụ đọc số dư bằng `JdbcTemplate`:

```java
import java.math.BigDecimal;
import org.springframework.jdbc.core.JdbcTemplate;

public BigDecimal findBalance(
        JdbcTemplate jdbc, long accountId) {

    String sql = "SELECT balance FROM accounts WHERE id = ?";
    return jdbc.queryForObject(
            sql, BigDecimal.class, accountId);
}
```

Ví dụ này giả định đã có `JdbcTemplate jdbc` từ Spring và thực sự có một hàng tương ứng. `queryForObject` có các quy tắc ngoại lệ riêng khi 0 hoặc nhiều hàng; không tự đồng nghĩa với `Optional.empty()`.

Khi truy vấn phức tạp hơn nhưng vẫn thuộc mẫu chung, `JdbcTemplate.query(...)` với `RowMapper` hoặc `ResultSetExtractor` thường là lựa chọn phù hợp:

```java
List<Long> accountIds = jdbc.query(
        "SELECT id FROM accounts WHERE balance >= ? ORDER BY id",
        (rs, rowNum) -> rs.getLong("id"),
        new BigDecimal("100000.00"));
```

Vậy **khi nào cần `DataSourceUtils` trực tiếp?**

- Tích hợp API driver/vendor yêu cầu làm việc trực tiếp với `Connection`.
- Sử dụng `CallableStatement` hoặc cursor đặc thù không phù hợp với abstraction có sẵn.
- Có helper JDBC mức thấp dùng trong thư viện nội bộ hoặc framework adapter.
- Kiểm soát một luồng `PreparedStatement`/`ResultSet` đặc biệt nhưng vẫn cần tham gia `@Transactional`.
- Cần áp dụng timeout transaction cho statement tự tạo.

Dù vậy, `JdbcTemplate` cũng hỗ trợ các callback như `ConnectionCallback`, `PreparedStatementCallback` và `CallableStatementCallback` cho một số nhu cầu thấp hơn. **Hãy thử callback trước khi viết một lớp tự quản lý connection** nếu nó đáp ứng được yêu cầu.

### Bảng lựa chọn

| Nhu cầu | Cách đề xuất |
|---|---|
| CRUD đơn giản bằng `SELECT/INSERT/UPDATE/DELETE` | `JdbcTemplate` hoặc `NamedParameterJdbcTemplate` |
| Mapping nhiều hàng có SQL tham số hóa | `JdbcTemplate.query(...)` + `RowMapper` |
| Một callback cần chạm tới API JDBC thấp hơn | `JdbcTemplate.execute(...)` / callback phù hợp |
| Adapter riêng tự tạo `PreparedStatement` và cần transaction Spring | `DataSourceUtils.getConnection/releaseConnection` |
| Thư viện legacy chỉ biết `DataSource.getConnection/close` | Cân nhắc `TransactionAwareDataSourceProxy`, có kiểm chứng |
| Mã độc lập không có Spring transaction | JDBC thuần + `try-with-resources` trên `Connection` |

Không cần trộn đồng thời `JdbcTemplate` và `DataSourceUtils` trong một thao tác chỉ để “chắc chắn có transaction”: `JdbcTemplate` đã xử lý cơ chế resource management của Spring.

## 10. `TransactionAwareDataSourceProxy` khác gì?

`TransactionAwareDataSourceProxy` là một wrapper `DataSource` phục vụ **mã JDBC vốn không biết Spring** và chỉ gọi:

```java
Connection c = dataSource.getConnection();
try {
    // SQL
} finally {
    c.close();
}
```

Khi dùng đúng proxy, thao tác lấy/đóng connection được điều chỉnh để phù hợp với resource/transaction Spring. Nhờ vậy, code legacy có thể tham gia Spring-managed transaction mà không cần gọi trực tiếp `DataSourceUtils`.

Tuy nhiên:

- Proxy chỉ có tác dụng khi mã thật sự nhận **đúng proxy đó**.
- Cấu hình transaction manager, target `DataSource` và thứ tự proxy cần theo hợp đồng Spring.
- Proxy không làm `@Transactional` tự hoạt động nếu Spring interceptor không bao quanh lời gọi.
- Không nên trộn handle từ một `DataSource` với `releaseConnection(..., otherDataSource)` theo cảm tính.
- Khi đã viết code **có nhận biết Spring**, `DataSourceUtils` hoặc `JdbcTemplate` thường trực quan hơn.

**Không dùng proxy và utility như hai biện pháp sửa lỗi chồng chéo mà không có thiết kế rõ.** Hãy xác định duy nhất đường lấy connection và trách nhiệm đóng/trả.

## 11. Transaction synchronization và transaction thực không hoàn toàn đồng nghĩa

`DataSourceUtils.getConnection(...)` có thể tham gia cơ chế **transaction synchronization** khi Spring đã bật đồng bộ tài nguyên trên thread. Cơ chế này có thể được dùng trong một vài ngữ cảnh không giống với “đang có một JDBC transaction thực sự đã bắt đầu”.

Điều cần phân biệt:

- **Connection được bind:** Spring đang quản lý vòng đời tài nguyên liên kết với `DataSource`.
- **Transaction thực đang hoạt động:** Spring đang thực hiện transaction với ngữ nghĩa phù hợp cho thao tác dữ liệu.
- **Transaction DB có hiệu lực:** các thay đổi SQL thực sự nằm trong cùng transaction của connection mà manager kiểm soát.

Có thể xem trạng thái để **chẩn đoán**:

```java
import java.sql.Connection;

import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.transaction.support.TransactionSynchronizationManager;

Connection connection =
        DataSourceUtils.getConnection(dataSource);

try {
    System.out.println("Spring actual transaction active: "
            + TransactionSynchronizationManager
                    .isActualTransactionActive());

    System.out.println("Spring synchronization active: "
            + TransactionSynchronizationManager
                    .isSynchronizationActive());

    System.out.println("Connection is transaction-bound: "
            + DataSourceUtils.isConnectionTransactional(
                    connection, dataSource));
} finally {
    DataSourceUtils.releaseConnection(connection, dataSource);
}
```

Đoạn này là ví dụ trong phương thức đã có `DataSource dataSource` và các dependency Spring cần thiết. Ba giá trị dùng cho quan sát, **không thay thế kiểm thử rollback trên database thật** và không nên dùng như một cơ chế xác thực nghiệp vụ.

Một connection được Spring đồng bộ tài nguyên **không có nghĩa** phương thức bất kỳ đang được yêu cầu commit một cách chính xác theo mong muốn. Phải kiểm thử đường chạy transaction manager thực tế.

## 12. Timeout: áp dụng deadline transaction cho `Statement` thủ công

Một lợi ích của `DataSourceUtils` trong code mức thấp là giúp statement tự tạo tôn trọng timeout Spring transaction. Ví dụ:

```java
@Transactional(
        timeout = 5,
        rollbackFor = SQLException.class)
public void runImportantOperation() throws SQLException {
    // Gateway tự tạo PreparedStatement như phần trước,
    // gọi DataSourceUtils.applyTransactionTimeout(ps, dataSource).
}
```

Cách hoạt động về mặt logic:

1. Transaction manager bắt đầu transaction với timeout/deadline theo chính sách.
2. Gateway lấy connection bound qua `DataSourceUtils`.
3. Trước khi `executeQuery()`/`executeUpdate()`, gateway gọi `applyTransactionTimeout(...)`.
4. Spring tính thời gian còn lại của transaction đã đăng ký và chuyển thành giá trị query timeout cho JDBC statement theo khả năng driver.
5. Driver/DBMS xử lý timeout theo cơ chế hỗ trợ.

**Không hiểu `setQueryTimeout(...)` hay `applyTransactionTimeout(...)` là “ngắt cứng mọi truy vấn đúng sau 5 giây”.** Timeout thực tế có thể phụ thuộc driver, độ trễ mạng, DBMS và trạng thái protocol. Sau timeout, transaction có thể cần rollback và đôi khi connection không còn đáng tin cậy.

Khi dùng `JdbcTemplate`, Spring đã có cơ chế áp dụng transaction timeout cho statement phù hợp, nên không nhất thiết phải gọi utility này thủ công.

### Timeout tầng khác không thể thay thế nhau

| Loại timeout | Phạm vi |
|---|---|
| Timeout chờ mượn connection từ pool | Thời gian chờ tài nguyên pool |
| Transaction timeout của `@Transactional` | Giới hạn thời gian mà Spring transaction manager áp dụng theo cơ chế của nó |
| `Statement.setQueryTimeout(seconds)` | Timeout thực thi query theo khả năng JDBC driver |
| `Connection.setNetworkTimeout(...)` | Timeout thao tác mạng trên connection theo driver |
| DB statement/lock timeout | Cơ chế chờ query/lock phía DBMS |
| HTTP request deadline | Hạn thời gian phản hồi của request bên ngoài |

Đừng cố sửa một query bị khóa bằng cách chỉ thay fetch size, hoặc xem timeout HTTP nghĩa là transaction đã tự rollback trong DB.

## 13. Spring transaction không tự lan qua thread khác

Với transaction manager JDBC cục bộ, association giữa resource và thread là điểm rất quan trọng.

Ví dụ nguy hiểm:

```java
@Transactional
public void process() {
    CompletableFuture.runAsync(() -> {
        // Không mặc định chạy cùng Spring transaction của process().
        accountGateway.credit(2L, new BigDecimal("100.00"));
    });
}
```

Tác vụ async có thể mượn connection khác và tự commit trước khi transaction bên ngoài kết thúc. Nếu service bên ngoài rollback, side effect trong thread khác **không tự động rollback theo**.

Hướng thiết kế:

- Khi các thao tác cần nguyên tử, giữ chúng trong **cùng luồng transaction và cùng connection**.
- Nếu cần xử lý bất đồng bộ, dùng một transaction độc lập cho tác vụ async, sự kiện/outbox hoặc workflow có idempotency/bù trừ.
- Không chuyền một `Connection` đang mượn qua thread chỉ để “giữ cùng transaction”; JDBC object không được mặc định thread-safe.
- Nếu dùng mô hình reactive (R2DBC), cần cơ chế transaction theo reactive context; `DataSourceUtils` của JDBC không trở thành transaction manager reactive.

Tương tự, trong proxy mode mặc định, gọi `this.transfer(...)` từ method khác của cùng bean có thể bỏ qua transaction interceptor. Hãy kiểm tra cấu trúc lời gọi và cơ chế Spring đang cấu hình thay vì chỉ dựa vào sự tồn tại của annotation.

## 14. Những lỗi cần tránh khi dùng `DataSourceUtils`

| Sai lầm | Vì sao nguy hiểm? | Thay bằng |
|---|---|---|
| Gọi `dataSource.getConnection()` từ pool thường trong `@Transactional` | Có thể mở connection độc lập, commit riêng | Dùng `DataSourceUtils` hoặc `JdbcTemplate` |
| Gọi `close()` trực tiếp lên connection lấy từ `DataSourceUtils` | Bỏ qua cơ chế release có nhận biết transaction | `DataSourceUtils.releaseConnection(...)` trong `finally` |
| Dùng try-with-resources cho connection transaction-bound | Có thể đóng handle Spring vẫn cần | Chỉ try-with-resources cho statement/result set |
| DAO gọi `commit()` ngay sau mỗi `executeUpdate()` | Phá vỡ biên transaction của service | Để transaction manager quyết định |
| DAO tự gọi `setAutoCommit(false)` bên trong transaction Spring | Có thể làm thay đổi trạng thái đang được quản lý | Để transaction manager thiết lập |
| Catch `SQLException` rồi trả rỗng | Có thể khiến Spring commit phần trước đó | Propagate/translate exception và rollback theo chính sách |
| Quên `rollbackFor` cho checked `SQLException` | Spring mặc định có thể commit dù phương thức lỗi | `rollbackFor=SQLException.class` hoặc runtime `DataAccessException` |
| Lấy connection từ một `DataSource`, release bằng cái khác | Spring không đối chiếu được tài nguyên đúng | Dùng cùng `DataSource` được cấu hình |
| Dùng transaction manager của database khác | DAO không ở cùng transaction | Chọn đúng manager với `DataSource` và kiểm thử |
| Giữ `Connection` trong field singleton | Trộn state giữa request/thread | Biến cục bộ và release sau mỗi scope |
| Nghĩ `DataSourceUtils` tự khởi tạo transaction | Không có biên commit/rollback tự động | `@Transactional` hoặc `TransactionTemplate` |
| Nghĩ mọi thread async tham gia transaction thread gốc | Thread khác không có bound resource tương ứng | Thiết kế transaction độc lập/đồng bộ |
| Dùng `isConnectionTransactional` thay kiểm thử dữ liệu | Chỉ kiểm tra liên kết tài nguyên, không chứng minh atomicity | Test commit/rollback thật với DBMS |
| Không dùng `applyTransactionTimeout` trong code tự tạo statement khi cần deadline Spring | Query có thể không nhận timeout transaction mong đợi | Áp dụng utility và kiểm chứng driver |
| Dùng `DataSourceUtils` cho mọi CRUD đơn giản | Tăng boilerplate, phải xử lý exception/resource | Ưu tiên `JdbcTemplate` |

### Khi release hoặc rollback cũng thất bại

`DataSourceUtils.releaseConnection(...)` là utility giải phóng connection theo ngữ cảnh Spring, **không phải quy trình cứu một transaction có trạng thái không rõ**. Nếu driver báo mất kết nối hay rollback/commit thất bại, ứng dụng phải theo chính sách của transaction manager/pool: đánh dấu tài nguyên không tin cậy, loại bỏ/reconnect khi có thể và tránh retry nghiệp vụ khi chưa biết kết quả commit.

Không tiếp tục chạy nhiều SQL trên một connection có protocol lỗi chỉ vì `releaseConnection(...)` đã được gọi. Với thao tác tài chính hoặc ghi dữ liệu quan trọng, cần cơ chế idempotency và đối soát ngoài lớp DAO.

## 15. Kiểm thử tích hợp để chứng minh cùng transaction

Mock `Connection` có thể xác nhận code gọi `DataSourceUtils.releaseConnection(...)`, nhưng không chứng minh hai `UPDATE` cùng được commit/rollback trên DB thật. Hãy kiểm thử với **Spring transaction manager + pool/DataSource + JDBC driver + DBMS** mà ứng dụng thực tế dùng.

### 15.1. Kịch bản thành công

Chuẩn bị hai tài khoản:

```sql
INSERT INTO accounts(id, balance)
VALUES (10, 1000.00), (20, 500.00);
```

Gọi:

```java
transferService.transfer(
        10L, 20L, new BigDecimal("200.00"));
```

Sau khi phương thức trả về thành công và transaction được commit, truy vấn **từ một connection độc lập** phải thấy tài khoản 10 còn `800.00` và tài khoản 20 có `700.00`.

### 15.2. Kịch bản lỗi bước thứ hai: bắt buộc rollback bước thứ nhất

Tạo chỉ tài khoản nguồn ID 30, không tạo tài khoản đích ID 999. Gọi:

```java
assertThrows(SQLException.class, () ->
        transferService.transfer(
                30L, 999L, new BigDecimal("200.00")));
```

Sau đó dùng `JdbcTemplate` hoặc một connection mới đọc lại số dư tài khoản 30. Kỳ vọng số dư **không đổi**.

Nếu tiền nguồn đã bị trừ dù credit đích thất bại, khả năng cao đường thực thi đang có vấn đề về **biên transaction, DataSource hoặc rollback policy**. Test này phát hiện nhiều lỗi thực tế hơn việc chỉ mock `PreparedStatement.executeUpdate()`.

### 15.3. Kiểm tra khả năng nhận diện connection bound

Có thể dùng `TransactionTemplate` tạo scope transaction cho một test cấu trúc:

```java
import java.sql.Connection;

import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public static boolean probeBoundConnection(
        DataSource dataSource,
        PlatformTransactionManager transactionManager) {

    TransactionTemplate template =
            new TransactionTemplate(transactionManager);

    Boolean bound = template.execute(status -> {
        Connection connection =
                DataSourceUtils.getConnection(dataSource);

        try {
            return DataSourceUtils.isConnectionTransactional(
                    connection, dataSource);
        } finally {
            DataSourceUtils.releaseConnection(
                    connection, dataSource);
        }
    });

    return Boolean.TRUE.equals(bound);
}
```

Đây là một phương thức minh họa đặt trong lớp Java có import `javax.sql.DataSource` cùng các class được liệt kê. Nó cho biết Spring đã bind tài nguyên theo `DataSource` trong transaction tạo bởi `TransactionTemplate`. **Vẫn cần bài test rollback ở phần trước** để xác minh thay đổi dữ liệu cuối cùng; không chỉ assert kết quả `true` là đủ.

### 15.4. Test có thể cho kết quả sai nếu test framework tự rollback

Một số Spring test dùng `@Transactional` trên chính test method và tự rollback khi test kết thúc. Điều này có thể khiến một phương thức production **không thực sự được gọi qua transaction proxy đúng như dự kiến** vẫn trông có vẻ “được rollback”.

Để kiểm chứng chính xác boundary của `TransferService.transfer(...)`:

- Chuẩn bị fixture ở transaction độc lập.
- Gọi service thông qua Spring bean thực tế, với transaction context mà test kiểm soát.
- Sau khi service kết thúc, quan sát dữ liệu từ **connection/transaction mới**.
- Không dựa chỉ vào rollback tự động của test framework để kết luận service tự quản lý transaction đúng.
- Đảm bảo test không dùng cùng ID hoặc schema bị các test chạy song song sửa đổi.

### 15.5. Các nhánh test khác

| Kịch bản | Điều muốn chứng minh |
|---|---|
| Đủ số dư, có tài khoản đích | Commit cả debit/credit |
| Không đủ số dư | Không có cập nhật nào được xác nhận |
| Đích không tồn tại | Rollback cả debit đã thực thi |
| `SQLException` từ driver khi credit | Checked exception làm transaction rollback |
| Lỗi timeout/query | Connection/transaction được dọn đúng |
| Không có Spring transaction | Gateway ngoài transaction vẫn release connection; không giả định atomicity cho nhiều thao tác |
| Bean tự tạo bằng `new` thay vì Spring | `@Transactional` không còn tác dụng proxy mặc định |
| Nhiều `DataSource` | Dao/manager dùng đúng cùng tài nguyên |
| Lời gọi `@Async` | Không kế thừa ngầm transaction JDBC từ thread gốc |
| Service dùng `JdbcTemplate` xen kẽ gateway | Cả hai cùng tham gia transaction khi cấu hình đúng |

Nên ghi lại phiên bản Spring, JDBC driver, loại pool, DBMS, isolation level, auto-commit và trạng thái kết quả trên connection mới. Với tính năng đặc thù vendor, unit test mock không thay integration test driver.

## 16. Hướng dẫn chẩn đoán khi rollback không có tác dụng

Khi một transaction tưởng đã rollback nhưng dữ liệu vẫn thay đổi, hãy đặt các câu hỏi theo thứ tự:

1. **Spring có thực sự áp dụng transaction interceptor?** Method có public/được gọi qua Spring bean/proxy trong cấu hình đang dùng không?
2. **Transaction manager nào xử lý `@Transactional`?** Có nhiều manager hoặc nguồn dữ liệu không?
3. **Gateway đang dùng `DataSource` nào?** Có đúng resource mà transaction manager bind không?
4. **Connection có được lấy qua `DataSourceUtils` hoặc abstraction transaction-aware không?**
5. **DAO có tự `commit()` hoặc đổi `autoCommit` không?**
6. **Checked `SQLException` có nằm trong rollback policy không?** Lỗi có bị catch và nuốt đi không?
7. **Có chạy SQL trong thread khác hoặc tác vụ async không?**
8. **Có lệnh DDL/side effect ngoài transaction hoặc database storage engine không hỗ trợ rollback không?**
9. **Test có đo dữ liệu bằng một connection độc lập sau khi transaction kết thúc không?**
10. **Có lỗi commit/connection mà kết quả chưa rõ không?** Nếu có, cần đối soát thay vì kết luận chắc chắn đã rollback.

Một thủ thuật chẩn đoán trong môi trường lab là log `TransactionSynchronizationManager.isActualTransactionActive()` và `DataSourceUtils.isConnectionTransactional(...)`. Nhưng đừng đưa mọi thông tin connection/session nhạy cảm vào production log hoặc coi một cờ true là bằng chứng cuối về dữ liệu.

## 17. Checklist áp dụng `DataSourceUtils` trong code JDBC mức thấp

1. Có thực sự cần JDBC mức thấp, hay `JdbcTemplate`/callback đã giải quyết đủ?
2. Đã xác định rõ **transaction manager**, `DataSource` và ranh giới `@Transactional` chưa?
3. Mọi DAO trong cùng nghiệp vụ có dùng connection nhận qua **`DataSourceUtils.getConnection(dataSource)`** hoặc abstraction Spring transaction-aware nhất quán không?
4. Có luôn **`releaseConnection(connection, dataSource)` trong `finally`** và dùng cùng `DataSource` không?
5. Có đóng `PreparedStatement` và `ResultSet` bằng `try-with-resources` mà không đóng nhầm transaction-bound connection không?
6. Có tránh tự `setAutoCommit`, `commit()` và `rollback()` bên trong gateway khi Spring sở hữu transaction không?
7. Nếu DAO ném `SQLException` checked, có `rollbackFor` hoặc cơ chế exception translation tương ứng không?
8. Có kiểm tra `@Transactional` thực sự được kích hoạt qua Spring proxy và không bị self-invocation/thread hopping làm mất ngữ cảnh không?
9. Nếu transaction có timeout, statement tự tạo có tôn trọng deadline qua `applyTransactionTimeout` và driver hỗ trợ không?
10. Có integration test dùng driver/DBMS thật kiểm tra **hai thao tác commit cùng nhau hoặc rollback cùng nhau** không?
11. Nếu có nhiều `DataSource` hoặc proxy, mapping giữa transaction manager và connection có được kiểm chứng không?
12. Khi kết quả commit chưa rõ, có chính sách idempotency/đối soát thay vì retry mù không?

## Ghi nhớ

- **`DataSourceUtils` là cầu nối JDBC mức thấp với resource/transaction synchronization của Spring**, không phải JDBC driver hay transaction manager.
- **`getConnection(dataSource)`** lấy connection có nhận biết transaction; **`releaseConnection(connection, dataSource)`** giải phóng đúng ngữ cảnh, tránh đóng nhầm connection Spring còn cần.
- **Trong code dùng `DataSourceUtils`, giữ `Connection` trong biến cục bộ và release ở `finally`; dùng `try-with-resources` cho `PreparedStatement` và `ResultSet`**.
- **`@Transactional` chỉ có hiệu lực khi transaction interceptor và manager phù hợp thực sự chạy**. DAO phải dùng đúng `DataSource` được manager quản lý.
- **Spring mặc định không luôn rollback checked `SQLException`**; dùng `rollbackFor=SQLException.class` hoặc ngoại lệ runtime được dịch đúng nếu nghiệp vụ yêu cầu rollback.
- **`DataSourceUtils.applyTransactionTimeout(...)`** giúp statement tự tạo nhận timeout Spring transaction khi phù hợp; không thay việc đặt và kiểm thử deadline.
- **`JdbcTemplate` đã tích hợp cơ chế này** cho CRUD thông thường; chỉ dùng utility trực tiếp khi thật sự cần điều khiển JDBC ở mức thấp.
- **Kiểm thử trên database thật** để bảo đảm hai thao tác thuộc cùng transaction, không chỉ kiểm tra một phương thức helper được gọi.

Khi kết nối JDBC đi qua Spring transaction manager đúng cách, ứng dụng có thể kết hợp tiện ích của `@Transactional` với sức mạnh của các API `Connection`, `PreparedStatement` và `ResultSet` mức thấp. `DataSourceUtils` giúp bảo toàn **cùng một connection và cùng ranh giới giao dịch** giữa các lớp DAO, miễn là code luôn tuân thủ đúng hợp đồng sở hữu tài nguyên, rollback và cấu hình `DataSource`.
