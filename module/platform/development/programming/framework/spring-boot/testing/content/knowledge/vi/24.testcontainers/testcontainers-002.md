# Dependency Testcontainers, JUnit integration và môi trường Docker

**Testcontainers** giúp bài kiểm thử Java khởi tạo và quản lý một dịch vụ thật trong container — chẳng hạn PostgreSQL, MySQL, Redis, MongoDB, Kafka hoặc một HTTP mock server — thay vì chỉ dùng mock, database H2 hoặc dựa vào một dịch vụ được cài thủ công trên máy developer. Trong Spring Boot, Testcontainers đặc biệt hữu ích để bắt những lỗi mà unit test không quan sát được: SQL dialect, constraint, message broker protocol, serializer của driver, kết nối qua host/port động và cấu hình khởi động ứng dụng.

Tuy nhiên, thêm một dependency Testcontainers vào Gradle **không tự khởi động Docker**. JUnit extension có lifecycle riêng; Spring Boot cần được cung cấp **connection details** của service; Docker engine và image registry phải truy cập được. Một test dùng `@Container` mà thiếu `@Testcontainers` có thể không được quản lý; một test có `@ServiceConnection` nhưng quên `spring-boot-testcontainers` có thể không compile; một test với PostgreSQLContainer nhưng thiếu JDBC driver sẽ tạo được container mà Spring vẫn không mở được connection.

Bài này thuộc phần **Testcontainers** của module **Spring Boot – testing**. Ví dụ đầy đủ sử dụng **Java 17+, Spring Boot 3.5.16, Testcontainers 1.21.x, JUnit Jupiter 5, Spring JDBC và PostgreSQL 16**. Phiên bản được chọn để cả import Java lẫn Gradle coordinates nhất quán. Testcontainers 2.x đổi tên module và package; cần xem mục 5 trước khi nâng cấp. Ví dụ dành cho môi trường test độc lập, không kết nối production.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

- Giải thích Testcontainers chạy backend thật bằng Docker API và khác với việc mock `JdbcTemplate`/repository.
- Phân biệt các dependency `spring-boot-starter-test`, `spring-boot-testcontainers`, `org.testcontainers:junit-jupiter`, module theo database và JDBC driver.
- Viết Gradle/Maven dependency đúng theo **Spring Boot BOM** và nhánh Testcontainers.
- Cài/kiểm môi trường Docker trên Linux, macOS, Windows/WSL2 và CI.
- Dùng JUnit Jupiter `@Testcontainers` + `@Container`, phân biệt static container và instance container.
- Dùng Spring Boot `@ServiceConnection` hoặc Spring Test `@DynamicPropertySource` đúng vai trò.
- Hiểu container được quản lý bởi JUnit khác container được quản lý như **Spring bean** ở lifecycle và context cache.
- Chạy integration test dùng PostgreSQL container, schema.sql, JdbcTemplate và assertions trên database thật.
- Nhận diện lỗi Docker daemon unavailable, image pull, port mapping, Ryuk, driver mismatch, `Failed to load ApplicationContext` và shared test state.
- Tối ưu startup, isolation, parallel test, cleanup, giới hạn đặc quyền và bảo mật credentials.
- Biết khi nào cần một test full integration và khi nào unit/slice test là đủ.

## 2. Testcontainers giải quyết bài toán gì?

Xét repository có lệnh PostgreSQL:

```sql
INSERT INTO books (isbn, title)
VALUES ('ISBN-001', 'Spring Boot Testing')
RETURNING id;
```

Một unit test với Mockito có thể chứng minh repository **gọi** `JdbcTemplate`, nhưng không bảo đảm SQL tương thích PostgreSQL, schema có UNIQUE index, connection pool kết nối đúng hay transaction rollback. H2 cũng có thể chạy syntax/constraint khác PostgreSQL. Testcontainers tạo **PostgreSQL thật trong một container ephemeral**, để test quan sát hành vi qua JDBC driver thật.

Luồng:

```text
./gradlew test
     |
     v
JUnit Jupiter / Spring TestContext
     |
     +--> Testcontainers Java library
     |       |
     |       +--> Docker API -> PostgreSQL container
     |       |                  port 5432 bên trong
     |       |                  host port ngẫu nhiên
     |       |
     |       +--> tạo JDBC URL, username, password
     |
     +--> Spring Boot DataSource / JdbcTemplate
     |       |
     |       v
     +--> repository thật -> PostgreSQL thật
     |
     +--> JUnit assertions trên rows / constraints
     |
     +--> lifecycle cleanup container
```

**Testcontainers không phải embedded database chạy trong JVM.** Nó đòi một container runtime tương thích Docker API. Một bộ test có thể chạy hoàn toàn trên laptop mà không cần cài PostgreSQL trực tiếp, nhưng cần Docker engine hoạt động hoặc một container runtime/remote service được Testcontainers hỗ trợ.

### 2.1. Test này chứng minh những gì?

- Database engine/version gần với production hơn một fake in-memory.
- JDBC driver, SQL syntax, identity, constraints và repository logic được thực thi.
- Spring DataSource/connection pool kết nối tới host/port runtime đúng.
- Migration/init scripts có thể được kiểm cùng ứng dụng.
- Một số giao thức, lỗi kết nối và transaction semantics có thể được quan sát.

### 2.2. Test này chưa tự chứng minh gì?

- Network proxy, TLS, firewall hoặc quyền database trên production nếu container test không mô phỏng.
- High availability/replication/cluster theo kiến trúc thực.
- Vận hành production ở tải lớn, cùng dữ liệu và scale thật.
- Business workflow đã đúng nếu test chỉ gọi `SELECT 1`.
- Dữ liệu luôn sạch giữa các method nếu test không isolation/cleanup.

## 3. Phân loại dependency: thứ gì cung cấp khả năng nào?

| Dependency | Vai trò | Có bắt buộc trong mọi test không? |
|---|---|---|
| `spring-boot-starter-test` | JUnit Jupiter, Spring Test, AssertJ/Mockito và bộ test Boot | Thường dùng cho ứng dụng Spring Boot |
| `org.testcontainers:junit-jupiter` | JUnit 5 extension cho `@Testcontainers`/`@Container`, nhánh **1.x** | Khi muốn JUnit quản lý container fields |
| `org.testcontainers:postgresql` | `PostgreSQLContainer`, nhánh **1.x** | Khi test dùng Postgres module |
| `org.testcontainers:testcontainers` | Core Java Testcontainers; thường là transitively required | Không cần khai báo riêng nếu module đã mang core đúng |
| `org.springframework.boot:spring-boot-testcontainers` | `@ServiceConnection`, container-as-bean, `@ImportTestcontainers` | Khi dùng tính năng tích hợp này của Spring Boot |
| `org.postgresql:postgresql` | **JDBC driver** kết nối PostgreSQL | Có nếu test dùng JDBC PostgreSQL |
| `spring-boot-starter-jdbc` | DataSource, HikariCP, JdbcTemplate, transaction support | Khi ứng dụng dùng JDBC |
| `testcontainers-bom` | Quản lý version nhóm Testcontainers | Dùng khi không có BOM phù hợp/đã cố ý override |

**Ba dependency dễ bị nhầm:**

1. `spring-boot-starter-test` có JUnit, **không có nghĩa đã có mọi module Testcontainers**.
2. `junit-jupiter` của Testcontainers là **extension quản lý container**, không phải chính JUnit engine. `@Test` của JUnit đến từ `org.junit.jupiter.api.Test`.
3. `spring-boot-testcontainers` cung cấp integration của Boot, **không thay thế** database module/JDBC driver. Thiếu `postgresql` module sẽ không có `PostgreSQLContainer`; thiếu `org.postgresql` driver thì JDBC connection không hoạt động.

