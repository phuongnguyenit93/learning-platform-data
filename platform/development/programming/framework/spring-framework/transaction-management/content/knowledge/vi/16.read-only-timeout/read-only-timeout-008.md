# Timeout không tương đương hủy mọi công việc Java hoặc lời gọi mạng

## 1. Vấn đề thực tế: `@Transactional(timeout = ...)` bảo vệ điều gì?

Một đoạn code thường gây hiểu nhầm:

```java
@Transactional(timeout = 2)
public void checkout() {
    callSlowExternalApi();
    saveOrder();
}
```

Đây là **mã minh họa**: `callSlowExternalApi()` và `saveOrder()` chưa được định nghĩa; nó không phải chương trình độc lập. Người viết đôi khi nghĩ rằng sau đúng 2 giây, Spring sẽ dừng method, hủy HTTP request, ngắt mọi thread, thu hồi toàn bộ tác dụng phụ rồi rollback mọi hệ thống. **Cách hiểu ấy sai.**

Trong cơ chế transaction **imperative** của Spring Framework, `timeout` là **thuộc tính quản lý giao dịch**, không phải bộ hẹn giờ có quyền dừng tùy ý mọi mã Java. Một transaction manager có thể lưu **deadline** và sử dụng nó để điều khiển thao tác của những **tài nguyên tham gia transaction**. Với `DataSourceTransactionManager`, Spring JDBC có thể áp dụng thời gian còn lại cho JDBC `Statement.setQueryTimeout(...)` hoặc phát hiện deadline đã hết khi chuẩn bị lệnh. Nhưng:

- `Thread.sleep(...)` không bị transaction manager tự ngắt chỉ vì transaction timeout đã hết.
- Một vòng lặp CPU, phép tính Java, đọc file, chờ lock Java, chờ queue hoặc gọi thư viện bên ngoài không tự động bị Spring transaction timeout hủy.
- HTTP client có các timeout riêng (kết nối, chờ response/request). `@Transactional(timeout=2)` **không tự chuyển thành HTTP request timeout 2 giây**.
- Gọi đến một hệ thống từ xa đã tạo side effect (gửi email, thanh toán, publish message) **không được hoàn tác** chỉ vì JDBC transaction phía caller rollback.
- Ngay cả lỗi timeout ở database cũng có thể phụ thuộc database/driver/transaction manager: không nên hứa rằng cứ đến deadline là mọi JDBC statement đang chạy sẽ dừng ngay lập tức ở đúng mili giây.

**Bài học này thuộc chủ đề “Read-only và timeout” của Spring transaction management.** Mục tiêu là phân biệt timeout giao dịch với cơ chế hủy công việc, sau đó thiết kế và kiểm thử timeout theo từng lớp.

### Sau bài học, bạn cần làm được

1. Giải thích `@Transactional(timeout = 3)` là một cấu hình thời gian tính **bằng giây**, áp dụng cho transaction mới khi được transaction infrastructure hỗ trợ.
2. Nhìn đúng ranh giới **Spring transaction / JDBC statement / HTTP client / Java thread / request gateway**.
3. Phân biệt deadline đã hết với việc **method thật sự ngừng chạy**.
4. Tạo ví dụ Java 17+ trong đó Java tiếp tục chạy sau transaction deadline, nhưng một JDBC operation sau deadline bị từ chối và các ghi trước đó rollback.
5. Cấu hình HTTP timeout riêng, kiểm soát `InterruptedException`, cancellation, retry, idempotency và tránh giữ connection/row lock trong lúc chờ mạng.
6. Hiểu tại sao exception, rollback và kết thúc tác vụ từ xa **không phải một sự kiện duy nhất**.

## 2. Timeout thuộc lớp nào?

Hãy hình dung một HTTP request đi qua controller → service → database và một API khác:

```text
Client / Load balancer / API gateway
       |
       |  Request deadline / gateway timeout
       v
Spring MVC Controller
       |
       |  Java method execution, worker thread
       v
@Transactional(timeout = 2) Service
       |
       |  Spring transaction deadline, rollback policy
       +------------------------+
       |                        |
       v                        v
Spring JDBC / JPA            Java HttpClient
       |                        |
       | Statement/query        | connect timeout,
       | timeout / lock         | per-request timeout,
       | timeout / DB limits    | cancellation policy
       v                        v
Database                    Remote server
       |                        |
       v                        v
COMMIT / ROLLBACK           Remote side effects
(chỉ tài nguyên            (không tự rollback
 tham gia transaction)       theo JDBC transaction)
```

