# Connection pool, timeout và tương tác với virtual thread

> **Phạm vi:** Java 27 — chương **Truy cập cơ sở dữ liệu**. Bài học trình bày vòng đời JDBC connection, cách sử dụng connection pool, phân biệt các lớp timeout, thiết kế tác vụ dùng **virtual threads** và chẩn đoán tình trạng chờ kết nối. Chỉ dùng các cơ chế còn được hỗ trợ; các ví dụ JDBC dựa trên Java SE 27, còn phần HikariCP được ghi rõ là thư viện bên thứ ba và cấu hình cần kiểm tra theo phiên bản triển khai.

## 1. Bài toán: virtual threads rất nhiều, kết nối database vẫn hữu hạn

Virtual threads cho phép ứng dụng có nhiều tác vụ chờ I/O mà không cần cấp một platform thread cho mỗi tác vụ trong suốt thời gian chờ. Nhưng số lượng **database connections** đồng thời vẫn bị giới hạn bởi database, cấu hình pool, khả năng CPU/đĩa và chính workload SQL.

Ví dụ một dịch vụ có:

- 5.000 virtual threads đang xử lý các yêu cầu.
- Một JDBC connection pool cấu hình tối đa 12 connections.
- Mỗi tác vụ cần một connection để chạy truy vấn.
- Nhiều truy vấn mất thời gian vì database hoặc network.

Trong mô hình **mỗi tác vụ mượn một connection tại một thời điểm**, tối đa khoảng 12 tác vụ có thể giữ connection từ pool này cùng lúc. Các tác vụ còn lại chờ pool cấp connection hoặc bị từ chối khi quá thời hạn chờ.

~~~text
  5.000 request tasks (virtual threads)
                    │
                    ▼
             DataSource.getConnection()
                    │
                    ▼
          ┌───────────────────────┐
          │ JDBC connection pool  │
          │ maxPoolSize = 12      │
          │  ├── 12 đang mượn     │──▶ Database
          │  └── còn lại đang chờ │
          └───────────────────────┘
                    │
                    └─ Quá thời hạn mượn → SQLException
~~~

**Virtual threads không phải database connections.** Cần tách ba tài nguyên:

1. **Virtual thread:** đơn vị đại diện cho công việc ứng dụng.
2. **JDBC connection:** phiên làm việc có trạng thái với database, thường tốn tài nguyên đáng kể.
3. **Pool:** bộ quản lý connections có giới hạn, chính sách tái sử dụng, chờ, kiểm tra kết nối và loại bỏ kết nối hỏng.

### 1.1. Những câu hỏi cần trả lời

Sau bài học, bạn nên xác định được:

- Vì sao `DataSource` **không đồng nghĩa** mọi implementation đều là pool.
- Khi nào `Connection.close()` trả logical connection về pool.
- `connectionTimeout` của pool khác `setQueryTimeout` và `setNetworkTimeout` thế nào.
- Vì sao một virtual thread chờ pool **không tự chứng minh carrier bị pin**.
- Cách chọn giới hạn kết nối theo database capacity và thời gian giữ connection.
- Khi nào timeout có thể khiến trạng thái transaction **không xác định**, không được retry mù quáng.
- Những số liệu cần xem khi p95/p99 latency tăng và pool có nhiều pending requests.

## 2. DataSource, Connection và pool: khái niệm cốt lõi

`javax.sql.DataSource` là interface được Java SE cung cấp trong module `java.sql`. Nó là một **factory lấy connection**, và được tài liệu Oracle khuyến nghị thay cho việc viết trực tiếp `DriverManager.getConnection(...)` cho các ứng dụng cần quản lý DataSource có cấu hình.

Có nhiều kiểu implementation `DataSource`:

- **Basic DataSource:** mỗi lần gọi có thể tạo connection vật lý mới.
- **Pooled DataSource:** kết nối tham gia một connection pool qua pool manager.
- **DataSource với transaction management:** được framework/container quản lý thêm về transaction, có thể có pooling.

**Không phải mọi `DataSource` tự động tạo pool.** Hợp đồng của interface không yêu cầu một số kết nối tối đa, hàng đợi mượn kết nối hay cơ chế metrics cụ thể. Những thuộc tính đó đến từ implementation hoặc framework cung cấp DataSource.

### 2.1. Phân biệt physical connection và logical connection

Với pool điển hình:

~~~text
Ứng dụng                    Pool manager                  Database
    │                           │                            │
    ├─ getConnection() ────────▶│                            │
    │                           ├─ lấy connection khả dụng    │
    │◀──── connection handle ───┤                            │
    │                           │                            │
    ├─ prepareStatement(...) ───────────────────────────────▶│
    │◀──────────── ResultSet ────────────────────────────────┤
    │                           │                            │
    ├─ connection.close() ─────▶│ đánh dấu trả connection     │
    │                           │ (có thể giữ socket/phiên DB)│
    └───────────────────────────┴────────────────────────────┘
~~~

Connection mà code nhận được có thể là **wrapper/proxy logic**. `close()` trên handle thường có nghĩa **trả connection về pool** nếu pool còn sử dụng được, chứ không nhất thiết đóng TCP socket hoặc physical database session tại thời điểm đó.

Nhưng đây là đặc tính của **pooled implementation**, không phải cam kết rằng `Connection.close()` luôn trả connection về pool. Với basic `DataSource` hoặc `DriverManager`, close thường giải phóng connection vật lý.

**Quy tắc đúng trong mọi trường hợp:** code đã mượn connection phải gọi `close()` khi kết thúc scope sở hữu, tốt nhất qua `try-with-resources`. Để pool quyết định việc tái sử dụng physical connection.

### 2.2. Pool không làm tăng số transaction database có thể xử lý vô hạn

Pool giúp tái sử dụng việc tạo/xác thực connection, tránh mở–đóng physical connection cho mỗi thao tác, và giới hạn số phiên DB được cấp cho ứng dụng. Nó **không tự tối ưu truy vấn SQL**, không làm index xuất hiện, cũng không tăng số CPU/IOPS của database.

Tăng `maximumPoolSize` quá cao còn có thể:

- Tăng áp lực memory và connection state tại DB.
- Tăng contention trên locks, I/O, CPU của DB.
- Tăng số transaction đang mở và rủi ro deadlock.
- Vượt tổng số connection database cho phép khi có nhiều replicas.
- Làm p99 latency tệ hơn dù hàng đợi ở pool có vẻ ngắn đi.

## 3. Một request nên sở hữu connection trong phạm vi nhỏ nhất hợp lý

Ví dụ repository chỉ đọc một bản ghi và không chia sẻ `Connection` giữa các task.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import java.util.Optional;
import javax.sql.DataSource;

public final class CustomerRepository {
    private final DataSource dataSource;

    public record Customer(long id, String displayName) {}

