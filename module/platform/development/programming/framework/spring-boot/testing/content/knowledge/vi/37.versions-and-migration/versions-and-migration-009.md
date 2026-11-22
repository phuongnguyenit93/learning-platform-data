# Thay đổi test database replacement, service connection và thư viện container

Một bài `@DataJpaTest` đang dùng PostgreSQL Testcontainers chạy xanh ở Spring Boot 3.3, nhưng sau khi nâng phiên bản, kết quả truy vấn hoặc câu SQL trở nên khác. Có khi chỉ vì Spring Boot đã **thay `DataSource` bằng H2**, có khi vì từ Spring Boot 3.4 logic test-database replacement đổi mặc định để **nhận diện container database**, có khi `@ServiceConnection` được khai báo nhưng không tạo được `JdbcConnectionDetails`, hoặc classpath đã trộn Testcontainers 1.x và 2.x. Một lỗi nguy hiểm là test xanh trên H2 trong khi người viết tưởng đã kiểm PostgreSQL và migrations thực.

Bài Knowledge **“Thay đổi test database replacement, service connection và thư viện container”** thuộc phần **Phiên bản và chuyển đổi** của module **Spring Boot – testing**. Đây là hướng dẫn nâng cấp và chẩn đoán thực hành, không chỉ là bảng thay số phiên bản. Ta xác định **database thực sự được nối**, **vì sao framework chọn nó**, **độ ưu tiên giữa connection details và properties**, **lifecycle của container** và **dependency versions đi theo BOM nào**. Sau đó viết các tests khiến CI **thất bại rõ ràng nếu PostgreSQL bị thay thành H2**.

**Mốc được dùng để chạy ví dụ chính:** Java 17+, Spring Boot **3.5.16**, Spring Framework 6.2.x, Gradle, JUnit 5, Spring Data JPA, H2 và PostgreSQL Testcontainers **1.21.4** do Spring Boot 3.5 quản lý. Trong nhánh Spring Boot 4.x, một số packages/test modules và Testcontainers **2.x** đã thay đổi; mã chạy của Boot 3.5 không được copy nguyên imports/artifacts sang Boot 4 mà không chuyển đổi. Hãy luôn đọc **BOM và Java API docs của đúng minor version đang dùng**.

**Quy tắc kiểm thử:** Đừng chỉ assert repository trả được hàng. Khi bài test *phải* dùng PostgreSQL, assert chính xác `DatabaseMetaData.getDatabaseProductName()`, connection URL/connection details trong phạm vi an toàn và ít nhất một khác biệt có ý nghĩa (migration/constraint/query). Nếu test chỉ chạy trên H2, nói rõ “H2 slice test” thay vì “integration với production dialect”.

## 1. Mục tiêu học tập

- Giải thích `@AutoConfigureTestDatabase` hoạt động ở JDBC/JPA test slices, không phải tất cả Spring tests.
- Phân biệt bốn giá trị `Replace.ANY`, `AUTO_CONFIGURED`, `NON_TEST`, `NONE`.
- Nhớ thay đổi mặc định: Spring Boot **3.3: ANY**, từ **3.4/3.5: NON_TEST**.
- Hiểu điều kiện để `NON_TEST` nhận diện datasource đã nối test database từ containers/`@DynamicPropertySource`/Testcontainers JDBC URL.
- Biết `@ServiceConnection` tạo `ConnectionDetails` tương ứng và **ưu tiên hơn `spring.datasource.*` connection properties** khi auto-configuration sử dụng details.
- Biết `spring-boot-testcontainers` phải nằm trong test dependencies khi muốn dùng service connections.
- Phân biệt `@Container` static field, `@TestConfiguration @Bean` container và `@ImportTestcontainers` về lifecycle/Context cache.
- Viết một `@DataJpaTest` H2 rõ ràng và một `@DataJpaTest` PostgreSQL giữ nguyên DB.
- Dùng `JdbcConnectionDetails` và JDBC metadata để kiểm DB thực sự được chọn.
- Kiểm một full `@SpringBootTest` dùng `@ServiceConnection` khác test slice replacement thế nào.
- Biết `@DynamicPropertySource` là cách thay thế linh hoạt; không cần bắt buộc đồng thời với `@ServiceConnection` cho cùng JDBC DB.
- Chọn `Replace.NONE` khi test cần giữ chính xác datasource, nhất là khi migration giữa versions.
- Phân biệt Testcontainers JDBC URL `jdbc:tc:...` với Java-managed PostgreSQLContainer.
- Nắm cơ chế BOM/version alignment và sự khác biệt **Testcontainers 1.x vs 2.x** về Maven artifact/package.
- Biết cách chuyển Spring Boot 3.5 → 4.x mà không import sai `DataJpaTest`/`AutoConfigureTestDatabase`.
- Xử lý Docker unavailable, image pull, driver missing, constructor/package mismatch và DB cache contamination.
- Thiết kế kế hoạch nâng cấp với baseline, version matrix, negative tests, log và rollback.
- Không chạm vào production DB, Docker daemon của người khác hoặc credentials production trong tests.

## 2. Tại sao “bài test vẫn xanh” đôi khi là tín hiệu sai?

Giả sử repository có một native query phụ thuộc PostgreSQL. Nếu test bị thay bằng H2 hoặc không chạy migration thật, có hai khả năng:

1. Test fail sớm vì cú pháp SQL không tương thích. Đây là dấu hiệu dễ thấy.
2. Test vẫn pass vì query tương thích cả hai, nhưng **không hề kiểm** partial index, JSONB, type mapping, lock/transaction hoặc constraint semantics của PostgreSQL.

Trường hợp 2 nguy hiểm hơn: CI xanh nhưng bằng chứng đã đổi. Tên class `ProductPostgresIntegrationTest` hoặc một `PostgreSQLContainer` được khởi động **không chứng minh** `DataSource` mà Spring Repository dùng đang trỏ vào container đó. Container có thể chạy bên cạnh trong khi `TestDatabaseAutoConfiguration` đã thay `DataSource` bằng embedded H2.

**Kỹ thuật phòng thủ:** Assert vendor DB và một truy vấn/constraint theo đúng test goal, không chỉ `contextLoads`. Log một phần metadata **không chứa username/password/token**, tránh in toàn bộ JDBC URL nếu nó có credentials nhúng.

## 3. Bản đồ thay đổi phiên bản chính

| Nhánh | `@AutoConfigureTestDatabase.replace` mặc định | Container được giữ thế nào? | Thư viện Testcontainers và imports |
|---|---|---|---|
| Spring Boot 3.3.x | `ANY` | Thường cần `replace=NONE` để tránh datasource bị thay trong slice | Boot BOM 3.3 manages Testcontainers 1.x; `org.testcontainers.containers.PostgreSQLContainer` |
| Spring Boot 3.4.x | `NON_TEST` (mới ở 3.4) | Thử nhận diện test DB từ container/metadata/dynamic URL | Testcontainers 1.x; bean overrides `@MockitoBean` cũng bắt đầu phổ biến |
| Spring Boot 3.5.16 | `NON_TEST` | Giữ các test DB **được nhận diện** và auto-configured; kiểm connection thực | Boot BOM quản lý Testcontainers **1.21.4**; imports 1.x |
| Spring Boot 4.0/4.1 | `NON_TEST` | Logic chủ đạo tương tự nhưng module/package test tách theo công nghệ | BOM của nhánh mới quản lý Testcontainers 2.x; nhiều artifacts/packages đổi tên |

Các phiên bản trong bảng là các mốc **đã đối chiếu với API/BOM**, không phải lời khuyên tự nâng trực tiếp từ 3.3 lên bất kỳ 4.x patch nào. Spring Boot 4 còn có breaking changes về module layout và requirements khác: đọc migration guide của nhánh đích, không chỉ sửa version plugin.

### 3.1. Điểm rơi thay đổi ở 3.4

Spring Boot 3.4 giới thiệu `NON_TEST` và thay mặc định cũ `ANY`. Mục tiêu là tránh thay một datasource đã được nhận diện là **test database từ Testcontainers** bằng H2 trong `@DataJpaTest`/`@JdbcTest`. Do đó một test “không đổi source” nhưng đổi Spring Boot có thể thay database thực sự được sử dụng.

**Không dùng default làm hợp đồng dài hạn nếu test phải chạy đúng vendor.** Với bài bắt buộc PostgreSQL, `@AutoConfigureTestDatabase(replace=NONE)` nói rõ intent và thường ổn định hơn khi chạy trên nhiều versions. Với bài chủ đích H2, dùng `Replace.ANY` hoặc cấu hình explicit H2 để tránh dựa vào tự đoán.

## 4. AutoConfigureTestDatabase thực sự xử lý cái gì?

Trong Spring Boot 3.5, annotation:

```java
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;

@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class SomeJpaOrJdbcTest {
    // Một fragment chú thích; hoàn thiện cùng test slice phù hợp.
}
```

chỉ cấu hình việc **thay thế DataSource được test auto-configuration xử lý**. Nó không đổi một cách thần kỳ mọi connection của R2DBC, MongoDB hay Redis. Nếu có nhiều `DataSource` beans, tài liệu API nói **chỉ `@Primary DataSource`** được xét trong replacement behavior; các datasource khác cần test configuration/verification riêng.

