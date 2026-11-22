# Chi phí tạo kết nối và vai trò của connection pool

Một dịch vụ Java có thể cần hàng trăm hoặc hàng nghìn lượt truy vấn cơ sở dữ liệu mỗi giây. Nếu mỗi lượt truy vấn đều mở một kết nối vật lý mới, xác thực, thực thi SQL rồi ngắt kết nối, thời gian thiết lập phiên và lượng tài nguyên phát sinh có thể chiếm phần đáng kể so với công việc đọc/ghi dữ liệu. **Connection pool** giải quyết vấn đề này bằng cách duy trì một tập kết nối có thể tái sử dụng và cho các luồng công việc mượn kết nối trong thời gian cần thiết.

Tuy nhiên, pool không biến cơ sở dữ liệu thành tài nguyên vô hạn. Pool quá nhỏ khiến nhiều yêu cầu chờ; pool quá lớn có thể khiến DBMS quá tải vì quá nhiều phiên và truy vấn đồng thời. Thiết kế tốt cần hiểu **chi phí mở kết nối**, **thời gian giữ kết nối**, **ngân sách kết nối trên toàn hệ thống** và **vòng đời giao dịch**.

Bài thuộc chương **Kết nối và tài nguyên** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Trong bối cảnh persistence cho Java, việc quản lý kết nối phải đi cùng thiết kế transaction, xử lý lỗi kết nối, bảo mật thông tin đăng nhập, theo dõi hiệu năng và khả năng phục hồi khi cơ sở dữ liệu gặp sự cố.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Chỉ ra các bước khiến việc thiết lập kết nối JDBC vật lý có chi phí cao hơn việc dùng kết nối đang mở.
2. Phân biệt kết nối vật lý, kết nối logic được mượn từ pool, phiên làm việc DBMS và transaction.
3. Giải thích cơ chế mượn, trả, kiểm tra và thay thế kết nối trong pool.
4. Chọn giới hạn pool dựa trên tải đồng thời, thời gian giữ kết nối và ngân sách phiên của cơ sở dữ liệu.
5. Sử dụng `DataSource`, `try-with-resources` và transaction JDBC để tránh rò rỉ hoặc giữ kết nối quá lâu.
6. Phân biệt timeout lấy kết nối, timeout thiết lập mạng, timeout câu lệnh và timeout chờ khóa.
7. Nhận biết pool exhaustion, kết nối chết, transaction lâu, tăng số replica và các rủi ro khi dùng connection proxy.

## 2. Kết nối đến cơ sở dữ liệu thực chất gồm những gì?

Khi Java gọi:

~~~java
Connection connection = DriverManager.getConnection(url, user, password);
~~~

driver cần thiết lập một **kết nối vật lý** tới DBMS, trừ khi có một tầng proxy hoặc cơ chế tái sử dụng bên dưới đã làm phần việc đó. Tùy loại cơ sở dữ liệu, driver, TLS và đường mạng, quá trình có thể gồm:

1. Xác định địa chỉ server: cấu hình host, DNS, endpoint cluster hoặc chuyển hướng đến nút phù hợp.
2. Thiết lập kết nối mạng, thường là TCP hoặc transport được hỗ trợ.
3. Thỏa thuận TLS nếu được bật hoặc được yêu cầu.
4. Thực hiện bắt tay giao thức, xác thực người dùng và lựa chọn cơ sở dữ liệu.
5. Thiết lập phiên (*session*), các thuộc tính ban đầu và tài nguyên server phục vụ kết nối.
6. Trả về đối tượng JDBC `Connection` để ứng dụng có thể gửi câu lệnh.

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant Driver as JDBC driver
    participant DB as Database
    App->>Driver: Mở connection vật lý
    Driver->>DB: Kết nối mạng / TLS (nếu dùng)
    DB-->>Driver: Bắt tay và xác thực
    Driver->>DB: Thiết lập phiên
    DB-->>Driver: Phiên sẵn sàng
    Driver-->>App: JDBC Connection
    App->>DB: Execute SQL
    DB-->>App: Kết quả
    App->>Driver: close()
    Driver->>DB: Đóng kết nối vật lý (không dùng pool)
~~~

Mỗi bước có thể có **độ trễ** và **chi phí tài nguyên**. Chẳng hạn:

- Bắt tay mạng và TLS có thể cần nhiều lượt trao đổi qua mạng. Với DB ở xa, độ trễ mạng được cộng vào thời gian mở kết nối.
- Xác thực và tạo session dùng CPU; server có thể cần cấp phát bộ nhớ hoặc cấu trúc thực thi. PostgreSQL truyền thống gắn mỗi kết nối client với một backend process; nhiều DBMS khác có kiến trúc tài nguyên khác.
- Mở rồi đóng liên tục làm tăng số thao tác điều khiển kết nối và có thể tạo đỉnh tải khi nhiều request cùng đến.
- Khi kết nối đã sẵn sàng, **mỗi truy vấn vẫn có chi phí mạng và thực thi SQL riêng**; pool chỉ giảm phần chi phí lặp lại của **thiết lập/đóng kết nối**, không bỏ qua việc thực thi SQL.

Không nên khẳng định “mở kết nối luôn mất X mili-giây”: chi phí thay đổi theo máy chủ, mạng, chứng chỉ, cấu hình xác thực và tải hiện tại. Đo trên môi trường thực với đúng DBMS và kiến trúc triển khai.

### 2.1. Phân biệt connection, session và transaction

