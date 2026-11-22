# Container dùng chung, context được cache và vòng đời kết nối

## 1. Tình huống thực tế: test đầu PASS, test sau báo connection refused

Một bộ kiểm thử Spring Boot tích hợp PostgreSQL, Redis, Kafka hoặc RabbitMQ bằng Testcontainers. Test class A chạy thành công; khi test class B bắt đầu, Spring TestContext Framework tái sử dụng `ApplicationContext` của A để tiết kiệm thời gian. Thế nhưng Testcontainers JUnit 5 extension đã **dừng container ở cuối class A**. DataSource/HikariCP/Kafka listener trong context cache vẫn giữ cấu hình trỏ đến host/port cũ. Hậu quả là test B thất bại với `Connection refused`, `Connection is closed`, `SQLTransientConnectionException`, `TimeoutException` hoặc lỗi client-specific khác.

Mấu chốt không nằm ở việc Java test dùng `static` hay không, mà ở **hai vòng đời được quản lý bởi hai hệ thống khác nhau**:

- **JUnit/Testcontainers extension**: `@Container static` thường start một lần cho mỗi test class và stop khi class kết thúc.
- **Spring TestContext cache**: `ApplicationContext` có thể sống qua nhiều test classes (có cùng cache key) và chỉ đóng khi đánh dấu dirty, bị loại theo LRU hoặc JVM kết thúc.
- **Spring-managed Testcontainers bean**: container là bean thuộc `ApplicationContext`, được Spring Boot start trước các beans phụ thuộc và stop **sau** khi các beans khác đã destroy; vì vậy lifetime đi cùng cached context.
- **Singleton container pattern không có JUnit extension**: container start trong static initializer cho toàn JVM/test run; các Spring contexts có thể dùng chung. Phải tự hiểu cleanup và data isolation.

Đề bài này thuộc chủ đề **Context cache và hiệu năng**: sử dụng container dùng chung để tăng tốc **nhưng không tái sử dụng các connection đã hỏng, không làm nhiễm dữ liệu test và không diễn giải sai dấu hiệu cache hit**.

### Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Giải thích cache key/lifecycle của Spring TestContext Framework 6.2 và tác dụng với `@SpringBootTest`.
2. Phân biệt **container instance**, Docker process, mapped port, `ApplicationContext`, `DataSource`, connection pool và connection thực.
3. Biết khi nào `@Testcontainers + @Container` an toàn, và vì sao static field **không mặc nhiên là singleton cho toàn suite**.
4. Sử dụng `@TestConfiguration` + `@Bean` + `@ServiceConnection` theo Spring Boot 3.5 để container có vòng đời cùng cached context.
5. Hiểu lựa chọn `@ImportTestcontainers` và singleton static initializer + `@DynamicPropertySource`.
6. Tránh cache-key fragmentation do `@ActiveProfiles`, `@TestPropertySource`, `@DynamicPropertySource`, bean overrides, `@DirtiesContext` và các cấu hình khác.
7. Kiểm tra context/controller/database đang dùng **endpoint hiện tại của container**, không hard-code port 5432 trên host.
8. Kiểm khả năng sống của JDBC connections bằng query thật và xác minh state đã commit/rollback.
9. Thiết kế cách ly dữ liệu khi nhiều classes cùng một broker/DB: unique IDs, per-schema/per-topic, targeted cleanup, fixtures độc lập.
10. Kiểm shutdown order và hiểu giới hạn giữa container stop, pool close, cache eviction và process-level cleanup.
11. Viết bài kiểm thử tối ưu tốc độ nhưng vẫn đủ độ tin cậy; dùng logs của Spring TestContext cache để đo hit/miss thay vì đoán.
12. Chạy project Maven **Java 17 / Spring Boot 3.5.16 / PostgreSQL Testcontainers / JDBC / JUnit 5** với hai test classes cùng cấu hình, Spring-managed container và các assertions chống data contamination.

**Phạm vi xác thực:** Những ví dụ code trong bài được kiểm tra về tính nhất quán API, imports và cấu trúc. Lệnh Maven cần chạy trong môi trường có Docker; không được coi một mã nguồn viết ra nhưng chưa chạy là bằng chứng test đã PASS.

## 2. Bốn thứ có thể bị nhầm là “dùng chung”

### 2.1. Docker container instance

Một `PostgreSQLContainer<?>` là Java object quản lý một Docker container. Nó có:
- Docker image;
- environment/credentials/databaseName;
- start/stop state;
- Docker container ID;
- network;
- exposed container port 5432;
- host và **mapped port động**.

Container có thể còn running trong khi một connection riêng lẻ đã chết. Ngược lại, Java object vẫn tồn tại dù Docker process đã stop. Đừng suy `static final PostgreSQLContainer` đồng nghĩa “running mãi”.

### 2.2. ApplicationContext

`ApplicationContext` giữ Spring bean definitions/instances như `DataSource`, `JdbcTemplate`, repository, producer, client factory, transaction manager. Spring TestContext Framework có thể cache và reuse context giữa các test classes có cấu hình giống nhau.

Một context được cache **không tự kiểm tra lại** mọi external port/container life cycle mỗi lần được reuse. Nếu nó được dựng khi PostgreSQL ở port X nhưng container đã stop/restart ra port Y, connection pool có thể tiếp tục gọi endpoint cũ.

### 2.3. Connection pool

HikariCP dùng pool quản lý JDBC connections. Một `DataSource` bean không phải một PostgreSQL connection. Pool có thể có 0–N physical connections, tạo lại hoặc validate khi borrow. Một container đã dừng có thể khiến:
- Existing connections hỏng.
- Connection creation thất bại.
- Pool chờ đến connection timeout.
- Client bean fail trong destruction callback.
- Test đầu vẫn qua nhờ cached data, test sau mới truy cập DB rồi fail.

Giải pháp không phải chỉ tăng `connectionTimeout`, mà là đảm bảo **backend live và endpoint đúng trong suốt lifetime của pool**.

### 2.4. Database/schema/test data

Nếu hai test classes cùng PostgreSQL container:
- Chúng có thể cùng database và cùng tables.
- Dữ liệu được commit ở class A vẫn còn cho class B.
- Spring context cache **không** reset DB giữa test methods.
- `@DirtiesContext` đóng context, **không có nghĩa tự xóa schema hoặc mọi external state**.
- Lệnh `DELETE FROM table` toàn bảng ở test A có thể xóa data của test B nếu chạy song song.

Container dùng chung chỉ là **infrastructure sharing**; **data isolation** vẫn là bài toán riêng.

## 3. Lifecycle trên một sơ đồ

### 3.1. Sai: mỗi test class được JUnit quản lý container, context lại được Spring cache

~~~text
JVM test suite
  |
  +-- TestClassA (JUnit extension)
  |      |
  |      +-- start PostgreSQL container #1 (hostPort=49153)
  |      +-- create Spring ApplicationContext K
  |      |      DataSource -> jdbc:postgresql://localhost:49153/test
  |      |
  |      +-- tests PASS
  |      +-- JUnit stops container #1 after class
  |              |
  |              +-- Spring context K vẫn trong cache
  |
  +-- TestClassB (cùng Spring cache key K)
         |
         +-- có thể restart container / dùng instance khác
         |          mapped hostPort có thể thay đổi
         +-- Spring reuses cached context K
         +-- DataSource vẫn trỏ endpoint đã hết lifetime
         +-- query -> connection refused / stale pool
~~~

Đây là tình huống được **Spring Boot 3.5** cảnh báo trong mục Testcontainers. `static @Container` có nghĩa là **per-class** với JUnit extension, không phải “mỗi JVM chỉ start một lần”. Nếu các lớp kế thừa cùng base test có static field và extension, JUnit có thể stop container sau subclass trước khi subclass kế tiếp sử dụng context cache.

### 3.2. Đúng với Spring-managed container bean

~~~text
Spring TestContext cache: ApplicationContext K
  |
  +-- Spring creates PostgreSQLContainer bean
  +-- Spring Boot starts PostgreSQL before dependent beans
  +-- @ServiceConnection -> JdbcConnectionDetails
  +-- DataSource/Hikari/JdbcTemplate initialized
  |
  +-- TestClassA uses context K, queries DB
  +-- TestClassA ends
  |
  +-- TestClassB uses same context K, queries same running DB
  |
  +-- context K closed by @DirtiesContext/LRU/JVM shutdown
         |
         +-- application beans / connection pools destroyed
         +-- PostgreSQL container stopped afterward
~~~

**Quan trọng:** Mô hình này thường start **một container trên mỗi ApplicationContext**. Nếu hai test classes tạo cache keys khác nhau, Spring có thể tạo hai contexts và hai container beans. Đây là lý do phải quản lý cache keys, không chỉ thêm `@ServiceConnection`.

### 3.3. Một lựa chọn khác: singleton container dài hơn contexts

~~~text
JVM
  |
  +-- static initializer: postgres.start() exactly once
  |                    |
  |                    +-- container sống cho suite/JVM
  |
  +-- ApplicationContext A -> dynamic JDBC URL của singleton
  +-- ApplicationContext B -> same backend, khác bean configs nếu cần
  +-- Context A/B close
  |
  +-- JVM exits / Testcontainers cleanup
          -> container stop (tùy môi trường/cleanup)
~~~

Mô hình này giảm số container restarts khi có nhiều contexts, nhưng đòi **quy tắc ownership/cleanup** riêng, không cho test methods tùy tiện stop shared container hoặc xóa data của test khác.

## 4. Spring TestContext cache: định nghĩa đúng cache key

### 4.1. Context cache theo cấu hình, không theo tên class

Spring Framework TestContext Framework lưu `ApplicationContext` trong **static cache** cùng JVM. Context được reuse khi hai tests có “unique context configuration” tương đương. Những thành phần chính của key bao gồm:

- `@ContextConfiguration` locations/classes/initializers/loader.
- Context hierarchy/parent.
- `@ActiveProfiles`.
- `@TestPropertySource` properties/descriptors.
- `contextCustomizers`, bao gồm `@DynamicPropertySource` methods, Spring test bean overrides như `@MockitoBean`/`@MockitoSpyBean` và các customizers của Spring Boot.
- Web resource base path và related test configuration attributes.

