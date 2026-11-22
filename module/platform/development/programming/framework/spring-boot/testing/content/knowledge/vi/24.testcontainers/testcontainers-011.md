# Dọn tài nguyên, log container và chẩn đoán startup lỗi với Testcontainers

**Testcontainers** giúp integration test chạy với những dịch vụ thực như PostgreSQL, Redis, Kafka, MongoDB hoặc một HTTP server trong Docker. Nhờ đó, Spring Boot test có thể kiểm **SQL thật, protocol thật, transaction thật, mapping và cấu hình kết nối**, thay vì chỉ mock repository. Nhưng việc tạo được container chưa đủ: cần quản lý **vòng đời container**, dọn **dữ liệu test** mà không phá test khác, thu **log đúng thời điểm**, xác định **lý do startup failure** và tránh những lối sửa tắt khiến CI vừa chậm vừa flaky.

Bài này trả lời ba câu hỏi thực tế:

1. **Dọn cái gì, khi nào, do ai?** Phân biệt xóa container, volume/network, dữ liệu trong container, Java connection/client, test fixture và những tài nguyên ngoài Docker.
2. **Lấy log ở đâu?** Dùng `getLogs()`, `followOutput()`, `withLogConsumer(...)`, SLF4J và `docker logs` khi container còn tồn tại. Thu log khi test fail nhưng không làm lộ secret hoặc làm mất nguyên nhân lỗi gốc.
3. **Chẩn đoán lỗi start thế nào?** Tách Docker daemon/image pull khỏi container process, wait strategy, service readiness, database migration, network và Spring context. Chọn phương pháp tái lập và sửa đúng lớp.

Ví dụ hoàn chỉnh ở phần 7 dùng **Java 17, Spring Boot 3.5, JUnit Jupiter, PostgreSQL 16 và Testcontainers**, có cleanup dữ liệu theo `runId`, container shared theo test class, service connection tự cấu hình, live log consumer và snapshot log khi JUnit test thất bại.

## 1. Phân biệt 5 tầng tài nguyên

```text
Test/CI process
   |
   +-- Spring ApplicationContext
   |      +-- DataSource / Connection Pool / repository / service
   |
   +-- Testcontainers JUnit extension
   |      +-- PostgreSQLContainer<?> object trong JVM
   |              |
   |              +-- Docker container process
   |              |      +-- stdout / stderr / exit code / health status
   |              |
   |              +-- volumes / network / mapped port / environment
   |
   +-- data created by tests
          +-- tables, rows, keys, messages, files, topics
          +-- business IDs / tenant IDs / external side effects
```

Một lời gọi `postgres.stop()` chủ yếu nhắm tới **Docker container** và tài nguyên gắn với vòng đời đó. Nó **không tự dọn** một PostgreSQL database external, một bind-mounted thư mục của host, một named volume được giữ lại có chủ đích, hay message đã gửi tới broker khác.

Ngược lại, `jdbcTemplate.update("DELETE ...")` có thể xóa row test nhưng **không dừng container** hay giải phóng mapped port, connection pool hoặc thread của ứng dụng. Spring `@DirtiesContext` yêu cầu làm mới application context nhưng **không phải lệnh dừng mọi container hoặc xóa mọi dữ liệu Docker**.

| Tài nguyên | Đơn vị sở hữu | Cách dọn đúng | Không được nhầm với |
|---|---|---|---|
| Container do `@Container` quản lý | JUnit extension/Testcontainers | Extension dừng sau test method/class theo vòng đời | Dọn row giữa hai tests |
| Container được `start()` thủ công | Code tạo container | `try/finally` và `stop()` | JUnit tự quản nếu không có extension |
| Rows/keys/fixtures | Test method/class hoặc test run | Delete theo `runId` hoặc reset database **độc quyền** | Container static tự reset mọi method |
| Docker volume/network | Container/test environment | Mặc định lifecycle của Docker/Testcontainers; chỉ cleanup có phạm vi rõ | Mọi named volume đều bị xóa an toàn |
| Connection pool/clients | Spring context/Java object | Đóng context/pool và resources theo owner | Chỉ dừng DB container là đủ |
| Log files/CI artifacts | Build/CI job | Redact, lưu có retention/permission | Dữ liệu luôn công khai và an toàn |
| Broker/external API | Test fixture, sandbox, service riêng | Cleanup/compensation theo resource ID | DB transaction rollback |

**Nguyên tắc:** dọn theo **tầng sở hữu thực tế**, tránh lệnh toàn cục như `docker system prune -a --volumes` hoặc `DROP DATABASE` trên môi trường dùng chung.

## 2. Vòng đời `@Testcontainers` và `@Container` của JUnit Jupiter

Testcontainers cung cấp JUnit Jupiter extension:

```java
@Testcontainers
class RepositoryIntegrationTest {
    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // Các @Test sử dụng chung một container cho cả class.
}
```

Đây chỉ là snippet vòng đời, chưa có test methods/dependencies. Các hành vi cơ bản:

- **`static @Container`**: container được khởi động trước các test methods trong class và dừng sau khi class hoàn tất. Nhiều methods **dùng cùng một database instance**; không tự reset bảng sau mỗi test.
- **Instance `@Container`** (field không static): được tạo/start/stop quanh mỗi test method, cho isolation tốt hơn nhưng có thể tốn thời gian khởi động database.
- **`@Testcontainers`** kích hoạt extension. Chỉ có field `@Container` mà không đăng ký extension theo cách tương ứng thì không được bảo đảm lifecycle JUnit mong đợi.
- **`@BeforeEach`/`@AfterEach`** thường dùng cho dữ liệu giữa các methods. **`@BeforeAll`/`@AfterAll`** có thể chuẩn bị/kiểm tra phạm vi class, nhưng không nên tự `stop()` một container đã do extension quản lý.
- Testcontainers JUnit extension được tài liệu mô tả là **đã kiểm chứng với thực thi tuần tự**; parallel execution có thể tạo tương tác ngoài ý muốn. Nếu chạy song song, phải có isolation riêng và hiểu rõ framework/config.

