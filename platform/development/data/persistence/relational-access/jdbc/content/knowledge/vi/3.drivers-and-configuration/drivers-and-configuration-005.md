# Truyền thông tin kết nối qua cấu hình và Properties

Trong **JDBC (Java Database Connectivity)**, ứng dụng Java cần biết **kết nối đến đâu**, **dùng tài khoản nào** và **driver phải kết nối như thế nào** trước khi truy cập cơ sở dữ liệu quan hệ. Những thông tin đó được truyền từ cấu hình ứng dụng đến JDBC, thường qua URL kết nối, tên người dùng/mật khẩu và đối tượng `java.util.Properties`.

Bài học thuộc chương **Driver và cấu hình**. Trọng tâm là cách dùng `DriverManager.getConnection(String, Properties)`, cách nạp dữ liệu từ file cấu hình và biến môi trường, cách phân biệt thuộc tính chung với thuộc tính phụ thuộc driver, cùng những quy tắc bảo vệ thông tin kết nối trong ứng dụng thật.

Sau bài học, bạn sẽ có thể: tạo kết nối không ghi cứng mật khẩu; xác định nguồn và thứ tự ưu tiên của cấu hình; tự nạp file `.properties`; phân biệt `Properties` của ứng dụng và `Properties` chuyển cho driver; xử lý trường hợp thiếu cấu hình mà không làm lộ bí mật.

## 1. Vì sao cần đưa thông tin kết nối ra ngoài mã nguồn?

Xét cách tạo kết nối trực tiếp:

~~~java
Connection connection = DriverManager.getConnection(
        "jdbc:postgresql://localhost:5432/inventory",
        "app_user",
        "example_password" // Chỉ là ví dụ; không ghi mật khẩu thật vào mã.
);
~~~

Cách viết này dễ hiểu khi học JDBC, nhưng không phù hợp để vận hành: địa chỉ database thay đổi giữa môi trường phát triển, kiểm thử và production; tài khoản có thể được xoay vòng; việc ghi mật khẩu vào mã làm tăng nguy cơ lộ qua Git, review, log hoặc bản build.

Một thiết kế tốt tách hai trách nhiệm:

- **Nguồn cấu hình**: môi trường chạy, file cấu hình, tham số JVM hoặc hệ thống quản lý bí mật cung cấp giá trị.
- **Mã tạo kết nối**: đọc và kiểm tra các giá trị đó, xây dựng URL/`Properties`, gọi JDBC và trả `Connection` để ứng dụng sử dụng.

~~~text
                          CÁC NGUỒN CẤU HÌNH
                      ┌──────────────────────┐
                      │ Biến môi trường      │
                      │ File .properties     │
                      │ JVM -D / cấu hình app│
                      │ Secret manager       │
                      └──────────┬───────────┘
                                 │ đọc, kiểm tra, chọn giá trị
                                 ▼
                      ┌──────────────────────┐
                      │ Cấu hình ứng dụng    │
                      │ jdbcUrl, user, ...   │
                      └──────────┬───────────┘
                                 │ xây Properties cho driver
                                 ▼
                      ┌──────────────────────┐
                      │ DriverManager        │
                      │ .getConnection(...)  │
                      └──────────┬───────────┘
                                 ▼
                            JDBC Driver
                                 │
                                 ▼
                             Database
~~~

**Đưa cấu hình ra ngoài mã** không có nghĩa mọi nguồn cấu hình đều an toàn như nhau. Chẳng hạn file `.properties` hoặc biến môi trường chứa mật khẩu vẫn phải được bảo vệ bằng quyền truy cập và quy trình triển khai phù hợp.

## 2. Ba nhóm thông tin cần phân biệt

| Nhóm | Ví dụ | Nơi sử dụng |
| --- | --- | --- |
| **Địa chỉ JDBC** | `jdbc:postgresql://db.example.internal:5432/inventory` | Được truyền riêng trong tham số `url` của `getConnection(...)` |
| **Thông tin xác thực** | `user`, `password` hoặc cơ chế token/authentication khác | Thường nằm trong `Properties`, truyền qua overload username/password, hoặc cơ chế riêng của driver |
| **Tùy chọn driver** | Mã hóa TLS, chứng chỉ, timeout tạo socket, tên ứng dụng | Các key/value của `Properties` hoặc JDBC URL, theo tài liệu *đúng driver* |

