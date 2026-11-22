# Dùng `DataSource` được cấu hình trong ứng dụng Spring

Trong chương **Tích hợp Spring**, ứng dụng Java có thể tiếp tục dùng **JDBC** để truy cập cơ sở dữ liệu quan hệ, thực hiện SQL tham số hóa, CRUD, đọc `ResultSet`, quản lý transaction, batching và xử lý lỗi. Điểm khác so với một ứng dụng Java thuần là **Spring quản lý đối tượng `DataSource`** và cung cấp nó cho những thành phần cần dùng, thay vì để từng DAO tự tạo kết nối bằng `DriverManager.getConnection(...)`.

Với Spring Boot, một `DataSource` thường có thể được **auto-configure** từ `application.yml` và các dependency trên classpath. Với Spring Framework không dùng Boot, ta có thể khai báo `DataSource` bằng `@Bean`. Trong cả hai trường hợp, repository nên nhận dependency qua constructor; khi cần tham gia `@Transactional`, mã phải lấy connection theo cơ chế transaction của Spring.

Bài học này giúp bạn:

- Hiểu vai trò của `javax.sql.DataSource` và connection pool trong Spring.
- Cấu hình và tiêm một `DataSource` cho mã JDBC.
- Dùng `PreparedStatement`/`ResultSet` đúng vòng đời.
- Phân biệt kết nối lấy trực tiếp và kết nối do Spring transaction manager quản lý.
- Dùng `JdbcTemplate`, `DataSourceUtils` và `@Transactional` đúng cách.
- Xử lý cấu hình nhiều DataSource, lỗi transaction, timeout, quyền truy cập và kiểm thử.

## 1. `DataSource` vẫn là API JDBC

`DataSource` thuộc package `javax.sql` của JDBC, không phải một loại database riêng của Spring:

~~~java
import javax.sql.DataSource;
import java.sql.Connection;

try (Connection conn = dataSource.getConnection()) {
    // conn là java.sql.Connection của JDBC.
}
~~~

Một `DataSource` có thể cấp kết nối mới mỗi lần, hoặc sử dụng **connection pool** để tái sử dụng những kết nối vật lý. Spring chỉ làm nhiệm vụ quản lý lifecycle và dependency injection cho bean này.

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| `DataSource` | Cấp `Connection` cho ứng dụng | HikariDataSource, DataSource của container |
| Connection pool | Giới hạn/tái sử dụng kết nối vật lý | HikariCP |
| JDBC driver | Chuyển các API JDBC thành giao tiếp DBMS | pgJDBC, MySQL Connector/J |
| `Connection` | Thực thi SQL, quản lý transaction/isolation JDBC | `setAutoCommit`, `commit`, `rollback` |
| `PreparedStatement` | Truyền tham số an toàn, thực thi SQL | `setLong`, `setString`, `executeUpdate` |
| `ResultSet` | Đọc các hàng được trả về | `next`, `getObject` |
| Spring container | Tạo/tiêm/đóng các bean theo cấu hình | `@Configuration`, `@Bean`, `@Component` |

Sơ đồ:

~~~mermaid
flowchart TD
    S["Spring ApplicationContext"] --> DS["DataSource bean"]
    S --> A["ProductRepository"]
    S --> B["WalletTransferService"]
    S --> JT["JdbcTemplate bean"]
    A --> DS
    B --> JT
    JT --> DS
    DS --> P["Connection pool, nếu có"]
    P --> DR["JDBC driver"]
    DR --> DB["PostgreSQL / MySQL / DBMS"]
~~~

**Lợi ích khi Spring sở hữu `DataSource`:**

1. URL, username, password, timeout, pool size nằm ở **một nơi cấu hình**.
2. Repository phụ thuộc vào interface, không hard-code driver và credentials.
3. Nhiều thành phần tái sử dụng cùng pool mà không tạo pool riêng cho mỗi request.
4. Spring có thể quản lý vòng đời và đóng tài nguyên pool khi dừng ứng dụng.
5. Transaction manager có thể điều phối những lời gọi JDBC cùng sử dụng đúng `DataSource`.
6. Integration test có thể thay DataSource bằng một DB riêng cho test.

**Lưu ý:** “Dùng cùng `DataSource`” **không có nghĩa mọi phương thức tự động dùng cùng một connection**. Pool có thể trả connection khác nhau ở mỗi lần mượn. Khi cần một transaction chung, phải sử dụng đúng cơ chế binding của Spring.

## 2. Spring Framework và Spring Boot khác nhau ở đâu?

**Spring Framework** cung cấp bean container, `JdbcTemplate`, `DataSourceUtils` và transaction management. **Spring Boot** bổ sung auto-configuration và cách đặt thuộc tính theo quy ước.

| Công việc | Spring Framework | Spring Boot |
| --- | --- | --- |
| Tạo `DataSource` | Tự khai báo bean hoặc cấu hình qua container | Có thể tự tạo từ `spring.datasource.*` |
| Chọn pool | Tự thêm/configure implementation | Thường ưu tiên HikariCP nếu đủ dependency |
| Tạo `JdbcTemplate` | Thường tự khai báo `@Bean` | Có thể được auto-configure |
| Tạo transaction manager | Khai báo manager và bật transaction | Có auto-configuration khi điều kiện phù hợp |
| Cấu hình môi trường | `@Value`, properties, secrets | Externalized config, profiles, property binding |

