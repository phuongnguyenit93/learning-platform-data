# DataSource, connection pool và chi phí truy cập cơ sở dữ liệu

Trong ứng dụng dùng **Spring Data JDBC**, mỗi thao tác đọc hoặc ghi dữ liệu cuối cùng đều phải đi qua một kết nối JDBC để gửi câu lệnh SQL đến cơ sở dữ liệu quan hệ. Hiểu `DataSource`, connection pool và chi phí của từng lần truy cập giúp giải thích vì sao một truy vấn SQL có vẻ đơn giản vẫn có thể chậm, vì sao ứng dụng hết kết nối khi có nhiều request, và vì sao tăng kích thước pool không phải lúc nào cũng cải thiện hiệu năng.

Bài này tập trung vào nền tảng cần biết trước khi sử dụng `CrudRepository`, `JdbcTemplate`, `JdbcClient` và transaction trong Spring Data JDBC.

## 1. Từ lời gọi Repository đến cơ sở dữ liệu

Một luồng truy cập dữ liệu thường có hình dạng:

~~~text
HTTP request / job / message handler
          |
          v
       Service
          |
          +---- Spring Transaction Manager (nếu có @Transactional)
          |
          v
Spring Data JDBC Repository / JdbcClient / JdbcTemplate
          |
          v
      DataSource
          |
          v
Connection pool (thường là HikariCP trong Spring Boot)
          |
          v
JDBC Driver (ví dụ PostgreSQL JDBC Driver)
          |
          v
Database server
~~~

Các thành phần trong sơ đồ đảm nhiệm những việc khác nhau:

| Thành phần | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| `DataSource` | API cung cấp `java.sql.Connection` cho mã truy cập dữ liệu | Nó là điểm lấy kết nối, không phải bản thân một kết nối. |
| `Connection` | Phiên giao tiếp JDBC với database, dùng để chạy SQL và quản lý transaction | Khi được lấy từ pool, đối tượng trả về thường là một *proxy* của kết nối vật lý. |
| Connection pool | Giữ và tái sử dụng các kết nối vật lý; giới hạn số kết nối có thể được mượn đồng thời | Pool giảm chi phí tạo kết nối mới, nhưng không làm SQL chạy nhanh hơn một cách trực tiếp. |
| JDBC Driver | Biến thao tác JDBC thành giao thức trao đổi với hệ quản trị cơ sở dữ liệu | Driver phụ thuộc loại database, chẳng hạn PostgreSQL hoặc MySQL. |
| `JdbcClient` / `JdbcTemplate` | Cung cấp API thực thi SQL, bind tham số và xử lý tài nguyên JDBC | Thường tự lấy và trả kết nối theo ngữ cảnh transaction của Spring. |
| Spring Data JDBC Repository | Ánh xạ aggregate và cung cấp các thao tác repository theo mô hình Spring Data | Sử dụng hạ tầng Spring JDBC ở bên dưới; không phải JPA/ORM có persistence context. |

Ví dụ, lời gọi `orderRepository.findById(42L)` có thể dẫn tới một hoặc nhiều câu SQL tùy cấu trúc aggregate và cách Spring Data JDBC tải dữ liệu. Repository giúp lập trình thuận tiện, nhưng **không loại bỏ chi phí giao tiếp với database**.

## 2. DataSource là gì?

`javax.sql.DataSource` là interface chuẩn JDBC, cung cấp phương thức trọng tâm:

~~~java
Connection connection = dataSource.getConnection();
~~~

`DataSource` tách mã truy cập dữ liệu khỏi việc tự xây URL, cấu hình driver, mở TCP socket và xác thực với database. Trong Spring Boot, cấu hình `spring.datasource.*` giúp framework tạo và quản lý một `DataSource` để repository, JDBC client và transaction manager cùng sử dụng.

Nếu `DataSource` không có pool, mỗi lần lấy kết nối có thể phải thiết lập một phiên vật lý mới. Với `HikariDataSource`, `getConnection()` thường là thao tác **mượn** một kết nối đã có trong pool; khi cần và chưa chạm giới hạn, pool có thể tạo thêm kết nối vật lý.

Điểm quan trọng là phân biệt hai lớp:

- **Kết nối vật lý:** phiên làm việc thực sự giữa tiến trình ứng dụng và database, tiêu thụ tài nguyên ở cả hai phía.
- **Kết nối được mượn:** đối tượng `Connection` mà code đang nắm giữ; với connection pool, thường là wrapper/proxy đại diện cho phiên vật lý đó.

