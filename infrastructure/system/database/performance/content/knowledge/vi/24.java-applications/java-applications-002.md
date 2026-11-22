# HikariCP: số kết nối, thời gian chờ và chỉ số sử dụng

Ứng dụng Java thường không mở một kết nối cơ sở dữ liệu mới cho mỗi câu SQL rồi đóng kết nối vật lý sau khi dùng. Việc thiết lập kết nối có thể tốn thời gian và tài nguyên ở cả ứng dụng lẫn database. **Connection pool** giữ một nhóm kết nối đã được tạo, cho phép các luồng mượn kết nối trong thời gian cần truy cập dữ liệu rồi trả lại pool để yêu cầu khác sử dụng. HikariCP là một connection pool phổ biến trong hệ sinh thái Java, được thiết kế để quản lý vòng đời và cấp phát kết nối với overhead thấp.

Pool có thể trở thành điểm nghẽn nếu kích thước quá nhỏ, timeout không phù hợp hoặc ứng dụng giữ kết nối quá lâu. Ngược lại, pool quá lớn có thể đẩy quá nhiều session xuống database, làm tăng context switching, bộ nhớ, lock contention và độ trễ truy vấn. Vì vậy, cần chọn số kết nối theo năng lực database và mức đồng thời thực tế; cấu hình timeout theo ngân sách thời gian của request; đồng thời theo dõi active, idle, pending, acquire time và usage time.

Trong module **DATABASE_PERFORMANCE**, nội dung này kết nối hiệu năng database với cách ứng dụng Java sử dụng tài nguyên kết nối. Bạn sẽ học vòng đời connection trong HikariCP, cách chọn `maximumPoolSize` và `minimumIdle`, phân biệt các timeout, đọc metric để nhận diện pool saturation hoặc connection leak, và kiểm chứng cấu hình dưới tải đại diện. Mục tiêu là duy trì số kết nối vừa đủ, giới hạn thời gian chờ và giúp database xử lý tải ổn định.

## 1. Connection pool giải quyết vấn đề gì?

Một kết nối JDBC vật lý có thể cần DNS, TCP handshake, TLS, xác thực, cấp phát session ở database và khởi tạo trạng thái session. Nếu ứng dụng tạo kết nối cho mọi câu lệnh, những chi phí này lặp lại và có thể làm tăng tải đột biến lên database.

HikariCP giữ một tập kết nối đã mở. Khi một request cần database, ứng dụng gọi `DataSource.getConnection()`. Pool trả một kết nối rảnh nếu có; nếu tất cả kết nối đang được mượn và pool chưa đạt giới hạn, HikariCP có thể tạo kết nối mới; nếu đã đạt giới hạn, request phải chờ đến khi có kết nối được trả lại hoặc hết `connectionTimeout`.

Khi ứng dụng gọi `Connection.close()`, với connection do HikariCP cấp, thao tác này thường trả proxy connection về pool để tái sử dụng. Nó không có nghĩa là đóng ngay kết nối TCP vật lý. Pool vẫn có thể đóng kết nối vật lý khi hết vòng đời, bị lỗi, không còn cần thiết hoặc pool shutdown.

### Vòng đời đơn giản

```text
Request Java
    |
    v
DataSource.getConnection()
    |
    +---- Có connection idle? ---- Có ----> Mượn connection
    |                                      |
    +---- Chưa đủ maximumPoolSize?          v
    |             |                     Thực thi SQL
    |             Có                       |
    |             |                         v
    |        Tạo connection             close() / trả pool
    |                                       |
    +---- Đã đầy ---------------------------+
                  |
                  v
           Chờ đến connectionTimeout
                  |
          Có connection / timeout
```

Pool điều tiết số kết nối đồng thời từ một instance ứng dụng đến database. Nó không tự giới hạn tổng số kết nối từ tất cả pod, máy chủ, batch job, công cụ quản trị hoặc dịch vụ khác. Tổng tải kết nối phải được tính ở cấp toàn hệ thống.

## 2. Các trạng thái và chỉ số cơ bản của HikariCP

HikariCP thường cung cấp các số đo về số kết nối và thời gian sử dụng. Tên metric cụ thể phụ thuộc phiên bản, integration và registry, nhưng các khái niệm cốt lõi gồm:

| Metric | Ý nghĩa | Cách đọc |
|---|---|---|
| Active connections | Số kết nối hiện đang được ứng dụng mượn | Tăng cao kéo dài có thể cho thấy truy vấn lâu hoặc pool thiếu dung lượng |
| Idle connections | Số kết nối sẵn sàng cho request | Bằng 0 trong giờ cao điểm có thể bình thường nếu không có pending; cần xem cùng các metric khác |
| Total connections | Tổng kết nối vật lý đang nằm trong pool | Thường nằm giữa `minimumIdle` và `maximumPoolSize` theo cấu hình và tải |
| Pending threads | Số luồng đang chờ mượn connection | Pending tăng kéo dài là dấu hiệu có hàng đợi ở pool |
| Connection acquire time | Thời gian từ lúc yêu cầu đến khi nhận được connection | Tăng cao làm request chậm trước cả khi chạy SQL |
| Connection usage time | Thời gian connection được giữ từ lúc mượn đến lúc trả | Tăng cao có thể do query chậm, transaction dài hoặc code giữ connection lâu |
| Connection timeout count | Số lần không lấy được connection trước deadline | Cần điều tra pool, database và vòng đời connection |
| Connection creation/close | Số connection được tạo và đóng | Dao động lớn có thể gợi ý cấu hình min/max, lỗi kết nối hoặc vòng đời không phù hợp |

### Active, idle và pending phải được đọc cùng nhau

Một ảnh chụp tại một thời điểm không đủ kết luận pool có vấn đề. Ví dụ, `active = maximumPoolSize` trong vài giây có thể chỉ phản ánh đợt tải ngắn. Nếu `active` chạm trần liên tục, `idle = 0`, `pending` tăng và acquire latency tăng, pool đang tạo hàng đợi.

Nếu `active` thấp, `idle` cao và pending luôn bằng 0, pool có thể đang lớn hơn nhu cầu. Tuy nhiên, cần xem chu kỳ cao điểm, batch job và thời gian mở rộng tải trước khi giảm kích thước.

### Acquire time khác usage time

- **Acquire time** đo thời gian chờ pool cấp kết nối. Đây là phần thời gian request có thể bị chặn trước khi bắt đầu truy vấn.
- **Usage time** đo khoảng thời gian ứng dụng giữ kết nối. Nó bao gồm thời gian thực thi SQL, đọc kết quả, xử lý trong transaction và mọi công việc khác diễn ra trước khi trả connection.

Nếu acquire time cao nhưng usage time ngắn, cần xem pool size, số request đồng thời và tốc độ tạo kết nối. Nếu usage time cao, cần tìm truy vấn chậm, transaction dài, result set lớn hoặc code giữ connection trong lúc chờ việc khác.

## 3. Chọn maximumPoolSize

`maximumPoolSize` là giới hạn số kết nối vật lý mà một HikariDataSource có thể duy trì. Khi số kết nối đang được mượn đạt giới hạn và không còn idle connection, các luồng mới phải chờ.

Không nên đặt pool bằng số request đồng thời hoặc số thread của web server một cách máy móc. Database có giới hạn về CPU, I/O, memory, session, lock và khả năng xử lý truy vấn song song. Một số lượng kết nối quá lớn có thể làm database phải chuyển đổi giữa nhiều session, tăng tranh chấp và giảm throughput.

### Tính ngân sách ở cấp toàn hệ thống

Giả sử một dịch vụ có 6 replica, mỗi replica có một pool tối đa 20 connection. Riêng dịch vụ đó có thể mở đến 120 kết nối. Nếu còn worker nền, dịch vụ báo cáo, migration và công cụ quản trị, tổng số session có thể cao hơn đáng kể.

Một cách lập ngân sách là:

\[
C_{application} = N_{replicas} \times P_{max}
\]

Sau đó cộng các nguồn kết nối khác và so sánh với giới hạn database:

\[
C_{total} = C_{application} + C_{jobs} + C_{admin} + C_{other}
\]

Phải chừa dự phòng cho failover, rolling deployment, autoscaling và kết nối quản trị. Khi rollout, phiên bản cũ và mới có thể cùng tồn tại trong thời gian ngắn, làm số pool hoạt động tăng tạm thời.

### Pool nhỏ có thể nhanh hơn pool lớn

Một pool nhỏ giới hạn mức đồng thời đi vào database. Các request dư được xếp hàng ở ứng dụng thay vì tạo thêm session cạnh tranh tài nguyên bên trong database. Nếu database đã bão hòa, tăng pool có thể làm thời gian chờ khóa, CPU context switch và p99 latency tăng mà không tăng số transaction commit.

Mục tiêu không phải làm `active` luôn bằng `maximumPoolSize`. Mục tiêu là đạt throughput cần thiết với thời gian chờ và độ trễ chấp nhận được, trong khi database vẫn còn khả năng phục vụ các workload khác.

### Heuristic chỉ là điểm bắt đầu

Một số hướng dẫn HikariCP từng nêu công thức kinh nghiệm dựa trên số core CPU và thiết bị lưu trữ hiệu dụng để bắt đầu thử nghiệm. Đây không phải công thức phổ quát cho mọi workload, cloud database, SSD hay hệ thống có nhiều truy vấn chờ I/O. Hãy bắt đầu từ ngân sách session của database và kiểm thử concurrency thực tế; không đưa một con số kinh nghiệm vào production mà không đo.

