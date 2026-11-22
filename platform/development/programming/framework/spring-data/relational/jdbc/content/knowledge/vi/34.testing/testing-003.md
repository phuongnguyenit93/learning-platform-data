# Cấu hình @DataJdbcTest và phạm vi bean được nạp

Trong Spring Data Relational JDBC, **`@DataJdbcTest`** là test slice dành cho repository và mapping JDBC. Nó khởi tạo nhóm hạ tầng cần cho Data JDBC, giới hạn phạm vi bean được quét và mặc định chạy mỗi test trong transaction được rollback sau khi test kết thúc.

Điểm quan trọng là `@DataJdbcTest` không nạp toàn bộ application context. Repository và entity được phát hiện theo quy tắc của Data JDBC; các service, controller, component và cấu hình ứng dụng thông thường có thể không xuất hiện. Khi test cần một bean ngoài slice, hãy đưa bean đó vào rõ ràng bằng `@Import`, `@TestConfiguration` hoặc `@EnableConfigurationProperties`.

Bài học trình bày bean nào được nạp, cách bổ sung cấu hình, lựa chọn database, transaction mặc định và sự khác nhau giữa `@DataJdbcTest`, `@JdbcTest` và `@SpringBootTest`.

## 1. @DataJdbcTest là gì?

`@DataJdbcTest` chỉ bật auto-configuration liên quan đến kiểm thử Spring Data JDBC. Trong cấu hình thông thường, nó cung cấp:

- `DataSource` dùng cho test.
- `JdbcTemplate` và các thành phần JDBC cần thiết.
- Spring Data JDBC repositories.
- Mapping infrastructure cho entity và aggregate.
- Transaction management cho test.

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJdbcTest
class ProductRepositoryTest {

    @Autowired
    ProductRepository products;

    @Test
    void savesAndLoadsProduct() {
        Product product = new Product(null, "SKU-01", "Notebook");

        Product saved = products.save(product);

        assertThat(saved.getId()).isNotNull();
        assertThat(products.findById(saved.getId()))
                .get()
                .extracting(Product::getName)
                .isEqualTo("Notebook");
    }
}
~~~

Ví dụ giả định entity và repository đã được khai báo. Mục tiêu là kiểm tra repository hoạt động với database và mapping trong test slice.

### 1.1. Phạm vi test slice

`@DataJdbcTest` phù hợp để kiểm tra:

- Repository CRUD.
- Derived query và query method.
- Mapping entity, value object và aggregate child.
- Custom converter và naming strategy.
- Constraint, generated ID và hành vi JDBC.

Nó không mặc định kiểm tra toàn bộ service orchestration, HTTP layer, security filter hoặc message broker. Với các use case xuyên nhiều layer, hãy cân nhắc `@SpringBootTest`.

### 1.2. JUnit 5

`@DataJdbcTest` đã tích hợp Spring Test extension. Với JUnit 5, thông thường không cần thêm `@ExtendWith(SpringExtension.class)` thủ công.

## 2. Những bean được nạp và không được nạp

### 2.1. Những thành phần được phát hiện

Spring Boot giới hạn component scanning của Data JDBC test slice vào các thành phần persistence phù hợp, chủ yếu gồm:

- Repository của Spring Data JDBC.
- Entity được đánh dấu bằng `@Table`.
- Bean triển khai `AbstractJdbcConfiguration`.
- Các auto-configuration liên quan đến Data JDBC test.

Entity:

~~~java
@Table("product")
public class Product {

    @Id
    private Long id;

    private String sku;
    private String name;
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends CrudRepository<Product, Long> {
}
~~~

Entity và repository được phát hiện nếu nằm trong phạm vi scanning phù hợp của ứng dụng.

### 2.2. Những bean thông thường không tự động được nạp

Các bean ứng dụng sau thường không được quét trong `@DataJdbcTest`:

- `@Service`.
- `@Component`.
- `@Controller` hoặc `@RestController`.
- Các `@Configuration` thông thường không thuộc nhóm cấu hình JDBC được phép.
- `@ConfigurationProperties` bean nếu chưa được bật rõ ràng.

Ví dụ, service sau không tự động có mặt chỉ vì nó nằm cùng package với repository:

~~~java
@Service
public class ProductService {
    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }
}
~~~

Giới hạn này giúp test repository không vô tình phụ thuộc HTTP client, broker, scheduler hoặc các thành phần không liên quan đến persistence.

## 3. Bổ sung bean bằng @Import

Khi test cần một service hoặc cấu hình cụ thể, dùng `@Import`:

~~~java
@DataJdbcTest
@Import(ProductService.class)
class ProductServiceJdbcTest {

