# Quản lý timeout cho kết nối, truy vấn và tác vụ dài

Một command Spring Shell có thể gọi API từ xa, lấy connection từ pool, chạy truy vấn SQL rồi xử lý một tập dữ liệu lớn. Mỗi bước có thể bị chậm ở một nơi khác nhau. Nếu chỉ đặt một timeout ở command hoặc ở HTTP client, các bước còn lại vẫn có thể chờ lâu hơn dự kiến.

Spring Boot và Spring Framework cung cấp timeout ở nhiều tầng: HTTP connect/read, thời gian chờ connection pool, thời gian chạy câu SQL, transaction và thời gian chờ một tác vụ bất đồng bộ. Ứng dụng CLI cần kết hợp các giới hạn này thành một ngân sách thời gian cho mỗi command.

## 1. Phân biệt các loại timeout

| Loại timeout | Giới hạn điều gì? | Ví dụ cấu hình/API |
| --- | --- | --- |
| HTTP connect | Thời gian thiết lập kết nối tới máy chủ | spring.http.client.connect-timeout |
| HTTP read | Thời gian chờ dữ liệu phản hồi | spring.http.client.read-timeout |
| Pool acquisition | Thời gian chờ lấy connection đang rảnh từ pool | spring.datasource.hikari.connection-timeout |
| Connection validation | Thời gian kiểm tra connection còn hoạt động | spring.datasource.hikari.validation-timeout |
| SQL query | Thời gian thực thi một JDBC statement | spring.jdbc.template.query-timeout |
| JPA query | Hint thời gian cho một truy vấn JPA | jakarta.persistence.query.timeout |
| Transaction | Thời gian tối đa của một transaction mới | @Transactional(timeout = ...) |
| Task wait/deadline | Thời gian command chờ một tác vụ hoàn thành | Future.get(timeout, unit) |

Các giới hạn này giải quyết những vấn đề khác nhau. Pool acquisition timeout không giới hạn thời gian chạy SQL. Query timeout không giới hạn thời gian gọi API. Transaction timeout không phải deadline cho toàn bộ command. Spring Shell không có một thuộc tính duy nhất tự động giới hạn tất cả hoạt động bên trong command.

## 2. Thiết kế ngân sách thời gian cho command

Trước khi cấu hình từng tầng, hãy xác định thời gian tối đa người vận hành chấp nhận chờ. Ví dụ minh họa:

| Hoạt động | Ngân sách |
| --- | ---: |
| Toàn bộ command đồng bộ hóa | 30 giây |
| Lấy connection từ pool | 2 giây |
| Một truy vấn SQL | 5 giây |
| Thiết lập kết nối HTTP | 2 giây |
| Chờ phản hồi HTTP | 5 giây |
| Xử lý và ghi kết quả | Phần thời gian còn lại |

Đây là số liệu để minh họa cách chia ngân sách, không phải giá trị mặc định phù hợp với mọi ứng dụng. Nếu command gọi ba API tuần tự, tổng thời gian có thể lớn hơn read timeout của một request. Hãy tính cả số lần gọi, retry, backoff và thời gian xử lý kết quả.

Khi một command có nhiều bước, dùng một deadline chung. Sau mỗi bước, tính thời gian còn lại thay vì cấp lại toàn bộ timeout ban đầu. Có thể dùng System.nanoTime() để đo khoảng thời gian vì đồng hồ này không bị thay đổi khi hệ điều hành đồng bộ lại giờ:

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

long deadlineNanos =
        System.nanoTime() + Duration.ofSeconds(30).toNanos();

long remainingNanos = deadlineNanos - System.nanoTime();
if (remainingNanos <= 0) {
    throw new TimeoutException("Đã hết thời gian cho command");
}
```

Các timeout ở tầng tài nguyên cần ngắn hơn hoặc bằng thời gian còn lại của command. Deadline tổng vẫn cần được kiểm tra giữa các bước, vì nhiều timeout riêng lẻ không tự cộng lại thành một giới hạn tổng.

## 3. Cấu hình timeout cho HTTP client

Spring Boot 3.4 cung cấp cấu hình chung cho các HTTP client được auto-configure. Hai thuộc tính thường dùng là connect-timeout và read-timeout:

```yaml
spring:
  http:
    client:
      connect-timeout: 2s
      read-timeout: 5s
