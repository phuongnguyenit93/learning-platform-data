# Kiểm chứng truy vấn, ánh xạ, ràng buộc và ngoại lệ

Tầng dữ liệu chuyển đổi giữa mô hình đối tượng của ứng dụng và dữ liệu được lưu trữ. Một repository có thể được Spring tạo thành công, EntityManager có thể được inject đúng, nhưng câu truy vấn vẫn trả sai bản ghi; một entity có thể được lưu trong bộ nhớ nhưng mapping cột bị sai; một ràng buộc có thể chỉ phát hiện lỗi khi SQL thực sự được gửi tới database; và lỗi từ JDBC hoặc JPA có thể được chuyển thành loại exception khác ở ranh giới Spring.

Kiểm thử tầng dữ liệu cần xác nhận nhiều hành vi riêng biệt:

- **Truy vấn:** điều kiện lọc, join, sắp xếp, phân trang và kết quả trả về có đúng không?
- **Ánh xạ:** dữ liệu giữa bảng/cột và entity/object có được chuyển đổi chính xác không?
- **Ràng buộc:** database có thực thi khóa chính, khóa ngoại, unique, not-null và các điều kiện schema không?
- **Ngoại lệ:** lỗi truy vấn, lỗi dữ liệu hoặc lỗi kết nối được phát hiện và chuyển đổi như thế nào?

Spring Boot cung cấp các test slice như **@DataJpaTest**, **@JdbcTest** và **@DataJdbcTest** để tạo phạm vi kiểm thử tập trung vào persistence. Spring Framework TestContext cung cấp context, transaction test, **@Sql** và các tiện ích khác. Khi chọn đúng phạm vi và đúng database, bài kiểm thử có thể phát hiện lỗi ở repository và mapping trước khi chúng xuất hiện trong luồng nghiệp vụ lớn hơn.

## 1. Phân biệt các loại kiểm thử tầng dữ liệu

Không phải mọi test có repository đều kiểm tra cùng một thứ. Hãy xác định câu hỏi trước khi chọn công cụ.

| Mục tiêu | Phạm vi cần chạy | Công cụ thường dùng |
|---|---|---|
| Quy tắc nghiệp vụ gọi repository đúng cách | Application service | JUnit thuần với fake/mock repository |
| Derived query, JPQL, native query | Spring Data JPA repository | @DataJpaTest |
| Entity, relationship, converter và persistence | JPA provider + database | @DataJpaTest, TestEntityManager |
| SQL qua JdbcTemplate | JDBC layer | @JdbcTest |
| Repository Spring Data JDBC | Spring Data JDBC | @DataJdbcTest |
| Migration và schema production | Database cùng hệ quản trị phù hợp | Testcontainers + migration tool |
| Transaction giữa nhiều thành phần | Application context và database | @SpringBootTest hoặc test tích hợp có phạm vi phù hợp |

Một unit test dùng mock repository có thể xác nhận service gọi findById() hoặc save() theo hợp đồng. Nó không thực thi SQL và không chứng minh query đúng. Muốn kiểm tra truy vấn, mapping hoặc constraint, test phải đi qua persistence adapter và một database thực sự đang chạy.

### @DataJpaTest

@DataJpaTest là test slice của Spring Boot dành cho JPA. Nó thường cấu hình:

- Entity scanning.
- Spring Data JPA repositories.
- EntityManager và JPA provider.
- DataSource và transaction manager phù hợp.
- Các cấu hình liên quan đến JPA trong phạm vi slice.
- TestEntityManager để hỗ trợ kiểm thử persistence.

Test thường chạy trong transaction và rollback sau mỗi method. Theo mặc định, Spring Boot có thể thay DataSource được cấu hình bằng embedded database nếu có trên classpath. Điều này giúp test nhanh, nhưng có thể làm kết quả khác với database production.

### @JdbcTest

@JdbcTest tạo slice tập trung vào JDBC, thường cấu hình DataSource, JdbcTemplate và transaction manager mà không nạp toàn bộ application service hoặc web layer.

Dùng nó khi cần kiểm tra SQL được thực thi qua JdbcTemplate, RowMapper, NamedParameterJdbcTemplate hoặc các thành phần JDBC liên quan.

### @DataJdbcTest

@DataJdbcTest dành cho Spring Data JDBC. Nó kiểm tra aggregate mapping và repository theo mô hình Spring Data JDBC, khác với JPA/Hibernate. Không nên dùng @DataJpaTest chỉ vì dự án có Spring Data trong tên; hãy chọn slice theo công nghệ persistence thực tế.

## 2. Kiểm thử repository với @DataJpaTest

Giả sử ứng dụng quản lý khách hàng:

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "email", nullable = false, unique = true)
    private String email;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    protected Customer() {
    }

    public Customer(String email, String displayName) {
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
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    List<Customer> findByDisplayNameContainingIgnoreCase(
            String keyword
    );
}
~~~

Test slice:

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void findsCustomerByEmail() {
        Customer saved = repository.save(
                new Customer("lan@example.test", "Lan Nguyen")
        );

        Optional<Customer> actual =
                repository.findByEmail("lan@example.test");

        assertTrue(actual.isPresent());
        assertEquals(saved.getId(), actual.orElseThrow().getId());
    }
}
~~~

Bài test này tạo context tập trung vào JPA, lưu một bản ghi và chạy derived query do Spring Data JPA tạo. Nếu tên method, property path hoặc mapping không đúng, lỗi có thể xuất hiện khi khởi tạo repository hoặc khi truy vấn thực thi.

