# timeout, timeoutString và cấu hình qua placeholder trong @Transactional

> **Ngữ cảnh:** Spring Framework — Transaction Management — `@Transactional`. Bài này giải thích hai thuộc tính `timeout`, `timeoutString`, cách đưa số giây từ cấu hình bên ngoài qua placeholder, cơ chế thực thi thật sự, ảnh hưởng của propagation, các trường hợp timeout không có hiệu lực và cách kiểm chứng cấu hình. Ví dụ chạy với **Java 17**, **Spring Boot 3.5.7 / Spring Framework 6.2**, **JDBC/H2**, nhưng các nguyên tắc nền tảng áp dụng cho Spring Framework khi dùng transaction manager phù hợp.

## 1. Transaction timeout là gì và giải quyết vấn đề nào?

Một giao dịch mở quá lâu có thể giữ kết nối database, lock và tài nguyên khác, làm tăng contention, nguy cơ deadlock, chậm truy vấn và cạn connection pool. **Transaction timeout** là một giới hạn thời gian mà transaction manager/tài nguyên giao dịch có thể dùng để kiểm soát một transaction.

Ví dụ nghiệp vụ cần chuyển trạng thái đơn hàng và ghi bản ghi kiểm toán trong cùng một giao dịch. Để tránh thao tác database giữ tài nguyên không giới hạn, ta có thể khai báo:

```java
@Transactional(timeout = 5)
public void confirmOrder(long orderId) {
    // Các thao tác database qua repository/JdbcTemplate.
}
```

`timeout = 5` có nghĩa là cấu hình transaction timeout bằng **5 giây** cho **giao dịch mới** do lời gọi này bắt đầu. Đây là metadata của Spring: mức độ thực thi hạn chót phụ thuộc transaction manager, JDBC driver, database và loại công việc. Không nên hiểu nó là một bộ đếm tự động kill Java method đúng tại giây thứ năm.

Phân biệt ngay từ đầu:

| Giới hạn | Phạm vi | Ví dụ |
| --- | --- | --- |
| Transaction timeout | Transaction do Spring transaction manager quản lý | `@Transactional(timeout = 5)` |
| Query/statement timeout | Một câu SQL/JDBC statement | `Statement.setQueryTimeout(3)` |
| Connection acquisition timeout | Thời gian chờ lấy connection từ pool | Cấu hình HikariCP `connectionTimeout` |
| Network connect/read timeout | Kết nối/đọc HTTP hay socket | HTTP client timeout |
| Request deadline | Toàn bộ yêu cầu API, gồm nhiều bước | Deadline ở server/gateway/application |
| Lock timeout | Thời gian chờ một lock trong database | Tham số riêng của PostgreSQL, MySQL, v.v. |

**Không một timeout nào tự thay thế các timeout còn lại.** Một transaction có thể chờ lock; HTTP client có thể timeout; và đoạn Java có thể tính toán lâu ngay cả khi Spring đã khai báo giới hạn giao dịch.

## 2. Hai thuộc tính: `timeout` và `timeoutString`

`@Transactional` dùng ở đây là `org.springframework.transaction.annotation.Transactional` của **Spring**, không phải annotation JTA `jakarta.transaction.Transactional` (JTA không cung cấp hai thuộc tính này theo cùng API).

### 2.1. `timeout`: số nguyên cố định trong source

```java
import org.springframework.transaction.annotation.Transactional;

@Transactional(timeout = 10)
public void importSmallBatch() {
    // Transaction timeout được khai báo là 10 giây.
}
```

- Kiểu Java: `int`.
- Đơn vị: **giây**, không phải mili giây, `Duration` hoặc phút.
- Dùng khi muốn con số rõ ràng, ổn định ngay trong code.
- Giá trị mặc định của annotation: `TransactionDefinition.TIMEOUT_DEFAULT`, tức **-1**, biểu thị dùng timeout mặc định của transaction infrastructure (có thể không giới hạn nếu hệ thống không hỗ trợ timeout).
- Vì đây là phần tử annotation kiểu `int`, giá trị phải là **compile-time constant**. Có thể dùng literal `10` hoặc một hằng số `static final int` hợp lệ; không đưa chuỗi placeholder hay giá trị `@Value` vào đây.

### 2.2. `timeoutString`: chuỗi biểu diễn số giây

```java
@Transactional(timeoutString = "10")
public void importSmallBatch() {
    // Timeout 10 giây, được biểu diễn bằng String.
}
```

`timeoutString` có ý nghĩa về **số giây** giống `timeout` nhưng kiểu Java là `String`. Thuộc tính này được giới thiệu ở **Spring Framework 5.3**; lợi ích lớn nhất là có thể dùng placeholder:

```java
@Transactional(timeoutString = "${app.tx.import-seconds}")
public void importSmallBatch() {
    // Lấy timeout từ cấu hình đã được Spring resolve.
}
```

Sau khi Spring resolve, kết quả phải chuyển được thành **số giây nguyên hợp lệ**. Ví dụ `"10"` hợp lệ; `"10s"`, `"PT10S"`, `"500ms"` không phải dạng số giây nguyên được trông đợi bởi thuộc tính này. Muốn cấu hình theo kiểu `Duration` ở nơi khác thì hãy chuyển đổi có kiểm soát sang số giây trước khi áp dụng bằng API chương trình thích hợp.

