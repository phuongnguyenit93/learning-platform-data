# Nạp cấu hình DataSource và repository cần thiết

Kiểm thử tầng dữ liệu cần một `DataSource` có thể kết nối tới database và một tập repository phù hợp với phạm vi test. Với Spring Data JPA, context còn cần nhận diện entity, tạo `EntityManagerFactory` và transaction manager. Với JDBC, context cần `JdbcTemplate` hoặc các DAO tương ứng. Nếu thiếu một phần cấu hình, test có thể không khởi động, inject nhầm repository hoặc chạy trên một database khác với dự kiến.

Khi chuẩn bị test, hãy xác định rõ mình muốn kiểm tra điều gì: câu lệnh SQL, mapping entity, query repository, transaction, hay toàn bộ luồng từ service tới database. Từ mục tiêu đó, chọn test slice hoặc full application context, rồi nạp đúng `DataSource`, repository và cấu hình liên quan. Một context dữ liệu nhỏ thường chạy nhanh và dễ chẩn đoán hơn; full context phù hợp khi chính sự phối hợp với các bean khác là điều cần kiểm tra.

## 1. Các thành phần cần có ở tầng dữ liệu

Một test Spring làm việc với database thường cần một số thành phần sau:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `DataSource` | Cung cấp kết nối JDBC tới database | HikariCP, H2, PostgreSQL datasource |
| JDBC access | Thực thi SQL trực tiếp | `JdbcTemplate`, `NamedParameterJdbcTemplate` |
| Entity | Mô tả dữ liệu được ORM quản lý | `@Entity Order` |
| `EntityManagerFactory` | Tạo `EntityManager` cho JPA | `LocalContainerEntityManagerFactoryBean` |
| Repository | Cung cấp API truy vấn và lưu dữ liệu | `JpaRepository`, `CrudRepository`, DAO tùy chỉnh |
| Transaction manager | Quản lý ranh giới transaction | `DataSourceTransactionManager`, `JpaTransactionManager` |
| Schema và dữ liệu mẫu | Tạo cấu trúc bảng và fixture | Flyway, Liquibase, `schema.sql`, `@Sql` |

Không phải test nào cũng cần tất cả các thành phần. Một JDBC test có thể chỉ cần `DataSource` và `JdbcTemplate`. Một JPA repository test cần entity mapping, repository infrastructure và transaction manager. Test service gọi repository có thể cần thêm service bean và các collaborator khác.

## 2. Chọn phạm vi test trước khi nạp cấu hình

Spring Boot cung cấp các test slice để chỉ khởi tạo phần ứng dụng liên quan tới tầng dữ liệu:

| Annotation | Phạm vi chính | Khi phù hợp |
| --- | --- | --- |
| `@JdbcTest` | JDBC infrastructure và các thành phần liên quan | Kiểm tra SQL, `JdbcTemplate` hoặc JDBC component |
| `@DataJpaTest` | Entity, Spring Data JPA repository và JPA infrastructure | Kiểm tra mapping, derived query, JPQL và repository |
| `@SpringBootTest` | ApplicationContext rộng theo cấu hình Boot | Kiểm tra repository cùng service, transaction, event hoặc các module khác |
| `@SpringJUnitConfig` | Spring TestContext với Java/XML configuration được chỉ định | Dùng Spring Framework thuần hoặc một context tự thiết kế |

`@DataJpaTest` và `@JdbcTest` thường cấu hình transaction cho test method và rollback sau mỗi method. Chúng không mặc định nạp toàn bộ service của ứng dụng. Nếu test cần một bean hỗ trợ, có thể import nó bằng `@Import` hoặc test configuration.

Không dùng `@SpringBootTest` chỉ vì repository không được tìm thấy. Trước hết hãy kiểm tra package scan, entity scan và cấu hình slice. Chỉ chuyển sang full context khi hành vi cần kiểm tra thực sự phụ thuộc vào cấu hình toàn ứng dụng.

## 3. Cấu hình DataSource trong Spring Boot

Spring Boot có thể tự cấu hình `DataSource` từ các thuộc tính `spring.datasource.*`, miễn là có JDBC driver và dependency phù hợp trên classpath.

Ví dụ cấu hình trong `application-test.yml`:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders_test
    username: test_user
    password: test_password
    driver-class-name: org.postgresql.Driver
    hikari:
      maximum-pool-size: 4
      minimum-idle: 1
