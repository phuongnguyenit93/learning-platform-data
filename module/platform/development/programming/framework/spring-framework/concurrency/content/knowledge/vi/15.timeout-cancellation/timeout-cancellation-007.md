# Đặt timeout riêng cho truy cập cơ sở dữ liệu hoặc lời gọi mạng

> **Module:** Spring Framework – concurrency  
> **Chủ đề cha:** Hết hạn và hủy  
> **Mục tiêu:** Hiểu vì sao timeout của `Future`, `CompletableFuture`, `@Async` hoặc HTTP request đầu vào **không thay thế timeout của thao tác I/O**; thiết kế timeout riêng khi lấy connection, chạy SQL và gọi HTTP; phối hợp với deadline tổng, hủy tác vụ, transaction, retry và giám sát trong ứng dụng Spring.

## 1. Quy tắc quan trọng nhất: đặt timeout nơi đang chờ tài nguyên

Một endpoint hoặc `@Async` worker có thể đang chờ:

- Có worker trống trong thread pool, hoặc chờ job được lấy khỏi queue.
- Mượn `Connection` từ JDBC connection pool.
- Kết nối TCP/TLS đến database, gửi SQL, chờ query trả kết quả hoặc chờ đọc socket.
- Mở kết nối tới HTTP service, chờ phản hồi và đọc dữ liệu.
- Chờ một `CompletableFuture` hoàn thành ở phía caller.

Đây là **những điểm chờ khác nhau**. Đặt `future.orTimeout(2, TimeUnit.SECONDS)` chỉ làm thay đổi trạng thái quan sát của future khi hết hạn; nó không chứng minh JDBC statement hoặc HTTP request đang blocking đã bị dừng. Worker có thể vẫn giữ connection và tiếp tục thực hiện I/O trong khi caller đã nhận timeout.

**Nguyên tắc:** Đặt giới hạn ở lớp **thực thi thao tác thật** (JDBC driver/SQL statement, HTTP client, network stack), đồng thời đặt một **deadline end-to-end** ở lớp nghiệp vụ để không tiếp tục các bước vô ích sau hạn. Hai loại giới hạn bổ sung cho nhau, không thể dùng một cái thay mọi cái khác.

## 2. Sơ đồ các lớp timeout trong một công việc Spring

Ví dụ luồng lấy trạng thái đơn hàng từ DB rồi gọi một hệ thống khác:

~~~text
HTTP request / job handler -- [deadline nghiệp vụ tổng]
        |
        v
Spring @Async / ThreadPoolTaskExecutor
        |-- queue wait: task có thể chưa bắt đầu
        v
DataSource.getConnection()
        |-- connection-pool acquisition timeout
        |-- JDBC driver connect/login timeout khi phải tạo connection
        v
JdbcTemplate.query(...)
        |-- Statement / query timeout
        |-- JDBC socket read timeout
        |-- database-side statement/lock timeout (nếu cấu hình)
        v
HTTP client gọi service phụ thuộc
        |-- TCP connection timeout
        |-- response/request timeout
        |-- connection-pool acquisition, read/write/idle timeout tùy thư viện
        v
Xử lý kết quả và trả response
        |
        +-- Future/CompletableFuture timeout ở người chờ
~~~

**Một timeout không tự giới hạn tất cả các đoạn ở phía dưới.** Chẳng hạn `HikariCP.connectionTimeout=500ms` không có nghĩa một `SELECT` sau khi lấy được connection cũng chỉ chạy 500ms. Tương tự, `HttpClient.connectTimeout=400ms` chỉ giới hạn việc thiết lập **kết nối mới**, không phải toàn bộ thời gian server xử lý request và trả dữ liệu.

Đọc kết quả timeout cần xác định **cơ chế nào đã hết hạn**. Một lỗi đợi connection khác với SQL query timeout, và cả hai khác với remote HTTP timeout. Nếu không phân biệt, hệ thống có thể retry sai hoặc tăng pool size trong khi nguyên nhân thật nằm ở DB/server.

## 3. Chọn timeout theo ngân sách thời gian, không theo một con số duy nhất

Giả sử yêu cầu nghiệp vụ phải hoàn thành trong khoảng **3 giây**. Một cấu hình minh họa có thể dùng các ngân sách:

| Đoạn chờ | Ví dụ thời gian | Lớp cần áp |
| --- | ---: | --- |
| Mượn connection từ pool | 250 ms | HikariCP `connectionTimeout` |
| Thực thi SQL | 800 ms | JDBC `Statement.setQueryTimeout` (độ phân giải giây) hoặc database-side timeout phù hợp |
| Một HTTP call sau DB | 1.200 ms tổng | HTTP client request/response timeout; connect nằm **trong** budget HTTP |
| Phần còn lại | 750 ms | serialization, scheduling, logging, tải bất thường, sai số thời gian |

Các giá trị trên chỉ là **ví dụ tính ngân sách**, không phải cấu hình khuyến nghị áp dụng cứng. `Statement.setQueryTimeout` nhận **giây nguyên**, nên 800ms không thể truyền trực tiếp vào nó; nếu cần giới hạn dưới giây, phải dùng giải pháp DB/driver riêng hoặc thiết kế deadline phù hợp. Tài liệu từng driver quyết định độ phân giải và việc cancel thực tế.

Không cộng `connectTimeout` và request timeout như hai thời lượng độc lập nếu request timeout **đã bao trùm** giai đoạn thiết lập kết nối. Đồng thời, đừng đánh đồng tổng timeout cấu hình với một bảo đảm thời gian cứng: DNS, scheduler, rollback, driver và hệ thống bên ngoài có thể có hành vi khác.