    @Autowired
    ProductService productService;

    @Autowired
    ProductRepository products;

    @Test
    void createsProductThroughService() {
        productService.create("SKU-02", "Pen");

        assertThat(products.findBySku("SKU-02")).isPresent();
    }
}
~~~

`@Import(ProductService.class)` đưa service vào test context. Các dependency của service vẫn phải có trong context. Nếu service cần một gateway, clock hoặc policy, hãy import bean thật phù hợp hoặc khai báo bean test.

Có thể import nhiều bean:

~~~java
@DataJdbcTest
@Import({
        ProductService.class,
        ProductPolicy.class,
        ProductJdbcConfiguration.class
})
class ProductServiceJdbcTest {
}
~~~

Chỉ import những bean test cần. Nếu import một cấu hình ứng dụng lớn, context có thể kéo theo nhiều dependency và làm mất lợi ích của slice.

## 4. Dùng @TestConfiguration cho bean chỉ phục vụ test

`@TestConfiguration` cho phép khai báo bean bổ sung dành riêng cho test:

~~~java
@DataJdbcTest
@Import(ProductRepositoryTest.TestConfig.class)
class ProductRepositoryTest {

    @Autowired
    ProductRepository products;

    @TestConfiguration(proxyBeanMethods = false)
    static class TestConfig {

        @Bean
        ProductNamePolicy productNamePolicy() {
            return new ProductNamePolicy(100);
        }
    }
}
~~~

Ví dụ tạo một policy chỉ dùng trong test. `proxyBeanMethods = false` phù hợp khi các method `@Bean` không gọi lẫn nhau qua proxy.

Nếu bean test cần repository hoặc `JdbcTemplate`, inject chúng qua tham số method `@Bean`. Không tự tạo datasource thứ hai nếu test chỉ cần dùng hạ tầng do `@DataJdbcTest` cung cấp.

## 5. Bổ sung @ConfigurationProperties

`@ConfigurationProperties` bean không tự động được đăng ký chỉ vì class tồn tại. Có thể bật rõ bằng `@EnableConfigurationProperties`:

~~~java
@DataJdbcTest
@EnableConfigurationProperties(DatabaseOptions.class)
class ProductRepositoryTest {
}
~~~

Ví dụ properties:

~~~java
@ConfigurationProperties(prefix = "app.database")
public record DatabaseOptions(
        int batchSize,
        boolean auditEnabled
) {
}
~~~

Có thể cung cấp giá trị riêng cho test:

~~~java
@DataJdbcTest(properties = {
        "app.database.batch-size=50",
        "app.database.audit-enabled=false"
})
@EnableConfigurationProperties(DatabaseOptions.class)
class ProductRepositoryTest {
}
~~~

## 6. AbstractJdbcConfiguration và custom mapping

Ứng dụng có thể tùy chỉnh Spring Data JDBC bằng class kế thừa `AbstractJdbcConfiguration`. Cấu hình này có thể đăng ký custom conversions, naming strategy và các thành phần mapping phù hợp.

Ví dụ khung:

~~~java
@Configuration
public class JdbcMappingConfiguration
        extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
                new MoneyToBigDecimalConverter(),
                new BigDecimalToMoneyConverter()
        );
    }
}
~~~

Tên và chữ ký method cấu hình converter phụ thuộc phiên bản Spring Data Relational; dùng API của dependency trong dự án. Nếu cấu hình không được phát hiện trong test, import rõ:

~~~java
@DataJdbcTest
@Import(JdbcMappingConfiguration.class)
class ProductMappingTest {
}
~~~

Nếu production dùng custom converter cho Money, enum hoặc value object, test persistence cần nạp cùng mapping configuration để kết quả phản ánh đúng production.

## 7. Database mặc định và DataSource replacement

Theo mặc định, `@DataJdbcTest` sử dụng database embedded trong bộ nhớ nếu có trên classpath. Nó có thể thay datasource của ứng dụng bằng test database.

Ví dụ thêm H2 cho test:

~~~groovy
dependencies {
    testRuntimeOnly("com.h2database:h2")
}
~~~

Embedded database hữu ích cho CRUD, mapping đơn giản và query portable. Tuy nhiên, nó không bảo đảm behavior giống PostgreSQL, MySQL, SQL Server hoặc Oracle ở mọi trường hợp. SQL dialect, kiểu dữ liệu, function, collation, locking và DDL có thể khác.

### 7.1. Giữ datasource ứng dụng

Nếu muốn test dùng datasource đã cấu hình, có thể khai báo:

~~~java
@DataJdbcTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
class ProductRepositoryPostgresTest {
}
~~~

`Replace.NONE` yêu cầu không thay datasource mặc định của ứng dụng. Đây là lựa chọn rõ ràng khi test kết nối tới database Testcontainers hoặc một database test riêng.

### 7.2. Các chế độ replace

| Giá trị | Ý nghĩa |
| --- | --- |
| `ANY` | Thay datasource dù được auto-configure hay khai báo thủ công |
| `AUTO_CONFIGURED` | Chỉ thay datasource được auto-configure |
| `NON_TEST` | Thay datasource trừ trường hợp datasource auto-configured được nhận diện là test database |
| `NONE` | Không thay datasource ứng dụng |

Mặc định và cách nhận diện test datasource thay đổi theo Spring Boot version. Từ các phiên bản mới, datasource Testcontainers qua `@ServiceConnection` hoặc `@DynamicPropertySource` có thể được nhận diện là test database. Khi muốn giữ datasource một cách tường minh, dùng `Replace.NONE`.

## 8. Dùng Testcontainers cho database production

Nếu production dùng PostgreSQL, test với PostgreSQL qua Testcontainers giúp phát hiện khác biệt dialect mà H2 có thể bỏ sót.

~~~java
@DataJdbcTest
@Testcontainers
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
class ProductRepositoryPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    @Autowired
    ProductRepository products;

    @Test
    void savesProductUsingPostgres() {
        Product saved = products.save(
                new Product(null, "SKU-PG-01", "Notebook")
        );

        assertThat(products.findById(saved.getId())).isPresent();
    }
}
~~~

Ví dụ dùng Spring Boot 3.1+ có hỗ trợ `@ServiceConnection`. Cần khai báo dependency Testcontainers JUnit Jupiter, module PostgreSQL và Spring Boot Testcontainers tương ứng. Chọn image version phù hợp với database production.

### 8.1. Dùng @DynamicPropertySource

Nếu không dùng `@ServiceConnection`, có thể đăng ký URL, username và password:

~~~java
@DynamicPropertySource
static void configureDatabase(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

Container phải sẵn sàng trước khi datasource được tạo. Dùng `Replace.NONE` nếu muốn thể hiện rõ rằng test cần giữ datasource container.

### 8.2. Khi nào cần database mục tiêu?

Hãy dùng database production hoặc Testcontainers khi test phụ thuộc vào:

- Cú pháp SQL riêng như JSON operator, array, CTE hoặc function vendor-specific.
- Kiểu dữ liệu đặc thù.
- Collation và case sensitivity.
- Locking/isolation semantics.
- Generated key, sequence và identity behavior.
- Migration DDL hoặc index strategy riêng.

H2 vẫn hữu ích cho test nhanh, nhưng không phải bằng chứng rằng truy vấn sẽ chạy đúng trên database production.

## 9. Transaction và rollback mặc định

`@DataJdbcTest` được đánh dấu transactional. Mỗi test method thường chạy trong transaction riêng và Spring rollback transaction sau khi test kết thúc.

~~~java
@DataJdbcTest
class ProductRepositoryTest {

    @Autowired
    ProductRepository products;

    @Test
    void insertsProduct() {
        products.save(new Product(null, "SKU-01", "Notebook"));

        assertThat(products.count()).isEqualTo(1);
    }
}
~~~

Sau test, dữ liệu được rollback nên test tiếp theo không bị ảnh hưởng bởi hàng vừa insert.

### 9.1. Test transaction thật của service

Test method đang chạy trong transaction có thể khiến repository operation tham gia transaction của test. Điều này đôi khi làm test không quan sát được commit boundary của service.

Nếu cần kiểm thử hành vi sau commit, listener AFTER_COMMIT hoặc transaction propagation, có thể tắt transaction bao ngoài của test:

~~~java
@DataJdbcTest
@Import(OrderApplicationService.class)
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class OrderApplicationServiceTransactionTest {
}
~~~

Khi test không có transaction ngoài, method service có `@Transactional` sẽ tạo transaction riêng và commit/rollback theo proxy. Cần chuẩn bị dữ liệu và dọn dữ liệu phù hợp với test đó.

Một lựa chọn khác là dùng `TestTransaction` hoặc `@Commit` khi muốn chủ động commit transaction của test. Chỉ dùng khi mục tiêu test thực sự cần commit.

### 9.2. Không tắt rollback cho mọi test

Không nên thêm `@Transactional(propagation = NOT_SUPPORTED)` cho toàn bộ test suite chỉ vì một test cần commit. Test thông thường nên giữ rollback mặc định để độc lập và dễ chạy lặp.

## 10. Migration và schema trong @DataJdbcTest

Repository chỉ hoạt động nếu schema đã sẵn sàng. Có thể tạo schema test theo một trong các cách:

- Flyway migrations.
- Liquibase changelog.
- SQL initialization scripts dành cho test.
- Schema được tạo sẵn bởi test infrastructure.

Nếu ứng dụng dùng Flyway hoặc Liquibase, hãy xác nhận migration auto-configuration được bật trong test slice và chạy trước repository test. Không nên tạo cùng một bảng bằng cả migration và schema script độc lập, vì hai nguồn schema có thể lệch nhau.

### 10.1. Kiểm thử chuỗi migration

Test repository với database trống giúp xác nhận migration tạo được schema. Tuy nhiên, vẫn cần test nâng cấp từ schema version cũ nếu migration có backfill hoặc đổi kiểu.

Với migration quan trọng:

1. Tạo database Testcontainers sạch.
2. Chạy migration đến version cũ.
3. Insert dữ liệu cũ đại diện.
4. Chạy migration mới.
5. Kiểm tra schema, constraint và dữ liệu đã chuyển.
6. Khởi tạo repository và xác nhận mapping hoạt động.

### 10.2. Test slice không phải luôn là migration test đầy đủ

`@DataJdbcTest` tập trung vào Data JDBC components. Nếu migration phụ thuộc cấu hình hoặc thứ tự khởi tạo riêng của ứng dụng, hãy xác nhận context test thực sự nạp migration. Khi cần kiểm thử deployment flow toàn ứng dụng, có thể dùng integration test riêng với `@SpringBootTest`.

## 11. Bổ sung filter scanning khi thật sự cần

`@DataJdbcTest` có thuộc tính `includeFilters` và `excludeFilters` để tùy chỉnh component scanning. Đây là lựa chọn nâng cao khi cần thêm loại bean vào phạm vi scanning.

~~~java
@DataJdbcTest(
        includeFilters = @ComponentScan.Filter(
                type = FilterType.ASSIGNABLE_TYPE,
                classes = ProductService.class
        )
)
class ProductServiceTest {
}
~~~

Trong phần lớn test slice, `@Import(ProductService.class)` hoặc `@TestConfiguration` thường dễ đọc và kiểm soát hơn. Dùng filter khi muốn điều chỉnh quy tắc scanning một cách có hệ thống.

### 11.1. Không dùng component scan toàn bộ ứng dụng

Thêm `@ComponentScan("com.example")` có thể đưa rất nhiều bean vào context và làm mất ý nghĩa của slice. Nếu test cần toàn bộ ứng dụng, dùng `@SpringBootTest` để thể hiện rõ mục đích.

## 12. So sánh @DataJdbcTest, @JdbcTest và @SpringBootTest

| Annotation | Phạm vi | Khi nên dùng |
| --- | --- | --- |
| `@DataJdbcTest` | Spring Data JDBC repositories, entity mapping và hạ tầng JDBC liên quan | Test repository, aggregate mapping, query và persistence |
| `@JdbcTest` | DataSource, JdbcTemplate và hạ tầng JDBC cơ bản; không tập trung vào Spring Data JDBC repositories | Test SQL/JdbcTemplate trực tiếp |
| `@SpringBootTest` | Toàn bộ application context theo cấu hình ứng dụng | Test service orchestration, integration nhiều layer, wiring đầy đủ |

### 12.1. @JdbcTest

`@JdbcTest` phù hợp nếu code dùng `JdbcTemplate` hoặc `NamedParameterJdbcTemplate` trực tiếp và không cần Spring Data JDBC repository.

~~~java
@JdbcTest
class ProductSqlRepositoryTest {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void countsRows() {
        Integer count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM product",
                Integer.class
        );

        assertThat(count).isZero();
    }
}
~~~

### 12.2. @SpringBootTest

`@SpringBootTest` nạp cấu hình ứng dụng đầy đủ:

~~~java
@SpringBootTest
class ProductApplicationIntegrationTest {

    @Autowired
    ProductService productService;

    @Test
    void createsProductThroughApplicationFlow() {
        // test service, repository và các dependency liên quan
    }
}
~~~

Test này có thể cần nhiều dependency hơn và chạy lâu hơn. Bù lại, nó kiểm tra wiring thật của application context.

### 12.3. Chọn annotation theo mục tiêu

- Muốn kiểm tra entity, repository và SQL mapping: chọn `@DataJdbcTest`.
- Muốn kiểm tra một lớp JDBC dùng template trực tiếp: chọn `@JdbcTest`.
- Muốn kiểm tra nhiều layer và cấu hình đầy đủ: chọn `@SpringBootTest`.

