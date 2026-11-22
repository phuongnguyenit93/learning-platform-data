# Nhóm kết nối: mượn, sử dụng và trả lại

Một ứng dụng Spring có thể phục vụ nhiều request cùng lúc, nhưng mỗi truy vấn JDBC cần một `Connection` tới cơ sở dữ liệu. Tạo một kết nối vật lý mới cho mọi thao tác thường tốn chi phí thiết lập phiên, xác thực, mạng và bộ nhớ ở phía DB. **Connection pool (nhóm kết nối)** quản lý một tập kết nối có giới hạn để các công việc có thể mượn, dùng và trả lại mà không phải liên tục mở rồi hủy kết nối vật lý.

Bài học tập trung vào chu trình **mượn → sử dụng → trả**, khác biệt giữa connection logic/vật lý, trách nhiệm đóng tài nguyên, cơ chế `DataSource` trong Spring, quan hệ với giao dịch và cách nhận biết tình trạng hết kết nối. Ví dụ Java 17+ sử dụng HikariCP và H2.

## 1. Từ kết nối trực tiếp đến nhóm kết nối

Cách truy cập JDBC đơn giản nhất:

```java
// Minh họa JDBC trực tiếp; url, user và password đã được khai báo.
try (Connection con = DriverManager.getConnection(url, user, password)) {
    // Chạy SQL trong phạm vi sử dụng connection.
}
```

Mỗi lần `DriverManager.getConnection` thường thiết lập một kết nối vật lý đến DB. Trong ứng dụng có nhiều truy vấn nhỏ, lặp lại quá trình đó làm tăng độ trễ; database cũng chỉ chấp nhận số phiên kết nối hữu hạn.

Pool giữ các connection có thể dùng lại. Khi có connection rảnh và hợp lệ, việc mượn thường nhanh hơn tạo kết nối vật lý. Nếu không có connection rảnh nhưng chưa đạt giới hạn, pool có thể mở thêm. Nếu đã hết công suất, yêu cầu mượn mới phải đợi, hoặc bị từ chối sau timeout.

| Thành phần | Trách nhiệm |
| --- | --- |
| `javax.sql.DataSource` | Giao diện chuẩn cung cấp `Connection` qua `getConnection()`; bản thân giao diện không bảo đảm có pool. |
| `HikariDataSource` | Một triển khai `DataSource` quản lý connection pool, cấu hình giới hạn, timeout, kiểm tra và shutdown. |
| `Connection` được mượn | Handle trao quyền sử dụng kết nối trong phạm vi công việc; không nên giữ mãi trong field dùng chung. |
| Kết nối vật lý | Phiên JDBC thực sự nối với DB, có thể được dùng lại qua nhiều lượt mượn. |
| `PreparedStatement` / `ResultSet` | Tài nguyên của lần thực thi SQL; cần được đóng đúng vòng đời bên trong lần mượn. |

Pool là cơ chế **tái sử dụng và giới hạn tài nguyên**, không phải giao dịch: chỉ dùng pool không tự khiến hai lệnh SQL thuộc cùng một transaction và không làm SQL chậm tự động chạy nhanh hơn.

## 2. Chu trình mượn → sử dụng → trả

```text
Luồng/request gọi DataSource.getConnection()
                    |
            +-------v--------+
            | Connection pool|
            | idle / active  |
            +-------+--------+
                    |
       +------------+-------------------------+
       |            |                         |
   Có idle      Chưa tới max             Đã đạt max
       |            |                         |
   Cấp handle  Có thể tạo vật lý        Chờ cho đến
       |            |                    connectionTimeout
       +------------+                         |
                    v                    Có trả / timeout
          Connection được mượn
                    |
            Statement / ResultSet
                    |
           Hoàn thành công việc
                    |
           Connection.close()
                    |
          Trả handle về pool
                    |
       Reset/kiểm tra/loại bỏ nếu cần
                    |
         Sẵn sàng cho người mượn khác
```

### Mượn