Nên biểu diễn deadline tại mỗi yêu cầu bằng một **thời điểm hết hạn** (dùng monotonic clock khi đo duration trong cùng JVM). Trước mỗi bước còn lại, kiểm tra thời gian còn lại; không bắt đầu một lời gọi vốn không còn cơ hội hoàn tất hợp lệ.

## 4. JDBC: timeout lấy connection khác timeout thực thi SQL

Khi dùng Spring với `DataSource`/HikariCP, thường có nhiều giới hạn:

| Cơ chế | Kiểm soát | Không kiểm soát |
| --- | --- | --- |
| HikariCP `connectionTimeout` (ms) | Tối đa thời gian chờ **mượn** connection từ pool khi pool không thể cấp connection | Thời gian một câu SQL chạy sau khi mượn được |
| HikariCP `validationTimeout` (ms) | Thời gian kiểm tra connection còn sống trong quá trình validation | Timeout của câu query nghiệp vụ |
| JDBC driver connect/login timeout | Giai đoạn kết nối hoặc login đến DB, theo driver | Mọi SQL chạy trên connection đã thiết lập |
| JDBC `Statement.setQueryTimeout(seconds)` | Thời gian chờ statement thực thi theo JDBC và hỗ trợ driver | Thời gian đợi pool cấp connection trước đó |
| JDBC driver socket read timeout | Thời gian đọc socket khỏi DB theo driver (thường là khoảng chờ cho thao tác đọc) | Không nhất thiết tương đương query timeout hoặc transaction timeout |
| Database statement/lock timeout | Giới hạn do server DB áp dụng cho statement/lock theo engine | HTTP call xảy ra bên ngoài DB |
| Spring transaction timeout | Thời gian cho transaction khi transaction manager hỗ trợ và các thao tác tham gia được cấu hình đúng | Không phải công tắc tổng để hủy mọi HTTP/network operation |

Ví dụ: pool có 10 connection, 10 truy vấn dài chiếm hết. Task thứ 11 có thể chờ đến `connectionTimeout` rồi thất bại **chưa chạy một SQL nào**. Dù `JdbcTemplate.setQueryTimeout(2)`, giới hạn 2 giây của SQL không chữa thời gian chờ lấy connection.

Ngược lại, khi đã lấy được connection ngay nhưng một `SELECT` chạy lâu, timeout mượn pool không giới hạn truy vấn đó. Cần query/statement/server timeout.

## 5. HikariCP: đặt thời gian đợi connection trong Spring Boot

Nếu dự án dùng **Spring Boot + HikariCP**, có thể cấu hình pool acquisition timeout bằng thuộc tính Boot:

~~~yaml
spring:
  datasource:
    hikari:
      connection-timeout: 500
      validation-timeout: 400
      maximum-pool-size: 10
~~~

Các số theo **milliseconds**; đây là ví dụ dùng cho kiểm thử/ngữ cảnh latency thấp, không phải giá trị production nên áp dụng nguyên xi. Hikari yêu cầu `validationTimeout` thấp hơn `connectionTimeout` và cũng có ngưỡng tối thiểu. `maximum-pool-size` quyết định trần số connection đang được quản lý bởi pool; tăng mù quáng có thể chuyển nghẽn từ pool ứng dụng sang DB.

Khi một lời gọi `DataSource.getConnection()` không được phục vụ trong `connectionTimeout`, Hikari báo lỗi acquisition (thường là `SQLException`, được Spring dịch nếu đi qua abstraction tương ứng). Đây là **pool timeout**; không mặc định JDBC statement đã chạy hay DB vừa cancel query.

Cũng cần cấu hình **JDBC driver connect/login timeout** nếu việc tạo connection mới có thể treo lâu. `connectionTimeout` của pool và connect timeout của driver là hai chính sách khác nhau; tên tương tự không làm chúng đồng nhất.

Với Spring Framework không dùng Boot, các khóa `spring.datasource.hikari.*` không tự có hiệu lực. Bạn phải cấu hình `HikariDataSource` hoặc connection pool đang dùng qua cách cấu hình riêng của ứng dụng.

## 6. JDBC chuẩn: giới hạn chính truy vấn bằng Statement.setQueryTimeout

JDBC có `Statement.setQueryTimeout(int seconds)`, được `PreparedStatement` kế thừa. Nó áp thời gian chờ statement thực thi, tính theo **giây**. Driver được kỳ vọng nhận biết hết hạn và cố gắng hủy câu lệnh; nhưng thời điểm dừng thực tế, cách driver gửi cancel, trạng thái connection và kết quả side effect cần xem riêng theo driver/DB.

Đoạn JDBC minh họa (giả định có `DataSource dataSource` hợp lệ):

~~~java
String sql = "select status from orders where id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setQueryTimeout(2);  // 2 giây, chỉ cho statement này
    statement.setLong(1, orderId);

    try (ResultSet rs = statement.executeQuery()) {
        if (!rs.next()) {
            throw new IllegalStateException("Order not found");
        }
        return rs.getString(1);
    }
}
~~~

Đây là **đoạn ghép vào phương thức Java**, không phải chương trình độc lập; cần import `java.sql.Connection`, `PreparedStatement`, `ResultSet`, `DataSource` và biến `orderId`. `try-with-resources` đóng result set, statement và connection theo đường thành công hoặc lỗi.

