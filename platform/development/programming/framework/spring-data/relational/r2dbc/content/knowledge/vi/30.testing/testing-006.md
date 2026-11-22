# Cung cấp thuộc tính kết nối động cho môi trường kiểm thử

Khi kiểm thử ứng dụng Spring Data R2DBC, thông tin kết nối database thường chỉ được biết tại thời điểm chạy test. Ví dụ, Testcontainers khởi động PostgreSQL trong container và cấp một cổng host ngẫu nhiên. Ứng dụng cần nhận đúng host, port, database, username và password trước khi Spring tạo ConnectionFactory.

Spring Test cung cấp **@DynamicPropertySource** và **DynamicPropertyRegistry** để đăng ký các property được tính động trong lúc khởi tạo ApplicationContext. Kết hợp với Testcontainers, cách này cho phép test dùng database thật trong container mà không phải cố định port hoặc ghi thông tin kết nối vào file cấu hình.

Trong ứng dụng Spring Boot dùng R2DBC auto-configuration, các property quan trọng thường là spring.r2dbc.url, spring.r2dbc.username và spring.r2dbc.password. Các property pool nằm dưới spring.r2dbc.pool.* khi dự án dùng r2dbc-pool và phiên bản Spring Boot hỗ trợ chúng.

Điểm cần nhớ là R2DBC URL khác JDBC URL. Một container PostgreSQL có thể cung cấp JDBC URL, nhưng không thể lấy nguyên URL đó gán vào spring.r2dbc.url. Cần tạo URL theo driver R2DBC hoặc xây dựng ConnectionFactoryOptions tương ứng.

## 1. Vì sao cần property động trong test?

Một cấu hình local cố định có thể trông như sau:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/app_test
    username: test
    password: test
~~~

Cấu hình này chỉ hoạt động nếu database luôn chạy tại localhost:5432 với đúng database và credentials. Trong CI hoặc khi chạy nhiều test song song, port có thể khác, database có thể được tạo riêng cho từng lần chạy và container có thể chỉ tồn tại trong vòng đời test.

Với Testcontainers, thông tin kết nối thường được cấp lúc container khởi động:

- Host có thể là localhost hoặc địa chỉ do runtime container cung cấp.
- Port bên trong container được ánh xạ sang một port khả dụng trên host.
- Database name, username và password được cấu hình cho container.
- Container chỉ sẵn sàng sau khi được khởi động và health check hoàn tất.

Do đó, property cần được tạo từ thông tin thực tế của container, không dựa trên port cố định.

### 1.1. Cấu hình động phải có trước khi Spring tạo ConnectionFactory

Spring Boot tạo ConnectionFactory dựa trên cấu hình khi ApplicationContext khởi tạo. Nếu test đợi đến method test mới thay property, ConnectionFactory có thể đã được tạo với giá trị cũ.

Đăng ký dynamic property trong giai đoạn chuẩn bị TestContext để Spring có thể đọc các giá trị trước khi khởi tạo bean cần cấu hình database.

Không nên làm kiểu sau:

~~~java
@BeforeEach
void setProperties() {
    System.setProperty(
        "spring.r2dbc.url",
        "r2dbc:postgresql://localhost:5432/app_test"
    );
}
~~~

@BeforeEach chạy sau khi test context thường đã được tạo. Thay đổi property lúc đó không bảo đảm ConnectionFactory đã dùng giá trị mới.

## 2. Dùng Testcontainers và @DynamicPropertySource

Ví dụ dưới đây dùng PostgreSQL Testcontainer và Spring Boot integration test.

Các dependency test thường cần:

~~~gradle
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")

    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
~~~