| Khái niệm | Vai trò | Vòng đời |
|---|---|---|
| **Physical connection** | Kênh kết nối giữa client/proxy và DBMS | Được tạo, dùng lại hoặc đóng khi hỏng/hết vòng đời |
| **DB session** | Ngữ cảnh server gắn với kết nối hoặc cơ chế proxy | Có thể lưu trạng thái phiên như biến cấu hình, prepared statement, bảng tạm |
| **Logical connection / lease** | Quyền sử dụng một connection mà pool trao cho một đoạn mã | Bắt đầu khi `getConnection()` thành công, kết thúc khi `close()` |
| **Transaction** | Nhóm thao tác có ranh giới commit/rollback | Có thể gồm nhiều SQL trên cùng connection; kết thúc sớm nhất có thể |
| **Statement / ResultSet** | Đối tượng thực thi SQL và đọc kết quả | Nên đóng ngay khi xong |

Trong mô hình JDBC đồng bộ thông thường, các câu SQL của một transaction dùng cùng một `Connection`. Một connection có thể phục vụ **nhiều transaction liên tiếp**, nhưng không có nghĩa được phép cho nhiều luồng đồng thời dùng chung connection đó một cách tùy tiện.

**Không đồng nhất “có một Connection object” với “đang sở hữu một kết nối vật lý mới”.** Khi dùng pool, đối tượng trả về có thể là wrapper/proxy; `close()` thường kết thúc lượt mượn và đưa kết nối vật lý trở về tập sẵn sàng.

## 3. Connection pool làm việc như thế nào?

Pool duy trì tối đa một số kết nối vật lý và quản lý việc chia sẻ chúng theo thời gian. Các thành phần thường gặp:

- **Idle connections:** kết nối đang sẵn sàng cho yêu cầu tiếp theo.
- **Active/in-use connections:** kết nối đang được ứng dụng mượn.
- **Pending/waiting requests:** yêu cầu `getConnection()` phải chờ vì chưa có kết nối rảnh và pool đã chạm giới hạn hoặc chưa tạo xong kết nối.
- **Acquisition timeout:** thời gian tối đa chờ pool cấp một connection.
- **Lifecycle maintenance:** phát hiện kết nối chết, đóng kết nối quá tuổi hoặc không còn cần thiết, tạo kết nối thay thế trong giới hạn được cấu hình.

~~~mermaid
flowchart LR
    A["Java request / job"] --> B["DataSource / pool"]
    B --> C{"Có connection rảnh?"}
    C -->|Có| D["Cho mượn connection"]
    C -->|"Không; còn khả năng tạo"| E["Mở physical connection"]
    E --> D
    C -->|"Chạm giới hạn"| F["Chờ trong hàng đợi"]
    F -->|"Có connection được trả"| D
    F -->|"Hết thời gian"| G["Acquisition timeout"]
    D --> H["Thực thi SQL / transaction"]
    H --> I["close() trả lease"]
    I --> B
~~~

Sơ đồ mô tả hành vi khái quát; pool cụ thể có thể chủ động tạo kết nối trước, duy trì mức tối thiểu hoặc dùng thuật toán hàng đợi riêng.

### 3.1. Tái sử dụng giúp gì?

Không có pool, một API chạy ba truy vấn và mỗi lần mở kết nối độc lập có thể lặp ba lần quá trình kết nối–xác thực–đóng. Với pool, API có thể mượn một kết nối, chạy cả ba truy vấn trong phạm vi thích hợp, sau đó trả về để request khác sử dụng. Lần mượn tiếp theo thường không cần bắt tay mạng và xác thực lại.

Lợi ích chính:

- Giảm độ trễ mở kết nối cho các request lặp lại.
- Giảm số lần tạo/hủy session ở DBMS.
- **Giới hạn số kết nối đang mở** từ một ứng dụng tới DBMS.
- Cho phép kiểm soát thời gian chờ, sức khỏe kết nối và số lượng kết nối tối đa.
- Cung cấp tín hiệu quan sát áp lực tải như active, idle, pending và thời gian đợi.

Pool không làm truy vấn chậm trở nên nhanh về mặt thuật toán. Nếu một câu SQL thiếu chỉ mục, quét nhiều trang hoặc chờ khóa lâu, nó vẫn chiếm connection trong quá trình chạy.

### 3.2. Vì sao pool quá lớn cũng gây hại?

Mỗi kết nối vật lý có chi phí ở DBMS. Quá nhiều kết nối đồng thời có thể dẫn đến:

- Tăng dùng bộ nhớ và tài nguyên xử lý cho session/backend.
- Nhiều câu SQL đồng thời cạnh tranh CPU, I/O, buffer cache và khóa.
- Tăng chuyển ngữ cảnh và kéo dài thời gian thực thi trung bình.
- Chạm giới hạn `max_connections` hoặc ngưỡng kết nối của dịch vụ DB managed.
- Khi DB bị chậm, nhiều connection giữ query lâu hơn, khiến hàng đợi và tải hệ thống tiếp tục tăng.

**Pool là một bộ giới hạn cạnh tranh**, không chỉ là cache kết nối. Tăng `maximumPoolSize` có thể làm giảm thời gian chờ tại pool trong ngắn hạn nhưng tăng thời gian truy vấn và lỗi tại DB.

## 4. Ví dụ định lượng: chi phí mở kết nối

Giả sử một request thực hiện một câu SQL với các chi phí minh họa:

| Thành phần | Giá trị giả định |
|---|---:|
| Thiết lập kết nối vật lý, xác thực và chuẩn bị session | 25 ms |
| Thực thi SQL và nhận kết quả | 8 ms |
| Đóng kết nối vật lý | 2 ms |

Nếu mỗi request mở kết nối mới, phần chi phí không tính thời gian xử lý Java khác khoảng:

~~~text
Không pool: 25 + 8 + 2 = 35 ms
~~~

Nếu mượn được kết nối đã mở và phần thao tác mượn/trả chỉ khoảng 0,2 ms trong ví dụ:

~~~text
Pool rảnh: 0,2 + 8 = 8,2 ms
~~~

Đây là **số giả định để giải thích**, không phải benchmark hoặc lời hứa giảm từ 35 ms xuống 8,2 ms trong mọi hệ thống. Với pool, request còn có thể phải **đợi** nếu không có kết nối rảnh. Khi đó thời gian xử lý dữ liệu người dùng nhìn thấy là:

~~~text
Thời gian DB của request ≈
    chờ lấy connection
  + thời gian dùng connection (SQL, chờ khóa, transaction)
  + công việc driver / mạng liên quan
~~~

Khi pool bão hòa, **thời gian chờ lấy connection có thể vượt xa chi phí thiết lập kết nối**. Đây là lý do quan sát riêng hai thành phần quan trọng hơn chỉ nhìn tổng độ trễ endpoint.

## 5. Dùng connection pool trong Java

### 5.1. Dùng `DataSource` thay cho mở connection mới ở mỗi repository

`javax.sql.DataSource` là giao diện chuẩn để ứng dụng nhận connection. Pool là một hiện thực cụ thể của `DataSource`; Java cũng có những `DataSource` không sử dụng pool, nên bản thân việc gọi `getConnection()` chưa đủ chứng minh tái sử dụng connection.

Ví dụ repository JDBC chỉ biết về `DataSource`:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class CustomerRepository {
    private final DataSource dataSource;

    public CustomerRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean exists(long customerId) throws SQLException {
        String sql = "SELECT 1 FROM customers WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, customerId);

            try (ResultSet rows = statement.executeQuery()) {
                return rows.next();
            }
        }
    }
}
~~~

Nếu `dataSource` được cấu hình bằng pool, `Connection.close()` trong `try-with-resources` thường **trả connection về pool**, không đóng socket ngay. Kết nối vật lý vẫn được pool quản lý và có thể được dùng cho request tiếp theo.

Đoạn mã cũng đóng `ResultSet` và `PreparedStatement` theo thứ tự hợp lý. Không nên giữ `ResultSet` hoặc stream phụ thuộc connection sau khi connection đã được trả; những thao tác đọc trễ có thể gặp lỗi hoặc giữ connection lâu ngoài ý muốn.

### 5.2. Cấu hình minh họa với HikariCP

HikariCP là một thư viện pool JDBC phổ biến trong hệ sinh thái Java. Các giá trị dưới đây **chỉ minh họa cú pháp và đơn vị**, cần đo và đối chiếu với DBMS thật:

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import javax.sql.DataSource;

public final class DatabaseConfig {
    public static HikariDataSource createDataSource() {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(System.getenv("APP_DB_URL"));
        config.setUsername(System.getenv("APP_DB_USER"));
        config.setPassword(System.getenv("APP_DB_PASSWORD"));

        config.setMaximumPoolSize(16);    // Tối đa 16 physical connections.
        config.setMinimumIdle(4);         // Cố gắng duy trì 4 kết nối rảnh.
        config.setConnectionTimeout(3000); // Chờ mượn tối đa 3.000 ms.
        config.setValidationTimeout(1000); // Timeout kiểm tra kết nối.
        config.setIdleTimeout(600000);     // 10 phút cho phần idle dư.
        config.setMaxLifetime(1800000);    // Tuổi tối đa cấu hình 30 phút.

        return new HikariDataSource(config);
    }
}
~~~

Ở đây, đối tượng `HikariDataSource` phải được tạo một lần theo vòng đời ứng dụng (hoặc theo cấu hình riêng đã được quyết định), chia sẻ cho repository, rồi **đóng pool khi ứng dụng shutdown**:

~~~java
try (HikariDataSource pool = DatabaseConfig.createDataSource()) {
    CustomerRepository repository = new CustomerRepository(pool);
    boolean found = repository.exists(42L);
    System.out.println(found);
}
// pool.close() giải phóng các kết nối vật lý đang được quản lý.
~~~

Ví dụ `try-with-resources` ở trên thể hiện **vòng đời của toàn ứng dụng ở dạng thu nhỏ**. Trong web service thực, pool thường sống suốt thời gian service hoạt động và được đóng bởi hook shutdown hoặc container/framework; không tạo và đóng cả pool trong từng request.

Một số lưu ý về cấu hình:

- `maximumPoolSize` khống chế số connection vật lý mà pool quản lý, gồm đang dùng và rảnh.
- `minimumIdle` là mục tiêu duy trì số connection rảnh; một số triển khai mặc định giữ gần như một pool cố định khi không cấu hình mục tiêu này.
- `connectionTimeout` ở HikariCP là thời gian chờ **mượn connection**; nó không trực tiếp đặt giới hạn chạy SQL.
- `validationTimeout` áp dụng khi kiểm tra kết nối; việc kiểm tra và loại bỏ kết nối hỏng tùy cách pool vận hành.
- `idleTimeout` thường áp dụng cho **idle connections vượt mức tối thiểu**, theo giới hạn và chính sách của thư viện; không phải cam kết đóng chính xác ở một thời điểm.
- `maxLifetime` giúp thay thế connection theo vòng đời; connection đang được mượn thường không bị giật khỏi tay code chỉ vì đạt mốc tuổi, mà được xử lý khi trả về.
- Đơn vị thời gian trong các setter trên là **mili-giây**. Tên cấu hình và giới hạn có thể khác khi dùng property của Spring Boot hoặc phiên bản thư viện khác.

