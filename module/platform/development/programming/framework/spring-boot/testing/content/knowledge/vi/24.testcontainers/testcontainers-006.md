# @DynamicPropertySource khi cần tự cung cấp cấu hình kết nối cho Testcontainers

## 1. Mục tiêu bài học

Khi chạy integration test với Testcontainers, database, Redis, Kafka hoặc một HTTP service giả lập thường được tạo **động**. Ví dụ, PostgreSQL container có thể mở cổng `5432` bên trong Docker nhưng được ánh xạ sang một cổng ngẫu nhiên trên máy chạy test. Vì vậy, viết cứng `spring.datasource.url=jdbc:postgresql://localhost:5432/... ` trong `application-test.properties` không phải cách cấu hình đáng tin.

Spring TestContext cung cấp **`@DynamicPropertySource`** và **`DynamicPropertyRegistry`** để truyền các giá trị cấu hình **được biết lúc chạy test**, như JDBC URL, username, password, host và mapped port, vào `Environment` trước khi Spring khởi tạo các bean phụ thuộc chúng.

Bài thuộc module **Spring Boot – testing**, nhóm **Testcontainers**, với mục tiêu chính: **dùng `@DynamicPropertySource` khi cần tự cung cấp cấu hình kết nối**. Đây là kỹ thuật tích hợp Spring TestContext, không phải annotation khởi động container.

Sau bài này, bạn có thể:

1. Hiểu đúng chức năng và lifecycle của `@DynamicPropertySource` và `DynamicPropertyRegistry`.
2. Đăng ký cấu hình JDBC động bằng `registry.add("spring.datasource.url", postgres::getJdbcUrl)`.
3. Giải thích vì sao phương thức đăng ký phải là `static` và nhận đúng một tham số `DynamicPropertyRegistry`.
4. Phân biệt `Supplier` lười lấy giá trị với gọi getter container quá sớm.
5. Dùng `@Testcontainers`/`@Container` để quản lý container và đưa connection details vào Spring Boot.
6. Viết `@SpringBootTest` dùng PostgreSQL thật, kiểm JDBC metadata, service và repository.
7. Viết `@DataJpaTest` giữ PostgreSQL container bằng `@AutoConfigureTestDatabase(replace = NONE)` trên Spring Boot 3.3.
8. Kiểm tra đường kết nối **thực sự** thay vì chỉ assert properties.
9. Dùng dynamic properties cho nhiều services hoặc custom configuration prefixes.
10. Chọn giữa `@DynamicPropertySource`, `@ServiceConnection`, `@TestPropertySource` và `@ActiveProfiles`.
11. Tránh bẫy Spring context caching, shared container lifecycle, parallel tests, stale ports, database replacement và lộ credentials.
12. Chạy được ví dụ đầy đủ bằng **Java 17, Spring Boot 3.3.5, Gradle, PostgreSQL Testcontainers và JUnit Jupiter**.

**Kết luận ngắn:** `@DynamicPropertySource` đưa **giá trị kết nối động** vào Spring `Environment`. Nó **không tự khởi động database** và **không tự xác minh app thực sự dùng connection đó**; cần quản lý lifecycle của container và viết assertions trên DataSource/runtime.

## 2. Vấn đề khi cấu hình URL tĩnh

Giả sử Testcontainers khởi động PostgreSQL:

~~~text
PostgreSQL container
  internal port: 5432
          |
          v
Docker host mapped port: 49157  (chỉ là ví dụ)
          |
          v
JDBC URL do container cung cấp:
jdbc:postgresql://localhost:49157/customer_test
~~~

Ở một lượt chạy khác, mapped port có thể là `49231` hoặc một số khác. Con số trong sơ đồ **không phải port cố định mà test được phép giả định**. Testcontainers chọn mapping động để giảm xung đột khi nhiều jobs cùng chạy.

Mẫu cấu hình dễ sai:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/customer_test
spring.datasource.username=test_user
spring.datasource.password=test_password
~~~

Nếu máy developer tình cờ có PostgreSQL ở port 5432, phép thử có thể kết nối **nhầm database** và “xanh giả”. Trên CI không có DB đó, phép thử có thể fail `Connection refused`. Khi parallel jobs cùng đòi một host port, chúng còn có thể xung đột.

Cách đúng là lấy giá trị từ **container instance đang chạy**:

~~~java
@DynamicPropertySource
static void postgresProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

Giải thích:

- `postgres` là một `PostgreSQLContainer<?>` do test khai báo.
- `getJdbcUrl()` trả host, mapped port và database phù hợp với container.
- `getUsername()`/`getPassword()` trả credentials dành cho database test.
- `registry.add(...)` cung cấp properties cho Spring Boot auto-configuration.
- Ba method references truyền **Supplier**, không gọi getter ngay ở bước đăng ký.

## 3. `@DynamicPropertySource` nằm ở đâu?

Import chính xác trong Spring Framework 6.1 / Spring Boot 3.3:

~~~java
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.DynamicPropertyRegistry;
~~~

Phương thức hợp lệ:

~~~java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("feature.endpoint", () -> "http://localhost:18080");
}
~~~

Đây là snippet minh họa API, không phải cấu hình Testcontainers. Cách khai báo bắt buộc:

- Method có annotation `@DynamicPropertySource`.
- Method là **`static`**.
- Method trả **`void`**.
- Method có **một tham số `DynamicPropertyRegistry`**.
- Test chạy với Spring TestContext hỗ trợ dynamic property sources.
- `registry.add(name, supplier)` nhận một property name và một `Supplier` cung cấp value.

Đây không phải annotation đặt lên field container, bean `@ConfigurationProperties` hay method `@Test`. Trong Spring Framework 6.1, phần khai báo dynamic property theo kiểu này thuộc **test class** và được Spring TestContext gọi khi chuẩn bị `ApplicationContext` cho integration test.

### Vai trò của từng thành phần

| Thành phần | Chịu trách nhiệm | Không chịu trách nhiệm |
| --- | --- | --- |
| `@Testcontainers` | Bật JUnit 5 Testcontainers extension | Tự cấu hình Spring `Environment` |
| `@Container` | Xác định container để extension start/stop | Tự bind `spring.datasource.url` |
| `PostgreSQLContainer` | Quản lý DB container và API đọc URL/credentials | Tự bảo đảm app dùng đúng DB |
| `@DynamicPropertySource` | Cho Spring TestContext biết method đăng ký properties | Start container hoặc tạo SQL schema |
| `DynamicPropertyRegistry` | Đăng ký key/value suppliers vào Environment | Tạo Bean DataSource nếu thiếu auto-configuration |
| `DataSourceAutoConfiguration` | Xây DataSource dựa trên config/conditions | Kiểm DB schema đúng nghiệp vụ |
| `@ServiceConnection` | Cung cấp typed connection details khi dùng Boot integration | Cần thiết khi đã chọn dynamic properties thuần |

`@DynamicPropertySource` có thể dùng với PostgreSQL, Redis, Kafka, WireMock hoặc một service trên host; **không phụ thuộc duy nhất vào Testcontainers**. Nó cần khi endpoint/port được tạo hoặc biết ở runtime.

## 4. Vì sao phải dùng `Supplier`?

Method `DynamicPropertyRegistry.add` nhận một `Supplier` trả giá trị, ví dụ:

~~~java
registry.add("spring.datasource.url", postgres::getJdbcUrl);
~~~

Phép đăng ký này không cần đọc JDBC URL ngay khi Java gọi `registerProperties`. Spring gọi supplier khi property được resolve.

Tương đương về ý tưởng:

~~~java
registry.add("spring.datasource.url",
        () -> postgres.getJdbcUrl());
~~~

Dễ mắc lỗi:

~~~java
// KHÔNG COMPILE: đối số thứ hai cần Supplier,
// nhưng getter trả về String.
registry.add("spring.datasource.url",
        postgres.getJdbcUrl());