Không nên chỉ assert Optional khác null. Hãy kiểm tra bản ghi đúng, giá trị quan trọng và trường hợp không tìm thấy:

~~~java
@Test
void returnsEmptyWhenEmailDoesNotExist() {
    assertTrue(repository.findByEmail("missing@example.test").isEmpty());
}
~~~

Test không có dữ liệu đầu vào thường hữu ích để bảo vệ semantics của repository, nhất là khi query có điều kiện lọc hoặc join.

### Khi repository cần cấu hình bổ sung

@DataJpaTest không nạp toàn bộ component scan như @SpringBootTest. Nếu repository phụ thuộc một converter, custom repository implementation hoặc cấu hình riêng, có thể import cấu hình cần thiết:

~~~java
@DataJpaTest
@Import(CustomerJpaTestConfiguration.class)
class CustomerRepositoryTest {
    // Repository tests
}
~~~

Chỉ import phần cấu hình liên quan. Nếu cần toàn bộ service, web server và nhiều hạ tầng cùng lúc, đó có thể là yêu cầu của integration test rộng hơn.

## 3. Tạo dữ liệu kiểm thử có chủ đích

Query test chỉ có giá trị khi dữ liệu phân biệt được các điều kiện cần kiểm tra. Một test lọc theo trạng thái cần ít nhất các bản ghi ở nhiều trạng thái; một test sắp xếp cần dữ liệu có giá trị sắp xếp khác nhau; một test phân trang cần đủ bản ghi để vượt qua ranh giới trang.

Ví dụ repository:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {

    List<Order> findByStatusOrderByCreatedAtDesc(OrderStatus status);

    Page<Order> findByCustomerId(
            Long customerId,
            Pageable pageable
    );
}
~~~

Test có thể tạo fixture rõ ràng:

~~~java
@Test
void filtersAndSortsOrdersByStatus() {
    repository.save(new Order(
            10L, OrderStatus.PENDING,
            Instant.parse("2026-01-01T10:00:00Z")
    ));
    repository.save(new Order(
            10L, OrderStatus.PAID,
            Instant.parse("2026-01-02T10:00:00Z")
    ));
    repository.save(new Order(
            10L, OrderStatus.PENDING,
            Instant.parse("2026-01-03T10:00:00Z")
    ));

    List<Order> actual =
            repository.findByStatusOrderByCreatedAtDesc(
                    OrderStatus.PENDING
            );

    assertEquals(2, actual.size());
    assertEquals(
            Instant.parse("2026-01-03T10:00:00Z"),
            actual.get(0).getCreatedAt()
    );
    assertEquals(
            Instant.parse("2026-01-01T10:00:00Z"),
            actual.get(1).getCreatedAt()
    );
}
~~~

Các nguyên tắc tạo fixture:

- Dùng giá trị cố định, có ý nghĩa và dễ đọc.
- Tạo cả bản ghi khớp lẫn không khớp điều kiện.
- Tạo dữ liệu biên cho khoảng ngày, số lượng, trạng thái và null.
- Không phụ thuộc ID tự sinh nếu ID không phải điều cần kiểm tra.
- Không giả định thứ tự trả về nếu query không khai báo ORDER BY.
- Mỗi test tự chuẩn bị dữ liệu của mình hoặc dùng script fixture có thể lặp lại.

Nếu nhiều test dùng chung fixture, helper nên tạo dữ liệu mới cho mỗi test hoặc đảm bảo dữ liệu được rollback/cleanup. Tránh static mutable fixture hoặc phụ thuộc thứ tự chạy.

## 4. Kiểm chứng derived query và JPQL

Spring Data JPA có thể tạo query từ tên method. Test cần xác nhận method diễn đạt đúng property path và điều kiện dự kiến.

Ví dụ:

~~~java
List<Customer> findByStatusAndCreatedAtAfter(
        CustomerStatus status,
        Instant createdAt
);
~~~

Test nên có các bản ghi:

- Đúng status và sau thời điểm mốc.
- Đúng status nhưng trước thời điểm mốc.
- Sai status nhưng sau thời điểm mốc.
- Đúng status và đúng bằng thời điểm mốc nếu semantics ranh giới quan trọng.

Điều này giúp phát hiện nhầm lẫn giữa After và GreaterThanEqual, hoặc sai property path trong tên method.

### Kiểm tra JPQL

Với query viết tường minh:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {

    @Query("""
        select o
        from Order o
        where o.customerId = :customerId
          and o.status = :status
        order by o.createdAt desc
        """)
    List<Order> findRecentOrders(
            @Param("customerId") Long customerId,
            @Param("status") OrderStatus status
    );
}
~~~

Test phải xác nhận cả predicate lẫn thứ tự kết quả. Query có thể biên dịch nhưng vẫn sai về logic, chẳng hạn dùng nhầm thuộc tính, thiếu điều kiện, join sai hoặc sort theo cột khác.

### Query có join và quan hệ entity

Khi query đi qua quan hệ:

~~~java
@Query("""
    select o
    from Order o
    join o.customer c
    where c.email = :email
    """)
List<Order> findByCustomerEmail(@Param("email") String email);
~~~

Hãy tạo nhiều customer và order để xác nhận kết quả chỉ chứa đơn hàng thuộc customer được chỉ định. Nếu dùng left join, test cần cả trường hợp có quan hệ và không có quan hệ. Nếu dùng distinct, test nên kiểm tra không có bản ghi lặp khi join tới collection.

Với quan hệ OneToMany hoặc ManyToMany, join có thể tạo nhiều dòng SQL cho cùng một entity. Kết quả object và cách Hibernate xử lý duplicate phụ thuộc query và mapping. Dữ liệu test cần đủ để phát hiện vấn đề đó.