Vì vậy, một ứng dụng có thể xử lý hàng nghìn lời gọi repository trong một phút nhưng chỉ duy trì một số lượng kết nối vật lý nhỏ hơn rất nhiều.

### Điều gì xảy ra khi gọi `close()`?

Với kết nối trực tiếp không qua pool, `close()` thường đóng phiên vật lý. Với kết nối mượn từ HikariCP, `close()` thông thường **trả kết nối về pool** để request khác tái sử dụng. Pool sẽ thực sự đóng kết nối vật lý khi nó hết hạn, hỏng, bị loại bỏ hoặc khi pool dừng.

Điều đó không làm `close()` trở nên tùy chọn: quên trả kết nối khiến pool cạn, dù database vẫn còn khả năng xử lý SQL.

Khi phải dùng JDBC thủ công bên ngoài transaction do Spring quản lý, dùng `try-with-resources`:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "SELECT COUNT(*) FROM orders WHERE customer_id = ?")) {

    statement.setLong(1, customerId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            long count = resultSet.getLong(1);
            // Sử dụng count.
        }
    }
}
~~~

Trong code nghiệp vụ Spring, thường nên dùng `JdbcClient`, `JdbcTemplate` hoặc Spring Data JDBC Repository để framework xử lý việc lấy/trả kết nối và tham gia transaction. **Không tùy tiện gọi `dataSource.getConnection()` bên trong phương thức `@Transactional`**: thao tác đó không mặc nhiên bảo đảm dùng đúng kết nối đang gắn với transaction của Spring. Nếu thật sự cần API JDBC cấp thấp trong transaction, hãy dùng cơ chế do Spring hỗ trợ như `DataSourceUtils`.

## 3. Vòng đời mượn và trả kết nối

Không có transaction bao trùm, một thao tác truy cập dữ liệu thường diễn ra theo trình tự:

1. Repository hoặc JDBC client yêu cầu một `Connection` thông qua hạ tầng Spring JDBC.
2. Pool tìm kết nối rảnh. Nếu chưa có và được phép mở thêm, pool có thể tạo kết nối vật lý; nếu tất cả đang bận, lời gọi phải đợi.
3. JDBC driver gửi SQL cùng tham số đến database.
4. Database phân tích, lập kế hoạch/thực thi SQL và gửi kết quả hoặc số hàng bị ảnh hưởng trở lại.
5. Spring ánh xạ kết quả thành đối tượng Java và đóng tài nguyên JDBC.
6. Kết nối được trả về pool để lượt truy cập sau có thể mượn lại.

Minh họa với pool tối đa ba kết nối:

~~~text
Thời điểm T1
  Request A ---- mượn C1 ---- đang chạy SQL
  Request B ---- mượn C2 ---- đang chạy SQL
  Request C ---- mượn C3 ---- đang chạy SQL
  Request D ---- đợi một kết nối rảnh

Thời điểm T2
  Request B ---- trả C2
  Request D ---- mượn C2 ---- chạy SQL
~~~

Trong thời gian đợi, Request D không chiếm thêm kết nối database. Nếu đợi lâu hơn `connectionTimeout` của pool, việc mượn kết nối thất bại và ứng dụng nhận exception. Điều đó **khác** với câu SQL đã chạy nhưng vượt quá thời gian thực thi.

### Một transaction có thể giữ kết nối lâu hơn một câu SQL

Với Spring JDBC và transaction manager thông dụng, Spring gắn một kết nối với thread đang thực thi transaction để nhiều thao tác JDBC cùng tham gia transaction đó. Kết nối thường được lấy ở đầu transaction hoặc khi lần đầu thực sự cần, tùy cấu hình. Nó được trả về pool sau khi transaction kết thúc.

~~~text
@Transactional bắt đầu
  |
  +-- UPDATE tài khoản A
  +-- UPDATE tài khoản B
  +-- COMMIT (hoặc ROLLBACK)
  |
@Transactional kết thúc -> trả connection
~~~

Lợi ích: các câu SQL liên quan có thể tuân theo cùng một ranh giới commit/rollback. Đổi lại, transaction kéo dài khiến kết nối bị giữ lâu hơn và có thể tăng thời gian giữ khóa trong database.

## 4. Chi phí truy cập database đến từ đâu?

Thời gian của một thao tác truy cập dữ liệu không chỉ là thời gian database xử lý câu SQL:

| Thành phần thời gian | Ví dụ nguyên nhân |
| --- | --- |
| Chờ kết nối từ pool | Tất cả kết nối đang được mượn; một số transaction giữ kết nối quá lâu. |
| Thiết lập kết nối mới | TCP handshake, TLS, xác thực, khởi tạo session, hoặc DNS/network. |
| Gửi yêu cầu và nhận kết quả | Độ trễ mạng, nhiều lượt trao đổi, payload kết quả lớn. |
| Xử lý SQL trên database | Parse/plan, quét bảng/index, join, sort, aggregate, đọc/ghi bộ nhớ và đĩa. |
| Chờ tài nguyên và khóa | Lock contention, transaction khác chưa commit, giới hạn CPU/I/O. |
| Chuyển kết quả thành đối tượng | Đọc `ResultSet`, chuyển kiểu dữ liệu, ánh xạ entity/aggregate. |
| Kết thúc transaction | Gửi `COMMIT` hoặc `ROLLBACK`, đồng bộ log theo chính sách độ bền dữ liệu. |

Có thể hình dung:

~~~text
Tổng thời gian thao tác
  ≈ thời gian chờ pool
  + thời gian truyền nhận
  + thời gian thực thi/chờ tại database
  + thời gian ánh xạ dữ liệu
  + chi phí transaction
~~~

Đây là mô hình suy nghĩ, không phải công thức cộng tuyệt đối cho mọi driver: một số giai đoạn có thể chồng lấn, và thao tác có thể tái sử dụng kết nối đang gắn với transaction.

### Vì sao nhiều truy vấn nhỏ có thể đắt?

Giả sử minh họa một lần trao đổi với database mất 3 ms truyền nhận và câu SQL mất 2 ms thực thi:

- Một truy vấn: khoảng `3 + 2 = 5 ms`, chưa kể chờ pool/ánh xạ.
- Một trăm truy vấn chạy tuần tự: khoảng `100 × 5 = 500 ms`.

Số đo này **chỉ để minh họa phép cộng chi phí**, không phải tốc độ mặc định của JDBC hay một hệ quản trị database cụ thể.

Một vòng lặp gọi repository cho từng phần tử có thể tạo hàng chục hoặc hàng trăm lượt round-trip:

~~~java
for (Long orderId : orderIds) {
    Order order = orderRepository.findById(orderId).orElseThrow();
    process(order);
}
~~~

Nếu nghiệp vụ cho phép, truy vấn theo tập ID, xử lý theo lô hoặc thiết kế lại cách đọc aggregate thường tiết kiệm nhiều round-trip hơn việc tăng số kết nối. Với Spring Data JDBC, một lần tải aggregate chứa các collection con cũng có thể cần nhiều câu SQL; cần quan sát SQL thực tế thay vì mặc định cho rằng mỗi lời gọi repository luôn tương ứng đúng một truy vấn.

### Phân biệt độ trễ và thông lượng

- **Latency (độ trễ):** một thao tác chờ bao lâu để có kết quả. Người dùng thường cảm nhận qua thời gian phản hồi.
- **Throughput (thông lượng):** hệ thống hoàn thành được bao nhiêu thao tác trong một đơn vị thời gian.
- **Concurrency (mức đồng thời):** có bao nhiêu thao tác đang chạy hoặc đang chờ tại cùng thời điểm.

Pool lớn hơn có thể cho phép nhiều câu SQL chạy đồng thời, nhưng nếu database đã bão hòa CPU, I/O hoặc khóa, độ trễ lại có thể tăng do tranh chấp. Thêm kết nối không làm CPU và IOPS của database tự tăng.

## 5. Connection pool giải quyết vấn đề gì?

Không có tái sử dụng kết nối, mỗi request có thể phải chịu chi phí khởi tạo một kết nối vật lý. Pool duy trì các kết nối để giảm chi phí đó, tái sử dụng tài nguyên và giới hạn số lượng kết nối gửi vào database.

Ba khái niệm cốt lõi:

- **Active:** số kết nối hiện được ứng dụng mượn.
- **Idle:** số kết nối có trong pool nhưng đang rảnh.
- **Pending:** số lời gọi đang đợi được mượn kết nối (không phải là số kết nối vật lý).

Thông thường `active + idle = total` và `total ≤ maximumPoolSize`. Khi `active` chạm giới hạn và không có kết nối rảnh, request mới phải chờ đến lúc một kết nối được trả hoặc đến khi hết timeout.

