# MySQL container/Testcontainers và môi trường kiểm thử cô lập

Kiểm thử ứng dụng Spring Boot và JPA với MySQL thật giúp phát hiện những lỗi mà database giả lập hoặc H2 có thể không tái hiện: khác biệt SQL dialect, kiểu dữ liệu, collation, transaction isolation, khóa ngoại, generated key, JSON, index và hành vi của migration. Testcontainers cho phép khởi chạy một MySQL container dùng riêng cho test, cấp cổng kết nối động và dọn môi trường sau khi kiểm thử.

Một bài kiểm thử tốt cần tái lập được phiên bản MySQL và cấu hình gần production, đồng thời bảo đảm dữ liệu của test này không làm ảnh hưởng test khác. Container chỉ cung cấp môi trường database cô lập; ứng dụng vẫn cần quản lý transaction, dữ liệu mẫu, migration và cleanup đúng cách.

## 1. Vì sao nên kiểm thử với MySQL thật?

H2 và database giả lập có ích cho một số kiểm thử nhanh, nhưng chúng không thay thế hoàn toàn MySQL khi ứng dụng chạy trên MySQL trong production.

Các khác biệt thường gây lỗi:

- **SQL dialect:** cú pháp `LIMIT`, hàm ngày giờ, JSON, upsert, generated column và DDL khác nhau giữa các database.
- **Kiểu dữ liệu:** `TINYINT`, `UNSIGNED`, `DECIMAL`, `TIMESTAMP`, `DATETIME`, `JSON` và quy tắc chuyển kiểu không giống nhau.
- **Collation:** phân biệt hoa/thường, dấu, khoảng trắng cuối và thứ tự sắp xếp có thể khác.
- **Transaction:** isolation level, gap lock, next-key lock, deadlock và hành vi concurrent write phụ thuộc InnoDB.
- **Index và constraint:** kế hoạch thực thi, unique index, foreign key và giới hạn index có thể khác.
- **Generated key:** cách lấy ID từ `AUTO_INCREMENT` và hành vi của JDBC driver cần được kiểm tra trên database thực.
- **Migration:** Flyway/Liquibase phải chạy DDL đúng trên phiên bản MySQL mục tiêu.

Testcontainers tạo MySQL thực trong Docker để các kiểm thử tích hợp sử dụng cùng engine và hành vi gần môi trường triển khai. Điều này đặc biệt hữu ích cho repository test, kiểm thử transaction, migration và kiểm thử API có truy cập database.

## 2. Testcontainers hoạt động như thế nào?

Testcontainers là thư viện Java khởi chạy dependency trong container khi test cần sử dụng. Với MySQL, quy trình thường diễn ra như sau:

```text
JUnit bắt đầu test
       |
       v
Testcontainers yêu cầu Docker khởi chạy MySQL image
       |
       v
MySQL khởi tạo database, user và cấu hình
       |
       v
Testcontainers chờ MySQL sẵn sàng
       |
       v
Spring Boot nhận JDBC URL, username, password động
       |
       v
Flyway/Liquibase và Hibernate khởi tạo ứng dụng
       |
       v
Test chạy với MySQL thật
       |
       v
JUnit kết thúc, container được dừng và dọn
```

Testcontainers thường ánh xạ cổng MySQL trong container sang một cổng ngẫu nhiên trên host. Không giả định MySQL luôn ở `localhost:3306`. JDBC URL phải lấy từ container đang chạy, ví dụ qua `getJdbcUrl()`.

Container có vòng đời rõ ràng: khởi động, chờ sẵn sàng, cấp thông tin kết nối, chạy test rồi dừng. Nếu dùng container tĩnh ở cấp class, nhiều test method trong class có thể dùng chung một container; nếu dùng container theo instance, mỗi test có thể có container riêng nhưng thời gian chạy sẽ tăng.

## 3. Chuẩn bị dependency và Docker

Ví dụ Gradle với Spring Boot và JUnit 5:

```kotlin
dependencies {
    runtimeOnly("com.mysql:mysql-connector-j")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:mysql")

    // Chỉ cần khi dùng @ServiceConnection của Spring Boot 3.1+
    testImplementation("org.springframework.boot:spring-boot-testcontainers")
}
```