## 5. Kiểm chứng native query, projection và pagination

### Native SQL query

Native query chạy SQL trực tiếp trên database:

~~~java
@Query(
    value = """
        select *
        from orders
        where customer_id = :customerId
          and status = :status
        order by created_at desc
        """,
    nativeQuery = true
)
List<Order> findNativeOrders(
        @Param("customerId") Long customerId,
        @Param("status") String status
);
~~~

Native query có thể phụ thuộc dialect, tên bảng/cột, kiểu dữ liệu và hàm riêng của database. Test trên H2 không tự chứng minh câu SQL hoạt động trên PostgreSQL hoặc MySQL. Với native query quan trọng, nên chạy trên đúng hệ quản trị hoặc phiên bản tương thích với production.

### Projection

Spring Data projection có thể trả về interface hoặc DTO thay vì entity đầy đủ. Test cần xác nhận alias cột khớp property, kiểu dữ liệu được chuyển đúng và các trường được chọn không bị đảo.

~~~java
public interface CustomerSummary {
    String getEmail();
    String getDisplayName();
}
~~~

~~~java
@Query("""
    select c.email as email,
           c.displayName as displayName
    from Customer c
    where c.id = :id
    """)
Optional<CustomerSummary> findSummaryById(@Param("id") Long id);
~~~

Assertion nên kiểm tra từng field của projection. Chỉ xác nhận projection tồn tại có thể bỏ sót lỗi alias hoặc giá trị trả về sai.

### Pagination và sorting

Ví dụ:

~~~java
Page<Order> findByCustomerId(Long customerId, Pageable pageable);
~~~

Test có thể kiểm tra:

~~~java
Page<Order> page = repository.findByCustomerId(
        customerId,
        PageRequest.of(0, 2, Sort.by("createdAt").descending())
);

assertEquals(2, page.getContent().size());
assertEquals(3, page.getTotalElements());
assertEquals(2, page.getTotalPages());
assertTrue(page.getContent().get(0).getCreatedAt()
        .isAfter(page.getContent().get(1).getCreatedAt()));
~~~

Hãy tạo nhiều hơn page size một bản ghi để kiểm tra phân trang. Với query phức tạp, cần xác nhận count query đúng; tổng số bản ghi sai có thể khiến totalElements và totalPages không chính xác dù content của trang đầu trông đúng.

Nếu dùng Pageable trong native query, có thể cần khai báo countQuery riêng để Spring Data tính tổng số bản ghi. Test nên đi qua nhiều trang, trang cuối và trường hợp không có kết quả.

## 6. Ánh xạ entity và cột

Một entity được khởi tạo đúng trong Java không chứng minh mapping database chính xác. Mapping chỉ được kiểm tra khi dữ liệu được ghi xuống database và đọc lại.

Các khía cạnh thường cần xác nhận:

- Tên bảng và tên cột.
- Kiểu dữ liệu và độ dài.
- ID tự sinh và chiến lược generation.
- Enum lưu dạng string hay ordinal.
- Embedded object và attribute override.
- Quan hệ ManyToOne, OneToMany, OneToOne và ManyToMany.
- Cascade, orphan removal và fetch behavior.
- Converter cho kiểu tùy chỉnh.
- Version column cho optimistic locking.
- Nullability và default value.

### Dùng flush và clear để kiểm tra dữ liệu thực sự được lưu

Trong JPA, entity có thể vẫn nằm trong persistence context. Nếu test lưu rồi đọc lại cùng ID, EntityManager có thể trả về object đang được quản lý mà không đọc database.

Để kiểm tra round-trip mapping:

~~~java
@DataJpaTest
class CustomerMappingTest {

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void persistsAndReloadsCustomerFields() {
        Customer customer =
                new Customer("lan@example.test", "Lan Nguyen");

        entityManager.persist(customer);
        entityManager.flush();

        Long id = customer.getId();

        entityManager.clear();

        Customer reloaded = entityManager.find(Customer.class, id);

        assertEquals("lan@example.test", reloaded.getEmail());
        assertEquals("Lan Nguyen", reloaded.getDisplayName());
    }
}
~~~

flush() buộc JPA đồng bộ persistence context với database. clear() loại các entity đang được quản lý khỏi persistence context. Lần find() sau đó phải lấy dữ liệu lại qua persistence layer, giúp test kiểm tra mapping đọc/ghi rõ hơn.

Có thể dùng TestEntityManager cho thao tác persist, flush, clear và find. Với test không dùng Spring Boot JPA slice, có thể inject EntityManager hoặc dùng EntityManagerFactory theo cấu hình test.

### Kiểm tra enum

Nếu enum được lưu bằng ordinal, thứ tự phần tử enum có thể ảnh hưởng dữ liệu cũ khi enum được sửa. Dùng @Enumerated(EnumType.STRING) thường dễ đọc và ít rủi ro thay đổi thứ tự hơn, nhưng vẫn cần kiểm tra độ dài cột và dữ liệu hợp lệ.

Test nên persist một enum, flush/clear rồi đọc lại. Nếu muốn xác nhận giá trị vật lý trong cột, có thể dùng JdbcTemplate hoặc native query để kiểm tra nội dung thực lưu.

### Kiểm tra converter

Với AttributeConverter, test cần xác nhận chuyển đổi cả hai chiều:

~~~java
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

Test round-trip nên bao gồm giá trị thông thường, zero, null nếu được phép và giá trị biên. Nếu converter có quy tắc làm tròn hoặc scale, assertion phải kiểm tra chính xác chính sách đó.