Đặt các artifact test-only dưới `testImplementation`/`testRuntimeOnly` để không đưa Docker/Testcontainers vào production runtime một cách vô tình.

## 4. BOM: phải thống nhất phiên bản

Với **Spring Boot 3.5.x**, BOM của Boot quản lý Testcontainers **1.21.x** (ví dụ tài liệu dependency coordinates 3.5.16 ghi 1.21.4). Vì vậy một project dùng Spring Boot Gradle plugin và dependency management thông thường có thể viết:

```groovy
testImplementation 'org.testcontainers:junit-jupiter'
testImplementation 'org.testcontainers:postgresql'
testImplementation 'org.springframework.boot:spring-boot-testcontainers'
```

mà không ghi version từng dependency. Gradle sẽ resolve chúng theo BOM/project policy.

**Không được** giữ một artifact 1.x rồi ép một module khác lên 2.x mà chưa kiểm API, package và transitive dependencies. Lỗi thường gặp là `ClassNotFoundException`, `NoClassDefFoundError`, `NoSuchMethodError`, hoặc import `PostgreSQLContainer` bị đổi package.

Để xem phiên bản thực sự trên Gradle:

```bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency testcontainers --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency postgresql --configuration testRuntimeClasspath
```

Nếu dự án đã có corporate BOM, version catalog (`libs.versions.toml`), Gradle platform hoặc dependency constraints, hãy ưu tiên **một nguồn version management rõ ràng** và xem dependency graph trước khi thêm override.

## 5. Testcontainers 1.x và 2.x: khác biệt cần nhớ

**Nhánh 1.x dùng trong bài runnable:**

```groovy
testImplementation 'org.testcontainers:junit-jupiter'
testImplementation 'org.testcontainers:postgresql'
```

Java:

```java
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
```

**Nhánh 2.x trong tài liệu Testcontainers mới hơn** có các module đổi tên:

```groovy
// Chỉ minh họa tọa độ nhánh 2.x.
// Không thay vào build Boot 3.5.x bên dưới mà chưa nâng BOM/API.
testImplementation 'org.testcontainers:testcontainers-junit-jupiter'
testImplementation 'org.testcontainers:testcontainers-postgresql'
```

Class PostgreSQL được di chuyển sang package theo module, ví dụ:

```java
// Import của nhánh 2.x (minh họa, không thuộc ví dụ 1.x):
import org.testcontainers.postgresql.PostgreSQLContainer;
```

**Nhìn README theo bản mới nhất không có nghĩa các dependencies đó phù hợp trực tiếp với BOM cũ.** Khi nâng từ 1.x lên 2.x, cập nhật **cùng lúc** các artifacts, imports, version constraints, JUnit integration và Boot compatibility. Testcontainers 2.x bỏ JUnit 4 support và di chuyển container classes/module coordinates; muốn nâng nhánh hãy làm theo migration guide và chạy lại toàn bộ integration suite.

Lỗi mẫu:

```text
error: package org.testcontainers.containers does not contain PostgreSQLContainer
```

có thể do đã dùng 2.x module nhưng giữ source import 1.x. Ngược lại, `org.testcontainers.postgresql.PostgreSQLContainer` không tồn tại trong 1.x. **Không “sửa” bằng cách thêm cả hai nhánh vào classpath**.

## 6. Gradle hay Maven: chỉ cần một cấu hình được kiểm soát

### 6.1. Gradle Boot 3.5.x

Những thành phần chính:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.postgresql:postgresql'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là phần cấu hình cốt lõi; `build.gradle` hoàn chỉnh ở mục 15 có thêm `repositories`, `java.toolchain` và metadata. Test driver `org.postgresql:postgresql` đặt ở `testRuntimeOnly` vì chỉ các integration tests trong bài cần PostgreSQL.

### 6.2. Maven Boot 3.5.x

