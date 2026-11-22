# Kiểm thử Repository bằng Testcontainers và migration thực tế

Một repository test chạy trên H2 thường nhanh và tiện, nhưng H2 không thay thế được PostgreSQL hoặc MySQL khi ứng dụng phụ thuộc vào SQL, kiểu dữ liệu, collation, constraint, locking hay hành vi riêng của database triển khai. Testcontainers cho phép khởi chạy database thật trong Docker ngay khi chạy test. Khi kết hợp với Flyway hoặc Liquibase, bài test sẽ đi qua đúng chuỗi mà ứng dụng cần khi khởi động: tạo database, chạy migration, kiểm tra mapping JPA rồi thực thi repository.

Mục tiêu của bài thực hành là xây dựng một bộ kiểm thử có thể xác nhận:

1. Test đang kết nối đúng engine và phiên bản database đã chọn.
2. Container được khởi động trước khi Spring tạo DataSource và EntityManagerFactory.
3. Migration production thực sự chạy trên database container.
4. Hibernate kiểm tra mapping với schema do migration tạo.
5. Repository đọc, ghi, phân trang và thực thi constraint trên engine thật.
6. Transaction rollback, commit và lỗi database được kiểm tra ở đúng ranh giới.
7. Test có dữ liệu độc lập, có thể chạy lặp lại trên máy lập trình và CI.

Testcontainers không loại bỏ nhu cầu unit test. Hãy dùng unit test cho quy tắc nghiệp vụ không cần database, dùng repository test nhanh cho truy vấn portable nếu có lợi, và dùng container cho những hành vi cần tương thích với database thật.

## 1. Chọn loại test phù hợp

Spring Boot cung cấp hai cách thường dùng để kiểm thử Spring Data JPA.

**`@DataJpaTest`** tạo một test slice tập trung vào entity, repository, JPA và các cấu hình liên quan. Nó không tải toàn bộ service hoặc web layer. Theo mặc định, test có transaction và rollback khi kết thúc. Nếu có embedded database trên classpath, Spring Boot có thể thay DataSource bằng database trong bộ nhớ. Khi muốn dùng Testcontainers, cần cấu hình `@AutoConfigureTestDatabase(replace = Replace.NONE)`.

**`@SpringBootTest`** tải ApplicationContext của ứng dụng. Dùng cách này khi cần xác minh service, transaction boundary, event listener, cấu hình datasource, security hoặc nhiều bean phối hợp. Có thể dùng `webEnvironment = NONE` nếu không cần mở HTTP server.

| Nhu cầu | Annotation thường phù hợp |
|---|---|
| Mapping entity, derived query, JPQL, native query và repository CRUD | `@DataJpaTest` |
| Repository cùng service và transaction nghiệp vụ | `@SpringBootTest` |
| Kiểm tra API HTTP gọi tới service và database | `@SpringBootTest(webEnvironment = RANDOM_PORT)` |
| Migration tạo schema và Hibernate validate mapping | Cả hai; thường dùng `@SpringBootTest` cho luồng ứng dụng đầy đủ |
| Kiểm tra commit thực tế | Test được thiết kế riêng, không bị bao bởi transaction rollback của test |

Không nên chọn `@DataJpaTest` chỉ vì nó chạy nhanh nếu test cần bean service hoặc cấu hình không nằm trong test slice. Test slice giới hạn component scan; có thể import bean cần thiết, hoặc chuyển sang `@SpringBootTest` khi cần toàn bộ ứng dụng.

## 2. Dependency và khác biệt phiên bản

Ví dụ bên dưới dùng Spring Boot 4.1.x và Testcontainers 2.0.x. Các phiên bản được quản lý bằng Spring Boot dependency management và Testcontainers BOM. Testcontainers 2.x đổi tên artifact module và package container so với dòng 1.x, vì vậy không trộn tọa độ dependency hoặc import của hai dòng.

Ví dụ Maven:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>testcontainers-bom</artifactId>
            <version>2.0.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa-test</artifactId>
        <scope>test</scope>
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
        <artifactId>testcontainers-junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers-postgresql</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers-mysql</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>com.mysql</groupId>
        <artifactId>mysql-connector-j</artifactId>
        <scope>runtime</scope>
    </dependency>

    <!-- Chọn Flyway hoặc Liquibase, không dùng cả hai để quản lý cùng schema. -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-flyway</artifactId>
    </dependency>
    <dependency>
        <groupId>org.flywaydb</groupId>
        <artifactId>flyway-database-postgresql</artifactId>
    </dependency>
    <dependency>
        <groupId>org.flywaydb</groupId>
        <artifactId>flyway-mysql</artifactId>
    </dependency>
