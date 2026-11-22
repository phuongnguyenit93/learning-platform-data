# Container reuse, context cache và giới hạn khi chạy song song

## 1. Bài toán thực tế: nhanh hơn nhưng không được làm test sai

Trong module **Spring Boot - testing**, nhóm **Testcontainers**, một bộ integration test thường dùng PostgreSQL, Redis, Kafka hoặc Elasticsearch chạy trong Docker. Container giúp kiểm tra ứng dụng với backend gần production, nhưng khởi động lại backend cho từng test rất tốn thời gian. Vì vậy ta muốn tái sử dụng hạ tầng, đồng thời bảo đảm test vẫn đúng khi chạy lại, chạy cả suite và chạy song song.

Ba triệu chứng thường gặp:

1. Test A sử dụng PostgreSQL Testcontainer thành công, test B bắt đầu với **cached Spring ApplicationContext** và connection pool cũ, nhưng container của test A đã bị JUnit dừng: báo `Connection refused`.
2. Test chạy lẻ PASS, chạy chung FAIL vì A `DELETE FROM orders` trong khi B đang đọc chung database.
3. Bật `withReuse(true)` cho nhanh rồi dữ liệu/volume/schema từ lần chạy hôm trước còn lại: test không còn repeatable và CI khó dọn dẹp.

Cần phân biệt **ít nhất bốn kiểu reuse**:

- Container chia sẻ giữa **các test method cùng một class**, bằng static `@Container` của Testcontainers JUnit extension.
- Container sống cùng **Spring ApplicationContext được cache**, bằng Spring-managed `@Bean`, có thể phục vụ nhiều test class trong một JVM có **cùng context cache key**.
- Một container kiểu **singleton/manual lifecycle** trong JVM, được khởi động một lần bằng code, không phải tự động bằng JUnit extension; phải tự quản lý state và lifecycle.
- **Experimental reusable containers** dùng `withReuse(true)`: cố giữ container chạy **giữa những lần thực thi JVM/test khác nhau**, chủ yếu dành cho máy phát triển; không khuyến nghị cho CI.

**Mục tiêu:** giải thích vòng đời và cache key; biết khi nào tái sử dụng có ích hoặc nguy hiểm; cấu hình Spring Boot 3.5 + Testcontainers đúng; minh họa hai test class có thể dùng cùng cached context; bảo vệ database fixtures; hiểu giới hạn chạy song song của JUnit/Testcontainers/Spring/Gradle; và có checklist vận hành CI.

Ví dụ chính dùng **Java 17, Spring Boot 3.5.16, JUnit Jupiter, PostgreSQL 16.4-alpine, Spring JDBC và Testcontainers**. Chọn PostgreSQL để nhìn thấy tác động của database state, connection pool và context lifecycle. Cấu hình chính **không bật experimental reuse** và **không yêu cầu cả suite phải chạy theo một thứ tự**.

## 2. Ma trận bốn nghĩa của “reuse”

| Kỹ thuật | Scope chia sẻ | Ai start/stop? | Dữ liệu có được tự reset? | Hợp lý cho CI? |
| --- | --- | --- | --- | --- |
| Static `@Container` + `@Testcontainers` | Các method trong một test class | JUnit Testcontainers extension | **Không**; phải seed/cleanup | Có khi lifecycle/caching được quản lý rõ; lưu ý rủi ro context cache |
| Spring-managed `@Bean` container | Một `ApplicationContext`; có thể qua nhiều test classes cùng cache key | Spring Boot start trước client beans, stop khi context đóng | **Không**; phải seed/cleanup | **Có**, là pattern chính trong bài |
| Manual static singleton `container.start()` | JVM/classloader hoặc lifetime được code quản lý | Code của test/application | **Không** | Chỉ khi thiết kế teardown/connection/context/isolated data rất cẩn thận |
| `withReuse(true)` + host opt-in | Nhiều lần chạy có cùng container config | Manual start; **không được stop** nếu muốn reuse | **Không**; state còn nguyên | **Không nên**; tính năng thử nghiệm, Testcontainers khuyến cáo không dùng trong CI |

**Cache reuse không bằng experimental reuse.** Spring context cache chia sẻ các Java beans/container **trong một test process** nếu configuration khớp; container vẫn có thể bị dừng khi context đóng. `withReuse(true)` cố tình làm Docker container **tiếp tục sống sau JVM**. Hai cơ chế khác nhau về thời gian sống, cleanup và an toàn dữ liệu.

**Container reuse không bằng image caching.** Docker tải image `postgres:16.4-alpine` một lần rồi có thể dùng lại layer; lần khởi động một **container instance mới** vẫn khác với việc tái sử dụng đúng container đang chạy.

## 3. JUnit extension: static và instance @Container khác nhau

Testcontainers Java cung cấp Jupiter extension:

~~~java
@Testcontainers
class DatabaseIntegrationTest {

    @Container
    static PostgreSQLContainer<?> database =
            new PostgreSQLContainer<>("postgres:16.4-alpine");

    @Test
    void first() {
        // Container đã start cho class.
    }

    @Test
    void second() {
        // Cùng static container trong class này.
    }
}
~~~

**Đoạn trên là skeleton**, cần imports của JUnit và Testcontainers, cùng các assertion/application wiring mới thành test hữu ích.

Quy tắc theo documentation của Testcontainers:

- Static field `@Container`: bắt đầu trước các test method, dừng **sau test class**.
- Instance field `@Container`: container có lifecycle **theo từng test method**, thường tốn startup hơn nhưng dễ cô lập.
- `@Testcontainers` kích hoạt extension tìm những field đó; một static field không được JUnit quản lý nếu bạn không dùng extension/annotation.
- Một container được static field giữ qua nhiều test methods **không tự xóa data** sau method.
- `@Testcontainers(parallel = true)` là hỗ trợ khởi động **nhiều containers** đồng thời trong extension; **không** biến mọi JUnit test method thành parallel-safe.

**Giới hạn quan trọng:** Testcontainers công khai ghi nhận JUnit Jupiter extension **chỉ được thử nghiệm với sequential execution**; chạy test methods/classes song song qua extension là **unsupported** và có thể gây side effects ngoài dự kiến. Đừng coi việc JUnit hỗ trợ parallel là bằng chứng extension này cũng bảo đảm an toàn.

### Vì sao static container chưa giải quyết cached Spring context?

