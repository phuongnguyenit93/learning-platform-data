# Khai báo DataSource cùng JdbcTransactionManager

> **Phạm vi:** Spring Framework — Transaction Management, phần **Giao dịch đầu tiên**. Bài học hướng dẫn kết nối một cơ sở dữ liệu quan hệ bằng `DataSource`, khai báo `JdbcTransactionManager` và sử dụng `JdbcTemplate` trong **một giao dịch JDBC cục bộ**. Ví dụ hoàn chỉnh dùng Java 17, Spring Boot 3.5.7 (Spring Framework 6.2), Maven và H2 để có thể chạy ngay mà không cần cài database riêng.

## 1. Mục tiêu và bức tranh tổng thể

Sau bài này, bạn cần hiểu và làm được:

1. Giải thích vai trò riêng của `DataSource`, `JdbcTransactionManager`, `JdbcTemplate` và `@Transactional`.
2. Khai báo các Spring bean dùng **cùng một `DataSource`**, bảo đảm những câu SQL trong cùng giao dịch sử dụng connection do Spring quản lý.
3. Thấy kết quả **commit** khi phương thức hoàn tất bình thường và **rollback** khi có lỗi không kiểm tra (`RuntimeException`) thoát khỏi phương thức.
4. Chạy ví dụ chuyển tiền giữa hai tài khoản trên H2; kiểm chứng rằng lỗi ở thao tác sau hoàn tác cả hai cập nhật.
5. Phân biệt cấu hình thủ công của Spring với auto-configuration của Spring Boot và tránh các lỗi phổ biến về proxy, nhiều `DataSource` và thao tác JDBC trực tiếp.

Sơ đồ hoạt động:

```text
Đối tượng gọi
    |
    v
Spring AOP proxy (@Transactional)
    |
    v
JdbcTransactionManager --------> DataSource --------> JDBC Connection
    |                                                  ^
    | mở / commit / rollback                           |
    v                                                  |
BankService ------> JdbcTemplate ------> DataSourceUtils
    |
    +-- UPDATE accounts ...
    +-- UPDATE accounts ...
```

**Mấu chốt:** `DataSource` cung cấp connection; `JdbcTransactionManager` quyết định ranh giới giao dịch và gắn connection vào luồng đang thực thi; `JdbcTemplate` lấy connection phù hợp với giao dịch ấy thông qua cơ chế của Spring. Hai câu `UPDATE` trong một phương thức dịch vụ có thể cùng thành công hoặc cùng bị rollback.

## 2. Các thành phần và trách nhiệm

| Thành phần | API / package | Trách nhiệm |
| --- | --- | --- |
| `DataSource` | `javax.sql.DataSource` (Java/JDBC) | Nơi ứng dụng xin `Connection` tới database; có thể là pool, JNDI hoặc một nguồn kết nối đơn giản. |
| `DriverManagerDataSource` | `org.springframework.jdbc.datasource` | Hiện thực `DataSource` đơn giản, tạo kết nối mới mỗi lần yêu cầu; phù hợp demo/test, **không cung cấp pool**. |
| `JdbcTransactionManager` | `org.springframework.jdbc.support` | Hiện thực `PlatformTransactionManager` cho **một** JDBC `DataSource`, quản lý begin/commit/rollback và dịch lỗi SQL ở bước commit/rollback khi có thể. |
| `JdbcTemplate` | `org.springframework.jdbc.core` | Chạy SQL, quản lý statement/result set, xử lý kết nối đúng cách, dịch nhiều `SQLException` thành `DataAccessException`. |
| `@Transactional` | `org.springframework.transaction.annotation` | Khai báo transaction boundary quanh lời gọi phương thức khi được cơ chế AOP transaction của Spring áp dụng. |
| `@EnableTransactionManagement` | `org.springframework.transaction.annotation` | Bật xử lý `@Transactional` trong cấu hình Spring thuần; trong nhiều ứng dụng Boot, hạ tầng này được auto-configure. |
| `TransactionTemplate` | `org.springframework.transaction.support` | Lựa chọn quản lý giao dịch bằng callback thay vì annotation. |

