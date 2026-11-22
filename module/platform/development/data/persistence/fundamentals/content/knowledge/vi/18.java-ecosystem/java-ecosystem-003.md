# Trách nhiệm của driver, DataSource và connection pool

Khi một ứng dụng Java truy cập PostgreSQL, thường có ba thành phần xuất hiện cạnh nhau: **JDBC driver**, **DataSource** và **connection pool**. Chúng có liên quan nhưng không phải ba tên gọi của cùng một thứ. Nếu hiểu nhầm, ứng dụng có thể mở hàng trăm kết nối mạng không cần thiết, đóng nhầm connection đang thuộc transaction, cấu hình timeout sai tầng hoặc để trạng thái của request trước ảnh hưởng request sau.

Bài học thuộc chương **Hệ sinh thái Java** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Phạm vi module bao gồm lựa chọn mô hình dữ liệu, lược đồ, truy vấn, chỉ mục, giao dịch, kiểm soát đồng thời, xử lý lỗi kết nối, bảo mật, sao lưu và tối ưu hiệu năng. Nội dung này giải thích cách ba thành phần nói trên phối hợp để hiện thực **ranh giới persistence** trong Java, minh họa qua **JDBC, PostgreSQL, HikariCP và Spring**. Những giá trị cấu hình chỉ là ví dụ, không phải khuyến nghị mặc định áp dụng cho mọi môi trường hoặc mọi phiên bản.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích rõ nhiệm vụ của **JDBC driver**, giao diện **javax.sql.DataSource** và **connection pool**.
- Vẽ được đường đi từ lời gọi repository tới connection vật lý, giao thức của database và kết quả trả về.
- Phân biệt **connection vật lý**, **logical connection** được mượn từ pool và **transaction**.
- Sử dụng **try-with-resources** đúng cách với JDBC và hiểu ý nghĩa của **Connection.close()** khi có pool.
- Đặt ranh giới commit/rollback tại tầng ứng dụng, tránh tự mở connection ngoài transaction của Spring.
- Nhận diện vị trí của timeout kết nối, thời gian mượn connection, timeout câu SQL, bảo mật TLS và xử lý connection hỏng.
- Chọn kích thước pool dựa trên tải và giới hạn database, sử dụng metrics để tìm nguyên nhân khi pool cạn.

## 2. Bức tranh tổng thể: ba tầng, ba trách nhiệm

~~~text
Application service / Repository
              |
              | DataSource.getConnection()
              v
     +-----------------------+
     | DataSource           |  Hợp đồng cấp Connection
     | (có thể dùng pool)   |
     +-----------------------+
              |
              | Pool cấp logical connection nếu có pooling
              v
     +-----------------------+
     | JDBC Connection      |  API JDBC: prepare, execute,
     | PreparedStatement    |  transaction, ResultSet
     +-----------------------+
              |
              v
     +-----------------------+
     | JDBC driver          |  Giao tiếp giao thức DBMS,
     | (ví dụ pgJDBC)       |  chuyển kiểu, nhận kết quả/lỗi
     +-----------------------+
              |
              | TCP/TLS + giao thức PostgreSQL
              v
     +-----------------------+
     | Database server      |  SQL, khóa, MVCC, WAL,
     | PostgreSQL           |  transaction và dữ liệu
     +-----------------------+
~~~

Sơ đồ mô tả **vai trò logic**, không phải mỗi hộp buộc là một tiến trình hay thư viện khác nhau. Pool có thể tự cài đặt giao diện DataSource và sử dụng driver ở phía dưới. Khi không có pool, DataSource vẫn có thể cấp một kết nối vật lý mới cho mỗi lần gọi.

| Thành phần | Câu hỏi chính | Nhiệm vụ |
| --- | --- | --- |
| **JDBC driver** | Làm sao Java nói chuyện với DBMS? | Hiện thực giao thức kết nối, thực thi lệnh qua JDBC, chuyển dữ liệu và lỗi |
| **DataSource** | Ứng dụng lấy Connection từ đâu? | Cung cấp giao diện tạo/cấp Connection và cấu hình nguồn kết nối |
| **Connection pool** | Làm sao tái sử dụng Connection hiệu quả? | Quản lý tập kết nối vật lý, cho mượn/trả, kiểm tra và giới hạn tài nguyên |
| **Transaction manager** | Các thay đổi nào commit/rollback cùng nhau? | Điều phối transaction trên tài nguyên tham gia; đây là vai trò riêng |
| **Database server** | SQL và ACID được thực thi ở đâu? | Quản lý dữ liệu, khóa, cô lập, WAL, commit và phục hồi |

Điểm mấu chốt: **DataSource là một giao diện; pooling là một khả năng của một số triển khai DataSource; driver là lớp giao tiếp với DBMS**.

## 3. JDBC driver chịu trách nhiệm những gì?

**JDBC (Java Database Connectivity)** xác định API chuẩn trong các gói **java.sql** và **javax.sql**. Một **JDBC driver** cho DBMS cụ thể hiện thực cầu nối giữa API đó với giao thức và ngữ nghĩa của hệ lưu trữ.

Với PostgreSQL, thư viện **pgJDBC** cho phép code Java dùng các đối tượng như **Connection**, **PreparedStatement**, **ResultSet**, **DatabaseMetaData**. Driver thực hiện những công việc điển hình:

1. **Thiết lập kết nối:** giao tiếp tới máy chủ, thực hiện handshake và xác thực theo cấu hình; TLS có được sử dụng hay không phụ thuộc driver, URL/properties và server.
2. **Gửi câu lệnh và tham số:** chuyển lời gọi **prepareStatement(...)**, **setLong(...)**, **executeQuery()** thành tương tác phù hợp với PostgreSQL.
3. **Ánh xạ kiểu dữ liệu:** chuyển các kiểu SQL thành kiểu Java và ngược lại, ví dụ **BIGINT → long**, **NUMERIC → BigDecimal**, **TIMESTAMP** và các kiểu thời gian tương ứng.
4. **Trả kết quả:** cung cấp ResultSet và metadata để code ứng dụng đọc hàng/cột.
5. **Phơi bày lỗi:** chuyển phản hồi lỗi và lỗi truyền thông thành các dạng **SQLException**, có thể kèm **SQLSTATE**, error code và chuỗi exception.
6. **Hỗ trợ điều khiển kết nối:** truyền các thao tác **setAutoCommit**, **commit**, **rollback**, isolation, cancel và các thuộc tính JDBC theo khả năng của driver/DBMS.

Ví dụ về JDBC với driver đã có trên classpath:

~~~java
String sql = """
    SELECT id, total_amount
    FROM orders
    WHERE tenant_id = ? AND id = ?
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, tenantId);
    statement.setLong(2, orderId);

    try (ResultSet rs = statement.executeQuery()) {
        if (rs.next()) {
            long id = rs.getLong("id");
            java.math.BigDecimal amount =
                    rs.getBigDecimal("total_amount");
            // Sử dụng id và amount theo nghiệp vụ.
        }
    }
}
~~~

Code trên giả định **dataSource**, **tenantId**, **orderId** đã được cung cấp từ tầng ứng dụng và người gọi có quyền truy cập tenant tương ứng. Driver gửi SQL; **database server** mới là thành phần thực thi điều kiện WHERE, sử dụng chỉ mục, xử lý khóa và tính cô lập.

### Driver không tự làm thay các nhiệm vụ khác

- Driver **không tự quyết định** một use case gồm ba câu SQL phải nằm trong cùng giao dịch. Ứng dụng hoặc transaction manager phải chọn ranh giới.
- Driver **không tự bảo đảm** kết nối được tái sử dụng giữa các request. Đó là nhiệm vụ của pool nếu có.
- Driver **không tự sửa** một truy vấn thiếu chỉ mục, một biểu thức SQL có race condition hoặc mô hình dữ liệu thiếu unique constraint.
- Driver **không tự cung cấp exactly-once** khi client gửi lại lệnh sau timeout.
- Driver cũng không làm cho mọi DBMS có ngữ nghĩa SQL hoặc mức cô lập hoàn toàn giống nhau; JDBC chuẩn hóa giao diện, không xóa hết khác biệt của DBMS.

## 4. DataSource là hợp đồng cấp Connection

**javax.sql.DataSource** là một giao diện JDBC cho phép code yêu cầu **Connection** mà không cần biết trực tiếp URL, credential hoặc cách tạo connection:

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.SQLException;

public final class CustomerDao {
    private final DataSource dataSource;

    public CustomerDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean connectionAvailable() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            return connection.isValid(2);
        }
    }
}
~~~

Đây là ví dụ về cách dùng giao diện, **không phải health-check nên gọi trước mọi truy vấn**. Việc chủ động gọi **isValid** cho mỗi request có thể tạo thêm round-trip; pool và cơ chế health-check của ứng dụng nên được cấu hình đúng để tránh kiểm tra dư thừa.

Lợi ích thiết kế:

- **Tách phụ thuộc:** DAO phụ thuộc DataSource thay vì hard-code phương thức **DriverManager.getConnection(...)**.
- **Thay triển khai:** cùng DAO có thể dùng DataSource đơn giản lúc thử nghiệm và một pool trong môi trường sản xuất.
- **Cấu hình tập trung:** URL, credential, TLS, chính sách pool và metrics được quản lý ở ranh giới khởi tạo ứng dụng.
- **Tích hợp container/framework:** Spring có thể cấp DataSource qua dependency injection; application server có thể cung cấp nguồn kết nối qua JNDI.
- **Kiểm thử:** có thể tiêm DataSource trỏ tới database thử nghiệm mà không sửa logic nghiệp vụ.

**DataSource không mặc nhiên là pool.** Một DataSource đơn giản có thể tạo connection vật lý mới mỗi lần gọi; một DataSource như **HikariDataSource** tích hợp pool và trả connection được quản lý. Tên interface không cho biết chi phí của **getConnection()**; phải xác định triển khai thực tế.

### DriverManager đặt ở đâu?

**java.sql.DriverManager** là cách lấy connection trực tiếp dựa trên URL và driver đã đăng ký:

~~~java
try (Connection connection = java.sql.DriverManager.getConnection(
        jdbcUrl, username, password)) {
    // Làm việc với một kết nối JDBC.
}
~~~

Cách này có thể hữu ích cho ví dụ ngắn hoặc chương trình nhỏ, nhưng **mỗi lần getConnection thường thiết lập một kết nối mới** nếu không có lớp quản lý khác. Với web service nhiều request, nên dùng **DataSource được khởi tạo và quản lý vòng đời tập trung**, thường với connection pool.

## 5. Connection pool giải quyết vấn đề nào?

Tạo connection vật lý đến PostgreSQL thường có chi phí: mở socket, xác thực, thiết lập phiên và dùng tài nguyên phía server. Nếu hàng trăm request liên tiếp đều mở/đóng kết nối vật lý riêng, ứng dụng chịu thêm độ trễ và database phải quản lý nhiều phiên ngắn hạn.

**Connection pool** quản lý một nhóm kết nối vật lý có thể tái sử dụng:

~~~text
                    HikariDataSource
                           |
           +---------------+---------------+
           |               |               |
   physical conn A  physical conn B  physical conn C
           |               |               |
           +---------------+---------------+
                           |
                  Borrow / release
                           |
                    Java request
                           |
                logical connection
~~~

Ở một pool như HikariCP, ứng dụng thường nhận **logical connection** (một đối tượng bọc/delegate cho kết nối được quản lý). Khi gọi **close()** trên logical connection:

1. Ứng dụng kết thúc quyền sử dụng connection đó.
2. Pool có thể dọn/reset trạng thái đã thay đổi và kiểm tra điều kiện tái sử dụng theo thiết kế của pool.
3. Connection vật lý **thường được trả về pool**, không nhất thiết đóng socket tới database.
4. Nếu connection hỏng, quá hạn sử dụng hoặc pool đang đóng, pool có thể loại bỏ connection vật lý và tạo connection thay thế khi phù hợp.

Một pool điển hình còn có **giới hạn số kết nối**, hàng đợi chờ mượn, cơ chế kiểm tra kết nối, chính sách vòng đời, metrics và phát hiện connection bị giữ lâu.

**Không coi pool là bộ nhớ đệm dữ liệu SQL.** Connection pool tái sử dụng kết nối; nó không mặc nhiên cache mọi kết quả SELECT hay biến một câu SQL chậm thành câu SQL nhanh. Một số driver có cơ chế cache prepared statement trên từng connection, nhưng đó là trách nhiệm và cấu hình riêng.

## 6. Vòng đời của một connection: vật lý và logic

Hai lớp đối tượng cần phân biệt:

| Khái niệm | Vòng đời | Thành phần sở hữu |
| --- | --- | --- |
| **Physical connection** | Có thể sống qua nhiều request, gắn với phiên DB/socket | Pool hoặc DataSource tạo connection |
| **Logical/borrowed Connection** | Chỉ nên sống trong phạm vi một đơn vị truy cập/giao dịch | Code đang mượn hoặc transaction manager |
| **Statement/ResultSet** | Trong phạm vi thao tác truy vấn và tiêu thụ kết quả | Code hoặc framework tạo chúng |
| **Transaction** | Bắt đầu, thực hiện một nhóm thao tác, rồi commit/rollback | Service/transaction manager hoặc code JDBC thủ công |

Sơ đồ một request dùng pool:

~~~text
Pool giữ physical connection A
          |
Request #1 mượn A ----> chạy SQL ----> close logical connection
          |                                  |
          +----------------------------------+
                    A quay lại pool

Request #2 có thể mượn A ở thời điểm sau
~~~

Đối tượng Connection trả về của lần mượn thứ hai không cần là cùng Java object với lần thứ nhất. **Không giữ lại logical connection sau close()**, không tái sử dụng PreparedStatement của lượt mượn trước, và không chia sẻ cùng Connection để nhiều thread cùng chạy transaction.

### Pool có tự rollback khi code quên không?

Một pool chất lượng cố gắng ngăn việc giao dịch dở dang bị tái sử dụng; nhưng **ứng dụng vẫn phải commit hoặc rollback rõ ràng khi tự quản lý transaction**. Không xây dựng nghiệp vụ dựa trên giả định rằng **Connection.close()** sẽ luôn thay bạn chọn đúng rollback, hoặc sẽ hiểu một use case đã thành công hay thất bại. Khi rollback thất bại vì mất kết nối, connection có thể không còn an toàn để tái sử dụng.

## 7. Ví dụ HikariCP: cấu hình một DataSource có pool

Giả sử ứng dụng có dependency **HikariCP** và **PostgreSQL JDBC driver** phù hợp với phiên bản Java. Đoạn dưới đây khởi tạo một pool cho một ứng dụng nhỏ, thực hiện SELECT và đóng pool khi chương trình kết thúc:

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public final class DataSourceExample {
    public static void main(String[] args) throws Exception {
        HikariConfig config = new HikariConfig();

        // Ví dụ: DB_URL = jdbc:postgresql://db.example.internal:5432/app
        config.setJdbcUrl(System.getenv("DB_URL"));
        config.setUsername(System.getenv("DB_USER"));
        config.setPassword(System.getenv("DB_PASSWORD"));
        config.setMaximumPoolSize(10);
        config.setConnectionTimeout(2_000); // mili giây: chờ mượn.
        config.setPoolName("orders-db");

        // Ở đây main sở hữu vòng đời pool.
        try (HikariDataSource dataSource = new HikariDataSource(config)) {
            String sql = "SELECT count(*) FROM orders";
            try (Connection connection = dataSource.getConnection();
                 PreparedStatement statement =
                         connection.prepareStatement(sql);
                 ResultSet rs = statement.executeQuery()) {
                rs.next();
                System.out.println("orders = " + rs.getLong(1));
            }
        }
    }
}
~~~

Điểm cốt lõi của ví dụ:

- Tạo **một HikariDataSource** cho vòng đời ứng dụng/nguồn dữ liệu, **không tạo pool mới trong từng request**.
- HikariCP quản lý connection vật lý; PostgreSQL JDBC driver thực hiện kết nối và giao thức SQL tới PostgreSQL.
- **Connection.close()** trong try-with-resources trả connection mượn về pool theo cơ chế của HikariCP.
- **HikariDataSource.close()** khi ứng dụng ngừng là đóng **chính pool**, khác với đóng một connection mượn.
- **connectionTimeout=2000** chỉ ràng buộc thời gian đợi mượn từ pool theo HikariCP; nó không đặt timeout mỗi câu SELECT là hai giây.
- Lấy credential từ môi trường minh họa việc không hard-code mật khẩu trong source. Trong sản xuất, dùng cơ chế secret management và cấu hình TLS/ủy quyền phù hợp; biến môi trường không tự bảo đảm bí mật trong mọi môi trường vận hành.

Nếu thiếu một trong ba biến môi trường, đoạn mã có thể lỗi khi khởi tạo pool; ứng dụng thật nên **validate cấu hình và báo lỗi khởi động an toàn** thay vì tiếp tục với kết nối không đầy đủ. Khi dùng Spring Boot, thông thường để framework quản lý bean DataSource và đóng pool ở cuối vòng đời ứng dụng, không tạo thủ công thêm một pool giống vậy.

## 8. Repository phụ thuộc DataSource thay vì phụ thuộc pool cụ thể

Một DAO có thể nhận DataSource qua constructor:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderLookupDao {
    private final DataSource dataSource;

    public OrderLookupDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean exists(long tenantId, long orderId)
            throws SQLException {
        String sql = """
            SELECT 1 FROM orders
            WHERE tenant_id = ? AND id = ?
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setLong(1, tenantId);
            statement.setLong(2, orderId);

            try (ResultSet rs = statement.executeQuery()) {
                return rs.next();
            }
        }
    }
}
~~~

