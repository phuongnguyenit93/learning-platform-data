# Cấu hình pool: kích thước, thời gian chờ và vòng đời kết nối

Trong **Spring Data Relational JDBC**, repository và JdbcTemplate truy cập database thông qua DataSource. Trong ứng dụng chạy thật, DataSource thường được bọc bởi một **connection pool**: pool tạo và giữ sẵn một số JDBC connection, cấp connection cho thao tác cần database và nhận lại connection khi thao tác hoàn tất.

Connection pool giúp tránh tạo kết nối vật lý mới cho từng câu SQL, kiểm soát số kết nối đồng thời và phát hiện tình trạng thiếu connection. Nhưng pool cần được cấu hình theo năng lực database và tải thực tế. Pool quá nhỏ làm request phải chờ; pool quá lớn có thể làm database quá tải, tăng tranh chấp lock và giảm throughput.

Bài này dùng **HikariCP** làm ví dụ vì Spring Boot thường chọn HikariCP khi thư viện có mặt trên classpath. Các thuộc tính spring.datasource.hikari.* chỉ áp dụng cho HikariCP; pool khác có tên thuộc tính và semantics riêng.

## 1. Connection pool nằm ở đâu trong Spring Data JDBC?

Repository Spring Data JDBC không tự giữ một JDBC connection trong suốt vòng đời bean. Repository dùng hạ tầng DataSource để lấy connection khi cần thực hiện thao tác database. Pool quản lý các connection vật lý và tái sử dụng chúng.

```text
Application service
       │
       ▼
Spring Data JDBC repository / JdbcTemplate
       │
       ▼
DataSource (HikariCP pool)
       │
       ├── Connection A ───┐
       ├── Connection B ───┼── Database
       ├── Connection C ───┤
       └── ...             ┘
```

Khi một thao tác cần connection, pool cấp một connection đang rảnh. Khi JDBC connection được đóng theo contract, HikariCP thường đưa connection trở lại pool thay vì đóng kết nối vật lý ngay lập tức.

Lợi ích chính:

- Giảm chi phí tạo TCP/database session lặp lại.
- Giới hạn số connection mà một instance ứng dụng mở tới database.
- Cho phép cấu hình thời gian chờ lấy connection.
- Tái sử dụng connection sau khi transaction hoặc thao tác JDBC hoàn tất.
- Cung cấp metric để quan sát connection đang dùng, đang rảnh và request đang chờ.

Pool không làm câu SQL chạy nhanh hơn một cách tự động. Query chậm, lock contention, transaction dài hoặc database thiếu tài nguyên vẫn gây chậm dù pool được cấu hình tốt.

## 2. Spring Boot chọn và cấu hình HikariCP

Khi dùng Spring Boot với JDBC starter và HikariCP có mặt trên classpath, auto-configuration thường tạo DataSource dùng HikariCP. Spring Data JDBC dùng DataSource này thông qua JDBC infrastructure.

Ví dụ cấu hình:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop
    username: shop_app
    password: configure-through-secret-store
    hikari:
      pool-name: ShopJdbcPool
      maximum-pool-size: 12
      minimum-idle: 3
      connection-timeout: 2000
      validation-timeout: 1000
      idle-timeout: 600000
      max-lifetime: 1740000
      keepalive-time: 120000
      leak-detection-threshold: 0