`DataSource.getConnection()` có thể là thao tác **chờ** và có thể ném `SQLException`. Không giả định mượn connection luôn tức thì. Hai lượt mượn khác nhau cũng không được bảo đảm nhận cùng kết nối vật lý.

Một connection đang được mượn thường được tính là **active** ngay cả khi code Java đang làm việc khác và chưa chạy câu lệnh SQL. Vì vậy, mượn gần thời điểm thực sự cần DB, dùng nhanh, trả sớm.

### Sử dụng

Trong thời gian mượn, ứng dụng có thể tạo `PreparedStatement`, gắn tham số, chạy SQL và đọc `ResultSet`. Connection được mượn không nên chia sẻ tùy tiện giữa nhiều request hoặc nhiều thread; trạng thái giao dịch và các thuộc tính JDBC nằm trên connection có thể ảnh hưởng nhau.

Với JDBC tự quản lý transaction, ứng dụng còn chịu trách nhiệm quyết định `commit`/`rollback` trước khi trả connection. Với giao dịch do Spring quản lý, transaction manager nắm quyền này.

### Trả

Khi dùng **pool-managed connection**, gọi `connection.close()` thường là **đóng handle logic và trả lượt mượn**, không phải luôn đóng socket thật. Pool quyết định giữ lại hay loại bỏ kết nối vật lý tùy trạng thái, tuổi thọ và kết quả kiểm tra.

Sau khi `close()`, handle đó đã hết quyền sử dụng; không tiếp tục gọi SQL trên nó hoặc cất lại để dùng sau. Muốn thực hiện tác vụ mới, hãy gọi `getConnection()` lần nữa.

**Đóng handle mượn khác với đóng chính pool.** `HikariDataSource.close()` dừng pool và dành cho thời điểm ứng dụng hoặc thành phần sở hữu pool kết thúc, không gọi sau mỗi request.

## 3. Quy tắc đóng tài nguyên bằng try-with-resources

Trong JDBC trực tiếp, cách phổ biến và an toàn là:

```java
// Minh họa bên trong ứng dụng đã có dataSource và productId.
String sql = "SELECT name FROM product WHERE id = ?";
try (Connection con = dataSource.getConnection();
     PreparedStatement ps = con.prepareStatement(sql)) {
    ps.setLong(1, productId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            System.out.println(rs.getString("name"));
        }
    }
}
```

Đoạn này không chạy độc lập vì `dataSource`, `productId` và bảng `product` thuộc ứng dụng tích hợp. `try-with-resources` bảo đảm gọi `close()` trên các đối tượng đã được mở thành công khi thoát block, kể cả khi SQL ném lỗi. Thứ tự đóng là `ResultSet`, rồi `PreparedStatement`, rồi `Connection`. Nếu `getConnection()` ném exception thì chưa có connection nào để trả.

Nếu sử dụng `try/finally` thủ công, phải xét mọi đường `return`, `throw`, lỗi giữa hai lệnh và exception khi cleanup. Quên release ở một đường lỗi là một nguyên nhân kinh điển gây **connection leak**.

### `close()` không thay cho commit/rollback

Với JDBC tự quản lý giao dịch, điều khiển transaction rõ ràng:

```java
// Đoạn minh họa; performFirstWrite/performSecondWrite
// là các phương thức JDBC của ứng dụng, chưa được định nghĩa ở đây.
try (Connection con = dataSource.getConnection()) {
    con.setAutoCommit(false);
    try {
        performFirstWrite(con);
        performSecondWrite(con);
        con.commit();
    } catch (SQLException | RuntimeException error) {
        try {
            con.rollback();
        } catch (SQLException rollbackFailure) {
            error.addSuppressed(rollbackFailure);
        }
        throw error;
    }
}
```

Pool có thể rollback phần đang dở và khôi phục một số thuộc tính JDBC khi nhận lại connection, tùy implementation. Tuy nhiên, **không dựa vào `close()` để quyết định transaction thành công hay thất bại**; luôn commit/rollback theo nghiệp vụ hoặc để Spring transaction manager quản lý.