Cần phân biệt:

1. `setQueryTimeout(2)` không bao gồm thời gian `dataSource.getConnection()` đã mất ở phía trên.
2. Nếu SQL timeout, JDBC có thể ném `SQLTimeoutException`; Spring JDBC thường chuyển các `SQLException` theo hệ thống `DataAccessException`. Không ràng buộc cứng ứng dụng vào một message exception cụ thể giữa nhiều driver.
3. Timeout thường **yêu cầu** hủy statement, không đồng nghĩa có thể hoàn tác mọi lệnh đã được DB thực thi, commit hoặc gửi side effect.
4. Timeout JDBC không thay thế network socket timeout: driver có thể cần chờ giao thức hủy hoặc mất kết nối, tùy implementation.
5. SQL batching, stream kết quả lớn và các phần đọc `ResultSet` có thể có phạm vi timeout khác nhau giữa driver. Hãy kiểm tra tài liệu và thử nghiệm DB thực tế.

Không dùng `Thread.interrupt()` hoặc `CompletableFuture.orTimeout()` như cách duy nhất giới hạn SQL blocking. Cơ chế driver/server mới là điểm chính để phát tín hiệu cancel/tránh chờ không có hạn.

## 7. Spring JdbcTemplate: cấu hình query timeout

Spring JDBC cung cấp `JdbcTemplate.setQueryTimeout(int)`. Mặc định của `JdbcTemplate` là **-1**: không áp một giá trị timeout cụ thể lên statement và để driver sử dụng mặc định. Khi đặt giá trị dương, `JdbcTemplate` cố gắng áp giới hạn khi tạo statement.

Một cấu hình Spring Framework dùng chung một template:

~~~java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration(proxyBeanMethods = false)
public class DatabaseTimeoutConfig {
    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        JdbcTemplate template = new JdbcTemplate(dataSource);
        template.setQueryTimeout(2); // giây
        return template;
    }
}
~~~

Đây là **đoạn cấu hình tích hợp Spring**, cần dependency `spring-jdbc` và bean `DataSource` được tạo trước đó. Khi một service dùng `JdbcTemplate` này để thực thi SQL, các statement do template quản lý chịu query timeout áp dụng, trừ khi có ràng buộc khác (đặc biệt timeout transaction).