Các slices như `@DataJpaTest` và `@JdbcTest` bao gồm test database auto-configuration tương ứng. `@SpringBootTest` thuần **không tự động thay datasource bằng H2 chỉ vì H2 có trong test classpath**; nếu muốn replacement trong full context, phải áp chính annotation/config phù hợp. Mức độ “embedded DB tự động” còn phụ thuộc app configuration và driver có trên classpath.

## 5. Bốn lựa chọn Replace, nên dùng lúc nào?

| Replace | Ý nghĩa | Dùng khi |
|---|---|---|
| `ANY` | Thay `DataSource` dù tự cấu hình hay khai báo thủ công | Slice cố tình luôn chạy H2/embedded DB |
| `AUTO_CONFIGURED` | Chỉ thay `DataSource` được Boot auto-configure | Cần mô phỏng hành vi cũ có phân biệt datasource thủ công |
| `NON_TEST` | Thay datasource **trừ khi** nó được auto-configure và kết nối tới một test database đã được nhận diện | Mặc định từ Boot 3.4, hỗ trợ container test |
| `NONE` | Không thay `DataSource` hiện có | PostgreSQL Testcontainers/real DB test chắc chắn cần giữ |

Với `NON_TEST`, từ “test” **không có nghĩa** “tên database có hậu tố _test”. Boot dựa vào thông tin cấu hình/metadata cụ thể. Một URL `jdbc:postgresql://localhost:5432/mydb` dù có tên `test` không tự bảo đảm Boot sẽ coi là recognized test database.

### 5.1. `AUTO_CONFIGURED` không có nghĩa “chỉ thay production DB”

Nó dựa vào **bean origin** (được Boot tự cấu hình), không dựa vào môi trường production/test. Một datasource được auto-configure đang trỏ vào PostgreSQL Testcontainers có thể bị thay khi dùng `AUTO_CONFIGURED`. Vì thế không dùng nó để “bảo vệ container”; mục đích phục hồi hành vi cũ cần được xác định rõ.

### 5.2. `ANY` có thể biến PostgreSQL test thành H2 test

Một class được gắn:

```java
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY)
class IntendedPostgresTest {
    // Nếu embedded H2 sẵn, @DataJpaTest có thể dùng H2.
    // Container chạy không bảo đảm repository dùng PostgreSQL.
}
```

Snippet này chưa có imports/container setup, dùng để minh họa ý nghĩa lựa chọn. Trong test thật, inspect JDBC metadata sau context startup để biết điều gì đã xảy ra.

## 6. NON_TEST nhận diện test database bằng dấu hiệu nào?

Theo Java API Boot 3.5, các trường hợp được xem là test database gồm:

1. Bean definition có `ContainerImageMetadata`, bao gồm các Testcontainers databases được khai báo `@ServiceConnection` và các connections từ Docker Compose.
2. `spring.datasource.url` có giá trị được cung cấp bởi `@DynamicPropertySource`.
3. `spring.datasource.url` dùng **Testcontainers JDBC URL syntax**, ví dụ `jdbc:tc:postgresql:17-alpine:///testdb`.

Ý nghĩa thực tế: Boot 3.4/3.5 có thể **giữ** một datasource auto-configured sử dụng những nguồn được nhận diện. Nhưng nếu người viết tự tạo `@Bean DataSource` hoặc override bằng config phức tạp, việc nhận diện có thể khác. `NON_TEST` có điều kiện “auto-configured and connecting to a test database”, không đơn giản là “bất kỳ bean có liên quan Docker”.

**Quy tắc:** Nếu yêu cầu test PostgreSQL là bắt buộc, đặt `Replace.NONE` để diễn đạt intent hoặc ít nhất **assert database vendor** để bắt regression. Nếu thử nghiệm default `NON_TEST` là chính mục tiêu của bài học, cố tình không thêm NONE và viết assertions xác nhận cách Boot nhận diện.

## 7. @ServiceConnection giải quyết vấn đề gì?

Từ Spring Boot 3.1, `@ServiceConnection` trên Testcontainers declaration cho phép Boot tạo các `ConnectionDetails` beans dựa vào loại container hoặc tên image. Auto-configuration dùng `ConnectionDetails` để cấu hình JDBC/R2DBC/Redis/Kafka/etc., thay vì bạn tự chép host, mapped port, username và password vào nhiều `spring.*` properties.

Ví dụ trong Boot 3.5 (snippet):

```java
@Testcontainers
@SpringBootTest
class PostgresServiceConnectionExample {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:17-alpine");

    // Boot có thể tạo JdbcConnectionDetails cho datasource.
}
```

Cần imports từ `org.testcontainers.containers.PostgreSQLContainer`, `org.testcontainers.junit.jupiter.*`, `org.springframework.boot.testcontainers.service.connection.ServiceConnection` và thư viện `spring-boot-testcontainers`. Container do JUnit Testcontainers extension quản lý khi có `@Container`; còn Spring Boot tạo connection details.

### 7.1. Không nhầm ServiceConnection với container lifecycle

`@ServiceConnection` **không phải** annotation thay `@Container` của JUnit hoặc `@Bean` của Spring. Nó nói “container này là nguồn thông tin kết nối” cho auto-configuration. Container vẫn phải được **tạo, start và stop** bằng lifecycle phù hợp. Với `@Bean` container, Spring Boot 3.5 có thể quản lý start/stop theo ApplicationContext; với static field, `@Testcontainers` extension quản lý lifecycle.

## 8. ConnectionDetails ưu tiên hơn connection properties như thế nào?

Spring Boot service connection docs: khi một `ConnectionDetails` phù hợp được tạo, nó **ưu tiên hơn** thông tin kết nối trong các properties tương ứng mà auto-configuration sẽ sử dụng. Ví dụ:

```properties
# Nếu có JdbcConnectionDetails từ PostgreSQLContainer,
# URL dưới đây không nhất thiết là URL DataSource đang dùng!
spring.datasource.url=jdbc:h2:mem:decoy
```

Nếu app context import PostgreSQL container bean với `@ServiceConnection`, Boot JDBC auto-config có thể dùng JDBC URL, user/password từ `JdbcConnectionDetails` thay cho `spring.datasource.url`. Vì vậy đọc `Environment.getProperty("spring.datasource.url")` **chưa chứng minh** actual database connection.

**Phép kiểm đáng tin:** `dataSource.getConnection().getMetaData().getDatabaseProductName()` hoặc JDBC connection metadata trong test-only code, cộng `JdbcConnectionDetails.getJdbcUrl()` để điều tra nguồn. Không log password và không coi property H2 “decoy” là chứng cứ DataSource là H2.

### 8.1. Nguồn JdbcConnectionDetails

Trong Boot 3.5, interface:

```java
import org.springframework.boot.autoconfigure.jdbc.JdbcConnectionDetails;
```

có các methods như `getJdbcUrl()`, `getUsername()`, `getPassword()` và default `getDriverClassName()`. Không print toàn bộ bean fields nếu logging/CI có thể lộ credentials. Tên bean và nguồn của nó có thể khác theo auto-config; test không nên phụ thuộc vào số lượng auto-config internals nếu không cần.

## 9. @DynamicPropertySource: lựa chọn khi không dùng ServiceConnection

Trước service connections và trong các trường hợp custom services, `@DynamicPropertySource` là cách đưa các giá trị động vào Spring Environment:

```java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url",
            postgres::getJdbcUrl);
    registry.add("spring.datasource.username",
            postgres::getUsername);
    registry.add("spring.datasource.password",
            postgres::getPassword);
}
```

Đây là snippet, cần container `postgres` và imports `org.springframework.test.context.DynamicPropertyRegistry/DynamicPropertySource`. Trong Boot 3.5, default `NON_TEST` nhận diện database URL từ `@DynamicPropertySource` theo rule tài liệu; trong Boot 3.3, default `ANY` có thể vẫn thay datasource, vì vậy thường cần **`@AutoConfigureTestDatabase(replace=NONE)`**.

**Không khai báo cả `@ServiceConnection` và `@DynamicPropertySource` cho cùng JDBC container nếu không có lý do rõ.** Bạn sẽ có hai nguồn cấu hình cùng mô tả database, khiến khó biết path nào đang active. Chọn một cơ chế và assert kết nối thực sau khi nâng cấp.

## 10. Testcontainers JDBC URL: một con đường thứ ba

Testcontainers hỗ trợ JDBC URL pattern:

```properties
spring.datasource.url=jdbc:tc:postgresql:17-alpine:///catalog_test
spring.datasource.driver-class-name=org.testcontainers.jdbc.ContainerDatabaseDriver
```

Khi sử dụng đúng Testcontainers JDBC module/driver, container được khởi tạo qua cơ chế JDBC URL. Đây khác việc tự tạo `PostgreSQLContainer` Java object và dùng `@ServiceConnection`. Trong Boot 3.5, default NON_TEST có logic nhận diện `jdbc:tc:` là test datasource.

**Giới hạn:** Việc tự khởi container từ JDBC URL có lifecycle/khả năng reuse khác container Spring `@Bean` hoặc JUnit `@Container`. Không tự tạo đồng thời ba container paths rồi nghĩ chúng trỏ vào một database. Nếu project dùng Flyway, HikariCP và multiple connections, cần kiểm migration chạy đúng URL và thời điểm container startup.

**Khuyến nghị chọn một phương pháp chính** trong mỗi nhóm tests; giữ các lựa chọn khác như các kịch bản migration riêng.