### Tránh một pool cho mỗi request hoặc tenant

Thông thường, ứng dụng tạo một hoặc một số ít `DataSource` được quản lý trong vòng đời ứng dụng. Không tạo HikariDataSource mới cho từng request. Nếu mỗi tenant hoặc module tạo pool riêng, tổng connection có thể tăng theo số tenant và khó kiểm soát. Chỉ dùng nhiều pool khi có lý do rõ như tách workload đọc/ghi, database khác nhau hoặc cô lập tải; phải tính tổng giới hạn của tất cả pool.

## 4. minimumIdle và hành vi co giãn pool

`minimumIdle` là số kết nối idle tối thiểu mà pool cố gắng duy trì. Nếu không cấu hình riêng, HikariCP thường dùng hành vi pool cố định với minimum idle tương đương maximum pool size theo mặc định của cấu hình. Khi đặt `minimumIdle` thấp hơn `maximumPoolSize`, pool có thể co giãn theo tải và đóng kết nối idle vượt mức sau khoảng thời gian phù hợp.

### Pool cố định

Pool cố định giữ số kết nối gần với maximum pool size. Ưu điểm là khi tải tăng, kết nối đã sẵn sàng; ứng dụng ít phải chịu chi phí tạo connection ngay lúc peak. Nhược điểm là giữ nhiều session ngay cả khi tải thấp.

### Pool co giãn

Pool co giãn giữ một số connection tối thiểu và mở rộng khi cần, sau đó có thể thu hẹp khi idle. Cách này giảm số session lúc nhàn rỗi nhưng khi tải tăng đột ngột, việc tạo connection mới có thể làm tăng acquire time. Nếu database hoặc network khởi tạo connection chậm, cần kiểm thử warm-up và peak burst.

`idleTimeout` chỉ có ý nghĩa khi pool được phép thu nhỏ dưới maximum size, tức `minimumIdle` thấp hơn `maximumPoolSize`. Kết nối không bị đóng nếu việc đó làm pool giảm dưới minimum idle. Không dùng `idleTimeout` như cách giới hạn thời gian query hoặc transaction.

## 5. Phân biệt các timeout

HikariCP có nhiều timeout cho các giai đoạn khác nhau. Đặt chúng cùng một giá trị hoặc tăng tất cả khi có lỗi thường che giấu nguyên nhân.

| Tham số | Kiểm soát điều gì? | Khi hết hạn |
|---|---|---|
| `connectionTimeout` | Thời gian tối đa chờ lấy connection từ pool | `getConnection()` thất bại, thường ném `SQLTransientConnectionException` |
| `validationTimeout` | Thời gian tối đa kiểm tra connection còn hợp lệ | Validation không hoàn tất đúng hạn; giá trị phải nhỏ hơn `connectionTimeout` |
| `idleTimeout` | Thời gian connection idle vượt mức minimum có thể được thu hồi | Pool có thể đóng connection idle dư |
| `maxLifetime` | Tuổi thọ tối đa của connection vật lý trong pool | Connection được retire; connection đang được mượn thường chỉ bị loại khi trả về |
| `keepaliveTime` | Chu kỳ kiểm tra/giữ sống connection idle | Pool có thể ping connection idle; phải nhỏ hơn `maxLifetime` |
| `leakDetectionThreshold` | Ngưỡng cảnh báo connection được mượn quá lâu | Ghi cảnh báo kèm stack trace; không tự thu hồi connection |

Các tham số và giới hạn hợp lệ có thể thay đổi theo phiên bản HikariCP. Luôn kiểm tra tài liệu đúng phiên bản đang dùng.

### connectionTimeout

`connectionTimeout` là thời gian request chờ một connection sẵn sàng. Nó không phải query timeout và cũng không phải transaction timeout. Nếu pool đầy vì truy vấn đang chạy lâu, tăng `connectionTimeout` chỉ làm request chờ lâu hơn; nó không làm database xử lý nhanh hơn.

Nên đặt timeout phù hợp với deadline của request. Ví dụ, nếu API có deadline 2 giây, không nên để riêng bước lấy connection chờ 30 giây rồi mới trả lỗi. Cần dành thời gian cho truy vấn, xử lý kết quả và phản hồi.

### validationTimeout

Validation timeout giới hạn thời gian kiểm tra connection. Nó cần nhỏ hơn connection timeout để việc kiểm tra không vượt quá ngân sách chờ lấy kết nối. Với JDBC driver hỗ trợ `Connection.isValid()`, HikariCP thường có thể dùng cơ chế này; chỉ cấu hình `connectionTestQuery` khi driver cần câu kiểm tra tùy chỉnh theo tài liệu.