## 4. Ví dụ đầy đủ: mượn hết pool rồi trả lại

Ví dụ chạy với **Java 17+, Maven, HikariCP 5.1.0 và H2 in-memory**. Pool chỉ chứa tối đa hai connection vật lý. Giữ hai handle cùng lúc khiến lần mượn thứ ba phải đợi rồi timeout. Khi hai handle được đóng, ta lại mượn được connection và truy vấn dữ liệu.

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>learning</groupId>
    <artifactId>pool-lifecycle-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>com.zaxxer</groupId>
            <artifactId>HikariCP</artifactId>
            <version>5.1.0</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-simple</artifactId>
            <version>2.0.13</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo `src/main/java/PoolLifecycleDemo.java`:

```java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLTransientConnectionException;
import java.sql.Statement;

public class PoolLifecycleDemo {
    public static void main(String[] args) throws SQLException {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl("jdbc:h2:mem:pool_demo;DB_CLOSE_DELAY=-1");
        config.setUsername("sa");
        config.setPassword("");
        config.setPoolName("learning-pool");
        config.setMaximumPoolSize(2);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(1_000);

        try (HikariDataSource pool = new HikariDataSource(config)) {
            // Khởi tạo dữ liệu rồi trả connection.
            try (Connection init = pool.getConnection();
                 Statement stmt = init.createStatement()) {
                stmt.executeUpdate(
                    "CREATE TABLE sample (id INT PRIMARY KEY, message VARCHAR(40))");
                stmt.executeUpdate(
                    "INSERT INTO sample(id, message) VALUES (1, 'hello')");
            }
            System.out.println("Initialized");

            // Hai handle tồn tại đồng thời.
            try (Connection first = pool.getConnection();
                 Connection second = pool.getConnection()) {
                System.out.println("Borrowed 2 connections");
                try (Connection unexpected = pool.getConnection()) {
                    throw new AssertionError("Third borrow should not succeed");
                } catch (SQLTransientConnectionException expected) {
                    System.out.println("Third borrow timed out");
                }
            }
            System.out.println("Returned 2 connections");

            // Hai handle đã trả; có thể mượn lại.
            try (Connection again = pool.getConnection();
                 PreparedStatement ps = again.prepareStatement(
                     "SELECT message FROM sample WHERE id = ?")) {
                ps.setInt(1, 1);
                try (ResultSet rs = ps.executeQuery()) {
                    if (!rs.next()) {
                        throw new SQLException("Missing sample row");
                    }
                    System.out.println(
                        "Borrow again: " + rs.getString("message"));
                }
            }
        }
        System.out.println("Pool closed");
    }
}
```

Chạy trong thư mục `pom.xml` bằng JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=PoolLifecycleDemo
```

Các dòng **stdout từ `System.out`** dự kiến:

```text
Initialized
Borrowed 2 connections
Third borrow timed out
Returned 2 connections
Borrow again: hello
Pool closed
```

HikariCP có thể ghi log khởi động/shutdown hoặc cảnh báo timeout ra **stderr**, không được tính trong các dòng stdout trên.

Giải thích:

1. Connection khởi tạo bảng được trả ngay sau khi tạo dữ liệu.
2. Hai connection `first` và `second` đang được giữ; `maximumPoolSize = 2` khiến lần `getConnection()` thứ ba phải chờ.
3. Khi quá `connectionTimeout = 1_000` mili-giây, HikariCP ném `SQLTransientConnectionException`. Đó là lỗi chờ **mượn** connection; câu SQL của người mượn thứ ba thậm chí chưa được chạy.
4. Thoát block trả hai handle; lần mượn tiếp theo đọc được hàng `hello`.
5. `HikariDataSource.close()` ở block ngoài kết thúc vòng đời pool.

Không kết luận rằng `first`, `second` và `again` luôn dùng cùng kết nối vật lý, hay rằng pool bắt buộc cấp lại theo một thứ tự cố định. Pool có thể thay thế connection khi kiểm tra thấy hỏng hoặc khi vượt tuổi thọ.

## 5. Đối tượng nào được giữ lâu, đối tượng nào được giữ ngắn?

Sai lầm phổ biến:

```java
// SAI: lưu Connection làm field của một repository dùng chung.
class BadRepository {
    private final Connection connection;