Nếu dự án quản lý dependency bằng Maven, khai báo các artifact tương ứng trong pom.xml. Nên dùng phiên bản Testcontainers tương thích với Spring Boot và Java version của dự án, tốt nhất qua BOM hoặc dependency management của dự án.

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class CustomerRepositoryIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("app_test")
            .withUsername("test")
            .withPassword("test");

    @DynamicPropertySource
    static void r2dbcProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.r2dbc.url",
            () -> "r2dbc:postgresql://"
                + postgres.getHost()
                + ":"
                + postgres.getMappedPort(
                    PostgreSQLContainer.POSTGRESQL_PORT
                )
                + "/"
                + postgres.getDatabaseName()
        );

        registry.add(
            "spring.r2dbc.username",
            postgres::getUsername
        );

        registry.add(
            "spring.r2dbc.password",
            postgres::getPassword
        );
    }

    @Test
    void repositoryCanReadFromContainerDatabase() {
        // Thực hiện kiểm thử repository/service.
    }
}
~~~

Các thành phần quan trọng:

- @Testcontainers kích hoạt tích hợp JUnit 5 của Testcontainers.
- @Container đánh dấu container được quản lý theo lifecycle của test.
- static container được khởi động một lần cho class test.
- @DynamicPropertySource đăng ký các giá trị cấu hình động.
- DynamicPropertyRegistry nhận tên property và Supplier cung cấp giá trị khi Spring cần đọc.
- URL dùng driver scheme r2dbc:postgresql, host và mapped port do container cung cấp.

### 2.1. Vì sao phải dùng getMappedPort?

PostgreSQL trong container thường lắng nghe port 5432. Nhưng Testcontainers có thể ánh xạ port đó sang một port host ngẫu nhiên, chẳng hạn 49172.

Không nên viết:

~~~java
"r2dbc:postgresql://localhost:5432/app_test"
~~~

vì port 5432 trên host có thể không phải port của container. Hãy lấy port được ánh xạ:

~~~java
postgres.getMappedPort(PostgreSQLContainer.POSTGRESQL_PORT)
~~~

Tương tự, không nên mặc định host luôn là localhost. Dùng postgres.getHost() để lấy host có thể truy cập container từ môi trường chạy test.

### 2.2. Không dùng JDBC URL cho R2DBC

PostgreSQLContainer.getJdbcUrl() trả về URL dạng JDBC, ví dụ:

~~~text
jdbc:postgresql://localhost:49172/app_test
~~~

URL này dành cho JDBC driver. R2DBC PostgreSQL driver cần URL theo scheme R2DBC:

~~~text
r2dbc:postgresql://localhost:49172/app_test
~~~

Vì vậy, nếu dùng Testcontainers PostgreSQL với Spring Data R2DBC, hãy tự tạo R2DBC URL từ host, mapped port và database name, hoặc dùng ConnectionFactoryOptions phù hợp.

### 2.3. Dùng DynamicPropertyRegistry.add đúng cách

add nhận tên property và Supplier, vì vậy nên truyền method reference hoặc lambda để giá trị được lấy từ container:

~~~java
registry.add("spring.r2dbc.username", postgres::getUsername);
~~~

Không gọi getter quá sớm trước khi container được khởi động nếu giá trị phụ thuộc trạng thái container. Supplier cho phép TestContext lấy giá trị khi resolve property.

Phương thức được đánh dấu @DynamicPropertySource phải là static. Nó thường nằm trong test class hoặc một superclass dùng chung cho nhiều test class.

## 3. Các property R2DBC thường cần cấp động

Với Spring Boot auto-configuration, các property chính:

| Property | Mục đích | Ví dụ |
|---|---|---|
| spring.r2dbc.url | R2DBC connection URL | r2dbc:postgresql://host:port/app_test |
| spring.r2dbc.username | Tên người dùng database | test |
| spring.r2dbc.password | Mật khẩu database | test |
| spring.r2dbc.pool.enabled | Bật/tắt connection pool khi có hỗ trợ | true/false |
| spring.r2dbc.pool.initial-size | Số connection khởi tạo ban đầu | 1 |
| spring.r2dbc.pool.max-size | Số connection tối đa | 5 |
| spring.r2dbc.pool.max-acquire-time | Thời gian tối đa chờ lấy connection | 3s |