### 2.3. Bảng so sánh nhanh

| Tiêu chí | `timeout` | `timeoutString` |
| --- | --- | --- |
| Kiểu thuộc tính | `int` | `String` |
| Đơn vị | Giây | Giây |
| Dạng cố định | `timeout = 10` | `timeoutString = "10"` |
| Placeholder `${...}` | Không thể gán vào `int` | Có |
| Giá trị mặc định của annotation | `-1` | Chuỗi rỗng `""` |
| Dùng cho môi trường dev/staging/prod khác nhau | Phải điều chỉnh source hoặc cơ chế khác | Đổi config/property |
| Cơ chế thời hạn sau khi resolve | Cùng transaction timeout semantics | Cùng transaction timeout semantics |

**Chọn đúng một trong hai** để đặt timeout cụ thể cho một `@Transactional`. Đừng khai báo đồng thời `timeout = 5` và `timeoutString = "7"`: Spring coi đây là khai báo xung đột và từ chối cấu hình thay vì ngầm chọn một giá trị.

## 3. Placeholder `${...}` giải quyết bài toán gì?

Nhiều hệ thống cần timeout khác nhau giữa local, staging và production, hoặc cần điều chỉnh sau khi quan sát hiệu năng. Nếu ghi cứng `@Transactional(timeout = 5)`, thay đổi giá trị thường đòi sửa Java code và build lại. Với `timeoutString`, chính sách được đặt trong property:

```java
@Service
public class ExportService {

    @Transactional(timeoutString = "${app.transaction.export-timeout-seconds}")
    public void exportToDatabase() {
        // Các thao tác trong transaction.
    }
}
```

```properties
# src/main/resources/application.properties
app.transaction.export-timeout-seconds=15
```

Khi transaction attribute được Spring phân tích và resolve, `${app.transaction.export-timeout-seconds}` trở thành `"15"`, rồi được diễn giải là **15 giây**.

Bạn cũng có thể khai báo **giá trị dự phòng ngay trong placeholder**:

```java
@Transactional(timeoutString = "${app.transaction.export-timeout-seconds:15}")
public void exportToDatabase() {
    // Dùng 15 giây nếu property không được cung cấp.
}
```

Cú pháp `${key:default}` là cú pháp placeholder của Spring; phần `:15` là giá trị dùng khi không tìm thấy khóa. Tránh dùng giá trị dự phòng thiếu kiểm soát ở nghiệp vụ rất nhạy cảm: cần biết ứng dụng đang dùng giá trị thực sự nào.

### 3.1. Ngoại hóa theo môi trường

Ví dụ với Spring Boot:

```properties
# application.properties
app.tx.checkout-seconds=8
app.tx.report-seconds=30
```

```java
@Transactional(timeoutString = "${app.tx.checkout-seconds:8}")
public void checkout() {
    // Transaction tối đa theo cấu hình checkout.
}

@Transactional(timeoutString = "${app.tx.report-seconds:30}",
               readOnly = true)
public void buildReport() {
    // Transaction báo cáo.
}
```

Trên production có thể thay `app.tx.checkout-seconds` bằng biến môi trường tương thích với cách Spring Boot ánh xạ property, hoặc truyền command line argument:

```bash
java -jar target/transaction-timeout-demo-1.0.0.jar \
  --app.tx.checkout-seconds=12
```