```

Các giá trị trên là cấu hình minh họa, không phải bộ thông số tối ưu cho mọi ứng dụng. Chẳng hạn maximum-pool-size 12 chỉ là một điểm bắt đầu cần kiểm chứng bằng tải thật; nó không có nghĩa database luôn nên nhận 12 connection từ mỗi instance.

Những thuộc tính Hikari thường được quan tâm:

| Thuộc tính | Tác dụng |
| --- | --- |
| pool-name | Tên pool trong log/metric |
| maximum-pool-size | Số connection tối đa, gồm connection đang dùng và đang rảnh |
| minimum-idle | Số connection rảnh tối thiểu mà pool cố duy trì |
| connection-timeout | Thời gian tối đa chờ lấy connection từ pool |
| validation-timeout | Thời gian tối đa chờ kiểm tra một connection |
| idle-timeout | Thời gian connection rảnh có thể được loại bỏ khi pool có nhiều hơn mức tối thiểu |
| max-lifetime | Tuổi thọ tối đa của connection trong pool |
| keepalive-time | Chu kỳ kiểm tra/giữ sống connection đang rảnh |
| leak-detection-threshold | Ngưỡng cảnh báo connection được mượn quá lâu |

Nếu không dùng HikariCP, hãy kiểm tra pool thực tế được Spring Boot chọn và tài liệu cấu hình của pool đó. Không sao chép nguyên xi các thuộc tính Hikari sang Tomcat JDBC Pool, Apache DBCP2 hoặc pool do ứng dụng tự tạo.

## 3. Chọn maximumPoolSize

maximumPoolSize giới hạn tổng số connection mà một HikariCP pool có thể cấp đồng thời. Nó bao gồm connection đang được ứng dụng mượn và connection đang rảnh trong pool.

Khi mọi connection đã được mượn, request tiếp theo phải đợi một connection trả về. Nếu thời gian chờ vượt connectionTimeout, HikariCP ném lỗi lấy connection.

### 3.1. Không chọn pool size chỉ dựa trên số thread

Một ứng dụng có 200 HTTP worker thread không có nghĩa cần 200 database connection. Phần lớn request có thể đang xử lý CPU, gọi dịch vụ khác hoặc không truy cập database cùng lúc. Ngược lại, một số ít transaction chạy lâu cũng có thể giữ connection và làm pool cạn.

Số connection phù hợp phụ thuộc:

- Khả năng xử lý đồng thời của database.
- Số CPU và tài nguyên I/O của database.
- Thời gian một thao tác giữ connection.
- Số query/transaction đang chạy đồng thời.
- Số instance ứng dụng và các dịch vụ khác cùng dùng database.
- Workload đọc/ghi, lock contention và độ phức tạp query.

Tăng pool size có thể làm tăng số query cùng tranh chấp CPU, I/O và lock. Nếu database đã bão hòa, thêm connection thường không cải thiện throughput.

### 3.2. Tính tổng connection của toàn hệ thống

Đừng chỉ nhìn maximum-pool-size của một instance. Ví dụ có 4 instance ứng dụng, mỗi instance cấu hình pool tối đa 12:

```text
4 application instances × 12 connections = 48 connections
```

Database còn có thể nhận kết nối từ worker/background job, migration tool, admin console, công cụ giám sát, dịch vụ khác và pool riêng cho datasource khác.

Tổng connection tối đa phải nằm trong giới hạn database cho phép, đồng thời chừa dung lượng cho admin, failover và các tác vụ vận hành. Với nhiều datasource, tính riêng từng pool rồi cộng tổng theo database đích. Khi rolling deployment hoặc autoscaling, tính cả số instance overlap trong thời gian chuyển đổi.

### 3.3. Cách tìm kích thước phù hợp

Một quy trình thực tế:

1. Xác định giới hạn connection của database và phần dung lượng cần chừa.
2. Tính tổng số instance có thể chạy đồng thời, kể cả autoscaling và rolling deployment.
3. Chọn pool size ban đầu bảo thủ.
4. Chạy tải đại diện cho production, gồm cả giờ cao điểm và query nặng.
5. Quan sát connection active/idle/pending, thời gian chờ lấy connection, query latency và database CPU/I/O.
6. Điều chỉnh pool size rồi chạy lại cùng workload để so sánh.

Nếu số connection active thường thấp hơn giới hạn và không có request pending, tăng pool có thể không đem lại lợi ích. Nếu pool thường xuyên chạm giới hạn, cần tìm nguyên nhân connection bị giữ lâu trước khi chỉ tăng con số.

## 4. minimumIdle và pool cố định

minimumIdle là số connection rảnh tối thiểu mà HikariCP cố gắng duy trì. Nếu minimumIdle nhỏ hơn maximumPoolSize, pool có thể mở rộng khi tải tăng và loại bỏ connection rảnh vượt mức tối thiểu sau idleTimeout.

HikariCP mặc định minimumIdle bằng maximumPoolSize nếu không cấu hình riêng, tạo hành vi gần với fixed-size pool. Tài liệu HikariCP thường khuyến nghị giữ mặc định này cho nhiều workload để có khả năng phản hồi ổn định; pool linh hoạt vẫn có thể hữu ích khi chi phí giữ connection rảnh đáng kể.

Ví dụ:

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 12
      minimum-idle: 3
      idle-timeout: 600000
```