### maxLifetime

Một số firewall, load balancer, proxy hoặc database server đóng connection sau một thời gian nhất định. `maxLifetime` nên ngắn hơn giới hạn đó để pool chủ động thay connection trước khi hạ tầng đóng bất ngờ. HikariCP thường không retire một connection đang được ứng dụng mượn ngay giữa lúc sử dụng; connection được loại khi trả về pool sau khi hết tuổi thọ.

Không đặt `maxLifetime` quá thấp vì sẽ tạo churn: liên tục đóng/mở connection, tăng xác thực và tải lên database. Không đặt dài hơn giới hạn của hạ tầng nếu điều đó khiến connection chết bất ngờ.

### keepaliveTime

Keepalive có thể giúp connection idle không bị thiết bị mạng hoặc proxy đóng do không hoạt động. HikariCP chỉ kiểm tra connection idle, không thực hiện keepalive trên connection đang được ứng dụng mượn. `keepaliveTime` phải nhỏ hơn `maxLifetime` và cần phù hợp với chính sách idle timeout của hạ tầng.

### leakDetectionThreshold

Leak detection cảnh báo khi connection được mượn lâu hơn ngưỡng. Đây là công cụ chẩn đoán, không phải bộ hẹn giờ tự đóng connection. Một truy vấn hợp lệ nhưng chạy lâu cũng có thể kích hoạt cảnh báo. Hãy dùng stack trace để tìm nơi mượn connection và kiểm tra nó có được trả lại sau mọi nhánh thành công/lỗi hay không.

## 6. Sử dụng connection đúng cách trong Java

Luôn trả connection về pool kể cả khi truy vấn ném exception. Với JDBC thuần, dùng try-with-resources:

```java
public Customer findCustomer(DataSource dataSource, long customerId)
        throws SQLException {
    String sql = "SELECT customer_id, display_name "
               + "FROM customer WHERE customer_id = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, customerId);

        try (ResultSet resultSet = statement.executeQuery()) {
            if (!resultSet.next()) {
                return null;
            }
            return new Customer(
                    resultSet.getLong("customer_id"),
                    resultSet.getString("display_name"));
        }
    }
}
```

Khi `Connection.close()` được gọi, HikariCP nhận lại connection để tái sử dụng. Các đối tượng `Statement` và `ResultSet` cũng cần được đóng để giải phóng tài nguyên liên quan.

### Không giữ connection trong lúc làm việc không liên quan đến database

Tránh mẫu sau:

```java
try (Connection connection = dataSource.getConnection()) {
    updateOrder(connection);
    paymentGateway.callRemoteService(); // Có thể chờ mạng vài giây
    writeAuditRecord(connection);
}
```

Trong thời gian gọi dịch vụ thanh toán, connection vẫn bị giữ dù database không làm việc. Nếu nhiều request cùng làm vậy, active connections tăng và pool nhanh chóng cạn.

Hãy thiết kế transaction ngắn và điều phối thao tác bên ngoài transaction bằng trạng thái nghiệp vụ, outbox hoặc saga khi phù hợp. Tuy nhiên, không tách transaction tùy tiện nếu điều đó làm mất tính nguyên tử mà nghiệp vụ cần.

### Transaction scope phải rõ ràng

Trong Spring, transaction manager thường mượn connection khi transaction bắt đầu truy cập database và trả connection khi transaction hoàn tất. Một method `@Transactional` kéo dài qua nhiều lời gọi service có thể giữ connection lâu hơn dự kiến. Hạn chế đặt thao tác mạng, sleep, xử lý file hoặc chờ người dùng bên trong transaction.

Không mở connection thủ công bên trong một transaction được framework quản lý nếu không hiểu cách transaction manager bind connection theo thread. Dùng đúng `JdbcTemplate`, JPA repository hoặc cơ chế truy cập được cấu hình để tham gia cùng transaction.

## 7. Pool-locking và việc một thread giữ nhiều connection

Một trường hợp đặc biệt là mỗi thread có thể giữ nhiều connection cùng lúc. Nếu mọi thread đã giữ một connection và mỗi thread lại chờ connection thứ hai, pool có thể không còn connection rảnh để bất kỳ thread nào tiến lên. Đây là pool-locking.

Một giới hạn lý thuyết thường được dùng để tránh deadlock kiểu này là:

\[
P_{min} = T_n \times (C_m - 1) + 1
\]

Trong đó:

- (T_n) là số thread đồng thời có thể giữ connection.
- (C_m) là số connection tối đa mỗi thread có thể giữ cùng lúc.
- (P_{min}) là kích thước pool tối thiểu theo mô hình giữ nhiều connection này.