### Container dùng chung không đồng nghĩa state dùng chung có kiểm soát

```text
static PostgreSQLContainer
    |
    +-- Test A: INSERT order run_id=A
    |
    +-- Test B: SELECT count(*) ...
    |        Có thể thấy order A nếu Test A không cleanup!
    |
    +-- Test C: DELETE chỉ run_id=C
```

Dù extension tự dừng container ở cuối class, Test B vẫn có thể fail do **dữ liệu còn trong class**. Vì vậy fixture cleanup giữa các tests là trách nhiệm độc lập với lifecycle Docker.

Nếu suite muốn **tối đa isolation**, có thể dùng container riêng per test hoặc schema/database tách theo class; nếu muốn **tối ưu tốc độ**, dùng static container + unique test key + scoped cleanup. Không có cấu hình phù hợp cho mọi DB, tests và CI infrastructure.

## 3. Ryuk, resource reaper và container bị bỏ lại

Theo hành vi mặc định được Testcontainers hỗ trợ, **Ryuk/resource reaper** giúp dọn những Docker resources mang nhãn Testcontainers còn lại khi test JVM kết thúc hoặc bị gián đoạn. JUnit extension vẫn chủ động quản lý `@Container` khi lifecycle diễn ra bình thường.

Điều cần hiểu:

- **Ryuk không thay thế `@AfterEach`**: nó xử lý Docker resources theo session, không xóa riêng order của Test A trong database mà Test B sắp dùng.
- Trong môi trường Docker-in-Docker hoặc CI restricted, Ryuk có thể không kết nối Docker socket hoặc bị security policy chặn. Thông báo lỗi **Ryuk startup** khác lỗi PostgreSQL process.
- Không vội đặt `TESTCONTAINERS_RYUK_DISABLED=true` chỉ để test xanh; nếu vô hiệu hóa resource reaper, bạn cần chiến lược cleanup Docker resources có chủ đích và quyền phù hợp.
- **Reusable containers** (`withReuse(true)` kết hợp testcontainers config) có thể cố tình tồn tại sau JVM; tính năng có điều kiện và không được khuyến khích dùng vô tội vạ trong CI. Đặc biệt, Testcontainers JUnit Jupiter extension **không hỗ trợ phối hợp container reuse theo cơ chế reuse thử nghiệm như một lựa chọn lifecycle chuẩn**.
- Container có thể không được dừng sạch sau khi JVM bị kill đột ngột, Docker daemon lỗi hoặc CI runner bị bỏ ngang. Cần diagnostic qua Docker labels/session và janitor có scope.

### Dọn Docker resources: kiểm ID và quyền sở hữu trước

Các lệnh **điều tra**, không phải lệnh xóa rộng:

```bash
docker info
docker ps -a
docker inspect <container-id>
docker logs <container-id>
docker volume ls
docker network ls
```

`<container-id>` là placeholder cho Docker ID thực tế lấy từ log Testcontainers hoặc `docker ps -a`. Trong shell, thay bằng ID thật chứ không nhập dấu `< >` nguyên văn. Xóa **một container do chính test run sở hữu** (nếu đã xác minh) có thể dùng:

```bash
docker rm -f <container-id>
```

Không tự chạy lệnh này trên container của người khác hoặc shared CI environment. Trước khi xóa, cần xác nhận image, label, owner, process và dependent resources. Đừng dùng `docker system prune`, `docker volume prune` hay `docker network prune` để “dọn cho sạch” trong một môi trường không độc quyền: chúng có thể ảnh hưởng nhiều dự án khác.

## 4. Log container: snapshot và theo dõi realtime

### 4.1. `getLogs()`: lấy stdout/stderr từ thời điểm tạo container

Testcontainers cho phép:

```java
String allLogs = postgres.getLogs();
String stderrOnly = postgres.getLogs(
        org.testcontainers.containers.output.OutputFrame.OutputType.STDERR);
```

Snippet cần biến `postgres` đã start. `getLogs()` lấy **snapshot** log của container từ khi được tạo tới thời điểm gọi; nó không phải tail streaming live vô hạn. Có thể lọc stdout/stderr bằng `OutputFrame.OutputType`. Với PostgreSQL, readiness message thường xuất hiện ở stderr, nhưng nội dung/timing thay đổi theo image/version; **không assert nguyên văn line startup trừ khi log text chính là contract**.

Nên giới hạn số ký tự khi đưa log vào CI artifact vì log có thể rất lớn:

```java
static String tail(String value, int chars) {
    return value.substring(Math.max(0, value.length() - chars));
}
```

Đây là helper độc lập trong một Java class, giả định input không null và `chars >= 0`; nếu log có secret, **phải redact trước khi lưu**, không coi truncate là đủ để che secret.

### 4.2. `followOutput()`: nhận từng frame log theo thời gian

Khi muốn theo dõi stdout/stderr trong test:

```java
container.followOutput(frame -> {
    String line = frame.getUtf8String();
    // Redact + gửi vào test logger nếu thật sự cần.
});
```