### Kiểm tra quan hệ và cascade

Giả sử Order có nhiều OrderLine. Test cần xác nhận:

- Lưu order với line có cascade persist hay không.
- Xóa order có xóa line theo cascade remove nếu mapping yêu cầu không.
- Bỏ một line khỏi collection có kích hoạt orphan removal không.
- Foreign key được thiết lập đúng.
- Quan hệ owning side được cập nhật đúng.

JPA chỉ ghi quan hệ theo owning side. Nếu test chỉ thay đổi inverse side, dữ liệu có thể không được cập nhật như mong đợi. Hãy kiểm tra lại entity mapping và cách cập nhật cả hai phía của quan hệ.

## 7. Kiểm tra ràng buộc ở hai tầng: Bean Validation và database

Một lỗi phổ biến là nhầm annotation validation với constraint của schema.

~~~java
@Entity
@Table(
    name = "customers",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customer_email",
        columnNames = "email"
    )
)
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    @NotBlank
    @Column(name = "email", nullable = false)
    private String email;
}
~~~

Có hai cơ chế riêng:

- @NotBlank là Bean Validation constraint. Nó kiểm tra nội dung chuỗi và có thể được thực thi trước khi JPA ghi entity, nếu Bean Validation được tích hợp.
- nullable = false và @UniqueConstraint mô tả metadata schema cho JPA provider khi schema được tạo theo mapping. Constraint thực sự phải tồn tại trong database đang chạy.

Trong môi trường production, schema thường được quản lý bằng Flyway, Liquibase hoặc migration SQL. Khi đó, test cần xác nhận migration đã tạo constraint thực tế. Annotation trong entity không tự chứng minh schema production có cùng constraint.

### Kiểm tra Bean Validation

Nếu mục tiêu là kiểm tra Bean Validation:

~~~java
@Test
void rejectsBlankEmailBeforePersistence() {
    Customer customer = new Customer(" ", "Lan");

    assertThrows(
            jakarta.validation.ConstraintViolationException.class,
            () -> validator.validate(customer)
    );
}
~~~

Ví dụ này dùng jakarta.validation.ConstraintViolationException do Bean Validation trả về. Nó không chứng minh database có NOT NULL constraint.

Nếu mục tiêu là kiểm tra NOT NULL của database, cần gửi SQL hoặc flush entity xuống database với schema thực sự có constraint. Khi đó exception thường đến từ JDBC driver/JPA provider và có thể được Spring chuyển thành DataIntegrityViolationException ở tầng repository.

### Kiểm tra unique constraint

Test cần tạo bản ghi đầu tiên rồi cố gắng ghi bản ghi thứ hai vi phạm cùng unique key:

~~~java
@Test
void rejectsDuplicateEmail() {
    repository.saveAndFlush(
            new Customer("lan@example.test", "Lan")
    );

    assertThrows(
            DataIntegrityViolationException.class,
            () -> repository.saveAndFlush(
                    new Customer("lan@example.test", "Lan Two")
            )
    );
}
~~~

saveAndFlush() hữu ích vì nó buộc SQL được gửi trong lúc test đang thực thi. Nếu chỉ gọi save(), lỗi unique có thể chỉ xuất hiện lúc flush tự động hoặc khi transaction commit, thời điểm có thể nằm ngoài lambda assertion.

Tên exception và nguyên nhân sâu hơn phụ thuộc persistence provider, driver và cơ chế dịch exception. Với Spring Data repository, lỗi integrity thường được chuyển thành DataIntegrityViolationException. Hãy kiểm tra cause chain nếu cần phân biệt unique, foreign key hoặc not-null violation.

### Kiểm tra foreign key và check constraint

Để kiểm tra khóa ngoại, tạo entity tham chiếu tới bản ghi cha không tồn tại hoặc dùng JDBC insert giá trị không hợp lệ. Cần bảo đảm schema test có foreign key constraint thật. Nếu Hibernate đang tự tạo schema thiếu constraint, test có thể xanh dù migration production có yêu cầu khác.

Với database hỗ trợ CHECK, có thể xác nhận một giá trị không hợp lệ bị từ chối, ví dụ số lượng phải lớn hơn 0. Nếu constraint được tạo bởi migration, test nên khởi tạo schema từ migration để kiểm tra đúng DDL được triển khai.

## 8. Phân biệt exception từ Bean Validation, JPA, Hibernate và Spring

Nhiều tầng có thể phát sinh exception với tên hoặc ý nghĩa gần nhau. Cần xác định lỗi xuất hiện ở đâu.

| Tầng | Ví dụ exception | Ý nghĩa |
|---|---|---|
| Jakarta Bean Validation | jakarta.validation.ConstraintViolationException | Object vi phạm constraint validation |
| JPA | jakarta.persistence.PersistenceException, EntityExistsException, OptimisticLockException | Lỗi theo hợp đồng persistence |
| Hibernate | org.hibernate.exception.ConstraintViolationException | Database constraint bị vi phạm qua Hibernate |
| Spring DAO translation | DataIntegrityViolationException, DuplicateKeyException | Lỗi persistence được chuyển thành DataAccessException |
| JDBC | SQLException và subclass | Driver báo lỗi SQL hoặc kết nối |

Lưu ý có hai class thường cùng tên đơn giản là ConstraintViolationException:

- jakarta.validation.ConstraintViolationException thuộc Bean Validation.
- org.hibernate.exception.ConstraintViolationException thuộc Hibernate và mô tả lỗi constraint ở database.

Khi viết import hoặc đọc stack trace, cần phân biệt package đầy đủ.

### Spring exception translation