</dependencies>
~~~

Nếu dự án dùng Liquibase, thay starter Flyway và các Flyway database modules bằng `spring-boot-starter-liquibase`; giữ lại PostgreSQL/MySQL JDBC driver và Testcontainers modules. Đừng khai báo Flyway và Liquibase cùng quản lý một schema.

Với Spring Boot 3.1 trở lên, `@ServiceConnection` đã có sẵn nhưng package test annotation và dependency Testcontainers phụ thuộc phiên bản. Spring Boot 3.x thường dùng `org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest` và Testcontainers 1.x với artifact `postgresql`, `mysql`, `junit-jupiter`. Spring Boot 4.x và Testcontainers 2.x dùng các module test starter và package mới như trong ví dụ. Hãy dùng BOM và tài liệu đúng major version của dự án.

## 3. Khởi chạy PostgreSQL hoặc MySQL container

Spring Boot có thể quản lý container như một Spring bean. Cách này phù hợp với TestContext cache: container được khởi động cùng ApplicationContext và dừng khi context đóng. `@ServiceConnection` giúp Spring Boot tạo connection details từ container, nên không cần tự ghép JDBC URL, username và password.

### Cấu hình PostgreSQL

Đặt class cấu hình trong `src/test/java`:

~~~java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.postgresql.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
class PostgresContainerConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer postgresContainer() {
        return new PostgreSQLContainer("postgres:16.6-alpine")
                .withDatabaseName("jpa_test")
                .withUsername("test_user")
                .withPassword("test_password");
    }
}
~~~

### Cấu hình MySQL

Khi cần kiểm thử MySQL, dùng một cấu hình riêng và import vào test class tương ứng:

~~~java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.mysql.MySQLContainer;

@TestConfiguration(proxyBeanMethods = false)
class MySqlContainerConfiguration {

    @Bean
    @ServiceConnection
    MySQLContainer mysqlContainer() {
        return new MySQLContainer("mysql:8.4")
                .withDatabaseName("jpa_test")
                .withUsername("test_user")
                .withPassword("test_password");
    }
}
~~~

Chỉ import một cấu hình database vào mỗi test context. Nếu ứng dụng hỗ trợ cả PostgreSQL và MySQL, tạo hai nhóm test độc lập hoặc hai profile CI. Không để hai container cùng cung cấp một DataSource mặc định trong cùng test context nếu chưa cấu hình rõ nhiều datasource.

Pin image version gần với production, ví dụ PostgreSQL 16.x hoặc MySQL 8.4.x. Tránh dùng tag `latest`, vì image có thể thay đổi giữa hai lần chạy test. Nếu production bật extension, collation, timezone hoặc cấu hình server đặc biệt, hãy tái tạo các điều kiện đó trong container.

### Gắn container vào @DataJpaTest

~~~java
import org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;

@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
@Import(PostgresContainerConfiguration.class)
@ActiveProfiles("test")
class AccountRepositoryPostgresTest {
    // Các test repository
}
~~~

`replace = NONE` ngăn Spring thay PostgreSQL container bằng H2. `@Import` đưa `@TestConfiguration` vào test slice. Với MySQL, thay cấu hình import bằng `MySqlContainerConfiguration.class`.

### Khi nào dùng @DynamicPropertySource?

`@DynamicPropertySource` là lựa chọn thay thế khi không dùng `@ServiceConnection`, cần cấu hình một datasource tùy biến hoặc đang dùng Spring Boot cũ hơn 3.1:

~~~java
@Container
static final PostgreSQLContainer postgres =
        new PostgreSQLContainer("postgres:16.6-alpine");

@DynamicPropertySource
static void datasourceProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
    registry.add("spring.datasource.driver-class-name",
            postgres::getDriverClassName);
}
~~~