**Tên class không phải cache key duy nhất.** Hai classes khác nhau với cùng config có thể reuse context. Ngược lại, hai classes trông giống nhau nhưng khác profile, properties, mock bean definitions hoặc customizers có thể dùng hai contexts.

### 4.2. Tại sao nhiều context làm test chậm?

Khởi tạo Spring context có thể kéo theo:
- Bean scanning và dependency injection.
- Hikari connection pool.
- ORM/JPA EntityManagerFactory.
- Kafka/Rabbit listeners.
- Security filter chain.
- Auto-configuration.
- SQL migrations/initialization.
- Testcontainers image/container startup.
- HTTP client pool/observability exporters.

Nếu tạo một context cho **mỗi test class** bằng cách vô tình khác cache key, chi phí startup lặp lại. Nếu container bean thuộc context, container cũng có thể start lại.

### 4.3. Cache là per-JVM

Cache Spring TestContext là static trong **JVM process**. Nếu Maven Surefire/Gradle chạy mỗi class trong một forked JVM, contexts **không** share được qua processes. Đây là hành vi đúng, không phải lỗi cache.

Ví dụ khác nhau:
- Cùng JVM, same key: kỳ vọng reuse.
- Fork riêng, same source annotations: không reuse.
- IDE chạy một class độc lập: startup mới.
- Test class chạy trong suite đã có context: có thể reuse.
- JVM shutdown: contexts đóng, containers thuộc context dừng.

Không khẳng định “container start đúng 1 lần cho cả CI” nếu build dùng nhiều forks/machines.

### 4.4. LRU và giới hạn context cache

Theo Spring Framework 6.2, default cache maximum size là **32** contexts; khi vượt, LRU eviction sẽ close một context cũ. Có thể cấu hình JVM system property:

~~~bash
mvn test -Dspring.test.context.cache.maxSize=16
~~~

Điều này **giảm số context giữ đồng thời**, không nhất thiết tăng tốc. Cache quá nhỏ có thể gây thrashing: context vừa bị close lại phải build lại; nếu context sở hữu container, container cũng stop/start lại. Đo stats thay vì tùy tiện đổi từ 32 xuống 1.

### 4.5. Bật logs để nhìn cache hits/misses

Spring Framework có logger:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Hoặc dùng JVM logging configuration phù hợp với build. Log sẽ cung cấp thông tin về size/hits/misses/cache behavior. Khi phân tích:
- Xem số lần context thực sự load, không chỉ số test methods.
- Xem class nào làm xuất hiện cache key mới.
- Xem có `@DirtiesContext` hoặc eviction không.
- Phân biệt load một context mới với restart riêng Docker container.
- Đọc Maven Surefire reports để biết tests nào thực sự executed.

Cảnh báo: log cache có thể nhiều; chỉ bật khi phân tích hiệu năng/test topology và không dùng exact log line như application contract.

### 4.6. @DirtiesContext: khi nào nên dùng?

`@DirtiesContext` đánh dấu current context không còn dùng lại được, khiến Spring TestContext evict/close context theo mode. Hữu ích nếu:
- Test thay đổi singleton bean state mà không thể reset an toàn.
- Test sửa environment hoặc internal context infrastructure.
- Có một loại container/client context bắt buộc isolate theo class.

Nhưng dùng `@DirtiesContext` vô tội vạ trên mọi class:
- Phá cache reuse.
- Buộc bean/application startup lại.
- Với Spring-managed container, khiến container stop và tạo lại.
- Làm suite chậm hơn.
- Không tự dọn toàn bộ external state nếu container là process-level singleton hoặc resource ngoài Spring.

**Không dùng `@DirtiesContext` như “DB cleanup” thay cho fixtures/transactions/targeted data deletion.**

## 5. Ba chiến lược container ownership hợp lệ

| Chiến lược | Container owner | Lifetime | Cache context phù hợp? | Khi nên chọn |
| --- | --- | --- | --- | --- |
| `@Testcontainers + @Container static` | JUnit Testcontainers extension | Test class | Phải cẩn thận nếu context sống qua class | Một class độc lập hoặc context được isolate rõ |
| `@Bean + @ServiceConnection` trong `@TestConfiguration` | Spring Boot ApplicationContext | Context lifetime, gồm cached reuse | **Ưu tiên cho Boot 3.5** | Nhiều Spring tests dùng cùng context |
| `@ImportTestcontainers` | Spring Boot test infrastructure cho declarations import | Context-aware | Có, theo docs Boot | Tái sử dụng definitions Testcontainers trong test config |
| Singleton static initializer + `@DynamicPropertySource` | Test suite/JVM; thủ công | JVM/test run | Có nếu container luôn sống | Nhiều contexts cùng backend, cần kiểm ownership |
| Reusable container opt-in (`withReuse(true)`) | Developer/Testcontainers environment | Có thể vượt một run local | Không thay context lifecycle | Tối ưu local có rủi ro isolation |
| External sandbox DB/service | Hệ thống ngoài suite | Do môi trường quản lý | Chỉ khi endpoints ổn định | E2E/contract environment có cleanup rules |

**Chọn ownership trước khi viết annotations.** Không trộn mô hình “JUnit stop class” với kỳ vọng “Spring cached context còn sống tới cuối suite”.

### 5.1. Mẫu khuyến nghị của bài

Với Boot 3.5:
- Đặt container trong `@TestConfiguration` bằng `@Bean`.
- Thêm `@ServiceConnection` nếu container typed/recognized.
- Import **cùng test configuration class** trong nhiều tests có cùng app config.
- Không thêm `@Testcontainers`/`@Container` vào bean này.
- Không gọi `container.start()` hoặc `container.stop()` thủ công trong tests thông thường.
- Giữ tests ở cùng profiles/overrides khi muốn cache hit.
- Cleanup dữ liệu bằng ID riêng, không delete toàn DB trừ khi môi trường đã isolate.

### 5.2. JUnit extension vẫn có giá trị

`@Testcontainers` + `@Container` rất tốt cho:
- Plain JUnit tests không khởi tạo Spring context.
- One-off integration class với context không cần sống tiếp.
- Tests cần instance container riêng cho từng test method, chấp nhận startup cost.
- Scenarios kiểm startup failure/teardown theo lifecycle của JUnit.

Vấn đề chỉ xảy ra khi **container lifetime và dependent Spring beans lifetime không khớp**. Không phải mọi `@Container` đều là anti-pattern.

### 5.3. Vòng đời container Spring bean

Theo Spring Boot 3.5 docs:
- Container beans được tạo/start trước các beans phụ thuộc.
- Spring-managed client beans bị destroy trước khi container stop.
- Container start **một lần trên mỗi context** nếu context không bị rebuild.
- Khi context đóng theo Spring TestContext, container được stop.
- Cùng một container instance có thể phục vụ nhiều test classes chia sẻ cached context.

Điều này tránh một dạng stale-connection bug và shutdown race phổ biến, nhưng **không bảo đảm mọi DB transaction/cleanup đúng**. Context lifecycle khác với dữ liệu test.

## 6. @ServiceConnection và @DynamicPropertySource

### 6.1. @ServiceConnection: connection details có precedence

Spring Boot `spring-boot-testcontainers` có các connection details factories. Với typed container `PostgreSQLContainer<?>`, `@ServiceConnection` có thể tạo `JdbcConnectionDetails` để Spring DataSource auto-configuration dùng container's JDBC URL, username và password.

Ví dụ:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class PostgresTestConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>(
                DockerImageName.parse("postgres:16-alpine"))
                .withDatabaseName("testdb");
    }
}
~~~

Dạng này **không** cần tự set:
- `spring.datasource.url`;
- `spring.datasource.username`;
- `spring.datasource.password`;
- `@DynamicPropertySource` cho JDBC.

Khi một service connection details bean được dùng, nó có precedence so với connection-related properties thông thường. Đừng đồng thời hard-code `localhost:5432` rồi suy rằng test đang dùng Docker mapped port đó.

### 6.2. Typed container và GenericContainer

Với typed PostgreSQLContainer, Boot biết loại service. Với `GenericContainer<?>`, Spring Boot không luôn suy được service type chỉ từ `@Bean` method vì không instantiate bean sớm để xem Docker image. Khi cần:

~~~java
@Bean
@ServiceConnection(name = "redis")
GenericContainer<?> redisContainer() {
    return new GenericContainer<>(
            DockerImageName.parse("redis:7-alpine"))
            .withExposedPorts(6379);
}
~~~

Đoạn minh họa cho Redis này cần imports và có thể cần dependency tương ứng. Thuộc tính `name="redis"` cho Boot hint tạo `RedisConnectionDetails`; không được copy `name="postgres"` vào container khác để hack type. ServiceConnection factories cũng phụ thuộc classpath của client/service mà app dùng.

### 6.3. DynamicPropertySource khi không có ServiceConnection

Nếu dùng một singleton container ngoài Spring context:

~~~java
@DynamicPropertySource
static void databaseProperties(
        DynamicPropertyRegistry registry) {
    registry.add(
            "spring.datasource.url",
            POSTGRES::getJdbcUrl);
    registry.add(
            "spring.datasource.username",
            POSTGRES::getUsername);
    registry.add(
            "spring.datasource.password",
            POSTGRES::getPassword);
}
~~~

Đây là method `static` của test/base class với parameter `DynamicPropertyRegistry`. Dynamic properties có precedence cao hơn nhiều source thường gặp; giá trị được cung cấp qua lazy `Supplier`.

**Cảnh báo:** Một supplier tham chiếu container có thể trả URL **mới** sau restart, nhưng `DataSource` của cached context không tự khởi tạo lại để dùng URL mới. Một bean đã được initialize với URL cũ không tự “đọc lại” mọi property khi container đổi mapped port. Hãy giữ external resource live trong lifetime context hoặc đóng/rebuild context đúng cách.

### 6.4. DynamicPropertySource ở base class và subclasses

