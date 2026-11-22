# Cấp phát kết nối thông qua DataSource trong JDBC

Để thực thi truy vấn SQL, ứng dụng Java cần một `Connection` tới hệ quản trị cơ sở dữ liệu. **JDBC (Java Database Connectivity)** cung cấp hai cách tiếp cận thường gặp: lấy kết nối qua `DriverManager` và lấy kết nối qua **`javax.sql.DataSource`**. Với những ứng dụng có nhiều thành phần nghiệp vụ, `DataSource` là điểm truy cập kết nối thuận tiện vì mã xử lý dữ liệu chỉ cần biết **nguồn cấp kết nối**, còn việc cấu hình driver, tài khoản và cơ chế cấp phát được quản lý bên ngoài.

Trong chương *Quản lý kết nối*, cần phân biệt ba thao tác: **cấu hình `DataSource`**, **xin `Connection` để thực hiện một đơn vị công việc**, và **đóng `Connection` đúng lúc**. Khi `DataSource` có kết hợp connection pool, `close()` thường trả kết nối về pool để tái sử dụng; với nguồn không có pool, đóng kết nối thường giải phóng kết nối vật lý.

## 1. `DataSource` là gì?

`DataSource` là **giao diện tiêu chuẩn của JDBC trong gói `javax.sql`**, không phải tên một driver hay một pool cụ thể. Nó mô tả một đối tượng có thể cung cấp các kết nối JDBC:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.SQLException;

public static void runQuery(DataSource dataSource) throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        // Su dung connection de thuc thi SQL.
    } // Dong Connection sau khi hoan tat cong viec.
}
```

Hai phương thức quan trọng là:

- `Connection getConnection()`: lấy kết nối bằng thông tin xác thực/cấu hình đã được thiết lập trong nguồn.
- `Connection getConnection(String username, String password)`: yêu cầu kết nối bằng cặp thông tin đăng nhập truyền trực tiếp. Việc hỗ trợ hoặc hành vi kết hợp với pool phụ thuộc `DataSource` cụ thể.

`DataSource` còn có các phương thức cấu hình/khai báo như `setLoginTimeout()`, `getLoginTimeout()` và `getLogWriter()`. Tuy nhiên, các cấu hình chuyên biệt (URL, host, pool size, SSL, timeout...) thường thuộc về **lớp hiện thực**, chứ không phải các setter chung của interface `DataSource`.

### `DataSource` không mặc định là connection pool

Đây là điểm quan trọng nhất trong bài:

| Kiểu nguồn kết nối | Khi gọi `getConnection()` | Khi gọi `Connection.close()` |
| --- | --- | --- |
| `DataSource` đơn giản, không pool | Thường thiết lập một kết nối vật lý mới | Thường đóng/giải phóng kết nối vật lý |
| `DataSource` được pool quản lý | Thường lấy một kết nối logic từ pool, có thể tạo kết nối vật lý nếu cần | Thường trả kết nối logic về pool; kết nối vật lý được pool quản lý |
| `DataSource` do application server cung cấp | Hành vi do server, pool và transaction manager cấu hình | Trả tài nguyên theo hợp đồng quản lý của server |

Vì vậy câu “dùng `DataSource` tức là đã có pooling” là **sai**. Pool là một **cơ chế triển khai/cấu hình**, còn `DataSource` là **hợp đồng lấy connection** mà ứng dụng có thể dùng chung.

## 2. So sánh `DataSource` và `DriverManager`

`DriverManager` thuộc `java.sql` và thường dùng để kết nối trực tiếp:

```java
import java.sql.Connection;
import java.sql.DriverManager;

try (Connection connection = DriverManager.getConnection(
        "jdbc:postgresql://localhost:5432/store",
        System.getenv("APP_DB_USER"),
        System.getenv("APP_DB_PASSWORD"))) {
    // Thuc thi SQL.
}
```

Với `DataSource`, mã nghiệp vụ không cần tự biết URL và tài khoản:

```java
import java.sql.Connection;
import javax.sql.DataSource;