Ví dụ service sử dụng:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderStatusReader {
    private final JdbcTemplate jdbc;

    public OrderStatusReader(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public String status(long orderId) {
        return jdbc.queryForObject(
            "select status from orders where id = ?",
            String.class,
            orderId);
    }
}
~~~

Đây là **ví dụ ghép vào project**, giả định DB có bảng `orders`, cột `id` và `status`; không thể chạy độc lập nếu không có datasource/schema. `queryForObject` cũng có thể báo lỗi không tìm thấy hoặc quá nhiều hàng, hoàn toàn khác với timeout; không gộp chúng thành cùng một loại retry.

**Điểm tinh tế:** Khi có transaction timeout đang hiệu lực, `JdbcTemplate` thông thường sử dụng **thời gian còn lại của transaction** để áp lên statement, thay thế giá trị query timeout riêng. Đừng viết quy tắc sai rằng hệ thống luôn tự chọn giá trị nhỏ nhất trong hai số do bạn khai báo. Hãy kiểm tra Spring transaction manager và hành vi thực tế.

## 8. Transaction timeout không phải một đồng hồ hủy mọi I/O

Spring có thuộc tính `@Transactional(timeout = n)` với **n tính bằng giây**, tùy transaction manager hỗ trợ. Trong JDBC với `DataSourceTransactionManager` (hoặc cấu hình tương đương), Spring có thể truyền thời gian còn lại của transaction vào statement do `JdbcTemplate` tạo.

~~~java
@Service
public class InventoryService {
    private final JdbcTemplate jdbc;

    public InventoryService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(timeout = 4, readOnly = true)
    public Integer available(long skuId) {
        return jdbc.queryForObject(
            "select quantity from inventory where sku_id = ?",
            Integer.class,
            skuId);
    }
}
~~~

Đoạn này cần import Spring JDBC, `@Transactional`, `@Service` và phải được gọi qua Spring transaction proxy; không phải project chạy một mình. Hành vi timeout chính xác phụ thuộc transaction manager, propagation hiện tại, JDBC driver và phạm vi transaction.

**Các hiểu nhầm cần tránh:**

- `@Transactional(timeout=4)` không bảo đảm một HTTP call thực hiện bên trong transaction cũng bị hủy sau bốn giây.
- Không phải mọi transaction manager đều áp deadline xuống mọi resource/driver giống nhau.
- Nếu method tham gia một transaction đã tồn tại, timeout của annotation mới không nhất thiết tạo đồng hồ mới; thuộc tính timeout được định nghĩa theo propagation và việc tạo transaction.
- Spring transaction timeout không thay thế thời gian đợi lấy connection từ pool hoặc socket timeout của driver trong mọi cấu hình.
- `@Transactional` ở method tự gọi bằng `this.method()` trong proxy mode có thể bị bỏ qua. Với `@Async`, transaction imperative cũng không tự đi từ caller thread sang async worker.

Nếu nghiệp vụ vừa dùng DB vừa gọi remote API, **không nên giữ transaction và DB connection mở suốt một lời gọi mạng chậm** trừ khi đã đánh giá kỹ. Làm như vậy có thể giữ lock/connection, đẩy pool vào nghẽn. Thường cần chia transaction boundary hoặc thiết kế outbox/saga phù hợp nghiệp vụ.

## 9. Driver và database cũng có timeout riêng

Cùng khái niệm JDBC nhưng driver triển khai chi tiết rất khác nhau. Với **PostgreSQL JDBC (pgJDBC)**, ví dụ các tham số URL thường gặp:

~~~text
jdbc:postgresql://db.example.invalid:5432/orders?connectTimeout=3&socketTimeout=8
~~~

Đây là **URL minh họa**, không phải địa chỉ DB thật và không kèm credentials. Trong pgJDBC, `connectTimeout` là giới hạn thiết lập socket tính bằng giây, còn `socketTimeout` là giới hạn socket read tính bằng giây. Driver cũng có `queryTimeout` dạng tham số mặc định khi statement không đặt timeout riêng.

Không lấy bảng đơn vị của pgJDBC rồi áp cho MySQL, SQL Server hoặc Oracle JDBC: một driver khác có thể dùng milliseconds, tên property khác hoặc cách hủy khác. Hãy chọn theo driver/version thực tế của dự án.

Phía **PostgreSQL server** còn có `statement_timeout` để giới hạn statement trực tiếp trên DB, và `lock_timeout` cho việc chờ lock. Ví dụ trong một transaction kiểm soát được:

~~~sql
BEGIN;
SET LOCAL statement_timeout = '2s';
SELECT status FROM orders WHERE id = 42;
COMMIT;
~~~

Đây là **SQL minh họa PostgreSQL**, cần bảng hợp lệ và quyền DB; không áp dụng nguyên xi trên database khác. `SET LOCAL` làm timeout có phạm vi transaction. Cần tránh thay đổi session-level setting rồi trả connection vào pool mà không quản lý reset đúng cách.

Timeout server mang lại một tầng bảo vệ khi caller/driver không còn chờ, nhưng không phải mọi thao tác đã có tác dụng phụ đều tự hoàn tác như ý định nghiệp vụ. Đối với ghi dữ liệu, thiết kế transaction và trạng thái commit là yếu tố quyết định.

## 10. HTTP: connect timeout không phải request/response timeout

Khi gọi dịch vụ qua mạng, cần phân biệt:

| Giới hạn | Ý nghĩa | Khi nào hữu ích |
| --- | --- | --- |
| Connect timeout | Thời gian thiết lập **kết nối mới** đến remote endpoint | Host không phản hồi TCP connect, firewall/drop |
| Connection pool acquisition timeout | Thời gian đợi một connection khả dụng từ **HTTP client connection pool**, nếu thư viện có pool | Client bị cạn connection dù remote còn hoạt động |
| Request/response timeout | Thời gian mong đợi remote trả response theo chính sách client | Server xử lý lâu hoặc response bị chậm |
| Socket read/idle timeout | Thời gian một thao tác đọc không có dữ liệu, tùy thư viện và transport | Đường truyền đứng hoặc streaming không có tiến triển |
| Total deadline | Thời điểm toàn nghiệp vụ phải hoàn tất | Tránh tiếp tục các bước sau khi kết quả đã hết giá trị |

Không phải HTTP client nào cũng có đầy đủ các thuộc tính trên hoặc cùng ý nghĩa. Đặc biệt, **read timeout không luôn là tổng thời gian của toàn response body**: nếu thư viện chỉ đo khoảng im lặng giữa các lần đọc, server gửi một byte định kỳ vẫn có thể làm tổng thời gian rất dài. Với streaming, cần thêm giới hạn tổng thời gian hoặc lượng dữ liệu nếu nghiệp vụ đòi hỏi.

Một kết nối đã được tái sử dụng thường **không trải qua connect mới**, nên chỉ đặt connect timeout không đủ bảo vệ khỏi remote xử lý chậm. Lệnh gọi có thể chờ response rất lâu dù kết nối đã tồn tại.

## 11. Java 17 HttpClient: cấu hình connect + request timeout riêng

JDK 17 hỗ trợ `java.net.http.HttpClient` và `HttpRequest`:

~~~java
HttpClient client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofMillis(500))
    .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.invalid/orders/42"))
    .timeout(Duration.ofSeconds(2))
    .GET()
    .build();

HttpResponse<String> response =
    client.send(request, HttpResponse.BodyHandlers.ofString());
~~~

Đây là **đoạn tích hợp**, cần import `HttpClient`, `HttpRequest`, `HttpResponse`, `URI`, `Duration`, đồng thời xử lý `IOException` và `InterruptedException`; hostname `example.invalid` chỉ dùng minh họa, không phải endpoint thật.

Cơ chế:

- `HttpClient.Builder.connectTimeout(Duration)` áp cho việc **thiết lập kết nối mới**. Nếu kết nối được reuse, timeout này không phải đồng hồ độc lập để giới hạn toàn response.
- `HttpRequest.Builder.timeout(Duration)` đặt timeout của **request**; trong API JDK 17, nếu response chưa nhận trong hạn, `HttpTimeoutException` xuất hiện ở `send` hoặc `sendAsync` hoàn tất ngoại lệ. Đây không đơn giản là “TCP socket read timeout”.
- `HttpConnectTimeoutException` là một subtype của `HttpTimeoutException`, cho phép phân loại lỗi kết nối so với lỗi phản hồi khi cần.
- Tất cả timeout Duration dùng ở đây phải là **giá trị dương**; đừng dùng `Duration.ZERO` với giả định đồng nghĩa vô hạn.
- Một remote HTTP server **có thể vẫn xử lý request** sau khi client timeout. Đặc biệt khi gửi POST/PUT có side effect, retry phải có idempotency key hoặc cơ chế kiểm tra kết quả.