JDBC quy định các interface và overload chuẩn, nhưng **không chuẩn hóa tên của mọi thuộc tính cấu hình**. Các key `user` và `password` được dùng phổ biến, còn `sslmode`, `encrypt`, `connectTimeout`, `socketTimeout` chỉ có ý nghĩa khi driver tương ứng hỗ trợ. Đơn vị và giá trị có thể khác nhau.

Một JDBC URL điển hình bắt đầu bằng tiền tố `jdbc:`. Cú pháp phần còn lại do driver quyết định; vì vậy không tự ghép tên database, cổng hoặc query parameter bằng một quy tắc duy nhất cho tất cả hệ quản trị.

## 3. Sử dụng `DriverManager.getConnection` với `Properties`

`DriverManager` có ba overload phổ biến:

~~~java
DriverManager.getConnection(url);
DriverManager.getConnection(url, username, password);
DriverManager.getConnection(url, properties);
~~~

Overload thứ ba nhận một `java.util.Properties`. Đây là một tập cặp *key → value*; trong cấu hình JDBC thông thường, cả tên khóa và giá trị đều được biểu diễn bằng chuỗi.

Ví dụ tối giản:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Properties;

public final class DirectJdbcConnection {
    public static Connection open(String url, String user, String password)
            throws SQLException {

        Properties properties = new Properties();
        properties.setProperty("user", user);
        properties.setProperty("password", password);

        return DriverManager.getConnection(url, properties);
    }
}
~~~

Lời gọi `getConnection(url, properties)` yêu cầu `DriverManager` tìm một driver JDBC phù hợp với URL và chuyển các thuộc tính cho driver đó khi thiết lập kết nối. **Driver JAR vẫn phải có ở runtime**; chỉ tạo `Properties` không làm JDBC tự cài driver.

Một cách dùng tài nguyên đúng:

~~~java
try (Connection connection =
             DirectJdbcConnection.open(jdbcUrl, dbUser, dbPassword)) {
    // Tạo PreparedStatement, thực thi SQL trong phạm vi kết nối.
} // Luôn đóng Connection khi không còn dùng.
~~~

Trong hai đoạn trên, `jdbcUrl`, `dbUser`, `dbPassword` được cung cấp từ cấu hình ở bên ngoài; mã nguồn không chứa dữ liệu đăng nhập cố định.

**Lưu ý:** `Properties` là đối tượng Java dùng để truyền cấu hình, **không phải** một connection pool và cũng không bảo mật hay mã hóa giá trị tự động. `properties.setProperty("password", ...)` vẫn giữ mật khẩu trong bộ nhớ tiến trình; tránh đưa đối tượng đó ra log.

## 4. Các nguồn cấu hình phổ biến trong Java

### 4.1. Biến môi trường

Biến môi trường phù hợp để cung cấp giá trị khi chạy ứng dụng trong máy phát triển, container hoặc hệ thống triển khai.

~~~java
String jdbcUrl = System.getenv("DB_JDBC_URL");
String username = System.getenv("DB_USER");
String password = System.getenv("DB_PASSWORD");
~~~

`System.getenv(...)` trả về `null` nếu biến không tồn tại; nên kiểm tra trước khi truyền cho JDBC. Cách này giúp cùng một binary chạy ở nhiều môi trường với cấu hình khác nhau.

Ví dụ tên biến có thể là:

~~~text
DB_JDBC_URL = jdbc:postgresql://db.example.internal:5432/inventory
DB_USER     = inventory_app
DB_PASSWORD = (do hệ thống triển khai cung cấp)
~~~

Phần tên và giá trị chỉ minh họa. Không đặt mật khẩu thật vào tài liệu, lệnh shell được lưu lịch sử, ảnh chụp màn hình hoặc log.

### 4.2. File `.properties`

Một file cấu hình của ứng dụng có thể lưu các giá trị không nhạy cảm:

~~~properties
# config/database.properties
jdbc.url=jdbc:postgresql://localhost:5432/inventory
# Thuộc tính driver-specific: PostgreSQL driver hiểu key này.
driver.connectTimeout=5
# Bật xác minh TLS khi môi trường có cấu hình CA/chứng chỉ phù hợp.
driver.sslmode=verify-full
~~~