Ví dụ hai test class có cùng Spring configuration. Spring có thể tái dùng `ApplicationContext` đã tạo ở class A khi class B chạy, bởi TestContext cache độc lập với JUnit class lifecycle.

~~~text
Class A chạy:
  @Testcontainers start PostgreSQL A
  Spring xây ApplicationContext C -> DataSource URL/port của A
  Tests trong A chạy
  JUnit stop PostgreSQL A

Class B chạy:
  Spring tìm thấy cache key phù hợp -> trả lại C
  DataSource trong C vẫn trỏ tới PostgreSQL A đã stop
  => connection refused / stale endpoint
~~~

Không phải mọi cách khai báo static field đều chắc chắn khiến hai class dùng chung context; cache key/customizers có thể khác. Nhưng **rủi ro lifecycle lệch nhau là có thật**, được Spring Boot documentation cảnh báo. Đừng bắt Spring cache phải hiểu và tự restart mọi resource do JUnit extension đã dừng.

## 4. Spring-managed container bean: khớp lifecycle với context

Spring Boot 3.5 cho phép tạo container như một **Spring bean trong `@TestConfiguration`**. Một bean container như vậy được Spring Boot start **trước những bean ứng dụng phụ thuộc vào nó** và stop **sau khi các bean khác bị destroy**.

~~~text
Spring TestContext bắt đầu tạo ApplicationContext C
    |
    +-- Container @Bean được tạo và start
    +-- @ServiceConnection cung cấp connection details
    +-- DataSource, JdbcTemplate và app beans được tạo
    +-- @SpringBootTest class A dùng context C
    +-- @SpringBootTest class B cùng cache key có thể dùng C
    |
Spring TestContext đóng/evict C
    |
    +-- destroy app beans, connection pool
    +-- dừng container @Bean sau cùng
~~~

Cơ chế này thuận lợi hơn khi ứng dụng có datasource, Elasticsearch client, listener hoặc migration bean cần backend tồn tại trong suốt vòng đời cached context.

**Không có cam kết** container sẽ chỉ start đúng một lần cho toàn bộ `gradlew test`. Spring có thể tạo **nhiều context** nếu active profile, test properties, imported configurations, bean overrides, web environment, context customizers hoặc các thành phần cache key khác nhau. Cache có thể evict hoặc test có `@DirtiesContext`. Gradle forks cũng có cache khác.

Trong Spring Boot 3.5, `@ServiceConnection` từ `spring-boot-testcontainers` cung cấp `JdbcConnectionDetails` cho `PostgreSQLContainer`, nên không cần hard-code `spring.datasource.url=jdbc:postgresql://localhost:5432/...`. Connection details được ưu tiên hơn connection properties tương ứng. Chính PostgreSQLContainer typed return value cho phép Boot xác định factory phù hợp.

## 5. Context cache: key, scope và eviction

Spring TestContext giữ ApplicationContext trong **static cache của JVM**. Nó tạo key từ cấu hình test, không đơn giản từ tên class:

| Thành tố | Ví dụ làm thay đổi key |
| --- | --- |
| `@ContextConfiguration` classes/locations/initializers | Test A import config khác test B |
| Spring Boot context customizers | `@DynamicPropertySource` methods, `@MockitoBean`/bean overrides, Boot customizers |
| `@ActiveProfiles` | `test` so với `integration` |
| `@TestPropertySource` / inline properties | Một test đặt `feature.flag=true`, test khác đặt false |
| Context loader / parent hierarchy | Custom loader, `@ContextHierarchy` |
| `@WebAppConfiguration` resource base path | Web application settings khác |
| Loại web environment và Boot test options | `RANDOM_PORT`, `MOCK` hoặc những Boot customizers khác |

Một số test class dùng **cùng chính xác** `@SpringBootTest(classes=DemoApplication.class)` và `@Import(PostgresTestConfig.class)` có thể chia sẻ context. Nếu một class có thêm `@MockBean` hay `@TestPropertySource` riêng, đó có thể trở thành context khác với container khác.

Theo Spring Framework, cache mặc định có **max size 32** contexts, dùng **LRU eviction**. Có thể cấu hình với JVM property `spring.test.context.cache.maxSize`; log `org.springframework.test.context.cache=DEBUG` để thấy hit/miss/size. Mỗi Gradle test worker JVM có static cache **riêng**.

### @DirtiesContext không phải dữ liệu cleanup

`@DirtiesContext` yêu cầu Spring loại bỏ/đóng ApplicationContext khỏi cache, nên container bean thuộc context đó cũng được dừng. Context tiếp theo sẽ được tạo lại; đó là thao tác **đắt** và có thể ảnh hưởng tests đang dùng cùng context nếu chạy song song.

Nó **không tự xóa state** ở một database ngoài context, Kafka cluster dùng chung hay một **experimental reusable container** vẫn chạy. Đừng gắn `@DirtiesContext` lên mọi test chỉ để “chắc ăn” nếu bạn có thể dọn đúng rows/topics của test.

### Failure threshold

Spring Framework 6.1+ có **context failure threshold**, mặc định 1 attempt cho cùng cache key. Nếu backend không khởi động khiến context load FAIL, test khác có cùng key có thể bị skip tải context ngay với một `IllegalStateException` nói failure threshold đã vượt. Thấy 10 test báo lỗi liên tiếp không có nghĩa Docker khởi động lỗi 10 lần: **tìm root cause của lần đầu**.

## 6. Ví dụ runnable: Java 17, Boot 3.5, PostgreSQL Testcontainers

Tạo một repository JDBC tối giản viết/đọc `tc_notes`. Mục tiêu là minh họa vòng đời và cô lập test data, không triển khai một business application phức tạp.

Cấu trúc:

~~~text
settings.gradle
build.gradle
src/main/java/com/example/containercache/
    ContainerCacheApplication.java
    NoteRepository.java
src/test/resources/
    application.properties
    schema.sql
src/test/java/com/example/containercache/
    PostgresTestConfig.java
    NoteRepositoryAIntegrationTest.java
    NoteRepositoryBIntegrationTest.java
~~~

