# Kiểm thử tính năng mở rộng Hibernate trên phiên bản và cơ sở dữ liệu mục tiêu

Một tính năng mở rộng Hibernate có thể hoạt động trong unit test nhưng thất bại khi chạy trên phiên bản Hibernate khác hoặc database thật. Nguyên nhân thường nằm ở khác biệt API/SPI, cách provider sinh SQL, kiểu dữ liệu JDBC, transaction semantics, dialect, migration hoặc extension không được đăng ký trong SessionFactory.

Kiểm thử extension phải xác nhận đồng thời ba điều: extension được nạp đúng vào Hibernate, hành vi của nó đúng theo nghiệp vụ và nó tương thích với tổ hợp Hibernate/Jakarta Persistence/JDK/JDBC driver/database mà ứng dụng hỗ trợ. H2 hữu ích cho test nhanh, nhưng không thay thế được integration test trên database mục tiêu.

Bài này xây dựng chiến lược kiểm thử từ unit test đến Testcontainers, lập ma trận tương thích, minh họa mapping tùy biến trên PostgreSQL và chỉ ra các kiểm tra cần có cho UserType, Integrator, event listener, interceptor, Dialect, filter, generator, cache và bytecode enhancement.

## 1. Xác định chính xác thứ cần kiểm thử

Trước khi viết test, phân loại extension đang phát triển. Mỗi loại có điểm hỏng khác nhau.

| Extension hoặc điểm mở rộng | Điều cần xác nhận |
|---|---|
| Jakarta Persistence AttributeConverter | Chuyển đổi Java ↔ JDBC, null, precision/scale, truy vấn và round-trip |
| Hibernate UserType, JavaType, JdbcType, BasicType | Bind/extract JDBC, dirty checking, equality/hash, SQL type, cache representation |
| Integrator, ServiceContributor, ServiceRegistry | Extension được phát hiện và đăng ký đúng trong mỗi SessionFactory |
| EventListenerRegistry, Hibernate event listener | Event đúng phase, đúng số lần, transaction rollback và thứ tự listener |
| Interceptor, StatementInspector | SQL được quan sát/chỉnh sửa đúng, không gây lặp hoặc thay đổi dữ liệu ngoài ý muốn |
| Custom Dialect, SQL function, type contributor | SQL sinh ra hợp lệ trên dialect và database thực tế |
| Filter, multi-tenancy, soft-delete | Điều kiện lọc được áp dụng ở đúng truy vấn và không rò dữ liệu giữa tenant |
| Identifier generator | Sinh khóa đúng khi insert đồng thời, rollback và nhiều node |
| Second-level cache, query cache | Cache hit/miss, invalidation và nhất quán giữa Session |
| Bytecode enhancement | Lazy loading, dirty tracking và association behavior khi class thực sự được enhance |
| Envers, Search, Spatial, Vector hoặc extension khác | Module, schema, driver và database extension được cài đúng, hành vi đọc/ghi hoạt động |

Không phải mọi extension đều là Hibernate SPI. `AttributeConverter` thuộc Jakarta Persistence và portable hơn. `UserType`, `Integrator`, `StatementInspector` và nhiều service registry contract là API riêng của Hibernate. Hãy xác định contract mà extension dựa vào trước khi chọn test.

### 1.1. Phân biệt API, SPI và internal implementation

Một package compile được không có nghĩa nó là API được hỗ trợ lâu dài.

- Ưu tiên contract công khai trong Javadoc và Integration Guide.
- Kiểm tra annotation trạng thái như `@Incubating` hoặc `@Internal` nếu có.
- Tránh phụ thuộc class trong package `org.hibernate.internal` hoặc chi tiết implementation không được tài liệu cam kết.
- Nếu extension bắt buộc dùng SPI, pin phiên bản Hibernate tương thích và chạy compatibility test khi nâng version.
- Không giả định extension compile với Hibernate 6 sẽ chạy nguyên trạng trên Hibernate 7.

Unit test có thể xác nhận thuật toán riêng của extension, nhưng chỉ integration test với Hibernate thật mới xác nhận việc bootstrap, đăng ký và gọi extension qua đúng lifecycle.

## 2. Lập ma trận tương thích trước khi viết test

Một tổ hợp triển khai không chỉ có một phiên bản Hibernate. Ít nhất cần ghi nhận:

- Java runtime/JDK.
- Spring Boot và Spring Framework nếu ứng dụng dùng Spring.
- Spring Data JPA.
- Hibernate ORM.
- Jakarta Persistence API.
- JDBC driver.
- Database engine và phiên bản.
- Migration tool và phiên bản.
- Extension artifact hoặc module đi kèm Hibernate.
- Cache provider, search engine hoặc database extension nếu có.

Ví dụ bảng quản lý:

| Thành phần | Phiên bản production | Phiên bản cần thử nâng cấp | Ghi chú |
|---|---|---|---|
| JDK | 21 | 25 | Cả compile và runtime |
| Spring Boot | Phiên bản BOM đang triển khai | BOM mục tiêu | Không tự ý override Hibernate |
| Hibernate ORM | Bản được BOM quản lý | Bản được hỗ trợ trong stack mới | Kiểm tra API/SPI thay đổi |
| Jakarta Persistence | Phiên bản do stack quản lý | Phiên bản tương ứng Hibernate | Tránh trộn namespace/API |
| JDBC driver | Driver đang dùng | Driver mục tiêu | Kiểm tra release notes |
| Database | Engine/version production | Version sẽ nâng cấp | Dùng cùng major/minor khi có thể |
| Extension | Artifact đang phát hành | Build candidate | Kiểm tra dependency transitive |

Không lấy phiên bản mới nhất của từng thư viện rồi ghép tùy ý. Hãy dùng compatibility matrix và dependency management của Spring Boot/Hibernate để chọn tổ hợp được hỗ trợ.

Tại thời điểm 09-11-2026, trang phát hành Hibernate ghi nhận Hibernate ORM 7.4.15.Final là bản stable mới nhất; dòng 7.4 tương thích với Java 17, 21, 25 hoặc 26 và Jakarta Persistence 3.2, đồng thời liệt kê Spring Boot 4.1 trong ma trận. Hibernate 6.6 vẫn là dòng limited-support và tương thích Spring Boot 3.4–3.5. Dòng 7.1 đã end-of-life. Đây là ví dụ cho thấy phải đọc trạng thái hỗ trợ của cả stack trước khi quyết định nâng cấp; dự án đang chạy Spring Boot 3 không nên chỉ đổi riêng hibernate-core sang 7.4. [Hibernate ORM releases and compatibility matrix](https://hibernate.org/orm/releases/).

### 2.1. Đọc đúng compatibility matrix

Khi kiểm tra một tổ hợp:

1. Xác nhận Hibernate hỗ trợ JDK đang chạy.
2. Xác nhận Hibernate implement đúng Jakarta Persistence version mà framework yêu cầu.
3. Kiểm tra Spring Boot/Spring Data JPA có quản lý và hỗ trợ dòng Hibernate đó không.
4. Kiểm tra extension module có cùng release train với hibernate-core không.
5. Kiểm tra JDBC driver hỗ trợ phiên bản database mục tiêu.
6. Kiểm tra database version nằm trong phạm vi dialect hỗ trợ.
7. Lưu kết quả thành matrix có thể chạy lại trong CI.

Nếu dùng Spring Boot BOM, không khai báo version Hibernate riêng chỉ để “thử nhanh” mà không cập nhật dependency liên quan. Dùng dependency tree để biết artifact thực tế được resolve.

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.hibernate,org.springframework.data,jakarta.persistence
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency hibernate-core --configuration runtimeClasspath
~~~

Kết quả phải cho biết version thực sự chạy ở runtime, không chỉ version ghi trong file build.

### 2.2. Chọn các điểm trong ma trận

Không nhất thiết chạy mọi hoán vị JDK × Hibernate × database nếu chi phí quá lớn. Có thể chia:

- **Minimum supported:** tổ hợp cũ nhất mà ứng dụng cam kết hỗ trợ.
- **Production exact:** đúng engine, driver và version đang chạy thật.
- **Upgrade candidate:** tổ hợp dự kiến nâng cấp.
- **Critical combinations:** những tổ hợp có tính năng extension đặc thù, ví dụ PostgreSQL JSONB hoặc MySQL generated column.
- **Nightly matrix:** mở rộng các tổ hợp còn lại để phát hiện regression sớm.

Không được bỏ test trên production database chỉ vì H2 và một database khác đã pass.

## 3. Database dialect quyết định điều gì?

Dialect cung cấp thông tin về đặc điểm database và chuyển biểu thức Hibernate thành SQL phù hợp. Cùng một mapping có thể sinh kiểu cột, function, pagination, locking hoặc DDL khác nhau trên PostgreSQL, MySQL, Oracle và SQL Server.

Với Hibernate ORM 7.4, dialect guide công bố các mức database tối thiểu tương ứng, ví dụ PostgreSQL 14, MySQL 8.0, MariaDB 10.6, Oracle 19, SQL Server 12 và H2 2.1.214. Đây là mức tối thiểu của dialect trong tài liệu, không phải cam kết rằng mọi tính năng ứng dụng đều hoạt động trên mọi bản database ở mức đó. [Hibernate Dialects](https://docs.hibernate.org/stable/core/dialect/).

Đối với third-party dialect, trách nhiệm tương thích thuộc nhà phát triển dialect; Hibernate không chạy CI chính thức cho mọi dialect bên ngoài. Cần kiểm tra tài liệu và test suite của chính dialect đó.

### 3.1. Vì sao H2 không thay thế database mục tiêu?

H2 hữu ích vì khởi động nhanh và tiện cho repository test. Tuy nhiên, nó có thể khác database production ở:

- Kiểu dữ liệu như JSON, ARRAY, UUID, enum, spatial hoặc vector.
- Cách xử lý precision, scale, timezone và collation.
- Cú pháp DDL, generated column, partial index và check constraint.
- Native query, stored procedure và SQL function.
- Pagination, locking, isolation và deadlock.
- Sequence, identity, generated key và batch statement.
- Transactional DDL, trigger và foreign key behavior.
- Optimizer và execution plan.

Chế độ compatibility của H2 cũng không biến H2 thành PostgreSQL/MySQL thật. Dùng H2 cho test nhanh; dùng đúng database engine cho tính năng phụ thuộc dialect.

## 4. Chiến lược kiểm thử theo nhiều lớp

Không đưa mọi kiểm tra vào một loại integration test. Tách theo chi phí và loại lỗi cần phát hiện.

### 4.1. Unit test cho logic thuần

Dùng unit test để kiểm tra những phần không cần Hibernate hoặc database:

- Quy tắc chuẩn hóa dữ liệu trong converter.
- Validate cấu hình extension.
- Hàm tạo tên cột hoặc biểu thức thuần Java.
- Mapping từ event sang domain event.
- Quy tắc quyết định tenant/filter.
- Xử lý lỗi và fallback trong code extension.

Unit test phải nhanh, không mở SessionFactory nếu không cần. Nó không chứng minh JDBC binding hoặc SQL do dialect sinh ra là đúng.

### 4.2. Bootstrap test cho đăng ký extension

Tạo Hibernate bootstrap hoặc Spring application context với extension thực tế và xác nhận:

- Extension được phát hiện.
- Không có lỗi class loading hoặc service loading.
- Đăng ký xảy ra đúng một lần cho mỗi SessionFactory.
- Mapping metadata chứa type/contributor mong muốn.
- Listener hoặc interceptor thực sự được gọi.
- Đóng SessionFactory giải phóng resource và không để listener cũ tồn tại.

Nếu extension được đăng ký bằng property, service loader, Integrator hoặc Spring customizer, test phải dùng đúng đường đăng ký production. Tạo instance trực tiếp trong unit test không xác nhận cấu hình bootstrap.

### 4.3. Integration test trên database thật

Dùng database engine/version gần production để kiểm tra:

- Insert, update, select, delete và round-trip.
- SQL type và giá trị lưu thực tế.
- Query predicate, sort, pagination và aggregate.
- Flush/clear/reload.
- Transaction commit/rollback.
- Concurrency và locking.
- Index, constraint, trigger và native function.
- Migration schema từ phiên bản trước.

Đây là lớp test quyết định tính tương thích database.

### 4.4. Migration test

Chạy migration trên schema rỗng và schema cũ có dữ liệu đại diện:

1. Tạo schema theo phiên bản release trước.
2. Nạp dữ liệu mẫu có cả null, biên precision, dữ liệu cũ và quan hệ.
3. Chạy Flyway/Liquibase migration đến version mới.
4. Khởi tạo Hibernate với schema đã migrate.
5. Dùng `ddl-auto=validate` để kiểm tra mapping/schema.
6. Đọc lại dữ liệu, kiểm tra constraint/index và tiếp tục ghi dữ liệu mới.

Chỉ dùng `create-drop` trong test mapping nhanh không đủ để chứng minh migration production an toàn.

## 5. Dùng Testcontainers với đúng database engine

Testcontainers tạo database tạm trong container, cho phép integration test chạy trên engine thật mà không yêu cầu mỗi developer tự cài server riêng.

Với JUnit 5, cần module JUnit Jupiter và module database tương ứng. Testcontainers hỗ trợ khởi tạo database container bằng annotation hoặc JDBC URL đặc biệt. [Testcontainers JDBC support](https://java.testcontainers.org/modules/databases/jdbc/).

### 5.1. Dependencies

Ví dụ Gradle; dùng Testcontainers BOM để đồng bộ version các module:

~~~groovy
dependencies {
    testImplementation platform(
        "org.testcontainers:testcontainers-bom:${testcontainersVersion}"
    )
    testImplementation "org.testcontainers:junit-jupiter"
    testImplementation "org.testcontainers:postgresql"
}
~~~

Khai báo version BOM theo version đã được dự án lựa chọn và kiểm tra tương thích JDK/CI. Không để từng module Testcontainers tự resolve một version khác nhau.

### 5.2. Cấu hình Spring Boot test

Ví dụ dưới đây cố định PostgreSQL image để kết quả có thể tái lập. Trong dự án thật, thay image tag bằng đúng major/minor đang chạy production hoặc phiên bản cần kiểm thử nâng cấp.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@DataJpaTest
@Testcontainers
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
class HibernateExtensionPostgresTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16.4")
                    .withDatabaseName("app")
                    .withUsername("test")
                    .withPassword("test");

    @DynamicPropertySource
    static void configureDatabase(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    private EntityManager entityManager;

    @Test
    void databaseIsTheTargetPostgresEngine() {
        Object product = entityManager
                .createNativeQuery("select version()")
                .getSingleResult();

        assertThat(product.toString()).contains("PostgreSQL");
    }
}
~~~

Ví dụ dùng `@DataJpaTest` để khởi tạo JPA slice. `@AutoConfigureTestDatabase(replace = NONE)` ngăn Spring thay datasource container bằng embedded database. `@DynamicPropertySource` cung cấp JDBC URL và credentials sau khi container khởi động.

Test trên chỉ chứng minh kết nối tới PostgreSQL. Các test tiếp theo phải gọi mapping hoặc extension cụ thể và xác nhận kết quả nghiệp vụ.

### 5.3. Cài database extension cần thiết

Nếu extension cần PostgreSQL extension như PostGIS, pgvector hoặc function riêng, image database phải cài đúng extension và version. Có thể dùng image đã chuẩn bị hoặc init script chạy khi container tạo database.

Không chỉ kiểm tra `CREATE EXTENSION` thành công. Cần xác nhận:

- Extension database đã được cài và bật.
- Version extension đúng với production.
- Kiểu dữ liệu/operator/function có sẵn.
- JDBC driver đọc/ghi được kiểu dữ liệu.
- Hibernate mapping và query thực sự sử dụng được feature.

## 6. Ví dụ kiểm thử mapping tùy biến bằng AttributeConverter

Ví dụ dùng `Money` làm value object và converter sang `NUMERIC`. Đây là extension point của Jakarta Persistence; kiểm thử trên PostgreSQL giúp phát hiện khác biệt về precision/scale và JDBC representation.

Value object:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public record Money(BigDecimal amount) {

    public Money {
        Objects.requireNonNull(amount, "amount is required");
        amount = amount.setScale(2, RoundingMode.UNNECESSARY);
    }
}
~~~

Converter:

~~~java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;
import java.math.BigDecimal;

@Converter
public class MoneyConverter
        implements AttributeConverter<Money, BigDecimal> {

    @Override
    public BigDecimal convertToDatabaseColumn(Money money) {
        return money == null ? null : money.amount();
    }

    @Override
    public Money convertToEntityAttribute(BigDecimal value) {
        return value == null ? null : new Money(value);
    }
}
~~~

Entity:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "product_price")
public class ProductPrice {

    @Id
    private Long id;

    @Convert(converter = MoneyConverter.class)
    @Column(nullable = false, precision = 19, scale = 2)
    private Money price;

    protected ProductPrice() {
    }

    public ProductPrice(Long id, Money price) {
        this.id = id;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public Money getPrice() {
        return price;
    }
}
~~~

Thêm test method sau vào `HibernateExtensionPostgresTest` ở phần trước:

~~~java
@Test
void persistsAndReloadsMoneyValue() {
    entityManager.persist(
            new ProductPrice(
                    1L,
                    new Money(new BigDecimal("12.30"))
            )
    );

    entityManager.flush();
    entityManager.clear();

    ProductPrice loaded =
            entityManager.find(ProductPrice.class, 1L);

    assertThat(loaded.getPrice().amount())
            .isEqualByComparingTo("12.30");
}
~~~

`flush()` buộc Hibernate gửi INSERT; `clear()` loại entity khỏi persistence context; `find()` buộc provider đọc lại giá trị qua JDBC và chạy converter theo chiều ngược. Test này chạy trên cùng PostgreSQL container đã cấu hình ở phần trước.

### 6.1. Những ca cần thêm cho converter/type

Round-trip một giá trị bình thường chưa đủ. Thêm test cho:

- Giá trị null nếu mapping cho phép.
- Giá trị âm, zero và giá trị sát giới hạn precision.
- Scale lớn hơn scale của cột.
- Giá trị không thể biểu diễn theo rounding policy.
- Equality/hashCode của value object.
- Predicate so sánh, sort và aggregate nếu ứng dụng query theo thuộc tính.
- Dirty checking khi thay đổi value object.
- Second-level cache nếu entity được cache.
- Native SQL hoặc stored procedure nếu extension cần tương tác với chúng.

Nếu converter chủ động từ chối scale không hợp lệ, test phải xác nhận exception của converter. Nếu database từ chối precision, test phải xác nhận lỗi database được chuyển lên đúng tầng.

## 7. Kiểm thử Hibernate UserType và type system

`UserType` hoặc type contributor thường tác động sâu hơn AttributeConverter vì extension có thể điều khiển JDBC type, binding, extraction, equality, mutability và cache representation.

Không chỉ test hai method convert. Một bộ test type cần bao gồm:

1. **Bootstrap:** mapping có đăng ký đúng type không?
2. **DDL:** Hibernate tạo hoặc validate đúng SQL column type không?
3. **Bind:** giá trị Java được bind bằng JDBC type nào?
4. **Extract:** đọc ResultSet trả về object có đúng không?
5. **Null:** JDBC null được xử lý đúng không?
6. **Equality:** provider có nhận ra hai giá trị tương đương không?
7. **Dirty checking:** thay đổi thật có tạo UPDATE, giá trị không đổi có tránh UPDATE thừa không?
8. **Mutability:** snapshot có bị thay đổi ngoài ý muốn khi object mutable được chỉnh sửa không?
9. **Cache:** serialize/deserialize và cache key có nhất quán không?
10. **Query:** parameter binding, predicate, ordering và projection có hoạt động không?

Đặc biệt kiểm thử `equals`, `hashCode`, deep copy và disassemble/assemble nếu type có hỗ trợ cache. Một type có thể round-trip đúng nhưng dirty checking sai, khiến Hibernate bỏ sót update hoặc phát update không cần thiết.

### 7.1. Kiểm tra SQL type và dữ liệu ở database

Với mỗi database mục tiêu, xác nhận cả metadata cột và dữ liệu lưu. Không suy ra SQL type chỉ từ Java class.

Có thể dùng native query hoặc JDBC metadata để kiểm tra:

- Column type thực tế.
- Precision, scale, length và nullability.
- Binary/text encoding.
- JSON/ARRAY/UUID representation.
- Timezone behavior.
- Default value và generated expression.

Không assert toàn bộ chuỗi DDL nếu không cần. DDL có thể đổi cách format giữa Hibernate version mà schema semantics vẫn tương đương. Assert các thuộc tính schema mà ứng dụng phụ thuộc.

## 8. Kiểm thử Integrator, ServiceContributor và EventListener

Các extension được đăng ký qua Integrator, ServiceContributor hoặc registry phải được kiểm tra cả lúc bootstrap và lúc chạy.

### 8.1. Kiểm tra đăng ký

Test cần khởi tạo SessionFactory bằng cấu hình production và xác nhận extension được gọi. Tránh tạo listener thủ công trong test rồi gọi trực tiếp method vì cách đó bỏ qua registry.

Các câu hỏi cần trả lời:

- Integrator có được phát hiện từ service loader hoặc cấu hình không?
- Service có được thêm vào đúng registry?
- Listener có được đăng ký trên đúng event type?
- Mỗi SessionFactory có đúng một registration không?
- Khi đóng SessionFactory, resource của extension có được giải phóng không?
- Khi context khởi động lại, có còn listener từ context cũ không?

### 8.2. Kiểm tra event lifecycle

Với listener trước/sau insert, update hoặc delete, tạo entity thật và thực hiện transaction thật:

- Event nào được phát ra?
- Callback chạy một hay nhiều lần?
- Callback chạy trước hay sau SQL/flush?
- Rollback có để lại side effect ngoài transaction không?
- Batch insert/update có tạo số callback như dự kiến không?
- Bulk HQL/Criteria DML có bỏ qua entity lifecycle không?

Không giả định bulk update/delete gọi cùng lifecycle event như thao tác `EntityManager.persist()` hoặc `remove()` trên từng entity. Test phải phản ánh đúng loại thao tác ứng dụng sử dụng.

### 8.3. Kiểm tra listener thread-safe

Một SessionFactory có thể phục vụ nhiều thread. Nếu listener giữ mutable state, test đồng thời phải xác nhận:

- Không dùng chung EntityManager hoặc Session giữa thread.
- Không lưu dữ liệu theo request trong singleton field.
- Counter/registry dùng cơ chế đồng bộ phù hợp.
- Không phát trùng event khi transaction retry.
- Không rò dữ liệu giữa tenant hoặc session.

## 9. Kiểm thử Interceptor và StatementInspector

Interceptor và StatementInspector thường dùng để audit, quan sát hoặc điều chỉnh SQL.

Test cần xác nhận:

- SQL được quan sát đúng loại thao tác.
- Parameter không bị log lộ dữ liệu nhạy cảm.
- SQL sửa đổi vẫn hợp lệ trên từng dialect mục tiêu.
- Không thêm điều kiện hai lần.
- Không làm sai query cache hoặc batch behavior.
- Không gây recursion khi extension tự thực hiện query.
- Không làm thay đổi thứ tự hoặc số lượng bind parameter.
- Extension không giữ Session/Connection lâu hơn transaction.

Nếu chỉ cần đo SQL, ưu tiên ghi nhận statement trong test và assert thuộc tính cần thiết như có predicate tenant hoặc số lần SELECT. Tránh so sánh nguyên văn toàn bộ SQL vì quote, alias, whitespace và cách render có thể đổi giữa dialect hoặc Hibernate version.

Nếu extension có nhiệm vụ sửa SQL, phải chạy query đã sửa trên database thật. Unit test chuỗi SQL không chứng minh database chấp nhận cú pháp đó.

## 10. Kiểm thử custom Dialect và SQL function

Custom Dialect hoặc function contributor cần được test trên database mà nó tuyên bố hỗ trợ.

Các bước:

1. Bootstrap Hibernate với đúng dialect/registration.
2. Kiểm tra function có được nhận diện trong HQL/Criteria.
3. Thực thi truy vấn sử dụng function trên database thật.
4. Xác nhận kết quả, null semantics và kiểu dữ liệu trả về.
5. Kiểm tra function với tham số bind, Unicode và giá trị biên.
6. Kiểm tra SQL được sinh ở từng Hibernate version mục tiêu.
7. Xác nhận database version thấp nhất trong support range cũng thực thi được.

Không chỉ assert function đã được đăng ký trong metadata. Function có thể đăng ký thành công nhưng SQL translator tạo cú pháp database version đó không hỗ trợ.

Nếu function dùng cú pháp PostgreSQL riêng, test trên H2 không chứng minh nó đúng. Nếu dialect là third-party, chạy test suite của vendor dialect và ghi rõ giới hạn support.

## 11. Kiểm thử Filter, tenant và soft delete

Filter và tenant extension có rủi ro rò dữ liệu cao. Hãy kiểm thử cả query đơn giản lẫn những đường truy cập ít phổ biến:

- `findById`, `findAll` và derived query.
- JPQL/HQL và Criteria query.
- Lazy collection loading.
- EntityGraph và fetch join.
- Native query.
- Bulk update/delete.
- Cache hit từ Session hoặc second-level cache.
- Session mở trước khi tenant context thay đổi.
- Background job và async thread.

Không mặc định Hibernate filter áp dụng cho mọi native SQL hoặc bulk operation. Kiểm tra rõ đường truy vấn thực tế. Nếu tenant isolation là ranh giới bảo mật, cân nhắc database row-level security hoặc constraint bổ sung bên cạnh filter ở ORM.

Với soft delete, test:

- Entity bị đánh dấu xóa có còn xuất hiện trong query thường không?
- Có thể truy cập bằng query quản trị không?
- Unique constraint có xử lý record đã xóa đúng không?
- Association và cascade có hành vi mong đợi không?
- Native SQL có bỏ qua soft-delete predicate không?
- Restore có hoạt động và xử lý conflict không?

## 12. Kiểm thử Identifier Generator và concurrency

Generator dùng sequence, identity, table hoặc custom algorithm phải được kiểm thử trên database mục tiêu.

Các ca quan trọng:

- Insert một entity và xác nhận ID được gán.
- Insert nhiều entity trong cùng transaction.
- Insert đồng thời từ nhiều transaction/thread.
- Rollback sau khi lấy ID.
- Restart application hoặc tạo SessionFactory mới.
- Batch insert nếu ứng dụng bật batching.
- Sequence allocation size và database sequence increment.
- Nhiều application instance cùng dùng một database.

Sequence có thể tạo khoảng trống sau rollback; không viết test giả định ID phải liên tục nếu generator/database không bảo đảm điều đó.

Với custom generator, xác nhận không sinh trùng ID dưới concurrency. Dùng unique constraint của database làm lớp bảo vệ cuối cùng; unit test tuần tự không đủ để chứng minh tính duy nhất trong hệ thống nhiều node.

## 13. Kiểm thử cache và bytecode enhancement

### 13.1. Second-level cache và query cache

Nếu extension tương tác với cache, test qua nhiều Session khác nhau:

1. Session A đọc entity và làm cache warm.
2. Session B cập nhật hoặc xóa entity.
3. Session C đọc lại và phải thấy trạng thái mới.
4. Kiểm tra query cache invalidation khi bảng liên quan thay đổi.
5. Kiểm tra rollback không làm cache phản ánh dữ liệu chưa commit.
6. Kiểm tra eviction, expiry và serialization nếu cache provider yêu cầu.

Test với cache provider thật mà production sử dụng. Cache in-memory giả lập không chứng minh cluster invalidation hoặc serialization giữa node.

### 13.2. Bytecode enhancement

Nếu extension phụ thuộc enhancement, test class đã được build bằng đúng enhancement plugin và options production. Test chạy trên class chưa enhance sẽ không kiểm tra được dirty tracking hoặc lazy loading dựa trên enhancement.

Xác nhận:

- Build thực sự chạy enhancement goal/task.
- Entity có enhancement marker/behavior tương ứng.
- Lazy attribute chỉ tải khi được truy cập.
- Dirty tracking nhận ra thay đổi field.
- Association hai chiều không bị đồng bộ sai.
- Enhancement không làm hỏng proxy, serialization hoặc test runtime.

Không chạy enhancement hai lần với options khác nhau. Kiểm tra migration guide khi nâng Hibernate vì option/plugin behavior có thể thay đổi.

## 14. Kiểm thử migration và schema compatibility

Extension có thể yêu cầu cột, index, function, sequence hoặc database extension riêng. Schema test phải phản ánh quá trình nâng cấp thực tế.

### 14.1. Kiểm tra schema mới

- Chạy migration từ database rỗng.
- Khởi động Hibernate với schema đã tạo.
- Đặt `hibernate.hbm2ddl.auto=validate` hoặc cấu hình tương đương qua Spring Boot.
- Kiểm tra kiểu cột, nullability, precision, index, constraint, sequence và function.
- Chạy CRUD/query dùng extension.

### 14.2. Kiểm tra nâng cấp schema cũ

Tạo database bằng migration của release trước, nạp dữ liệu đại diện rồi chạy migration mới. Kiểm tra dữ liệu cũ không bị cắt, đổi timezone hoặc mất precision.

Nếu extension đổi representation, cần test chuyển đổi hai chiều:

- Dữ liệu cũ có đọc được trong code mới không?
- Migration có giữ được semantics không?
- Có thể rollback application version trong giai đoạn deployment không?
- Có cần backfill theo batch không?
- Code mới có tương thích với schema trong thời gian rolling deployment không?

Không dùng Hibernate schema auto-update làm cơ chế migration production thay cho Flyway/Liquibase đã được quản lý.

## 15. Đo hiệu năng và kiểm tra query regression

Một extension đúng về kết quả vẫn có thể gây regression:

- Thêm query cho mỗi entity.
- Tắt batching.
- Làm query cache luôn miss.
- Tạo JOIN hoặc cast khiến index không dùng được.
- Gọi reflection/serialization trên mỗi row.
- Giữ Session/Connection quá lâu.

Các phép đo hữu ích:

- Số SQL statement cho một use case.
- Số lần flush và batch size thực tế.
- Query count khi truy cập association.
- Thời gian bootstrap SessionFactory.
- Heap allocation khi đọc batch lớn.
- Execution plan và index usage.
- P95/P99 của đường truy vấn quan trọng.

Dùng Hibernate Statistics hoặc datasource instrumentation trong test. Đối với query nhạy hiệu năng, chạy `EXPLAIN` trên database mục tiêu với dữ liệu có cardinality gần production. Không dùng vài hàng fixture rồi kết luận index hoặc optimizer behavior sẽ giống production.

## 16. Tổ chức CI cho version và database matrix

Một pipeline thực tế có thể chia:

| Job | Nội dung | Tần suất |
|---|---|---|
| Compile/unit | Compile extension trên JDK và Hibernate API mục tiêu; unit test logic thuần | Mỗi pull request |
| Bootstrap | Khởi tạo SessionFactory, xác nhận extension registration | Mỗi pull request |
| Fast JPA | Test mapping/repository trên database nhẹ | Mỗi pull request |
| Target DB | Testcontainers với engine/version production | Mỗi pull request hoặc nhánh chính |
| Compatibility matrix | Các Hibernate/JDK/database combo được hỗ trợ | Nightly hoặc release |
| Migration | Nâng schema từ bản release trước | Mỗi pull request ảnh hưởng schema |
| Performance smoke | Query count, batch, regression lớn | Nightly/release |
| Upgrade candidate | Hibernate/JDBC/database version mới dự kiến triển khai | Nhánh nâng cấp riêng |

Khi extension dùng Hibernate SPI, phải compile và chạy test với từng Hibernate line mà ứng dụng cam kết hỗ trợ. Chỉ chạy test trên một version mới nhất không chứng minh extension tương thích với version cũ hơn.

Nếu extension chỉ hỗ trợ một dòng Hibernate, ghi rõ range đó trong dependency metadata, tài liệu và release note. Fail fast khi gặp version không được hỗ trợ sẽ dễ chẩn đoán hơn lỗi runtime khó hiểu.

## 17. Cách chẩn đoán test fail

| Triệu chứng | Nguyên nhân thường gặp | Bước kiểm tra |
|---|---|---|
| Extension không được gọi | Chưa đăng ký hoặc đăng ký sai registry | Kiểm tra bootstrap log, service loader và SessionFactory |
| Chạy với H2 nhưng fail PostgreSQL | SQL/type/function khác dialect | Chạy test trên đúng PostgreSQL image và driver |
| Compile với Hibernate mới nhưng runtime fail | SPI/API không tương thích hoặc dependency conflict | Kiểm tra dependency tree và classpath runtime |
| Giá trị đọc khác giá trị ghi | Converter/type binding hoặc precision/scale | Kiểm tra JDBC type, native value và round-trip |
| Dirty checking bỏ sót update | Equality, snapshot hoặc mutability sai | Test thay đổi object mutable và flush |
| SQL bị thêm điều kiện hai lần | Interceptor/listener chạy lặp | Kiểm tra registration count và lifecycle |
| Tenant khác đọc được dữ liệu | Filter không áp dụng cho một query path/cache | Test native, bulk, collection loading và cache |
| Test pass nhưng migration fail | Chỉ dùng create-drop, không nâng schema cũ | Chạy migration từ fixture schema release trước |
| ID trùng dưới tải | Generator không thread-safe hoặc allocation sai | Test nhiều transaction và unique constraint |
| Query chậm sau khi thêm extension | Thêm SQL, cast, JOIN hoặc tắt batching | Đếm statement và xem execution plan |
| Cache trả dữ liệu cũ | Invalidation/serialization sai | Test qua nhiều Session và node/provider thật |
| Upgrade gây lỗi mapping | API, default hoặc DDL thay đổi | Đọc migration guide của từng version |

Khi test fail, lưu dữ liệu đủ để tái hiện: Hibernate version, JDBC driver version, database image tag, JDK, dialect, schema migration version, SQL đã sinh và exception chain. Không chỉ lưu stack trace không có môi trường đi kèm.

## 18. Checklist trước khi phát hành extension

- [ ] Đã xác định extension dựa trên Jakarta Persistence API hay Hibernate-specific API/SPI.
- [ ] Đã kiểm tra API có trạng thái incubating/internal hay không.
- [ ] Có compatibility matrix cho JDK, Spring Boot, Spring Data JPA, Hibernate, JDBC driver và database.
- [ ] Version của Hibernate module được đồng bộ với hibernate-core.
- [ ] Đã kiểm tra dependency tree runtime.
- [ ] Extension được bootstrap và đăng ký đúng như production.
- [ ] Unit test bao phủ logic thuần, null và dữ liệu biên.
- [ ] Integration test chạy trên database engine/version mục tiêu.
- [ ] Testcontainers dùng image tag cố định, không dùng `latest`.
- [ ] H2 chỉ được dùng cho test nhanh, không thay thế test dialect thật.
- [ ] Type mapping được test bind, extract, round-trip, equality và dirty checking.
- [ ] Event listener/interceptor được test phase, số lần gọi và rollback.
- [ ] Custom Dialect/function được thực thi trên database thật.
- [ ] Filter/tenant được test qua JPQL, native, collection, bulk và cache path.
- [ ] Generator được test với transaction đồng thời.
- [ ] Cache được test qua nhiều Session và provider production.
- [ ] Bytecode enhancement được bật trong test nếu production phụ thuộc nó.
- [ ] Migration được chạy từ schema rỗng và schema release trước.
- [ ] `ddl-auto=validate` xác nhận mapping phù hợp schema đã migrate.
- [ ] Query count, batching và execution plan không có regression đáng kể.
- [ ] CI có job cho minimum supported, production exact và upgrade candidate.
- [ ] Release note nêu rõ Hibernate/database version được hỗ trợ.

## 19. Tài liệu tham khảo

- [Hibernate ORM Releases and Compatibility Matrix](https://hibernate.org/orm/releases/) — trạng thái release, JDK, Jakarta Persistence, Spring Boot và các dòng Hibernate được hỗ trợ.
- [Hibernate ORM 7.4 Documentation](https://hibernate.org/orm/documentation/7.4/) — User Guide, Integration Guide, Migration Guide và Javadoc theo đúng dòng version.
- [Hibernate ORM Integration Guide](https://docs.hibernate.org/stable/core/integrationguide/html_single/) — ServiceRegistry, Integrator và các integration point dành cho extension developer.
- [Hibernate ORM User Guide](https://docs.hibernate.org/stable/core/userguide/html_single/) — mapping, type system, fetching, cache, schema và query behavior.
- [Hibernate Dialects](https://docs.hibernate.org/stable/core/dialect/) — dialect được hỗ trợ và database version tối thiểu.
- [Hibernate Migration Guides](https://hibernate.org/orm/documentation/migrate/) — thay đổi API/SPI, default và DDL theo từng dòng version.
- [Testcontainers JDBC Support](https://java.testcontainers.org/modules/databases/jdbc/) — database container và cách kết nối JDBC trong integration test.

Một extension chỉ thực sự sẵn sàng khi nó được đăng ký đúng, giữ đúng semantics trên Hibernate mục tiêu và chạy được trên database production. Hãy kiểm thử logic thuần ở unit test, bootstrap ở integration test và dùng Testcontainers với đúng engine/version để xác nhận JDBC, dialect, schema, transaction và extension behavior. Khi nâng Hibernate hoặc database, chạy lại compatibility matrix và migration test trước khi phát hành.