Nếu dùng `spring-boot-starter-parent` hoặc một `dependencyManagement` chuẩn Boot, các dependency sau thường không cần chỉ định version:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
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
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
```

**Đây là snippet của `pom.xml`, không phải POM độc lập**: project còn cần `modelVersion`, `groupId`, `artifactId`, parent/BOM, Java version và Maven plugins. Dùng Maven Surefire/JUnit Platform tương thích nếu không kế thừa parent Boot. JUnit 4 `@RunWith` không phải cách tích hợp cho những ví dụ `@Testcontainers` của JUnit Jupiter.

## 7. Docker engine: phụ thuộc ngoài JVM

Testcontainers cần một runtime tương thích Docker API. Trong workflow phổ biến:

- **Linux:** Docker Engine chạy, user có quyền truy cập socket/daemon.
- **Windows/macOS:** Docker Desktop chạy Linux containers; trên Windows, WSL2 backend thường là lựa chọn phổ biến.
- **CI Linux:** runner có Docker daemon/sidecar/remote Docker hoặc dịch vụ Testcontainers-compatible được cấu hình.
- **Một số runtime thay thế:** Podman/Colima/Rancher Desktop có thể cần cấu hình socket/host/privileged services riêng; mức tương thích không được giả định hoàn toàn giống Docker Engine.

**Không chỉ cài Docker CLI.** Một lệnh `docker --version` chạy được chỉ chứng minh client binary có tồn tại; nó **không chứng minh Docker daemon đang chạy**.

Các kiểm tra trước khi chạy JUnit:

```bash
docker version
docker info
docker run --rm hello-world
docker pull postgres:16-alpine
```

`docker version`/`docker info` phải thấy **Server**/daemon thông tin phù hợp. `docker run` xác minh có thể tạo container. `docker pull` kiểm registry, DNS, proxy, authentication và tag. Trên máy có hạn chế network, image có thể được cung cấp qua registry mirror mà team cho phép.

Không cần chạy `docker compose up` để có PostgreSQL của ví dụ: **Testcontainers tự tạo container và host port**. Nếu Docker Desktop bị dừng, Gradle vẫn có thể compile Java nhưng integration tests sẽ thất bại ở container startup.

## 8. Windows + WSL2: kiểm ở đúng môi trường chạy test

Một máy Windows thường có nhiều nơi chạy Gradle:

1. PowerShell/IntelliJ trên Windows host.
2. Terminal Ubuntu/WSL2.
3. Dev Container chạy trong Docker.
4. Remote CI/SSH environment.

Testcontainers phải truy cập được Docker API **từ nơi JVM/JUnit thực sự chạy**, không phải chỉ từ terminal bạn vừa kiểm.

Trên PowerShell:

```powershell
docker version
docker info
.\gradlew.bat test --tests com.example.containerlesson.PostgresJunitLifecycleTest
```

Trong WSL2 Linux shell:

```bash
docker version
docker info
./gradlew test --tests com.example.containerlesson.PostgresJunitLifecycleTest
```

Nếu Docker Desktop dùng WSL2 integration, cần bật integration cho distro chạy Gradle và bảo đảm đang ở **Linux containers mode**. Không tự bật Docker daemon TCP không TLS trên `0.0.0.0:2375` để “sửa nhanh” một lỗi kết nối: đó là exposure nguy hiểm, có thể trao quyền điều khiển host.

**Bẫy phổ biến:** IDE chạy JUnit bằng Windows JVM, terminal lại là WSL2 và Docker chỉ hoạt động từ WSL. Hãy xác định chính xác JVM executable, Docker context/socket và environment variables của IDE/Gradle daemon. Khởi động lại Gradle daemon/IDE khi thay Docker-related environment nếu nó giữ cấu hình cũ.

## 9. JUnit Jupiter integration: `@Testcontainers` và `@Container`

Đối với **Testcontainers 1.x**, annotation:

```java
@Testcontainers
class MyIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void test() {
        assertTrue(POSTGRES.isRunning());
    }
}
```

là snippet thiếu imports, không phải file hoàn chỉnh. Ý nghĩa:

- `@Testcontainers` kích hoạt **JUnit Jupiter extension**.
- `@Container` đánh dấu field mà extension quản lý start/stop.
- **Static field:** một container được start trước tất cả test methods trong class và stop sau class.
- **Instance field:** JUnit mặc định tạo instance test class cho mỗi method; container field không static được start/stop quanh từng method.
- `@Test` vẫn là annotation JUnit Jupiter, không phải của Testcontainers.
- `@Container` không tự tạo database table hoặc dọn từng row giữa test methods. Một static Postgres giữ dữ liệu giữa các methods cho đến khi stop.

### 9.1. Static hay instance?

| Mục tiêu | Static `@Container` | Instance `@Container` |
|---|---|---|
| Startup cost | Thường ít hơn trong một class | Thường cao hơn vì restart theo method |
| Data isolation mặc định | **Không** reset data giữa methods | Container mới mỗi method dễ cô lập hơn |
| JUnit lifecycle | BeforeAll/AfterAll của extension | BeforeEach/AfterEach của extension |
| Spring context cache | Có nguy cơ container bị stop trước cached context hết vòng đời | Còn dễ mâu thuẫn hơn nếu context reuse |
| Parallel methods | Cần bảo vệ shared DB state | Phù hợp hơn khi mỗi method có service riêng, vẫn kiểm parallel support |

Testcontainers JUnit 5 extension **không cam kết hỗ trợ chạy tests song song như một guarantee chung**; cần thận trọng với parallel mode và lifecycles. Nếu cần throughput cao, cân nhắc chia method theo independent schema/DB hoặc dùng quản lý container theo Spring context.

### 9.2. Không gọi `start()` hai lần

Khi dùng `@Testcontainers` + `@Container`, để extension start/stop. Không cần gọi `POSTGRES.start()` trong `@BeforeAll`. Nếu bạn chọn **manual lifecycle** (ví dụ container static singleton), phải chịu trách nhiệm start/stop và lưu ý Spring context cache; không trộn tùy tiện hai mô hình.

### 9.3. Chỉ skip khi thật sự muốn

Một số phiên bản Testcontainers có tùy chọn `@Testcontainers(disabledWithoutDocker = true)` để bỏ qua khi Docker không sẵn. Nó hữu ích cho những test optional trên máy developer, **nhưng có thể khiến CI báo xanh khi integration tests quan trọng bị skip**. Với pipeline phải bảo vệ database contract, ưu tiên **fail rõ ràng** nếu Docker không sẵn.

## 10. Kết nối Spring Boot với container qua `@ServiceConnection`

Spring Boot 3.5 có integration tự động qua `@ServiceConnection`:

```java
@Container
@ServiceConnection
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
```

Đây là snippet đặt trong test class có `@Testcontainers` và imports đúng. Spring Boot tạo `JdbcConnectionDetails` (và những connection details tương ứng nếu có) để auto-configuration dùng host, port, username, password của container.

**Điều bắt buộc:**

- Dependency `org.springframework.boot:spring-boot-testcontainers` ở test classpath.
- Một container class/image mà `ContainerConnectionDetailsFactory` nhận diện.
- JUnit/Boot phải quản lý **lifecycle** của container, không chỉ có annotation metadata.
- DataSource/driver đúng loại, với PostgreSQL là `org.postgresql:postgresql`.
- Nếu có nhiều DataSource/containers, phải chỉ rõ bean/connection mục tiêu và kiểm auto-configuration, không giả định mọi bean dùng cùng container.

**`@ServiceConnection` không phải tên khác của `@Testcontainers`.** Annotation đầu cho Spring Boot biết *kết nối service nào*; annotation sau cho JUnit biết *container field nào cần quản lý*. Có thể dùng chúng cùng nhau hoặc dùng container **Spring bean** có lifecycle do Boot quản lý.

Trong project runnable bên dưới, bài Spring integration test dùng **container dạng Spring bean** để tránh cached context giữ connection đến container đã bị JUnit stop.

## 11. `@DynamicPropertySource`: thay thế khi cần tự truyền properties

Spring Test hỗ trợ:

```java
// Snippet bên trong một test class có static PostgreSQLContainer<?> POSTGRES
// được JUnit hoặc setup phù hợp start trước khi Spring dùng properties.
@DynamicPropertySource
static void postgresProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
    registry.add("spring.datasource.username", POSTGRES::getUsername);
    registry.add("spring.datasource.password", POSTGRES::getPassword);
}
```

`@DynamicPropertySource` nhận suppliers cho properties động; nó **không tự start container**. Ví dụ test class dùng JUnit static `@Container` phải có `@Testcontainers` để extension start container; nếu không thì các suppliers có thể trỏ tới container chưa chạy.

| Tiêu chí | `@ServiceConnection` | `@DynamicPropertySource` |
|---|---|---|
| Công việc chính | Cấp connection details cho Boot auto-config | Đăng ký dynamic Spring Environment properties |
| Spring Boot module | Cần `spring-boot-testcontainers` | Có Spring Test là dùng được |
| Nhận diện backend | Container type/image/`name` | Bạn tự chọn property names |
| Config driver URL/user/pass | Thường tự nhận với supported type | Tự đăng ký đủ properties |
| Hệ service không có factory | Có thể cần custom factory/name | Linh hoạt với properties của ứng dụng |
| Lifecycle | **Không tự do một annotation mà bảo đảm mọi lifecycle**; tùy JUnit hay Spring bean | Không quản lý lifecycle |
| Property precedence | Connection details được Boot ưu tiên cho auto-config tương ứng | Dynamic properties có precedence cao trong Environment |

**Không dùng cả hai mà không hiểu precedence:** `@ServiceConnection` sinh `ConnectionDetails` có thể ưu tiên hơn `spring.datasource.url` bạn vừa đăng ký. Khi debug “tại sao URL khác”, kiểm connection factory và bean source, không chỉ đọc application-test.yml.

### 11.1. Container dùng image mirror/custom name

Nếu dùng `GenericContainer` cho Redis, một `@Bean` có return type chung không cho Boot suy ra image service. Có thể dùng `@ServiceConnection(name = "redis")` khi factory hỗ trợ. Với typed `PostgreSQLContainer`, Boot nhận ra loại JDBC database dễ hơn. Đừng giả định mọi image tự được support mà không có connection details factory.

## 12. Spring-managed container: điểm tinh tế của context cache

Spring TestContext có **ApplicationContext cache** để reuse context giữa các test classes. Trong khi đó:

- JUnit extension với static `@Container` stop container **sau test class**.
- Cached Spring context có thể sống **lâu hơn test class**.
- Test class khác reuse context cũ, DataSource/Hikari pool vẫn trỏ tới host/port của container đã stop.
- Lỗi `Connection refused` hoặc cleanup callback fail có thể xuất hiện không ổn định.

Spring Boot 3.5 khuyến nghị **quản lý container như một Spring bean** hoặc dùng `@ImportTestcontainers` khi context cần tồn tại tương ứng với container.

**Container bean:**

```java
@TestConfiguration(proxyBeanMethods = false)
class PostgresTestConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }
}
```

Đây là snippet; file runnable có nested configuration trong `PostgresSpringIntegrationTest`. Khi container là bean, Boot start trước các application beans phụ thuộc và stop sau khi bean teardown; lifecycle đi cùng cached ApplicationContext.

**Chọn giữa hai mẫu:**

- Test plain JUnit hoặc đơn lẻ, không có cached Spring context: dùng `@Testcontainers`/`@Container`.
- Một Spring Boot context có nhiều beans cần DB trong suốt lifecycle: ưu tiên container bean + `@ServiceConnection`.
- Test slice/class chỉ dùng một container static và không reuse context có thể dùng JUnit extension, nhưng phải hiểu giới hạn.
- Reuse một container giữa classes chỉ nên thiết kế khi DB data isolation và lifecycle đúng.

Không dùng `@DirtiesContext` tràn lan chỉ để giải quyết container đã bị stop; nó tốn thời gian khởi động và chưa chắc giải quyết data contamination.

## 13. Demo runnable: PostgreSQL thật và repository thật

Project minh họa có hai cấp test:

1. **Plain JUnit Jupiter**: `PostgresJunitLifecycleTest` dùng `@Testcontainers` + static `@Container`, kiểm kết nối PostgreSQL qua `DriverManager`. Không nạp Spring.
2. **Spring Boot integration**: `PostgresSpringIntegrationTest` dùng container khai báo trong `@TestConfiguration` + `@ServiceConnection`, kiểm schema, generated key và unique constraint qua `JdbcTemplate`.

Cấu trúc:

```text
testcontainers-dependencies-demo/
  settings.gradle
  build.gradle
  src/main/java/com/example/containerlesson/
    ContainerLessonApplication.java
    BookRepository.java
  src/main/resources/
    schema.sql
  src/test/java/com/example/containerlesson/
    PostgresJunitLifecycleTest.java
    PostgresSpringIntegrationTest.java