Nếu một base test class khai báo `@DynamicPropertySource` nhưng mỗi subclass có **một backend instance/port khác nhau**, Spring có thể thấy cache key giống nhau do method identity được kế thừa. Tài liệu Spring Framework cảnh báo rằng có thể phải dùng `@DirtiesContext` để mỗi subclass có context đúng dynamic values.

Tốt hơn khi có thể:
- Dùng cùng container/same port theo base class trong toàn suite.
- Hoặc dùng Spring-managed container bean theo context.
- Nếu cần backend riêng mỗi class, tạo cache-key separation có chủ đích và lifecycle phù hợp.
- Không mutate static `POSTGRES` reference giữa subclasses trong khi context còn cache.

### 6.5. Không đưa connection strings cố định vào fixtures

Đừng copy mapped Docker port từ một lần chạy:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:49153/testdb
~~~

Port 49153 là ví dụ, có thể đổi ở lần chạy tiếp theo. Test dùng `getJdbcUrl()` hoặc `JdbcConnectionDetails` để nhận endpoint hiện tại. Cũng không mặc định host luôn là `localhost` nếu Docker chạy remote/CI containerized; Testcontainers sẽ cung cấp host theo environment.

## 7. Dự án runnable: Spring-managed PostgreSQL dùng chung nhờ context cache

### 7.1. Mục tiêu và phạm vi

Project Maven Java 17 + Spring Boot 3.5.16:
- Một test-only `PostgreSQLContainer<?>` bean với `@Bean @ServiceConnection`.
- Hai `@SpringBootTest` classes có **cùng configuration** và `@ActiveProfiles("integration")`.
- Spring JDBC repository làm việc với PostgreSQL thật qua Hikari.
- Một `NoteService` có transaction boundary rõ.
- Schema tự khởi tạo bằng `schema.sql` trong integration context.
- Mỗi test method dùng note ID duy nhất và targeted cleanup.
- Test xác nhận container running, datasource sử dụng JDBC URL từ service connection, SQL `SELECT 1` hoạt động và database persistence/rollback.
- Không dùng `@Testcontainers`/`@Container` vì container được **Spring** quản lý.
- Không gắn `@DirtiesContext` để context có thể được tái sử dụng giữa test classes.

**Điều được chứng minh:** Khi chạy suite trong một JVM có cùng Spring test configuration, một context còn cache sẽ giữ container bean và DataSource sống đồng bộ, vì vậy class B không gặp lỗi kiểu “JUnit đã stop container của class A”. Test code không giả vờ chứng minh cache hit chỉ từ việc hai classes dùng cùng annotations: logs/cache metrics mới là cách xác nhận context có thực sự reuse trong build runner.

### 7.2. Cây thư mục

~~~text
cached-context-postgres-lab/
├── pom.xml
├── src/main/
│   ├── java/com/example/contextlab/
│   │   ├── CachedContextApplication.java
│   │   ├── NoteRecord.java
│   │   ├── NoteRepository.java
│   │   └── NoteService.java
│   └── resources/
│       ├── application.properties
│       └── schema.sql
└── src/test/
    ├── java/com/example/contextlab/
    │   ├── SharedPostgresTestConfig.java
    │   ├── SharedDatabaseAlphaTest.java
    │   └── SharedDatabaseBetaTest.java
    └── resources/
        └── application-integration.properties
~~~

Chú ý:
- Test config nằm trong `src/test/java`, không bị đóng gói vào production artifact.
- Không có Docker config trong `src/main`.
- Container image được kéo qua Docker runtime khi tests chạy.
- Class B có thể được JUnit chạy trước A; tests không phụ thuộc thứ tự test classes.

### 7.3. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>cached-context-postgres-lab</artifactId>
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
      <groupId>org.postgresql</groupId>
      <artifactId>postgresql</artifactId>
      <scope>runtime</scope>
    </dependency>

    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>

    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-testcontainers</artifactId>
      <scope>test</scope>
    </dependency>

    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>postgresql</artifactId>
      <scope>test</scope>
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
~~~

Lưu ý:
- Spring Boot 3.5 BOM quản lý versions của Testcontainers 1.x modules, ví dụ `org.testcontainers:postgresql`. Nếu nâng sang Testcontainers 2.x, artifact coordinates/packages có thể thay; kiểm BOM/version compatibility trước khi copy.
- Không cần `org.testcontainers:junit-jupiter` để quản lý container **dưới dạng Spring bean**, vì không dùng JUnit Testcontainers extension.
- PostgreSQL JDBC driver có `runtime` scope vì production code compile với `DataSource`/`JdbcTemplate`, không import driver internals.
- Docker là prerequisite external, không được giả lập bởi Mockito trong lab.

### 7.4. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.application.name=cached-context-postgres-lab
spring.main.web-application-type=none

spring.sql.init.mode=always
spring.datasource.hikari.maximum-pool-size=4
spring.datasource.hikari.connection-timeout=20000
spring.datasource.hikari.validation-timeout=5000
~~~

**Không có** `spring.datasource.url` hoặc credentials hard-coded. Trong tests, Boot lấy connection details từ `@ServiceConnection`. Nếu chạy bare `mvn spring-boot:run` ngoài test, ứng dụng sẽ cần datasource configuration thật do môi trường cấp; sample chủ yếu dành cho integration test và không cấu hình kết nối production.

`spring.sql.init.mode=always` cho phép Boot chạy `schema.sql` cả trên PostgreSQL external; đây là lựa chọn lab. Trong production, dùng Flyway/Liquibase hoặc schema migration system phù hợp; đừng dùng `CREATE TABLE IF NOT EXISTS` để thay thế migrations đã version.

### 7.5. schema.sql

`src/main/resources/schema.sql`:

~~~sql
CREATE TABLE IF NOT EXISTS test_notes (
    note_id VARCHAR(100) PRIMARY KEY,
    owner_tag VARCHAR(100) NOT NULL,
    message_text VARCHAR(200) NOT NULL
);
~~~

Một schema nhỏ để test:
- Primary key `note_id` bảo vệ duplicate.
- `owner_tag` biểu diễn namespace của test.
- `message_text` là synthetic payload.
- `CREATE TABLE IF NOT EXISTS` cho phép context khởi tạo lại trên DB tồn tại mà không lỗi table already exists, nhưng **không đảm bảo schema migration đúng** khi table definition thay đổi.
- Schema trong shared container tồn tại tới khi container bị stop/destroy hoặc database được reset có chủ đích.

### 7.6. CachedContextApplication.java

`src/main/java/com/example/contextlab/CachedContextApplication.java`:

~~~java
package com.example.contextlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CachedContextApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                CachedContextApplication.class, args);
    }
}
~~~

Không có `@EnableScheduling` hay bootstrap service nào tự xóa DB. Điều này giữ tests deterministic và tránh background workers chạm dữ liệu giữa test methods.

### 7.7. NoteRecord.java

`src/main/java/com/example/contextlab/NoteRecord.java`:

~~~java
package com.example.contextlab;

public record NoteRecord(
        String id,
        String ownerTag,
        String message) {
}
~~~

Java 17 record dùng để map một row. Không có ORM/JPA first-level cache làm nhiễu đọc lại; mỗi query đi qua `JdbcTemplate` và PostgreSQL.

### 7.8. NoteRepository.java

`src/main/java/com/example/contextlab/NoteRepository.java`:

~~~java
package com.example.contextlab;

import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class NoteRepository {

    private final JdbcTemplate jdbc;

    public NoteRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int insert(
            String id,
            String ownerTag,
            String message) {

        return jdbc.update(
                "INSERT INTO test_notes "
                        + "(note_id, owner_tag, message_text) "
                        + "VALUES (?, ?, ?)",
                id, ownerTag, message);
    }

    public Optional<NoteRecord> findById(String id) {
        return jdbc.query(
                "SELECT note_id, owner_tag, message_text "
                        + "FROM test_notes WHERE note_id = ?",
                (rs, rowNum) -> new NoteRecord(
                        rs.getString("note_id"),
                        rs.getString("owner_tag"),
                        rs.getString("message_text")),
                id).stream().findFirst();
    }

    public long countById(String id) {
        Long value = jdbc.queryForObject(
                "SELECT COUNT(*) FROM test_notes "
                        + "WHERE note_id = ?",
                Long.class,
                id);
        return value == null ? 0L : value;
    }

    public int deleteById(String id) {
        return jdbc.update(
                "DELETE FROM test_notes WHERE note_id = ?",
                id);
    }
}
~~~

Đây là JDBC trên PostgreSQL thật. `JdbcTemplate` dùng DataSource/connection pool do Boot auto-configure, không tự mở connection bằng `DriverManager.getConnection("jdbc:postgresql://localhost:5432/...")`.

`findById` trả `Optional` để test phân biệt row đã commit với row không tồn tại. `deleteById` chỉ dọn **một ID do test sở hữu**, không làm ảnh hưởng test khác có ID riêng.

### 7.9. NoteService.java

`src/main/java/com/example/contextlab/NoteService.java`:

~~~java
package com.example.contextlab;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class NoteService {

    private final NoteRepository notes;

    public NoteService(NoteRepository notes) {
        this.notes = notes;
    }

    @Transactional
    public void addNote(
            String id,
            String owner,
            String message) {

        notes.insert(id, owner, message);
    }

    @Transactional
    public void insertThenFail(
            String id,
            String owner,
            String message) {

        notes.insert(id, owner, message);
        throw new IllegalStateException(
                "injected before commit");
    }
}
~~~

Dùng hai public methods trong Spring bean:
- `addNote` return bình thường → Spring transaction commit.
- `insertThenFail` throw unchecked exception trước commit → transaction rollback.

JUnit tests **không gắn `@Transactional` lên class/method**, nên service transaction thực sự commit hoặc rollback và assertions đọc trạng thái **sau khi method kết thúc**. Nếu test method có outer test-managed transaction, kết quả có thể đánh lừa vì tất cả operations cùng thuộc transaction của test.

### 7.10. SharedPostgresTestConfig.java