Các class Java cùng package `com.example.containercache` để Spring Boot component scan `NoteRepository`. Hai test classes sẽ có **cùng config và import**, giúp Spring có cơ hội reuse cached context. **Không assert rằng context chắc chắn cùng identity** vì thứ tự/eviction/forks là yếu tố runtime; ta chỉ assert hành vi DB đúng.

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:postgresql'
    testImplementation 'org.testcontainers:junit-jupiter'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
}
~~~

Spring Boot dependency management thống nhất JDBC, PostgreSQL driver và Testcontainers versions phù hợp với Boot 3.5; không trộn Testcontainers 2.x coordinates vào mẫu 3.5 khi chưa kiểm lại BOM.

`maxParallelForks = 1` đảm bảo Gradle không chia tập test **thuộc task này** thành nhiều test JVMs song song. JUnit Jupiter vẫn có cấu hình parallel riêng; mặc định JUnit chạy tuần tự, nhưng nếu repo đã có `junit-platform.properties` bật parallel thì cần xét thêm. Một Gradle task khác, multi-module build hoặc CI shards vẫn có thể chạy đồng thời và sẽ có cache/container scope riêng.

### settings.gradle

~~~groovy
rootProject.name = 'container-cache-tests'
~~~

### PostgreSQL image

Ví dụ chọn `postgres:16.4-alpine` để pin server version thay vì `postgres:latest`. Nếu production dùng phiên bản khác, cân nhắc test trên cùng major và cấu hình extensions/collation giống production. Docker daemon/permissions và registry pull phải hoạt động; đây không phải một H2 test.

## 7. Application và repository JDBC thật

**src/main/java/com/example/containercache/ContainerCacheApplication.java**

~~~java
package com.example.containercache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContainerCacheApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContainerCacheApplication.class, args);
    }
}
~~~

**src/main/java/com/example/containercache/NoteRepository.java**

~~~java
package com.example.containercache;

import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class NoteRepository {
    private final JdbcTemplate jdbc;

    public NoteRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(String key, String text) {
        jdbc.update(
                """
                INSERT INTO tc_notes (note_key, note_text)
                VALUES (?, ?)
                """,
                key,
                text
        );
    }

    public Optional<String> find(String key) {
        return jdbc.query(
                """
                SELECT note_text
                FROM tc_notes
                WHERE note_key = ?
                """,
                (rs, rowNum) -> rs.getString("note_text"),
                key
        ).stream().findFirst();
    }

    public void delete(String key) {
        jdbc.update(
                "DELETE FROM tc_notes WHERE note_key = ?",
                key
        );
    }
}
~~~

`JdbcTemplate` thực hiện SQL thật trên PostgreSQL được Spring `DataSource` cấu hình. Repository intentionally **không dùng in-memory Map**, để tests thực sự kiểm tra connection và persisted state.

`insert`/`delete` chạy theo JDBC default/autocommit khi không có transaction ngoài. Hai test class **không** gắn `@Transactional`. Mỗi test chịu trách nhiệm xóa key mình đã ghi trong `finally`. Nếu dùng test `@Transactional` và rollback thì cần hiểu các đường có transaction độc lập, server HTTP thread hoặc asynchronous writes có thể commit ngoài rollback.

Không có identifier literal chung cho toàn suite; `note_key` được tạo riêng cho từng test bằng UUID, còn assertion so sánh **nội dung cố định**. Việc UUID khác nhau không làm test nondeterministic vì expected result không phụ thuộc giá trị ID ngẫu nhiên.

## 8. Schema và test properties

**src/test/resources/schema.sql**

~~~sql
CREATE TABLE IF NOT EXISTS tc_notes (
    note_key VARCHAR(100) PRIMARY KEY,
    note_text VARCHAR(255) NOT NULL
);
~~~

**src/test/resources/application.properties**

~~~properties
spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:schema.sql
spring.datasource.hikari.maximum-pool-size=4
~~~

`spring.sql.init.mode=always` cho phép Boot chạy SQL schema initializer trên PostgreSQL trong môi trường test, thay vì chỉ tự khởi tạo khi có embedded DB. `CREATE TABLE IF NOT EXISTS` giúp schema init không fail nếu một context khác dùng cùng database, nhưng **đừng dùng nó để che sự khác biệt schema migration của production**.

Không có `spring.datasource.url`/`username`/`password` hard-code vì `@ServiceConnection` cấp JDBC connection details từ container. Test config nên đảm bảo không vô tình kết nối tới production database qua một property source khác.

### Lưu ý khi có Flyway/Liquibase

Ứng dụng thật dùng Flyway/Liquibase nên chạy schema migrations bằng cùng tool trong integration test, thay vì trộn `schema.sql` demo với migration làm tạo trùng bảng. Spring Boot `@ServiceConnection` cũng có khả năng cung cấp details cho migration tooling từ `JdbcDatabaseContainer` khi phù hợp.

Tốt nhất mỗi module chọn **một chủ sở hữu schema**: SQL init cho demo nhỏ, hoặc migration scripts có kiểm soát cho production-like tests.

## 9. Testcontainers bean có vòng đời gắn với Spring context

**src/test/java/com/example/containercache/PostgresTestConfig.java**

~~~java
package com.example.containercache;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
public class PostgresTestConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>(
                "postgres:16.4-alpine"
        );
    }
}
~~~

**Vì sao là `@Bean`?** Spring Boot quản lý lifecycle theo `ApplicationContext`, tránh để JUnit tự stop container trong khi context/connection pool vẫn được cache.

**Vì sao là `@ServiceConnection`?** `JdbcConnectionDetails` được sinh dựa vào **typed PostgreSQLContainer**. Spring auto-config biết URL, mapped port, user/password phù hợp, bất kể Docker map container port 5432 sang host port nào. Không gọi `getMappedPort(5432)` trước khi container start, cũng không dùng `localhost:5432` như một hằng số.

**Vì sao `@TestConfiguration`?** Config chỉ có trong test source set và chỉ được import vào classes chọn dùng Testcontainers, không được biến thành một production Docker dependency.

Đừng thêm `@Container` vào bean return value này. `@Container` dành cho field do JUnit extension quản lý, không phải Spring bean. Đừng vừa `@Testcontainers` vừa cố dùng JUnit lifecycle cho cùng object Spring-managed; sẽ không rõ ai stop trước và làm cache mất ổn định.

**Lưu ý Spring Boot 3.1+:** `@ServiceConnection` là API tiện ích được giới thiệu trong dòng Boot 3.1. Với Boot cũ không có API này, sử dụng `@DynamicPropertySource` hoặc connection properties theo phiên bản. Bài mẫu chọn Boot 3.5 để không trộn cấu hình.

