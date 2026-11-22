# Vì sao dùng dịch vụ thật trong container cho kiểm thử tích hợp — Spring Boot và Testcontainers

## 1. Vấn đề gốc: mock cho câu trả lời giả, còn integration cần hợp đồng của dịch vụ thật

Giả sử một ứng dụng Spring Boot lưu đơn hàng vào PostgreSQL, phát sự kiện qua Kafka và đọc trạng thái ngắn hạn từ Redis. Unit test có thể dùng Mockito để định nghĩa:

```java
when(repository.findById(42L))
        .thenReturn(Optional.of(fakeOrder));
```

Đoạn trên chứng minh phần Java đang kiểm thử xử lý kết quả giả đúng như đã lập trình trong test. Nó **không** chứng minh repository SQL có chạy được với PostgreSQL, tên bảng/column có đúng, unique constraint có được tạo, Kafka consumer nhận sự kiện theo cấu hình thực, hay Redis key có TTL thực.

Trong một integration test, một lớp lỗi quan trọng xuất hiện **ở ranh giới với dịch vụ bên ngoài**: driver, connection protocol, SQL dialect, schema migration, serialization, authentication, transaction, message acknowledgment, persistence và timing. Khi muốn kiểm chứng những ranh giới đó, một dịch vụ chạy trong container có thể cung cấp bằng chứng đáng tin cậy hơn một fake.

**Testcontainers** là thư viện cho Java/JUnit giúp tạo và quản lý lifecycle của dịch vụ dạng container trong test: PostgreSQL, MySQL, MongoDB, Redis, Kafka, RabbitMQ, Elasticsearch, LocalStack và nhiều hệ thống khác. Mỗi test có thể kết nối với một instance được cấp host/port/credentials riêng, sử dụng API hoặc wire protocol giống loại dịch vụ ngoài mà ứng dụng sẽ dùng.

**Cốt lõi của bài:** Không phải “mọi thứ phải thật” mới là test tốt. Dùng dịch vụ thật trong container khi hành vi bạn muốn chứng minh **nằm trong dịch vụ, driver hoặc giao thức**; còn domain logic thuần vẫn nên test hẹp để nhanh, dễ debug và ít phụ thuộc hạ tầng.

Trong bài này, ví dụ code đầy đủ dùng **Java 17 + Spring Boot 3.3.0 + Spring Data JPA + PostgreSQL 16 Testcontainers + JUnit Jupiter + HTTP client thật**. Phần nguyên lý cũng áp dụng cho Kafka/Redis/MongoDB/RabbitMQ, nhưng chúng có những test oracle và quy tắc cô lập khác nhau.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt unit test với mock, embedded/in-memory database, container có engine thật và test trên môi trường staging.
2. Giải thích **vì sao Testcontainers cải thiện độ trung thực (fidelity)** của kiểm thử tích hợp so với mock/H2 ở những rủi ro vendor-specific.
3. Hiểu lifecycle: image, container, network, exposed/mapped port, startup wait, cleanup, JUnit extension.
4. Biết dùng `@Testcontainers`, `@Container`, `@ServiceConnection` với Spring Boot 3.3.
5. So sánh `@ServiceConnection` và `@DynamicPropertySource`, hiểu tránh hardcode host/port/credentials.
6. Viết dự án Gradle Java 17/Spring Boot có REST API, service, JPA repository và PostgreSQL Testcontainer.
7. Viết test xác minh **actual PostgreSQL vendor**, HTTP request đi qua embedded server, SQL native `ILIKE` và unique constraint thật.
8. Hiểu vì sao `@DataJpaTest` trên Boot 3.3 cần để ý `@AutoConfigureTestDatabase(replace=NONE)` khi muốn giữ datasource từ container.
9. Thiết kế test isolation, cleanup, transaction và database migrations chính xác.
10. Nhận diện tình huống container **không tương đương production**: topology, TLS, authentication, distributed failures, cloud service behavior và dữ liệu lớn.
11. Tổ chức CI: image pinning, runtime availability, caching có kiểm soát, timeouts, chẩn đoán và không nhầm `SKIPPED` với `PASSED`.
12. Đặt câu hỏi đúng trước khi mở rộng test: “Lỗi nào mock/slice test không thể chứng minh được?”

## 3. Năm cấp kiểm thử và ý nghĩa của “dịch vụ thật”

| Cấp | Thứ đang chạy | Ưu điểm | Không chứng minh được |
| --- | --- | --- | --- |
| Unit test thuần | Java object, fake/Mockito | Nhanh, tách biệt logic | SQL/protocol/driver/engine behavior |
| Spring slice + fake dependency | Ví dụ `@WebMvcTest` + mock service | Controller mapping, HTTP response giả lập | Service thật và database bên ngoài |
| Spring JPA slice + H2 | `@DataJpaTest` với embedded H2 | Mapping/query cơ bản, không cần Docker | PostgreSQL-specific behavior |
| Spring slice/full app + Testcontainers | Repository/controller thật, PostgreSQL/Kafka/Redis trong container | Driver/service engine, database/schema/protocol thực trong phạm vi test | Toàn bộ production deployment/network |
| Staging/deployment smoke | App đã triển khai, ingress/TLS/external services | Hành vi của môi trường gần production | Không nhất thiết dễ cô lập hoặc chạy ở mỗi PR |

**Mock có thể là lựa chọn tốt hơn** nếu unit cần kiểm tra “khi repository trả empty thì service phát `NotFoundException`”. Chỉ cần fake repository, không phải PostgreSQL.

**PostgreSQL thật có giá trị** khi muốn biết “một native SQL query có chạy trên PostgreSQL, unique index có từ chối duplicate và Hibernate entity có map đúng columns không?”. Mockito không thể trả lời.

**Container thật vẫn có giới hạn:** PostgreSQL chạy trong container không tự chứng minh hoạt động của production proxy, network policy, managed backups, IAM, TLS termination, replication lag hoặc failover topology. Sự trung thực cao hơn tại **tầng dịch vụ đã chạy**, không phải phép bảo đảm toàn bộ production giống test.

## 4. Mock hay database thật: hai loại hợp đồng khác nhau

### 4.1. Mock làm điều ta lập trình vào test

Ví dụ:

```java
when(orderRepository.save(any(Order.class)))
        .thenAnswer(invocation -> invocation.getArgument(0));
```

Dù entity thiếu column, database không tồn tại hoặc SQL query sai cú pháp, mock vẫn có thể trả lại object và test xanh. Đó là đúng bản chất mock: xác minh interactions hoặc business flow **với dependency giả**.

### 4.2. Embedded database giúp bắt lỗi thực, nhưng không phải cùng engine

H2 có thể kiểm tra JPA mapping cơ bản và nhiều derived queries, rất hữu ích cho fast tests. Tuy nhiên:

- PostgreSQL `ILIKE`, JSONB operators, partial indexes, `ON CONFLICT` có thể khác H2.
- Collation/case sensitivity và xử lý identifiers/keywords khác nhau.
- Data types, timestamps, numeric precision và generated IDs có thể khác.
- Transaction isolation, deadlocks và locking behavior khác.
- Flyway/Liquibase migrations có thể chứa SQL đặc thù PostgreSQL.
- H2 `MODE=PostgreSQL` vẫn chạy **H2**, không chạy PostgreSQL.

Vì vậy một test H2 pass là bằng chứng cho behavior **trên H2**, không phải khẳng định mọi SQL đều đúng trên PostgreSQL.

### 4.3. PostgreSQLContainer nâng mức bằng chứng

Khi dùng:

```java
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
```

Testcontainers sẽ khởi động một **PostgreSQL server thật** trên container runtime hỗ trợ. Spring Boot kết nối qua PostgreSQL JDBC driver. Khi repository thực hiện một native `ILIKE` query và test đối chiếu kết quả, bạn đã thực sự kiểm chứng PostgreSQL SQL parsing/execution cùng mapping/driver ở môi trường test.

Nhưng chỉ tạo container **chưa đủ**: test phải thực thi request/query thật và assert kết quả, đồng thời xác nhận datasource không bị một test auto-configuration thay thành H2.

## 5. Container là đơn vị thực thi, không phải một mock được bọc trong Docker

Một Testcontainers test thường trải qua:

```text
JUnit/Gradle test process (Java 17)
    |
    +-- Testcontainers client -> container runtime
    |      |
    |      +-- pulls/uses image postgres:16-alpine
    |      +-- creates isolated PostgreSQL container
    |      +-- waits for usable service
    |      +-- exposes container 5432 via mapped host port
    |      +-- provides host, port, JDBC URL, credentials
    |
    +-- Spring Boot ApplicationContext
    |      |
    |      +-- DataSource/HikariCP -> PostgreSQL JDBC driver
    |      +-- Spring Data JPA -> Hibernate -> SQL
    |      +-- Spring MVC/embedded Tomcat if RANDOM_PORT
    |
    +-- Test sends HTTP/request or calls repository
    +-- Assertions observe server/database state
    +-- JUnit/Testcontainers stop container per lifecycle
```