Pool cũng kiểm tra khả năng dùng của kết nối, loại bỏ kết nối hỏng/hết tuổi, và có thể khởi tạo kết nối mới để thay thế. Những cơ chế này giúp vận hành ổn định hơn, nhưng không thay thế việc xử lý lỗi mất kết nối hoặc thiết kế retry có kiểm soát ở tầng ứng dụng.

### Connection pool khác với thread pool

Một server có 200 thread xử lý HTTP không nhất thiết phải có 200 kết nối database. Nhiều request dành thời gian cho validate dữ liệu, serialize JSON, gọi service khác hoặc xử lý trong bộ nhớ. Ngược lại, 20 kết nối database không có nghĩa database chỉ thực hiện được 20 SQL mỗi giây: mỗi kết nối có thể hoàn thành rất nhiều SQL liên tiếp.

Đừng lấy số thread HTTP làm kích thước connection pool theo tỉ lệ 1:1.

## 6. Cấu hình DataSource và HikariCP trong Spring Boot

Ứng dụng có `spring-boot-starter-data-jdbc` và JDBC driver phù hợp thường được Spring Boot tự cấu hình `DataSource`; khi HikariCP có trên classpath và không bị cấu hình khác thay thế, HikariCP là pool mặc định phổ biến.

Ví dụ cấu hình PostgreSQL:

~~~yaml
spring:
  datasource:
    url: ${DB_URL:jdbc:postgresql://localhost:5432/shop}
    username: ${DB_USER:shop_app}
    password: ${DB_PASSWORD}
    hikari:
      pool-name: shop-jdbc-pool
      maximum-pool-size: 12
      connection-timeout: 3000
      validation-timeout: 1000
      max-lifetime: 1500000
~~~

Đây là **ví dụ cú pháp**, không phải bộ thông số tối ưu cho mọi hệ thống. Biến `DB_PASSWORD` phải được cung cấp từ môi trường hoặc cơ chế quản lý secret phù hợp; tránh commit mật khẩu thật vào repository. Đơn vị các giá trị Hikari trên là mili giây.

| Cấu hình Hikari | Tác dụng | Cách hiểu đúng |
| --- | --- | --- |
| `maximum-pool-size` | Giới hạn số kết nối vật lý trong một instance pool | Không phải số kết nối tối thiểu và cũng không phải số SQL mỗi giây. |
| `connection-timeout` | Thời gian tối đa chờ mượn một kết nối trước khi báo lỗi | Không giới hạn thời gian chạy SQL trên database. |
| `minimum-idle` | Mức kết nối rảnh pool cố gắng duy trì | Nếu không đặt, Hikari thường vận hành như pool kích thước cố định với mức idle mục tiêu bằng max. |
| `idle-timeout` | Thời gian một kết nối rảnh có thể bị thu hồi khi pool được phép co nhỏ | Chủ yếu có ý nghĩa khi `minimum-idle` nhỏ hơn `maximum-pool-size`. |
| `max-lifetime` | Giới hạn vòng đời tối đa dự kiến của kết nối vật lý | Nên ngắn hơn giới hạn tuổi kết nối của database/proxy/network; không đóng cưỡng bức kết nối đang được mượn. |
| `keepalive-time` | Kiểm tra kết nối đang rảnh theo chu kỳ phù hợp để hạn chế bị hạ tầng cắt ngầm | Chỉ dùng khi cần và cấu hình tương thích với `max-lifetime`. |
| `validation-timeout` | Giới hạn thời gian kiểm tra một kết nối còn dùng được | Phải nhỏ hơn `connection-timeout`. |
| `leak-detection-threshold` | Ghi log nghi vấn kết nối bị giữ lâu hơn ngưỡng | Là tín hiệu điều tra, không tự thu hồi kết nối; transaction chậm có thể gây cảnh báo giả. |

Không cần đặt mọi tham số chỉ vì Hikari có hỗ trợ. Hãy bắt đầu từ cấu hình đơn giản, đo tải thực tế rồi điều chỉnh khi có bằng chứng. Thời gian tạo TCP connection (driver/network), timeout chờ pool, timeout câu SQL và timeout transaction là những khái niệm độc lập; cần xử lý riêng tùy hệ quản trị và driver.

### Transaction và câu SQL có timeout riêng

Ví dụ:

- `connection-timeout: 3000`: nếu không mượn được connection sau tối đa khoảng 3 giây, Hikari báo lỗi.
- Driver `connectTimeout`: giới hạn thời gian mở kết nối vật lý tới database, tùy driver.
- `Statement.setQueryTimeout(...)`, timeout của template, hoặc cơ chế `statement_timeout` phía database: liên quan tới thời gian thực thi câu SQL.
- `@Transactional(timeout = ...)`: khai báo giới hạn thời gian transaction cho hạ tầng Spring, nhưng cách timeout được áp dụng/phát hiện phụ thuộc transaction manager và thao tác JDBC. Không nên coi đây là cơ chế bảo đảm database luôn hủy ngay mọi truy vấn quá hạn.

Khi phân tích log, phải biết **timeout ở lớp nào** trước khi quyết định tăng pool.

## 7. Chọn kích thước pool dựa trên tải và giới hạn database

Kích thước pool cần cân bằng ba điều: mức truy cập đồng thời thực tế, khả năng xử lý của database và giới hạn tổng kết nối trên **tất cả instance** ứng dụng.

Một ước lượng ban đầu dựa trên quan hệ Little:

~~~text
Số kết nối đang được giữ trung bình
  ≈ số lượt mượn kết nối mỗi giây × thời gian giữ kết nối trung bình (giây)
~~~

Ví dụ hệ thống có trung bình 200 lượt mượn kết nối/giây, mỗi lượt giữ 30 ms:

~~~text
200 × 0,030 = 6 kết nối đang được giữ trung bình
~~~

Con số 6 **không** đồng nghĩa nên đặt pool bằng 6. Tải tăng đột biến, phân phối thời gian giữ kết nối, transaction dài, CPU/IO của database và độ trễ mục tiêu đều ảnh hưởng đến kích thước cần thiết. Đây là điểm bắt đầu để đo và thử tải.

Điều đáng chú ý là phải dùng **thời gian giữ connection**, không lấy toàn bộ thời gian HTTP request làm đại diện nếu request còn làm công việc khác ngoài database.

### Tính giới hạn theo số bản sao ứng dụng

Giả sử có bốn replica, mỗi replica cấu hình `maximum-pool-size: 15`:

~~~text
Số kết nối ứng dụng có thể mở tối đa = 4 × 15 = 60
~~~

Nếu database cho phép 80 kết nối, vẫn cần dành chỗ cho job chạy nền, migration, công cụ quản trị, dịch vụ khác và kết nối dự phòng. Nếu hệ thống có nhiều loại pool, phải cộng tất cả. Công thức kiểm tra ngân sách:

~~~text
Tổng (số instance của từng dịch vụ × maximumPoolSize của dịch vụ đó)
    + kết nối từ các thành phần khác
    + phần dự phòng
  ≤ giới hạn kết nối database cho phép
~~~

Khi dùng proxy hoặc pool phía database như PgBouncer, cần tính thêm chính sách và giới hạn của tầng trung gian đó. Một pool quá lớn ở từng replica có thể khiến database vượt `max_connections` ngay khi ứng dụng scale-out.

### Vì sao tăng pool có thể làm hệ thống chậm hơn?

Giả sử database đủ tài nguyên chạy hiệu quả 12 truy vấn nặng cùng lúc. Cho phép 80 truy vấn nặng đồng thời có thể tạo hàng đợi ở CPU, buffer, disk hoặc lock, làm từng truy vấn lâu hơn. Kết nối bị giữ lâu hơn lại khiến nhiều request phải chờ pool, tạo vòng lặp xấu.

Do đó, cách tăng thông lượng bền vững thường là giảm thời gian thực thi và thời gian giữ connection trước, rồi mới cân chỉnh mức đồng thời phù hợp.

## 8. `@Transactional` và thời gian giữ kết nối

Trong Spring Data JDBC, transaction thường được quản lý qua `PlatformTransactionManager` phù hợp với JDBC, chẳng hạn `JdbcTransactionManager` hoặc `DataSourceTransactionManager`. Lời gọi từ repository hay Spring JDBC trong cùng transaction tham gia vào ranh giới commit/rollback do Spring quản lý.

Ví dụ một service chuyển tiền minh họa việc hai câu `UPDATE` cần thành công hoặc thất bại cùng nhau:

~~~java
import java.math.BigDecimal;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final JdbcClient jdbcClient;

    public TransferService(JdbcClient jdbcClient) {
        this.jdbcClient = jdbcClient;
    }

    @Transactional
    public void transfer(long fromId, long toId, BigDecimal amount) {
        if (fromId == toId || amount.signum() <= 0) {
            throw new IllegalArgumentException("Thông tin chuyển tiền không hợp lệ");
        }

        int debited = jdbcClient.sql("""
                UPDATE account
                   SET balance = balance - :amount
                 WHERE id = :fromId AND balance >= :amount
                """)
                .param("amount", amount)
                .param("fromId", fromId)
                .update();
        if (debited != 1) {
            throw new IllegalStateException("Tài khoản nguồn không tồn tại hoặc thiếu tiền");
        }

        int credited = jdbcClient.sql("""
                UPDATE account
                   SET balance = balance + :amount
                 WHERE id = :toId
                """)
                .param("amount", amount)
                .param("toId", toId)
                .update();
        if (credited != 1) {
            throw new IllegalStateException("Tài khoản đích không tồn tại");
        }
    }
}
~~~