## 10. Test class A: chạy thật và dọn đúng dữ liệu

**src/test/java/com/example/containercache/NoteRepositoryAIntegrationTest.java**

~~~java
package com.example.containercache;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = ContainerCacheApplication.class)
@Import(PostgresTestConfig.class)
class NoteRepositoryAIntegrationTest {

    @Autowired
    NoteRepository notes;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    PostgreSQLContainer<?> postgres;

    @Autowired
    ApplicationContext context;

    @Test
    void containerAndJdbcAreReady() {
        assertThat(postgres.isRunning()).isTrue();
        assertThat(context.getId()).isNotBlank();

        Integer answer = jdbc.queryForObject(
                "SELECT 1", Integer.class
        );
        assertThat(answer).isEqualTo(1);
    }

    @Test
    void insertsReadsAndCleansOwnKey() {
        String key = "a-" + UUID.randomUUID();

        try {
            notes.insert(key, "hello-from-A");

            assertThat(notes.find(key))
                    .contains("hello-from-A");
        } finally {
            notes.delete(key);
        }

        assertThat(notes.find(key)).isEmpty();
    }

    @Test
    void separateKeysDoNotOverwriteEachOther() {
        String first = "a1-" + UUID.randomUUID();
        String second = "a2-" + UUID.randomUUID();

        try {
            notes.insert(first, "alpha");
            notes.insert(second, "beta");

            assertThat(notes.find(first)).contains("alpha");
            assertThat(notes.find(second)).contains("beta");
        } finally {
            notes.delete(first);
            notes.delete(second);
        }
    }
}
~~~

Ba ca kiểm tra: backend/container sống, JDBC giao tiếp thật; insert/read/delete; và hai business keys độc lập. `finally` cố xóa đúng rows của test nếu assertion thất bại. Có thể fail nếu database không sẵn sàng ngay từ đầu; khi đó phải sửa root cause thay vì xóa/bật reuse bằng mọi giá.

**Không có `@DirtiesContext`** vì test không thay bean definitions/config và có cleanup đúng phạm vi. Context có thể được Spring reuse nếu test class sau dùng cùng key và chưa có eviction.

### Tại sao không assert containerId cố định?

`container.getContainerId()` và mapped port do runtime tạo ra, **không có giá trị cố định** xuyên các lần chạy. Test nên assert `isRunning()` và hành vi truy vấn, không assert một id/port literal. Muốn *quan sát* cache, có thể bật log của Spring context cache; test không nên fail chỉ vì context cần được rebuild hợp lệ.

## 11. Test class B: cùng config, nhưng dữ liệu độc lập

**src/test/java/com/example/containercache/NoteRepositoryBIntegrationTest.java**

~~~java
package com.example.containercache;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = ContainerCacheApplication.class)
@Import(PostgresTestConfig.class)
class NoteRepositoryBIntegrationTest {

    @Autowired
    NoteRepository notes;

    @Autowired
    PostgreSQLContainer<?> postgres;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void anotherClassCanUseTheSameContainerConfiguration() {
        assertThat(postgres.isRunning()).isTrue();

        String key = "b-" + UUID.randomUUID();

        try {
            notes.insert(key, "hello-from-B");

            assertThat(notes.find(key))
                    .contains("hello-from-B");

            Integer answer = jdbc.queryForObject(
                    "SELECT 1", Integer.class
            );
            assertThat(answer).isEqualTo(1);
        } finally {
            notes.delete(key);
        }
    }
}
~~~

Hai classes dùng **cùng** `@SpringBootTest(classes = ContainerCacheApplication.class)` và `@Import(PostgresTestConfig.class)`. Khi Spring cache key hoàn toàn tương đương và class B chạy trong cùng JVM trước khi cache evict, nó **có thể dùng cùng ApplicationContext và container bean** với class A.

Bộ test không cần biết class nào chạy trước và **không khẳng định** “container phải start đúng một lần” làm điều kiện PASS. Nếu fork/eviction khiến hai contexts được tạo, các tests vẫn đúng. Đó là khác biệt giữa **tối ưu startup** và **business correctness**.

### Vì sao phải có isolation dù reuse context?

Spring cache reuse *beans* và data source, không tạo database transaction/snapshot mới cho từng test. Nếu class A và B cùng chạy, những committed rows sẽ nằm trong cùng database trừ khi test cleanup. `UUID` tạo key riêng và `finally` xóa đúng key là điều kiện để không phá nhau.

**Giới hạn:** Testcontainers container giữ cả schema, dữ liệu, users, migrations, caches, broker topics và resource state. Không có “tự reset giữa tests” chỉ vì mỗi method có `@Test`.

## 12. Cách quan sát cache reuse mà không viết test phụ thuộc thứ tự

Khi muốn biết Spring thực sự cache như kỳ vọng, bật debug logger cho context cache:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Có thể thêm **tạm thời** vào `src/test/resources/application.properties` (không bắt buộc cho code mẫu). Spring TestContext sẽ log cache size/hit/miss, giúp chẩn đoán context churn. Nếu đưa vào sample runnable mặc định, log có thể dài; thường chỉ bật trong phiên profiling.

Chạy:

~~~bash
./gradlew test --tests "com.example.containercache.NoteRepository*IntegrationTest"
~~~

Cần chú ý test task/JUnit có thực sự đưa cả class A và B vào **cùng JVM** hay không. Cache của Spring là static theo process; `maxParallelForks=1` trong ví dụ giới hạn số fork chạy đồng thời, nhưng Gradle/IDE vẫn có thể chạy tasks hoặc invocations ở JVM khác nhau. **Không có cross-process context cache**.

### Khi nào Spring tạo context mới?

- Test class A có `@ActiveProfiles("test")`, class B `@ActiveProfiles("qa")`.
- Inline `@SpringBootTest(properties=...)` hoặc `@TestPropertySource` khác.
- `@MockitoBean`/`@MockBean` overrides khác.
- `@DynamicPropertySource` methods/customizers khác.
- `@Import` configurations khác.
- Một test dùng `@DirtiesContext` làm cache entry bị close.
- Cache vượt max size/LRU eviction, hoặc test chạy trong fork/JVM mới.