    BadRepository(DataSource source) throws SQLException {
        this.connection = source.getConnection();
    }
}
```

Code này giữ mãi một slot active của pool, không có ranh giới release rõ ràng. Nếu nhiều request dùng cùng connection, chúng có thể đụng nhau ở transaction, auto-commit, statement và trạng thái phiên. Connection cũng có thể hỏng sau restart DB.

Đối tượng nên có vòng đời dài là **`DataSource`/pool** (quản lý theo ứng dụng). Đối tượng có vòng đời ngắn là **connection được mượn** (quản lý theo phạm vi thực thi SQL hay transaction). Service/repository nên giữ `DataSource`, `JdbcTemplate` hoặc repository abstraction, **không giữ connection lâu dài**.

Một quy tắc thực tế khác: không mượn connection rồi gọi dịch vụ HTTP, chờ người dùng, sleep lâu hoặc xử lý tác vụ CPU lớn trong khi connection không làm gì. Trong thời gian đó pool vẫn xem connection là active và request khác có thể phải đợi.

## 6. Spring JDBC tự quản lý việc mượn và trả như thế nào?

Spring `JdbcTemplate` giúp lấy connection, tạo statement, thực thi truy vấn, đóng tài nguyên JDBC và dịch exception. Với repository thông thường, bạn không phải gọi `getConnection()`/`close()` trực tiếp.

Đây là **đoạn tích hợp** cho ứng dụng Spring đã có `JdbcTemplate` và bảng `product`:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProductRepository {
    private final JdbcTemplate jdbc;

    public ProductRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public String findName(long id) {
        return jdbc.queryForObject(
            "SELECT name FROM product WHERE id = ?",
            String.class,
            id
        );
    }
}
```

`JdbcTemplate` sử dụng cơ chế truy cập connection **transaction-aware** của Spring dựa trên `DataSourceUtils`. Nếu không có giao dịch Spring đang quản lý, connection thường được release khi thao tác hoàn thành. Nếu có giao dịch liên kết với luồng hiện tại, Spring phải giữ connection đến thời điểm kết thúc transaction; một lời gọi repository trung gian hoàn thành **không có nghĩa** connection đã trả về pool.

### Ranh giới `@Transactional`

Ví dụ service ghép hai thao tác dữ liệu:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderRepository orders;
    private final InventoryRepository inventory;

    public OrderService(OrderRepository orders,
                        InventoryRepository inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public void place(long productId, int quantity) {
        orders.insertOrder(productId, quantity);
        inventory.decreaseStock(productId, quantity);
    }
}
```

Đoạn này **không phải chương trình độc lập**; hai repository là dependency của ứng dụng. Nếu transaction management đã được kích hoạt, lời gọi đi qua Spring interceptor và hai repository dùng cùng `DataSource`/transaction manager phù hợp, luồng phổ biến là:

```text
Request → proxy của OrderService
          → bắt đầu / tham gia transaction
          → bind Connection vào transaction (khi cần)
          → orders.insertOrder() dùng connection đã bind
          → inventory.decreaseStock() dùng connection đã bind
          → COMMIT hoặc ROLLBACK theo kết quả/rollback rules
          → release Connection về pool khi transaction kết thúc