Lệnh minh họa này dành cho shell hỗ trợ dấu `\` nối dòng (như Bash); trên PowerShell/Windows có thể viết **một dòng**. CLI của Boot ưu tiên nguồn cấu hình phù hợp với property precedence. Việc một môi trường có giá trị cao hơn môi trường khác **không làm thay đổi source annotation**.

### 3.2. Đặt environment variable rõ ràng

Có thể trung gian qua một biến môi trường có tên riêng:

```properties
# application.properties
app.tx.checkout-seconds=${CHECKOUT_TX_SECONDS:8}
```

```java
@Transactional(timeoutString = "${app.tx.checkout-seconds}")
public void checkout() {
    // 8 giây theo default khi không khai báo CHECKOUT_TX_SECONDS.
}
```

Ví dụ đặt `CHECKOUT_TX_SECONDS=12` trước khi khởi động ứng dụng khiến placeholder cuối cùng resolve thành `12`. Tách cấu hình như vậy giúp bản thân annotation chỉ tham chiếu một key nghiệp vụ ổn định, còn cách cấp giá trị có thể do deployment quản lý.

### 3.3. Phân biệt thời điểm resolve với thời điểm bắt đầu transaction

Thông thường, `timeoutString` được Spring resolve từ configuration/environment khi hạ tầng xác định transaction attribute và cache thông tin phương thức. Nó **không phải biểu thức được tính lại theo mỗi HTTP request hoặc mỗi bản ghi**.

Đổi file `application.properties` trên đĩa khi JVM đang chạy **không mặc nhiên khiến timeout của annotation đang dùng đổi ngay**. Cần một cơ chế refresh/recreate bean và transaction metadata phù hợp, hoặc thường đơn giản hơn là cập nhật cấu hình rồi khởi động lại/redeploy. Nếu cần tính timeout theo dữ liệu của **mỗi lần gọi**, xem `TransactionTemplate` trong phần 9.

## 4. Quy tắc kết hợp với propagation và transaction sẵn có

Thông số timeout có ý nghĩa khi **một giao dịch mới thực sự được bắt đầu**. Đây là điều kiện quan trọng nhất để tránh đọc nhầm annotation.

`@Transactional` mặc định dùng `Propagation.REQUIRED`:

- **Không có transaction hiện tại:** `REQUIRED` mở một transaction mới. Timeout khai báo tại lời gọi đó có thể được áp dụng.
- **Đã có transaction hiện tại:** `REQUIRED` tham gia transaction có sẵn. Nó không mở transaction vật lý mới, vì vậy timeout khai báo tại phương thức tham gia **không đặt lại đồng hồ** hay tạo deadline mới.
- **`REQUIRES_NEW`:** tạm ngưng transaction hiện tại (nếu có) và mở transaction độc lập; timeout riêng của giao dịch mới có hiệu lực cho ranh giới mới đó. Phải hiểu tác động về connection pool, lock và commit/rollback độc lập.
- **`SUPPORTS`/`NOT_SUPPORTED`/`NEVER`:** không nên kỳ vọng timeout annotation tạo giới hạn transaction mới, vì các chế độ này không tạo transaction mới theo ý nghĩa cần thiết.
- **`NESTED`:** thông thường là savepoint bên trong cùng transaction JDBC; không phải một transaction vật lý mới với một đồng hồ độc lập.

### 4.1. Ví dụ: bên ngoài 30 giây, bên trong 5 giây

```java
@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional(timeout = 30)
    public void runJob() {
        inner.runPart();
    }
}

@Service
class InnerService {
    @Transactional(timeoutString = "${app.tx.part-seconds:5}")
    public void runPart() {
        // Mặc định REQUIRED: tham gia transaction của runJob().
    }
}
```

Đây là **trích đoạn minh họa**, cần được đặt trong ứng dụng Spring có transaction manager và proxy đúng cách. Nếu caller đi qua Spring proxy của `OuterService` và `InnerService`:

1. `OuterService.runJob()` tạo transaction mới với timeout 30 giây.
2. `InnerService.runPart()` được gọi qua proxy nhưng `REQUIRED` **tham gia transaction hiện có**.
3. Giá trị `5` của `runPart()` **không tự làm transaction đang tồn tại chỉ còn 5 giây**. Thời hạn ban đầu của transaction do `runJob()` tạo vẫn chi phối.

Nếu muốn công việc bên trong có một transaction độc lập, có thể khai báo:

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    timeoutString = "${app.tx.part-seconds:5}"
)
public void runPart() {
    // Giao dịch mới, có timeout riêng.
}
```

Cần import `org.springframework.transaction.annotation.Propagation`. `REQUIRES_NEW` **không phải cách mặc định để “ép timeout ngắn hơn”**: nó tạo transaction vật lý và ranh giới commit/rollback khác. Một transaction ngoài có thể rollback trong khi transaction bên trong đã commit, nên chỉ dùng khi tính độc lập đó phù hợp nghiệp vụ.

### 4.2. Mức class và mức method

```java
@Transactional(timeoutString = "${app.tx.default-seconds:15}")
@Service
class BillingService {

    public void regularOperation() {
        // Nhận transaction settings khai báo ở mức class,
        // nếu được gọi qua cơ chế transaction của Spring.
    }

    @Transactional(timeout = 3)
    public void urgentOperation() {
        // Annotation ở method ghi đè settings ở mức class.
    }
}
```

Một annotation cụ thể hơn trên method có **độ ưu tiên cao hơn** annotation ở class. Spring không tự “gộp thuộc tính timeout của method với timeoutString của class” thành hai giá trị mâu thuẫn: transaction attribute được xác định theo cấu hình áp dụng cho phương thức.

## 5. Timeout được thực thi như thế nào trong JDBC?

Với `DataSourceTransactionManager` hoặc `JdbcTransactionManager`, Spring quản lý một JDBC connection theo transaction. Khi khai báo timeout cho transaction mới, Spring lưu thông tin thời hạn vào ngữ cảnh connection/transaction. Các thao tác JDBC qua `JdbcTemplate` có thể lấy **thời gian còn lại** rồi đặt timeout cho `Statement` tương ứng.

Diễn biến khái quát:

```text
T=0s  Caller vào proxy của @Transactional(timeout=5)
      -> transaction manager bắt đầu transaction, lập hạn chót.

T=2s  JdbcTemplate tạo PreparedStatement
      -> Spring gắn query timeout theo thời gian còn lại.

T=5s  Hạn chót transaction đã tới.
      -> Truy cập database/kiểm tra hạn chót có thể thất bại.

Sau đó, transaction manager xử lý commit/rollback
theo exception, rollback-only và khả năng của tài nguyên.
```