```

**Phạm vi:** Java 17, Gradle 8.x tương thích với Boot plugin, Docker Linux container engine, PostgreSQL image `postgres:16-alpine`, Testcontainers theo BOM Boot 3.5.16. Không có dữ liệu/credential production. Mỗi test class sử dụng database/container riêng theo lifecycle; dữ liệu trong `PostgresSpringIntegrationTest` được reset trước từng method.

## 14. Project Gradle hoàn chỉnh

**`settings.gradle`**

```groovy
rootProject.name = 'testcontainers-dependencies-demo'
```

**`build.gradle`**

```groovy
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.postgresql:postgresql'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Vì sao không có version ở từng dependency?** Spring Boot 3.5.16 dependency management đã cấp versions phù hợp. Dùng Boot plugin và `io.spring.dependency-management` ở đây để giữ ví dụ dễ hiểu. Nếu build của công ty dùng Gradle native `platform(...)`, version catalog, security constraints hoặc version lockfiles, phải tuân theo cách đó thay vì copy plugin setup nguyên vẹn.

**Vì sao JDBC driver test-only?** Project chỉ tập trung vào integration tests. Nếu ứng dụng thực cần chạy PostgreSQL trong production, hãy thêm driver như một **runtime dependency** và cấu hình production DataSource an toàn theo môi trường; **không** cấu hình URL production ngay trong test. Bản demo không thiết kế để `bootRun` độc lập mà không có DataSource ngoài.

## 15. Application và SQL schema

**`src/main/java/com/example/containerlesson/ContainerLessonApplication.java`**

```java
package com.example.containerlesson;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContainerLessonApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContainerLessonApplication.class, args);
    }
}
```

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    isbn VARCHAR(40) NOT NULL UNIQUE,
    title VARCHAR(200) NOT NULL
);
```

**Chú ý init schema trên PostgreSQL:** Spring Boot mặc định chỉ thực hiện basic SQL initialization cho **embedded database** theo chính sách phù hợp; PostgreSQL container là database ngoài JVM, nên test Spring ở mục 18 đặt `spring.sql.init.mode=always` để chạy `schema.sql`. Nếu không, bạn có thể gặp `relation "books" does not exist` mặc dù DataSource đã connect thành công.

Trong hệ thống thật, nên để Flyway/Liquibase migration là nguồn chân lý thay vì sao chép DDL vào schema.sql. Bài này dùng schema.sql để người học tập trung vào Testcontainers dependencies và JUnit lifecycle.

## 16. Repository: JDBC thực, không Mockito

**`src/main/java/com/example/containerlesson/BookRepository.java`**

```java
package com.example.containerlesson;

import java.sql.PreparedStatement;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class BookRepository {

    private final JdbcTemplate jdbc;

    public BookRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public long create(String isbn, String title) {
        KeyHolder holder = new GeneratedKeyHolder();

        int affected = jdbc.update(connection -> {
            PreparedStatement statement =
                    connection.prepareStatement(
                            """
                            INSERT INTO books (isbn, title)
                            VALUES (?, ?)
                            """,
                            new String[] {"id"});
            statement.setString(1, isbn);
            statement.setString(2, title);
            return statement;
        }, holder);

        if (affected != 1) {
            throw new IllegalStateException(
                    "Expected one inserted book");
        }

        Number key = holder.getKey();
        if (key == null) {
            throw new IllegalStateException(
                    "PostgreSQL did not return a generated id");
        }
        return key.longValue();
    }

    public String findTitle(String isbn) {
        return jdbc.queryForObject(
                "SELECT title FROM books WHERE isbn = ?",
                String.class, isbn);
    }

    public long count() {
        Long rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM books", Long.class);
        if (rows == null) {
            throw new IllegalStateException(
                    "Count query unexpectedly returned null");
        }
        return rows;
    }
}
```

Các điểm quan trọng:

- `JdbcTemplate` được Spring auto-configure từ DataSource của PostgreSQL container.
- Mọi giá trị input đi qua `PreparedStatement`, không nối chuỗi SQL thủ công.
- `KeyHolder` đọc ID do **PostgreSQL** sinh, không giả định ID luôn bằng 1.
- `UNIQUE(isbn)` được database thật thực thi; Spring chuyển SQL exception phù hợp thành `DataAccessException`.
- Code có thể compile trên Java 17 với Spring JDBC 6.2.x, không cần ORM/JPA hoặc HTTP server.
- Test Spring sau đây chạy repository thật, không dùng Mockito stub trả key/rows.

## 17. Plain JUnit: kiểm JUnit extension và Docker port động

**`src/test/java/com/example/containerlesson/PostgresJunitLifecycleTest.java`**

```java
package com.example.containerlesson;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
class PostgresJunitLifecycleTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("jupiter_demo")
                    .withUsername("test")
                    .withPassword("test");

    @Test
    void startsPostgresAndExposesMappedPort()
            throws Exception {

        assertTrue(POSTGRES.isRunning());
        assertTrue(POSTGRES.getMappedPort(5432) > 0);
        assertTrue(POSTGRES.getJdbcUrl()
                .startsWith("jdbc:postgresql:"));

        try (Connection connection = DriverManager.getConnection(
                    POSTGRES.getJdbcUrl(),
                    POSTGRES.getUsername(),
                    POSTGRES.getPassword());
             PreparedStatement statement =
                    connection.prepareStatement("SELECT 1");
             ResultSet rows = statement.executeQuery()) {

            assertTrue(rows.next());
            assertEquals(1, rows.getInt(1));
        }
    }
}
```

### 17.1. Test này kiểm điều gì?

1. JUnit 5 extension được load; `@Container` start container static trước test.
2. Docker image PostgreSQL khởi động và nhận connection.
3. Testcontainers expose container port 5432 qua **host port động**, không hard-code `localhost:5432`.
4. PostgreSQL JDBC driver có trên test runtime classpath.
5. JDBC statement `SELECT 1` chạy thực và trả đúng dữ liệu.

**Không** có Spring Boot ApplicationContext trong test này. Nếu test đỏ vì `Could not find a valid Docker environment`, đừng bắt đầu sửa repository Spring vì repository chưa hề chạy. Nếu đỏ vì `No suitable driver`, kiểm JDBC driver dependency. Nếu đỏ vì `Connection refused`, kiểm startup/readiness, mapped host/port và Docker runtime.

### 17.2. Expected output

Có **1 JUnit test method**, dự kiến PASS nếu Docker runtime và dependencies sẵn sàng. `SELECT 1` trả numeric `1`. JUnit không yêu cầu một dòng `System.out.println` cố định; container ID, mapped port và logs sẽ khác mỗi run.

## 18. Spring Boot integration: container như Spring bean

**`src/test/java/com/example/containerlesson/PostgresSpringIntegrationTest.java`**

```java
package com.example.containerlesson;