```

Vì thế, thời gian một connection được giữ có thể dài bằng phần đáng kể của transaction, không chỉ thời gian của một câu SQL. Transaction kéo dài do I/O mạng, lock hoặc logic không cần DB sẽ dễ làm pool cạn.

Một số giới hạn cần ghi nhớ:

- `@Transactional` trong proxy mode thông thường không mở ranh giới mới khi method gọi trực tiếp `this.otherMethod()` trong cùng bean.
- Propagation `REQUIRES_NEW` có thể cần thêm connection riêng trong khi transaction ngoài vẫn giữ tài nguyên; phải cân nhắc khả năng hết pool.
- Công việc chuyển sang thread khác không mặc nhiên thừa hưởng connection/transaction của thread gốc.
- Nhiều `DataSource` không tự thành một giao dịch nguyên tử duy nhất chỉ vì cùng xuất hiện trong một phương thức có `@Transactional`.

### Khi buộc phải dùng Connection thủ công trong Spring

Thay vì lấy connection trực tiếp từ pool ở giữa transaction Spring, hãy dùng `DataSourceUtils`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;
import org.springframework.jdbc.datasource.DataSourceUtils;

public final class CustomJdbcAccess {
    private final DataSource dataSource;

    public CustomJdbcAccess(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void markProcessed(long id) throws SQLException {
        Connection con = DataSourceUtils.getConnection(dataSource);
        try (PreparedStatement ps = con.prepareStatement(
                "UPDATE job SET processed = TRUE WHERE id = ?")) {
            ps.setLong(1, id);
            ps.executeUpdate();
        } finally {
            DataSourceUtils.releaseConnection(con, dataSource);
        }
    }
}
```

Class có thể biên dịch khi thêm Spring JDBC, nhưng cần nguồn dữ liệu và bảng `job` để chạy. `getConnection` biết connection do Spring bind vào transaction, `releaseConnection` không đóng sớm connection ấy khi vẫn thuộc transaction. `JdbcTemplate` thường gọn và ít lỗi hơn.

Tránh gọi `dataSource.getConnection()` trực tiếp bên trong transaction Spring rồi giả định connection đó tự tham gia transaction đang có. Nó có thể là một connection khác, chạy ngoài ranh giới commit/rollback được kỳ vọng. `TransactionAwareDataSourceProxy` dành cho một số mã JDBC cũ cần API `DataSource`, nhưng không cần thêm nó nếu dùng `JdbcTemplate` hoặc `DataSourceUtils` đúng cách.

## 7. Pool xử lý trạng thái và kết nối vật lý khi nhận lại

Trả handle về pool không đơn giản là đổi một nhãn `active` thành `idle`. Pool cần bảo đảm kết nối hợp lệ và các trạng thái JDBC có thể được tái sử dụng an toàn.

| Trạng thái | Nguy cơ nếu bị bỏ sót |
| --- | --- |
| `setAutoCommit(false)` còn hiệu lực | Người mượn sau có thể vô tình chạy nhiều lệnh mà không commit. |
| Isolation, read-only, schema/catalog bị đổi | Lệnh sau chạy dưới ngữ cảnh khác kỳ vọng. |
| Transaction chưa được kết thúc | Có thể giữ thay đổi chưa commit/khóa và tạo rò rỉ trạng thái. |
| ResultSet/Statement chưa đóng | Tích tụ cursor, tài nguyên driver hoặc database. |
| Connection vật lý chết do network/DB restart | Lần mượn tiếp theo có thể lỗi nếu không phát hiện và thay thế. |
| Session state đặc thù DB như bảng tạm, biến phiên, advisory lock | Có thể không được reset đầy đủ bởi cơ chế pool chung. |

HikariCP theo dõi/khôi phục một số thuộc tính JDBC chuẩn và có cơ chế xác minh hoặc loại bỏ connection hỏng. Nhưng không nên mặc định pool biết hết session state được thay đổi bằng SQL riêng của một hệ quản trị. Nếu ứng dụng tự tạo session state như vậy, cần cleanup rõ ràng hoặc thiết kế lại.

Với driver JDBC 4 hiện đại, HikariCP thường sử dụng kiểm tra chuẩn như `Connection.isValid(...)` khi cần; không phải mặc định cấu hình `connectionTestQuery` tùy ý. Connection đến tuổi loại bỏ hoặc hỏng có thể bị đóng vật lý **khi trả**, thay vì quay về idle.

