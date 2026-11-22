# DriverManager, DataSource và nơi quản lý cấu hình kết nối JDBC trong Java

## 1. Vấn đề thiết kế: mở kết nối và quản lý cấu hình là hai nhiệm vụ khác nhau

Trong Java 17+, JDBC cung cấp các giao diện tiêu chuẩn để ứng dụng thực thi SQL qua `java.sql.Connection`. Hai con đường thường gặp để lấy một connection là:

- **`java.sql.DriverManager.getConnection(...)`:** nhận JDBC URL, user/credential và yêu cầu một JDBC driver đã đăng ký tạo kết nối. Đây là API **static**.
- **`javax.sql.DataSource.getConnection()`:** ứng dụng gọi lên **một đối tượng nhà máy kết nối đã được cấu hình trước**. DataSource là **interface**, không phải một class driver cụ thể.

Theo Javadoc Java SE 25, **`DataSource` là cách được ưu tiên** khi ứng dụng cần lấy kết nối database. `DriverManager` vẫn còn hợp lệ, **không deprecated**, rất phù hợp trong ứng dụng nhỏ, công cụ một lần hoặc bên trong một lớp hạ tầng.

Các câu hỏi về **cấu hình và vận hành** không được giải quyết chỉ bằng việc đổi tên API:

1. JDBC URL, host, port, database, user, secret và TLS settings được lấy từ đâu?
2. Ai tạo DataSource/connection pool và sở hữu vòng đời của nó?
3. Repository có được phép tự đọc `System.getenv`, tự quyết định URL và tạo pool mỗi request không?
4. Ai chịu trách nhiệm close Connection? Ai đóng pool khi ứng dụng ngừng chạy?
5. Login timeout, pool acquisition timeout, network timeout và query timeout khác nhau thế nào?
6. Làm sao kiểm thử logic không cần database, nhưng vẫn có integration test với driver/database thật?

**Nguyên tắc thực hành:** Tạo và cấu hình `DataSource` tại **application bootstrap/composition root** hoặc framework/container; inject nó vào code nghiệp vụ. Mỗi request hoặc đơn vị transaction mượn `Connection` rồi đóng bằng `try-with-resources`. Owner của connection pool quản lý pooling, secrets, reload/rotation và shutdown.

## 2. So sánh chính xác `DriverManager` và `DataSource`

| Thuộc tính | `DriverManager` | `DataSource` |
| --- | --- | --- |
| Java API | `java.sql.DriverManager` | `javax.sql.DataSource`, thuộc module `java.sql` |
| Bản chất | Static class quản lý các JDBC drivers | Interface mô tả factory cung cấp `Connection` |
| Mã gọi phổ biến | `DriverManager.getConnection(url, user, password)` | `dataSource.getConnection()` |
| Cấu hình | Được truyền vào từng lời gọi hoặc được một factory/facade đóng gói | Gắn với instance DataSource đã cấu hình trước |
| Chọn driver | DriverManager chọn trong các `java.sql.Driver` đã có | Vendor DataSource, pool hoặc container chọn cách tạo connection |
| Pooling mặc định | **Không có** connection pool chuẩn do DriverManager tự cung cấp | **Không được bảo đảm bởi interface**; có thể được pool implementation cung cấp |
| Code phụ thuộc cụ thể | Dễ làm business code biết URL/user nếu gọi trực tiếp | Repository chỉ phụ thuộc interface và được inject |
| Thay config môi trường | Cần quản lý ở nơi tạo arguments | Cấu hình ở bootstrap; repository dùng cùng hợp đồng |
| Đời sống | `Connection` do caller đóng | `Connection` do caller đóng; pool owner đóng pool nếu pool hỗ trợ |
| Dùng khi nào? | CLI, migration tool, smoke test, demo, lớp thấp của hạ tầng | Ứng dụng server, jobs, nhiều repositories, quản lý cấu hình lâu dài |
| Thử nghiệm | Có thể fake nhưng static calls cần wrapper | Dễ inject fake/real DataSource trong tests |

**`javax.sql.DataSource` vẫn là tên chuẩn trên Java SE hiện đại**: không phải `jakarta.sql.DataSource`. Dù dùng Jakarta EE hoặc framework mới, JDBC interface này vẫn thuộc module `java.sql` của JDK.

### Dòng chảy kết nối

~~~text
Nhánh DriverManager:
    Application/CLI
       -> DriverManager.getConnection(url, credentials)
          -> Chọn JDBC Driver phù hợp
             -> Connection

Nhánh DataSource:
    Config/Secrets -> Bootstrap/DI/Container
                         -> Tạo và giữ DataSource/Pool
                            -> Inject vào Repository
                               -> dataSource.getConnection()
                                  -> JDBC work
                                     -> connection.close()
                                        -> nếu pooled: trả về pool
~~~

**`DataSource` không tự động là pool.** Một DataSource basic có thể mở connection vật lý mới mỗi lần. Một DataSource có pooling trả logical connection được quản lý bởi pool/driver; close thường đánh dấu kết thúc lượt mượn và trả kết nối về pool.

## 3. Sử dụng `DriverManager` đúng cách

Trong một utility nhỏ, bạn có thể dùng:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