## 11. Thư viện cần có cho Spring Boot 3.5 + PostgreSQLContainer

Với Spring Boot 3.5.16, BOM đã quản lý Testcontainers **1.21.4**; dùng coordinates **không kèm version**:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:postgresql'
    testImplementation 'org.testcontainers:junit-jupiter'
    testRuntimeOnly 'org.postgresql:postgresql'
}
```

**Phân vai dependency:**

- `spring-boot-starter-test`: JUnit Jupiter, Spring Boot Test và assertions.
- `spring-boot-testcontainers`: Boot integration, `@ServiceConnection`, connection-details factories.
- `org.testcontainers:postgresql`: PostgreSQLContainer class (Testcontainers **1.x**).
- `org.testcontainers:junit-jupiter`: `@Testcontainers`/`@Container` extension cho static fields.
- `org.postgresql:postgresql`: JDBC driver (module container không tự thay driver).
- `org.testcontainers:jdbc`: thêm nếu dùng `jdbc:tc:` path và module chưa được transitively cung cấp theo đúng setup.

Không trộn ví dụ của Testcontainers 2.x vào BOM 3.5. Một build có `org.testcontainers:postgresql:1.21.4` nhưng cũng khai `org.testcontainers:testcontainers-postgresql:2.0.5` có nguy cơ trùng classes/cấu trúc phụ thuộc, class loading errors và API bất nhất. Chọn một version family có chủ đích.

## 12. Testcontainers 1.x và 2.x: thay đổi tọa độ/artifact/package

Một điểm rất dễ lỗi khi đọc blog hiện tại trong project Boot 3.5: tài liệu Testcontainers Java **mới** mô tả nhánh 2.x, trong khi Boot 3.5 BOM dùng 1.21.x. Mô hình chuyển đổi:

| Thành phần | Testcontainers 1.21.x | Testcontainers 2.x |
|---|---|---|
| Core | `org.testcontainers:testcontainers` | Core giữ cùng nhóm/tên |
| PostgreSQL module | `org.testcontainers:postgresql` | `org.testcontainers:testcontainers-postgresql` |
| JUnit 5 extension | `org.testcontainers:junit-jupiter` | `org.testcontainers:testcontainers-junit-jupiter` |
| Java PostgreSQLContainer | `org.testcontainers.containers.PostgreSQLContainer` | `org.testcontainers.postgresql.PostgreSQLContainer` |
| Module Redis/Kafka/... | 1.x module coordinates/packages tương ứng | 2.x module artifacts/packages mới, phải tra từng module |
| Version quản lý | Spring Boot 3.5 BOM: **1.21.4** | Một số Spring Boot 4.x BOM: **2.0.x** |

Đây là hai **nhánh tương thích cần migration**, không chỉ “đổi version string”. Khi nâng lên Testcontainers 2.x, update cả **Gradle coordinates, imports, API constructor/generics, transitive dependencies và Docker compatibility**. Đừng tự thêm `2.0.5` vào Boot 3.5 build rồi giữ toàn bộ imports 1.x; muốn override BOM phải có compatibility assessment đầy đủ.

### 12.1. Imports rất dễ bị copy nhầm

**Boot 3.5 / Testcontainers 1.x:**

```java
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
```

**Khi sử dụng Testcontainers 2.x modules/packages mới:**

```java
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
```

Phần JUnit package có thể giữ, nhưng **artifact tọa độ** của extension đổi. Nếu code có wildcard imports hoặc module-specific classes như MongoDB/Kafka, kiểm từng package theo API v2. Với 2.x, không copy `PostgreSQLContainer<?>` generic style cũ một cách vô điều kiện; theo docs mới, class có thể có API signature khác. Mục 20–25 của bài **chỉ dành cho Boot 3.5/Testcontainers 1.x**.

## 13. Spring Boot 4.x còn đổi cả test annotations/imports

Ngoài Testcontainers, Spring Boot 4 modular hóa test support theo công nghệ. Ví dụ:

| Khái niệm | Boot 3.5 import | Boot 4.x import |
|---|---|---|
| `@DataJpaTest` | `org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest` | `org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest` |
| `@AutoConfigureTestDatabase` | `org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase` | `org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase` |
| `@ServiceConnection` | `org.springframework.boot.testcontainers.service.connection.ServiceConnection` | Kiểm API của nhánh 4.x, package service-connection trong module Boot Testcontainers |
| Module test slice | `spring-boot-test-autoconfigure`/starter-test layout 3.x | Module chuyên biệt `spring-boot-data-jpa-test`, `spring-boot-jdbc-test` và starters theo nhánh 4.x |

Do đó một migration 3.5→4.x cần audit **dependency artifact** và **Java package** đồng thời. “Cannot resolve symbol DataJpaTest” không có nghĩa Boot 4 bỏ chức năng JPA slice; có thể chỉ đổi package/module. Đừng tự đổi code 3.5 runnable bên dưới sang 4.0 mà giữ Gradle 3.5 artifacts; đó là mixing không hợp lệ.

**Tài liệu đối chiếu:** JavaDoc `@DataJpaTest`/`@AutoConfigureTestDatabase` của đúng Boot 4.x branch, managed dependency coordinates và migration guide. Không nên lấy latest docs luôn luôn nếu repository chưa nâng major.

## 14. Chọn cơ chế theo mục tiêu test

| Bạn muốn kiểm gì? | Cách phù hợp | Annotation/chú ý |
|---|---|---|
| Repository method với SQL portable, PR rất nhanh | H2 `@DataJpaTest` | `Replace.ANY` nếu muốn ép embedded; assert H2 |
| PostgreSQL-specific query, JSONB, partial index | PostgreSQL Testcontainers + `@DataJpaTest` | `@ServiceConnection`, `Replace.NONE` rõ intent hoặc default NON_TEST + assert |
| Full service transaction/proxy + Postgres | `@SpringBootTest` + Postgres container | Không bị slice replacement mặc định; assert vendor |
| Cấu hình legacy/custom JDBC | `@DynamicPropertySource` | `Replace.NONE` với slice khi muốn bất biến qua versions |
| PostgreSQL test mà không tạo container Java object | `jdbc:tc:` URL | JDBC module, driver, lifecycle và default replacement |
| Nhiều datasources | Bean-specific test config | `@Primary`/qualifiers, assert từng datasource |
| R2DBC | R2dbcConnectionDetails/test support riêng | JDBC replacement không tự áp cho R2DBC |
| MongoDB/Redis/Kafka | Respective connection-details factory | Không dùng `AutoConfigureTestDatabase` cho NoSQL |
| Migrations Flyway/Liquibase | DB cùng dialect và migration thật | Không dùng `ddl-auto=create-drop` làm giả migrations |
| Kiểm ngược hành vi Boot 3.3 | Explicit `Replace.ANY` trên Boot3.4+ | Cố ý, có DB assertion để không tạo false confidence |

**Một bài test có thể dùng H2 và vẫn tốt**, miễn là tên/gate/bằng chứng nói đúng. Vấn đề không nằm ở H2 mà ở **sự nhầm lẫn database đang chạy**.

## 15. Demo chạy được: catalog một bảng nhỏ

Ta tạo Spring Boot app lưu `CatalogItem` gồm:

- `id`: UUID do JPA/Hibernate sinh.
- `sku`: mã hàng, unique ở database.
- `priceCents`: số nguyên không âm.

Repository có `findBySku`, service có `create`, `load`. Ta chia tests:

1. **EmbeddedReplacementTest:** `@DataJpaTest` + `Replace.ANY`, assert **H2**.
2. **PostgresDefaultNonTestTest:** `@DataJpaTest` + `@Import(PostgresContainerConfig)`, **không đặt replace override** để kiểm default `NON_TEST` trên Boot 3.5; assert **PostgreSQL**.
3. **PostgresExplicitNoneTest:** `@DataJpaTest` + `Replace.NONE`, khẳng định explicit policy; assert **PostgreSQL**.
4. **PostgresFullContextTest:** `@SpringBootTest` + test container config, kiểm `JdbcConnectionDetails` ưu tiên một decoy `spring.datasource.url` và service ghi/đọc PostgreSQL qua transaction thật.

Demo không có controller/API, vì mục tiêu của bài là **data source selection và migration**, không phải HTTP serialization. Với một service cần kiểm HTTP, có thể bổ sung `@SpringBootTest(RANDOM_PORT)` nhưng không thay đổi cơ chế datasource chính.

## 16. Cây thư mục và preconditions

```text
database-test-migration/
  settings.gradle
  build.gradle
  src/main/java/com/example/dbmigration/
    DbMigrationApplication.java
    CatalogItem.java
    CatalogRepository.java
    CatalogService.java
  src/test/resources/
    application.properties
  src/test/java/com/example/dbmigration/
    PostgresContainerConfig.java
    EmbeddedReplacementTest.java
    PostgresDefaultNonTestTest.java
    PostgresExplicitNoneTest.java
    PostgresFullContextTest.java