```

connect-timeout giới hạn thời gian thiết lập kết nối. read-timeout giới hạn thời gian chờ đọc phản hồi theo cách triển khai của HTTP client được chọn. Spring Boot có thể tự phát hiện Apache HttpClient, Jetty, Reactor Netty, JDK HttpClient hoặc Simple JDK client tùy dependency trên classpath. Vì vậy, hãy kiểm tra semantics và giới hạn của request factory đang được dùng. Có thể chọn factory bằng spring.http.client.factory khi cần. <Link url="https://docs.spring.io/spring-boot/3.4/reference/io/rest-client.html" title="Calling REST Services — Spring Boot 3.4"/>.

Sử dụng RestClient.Builder do Spring Boot cung cấp:

```java
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class InventoryClient {

    private final RestClient restClient;

    public InventoryClient(RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("https://inventory.example.test")
                .build();
    }

    public InventoryItem findItem(String itemId) {
        return restClient.get()
                .uri("/items/{id}", itemId)
                .retrieve()
                .body(InventoryItem.class);
    }
}
```

Builder được Spring Boot cấu hình với request factory phù hợp. Các thuộc tính chung ở trên được áp dụng cho client auto-configured. Nếu một tích hợp cần timeout khác, tạo request factory riêng bằng ClientHttpRequestFactoryBuilder và ClientHttpRequestFactorySettings thay vì thay đổi timeout toàn cục cho mọi client. ClientHttpRequestFactorySettings có từ Spring Boot 3.4.0 và hỗ trợ withConnectTimeout(...) cùng withReadTimeout(...). <Link url="https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/http/client/ClientHttpRequestFactorySettings.html" title="ClientHttpRequestFactorySettings API"/>.

## 4. Hiểu giới hạn của HTTP timeout

Connect timeout và read timeout không nhất thiết là thời gian tối đa cho toàn bộ request. Một request có thể kết nối nhanh nhưng chờ server xử lý lâu; một response dạng streaming có thể tiếp tục gửi dữ liệu định kỳ và không vi phạm read timeout theo cách client đo khoảng chờ đọc.

Nếu cần giới hạn tổng thời gian của một request hoặc chuỗi request, hãy dùng deadline ở tầng service. Đồng thời kiểm tra timeout của proxy, load balancer và API đích. DNS lookup, TLS handshake, connection pool acquisition và redirect có thể có quy tắc riêng tùy HTTP client.

Với WebClient dựa trên Reactor Netty, cấu hình có thể gồm connect timeout và ReadTimeoutHandler; cách cấu hình này khác với RestClient blocking. Không sao chép cấu hình của một HTTP implementation sang implementation khác mà không kiểm tra API tương ứng. <Link url="https://docs.spring.io/spring-boot/3.4/how-to/http-clients.html" title="HTTP Clients — Spring Boot 3.4"/>.

## 5. Timeout lấy connection từ HikariCP

Khi ứng dụng dùng HikariCP, connection-timeout giới hạn thời gian một thread chờ lấy connection từ pool. Nếu pool đã đạt maximum-pool-size và không còn connection rảnh, lời gọi lấy connection sẽ chờ tối đa khoảng thời gian này rồi ném SQLException.

Ví dụ:

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 10
      connection-timeout: 3000
      validation-timeout: 1000
```

Hai giá trị timeout trong cấu hình HikariCP tính bằng millisecond:

- connection-timeout: 3000: chờ tối đa 3 giây để mượn connection từ pool.
- validation-timeout: 1000: giới hạn thời gian kiểm tra connection còn hoạt động.

validation-timeout phải nhỏ hơn connection-timeout. Các thuộc tính này được Spring Boot bind vào cấu hình Hikari datasource. <Link url="https://docs.spring.io/spring-boot/3.4/appendix/application-properties/" title="Common Application Properties — Spring Boot 3.4"/> · <Link url="https://github.com/brettwooldridge/HikariCP/wiki/Configuration" title="HikariCP Configuration"/>.

Không nhầm connection-timeout của Hikari với thời gian bắt tay TCP hoặc đăng nhập database. Thời gian mở kết nối vật lý còn phụ thuộc JDBC driver và cấu hình mạng. Các tùy chọn login/socket timeout thường được truyền qua driver hoặc JDBC URL, và tên thuộc tính khác nhau giữa PostgreSQL, MySQL, Oracle và các driver khác.