### `JdbcTransactionManager` và `DataSourceTransactionManager` khác nhau thế nào?

`JdbcTransactionManager` kế thừa `DataSourceTransactionManager`. Cả hai quản lý giao dịch JDBC trên một `DataSource`; điểm nổi bật của biến thể `JdbcTransactionManager` (từ Spring Framework 5.3) là **dịch `SQLException` ở giai đoạn commit/rollback** nhờ `SQLExceptionTranslator` theo tinh thần của `JdbcTemplate`. Ví dụ, lỗi tranh chấp dữ liệu phát hiện muộn ở commit có thể được biểu diễn bằng một lớp trong họ `DataAccessException` thay vì chỉ là `TransactionSystemException`.

Vì vậy, mã gọi cần sẵn sàng xử lý cả lỗi giao dịch và lỗi truy cập dữ liệu; không được giả định mọi lỗi commit luôn thuộc duy nhất một lớp exception. Bài này chọn `JdbcTransactionManager` để thấy rõ sự kết hợp với `JdbcTemplate`.

### Phạm vi bảo đảm

Một `JdbcTransactionManager` thông thường kiểm soát **một `DataSource` JDBC**, không mặc nhiên kiểm soát cơ sở dữ liệu khác, HTTP request, message broker hay transaction phía service bên ngoài. Nó cũng không đồng nghĩa Spring tự tạo distributed transaction/XA. Nếu ứng dụng dùng JPA, loại transaction manager phù hợp có thể là `JpaTransactionManager`; không nên tự ý gắn JDBC manager vào luồng nghiệp vụ JPA mà chưa thiết kế rõ.

## 3. Chuẩn bị dự án hoàn chỉnh

Ví dụ dùng một ứng dụng Spring Boot với hai tài khoản. Ban đầu số dư lần lượt là **1.000** và **500** đơn vị. Lần chuyển thứ nhất chuyển 200 và commit, cho ra **800 / 700**. Lần chuyển thứ hai thử chuyển 100 nhưng chủ động ném `IllegalStateException` sau hai câu `UPDATE`, vì vậy cả lần thứ hai phải rollback, số dư vẫn **800 / 700**.

Cấu trúc thư mục:

```text
jdbc-transaction-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── vn/
                └── example/
                    ├── JdbcTxApplication.java
                    └── BankService.java
```

### 3.1. `pom.xml`

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
    <artifactId>jdbc-transaction-demo</artifactId>
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

`spring-boot-starter-jdbc` cung cấp Spring JDBC và phần cần thiết cho transaction management. `h2` là JDBC driver và database in-memory dùng để chạy demo. Maven cần Java 17 trở lên; H2 chỉ sống trong tiến trình JVM của ví dụ.

### 3.2. `src/main/java/vn/example/JdbcTxApplication.java`

```java
package vn.example;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class JdbcTxApplication {

    public static void main(String[] args) {
        SpringApplication.run(JdbcTxApplication.class, args);
    }

    @Bean
    public DataSource dataSource() {
        DriverManagerDataSource source = new DriverManagerDataSource();
        source.setDriverClassName("org.h2.Driver");
        source.setUrl("jdbc:h2:mem:txdemo;DB_CLOSE_DELAY=-1");
        source.setUsername("sa");
        source.setPassword("");
        return source;
    }

    @Bean
    public JdbcTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    public CommandLineRunner demo(JdbcTemplate jdbc, BankService service) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE accounts (" +
                "id INT PRIMARY KEY, balance INT NOT NULL)"
            );
            jdbc.update(
                "INSERT INTO accounts(id, balance) VALUES (1, 1000), (2, 500)"
            );

            service.transfer(1, 2, 200, false);
            System.out.printf("after commit: %d, %d%n",
                balance(jdbc, 1), balance(jdbc, 2));

            try {
                service.transfer(1, 2, 100, true);
            } catch (IllegalStateException expected) {
                // Lần chuyển thứ hai đã bị rollback.
            }
            System.out.printf("after rollback: %d, %d%n",
                balance(jdbc, 1), balance(jdbc, 2));
        };
    }

    private static int balance(JdbcTemplate jdbc, int accountId) {
        return jdbc.queryForObject(
            "SELECT balance FROM accounts WHERE id = ?",
            Integer.class,
            accountId
        );
    }
}
```