```

Các thuộc tính thường gặp:

- `spring.datasource.url`: JDBC URL của database.
- `spring.datasource.username` và `spring.datasource.password`: thông tin xác thực.
- `spring.datasource.driver-class-name`: JDBC driver; thường Boot có thể suy luận từ URL.
- `spring.datasource.hikari.*`: cấu hình pool nếu datasource sử dụng HikariCP.

Không đưa mật khẩu production vào test resource hoặc source control. Dùng thông tin xác thực riêng cho database test, biến môi trường hoặc secret của CI. Nếu test sử dụng database được tạo động, có thể cung cấp URL và credential qua dynamic properties.

Kích hoạt profile test:

```java
@SpringBootTest
@ActiveProfiles("test")
class OrderRepositoryIntegrationTest {
}
```

`@ActiveProfiles("test")` yêu cầu Spring nạp cấu hình profile `test`, chẳng hạn `application-test.yml` trong Spring Boot. Profile chỉ chọn cấu hình; nó không tự tạo database, schema hoặc tài khoản.

## 4. Dependency cần thiết cho test dữ liệu

Với Spring Boot và JPA, dependency thường dùng là `spring-boot-starter-data-jpa`, JDBC driver cho database và `spring-boot-starter-test` ở test scope. Nếu dùng H2 làm database nhúng, thêm H2 ở test scope.

Ví dụ Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Nếu dùng PostgreSQL, thêm driver PostgreSQL trong scope phù hợp với cách ứng dụng chạy. Với Testcontainers, thêm module database tương ứng và `spring-boot-testcontainers` nếu sử dụng `@ServiceConnection`.

Không thêm đồng thời nhiều driver hoặc database chỉ để thử ngẫu nhiên. Hãy xác định test cần database nhúng, database container hay database riêng được cung cấp bởi CI.

## 5. `@DataJpaTest` tự cấu hình những gì?

`@DataJpaTest` là test slice dành cho JPA. Nó cấu hình các thành phần phổ biến như:

- Entity scanning và Spring Data JPA repositories theo cấu hình ứng dụng.
- `DataSource` và JPA infrastructure.
- `EntityManager` cho test.
- Transaction test-managed; mặc định rollback sau mỗi test method.
- Các thành phần cần thiết để kiểm tra repository mà không nạp toàn bộ application context.

Ví dụ:

```java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    OrderRepository orderRepository;

    @Test
    void findsOrdersByCustomerId() {
        orderRepository.save(new Order("customer-42"));

        List<Order> result = orderRepository.findByCustomerId("customer-42");

        assertEquals(1, result.size());
    }
}
```

Test slice giúp kiểm tra repository thật với database test. Không cần mock `OrderRepository` vì chính repository là đối tượng cần được kiểm tra.

`@DataJpaTest` không mặc định nạp mọi `@Service`, controller hoặc bean tùy chỉnh của ứng dụng. Nếu cần kiểm tra một service gọi repository, hãy cân nhắc `@SpringBootTest` hoặc import service cần thiết vào slice khi cấu trúc phù hợp.

## 6. Chọn database nhúng hay database thật

Theo cấu hình mặc định và phiên bản Spring Boot, `@DataJpaTest` có thể thay datasource của ứng dụng bằng database nhúng nếu một database nhúng tương thích có trên classpath. H2 thường được dùng cho mục đích này.

Database nhúng có ưu điểm:

- Khởi động nhanh và dễ chạy trên máy lập trình.
- Không cần cài database server.
- Dữ liệu có thể được tạo mới cho mỗi context hoặc theo cấu hình URL.
- Phù hợp với test repository cơ bản và kiểm tra logic SQL tương đối portable.

Nhưng database nhúng có thể khác database production về:

- Cú pháp SQL và function đặc thù.
- Kiểu dữ liệu, collation, timezone và sequence.
- Constraint, index, locking và isolation.
- Query planner và hiệu năng.
- Hành vi migration hoặc extension của database.

Nếu ứng dụng chạy PostgreSQL, MySQL hoặc Oracle ở production, nên có integration test trên đúng engine thông qua Testcontainers hoặc database test riêng. H2 vẫn hữu ích cho test nhanh, nhưng không thay thế được kiểm chứng tương thích với database production.

## 7. Giữ datasource đã cấu hình bằng `@AutoConfigureTestDatabase`

Khi muốn `@DataJpaTest` sử dụng datasource được cấu hình thay vì tự thay bằng database nhúng, có thể dùng:

```java
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
class PostgreSqlOrderRepositoryTest {
    // ...
}
```

`Replace.NONE` yêu cầu giữ datasource đã được cấu hình. Đây là lựa chọn thường dùng khi datasource trỏ tới PostgreSQL Testcontainers hoặc một database test do CI cung cấp.

Hãy phân biệt hai mục tiêu:

- Muốn dùng database nhúng để test nhanh: cho phép test slice thay datasource theo cấu hình mặc định của phiên bản Boot.
- Muốn xác nhận hành vi trên database cụ thể: giữ datasource được cung cấp và bảo đảm URL trỏ tới môi trường test an toàn.

Không đặt `Replace.NONE` một cách máy móc nếu ứng dụng đang có URL mặc định trỏ tới database dùng chung hoặc production. Cấu hình test phải xác định rõ database nào được phép nhận dữ liệu test.

## 8. Khởi chạy PostgreSQL bằng Testcontainers

Testcontainers tạo database thật trong container, giúp kiểm tra query và mapping trên cùng loại database với production. Một cách dùng phổ biến là JUnit Testcontainers extension kết hợp `@DynamicPropertySource`.

```java
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class OrderRepositoryPostgresTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    OrderRepository repository;

    @Test
    void persistsOrderUsingPostgreSql() {
        repository.save(new Order("customer-42"));

        assertTrue(repository.existsByCustomerId("customer-42"));
    }
}
```

Trong ví dụ, container được khởi chạy bởi Testcontainers JUnit extension. `@DynamicPropertySource` cung cấp JDBC URL, username và password cho Spring Boot. `Replace.NONE` giữ datasource được cấu hình từ container.

Để biên dịch ví dụ, dự án cần module Testcontainers PostgreSQL, JUnit Jupiter integration và driver PostgreSQL. Nếu dùng Spring Boot 3.1 trở lên, có thể cân nhắc `@ServiceConnection` cùng dependency `spring-boot-testcontainers` để Boot tự suy luận connection details từ container.

Container không tự tạo schema ứng dụng. Cần cấu hình Hibernate DDL, Flyway, Liquibase hoặc SQL initialization để tạo bảng trước khi repository test chạy.

## 9. Dùng `@ServiceConnection` với Spring Boot

Spring Boot hỗ trợ `@ServiceConnection` để tự tạo connection details cho một số Testcontainers container phổ biến. Ví dụ:

```java
@DataJpaTest
@Testcontainers
class OrderRepositoryContainerTest {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    OrderRepository repository;
}
```

`@ServiceConnection` cần Spring Boot hỗ trợ API này và dependency `spring-boot-testcontainers`. Cách này giảm số property phải đăng ký thủ công. Nếu loại container hoặc service không được hỗ trợ tự động, có thể dùng `@DynamicPropertySource` hoặc `DynamicPropertyRegistrar` tùy phiên bản Spring.

Không kết hợp nhiều cơ chế đăng ký cùng một property nếu không có lý do. Chọn một nguồn connection details rõ ràng để tránh khó hiểu giá trị nào đang được dùng.

## 10. Nạp repository và entity ở package riêng

Spring Boot thường suy luận package scan từ class `@SpringBootApplication` hoặc cấu hình chính. Nếu entity hoặc repository nằm ngoài package gốc, cần chỉ rõ phạm vi.

Ví dụ:

```java
@SpringBootApplication
@EntityScan(basePackageClasses = OrderEntity.class)
@EnableJpaRepositories(basePackageClasses = OrderRepository.class)
public class OrdersApplication {
}
```

`@EntityScan` chỉ định package chứa entity; `@EnableJpaRepositories` chỉ định package chứa Spring Data repository. Dùng `basePackageClasses` để tránh tên package dạng chuỗi và giữ tham chiếu tới class mốc.

Trong một test slice, nếu Boot không tìm thấy entity hoặc repository, hãy kiểm tra package gốc và cấu hình scan trước. Chỉ thêm `@EnableJpaRepositories` hoặc `@EntityScan` riêng trong test khi cấu trúc package thực sự cần cấu hình rõ ràng.

Nếu một repository được định nghĩa trong module thư viện, hãy chắc rằng module đó nằm trong test runtime classpath và package của nó được đưa vào repository scanning.

## 11. Cấu hình Spring Data repository bằng `@EnableJpaRepositories`

Trong Spring Framework thuần hoặc cấu hình JPA thủ công, `@EnableJpaRepositories` bật cơ chế phát hiện và tạo implementation cho repository interface.

```java
@Configuration
@EnableJpaRepositories(basePackageClasses = OrderRepository.class)
class JpaRepositoryConfig {
}
```

Ví dụ repository:

```java
public interface OrderRepository extends JpaRepository<Order, Long> {