public static void performWork(DataSource dataSource) throws Exception {
    try (Connection connection = dataSource.getConnection()) {
        // Thuc thi SQL.
    }
}
```

| Tiêu chí | `DriverManager` | `DataSource` |
| --- | --- | --- |
| API lấy kết nối | Lời gọi tĩnh `getConnection(url, ...)` | Phương thức `getConnection()` của một đối tượng nguồn |
| Thông tin kết nối | Thường truyền vào tại vị trí mở kết nối | Thường cấu hình riêng rồi đưa `DataSource` cho nơi sử dụng |
| Đổi database hoặc driver | Mã gọi thường chứa/nhận URL và cấu hình driver | Có thể đổi cách tạo/configure `DataSource` mà giữ mã repository |
| Connection pooling | Không tự tạo pool | Có thể dùng `DataSource` của một pool |
| Dependency injection | Cần lớp trung gian nếu muốn tiêm cấu hình | Dễ tiêm trực tiếp bằng interface `DataSource` |
| Ứng dụng nhỏ/minh họa | Phù hợp | Cũng phù hợp |
| Ứng dụng nhiều request/đồng thời | Có thể dùng với kiến trúc bổ sung | Thường thuận tiện khi kết hợp pool và lifecycle do framework quản lý |

Cả hai đều dựa vào **JDBC driver** tương thích với DBMS; `DataSource` không thay thế driver. `DataSource` cũng không tự bảo đảm hiệu năng cao hơn: lợi ích hiệu năng thường đến từ **connection pooling được cấu hình phù hợp**, tránh phải liên tục thiết lập kết nối vật lý.

## 3. Kiến trúc cấp phát qua `DataSource`

Ứng dụng không cần tự quyết định mỗi lần mở TCP socket hay tái sử dụng connection. Thay vào đó, phần quản lý hạ tầng cấu hình một `DataSource` và đưa nó tới các thành phần truy cập dữ liệu:

```text
    Cấu hình ứng dụng / container
         | URL, credentials, TLS,
         | pool size, timeout...
         v
    +---------------------------+
    | DataSource implementation |
    | (đơn giản hoặc có pool)   |
    +-------------+-------------+
                  ^
                  | getConnection()
                  |
    +-------------+-------------+
    | Repository / DAO          |
    | SQL qua JDBC              |
    +-------------+-------------+
                  |
                  | Connection,
                  | PreparedStatement,
                  | ResultSet
                  v
              JDBC driver
                  |
                  v
                 DBMS
```

Mã truy cập dữ liệu chỉ phụ thuộc `javax.sql.DataSource`. Phần khởi tạo cụ thể có thể sử dụng một lớp của driver, một thư viện pool hoặc nguồn do application server đăng ký. Nhờ vậy cùng một repository có thể phục vụ cho môi trường local và production bằng hai cách cấp phát khác nhau.

## 4. Ví dụ không có pool: `PGSimpleDataSource`

Đầu tiên, xét ví dụ chạy với **PostgreSQL JDBC Driver**. Lớp `org.postgresql.ds.PGSimpleDataSource` là một hiện thực `DataSource` riêng của driver PostgreSQL và **không triển khai connection pooling**. Ứng dụng cần thêm dependency PostgreSQL JDBC Driver tương thích với phiên bản Java đang sử dụng.

Giả sử database `store` có bảng:

```sql
CREATE TABLE inventory_item (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(64) NOT NULL UNIQUE,
    quantity INTEGER NOT NULL CHECK (quantity >= 0)
);

INSERT INTO inventory_item(id, sku, quantity)
VALUES (1, 'SKU-001', 20);
```

Mã Java hoàn chỉnh bên dưới gồm **nơi khởi tạo nguồn** và **nơi tiêu thụ nguồn**:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;
import org.postgresql.ds.PGSimpleDataSource;

public final class DataSourceExample {
    private DataSourceExample() {}

    public static void main(String[] args) throws SQLException {
        String user = requiredEnv("APP_DB_USER");
        String password = requiredEnv("APP_DB_PASSWORD");

        PGSimpleDataSource postgres = new PGSimpleDataSource();
        postgres.setServerNames(new String[] {"localhost"});
        postgres.setPortNumbers(new int[] {5432});
        postgres.setDatabaseName("store");
        postgres.setUser(user);
        postgres.setPassword(password);

        DataSource dataSource = postgres;
        System.out.println(findSkuById(dataSource, 1L));
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isEmpty()) {
            throw new IllegalStateException("Thieu bien moi truong " + name);
        }
        return value;
    }

    // Repository chi phu thuoc interface DataSource.
    public static Optional<String> findSkuById(
            DataSource dataSource, long itemId) throws SQLException {

        String sql = "SELECT sku FROM inventory_item WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, itemId);
            try (ResultSet result = statement.executeQuery()) {
                if (result.next()) {
                    return Optional.of(result.getString("sku"));
                }
                return Optional.empty();
            }
        }
    }
}
```