**Phân biệt các cổng**:

- PostgreSQL trong container lắng nghe cổng **5432**.
- Trên host, container runtime ánh xạ đến **một cổng có thể thay đổi**: ví dụ 32785 chỉ là ví dụ, không phải port thật cần hardcode.
- Embedded Spring Boot web server dùng `RANDOM_PORT` lại có **một cổng khác**.
- HTTP request từ test đến Spring Boot và JDBC connection từ Spring Boot đến PostgreSQL là **hai kết nối độc lập**.

Không ghi `jdbc:postgresql://localhost:5432/...` trong test rồi mặc định PostgreSQLContainer cũng được map vào 5432 của host. Hãy lấy connection details từ Testcontainers.

## 6. Vòng đời và thời điểm readiness

### 6.1. Image và container

Image `postgres:16-alpine` chứa PostgreSQL runtime và scripts/config đi kèm, không phải database đang chạy. Testcontainers tạo một container **process** từ image. Khi process hoàn tất startup và sẵn sàng kết nối, JUnit test mới nên bắt đầu thao tác DB.

Image tag không cố định tuyệt đối từng patch release; trong CI cần tính reproducibility có thể pin digest hoặc dùng registry mirror đã kiểm duyệt, và chủ động nâng version.

### 6.2. Startup readiness khác “process đã tồn tại”

Một container process có thể tồn tại nhưng dịch vụ chưa sẵn sàng nhận JDBC query. Testcontainers module chuyên dụng cung cấp wait/readiness logic phù hợp hơn việc gọi `Thread.sleep(5000)`.

Với generic services, có thể cấu hình wait strategy:

```java
GenericContainer<?> service = new GenericContainer<>(
        DockerImageName.parse("redis:7-alpine"))
        .withExposedPorts(6379)
        .waitingFor(Wait.forListeningPort());
```

Đây là **mảnh code minh họa**, cần imports `GenericContainer`, `DockerImageName` và `Wait`, chưa phải một test class độc lập. Listening port chỉ chứng minh có listener, **không nhất thiết chứng minh service đã sẵn sàng phục vụ mọi nghiệp vụ** (ví dụ migrations/cluster readiness). Khi module chuyên dụng có readiness probe phù hợp, nên dùng module đó.

### 6.3. Không dùng sleep làm đồng bộ hóa

`Thread.sleep(3000)` không biết container sẽ startup trong 1 hay 15 giây. CI chậm, cold image download hoặc initialization scripts có thể làm test flaky. Dùng readiness/wait strategy, timeouts hữu hạn và log root cause.

### 6.4. Testcontainers cleanup

Testcontainers thường quản lý stop/remove các container do test tạo, có thể dùng cơ chế resource reaper (Ryuk) tùy runtime/config. Một số môi trường Docker bị giới hạn quyền sẽ yêu cầu cấu hình phù hợp. Không tắt resource cleanup để ép test xanh mà không hiểu tác động: container orphan có thể tích tụ, gây tốn CPU/disk và rò dữ liệu test.

## 7. JUnit Jupiter: `@Testcontainers` và `@Container`

Một class cơ bản:

```java
@Testcontainers
class DatabaseTest {
    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
```

Ý nghĩa:

- `@Testcontainers` kích hoạt Testcontainers JUnit 5 extension.
- `@Container` đánh dấu field để extension quản lý.
- `static @Container`: một container được share giữa **các test methods trong cùng class**; khởi động trước khi methods chạy và dừng sau class.
- Instance `@Container`: một container cho **mỗi test method**, isolation cao hơn nhưng chi phí startup thường lớn hơn.
- Testcontainers JUnit extension được tài liệu hóa chủ yếu cho **sequential execution**; không mặc định bật JUnit parallel rồi kỳ vọng lifecycle của mọi container được bảo đảm.

**Static container không đồng nghĩa tự share an toàn giữa nhiều test classes.** Khi cần reuse giữa classes, vòng đời container phải khớp Spring context caching; phần sau sẽ bàn kỹ.

## 8. Spring Boot 3.3 kết nối Testcontainers như thế nào?

Spring Boot 3.1+ có integration `spring-boot-testcontainers` và annotation:

```java
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
```

Khi đặt `@ServiceConnection` trên typed container field, Boot có thể tự tạo các `ConnectionDetails` beans cho auto-configurations có hỗ trợ, ví dụ `JdbcConnectionDetails` cho PostgreSQL JDBC.

```java
@Container
@ServiceConnection
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
```

Thay vì tự nối host/port/username/password bằng strings, Spring Boot dùng connection details lấy từ container.

**Lưu ý quan trọng:** ConnectionDetails do service connection cung cấp có thể **được ưu tiên hơn** các connection properties tương ứng. Trong test phải biết nguồn cấu hình thực đang có hiệu lực và không đưa production secrets vào cùng context.

### 8.1. Nếu đang dùng GenericContainer

`@ServiceConnection` không thể luôn đoán dịch vụ dựa trên `GenericContainer` vì thiếu type cụ thể. Trong các trường hợp dựa vào image name, cần `@ServiceConnection(name="redis")` hoặc cách đăng ký connection details thích hợp với phiên bản Boot.

Nếu module chuyên dụng tồn tại (`PostgreSQLContainer`, `MongoDBContainer`, `KafkaContainer`...), ưu tiên module đó khi phù hợp để có wait strategy, connection API và typing rõ ràng.

### 8.2. `@DynamicPropertySource` là phương án thay thế

Không bắt buộc dùng `@ServiceConnection`. Spring Test có:

```java
@Container
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

@DynamicPropertySource
static void databaseProperties(
        DynamicPropertyRegistry registry) {
    registry.add(
            "spring.datasource.url", postgres::getJdbcUrl);
    registry.add(
            "spring.datasource.username", postgres::getUsername);
    registry.add(
            "spring.datasource.password", postgres::getPassword);
}
```

Đây là **snippet thay thế**, không phải code runnable đầy đủ. Nó cần imports Spring Test `DynamicPropertySource`/`DynamicPropertyRegistry` và JUnit Testcontainers. Không thêm cả `@ServiceConnection` lẫn dynamic JDBC properties cho cùng một container nếu không có nhu cầu rõ ràng, vì hai nguồn cùng cấu hình connection dễ gây nhầm.

### 8.3. Testcontainers JDBC URL

Với databases có JDBC support, Testcontainers còn có cách đặt JDBC URL dạng:

```properties
spring.datasource.url=jdbc:tc:postgresql:16-alpine:///catalog_test
```

Đây là một **phương án khác**, không cần khai báo một `PostgreSQLContainer` field cho cùng datasource khi đã dùng special JDBC URL. Nó dùng Testcontainers JDBC driver/module phù hợp, cần hiểu container lifecycle và URL options. Không trộn ba phương án (`@ServiceConnection`, `@DynamicPropertySource`, `jdbc:tc:`) một cách ngẫu nhiên.

## 9. `@DataJpaTest` khác `@SpringBootTest` khi kết nối container

`@DataJpaTest` là JPA slice giúp nạp repository/entities thay vì toàn bộ app. Với Boot 3.3, nó mặc định có cơ chế thay test datasource bằng embedded database khi phù hợp. Nếu H2 có trên classpath, datasource bạn nghĩ là PostgreSQLContainer có thể bị thay.

Khi **bắt buộc dùng PostgreSQL trong JPA slice trên Boot 3.3**:

```java
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
@Testcontainers
class PostgresJpaSliceTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
```

Đây là **khung minh họa**, chưa có repository/assertions, cần imports phù hợp. `Replace.NONE` chỉ nói “không thay DataSource”; nó **không tự tạo PostgreSQL**. Container và connection details vẫn phải được cấu hình.

Từ **Spring Boot 3.4**, `Replace.NON_TEST` được bổ sung và trở thành mặc định, nhận biết tốt hơn test datasource cung cấp từ Testcontainers. Đừng copy mode `NON_TEST` vào dự án Boot 3.3 — enum đó chưa tồn tại.

Trong dự án runnable sau, dùng **`@SpringBootTest(RANDOM_PORT)`** nên không cần `@AutoConfigureTestDatabase` của JPA slice. Ta cần cả REST API, service, repository, database và embedded server thật trong một integration test.

## 10. Dự án thực hành đầy đủ: Java 17 + Spring Boot 3.3.0 + PostgreSQL 16

Mục tiêu dự án:

1. POST `/api/items` nhận JSON, tạo item qua service và Spring Data JPA trên PostgreSQL thật.
2. GET `/api/items/{code}` lấy item đã lưu; ID không tồn tại trả 404.
3. GET `/api/items/search?word=...` dùng **PostgreSQL-specific `ILIKE`** trong repository native query.
4. Repository có unique constraint cho `code` và test phải nhìn thấy database từ chối duplicate.
5. JUnit xác nhận **actual database vendor** là PostgreSQL.
6. Spring Boot app chạy với embedded Tomcat RANDOM_PORT và Java 17 HTTP client gửi request thật qua socket.
7. Test setup/cleanup dùng container database cô lập, **không** dựa vào JUnit `@Transactional` để rollback server commits.

### 10.1. Cây thư mục

```text
testcontainers-why-real-service/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/catalog/
    │   ├── CatalogApplication.java
    │   ├── CatalogItem.java
    │   ├── CatalogRepository.java
    │   ├── CreateItemRequest.java
    │   ├── ItemResponse.java
    │   ├── ItemService.java
    │   └── ItemController.java
    └── test/java/example/catalog/
        └── CatalogPostgresIntegrationTest.java
```

### 10.2. `settings.gradle`

```groovy
rootProject.name = 'testcontainers-why-real-service'
```

### 10.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Các versions còn lại do Spring Boot 3.3 BOM quản lý để Spring Data, JUnit và Testcontainers tương thích nhau. Chỉ dùng **một** Spring Boot major version trong project; không thêm Testcontainers 2.x coordinates vào Boot 3.3 mà chưa kiểm tra compatibility, vì ecosystem artifacts/package đã thay đổi qua các major releases.

**Điều kiện để chạy:** JDK 17, Gradle wrapper tương thích (ví dụ Gradle 8.5), Maven Central accessible, một Docker/compatible container runtime cho Testcontainers và quyền tải image PostgreSQL. Không có Docker, test integration sẽ fail ở startup; đó là tín hiệu môi trường thiếu, không phải PostgreSQL bị mock.

### 10.4. `CatalogApplication.java`

**`src/main/java/example/catalog/CatalogApplication.java`:**

```java
package example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
```

Class này nằm cùng package gốc với controllers, service, JPA entity, repository. Khi `@SpringBootTest` chạy, Boot quét các beans bình thường và khởi tạo datasource từ `@ServiceConnection` trong test.

### 10.5. `CatalogItem.java` — JPA entity và unique constraint

**`src/main/java/example/catalog/CatalogItem.java`:**

```java
package example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
        name = "catalog_items",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_catalog_item_code",
                columnNames = "code")
)
public class CatalogItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "code", nullable = false, length = 40)
    private String code;

    @Column(name = "label", nullable = false, length = 120)
    private String label;

    @Column(name = "price_cents", nullable = false)
    private long priceCents;

    protected CatalogItem() {
        // Constructor required by JPA.
    }

    public CatalogItem(
            String code, String label, long priceCents) {
        this.code = code;
        this.label = label;
        this.priceCents = priceCents;
    }

    public Long getId() {
        return id;
    }

    public String getCode() {
        return code;
    }

    public String getLabel() {
        return label;
    }

    public long getPriceCents() {
        return priceCents;
    }
}
```

Entity dùng `jakarta.persistence` theo Boot 3.x. Hệ thống lưu `price_cents` theo minor currency units để test số nguyên, không cần floating point currency rounding.

`@UniqueConstraint` sẽ được Hibernate tạo thành database constraint khi lab dùng `ddl-auto=create-drop`. Trong production nên dùng Flyway/Liquibase migrations để tạo schema/index thực.

**Không assert ID = 1**: PostgreSQL sequences/identity counters có thể thay đổi sau rollback hoặc các inserts khác. Test chỉ cần ID có và truy vấn được qua business key.

### 10.6. `CatalogRepository.java` — derived query và native PostgreSQL `ILIKE`

**`src/main/java/example/catalog/CatalogRepository.java`:**

```java
package example.catalog;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CatalogRepository
        extends JpaRepository<CatalogItem, Long> {

    Optional<CatalogItem> findByCode(String code);

    @Query(
        value = """
                SELECT *
                  FROM catalog_items
                 WHERE label ILIKE CONCAT('%', :word, '%')
                 ORDER BY code
                """,
        nativeQuery = true
    )
    List<CatalogItem> searchLabelsIgnoreCase(
            @Param("word") String word);
}
```

Đây là ví dụ có chủ đích để chứng minh **engine fidelity**: `ILIKE` là toán tử match không phân biệt chữ hoa/thường của PostgreSQL. H2 có thể có chế độ tương thích và một số cú pháp gần giống, nhưng một H2 test không là bằng chứng cho PostgreSQL parser/semantics.

`@Param("word")` bind tham số vào native query; không nối chuỗi SQL bằng input người dùng. Bài mẫu tìm substring trong label. Trong production cần cân nhắc escaping literal wildcard `%` và `_`, search index/collation/locale nếu muốn hỗ trợ tìm kiếm chính xác hoặc hiệu năng cao.

`ORDER BY code` được khai báo để test không phụ thuộc thứ tự tự nhiên của database.

### 10.7. DTO `CreateItemRequest.java`

**`src/main/java/example/catalog/CreateItemRequest.java`:**

```java
package example.catalog;

public record CreateItemRequest(
        String code,
        String label,
        long priceCents) {}
```

Spring Boot starter-web kéo theo Jackson JSON converter hỗ trợ Java 17 records. Trong app production, có thể dùng Jakarta Bean Validation; lab dùng explicit validation đơn giản ở service để giữ dependencies tối thiểu.

### 10.8. DTO `ItemResponse.java`

**`src/main/java/example/catalog/ItemResponse.java`:**

```java
package example.catalog;

public record ItemResponse(
        Long id,
        String code,
        String label,
        long priceCents) {}
```

REST JSON là một contract bên ngoài. Dù database lưu `price_cents`, response field của record sẽ là `priceCents` khi không có Jackson naming override. JPA `@Column` không tự đổi JSON property name.

### 10.9. `ItemService.java` — nghiệp vụ và giao dịch

**`src/main/java/example/catalog/ItemService.java`:**

```java
package example.catalog;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ItemService {
    private final CatalogRepository repository;

    public ItemService(CatalogRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public ItemResponse create(CreateItemRequest input) {
        if (input == null
                || input.code() == null
                || input.code().isBlank()
                || input.label() == null
                || input.label().isBlank()
                || input.priceCents() < 0) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "code, label and nonnegative price are required");
        }

        CatalogItem entity = repository.saveAndFlush(
                new CatalogItem(
                        input.code(),
                        input.label(),
                        input.priceCents()));

        return toResponse(entity);
    }

    @Transactional(readOnly = true)
    public ItemResponse byCode(String code) {
        CatalogItem found = repository.findByCode(code)
                .orElseThrow(() ->
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND,
                                "item not found"));

        return toResponse(found);
    }

    @Transactional(readOnly = true)
    public List<ItemResponse> search(String word) {
        return repository.searchLabelsIgnoreCase(word)
                .stream()
                .map(ItemService::toResponse)
                .toList();
    }

    private static ItemResponse toResponse(CatalogItem item) {
        return new ItemResponse(
                item.getId(),
                item.getCode(),
                item.getLabel(),
                item.getPriceCents());
    }
}
```

`@Transactional` tạo transaction ở service boundary khi được gọi qua Spring proxy. `repository.saveAndFlush` yêu cầu Hibernate thực thi SQL sớm trong transaction, nhưng **flush không tự commit**. Transaction của service kết thúc khi method trả thành công; với JPA normal operations, interceptor sẽ commit. Unique constraint được database kiểm tra theo DDL hiện tại, test sẽ xác nhận bằng repository call.

Đường `search` dùng native SQL ở PostgreSQL, nên khi database engine/driver/query sai, test sẽ fail dù unit test service với mocked repository vẫn có thể xanh.

### 10.10. `ItemController.java` — HTTP boundary

**`src/main/java/example/catalog/ItemController.java`:**

```java
package example.catalog;

import java.net.URI;
import java.util.List;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/items")
public class ItemController {
    private final ItemService service;

    public ItemController(ItemService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<ItemResponse> create(
            @RequestBody CreateItemRequest request) {
        ItemResponse created = service.create(request);
        URI location = URI.create(
                "/api/items/" + created.code());

        return ResponseEntity.created(location)
                .body(created);
    }

    @GetMapping("/search")
    public List<ItemResponse> search(
            @RequestParam String word) {
        return service.search(word);
    }

    @GetMapping("/{code}")
    public ItemResponse byCode(
            @PathVariable String code) {
        return service.byCode(code);
    }
}
```