Dừng container theo context **không phải lỗi** nếu context đúng là đã đóng; lỗi là app beans **còn trỏ tới container đã bị một lifecycle khác dừng**.

## 13. @DynamicPropertySource và static container: pattern phổ biến cần hiểu rủi ro

Một pattern cũ/đơn giản:

~~~java
@Testcontainers
@SpringBootTest
class ExampleWithDynamicProperties {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16.4-alpine");

    @DynamicPropertySource
    static void postgresProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    // @Autowired JdbcTemplate; @Test ...
}
~~~

**Đây là skeleton**: cần imports, assertions và cấu hình datasource/driver. Nó mô tả `@DynamicPropertySource` để đăng ký URL/user/password động từ container. Không coi đây là mẫu khuyến nghị nhất khi dự án đã dùng Boot 3.5 `@ServiceConnection`.

Rủi ro đặc biệt:

1. Static `@Container` có JUnit class lifecycle; nó stop sau class.
2. Spring TestContext cache có thể giữ `DataSource`/client lâu hơn.
3. Khi cùng cached context tái sử dụng, app bean vẫn giữ connection details tới container đã stop.
4. `@DynamicPropertySource` là **một thành phần context cache key**; không giả định Spring tự nhận ra tất cả những thay đổi *giá trị runtime* của dynamic suppliers.
5. Nếu các subclasses kế thừa cùng dynamic method nhưng cấu hình/container thực khác nhau, Spring docs khuyến cáo cân nhắc `@DirtiesContext` để đảm bảo context được dựng lại; đổi lại context churn.

**Đừng chữa bằng cách luôn thêm `@DirtiesContext` vào mọi test**: có thể tốn nhiều container startups và gây vấn đề khi parallel. Nếu bài toán là Spring Boot 3.5 và container phải sống theo cached context, chọn Spring-managed `@Bean` hoặc `@ImportTestcontainers`.

## 14. @ImportTestcontainers: cách khai báo dùng lại container configuration

Spring Boot 3.5 có `@ImportTestcontainers` để import các declarations từ interface hoặc class có container fields vào một test configuration.

Ví dụ ý tưởng **không phải bộ test runnable thứ hai**:

~~~java
interface SharedContainers {
    @Container
    PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16.4-alpine");
}
~~~

~~~java
@TestConfiguration(proxyBeanMethods = false)
@ImportTestcontainers(SharedContainers.class)
class ImportedContainersConfiguration {
}
~~~

`@ImportTestcontainers` nằm ở `org.springframework.boot.testcontainers.context.ImportTestcontainers`. Khi dùng cách này trong Spring Boot test config, Boot quản lý imported container declarations như phần của context lifecycle theo tài liệu, giúp tránh JUnit extension tự stop trước khi context được đóng.

Đoạn này cần imports và config thêm phù hợp; **mẫu runnable chính dùng `@Bean + @ServiceConnection`**, không cần `@ImportTestcontainers`. Nếu dùng containers trên fields, nhớ bảo đảm cách đăng ký service connection/connection properties theo Boot version. Không dùng cả JUnit extension và Spring lifecycle cùng lúc cho một container instance khi chưa hiểu ai start/stop.

## 15. Experimental withReuse(true): chức năng khác hẳn context cache

Testcontainers Java có tính năng **Reusable Containers (Experimental)**. Nó **opt-in** và giữ container sống qua nhiều lần chạy nếu container config trùng khớp, nhưng tài liệu chính thức nói rõ tính năng còn thử nghiệm và **không phù hợp CI**.

Cách bật cho **máy phát triển cá nhân**:

~~~properties
# ~/.testcontainers.properties
testcontainers.reuse.enable=true
~~~

Hoặc môi trường shell:

~~~bash
export TESTCONTAINERS_REUSE_ENABLE=true
~~~

Dành cho PowerShell:

~~~powershell
$env:TESTCONTAINERS_REUSE_ENABLE = "true"
~~~

Và code minh họa manual lifecycle:

~~~java
GenericContainer<?> redis = new GenericContainer<>("redis:7.4-alpine")
        .withExposedPorts(6379)
        .withReuse(true);

redis.start();

// Chỉ ở môi trường DEV có opt-in reuse.
// Không gọi stop(), không try-with-resources và
// không đặt đối tượng này dưới @Container JUnit extension.
~~~

**Đây là snippet minh họa**, cần import `org.testcontainers.containers.GenericContainer` và một test/dev harness phù hợp. Không đặt snippet này trong demo PostgreSQL ở các phần trên.

Theo Testcontainers:

- Phải có **host-level opt-in** và `withReuse(true)` trong code.
- Phải start thủ công bằng `start()`, không stop khi muốn container được tái sử dụng.
- **Không dùng JUnit extension `@Container`** hoặc try-with-resources vì chúng sẽ stop container.
- Host opt-in có thể dùng `~/.testcontainers.properties` hoặc environment variable; **không kích hoạt bằng classpath `testcontainers.properties`**.
- Config phải match giữa các lần chạy; thay image/env/ports/network có thể khiến container mới được tạo.
- Container có thể mang dữ liệu, credentials, volume và trạng thái từ lần chạy trước; phải có reset strategy riêng.
- Resource cleanup/networking chưa được bảo đảm như lifecycle thông thường, vì vậy **không khuyến nghị chạy trong CI**.

**Không phối hợp `withReuse(true)` một cách vô thức với Spring-managed container bean**, vì Spring sẽ stop bean khi context đóng — trái mục tiêu của experimental reuse. Muốn dùng experimental reuse trong local dev, thiết kế một manual lifecycle riêng, không dùng cùng object cho cả hai cơ chế stop khác nhau.

### Dùng Testcontainers JDBC URL?

Một số module JDBC hỗ trợ `TC_REUSABLE=true` trong Testcontainers JDBC URL, ví dụ theo tài liệu:

~~~properties
# Minh họa cấu trúc URL, không phải config của app chính.
spring.datasource.url=jdbc:tc:postgresql:16.4:///testdb?TC_REUSABLE=true
~~~

Tính năng này cũng phụ thuộc host opt-in và giới hạn của reusable containers. Không đồng thời dùng URL `jdbc:tc:...` và `@ServiceConnection` từ Spring-managed PostgreSQLContainer trong cùng mẫu mà không kiểm soát datasource precedence; hai cách tạo backend khác nhau.

