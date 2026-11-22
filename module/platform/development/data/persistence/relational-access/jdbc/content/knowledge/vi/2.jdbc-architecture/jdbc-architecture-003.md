# Vai trò của Driver và DriverManager

Trong **JDBC (Java Database Connectivity)** — API Java để truy cập cơ sở dữ liệu quan hệ — ứng dụng viết mã bằng các giao diện chung như `Connection`, `PreparedStatement` và `ResultSet`, còn một **JDBC driver** triển khai cách giao tiếp với cơ sở dữ liệu cụ thể. **`DriverManager`** là thành phần thuộc JDK giúp tìm driver phù hợp và yêu cầu driver tạo kết nối.

Bài học thuộc chương **Kiến trúc JDBC**. Mục tiêu là hiểu chính xác ai chịu trách nhiệm về việc gì, một lời gọi `DriverManager.getConnection(...)` được xử lý ra sao, cách driver được phát hiện, khi nào cần nạp driver thủ công, và vì sao ứng dụng máy chủ thường dùng `DataSource` thay cho lời gọi `DriverManager` trực tiếp.

## 1. Vị trí của Driver và DriverManager trong kiến trúc JDBC

~~~text
                  ỨNG DỤNG JAVA
                  ┌───────────────────────────────┐
                  │ DAO / Repository / Service    │
                  │ Dùng java.sql.*               │
                  └───────────────┬───────────────┘
                                  │ getConnection(url, ...)
                                  ▼
                      ┌───────────────────────┐
                      │ java.sql.DriverManager│
                      │ Tìm driver phù hợp    │
                      └────────────┬──────────┘
                                   │ gọi Driver.connect(...)
                ┌──────────────────┼──────────────────┐
                ▼                  ▼                  ▼
       ┌────────────────┐ ┌────────────────┐ ┌────────────────┐
       │ JDBC Driver A  │ │ JDBC Driver B  │ │ JDBC Driver C  │
       │ do nhà cung cấp│ │ do nhà cung cấp│ │ do nhà cung cấp│
       │ DB triển khai  │ │ DB triển khai  │ │ DB triển khai  │
       └────────┬───────┘ └────────┬───────┘ └────────┬───────┘
                │                  │                  │
                ▼                  ▼                  ▼
             Database A         Database B         Database C

Sau khi có Connection:
Ứng dụng → Connection → PreparedStatement → ResultSet
                   (driver triển khai giao thức với DB)
~~~

Ba vai trò cần phân biệt:

- **JDBC API**: các hợp đồng chuẩn trong `java.sql` và `javax.sql`, chẳng hạn `Connection` và `Driver`. Nhờ hợp đồng chung, mã truy vấn cơ bản có thể ít phụ thuộc vào nhà cung cấp DB.
- **Driver**: mã thư viện của nhà cung cấp cơ sở dữ liệu (hoặc bên thứ ba) triển khai `java.sql.Driver` và các đối tượng JDBC liên quan. Nó hiểu URL/giao thức riêng, thiết lập kết nối và trao đổi với DB.
- **DriverManager**: lớp tiện ích có các phương thức tĩnh để quản lý các driver đã đăng ký/khả dụng và chọn driver khi ứng dụng yêu cầu kết nối. Nó **không phải** chính driver, cũng không trực tiếp thực thi SQL.

Ví dụ, lời gọi `statement.executeQuery(...)` được thực hiện trên một `Statement` do driver cung cấp thông qua `Connection`. `DriverManager` không xuất hiện trong đường gọi thực thi câu SQL đó.

## 2. Driver là gì? Hợp đồng `java.sql.Driver`

`java.sql.Driver` là **interface**. Một JDBC driver thực tế thường nằm trong thư viện JAR riêng, được thêm vào runtime classpath hoặc module path của ứng dụng.

Các phương thức đáng chú ý:

| Phương thức của `Driver` | Ý nghĩa |
| --- | --- |
| `connect(String url, Properties info)` | Thử thiết lập `Connection` theo URL và thuộc tính được cung cấp; có thể trả `null` nếu driver không nhận URL |
| `acceptsURL(String url)` | Kiểm tra driver có nhận diện kiểu JDBC URL đó hay không |
| `getPropertyInfo(String url, Properties info)` | Mô tả các thuộc tính cấu hình kết nối driver hỗ trợ |
| `getMajorVersion()` / `getMinorVersion()` | Thông tin phiên bản của driver |
| `jdbcCompliant()` | Cho biết driver tự báo có tuân thủ các yêu cầu JDBC compliance tương ứng hay không |
| `getParentLogger()` | Lấy logger cha theo hợp đồng JDBC, hoặc báo không hỗ trợ tính năng này |