public final class ConnectionCheck {
    public static void main(String[] args) throws SQLException {
        String url = System.getenv("DB_URL");
        String user = System.getenv("DB_USER");
        String password = System.getenv("DB_PASSWORD");
        if (url == null || user == null || password == null) {
            throw new IllegalStateException("Thiếu cấu hình kết nối");
        }

        try (Connection c = DriverManager.getConnection(url, user, password)) {
            System.out.println("Connection established: " + !c.isClosed());
        }
    }
}
~~~

Đây là **file Java biên dịch được**, nhưng việc **chạy thành công cần JDBC driver JAR thật**, database endpoint, DB credentials và environment variables hợp lệ. Ví dụ không có stdout cố định vì phụ thuộc môi trường. Đặt password trong secret manager hoặc cơ chế cung cấp environment secrets của platform; mã ví dụ **không chứa secret thật** và không log secret.

### Driver JDBC được nạp như thế nào?

JDBC 4+ có **service-provider mechanism**. Một JDBC driver hiện đại thường đóng gói service descriptor `META-INF/services/java.sql.Driver` trong JAR; `DriverManager` có thể khám phá driver nhờ `ServiceLoader` khi driver hiện diện trong loading context thích hợp. Do đó lời khuyên “bất cứ ứng dụng JDBC nào cũng bắt buộc phải gọi `Class.forName("vendor.Driver")`” là lỗi thời đối với phần lớn driver hiện hành.

Tuy nhiên, **auto-discovery không thể thay dependency**. Nếu thiếu driver artifact ở runtime, hoặc class/module loader không nhìn thấy driver, việc truyền đúng `jdbc:...` URL vẫn không mở được kết nối.

Javadoc còn lưu ý việc `DriverManager` khởi tạo **lazy** và quá trình khám phá driver phụ thuộc classloader context khi khởi tạo. Với application servers và plugin classloaders, cần quản lý visibility và lifecycle. Một driver tự đăng ký vào `DriverManager` có thể cần được deregister đúng lúc khi hot-unload plugin để tránh giữ tham chiếu classloader; không deregister driver mà request khác vẫn dùng.

### Các overload và credentials

~~~java
Connection c1 = DriverManager.getConnection(url, user, password);

Properties properties = new Properties();
properties.setProperty("user", user);
properties.setProperty("password", password);
Connection c2 = DriverManager.getConnection(url, properties);
~~~

Đây là đoạn **minh họa trong method** với `url`, `user`, `password` đã có, cần import `Properties`, `Connection` và xử lý `SQLException`. Phải đóng `c1` và `c2` trong ứng dụng thật, ưu tiên try-with-resources.

**Không đặt `user/password` cả trong URL lẫn trong `Properties`**: theo Javadoc `DriverManager`, thứ tự ưu tiên nếu một property bị truyền hai lần là **implementation-defined**. Tránh đưa secret vào URL/command line nếu driver có hỗ trợ credentials riêng, vì URL rất dễ bị log, in ra exception hoặc metrics.

## 4. `DataSource` là contract cho repository và service

Các phương thức quan trọng của interface:

~~~java
Connection getConnection() throws SQLException;
Connection getConnection(String username, String password) throws SQLException;
~~~

Một repository dùng constructor injection:

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;

public final class ItemRepository {
    private final DataSource source;

    public ItemRepository(DataSource source) {
        this.source = source;
    }

    public Optional<String> findTitle(long id) throws SQLException {
        String sql = "SELECT title FROM items WHERE id = ?";
        try (Connection connection = source.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);
            try (ResultSet rows = statement.executeQuery()) {
                return rows.next()
                        ? Optional.ofNullable(rows.getString(1))
                        : Optional.empty();
            }
        }
    }
}
~~~

Class này **biên dịch trên Java 17**, nhưng chạy SQL đòi hỏi bảng `items` và DataSource của database thật. Mục đích là minh họa dependency inversion: repository **không cần biết** JDBC URL, password, driver class, pool size hay cloud region. `PreparedStatement` dùng parameter `?` thay vì ghép giá trị input vào SQL.

Khi đổi DB vendor, code repository vẫn có thể cần sửa SQL dialect hoặc schema; **DataSource không tự làm SQL portable hoàn toàn**.

### Ba nhóm triển khai được Javadoc nêu

1. **Basic DataSource:** cấp một `Connection` thông thường.
2. **Pooling-capable DataSource:** cấp logical connections tham gia pool do middle-tier/connection-pool manager quản lý.
3. **Distributed transaction DataSource:** tích hợp transaction manager phân tán, thường cũng dùng pooling.

Có những interface bổ sung như `ConnectionPoolDataSource` và `XADataSource` để hạ tầng kết nối/giao dịch tương tác với driver, nhưng repository đa phần vẫn chỉ cần `DataSource`.

**`DataSource` không kế thừa `AutoCloseable`**, không có method `close()` trong interface. Pool implementation như HikariDataSource có thể có `close()`; chỉ bootstrap/container là nơi quản lý đóng pool theo lifecycle. Đừng gọi close pool ở mỗi repository request.

## 5. Nơi quản lý cấu hình: bootstrap/composition root

