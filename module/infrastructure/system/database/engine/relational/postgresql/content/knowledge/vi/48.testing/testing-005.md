# Kiểm thử tích hợp Java bằng PostgreSQL thật và Testcontainers

Kiểm thử tích hợp database cần xác nhận rằng ứng dụng Java thực sự làm việc đúng với hệ quản trị cơ sở dữ liệu mà production sử dụng. Một test có thể pass với mock repository hoặc H2 nhưng vẫn fail khi chạy trên PostgreSQL vì khác biệt về SQL dialect, kiểu dữ liệu, transaction behavior, constraints, indexes, locking, collation hoặc extension.

**Testcontainers** giải quyết vấn đề này bằng cách khởi chạy PostgreSQL trong container dùng cho test, cung cấp connection details động cho ứng dụng và dọn container sau khi test kết thúc. Test chạy với PostgreSQL server thật, thường dùng đúng major version hoặc image gần production, nhưng vẫn giữ được môi trường test cô lập và có thể tái lập.

Mục tiêu không phải đưa toàn bộ production vào mỗi test. Hãy chọn một database thật, schema được tạo từ migration thật, data fixture nhỏ và các assertion tập trung vào behavior cần xác nhận. Unit tests vẫn dùng mocks khi cần kiểm tra logic thuần; integration tests dùng PostgreSQL thật để kiểm tra đường đi từ Java code qua JDBC/ORM tới database.

~~~text
                  Java integration test
                           |
                           v
                  Testcontainers API
                           |
                           v
                 PostgreSQL container
                           |
             +-------------+-------------+
             |             |             |
             v             v             v
          JDBC/ORM      Migrations    Real SQL behavior
             |             |             |
             +-------------+-------------+
                           |
                           v
                   Assertions in JUnit
                           |
                           v
                 Container is stopped
~~~

Bài học thuộc module **Database Engine Relational PostgreSQL**, chương **Kiểm thử**, với đề tài **“Kiểm thử tích hợp Java bằng PostgreSQL thật và Testcontainers”**.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt unit test, repository test, integration test và end-to-end test.
2. Giải thích vì sao H2 hoặc mock không thay thế hoàn toàn PostgreSQL thật.
3. Mô tả Testcontainers và vai trò của Docker/container runtime.
4. Thêm các dependency Testcontainers cho Java, JUnit 5 và PostgreSQL.
5. Khởi chạy PostgreSQL container bằng PostgreSQLContainer.
6. Lấy JDBC URL, username, password và mapped port động.
7. Quản lý container theo test class hoặc theo từng test method.
8. Viết integration test JDBC không cần Spring.
9. Tích hợp Testcontainers với Spring Boot, DataSource, JdbcTemplate và JPA.
10. Cấu hình datasource bằng DynamicPropertySource hoặc ServiceConnection.
11. Chạy Flyway/Liquibase migrations trên PostgreSQL container.
12. Kiểm thử repositories, constraints, JSONB, UUID, enum, arrays và timestamp behavior.
13. Kiểm tra transaction rollback và hiểu giới hạn của @Transactional trong tests.
14. Cô lập dữ liệu giữa các tests.
15. Chạy tests song song mà không tạo race conditions.
16. Kiểm thử locking, isolation và concurrent updates trên PostgreSQL thật.
17. Dùng init scripts và database fixtures có kiểm soát.
18. Tối ưu tốc độ test bằng image caching, lifecycle phù hợp và suite reuse.
19. Chạy Testcontainers trong CI với Docker daemon.
20. Chẩn đoán lỗi Docker, image pull, startup, readiness, port mapping và connection.
21. Thiết kế test assertions ổn định, không phụ thuộc implementation details.
22. Xây dựng test strategy cho nhiều PostgreSQL versions.
23. Biết khi nào cần container PostgreSQL đơn lẻ, nhiều containers hoặc môi trường dịch vụ tích hợp.
24. Lập checklist và runbook cho integration testing bằng PostgreSQL thật.

**Phạm vi:** Ví dụ sử dụng Java, JUnit 5, Testcontainers và PostgreSQL. Spring Boot được trình bày như một integration phổ biến, nhưng các nguyên tắc cũng áp dụng cho JDBC thuần, jOOQ, MyBatis, Hibernate/JPA và các framework Java khác. Pin phiên bản Java, PostgreSQL image, JDBC driver, Testcontainers và Spring Boot theo compatibility matrix của dự án.

---

## 2. Vì sao cần PostgreSQL thật trong integration tests?

### 2.1. Unit test không kiểm tra database behavior

Một unit test dùng mock repository có thể xác nhận service gọi phương thức save với object đúng. Nó không chứng minh:
- SQL được sinh ra hợp lệ.
- Column mapping chính xác.
- Constraint được áp dụng.
- Transaction thực sự rollback.
- Query hoạt động với PostgreSQL.
- Migration tạo đúng schema.
- Concurrent transactions có behavior mong muốn.

Mock hữu ích để cô lập logic, nhưng không thay thế test với database.

### 2.2. H2 không phải PostgreSQL

H2 có thể chạy embedded hoặc in-memory, giúp test nhanh. Tuy nhiên, PostgreSQL và H2 có khác biệt về:
- SQL dialect và built-in functions.
- JSON/JSONB, arrays, enums, ranges và UUID.
- Identity/sequence semantics.
- Collations và text comparison.
- Date/time types và timezone.
- Partial indexes, expression indexes và exclusion constraints.
- ON CONFLICT, RETURNING và locking.
- Transaction isolation và concurrency behavior.
- Extensions như pgcrypto, PostGIS hoặc pg_trgm.
- Query planner và execution plans.

H2 compatibility mode có thể hỗ trợ một số cú pháp, nhưng không biến H2 thành PostgreSQL.

### 2.3. SQLite cũng không đại diện PostgreSQL

SQLite phù hợp với một số ứng dụng embedded, nhưng có type system, locking, concurrency và SQL behavior khác. Nếu production chạy PostgreSQL, các tests quan trọng về database cần chạy trên PostgreSQL.

### 2.4. Testcontainers cung cấp môi trường thật

Testcontainers khởi chạy container dựa trên image PostgreSQL. Test kết nối tới server thông qua JDBC driver giống cách ứng dụng kết nối production.

### 2.5. Tính tái lập

Test có thể khai báo rõ:
- PostgreSQL image/version.
- Database name.
- Username/password test.
- Init scripts.
- Environment variables.
- Startup configuration.
- Migrations và test data.

Điều này giảm phụ thuộc vào PostgreSQL cài sẵn trên máy developer.

### 2.6. Test thật không có nghĩa test toàn bộ production topology

Một container PostgreSQL đơn lẻ không mô phỏng HA cluster, replication, managed cloud networking, backup service hay production data volume. Những yêu cầu đó cần integration/system tests riêng.

---

## 3. Chọn đúng loại test

| Loại test | Database | Mục đích |
| --- | --- | --- |
| Unit test | Mock hoặc không cần DB | Kiểm tra logic nhỏ, nhanh |
| Repository integration test | PostgreSQL container | Kiểm tra SQL, mapping và repository |
| Application integration test | PostgreSQL container + application context | Kiểm tra service, transaction và wiring |
| API integration test | Ứng dụng chạy cùng PostgreSQL container | Kiểm tra HTTP request tới persistence layer |
| Contract test | PostgreSQL và hệ thống phụ thuộc được mô phỏng có chủ đích | Kiểm tra interface/integration contract |
| End-to-end test | Môi trường gần production | Kiểm tra workflow qua nhiều services |
| Performance/load test | Môi trường có cấu hình và dữ liệu đại diện | Đánh giá latency, throughput và contention |

### 3.1. Không dùng integration test cho mọi method

Một hàm tính phí thuần không cần PostgreSQL container. Unit test cho logic đó sẽ nhanh và dễ chẩn đoán hơn.

### 3.2. Dùng PostgreSQL thật cho behavior phụ thuộc database

Ưu tiên integration tests cho:
- Repository queries phức tạp.
- Custom SQL.
- Migrations.
- Constraints và indexes.
- Transaction boundaries.
- Locking/concurrency.
- Type mappings.
- PostgreSQL extensions.
- Database-specific functions.

### 3.3. Phân lớp test suite

Một dự án có thể tổ chức:
- Unit tests: chạy thường xuyên, không cần Docker.
- Integration tests: dùng PostgreSQL Testcontainers.
- System tests: chạy ứng dụng và các dependencies liên quan.
- Performance tests: chạy riêng với workload/data lớn.

Không nên bắt mọi developer chạy một hệ thống nhiều services khi chỉ sửa một hàm thuần.

---

## 4. Kiến trúc Testcontainers

Testcontainers là thư viện Java điều khiển container runtime để tạo dependencies dùng trong tests.

### 4.1. Các thành phần

| Thành phần | Vai trò |
| --- | --- |
| Container image | PostgreSQL server image |
| Docker/container runtime | Khởi tạo và quản lý container |
| Testcontainers library | Lifecycle, port mapping, wait strategy |
| JUnit 5 extension | Tích hợp start/stop với test lifecycle |
| JDBC driver | Kết nối Java tới PostgreSQL |
| Application/DAO | Code thực tế cần kiểm thử |
| Test fixtures | Schema và dữ liệu test |
| Assertions | Xác nhận behavior |

### 4.2. Lifecycle cơ bản

~~~text
JUnit discovers test class
        |
        v
Testcontainers starts PostgreSQL
        |
        v
Wait until PostgreSQL is ready
        |
        v
Expose mapped host port
        |
        v
Configure JDBC/DataSource
        |
        v
Run migrations and test setup
        |
        v
Execute test methods
        |
        v
Run cleanup callbacks
        |
        v
Stop and remove container
~~~

### 4.3. Port mapping động

Container PostgreSQL lắng nghe port 5432 bên trong container. Testcontainers thường ánh xạ sang một host port động để tránh xung đột với PostgreSQL local hoặc test khác.

Không hard-code localhost:5432. Lấy JDBC URL và credentials từ container object.

### 4.4. Readiness