Điểm quan trọng trong `Driver.connect(...)`: nếu URL **không thuộc loại driver xử lý**, driver phải trả về `null` để bộ quản lý có thể thử driver khác. Nếu URL thuộc loại được nhận diện nhưng quá trình kết nối thất bại, driver có thể ném `SQLException`. Không nên hiểu mọi giá trị `null` hoặc mọi `SQLException` là lỗi “thiếu driver” giống nhau.

Driver còn cung cấp các lớp triển khai cụ thể của `Connection`, `Statement`, `ResultSet` và các thành phần khác. Ứng dụng thường chỉ giữ biến theo các **giao diện JDBC chuẩn** để tránh phụ thuộc vào tên lớp triển khai của driver.

### Một hệ thống có thể có nhiều driver

Ứng dụng có thể đưa nhiều JDBC driver vào runtime, ví dụ một driver cho PostgreSQL và một driver cho MySQL. Cả hai cùng thực thi `java.sql.Driver` nhưng nhận diện kiểu URL khác nhau:

~~~text
jdbc:postgresql://localhost:5432/shop
jdbc:mysql://localhost:3306/shop
~~~

Các URL trên chỉ để minh họa; máy chủ, cơ sở dữ liệu, thư viện driver, tài khoản và mạng phải phù hợp thì mới kết nối được. Chuỗi bắt đầu bằng `jdbc:`, sau đó có phần giao thức do driver quy định. **JDBC không áp đặt một cú pháp URL đầy đủ duy nhất cho mọi nhà cung cấp.**

## 3. DriverManager là gì? Những gì lớp này làm

`java.sql.DriverManager` là lớp của Java SE, cung cấp chủ yếu các **phương thức tĩnh**. Các thao tác thường gặp:

| API | Công dụng |
| --- | --- |
| `DriverManager.getConnection(url)` | Tìm driver phù hợp và yêu cầu mở kết nối bằng thông tin từ URL |
| `DriverManager.getConnection(url, user, password)` | Tương tự, kèm tên đăng nhập và mật khẩu |
| `DriverManager.getConnection(url, properties)` | Chuyển các thuộc tính kết nối cho driver |
| `DriverManager.getDriver(url)` | Tìm driver đã đăng ký có thể nhận diện URL theo khả năng hiển thị với caller |
| `DriverManager.getDrivers()` | Liệt kê các driver đã đăng ký mà caller có thể truy cập |
| `DriverManager.registerDriver(driver)` | Đăng ký một đối tượng driver với `DriverManager` |
| `DriverManager.deregisterDriver(driver)` | Bỏ đăng ký driver; cần thiết trong một số tình huống quản lý vòng đời class loader |
| `DriverManager.setLoginTimeout(seconds)` | Cấu hình giới hạn thời gian chờ khi cố thiết lập kết nối theo cơ chế DriverManager |

`DriverManager` **không** làm connection pool theo hợp đồng của nó. Mỗi lời gọi `getConnection(...)` yêu cầu tạo/lấy kết nối thông qua driver; không có cơ chế pool chuẩn tự động chỉ vì dùng `DriverManager`. Tương tự, `DriverManager` không quyết định schema SQL, không ánh xạ bản ghi thành đối tượng nghiệp vụ và không quản lý transaction của ứng dụng sau khi đã trả về `Connection`.

## 4. Điều gì xảy ra khi gọi `DriverManager.getConnection`?

Giả sử ứng dụng gọi:

~~~java
Connection connection = DriverManager.getConnection(
        "jdbc:postgresql://localhost:5432/shop",
        username,
        password
);
~~~

Về mặt khái niệm, đường đi là:

1. `DriverManager` xem những driver đã đăng ký và **được phép hiển thị** cho mã gọi, theo cơ chế class loader của Java.
2. Nó thử lần lượt những driver phù hợp thông qua cơ chế kết nối của `Driver`.
3. Một driver không nhận diện URL có thể trả `null` từ `connect(...)`; bộ quản lý tiếp tục thử driver khác.
4. Khi một driver trả về `Connection` không null, `DriverManager` trả kết nối đó cho ứng dụng.
5. Nếu không có driver nào tạo được kết nối, hoặc xảy ra lỗi kết nối, `getConnection(...)` ném `SQLException`. Thông điệp và SQLState cụ thể phụ thuộc trường hợp/driver.