Pool có thể giữ ít nhất 3 connection rảnh và tăng lên khi có tải. Nếu đặt minimum-idle bằng 12, pool duy trì đủ 12 connection rảnh khi không có connection nào đang được mượn.

Không đặt minimum-idle cao hơn nhu cầu chỉ để tránh khởi tạo connection khi có tải. Mỗi connection rảnh vẫn là một session database và tiêu thụ tài nguyên.

## 5. Phân biệt các loại timeout

Từ timeout có thể nói về nhiều giai đoạn khác nhau. Cấu hình đúng phụ thuộc giai đoạn cần giới hạn:

| Timeout | Giới hạn điều gì? | Thường cấu hình ở đâu? |
| --- | --- | --- |
| Pool acquisition timeout | Chờ mượn connection từ pool | Hikari connection-timeout |
| Connection validation timeout | Chờ kiểm tra connection | Hikari validation-timeout |
| Driver connect timeout | Mở kết nối vật lý tới database | JDBC driver URL/property |
| Query/statement timeout | Thời gian thực thi câu SQL | JDBC statement, Spring JDBC hoặc database |
| Socket/read timeout | Chờ dữ liệu qua socket sau khi gửi query | JDBC driver/network/database |
| Transaction timeout | Thời gian cho phép transaction hoàn tất | Transaction manager/framework |

connection-timeout của HikariCP **không phải query timeout**. Nếu một câu SQL chạy 60 giây, đặt connection-timeout thành 2 giây không tự hủy câu SQL sau 2 giây. Nó chỉ giới hạn thời gian request chờ được cấp connection từ pool.

## 6. connectionTimeout: thời gian chờ mượn connection

Ví dụ:

```yaml
spring:
  datasource:
    hikari:
      connection-timeout: 2000
```

Giá trị tính bằng milliseconds. Nếu không có connection rảnh và pool đã đạt maximumPoolSize, caller chờ tối đa khoảng thời gian này. Khi hết hạn, HikariCP báo lỗi timeout lấy connection.

Chọn timeout dựa trên latency mục tiêu của ứng dụng:

- Quá ngắn: request có thể lỗi khi tải tăng đột biến trong thời gian ngắn.
- Quá dài: thread ứng dụng bị giữ lâu để chờ connection, làm tăng hàng đợi và có thể gây hiệu ứng domino.
- Phải phối hợp với HTTP request timeout, transaction timeout và retry policy.

Không retry vô hạn khi pool hết connection. Retry nhanh có thể làm tăng số request chờ và khiến pool/database càng khó phục hồi.

## 7. validationTimeout và driver connect timeout

validation-timeout giới hạn thời gian chờ kiểm tra connection còn hợp lệ. Giá trị này phải nhỏ hơn connection-timeout.

Ví dụ:

```yaml
spring:
  datasource:
    hikari:
      connection-timeout: 2000
      validation-timeout: 1000
```