import java.sql.Connection;
import javax.sql.DataSource;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.testcontainers.containers.PostgreSQLContainer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = ContainerLessonApplication.class,
        properties = "spring.sql.init.mode=always")
@Import(PostgresSpringIntegrationTest.PostgresConfig.class)
class PostgresSpringIntegrationTest {

    @TestConfiguration(proxyBeanMethods = false)
    static class PostgresConfig {

        @Bean
        @ServiceConnection
        PostgreSQLContainer<?> postgresContainer() {
            return new PostgreSQLContainer<>(
                    "postgres:16-alpine")
                    .withDatabaseName("spring_demo")
                    .withUsername("test")
                    .withPassword("test");
        }
    }

    @Autowired
    BookRepository books;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    DataSource dataSource;

    @BeforeEach
    void cleanOwnedTable() {
        // Database 'spring_demo' chỉ thuộc test container của context.
        jdbc.update("DELETE FROM books");
    }

    @Test
    void generatesKeyAndReadsPersistedRow() {
        long id = books.create(
                "ISBN-001", "Spring Boot Testing");

        assertTrue(id > 0);
        assertEquals("Spring Boot Testing",
                books.findTitle("ISBN-001"));
        assertEquals(1L, books.count());
    }

    @Test
    void realUniqueConstraintRejectsDuplicateIsbn() {
        books.create("ISBN-DUP", "First edition");

        assertThrows(DuplicateKeyException.class,
                () -> books.create(
                        "ISBN-DUP", "Other edition"));

        assertEquals(1L, books.count());
    }

    @Test
    void reallyUsesPostgreSqlNotAnEmbeddedFake()
            throws Exception {

        try (Connection connection =
                     dataSource.getConnection()) {
            String product = connection.getMetaData()
                    .getDatabaseProductName();

            assertEquals("PostgreSQL", product);
        }
    }
}
```

### 18.1. Cơ chế lifecycle

- `@Import` đưa nested `PostgresConfig` vào **test application context**.
- `@Bean` trả typed `PostgreSQLContainer<?>`; Spring Boot quản lý container bean.
- `@ServiceConnection` tạo `JdbcConnectionDetails` để DataSource chọn URL/user/password của container.
- Boot khởi động container trước các beans phụ thuộc và dừng container sau khi context teardown.
- `spring.sql.init.mode=always` tạo bảng trên PostgreSQL thật qua `schema.sql`.
- `@BeforeEach` xóa data của riêng test DB, nhưng **không reset identity**; ID chỉ được assert dương.
- Mỗi `@Test` chạy `BookRepository` thật với constraints thật.

**Không đặt `@Testcontainers` hoặc `@Container` lên `PostgresConfig` trong ví dụ này**: lifecycle ở đây thuộc **Spring bean**, không phải JUnit Jupiter extension. Đây là cách được Spring Boot 3.5 khuyến nghị khi context có thể được cache giữa test classes.

### 18.2. Test này chứng minh gì?

- Spring Boot autoconfiguration biết lấy connection details từ Testcontainers.
- PostgreSQL JDBC driver và DataSource hoạt động.
- `schema.sql` thực sự đã tạo bảng.
- Repository insert/query và generated key chạy.
- Database UNIQUE constraint từ chối duplicate.
- Kết nối thực sự là PostgreSQL, không bị thay lén bằng H2.

Bài test này **không kiểm HTTP transport**, vì không có controller/server. Nó cũng không kiểm SSL/TLS hoặc production database users/permissions. **Integration test** có nghĩa qua boundary database thật của môi trường kiểm thử, không phải end-to-end production.

### 18.3. Expected test count

`PostgresSpringIntegrationTest` có **3 JUnit test methods**. Cùng class chứa một PostgreSQL container như Spring bean trong context; method `cleanOwnedTable()` chạy trước từng test nên dữ liệu không phụ thuộc thứ tự. Tổng với `PostgresJunitLifecycleTest` là **4 test methods**.

Nếu project chạy đúng môi trường, tất cả dự kiến pass. Không có stdout nghiệp vụ cố định; Gradle có thể ghi `BUILD SUCCESSFUL`. **Đây là kết quả dự kiến từ mã được rà soát, không phải tuyên bố đã chạy Docker/Gradle trên repository thực tế.**

## 19. Alternative: `@JdbcTest` + PostgreSQL Testcontainer

`@JdbcTest` chỉ dựng JDBC slice thay vì full application context, nhanh hơn khi chỉ cần kiểm SQL/row mapping. Nếu dùng PostgreSQL container, cần tránh auto-replace DataSource thành embedded test database:

```java
// Snippet minh họa, không phải file runnable độc lập.
@JdbcTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
@Import(BookRepository.class)
class BookJdbcSliceTest {
    // Cấp PostgreSQL connection bằng @ServiceConnection
    // hoặc @DynamicPropertySource trong test setup.
}
```

Trong Spring Boot 3.5, `@JdbcTest` thường tạo test transaction và rollback sau mỗi method. Điều này hữu ích cho isolation, nhưng **không chứng minh rollback của một service production** nếu transaction của JUnit tự dọn hết dữ liệu. Để test service transaction thật, dùng test không có test-managed transaction bao quanh service call, rồi kiểm data sau exception.

Trong demo chính, `@SpringBootTest` giúp minh họa Boot connection details và JDBC integration rõ ràng; một project lớn có thể dùng nhiều `@JdbcTest` cho repository cases, ít full context tests hơn.

## 20. Đường kết nối host/port: không hard-code localhost

Testcontainers có hai “góc nhìn” mạng:

- **Container port:** PostgreSQL lắng nghe `5432` bên trong container.
- **Host-mapped port:** Docker ánh xạ sang một port khả dụng trên máy JVM nhìn thấy.

Trong plain JUnit test dùng:

```java
String jdbcUrl = POSTGRES.getJdbcUrl();
String host = POSTGRES.getHost();
int port = POSTGRES.getMappedPort(5432);
```

**Không viết:**

```java
// PHẢN VÍ DỤ: không portable với Docker remote/CI.
String jdbcUrl =
        "jdbc:postgresql://localhost:5432/jupiter_demo";