Ví dụ giả định bảng `account(id, balance)` dùng kiểu dữ liệu tiền tệ có độ chính xác thích hợp, và service được gọi qua bean Spring để `@Transactional` có hiệu lực. Kiểm tra số hàng bị ảnh hưởng giúp phát hiện lỗi nghiệp vụ. Theo quy tắc rollback mặc định của Spring với unchecked exception, nếu thao tác thứ hai lỗi, thay đổi trước đó cũng rollback. Trong hệ thống chuyển tiền thực tế còn cần xử lý đồng thời, deadlock/retry an toàn, audit và các quy tắc nghiệp vụ khác.

**Điểm hiệu năng:** một transaction như trên thường giữ kết nối xuyên suốt hai `UPDATE`. Đây là điều cần thiết cho tính nguyên tử, nhưng phạm vi transaction nên ngắn:

~~~java
// Không nên: giữ transaction database trong lúc chờ dịch vụ bên ngoài.
@Transactional
public void placeOrder(OrderCommand command) {
    orderRepository.save(command.toOrder());
    externalPaymentClient.charge(command.payment()); // có thể mất vài giây
}
~~~

Trong thiết kế thật, việc thanh toán ngoài database thường cần quy trình tách bước, trạng thái trung gian hoặc outbox/saga phù hợp. Không đưa call mạng chậm vào transaction JDBC chỉ để tiện viết code.

Các lưu ý thêm:

- `@Transactional(readOnly = true)` thể hiện ý định đọc và có thể cung cấp hint tối ưu; không nên xem là cơ chế phân quyền hoặc chặn ghi tuyệt đối ở mọi database.
- Transaction do Spring quản lý thường gắn với **thread hiện tại**. Tự chuyển sang thread khác hoặc dùng API bất đồng bộ có thể làm mất ngữ cảnh transaction.
- Tự gọi một phương thức `@Transactional` khác trong cùng đối tượng có thể bỏ qua proxy Spring; ranh giới transaction không tự động xuất hiện như mong đợi.
- Spring Data JDBC không dùng cơ chế giữ `EntityManager` và lazy-loading session như JPA. Dù vậy, transaction dài và số truy vấn sinh ra khi tải/lưu aggregate vẫn ảnh hưởng trực tiếp đến pool.

## 9. Cách giảm chi phí truy cập database

Tối ưu hiệu năng JDBC bắt đầu bằng số lượt round-trip và chất lượng SQL, sau đó mới đến tham số của pool.

### 9.1. Giảm số câu SQL không cần thiết

Thay vì truy vấn một bản ghi cho mỗi ID trong vòng lặp, cân nhắc truy vấn theo tập hoặc cách đọc được thiết kế cho màn hình báo cáo:

~~~sql
SELECT id, customer_id, total_amount
FROM orders
WHERE id IN (?, ?, ?, ?);
~~~

Sử dụng tham số bind qua JDBC thay vì ghép chuỗi từ input. Nếu tập ID lớn, phải chia lô hợp lý và cân nhắc giới hạn của database/driver. Với Spring Data JDBC, cũng cần hiểu thao tác `save`/`saveAll` trên aggregate có thể kéo theo nhiều câu lệnh; tên phương thức không bảo đảm JDBC batching thực sự.

### 9.2. Chỉ lấy dữ liệu cần dùng

`SELECT *` có thể truyền nhiều cột không phục vụ tính năng. Với trang danh sách, dùng projection/DTO hoặc truy vấn JDBC được thiết kế cho dữ liệu hiển thị; giới hạn số dòng và phân trang khi phù hợp. Result set quá lớn tăng chi phí mạng, mapping và bộ nhớ.

### 9.3. Thiết kế index đúng theo cách lọc và sắp xếp

Ví dụ truy vấn thường xuyên:

~~~sql
SELECT id, created_at, status
FROM orders
WHERE customer_id = ?
ORDER BY created_at DESC
LIMIT 20;
~~~