`src/test/java/com/example/contextlab/SharedPostgresTestConfig.java`:

~~~java
package com.example.contextlab;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;

import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;

@TestConfiguration(proxyBeanMethods = false)
public class SharedPostgresTestConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>(
                DockerImageName.parse("postgres:16-alpine"))
                .withDatabaseName("labdb")
                .withUsername("lab_user")
                .withPassword("lab_password");
    }
}
~~~

Điều quan trọng:
1. `@TestConfiguration` chỉ thuộc test source set.
2. `@Bean` tạo container như Spring bean, không phải JUnit field.
3. `@ServiceConnection` (từ `spring-boot-testcontainers`) sinh connection details cho JDBC auto-config.
4. Không gọi `start()` trong bean factory method; Boot quản lý start/stop.
5. Không gọi `stop()` trong `@AfterEach`/`@AfterAll` của test classes.
6. Một cached `ApplicationContext` chứa một container bean và DataSource tương ứng.
7. Khi context close, Spring/Boot dừng container đúng lifecycle; connection pool/client beans được destroy trước backend.

Credential ở đây là **test-only synthetic** không phải secret. Không copy trực tiếp vào production config; production dùng secret management theo environment.

### 7.11. application-integration.properties

`src/test/resources/application-integration.properties`:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
logging.level.org.testcontainers=INFO
~~~

Hai test classes dùng `@ActiveProfiles("integration")` để load file này. Khi chạy suite:
- Spring TestContext cache DEBUG logs giúp phân tích hits/misses.
- Testcontainers INFO hiển thị container startup/endpoints.
- Không nên assert exact log line vì format/stats thay theo version/order.
- Nếu console output quá lớn, tắt DEBUG sau khi đã xác nhận cache topology.

### 7.12. SharedDatabaseAlphaTest.java

`src/test/java/com/example/contextlab/SharedDatabaseAlphaTest.java`:

~~~java
package com.example.contextlab;

import java.sql.Connection;
import java.util.UUID;

import javax.sql.DataSource;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.jdbc.JdbcConnectionDetails;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import org.testcontainers.containers.PostgreSQLContainer;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("integration")
@Import(SharedPostgresTestConfig.class)
class SharedDatabaseAlphaTest {

    @Autowired
    PostgreSQLContainer<?> postgres;

    @Autowired
    DataSource dataSource;

    @Autowired
    JdbcConnectionDetails details;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    NoteRepository repository;

    @Autowired
    NoteService service;

    private String noteId;

    @BeforeEach
    void prepareUniqueId() {
        noteId = "alpha_" + UUID.randomUUID()
                .toString().replace("-", "");
    }

    @AfterEach
    void cleanOnlyOwnedData() {
        repository.deleteById(noteId);
    }

    @Test
    void postgresBeanAndLiveJdbcConnectionAgree()
            throws Exception {

        assertThat(postgres.isRunning()).isTrue();

        assertThat(details.getJdbcUrl())
                .isEqualTo(postgres.getJdbcUrl());

        try (Connection connection =
                     dataSource.getConnection()) {

            assertThat(connection.isValid(2)).isTrue();

            assertThat(
                    connection.getMetaData().getURL())
                    .contains(
                            ":" + postgres.getMappedPort(5432)
                                    + "/");
        }

        Integer one = jdbc.queryForObject(
                "SELECT 1",
                Integer.class);

        assertThat(one).isEqualTo(1);
    }

    @Test
    void serviceWriteIsCommittedAndReadableLater() {

        service.addNote(
                noteId,
                "alpha",
                "hello from first test class");

        assertThat(repository.countById(noteId))
                .isEqualTo(1L);

        assertThat(repository.findById(noteId))
                .hasValueSatisfying(note -> {
                    assertThat(note.id()).isEqualTo(noteId);
                    assertThat(note.ownerTag())
                            .isEqualTo("alpha");
                    assertThat(note.message())
                            .isEqualTo(
                                    "hello from first test class");
                });
    }
}
~~~

**Test 1**:
- Container đang running tại lúc query.
- `JdbcConnectionDetails` lấy từ typed `PostgreSQLContainer`, URL đúng.
- Physical JDBC connection có thể `isValid(2)`.
- Metadata URL chứa mapped port động thay vì một fixed host port.
- `SELECT 1` đi qua PostgreSQL thật.

**Test 2**:
- Transaction của `NoteService` commit.
- Repository query sau method thấy row.
- Test dùng ID riêng; không phụ thuộc data của class B.
- `@AfterEach` dọn đúng ID.

Chúng **không** khẳng định cache hit hay “chỉ một container toàn JVM” chỉ bằng assertions `isRunning()`. Cache reuse phải được quan sát ở suite execution/logs; tính đúng đắn của connection được kiểm trực tiếp.

### 7.13. SharedDatabaseBetaTest.java

`src/test/java/com/example/contextlab/SharedDatabaseBetaTest.java`:

~~~java
package com.example.contextlab;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.context.ActiveProfiles;

import org.testcontainers.containers.PostgreSQLContainer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
@ActiveProfiles("integration")
@Import(SharedPostgresTestConfig.class)
class SharedDatabaseBetaTest {

    @Autowired
    PostgreSQLContainer<?> postgres;

    @Autowired
    NoteRepository repository;

    @Autowired
    NoteService service;

    private String noteId;

    @BeforeEach
    void uniqueFixture() {
        noteId = "beta_" + UUID.randomUUID()
                .toString().replace("-", "");
    }

    @AfterEach
    void cleanupOwnedRow() {
        repository.deleteById(noteId);
    }

    @Test
    void secondTestClassCanUseLiveSharedInfrastructure() {
        assertThat(postgres.isRunning()).isTrue();

        service.addNote(
                noteId,
                "beta",
                "created by second test class");

        assertThat(repository.findById(noteId))
                .hasValueSatisfying(note -> {
                    assertThat(note.ownerTag())
                            .isEqualTo("beta");
                    assertThat(note.message())
                            .isEqualTo(
                                    "created by second test class");
                });
    }

    @Test
    void failedServiceTransactionRollsBack() {

        assertThatThrownBy(() ->
                service.insertThenFail(
                        noteId,
                        "beta",
                        "should roll back"))
                .isInstanceOf(
                        IllegalStateException.class)
                .hasMessageContaining(
                        "injected before commit");

        assertThat(repository.countById(noteId))
                .isZero();
    }

    @Test
    void duplicateKeyIsRejectedByPostgres() {

        repository.insert(
                noteId,
                "beta",
                "original");

        assertThatThrownBy(() ->
                repository.insert(
                        noteId,
                        "beta",
                        "duplicate"))
                .isInstanceOf(
                        DataIntegrityViolationException.class);

        assertThat(repository.countById(noteId))
                .isEqualTo(1L);

        assertThat(repository.findById(noteId))
                .hasValueSatisfying(note ->
                        assertThat(note.message())
                                .isEqualTo("original"));
    }
}
~~~

**Test 1**: Class B dùng đúng test configuration như A, có connection live và business SQL chạy được. Không phụ thuộc A chạy trước. Trong same JVM, same context cache key, Spring có thể reuse context/container.

**Test 2**: Transaction throw trước commit phải rollback, kiểm bằng query thật sau method. Không có test-level transaction che đi actual behavior.

**Test 3**: PostgreSQL primary key ngăn duplicate data ở database layer. Câu INSERT đầu thành công; INSERT thứ hai bị integrity constraint reject; row gốc không bị overwrite. Không dựa vào H2 fake cho database uniqueness semantics.

**Isolation:** Mỗi method có ID per-test từ UUID; cleanup chỉ note ID của test. Điều này an toàn hơn reset toàn bảng khi suite chạy nhiều classes hoặc parallel workers cùng container. Nếu một test bất ngờ crash trước cleanup, stale row có ID riêng sẽ không trùng với ID của lần chạy khác; vẫn cần môi trường cleanup/TTL cho broker/DB dùng lâu dài.

### 7.14. Lệnh chạy Maven

Từ thư mục `cached-context-postgres-lab`, có JDK 17+, Maven, Docker daemon có thể chạy image `postgres:16-alpine`:

~~~bash
mvn -q clean test

mvn -q -Dtest=SharedDatabaseAlphaTest test
mvn -q -Dtest=SharedDatabaseBetaTest test

mvn -q -Dtest=SharedDatabaseAlphaTest,SharedDatabaseBetaTest test
~~~

Kỳ vọng:
- **5 JUnit test methods** qua hai classes.
- Docker/Testcontainers tạo PostgreSQL khi first matching `ApplicationContext` được load.
- Cả hai classes có cùng annotations/profile/`@Import` nên trong một JVM/cache chưa bị evict, context có thể reuse.
- Postgres bean không bị JUnit extension stop sau class A.
- Database SQL và transaction assertions PASS nếu môi trường phù hợp.
- Surefire reports tại `target/surefire-reports` cho biết số methods chạy/failed/skipped.

**Không đoán chính xác số container starts từ tên test command**: Maven forks, context cache evictions, IDE test engine hoặc cấu hình bean overrides khác nhau có thể thay behavior. Để xác nhận sharing, xem DEBUG stats của `org.springframework.test.context.cache` và Testcontainers start logs. Chạy từng test class bằng **lệnh Maven riêng** thường tạo JVM riêng; không phải thí nghiệm “shared context across two classes”.

**Chưa có kết quả chạy thật trong tài liệu:** Mã được review để có thể dùng như project runnable, nhưng không tuyên bố `Tests run: 5, Failures: 0` đã được quan sát khi chưa chạy Maven/Docker.

## 8. Anti-pattern: static @Container trong base class nhưng context reuse

### 8.1. Mẫu dễ gây lỗi

~~~java
@SpringBootTest
@Testcontainers
abstract class BrokenPostgresBaseTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url",
                POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username",
                POSTGRES::getUsername);
        registry.add("spring.datasource.password",
                POSTGRES::getPassword);
    }
}

class IntegrationATest extends BrokenPostgresBaseTest {
    @Test
    void testA() { }
}

