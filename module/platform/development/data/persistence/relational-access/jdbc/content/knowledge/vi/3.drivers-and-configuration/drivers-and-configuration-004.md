# Cấu trúc JDBC URL và thuộc tính kết nối

## 1. JDBC URL nằm ở đâu trong kiến trúc kết nối?

**JDBC (Java Database Connectivity)** là API chuẩn của Java để truy cập cơ sở dữ liệu quan hệ. Khi ứng dụng cần chạy SQL, nó phải có một `java.sql.Connection`. JDBC driver do nhà cung cấp cơ sở dữ liệu hoặc bên thứ ba triển khai là thành phần hiểu giao thức kết nối thực tế.

Trong một ứng dụng Java, chuỗi **JDBC URL** thường trả lời những câu hỏi: dùng driver/giao thức nào, tìm máy chủ hay tệp cơ sở dữ liệu ở đâu, truy cập database hoặc service nào, và có những tùy chọn kết nối nào. Bên cạnh URL, driver có thể nhận **thuộc tính kết nối (connection properties)** như tên người dùng, mật khẩu, timeout và tùy chọn bảo mật.

Ví dụ một URL cho PostgreSQL:

~~~text
jdbc:postgresql://db.example.internal:5432/sales?sslmode=verify-full
~~~

URL trên chỉ là cấu hình minh họa. Ứng dụng cần có PostgreSQL JDBC driver, máy chủ có thể truy cập được, database `sales` tồn tại và TLS/certificate được cấu hình phù hợp.

**Mục tiêu bài học:** đọc được cấu trúc URL, nhận biết điểm giống và khác giữa các driver, truyền thuộc tính theo cách phù hợp, phân biệt các loại timeout, giữ bí mật thông tin xác thực và chẩn đoán những lỗi kết nối cơ bản.

## 2. Cú pháp JDBC URL tổng quát

JDBC định nghĩa dạng URL khái quát:

~~~text
jdbc:<subprotocol>:<subname>
~~~

Trong đó:

- **`jdbc:`** là tiền tố nhận diện URL của JDBC.
- **`subprotocol`** nhận diện loại driver hoặc giao thức JDBC, chẳng hạn `postgresql`, `mysql`, `sqlserver`, `oracle`, `sqlite`, `h2`.
- **`subname`** là phần thông tin kết nối mà driver đó tự quy định. Nó có thể chứa địa chỉ mạng, cổng, tên database, đường dẫn tệp, service name hoặc các tham số.

**Quan trọng:** chỉ bộ khung ở trên có tính tổng quát. JDBC **không quy định một mẫu host/port/database/query string chung cho tất cả driver**. Dấu `//`, `/`, `?`, `&`, dấu chấm phẩy, dấu `@` và cách mã hóa ký tự phụ thuộc driver. Vì vậy, đừng lấy một URL PostgreSQL rồi chỉ đổi `postgresql` thành `oracle` hoặc `sqlserver`.

Xét ví dụ PostgreSQL:

~~~text
jdbc:postgresql://db.example.internal:5432/sales?sslmode=verify-full
│    │          │                    │    │     │
│    │          │                    │    │     └─ Tùy chọn do pgJDBC hiểu
│    │          │                    │    └─────── Tên database: sales
│    │          │                    └──────────── Cổng TCP: 5432
│    │          └───────────────────────────────── Máy chủ: db.example.internal
│    └──────────────────────────────────────────── Subprotocol: postgresql
└───────────────────────────────────────────────── Prefix JDBC
~~~

Ở URL này, phần `?sslmode=verify-full` thuộc cú pháp tham số URL mà **pgJDBC** hỗ trợ, không phải một cú pháp bảo mật bắt buộc hoặc tương đương ở mọi driver.

### Những thông tin dễ nhầm