Cấu hình này tốt hơn chỉ gọi `CompletableFuture.orTimeout` ở bên ngoài bởi giao thức HTTP client biết đến timeout của request thật. Dù vậy, cancellation và đóng connection cụ thể vẫn phụ thuộc transport, body handler, version và tình huống.

## 12. Ví dụ Java 17+ chạy độc lập: HTTP server cố tình trả lời chậm

Để quan sát timeout mà **không cần internet hay một server bên ngoài**, dùng HTTP server local của JDK. Server chậm 700ms trước khi gửi response; client đặt request timeout 120ms. Chương trình in một dòng xác định khi client phát hiện timeout.

Tạo file **NetworkTimeoutDemo.java**:

~~~java
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

public class NetworkTimeoutDemo {
    private static void slowResponse(HttpExchange exchange) {
        try {
            Thread.sleep(700);
            byte[] body = "ready".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, body.length);
            try (var output = exchange.getResponseBody()) {
                output.write(body);
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        } catch (IOException disconnected) {
            // Client may have timed out before this response was written.
        } finally {
            exchange.close();
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService serverWorkers = Executors.newSingleThreadExecutor();
        server.setExecutor(serverWorkers);
        server.createContext("/slow", NetworkTimeoutDemo::slowResponse);
        server.start();

        try {
            HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(300))
                .build();
            HttpRequest request = HttpRequest.newBuilder(
                    URI.create("http://127.0.0.1:"
                        + server.getAddress().getPort() + "/slow"))
                .timeout(Duration.ofMillis(120))
                .GET()
                .build();

            try {
                client.send(request, HttpResponse.BodyHandlers.ofString());
                System.out.println("Unexpected: request succeeded");
            } catch (HttpTimeoutException timeout) {
                System.out.println("HTTP request timed out");
            }
        } finally {
            server.stop(0);
            serverWorkers.shutdownNow();
        }
    }
}
~~~

Chạy trên **JDK 17+**:

~~~bash
javac NetworkTimeoutDemo.java
java NetworkTimeoutDemo
~~~

**Stdout khi máy cho phép khởi tạo server/client local bình thường**:

~~~text
HTTP request timed out
~~~

Demo đã được biên dịch và chạy thành công; không cần dependency Spring, database hoặc internet. Server chỉ bind loopback `127.0.0.1` trên một port trống tự chọn. Vì response chậm hơn request timeout, `HttpTimeoutException` được bắt và chương trình in thông báo. `finally` dừng server và giải phóng executor phục vụ server.

**Điểm học quan trọng:** hết hạn ở client **không có nghĩa server đã bị JVM khách ra lệnh dừng công việc**. Nếu server đang làm một thao tác có side effect, dù caller không còn chờ phản hồi, trạng thái ở phía server vẫn có thể đã thay đổi. Test này chỉ chứng minh client thực thi request-level timeout tại lớp I/O.

`com.sun.net.httpserver.HttpServer` thuộc module `jdk.httpserver` đi kèm **JDK**, phục vụ demo kiểm thử local; nó không phải Spring Boot embedded server và không dành để thay production web server.

## 13. Spring RestClient: chọn request factory và cấu hình HTTP timeout

Trong **Spring Framework 6.2**, một `RestClient` dùng `JdkClientHttpRequestFactory` có thể nhận `HttpClient` JDK đã cấu hình connect timeout, đồng thời đặt response/read timeout ở request factory:

~~~java
import java.net.http.HttpClient;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class HttpClientTimeoutConfig {
    @Bean
    RestClient stockRestClient() {
        HttpClient jdkClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofMillis(500))
            .build();

        JdkClientHttpRequestFactory factory =
            new JdkClientHttpRequestFactory(jdkClient);
        factory.setReadTimeout(Duration.ofSeconds(2));

        return RestClient.builder()
            .requestFactory(factory)
            .baseUrl("https://stock.example.invalid")
            .build();
    }
}
~~~

Đây là **đoạn cấu hình Spring**, cần dependency `spring-web` và URL remote thật khi chạy; `example.invalid` cố ý không trỏ tới hệ thống thật. Cặp giá trị là ví dụ cho connect/response timeout, không phải lời khuyên chọn cố định cho mọi API.

Tên gọi `setReadTimeout` và cách mapping sang native HTTP client **phụ thuộc request factory/version**. Đừng sao chép nguyên giá trị cho Apache HttpComponents, Reactor Netty, Jetty hoặc OkHttp rồi giả định cùng semantics. Spring có nhiều `ClientHttpRequestFactory`; hãy kiểm tra runtime thực sự chọn factory nào.

Với **Spring WebClient** dựa trên Reactor Netty, các timeout thường cấu hình ở lớp Reactor Netty `HttpClient`: connect timeout và response timeout là những cơ chế khác nhau. Thay một property không được kết nối vào `WebClient` thật sẽ không có tác dụng. Trong hệ thống reactive, tránh `block()` trên event-loop và sử dụng timeout/cleanup phù hợp pipeline.

**Không đánh đồng** `spring.mvc.async.request-timeout` của Spring MVC với timeout của HTTP client gọi service bên ngoài. Timeout phía server inbound không thay thế timeout của `RestClient`/`WebClient` outbound.

## 14. @Async và CompletableFuture: timeout ngoài không dừng JDBC/HTTP bên trong