Snippet giả định container hỗ trợ `followOutput` và có biến `container`; dùng Consumer của `OutputFrame`. Testcontainers cũng có `WaitingConsumer` để chờ một log frame khớp predicate với timeout. **Đừng dùng `Thread.sleep(10000)` như cách xác minh readiness**; nếu mục tiêu là container/service ready, nên dùng wait strategy của Testcontainers trước khi ứng dụng kết nối.

### 4.3. `Slf4jLogConsumer`: chuyển output tới log framework

```java
private static final Logger LOG =
        LoggerFactory.getLogger("testcontainers.postgresql");

static final PostgreSQLContainer<?> PG =
        new PostgreSQLContainer<>("postgres:16-alpine")
                .withLogConsumer(new Slf4jLogConsumer(LOG));
```

Snippet cần imports `org.slf4j.Logger`, `LoggerFactory`, `org.testcontainers.containers.output.Slf4jLogConsumer` và `PostgreSQLContainer`; ví dụ hoàn chỉnh ở phần 7. Đặt log consumer **trước khi container start** để thu cả giai đoạn startup. Log consumer phụ thuộc mức log của SLF4J backend: có thể cấu hình riêng test logger tại DEBUG/INFO theo nhu cầu.

**Không in bừa stdout**: database logs hoặc app container logs có thể chứa URL, user, token, SQL bind values, HTTP headers hoặc dữ liệu khách hàng. Trong CI, dùng test credentials, redact secrets, phân quyền artifacts, đặt retention và chỉ bật verbose logging khi chẩn đoán.

### 4.4. Chụp log khi JUnit test thất bại

Có thể đăng ký một `TestWatcher` để in **tail** của container logs nếu test method fail. Điều này hữu ích vì JUnit extension có thể dừng container ở cuối class, khiến `docker logs <id>` không còn truy cập được.

**Giới hạn:** `TestWatcher.testFailed` không thay thế logging ở **startup failure xảy ra trước khi test method chạy**. Nếu container/image không bao giờ start, callback method-failure có thể không chạy; cần xem stack trace của `ContainerLaunchException`, log Testcontainers/Docker và CI diagnostics.

## 5. Readiness khác trạng thái `running`

Testcontainers phân biệt:

- **Startup check**: container process đã đạt trạng thái `running` hoặc một trạng thái khởi động hợp lệ với loại container đó hay chưa.
- **Wait strategy**: service bên trong container đã **sẵn sàng cho client thật** hay chưa.
- **Application readiness**: Spring Boot application đã kết nối DB, chạy SQL init/migrations và tạo bean đủ để test chạy hay chưa.

Ví dụ một process đã chạy và mở port TCP, nhưng database vẫn chưa chấp nhận authentication/query. Chỉ thấy port 5432 **LISTEN** không chứng minh `SELECT 1` thành công. Với specialized `PostgreSQLContainer`, **giữ default JDBC-oriented wait strategy** thay vì vội thay bằng wait log message chung; module database đã có cơ chế chờ thích hợp.

### `Wait.forLogMessage` với GenericContainer

```java
GenericContainer<?> redis = new GenericContainer<>(
        DockerImageName.parse("redis:7-alpine"))
        .withExposedPorts(6379)
        .waitingFor(Wait.forLogMessage(
                ".*Ready to accept connections.*\\n", 1));
```

Đây là snippet minh họa, cần imports `GenericContainer`, `DockerImageName`, `org.testcontainers.containers.wait.strategy.Wait`. Regex và `times=1` phải khớp **log của image/version được pin**. Nếu log format thay đổi, test có thể timeout dù Redis thật sự đã ready. Với PostgreSQL hoặc các specialized containers, **không override wait strategy mặc định nếu không có bằng chứng**.

Tăng startup timeout chỉ khi biết service thực sự khởi động chậm:

```java
new GenericContainer<>("myorg/service:1.0")
        .withExposedPorts(8080)
        .waitingFor(Wait.forHttp("/health").forStatusCode(200))
        .withStartupTimeout(java.time.Duration.ofMinutes(2));
```

Snippet không runnable độc lập vì image `myorg/service:1.0` là ví dụ. `Wait.forHttp` phù hợp khi `/health` phản ánh service readiness. **Không lặp lại vô hạn** và không chỉ tăng timeout từ 60 lên 600 giây để che lỗi credentials, sai image hoặc thiếu init script.

### Mapped ports và kết nối đúng

Đừng hardcode `localhost:5432`: Testcontainers thường **map cổng container sang một cổng host động**. Trong Java, dùng:

```java
String jdbcUrl = postgres.getJdbcUrl();
String host = postgres.getHost();
int port = postgres.getMappedPort(5432);
```

Các getter này phải được dùng **sau khi container start**. Với Spring Boot, nên dùng `@ServiceConnection` (Boot 3.5) hoặc `@DynamicPropertySource` để đưa URL/credentials vào context; tuyệt đối đừng nối `localhost:5432` theo suy đoán nếu CI chạy trên Docker host từ xa.

## 6. Vòng lặp chẩn đoán startup failure

Khi `@SpringBootTest` báo `Failed to load ApplicationContext`, đó là **triệu chứng chung**, không phải nguyên nhân gốc. Hãy phân loại:

```text
Maven test failed
    |
    v
Đã kết nối được Docker daemon chưa?
    |-- Không --> daemon/socket/context/permissions/CI runner
    |
    v
Pull image thành công?
    |-- Không --> registry/auth/network/rate limit/tag/architecture
    |
    v
Docker create/start container thành công?
    |-- Không --> mount/volume/permission/port/memory/cgroup/Ryuk
    |
    v
Container process còn running?
    |-- Không --> docker logs, exit code, entrypoint/config/health
    |
    v
Wait strategy đạt readiness?
    |-- Không --> wrong port, health path, log regex, startup timeout
    |
    v
Ứng dụng Spring tạo datasource/client được?
    |-- Không --> JDBC URL, credentials, SSL, mapped port, bean config
    |
    v
Schema/migrations/query chạy được?
    |-- Không --> schema.sql, Flyway/Liquibase, dialect, privileges
    |
    v
Tests pass và resource cleanup?
    |-- Không --> fixture isolation, concurrency, leaks, async effects
```

### 6.1. Không truy cập được Docker

Triệu chứng: `Could not find a valid Docker environment`, `Cannot connect to the Docker daemon`, permission denied trên socket hoặc Docker context trỏ sai nơi.

Kiểm:

```bash
docker version
docker info
docker context ls
docker ps
```

Nếu máy dùng Docker Desktop, xác nhận daemon thực sự chạy. Với Linux CI/remote Docker, kiểm quyền socket, user/group, `DOCKER_HOST` và Docker context. **Không** tự chmod `666` cho Docker socket trong CI để chữa lỗi: quyền điều khiển Docker daemon có ảnh hưởng bảo mật lớn. Với Docker-in-Docker, kiểm network/socket mounts và chính sách runner.

### 6.2. Pull image bị lỗi

Dấu hiệu: `manifest unknown`, `pull access denied`, `429 Too Many Requests`, `TLS handshake timeout`, registry auth, platform architecture mismatch.

- Dùng **tag image tồn tại và được pin** (ví dụ `postgres:16-alpine`), tránh `:latest` trong CI cần deterministic.
- Nếu private registry, dùng credentials qua secret store/CI, không đưa password vào log hoặc commit POM.
- Với arm64/amd64, kiểm image có hỗ trợ platform và môi trường có emulation phù hợp.
- Lỗi registry/network không giải quyết bằng cách tăng **database wait timeout**.
- Không xóa image cache toàn cục chỉ vì một tag không pull được.

### 6.3. Container exit ngay khi khởi động

Xem Docker metadata/log:

```bash
docker ps -a
docker inspect <container-id>
docker logs <container-id>
```

Đọc `State.ExitCode`, `State.Error`, `State.OOMKilled`, `Health.Status` (nếu có), mount errors và stdout/stderr. Với PostgreSQL, lỗi có thể do environment/init script, permission của data directory, không đủ RAM/disk hoặc dữ liệu cũ không tương thích với image major version.

**Quan trọng:** khi Testcontainers thấy startup failure, nó có thể **dừng/xóa container**; lúc ấy `docker logs <id>` không còn khả dụng. Thu log qua Testcontainers logger/CI console ngay từ giai đoạn startup là cách đáng tin hơn. Testcontainers cũng có thể tự log **output của container thất bại** ở mức ERROR tùy code/version, nhưng không nên chỉ dựa vào một message cố định.

### 6.4. Container running nhưng wait timeout

Dấu hiệu: `Timed out waiting for container port to open`, `ContainerLaunchException`, `HTTP 503` hoặc `Wait strategy failed`.

Kiểm **service đang nghe cổng nào**, `withExposedPorts`, container-to-host port mapping, đúng health endpoint, TLS, regex log và tình huống DB init/migrations chậm. Đừng dùng `Thread.sleep` trước test như bản vá chung. Nếu image đã cung cấp healthcheck, cân nhắc `Wait.forHealthcheck()`; nếu không, dùng `Wait.forHttp` hoặc specialized module thích hợp.

**`withStartupTimeout(Duration)` chỉ thay deadline**. Nếu service không bao giờ ready vì sai credentials hoặc không mở cổng, tăng thời gian chỉ làm CI chậm. Hãy lấy log + exit code + wait condition trước.

### 6.5. Container ready nhưng Spring context fail

Triệu chứng: `BeanCreationException`, `PSQLException: password authentication failed`, `Connection refused`, `relation does not exist` hoặc `FlywayValidateException`.

Kiểm:

- Spring Boot đang dùng **`@ServiceConnection`** hay `@DynamicPropertySource`? `@ServiceConnection` được hỗ trợ khi có dependency `spring-boot-testcontainers`.
- `@ServiceConnection` details có thể ưu tiên cao hơn connection properties. Nếu hardcode `spring.datasource.url` và dùng ServiceConnection cùng lúc, phải hiểu ai thắng.
- Driver JDBC `org.postgresql:postgresql` có mặt trong runtime/test classpath?
- `spring.sql.init.mode=always` có chạy `schema.sql` đúng datasource sau khi container ready?
- Flyway/Liquibase có migrations thực sự được áp dụng? Có xung đột với Hibernate `ddl-auto`?
- Đã dùng database name/schema và mapped port từ container chưa?
- Lỗi ở bootstrap Spring **không chứng minh** Docker không chạy; phân biệt nguyên nhân qua stack trace và container logs.

## 7. Ví dụ runnable: Java 17 + Spring Boot 3.5 + PostgreSQL Testcontainers

Mục tiêu: các test dùng **một PostgreSQL container static** trong class. Spring Boot kết nối tự động qua `@ServiceConnection`. `schema.sql` tạo bảng `audit_events`. Mỗi test tạo **`runId` duy nhất**, `@AfterEach` xóa đúng row và verify count bằng 0. TestWatcher thu tail container logs khi **một test method thất bại**; `Slf4jLogConsumer` theo dõi logs từ startup.