class IntegrationBTest extends BrokenPostgresBaseTest {
    @Test
    void testB() { }
}
~~~

**Đây là anti-pattern snippet, không thuộc runnable project.** Imports JUnit/Testcontainers/Spring được lược để nhấn mạnh lỗi ownership.

Vì `@Testcontainers` JUnit extension quản lý `static @Container` theo **test class**, container có thể stop sau một subclass. Context từ class A vẫn cache nếu key tương đương. Đến class B, JUnit có thể start lại container nhưng mapped port có thể khác; context và pool vẫn trỏ URL cũ.

### 8.2. Tại sao chỉ thêm static không cứu được?

`static` giữ cùng Java object trong classloader. Nó **không thay đổi quyết định stop lifecycle của JUnit extension**. Container Java object có thể bị stop rồi restart với Docker container ID/port mới. Spring cached context thường không tự cấu hình lại DataSource theo mapping mới.

### 8.3. Tại sao tăng connection timeout không sửa được?

Nếu DataSource trỏ port đã đóng, tăng timeout từ 30s lên 120s chỉ khiến suite chờ lâu hơn. Phải:
- Giữ container sống đến khi context đóng;
- Hoặc rebuild context và clients khi backend đổi;
- Hoặc dùng singleton process-level resource không bị JUnit extension stop giữa classes.

### 8.4. @DirtiesContext có phải fix?

Nếu bạn buộc tách context theo class, `@DirtiesContext(classMode=AFTER_CLASS)` có thể tránh reuse context đã phụ thuộc container stop, nhưng:
- Chi phí startup tăng.
- Shutdown order giữa JUnit container và client beans vẫn cần kiểm.
- Không tự giải quyết DB cleanup.
- Không phải giải pháp tối ưu khi muốn **chia sẻ container/context để tăng tốc**.

Spring Boot 3.5 chính thức ưu tiên container beans hoặc `@ImportTestcontainers` khi cần context usable trong suốt cached lifetime.

## 9. Singleton container pattern: dùng chung qua nhiều contexts

### 9.1. Khi nào có ý nghĩa?

Có suite 60 test classes, tạo nhiều `ApplicationContext` vì profiles/security/test overrides khác nhau; mỗi context-managed bean có thể start một PostgreSQL container riêng. Nếu số containers quá tốn tài nguyên, một **singleton container của JVM** có thể làm backend chung cho các contexts mà không phụ thuộc context lifetime.

Nhưng container phải được start **ngoài JUnit extension** và giữ sống cho tới khi mọi contexts dùng nó xong. Một base class static initializer là pattern đã được Testcontainers/Docker docs minh họa.

### 9.2. Abstract base với static initializer

~~~java
public abstract class SharedPostgresBase {

    protected static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine");

    static {
        POSTGRES.start();
    }

    @DynamicPropertySource
    static void configureDatabase(
            DynamicPropertyRegistry registry) {

        registry.add(
                "spring.datasource.url",
                POSTGRES::getJdbcUrl);
        registry.add(
                "spring.datasource.username",
                POSTGRES::getUsername);
        registry.add(
                "spring.datasource.password",
                POSTGRES::getPassword);
    }
}
~~~

Đây là một **pattern minh họa**, không nằm trong Maven lab chính. Nó cần imports tương ứng và test class kế thừa base cùng `@SpringBootTest`/configuration. **Không** đặt `@Testcontainers` lên base và **không** gắn `@Container` lên `POSTGRES`, vì extension có thể stop resource per-class. Cũng không gọi `POSTGRES.stop()` ở `@AfterAll` của từng subclass.

### 9.3. Cleanup và giới hạn

- Testcontainers core thường dùng resource reaper/Ryuk và JVM cleanup; đừng coi đó là durable data retention policy.
- Khi JVM bị kill mạnh, cleanup có thể bị ảnh hưởng bởi Docker/CI setup; cần có post-job cleanup/quota.
- Một JVM khác sẽ start singleton riêng, không chia sẻ same Java static.
- Test runs khác có thể có images/containers khác; không chia sẻ bằng hostname mặc định.
- Một singleton backend **không tự cô lập dữ liệu**; migrations/schema/caches, topics, queues phải tách namespace.
- Nếu một test cố stop singleton, các contexts còn lại sẽ fail.
- Cùng broker có thể dùng cho nhiều contexts nhưng client beans/connection pools phải được close trước khi backend stop.

### 9.4. Reusable container không phải singleton pattern

Testcontainers có experimental reusable containers cho local development thông qua opt-in. Nó có thể giữ container chạy qua nhiều test runs. Nhưng:
- Không dành cho CI sạch có yêu cầu reproducibility.
- Có nguy cơ dữ liệu/schema tồn dư giữa runs.
- Không khắc phục context cache key fragmentation.
- Không thay thế service connection/host-port management.
- Không cho test tùy tiện cleanup shared instance của người khác.

Bài học này **không** bật `withReuse(true)` trong lab để tránh trạng thái khó lặp.

## 10. @ImportTestcontainers: một lựa chọn chính thức khác

Spring Boot 3.5 hỗ trợ `@ImportTestcontainers` để import container declarations từ classes/interfaces có `@Container` fields vào Spring test configuration, giúp Boot quản lý lifecycle phù hợp với context.

Ví dụ:

~~~java
public interface InfrastructureContainers {

    @Container
    PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine");
}

@TestConfiguration(proxyBeanMethods = false)
@ImportTestcontainers(InfrastructureContainers.class)
class InfrastructureConfig {
}
~~~

Đây là **snippet tùy chọn**, không nằm trong runnable Maven lab; cần imports:
- `org.testcontainers.junit.jupiter.Container`;
- `org.testcontainers.containers.PostgreSQLContainer`;
- `org.springframework.boot.testcontainers.context.ImportTestcontainers`;
- `org.springframework.boot.test.context.TestConfiguration`.

Nếu dùng `@ImportTestcontainers` để quản lý lifecycle, không tự đưa cùng object vào một `@Testcontainers` lifecycle khác ở test classes rồi stop nó bằng JUnit extension. Nếu cần service connections tự động, xem cách annotation `@ServiceConnection` áp trên imported declarations hoặc cấu hình connection details cho container type theo Boot docs.

### 10.1. Khi nào chọn @ImportTestcontainers?

- Đã có class/interface khai báo nhiều containers bằng fields.
- Muốn chia sẻ declarations ở test configuration.
- Muốn giữ container lifetime aligned với context caching.
- Không muốn viết lại mọi declaration thành `@Bean` methods.

### 10.2. Khi nào @Bean dễ hiểu hơn?

- Một hoặc ít containers.
- Muốn Spring DI/autowire typed container.
- Muốn ownership thể hiện rõ trong `@TestConfiguration`.
- Muốn dùng `@ServiceConnection` trên bean method.
- Muốn đảm bảo test readers không nhầm với JUnit per-class extension lifecycle.

Trong lab, `@Bean @ServiceConnection` được chọn vì đơn giản và diễn đạt chính xác ranh giới.

## 11. Cache key fragmentation và chi phí test suite

### 11.1. Dùng @MockitoBean ở mọi test class

Nếu mỗi test class khai báo các `@MockitoBean` khác nhau, Spring Framework TestContext customizers có thể khác, sinh context mới. Một repository mock dùng ở class A và service mock ở class B không tự nhiên share context chỉ vì cả hai có `@SpringBootTest`.

Giải pháp: nhóm những tests có cùng dependency overrides, hoặc giảm số full-context tests bằng unit/slice tests; không ép một context chứa mọi mock để tăng cache hit nếu tests cần behavior khác nhau.

### 11.2. @TestPropertySource thay đổi thường xuyên

~~~java
@SpringBootTest(properties = {
    "feature.enabled=true",
    "test.unique.port=50001"
})
~~~

và class khác `test.unique.port=50002` có context key khác nhau. Nếu mỗi class gắn random property để “cô lập” dữ liệu thì cache bị vô hiệu. Tạo **unique test data IDs** trong method thay vì random Spring properties khi không cần thay bean config.

### 11.3. @ActiveProfiles là một phần key

`@ActiveProfiles("integration")` và `@ActiveProfiles({"integration", "debug"})` không đồng nhất. Profile khác có thể nạp beans khác và cần context khác. Không bỏ profile chỉ để ép cache hit nếu security/behavior thực sự thay đổi.

### 11.4. @DynamicPropertySource method identity

Context customizers chứa `@DynamicPropertySource` methods. Hai tests với identical property names nhưng methods khác hoặc inherited methods dynamic values khác nhau có thể ảnh hưởng cache key/behavior. Giữ một common base/config nếu muốn share resource; khi dynamic values khác thực sự cần context riêng, isolate có chủ đích.

### 11.5. Web environment và context types

`@SpringBootTest(webEnvironment=MOCK)` khác với `RANDOM_PORT`, có thể nạp web server và properties khác. Context có thể khác key/behavior. Không ép controller HTTP integration và pure JDBC integration test vào cùng một web context khi một test không cần server.

### 11.6. LRU eviction khi contexts quá nhiều

Nếu mỗi class có unique config, default 32-entry cache có thể churn. Với container-as-bean, eviction đóng context và stop container. Nếu suite dùng hai lại hàng trăm contexts cùng một DB type, có thể cần:
- Refactor test configuration.
- Chọn singleton containers ngoài context có ownership rõ.
- Group suites/batch by infrastructure.
- Điều chỉnh fork count/cache size có đo lường.
- Ưu tiên slice/unit tests cho phần không cần broker thật.

Đừng tăng cache max tùy ý lên 1000: memory và Docker resources có thể tăng nhanh, nhất là mỗi context sở hữu container riêng.

## 12. Context cache không phải data isolation

### 12.1. Rủi ro khi nhiều classes cùng database

Nếu class A chạy:

~~~sql
DELETE FROM test_notes;
~~~

trong khi B đang ghi data, A có thể xóa records của B. Dùng `@Sql` cleanup toàn bảng không an toàn khi tests parallel trên shared database.