Điều này **không có nghĩa** rằng Spring bắt buộc ngắt một CPU loop, `Thread.sleep`, lời gọi HTTP hay tiến trình con đúng lúc hết 5 giây. Với JDBC, timeout thường dựa vào query timeout của driver/database và kiểm tra trạng thái transaction khi framework tương tác với tài nguyên. Thời gian thực tế/loại exception khác nhau giữa driver, database và phương thức thực thi.

`JdbcTemplate` áp dụng timeout theo cơ chế JDBC của Spring. Nếu dùng JDBC mức thấp, code cần sử dụng connection nhận biết transaction (như `DataSourceUtils.getConnection`) và áp dụng deadline của transaction lên từng `Statement` bằng `DataSourceUtils.applyTransactionTimeout` hoặc một proxy datasource phù hợp.

Ví dụ **trích đoạn API**:

```java
Connection con = DataSourceUtils.getConnection(dataSource);
try {
    PreparedStatement stmt =
        con.prepareStatement("UPDATE jobs SET state = ? WHERE id = ?");
    try (stmt) {
        DataSourceUtils.applyTransactionTimeout(stmt, dataSource);
        stmt.setString(1, "DONE");
        stmt.setLong(2, jobId);
        stmt.executeUpdate();
    }
} finally {
    DataSourceUtils.releaseConnection(con, dataSource);
}
```

Đoạn trên giả định `dataSource`, `jobId` có sẵn; cần import `java.sql.Connection`, `java.sql.PreparedStatement` và `org.springframework.jdbc.datasource.DataSourceUtils`, chỉ nên đặt **bên trong transaction đã mở**. Dùng `JdbcTemplate` vẫn là cách ít lỗi hơn. Đừng tự `commit()`, `rollback()` hay `close()` connection do Spring đang quản lý.

### 5.1. Các exception có thể xuất hiện

Khi timeout thực sự được phát hiện, tùy cơ chế có thể gặp:

- `org.springframework.transaction.TransactionTimedOutException` khi Spring thấy thời hạn transaction đã hết.
- `org.springframework.dao.QueryTimeoutException` hoặc exception thuộc họ `DataAccessException` khi truy vấn bị timeout và được Spring dịch từ lỗi database.
- Một `SQLException` hoặc exception đặc thù driver/framework nếu tầng đó không được dịch như trên.
- Exception bổ sung ở bước commit/rollback nếu tài nguyên đang ở trạng thái lỗi hoặc đã đánh dấu rollback-only.

Vì vậy, **không hard-code kỳ vọng rằng mọi timeout đều ném chính xác `TransactionTimedOutException`**. Nếu unchecked exception thoát ra qua transaction interceptor, chính sách mặc định thường rollback transaction. Nếu bắt rồi nuốt lỗi ở bên trong, hoặc nếu database vẫn đang xử lý/có trạng thái không chắc chắn, phải xác minh kết quả và chính sách rollback thực tế.

### 5.2. Timeout không bảo đảm hủy side effect ngoài transaction

Giả sử phương thức `@Transactional(timeout = 5)` vừa cập nhật database A, vừa gọi HTTP thanh toán bên ngoài. Nếu request HTTP hoàn thành sau khi A hết hạn, rollback database A **không tự hoàn tác** khoản tiền tại hệ thống thanh toán. Muốn bảo đảm quy trình xuyên hệ thống cần chính sách timeout HTTP riêng, idempotency, trạng thái chưa xác định và đối soát/bù trừ theo nghiệp vụ.

## 6. Ví dụ Java 17 hoàn chỉnh: thấy timeout đã resolve từ property

**Mục tiêu của demo:** tạo hai transaction JDBC có annotation khác nhau, kiểm tra `timeout = 3` và `timeoutString` đã resolve thành `7` từ cấu hình, chứng minh phương thức gọi qua Spring bean thực sự có transaction, và ghi hai dòng dữ liệu thành công. Demo **không cố giả lập một SQL chậm bằng `Thread.sleep`**, vì đó không phải phép thử đáng tin cho cơ chế timeout JDBC.

Dự án cần JDK 17 và Maven 3.9+; không cần cài H2 riêng.

Cấu trúc:

```text
transaction-timeout-demo/
├── pom.xml
└── src/main/
    ├── java/vn/example/tx/
    │   ├── TimeoutDemoApplication.java
    │   └── AuditService.java
    └── resources/
        └── application.properties
```

### 6.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>vn.example</groupId>
    <artifactId>transaction-timeout-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot cấu hình một `DataSource` H2 và JDBC transaction manager phù hợp khi dependencies/điều kiện auto-configuration được đáp ứng. `@EnableTransactionManagement` trong ví dụ làm rõ ý định kích hoạt cơ chế transaction annotation.

### 6.2. `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:timeout_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