| Loại timeout | Đối tượng điều khiển | Giới hạn quan trọng |
| --- | --- | --- |
| **Transaction timeout** của Spring | Physical transaction mới do manager hỗ trợ; deadline/tài nguyên transaction | Không phải Java thread-killer hoặc timeout HTTP tự động |
| JDBC **statement/query timeout** | Thời gian thực thi một SQL statement theo driver/database | Tùy DB/driver; không tương đương deadline toàn bộ Java use case |
| Database **lock timeout** | Thời gian chờ lấy một lock | Có thể thất bại khi chờ khóa dù thời gian query khác còn đủ |
| HTTP **connect timeout** | Thời gian thiết lập kết nối (trong phạm vi client hỗ trợ) | Không nhất thiết giới hạn toàn bộ request/response |
| HTTP **request/response timeout** | Thời gian chờ của một lời gọi mạng theo HTTP client | Không tự thu hồi tác dụng phụ đã xảy ra phía remote |
| Gateway/request timeout | Thời gian caller/gateway chờ response | Không bảo đảm server worker đã dừng hoặc transaction đã rollback |
| Application **deadline/cancellation** | Quy tắc phối hợp của code, API và tác vụ | Cần các tầng phối hợp, không có một annotation bảo đảm mọi thứ |

**Ví dụ:** gateway trả 504 sau 5 giây. Điều này chỉ xác nhận gateway đã hết thời gian chờ theo chính sách của nó; một task trên server **có thể vẫn đang chạy** và sau đó commit database hoặc gửi message. Muốn biết kết quả thực tế, cần kiểm tra transaction outcome, tracing và idempotent operation status.

## 3. Spring hiểu `@Transactional(timeout = n)` như thế nào?

Cấu hình:

```java
@Transactional(timeout = 3)
public void updateInventory() {
    // Thao tác nghiệp vụ cần transaction.
}
```

Đây là **minh họa**, chưa có class/repository. `timeout = 3` được khai báo **bằng giây**. Giá trị mặc định `-1` nghĩa là dùng default timeout của transaction system (hoặc không có giới hạn nếu không được hỗ trợ).

Theo Spring Framework, thuộc tính `timeout` áp dụng khi **transaction mới được bắt đầu**, thông thường với `PROPAGATION_REQUIRED` hoặc `PROPAGATION_REQUIRES_NEW`:

- `REQUIRED` khi **chưa có transaction**: tạo transaction mới, sử dụng timeout được khai báo nếu manager hỗ trợ.
- `REQUIRED` khi **đang tham gia T1**: không tự tạo một physical transaction có deadline riêng; khai báo timeout ở inner không mặc nhiên ghi đè timeout của T1.
- `REQUIRES_NEW`: tạo **physical transaction riêng**, có thể áp dụng deadline riêng của inner. Tài nguyên transaction ngoài được tạm treo theo manager.
- `NESTED` trong JDBC thường dùng **savepoint cùng physical transaction**, không có physical clock/deadline mới độc lập giống `REQUIRES_NEW`.

Không được khẳng định timeout luôn hoạt động giống nhau trên mọi `PlatformTransactionManager`. Tài nguyên JDBC, JPA/Hibernate, JTA, R2DBC và từng database có cơ chế enforcement riêng. Một manager không hỗ trợ một timeout không mặc định có khả năng hủy mọi đoạn code; thậm chí nó có thể từ chối cấu hình tùy implementation.

### 3.1. Deadline ≠ lập tức interrupt

Một phép tính Java thuần:

```java
@Transactional(timeout = 1)
public void compute() {
    busyCalculation();
}
```

Đây là **đoạn minh họa**. Khi transaction được proxy tạo, timeout được đặt ở transaction manager; nhưng Spring không tự biến `busyCalculation()` thành một đoạn Java bắt buộc bị dừng sau một giây. Nếu code tính toán không truy cập tài nguyên có kiểm tra deadline và không có cơ chế cancellation riêng, nó có thể tiếp tục chạy quá thời gian ấy.

Tương tự, `Thread.sleep(1500)` chỉ thức dậy sau khi đủ thời gian hoặc có thread khác interrupt theo cơ chế Java; **transaction timeout tự nó không gọi `Thread.interrupt()`** cho worker đang ngủ. Sau thời gian chờ, code vẫn có thể thực thi các câu lệnh Java tiếp theo.

### 3.2. JDBC timeout thực sự có thể được phát hiện ở đâu?

Với `DataSourceTransactionManager` và `JdbcTemplate`:

1. Transaction manager mở JDBC transaction và gắn một connection holder/deadline với thread.
2. `JdbcTemplate` lấy connection qua Spring-aware API (`DataSourceUtils`), dùng connection đang tham gia transaction.
3. Khi tạo/chạy JDBC statement, Spring có thể lấy **thời gian transaction còn lại** để gọi `Statement.setQueryTimeout(...)`.
4. Nếu deadline **đã hết** tại thời điểm lấy thời gian còn lại, Spring có thể ném `TransactionTimedOutException` trước khi SQL tiếp theo chạy.
5. Nếu một SQL đang thực thi quá thời gian được áp, driver/database có thể phát sinh lỗi query timeout theo cơ chế riêng; loại exception được dịch sang Spring có thể khác `TransactionTimedOutException`.
6. Nếu exception unchecked thoát khỏi `@Transactional` boundary, mặc định Spring rollback những JDBC writes nằm trong transaction.

Từ đó có một chi tiết rất quan trọng: **mã Java đã chạy sau deadline không chứng minh JDBC transaction vẫn còn được phép thực hiện thêm SQL**. Deadline có thể được kiểm tra **khi resource tiếp tục được sử dụng**, không phải bằng một thread độc lập giết Java code đúng giây thứ n.