```

Với Docker Desktop trên host, `getHost()` có thể trông giống localhost; với remote Docker hoặc Docker-in-Docker, nó có thể khác. `getMappedPort(...)` chỉ có ý nghĩa **sau khi container đã start**.

### 20.1. Container-to-container network khác host-to-container

Nếu ứng dụng cũng chạy **bên trong một container**, có thể cần Docker network alias và internal port thay vì mapped host port. `withNetwork(Network.SHARED)`/`withNetworkAliases(...)` là pattern cho network nội bộ; khi một test JVM chạy trên host, thường dùng `getHost()`/`getMappedPort(...)`. Đừng copy một URL nội bộ không resolve từ JVM test.

### 20.2. Port xung đột

Testcontainers chọn dynamic port để giảm collisions. Nếu bạn dùng `withFixedExposedPort` hoặc cấu hình `5432:5432` cố định, chạy song song dễ conflict. **Ưu tiên dynamic ports**; chỉ cố định khi một protocol/testing constraint thực sự yêu cầu.

## 21. Readiness: container chạy khác service sẵn sàng

Docker có thể báo container **running** trong khi PostgreSQL vẫn khởi động; Testcontainers database modules có startup/readiness behavior riêng để chờ dịch vụ đủ sẵn sàng. Khi dùng `PostgreSQLContainer`, ưu tiên readiness mặc định của module thay vì chèn `Thread.sleep(10000)`.

Nếu dùng `GenericContainer` cho service tự xây:

```java
// Snippet: GenericContainer<?> server, khi ứng dụng trả /health:
server.waitingFor(
        Wait.forHttp("/health")
                .forPort(8080)
                .forStatusCode(200));
```

Snippet cần import `org.testcontainers.containers.wait.strategy.Wait` và container expose đúng port; không phải file runnable. Lựa chọn health endpoint/log message/port wait phải phản ánh **service thực sự sẵn sàng**, tránh sleep cố định.

**Startup timeout vs request timeout** không giống nhau. Một database chậm boot do image pull không nhất thiết là application query timeout. Đọc log container và nguyên nhân trước khi tăng timeout trên mọi test.

## 22. Data isolation và lifecycle giữa test methods

Một static PostgreSQL container giữ **cùng database** trong nhiều test methods. JUnit tạo test instance mới mỗi method **không reset DB**.

Chiến lược:

1. Query/delete đúng dữ liệu thuộc test trước/ sau method.
2. Dùng `@Transactional` + rollback ở test khi điều đó phù hợp, nhưng đừng dùng nó để suy luận sai về service transaction.
3. Dùng schema/database riêng mỗi class/run nếu chạy parallel.
4. Dùng fixture với unique business IDs, không đoán identity liên tục.
5. Chạy migration/schema tại startup của context; không phụ thuộc test order.
6. Dùng `@Sql` hoặc repository setup/cleanup khi cần data fixtures.
7. Tránh việc một test xóa toàn bộ DB dùng chung với test khác.

Ví dụ `PostgresSpringIntegrationTest` dùng `DELETE FROM books` trong `@BeforeEach` vì **database chỉ tồn tại trong Postgres container do context này sở hữu**. Nếu chuyển sang shared test PostgreSQL, phải dùng schema/namespace riêng và data cleanup hẹp hơn.

### 22.1. Transaction của test và transaction của server

Với `@SpringBootTest(RANDOM_PORT)`, HTTP server xử lý request ở context/thread riêng, và `@Transactional` của JUnit test method không tự rollback các writes do server thực hiện. Test database cần explicit cleanup hoặc fixture isolation. Đừng dựa vào một annotation rollback mà chưa kiểm boundary.

## 23. Testcontainers Reuse và Ryuk resource cleanup

**Ryuk** là resource reaper giúp dọn containers/networks/volumes được Testcontainers tạo khi JVM kết thúc bất thường trong những trường hợp được hỗ trợ. Nó cần có thể chạy và truy cập Docker API phù hợp. Một số CI có quyền hạn Docker hạn chế khiến Ryuk bị chặn.

**Không tắt Ryuk mặc định** chỉ để cho test xanh. Biến môi trường `TESTCONTAINERS_RYUK_DISABLED=true` là biện pháp đặc biệt khi môi trường đã có cơ chế cleanup thay thế đáng tin cậy, ví dụ runner ephemeral và container cleanup policies phù hợp. Tắt Ryuk trên máy dùng chung có thể để lại tài nguyên mồ côi.

**Reusable containers (`withReuse(true)`)** là tính năng experimental. Chúng có thể giữ container chạy qua nhiều test executions; data/credentials/ports tồn tại lâu hơn một suite. Tài liệu Testcontainers cảnh báo reuse **không phù hợp CI** theo policy hiện hành. Với developer cần tốc độ, chỉ bật reuse sau khi hiểu state leakage và cleanup; không bật tự động cho cả team.

### 23.1. Container static là “reuse” chưa?

Không. Static `@Container` chỉ **share trong test class/lifecycle extension**. `withReuse(true)` là tính năng cross-process opt-in đặc biệt. Spring context caching có thể giữ container bean lâu hơn một test class nhưng vẫn trong lifecycle context — cũng khác reusable containers experimental.

### 23.2. Đừng tự xóa resource đang chạy của suite khác

Không chạy `docker system prune -af` như một “fix” mặc định khi test fail: nó có thể xóa images/containers/volumes mà project khác cần. Chỉ cleanup resources thuộc run/test và tuân thủ chính sách quản trị máy/CI.

## 24. CI: Docker phải chạy ở nơi test JVM chạy

Một CI pipeline đúng cần:

- Java/Gradle build environment.
- Docker API-compatible daemon hoặc managed container service truy cập được từ test JVM.
- Quyền pull images của PostgreSQL và các helper images của Testcontainers.
- Network/DNS/proxy/registry authentication phù hợp.
- Quyền chạy các helper container cần thiết (như Ryuk), hoặc cơ chế cleanup thay thế theo policy.
- Disk/RAM/CPU đủ để khởi động service và chạy tests đồng thời.
- Test result artifacts/logs được lưu khi thất bại để debug.

Ví dụ **workflow minh họa** trên một runner Linux có Docker Engine sẵn:

```yaml
# Snippet GitHub Actions; điều chỉnh quyền và policy CI của tổ chức.
name: integration-tests
on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - name: Check Docker API
        run: docker info
      - name: Run integration tests
        run: ./gradlew test
```

Đây là **snippet workflow**, không phải bảo đảm mọi self-hosted/locked-down runner có Docker. Trên runner không có daemon, `docker info` sẽ fail sớm thay vì giấu nguyên nhân trong `Failed to load ApplicationContext`.

### 24.1. Docker-in-Docker và remote Docker

Khi Gradle/JVM chạy **bên trong một job container**, `localhost` trỏ tới chính job container, không tự trỏ Docker daemon. Có thể cần socket mount được quản trị, DinD sidecar, network alias hoặc remote Docker setup theo CI platform. `DOCKER_HOST`, `TESTCONTAINERS_HOST_OVERRIDE` và các biến socket override chỉ dùng khi bạn hiểu topology; **không copy bừa host/port từ hướng dẫn của môi trường khác**.

**Không mount Docker socket tùy tiện vào untrusted PR jobs**: socket Docker thường tương đương quyền quản trị Docker host, có rủi ro lớn nếu job chạy code không đáng tin.

## 25. Diagnosing: đọc đúng lớp của lỗi

Một test có các lớp:

```text
Gradle resolution
    -> JUnit extension discovered
       -> Docker environment detection
          -> Image pull
             -> Container startup / readiness
                -> Host port mapping
                   -> Driver connection
                      -> Spring DataSource / schema migration
                         -> Repository + assertions