| Thành phần | Ý nghĩa thường gặp | Giới hạn cần nhớ |
|---|---|---|
| Host | Tên DNS hoặc địa chỉ máy chủ database | Driver có thể hỗ trợ nhiều host, instance hoặc tệp local |
| Port | Cổng dịch vụ database đang lắng nghe | Cổng mặc định tùy hệ quản trị; có thể đổi bằng cấu hình server |
| Database/catalog | Cơ sở dữ liệu logic muốn kết nối | Có driver dùng database name, service name hoặc định danh khác |
| Schema | Không gian tên của bảng trong database | Không nhất thiết là phần đường dẫn của JDBC URL |
| Username/password | Danh tính đăng nhập | Có thể truyền qua properties, cơ chế xác thực khác hoặc cấu hình nguồn kết nối |
| Options | TLS, timeout, charset, hành vi driver... | Tên, kiểu và đơn vị giá trị do driver quy định |

Ví dụ, với PostgreSQL, phần `/sales` chỉ **database**, không phải một bảng hay một schema tên `sales`. Schema mặc định và `search_path` là các khái niệm khác.

## 3. JDBC URL khác nhau thế nào giữa các driver?

Bảng sau dùng giá trị giả định `db.example.internal`, database/service `sales` và cổng thường thấy. Những giá trị này **không phải cấu hình cho mọi hệ thống**.

| Hệ quản trị / driver | JDBC URL minh họa | Đặc điểm cú pháp |
|---|---|---|
| PostgreSQL (pgJDBC) | `jdbc:postgresql://db.example.internal:5432/sales` | `//host:port/database` |
| MySQL Connector/J | `jdbc:mysql://db.example.internal:3306/sales` | `//host:port/database` |
| Microsoft SQL Server | `jdbc:sqlserver://db.example.internal:1433;databaseName=sales` | Thuộc tính kết nối thường phân tách bằng dấu `;` |
| Oracle JDBC Thin (service name) | `jdbc:oracle:thin:@//db.example.internal:1521/SALESPDB` | Prefix `oracle:thin:@//` rồi đến service name |
| SQLite JDBC (driver bên thứ ba) | `jdbc:sqlite:./data/sales.db` | Đường dẫn tới tệp, không nhất thiết có máy chủ TCP |
| H2 (in-memory) | `jdbc:h2:mem:sales` | Cơ sở dữ liệu trong bộ nhớ theo cú pháp của H2 |

### 3.1. Ví dụ URL PostgreSQL và MySQL với tùy chọn

~~~text
# PostgreSQL (pgJDBC)
jdbc:postgresql://db.example.internal:5432/sales?sslmode=verify-full&connectTimeout=10

# MySQL Connector/J
jdbc:mysql://db.example.internal:3306/sales?sslMode=VERIFY_IDENTITY&connectTimeout=5000
~~~

Đây là ví dụ **hai driver có tên thuộc tính và đơn vị thời gian riêng**:

- Với pgJDBC, `connectTimeout=10` có đơn vị **giây**.
- Với MySQL Connector/J, `connectTimeout=5000` có đơn vị **mili giây**.
- `sslmode=verify-full` của pgJDBC và `sslMode=VERIFY_IDENTITY` của Connector/J là các chế độ nhằm xác thực cả chứng chỉ và danh tính máy chủ, nhưng cấu hình trust store/CA cụ thể vẫn cần phù hợp môi trường.

Ngay cả khi tên thuộc tính giống nhau, **không được giả định đơn vị, giá trị mặc định hoặc hành vi giống nhau giữa driver**. Tham số của ví dụ cần được kiểm tra với đúng phiên bản driver mà dự án đang dùng.

### 3.2. Ví dụ SQL Server và Oracle

~~~text
# Microsoft JDBC Driver for SQL Server
jdbc:sqlserver://db.example.internal:1433;databaseName=sales;encrypt=true;trustServerCertificate=false

# Oracle JDBC Thin theo service name
jdbc:oracle:thin:@//db.example.internal:1521/SALESPDB
~~~

Với Microsoft SQL Server, dấu chấm phẩy phân tách các thuộc tính theo quy tắc của Microsoft JDBC Driver. Trong trường hợp giá trị chứa ký tự đặc biệt, driver có quy tắc escape riêng; không được áp dụng máy móc cách encode URL kiểu HTTP.

Với Oracle, cú pháp có thể thay đổi theo service name, SID hoặc connect descriptor. Ví dụ trên dùng **service name**, và không thể suy ra chuỗi tương đương từ URL PostgreSQL. Những tùy chọn TLS/Oracle Net cũng cần cấu hình theo hướng dẫn Oracle.