```

Yêu cầu:

- Java 17+, Gradle Wrapper tương thích Boot 3.5, Maven Central.
- Docker daemon/runtime **đang hoạt động** và có quyền kéo/chạy image `postgres:17-alpine` để chạy ba PostgreSQL tests.
- Môi trường không có Internet phải có image cache phù hợp hoặc internal registry được cấu hình hợp lệ.
- `H2` và `postgresql` JDBC drivers có trong test runtime classpath.
- Không chỉ vào production DB; container của demo tạo **database test riêng**.
- Không thay credentials/registry/path ngoài phạm vi nếu chưa có quyền.

**Trung thực về execution:** Source dưới đây được thiết kế/rà soát theo docs Boot 3.5.16, nhưng chưa được thực thi trong Gradle/Docker môi trường người học. Phần “expected behavior” không phải log thực tế.

## 17. Gradle full configuration: Boot 3.5 và BOM quản lý Testcontainers

**`settings.gradle`**

```groovy
rootProject.name = 'database-test-migration'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    // H2 used for explicitly embedded slice tests.
    testRuntimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'

    // Boot 3.5.16 BOM selects Testcontainers 1.21.4.
    testImplementation 'org.testcontainers:postgresql'
    testImplementation 'org.testcontainers:junit-jupiter'

    // Testcontainers does not replace a JDBC driver.
    testRuntimeOnly 'org.postgresql:postgresql'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Vì sao không ghi `org.testcontainers:postgresql:1.21.4`?** Khi dùng Spring Boot BOM + io.spring.dependency-management, bỏ version để dependency graph thống nhất. Nếu tự override lên 2.x nhưng không thay artifacts/imports của toàn suite, dễ tạo classpath không nhất quán.

**Vì sao H2 và PostgreSQL driver là testRuntimeOnly?** Main app core chỉ cần JPA interfaces; các database được chọn trong tests. Nếu muốn `bootRun` ngoài tests, cấu hình datasource/driver ở runtime app riêng. Không gửi JDBC username/password cố định qua repo ngoài mục training.

### 17.1. Cách xem phiên bản thực sự resolve

```bash
./gradlew dependencyInsight \
  --dependency org.testcontainers:postgresql \
  --configuration testRuntimeClasspath

./gradlew dependencies \
  --configuration testRuntimeClasspath
```

Lệnh này giúp xem version conflict/selection. `dependencyInsight` và Gradle report không tự chứng minh Docker đang chạy hoặc test nối đúng PostgreSQL. Cần kết hợp `DataSource` metadata assertions trong JUnit tests.

## 18. Spring Boot application class

**`src/main/java/com/example/dbmigration/DbMigrationApplication.java`**

```java
package com.example.dbmigration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DbMigrationApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                DbMigrationApplication.class, args);
    }
}
```

Đặt application root trong package bao entity/repository/service để `@DataJpaTest` quét đúng JPA và `@SpringBootTest` nạp đúng app. Không thêm `@EnableJpaRepositories` thừa nếu cấu trúc package chuẩn đã đủ.

## 19. JPA entity và repository

**`src/main/java/com/example/dbmigration/CatalogItem.java`**

```java
package com.example.dbmigration;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.util.UUID;

@Entity
@Table(
        name = "catalog_items",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_catalog_items_sku",
                columnNames = "sku"))
public class CatalogItem {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false, length = 40)
    private String sku;

    @Column(nullable = false)
    private long priceCents;

    protected CatalogItem() {
        // Required by JPA.
    }

    public CatalogItem(String sku, long priceCents) {
        if (sku == null || sku.isBlank() || priceCents < 0) {
            throw new IllegalArgumentException(
                    "Invalid catalog item");
        }
        this.sku = sku;
        this.priceCents = priceCents;
    }

    public UUID getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public long getPriceCents() {
        return priceCents;
    }
}
```

**`src/main/java/com/example/dbmigration/CatalogRepository.java`**

```java
package com.example.dbmigration;

import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CatalogRepository
        extends JpaRepository<CatalogItem, UUID> {

    Optional<CatalogItem> findBySku(String sku);
}
```

Entity có unique constraint chung H2/PostgreSQL; tests dùng `saveAndFlush` để lỗi SQL xuất hiện trong boundary rõ. Không dùng constraint này để tuyên bố H2 giống PostgreSQL về mọi index/locking semantics.

## 20. Service thật với transaction

**`src/main/java/com/example/dbmigration/CatalogService.java`**

```java
package com.example.dbmigration;

import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CatalogService {

    private final CatalogRepository repository;

    public CatalogService(CatalogRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public UUID create(String sku, long priceCents) {
        CatalogItem item = repository.save(
                new CatalogItem(sku, priceCents));
        return item.getId();
    }

    @Transactional(readOnly = true)
    public CatalogItem load(UUID id) {
        return repository.findById(id).orElseThrow();
    }
}
```

Trong full-context test, gọi `CatalogService.create` thông qua Spring proxy nên transaction commit sau method body. Unit test tạo `new CatalogService(...)` sẽ không kiểm transaction AOP; ở đây chúng ta dùng thật PostgreSQL datasource/repository để bảo đảm behavior xuyên layers.

## 21. Test-only properties: không ghi đè container một cách nhầm lẫn

**`src/test/resources/application.properties`**

```properties
# Training only: generate schema inside owned test databases.
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false

# Avoid accidental H2 in-memory database name collisions.
spring.datasource.generate-unique-name=true

# Uncomment to diagnose which datasource Boot initialized:
# logging.level.org.springframework.boot.autoconfigure.jdbc=DEBUG
# logging.level.org.springframework.boot.test.autoconfigure.jdbc=DEBUG
# logging.level.org.testcontainers=INFO
```

Không đặt `spring.datasource.url=jdbc:h2:mem:...` ở global test properties nếu các PostgreSQL tests cần tự chọn URL qua `@ServiceConnection`. Mẫu full-context cố ý dùng H2 `decoy` **chỉ trên chính class test đó** để chứng minh precedence.

**Quan trọng:** `spring.jpa.hibernate.ddl-auto=create-drop` làm Hibernate tạo schema thử nghiệm, không chứng minh Flyway migrations thực. Khi đánh giá migration compatibility của sản phẩm, chuyển sang chạy Flyway/Liquibase trên database/container cùng dialect và thường dùng `ddl-auto=validate` hoặc `none`, không để Hibernate tạo bảng thay migrations.

## 22. H2 test: cố tình thay DataSource bằng embedded DB

**`src/test/java/com/example/dbmigration/EmbeddedReplacementTest.java`**

```java
package com.example.dbmigration;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY)
class EmbeddedReplacementTest {

    @Autowired
    DataSource dataSource;

    @Autowired
    CatalogRepository repository;

    @Test
    void replacementReallyUsesH2() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            assertEquals("H2",
                    connection.getMetaData().getDatabaseProductName());
        }
    }

    @Test
    void repositoryWorksOnEmbeddedDatabase() {
        String sku = "H2-" + UUID.randomUUID();
        repository.saveAndFlush(new CatalogItem(sku, 1200));

        assertTrue(repository.findBySku(sku).isPresent());
    }
}
```

**Hai tests** nói rõ ý định: đây là **H2 slice**, không phải PostgreSQL integration. `Replace.ANY` yêu cầu thay datasource; có H2 trên test runtime classpath để embedded replacement khả dụng. `@DataJpaTest` mặc định transaction rollback, nên dữ liệu method thứ hai không được commit vào DB chung.

**Vì sao assert vendor?** Nếu một nâng cấp/lỗi config làm `DataSource` trỏ ra PostgreSQL hoặc một database khác, `replacementReallyUsesH2` sẽ fail thay vì tiếp tục chạy với môi trường ngoài ý muốn. Với tests được phép dùng H2/Derby/HSQLDB tùy classpath, assert tên phù hợp với policy đã chọn.

## 23. PostgresContainerConfig: Spring quản lý lifecycle của container

**`src/test/java/com/example/dbmigration/PostgresContainerConfig.java`**

```java
package com.example.dbmigration;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
public class PostgresContainerConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> catalogPostgres() {
        return new PostgreSQLContainer<>("postgres:17-alpine")
                .withDatabaseName("catalog_test")
                .withUsername("catalog")
                .withPassword("test_only");
    }
}
```

Đây là lựa chọn **container bean** của Spring Boot:

- `@TestConfiguration` chỉ được import trong tests cần PostgreSQL; không scan mặc định vào application thường.
- `@Bean` trả về **typed** `PostgreSQLContainer<?>`; Boot có thể suy ra JDBC service connection mà không cần `name`.
- `@ServiceConnection` tạo `JdbcConnectionDetails` từ container.
- Spring quản lý **start/stop theo ApplicationContext lifecycle**, tiện khi Spring TestContext cache reuse context.
- Trong test class dùng `@Import(PostgresContainerConfig.class)`, **không cần** thêm `@Testcontainers/@Container` vì đây là Spring bean chứ không phải JUnit static field.

**Tại sao không dùng cả hai lifecycle cùng lúc?** Đặt `@Container` trên bean method sẽ không làm nó thành một JUnit field. Ngược lại, dùng static `@Container` rồi tự stop container ở `@AfterAll` có thể khiến cached ApplicationContext trong test class khác vẫn giữ DataSource kết nối tới container đã dừng.

### 23.1. Container image và mật khẩu

Image tag `postgres:17-alpine` là ví dụ lab. Production-like CI có thể pin digest để tăng reproducibility/supply-chain integrity. Mật khẩu `test_only` chỉ dành cho database tạo mới trong container test, không dùng cho shared staging/production. Đừng in Postgres connection password trong test reports.