Và ngược lại, **không nhận được timeout exception** không tự chứng minh mọi thứ hoàn thành dưới deadline: một manager/driver có thể không chủ động kiểm tra lúc thuần Java tính toán hoặc lúc commit. Hãy đo latency và transaction outcome thay vì suy đoán.

## 4. Một timeline phân biệt rõ điều xảy ra

Giả sử service tạo T1 với `timeout=1` giây:

```text
t = 0 ms
    Spring proxy mở T1; JDBC connection được bind.
    SQL INSERT log_before chạy thành công (chưa commit).

t = 100 ms
    Java bắt đầu chờ bằng Thread.sleep(1400).
    Transaction deadline của T1 tiếp tục trôi.

t ≈ 1500 ms
    Thread.sleep trả về; Java in "Java step finished".
    Không có Spring watchdog nào tự xóa đoạn Java vừa chạy.

t > 1500 ms
    Java gọi JdbcTemplate.update(...) một lần nữa.
    JDBC infrastructure kiểm tra thời gian còn lại của T1.
    Có thể ném TransactionTimedOutException / query-timeout failure.

Sau khi exception thoát khỏi @Transactional method
    Spring transaction interceptor rollback T1.
    INSERT log_before được hủy; câu SQL sau deadline không commit.
```

Trong demo phía dưới, ta **cố ý để JDBC operation thứ hai diễn ra sau thời gian chờ đủ dài** để kiểm tra đường timeout của Spring JDBC. Dòng `Java step finished` xuất hiện **trước** ngoại lệ. Vì vậy người học quan sát hai sự kiện khác nhau: Java tiếp tục chạy **và** transaction có thể thất bại khi dùng tài nguyên.

Nếu bài toán thay `Thread.sleep` bằng một HTTP call chậm, quy tắc vẫn vậy: **Spring transaction deadline không trực tiếp cấu hình timeout/cancel của HTTP client**. HTTP client có thể còn chờ, dù transaction đã quá deadline.

## 5. Thực hành runnable: Java 17, Spring Framework 6.2 và H2

Chương trình nhỏ sau dùng **Java 17+**, **Spring Framework 6.2.8**, **Spring JDBC**, **H2 2.3.232**; không cần Spring Boot hoặc máy chủ HTTP. Nó kiểm chứng ba điều:

1. Transaction có thể active lúc bắt đầu một method.
2. Method **vẫn thực thi code Java sau một đoạn sleep dài hơn `timeout=1`**.
3. Một JDBC statement được gọi **sau deadline** phát sinh timeout và các ghi trước đó trong cùng transaction rollback.

Đây là **demo kiểm chứng local JDBC**; đừng dùng `Thread.sleep` như phương thức điều tiết transaction trong production.

### 5.1. Cấu trúc project

```text
transaction-timeout-boundary/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── TimeoutBoundaryDemo.java
```

### 5.2. `pom.xml`