Hãy dùng dependency management của Spring Boot hoặc import Testcontainers BOM để các module Testcontainers có phiên bản tương thích. Không trộn tùy tiện các phiên bản `junit-jupiter`, `mysql` và core Testcontainers.

Với Maven, khai báo các dependency tương ứng trong `pom.xml`, đặt scope `test` cho Testcontainers và dùng Spring Boot dependency management hoặc BOM phù hợp.

Máy chạy test cần có Docker daemon hoạt động và tài khoản thực thi test có quyền truy cập. Testcontainers có thể tải image MySQL trong lần chạy đầu tiên, vì vậy cần mạng hoặc cache image sẵn có. Trên CI, runner phải cung cấp Docker engine hoặc một môi trường container tương thích được Testcontainers hỗ trợ.

Kiểm tra trước khi chạy:

```bash
docker version
docker info
```

Nếu lệnh Docker không truy cập được daemon, test sẽ lỗi trước khi Spring Boot tạo được datasource. Hãy phân biệt lỗi Docker environment với lỗi JDBC, migration hoặc test assertion.

## 4. Tạo MySQL container bằng JUnit 5

Testcontainers cung cấp `MySQLContainer` để cấu hình image, database, username và password. Ví dụ dưới đây dùng một container tĩnh cho toàn bộ test method trong class:

```java
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
class MySqlContainerSmokeTest {

    @Container
    static final MySQLContainer<?> mysql =
        new MySQLContainer<>("mysql:8.4")
            .withDatabaseName("orders_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @Test
    void mysqlStartsAndAcceptsConnections() {
        assertTrue(mysql.isRunning());
        System.out.println(mysql.getJdbcUrl());
    }
}
```

`@Testcontainers` kích hoạt tích hợp JUnit 5. `@Container` đánh dấu container do extension quản lý. Trường `static` làm container khởi động một lần cho class; container không static thường có vòng đời theo từng test method.

`mysql:8.4` chỉ minh họa một dòng phiên bản. Trong CI và bài test cần tái lập, pin tag patch cụ thể hoặc digest đã kiểm duyệt, đồng bộ với phiên bản MySQL production. Không dùng tag `latest`, vì image có thể thay đổi mà không có thay đổi source code.

Không in JDBC URL hoặc thông tin xác thực trong log production. Ví dụ trên chỉ kiểm tra startup; các test tích hợp thực tế nên lấy connection details để cấu hình Spring datasource.

## 5. Kết nối Spring Boot tới MySQL container

Cách phổ biến và tương thích với nhiều phiên bản Spring Boot là dùng `@DynamicPropertySource` để đăng ký các thuộc tính datasource từ container đang chạy.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Statement;

import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@SpringBootTest
class DatabaseIntegrationTest {

    @Container
    static final MySQLContainer<?> mysql =
        new MySQLContainer<>("mysql:8.4")
            .withDatabaseName("orders_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", mysql::getJdbcUrl);
        registry.add("spring.datasource.username", mysql::getUsername);
        registry.add("spring.datasource.password", mysql::getPassword);
        registry.add("spring.datasource.driver-class-name", mysql::getDriverClassName);
    }

    @Autowired
    DataSource dataSource;

    @Test
    void connectsToRealMySql() throws Exception {
        try (Connection connection = dataSource.getConnection();
             Statement statement = connection.createStatement();
             ResultSet rs = statement.executeQuery("SELECT VERSION()")) {
            assertTrue(rs.next());
            assertTrue(rs.getString(1).contains("8.4"));
        }
    }
}
```

`@DynamicPropertySource` phải là phương thức `static`. Các supplier chỉ được đánh giá khi Spring cần thuộc tính; container phải được khởi động trước khi datasource mở kết nối. Khi dùng `@Container` tĩnh cùng JUnit extension, Testcontainers quản lý thứ tự vòng đời này.

Không ghi cứng `jdbc:mysql://localhost:3306/...` vì cổng host do Testcontainers cấp có thể khác ở mỗi lần chạy hoặc mỗi runner CI. Luôn lấy URL, username và password từ đối tượng container.

### Dùng @ServiceConnection trong Spring Boot 3.1+

Spring Boot 3.1 trở lên cung cấp `@ServiceConnection` để tự tạo connection details từ container được Spring quản lý. Cần thêm dependency `spring-boot-testcontainers`.

Ví dụ cấu hình test:

```java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.MySQLContainer;

@TestConfiguration(proxyBeanMethods = false)
class MySqlTestContainerConfiguration {

    @Bean
    @ServiceConnection
    MySQLContainer<?> mysqlContainer() {
        return new MySQLContainer<>("mysql:8.4")
            .withDatabaseName("orders_test")
            .withUsername("test_user")
            .withPassword("test_password");
    }
}
```

Đưa cấu hình vào test:

```java
@SpringBootTest
@Import(MySqlTestContainerConfiguration.class)
class OrderRepositoryIntegrationTest {
    // Test repository hoặc service
}
```

Spring Boot nhận diện container bean và tạo `JdbcConnectionDetails` phù hợp. Container được quản lý theo lifecycle của Spring context. Với Spring Boot cũ hơn 3.1 hoặc cấu hình đặc biệt, dùng `@DynamicPropertySource`.

Chọn một cơ chế wiring rõ ràng cho test class. Không cần khai báo đồng thời `@ServiceConnection` và `@DynamicPropertySource` cho cùng datasource trừ khi có thuộc tính bổ sung thực sự cần override.

## 6. Dùng MySQLContainer với @DataJpaTest

`@DataJpaTest` tạo Spring test slice tập trung vào JPA repositories, entity mapping và truy vấn. Theo mặc định, Spring Boot có thể thay datasource bằng embedded database nếu tìm thấy. Khi muốn kiểm thử với MySQL container, yêu cầu giữ datasource đã cấu hình:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase.Replace.NONE;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@DataJpaTest
@AutoConfigureTestDatabase(replace = NONE)
@Testcontainers
class OrderRepositoryTest {