Không dùng `@SpringBootTest` cho mọi repository test nếu slice đã đủ. Ngược lại, không ép `@DataJdbcTest` làm nhiệm vụ kiểm tra toàn bộ service graph.

## 13. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy ProductService bean | Service không thuộc component scan của slice | Dùng `@Import` hoặc `@TestConfiguration` |
| Repository không được tạo | Entity/repository nằm ngoài phạm vi scanning hoặc thiếu auto-configuration | Kiểm tra package, `@Table` và repository setup |
| Không có custom converter | Cấu hình JDBC không được import/phát hiện | Import subclass `AbstractJdbcConfiguration` |
| Không bind được properties | `@ConfigurationProperties` chưa được bật | Dùng `@EnableConfigurationProperties` |
| Test chạy trên H2 thay vì PostgreSQL | Test database replacement đã thay datasource | Dùng Testcontainers và `Replace.NONE` |
| SQL chạy trên H2 nhưng lỗi production | Dialect hoặc kiểu dữ liệu khác nhau | Test trên database mục tiêu |
| Dữ liệu test còn lại giữa các test | Transaction rollback bị tắt hoặc test commit | Kiểm tra propagation, `@Commit` và cleanup |
| Không quan sát được AFTER_COMMIT | Test transaction bao ngoài chưa commit | Dùng `NOT_SUPPORTED` hoặc điều khiển `TestTransaction` |
| Flyway/Liquibase không chạy | Auto-configuration bị tắt hoặc không có dependency | Kiểm tra dependency, property và auto-config test |
| Bean bị nạp quá nhiều | Dùng component scan rộng | Giữ slice hẹp, import bean cần thiết |
| Test không tìm được application configuration | Test nằm ngoài package scan của Boot | Đặt test đúng package hoặc chỉ định test configuration |

## 14. Quy trình cấu hình một Data JDBC test

Khi tạo test cho repository:

1. **Xác định mục tiêu:** chỉ test repository hay cần service/use case?
2. **Dùng `@DataJdbcTest`:** để nạp Data JDBC slice và repository.
3. **Kiểm tra entity scan:** entity cần được mapping bằng annotation phù hợp như `@Table`.
4. **Bổ sung bean có chủ đích:** dùng `@Import`, `@TestConfiguration` hoặc `@EnableConfigurationProperties`.
5. **Chọn database:** embedded cho test nhanh, Testcontainers cho dialect production.
6. **Kiểm soát datasource replacement:** dùng `@AutoConfigureTestDatabase` nếu cần giữ datasource đã cấu hình.
7. **Chuẩn bị schema:** xác nhận Flyway/Liquibase hoặc SQL initialization chạy đúng.
8. **Giữ rollback mặc định:** chỉ tắt transaction cho test cần quan sát commit thật.
9. **Kiểm tra mapping và aggregate:** test root, child, generated ID, custom conversion và constraint.
10. **Chuyển sang full context khi cần:** dùng `@SpringBootTest` cho wiring và integration nhiều layer.

## Ghi nhớ

`@DataJdbcTest` là test slice tập trung vào Spring Data JDBC. Nó cấu hình hạ tầng database cho test, phát hiện repository và entity `@Table`, đồng thời mặc định chạy test trong transaction được rollback sau mỗi method. Phạm vi bean bị giới hạn: service, component, controller và configuration properties thông thường không tự động được nạp. Dùng `@Import` hoặc `@TestConfiguration` để thêm bean cần thiết; dùng `@EnableConfigurationProperties` cho properties bean và import cấu hình kế thừa `AbstractJdbcConfiguration` khi cần custom mapping.

Mặc định test thường dùng embedded database nếu có trên classpath. Khi cần kiểm tra đúng dialect production, dùng Testcontainers và cấu hình `@AutoConfigureTestDatabase(replace = Replace.NONE)` để giữ datasource container. Giữ rollback mặc định cho test repository thông thường; chỉ tắt transaction bao ngoài khi cần kiểm tra commit, rollback hoặc event sau commit. Chọn `@JdbcTest` cho code JDBC dùng template trực tiếp và `@SpringBootTest` khi cần toàn bộ application context.

## Tài liệu tham khảo

- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [DataJdbcTest API — Spring Boot 3.5](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/data/jdbc/DataJdbcTest.html)
- [AutoConfigureTestDatabase API — Spring Boot 3.5](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.html)
- [AutoConfigureTestDatabase.Replace API — Spring Boot 3.5](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.Replace.html)