Đây là **mô tả luồng chọn driver**, không phải cam kết rằng `DriverManager` nhất thiết gọi `acceptsURL(...)` trước mỗi lần gọi `connect(...)`. `acceptsURL(...)` là một API riêng để hỏi khả năng nhận URL; việc chọn kết nối của `DriverManager` dựa trên hợp đồng `Driver.connect(...)`.

~~~text
DriverManager.getConnection(url, props)
    │
    ├── thử Driver A.connect(url, props)
    │       └── trả null nếu không nhận URL
    │
    ├── thử Driver B.connect(url, props)
    │       └── trả Connection nếu kết nối thành công
    │
    └── trả Connection cho ứng dụng
             │
             ├── connection.prepareStatement(...)
             ├── statement.executeQuery()
             └── connection.close()
~~~

Nếu nhiều driver cùng nhận một loại URL, driver được thử trước có thể ảnh hưởng kết quả. Vì vậy, các hệ thống hỗ trợ nhiều nguồn dữ liệu nên quản lý cấu hình/driver rõ ràng thay vì dựa vào thứ tự đăng ký tình cờ.

## 5. Java phát hiện driver bằng cách nào?

### 5.1. Cơ chế tự phát hiện từ JDBC 4.0 (Java 6 trở lên)

Trong môi trường Java hiện đại, JDBC driver thường công bố một **service provider** để Java có thể phát hiện mà không cần gọi `Class.forName(...)` trong mã ứng dụng.

Ở cách đóng gói JAR truyền thống, nhà phát triển driver có thể cung cấp tệp:

~~~text
META-INF/services/java.sql.Driver
~~~

Nội dung là tên đầy đủ của lớp triển khai `Driver`, ví dụ:

~~~text
org.postgresql.Driver
~~~

Khi driver JAR thực sự có mặt và hiển thị ở runtime, hệ thống phát hiện service của Java/JDBC có thể nạp driver để `DriverManager` sử dụng. Các driver được đóng gói thành module có thể khai báo provider theo cơ chế Java Platform Module System tương ứng.

Điều kiện thực tế là **thư viện driver phải có trong môi trường chạy**. Việc chỉ khai báo import `java.sql.*` hoặc biên dịch thành công không tự đem mã driver của PostgreSQL, MySQL hay một DB cụ thể vào ứng dụng.

### 5.2. Vì sao các tài liệu cũ dùng `Class.forName`?

Bạn có thể gặp:

~~~java
// Kiểu nạp driver thủ công thường thấy trong ví dụ JDBC cũ:
Class.forName("org.postgresql.Driver");
~~~

Trước thời kỳ tự phát hiện driver phổ biến, việc nạp lớp driver có thể kích hoạt mã khởi tạo của nó để tự đăng ký với `DriverManager`. Với driver JDBC hiện đại được đóng gói đúng, **thường không cần** dòng này.

`Class.forName(...)` vẫn có thể hữu ích cho trường hợp legacy, driver không có provider metadata hoặc môi trường class loader đặc biệt. Tuy nhiên, nó **không sửa được** tình trạng thiếu driver JAR ở runtime, và không nên được thêm như một “phép thử” thay cho kiểm tra dependency.

> **Phân biệt:** “JDBC driver được tự phát hiện” chỉ nói rằng ứng dụng không phải chủ động gọi tên lớp driver trong trường hợp thông dụng. Nó không có nghĩa Java SE đã tích hợp sẵn driver cho tất cả hệ quản trị cơ sở dữ liệu.

### 5.3. Đăng ký và bỏ đăng ký

Một số driver hoặc thành phần hạ tầng có thể sử dụng:

~~~java
DriverManager.registerDriver(myDriver);
// ... sau đó, khi chủ sở hữu driver kết thúc vòng đời:
DriverManager.deregisterDriver(myDriver);
~~~

Trong ví dụ, `myDriver` là một đối tượng đã triển khai `java.sql.Driver`. Đăng ký thủ công thường là công việc của thư viện/driver hoặc môi trường tích hợp, **không phải** thao tác mỗi repository cần làm khi khởi tạo.