Driver connect timeout áp dụng khi tạo kết nối vật lý mới, không phải khi mượn connection đang có trong pool. Cách cấu hình phụ thuộc JDBC driver. Ví dụ với PostgreSQL JDBC, URL có thể chứa connectTimeout:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db-host:5432/shop?connectTimeout=5
```

Giá trị và đơn vị phải theo tài liệu driver đang dùng. Không dùng URL property của PostgreSQL cho MySQL, SQL Server hoặc Oracle.

Nếu database khởi động chậm hoặc mạng không ổn định, driver connect timeout và cách ứng dụng khởi động/fail-fast cần được thiết kế riêng. connection-timeout không thay thế chúng.

## 8. idleTimeout: loại bỏ connection rảnh

idle-timeout quy định thời gian một connection rảnh có thể tồn tại trước khi pool xem xét loại bỏ nó. HikariCP chỉ thu hẹp pool xuống dưới maximumPoolSize khi số connection rảnh vượt minimumIdle.

Ví dụ:

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 12
      minimum-idle: 3
      idle-timeout: 600000
```

Khi tải giảm, pool có thể đóng những connection rảnh vượt mức 3 sau thời gian idle. Nó không đóng connection đang được transaction sử dụng.

Nếu minimumIdle bằng maximumPoolSize, idle-timeout không làm pool giảm xuống dưới mức cố định đó. Vì vậy, đừng kỳ vọng chỉ đổi idle-timeout là giảm được tất cả connection rảnh.

## 9. maxLifetime: vòng đời tối đa của connection

max-lifetime quy định tuổi thọ tối đa mà pool cho phép một connection tồn tại. HikariCP không cố đóng connection đang được sử dụng; connection hết tuổi thọ sẽ được đánh dấu để loại bỏ sau khi được trả về.

Nên đặt maxLifetime thấp hơn giới hạn tuổi thọ connection do database, proxy, firewall hoặc hạ tầng mạng áp đặt. Ví dụ, nếu hạ tầng đóng connection sau 30 phút, pool có thể đặt khoảng 29 phút để chủ động loại bỏ trước giới hạn đó:

```yaml
spring:
  datasource:
    hikari:
      max-lifetime: 1740000
```

Đây chỉ là ví dụ khi giới hạn hạ tầng thực sự là 30 phút. Hãy xác định timeout của database/proxy/network đang dùng. Nếu maxLifetime dài hơn giới hạn bên ngoài, ứng dụng có thể mượn phải connection đã bị hạ tầng đóng và gặp lỗi giữa thao tác.

Không đặt maxLifetime quá ngắn nếu không có lý do; pool sẽ thường xuyên tạo connection mới, tăng chi phí handshake và tải lên database.

## 10. keepaliveTime: giữ connection rảnh không bị hạ tầng đóng

keepalive-time cho phép HikariCP kiểm tra connection đang rảnh theo chu kỳ để tránh bị một số thiết bị mạng hoặc dịch vụ database đóng do idle. Keepalive chỉ áp dụng cho connection đang rảnh, không chạy trên connection đang được ứng dụng mượn.

Ví dụ nếu hạ tầng đóng connection rảnh sau 5 phút, có thể cấu hình keepalive ngắn hơn khoảng đó:

```yaml
spring:
  datasource:
    hikari:
      keepalive-time: 120000
      max-lifetime: 1740000
```

keepalive-time phải nhỏ hơn max-lifetime. Không bật keepalive chỉ vì có thể; trước tiên xác định database/proxy có idle timeout hay không. Keepalive tạo thêm hoạt động kiểm tra, vì vậy cần cân nhắc khi có nhiều pool và nhiều connection.

## 11. leakDetectionThreshold: phát hiện connection bị giữ lâu

leak-detection-threshold khiến HikariCP ghi cảnh báo nếu connection được mượn lâu hơn ngưỡng cấu hình mà chưa được trả lại.

Ví dụ bật tạm trong môi trường kiểm thử:

```yaml
spring:
  datasource:
    hikari:
      leak-detection-threshold: 30000
```