Ý nghĩa các bean:

- `dataSource()` khai báo **một** nguồn kết nối H2. `jdbc:h2:mem:txdemo` là database trong bộ nhớ; `DB_CLOSE_DELAY=-1` giữ database tồn tại giữa các lần đóng connection trong cùng JVM để demo truy vấn nhiều lần.
- `transactionManager(DataSource dataSource)` nhận **chính bean `DataSource`** được Spring inject và khởi tạo `JdbcTransactionManager`. Spring dùng nó để điều phối connection của nguồn dữ liệu đó.
- `jdbcTemplate(DataSource dataSource)` cũng sử dụng **cùng bean `DataSource`**. Đây là điều kiện quan trọng để SQL của `JdbcTemplate` tham gia giao dịch do manager tương ứng điều khiển.
- `@EnableTransactionManagement` bật xử lý `@Transactional`; trong Spring Boot cấu hình transaction thường đã có hạ tầng auto-configuration, nhưng khai báo tường minh ở ví dụ giúp người học nhận biết vai trò.
- `CommandLineRunner` tạo bảng và dữ liệu mẫu **bên ngoài phương thức transfer có transaction**, sau đó gọi sang một bean dịch vụ riêng để đảm bảo lời gọi đi qua Spring proxy.

`DriverManagerDataSource` được dùng **chỉ để học**. Mỗi lần lấy connection có thể tạo kết nối vật lý mới. Với dịch vụ thật, hãy dùng pooling `DataSource` như HikariCP và đưa cấu hình kết nối/secret ra ngoài mã nguồn.

### 3.3. `src/main/java/vn/example/BankService.java`

```java
package vn.example;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BankService {
    private final JdbcTemplate jdbc;

    public BankService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(int fromId, int toId, int amount,
                         boolean failAfterUpdates) {
        if (amount <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update(
            "UPDATE accounts " +
            "SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, fromId, amount
        );
        if (debited != 1) {
            throw new IllegalArgumentException("Insufficient funds");
        }

        int credited = jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = ?",
            amount, toId
        );
        if (credited != 1) {
            throw new IllegalArgumentException("Receiver not found");
        }

        if (failAfterUpdates) {
            throw new IllegalStateException("Simulated failure");
        }
    }
}
```

Phương thức `transfer` được khai báo `public` trên một Spring bean `@Service`, và được gọi từ bean khác (runner). Điều này quan trọng vì xử lý `@Transactional` theo cách phổ biến dùng **proxy**. Hai lệnh cập nhật đều đi qua cùng `JdbcTemplate` và do đó sử dụng connection đang gắn với transaction.

Phép kiểm tra `balance >= ?` trong câu `UPDATE` tránh trừ quá số dư đối với một thao tác riêng lẻ và bảo vệ thao tác đồng thời ở mức hàng được DB khóa/cập nhật. Trong ứng dụng tài chính thực tế vẫn cần thiết kế chi tiết về đơn vị tiền, làm tròn, kiểm soát đồng thời, idempotency và kiểm toán; ví dụ chỉ nhằm chứng minh commit/rollback JDBC.

### 3.4. Chạy và xem kết quả

Từ thư mục `jdbc-transaction-demo`:

```bash
java -version
mvn -version
mvn -q spring-boot:run
```

Hai dòng do chương trình demo chủ động in ra là:

```text
after commit: 800, 700
after rollback: 800, 700
```

Maven/Spring Boot có thể in thêm log khởi động tùy cấu hình; hai dòng trên là **kết quả nghiệp vụ xác định**. Sau lần thành công: 1.000 − 200 = 800; 500 + 200 = 700. Sau lần thất bại: hai `UPDATE` của lần chuyển 100 đều rollback nên số dư không đổi.

Nếu xóa `@Transactional` trên `BankService.transfer`, hai câu `UPDATE` của ví dụ có thể chạy và commit độc lập theo auto-commit của các connection lấy được. Khi ném exception cuối phương thức, **không có transaction bao quanh để rollback cả hai thao tác**; vì thế không được suy ra kết quả luôn là 800/700. Hãy dùng test để xác định cấu hình thực tế thay vì dựa vào việc chương trình có ném exception.

## 4. Vì sao các câu SQL dùng chung một giao dịch?

Với `@Transactional` có hiệu lực trên `BankService.transfer`, chuỗi diễn biến là:

1. Caller gọi **proxy** của `BankService`.
2. `TransactionInterceptor` tìm transaction manager phù hợp, ở đây bean `transactionManager` thuộc loại `JdbcTransactionManager`.
3. Manager lấy `Connection` từ `DataSource` đã khai báo, chuẩn bị trạng thái transaction (chẳng hạn tắt auto-commit theo cách cần thiết) và gắn connection vào ngữ cảnh giao dịch của luồng hiện tại.
4. `JdbcTemplate` gọi cơ chế truy cập connection có nhận biết giao dịch (`DataSourceUtils`). Nó nhận lại connection đã được Spring liên kết với transaction cho **cùng `DataSource`**.
5. Hai câu `UPDATE` chạy trên tài nguyên JDBC đang thuộc cùng transaction.
6. Nếu method kết thúc bình thường và không bị đánh dấu rollback-only, manager **commit**. Nếu lỗi phù hợp quy tắc rollback thoát ra, manager **rollback**.
7. Spring dọn trạng thái transaction và trả/đóng connection theo cách phù hợp với `DataSource`.

Tuyệt đối không hiểu rằng chỉ cần khai báo một bean tên `transactionManager` là mọi code JDBC trong ứng dụng đều cùng transaction. **Cơ chế lấy connection và đối tượng `DataSource` phải tương thích**. `JdbcTemplate` và `DataSourceUtils` xử lý phần đó; gọi `dataSource.getConnection()` trực tiếp ở nơi khác có thể tạo connection riêng, không tham gia transaction hiện hành.

### Tránh lấy connection theo cách không nhận biết transaction

Ví dụ sau là **minh họa lỗi**, không phải chương trình độc lập:

```java
try (var connection = dataSource.getConnection()) {
    // Connection này có thể độc lập với connection do
    // JdbcTransactionManager đã gắn vào transaction hiện tại.
}
```

Ưu tiên dùng `JdbcTemplate`. Khi thật sự phải thao tác JDBC mức thấp bên trong một phương thức đang có Spring transaction, dùng:

```java
Connection connection = DataSourceUtils.getConnection(dataSource);
try {
    // Tạo PreparedStatement và thao tác JDBC bằng connection này.
} finally {
    DataSourceUtils.releaseConnection(connection, dataSource);
}
```

Đoạn trên là **mẫu tích hợp**, cần import `java.sql.Connection` và `org.springframework.jdbc.datasource.DataSourceUtils`. `releaseConnection` biết rằng connection đang được transaction giữ nên không tự ý đóng nó trước thời điểm Spring kết thúc giao dịch. Không tự gọi `commit()`, `rollback()` hoặc điều chỉnh `autoCommit` trên connection do Spring quản lý nếu không chủ ý và chưa hiểu hệ quả.

## 5. Spring Boot cấu hình tự động khác gì khai báo thủ công?

### Spring Framework thuần

