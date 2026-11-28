# Testcontainers, thông tin kết nối động và vòng đời tài nguyên kiểm thử

Spring Session cần một kho session có thể được truy cập trong suốt vòng đời request. Với ứng dụng dùng Redis hoặc JDBC, unit test dựa trên mock không chứng minh được kết nối, schema, serialization, TTL, transaction hay khả năng chia sẻ session giữa các request. Testcontainers giúp khởi chạy backend thật trong container dành riêng cho test; Spring Boot và Spring Test có thể nhận thông tin kết nối của container một cách động để cấu hình repository.

Một integration test tốt phải kiểm soát ba phần: backend mà test đang dùng, thông tin kết nối mà application context nhận được, và thời điểm tài nguyên được tạo/đóng. Nếu container dừng trong khi Spring context vẫn được cache, test sau có thể thất bại khó đoán. Nếu nhiều test dùng chung database hoặc Redis namespace mà không cô lập dữ liệu, kết quả có thể phụ thuộc thứ tự chạy.

Bài học này trình bày cách dùng Testcontainers với Spring Session JDBC và Redis, cách cấp URL/host/port động bằng @DynamicPropertySource, lựa chọn @ServiceConnection của Spring Boot, quản lý vòng đời JUnit, và cách tránh lỗi do context cache, chạy song song hoặc dọn tài nguyên sai thời điểm.

## 1. Vì sao cần backend thật trong integration test?

Mock SessionRepository hữu ích để kiểm tra logic controller hoặc tiêm lỗi có chủ đích. Tuy nhiên, mock không kiểm tra các hành vi của backend:

- JDBC có chạy đúng schema SPRING_SESSION và SPRING_SESSION_ATTRIBUTES không;
- transaction và foreign key có hoạt động đúng không;
- Redis có lưu key, TTL và namespace đúng không;
- serializer có thể ghi rồi đọc lại attributes thực tế không;
- session có được chia sẻ giữa hai request hoặc hai application context không;
- connection pool có dùng đúng host/port do container cấp không;
- cleanup và expiration có tương tác đúng với backend không.

Testcontainers chạy database hoặc Redis thực tế trong container. Test vẫn có thể dùng @SpringBootTest, MockMvc hoặc WebTestClient, nhưng request sẽ đi qua cấu hình repository thật và backend riêng cho test.

Testcontainers không thay thế unit test. Nên giữ các unit test nhanh cho logic thuần và dùng integration test có backend thật cho các hợp đồng storage, transaction, serialization, expiration và multi-instance.

## 2. Dependency và phiên bản

Với Gradle và Spring Boot dependency management, có thể khai báo:

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")
    testImplementation("org.springframework.boot:spring-boot-testcontainers")
}
~~~

spring-boot-testcontainers cần thiết khi dùng @ServiceConnection. Nếu chỉ dùng @DynamicPropertySource, có thể không cần module này. Với Redis dùng GenericContainer, module JUnit Jupiter cung cấp tích hợp JUnit; container image được chọn qua Docker image name.

Để tránh lệch phiên bản giữa các module Testcontainers, dùng BOM phù hợp với dự án hoặc version catalog đã được quản lý. Spring Boot cũng quản lý phiên bản các thư viện tương thích qua dependency management. Không tùy tiện trộn module Testcontainers thuộc các major version khác nhau.

Ví dụ Maven tương đương:

~~~xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-testcontainers</artifactId>
    <scope>test</scope>
</dependency>
~~~

Các dependency không có version riêng trong ví dụ khi dự án đã import BOM quản lý tương ứng. Nếu không dùng dependency management, phải khai báo version tương thích cho toàn bộ nhóm thư viện.

## 3. Cách Testcontainers quản lý container

Testcontainers dùng Docker-compatible runtime để tạo tài nguyên tạm thời như PostgreSQL, MySQL hoặc Redis. Khi container khởi động, thư viện có thể ánh xạ cổng nội bộ sang một cổng host động. Test phải lấy thông tin từ container đang chạy thay vì giả định cổng cố định.