## 6. Timeout cho câu truy vấn JDBC

Spring Boot hỗ trợ spring.jdbc.template.query-timeout để cấu hình thời gian tối đa cho các statement do JdbcTemplate thực thi:

```yaml
spring:
  jdbc:
    template:
      query-timeout: 5s
```

Nếu không ghi hậu tố đơn vị, Spring Boot hiểu giá trị là giây. Giá trị mặc định là dùng cấu hình mặc định của JDBC driver. JdbcTemplate áp dụng query timeout cho JDBC statement thông qua Statement.setQueryTimeout(...); khả năng ngắt truy vấn phụ thuộc driver và database. <Link url="https://docs.spring.io/spring-boot/3.4/appendix/application-properties/" title="Common Application Properties — Spring Boot 3.4"/> · <Link url="https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html" title="JdbcTemplate API — Spring Framework 6.2"/>.

Ví dụ dùng JdbcTemplate:

```java
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderRepository {

    private final JdbcTemplate jdbcTemplate;

    public OrderRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<String> findPendingOrderIds() {
        return jdbcTemplate.query(
                "select id from orders where status = ?",
                (rs, rowNum) -> rs.getString("id"),
                "PENDING");
    }
}
```

Nếu query timeout được đặt trên transaction đang hoạt động, thời gian còn lại của transaction có thể ghi đè timeout mặc định của JdbcTemplate. Vì vậy, một truy vấn ở gần cuối transaction có thể nhận timeout ngắn hơn giá trị cấu hình chung.

## 7. Timeout cho truy vấn JPA

Với JPA, có thể đặt query hint jakarta.persistence.query.timeout. Giá trị của hint được tính bằng millisecond:

```java
List<Customer> customers = entityManager
        .createQuery(
                "select c from Customer c where c.status = :status",
                Customer.class)
        .setParameter("status", CustomerStatus.ACTIVE)
        .setHint("jakarta.persistence.query.timeout", 3000)
        .getResultList();
```

Hint này yêu cầu provider giới hạn truy vấn trong khoảng 3 giây. Tuy nhiên, Jakarta Persistence cho phép provider hoặc database không thực thi hint. Hãy kiểm tra Hibernate hoặc provider đang dùng và kiểm thử với đúng database trong môi trường triển khai. Không coi JPA query hint là cơ chế hủy truy vấn được đảm bảo trên mọi hệ quản trị. <Link url="https://jakartaee.github.io/persistence/latest-nightly/nightly.html" title="Jakarta Persistence — Query Timeout Hint"/>.

## 8. Timeout cho transaction

Spring hỗ trợ timeout trên transaction bằng @Transactional(timeout = ...). Đơn vị là giây:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderUpdateService {

    @Transactional(timeout = 10)
    public void updateOrderStatus(String orderId) {
        // Đọc và cập nhật dữ liệu trong một transaction ngắn.
    }
}
```

Transaction timeout áp dụng khi transaction mới được tạo với propagation REQUIRED hoặc REQUIRES_NEW. Transaction manager và resource phải hỗ trợ timeout để giới hạn được thao tác. Với JDBC, Spring có thể áp dụng thời gian còn lại của transaction vào statement; điều này giúp các query trong transaction tuân theo phần ngân sách còn lại. <Link url="https://docs.spring.io/spring/reference/6.2/data-access/transaction/declarative/annotations.html" title="Using @Transactional — Spring Framework 6.2"/>.

Transaction timeout không tự giới hạn HTTP call, vòng lặp CPU hoặc toàn bộ command. Tránh mở một transaction rồi giữ nó trong suốt một tác vụ chạy nhiều phút. Hãy chia tác vụ thành các bước, mỗi bước dùng transaction ngắn để cập nhật dữ liệu và checkpoint.

## 9. Timeout cho tác vụ dài

Một command có thể tạo báo cáo, đồng bộ hàng nghìn bản ghi hoặc thực hiện tác vụ mất nhiều phút. Nếu command chạy đồng bộ trên thread của shell, người vận hành không thể tiếp tục nhập lệnh trong lúc chờ.

Có hai cách tổ chức:

- **Chờ có giới hạn:** command gửi công việc tới executor, chờ kết quả đến một deadline rồi trả kết quả hoặc báo timeout.
- **Job nền:** command tạo job, trả về job ID; người vận hành dùng command khác để xem trạng thái hoặc yêu cầu hủy. Cách này phù hợp với tác vụ kéo dài và cần theo dõi tiến độ.

Spring cung cấp TaskExecutor và ThreadPoolTaskExecutor để quản lý thực thi bất đồng bộ. Dùng thread pool có giới hạn và queue hữu hạn để tránh nhận vô hạn tác vụ khi hệ thống đang quá tải. <Link url="https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html" title="Task Execution and Scheduling — Spring Framework 6.2"/>.

## 10. Cấu hình executor có giới hạn

Ví dụ tạo executor riêng cho các tác vụ dài:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class TaskExecutionConfiguration {

    @Bean("longTaskExecutor")
    ThreadPoolTaskExecutor longTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("long-task-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }
}
```