Trong ứng dụng Spring không dùng Boot, thường cần khai báo:

- `@Bean DataSource`.
- `@Bean JdbcTransactionManager` nhận đúng `DataSource`.
- `@Bean JdbcTemplate` nhận cùng `DataSource`.
- `@EnableTransactionManagement` để kích hoạt xử lý `@Transactional`.

Phương thức bean có thể khai báo kiểu trả về `PlatformTransactionManager` thay cho `JdbcTransactionManager` nếu code chỉ cần interface:

```java
@Bean
public PlatformTransactionManager transactionManager(DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
```

Trong trường hợp đó import `org.springframework.transaction.PlatformTransactionManager`; chức năng JDBC không thay đổi.

### Spring Boot

Với `spring-boot-starter-jdbc` và một cấu hình datasource hợp lệ, Spring Boot thông thường **auto-configure** `DataSource`, `JdbcTemplate` và transaction manager JDBC nếu chưa có bean cấu hình thay thế và các điều kiện phù hợp được đáp ứng. Với một database bên ngoài, các property quen thuộc là `spring.datasource.url`, `spring.datasource.username`, `spring.datasource.password` và tùy trường hợp `spring.datasource.driver-class-name`.

Bản chạy H2 ở phần 3 cố ý khai báo bean thủ công để học rõ luồng wiring. **Không cần vừa định nghĩa bean `DataSource` bằng tay vừa kỳ vọng các property `spring.datasource.*` luôn thay đổi bean đó**: custom bean thường khiến phần auto-configure `DataSource` tương ứng lùi lại. Khi chọn cách Boot tự cấu hình, hãy bỏ bean `dataSource()` tự tạo và cung cấp property chuẩn. Không trộn cả hai cách nếu chưa hiểu điều kiện auto-configuration.

Ví dụ **thay thế**, dành cho dự án Boot chỉ dùng H2 và cho phép Boot tạo `DataSource`:

```properties
spring.datasource.url=jdbc:h2:mem:txdemo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.driver-class-name=org.h2.Driver
```

Các dòng này là nội dung của `src/main/resources/application.properties` **trong phương án auto-configuration**, không cần thêm vào dự án ở phần 3. Khi tự cấu hình, Boot thường dùng HikariCP nếu starter mang HikariCP vào classpath. Việc chọn transaction manager thực tế còn phụ thuộc các bean và persistence stack có mặt, vì thế với bài đầu tiên hãy giữ rõ chỉ một nguồn dữ liệu JDBC và một manager.

Trong production, nên đưa mật khẩu vào secret manager hoặc biến môi trường, giới hạn quyền database, cấu hình pool/timeout và giám sát kết nối. Không dùng `DriverManagerDataSource` làm pool cho tải cao.

## 6. Transaction boundary bằng `@Transactional`

Ví dụ sử dụng cách **declarative transaction management**. Các thuộc tính mặc định thông dụng của `@Transactional` trong Spring gồm:

| Thuộc tính | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `propagation` | `REQUIRED` | Nếu chưa có transaction phù hợp thì tạo mới; nếu có thì tham gia. |
| `isolation` | `DEFAULT` | Để database quyết định mức isolation mặc định. |
| `readOnly` | `false` | Transaction cho phép đọc và ghi; `readOnly=true` thường là gợi ý tối ưu, không phải chặn ghi tuyệt đối. |
| `timeout` | Theo transaction system hoặc không giới hạn nếu không hỗ trợ | Đặt giới hạn theo cơ chế transaction; timeout không phải cơ chế hủy chắc chắn mọi tác vụ bên ngoài. |
| Rollback | `RuntimeException` hoặc `Error` | Checked exception **không tự động** gây rollback theo quy tắc mặc định, trừ khi cấu hình khác. |