Endpoint trả 201 + `Location` khi tạo, 200 khi đọc và 404 nếu không có item. Trong lab, `code` là slug chứa ký tự an toàn như `CAM-01`. Với public API thực tế cần URL-encode path segment hoặc dùng identifier phù hợp; đừng nối một chuỗi bất kỳ chứa `/`, `?`, `#` vào URI rồi coi đó là đường dẫn an toàn.

## 11. JUnit integration test đầy đủ: live HTTP + live PostgreSQL

**`src/test/java/example/catalog/CatalogPostgresIntegrationTest.java`:**

```java
package example.catalog;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.time.Duration;
import java.util.List;

import javax.sql.DataSource;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.jpa.hibernate.ddl-auto=create-drop"
)
class CatalogPostgresIntegrationTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @LocalServerPort
    int httpPort;

    @Autowired
    DataSource dataSource;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    CatalogRepository repository;

    @Autowired
    ObjectMapper mapper;

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    private URI uri(String path) {
        return URI.create(
                "http://127.0.0.1:" + httpPort + path);
    }

    private HttpResponse<String> get(String path)
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(uri(path))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        return http.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    private HttpResponse<String> post(
            CreateItemRequest item) throws Exception {
        String body = mapper.writeValueAsString(item);

        HttpRequest request = HttpRequest.newBuilder()
                .uri(uri("/api/items"))
                .timeout(Duration.ofSeconds(10))
                .header("Content-Type", "application/json")
                .POST(
                        HttpRequest.BodyPublishers.ofString(
                                body,
                                StandardCharsets.UTF_8))
                .build();

        return http.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    @BeforeEach
    void cleanBefore() {
        repository.deleteAll();
    }

    @AfterEach
    void cleanAfter() {
        repository.deleteAll();
    }

    @Test
    void actualDatasourceIsPostgreSql() throws Exception {
        assertTrue(postgres.isRunning());
        assertTrue(httpPort > 0);

        try (Connection connection =
                     dataSource.getConnection()) {
            assertEquals(
                    "PostgreSQL",
                    connection.getMetaData()
                            .getDatabaseProductName());
        }
    }

    @Test
    void livePostPersistsAndLiveGetReadsCommittedData()
            throws Exception {
        HttpResponse<String> created = post(
                new CreateItemRequest(
                        "CAM-01", "Camera body", 250000L));

        assertEquals(201, created.statusCode());
        assertTrue(
                created.headers()
                        .firstValue("Location")
                        .orElse("")
                        .endsWith("/api/items/CAM-01"));

        JsonNode body = mapper.readTree(created.body());

        assertNotNull(body.get("id"));
        assertEquals("CAM-01",
                body.path("code").asText());
        assertEquals("Camera body",
                body.path("label").asText());
        assertEquals(250000L,
                body.path("priceCents").asLong());

        Long storedRows = jdbc.queryForObject(
                """
                SELECT COUNT(*)
                  FROM catalog_items
                 WHERE code = ?
                """,
                Long.class,
                "CAM-01");

        assertEquals(Long.valueOf(1L), storedRows);

        HttpResponse<String> fetched =
                get("/api/items/CAM-01");

        assertEquals(200, fetched.statusCode());

        JsonNode got = mapper.readTree(fetched.body());
        assertEquals("CAM-01", got.path("code").asText());
        assertEquals(250000L,
                got.path("priceCents").asLong());
    }

    @Test
    void nativeIlikeQueryIsActuallyRunByPostgres()
            throws Exception {
        repository.saveAllAndFlush(List.of(
                new CatalogItem(
                        "CAM-01", "Camera body", 200000L),
                new CatalogItem(
                        "CAM-02", "camera lens", 50000L),
                new CatalogItem(
                        "ACC-01", "Tripod", 40000L)));

        HttpResponse<String> response = get(
                "/api/items/search?word=cAmErA");

        assertEquals(200, response.statusCode());

        JsonNode array = mapper.readTree(response.body());

        assertTrue(array.isArray());
        assertEquals(2, array.size());
        assertEquals("CAM-01",
                array.get(0).path("code").asText());
        assertEquals("CAM-02",
                array.get(1).path("code").asText());
    }

    @Test
    void postgresRejectsDuplicateBusinessKey() {
        repository.saveAndFlush(
                new CatalogItem(
                        "UNIQUE-01", "First", 1000L));

        assertThrows(
                DataIntegrityViolationException.class,
                () -> repository.saveAndFlush(
                        new CatalogItem(
                                "UNIQUE-01", "Second", 2000L)));

        // Do not continue using a failed transaction.
    }

    @Test
    void missingItemReturns404FromRunningHttpServer()
            throws Exception {
        HttpResponse<String> result =
                get("/api/items/UNKNOWN-99");

        assertEquals(404, result.statusCode());
        assertFalse(
                repository.findByCode("UNKNOWN-99")
                        .isPresent());
    }
}
```

Đây là **một class** có năm phương thức test. Class dùng `@Container static`, phù hợp lifecycle một class với nhiều methods tuần tự. Các methods không phụ thuộc vào thứ tự JUnit chạy; `@BeforeEach` và `@AfterEach` xóa bảng **chỉ vì lab có PostgreSQL container test cô lập**. Không sao chép `deleteAll` vào production/staging database dùng chung.

### 11.1. Test 1 chứng minh vendor thật, không đoán từ dependency

`actualDatasourceIsPostgreSql` lấy một JDBC `Connection` từ **DataSource đang được Spring Boot inject**, đọc metadata và assert:

```java
assertEquals(
        "PostgreSQL",
        connection.getMetaData().getDatabaseProductName());
```

Nếu test vô tình bị chuyển sang H2, assertion này **thất bại**. Đó là bằng chứng mạnh hơn tên class `PostgresIntegrationTest` hoặc việc trong Gradle có `org.postgresql:postgresql`.

`postgres.isRunning()` và `httpPort > 0` là dấu hiệu lifecycle. Chúng chưa chứng minh API logic, vì thế còn các tests gửi HTTP và đọc SQL state.

### 11.2. Test 2 kiểm tra hai ranh giới thật

`livePostPersistsAndLiveGetReadsCommittedData` làm:

1. Java `HttpClient` gửi JSON qua HTTP socket đến embedded Tomcat `RANDOM_PORT`.
2. Spring MVC deserialize JSON vào Java record.
3. Controller gọi service và JPA repository.
4. PostgreSQL container thực hiện INSERT/transaction.
5. HTTP response mang 201 + `Location` + JSON body.
6. Test JDBC query trực tiếp PostgreSQL và thấy row sau HTTP response.
7. Một HTTP GET thứ hai đọc lại dữ liệu qua controller/service/repository.

Đây là nhiều bằng chứng hơn `when(repository.save(...)).thenReturn(...)`; nó kiểm tra kết nối giữa các tầng thật. Tuy nhiên HTTP localhost không chứng minh ingress, TLS hay external load balancer production.

### 11.3. Test 3 kiểm tra cú pháp PostgreSQL-specific

`nativeIlikeQueryIsActuallyRunByPostgres` đưa ba records vào PostgreSQL và gọi endpoint tìm kiếm. Native query sử dụng `ILIKE`, parameter binding và `ORDER BY code`. Test yêu cầu cả kết quả matching và nonmatching; nếu SQL sai hoặc datasource không phải PostgreSQL, test có khả năng phát hiện.

Không suy luận từ test nhỏ này rằng query đủ nhanh ở bảng hàng triệu rows. Với search performance cần index/`EXPLAIN` và dữ liệu gần thực tế. `ILIKE '%word%'` có thể cần trigram index để đáp ứng tải lớn, tùy yêu cầu.

### 11.4. Test 4 kiểm tra unique constraint thật

`postgresRejectsDuplicateBusinessKey` lưu hai entities khác ID nhưng trùng `code`. PostgreSQL phải từ chối INSERT thứ hai theo unique constraint được Hibernate tạo ở lab, Spring Data repository exception translation thông thường phát `DataIntegrityViolationException`.

Do `GenerationType.IDENTITY`, SQL INSERT có thể xảy ra trong `save` hoặc `saveAndFlush`; bọc **toàn bộ `saveAndFlush` trong lambda assertThrows** giúp không phụ thuộc vị trí cụ thể bên trong method. Nếu database dùng deferred constraints, lỗi có thể chỉ xuất hiện tại commit; trong lab unique constraint thông thường không deferred.

Negative test kết thúc ngay sau assertion. Trong test method này **không có `@Transactional` ở JUnit test thread**; repository write methods tự dùng transactions, sau lỗi transaction thứ hai được rollback. `@AfterEach` cleanup thực thi trong một repository transaction mới.