Để chạy ví dụ, cần PostgreSQL đang hoạt động tại địa chỉ/cổng đã ghi, database và bảng đã được tạo, tài khoản có quyền `SELECT`, hai biến môi trường đã có giá trị và driver đã được đưa vào classpath. Với hàng mẫu, kết quả là `Optional[SKU-001]`.

Những điểm đáng chú ý:

1. `PGSimpleDataSource` là **lớp cấu hình cụ thể**. Việc đặt host, port và tài khoản chỉ làm ở bước khởi tạo.
2. `findSkuById` nhận **`DataSource` thay vì `PGSimpleDataSource`**; phương thức không cần biết driver hay quy trình mở kết nối.
3. `getConnection()` được gọi **tại thời điểm cần truy cập dữ liệu**, tránh giữ một `Connection` dùng mãi cho nhiều yêu cầu.
4. `PreparedStatement` nhận tham số `?` qua `setLong()`, không phải ghép giá trị người dùng vào chuỗi SQL.
5. `try-with-resources` đóng `ResultSet`, `PreparedStatement` và `Connection` sau khi truy vấn. Vì ví dụ dùng `PGSimpleDataSource` không có pool, mỗi lần lấy connection thường cần thiết lập kết nối vật lý.

**Không đưa `PGSimpleDataSource` thành một pool chỉ bằng cách sử dụng biến kiểu `DataSource`.** Loại đối tượng thực tế do code khởi tạo vẫn quyết định cách cấp phát.

## 5. Ví dụ có pool: `HikariDataSource`

Trong ứng dụng có nhiều request, việc tạo kết nối vật lý cho mỗi truy vấn tốn chi phí thiết lập TCP, xác thực và khởi tạo phiên. **Connection pool** giữ một nhóm kết nối vật lý để nhiều luồng công việc có thể mượn và trả lại.

Một ví dụ phổ biến là **HikariCP**. Thư viện này cung cấp `HikariDataSource` hiện thực `DataSource`; ứng dụng cần thêm dependency HikariCP **và** JDBC driver của DBMS. Dưới đây là phần cấu hình minh họa (các con số phải được điều chỉnh theo tải thực tế và giới hạn kết nối của DBMS):

```java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import javax.sql.DataSource;

HikariConfig config = new HikariConfig();
config.setJdbcUrl("jdbc:postgresql://localhost:5432/store");
config.setUsername(System.getenv("APP_DB_USER"));
config.setPassword(System.getenv("APP_DB_PASSWORD"));
config.setMaximumPoolSize(10);
config.setConnectionTimeout(10_000); // Thoi gian cho lay connection: 10 giay.

try (HikariDataSource pool = new HikariDataSource(config)) {
    DataSource dataSource = pool;

    // Dung lai phuong thuc findSkuById(DataSource, long) o vi du tren.
    System.out.println(DataSourceExample.findSkuById(dataSource, 1L));
}
```

Đây là đoạn mã dùng trong một phương thức (ví dụ `main`) đã khai báo `throws SQLException` hoặc tự xử lý lỗi. Trong ứng dụng thật, **pool thường được khởi tạo một lần khi ứng dụng bắt đầu và đóng khi ứng dụng kết thúc**; không tạo rồi đóng pool mỗi khi xử lý một HTTP request.

### Pool làm gì khi ứng dụng xin connection?