Đoạn này giả định container được quản lý bởi JUnit Testcontainers extension với `@Testcontainers` và `@Container`. Khi dùng JUnit extension, container static được dừng sau test class, trong khi Spring có thể giữ ApplicationContext trong cache và tái sử dụng cho class khác. Nếu context còn sống nhưng container đã dừng, test sau có thể lỗi kết nối. Với Spring Boot, ưu tiên Spring-managed container bean hoặc `@ImportTestcontainers` khi cần chia sẻ context lâu hơn.

## 4. Chạy migration thật trước khi test repository

Điểm quan trọng của bài test là schema phải do migration production tạo. Không để Hibernate tự tạo bảng rồi kết luận migration đã đúng.

Với Flyway, đặt migration trong `src/main/resources/db/migration`:

`V1__create_account.sql` cho PostgreSQL:

~~~sql
CREATE TABLE account (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_account_email UNIQUE (email)
);
~~~

Nếu chạy cùng nghiệp vụ trên MySQL, migration có thể cần cú pháp riêng, ví dụ:

`V1__create_account.sql` trong thư mục migration MySQL:

~~~sql
CREATE TABLE account (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_account_email UNIQUE (email)
);
~~~

Không giả định một migration có cú pháp identity, JSON, sequence, index hoặc function riêng sẽ chạy nguyên trạng trên cả hai engine. Nếu phải hỗ trợ nhiều vendor, dùng thư mục migration riêng hoặc cấu trúc migration portable đã được kiểm chứng. Flyway hỗ trợ placeholder `{vendor}` trong location, ví dụ:

~~~properties
spring.flyway.locations=classpath:db/migration/{vendor}
~~~

Tên thư mục được chọn theo vendor do Flyway nhận diện, chẳng hạn `postgresql` hoặc `mysql`. Hãy kiểm tra đường dẫn thực tế bằng log Flyway.

Với cấu hình test:

~~~properties
spring.flyway.enabled=true
spring.flyway.locations=classpath:db/migration
spring.jpa.hibernate.ddl-auto=validate
spring.jpa.show-sql=false
~~~

Khi Spring tạo ApplicationContext, Flyway kết nối vào container, đọc migration chưa chạy và áp dụng chúng. Sau đó Hibernate khởi tạo EntityManagerFactory và kiểm tra mapping với schema hiện có.

`ddl-auto=validate` giúp phát hiện một số sai lệch về bảng/cột giữa entity và schema. Nó không thay thế kiểm tra mọi index, trigger, check constraint, extension hay nội dung migration. Vì vậy vẫn cần test trực tiếp các ràng buộc quan trọng. Nếu schema hoàn toàn do migration quản lý, có thể dùng `ddl-auto=none` và tự kiểm tra schema bằng test.

Không dùng `create` hoặc `create-drop` trong bài test migration production, vì Hibernate có thể tạo schema mới và che mất migration thiếu hoặc sai. Cũng không trộn `schema.sql`/ `data.sql` với Flyway hoặc Liquibase để cùng tạo schema.

### Nếu dùng Liquibase

Đặt changelog chính ở vị trí mặc định hoặc cấu hình rõ ràng:

~~~properties
spring.liquibase.enabled=true
spring.liquibase.change-log=classpath:db/changelog/db.changelog-master.yaml
spring.jpa.hibernate.ddl-auto=validate
~~~

Ví dụ changelog YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-account
      author: team
      changes:
        - createTable:
            tableName: account
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(320)
                  constraints:
                    nullable: false
                    unique: true
              - column:
                  name: display_name
                  type: VARCHAR(120)
                  constraints:
                    nullable: false
~~~

Liquibase chạy changelog trên DataSource của container khi Spring khởi động. Các bảng `DATABASECHANGELOG` và `DATABASECHANGELOGLOCK` ghi nhận lịch sử và trạng thái lock. Khi cần kiểm tra rollback hoặc contexts/labels, chạy đúng changelog và cấu hình tương tự môi trường triển khai.

## 5. Entity, repository và dữ liệu mẫu

Entity cần khớp với schema sau migration. Ví dụ:

~~~java
@Entity
@Table(name = "account")
public class Account {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 320, unique = true)
    private String email;

    @Column(name = "display_name", nullable = false, length = 120)
    private String displayName;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    protected Account() {
    }

    public Account(String email, String displayName) {
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

Repository:

~~~java
public interface AccountRepository extends JpaRepository<Account, Long> {
    Optional<Account> findByEmail(String email);

    List<Account> findByDisplayNameContainingIgnoreCase(String keyword);

    boolean existsByEmail(String email);
}
~~~

Trong ví dụ, getter và constructor chỉ là phần cần thiết cho test minh họa. Một entity thực tế có thể dùng auditing, enum, relationship, embedded type hoặc custom converter; những mapping đó cũng cần được kiểm tra trên database production-compatible.

Fixture nên được tạo có chủ đích và độc lập:

- Dùng builder/factory để tạo entity hợp lệ với giá trị mặc định.
- Dùng email hoặc business key riêng cho từng test để tránh đụng dữ liệu.
- Dùng `@Sql` với script trong `src/test/resources` khi cần một tập dữ liệu cố định.
- Dùng `JdbcTemplate` để chuẩn bị dữ liệu đặc thù hoặc kiểm tra trực tiếp schema.
- Không phụ thuộc vào thứ tự test method hoặc giá trị ID tự tăng cụ thể.

Ví dụ fixture SQL:

~~~sql
INSERT INTO account(email, display_name)
VALUES ('seed@example.com', 'Seed Account');
~~~

Nếu test dùng cả PostgreSQL và MySQL, hãy giữ fixture portable hoặc tách fixture theo vendor khi có khác biệt về cú pháp và kiểu dữ liệu.

## 6. Kiểm thử repository trên database thật

Một test đọc lại entity sau khi flush và clear giúp xác nhận dữ liệu đã đi qua database, thay vì chỉ đọc lại object còn trong persistence context:

~~~java
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Import(PostgresContainerConfiguration.class)
class AccountRepositoryPostgresTest {

    @Autowired
    private AccountRepository repository;

    @Autowired
    private EntityManager entityManager;

    @Test
    void savesAndReloadsAccount() {
        Account saved = repository.saveAndFlush(
                new Account("alice@example.com", "Alice")
        );

        Long id = saved.getId();
        assertThat(id).isNotNull();

        entityManager.clear();

        Account reloaded = repository.findById(id).orElseThrow();

        assertThat(reloaded.getEmail()).isEqualTo("alice@example.com");
        assertThat(reloaded.getDisplayName()).isEqualTo("Alice");
        assertThat(reloaded.getCreatedAt()).isNotNull();
    }

    @Test
    void findsByEmailAndName() {
        repository.saveAndFlush(
                new Account("bob@example.com", "Bob Nguyen")
        );

        assertThat(repository.findByEmail("bob@example.com")).isPresent();
        assertThat(repository.findByDisplayNameContainingIgnoreCase("BOB"))
                .extracting(Account::getEmail)
                .contains("bob@example.com");
    }
}
~~~

Test này kiểm tra insert, ID, default timestamp và query method. Tùy schema, `created_at` có thể được database gán default khi insert. Nếu Hibernate insert explicit NULL thay vì bỏ cột, default không chạy; hãy cấu hình mapping phù hợp hoặc gán giá trị qua entity lifecycle/auditing.

Các nhóm kiểm thử nên có:

- CRUD và mapping quan hệ: `@ManyToOne`, `@OneToMany`, cascade, orphan removal.
- Derived query, JPQL, Criteria/Specification và native query.
- Pagination/sort, count query, projection và fetch strategy.
- Unique, not-null, foreign key, check constraint và default value.
- Kiểu dữ liệu đặc thù: UUID, JSON/JSONB, enum, timestamp, decimal và collation.
- Optimistic locking với `@Version`, pessimistic locking và isolation nếu ứng dụng phụ thuộc.
- Batch insert/update, stored procedure, trigger hoặc function nếu được dùng trong production.

Không chỉ kiểm tra rằng repository trả về một kết quả; hãy xác nhận thứ tự, số lượng, giá trị null, precision và các trường hợp biên mà nghiệp vụ cần.

### Kiểm tra constraint thật

~~~java
@Test
void rejectsDuplicateEmail() {
    repository.saveAndFlush(
            new Account("same@example.com", "First")
    );

    assertThatThrownBy(() ->
            repository.saveAndFlush(
                    new Account("same@example.com", "Second")
            )
    ).isInstanceOf(DataIntegrityViolationException.class);
}
~~~

`saveAndFlush()` buộc Hibernate gửi câu insert để database kiểm tra unique constraint ngay trong lời gọi. Loại exception cụ thể có thể khác theo provider/translator, nhưng với Spring Data JPA thường được chuyển thành `DataIntegrityViolationException`.

Khi câu SQL thất bại, transaction có thể bị đánh dấu rollback-only hoặc database connection đang ở trạng thái lỗi. Không tiếp tục chạy thêm query ghi trong cùng test transaction để kiểm tra hậu quả. Tách mỗi kịch bản constraint thành test method riêng hoặc xác minh sau rollback bằng transaction khác.

## 7. Kiểm tra migration đã chạy và schema có đúng

Với Flyway, có thể kiểm tra lịch sử migration:

~~~java
@Autowired
private JdbcTemplate jdbcTemplate;

@Test
void flywayAppliedMigrations() {
    Integer successful = jdbcTemplate.queryForObject(
            "select count(*) from flyway_schema_history where success = true",
            Integer.class
    );

    assertThat(successful).isNotNull();
    assertThat(successful).isGreaterThan(0);
}
~~~

Với Liquibase, kiểm tra `DATABASECHANGELOG` và `DATABASECHANGELOGLOCK`. Tuy nhiên, chỉ đếm số bản ghi lịch sử chưa chứng minh schema đúng. Hãy xác nhận version cụ thể, checksum hoặc cấu trúc mà migration phải tạo; sau đó thực thi repository query trên schema đó.

Nên có ít nhất hai loại migration test:

**Fresh install:** tạo container rỗng, chạy toàn bộ migration từ phiên bản đầu tiên và kiểm tra repository hoạt động.

**Upgrade path:** dựng schema ở version cũ, nạp dữ liệu đại diện, chạy các migration mới và kiểm tra dữ liệu cũ vẫn đúng. Đây là cách phát hiện lỗi chuyển đổi dữ liệu, default value, constraint mới hoặc migration không an toàn khi có dữ liệu thật.

Với Flyway, không sửa file versioned migration đã được áp dụng ở môi trường dùng chung. Tạo migration version mới; lệnh validate sẽ phát hiện checksum thay đổi ngoài ý muốn. Với Liquibase, không chỉnh sửa changeSet đã triển khai nếu không có quy trình quản lý checksum/clearCheckSums phù hợp; ưu tiên thêm changeSet mới.

## 8. Chọn @DataJpaTest hay @SpringBootTest cho migration?

`@DataJpaTest` phù hợp khi muốn kiểm tra repository và mapping với database container. Test slice tự động cấu hình DataSource, EntityManager và repository; nó mặc định dùng transaction và rollback sau mỗi test. Import container configuration và dùng `replace = NONE` để giữ database thật.

`@SpringBootTest(webEnvironment = NONE)` phù hợp khi cần chứng minh toàn bộ ứng dụng khởi động trên database container, migration chạy, service được inject và transaction nghiệp vụ hoạt động. Ví dụ:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Import(PostgresContainerConfiguration.class)
@ActiveProfiles("test")
class AccountServiceIntegrationTest {

    @Autowired
    private AccountService accountService;

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void serviceCreatesAccount() {
        Account account = accountService.register(
                "service@example.com",
                "Service Test"
        );

        assertThat(account.getId()).isNotNull();
        assertThat(accountRepository.findByEmail("service@example.com"))
                .isPresent();
    }
}
~~~

Nếu service method có `@Transactional`, transaction do service mở sẽ commit khi method kết thúc, vì test ở ví dụ này không được đánh dấu `@Transactional`. Nếu thêm `@Transactional` vào test class, test transaction bên ngoài có thể khiến dữ liệu rollback khi test kết thúc.

### Kiểm tra commit và rollback

`@DataJpaTest` mặc định rollback test transaction. Điều đó tốt cho cleanup nhưng không tự chứng minh đường commit hoạt động. Để kiểm tra commit, có thể vô hiệu hóa test-managed transaction cho test method:

~~~java
@Test
@Transactional(propagation = Propagation.NOT_SUPPORTED)
void serviceCommitIsVisibleAfterMethodReturns() {
    accountService.register("commit@example.com", "Commit Test");

    assertThat(accountRepository.findByEmail("commit@example.com"))
            .isPresent();
}
~~~

Ví dụ giả định `register()` mở transaction riêng qua Spring proxy. Với test rollback, tạo một lỗi nghiệp vụ sau khi ghi, để exception thoát khỏi service transactional rồi xác nhận dữ liệu không còn trong transaction mới.

Nếu dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)`, request HTTP được xử lý ở thread/server transaction riêng. Transaction của test method không bao quanh transaction của request, nên rollback tự động ở test không xóa dữ liệu mà server đã commit. Hãy cleanup rõ ràng hoặc dùng database/schema riêng.

## 9. Cô lập dữ liệu và vòng đời container

Một container có thể được dùng chung cho nhiều test method trong một class hoặc nhiều class nếu Spring giữ chung ApplicationContext. Điều này giúp tiết kiệm thời gian nhưng cần quy tắc dữ liệu rõ ràng.

- Mỗi test tạo business key duy nhất, ví dụ email có suffix từ test name hoặc UUID.
- Dùng `@Sql` hoặc fixture builder để tạo dữ liệu cần thiết trước mỗi test.
- Dùng rollback transaction cho các test repository thông thường.
- Với test commit hoặc test nhiều transaction, cleanup dữ liệu bằng transaction riêng hoặc schema/database cô lập.
- Không phụ thuộc ID auto-increment bắt đầu từ 1; sequence có thể không rollback.
- Không chạy test song song trên cùng dữ liệu dùng chung nếu không có isolation.
- Không để test method đọc dữ liệu do test method khác tạo ra.

Container static do JUnit extension quản lý sẽ dừng sau test class. Spring TestContext có thể cache ApplicationContext và dùng lại giữa các class; context còn sống nhưng container đã dừng sẽ gây lỗi khó chẩn đoán. Vì vậy, với Spring Boot, ưu tiên container bean hoặc `@ImportTestcontainers` để lifecycle của container gắn với lifecycle của ApplicationContext.

Không bật reusable container trong CI nếu chưa có chiến lược reset dữ liệu và bảo đảm tính cô lập. Reuse có thể hữu ích khi phát triển local, nhưng làm test phụ thuộc trạng thái cũ nếu không dọn sạch.

## 10. Chạy trong CI

Testcontainers cần Docker-compatible runtime. Trước khi chạy test, CI runner phải truy cập được Docker daemon hoặc môi trường container được hỗ trợ. Ví dụ lệnh:

~~~bash
./mvnw -Dtest=AccountRepositoryPostgresTest test
~~~

Hoặc:

~~~bash
./gradlew test --tests "*AccountRepositoryPostgresTest"
~~~

Các nguyên tắc cho CI:

1. Pin image version và dependency BOM.
2. Chạy test container trong job có Docker runtime.
3. Không tự động đổi sang H2 khi Docker không khả dụng; job production-compatible phải báo rõ đã chạy hay bị bỏ qua.
4. Thu thập log container và migration khi test thất bại.
5. Chạy nhóm test nhanh thường xuyên, nhóm Testcontainers ít nhất trước merge/release.
6. Nếu chạy nhiều database engine, tách matrix job PostgreSQL/MySQL để biết engine nào thất bại.
7. Dùng image cache để giảm thời gian pull, nhưng không dùng tag mutable như `latest`.

Testcontainers tự dừng và dọn container do lifecycle quản lý. Nếu container không dừng, kiểm tra test process bị kill, Docker runtime hoặc cấu hình cleanup. Không hard-code host port; hãy dùng connection details do Testcontainers cung cấp.

## 11. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Docker daemon unavailable | Docker chưa chạy hoặc CI thiếu quyền | Kiểm tra Docker context/socket và quyền runner |
| Test vẫn chạy trên H2 | `@DataJpaTest` thay datasource embedded | Đặt `replace = NONE`, kiểm tra `@ServiceConnection` |
| Không tạo được ConnectionDetails | Thiếu `spring-boot-testcontainers` hoặc container type không được nhận diện | Kiểm tra dependency và kiểu container |
| `No suitable driver` | Thiếu JDBC driver tương ứng | Thêm PostgreSQL/MySQL driver |
| Flyway báo không có database plugin | Thiếu module Flyway cho engine | Thêm `flyway-database-postgresql` hoặc `flyway-mysql` đúng phiên bản |
| Flyway không thấy migration | Sai location, profile hoặc tên file | Kiểm tra `spring.flyway.locations` và thư mục classpath |
| Hibernate validate thất bại | Entity và schema migration không khớp | So sánh tên cột, kiểu dữ liệu, nullability và version |
| Test pass nhưng commit fail | Chỉ kiểm tra trong transaction rollback | Thêm test commit riêng |
| Test sau bị mất kết nối | JUnit đã dừng container nhưng Spring context còn cache | Quản lý container như Spring bean hoặc import container configuration |
| PostgreSQL pass nhưng MySQL fail | SQL, collation, type hoặc migration phụ thuộc vendor | Tách migration/fixture theo engine và test trên đúng phiên bản |

Khi debug, xem log khởi động Spring, URL/driver thực tế, log Flyway/Liquibase và log container. Không ghi mật khẩu hoặc dữ liệu bind nhạy cảm vào log CI.

## 12. Chiến lược test nhiều lớp

Một pipeline cân bằng có thể chia thành:

| Lớp | Công cụ | Điều cần chứng minh |
|---|---|---|
| Unit test | JUnit, Mockito | Quy tắc nghiệp vụ độc lập database |
| Repository test nhanh | H2 hoặc database container | Mapping và query portable |
| Repository integration | Testcontainers PostgreSQL/MySQL | SQL, type, constraint và dialect thực tế |
| Migration test | Flyway/Liquibase trên container | Fresh install và upgrade schema |
| Service/transaction integration | `@SpringBootTest` + container | Commit, rollback và nhiều bean phối hợp |
| CI matrix | PostgreSQL/MySQL jobs | Mỗi engine được kiểm tra độc lập |

Nếu production chỉ dùng PostgreSQL, ưu tiên container PostgreSQL đúng major version production; không cần chạy MySQL chỉ vì Testcontainers hỗ trợ. Nếu sản phẩm hỗ trợ nhiều database, mỗi engine cần bộ migration và integration test riêng. Kết quả trên một engine không chứng minh engine còn lại tương thích.

## 13. Checklist trước khi hoàn thành

- [ ] Chọn đúng engine và pin version gần production.
- [ ] Có dependency Testcontainers JUnit và module database tương ứng.
- [ ] Có JDBC driver và `spring-boot-testcontainers` khi dùng `@ServiceConnection`.
- [ ] Container được quản lý theo lifecycle phù hợp với Spring context.
- [ ] `@DataJpaTest` dùng `replace = NONE` khi chạy trên container.
- [ ] Migration production thực sự chạy trên database container.
- [ ] Hibernate dùng `validate` hoặc `none`, không tự tạo schema thay migration.
- [ ] Test kiểm tra repository round-trip sau flush/clear.
- [ ] Test kiểm tra unique/FK/not-null/default và native query quan trọng.
- [ ] Test migration fresh install và upgrade path.
- [ ] Test commit/rollback ở transaction boundary phù hợp.
- [ ] Fixture độc lập, không phụ thuộc thứ tự hoặc ID tự tăng.
- [ ] CI có Docker runtime và không âm thầm bỏ qua test container.
- [ ] Log container/migration đủ để chẩn đoán lỗi.

## 14. Tài liệu tham khảo chính thức

- [Spring Boot Testcontainers và @ServiceConnection](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Spring Boot testing: @DataJpaTest, @SpringBootTest và transaction rollback](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Testcontainers PostgreSQL module](https://java.testcontainers.org/modules/databases/postgres/)
- [Testcontainers MySQL module](https://java.testcontainers.org/modules/databases/mysql/)
- [Testcontainers JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/)
- [Flyway PostgreSQL support](https://documentation.red-gate.com/fd/postgresql-database-277579325.html)
- [Flyway MySQL support](https://documentation.red-gate.com/fd/mysql-277579322.html)
- [Spring Boot database initialization và Flyway/Liquibase](https://docs.spring.io/spring-boot/reference/how-to/data-initialization.html)

## Kết luận

Testcontainers giúp Spring Data JPA repository test chạy trên PostgreSQL hoặc MySQL thật trong môi trường cô lập. Khi kết nối container bằng `@ServiceConnection`, chạy migration Flyway/Liquibase và để Hibernate validate schema, test sẽ kiểm tra được cả quá trình khởi tạo database lẫn hành vi repository. Hãy chọn `@DataJpaTest` cho repository slice, `@SpringBootTest` cho service và transaction đầy đủ, kiểm tra commit/rollback riêng, quản lý fixture có tính lặp lại và cấu hình Docker runtime cho CI. Một test chỉ đáng tin cậy cho production khi nó chạy trên đúng engine, migration và phiên bản mà ứng dụng sẽ triển khai.