Copy nguyên nội dung của code block này vào `pom.xml`. **XML declaration là dòng đầu tiên**; không đặt comment trước dòng đó.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>transaction-timeout-boundary</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
                <configuration>
                    <mainClass>example.TimeoutBoundaryDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` quản lý bean/proxy; `spring-jdbc` có `JdbcTemplate` và `DataSourceTransactionManager`; `spring-tx` có `@Transactional`/timeout exceptions; H2 cung cấp database trong bộ nhớ và xuất hiện trên compile classpath vì Java import `JdbcDataSource`.

### 5.3. `src/main/java/example/TimeoutBoundaryDemo.java`

```java
package example;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionTimedOutException;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class TimeoutBoundaryDemo {

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            TimeoutService service = context.getBean(TimeoutService.class);

            jdbc.execute(
                "CREATE TABLE events (" +
                "id INT PRIMARY KEY, label VARCHAR(40) NOT NULL)"
            );

            System.out.println("CASE 1: Java work after deadline");
            service.onlyJava();
            System.out.println("Java-only method returned");

            System.out.println("CASE 2: JDBC after deadline");
            try {
                service.jdbcAfterDeadline();
                System.out.println("Unexpected: JDBC completed");
            } catch (TransactionTimedOutException expected) {
                System.out.println("Outcome: TransactionTimedOutException");
            }

            Integer rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM events", Integer.class
            );
            System.out.println("Committed rows after rollback: " + rows);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {

        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:timeout_boundary;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public TimeoutService timeoutService(JdbcTemplate jdbcTemplate) {
            return new TimeoutService(jdbcTemplate);
        }
    }

    public static class TimeoutService {
        private final JdbcTemplate jdbc;

        public TimeoutService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(timeout = 1)
        public void onlyJava() {
            System.out.println(
                "Transaction active: "
                    + TransactionSynchronizationManager
                        .isActualTransactionActive()
            );
            pause(1400);
            System.out.println("Java continued after 1400 ms");
            // Không dùng thêm SQL sau deadline.
            // Trong local JDBC demo, không có watchdog tự interrupt.
        }

        @Transactional(timeout = 1)
        public void jdbcAfterDeadline() {
            jdbc.update(
                "INSERT INTO events (id, label) VALUES (?, ?)",
                1, "before"
            );

            pause(1400);
            System.out.println("Java continued, trying another JDBC write");

            // JdbcTemplate kiểm tra transaction deadline khi tạo statement.
            // Deadline đã hết -> TransactionTimedOutException, rollback.
            jdbc.update(
                "INSERT INTO events (id, label) VALUES (?, ?)",
                2, "after"
            );
        }

        private static void pause(long milliseconds) {
            try {
                Thread.sleep(milliseconds);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Interrupted", ex);
            }
        }
    }
}
```

**Điều được kiểm chứng:**

- `TimeoutService` được đăng ký bằng `@Bean` và lấy từ `ApplicationContext`. Đây là Spring-managed bean có thể được proxy; nó không phải một object tạo bằng `new` tùy ý trong `main()`.
- `@EnableTransactionManagement` bật annotation-driven transaction interception.
- `DataSourceTransactionManager` quản lý H2 datasource duy nhất, cùng datasource mà `JdbcTemplate` sử dụng.
- Hai public methods được gọi **từ bên ngoài bean qua proxy**, tránh self-invocation.
- `@Transactional(timeout=1)` áp dụng cho **physical transaction mới** ở mỗi case, vì không có outer transaction bao quanh.
- `pause(1400)` khiến Java thread chờ hơn 1 giây. Không có code nào gọi `Thread.interrupt()` chỉ vì deadline Spring đã hết.
- Case 1 không thực hiện SQL sau sleep. Nó minh họa **Java code vẫn hoàn thành** và JDBC transaction manager không phải cơ chế dừng Java statement theo wall-clock.
- Case 2 ghi một hàng vào DB **trước** sleep, rồi chạy thêm JDBC statement **sau** deadline. Với `JdbcTemplate` + `DataSourceTransactionManager`, việc lấy thời gian còn lại có thể ném `TransactionTimedOutException`. Exception unchecked thoát khỏi proxy; Spring rollback cả transaction, xóa hàng đã insert trước đó.

### 5.4. Chạy chương trình

Đứng tại thư mục `transaction-timeout-boundary`, với JDK 17+ và Maven 3.9+:

```bash
java -version
mvn -version
mvn -q compile exec:java
```

**Output dự kiến** cho Spring Framework 6.2.8 + H2 local JDBC như cấu hình trong bài (bỏ qua log Maven/Spring bổ sung, giả định thread không bị interrupt từ bên ngoài):

```text
CASE 1: Java work after deadline
Transaction active: true
Java continued after 1400 ms
Java-only method returned
CASE 2: JDBC after deadline
Java continued, trying another JDBC write
Outcome: TransactionTimedOutException
Committed rows after rollback: 0
```

Đây là một ví dụ **dự kiến theo semantics của Spring JDBC local transaction**, không phải lời hứa mọi database/JPA/JTA driver sẽ ném đúng cùng exception ở cùng thời điểm. Nếu thay manager/driver, hãy ghi nhận exception và transaction outcome thực tế thay vì so từng ký tự output.

### 5.5. Tại sao hai case có vẻ ngược nhau?

**Case 1:** Spring mở transaction, Java sleep dài hơn timeout, in log rồi return. Trong đường thực thi này **không có JDBC statement mới sau deadline** để yêu cầu Spring áp dụng query timeout. Với local JDBC transaction manager như demo, không có thành phần độc lập ép Java thread dừng. Điều này cho thấy timeout không phải `Future.cancel(true)` hoặc một scheduler ngầm có thể giết mọi công việc Java.

**Case 2:** Spring mở T2, JDBC insert đầu tiên nằm trong T2 và chưa commit. Java sleep hơn timeout rồi vẫn in được log; chính tại **JDBC operation tiếp theo**, deadline đã hết nên resource holder có thể ném `TransactionTimedOutException`. Exception đi qua transaction interceptor, Spring rollback T2. Query bên ngoài transaction sau đó đếm 0 hàng. Như vậy:

```text
Java tiếp tục chạy sau deadline       = có
JDBC operation mới sau deadline       = bị từ chối trong ví dụ
Ghi dữ liệu trước timeout được commit = không; transaction rollback
Spring tự hủy Thread.sleep()          = không
```

Một transaction timeout không thể trở thành lời bảo đảm rằng **mọi tác dụng phụ từ xa đã biến mất**. Nếu trước sleep ta gọi HTTP để đặt hàng ở một hệ thống khác, rollback H2 không tự hoàn tác đơn hàng remote.

## 6. Timeout của HTTP call là một cấu hình khác

Spring transaction manager điều khiển transaction; **HTTP client** điều khiển thời gian chờ HTTP. Với Java 17 `java.net.http.HttpClient`, ví dụ minh họa:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class RemoteLookup {
    private final HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

    public String lookup() throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://api.example.com/status"))
            .timeout(Duration.ofSeconds(3))
            .GET()
            .build();

        HttpResponse<String> response =
            client.send(request, HttpResponse.BodyHandlers.ofString());

        return response.body();
    }
}
```

Đây là **ví dụ HTTP minh họa, không chạy trong demo Maven ở mục 5**, và URL là endpoint giả định. Nó phân biệt:

- `connectTimeout(Duration.ofSeconds(2))`: chính sách timeout **thiết lập kết nối** trong phạm vi HTTP client.
- `HttpRequest.Builder.timeout(Duration.ofSeconds(3))`: giới hạn thời gian dành cho **request** theo API HTTP client.
- Không có dòng nào liên quan trực tiếp tới `@Transactional(timeout=1)`. Muốn outer Spring transaction có deadline khác, phải cấu hình transaction riêng.

Khi HTTP request hết thời gian chờ, client có thể ném `HttpTimeoutException`. Điều đó **không xác nhận server remote chưa xử lý request**. Đặc biệt với POST tạo thanh toán/đơn hàng: server có thể đã xử lý thành công nhưng response bị trễ; caller timeout rồi retry mù quáng sẽ gây **xử lý trùng**. Hãy dùng idempotency key, trạng thái operation, request IDs và cơ chế reconciliation.

### 6.1. `@Transactional(timeout = 2)` không tự set HTTP timeout 2 giây

Một đoạn code dễ làm sai:

```java
@Transactional(timeout = 2)
public void slowCheckout() {
    externalClient.callWithoutRequestTimeout(); // Có thể chờ lâu hơn 2 giây.
    repository.saveOrder();                     // Có thể fail vì T1 hết deadline.
}
```

Đây là **minh họa**, không định nghĩa dependency. Một remote call kéo dài 20 giây vẫn có thể kết thúc bình thường hoặc bị ngắt theo chính HTTP stack; `@Transactional(timeout=2)` không tự tạo watchdog đặt `HttpClient` timeout 2 giây. Khi gọi JDBC sau đó, Spring có thể phát hiện deadline hết và rollback local DB write, nhưng side effect remote đã xảy ra **vẫn có thể tồn tại**.

### 6.2. Kết nối, TLS, đọc response và tổng deadline

Các HTTP stacks (Java HttpClient, OkHttp, Apache HttpClient, WebClient, gateway, service mesh) cung cấp các timeout khác nhau: DNS/connect/TLS, request, read/response, idle timeout, call timeout hoặc deadline. Không phải timeout nào cũng đo cùng một giai đoạn. Khi xây service production, hãy biết **timeout cụ thể trên thư viện và phiên bản đang dùng**; đừng gắn một con số rồi giả định bao trùm DNS, TLS, streaming body và mọi retry.

Nếu một API có ngân sách toàn bộ 4 giây, việc đặt từng HTTP retry 4 giây rồi thực hiện 5 lần không bảo đảm hoàn thành trong 4 giây. Cần một **end-to-end deadline** và giảm thời gian chờ còn lại cho mỗi bước.

## 7. Cancellation trong Java là phối hợp, không phải hủy cưỡng bức

### 7.1. `Thread.interrupt()` là tín hiệu

Java thường không có một cơ chế an toàn để buộc dừng bất kỳ thread tùy ý tại đúng một timestamp. `Thread.interrupt()` là một tín hiệu hợp tác: những operations có hỗ trợ interruption (ví dụ `Thread.sleep`) sẽ phản hồi bằng `InterruptedException`; mã CPU-bound cần tự kiểm tra interrupt hoặc cancellation flag nếu muốn dừng.

Mẫu handling:

```java
try {
    Thread.sleep(5000);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Operation interrupted", ex);
}
```

Đây là **mã minh họa**, không phải một complete Java file. Trong ví dụ Maven, ta dùng cùng ý tưởng: **khôi phục interrupted flag**, rồi ném unchecked exception để transaction interceptor có thể rollback nếu method đang được advice. Không nuốt interruption rồi tiếp tục thao tác ghi như chưa có gì xảy ra.

Nhưng ngay cả khi Java worker đã dừng nhờ interruption, **một HTTP POST hoặc SQL đã được remote server thực hiện trước đó không tự bị đảo ngược**. Cần phân biệt **dừng chờ**, **dừng thực thi local**, **dừng tác vụ remote** và **hoàn tác side effect**.

### 7.2. `Future.cancel(true)` và `CompletableFuture.orTimeout` không phải phép màu

Một `Future.cancel(true)` có thể **yêu cầu interrupt** thread đang chạy, nhưng tác vụ phải hỗ trợ interruption/cancellation; nó không bảo đảm I/O bên ngoài bị dừng đúng lúc. Với `CompletableFuture.orTimeout(...)`, future được đánh dấu complete exceptionally theo deadline, nhưng điều đó **không tự bảo đảm** công việc bên dưới hoặc remote operation đã bị dừng. Các API async khác có cancellation semantics riêng; hãy kiểm tra library implementation.

```java
// Ví dụ minh họa, chưa khai báo executor/future:
future.orTimeout(2, TimeUnit.SECONDS)
      .exceptionally(ex -> {
          recordTimeout(ex);
          return fallbackResult();
      });
```

Đoạn này **không độc lập để biên dịch**. Quan sát `fallbackResult()` không chứng minh task gốc chưa tiếp tục chạy. Nếu task còn chạy và ghi database sau khi caller trả timeout, bạn cần cancellation propagation, idempotency và kiểm soát transaction boundary thích hợp.

### 7.3. `@Async` và transaction context