Ví dụ cụ thể hóa ý định:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED,
    timeout = 10
)
public void updateTwoRows() {
    // Thực hiện các thao tác JdbcTemplate cùng DataSource.
}
```

Đây là **trích đoạn minh họa**, với `Propagation` và `Isolation` từ `org.springframework.transaction.annotation`. Hỗ trợ mức isolation, timeout và cách kiểm soát khóa phụ thuộc database/driver; không được mặc định mọi database hành xử hoàn toàn giống nhau.

Nếu cần rollback cả checked exception:

```java
@Transactional(rollbackFor = IOException.class)
public void processFileAndUpdate() throws IOException {
    // Phần DB dùng JdbcTemplate; IOException cần được ném ra ngoài.
}
```

Cần import `java.io.IOException`. Đây cũng là **trích đoạn**, không phải chương trình standalone. Ngược lại, nếu bắt exception ngay trong method và không ném tiếp hoặc không đánh dấu rollback-only, Spring có thể xem method đã hoàn tất bình thường và commit. Hãy chủ động quyết định chính sách khi xử lý lỗi.

### Khi nào dùng `TransactionTemplate`?

Nếu cần điều khiển transaction bằng đoạn code thay vì annotation, có thể tạo `TransactionTemplate` từ cùng manager:

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);

template.executeWithoutResult(status -> {
    jdbc.update("UPDATE accounts SET balance = balance - 1 WHERE id = 1");
    jdbc.update("UPDATE accounts SET balance = balance + 1 WHERE id = 2");
});
```

Đây là **trích đoạn minh họa** với biến `transactionManager` và `jdbc` đã được cung cấp trong phương thức chứa nó, cần import `org.springframework.transaction.support.TransactionTemplate`. Nếu callback ném exception phù hợp, Spring rollback; có thể dùng `status.setRollbackOnly()` để yêu cầu rollback chủ động. `TransactionTemplate` hữu ích khi cần ranh giới giao dịch rõ trong code, nhưng không nên lồng vô tội vạ với `@Transactional` khi chưa hiểu propagation.

## 7. Những lỗi cấu hình thường gặp

### 7.1. `JdbcTemplate` và manager dùng hai nguồn dữ liệu khác nhau

Nếu manager được tạo bằng `dataSourceA` còn template chạy trên `dataSourceB`, SQL của B không mặc nhiên tham gia transaction JDBC của A. Đôi khi hai datasource có cùng JDBC URL nhưng là **hai bean/connection provider khác nhau**, dẫn đến khó nhận biết lỗi. Luôn kiểm tra injection, qualifier và quy trình quản lý connection.

### 7.2. Dùng `@Transactional` trên đối tượng tự tạo bằng `new`

Ví dụ `new BankService(jdbcTemplate)` bỏ qua container/proxy của Spring. Phương thức có annotation trên đối tượng này không được transaction interceptor của Spring tự động bao quanh. Dùng bean do Spring tạo, inject qua constructor và gọi qua bean tham chiếu ấy.

### 7.3. Tự gọi phương thức trong cùng bean (self-invocation)

`this.transfer(...)` từ một phương thức khác của `BankService` thường **không đi qua proxy** khi dùng Spring AOP proxy mode, nên `@Transactional` gắn trên `transfer` có thể không có hiệu lực. Đặt boundary ở public method được bean khác gọi, hoặc tái cấu trúc service. Đừng xem việc annotation hiện diện trong source code là bằng chứng transaction thực sự đang chạy.

### 7.4. Exception bị nuốt

`JdbcTemplate` có thể ném `DataAccessException` (unchecked). Nếu method bắt rồi bỏ qua lỗi, manager không biết phải rollback, trừ khi transaction đã bị đánh dấu rollback-only bởi cơ chế khác. Tránh ghi log rồi trả success giả; thường nên ném tiếp exception hoặc chủ động điều khiển rollback theo nghiệp vụ.

### 7.5. Nhầm `readOnly` với quyền database