## 24. Spring Boot 3.5 default NON_TEST giữ được PostgreSQL

**`src/test/java/com/example/dbmigration/PostgresDefaultNonTestTest.java`**

```java
package com.example.dbmigration;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest
@Import(PostgresContainerConfig.class)
class PostgresDefaultNonTestTest {

    @Autowired
    DataSource dataSource;

    @Autowired
    CatalogRepository repository;

    @Test
    void defaultNonTestPreservesServiceConnectionPostgres()
            throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            assertEquals("PostgreSQL",
                    connection.getMetaData().getDatabaseProductName());
        }
    }

    @Test
    void repositoryActuallyQueriesPostgres() {
        String sku = "PG-DEFAULT-" + UUID.randomUUID();

        repository.saveAndFlush(new CatalogItem(sku, 2399));

        assertTrue(repository.findBySku(sku).isPresent());
    }
}
```

**Hai tests** chạy PostgreSQL thực trong Testcontainers. Class **không khai báo `@AutoConfigureTestDatabase(replace=NONE)`**, vì chúng ta muốn kiểm behavior default `NON_TEST` của Spring Boot 3.5.16: Spring service connection có container metadata, test-database replacement giữ datasource thay vì thay bằng H2. Nếu chạy cùng code trên Boot 3.3, **đừng giả định** vẫn giữ Postgres: default `ANY` trước 3.4 có thể thay datasource.

Điểm QA quyết định là `getDatabaseProductName()=="PostgreSQL"`. Nếu test đã tạo/khởi container nhưng repository đang dùng H2, test này sẽ fail.

## 25. Explicit NONE: giữ DB rõ ý định, dễ đọc khi migration

**`src/test/java/com/example/dbmigration/PostgresExplicitNoneTest.java`**

```java
package com.example.dbmigration;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
@Import(PostgresContainerConfig.class)
class PostgresExplicitNoneTest {

    @Autowired
    DataSource dataSource;

    @Autowired
    CatalogRepository repository;

    @Test
    void explicitNoneKeepsPostgresDataSource()
            throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            assertEquals("PostgreSQL",
                    connection.getMetaData().getDatabaseProductName());
        }
    }

    @Test
    void generatedUuidAndRepositoryWorkOnPostgres() {
        CatalogItem saved = repository.saveAndFlush(
                new CatalogItem("PG-NONE-" + java.util.UUID.randomUUID(),
                        3100));

        assertNotNull(saved.getId());
    }
}
```

**Hai methods**. `Replace.NONE` khiến intent “không thay datasource” hiển nhiên, giúp review khi migrate giữa Boot 3.3/3.4/3.5. Nó **không tự tạo** PostgreSQL connection; cần `@ServiceConnection`/dynamic properties/JDBC URL để Boot có URL thật. Một test dùng NONE nhưng quên cấu hình URL có thể fail vì không có datasource hoặc trỏ sai host — đây là setup failure cần sửa, không phải lý do bỏ NONE.

**Không nên nói `Replace.NONE` luôn tốt nhất**: với fast H2 slice muốn auto-replacement, NONE có thể giữ nhầm production URL nếu test config bị sai. Chọn mode theo test goal, assert vendor và isolate credentials.

## 26. Full context: @ServiceConnection được ưu tiên hơn URL cấu hình

**`src/test/java/com/example/dbmigration/PostgresFullContextTest.java`**

```java
package com.example.dbmigration;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(properties =
        "spring.datasource.url=jdbc:h2:mem:decoy")
@Import(PostgresContainerConfig.class)
class PostgresFullContextTest {

    @Autowired
    DataSource dataSource;

    @Autowired
    CatalogService service;

    @Autowired
    CatalogRepository repository;

    @Test
    void serviceConnectionOverridesDecoyJdbcUrl()
            throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            assertEquals("PostgreSQL",
                    connection.getMetaData().getDatabaseProductName());
        }
    }

    @Test
    void realServiceCommitsAndCanBeReadBack() {
        String sku = "FULL-" + UUID.randomUUID();
        UUID id = service.create(sku, 4500);

        try {
            CatalogItem loaded = repository.findById(id)
                    .orElseThrow();

            assertEquals(sku, loaded.getSku());
            assertEquals(4500, loaded.getPriceCents());
            assertNotNull(loaded.getId());
        } finally {
            repository.deleteById(id);
        }
    }
}
```

**Hai methods** chạy full Spring app với container Postgres test bean. Ở class này, `spring.datasource.url` cố ý đặt H2 `decoy`, nhưng `JdbcConnectionDetails` từ `@ServiceConnection` ưu tiên khi JDBC auto-config chọn datasource, do đó assertion vẫn phải là **PostgreSQL**. Đây là một phép kiểm migration mạnh hơn chỉ đọc `Environment` property.

Bài test thứ hai **không đặt `@Transactional` trên test class**. `CatalogService.create` có transaction riêng; khi call return, commit đã hoàn thành. Repository readback là một operation khác nên kiểm được dữ liệu committed. `finally` xóa đúng ID test tạo; không xóa toàn database.

**Kết luận giới hạn:** Không có HTTP server ở `@SpringBootTest` mặc định (MOCK web environment do app không có Web starter). Test này chứng minh full service→repository→Postgres wiring/transaction, **không** chứng minh inbound HTTP, authentication hoặc production deployment.

## 27. Tổng tests và kết quả kỳ vọng

| Class | Số `@Test` | Database thực phải thấy | Mục đích |
|---|---:|---|---|
| `EmbeddedReplacementTest` | 2 | H2 | Replacement `ANY` |
| `PostgresDefaultNonTestTest` | 2 | PostgreSQL | Default `NON_TEST` 3.5 |
| `PostgresExplicitNoneTest` | 2 | PostgreSQL | Explicit `NONE` |
| `PostgresFullContextTest` | 2 | PostgreSQL | ServiceConnection precedence + real commit |
| **Tổng** | **8** | H2 + PostgreSQL (container riêng) | Không nhầm vendor DB |

Chạy với Gradle Wrapper:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

JDK 17+, Gradle wrapper hợp lệ, Docker daemon đang chạy và image PostgreSQL khả dụng là **preconditions**. Khi không có Docker, các PostgreSQL tests nên **FAIL setup** ở CI job bắt buộc container, thay vì tự skip toàn bộ mà báo “PostgreSQL verified”.

**Kết quả kỳ vọng từ source review:** 8 tests được thiết kế pass theo Boot 3.5.16 và TC 1.21.4. Đây **không phải log đã chạy Gradle**, chưa có evidence về actual runtime/test report trong repository của người học.

## 28. Vì sao @DataJpaTest có thể chạy với H2 dù Postgres đang khởi động?

Điểm gây nhầm phổ biến:

```java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY)
class WronglyAssumedPostgresTest {
    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:17-alpine");
}
```

Snippet chưa đầy imports/test method, chỉ minh họa. Container được JUnit quản lý và đang chạy **không có nghĩa** Spring JPA datasource tự trỏ vào container. Nếu không có `@ServiceConnection` hoặc DynamicPropertySource, Boot thậm chí chưa được cung cấp host/port/user/password của container. Nếu có nhưng replacement mode `ANY` và H2 tồn tại, datasource có thể bị thay.

**Cách điều tra:**

1. In/log an toàn actual `DatabaseMetaData.getDatabaseProductName()`.
2. Kiểm `@AutoConfigureTestDatabase` effective mode, version mặc định.
3. Kiểm `JdbcConnectionDetails` có được tạo không.
4. Kiểm `PostgreSQLContainer` instance đúng class và đang start.
5. Kiểm test source dùng `@DataJpaTest` (auto-replace) hay `@SpringBootTest` (không same default).
6. Kiểm H2 có trong test classpath không.
7. Kiểm `@Primary DataSource`/multiple datasources.
8. Kiểm migrations và connection URL khi test khởi.
9. Nếu đã xác định test phải là PostgreSQL, dùng `NONE` và vendor assertions.
10. Tránh “fix” bằng xóa H2 dependency toàn project nếu fast H2 slices vẫn cần nó.

## 29. @Container static field và context cache: vấn đề lifetime

Hai mô hình Testcontainers khác nhau:

**JUnit-managed:**

```java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class LegacyContainerTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:17-alpine");
}
```

**Spring-managed (mẫu runnable ở mục 23):**

```java
@TestConfiguration(proxyBeanMethods = false)
class SharedPostgresTestConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgres() {
        return new PostgreSQLContainer<>("postgres:17-alpine");
    }
}
```

Cả hai đều cần Spring Boot testcontainers module để tạo service connection. Với **static field**, JUnit Testcontainers extension quản lý container per test class; Spring TestContext có thể cache ApplicationContext vượt lifecycle của một class. Một class khác reuse cached context nhưng container đã stop thì DataSource có URL cũ, dẫn đến connection refused. Với **Spring bean**, Boot quản lý container theo context và dừng nó khi context đóng; thường an toàn hơn với cache reuse.

Không gọi `postgres.stop()` thủ công trong `@AfterAll` nếu cached context còn sử dụng nó. Khi test container thực sự có lifecycle khác nhau giữa classes, dùng config/context keys khác hoặc quản lý context dirty/teardown có chủ đích; đừng dùng `@DirtiesContext` bừa bãi để thay việc hiểu lifecycle.