Một shared container có thể giữ:
- Business rows.
- Flyway schema history.
- Sequences/autoincrement counters.
- PostgreSQL advisory locks/long-running sessions.
- Test-created users/roles/schema.
- Event outbox records.
- Materialized views/caches.

Cache context chỉ quản lý Spring beans, không reset mọi state đó.

### 12.2. Cách ly qua unique business IDs

Trong project lab:
- Mỗi test method tạo ID mới bằng UUID.
- Có prefix theo class để debug.
- Sau test, chỉ delete row mang đúng ID.
- Không đọc count toàn table mà kết luận đó là count của test.
- Assertions dùng `WHERE note_id = ?`.

Cách này tốt cho tests thao tác theo row, nhưng chưa đủ khi test đòi **global unique constraint**, full table count, sequence starts at 1, hay migrations sạch. Với những yêu cầu đó cần DB/schema/container riêng hoặc reset controlled.

### 12.3. Transaction rollback trên test method

`@Transactional` trên JUnit test method thường rollback cuối test và có thể giúp isolate DB writes. Nhưng:
- Nếu business code mở `REQUIRES_NEW`, transaction có thể commit ngoài rollback của test.
- External messages/email/cache không rollback theo JDBC test transaction.
- Test có thể không kiểm đúng production commit semantics.
- Asynchronous worker chạy thread khác không tự tham gia test ThreadLocal transaction.
- JDBC pool/connection lifecycle của container vẫn là vấn đề riêng.

Với commit/rollback contract, dùng tests không có outer test transaction, cleanup bằng IDs hoặc isolated DB.

### 12.4. @Sql cleanup và transaction modes

`@Sql(scripts="...")` tiện cho fixtures/cleanup, nhưng khi chạy shared broker/DB:
- Đừng dùng global TRUNCATE trong khi tests song song.
- Phân biệt execution phase BEFORE/AFTER.
- Transaction mode của SqlConfig ảnh hưởng commit/rollback.
- Một test fail trước cleanup vẫn có thể được xử lý bởi after scripts/extension, nhưng process crash có thể bỏ qua cleanup.
- Nếu cần data reset toàn diện, dùng một DB/container/schema **owned by this test**.

### 12.5. Schema per class/test

PostgreSQL hỗ trợ schemas. Một chiến lược:
- Mỗi test class tạo schema unique.
- Tạo tables/migrations trong schema đó.
- Dùng connection `currentSchema`/search_path phù hợp.
- Drop schema owned ở teardown.

Cẩn thận với pooled connections: session-level `search_path` có thể lưu trên connection khi trả về pool nếu bạn set thủ công; test khác mượn connection rồi thấy schema sai. Config schema ở datasource/connection init hoặc isolate pool/context per schema đúng cách.

### 12.6. Kafka/Rabbit/Redis cũng tương tự

- Kafka: unique topic + consumer group + event ID, không reuse committed offsets vô tình.
- RabbitMQ: unique queue/exchange/binding, competing consumers của cùng queue có thể ăn message test khác.
- Redis: unique prefix key/db/instance, TTL + cleanup, đừng gọi `FLUSHALL` trên shared backend.
- PostgreSQL/MySQL: unique schema/key, transactional cleanup, migrations.
- Elasticsearch/OpenSearch: unique index alias/name, cleanup.
- Object storage: unique bucket/prefix, versioned fixtures.
- OAuth/IdP: test realm/client/user riêng, không dùng production tenants.

“Container dùng chung” không đồng nghĩa “các tests tự cách ly nhau”.

## 13. Các dạng kết nối stale và cách nhận diện

### 13.1. Container stopped nhưng DataSource bean còn

Triệu chứng:
- `PSQLException: Connection refused`.
- Hikari pool initialization failed / connection timeout.
- Repeated retries trên một port mapped không còn listening.

Kiểm:
1. Test class vừa kết thúc có JUnit `@Container` stop lifecycle không?
2. Spring TestContext logs có context cache hit ở class kế tiếp?
3. Docker container ID/port của previous class có còn running?
4. `DataSource` đang dùng URL nào?
5. Có test method/class nào gọi `container.stop()` không?
6. Có `@DirtiesContext` đóng context trùng thời điểm không?

### 13.2. Container restart nhưng mapped port đổi

Testcontainers expose container port 5432 nhưng map tới **host port động**. Restart có thể đổi 49153 → 49188. Một Hikari DataSource cũ không tự rebind chỉ vì property supplier bây giờ trả 49188. Giữ resource lifetime đồng nhất hoặc rebuild client context khi endpoint thay đổi.

### 13.3. Container đang running nhưng DB chưa ready

Một running Docker process không có nghĩa application đã kết nối được. PostgreSQL container module có readiness/wait logic; spring-managed lifecycle start trước clients; test vẫn nên query `SELECT 1` khi contract yêu cầu.

Với GenericContainer custom image, cần wait strategy:
- Listening port.
- HTTP health endpoint.
- Log message/healthcheck.
- Tùy service: schema initialized, migrations done, consumer assigned.

Đừng viết `Thread.sleep(5000)` làm readiness check. Testcontainers wait strategies và bounded retries có điều kiện giúp ổn định.

### 13.4. DataSource connected nhưng schema chưa sẵn

Có thể đã kết nối PostgreSQL nhưng `relation does not exist` do migration/script init chưa chạy, chạy ở wrong schema hoặc context initialization failed. Kiểm:
- SQL init config `spring.sql.init.mode=always`.
- Flyway/Liquibase migrations.
- JDBC URL database/schema.
- Transaction commit/connection visibility.
- Test data owner and cleanup.
- Log schema initialization failures.

### 13.5. Pool stale connection giữa idle dài

Ngay cả khi container không stop, network/proxy idle timeout có thể cắt TCP connection. Hikari có validation/lifetime/keepalive settings. Test integration production-like có thể inject network pause/restart qua Toxiproxy, nhưng việc tăng keepalive chỉ giải quyết một lớp reliability; không thay container ownership.

### 13.6. Connection leaks

Nếu test tự `dataSource.getConnection()` mà không close, pool hết connections. Code lab dùng `try (Connection connection = ...)` để đảm bảo return to pool. `JdbcTemplate` tự quản lý connections cho statement lifecycle. Khi có nhiều async workers, Hikari max pool size phải phù hợp concurrency và transaction durations.

### 13.7. Shutdown order

Nếu JUnit dừng container **trước** khi Spring context đóng, một bean `@PreDestroy` có thể thử flush state hoặc close network client sau khi backend đã stop và throw error. Spring-managed container tránh thứ tự shutdown bất lợi này theo Boot docs: dependent beans destroy trước, container stop sau. Nếu library client tự start non-managed threads, vẫn cần đảm bảo chúng được shutdown đúng.

## 14. Test contexts và container startup trong CI

### 14.1. Một lệnh Maven, một hay nhiều JVM?

Chạy:

~~~bash
mvn -q -Dtest=SharedDatabaseAlphaTest,SharedDatabaseBetaTest test
~~~

Maven Surefire điều phối cả hai classes trong cùng command. Nhưng kết quả cache reuse vẫn phụ thuộc Surefire fork settings. Nếu có nhiều JVMs/processes, static Spring cache không được chia sẻ. Không hard-code expectation “Docker start đúng một lần” khi build configuration thay đổi.

### 14.2. Docker unavailable không phải PASS

Nếu không có Docker, Testcontainers có thể fail startup/context initialization. Đối với integration jobs, fail sớm là hữu ích: CI phải có Docker/compatible runtime. Nếu dùng `@Testcontainers(disabledWithoutDocker=true)` cho JUnit-managed containers, tests có thể SKIP; không diễn giải build exit 0 với all tests skipped là integration PASS.

Project chính **không** dùng skip annotation: thiếu Docker sẽ làm test không khởi tạo được container và CI báo lỗi. Nếu team chủ động chia test unit/integration profiles, báo rõ số tests executed.

### 14.3. Reuse image layers nhưng không reuse DB state

Docker image cache làm pull nhanh, khác container reuse. Một fresh container từ cached image vẫn có database instance mới. Build pipeline có thể pre-pull image để giảm latency, nhưng không cần bật reusable container persistent.

### 14.4. Parallel suite

Nếu test classes chạy parallel:
- Context cache infrastructure có thể share cùng bean.
- Database accepts concurrent connections.
- Test fixtures và cleanup phải được namespace.
- Pool size đủ cho number of concurrent worker threads.
- Nếu tests mutate shared singleton bean settings/log levels, cần resource lock hoặc isolate context.
- Nếu async tasks còn chạy sau test teardown, chúng có thể dùng DB sau cleanup; wait for business completion trước teardown.

### 14.5. Maven Surefire forks

Fork count, reuseForks và test grouping thay đổi cách các classes chia JVM. Nếu fork-per-class, không có JVM-local context sharing. Giữ cấu hình explicit khi benchmark, và báo performance numbers kèm máy/CI runtime/image/cache/number of forks thay vì một số tuyệt đối không thể lặp.

### 14.6. Context startup khác container startup

Một cached context hit tránh tạo lại nhiều beans. Container là Spring bean và không restart khi context còn sống. Nhưng:
- Context mới có thể reuse process-level singleton container (nếu pattern ngoài context).
- Context mới với bean container thường start một container mới.
- Cùng context nhưng test mở thêm clients/connections vẫn tốn thời gian.
- Docker image layer cache rút ngắn pull, không thay context key.

Đừng đo chung một duration rồi kết luận chính xác nguyên nhân khi chưa có logs/metrics.

## 15. Đo hiệu năng có cơ sở

### 15.1. Baseline trước khi tối ưu

Ghi nhận:
- Tổng thời gian build/test phase.
- Số test classes/methods.
- Số contexts initialized.
- Context cache hit/miss, maxSize, eviction.
- Số Docker containers started và thời gian image pull/start.
- DB migration/SQL init time.
- Number of Surefire forks/parallel workers.
- Peak RAM/CPU và Docker resources.
- Failures/flaky rate qua nhiều runs.

Một optimization chỉ có ích khi **giảm thời gian hoặc tài nguyên mà không tăng false PASS/data interference**.