Các property pool và khả năng bind cụ thể phụ thuộc phiên bản Spring Boot và việc ứng dụng có dùng r2dbc-pool hay không. Không phải driver nào cũng cung cấp cùng một tập option.

Ví dụ đăng ký thêm pool properties:

~~~java
@DynamicPropertySource
static void r2dbcProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.r2dbc.url", TestDatabase::r2dbcUrl);
    registry.add("spring.r2dbc.username", TestDatabase::username);
    registry.add("spring.r2dbc.password", TestDatabase::password);
    registry.add("spring.r2dbc.pool.enabled", () -> true);
    registry.add("spring.r2dbc.pool.initial-size", () -> 1);
    registry.add("spring.r2dbc.pool.max-size", () -> 4);
}
~~~

Pool nhỏ có thể phù hợp với test để giảm tài nguyên, nhưng cần đủ connection cho các test chạy đồng thời và các transaction đang mở. Nếu test không cần kiểm tra pool, có thể dùng cấu hình đơn giản hơn.

## 4. Dùng helper để tái sử dụng cấu hình động

Nếu nhiều test class cùng dùng một container, có thể gom việc tạo URL và đăng ký property vào một base class hoặc utility.

Ví dụ:

~~~java
abstract class AbstractR2dbcIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("app_test")
            .withUsername("test")
            .withPassword("test");

    @DynamicPropertySource
    static void registerR2dbcProperties(
            DynamicPropertyRegistry registry) {

        registry.add(
            "spring.r2dbc.url",
            AbstractR2dbcIntegrationTest::r2dbcUrl
        );
        registry.add(
            "spring.r2dbc.username",
            postgres::getUsername
        );
        registry.add(
            "spring.r2dbc.password",
            postgres::getPassword
        );
    }

    private static String r2dbcUrl() {
        return "r2dbc:postgresql://"
            + postgres.getHost()
            + ":"
            + postgres.getMappedPort(
                PostgreSQLContainer.POSTGRESQL_PORT
            )
            + "/"
            + postgres.getDatabaseName();
    }
}
~~~

Test class kế thừa:

~~~java
@SpringBootTest
@Testcontainers
class OrderRepositoryIntegrationTest
        extends AbstractR2dbcIntegrationTest {

    @Test
    void savesOrder() {
        // Kiểm thử.
    }
}
~~~

Khi dùng base class, cần hiểu lifecycle container và Spring TestContext cache. Không nên tạo một container riêng rồi dừng nó trong khi ApplicationContext đã cache vẫn giữ ConnectionFactory trỏ tới port cũ.

Một cách phổ biến là dùng một container static dùng chung trong base class cho cùng nhóm test, hoặc dùng một singleton container được quản lý có chủ đích. Nếu mỗi test class cần database/container độc lập, cần bảo đảm Spring context tương ứng không được tái sử dụng với property cũ.

## 5. Context caching và vòng đời container

Spring TestContext có thể cache ApplicationContext để tăng tốc các test dùng chung cấu hình. Dynamic properties được dùng trong lúc xây dựng context. Điều này tạo ra vấn đề nếu container bị dừng nhưng context cache vẫn giữ ConnectionFactory trỏ tới host/port cũ.

Ví dụ rủi ro:

1. Test class A khởi động container A trên port 49172.
2. Spring tạo ApplicationContext với URL trỏ tới port 49172.
3. Test class A kết thúc và container A bị dừng.
4. Test class B có cấu hình tương tự và Spring tái sử dụng ApplicationContext đã cache.
5. ConnectionFactory vẫn trỏ tới port cũ, trong khi container B có port khác.

Các cách hạn chế:

- Dùng một static container dùng chung với base class có lifecycle tương thích với context cache.
- Giữ container sống trong suốt khoảng thời gian context được tái sử dụng.
- Nếu test cần context/container độc lập, dùng cấu hình context riêng hoặc @DirtiesContext khi thực sự cần loại context khỏi cache.
- Tránh khởi động/dừng container thủ công trong @BeforeEach nếu ApplicationContext dùng connection được tạo từ container đó.
- Không thay giá trị property sau khi ConnectionFactory đã được khởi tạo và kỳ vọng bean tự cập nhật.

@DirtiesContext đóng context cache, nhưng không phải công cụ mặc định để sửa mọi vấn đề lifecycle. Dùng nó có thể làm test chậm hơn vì context phải tạo lại.

### 5.1. Kế thừa @DynamicPropertySource

Có thể đặt dynamic property method trong superclass để nhiều test class dùng chung. Nếu subclass cần giá trị động khác nhau nhưng dùng chung tên property, cần chú ý context cache có thể xem các cấu hình test là tương tự và tái sử dụng context.

Nếu giá trị động thay đổi giữa các subclass, hãy cấu hình context identity/lifecycle rõ ràng hoặc tách các test group. Không phụ thuộc vào việc Supplier sẽ luôn được gọi lại để thay đổi một ConnectionFactory đã tồn tại.

## 6. Kết hợp @ActiveProfiles và application-test.yml

Có thể giữ cấu hình chung trong profile test và chỉ cấp các giá trị phụ thuộc container bằng @DynamicPropertySource.

Ví dụ src/test/resources/application-test.yml:

~~~yaml
spring:
  r2dbc:
    pool:
      enabled: true
      initial-size: 1
      max-size: 5

logging:
  level:
    org.springframework.r2dbc: DEBUG
~~~

Test:

~~~java
@SpringBootTest
@ActiveProfiles("test")
@Testcontainers
class CustomerRepositoryIntegrationTest {
    // Container và @DynamicPropertySource.
}
~~~

Trong trường hợp này:

- application-test.yml chứa các giá trị tĩnh dành cho test.
- @DynamicPropertySource cung cấp URL, username và password được tạo khi container chạy.
- @ActiveProfiles("test") kích hoạt profile tương ứng.

Dynamic properties có độ ưu tiên cao hơn các nguồn cấu hình test thông thường như @TestPropertySource, system properties, environment variables và application property sources trong cơ chế TestContext. Vì vậy, giá trị dynamic có thể ghi đè URL tĩnh trong application-test.yml.

Không nên khai báo cùng một property ở nhiều nơi nếu không cần. Nếu có ghi đè, hãy hiểu rõ nguồn nào thắng để tránh test vô tình kết nối database khác.

## 7. Khi ứng dụng tự khai báo ConnectionFactory

Dynamic properties như spring.r2dbc.url chỉ được Spring Boot auto-configuration sử dụng khi Boot chịu trách nhiệm tạo ConnectionFactory.

Nếu ứng dụng tự khai báo bean:

~~~java
@Bean
ConnectionFactory connectionFactory() {
    return ConnectionFactories.get(
        "r2dbc:postgresql://localhost:5432/app"
    );
}
~~~

thì bean này có thể làm auto-configuration lùi lại. Khi đó, thay đổi spring.r2dbc.url trong @DynamicPropertySource không tự thay đổi URL hard-code bên trong bean.

Đây là nguyên nhân phổ biến khiến test đã đăng ký dynamic property nhưng ứng dụng vẫn kết nối database cũ.

### 7.1. Đọc property động trong custom ConnectionFactory bean

Nếu cần custom bean, hãy inject Environment và đọc property đã được đăng ký:

~~~java
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.ConnectionFactoryOptions;
import io.r2dbc.spi.ConnectionFactories;
import org.springframework.core.env.Environment;

@Configuration
class TestDatabaseConfiguration {