Với JUnit Jupiter, extension thường được kích hoạt bằng @Testcontainers, còn container được đánh dấu @Container:

- Container field static: được khởi động một lần cho test class và dừng sau class.
- Container field không static: được khởi động và dừng cho từng test method.

Static container giảm thời gian khởi động khi nhiều test method dùng chung backend. Instance container tăng mức cô lập nhưng tốn thời gian hơn. Dù chọn cách nào, dữ liệu test vẫn cần được cô lập riêng; vòng đời container không tự xóa mọi bản ghi hoặc key giữa các test method.

## 4. PostgreSQL container cho Spring Session JDBC

Ví dụ dùng PostgreSQL container và @DynamicPropertySource:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class JdbcSessionIntegrationTests {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("session_test")
                    .withUsername("session_user")
                    .withPassword("session_password");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add("spring.datasource.driver-class-name",
                postgres::getDriverClassName);
        registry.add("spring.session.jdbc.initialize-schema",
                () -> "always");
    }

    @Test
    void contextStartsAgainstTheContainerDatabase() {
        // Gọi repository hoặc endpoint dùng Spring Session JDBC.
    }
}
~~~

getJdbcUrl(), getUsername(), getPassword() và getDriverClassName() lấy thông tin từ container đang chạy. Test không hard-code host port PostgreSQL. Testcontainers có thể ánh xạ cổng 5432 trong container sang một cổng host khác nhau ở mỗi lần chạy.

spring.session.jdbc.initialize-schema=always yêu cầu Spring Session khởi tạo schema JDBC theo cấu hình của ứng dụng test. Nếu dự án dùng Flyway/Liquibase hoặc quản lý schema bằng migration riêng, hãy chọn một chủ sở hữu schema duy nhất và cấu hình thứ tự migration rõ ràng; tránh để cả Spring Session lẫn migration tool cùng tạo một bảng theo hai định nghĩa khác nhau.

Container image nên được pin theo major/minor hoặc digest phù hợp với môi trường CI. Không dùng tag trôi nổi nếu test cần tái lập kết quả giữa các lần chạy.

## 5. Redis container cho Spring Session

Redis có thể chạy bằng GenericContainer và expose cổng 6379:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
class RedisSessionIntegrationTests {

    @Container
    static final GenericContainer<?> redis =
            new GenericContainer<>(DockerImageName.parse("redis:7-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add("spring.data.redis.port",
                () -> redis.getMappedPort(6379));
        registry.add("spring.session.redis.namespace",
                () -> "test:spring-session");
    }

    @Test
    void contextStartsAgainstTheContainerRedis() {
        // Tạo và khôi phục session qua repository Redis thật.
    }
}
~~~

Spring Boot 3.x dùng property spring.data.redis.*. Dự án Boot cũ có thể dùng prefix khác; hãy đối chiếu cấu hình theo đúng phiên bản đang chạy. getHost() và getMappedPort(6379) là nguồn kết nối thực tế. Không mặc định Redis luôn ở localhost:6379.

Namespace riêng giúp test không đụng vào key của ứng dụng hoặc test suite khác. Nếu mỗi test class dùng cùng Redis container, có thể cấp namespace riêng theo class hoặc xóa đúng các key thuộc namespace test sau mỗi test. Không chạy FLUSHALL trên một Redis dùng chung cho nhiều test song song.

Nếu cần kiểm tra keyspace notifications hoặc expiration event, cấu hình Redis container và repository tương ứng với yêu cầu test. Một container Redis mặc định không chứng minh cấu hình production đã bật đúng notification hoặc ACL.

## 6. Thông tin kết nối động bằng DynamicPropertySource

@DynamicPropertySource là extension point của Spring TestContext. Phương thức phải là static và nhận DynamicPropertyRegistry. Mỗi property được đăng ký cùng một Supplier, để giá trị được lấy khi Spring cần resolve property.

~~~java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

Ưu điểm:

- Không cần ghi host/port cố định vào application-test.yml.
- Dùng được với container có cổng host được ánh xạ động.
- Có thể đăng ký URL, username, password, Redis host/port, namespace và các property riêng.
- Có thể dùng cùng @SpringBootTest, @DataJdbcTest hoặc test slice phù hợp.