## 16. Vì sao không bật reusable containers trên CI?

CI cần tính **reproducible, isolated và disposable**:

- Pipeline có thể dùng runner tạm, Docker daemon tạm hoặc remote engine; container cũ không chắc tồn tại.
- Một reused container có thể chứa data/schema của build trước, khiến “fresh database” giả.
- Hai builds cùng cấu hình có thể đụng cùng instance, làm test phá dữ liệu nhau.
- Container có thể giữ credentials/secrets/logs từ phiên trước.
- Network/cleanup của experimental reuse có giới hạn, khiến resource leak khó chẩn đoán.
- CI scale nhiều workers tạo nhiều namespaces/forks, nên reuse chưa chắc đem lại hiệu năng thực.

**Khuyến nghị CI:** dùng Spring-managed container bean, pin image, seed/cleanup hoặc per-worker database/schema, tận dụng Docker image cache và Spring TestContext cache **trong cùng JVM**. Đo startup time trước khi tối ưu. Đừng đánh đổi test isolation để tiết kiệm vài giây.

Khi cần benchmark hiệu năng:

1. Đo thời gian cold image pull, container startup, context startup, schema migration và từng test method riêng.
2. Log số lần tạo ApplicationContext và số container ID thực.
3. Xác định test classes có cache key thực sự giống nhau không.
4. Chỉ tối ưu sau khi có profile; có khi migration/indexing tốn thời gian hơn Docker startup.
5. Chạy suite với clean database một lượt để đảm bảo tối ưu không che lỗi.

## 17. Ba tầng parallelism: JUnit, Spring và Gradle/CI

| Tầng | Cách bật phổ biến | Rủi ro chính |
| --- | --- | --- |
| JUnit Jupiter | `junit.jupiter.execution.parallel.enabled=true` cùng execution modes | Test methods/classes trong JVM cùng truy cập backend |
| Spring TestContext | Cache một `ApplicationContext` cho nhiều tests | Shared singleton beans, DB state, cache eviction/`@DirtiesContext` |
| Gradle test workers | `maxParallelForks > 1` / `forkEvery` | **Nhiều JVM**, mỗi JVM có cache riêng; nhiều containers |
| CI matrix/shards | Nhiều jobs/agents chạy cùng lúc | Shared Docker daemon/remote DB/index/topic/state |

**Spring TestContext hỗ trợ một số use cases parallel tests**, nhưng chính tài liệu Spring cảnh báo không nên parallel khi test dùng `@DirtiesContext`, bean mocks/spies hoặc **thay state của shared systems** như DB/message broker/filesystem.

**Testcontainers JUnit extension cảnh báo unsupported parallel execution**; đừng suy từ việc `@Testcontainers(parallel=true)` cho phép start containers đồng thời thành việc test code chạy song song an toàn.

### Cấu hình JUnit để nhìn thấy rõ tác động

Ví dụ opt-in **classes song song, methods trong class tuần tự**:

~~~properties
# src/test/resources/junit-platform.properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=same_thread
junit.jupiter.execution.parallel.mode.classes.default=concurrent
~~~

Đây là **phương án thí nghiệm tùy chọn**, **không** được bật trong mẫu runnable chính. Chỉ cân nhắc khi các test classes đã có isolation và lifecycle tương thích. Nếu sử dụng JUnit-managed `@Container` extension, parallel vẫn ngoài phạm vi được Testcontainers xác nhận hỗ trợ.

**`maxParallelForks=1` không tắt JUnit parallel trong một JVM**, và `junit.jupiter.execution.parallel.enabled=false` không ngăn các Gradle tasks/CI jobs khác chạy đồng thời. Phải quản lý cả ba tầng.

### @ResourceLock

JUnit Jupiter có `@ResourceLock` để điều phối những test trong cùng engine/JVM cùng dùng một **resource logic**:

~~~java
@ResourceLock(
        value = "shared-postgres-fixture",
        mode = ResourceAccessMode.READ_WRITE
)
class SharedDatabaseTest {
    // Những methods/tests được đánh dấu tương ứng
    // có thể cần chạy tuần tự nếu cùng phá fixture.
}
~~~

Đoạn này là **skeleton**, cần imports của JUnit Jupiter parallel và một test class hoàn chỉnh. `@ResourceLock` **không khóa PostgreSQL trên nhiều JVM hoặc CI jobs**. Nó cũng không biến Testcontainers JUnit extension thành một cơ chế officially supported parallel. Nếu database dùng chung giữa processes, cần isolation ở datasource/schema/namespace hoặc một coordinator xuyên processes thực sự.

## 18. Chạy song song đúng cách: cô lập theo cấp độ dữ liệu

Một container chia sẻ không nhất thiết làm test flake nếu **mỗi test sở hữu dữ liệu riêng**. Nhưng cần xác định đơn vị tách biệt:

| Backend | Cô lập mức nhẹ | Cô lập mức mạnh | Rủi ro |
| --- | --- | --- | --- |
| PostgreSQL/MySQL | Business key/tenant ID riêng + cleanup | Schema/database/container riêng | `TRUNCATE`, shared sequences, migrations, row locks |
| Redis | Prefix key theo run/test, TTL + cleanup | DB instance/container riêng | `FLUSHALL` xóa dữ liệu test khác |
| Kafka | Topic per run, group.id riêng, key độc lập | Broker/cluster riêng | Consumer offsets/group reuse, topic deletion |
| Elasticsearch | Index alias/index theo test worker | Cluster/container riêng | `DELETE index` trong lúc test khác tìm |
| MongoDB | Database/collection namespace per suite | Mongo instance riêng | `dropDatabase` khi test khác đang đọc |
| RabbitMQ | Queue/exchange/vhost theo run | Broker instance riêng | Purge/delete shared queue |
| LocalStack/S3 | Bucket/object prefix theo run | LocalStack instance riêng | Delete bucket chung |

**`@Transactional` không bảo đảm mọi thay đổi được rollback** nếu server xử lý HTTP request trên thread khác, một `REQUIRES_NEW` commit, một task async chạy riêng hoặc backend không có transaction tương đương. Do đó hãy dùng transaction test khi phù hợp, nhưng **không thay thế cleanup/isolation rõ ràng**.

### SQL teardown

Đừng dùng:

~~~sql
TRUNCATE TABLE tc_notes;
~~~