Một thiết kế dễ quản lý:

~~~text
       Deployment config / Secret Manager
             |
             v
    DbSettings đã validate một lần
             |
             v
      Application bootstrap / DI
             |
             v
    Vendor DataSource hoặc Pool
             |
             +---- ItemRepository
             +---- InvoiceRepository
             +---- ReportingJob
                     |
                     v
             JDBC Connection mượn ngắn hạn
~~~

**Composition root** là điểm khởi tạo application graph: đọc config, truy xuất secrets, validate options, tạo DataSource, inject vào services, đăng ký cleanup. Nó có thể là một `main` Java SE, một bean/framework startup, hoặc resource configuration của application server.

### Thông tin cấu hình nên ở đâu?

| Loại thông tin | Nơi quản lý ưu tiên |
| --- | --- |
| JDBC URL, host, DB name, port | Deployment config / environment-specific config / config service |
| Username, password, access token, DB certificate private key | Secret manager / secret provisioning với phân quyền rõ |
| TLS mode, trust store, certificate verification | Deployment security configuration, được audit |
| Pool maximum size, minimum idle, max lifetime | App bootstrap/framework pool configuration |
| Pool acquisition timeout, connection/login timeout, socket timeout | Config tập trung, đặt đúng cấp driver/pool |
| Tên resource JNDI hoặc DataSource bean | Application/container configuration |
| Schema migrations | Quy trình triển khai riêng, theo version và DB role có quyền thích hợp |
| Metrics, connection validation query/strategy | Monitoring/health configuration |

Không để từng repository gọi `System.getenv("DB_URL")` rồi tự tạo driver/pool trong mỗi method. Điều đó khiến đổi environment khó, test khó, thông tin bí mật rải rác và dễ phát sinh nhiều pools ngoài ý muốn.

### Typed config ở điểm khởi tạo

~~~java
import java.util.Objects;

record DbSettings(String url, String user, String password) {
    DbSettings {
        Objects.requireNonNull(url);
        Objects.requireNonNull(user);
        Objects.requireNonNull(password);
        if (!url.startsWith("jdbc:")) {
            throw new IllegalArgumentException("DB_URL phải là JDBC URL");
        }
    }

    static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu cấu hình " + key);
        }
        return value;
    }

    static DbSettings load() {
        return new DbSettings(
                requiredEnv("DB_URL"),
                requiredEnv("DB_USER"),
                requiredEnv("DB_PASSWORD"));
    }
}
~~~

Đây là **record cần đặt trong file Java thích hợp**; không chứa `main` độc lập. Kiểm tra prefix `jdbc:` chỉ là validation đơn giản. Production phải validate **host/database nằm trong allowlist/môi trường được phép**, TLS options, driver-specific connection parameters và DB role. Nếu hệ thống dùng identity-based authentication không có password, cấu trúc record phải điều chỉnh đúng giao thức đó.

**Environment variables không tự biến thành kho bí mật an toàn.** Chúng có thể bị lộ qua deployment manifests, process debugging, support dumps hoặc cấu hình logs nếu quyền truy cập bị sai. Ưu tiên secrets API và access control của nền tảng, cấp secrets tại điểm khởi tạo, không log `DbSettings` khi chứa password. Nếu rotate credentials, cần policy refresh/drain/recreate pool và physical connections; sửa một giá trị environment giữa runtime không bảo đảm pool tự cập nhật.

### JNDI/DI và môi trường app server

Một DataSource do application server cấp có thể được tra theo JNDI:

~~~java
import javax.naming.InitialContext;
import javax.sql.DataSource;

DataSource source = (DataSource) new InitialContext()
        .lookup("java:comp/env/jdbc/AppDb");
~~~

Đoạn này **chỉ minh họa trong một method**, cần xử lý `NamingException` và container phải cấu hình tên `java:comp/env/jdbc/AppDb`. Một ứng dụng standalone không tự có JNDI resource ấy. Ngoài JNDI, Spring, Micronaut, Quarkus và các DI container có thể tạo/inject DataSource theo cấu hình riêng; code repository vẫn giữ constructor nhận `DataSource`.

**Owner quan trọng:** Nếu container quản lý pool, ứng dụng thường **không** tự đóng pool đó ngoài lifecycle của container. Nếu ứng dụng tự tạo pool, chính bootstrap phải đăng ký close khi shutdown và tránh tạo pool ở scope request.

## 6. Chương trình Java 17+ hoàn chỉnh, không cần database thật

Ví dụ này tách hai cách cấp connection bằng một **fake JDBC driver** có thể biên dịch và chạy với **JDK thuần**, không mở socket và **không thể chạy SQL thực**. Nó minh họa interface, cách truyền cấu hình, đóng connection và việc `DataSource` không mặc định pool.

`DriverManager` được đăng ký `DemoDriver` để phục vụ một lần `getConnection`. `ConfiguredDataSource` là DataSource **basic**, lưu config và gọi `Driver.connect` trực tiếp (không đi qua DriverManager); nhờ vậy thấy DataSource interface không bắt buộc phụ thuộc DriverManager hay có pooling.

Tạo file **`JdbcConfigDemo.java`** với toàn bộ nội dung:

~~~java
import java.io.PrintWriter;
import java.lang.reflect.Proxy;
import java.sql.Connection;
import java.sql.Driver;
import java.sql.DriverManager;
import java.sql.DriverPropertyInfo;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.util.Objects;
import java.util.Properties;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Logger;
import javax.sql.DataSource;

public final class JdbcConfigDemo {
    record DbConfig(String url, String user, String password) {
        DbConfig {
            Objects.requireNonNull(url);
            Objects.requireNonNull(user);
            Objects.requireNonNull(password);
        }
    }

    static final class DemoDriver implements Driver {
        final AtomicInteger opened = new AtomicInteger();
        final AtomicInteger closed = new AtomicInteger();

        @Override public boolean acceptsURL(String url) {
            return url != null && url.startsWith("jdbc:demo:");
        }

        @Override public Connection connect(String url, Properties properties)
                throws SQLException {
            if (!acceptsURL(url)) return null;
            if (!"reader".equals(properties.getProperty("user")))
                throw new SQLException("Demo user not accepted");
            int id = opened.incrementAndGet();
            AtomicBoolean isClosed = new AtomicBoolean();
            return (Connection) Proxy.newProxyInstance(
                    Connection.class.getClassLoader(),
                    new Class<?>[] {Connection.class},
                    (proxy, method, args) -> switch (method.getName()) {
                        case "toString" -> "demo-connection-" + id;
                        case "close" -> {
                            if (isClosed.compareAndSet(false, true)) closed.incrementAndGet();
                            yield null;
                        }
                        case "isClosed" -> isClosed.get();
                        case "isValid" -> !isClosed.get();
                        default -> throw new SQLFeatureNotSupportedException(
                                "Only connection lifecycle is simulated");
                    });
        }

        @Override public DriverPropertyInfo[] getPropertyInfo(String url, Properties info) {
            return new DriverPropertyInfo[0];
        }
        @Override public int getMajorVersion() { return 1; }
        @Override public int getMinorVersion() { return 0; }
        @Override public boolean jdbcCompliant() { return false; }
        @Override public Logger getParentLogger() {
            return Logger.getLogger("demo.jdbc");
        }
    }

    static final class ConfiguredDataSource implements DataSource {
        private final DbConfig config;
        private final Driver driver;
        private int loginTimeout;
        private PrintWriter logWriter;

        ConfiguredDataSource(DbConfig config, Driver driver) {
            this.config = config;
            this.driver = driver;
        }

        @Override public Connection getConnection() throws SQLException {
            return getConnection(config.user(), config.password());
        }

        @Override public Connection getConnection(String user, String password)
                throws SQLException {
            Properties properties = new Properties();
            properties.setProperty("user", user);
            properties.setProperty("password", password);
            Connection connection = driver.connect(config.url(), properties);
            if (connection == null) throw new SQLException("Driver rejected URL");
            return connection;
        }

        @Override public int getLoginTimeout() { return loginTimeout; }
        @Override public void setLoginTimeout(int seconds) {
            if (seconds < 0) throw new IllegalArgumentException("seconds < 0");
            loginTimeout = seconds;
        }
        @Override public PrintWriter getLogWriter() { return logWriter; }
        @Override public void setLogWriter(PrintWriter writer) { logWriter = writer; }
        @Override public Logger getParentLogger() {
            return Logger.getLogger("demo.jdbc");
        }
        @Override public boolean isWrapperFor(Class<?> type) {
            return type.isInstance(this);
        }
        @Override public <T> T unwrap(Class<T> type) throws SQLException {
            if (type.isInstance(this)) return type.cast(this);
            throw new SQLException("Not a wrapper for " + type.getName());
        }
    }

    public static void main(String[] args) throws SQLException {
        DbConfig config = new DbConfig("jdbc:demo:local", "reader", "test-only");
        DemoDriver driver = new DemoDriver();
        DriverManager.registerDriver(driver);
        try {
            try (Connection connection = DriverManager.getConnection(
                    config.url(), config.user(), config.password())) {
                System.out.println("DriverManager -> " + connection);
            }

            DataSource source = new ConfiguredDataSource(config, driver);
            try (Connection connection = source.getConnection()) {
                System.out.println("DataSource -> " + connection);
            }

            System.out.println("connections opened: " + driver.opened.get());
            System.out.println("connections closed: " + driver.closed.get());
            System.out.println("pool built in: no");
        } finally {
            DriverManager.deregisterDriver(driver);
        }
    }
}
~~~

Chạy với JDK **17 hoặc mới hơn**, trong thư mục có file:

~~~bash
javac --release 17 JdbcConfigDemo.java
java JdbcConfigDemo
~~~

**Stdout chính xác**, đã được biên dịch và chạy trên **OpenJDK 24.0.2** với `--release 17`:

~~~text
DriverManager -> demo-connection-1
DataSource -> demo-connection-2
connections opened: 2
connections closed: 2
pool built in: no
~~~

### Tại sao các dòng xuất hiện?