Nếu một connection được giữ quá 30 giây, HikariCP có thể ghi stack trace nơi connection được mượn. Đây là **cảnh báo**, không phải cơ chế tự động thu hồi connection. Connection có thể được trả về sau đó; log cảnh báo không tự chứng minh có leak thật.

Các nguyên nhân thường gặp:

- Lấy connection trực tiếp nhưng quên đóng.
- Không đóng ResultSet hoặc Statement khi tự quản lý JDBC.
- Transaction mở quá lâu.
- Gọi HTTP/service ngoài trong khi đang giữ transaction.
- Chờ lock hoặc câu SQL chạy lâu.
- Đường code lỗi không đi qua finally/try-with-resources.

JdbcTemplate và Spring Data repository quản lý vòng đời JDBC resource thông thường. Nếu tự dùng JDBC trực tiếp, dùng try-with-resources hoặc API transaction-aware phù hợp. Không giữ connection trong field của singleton service.

## 12. Vòng đời connection trong transaction

Trong Spring JDBC, transaction manager có thể gắn một connection với transaction hiện tại. Các thao tác repository/JDBC trong cùng transaction thường dùng lại connection được quản lý đó. Khi transaction hoàn tất, connection được trả lại pool.

```text
@Transactional service method
          │
          ▼
Transaction manager bắt đầu transaction
          │
          ▼
Mượn connection từ DataSource pool
          │
          ▼
Repository call A ───┐
                     ├── dùng connection của transaction
Repository call B ───┘
          │
          ▼
Commit hoặc rollback
          │
          ▼
Trả connection về pool
```

Ví dụ:

```java
@Service
public class OrderService {

    private final PurchaseOrderRepository orders;
    private final CustomerRepository customers;

    public OrderService(
            PurchaseOrderRepository orders,
            CustomerRepository customers) {
        this.orders = orders;
        this.customers = customers;
    }

    @Transactional
    public void confirmOrder(Long orderId, Long customerId) {
        PurchaseOrder order = orders.findById(orderId)
                .orElseThrow();
        Customer customer = customers.findById(customerId)
                .orElseThrow();

        order.confirmFor(customer);
        orders.save(order);
    }
}
```

Các repository call trong cùng transaction có thể dùng connection gắn với transaction đó. Connection không được giữ suốt vòng đời OrderService; nó được mượn và trả theo transaction/operation.

Với thao tác không nằm trong transaction tường minh, Spring Data/JDBC vẫn lấy connection để thực hiện lệnh và trả lại sau khi hoàn tất. Transaction boundary nên đặt ở service/use case để nhiều thao tác cần nguyên tử có thể dùng cùng transaction.

### 12.1. Không giữ transaction lâu hơn cần thiết

Ví dụ không nên:

```java
@Transactional
public OrderResult process(Long id) {
    PurchaseOrder order = repository.findById(id).orElseThrow();

    // Gọi dịch vụ bên ngoài trong khi transaction/connection đang mở.
    paymentClient.authorize(order);

    order.confirm();
    repository.save(order);
    return OrderResult.from(order);
}
```

Nếu paymentClient mất 10 giây, connection có thể bị giữ trong suốt thời gian chờ dù database không làm việc. Nhiều request như vậy có thể làm pool cạn.

Thiết kế transaction ngắn hơn, chỉ bao quanh phần database cần nguyên tử. Nếu cần phối hợp với hệ thống ngoài, cân nhắc quy trình nhiều bước, outbox hoặc saga theo yêu cầu nghiệp vụ thay vì giữ connection trong lúc chờ mạng.

### 12.2. Tự lấy connection