Container process chạy không có nghĩa PostgreSQL đã sẵn sàng nhận connections. Testcontainers dùng wait strategy để đợi service ready.

### 4.5. Isolation

Container mới tạo ra một database environment mới. Nhưng nếu một container được dùng chung cho nhiều tests, dữ liệu trong database vẫn có thể rò rỉ giữa tests. Isolation còn phụ thuộc cách quản lý schema, transactions và fixtures.

---

## 5. Yêu cầu môi trường

### 5.1. Java

Dùng một JDK được dự án hỗ trợ. Testcontainers Java và Spring Boot có minimum Java versions theo từng release; kiểm tra compatibility matrix của các dependency đang chọn.

### 5.2. Docker hoặc container runtime tương thích

Testcontainers cần kết nối tới container runtime. Trong phần lớn môi trường developer/CI, đó là Docker Engine hoặc Docker Desktop.

Kiểm tra:

~~~bash
docker version
docker info
~~~

Lệnh phải truy cập được daemon, không chỉ hiển thị Docker CLI version.

### 5.3. Maven hoặc Gradle

Project build phải resolve được Testcontainers artifacts và PostgreSQL JDBC driver. Pin version qua BOM hoặc dependency management.

### 5.4. Network và image registry

Lần đầu chạy có thể cần pull PostgreSQL image. CI cần quyền truy cập registry hoặc mirror nội bộ.

### 5.5. Không cần PostgreSQL host installation

Testcontainers sử dụng PostgreSQL image trong container. Developer không bắt buộc phải cài PostgreSQL server trực tiếp trên máy, nhưng cần container runtime.

### 5.6. Resource

Container cần CPU, memory và disk cho image, database files và WAL. Test suite song song có thể khởi chạy nhiều containers và làm cạn tài nguyên.

---

## 6. Thêm dependency với Maven

Testcontainers có nhiều modules. Với PostgreSQL và JUnit 5, cần module PostgreSQL cùng JUnit Jupiter integration.

### 6.1. Quản lý version bằng BOM

~~~xml
<properties>
    <testcontainers.version>YOUR_TESTCONTAINERS_VERSION</testcontainers.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>testcontainers-bom</artifactId>
            <version>YOUR_TESTCONTAINERS_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Thay placeholder bằng version được dự án chọn. BOM giúp các Testcontainers modules dùng versions tương thích nhau.

### 6.2. PostgreSQL module

~~~xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
~~~

### 6.3. JUnit Jupiter module

~~~xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
~~~

### 6.4. PostgreSQL JDBC driver

~~~xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
~~~

Nếu application đã có PostgreSQL driver ở compile/runtime scope, không cần khai báo duplicate chỉ để test. Bảo đảm test runtime có driver.

### 6.5. JUnit 5

Dùng JUnit Jupiter API/engine và Surefire/Failsafe versions tương thích với build. Spring Boot starter test thường cung cấp JUnit Jupiter cho ứng dụng Spring Boot.

### 6.6. Dependency scopes

- Testcontainers modules: test scope.
- PostgreSQL JDBC driver: runtime/compile nếu ứng dụng cần; test scope nếu chỉ integration tests cần.
- JUnit: test scope.
- Flyway/Liquibase: application dependency nếu production sử dụng migrations, test phải chạy đúng migration engine đó.

### 6.7. Tránh trộn Testcontainers major versions

Không khai báo các modules với versions rời rạc không tương thích. Dùng BOM hoặc version catalog.

---

## 7. Thêm dependency với Gradle

### 7.1. Groovy DSL

~~~groovy
dependencies {
    testImplementation platform("org.testcontainers:testcontainers-bom:YOUR_TESTCONTAINERS_VERSION")
    testImplementation "org.testcontainers:postgresql"
    testImplementation "org.testcontainers:junit-jupiter"

    testImplementation "org.postgresql:postgresql"
}
~~~

Thay placeholder bằng version đã pin trong dự án.

### 7.2. Kotlin DSL

~~~kotlin
dependencies {
    testImplementation(platform("org.testcontainers:testcontainers-bom:YOUR_TESTCONTAINERS_VERSION"))
    testImplementation("org.testcontainers:postgresql")
    testImplementation("org.testcontainers:junit-jupiter")

    testImplementation("org.postgresql:postgresql")
}
~~~

### 7.3. Version catalog

Có thể khai báo version trong gradle/libs.versions.toml và tham chiếu từ build files. Mục tiêu là một nguồn version duy nhất cho toàn bộ modules.

### 7.4. Chạy test

~~~bash
./gradlew test
~~~

Nếu integration tests được tách thành source set/task riêng, chạy task đó theo convention của project.

### 7.5. Dependency verification

Kiểm tra dependency tree khi gặp NoSuchMethodError, NoClassDefFoundError hoặc version conflict. Đặc biệt tránh một module Testcontainers bị kéo vào với version khác BOM.

---

## 8. Tạo PostgreSQL container bằng JUnit 5

Đây là ví dụ tối thiểu cho một integration test dùng JDBC trực tiếp.

### 8.1. Test class

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Testcontainers
class PostgreSqlSmokeIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("app_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @Test
    void connectsToRealPostgreSql() throws Exception {
        try (Connection connection = DriverManager.getConnection(
                postgres.getJdbcUrl(),
                postgres.getUsername(),
                postgres.getPassword());
             Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery("SELECT 1")) {

            result.next();
            assertEquals(1, result.getInt(1));
        }
    }
}
~~~

Image tag chỉ mang tính minh họa. Với CI/release pipeline, pin PostgreSQL patch version hoặc image digest theo policy của dự án.

### 8.2. @Testcontainers

Annotation này bật JUnit Jupiter extension của Testcontainers. Extension quản lý lifecycle cho fields có @Container.

### 8.3. @Container static

Static container được start một lần cho test class và stop sau class. Đây là lựa chọn phổ biến để giảm startup time khi nhiều methods dùng chung database environment.

### 8.4. @Container instance

Nếu container field không static, extension khởi chạy và dừng container theo từng test method. Isolation cao hơn nhưng startup overhead lớn hơn.

### 8.5. PostgreSQLContainer

PostgreSQLContainer cung cấp các phương thức như:
- getJdbcUrl().
- getUsername().
- getPassword().
- getHost().
- getMappedPort(5432).

Dùng các giá trị do container cung cấp; mapped port có thể khác nhau giữa các runs.

### 8.6. try-with-resources

Đóng JDBC Connection, Statement và ResultSet để tránh leak resources. Container lifecycle không tự đóng các JDBC objects do test tạo.

### 8.7. Không dùng fixed host port

Không cấu hình host port 5432 cố định nếu không có yêu cầu đặc biệt. Dynamic mapping giúp tránh xung đột và hỗ trợ chạy nhiều tests.

---

## 9. Container lifecycle: static, instance và singleton

Lựa chọn lifecycle ảnh hưởng tốc độ và mức độ cô lập.

### 9.1. Static @Container

Ưu điểm:
- Một lần khởi động cho cả test class.
- Nhiều methods dùng cùng database instance.
- Phù hợp repository test class có fixture/cleanup rõ ràng.

Nhược điểm:
- Data có thể tồn tại giữa methods.
- Parallel methods có thể tranh chấp dữ liệu.
- Container dừng khi class kết thúc.

### 9.2. Instance @Container

Ưu điểm:
- Mỗi test method có database container mới.
- Isolation tốt và ít phụ thuộc cleanup.
- Dễ test behavior cần database state trống.

Nhược điểm:
- Startup/stop overhead cao.
- Pull image hoặc initialize database có thể tốn thời gian.
- Nhiều methods có thể tiêu thụ CPU/RAM đáng kể.

### 9.3. Singleton container pattern

Một số dự án dùng static singleton được start thủ công để chia sẻ PostgreSQL giữa nhiều test classes. Cách này có thể giảm thời gian startup nhưng cần quản lý lifecycle rõ ràng.

Nếu dùng singleton:
- Không để tests phụ thuộc thứ tự.
- Cleanup hoặc schema isolation sau từng test.
- Đảm bảo container không bị extension dừng giữa suite.
- Tránh xung đột với parallel execution.
- Có một owner rõ ràng cho startup/shutdown.

### 9.4. Spring context caching

Spring TestContext có thể cache ApplicationContext giữa các test classes. Nếu container static do JUnit extension quản lý dừng sau class đầu tiên nhưng context vẫn được tái sử dụng, class tiếp theo có thể dùng datasource trỏ tới container đã dừng.

Giải pháp có thể gồm:
- Một shared container sống lâu hơn các test classes.
- Quản lý container theo Spring context lifecycle.
- Dùng ServiceConnection/DynamicPropertySource cùng một lifecycle strategy rõ ràng.
- Không kết hợp lifecycle annotations theo cách khiến context outlive container.

### 9.5. Không mặc định reusable containers trong CI

Reusable containers có thể hữu ích cho local development nhưng giữ container giữa các test runs làm tăng nguy cơ state leakage. Không bật reuse trong CI nếu không có thiết kế cleanup và isolation được kiểm soát.

### 9.6. Chọn lifecycle theo test scope

| Nhu cầu | Cách thường phù hợp |
| --- | --- |
| Một smoke test đơn giản | Instance container |
| Nhiều repository methods cùng class | Static @Container + cleanup |
| Nhiều Spring test classes, context cached | Shared lifecycle được thiết kế rõ |
| Parallel tests cần isolation mạnh | Container/schema/database riêng theo worker |
| Suite dài và startup đắt | Suite-scoped container + deterministic cleanup |

---

## 10. Cấu hình container và PostgreSQL image

### 10.1. Chọn image

~~~java
new PostgreSQLContainer<>("postgres:16-alpine")
~~~

Chọn image có:
- PostgreSQL major version tương ứng production.
- Patch version được pin khi cần deterministic builds.
- Architecture phù hợp CI runners.
- Extension packages cần thiết nếu tests dùng extensions.

### 10.2. Không dùng latest cho integration tests ổn định

latest có thể thay đổi bất ngờ. Một lần CI chạy hôm nay và tuần sau có thể dùng PostgreSQL version khác mà không có code change.