```

**Tìm lớp đầu tiên bị lỗi**. Đừng sửa `@Transactional` nếu image còn chưa pull xong.

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra |
|---|---|---|
| `package org.testcontainers.junit.jupiter does not exist` | Thiếu module `junit-jupiter` hoặc nhầm artifact 2.x | Gradle testCompileClasspath, BOM |
| `PostgreSQLContainer cannot be resolved` | Thiếu module PostgreSQL hoặc import 1.x/2.x sai | `dependencyInsight` và import |
| `ServiceConnection cannot be resolved` | Thiếu `spring-boot-testcontainers` | testImplementation dependency |
| `No tests found for given includes` | Sai FQCN, JUnit Platform chưa bật | `useJUnitPlatform()`, class/method names |
| `Could not find a valid Docker environment` | Daemon/socket không có hoặc quyền sai | `docker version` có Server? JUnit JVM env? |
| `Permission denied /var/run/docker.sock` | User không đủ quyền Docker API | User/groups/CI policy; không chmod 777 |
| `Pull access denied` | Image tag/private registry/auth/proxy | `docker pull`, mirror credentials |
| `ContainerLaunchException` | Container crash/readiness/startup timeout | Container logs, image/platform, memory |
| `Timed out waiting for container port` | Sai port/health check, service chưa sẵn sàng | Wait strategy và exposed port |
| `No suitable driver` | PostgreSQL JDBC driver thiếu ở test runtime | `org.postgresql:postgresql` |
| `Connection refused` | URL host/port sai hoặc container stop sớm | `getJdbcUrl`, lifecycle/context cache |
| `relation "books" does not exist` | schema.sql chưa init trên non-embedded DB | `spring.sql.init.mode=always`/migrations |
| `duplicate key violates unique constraint` | Fixture còn lại hoặc scenario negative | Cleanup/unique IDs, kiểm expected |
| Test xanh riêng nhưng đỏ trong suite | Shared DB data/context cache/parallel | Isolation, bean vs JUnit container lifecycle |
| Ryuk không thể start | CI privileged/network restrictions | Security policy/ephemeral runner và cleanup |
| Docker chạy trong terminal nhưng JUnit fail | IDE dùng JVM/context khác | Java process env, Docker context/socket |
| `NoSuchMethodError` ở Testcontainers | Trộn major/minor dependency versions | BOM/lockfiles, dependencyInsight |

**Không log password production** khi debug. Container demo có test credentials cố định nhưng không được sao chép vào production database. Những lỗi network/proxy cần được xử lý ở hạ tầng test, không sửa expected assertion để bỏ qua việc không khởi động backend.

## 26. Chu trình debug có thể thực hiện ngay

1. **Xác nhận Gradle version resolution:** `./gradlew dependencies --configuration testRuntimeClasspath`.
2. **Xác nhận Java runtime và JUnit:** `java -version`, `./gradlew test --tests ... --info`.
3. **Xác nhận Docker daemon:** `docker version` có Server, `docker info` không báo lỗi.
4. **Xác nhận image pull:** `docker pull postgres:16-alpine` từ chính máy/runner.
5. **Chạy plain JUnit test:** `PostgresJunitLifecycleTest` — loại trừ Spring context.
6. **Chạy Spring integration test:** `PostgresSpringIntegrationTest` — kiểm ServiceConnection + schema.
7. **Nếu Spring fail:** đọc **root cause** của `Failed to load ApplicationContext`, không chỉ dòng đầu.
8. **Nếu SQL fail:** kiểm schema/migration, DataSource database product name, user/schema quyền.
9. **Nếu suite fail theo thứ tự:** reset test data/context lifecycle; tạm chạy tuần tự để xác định state collision rồi sửa isolation.
10. **Nếu CI fail nhưng local pass:** so image registry, RAM, Docker topology, filesystem, permissions, startup timeout và parallelism.
11. **Đừng overwrite/làm sạch toàn bộ Docker host** khi chưa xác nhận resources thuộc test run.

Câu hỏi quan trọng trong debug là: **“Trong các ranh giới ấy, ranh giới đầu tiên chưa làm được điều đã cam kết là đâu?”**

## 27. Performance: test nhanh mà vẫn có coverage

Testcontainers giúp thực thi dịch vụ thật, nhưng container startup và image pull tạo chi phí. Một chiến lược hợp lý:

- **Unit tests thuần:** nhanh, không Docker, kiểm domain logic với fake/mock phù hợp.
- **Slice tests:** chỉ nạp phần Spring cần thiết, có thể dùng container thật cho repository adapter.
- **Full-context integration tests:** chọn các luồng quan trọng liên quan tới auto-config, migrations, service transaction.
- **Transport/E2E tests:** ít nhưng có giá trị khi cần kiểm real HTTP, TLS, broker protocol hoặc nhiều dịch vụ.
- **Image caching:** hỗ trợ pull nhanh nếu CI registry policy cho phép; pin image tags/digests đã review để giảm surprise.
- **Spring context caching:** có ích khi container là Spring bean và context lifecycle thống nhất.
- **Không lạm dụng container per method:** nếu dữ liệu có thể reset xác định, per-class/context container thường ít chi phí hơn.
- **Chạy song song có kiểm soát:** không để hai tests cùng xóa một database/schema/queue; JUnit extension của Testcontainers có giới hạn với parallel mode.
- **Resource budget:** Postgres + Kafka + Elasticsearch đồng thời có thể quá nặng cho laptop/CI nhỏ; tách suites và có quotas.

**Tránh tối ưu giả:** Chuyển mọi database test sang H2 cho nhanh có thể bỏ lọt PostgreSQL-specific bugs; ngược lại chuyển mọi phép tính cộng hai số vào full Docker integration test làm suite chậm mà không tăng khả năng phát hiện lỗi.

## 28. Security và quản trị môi trường test

Testcontainers có quyền tạo container qua Docker API. Điều này ảnh hưởng cả local và CI:

1. **Docker socket là tài nguyên quyền cao**; hạn chế ai được mount/truy cập.
2. **Images cần nguồn tin cậy:** pin image, scan vulnerabilities và dùng registry mirror/allowlist khi tổ chức yêu cầu.
3. **Không đưa secret production** vào `withEnvironment(...)`, logs, test fixtures hoặc image layers.
4. **Network isolation:** test container nên hạn chế inbound/outbound theo yêu cầu, không tự kết nối production.
5. **Resource constraints:** giới hạn CPU/RAM/disk nếu runner chia sẻ tài nguyên.
6. **Cleanup:** biết ai sở hữu containers/volumes; tránh orphan resources có credentials/dữ liệu.
7. **CI untrusted pull request:** đánh giá kỹ việc cho phép thực thi Docker daemon và privileged helper.
8. **Test user permissions:** PostgreSQL role demo có quyền trên test database; đừng dùng superuser production để tiện test.
9. **Observability:** chỉ ghi host/port/image vào log ở mức cần thiết; che credentials/tokens.
10. **Reproducibility:** Java/Gradle/Boot/Testcontainers/Postgres image versions có quy tắc pin/nâng cấp được review.

**“Test-only” là cấu hình và quyền hạn thật, không phải chỉ là một tên database chứa chữ test.** Khi có bất kỳ nghi ngờ nào về host/credentials, không thực hiện destructive cleanup.

## 29. Bài tập kiểm tra hiểu biết

### Bài A — thiếu dependency

Build có `spring-boot-starter-test` và `spring-boot-starter-jdbc` nhưng import `@Testcontainers`/`PostgreSQLContainer` không compile. Cần thêm artifact nào cho Spring Boot 3.5? Khi dùng `@ServiceConnection` thì cần gì nữa?

**Đáp án:** `org.testcontainers:junit-jupiter` và `org.testcontainers:postgresql`; thêm `spring-boot-testcontainers` cho `@ServiceConnection`, cùng PostgreSQL JDBC driver ở runtime test.

### Bài B — JUnit lifecycle

Một test có `@Container static final PostgreSQLContainer<?>` nhưng **không có `@Testcontainers`** và không tự start. Container có chắc được start không?

**Đáp án:** Không. `@Container` đánh dấu field nhưng JUnit extension phải được kích hoạt bằng `@Testcontainers` (hoặc lifecycle phải được quản lý bởi cơ chế khác). Đừng dựa vào annotation metadata đơn lẻ.

### Bài C — static vs instance

Một test class có ba methods. Với static container, có bao nhiêu lần container được start theo JUnit extension? Instance field thì sao?

**Đáp án:** Static: thường một lần trước class/stop sau class. Instance: start/stop cho mỗi method theo lifecycle JUnit mặc định. Cả hai không tự reset database rows khi static container được share.

### Bài D — host port

PostgreSQL chạy ở 5432 bên trong container, Docker map thành 32791 trên host. Test cố kết nối `localhost:5432`. Sai ở đâu?

**Đáp án:** Container internal port khác mapped host port; dùng `getJdbcUrl()` hoặc `getHost()` + `getMappedPort(5432)`, không hard-code.

### Bài E — ServiceConnection vs DynamicPropertySource

`@ServiceConnection` có phải annotation start container không? `@DynamicPropertySource` có phải tự tạo Docker container không?

**Đáp án:** Không. Chúng cấu hình connection details/properties. Lifecycle phải do JUnit extension, Spring bean hoặc manual management đảm nhiệm.

### Bài F — class khác fail

Test class A dùng static `@Container` và cached Spring context. Class B dùng lại context nhưng database connection refused. Tại sao?

**Đáp án:** JUnit có thể đã stop container sau class A trong khi cached context còn tồn tại. Cân nhắc Spring-managed container bean/@ImportTestcontainers hoặc thiết kế cache/lifecycle nhất quán.

### Bài G — Docker không sẵn

Gradle compile thành công nhưng JUnit báo `Could not find a valid Docker environment`. Có nên sửa query SQL?

**Đáp án:** Không. Kiểm Docker daemon/socket, permissions, JVM environment của IDE/CI và Docker runtime topology trước.

### Bài H — trộn Testcontainers 1.x/2.x

Một project Boot 3.5 thêm `org.testcontainers:testcontainers-postgresql:2.x` nhưng code import `org.testcontainers.containers.PostgreSQLContainer`. Cần làm gì?

**Đáp án:** Chọn một nhánh version thống nhất; Boot 3.5 BOM quản lý 1.x với artifact `postgresql` và import `org.testcontainers.containers`. Nâng 2.x cần đổi dependencies/packages và kiểm Boot compatibility.

### Bài I — database thật, test vẫn vô nghĩa

Test chỉ `SELECT 1` trả 1 rồi kết luận transaction rollback và UNIQUE business invariant đã đúng. Kết luận có đúng?

**Đáp án:** Không. Nó chứng minh readiness/driver/connection. Cần thêm repository/service tests và assertions trên row state, constraint, rollback.

### Bài J — CI bảo mật

Một nhóm đề xuất mount Docker socket host vào container chạy untrusted pull requests và tắt Ryuk để dễ chạy. Rủi ro? Cách tốt hơn?

**Đáp án:** Socket mang quyền cao trên Docker host; tắt cleanup có thể để lại containers/data. Dùng runner cô lập/quyền tối thiểu/managed container runtime và cleanup policy được kiểm soát.

## 30. Checklist trước khi giao integration suite

- [ ] Tôi xác định **bug/rủi ro** mà test với container thật cần phát hiện.
- [ ] Java/Gradle/Spring Boot/Testcontainers major versions nhất quán.
- [ ] Không trộn artifacts `org.testcontainers:postgresql` 1.x và `testcontainers-postgresql` 2.x.
- [ ] `spring-boot-starter-test` đã có, JUnit Jupiter tests được Gradle/Surefire nhận diện.
- [ ] Module Testcontainers đúng backend đã có trên `testImplementation`.
- [ ] JDBC/Redis/Mongo/HTTP client driver có trên classpath phù hợp.
- [ ] Nếu dùng `@ServiceConnection`, có `spring-boot-testcontainers`.
- [ ] Nếu dùng JUnit `@Container`, có `@Testcontainers` hoặc lifecycle tương ứng.
- [ ] Tôi phân biệt static/container-per-method với Spring-managed container bean.
- [ ] Tôi đã kiểm Spring context cache và shutdown lifecycle.
- [ ] Docker daemon/runtime truy cập được **từ JVM chạy test**.
- [ ] CI có quyền pull images, tạo containers, kết nối dynamic ports và cleanup.
- [ ] Không hard-code `localhost:5432` hoặc host-mapped port.
- [ ] Service readiness được kiểm đúng, không dùng sleep tùy tiện.
- [ ] Database schema/migrations được áp dụng trên container DB.
- [ ] Test không vô tình dùng H2 hoặc database production.
- [ ] Test data được cleanup/isolate; không dựa vào identity bắt đầu từ 1.
- [ ] Parallel tests không ghi/xóa cùng resource ngoài ý muốn.
- [ ] Ryuk/reuse có policy rõ; không tắt cleanup mặc định.
- [ ] Không có token, password, secret production trong test source/logs.
- [ ] Test thất bại nếu Docker không sẵn khi nó là required CI gate.
- [ ] Số integration tests đủ để bảo vệ boundary, không biến mọi unit test thành Docker test.
- [ ] Có báo cáo những gì **chưa** kiểm: TLS production, HA, proxy, load, permissions thật.

**Kết luận:** Testcontainers giúp Java/Spring Boot kiểm các backend thật trong môi trường tạm thời, nhưng độ tin cậy đến từ **cả bộ ba**: (1) dependency/BOM và driver đúng version, (2) lifecycle JUnit/Spring đúng, (3) Docker runtime/CI và dữ liệu test được quản lý an toàn. `@Testcontainers` + `@Container` quản lý containers trong JUnit; `@ServiceConnection` hoặc `@DynamicPropertySource` nối Spring với dịch vụ; container bean thường phù hợp hơn khi cần lifecycle trùng Spring context cache. Hãy xác minh đến tận row/constraint/schema, không dừng ở “container đã chạy” rồi tuyên bố business integration đã đúng.

### Tài liệu tham khảo chính thức

- Spring Boot 3.5 — Testcontainers, Spring-managed container beans, JUnit extension, service connections và dynamic properties: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Spring Boot 3.5 — Managed Dependency Coordinates, Testcontainers 1.x modules: https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html
- Testcontainers for Java — JUnit Jupiter 5 integration/lifecycles: https://java.testcontainers.org/test_framework_integration/junit_5/
- Testcontainers for Java — Docker runtime support và discovery: https://java.testcontainers.org/supported_docker_environment/
- Testcontainers for Java — PostgreSQL module: https://java.testcontainers.org/modules/databases/postgres/
- Testcontainers — Release 2.0 breaking module/package changes: https://github.com/testcontainers/testcontainers-java/releases/tag/2.0.0
- Testcontainers — Reusable Containers (experimental): https://java.testcontainers.org/features/reuse/
- Testcontainers — Configuring Ryuk/resource reaper: https://java.testcontainers.org/features/configuration/
- Spring Framework — TestContext cache, transaction lifecycle: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
