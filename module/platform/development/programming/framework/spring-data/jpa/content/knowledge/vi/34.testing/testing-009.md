# Kiểm thử derived query, JPQL, native SQL và Specification

## Mục tiêu

Spring Data JPA hỗ trợ nhiều cách xây dựng truy vấn: suy diễn từ tên phương thức (derived query), JPQL, SQL thuần (native SQL) và Specification cho truy vấn động. Mỗi cách có quy tắc riêng về tên thuộc tính, cú pháp, kiểu tham số, phân trang và phụ thuộc hệ quản trị cơ sở dữ liệu. Repository test cần xác nhận kết quả nghiệp vụ trên database, không chỉ xác nhận phương thức được gọi.

Sau bài này, bạn có thể:

- Thiết lập test repository bằng @DataJpaTest.
- Tạo dữ liệu kiểm thử ổn định và kiểm soát persistence context.
- Kiểm thử derived query, JPQL, native SQL và Specification.
- Kiểm tra sort, pagination, count query và projection.
- Hiểu transaction rollback trong test.
- Chọn database phù hợp cho native query và hành vi đặc thù.

## 1. Phân biệt bốn cách truy vấn

| Cách truy vấn | Cách khai báo | Điều cần kiểm thử |
|---|---|---|
| Derived query | Tên phương thức như findByStatusAndName... | Tên thuộc tính, toán tử, thứ tự, null và kết quả |
| JPQL | @Query với ngôn ngữ truy vấn entity | Tên entity, thuộc tính Java, join, parameter và kết quả |
| Native SQL | @Query(nativeQuery = true) | Tên bảng/cột, dialect, kiểu dữ liệu và mapping |
| Specification | Predicate từ Criteria API | Điều kiện động, cách kết hợp, join, sort và pagination |

Derived query và JPQL thường độc lập với tên bảng. Native SQL phụ thuộc schema và hệ quản trị cụ thể. Specification xây dựng predicate theo Criteria API, vì vậy cần kiểm tra cả trường hợp có và không có bộ lọc.

## 2. Tạo mô hình kiểm thử nhất quán

Dùng một entity nhỏ để minh họa cả bốn kiểu truy vấn. Ví dụ giả định Spring Boot 3, Jakarta Persistence và Java 17 trở lên.

Enum trạng thái:

~~~java
public enum CustomerStatus {
    ACTIVE,
    INACTIVE
}
~~~

Entity:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "customer_record")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, unique = true)
    private String email;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private CustomerStatus status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected Customer() {
    }

    public Customer(
            String name,
            String email,
            CustomerStatus status,
            Instant createdAt) {
        this.name = name;
        this.email = email;
        this.status = status;
        this.createdAt = createdAt;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public String getEmail() { return email; }
    public CustomerStatus getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }
}
~~~

Enum được lưu bằng tên thông qua EnumType.STRING, nên cột status chứa ACTIVE hoặc INACTIVE. Cột thời gian được ánh xạ sang created_at. Các tên này được dùng trong native SQL; tên thuộc tính Java là name, email, status và createdAt.

Repository:

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {

    List<Customer>
    findByStatusAndNameContainingIgnoreCaseOrderByNameAsc(
        CustomerStatus status,
        String keyword
    );

    @Query("""
        select c
          from Customer c
         where c.status = :status
           and c.createdAt >= :from
         order by c.createdAt desc
        """)
    List<Customer> findByStatusCreatedSince(
        @Param("status") CustomerStatus status,
        @Param("from") Instant from
    );

    @Query(value = """
        select *
          from customer_record
         where status = :status
         order by created_at desc
        """, nativeQuery = true)
    List<Customer> findNativeByStatus(
        @Param("status") String status
    );

    @Query(
        value = """
            select *
              from customer_record
             where status = :status
             order by created_at desc
            """,
        countQuery = """
            select count(*)
              from customer_record
             where status = :status
            """,
        nativeQuery = true
    )
    Page<Customer> findNativePageByStatus(
        @Param("status") String status,
        Pageable pageable
    );
}
~~~