### 3.3. Cơ sở dữ liệu nhúng và đường dẫn tệp

`jdbc:sqlite:./data/sales.db` có thể tham chiếu tệp theo thư mục làm việc của chương trình, tùy driver. `jdbc:h2:mem:sales` thường chỉ đến một cơ sở dữ liệu bộ nhớ trong tiến trình. Quy tắc tạo, chia sẻ và vòng đời database nhúng phải xem tài liệu của driver: **không có quy tắc chung rằng đóng `Connection` sẽ luôn xóa hoặc luôn giữ database**.

Đường dẫn tương đối có thể khiến ứng dụng chạy đúng trên máy lập trình nhưng lại dùng một database khác khi triển khai dưới service/container vì **working directory** thay đổi. Nên kiểm soát đường dẫn tuyệt đối/volume trong môi trường triển khai nếu dùng database dạng tệp.

## 4. Thuộc tính kết nối gồm những nhóm nào?

Ngoài địa chỉ đích, kết nối thường cần nhiều nhóm thuộc tính:

| Nhóm | Ví dụ | Mục đích |
|---|---|---|
| Xác thực | `user`, `password`, authentication mode | Xác minh danh tính và quyền truy cập |
| Bảo mật đường truyền | TLS/SSL mode, CA/trust store, tên máy chủ cần xác thực | Bảo vệ dữ liệu truyền qua mạng và xác thực máy chủ |
| Thiết lập kết nối | Connection timeout, login timeout, keepalive | Kiểm soát thời gian chờ tạo kết nối và đặc tính socket |
| Đọc/ghi qua mạng | Socket/read timeout | Giới hạn thời gian chờ hoạt động mạng theo cách driver định nghĩa |
| Hành vi driver | Kiểu mã hóa, batch rewrite, prepared statement caching, server-side cursor | Tùy chỉnh cách driver làm việc với database |
| Khả năng chịu lỗi | Nhiều host, failover, load balancing, retry | Điều phối điểm đích và hành vi phục hồi nếu driver hỗ trợ |
| Phiên làm việc | Schema mặc định, application name, timezone, session options | Thiết lập ngữ cảnh cho connection khi được driver/database hỗ trợ |

**Không phải tất cả mục trong bảng là thuộc tính chuẩn của JDBC URL.** Một số chỉ có ở từng driver, một số phải cấu hình bằng `DataSource`, connection pool hoặc chạy câu lệnh SQL sau khi kết nối.

Chẳng hạn, `setAutoCommit(false)` và `setTransactionIsolation(...)` là phương thức của `java.sql.Connection`. `Statement.setQueryTimeout(...)` thuộc việc thực thi một câu SQL. Chúng không tự động trở thành tham số URL có cùng tên trên mọi driver.

## 5. Truyền cấu hình qua `DriverManager`

`java.sql.DriverManager` cung cấp nhiều cách mở kết nối. Hai overload thường gặp:

~~~java
Connection getConnection(String url, String user, String password)
Connection getConnection(String url, java.util.Properties info)
~~~

Với `Properties`, ta có thể đưa username/password và các thuộc tính mà driver hỗ trợ vào một đối tượng cấu hình:

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Properties;

public final class JdbcUrlConnectionExample {
    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu biến môi trường: " + key);
        }
        return value;
    }

    public static void main(String[] args) throws SQLException {
        // Ví dụ DB_JDBC_URL:
        // jdbc:postgresql://db.example.internal:5432/sales
        String jdbcUrl = requiredEnv("DB_JDBC_URL");
        Properties properties = new Properties();
        properties.setProperty("user", requiredEnv("DB_USER"));
        properties.setProperty("password", requiredEnv("DB_PASSWORD"));

        try (Connection connection =
                     DriverManager.getConnection(jdbcUrl, properties)) {
            DatabaseMetaData metadata = connection.getMetaData();
            System.out.println("Database: " + metadata.getDatabaseProductName());
            System.out.println("Driver: " + metadata.getDriverName());
        }
    }
}
~~~

Chương trình cần có JDBC driver đúng loại database trong dependency/runtime classpath hoặc module path và phải có thông tin truy cập thực tế trong biến môi trường. Ví dụ sử dụng `String.isBlank()` (Java 11+).