    List<Order> findByCustomerId(String customerId);
}
```

Spring Data tạo proxy implementation cho repository. Ta không tự viết class implement mọi method CRUD. Tuy nhiên, custom repository fragment hoặc implementation riêng vẫn cần được đặt đúng package và tuân theo naming convention/cấu hình tương ứng của Spring Data.

Các thuộc tính hữu ích của `@EnableJpaRepositories` gồm `basePackages`, `basePackageClasses`, `entityManagerFactoryRef` và `transactionManagerRef`. Với một datasource mặc định, các tham chiếu thường được suy luận. Với nhiều datasource, cần chỉ rõ repository nào dùng entity manager factory và transaction manager nào.

## 12. Cấu hình JPA trong Spring Framework thuần

Nếu không dùng Spring Boot auto-configuration, cần khai báo `DataSource`, `EntityManagerFactory`, transaction manager và repository scanning.

Ví dụ cấu hình test với H2:

```java
@Configuration
@EnableTransactionManagement
@EnableJpaRepositories(basePackageClasses = OrderRepository.class)
class JpaTestConfig {

    @Bean
    DataSource dataSource() {
        return new EmbeddedDatabaseBuilder()
            .setType(EmbeddedDatabaseType.H2)
            .addScript("classpath:/db/schema.sql")
            .build();
    }