    @Bean
    ConnectionFactory connectionFactory(Environment environment) {
        String host =
            environment.getRequiredProperty("test.r2dbc.host");
        Integer port =
            environment.getRequiredProperty("test.r2dbc.port", Integer.class);
        String database =
            environment.getRequiredProperty("test.r2dbc.database");
        String username =
            environment.getRequiredProperty("test.r2dbc.username");
        String password =
            environment.getRequiredProperty("test.r2dbc.password");

        ConnectionFactoryOptions options =
            ConnectionFactoryOptions.builder()
                .option(ConnectionFactoryOptions.DRIVER, "postgresql")
                .option(ConnectionFactoryOptions.HOST, host)
                .option(ConnectionFactoryOptions.PORT, port)
                .option(ConnectionFactoryOptions.DATABASE, database)
                .option(ConnectionFactoryOptions.USER, username)
                .option(ConnectionFactoryOptions.PASSWORD, password)
                .build();

        return ConnectionFactories.get(options);
    }
}
~~~

Test đăng ký property riêng:

~~~java
@DynamicPropertySource
static void registerDatabase(DynamicPropertyRegistry registry) {
    registry.add("test.r2dbc.host", postgres::getHost);
    registry.add(
        "test.r2dbc.port",
        () -> postgres.getMappedPort(
            PostgreSQLContainer.POSTGRESQL_PORT
        )
    );
    registry.add("test.r2dbc.database", postgres::getDatabaseName);
    registry.add("test.r2dbc.username", postgres::getUsername);
    registry.add("test.r2dbc.password", postgres::getPassword);
}
~~~

Cách này hữu ích khi ứng dụng có logic tạo ConnectionFactory riêng. Tuy nhiên, chỉ nên khai báo custom factory trong test khi thực sự cần; nếu Boot auto-configuration đã đáp ứng nhu cầu, dùng spring.r2dbc.* đơn giản và ít cấu hình hơn.

### 7.2. Tránh custom bean đọc giá trị quá sớm

Không tạo ConnectionFactory static ở thời điểm class load trước khi dynamic property được đăng ký. Hãy để Spring tạo bean sau khi TestContext đã đăng ký property, qua dependency injection hoặc @Configuration.

Nếu custom factory cần SSL, driver-specific option hoặc pooling, hãy thêm các option tương ứng từ property đã bind. Tên và kiểu option phụ thuộc driver; không sao chép option của PostgreSQL sang driver khác một cách máy móc.

## 8. Dùng @ServiceConnection khi Spring Boot hỗ trợ

Một số phiên bản Spring Boot hỗ trợ Testcontainers service connection thông qua @ServiceConnection. Khi loại container và service connection factory tương ứng được hỗ trợ, Spring Boot có thể tạo ConnectionDetails và cấu hình kết nối mà không cần tự đăng ký từng property.

Ví dụ khái niệm:

~~~java
@Testcontainers
@SpringBootTest
class CustomerRepositoryIntegrationTest {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

}
~~~

Cách này ngắn hơn nhưng phụ thuộc phiên bản Spring Boot, module Testcontainers và loại service connection được hỗ trợ. Với R2DBC, hãy kiểm tra tài liệu phiên bản dự án để xác nhận service connection cung cấp R2DBC ConnectionDetails tương ứng.

Nếu phiên bản đang dùng không hỗ trợ service connection cho R2DBC, hoặc ứng dụng cần property tùy chỉnh, @DynamicPropertySource vẫn là cách rõ ràng và linh hoạt.

Không kết hợp @ServiceConnection và @DynamicPropertySource cho cùng một URL chỉ vì muốn chắc chắn. Hai nguồn cấu hình cùng cung cấp một giá trị có thể làm khó xác định nguồn nào đang được dùng.

## 9. Cấu hình động cho database khác PostgreSQL

Nguyên tắc chung không phụ thuộc PostgreSQL: lấy thông tin host, port, database và credentials từ container, sau đó tạo URL theo R2DBC driver tương ứng.