Với JDBC 4.0+, driver thường được tự đăng ký qua cơ chế Java service provider nếu driver JAR được đóng gói đúng, nên thông thường không cần `Class.forName("...Driver")`. Tuy nhiên, nếu driver không được tải, thiếu JAR, URL không được driver hỗ trợ hoặc module/class loader khác, `DriverManager` có thể ném `SQLException` với thông báo như `No suitable driver`.

**Không in `properties` hoặc password ra log.** Đối tượng `Properties` không che giấu bí mật khi bị chuyển thành chuỗi.

### 5.1. Đặt thuộc tính driver trong `Properties`

Chẳng hạn, nếu **chắc chắn đang dùng pgJDBC**, có thể viết:

~~~java
Properties options = new Properties();
options.setProperty("user", requiredEnv("DB_USER"));
options.setProperty("password", requiredEnv("DB_PASSWORD"));
options.setProperty("sslmode", "verify-full");   // pgJDBC
options.setProperty("connectTimeout", "10");     // pgJDBC: giây
options.setProperty("socketTimeout", "30");      // pgJDBC: giây

try (Connection connection =
             DriverManager.getConnection(requiredEnv("DB_JDBC_URL"), options)) {
    // Thực thi SQL trong phạm vi Connection còn mở.
}
~~~

Đoạn này là ví dụ riêng cho **PostgreSQL JDBC driver**, không phải danh sách properties chuẩn để dùng nguyên vẹn với MySQL, SQL Server hoặc Oracle. `sslmode=verify-full` chỉ hoạt động khi chứng chỉ CA/tên máy chủ có thể được xác thực đúng cách.

Nếu một thuộc tính được đặt **đồng thời trong URL và `Properties`**, không nên dựa vào giả định chung về độ ưu tiên: cách xử lý trùng tên do driver xác định. Hãy khai báo mỗi giá trị ở **một nơi** khi có thể và kiểm tra tài liệu driver nếu dự án cần quy tắc precedence cụ thể.

### 5.2. Chú ý khi URL chứa ký tự đặc biệt

Với driver dùng dấu `?` và `&` cho tùy chọn, dấu `&` có vai trò ngăn cách thuộc tính. Trong ví dụ SQL Server, dấu `;` là ký tự ngăn cách thường dùng. Đưa password, path hoặc ký tự đặc biệt trực tiếp vào URL có thể làm driver hiểu nhầm.

Không có quy tắc chung đảm bảo `URLEncoder.encode(...)` đúng cho mọi phần của JDBC URL. Cách escape và mã hóa tên database, tên người dùng hoặc giá trị property phải tuân theo **driver tương ứng**. Một cách giảm rủi ro là để credential trong `Properties`/secret configuration và URL chỉ chứa vị trí kết nối, miễn là cách đó được driver hỗ trợ.

## 6. `DataSource`: cách cấu hình kết nối cho ứng dụng lâu dài

`javax.sql.DataSource` là abstraction cung cấp `Connection` mà ứng dụng sử dụng. Một implementation có thể mở kết nối trực tiếp, hoặc được cấu hình để dùng **connection pool**. Pool là đặc tính của implementation và cấu hình, **không phải mặc định của mọi `DataSource`**.

~~~mermaid
flowchart TD
    C["Cấu hình deployment<br/>URL, credentials, TLS, timeouts"] --> DS["DataSource implementation<br/>(có thể dùng connection pool)"]
    APP["Repository / Service"] -->|"getConnection()"| DS
    DS -->|"java.sql.Connection"| APP
    APP -->|"PreparedStatement / SQL"| DB[("Database")]
    APP -->|"close()"| DS
~~~

Mã repository chỉ cần biết interface:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderCounter {
    private final DataSource dataSource;

    public OrderCounter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long countOrders() throws SQLException {
        String sql = "SELECT COUNT(*) FROM orders";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql);
             ResultSet result = statement.executeQuery()) {
            if (!result.next()) {
                throw new SQLException("Truy vấn đếm không trả về hàng");
            }
            return result.getLong(1);
        }
    }
}
~~~