# Nếu không truyền biến môi trường, dùng 7 giây.
demo.tx.configured-seconds=${TX_TIMEOUT_SECONDS:7}
```

Key `demo.tx.configured-seconds` là tên do ứng dụng này tự đặt, **không phải** thuộc tính timeout mặc định có sẵn của Spring Boot. `${TX_TIMEOUT_SECONDS:7}` cho phép thay giá trị bằng môi trường mà không sửa Java code. Nếu không cung cấp biến môi trường, timeout cấu hình là 7 giây.

### 6.3. `src/main/java/vn/example/tx/AuditService.java`

```java
package vn.example.tx;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class AuditService {
    private final JdbcTemplate jdbc;

    public AuditService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(timeout = 3)
    public void saveFixed(long id, String details) {
        jdbc.update(
            "INSERT INTO audit_events(id, details) VALUES (?, ?)",
            id, details
        );
    }

    @Transactional(timeoutString = "${demo.tx.configured-seconds:7}")
    public boolean saveConfigured(long id, String details) {
        jdbc.update(
            "INSERT INTO audit_events(id, details) VALUES (?, ?)",
            id, details
        );
        return TransactionSynchronizationManager
            .isActualTransactionActive();
    }
}
```

Hai method khác nhau để dễ quan sát:

- `saveFixed()` dùng **timeout cố định 3 giây**.
- `saveConfigured()` dùng **timeoutString** lấy từ property, mặc định 7 giây nếu không cấu hình khác.
- `TransactionSynchronizationManager.isActualTransactionActive()` kiểm tra trạng thái transaction ở luồng hiện tại **khi method đang chạy**. Trả về `true` trong bối cảnh demo; đây là phép kiểm tra transaction có active, **không phải phép đo timeout đã được database cưỡng chế**.

### 6.4. `src/main/java/vn/example/tx/TimeoutDemoApplication.java`

```java
package vn.example.tx;

import java.lang.reflect.Method;
import java.util.Objects;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.interceptor.TransactionAttribute;
import org.springframework.transaction.interceptor.TransactionAttributeSource;

@SpringBootApplication
@EnableTransactionManagement
public class TimeoutDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(TimeoutDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner run(JdbcTemplate jdbc,
                          AuditService service,
                          TransactionAttributeSource attributes) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE audit_events (" +
                "id BIGINT PRIMARY KEY, " +
                "details VARCHAR(80) NOT NULL)"
            );

            service.saveFixed(1L, "fixed");
            boolean active = service.saveConfigured(2L, "configured");

            System.out.println("fixed-timeout-seconds=" +
                timeoutOf(attributes, "saveFixed"));
            System.out.println("configured-timeout-seconds=" +
                timeoutOf(attributes, "saveConfigured"));
            System.out.println("active-inside-transaction=" + active);
            System.out.println("rows=" + jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_events", Integer.class));
        };
    }

    private static int timeoutOf(TransactionAttributeSource source,
                                 String methodName)
            throws NoSuchMethodException {
        Method method = AuditService.class.getMethod(
            methodName, long.class, String.class
        );
        TransactionAttribute attribute =
            source.getTransactionAttribute(method, AuditService.class);

        return Objects.requireNonNull(attribute,
            "Missing transaction attribute for " + methodName
        ).getTimeout();
    }
}
```

Phương thức `timeoutOf` hỏi **transaction metadata đã được Spring xử lý**, không tự đọc chuỗi annotation bằng reflection thuần. `getTimeout()` trong `TransactionAttribute` cho biết số giây sau khi xử lý `timeoutString`. Điều này giúp kiểm chứng key property được resolve chính xác, nhưng vẫn cần integration test riêng để chứng minh database/driver thực sự áp dụng deadline khi truy vấn quá lâu.

Runner gọi `AuditService` qua một Spring bean khác, tránh lỗi self-invocation. Hai INSERT chạy trong transaction riêng và commit bình thường. `TransactionAttributeSource` được Spring cấu hình sẵn khi `@EnableTransactionManagement` hoạt động.

### 6.5. Chạy và đối chiếu

Từ thư mục dự án:

```bash
java -version
mvn -version
mvn -q package
java -jar target/transaction-timeout-demo-1.0.0.jar
```

**Khi không có biến môi trường `TX_TIMEOUT_SECONDS`**, các dòng do ứng dụng chủ động in ra là:

```text
fixed-timeout-seconds=3
configured-timeout-seconds=7
active-inside-transaction=true
rows=2
```

Spring Boot có thể in thêm log khởi động; chỉ các dòng trên là output nghiệp vụ có chủ đích.

Thử thay giá trị **khi khởi động** mà không sửa code:

```bash
java -jar target/transaction-timeout-demo-1.0.0.jar \
  --demo.tx.configured-seconds=12