    public CustomerRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public Optional<Customer> findById(long id) throws SQLException {
        if (id <= 0) {
            throw new IllegalArgumentException("id must be positive");
        }

        String sql = """
                SELECT id, display_name
                FROM customers
                WHERE id = ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setLong(1, id);
            statement.setQueryTimeout(3); // seconds, driver-dependent

            try (ResultSet rows = statement.executeQuery()) {
                if (!rows.next()) {
                    return Optional.empty();
                }
                return Optional.of(new Customer(
                        rows.getLong("id"),
                        rows.getString("display_name")));
            }
        }
    }
}
~~~

**Hợp đồng ví dụ:**

- `dataSource` được tạo/cấu hình bên ngoài repository và có thể là pooled DataSource.
- Mỗi lần gọi `findById` mượn một connection riêng trong thời gian cần thực thi.
- `PreparedStatement` dùng placeholder `?`; không nối giá trị ID từ input vào SQL.
- `setQueryTimeout(3)` là yêu cầu timeout tính bằng **giây** cho statement, tùy JDBC driver/DB hỗ trợ và hành vi cancel.
- `Optional.empty()` biểu diễn **truy vấn thành công nhưng không thấy bản ghi**.
- Lỗi mượn connection, SQL, timeout hoặc I/O → `SQLException` hoặc subtype phù hợp, **không** bị chuyển thành `Optional.empty()`.
- `ResultSet` đóng trước `PreparedStatement`; statement đóng trước connection khi rời `try-with-resources`.

Code trên là JDBC chuẩn Java 27. Để chạy thật, cần schema `customers(id, display_name)`, JDBC driver và `DataSource` đã cấu hình phù hợp với database. Không có database nhúng nào được Java SE tự cung cấp.

### 3.1. Vì sao không giữ connection trong field của repository?

Sai về thiết kế:

~~~java
// Không làm kiểu này với một repository chia sẻ giữa nhiều request:
class BadRepository {
    private final Connection sharedConnection;

    BadRepository(Connection sharedConnection) {
        this.sharedConnection = sharedConnection;
    }
}
~~~

`Connection` có trạng thái phiên như auto-commit, transaction, isolation và những statement/result set đang hoạt động. Không được mặc định một connection được chia sẻ đồng thời giữa nhiều virtual threads là an toàn. Hợp đồng thread-safety của JDBC driver có thể khác nhau, và việc dùng chung connection rất dễ tạo transaction interference.

**Chia sẻ `DataSource`**, không chia sẻ một connection mutable giữa các request độc lập. Mỗi unit of work mượn handle, dùng và trả đúng hạn.

### 3.2. Không trả ResultSet/Stream còn phụ thuộc connection đã đóng

Sai:

~~~java
// Không trả ResultSet sau khi connection/statement đã đóng:
// try (Connection c = ds.getConnection();
//      PreparedStatement ps = c.prepareStatement(sql)) {
//     return ps.executeQuery();
// }
~~~

Sau khi rời block, tài nguyên cần cho `ResultSet` đã bị đóng hoặc không còn hợp lệ. Hãy **materialize dữ liệu cần trả** thành record, list hoặc domain object trước khi scope kết thúc. Nếu cần streaming kết quả rất lớn, phải thiết kế ownership và lifecycle xuyên suốt quá trình duyệt, có giới hạn thời gian và backpressure.

## 4. Vòng đời mượn–trả connection và những điểm làm pool cạn

Một lượt mượn connection (*borrow/checkout*) thường đi qua:

1. Caller gọi `dataSource.getConnection()`.
2. Pool tìm connection idle hợp lệ, hoặc tạo mới nếu chưa đạt giới hạn và còn khả năng.
3. Nếu không có connection, caller có thể **chờ** trong thời gian do pool quy định.
4. Caller nhận logical handle, dùng statement/transaction.
5. Caller đóng statement/result set và `Connection.close()`.
6. Pool reset/trả/loại connection theo chính sách implementation và tình trạng phiên.

Các vấn đề thường gặp:

| Tình huống | Tác động |
| --- | --- |
| Không gọi `close()` | Connection bị giữ, số idle giảm dần, các request khác chờ |
| Transaction mở lâu | Connection bận trong thời gian không làm SQL; có thể giữ DB locks |
| Query chậm | Mỗi query giữ connection lâu hơn, giảm throughput pool |
| Lấy connection trước khi gọi HTTP API | Kéo dài thời gian sở hữu khi chờ dịch vụ ngoài |
| Pool size quá lớn | DB phải phục vụ nhiều session hơn khả năng tối ưu |
| Pool size quá nhỏ với workload đã được đo | Nhiều request chờ acquire dù DB còn khả năng |
| Timeout thiếu hoặc quá dài | Hàng đợi tăng, latency lan truyền sang các tầng khác |
| Không có timeout/cancellation phù hợp | Một số tác vụ có thể bị treo rất lâu |
| Connection được trả nhưng trạng thái session không reset đúng | Caller sau có thể thừa hưởng auto-commit/schema/isolation không mong muốn |

**Giữ connection chỉ khi thực sự cần DB** là cách rất hiệu quả để nâng khả năng phục vụ đồng thời mà không cần tăng pool size.

## 5. Các lớp timeout: cùng tên nhưng khác phạm vi

“Database timeout 5 giây” là mô tả **thiếu thông tin**. Có nhiều giai đoạn chờ khác nhau, thường thuộc các thành phần khác nhau.

| Thời hạn | Đang chờ điều gì? | Cấp cấu hình thông dụng | Đơn vị |
| --- | --- | --- | --- |
| Pool acquisition timeout | Chờ pool cấp một logical connection | Pool implementation, ví dụ HikariCP `connectionTimeout` | Thường ms |
| Database login/connect timeout | Tạo kết nối vật lý, handshake và đăng nhập DB | JDBC driver, `DataSource.setLoginTimeout`, driver URL/properties | Tùy API, thường giây |
| Connection validation timeout | Kiểm tra physical connection còn sống | Pool, `Connection.isValid(timeout)` | Tùy API |
| Statement/query timeout | Chờ statement thực thi / driver hủy câu SQL | `Statement.setQueryTimeout(seconds)` | Giây |
| Network timeout | Chờ DB phản hồi cho một request JDBC | `Connection.setNetworkTimeout(executor, milliseconds)` hoặc driver socket settings | Ms |
| Transaction timeout | Giới hạn thời gian một transaction được phép hoạt động | Framework/transaction manager/DB, không có một property JDBC chung duy nhất | Tùy framework |
| Request/deadline timeout | Ngân sách thời gian end-to-end của HTTP/job | Tầng ứng dụng/HTTP server/task owner | Ms hoặc `Duration` |
| Idle timeout của pool | Bao lâu một idle connection có thể được nghỉ hưu | Pool implementation | Thường ms |
| Max lifetime | Thời gian sống tối đa của physical connection trước khi được thay | Pool implementation | Thường ms |

### 5.1. Ba bẫy quan trọng

**Thứ nhất:** timeout mượn connection ở pool **không** giới hạn thời gian chạy SQL sau khi connection được cấp.

**Thứ hai:** statement query timeout **không** thay thế timeout mượn connection. Nếu nhiều request không mượn được connection, chúng có thể thất bại trước khi tạo statement.

**Thứ ba:** transaction timeout hoặc deadline của HTTP request **không tự áp dụng** lên mọi JDBC driver và mọi network operation. Cần kiểm tra cơ chế truyền timeout/cancellation của framework và driver đang dùng.

### 5.2. Trục thời gian của một yêu cầu

~~~text
Request bắt đầu
    │
    ├── chờ pool connection ───[pool acquisition timeout]
    │
    ├── execute SQL ──────────[query timeout / network timeout]
    │
    ├── xử lý dữ liệu
    │
    ├── commit/rollback ──────[DB/driver timeout phù hợp]
    │
    └── phản hồi
          │
          └──────────────[end-to-end request deadline]──────
~~~

Một request có thể mất **nhiều hơn** một query timeout vì nó còn bao gồm thời gian mượn, mapping kết quả, commit và các bước khác. Đặt `queryTimeout=3` giây không có nghĩa `requestDeadline=3` giây.

## 6. JDBC API timeout theo Java SE 27

### 6.1. DataSource.setLoginTimeout(int seconds)

~~~java
import javax.sql.DataSource;

static void configureLoginTimeout(DataSource source)
        throws java.sql.SQLException {
    source.setLoginTimeout(5); // seconds
}
~~~

`setLoginTimeout(5)` là giới hạn mà DataSource/driver sử dụng khi cố **thiết lập kết nối với DB** theo hợp đồng JDBC. Giá trị 0 mang nghĩa dùng timeout hệ thống mặc định nếu có; nếu không, có thể là không có giới hạn.

Đừng coi API này là `connectionTimeout` của HikariCP: cái thứ hai thường điều khiển **thời gian client chờ pool cho mượn connection**. Với pooled DataSource, cách hai timeout được áp dụng cần xác minh theo implementation và driver.

### 6.2. Statement.setQueryTimeout(int seconds)

~~~java
try (var connection = dataSource.getConnection();
     var statement = connection.prepareStatement(
             "SELECT display_name FROM customers WHERE id = ?")) {

    statement.setLong(1, 42L);
    statement.setQueryTimeout(3); // seconds

    try (var rows = statement.executeQuery()) {
        while (rows.next()) {
            System.out.println(rows.getString(1));
        }
    }
}
~~~

Đoạn này là snippet bên trong method có biến `dataSource` và ngữ cảnh xử lý `SQLException`; nó không phải toàn bộ lớp cần copy riêng.

`Statement.setQueryTimeout` quy định số **giây** mà driver sẽ đợi cho statement thực thi; khi timeout, driver sẽ ít nhất cố gắng cancel statement và có thể báo `SQLTimeoutException`. Việc cancel trên server, khả năng tiếp tục sử dụng connection và phạm vi thời gian thực tế phụ thuộc driver/DB.

**Đừng giả định việc hủy SQL chắc chắn hoàn tất ngay lập tức**, hoặc dữ liệu đã ghi chưa được commit chỉ vì caller đã nhận exception. Với transaction viết, phải xem trạng thái transaction rõ ràng.

### 6.3. Connection.setNetworkTimeout(Executor, milliseconds)

~~~java
import java.sql.Connection;
import java.util.concurrent.Executor;

static void configureNetworkTimeout(
        Connection connection,
        Executor timeoutExecutor) throws java.sql.SQLException {

    connection.setNetworkTimeout(timeoutExecutor, 5_000); // ms
}
~~~

`setNetworkTimeout` giới hạn thời gian chờ phản hồi database cho một request JDBC, theo hợp đồng driver. Nó là cơ chế mạnh hơn query timeout: khi bị vượt, driver có thể đánh dấu connection **đã đóng và không thể dùng lại**, vì tình trạng network có thể không cho phép tiếp tục an toàn.

- **Đơn vị milliseconds**, khác `setQueryTimeout`.
- Yêu cầu một `Executor` phù hợp; code ví dụ nhận executor được quản lý ở bên ngoài.
- Driver có thể không hỗ trợ API và ném `SQLFeatureNotSupportedException`.
- Không phải một deadline end-to-end cho toàn request.
- Việc thay đổi timeout trên một pooled connection cần xét cơ chế **reset session state** của pool và driver; không áp đặt tùy tiện nếu framework đã quản lý nó.

Theo Javadoc, network timeout được thiết kế để xử lý các tình huống phản hồi DB bị kẹt quá lâu do network failures. Hãy dùng giá trị cao hơn các timeout nghiệp vụ bình thường khi thích hợp, để query/transaction timeout có cơ hội thực thi trước.

### 6.4. Phân biệt timeout, cancellation và lỗi SQL

Trong JDBC:

- `SQLTimeoutException` thể hiện driver đã phát hiện giới hạn timeout tương ứng và có hành động cancel theo hợp đồng.
- `SQLException` có thể đến từ rất nhiều nguyên nhân (connection closed, schema error, permission, deadlock, protocol...).
- Một pool có thể ném một subtype `SQLException` khi **chờ mượn connection quá lâu**; loại cụ thể không nên giả định giống nhau cho mọi pool.
- `Statement.cancel()` chỉ yêu cầu hủy nếu DBMS và driver hỗ trợ.
- `Thread.interrupt()` hoặc `Future.cancel(true)` không phải hợp đồng bảo đảm mọi JDBC call chặn sẽ hủy ngay.

Khi cần retry, phân loại từ **SQLState, vendor error code, transaction boundary và idempotency**, không chỉ từ tên exception chứa chữ “timeout”.

## 7. Cấu hình pool bằng HikariCP: ví dụ có phạm vi rõ ràng

**HikariCP là thư viện bên thứ ba**, không phải class được Java SE 27 cung cấp. Muốn dùng ví dụ, dự án phải khai báo một phiên bản HikariCP hiện hành, tương thích với JDK/JDBC driver/database, trong dependency manager.

Ví dụ khởi tạo một pool ở tầng composition root (nơi tạo dependencies của ứng dụng):

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import java.util.Objects;

public final class DataSources {
    private DataSources() {}

    public static HikariDataSource createFromEnvironment() {
        String url = Objects.requireNonNull(
                System.getenv("DB_JDBC_URL"), "DB_JDBC_URL");
        String username = Objects.requireNonNull(
                System.getenv("DB_USERNAME"), "DB_USERNAME");
        String password = Objects.requireNonNull(
                System.getenv("DB_PASSWORD"), "DB_PASSWORD");

        var config = new HikariConfig();
        config.setJdbcUrl(url);
        config.setUsername(username);
        config.setPassword(password);

        config.setPoolName("orders-pool");
        config.setMaximumPoolSize(12);
        config.setConnectionTimeout(1_500); // ms: wait for pool borrow
        config.setValidationTimeout(1_000); // ms: validation
        config.setMaxLifetime(1_500_000);   // ms: illustrative

        return new HikariDataSource(config);
    }
}
~~~

**Các con số trên chỉ dùng để minh họa cấu hình, không phải mặc định hay đề xuất áp dụng nguyên trạng trong production.** Phải kiểm tra phiên bản HikariCP và điều kiện DB trước khi quyết định. Chẳng hạn, `validationTimeout` phải phù hợp ràng buộc của HikariCP và không lớn hơn `connectionTimeout` theo hướng dẫn chính thức.

Trong một ứng dụng nhỏ, lifetime có thể quản lý như sau:

~~~java
public class App {
    public static void main(String[] args) throws Exception {
        try (var dataSource = DataSources.createFromEnvironment()) {
            var repository = new CustomerRepository(dataSource);
            System.out.println(repository.findById(42L));
        } // shutdown pool khi ứng dụng kết thúc
    }
}
~~~

**Ownership khác nhau:**

- `HikariDataSource` là pool sống suốt vòng đời ứng dụng hoặc một thành phần đã được quản lý.
- `Connection` là **handle mượn tạm** cho mỗi operation/transaction.
- Repository chỉ **giữ tham chiếu DataSource**, không được `close()` DataSource mỗi lần truy vấn.
- Việc đóng pool trong lúc request còn hoạt động cần được phối hợp với quy trình graceful shutdown.
- Không log mật khẩu; không nhúng thông tin đăng nhập thật trong source code.

### 7.1. Những tham số HikariCP thường gặp

| Thuộc tính | Vai trò | Bẫy thường gặp |
| --- | --- | --- |
| `maximumPoolSize` | Giới hạn tổng connections pool (idle + active) | Không tăng tỷ lệ với số virtual threads |
| `minimumIdle` | Mục tiêu số idle connections | Nếu không cấu hình, cách vận hành phụ thuộc default HikariCP phiên bản dùng |
| `connectionTimeout` | Thời gian tối đa caller đợi mượn connection | **Không giới hạn query duration** |
| `validationTimeout` | Thời gian tối đa cho validation | Không thay thế query timeout |
| `maxLifetime` | Tuổi đời tối đa trước khi connection được nghỉ hưu | Không buộc hủy một connection đang được mượn giữa transaction bình thường |
| `idleTimeout` | Thời gian idle trước khi connection có thể bị nghỉ hưu | Có thể không có tác dụng khi pool chạy dạng kích thước cố định |
| `keepaliveTime` | Kiểm tra định kỳ một số connection **đang idle** | Không sửa được query đang treo hoặc connection đang được mượn |
| `leakDetectionThreshold` | Cảnh báo khi handle bị giữ lâu | **Không phải** giới hạn cưỡng chế giải phóng connection |

Ý nghĩa và ràng buộc cụ thể có thể thay đổi giữa các release. Nguồn cấu hình để kiểm tra là README và tài liệu chính chủ tại `github.com/brettwooldridge/HikariCP`, kết hợp với tài liệu JDBC driver đang triển khai.

### 7.2. Vì sao maxLifetime phải xét timeout phía database?

Connection vật lý có thể bị ngắt bởi server, proxy/load balancer, firewall hoặc thiết lập giới hạn tuổi kết nối. Pool thường nên có chính sách kiểm tra và thay connection **trước hoặc phù hợp** với thời hạn của hạ tầng, tránh tiếp tục cho mượn một connection không còn hợp lệ.

Nhưng:

- Một connection đang **được mượn** không nên bị pool cắt chỉ vì đến tuổi thọ thông thường; HikariCP sẽ xử lý retirement theo hợp đồng pool.
- `maxLifetime` **không** thay thế statement/network timeout.
- `keepaliveTime` không tự đảm bảo mọi database session không bao giờ chết.
- Connection có thể chết **bất kỳ lúc nào**, kể cả ngay sau khi pool validation thành công.

Ứng dụng vẫn phải xử lý `SQLException` hợp lý và xác định ranh giới transaction.

## 8. Virtual threads tương tác với pool như thế nào?

Trong Java 27, virtual thread phù hợp với code JDBC ở phong cách đồng bộ dễ đọc:

~~~java
var customer = repository.findById(customerId);
~~~

Khi phải chờ I/O hỗ trợ unmount, JDK có thể tạm ngưng virtual thread và dùng carrier để chạy việc khác. Nhưng tương tác với JDBC **còn phụ thuộc cách driver thực hiện I/O, native calls và các đoạn mã bên trong driver**. Không bảo đảm mọi driver/phiên bản đều unmount tối ưu trong mọi tình huống.

### 8.1. Một virtual thread có thể chờ connection mà không giữ platform thread

Các pool hiện đại thường có cơ chế chờ kết nối bằng synchronization primitives. Khi một virtual thread đang đợi pool cấp connection, nó không nhất thiết chiếm carrier trong suốt thời gian chờ.

Ví dụ:

~~~text
Task 1-10 ───────▶ mượn được 10 connections ──▶ chạy SQL
Task 11-1000 ────▶ chờ pool (queued/pending)
                       │
                       ├─ có connection được trả → tiếp tục
                       └─ hết thời gian chờ → pool acquisition timeout
~~~

Oracle Java SE 27 nêu rõ **database connection pools themselves serve as a semaphore**. Một pool cho tối đa 10 connections đã giới hạn số tác vụ đồng thời dùng connections; thông thường **không cần thêm semaphore có cùng giới hạn ngay trước pool**.

Lưu ý: chờ **không phải không tốn tài nguyên**. Hàng chờ lớn vẫn chiếm memory của task, request context, các socket HTTP đang mở và có thể gia tăng latency.

### 8.2. Không tạo pool virtual threads cố định chỉ để giới hạn DB

Không nên dùng virtual threads như một tập worker cố định theo mô hình platform-thread pool:

~~~java
// Không đặt mục tiêu "chỉ có 10 virtual threads để bảo vệ 10 DB connections".
// Mục tiêu của virtual thread là một task có lifetime riêng.
~~~

Nếu cần nhiều tác vụ độc lập, dùng `Executors.newVirtualThreadPerTaskExecutor()` hoặc framework đã cấu hình phù hợp; connection pool tự giới hạn số connection được cho mượn.

Ví dụ tạo task độc lập và thu kết quả:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import javax.sql.DataSource;

public final class CustomerBatchLookup {
    public static List<Optional<CustomerRepository.Customer>> lookupAll(
            DataSource dataSource,
            List<Long> customerIds)
            throws InterruptedException, ExecutionException {

        var repository = new CustomerRepository(dataSource);

        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            var futures = new ArrayList<
                    Future<Optional<CustomerRepository.Customer>>>();

            for (long id : customerIds) {
                futures.add(executor.submit(() -> repository.findById(id)));
            }

            var results = new ArrayList<
                    Optional<CustomerRepository.Customer>>();

            for (var future : futures) {
                results.add(future.get()); // Không bỏ qua exception
            }

            return List.copyOf(results);
        }
    }
}
~~~

Ở đây `CustomerRepository` là class ở phần 3 và mọi task dùng chung **DataSource**, không dùng chung **Connection**. `Future.get()` có thể ném `ExecutionException` chứa lỗi JDBC từ task; code chủ động chờ tất cả kết quả trong tình huống thành công.

**Giới hạn của ví dụ:** nếu một task thất bại, phương thức có thể ném trước khi đọc hết các future; `executor.close()` vẫn chờ task còn lại theo hợp đồng, không có chính sách cancel/error aggregation chuyên biệt. Với batch lớn hoặc latency giới hạn, cần giới hạn số task được submit, xử lý fail-fast/cancellation và bảo vệ memory riêng. Virtual threads rẻ hơn platform threads, **không có nghĩa phát sinh vô hạn request hoặc futures là miễn phí**.

### 8.3. Khi nào cần semaphore bổ sung?

Nếu một pool đã giới hạn số connection, đặt `Semaphore(10)` ngay trước pool 10 connections thường chỉ tạo **hai tầng chờ**.

Semaphore riêng có thể có ý nghĩa khi phải bảo vệ **một tài nguyên khác**:

- Một external payment API chỉ chịu được 5 requests cùng lúc.
- Một endpoint thực hiện thao tác DB **rất nặng** và cần budget thấp hơn tổng pool.
- Một tenant cần quota concurrency độc lập với tenant khác.
- Một workload chạy background cần dành capacity cho traffic tương tác.

Nếu dùng semaphore, xác định rõ **tài nguyên nào** đang được giới hạn, timeout khi chờ permit, cancellation và nơi đo thời gian chờ.

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.Semaphore;

public final class LimitedHeavyOperation {
    private final Semaphore permits = new Semaphore(3);

    public <T> T run(Callable<T> work) throws Exception {
        permits.acquire(); // interruptible
        try {
            return work.call();
        } finally {
            permits.release();
        }
    }
}
~~~

Không đặt hai semaphore/pool queue chồng nhau một cách vô tình; khi có nhiều hàng chờ, cần giám sát cả hai để xác định chỗ nghẽn thật.

## 9. Transaction làm tăng thời gian giữ connection

Một connection dùng cho transaction có thể giữ nhiều tài nguyên DB hơn một truy vấn read-only đơn giản: transaction state, locks và một slot trong pool.

Ví dụ sai về lifetime:

~~~java
// Không làm như sau nếu HTTP call không nằm trong DB transaction cần thiết:
// try (Connection c = dataSource.getConnection()) {
//     c.setAutoCommit(false);
//     callExternalPaymentGateway();  // Có thể timeout rất lâu
//     updateDatabase(c);
//     c.commit();
// }
~~~

Connection đang bị giữ trong lúc chờ HTTP API. Nếu có 12 connections và mọi task đều chờ external service trong transaction, pool sẽ cạn dù database gần như không có SQL đang thực thi.

### 9.1. Nguyên tắc scope

- Mượn connection **sát thời điểm cần truy cập DB**.
- Hoàn tất statement/result set trước khi trả connection.
- Với transaction, thực hiện `commit` hoặc `rollback` theo contract trước khi đóng.
- Không giữ connection khi thực hiện remote I/O không cần nằm trong cùng atomic unit.
- Không truyền `Connection` sang nhiều virtual threads rồi để các task thao tác cùng một session.
- Nếu cần nhiều bước nghiệp vụ qua DB và dịch vụ ngoài, thiết kế transaction/outbox/saga/idempotency phù hợp; **JDBC transaction không bao trùm HTTP call**.

### 9.2. Ví dụ transaction có rollback và suppressed exception

Đoạn sau minh họa một thao tác chuyển số tiền bằng đơn vị nhỏ nhất (chẳng hạn cents). Schema giả định có `accounts(id, balance_cents)` và giới hạn kiểu dữ liệu đủ lớn. Transaction bao gồm hai câu `UPDATE`; không có lời gọi remote.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.Objects;
import javax.sql.DataSource;

public final class TransferRepository {
    private final DataSource dataSource;

    public TransferRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public void transfer(long fromId, long toId, long cents)
            throws SQLException {

        if (fromId <= 0 || toId <= 0 || fromId == toId
                || cents <= 0) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                String debitSql = """
                        UPDATE accounts
                        SET balance_cents = balance_cents - ?
                        WHERE id = ? AND balance_cents >= ?
                        """;
                String creditSql = """
                        UPDATE accounts
                        SET balance_cents = balance_cents + ?
                        WHERE id = ?
                        """;

                try (PreparedStatement debit =
                             connection.prepareStatement(debitSql);
                     PreparedStatement credit =
                             connection.prepareStatement(creditSql)) {

                    debit.setQueryTimeout(5);
                    debit.setLong(1, cents);
                    debit.setLong(2, fromId);
                    debit.setLong(3, cents);

                    if (debit.executeUpdate() != 1) {
                        throw new IllegalStateException(
                                "Source missing or insufficient funds");
                    }

                    credit.setQueryTimeout(5);
                    credit.setLong(1, cents);
                    credit.setLong(2, toId);

                    if (credit.executeUpdate() != 1) {
                        throw new IllegalStateException(
                                "Destination account not found");
                    }
                }

                connection.commit();
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
~~~

**Đọc đúng ví dụ:**

- `DataSource.getConnection()` mượn connection, `try-with-resources` trả/đóng khi ra khỏi scope.
- `setAutoCommit(false)` tạo transaction do caller quản lý, không dùng mặc định auto-commit cho hai bước cần atomicity.
- Cả hai `UPDATE` phải thành công rồi mới `commit()`.
- Nếu execute hoặc logic ném lỗi, code cố `rollback()` và giữ lỗi rollback trong danh sách `suppressed`.
- Driver/pool/framework có thể quản lý reset connection state khi trả handle; với code ứng dụng trực tiếp tự quản lý connection, phải xác nhận policy trả connection/rollback/autoCommit của pool đang dùng.
- Transaction này **không thay thế** constraint của DB, validation, deadlock handling, money arithmetic rules hoặc isolation policy. Thao tác thật cần kiểm thử theo DBMS đang triển khai.
- Nếu `commit()` bị timeout hoặc mất kết nối, caller có thể **không biết chắc giao dịch đã commit hay chưa**. Cố rollback sau lỗi commit không chứng minh DB đã hoàn nguyên. Không tự động retry chuyển tiền nếu không có idempotency và cơ chế đối soát.

## 10. Deadline end-to-end và cancellation

Giả sử request HTTP có ngân sách **2 giây**. Một cách chia ngân sách minh họa:

~~~text
Request deadline (2.000 ms)
  ├─ Chờ pool                  200 ms
  ├─ SQL + nhận kết quả        900 ms
  ├─ Ánh xạ / nghiệp vụ       200 ms
  ├─ Phản hồi                 100 ms
  └─ Margin cho biến động      600 ms
~~~

Các con số là **ngân sách mục tiêu ví dụ**, không phải giới hạn tự động được JDBC thi hành. Chúng chỉ có ý nghĩa nếu ứng dụng thực sự triển khai deadline xuyên các bước và cấu hình pool/driver tương thích.

### 10.1. Timeout nào nên xảy ra trước?

Trong nhiều trường hợp:

- **Pool borrow timeout** nên đủ ngắn để request không bị chôn trong hàng đợi khi hệ thống quá tải.
- **Query timeout** nên phản ánh giá trị tối đa chấp nhận cho SQL, có tính đến độ chính xác/timeouts mà driver hỗ trợ.
- **Network timeout** thường là cơ chế bảo vệ cuối cùng khi giao tiếp DB có vấn đề nghiêm trọng.
- **Request deadline** phải tính luôn borrow, SQL, commit/rollback và các công việc khác.

Không có thứ tự thời gian “đúng cho mọi hệ thống”. Tuy nhiên, sẽ nguy hiểm khi request deadline ngắn mà JDBC call có thể bị treo lâu hơn nhiều mà không có cancellation hiệu quả.

### 10.2. Timeout không đồng nghĩa rollback đã thành công

Một timeout có thể xảy ra:

- Trước khi mượn được connection: chưa bắt đầu query.
- Trong lúc statement đang chạy: DB có thể đã xử lý **một phần** hoặc toàn bộ trước khi cancel.
- Sau khi DB đã commit nhưng trước khi client nhận xác nhận: outcome có thể **không xác định**.
- Trong lúc connection bị network failure: connection có thể không còn an toàn để sử dụng.

Vì vậy, API write cần xác định retry idempotent (request ID/unique constraint), transactional boundaries và chính sách đối soát. Đừng đánh đồng mọi `SQLTimeoutException` với `"chưa thực hiện"`.

### 10.3. Virtual-thread interruption

Virtual thread tuân theo `Thread.interrupt()` và cơ chế cancellation của tác vụ, nhưng JDBC driver quyết định việc chặn trong driver có phản hồi interrupt đến đâu. Ví dụ `Future.cancel(true)` **yêu cầu** ngắt, không bảo đảm server hủy SQL và release database connection ngay tức thì.

Khi xử lý `InterruptedException` ở tầng ứng dụng:

~~~java
try {
    doInterruptibleWork();
} catch (InterruptedException failure) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Đây là một snippet về interruption policy; `doInterruptibleWork()` là method minh họa có thể bị interrupt. Không dùng việc bắt và bỏ qua interruption như cách “ổn định” timeout, vì nó có thể giữ task/connection sống lâu hơn yêu cầu.

## 11. Sizing connection pool: dựa trên database capacity, không dựa trên số thread

Pool size là một **quyết định về tài nguyên DB**. Không có công thức chung đúng cho mọi workload. Các biến cần đo:

- Số CPU, khả năng xử lý đồng thời, I/O và giới hạn connections của DB.
- Tần suất yêu cầu cần DB; tỷ lệ truy vấn read/write.
- Thời gian connection **được mượn** (bao gồm transaction, result mapping và thời gian không thực sự chạy SQL).
- Số application replicas, background workers và công cụ quản trị cùng dùng DB.
- Mức độ lock contention, transaction isolation, deadlock, query plan và index.
- SLA latency và khả năng xếp hàng ở pool khi traffic tăng đột biến.

### 11.1. Tổng connection budget của nhiều replicas

Giả sử DB cho phép tối đa 100 phiên kết nối, hệ thống dành 20 cho maintenance/administration/background jobs và một số client khác. Bốn replicas ứng dụng cần chia phần còn lại:

~~~text
DB maximum connections: 100
  ├─ Reserve ngoài các app replicas: 20
  └─ Budget cho app replicas:       80

Nếu có 4 replicas:
  4 × maxPoolSize(12) = 48 connections tối đa từ nhóm pool này.
~~~

Con số **48** không vượt 80, nhưng không có nghĩa 12 là lựa chọn tối ưu. Có thể DB chỉ đạt throughput tốt nhất ở ít active queries hơn; cũng có thể traffic không đủ để dùng hết 12 connections. Nếu dự án có nhiều pools, batch jobs hoặc scale thêm replicas, phải tính **tổng tất cả**:

~~~text
Σ(maxPoolSize của từng pool/replica) + các clients khác
    ≤ Connection budget thực tế của DB
~~~

Với workload đa tenant hoặc pool kết nối đến nhiều database/cluster, tính riêng theo **mỗi backend**. Không lấy số kết nối tối đa đã khai báo trong DB rồi phân hết cho request chính mà không chừa headroom.

### 11.2. Ước tính concurrency từ thời gian giữ connection

Một heuristic dùng **Little's law** ở trạng thái ổn định:

\`L ≈ λ × W\`

Trong đó:

- `L`: số connections đang được mượn trung bình.
- `λ`: số tác vụ **thực sự mượn DB connection** trong một giây.
- `W`: thời gian mỗi tác vụ giữ connection trung bình, tính bằng giây.

Ví dụ:

~~~text
200 DB operations / second
× 0.04 second giữ connection / operation
≈ 8 connections active trung bình
~~~

Số 8 **không** phải khuyến nghị đặt pool bằng 8: lưu lượng thường có bursts, thời gian giữ connection có phân bố dài, query contention và error spikes. Phải quan sát **p95/p99 borrow wait**, active usage, queue depth và DB metrics trước khi chọn headroom.

**Đo W là thời gian từ mượn được đến lúc trả connection**, không phải toàn bộ thời gian HTTP request nếu request còn thực hiện các tác vụ khác.

### 11.3. Vì sao tăng pool size có thể làm chậm hơn?

Nếu DB bị giới hạn CPU/IOPS hoặc nhiều transaction tranh chấp cùng rows:

- Thêm connection làm tăng số SQL đang cạnh tranh tài nguyên.
- Query có thể chờ DB locks lâu hơn.
- Transaction dài giữ connection và lock lâu hơn.
- Latency mỗi thao tác tăng, khiến số active connections tiếp tục cao.
- Pool queue có thể lại tăng dù đã mở rộng.

Đây là một vòng phản hồi xấu: **nhiều connection hơn → DB chậm hơn → giữ connection lâu hơn → lại thiếu connection**. Cách sửa có thể là tối ưu SQL/index, giảm transaction duration, batching phù hợp, giới hạn concurrency hoặc phân phối read workloads thay vì tăng số connection vô hạn.

## 12. Metrics và tracing cần có khi chạy production

Một dashboard hữu ích phải phân biệt **pool wait** với **query duration**, **connection hold time** và **database-side wait**.

| Metric | Ý nghĩa | Câu hỏi cần trả lời |
| --- | --- | --- |
| Active connections | Số handle đang được mượn | Pool có thường xuyên chạm maximum không? |
| Idle connections | Connections đang sẵn sàng | Có thể phục vụ yêu cầu mới ngay không? |
| Pending/waiting acquisition | Số tác vụ đợi connection | Có hàng chờ kéo dài không? |
| Total connections | Tổng active + idle theo pool | Pool có đang tạo/loại connection bất thường không? |
| Connection acquire duration | Thời gian `getConnection()` | Nghẽn xảy ra **trước khi chạy SQL**? |
| Connection usage/hold duration | Thời gian từ mượn đến trả | Transaction/callback có giữ connection quá lâu? |
| Query execution duration | Thời gian SQL, DB/network | Query chậm hay acquire chậm? |
| Acquisition timeout count | Số lần pool không cấp kịp | Có overload, leak hay pool cấu hình sai? |
| Connection creation/validation failures | Không tạo hoặc kiểm tra được connection | DB restart, network, credentials, limits? |
| Leak detection warnings | Handle giữ lâu hơn ngưỡng cảnh báo | Rò rỉ thật hay query/transaction hợp lệ nhưng chậm? |
| DB active sessions/locks | Tải và lock từ phía database | DB có còn capacity không? |
| Request p50/p95/p99, error rate | Trải nghiệm đầu cuối | Thay đổi pool có cải thiện SLA không? |

### 12.1. Đo thời gian mượn bằng monotonic clock

~~~java
import java.sql.Connection;
import java.sql.SQLException;
import java.util.concurrent.TimeUnit;
import javax.sql.DataSource;

static void runOperation(DataSource source) throws SQLException {
    long startNanos = System.nanoTime();

    try (Connection connection = source.getConnection()) {
        long borrowNanos = System.nanoTime() - startNanos;
        System.out.println("borrowMs="
                + TimeUnit.NANOSECONDS.toMillis(borrowNanos));

        // Thực thi công việc database trong scope connection này.
    }
}
~~~

`System.nanoTime()` phù hợp để đo **elapsed time** vì không dựa vào đồng hồ lịch (wall clock). Trong sản phẩm thật, ghi metric với nhãn pool/service/operation hữu ích, nhưng tránh nhãn có độ biến thiên cực lớn như ID từng request hoặc SQL chứa dữ liệu đầu vào.

### 12.2. HikariCP Pool MXBean (nếu dùng HikariCP)

Một số số liệu tức thời có thể lấy bằng `HikariPoolMXBean`:

~~~java
import com.zaxxer.hikari.HikariDataSource;
import com.zaxxer.hikari.HikariPoolMXBean;

static void printPoolState(HikariDataSource pool) {
    HikariPoolMXBean stats = pool.getHikariPoolMXBean();
    if (stats == null) {
        return; // Pool chưa khởi tạo hoặc không sẵn sàng
    }

    System.out.println("active=" + stats.getActiveConnections());
    System.out.println("idle=" + stats.getIdleConnections());
    System.out.println("waiting=" + stats.getThreadsAwaitingConnection());
    System.out.println("total=" + stats.getTotalConnections());
}
~~~

Đây là metric **theo thời điểm**, có thể thay đổi ngay sau khi đọc. Nó không phải snapshot transactionally consistent, cũng không thay thế histogram acquisition/usage duration. Nhiều triển khai ứng dụng sẽ xuất metrics qua Micrometer/Prometheus/JMX hoặc công cụ monitoring đang dùng thay vì in stdout.

**Không** thu metrics bằng cách log toàn bộ JDBC connection URL nếu URL có chứa credential/token.

### 12.3. Virtual thread metrics và JFR

Khi chạy virtual threads, bổ sung:

- Số tasks đang chạy/đang chờ, request queue và cancellation.
- CPU utilization và GC pauses.
- `jdk.VirtualThreadPinned` từ JFR khi cần điều tra carrier pinning.
- Thread dump và `jcmd Thread.vthread_scheduler` để quan sát scheduler khi nghi ngờ scheduling.
- JDBC driver/DB metrics và pool acquisition metrics để nhận diện nguồn chặn thật.

**Một virtual thread ở `WAITING` khi gọi `getConnection()` không đủ để kết luận scheduler hoặc JVM có lỗi.** Nó có thể đang chờ theo hợp đồng pool.

## 13. Java 27, JDBC driver và pinning

Ở JDK 21–23, một số blocking operation khi virtual thread đang giữ intrinsic monitor có thể gây pinning. **Từ JDK 24, JEP 491 đã thay đổi cơ chế synchronized monitors**, giúp virtual threads chặn/unmount phù hợp mà không bị pin **chỉ vì đang giữ `synchronized`**.

Vì vậy trên **Java 27**:

- Không tự động coi driver dùng `synchronized` là không tương thích virtual threads.
- Không thay toàn bộ synchronized code bằng `ReentrantLock` chỉ vì đọc hướng dẫn cho JDK 21–23.
- Vẫn kiểm tra **lock contention**: một monitor chỉ cho một thread giữ, nên critical section dài vẫn có thể làm các tác vụ khác chờ.
- Native/JNI/foreign function frames và một số VM situations vẫn có thể gây pinning.
- Một JDBC driver có native/network behavior đặc thù có thể tác động tới carrier; kiểm thử trên đúng driver/JDK/DB/version.
- Tranh chấp DB connection pool và pinning **là hai vấn đề khác nhau**, không được gộp làm một.

### 13.1. Triệu chứng và cách nhận biết

| Hiện tượng | Bằng chứng | Hướng xử lý |
| --- | --- | --- |
| Pool active = max; waiting tăng; JFR ít pinned event | Pool metrics, query/hold time | Rút ngắn connection hold, tối ưu DB, điều chỉnh capacity có đo |
| Nhiều pinned events dài, stack tới native/VM | JFR `jdk.VirtualThreadPinned`, reason/stack | Điều tra native callback/driver hoặc operation cản unmount |
| Nhiều monitor enter waits | JFR `jdk.JavaMonitorEnter`, thread dump | Giảm contention, giữ invariant đúng |
| DB CPU cao, query latency tăng | DB metrics, SQL profiles, locks | Tối ưu truy vấn hoặc giảm DB concurrency |
| Acquire timeout nhưng active thấp | Pool creation/validation errors, connectivity | Xem kết nối vật lý, DB restart, credential, networking |
| Request timeout trước khi có query | Borrow wait và request deadline | Xem hàng đợi tại pool, admission control |
| Query timeout sau khi mượn thành công | Driver SQL timeout, DB execution | Xem query plan/index, cancellation và transaction outcome |

Không suy luận “ít pinned events nghĩa là không có blocking”: đa số virtual-thread-friendly blocking có thể unmount bình thường.

### 13.2. Cách đọc thread dump đúng

Dùng các công cụ JDK với quyền phù hợp trên **đúng JVM process**:

~~~text
jcmd <pid> VM.version
jcmd <pid> Thread.dump_to_file -format=json threads.json
jcmd <pid> Thread.vthread_scheduler
~~~

Với một recording JFR:

~~~text
jcmd <pid> JFR.start name=DbWait settings=profile duration=60s filename=db-wait.jfr
jfr print --events jdk.VirtualThreadPinned,jdk.SocketRead,jdk.JavaMonitorEnter db-wait.jfr
~~~

Đây là **runbook mẫu**, cần điều chỉnh thời điểm thu thập, thư mục output và quyền truy cập. Với pinning nghiêm trọng, xem stack và reason; với pool exhaustion, ưu tiên **pool pending/acquire time và DB-side diagnostics**.

## 14. Quy trình điều tra khi pool báo “connection timeout”

Giả sử service trả lỗi mượn connection sau 1,5 giây. Cách điều tra có hệ thống:

### Bước 1 — Tách acquire timeout và query timeout

Nhìn vào stack trace:

- Exception xảy ra trong `dataSource.getConnection()` → nghi pool acquisition/connection creation.
- Exception xảy ra trong `statement.executeQuery()`/`executeUpdate()` → nghi query/network/DB.
- Exception xảy ra trong `commit()` → kiểm tra **transaction outcome không xác định**.

Không gộp cả ba vào một dashboard ghi `db_timeout` không phân loại.

### Bước 2 — Kiểm tra pool state ngay khi lỗi

Thu:

- `active`, `idle`, `total`, `waiting`.
- Maximum pool size, acquisition timeout và validation timeout.
- Connection usage duration, acquisition duration.
- Số lần pool tạo connection mới, lỗi tạo/validation.

Nếu `active == maximumPoolSize` và `waiting` cao, có thể pool bị sử dụng hết. Nhưng nếu active thấp và không tăng total, cần xem DB/network/validation failures hoặc pool configuration, thay vì chỉ tăng maximum size.

### Bước 3 — Tìm nơi giữ connection lâu

Một số nguyên nhân:

- Transaction có query chậm hoặc chờ DB lock.
- ORM transaction mở trước khi gọi HTTP API.
- Không đóng `ResultSet`/`Statement`/`Connection`.
- Xử lý mapping dữ liệu lớn trong khi giữ connection.
- Task có vòng chờ nhưng không cấu hình timeout.
- Database failover làm validation/connection creation chậm.

Xem stack traces, pool leak warnings, tracing spans và DB active sessions theo **cùng mốc thời gian**.

### Bước 4 — Kiểm tra tổng tải phía DB

Trên database:

- Connection count và các session idle-in-transaction.
- Query latency, execution plans, slow query logs.
- Lock wait/deadlock và transaction duration.
- CPU, IOPS, storage queue, network errors.
- Connection limit và các client cùng sử dụng DB.

Một connection pool chỉ có 12 slots vẫn có thể gây quá tải DB nếu truy vấn rất nặng; một pool có 100 slots vẫn có thể rỗng nhanh khi 100 connections bị giữ trong transaction dài.

### Bước 5 — Chọn đúng hướng sửa

- Leak thật → bắt buộc `close()` mọi handle và sửa ownership.
- Hold time dài → rút ngắn transaction, tránh I/O ngoài DB trong scope.
- Query chậm → tối ưu SQL/index và transaction.
- Pool thấp nhưng DB còn headroom → thử tăng size có kiểm soát, benchmark.
- DB đã quá tải → giảm concurrency, admission control, cache/read replica nếu phù hợp.
- Lỗi kết nối/validation → xử lý network, credential, failover và driver settings.
- Request backlog lớn → quy định deadline, hàng đợi và load shedding có thể quan sát.
- Native pinning có bằng chứng → điều tra driver/native path, không gắn nhãn mọi acquire wait là pinning.

### Bước 6 — So sánh trước/sau

Không kết luận thành công chỉ vì hết acquisition timeout. Kiểm tra thêm:

- Throughput và request p95/p99.
- DB CPU, lock waits, slow SQL.
- Pool pending/active/idle và thời gian giữ.
- Error rate, retry count, timeout count.
- Driver/JFR scheduler/pinning nếu vấn đề có liên quan.

**Mục tiêu là tính ổn định end-to-end**, không phải tối đa hóa số active connections.

## 15. Kiểm thử kết hợp pool + virtual threads

Bài test nên xác nhận hợp đồng concurrency, timeout và resource ownership.

### 15.1. Những tình huống cần kiểm tra

1. **Borrow/return:** dùng connection rồi đóng thì số active giảm trở lại theo pool metrics.
2. **Pool limit:** nhiều task cùng mượn không vượt quá số physical connections mà pool cấu hình.
3. **Acquisition timeout:** khi tất cả connections được giữ, borrower mới đợi và nhận lỗi đúng theo pool policy.
4. **Query timeout:** câu SQL chậm được driver/DB xử lý theo cấu hình; kết quả ngoại lệ/connection state được kiểm tra.
5. **Interrupted task:** hủy tác vụ đang chờ; xác nhận driver/pool phản hồi cancellation theo contract đang triển khai.
6. **Exception path:** SQL lỗi, mapping lỗi hoặc runtime exception không làm rò rỉ connection.
7. **Transaction rollback:** một update thất bại không để dữ liệu bị cập nhật một nửa.
8. **Commit ambiguity:** nếu connection mất khi commit, ứng dụng không retry không kiểm soát.
9. **Pool shutdown:** service dừng theo trình tự, ngừng nhận task mới và chờ task quan trọng kết thúc.
10. **Multi-replica load:** tổng DB connections của nhiều instance không vượt budget.

### 15.2. Kịch bản test pool capacity tối giản

Giả sử một pool test giới hạn **2 connections**:

~~~text
Task A mượn connection 1 và giữ trong một barrier
Task B mượn connection 2 và giữ trong cùng barrier
Task C gọi getConnection() khi pool đã đầy
    → Task C chờ theo acquire timeout

Khi A trả connection:
    → C có thể mượn và tiếp tục

Khi A và B không trả trong thời gian cho phép:
    → C nhận lỗi acquisition timeout của pool
~~~

Test có thể dùng `CountDownLatch` để làm cho trạng thái “hai connections đang được mượn” lặp lại được, thay vì trông chờ vào `Thread.sleep` hoặc timing ngẫu nhiên. Khi test có database thật, dùng một schema/instance riêng để không làm gián đoạn traffic production.

**Không** tạo một test đòi acquisition timeout trên đúng 1.500 ms đến từng mili giây: scheduler, I/O và chính sách timeout implementation có sai số. Hãy xác minh khoảng thời gian hợp lý và loại lỗi/nguyên nhân.

### 15.3. Đừng chỉ test truy vấn đơn lẻ

Một truy vấn chạy nhanh không chứng minh pool chịu được 500 concurrent requests. Phải kiểm tra:

- Tỷ lệ requests truy cập DB.
- Thời gian mượn connection khi thành công và khi thất bại.
- Độ dài transactions dưới tải.
- Số result rows, mapping/serialization time.
- Retry storms sau network failures.
- Mức tải của các tác vụ batch/background cùng pool.
- Tác động của maxPoolSize và số replicas lên DB.

## 16. Các anti-pattern cần tránh

| Anti-pattern | Tại sao sai | Cách thay |
| --- | --- | --- |
| “Có 10.000 virtual threads thì cần 10.000 DB connections” | Virtual threads và connections là hai tài nguyên khác nhau | Pool theo DB capacity và measured usage |
| Đặt pool size bằng CPU core count mà không đo | Core count không phản ánh query/lock/I/O/replicas | Load test và metrics |
| Tạo `DataSource`/connection pool mới cho từng request | Tăng số sessions, tạo/đóng pool tốn tài nguyên | Một pool được quản lý theo lifetime ứng dụng |
| Dùng `DriverManager.getConnection()` cho mọi request rồi tưởng có pool | DriverManager không phải pooling abstraction | Dùng pooled DataSource khi cần |
| Giữ `Connection` làm singleton mutable | Transaction/statement interference, leak | Share DataSource, borrow per scope |
| Không gọi `Connection.close()` vì nghĩ pool tự thu hồi | Pool có thể cạn dần | Try-with-resources |
| Gọi `dataSource.close()` sau mỗi truy vấn | Đóng cả pool, ảnh hưởng requests khác | Chỉ đóng khi shutdown owner |
| Giữ connection trong lúc gọi API ngoài | Hold time tăng, pool exhaustion | Thu nhỏ transaction đúng nghĩa |
| Dùng `connectionTimeout` của pool như query timeout | Query vẫn có thể chạy rất lâu | Statement/driver timeout riêng |
| Dùng `setQueryTimeout` như timeout mượn pool | Không ảnh hưởng `getConnection()` | Cấu hình pool acquisition |
| Dùng network timeout quá ngắn | Kết nối có thể bị đóng khi operation hợp lệ còn chạy | Chọn ngưỡng từ driver/DB SLA và phối hợp deadline |
| Catch mọi `SQLException` rồi trả empty | Che lỗi hệ thống thành không có dữ liệu | Phân loại lỗi; propagate cause |
| Retry một write sau timeout mà không có idempotency | Có thể lặp giao dịch đã commit | Key định danh/DB constraint/đối soát |
| Thêm semaphore y hệt pool size | Hai hàng chờ, khó giám sát | Dựa vào pool; semaphore riêng chỉ khi hạn chế tài nguyên khác |
| Tăng pool size khi DB CPU/lock đã quá tải | Làm DB chậm thêm | Tối ưu DB hoặc giảm concurrency |
| Chạy JDBC operation ở nhiều threads trên một Connection | Không có hợp đồng thread-safety chung; transaction bị chia sẻ | Mỗi unit of work sở hữu connection riêng |
| Nghĩ virtual thread WAITING nghĩa là carrier pin | Nhiều operation chờ hỗ trợ unmount | JFR + pool metrics + thread dump |
| Dùng `-Djdk.tracePinnedThreads` như giải pháp Java 27 | Là lời khuyên cũ cho JDK 21–23 | JFR `jdk.VirtualThreadPinned` trên JDK 24+ |
| Dựa vào leak warning để auto-release | Leak detection thường chỉ cảnh báo | Sửa ownership/scope và thời gian giữ |
| Đóng ResultSet/Connection sau khi trả lazy stream | Stream sẽ gặp resource đã đóng | Materialize trong scope hoặc thiết kế lifecycle rõ |

## 17. Checklist thiết kế production

- [ ] Đã xác định `DataSource` hiện tại thật sự dùng pool nào, phiên bản nào và có metric nào.
- [ ] `DataSource` sống theo ứng dụng, không khởi tạo/đóng mỗi request.
- [ ] Mỗi tác vụ/transaction dùng logical connection theo scope riêng.
- [ ] Mọi `Connection`/`Statement`/`ResultSet` được đóng qua try-with-resources.
- [ ] Không trả ResultSet/lazy stream sau khi resource đã đóng.
- [ ] `PreparedStatement` dùng parameters thay vì nối input thành SQL.
- [ ] Không biến lỗi DB/timeout thành `Optional.empty()`.
- [ ] Đã phân biệt pool borrow, login/connect, validation, statement, network và request deadlines.
- [ ] Không coi timeout là bằng chứng write chưa thực hiện hoặc transaction đã rollback.
- [ ] Các write operations có idempotency/correlation và policy retry có kiểm soát.
- [ ] Transaction không giữ connection khi chờ remote service nếu không bắt buộc.
- [ ] Pool sizing tính cả replicas, batch workers, reserved DB connections và DB capacity.
- [ ] Không coi số virtual threads là target số DB connections.
- [ ] Không thêm semaphore trùng chức năng pool trừ khi có budget khác được ghi rõ.
- [ ] Có metrics active/idle/pending, borrow duration, hold duration, query latency và timeout count.
- [ ] Có DB metrics về CPU, lock waits, active sessions và slow SQL.
- [ ] Có thời gian chờ/cancellation rõ khi DB hoặc pool quá tải.
- [ ] Đã kiểm thử đúng JDBC driver/JDK 27, đặc biệt với interruption và network behavior.
- [ ] Nếu nghi pinning, đã xem JFR/stack và xét JEP 491 thay vì mặc định lỗi synchronized.
- [ ] Đã kiểm thử pool exhaustion, transaction rollback, commit ambiguity và graceful shutdown.
- [ ] Không log credential, SQL bind values nhạy cảm hoặc connection URL chứa secret.
- [ ] Có kế hoạch load test trước/sau mỗi lần chỉnh maximumPoolSize hoặc timeouts.

## 18. Nguồn chính thức và tài liệu liên quan

- [Java SE 27 API — DataSource](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/javax/sql/DataSource.html) — factory kết nối, login timeout, các kiểu DataSource.
- [Java SE 27 API — Connection](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/Connection.html) — transaction, auto-commit, close, network timeout, rollback, commit.
- [Java SE 27 API — PreparedStatement](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/PreparedStatement.html) — SQL có tham số và execution.
- [Java SE 27 API — Statement](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/Statement.html) — `setQueryTimeout`, `cancel`, `SQLTimeoutException`.
- [Java SE 27 API — SQLException](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/SQLException.html) — SQLState, vendor error code, cause, chained exceptions.
- [Java SE 27 API — SQLTimeoutException](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/SQLTimeoutException.html) — timeout được JDBC driver phát hiện.
- [Java SE 27 — Virtual Threads](https://docs.oracle.com/en/java/javase/27/core/virtual-threads.html) — virtual threads, semaphore, database connection pools và cảnh báo không pool virtual threads.
- [Java SE 27 API — Executors](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Executors.html) — `newVirtualThreadPerTaskExecutor()`.
- [Java SE 27 API — Semaphore](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Semaphore.html) — budget tác vụ theo tài nguyên.
- [Java SE 27 — jcmd Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jcmd.html) — virtual thread scheduler dumps và JFR.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444) — virtual threads chính thức từ Java 21.
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491) — hành vi monitor từ JDK 24, tránh khuyến cáo pinning lỗi thời.
- [HikariCP — README và configuration](https://github.com/brettwooldridge/HikariCP) — `maximumPoolSize`, `connectionTimeout`, `validationTimeout`, lifecycle settings và pooling diagnostics (thư viện ngoài JDK).

**Kết luận:** Java 27 cho phép xử lý rất nhiều tác vụ I/O bằng virtual threads, nhưng database connections vẫn là một **tài nguyên hữu hạn**. Connection pool có nhiệm vụ tái sử dụng và giới hạn connections; nó không phải một virtual-thread pool. Thiết kế đúng cần **mượn muộn, trả sớm**, phân biệt mọi lớp timeout, tránh giữ connection trong transaction dài, giữ nguyên thông tin lỗi và đo đồng thời **pool queue, connection hold time, SQL latency và DB capacity**. Khi service chậm, phân biệt pool exhaustion với pinning thực sự trước khi đổi cấu hình hoặc code.