Repository kế thừa JpaSpecificationExecutor để hỗ trợ Specification. Derived query dùng tên thuộc tính Java; JPQL dùng tên entity và thuộc tính entity; native SQL dùng tên bảng và cột trong database. Hai phương thức native nhận String vì status được lưu dưới dạng chuỗi. Cách bind enum vào native query có thể phụ thuộc provider, vì vậy hãy chọn kiểu tham số rõ ràng.

## 3. Thiết lập @DataJpaTest

@DataJpaTest tạo test slice cho tầng JPA. Spring Boot cấu hình entity, repository và các thành phần persistence liên quan. Khi có embedded database trên classpath, test thường dùng database nhúng. Test được quản lý trong transaction và mặc định rollback sau mỗi test method.

Các dependency thường dùng:

~~~xml
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
~~~

Test tối thiểu:

~~~java
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class CustomerRepositoryTest {
    // repository tests
}
~~~

Nếu muốn dùng database đã cấu hình thay vì database nhúng:

~~~java
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class CustomerRepositoryIntegrationTest {
}
~~~

Chỉ dùng cấu hình này khi môi trường test cung cấp database an toàn, schema và dữ liệu phù hợp. Không trỏ test vào database production. Nếu cần bean cấu hình riêng, có thể dùng @Import; @DataJpaTest không tải toàn bộ mọi service và component như @SpringBootTest.

## 4. Tạo fixture có kết quả dự đoán được

Dùng thời gian cố định thay vì Instant.now() để kết quả không phụ thuộc thời điểm chạy. Dùng email khác nhau để không vi phạm unique constraint.

~~~java
import java.time.Instant;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Autowired
    private TestEntityManager entityManager;

    @BeforeEach
    void setUp() {
        entityManager.persist(new Customer(
            "An", "an@example.test", CustomerStatus.ACTIVE,
            Instant.parse("2025-01-01T00:00:00Z")));

        entityManager.persist(new Customer(
            "Anna", "anna@example.test", CustomerStatus.ACTIVE,
            Instant.parse("2025-02-01T00:00:00Z")));

        entityManager.persist(new Customer(
            "Bao", "bao@example.test", CustomerStatus.INACTIVE,
            Instant.parse("2025-03-01T00:00:00Z")));

        entityManager.flush();
        entityManager.clear();
    }
}
~~~

flush() buộc INSERT được gửi xuống database. clear() xóa persistence context, tránh việc test vô tình đọc lại entity đang được quản lý trong bộ nhớ thay vì kiểm tra hành vi truy vấn thực tế.

Vì @DataJpaTest mặc định rollback transaction của test sau mỗi method, dữ liệu tạo trong setUp không tồn tại lâu dài giữa các test. Nếu chủ động commit hoặc chạy test nhiều transaction, cần thiết kế cleanup và dữ liệu riêng cho từng test.

## 5. Kiểm thử derived query

Derived query được Spring Data tạo từ tên phương thức. Tên phương thức tham chiếu thuộc tính Java của entity, không phải tên cột database.

Phương thức:

~~~java
List<Customer>
findByStatusAndNameContainingIgnoreCaseOrderByNameAsc(
    CustomerStatus status,
    String keyword
);
~~~

Tên phương thức thể hiện:

- findByStatus: lọc theo status.
- AndNameContaining: name chứa chuỗi tìm kiếm.
- IgnoreCase: so sánh không phân biệt hoa thường theo cách provider/database hỗ trợ.
- OrderByNameAsc: sắp xếp theo name tăng dần.

Test:

~~~java
@Test
void derivedQueryFiltersAndSortsByName() {
    List<Customer> result =
        customerRepository
            .findByStatusAndNameContainingIgnoreCaseOrderByNameAsc(
                CustomerStatus.ACTIVE,
                "an"
            );

    assertThat(result)
        .extracting(Customer::getName)
        .containsExactly("An", "Anna");
}
~~~