`@Transactional(readOnly = true)` là cấu hình/hint về transaction và có thể được driver/database áp dụng theo mức độ khác nhau. Nó **không thay thế** tài khoản database chỉ đọc, chính sách phân quyền SQL hay kiểm tra tại DB. Không dùng nó làm ranh giới bảo mật.

### 7.6. Thiếu driver, sai JDBC URL hoặc secret

Các lỗi như `Cannot load driver class`, `Failed to obtain JDBC Connection`, authentication failure thường do thiếu driver, URL không đúng, database chưa chạy, quyền truy cập hoặc secret sai. Kiểm tra dependency, phiên bản JDBC driver, URL, host/port, pool và network trước khi đổ lỗi cho `@Transactional`.

### 7.7. Giữ transaction quá lâu hoặc chuyển sang thread khác

Đừng đặt truy vấn chậm, chờ HTTP dài hay xử lý file lớn trong transaction làm giữ connection và lock quá lâu. Transaction JDBC kiểu imperative thường gắn với thread hiện tại; chạy tác vụ con bằng `new Thread(...)` hoặc `@Async` **không tự kế thừa transaction**. Nếu cần xử lý nền, thiết kế transaction riêng ở nơi thực thi.

### 7.8. Tin rằng nhiều giao dịch cục bộ thành một giao dịch chung

`JdbcTransactionManager` không làm atomic cập nhật của hai database độc lập, và không rollback được tác động HTTP/email/broker. Nếu cần bảo đảm liên hệ nhiều hệ thống, phải nghiên cứu cơ chế thích hợp như outbox, idempotency, saga hoặc distributed transaction khi các participant thật sự hỗ trợ. Với bài nhập môn, hãy giới hạn vào **một JDBC `DataSource`**.

## 8. Khi ứng dụng có nhiều `DataSource`

Khi có nhiều database, mỗi `JdbcTransactionManager` cần gắn với đúng `DataSource`. Có thể đặt tên bean riêng và chỉ định manager trong `@Transactional`:

```java
@Bean("ordersTransactionManager")
public JdbcTransactionManager ordersTransactionManager(
        @Qualifier("ordersDataSource") DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
```

```java
@Transactional(transactionManager = "ordersTransactionManager")
public void updateOrder() {
    // JdbcTemplate của phần orders phải dùng ordersDataSource.
}
```

Đây là **các trích đoạn cấu hình mở rộng**, giả định ứng dụng đã có bean `ordersDataSource` và `JdbcTemplate` tương ứng; không phải mã độc lập. Import `org.springframework.beans.factory.annotation.Qualifier`. Với nhiều manager, cần giải quyết cách chọn bean mặc định/`@Primary` hoặc qualifier, và không mặc định một annotation sẽ quản lý tất cả datasource. **Hai `JdbcTransactionManager` độc lập không biến thành XA/2PC.**

Nếu một ứng dụng dùng Spring Data JPA cùng JDBC, phải xác định transaction manager nào là chủ đạo; trường hợp dùng `JpaTransactionManager` với cùng datasource có thể phối hợp những thao tác JDBC được quản lý đúng cách, nhưng không nên cấu hình chồng chéo hoặc chọn ngẫu nhiên manager chỉ vì tên bean.

## 9. Tự kiểm chứng giao dịch thay vì chỉ nhìn annotation

Trong bài demo, phép thử quan trọng nhất là:

- Trạng thái ban đầu: tài khoản 1 có **1000**, tài khoản 2 có **500**.
- Lần 1 gọi `transfer(1, 2, 200, false)`; không exception; quan sát **800**, **700**.
- Lần 2 gọi `transfer(1, 2, 100, true)`; sau hai `UPDATE` có exception; quan sát **vẫn 800**, **700**.
- Xác nhận lời gọi đến `transfer` đi qua **Spring bean** và `JdbcTemplate` dùng cùng `DataSource` với manager.

Có thể xem transaction đang active trong một method do Spring quản lý bằng **trích đoạn chẩn đoán**:

```java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
System.out.println("transaction active = " + active);
```

Cần import `org.springframework.transaction.support.TransactionSynchronizationManager`. Với `transfer` được gọi qua proxy và transaction đã bắt đầu, thường nhận `true`. Nhưng phép kiểm tra này **không thay thế** kiểm thử rollback và xác minh datasource/connection thực tế.

Trong test integration, dùng chính database hoặc một database có hành vi phù hợp khi kiểm tra locking/isolation; một số khác biệt về DDL, autocommit và isolation của H2 so với PostgreSQL/MySQL có thể khiến test đơn giản chưa phản ánh hết production. Nếu test method tự có `@Transactional`, Spring Test có thể rollback test ở cuối; cần phân biệt rollback của test với hành vi commit/rollback của service đang được kiểm thử.

### Bài tập nhỏ

1. Thay `failAfterUpdates` thành `false` ở lần gọi thứ hai; dự đoán và chạy để xác nhận số dư thành **700 / 800**.
2. Giữ `failAfterUpdates=true`, thêm một câu `SELECT` trong `transfer` trước khi ném lỗi và quan sát dữ liệu **bên trong transaction**. Sau rollback, quan sát dữ liệu **bên ngoài transaction** không đổi.
3. Đổi exception cuối method thành checked exception tự định nghĩa và khai báo `throws`; so sánh hành vi khi **có** và **không có** `rollbackFor`. Cẩn thận vì điều chỉnh này thay đổi mã nguồn nên phải biên dịch lại.
4. Tạm tách `JdbcTemplate` sang một `DataSource` khác trong môi trường thử nghiệm để hiểu vì sao **same DataSource** là điều kiện wiring quan trọng; không làm thí nghiệm này trên database production.

## 10. Checklist triển khai `DataSource` + `JdbcTransactionManager`

- [ ] Có dependency Spring JDBC, transaction support và JDBC driver đúng loại.
- [ ] `DataSource` có URL/driver/credentials hợp lệ; production dùng pool và secret bên ngoài mã nguồn.
- [ ] Chỉ có một `DataSource` cho transaction demo, hoặc các `DataSource` khác được qualifier rõ ràng.
- [ ] `JdbcTransactionManager` nhận đúng `DataSource` mà `JdbcTemplate` dùng.
- [ ] Hạ tầng `@Transactional` đã bật, service được Spring quản lý, caller đi qua proxy.
- [ ] Transaction boundary đặt ở service method bao trùm **toàn bộ** các SQL cần atomic.
- [ ] Có quy tắc rollback rõ, kể cả checked exceptions khi cần.
- [ ] Không dùng `DataSource.getConnection()` trực tiếp theo cách bỏ qua cơ chế transaction-aware.
- [ ] Kiểm thử cả commit và rollback trên dữ liệu thật, không chỉ xác nhận exception đã được ném.
- [ ] Có timeout, giới hạn pool, logging/metrics và kiểm soát transaction dài phù hợp môi trường vận hành.

**Ghi nhớ:** `DataSource` là nguồn tạo connection; `JdbcTransactionManager` quản lý transaction trên connection của nguồn ấy; `JdbcTemplate` sử dụng connection đúng ngữ cảnh. Kết nối đúng **ba thành phần** và gọi dịch vụ qua Spring proxy là nền tảng để có giao dịch JDBC đầu tiên hoạt động như kỳ vọng.

## Tài liệu tham khảo

- Spring Framework — [Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSource`, `DataSourceUtils`, `DataSourceTransactionManager` và `JdbcTransactionManager`.
- Spring Framework — [JdbcTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html): constructor, khả năng dịch lỗi commit/rollback.
- Spring Framework — [Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): cấu hình declarative transactions.
- Spring Framework — [Understanding Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): proxy và interceptor.
- Spring Framework — [Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionTemplate`.
- Spring Boot — [SQL Databases](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html): datasource properties, pool và `JdbcTemplate`.