## 30. @DynamicPropertySource khi migrate từ code cũ

Một project Boot 3.2/3.3 thường có:

```java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class LegacyDynamicPropertiesTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:17-alpine");

    @DynamicPropertySource
    static void register(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url",
                postgres::getJdbcUrl);
        registry.add("spring.datasource.username",
                postgres::getUsername);
        registry.add("spring.datasource.password",
                postgres::getPassword);
    }
}
```

Đây là **snippet minh họa**, không phải file core runnable: cần imports JUnit, Spring, TC và một test method. Vẫn là cách hợp lệ khi cần custom properties ngoài JDBC hoặc không có service-connection factory phù hợp.

**Khi migrate sang @ServiceConnection:**

1. Bổ sung `org.springframework.boot:spring-boot-testcontainers`.
2. Đánh dấu container bằng `@ServiceConnection` (hoặc chuyển thành Spring `@Bean` container).
3. Chọn một connection source làm chuẩn; bỏ các dynamic JDBC properties dư thừa.
4. Với `@DataJpaTest`, đặt `NONE` nếu muốn explicit DB retention, hoặc kiểm default NON_TEST và assert vendor.
5. Đừng loại DynamicPropertySource cho các **non-database properties** tùy chỉnh nếu chúng vẫn cần.
6. Kiểm bean lifecycle/cache và DB schema migrations.
7. Chạy tests với Docker và đọc JDBC metadata.

Không thay thế DynamicPropertySource chỉ vì annotation mới “ngắn hơn” nếu dự án cần custom schemas, multiple datasources hoặc connection properties không được factory hỗ trợ.

## 31. Container type, image name và ConnectionDetails factories

Spring Boot dùng `ContainerConnectionDetailsFactory` để tạo details từ **container subtype** hoặc **image repository name**. Với các typed containers như `PostgreSQLContainer`, Boot nhận biết khá trực tiếp. Nhưng generic containers có thể thiếu thông tin kiểu khi khai báo `@Bean`:

```java
@TestConfiguration(proxyBeanMethods = false)
class RedisContainerConfig {

    @Bean
    @ServiceConnection(name = "redis")
    GenericContainer<?> redis() {
        return new GenericContainer<>("redis:7-alpine")
                .withExposedPorts(6379);
    }
}
```

Snippet này cần imports `GenericContainer`/Bean/TestConfiguration/ServiceConnection; không thuộc runnable Postgres project. `name="redis"` quan trọng khi Boot không thể suy ra image name từ `@Bean GenericContainer<?>` return type trước khi bean được tạo. Với custom/private images như `registry.company.test/mirror/redis`, `name` cũng giúp factory nhận đúng loại service.

### 31.1. Một container có thể cho nhiều loại ConnectionDetails

`PostgreSQLContainer` có thể tạo `JdbcConnectionDetails` và `R2dbcConnectionDetails` khi các factory/auto-config liên quan hiện diện. Có thể giới hạn bằng `@ServiceConnection(type=...)` nếu cần. Trong project chỉ dùng JDBC, không cần bật R2DBC drivers. **Không giả định R2DBC datasource được thay bởi `@AutoConfigureTestDatabase`**, vì annotation đó chỉ áp trên JDBC DataSource.

## 32. Multiple DataSources và custom @Bean DataSource

Một ứng dụng có `primaryDataSource` cho orders và `auditDataSource` cho audit:

```java
@Bean
@Primary
DataSource primaryDataSource() { /* ... */ }

@Bean
DataSource auditDataSource() { /* ... */ }
```

Đây là snippet giả, chưa có implementations. Với multiple datasources, `@AutoConfigureTestDatabase` chỉ xét `@Primary` bean. Nếu test cần cả hai database cùng Docker, phải cấu hình/qualify và assert **từng** datasource, không suy ra từ một query repository.

Với một DataSource tự định nghĩa qua `@Bean`, Boot JDBC auto-configuration có thể back off. `JdbcConnectionDetails` từ Testcontainers **không bảo đảm override một custom DataSource bean** tự đọc URL riêng/cố định. Bạn phải sửa factory để dùng details, hoặc dùng properties injected đúng cách, hoặc tạo test-specific bean configuration. Một test vendor assertion sẽ bắt việc tự định nghĩa bean khiến Spring Boot auto-config không còn kiểm soát URL.

## 33. Migrations Flyway/Liquibase là một vấn đề khác với replacement

Một bài `@DataJpaTest` dùng H2 và `ddl-auto=create-drop` có thể tạo entity tables hợp lệ nhưng không chạy migrations PostgreSQL thực tế. Khi nâng Boot/Testcontainers, có thể xảy ra lỗi từ:

- Flyway plugin/version và modules riêng cho PostgreSQL.
- Migration script chứa `CREATE INDEX CONCURRENTLY`, JSONB, partial indexes hoặc operators mà H2 không hỗ trợ.
- Schema search path/user permissions khác.
- Liquibase changelog context/labels/tablespaces không giống production.
- Hibernate dialect/validation đổi theo ORM version.
- Container image từ PostgreSQL 14 lên 17 tạo behavior khác.
- Docker Compose service connection tự nhận DB khác environment mong muốn.

**Tách hai mục tiêu:**

1. **JPA fast slice**: H2, Hibernate DDL từ entities, tốc độ cao; không tuyên bố migration validated.
2. **DB migration integration**: PostgreSQL Testcontainers, apply Flyway/Liquibase scripts thật, `ddl-auto=validate` hoặc disable Hibernate DDL phù hợp, assert đúng DB vendor và schema constraints.

Một test integration vẫn dùng `ddl-auto=create-drop` chỉ xác minh Hibernate tạo được schema, **không** chứng minh Flyway migration V001..V100 đã chạy.

### 33.1. ServiceConnection cho Flyway và Liquibase

Boot Testcontainers factory hỗ trợ loại connection details liên quan JDBC/Flyway/Liquibase từ JdbcDatabaseContainer. Nhưng vẫn phải kiểm auto-configuration conditions, libraries Flyway/Liquibase trên classpath và migration locations. Một service connection thành công **không tự chạy migrations** nếu migration engine chưa được thêm hoặc đã bị disable.

## 34. Maven BOM, Gradle BOM và quản lý version

Một build an toàn chọn **một BOM quản lý phù hợp với Spring Boot version**:

```groovy
plugins {
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencies {
    testImplementation 'org.testcontainers:postgresql'
    testImplementation 'org.testcontainers:junit-jupiter'
}
```

Khi dùng plugin dependency management phù hợp, version của Testcontainers module do Spring Boot dependency management chọn. Nếu team cần override phiên bản vì Docker API compatibility/security update, làm **đồng bộ cả family** qua BOM override, kiểm Spring Boot service connection support, rồi chạy test matrix. Không nâng một module đơn lẻ và để core/Testcontainers JDBC/JUnit extension ở versions khác nhau.

**Kiểm đủ hai nơi:**

- Build dependency graph: đúng artifacts/versions và không có version conflicts.
- Runtime JDBC metadata: đúng DB thực (PostgreSQL/H2) và schema/migrations.

`dependencies --configuration testRuntimeClasspath` là bằng chứng về classpath, **không** là bằng chứng DataSource đang trỏ vào container nào.

## 35. Docker và CI khi nâng phiên bản

Testcontainers phụ thuộc một **container runtime khả dụng**. Một CI job chạy tests PostgreSQL cần:

- Docker daemon hoặc runtime được Testcontainers hỗ trợ; quyền truy cập socket/endpoint phù hợp.
- Network/image registry access; pull policy đúng.
- Dung lượng disk và RAM đủ cho container/JVM.
- Image tag/digest được kiểm soát; tránh `latest` tạo thay đổi ngoài ý muốn.
- Không reuse database container của job khác nếu data ownership không rõ.
- Cleanup containers/resources theo test lifecycle; không để leaked Docker networks/volumes.
- CI artifact logs không chứa container password hoặc DB data nhạy cảm.
- Test DB user/role chỉ có quyền trong test container.
- Gradle test task timeout và readiness hữu hạn.
- Nếu Docker unavailable ở required integration job, báo **SETUP FAIL**, không skip rồi tuyên bố integration pass.
- Tránh chạy Testcontainers privileged/unrestricted trong môi trường không được phép; test không phải lý do bỏ security controls.
- Trên Windows/macOS Docker Desktop, kiểm Docker API compatibility với Testcontainers/docker-java version tương ứng.

**Đặc biệt với Spring Boot 3.5:** Boot có hướng dẫn về `docker-java.properties` và Docker Desktop API version compatibility; đừng đổi Docker daemon version/`DOCKER_HOST` bừa bãi trước khi đọc startup cause và dependency graph.