### 15.2. Thứ tự tối ưu khuyến nghị

1. Tránh `@SpringBootTest` cho pure unit tests.
2. Dùng đúng test slice (`@WebMvcTest`, `@DataJpaTest`...) khi đủ kiểm behavior.
3. Nhóm các full context tests dùng cùng config/profiles để cache hit.
4. Dùng Spring-managed container bean cho các cached contexts.
5. Tạo fixtures nhỏ và dùng targeted cleanup.
6. Cân nhắc suite-level singleton container khi nhiều distinct contexts cần cùng backend, có isolation mạnh.
7. Chỉ sau đó cân chỉnh Docker image/test forks/cache.maxSize.
8. Bảo vệ correctness với concurrency/fault-injection/restart tests cho những phần nhạy cảm.

### 15.3. Không dùng @DirtiesContext như công cụ cleanup mặc định

Mỗi `@DirtiesContext` có thể gây:
- Bean scanning/bootstrap lại.
- Pool tạo lại.
- Container start mới.
- Migration chạy lại.
- Broker clients/listeners resubscribe.
- Context cache miss.

Có thể hợp lý khi test thực sự làm hỏng singleton config, nhưng đó là trade-off cần đo.

### 15.4. Không đo startup bằng Thread.sleep

Một benchmark giả:

~~~java
long start = System.nanoTime();
Thread.sleep(1000);
long elapsed = System.nanoTime() - start;
~~~

không đo Spring context hay container startup. Dùng actual build/test logs, TestContext metrics và Docker container timestamps nếu cần. Không thêm sleeps để “ổn định” test performance.

## 16. Failure tests bổ sung cho container/context lifetime

### 16.1. Tình huống class boundary

Kịch bản QA quan trọng:
1. Chạy class A với DB query thật.
2. JUnit kết thúc class A.
3. Class B dùng cùng Spring configuration trong **cùng JVM**.
4. Nếu context reused, DB/container vẫn sống.
5. Class B query thật qua Spring bean/client.
6. Assert no stale endpoint error.
7. Xem context cache logs chứng minh hit.

Code lab thực hiện các bước quan sát DB ở cả hai classes, còn cache hit được kiểm qua logs/cấu hình suite.

### 16.2. Explicit @DirtiesContext test

Một test riêng có thể dùng `@DirtiesContext(classMode=AFTER_CLASS)` để ép close và tạo context mới ở class sau, nhằm kiểm startup path. Nhưng làm vậy trong chính hai classes của lab sẽ khiến mất mục tiêu reuse. Tách suite:
- Suite A: cache reuse/lifecycle stable.
- Suite B: context rebuild/stop/start behavior.
- Suite C: backend outage/recovery bằng network proxy.

Không trộn ba mục tiêu trong một test class rồi suy kết luận từ timing.

### 16.3. Backend stop injection

Nếu cố tình `container.stop()` trong một test:
- Bạn đang thay đổi resource của cả shared context/test suite.
- Những tests khác có thể fail do connection stale.
- Mô hình Spring-managed container không được thiết kế để auto-restart khi bạn stop bean ngoài lifecycle.
- Test failure injection như vậy phải sở hữu **một dedicated container/context**, không phá container dùng chung.

Với network partition, dùng Toxiproxy/controlled infrastructure riêng và reset state trong teardown.

### 16.4. Context close and dependent beans

Muốn kiểm shutdown ordering:
- Dùng dedicated test config với một client bean có `@PreDestroy`/`DisposableBean` probe.
- Quan sát container còn running khi client destroy được gọi.
- Sau context.close, kiểm container stop.
- Không manually close shared cached context của suite chính; làm vậy phá test classes khác.

Spring Boot docs đã quy định order cho container beans; ứng dụng có custom lifecycle hooks vẫn cần validate nếu critical.

### 16.5. Connection pool refresh

Cần kiểm trường hợp DB được restart do orchestrator ngoài app:
- Pool detects connection invalid.
- New connection uses **same stable endpoint** khi backend restart trong một network abstraction.
- SQL retry đúng policy (không retry vô hạn).
- Transactions mid-flight rollback/reconcile.
- JDBC credentials/SSL settings vẫn hợp lệ.
- Connection leak metrics không tăng.

Đây là production resilience concern khác với test context cache. Không kỳ vọng Hikari tự sửa JDBC URL khi Docker mapped port đổi.

## 17. Dùng chung nhiều services

### 17.1. PostgreSQL + Redis

Một integration context có thể có:
- `PostgreSQLContainer<?>` cho JDBC.
- `GenericContainer<?>` Redis và `@ServiceConnection(name="redis")`.
- DataSource/Hikari và RedisConnectionFactory clients.

Spring-managed container beans giúp cả hai backends sống theo context. Nhưng reset data phải phù hợp:
- PostgreSQL rows qua IDs/schema.
- Redis keys qua prefix.
- Không `FLUSHALL` nếu test khác dùng Redis.
- Validate Redis TTL trong separate test khi contract cần.

### 17.2. Kafka + PostgreSQL

Khi handler đọc Kafka và ghi DB:
- Kafka container và PostgreSQL container phải ready.
- Broker connection details/JDBC details được đăng ký đúng.
- Test eventId/consumer group riêng để tránh duplicate messages.
- Listener threads phải stop sạch trước broker/container stop.
- DB transaction và Kafka offset commit không phải một transaction duy nhất theo mặc định.
- Có thể dùng outbox/idempotent handlers, nhưng cần test business consistency riêng.

Context cache càng quan trọng khi startup Kafka/Postgres cùng lúc tốn tài nguyên; data isolation cũng càng quan trọng vì topic/offsets tồn tại lâu trong container shared.

### 17.3. RabbitMQ + Redis

Một app có Rabbit listener và Redis cache:
- Queue/exchange names phải owned riêng.
- Context cached có thể giữ Rabbit listener subscriptions, chúng vẫn consume messages khi class A đã xong.
- Test B có thể bị listener từ class A “ăn mất” messages nếu cùng queue.
- Redis key namespace phải tách giữa tests.
- Nếu một class muốn tắt listener/đổi routing config, có thể cần context isolation hoặc dedicated client; không mutate shared beans tùy tiện.

### 17.4. Một broker, nhiều ApplicationContexts

Nếu cố tình dùng suite-level Kafka/Rabbit singleton cho nhiều contexts, các consumers trong mỗi context có thể **đồng thời active**. Điều này tạo interactions không có trong một-container-per-class. Cần giới hạn concurrency, unique topics/queues/groups, pause/stop listeners nếu test yêu cầu. Chỉ chia sẻ broker infrastructure chứ không tự động chia sẻ nghiệp vụ.

## 18. Common pitfalls và troubleshooting

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Class A PASS, B connection refused | JUnit @Container stopped, Spring reused context | Spring-managed container bean hoặc singleton đúng lifetime |
| `static @Container` vẫn restart | Static là Java field, extension stop per class | Không trộn JUnit extension với JVM singleton |
| Hikari trỏ port cũ | Mapped port đổi nhưng cached DataSource chưa rebuild | Giữ container live hoặc rebuild context |
| @ServiceConnection không có tác dụng | Thiếu `spring-boot-testcontainers` hoặc annotation sai scope | Thêm dependency và bean/typed container đúng |
| GenericContainer không match service | Boot không suy image repository khi bean method generic | `@ServiceConnection(name="...")` |
| DB schema không tồn tại | SQL init/migration chưa chạy hoặc wrong DB | Kiểm mode, logs, JDBC URL/schema |
| Test chỉ PASS khi chạy một mình | Data contamination/order dependency | Unique IDs, targeted cleanup, no global reset |
| Context tạo mới mỗi class | Profiles/properties/mocks/dynamic customizers khác | So sánh cache key inputs; giảm fragmentation |
| Context bị evict liên tục | Cache quá nhỏ/nhiều unique configurations | Log cache stats, đo và sửa topology |
| @DirtiesContext làm test chậm | Context + container start lại | Chỉ dùng khi state thực sự dirty |
| Docker startup chậm | Image pull, resource pressure, repeated starts | Cache images, Spring beans/context reuse |
| Container chạy nhưng query fail | Port/service/schema chưa ready | Testcontainers wait, DB SELECT 1, migrations |
| Connection pool exhausted | Connection leak, threads giữ transaction | try-with-resources, Hikari metrics |
| Duplicate note giữa tests | Reuse business key/shared data | Per-test UUID/unique namespace |
| Truncate cleanup xóa dữ liệu test khác | Shared DB + parallel tests | Targeted delete/schema isolation |
| Cache hit nhưng data khác | Shared external state vẫn tồn dư | Isolate data, không suy cache hit = clean DB |
| Cache miss nhưng backend vẫn dùng chung | Suite singleton container | Phân biệt context và Docker lifetime |
| Build split nhiều forks | Cache static không cross-JVM | Giảm forks/group tests nếu phù hợp |
| JUnit tests skipped khi thiếu Docker | disabledWithoutDocker | CI kiểm executed counts |
| Lifecycle close gây client errors | Container stop trước dependent beans | Spring-managed bean order |
| `@DynamicPropertySource` URL “đổi” nhưng pool vẫn cũ | Supplier lazy không rebuild initialized bean | Stable backend lifetime hoặc context reload |
| Embedded H2 test PASS, PG fail | Dialect/concurrency/SQL semantics khác | Testcontainers đúng PostgreSQL |
| @Transactional test che commit lỗi | Test-managed rollback | Test service boundary không outer transaction |
| Container reusable làm chạy chéo CI | Data tồn dư/ownership không rõ | Không bật reuse cho CI sạch |
| Root context startup logs khó đọc | Logging framework/test runner | Filter org.springframework.test.context.cache DEBUG |
| Shutdown test phá suite | Manually close cached context/stop shared container | Dedicated context/container cho lifecycle failure tests |

### 18.1. Chẩn đoán theo thứ tự có hiệu quả