Spring có cơ chế chuyển exception đặc thù của persistence API thành hệ thống exception nhất quán thuộc DataAccessException. Với Spring Data repository, proxy repository thường áp dụng cơ chế dịch lỗi phù hợp. Với JDBC, JdbcTemplate cũng chuyển SQLException thành DataAccessException.

Điều này giúp service không cần phụ thuộc trực tiếp vào Hibernate hoặc JDBC driver exception. Ví dụ, duplicate key có thể được biểu diễn bằng DuplicateKeyException, còn các vi phạm integrity khác thường đi qua DataIntegrityViolationException.

Không nên assert toàn bộ message của driver vì message có thể khác theo phiên bản database, ngôn ngữ hoặc driver. Nếu hợp đồng của ứng dụng là exception Spring cụ thể, hãy assert loại exception và khi cần thì kiểm tra cause hoặc constraint name theo cách ít phụ thuộc môi trường nhất.

## 9. Kiểm thử ngoại lệ ở đúng thời điểm SQL được thực thi

Với JPA, lệnh save() có thể chưa gửi SQL ngay. Hibernate có thể trì hoãn ghi cho tới flush. Vì vậy, test constraint cần chủ động flush.

Ba cách phổ biến:

~~~java
repository.save(entity);
entityManager.flush();
~~~

Hoặc:

~~~java
repository.saveAndFlush(entity);
~~~

Hoặc:

~~~java
entityManager.persist(entity);
entityManager.flush();
~~~

Đặt flush bên trong lambda của assertThrows để assertion bắt đúng exception:

~~~java
assertThrows(
        DataIntegrityViolationException.class,
        () -> {
            repository.save(entity);
            entityManager.flush();
        }
);
~~~

Nếu flush gây lỗi, transaction hiện tại có thể bị đánh dấu rollback-only hoặc không còn sử dụng được tùy provider/database. Không nên tiếp tục nhiều thao tác persistence trong cùng transaction sau một lỗi constraint rồi kỳ vọng trạng thái vẫn bình thường. Hãy để test kết thúc và rollback, hoặc dùng test method riêng cho từng loại lỗi.

Với JDBC, câu SQL thường được thực thi ngay khi gọi update() hoặc execute(), nên exception thường xuất hiện ngay tại lời gọi đó:

~~~java
assertThrows(
        DataIntegrityViolationException.class,
        () -> jdbcTemplate.update(
                "insert into customers(email, display_name) values (?, ?)",
                "lan@example.test",
                "Duplicate"
        )
);
~~~

Test nên xác nhận đúng thao tác gây lỗi thay vì đặt cả đoạn setup dài vào một lambda rộng, vì điều đó có thể khiến assertion bắt nhầm exception từ bước chuẩn bị dữ liệu.

## 10. Kiểm thử exception translation với JdbcTemplate

JdbcTemplate chuyển SQLException thành hệ thống exception của Spring. Ví dụ repository:

~~~java
@Repository
public class CustomerJdbcRepository {

    private final JdbcTemplate jdbcTemplate;

    public CustomerJdbcRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public CustomerRow findByEmail(String email) {
        return jdbcTemplate.queryForObject(
                """
                select id, email, display_name
                from customers
                where email = ?
                """,
                (rs, rowNum) -> new CustomerRow(
                        rs.getLong("id"),
                        rs.getString("email"),
                        rs.getString("display_name")
                ),
                email
        );
    }
}
~~~

Nếu query không trả về bản ghi, queryForObject() thường ném EmptyResultDataAccessException. Nếu query trả về nhiều dòng trong khi API yêu cầu một dòng, có thể nhận IncorrectResultSizeDataAccessException.

Test có thể kiểm tra hợp đồng:

~~~java
@Test
void reportsMissingCustomer() {
    assertThrows(
            EmptyResultDataAccessException.class,
            () -> repository.findByEmail("missing@example.test")
    );
}
~~~

Nếu repository được thiết kế để trả Optional<Customer>, hãy kiểm tra nó trả Optional.empty() thay vì để exception rò ra. Test cần phản ánh hợp đồng mà repository thực sự công bố.

### Phân biệt lỗi dữ liệu và lỗi hạ tầng

Một số nhóm lỗi khác:

- DataIntegrityViolationException: dữ liệu vi phạm constraint.
- DuplicateKeyException: lỗi duplicate key được nhận diện cụ thể.
- QueryTimeoutException: truy vấn vượt quá giới hạn do driver/database báo.
- CannotAcquireLockException: không lấy được lock theo thao tác dữ liệu.
- DataAccessResourceFailureException: lỗi truy cập tài nguyên dữ liệu.
- TransientDataAccessException: lỗi có khả năng tạm thời, có thể thử lại tùy chính sách.

Không nên tạo test bằng cách cố tình làm database production hoặc mạng thật mất kết nối. Dùng database test, cấu hình timeout có kiểm soát hoặc fake adapter cho logic retry; các bài kiểm tra lỗi hạ tầng thực tế cần môi trường cô lập.

## 11. Kiểm thử @JdbcTest và RowMapper

Khi code dùng JdbcTemplate, test cần xác nhận SQL, parameter binding và ánh xạ ResultSet.

~~~java
@Repository
public class ProductJdbcRepository {

    private final JdbcTemplate jdbcTemplate;

    public ProductJdbcRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Optional<ProductRow> findBySku(String sku) {
        return jdbcTemplate.query(
                """
                select sku, product_name, unit_price
                from products
                where sku = ?
                """,
                (rs, rowNum) -> new ProductRow(
                        rs.getString("sku"),
                        rs.getString("product_name"),
                        rs.getBigDecimal("unit_price")
                ),
                sku
        ).stream().findFirst();
    }
}
~~~