Nếu cần dùng JDBC trực tiếp:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement("SELECT 1")) {
    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            // Xử lý kết quả.
        }
    }
}
```

Với connection lấy trực tiếp từ pool ngoài transaction, close() trả connection về pool. Trong transaction do Spring quản lý, nên dùng JdbcTemplate, DataSourceUtils hoặc TransactionAwareDataSourceProxy phù hợp để tham gia đúng transaction. Không tự đóng connection vật lý được Spring transaction manager quản lý.

## 13. Cấu hình theo môi trường

Pool size và timeout thường khác nhau giữa local, test, staging và production. Có thể dùng profile:

```yaml
spring:
  config:
    activate:
      on-profile: local
  datasource:
    hikari:
      maximum-pool-size: 4
      minimum-idle: 1
      connection-timeout: 3000
```

Production có thể cấu hình qua biến môi trường của nền tảng triển khai hoặc secret store. Không commit username/password thật vào repository.

Khi dùng nhiều datasource, mỗi datasource có thể có pool riêng. Hãy đặt tên pool khác nhau và tính tổng connection tới từng database. Không nhân đôi pool cho cùng một database nếu không có lý do kiến trúc rõ ràng.

## 14. Theo dõi pool bằng metrics

HikariCP cung cấp số liệu giúp biết pool đang hoạt động thế nào. Khi tích hợp Micrometer/Actuator, các metric thường có tiền tố hikaricp.connections:

| Metric | Ý nghĩa |
| --- | --- |
| hikaricp.connections.active | Số connection đang được mượn |
| hikaricp.connections.idle | Số connection rảnh trong pool |
| hikaricp.connections.pending | Số caller đang chờ connection |
| hikaricp.connections.max | Giới hạn connection tối đa |
| hikaricp.connections.min | Mức connection rảnh tối thiểu |
| hikaricp.connections.acquire | Thời gian lấy connection |
| hikaricp.connections.usage | Thời gian connection được sử dụng |

Metric cụ thể có thể khác theo phiên bản Micrometer, HikariCP và registry. Dùng endpoint Actuator hoặc hệ thống metrics đã cấu hình để xác nhận tên metric thực tế.

Một số dấu hiệu:

- active thường xuyên bằng max và pending tăng: pool đang bão hòa.
- pending tăng nhưng database CPU thấp: có thể transaction giữ connection lâu, lock wait hoặc connection bị rò rỉ.
- active cao cùng query latency cao và database CPU/I/O cao: database có thể là nút thắt; tăng pool có thể làm tình hình tệ hơn.
- idle cao liên tục: pool có thể đang lớn hơn nhu cầu, nhưng phải xét đỉnh tải và khả năng scale.
- acquire tăng: request mất thời gian chờ lấy connection.

Không xem một snapshot đơn lẻ là kết luận. Quan sát xu hướng qua giờ cao điểm, deploy, autoscaling và batch job.

## 15. Chẩn đoán pool cạn

Khi log có lỗi kiểu “Connection is not available, request timed out”, kiểm tra theo thứ tự:

1. Pool nào phát sinh lỗi và maximumPoolSize hiện tại là bao nhiêu?
2. active, idle, pending tại thời điểm lỗi?
3. Query nào đang chạy lâu hoặc chờ lock?
4. Transaction nào giữ connection lâu?
5. Có đường JDBC trực tiếp không đóng resource không?
6. Có HTTP call, file I/O hoặc xử lý CPU nằm trong transaction không?
7. Tổng pool size của tất cả replica có vượt ngân sách database không?
8. Database có đang đạt giới hạn connection, CPU, I/O hoặc memory không?

Nếu connection được giữ lâu do query chậm, tối ưu query/index hoặc xử lý lock trước khi tăng pool. Nếu workload thực sự cần nhiều connection hơn và database còn đủ năng lực, tăng dần pool rồi đo lại.

Không đặt maximum-pool-size cực lớn để loại bỏ timeout. Việc đó có thể chuyển hàng đợi từ ứng dụng sang database, khiến tất cả query chậm hơn và làm lỗi lan rộng.

## 16. Vòng đời pool khi ứng dụng khởi động và tắt

Trong ứng dụng Spring Boot, DataSource là bean do container quản lý. Khi application context khởi động, pool được khởi tạo theo cấu hình; tùy cấu hình khởi tạo, ứng dụng có thể tạo một số connection sớm hoặc tạo khi có nhu cầu.

Khi ứng dụng tắt bình thường, Spring đóng bean DataSource và HikariCP dọn pool, giải phóng các connection vật lý. Không tạo pool mới cho mỗi request và không tự gọi close() trên bean DataSource dùng chung trong service.

Trong rolling deployment:

- Instance cũ cần có thời gian hoàn tất request/transaction đang chạy.
- Readiness/liveness và graceful shutdown phải phối hợp với thời gian drain request.
- Instance mới có thể mở pool trong lúc instance cũ chưa đóng; tính cả giai đoạn overlap trong ngân sách connection database.
- Không để shutdown cắt ngang transaction quan trọng nếu nền tảng cho phép cấu hình thời gian chờ dừng phù hợp.

Nếu database restart hoặc network bị gián đoạn, pool có thể loại bỏ connection lỗi và tạo lại theo khả năng của driver/pool. Ứng dụng vẫn cần retry có giới hạn ở tầng phù hợp và xử lý lỗi transaction; pool không thể làm một transaction đang thất bại trở thành thành công.

## 17. Ví dụ cấu hình tổng hợp

Một cấu hình minh họa cho ứng dụng Spring Data JDBC dùng PostgreSQL:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db-host:5432/shop
    username: shop_app
    password: set-through-secret-store
    hikari:
      pool-name: ShopJdbcPool
      maximum-pool-size: 12
      minimum-idle: 3
      connection-timeout: 2000
      validation-timeout: 1000
      idle-timeout: 600000
      max-lifetime: 1740000
      keepalive-time: 120000
      leak-detection-threshold: 0
```