### 10.3. Image digest

Với môi trường cần reproducibility cao, có thể pin image digest thay vì chỉ tag. Quy trình cập nhật digest nên có review và test.

### 10.4. Database name và credentials

~~~java
PostgreSQLContainer<?> postgres =
    new PostgreSQLContainer<>("postgres:16-alpine")
        .withDatabaseName("orders_test")
        .withUsername("test_user")
        .withPassword("test_password");
~~~

Credentials test chỉ dùng trong environment disposable. Không dùng production secrets.

### 10.5. Environment variables

PostgreSQL official image sử dụng biến như POSTGRES_DB, POSTGRES_USER và POSTGRES_PASSWORD. PostgreSQLContainer thường cấu hình các biến tương ứng thông qua builder methods.

### 10.6. Command và configuration

Có thể tùy chỉnh server command, environment hoặc mount config file khi test cần:
- shared_preload_libraries.
- TimeZone.
- max_connections.
- logging.
- Extensions.
- Replication settings.

Không tùy chỉnh quá nhiều nếu behavior cần test có thể được xác nhận bằng PostgreSQL defaults gần production.

### 10.7. Startup timeout

Database image có thể cần thời gian initialize data directory. Nếu startup timeout, xem logs và resource usage trước khi tăng timeout vô hạn.

### 10.8. Readiness

Dùng wait strategy của PostgreSQLContainer hoặc strategy phù hợp. Không dùng Thread.sleep cố định để đoán PostgreSQL đã ready.

---

## 11. JDBC connection và cấu hình động

### 11.1. JDBC URL

postgres.getJdbcUrl() trả URL có host và mapped port phù hợp với runtime hiện tại.

### 11.2. Không hard-code localhost

Không giả định Docker host là localhost trong mọi môi trường. Testcontainers hỗ trợ các runtime/host mappings khác nhau. Dùng getJdbcUrl().

### 11.3. JDBC properties

Nếu ứng dụng cần SSL, application_name, connectTimeout hoặc socketTimeout, cấu hình JDBC properties phù hợp. Test environment nên phản ánh những properties cần xác minh.

### 11.4. Connection pool

Nếu dùng HikariCP hoặc pool khác, đảm bảo pool được tạo sau khi container sẵn sàng và được đóng khi test context kết thúc.

### 11.5. Pool cleanup

Pool giữ connection tới container. Nếu container dừng trước pool, test teardown có thể báo lỗi close/connection. Lifecycle order cần bảo đảm datasource/pool đóng trước container.

### 11.6. Test connection

Có thể chạy SELECT 1 hoặc query vào pg_catalog để xác nhận server version:

~~~sql
SELECT current_database(), current_user, version();
~~~

### 11.7. Kiểm tra PostgreSQL major

Test có thể assert server version major phù hợp để tránh image tag/config drift. Không assert full version string nếu patch updates được phép.

---

## 12. Integration test với Spring Boot

Spring Boot có thể tự cấu hình DataSource từ properties được cung cấp bởi Testcontainers.

### 12.1. Dependencies

Ngoài PostgreSQL/JUnit Testcontainers modules, cần Spring Boot test support. Với ServiceConnection, thêm Spring Boot Testcontainers module tương ứng version Boot.

Ví dụ Maven:

~~~xml
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
~~~

### 12.2. DynamicPropertySource

Cách này truyền container properties vào Spring Environment:

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
class OrderRepositoryIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("orders_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Test
    void contextStartsWithPostgres() {
        // Inject repository or JdbcTemplate and exercise real database.
    }
}
~~~

### 12.3. DynamicPropertySource

Method phải static và đăng ký property suppliers. Supplier được lấy khi Spring tạo context. Đây là cách linh hoạt để truyền URL/credentials động.

### 12.4. ServiceConnection

Với Spring Boot versions hỗ trợ ServiceConnection (từ Spring Boot 3.1), có thể dùng annotation để Boot tự nhận diện container connection details:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class OrderServiceIT {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

Cần dependency spring-boot-testcontainers và phiên bản Boot có hỗ trợ. Kiểm tra package/import theo Boot version đang dùng.

### 12.5. Chọn một cách cấu hình rõ ràng

DynamicPropertySource phù hợp khi cần tự map nhiều properties hoặc dùng Spring Boot version cũ hơn. ServiceConnection giảm boilerplate trên Boot mới. Tránh cấu hình hai nguồn khác nhau cùng ghi datasource properties mà không rõ precedence.

### 12.6. Repository injection

~~~java
@SpringBootTest
class OrderRepositoryIT {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void savesAndLoadsOrder() {
        // Use repository backed by PostgreSQL container.
    }
}
~~~

Phần container setup có thể đặt trong cùng class hoặc base/configuration class có lifecycle phù hợp.

### 12.7. JdbcTemplate

~~~java
@Autowired
JdbcTemplate jdbcTemplate;

@Test
void databaseIsPostgres() {
    String database = jdbcTemplate.queryForObject(
        "select current_database()",
        String.class
    );

    assertEquals("orders_test", database);
}
~~~

### 12.8. JPA/Hibernate

Nếu dùng JPA:
- Đặt dialect/driver theo Spring Boot auto-configuration.
- Chạy migrations trước repository tests.
- Không để Hibernate ddl-auto=create-drop che mất lỗi migration.
- Dùng cùng schema strategy với production.
- Kiểm tra generated SQL và mappings với PostgreSQL thật.

---

## 13. Chạy migrations trong container

Một integration test có giá trị phải xác nhận schema có thể được tạo từ migration thật.

### 13.1. Flyway

Nếu production dùng Flyway, hãy để Spring Boot hoặc Flyway migrate PostgreSQL container khi context khởi động.

Ví dụ cấu hình test:
~~~properties
spring.flyway.enabled=true
spring.jpa.hibernate.ddl-auto=validate
~~~

Đặt migration scripts trong location mà application thực sự sử dụng.

### 13.2. Liquibase

Nếu production dùng Liquibase, chạy changelog trên PostgreSQL container thay vì tạo schema riêng bằng Hibernate.

### 13.3. Không dùng schema giả thay migrations

Nếu test tự tạo table thủ công nhưng production dùng Flyway, tests có thể pass dù migration bị lỗi hoặc thiếu index/constraint.

### 13.4. Migration from empty database

Một test quan trọng là tạo database mới hoàn toàn và chạy tất cả migrations từ version đầu. Nó phát hiện:
- Migration thiếu dependency.
- SQL syntax không tương thích.
- Object order sai.
- Duplicate names.
- Constraint/data conversion lỗi.
- Migration phụ thuộc state tồn tại từ môi trường developer.

### 13.5. Upgrade path test

Nếu dự án có nhiều versions đã deploy, cần test cả:
- Fresh install tới latest schema.
- Nâng từ một schema version được hỗ trợ tới latest.
- Data transformations với fixture đại diện.

### 13.6. Migration transaction semantics

Một số DDL/maintenance commands không chạy trong transaction block. Migration framework phải hỗ trợ non-transactional migration khi cần, ví dụ CREATE INDEX CONCURRENTLY. Kiểm thử migration thật sẽ phát hiện framework bọc transaction sai.

### 13.7. Test extension

Nếu migration cài pgcrypto, PostGIS hoặc extension khác, PostgreSQL image cần package tương ứng. Official postgres image cơ bản không đảm bảo có mọi extension ngoài core/contrib package của image đó.

---

## 14. Init scripts và seed data

### 14.1. Init script

PostgreSQLContainer hỗ trợ withInitScript để chạy SQL script trong quá trình khởi tạo database:

~~~java
static final PostgreSQLContainer<?> postgres =
    new PostgreSQLContainer<>("postgres:16-alpine")
        .withInitScript("db/test-init.sql");
~~~

Script path được tìm trong test classpath theo cơ chế Testcontainers.

### 14.2. Init script phù hợp với gì?

- Tạo roles phụ cho lab.
- Cài extension có trong image.
- Tạo remote fixture đơn giản.
- Chuẩn bị database settings cần thiết.
- Tạo dữ liệu nền nhỏ.

### 14.3. Migrations và init script có vai trò khác

Init script là setup của container. Migration là schema evolution của ứng dụng. Không chuyển toàn bộ production migrations thành init script chỉ để test chạy nhanh.

### 14.4. Data fixtures

Dùng fixtures nhỏ, deterministic và dễ hiểu. Tránh phụ thuộc vào ID sequence cố định nếu test có thể chạy song song hoặc dùng shared database.

### 14.5. SQL script encoding

Lưu script UTF-8 và kiểm tra locale/encoding của database. Dữ liệu Unicode nên được test rõ ràng nếu ứng dụng có nội dung đa ngôn ngữ.

### 14.6. Programmatic setup

Có thể dùng JdbcTemplate, repository hoặc SQL script để tạo test data trong @BeforeEach. Chọn một cơ chế nhất quán và cleanup tương ứng.

---

## 15. Kiểm thử repository với PostgreSQL thật

### 15.1. Mục tiêu

Repository test cần kiểm tra contract giữa Java persistence code và PostgreSQL:
- Insert/update/delete.
- Query predicates.
- Joins và projections.
- Pagination/sorting.
- Null handling.
- Unique/FK/check constraints.
- Type conversion.
- Transaction behavior.

### 15.2. Ví dụ repository

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    @Query("""
        select c
        from Customer c
        where c.status = :status
        order by c.createdAt desc
    """)
    List<Customer> findRecentByStatus(
        @Param("status") CustomerStatus status
    );
}
~~~

### 15.3. Test behavior, không test implementation

~~~java
@Test
void findsCustomerByEmail() {
    Customer customer = new Customer(
        "reader@example.test",
        "Reader"
    );

    customerRepository.saveAndFlush(customer);

    Optional<Customer> found =
        customerRepository.findByEmail("reader@example.test");

    assertTrue(found.isPresent());
    assertEquals("Reader", found.orElseThrow().getName());
}
~~~

Ví dụ cần entity constructors/mappings phù hợp dự án.