Trong Spring imperative, tài nguyên transaction JDBC thường được gắn với **thread hiện tại**. Gọi `@Async` hoặc tự tạo `CompletableFuture` ở một thread khác **không tự mang transaction T1 sang thread mới**. Method async có thể mở transaction của riêng nó nếu đi qua Spring proxy và có cấu hình phù hợp. Timeout của T1 không tự điều khiển deadline của transaction mới đó, và T1 rollback không mặc định rollback một transaction độc lập ở thread khác.

Với reactive programming (R2DBC, Project Reactor), Spring dùng **Reactor Context** cho reactive transactions thay vì thread-bound JDBC resources; cần áp dụng cơ chế timeout/cancellation của reactive pipeline phù hợp. Đừng sao chép kết luận về `Thread.sleep`/`JdbcTemplate` sang reactive chain mà không xem API thực tế.

## 8. Timeout, rollback và dữ liệu từ xa là ba câu hỏi khác nhau

| Câu hỏi | Cơ chế cần xem | Kết luận đúng |
| --- | --- | --- |
| Đã vượt ngân sách thời gian tổng thể? | Request deadline, tracing, elapsed time | Có thể quá hạn dù task vẫn chạy |
| JDBC statement bị dừng? | Spring JDBC timeout, driver, database query timeout | Phụ thuộc nơi kiểm tra deadline/driver |
| Local transaction đã rollback? | Transaction manager và kết quả commit/rollback | Chỉ đảm bảo cho resource tham gia transaction |
| HTTP client đã ngừng chờ? | HTTP request/call timeout | Chưa chứng minh remote server chưa xử lý |
| Worker Java đã thực sự dừng? | Thread/cancellation state, task completion | Timeout của future/caller không tự chứng minh |
| Tác dụng phụ remote đã bị hủy? | Protocol/idempotency/compensation/remote status | JDBC rollback không trả lời câu hỏi này |

### 8.1. Không bắt timeout rồi trả thành công giả

Mã sai về mặt nghiệp vụ:

```java
@Transactional(timeout = 1)
public void updateOrder() {
    repository.writeFirstStep();
    try {
        repository.writeSecondStep(); // Có thể phát sinh timeout.
    } catch (RuntimeException ex) {
        // Sai: nuốt lỗi rồi return như giao dịch thành công.
    }
}
```

Đây là **minh họa**. Khi SQL đã timeout hoặc database báo lỗi, trạng thái transaction có thể đã rollback-only hoặc tài nguyên không còn an toàn để tiếp tục. Nếu catch và swallow, caller có thể thấy một kết quả thành công giả; commit sau đó có thể thất bại. Cách đơn giản và dễ dự đoán là **cho lỗi thoát qua transaction boundary**, rollback rồi xử lý ở lớp orchestrator/caller. Retry (nếu phù hợp) trong **transaction mới**, có idempotency.

### 8.2. Timeout không thay thế business deadline

Ví dụ thanh toán có ngân sách 3 giây tổng:

```text
Gateway deadline:                     3000 ms
  Kiểm tra local/validation:           150 ms
  Remote API với request timeout:     1200 ms
  Transaction DB ngắn:                 500 ms
  Buffer để commit và trả response:    còn lại
```

Các số chỉ là **ví dụ thiết kế**, không phải SLO khuyến nghị chung. Một hệ thống cần đo latency thực tế để phân bổ ngân sách. Không giữ transaction database mở trong suốt một HTTP call chậm nếu thiết kế cho phép tách ngoài transaction. Nếu cần trạng thái nhất quán giữa database và remote API, hãy xem saga/compensation, transactional outbox và idempotency.

### 8.3. Nếu remote gọi thành công nhưng DB rollback thì sao?

Có thể xảy ra:

```text
T1 local bắt đầu
  |
  +-- HTTP POST remote tạo resource thành công
  |
  +-- Java tiếp tục, JDBC statement kiểm tra deadline đã hết
  |
  +-- Local T1 rollback
  |
  +-- Remote resource vẫn có thể tồn tại
```

Không thể khắc phục bằng cách tăng `@Transactional(timeout=...)`. Cần contract về việc tạo/hủy remote resource, idempotency keys, trạng thái giao dịch nghiệp vụ, outbox/saga hoặc thiết kế workflow theo các bước bền vững.

## 9. Thiết kế transaction boundary ngắn, timeout nhiều tầng

### 9.1. Tránh remote I/O lâu bên trong transaction

Mẫu rủi ro:

```java
@Transactional(timeout = 5)
public void placeOrder() {
    repository.reserveItems();
    remoteShippingApi.createShipment(); // Có thể block dài.
    repository.markReady();
}
```

**Mã minh họa:** class/dependencies chưa được định nghĩa. Vấn đề không chỉ ở timeout: transaction có thể giữ connection và row locks khi chờ remote, tăng lock contention, pool starvation và nguy cơ side effect remote không rollback.

Thiết kế thay thế (ở mức workflow):

```text
1. Validate đầu vào, lấy dữ liệu tham chiếu (không giữ DB lock quá lâu).
2. Mở transaction NGẮN.
3. Ghi order + outbox event atomically, commit.
4. Worker/outbox publisher gọi remote với HTTP timeout/retry/idempotency.
5. Lưu trạng thái remote operation, retry/compensate nếu cần.
```