trong một test có thể chạy song song với test khác trên cùng database. Nó xóa dữ liệu của cả hai. Mẫu runnable dùng `DELETE WHERE note_key = ?` trong `finally` với key duy nhất cho từng test.

Nếu môi trường được cô lập ở mức **container riêng per test class**, TRUNCATE có thể chấp nhận tùy contract và không có test khác chia sẻ container. Không khái quát một chiến lược cleanup cho mọi scope.

### Side effects không chỉ là rows

Nếu test dùng app singleton mutable caches, Redis locks, broker consumer groups hoặc external connectors, chỉ xóa DB rows chưa đủ. Tái sử dụng context giữ lại beans/caches giữa methods/classes: phải reset những state có ảnh hưởng tới expected results hoặc tái tạo context khi thực sự cần.

## 19. Những điều có thể vô hiệu hóa lợi ích của Spring context cache

1. **Mỗi class khai báo test property riêng:** context cache key khác, container bean mới.
2. **@MockitoBean/spy khác nhau:** bean overrides là context customizers; có thể tách cache và tạo shared mutable mock state.
3. **@DirtiesContext phổ biến:** đóng cached context, container bean bị stop, test sau tạo lại.
4. **Too many contexts:** vượt LRU max 32 làm context cũ bị evict.
5. **Gradle forks nhiều:** cache static không vượt process; mỗi JVM tự startup hạ tầng.
6. **Mỗi method ép new JVM:** context/cache không thể reuse.
7. **Thay config giữa hai classes:** `@ActiveProfiles`/`@TestPropertySource` khác làm cache split.
8. **Dùng static @Container của JUnit:** stop theo test class, có thể trước cached context.
9. **Mỗi test class tự viết một `@TestConfiguration` khác:** dù tạo container giống nhau, class config khác có thể gây cache key khác.
10. **Một test mutate singleton trong context:** test sau nhận state cũ, dù Docker vẫn sống.

**Mẹo:** đưa container config chung vào **một `PostgresTestConfig`** và import nhất quán, như hai test classes ở ví dụ. Chọn một số test groups theo dependency profile thật; không ép mọi module dùng chung một context nặng chứa đủ Kafka/Redis/DB nếu một test chỉ cần JDBC.

## 20. Hướng dẫn kiểm tra runtime khi test thất bại

### Connection refused sau class A

- Có đang dùng static `@Container` với JUnit lifecycle không?
- Spring đã reuse cached `ApplicationContext` sau khi container bị stop chưa?
- Datasource đang giữ URL/port mapping của container cũ?
- Test B có cùng cache key không, và container A còn chạy?
- Có `@DirtiesContext` hoặc context eviction không?

**Giải pháp ưu tiên:** chuyển container phụ thuộc context sang Spring-managed bean hoặc `@ImportTestcontainers`, không cố start/stop thủ công trong `@BeforeAll`/`@AfterAll` khi Spring cache vẫn đang được dùng.

### Test suite fail nhưng test đơn lẻ pass

- Hai tests có cleanup toàn bảng/index/topic không?
- Có `@BeforeEach` `DELETE ALL` trong shared DB không?
- Test methods/classes chạy concurrent trong JVM hay across forks?
- Có reset static singleton/fake/mock khác?
- Container reuse giữa process giữ lại data cũ?
- Có seed data thiếu namespace/unique key không?

**Giải pháp:** phân biệt *lifecycle conflict* với *state conflict*, thêm isolation/cleanup per test, giảm parallel ở nhóm không an toàn, và đo lại khi các assertions ổn định.

### Context startup fail nhiều lần

- Xem lỗi **đầu tiên** (Docker daemon chưa chạy, image pull, credentials, no matching driver).
- Spring 6.1+ có failure threshold, nên lỗi sau có thể chỉ là skip vì cùng cache key.
- Bật DEBUG cache log khi cần, không chỉ đọc stack trace cuối cùng.
- Không tăng failure threshold để che một container thật sự không thể start.

### Docker OutOfMemory/ports exhausted

- Bao nhiêu Gradle test workers/JVMs/CI jobs đang start containers đồng thời?
- Image có giới hạn RAM/CPU không?
- Có test nào bật experimental reuse khiến Docker container tiếp tục sống?
- Có port cố định `withFixedExposedPort` hoặc bind port 5432 gây conflict?
- Có host networking hoặc Testcontainers network config chưa được cô lập?

**Khuyến nghị:** giữ mapped ports động; dùng `@ServiceConnection`/runtime connection details; pin maxParallelForks theo tài nguyên runner; cleanup container đúng lifecycle.

## 21. Kịch bản quyết định reuse trong thực tế

| Tình huống | Lựa chọn thực dụng |
| --- | --- |
| Một class có 5 test methods, backend không cần giữ data giữa tests | Static `@Container` hoặc Spring-managed bean, thêm cleanup |
| Nhiều `@SpringBootTest` classes có cấu hình giống nhau | **Spring-managed container bean** + context cache và test fixtures riêng |
| Có `@DataJpaTest` và `@SpringBootTest` khác context key | Chấp nhận contexts/containers khác hoặc thiết kế fixture layer chung cẩn thận |
| Developer chạy đi chạy lại một test, startup chậm | Có thể **thử experimental reuse** trên máy cá nhân, với data reset rõ ràng |
| CI chạy multi-module, test workers song song | **Không dùng experimental reuse**; cô lập container/schema và hạn chế concurrency theo tài nguyên |
| Một shared Kafka/Redis cluster bị nhiều tests xóa state | Namespace theo run hoặc container riêng, không chỉ `@ResourceLock` trong JVM |
| Test dùng `@DirtiesContext`, mock overrides và mutable beans | Giảm parallel, cân nhắc lại context caching/isolation |
| Hệ thống không có Docker | Dùng backend test service được cấp riêng hoặc chỉ unit/mock tests; không giả tuyên bố integration PASS |
| Cần verify production transaction locking/isolation | Testcontainers DB cùng loại production, transaction boundaries riêng, không chỉ H2 |
| Chỉ muốn tăng tốc test | Đo metrics trước; cân nhắc Docker image cache, giảm context churn, schema migration cost |

Không tối ưu một test theo số container ID trước khi xác minh correctness. Một bài test có thể start **hai containers hợp lệ** nếu hai context keys khác nhau; đó là chi phí hiệu năng, không phải failure logic. Ngược lại, một container duy nhất nhưng các tests phá dữ liệu của nhau vẫn là thiết kế sai.