```text
                  DataSource / Pool
                      |
     +----------------+----------------+
     |                |                |
  Kết nối A         Kết nối B       Kết nối C
  (đang dùng)       (rảnh)          (rảnh)
                      |
     getConnection() -> mượn B
                      |
               SQL / transaction
                      |
         Connection.close() -> trả B
                      |
             B có thể được mượn lại
```

Trình tự tổng quát:

1. Pool được cấu hình với URL, tài khoản, kích thước tối đa và các timeout phù hợp.
2. `dataSource.getConnection()` yêu cầu **một connection logic**. Nếu có connection vật lý rảnh, pool có thể tái sử dụng; nếu còn dung lượng, pool có thể mở thêm.
3. Ứng dụng sử dụng connection trong phạm vi xử lý ngắn, rồi gọi `close()`.
4. Pool đưa connection vật lý có thể tái sử dụng về trạng thái sẵn sàng theo cơ chế của thư viện; một số connection có thể bị hủy nếu hỏng hoặc quá tuổi.
5. Nếu các connection đều bận và không thể cấp thêm, yêu cầu có thể phải **chờ**, rồi lỗi timeout nếu vượt thời gian quy định.

Từ góc nhìn mã JDBC, cả nguồn không pool và có pool đều có `getConnection()` và `close()`. **Không suy đoán rằng mọi lần `close()` đều đóng socket**, vì đối với pool nó thường đánh dấu đã trả connection về nguồn.

## 6. Ai sở hữu `DataSource` và ai sở hữu `Connection`?

Trong kiến trúc ứng dụng, cần phân biệt vòng đời của **nguồn kết nối** và **kết nối đang mượn**:

| Tài nguyên | Thường được tạo bởi | Thời gian sống nên có | Ai kết thúc vòng đời? |
| --- | --- | --- | --- |
| `DataSource` đơn giản | Bootstrap/configuration hoặc framework | Gắn với cấu hình ứng dụng | Chủ sở hữu cấu hình/ứng dụng |
| `DataSource` có pool | Bootstrap, dependency injection container hoặc application server | Thường kéo dài theo vòng đời ứng dụng | Chủ sở hữu pool/container |
| `Connection` lấy từ nguồn | Repository/service khi cần công việc | Một đơn vị công việc hoặc một transaction | Bên đã mượn, hoặc transaction manager quản lý |
| `PreparedStatement` | Thành phần thực thi truy vấn | Trong phạm vi thao tác SQL | Bên tạo statement |
| `ResultSet` | Statement trả về | Trong phạm vi đọc kết quả | Bên đọc; nên đóng rõ ràng |

Một repository nên nhận `DataSource` qua constructor thay vì tạo nguồn mới bên trong từng phương thức:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.Objects;
import javax.sql.DataSource;

public final class InventoryRepository {
    private final DataSource dataSource;