### 11.5. Test 5 xác nhận response thật của API

`missingItemReturns404FromRunningHttpServer` gửi GET đến server trên cổng được cấp, nhận **HTTP 404** từ Spring MVC exception handling, rồi xác nhận không có record trong PostgreSQL. Đây khác với một unit test chỉ assert service ném exception.

Không assert default error JSON body vì nó có thể thay đổi theo Boot error configuration, content negotiation và version. Nếu public API định nghĩa error schema cố định, thêm `@RestControllerAdvice` và test schema ấy.

## 12. Chạy dự án và kết quả dự kiến

Trước tiên cần một container runtime được Testcontainers hỗ trợ, Maven dependencies tải được và JDK 17. Từ project có Gradle Wrapper tương thích:

```bash
./gradlew test
./gradlew test --tests example.catalog.CatalogPostgresIntegrationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.catalog.CatalogPostgresIntegrationTest
```

**Kết quả dự kiến:** **5 test methods pass** nếu Docker/runtime, PostgreSQL image và dependency versions đúng. Gradle thường báo `BUILD SUCCESSFUL`; port, container ID, database credentials do Testcontainers cấp và thời gian chạy là giá trị động.

Bài viết này **không tuyên bố đã chạy Docker hay ghi nhận logs thật**. Code được thiết kế để chạy trong một project như cấu trúc; test cần được thực thi trên máy/CI có môi trường phù hợp để xác nhận.

### 12.1. Lần chạy đầu có thể chậm hơn

Lần đầu Testcontainers có thể phải pull image PostgreSQL; sau đó container runtime có image cache nên các lượt chạy có thể nhanh hơn. Khởi động PostgreSQL vẫn tốn tài nguyên hơn Mockito/H2 đơn giản.

Trên CI có network chậm hoặc registry rate limit, test có thể fail trước khi chạy assertions. Khi đó xem log image pull/container startup, không sửa repository SQL nếu chưa có bằng chứng SQL lỗi.

### 12.2. Lệnh test bị skip có phải pass không?

Nếu project chọn tách fast tests và integration tests bằng Gradle task/source set hoặc JUnit tags, một lần `test` xanh chỉ xác nhận **những tests thực sự được execute**. Nếu integration test bị exclude/disabled, không được báo “PostgreSQL integration đã PASS”.

Với lab này, class không có skip condition; thiếu Docker sẽ làm test startup fail. Trong project thật có thể thêm `@EnabledIfEnvironmentVariable` để chỉ bật ở CI integration stage, nhưng phải báo rõ SKIPPED khi biến chưa bật.

## 13. Vì sao không cần hardcode cổng PostgreSQL?

Ví dụ anti-pattern:

```properties
spring.datasource.url=jdbc:postgresql://localhost:5432/catalog
spring.datasource.username=postgres
spring.datasource.password=postgres
```

Nếu máy đang chạy PostgreSQL local, test có thể ghi nhầm một database không thuộc test; nếu 5432 bị chiếm, container không thể bind như mong đợi. Testcontainers thường map PostgreSQL container port 5432 sang **cổng host ngẫu nhiên**, tránh collisions giữa CI jobs.

Khi dùng `@ServiceConnection`, Boot nhận JDBC URL/username/password từ container. Khi dùng trực tiếp Testcontainers API:

```java
String url = postgres.getJdbcUrl();
String username = postgres.getUsername();
String password = postgres.getPassword();
```

Đây là snippet gắn với biến container đã được khởi động, **không** phải secrets cố định cần hardcode. Không log password ra console.

### 13.1. Container-to-container networking khác host-to-container

Nếu application cũng chạy trong container (không phải JVM host), `localhost` là địa chỉ trong **container đó**, không phải tự động trỏ PostgreSQL container. Khi cần nhiều containers trong cùng Docker network, có thể dùng network aliases để service gọi nhau theo DNS alias trong network, thay vì lấy host mapped port.

Lab chạy Spring Boot trong test JVM của host và PostgreSQL trong container. `@ServiceConnection`/Testcontainers JDBC URL phù hợp với kiến trúc này.

## 14. Test data isolation: service thật còn state thật

Mock thường không giữ state giữa tests trừ khi bạn cố ý cấu hình. PostgreSQL/Redis/Kafka trong container **có thể giữ state** qua các methods trong cùng lifecycle:

- PostgreSQL: rows, tables, sequences, schemas.
- Redis: keys, TTL, streams.
- Kafka: topics, offsets, consumer groups và messages.
- MongoDB: collections, documents, indexes.
- RabbitMQ: queues, exchanges, unacked messages.

Do đó, test phải có **isolation strategy**, không chỉ “có container” là sạch.

### 14.1. Với PostgreSQL

Lab dùng một database trong container dành riêng cho một class, xóa rows của repository trước/sau tests. Vì không chia sẻ container với hệ thống khác, `repository.deleteAll()` có phạm vi được biết trước.

Với suite nhiều test classes:

- Dùng schema/database riêng theo test run khi thích hợp.
- Dùng unique business keys và cleanup đúng records.
- Không assert sequence bắt đầu từ 1 sau rollback.
- Tránh các tests chạy parallel trên cùng tables nếu cleanup có thể xóa dữ liệu lẫn nhau.
- Với migration tests, tạo fresh schema/container hoặc reset có kiểm soát.
- Nếu test lưu trong transaction đã commit (HTTP server thread), test-managed rollback ở JUnit thread **không** hoàn tác server commits.

### 14.2. Với Kafka

Để test consumer thật, cần phân biệt:

- Topic name riêng theo test hoặc test run.
- Consumer group IDs riêng để offset cũ không làm test skip messages.
- Await/poll có timeout thay vì `Thread.sleep` cố định.
- Acknowledgment, retries, dead-letter topic và partition ordering.
- Broker container đã sẵn sàng trước khi producer/consumer kết nối.

Một mock `KafkaTemplate.send` không chứng minh broker nhận record, key serializer có đúng hay consumer có commit offset hay không.

### 14.3. Với Redis

Thao tác `SET`/`GET`/`EXPIRE` có thể được test với Redis container để xác minh wire protocol, serialization, TTL và key semantics. Nhưng một Redis instance đơn trong container không chứng minh Redis Cluster failover, eviction dưới memory pressure hoặc Sentinel behavior.

Không dùng `FLUSHALL` lên Redis dùng chung; dùng Redis container riêng hoặc key prefix + cleanup.

### 14.4. Với RabbitMQ

RabbitMQ container có thể xác minh exchange/queue bindings, routing keys, message acknowledgment và redelivery, nhưng broker topology/HA/TLS production còn tùy môi trường. Đảm bảo messages/queues của test không va nhau trong suite.

## 15. Migration, schema và dữ liệu production-like

Lab dùng:

```properties
spring.jpa.hibernate.ddl-auto=create-drop
```

chỉ để dự án có schema ngay trên PostgreSQL container mới. **Đây không phải kiểm thử Flyway/Liquibase migration thật**. Hibernate tạo bảng từ entities không chứng minh scripts production sẽ chạy đúng hoặc upgrade schema có tương thích dữ liệu cũ.

Nếu mục tiêu là kiểm tra migrations:

1. Tạo PostgreSQL test container mới, chọn version gần production.
2. Chạy Flyway/Liquibase migrations giống deployment thực.
3. Đặt Hibernate `ddl-auto=validate` hoặc `none` theo chính sách.
4. Ghi seed data tối thiểu hoặc chạy migration từ schema cũ.
5. Assert index, foreign keys, constraints, query và data preservation.
6. Không để Hibernate `create-drop` tự tạo thay schema của migration test.
7. Khi muốn kiểm tra nâng cấp từ version N-1, bắt đầu từ snapshot/schema N-1 hợp lệ trong môi trường test an toàn.

**Một test Testcontainers vẫn có thể cho false confidence nếu schema nó dùng không phải schema production.**

## 16. Transaction semantics không tự giống nhau

### 16.1. @DataJpaTest rollback mặc định

`@DataJpaTest` thường mở test-managed transaction rồi rollback mỗi method. Điều này rất thuận tiện cho tests dùng JPA repository trực tiếp. Nhưng SQL có thể cần explicit flush để constraints được kiểm tra trước rollback.

### 16.2. @SpringBootTest RANDOM_PORT với server request thread

Trong lab, Java HTTP client gọi embedded Tomcat. Controller-service và PostgreSQL transactions chạy trong server thread, **khác test thread**. Vì vậy `@Transactional` trên JUnit method không tự rollback những writes server đã commit.

Lab cố ý không thêm `@Transactional` lên test class và cleanup bằng repository calls. Khi test body đã trả 201, có thể query JDBC/PostgreSQL để kiểm tra state đã commit.