Đoạn mã hay gây hiểu nhầm:

~~~java
CompletableFuture<String> future =
    CompletableFuture.supplyAsync(
        () -> blockingJdbcCall(),
        ioExecutor);

future.orTimeout(2, TimeUnit.SECONDS);
~~~

Đây là **đoạn minh họa**, cần `blockingJdbcCall`/`ioExecutor` và imports tương ứng. `orTimeout` có thể làm future hoàn tất **exceptionally** sau hai giây. Nó **không bảo đảm** `blockingJdbcCall()` hoặc JDBC connection bị interrupt/đóng/rollback khi đã chạy. Worker có thể vẫn giữ JDBC connection và tiếp tục thực thi SQL sau khi caller tưởng đã “cancel”.

Một cách thiết kế tốt hơn là đặt timeout **ngay trong JDBC** ở lời gọi `blockingJdbcCall`: `JdbcTemplate.setQueryTimeout(...)`, JDBC `Statement.setQueryTimeout(...)`, driver/server timeout. Tương tự, nếu callback dùng HTTP client thì request timeout phải được cấu hình trên HTTP client/request, không chỉ trên returned future.

Ví dụ `CompletableFuture<HttpResponse<String>>` từ `HttpClient.sendAsync(...)` được hưởng timeout của `HttpRequest` vì native HTTP client thực thi policy đó. Nếu đặt thêm `future.orTimeout(...)`, đây là một **đồng hồ quan sát bổ sung**, không nên xem là thay thế request timeout đã cấu hình.

**Phân biệt ba hành vi:**

1. **Timed-out caller:** người chờ kết quả ngừng chờ hoặc future được hoàn tất timeout.
2. **Cancellation attempt:** hệ thống cố ngắt/hủy tác vụ bên dưới thông qua API driver/client nếu hỗ trợ.
3. **Remote work actually stopped:** DB/server đã thực sự ngừng xử lý và trả tài nguyên.

Ba điều này không đồng nghĩa. Với `CompletableFuture.cancel(true)` của JDK, cờ `mayInterruptIfRunning` không có tác dụng buộc worker đang chạy phải bị interrupt. Với JDK HTTP client, cancellation của future bất đồng bộ cũng không nên được hiểu là xác nhận remote đã dừng xử lý.

## 15. Deadline tổng, retry budget và propagation

Một tác vụ có các bước DB → HTTP cần có **deadline end-to-end**. Ví dụ inbound yêu cầu được cấp 3 giây, đến lúc bắt đầu HTTP chỉ còn 900ms. Nếu vẫn cấu hình HTTP request timeout 2 giây mà không kiểm tra thời gian còn lại, kết quả có thể đến sau khi response inbound đã hết hiệu lực.

Một cách tính ở **cùng tiến trình Java** bằng clock monotonic:

~~~java
long deadlineNanos =
    System.nanoTime() + TimeUnit.SECONDS.toNanos(3);

// Sau khi hoàn tất bước DB...
long remainingNanos = deadlineNanos - System.nanoTime();
if (remainingNanos <= 0) {
    throw new TimeoutException("Request deadline exceeded");
}
Duration requestBudget = Duration.ofNanos(remainingNanos);
~~~

Đây là **đoạn ghép vào phương thức**, cần import `TimeUnit`, `Duration`, `TimeoutException`; không phải class độc lập. `System.nanoTime()` phù hợp đo **elapsed time trong một JVM**, không dùng như timestamp có ý nghĩa qua máy khác. Phải xử lý overflow/budget quá nhỏ phù hợp hệ thống khi thiết kế API chung.

Truyền `requestBudget` vào builder HTTP request thực tế, có thể trừ thêm safety margin để đáp ứng serializer/logging. Với SQL, nếu API chỉ nhận timeout theo giây nguyên, không tự làm tròn thành 0 rồi vô tình vô hiệu hóa timeout; thay vào đó chọn policy làm tròn hợp lệ, driver/server setting có độ phân giải phù hợp hoặc từ chối bước không đủ thời gian.

**Retry:** mỗi retry phải nằm trong deadline tổng và còn đủ budget cho việc chờ + thực thi. Không retry ngay khi DB/HTTP đã timeout, vì có thể tăng quá tải và nhân side effect. Chỉ retry lỗi thật sự tạm thời, có backoff + jitter, max attempts và idempotency, tôn trọng `Retry-After` nếu remote trả tín hiệu phù hợp.

## 16. Khi timeout xảy ra: tài nguyên, transaction và kết quả không chắc chắn

Với DB:

- Timeout của statement có thể kích hoạt nỗ lực cancel, nhưng cần xác minh driver/DB thật có ngừng câu query hay chưa.
- Transaction có thể cần rollback; nếu Spring thấy một `DataAccessException` unchecked đi qua transaction interceptor, mặc định thường đánh dấu rollback theo rule của Spring. Nhưng nếu bạn **bắt và nuốt lỗi** trước khi interceptor biết, rollback không tự nhiên xảy ra.
- Một câu `UPDATE`/stored procedure có thể thực hiện một phần công việc trước khi timeout; trạng thái commit/rollback quyết định hệ quả cuối cùng, không thể kết luận chỉ bằng thông báo timeout.
- Đóng `ResultSet`/`Statement`/`Connection` bằng `try-with-resources`; khi dùng Spring JDBC, để template/transaction manager quản lý tài nguyên thay vì đóng connection bound vào transaction sai cách.
- Một connection bị lỗi network nghiêm trọng có thể không còn an toàn để reuse; để driver/pool kiểm tra và loại bỏ theo cơ chế của chúng.