Ví dụ, nếu 8 thread có thể cùng giữ tối đa 2 connection, công thức cho kết quả 9. Đây là công thức tránh một dạng pool-locking trong giả định đã nêu, không phải công thức chọn pool size tối ưu cho database.

Thiết kế tốt hơn thường là giảm số connection được giữ đồng thời trên mỗi luồng, tránh lồng transaction hoặc truy cập nhiều datasource không cần thiết, và giữ thứ tự lấy tài nguyên nhất quán. Nếu phải dùng nhiều connection, cần kiểm thử deadlock ở mức pool và database.

## 8. Cấu hình HikariCP trong Spring Boot

Spring Boot thường tự cấu hình HikariCP làm pool mặc định khi thư viện có mặt trong classpath và ứng dụng dùng cấu hình datasource phù hợp. Có thể cấu hình trong `application.yml`:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db-host:5432/appdb
    username: app_user
    password: ${DB_PASSWORD}
    hikari:
      pool-name: app-db-pool
      maximum-pool-size: 12
      minimum-idle: 4
      connection-timeout: 1500
      validation-timeout: 1000
      idle-timeout: 300000
      max-lifetime: 1500000
      keepalive-time: 120000
      leak-detection-threshold: 0
```

Các con số chỉ là ví dụ cấu hình, không phải giá trị khuyến nghị chung. `maximum-pool-size: 12` cần được đánh giá cùng số replica và giới hạn session database. `connection-timeout: 1500` là 1,5 giây; phải phù hợp deadline request và latency bình thường. `leak-detection-threshold: 0` tắt cảnh báo leak; chỉ bật ngưỡng dương khi đang điều tra hoặc có lý do vận hành rõ.

### Cấu hình bằng Java

```java
HikariConfig config = new HikariConfig();
config.setJdbcUrl(jdbcUrl);
config.setUsername(username);
config.setPassword(password);
config.setPoolName("app-db-pool");
config.setMaximumPoolSize(12);
config.setMinimumIdle(4);
config.setConnectionTimeout(1500);
config.setValidationTimeout(1000);
config.setMaxLifetime(1_500_000);