DAO không cần import **HikariDataSource** hay biết pool có bao nhiêu connection. Đây là lợi ích của **phụ thuộc vào abstraction**. Nó cũng không nên tự in credential, tạo thêm DataSource mới hoặc can thiệp chính sách retry toàn ứng dụng.

Tuy nhiên, cách **tự gọi dataSource.getConnection()** trong từng DAO ở trên phù hợp với thao tác độc lập **chưa nằm trong transaction Spring do framework sở hữu**. Nếu nhiều DAO phải cùng tham gia một transaction Spring, ưu tiên **JdbcTemplate**, **DataSourceUtils** hoặc cơ chế framework hỗ trợ tham gia transaction, thay vì mỗi DAO tự lấy một connection rồi tưởng chúng cùng transaction.

## 9. Driver, DataSource và pool không quyết định transaction boundary

Một câu SQL độc lập có thể dùng auto-commit; một nghiệp vụ nhiều bước phải dùng transaction để tất cả thay đổi được xác nhận cùng nhau. Điều này do **người thiết kế use case** quyết định.

~~~text
Application service: PlaceOrder
       |
       +-- UPDATE inventory
       +-- INSERT orders
       +-- INSERT order_events
       |
       +-- COMMIT nếu mọi bước hợp lệ
       +-- ROLLBACK nếu có lỗi
~~~

### 9.1. JDBC thuần: một Connection cho một transaction