- `DbConfig` tập hợp URL, user, password. Dữ liệu `"test-only"` chỉ dành cho mô phỏng; **không** hardcode password production.
- `DemoDriver` implement `java.sql.Driver`. Dùng `Proxy` để tạo một `Connection` giả hỗ trợ `toString`, `close`, `isClosed` và `isValid`; các JDBC operations khác ném `SQLFeatureNotSupportedException`. Đây không phải database driver triển khai SQL thật.
- `DriverManager.registerDriver(driver)` cố ý đăng ký fake driver. Driver vendor hiện đại thường được auto-discover từ JDBC SPI JAR, không cần code ứng dụng tự `registerDriver`.
- `ConfiguredDataSource` implement interface `DataSource` và gọi driver trực tiếp, nên không có pool. Hai kết nối độc lập được tạo cho hai lần gọi.
- `try-with-resources` bảo đảm `close` gọi trên hai kết nối. Bộ đếm `opened=2`, `closed=2` cho thấy không bỏ quên close trong tình huống thử.
- `deregisterDriver` trong `finally` chỉ dọn đăng ký global mà demo tự tạo; không deregister một driver đang có consumers khác.
- `ConfiguredDataSource.setLoginTimeout(...)` trong ví dụ **chỉ lưu setting**, không enforce timeouts: fake driver không có network. Đừng dùng class demo làm DataSource production.
- `jdbcCompliant() == false` phản ánh fake driver chưa cung cấp hành vi JDBC hoàn chỉnh.

## 7. Tạo DataSource production: driver, pool và lifecycle

Một vendor JDBC driver có thể cung cấp một DataSource basic; một thư viện pool như **HikariCP** hoặc application server có pooling-capable DataSource. **Cả HikariCP và JDBC vendor driver đều là dependencies ngoài Java SE**; thêm phiên bản tương thích runtime vào Maven/Gradle và test với database tương ứng.

Đoạn **minh họa** cách bootstrap pool HikariCP (không chạy độc lập nếu chưa có dependency, cấu hình và DB thật):

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import java.sql.Connection;

HikariConfig config = new HikariConfig();
config.setJdbcUrl(settings.url());
config.setUsername(settings.user());
config.setPassword(settings.password());
config.setMaximumPoolSize(8);
config.setConnectionTimeout(3_000); // Thời gian chờ mượn connection (ms).

try (HikariDataSource pool = new HikariDataSource(config)) {
    try (Connection connection = pool.getConnection()) {
        // Thực thi JDBC work.
    }
}
// Chỉ owner ở bootstrap đóng pool; không tạo/đóng pool mỗi request.
~~~

Biến `settings` ở đây là cấu hình đã được tạo/validate và có secrets từ thành phần tin cậy. Trong một server lâu dài, DataSource/pool sống đến **application shutdown**, không nằm trong try-with-resources của từng request. Pool có thể có thread nền và nhiều physical connections: tạo mới nó liên tục là **phá mục tiêu pooling**.

### Pool size không càng lớn càng tốt

Nếu có 6 application replicas và mỗi pool tối đa 15 physical connections, riêng hệ thống này có thể dùng **90 DB connections**, chưa tính migrations, admin tools và các service khác. Pool sizing phải xét `max_connections` của DB, concurrency, query latency, transaction duration, số replicas và headroom khi rolling deploy.

Một pool lớn quá có thể khiến DB quá tải. Nên quan sát các chỉ số **active/idle/pending connections**, acquisition wait, timeout rates, DB CPU/locks và slow queries để điều chỉnh. Khi latency cao, pool size chỉ là một phần chẩn đoán; tối ưu SQL và transaction length có thể quan trọng hơn.

### `DataSource.getConnection(user,password)` có phải per-user pool không?

Không. Những pooled DataSource implementations thường được cấu hình cho một account/credential set. Overload hai tham số có thể bị hạn chế, unsupported hoặc tuân thủ chính sách riêng của implementation. Không dùng một pool để thay account tùy request nếu chưa có thiết kế isolation. Khi multi-tenant database/role cần phân tách, tạo datasource/pool theo scope được phép hoặc dùng cơ chế database support đúng chuẩn.

## 8. Bốn loại timeout phải phân biệt

| Tầng | API/config | Nội dung |
| --- | --- | --- |
| **Pool acquisition** | Hikari `connectionTimeout` hoặc container borrow timeout | Tối đa chờ lấy connection rảnh từ pool |
| **Login/connection establishment** | `DataSource.setLoginTimeout(seconds)` / `DriverManager.setLoginTimeout(seconds)` | Thời gian chờ kết nối/login theo driver |
| **Network** | Driver-specific connect/socket timeouts; `Connection.setNetworkTimeout(...)` khi được hỗ trợ | Kết nối TCP, đọc/ghi network, tình huống mạng treo |
| **SQL execution** | `Statement.setQueryTimeout(seconds)`, database statement timeout | Thời gian chạy câu lệnh SQL theo driver/database |

`DriverManager.setLoginTimeout` là setting **static/process-wide**, không phải một timeout riêng cho từng repository request. `DataSource.setLoginTimeout` cũng **không** có nghĩa mọi query sẽ timeout sau cùng số giây đó. Pool borrowing timeout, TCP connect timeout và query timeout phải được cấu hình riêng theo driver/pool.