~~~

Ngoài lỗi kiểu dữ liệu, đọc port **trước khi container start** còn có thể gây exception kiểu `Mapped port can only be obtained after the container is started`. Với `@Testcontainers` và một static `@Container` ở cùng test class, JUnit extension quản lý startup trước khi test context cần kết nối, theo pattern được Spring/Testcontainers hỗ trợ.

### Supplier lười đọc không có nghĩa connection được hot-reload

Đăng ký một supplier là cơ chế **đọc property động**, nhưng `DataSource` được auto-configure trong quá trình khởi tạo ApplicationContext. Khi bean Hikari được tạo với URL X, nếu container sau đó đổi mapped port sang Y, **bean Hikari không tự thay URL và reconnect** chỉ vì supplier có thể trả Y.

Vì vậy:

- Container cần sẵn sàng trước thời điểm Spring tạo các bean phụ thuộc kết nối.
- Không restart container giữa các test methods mà vẫn tái sử dụng một ApplicationContext cũ.
- Nếu property values thực sự thay đổi theo test class, cần context mới hoặc container lifecycle ổn định theo phạm vi context.
- Không dùng `registry.add(..., () -> randomPort())` để sinh port khác nhau mỗi lần Spring đọc property; supplier nên phản ánh endpoint **đang hoạt động và ổn định**.

## 5. Thứ tự chạy khi dùng JUnit và Spring

Một lifecycle đơn giản cho static container trong test class:

~~~text
JUnit Jupiter + Testcontainers extension
       |
       v
Start static @Container PostgreSQL
       |
       v
Spring TestContext chuẩn bị ApplicationContext
       |
       v
Gọi static @DynamicPropertySource method
       |
       v
Thêm Suppliers vào Environment
       |
       v
Spring Boot tạo DataSource/Hikari,
JPA EntityManagerFactory/repositories/services
       |
       v
@BeforeEach -> @Test -> @AfterEach
       |
       v
Đóng hoặc tái sử dụng Spring context theo cache policy
       |
       v
Testcontainers dừng static container cuối test class
~~~

Sơ đồ là **mô hình quan hệ khái quát**, không phải thứ tự tuyệt đối của mọi JUnit extension callback nội bộ. Phần quan trọng là các URL/credentials từ container có sẵn khi DataSource thực sự được tạo.

`@Container` chỉ có hiệu lực như lifecycle annotation khi dùng đúng Testcontainers JUnit Jupiter integration (ví dụ class gắn `@Testcontainers`), hoặc nếu bạn chủ động quản lý startup bằng cách khác.

### Static khác instance container

~~~java
@Testcontainers
class ExampleTest {
    @Container
    static PostgreSQLContainer<?> postgres = ...;
}
~~~

Static `@Container` thường dùng **một lần cho test class**. Nếu khai báo container instance field, Testcontainers extension quản lý theo từng test method; điều đó dễ **không phù hợp** với `@DynamicPropertySource` static và một cached Spring context cần một URL ổn định.

Khi mong mỗi method dùng DB mới, cần thiết kế context/resource isolation rõ ràng; chỉ đổi `static` thành instance field không giải quyết tự động vấn đề Spring context caching.

## 6. So sánh với cấu hình test tĩnh

| Cách | Dữ liệu kết nối đến từ đâu | Phù hợp |
| --- | --- | --- |
| `application-test.properties` | File profile test | URL/port cố định, không thay theo runtime |
| `@TestPropertySource(properties=...)` | Static inline properties/resources | Override test-specific values đã biết trước |
| `@SpringBootTest(properties=...)` | Inline properties trên test annotation | Config tĩnh cho context |
| `@DynamicPropertySource` | `Supplier` chạy khi property được resolve | Testcontainers mapped ports, mock service URLs |
| `@ServiceConnection` | Typed `ConnectionDetails` từ container, Boot integration | DB/services được Boot hỗ trợ nhận diện |
| `System.setProperty(...)` | JVM-global mutable state | Thường nên tránh vì rò giữa test classes/parallel jobs |
| `@ActiveProfiles("test")` | Bật một tập nguồn cấu hình profile | Phân nhóm config, không tự tạo URL động |

### Độ ưu tiên của dynamic properties

Theo Spring TestContext, properties đăng ký qua `@DynamicPropertySource` có **precedence cao hơn** nhiều property sources thông dụng, gồm `@TestPropertySource`, biến môi trường hệ điều hành, Java system properties và `@PropertySource`.

Ví dụ minh họa:

~~~java
@TestPropertySource(properties = {
    "spring.datasource.url=jdbc:postgresql://localhost:1/unused"
})
@SpringBootTest
class ExampleOverrideTest {

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url",
                postgres::getJdbcUrl);
    }
}
~~~

Snippet này **không phải class runnable**: thiếu khai báo container/imports và cấu hình Boot. Nó minh họa precedence. **Không trỏ giá trị “fallback” tới production URL** vì một lỗi setup hoặc thay đổi behavior có thể làm test kết nối nhầm DB thật.

### Property precedence khác ConnectionDetails precedence

Trong Spring Boot, typed `ConnectionDetails` do `@ServiceConnection` cung cấp có thể được Boot auto-configuration ưu tiên hơn connection-related properties. Nếu bạn dùng **đồng thời `@ServiceConnection` và `@DynamicPropertySource` cho cùng PostgreSQL**, việc nhìn vào Environment chưa chắc phản ánh đường kết nối thực tế do DataSource chọn. Thực hành an toàn:

1. **Chọn một cách cấu hình chính** cho cùng connection.
2. Khi dùng manual dynamic properties, không cần thêm `@ServiceConnection` trên cùng container.
3. Assert `DataSource.getConnection().getMetaData()` thay vì chỉ đọc Environment.
4. Nếu buộc kết hợp (nhiều libraries/services), ghi rõ từng property/typed details và thứ tự ưu tiên.

## 7. Ví dụ chạy được: Java 17 + Spring Boot 3.3.5 + PostgreSQL

Project mẫu có:

- Một Spring Boot app dùng Spring Data JPA.
- Entity `CustomerAccount`.
- Repository `CustomerAccountRepository`.
- Service `AccountRegistrationService` có transaction.
- Một `@SpringBootTest` dùng PostgreSQL container và dynamic properties.
- Một `@DataJpaTest` riêng dùng PostgreSQL container, **`Replace.NONE`** và rollback test.
- Tổng cộng **4 method `@Test`**, chia đều cho hai lớp.
- Test xác minh DB engine PostgreSQL và một thao tác ghi/đọc dữ liệu thật.

Không có H2 trong dependency tree của lab. Container Postgres chạy trên Docker/compatible container runtime của máy/CI. Với một môi trường không có Docker, các integration tests **không thể kỳ vọng pass**; không đổi sang H2 chỉ để giữ test xanh nếu yêu cầu đang kiểm là PostgreSQL.

### 7.1. Cây thư mục

~~~text
dynamic-property-postgres/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/dynamicproperties/
    │   ├── DemoApplication.java
    │   ├── CustomerAccount.java
    │   ├── CustomerAccountRepository.java
    │   └── AccountRegistrationService.java
    └── test/java/com/example/dynamicproperties/
        ├── CustomerFullContextTest.java
        └── CustomerJpaSliceTest.java
~~~

Gradle Wrapper scripts và `gradle-wrapper.jar` cần được tạo bằng Gradle tương thích hoặc lấy từ repo. Đoạn Markdown không chứa tệp nhị phân Wrapper JAR.

### 7.2. `settings.gradle`

~~~groovy
rootProject.name = 'dynamic-property-postgres'
~~~

### 7.3. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'

    testRuntimeOnly 'org.postgresql:postgresql'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

**Giải thích:**