Các nguyên tắc cần giữ:

1. Container phải được khởi động trước khi property supplier được gọi.
2. Supplier phải lấy dữ liệu từ chính container field đang dùng, không lấy từ một container khác.
3. Property name phải khớp với Spring Boot/Spring Session version của dự án.
4. Không lưu connection string chứa password vào log hoặc artifact test.
5. Không dùng cổng mặc định của host; dùng mapped port do Testcontainers cấp.

DynamicPropertySource chỉ đăng ký giá trị cấu hình. Nó không tự khởi động container, không quản lý cleanup và không bảo đảm Spring context sẽ đóng trước khi container dừng. Các trách nhiệm lifecycle vẫn phải được thiết kế riêng.

## 7. Spring Boot ServiceConnection

Từ Spring Boot 3.1, @ServiceConnection có thể tạo ConnectionDetails từ container được hỗ trợ, giảm việc tự khai báo từng property. Với PostgreSQL:

~~~java
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;

@Testcontainers
@SpringBootTest
class JdbcSessionServiceConnectionTests {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

Spring Boot nhận diện loại container và cung cấp connection details phù hợp cho datasource. Cách này gọn khi container type có service connection factory được Spring Boot hỗ trợ.

Không phải mọi GenericContainer đều tự được nhận diện. Với container tùy chỉnh hoặc backend không có service connection factory, dùng @DynamicPropertySource. Một số generic container có thể cần khai báo service name tường minh theo API Spring Boot version; hãy kiểm tra tài liệu đúng phiên bản trước khi áp dụng.

Không cần vừa khai báo @ServiceConnection vừa đăng ký lại cùng datasource properties bằng @DynamicPropertySource nếu không có lý do cụ thể. Hai nguồn cấu hình cùng tồn tại có thể làm việc ưu tiên property khó hiểu. Chọn một cơ chế rõ ràng cho mỗi service.

@ServiceConnection chỉ cung cấp thông tin kết nối. Nó không thay thế migration/schema initialization, namespace cô lập, lifecycle management hoặc assertion về dữ liệu session.

## 8. Chọn cách cung cấp kết nối

| Tình huống | Cách phù hợp |
|---|---|
| PostgreSQL/MySQL container được Spring Boot hỗ trợ | Ưu tiên @ServiceConnection nếu dùng Boot 3.1+ |
| Redis container hoặc GenericContainer tùy chỉnh | @DynamicPropertySource thường rõ ràng và linh hoạt |
| Nhiều property đặc thù như namespace, timeout, key prefix | @DynamicPropertySource |
| Ứng dụng không dùng Spring Boot | @DynamicPropertySource hoặc cấu hình test context trực tiếp |
| Backend nội bộ có connection factory riêng | Dynamic properties hoặc test configuration riêng |
| Muốn kiểm tra giá trị cấu hình thực tế | Đọc Environment/bean đã cấu hình trong test, không chỉ kiểm tra annotation |

@ServiceConnection và @DynamicPropertySource không thay đổi cách Spring Session sử dụng repository. Chúng chỉ giải quyết việc Spring context nhận đúng thông tin để kết nối backend test.

## 9. Kiểm tra session thực sự được lưu và khôi phục

Một test context khởi động thành công chưa đủ chứng minh Spring Session đã dùng đúng backend. Hãy kiểm tra hành vi qua request:

1. Gửi request tạo hoặc cập nhật session attribute.
2. Lấy cookie session từ response.
3. Gửi request thứ hai kèm cookie đó.
4. Xác nhận attribute được khôi phục.
5. Kiểm tra dữ liệu trong backend test hoặc dùng repository API để xác nhận.

Ví dụ với MockMvc, giả sử ứng dụng test có endpoint /test/session để ghi và đọc một attribute:

~~~java
@Autowired
MockMvc mockMvc;

@Test
void sessionSurvivesAcrossRequests() throws Exception {
    MvcResult first = mockMvc.perform(post("/test/session")
                    .param("value", "spring-session"))
            .andExpect(status().isOk())
            .andReturn();

    Cookie sessionCookie = first.getResponse().getCookie("SESSION");
    assertThat(sessionCookie).isNotNull();

    mockMvc.perform(get("/test/session").cookie(sessionCookie))
            .andExpect(status().isOk())
            .andExpect(content().string("spring-session"));
}
~~~

Endpoint này chỉ phục vụ test và cookie name phải khớp CookieSerializer của ứng dụng. Nếu ứng dụng dùng tên cookie mặc định khác, điều chỉnh assertion. Test này xác nhận session qua request, nhưng để chứng minh hai instance chia sẻ dữ liệu, cần gửi request tới hai application instance/context dùng cùng backend.

Với JDBC, có thể xác nhận bảng session và attributes đã được ghi. Với Redis, có thể dùng Redis client/test inspection để xác nhận key thuộc namespace đã cấu hình. Tránh phụ thuộc quá nhiều vào cấu trúc key nội bộ nếu mục tiêu test chỉ là contract công khai; cấu trúc key có thể thay đổi theo phiên bản.

## 10. Vòng đời container với JUnit Jupiter

Có hai kiểu khai báo phổ biến:

~~~java
@Container
static PostgreSQLContainer<?> postgres = ...;
~~~

Container static được khởi động một lần cho class và dừng sau class.

~~~java
@Container
PostgreSQLContainer<?> postgres = ...;
~~~

Container instance được khởi động trước từng test method và dừng sau method đó.

| Kiểu | Lợi ích | Chi phí/rủi ro |
|---|---|---|
| Static per class | Khởi động một lần, các method dùng chung backend | Dữ liệu giữa method cần cleanup; container dừng sau class |
| Instance per method | Cô lập backend ở mức method | Khởi động chậm, tốn CPU/RAM và thời gian |
| Singleton dùng toàn test JVM | Có thể dùng chung backend giữa nhiều class | Phải quản lý context cache, trạng thái test và shutdown rõ ràng |

Chọn lifecycle dựa trên mục tiêu cô lập và thời gian chạy. Không dùng instance container cho mọi test nếu backend khởi động nặng và test không cần cô lập ở mức process.

## 11. Spring TestContext cache và container đã dừng

Spring TestContext có thể cache ApplicationContext để tái sử dụng giữa các test class có cấu hình tương thích. Trong khi đó, JUnit Testcontainers extension dừng static container sau khi class kết thúc.

Điều này tạo ra một tình huống nguy hiểm:

1. Test class A khởi động container và Spring context kết nối đến container.
2. Class A kết thúc; JUnit extension dừng container.
3. Spring giữ context A trong cache.
4. Test class B dùng lại context đó.
5. DataSource/RedisConnectionFactory trong context vẫn trỏ tới cổng của container đã dừng.
6. Test B gặp connection refused dù context không được tạo lại.

Các cách xử lý:

- Dùng singleton container tồn tại trong toàn test JVM nếu nhiều class cần cùng backend.
- Dùng @DirtiesContext(classMode = AFTER_CLASS) khi cần đóng context sau class để tránh tái sử dụng context gắn với container đã dừng.
- Tổ chức các test dùng chung một base class/context và một lifecycle container tương thích.
- Giảm cache hoặc tách test suite khi cần cô lập hoàn toàn.

Không thêm @DirtiesContext vào mọi test một cách máy móc; nó làm tăng thời gian tạo context. Chọn chiến lược có chủ đích và xác nhận bằng test chạy liên tiếp nhiều class.

## 12. Singleton container cho nhiều test class

Khi nhiều test class dùng chung backend, có thể tạo singleton container trong base class:

~~~java
abstract class SharedPostgresTestBase {

    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("session_test")
                    .withUsername("session_user")
                    .withPassword("session_password");