## 22. Checklist QA trước khi bật cache/parallel/reuse

- [ ] Đã phân biệt static JUnit `@Container`, Spring context-managed bean, singleton JVM và experimental `withReuse`?
- [ ] Biết chính xác ai `start()` và ai `stop()` container?
- [ ] Nếu dùng Spring TestContext cache, vòng đời backend có ít nhất dài bằng client beans phụ thuộc?
- [ ] `@ServiceConnection` được khai báo trên typed container phù hợp (hoặc đúng name cho generic container)?
- [ ] Không hard-code mapped host port hoặc assume container luôn ở 5432 trên host?
- [ ] Hai test classes có cùng cache key thực, không chỉ giống một tên annotation?
- [ ] Hiểu cache là static per JVM, mặc định max size 32 và LRU eviction?
- [ ] Nếu dùng `@DirtiesContext` có tính tới context/container restarts và parallel hazard?
- [ ] Không dùng `@Container` extension như một lời bảo đảm parallel supported?
- [ ] Biết `@Testcontainers(parallel=true)` không tự biến parallel JUnit tests thành safe?
- [ ] Có seed/cleanup **per test** thay vì `TRUNCATE`/`FLUSHALL`/delete shared index khi có test khác đang chạy?
- [ ] Dữ liệu được đặt namespace theo test/build/worker nếu phải chia sẻ backend?
- [ ] Không dựa vào `@Transactional` rollback khi HTTP/async/REQUIRES_NEW đã commit?
- [ ] Không chia sẻ mutable singleton test fixture/generator giữa concurrent tests?
- [ ] Đã xét Gradle maxParallelForks, JUnit parallel config và CI shards như **ba tầng riêng**?
- [ ] Nếu có `@ResourceLock`, hiểu nó chỉ áp dụng trong JUnit engine/JVM phù hợp?
- [ ] Experimental reuse chỉ được bật dev-local, có host opt-in, `withReuse(true)` và manual start?
- [ ] Không dùng `@Container`/try-with-resources/Spring-managed stop cho experimental reusable container?
- [ ] Không bật experimental reuse trên CI hoặc coi nó là cơ chế database reset?
- [ ] Docker images được pin, memory/CPU/registry/port mapping đủ cho concurrency?
- [ ] Có quan sát `org.springframework.test.context.cache=DEBUG` hoặc metrics phù hợp trước khi kết luận reuse thật sự xảy ra?
- [ ] Không assert test phải chạy theo class order hoặc một container ID cụ thể?
- [ ] Test integration đã chạy trên backend thật và reports phân biệt chưa thực thi với QA chỉ đọc code?

## 23. Chạy bộ ví dụ và đọc kết quả đúng cách

Dùng JDK 17+, Docker daemon hoạt động, Gradle Wrapper có sẵn:

~~~bash
./gradlew test --tests "com.example.containercache.NoteRepositoryAIntegrationTest"
./gradlew test --tests "com.example.containercache.NoteRepositoryBIntegrationTest"
./gradlew test --tests "com.example.containercache.NoteRepository*IntegrationTest"
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.containercache.NoteRepositoryAIntegrationTest"
.\gradlew.bat test --tests "com.example.containercache.NoteRepositoryBIntegrationTest"
.\gradlew.bat test --tests "com.example.containercache.NoteRepository*IntegrationTest"
~~~

Có **4 JUnit test methods**: 3 ở class A và 1 ở class B. Các assertions kỳ vọng PASS khi PostgreSQL container start và SQL initialization thành công. **Đây là kết quả dự kiến sau khi kiểm tra code và tài liệu, không phải log Gradle/Testcontainers/JUnit đã chạy trong lúc soạn**.

Ví dụ không gọi `System.out.println` nên không có stdout cố định do ứng dụng tự in. Gradle/JUnit logs, Docker mapped ports, container IDs và cache hit counts có thể thay đổi theo môi trường. Nếu muốn kiểm tra tối ưu context cache, chạy **cả hai classes trong cùng Gradle invocation** (lệnh thứ ba) và bật DEBUG cache log; đừng đo bằng việc chạy hai lệnh `gradlew test` riêng rồi đòi có shared Spring cache vì mỗi lệnh có thể dùng test JVM khác.

### Nếu muốn thí nghiệm với parallel

Hãy bắt đầu bằng cách giữ JUnit sequential và Gradle maxParallelForks=1 cho integration tests có shared state. Sau khi tách dữ liệu và backend lifecycle, mới bật JUnit classes parallel hoặc chia forks có kiểm soát, theo dõi DB lock waits, memory, Docker resource usage và flaky failures. Nếu có static `@Container` JUnit extension, lưu ý tài liệu Testcontainers **không hỗ trợ chính thức parallel test execution với extension**.

### Kết luận

**Reuse hợp lệ = vòng đời đúng + context key phù hợp + dữ liệu được cô lập.** Spring Boot 3.5 có thể quản lý Testcontainers như Spring beans để chúng sống theo cached ApplicationContext; JUnit static `@Container` có lifecycle khác; experimental `withReuse(true)` là lựa chọn dev-only có thể để lại state xuyên nhiều lần chạy. Không có cơ chế nào trong ba cơ chế này tự bảo đảm tests parallel-safe. Trước khi tối ưu số lần start container, phải kiểm tra cleanup và transaction/isolation, sau đó mới tối ưu cache/reuse bằng số đo thực.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Testcontainers, Spring beans, JUnit extension, service connections, @ImportTestcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html)
- [Testcontainers Java — JUnit Jupiter extension (static/instance lifecycle; parallel limitation)](https://java.testcontainers.org/test_framework_integration/junit_5/)
- [Testcontainers Java — Reusable Containers, experimental](https://java.testcontainers.org/features/reuse/)
- [Testcontainers Java — Custom configuration](https://java.testcontainers.org/features/configuration/)
- [Spring Framework 6.2 — TestContext context caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html)
- [Spring Framework 6.2 — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/parallel-test-execution.html)
- [Spring Framework — Context Failure Threshold](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/failure-threshold.html)
- [JUnit Jupiter — Parallel Test Execution](https://docs.junit.org/current/user-guide/#writing-tests-parallel-execution)