- `spring-boot-starter-data-jpa` cung cấp Spring Data JPA, Hibernate, transaction manager và JDBC/Hikari infrastructure.
- `spring-boot-starter-test` cung cấp JUnit Jupiter, Spring TestContext, assertions và Spring Boot testing annotations.
- `org.testcontainers:junit-jupiter` cho `@Testcontainers` và `@Container`.
- `org.testcontainers:postgresql` cho `PostgreSQLContainer`.
- `org.postgresql:postgresql` là PostgreSQL JDBC driver **ở test runtime**; production deployment phải có driver/DB dependency riêng theo kiến trúc của app.
- `junit-platform-launcher` và `useJUnitPlatform()` cho phép Gradle chạy JUnit Jupiter.
- **Không bắt buộc thêm `spring-boot-testcontainers`** chỉ để dùng `@DynamicPropertySource`. Module đó dành cho các tích hợp Boot như `@ServiceConnection`; ví dụ này dùng Testcontainers + Spring TestContext.
- **Không cần H2**, và không dùng in-memory replacement; mục tiêu là chứng minh PostgreSQL container thật.

Spring Boot BOM quản lý những version thư viện test tương thích. Nếu project đã dùng Gradle platform hoặc BOM riêng, kiểm dependency tree thay vì ghim tùy tiện Testcontainers major version.

### 7.4. Application root

**`src/main/java/com/example/dynamicproperties/DemoApplication.java`**

~~~java
package com.example.dynamicproperties;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

File này là root auto-configuration và component scan. Các lớp entity/repository/service cùng package nên Boot/JPA tìm được. Lab **không** có application properties trỏ production DB; các test cấp connection details động.

### 7.5. Entity

**`src/main/java/com/example/dynamicproperties/CustomerAccount.java`**

~~~java
package com.example.dynamicproperties;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_accounts")
public class CustomerAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "email", nullable = false,
            unique = true, length = 150)
    private String email;

    @Column(name = "display_name", nullable = false,
            length = 100)
    private String displayName;

    protected CustomerAccount() {
        // JPA requirement
    }

    public CustomerAccount(String email, String displayName) {
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

`GenerationType.IDENTITY` yêu cầu database sinh ID, nên tests không hardcode ID. Column `email` unique, nullable=false; `display_name` có tên cột tường minh. Hibernate tạo schema trong test theo `ddl-auto=create-drop` **chỉ để giữ lab chạy độc lập**. Trong dự án production có Flyway/Liquibase, hãy dùng migrations thật và `ddl-auto=validate/none` thay vì tạo lại schema.

### 7.6. Repository

**`src/main/java/com/example/dynamicproperties/CustomerAccountRepository.java`**

~~~java
package com.example.dynamicproperties;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerAccountRepository
        extends JpaRepository<CustomerAccount, Long> {

    Optional<CustomerAccount> findByEmail(String email);

    long countByEmail(String email);
}
~~~

Đây là Spring Data JPA repository: các method được suy từ tên Java property `email`. Các tests sẽ gọi repository thật trên PostgreSQL, không dùng mock DB hoặc repository fake.

### 7.7. Transactional service

**`src/main/java/com/example/dynamicproperties/AccountRegistrationService.java`**

~~~java
package com.example.dynamicproperties;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountRegistrationService {

    private final CustomerAccountRepository repository;

    public AccountRegistrationService(
            CustomerAccountRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Long register(String email, String displayName) {
        CustomerAccount saved = repository.save(
                new CustomerAccount(email, displayName));
        return saved.getId();
    }
}
~~~

Đây là service thật để full-context test kiểm được **application wiring và transaction**. Method `register` dùng `@Transactional` và repository save; với IDENTITY mapping, Hibernate cần INSERT để cấp ID. Test full context không `@Transactional`, nên service transaction có thể commit trước khi test gọi read ở repository.

**Tại sao không mock service/repository?** Vì bài muốn xác minh connection động từ Testcontainers, nếu mock DataSource hoặc repository thì dù URL sai, test cũng có thể xanh. Unit test thích hợp với business logic thuần, nhưng không thay được integration test có DB thật.

## 8. `@SpringBootTest`: cung cấp URL, user và password từ PostgreSQLContainer

**`src/test/java/com/example/dynamicproperties/CustomerFullContextTest.java`**

~~~java
package com.example.dynamicproperties;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.UUID;

import javax.sql.DataSource;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@SpringBootTest(
    classes = DemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "spring.jpa.hibernate.ddl-auto=create-drop",
        "spring.sql.init.mode=never"
    })
class CustomerFullContextTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("accounts_full_test")
                    .withUsername("test_user")
                    .withPassword("test_password");

    @DynamicPropertySource
    static void datasourceProperties(
            DynamicPropertyRegistry registry) {

        registry.add("spring.datasource.url",
                postgres::getJdbcUrl);
        registry.add("spring.datasource.username",
                postgres::getUsername);
        registry.add("spring.datasource.password",
                postgres::getPassword);
    }

    @Autowired
    private DataSource dataSource;

    @Autowired
    private Environment environment;

    @Autowired
    private CustomerAccountRepository repository;

    @Autowired
    private AccountRegistrationService service;

    private String createdEmail;

    @AfterEach
    void cleanupOnlyRowsCreatedByThisTest() {
        if (createdEmail != null) {
            repository.findByEmail(createdEmail)
                    .ifPresent(repository::delete);
        }
    }

    @Test
    void datasourceReallyUsesPostgresContainer()
            throws SQLException {

        assertTrue(postgres.isRunning());

        try (Connection connection = dataSource.getConnection()) {
            assertEquals(
                    "PostgreSQL",
                    connection.getMetaData().getDatabaseProductName());

            assertTrue(connection.getMetaData().getURL()
                    .startsWith("jdbc:postgresql:"));

            assertEquals(
                    "accounts_full_test",
                    connection.getCatalog());
        }

        assertEquals(
                postgres.getJdbcUrl(),
                environment.getProperty("spring.datasource.url"));
    }

    @Test
    void fullContextServiceWritesAndReadsFromPostgres() {
        createdEmail = "full-" + UUID.randomUUID()
                + "@example.test";

        Long id = service.register(
                createdEmail, "Full Context");

        assertNotNull(id);

        CustomerAccount found =
                repository.findByEmail(createdEmail)
                        .orElseThrow();

        assertEquals(id, found.getId());
        assertEquals("Full Context", found.getDisplayName());
        assertEquals(1L,
                repository.countByEmail(createdEmail));
    }
}
~~~

### Phân tích test full context

**`@Container static PostgreSQLContainer`**

- Testcontainers JUnit Jupiter extension start container một lần theo class lifecycle.
- Mapped port được cấp khi container khởi động; không cố định 5432 ở host.
- `getJdbcUrl`/`getUsername`/`getPassword` cung cấp connection details thật.
- Database name `accounts_full_test` chỉ dùng trong container test. Username/password ở đây là credentials mẫu, **không phải production credentials**.

**`@DynamicPropertySource`**

- Được Spring TestContext dùng để đăng ký cấu hình vào Environment.
- Cung cấp đúng ba properties cho Spring Boot DataSource auto-configuration.
- Truyền getter dưới dạng method reference `Supplier`.
- Không cần `@ActiveProfiles("test")` chỉ để đăng ký port động.

**`@SpringBootTest(webEnvironment = NONE)`**

- Nạp full application bean graph mà không chạy HTTP server.
- Có `AccountRegistrationService` thật và Spring Data JPA repository thật.
- Không mặc định thay PostgreSQL DataSource bằng H2 theo cơ chế test slice.
- Chạy Hibernate DDL để tạo bảng trong **PostgreSQL container test**; không phải database production.

**Test metadata**