| Database | Driver scheme thường dùng | Ghi chú |
|---|---|---|
| PostgreSQL | r2dbc:postgresql:// | Driver artifact r2dbc-postgresql |
| MySQL | r2dbc:mysql:// | Driver artifact r2dbc-mysql |
| MariaDB | r2dbc:mariadb:// | Tùy driver được chọn |
| Microsoft SQL Server | r2dbc:mssql:// | Driver-specific options |
| H2 R2DBC | r2dbc:h2:mem:///... | Thường dùng cho test nhẹ, không thay thế hoàn toàn database production |

URL và option chính xác phụ thuộc driver và phiên bản. Hãy tham khảo tài liệu driver thay vì giả định tất cả đều có cùng cú pháp username/password, SSL hoặc query options.

### 9.1. Dùng Testcontainers với database mục tiêu

Nếu production dùng PostgreSQL, kiểm thử tích hợp nên ưu tiên PostgreSQL container cùng major version hoặc phiên bản được dự án hỗ trợ. Dùng H2 có thể nhanh hơn nhưng có khác biệt về SQL dialect, kiểu dữ liệu, sequence/identity, locking, constraint, JSON, collation và transaction semantics.

Testcontainers giúp kiểm thử trên database thật trong môi trường cô lập, tăng độ tin cậy của các test mapping, query và migration.

### 9.2. Test database không nên trỏ vào production

Property động cần trỏ tới container hoặc database test chuyên biệt. Không lấy URL production từ secret store rồi dùng làm default cho test. Một test có thể chạy migration, truncate bảng hoặc xóa dữ liệu; kết nối nhầm production có thể gây hậu quả nghiêm trọng.

Dùng credentials dùng riêng cho test, quyền tối thiểu và database có thể hủy sau test.

## 10. Dynamic property cho migration và schema setup

Ứng dụng R2DBC có thể dùng Flyway hoặc Liquibase để tạo schema trước khi test. Một số công cụ migration sử dụng JDBC thay vì R2DBC, nên cần cấu hình đúng JDBC URL riêng trỏ tới cùng container/database.

Ví dụ với Flyway:

~~~java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.r2dbc.url", TestDatabase::r2dbcUrl);
    registry.add("spring.r2dbc.username", postgres::getUsername);
    registry.add("spring.r2dbc.password", postgres::getPassword);

    registry.add("spring.flyway.url", postgres::getJdbcUrl);
    registry.add("spring.flyway.user", postgres::getUsername);
    registry.add("spring.flyway.password", postgres::getPassword);
}
~~~

Ở đây hai URL có scheme khác nhau nhưng cùng trỏ tới container database:

- spring.r2dbc.url dùng R2DBC driver.
- spring.flyway.url dùng JDBC driver cho migration.

Không gán JDBC URL vào spring.r2dbc.url hoặc R2DBC URL vào spring.flyway.url.

Nếu dự án dùng Liquibase, schema.sql hoặc một cơ chế migration khác, hãy cấp property đúng namespace và đảm bảo migration chạy trước khi test truy cập repository.

### 10.1. Tránh race giữa migration và test

Container cần sẵn sàng và schema phải được tạo trước khi repository query. Spring Boot thường chạy migration trong quá trình context startup khi cấu hình tương ứng được bật. Nếu test tự khởi tạo schema thủ công, hãy đảm bảo hoàn tất trước khi chạy test case.

Không để nhiều test class đồng thời chạy migration phá hủy trên cùng một database/schema dùng chung. Có thể dùng database/schema riêng hoặc tuần tự hóa nhóm test cần migration độc lập.

## 11. Kiểm tra cấu hình kết nối thực tế

Khi test báo lỗi connection, hãy kiểm tra từng lớp:

1. Container đã khởi động và database đã sẵn sàng chưa?
2. Host và mapped port có lấy từ container không?
3. URL có scheme R2DBC đúng với driver không?
4. Username/password/database name có trùng cấu hình container không?
5. Driver R2DBC có nằm trên test runtime classpath không?
6. Spring Boot có đang auto-configure ConnectionFactory hay ứng dụng tự khai báo bean?
7. Repository/template có dùng đúng ConnectionFactory không?
8. Migration đã chạy trên cùng database chưa?
9. TestContext có đang tái sử dụng ConnectionFactory trỏ tới container đã dừng không?
10. Connection pool có còn giữ connection cũ sau khi container restart không?

Có thể log thông tin host, port và database name trong test để chẩn đoán, nhưng tránh log password hoặc URL chứa credentials.

### 11.1. Không chỉ kiểm tra property string

Việc đọc được spring.r2dbc.url đúng không bảo đảm repository đang dùng factory được tạo từ property đó. Một custom ConnectionFactory bean, profile khác hoặc cấu hình multi-database có thể khiến repository dùng nguồn khác.

Hãy kiểm tra cả bean wiring và thực hiện một truy vấn nhỏ tới database container trong integration test.

## 12. Dùng profile test và dynamic property cùng nhau

Một cách tổ chức phổ biến:

~~~text
src/main/resources/
    application.yml

src/test/resources/
    application-test.yml

src/test/java/
    AbstractR2dbcIntegrationTest.java
    CustomerRepositoryIntegrationTest.java
    OrderRepositoryIntegrationTest.java
~~~

application.yml chứa cấu hình mặc định cho ứng dụng. application-test.yml chứa các giá trị test tĩnh như pool size, logging và feature flags. Testcontainers cung cấp URL và credentials qua @DynamicPropertySource.

Ví dụ:

~~~yaml
spring:
  r2dbc:
    pool:
      enabled: true
      max-size: 4

  flyway:
    enabled: true

logging:
  level:
    org.springframework.r2dbc: DEBUG
~~~

Không cần lưu URL container với port cố định trong file. Giá trị đó được đăng ký động từ container khi test chạy.

Nếu test dùng nhiều database, có thể đăng ký nhiều property namespace riêng:

~~~java
registry.add("app.orders.r2dbc.url", TestDatabases::ordersUrl);
registry.add("app.billing.r2dbc.url", TestDatabases::billingUrl);
~~~

Custom configuration sẽ bind các namespace này và tạo factory tương ứng. Nếu dùng Spring Boot auto-configuration mặc định, chỉ một spring.r2dbc.* namespace được chọn làm ConnectionFactory mặc định; nhiều database thường cần cấu hình bean riêng.

## 13. Những lỗi thường gặp

**Gán JDBC URL vào spring.r2dbc.url.** Testcontainers getJdbcUrl() trả URL JDBC. R2DBC cần driver scheme riêng. Hãy tạo r2dbc:postgresql://... từ host, mapped port và database name.

**Dùng port cố định 5432.** Testcontainers thường ánh xạ port container sang port host ngẫu nhiên. Dùng getMappedPort() thay vì hard-code 5432 trên host.

**Đăng ký property trong @BeforeEach.** @BeforeEach chạy quá muộn nếu ApplicationContext và ConnectionFactory đã được tạo. Dùng @DynamicPropertySource hoặc cơ chế property source chạy trước context initialization.

**Dynamic property không ảnh hưởng custom ConnectionFactory.** Nếu ứng dụng tự khai báo bean factory với URL cố định, Boot auto-configuration có thể đã lùi lại. Hãy để custom bean đọc property động hoặc bỏ custom bean nếu không cần.

**Container dừng nhưng Spring context vẫn được cache.** ConnectionFactory có thể trỏ tới port cũ. Dùng lifecycle container tương thích context cache, shared container hoặc tách context khi cần.

**Thiếu R2DBC driver dependency.** Có URL đúng nhưng driver không có trên classpath thì ConnectionFactory không thể được tạo. Đảm bảo test/runtime dependencies có driver R2DBC tương ứng.