Bộ test không cố tình làm container fail, vì startup failure khiến cả JUnit class không khởi tạo được; phần 8 cung cấp bài tập chẩn đoán an toàn để tự thực hành trên môi trường test.

### 7.1. Cấu trúc project

```text
testcontainers-diagnostics/
├── pom.xml
└── src/
    ├── main/java/com/example/tc/
    │   └── DiagnosticsApplication.java
    └── test/
        ├── java/com/example/tc/
        │   └── PostgresDiagnosticsTest.java
        └── resources/
            └── schema.sql
```

### 7.2. `pom.xml` đầy đủ

Dùng Spring Boot **3.5.0** để các dependency/test annotations cùng dòng. Java 17+, JUnit Jupiter, Spring JDBC, PostgreSQL JDBC driver và Testcontainers. Cần **Docker Engine/Desktop** hoạt động và khả năng pull image `postgres:16-alpine`.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>testcontainers-diagnostics</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>junit-jupiter</artifactId>
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
```

**Đừng tự pin Testcontainers 2.x vào POM Boot 3.5 này** rồi giữ nguyên imports cũ: Testcontainers modules/package đã thay đổi ở các dòng mới. Boot BOM quản lý các phiên bản liên quan cho ví dụ, khi nâng cấp phải đối chiếu compatibility chính xác.

### 7.3. Spring Boot main class

File **`src/main/java/com/example/tc/DiagnosticsApplication.java`**:

```java
package com.example.tc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DiagnosticsApplication {
    public static void main(String[] args) {
        SpringApplication.run(DiagnosticsApplication.class, args);
    }
}
```

Application này không cần web starter. `@SpringBootTest(webEnvironment=NONE)` chỉ khởi động Spring container, JdbcTemplate/DataSource và SQL initialization. Không có HTTP server của app; PostgreSQL Docker container vẫn có network port riêng.

### 7.4. SQL schema dành riêng cho test

File **`src/test/resources/schema.sql`**:

```sql
CREATE TABLE IF NOT EXISTS audit_events (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(80) NOT NULL,
    event_name VARCHAR(80) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_events_run
    ON audit_events (run_id);
```

Bảng có `run_id` cho cleanup theo owner. `IF NOT EXISTS` giúp script có thể được chạy lại trong DB riêng, nhưng không tự validate schema migration. Trong production, nếu dùng Flyway/Liquibase, test integration của migrations nên chạy **cùng migrations thật** thay vì một schema.sql giản lược.

### 7.5. Test class đủ 5 test methods, cleanup và logs

File **`src/test/java/com/example/tc/PostgresDiagnosticsTest.java`**:

```java
package com.example.tc;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtensionContext;
import org.junit.jupiter.api.extension.RegisterExtension;
import org.junit.jupiter.api.extension.TestWatcher;

import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.jdbc.core.JdbcTemplate;

import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.containers.output.Slf4jLogConsumer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "spring.sql.init.mode=always")
class PostgresDiagnosticsTest {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> PG =
            new PostgreSQLContainer<>(
                    DockerImageName.parse("postgres:16-alpine"))
                    .withDatabaseName("diagnostics")
                    .withUsername("test_user")
                    .withPassword("local_test_password")
                    .withLogConsumer(new Slf4jLogConsumer(
                            LoggerFactory.getLogger("tc.postgresql")));

    @RegisterExtension
    static final TestWatcher LOGS_ON_FAILURE = new TestWatcher() {
        @Override
        public void testFailed(
                ExtensionContext context, Throwable cause) {
            // Chỉ là diagnostic. Không làm mất lỗi test ban đầu.
            try {
                if (!PG.isRunning()) {
                    System.err.println(
                            "PostgreSQL container no longer running");
                    return;
                }
                String logs = PG.getLogs();
                System.err.println(
                        "PostgreSQL logs for failed test: "
                        + context.getDisplayName());
                System.err.println(tail(logs, 4000));
            } catch (Exception logFailure) {
                System.err.println(
                        "Cannot read container logs: "
                        + logFailure.getClass().getSimpleName());
            }
        }
    };

    @Autowired
    private JdbcTemplate jdbc;

    private String runId;

    @BeforeEach
    void createUniqueOwnerId() {
        runId = "it-" + UUID.randomUUID();
    }

    @AfterEach
    void removeOnlyThisTestsRows() {
        if (runId == null) {
            return;
        }
        jdbc.update(
                "DELETE FROM audit_events WHERE run_id = ?", runId);
        assertThat(countFor(runId)).isZero();
    }

    static String tail(String value, int chars) {
        return value.substring(Math.max(0, value.length() - chars));
    }