Trên PostgreSQL, index như sau có thể hỗ trợ mẫu truy vấn đó:

~~~sql
CREATE INDEX idx_orders_customer_created
    ON orders (customer_id, created_at DESC);
~~~

Index có chi phí lưu trữ và bảo trì khi ghi; không nên thêm theo cảm tính. Đọc execution plan bằng `EXPLAIN` (hoặc `EXPLAIN ANALYZE` trên môi trường phù hợp) để biết database có dùng index và truy vấn chậm ở đâu. Lưu ý `EXPLAIN ANALYZE` thực thi câu lệnh thật; cần thận trọng đặc biệt với thao tác ghi.

### 9.4. Batch khi có nhiều thao tác tương tự

`JdbcTemplate.batchUpdate(...)` có thể giúp giảm số lượt gọi JDBC và cho phép driver tối ưu việc gửi lệnh, tùy driver và cấu hình. Batch không đồng nghĩa mọi database sẽ xử lý tất cả dữ liệu trong một phép toán duy nhất. Cần đo SQL thực tế, số round-trip, thời gian khóa và kích thước lô.

### 9.5. Giữ transaction ngắn, đóng tài nguyên sớm

Chỉ đưa vào transaction những bước cần cùng tính nguyên tử. Tránh xử lý file lớn, gọi mạng hoặc chờ người dùng trong transaction. Với kết quả lớn được stream, kết nối có thể phải giữ cho đến khi stream được đọc hết và đóng đúng cách; cân nhắc phân trang/chia lô nếu phù hợp.

## 10. Quan sát và chẩn đoán pool bị nghẽn

Trong Spring Boot, có thể dùng Actuator/Micrometer để quan sát số kết nối Hikari nếu đã tích hợp metrics. Những tên metric thường gặp gồm:

- `hikaricp.connections.active`: số connection đang được mượn.
- `hikaricp.connections.idle`: số connection rảnh.
- `hikaricp.connections.pending`: số lượt đang chờ.
- `hikaricp.connections.max`: giới hạn tối đa của pool.
- `hikaricp.connections.acquire`: thời gian mượn connection.
- `hikaricp.connections.usage`: thời gian một connection được giữ.
- `hikaricp.connections.timeout`: số lần mượn connection bị timeout.

Tên và mức độ sẵn có phụ thuộc phiên bản/cấu hình metrics. Nên đối chiếu metric của chính ứng dụng cùng số liệu phía database: active sessions, slow queries, lock waits, CPU, I/O và giới hạn số kết nối.

| Dấu hiệu | Giả thuyết cần kiểm tra | Bước điều tra hữu ích |
| --- | --- | --- |
| `active` gần `max`, `pending` tăng | Pool bị chiếm hết hoặc transaction giữ kết nối lâu | Xem thời gian `usage`, SQL chậm, transaction scope và concurrency. |
| `acquire` tăng, xuất hiện connection timeout | Request chờ pool quá lâu | Kiểm tra số truy vấn, thời gian giữ connection và saturation của database trước khi tăng max. |
| SQL chậm nhưng `pending` gần 0 | Nút thắt có thể nằm ở execution plan, khóa, network hoặc database | Phân tích slow query, `EXPLAIN`, CPU/I/O và lock waits. |
| Database báo “too many connections” | Tổng pool của các replica/dịch vụ vượt ngân sách | Tính tổng `replica × maximumPoolSize` cùng các kết nối khác. |
| `active` không giảm sau khi tải ngừng | Kết nối rò rỉ hoặc transaction/tác vụ chưa kết thúc | Tìm JDBC thủ công thiếu `close()`, stream chưa đóng, transaction treo và thread dump khi cần. |
| Số timeout tăng sau khi tăng pool | Database có thể đã bị quá tải vì đồng thời cao hơn | So sánh SQL latency, lock waits, CPU và throughput trước/sau. |

Một lỗi “connection is not available, request timed out” từ Hikari thường nói rằng **không mượn được kết nối đúng hạn**. Nó không chứng minh database đã chết, cũng không đủ để kết luận phải tăng `maximumPoolSize`.

### Trình tự tìm nguyên nhân khi request chậm