Trong hệ thống thực, thông tin đăng nhập nên lấy từ kho bí mật/cơ chế quản lý cấu hình phù hợp; hạn chế xuất giá trị mật khẩu ra log, và có quy trình làm mới credential khi rotate.

### 5.3. Ranh giới transaction với pooled connection

Một nghiệp vụ có nhiều bước cần tính nguyên tử phải dùng **cùng connection trong một transaction**. Ví dụ chuyển đơn sang trạng thái thanh toán:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderPaymentService {
    private final DataSource dataSource;

    public OrderPaymentService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void markPaid(long orderId) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            boolean oldAutoCommit = connection.getAutoCommit();
            try {
                connection.setAutoCommit(false);

                try (PreparedStatement statement = connection.prepareStatement(
                        "UPDATE orders SET status = 'PAID' "
                      + "WHERE id = ? AND status = 'PENDING'")) {
                    statement.setLong(1, orderId);
                    if (statement.executeUpdate() != 1) {
                        throw new IllegalStateException(
                            "Order missing or not pending");
                    }
                }

                // Các SQL bắt buộc thuộc cùng nghiệp vụ sẽ chạy tại đây.
                connection.commit();
            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            } finally {
                connection.setAutoCommit(oldAutoCommit);
            }
        }
    }
}
~~~

Đây là ví dụ về **vòng đời connection và transaction**; hệ thống thanh toán thực cần thêm kiểm toán, xử lý idempotency, trạng thái thanh toán từ bên ngoài và logic nghiệp vụ phù hợp.

Cần nhớ:

- `getConnection()` bắt đầu thời gian mượn; `close()` kết thúc lượt mượn.
- `commit()` hoặc `rollback()` kết thúc transaction nhưng **không tự trả connection về pool** nếu đối tượng JDBC vẫn đang được giữ.
- Đừng gọi network API chậm, chờ người dùng hoặc xử lý CPU nặng không cần thiết trong khi connection/transaction vẫn đang được giữ.
- Các thay đổi session như `autoCommit`, isolation, `readOnly`, schema hoặc biến riêng của DB phải được khôi phục theo chính sách pool/transaction manager. Không giả định mọi thay đổi session tùy ý đều được pool tự reset.
- Khi cleanup thất bại, đừng che mất lỗi gốc; ví dụ giản lược ở trên có thể cần lớp quản lý transaction chuyên dụng để xử lý mọi lỗi reset connection.
- Với Spring/JPA, một transaction manager có thể mượn và giữ connection theo phạm vi `@Transactional`; mã repository không nên tự mở transaction trái với cách framework đang quản lý.

## 6. Pool sizing: đặt tối đa bao nhiêu connection?

Không có công thức cố định kiểu “pool bằng số CPU nhân hai” đúng với mọi hệ thống. Một phương pháp bắt đầu là đo **thông lượng yêu cầu cần DB** và **thời gian trung bình một yêu cầu giữ connection**.

Theo nguyên lý Little's Law trong trạng thái ổn định:

\[
L \approx \lambda \times W
\]

Trong đó:

- \(L\): số lượt mượn connection đang hoạt động trung bình.
- \(\lambda\): số lượt mượn connection mỗi giây (không nhất thiết bằng số HTTP request nếu một request mượn nhiều lần).
- \(W\): thời gian giữ connection trung bình tính bằng giây, từ lúc mượn thành công đến lúc trả.

Ví dụ một service ở giờ cao điểm có khoảng **250 lượt mượn/giây**, và mỗi lượt giữ connection trung bình **40 ms**:

\[
L \approx 250 \times 0{,}04 = 10
\]

Kết quả 10 là **mức đồng thời trung bình ước tính**, chưa phải cấu hình `maximumPoolSize` tối ưu. Đỉnh tải, phân bố đuôi dài, transaction chờ khóa và sự thay đổi của DB có thể khiến mức cần thiết lớn hơn. Có thể thử một khoảng giá trị phù hợp trên môi trường đo tải, ví dụ **12–20** ở tình huống minh họa, rồi so sánh thời gian chờ pool, throughput và độ trễ SQL. Đây không phải khuyến nghị mặc định cho mọi ứng dụng.

### 6.1. Ngân sách kết nối là ngân sách chung của toàn DB

Giả sử:

~~~text
Giới hạn DB cho các phiên ứng dụng (sau khi trừ phần dự phòng): 90
Service A: 3 replica × maximumPoolSize 20 = tối đa 60
Service B: 2 replica × maximumPoolSize 15 = tối đa 30
Tổng tối đa lý thuyết = 90
~~~

Ở mức này, ngân sách cho các pool đã đầy và **không còn chỗ** cho công cụ vận hành, migration hoặc tình huống mới nếu phần dự phòng chưa tính đúng. Khi autoscaling tăng service A lên 5 replica, tổng lý thuyết nhảy thành **130**, vượt ngân sách 90 ngay cả khi mỗi pool cấu hình “chỉ 20”.

Hãy tính đủ:

- Tất cả instance/replica ở mọi service và worker.
- Pool riêng cho đọc/ghi, tenant, shard hoặc database.
- Các job migration, quản trị và giám sát.
- Kết nối của proxy và lượng kết nối trực tiếp đi vòng qua proxy.
- Phần dự phòng cần thiết để vận hành và khôi phục khi có sự cố.

**Tổng giới hạn kết nối của các pool có thể lớn hơn lượng kết nối thực tế đang dùng**, nhưng không nên dựa vào giả định rằng mọi pool sẽ không bao giờ đầy. Cần lập ngân sách theo tình huống tải đỉnh và khi autoscaling.