```

Lúc này dòng `configured-timeout-seconds` thành **12**, còn `fixed-timeout-seconds` vẫn là **3**, `active-inside-transaction` vẫn `true` và `rows` vẫn **2**. Đối với PowerShell, viết câu lệnh `java -jar ... --demo.tx.configured-seconds=12` trên **một dòng**.

> **Cần phân biệt:** Demo kiểm tra **annotation và property resolution**, không mô phỏng hành vi hủy truy vấn tại chính xác giây thứ 3/7. Một integration test về timeout nên sử dụng database/driver thực tế và thao tác chờ lock hoặc truy vấn dài có kiểm soát, rồi xác nhận rollback, connection/lock được giải phóng và kiểu exception thực tế.

## 7. Khi nào timeout được dùng, khi nào bị bỏ qua?

| Tình huống | Timeout có tác dụng? | Giải thích |
| --- | --- | --- |
| Caller vào `@Transactional(timeout=5)`, trước đó chưa có transaction | **Có thể áp dụng** | `REQUIRED` mở transaction mới với giá trị 5. |
| Caller vào `@Transactional(timeoutString="${...}")`, đã resolve giá trị 8, không có transaction trước đó | **Có thể áp dụng** | Giống `timeout=8`, phụ thuộc manager/tài nguyên. |
| Transaction 30 giây đã tồn tại; inner method `REQUIRED` khai báo timeout 5 giây | **Không reset thành 5** | Inner tham gia transaction cũ. |
| Inner `REQUIRES_NEW` khai báo timeout 5 giây | **Có cho transaction mới** | Outer transaction được tạm ngưng; inner có ranh giới riêng. |
| Gọi `this.innerMethod()` trong cùng bean qua proxy mode mặc định | **Có thể không có giao dịch mới như mong đợi** | Lời gọi không đi qua Spring proxy. |
| Dùng `Thread.sleep(20000)` trong method timeout 5 giây | **Không bảo đảm thread bị cắt tại 5 giây** | Transaction timeout không phải thread interruption timer. |
| Dùng `JdbcTemplate` với `JdbcTransactionManager`/`DataSourceTransactionManager` | **Được tích hợp vào JDBC statement** | Có thể truyền thời gian còn lại cho query timeout. |
| Dùng connection/statement JDBC raw không transaction-aware | **Có thể không áp dụng đầy đủ** | Phải bảo đảm sử dụng connection/statement do Spring quản lý. |
| Gọi HTTP/email trong transaction JDBC | **Không tự đặt timeout mạng hay rollback remote side effect** | Cần deadline/client timeout, chống trùng và compensation riêng. |
| Không khai báo timeout ở annotation | Theo **manager/system default** | Không mặc nhiên là một giá trị cố định giống nhau trên mọi hệ thống. |

Cụm “có thể áp dụng” trong bảng nhấn mạnh rằng annotation cung cấp **ý định transaction timeout**; mức độ cưỡng chế phụ thuộc transaction manager, database, driver và cách truy cập tài nguyên.

## 8. Cấu hình timeout mặc định ở transaction manager

Khi nhiều method không khai báo `timeout`/`timeoutString`, có thể muốn có chính sách mặc định. Với một manager kế thừa `AbstractPlatformTransactionManager`, cấu hình ví dụ:

```java
@Configuration
@EnableTransactionManagement
class TransactionConfig {