## 8. Cấu hình pool và các timeout

Một số thuộc tính HikariCP quan trọng:

| Thuộc tính | Tác dụng | Lưu ý |
| --- | --- | --- |
| `maximumPoolSize` | Số connection tối đa trong một pool, gồm active và idle. | Giới hạn tài nguyên DB; đặt quá lớn có thể tăng tranh chấp. |
| `minimumIdle` | Số connection rảnh pool cố duy trì. | Mặc định HikariCP thường bằng `maximumPoolSize`; có thể bỏ cấu hình nếu muốn pool gần kích thước cố định. |
| `connectionTimeout` | Thời gian tối đa đợi `getConnection()` khi chưa lấy được handle. | Không giới hạn thời gian chạy SQL hay toàn bộ transaction. |
| `idleTimeout` | Khoảng idle trước khi cân nhắc loại bỏ connection dư. | Chủ yếu có tác dụng khi `minimumIdle < maximumPoolSize`; thời điểm loại bỏ không tuyệt đối chính xác. |
| `maxLifetime` | Tuổi tối đa của connection vật lý trước khi lên kế hoạch thay thế. | Connection đang được mượn thường không bị cắt giữa chừng chỉ vì đến tuổi. |
| `keepaliveTime` | Chu kỳ kiểm tra giữ sống đối với kết nối rảnh khi được cấu hình. | Không thay thế timeout TCP, cấu hình DB hay giám sát. |
| `leakDetectionThreshold` | Ngưỡng ghi log nghi ngờ một connection được giữ quá lâu. | Không tự trả connection; giao dịch dài hợp lệ cũng có thể bị cảnh báo. |
| `autoCommit` | Chế độ auto-commit mặc định của connection được cấp. | Khi có Spring transaction, manager điều khiển trạng thái giao dịch theo ranh giới của nó. |

Với ứng dụng **Spring Boot** đã có JDBC driver PostgreSQL, HikariCP và cơ chế auto-configuration tương ứng, cấu hình minh họa:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/appdb
    username: demo_user
    password: demo_password
    hikari:
      pool-name: application-pool
      maximum-pool-size: 12
      connection-timeout: 2000