1. Test nào fail, ở class/method thứ mấy?
2. Lỗi liên quan create context hay dùng connection sau context cache hit?
3. Container owner là JUnit extension, Spring bean, singleton JVM hay external service?
4. Container running ngay lúc fail không?
5. Mapped host port lúc client bean tạo và lúc fail có khác?
6. DataSource/producer/client đang dùng connection details nào?
7. Có `@DirtiesContext`, LRU cache eviction, fork-per-class không?
8. Cache hit/miss logs nói gì?
9. Data schema/migrations/transactions đã sẵn sàng?
10. Test data cleanup có xóa nhầm records khác?
11. Có parallel test/background listeners shared không?
12. Cuối cùng mới tune timeout/pool size, không dùng timeout để che endpoint chết.

### 18.2. Khi báo lỗi cho team, cung cấp

- Test suite command.
- Spring Boot/Testcontainers/PostgreSQL versions.
- Docker runtime type.
- Class/test order nếu có.
- Cache hit/miss/contexts count (không cần full private build logs).
- Docker container ID truncated và mapped port (không kèm credentials).
- Datasource URL **redacted** (không có password/token).
- Relevant exception stack trace và phase: startup/query/teardown.
- Owner/lifetime model đang dùng.
- Cách tái hiện với two-class suite.

Không đính kèm secrets hay production database URLs vào ticket.

## 19. Bài tập học sâu

1. Chạy lab với cả hai classes trong một Maven test invocation. Ghi cache hits/misses từ logger DEBUG.
2. Chạy từng class bằng hai Maven commands riêng; giải thích vì sao context static cache không reuse giữa hai JVMs.
3. Thêm test thứ ba có cùng `@ActiveProfiles`/`@Import`; dự đoán cache behavior.
4. Thêm `@SpringBootTest(properties="demo.mode=other")` vào class B; quan sát context mới và container bean mới.
5. Thêm `@MockitoBean` vào riêng class B; giải thích vì sao cache key có thể đổi.
6. Thêm `@DirtiesContext` vào class A; quan sát container/context restart và suite runtime.
7. Đổi `spring.test.context.cache.maxSize` từ 32 xuống 1 trong một suite nhiều contexts; quan sát LRU effects.
8. Đưa PostgreSQL container ra static initializer ở base class, dùng `@DynamicPropertySource`; so sánh JVM singleton với context bean model.
9. Cố tình gắn `@Testcontainers @Container` vào base singleton đó; phân tích vì sao class B có thể fail.
10. Thêm `SELECT 1` trước một truy vấn có schema, phân biệt backend readiness với migration readiness.
11. Tạo note ID cố định ở hai classes; quan sát duplicate/data contamination; sửa bằng UUID prefix.
12. Thử cleanup `DELETE FROM test_notes` toàn bảng khi chạy parallel, rồi thay bằng targeted deletes.
13. Chạy Hikari pool với max size 1/2/4; quan sát thời gian khi nhiều tests mượn connection đồng thời.
14. Viết một leak test cố tình không close JDBC Connection, phân tích timeout; sửa bằng try-with-resources.
15. Dùng `@Sql` tạo fixtures, đánh giá transaction mode và isolation khi cùng database.
16. Tạo schema-per-class trên PostgreSQL với unique name và search_path đúng; test không xâm phạm schema khác.
17. Thêm Redis container dùng `@ServiceConnection(name="redis")`, kiểm key namespace/TTL.
18. Thêm Kafka container và unique consumer groups/topics; kiểm consumer offsets không làm test khác miss message.
19. Dùng `@ImportTestcontainers` để import container declarations; so sánh lifecycle với `@Bean`.
20. Viết một test dedicated stop/start container để quan sát Hikari stale connections. Không chạy test này trong shared suite.
21. Tạo một Spring bean có `@PreDestroy` cần DB access; xác nhận destroy order với Spring-managed container trong dedicated context.
22. Bật fork-per-class trong Surefire và giải thích mất context cache reuse.
23. Bật JUnit parallel, dùng unique IDs và targeted cleanup, sau đó kiểm DB không chứa dữ liệu lạ.
24. Tạo business transaction fail trước commit; verify rollback bằng query sau method, không dựa test-level transaction.
25. So sánh thời gian suite với plain unit test, JDBC slice, full context và full context + Testcontainers.
26. Dùng Docker image cache trong CI, phân biệt image pull time với container startup time.
27. Tạo test ngoài cùng JVM khác cache keys nhưng cùng singleton broker, đánh giá overhead và isolation.
28. Kiểm một reusable container opt-in local qua nhiều runs, rồi nêu lý do không áp dụng cho CI.
29. Đọc TestContext cache DEBUG logs để lập bảng contexts loaded/hit/miss/eviction.
30. Viết architectural decision record xác định owner/lifetime, data cleanup và CI fork policy cho từng integration service.

## 20. Checklist kỹ thuật trước khi merge

- [ ] Chọn owner container: JUnit extension, Spring bean, JVM singleton hay external service?
- [ ] Với cached Spring context, container có còn sống suốt lifetime dependent beans không?
- [ ] Không trộn singleton static initializer và `@Container` JUnit lifecycle?
- [ ] Spring-managed containers có `@TestConfiguration + @Bean` hoặc `@ImportTestcontainers` đúng?
- [ ] `spring-boot-testcontainers` dependency có mặt khi dùng `@ServiceConnection`?
- [ ] Typed container/service details được Boot nhận diện đúng?
- [ ] Không hard-code mapped host port?
- [ ] Connection details từ container được DataSource/client thực sự dùng?
- [ ] Test có query/backend health thật, không chỉ `container.isRunning()`?
- [ ] SQL migrations/schema initialized ở đúng database?
- [ ] Không đóng shared container trong `@AfterAll`?
- [ ] Không manual close shared cached context ngoài lifecycle?
- [ ] Cache key inputs giữa test classes được giữ đồng nhất khi muốn reuse?
- [ ] Có `@DirtiesContext` nào không cần thiết phá cache?
- [ ] Có chú ý default cache max size và LRU eviction?
- [ ] Có xét Maven Surefire forks/CI workers/JVM boundary?
- [ ] Context cache hit được quan sát qua logs/metrics, không đoán từ annotations?
- [ ] Container bean không mặc định “single container cho mọi contexts”?
- [ ] Có per-test unique IDs/namespaces/targeted cleanup?
- [ ] Không TRUNCATE/FLUSHALL/DELETE global trên shared backend khi parallel?
- [ ] `@Transactional` test-level không che real commit semantics?
- [ ] Có kiểm duplicate/rollback bằng database thật khi contract yêu cầu?
- [ ] Có bảo vệ asynchronous jobs/listeners không còn chạy sau teardown?
- [ ] Có kiểm client beans shutdown trước backend container khi cần?
- [ ] Có phân biệt readyness, schema readiness và app business readiness?
- [ ] Không biến Docker unavailable thành “green all skipped” trên CI?
- [ ] Test failure injection dùng dedicated container để không phá suite?
- [ ] Production-like backend/version được chọn khi cần lock/isolation semantics?
- [ ] Credentials, customer data, JDBC URLs trong logs được redacted?
- [ ] Có benchmark baseline và regressions sau tối ưu cache/lifecycle?
- [ ] Test Maven/Surefire executed counts đã được xác nhận trong CI?

**Kết luận:** Container dùng chung và Spring context cache có thể làm integration suite nhanh hơn rõ rệt, nhưng chỉ khi **vòng đời Docker service không ngắn hơn vòng đời các Spring beans đang sử dụng nó**. Với Spring Boot 3.5, quản lý Testcontainers dưới dạng `@Bean` cùng `@ServiceConnection` (hoặc `@ImportTestcontainers`) là cách dễ hiểu để đồng bộ container start/stop với cached `ApplicationContext`. Nếu muốn chia sẻ backend xuyên nhiều contexts, JVM singleton pattern là một lựa chọn khác, nhưng không gắn `@Container` vào đó và phải quản lý data isolation cẩn thận. Luôn phân biệt cache hit của context, container process còn chạy, endpoint hiện tại của connection pool và dữ liệu test còn tồn. Tăng timeout hoặc thêm `@DirtiesContext` bừa bãi không sửa được thiết kế ownership sai; hãy xác định **ai start, ai stop, ai dùng, và dùng đến khi nào**.

## 21. Tài liệu tham khảo chính thức

- Spring Boot 3.5.16 — Testcontainers (Using Spring Beans; Lifecycle of Managed Containers; Service Connections; @ImportTestcontainers): https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Spring Framework 6.2 — TestContext Context Caching, cache key, default 32/LRU, DEBUG stats: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework 6.2 — @DynamicPropertySource and dynamic property precedence: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/dynamic-property-sources.html
- Spring Framework 6.2 — @DirtiesContext: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dirtiescontext.html
- Spring Framework 6.2 — @Sql and transactional SQL test fixtures: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/executing-sql.html
- Spring Boot 3.5 — SQL Databases (JDBC, SQL initialization, Hikari): https://docs.spring.io/spring-boot/3.5/reference/data/sql.html
- Spring Boot 3.5 — Spring Boot Testing: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Testcontainers Java — PostgreSQL module: https://java.testcontainers.org/modules/databases/postgres/
- Testcontainers Java — JUnit 5 integration: https://java.testcontainers.org/test_framework_integration/junit_5/
- Testcontainers — Singleton Containers pattern: https://java.testcontainers.org/test_framework_integration/manual_lifecycle_control/#singleton-containers
- Docker official guide — Testcontainers JUnit 5 lifecycle and singleton container caveats: https://docs.docker.com/guides/testcontainers-java-lifecycle/singleton-containers/
- Testcontainers Java — Container startup lifecycle and wait strategies: https://java.testcontainers.org/features/startup_and_waits/
- Testcontainers Java — Reusable Containers (experimental/local-only): https://java.testcontainers.org/features/reuse/
- Maven Surefire — Forking a JVM, forkCount and reuseForks: https://maven.apache.org/surefire/maven-surefire-plugin/examples/fork-options-and-parallel-execution.html
- HikariCP — Pool configuration and JDBC connection lifecycle: https://github.com/brettwooldridge/HikariCP