Trong máy chủ ứng dụng có nhiều class loader và hỗ trợ triển khai lại module (redeploy), một driver vẫn được đăng ký sau khi module hết vòng đời có thể góp phần giữ tham chiếu đến class loader cũ. Việc hủy đăng ký đúng lúc đôi khi cần thiết, nhưng phải thuộc trách nhiệm của thành phần sở hữu driver/class loader, không tùy tiện hủy driver dùng chung bởi thành phần khác.

## 6. Ví dụ dùng DriverManager để truy vấn an toàn

Ví dụ sau dùng JDBC chuẩn; giả định đã cấu hình driver, cơ sở dữ liệu và bảng `products(id, name)`. Chạy ứng dụng với các biến môi trường `JDBC_URL`, `DB_USER`, `DB_PASSWORD` phù hợp.

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class JdbcDriverManagerDemo {

    public static void main(String[] args) throws SQLException {
        String url = requiredEnv("JDBC_URL");
        String user = requiredEnv("DB_USER");
        String password = requiredEnv("DB_PASSWORD");

        String sql = "SELECT id, name FROM products WHERE id = ?";

        // DriverManager chọn driver; driver tạo đối tượng Connection.
        try (Connection connection =
                     DriverManager.getConnection(url, user, password);
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            // Dùng tham số, không nối trực tiếp đầu vào vào SQL.
            statement.setLong(1, 42L);

            // Statement của driver trả về ResultSet của driver.
            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    long id = rows.getLong("id");
                    String name = rows.getString("name");
                    System.out.println(id + " - " + name);
                }
            }
        } // Đóng ResultSet, PreparedStatement, rồi Connection.
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "Missing environment variable: " + name);
        }
        return value;
    }
}
~~~

*Ví dụ dùng `String.isBlank()` (Java 11 trở lên), và bảng `products` chỉ là minh họa. Không cần import lớp driver cụ thể trong mã trên; driver tương thích vẫn phải được cung cấp ở runtime.*

Ở đây, mỗi thành phần thực hiện đúng trách nhiệm:

- **Ứng dụng** chọn URL, SQL, tham số, cách duyệt kết quả và thời điểm đóng tài nguyên.
- **`DriverManager`** tìm driver phù hợp cho URL và yêu cầu kết nối.
- **Driver** thiết lập giao tiếp với DB, tạo `Connection` và các đối tượng JDBC phục vụ thực thi SQL.
- **`try-with-resources`** đóng tài nguyên theo thứ tự ngược lúc khai báo, kể cả khi phát sinh `SQLException`. Mã nguồn không cần tự gọi `DriverManager.deregisterDriver(...)` sau mỗi kết nối.

Khi chuyển sang hệ quản trị khác, phần dùng `Connection`, `PreparedStatement` và `ResultSet` có thể giữ cách viết tương tự. Tuy nhiên, JDBC **không bảo đảm SQL dialect, kiểu dữ liệu, tính năng sinh khóa hay hành vi transaction hoàn toàn giống nhau** giữa mọi DB; cần kiểm tra và điều chỉnh khi chuyển hệ.

## 7. Dùng Properties khi cần truyền thuộc tính driver

Ngoài overload dùng username/password, có thể truyền các thuộc tính kết nối qua `Properties`:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Properties;

// url, username, password được lấy từ cấu hình an toàn.
Properties properties = new Properties();
properties.setProperty("user", username);
properties.setProperty("password", password);

try (Connection connection =
             DriverManager.getConnection(url, properties)) {
    System.out.println("Connected: " + !connection.isClosed());
}
~~~

Các khóa `user` và `password` là quy ước thông dụng. Những khóa như cấu hình SSL, connect timeout, socket timeout, application name, encoding... **phụ thuộc driver và tài liệu nhà cung cấp**. Không giả định rằng một thuộc tính đặt được qua driver A sẽ có cùng tên/đơn vị/hành vi với driver B.

Tránh in toàn bộ `Properties` hoặc JDBC URL khi chúng có thể chứa mật khẩu/token. `Properties` không tự che dữ liệu bí mật trong log.

## 8. Kiểm tra driver nào đang khả dụng

Khi debug lỗi “không tìm thấy driver”, có thể liệt kê các driver mà `DriverManager` nhìn thấy từ mã đang chạy:

~~~java
import java.sql.Driver;
import java.sql.DriverManager;
import java.util.Enumeration;

Enumeration<Driver> drivers = DriverManager.getDrivers();