- `postgres.isRunning()` chỉ xác nhận container đang chạy.
- `getDatabaseProductName() == "PostgreSQL"` chứng minh JDBC connection lấy từ DataSource đi đến PostgreSQL.
- `getURL().startsWith("jdbc:postgresql:")` kiểm driver/URL phù hợp engine.
- `connection.getCatalog()` kiểm database name trong lab, giúp bắt đường nối sai.
- Đọc `environment.getProperty(...)` bổ sung thông tin về registration, nhưng **không dùng riêng giá trị này** làm bằng chứng kết nối.

**Test service**

- Ghi một account qua service thật, đọc bằng repository thật, xác nhận ID và display name.
- Dùng email UUID để mỗi lần chạy có fixture riêng.
- `@AfterEach` dọn **chỉ row được tạo trong method hiện tại**; không dùng `deleteAll()` toàn bảng.
- Vì full-context test không có test-managed transaction theo mặc định, insert có thể đã commit. Cleanup dùng repository delete trong một transaction thích hợp.
- Dù cleanup bình thường chạy, khi JVM bị kill trước teardown, container test cũng được dừng/hủy bởi hạ tầng; không đem cùng schema này dùng cho production.

## 9. `@DataJpaTest`: giữ PostgreSQL thay vì H2

Spring Boot 3.3 có test database auto-configuration cho `@DataJpaTest`. Theo policy mặc định của Boot 3.3, một DataSource có thể bị **thay bằng embedded DB** nếu embedded driver có sẵn. Đây là bẫy rất thường gặp:

~~~text
@DynamicPropertySource đăng ký đúng:
  spring.datasource.url = jdbc:postgresql://localhost:<port>/...
          |
          v
@AutoConfigureTestDatabase mặc định ở Boot 3.3:
  có thể REPLACE DataSource bằng H2
          |
          v
Environment có Postgres URL
nhưng repository đang thực sự chạy với H2
~~~

Muốn bảo đảm **đúng PostgreSQL container** trong JPA slice:

~~~java
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE)
~~~

Nó **không tạo URL**; nó chỉ yêu cầu test auto-configuration **không thay DataSource** mà dynamic properties đã giúp cấu hình. Vẫn cần PostgreSQL driver, container và Spring Data JPA.

### Class test JPA slice đầy đủ

**`src/test/java/com/example/dynamicproperties/CustomerJpaSliceTest.java`**

~~~java
package com.example.dynamicproperties;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.UUID;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@DataJpaTest(
    showSql = false,
    properties = {
        "spring.jpa.hibernate.ddl-auto=create-drop",
        "spring.sql.init.mode=never"
    })
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE)
class CustomerJpaSliceTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("accounts_slice_test")
                    .withUsername("test_user")
                    .withPassword("test_password");

    @DynamicPropertySource
    static void registerDatabase(
            DynamicPropertyRegistry registry) {

        registry.add("spring.datasource.url",
                postgres::getJdbcUrl);
        registry.add("spring.datasource.username",
                postgres::getUsername);
        registry.add("spring.datasource.password",
                postgres::getPassword);
    }

    @Autowired
    private DataSource dataSource;

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private CustomerAccountRepository repository;

    @Test
    void sliceHasNotReplacedPostgresWithH2()
            throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            assertEquals(
                    "PostgreSQL",
                    connection.getMetaData().getDatabaseProductName());

            assertTrue(connection.getMetaData().getURL()
                    .startsWith("jdbc:postgresql:"));

            assertEquals(
                    "accounts_slice_test",
                    connection.getCatalog());
        }
    }

    @Test
    void repositoryRoundTripUsesPostgresSchema() {
        String email = "slice-" + UUID.randomUUID()
                + "@example.test";

        CustomerAccount original = new CustomerAccount(
                email, "JPA Slice");

        entityManager.persistAndFlush(original);
        entityManager.clear();

        CustomerAccount fetched =
                repository.findByEmail(email).orElseThrow();

        assertNotNull(fetched.getId());
        assertEquals(email, fetched.getEmail());
        assertEquals("JPA Slice", fetched.getDisplayName());
        assertEquals(1L, repository.countByEmail(email));
    }
}
~~~

### Vì sao không cần cleanup thủ công trong slice?

`@DataJpaTest` thường khởi tạo một **test-managed transaction** và rollback cuối mỗi JUnit method. `entityManager.persistAndFlush` gửi INSERT đến database trong transaction test, nhưng **flush không commit**. Khi test kết thúc, row vừa insert sẽ rollback.

Do đó:

- Không cần `@AfterEach repository.deleteAll()` ở ví dụ slice.
- `persistAndFlush` cùng `clear` giúp không chỉ assert một Java object đang managed.
- Test query vẫn chạy trên PostgreSQL thật, nhưng trong transaction test.
- Đây **không phải bằng chứng** một transaction của HTTP server đã commit hoặc một app runtime khác nhìn thấy row sau test.
- Nếu service dùng `REQUIRES_NEW` hoặc thao tác ngoài transaction test, rollback có thể không dọn tất cả side effects; cần xử lý theo thực tế.

### Bẫy kiểm engine

Đừng chỉ:

~~~java
assertEquals(
    postgres.getJdbcUrl(),
    environment.getProperty("spring.datasource.url"));
~~~

Đoạn này chỉ kiểm Environment phản ánh dynamic source. Nếu JPA slice đã thay DataSource bằng H2, **Environment vẫn có thể cho giá trị PostgreSQL** và assertion vẫn xanh. Test ở trên mở connection thực rồi kiểm metadata. Đây là cơ chế bảo vệ chính trước **false confidence**.

### Boot 3.3 và Boot 3.4 có khác nhau

| Phiên bản | Behavior liên quan |
| --- | --- |
| Spring Boot 3.3.x | Default replacement cho JPA/JDBC slice thường là `Replace.ANY` |
| Spring Boot 3.4+ | Có `Replace.NON_TEST` để nhận diện và giữ một số datasource test hợp lệ |
| Cả hai | `Replace.NONE` có thể dùng khi muốn **không thay** DataSource cụ thể |
| Cả hai | Phải kiểm connection thực; annotation không chứng minh engine an toàn |

Với Boot 3.3, **đừng viết `Replace.NON_TEST`** vì enum chưa có ở version đó. Mặt khác, `Replace.NONE` cũng không có nghĩa URL an toàn; nếu dynamic supplier trỏ DB production, test vẫn nguy hiểm. Luôn dùng test-specific container và giới hạn quyền.

## 10. Chạy Gradle và quan sát kết quả

Để chạy **4 method `@Test`** đã định nghĩa, cần:

- JDK 17 (hoặc toolchain provisioning được Gradle cấu hình).
- Gradle Wrapper tương thích với project.
- Docker/container runtime mà Testcontainers có thể sử dụng.
- Quyền chạy image PostgreSQL 16 Alpine và tải Maven dependencies.
- Không cần một PostgreSQL server cài sẵn ở port 5432.
- Không cần H2.

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Chạy một nhóm:

~~~bash
./gradlew test --tests 'com.example.dynamicproperties.CustomerFullContextTest'
./gradlew test --tests 'com.example.dynamicproperties.CustomerJpaSliceTest'
~~~

Trên Windows, thay `./gradlew` bằng `.\gradlew.bat` trong các câu lệnh tương ứng.

Với code và môi trường tương thích, **kỳ vọng 4 tests pass**:

| Class | Test | Kiểm |
| --- | --- | --- |
| `CustomerFullContextTest` | `datasourceReallyUsesPostgresContainer` | DB engine, URL, catalog, registry |
| `CustomerFullContextTest` | `fullContextServiceWritesAndReadsFromPostgres` | Service transaction + repository thật |
| `CustomerJpaSliceTest` | `sliceHasNotReplacedPostgresWithH2` | DB engine thật, không bị embedded replacement |
| `CustomerJpaSliceTest` | `repositoryRoundTripUsesPostgresSchema` | JPA flush/clear/query và test rollback |