Các thông số trên là ví dụ. Chọn số thread dựa trên mức sử dụng CPU, database connection pool và giới hạn của API bên ngoài. Nếu executor nhận thêm tác vụ khi thread và queue đã đầy, chính sách từ chối có thể phát sinh TaskRejectedException; command nên báo rằng hệ thống đang bận thay vì âm thầm bỏ việc.

## 11. Chờ Future với timeout và yêu cầu hủy

Future.get(timeout, unit) giới hạn thời gian thread gọi get chờ kết quả. Khi hết thời gian, phương thức ném TimeoutException. Gọi cancel(true) để yêu cầu interrupt thread đang chạy:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class ReportCommands {

    private final ThreadPoolTaskExecutor longTaskExecutor;
    private final ReportService reportService;

    public ReportCommands(
            @Qualifier("longTaskExecutor") ThreadPoolTaskExecutor longTaskExecutor,
            ReportService reportService) {
        this.longTaskExecutor = longTaskExecutor;
        this.reportService = reportService;
    }

    @ShellMethod(key = "report generate", value = "Tạo báo cáo")
    public String generate(
            @ShellOption(value = "--report-id") String reportId) {

        Future<String> task =
                longTaskExecutor.submit(() -> reportService.generate(reportId));

        try {
            return task.get(10, TimeUnit.MINUTES);
        }
        catch (TimeoutException ex) {
            task.cancel(true);
            throw new IllegalStateException(
                    "Tác vụ tạo báo cáo đã vượt quá thời gian cho phép", ex);
        }
        catch (InterruptedException ex) {
            task.cancel(true);
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Đã ngắt lệnh tạo báo cáo", ex);
        }
        catch (ExecutionException ex) {
            throw new IllegalStateException("Không thể tạo báo cáo", ex.getCause());
        }
    }
}
```

Ví dụ giới hạn thời gian command chờ báo cáo ở 10 phút. Trong ứng dụng thực tế, lấy thời gian này từ cấu hình và tính theo deadline còn lại nếu command có nhiều bước.

## 12. Hủy tác vụ phải có tính hợp tác

Future.cancel(true) gửi yêu cầu interrupt. Nó không cưỡng bức dừng một thread đang chạy. Tác vụ phải kiểm tra trạng thái interrupt và thoát ở các điểm an toàn:

```java
import java.util.concurrent.CancellationException;

import org.springframework.stereotype.Service;

@Service
public class ReportService {