Ở đây `jdbc.url` là **tên khóa do ứng dụng tự chọn**. JDBC không tự động đọc khóa đó. Tiền tố `driver.` cũng là **quy ước do ứng dụng tự đặt** để chỉ các key cần chuyển sang driver; trong ví dụ về sau, chương trình loại bỏ tiền tố này trước khi tạo `Properties` gửi cho JDBC.

Có thể nạp file `.properties` bằng `Properties.load(...)`:

~~~java
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

Properties config = new Properties();

try (Reader reader = Files.newBufferedReader(
        Path.of("config/database.properties"), StandardCharsets.UTF_8)) {
    config.load(reader);
}

String jdbcUrl = config.getProperty("jdbc.url");
~~~

`Properties.load(Reader)` nhận ký tự từ `Reader`; với `Files.newBufferedReader(..., UTF_8)`, ví dụ cho phép đọc file mã hóa UTF-8. Ngược lại, overload `Properties.load(InputStream)` dùng quy ước mã hóa Latin-1/ISO-8859-1 của định dạng properties; đây là điểm cần nhớ khi file có nội dung tiếng Việt hoặc ký tự Unicode. Các ký tự đặc biệt như `=`, `:`, `\\` có quy tắc escape trong cú pháp `.properties`.

Tệp `.properties` không được JDBC tự tìm và nạp chỉ vì có phần mở rộng đó. **Ứng dụng/framework phải chủ động đọc** file rồi chuyển những giá trị cần thiết đến driver hoặc `DataSource`.

### 4.3. System properties của JVM

Java còn có **system properties** đọc bằng `System.getProperty(...)`, ví dụ một chương trình có thể chấp nhận đối số JVM:

~~~text
-Dapp.jdbc.url=jdbc:postgresql://localhost:5432/inventory
~~~

Rồi đọc:

~~~java
String jdbcUrl = System.getProperty("app.jdbc.url");
~~~

System property của JVM và `java.util.Properties` gửi cho JDBC là hai khái niệm khác nhau: `System.getProperty("app.jdbc.url")` chỉ đọc cấu hình của tiến trình; **không tự đẩy giá trị** đó vào `DriverManager`. Tránh truyền thông tin bí mật qua tham số dòng lệnh vì chúng có thể xuất hiện trong lịch sử lệnh hoặc thông tin tiến trình.

### 4.4. Secret manager và framework

Trong ứng dụng production, thông tin nhạy cảm thường do hệ thống cấu hình/secret manager cấp, rồi được đưa tới lớp tạo kết nối hoặc một `DataSource` đã cấu hình. Framework như Spring có thể đọc các khóa của chính framework và dựng `DataSource`, nhưng đó là hành vi của framework, **không phải JDBC core tự hiểu mọi khóa trong file**.

## 5. Ví dụ hoàn chỉnh: file cấu hình + biến môi trường + Properties

Ví dụ sau có một thứ tự ưu tiên rõ ràng:

- URL: ưu tiên `DB_JDBC_URL` nếu được đặt và không rỗng; nếu không, dùng khóa `jdbc.url` trong file.
- Tài khoản và mật khẩu: lấy từ `DB_USER` và `DB_PASSWORD`, không đặt sẵn trong file minh họa.
- Các khóa bắt đầu bằng `driver.` trong file: bỏ tiền tố để chuyển vào `Properties` gửi đến driver.
- Giá trị `user` và `password` từ biến môi trường ghi sau cùng để không bị file thay thế.

~~~java
import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Properties;

public final class JdbcConnectionFactory {

    private static final String DRIVER_PREFIX = "driver.";

    private JdbcConnectionFactory() {
    }

    public static Connection open(Path configPath)
            throws IOException, SQLException {

        Properties appConfig = new Properties();

        try (Reader reader = Files.newBufferedReader(
                configPath, StandardCharsets.UTF_8)) {
            appConfig.load(reader);
        }

        String url = required(
                firstNonBlank(System.getenv("DB_JDBC_URL"),
                        appConfig.getProperty("jdbc.url")),
                "DB_JDBC_URL or jdbc.url");

        String user = required(System.getenv("DB_USER"), "DB_USER");
        String password = required(
                System.getenv("DB_PASSWORD"), "DB_PASSWORD");

        Properties driverProps = new Properties();

        for (String key : appConfig.stringPropertyNames()) {
            if (key.startsWith(DRIVER_PREFIX)
                    && key.length() > DRIVER_PREFIX.length()) {

                String driverKey = key.substring(DRIVER_PREFIX.length());
                driverProps.setProperty(
                        driverKey, appConfig.getProperty(key));
            }
        }

        // Credentials lấy từ môi trường, luôn được gán sau cùng.
        driverProps.setProperty("user", user);
        driverProps.setProperty("password", password);

        return DriverManager.getConnection(url, driverProps);
    }