### 15.4. flush để phát hiện lỗi database

JPA có thể trì hoãn SQL tới flush/commit. Nếu chỉ assert entity trong persistence context, test có thể không thực sự gửi SQL tới PostgreSQL.

Dùng saveAndFlush hoặc EntityManager.flush khi cần xác nhận constraint, generated values hoặc SQL execution.

### 15.5. clear persistence context

Sau khi ghi, EntityManager có thể trả object đã cache. Dùng flush + clear rồi đọc lại để xác nhận schema/database round trip thay vì chỉ đọc lại cùng managed entity.

### 15.6. JdbcTemplate test

Với SQL tùy chỉnh, JdbcTemplate có thể kiểm tra trực tiếp:
- JSONB operators.
- RETURNING.
- PostgreSQL casts.
- CTEs.
- Window functions.
- Partial-index-dependent query.
- Advisory locks.

### 15.7. Kiểm tra exception

Khi test unique/FK violation, assert exception type/SQLSTATE ở boundary phù hợp. ORM có thể wrap SQLException trong DataIntegrityViolationException hoặc PersistenceException.

---

## 16. Kiểm thử PostgreSQL-specific features

PostgreSQL thật đặc biệt hữu ích khi ứng dụng dùng các tính năng không được H2 mô phỏng đầy đủ.

### 16.1. JSONB

Test:
- Insert/read JSONB.
- JSON path/operators.
- Containment.
- Null/missing key behavior.
- GIN index nếu query cần.
- Mapping JSON giữa Java object và PostgreSQL.

### 16.2. UUID

Test UUID generation, JDBC mapping, parameter binding và index lookups.

### 16.3. Arrays

Test mapping Java collections/arrays sang PostgreSQL arrays, NULL elements và operators như ANY/ALL nếu ứng dụng dùng.

### 16.4. Enums

Test mapping Java enum với PostgreSQL enum hoặc text/varchar representation. Kiểm tra migration khi thêm label và application compatibility.

### 16.5. Range và multirange

Nếu dùng daterange, int4range, tstzrange hoặc custom range, test bounds, empty ranges, overlaps và operators trên PostgreSQL.

### 16.6. Generated identity và sequences

Test generated IDs, sequence behavior, rollback gaps và batch inserts. Không assert rằng sequence luôn liên tục.

### 16.7. Partial và expression indexes

Test query behavior và uniqueness với indexes có WHERE predicate hoặc indexed expressions.

### 16.8. Exclusion constraints

Test constraint ngăn overlapping intervals hoặc conflicts theo operator classes. H2 không thay thế được behavior PostgreSQL-specific này.

### 16.9. Extensions

Nếu ứng dụng phụ thuộc pgcrypto, PostGIS, pg_trgm hoặc extension khác, dùng image có package tương ứng và cài extension trong test database.

### 16.10. Collation và locale

Test sort/equality cho dữ liệu đa ngôn ngữ khi ứng dụng phụ thuộc locale. Chọn image/OS/ICU tương thích production nếu semantics quan trọng.

---

## 17. Transaction testing

Transaction tests dễ tạo false confidence nếu không hiểu Spring/JPA/connection lifecycle.

### 17.1. @Transactional test

Spring test có thể mở transaction trước test và rollback sau test. Điều này giúp cleanup dữ liệu được ghi qua transaction tham gia cùng test context.

### 17.2. Ví dụ

~~~java
@SpringBootTest
@Transactional
class CustomerRepositoryIT {

    @Autowired
    CustomerRepository repository;

    @Test
    void savesCustomer() {
        repository.saveAndFlush(
            new Customer("a@example.test", "A")
        );

        assertTrue(repository.findByEmail("a@example.test").isPresent());
    }
}
~~~

### 17.3. Rollback chỉ áp dụng transaction tương ứng

Rollback test transaction không tự hoàn tác:
- HTTP request chạy ở server thread khác.
- @Async task.
- Transaction REQUIRES_NEW.
- Connection độc lập do code tự mở.
- Background worker.
- External service side effects.
- Sequence increments.

### 17.4. Test commit behavior

Một test luôn rollback có thể không kiểm tra được behavior xảy ra sau commit. Cần test riêng khi ứng dụng phụ thuộc deferred constraints, after-commit events, transaction synchronization hoặc visibility giữa connections.

### 17.5. Deferred constraints

Một số constraints được kiểm tra cuối transaction. Dùng flush có thể chưa kích hoạt deferred constraint nếu transaction chưa commit. Thiết kế test thực hiện commit/transaction boundary thật để xác nhận.

### 17.6. Isolation levels

PostgreSQL hỗ trợ READ COMMITTED, REPEATABLE READ và SERIALIZABLE. Test concurrency nên mở nhiều connections/transactions thực sự và xác nhận outcome/SQLSTATE theo isolation level.

### 17.7. Không giả định test method luôn có một connection

Connection pool và ORM có thể lấy/trả connection khác nhau. Nếu test cần giữ session-level state hoặc advisory lock, xác định connection lifecycle rõ.

---

## 18. Cô lập dữ liệu giữa tests

Một container mới không đảm bảo mọi test trong container dùng dữ liệu sạch. Cần chiến lược isolation.

### 18.1. Rollback transaction

Phù hợp với test đồng bộ mà mọi thao tác database tham gia cùng transaction.

### 18.2. DELETE/TRUNCATE cleanup

Có thể xóa rows sau mỗi test. Cần chú ý:
- Foreign key dependencies.
- Identity/sequence reset.
- Triggers.
- Table ownership.
- Concurrent test interference.

### 18.3. TRUNCATE ... RESTART IDENTITY CASCADE

~~~sql
TRUNCATE TABLE
    order_item,
    customer_order,
    customer
RESTART IDENTITY CASCADE;
~~~

Chỉ dùng khi test database disposable và danh sách tables được kiểm soát. CASCADE có thể xóa dữ liệu nhiều bảng phụ thuộc.

### 18.4. Database/schema riêng

Mỗi test suite hoặc worker có thể dùng database/schema riêng. Cách này tăng isolation nhưng cần tạo/drop và cấu hình search_path/DataSource cẩn thận.

### 18.5. Container riêng

Mỗi test method có container riêng là isolation mạnh, nhưng chi phí startup cao. Dùng cho tests nhạy cảm với global database state hoặc migrations destructive.

### 18.6. Unique test data

Dùng IDs/emails/names duy nhất để giảm xung đột. Đừng dựa vào dữ liệu còn lại từ test trước.

### 18.7. Test độc lập

Mỗi test phải tự tạo prerequisites và có thể chạy riêng. Không phụ thuộc execution order hoặc dữ liệu do test khác để lại.

### 18.8. Cleanup sau failure

Nếu test fail trước cleanup, suite sau không nên bị ảnh hưởng. Ưu tiên transaction rollback, per-test schema/database hoặc teardown trong finally/afterEach.

---

## 19. Parallel test execution

Chạy tests song song có thể giảm tổng thời gian nhưng làm tăng nguy cơ contention.

### 19.1. Shared static container

Nhiều tests có thể cùng kết nối một PostgreSQL container. Nếu chúng dùng chung tables/data, race conditions có thể xảy ra.

### 19.2. JUnit parallel execution

Testcontainers JUnit Jupiter extension có các giới hạn về parallel execution; không nên bật parallel tests một cách mù quáng khi dùng extension lifecycle mặc định. Đọc tài liệu phiên bản Testcontainers đang dùng và thiết kế container ownership rõ ràng.

### 19.3. Isolation strategies

- Container riêng cho worker/test class.
- Database riêng cho mỗi worker.
- Schema riêng với search_path riêng.
- Fixture keys duy nhất.
- Không dùng shared mutable rows.
- Giới hạn test parallelism theo DB capacity.

### 19.4. Advisory locks

Có thể dùng advisory locks để điều phối tests chia sẻ tài nguyên, nhưng lock keys phải unique và lock lifecycle rõ ràng. Đây không phải thay thế data isolation.

### 19.5. Connection pool sizing

Nhiều Spring contexts cùng tạo Hikari pools có thể mở rất nhiều connections. Giảm maximumPoolSize trong test hoặc giảm parallel workers.

### 19.6. CI workers

Nếu build chạy trên nhiều agents, mỗi agent nên có container/database namespace độc lập. Không trỏ nhiều agents vào cùng một PostgreSQL test service có state dùng chung.

---

## 20. Kiểm thử concurrency và locking

PostgreSQL thật cho phép test các tình huống mà in-memory database không mô phỏng chính xác.

### 20.1. Optimistic locking

Dùng version column trong JPA hoặc SQL condition để phát hiện lost update. Test hai transactions cùng sửa một row và xác nhận một transaction bị conflict.

### 20.2. Pessimistic locking

Test SELECT FOR UPDATE, lock waits và timeout bằng hai connections. Dùng latches/barriers để điều khiển thứ tự thay vì Thread.sleep tùy tiện.

### 20.3. Unique constraint dưới concurrency

Hai transactions cùng insert một key duy nhất. Test phải xác nhận chỉ một transaction commit và transaction còn lại nhận unique violation hoặc kết quả nghiệp vụ tương ứng.

### 20.4. Deadlock

Deadlock tests cần điều phối thứ tự lock có chủ đích, timeout giới hạn và cleanup. Không dùng timing ngẫu nhiên làm test chính.

### 20.5. Serialization failure

Với SERIALIZABLE, test có thể nhận SQLSTATE 40001. Application cần retry toàn transaction theo policy, không chỉ retry statement cuối.

### 20.6. Lock timeout

Cấu hình lock_timeout ngắn trong test để không treo suite. Assert SQLSTATE hoặc exception mapping ở tầng phù hợp.

### 20.7. Không assert execution plan tuyệt đối

Planner có thể chọn plan khác theo PostgreSQL patch version, statistics và data volume. Test semantics là chính; plan assertions chỉ nên kiểm tra đặc tính ổn định có chủ đích.

---

## 21. Test schema migrations

Migrations là một trong những lý do mạnh nhất để dùng PostgreSQL thật.