Chi tiết tạo `DataSource` như tên property chứa JDBC URL, username/password, giới hạn pool, timeout khi chờ mượn kết nối phụ thuộc **driver, connection-pool library hoặc framework**. Không có `DataSource.setJdbcUrl(...)` chuẩn áp dụng cho mọi implementation; ví dụ HikariCP hay các implementation của vendor có cách cấu hình riêng.

Lưu ý rằng ứng dụng vẫn phải `close()` connection trong `try-with-resources`. Với pool, lời gọi này thường hoàn trả kết nối logic về pool để tái sử dụng.

### So sánh hai điểm vào

| Câu hỏi | `DriverManager` | `DataSource` |
|---|---|---|
| Cần truyền JDBC URL ở đâu? | Trực tiếp cho `getConnection(...)` | Ở cấu hình implementation hoặc framework |
| API trả về | `java.sql.Connection` | `java.sql.Connection` |
| Phân tách cấu hình khỏi repository | Cần tự tổ chức | Tự nhiên hơn với DI và cấu hình tập trung |
| Connection pooling | Không được `DriverManager` tự cung cấp | Có thể có nếu implementation dùng pool |
| Thường phù hợp | Ví dụ học tập, công cụ nhỏ | Ứng dụng backend nhiều request, production |

## 7. Phân biệt các loại timeout liên quan kết nối

Đặt một tham số `timeout=30` mơ hồ rất dễ gây hiểu nhầm. Các giai đoạn khác nhau có thể có giới hạn thời gian riêng:

~~~mermaid
flowchart LR
    A["Chờ pool cấp Connection"] --> B["Mở socket / đăng nhập"]
    B --> C["Thực thi SQL"]
    C --> D["Chờ dữ liệu trên socket"]
    D --> E["Đọc ResultSet"]
    E --> F["Đóng / trả về pool"]
~~~

| Loại timeout | Giới hạn điều gì? | Đặt ở đâu? |
|---|---|---|
| Pool acquisition timeout | Chờ mượn một connection khả dụng từ pool | Cấu hình thư viện pool; không có tên chung toàn JDBC |
| Login timeout | Chờ thiết lập kết nối/đăng nhập | `DriverManager.setLoginTimeout(int)` hoặc `DataSource.setLoginTimeout(int)`, đơn vị giây; mức độ tuân thủ phụ thuộc driver |
| Connect timeout | Một phần hoặc toàn bộ quá trình tạo kết nối mạng theo driver | Property riêng của driver; **kiểm tra đơn vị** |
| Socket/read timeout | Thời gian chờ thao tác đọc mạng theo driver/socket | Thuộc tính riêng của driver |
| Query timeout | Thời gian tối đa cho một `Statement` thực thi theo JDBC | `Statement.setQueryTimeout(int)`, đơn vị giây; cách thực thi/hủy query tùy driver/database |
| Network timeout của Connection | Thời gian chờ cho hoạt động mạng theo `Connection` | `Connection.setNetworkTimeout(executor, milliseconds)` khi driver hỗ trợ |

Ví dụ:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement("SELECT id FROM orders WHERE id = ?")) {

    statement.setQueryTimeout(15); // JDBC: giây
    statement.setLong(1, orderId);

    try (ResultSet result = statement.executeQuery()) {
        if (result.next()) {
            System.out.println(result.getLong("id"));
        }
    }
}
~~~

Đoạn này giả định `dataSource` và `orderId` đã tồn tại trong ngữ cảnh. `setQueryTimeout(15)` không thay thế cho connect timeout, socket timeout hoặc thời gian chờ lấy kết nối từ pool. Driver cũng có thể có giới hạn và hành vi khác nhau khi query bị hủy do timeout.

**Ví dụ điển hình về đơn vị:** `connectTimeout=10` của pgJDBC là 10 **giây**; `connectTimeout=5000` của MySQL Connector/J là 5000 **mili giây**. Sao chép giá trị 10 giữa hai driver có thể làm kết nối thất bại gần như ngay lập tức.

## 8. TLS, thông tin xác thực và cách giữ bí mật cấu hình

JDBC URL thường chứa địa chỉ đích và các tùy chọn TLS. Khi kết nối qua mạng không hoàn toàn tin cậy, cần quan tâm cả **mã hóa đường truyền** lẫn **xác thực máy chủ**:

1. **Mã hóa:** bảo vệ dữ liệu truyền khỏi bị đọc trộm trên đường truyền.
2. **Xác thực chứng chỉ:** tin cậy CA/certificate chain đúng.
3. **Xác thực tên máy chủ:** xác minh chứng chỉ được cấp cho đúng hostname, giảm nguy cơ kết nối nhầm máy chủ.

Ví dụ `sslmode=verify-full` (pgJDBC) hoặc `sslMode=VERIFY_IDENTITY` (Connector/J) thể hiện ý định xác thực máy chủ theo khả năng của driver. Với SQL Server, `encrypt=true;trustServerCertificate=false` thường được dùng để yêu cầu mã hóa đồng thời xác minh chứng chỉ theo cấu hình driver. Cần kiểm tra yêu cầu CA/trust store, tên DNS và phiên bản driver thực tế.

**Không nên chữa lỗi chứng chỉ bằng cách tắt xác thực máy chủ** như `trustServerCertificate=true` hoặc chế độ tương đương trong production. Cách đúng là sửa chứng chỉ, hostname hoặc trust configuration theo chính sách hệ thống.

### Nơi lưu cấu hình

| Cách lưu | Đánh giá |
|---|---|
| Username/password hard-code trong mã Java | Tránh: dễ lộ qua Git, log và artifact |
| Password chứa trực tiếp trong JDBC URL | Hạn chế: URL có thể xuất hiện trong log, stack trace hoặc công cụ giám sát |
| Environment variables cho runtime | Tốt hơn hard-code trong ví dụ/triển khai đơn giản; vẫn cần kiểm soát quyền truy cập môi trường |
| Secret manager và cấu hình được cấp quyền | Phù hợp hơn ở môi trường production nhiều dịch vụ |
| Tài khoản database quyền rộng dùng chung | Tránh: vi phạm nguyên tắc cấp quyền tối thiểu |

Mã ví dụ ở trên đọc `DB_JDBC_URL`, `DB_USER`, `DB_PASSWORD` qua biến môi trường, **không** xuất giá trị password. Ở môi trường vận hành, cần tổ chức cơ chế cấp phát, xoay vòng credential và quyền truy cập phù hợp.

### Mô hình cấu hình cho từng môi trường

~~~text
Development:  URL -> localhost / database thử nghiệm
Test:         URL -> database riêng, dữ liệu test
Staging:      URL -> database staging, credentials staging
Production:   URL -> database production, TLS xác thực, secrets production
~~~

Chương trình có thể dùng **cùng mã kết nối** và nhận URL/thuộc tính từ cấu hình từng môi trường. Cần kiểm tra kỹ tên môi trường, quyền tài khoản, khả năng kết nối, migration và dữ liệu trước khi chạy thao tác ghi; không nên copy credential production vào bài tập hoặc bản cấu hình mẫu trong repository.

## 9. Các trường hợp URL đặc biệt cần chú ý

### 9.1. Địa chỉ IPv6 và DNS

Một số driver dùng cú pháp host dạng URL với IPv6 đặt trong dấu ngoặc vuông, ví dụ `[2001:db8::10]`. Nhưng hỗ trợ, tên host và cách phân giải vẫn tùy driver. Dùng tên DNS ổn định thường giúp cấu hình TLS hostname dễ quản lý hơn, vì nhiều chế độ TLS cần chứng chỉ khớp với host trong URL.

Địa chỉ loopback `localhost` chỉ chính môi trường đang chạy ứng dụng. Trong container, `localhost` thường là **container đó**, không mặc nhiên trỏ đến database chạy trên máy host hoặc container khác.

### 9.2. Nhiều host, failover, load balancing

Một số driver hỗ trợ khai báo nhiều host hoặc URL đặc biệt cho primary/replica. Cú pháp và thuật toán chọn host, retry, cân bằng tải và định tuyến read-only rất khác nhau.

Không nên suy rằng chuỗi có nhiều host sẽ tự cung cấp failover an toàn, hay rằng driver sẽ tự chọn replica khi một câu SQL chỉ đọc. Cần xem tài liệu driver và mô hình transaction/topology của database. Retry một thao tác ghi không rõ kết quả có thể tạo ghi trùng.