### 16.3. PostgreSQL transactions khác H2 và không phải mọi lỗi xuất hiện cùng thời điểm

PostgreSQL unique constraints thông thường được kiểm tra khi INSERT/UPDATE SQL thực hiện. Nhưng PostgreSQL cũng hỗ trợ `DEFERRABLE` constraints được kiểm tra lúc commit. Flush có thể gửi SQL mà lỗi vẫn được hoãn.

Nếu test muốn chứng minh transaction isolation, locks/deadlocks hoặc commit-time checks, hãy viết tests có nhiều connections/transactions và schema phù hợp; một HTTP CRUD test đơn giản chưa chứng minh chúng.

### 16.4. Tại sao không đặt @Transactional rồi chỉ tin rollback?

Với full HTTP integration test, các transactions của application có lifecycle riêng. Nếu test thêm JUnit `@Transactional`, bạn có thể nhìn thấy dữ liệu/rollback của repository calls trong test thread nhưng nhầm với server-side behavior. Ranh giới được chứng minh phải dựa vào transactions thực và state được quan sát sau HTTP response.

## 17. Reliability: real services có lợi và có chi phí

**Lợi ích của Testcontainers:**

- Phát hiện configuration/driver/protocol lỗi thật sớm.
- Kiểm tra SQL/broker/serialization trên engine tương ứng.
- Ít phụ thuộc vào shared staging environment.
- Mỗi test run có thể nhận host/port/database credentials riêng.
- Dễ tái hiện lỗi tích hợp trong CI có container runtime.
- Có thể pin service version và tạo clean fixtures.
- Bảo vệ những migrations/unique constraints/indexes mà mocks không thấy.

**Chi phí và trade-offs:**

- Cần container runtime, image registry/network và dung lượng disk.
- Startup kéo dài hơn unit tests; cold image pulls chậm.
- Dịch vụ thật có trạng thái: phải cleanup/isolate.
- Port/network/resource contention vẫn có thể gây flaky tests.
- Container engine/version/topology có thể khác production.
- Test failures có nhiều tầng nguyên nhân: Docker, image pull, app context, database schema, HTTP, business code.
- Reusable container không tự an toàn khi chạy CI/parallel; cần policy rõ.

Giải pháp không phải loại bỏ integration tests, mà **đặt chúng đúng chỗ và thiết kế đáng tin**.

## 18. Chọn dịch vụ container nào theo rủi ro?

| Dịch vụ | Lỗi mock khó bắt | Test oracle có ý nghĩa |
| --- | --- | --- |
| PostgreSQL | Native SQL, constraints, isolation, JPA mapping | Query result, SQLSTATE/constraint, committed row |
| MySQL/MariaDB | Collation, JSON queries, transaction, upsert | Behavior trên đúng MySQL engine/schema |
| MongoDB | BSON mapping, aggregation, unique indexes, query semantics | Raw document và query results |
| Redis | TTL, serialization, pub/sub, stream semantics | Key/value, expiration trong thời gian hữu hạn |
| Kafka | Serialization, partition key, consumer offsets, retry | Broker nhận record và consumer nhận/ack đúng |
| RabbitMQ | Routing keys, bindings, acknowledgments | Message được route/ack và redeliver đúng |
| Elasticsearch/OpenSearch | Analyzer/index mappings, query DSL | Search results sau index refresh/await |
| LocalStack/cloud emulators | Một tập AWS-like APIs và request contracts | API behavior trong phạm vi emulator |
| External HTTP mock server | REST request/response contract được mô phỏng | HTTP path/body/headers với response do test quy định |

**Lưu ý LocalStack:** dù chạy container, nó là **một emulator**, không phải AWS service production thật. Tên “container” không tự bảo đảm loại engine thật. Phải phân biệt **real service container** (PostgreSQL/Kafka broker) và **emulator/fake container** (một số cloud service simulators) khi định nghĩa bằng chứng test.

Nếu product cần TLS/IAM/failover của managed cloud service, phải có tests ở môi trường phù hợp; container local không đủ.

## 19. Khi nào mock vẫn nên là lựa chọn đầu tiên?

Một số bài toán không được cải thiện bởi PostgreSQL container:

- Hàm tính tổng tiền, thuế hoặc discount không chạm database.
- Retry/backoff decision khi một outbound call ném timeout.
- Mapping Java DTO thuần sang Java domain object.
- Auth policy logic ở lớp service đã được tách ra khỏi security infrastructure.
- Luồng lỗi khi repository trả `Optional.empty()`.
- Các edge cases khó tái tạo bằng real server như “phản hồi sau đúng 17 giây”, ở test unit có thể dùng fake clock/fault injection.

Trong unit test, fake/mocks tạo điều kiện lỗi có thể kiểm soát được. Với integration, real service xác minh các hợp đồng quan trọng mà fake **có thể giả định sai**.

**Không bỏ hết unit tests để thay bằng một suite Testcontainers chậm**: bạn sẽ mất feedback nhanh và khả năng cô lập lỗi logic.

## 20. Giới hạn về tính tương đương production

### 20.1. Đúng loại dịch vụ chưa chắc đúng phiên bản

PostgreSQL 16 trong container không chứng minh mọi behavior PostgreSQL 15/17 hoặc vendor managed với extensions khác nhau. Pin image đúng major/version quan trọng, và chạy compatibility matrix khi ứng dụng hỗ trợ nhiều versions.

### 20.2. Khác topology

Một node PostgreSQL, Kafka broker hoặc Redis đơn không giống cluster/sharded/replicated deployment. Các lỗi leader election, failover, replication lag, quorum và multi-zone partition cần test môi trường/topology tương ứng.

### 20.3. Khác authentication và TLS

Container lab thường dùng credentials được cấp tự động và localhost traffic. Production có thể dùng TLS, mTLS, IAM/LDAP, secrets rotation, certificate trust chains. Integration lab xanh không xác nhận các tầng đó.

### 20.4. Khác network và latency

Docker localhost có latency rất nhỏ, ít packet loss. Cross-region network, DNS, load balancer, proxy, firewall và service mesh có thể làm timeouts/retries khác biệt. Dùng fault-injection proxy (ví dụ Toxiproxy container) hoặc staging chaos tests nếu network faults là yêu cầu — không tự tạo sleep để giả lập toàn bộ network behavior.

### 20.5. Khác dữ liệu và workload

Một vài rows không thể đại diện cho dataset 10 triệu rows, indexes bão hòa, connection pool exhaustion hay query planner statistics. Performance/throughput tests cần dữ liệu và workload phù hợp, chạy riêng khỏi những integration correctness tests nhỏ.

### 20.6. Khác file/volume lifecycle

Container có ephemeral filesystem trừ khi mount volumes. Production thường có persistent storage, backup/restore, disk limits. Mất container không là bằng chứng backup hoặc disaster recovery hoạt động.

## 21. Kiểm soát test suite và Spring TestContext cache

### 21.1. Static @Container theo JUnit class

Trong lab chỉ có một `CatalogPostgresIntegrationTest`, nên `@Testcontainers` + static `@Container` phù hợp.

### 21.2. Bẫy cache context giữa test classes

Spring TestContext có thể cache `ApplicationContext` giữa classes có cấu hình giống nhau. JUnit Testcontainers extension dừng static container **sau khi class kết thúc**. Một test class sau nếu tái dùng cached Spring context/datasource đến một container đã dừng có thể fail connection.

Khi suite có nhiều integration classes và muốn reuse một database:

- Cân nhắc Spring-managed container lifecycle (container as bean) nếu phù hợp Boot version.
- Hoặc dùng singleton container pattern có vòng đời kéo dài bằng JVM/context, không dùng JUnit `@Container` stop ở mỗi class.
- Không kết hợp singleton container pattern với `@Testcontainers`/`@Container` trên chính singleton field vì extension sẽ stop container cuối class.
- Khi cần isolation nghiêm ngặt, tạo context/database/container riêng theo class và biết chi phí startup.
- Không dùng `@DirtiesContext` như cách mặc định để né mọi lifecycle vấn đề; nó tăng startup và không thay thế cleanup state.

### 21.3. Reusable container không phải singleton container

Testcontainers có tính năng reusable containers ở một số versions, nhưng nó có thể là tính năng experimental/opt-in và không phù hợp CI do trạng thái còn tồn tại sau test. Đừng nhầm với **singleton container pattern trong cùng test JVM** (quản lý vòng đời thủ công).

Khi bật reuse, test phải có isolation/reset chặt; không tin container đã sạch sau lần chạy trước.

### 21.4. Chạy song song

JUnit/Testcontainers JUnit extension được tài liệu hóa chủ yếu cho sequential execution. Khi bật parallel:

- Các tests dùng chung PostgreSQL DB có thể xóa dữ liệu lẫn nhau.
- Kafka consumer group offsets có thể tranh chấp.
- Redis key names có thể collision.
- Container startup có thể quá tải CPU/memory.
- Context cache và singleton state có thể tạo phụ thuộc thứ tự.

Giữ lab chạy tuần tự. Nếu thật sự cần parallel, cô lập state theo test run và quản lý lifecycle/synchronization rõ.

## 22. Kết nối hai container trong cùng một network

Khi cả ứng dụng và database đều chạy trong Docker (khác lab host JVM), dùng network alias thay vì hardcode mapped host port:

```java
Network network = Network.newNetwork();

GenericContainer<?> db = new GenericContainer<>(
        DockerImageName.parse("postgres:16-alpine"))
        .withNetwork(network)
        .withNetworkAliases("db")
        .withExposedPorts(5432);
```

Đây chỉ là snippet minh họa **network wiring**, chưa runnable như PostgreSQL module: còn cần environment variables, service-specific wait strategy, app container và cleanup network. Trong container network, application container có thể dùng hostname `db` và container port 5432 nếu PostgreSQL thực sự được cấu hình và ready.

Trong lab host-JVM, đơn giản hơn: dùng `PostgreSQLContainer` + `@ServiceConnection`; không tự tạo Docker network chỉ để gọi PostgreSQL.

**Container hostname/port trong network và mapped host/port là hai hệ địa chỉ khác nhau**. Đúng loại URI phụ thuộc bên gọi đang chạy trên host hay trong container.

## 23. CI/CD: quyết định đặt Testcontainers ở giai đoạn nào

Một pipeline hợp lý:

```text
Pull request
   |
   +-- compile / static analysis
   +-- unit tests (Mockito/Java logic)
   +-- fast Spring slices where appropriate
   +-- critical Testcontainers integration tests
   |
   v
Merge / main branch
   |
   +-- full Testcontainers matrix: DB, broker, cache
   +-- migration compatibility tests
   +-- API contract tests
   |
   v
Pre-release/staging
   |
   +-- deployment smoke: TLS/ingress/auth
   +-- performance/failover/fault injection as required
```

Không nhất thiết chạy mọi container integration case ở mỗi keystroke. Nhưng các test có rủi ro cao (schema, native SQL, message contracts) nên có gate trong pipeline đủ sớm để phát hiện trước production.

### 23.1. Điều kiện CI

- Agent có container runtime được Testcontainers hỗ trợ.
- Có thể pull images qua registry/mirror.
- Có đủ CPU/memory/disk cho PostgreSQL/Kafka v.v.
- Cho phép Testcontainers resource cleanup theo policy.
- Có network/volume permissions phù hợp.
- Docker daemon hoặc remote runtime được cấu hình bảo mật.
- Credentials test chỉ dành cho test, không dùng production secrets.
- CI logs không in passwords/tokens.

### 23.2. Docker-in-Docker hoặc remote runtime

Trong một số CI agents, test JVM chạy **bên trong container** và kết nối Docker daemon ngoài. Khi đó mapped host address mà Testcontainers trả về có thể không là `localhost` của JVM container. Đừng viết test tự lắp `localhost:randomPort` cho external services. Dùng `container.getHost()`/`getMappedPort()`/`getJdbcUrl()` hoặc service connection để runtime xử lý đúng.

### 23.3. CI image cache và reproducibility

Caching images giảm thời gian pull nhưng có thể che việc registry tag đã đổi. Với test cần ổn định mạnh, pin digest, kiểm soát dependency versions và nâng theo lịch bảo trì. Không dựa vào `latest` ở main branch cho những tests bảo vệ release.

### 23.4. Không tắt integration tests âm thầm

Nếu Docker chưa có, nên:

- Fail rõ ở stage bắt buộc.
- Hoặc skip/disable với thông báo minh bạch ở stage không bắt buộc.
- Báo số executed/failed/skipped và điều kiện môi trường.

**BUILD SUCCESSFUL + 0 integration tests executed không phải bằng chứng PostgreSQL đã đúng**.

## 24. Timeout và chẩn đoán lỗi từ đúng tầng

| Dấu hiệu | Tầng có khả năng lỗi | Cách điều tra |
| --- | --- | --- |
| `Could not find a valid Docker environment` | Container runtime | Docker/socket/permissions/remote daemon |
| `ImagePullBackOff`/pull failure | Registry/network | Image name/tag/auth/rate limit |
| Container startup timed out | Service initialization | Logs/wait strategy/memory/volume |
| `Connection refused` | Host/port/service chưa ready | JDBC URL/mapped port/container state |
| `Failed to load ApplicationContext` | Spring configuration | Root cause bean, datasource, migration |
| `No suitable driver` | JDBC classpath | PostgreSQL driver/runtime dependencies |
| `relation does not exist` | Schema | Hibernate DDL/Flyway/Liquibase/table name |
| `DataIntegrityViolationException` | Database constraint | Unique/FK/NOT NULL, SQLSTATE |
| H2 test pass, PostgreSQL native query fail | SQL dialect | Test đúng vendor/query |
| HTTP 404 | Routing/URL | Context path/controller mapping |
| HTTP 401/403 | Security | Authentication/authorization/CSRF |
| HTTP 500 | Application/server | Root cause logs, DB exception |
| Test pass riêng, fail trong suite | Shared state/cache/lifecycle | Cleanup, parallelism, static container |
| Unexpected data persisted after test | Transaction scope | Server-side commit vs test rollback |
| Test rất chậm | Image pull/startup/queries | Profiling, cache, reuse strategy |
| `No tests found` | Gradle/JUnit discovery | Method annotations/`useJUnitPlatform`/test filter |

### 24.1. Connection refused khác HTTP 404

**Connection refused** nghĩa là không có TCP connection thành công tới host/port được chỉ định. **HTTP 404** nghĩa là client đã nhận response từ một server trên đường kết nối. Đừng sửa repository query nếu test chưa kết nối được database.

### 24.2. Testcontainers logs

Khi test fail startup, logs của container có thể rất hữu ích:

```java
String logs = postgres.getLogs();
```

Đây là snippet trong class có `postgres`. Tránh in toàn bộ logs chứa credentials/secrets vào public CI artifacts. Khi container đã bị dừng và log retention bị hạn chế, cấu hình log consumer/report đúng nhu cầu trước test.

### 24.3. Root cause ưu tiên trước exception bao ngoài

`Failed to load ApplicationContext` có thể bắt nguồn từ PostgreSQL container chưa ready, JDBC credentials sai, schema migration lỗi hoặc bean injection lỗi. Xem chain `Caused by` đầu tiên liên quan, kiểm tra container/DB state rồi mới điều chỉnh Spring annotations.

### 24.4. Khi HTTP create thất bại nhưng Postgres đang chạy

Kiểm tra:

1. HTTP client gọi đúng `@LocalServerPort`?
2. JSON body và `Content-Type` đúng?
3. Controller/service bean được nạp?
4. JPA transaction manager/connection details đúng?
5. Schema đã tạo hoặc migrations đã chạy?
6. Constraints và SQL exceptions có đúng expected?
7. Error handler có che status/root cause không?

Một container health check xanh không chứng minh application API xử lý đúng.

## 25. Security và dữ liệu test

Không đưa production datasets hoặc credentials vào integration tests khi không cần thiết. Một PostgreSQL test container có thể chứa fixture giả, nhưng vẫn có thể ghi logs hoặc artifact trên disk của CI.

Quy tắc an toàn:

- Dùng synthetic fixtures, không copy personal data từ production.
- Không để CI có network/credentials ghi vào production DB.
- Không in passwords, tokens, PII hay raw HTTP auth headers.
- Dùng private registry/image digest được tổ chức tin cậy khi cần.
- Hạn chế quyền Docker daemon; socket access có thể tương đương quyền mạnh trên host.
- Đặt retention/cleanup cho image layers, volumes, debug logs và test reports.
- Khi test có `deleteAll()` hoặc `dropDatabase()`, chỉ thực hiện trên dedicated test container/schema.
- Với broker, không publish messages vào production topics/queues.
- Với Redis, không gọi `FLUSHALL` trên shared instance.
- Nếu Testcontainers phải dùng remote daemon, xem xét bảo mật network/TLS và boundaries.

**Một kết quả test chính xác vẫn không chấp nhận được nếu test có thể phá dữ liệu thật**.

## 26. Bài tập thực hành

### Bài 1 — Đo giá trị của mock và container

Viết unit test `ItemService.byCode` với mocked `CatalogRepository` trả `Optional.empty()` và assert 404-related exception. Sau đó chạy `missingItemReturns404FromRunningHttpServer` trong lab. Nêu rõ unit test kiểm tra service decision, integration kiểm tra HTTP/server/DB boundary.