```

Đây không phải cấu hình production có sẵn: phải dùng secret management thay cho mật khẩu mẫu, cấu hình driver/DB và chọn thông số theo tải thật. `spring.datasource.hikari.*` là cơ chế Spring Boot, không phải namespace tự tồn tại trong mọi ứng dụng Spring Framework thuần.

### Chọn kích thước pool theo tổng tài nguyên DB

Giả sử có 3 instance ứng dụng, mỗi instance tối đa 12 connection. Tổng tiềm năng là **36 connection**, chưa kể tiến trình migration, dịch vụ khác, tác vụ nền và kết nối quản trị. Nếu DB cho phép 40 kết nối thì rất dễ chạm giới hạn. Cần ngân sách connection cho cả hệ thống rồi mới chia cho từng instance.

Không chọn pool bằng cách lấy số request đồng thời rồi đặt connection bằng số đó; một request có thể chưa cần DB hoặc chỉ dùng connection trong thời gian ngắn. Ngược lại, một request với transaction dài có thể giữ connection lâu dù ít SQL. Cần đo thời gian giữ kết nối, số waiting, throughput, CPU/IO của DB, lock và giới hạn backend.

Ví dụ để **ước lượng trung bình**: nếu có 100 công việc DB mỗi giây và mỗi công việc giữ connection trung bình 50 ms, số active trung bình xấp xỉ `100 × 0,05 = 5` trong hệ thống ổn định. Ước lượng này không phản ánh đỉnh tải, phân bố thời gian giữ connection hay giới hạn xử lý của DB; phải đo và đặt headroom phù hợp.

### Ba timeout khác nhau

1. **Borrow/connection timeout:** chưa có `Connection`, `getConnection()` đang đợi pool. HikariCP có thể ném `SQLTransientConnectionException`.
2. **Statement/query/socket timeout:** đã mượn connection; SQL, lock hoặc network kéo dài, gây SQLException ở giai đoạn thực thi.
3. **Transaction/request timeout:** deadline của giao dịch Spring, request HTTP hoặc nghiệp vụ; không đồng nghĩa thời điểm tài nguyên JDBC đã được release.

Tăng `connectionTimeout` chỉ cho phép đợi lâu hơn; không tăng dung lượng pool. Tăng `maximumPoolSize` khi DB đã bão hòa có thể làm sự cố nặng hơn.

## 9. Đo active, idle, total, waiting và thời gian mượn

Các thông số nên quan sát:

- **Active:** connection đang được mượn, kể cả khi thread chưa thực thi SQL.
- **Idle:** connection sẵn có để mượn.
- **Total:** tổng connection vật lý pool đang quản lý tại thời điểm đo.
- **Waiting/pending:** số luồng đang chờ `getConnection()`; khi tăng cao cùng active ≈ max, pool có thể đang bão hòa.
- **Acquisition time:** thời gian chờ mượn; nên xem percentile, không chỉ trung bình.
- **Usage/hold duration:** thời gian từ mượn đến trả; quá dài có thể do transaction, lock, SQL chậm, I/O hoặc leak.
- **Timeout/errors:** phân biệt không lấy được connection với lỗi SQL, network hoặc lỗi DB.

Với `HikariDataSource`, có thể lấy snapshot bằng `HikariPoolMXBean`:

```java
// Đoạn minh họa; pool là HikariDataSource đang hoạt động.
var stats = pool.getHikariPoolMXBean();
System.out.println("active=" + stats.getActiveConnections());
System.out.println("idle=" + stats.getIdleConnections());
System.out.println("total=" + stats.getTotalConnections());
System.out.println("waiting=" + stats.getThreadsAwaitingConnection());
```

Các con số này thay đổi liên tục nên **không có stdout cố định**. Trong hệ thống thực, nên đưa metric ra công cụ quan sát và đối chiếu với query latency, transaction duration, deadlock, giới hạn connection phía DB.

### Leak detection không phải cơ chế đóng tự động

`leakDetectionThreshold` giúp log stack trace khi một handle bị giữ lâu đáng ngờ. Đó là dấu hiệu để điều tra, không kết luận chắc chắn đã leak. Một transaction hợp lệ nhưng lâu cũng có thể vượt ngưỡng. Thư viện không tự đóng handle chỉ vì phát cảnh báo leak.

Một leak thực sự thường là code mượn connection nhưng mất đường release, ví dụ câu lệnh ném exception rồi return/throw trước khi tới `close()`. Kiểm tra try-with-resources, finally và mọi đường thoát trước khi chỉ tăng pool size.

## 10. Chẩn đoán khi bị timeout mượn connection

```text
getConnection() timeout
        |
        +-- active chạm maximumPoolSize liên tục?
        |       +-- thời gian giữ connection dài:
        |       |     kiểm tra transaction, SQL, lock, I/O trong transaction
        |       +-- handle bị quên release:
        |             kiểm tra nhánh exception, leak log, resource ownership
        |
        +-- waiting cao nhưng DB chưa bão hòa?
        |       +-- đánh giá lại sizing và peak concurrency bằng số liệu
        |
        +-- total chưa đạt max nhưng vẫn không cấp được?
                +-- kiểm tra DB max connections, mạng, xác thực,
                    driver, validation hoặc khả năng tạo phiên mới