## 36. Dấu hiệu chẩn đoán và hướng xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Cách xác minh / xử lý |
|---|---|---|
| Test tưởng PostgreSQL nhưng JDBC metadata nói H2 | TestDatabase replacement, H2 trên classpath | Kiểm Replace mode, dùng NONE/assert |
| Sau 3.3→3.4 test bỗng chạy PostgreSQL | Default ANY→NON_TEST | Test intent, pin ANY nếu muốn H2 |
| `NoSuchBeanDefinitionException JdbcConnectionDetails` | Không có factory/ServiceConnection hoặc bean creation sai | Kiểm `spring-boot-testcontainers`/container type |
| Container chạy nhưng datasource vẫn sai | Chưa truyền details hoặc custom DataSource bean | Assert actual connection; xem @Bean/auto-config |
| `Failed to replace DataSource with embedded database` | Replace yêu cầu embedded nhưng H2/HSQL/Derby driver không có | Thêm đúng embedded driver hoặc NONE cho PG |
| `Could not find a valid Docker environment` | Runtime/permissions/DOCKER_HOST | Kiểm Docker setup, không skip tự động |
| `No suitable driver` cho PostgreSQL | Thiếu `org.postgresql:postgresql` | Thêm JDBC driver vào test runtime |
| `NoClassDefFoundError org.testcontainers...PostgreSQLContainer` | Trộn 1.x/2.x module hoặc import sai | Căn lại BOM, artifacts, package |
| `ClassNotFoundException Testcontainers JUnit Jupiter` | Thiếu/nhầm module junit extension | Dùng artifact đúng family |
| Boot 4 không tìm `DataJpaTest` cũ | Package/module chuyển | Sửa imports/add module Boot4 |
| Property datasource URL là H2 nhưng metadata là Postgres | `ConnectionDetails` override | Trust JDBC metadata, kiểm factory |
| `@ServiceConnection` trên GenericContainer không có factory | Chưa có name/type hint | `name="redis"` hoặc custom details |
| Docker container stop trước Spring context | Per-class JUnit lifecycle vs cached context | Spring-managed @Bean/ImportTestcontainers |
| Spring cache test khác dùng cổng container cũ | Dynamic property/container lifecycle mismatch | Align context key/lifecycle |
| `@DataJpaTest` không thấy service bean | Slice intentionally excludes service | Import targeted config hoặc full context |
| JPA/Hibernate schema sai trên Postgres | DDL/migrations khác H2 | Run real migrations, validate |
| H2 tests pass nhưng native SQL fail production | DB dialect/feature difference | Postgres integration, not only H2 |
| Test flaps khi parallel | Shared DB/IDs/cached state | Unique fixtures, transaction rollback |
| Boot upgrade báo repository method lỗi | Spring Data/Hibernate semantics change | Read exception root, migration release notes |
| `BeanDefinitionOverrideException` | Hai DB configs/imports gây duplicate beans | Chọn một source, audit qualifiers |
| Password trong CI logs | In toàn bộ ConnectionDetails/JDBC URL | Log productName và masked details |

### 36.1. Bắt đầu từ root cause, không từ exception cuối

Nếu context startup fail, đừng thử bừa `@DirtiesContext`, `@Transactional` hoặc bỏ toàn bộ assertions. Thu thập **exception cause chain đầu tiên**, dependency graph, Boot version, TC version, Docker environment và actual connection details. Mỗi thay đổi chỉ sửa một giả thuyết, chạy lại test đồng nhất.

## 37. Bốn bước debug thứ tự chọn DataSource

```text
1. Context thuộc loại nào?
     @DataJpaTest / @JdbcTest / @SpringBootTest

2. Replace mode hiệu lực là gì?
     ANY / AUTO_CONFIGURED / NON_TEST / NONE

3. Có kết nối test hợp lệ và được Boot nhận diện không?
     ServiceConnection -> JdbcConnectionDetails
     DynamicPropertySource -> datasource URL
     jdbc:tc:... -> Testcontainers JDBC driver
     custom @Bean DataSource -> có thể bypass auto-config

4. Actual DataSource.getConnection().getMetaData():
     DatabaseProductName = "H2" hay "PostgreSQL"?
     -> Test FAIL nếu khác target.
```

Không bắt đầu từ `spring.datasource.url` duy nhất: với `ConnectionDetails`, property có thể không phản ánh connection được dùng. Không bắt đầu từ việc thấy log `PostgreSQLContainer started`: container có thể không phải DB của repository.

## 38. Quy trình nâng cấp có kiểm soát

**Trước nâng cấp:**

1. Ghi version của Boot plugin, Spring Framework, Spring Data, Hibernate, Testcontainers BOM và Postgres image.
2. Liệt kê JPA/JDBC test slices và annotations `@AutoConfigureTestDatabase` đang áp.
3. Tìm các `@DynamicPropertySource` methods, `@ServiceConnection` fields/beans và `jdbc:tc:` URLs.
4. Xác định tests nào **bắt buộc PostgreSQL** và tests nào **cố ý H2**.
5. Thêm JDBC vendor assertions ở các test đại diện, tránh thay DB âm thầm.
6. Ghi các schemas/migrations và DB-specific tests thực chạy.
7. Baseline Gradle test count, startup times, context cache misses, Docker versions.
8. Đảm bảo test DB isolated, user/credentials không chạm production.

**Trong nâng cấp:**

9. Nâng Boot BOM tập trung, không override Testcontainers từng module ngẫu nhiên.
10. Với Boot3.3→3.4, rà default ANY→NON_TEST.
11. Với Boot3.5→4.x, sửa imports/test modules và TC 1.x→2.x artifacts/packages theo docs.
12. Chỉ chọn một nguồn JDBC connection details cho mỗi test group.
13. Cấu hình `Replace.NONE`/ANY theo intention rõ ràng.
14. Chạy H2 tests trước; sau đó PostgreSQL container tests; cuối cùng full integration/migrations.
15. Nếu context cache tái sử dụng container đã stop, sửa lifecycle thay vì tắt toàn bộ cache.
16. Kiểm từng test thực **đúng database product**, không chỉ pass status.

**Sau nâng cấp:**

17. So sánh query/constraint behavior/migrations, cleanup and rollback.
18. Lưu JUnit XML/HTML reports, dependency insight và Docker diagnostics.
19. Đánh giá performance/CI cost, image pull và memory.
20. Document quyết định thay đổi/test scope/known differences.
21. Nếu rollback version, giữ source/imports/dependency family đồng bộ; không rollback plugin đơn lẻ.

## 39. Các tình huống migration phổ biến

### 39.1. Boot 3.3 → 3.4, H2 fast slice vô tình thành Postgres

Trước đó `@DataJpaTest` mặc định `ANY` có thể thay datasource thành H2; sau nâng Boot 3.4, default `NON_TEST` nhận diện container nên test bắt đầu chạy PostgreSQL, làm CI chậm hơn. Nếu mục đích test là H2 portable mapping, pin `@AutoConfigureTestDatabase(replace=ANY)` và assert `H2`. Còn nếu mục đích là Postgres-specific integration, giữ Postgres và đưa vào đúng CI gate.

### 39.2. PostgreSQL Testcontainers test chạy H2

Thường do `replace=ANY`, không có `@ServiceConnection`/DynamicPropertySource, hoặc custom DataSource override. Đừng chỉ đổi tên class. Assert actual vendor, inspect replacement mode, thêm connection details hoặc NONE.

### 39.3. Boot 3.5 copy docs Testcontainers 2.0

Blog hiện tại dùng `org.testcontainers:testcontainers-postgresql` nhưng Boot 3.5 BOM vẫn quản lý `org.testcontainers:postgresql:1.21.4`. Không kết hợp tùy tiện. Chọn tài liệu của Testcontainers 1.x nếu giữ Boot3.5; nếu nâng Boot4.x, nâng trọn dependency family/modules/imports và test compatibility.

### 39.4. GenericContainer Redis không được nhận dạng

Với `@Bean GenericContainer<?>`, Boot không thể gọi bean sớm để đọc image name; cần `@ServiceConnection(name="redis")` hoặc một details factory/custom bean được hỗ trợ. PostgreSQL typed container ở demo không có vấn đề ấy.

### 39.5. PostgreSQL tests vẫn pass nhưng Flyway migrations không được chạy

`@ServiceConnection` chỉ cung cấp connection details, không tự thêm Flyway hoặc schema scripts. Đảm bảo test dependency/migration locations và `ddl-auto=validate` phù hợp, rồi assert schema được migration tạo. Hãy phân biệt “JPA create-drop pass” và “database migration pass”.

### 39.6. Context cache reuse stale port

Một static `@Container` per-class bị stop sau class A, nhưng context cache được class B tái sử dụng với datasource URL cũ. Dùng Spring-managed container bean cùng lifecycle với cached context hoặc tách contexts đúng cách. Không sửa bằng cách hard-code mapped port, vì Docker mapping là động.

## 40. Bài tập có đáp án

### A. Cấu hình mặc định thay đổi

Một `@DataJpaTest` trên Boot 3.3 mặc định `ANY` và trên Boot 3.5 mặc định `NON_TEST`. Hậu quả có thể là gì?

**Đáp án:** Một datasource test từ Testcontainers được nhận diện có thể được giữ ở Boot3.5 thay vì bị thay bằng embedded H2; test target DB và timing/CI thay đổi. Assert vendor, explicit mode nếu cần.

### B. H2 trên classpath

Một test PostgreSQL có H2 ở `testRuntimeClasspath`. Điều đó có nghĩa Boot chắc chắn chọn H2?

**Đáp án:** Không. Phụ thuộc `@AutoConfigureTestDatabase` mode, JDBC auto-config và `ConnectionDetails`. Kiểm metadata; `NONE` giữ DB khi đúng connection.

### C. Service connection thiếu module

`@ServiceConnection` không resolve import trong Boot3.5. Dependency thường bị thiếu?

**Đáp án:** `testImplementation 'org.springframework.boot:spring-boot-testcontainers'`.