### Bài 2 — Chứng minh actual vendor

Trong `actualDatasourceIsPostgreSql`, tạm đổi expected database product name thành H2. Test phải fail khi thực sự dùng PostgreSQL. Khôi phục. Vì sao chỉ có PostgreSQL driver trong Gradle không là bằng chứng?

### Bài 3 — Chứng minh ILIKE thật

Thay query native `ILIKE` bằng một cú pháp không hợp lệ trên PostgreSQL trong nhánh học tập. Chạy `nativeIlikeQueryIsActuallyRunByPostgres` và đọc lỗi từ database. Khôi phục. Nếu chỉ mock repository trả hai rows, vì sao lỗi SQL không được phát hiện?

### Bài 4 — Unique constraint

Thêm hai inserts cùng `code` và xem `DataIntegrityViolationException`. Thử bỏ unique constraint annotation trên fresh container/schema, test có thể không còn nhận duplicate violation. Khôi phục. Giải thích vì sao test của lab kiểm tra DDL Hibernate tạo, chưa kiểm tra Flyway migration.

### Bài 5 — Transaction sau HTTP request

Chạy test POST rồi đọc `JdbcTemplate` trong JUnit thread sau HTTP 201. Thử thêm `@Transactional` trên test method ở nhánh riêng, xem vì sao nó không rollback writes do server request thread commit. Thiết kế cleanup đúng.

### Bài 6 — Đổi Testcontainers lifecycle

Thử chuyển static `@Container` thành instance field trên một class riêng nhỏ; quan sát startup time/number of containers. Đừng coi mỗi method mở một container là bắt buộc để có isolation nếu database đã được reset an toàn.

### Bài 7 — Migration thật

Thêm Flyway `V1__create_catalog_items.sql` dành cho PostgreSQL vào project biến thể, chuyển `ddl-auto=validate`, xác nhận migration chạy trên container trước khi repository tests. Thêm migration dùng native index/constraint để thấy lợi ích đúng vendor.

### Bài 8 — Image version

Pin `postgres:15-alpine` rồi chạy integration tests để kiểm tra compatibility, sau đó `postgres:16-alpine`. Không tự kết luận mọi version sẽ giống nhau; xem query/schema differences và production support matrix.

### Bài 9 — Redis TTL

Tạo một RedisContainer hoặc GenericContainer phù hợp, lưu key với TTL ngắn, dùng polling có timeout để kiểm tra expiration. Không dùng fixed sleep duy nhất như một phương pháp đáng tin; không flush shared Redis database.

### Bài 10 — Kafka event contract

Tạo test Kafka broker container, một producer và một consumer có consumer group ID riêng, gửi event rồi đợi consumer nhận bằng polling/timeout. Assert key/headers/payload và offset/ack behavior theo contract. So sánh với Mockito test `KafkaTemplate.send`.

### Bài 11 — Context cache bug

Thiết kế hai test classes cùng Spring configuration nhưng cùng static container được JUnit extension stop ở cuối class đầu. Quan sát vì sao cached ApplicationContext ở class sau có thể giữ datasource trỏ container đã dừng. Sửa bằng lifecycle quản lý đồng nhất, không che lỗi bằng retry vô hạn.

### Bài 12 — Fault injection

Kết hợp Toxiproxy (trong môi trường test) hoặc test double có kiểm soát để tạo timeout/network disconnect, xem client retry/backoff. Giải thích vì sao một database container healthy không tự kiểm tra behavior khi mạng mất.

## 27. Checklist trước khi đánh dấu integration test PASS

- [ ] Tôi biết **hành vi nào cần engine thật**, không chỉ nói “integration mạnh hơn”.
- [ ] Tôi không thay unit tests thuần bằng container vô ích.
- [ ] Tôi phân biệt real service container, embedded emulator và mock server.
- [ ] Dịch vụ chạy đúng loại/phiên bản hoặc biết giới hạn compatibility.
- [ ] Container runtime/image permissions sẵn sàng và logs hữu ích khi fail.
- [ ] `@Testcontainers`/`@Container` lifecycle được thiết kế phù hợp test scope.
- [ ] `@ServiceConnection` hoặc `@DynamicPropertySource` gắn app tới đúng container.
- [ ] Không hardcode Docker mapped port hoặc dùng localhost sai network context.
- [ ] Với `@DataJpaTest` Boot 3.3, tôi hiểu datasource replacement và `Replace.NONE`.
- [ ] Test xác minh actual DB vendor hoặc service identity khi mục tiêu cần.
- [ ] Test gửi query/request thật chứ không chỉ assert bean khác null.
- [ ] Có positive và negative cases: dữ liệu đúng, vi phạm constraint, not found.
- [ ] Có SQL/schema migrations thực nếu chính migrations là mục tiêu.
- [ ] Data fixture/cleanup không đụng production hay state test khác.
- [ ] Tôi không nhầm flush với commit, hay test rollback với server-side rollback.
- [ ] CI có stage chạy integration tests thực sự, không chỉ skip.
- [ ] Context cache và container lifecycle không để connection trỏ container đã dừng.
- [ ] Thứ tự tests không ảnh hưởng kết quả; nếu chạy parallel có isolation riêng.
- [ ] Test không mặc định chứng minh TLS, sharding, replication hoặc managed-cloud behavior.
- [ ] Không log secrets hoặc cấp production network credentials vào test job.
- [ ] Khi test fail, tôi phân loại container startup vs app context vs SQL vs HTTP.
- [ ] Không bịa thời gian chạy, output hay status test chưa được thực thi.

## 28. Quy tắc quyết định cuối cùng

```text
Hành vi cần kiểm tra?
      |
      +--> Pure business Java logic?
      |       -> Unit test + fake/Mockito.
      |
      +--> MVC/JSON/controller contract riêng?
      |       -> @WebMvcTest + MockMvc.
      |
      +--> JPA mapping với SQL cơ bản?
      |       -> @DataJpaTest + embedded database,
      |          hoặc PostgreSQL container nếu cần vendor.
      |
      +--> PostgreSQL-specific SQL/migrations/constraints?
      |       -> @DataJpaTest or @SpringBootTest
      |          + PostgreSQL Testcontainers.
      |
      +--> HTTP -> service -> repository -> DB?
      |       -> @SpringBootTest(RANDOM_PORT)
      |          + real HTTP client + PostgreSQL container.
      |
      +--> Kafka/Redis/RabbitMQ protocol semantics?
      |       -> Module container tương ứng +
      |          producer/consumer/client thật.
      |
      +--> Production ingress/TLS/failover/cloud IAM?
              -> Staging/deployment/chaos tests
                 với đúng topology/configuration.
```

**Tổng kết:** Testcontainers không phải công cụ thay thế mọi test mà là cách **đưa dịch vụ thực tới gần bài test**. Khi lỗi có thể nằm ở PostgreSQL/Kafka/Redis/MongoDB driver, SQL, schema, protocol hoặc persistence semantics, chạy một service engine thật trong container giúp kiểm tra những giả định mà mock không hề chứng minh. Giá trị ấy chỉ trọn vẹn khi test gửi thao tác thật, assert kết quả quan sát được, cô lập state, kiểm soát lifecycle và thừa nhận những khác biệt còn lại so với production.

## 29. Tài liệu chính thức

- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — Testcontainers support và Service Connections: https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html
- Spring Boot 3.3 — Spring Boot Testcontainers APIs: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/testcontainers/service/connection/ServiceConnection.html
- Spring Boot 3.3 — AutoConfigureTestDatabase và replacement: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.html
- Testcontainers — Overview: https://java.testcontainers.org/
- Testcontainers — PostgreSQL module: https://java.testcontainers.org/modules/databases/postgres/
- Testcontainers — JUnit Jupiter integration: https://java.testcontainers.org/test_framework_integration/junit_5/
- Testcontainers — Container lifecycle management: https://testcontainers.com/guides/testcontainers-container-lifecycle/
- Testcontainers — Networking: https://java.testcontainers.org/features/networking/
- Testcontainers — Wait strategies: https://java.testcontainers.org/features/startup_and_waits/
- Testcontainers — Reusable containers caveats: https://java.testcontainers.org/features/reuse/
- Testcontainers — Testing a Spring Boot REST API: https://testcontainers.com/guides/testing-spring-boot-rest-api-using-testcontainers/
- Spring Framework — TestContext transactions: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
- Spring Framework — TestContext context caching: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- PostgreSQL — `ILIKE` pattern matching: https://www.postgresql.org/docs/current/functions-matching.html
- Spring Data JPA — Query methods and transactions: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- JUnit Jupiter — Test lifecycle and assertions: https://docs.junit.org/current/user-guide/