Không phải mọi Spring Boot application đều có DataSource bean: cần JDBC-related dependency, driver và cấu hình phù hợp. Nếu đã tự định nghĩa bean, auto-configuration mặc định có thể lùi lại.

## 3. Dùng `spring-boot-starter-jdbc` trong Spring Boot

Với dự án Maven đang dùng Spring Boot dependency management, dependency thường như sau:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Trong ví dụ này, DBMS đích là PostgreSQL. Nếu ứng dụng dùng MySQL, SQL Server hoặc DBMS khác, phải thay JDBC driver và URL tương ứng. Không cần tự thêm phiên bản dependency ở snippet nếu ứng dụng đã có BOM/parent quản lý; nếu không, dự án phải cung cấp phiên bản tương thích.

### Ví dụ `application.yml`

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/inventory_db
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 12
      minimum-idle: 2
      connection-timeout: 30000
      validation-timeout: 5000
~~~

Giải thích:

- `spring.datasource.url`: JDBC URL trỏ đến DBMS mục tiêu; `localhost` chỉ phù hợp khi DB thực sự chạy tại địa chỉ đó.
- `username` và `password`: lấy từ biến môi trường hoặc secret đã cấp cho ứng dụng.
- `maximum-pool-size`: giới hạn số connection vật lý mà pool quản lý cho ứng dụng theo cấu hình.
- `minimum-idle`: số idle connection pool cố duy trì trong điều kiện phù hợp.
- `connection-timeout`: thời gian chờ **lấy connection từ HikariCP**, tính theo mili giây; không phải giới hạn thời gian chạy SQL.
- `validation-timeout`: thời gian pool cho phép kiểm tra connection còn hợp lệ; cũng không phải query timeout.

Các số trên **chỉ là cấu hình ví dụ**, không phải giá trị tối ưu cho mọi ứng dụng.

### Có cần khai báo driver class?

Trong trường hợp thông thường, Boot có thể nhận diện driver từ URL và classpath. Có thể khai báo thêm khi cần:

~~~yaml
spring:
  datasource:
    driver-class-name: org.postgresql.Driver
~~~

Điều quan trọng hơn là dependency JDBC driver thực sự có mặt và tương thích với server. Chỉ ghi tên class mà thiếu driver JAR vẫn không giúp ứng dụng mở kết nối.

### Vì sao không commit password thật?

Không đưa credential production vào file được commit lên Git. Dùng môi trường triển khai, secret manager, vault hoặc cơ chế quản lý cấu hình an toàn. Đảm bảo log khởi động, thông báo lỗi và công cụ quan sát không in password hay JDBC URL chứa thông tin nhạy cảm.

## 4. Tiêm `DataSource` bằng constructor injection

Trong Spring, một class được đăng ký bean có thể nhận `DataSource` qua constructor:

~~~java
import javax.sql.DataSource;
import org.springframework.stereotype.Component;

@Component
public class DatabaseInfo {
    private final DataSource dataSource;

    public DatabaseInfo(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public String implementationName() {
        return dataSource.getClass().getName();
    }
}
~~~

Repository không cần biết username, URL, kích thước pool hoặc cách tạo driver. Spring container cấp dependency khi khởi tạo bean.

Constructor injection giúp:

- Giữ dependency rõ ràng, thường là `final`.
- Dễ kiểm thử với một DataSource riêng.
- Phát hiện sớm cấu hình thiếu bean.
- Tránh truy xuất ApplicationContext bằng tay ở mọi phương thức.

`getClass().getName()` có thể cho biết class DataSource hoặc proxy nhưng **không chứng minh** pool đang hoạt động đúng. Muốn xác nhận khả năng kết nối, có thể thực hiện một truy vấn kiểm tra có deadline và dùng công cụ health/metrics.

### Không tạo pool trong từng repository

Sai:

~~~java
@Repository
class BadRepository {
    private final HikariDataSource pool =
        new HikariDataSource(); // Một pool riêng, chưa cấu hình.
}
~~~

Một repository tự tạo DataSource làm phân tán cấu hình và rủi ro leak. Nếu mỗi request còn tạo thêm pool, số connection vật lý có thể tăng ngoài kiểm soát.

Cách đúng là **tiêm bean `DataSource` đã cấu hình** từ Spring.

## 5. Dùng `DataSource` trực tiếp với `PreparedStatement` và `ResultSet`

Đây là ví dụ JDBC thuần trong một Spring repository. Ví dụ dành cho thao tác **đọc độc lập không yêu cầu tham gia transaction Spring hiện có**.

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import org.springframework.stereotype.Repository;

record Product(long id, String name, long priceCents) {}

@Repository
public class PlainJdbcProductReader {
    private final DataSource dataSource;

    public PlainJdbcProductReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<Product> findById(long productId)
            throws SQLException {
        String sql = """
            SELECT id, name, price_cents
            FROM products
            WHERE id = ?
            """;

        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setLong(1, productId);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }
                return Optional.of(new Product(
                    rs.getLong("id"),
                    rs.getString("name"),
                    rs.getLong("price_cents")
                ));
            }
        }
    }
}
~~~