Ý nghĩa của ví dụ:

- Tối đa 12 connection cho một instance ứng dụng.
- Cố duy trì ít nhất 3 connection rảnh.
- Chờ tối đa 2 giây để mượn connection.
- Timeout kiểm tra connection là 1 giây, nhỏ hơn acquisition timeout.
- Connection rảnh có thể được loại bỏ nếu vượt mức tối thiểu.
- Tuổi thọ connection là 29 phút trong ví dụ giả định hạ tầng có giới hạn 30 phút.
- Keepalive kiểm tra connection rảnh mỗi 2 phút, nếu driver/pool và hạ tầng cần.
- Tắt leak detection trong cấu hình bình thường; bật tạm khi điều tra connection bị giữ lâu.

Trước khi dùng các con số này, xác nhận giới hạn database/proxy, số replica tối đa, workload và metrics. Giá trị cấu hình là điểm xuất phát cho thử nghiệm tải, không phải công thức thay cho đo đạc.

## 18. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Connection acquisition timeout | Pool hết connection hoặc connection bị giữ lâu | Xem active/pending, transaction duration, query và leak |
| Tăng pool nhưng throughput không tăng | Database đã bão hòa hoặc lock contention | Đo database CPU/I/O, query latency và lock wait |
| Pool có nhiều connection idle | minimumIdle cao hoặc pool size lớn hơn nhu cầu | Đánh giá mức tối thiểu và tải đỉnh trước khi giảm |
| Connection bị đóng khi đang dùng | maxLifetime dài hơn giới hạn hạ tầng hoặc network cắt kết nối | Đặt lifetime thấp hơn giới hạn bên ngoài và kiểm tra driver |
| Connection idle bị firewall/proxy đóng | Không có keepalive hoặc idle timeout không tương thích | Xác định timeout hạ tầng và cấu hình keepalive phù hợp |
| connection-timeout ngắn nhưng SQL vẫn chạy lâu | Nhầm acquisition timeout với query timeout | Cấu hình statement/database/driver timeout riêng |
| Leak detection cảnh báo nhưng không có leak | Transaction hoặc query hợp lệ chạy lâu hơn ngưỡng | Đối chiếu stack trace và thời gian usage; điều chỉnh ngưỡng |
| Database hết giới hạn connection khi deploy | Tổng pool của các replica và instance overlap quá lớn | Tính ngân sách connection toàn hệ thống |
| Test chạy được nhưng production lỗi connection | Pool/test DB không giống production hoặc tải test quá thấp | Dùng database mục tiêu và tải đại diện |
| Connection không được trả về | JDBC resource tự quản lý không được đóng | Dùng try-with-resources hoặc Spring JDBC abstraction |