    private static String firstNonBlank(String preferred, String fallback) {
        return preferred != null && !preferred.isBlank()
                ? preferred : fallback;
    }

    private static String required(String value, String key) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing required configuration: " + key);
        }
        return value;
    }
}
~~~

*Đoạn mã dùng `String.isBlank()` và `Path.of(...)` (Java 11 trở lên). Trong ví dụ, mật khẩu rỗng được coi là cấu hình thiếu; hệ thống cho phép mật khẩu rỗng có thể điều chỉnh quy tắc kiểm tra theo chính sách của mình.*

Cách gọi:

~~~java
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

String sql = "SELECT id, name FROM products WHERE id = ?";

try (Connection connection = JdbcConnectionFactory.open(
             Path.of("config/database.properties"));
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, 42L);

    try (ResultSet rows = statement.executeQuery()) {
        if (rows.next()) {
            System.out.println(rows.getLong("id")
                    + ": " + rows.getString("name"));
        }
    }
}
~~~

Ví dụ giả định database có bảng `products(id, name)` và thư viện PostgreSQL JDBC driver phù hợp đã có ở runtime. Phương thức `open(...)` trả kết nối đã mở; **caller sở hữu trách nhiệm đóng `Connection`** bằng `try-with-resources`. `PreparedStatement` và `ResultSet` cũng được đóng đúng phạm vi.

Trong ứng dụng thực, để giảm đọc file và tạo kết nối thủ công cho mỗi request, cấu hình thường được đọc một lần lúc khởi động; tầng hạ tầng tạo `DataSource` hoặc connection pool và truyền đối tượng đó vào các repository.

## 6. Hai lớp Properties không phải cùng một tập khóa

Ví dụ `JdbcConnectionFactory` dùng **hai đối tượng khác nhau**:

1. `appConfig`: dữ liệu của ứng dụng, gồm các khóa tự đặt như `jdbc.url`, `driver.connectTimeout`.
2. `driverProps`: chỉ chứa các khóa driver thực sự nhận, chẳng hạn `user`, `password`, `connectTimeout`.

Tách hai lớp này giúp tránh đưa nhầm cấu hình ứng dụng vào driver.

| Khóa trong file ứng dụng | Cách mã ví dụ xử lý | Giá trị/khóa chuyển tới JDBC |
| --- | --- | --- |
| `jdbc.url=...` | Dùng làm tham số URL, trừ khi biến môi trường override | `getConnection(url, ...)` |
| `driver.connectTimeout=5` | Bỏ tiền tố `driver.` | `connectTimeout=5` |
| `driver.sslmode=verify-full` | Bỏ tiền tố `driver.` | `sslmode=verify-full` |
| `app.featureX=true` | Không khớp tiền tố; ứng dụng xử lý riêng | Không được chuyển tới driver |
| `DB_USER` trong environment | Lấy và kiểm tra | `user=...` |
| `DB_PASSWORD` trong environment | Lấy và kiểm tra | `password=...` |

Kết quả thực thi phụ thuộc driver. Ví dụ các tên `connectTimeout` và `sslmode` trong bảng liên quan đến driver PostgreSQL và **không phải thuộc tính JDBC thống nhất giữa mọi nhà cung cấp**. Với database khác, tham khảo tài liệu của driver đó trước khi giữ nguyên cấu hình.

### Khi URL và Properties cùng định nghĩa một key

Một số driver cho phép truyền tham số qua cả URL lẫn `Properties`:

~~~text
jdbc:postgresql://localhost:5432/inventory?sslmode=require
~~~

Và đồng thời:

~~~java
properties.setProperty("sslmode", "verify-full");
~~~

Nếu cùng key xuất hiện ở cả URL lẫn `Properties`, **giá trị được ưu tiên có thể phụ thuộc driver**. JDBC không bảo đảm một quy tắc ưu tiên chung trong trường hợp này. Chỉ định một thuộc tính ở **một nơi** theo quy ước thống nhất, nhất là với SSL/TLS và các thiết lập bảo mật.