Test xác nhận đồng thời điều kiện status, phép tìm chuỗi không phân biệt hoa thường và thứ tự kết quả. Nếu chỉ kiểm tra result không null, test chưa xác nhận truy vấn lọc đúng.

Nên kiểm thử thêm các trường hợp thực sự có trong nghiệp vụ: không có bản ghi phù hợp, Optional rỗng, giới hạn First hoặc Top, Between, Before, After, In, IsNull và thứ tự khi nhiều bản ghi có cùng giá trị. Tên phương thức sai thuộc tính thường khiến repository không khởi tạo được; test context có thể phát hiện lỗi này ngay khi khởi động.

## 6. Kiểm thử JPQL với @Query

JPQL truy vấn entity và thuộc tính Java. Trong JPQL, dùng Customer, createdAt và status, không dùng tên bảng customer_record hoặc tên cột created_at.

Truy vấn đã khai báo:

~~~java
@Query("""
    select c
      from Customer c
     where c.status = :status
       and c.createdAt >= :from
     order by c.createdAt desc
    """)
List<Customer> findByStatusCreatedSince(
    @Param("status") CustomerStatus status,
    @Param("from") Instant from
);
~~~

Test:

~~~java
@Test
void jpqlFiltersByStatusAndCreationTime() {
    List<Customer> result =
        customerRepository.findByStatusCreatedSince(
            CustomerStatus.ACTIVE,
            Instant.parse("2025-02-01T00:00:00Z")
        );

    assertThat(result)
        .extracting(Customer::getName)
        .containsExactly("Anna");
}
~~~

Test kiểm tra named parameter, enum và điều kiện thời gian. Dùng mốc cố định giúp kết quả ổn định giữa các lần chạy.

Các lỗi thường gặp với JPQL:

- Dùng tên bảng hoặc cột thay cho entity/property.
- Viết sai tên thuộc tính hoặc đường dẫn quan hệ.
- Quên @Param hoặc đặt tên parameter khác tên trong query.
- Dùng hàm hoặc toán tử không được provider hỗ trợ.
- Trả về kiểu dữ liệu không khớp projection.
- Join quan hệ làm kết quả bị lặp khi một entity có nhiều bản ghi con.

Nếu truy vấn dùng join collection, kiểm tra có cần distinct hay không. Khi truy vấn trả Page, hãy xác nhận cả nội dung trang và tổng số phần tử vì Spring Data có thể chạy count query riêng.

## 7. Kiểm thử native SQL

Native SQL dùng trực tiếp schema database. Tên bảng, tên cột, kiểu dữ liệu, hàm SQL và cú pháp phân trang phụ thuộc hệ quản trị.

Truy vấn:

~~~sql
select *
from customer_record
where status = :status
order by created_at desc
~~~

Test:

~~~java
@Test
void nativeQueryUsesDatabaseColumnNamesAndOrdering() {
    List<Customer> result =
        customerRepository.findNativeByStatus("ACTIVE");

    assertThat(result)
        .extracting(Customer::getName)
        .containsExactly("Anna", "An");
}
~~~

Test xác nhận native query dùng đúng tên bảng/cột và trả đúng thứ tự. Vì status được ánh xạ bằng EnumType.STRING, tham số ACTIVE phù hợp với dữ liệu đã lưu.

Native query cần chú ý:

- SELECT * thuận tiện khi kết quả khớp mapping entity; nếu join nhiều bảng có cột trùng tên, hãy chọn cột và alias rõ ràng.
- Query trả entity cần cung cấp đủ cột mà mapping yêu cầu.
- Dùng bind parameter; không nối chuỗi input của người dùng vào SQL.
- Tên bảng và cột phải đúng schema thực tế, kể cả quy tắc chữ hoa/chữ thường của database.
- Hàm ngày giờ, JSON, toán tử, kiểu cast và cú pháp phân trang có thể khác giữa PostgreSQL, MySQL, Oracle và SQL Server.
- Không thể bind tên bảng, tên cột hoặc hướng sắp xếp như một giá trị thông thường; nếu cần SQL động, hãy whitelist các lựa chọn hợp lệ.