HikariDataSource dataSource = new HikariDataSource(config);
```

Ứng dụng phải quản lý vòng đời `HikariDataSource` như một thành phần dùng chung. Khi ứng dụng shutdown, pool cần được đóng một lần để giải phóng connection và thread nội bộ. Không tạo một datasource mới cho mỗi repository hoặc request.

### Cẩn thận với cấu hình theo môi trường

Pool size phù hợp trên máy phát triển một instance có thể không phù hợp khi production chạy nhiều replica. Hãy tính tổng kết nối theo autoscaling max replicas, job nền và thời gian rolling deployment. Không đưa mật khẩu database vào file cấu hình được commit; dùng secret manager hoặc biến môi trường theo chính sách triển khai.

## 9. Đo HikariCP bằng Micrometer và JMX

HikariCP có thể cung cấp metric thông qua Micrometer hoặc JMX. Trong Spring Boot Actuator, khi cấu hình metrics phù hợp, các metric pool thường được xuất dưới nhóm tên bắt đầu bằng `hikaricp.connections`. Tên đầy đủ và tag phụ thuộc phiên bản Spring Boot, Micrometer và HikariCP.

Các đại lượng thường cần quan sát:

- `active`: số connection đang được mượn.
- `idle`: số connection đang rảnh.
- `pending`: số thread chờ connection.
- `max`: giới hạn pool.
- `min`: mức idle tối thiểu.
- `timeout`: số lần chờ lấy connection hết hạn.
- `acquire`: thời gian lấy connection.
- `usage`: thời gian giữ connection.
- `creation`: thời gian tạo connection mới nếu integration xuất metric này.

### Cấu hình quan sát

Với Spring Boot Actuator và Micrometer registry phù hợp, có thể kiểm tra endpoint metrics theo cấu hình bảo mật của ứng dụng. Ví dụ endpoint Actuator thường có dạng `/actuator/metrics`; metric cụ thể có thể là `/actuator/metrics/hikaricp.connections.active`. Không mở endpoint metrics công khai nếu chưa có kiểm soát truy cập và lọc thông tin phù hợp.

HikariCP cũng hỗ trợ JMX thông qua cấu hình `registerMbeans`. JMX hữu ích trong một số môi trường vận hành, nhưng cần bảo vệ cổng quản trị và xác thực phù hợp.

### Đặt tag và pool name

Đặt `poolName` dễ nhận diện như `orders-db-pool` hoặc `reporting-db-pool` để phân biệt nhiều pool. Tránh tạo tag có cardinality cao như user ID, request ID hoặc SQL parameter; metric có thể làm hệ thống monitoring phình bộ nhớ và khó tổng hợp.

## 10. Đọc metric để chẩn đoán

### Trường hợp A: pool bão hòa

Dấu hiệu:

- `active` thường xuyên bằng `max`.
- `idle` gần 0.
- `pending` duy trì lớn hơn 0.
- Acquire time và timeout count tăng.

Hướng điều tra:

1. Xác định truy vấn nào giữ connection lâu qua usage time và query fingerprint.
2. Kiểm tra lock wait, slow query, I/O và transaction duration ở database.
3. Kiểm tra code có giữ connection trong lúc gọi API hoặc xử lý không liên quan không.
4. Đối chiếu số pool trên toàn bộ replica với session capacity của database.
5. Chỉ tăng maximum pool size nếu database còn năng lực xử lý và thử nghiệm chứng minh throughput cải thiện.

### Trường hợp B: usage time cao nhưng pending thấp

Pool chưa chắc bão hòa, nhưng connection được giữ lâu. Có thể do truy vấn chậm, trả quá nhiều hàng, ứng dụng đọc `ResultSet` chậm hoặc transaction bao quanh quá nhiều thao tác. Hãy xem query duration và thời gian từ lúc mượn đến lúc trả connection.

### Trường hợp C: pending tăng dù database có vẻ nhàn

Kiểm tra connection creation, network, DNS, TLS, xác thực, database connection limit và connection validation. Pool có thể mất thời gian tạo connection mới hoặc nhiều connection bị retire cùng lúc. Kiểm tra log HikariCP và lỗi JDBC driver.

### Trường hợp D: active thấp nhưng timeout vẫn xuất hiện

Kiểm tra metric có đúng pool không, có nhiều datasource/pool khác nhau không, timeout xảy ra ở thời điểm nào và request có đang chờ tạo connection không. Có thể pool bị đóng, database không chấp nhận connection mới, hoặc timeout đến từ một pool khác.

### Trường hợp E: connection leak

Nếu active tăng dần theo thời gian và không trở về mức bình thường, pending tăng dù request rate không tăng tương ứng, có thể connection không được trả lại. Bật leak detection trong thời gian điều tra, xem stack trace, rà soát mọi đường thoát exception và bảo đảm try-with-resources hoặc transaction manager đóng tài nguyên.

Leak detection chỉ cảnh báo connection đã được giữ lâu hơn ngưỡng. Một transaction hợp lệ kéo dài cũng có thể tạo cảnh báo. Hãy xác minh code path và usage time trước khi kết luận.

## 11. HikariCP không thay thế timeout của truy vấn

Các timeout cần được cấu hình ở đúng lớp:

| Lớp | Ví dụ | Phạm vi |
|---|---|---|
| HTTP/request | Request deadline hoặc timeout của gateway | Toàn bộ thời gian xử lý yêu cầu |
| Connection pool | Hikari `connectionTimeout` | Chờ mượn connection |
| JDBC statement | `Statement.setQueryTimeout()` hoặc cấu hình driver | Thời gian chờ thực thi statement theo hỗ trợ driver |
| Transaction | Transaction timeout của framework/database | Thời gian transaction được phép tồn tại |
| Network/database | Socket timeout, server-side statement timeout | Chờ phản hồi mạng hoặc giới hạn phía database |

Nếu request deadline là 3 giây, tổng thời gian chờ pool, chạy SQL, xử lý kết quả và trả response phải nằm trong ngân sách đó. Cấu hình `connectionTimeout` 10 giây có thể khiến request vượt deadline trước khi SQL bắt đầu.

Query timeout không phải lúc nào cũng bảo đảm server dừng ngay mọi công việc. Hành vi cancel phụ thuộc driver và hệ quản trị; cần kiểm thử để xác nhận statement thực sự bị hủy và transaction được đưa về trạng thái hợp lệ.

## 12. Kết hợp pool sizing với năng lực database

Pool là van điều tiết tải. Để chọn kích thước, cần xem cả năng lực xử lý lẫn workload khác đang dùng database.

### Các giới hạn cần tính

- Giới hạn kết nối/session của database và phần dự phòng cho quản trị.
- Số replica tối đa khi autoscaling hoặc rolling deployment.
- Pool của API, worker, scheduler, batch và báo cáo.
- Kết nối từ migration, monitoring, backup và công cụ vận hành.
- Số truy vấn đồng thời database có thể xử lý mà không tăng mạnh lock wait, CPU hoặc I/O latency.
- Số transaction dài hoặc truy vấn phân tích cần connection lâu.

### Đừng tối ưu pool riêng lẻ

Nếu API có pool 20 connection nhưng database chỉ có thể xử lý tốt 40 transaction đồng thời cho workload chung, hai replica đã có thể tiêu thụ hết ngân sách. Nếu worker nền cũng mở 20 connection mỗi replica, API có thể bị cạnh tranh session dù pool riêng của nó chưa đầy.

Có thể tách workload đọc/ghi hoặc OLTP/analytics bằng datasource riêng, read replica hoặc hàng đợi. Nhưng mỗi pool bổ sung là một ngân sách kết nối mới; phải có giới hạn tổng và chính sách ưu tiên.

### Hàng đợi ở ứng dụng

Một pool nhỏ có thể khiến request chờ ở ứng dụng. Điều này có thể tốt hơn để database nhận quá nhiều truy vấn đồng thời, nhưng hàng đợi phải có giới hạn. Nếu request chờ quá lâu, nên trả lỗi quá tải có kiểm soát hoặc giảm tải sớm thay vì giữ hàng nghìn thread chờ connection.

Kết hợp connection pool với bounded executor, bulkhead, backpressure và deadline request để kiểm soát tổng concurrency. Không dùng queue vô hạn vì nó biến quá tải thành latency và bộ nhớ tăng không giới hạn.

## 13. Kiểm thử cấu hình pool

Không chọn pool size chỉ từ benchmark một request hoặc môi trường laptop. Hãy kiểm thử bằng workload gần production:

1. Xác định tỷ lệ đọc/ghi, thời gian SQL, transaction duration và số request đồng thời.
2. Chọn một số mức `maximumPoolSize` nhỏ, vừa và lớn trong ngân sách database.
3. Giữ cùng dữ liệu, query mix, số replica và cấu hình database.
4. Đo throughput commit, p50/p95/p99, acquire time, usage time, pending, timeout và số session database.
5. Theo dõi CPU, I/O, lock wait, memory, log flush và connection churn ở database.
6. Thử peak burst, rolling deployment, database failover và network interruption.
7. Kiểm tra pool có phục hồi sau connection bị đóng hoặc database restart không.
8. Chọn cấu hình đạt throughput mục tiêu với latency ổn định và headroom cho tải khác.

### Đường cong throughput

Khi tăng pool size, throughput có thể tăng lúc đầu vì nhiều truy vấn được chạy đồng thời hơn. Đến một điểm, database bão hòa; throughput phẳng hoặc giảm, trong khi p99, lock wait và active sessions tiếp tục tăng. Điểm vận hành phù hợp thường nằm trước vùng bão hòa, có đủ headroom cho spike và các dịch vụ khác.

Không chỉ so sánh requests/second ở tầng HTTP. Cần đo transaction commit thành công ở database, số timeout/retry và độ đúng dữ liệu. Một pool lớn có thể làm request được nhận nhiều hơn nhưng tỷ lệ hoàn tất thành công thấp hơn.

## 14. Cấu hình minh họa và cách diễn giải

```yaml
spring:
  datasource:
    hikari:
      pool-name: checkout-db-pool
      maximum-pool-size: 10
      minimum-idle: 3
      connection-timeout: 1200
      validation-timeout: 800
      max-lifetime: 1500000
      keepalive-time: 120000
      leak-detection-threshold: 0