    static {
        POSTGRES.start();
    }

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
    }
}
~~~

Trong pattern này, không gắn @Container lên singleton nếu muốn container tiếp tục sống qua các class; JUnit extension có thể dừng nó sau từng class. Testcontainers/Ryuk hỗ trợ dọn container còn lại khi JVM kết thúc bất thường hoặc hoàn tất, tùy môi trường. Có thể đăng ký shutdown hook nếu dự án có yêu cầu lifecycle riêng; tránh dừng container khi một context còn sử dụng.

Singleton làm test chạy nhanh hơn nhưng chia sẻ backend. Mỗi class vẫn phải cô lập dữ liệu: dùng schema/database riêng, namespace riêng hoặc cleanup theo tập dữ liệu do test tạo. Không để một test xóa dữ liệu của test khác.

## 13. Cleanup dữ liệu giữa các test

Container mới cho mỗi class không có nghĩa mọi test method đều có database trống. Static container giữ dữ liệu sau mỗi method. Cần quyết định chiến lược reset:

**JDBC**

- Tạo database/schema riêng cho test class.
- Dùng transaction rollback khi toàn bộ thao tác test tham gia cùng transaction (không áp dụng mặc định cho mọi HTTP request/async operation).
- Xóa các session/attribute do test tạo bằng fixture hoặc repository cleanup.
- Reset sequence/table có kiểm soát khi cần.
- Không truncate bảng session nếu test khác đang chạy song song trên cùng database.