### 7.1. Native query có phân trang

Với native query trả Page, nên khai báo countQuery rõ ràng khi Spring Data không thể suy ra count query an toàn:

~~~java
@Query(
    value = """
        select *
          from customer_record
         where status = :status
         order by created_at desc
        """,
    countQuery = """
        select count(*)
          from customer_record
         where status = :status
        """,
    nativeQuery = true
)
Page<Customer> findNativePageByStatus(
    @Param("status") String status,
    Pageable pageable
);
~~~

Test cả nội dung trang và tổng số phần tử:

~~~java
@Test
void nativeQueryReturnsCorrectPageAndTotal() {
    Page<Customer> page =
        customerRepository.findNativePageByStatus(
            "ACTIVE",
            PageRequest.of(0, 1)
        );

    assertThat(page.getContent())
        .extracting(Customer::getName)
        .containsExactly("Anna");

    assertThat(page.getTotalElements()).isEqualTo(2);
    assertThat(page.getTotalPages()).isEqualTo(2);
}
~~~

Vì truy vấn sắp xếp created_at giảm dần, Anna đứng trước An. Test kiểm tra cả count query; nếu count query sai điều kiện, content có thể đúng nhưng totalElements vẫn sai.

## 8. Kiểm thử Specification

Specification dùng Criteria API để xây dựng điều kiện động. Repository cần kế thừa JpaSpecificationExecutor.

Tạo các predicate có thể kết hợp:

~~~java
import java.util.Locale;
import org.springframework.data.jpa.domain.Specification;

public final class CustomerSpecifications {

    private CustomerSpecifications() {
    }

    public static Specification<Customer> hasStatus(
            CustomerStatus status) {
        return (root, query, cb) ->
            status == null
                ? cb.conjunction()
                : cb.equal(root.get("status"), status);
    }

    public static Specification<Customer> nameContains(
            String keyword) {
        return (root, query, cb) -> {
            if (keyword == null || keyword.isBlank()) {
                return cb.conjunction();
            }

            String pattern =
                "%" + keyword.toLowerCase(Locale.ROOT) + "%";

            return cb.like(
                cb.lower(root.<String>get("name")),
                pattern
            );
        };
    }
}
~~~

cb.conjunction() trả về điều kiện luôn đúng, hữu ích khi bộ lọc không được cung cấp. nameContains dùng lowercase để tìm không phân biệt hoa thường. Nếu chuỗi tìm kiếm chứa ký tự % hoặc _, hãy quyết định rõ cách escape và viết test cho hành vi đó.

Kết hợp hai Specification:

~~~java
@Test
void specificationCombinesStatusAndNameFilters() {
    Specification<Customer> spec =
        CustomerSpecifications.hasStatus(CustomerStatus.ACTIVE)
            .and(CustomerSpecifications.nameContains("an"));

    List<Customer> result =
        customerRepository.findAll(spec, Sort.by("name").ascending());

    assertThat(result)
        .extracting(Customer::getName)
        .containsExactly("An", "Anna");
}
~~~

Test xác nhận các predicate được kết hợp bằng AND và kết quả được sắp xếp theo thuộc tính entity.

### 8.1. Bộ lọc tùy chọn

Khi xây dựng search API, mỗi filter có thể được truyền hoặc bỏ trống. Nên kiểm thử các tổ hợp có ý nghĩa:

~~~java
@Test
void specificationIgnoresMissingOptionalFilters() {
    Specification<Customer> spec =
        CustomerSpecifications.hasStatus(null)
            .and(CustomerSpecifications.nameContains(""));

    List<Customer> result = customerRepository.findAll(spec);

    assertThat(result).hasSize(3);
}
~~~

Ngoài trường hợp không có filter, hãy kiểm thử từng filter riêng, nhiều filter kết hợp và trường hợp không có kết quả. Điều này giúp phát hiện predicate null hoặc chuỗi rỗng vô tình tạo điều kiện sai.

### 8.2. Phân trang và count với Specification

~~~java
@Test
void specificationSupportsPaginationAndTotalCount() {
    Specification<Customer> spec =
        CustomerSpecifications.hasStatus(CustomerStatus.ACTIVE);

    Page<Customer> page = customerRepository.findAll(
        spec,
        PageRequest.of(0, 1, Sort.by("name").ascending())
    );

    assertThat(page.getContent())
        .extracting(Customer::getName)
        .containsExactly("An");

    assertThat(page.getTotalElements()).isEqualTo(2);
    assertThat(page.getTotalPages()).isEqualTo(2);
}
~~~

Khi Specification có join collection, một entity có thể xuất hiện nhiều lần trong SQL result. Có thể cần distinct và cần xác nhận count query không đếm trùng. Nếu predicate dùng fetch join collection kết hợp pagination, Hibernate có thể phải phân trang trong bộ nhớ hoặc phát cảnh báo; hãy thiết kế truy vấn phù hợp thay vì mặc định fetch mọi quan hệ.

## 9. Kiểm thử projection và truy vấn tổng hợp

Không phải truy vấn nào cũng cần trả entity đầy đủ. Nếu repository trả interface projection, DTO hoặc scalar, test phải kiểm tra chính xác từng trường.

Projection interface:

~~~java
public interface CustomerNameView {
    Long getId();
    String getName();
}
~~~

JPQL projection:

~~~java
@Query("""
    select c.id as id, c.name as name
      from Customer c
     where c.status = :status
     order by c.name
    """)
List<CustomerNameView> findNamesByStatus(
    @Param("status") CustomerStatus status
);
~~~

Test:

~~~java
@Test
void jpqlProjectionMapsSelectedFields() {
    List<CustomerNameView> result =
        customerRepository.findNamesByStatus(CustomerStatus.ACTIVE);

    assertThat(result)
        .extracting(CustomerNameView::getName)
        .containsExactly("An", "Anna");

    assertThat(result)
        .extracting(CustomerNameView::getId)
        .doesNotContainNull();
}
~~~

Alias trong JPQL cần khớp tên getter của projection. Với DTO constructor expression, thứ tự và kiểu tham số phải khớp constructor. Test projection giúp phát hiện lỗi alias, kiểu trả về và thiếu cột mà test chỉ đếm số dòng có thể bỏ sót.

## 10. Transaction và dữ liệu test

Một số nguyên tắc giúp repository test đáng tin cậy:

- Dùng @DataJpaTest cho test tập trung vào entity mapping và repository.
- Dùng TestEntityManager hoặc repository để tạo fixture; flush trước truy vấn cần kiểm tra.
- Clear persistence context nếu muốn bảo đảm truy vấn đọc lại dữ liệu từ database.
- Dùng thời gian, ID tham chiếu và chuỗi cố định để test có thể lặp lại.
- Không phụ thuộc thứ tự trả về nếu query không khai báo ORDER BY.
- Dùng AssertJ hoặc JUnit assertion để kiểm tra giá trị, thứ tự và tổng số phần tử.
- Giữ mỗi test độc lập; không phụ thuộc thứ tự chạy test.
- Không dùng dữ liệu production thật trong test.

Test slice mặc định thường chạy trong transaction và rollback sau test. Nếu kiểm tra hành vi phụ thuộc commit, như transaction event AFTER_COMMIT, hãy chủ động điều khiển transaction bằng TestTransaction hoặc cấu hình test phù hợp. Nếu test mở nhiều transaction, kiểm tra dữ liệu bằng EntityManager hoặc transaction mới sau khi commit.