    public String generate(String reportId) {
        // loadBatches và processBatch là các hàm nghiệp vụ của ứng dụng.
        for (ReportBatch batch : loadBatches(reportId)) {
            if (Thread.currentThread().isInterrupted()) {
                throw new CancellationException("Report generation was cancelled");
            }

            processBatch(batch);
        }

        return "Đã tạo báo cáo " + reportId;
    }
}
```

Nếu tác vụ đang chờ I/O, cần timeout riêng cho HTTP hoặc database. Interrupt không đảm bảo mọi JDBC driver hay HTTP client đều dừng request ngay lập tức. Query timeout, socket/read timeout và cơ chế cancel của driver vẫn cần được cấu hình.

Khi bắt InterruptedException, hãy khôi phục cờ interrupt bằng Thread.currentThread().interrupt() trước khi trả lỗi hoặc kết thúc. Không nuốt interrupt rồi tiếp tục chạy công việc.

## 13. An toàn dữ liệu khi timeout hoặc hủy

Timeout chỉ cho biết command không nhận được kết quả trong thời gian cho phép. Nó không chứng minh thao tác từ xa chưa xảy ra. Ví dụ server có thể đã nhận lệnh triển khai, ghi dữ liệu xong nhưng phản hồi bị chậm.

Với command có side effect:

- Dùng operation ID hoặc idempotency key để tránh thực hiện trùng khi người dùng chạy lại.
- Lưu trạng thái job như QUEUED, RUNNING, SUCCEEDED, FAILED, CANCEL_REQUESTED, CANCELLED.
- Ghi checkpoint sau từng batch để có thể tiếp tục hoặc xác định phần việc đã hoàn tất.
- Chỉ đánh dấu CANCELLED khi worker xác nhận đã dừng ở điểm an toàn.
- Sau timeout, cung cấp command tra cứu trạng thái thay vì khuyến khích chạy lại ngay.

Không giữ transaction database mở trong khi gọi API từ xa hoặc chờ người dùng. Tách cập nhật trạng thái, lời gọi bên ngoài và ghi kết quả thành các bước có ranh giới rõ ràng.

## 14. Retry phải nằm trong deadline

Retry có thể giúp vượt qua lỗi mạng tạm thời, nhưng nếu mỗi lần retry được cấp một timeout đầy đủ thì tổng thời gian có thể vượt xa giới hạn command.

Ví dụ một request có read timeout 5 giây và retry 3 lần có thể chờ hơn 15 giây, chưa tính thời gian backoff. Hãy:

1. Đặt deadline tổng cho command.
2. Trước mỗi lần retry, tính thời gian còn lại.
3. Chỉ gửi request nếu ngân sách còn đủ.
4. Dùng backoff có giới hạn và tránh retry khi deadline đã hết.
5. Không retry lỗi validation, lỗi xác thực hoặc thao tác không idempotent nếu chưa có cơ chế chống lặp.

Timeout và retry phải được thiết kế cùng nhau. Tăng timeout không phải lúc nào cũng làm hệ thống đáng tin cậy hơn; đôi khi nó chỉ giữ thread và connection bận lâu hơn.

## 15. Hiển thị timeout trong Spring Shell

Thông báo lỗi nên cho người vận hành biết thao tác nào hết thời gian, giới hạn nào đã áp dụng và cách kiểm tra trạng thái:

```text
Không thể lấy danh sách đơn hàng: truy vấn vượt quá 5 giây.
Hãy thử thu hẹp bộ lọc hoặc kiểm tra trạng thái database.
```

Với job dài:

```text
Tác vụ report-2026-004 vẫn chưa hoàn tất sau 10 phút.
Job ID: job-7f31
Đã gửi yêu cầu hủy. Dùng job status job-7f31 để kiểm tra trạng thái.
```

Không hiển thị stack trace, JDBC URL, token hoặc thông tin nhạy cảm. Với command được gọi từ script/CI, hãy ánh xạ timeout sang kết quả thất bại và mã thoát khác 0 theo cơ chế exit-code của ứng dụng; chỉ in thông báo lỗi mà vẫn trả mã thành công sẽ khiến automation hiểu sai.

## 16. Kiểm thử timeout

Kiểm thử cần chứng minh timeout được áp dụng ở đúng tầng:

| Tình huống | Cách kiểm thử |
| --- | --- |
| HTTP connect timeout | Dùng endpoint hoặc mock server không chấp nhận kết nối trong thời gian giới hạn |
| HTTP read timeout | Dùng mock server trì hoãn response body |
| Pool acquisition timeout | Giữ hết connection trong pool rồi yêu cầu thêm một connection |
| JDBC query timeout | Chạy câu SQL có thời gian xử lý dài trên database hỗ trợ cancel |
| JPA query hint | Xác nhận provider thực tế áp dụng hoặc bỏ qua hint |
| Transaction timeout | Chạy thao tác vượt giới hạn trong transaction mới |
| Task deadline | Dùng task giả lập chậm và xác nhận command trả lỗi trong thời gian dự kiến |
| Cancellation | Xác nhận worker nhận interrupt, dừng ở checkpoint và cập nhật trạng thái |

Không chỉ kiểm tra exception. Hãy đo thời gian thực tế, xác nhận connection được trả về pool, transaction được rollback khi phù hợp và task không tiếp tục ghi dữ liệu sau khi đã báo hủy.

## 17. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| HTTP request chờ lâu dù đã đặt connect timeout | Server đã nhận kết nối nhưng phản hồi chậm | Đặt read timeout và deadline tổng |
| Hết connection pool | Thread giữ connection quá lâu hoặc pool quá nhỏ | Kiểm tra thời gian giữ connection, pool sizing và pool acquisition timeout |
| Query chạy lâu hơn dự kiến | JDBC driver không hỗ trợ hoặc không áp dụng query timeout | Kiểm tra driver/database và thử truy vấn tích hợp |
| Transaction timeout không tác dụng | Transaction không được tạo mới hoặc manager không hỗ trợ timeout | Kiểm tra propagation, transaction manager và proxy |
| Command báo timeout nhưng worker vẫn chạy | Worker không xử lý interrupt hoặc đang mắc trong I/O không có timeout | Thêm cancellation checkpoint và timeout cho tài nguyên |
| Retry kéo dài vô hạn | Mỗi lần thử được cấp lại toàn bộ timeout | Dùng deadline chung và giới hạn số lần retry |
| Người dùng chạy lại thao tác đã timeout | Không biết server đã thực hiện side effect hay chưa | Dùng operation ID, idempotency và command tra cứu trạng thái |
| Thread pool cạn tài nguyên | Queue không giới hạn hoặc nhận quá nhiều job | Đặt queue hữu hạn, concurrency limit và xử lý task rejection |

## 18. Bài thực hành tổng hợp

Xây dựng CLI có command inventory sync đồng bộ dữ liệu từ API và database:

1. Đặt HTTP connect timeout 2 giây và read timeout 5 giây.
2. Đặt Hikari pool acquisition timeout 3 giây và validation timeout 1 giây.
3. Đặt JDBC query timeout 5 giây.
4. Đặt transaction timeout 10 giây cho thao tác cập nhật ngắn.
5. Tạo executor có giới hạn thread và queue cho công việc đồng bộ dài.
6. Đặt deadline tổng 30 giây cho command đồng bộ một lần.
7. Tính thời gian còn lại trước mỗi API call, query và retry.
8. Khi hết deadline, gọi cancel(true) và để worker dừng tại checkpoint.
9. Lưu job ID, trạng thái và checkpoint để người vận hành tra cứu.
10. Viết integration test cho HTTP chậm, query chậm, pool cạn và task bị hủy.

## 19. Tiêu chí hoàn thành

| Năng lực | Tiêu chí |
| --- | --- |
| Timeout taxonomy | Phân biệt connect, read, pool, query, transaction và task timeout |
| HTTP | Cấu hình và kiểm thử timeout cho RestClient/WebClient theo client thực tế |
| Database pool | Phân biệt chờ pool với mở kết nối vật lý |
| JDBC/JPA | Đặt query timeout và hiểu giới hạn của driver/provider |
| Transaction | Dùng transaction timeout cho transaction mới và ngắn |
| Task execution | Dùng executor có giới hạn và deadline cho tác vụ dài |
| Cancellation | Hiểu interrupt là yêu cầu hợp tác, không phải cưỡng bức dừng |
| Deadline | Chia sẻ một ngân sách thời gian qua nhiều bước và retry |
| Operations | Hiển thị timeout rõ ràng, tra cứu job và bảo vệ side effect |
| Testing | Xác nhận thời gian, rollback, trả connection và dừng worker |

## Tài liệu tham khảo

- [Spring Boot 3.4 — Calling REST Services](https://docs.spring.io/spring-boot/3.4/reference/io/rest-client.html)
- [Spring Boot 3.4 — HTTP Clients](https://docs.spring.io/spring-boot/3.4/how-to/http-clients.html)
- [Spring Boot 3.4 — Common Application Properties](https://docs.spring.io/spring-boot/3.4/appendix/application-properties/)
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP/wiki/Configuration)
- [Spring Framework 6.2 — JdbcTemplate API](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [Spring Framework 6.2 — Using @Transactional](https://docs.spring.io/spring/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Jakarta Persistence — Query Timeout Hint](https://jakartaee.github.io/persistence/latest-nightly/nightly.html)