```

Giả sử dịch vụ có tối đa 5 replica, mỗi replica có pool tối đa 10. Riêng dịch vụ checkout có thể mở đến 50 kết nối. Nếu database chỉ dành 60 session cho ứng dụng checkout, phần dự phòng cho migration, worker, monitoring và quản trị còn rất nhỏ. Nếu autoscaling tăng lên 8 replica, tổng tối đa thành 80 và có thể vượt ngân sách.

Trong ví dụ, `connection-timeout` 1,2 giây là giới hạn chờ lấy connection, không phải thời gian query. `max-lifetime` 25 phút chỉ là giá trị minh họa; phải ngắn hơn timeout của proxy/database nếu hạ tầng có giới hạn ngắn hơn. `keepalive-time` cần nhỏ hơn max lifetime. Leak detection đang tắt; có thể bật tạm thời khi điều tra connection bị giữ lâu.

Không sao chép cấu hình này vào mọi dịch vụ. Một worker batch có transaction dài, một API OLTP có request deadline ngắn và một job báo cáo có thể cần pool size, timeout và concurrency khác nhau.

## 15. Checklist chẩn đoán khi gặp lỗi lấy connection

Khi log xuất hiện lỗi kiểu `Connection is not available, request timed out`, hãy kiểm tra theo thứ tự:

1. Pool name nào phát sinh lỗi và cấu hình max/min hiện tại là gì?
2. Tại thời điểm lỗi, active, idle, total và pending là bao nhiêu?
3. Acquire time và timeout count tăng từ khi nào?
4. Connection usage time có tăng không? Có request hoặc transaction giữ connection lâu?
5. Database có slow query, lock wait, CPU/I/O saturation hoặc hết session không?
6. Có deploy, autoscaling hoặc batch job làm số pool tăng đột ngột không?
7. Có lỗi network, DNS, TLS, authentication hoặc connection validation không?
8. Có connection leak, N+1 query, result set lớn hoặc remote call bên trong transaction không?
9. Pool có tạo/đóng connection liên tục do maxLifetime/idleTimeout hoặc lỗi hạ tầng không?
10. Timeout có phù hợp request deadline và chính sách retry không?

Không tự động retry vô hạn khi lấy connection thất bại. Retry làm tăng số request chờ và có thể khuếch đại sự cố. Dùng retry có giới hạn, exponential backoff và jitter khi thao tác có thể retry an toàn; với transaction ghi, cần idempotency hoặc cơ chế xác định kết quả trước khi chạy lại.

## 16. Những sai lầm thường gặp

1. **Đặt maximumPoolSize thật lớn để hết timeout:** có thể làm database quá tải và tăng latency.
2. **Tính pool theo một instance:** quên nhân với số replica, worker và pool khác.
3. **Tăng connectionTimeout để che pool saturation:** request chỉ chờ lâu hơn.
4. **Nhầm connectionTimeout với query timeout:** SQL đã chạy có timeout riêng ở driver/database.
5. **Giữ connection trong lúc gọi API bên ngoài:** làm giảm số connection sẵn sàng cho truy vấn khác.
6. **Không dùng try-with-resources:** exception có thể khiến connection không được trả lại.
7. **Coi leak detection là cơ chế tự sửa leak:** nó chỉ cảnh báo connection bị giữ lâu.
8. **Đặt minimumIdle bằng maximumPoolSize ở mọi môi trường:** có thể giữ quá nhiều session lúc tải thấp.
9. **Đặt maxLifetime dài hơn giới hạn proxy/database:** connection có thể bị đóng bất ngờ khi đang dùng.
10. **Bật connectionTestQuery không cần thiết:** có thể thêm round trip nếu JDBC `isValid()` đã được hỗ trợ tốt.
11. **Chỉ theo dõi active connections:** bỏ qua pending, acquire time, usage time và database wait.
12. **Dùng queue vô hạn khi pool đầy:** biến quá tải thành tăng latency và tiêu thụ bộ nhớ.
13. **Tạo nhiều DataSource không kiểm soát:** tổng connection tăng ngoài dự kiến.
14. **Đánh giá bằng request rate thay vì commit thành công:** không nhận ra timeout, retry và rollback.

## 17. Danh sách kiểm tra trước khi triển khai

- [ ] Đã tính tổng connection tối đa từ mọi replica, pool, worker và công cụ vận hành.
- [ ] Đã chừa session cho quản trị, migration, failover và các dịch vụ khác.
- [ ] Đã chọn `maximumPoolSize` bằng load test với database workload đại diện.
- [ ] Đã xác định `minimumIdle` theo yêu cầu warm-up, tải nền và chi phí giữ session.
- [ ] `connectionTimeout` phù hợp deadline request; không bị nhầm với query timeout.
- [ ] `validationTimeout` nhỏ hơn `connectionTimeout`.
- [ ] `maxLifetime` và `keepaliveTime` phù hợp giới hạn proxy/network/database và phiên bản HikariCP.
- [ ] Đã kiểm tra mọi connection được trả lại qua try-with-resources hoặc transaction manager.
- [ ] Không giữ connection trong lúc chờ dịch vụ ngoài hoặc xử lý không liên quan.
- [ ] Đã theo dõi active, idle, pending, acquire, usage và timeout count.
- [ ] Đã có cảnh báo cho pending kéo dài, acquire latency và timeout tăng.
- [ ] Đã kiểm thử peak burst, rolling deployment, database restart và network interruption.
- [ ] Đã xác minh throughput commit, p95/p99, lock wait và database headroom sau điều chỉnh.

HikariCP giúp tái sử dụng và giới hạn kết nối JDBC, nhưng hiệu quả phụ thuộc vào cách chọn pool size, thời gian giữ connection và khả năng xử lý của database. Hãy tính tổng connection trên tất cả replica, dùng timeout theo deadline của request, trả connection ngay sau khi hoàn tất công việc database và theo dõi active/idle/pending cùng acquire/usage time. Khi pool bão hòa, tìm nguyên nhân ở query, transaction, lock, network hoặc connection lifecycle trước khi tăng giới hạn. Chỉ chốt cấu hình sau khi load test chứng minh throughput commit và p95/p99 cải thiện mà database vẫn còn headroom.
