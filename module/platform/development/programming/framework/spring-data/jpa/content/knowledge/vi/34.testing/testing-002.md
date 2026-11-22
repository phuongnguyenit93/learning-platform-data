# Phạm vi tự cấu hình của @DataJpaTest

## 1. @DataJpaTest dùng để làm gì?

@DataJpaTest là annotation kiểm thử dạng slice của Spring Boot dành cho tầng persistence. Nó tạo một Spring ApplicationContext tập trung vào các thành phần liên quan đến JPA, giúp kiểm thử entity mapping, Spring Data repositories, câu truy vấn và hành vi persistence mà không cần khởi động toàn bộ ứng dụng.

Một bài kiểm thử repository thường chỉ cần:

- Entity và mapping quan hệ.
- EntityManager và hạ tầng JPA.
- Spring Data JPA repositories.
- DataSource và transaction manager.
- Các cấu hình cần thiết để tạo schema và thực thi SQL.

@DataJpaTest tự cấu hình các thành phần phù hợp với phạm vi đó. Các thành phần ở tầng web, controller, service và những bean ứng dụng thông thường không tự động được nạp như khi dùng @SpringBootTest.

Đây là khác biệt cốt lõi giữa slice test và full application integration test:

| Tiêu chí | @DataJpaTest | @SpringBootTest |
|---|---|---|
| Phạm vi ApplicationContext | Tập trung vào persistence/JPA | Toàn bộ ứng dụng theo cấu hình |
| Repository và EntityManager | Tự cấu hình | Có nếu ứng dụng cấu hình chúng |
| Controller, service thông thường | Không tự động nạp | Thường được nạp |
| Tốc độ khởi tạo | Thường nhanh hơn | Thường chậm hơn |
| Mục tiêu | Kiểm tra mapping, repository, query, persistence | Kiểm tra tích hợp nhiều tầng hoặc luồng ứng dụng hoàn chỉnh |
| Transaction test | Mặc định có transaction và rollback sau test | Phụ thuộc cấu hình test và transaction |

Hãy chọn @DataJpaTest khi câu hỏi cần trả lời thuộc tầng dữ liệu. Nếu cần kiểm tra controller gọi service rồi repository, security filter, HTTP serialization hoặc toàn bộ wiring của ứng dụng, hãy dùng @SpringBootTest hoặc loại test phù hợp hơn.

## 2. Những gì @DataJpaTest tự cấu hình

Trong một ứng dụng Spring Boot có JPA, @DataJpaTest thường thiết lập các thành phần sau:

1. **Entity scanning:** tìm các lớp entity trong phạm vi cấu hình ứng dụng.
2. **JPA infrastructure:** cấu hình EntityManagerFactory và các thành phần JPA cần thiết.
3. **Spring Data repositories:** phát hiện và tạo bean cho repository phù hợp.
4. **DataSource:** tạo hoặc sử dụng DataSource theo cấu hình test.
5. **Transaction support:** cấu hình transaction manager để test có thể chạy trong transaction.
6. **TestEntityManager:** cung cấp tiện ích thao tác entity dành cho bài test khi hạ tầng JPA phù hợp.
7. **Database initialization/auto-configuration:** áp dụng các cấu hình database và JPA liên quan trong phạm vi test slice.

Annotation này được xây dựng từ nhiều annotation cấu hình test của Spring Boot. Nó giới hạn component scanning và auto-configuration theo mục đích persistence. Vì vậy, không nên kỳ vọng mọi bean có trong ứng dụng production đều xuất hiện trong context của test.

### 2.1. Entity và repository được phát hiện

Ví dụ ứng dụng có entity Product và repository ProductRepository:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;
    private String sku;

    protected Product() {
    }

    public Product(String name, String sku) {
        this.name = name;
        this.sku = sku;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getSku() {
        return sku;
    }
}
~~~

~~~java
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, Long> {
    Optional<Product> findBySku(String sku);
}
~~~

Bài test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class ProductRepositoryTest {
    @Autowired
    private ProductRepository products;

    @Test
    void findsProductBySku() {
        products.save(new Product("Keyboard", "KB-01"));

        var result = products.findBySku("KB-01");

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().getName()).isEqualTo("Keyboard");
    }
}
~~~

Spring Boot tạo context cho JPA test, inject repository và cho phép kiểm tra truy vấn theo quy ước tên phương thức. Đây là ví dụ minh họa các lớp thuộc cùng ứng dụng; entity và repository phải nằm trong phạm vi scan của cấu hình test.

## 3. Transaction và rollback mặc định