### 9.3. Default schema, timezone và session state

Những thuộc tính như schema mặc định hoặc timezone có thể được cấu hình bằng property của driver, biến phía server hoặc SQL ở đầu phiên. Giá trị nào được hỗ trợ và ảnh hưởng đến loại dữ liệu nào đều tùy database.

Ví dụ, **tên database trong URL không đủ để xác định timezone của một cột `TIMESTAMP`**. Ứng dụng cần quy ước kiểu dữ liệu, timezone, driver conversion và cách biểu diễn thời điểm theo từng hệ quản trị.

### 9.4. Ký tự đặc biệt trong tên database hoặc property

Từng driver có thể dùng quy tắc escape riêng cho dấu `;`, `&`, `=`, khoảng trắng, dấu gạch chéo và các ký tự không ASCII. Với URL nhúng đường dẫn tệp, phải phân biệt cú pháp filesystem với cú pháp URL. Luôn đọc hướng dẫn chính thức của driver đang dùng và kiểm tra bằng kết nối thực tế, thay vì áp dụng một hàm URL-encoding chung cho mọi trường hợp.

## 10. Chẩn đoán lỗi cấu hình thường gặp

`SQLException` có thể chứa `getSQLState()`, `getErrorCode()`, thông điệp và các lỗi liên kết. SQLState thường giúp phân loại, nhưng **mã vendor và nội dung thông báo không đồng nhất giữa driver**.

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| `No suitable driver` | Thiếu JDBC driver, URL sai subprotocol hoặc driver chưa được nạp | Kiểm tra dependency runtime, prefix URL và driver phù hợp |
| Không phân giải được host / connection refused | Sai DNS, host, port, firewall, database chưa lắng nghe | Kiểm tra mạng từ đúng máy/container chạy ứng dụng và endpoint thực tế |
| Kết nối chờ quá lâu | Connect/login/socket timeout chưa cấu hình đúng; mạng không phản hồi | Đối chiếu từng timeout và **đơn vị** theo driver |
| Authentication failed | Sai username/password, cơ chế auth hoặc cấu hình server | Kiểm tra secret, người dùng và quyền truy cập; không log mật khẩu |
| Database không tồn tại / không chọn được | Tên database hoặc service name sai | Xác minh đích bằng công cụ quản trị và cú pháp URL vendor |
| TLS handshake / certificate failed | Trust store/CA, hostname, chứng chỉ, phiên bản TLS không phù hợp | Xác minh chứng chỉ và chế độ xác thực máy chủ; tránh tắt verify |
| Connection pool exhausted | Thiếu đóng connection, truy vấn giữ kết nối lâu hoặc pool thiếu capacity | Kiểm tra `try-with-resources`, transaction, pool metrics |
| Không tìm thấy bảng dù kết nối thành công | Sai database/schema, `search_path`, quyền hoặc chữ hoa/chữ thường | Kiểm tra database hiện tại, schema và câu SQL |
| Sai charset/ngày giờ | Cấu hình driver, database hoặc biểu diễn kiểu dữ liệu không thống nhất | Xem kiểu SQL, charset, timezone và quy tắc chuyển đổi |

### Mẫu ghi nhận lỗi đủ hữu ích nhưng tránh lộ bí mật

~~~java
try (Connection connection = dataSource.getConnection()) {
    System.out.println("Connected: " + connection.isValid(2));
} catch (SQLException ex) {
    System.err.println("SQLState: " + ex.getSQLState());
    System.err.println("Vendor code: " + ex.getErrorCode());
    System.err.println("Type: " + ex.getClass().getSimpleName());
    // Ghi thông điệp chi tiết qua logger được kiểm soát,
    // sau khi bảo đảm không rò rỉ URL chứa credentials.
    throw ex;
}
~~~

Đoạn mã minh họa nằm trong phương thức có `dataSource` và khai báo `throws SQLException`. `Connection.isValid(int timeout)` dùng thời gian chờ tính bằng **giây**. Nó kiểm tra connection còn hợp lệ ở thời điểm gọi, nhưng không bảo đảm rằng mọi truy vấn tiếp theo đều thành công.