    public InventoryRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public int setQuantity(long itemId, int quantity) throws SQLException {
        if (quantity < 0) {
            throw new IllegalArgumentException("quantity khong duoc am");
        }
        String sql = "UPDATE inventory_item SET quantity = ? WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setInt(1, quantity);
            statement.setLong(2, itemId);
            return statement.executeUpdate();
        }
    }
}
```

Lớp repository chỉ giữ `DataSource` để xin connection khi cần. **Không lưu một `Connection` dùng chung làm field tĩnh hoặc chia sẻ cho nhiều request đồng thời**, vì connection có trạng thái phiên/transaction, thường không được thiết kế để nhiều tác vụ nghiệp vụ thao tác đồng thời trên cùng một connection.

### Lưu ý khi dùng framework quản lý transaction

Với các framework như Spring, nếu transaction manager chịu trách nhiệm cấp phát connection cho toàn bộ giao dịch, mã truy cập dữ liệu cần dùng đúng cơ chế lấy/trả connection được framework quy định (ví dụ `JdbcTemplate`, `DataSourceUtils`, hoặc các lớp repository do framework quản lý). Không tự mở một connection mới bằng `dataSource.getConnection()` rồi mặc định nó sẽ tham gia transaction đang được framework quản lý. Quy tắc chi tiết phụ thuộc cách cấu hình transaction và loại `DataSource`.

## 7. Giữ một connection xuyên suốt transaction

Mỗi lần `getConnection()` có thể trả về **một connection khác nhau**. Nếu hai câu SQL phải được commit hoặc rollback như một đơn vị, nên chạy chúng trên **cùng một `Connection`** và quản lý transaction rõ ràng.

Ví dụ chuyển `units` đơn vị hàng từ một kho/mặt hàng sang một dòng khác trong bảng `inventory_item` đã định nghĩa:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public static void transferStock(
        DataSource source, long fromId, long toId, int units)
        throws SQLException {

    if (units <= 0 || fromId == toId) {
        throw new IllegalArgumentException("Tham so chuyen kho khong hop le");
    }

    try (Connection connection = source.getConnection()) {
        boolean previousAutoCommit = connection.getAutoCommit();
        try {
            connection.setAutoCommit(false);

            String decreaseSql =
                    "UPDATE inventory_item SET quantity = quantity - ? " +
                    "WHERE id = ? AND quantity >= ?";
            String increaseSql =
                    "UPDATE inventory_item SET quantity = quantity + ? " +
                    "WHERE id = ? AND quantity <= ?";

            try (PreparedStatement decrease =
                         connection.prepareStatement(decreaseSql);
                 PreparedStatement increase =
                         connection.prepareStatement(increaseSql)) {

                decrease.setInt(1, units);
                decrease.setLong(2, fromId);
                decrease.setInt(3, units);
                if (decrease.executeUpdate() != 1) {
                    throw new SQLException("Nguon khong ton tai hoac thieu hang");
                }

                increase.setInt(1, units);
                increase.setLong(2, toId);
                increase.setInt(3, Integer.MAX_VALUE - units);
                if (increase.executeUpdate() != 1) {
                    throw new SQLException("Dich khong ton tai hoac vuot gioi han");
                }
            }

            connection.commit();
        } catch (SQLException error) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                error.addSuppressed(rollbackError);
            }
            throw error;
        } finally {
            connection.setAutoCommit(previousAutoCommit);
        }
    }
}
```

Điểm quan trọng ở ví dụ là **chỉ xin connection một lần cho cả hai cập nhật**. Nếu thao tác thứ hai thất bại, `rollback()` hủy thay đổi trước đó trong phạm vi transaction (với điều kiện DBMS và bảng hỗ trợ transaction theo cấu hình tương ứng). Dữ liệu được bảo vệ thêm bằng ràng buộc `CHECK (quantity >= 0)` và điều kiện cập nhật để tránh số lượng âm hoặc tràn `INTEGER`.

Khi dùng pool, cần **khôi phục trạng thái connection** như `autoCommit` trước khi trả connection về pool, hoặc để transaction manager/pool được cấu hình thực hiện reset theo hợp đồng của chúng. Mã ví dụ minh họa transaction JDBC thủ công; trong hệ thống thực tế nên dùng một transaction boundary nhất quán và xử lý lỗi khôi phục trạng thái phù hợp với framework.

## 8. Đăng ký `DataSource` từ JNDI hoặc dependency injection

Trong một số application server, `DataSource` được cấu hình bên ngoài mã Java và **tra cứu qua JNDI (Java Naming and Directory Interface)**:

```java
import javax.naming.InitialContext;
import javax.naming.NamingException;
import javax.sql.DataSource;

public static DataSource lookupDataSource() throws NamingException {
    InitialContext context = new InitialContext();
    return (DataSource) context.lookup("java:comp/env/jdbc/StoreDB");
}
```

Tên `java:comp/env/jdbc/StoreDB` chỉ là ví dụ. Server phải cấu hình tài nguyên với tên đó, driver và quyền tương ứng. **Một ứng dụng Java SE thông thường không tự có JNDI datasource nếu chưa thiết lập provider/context**.

Trong các ứng dụng sử dụng dependency injection, `DataSource` thường được cung cấp qua constructor:

```java
public final class InventoryService {
    private final InventoryRepository repository;

    public InventoryService(DataSource source) {
        this.repository = new InventoryRepository(source);
    }
}
```

Đoạn này giả định `InventoryRepository` ở phần trước và `javax.sql.DataSource` đã được import. Spring Boot và nhiều framework có thể tạo pool và bean `DataSource` từ cấu hình của ứng dụng; quy tắc khởi tạo và đóng pool phụ thuộc framework. Mã nghiệp vụ vẫn chỉ cần interface `DataSource`.