@DataJpaTest được cấu hình để mỗi test method chạy trong transaction. Mặc định, transaction này được rollback khi test kết thúc. Vì vậy, dữ liệu tạo trong một test không tồn tại để ảnh hưởng đến test tiếp theo.

Ví dụ:

~~~java
@DataJpaTest
class ProductRepositoryTest {
    @Autowired
    private ProductRepository products;

    @Test
    void savesProduct() {
        Product product = products.save(new Product("Mouse", "MS-01"));

        assertThat(product.getId()).isNotNull();
        assertThat(products.findBySku("MS-01")).isPresent();
    }
}
~~~

Khi test hoàn tất, Spring Test rollback transaction. Không cần tự xóa dữ liệu bằng repository trong mỗi test chỉ để dọn dữ liệu được tạo trong transaction đó.

Một số lưu ý:

- Rollback áp dụng cho transaction test do Spring quản lý. Nếu test tự mở transaction độc lập hoặc thao tác ngoài transaction đó, dữ liệu có thể không được rollback cùng test.
- Nếu gọi dịch vụ dùng propagation REQUIRES_NEW, transaction bên trong có thể commit độc lập; cần hiểu rõ ranh giới transaction trước khi dùng.
- @Commit hoặc @Rollback(false) có thể thay đổi hành vi mặc định. Chỉ dùng khi test thật sự cần dữ liệu được commit.
- Rollback không hoàn tác mọi tác động ngoài database, chẳng hạn gửi message, gọi HTTP hoặc ghi file. Slice test thường không nạp những thành phần này, nhưng test tự gọi chúng vẫn phải tự quản lý.

### 3.1. Flush để kiểm tra lỗi ở database

save() có thể chỉ đưa entity vào persistence context. SQL có thể chưa được gửi ngay đến database. Nếu muốn chắc chắn câu lệnh INSERT hoặc constraint được kiểm tra trong test, hãy flush:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class ProductPersistenceTest {
    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private ProductRepository products;

    @Test
    void persistsAndReloadsProduct() {
        Product saved = entityManager.persistAndFlush(
                new Product("Monitor", "MN-01")
        );

        Long id = saved.getId();

        entityManager.clear();

        Product reloaded = products.findById(id).orElseThrow();

        assertThat(reloaded.getName()).isEqualTo("Monitor");
    }
}
~~~

persistAndFlush() lưu entity và buộc đồng bộ SQL xuống database. clear() xóa các entity đang được quản lý khỏi persistence context. Lần findById() sau đó cần tải entity lại, giúp test kiểm tra dữ liệu đã được ghi và đọc từ persistence layer thay vì chỉ kiểm tra object còn nằm trong first-level cache.

Flush không phải commit. Transaction test vẫn có thể rollback khi method kết thúc.

## 4. Database mặc định và cách giữ database đã cấu hình

Một đặc điểm quan trọng của @DataJpaTest là khả năng dùng embedded database cho test nếu có thư viện phù hợp trên classpath. Cấu hình test database có thể thay thế DataSource đang được ứng dụng cấu hình. Hành vi mặc định và cách nhận diện database test có thể thay đổi theo phiên bản Spring Boot.

Điều này tiện cho repository test nhanh, nhưng có thể gây khác biệt nếu production dùng PostgreSQL, MySQL, Oracle hoặc SQL Server. SQL dialect, kiểu dữ liệu, sequence, locking, constraint và hành vi transaction không phải lúc nào cũng giống H2.

Nếu muốn dùng DataSource đã cấu hình, có thể khai báo rõ:

~~~java
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class ProductRepositoryIntegrationTest {
    // Tests use the configured DataSource.
}
~~~

Replace.NONE yêu cầu Spring Boot không thay DataSource bằng embedded database. Khi đó, test cần có cấu hình kết nối hợp lệ, database sẵn sàng và schema được chuẩn bị theo cách phù hợp.

Với Testcontainers, có thể khởi tạo database container cho integration test và cung cấp thông tin kết nối qua DynamicPropertySource hoặc cơ chế ServiceConnection của phiên bản Spring Boot tương ứng. Nếu giữ DataSource do container cung cấp, hãy cấu hình replace = NONE khi cần tránh test database auto-configuration thay thế nó.

Không nên mặc định rằng test chạy qua H2 đã chứng minh câu SQL hoặc mapping tương thích hoàn toàn với database production.

## 5. Tùy chỉnh cấu hình trực tiếp trên @DataJpaTest

@DataJpaTest cung cấp một số thuộc tính để điều chỉnh phạm vi và hành vi của slice. Có thể truyền thuộc tính cấu hình ứng dụng ngay trên annotation:

~~~java
@DataJpaTest(properties = {
    "spring.jpa.hibernate.ddl-auto=create-drop",
    "spring.jpa.properties.hibernate.format_sql=true"
})
class ProductRepositoryTest {
}
~~~

Thuộc tính properties được thêm vào Environment của test context và có thể ghi đè giá trị cấu hình tương ứng. Ví dụ trên yêu cầu Hibernate tạo schema khi context khởi động và xóa schema theo cấu hình create-drop khi kết thúc vòng đời phù hợp. Chỉ dùng ddl-auto=create-drop khi test database được phép tạo và xóa schema.

Một số tùy chỉnh thường dùng:

| Thuộc tính/annotation | Mục đích |
|---|---|
| @DataJpaTest(properties = {...}) | Thêm hoặc ghi đè property cho test context |
| @DataJpaTest(showSql = false) | Tắt việc hiển thị SQL theo cấu hình của slice |
| @DataJpaTest(excludeAutoConfiguration = {...}) | Loại một auto-configuration cụ thể khỏi slice |
| @AutoConfigureTestDatabase(replace = NONE) | Giữ DataSource đã cấu hình thay vì thay bằng embedded database |
| @Import(...) | Bổ sung cấu hình hoặc bean cần thiết cho test |
| @TestPropertySource | Nạp property từ file hoặc khai báo inline |
| @Sql | Chạy script SQL để chuẩn bị hoặc kiểm tra dữ liệu |
| @ActiveProfiles("test") | Chọn profile cấu hình dành cho test |

Hãy kiểm tra API của đúng phiên bản Spring Boot đang dùng vì các thuộc tính và hành vi auto-configuration có thể thay đổi giữa các phiên bản.

### 5.1. showSql và logging

@DataJpaTest thường hiển thị SQL trong test theo cấu hình mặc định của annotation. Có thể tắt bằng:

~~~java
@DataJpaTest(showSql = false)
class ProductRepositoryTest {
}
~~~

Hoặc cấu hình logging để điều chỉnh mức log của Hibernate. Hiển thị SQL giúp đọc câu truy vấn, nhưng nếu cần xem giá trị bind parameter, số lần thực thi hay JDBC batch thì cần cấu hình logger/công cụ quan sát tương ứng. Không nên bật log chi tiết dữ liệu nhạy cảm trong môi trường production.

## 6. Giới hạn component scanning của slice

@DataJpaTest tập trung vào entity và repository. Các bean thông thường như @Service, @Controller, @RestController hoặc component không thuộc phạm vi JPA thường không được component scan tự động đưa vào context.

Ví dụ một repository cần một bean tùy chỉnh để thực hiện auditing hoặc một converter/configuration đặc biệt. Nếu bean đó không được slice nạp, test có thể báo lỗi thiếu dependency hoặc hành vi khác production.

Có hai cách thường dùng để bổ sung cấu hình có chủ đích:

**Cách 1: @Import cấu hình cần thiết**

~~~java
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;

@DataJpaTest
@Import(ProductJpaTestConfig.class)
class ProductRepositoryTest {
}
~~~

ProductJpaTestConfig là lớp cấu hình riêng của dự án, chứa đúng bean mà test cần. Cách này làm rõ phụ thuộc được thêm vào slice.

**Cách 2: @TestConfiguration**

~~~java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration
class ProductJpaTestConfig {
    @Bean
    ProductNameNormalizer productNameNormalizer() {
        return new ProductNameNormalizer();
    }
}
~~~

Sau đó import cấu hình vào test:

~~~java
@DataJpaTest
@Import(ProductJpaTestConfig.class)
class ProductRepositoryTest {
}
~~~

@TestConfiguration dành cho bean hỗ trợ test. Khi dùng cấu hình lồng bên trong test class hoặc cấu hình riêng, cần bảo đảm nó được Spring Boot phát hiện/import theo cách dự định. Import tường minh thường dễ đọc và ít phụ thuộc vào component scanning.

### 6.1. includeFilters và excludeFilters

Nếu thực sự cần điều chỉnh các loại component được scan trong slice, @DataJpaTest hỗ trợ các filter của component scan như includeFilters, excludeFilters và useDefaultFilters.

Ví dụ minh họa:

~~~java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest(
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = ProductNameNormalizer.class
    )
)
class ProductRepositoryTest {
}
~~~

Filter chỉ có ý nghĩa trong phạm vi component scanning mà slice thực hiện. Nó không phải cách bật toàn bộ application context. Với cấu hình phức tạp hoặc bean có dependency lớn, @Import một test configuration cụ thể thường dễ kiểm soát hơn.