Test:

~~~java
@JdbcTest
@Import(ProductJdbcRepository.class)
class ProductJdbcRepositoryTest {

    @Autowired
    private ProductJdbcRepository repository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void mapsSelectedColumnsToProductRow() {
        jdbcTemplate.update(
                """
                insert into products(sku, product_name, unit_price)
                values (?, ?, ?)
                """,
                "SKU-01",
                "Keyboard",
                new BigDecimal("125000.00")
        );

        ProductRow actual =
                repository.findBySku("SKU-01").orElseThrow();

        assertEquals("SKU-01", actual.sku());
        assertEquals("Keyboard", actual.name());
        assertEquals(new BigDecimal("125000.00"), actual.unitPrice());
    }
}
~~~

@JdbcTest không nhất thiết scan mọi repository component của ứng dụng. Nếu class cần kiểm tra không tự được đưa vào slice, dùng @Import để đăng ký nó.

Những điều cần xác nhận trong JDBC test:

- SQL dùng đúng bảng và cột.
- Parameter được bind đúng thứ tự hoặc đúng tên.
- RowMapper đọc đúng column label.
- Kiểu dữ liệu được chuyển đúng.
- Null được xử lý phù hợp.
- Truy vấn không tìm thấy và nhiều kết quả được xử lý theo hợp đồng.
- Batch update hoặc generated key được đọc đúng nếu có.

Không nên chỉ kiểm tra query chạy mà không kiểm tra giá trị các cột. Một RowMapper có thể gán nhầm hai cột cùng kiểu dữ liệu và test chỉ assert object tồn tại sẽ không phát hiện lỗi.

## 12. Dùng @Sql để chuẩn bị và dọn dữ liệu

Spring TestContext hỗ trợ @Sql để thực thi SQL script trước hoặc sau test method. Điều này hữu ích khi fixture cần nhiều bảng, dữ liệu quan hệ hoặc dữ liệu mà việc tạo qua entity không thể hiện đúng cấu trúc database.

Ví dụ:

~~~java
@DataJpaTest
@Sql(
    scripts = "/sql/customer-test-data.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
class CustomerSearchRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void findsCustomerCreatedBySqlFixture() {
        assertTrue(
                repository.findByEmail("fixture@example.test").isPresent()
        );
    }
}
~~~

File SQL nằm trong test classpath, ví dụ src/test/resources/sql/customer-test-data.sql.

Có thể dùng @Sql ở cấp class hoặc method. Cấp method phù hợp khi mỗi test cần bộ dữ liệu khác nhau. Cấp class phù hợp với dữ liệu chung, nhưng cần xem xét transaction và cleanup.

### @SqlConfig và transaction mode

@SqlConfig cho phép tùy chỉnh cách Spring thực thi script, chẳng hạn:

- DataSource hoặc transaction manager được dùng.
- Separator giữa các statement.
- Encoding.
- Error mode.
- Transaction mode.

Với test-managed transaction, script thường tham gia transaction của test theo cấu hình mặc định. Nếu cần script chạy trong transaction riêng, có thể dùng transaction mode ISOLATED. Khi đó, dữ liệu được script commit có thể tồn tại ngoài transaction test và cần cleanup rõ ràng.

Không nên dùng ISOLATED một cách tùy tiện vì nó có thể làm dữ liệu fixture không bị rollback cùng test. Hãy xác định script setup thuộc transaction nào và ai chịu trách nhiệm dọn dữ liệu.

## 13. Test transaction, rollback và kiểm tra dữ liệu đã commit

@DataJpaTest thường chạy test method trong transaction và rollback khi kết thúc. Điều này giúp test độc lập và tránh tích lũy dữ liệu. Tuy nhiên, rollback có thể che khuất một số vấn đề liên quan tới commit.

Ví dụ, muốn kiểm tra một hành vi chỉ xảy ra khi transaction commit, test có thể dùng TestTransaction:

~~~java
@DataJpaTest
class CustomerCommitTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void commitsThenReadsCustomer() {
        repository.save(new Customer("commit@example.test", "Commit"));

        TestTransaction.flagForCommit();
        TestTransaction.end();

        assertFalse(TestTransaction.isActive());
        assertTrue(repository.findByEmail("commit@example.test").isPresent());

        TestTransaction.start();
    }
}
~~~

Sau khi commit transaction đầu, test có thể bắt đầu transaction mới để thực hiện các bước tiếp theo. Nếu không cần transaction thứ hai, không cần gọi start().

Cần dọn dữ liệu đã commit. Nếu test chạy lại, bản ghi có thể gây duplicate key hoặc làm thay đổi kết quả. Có thể dùng ID duy nhất, cleanup tường minh hoặc database/schema riêng cho test.

Nếu cần kiểm tra transaction isolation hoặc locking giữa hai transaction đồng thời, một test đơn lẻ với một test-managed transaction là chưa đủ. Cần tạo hai transaction độc lập, kiểm soát thứ tự thực thi và dùng database có semantics phù hợp.

## 14. Embedded database hay database giống production?

Embedded database như H2 thường giúp test nhanh và dễ chạy cục bộ. Tuy nhiên, nó có thể khác PostgreSQL, MySQL hoặc SQL Server ở:

- SQL dialect và cú pháp native query.
- Kiểu dữ liệu, độ chính xác số và timezone.
- Case sensitivity, collation và so sánh chuỗi.
- Sequence, identity và generated key.
- JSON, array, enum và kiểu dữ liệu riêng.
- Locking, isolation và transaction behavior.
- Constraint, index và cách báo lỗi.
- Hàm SQL, stored procedure và execution plan.