while (drivers.hasMoreElements()) {
    Driver driver = drivers.nextElement();
    System.out.println(
            driver.getClass().getName()
            + " (version "
            + driver.getMajorVersion()
            + "."
            + driver.getMinorVersion()
            + ")"
    );
}
~~~

`getDrivers()` liệt kê các driver **đã đăng ký và được phép hiển thị cho caller**. Do vậy, nếu thiếu driver trong danh sách, nguyên nhân có thể là thiếu dependency runtime, sai cấu hình provider hoặc giới hạn class loader. Đây là thông tin chẩn đoán; không nên sử dụng việc liệt kê driver ở mỗi request nghiệp vụ.

Có thể kiểm tra driver nhận URL:

~~~java
import java.sql.Driver;
import java.sql.DriverManager;
import java.sql.SQLException;

String jdbcUrl = "jdbc:postgresql://localhost:5432/shop";

try {
    Driver driver = DriverManager.getDriver(jdbcUrl);
    System.out.println("Driver: " + driver.getClass().getName());
} catch (SQLException error) {
    System.err.println("No visible driver for URL: " + error.getMessage());
}
~~~

Tìm được một driver nhận URL **không chứng minh** DB đã hoạt động, tài khoản hợp lệ hay mạng thông suốt. `getDriver(url)` kiểm tra khả năng nhận diện URL chứ không mở một kết nối.

## 9. So sánh DriverManager và DataSource

`DriverManager` là một cách trực tiếp để lấy `Connection`. Trong ứng dụng chạy lâu, nhất là server có nhiều yêu cầu đồng thời, thông thường dùng **`javax.sql.DataSource`**.

| Tiêu chí | `DriverManager` | `DataSource` |
| --- | --- | --- |
| Lấy kết nối | Gọi phương thức tĩnh `getConnection(...)` | Gọi `dataSource.getConnection()` trên đối tượng cấu hình/inject |
| Nguồn cấu hình | Truyền URL, credentials và properties mỗi lần hoặc qua lớp tiện ích | Cấu hình tập trung trong một đối tượng |
| Connection pool | Không cung cấp pool theo hợp đồng chuẩn | Có thể được triển khai bằng pool, ví dụ HikariCP; interface `DataSource` tự nó không bắt buộc pooling |
| Dùng trong thử nghiệm/CLI nhỏ | Dễ bắt đầu | Có thể không cần |
| Dùng trong ứng dụng server | Cần tự quản lý cấu hình và vòng đời | Thường thuận tiện hơn cho DI, pool, quan sát hoạt động và vận hành |
| Thực thi SQL | Trả `Connection` để dùng JDBC API | Cũng trả `Connection` để dùng JDBC API |

Ví dụ ở lớp repository nhận sẵn một `DataSource`:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class ProductRepository {
    private final DataSource dataSource;

    public ProductRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public String findName(long id) throws SQLException {
        String sql = "SELECT name FROM products WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setLong(1, id);

            try (ResultSet rows = statement.executeQuery()) {
                return rows.next() ? rows.getString("name") : null;
            }
        }
    }
}
~~~

`ProductRepository` không cần biết driver được tìm bằng cách nào hoặc pool được tạo ra sao. Tầng cấu hình ứng dụng cung cấp một `DataSource` phù hợp; repository chỉ sử dụng `Connection`. Với `DataSource` có pool, gọi `connection.close()` thường trả kết nối logic về pool; ứng dụng vẫn cần **đóng kết nối** tại ranh giới sở hữu của mỗi thao tác.

Không nhầm `DriverManager` với `DataSource`: cả hai đều dẫn đến `Connection`, nhưng chúng là **hai API khởi tạo/lấy kết nối khác nhau**. Một `DataSource` do driver cung cấp có thể tạo kết nối trực tiếp, còn một pool `DataSource` dùng driver/hạ tầng kết nối phía dưới để quản lý tái sử dụng.

## 10. Phân biệt ba nhóm lỗi phổ biến

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `No suitable driver found for jdbc:...` | Thiếu driver ở runtime, URL không đúng loại, provider không được phát hiện, driver bị ẩn bởi class loader | Kiểm tra dependency, tên URL, `DriverManager.getDrivers()`, cách đóng gói/chạy ứng dụng |
| Driver phù hợp nhưng `getConnection(...)` lỗi | DB không chạy, DNS/mạng, sai tài khoản, sai tên database, TLS, timeout... | Xem `SQLException`, SQLState, vendor code, log driver/DB và kết nối mạng |
| Đã có `Connection` nhưng SQL thất bại | SQL sai, bảng/cột không tồn tại, thiếu quyền, vi phạm ràng buộc, deadlock, timeout truy vấn | Kiểm tra câu SQL, quyền/schema, transaction và lỗi trả từ driver |