Đây là **kết quả dự kiến từ source**, không phải bản ghi đã thực thi Docker/Gradle ở môi trường người học. Port container, thời gian khởi động, PostgreSQL logs và Gradle task logs có thể thay đổi; **không có stdout nghiệp vụ cố định** trong code test.

Báo cáo JUnit thường ở:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.dynamicproperties.CustomerFullContextTest.xml
    └── TEST-com.example.dynamicproperties.CustomerJpaSliceTest.xml
~~~

Khi Gradle báo `UP-TO-DATE` hoặc `FROM-CACHE`, đó không nhất thiết là test mới được thực thi. Khi điều tra lỗi môi trường hoặc dynamic port:

~~~bash
./gradlew test --rerun-tasks
~~~

Nếu project chưa có Wrapper, một bản Gradle đã cài tương thích có thể tạo:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Sau đó lưu Wrapper scripts/JAR theo quy định. Đừng đổi version Gradle/Boot của project thật mà không kiểm tương thích dependency tree.

### Docker trong CI

Nếu Docker daemon chưa chạy, Testcontainers có thể báo không tìm thấy Docker environment. Đó là **lỗi hạ tầng**, không phải lý do để xóa assertions hoặc giả lập kết quả “PASS”. Hãy kiểm Docker socket/permissions, Testcontainers compatibility và image pull/network. Không cần mount Docker socket vào ứng dụng production; chỉ runner dành cho integration tests cần quyền container phù hợp.

## 11. Khi nào nên dùng `@ServiceConnection` thay vì `@DynamicPropertySource`?

Spring Boot 3.1+ có tích hợp Testcontainers qua **`@ServiceConnection`**, trong module `spring-boot-testcontainers`. Với loại container/service được Boot nhận diện, annotation này có thể cung cấp **`ConnectionDetails`** tự động mà không cần tự đăng ký ba properties JDBC.

Ví dụ **minh họa**, không có trong project runnable ở trên:

~~~groovy
testImplementation 'org.springframework.boot:spring-boot-testcontainers'
~~~

~~~java
@Testcontainers
@SpringBootTest
class ServiceConnectionExample {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // @Autowired repository/dataSource and @Test methods...
}
~~~

Cần imports, app configuration và test method thực để chạy. Spring Boot có thể tự tạo `JdbcConnectionDetails` dựa trên `PostgreSQLContainer`.

**So sánh:**

| Tiêu chí | `@DynamicPropertySource` | `@ServiceConnection` |
| --- | --- | --- |
| Đối tượng cung cấp | Spring Environment properties | Typed `ConnectionDetails` của Spring Boot |
| Cách khai báo | Static registry method, Supplier | Annotation trên container field/bean hỗ trợ |
| Linh hoạt với custom prefix | Rất cao | Phụ thuộc type connection details được hỗ trợ |
| Cần `spring-boot-testcontainers` | Không bắt buộc | Có |
| Bật trên framework không phải Boot | Có thể, qua Spring TestContext | Là tiện ích riêng của Spring Boot |
| Khi nhiều services tự định nghĩa props | Thích hợp | Có thể cần kết hợp manual registration |
| Nguy cơ xung đột nếu dùng cả hai | Có, do hai đường cấp config | Có, connection details có thể ưu tiên property |
| Kiểm actual DB | Vẫn cần metadata/SQL test | Vẫn cần metadata/SQL test |

### Khuyến nghị lựa chọn

- Nếu test chỉ kết nối PostgreSQL/Redis/MongoDB mà Boot đã hỗ trợ nhận diện tốt, **`@ServiceConnection`** thường ngắn và ít boilerplate.
- Nếu test cần truyền **custom key**, chẳng hạn `external.inventory.base-url`, một token/host/port tạo bởi local process, hoặc engine/library không có typed details tương ứng, **`@DynamicPropertySource`** linh hoạt hơn.
- Nếu dự án không dùng `spring-boot-testcontainers` hoặc muốn giữ mô hình Spring TestContext độc lập, dynamic properties vẫn là lựa chọn phổ biến.
- Tránh gắn đồng thời `@ServiceConnection` và `@DynamicPropertySource` cho cùng datasource nếu không có lý do được giải thích và kiểm chứng.

**Chủ đề bài này cố ý tập trung vào `@DynamicPropertySource`** để người học hiểu chính xác cách tự cấp connection properties, kể cả khi sử dụng Spring Boot phiên bản có service connections.

## 12. Mở rộng cho Redis, Kafka và HTTP mock server

`@DynamicPropertySource` không chỉ dùng cho `spring.datasource.*`. Bất kỳ Spring property nào nhận host/port/URL động cũng có thể được đăng ký.

### Redis qua GenericContainer

~~~java
@Testcontainers
class RedisIntegrationTest {

    @Container
    static GenericContainer<?> redis =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisSettings(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add("spring.data.redis.port",
                () -> redis.getMappedPort(6379));
    }
}
~~~

**Snippet minh họa**, cần Spring context, imports và test method. Không nhầm `redis.getMappedPort(6379)` với port `6379` trên host: mapped port cần lấy **sau khi container start**. Đối với một app dùng Spring Data Redis ở Boot 3.3, prefix cấu hình phổ biến là `spring.data.redis.*`. Khi library riêng dùng prefix khác, đăng ký đúng key mà library đó bind.

### HTTP mock server

Giả sử một mock server có method `getBaseUrl()`, ví dụ:

~~~java
@DynamicPropertySource
static void serviceEndpoint(DynamicPropertyRegistry registry) {
    registry.add("external.payment.base-url",
            paymentMockServer::getBaseUrl);
}
~~~

**Snippet minh họa**: cần khai báo/khởi động `paymentMockServer` phù hợp và đảm bảo app dùng `external.payment.base-url`. Đăng ký một key không được bean nào đọc **không có tác dụng**. Muốn chứng minh hệ thống dùng mock server, hãy gửi request từ client thật trong test và assert mock server đã nhận request tương ứng.

### Kafka bootstrap servers

Nếu có `KafkaContainer kafka` phù hợp trong test:

~~~java
registry.add("spring.kafka.bootstrap-servers",
        kafka::getBootstrapServers);
~~~

Đây là snippet cho một method `@DynamicPropertySource` có sẵn `registry`/`kafka`. Spring Kafka có thể đọc danh sách bootstrap server từ property đó. Khi dùng nhiều Kafka brokers/security protocol, cần cấp đầy đủ cấu hình, không chỉ một chuỗi URI.

### Nhiều services trong cùng registry

~~~java
@DynamicPropertySource
static void dynamicServices(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url",
            postgres::getJdbcUrl);
    registry.add("spring.datasource.username",
            postgres::getUsername);
    registry.add("spring.datasource.password",
            postgres::getPassword);
    registry.add("spring.data.redis.host",
            redis::getHost);
    registry.add("spring.data.redis.port",
            () -> redis.getMappedPort(6379));
}
~~~

Đây là snippet cần cả hai containers có lifecycle phù hợp. Các suppliers có thể dùng các instance khác nhau. Không cần tạo một `@DynamicPropertySource` method riêng cho từng property nếu cùng nhóm config và cùng phạm vi test.

**Cảnh báo:** App có thể khởi động bean dùng cả PostgreSQL và Redis; một container chưa start khi supplier được resolve sẽ gây context failure. Bảo đảm tất cả services cần thiết được JUnit/Boot/Testcontainers quản lý nhất quán.

## 13. Context caching: bẫy container dừng nhưng context còn sống

Spring TestContext cache `ApplicationContext` dựa trên nhiều yếu tố cấu hình test. Cache giúp suite chạy nhanh, nhưng tạo một tình huống cần đặc biệt chú ý:

1. Test class A dùng một static container Postgres.
2. Spring tạo ApplicationContext và Hikari DataSource kết nối container A.
3. Class A kết thúc, Testcontainers extension dừng container A.
4. Class B có cấu hình Spring tương đương và context được tái sử dụng từ cache.
5. DataSource vẫn giữ endpoint/container A **đã dừng**.
6. Class B nhận lỗi `Connection refused`, `connection is closed` hoặc timeout ngẫu nhiên.

**Một method `@DynamicPropertySource` được khai báo không làm Hikari pool tự thay endpoint khi context cache vẫn giữ bean cũ.** Đây là lý do cần đồng bộ **container lifetime** và **ApplicationContext lifetime**.

### Cách giảm rủi ro

- Trong ví dụ runnable, hai classes dùng **Spring test configurations khác nhau** (`@SpringBootTest` và `@DataJpaTest`), container riêng và database riêng. Không cố tái sử dụng một DB container đã dừng giữa các contexts.
- Khi dùng chung base test class với static container, cân nhắc một singleton container sống trong toàn bộ khoảng thời gian cache context được dùng.
- Nếu các subclass nhận **dynamic property values khác nhau**, Spring docs gợi ý `@DirtiesContext` trên base class khi cần context mới.
- `@DirtiesContext` **evict context**, không xóa dữ liệu DB đã commit; đừng dùng nó thay cleanup.
- Khi cần scale integration tests, nhóm tests theo context/container configuration ổn định để giảm startup cost nhưng không rò state.

### Ví dụ cấu trúc gợi ý

~~~java
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_CLASS)
abstract class IsolatedPostgresTestBase {
    // Static container/dynamic properties cho mỗi subclass.
    // Mỗi subclass cần context mới nếu endpoints khác nhau.
}
~~~

Đây là snippet cấu trúc, không phải class chạy độc lập. Tùy inheritance và cách JUnit/Testcontainers quản lý static field, cần xác định container có bị share ngoài ý muốn không. Không thêm `@DirtiesContext` cho mọi test khi cùng một container/context có thể được tái sử dụng an toàn; nó làm suite chậm và tạo nhiều kết nối hơn.

### Không dùng instance container với một cached context vô thức

~~~java
@Container
PostgreSQLContainer<?> postgres = ...;
~~~

Nếu container là instance field, JUnit extension có thể start/stop mỗi method. Nhưng `@DynamicPropertySource` là static, và Spring context có thể giữ DataSource lâu hơn method; mapped port/endpoint của container mới không tự đi vào Hikari đã tạo. Khi mục tiêu là **mỗi test method có một database thật**, hãy chọn cách cô lập DB schema/transaction/container lifecycle có chủ đích thay vì thay một keyword.

## 14. Kiểm thử song song và isolation dữ liệu

Khi chạy nhiều JUnit methods/classes song song, tránh các mẫu:

- Tất cả methods dùng một email/ID cố định và cùng ghi/DELETE.
- Một `@AfterEach repository.deleteAll()` xóa dữ liệu của method khác.
- Static mutable properties/state mà nhiều classes ghi đè.
- Restart một shared container trong khi context khác vẫn dùng pool.
- Giả định transaction test bao trùm mọi request HTTP/server thread.
- Dùng database name cố định trên một DB server chia sẻ ngoài Testcontainers.

Các giải pháp:

1. Dùng **test-specific keys** như UUID và cleanup theo chính keys ấy.
2. Dùng `@DataJpaTest` rollback khi test chỉ gọi repository trong cùng test-managed transaction.
3. Dùng schema/database riêng hoặc container riêng khi các operations không thể rollback.
4. Nếu dùng container chung toàn suite, xác định rõ ownership và không cleanup toàn bảng.
5. Với parallel writes, đảm bảo isolation và lock behavior; nếu cần transaction semantics của PostgreSQL thì test đúng engine.
6. Khi test HTTP real server, cleanup committed data bằng transaction thực sự commit.

**Full-context test của demo** dùng UUID email và targeted deletion. **JPA slice test** dùng UUID và rollback mặc định. Hai cách khác nhau vì transaction boundary khác nhau, không phải vì cùng dùng một annotation `@DynamicPropertySource` thì transaction behavior giống nhau.

## 15. Vì sao không lấy URL động bằng `System.setProperty`?

Một mẫu cũ:

~~~java
@BeforeAll
static void configure() {
    System.setProperty(
            "spring.datasource.url",
            postgres.getJdbcUrl());
}
~~~

Bên cạnh việc phải bảo đảm container start đúng thứ tự, `System.setProperty` thay đổi **JVM-global state**; nó có thể ảnh hưởng những tests khác trong cùng JVM, nhất là khi chạy song song hoặc dùng Spring context cache.

`@DynamicPropertySource` giúp gắn property sources với **Spring test ApplicationContext configuration**, không cần mutate global JVM property. Đây là một lợi ích lớn cho test isolation.

Khi một external library không dùng Spring Environment mà chỉ đọc Java system properties, `@DynamicPropertySource` có thể **không đủ**; bạn phải dùng cơ chế config của library đó nhưng cần quản lý scope/cleanup cẩn thận. Không kỳ vọng mọi library bên ngoài đều tự đọc `spring.datasource.url` hoặc bất cứ key Spring nào.

## 16. `@DynamicPropertySource` không thay thế `@ActiveProfiles`

Một hệ thống có thể dùng đồng thời:

~~~java
@ActiveProfiles("test")
@SpringBootTest
@Testcontainers
class PostgresWithProfileTest {

    @Container
    static PostgreSQLContainer<?> postgres = ...;

    @DynamicPropertySource
    static void database(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url",
                postgres::getJdbcUrl);
        registry.add("spring.datasource.username",
                postgres::getUsername);
        registry.add("spring.datasource.password",
                postgres::getPassword);
    }
}
~~~

Đây là snippet không độc lập. `@ActiveProfiles("test")` chọn một profile, còn dynamic registry cung cấp URL/credentials chính xác ở runtime.

Ví dụ `application-test.yml` có thể đặt:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
  flyway:
    enabled: true
logging:
  level:
    org.hibernate.SQL: DEBUG
~~~

Đây là **cấu hình mở rộng**, không phải file có sẵn trong runnable project; khi dùng `ddl-auto: validate`, schema phải được Flyway/migration tạo trước. Không chạy đoạn này độc lập vì sẽ thiếu migration. Phân chia trách nhiệm:

- Profile: chọn mức logging, schema strategy, feature flags và các defaults test.
- DynamicPropertySource: giá trị URL/host/port không biết trước.
- Migration tool: chuẩn bị schema tương thích.
- Assertions: chứng minh DataSource và business behavior dùng đúng resource.

Không ghi mật khẩu thật vào `application-test.yml` chỉ vì có profile `test`. Dùng credentials test của container hoặc CI secrets theo chính sách.

## 17. Khi cần custom configuration prefix hoặc hơn một DataSource

Một số ứng dụng không dùng property mặc định `spring.datasource.*` cho mọi kết nối. Ví dụ:

~~~properties
app.datasource.orders.url=...
app.datasource.audit.url=...
~~~

Nếu app tự tạo hai DataSource từ các prefix này, registry có thể đăng ký:

~~~java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("app.datasource.orders.url",
            ordersPostgres::getJdbcUrl);
    registry.add("app.datasource.orders.username",
            ordersPostgres::getUsername);
    registry.add("app.datasource.orders.password",
            ordersPostgres::getPassword);

    registry.add("app.datasource.audit.url",
            auditPostgres::getJdbcUrl);
    registry.add("app.datasource.audit.username",
            auditPostgres::getUsername);
    registry.add("app.datasource.audit.password",
            auditPostgres::getPassword);
}
~~~