## 9. Các tham số vận hành quan trọng của một connection pool

Khi dùng pool, lựa chọn giá trị cấu hình phải dựa trên tải thực tế, giới hạn DBMS và số bản sao của ứng dụng.

| Tham số/cơ chế | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| Kích thước pool tối đa | Số connection vật lý tối đa pool giữ | Tổng connection của **tất cả instance** có thể vượt giới hạn DBMS nếu mỗi instance cấu hình quá lớn |
| Thời gian chờ lấy connection | Khoảng thời gian request chờ pool cấp connection | Hết thời gian thường gây lỗi cấp phát; cần theo dõi tình trạng pool bão hòa |
| Thời gian sống tối đa | Thời gian pool dự kiến giữ connection trước khi thay thế | Phải xét timeout của database, network/load balancer và chính sách pool |
| Idle timeout / minimum idle | Quản lý connection rảnh | Không phải thư viện nào cũng cho phép điều chỉnh độc lập mọi tham số |
| Kiểm tra tính hợp lệ | Tránh cấp connection đã hỏng | Pool có thể dùng `Connection.isValid()` hoặc truy vấn validation |
| Leak detection / metrics | Quan sát connection bị giữ quá lâu, số request đang chờ | Không thay thế việc đóng connection đúng phạm vi |

Ví dụ: ứng dụng có **5 instance** với pool tối đa **20** trên mỗi instance có thể sử dụng đến **100 connection vật lý** chỉ riêng từ các instance này, chưa tính tác vụ quản trị, migration, công cụ giám sát và dịch vụ khác. Không chọn pool size bằng số luồng HTTP một cách máy móc; pool quá lớn có thể làm DBMS quá tải do nhiều truy vấn song song.

Phần lớn pool triển khai cơ chế xử lý connection hỏng. Tuy nhiên, nếu ứng dụng giữ connection trong thời gian dài, quên đóng `ResultSet` hoặc chạy transaction quá lâu, pool sẽ cạn dù cấu hình kết nối đúng.

## 10. Lỗi thường gặp khi lấy kết nối qua `DataSource`

| Biểu hiện | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Không kết nối được database | Sai URL, host, port, TLS, tài khoản, hoặc DBMS không hoạt động | Kiểm tra cấu hình nguồn, network và quyền |
| Lỗi thiếu driver | Thư viện JDBC driver không có trên runtime classpath | Thêm đúng driver cho DBMS và Java runtime |
| Chờ lấy connection rồi timeout | Pool hết connection rảnh, transaction quá lâu hoặc connection leak | Giám sát active/idle/waiting, giới hạn thời gian xử lý và đóng connection |
| Số connection phía DBMS tăng bất thường | Tạo pool mới cho mỗi request hoặc mỗi repository | Tạo một nguồn/pool theo lifecycle ứng dụng rồi tái sử dụng |
| Query lỗi sau khi request kết thúc | `Connection` hoặc `ResultSet` đã đóng; dùng tài nguyên quá phạm vi | Đọc hết kết quả và xử lý trong `try-with-resources` |
| Dữ liệu không đồng nhất giữa hai cập nhật | Mỗi thao tác lấy connection riêng, không có transaction chung | Sử dụng cùng `Connection` hoặc transaction manager |
| Transaction của framework không bao gồm truy vấn | Lấy connection trực tiếp ngoài cơ chế transaction của framework | Dùng API truy cập dữ liệu/connection phù hợp với transaction manager |
| Kết nối gặp trạng thái bất ngờ | Trả connection về pool khi autocommit/isolation/session bị thay đổi | Đặt ranh giới transaction rõ ràng, reset trạng thái theo cơ chế pool/framework |
| Thay driver rồi lỗi kiểu dữ liệu | Khác biệt SQL dialect, driver hoặc DBMS | Kiểm thử các thao tác và kiểu dữ liệu trên driver đích |