Nếu ứng dụng dùng JPQL đơn giản và chỉ cần kiểm tra mapping cơ bản, embedded database có thể đủ cho một phần test. Nếu query phụ thuộc database-specific SQL hoặc schema production, cần test trên hệ quản trị tương ứng.

### Không thay database đã cấu hình

Trong Spring Boot test slice, có thể yêu cầu giữ DataSource đã cấu hình thay vì thay bằng embedded database:

~~~java
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
class PostgreSqlRepositoryTest {
}
~~~

Khi đó, test dùng database được cung cấp bởi cấu hình test. Hãy bảo đảm endpoint là database test cô lập, không phải môi trường production hoặc dữ liệu dùng chung ngoài ý muốn.

### Dùng Testcontainers

Testcontainers có thể khởi chạy database tương thích với production trong môi trường test:

~~~java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
class PostgreSqlCustomerRepositoryTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
~~~

Ví dụ cần dependency Testcontainers PostgreSQL và JUnit Jupiter phù hợp. Image tag nên được ghim theo phiên bản mà dự án muốn kiểm tra, thay vì dùng tag trôi nổi.

Với Spring Boot phiên bản hỗ trợ service connection, có thể dùng @ServiceConnection để Boot tự lấy connection details từ container. Nếu dùng @DynamicPropertySource, property được đăng ký thông qua supplier để đọc giá trị runtime như host và port.

Testcontainers giúp kiểm tra SQL, migration, constraint và behavior trên database thực tế hơn. Nó không tự động bảo đảm test có dữ liệu sạch; cần quản lý schema, fixture, transaction và cleanup.

Với context cache, vòng đời container phải tương thích với vòng đời ApplicationContext. Nếu context được tái sử dụng sau khi container đã dừng, DataSource có thể giữ endpoint không còn hoạt động. Hãy quản lý container ở phạm vi phù hợp với các test dùng chung context.

## 15. Kiểm tra migration và schema thực tế

Entity annotation và schema production có thể lệch nhau. Ví dụ, entity có @Column(nullable = false) nhưng migration cũ chưa thêm NOT NULL; hoặc migration tạo unique index nhưng entity không khai báo unique = true.

Nếu ứng dụng dùng Flyway hoặc Liquibase, test tích hợp nên khởi tạo database trống và chạy migration thật. Sau đó chạy repository test trên schema được tạo từ migration.

Những điều nên kiểm tra:

- Migration chạy theo đúng thứ tự.
- Constraint và index được tạo.
- Tên bảng/cột tương thích với mapping.
- Kiểu dữ liệu tương thích với entity.
- Foreign key và cascade behavior đúng.
- Migration từ phiên bản trước có thể nâng cấp lên schema mới.
- Native query và stored procedure vẫn hoạt động.

Không nên chỉ dùng Hibernate ddl-auto=create-drop để kết luận migration production đúng. Hibernate có thể tự tạo schema từ entity và bỏ qua lỗi trong file migration. Nếu mục tiêu là kiểm tra migration, phải để migration tool tạo schema.

## 16. Kiểm tra optimistic locking và concurrency

Entity có thể dùng version field:

~~~java
@Entity
class Inventory {

    @Id
    private Long id;

    private int quantity;

    @Version
    private long version;
}
~~~

@Version giúp phát hiện cập nhật đồng thời dựa trên version. Test optimistic locking cần hai persistence context hoặc hai transaction độc lập:

1. Đọc cùng một bản ghi từ hai transaction.
2. Transaction thứ nhất cập nhật và commit.
3. Transaction thứ hai cố cập nhật với version cũ.
4. Xác nhận transaction thứ hai nhận lỗi optimistic locking.

Một test dùng cùng một EntityManager hoặc cùng persistence context không mô phỏng được hai bản đọc độc lập. Cần flush và clear, hoặc dùng hai EntityManager/transaction để tạo tình huống cạnh tranh thực sự.

Exception có thể được biểu diễn thành OptimisticLockException ở JPA hoặc ObjectOptimisticLockingFailureException ở Spring tùy đường đi và lớp dịch exception. Test nên assert loại exception ở đúng API mà ứng dụng công bố.

Pessimistic locking, deadlock và timeout phụ thuộc database engine và cách điều phối transaction. Những test này nên chạy trên database tương thích production, có timeout hữu hạn và dữ liệu cô lập.

## 17. Kiểm tra lỗi truy vấn và lỗi số lượng kết quả

Một repository method có thể có hợp đồng khác nhau khi không có bản ghi:

- Trả Optional.empty().
- Trả collection rỗng.
- Trả null nếu API cũ hoặc custom implementation cho phép.
- Ném exception nếu query yêu cầu đúng một kết quả.

Test cần xác nhận hành vi đã chọn.

Ví dụ với JdbcTemplate.queryForObject, không có dòng thường dẫn tới EmptyResultDataAccessException. Với Spring Data JPA, method trả Optional có thể trả empty. Với custom query trả một entity đơn trị, hành vi khi không có hoặc nhiều kết quả phụ thuộc chữ ký và provider.

Không nên bắt mọi exception chung chung rồi coi đó là kết quả hợp lệ. Hãy assert loại exception cụ thể và giữ phần thao tác có thể ném lỗi trong lambda nhỏ:

~~~java
assertThrows(
        IncorrectResultSizeDataAccessException.class,
        () -> repository.findUniqueCustomerByDomain("example.test")
);
~~~