Đây là snippet minh họa, yêu cầu **hai container instances** và app `@ConfigurationProperties`/`@Bean` thực sự bind vào các keys này. Việc đăng ký key mới không tự tạo/đổi DataSource bean.

### Đúng DataSource/qualifier quan trọng hơn một URL chung

Khi ứng dụng có `@Primary DataSource` cho orders và `@Qualifier("auditDataSource")` cho audit, một test chỉ mở connection primary không thể chứng minh audit source cũng đúng. Hãy:

- Inject từng DataSource với qualifier tương ứng.
- Mở connection và kiểm `DatabaseProductName`, catalog/schema của từng resource.
- Kiểm repository/transaction manager đã dùng đúng DataSource.
- Khi có `AbstractRoutingDataSource`, thiết lập đúng tenant/route context trước khi kiểm.
- Tránh dùng connection details một container để cấu hình nhầm cả hai nguồn.

Trong test slice Boot 3.3, `@AutoConfigureTestDatabase` replacement thường chỉ cân nhắc **primary DataSource**, không tự thay tất cả các nguồn trong multi-DB app. Nếu đã dùng `Replace.NONE`, đó là yêu cầu giữ DataSource, **không tự xác nhận từng nguồn là test-only**.

## 18. Khi nào Testcontainers JDBC URL `jdbc:tc:` là lựa chọn khác?

Testcontainers có một chế độ JDBC URL đặc biệt, ví dụ:

~~~properties
spring.datasource.url=jdbc:tc:postgresql:16-alpine:///sampledb
~~~

Khi có Testcontainers JDBC driver support phù hợp, một connection thông qua URL `jdbc:tc:...` có thể tạo database container mà không cần khai báo `@Container` theo cách thông thường.

Đây là **hướng thay thế**, không dùng trong runnable lab. Điểm khác biệt:

| Cách | Quản lý container | Cấu hình |
| --- | --- | --- |
| Static `@Container` + `@DynamicPropertySource` | JUnit/Testcontainers extension | Registry URL/user/password từ container |
| Static `@Container` + `@ServiceConnection` | JUnit/Testcontainers + Boot typed details | Ít boilerplate nếu supported |
| JDBC URL `jdbc:tc:...` | Testcontainers JDBC driver | URL đặc biệt, lifecycle gắn với JDBC |
| External DB test cố định | Hạ tầng ngoài Testcontainers | File/profile/CI secrets, cần tự quản lý |

Không trộn `jdbc:tc:` với `postgres::getJdbcUrl` trong cùng một DataSource nếu không hiểu semantics. Với Boot 3.3 test slices, vẫn phải chú ý embedded database replacement; `Replace.NONE` là policy rõ ràng khi muốn giữ nguồn kết nối đã cấu hình.

## 19. Test auto-config vs test chuẩn bị schema

`@DynamicPropertySource` chỉ cung cấp kết nối. Nó **không tự tạo bảng, index hoặc insert fixture**. Trong runnable lab, ta dùng:

~~~properties
spring.jpa.hibernate.ddl-auto=create-drop
~~~

vì đây là bài học về dynamic connection, không phải bài Flyway/Liquibase. Điều này có các giới hạn:

- Hibernate tạo schema theo entity hiện tại trong container test.
- Nó không chứng minh migrations đã được triển khai đúng.
- Không mô phỏng dữ liệu legacy trong một DB đang chạy version trước.
- `create-drop` không phù hợp database production hoặc database chia sẻ.
- Nếu deploy thật dùng Flyway/Liquibase, phải có migration integration tests riêng.

Trong dự án có Flyway hoặc Liquibase:

1. Cho test database được tạo riêng.
2. Chạy migration thật trước khi repository queries.
3. Dùng `ddl-auto=validate` hoặc `none` theo hợp đồng.
4. Verify DB engine/schema/migration history.
5. Tạo fixture cô lập và kiểm behavior.

Nếu dùng `@DataJpaTest` trên PostgreSQL Testcontainers, thêm đúng migration test auto-config nếu cần; không giả định schema có sẵn chỉ vì DataSource đã kết nối thành công.

### “Connection successful” chưa phải “Integration successful”

Một phép thử chỉ:

~~~java
try (Connection c = dataSource.getConnection()) {
    assertTrue(c.isValid(2));
}
~~~

có thể chứng minh connection usable, nhưng không chứng minh schema đúng, JPA mapping đúng, migration đúng hoặc service nghiệp vụ hoạt động. Vì vậy runnable lab có **hai loại assertion**: JDBC metadata **và** repository/service round-trip.

## 20. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `Mapped port can only be obtained after the container is started` | Gọi getMappedPort/getJdbcUrl khi container chưa start | Dùng Supplier và quản lý lifecycle static @Container đúng |
| `@DynamicPropertySource method must be static` | Method instance hoặc signature sai | `static void method(DynamicPropertyRegistry registry)` |
| Không tìm thấy DynamicPropertyRegistry | Thiếu spring-test/Spring TestContext dependency | `spring-boot-starter-test` trong testImplementation |
| Không có Docker environment | Docker daemon/socket/permissions thiếu | Sửa runner/container runtime; không giả pass |
| `Connection refused` đến localhost:5432 | URL hardcode port nội bộ, mapped port khác | Dùng `postgres::getJdbcUrl` |
| Hikari connect nhầm port cũ | Reuse cached context sau container restart/stop | Đồng bộ lifecycle và context cache |
| Environment cho Postgres URL nhưng query chạy H2 | `@DataJpaTest` Boot 3.3 replace DataSource | `Replace.NONE`; assert JDBC metadata |
| `Failed to replace DataSource with embedded database` | Slice đòi H2/HSQLDB nhưng không có driver | `Replace.NONE` để giữ container nếu đó là mục tiêu |
| `No suitable driver` | Thiếu PostgreSQL JDBC driver trên test runtime | Thêm `testRuntimeOnly org.postgresql:postgresql` |
| DataSource tự dùng localhost:5432 | Dynamic registry không được phát hiện hoặc key sai | Kiểm Spring test context và prefix configuration |
| Container isRunning=true nhưng app vẫn sai DB | Bean custom/ConnectionDetails có precedence khác | Kiểm metadata của injected DataSource thực |
| `@ServiceConnection` không hoạt động | Thiếu spring-boot-testcontainers hoặc unsupported container info | Thêm module/cấu hình hoặc dùng DynamicPropertySource |
| App không nạp business service trong `@DataJpaTest` | Slice cố ý giới hạn component scan | Chuyển full context hoặc `@Import` có chủ đích |
| Test chỉ chạy một class, cả suite fail | Spring context cache reuse stale container | Tách context/lifecycle hoặc `@DirtiesContext` khi cần |
| Test rollback nhưng DB còn row | HTTP/server transaction hoặc REQUIRES_NEW/auto-commit độc lập | Cleanup scoped/transaction đúng |
| `relation customer_accounts does not exist` | Chưa chạy DDL/migrations | Cấu hình schema strategy đúng test DB |
| Insert trùng unique key | Fixture hardcode email dùng chung | Dùng test-specific UUID và cleanup/rollback |
| Hikari pool exhaustion | Không đóng JDBC connection hoặc giữ transaction lâu | Try-with-resources, giảm contention |
| CI Docker pull timeout | Network/registry restrictions | Dùng cached image/registry mirror theo chính sách |
| Password bị lộ trong logs | Log full Environment/URL/secret | Sanitize; không log passwords/tokens |
| Test pass trên laptop, fail CI | Docker differences, OS, architecture, resources | Chuẩn hóa CI runner/image version và test settings |

### Debug theo thứ tự