1. Đo latency của request và xác định thời gian có bao nhiêu phần dành cho truy cập dữ liệu.
2. Kiểm tra thời gian chờ pool (`acquire`/`pending`) và thời gian giữ connection (`usage`).
3. Đếm SQL trên mỗi request, tìm các vòng lặp truy vấn và các thao tác aggregate phát sinh nhiều câu SQL.
4. Nếu SQL chậm, kiểm tra execution plan, index, dữ liệu đọc/ghi, khóa và tài nguyên database.
5. Nếu pool thường xuyên chật, xác minh transaction có đang giữ connection trong khi thực hiện công việc không liên quan đến database.
6. Sau khi xử lý nguyên nhân lớn, thử tải với mức concurrency phù hợp và điều chỉnh pool trong giới hạn tổng kết nối của database.

## 11. Những hiểu nhầm thường gặp

| Nhận định | Thực tế |
| --- | --- |
| “Mỗi lần gọi Repository đều mở một TCP connection mới.” | Với pool, lời gọi thường mượn lại kết nối vật lý hiện có; nhiều thao tác trong một transaction có thể dùng chung kết nối. |
| “Cấu hình 100 connections sẽ làm SQL nhanh gấp 10 lần so với 10 connections.” | Pool tăng mức đồng thời tối đa; tốc độ một SQL và sức chịu tải của database vẫn phụ thuộc các tài nguyên khác. |
| “`close()` làm kết nối vật lý mất đi nên không cần gọi.” | Với pool, `close()` thường trả kết nối để tái sử dụng; bỏ qua có thể gây cạn pool. |
| “`connection-timeout` kiểm soát SQL chậm.” | Đây là timeout chờ mượn connection; timeout thực thi SQL cần cơ chế khác. |
| “Gọi `saveAll` chắc chắn gửi một câu SQL duy nhất.” | Spring Data JDBC có thể sinh nhiều câu SQL cho nhiều entity/aggregate; cần xem hành vi thực tế và dùng batch thích hợp khi cần. |
| “`@Transactional` giúp nhanh hơn trong mọi trường hợp.” | Transaction bảo đảm ranh giới nhất quán; nếu quá rộng, nó làm kết nối và khóa bị giữ lâu, tăng tranh chấp. |
| “Hết connection chỉ cần tăng max pool.” | Cần xác định SQL chậm, transaction dài, leak, tải tăng hoặc database quá khả năng trước khi điều chỉnh. |

## 12. Tình huống thực hành để tự kiểm tra cách hiểu

Giả sử một ứng dụng có 3 replica, mỗi replica dùng HikariCP `maximum-pool-size: 10`. Mỗi replica có 40 request đang xử lý. Database cho phép tối đa 60 connection cho toàn hệ thống.

**Câu hỏi 1.** Có nhất thiết phải có 120 kết nối database hay không?

Không. 40 request trên một replica không đồng nghĩa 40 request đều đang giữ connection. Tổng số connection vật lý mà ba pool có thể mở tối đa theo cấu hình là `3 × 10 = 30`, nếu không có pool khác.

**Câu hỏi 2.** Nếu có 11 request trên cùng replica đồng thời cần chạy SQL và cả 10 connection đã được mượn thì chuyện gì xảy ra?

Request thứ 11 phải chờ một connection được trả. Nếu chờ quá `connection-timeout`, nó thất bại ở bước mượn connection.

**Câu hỏi 3.** Tại sao giữ transaction mở trong lúc gọi API thanh toán 2 giây là nguy hiểm?

Connection và có thể cả khóa database tiếp tục bị giữ trong lúc ứng dụng chờ mạng. Số connection khả dụng giảm; các request còn lại phải chờ và có nguy cơ timeout, dù thời gian chạy SQL thật sự rất ngắn.

**Câu hỏi 4.** Nếu một endpoint chạy 150 SQL nhỏ tuần tự, nên thử gì trước khi tăng pool?

Đếm và nhóm các truy vấn theo nghiệp vụ; cân nhắc truy vấn theo tập, projection, batch, index và thay đổi cách đọc aggregate để giảm lượt round-trip. Sau đó đo lại thời gian SQL, connection usage và pool wait.

## Ghi nhớ khi xây dựng ứng dụng Spring Data JDBC

`DataSource` là nơi lấy kết nối, pool tái sử dụng kết nối vật lý, còn Spring JDBC và Spring Data JDBC là các lớp thực thi thao tác dữ liệu ở phía ứng dụng. Một kết nối được mượn là tài nguyên hữu hạn: hãy trả sớm, giữ transaction gọn và hạn chế các truy vấn lặp. Để tối ưu hệ thống, phải nhìn đồng thời **số câu SQL, thời gian thực thi, thời gian giữ connection, thời gian chờ pool và năng lực database**.