Nếu test cần một service hoàn chỉnh cùng các dependency của nó, đó có thể là dấu hiệu test đang vượt khỏi phạm vi của @DataJpaTest. Hãy cân nhắc một integration test dùng @SpringBootTest.

## 7. Những thành phần không nên kỳ vọng có sẵn

Một số nhầm lẫn thường dẫn đến lỗi khi viết slice test:

- **Service bean:** @Service không tự động được nạp như trong full context. Nếu repository test cần service, có thể import bean cụ thể, nhưng nên cân nhắc liệu test có còn tập trung vào persistence hay không.
- **Controller và web infrastructure:** không phải mục tiêu của @DataJpaTest. Dùng @WebMvcTest hoặc @SpringBootTest cho kiểm thử web.
- **Security configuration:** không nên giả định toàn bộ security filter chain và cấu hình authentication được nạp. Test cần security integration phải cấu hình đúng slice hoặc dùng loại test phù hợp.
- **Messaging, scheduler và external clients:** Kafka listener, scheduler, HTTP client hoặc các bean tích hợp ngoài thường không thuộc slice JPA.
- **Toàn bộ application configuration:** chỉ các cấu hình/auto-configuration phù hợp với slice mới được áp dụng. Nếu một cấu hình custom có ảnh hưởng đến JPA, hãy import nó có chủ đích.

Không nên thêm @SpringBootTest chỉ để giải quyết mọi lỗi thiếu bean một cách máy móc. Trước hết hãy xác định bean nào thực sự cần cho mục tiêu persistence test và import đúng phần cấu hình đó.

## 8. Dùng @DataJpaTest với dữ liệu kiểm thử

Có thể chuẩn bị dữ liệu bằng repository, TestEntityManager, @Sql hoặc data initialization phù hợp.

Ví dụ dùng TestEntityManager:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class ProductRepositoryQueryTest {
    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private ProductRepository products;

    @Test
    void findsOnlyProductsInRequestedCategory() {
        entityManager.persist(new Product("Book A", "BOOK-A"));
        entityManager.persist(new Product("Book B", "BOOK-B"));
        entityManager.persist(new Product("Pen", "PEN-01"));
        entityManager.flush();
        entityManager.clear();

        var books = products.findByCategory("BOOK");

        assertThat(books).hasSize(2);
        assertThat(books)
                .extracting(Product::getSku)
                .containsExactlyInAnyOrder("BOOK-A", "BOOK-B");
    }
}
~~~

Ví dụ giả định entity Product có thuộc tính category và repository khai báo findByCategory(String category). Phần entity/repository phải khớp với mô hình thật của dự án.

Dùng flush và clear giúp test quan sát dữ liệu đã được đồng bộ xuống database. Nếu chỉ gọi persist rồi kiểm tra collection trong bộ nhớ, test có thể không kiểm tra được câu query thực tế.

Với dữ liệu cố định dùng cho nhiều test, có thể dùng @Sql hoặc script khởi tạo schema/data. Hãy nhớ rằng mỗi test mặc định chạy trong transaction và rollback; script được thực thi ở pha nào và có tham gia transaction hay không phụ thuộc cấu hình @Sql execution phase và transaction mode.

## 9. Kiểm thử transaction và hành vi commit

Mặc định rollback sau test giúp test độc lập và tránh tích lũy dữ liệu. Tuy nhiên, nó cũng có nghĩa test không nhất thiết kiểm tra chính xác hành vi sau commit.

Nếu cần kiểm tra logic phụ thuộc transaction commit, callback sau commit, constraint được kiểm tra khi commit hoặc dữ liệu nhìn thấy từ transaction khác, phải thiết kế test rõ ràng hơn. Có thể dùng TransactionTemplate, @Commit, @Rollback(false) hoặc transaction độc lập tùy trường hợp.

Một số lưu ý:

1. @DataJpaTest tự mở transaction cho test method theo mặc định. Gọi repository trong test thường tham gia transaction này.
2. Test method chạy trong transaction không mô phỏng nhiều transaction đồng thời chỉ bằng cách gọi repository nhiều lần.
3. Để kiểm tra visibility giữa hai transaction, cần connection/transaction độc lập và điều khiển thứ tự commit.
4. Nếu một transaction con dùng REQUIRES_NEW, nó có thể commit dù transaction ngoài rollback; hãy kiểm tra đúng propagation.
5. Test có thể dùng @Transactional(propagation = NOT_SUPPORTED) để chạy ngoài transaction test mặc định trong những tình huống cần thiết, nhưng khi đó cần tự quản lý dữ liệu test.