1. Kiểm **Spring Boot version**: code mẫu là 3.3.5.
2. Kiểm JDK/Gradle/Testcontainers dependencies và Docker daemon.
3. Container có start không? Nếu không, đọc Testcontainers root cause.
4. `@DynamicPropertySource` có đúng static method/registry signatures?
5. Có truyền **supplier**, không gọi getter quá sớm?
6. Property keys có được Spring Boot/custom configuration đọc?
7. Đang dùng `@SpringBootTest` hay slice `@DataJpaTest`/`@JdbcTest`?
8. Với Boot 3.3 slice, có `@AutoConfigureTestDatabase(replace = NONE)`?
9. Có `@ServiceConnection`/custom bean ghi đè connection details?
10. Mở DataSource connection thực, kiểm DB product/cataloɡ/URL.
11. Query repository thật, không chỉ Environment hoặc container.isRunning.
12. Khi chạy cả suite, xem context cache và container lifecycle.
13. Khi có fixture/state, kiểm transaction và cleanup.
14. Không đưa credentials/PII vào logs trong lúc debug.

## 21. Bài tập thực hành

**Bài A — bỏ URL động:** Trong class full context, tạm xóa `registry.add("spring.datasource.url", postgres::getJdbcUrl)` và chạy trên một database test riêng. Giải thích vì sao auto-configuration không còn endpoint, hoặc có thể dùng nhầm URL khác từ environment. Khôi phục đăng ký.

**Bài B — đổi thành getter trực tiếp:** Thử `registry.add("spring.datasource.url", postgres.getJdbcUrl())`. Code phải **không compile** vì đối số cần Supplier. Sửa lại method reference.

**Bài C — hardcode port:** Thay container URL bằng `jdbc:postgresql://localhost:5432/accounts_full_test` trong một test branch. Quan sát rủi ro nối nhầm DB hoặc kết nối fail khi mapped port khác. Hoàn nguyên.

**Bài D — H2 replacement:** Trong JPA slice, bỏ `@AutoConfigureTestDatabase(replace=NONE)` và thêm H2 test driver. Với Boot 3.3, slice có thể thay Postgres bằng H2; metadata assertion phải phát hiện sai engine.

**Bài E — metadata vs Environment:** Viết assertion chỉ đọc `environment.getProperty("spring.datasource.url")`; giải thích vì sao nó không đủ nếu DataSource đã bị replace. Viết lại bằng Connection metadata.

**Bài F — thêm custom property:** Giả lập một HTTP server chạy mapped port động và đăng ký `external.payment.base-url`. Dùng client thật trong app để gọi server mock, assert request và response.

**Bài G — cùng container, nhiều test classes:** Dùng một base class khai báo dynamic properties và static container. Chạy suite khi container được stop giữa classes; kiểm context cache, lựa chọn singleton lifetime hoặc `@DirtiesContext` phù hợp.

**Bài H — service connection:** Thêm `spring-boot-testcontainers` và đổi một class riêng sang `@ServiceConnection`. Bỏ dynamic registry cho PostgreSQL trong class đó, rồi assert JDBC metadata; so sánh boilerplate và behavior.

**Bài I — profile:** Thêm `@ActiveProfiles("test")` và cấu hình logging/schema strategy tĩnh. Giữ URL/credentials trong `@DynamicPropertySource`. Giải thích trách nhiệm của mỗi công cụ.

**Bài J — cleanup:** Trong full context test, dùng một UUID email; kiểm @AfterEach dọn row đúng email. Không dùng `deleteAll()` khi có test chạy song song.

**Bài K — Flyway migration:** Bỏ `ddl-auto=create-drop`, thêm Flyway migration tạo `customer_accounts`. Chạy trên Postgres container, assert migration history và repository round-trip.

**Bài L — database khác:** Dùng MySQLContainer theo version MySQL của tổ chức, thay JDBC driver và registry tương ứng; kiểm `DatabaseProductName = MySQL`. Không giả định PostgreSQL-specific SQL portable.

**Bài M — nhiều services:** Đăng ký PostgreSQL và Redis mapped ports trong cùng registry; kiểm cả JPA repository và Redis client. Tránh tự mở rộng thành stress test không ổn định.

## 22. Checklist trước khi merge

- [ ] Mục tiêu có thật sự cần endpoint/config **động** không?
- [ ] `@DynamicPropertySource` là static void method với một `DynamicPropertyRegistry`?
- [ ] Mọi `registry.add` dùng Supplier/method reference?
- [ ] Container được start trước khi Spring resolve connection settings?
- [ ] Không hardcode host port của container?
- [ ] Không dùng Docker/container không do test lifecycle quản lý?
- [ ] Dynamic properties đúng keys mà DataSource/custom client đọc?
- [ ] Không đăng ký cùng một datasource đồng thời qua `@ServiceConnection` và registry khi không hiểu precedence?
- [ ] Dùng test-only container/credentials, không lộ secrets?
- [ ] Trong Boot 3.3 `@DataJpaTest`/`@JdbcTest`, dùng `Replace.NONE` khi phải giữ Testcontainers?
- [ ] Tôi đã kiểm `DataSource.getConnection().getMetaData()` thực tế?
- [ ] Có ít nhất một query/operation thật để chứng minh integration?
- [ ] Schema được khởi tạo đúng bằng test DDL/migration, không ngầm dựa production?
- [ ] Transaction/cleanup phù hợp giữa full context và test slice?
- [ ] Fixture dùng unique test IDs, không xóa dữ liệu ngoài phạm vi?
- [ ] Static container lifetime khớp ApplicationContext cache?
- [ ] Parallel tests không restart shared container hoặc mutate global System properties?
- [ ] CI có Docker runtime, image, permissions và network đúng?
- [ ] Tests không âm thầm chuyển sang H2/mocks khi cần DB production engine?
- [ ] Logs không chứa passwords/tokens/PII?
- [ ] Gradle/JUnit report cho biết test thực sự chạy, không chỉ cache task?

## 23. Nguồn tham khảo chính thức

Các nguồn dưới đây tương thích với chủ đề Spring Boot 3.3.x/Spring Framework 6.1.x; kiểm dependency/version chính xác khi nâng lên Boot 3.4+ hoặc Boot 4.

- [Spring Framework — Context Configuration with Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): method static, registry Supplier, precedence, inheritance và context caching.
- [Spring Framework 6.1 — DynamicPropertySource Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/context/DynamicPropertySource.html): annotation API và test lifecycle.
- [Spring Boot 3.3 — Testcontainers](https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html): `@ServiceConnection` và `@DynamicPropertySource`.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@DataJpaTest`, `@JdbcTest`, test datasource replacement.
- [Spring Boot 3.3 — AutoConfigureTestDatabase.Replace](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.Replace.html): `ANY`, `AUTO_CONFIGURED`, `NONE`.
- [Spring Boot 3.4 — AutoConfigureTestDatabase.Replace](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.Replace.html): `NON_TEST` nhận diện các database dành cho tests.
- [Testcontainers Java — JUnit 5 Quickstart](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers`, `@Container` lifecycle.
- [Testcontainers Java — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): `PostgreSQLContainer`, `getJdbcUrl`, database/user/password.
- [Spring Data JPA — Testing and Transactions](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): test slice rollback mặc định và context setup.
- [JUnit Jupiter — User Guide](https://docs.junit.org/5.10.2/user-guide/): method lifecycle và Gradle/JUnit Platform.

**Ghi nhớ:** `@DynamicPropertySource` là cầu nối giữa **endpoint được tạo động trong Testcontainers** và **Spring Environment**. Cách dùng đúng gồm static method, `DynamicPropertyRegistry.add(..., Supplier)`, container lifecycle ổn định, property names chính xác, và assertions trên JDBC/HTTP integration thật. Với JPA/JDBC slices của Spring Boot 3.3, hãy giữ datasource container bằng `@AutoConfigureTestDatabase(replace=NONE)`. Đừng coi một URL đúng trong properties là bằng chứng cuối cùng: hãy kiểm **DataSource đang mở connection tới đâu**.