Đây là JDBC chuẩn: dùng SQL tham số hóa, đóng `ResultSet`, `PreparedStatement` và `Connection` bằng `try-with-resources`.

Với pooled DataSource, `Connection.close()` thường trả **logical connection về pool**, không nhất thiết đóng socket vật lý. Dù vậy, luôn đóng logical connection đúng scope để không làm cạn pool.

**Cảnh báo quan trọng:** Trong Spring `@Transactional`, lời gọi `dataSource.getConnection()` trực tiếp trên pool **có thể lấy connection không được transaction manager ràng buộc với transaction hiện tại**. Đoạn mã này không phải ví dụ phù hợp để phối hợp nhiều bước ghi cần nguyên tử dưới `@Transactional`. Cách dùng đúng nằm ở phần 7–9.

## 6. `JdbcTemplate` là cách phổ biến để dùng DataSource trong Spring

Spring JDBC có `JdbcTemplate`, một lớp tiện ích làm việc dựa trên `DataSource` và các API JDBC:

- Lấy connection phù hợp với Spring transaction.
- Tạo và đóng statement/result set.
- Bind tham số SQL.
- Gọi `executeQuery()`/`executeUpdate()`.
- Ánh xạ các hàng thành đối tượng Java.
- Chuyển lỗi `SQLException` sang các lớp `DataAccessException`.

Ví dụ:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProductRepository {
    private final JdbcTemplate jdbc;

    public ProductRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<Product> findById(long id) {
        List<Product> results = jdbc.query(
            """
            SELECT id, name, price_cents
            FROM products
            WHERE id = ?
            """,
            (rs, rowNum) -> new Product(
                rs.getLong("id"),
                rs.getString("name"),
                rs.getLong("price_cents")
            ),
            id
        );
        return results.stream().findFirst();
    }

    public int rename(long id, String newName) {
        return jdbc.update(
            "UPDATE products SET name = ? WHERE id = ?",
            newName, id
        );
    }
}
~~~

`JdbcTemplate` không phải ORM: bạn vẫn viết SQL, chọn cột, kiểm tra số hàng ảnh hưởng và xác định transaction. Nó giảm boilerplate, đặc biệt giúp connection được lấy/giải phóng đúng cách khi Spring quản lý transaction.

### Dùng tham số có tên

Với SQL dài, Spring cung cấp `NamedParameterJdbcTemplate`:

~~~java
import java.util.Map;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

int changed = namedJdbc.update(
    """
    UPDATE products
    SET name = :name
    WHERE id = :id
    """,
    Map.of("name", "Bàn phím", "id", 100L)
);
~~~

`:name` và `:id` là tham số tên do Spring xử lý; bên dưới vẫn truyền giá trị an toàn bằng JDBC.

**Không nhầm tham số hóa với phân quyền.** Truy vấn `WHERE id = ?` chưa bảo vệ dữ liệu của tenant khác nếu chính sách yêu cầu `tenant_id = ?`. Tầng repository phải áp điều kiện quyền như một quy tắc bắt buộc.

## 7. `@Transactional` gắn với DataSource nào?

Với transaction JDBC cục bộ, Spring thường quản lý connection của **một DataSource** thông qua transaction manager như `JdbcTransactionManager` hoặc `DataSourceTransactionManager`.

~~~mermaid
sequenceDiagram
    participant API as Controller/Caller
    participant Proxy as Spring transactional proxy
    participant TM as JDBC Transaction Manager
    participant Repo as JdbcTemplate Repository
    participant DB as Database
    API->>Proxy: transfer(...)
    Proxy->>TM: Begin transaction
    TM->>TM: Bind Connection vào thread
    Proxy->>Repo: UPDATE ví A
    Repo->>DB: Dùng Connection đã bind
    Proxy->>Repo: UPDATE ví B
    Repo->>DB: Cùng Connection transaction
    alt Thành công
       Proxy->>TM: commit()
    else RuntimeException
       Proxy->>TM: rollback()
    end
~~~

Điều kiện quan trọng:

1. Transaction manager phải quản lý **cùng DataSource** mà `JdbcTemplate` đang dùng.
2. Lời gọi method `@Transactional` phải đi qua cơ chế transaction của Spring, thường là Spring proxy.
3. Toàn bộ các lệnh SQL cần nguyên tử phải tham gia **cùng connection/transaction**.
4. DBMS/storage engine phải hỗ trợ transaction.
5. Lỗi cần rollback phải được truyền ra hoặc được đánh dấu rollback-only theo chính sách.

### Ví dụ chuyển tiền bằng `JdbcTemplate` và `@Transactional`

Giả sử bảng:

~~~sql
CREATE TABLE wallets (
    id BIGINT PRIMARY KEY,
    balance DECIMAL(19, 2) NOT NULL CHECK (balance >= 0)
);
~~~

Service:

~~~java
import java.math.BigDecimal;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WalletTransferService {
    private final JdbcTemplate jdbc;

    public WalletTransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(
            long fromId, long toId, BigDecimal amount
    ) {
        if (fromId == toId || amount == null
                || amount.signum() <= 0) {
            throw new IllegalArgumentException(
                "Yêu cầu chuyển tiền không hợp lệ"
            );
        }

        int debited = jdbc.update(
            """
            UPDATE wallets
            SET balance = balance - ?
            WHERE id = ? AND balance >= ?
            """,
            amount, fromId, amount
        );

        if (debited != 1) {
            throw new IllegalStateException(
                "Ví nguồn không tồn tại hoặc không đủ số dư"
            );
        }

        int credited = jdbc.update(
            """
            UPDATE wallets
            SET balance = balance + ?
            WHERE id = ?
            """,
            amount, toId
        );

        if (credited != 1) {
            throw new IllegalStateException(
                "Ví đích không tồn tại"
            );
        }
    }
}
~~~

Khi lệnh cộng tiền thất bại và method ném `IllegalStateException`, Spring transaction manager sẽ yêu cầu rollback đối với transaction hiện tại theo chính sách mặc định. Khoản trừ ở bước đầu sẽ không được commit nếu cả hai câu SQL thực sự ở cùng transaction.

Ví dụ chỉ nói về **giao dịch trong một DBMS**; hệ thống thanh toán thật còn cần kiểm soát concurrency, idempotency, nhật ký giao dịch, đối soát và các ràng buộc nghiệp vụ khác.

### Vì sao không tự gọi `commit()` trong repository?

Trong mô hình `@Transactional`, tầng service/transaction manager quyết định ranh giới giao dịch. Nếu repository tự gọi `Connection.commit()`, nó có thể xác nhận dữ liệu **trước** khi toàn bộ quy trình nghiệp vụ hoàn thành.

Repository chỉ nên chạy SQL và trả kết quả; việc commit/rollback thuộc tầng transaction đã được thiết kế.

## 8. Sai lầm quan trọng: lấy connection trực tiếp bên trong Spring transaction

Giả sử một method `@Transactional` gọi repository:

~~~java
// CÓ THỂ SAI nếu cần tham gia @Transactional:
try (Connection conn = dataSource.getConnection()) {
    // JDBC ở đây có thể dùng Connection khác
    // với Connection do Spring bind vào thread.
}
~~~

Một DataSource dạng pool thông thường có thể trả về connection khác, auto-commit mặc định có thể bật. Lúc ấy, dù `@Transactional` của service rollback, SQL của repository có thể đã commit riêng.

**Cách đúng cho mã Spring mới:** dùng `JdbcTemplate` hoặc cơ chế lấy connection của Spring là `DataSourceUtils`.

### `DataSourceUtils` khi muốn tiếp tục viết JDBC thuần

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.stereotype.Repository;

@Repository
public class ScopedJdbcProductWriter {
    private final DataSource dataSource;

    public ScopedJdbcProductWriter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public int rename(long id, String name)
            throws SQLException {
        Connection conn =
            DataSourceUtils.getConnection(dataSource);

        try {
            try (PreparedStatement ps = conn.prepareStatement(
                    "UPDATE products SET name = ? WHERE id = ?")) {
                ps.setString(1, name);
                ps.setLong(2, id);
                return ps.executeUpdate();
            }
        } finally {
            DataSourceUtils.releaseConnection(
                conn, dataSource
            );
        }
    }
}
~~~

`DataSourceUtils.getConnection(...)` được thiết kế để tương tác với connection gắn vào transaction hiện tại. `releaseConnection(...)` chỉ đóng/trả connection khi thích hợp, không phá connection mà Spring transaction manager đang giữ.

**Đừng dùng `try (Connection conn = DataSourceUtils.getConnection(...))`**: auto-close có thể can thiệp vòng đời của connection do transaction manager kiểm soát. Chỉ đóng statement/result set bằng try-with-resources; giải phóng connection bằng `DataSourceUtils.releaseConnection(...)`.

Với mã JDBC legacy khó sửa, Spring còn có `TransactionAwareDataSourceProxy`. Đây là wrapper có thể làm những lời gọi `getConnection()` kiểu cũ tham gia hạ tầng Spring transaction trong điều kiện phù hợp. Tuy nhiên, không nên đưa proxy nhiều tầng vào hệ thống tùy tiện; với code mới, `JdbcTemplate` hoặc `DataSourceUtils` thường rõ và dễ test hơn.

## 9. Các giới hạn của `@Transactional` cần hiểu

### 9.1. Self-invocation

~~~java
@Service
class OrderService {
    void outerMethod() {
        innerMethod(); // Gọi trực tiếp trên this.
    }

    @Transactional
    public void innerMethod() {
        // Transaction có thể không được tạo theo proxy mode.
    }
}
~~~

Trong mô hình proxy thông dụng của Spring, một lời gọi trong cùng object không đi qua proxy, nên annotation trên method được gọi nội bộ có thể không có hiệu lực. Thay đổi thiết kế service để lời gọi transaction đi qua một bean do Spring quản lý, hoặc dùng cơ chế transaction phù hợp.

### 9.2. Runtime exception và checked exception

Mặc định, Spring thường rollback đối với `RuntimeException` và `Error`, nhưng **không mặc định rollback với mọi checked exception**.

~~~java
@Transactional(rollbackFor = SQLException.class)
public void updateWithRawJdbc() throws SQLException {
    // Gọi JDBC thuần và ném SQLException.
}
~~~