Không nên tắt rollback cho toàn bộ slice chỉ để làm test pass. Hãy xác định điều gì cần kiểm tra và tạo ranh giới transaction tương ứng.

## 10. Khi nào @DataJpaTest chưa đủ?

@DataJpaTest phù hợp với kiểm thử repository, entity mapping, JPQL/native query, converter, auditing persistence, constraint và transaction ở tầng dữ liệu. Nhưng nó không kiểm tra được toàn bộ wiring của ứng dụng.

Hãy chuyển sang @SpringBootTest khi cần xác nhận:

- Service thực sự được inject và gọi repository theo luồng nghiệp vụ.
- Nhiều tầng cấu hình phối hợp đúng trong một ApplicationContext đầy đủ.
- Controller, security, messaging hoặc các integration bean tham gia vào use case.
- Một transaction bao trùm nhiều service/repository và cần kiểm tra toàn bộ hành vi.
- Cấu hình production thực tế có nhiều auto-configuration tương tác mà slice không nạp.

Có thể kết hợp @SpringBootTest với @AutoConfigureTestDatabase hoặc Testcontainers tùy mục tiêu. Integration test đầy đủ thường tốn thời gian hơn, vì vậy nên giữ @DataJpaTest cho các kiểm thử persistence có phạm vi hẹp và dùng full context cho các luồng thực sự cần nó.

## 11. Các lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Không tìm thấy repository bean | Repository nằm ngoài phạm vi scan hoặc cấu hình slice bị thay đổi | Kiểm tra package cấu hình chính và repository scanning; import cấu hình cần thiết |
| Không tìm thấy entity/table | Entity không được scan hoặc schema chưa được tạo | Kiểm tra package entity, ddl-auto, migration và SQL initialization |
| Test dùng H2 nhưng production lỗi | Khác biệt dialect, sequence, kiểu dữ liệu, constraint hoặc SQL | Chạy integration test trên database cùng engine với production |
| Thiếu bean custom | Slice không nạp @Service/@Component thông thường | Dùng @Import hoặc @TestConfiguration cho dependency cần thiết |
| Dữ liệu test biến mất sau method | Transaction mặc định rollback | Đây là hành vi dự kiến; dùng @Commit hoặc transaction riêng nếu mục tiêu cần commit |
| Test không thấy lỗi constraint | SQL chưa flush hoặc constraint chỉ được kiểm tra muộn hơn | Gọi flush và kiểm tra thời điểm database thực thi constraint |
| Test context quá nặng | Import quá nhiều cấu hình hoặc vô tình dùng full application config | Giữ slice tập trung vào JPA; chỉ import dependency cần thiết |
| Query test trả kết quả cũ | Persistence context hoặc cache ảnh hưởng kết quả | Flush/clear, kiểm soát cache và xác minh SQL thực tế |

## 12. Quy trình thiết kế một @DataJpaTest tốt

Một quy trình thực tế có thể áp dụng:

1. Xác định đúng đối tượng cần kiểm thử: mapping entity, derived query, JPQL, native SQL, repository behavior hay constraint.
2. Dùng @DataJpaTest để tạo slice persistence tối thiểu.
3. Quyết định database test: embedded database cho kiểm thử nhanh hay database thật qua Testcontainers để xác minh tương thích.
4. Nếu cần giữ DataSource đã cấu hình, đặt @AutoConfigureTestDatabase(replace = NONE) rõ ràng.
5. Tạo dữ liệu qua TestEntityManager hoặc repository, rồi flush/clear khi cần xác minh SQL.
6. Bổ sung custom bean bằng @Import hoặc @TestConfiguration, chỉ trong phạm vi thực sự cần.
7. Dựa vào rollback mặc định để cô lập test; thiết kế transaction độc lập khi cần kiểm tra commit hoặc concurrency.
8. Nếu phải nạp service/controller và nhiều tầng ứng dụng, chuyển test đó sang @SpringBootTest.
9. Chạy test trên đúng phiên bản Spring Boot, Hibernate và database mục tiêu trước khi kết luận cấu hình đã tương thích.

@DataJpaTest giúp kiểm thử tầng persistence nhanh và có phạm vi rõ ràng. Tùy chỉnh đúng phạm vi của nó đòi hỏi hiểu những bean được tự cấu hình, cách database test được chọn, transaction rollback mặc định và giới hạn component scanning. Khi slice không còn đủ để đại diện cho luồng cần kiểm thử, hãy dùng một integration test đầy đủ thay vì biến slice thành một ApplicationContext khó kiểm soát.