### 6.2. Đo chỗ nghẽn trước khi tăng pool

| Quan sát | Khả năng xảy ra | Hướng điều tra |
|---|---|---|
| Pool `active` gần tối đa, `pending` tăng | Pool đang bão hòa | Đo thời gian giữ connection, SQL chậm, transaction dài |
| Pool `active` cao, DB CPU/I/O cũng đầy | DB có thể là nút thắt | Tối ưu query/index, giảm truy vấn, cân nhắc giới hạn đồng thời |
| Pool `active` cao nhưng DB ít làm việc | Connection bị giữ khi Java xử lý/chờ mạng | Tìm transaction dài hoặc rò rỉ connection |
| Pool còn nhiều `idle` nhưng API chậm | Điểm nghẽn có thể ở query, mạng hoặc logic khác | Theo dõi SQL và request thay vì tăng pool |
| Nhiều service cùng mở pool sau restart | Connection storm và chi phí xác thực đồng loạt | Khởi động có điều tiết, giới hạn tổng connection, retry có backoff |
| DB báo quá nhiều connection | Ngân sách toàn cụm chưa phù hợp | Tính lại replica, pool, job nền và dự phòng |

Nên xác định bottleneck thật trước khi chỉnh `maximumPoolSize`. Một pool lớn hơn có thể **xếp thêm công việc vào DB** và kéo dài toàn bộ hệ thống.

## 7. Timeout và lỗi thường gặp

### 7.1. Timeout lấy connection khác timeout kết nối mạng

Một đoạn mã có thể thất bại ngay tại `dataSource.getConnection()` vì nhiều nguyên nhân:

- Không có connection rảnh và pool đã đạt mức tối đa: **acquisition timeout**.
- Pool muốn tạo connection mới nhưng DB chậm, host không truy cập được hoặc TLS/xác thực lỗi: **connection establishment failure/timeout**.
- Một connection cũ đã chết, không còn khả dụng, pool cần kiểm tra và thay thế: có thể phát sinh chờ hoặc lỗi tùy chính sách.
- DBMS từ chối kết nối mới do quá giới hạn phiên hoặc chính sách truy cập: lỗi server/driver, có thể bị bọc thành lỗi cấp connection.

Không suy luận tất cả lỗi tại `getConnection()` đều do pool quá nhỏ. Cần ghi mã lỗi, chuỗi nguyên nhân, số liệu pool và tình trạng DB tại thời điểm xảy ra.

### 7.2. Timeout chạy SQL và timeout chờ khóa

Khi đã mượn được connection:

- `Statement.setQueryTimeout(...)` có thể yêu cầu giới hạn thời gian chạy câu SQL tùy driver.
- DBMS có thể cung cấp `statement_timeout` hoặc khái niệm tương ứng.
- Chờ một lock khi giao dịch khác đang ghi có thể có giới hạn riêng, chẳng hạn `lock_timeout` của PostgreSQL.
- Transaction manager có thể đặt giới hạn cho toàn transaction.
- Network/socket timeout có thể phản ánh mất liên lạc chứ không trực tiếp nói SQL chậm.

Nếu một transaction chờ khóa 20 giây, connection bị giữ suốt thời gian đó, đồng thời góp phần làm tăng số người đợi trong pool. Vì vậy khi có `getConnection()` timeout ở endpoint khác, nguyên nhân sâu có thể nằm ở **giao dịch dài hoặc chờ khóa** của các endpoint đang giữ connection.

### 7.3. Mất kết nối và trạng thái COMMIT không chắc chắn

Nếu kết nối đứt trong lúc chạy giao dịch, cần rollback/đóng tài nguyên theo trạng thái driver cho phép. Nếu mạng đứt **sau khi client gửi COMMIT nhưng trước khi nhận được kết quả**, ứng dụng có thể không biết server đã commit chưa.

Pool không giải quyết được bài toán **commit mơ hồ**. Với nghiệp vụ quan trọng, cần mã thao tác duy nhất, ràng buộc dữ liệu, idempotency và quy trình đối soát trước khi retry. Đừng dùng một vòng retry kết nối để tự động gửi lại giao dịch thanh toán mà không xác minh kết quả.

## 8. Quản lý vòng đời kết nối và sức khỏe pool

### 8.1. Idle, maximum lifetime và kết nối bị đóng từ phía server

Một connection không được sử dụng lâu có thể bị DBMS, firewall, proxy hoặc thiết bị mạng đóng. Một connection được dùng nhiều lần cũng có thể phải thay khi credential, topology hoặc chính sách server thay đổi.

Pool thường hỗ trợ:

- **Idle eviction:** giảm số connection rảnh vượt mục tiêu.
- **Maximum lifetime:** luân chuyển connection sau một độ tuổi cấu hình.
- **Health check/validation:** tránh đưa connection đã chết cho ứng dụng.
- **Keepalive khi idle:** trong các trường hợp hỗ trợ, kiểm tra hoặc duy trì kết nối idle để giảm rủi ro bị đóng im lặng.
- **Retirement:** đánh dấu connection không dùng lại sau khi trả về nếu đã quá tuổi/hỏng.

Không nên đặt `maxLifetime` lớn hơn mọi giới hạn tuổi kết nối của hạ tầng mà không hiểu cơ chế: connection có thể bị server ngắt trước khi pool dự định thay. Nhưng **đặt thời gian quá ngắn** cũng gây quá nhiều lần tạo kết nối và làm mất lợi ích tái sử dụng.

Các mốc thời gian cần đối chiếu gồm timeout của database, proxy/load balancer, thiết lập TLS và cách triển khai pool. Đảm bảo vẫn có giám sát để nhận ra lỗi kết nối bất thường sau khi thay đổi cấu hình.