## 19. Checklist cấu hình pool

Trước khi đưa pool configuration lên production, xác nhận:

1. Pool thực tế là HikariCP hay implementation khác?
2. Tổng connection tối đa của mọi replica/datasource nằm trong ngân sách database?
3. maximumPoolSize được chọn từ tải đo được thay vì số thread?
4. minimumIdle có phù hợp với tải nền và chi phí connection rảnh?
5. connectionTimeout phù hợp với request/transaction deadline?
6. validationTimeout nhỏ hơn connectionTimeout?
7. maxLifetime thấp hơn giới hạn connection của database/proxy/network?
8. keepaliveTime chỉ bật khi cần và nhỏ hơn maxLifetime?
9. Driver connect timeout và query timeout được cấu hình riêng nếu cần?
10. Transaction ngắn, không giữ connection trong lúc chờ dịch vụ ngoài?
11. Có metrics active/idle/pending/acquire/usage và cảnh báo phù hợp?
12. Có kế hoạch graceful shutdown và tính cả connection overlap khi deploy?

## 20. Bài tập thực hành

**Bài 1 — Quan sát pool.** Chạy ứng dụng Spring Data JDBC với HikariCP. Ghi lại pool name, maximum size, minimum idle và số connection active/idle lúc ứng dụng nhàn rỗi.

**Bài 2 — Pool exhaustion.** Tạo một endpoint test giữ transaction lâu có kiểm soát. Gửi nhiều request đồng thời và quan sát active, pending cùng lỗi acquisition timeout. Dừng test ngay sau khi thu được metrics cần thiết.

**Bài 3 — So sánh pool size.** Chạy cùng workload với các mức maximum pool size khác nhau. Ghi throughput, p95/p99 latency, database CPU và lock wait; không chỉ so sánh số request thành công.

**Bài 4 — Timeout khác nhau.** Làm một thao tác chờ connection và một query chạy lâu. Quan sát connection-timeout chỉ ảnh hưởng việc mượn connection, rồi thử query/statement timeout riêng.

**Bài 5 — maxLifetime và keepalive.** Đọc cấu hình idle/lifetime của database hoặc proxy. Đặt max lifetime thấp hơn giới hạn và keepalive thấp hơn idle timeout khi cần; quan sát connection được thay mới.

**Bài 6 — Leak detection.** Bật leak-detection-threshold trong môi trường test, cố ý giữ một connection lâu rồi trả lại. Đọc stack trace và phân biệt cảnh báo usage lâu với connection bị mất thật.

**Bài 7 — Transaction boundary.** So sánh một service giữ transaction trong lúc gọi HTTP với phiên bản tách phần gọi HTTP ra ngoài transaction. Quan sát connection usage và pending requests.

**Bài 8 — Graceful shutdown.** Chạy một transaction có thời gian xác định, gửi tín hiệu dừng ứng dụng và quan sát quá trình drain request, đóng DataSource và giải phóng pool.

### Tài liệu tham khảo

- [Spring Boot — SQL Databases / DataSource Configuration](https://docs.spring.io/spring-boot/reference/data/sql.html): auto-configuration DataSource và connection pool.
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby): ý nghĩa các thuộc tính pool, timeout, lifetime, keepalive và leak detection.
- [Spring Framework — Data Access and JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html): JdbcTemplate, quản lý JDBC resource và transaction integration.
- [Spring Framework — DataSourceTransactionManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html): quản lý connection gắn với transaction JDBC.