Nếu lỗi checked exception phải rollback, cần `rollbackFor` hoặc cấu hình quy tắc tương đương. `JdbcTemplate` thường ném `DataAccessException` dạng unchecked, nên mặc định phù hợp với nhiều đường lỗi SQL.

Không bắt và nuốt exception chỉ để trả một giá trị mặc định nếu nghiệp vụ yêu cầu rollback. Khi exception không thoát khỏi method, transaction manager có thể xem việc gọi method là thành công, trừ khi đã có trạng thái rollback-only hoặc lỗi DB ngăn commit.

### 9.3. Bất đồng bộ và thread mới

Transaction JDBC kiểu imperative thường gắn với **thread**. Chạy JDBC trong `CompletableFuture.runAsync(...)` hoặc `@Async` không tự mang theo transaction của thread gọi.

Nếu công việc bất đồng bộ cần ghi DB, hãy thiết kế **transaction riêng** cho mỗi task, xử lý kết quả/đối soát và không chia sẻ cùng `Connection` bừa bãi giữa nhiều thread.

### 9.4. Nhiều cơ sở dữ liệu

Một local JDBC transaction manager thường quản lý **một DataSource**. Một lời gọi `@Transactional` không tự tạo giao dịch nguyên tử trên hai DataSource khác nhau. Nếu ghi đồng thời vào hai hệ thống, cần thiết kế transaction phân tán hoặc các mô hình outbox/saga/bù trừ theo yêu cầu thực tế.

## 10. Tự khai báo `DataSource` trong Spring Framework

Khi không dùng Spring Boot auto-configuration, hoặc cần một cấu hình riêng, có thể tạo `DataSource` bằng `@Bean`. Ví dụ Spring Framework + HikariCP:

~~~java
import javax.sql.DataSource;
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class JdbcConfig {
    @Bean
    public DataSource dataSource(
            @Value("${app.db.url}") String url,
            @Value("${app.db.user}") String user,
            @Value("${app.db.password}") String password
    ) {
        HikariConfig cfg = new HikariConfig();
        cfg.setJdbcUrl(url);
        cfg.setUsername(user);
        cfg.setPassword(password);
        cfg.setMaximumPoolSize(12);
        return new HikariDataSource(cfg);
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    public PlatformTransactionManager transactionManager(
            DataSource dataSource
    ) {
        return new JdbcTransactionManager(dataSource);
    }
}
~~~

Ví dụ này cần dependency HikariCP và Spring JDBC/transaction thích hợp. Các thuộc tính `app.db.*` cần được cung cấp từ nguồn cấu hình an toàn; cấu hình Spring thuần có thể cần thêm property source phù hợp.

`JdbcTransactionManager` là một transaction manager được Spring JDBC cung cấp trong các phiên bản hỗ trợ; `DataSourceTransactionManager` là lựa chọn khác thường gặp. Cả hai quản lý transaction cục bộ dựa trên JDBC DataSource.

**Không cần tạo bean thủ công nếu Boot auto-configuration đã đáp ứng yêu cầu.** Khi bạn tự tạo `@Bean DataSource`, Boot có thể không tạo bean mặc định nữa. Một số thuộc tính `spring.datasource.hikari.*` không tự động bind vào bean thủ công của bạn; phải cấu hình chính xác theo cách bạn đã chọn.

## 11. Nhiều `DataSource`: cần chỉ định rõ bean và transaction manager

Nếu ứng dụng dùng cả DB đơn hàng và DB báo cáo:

~~~java
@Component
public class ReportService {
    private final DataSource reporting;

    public ReportService(
            @Qualifier("reportingDataSource")
            DataSource reporting
    ) {
        this.reporting = reporting;
    }
}
~~~

Mẫu trên yêu cầu ứng dụng thực sự khai báo bean `reportingDataSource`. Nếu nhiều DataSource cùng type và không có `@Qualifier` hoặc `@Primary` phù hợp, Spring có thể không biết nên inject bean nào.

Với transaction manager đặt tên, có thể viết:

~~~java
@Transactional("ordersTransactionManager")
public void performOrderOperation() {
    // Repository phải dùng JdbcTemplate/DataSource
    // tương ứng với ordersTransactionManager.
}
~~~

Không được giả định transaction manager của orders cũng tự rollback những thao tác dùng reporting DataSource. Cần kiểm tra cả phương thức giao dịch và đường cấu hình bean khi có nhiều nguồn dữ liệu.

## 12. Connection pool không phải transaction manager

Pool và transaction là hai nhiệm vụ khác nhau:

- **Pool** quản lý **kết nối vật lý/logical**, giới hạn số lượng và thời gian chờ mượn.
- **Transaction manager** quản lý **ranh giới begin/commit/rollback** và binding connection cho một đơn vị nghiệp vụ.
- **JdbcTemplate** giúp mã gọi SQL bằng connection đúng với Spring transaction khi cấu hình phù hợp.

| Thao tác | Chủ thể điều phối |
| --- | --- |
| `dataSource.getConnection()` | DataSource/pool |
| `Connection.close()` với pooled connection | Trả logical connection về pool theo implementation |
| `@Transactional` | Spring transaction interceptor/manager |
| `JdbcTemplate.update()` trong transaction | Spring JDBC dùng connection transaction-bound |
| Pool exhaustion timeout | Pool, không đồng nghĩa query timeout |
| `Statement.setQueryTimeout()` | JDBC driver và DBMS theo hỗ trợ |
| `Connection.setNetworkTimeout()` | JDBC driver/network layer theo hỗ trợ |

**Ví dụ nhầm lẫn:** `spring.datasource.hikari.connection-timeout: 30000` nghĩa là chờ mượn connection tối đa khoảng 30 giây theo cấu hình Hikari, **không** có nghĩa mọi câu `SELECT` sẽ tự bị hủy sau 30 giây.

Query timeout và transaction timeout có API/chính sách riêng, phải kiểm thử khả năng thực thi trên driver/DBMS mục tiêu.

### Khi pool quá tải

Một pool size lớn không mặc nhiên nhanh hơn. Cần xét tổng connection từ **mọi instance** của ứng dụng, thời gian mỗi transaction giữ connection, lock waits, query plan, batch/reporting jobs và giới hạn DBMS.

Nên theo dõi active/idle/pending connections, thời gian lấy connection, query latency, transaction duration, deadlock và lỗi mở kết nối. Đóng `ResultSet`/`Statement` sớm để tránh giữ connection không cần thiết.

## 13. Bảo mật và trạng thái session khi tái sử dụng connection

Tập trung `DataSource` giúp kiểm soát credential và quyền truy cập, nhưng cũng tạo một trách nhiệm chung:

1. Dùng DB runtime role **ít quyền nhất** theo nghiệp vụ; role migration nên tách khi thích hợp.
2. Không nhận username/password từ request để cấp quyền DB một cách tùy tiện.
3. SQL tham số hóa bảo vệ giá trị khỏi injection nhưng không tự thêm `tenant_id`/`owner_id`. Phân quyền vẫn phải thực hiện trong truy vấn hoặc DB policy.
4. Nếu dùng PostgreSQL Row-Level Security hoặc session variables, phải reset scope giữa các lần dùng lại pooled connection.
5. Ưu tiên transaction-local context khi DBMS hỗ trợ, đồng thời kiểm thử cả commit, rollback, timeout và exception.
6. Cấu hình TLS/server certificate validation phù hợp driver; không coi mọi tùy chọn “ssl=true” là đã xác minh hostname/certificate.
7. Không ghi password hoặc token vào SQL logs, metrics labels hay exception message tự xây dựng.

Một kết nối logic được tenant A sử dụng rồi trả về pool có thể được tenant B mượn. Nếu driver/server session còn giữ `search_path` hoặc tenant variable cũ, tenant B có thể đọc sai phạm vi. Đây là lỗi **connection state hygiene**, không phải lỗi của PreparedStatement.

## 14. Kiểm thử cấu hình DataSource và transaction thật

Một integration test cần xác nhận:

- Spring container tạo được đúng `DataSource` và `JdbcTemplate`.
- URL, driver, schema và runtime DB role đúng môi trường test.
- Mọi thao tác trong một method `@Transactional` dùng cùng transaction.
- Khi bước thứ hai thất bại, bước đầu bị rollback.
- Connection trả về pool khi hoàn tất hoặc ném exception.
- Nhiều DataSource không bị chọn nhầm.
- Schema/constraint, isolation và generated keys được kiểm thử với DBMS mục tiêu.

### Ví dụ JUnit 5 + Spring Boot integration test

Giả sử lớp `WalletTransferService` đã được đăng ký thành bean, bảng `wallets` tồn tại trên **database riêng cho test**. Test này **không bọc toàn bộ method test trong `@Transactional`**, để service tự mở/kết thúc transaction và bước đọc sau đó quan sát trạng thái đã commit.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class WalletTransferIntegrationTest {
    @Autowired WalletTransferService transfers;
    @Autowired JdbcTemplate jdbc;

    @Test
    void rollbackWhenDestinationIsMissing() {
        long sourceId = 501001L;
        long missingTargetId = 999999L;

        // Chỉ chạy trên DB test có dữ liệu fixture được cô lập.
        jdbc.update(
            "INSERT INTO wallets(id, balance) VALUES (?, ?)",
            sourceId, new BigDecimal("100.00")
        );

        try {
            assertThrows(IllegalStateException.class, () ->
                transfers.transfer(
                    sourceId, missingTargetId,
                    new BigDecimal("30.00")
                )
            );

            BigDecimal after = jdbc.queryForObject(
                "SELECT balance FROM wallets WHERE id = ?",
                BigDecimal.class,
                sourceId
            );

            assertNotNull(after);
            assertEquals(0,
                new BigDecimal("100.00").compareTo(after));
        } finally {
            jdbc.update(
                "DELETE FROM wallets WHERE id = ?",
                sourceId
            );
        }
    }
}
~~~

**Giới hạn và chuẩn bị:**

- `missingTargetId` phải chắc chắn **không tồn tại** trong fixture.
- Dùng schema/DB riêng hoặc định danh fixture duy nhất; đừng cho test khác chạy đồng thời trên cùng ID.
- Test có thể ghi và dọn dữ liệu thật trong DB test; không trỏ nó vào production.
- Nếu lỗi xảy ra trong quá trình setup hoặc cleanup, cần tổ chức fixture/transaction phù hợp để test không để lại dữ liệu.
- Test này kiểm tra **rollback của service khi được gọi qua Spring bean**. Đây là điều mà test chỉ assert exception, hoặc test tự bao ngoài bằng một transaction rollback, có thể không chứng minh rõ.

### `@JdbcTest` có thể thay DataSource bằng DB nhúng

Trong một số cấu hình Spring Boot test slice, `@JdbcTest` có thể tự thay DataSource bằng embedded DB nếu có dependency. Khi muốn kiểm thử đúng PostgreSQL/MySQL mục tiêu, cần cấu hình không thay DataSource, ví dụ ở các phiên bản Boot hỗ trợ annotation:

~~~java
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;

@JdbcTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class JdbcTargetDatabaseTest {
    // Test với DataSource đã được cấu hình cho DB test.
}
~~~

`Replace.NONE` không tự khởi động DBMS: dự án vẫn phải cấp server/container, credentials và migration. Với phiên bản Boot khác nhau, hãy kiểm tra package/API của test annotations tương ứng.

Đừng dùng test trên H2 ở chế độ tương thích PostgreSQL để kết luận tất cả transaction/locking, RLS, JSONB hoặc generated keys của PostgreSQL đã được chứng minh.

## 15. Phân biệt lỗi `SQLException` và `DataAccessException`

JDBC thuần có thể ném checked `SQLException`:

~~~java
try {
    int updated = ps.executeUpdate();
} catch (SQLException error) {
    System.err.println("SQLState: " + error.getSQLState());
    System.err.println("Vendor code: " + error.getErrorCode());
    throw error;
}
~~~

`JdbcTemplate` thường chuyển thành các lớp con của `org.springframework.dao.DataAccessException` (unchecked), có thể phân loại lỗi DB mà không buộc mọi method phải khai báo `throws SQLException`.

~~~java
import org.springframework.dao.DataAccessException;

try {
    repository.rename(productId, "Tên mới");
} catch (DataAccessException error) {
    // Để transaction manager nhận biết lỗi bắt buộc.
    throw error;
}
~~~

Không giả định mọi driver đều được dịch thành cùng subclass cụ thể. Khi cần chẩn đoán, hãy xem nguyên nhân gốc, SQLState, vendor code và log.

Chỉ thêm `@Repository` lên một class dùng JDBC thuần **không tự dịch tất cả `SQLException` mà class đó ném**. `JdbcTemplate` thực hiện exception translation trong các API nó quản lý.

Với PostgreSQL, nhiều lỗi SQL trong một transaction có thể khiến transaction ở trạng thái aborted và cần rollback. Không thử tiếp tục gửi SQL chỉ vì mã Java đã bắt một exception.

## 16. Những lỗi cấu hình và sử dụng thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Từng DAO tự đọc JDBC URL và gọi `DriverManager` | Phân tán cấu hình, bỏ qua pool | Inject `DataSource` bean |
| Tạo Hikari pool mỗi request | Bùng nổ kết nối và leak | Một pool do Spring quản lý |
| Tự tạo `@Bean DataSource` rồi nghĩ Boot vẫn bind mọi property cũ | Cấu hình không khớp | Chọn rõ auto-config hay manual bean |
| `@Transactional` cùng `dataSource.getConnection()` trực tiếp | SQL có thể ngoài transaction | `JdbcTemplate` hoặc `DataSourceUtils` |
| Dùng try-with-resources cho connection lấy qua `DataSourceUtils` | Đóng connection transaction-bound sai lúc | `releaseConnection` |
| Repository tự commit trong service transaction | Phá tính nguyên tử | Transaction manager sở hữu commit |
| Method `@Transactional` gọi từ `this` | Proxy thường không intercept | Tách bean/đổi thiết kế |
| Nuốt ngoại lệ bắt buộc | Transaction có thể commit dở | Ném lại hoặc đánh dấu rollback |
| Dùng checked exception nhưng quên `rollbackFor` | Có thể không rollback | Cấu hình đúng chính sách |
| Tạo thread mới trong transaction rồi nghĩ cùng connection | Transaction thread-bound | Transaction riêng cho task |
| Nhiều DataSource không có qualifier | Inject/transaction nhầm DB | `@Qualifier` và manager riêng |
| Nhầm Hikari connection timeout với SQL timeout | Chẩn đoán sai nghẽn pool | Đo và cấu hình đúng loại timeout |
| Chỉ kiểm tra happy path | Không lộ lỗi pool/rollback | Integration test bằng DB mục tiêu |
| Để session tenant context trong pooled connection | Rò phạm vi giữa request | Transaction-local/reset state |
| Lưu mật khẩu thật trong file Git | Lộ secret | Dùng secret manager/env |
| Tăng max pool size không đo DB load | DBMS có thể càng quá tải | Theo dõi pool, query và lock waits |

## 17. Tình huống luyện tập

**Tình huống A.** Spring Boot đã có `spring.datasource.url`, username/password và dependency `spring-boot-starter-jdbc`. Repository có cần gọi `DriverManager.getConnection(...)` không?

**Đáp án:** Thông thường không. Boot có thể tạo `DataSource` bean và repository inject bean đó. Dùng `JdbcTemplate` hoặc JDBC đúng vòng đời theo mục tiêu transaction.

**Tình huống B.** Hai repository inject cùng DataSource pool, nhưng mỗi nơi gọi `dataSource.getConnection()` trực tiếp trong method service `@Transactional`. Có chắc hai thao tác cùng transaction không?

**Đáp án:** Không. Có thể chúng lấy connection khác connection do manager quản lý. Dùng `JdbcTemplate` hoặc `DataSourceUtils` trên đúng DataSource.

**Tình huống C.** Một repository gọi `DataSourceUtils.getConnection()` rồi đóng ngay bằng `conn.close()`. Vì sao rủi ro?

**Đáp án:** Connection có thể đang được transaction manager giữ. Phải giải phóng bằng `DataSourceUtils.releaseConnection(conn, dataSource)` để tuân theo cơ chế Spring.

**Tình huống D.** `WalletTransferService.transfer()` được gọi qua Spring bean, trừ tiền thành công nhưng cộng tiền vào ví đích không tồn tại. Kết quả đúng?

**Đáp án:** Nếu Spring transaction hoạt động và hai SQL dùng cùng connection, `IllegalStateException` sẽ dẫn tới rollback, không giữ khoản trừ tiền.

**Tình huống E.** Một method `@Transactional` bắt `DataAccessException` rồi chỉ log và return bình thường. Có chắc rollback không?

**Đáp án:** Không. Transaction có thể được commit nếu exception đã bị nuốt và transaction chưa được đánh dấu rollback-only. Không bỏ qua lỗi bắt buộc.

**Tình huống F.** `spring.datasource.hikari.connection-timeout: 30000` có nghĩa mọi SELECT bị dừng sau 30 giây?

**Đáp án:** Không. Đó là giới hạn chờ lấy connection từ pool, tính bằng mili giây, khác query timeout.

**Tình huống G.** App có `ordersDataSource` và `analyticsDataSource`. Một `@Transactional("ordersTransactionManager")` có rollback cả analytics DB không?

**Đáp án:** Không mặc định. Local transaction manager chỉ quản lý DataSource tương ứng. Cần thiết kế consistency khác cho nhiều DB.

**Tình huống H.** Method có `@Transactional` nhưng được gọi bằng `this.update()` từ một method cùng class. Có bảo đảm proxy tạo transaction không?

**Đáp án:** Không theo proxy mode thường gặp. Lời gọi nội bộ không đi qua Spring proxy; cần tổ chức bean/call path phù hợp.

**Tình huống I.** Sau khi app dùng tenant A, connection được trả về pool rồi cấp cho tenant B nhưng session variable vẫn giữ tenant A. Vấn đề thuộc lớp nào?

**Đáp án:** Quản lý trạng thái session của pooled connection. Cần transaction-local context hoặc reset được kiểm chứng, không chỉ SQL tham số hóa.

**Tình huống J.** Test `@JdbcTest` chạy xanh với H2 và production dùng PostgreSQL. Có chứng minh PostgreSQL transaction/driver giống H2 không?

**Đáp án:** Không. Cần integration test trên DBMS mục tiêu và kiểm soát việc test slice có thay DataSource bằng DB nhúng hay không.

**Tình huống K.** Một ứng dụng tự tạo `@Bean DataSource` nhưng vẫn thay `spring.datasource.hikari.maximum-pool-size`, vì sao số connection không đổi?

**Đáp án:** Bean tự tạo có thể không nhận được property binding mặc định của Boot. Cần cấu hình/bind chính bean đó và xác nhận pool thật.

**Tình huống L.** App gửi SQL tham số hóa qua JdbcTemplate nhưng chỉ lọc `WHERE id = ?`. Có tự động được phân quyền theo tenant không?

**Đáp án:** Không. Parameter binding chống SQL injection, không thay authorization. Repository phải đưa predicate quyền được xác thực vào SQL hoặc dùng DB policy phù hợp.

## Ghi nhớ

- **`DataSource` là API JDBC được Spring quản lý thành bean**; nó có thể đại diện cho connection pool, giúp tập trung cấu hình và vòng đời.
- **Spring Boot thường cấu hình `DataSource` từ `spring.datasource.*`** khi đủ dependency; Spring Framework có thể khai báo `@Bean`.
- **Constructor injection** giúp repository dùng đúng bean thay vì tự tạo driver/pool.
- **`JdbcTemplate` vẫn là JDBC** nhưng giảm boilerplate, đóng tài nguyên đúng cách và phối hợp với Spring transaction.
- **`@Transactional` yêu cầu SQL tham gia đúng connection do transaction manager quản lý**. Dùng `JdbcTemplate`/`DataSourceUtils`, không mặc nhiên lấy connection trực tiếp từ pool.
- **Connection pool, transaction manager, query timeout và network timeout là những cơ chế khác nhau**; cần phân biệt và đo thực tế.
- **Kiểm thử rollback, connection state, quyền truy cập và DBMS mục tiêu** trước khi coi cấu hình JDBC/Spring đã phù hợp sản xuất.