### 8.2. Connection leak và thời gian mượn quá dài

**Connection leak** xảy ra khi code mượn connection rồi không trả, ví dụ nhánh exception không đóng `Connection`. Khi đủ lượt bị leak, pool cạn kết nối và request mới chỉ còn chờ rồi timeout.

~~~java
// Sai: có thể không trả connection nếu executeQuery() ném lỗi.
Connection connection = dataSource.getConnection();
PreparedStatement statement =
    connection.prepareStatement("SELECT * FROM customers");
ResultSet rows = statement.executeQuery();
// Không có finally/try-with-resources để đóng.
~~~

Biện pháp cơ bản là dùng `try-with-resources` hoặc transaction manager đáng tin cậy. Nhưng **không phải mọi connection được mượn lâu đều là leak**: một báo cáo dài có thể hợp lệ nhưng vẫn gây áp lực pool. Phải phân biệt bằng trace và mục đích nghiệp vụ.

Một số pool hỗ trợ phát hiện nghi ngờ leak bằng cách ghi stack trace khi lượt mượn kéo dài quá ngưỡng. Tín hiệu đó giúp điều tra, nhưng tự nó không chứng minh có leak thật và không thay thế việc đóng tài nguyên.

### 8.3. Trạng thái session bị rò qua lần mượn

Tái sử dụng connection có một rủi ro: trạng thái session của request trước có thể ảnh hưởng request sau nếu không được reset đúng cách.

Các loại trạng thái cần xem xét:

- `autoCommit`, isolation level, chế độ `readOnly`, catalog/schema.
- Session variables, múi giờ, locale hoặc tenant context.
- Bảng tạm, lock theo phiên và các prepared statement gắn với session.
- Transaction còn mở vì code bỏ quên rollback.
- Cấu hình bảo mật ở mức session, ví dụ biến dùng cho row-level security trong DBMS hỗ trợ.

Pool JDBC có thể theo dõi/reset một số thuộc tính JDBC thông dụng, nhưng **không tự bảo đảm xóa mọi thay đổi riêng của từng DBMS**, đặc biệt các câu `SET` gửi trực tiếp bằng SQL. Ứng dụng phải tuân thủ hợp đồng của pool và transaction manager, chọn cách đặt session state có phạm vi transaction khi thích hợp.

Trong hệ thống multi-tenant, session context bị rò có thể gây lỗi **cô lập dữ liệu giữa tenant**, không chỉ giảm hiệu năng. Kiểm soát quyền truy cập vẫn phải nằm trong thiết kế bảo mật, không thể chỉ tin rằng pool sẽ cấp “kết nối mới” mỗi lần.

## 9. Pool, transaction và framework Java

### 9.1. Spring và JPA

Trong Spring/JPA, application thường không gọi trực tiếp `Connection.close()` ở mọi repository. Transaction manager mượn connection từ pool, sử dụng trong phạm vi transaction và trả lại theo vòng đời mà framework quản lý.

Ví dụ:

~~~java
@Service
public class InvoiceService {
    private final InvoiceRepository repository;

    public InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void approveInvoice(long invoiceId) {
        Invoice invoice = repository.findById(invoiceId)
            .orElseThrow();
        invoice.approve();
        // Các SQL phát sinh trong transaction do framework quản lý.
    }
}
~~~

Cần hiểu cấu hình transaction manager và ORM thực tế. `@Transactional` có thể khiến connection bị giữ trong lúc Java thực hiện các công việc không cần DB; thời điểm connection được mượn/trả còn phụ thuộc chế độ acquisition/release của framework.

Lỗi phổ biến: đưa cả thao tác gọi HTTP, chờ hàng đợi, đọc file lớn hoặc gửi email vào một method `@Transactional`. Điều đó có thể kéo dài transaction và thời gian giữ connection. Nên tổ chức phạm vi transaction bao quanh những thao tác DB cần nhất quán.

### 9.2. Bất đồng bộ và luồng xử lý

Connection JDBC thông thường không phải đối tượng nên được truyền tùy tiện giữa các thread rồi sử dụng song song. Một transaction trên thread này cũng không tự lan sang thread khác chỉ vì các lời gọi đều dùng chung `DataSource`.

Với `CompletableFuture`, `@Async` hoặc worker nền, cần làm rõ transaction và connection ở từng tác vụ. Một nhóm tác vụ lớn có thể đồng thời yêu cầu mượn connection và làm đầy pool dù HTTP traffic không tăng. Giới hạn concurrency ở tầng ứng dụng và sức tải của DB phải được thiết kế cùng nhau.

Đối với ứng dụng reactive, connection pool của driver reactive có thể khác pool JDBC. Không áp dụng trực tiếp giả định về block/thread hoặc API `DataSource` của JDBC cho giao thức reactive.

## 10. Proxy và connection pooling nhiều tầng

Khi có nhiều instance ứng dụng kết nối tới cùng DB, có thể xuất hiện thêm lớp proxy hoặc pool ở gần server:

~~~text
Java replicas
    |
    +-- JVM A: JDBC pool (tối đa 20)
    +-- JVM B: JDBC pool (tối đa 20)
    +-- JVM C: JDBC pool (tối đa 20)
    |
Database connection proxy (nếu triển khai)
    |
Database server và các session backend
~~~

Ví dụ trong hệ sinh thái PostgreSQL, **PgBouncer** là một connection pooler/proxy thường dùng. Các chế độ pool có khác biệt lớn:

- **Session pooling:** một backend connection thường gắn với client trong suốt session; nhiều tính năng session có thể hoạt động tự nhiên hơn nhưng mức chia sẻ backend giữa các client bị hạn chế.
- **Transaction pooling:** backend connection được mượn theo transaction rồi trả sau khi transaction kết thúc; có thể phục vụ nhiều client connection bằng ít backend hơn ở những workload phù hợp.
- **Statement pooling:** giới hạn phạm vi tương ứng; có các hạn chế về giao dịch và trạng thái phiên, cần xem tài liệu chính xác của công cụ.

Với transaction pooling, **một client connection có thể không luôn được gắn với cùng backend session sau mỗi transaction**. Điều này có thể ảnh hưởng bảng tạm, biến session, advisory locks cấp phiên, prepared statements và những tính năng phụ thuộc session. Mức hỗ trợ prepared statements còn phụ thuộc phiên bản/cấu hình của proxy và driver, không nên khẳng định luôn bị cấm hoặc luôn được hỗ trợ.

Có proxy **không** đồng nghĩa bỏ hết pool phía Java. Pool JDBC vẫn có vai trò giới hạn concurrency của ứng dụng và giảm chi phí tạo client connection. Nhưng phải thiết kế ngân sách và timeout đồng thời cho cả hai lớp, tránh các hàng đợi khó quan sát.

## 11. Quan sát và tinh chỉnh trong vận hành

Một hệ thống có pool tốt cần có chỉ số để đánh giá tình trạng trong các khung thời gian có tải:

| Chỉ số | Mục đích |
|---|---|
| Connections active / idle / total | Biết pool đang dùng bao nhiêu và có dư hay cạn |
| Threads/requests pending acquisition | Biết số yêu cầu đang đợi pool |
| Acquisition time p50/p95/p99 | Đo độ trễ lấy connection, khác thời gian chạy SQL |
| Connection usage/hold time | Đo thời gian mượn connection; phát hiện transaction dài |
| Connection creation time / failures | Phát hiện chậm xác thực, mạng, giới hạn DB và kết nối lỗi |
| Leak suspicion logs | Truy tìm đường code giữ connection lâu |
| DB active sessions, CPU, I/O, memory | Đánh giá DB có tiếp nhận thêm concurrency được không |
| Query duration, lock wait, deadlock | Phân biệt chậm do SQL hay chờ tranh chấp |
| Application p95/p99 và throughput | Đánh giá tác động lên trải nghiệm người dùng |

Một luồng phân tích thường gặp:

~~~mermaid
flowchart TD
    A["API chậm hoặc getConnection timeout"] --> B{"Pending acquisition tăng?"}
    B -->|Không| C["Xem query, mạng, logic ứng dụng"]
    B -->|Có| D{"Active connections gần tối đa?"}
    D -->|Không| E["Xem tạo/validate connection, DB/network lỗi"]
    D -->|Có| F["Đo hold time, SQL, transaction, lock wait"]
    F --> G{"DB còn đủ năng lực?"}
    G -->|Không| H["Tối ưu query, giới hạn concurrency, giảm tải"]
    G -->|Có| I["Thử sizing pool bằng đo tải"]
~~~

Đồ thị chỉ mô tả trình tự đặt câu hỏi. Chẳng hạn số pending tăng cũng có thể do DB từ chối connection mới, và nhiều bottleneck có thể cùng xảy ra.

### 11.1. Thử nghiệm tải nên đo những gì?

Khi thay `maximumPoolSize` từ 10 sang 20, hãy đo trong điều kiện có thể so sánh:

1. Thông lượng thực tế và p95/p99 độ trễ API.
2. Acquisition time và pending requests tại pool.
3. Độ trễ SQL, khóa, CPU/I/O và số phiên trên DB.
4. Số request thất bại, connection creation error và transaction rollback.
5. Tác động lên các service **khác** sử dụng chung DB.

Nếu pending giảm nhưng SQL p99 tăng mạnh và DB CPU chạm trần, pool lớn hơn có thể làm trải nghiệm xấu đi. Nếu DB còn dư tài nguyên, query nhanh và pending chiếm phần lớn độ trễ, tăng pool có thể hữu ích. Quyết định dựa trên dữ liệu tải thực tế.

### 11.2. Kiểm tra lại khi scale hoặc failover

Pool sizing cần được đánh giá lại khi:

- Tăng số replica hoặc thêm background worker.
- Đổi loại database instance, thêm read replica hoặc proxy.
- Độ trễ mạng thay đổi do chuyển vùng.
- Truy vấn trở nên nặng hơn vì dữ liệu tăng hoặc query plan đổi.
- Database failover hoặc rotate credentials gây nhiều connection bị mất đồng thời.

Khi nhiều instance tái kết nối ngay sau failover, cần giới hạn tốc độ retry/backoff và tránh bão tạo kết nối. Pool chỉ có thể phục hồi các kết nối dựa trên khả năng DB và mạng thực tế; không tự bảo đảm nghiệp vụ được chạy lại an toàn.

## 12. Các sai lầm điển hình

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Tạo `HikariDataSource` mới cho mỗi request | Lặp lại chi phí mở connection; mất ý nghĩa pool | Tạo pool có vòng đời của ứng dụng |
| Giữ `Connection` trong field singleton của repository | Nhiều request dùng chung một connection/transaction sai cách | Mượn theo đơn vị công việc rồi trả |
| Quên `close()` trên nhánh exception | Leak và pool exhaustion | Dùng `try-with-resources`/transaction manager |
| `commit()` rồi quên trả connection | Pool vẫn coi connection đang được mượn | Đóng lease sau khi xong, dù đã commit |
| Đặt pool bằng giới hạn DB cho từng replica | Tổng pool vượt ngân sách DB khi scale | Tính tổng replica và phần dự phòng |
| Tăng pool mỗi khi API chậm | Có thể khiến DB càng quá tải | Đo acquisition, hold time, query và DB saturation |
| Dùng transaction để bao cả gọi HTTP | Giữ connection/khóa quá lâu | Thu gọn ranh giới transaction |
| Tin rằng pool reset mọi biến session | Rò trạng thái người dùng/tenant | Dùng transaction-scoped setting và reset đúng hợp đồng |
| Retry mọi lỗi kết nối bằng cách gửi lại nghiệp vụ | Có thể lặp thanh toán khi COMMIT mơ hồ | Dùng operation ID, idempotency và đối soát |