    private long countFor(String id) {
        Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_events WHERE run_id = ?",
                Long.class, id);
        return count == null ? -1L : count;
    }

    @Test
    void postgresContainerIsReadyAndQueryWorks() {
        assertThat(PG.isRunning()).isTrue();
        assertThat(PG.getJdbcUrl())
                .startsWith("jdbc:postgresql://");
        assertThat(PG.getMappedPort(5432)).isPositive();
        assertThat(jdbc.queryForObject(
                "SELECT 1", Integer.class)).isEqualTo(1);
    }

    @Test
    void insertedRowIsVisibleBeforeCleanup() {
        jdbc.update(
                "INSERT INTO audit_events(run_id, event_name) "
                + "VALUES (?, ?)",
                runId, "CREATED");

        assertThat(countFor(runId)).isEqualTo(1L);
    }

    @Test
    void cleanupByOwnerIdIsIdempotent() {
        jdbc.update(
                "INSERT INTO audit_events(run_id, event_name) "
                + "VALUES (?, ?)",
                runId, "DUPLICATE_CLEANUP_TEST");

        jdbc.update(
                "DELETE FROM audit_events WHERE run_id = ?", runId);
        jdbc.update(
                "DELETE FROM audit_events WHERE run_id = ?", runId);

        assertThat(countFor(runId)).isZero();
    }

    @Test
    void cleanupDoesNotDeleteAnotherOwnersRow() {
        String otherRunId = "it-other-" + UUID.randomUUID();
        try {
            jdbc.update(
                    "INSERT INTO audit_events(run_id, event_name) "
                    + "VALUES (?, ?)",
                    runId, "MY_EVENT");
            jdbc.update(
                    "INSERT INTO audit_events(run_id, event_name) "
                    + "VALUES (?, ?)",
                    otherRunId, "OTHER_EVENT");

            jdbc.update(
                    "DELETE FROM audit_events WHERE run_id = ?", runId);

            assertThat(countFor(runId)).isZero();
            assertThat(countFor(otherRunId)).isEqualTo(1L);
        } finally {
            jdbc.update(
                    "DELETE FROM audit_events WHERE run_id = ?",
                    otherRunId);
        }
    }

    @Test
    void diagnosticSnapshotCanBeObtained() {
        String logs = PG.getLogs();
        assertThat(logs).isNotNull();
        assertThat(PG.isRunning()).isTrue();
        // Không assert text startup cụ thể vì khác image/version.
    }
}
```

### 7.6. Tại sao từng phần quan trọng?

- `static @Container` + `@Testcontainers`: Jupiter extension start/stop container quanh test class; các test methods share một PostgreSQL process.
- `@ServiceConnection`: Spring Boot tạo connection details từ **`PostgreSQLContainer`** (cần `spring-boot-testcontainers`); không cần hardcode URL, port hay password trong `spring.datasource.*`.
- `withLogConsumer(...)`: stream logs vào SLF4J từ startup. Với logger `tc.postgresql`, cấu hình log level test để xem chi tiết; không tự bật toàn bộ TRACE.
- `@RegisterExtension TestWatcher`: nếu **một method** fail, in phần tail của `PG.getLogs()`; callback bắt lỗi diagnostic riêng để không che assertion failure. Nó **không phải** cách duy nhất thu log khi lỗi ở `beforeAll`/container startup.
- `@BeforeEach`: một owner key ngẫu nhiên cho mỗi method; không phụ thuộc thứ tự chạy hoặc ID sequence.
- `@AfterEach`: delete đúng `run_id` và assert zero, dù test có assertion fail. Nếu cleanup fail, test sẽ báo thất bại thay vì im lặng.
- Test scoped cleanup kiểm rằng xóa **run A không xóa run B**, còn B được dọn trong `finally`, giảm rò rỉ fixture.
- Test diagnostic kiểm API `getLogs()` hoạt động, không gắn assertion quá chặt vào wording của image.
- `JdbcTemplate` thực thi SQL qua PostgreSQL thật; không phải in-memory fake. **Test này không dùng `@Transactional`**, nên cleanup SQL chạy và commit theo semantics của JDBC auto-commit/pool. Nếu thêm `@Transactional` lên test, delete trong `@AfterEach` có thể tham gia test transaction bị rollback — phải phân tích boundary trước.

**5 tests dự kiến PASS** trên môi trường có Docker, image có thể pull, PostgreSQL start và schema.sql chạy. Các test không cố tình gây startup failure trong happy-path suite. Không có stdout nghiệp vụ cố định; logs PostgreSQL/CI phụ thuộc image và mức logging.

### 7.7. Lệnh chạy

Tại thư mục project có `pom.xml`, cần **JDK 17+**, Maven và Docker:

```bash
docker info
mvn test
```

Chạy đúng class:

```bash
mvn -Dtest=PostgresDiagnosticsTest test
```

Nếu dự án có Maven Wrapper: `./mvnw test` hoặc `mvnw.cmd test` trên Windows. Với một JUnit test class, Maven Surefire thường hiển thị **Tests run: 5, Failures: 0, Errors: 0**. Lần chạy đầu có thể lâu hơn do pull image. Nếu Docker không sẵn sàng, test sẽ fail **ở giai đoạn khởi tạo Testcontainers**, không phải vì SQL assertion sai.

Không chạy `javac` trên class test riêng lẻ: cần Spring Boot, JUnit Jupiter, Testcontainers và PostgreSQL JDBC driver trên test classpath. POM/Maven xử lý dependency đúng.

## 8. Thực hành chẩn đoán startup lỗi mà không làm hỏng CI

Muốn hiểu một startup failure, tạo **một bài thử nghiệm riêng trên máy local/test branch**, không đưa container cố tình fail vào CI happy-path:

1. **Sai image tag**: thay `postgres:16-alpine` bằng một tag chắc chắn không có thật. Kỳ vọng lỗi ở **pull image**, không phải wait port. Đọc root cause registry/manifest.
2. **Sai wait condition**: chỉ trong test local, cấu hình `GenericContainer` có `Wait.forLogMessage` tìm một log marker không bao giờ xuất hiện với timeout ngắn. Kỳ vọng container có thể running nhưng **readiness timeout**.
3. **Sai schema.sql**: đặt DDL sai cú pháp trong **project test riêng**, container PostgreSQL đã ready nhưng Spring SQL initializer fail. Đây là **Spring context/DB initialization error**, không phải Docker startup failure.
4. **Sai password/URL**: cố cấu hình client khác dùng credentials sai. PostgreSQL container vẫn có thể ready; connection/authentication fail.
5. **CI không có Docker socket**: kiểm `docker info` tại runner. Đây là environment startup failure; không thử `chmod 666 /var/run/docker.sock` như giải pháp mặc định.
6. **Cố kéo image quá lớn**: không dùng trên shared CI chỉ để test timeout; kiểm cache/registry thay vì tăng timeout mọi bài.

### 8.1. Thu đủ thông tin cho một lỗi khó tái lập

Trong bug report/CI artifact, nên có:

- **Test class/method** hoặc phase bị lỗi (`beforeAll`, Spring context bootstrap, query assertion, `afterEach`).
- **Image repository + tag/digest**, module/version Testcontainers, Java/Spring Boot version.
- Docker version/context/provider và runner OS/architecture (**không** upload secret `DOCKER_HOST` nếu chứa thông tin nhạy cảm).
- Root cause exception đầu tiên ở stack trace: `ContainerLaunchException`, `PSQLException`, `BeanCreationException` hay registry error.
- **Container ID, exit code, OOMKilled, health/wait status** khi còn lấy được.
- **Redacted container log tail** và Testcontainers framework log quanh startup, không chỉ phần cuối Maven stack trace.
- Port mapping động, `@ServiceConnection`/DynamicPropertySource và SQL migration/init status.
- Đã xảy ra ở máy local, CI riêng, hay chỉ khi chạy cả suite/parallel?
- Cách tái hiện gọn (image, lệnh Maven, test class), deadline/timeout và tình trạng Docker daemon.

Đừng đưa toàn bộ `docker inspect` hoặc log raw có credentials, environment values, token, SQL binds chứa PII lên issue tracker công khai. Redact trước và phân quyền artifacts.

### 8.2. Bật log Testcontainers theo scope

Spring Boot/SLF4J logging có thể bật logger Testcontainers khi cần:

```properties
logging.level.org.testcontainers=DEBUG
logging.level.com.github.dockerjava=INFO
logging.level.tc.postgresql=INFO
```

Đây là snippet thuộc **`src/test/resources/application.properties`** khi muốn debug. Mức log và chính xác logger name có thể đổi giữa version. Dùng DEBUG có chọn lọc trong CI run chẩn đoán, không mặc định TRACE cho mọi build vì log có thể lớn và chứa dữ liệu nhạy cảm. Trong ví dụ, `Slf4jLogConsumer` gửi line vào logger tên `tc.postgresql`.

**Khi lỗi xảy ra trước Spring context**, cấu hình `application.properties` chưa chắc đã được áp dụng đủ sớm. Khi đó xem trực tiếp log Maven/JUnit, cấu hình SLF4J test runtime và environment logging ở Testcontainers; không kết luận “không có log” nghĩa container chưa ghi gì.

## 9. Dọn dữ liệu và Docker đúng khi CI chạy song song

Một static container chỉ shared trong một test class không tự đảm bảo isolation nếu:

- Hai test classes dùng **cùng PostgreSQL database/schema external**.
- Context reuse hoặc reusable container làm state tồn tại giữa suites.
- CI jobs song song cùng truy cập một service/volume/bucket.
- Background listener vẫn ghi sau khi `@AfterEach` đã xóa row.
- Test tạo table/index/role mới mà cleanup chỉ xóa data rows.

### Các cách cách ly theo mức chi phí

| Mức | Tài nguyên | Chi phí | Độ cô lập |
|---|---|---|---|
| Per method container | Mỗi JUnit method một DB container | Cao | Cao, nhưng phải tránh global external state |
| Per class static container | Một DB container cho một class | Trung bình | Chỉ tốt khi mỗi method có owner key/cleanup |
| Per suite shared container | Một container cho nhiều classes | Thấp hơn | Cần database/schema/run IDs riêng |
| External shared staging DB | DB được dùng chung | Thấp cho startup, rủi ro cao | Chỉ khi có tenant/schema/key isolation và quyền an toàn |
| Reusable container local | Container sống qua JVM | Nhanh khi lặp local | **State tồn dư có chủ đích**; tránh làm giả định CI |
| Ephemeral CI worker + container | Runner và Docker resources riêng | Tùy pipeline | Tốt nếu teardown thật và không dùng shared external resources |

Nếu cần reset schema mỗi method, chạy migrations trên DB/schema **của riêng test**, không dùng `DROP SCHEMA public CASCADE` trên cluster khác. Với Kafka/Redis/Mongo, mỗi backend có cách dọn khác: dùng topic/consumer group hoặc key prefix/test owner, không “dùng Docker stop là xong” khi các dịch vụ khác đang tồn tại độc lập.

### Thứ tự cleanup khi có dependencies

Ví dụ một test tạo DB + Kafka topic + application container:

```text
1. Ngừng/cancel publishers, consumers, async jobs của test.
2. Await in-flight operations hoàn tất với deadline.
3. Delete test-owned rows/messages/files/cache keys nếu resource còn dùng chung.
4. Đóng clients/pools, giải phóng connection/subscription.
5. Để JUnit/Testcontainers dừng container đúng owner/lifecycle.
6. Kiểm logs/failures; archive redacted diagnostic và teardown CI resources.
```

Không dừng DB container **trước** khi cleanup SQL trên chính DB đó. Với resource mà container hoàn toàn sở hữu (filesystem ephemeral và không share), việc dừng/xóa container có thể đủ, nhưng đừng tổng quát hóa sang named volume hoặc shared environment.

## 10. Startup troubleshooting theo triệu chứng

| Triệu chứng | Kiểm tra đầu tiên | Khắc phục có nguyên nhân |
|---|---|---|
| `Could not find a valid Docker environment` | `docker info`, daemon/socket/context, runner permission | Bật Docker daemon, sửa CI mount/permissions theo policy |
| `manifest unknown` / image pull denied | Repository/tag/registry auth/platform | Dùng tag hợp lệ, registry credentials an toàn, đúng architecture |
| Ryuk container lỗi startup | Docker socket/network/security policy | Sửa runner/Docker config; không disable Ryuk chỉ để che lỗi |
| `ContainerLaunchException` khi start | Root cause + `docker logs`/exit code/mount/OOM | Sửa env, image, mount, RAM/disk hoặc init script |
| Container running nhưng wait timeout | Exposed port, health URL, wait regex và log | Chọn Wait strategy đúng dịch vụ; tăng timeout chỉ khi start chậm có thật |
| `Connection refused` | mapped port, host, readiness, Docker network | Dùng container.getHost/getMappedPort hoặc ServiceConnection |
| `password authentication failed` | DB user/password, connection details precedence | Sửa credentials hoặc @ServiceConnection config, không tăng timeout |
| `relation ... does not exist` | schema.sql/Flyway, database/schema name | Chạy SQL init/migrations đúng database |
| Local pass CI fail | Docker version/architecture, resource limits, shared runner | So môi trường, pin image, thu logs/metrics, giảm parallel load |
| Tests pass riêng nhưng fail cả suite | Data bleed, Spring context cache, reuse, parallel | testRunId, cleanup và isolation theo class/run |
| Docker disk full | `docker system df`, volume/image cache | Xóa **resources test-owned đã xác minh**, không prune bừa |
| Chạy lại test bị duplicate key | DB static/reused, cleanup chưa thành công | Scope DELETE/rollback, verify zero, CI report cleanup |
| Không thấy logs khi startup fail | Container bị xóa trước `docker logs`, logger chưa bật | Testcontainers startup logs/CI console, log consumer trước start |
| Chờ 120s vẫn fail sau tăng timeout | Wrong wait/credentials/schema, không phải chậm | Đọc root cause thay vì tiếp tục tăng deadline |

## 11. Checklist trước khi merge test dùng Testcontainers

- [ ] Tôi biết **container nào do JUnit extension quản lý**, container nào do code tự start/stop.
- [ ] `static @Container` dùng chung database cho test methods; đã thiết kế fixture isolation.
- [ ] Container/service được cấu hình với image tag/digest rõ ràng, không mặc định `:latest`.
- [ ] Docker daemon, registry và architecture được CI runner hỗ trợ.
- [ ] Không hardcode host port; dùng `getMappedPort`, `getJdbcUrl`, `@ServiceConnection` hoặc `@DynamicPropertySource`.
- [ ] Wait strategy thực sự đại diện readiness của service; không chữa bằng `Thread.sleep`.
- [ ] Startup timeout phù hợp và có log/diagnostic khi timeout.
- [ ] Test có thể chụp stdout/stderr bằng `getLogs`, log consumer hoặc Docker command.
- [ ] TestWatcher/diagnostics không làm mất root cause lỗi test; có phương án xem lỗi startup **trước** JUnit methods.
- [ ] Secrets/PII được redact khỏi CI logs, URLs và report.
- [ ] Test tạo dữ liệu có owner key/namespace và có cleanup idempotent.
- [ ] `@AfterEach` xóa đúng dữ liệu và **verify zero**; không silently ignore cleanup failure.
- [ ] Nếu có background task, đã await/cancel trước cleanup.
- [ ] Cleanup không phụ thuộc test execution order, không dùng wildcard trên shared database.
- [ ] Không dùng `@DirtiesContext` như phương án reset Docker/database data.
- [ ] Không disable resource reaper hoặc bật reusable container trên shared CI thiếu chiến lược cleanup.
- [ ] Nếu có volume/network/bind mount, đã kiểm quyền sở hữu và teardown thực.
- [ ] Đã thử chạy lại suite, chạy cả class và CI (khi có Docker) để phát hiện data leak.
- [ ] Log và lỗi startup được phân loại theo **Docker/image, process, readiness, Spring context, database schema và test logic**.

**Kết luận:** Testcontainers giải quyết việc **cung cấp service thật trong test**, nhưng không tự giải quyết mọi bài toán dọn dữ liệu, quan sát log và ổn định startup. Test đáng tin cần: **lifecycle rõ, test-owned data, scoped cleanup, readiness đúng, log tại thời điểm lỗi và chẩn đoán theo lớp**. Khi test không start được, hãy tìm root cause ở Docker/image/entrypoint/wait/Spring datasource/schema trước khi tăng timeout hoặc xóa tài nguyên bừa bãi.

### Nguồn chính thức

- [Testcontainers for Java — JUnit Jupiter integration](https://java.testcontainers.org/test_framework_integration/junit_5/)
- [Testcontainers for Java — Accessing container logs](https://java.testcontainers.org/features/container_logs/)
- [Testcontainers for Java — Waiting for containers to start or be ready](https://java.testcontainers.org/features/startup_and_waits/)
- [Testcontainers for Java — Custom configuration and cleanup](https://java.testcontainers.org/features/configuration/)
- [Spring Boot 3.5 — Testcontainers and service connections](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Testcontainers for Java — PostgreSQL module](https://java.testcontainers.org/modules/databases/postgres/)
- [Docker — `docker logs`](https://docs.docker.com/reference/cli/docker/container/logs/)