Nếu nhiều nguồn cấu hình của *ứng dụng* được chấp nhận, hãy tự định nghĩa thứ tự ưu tiên trong mã và tài liệu cấu hình; đừng nhầm nó với quy tắc xử lý trùng key do *driver* quyết định.

## 7. Cấu hình SSL/TLS và timeout: đừng giả định tính di động

Những thuộc tính ảnh hưởng bảo mật và độ tin cậy cần được đặt có chủ đích.

| Mục tiêu | Cơ chế thường gặp | Điều cần kiểm tra |
| --- | --- | --- |
| Mã hóa và xác thực server DB | Tùy chọn TLS/SSL riêng của driver (ví dụ `sslmode` với PostgreSQL) | Chế độ có xác minh hostname/chứng chỉ hay không; CA/trust store |
| Giới hạn mở socket/kết nối | Connect timeout riêng của driver | Key và đơn vị là giây hay mili giây |
| Giới hạn đợi dữ liệu qua mạng | Socket read timeout của driver hoặc `Connection.setNetworkTimeout(...)` | Phạm vi, đơn vị, hậu quả khi kết nối mất phản hồi |
| Giới hạn thực thi SQL | `Statement.setQueryTimeout(int seconds)` | Được đặt trên câu lệnh, **không** phải thuộc tính kết nối chung |
| Giới hạn đợi mượn connection từ pool | Cấu hình của pool | Khác với driver TCP connect timeout |
| Giới hạn giai đoạn login | `DriverManager.setLoginTimeout(int seconds)` hoặc cấu hình `DataSource`/driver | Phạm vi áp dụng, mức hỗ trợ; không dùng để giới hạn SQL |

Không sao chép tên `connectTimeout`/`socketTimeout` giữa các driver mà không kiểm tra tài liệu; tên và đơn vị có thể khác. Không đặt TLS “bật” đồng nghĩa với “xác thực server đầy đủ”: tùy chọn cho phép kết nối được mã hóa nhưng **không kiểm tra danh tính máy chủ** vẫn có thể để lại rủi ro. Khi triển khai production, cấu hình chứng chỉ và hostname verification phù hợp với DB.

`DriverManager.setLoginTimeout(...)` có tác động phạm vi rộng hơn một lời gọi riêng lẻ trong tiến trình Java; không thay đổi liên tục theo mỗi request. `Statement.setQueryTimeout(...)` nhận **giây**, còn `Connection.setNetworkTimeout(...)` nhận **mili giây** và yêu cầu một `Executor` hợp lệ; hai API này phục vụ hai mục tiêu khác nhau.

## 8. Khi ứng dụng dùng DataSource hoặc connection pool

`DriverManager.getConnection(url, props)` thích hợp cho ví dụ đơn giản, tiện ích nhỏ hoặc công cụ dòng lệnh. Trong ứng dụng server, thường dùng `javax.sql.DataSource` vì có thể cấu hình một lần, quản lý kết nối qua pool và inject vào repository:

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.SQLException;

public final class InventoryService {
    private final DataSource dataSource;

    public InventoryService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void performDatabaseWork() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            // Sử dụng Connection theo JDBC API.
        }
    }
}
~~~

`DataSource` là **interface lấy kết nối**, bản thân interface không bảo đảm có pool. Pool như HikariCP có cấu hình của **pool** (giới hạn số kết nối, thời gian chờ mượn), đồng thời có cách chuyển **thuộc tính kết nối riêng của driver** xuống driver. Đây là hai cấp cấu hình khác nhau.

Ví dụ minh họa với HikariCP (cần thư viện tương ứng, không thuộc JDBC core):

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

HikariConfig poolConfig = new HikariConfig();
poolConfig.setJdbcUrl(jdbcUrl);
poolConfig.setUsername(dbUser);
poolConfig.setPassword(dbPassword);
poolConfig.setMaximumPoolSize(10);
poolConfig.setConnectionTimeout(2_000L); // Chờ mượn pool: mili giây.

// Thuộc tính PostgreSQL JDBC driver, không phải chuẩn chung:
poolConfig.addDataSourceProperty("sslmode", "verify-full");

HikariDataSource dataSource = new HikariDataSource(poolConfig);

// Quản lý dataSource suốt vòng đời ứng dụng;
// đóng dataSource khi ứng dụng tắt, không đóng mỗi request.
~~~