### D. Không có PostgreSQL JDBC driver

Postgres container start nhưng Hikari báo “No suitable driver”. Cần bổ sung gì?

**Đáp án:** PostgreSQL JDBC driver, ví dụ `testRuntimeOnly 'org.postgresql:postgresql'`. Testcontainers module không thay driver.

### E. ConnectionDetails vs property

`spring.datasource.url` hiển thị H2 nhưng `DataSource.getConnection()` báo PostgreSQL. Nên tin gì?

**Đáp án:** Actual JDBC metadata/ConnectionDetails. Service connection có precedence cao hơn connection-related properties trong auto-config.

### F. Multiple datasources

Có hai DataSource beans, một `@Primary`. `@AutoConfigureTestDatabase` tự thay cả hai?

**Đáp án:** Không. API cho biết chỉ primary datasource được xét; test từng datasource và qualifiers.

### G. Testcontainers module version

Bạn thêm `org.testcontainers:testcontainers-postgresql:2.0.5` vào Boot3.5 nhưng còn `org.testcontainers:postgresql:1.21.4`. Có nên merge?

**Đáp án:** Không trước khi đồng bộ version family, imports và kiểm compatibility. Trộn 1.x/2.x là rủi ro classpath.

### H. Package của DataJpaTest trong Boot4

Project nâng Boot4 mà `org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest` không resolve. Nghĩa là DataJpaTest đã biến mất?

**Đáp án:** Không. Boot4 modular hóa; import mới `org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest` và thêm test module/starter phù hợp.

### I. @Bean và @Container

Một method `@Bean PostgreSQLContainer` trong @TestConfiguration có cần `@Container` của JUnit?

**Đáp án:** Không. Spring Boot quản lý container bean lifecycle; dùng `@ServiceConnection` để tạo connection details.

### J. Static container cache

JUnit container stop sau class A, class B reuse Spring ApplicationContext. Triệu chứng?

**Đáp án:** Datasource có thể trỏ port container đã chết. Giải quyết lifetime/caching; không dựa vào random sleep.

### K. Dynamic properties

Một Boot3.3 JPA slice dùng `@DynamicPropertySource`. Có nên vẫn đặt `Replace.NONE`?

**Đáp án:** Có khi bắt buộc giữ container DB vì default ANY. Boot3.4+ NON_TEST nhận diện dynamic URL trong trường hợp phù hợp, nhưng explicit NONE vẫn rõ intent và nên verify actual vendor.

### L. Container image thành công

Log nói `PostgreSQLContainer started`. Có đủ chứng minh repository dùng PostgreSQL?

**Đáp án:** Không. DataSource có thể bị replacement thành H2; assert database metadata.

### M. H2 migration confidence

JPA create-drop trên H2 xanh có chứng minh Flyway PostgreSQL migrations chạy không?

**Đáp án:** Không. Dùng Postgres container, migrations thật và schema validation.

### N. Docker unavailable

CI runner không có Docker, 4 PostgreSQL tests skip bằng assumption, job xanh. Có thể báo “Postgres integration passed”?

**Đáp án:** Không. Đó là NOT RUN/SKIPPED, job cần setup Docker hoặc báo blocker; critical integration gate không được silent green.

### O. JDBC vs R2DBC

Một PostgreSQLContainer cung cấp cả Jdbc/R2dbcConnectionDetails. `@AutoConfigureTestDatabase` có tự thay R2DBC ConnectionFactory không?

**Đáp án:** Không. Annotation hướng tới JDBC DataSource; R2DBC test auto-configuration và driver cần kiểm riêng.

### P. Nên bỏ H2 hoàn toàn?

Cả H2 slice và PostgreSQL integration đều có giá trị. Có nhất thiết bỏ H2 khỏi build để tránh replacement không?

**Đáp án:** Không. Giữ H2 cho fast portable tests nếu có mục tiêu; dùng mode/ConnectionDetails/metadata assertions phân biệt rõ vendor và tránh test nhầm.

## 41. Checklist trước khi merge nâng cấp

- [ ] Biết Spring Boot version/BOM hiện tại và đích, có migration guide đúng nhánh.
- [ ] TestDatabase Replace defaults được so với 3.3/3.4/3.5/4.x.
- [ ] Tôi biết `ANY/AUTO_CONFIGURED/NON_TEST/NONE` khác nhau.
- [ ] H2 fast tests được gắn mode/metadata đúng yêu cầu.
- [ ] PostgreSQL-specific tests assert `DatabaseProductName=PostgreSQL`.
- [ ] Không suy database đang dùng chỉ từ container started logs.
- [ ] Có kiểm `@Primary DataSource` khi multiple datasources.
- [ ] Không coi `spring.datasource.url` property luôn là actual JDBC URL.
- [ ] `@ServiceConnection` có `spring-boot-testcontainers` trong test dependencies.
- [ ] Typed container hoặc image name factory được nhận diện đúng.
- [ ] `GenericContainer` cần name hint nếu factory không suy được từ type.
- [ ] Không khai đồng thời dynamic JDBC props và service connection một cách mơ hồ.
- [ ] Container lifecycle khớp TestContext cache, không stop sớm.
- [ ] `@DataJpaTest`/`@SpringBootTest` được phân biệt replacement behavior.
- [ ] Có PostgreSQL JDBC driver trên test runtime classpath.
- [ ] Testcontainers 1.x artifacts không trộn với 2.x modules.
- [ ] BOM được dùng thay cho tự pin nhiều phiên bản lệch nhau.
- [ ] Sau nâng Boot4, package test annotations/modules đã được đổi đúng.
- [ ] CI có Docker runtime/permissions/image access cho tests cần container.
- [ ] Docker unavailable không tự báo PostgreSQL tests pass.
- [ ] Container image tag/digest và DB engine version được ghi rõ.
- [ ] H2 không dùng để kết luận PostgreSQL JSONB/locking/partial indexes đúng.
- [ ] Flyway/Liquibase migrations được kiểm riêng trên DB cùng dialect.
- [ ] Hibernate create-drop không bị coi là migration test.
- [ ] No production credentials/production DB URLs trong test.
- [ ] Test-owned DB/rows có rollback/cleanup và không đụng data khác.
- [ ] CI artifacts lưu JUnit XML/HTML cùng dependency insight/logs cần thiết.
- [ ] Test count thực chạy không về 0 do tags/skips/source mismatch.
- [ ] Cache misses, container startups và suite duration được đo lại.
- [ ] TestConfig/ConnectionDetails không leak vào production application.
- [ ] Những lỗi startup được phân tích từ root cause, không sửa kiểu thử-vận-may.
- [ ] Có rollback plan đồng bộ version/dependencies/imports khi cần.
- [ ] QA nói rõ code reviewed, chưa phải tests executed nếu chưa chạy thật.

**Kết luận:** Nâng Spring Boot/Testcontainers có thể đổi **database thực** mà bài test đang sử dụng dù logic test không đổi. Spring Boot 3.3 mặc định `Replace.ANY`; từ 3.4 `NON_TEST` giúp nhận diện datasource test đã nối container. `@ServiceConnection` làm Boot tạo `JdbcConnectionDetails` và có thể ưu tiên URL từ container hơn properties, nhưng không tự thay thế lifecycle container hoặc một custom DataSource bean không dùng auto-config. Đồng thời, Boot 3.5 quản lý **Testcontainers 1.21.4**, trong khi Boot 4 và Testcontainers 2.x có module/package changes cần migration. Cách phòng regression tốt nhất không phải “thử đổi annotation cho test xanh”, mà là **ghi rõ mục tiêu H2/Postgres, đồng bộ BOM/imports, assert database metadata, kiểm migrations và quản lý test-data/container lifecycle**.

### Tài liệu tham khảo chính thức

- Spring Boot 3.3 — AutoConfigureTestDatabase JavaDoc, `replace` default ANY: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.html
- Spring Boot 3.5.16 — AutoConfigureTestDatabase JavaDoc, `replace` default NON_TEST: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.html
- Spring Boot 3.5.16 — Replace enum, NON_TEST recognition patterns: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.Replace.html
- Spring Boot 3.4 Release Notes — `@AutoConfigureTestDatabase` and containers: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes
- Spring Boot 3.5 — Testcontainers service connections, container beans and dynamic properties: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Spring Boot 3.5 — Testing Spring Boot Applications, `@DataJpaTest`: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — Managed dependency coordinates, Testcontainers 1.21.4: https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html
- Spring Boot 3.5 — JdbcConnectionDetails API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jdbc/JdbcConnectionDetails.html
- Spring Boot 3.5 — Docker Desktop/Testcontainers Docker API troubleshooting: https://docs.spring.io/spring-boot/3.5/how-to/testing.html
- Spring Boot 4 — DataJpaTest package change: https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/data/jpa/test/autoconfigure/DataJpaTest.html
- Spring Boot 4 — AutoConfigureTestDatabase package change: https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/jdbc/test/autoconfigure/AutoConfigureTestDatabase.html
- Testcontainers 2 — PostgreSQL module/artifact and API: https://java.testcontainers.org/modules/databases/postgres/
- Testcontainers — Managing versions with BOM: https://java.testcontainers.org/
- Spring Framework 6.2 — DynamicPropertySource: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dynamicpropertysource.html
- Spring Framework 6.2 — TestContext caching: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