## 13. Bài tập vận dụng

### Bài 1: Ước lượng số connection hoạt động

Một dịch vụ có 300 lượt mượn connection/giây. Mỗi lượt giữ connection trung bình 30 ms. Hãy ước tính số lease đồng thời trung bình.

**Gợi ý:** `L ≈ λW = 300 × 0,03 = 9`. Đây là **trung bình**, không phải giới hạn pool cuối cùng; cần đo phân bố đỉnh và DB capacity.

### Bài 2: Scale replica

DB đã dành 70 connection cho ứng dụng. Service có 4 replica, mỗi replica đặt `maximumPoolSize = 20`. Có rủi ro gì?

**Gợi ý:** Trần lý thuyết là 80, vượt ngân sách 70. Dù không phải replica nào cũng dùng hết, khi spike hoặc restart đồng loạt có thể chạm giới hạn. Cần phân bổ theo toàn hệ thống và còn phần dự phòng.

### Bài 3: Pool timeout nhưng DB CPU thấp

Monitoring cho thấy `active = max`, `pending` tăng, DB CPU chỉ 20%. Một số transaction Java giữ connection hơn 30 giây để gọi HTTP bên ngoài. Có nên tăng pool ngay?

**Gợi ý:** Điều tra và rút ngắn thời gian giữ connection trước. Vấn đề có thể ở transaction dài, không phải DB không đủ khả năng thực thi SQL.

### Bài 4: `commit()` có trả connection không?

Repository mở connection từ pool, thực hiện transaction, gọi `commit()` rồi giữ đối tượng connection trong một field để dùng tiếp. `active connections` có giảm ngay không?

**Gợi ý:** Không nhất thiết. `commit()` kết thúc transaction; việc trả về pool thường xảy ra khi code gọi `close()` cho lease (hoặc framework giải phóng connection).

### Bài 5: Đổi isolation rồi trả pool

Một request đặt `Connection.TRANSACTION_SERIALIZABLE`, chạy xong và trả connection. Request sau dùng lại cùng physical connection. Rủi ro gì?

**Gợi ý:** Nếu thay đổi session không được khôi phục đúng, request sau có thể chạy isolation khác dự kiến, gây blocking hoặc thay đổi ngữ nghĩa. Cần transaction manager hoặc quy tắc reset thuộc tính kết nối nhất quán.

### Bài 6: PgBouncer transaction pooling

Một ứng dụng dùng prepared statements hoặc biến session tồn tại qua nhiều transaction. Chuyển proxy sang transaction pooling có cần kiểm tra tương thích không?

**Gợi ý:** Có. Backend session có thể thay đổi sau mỗi transaction. Phải kiểm tra tính năng phụ thuộc phiên, phiên bản proxy/driver và cấu hình thực tế.

### Bài 7: Mất kết nối khi COMMIT

Ứng dụng gửi COMMIT cho thao tác tạo đơn, nhưng mạng đứt trước khi nhận phản hồi. Có an toàn nếu mở connection mới rồi INSERT lại ngay?

**Gợi ý:** Không. Đơn cũ có thể đã commit. Kiểm tra/đối soát bằng khóa nghiệp vụ hoặc operation ID duy nhất, dùng idempotency để tránh ghi trùng.

## 14. Ghi nhớ

- **Tạo kết nối vật lý tốn chi phí** mạng, giao thức, xác thực và tài nguyên session; pool tái sử dụng kết nối để tránh lặp lại những chi phí này.
- **`Connection.close()` thường là trả lease về pool** khi ứng dụng dùng một pooled `DataSource`. `commit()` không tự đồng nghĩa trả kết nối.
- **Pool quản lý cạnh tranh**: quá nhỏ khiến đợi mượn, quá lớn có thể đẩy DB vào quá tải; phải tính tổng các pool trên mọi replica.
- **Thời gian giữ connection** quan trọng như số lượng connection. SQL chậm, chờ khóa, gọi HTTP trong transaction và connection leak đều có thể làm cạn pool.
- **Timeout xảy ra ở nhiều lớp**; phải phân biệt acquisition, network, query, lock và transaction trước khi retry hoặc thay cấu hình.
- **Tái sử dụng session cần kỷ luật**: đóng tài nguyên, rollback khi lỗi, reset trạng thái kết nối, bảo vệ tenant context và thiết kế idempotency khi COMMIT mơ hồ.
- **Tối ưu bằng phép đo**, gồm acquisition time, connection hold time, DB saturation, truy vấn thực tế và tải đỉnh sau khi scale.

Connection pool là một thành phần quản lý tài nguyên thiết yếu trong lớp persistence của Java. Nó giúp tiết kiệm chi phí mở kết nối và giữ tải truy cập DB trong giới hạn có thể kiểm soát. Hiệu quả bền vững đến từ việc thiết kế đúng ranh giới transaction, dùng `DataSource` an toàn, phân bổ ngân sách connection theo toàn hệ thống và theo dõi thực tế khi tải thay đổi.