Với HTTP:

- Client timeout không chứng minh remote **chưa nhận POST/PUT/PATCH**. Yêu cầu có thể được xử lý thành công trước khi response mất.
- Không tự retry mọi mutation bằng request mới. Dùng **idempotency key ổn định** qua các attempt hoặc API tra cứu trạng thái.
- Nếu dùng streaming lớn, giải phóng response body/subscriber/connection đúng abstraction; đừng để task timeout nhưng body stream vẫn giữ tài nguyên.
- Phân biệt connect error, request timeout, server trả `408`/`429`/`503` và lỗi deserialize; chúng có retry semantics khác nhau.

Khi task chạy trong `@Async` worker, timeout I/O cần được **chuyển thành trạng thái kết quả**: với method trả `CompletableFuture`, caller có thể theo dõi exceptional completion. Với `@Async void`, exception chưa bắt sẽ đi qua `AsyncUncaughtExceptionHandler` nếu lời gọi được Spring proxy xử lý, không quay về caller như một exception đồng bộ.

## 17. Thiết kế thứ tự timeout để tránh tự làm nghẽn hệ thống

Một policy tốt cần xét quan hệ với tài nguyên thực:

1. **Timeout lấy DB connection nhỏ hơn deadline tổng.** Nếu pool cạn, fail sớm thay vì giữ worker vô nghĩa.
2. **Query timeout phù hợp đặc tính SQL và SLO.** Truy vấn batch dài có thể cần pool/API riêng, không nên tăng timeout chung của tất cả request.
3. **Driver socket timeout bảo vệ đường truyền DB.** Tùy driver, cần đủ để cơ chế cancel/query timeout được trao đổi; đặt quá ngắn có thể làm hỏng kết nối trước khi DB xác nhận hủy statement.
4. **HTTP connect timeout ngắn nhưng hợp lý** cho mạng triển khai; request/response timeout giới hạn chính công việc remote. Có thêm pool acquisition timeout nếu HTTP client dùng connection pool.
5. **Tổng deadline dành buffer cho downstream và cleanup.** Đừng dành hết thời gian cho SQL rồi ngay sau đó mới bắt đầu HTTP khi caller đã hết hạn.
6. **Retry không được reset deadline tổng** thành một ngân sách mới vô hạn.
7. **Queue time cũng là latency.** Một `@Async` task nằm trong executor queue 5 giây rồi mới bắt đầu thì timeout 2 giây của SQL không bảo đảm job hoàn tất trong 2 giây kể từ lúc nộp.
8. **Đo concurrency và connection pool.** Một worker treo trong JDBC/HTTP đồng nghĩa một worker ít hơn cho các task khác; timeout I/O là một phần của cơ chế chống thread starvation.

Cần có ngoại lệ theo loại workload: một báo cáo chạy nền được phép 2 phút có thể cần worker pool, DB statement timeout và deadline khác với endpoint tương tác yêu cầu dưới 1 giây. Không có một cấu hình chung cho mọi nhiệm vụ.

## 18. Quan sát và kiểm thử timeout theo từng tầng

**Metric/tracing nên tách được:**

| Thành phần | Điều nên đo |
| --- | --- |
| ThreadPoolTaskExecutor | active threads, queue length, task waiting time, rejected submissions |
| Connection pool | active/idle/pending connections, acquisition latency, acquisition timeouts |
| SQL/JDBC | query duration, statement timeout, lock wait, SQLState/vendor error, transaction rollback |
| HTTP client | connection establishment, response latency, HTTP status, connect timeout, request timeout, pool wait |
| Nghiệp vụ | end-to-end latency, remaining deadline, retry attempts, late completions, duplicate prevention |

Các label metric có cardinality thấp; không đưa raw SQL chứa dữ liệu cá nhân, URL có token, request body hoặc user ID làm tag metric. Dùng tracing/log có cấu trúc và chính sách bảo mật khi cần drill-down.

**Bộ test gợi ý:**

1. **DB pool exhausted:** giữ hết connection trong test, yêu cầu một connection mới và xác nhận pool acquisition timeout hoạt động; không nhầm với query timeout.
2. **Long SQL:** chạy một query được DB test cố ý làm chậm (ví dụ `pg_sleep` trên PostgreSQL test environment) rồi xác nhận driver/server timeout và cách kết nối được trả về pool.
3. **Slow HTTP:** dùng một server local/mock server trả response chậm hơn request timeout; kiểm tra loại lỗi và tài nguyên cleanup như demo.
4. **Connect failure:** thử môi trường có network fault được kiểm soát; không giả định mọi địa chỉ sai đều gây connect timeout (có thể bị từ chối ngay).
5. **Late result:** làm cho caller/future hết hạn trước nhưng downstream xử lý xong muộn; xác nhận không ghi đè trạng thái cuối hoặc tạo tác dụng phụ trùng.
6. **Retry storm:** nhiều caller cùng gặp timeout; xác minh retry có giới hạn, backoff/jitter và không làm tăng tải vô hạn.
7. **Cancellation:** kiểm tra `Future.cancel` và thực tế JDBC/HTTP client/DB có giải phóng tài nguyên hay không; không chỉ assert trạng thái `isCancelled()`.
8. **Transaction boundary:** gây timeout bên trong `@Transactional`, kiểm tra rollback và trạng thái bảng sau lỗi theo DB thật.
9. **Queue wait:** giữ worker bằng latch để đo queue delay riêng với thời gian chạy SQL/network.