    @Bean
    JdbcTransactionManager transactionManager(DataSource dataSource) {
        JdbcTransactionManager manager =
            new JdbcTransactionManager(dataSource);
        manager.setDefaultTimeout(20);
        return manager;
    }
}
```

Đây là **trích đoạn cấu hình riêng**, cần import `javax.sql.DataSource`, `org.springframework.context.annotation.Bean`, `org.springframework.context.annotation.Configuration`, `org.springframework.transaction.annotation.EnableTransactionManagement` và `org.springframework.jdbc.support.JdbcTransactionManager`. Nó minh họa timeout mặc định **20 giây** của manager; **không chép thêm vào demo phần 6** vì Spring Boot trong demo đang auto-configure transaction manager.

Quy tắc lựa chọn:

1. Nếu method khai báo `@Transactional(timeout=3)`, giá trị 3 áp dụng khi method mở giao dịch mới.
2. Nếu method khai báo `@Transactional(timeoutString="${...}")` và property resolve thành 7, giá trị 7 áp dụng khi method mở giao dịch mới.
3. Nếu method chỉ `@Transactional`, manager có thể sử dụng `defaultTimeout=20`.
4. Nếu manager cũng không cấu hình timeout, hệ thống dùng timeout mặc định của underlying transaction infrastructure, hoặc không có timeout nếu tài nguyên không hỗ trợ.

Một thuộc tính **tự đặt** như `app.tx.default-seconds` không tự làm transaction manager đọc giá trị đó; phải gắn vào annotation hoặc truyền nó vào cấu hình manager bằng code.

## 9. Timeout tính ở runtime: `TransactionTemplate`

`@Transactional(timeoutString = "${...}")` phù hợp cho một **giá trị cấu hình của ứng dụng**. Nếu mỗi batch có SLA khác nhau dựa trên tham số gọi, dùng API lập trình có thể phù hợp hơn.

**Trích đoạn minh họa**, giả định có `PlatformTransactionManager manager` và `JdbcTemplate jdbc`:

```java
public void processBatch(int timeoutSeconds) {
    if (timeoutSeconds < 1 || timeoutSeconds > 300) {
        throw new IllegalArgumentException(
            "timeoutSeconds must be 1..300"
        );
    }

    TransactionTemplate tx = new TransactionTemplate(manager);
    tx.setTimeout(timeoutSeconds);
    tx.executeWithoutResult(status -> {
        jdbc.update(
            "UPDATE batch_jobs SET state = 'RUNNING' WHERE id = 42"
        );
    });
}
```

Cần import `org.springframework.transaction.support.TransactionTemplate`. Khác với annotation cố định, `setTimeout(timeoutSeconds)` nhận giá trị runtime. Tuy nhiên, nếu callback **tham gia** transaction hiện có (propagation `REQUIRED` mặc định), timeout mới cũng không tự thu ngắn deadline vật lý ban đầu. Nếu cần một giao dịch mới độc lập, phải thiết kế propagation, commit/rollback, tài nguyên và ảnh hưởng đồng thời cho đúng.

Dùng một `TransactionTemplate` riêng theo lần gọi như trên giúp tránh chia sẻ/chỉnh timeout của cùng một đối tượng template có trạng thái cấu hình giữa nhiều luồng. Giới hạn input để tránh các giá trị không hợp lệ hoặc cấu hình SLA không kiểm soát.

## 10. Lỗi và ngộ nhận thường gặp

### 10.1. Dùng placeholder cho `timeout` kiểu `int`

**Sai cú pháp Java:**

```java
@Transactional(timeout = "${app.tx.seconds}")
public void work() {
}
```

`timeout` đòi `int`, nên source không compile vì literal đang là `String`. **Đúng** là:

```java
@Transactional(timeoutString = "${app.tx.seconds:5}")
public void work() {
}
```

### 10.2. Khai báo đồng thời hai giá trị

**Sai về transaction metadata:**

```java
@Transactional(timeout = 5, timeoutString = "${app.tx.seconds:8}")
public void work() {
}
```

Không dùng cả hai trên cùng annotation với hai giá trị thực; Spring parser có thể ném lỗi `Specify 'timeout' or 'timeoutString', not both` khi đọc transaction metadata. Hãy chọn một thuộc tính.

### 10.3. Nhầm đơn vị

**Không đúng** nếu muốn 5 giây: `@Transactional(timeout=5000)`, vì đây là **5.000 giây**, không phải 5.000 mili giây. Viết `timeout=5` hoặc `timeoutString="5"`.

### 10.4. Property thiếu hoặc không phải số nguyên

```java
@Transactional(timeoutString = "${app.tx.seconds}")
public void work() {
}
```

Nếu `app.tx.seconds` không tồn tại, không có default và không được resolve, hoặc nhận giá trị chữ như `"fast"`, Spring có thể báo lỗi trong giai đoạn xử lý transaction attribute/khởi tạo hoặc khi method lần đầu được dùng. Không dựa vào thời điểm lỗi chính xác; hãy kiểm tra property trong startup/integration test, ưu tiên default rõ ràng và validation cấu hình ở đầu vào deployment.

### 10.5. Dùng `@Value` như thể là giá trị annotation

```java
@Value("${app.tx.seconds}")
private int seconds;
```

Field `seconds` có thể được inject, nhưng Java không cho viết `@Transactional(timeout = seconds)`: phần tử annotation cần compile-time constant. `@Value` và `timeoutString` là hai cơ chế khác nhau; với annotation, dùng placeholder qua `timeoutString`.

### 10.6. Phương thức inner tham gia transaction sẵn có

Một inner method được annotation với `timeout=1` không bảo đảm phần gọi đó thất bại sau 1 giây khi nó tham gia transaction outer 60 giây. Kiểm tra call graph, proxy boundary và propagation trước khi kết luận Spring “bỏ qua timeout”.

### 10.7. Dùng `Thread.sleep` để “chứng minh timeout”

```java
@Transactional(timeout = 1)
public void slowCpuWork() throws InterruptedException {
    Thread.sleep(5000);
}
```

Đây là **trích đoạn minh họa phản ví dụ**, không nên dùng làm kiểm thử transaction timeout. Tác vụ ngủ không bắt buộc bị Spring cắt sau 1 giây. Chỉ một JDBC operation thực sự có kiểm tra hoặc áp dụng deadline mới có thể quan sát lỗi liên quan; việc commit sau thời hạn cũng tùy manager/tài nguyên. Đừng suy ra 5 giây ngủ tương đương 5 giây SQL chờ.

### 10.8. Bắt exception rồi trả success

Ví dụ bắt `DataAccessException` và bỏ qua khiến interceptor không thấy exception thoát ra; tùy manager/tình trạng transaction, có thể không rollback theo kỳ vọng hoặc có rollback-only. Cần định nghĩa rõ lỗi timeout là thất bại nghiệp vụ, ném lỗi thích hợp hoặc đánh dấu rollback-only có chủ đích; không giả định tất cả trạng thái đều an toàn sau khi nuốt exception.

### 10.9. Nhầm request timeout với transaction timeout

Gateway timeout ở giây 10 không chứng minh database transaction bị rollback tại giây 10. Client ngắt kết nối có thể không dừng công việc server. Thiết kế timeout đồng bộ gồm HTTP client/server, queue wait, pool wait, database query/lock và transaction deadline cần nhất quán nhưng **là các cơ chế khác nhau**.

### 10.10. Gọi service khác hoặc chạy `@Async`

Transaction imperative của Spring thường gắn với thread hiện tại; việc khởi chạy thread khác hoặc `@Async` không tự mang theo ranh giới transaction và deadline của caller. Lời gọi đến microservice khác cũng không trở thành participant chỉ nhờ annotation. Thiết kế transaction mới ở nơi xử lý, deadline truyền qua API nếu có hợp đồng, và idempotency cho side effect.

## 11. Cách kiểm thử timeout có ý nghĩa

### Kiểm thử mức cấu hình

- Với property `app.tx.seconds=8`, xác nhận transaction metadata cho method sử dụng `timeoutString` resolve thành **8**; thay thành **12** và xác nhận thành 12 sau khi tạo application context tương ứng.
- Xác nhận method `timeout=3` luôn có metadata 3 bất kể property.
- Xác nhận một property không hợp lệ/thiếu bị phát hiện theo chính sách khởi động/test của bạn.
- Xác nhận hai thuộc tính cùng khai báo là một lỗi cấu hình cần sửa, không chấp nhận kết quả ngầm.

### Kiểm thử mức transaction

Dùng PostgreSQL/MySQL hoặc đúng database/driver production trong integration test, với một tình huống **chờ lock/truy vấn dài có kiểm soát**, rồi:

1. Gọi bean service qua Spring proxy, bảo đảm method tạo transaction mới thay vì tham gia transaction đã có.
2. Cấu hình timeout đủ ngắn để phép thử có thời gian giới hạn, nhưng tránh ngưỡng quá nhỏ khiến test bị flake.
3. Kiểm tra loại exception xảy ra trong **stack cụ thể** thay vì hard-code một loại cho mọi database.
4. Kiểm tra transaction đã rollback bằng cách đọc từ connection/transaction khác.
5. Xác nhận connection/lock được giải phóng và các request khác không bị kẹt.
6. Thử thêm một inner `REQUIRED` và inner `REQUIRES_NEW` để thấy deadline khác nhau theo transaction boundary.
7. Nếu test method của Spring Test tự có `@Transactional`, kiểm tra xem service có đang **join transaction của test**; điều này có thể làm timeout annotation trên service không được áp dụng như bạn tưởng.

Nếu dùng `Thread.sleep` để mô phỏng công việc CPU, hãy coi đó là test khả năng xử lý khác, **không phải bằng chứng transaction timeout cưỡng chế SQL**.

### Quan sát vận hành

Khi có lỗi timeout, log kèm transaction name, request/correlation ID, thời gian đã chạy, tên database/pool, exception class và ngữ cảnh retry. Đo số transaction dài, lock wait, query timeout, số connection đang chờ và tỷ lệ rollback. Đừng log secret, SQL chứa dữ liệu nhạy cảm hoặc payload người dùng không cần thiết.

## 12. Checklist chọn và áp dụng timeout

- [ ] Dùng đúng `org.springframework.transaction.annotation.Transactional` của Spring.
- [ ] Chọn `timeout = n` cho giá trị số giây cố định hoặc `timeoutString = "${key:default}"` cho cấu hình bên ngoài.
- [ ] Không đồng thời khai báo `timeout` và `timeoutString`.
- [ ] Giá trị cuối cùng là số giây nguyên hợp lệ, có default và validation rõ.
- [ ] Đã bật transaction infrastructure; service là Spring bean và lời gọi đi qua proxy.
- [ ] Biết method **bắt đầu transaction mới** hay chỉ tham gia transaction đang có.
- [ ] Nếu dùng `REQUIRES_NEW`, đã đánh giá connection pool, lock và tính độc lập commit/rollback.
- [ ] Đã xác minh transaction manager và JDBC/JPA resource thực sự hỗ trợ timeout cần dùng.
- [ ] Không nhầm transaction timeout với HTTP, statement, pool hay request timeout.
- [ ] Có integration test trên database/driver phù hợp và xác nhận rollback, không suy luận từ `Thread.sleep`.
- [ ] Cấu hình được externalize, được quan sát và thay đổi qua deployment/configuration lifecycle rõ ràng.
- [ ] Nếu timeout xảy ra cùng side effect ngoài database, có cách phân loại kết quả chưa rõ và đối soát.

**Ghi nhớ:** `timeout` và `timeoutString` cùng biểu diễn **timeout tính bằng giây của transaction mới**. `timeout` nhận `int` cố định; `timeoutString` nhận chuỗi, đặc biệt hữu ích với placeholder `${...}`. Annotation đặt **chính sách**, còn transaction manager/driver/database quyết định **cách thực thi**. Timeout của một method `REQUIRED` không làm mới deadline transaction mà method đó đang tham gia.

## Nguồn chính thức để đối chiếu

- Spring Framework 6.2 — [`@Transactional`: cấu hình timeout, timeoutString, propagation](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html).
- Spring Framework 6.2 — [`@Transactional` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html).
- Spring Framework — [`DefaultTransactionAttribute` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/interceptor/DefaultTransactionAttribute.html): `setTimeoutString` và `resolveAttributeStrings`.
- Spring Framework — [`DataSourceTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html): JDBC transaction timeout và `JdbcTemplate`.
- Spring Framework — [`DataSourceUtils` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html): `applyTransactionTimeout`.
- Spring Boot — [Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): nguồn property, environment và command-line arguments.