**Redis**

- Dùng namespace riêng theo test class hoặc test suite.
- Xóa key theo namespace của test, không flush toàn server dùng chung.
- Đặt TTL ngắn cho dữ liệu test nếu phù hợp, nhưng không dựa vào TTL để thay cleanup xác định.
- Không dùng chung prefix với ứng dụng developer hoặc môi trường ngoài test.

Khi chạy song song, database/schema/namespace phải thực sự tách biệt hoặc test phải dùng dữ liệu có ID duy nhất. Cleanup toàn cục có thể xóa session của test đang chạy ở thread khác.

## 14. Test song song và cổng động

Testcontainers ánh xạ cổng container sang cổng host động. Điều này giảm xung đột khi nhiều container cùng expose cổng PostgreSQL 5432 hoặc Redis 6379. Luôn lấy cổng bằng getMappedPort() và host bằng getHost().

Tuy vậy, cổng động không tự làm test an toàn khi chạy song song. Cần xem xét:

- mỗi class có container riêng hay dùng singleton;
- các test có chia sẻ cùng database/schema không;
- Redis namespace có trùng không;
- cleanup có xóa dữ liệu của test khác không;
- connection pool có bị tạo nhiều quá mức;
- CPU/RAM đủ cho số container đồng thời không;
- port mapping và network có được resolve theo container instance tương ứng không.

Nếu test suite bật parallel execution, bắt đầu bằng mức song song thấp và theo dõi tài nguyên. Tăng concurrency chỉ sau khi dữ liệu và lifecycle được cô lập.

## 15. Wait strategy và readiness

Container ở trạng thái running không nhất thiết dịch vụ bên trong đã sẵn sàng nhận kết nối. Testcontainers dùng wait strategy để đợi điều kiện readiness. Các module database thường có wait strategy mặc định; container tùy chỉnh có thể cần log message, health check hoặc port readiness.

Ví dụ với Redis generic container:

~~~java
import org.testcontainers.containers.wait.strategy.Wait;

GenericContainer<?> redis = new GenericContainer<>(
        DockerImageName.parse("redis:7-alpine"))
        .withExposedPorts(6379)
        .waitingFor(Wait.forListeningPort());
~~~

Port listening chỉ chứng minh cổng mở, không chứng minh authentication, ACL, database schema hoặc keyspace notifications đã được cấu hình đúng. Sau khi container sẵn sàng, test nên thực hiện một thao tác health/read-write thực tế nếu đó là điều kiện cần cho Spring Session.

Không tăng startup timeout quá lớn để che giấu image hoặc service khởi động sai. Hãy đọc log container và điều chỉnh wait strategy dựa trên readiness signal phù hợp.

## 16. Kiểm thử Spring Session JDBC end-to-end

Với JDBC, một integration test nên xác minh:

1. Spring context tạo được DataSource trỏ tới PostgreSQL container.
2. Schema Spring Session được khởi tạo hoặc migration đã chạy.
3. Request tạo session và response phát cookie.
4. Request tiếp theo dùng cookie khôi phục đúng attributes.
5. Logout/invalidate xóa hoặc làm mất hiệu lực session theo contract.
6. Session hết hạn không được trả về dù hàng vật lý có thể chờ cleanup.
7. Hai instance dùng cùng database có thể chia sẻ session.

Nếu kiểm tra schema bằng spring.session.jdbc.initialize-schema=always, bảo đảm test database riêng và không dùng property này như cách thay thế migration production. Production thường nên quản lý schema bằng migration đã được review.

Để kiểm tra transaction và foreign key cascade, dùng đúng DBMS production. H2 có thể khác PostgreSQL/MySQL về locking, DDL và query plan nên không phải bằng chứng đầy đủ cho hành vi production.

## 17. Kiểm thử Spring Session Redis end-to-end

Với Redis, xác minh:

- Spring Boot nhận host/port động từ container.
- Repository ghi và đọc session qua Redis thật.
- Namespace được cô lập.
- Session TTL được thiết lập/gia hạn theo chính sách.
- Logout hoặc invalidate khiến session không còn được khôi phục.
- Principal index/keyspace notifications hoạt động nếu tính năng đó được bật.
- Hai instance cùng dùng Redis có thể khôi phục session do node còn lại tạo.

Đừng chỉ kiểm tra PING. Một Redis server có thể phản hồi PING nhưng ứng dụng vẫn sai password, namespace, serializer hoặc quyền thao tác key. Hãy tạo và khôi phục một session thực tế qua Spring Session.

Nếu production bật TLS, ACL, password hoặc keyspace notifications, container test nên mô phỏng các phần có ảnh hưởng đến contract. Một container mặc định chỉ kiểm tra đường cơ bản.

## 18. Kiểm tra nhiều ApplicationContext hoặc nhiều instance

Để chứng minh session được chia sẻ, cần ít nhất hai repository/client cùng truy cập một backend. Có thể tạo hai application context với cấu hình server port riêng, cùng nhận datasource/Redis connection details của container:

~~~mermaid
flowchart LR
    C[HTTP client giữ cookie] --> A[Application context A]
    C --> B[Application context B]
    A --> RA[Spring Session repository A]
    B --> RB[Spring Session repository B]
    RA --> DB[(PostgreSQL hoặc Redis container)]
    RB --> DB
~~~

Test tạo session qua A, giữ cookie, rồi gửi request tới B. B phải khôi phục đúng session attributes và SecurityContext theo cấu hình. Sau đó có thể logout qua B và xác minh A không còn khôi phục session cũ.

Hai context trong cùng JVM không hoàn toàn tương đương hai process production, nhưng có thể kiểm tra phần lớn contract shared-store. Với yêu cầu về network, load balancer hoặc failover, bổ sung test chạy hai application process/container riêng.

## 19. DynamicPropertySource và thứ tự khởi tạo

Một lỗi phổ biến là property supplier được gọi khi container chưa chạy hoặc lấy port trước khi Testcontainers ánh xạ. Hãy để JUnit/Testcontainers quản lý container lifecycle và dùng supplier tham chiếu container đã được khởi động theo đúng extension lifecycle.

Nếu dùng singleton container, gọi start() trước khi Spring tạo context. Không khởi động container trong controller, PostConstruct của bean nghiệp vụ hoặc trong test method sau khi context đã refresh, vì DataSource/RedisConnectionFactory có thể đã được tạo với giá trị chưa hợp lệ.

Không cache thủ công getMappedPort() trước khi container start. Gọi getter trong supplier sau khi lifecycle đã khởi động. Nếu container restart, port mapping có thể thay đổi; context cũ không tự cập nhật connection factory. Cần đóng và tạo lại context hoặc giữ container sống xuyên suốt context.

## 20. @ServiceConnection và context cache

@ServiceConnection giảm việc tự đăng ký connection properties nhưng không giải quyết vấn đề container lifecycle. Nếu static @Container dừng sau class trong khi Spring context được cache, connection details trong context vẫn trỏ đến container đã dừng.