    @Container
    static final MySQLContainer<?> mysql =
        new MySQLContainer<>("mysql:8.4")
            .withDatabaseName("orders_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @DynamicPropertySource
    static void configureDatabase(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", mysql::getJdbcUrl);
        registry.add("spring.datasource.username", mysql::getUsername);
        registry.add("spring.datasource.password", mysql::getPassword);
    }

    @Autowired
    OrderRepository orderRepository;

    @Test
    void repositoryBeanIsCreated() {
        assertNotNull(orderRepository);
    }
}
```

`Replace.NONE` ngăn test slice thay datasource bằng embedded database. Nếu dùng `@ServiceConnection`, vẫn phải xác nhận test slice không thay datasource và cấu hình container được import đúng.

`@DataJpaTest` thường chạy mỗi test trong transaction và rollback sau test. Điều này hữu ích cho repository test, nhưng không bảo đảm mọi tác động đều được rollback: DDL có quy tắc implicit commit; thao tác chạy qua thread hoặc connection khác có thể commit riêng; message gửi ra ngoài database cũng không được rollback.

Nếu cần kiểm tra toàn bộ ứng dụng, security, REST endpoint, transaction boundary và migration, dùng `@SpringBootTest` thay vì chỉ dựa vào test slice.

## 7. Chạy migration thật trên container

Test với MySQL container là cơ hội xác nhận Flyway hoặc Liquibase chạy đúng trên phiên bản mục tiêu. Nếu production dùng Flyway, để test khởi động ứng dụng qua migration thực tế và xác nhận schema được tạo từ migration scripts.

Ví dụ cấu hình test khi ứng dụng đã quản lý migration bằng Flyway:

```yaml
spring:
  flyway:
    enabled: true
  jpa:
    hibernate:
      ddl-auto: validate
```

`ddl-auto: validate` yêu cầu Hibernate kiểm tra mapping với schema do migration tạo. Tránh dùng `create` hoặc `create-drop` trong test migration nếu mục tiêu là xác minh chính các file Flyway/Liquibase; Hibernate có thể tự tạo schema khác với production và che lỗi migration.

Kiểm tra lịch sử Flyway:

```sql
SELECT installed_rank, version, description, success
FROM flyway_schema_history
ORDER BY installed_rank;
```

Tên bảng history có thể đã được cấu hình khác. Với Liquibase, kiểm tra `DATABASECHANGELOG` và `DATABASECHANGELOGLOCK`.

Nên có test cho các trường hợp:

- Database rỗng chạy toàn bộ migration từ đầu.
- Nâng schema từ một phiên bản đã triển khai trước đó.
- Index, foreign key, unique constraint và default được tạo đúng.
- Kiểu dữ liệu, collation, charset và generated column đúng như dự kiến.
- Migration thất bại không để lại trạng thái nửa hoàn thành ngoài dự kiến.

Nếu test slice không tự nạp migration theo cấu hình của ứng dụng, dùng `@SpringBootTest` hoặc import đúng auto-configuration cần thiết. Điều quan trọng là test phải chạy chính pipeline migration mà production sử dụng.

## 8. Khởi tạo dữ liệu test

Testcontainers MySQL module hỗ trợ nạp script SQL khi container khởi động:

```java
static final MySQLContainer<?> mysql =
    new MySQLContainer<>("mysql:8.4")
        .withDatabaseName("orders_test")
        .withUsername("test_user")
        .withPassword("test_password")
        .withInitScript("db/test-schema.sql");
```

File `db/test-schema.sql` phải nằm trong test classpath, thường ở `src/test/resources/db/test-schema.sql`. Script này phù hợp cho schema hoặc dữ liệu khởi tạo đơn giản của container. Nếu ứng dụng đã dùng Flyway/Liquibase, tránh tạo một schema khác biệt trong init script; để migration của ứng dụng chịu trách nhiệm cấu trúc database.

Với dữ liệu riêng cho từng test, ưu tiên fixture qua repository hoặc SQL rõ ràng trong test. Ví dụ:

```java
@BeforeEach
void setUp() {
    orderRepository.deleteAll();
    customerRepository.deleteAll();
}
```

Khi có foreign key, thứ tự xóa phải theo quan hệ phụ thuộc hoặc dùng cleanup script được thiết kế rõ ràng. Tránh tắt foreign key checks chỉ để cleanup thuận tiện, vì điều đó có thể che lỗi dữ liệu.

Dữ liệu test nên nhỏ, có ý nghĩa và xác định rõ trạng thái mong đợi. Không phụ thuộc vào ID `AUTO_INCREMENT` cụ thể hoặc thứ tự test được JUnit chạy.

## 9. Cô lập dữ liệu giữa các test

Một container không đồng nghĩa mỗi test có database riêng. Nếu nhiều test method dùng chung container và cùng schema, dữ liệu có thể tồn tại sau khi một test kết thúc.

Có một số mức cô lập:

| Chiến lược | Cách hoạt động | Khi phù hợp |
|---|---|---|
| Một container cho mỗi test class | Static `@Container`; class dùng chung MySQL instance | Test nhanh hơn, cần cleanup dữ liệu giữa method |
| Một container cho mỗi test method | Instance `@Container`; container được tạo và dừng theo method | Cần môi trường rất sạch, chấp nhận startup chậm |
| Một schema/database cho mỗi test | Dùng một MySQL container nhưng tạo database riêng theo test | Test song song hoặc nhiều bộ dữ liệu cần tách biệt |
| Một container dùng chung theo suite | Quản lý lifecycle ở suite/context | Nhiều test class cần giảm thời gian startup; phải quản lý cleanup nghiêm ngặt |

Với phần lớn integration test, một container cho mỗi class là điểm cân bằng tốt. Dùng transaction rollback hoặc cleanup để tách dữ liệu từng method. Nếu test chạy song song, không để hai test cùng truncate hoặc sửa cùng bảng; dùng schema riêng, container riêng hoặc khóa điều phối phù hợp.

### Transaction rollback không phải lúc nào cũng đủ

`@Transactional` trên test có thể rollback các thao tác repository chạy trong cùng transaction test. Nhưng có các ngoại lệ:

- Test gọi HTTP tới server chạy ở thread khác; transaction của request server không tham gia transaction test.
- Service mở transaction `REQUIRES_NEW` và commit độc lập.
- Code dùng `@Async`, message listener hoặc executor khác.
- Test thực hiện DDL; nhiều DDL của MySQL gây implicit commit.
- Test gửi message hoặc gọi dịch vụ ngoài database.

Với test API hoặc bất đồng bộ, dùng dữ liệu có ID riêng và cleanup tường minh sau khi xác nhận kết quả. Không dựa vào rollback của test method để xóa tác động được commit bởi thread khác.

### Spring context cache và vòng đời container

Spring TestContext có thể cache `ApplicationContext` giữa các test class có cấu hình tương đương. Nếu một class dùng static `@Container` do JUnit quản lý, container có thể bị dừng khi class kết thúc trong khi Spring context được cache vẫn giữ `DataSource` trỏ tới container cũ. Test class kế tiếp có thể nhận lại context nhưng kết nối bị từ chối.

Để tránh lỗi vòng đời này, chọn một mô hình nhất quán:

- Dùng container bean với `@ServiceConnection` để vòng đời container gắn với Spring context.
- Dùng một container singleton được quản lý ở cấp suite nếu đội dự án có cơ chế lifecycle rõ ràng.
- Dùng `@DirtiesContext` khi cần buộc Spring đóng context sau class, chấp nhận chi phí khởi tạo lại.
- Hoặc tách cấu hình context/container sao cho không tái sử dụng context đã trỏ tới container bị dừng.

Không kết hợp JUnit-managed container theo class với Spring context cache mà chưa kiểm tra thứ tự dừng container và đóng context.

## 10. Kiểm thử transaction, constraint và concurrency

MySQL container cho phép kiểm tra hành vi InnoDB gần production hơn. Ví dụ kiểm tra unique constraint:

```java
@Test
void rejectsDuplicateEmail() {
    customerRepository.saveAndFlush(new Customer("a@example.test"));

    assertThrows(DataIntegrityViolationException.class, () -> {
        customerRepository.saveAndFlush(new Customer("a@example.test"));
    });
}
```

Test phải dùng đúng collation của schema để xác định email nào được xem là trùng. Nếu production dùng collation không phân biệt hoa/thường, kiểm tra thêm `A@example.test` và `a@example.test`.

Deadlock và lock wait cần được kiểm thử bằng transaction chạy trên connection độc lập, có latch/barrier để đồng bộ thời điểm truy cập. Không dùng `Thread.sleep()` làm cơ chế đồng bộ chính vì kết quả phụ thuộc tốc độ máy. Mỗi thread cần connection riêng và transaction riêng; sau test, xác minh trạng thái dữ liệu và xử lý exception đúng.

Kiểm tra isolation level của session:

```sql
SELECT @@transaction_isolation;
```

Test concurrency nên ghi nhận cả trường hợp thành công, deadlock victim, retry và timeout. Nếu ứng dụng có retry cho lỗi deadlock, kiểm tra số lần retry có giới hạn và transaction được thực hiện lại từ đầu.

## 11. Kiểm thử MySQL version, charset và SQL mode

Chọn image gần với phiên bản production. Nếu production chạy MySQL 8.4, test không nên mặc định chạy H2 hoặc một MySQL version cũ hơn. Khi hỗ trợ nhiều phiên bản, có thể tạo test matrix theo image tag, nhưng phải giữ phạm vi vừa đủ để CI không quá chậm.

Kiểm tra cấu hình thực tế từ container:

```sql
SELECT
  VERSION(),
  @@version_comment,
  @@sql_mode,
  @@character_set_server,
  @@collation_server,
  @@time_zone,
  @@transaction_isolation;
```

Nếu production dùng SQL mode, charset hoặc collation được tùy chỉnh, cấu hình container tương ứng và xác nhận giá trị sau startup. Ví dụ có thể truyền tham số server qua command của container:

```java
new MySQLContainer<>("mysql:8.4")
    .withCommand(
        "--character-set-server=utf8mb4",
        "--collation-server=utf8mb4_0900_ai_ci",
        "--sql-mode=STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION"
    );
```

Các tùy chọn phải tương thích với image và phiên bản MySQL được pin. Không đưa cấu hình test quá khác production chỉ để làm test xanh. Nếu muốn kiểm tra nhiều collation, tạo các test/schema riêng và nêu rõ mục tiêu mỗi cấu hình.

## 12. Kiểm tra JDBC URL, port và trạng thái sẵn sàng

Không hard-code cổng `3306` của host. Container thường lắng nghe `3306` bên trong, còn Testcontainers ánh xạ sang cổng host được cấp động.

Lấy thông tin từ container:

```java
String jdbcUrl = mysql.getJdbcUrl();
String username = mysql.getUsername();
String password = mysql.getPassword();
String host = mysql.getHost();
Integer mappedPort = mysql.getMappedPort(3306);
```

Không tự ghép URL từ host/port nếu `getJdbcUrl()` đã cung cấp URL chính xác cùng query parameter cần thiết. Nếu ứng dụng yêu cầu thuộc tính bổ sung, nối thuộc tính bằng cơ chế URL builder hoặc kiểm tra delimiter `?`/`&` để không làm hỏng URL.

MySQL container cần thời gian khởi động, khởi tạo data directory và sẵn sàng nhận kết nối. `MySQLContainer` cung cấp wait strategy phù hợp. Nếu tùy chỉnh startup command, init script hoặc cấu hình server, có thể cần tăng startup timeout:

```java
.withStartupTimeout(Duration.ofMinutes(2))
```

Đừng khắc phục startup race bằng cách chèn sleep cố định trước mỗi test. Hãy dùng wait strategy hoặc kiểm tra kết nối thực sự. Nếu container khởi động thất bại, đọc log container để phân biệt lỗi image, cấu hình MySQL, filesystem và tài nguyên Docker.

## 13. CI và tái lập môi trường

Để CI chạy ổn định:

1. Pin MySQL image tới patch tag hoặc digest được phê duyệt.
2. Cache image trong runner nếu chính sách CI cho phép.
3. Cấp Docker daemon cho job và xác nhận Testcontainers có thể truy cập.
4. Chạy test với JDBC port động; không giả định cổng host cố định.
5. Không dùng database dev/shared hoặc thông tin xác thực production.
6. Lưu log container khi test thất bại để điều tra.
7. Giới hạn parallelism để không làm Docker host hết RAM, CPU hoặc disk.
8. Dọn container và volume sau test; không giữ dữ liệu test giữa các pipeline.

Nếu CI dùng Docker-in-Docker hoặc remote Docker daemon, cần cấu hình Testcontainers để nhận đúng Docker host và socket. Không tự đặt `DOCKER_HOST` theo một địa chỉ cố định nếu runner cung cấp endpoint khác. Kiểm tra hướng dẫn của nền tảng CI.

Testcontainers reuse mode có thể giữ container giữa các lần chạy local để tiết kiệm startup time, nhưng không nên bật mặc định cho CI hoặc test cần dữ liệu sạch. Reuse có thể làm trạng thái database cũ ảnh hưởng kết quả, và không thay thế chiến lược cô lập dữ liệu.

## 14. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| Testcontainers không tìm thấy Docker | Docker daemon chưa chạy, quyền socket hoặc Docker host sai | Chạy `docker info`, kiểm tra quyền và cấu hình runner |
| Không tải được MySQL image | Mạng, registry rate limit, tag không tồn tại hoặc image architecture không phù hợp | Kiểm tra tag, registry credentials, cache và log pull |
| Container khởi động nhưng Spring không kết nối được | JDBC URL hard-code, lấy port sai hoặc container chưa ready | Dùng `getJdbcUrl()`, dynamic properties và wait strategy |
| Spring Boot dùng H2 thay vì MySQL | `@DataJpaTest` thay datasource tự động | Thêm `@AutoConfigureTestDatabase(replace = NONE)` và kiểm tra connection metadata |
| Flyway/Liquibase không chạy | Test slice không nạp migration hoặc migration bị tắt trong profile test | Dùng cấu hình migration production và kiểm thử với context phù hợp |
| Test phụ thuộc thứ tự chạy | Dữ liệu còn lại trong container dùng chung | Cleanup, transaction rollback hoặc schema/container riêng |
| Test song song thỉnh thoảng thất bại | Hai test cùng sửa/truncate bảng hoặc dùng cùng khóa dữ liệu | Tách schema/container hoặc tạo fixture theo test ID |
| Test rollback nhưng dữ liệu vẫn còn | Request chạy thread khác, `REQUIRES_NEW` hoặc DDL implicit commit | Cleanup tường minh và xác định transaction boundary thực tế |
| Container hết RAM/disk trên CI | Quá nhiều container hoặc image/volume tích lũy | Giới hạn parallelism, dọn tài nguyên và tăng tài nguyên runner |
| MySQL startup timeout | Máy CI chậm, cấu hình init nặng hoặc image lỗi | Đọc container logs, tối ưu init script và tăng timeout hợp lý |

Khi test thất bại, lấy log container và exception gốc trước khi tăng timeout hoặc retry toàn bộ job. Một lỗi SQL thật không được che bằng việc khởi động lại container nhiều lần.

## 15. Tổ chức test theo tầng

Không phải mọi test đều cần MySQL container. Chia test theo mục tiêu giúp giữ tốc độ CI và vẫn kiểm tra được hành vi quan trọng:

| Tầng test | Môi trường | Mục tiêu |
|---|---|---|
| Unit test | Không cần database; mock dependency ở ranh giới phù hợp | Kiểm tra logic thuần và quy tắc nghiệp vụ độc lập persistence |
| Repository/JPA integration test | MySQL Testcontainers, thường qua `@DataJpaTest` | Mapping, query, constraint, pagination, locking và transaction |
| Service integration test | Spring context + MySQL Testcontainers | Kết hợp service, repository, transaction boundary và event |
| API integration test | Spring Boot server + MySQL Testcontainers | HTTP, serialization, validation, security và persistence end-to-end |
| Migration test | MySQL Testcontainers với Flyway/Liquibase | Tạo mới schema và nâng cấp từ version cũ |

Giữ test unit nhanh; tập trung container cho các hành vi phụ thuộc MySQL. Với test migration hoặc API, có thể dùng một container theo class/suite và cleanup dữ liệu rõ ràng để giảm thời gian startup.

## 16. Ví dụ kiểm thử repository end-to-end

Giả sử entity đơn hàng dùng `BIGINT AUTO_INCREMENT` và repository có truy vấn tìm đơn theo customer:

```java
@Entity
@Table(name = "orders")
class Order {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "customer_id", nullable = false)
    private Long customerId;