Ví dụ query timeout:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "SELECT title FROM items WHERE id = ?")) {
    statement.setQueryTimeout(4);
    statement.setLong(1, itemId);
    try (ResultSet rows = statement.executeQuery()) {
        // Đọc kết quả tại đây; ResultSet cũng được đóng.
    }
}
~~~

Đây là **mã minh họa bên trong method** với `dataSource` và `itemId` đã tồn tại. Cần các JDBC imports và xử lý `SQLException`. Không coi statement timeout là một **hard deadline** tuyệt đối cho mọi loại lỗi network; phải kiểm thử theo driver và database thật.

Khi pool cạn connections, có thể xảy ra timeout mượn pool **mà chưa hề thử tạo query**. Khi DB tạm down, driver có thể ném lỗi kết nối. Cần phân biệt chúng ở logs/metrics và cơ chế retry.

## 9. Đóng Connection, transaction và pooling

Một `Connection` phải có **phạm vi sở hữu rõ ràng**. Mỗi request hoặc job mượn connection, chạy SQL, rồi close. Với pool, `Connection.close()` thường trả **logical handle** về pool; với non-pooled connection, close thường giải phóng **physical** resource.

~~~text
Request A  -> DataSource.getConnection() -> logical connection A -> close()
Request B  -> DataSource.getConnection() -> logical connection B -> close()
                                  |
                         Pool reuses physical connections
                                  |
Application shutdown -> pool owner closes pool once
~~~

Không lưu `Connection` như field singleton trong repository để nhiều threads dùng chung. Pool DataSource mới là đối tượng có lifecycle dài; mỗi Connection cần được mượn ngắn hạn. Nếu một Connection chứa transaction state, isolation level, schema hoặc session variables, pool cần reset chúng trước khi tái sử dụng theo implementation; ứng dụng phải tránh để lại session state vô tình rò rỉ.

Ví dụ transaction dùng cùng một Connection:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        // Thực thi các PreparedStatement thuộc cùng một transaction.
        connection.commit();
    } catch (SQLException | RuntimeException ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            ex.addSuppressed(rollbackFailure);
        }
        throw ex;
    }
}
~~~

Đây là **mã minh họa**, yêu cầu `dataSource` trong method và xử lý `SQLException`. Framework có transaction manager sẽ quản lý boundary; khi dùng framework không tự commit/rollback bên dưới theo ý riêng của mỗi repository. Nếu transaction rollback thất bại, ví dụ giữ exception gốc và `addSuppressed` thông tin rollback.

### Đóng pool khi nào?

- **Có pool do ứng dụng tạo:** đóng khi application shutdown sau khi ngừng nhận việc mới và drain in-flight requests theo deadline.
- **Container-managed DataSource:** container/framework quản lý pool; application code chỉ đóng `Connection` do nó mượn.
- **Basic DataSource:** interface không có `close()`; đọc tài liệu vendor để biết có tài nguyên cần cleanup hay không.
- **Không bao giờ** tạo `HikariDataSource` trong mỗi HTTP handler rồi đóng ngay sau query; như thế có thể tạo/đóng hàng loạt physical DB connections và threads.

## 10. Security: kết nối DB là ranh giới có quyền truy cập dữ liệu

Một hệ thống với JDBC cần nhiều hơn việc “kết nối được”:

- **Least privilege:** account đọc, ghi, migration/schema owner có quyền tách biệt nếu nghiệp vụ yêu cầu. Không chạy backend bằng DB superuser khi chỉ cần SELECT/INSERT.
- **Secrets:** lấy credentials từ secret manager/orchestrator, không commit vào source, Docker image hoặc public config. Hạn chế quyền xem logs/support dumps/CI variables.
- **Không đặt real password trong JDBC URL** nếu driver có trường credentials riêng; không log toàn bộ config object/Properties hay exception chứa secrets.
- **TLS với server identity verification:** kiểm tra CA/trust store và hostname/certificate theo driver. Bật encryption mà tắt verify không phải cấu hình production an toàn.
- **Không nhận URL tùy ý từ user.** JDBC URLs có thể trỏ tới host/database ngoài ranh giới cho phép; lấy endpoint từ trusted deployment config, validate allowlist và các vendor-specific properties.
- **Parameterized SQL:** `PreparedStatement` tránh nối giá trị input trực tiếp vào SQL. Việc dùng pool không bảo vệ khỏi SQL injection.
- **Credential rotation:** khi đổi secret, cần refresh/drain/recreate physical connections/pool theo hỗ trợ; không đợi một biến môi trường runtime tự cập nhật tất cả sessions.
- **Tenant isolation:** định nghĩa account/schema/connection scope; không để session-level state của tenant A sót lại khi connection được trả về và sau đó tenant B mượn.
- **No secret logging:** pool metrics nên dùng tên pool/DB role đã sanitize; tránh in `Connection.toString()` nếu vendor có thể chứa URL/parameters.
- **Resource exhaustion:** giới hạn pool size, acquisition waiting, retry rate và tổng kết nối trên mọi replicas; DB connection limit là tài nguyên hữu hạn.

### Không retry vô hạn khi connect lỗi