Trong đoạn HikariCP, `jdbcUrl`, `dbUser` và `dbPassword` đều đến từ cấu hình. `setConnectionTimeout(2_000L)` là giới hạn **chờ mượn connection từ pool**, không phải timeout thiết lập TCP socket. Khi repository đóng `Connection` mượn từ pool, nó thường được trả về pool để tái sử dụng. `HikariDataSource` được đóng khi pool hết vòng đời.

Lưu ý: Mã JDBC chung để tạo `PreparedStatement` và duyệt `ResultSet` gần như không đổi khi chuyển nguồn `Connection` từ `DriverManager` sang `DataSource`; điều cần thay đổi là **vị trí cấu hình và quản lý vòng đời kết nối**.

## 9. Bảo vệ thông tin kết nối

Thông tin kết nối có thể chứa tên máy chủ nội bộ, người dùng DB, mật khẩu, token hoặc đường dẫn đến chứng chỉ. Các quy tắc thực hành:

- **Không commit bí mật** trong source code, test fixture công khai, file `.properties` được theo dõi bởi Git hoặc ví dụ trong tài liệu. Đưa một bản cấu hình mẫu chỉ chứa key và giá trị giả định.
- **Không log toàn bộ URL/`Properties`**: một số driver cho phép đưa thông tin xác thực vào query parameter của URL. Ngoài ra `Properties.toString()` có thể lộ mật khẩu.
- **Phân quyền tài khoản DB** theo thao tác ứng dụng cần thực hiện. Tài khoản chỉ đọc không nên có quyền thay đổi schema hay quản trị database.
- **Dùng kênh bảo mật cho bí mật** như secret manager và cơ chế inject phù hợp; file cục bộ nếu bắt buộc phải có quyền truy cập chặt chẽ và không nằm trong kho mã nguồn.
- **Xoay vòng thông tin xác thực** và quản lý vòng đời connection/pool tương ứng, vì các connection đang mở có thể tồn tại sau khi mật khẩu được thay đổi.
- **Xác thực cấu hình TLS** bằng chứng chỉ/hostname đúng; không tắt xác minh chỉ để “kết nối cho chạy được”.
- **Không in chi tiết nhạy cảm khi báo lỗi**. Có thể ghi loại lỗi, SQLState, vendor code và một mã nhận dạng sự kiện; chỉ ghi URL đã được làm sạch nếu cần.

Biến môi trường thuận tiện nhưng vẫn có thể bị đọc bởi người có quyền trên máy, hệ thống chẩn đoán hoặc công cụ triển khai. Nó không tự cung cấp bảo mật tương đương secret manager.

## 10. Xác thực cấu hình và chẩn đoán kết nối

Tách vấn đề thành ba lớp để xử lý:

| Vị trí lỗi | Ví dụ | Hành động |
| --- | --- | --- |
| **Đọc cấu hình** | Không có `DB_PASSWORD`, file không tồn tại, `jdbc.url` rỗng | Báo tên khóa bị thiếu; kiểm tra nguồn/precedence; không in giá trị bí mật |
| **Tìm driver** | `No suitable driver found` hoặc URL không được nhận | Kiểm tra driver JAR tại runtime, URL và cơ chế phát hiện driver |
| **Mở kết nối** | Sai tài khoản, DB không chạy, TLS, firewall, timeout | Kiểm tra `SQLException`, SQLState, vendor code, log DB, mạng và tham số driver |

Có thể chẩn đoán bằng cách tách riêng lỗi thiếu cấu hình với lỗi JDBC:

~~~java
import java.io.IOException;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.SQLException;

try (Connection connection = JdbcConnectionFactory.open(
        Path.of("config/database.properties"))) {

    // Chỉ thực thi tác vụ sau khi đã có Connection.
} catch (IllegalArgumentException configError) {
    System.err.println("Configuration error: "
            + configError.getMessage());
} catch (IOException configIoError) {
    System.err.println("Cannot read DB configuration file");
} catch (SQLException jdbcError) {
    System.err.println("JDBC SQLState: " + jdbcError.getSQLState());
    System.err.println("JDBC vendor code: " + jdbcError.getErrorCode());
}
~~~

Ví dụ minh họa cố ý **không** in giá trị mật khẩu hoặc toàn bộ `Properties`. Trong ứng dụng thực tế, cần đưa lỗi vào hệ thống logging/monitoring có kiểm soát thay vì chỉ `System.err`.