    @Bean
    LocalContainerEntityManagerFactoryBean entityManagerFactory(
            DataSource dataSource) {

        var factory = new LocalContainerEntityManagerFactoryBean();
        factory.setDataSource(dataSource);
        factory.setPackagesToScan("com.example.orders.domain");
        factory.setJpaVendorAdapter(new HibernateJpaVendorAdapter());
        factory.setJpaPropertyMap(Map.of(
            "hibernate.hbm2ddl.auto", "none",
            "hibernate.show_sql", "false"
        ));
        return factory;
    }

    @Bean
    PlatformTransactionManager transactionManager(
            EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

Test sử dụng cấu hình:

```java
@SpringJUnitConfig(JpaTestConfig.class)
class OrderRepositoryTest {

    @Autowired
    OrderRepository repository;

    @Test
    void savesOrder() {
        // ...
    }
}
```

Ví dụ này giả định dependency Spring ORM, Spring Data JPA, Hibernate, H2 và Spring Test đã được khai báo. `EmbeddedDatabaseBuilder` thuộc Spring JDBC. `setPackagesToScan` phải trỏ tới package chứa entity. `@EnableJpaRepositories` phải trỏ tới package chứa repository interface.

Trong cấu hình thực tế, nên dùng package marker class thay cho chuỗi package nếu phù hợp. Cũng cần quản lý lifecycle datasource và entity manager factory qua bean destruction do Spring thực hiện.

## 13. Cấu hình JDBC test bằng `@JdbcTest`

Nếu component sử dụng JDBC thuần, không cần dựng JPA infrastructure. `@JdbcTest` tạo slice tập trung vào datasource và JDBC support:

```java
@JdbcTest
class OrderJdbcRepositoryTest {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void insertsAndReadsOrder() {
        jdbcTemplate.update(
            "insert into orders(id, customer_id, status) values (?, ?, ?)",
            42L, "customer-42", "PENDING"
        );

        String status = jdbcTemplate.queryForObject(
            "select status from orders where id = ?",
            String.class,
            42L
        );

        assertEquals("PENDING", status);
    }
}
```

`@JdbcTest` thường cấu hình embedded database nếu có và transaction rollback sau test. Nếu cần test DAO component cụ thể, có thể import component đó:

```java
@JdbcTest
@Import(OrderJdbcRepository.class)
class OrderJdbcRepositoryTest {
}
```

Không dùng `@DataJpaTest` cho DAO JDBC thuần nếu không cần entity manager. Chọn slice đúng giúp context nhỏ và test thể hiện rõ công nghệ truy cập dữ liệu đang được kiểm tra.

## 14. Nạp cấu hình repository tùy chỉnh vào test slice

Đôi khi repository cần converter, custom implementation hoặc bean hỗ trợ mà slice không tự nạp. Có thể tạo `@TestConfiguration`:

```java
@TestConfiguration(proxyBeanMethods = false)
class RepositoryTestSupport {

    @Bean
    Clock testClock() {
        return Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"),
            ZoneOffset.UTC
        );
    }
}
```

Import vào test:

```java
@DataJpaTest
@Import(RepositoryTestSupport.class)
class OrderRepositoryTest {

    @Autowired
    OrderRepository repository;
}
```

`@TestConfiguration` bổ sung bean dành riêng cho test. Không đặt test helper trong package production scan nếu không muốn bean đó xuất hiện trong ứng dụng runtime.

Nếu repository phụ thuộc một converter hoặc custom bean, hãy import đúng thành phần cần thiết. Tránh dùng `@ComponentScan` toàn bộ ứng dụng bên trong `@DataJpaTest`, vì điều đó có thể biến slice thành context gần như full application và làm tăng thời gian khởi động.

## 15. Dùng `@ContextConfiguration` để nạp cấu hình dữ liệu riêng

Với Spring Framework thuần, `@ContextConfiguration` chỉ rõ cấu hình cần nạp:

```java
@SpringJUnitConfig(classes = {
    JpaTestConfig.class,
    RepositoryTestSupport.class
})
class OrderRepositoryIntegrationTest {

    @Autowired
    OrderRepository repository;
}
```

Nếu dùng XML:

```java
@SpringJUnitConfig(locations = "classpath:/spring/persistence-test-context.xml")
class LegacyRepositoryTest {
}
```

Có thể kết hợp Java configuration và XML nếu dự án đang chuyển đổi dần:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(
    classes = JpaTestConfig.class,
    locations = "classpath:/spring/legacy-datasource-test.xml"
)
class RepositoryMigrationTest {
}
```

Đảm bảo các bean được khai báo từ nhiều nguồn không trùng tên hoặc trùng type theo cách gây ambiguity. Nếu test dùng Spring Boot, hãy cân nhắc `@DataJpaTest` hoặc `@SpringBootTest` trước khi tự dựng toàn bộ cấu hình thủ công.

## 16. Entity scan và repository scan là hai việc riêng

Một lỗi thường gặp là repository interface đã được tìm thấy nhưng entity lại không được nhận diện, hoặc entity có nhưng repository proxy không được tạo.

Hai phạm vi cần phân biệt:

- Entity scan tìm class có `@Entity`, `@Embeddable` hoặc các kiểu persistence liên quan theo cấu hình.
- Repository scan tìm interface Spring Data như `JpaRepository` và tạo proxy.

Trong cấu hình Spring Boot:

```java
@EntityScan(basePackageClasses = OrderEntity.class)
@EnableJpaRepositories(basePackageClasses = OrderRepository.class)
```

Trong cấu hình JPA thuần:

```java
factory.setPackagesToScan("com.example.orders.domain");
```

và:

```java
@EnableJpaRepositories(basePackageClasses = OrderRepository.class)
```

Nếu test báo `Not a managed type`, kiểm tra entity package và entity manager factory. Nếu báo không tìm thấy bean repository, kiểm tra repository scan, dependency Spring Data và context configuration.

## 17. Cấu hình schema và dữ liệu khởi tạo

Repository chỉ hoạt động khi schema cần thiết đã tồn tại. Có một số chiến lược phổ biến:

| Cách tạo schema | Khi phù hợp | Điểm cần chú ý |
| --- | --- | --- |
| Hibernate DDL (`create`, `create-drop`) | Test nhanh với entity mapping đơn giản | Có thể không phản ánh schema production và migration |
| `schema.sql` / `data.sql` | Schema nhỏ hoặc fixture SQL rõ ràng | Cần cấu hình đúng thời điểm và database platform |
| Flyway | Migration versioned được dùng như runtime | Tốt khi muốn test migration thật |
| Liquibase | ChangeLog quản lý schema | Dùng cùng changelog production nếu mục tiêu là kiểm tra schema thật |
| `@Sql` | Fixture theo test method/class | Phải quản lý transaction và cleanup |

Với Spring Boot, có thể cấu hình Hibernate DDL cho test:

```yaml
spring:
  jpa:
    hibernate:
      ddl-auto: create-drop
```

Chỉ dùng `create-drop` khi test chủ động muốn schema được tạo từ entity metadata. Nếu production dùng Flyway hoặc Liquibase, integration test quan trọng nên chạy migration thật để phát hiện sai lệch giữa entity và schema được triển khai.

Với SQL initialization:

```yaml
spring:
  sql:
    init:
      mode: always
      schema-locations: classpath:/db/schema-test.sql
      data-locations: classpath:/db/test-data.sql
```

Các thuộc tính cụ thể cần được đối chiếu với phiên bản Spring Boot. Tránh để Hibernate DDL, `schema.sql` và Flyway/Liquibase cùng cố tạo một schema theo những chính sách mâu thuẫn. Chọn một cơ chế chính và cấu hình rõ thứ tự khởi tạo.

## 18. Nạp dữ liệu theo test bằng `@Sql`

`@Sql` phù hợp khi mỗi test cần fixture riêng hoặc nhiều bảng cần dữ liệu liên kết:

```java
@DataJpaTest
@Sql("/sql/orders/insert-order-fixture.sql")
class OrderRepositoryQueryTest {

    @Autowired
    OrderRepository repository;

    @Test
    void findsPendingOrders() {
        List<Order> result = repository.findByStatus(OrderStatus.PENDING);

        assertFalse(result.isEmpty());
    }
}
```

Mặc định, script thường được thực thi trước test method. Có thể khai báo rõ `executionPhase` là `BEFORE_TEST_METHOD` hoặc `AFTER_TEST_METHOD`.

Với test transaction rollback, script và test có thể tham gia transaction theo cấu hình mặc định. Nếu cần cleanup commit độc lập, có thể dùng `@SqlConfig(transactionMode = ISOLATED)` và xác nhận transaction manager được chọn đúng.

Không nên đặt một file SQL khổng lồ làm fixture cho mọi test nếu mỗi test chỉ cần một vài bản ghi. Fixture quá rộng làm test phụ thuộc lẫn nhau và khó biết dữ liệu nào thực sự cần thiết.

## 19. Flush và clear khi kiểm tra JPA repository

JPA có persistence context. Khi gọi `save()`, entity có thể chỉ được quản lý trong persistence context; SQL chưa chắc đã được gửi ngay xuống database. Một test có thể đọc lại cùng object từ persistence context và vẫn xanh dù mapping hoặc constraint có vấn đề chỉ xuất hiện khi flush.

Để kiểm tra tương tác database thực tế hơn, hãy flush và clear:

```java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    OrderRepository repository;

    @Autowired
    TestEntityManager entityManager;

    @Test
    void persistsAndReloadsOrder() {
        Order saved = repository.save(new Order("customer-42"));

        entityManager.flush();
        entityManager.clear();

        Order reloaded = repository.findById(saved.getId()).orElseThrow();

        assertEquals("customer-42", reloaded.getCustomerId());
    }
}
```

`flush()` đẩy thay đổi đang chờ xuống database, giúp phát hiện một số lỗi SQL, constraint hoặc mapping. `clear()` loại entity đang được quản lý khỏi persistence context, buộc truy vấn tiếp theo đọc lại dữ liệu. `TestEntityManager` là tiện ích của Spring Boot Data JPA Test; với Spring Framework thuần, có thể dùng `EntityManager` trực tiếp.

Không cần flush/clear trong mọi test. Dùng chúng khi mục tiêu là xác nhận dữ liệu đã được ghi và đọc lại qua persistence layer, đặc biệt với mapping, cascade, constraint và query.

## 20. Cấu hình nhiều DataSource và nhiều repository group

Một ứng dụng có thể kết nối nhiều database, ví dụ database đơn hàng và database báo cáo. Khi đó, mỗi nhóm repository cần được gắn với `EntityManagerFactory` và transaction manager phù hợp.

Ví dụ cấu hình khái quát:

```java
@Configuration
@EnableJpaRepositories(
    basePackageClasses = OrderRepository.class,
    entityManagerFactoryRef = "ordersEntityManagerFactory",
    transactionManagerRef = "ordersTransactionManager"
)
class OrdersDatabaseConfig {
    // Khai báo ordersDataSource, ordersEntityManagerFactory,
    // ordersTransactionManager
}
```

Nhóm báo cáo:

```java
@Configuration
@EnableJpaRepositories(
    basePackageClasses = ReportRepository.class,
    entityManagerFactoryRef = "reportsEntityManagerFactory",
    transactionManagerRef = "reportsTransactionManager"
)
class ReportsDatabaseConfig {
    // Khai báo reportsDataSource, reportsEntityManagerFactory,
    // reportsTransactionManager
}
```

Khi có nhiều datasource, cần xác định rõ:

- Bean `DataSource` nào được inject vào từng entity manager factory.
- Package repository nào thuộc database nào.
- Entity package nào được scan bởi entity manager factory tương ứng.
- Transaction manager nào quản lý method repository/service.
- Test transaction cần chỉ rõ transaction manager nào nếu có nhiều lựa chọn.

Có thể dùng `@Qualifier` khi inject datasource hoặc transaction manager. Một bean có thể được đánh dấu `@Primary` cho luồng mặc định, nhưng không nên dựa vào primary khi test cần xác nhận repository dùng đúng database cụ thể.

Ví dụ test chọn transaction manager:

```java
@DataJpaTest
@Transactional("ordersTransactionManager")
class OrderRepositoryTest {
    // ...
}
```

Annotation và cách cấu hình nhiều persistence unit cần phù hợp với phiên bản Spring Data JPA và cấu trúc ứng dụng. Với nhiều datasource, một test context nhỏ riêng cho từng database thường dễ chẩn đoán hơn việc nạp tất cả persistence unit vào mọi test.

## 21. Repository tùy chỉnh và implementation fragment

Một repository có thể kết hợp method được Spring Data tự sinh với custom implementation. Khi test repository, phải nạp cả interface, entity và custom fragment implementation.

Ví dụ:

```java
public interface OrderRepository extends
        JpaRepository<Order, Long>,
        OrderRepositoryCustom {
}

public interface OrderRepositoryCustom {
    List<Order> searchOpenOrders(String customerId);
}
```

Implementation:

```java
class OrderRepositoryCustomImpl implements OrderRepositoryCustom {