`SQLException` có thể biểu thị user/password sai, DB host sai, TLS config lỗi, mạng gián đoạn, quyền thiếu hoặc DB quá tải. Retry nên dựa vào SQLState/vendor code hoặc các class lỗi transient được driver hỗ trợ, có **backoff**, hạn lần và deadline rõ. Đặc biệt với một giao dịch ghi, mất phản hồi sau commit khiến caller không biết liệu DB đã áp dụng thao tác hay chưa: retry mù có thể gây **ghi trùng**. Pool tự reconnect physical connection cũng không tự biến một business transaction thành idempotent.

## 11. Test đúng tầng: unit, integration, operational

### Unit test

Vì repository nhận `DataSource` trong constructor, bạn có thể inject fake/mock DataSource để kiểm tra việc request luôn close connection, xử lý exception và chọn branch. Nhưng việc mock hàng loạt `Connection`, `PreparedStatement`, `ResultSet` không tự chứng minh SQL được DB thật chấp nhận.

Chương trình `JdbcConfigDemo` ở phần 6 là **unit-style demonstration về API và lifecycle**, không kiểm thử SQL, authentication, socket, TLS, pooling hay transaction isolation. Dòng `pool built in: no` là một **kết luận từ implementation demo**, không phải khẳng định tất cả DataSource đều thiếu pool.

### Integration test

Với đường SQL thật, dùng DB test riêng (ví dụ một container database tạm thời) và cùng JDBC driver/dialect dự kiến ở production. Các trường hợp quan trọng:

1. Driver dependency ở runtime, URL/hostname/TLS đúng và thiếu driver được báo rõ.
2. DataSource tạo được kết nối, query thật và đóng resources trên mọi code path.
3. Username/secret sai; role thiếu quyền; database read-only hoặc schema không tồn tại.
4. Pool acquire/release, maximum size, timeout khi pool đầy và leak detection.
5. Transaction commit, rollback, isolation phù hợp, connection/session reset.
6. Lỗi network, DB restart/failover, credential rotation, stale connections.
7. Tải đồng thời nhiều requests; tổng connections theo replicas trong giới hạn DB.
8. Shutdown/drain không bỏ sót kết nối và background threads.
9. Environment config tách riêng test/prod; không bao giờ dùng production secrets trong CI.
10. Quan sát được acquisition latency và failed connections mà không ghi log secrets.

### Metrics nên theo dõi

Active/idle/total/pending connections, pool acquisition latency, connection creation failures, pool timeouts, slow queries, transaction duration, database `max_connections` usage và tỷ lệ retry. Nếu pending queue tăng liên tục, chưa chắc cần tăng pool size: bottleneck có thể là SQL, locks, CPU, network hoặc transaction giữ connection quá lâu.

## 12. Những lỗi và hiểu lầm phổ biến

| Hiểu lầm | Thực tế / cách sửa |
| --- | --- |
| “`DriverManager` đã deprecated.” | Không; nó vẫn được hỗ trợ, còn DataSource được khuyến nghị cho application design |
| “`DataSource` luôn có pool.” | Không; chỉ pooling implementation có cơ chế tái sử dụng |
| “DataSource là class tạo bằng `new DataSource()`.” | Interface, phải dùng implementation |
| “Trong Java mới dùng `jakarta.sql.DataSource`.” | JDBC Java SE vẫn dùng `javax.sql.DataSource` |
| “Luôn cần `Class.forName` để nạp JDBC driver.” | JDBC 4+ driver JAR thường có service discovery; kiểm tra runtime classloader |
| “Đóng Connection sẽ đóng cả pool.” | Nếu pooled thường trả logical connection về pool; owner đóng pool lúc shutdown |
| “DataSource nào cũng có method `close`.” | Interface không có close; pool implementation có thể hỗ trợ |
| “Mỗi request tự tạo pool thì sẽ an toàn hơn.” | Tốn tài nguyên và phá pooling; tạo pool ở application scope |
| “Chỉ cần `setLoginTimeout` để SQL không treo.” | Query/network/acquisition/login timeout là các lớp riêng |
| “Nhân pool size lên càng cao càng tốt.” | Tổng số connections có thể vượt DB capacity trên nhiều replicas |
| “`Connection` có thể dùng chung cho mọi threads.” | Dễ gây transaction state/thread safety bugs; dùng borrow-per-unit-of-work |
| “Config DB nên đặt trong repository.” | Tập trung ở bootstrap/framework, inject DataSource |
| “Environment variables tự bảo vệ password.” | Phải kiểm soát secrets provisioning, quyền và logging |
| “Sửa environment là pool đọc lại ngay.” | Cần lifecycle/rotation plan cho pool và physical sessions |
| “Đặt user/password cả URL lẫn Properties thì có thứ tự ưu tiên chuẩn.” | Precedence implementation-defined; chỉ cung cấp một lần |
| “JNDI luôn có trong Java CLI.” | Cần naming environment/application server được cấu hình |
| “Một pool dùng credentials tùy request luôn hoạt động.” | Tùy implementation, thường pool theo một auth identity |
| “`SQLException` nào cũng nên retry.” | Phân loại, backoff, deadline, idempotency và transaction semantics |
| “Fake Driver example kiểm thử SQL production.” | Chỉ minh họa API/cấu hình/close, không có DB thật |