### 21.1. Fresh schema test

Tạo database trống, chạy toàn bộ migrations, sau đó kiểm tra:
- Tables/columns.
- Primary/foreign keys.
- Unique/check constraints.
- Indexes.
- Functions/triggers.
- Extensions.
- Views/materialized views.
- Grants/owners.
- Migration history.

### 21.2. Upgrade test

Tạo schema ở một version cũ bằng migrations cũ, insert representative data rồi chạy migration mới. Xác nhận dữ liệu cũ được giữ và transform đúng.

### 21.3. Non-transactional migrations

CREATE INDEX CONCURRENTLY không được chạy trong transaction block. Kiểm tra migration tool có cấu hình non-transactional migration và recovery behavior.

### 21.4. Extension availability

Container image phải chứa package extension. CREATE EXTENSION trong migration sẽ fail nếu control files/library không có.

### 21.5. Migration history

Kiểm tra schema history table chỉ ghi success khi migration hoàn thành. Test failure path để xác nhận tool không đánh dấu migration failed thành applied.

### 21.6. Không chỉ test Hibernate DDL

Nếu production schema do Flyway/Liquibase quản lý, hãy chạy đúng migration engine. Hibernate create-drop có thể che lỗi migration scripts.

---

## 22. Kiểm thử bằng JDBC thuần

Không cần Spring để sử dụng Testcontainers.

### 22.1. Data access object

~~~java
public final class CustomerDao {
    private final DataSource dataSource;