Không phải mọi dự án đều cần outbox; nhưng nếu một side effect phải xảy ra **sau commit** và cần đảm bảo delivery, đây là hướng phù hợp hơn việc giữ một transaction JDBC mở khi chờ mạng.

### 9.2. Chọn timeout theo cấp độ

- **Database statement/query timeout** đủ ngắn để hạn chế truy vấn kẹt; thêm lock timeout khi DB hỗ trợ.
- **Transaction timeout** phù hợp chi phí của phần DB transaction thật sự. Đừng cấu hình như một yêu cầu ngắt mọi Java work.
- **HTTP request/call timeout** độc lập, rõ loại timeout (connect/read/total) theo thư viện cụ thể.
- **End-to-end request deadline** bao gồm nhiều bước và mọi retry, có buffer cho commit/cleanup.
- **Cancellation propagation** và error handling khi caller rời đi; tránh để worker tiếp tục side effect vô hạn.
- **Idempotency + trạng thái cuối** cho các lệnh có side effect bên ngoài transaction.

Đặt số liệu cụ thể dựa trên percentile latency, contention, SLO và retry budget thực tế; không có «timeout=3» đúng cho mọi hệ thống.

## 10. Những lỗi phổ biến khi dùng `@Transactional(timeout = ...)`

### Lỗi 1 — «Hết timeout là Thread bị Spring interrupt»

Không. Spring transaction interceptor không mặc định gửi `Thread.interrupt()` cho mọi đoạn Java đang chạy. Demo dùng `Thread.sleep(1400)` với `timeout=1` để quan sát Java tiếp tục thực thi sau deadline.

### Lỗi 2 — «HTTP call trong transaction tự mang cùng timeout»

Không. `HttpClient`, WebClient, RestClient hoặc thư viện khác cần timeout riêng. Chỉ thay transaction timeout không đủ khi remote service chậm.

### Lỗi 3 — «Có timeout thì không thể commit bất kỳ thứ gì sau deadline»

Không có quy tắc phổ quát như vậy trên mọi manager/driver. Hệ JDBC local có thể kiểm tra deadline khi tạo statement, không nhất thiết có một watchdog chủ động hủy toàn bộ transaction ngay lúc hết hạn. Case 1 minh họa Java hoàn thành dù deadline đã trôi qua. Luôn kiểm tra kết quả thực tế và cấu hình DB.

### Lỗi 4 — «Inner `REQUIRED(timeout=1)` luôn có deadline mới»

Không. Một inner `REQUIRED` tham gia physical transaction của outer không có independent physical deadline chỉ vì thêm annotation. `timeout` nhắm tới transaction **mới được tạo**, `REQUIRES_NEW` có thể tạo transaction riêng với timeout riêng.

### Lỗi 5 — «JDBC timeout đảm bảo HTTP side effect bị hoàn tác»

Không. JDBC rollback chỉ tác động tới JDBC resource tham gia transaction. Cần idempotency/compensation/remote protocol riêng.

### Lỗi 6 — «Cứ catch `TransactionTimedOutException` rồi tiếp tục commit»

Không an toàn. Exception timeout có thể cho thấy transaction/resource đang ở trạng thái lỗi hoặc rollback-only. Hãy để lỗi đi qua transaction boundary và thiết kế retry tại caller, bắt đầu transaction mới nếu hợp lệ.

### Lỗi 7 — «`Future.orTimeout` có nghĩa task đã dừng»

Không đảm bảo. Future có thể hoàn thành đặc biệt trong khi worker/remote operation vẫn đang chạy. Cần hợp tác cancellation và quan sát trạng thái thực.

### Lỗi 8 — «Có annotation là timeout hoạt động»

Không nếu method không được Spring transaction infrastructure intercept: self-invocation trong cùng bean, object tạo bằng `new`, method/class không thể proxy, bean do context khác quản lý, hoặc manager/tài nguyên không phù hợp. Đầu tiên hãy kiểm tra bean được Spring quản lý và caller gọi **qua proxy**.

### Lỗi 9 — «Hết transaction timeout sẽ rollback mọi công việc trong hệ thống»

Không. Cùng một use case có thể gọi nhiều database, phát message và chạy async task; không phải mọi tác vụ cùng tham gia một transaction. Hãy vẽ rõ physical transactions và side-effect boundaries.

### Lỗi 10 — «Gateway đã trả lỗi nên backend chắc chắn dừng»

Không. Timeout ở proxy/gateway có thể chỉ dừng thời gian **chờ response**; backend worker có thể tiếp tục hoặc remote side effect đã được thực hiện. Điều tra bằng request IDs, trace, idempotency key và transaction audit.

## 11. Tự kiểm tra, bài tập và kiểm thử

### Bài tập 1 — Đọc output demo

Trong case 2, tại sao có dòng:

```text
Java continued, trying another JDBC write
```

**trước** dòng `Outcome: TransactionTimedOutException`? Hãy giải thích nơi Spring kiểm tra deadline trong đường đi của JDBC statement.