Tên exception ví dụ cần khớp API thực tế. Nếu query trả Optional, hãy kiểm tra empty thay vì mong đợi exception.

## 18. Các lỗi thường gặp khi kiểm thử tầng dữ liệu

### Mock repository rồi kết luận query đúng

Mock không thực thi SQL hoặc JPQL. Dùng @DataJpaTest hoặc @JdbcTest để kiểm tra query thật.

### Chỉ gọi save mà không flush

Constraint hoặc lỗi SQL có thể chưa xuất hiện. Dùng saveAndFlush() hoặc EntityManager.flush() khi cần bắt lỗi trong test.

### Đọc lại entity từ cùng persistence context

EntityManager có thể trả object đang được quản lý trong bộ nhớ. Dùng clear() trước khi đọc lại để kiểm tra round-trip mapping.

### Dùng H2 nhưng production là PostgreSQL

Native query, type, locking và constraint behavior có thể khác. Chạy test tương thích production bằng Testcontainers khi những khác biệt đó quan trọng.

### Dùng entity schema generation thay migration production

Test có thể xanh dù migration lỗi. Nếu kiểm tra schema triển khai, chạy migration thật trên database test trống.

### Assert message exception quá chi tiết

Message driver thay đổi theo database và phiên bản. Ưu tiên assert exception type, SQL state hoặc constraint name khi ổn định và có ý nghĩa.

### Gộp nhiều loại lỗi vào một test

Nếu một test kiểm tra unique, foreign key, not-null và query timeout, khi thất bại khó xác định nguyên nhân. Tách theo hành vi và loại constraint.

### Dữ liệu test phụ thuộc thứ tự

Một test commit dữ liệu có thể làm test khác thất bại. Dùng transaction rollback mặc định, ID riêng, schema/database riêng hoặc cleanup rõ ràng.

### Test transaction che giấu lỗi commit

Test rollback không kiểm tra mọi hành vi xảy ra khi commit. Với yêu cầu commit hoặc visibility giữa transaction, dùng TestTransaction hoặc transaction độc lập.

### Không kiểm tra count query của pagination

Trang đầu có thể trả đúng content nhưng totalElements sai. Test nhiều trang và xác nhận count.

### Không xác nhận thứ tự khi query cần thứ tự

Database không bảo đảm thứ tự nếu query không có ORDER BY. Nếu thứ tự là hợp đồng, khai báo order trong query và assert rõ.

## 19. Quy trình thiết kế một bộ kiểm thử repository

Có thể xây dựng test theo các bước:

1. Xác định hợp đồng repository: đầu vào, điều kiện lọc, kết quả, thứ tự và trường hợp không có dữ liệu.
2. Chọn slice đúng công nghệ: @DataJpaTest, @JdbcTest hoặc @DataJdbcTest.
3. Quyết định database: embedded cho test nhanh hay Testcontainers cho tính tương thích.
4. Chuẩn bị fixture có dữ liệu khớp, không khớp và dữ liệu biên.
5. Kiểm tra truy vấn bằng assertion trên giá trị và thứ tự thực tế.
6. Kiểm tra mapping bằng persist/flush/clear/reload.
7. Kiểm tra constraint bằng cách buộc SQL thực thi và assert exception phù hợp.
8. Kiểm tra migration trên schema được tạo từ migration tool nếu đó là rủi ro cần bảo vệ.
9. Xác nhận transaction rollback/commit theo mục tiêu.
10. Chạy lại test độc lập và trong suite để bảo đảm dữ liệu không phụ thuộc thứ tự.

Không phải repository nào cũng cần test tất cả các mục. Một query đơn giản không cần test locking; một converter không cần dựng web server; một native query phụ thuộc PostgreSQL cần database phù hợp. Chọn test theo rủi ro và hợp đồng thực tế.

## 20. Tiêu chí chọn bằng chứng đúng cho mỗi hành vi

| Hành vi cần chứng minh | Bằng chứng phù hợp |
|---|---|
| Derived query lọc đúng | Gọi repository trên database với dữ liệu phân biệt và assert kết quả |
| JPQL join đúng | Tạo dữ liệu quan hệ và xác nhận tập kết quả |
| Native query tương thích | Chạy trên database/dialect tương ứng |
| Pagination đúng | Kiểm tra content, totalElements, totalPages và nhiều trang |
| Mapping ghi/đọc đúng | Persist, flush, clear, reload và so sánh field |
| Bean Validation đúng | Gọi Validator hoặc kích hoạt validation tại lifecycle phù hợp |
| Database constraint đúng | Chạy SQL/flush trên schema có constraint thật |
| Spring exception translation đúng | Gọi qua repository/JdbcTemplate và assert DataAccessException phù hợp |
| Migration đúng | Khởi tạo database trống và chạy migration thật |
| Optimistic locking đúng | Hai transaction/persistence context độc lập cạnh tranh cùng bản ghi |
| Commit visibility đúng | Commit transaction đầu rồi đọc bằng transaction khác |
| Rollback test đúng | Xác nhận dữ liệu không còn sau khi test transaction kết thúc |

Kiểm thử tầng dữ liệu có giá trị khi nó đi qua đúng thành phần có trách nhiệm thực thi hành vi. Mock repository chỉ bảo vệ cách service tương tác với repository; test slice và database bảo vệ query, mapping và constraint; migration test bảo vệ schema được triển khai; transaction test bảo vệ commit, rollback và concurrency. Khi tạo fixture có chủ đích, flush đúng thời điểm, đọc lại sau khi clear persistence context và chọn database tương thích với production, test sẽ phát hiện được những lỗi mà kiểm thử đơn vị thuần không thể quan sát.