    public CustomerDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void insert(long id, String email) throws SQLException {
        String sql = """
            INSERT INTO customer (id, email)
            VALUES (?, ?)
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);
            statement.setString(2, email);
            statement.executeUpdate();
        }
    }

    public Optional<String> findEmail(long id) throws SQLException {
        String sql = "SELECT email FROM customer WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);

            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    return Optional.empty();
                }
                return Optional.of(result.getString("email"));
            }
        }
    }
}
~~~

### 22.2. Test với container

~~~java
@Testcontainers
class CustomerDaoIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    private CustomerDao dao;

    @BeforeEach
    void setUp() throws SQLException {
        PGSimpleDataSource dataSource = new PGSimpleDataSource();
        dataSource.setURL(postgres.getJdbcUrl());
        dataSource.setUser(postgres.getUsername());
        dataSource.setPassword(postgres.getPassword());

        try (Connection connection = dataSource.getConnection();
             Statement statement = connection.createStatement()) {
            statement.execute("""
                CREATE TABLE IF NOT EXISTS customer (
                    id BIGINT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE
                )
                """);
        }

        dao = new CustomerDao(dataSource);
    }

    @Test
    void insertsAndReadsCustomer() throws SQLException {
        dao.insert(1L, "a@example.test");

        assertEquals(
            Optional.of("a@example.test"),
            dao.findEmail(1L)
        );
    }
}
~~~

Ví dụ cần PostgreSQL JDBC driver trong test runtime. Với suite thực tế, migrations/fixtures nên được quản lý tập trung thay vì tạo schema ad hoc trong mỗi method.

### 22.3. PreparedStatement

Dùng bind parameters cho values. Không nối user input vào SQL. Table/column identifiers không thể bind như values; nếu phải dynamic, validate allowlist và quote identifiers đúng cách.

### 22.4. Connection lifecycle

Mỗi DAO method có thể mở connection riêng. Khi test kiểm tra transaction xuyên nhiều operations, truyền connection/transaction context phù hợp thay vì để mỗi method tự mở connection độc lập.

---

## 23. Kiểm thử với jOOQ, MyBatis và Hibernate

### 23.1. jOOQ

PostgreSQL container giúp kiểm tra generated SQL, record mapping, JSONB/array types, stored functions và dialect-specific features. Dùng cùng jOOQ SQL dialect như production.

### 23.2. MyBatis

Test mapper XML/annotations trên PostgreSQL thật để phát hiện SQL syntax, resultMap, typeHandler và parameter binding issues.

### 23.3. Hibernate/JPA

Test entity mapping, schema validation, native queries, fetch joins, lazy loading, locking và transaction behavior.

### 23.4. Custom type handlers

Nếu dùng PostgreSQL enum/JSONB/array/range với custom Hibernate Types hoặc JDBC TypeHandler, test round-trip từ Java object tới PostgreSQL và trở lại.

### 23.5. Không chỉ test save/load đơn giản

Các lỗi thường nằm ở:
- Native SQL.
- Pagination.
- Batch operations.
- Bulk updates.
- Null values.
- Timezone conversion.
- JSON serialization.
- Enum mapping.
- Transaction propagation.

---

## 24. Test PostgreSQL extensions

### 24.1. Extension package phải có trong image

CREATE EXTENSION chỉ hoạt động nếu server image có extension control files, SQL scripts và shared library cần thiết.

### 24.2. Custom image

Nếu base image thiếu extension, tạo image test từ PostgreSQL image phù hợp và cài package extension tương ứng. Pin base image và package versions.

### 24.3. Init extension

Có thể cài extension bằng init script hoặc migration. Production path nào được dùng thì test path đó.

### 24.4. Ví dụ pgcrypto

~~~sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;

SELECT encode(digest('test', 'sha256'), 'hex');
~~~

### 24.5. PostGIS

Với PostGIS, dùng image PostgreSQL có PostGIS version tương thích hoặc build image riêng. Kiểm tra geometry/geography operations và spatial indexes.

### 24.6. Extension version

Ghi rõ PostgreSQL image và extension versions. Một test chỉ chạy trên latest extension không đảm bảo production version cũ tương thích.

### 24.7. Managed service differences

Managed PostgreSQL có extension allowlist và server settings riêng. Testcontainer image không mô phỏng mọi giới hạn provider; cần contract tests hoặc staging trên provider khi feature phụ thuộc managed service.

---

## 25. Wait strategies và startup reliability

### 25.1. Không dùng Thread.sleep

Một sleep cố định có thể:
- Quá ngắn trên CI chậm.
- Lãng phí thời gian trên máy nhanh.
- Không phát hiện startup failure đúng nguyên nhân.

### 25.2. Wait strategy

Testcontainers dùng wait strategies để chờ container đạt trạng thái sẵn sàng. PostgreSQLContainer đã cung cấp defaults phù hợp cho PostgreSQL image thông thường.

### 25.3. Custom wait

Nếu custom image có startup scripts hoặc entrypoint riêng, có thể cấu hình wait strategy dựa trên listening port, healthcheck hoặc log message. Đảm bảo điều kiện phản ánh readiness thật, không chỉ process existence.

### 25.4. Startup timeout

Tăng timeout chỉ khi có bằng chứng startup cần lâu hơn, ví dụ initialization dataset lớn hoặc CI resource yếu. Trước tiên xem container logs.

### 25.5. Database initialization

PostgreSQL official image chỉ chạy init scripts trong lần initialize data directory. Nếu mount volume cũ, init scripts có thể không chạy lại. Container disposable thông thường tạo data directory mới.

### 25.6. Chẩn đoán startup logs

Nếu container exit:
- Kiểm tra image pull.
- Environment variables.
- Permissions/volume mounts.
- Architecture mismatch.
- Port/daemon availability.
- PostgreSQL logs.
- Disk/memory limits.

---

## 26. CI pipeline với Testcontainers

### 26.1. Docker daemon phải sẵn sàng

CI runner cần Docker/container runtime mà Testcontainers có thể truy cập. Chỉ cài Docker CLI là chưa đủ.

### 26.2. Runner types

Các runner có thể khác nhau:
- Linux runner với Docker Engine.
- Self-hosted runner.
- Docker-in-Docker.
- Remote Docker daemon.
- Kubernetes-based runner.
- Windows/macOS runner.

Cấu hình socket, permissions và network tùy môi trường.

### 26.3. Build pipeline

Một pipeline cơ bản:
1. Checkout source.
2. Cài JDK.
3. Resolve dependencies.
4. Khởi chạy unit tests.
5. Khởi chạy integration tests; Testcontainers pull/start PostgreSQL.
6. Thu test reports và container logs khi fail.
7. Build artifact nếu test pass.

### 26.4. Không cần PostgreSQL host tĩnh nếu Testcontainers tự tạo

Testcontainers có thể tạo database environment cho từng test run. CI không nhất thiết cần khai báo một PostgreSQL service cố định bên ngoài.

### 26.5. Khi dùng CI service database

Nếu organization không cho Docker-in-Docker hoặc không hỗ trợ Testcontainers, có thể dùng PostgreSQL service do CI cung cấp. Tuy nhiên, lúc đó cần quản lý port, credentials, lifecycle và cleanup thủ công.

### 26.6. Image caching

CI có thể cache container images hoặc dùng registry mirror để giảm pull time. Cache phải theo image digest/tag đã pin.

### 26.7. Parallel builds

Giới hạn số test workers để không khởi chạy quá nhiều PostgreSQL containers cùng lúc. Theo dõi CPU, RAM và disk.

### 26.8. Artifact khi fail

Thu thập:
- JUnit XML reports.
- Test logs.
- PostgreSQL container logs.
- Application logs.
- Build/dependency versions.
- Container image tag/digest.
- Testcontainers diagnostic output.

### 26.9. Không lưu secrets production trong CI test

Dùng credentials disposable cho test. Không mount production secrets chỉ để chạy integration suite.

---

## 27. Testcontainers và Testcontainers JDBC URL

Testcontainers có cơ chế JDBC URL để khởi tạo container khi JDBC connection được tạo, thông qua driver integration.

### 27.1. JDBC URL concept

Một URL có dạng Testcontainers JDBC scheme, theo driver/database naming và container options. Cấu hình cụ thể phụ thuộc Testcontainers version và JDBC driver.

### 27.2. Khi nào hữu ích?

- Một test nhỏ dùng JDBC trực tiếp.
- Framework chỉ nhận datasource URL.
- Muốn khởi tạo container từ cấu hình thay vì quản lý container object.

### 27.3. Hạn chế

- Lifecycle ít tường minh hơn field @Container.
- Cấu hình init scripts/options có cú pháp riêng.
- Khó truy cập container object để lấy logs hoặc điều chỉnh runtime.
- Có thể khó phối hợp với Spring context caching.

### 27.4. Chọn API hay JDBC URL?

Dùng PostgreSQLContainer API khi cần lifecycle rõ, logs, custom configuration và tích hợp JUnit. JDBC URL phù hợp khi muốn datasource URL tự khởi tạo container và chấp nhận cơ chế lifecycle của driver.

### 27.5. Không trộn hai cơ chế vô thức

Một test không nên vô tình tạo hai containers do vừa khai báo @Container vừa dùng Testcontainers JDBC URL khác.

---

## 28. Test data và deterministic fixtures

### 28.1. Fixture nhỏ

Dùng số rows đủ để thể hiện behavior. Không cần hàng triệu rows để test một repository predicate cơ bản.

### 28.2. Data builders

Tạo builder/factory trong test source để tạo entities với defaults hợp lệ. Giúp test tập trung vào điều kiện đang kiểm tra.

### 28.3. Explicit timestamps

Dùng timestamp cố định và timezone rõ ràng để tránh test phụ thuộc thời điểm chạy.

### 28.4. Stable ordering

SQL không bảo đảm thứ tự rows nếu không có ORDER BY. Test list results nên sort/ORDER BY rõ ràng.

### 28.5. Avoid generated ID assumptions

Sequence/identity values có thể tăng qua rollback hoặc cleanup. Không hard-code kỳ vọng rằng ID luôn bắt đầu từ 1 trừ khi test reset sequence có chủ đích.

### 28.6. Null and boundary data

Fixture nên có:
- Null values nếu schema cho phép.
- Empty strings.
- Boundary timestamps.
- Unicode.
- Decimal scale.
- Duplicate candidates.
- Rows ở ranh giới pagination.

### 28.7. Builder không thay thế database constraints

Fixture builder có thể validate sớm, nhưng test vẫn cần xác nhận PostgreSQL constraints từ database.

---

## 29. Kiểm thử connection pool và failure behavior

### 29.1. Pool startup

Xác nhận pool khởi tạo sau container. Nếu context cache, đảm bảo container tồn tại suốt context lifetime.

### 29.2. Connection leak

Theo dõi active/idle connections, close resources và pool shutdown. Test nhiều methods có thể làm cạn max_connections nếu connection bị leak.

### 29.3. Database restart

Có thể test ứng dụng phản ứng khi remote database mất kết nối, nhưng cần controlled restart và timeout ngắn. Đây thường là integration/system test riêng.

### 29.4. Connection timeout

Cấu hình timeout hợp lý để test không treo vô hạn khi container không ready.

### 29.5. Retry policy

Chỉ retry lỗi transient phù hợp, ví dụ connection reset hoặc serialization failure theo policy. Không retry mọi SQLException, đặc biệt constraint violations.

### 29.6. SQLSTATE assertions

Dùng SQLState từ SQLException để phân loại database error. ORM/framework có thể wrap exception, nên lấy root cause khi cần.

### 29.7. Test cleanup

Đóng datasource/pool trước khi container stop. Không để background tasks tiếp tục query container sau test teardown.

---

## 30. Kiểm thử SQL migrations và schema drift

### 30.1. Schema validation

Sau migrations, có thể kiểm tra:
- Column types/nullability/defaults.
- Constraints.
- Index definitions.
- Views/functions.
- Extension versions.
- Grants/owners.
- Migration history.

### 30.2. pg_catalog

Dùng PostgreSQL catalogs để kiểm tra object properties khi behavior phụ thuộc metadata. Ví dụ pg_indexes, pg_constraint, pg_extension, pg_class.

### 30.3. Không assert OIDs

OID là implementation identifier có thể khác giữa database instances. Assert object names/definitions/behavior thay vì OID cụ thể.

### 30.4. Schema diff

Có thể so sánh schema expected với schema sau migration bằng migration tool hoặc schema diff tool. Không dựa duy nhất vào snapshot generated từ một môi trường cũ.

### 30.5. Migration idempotency

Không phải mọi migration được thiết kế để chạy nhiều lần. Test migration framework history và recovery behavior, không ép mọi script thành idempotent bằng IF NOT EXISTS một cách mù quáng.

### 30.6. Rollback migration

Nếu dự án có down migrations, test chúng trên PostgreSQL thật. Nhưng không phải mọi data migration đều có thể đảo ngược; ghi rõ destructive/non-reversible steps.

---

## 31. Kiểm thử transaction isolation và concurrency

### 31.1. READ COMMITTED

Mỗi statement trong transaction có thể thấy snapshot mới theo READ COMMITTED. Test concurrent update để xác nhận application logic không dựa vào snapshot cũ.

### 31.2. REPEATABLE READ

Nhiều statements trong cùng transaction đọc snapshot ổn định. Concurrent writes có thể dẫn tới serialization-style conflicts tùy operation.

### 31.3. SERIALIZABLE

Có thể trả serialization_failure. Application cần retry toàn transaction. Test cần xác nhận retry không duplicate external side effects.

### 31.4. SELECT FOR UPDATE

Dùng hai JDBC connections:
1. Connection A bắt đầu transaction và lock row.
2. Connection B cố lock cùng row.
3. Xác nhận B chờ hoặc timeout.
4. A commit/rollback.
5. Xác nhận B tiếp tục theo expected behavior.

### 31.5. SKIP LOCKED

Test job queue pattern bằng hai workers để xác nhận mỗi row chỉ được claim bởi một worker trong transaction.

### 31.6. NOWAIT

Test lock failure ngay lập tức và mapping lỗi tới application response.

### 31.7. Coordination

Dùng CountDownLatch, CyclicBarrier hoặc synchronization primitives để điều khiển thứ tự. Tránh Thread.sleep dài và flaky timing.

---

## 32. Kiểm thử nhiều PostgreSQL versions

### 32.1. Production parity

Ít nhất một integration suite nên dùng PostgreSQL major version giống production.

### 32.2. Upgrade compatibility

Nếu ứng dụng hỗ trợ nhiều major versions, chạy test matrix trên từng version được hỗ trợ.

### 32.3. CI matrix

Ví dụ conceptual matrix:
- PostgreSQL current production major.
- PostgreSQL next target major.
- PostgreSQL minimum supported major.

Không test mọi version không nằm trong support policy.

### 32.4. Extension matrix

Nếu dùng PostGIS/pgcrypto/pg_trgm, version extension cũng cần được pin/test cùng server version.

### 32.5. Avoid latest drift

Pin image versions và cập nhật có chủ đích. Một tag major có thể nhận patch updates theo thời gian; quyết định có chấp nhận floating patch hay pin digest dựa trên policy.

### 32.6. Version-specific assertions

SQLSTATE/message hoặc catalog columns có thể thay đổi. Assert behavior ổn định và ghi compatibility-specific tests khi cần.

---

## 33. Hiệu năng và tối ưu tốc độ suite

### 33.1. Startup cost

Pull image và initialize PostgreSQL là phần chi phí đáng kể. Cache image và tránh tạo container không cần thiết.

### 33.2. Reuse trong phạm vi suite

Một static/suite-scoped container có thể giảm startup. Đổi lại cần data isolation nghiêm ngặt.

### 33.3. Giảm fixture size

Chỉ tạo dữ liệu đủ cho assertion. Test performance riêng cần dataset lớn.

### 33.4. Tránh sleep

Dùng readiness checks và synchronization. Sleep làm suite chậm và flaky.

### 33.5. Tách integration task

Có thể chạy unit tests ở mỗi compile/change và integration tests ở pipeline phù hợp. Nhưng pull request thay đổi persistence code vẫn cần integration coverage.

### 33.6. Chọn số worker

Tăng parallelism chỉ tới mức Docker host và PostgreSQL containers chịu được. Quá nhiều containers làm suite chậm hơn do contention.

### 33.7. Reusable containers

Reusable containers có thể giữ trạng thái giữa runs và không phù hợp CI isolation mặc định. Nếu bật local reuse, developer phải biết cách reset state và không coi container đó là database sạch.

### 33.8. Testcontainers Cloud/remote runtime

Một số tổ chức có thể dùng remote container execution service. Khi đó cần kiểm tra network routing, image availability, credentials và support policy; không giả định host/port behavior giống Docker local.

---

## 34. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Docker daemon unavailable | Docker chưa chạy hoặc quyền socket thiếu | Kiểm tra docker info/permissions |
| Could not find a valid Docker environment | Runtime detection thất bại | Kiểm tra Docker context/endpoint |
| Image pull timeout | Registry/network/proxy | Kiểm tra registry, mirror và credentials |
| Container exits immediately | Env/config/init script lỗi | Đọc container logs |
| Connection refused | PostgreSQL chưa ready hoặc URL sai | Dùng container JDBC URL và wait strategy |
| Port conflict | Hard-coded host port | Dùng mapped port động |
| No suitable driver | JDBC driver thiếu | Thêm PostgreSQL JDBC driver test runtime |
| Authentication failed | User/password/database mismatch | Lấy credentials từ container |
| Spring context cannot connect | Property registration/lifecycle sai | Kiểm tra DynamicPropertySource/ServiceConnection |
| Container stopped between classes | Context cache và JUnit lifecycle không khớp | Dùng shared lifecycle phù hợp |
| Tests leak data | Shared database không cleanup | Transaction/schema/database isolation |
| Parallel tests flaky | Shared mutable data/locks | Tách database/schema hoặc giới hạn parallelism |
| Migration fails on extension | Image thiếu package extension | Dùng custom image đúng package |
| Tests pass locally, fail CI | Version/resource/network differences | Pin image/dependencies và thu logs |
| Out of memory/disk | Nhiều containers/data lớn | Giảm workers/fixtures, cấp tài nguyên |
| Slow startup | Image pull/init data | Cache image, tối ưu init và lifecycle |
| Stale pooled connections | Container dừng trước datasource | Sắp xếp lifecycle và close pool |

### 34.1. Đọc container logs

Khi startup hoặc SQL fails, lấy logs từ container object hoặc output Testcontainers. Logs PostgreSQL thường cho biết initialization, authentication, extension hoặc configuration error.

### 34.2. Không chỉ tăng timeout

Timeout lớn hơn có thể che một container bị cấu hình sai. Xác định PostgreSQL đang khởi động chậm hay đã exit.

### 34.3. Kiểm tra Docker context

Docker Desktop có thể chuyển context hoặc endpoint. Testcontainers phải kết nối đúng daemon mà CLI đang sử dụng.

### 34.4. Kiểm tra CI permissions

Runner cần quyền truy cập Docker socket/daemon. Nếu dùng remote daemon, kiểm tra TLS, host và port.

### 34.5. Kiểm tra image architecture

Image phải hỗ trợ architecture runner. Emulation có thể làm startup chậm hoặc không hoạt động như mong đợi.

---

## 35. Security trong integration tests

### 35.1. Credentials disposable

Dùng username/password riêng cho test container. Không tái sử dụng production credentials.

### 35.2. Không commit secrets

Không commit credentials, private keys hoặc dump dữ liệu thật. Test fixtures nên synthetic hoặc đã được làm sạch.

### 35.3. Container network

Container test không nên expose service ra network công cộng. Testcontainers thường chỉ cần host-mapped ports cho test process.

### 35.4. Image trust

Dùng image registry đáng tin cậy, pin version/digest và kiểm soát image updates.

### 35.5. Least privilege

Tạo test user có permissions tương ứng application role. Không chạy mọi repository tests bằng superuser nếu production dùng restricted role.

### 35.6. RLS tests

Nếu ứng dụng dùng Row-Level Security, tạo role/mapping phù hợp và test tenant isolation bằng database thật.

### 35.7. Logs và dumps

Test failure output có thể chứa SQL/data. Không đưa production PII hoặc secrets vào fixtures và logs.

### 35.8. Cleanup

Container disposable không thay thế việc cleanup artifact, volumes hoặc resources do custom scripts tạo ra. Đảm bảo test environment không để lại dữ liệu nhạy cảm.

---

## 36. Best practices

1. Dùng cùng PostgreSQL major version như production cho suite chính.
2. Pin PostgreSQL image và Testcontainers versions.
3. Dùng PostgreSQLContainer thay vì hard-coded localhost.
4. Dùng JUnit 5 lifecycle rõ ràng.
5. Dùng migrations thật để tạo schema.
6. Giữ test data nhỏ, deterministic và tự tạo trong mỗi test.
7. Dùng rollback chỉ khi mọi database operations tham gia cùng transaction.
8. Dùng cleanup/schema isolation cho HTTP, async và REQUIRES_NEW workflows.
9. Dùng flush/clear để xác nhận SQL đã thực sự chạy.
10. Test database-specific features trên PostgreSQL thật.
11. Dùng EXPLAIN/plan tests có mục đích, không assert toàn bộ plan string.
12. Điều khiển concurrency bằng synchronization, không bằng sleep.
13. Giới hạn parallelism theo resource capacity.
14. Thu container logs khi test fail.
15. Không dùng production secrets/data.
16. Đóng DataSource/connection pool trước khi container dừng.
17. Tách unit và integration test tasks nhưng giữ integration suite trong CI.
18. Test migration fresh install và upgrade path.
19. Chỉ thêm extensions vào custom image khi ứng dụng thực sự cần.
20. Ghi rõ PostgreSQL image, extension versions và test environment trong failure reports.

---

## 37. Ví dụ tổng hợp: repository integration test với Spring Boot

Ví dụ dưới đây giả định dự án có Spring Boot, Spring Data JPA, Flyway và JUnit 5. Dependency versions được quản lý bởi Spring Boot BOM và Testcontainers BOM tương thích.

### 37.1. Test entity

~~~java
@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String email;

    @Column(nullable = false)
    private String displayName;

    protected Customer() {
    }

    public Customer(String email, String displayName) {
        this.email = email;
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

### 37.2. Repository

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);
}
~~~

### 37.3. Flyway migration

File V1__create_customer.sql:

~~~sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL
);
~~~

### 37.4. Integration test

~~~java
@Testcontainers
@SpringBootTest
class CustomerRepositoryIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("app_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    CustomerRepository repository;

    @Test
    void savesAndFindsCustomer() {
        Customer saved = repository.saveAndFlush(
            new Customer("reader@example.test", "Reader")
        );

        repository.flush();

        Optional<Customer> found =
            repository.findByEmail("reader@example.test");

        assertTrue(found.isPresent());
        assertEquals(saved.getId(), found.orElseThrow().getId());
        assertEquals(
            "Reader",
            found.orElseThrow().getDisplayName()
        );
    }
}
~~~

### 37.5. Test properties

~~~properties
spring.flyway.enabled=true
spring.jpa.hibernate.ddl-auto=validate
~~~

### 37.6. Điều test này xác nhận

- Testcontainers khởi động PostgreSQL.
- Spring DataSource kết nối tới mapped port.
- Flyway tạo schema từ migration.
- Hibernate validate mapping.
- Repository thực hiện SQL qua PostgreSQL.
- Unique constraint và identity column được tạo bởi database thật.

### 37.7. Data cleanup

Nếu class dùng static container và nhiều tests, mỗi test cần rollback hoặc cleanup fixture. Không để test thứ hai phụ thuộc vào row do test thứ nhất tạo.

---

## 38. Lab 1: PostgreSQL smoke test bằng JUnit 5

### 38.1. Thêm dependencies

Thêm PostgreSQL module, JUnit Jupiter module, JUnit 5 và PostgreSQL JDBC driver vào test runtime theo Maven/Gradle.

### 38.2. Tạo test class

Dùng PostgreSQLContainer với image version được pin trong project.

### 38.3. Chạy query

Thực hiện SELECT 1, current_database(), current_user và version() bằng JDBC.

### 38.4. Kiểm tra mapped port

In ra host/mapped port trong log debug. Không ghi password.

### 38.5. Quan sát lifecycle

Chạy class hai lần. Xác nhận container được tạo/dọn theo lifecycle và test không phụ thuộc PostgreSQL local.

### 38.6. Kết luận

Test có thể kết nối tới PostgreSQL thật mà không cần server host cố định.

---

## 39. Lab 2: Repository và Flyway migrations

### 39.1. Tạo migration

Tạo table, unique constraint, foreign key và index trong Flyway migration.

### 39.2. Cấu hình Spring

Dùng DynamicPropertySource hoặc ServiceConnection để truyền connection details.

### 39.3. Chạy repository tests

Test insert, lookup, update, pagination và constraint violations.

### 39.4. Xác nhận schema

Truy vấn pg_catalog hoặc information_schema để xác nhận constraints/indexes được tạo.

### 39.5. Test fresh database

Tạo container/database mới và chạy tất cả migrations từ đầu.

### 39.6. Kết luận

Integration test xác nhận migration scripts thật có thể tạo schema trên đúng engine.

---

## 40. Lab 3: Transaction rollback và data isolation

### 40.1. Test rollback

Dùng @Transactional test và insert một row. Xác nhận row tồn tại trong test transaction.

### 40.2. Sau test

Chạy test khác hoặc query bằng connection mới để xác nhận row không còn sau rollback.

### 40.3. Thử REQUIRES_NEW

Tạo service method dùng propagation REQUIRES_NEW. Quan sát transaction độc lập có thể commit dù outer test transaction rollback.

### 40.4. Thử HTTP/async

Gọi application endpoint hoặc async task ghi dữ liệu bằng connection khác. Xác nhận rollback của test thread không tự rollback thao tác đó.

### 40.5. Cleanup

Thêm cleanup strategy cho committed rows. Không dựa vào @Transactional test cho mọi workflow.

### 40.6. Kết luận

Rollback test chỉ cô lập những writes tham gia đúng transaction.

---

## 41. Lab 4: PostgreSQL-specific behavior

### 41.1. JSONB

Tạo JSONB column, insert document và query bằng containment operator.

### 41.2. UUID

Insert/read UUID qua JDBC hoặc JPA.

### 41.3. Array

Insert PostgreSQL array và đọc lại bằng JDBC Array API hoặc mapping framework.

### 41.4. Constraint

Thử unique/check/foreign key violation và kiểm tra SQLSTATE.

### 41.5. Partial index

Tạo partial index qua migration và xác nhận query semantics.

### 41.6. Timezone

Insert timestamptz ở nhiều offsets, đọc lại trong session timezone khác và xác nhận instant semantics.

### 41.7. Kết luận

PostgreSQL container giúp phát hiện khác biệt mà H2 compatibility mode có thể bỏ sót.

---

## 42. Lab 5: Concurrency và lock behavior

### 42.1. Chuẩn bị table

Tạo một row có version/value để nhiều transactions cùng cập nhật.

### 42.2. Mở hai connections

Dùng hai JDBC connections và explicit transactions.

### 42.3. Lock row

Connection A thực hiện SELECT FOR UPDATE. Connection B cố lấy lock trên cùng row.

### 42.4. Điều khiển thứ tự

Dùng CountDownLatch hoặc CyclicBarrier để đồng bộ test threads. Không dùng sleep để đoán lúc lock được giữ.

### 42.5. Test timeout

Đặt lock_timeout cho connection B và xác nhận lỗi SQLSTATE phù hợp.

### 42.6. Test optimistic conflict

Dùng version column hoặc conditional UPDATE để xác nhận một writer nhận conflict.

### 42.7. Cleanup

Rollback/commit cả hai connections và đóng resources trong finally/try-with-resources.

### 42.8. Kết luận

Concurrency tests cần database thật, nhiều connections và synchronization có chủ đích.

---

## 43. Bài tập thực hành

### Bài 1 — Test layers

Phân biệt unit, repository integration, application integration và end-to-end tests.

### Bài 2 — H2 vs PostgreSQL

Liệt kê năm khác biệt PostgreSQL-specific có thể khiến test H2 pass nhưng production fail.

### Bài 3 — Testcontainers architecture

Mô tả container image, runtime, JUnit extension, JDBC driver và application code phối hợp ra sao.

### Bài 4 — Maven dependencies

Viết dependencyManagement BOM và dependencies PostgreSQL/JUnit Jupiter/Testcontainers.

### Bài 5 — Gradle dependencies

Viết cấu hình Gradle Kotlin DSL dùng Testcontainers BOM.

### Bài 6 — PostgreSQLContainer

Viết JUnit 5 test khởi chạy PostgreSQL và chạy SELECT 1.

### Bài 7 — Dynamic ports

Vì sao không hard-code localhost:5432? Viết cách lấy JDBC URL từ container.

### Bài 8 — Lifecycle

So sánh static @Container với instance @Container về startup cost và isolation.

### Bài 9 — Singleton

Nêu rủi ro của singleton container khi nhiều test classes và Spring context cache.

### Bài 10 — Spring Boot

Viết cấu hình DynamicPropertySource để cung cấp datasource URL/username/password.

### Bài 11 — ServiceConnection

Spring Boot version nào hỗ trợ ServiceConnection? Cần dependency nào?

### Bài 12 — Pool lifecycle

Vì sao DataSource/Hikari pool cần đóng trước khi container stop?

### Bài 13 — Flyway

Thiết kế test tạo database trống và chạy toàn bộ migrations.

### Bài 14 — Liquibase

Làm thế nào để xác nhận Liquibase changelog chạy trên PostgreSQL thật?

### Bài 15 — Hibernate DDL

Vì sao ddl-auto=create-drop có thể che lỗi production migration?

### Bài 16 — Fixtures

Thiết kế fixture deterministic cho repository test và tránh generated ID assumptions.

### Bài 17 — Cleanup

So sánh transaction rollback, DELETE/TRUNCATE, schema-per-test và container-per-test.

### Bài 18 — @Transactional

Nêu trường hợp writes không được rollback khi Spring test transaction kết thúc.

### Bài 19 — REQUIRES_NEW

Thiết kế test chứng minh REQUIRES_NEW commit không bị outer test rollback.

### Bài 20 — Deferred constraints

Vì sao flush có thể chưa đủ để test deferred constraint? Cần transaction boundary nào?

### Bài 21 — JSONB

Viết integration test insert/query JSONB bằng PostgreSQL operator.

### Bài 22 — Arrays và enums

Thiết kế round-trip tests cho PostgreSQL array và enum mapping.

### Bài 23 — Timestamp

Viết test chứng minh timestamptz giữ instant khi client và database dùng timezone khác.

### Bài 24 — Extensions

Làm thế nào build PostgreSQL image có PostGIS/pgcrypto và cài extension trong test?

### Bài 25 — Concurrency

Dùng hai JDBC connections test SELECT FOR UPDATE.

### Bài 26 — Deadlock

Thiết kế deadlock test có coordination rõ ràng và timeout giới hạn.

### Bài 27 — SQLSTATE

Viết test xác nhận unique violation và serialization failure được map đúng trong application.

### Bài 28 — Parallel tests

Vì sao shared static container có thể gây flaky tests? Đề xuất isolation strategy.

### Bài 29 — CI Docker

CI runner cần những điều kiện gì để Testcontainers truy cập Docker daemon?

### Bài 30 — Image pinning

Giải thích rủi ro dùng latest và lợi ích của pin patch version/digest.

### Bài 31 — Readiness

Vì sao Thread.sleep không phải readiness check? Chọn wait strategy phù hợp.

### Bài 32 — Image pull failure

Thiết kế troubleshooting cho registry timeout hoặc authentication failure.

### Bài 33 — Spring context cache

Một test class sau không kết nối được vì container class trước đã dừng. Phân tích lifecycle và cách sửa.

### Bài 34 — JDBC URL

So sánh PostgreSQLContainer API với Testcontainers JDBC URL.

### Bài 35 — Performance

Đề xuất cách giảm test suite time mà vẫn giữ data isolation.

### Bài 36 — Resource limits

Nhiều containers chạy song song làm CI hết memory. Cách điều chỉnh workers và fixtures?

### Bài 37 — Migration failure

Một migration CREATE INDEX CONCURRENTLY thất bại. Thiết kế test recovery và migration ledger behavior.

### Bài 38 — Managed PostgreSQL

Vì sao Testcontainers không thay thế staging test trên managed PostgreSQL khi dùng provider-specific features?

### Bài 39 — Test plan

Xây dựng test pyramid cho Java service dùng Spring Data JPA, Flyway, JSONB, RLS và PostgreSQL extensions.

### Bài 40 — End-to-end integration suite

Thiết kế suite từ PostgreSQL container, migrations, repository tests, HTTP API, transaction rollback, async writes, parallel workers, CI logs và PostgreSQL version matrix. Xác định test nào dùng unit mock, test nào cần PostgreSQL thật và cách cleanup từng loại.

---

## 44. Checklist trước khi đưa integration tests vào CI

| Hạng mục | Điều cần xác nhận |
| --- | --- |
| Database parity | PostgreSQL major version giống production |
| Image | Tag/digest được pin và cập nhật có review |
| Java | JDK tương thích |
| Testcontainers | Modules dùng cùng BOM/version |
| JUnit | Jupiter engine và extension được cấu hình |
| JDBC driver | Có trong test runtime |
| Docker runtime | Daemon reachable từ test process |
| Registry | CI pull được image hoặc dùng mirror |
| Container lifecycle | Static/instance/suite scope rõ |
| Port mapping | Dùng getJdbcUrl, không hard-code port |
| Readiness | Có wait strategy, không sleep cố định |
| Spring config | DynamicPropertySource hoặc ServiceConnection đúng version |
| Context cache | Container lifetime không ngắn hơn cached context |
| DataSource | Pool đóng trước container |
| Migrations | Chạy migrations production thật |
| Fresh schema | Test tạo database trống |
| Upgrade path | Test schema upgrade nếu dự án hỗ trợ |
| Extensions | Image có packages cần thiết |
| Fixtures | Synthetic, deterministic, nhỏ |
| Cleanup | Transaction/schema/database strategy rõ |
| Async writes | Có cleanup ngoài test transaction |
| Parallelism | Không chia sẻ mutable data thiếu isolation |
| Concurrency | Dùng synchronization và timeout |
| SQL behavior | Test types, constraints và PostgreSQL-specific features |
| Assertions | Ưu tiên behavior, tránh brittle plan strings |
| Logs | Thu PostgreSQL/container/application logs khi fail |
| Security | Không dùng production secrets/PII |
| Resource limits | Workers/container count phù hợp runner |
| CI reports | JUnit XML và build logs được lưu |
| Version matrix | Chỉ test versions nằm trong support policy |
| Recovery | Test failure path và cleanup |
| Ownership | Có người duy trì image/dependency versions |

## Kết luận

Kiểm thử tích hợp bằng PostgreSQL thật và Testcontainers giúp xác nhận Java application làm việc với đúng database engine mà production sử dụng. Testcontainers tạo PostgreSQL environment tạm thời, cung cấp connection details động và quản lý vòng đời container. Khi kết hợp với JUnit 5, JDBC/ORM và migration engine thật, test có thể phát hiện lỗi SQL, mapping, constraints, transaction, locking, extensions và PostgreSQL-specific behavior trước khi triển khai.

Những nguyên tắc cần nhớ:

1. **Mock và H2 không thay thế hoàn toàn PostgreSQL.** Dùng database thật cho behavior phụ thuộc engine, SQL và transaction.
2. **Pin PostgreSQL image và dependency versions.** Tránh latest làm kết quả test thay đổi âm thầm.
3. **Dùng JDBC URL và mapped port từ container.** Không hard-code localhost:5432.
4. **Chọn container lifecycle có chủ đích.** Static nhanh hơn; instance cô lập hơn; singleton cần quản lý cẩn thận.
5. **Tích hợp migrations production thật.** Không để Hibernate create-drop che lỗi Flyway/Liquibase.
6. **Hiểu giới hạn của @Transactional tests.** HTTP, async, REQUIRES_NEW và connections độc lập có thể commit ngoài test transaction.
7. **Cô lập test data.** Rollback, cleanup, schema/database riêng hoặc container riêng tùy workflow.
8. **Concurrency tests cần nhiều connections thật.** Dùng synchronization, lock timeout và SQLSTATE assertions.
9. **Kiểm tra PostgreSQL-specific types và extensions.** JSONB, arrays, enums, UUID, ranges, indexes và RLS cần test trên engine thật.
10. **Spring context và container phải cùng lifecycle.** Context cache không được giữ datasource trỏ tới container đã dừng.
11. **CI phải truy cập được Docker daemon.** CLI có mặt chưa đủ; cần runtime permissions, network và image availability.
12. **Không dùng sleep để đợi database.** Dùng readiness/wait strategy và đọc container logs khi fail.
13. **Giới hạn parallelism theo tài nguyên.** Shared container cần data isolation và connection pool sizing.
14. **Test migrations cả fresh install và upgrade path.** Kiểm tra schema/catalog sau khi chạy.
15. **Testcontainers không mô phỏng toàn bộ production infrastructure.** Managed-service behavior, HA, replication và provider-specific features có thể cần staging tests riêng.

Một integration suite đáng tin cậy dùng PostgreSQL version phù hợp, migrations thật, fixture có kiểm soát và assertions tập trung vào behavior. Container chỉ tạo môi trường; chất lượng test đến từ việc chọn đúng ranh giới, cô lập dữ liệu và kiểm tra cả đường đi thành công lẫn failure modes của ứng dụng.

## Tài liệu tham khảo

- [Testcontainers for Java — PostgreSQL module](https://java.testcontainers.org/modules/databases/postgres/)
- [Testcontainers for Java — JUnit 5 integration](https://java.testcontainers.org/test_framework_integration/junit_5/)
- [Testcontainers for Java — JDBC URL support](https://java.testcontainers.org/modules/databases/jdbc/)
- [PostgreSQL — Documentation](https://www.postgresql.org/docs/current/)
- [Spring Boot — Testcontainers support](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/)