### Bài tập 2 — Bỏ JDBC statement thứ hai

Sửa `jdbcAfterDeadline()` để không gọi `jdbc.update(...)` sau `pause(1400)`, rồi chạy lại. Quan sát output/DB trong môi trường H2 local; giải thích vì sao timeout không phải một watchdog hủy Java công việc. Không suy rộng kết quả đó sang JTA/database driver khác.

### Bài tập 3 — Giảm Java delay

Đổi sleep từ 1400 ms xuống 100 ms với `timeout=1`. Trong một môi trường bình thường, statement thứ hai có thể chạy trước deadline và transaction commit. Khi viết test, đừng dùng mốc thời gian quá sát deadline vì scheduler, máy chậm và CI có thể tạo flakiness.

### Bài tập 4 — Transaction timeout so với HTTP timeout

Cho một service có `@Transactional(timeout=2)` nhưng HTTP request timeout 6 giây. Nếu remote call mất 5 giây, những gì **có thể** xảy ra với HTTP response, Java execution và lệnh JDBC kế tiếp? Tách câu trả lời cho từng lớp thay vì nói «toàn bộ request bị hủy sau 2 giây».

### Bài tập 5 — Thử query timeout có chủ đích

Trong database test, chạy một SQL chậm được driver/database hỗ trợ với transaction timeout ngắn. Ghi nhận loại exception, thời gian thực tế và rollback. Không khẳng định `Statement.setQueryTimeout` được mọi driver thực thi chính xác theo cùng số mili giây.

### Bài tập 6 — Interruption

Trong một bản sao demo, interrupt worker khi đang sleep. Xác minh `InterruptedException`, khôi phục interrupted flag và rollback nếu ném unchecked exception qua transaction interceptor. Phân biệt thí nghiệm này với transaction timeout: **interrupt do test gửi**, không phải do `@Transactional(timeout=...)` tự sinh.

### Bài tập 7 — Thiết kế theo deadline

Một HTTP endpoint có ngân sách tổng 4 giây, gồm validation, một outbound HTTP call, DB transaction, retry và trả response. Hãy vẽ timeline và phân bổ timeout với buffer. Đảm bảo tổng retry budget không vượt deadline, xử lý idempotency nếu outbound call có side effect.

### Checklist kiểm tra production

| Câu hỏi | Cách xác minh |
| --- | --- |
| `@Transactional` có thực sự được intercept? | Bean từ Spring, đúng ApplicationContext, proxy/call path |
| Manager nào xử lý timeout? | `PlatformTransactionManager` và datasource thực |
| Timeout đang áp dụng cho transaction mới hay đang join? | Propagation `REQUIRED` / `REQUIRES_NEW` |
| JDBC dùng transaction-bound connection? | `JdbcTemplate` / `DataSourceUtils`; không tùy tiện lấy connection ngoài manager |
| Statement/query timeout hoạt động ra sao trên driver thật? | Integration test, SQL log, database metrics |
| HTTP client đã đặt connect/request timeout? | Cấu hình HTTP client và test slow endpoint |
| Retry có budget và idempotency không? | Trace request ID, status, số side effects |
| Timeout exception có thoát qua transaction boundary không? | Transaction logs và rollback outcome |
| Worker có thật sự dừng khi caller timeout? | Thread/task lifecycle, async job state |
| Remote side effect có còn tồn tại sau DB rollback? | Đọc trạng thái remote/reconciliation thay vì đoán |

## 12. Ghi nhớ

`@Transactional(timeout = n)` là **thời hạn cho giao dịch được transaction manager quản lý**, chủ yếu có tác dụng thông qua những tài nguyên tham gia transaction và cơ chế của manager/driver. Nó **không phải công tắc tự hủy Java thread**, không áp timeout cho mọi HTTP call và không thu hồi các side effects ở hệ thống xa.

Muốn một use case có giới hạn thời gian an toàn, hãy phối hợp **transaction timeout, JDBC statement/database timeout, HTTP request timeout, end-to-end deadline, cooperative cancellation, rollback/error handling và idempotency**. Chọn transaction boundary ngắn, không giữ database locks trong lúc chờ mạng dài, và kiểm thử cả **điều gì đã được commit** lẫn **tác vụ nào vẫn đang chạy** khi timeout xảy ra.

## 13. Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html) — `timeout` tính bằng giây; chỉ áp dụng cho transaction mới (`REQUIRED`/`REQUIRES_NEW` theo ngữ cảnh); rollback rules.
- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html) — `DataSourceTransactionManager`/`DataSourceUtils`, transaction-bound connection và JDBC statement query timeout.
- [Spring Framework — `DataSourceUtils` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html) — `applyTransactionTimeout(...)` và `applyTimeout(...)`.
- [Spring Framework — `ResourceHolderSupport` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/ResourceHolderSupport.html) — deadline và `TransactionTimedOutException` khi không còn thời gian.
- [Spring Framework — `@Transactional` API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html) — định nghĩa thuộc tính `timeout`.
- [Java 17 — `HttpClient` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html) và [`HttpRequest.Builder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html) — timeout cho kết nối/request.
- [Java 17 — `Thread` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html) — interruption; cooperative cancellation.