    private final EntityManager entityManager;

    OrderRepositoryCustomImpl(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Override
    public List<Order> searchOpenOrders(String customerId) {
        return entityManager.createQuery(
            "select o from Order o where o.customerId = :customerId " +
            "and o.status = :status", Order.class)
            .setParameter("customerId", customerId)
            .setParameter("status", OrderStatus.OPEN)
            .getResultList();
    }
}
```

Spring Data tìm implementation theo convention tên fragment và package phù hợp. Nếu implementation cần bean khác, hãy cấu hình chúng như dependency bình thường và bảo đảm chúng có trong test context.

Không mock custom fragment khi mục tiêu là kiểm tra query của nó. Hãy chạy repository thật với database test và xác nhận kết quả từ database.

## 22. Kiểm tra cấu hình DataSource trực tiếp

Khi test không khởi động hoặc kết nối nhầm database, có thể inject `DataSource` và kiểm tra metadata JDBC:

```java
@SpringBootTest
class DataSourceConfigurationTest {

    @Autowired
    DataSource dataSource;

    @Test
    void connectsToExpectedDatabase() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData metadata = connection.getMetaData();

            assertEquals("PostgreSQL", metadata.getDatabaseProductName());
        }
    }
}
```

Test này xác nhận datasource có thể mở connection và database engine đúng như mong đợi. Không in JDBC URL đầy đủ nếu nó chứa thông tin nhạy cảm. Nếu cần xác nhận schema hoặc catalog, hãy kiểm tra metadata an toàn hoặc truy vấn tới bảng/phiên bản phù hợp.

Khi kiểm tra nhiều datasource, inject theo qualifier và xác nhận từng nguồn riêng. Đừng chỉ xác nhận context có một bean `DataSource`; điều đó không chứng minh repository cụ thể đang dùng đúng datasource.

## 23. Cô lập test dữ liệu và cleanup

Với `@DataJpaTest` hoặc `@JdbcTest`, transaction test thường rollback sau method. Tuy nhiên, cleanup vẫn cần được thiết kế nếu:

- Test dùng `@Commit` hoặc `@Rollback(false)`.
- Code mở transaction `REQUIRES_NEW`.
- Công việc được chạy ở thread khác hoặc qua async executor.
- Database được dùng chung bởi nhiều worker/test process.
- Side effect nằm ngoài transaction database.

Khi cần cleanup thủ công, ưu tiên ID riêng của test:

```java
@AfterEach
void cleanUp() {
    repository.deleteByTestRunId(testRunId);
}
```

Không xóa toàn bảng trên database dùng chung. Nếu test chạy song song, dùng UUID, schema riêng hoặc database riêng để tránh một test xóa dữ liệu của test khác.

Nếu test chỉ thay đổi dữ liệu nghiệp vụ, không cần `@DirtiesContext`. Context có thể được tái sử dụng; database cần được rollback hoặc cleanup tại chính nguồn dữ liệu.

## 24. Những lỗi thường gặp khi nạp DataSource và repository

- **Thiếu JDBC driver:** datasource không thể tạo connection hoặc báo không tìm thấy driver phù hợp.
- **URL hoặc credential sai:** context khởi động thất bại khi pool tạo connection.
- **Test dùng nhầm database:** profile hoặc property source không được kích hoạt như dự kiến.
- **`@DataJpaTest` thay datasource ngoài ý muốn:** database nhúng được chọn thay vì container/database đã cấu hình; xem lại `@AutoConfigureTestDatabase`.
- **Không có embedded database trên classpath:** test slice không có database nhúng để sử dụng; cần cung cấp database phù hợp.
- **Entity không được scan:** lỗi `Not a managed type` hoặc entity manager không nhận diện entity.
- **Repository không được scan:** không có bean repository để inject.
- **Thiếu transaction manager:** repository/service không có transaction manager phù hợp hoặc có nhiều manager gây ambiguity.
- **DDL và migration xung đột:** Hibernate, SQL initialization và Flyway/Liquibase cùng tạo hoặc thay đổi schema.
- **H2 khác database production:** test nhanh qua H2 nhưng query thất bại trên PostgreSQL/MySQL thực tế.
- **Slice không chứa custom bean:** repository cần converter hoặc collaborator chưa được import.
- **Test chỉ đọc từ persistence context:** thiếu flush/clear nên chưa chứng minh dữ liệu được ghi và đọc lại từ database.
- **Dữ liệu bị rò rỉ:** commit, `REQUIRES_NEW`, async hoặc database dùng chung vượt ra ngoài transaction rollback.
- **Nhiều datasource mơ hồ:** repository dùng nhầm entity manager factory hoặc transaction manager.

## 25. Quy trình chẩn đoán DataSource và repository

Khi test tầng dữ liệu không khởi động hoặc kết quả không như mong đợi, hãy kiểm tra theo thứ tự:

1. **Dependency:** có Spring Data/JDBC, JDBC driver và database test cần thiết trong test runtime không?
2. **Phạm vi test:** dùng `@JdbcTest`, `@DataJpaTest`, `@SpringBootTest` hay `@SpringJUnitConfig` đúng với mục tiêu chưa?
3. **Property/profile:** `spring.datasource.url`, username, password và active profile có đúng không?
4. **Datasource replacement:** test slice có thay datasource bằng embedded database không; có cần `Replace.NONE` không?
5. **Schema:** bảng được tạo bằng migration, Hibernate DDL hay SQL script nào?
6. **Entity scan:** package entity đã được đưa vào entity manager factory chưa?
7. **Repository scan:** interface repository có nằm trong phạm vi `@EnableJpaRepositories` hoặc Boot auto-configuration không?
8. **Bean wiring:** repository có dùng đúng `DataSource`, `EntityManagerFactory` và transaction manager không?
9. **Transaction:** test có thực sự tham gia transaction mong muốn; có `REQUIRES_NEW`, async hoặc datasource khác không?
10. **Database engine:** có cần Testcontainers để xác nhận hành vi của database production thay vì chỉ dùng H2 không?

Có thể bật log phù hợp cho `org.springframework.jdbc`, `org.springframework.orm.jpa`, `org.springframework.data.repository` hoặc connection pool khi chẩn đoán. Hãy giới hạn log ở mức cần thiết và không ghi credential hoặc dữ liệu nhạy cảm.

## 26. Ví dụ lựa chọn cấu hình theo mục tiêu

| Mục tiêu | Cấu hình gợi ý | Database |
| --- | --- | --- |
| Kiểm tra một JDBC DAO | `@JdbcTest` và `@Import(dao.class)` | H2 hoặc database test |
| Kiểm tra derived query của repository | `@DataJpaTest` | H2 cho vòng nhanh |
| Kiểm tra native query PostgreSQL | `@DataJpaTest` + `Replace.NONE` + Testcontainers | PostgreSQL container |
| Kiểm tra service gọi repository và transaction | `@SpringBootTest` hoặc context hẹp có service | Database test tương thích |
| Kiểm tra cấu hình JPA trong Spring Framework thuần | `@SpringJUnitConfig(JpaTestConfig.class)` | EmbeddedDatabase hoặc container |
| Kiểm tra nhiều persistence unit | Context riêng, nhiều datasource và repository group rõ ràng | Database/schema riêng cho từng nhóm |

Một chiến lược thực tế thường có nhiều lớp: unit test service dùng mock repository khi chỉ kiểm tra logic; repository slice test dùng database thật hoặc nhúng; một số integration test dùng Testcontainers với đúng engine production; và chỉ một số ít full-context test xác nhận toàn bộ wiring.

## 27. Tổng kết

Nạp đúng `DataSource` và repository là nền tảng của kiểm thử tầng dữ liệu. Với Spring Boot, `@JdbcTest` và `@DataJpaTest` cung cấp slice phù hợp cho JDBC và JPA; `@AutoConfigureTestDatabase` giúp kiểm soát việc thay datasource; Testcontainers hoặc database test riêng giúp kiểm tra trên đúng engine. Với Spring Framework thuần, cần khai báo rõ datasource, entity manager factory, transaction manager và repository scanning.

Hãy phân biệt entity scan với repository scan, cấu hình schema riêng với datasource, và transaction test với các side effect chạy ngoài transaction. Khi context chỉ nạp những bean cần thiết và database được chọn có chủ đích, test tầng dữ liệu sẽ dễ lặp lại, dễ chẩn đoán và cung cấp bằng chứng sát với môi trường ứng dụng thực tế.