Dùng **đồng hồ có thể kiểm soát** hoặc latch trong unit test khi có thể, không viết test bằng `Thread.sleep` rồi kỳ vọng timing tuyệt đối. Đối với driver/network, phải có integration test thực tế vì các loại timeout chịu ảnh hưởng của OS, JDK và cấu hình hạ tầng.

## 19. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`CompletableFuture.orTimeout` dừng JDBC query.” | Nó làm future hết hạn; I/O bên dưới có thể còn chạy. |
| “`HikariCP.connectionTimeout` là SQL query timeout.” | Nó chủ yếu giới hạn thời gian mượn connection từ pool. |
| “`@Transactional(timeout=...)` tự cancel mọi HTTP request.” | Transaction timeout chỉ có hiệu lực lên các resource được transaction manager hỗ trợ và tích hợp. |
| “Có `connectTimeout` là remote API không bao giờ treo.” | Connect chỉ giới hạn lập kết nối mới; remote có thể chậm trả response. |
| “Mọi `readTimeout` đều giới hạn tổng thời gian request.” | Nhiều client chỉ giới hạn thời gian chờ giữa các lần đọc hoặc response theo policy riêng. |
| “`Statement.setQueryTimeout(2)` bao gồm thời gian lấy connection.” | Query timeout chỉ bắt đầu ở statement; acquisition nằm trước. |
| “`setQueryTimeout(500)` nghĩa là 500ms.” | JDBC nhận **giây**; đó là 500 giây nếu driver áp trực tiếp. |
| “Mọi driver dùng socketTimeout theo milliseconds.” | Tên và đơn vị là đặc thù driver; pgJDBC dùng giây. |
| “Timeout nghĩa là remote chưa tạo đơn/thanh toán.” | Remote có thể đã thực hiện, chỉ có response không tới kịp. |
| “Client timeout thì transaction chắc chắn rollback.” | Cần xác minh commit/rollback thực tế; hai hệ thống là những ranh giới riêng. |
| “Chỉ cần đặt tổng deadline 3 giây là mọi thread/connection được giải phóng.” | Deadline phải phối hợp timeout/hủy thực tế ở mỗi I/O boundary. |
| “Đặt timeout thật nhỏ luôn tốt hơn.” | Dễ tạo lỗi giả, retry storm, kết nối bị phá hủy và giảm throughput; cần theo SLO/tải. |

## 20. Checklist trước khi triển khai

- Xác định rõ từng chỗ đợi: executor queue, DB pool acquire, DB connect, SQL execution, DB socket, HTTP connect, HTTP response và caller wait.
- Chọn timeout ở **đúng lớp thực hiện I/O**; không chỉ đặt timeout trên future phía ngoài.
- Ghi rõ **đơn vị** của từng property: Hikari milliseconds, JDBC statement seconds, JDK HTTP `Duration`, pgJDBC driver properties theo tài liệu.
- Có deadline tổng và không bắt đầu bước mới khi không còn thời gian.
- Kiểm tra version/driver/request factory đang thực sự chạy; không áp giả định từ thư viện khác.
- Dùng query timeout, driver/network timeout và server timeout khi cần, hiểu điều kiện override bởi transaction timeout.
- Chọn đúng policy rollback, error propagation và cleanup khi timeout.
- Không giữ DB transaction/connection trong lúc remote call chậm nếu có thể tách boundary.
- Không auto-retry vô hạn; với tác vụ thay đổi trạng thái, có idempotency key và reconciliation.
- Quan sát connection pool pending, worker active, query/HTTP latency, timeout rate, retries và late completions.
- Kiểm thử cả slow query, slow HTTP, connection pool saturation, lỗi mạng, transaction rollback và side effect đến muộn.

**Kết luận:** Một `@Async` task có thể đã hết hạn trong mắt caller nhưng vẫn đang chờ JDBC/HTTP ở worker. Để tránh chiếm thread và connection vô thời hạn, phải **đặt timeout riêng tại DB driver/statement/server và HTTP client/request**, đồng thời quản lý deadline nghiệp vụ, retry, cancellation, cleanup và hậu quả của kết quả không chắc chắn.

## Tài liệu tham khảo chính thức

- [Java SE 17 – Statement.setQueryTimeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html): giới hạn thực thi JDBC statement và `SQLTimeoutException`.
- [Spring Framework – JdbcTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): `setQueryTimeout`, mặc định -1 và tương tác với timeout transaction.
- [Spring Framework – Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): timeout và propagation của transaction.
- [Spring Framework – DataSourceTransactionManager](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html): cách truyền transaction timeout xuống JDBC statements khi tích hợp đúng.
- [HikariCP – README](https://github.com/brettwooldridge/HikariCP): `connectionTimeout`, `validationTimeout`, `maximumPoolSize`.
- [PostgreSQL JDBC – Connection parameters](https://jdbc.postgresql.org/documentation/use/): `connectTimeout`, `socketTimeout`, `queryTimeout` và đơn vị.
- [Java SE 17 – HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): connect timeout và HTTP client configuration.
- [Java SE 17 – HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): timeout cho một HTTP request.
- [Spring Framework – JdkClientHttpRequestFactory](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/client/JdkClientHttpRequestFactory.html): `setReadTimeout(Duration)`.
- [Java SE 17 – CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `orTimeout`, `completeOnTimeout`, `cancel` và giới hạn hủy tác vụ.