Để chẩn đoán, xem `SQLException.getSQLState()`, mã lỗi vendor, log pool, số connection đang dùng và câu truy vấn đang chạy lâu ở phía DBMS. Không ghi mật khẩu hoặc dữ liệu nhạy cảm vào log.

## 11. Những nguyên tắc thực hành cần nhớ

1. **Tạo `DataSource` tại nơi quản lý cấu hình**, sau đó truyền nó tới các repository/DAO; tránh tạo pool liên tục trong từng request.
2. **Mượn connection muộn, trả sớm**, nhưng giữ cùng connection trong toàn bộ transaction cần tính nguyên tử.
3. **Luôn đóng `Connection`, `PreparedStatement` và `ResultSet` đúng phạm vi**. Với pool, `close()` thường là hành động trả connection về nguồn.
4. **Không chia sẻ một `Connection` cho các request đồng thời**. Bản thân nguồn `DataSource`/pool được thiết kế để cấp phát connection cho các công việc độc lập.
5. **Bảo vệ cấu hình kết nối** bằng biến môi trường hoặc kho bí mật phù hợp; tránh đặt mật khẩu trong mã nguồn.
6. **Kiểm tra giới hạn của DBMS trước khi tăng pool size**. Theo dõi thời gian chờ, active connections và thời gian transaction.
7. **Phân biệt tính năng chuẩn với phần triển khai**: `javax.sql.DataSource` và `getConnection()` là API JDBC; `PGSimpleDataSource`, `HikariDataSource` và cấu hình đặc thù thuộc thư viện hoặc driver.

## 12. Câu hỏi tự luyện

**Câu 1.** Hai `DataSource` đều được truyền vào repository dưới cùng interface. Một nguồn là `PGSimpleDataSource`, một nguồn là `HikariDataSource`. Hai nguồn có nhất thiết cấp connection theo cùng cơ chế không?

*Trả lời:* Không. Interface giống nhau, nhưng `PGSimpleDataSource` thông thường mở kết nối vật lý khi được gọi; `HikariDataSource` có pool để mượn và tái sử dụng connection.

**Câu 2.** Tại sao gọi `Connection.close()` vẫn cần thiết khi đang dùng connection pool?

*Trả lời:* Vì ứng dụng phải trả connection logic về pool sau khi xong việc. Quên đóng khiến pool nghĩ connection vẫn đang được sử dụng và có thể hết tài nguyên cấp phát.

**Câu 3.** Một giao dịch cần cập nhật hai bảng. Có nên gọi `dataSource.getConnection()` riêng cho từng truy vấn rồi hy vọng `commit()` trên connection thứ hai áp dụng cho cả hai?

*Trả lời:* Không. Với transaction JDBC thủ công, các lệnh liên quan phải chạy trên **cùng `Connection`**; hoặc sử dụng đúng transaction manager của framework.

**Câu 4.** Ứng dụng có 4 instance, mỗi instance giới hạn 25 connection trong pool. Tổng số connection từ các pool này có thể đạt bao nhiêu?

*Trả lời:* Tối đa **100 connection** nếu tất cả pool đều mở đến giới hạn, chưa tính các client khác truy cập DBMS.

**Câu 5.** Vì sao `javax.sql.DataSource` và `com.zaxxer.hikari.HikariDataSource` không phải là hai tên gọi thay thế trực tiếp?

*Trả lời:* `DataSource` là interface JDBC chuẩn; `HikariDataSource` là lớp hiện thực sử dụng connection pool của thư viện HikariCP. Ứng dụng có thể khai báo biến kiểu `DataSource` nhận một đối tượng `HikariDataSource`.

## Ghi nhớ

**`DataSource` là điểm cấp phát `Connection` được chuẩn hóa của JDBC**, giúp mã truy cập dữ liệu tách khỏi chi tiết tạo kết nối. Một `DataSource` có thể không có pool, có pool hoặc được container quản lý; hành vi thực tế phụ thuộc đối tượng hiện thực và cấu hình. Trong ứng dụng, hãy quản lý vòng đời `DataSource` ở tầng hạ tầng, lấy `Connection` theo phạm vi công việc hoặc transaction, đóng tài nguyên chắc chắn và giám sát khả năng cấp phát của pool để tránh rò rỉ hoặc cạn kết nối.