## 13. Quy tắc chọn công cụ theo tình huống

| Tình huống | Hướng thích hợp |
| --- | --- |
| CLI nhỏ có một tác vụ DB | `DriverManager.getConnection` và try-with-resources |
| Web backend nhiều request, job workers | Inject `DataSource` do bootstrap/framework quản lý |
| Muốn connection pooling | Dùng pool implementation hoặc container-managed DataSource, không chỉ một interface basic |
| Spring/Micronaut/Quarkus | Dùng DataSource bean/config và lifecycle của framework |
| Jakarta EE server | Dùng container-managed DataSource, thường qua JNDI/DI |
| Nhiều DB roles/tenants | Tách DataSource/pool theo role hoặc policy isolation |
| Unit test không có DB | Inject fake DataSource hoặc interface service hẹp |
| SQL integration test | Database thật tạm thời, driver đúng, schema migrations |
| Môi trường cần secrets rotation | Secret provider + pool refresh/drain hoặc restart theo policy |
| Phân tán giao dịch qua nhiều resources | Transaction manager/XA infrastructure khi có yêu cầu thật, không mặc định DataSource basic hỗ trợ |

## 14. Tự kiểm tra

1. **`DriverManager` có lỗi thời trên Java 17+ không?** Không; vẫn hợp lệ, còn DataSource thường phù hợp hơn cho ứng dụng cần abstraction và DI.
2. **`DataSource` nằm ở package nào?** `javax.sql` thuộc module `java.sql`, không phải `jakarta.sql`.
3. **`DataSource.getConnection()` có luôn tái sử dụng physical connection không?** Không; phụ thuộc pooling implementation.
4. **Vì sao repository nhận DataSource qua constructor?** Không phụ thuộc URL, secrets, pool vendor, dễ test và thay config.
5. **Ai nên đọc `DB_URL/DB_PASSWORD`?** Composition root, framework bootstrap hoặc một config/secret injection layer tin cậy.
6. **Khi nào đóng Connection?** Sau mỗi unit of work/transaction, tốt nhất dùng try-with-resources.
7. **Khi nào đóng pool?** Khi application owner shutdown; không trong mỗi request.
8. **`Class.forName` có bắt buộc cho driver hiện đại không?** Thông thường không nhờ JDBC 4+ service discovery; vẫn cần dependency/visibility.
9. **`setLoginTimeout` kiểm soát `SELECT` chứ?** Không; cần query timeout và driver/network config riêng.
10. **Vì sao không bỏ password vào URL?** Giảm nguy cơ lộ qua logs/diagnostics và tránh ambiguity với Properties.
11. **6 replicas × pool max 15 bằng bao nhiêu connection tiềm năng?** 90 connection cho hệ thống đó, chưa kể consumers khác.
12. **`JdbcConfigDemo` chứng minh gì?** Hai cách cấp Connection, lifecycle close và DataSource không tự pooling; không chứng minh SQL thật.
13. **Dùng một connection như singleton cho mọi request có ổn không?** Không; chia sẻ session/transaction state nguy hiểm.
14. **Nếu đổi DB cần thay repository không?** Interface có thể giữ, nhưng SQL dialect/schema vẫn có thể cần thay.
15. **Tại sao retry `SQLException` vô hạn là nguy hiểm?** Có lỗi vĩnh viễn, có thể overload DB và có rủi ro ghi trùng khi commit không rõ.
16. **Container quản lý JNDI DataSource thì ai close pool?** Container theo lifecycle của nó; application close các Connections đã mượn.

## 15. Tham khảo chính thức, còn áp dụng

- [Java SE 25 — javax.sql.DataSource](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/javax/sql/DataSource.html): ưu tiên DataSource, basic/pooling/distributed implementations, getConnection, login timeout.
- [Java SE 25 — java.sql.DriverManager](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/DriverManager.html): driver service discovery, getConnection overloads và property precedence.
- [Java SE 25 — java.sql.Driver](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/Driver.html): `connect`, `acceptsURL` và JDBC driver contract.
- [Java SE 25 — java.sql.Connection](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/Connection.html): `close`, `AutoCloseable`, transactions và network timeout.
- [Java SE 25 — javax.sql package](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/javax/sql/package-summary.html): DataSource, ConnectionPoolDataSource, XADataSource.
- [Java SE 25 — java.sql.Statement](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/Statement.html): query timeout API.
- [Java SE 25 — java.sql.SQLException](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/SQLException.html): SQLState, vendor code, chained exceptions.
- [HikariCP — official source/configuration](https://github.com/brettwooldridge/HikariCP): ví dụ thư viện pool ngoài JDK và vòng đời HikariDataSource.

**Ghi nhớ:** `DriverManager` là con đường trực tiếp để **driver mở kết nối**; `DataSource` là interface **cấp kết nối có thể inject**; **cấu hình, secrets, pooling và lifecycle** nằm ở bootstrap/container. Repository chỉ cần DataSource và đóng Connection đúng lúc. Chọn API theo ngữ cảnh, không dùng DriverManager để thay pool hay dùng DataSource để che giấu cấu hình rải rác.