Ví dụ xử lý và ghi thông tin lỗi có cấu trúc:

~~~java
try (Connection connection =
             DriverManager.getConnection(url, user, password)) {
    // Sử dụng connection.
} catch (SQLException error) {
    System.err.println("SQLState: " + error.getSQLState());
    System.err.println("Vendor error code: " + error.getErrorCode());
    System.err.println("Message: " + error.getMessage());
}
~~~

Thông điệp `SQLException` có thể chứa thông tin hạ tầng; khi đưa vào log tập trung cần tránh lộ dữ liệu kết nối nhạy cảm. `DriverManager.setLoginTimeout(...)` quản lý giới hạn của giai đoạn mở kết nối qua DriverManager, **không** tương đương với `Statement.setQueryTimeout(...)`, vốn giới hạn thời gian thực thi câu lệnh. Trong hệ thống pool, timeout **mượn connection** thường còn là một giới hạn riêng.

### Những sai lầm hay gặp

- Gọi `Class.forName(...)` rồi tin rằng đã đủ cấu hình: JAR vẫn phải có trong runtime, URL và thông tin kết nối phải chính xác.
- Cho rằng `DriverManager` tự quản lý pool hoặc tự đóng `Connection` sau một câu lệnh: ứng dụng phải đóng đúng vòng đời, tốt nhất qua `try-with-resources`.
- Nối chuỗi đầu vào người dùng vào SQL: dùng `PreparedStatement` và tham số `?`, không dựa vào DriverManager để ngăn SQL injection.
- Giữ một `Connection` toàn cục rồi chia sẻ cho nhiều luồng: vòng đời, transaction và hỗ trợ concurrent access phải được thiết kế rõ; trong server, nên cho từng thao tác mượn kết nối từ `DataSource`.
- Nhầm lỗi thiếu driver với lỗi DB không phản hồi: lần lượt kiểm tra driver hiện diện, URL được nhận diện và việc thiết lập kết nối vật lý.

## 11. Tự kiểm tra

**Câu 1.** Vì sao cùng đoạn Java dùng `Connection` và `PreparedStatement` có thể chạy với nhiều hệ quản trị?

Vì ứng dụng lập trình theo **giao diện JDBC chung**. Mỗi driver triển khai cách giao tiếp với DB của mình. Dù vậy, SQL dialect và các tính năng vendor-specific vẫn có thể cần thay đổi.

**Câu 2.** `DriverManager.getConnection(...)` có chạy SQL để trả một `ResultSet` không?

Không. Nó tìm driver và yêu cầu một `Connection`. Ứng dụng tạo `Statement` hoặc `PreparedStatement` từ kết nối rồi thực thi SQL.

**Câu 3.** Trong Java hiện đại, bắt buộc gọi `Class.forName("...Driver")` trước khi kết nối?

Không, nếu JDBC driver được đóng gói và phát hiện đúng qua cơ chế service provider. Vẫn phải có thư viện driver ở runtime; một số môi trường legacy/class loader đặc biệt có thể cần xử lý riêng.

**Câu 4.** Vì sao `getDriver(url)` thành công mà `getConnection(url, ...)` vẫn thất bại?

Vì nhận diện URL khác với thiết lập kết nối thực tế. Máy chủ DB, mạng, credentials, TLS hoặc cấu hình có thể sai.

**Câu 5.** Dùng `DataSource` có đồng nghĩa chắc chắn có connection pool?

Không. `DataSource` là interface cho việc lấy kết nối; chỉ một số triển khai có cơ chế pooling. HikariCP là ví dụ của thư viện cung cấp pool.

**Điểm cần nhớ:** `Driver` triển khai giao thức làm việc với hệ quản trị cơ sở dữ liệu; `DriverManager` tìm driver thích hợp và xin `Connection`; ứng dụng sử dụng các giao diện JDBC để thực thi SQL và đóng tài nguyên. Với Java hiện đại, driver thường được phát hiện tự động nếu JAR và metadata được đóng gói đúng; trong ứng dụng server, `DataSource` là điểm cấu hình kết nối thường phù hợp hơn.