**Chỉ cấp URL mà quên credentials.** Một số URL có thể chứa credentials, nhưng cách tách username/password thành property riêng thường rõ ràng hơn. Đảm bảo container và Spring dùng cùng giá trị.

**Migration chạy sang database khác.** Flyway thường dùng JDBC URL. Nếu chỉ cấu hình spring.r2dbc.url mà không cấu hình Flyway datasource, migration có thể không chạy vào database container mà ứng dụng đang query.

**Chạy test song song trên schema dùng chung.** Test có thể xóa dữ liệu hoặc migration cạnh tranh. Dùng schema/database riêng hoặc isolation phù hợp cho mỗi test group.

**Dùng credentials nhạy cảm trong source.** Không commit password thật hoặc URL production vào file test. Dùng credentials throwaway cho container và secret riêng nếu test phải kết nối dịch vụ đã quản lý.

## 14. Quy trình thiết lập thực tế

Một quy trình cơ bản cho Spring Boot + Spring Data R2DBC + Testcontainers:

1. Thêm R2DBC driver và Testcontainers dependency tương thích.
2. Khai báo container database bằng @Container static.
3. Chờ container sẵn sàng theo health check của Testcontainers.
4. Đăng ký spring.r2dbc.url bằng R2DBC scheme, host và mapped port.
5. Đăng ký username/password từ container.
6. Kích hoạt profile test nếu cần các cấu hình tĩnh riêng.
7. Bảo đảm Spring Boot auto-configuration dùng dynamic properties hoặc custom ConnectionFactory đọc đúng property.
8. Chạy migration trên đúng database container.
9. Thực hiện integration test qua repository/service.
10. Đảm bảo container không bị dừng trước khi ApplicationContext dùng nó kết thúc.

Với nhiều test class, cân nhắc base class hoặc singleton container để tránh khởi động database lặp lại và tránh context cache trỏ tới container đã dừng.

## 15. Nguyên tắc thiết kế

- Dùng @DynamicPropertySource để cấp property trước khi Spring tạo ApplicationContext.
- Dùng DynamicPropertyRegistry.add với Supplier để lấy host, mapped port và credentials từ container.
- Dùng spring.r2dbc.url, spring.r2dbc.username và spring.r2dbc.password cho Boot R2DBC auto-configuration.
- Tạo R2DBC URL theo scheme của driver; không dùng JDBC URL trực tiếp.
- Dùng getHost() và getMappedPort() thay vì hard-code localhost và port mặc định.
- Nếu tự khai báo ConnectionFactory, hãy inject property động vào bean đó.
- Ghép lifecycle Testcontainers với Spring TestContext cache.
- Tách property tĩnh trong application-test.yml khỏi giá trị động của container.
- Cấu hình migration JDBC riêng nếu công cụ migration dùng JDBC.
- Dùng database/credentials cô lập dành riêng cho test.
- Kiểm tra repository thực sự dùng ConnectionFactory được tạo từ dynamic properties.
- Kiểm thử trên đúng database engine và driver gần với production.

## 16. Ghi nhớ

Thuộc tính kết nối động cho phép test lấy URL, host, port, database và credentials từ môi trường đang chạy thay vì cố định chúng trong file cấu hình. Với Spring Boot R2DBC, @DynamicPropertySource có thể đăng ký spring.r2dbc.url, spring.r2dbc.username và spring.r2dbc.password từ Testcontainers trước khi ApplicationContext tạo ConnectionFactory.

Hãy dùng R2DBC URL theo driver và mapped port của container; JDBC URL từ Testcontainers chỉ dành cho JDBC-based tool như Flyway. Nếu ứng dụng tự tạo ConnectionFactory, dynamic property của Boot không tự thay đổi bean đó, nên custom factory phải đọc property tương ứng. Cuối cùng, quản lý đúng vòng đời container cùng Spring context cache và luôn dùng database test cô lập để các integration test có thể chạy lặp lại an toàn.