Do đó, quy tắc lifecycle vẫn giống khi dùng @DynamicPropertySource:

- container phải sống ít nhất bằng context sử dụng nó;
- nếu container dừng, context phụ thuộc phải được đóng hoặc tạo mới;
- nếu context được cache xuyên class, chọn singleton container hoặc chiến lược @DirtiesContext phù hợp;
- không để test class khác dùng lại connection details của container cũ.

## 21. Dọn tài nguyên và kết thúc test

Testcontainers JUnit extension tự dừng container được khai báo bằng @Container theo lifecycle của class/method. Ryuk là cơ chế hỗ trợ dọn container/network còn sót khi JVM kết thúc hoặc test bị ngắt, tùy môi trường. Không nên dựa vào Ryuk để bỏ qua quản lý tài nguyên của ứng dụng.

Các tài nguyên cần đóng hoặc dọn:

- container database/Redis;
- Spring ApplicationContext và DataSource connection pool;
- Redis client/connection factory;
- embedded web server;
- thread pool hoặc scheduler do test tạo;
- test data, schema và namespace;
- temporary file, network hoặc volume do test tạo.

Khi tự quản lý container bằng start()/stop(), dùng lifecycle rõ ràng và đảm bảo context/connection pool được đóng trước khi backend dừng. Nếu sử dụng JUnit extension, tránh gọi stop thủ công trong @AfterAll trừ khi có lý do cụ thể; không để hai thành phần cùng quản lý một resource với lifecycle mâu thuẫn.

Container reuse có thể rút ngắn thời gian chạy local, nhưng làm trạng thái backend tồn tại giữa các lần chạy. Đây là chế độ opt-in và không nên bật mặc định trong CI hoặc test cần tính tái lập. Nếu dùng local reuse, phải cô lập namespace và dữ liệu, đồng thời không dựa vào trạng thái cũ để test pass.

## 22. Xử lý lỗi và chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Connection refused | Container chưa sẵn sàng hoặc đã dừng | Kiểm tra lifecycle, wait strategy và log container |
| Kết nối nhầm cổng | Hard-code cổng container thay vì mapped port | Dùng getHost/getMappedPort hoặc container connection details |
| Context cache dùng container cũ | Container dừng sau class nhưng context còn được tái sử dụng | Singleton lifecycle hoặc đóng context sau class |
| Spring không nhận dynamic property | Sai property name hoặc method không static | Kiểm tra @DynamicPropertySource và version Boot |
| Không inject được ServiceConnection | Thiếu spring-boot-testcontainers hoặc container type không được hỗ trợ | Kiểm tra dependency và service connection factory |
| JDBC thiếu bảng session | Schema initialization/migration chưa chạy | Kiểm tra initialize-schema, migration order và schema |
| Redis session không tìm thấy | Namespace, host, port hoặc serializer không khớp | Kiểm tra property và round-trip request |
| Test ảnh hưởng lẫn nhau | Dùng chung schema/namespace và cleanup rộng | Tạo namespace/schema riêng hoặc dữ liệu duy nhất |
| Test song song chập chờn | Tài nguyên thiếu hoặc cleanup race | Giảm concurrency, cô lập dữ liệu và xem log |
| Container dừng quá sớm | Lifecycle JUnit không phù hợp context cache | So sánh thời gian sống của context và container |
| Container không được dọn | Test bị kill hoặc Ryuk không hoạt động trong môi trường | Kiểm tra Docker runtime, Ryuk và cleanup pipeline |

Luôn xem log container và log khởi tạo Spring context trước khi tăng timeout. Không in password hoặc connection URL đầy đủ vào log CI. Nếu cần chẩn đoán, log host/port và tên service đã được làm sạch.

## 23. Kiểm thử song song, cô lập và tính tái lập

Một integration test đáng tin cậy phải cho cùng kết quả dù chạy riêng, chạy cả suite hoặc chạy lại sau một lần thất bại. Để đạt điều đó:

- dùng image tag cố định;
- lấy cổng động từ container;
- tạo database/schema/namespace dành riêng;
- dùng ID test duy nhất;
- cleanup đúng phạm vi dữ liệu do test tạo;
- không phụ thuộc thứ tự test;
- tránh dùng thời gian sleep cố định để chờ service;
- dùng wait strategy và eventual assertion có timeout;
- giới hạn số container chạy song song theo tài nguyên CI;
- ghi lại image version, Testcontainers version và backend version khi test thất bại.

Nếu test cần chờ session expiration, chọn TTL ngắn trong profile test và dùng polling assertion với deadline thay vì Thread.sleep() dài. Test cần phân biệt expiry logic với cleanup vật lý nếu repository có job dọn riêng.

## 24. Checklist cho Spring Session integration test

- [ ] Dependency Testcontainers/JUnit và module backend dùng cùng version được quản lý.
- [ ] Container image được pin theo version phù hợp.
- [ ] Container được khởi động trước khi Spring resolve connection properties.
- [ ] Dùng @DynamicPropertySource hoặc @ServiceConnection nhất quán.
- [ ] Dùng host và mapped port do Testcontainers cung cấp.
- [ ] Spring Session JDBC schema/migration được khởi tạo rõ ràng.
- [ ] Redis namespace hoặc JDBC schema được cô lập.
- [ ] Test tạo session, khôi phục session qua request tiếp theo và kiểm tra attributes.
- [ ] Test logout, expiration và repository behavior cần thiết.
- [ ] Test nhiều context/instance nếu module cần shared session.
- [ ] Container sống đủ lâu cho mọi ApplicationContext sử dụng nó.
- [ ] Context/connection pool được đóng trước khi container bị dừng.
- [ ] Cleanup không xóa dữ liệu của test chạy song song.
- [ ] Có kiểm tra log, readiness và lỗi backend khi khởi động.
- [ ] CI có Docker-compatible runtime và quyền cần thiết cho Testcontainers.

## 25. Quy trình triển khai thực tế

1. Chọn backend phù hợp với repository production: PostgreSQL/MySQL cho JDBC hoặc Redis cho Redis repository.
2. Khai báo Testcontainers module và đồng bộ version qua BOM.
3. Tạo container static theo class hoặc singleton theo test suite dựa trên thời gian sống của Spring context.
4. Cấp thông tin kết nối bằng @ServiceConnection nếu được hỗ trợ; nếu không, dùng @DynamicPropertySource.
5. Cấu hình schema, namespace, timeout và serializer theo mục tiêu test.
6. Chạy round-trip session qua request thật.
7. Kiểm tra expiration, logout, index/event nếu tính năng đó thuộc phạm vi.
8. Chạy test nhiều instance và test song song khi cần.
9. Đóng context, pool, container và dọn dữ liệu theo lifecycle đã chọn.
10. Chạy lại test class riêng lẻ và cả suite để phát hiện phụ thuộc thứ tự.

Testcontainers làm cho integration test gần môi trường vận hành hơn, nhưng chỉ đáng tin khi connection details lấy từ container thực tế, resource lifecycle khớp với Spring context, và dữ liệu được cô lập. @DynamicPropertySource cung cấp cấu hình động linh hoạt; @ServiceConnection giảm boilerplate với service được Spring Boot hỗ trợ. Cả hai đều cần một chiến lược rõ ràng cho khởi động, context cache, cleanup và shutdown để kiểm thử Spring Session có thể tái lập trên máy developer lẫn CI.

## Tài liệu tham khảo

- Testcontainers for Java – JUnit 5: https://java.testcontainers.org/test_framework_integration/junit_5/
- Testcontainers for Java – Container lifecycle: https://java.testcontainers.org/test_framework_integration/manual_lifecycle_control/
- Spring Framework – DynamicPropertySource: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html
- Spring Boot – Testcontainers and service connections: https://docs.spring.io/spring-boot/reference/testing/testcontainers.html
- Spring Session – JDBC configuration: https://docs.spring.io/spring-session/reference/configuration/jdbc.html
- Spring Session – Redis configuration: https://docs.spring.io/spring-session/reference/configuration/redis.html