Ví dụ dùng một connection để trừ tồn kho và tạo đơn:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderCommandDao {
    private final DataSource dataSource;

    public OrderCommandDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void placeOrder(
            long tenantId, long productId, long quantity
    ) throws SQLException {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity phải dương");
        }

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                String decrease = """
                    UPDATE inventory
                    SET available = available - ?
                    WHERE tenant_id = ? AND product_id = ?
                      AND available >= ?
                    """;
                try (PreparedStatement st =
                             connection.prepareStatement(decrease)) {
                    st.setLong(1, quantity);
                    st.setLong(2, tenantId);
                    st.setLong(3, productId);
                    st.setLong(4, quantity);
                    if (st.executeUpdate() != 1) {
                        throw new IllegalStateException("Không đủ tồn kho");
                    }
                }

                String insert = """
                    INSERT INTO orders(tenant_id, product_id, quantity)
                    VALUES (?, ?, ?)
                    """;
                try (PreparedStatement st =
                             connection.prepareStatement(insert)) {
                    st.setLong(1, tenantId);
                    st.setLong(2, productId);
                    st.setLong(3, quantity);
                    st.executeUpdate();
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

Trong đoạn này:

1. Pool chỉ **cấp một connection**; không biết thao tác nào là “đặt hàng”.
2. Code chủ động gọi **setAutoCommit(false)**, thực thi hai câu SQL và kiểm tra điều kiện nghiệp vụ.
3. **commit()** xác nhận hai bước cùng nhau; khi lỗi, code cố gắng **rollback()**.
4. Sau khi kết thúc và đóng connection, pool có thể tái sử dụng physical connection cho request khác.

Đây là ví dụ về ranh giới transaction chứ chưa phải thiết kế đơn hàng đầy đủ. Hệ thống thực cần xác thực tenant, bảo vệ lặp yêu cầu bằng request ID, kiểm soát đồng thời và ghi lịch sử nghiệp vụ phù hợp. **Hai lần gọi placeOrder** vẫn có thể tạo hai đơn nếu caller retry sau kết quả commit không chắc chắn.

### 9.2. Vì sao không bật lại auto-commit trong finally một cách mù quáng?

Theo hợp đồng JDBC, thay đổi chế độ auto-commit khi có transaction đang hoạt động có thể **commit transaction đó**. Vì vậy, nếu rollback thất bại mà code lập tức gọi **setAutoCommit(true)**, có nguy cơ xác nhận thay đổi dở dang trên connection còn sống. Với connection do method sở hữu, cần kết thúc transaction rõ ràng và **close**; pool/driver phải quản lý việc bỏ kết nối không tin cậy. Nếu connection do transaction manager sở hữu, **không tự đổi auto-commit hoặc commit/rollback** bên trong DAO.

## 10. Spring quản lý transaction như thế nào?

Trong ứng dụng Spring JDBC phổ biến:

~~~text
HTTP request
   |
Application service @Transactional
   |
Transaction manager bắt đầu transaction
   |
JdbcTemplate / Repository A ------+
JdbcTemplate / Repository B ------+--> Connection tham gia
JdbcTemplate / Repository C ------+    cùng transaction
   |
Transaction manager COMMIT / ROLLBACK
   |
Trả connection về pool
~~~

Ví dụ service:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryOrderService {
    private final JdbcTemplate jdbc;

    public InventoryOrderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void reserve(long tenantId, long productId, long quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity phải dương");
        }

        int changed = jdbc.update(
            """
            UPDATE inventory
            SET available = available - ?
            WHERE tenant_id = ? AND product_id = ?
              AND available >= ?
            """,
            quantity, tenantId, productId, quantity
        );
        if (changed != 1) {
            throw new IllegalStateException("Không đủ tồn kho");
        }

        jdbc.update(
            """
            INSERT INTO orders(tenant_id, product_id, quantity)
            VALUES (?, ?, ?)
            """,
            tenantId, productId, quantity
        );
    }
}
~~~

Giả định **DataSourceTransactionManager/JdbcTransactionManager** hoặc transaction manager tương thích được cấu hình đúng với DataSource; **JdbcTemplate** tham gia transaction đang hoạt động. Spring mặc định thường rollback với **RuntimeException** và **Error**; quy tắc cho checked exception cần được kiểm tra và cấu hình nếu nghiệp vụ yêu cầu.

Cần phân biệt:

- **DataSource** cấp nguồn kết nối.
- **Connection pool** quản lý khả năng tái sử dụng và giới hạn phiên DB.
- **JdbcTemplate** giúp quản lý thao tác JDBC, binding tham số và giải phóng tài nguyên theo context Spring.
- **Transaction manager** quyết định bắt đầu, gắn tài nguyên với transaction, commit và rollback.
- **@Transactional** chỉ phát huy đúng khi lời gọi đi qua cơ chế transaction của Spring. Với proxy thông thường, lời gọi nội bộ **this.reserve(...)** có thể không được interceptor xử lý.

Nếu DAO bên trong **@Transactional** gọi trực tiếp **DriverManager.getConnection(...)** hoặc lấy connection độc lập từ pool không qua cơ chế tham gia transaction, thao tác ấy có thể nằm **ngoài transaction Spring** và commit riêng. Đó là lỗi ranh giới, không phải lỗi của driver.

### JPA/Hibernate và DataSource

JPA/Hibernate quản lý EntityManager, persistence context và dirty checking, nhưng cuối cùng vẫn cần tương tác với DB qua driver/kết nối do cấu hình xác định. **JpaTransactionManager** hoặc transaction manager tương ứng điều phối tài nguyên của JPA. Không suy rằng mọi thao tác JDBC trực tiếp và mọi EntityManager từ các DataSource khác nhau sẽ tự dùng cùng connection chỉ vì chúng chạy trong một method có annotation.

## 11. Timeout thuộc tầng nào?

Khi một request có lỗi timeout, trước hết cần xác định nó đang đợi **lấy connection**, **mở socket**, **câu SQL**, hay **kết thúc transaction**.

| Giới hạn | Tầng tiêu biểu | Phạm vi/đơn vị |
| --- | --- | --- |
| **HikariCP connectionTimeout** | Pool | Thời gian tối đa chờ mượn connection từ pool, **mili giây** |
| **pgJDBC connectTimeout** | Driver | Giới hạn thao tác socket connect theo driver, thường **giây** |
| **pgJDBC socketTimeout** | Driver/mạng | Thời gian chờ đọc dữ liệu socket, **giây**; có thể ảnh hưởng tính sử dụng của connection |
| **Statement.setQueryTimeout(...)** | JDBC statement/driver | Thời gian thực thi statement theo hợp đồng JDBC, **giây** |
| **PostgreSQL statement_timeout** | Database | Giới hạn thời gian statement ở server; cấu hình thời lượng như **'2s'** |
| **PostgreSQL lock_timeout** | Database | Giới hạn các lượt chờ lấy khóa; không phải tổng thời gian query |
| **Spring @Transactional(timeout = ...)** | Transaction manager | Giới hạn cho transaction mới theo cơ chế manager, **giây** |

Ví dụ:

~~~properties
# HikariCP: 1.5 giây chờ lấy connection từ pool.
spring.datasource.hikari.connection-timeout=1500
spring.datasource.hikari.maximum-pool-size=10
~~~

~~~java
try (Connection c = dataSource.getConnection();
     PreparedStatement st = c.prepareStatement(
             "SELECT count(*) FROM orders")) {
    st.setQueryTimeout(3); // Giây; khác pool connectionTimeout.
    try (ResultSet rs = st.executeQuery()) {
        rs.next();
    }
}
~~~

Ở PostgreSQL:

~~~sql
BEGIN;
SET LOCAL statement_timeout = '3s';
SET LOCAL lock_timeout = '500ms';

-- Câu SQL có thể bị hủy nếu vượt các giới hạn tương ứng.
SELECT count(*) FROM orders;
COMMIT;
~~~

**SET LOCAL** chỉ có hiệu lực trong transaction hiện tại. Điều này thường an toàn hơn **SET** ở cấp session nếu connection sẽ được trả về pool; các thay đổi cấu hình session qua SQL có thể tồn tại cho request sau.

Không có một tham số timeout duy nhất bảo đảm toàn bộ HTTP request kết thúc đúng thời điểm: pool wait, SQL, logic Java, gọi API ngoài và commit có thể chiếm các khoảng thời gian riêng. Cần thiết kế ngân sách end-to-end và cleanup khi cancellation.

## 12. Kích thước pool: nhiều connection hơn không luôn nhanh hơn

Giả sử một ứng dụng chạy **8 instance**, mỗi instance cấu hình **maximumPoolSize = 30**:

~~~text
Tối đa từ ứng dụng này: 8 * 30 = 240 kết nối DB
~~~

Nếu database chỉ cho phép 200 connection và còn nhiều ứng dụng/tiến trình quản trị khác cần truy cập, cấu hình này có nguy cơ vượt giới hạn hoặc tăng tranh chấp. Pool size phải xét **tổng theo số instance**, không chỉ nhìn một JVM.

Một công thức ngân sách sơ bộ:

~~~text
Tổng tối đa connection tiềm năng
  = tổng(maximumPoolSize của từng instance và dịch vụ)
  + connection của batch/worker/BI/khác

Mục tiêu: không vượt ngân sách DB sau khi giữ phần dự phòng vận hành.
~~~

Đây là **giới hạn năng lực tiềm năng**, không có nghĩa mọi pool luôn mở ngay đúng maximumPoolSize. Số connection thực tế phụ thuộc pool, minimumIdle, nhu cầu tải và chính sách quản lý.

### 12.1. Pool nhỏ quá

- Request chờ mượn connection, tăng **pending threads** và **acquisition latency**.
- Có thể xuất hiện lỗi **connection is not available** khi vượt **connectionTimeout**.
- Nếu database thực ra còn dư năng lực và truy vấn ngắn, điều chỉnh pool hợp lý có thể cải thiện throughput.

### 12.2. Pool lớn quá

- Database phải duy trì thêm session, bộ nhớ và tài nguyên đồng thời.
- Nhiều transaction cùng chạy có thể tăng lock contention, I/O và thời gian chờ.
- Query chậm không tự nhanh hơn; có thể làm database bị quá tải và khiến độ trễ p95/p99 xấu đi.

### 12.3. Virtual threads không tạo thêm connection vật lý

Java virtual threads giúp giảm chi phí quản lý nhiều tác vụ chờ, nhưng **mỗi thao tác JDBC blocking đang dùng connection vẫn phải có một connection thích hợp**. Có hàng chục nghìn virtual threads không có nghĩa có thể mở hàng chục nghìn database sessions an toàn. Pool vẫn là một giới hạn tài nguyên quan trọng và cần bảo đảm backpressure.

**Không có một kích thước pool tối ưu cho mọi hệ thống.** Cần đo thời gian giữ connection, số request đồng thời, throughput, lock wait, CPU/I/O của DB, cấu hình nhiều instance và dự phòng cho vận hành.

## 13. Phân biệt connection leak và connection giữ lâu hợp lệ

Một connection được mượn mà **không trả về** sẽ dần làm pool cạn. Lỗi thường gặp:

~~~java
Connection c = dataSource.getConnection();
PreparedStatement st = c.prepareStatement("SELECT * FROM orders");
ResultSet rs = st.executeQuery();
// Nếu code ném exception trước khi đóng c, connection có thể bị giữ.
~~~

Cách sửa là dùng try-with-resources hoặc để framework sở hữu tài nguyên đúng phạm vi.

Tuy nhiên, cảnh báo leak detection **không luôn chứng minh code quên close()**. Một transaction có thể giữ connection hợp lệ nhưng quá lâu vì:

- Chờ khóa của giao dịch khác.
- Gọi HTTP API trong transaction.
- Streaming/đọc ResultSet khổng lồ, xử lý từng hàng chậm.
- Chờ người dùng hoặc chạy tác vụ CPU dài giữa hai câu SQL.
- Transaction mở rồi bị bỏ ở trạng thái **idle in transaction**.

Với HikariCP, **leakDetectionThreshold** giúp log cảnh báo khi connection bị mượn quá lâu theo cấu hình; nó là **công cụ chẩn đoán**, không tự sửa logic, không quyết định có lỗi nghiệp vụ, và có thể báo cả giao dịch dài hợp lệ.

### Dòng ResultSet lớn cũng giữ tài nguyên

Ngay cả khi SQL đầu tiên hoàn tất, việc tiêu thụ một **ResultSet streaming** có thể giữ connection và transaction cho tới khi đọc hết hoặc đóng cursor/statement. Với PostgreSQL JDBC, cách dùng fetch size và auto-commit có thể ảnh hưởng việc dùng cursor phía server. Không mặc định rằng chỉ cần đặt **fetchSize** là có streaming trong mọi tình huống; phải hiểu driver, cursor, transaction và đóng tài nguyên đúng lúc.

## 14. Reset trạng thái connection giữa các request

Tái sử dụng physical connection là lợi ích lớn của pool, nhưng cũng tạo yêu cầu **trạng thái request cũ không được rò sang request mới**. Các thuộc tính có thể bao gồm:

- **autoCommit**.
- **transaction isolation** và **readOnly**.
- **schema/catalog** và một số thuộc tính JDBC khác.
- Session variables, **SET** SQL phía database, temporary tables, session-level advisory locks hoặc các setting riêng của DBMS.

Pool thường theo dõi và khôi phục nhiều thuộc tính mà code thay đổi qua **API Connection chuẩn**. Nhưng pool **không nhất thiết phát hiện mọi thay đổi session được thực hiện qua câu SQL tùy ý**, ví dụ:

~~~sql
-- Có thể tồn tại ở phạm vi session khi không được reset.
SET statement_timeout = '500ms';
SET search_path = some_schema;
~~~

Nếu sau đó connection được mượn bởi request khác, những thay đổi này có thể gây hành vi bất ngờ hoặc nghiêm trọng hơn là sai ranh giới truy cập dữ liệu. Cách khắc phục:

1. Đặt chính sách session mặc định ở nơi quản lý cấu hình có kiểm soát.
2. Ưu tiên **SET LOCAL** trong transaction cho các thông số chỉ cần ở một use case.
3. Để transaction manager/pool điều phối những thuộc tính JDBC mà chúng hiểu rõ.
4. Nếu buộc dùng session state, cần cơ chế reset chắc chắn trước khi tái sử dụng.
5. Không dùng sự tồn tại của một biến session như biện pháp thay thế xác thực/ủy quyền; các chính sách tenant phải được thiết kế và kiểm tra chống rò rỉ.

Ở PostgreSQL, **SET LOCAL** chỉ có phạm vi transaction; sau commit/rollback, giá trị cục bộ hết hiệu lực. Không đặt **SET LOCAL** rồi kỳ vọng nó tồn tại qua một transaction mới.

## 15. Connection hỏng, SQLException và retry

Kết nối vật lý có thể hỏng vì server restart, proxy/ngắt mạng, timeout socket, thay đổi TLS hoặc database đóng session. Driver báo lỗi theo JDBC; pool cần phát hiện và thay thế connection không còn sử dụng được. Ứng dụng vẫn phải quyết định **nghiệp vụ có được retry hay không**.

| Tình huống | Vai trò của từng tầng |
| --- | --- |
| Pool không cấp connection trước deadline | Pool báo acquisition timeout; ứng dụng xử lý quá tải/backpressure |
| Driver không mở được socket | Driver báo connect failure; pool có thể thử chiến lược tạo khác theo cấu hình |
| SQL bị hủy vì statement timeout | DB/driver báo SQLException; transaction có thể cần rollback |
| Kết nối đứt giữa transaction | Driver báo connection failure; pool không nên tái sử dụng connection hỏng |
| Kết nối đứt đúng lúc COMMIT | Client **có thể không biết** server đã commit hay chưa |
| Deadlock hoặc serialization failure | DB hủy một giao dịch theo quy tắc; ứng dụng có thể retry toàn bộ transaction |

Trong PostgreSQL, SQLSTATE thường gặp gồm **08xxx** (nhóm connection exception), **40001** (serialization failure), **40P01** (deadlock detected), **57014** (query canceled). Chỉ dựa vào SQLSTATE là chưa đủ để kết luận mọi lỗi thuộc nhóm đó đều retryable; cần xét idempotency, transaction state, deadline và nguyên nhân thực tế.

### 15.1. Commit không rõ kết quả

Một tình huống quan trọng:

~~~text
Java gửi COMMIT --> DB commit thành công
                         |
                   phản hồi bị mất
                         |
Java thấy SQLException / timeout
~~~

**Driver và pool không thể tự bảo đảm lần COMMIT này chưa xảy ra.** Nếu service tạo đơn, trừ tiền hoặc cộng điểm rồi retry toàn bộ logic với một request ID mới, có thể sinh tác động hai lần. Hệ thống cần **idempotency key, unique constraint và cơ chế đối soát** trạng thái trên connection mới trước khi thử lại an toàn.

### 15.2. Không chuyển lỗi mất connection thành “rollback chắc chắn”

Khi một câu SQL lỗi bên trong PostgreSQL transaction, transaction thường phải **ROLLBACK** trước khi tiếp tục. Nhưng khi mất kết nối đúng lúc commit, client có thể không xác định được kết quả; một lệnh rollback được thử sau đó có thể thất bại hoặc không đảo ngược một commit đã hoàn tất. Hãy ghi nhận trạng thái **UNKNOWN** nếu cần và tra lại trạng thái nghiệp vụ thay vì tự phỏng đoán.

## 16. Bảo mật: driver/pool không thay thế chính sách dữ liệu

Ranh giới bảo mật cần được xem xét ở từng lớp:

**Kết nối và xác thực.** Driver sử dụng credential, phương thức xác thực và cấu hình TLS được hỗ trợ. Nếu yêu cầu mã hóa và xác minh server, phải cấu hình TLS cùng chính sách xác thực chứng chỉ/hostname phù hợp; không giả định một JDBC URL bình thường luôn xác minh đúng danh tính DB server.

**Quản lý secret.** Không hard-code mật khẩu trong source hoặc log. Dùng dịch vụ quản lý secret, phân quyền truy cập và cơ chế xoay credential có kế hoạch. Connection pool có thể tiếp tục giữ các phiên đã xác thực sau khi credential đổi; cần chiến lược làm mới connection hợp lệ, không chỉ thay giá trị secret trong cấu hình.

**Quyền DB tối thiểu.** Tài khoản ứng dụng chỉ nên có quyền cần thiết. Kết nối có thể thành công nhưng việc truy vấn bảng ngoài phạm vi là lỗi phân quyền cần xử lý, không phải lỗi pool.

**PreparedStatement.** Truyền tham số qua bind variables cho giá trị dữ liệu; tránh ghép chuỗi SQL từ input người dùng. PreparedStatement không làm an toàn mọi phần SQL động như tên bảng, tên cột hay ORDER BY được nội suy tùy ý; cần allowlist các định danh hợp lệ.

**Ranh giới tenant.** Cần ràng buộc truy vấn theo tenant và xác thực quyền của người gọi. Nếu dùng Row Level Security hoặc session variables, phải thiết kế chống rò session state khi connection được trả về pool.

**Log và metrics.** Có thể log loại exception, SQLSTATE, thời gian mượn connection và correlation ID, nhưng tránh in nguyên credential, token hoặc dữ liệu nhạy cảm trong tham số SQL.

## 17. Theo dõi pool và DB để biết đang nghẽn ở đâu

Khi một API chậm hoặc hết connection, các số liệu có giá trị hơn việc chỉ xem exception cuối:

| Vị trí | Chỉ số nên xem | Cách diễn giải ban đầu |
| --- | --- | --- |
| **Pool** | Active connections | Có bao nhiêu connection đang được mượn |
| **Pool** | Idle connections | Có bao nhiêu connection sẵn sàng cấp |
| **Pool** | Pending/waiting requests | Có bao nhiêu request đang đợi connection |
| **Pool** | Acquisition timeout / wait duration | Có quá tải hoặc connection bị giữ lâu không |
| **Ứng dụng** | Transaction duration | Use case có giữ connection/khóa quá lâu không |
| **JDBC/DB** | SQL latency, lock wait, cancel | Truy vấn chậm do kế hoạch, khóa hay I/O |
| **Database** | Số session, trạng thái hoạt động | Có quá nhiều connection, idle transaction hoặc lock wait không |

### 17.1. Truy vấn quan sát PostgreSQL

Ví dụ chẩn đoán trên môi trường có quyền quan sát:

~~~sql
SELECT pid,
       application_name,
       state,
       wait_event_type,
       wait_event,
       now() - xact_start AS transaction_age
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

Nếu thấy nhiều **idle** connection trong PostgreSQL, điều đó **không tự chứng minh connection leak**: pool được thiết kế để giữ physical sessions nhàn rỗi. Ngược lại, **idle in transaction** là dấu hiệu cần điều tra vì session có transaction chưa kết thúc và có thể giữ tài nguyên. Quyền thấy chi tiết các session khác phụ thuộc vai trò kết nối.

Quan trọng: **pg_stat_activity không nhìn thấy những thread Java đang đứng đợi bên trong pool mà chưa có connection**. Cần metrics ở cả ứng dụng và DB để biết vấn đề nằm ở đâu.

### 17.2. Một quy trình chẩn đoán thực tế

1. Xác định request đang ở **getConnection**, đang execute SQL, đang xử lý Java hay đang commit.
2. So sánh **active/idle/pending** của pool với số connection trên DB và giới hạn cấu hình.
3. Đo transaction duration; tìm những use case giữ connection quá lâu.
4. Kiểm tra SQL chậm, lock wait, transaction idle và các đợt timeout.
5. Kiểm tra số application instances, worker/batch và tổng ngân sách connection.
6. Chỉ sau đó mới quyết định tối ưu SQL, rút ngắn transaction, giới hạn tải hay điều chỉnh pool size.

Tăng pool có thể giúp khi DB còn dư năng lực và số request chờ tăng do pool quá nhỏ; nhưng nếu mọi connection đang chờ cùng một hàng bị khóa, tăng pool còn có thể làm tranh chấp nặng hơn.

## 18. Kết hợp với các công nghệ Java khác

### 18.1. JdbcTemplate

**JdbcTemplate** vẫn dùng JDBC driver và DataSource phía dưới. Nó giảm code quản lý PreparedStatement/ResultSet và phối hợp tài nguyên với Spring transaction manager. Nó **không thay thế** pool; ứng dụng vẫn nên cấu hình DataSource phù hợp.

### 18.2. JPA/Hibernate

JPA/Hibernate thêm abstraction entity, persistence context, dirty checking và ORM SQL generation. Nhưng kết nối tới DB quan hệ vẫn cần driver và cơ chế cấp kết nối được cấu hình. **Pool không biết entity nào đang dirty**; ORM/transaction manager mới phối hợp flush và commit. Đóng persistence context không đồng nghĩa mọi transaction hoặc connection vật lý có cùng vòng đời trong mọi cấu hình.

### 18.3. JNDI/managed DataSource

Trong một application server, DataSource có thể được container tạo và quản lý, rồi ứng dụng lấy qua JNDI hoặc dependency injection. Khi đó ứng dụng không tự đóng pool toàn cục; nó chỉ giải phóng tài nguyên thuộc phạm vi mà mình sở hữu.

### 18.4. R2DBC

**R2DBC** là một hệ API/driver truy cập cơ sở dữ liệu **reactive/non-blocking**, khác với JDBC blocking. Các ứng dụng dùng R2DBC có thể có cơ chế ConnectionFactory và pool riêng. Không lấy các quy tắc của **javax.sql.DataSource**, **java.sql.Connection** hoặc transaction thread-bound của Spring JDBC rồi áp nguyên xi cho R2DBC.

### 18.5. Read replica và nhiều nguồn dữ liệu

Ứng dụng có thể có DataSource cho primary và DataSource cho read replica. Mỗi nguồn có chính sách kết nối, pool và tính nhất quán riêng. Một transaction trên primary không tự làm cho truy vấn lập tức thấy commit mới nhất trên replica; replication lag và routing policy phải được xử lý có chủ đích.

## 19. Những lỗi thiết kế phổ biến

| Nhầm lẫn/lỗi | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Nghĩ **DataSource = pool** trong mọi ứng dụng | Dùng DataSource không pooling mà không biết chi phí mở kết nối | Xác định triển khai thực tế của DataSource |
| Tạo **HikariDataSource** trong mỗi HTTP request | Tạo nhiều pool, nhiều kết nối vật lý, dễ cạn DB | Một pool được quản lý theo vòng đời ứng dụng/nguồn dữ liệu |
| Không đóng Connection mượn | Pool cạn, request mới timeout | try-with-resources hoặc transaction manager |
| Tự đóng Connection do framework sở hữu | Can thiệp vòng đời transaction và tài nguyên | Dùng JdbcTemplate/DataSourceUtils/repository phù hợp |
| Gọi **DriverManager.getConnection** bên trong @Transactional | SQL có thể chạy ở connection và giao dịch độc lập | Tham gia transaction qua hạ tầng Spring |
| Cho rằng **Connection.close()** luôn đóng socket DB | Không hiểu vì sao DB vẫn có session nhàn rỗi | Phân biệt logical close và physical close |
| Tăng pool để chữa SQL chậm hoặc lock wait | Có thể làm DB quá tải, tăng tranh chấp | Đo wait events, SQL và transaction duration |
| Nhầm pool connectionTimeout với query timeout | Cấu hình sai tầng; lỗi vẫn xảy ra | Phân loại pool wait, connect, statement và transaction |
| Dùng SQL **SET** session mà không reset | Request sau thừa hưởng session state của request trước | SET LOCAL hoặc chiến lược reset đáng tin cậy |
| Chia sẻ JDBC Connection cho nhiều thread | Giao dịch/ResultSet có thể xen kẽ không an toàn | Mỗi unit of work dùng connection thuộc phạm vi riêng |
| Dùng auto-commit cho hai bước phải nguyên tử | Bước đầu có thể commit khi bước sau thất bại | Giao dịch bao trùm use case |
| Coi timeout tại COMMIT là rollback chắc chắn | Retry tạo đơn/thanh toán hai lần | Idempotency key và đối soát trạng thái |
| Hard-code credential và tắt kiểm tra TLS | Tăng nguy cơ lộ dữ liệu hoặc kết nối sai server | Secret management, TLS và phân quyền đúng |
| Xem connection pool là cache query | Bỏ qua chỉ mục, N+1, kế hoạch SQL và dữ liệu | Tối ưu truy vấn/ORM độc lập với pool |

## 20. Bài tập vận dụng

### Bài 1. Ba tầng làm gì?

Một ứng dụng dùng **HikariDataSource** và PostgreSQL JDBC driver. Khi code gọi **dataSource.getConnection()**, thành phần nào chịu trách nhiệm chính về việc cấp lại một connection sẵn có, và thành phần nào nói chuyện giao thức PostgreSQL?

**Gợi ý:** HikariCP quản lý pool và cấp logical connection; pgJDBC hiện thực giao tiếp JDBC với PostgreSQL. DataSource là hợp đồng mà HikariDataSource triển khai.

### Bài 2. Vì sao gọi close mà DB vẫn có session?

Sau khi API gọi **Connection.close()**, nhóm vận hành vẫn thấy các session **idle** trong **pg_stat_activity**. Có phải code không đóng connection?

**Gợi ý:** Chưa chắc. Khi có pool, close của logical connection thường trả physical connection về pool; physical session có thể tiếp tục ở trạng thái idle để tái sử dụng.

### Bài 3. Hai DAO trong một transaction

Service dùng **@Transactional**; DAO A dùng **JdbcTemplate**, DAO B gọi **DriverManager.getConnection(...)** rồi tự UPDATE. Có chắc hai UPDATE commit/rollback cùng nhau không?

**Gợi ý:** Không. DAO B có thể tạo connection và transaction độc lập, ngoài context Spring. Cần dùng tài nguyên tham gia cùng transaction manager hoặc thiết kế ranh giới khác có chủ đích.

### Bài 4. Tính ngân sách pool

Một hệ thống chạy 12 application instances, mỗi instance cho phép tối đa 25 connection. Ngoài ra batch workers có thể mở 40 connection. Tổng kết nối tiềm năng là bao nhiêu, và vì sao không nên cấu hình DB chỉ đủ đúng con số này?

**Gợi ý:** **12 × 25 + 40 = 340** connection tiềm năng. Cần dự phòng cho admin, monitoring, maintenance, các ứng dụng khác và khả năng mở rộng; đồng thời kiểm tra DB có đủ tài nguyên xử lý mức đồng thời đó không.

### Bài 5. Hikari connectionTimeout

Pool có 10 connection, cả 10 đang được mượn. Request mới chờ **getConnection()** rồi báo timeout sau 2 giây. Việc nâng **Statement.setQueryTimeout** từ 3 lên 30 giây có giúp trực tiếp không?

**Gợi ý:** Không. Request chưa nhận connection để chạy statement. Tăng query timeout có thể khiến request khác giữ connection lâu hơn. Cần tìm nguyên nhân pool không có connection sẵn.

### Bài 6. Session state

Một request chạy **SET search_path = tenant_a** bằng SQL rồi trả connection về pool. Request sau mượn cùng physical connection. Có nguy cơ gì?

**Gợi ý:** Session state có thể còn tồn tại nếu không được reset; truy vấn request sau có thể chạy với schema ngoài mong đợi, có nguy cơ sai hoặc lộ dữ liệu. Dùng chính sách tenant và reset session đúng cách; ưu tiên phạm vi transaction khi phù hợp.

### Bài 7. Connection bị mất lúc COMMIT

Java gửi COMMIT rồi nhận SQLException do socket bị đóng. Có thể khẳng định transaction đã rollback và thử lại với order ID mới không?

**Gợi ý:** Không. DB có thể đã commit, chỉ phản hồi bị mất. Cần tra lại trạng thái theo request ID/idempotency key và chống thực hiện hai lần.

### Bài 8. Virtual threads

Một service chuyển sang dùng nhiều virtual threads và thấy số request đồng thời tăng, nhưng pool vẫn có maximumPoolSize=20. Có nên tự động tăng lên 2.000 connection để khớp số virtual threads không?

**Gợi ý:** Không. Virtual threads giảm chi phí thread nhưng không làm DB có thêm tài nguyên. Đo thời gian giữ connection, throughput và năng lực server, áp backpressure và điều chỉnh pool có kiểm chứng.

## 21. Checklist khi thiết kế tầng persistence Java

Trước khi đưa một dịch vụ vào môi trường thật, tự kiểm tra:

1. **Driver:** đúng loại DBMS, tương thích phiên bản Java/DB, cấu hình URL, TLS và timeout connect rõ ràng.
2. **DataSource:** được tạo và quản lý vòng đời ở một nơi; DAO phụ thuộc interface thay vì tự tạo kết nối.
3. **Pool:** có giới hạn, không nhân bản theo request, có metrics active/idle/pending, thời gian chờ và chính sách vòng đời phù hợp.
4. **Tài nguyên:** Connection, Statement, ResultSet được đóng đúng quyền sở hữu; streaming không giữ pool quá lâu.
5. **Transaction:** use case nhiều bước được commit/rollback trong cùng context; không vô tình dùng connection ngoài transaction manager.
6. **Trạng thái phiên:** auto-commit/isolation/readOnly/schema và session SQL setting không rò giữa request.
7. **Bảo mật:** credential được bảo vệ, TLS được kiểm tra theo yêu cầu, quyền DB tối thiểu, tenant boundary không dựa vào giả định về pool.
8. **Lỗi:** phân loại pool acquisition, connect, query, lock, transaction và commit-unknown; chỉ retry khi an toàn.
9. **Năng lực:** tổng pool của mọi instance phù hợp giới hạn và công suất DB; đo trước khi tăng số connection.
10. **Quan sát:** biết đối chiếu metrics ứng dụng với tình trạng session, lock và I/O của database.

## 22. Ghi nhớ

**Driver** giải quyết cách Java giao tiếp với một DBMS. **DataSource** là giao diện cấp Connection cho code ứng dụng. **Connection pool** là cơ chế quản lý và tái sử dụng các connection vật lý, thường được cung cấp qua một triển khai DataSource. **Transaction manager** là thành phần khác, điều phối việc các thay đổi cùng commit hoặc rollback. Cả bốn đều có vai trò rõ ràng, nhưng không tầng nào thay thế được việc thiết kế đúng truy vấn, mô hình dữ liệu và ranh giới nghiệp vụ.

Trong ứng dụng Java, hãy để repository làm việc qua DataSource/abstraction phù hợp, để pool quản lý vòng đời kết nối vật lý, và để service/transaction manager sở hữu transaction. Phân biệt **logical close** với **physical close**, cấu hình timeout đúng tầng, ngăn rò session state và theo dõi năng lực DB trước khi tăng pool. Khi gặp lỗi kết nối hoặc commit không rõ kết quả, bổ sung **idempotency và đối soát**, thay vì kỳ vọng driver hay pool tự bảo đảm retry an toàn.