Nếu cần chẩn đoán chuyên sâu, hãy ghi **tên môi trường, loại driver và version, SQLState, exception type, nhóm lỗi và thời điểm xảy ra**, đồng thời loại bỏ username/password/token, URL nhạy cảm và dữ liệu người dùng khỏi log.

## 11. Nguyên tắc thực hành khi chuẩn bị JDBC URL

1. **Xác định chính xác driver và phiên bản** trước khi viết URL. Đọc tài liệu driver để lấy cú pháp host, port, database/service và tên properties.
2. **Tách cấu hình theo môi trường.** Cấp URL, credential và TLS/trust từ configuration/secret provider thay vì gắn cứng trong mã.
3. **Đặt tham số có kiểm soát.** Tránh khai báo cùng property tại nhiều chỗ; ghi rõ đơn vị timeout và kiểm thử giá trị thực tế.
4. **Ưu tiên xác thực TLS đầy đủ** khi triển khai trên mạng. Chuẩn bị chứng chỉ/trust store và hostname hợp lệ.
5. **Dùng `DataSource` được cấu hình tập trung** cho ứng dụng lâu dài, với pool nếu tải yêu cầu; tránh tạo connection mới không cần thiết cho mỗi thao tác nội bộ.
6. **Đóng `Connection`, `Statement` và `ResultSet`** bằng `try-with-resources`. `close()` đặc biệt quan trọng khi dùng connection pool.
7. **Kiểm tra kết nối từ chính môi trường chạy ứng dụng**: DNS, port, credential, TLS, database/service và quyền.
8. **Không đồng nhất các loại timeout.** Một giới hạn chờ truy vấn không thay thế cho timeout tạo socket hoặc chờ pool.

## 12. Câu hỏi tự kiểm tra

1. Trong URL `jdbc:postgresql://db.internal:5432/orders`, phần nào là subprotocol và phần nào là tên database?
2. Vì sao `jdbc:mysql://...` không thể được chuyển thành URL SQL Server chỉ bằng cách đổi `mysql` thành `sqlserver`?
3. Có thể đưa `user` và `password` vào `Properties` thay vì đặt trong URL không? Điều gì cần kiểm tra nếu cùng property đã nằm trong URL?
4. Với pgJDBC, `connectTimeout=5` khác gì về đơn vị so với cùng số 5 trong MySQL Connector/J?
5. `Statement.setQueryTimeout(30)` có đảm bảo một yêu cầu chờ connection từ pool kết thúc sau 30 giây không? Vì sao?
6. Nếu TLS thất bại do hostname không khớp chứng chỉ, vì sao tắt kiểm tra certificate không phải giải pháp phù hợp cho production?
7. Tại sao `jdbc:sqlite:./data/app.db` có thể trỏ đến tệp khác khi ứng dụng được chuyển từ máy lập trình sang container?

**Ghi nhớ:** JDBC URL cho driver biết **cách và nơi kết nối**, nhưng cú pháp và thuộc tính cụ thể nằm trong hợp đồng của **từng driver**. Mã Java có thể lấy `Connection` bằng `DriverManager` hoặc `DataSource`. Thiết kế cấu hình tốt phải đồng thời kiểm soát **đúng đích, xác thực, TLS, timeout, quản lý kết nối và bí mật**.

### Tài liệu tham khảo

- [Java SE 21 — `DriverManager`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/DriverManager.html)
- [Java SE 21 — `Connection`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Connection.html)
- [Java SE 21 — `javax.sql.DataSource`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/javax/sql/DataSource.html)
- [PostgreSQL JDBC Driver — Connection parameters](https://jdbc.postgresql.org/documentation/use/)
- [MySQL Connector/J — Connection URL syntax](https://dev.mysql.com/doc/connector-j/en/connector-j-reference-jdbc-url-format.html)
- [Microsoft JDBC Driver for SQL Server — Building the connection URL](https://learn.microsoft.com/en-us/sql/connect/jdbc/building-the-connection-url)
- [Oracle JDBC — Data Sources and URLs](https://docs.oracle.com/en/database/oracle/oracle-database/21/jjdbc/data-sources-and-URLs.html)