Không gọi entityManager.clear() trước khi flush dữ liệu cần lưu, vì thay đổi chưa flush có thể bị detach và không được ghi như mong đợi. Thứ tự thường dùng là persist/save, flush, clear, rồi mới gọi query.

## 11. Khi nào cần database thật?

H2 hoặc embedded database giúp test nhanh, nhưng không bảo đảm hành vi giống database production.

Nên chạy integration test với cùng hệ quản trị khi truy vấn sử dụng:

- Native SQL hoặc hàm đặc thù của database.
- JSON, array, full-text search, CTE hoặc window function.
- Collation, case sensitivity hoặc timezone phụ thuộc cấu hình.
- Kiểu dữ liệu và phép chuyển đổi đặc thù.
- Locking, isolation, deadlock hoặc semantics phân trang.
- Generated column, sequence, identity và constraint phức tạp.

Có thể dùng Testcontainers để khởi tạo database thật cho integration test. Khi dùng Testcontainers, bảo đảm schema được tạo bằng cùng migration như production; tránh chỉ dựa vào Hibernate tự generate schema nếu dự án thực tế dùng Flyway hoặc Liquibase.

## 12. Lỗi thường gặp

1. Dùng tên cột trong JPQL. JPQL dùng entity và thuộc tính Java; native SQL dùng bảng và cột.
2. Không flush fixture. Query có thể chạy trước khi dữ liệu test được gửi xuống database.
3. Không clear persistence context khi cần kiểm tra trạng thái database. Entity trong bộ nhớ có thể làm test hiểu sai kết quả.
4. Không khai báo ORDER BY nhưng lại assert thứ tự. SQL không bảo đảm thứ tự nếu không yêu cầu rõ.
5. Chỉ kiểm tra số lượng kết quả. Hai kết quả vẫn có thể là hai bản ghi sai; hãy assert ID hoặc thuộc tính nghiệp vụ.
6. Bỏ qua count query. Page có content đúng nhưng totalElements hoặc totalPages có thể sai.
7. Dùng H2 để kết luận native SQL chạy đúng trên production. Dialect và kiểu dữ liệu có thể khác.
8. Trộn Specification với fetch join collection và pagination mà không kiểm tra count. Kết quả có thể lặp, sai count hoặc phân trang không hiệu quả.
9. Tạo dữ liệu test trùng unique key. Fixture cần email hoặc mã tham chiếu riêng cho mỗi bản ghi.
10. Test chỉ kiểm tra repository được gọi. Repository test cần chạy truy vấn thật và xác nhận kết quả từ database.

## 13. Checklist trước khi hoàn thành repository test

- Xác nhận derived query phản ánh đúng tên thuộc tính và điều kiện nghiệp vụ.
- Kiểm tra JPQL dùng đúng entity, property, parameter và kiểu trả về.
- Kiểm tra native SQL với đúng schema, alias, kiểu tham số và database dialect.
- Kiểm tra Specification đơn lẻ, kết hợp, filter rỗng, sort và pagination.
- Kiểm tra projection, count query và trường hợp không có kết quả.
- Flush và clear khi cần xác nhận truy vấn thực sự chạy trên database.
- Dùng fixture cố định, không phụ thuộc thứ tự test.
- Chạy native query, locking và tính năng đặc thù trên database tương ứng production.
- Xác nhận test transaction rollback hoặc commit đúng với hành vi đang kiểm thử.

Một repository test có giá trị khi xác nhận dữ liệu trả về đúng với yêu cầu nghiệp vụ trên database. Hãy kiểm thử từng kiểu truy vấn theo cú pháp và phạm vi phụ thuộc của nó, đồng thời kiểm tra thứ tự, phân trang, projection và các trường hợp biên mà ứng dụng thực sự sử dụng.