Một khi đã mở kết nối, luôn đóng bằng `try-with-resources`. Nếu mở kết nối thất bại, không có `Connection` hợp lệ để đóng; nếu mở thành công và thao tác tiếp theo thất bại, Java sẽ đóng các tài nguyên đã được khai báo trong `try`.

## 11. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Tạo file `database.properties` thì JDBC tự đọc.” | Ứng dụng phải nạp file hoặc framework phải xử lý rồi truyền thuộc tính cho driver/`DataSource`. |
| “`java.util.Properties` tự bảo mật mật khẩu.” | Đó chỉ là cấu trúc dữ liệu key/value trong bộ nhớ. |
| “`jdbc.url` là tên key JDBC bắt buộc.” | Đây là key tùy ứng dụng; `DriverManager` nhận URL qua tham số riêng. |
| “Tên key TLS/timeout dùng giống nhau trên mọi JDBC driver.” | Các tùy chọn driver-specific phải tra theo từng nhà cung cấp. |
| “Cho cùng một key vào URL và Properties thì Properties luôn thắng.” | Thứ tự ưu tiên giữa hai nguồn ở tầng driver có thể do driver quyết định. |
| “`setConnectionTimeout` của pool là `connectTimeout` TCP.” | Một cái giới hạn thời gian chờ mượn pool, cái còn lại thường là giới hạn mở kết nối vật lý của driver. |
| “Đổi DB chỉ cần đổi URL, mọi thứ khác giữ nguyên.” | Có thể cần đổi driver JAR, SQL dialect, cấu hình bảo mật và các key driver-specific. |
| “Đưa mật khẩu vào biến môi trường thì an toàn tuyệt đối.” | Vẫn phải quản lý quyền đọc môi trường, log, cấu hình triển khai và vòng đời bí mật. |

## 12. Bài tập thực hành

Giả sử bạn có file `config/database.properties` chỉ chứa:

~~~properties
jdbc.url=jdbc:postgresql://localhost:5432/inventory
driver.connectTimeout=5
driver.sslmode=verify-full
~~~

Và hệ thống chạy với `DB_USER`, `DB_PASSWORD` được cấp an toàn.

1. **Đổi địa chỉ DB:** đặt `DB_JDBC_URL` sang một URL thử nghiệm khác. Với `JdbcConnectionFactory` ở mục 5, URL nào được dùng? *Đáp án:* URL biến môi trường (nếu không rỗng) được ưu tiên so với `jdbc.url` của file.
2. **Kiểm tra tên key:** driver thực tế nhận `driver.connectTimeout` hay `connectTimeout`? *Đáp án:* Mã ví dụ bỏ tiền tố `driver.` nên nhận `connectTimeout`.
3. **Thiếu mật khẩu:** nếu không có `DB_PASSWORD`, lỗi xuất hiện ở giai đoạn nào? *Đáp án:* Kiểm tra cấu hình ném `IllegalArgumentException` trước khi gọi `DriverManager`, không đợi DB báo lỗi.
4. **Thay sang MySQL:** liệu `driver.sslmode=verify-full` giữ nguyên có đúng không? *Đáp án:* Không được giả định; phải tra cú pháp và thuộc tính TLS tương ứng của MySQL JDBC driver.
5. **Bổ sung pool:** repository đang dùng `DriverManager.getConnection(...)` trực tiếp. Nên chuyển trách nhiệm nào? *Đáp án:* Tầng cấu hình tạo và sở hữu `DataSource`/pool, repository nhận `DataSource` và đóng `Connection` sau mỗi thao tác.

## 13. Ghi nhớ

**`Properties` là cầu nối từ cấu hình ứng dụng đến JDBC driver, nhưng không phải cơ chế tự đọc file hay bảo mật dữ liệu.** Hãy xác định rõ nơi lấy URL, username/password và thuộc tính driver; kiểm tra các giá trị bắt buộc; công khai thứ tự ưu tiên khi có nhiều nguồn; và tra tài liệu driver cho mọi key không được JDBC chuẩn hóa.

Với các tiện ích nhỏ, `DriverManager.getConnection(url, properties)` là cách rõ ràng để kết nối. Với ứng dụng server, thường nên cấu hình `DataSource`/pool ở một tầng riêng và chuyển nó vào repository. Trong cả hai cách, đóng kết nối đúng vòng đời, giữ bí mật khỏi mã nguồn/log và kiểm tra cấu hình TLS là những yêu cầu thiết yếu.