    @Column(nullable = false, length = 24)
    private String status;

    protected Order() {}

    Order(Long customerId, String status) {
        this.customerId = customerId;
        this.status = status;
    }

    Long getId() { return id; }
    Long getCustomerId() { return customerId; }
    String getStatus() { return status; }
}
```

Repository:

```java
interface OrderRepository extends JpaRepository<Order, Long> {
    List<Order> findByCustomerIdAndStatus(Long customerId, String status);
}
```

Kiểm thử:

```java
@Test
void persistsAndQueriesOrderUsingMySql() {
    Order saved = orderRepository.saveAndFlush(
        new Order(501L, "PAID")
    );

    assertNotNull(saved.getId());

    List<Order> result = orderRepository
        .findByCustomerIdAndStatus(501L, "PAID");

    assertEquals(1, result.size());
    assertEquals(saved.getId(), result.get(0).getId());
}
```

Test này xác minh Hibernate mapping, generated key, SQL query và lưu/đọc dữ liệu trên MySQL. Để kiểm tra index hoặc hiệu năng truy vấn, cần thêm kiểm thử riêng với lượng dữ liệu phù hợp và dùng `EXPLAIN`; một test repository với vài dòng không chứng minh hiệu năng production.

## 17. Checklist trước khi đưa Testcontainers vào dự án

- [ ] Đã chọn MySQL image tương thích với phiên bản production và pin patch tag/digest.
- [ ] Đã thêm Testcontainers JUnit 5 và MySQL module với dependency versions đồng bộ.
- [ ] Docker daemon có sẵn trên máy dev và CI runner.
- [ ] Datasource lấy JDBC URL, username và password động từ container.
- [ ] `@DataJpaTest` không vô tình thay MySQL bằng embedded database.
- [ ] Flyway/Liquibase chạy đúng migration dùng trong production.
- [ ] Đã chọn lifecycle container theo class, method hoặc suite phù hợp.
- [ ] Có chiến lược cleanup/rollback và không để test phụ thuộc thứ tự chạy.
- [ ] Test song song không chia sẻ dữ liệu hoặc truncate cùng bảng.
- [ ] Đã kiểm thử SQL mode, charset, collation, timezone và isolation level cần thiết.
- [ ] Có test constraint, transaction, generated key và truy vấn đặc thù MySQL.
- [ ] CI có log container khi thất bại, giới hạn parallelism và dọn tài nguyên.
- [ ] Không dùng dữ liệu, password hoặc database production trong test.

MySQL container/Testcontainers giúp kiểm thử Spring Boot và JPA trên đúng database engine mà ứng dụng sử dụng. Kết hợp image được pin, datasource wiring động, migration thật và chiến lược cô lập dữ liệu rõ ràng sẽ tạo ra integration test có thể tái lập. Container cung cấp môi trường sạch; chất lượng kiểm thử vẫn phụ thuộc cách quản lý transaction, fixture, cleanup, concurrency và cấu hình gần production.