```

Không nên lập tức nâng `maximumPoolSize`; một vấn đề lock kéo dài có thể khiến nhiều connection chờ lẫn nhau. Cải thiện query, giảm thời gian giữ transaction và khắc phục leak thường hiệu quả hơn.

## 11. Các lỗi phổ biến và cách tránh

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Quên `close()` ở nhánh exception | Connection ở trạng thái active lâu và pool hết chỗ. | Dùng `try-with-resources` hoặc `finally` ở JDBC trực tiếp. |
| Lưu `Connection` làm field singleton | Rò rỉ slot, chia sẻ trạng thái transaction giữa request. | Lưu `DataSource`/`JdbcTemplate`; mượn theo phạm vi công việc. |
| Gọi `HikariDataSource.close()` sau một query | Dừng toàn bộ pool. | Chỉ shutdown pool khi thành phần sở hữu nó kết thúc. |
| Hiểu `Connection.close()` là luôn đóng socket | Bỏ qua cơ chế tái sử dụng và vòng đời handle logic. | Với pool-managed handle, close là trả; pool quyết định xử lý vật lý. |
| Không đóng statement/result set | Rò rỉ cursor hoặc tài nguyên driver. | Đóng chúng trong try-with-resources. |
| Gọi `DataSource.getConnection()` trực tiếp giữa `@Transactional` | Có thể nhận connection ngoài transaction Spring đang bind. | Ưu tiên `JdbcTemplate` hoặc `DataSourceUtils`. |
| Tưởng method repository return là connection được trả dù còn transaction ngoài | Chẩn đoán sai số active. | Hiểu transaction manager chỉ release khi transaction kết thúc. |
| Để giao dịch dở dang rồi chỉ đóng handle | Kết quả transaction phụ thuộc pool/driver, khó kiểm soát. | Commit/rollback rõ ràng hoặc để Spring quản lý. |
| Tăng max pool để giải quyết SQL chậm hoặc lock | Có thể dồn thêm tải lên DB. | Kiểm tra query, lock và thời gian giữ active. |
| Coi leak log là bằng chứng leak chắc chắn | Chẩn đoán nhầm transaction dài hợp lệ. | Đối chiếu stack trace, metrics và thời gian release. |
| Giữ connection khi gọi HTTP hay sleep | Chiếm slot dù không dùng DB. | Đưa I/O không cần DB ra ngoài transaction/lượt mượn. |

## 12. Checklist vận hành

Trước khi triển khai hoặc sửa lỗi nhóm kết nối, tự hỏi:

1. **Ai sở hữu pool?** Pool được tạo và shutdown theo vòng đời ứng dụng hay bị tạo/đóng ở từng request?
2. **Ai sở hữu handle?** Có bảo đảm release ở mọi đường thành công, exception và early-return không?
3. **Ai sở hữu transaction?** Là JDBC trực tiếp hay Spring transaction manager? Có hai cách quản lý bị trộn lẫn không?
4. **Connection được giữ bao lâu?** Có chờ I/O, HTTP, lock hoặc thao tác không cần DB trong lúc active không?
5. **Khi hết connection thì sao?** Có timeout phù hợp, thông báo lỗi đúng và metric waiting không?
6. **Tổng số connection của mọi instance có phù hợp giới hạn DB?** Có phần dự phòng cho dịch vụ khác không?
7. **Pool có quan sát được không?** Có active, idle, waiting, acquisition time, usage time và cảnh báo lỗi DB không?
8. **Có session state không được reset tự động không?** Nếu có, ai dọn dẹp nó trước lượt mượn tiếp theo?

**Ghi nhớ:** `DataSource` là nguồn cung connection; `getConnection()` là mượn; thao tác JDBC/transaction là sử dụng; `Connection.close()` với pool-managed handle thường là trả; `HikariDataSource.close()` là shutdown pool. Trong Spring, `JdbcTemplate` và transaction manager phối hợp việc mượn/trả theo đúng ranh giới giao dịch. Pool chỉ có một số kết nối hữu hạn, nên hiệu năng phụ thuộc vào cả **thời gian giữ connection** và **khả năng phục vụ của database**.

### Tài liệu tham khảo

- HikariCP — thiết kế và các tùy chọn cấu hình: https://github.com/brettwooldridge/HikariCP
- Spring Framework — JDBC `DataSource`: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Framework — `DataSourceUtils`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html
- Java SE 17 — `java.sql.Connection`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html
