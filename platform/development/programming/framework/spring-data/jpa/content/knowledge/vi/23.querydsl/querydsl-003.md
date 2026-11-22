# Xây dựng predicate có kiểm tra kiểu bằng Q-type trong Spring Data JPA

Querydsl là thư viện xây dựng query bằng Java API có kiểm tra kiểu ở thời điểm biên dịch. Với Spring Data JPA, Querydsl tạo các lớp Q-type từ entity. Thay vì viết tên thuộc tính dưới dạng chuỗi như name hoặc createdAt, code truy vấn tham chiếu trực tiếp đến các thuộc tính có kiểu tương ứng, ví dụ QCustomer.customer.name và QCustomer.customer.createdAt.

Q-type giúp IDE hỗ trợ autocomplete, compiler phát hiện nhiều lỗi sai tên property hoặc sai kiểu dữ liệu trước khi ứng dụng chạy. Predicate Querydsl có thể được truyền vào QuerydslPredicateExecutor của Spring Data hoặc dùng với JPAQueryFactory để xây truy vấn tùy biến.

Bài học này giải thích quá trình sinh Q-type, cấu hình annotation processor cho Jakarta Persistence, các biểu thức có kiểu, kết hợp điều kiện tùy chọn, truy vấn quan hệ và collection, tích hợp repository, custom query, web binding, phân trang, kiểm thử và những giới hạn cần lưu ý.

## 1. Querydsl và predicate có kiểm tra kiểu

Querydsl cung cấp DSL để biểu diễn điều kiện truy vấn bằng object Java. Predicate là một biểu thức Boolean có thể dùng trong WHERE.

Ví dụ với entity Customer:

~~~java
QCustomer customer = QCustomer.customer;

Predicate predicate = customer.name.eq("Linh")
    .and(customer.enabled.isTrue());
~~~

Predicate có nghĩa:

- name bằng Linh.
- enabled bằng true.

Không cần tự ghép chuỗi JPQL hoặc SQL. Querydsl dùng metadata của Q-type để biết tên property và kiểu dữ liệu; Querydsl JPA chuyển biểu thức thành query phù hợp cho JPA provider.

Một biểu thức có thể được giữ trong biến, kết hợp với biểu thức khác, truyền cho repository hoặc dùng trong JPAQueryFactory.

## 2. Q-type được sinh từ entity như thế nào?

Q-type là lớp Java được annotation processor của Querydsl sinh ra trong quá trình compile. Với entity Customer, processor tạo lớp QCustomer.

Entity:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    private String email;

    private Integer age;

    private Boolean enabled;

    @Enumerated(EnumType.STRING)
    private CustomerStatus status;

    private LocalDate birthDate;

    private LocalDateTime createdAt;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "address_id")
    private Address address;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    private List<Order> orders = new ArrayList<>();

    private Long tenantId;

    protected Customer() {
    }

    public Customer(
            String name,
            String email,
            Integer age,
            Boolean enabled,
            CustomerStatus status) {
        this.name = name;
        this.email = email;
        this.age = age;
        this.enabled = enabled;
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }

    public Integer getAge() {
        return age;
    }

    public Boolean getEnabled() {
        return enabled;
    }

    public CustomerStatus getStatus() {
        return status;
    }

    public LocalDate getBirthDate() {
        return birthDate;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public Address getAddress() {
        return address;
    }

    public List<Order> getOrders() {
        return orders;
    }

    public Long getTenantId() {
        return tenantId;
    }
}
~~~

Enum:

~~~java
public enum CustomerStatus {
    NEW,
    ACTIVE,
    SUSPENDED
}
~~~

The later Q-type examples also use two related entity types. Their property declarations are part of the same model: Address exposes city and countryCode; Order exposes status and its customer association. Keep each public type in its own Java source file.

~~~java
@Entity
@Table(name = "addresses")
public class Address {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String city;

    private String countryCode;

    protected Address() {
    }
}
~~~

~~~java
@Entity
@Table(name = "orders")
public class Order {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    protected Order() {
    }
}
~~~

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
~~~

Sau khi annotation processing chạy, Querydsl sinh lớp QCustomer có các path tương ứng:

- id là NumberPath<Long>.
- name và email là StringPath.
- age là NumberPath<Integer>.
- enabled là BooleanPath.
- status là EnumPath<CustomerStatus>.

Tên và chi tiết code sinh ra do processor quản lý. Không tự viết hoặc chỉnh sửa QCustomer bằng tay. Nếu entity thay đổi, chạy compile để sinh lại Q-type.

## 3. Q-type khác JPA static metamodel

JPA Criteria API thường dùng static metamodel class có hậu tố gạch dưới, ví dụ Customer_. Querydsl dùng Q-type, ví dụ QCustomer.

| Đặc điểm | JPA static metamodel | Querydsl Q-type |
|---|---|---|
| Ví dụ | Customer_.name | QCustomer.customer.name |
| API truy vấn | CriteriaBuilder/CriteriaQuery | Querydsl Predicate và query DSL |
| Cách biểu diễn | SingularAttribute/SetAttribute | StringPath, NumberPath, EntityPath, CollectionPath |
| Kết hợp điều kiện | CriteriaBuilder.and/or | BooleanExpression, BooleanBuilder |
| Sinh mã | JPA metamodel processor | Querydsl annotation processor |

Cả hai đều giúp tránh dùng tên property tùy ý dưới dạng chuỗi trong query. Querydsl cung cấp DSL riêng, trong khi JPA static metamodel làm việc trực tiếp với Criteria API chuẩn.

Không nhầm QCustomer với entity Customer. QCustomer là metadata để xây query; nó không phải entity được lưu trong persistence context.

## 4. Thêm dependency cho Spring Boot 3 và Jakarta Persistence

Spring Boot 3 / Spring Data JPA 3 sử dụng namespace jakarta.persistence. Querydsl cần artifact có classifier jakarta để annotation processor nhận đúng annotation của Jakarta.

Ví dụ Maven dùng Querydsl 5.1.0:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.querydsl</groupId>
        <artifactId>querydsl-jpa</artifactId>
        <version>5.1.0</version>
        <classifier>jakarta</classifier>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <annotationProcessorPaths>
                    <path>
                        <groupId>com.querydsl</groupId>
                        <artifactId>querydsl-apt</artifactId>
                        <version>5.1.0</version>
                        <classifier>jakarta</classifier>
                    </path>
                    <path>
                        <groupId>jakarta.persistence</groupId>
                        <artifactId>jakarta.persistence-api</artifactId>
                        <version>3.1.0</version>
                    </path>
                    <path>
                        <groupId>jakarta.annotation</groupId>
                        <artifactId>jakarta.annotation-api</artifactId>
                        <version>2.1.1</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Ví dụ Gradle:

~~~groovy
dependencies {
    implementation("com.querydsl:querydsl-jpa:5.1.0:jakarta")

    annotationProcessor("com.querydsl:querydsl-apt:5.1.0:jakarta")
    annotationProcessor("jakarta.persistence:jakarta.persistence-api")
    annotationProcessor("jakarta.annotation:jakarta.annotation-api")
}
~~~

Các version trong ví dụ minh họa một cấu hình Jakarta; hãy dùng version tương thích với Spring Boot, Spring Data JPA và Hibernate ORM mà dự án đang quản lý. Nếu dependency management của dự án đã cung cấp Jakarta API, tránh khai báo các version xung đột.

Với Spring Boot 2 / Spring Data JPA dùng javax.persistence, cấu hình Querydsl phải dùng artifact và annotation processor tương ứng với javax. Không trộn Q-type được sinh cho javax với ứng dụng Jakarta hoặc ngược lại.

## 5. Chạy annotation processor và kiểm tra Q-type

Sau khi thêm dependency và annotation processor, chạy compile:

~~~bash
mvn clean compile
~~~

Với Gradle:

~~~bash
./gradlew clean compileJava
~~~

Maven thường đặt source sinh tự động trong target/generated-sources/annotations; Gradle đặt dưới build/generated/sources/annotationProcessor/java/main.

Kiểm tra:

- Có file QCustomer.java được sinh không.
- IDE đã nhận thư mục generated sources chưa.
- Q-type phản ánh đúng property của entity không.
- Annotation processor có nhận Jakarta annotation không.
- Build có dùng cùng version Querydsl ở runtime và compile time không.

Không commit file generated nếu quy ước dự án không yêu cầu. Nhiều dự án chỉ commit entity và cấu hình processor, rồi sinh Q-type trong mỗi lần build. Hãy theo chính sách build của repository.

Khi đổi tên hoặc xóa property entity, chạy compile sạch để loại Q-type cũ và tạo lại metadata chính xác.

## 6. Đọc Q-type và các kiểu path phổ biến

Q-type cung cấp path phù hợp với kiểu Java của property:

| Property entity | Querydsl path thường gặp | Ví dụ |
|---|---|---|
| String | StringPath | customer.name |
| Long/Integer | NumberPath | customer.id, customer.age |
| Boolean | BooleanPath | customer.enabled |
| Enum | EnumPath | customer.status |
| LocalDate | DatePath | customer.birthDate |
| LocalDateTime | DateTimePath | customer.createdAt |
| Quan hệ entity | EntityPath/Q-type | customer.address.city |
| Collection | ListPath/SetPath/CollectionPath | customer.orders |

Ví dụ:

~~~java
QCustomer customer = QCustomer.customer;

BooleanExpression nameMatches =
    customer.name.containsIgnoreCase("linh");

BooleanExpression ageMatches =
    customer.age.goe(18);

BooleanExpression active =
    customer.enabled.isTrue();

BooleanExpression statusMatches =
    customer.status.eq(CustomerStatus.ACTIVE);
~~~

Kiểu path giúp compiler kiểm tra phương thức phù hợp. Ví dụ StringPath có các phép so sánh chuỗi; NumberPath có phép so sánh số; DateTimePath có phép so sánh thời gian.

Tên method có thể khác theo kiểu path. Dùng autocomplete hoặc tài liệu API của version Querydsl trong dự án để chọn đúng phép toán.

## 7. Các phép so sánh cơ bản

Querydsl có các biểu thức so sánh thường dùng:

~~~java
QCustomer c = QCustomer.customer;

BooleanExpression exactName = c.name.eq("Linh");
BooleanExpression differentName = c.name.ne("Linh");

BooleanExpression ageAtLeast = c.age.goe(18);
BooleanExpression ageBelow = c.age.lt(65);

BooleanExpression createdAfter =
    c.createdAt.goe(startTime);

BooleanExpression createdBefore =
    c.createdAt.lt(endTime);
~~~

Các phép toán phổ biến:

| Method | Ý nghĩa |
|---|---|
| eq(value) | Bằng |
| ne(value) | Khác |
| gt(value) | Lớn hơn |
| goe(value) | Lớn hơn hoặc bằng |
| lt(value) | Nhỏ hơn |
| loe(value) | Nhỏ hơn hoặc bằng |
| between(a, b) | Nằm trong khoảng |
| in(values) | Thuộc tập giá trị |
| notIn(values) | Không thuộc tập giá trị |

Một số method chỉ tồn tại trên path có kiểu phù hợp. Ví dụ gt/goe thường dùng với kiểu Comparable hoặc Number, không áp dụng cho mọi path.

## 8. Điều kiện chuỗi

StringPath cung cấp các thao tác chuỗi:

~~~java
QCustomer c = QCustomer.customer;

BooleanExpression exact = c.name.eq("Linh");
BooleanExpression contains = c.name.contains("linh");
BooleanExpression containsIgnoreCase =
    c.name.containsIgnoreCase("linh");

BooleanExpression starts =
    c.email.startsWithIgnoreCase("support");

BooleanExpression ends =
    c.email.endsWithIgnoreCase("@example.com");
~~~

Ý nghĩa:

- contains: tìm chuỗi con.
- containsIgnoreCase: tìm chuỗi con không phân biệt hoa/thường theo cách biểu diễn của Querydsl/provider/database.
- startsWith: tìm tiền tố.
- endsWith: tìm hậu tố.
- eq: so sánh chính xác theo semantics database.

Không suy luận rằng IgnoreCase đồng nghĩa bỏ dấu tiếng Việt. Việc phân biệt dấu, hoa/thường và Unicode còn phụ thuộc database collation và cách xử lý chuỗi. Kiểm thử trên database mục tiêu với dữ liệu thực tế.

Các phép contains thường tạo LIKE pattern có wildcard ở hai đầu; chúng có thể không tận dụng B-tree index thông thường hiệu quả trên bảng lớn. Kiểm tra execution plan trước khi dùng cho tìm kiếm quy mô lớn.

## 9. NULL phải dùng isNull và isNotNull

Querydsl không nên dùng eq(null) hoặc ne(null) để kiểm tra giá trị thiếu. Hãy dùng method chuyên biệt:

~~~java
QCustomer c = QCustomer.customer;

BooleanExpression emailMissing = c.email.isNull();

BooleanExpression emailPresent = c.email.isNotNull();
~~~

Không viết:

~~~java
c.email.eq(null);
~~~

Querydsl thường từ chối eq(null) và yêu cầu dùng isNull(). Ngoài ra, logic SQL với NULL là logic ba giá trị; phép so sánh thông thường với NULL không trả TRUE.

Nếu một tham số filter là null và có nghĩa bỏ qua điều kiện, không thêm predicate. Nếu null có nghĩa tìm các bản ghi có cột NULL, thêm isNull().

Hai yêu cầu này cần được phân biệt ở filter DTO hoặc API contract.

## 10. Kết hợp BooleanExpression bằng AND và OR

BooleanExpression có thể kết hợp trực tiếp:

~~~java
QCustomer c = QCustomer.customer;

BooleanExpression predicate =
    c.name.containsIgnoreCase("linh")
        .and(c.enabled.isTrue())
        .and(c.age.goe(18));
~~~

Nhóm OR:

~~~java
BooleanExpression textMatches =
    c.name.containsIgnoreCase("linh")
        .or(c.email.containsIgnoreCase("linh"));

BooleanExpression finalPredicate =
    textMatches.and(c.enabled.isTrue());
~~~

Ý nghĩa:

~~~text
(name contains "linh" OR email contains "linh")
AND enabled = true
~~~

Nên tạo biến riêng cho nhóm OR khi query có nhiều điều kiện. Điều này giúp tránh sai logic do người đọc hiểu nhầm thứ tự kết hợp.

BooleanExpression là cách biểu diễn tốt cho một điều kiện đã có đủ giá trị. Với nhiều filter tùy chọn, BooleanBuilder thường thuận tiện hơn.

## 11. BooleanBuilder cho điều kiện động

BooleanBuilder là predicate có thể bổ sung điều kiện dần:

~~~java
QCustomer c = QCustomer.customer;

BooleanBuilder builder = new BooleanBuilder();

builder.and(c.enabled.isTrue());
builder.and(c.age.goe(18));

if (keyword != null && !keyword.isBlank()) {
    builder.and(c.name.containsIgnoreCase(keyword.strip()));
}

if (status != null) {
    builder.and(c.status.eq(status));
}
~~~

Mỗi lần gọi and hoặc or, builder cập nhật biểu thức tổng hợp.

BooleanBuilder hữu ích khi số điều kiện thay đổi theo request. Hãy tạo một builder mới cho mỗi lần xây query; không giữ builder mutable dùng chung giữa các request hoặc lưu trong singleton.

Có thể dùng BooleanExpression kết hợp bất biến nếu số nhánh nhỏ và rõ ràng. Không cần dùng BooleanBuilder cho mọi query.

## 12. Filter DTO và xây predicate chỉ với filter hợp lệ

Dùng wrapper type để phân biệt filter không được gửi với giá trị false hoặc 0:

~~~java
public record CustomerFilter(
    String keyword,
    CustomerStatus status,
    Boolean enabled,
    Integer minAge,
    Integer maxAge,
    String email,
    NullMode emailMode
) {
    public enum NullMode {
        ANY,
        IS_NULL,
        IS_NOT_NULL
    }
}
~~~

Builder:

~~~java
public final class CustomerPredicates {

    private CustomerPredicates() {
    }

    public static Optional<Predicate> from(CustomerFilter filter) {
        QCustomer c = QCustomer.customer;
        BooleanBuilder builder = new BooleanBuilder();

        if (filter.keyword() != null
                && !filter.keyword().isBlank()) {
            String keyword = filter.keyword().strip();

            builder.and(
                c.name.containsIgnoreCase(keyword)
                    .or(c.email.containsIgnoreCase(keyword))
            );
        }

        if (filter.status() != null) {
            builder.and(c.status.eq(filter.status()));
        }

        if (filter.enabled() != null) {
            builder.and(c.enabled.eq(filter.enabled()));
        }

        if (filter.minAge() != null) {
            builder.and(c.age.goe(filter.minAge()));
        }

        if (filter.maxAge() != null) {
            builder.and(c.age.loe(filter.maxAge()));
        }

        if (filter.email() != null && !filter.email().isBlank()) {
            builder.and(c.email.eq(filter.email().strip()));
        }

        if (filter.emailMode() == CustomerFilter.NullMode.IS_NULL) {
            builder.and(c.email.isNull());
        } else if (filter.emailMode()
                == CustomerFilter.NullMode.IS_NOT_NULL) {
            builder.and(c.email.isNotNull());
        }

        return builder.hasValue()
            ? Optional.of(builder.getValue())
            : Optional.empty();
    }
}
~~~

Ý nghĩa của hợp đồng filter:

- keyword null hoặc blank: không thêm điều kiện tên/email.
- status null: không lọc status.
- enabled null: không lọc; false vẫn là một giá trị filter.
- minAge/maxAge null: bỏ qua cận tương ứng.
- emailMode ANY: không lọc nullness của email.
- emailMode IS_NULL: chỉ lấy email NULL.
- emailMode IS_NOT_NULL: chỉ lấy email khác NULL.

Optional.empty() ở đây biểu diễn không có predicate, không phải kết quả truy vấn rỗng. Caller cần xử lý trường hợp không có predicate bằng cách gọi repository không điều kiện tương ứng hoặc áp dụng phạm vi mặc định của ứng dụng.

Nếu filter có collection rỗng, hãy định nghĩa rõ semantics: bỏ qua điều kiện, trả không có kết quả hoặc từ chối request. Không phụ thuộc vào cách provider xử lý IN với collection rỗng.

## 13. QuerydslPredicateExecutor trong Spring Data JPA

Spring Data JPA cung cấp QuerydslPredicateExecutor để repository nhận Predicate Querydsl:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer> {
}
~~~

Các method thường dùng:

| Method | Kết quả |
|---|---|
| findOne(predicate) | Optional<T> |
| findAll(predicate) | Iterable<T> |
| findAll(predicate, sort) | Iterable<T> |
| findAll(predicate, pageable) | Page<T> |
| count(predicate) | long |
| exists(predicate) | boolean |

Ví dụ tìm khách hàng:

~~~java
QCustomer c = QCustomer.customer;

Predicate predicate = c.name.containsIgnoreCase("linh")
    .and(c.enabled.isTrue());

Iterable<Customer> customers =
    customerRepository.findAll(predicate);
~~~

Phân trang:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.asc("name"),
        Sort.Order.asc("id")
    )
);

Page<Customer> page =
    customerRepository.findAll(predicate, pageable);
~~~

QuerydslPredicateExecutor giúp triển khai các truy vấn entity đơn giản nhanh chóng. Nó không thay thế toàn bộ JPAQueryFactory khi cần projection, group by, nhiều join, fetch join hoặc query phức tạp.

## 14. Xử lý khi không có predicate

Không nên gọi QuerydslPredicateExecutor với một tham số null chỉ vì tất cả filter đều bị bỏ qua. Một số implementation yêu cầu Predicate không null.

Có thể xử lý rõ ở service:

~~~java
public Page<Customer> search(
        CustomerFilter filter,
        Pageable pageable) {

    Optional<Predicate> predicate =
        CustomerPredicates.from(filter);

    if (predicate.isPresent()) {
        return repository.findAll(predicate.get(), pageable);
    }

    return repository.findAll(pageable);
}
~~~

Ví dụ này coi filter không có predicate là lấy tất cả Customer trong phạm vi repository. Trong ứng dụng thực tế, vẫn phải áp dụng tenant, authorization hoặc soft-delete scope bắt buộc ở tầng phù hợp.

Nếu không có filter phải trả kết quả rỗng theo nghiệp vụ, hãy tạo predicate luôn false thay vì gọi findAll(pageable).

Đừng dùng null để vừa biểu diễn “không lọc” vừa biểu diễn “không được phép trả kết quả”.

## 15. Querydsl với quan hệ entity

Q-type cho phép đi theo property path đã mapping:

~~~java
QCustomer c = QCustomer.customer;

BooleanExpression cityMatches =
    c.address.city.eq("Da Nang");

BooleanExpression customerMatches =
    c.address.countryCode.eq("VN")
        .and(c.enabled.isTrue());
~~~

Trong ví dụ, Customer có quan hệ address và Address có property city/countryCode. Processor sinh path tương ứng nếu mapping entity hợp lệ.

Đối với quan hệ to-one, truy cập path lồng nhau thường được Querydsl chuyển thành join cần thiết trong query. Hãy kiểm tra SQL sinh ra nếu query có nhiều đường quan hệ hoặc association optional.

Nếu cần kiểm soát join type, alias hoặc điều kiện join, dùng JPAQueryFactory và khai báo join rõ ràng.

## 16. Collection và any()

Với collection association, Querydsl có thể dùng any() để diễn đạt điều kiện trên một phần tử liên quan:

~~~java
QCustomer c = QCustomer.customer;

BooleanExpression hasPaidOrder =
    c.orders.any().status.eq(OrderStatus.PAID);
~~~

Ý nghĩa: tìm Customer có ít nhất một Order mang status PAID.

Đây là biểu thức trên collection path. Cách provider chuyển thành SQL có thể phụ thuộc query và mapping; kiểm tra SQL khi hiệu năng hoặc số hàng kết quả quan trọng.

Nếu query cần nhiều điều kiện trên cùng một Order, hãy đảm bảo các điều kiện được áp dụng cho cùng một alias/order row. Với query phức tạp, khai báo join có alias trong JPAQueryFactory để kiểm soát rõ hơn.

## 17. Tự kiểm soát join bằng JPAQueryFactory

Tạo bean JPAQueryFactory:

~~~java
@Configuration
public class QuerydslConfiguration {

    @Bean
    public JPAQueryFactory jpaQueryFactory(EntityManager entityManager) {
        return new JPAQueryFactory(entityManager);
    }
}
~~~

Custom query:

~~~java
QCustomer customer = QCustomer.customer;
QOrder order = QOrder.order;

List<Customer> results = queryFactory
    .selectFrom(customer)
    .join(customer.orders, order)
    .where(
        order.status.eq(OrderStatus.PAID),
        customer.enabled.isTrue()
    )
    .distinct()
    .fetch();
~~~

JPAQueryFactory tạo query có kiểu kết quả. join nhận path và alias Q-type, vì vậy compiler kiểm tra association và thuộc tính được tham chiếu.

Dùng distinct khi join collection có thể tạo nhiều hàng cho cùng root entity và nghiệp vụ cần mỗi Customer chỉ xuất hiện một lần. DISTINCT có chi phí và không thay thế việc thiết kế join đúng.

Không fetch join collection tùy tiện trong query phân trang. Join collection có thể nhân hàng, làm phân trang và count phức tạp. Cân nhắc truy vấn ID theo trang trước rồi tải chi tiết hoặc dùng DTO projection.

## 18. Projection với Querydsl

Querydsl không chỉ trả entity. JPAQueryFactory có thể chọn một tập dữ liệu và ánh xạ sang DTO.

DTO:

~~~java
public record CustomerSummary(
    Long id,
    String name,
    String email
) {
}
~~~

Query:

~~~java
QCustomer c = QCustomer.customer;

List<CustomerSummary> summaries = queryFactory
    .select(Projections.constructor(
        CustomerSummary.class,
        c.id,
        c.name,
        c.email
    ))
    .from(c)
    .where(c.enabled.isTrue())
    .orderBy(c.name.asc(), c.id.asc())
    .fetch();
~~~

Projections.constructor dùng constructor có thứ tự tham số tương ứng với các expression được chọn. Kiểu dữ liệu và thứ tự phải khớp DTO.

Các lựa chọn projection khác gồm Projections.bean và Projections.fields, mỗi loại có yêu cầu riêng về setter, constructor hoặc field. Chọn constructor projection khi muốn DTO bất biến và hợp đồng constructor rõ ràng.

Nếu cần projection phức tạp, group by hoặc aggregate, JPAQueryFactory thường phù hợp hơn QuerydslPredicateExecutor.

## 19. Custom repository fragment cho Querydsl

Có thể đặt truy vấn Querydsl tùy chỉnh trong repository fragment:

~~~java
public interface CustomerSearchRepository {
    List<CustomerSummary> searchSummaries(CustomerFilter filter);
}
~~~

Repository chính:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer>,
                CustomerSearchRepository {
}
~~~

Implementation theo quy ước fragment:

~~~java
public class CustomerSearchRepositoryImpl
        implements CustomerSearchRepository {

    private final JPAQueryFactory queryFactory;

    public CustomerSearchRepositoryImpl(
            JPAQueryFactory queryFactory) {
        this.queryFactory = queryFactory;
    }

    @Override
    public List<CustomerSummary> searchSummaries(
            CustomerFilter filter) {

        QCustomer c = QCustomer.customer;
        BooleanBuilder where = new BooleanBuilder();

        if (filter.keyword() != null
                && !filter.keyword().isBlank()) {
            String keyword = filter.keyword().strip();

            where.and(
                c.name.containsIgnoreCase(keyword)
                    .or(c.email.containsIgnoreCase(keyword))
            );
        }

        if (filter.enabled() != null) {
            where.and(c.enabled.eq(filter.enabled()));
        }

        JPAQuery<CustomerSummary> query = queryFactory
            .select(Projections.constructor(
                CustomerSummary.class,
                c.id,
                c.name,
                c.email
            ))
            .from(c);

        if (where.hasValue()) {
            query.where(where);
        }

        return query
            .orderBy(c.name.asc(), c.id.asc())
            .fetch();
    }
}
~~~

Fragment phù hợp khi cần kết hợp Querydsl với projection, join, grouping hoặc logic truy vấn riêng. Tên implementation phải khớp interface cộng hậu tố Impl theo cấu hình repository.

Tách phần build predicate thành class dùng chung nếu nhiều fragment hoặc repository cần cùng một quy tắc filter. Không để một fragment vừa quản lý mọi query của hệ thống vừa chứa quá nhiều trách nhiệm.

## 20. Kết hợp Predicate từ nhiều nguồn

Predicate là object có thể truyền giữa các lớp. Ví dụ service có thể kết hợp điều kiện bảo mật với điều kiện tìm kiếm:

~~~java
QCustomer c = QCustomer.customer;

Predicate tenantScope =
    c.tenantId.eq(currentTenantId);

Optional<Predicate> search =
    CustomerPredicates.from(filter);

BooleanBuilder finalPredicate =
    new BooleanBuilder(tenantScope);

search.ifPresent(finalPredicate::and);

Page<Customer> page =
    repository.findAll(finalPredicate, pageable);
~~~

Điều kiện tenantScope luôn được áp dụng, kể cả khi người dùng không nhập filter. Đây là cách giữ phạm vi dữ liệu bắt buộc tách biệt với bộ lọc tùy chọn.

Không để client tự tạo hoặc truyền Predicate tùy ý qua HTTP. Predicate là biểu thức nội bộ của ứng dụng; API nên nhận DTO có field được whitelist và service tự xây predicate.

## 21. Querydsl web binding và QuerydslBinderCustomizer

Spring Data có thể bind query parameter HTTP thành Querydsl Predicate thông qua @QuerydslPredicate và Querydsl web support.

Ví dụ repository tùy chỉnh binding:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer>,
                QuerydslBinderCustomizer<QCustomer> {

    @Override
    default void customize(
            QuerydslBindings bindings,
            QCustomer root) {

        bindings.excludeUnlistedProperties(true);

        bindings.including(
            root.name,
            root.status
        );

        bindings.bind(root.name)
            .first((path, value) -> path.containsIgnoreCase(value));

        bindings.bind(root.status)
            .first((path, value) -> path.eq(value));
    }
}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerRepository repository;

    public CustomerController(CustomerRepository repository) {
        this.repository = repository;
    }

    @GetMapping
    public Iterable<Customer> search(
            @QuerydslPredicate(root = Customer.class)
            Predicate predicate) {
        return repository.findAll(predicate);
    }
}
~~~

Với web binding, cần bật Spring Data web support phù hợp trong ứng dụng và kiểm tra phiên bản Spring Data đang dùng. Spring Boot web auto-configuration thường cung cấp hạ tầng web tương ứng, nhưng không nên giả định mọi cấu hình tùy chỉnh đều đã bật Querydsl argument resolver.

Chỉ expose các property cần tìm kiếm. excludeUnlistedProperties(true) giúp tránh để client truy vấn tùy ý những field nội bộ như tenantId, deletedAt hoặc dữ liệu nhạy cảm.

## 22. Whitelist sort và filter từ API

Querydsl giúp xây predicate an toàn về kiểu, nhưng không có nghĩa mọi field đều nên được expose cho client.

Không nhận raw property name rồi dùng reflection hoặc PathBuilder tùy tiện để tạo query mà không kiểm soát.

Ví dụ whitelist sort:

~~~java
public Sort resolveSort(String key, String direction) {
    Sort.Direction order =
        Sort.Direction.fromString(direction);

    return switch (key) {
        case "name" -> Sort.by(order, "name");
        case "created" -> Sort.by(order, "createdAt");
        case "age" -> Sort.by(order, "age");
        default -> throw new IllegalArgumentException(
            "Unsupported sort field"
        );
    };
}
~~~

Nếu dùng JPAQueryFactory, có thể ánh xạ key thành expression Q-type tương ứng:

~~~java
OrderSpecifier<?> order = switch (key) {
    case "name" -> orderDirection == Direction.ASC
        ? c.name.asc()
        : c.name.desc();
    case "age" -> orderDirection == Direction.ASC
        ? c.age.asc()
        : c.age.desc();
    default -> throw new IllegalArgumentException(
        "Unsupported sort field"
    );
};
~~~

Whitelist bảo vệ cấu trúc query và giới hạn dữ liệu mà API cho phép sắp xếp. Đồng thời validate page size, số filter và độ dài chuỗi đầu vào.

## 23. Phân trang với QuerydslPredicateExecutor

QuerydslPredicateExecutor hỗ trợ Pageable:

~~~java
Predicate predicate = QCustomer.customer.enabled.isTrue();

Pageable pageable = PageRequest.of(
    0,
    25,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);

Page<Customer> result =
    repository.findAll(predicate, pageable);
~~~

Page chứa content, totalElements và totalPages. Để tính tổng, Spring Data có thể thực hiện count query.

Thêm tie-breaker duy nhất như id để tạo thứ tự xác định khi nhiều bản ghi có cùng createdAt. Điều này hữu ích cho pagination, dù dữ liệu thay đổi giữa các request vẫn có thể làm offset page dịch chuyển.

Nếu chỉ cần biết còn trang kế tiếp hay không, cân nhắc Slice hoặc query riêng để tránh chi phí count tổng.

## 24. Phân trang trong JPAQueryFactory

Với query tùy chỉnh, có thể dùng offset và limit:

~~~java
List<CustomerSummary> content = queryFactory
    .select(Projections.constructor(
        CustomerSummary.class,
        c.id,
        c.name,
        c.email
    ))
    .from(c)
    .where(predicate)
    .orderBy(c.createdAt.desc(), c.id.desc())
    .offset(pageable.getOffset())
    .limit(pageable.getPageSize())
    .fetch();
~~~

Nếu cần Page, xây count query riêng với cùng predicate:

~~~java
Long totalValue = queryFactory
    .select(c.count())
    .from(c)
    .where(predicate)
    .fetchOne();

long total = totalValue == null ? 0L : totalValue;
~~~

Sau đó tạo PageImpl từ content, pageable và total.

Không nên giả định một API count tự động luôn chính xác với query nhiều group by, distinct hoặc join collection. Viết count query phù hợp với semantics của query nội dung và kiểm thử totalElements.

## 25. Kiểu dữ liệu và phép toán theo domain

Q-type giữ thông tin kiểu property:

- Số nguyên và số thập phân: dùng NumberPath với gt, goe, between.
- Chuỗi: dùng StringPath với eq, contains, startsWith.
- Boolean: dùng isTrue, isFalse hoặc eq.
- Enum: dùng EnumPath với eq/in.
- Ngày: dùng DatePath/DateTimePath với before, after, between hoặc goe/lt.
- Quan hệ: dùng Q-type lồng nhau.
- Collection: dùng CollectionPath/ListPath/SetPath và các thao tác phù hợp.

Ví dụ khoảng ngày nửa mở:

~~~java
BooleanExpression createdInRange =
    c.createdAt.goe(from)
        .and(c.createdAt.lt(to));
~~~

Khoảng [from, to) bao gồm thời điểm bắt đầu và loại thời điểm kết thúc. Kiểu này hữu ích cho các khoảng ngày liên tiếp mà không chồng lấn biên.

Dùng BigDecimal cho tiền tệ thay vì double. Q-type phản ánh kiểu property của entity, nhưng không thay thế validation miền nghiệp vụ như minPrice không âm hoặc from không sau to.

## 26. Kiểm soát collection rỗng và dữ liệu NULL

Querydsl có các method isNull, isNotNull, in và notIn. Cần xác định semantics trước khi xây predicate:

~~~java
if (filter.statuses() != null
        && !filter.statuses().isEmpty()) {
    builder.and(c.status.in(filter.statuses()));
}
~~~

Ví dụ trên coi null và empty set đều là không áp dụng filter status.

Nếu empty set có nghĩa không được trả bản ghi nào, thêm predicate luôn false:

~~~java
if (filter.statuses() != null
        && filter.statuses().isEmpty()) {
    builder.and(Expressions.asBoolean(false));
}
~~~

Nếu muốn tìm field null:

~~~java
builder.and(c.email.isNull());
~~~

Nếu muốn bỏ qua filter email khi input null, không thêm predicate. Đừng gọi eq(null).

Logic của SQL với NULL là ba giá trị TRUE/FALSE/UNKNOWN. Vì vậy, ne(value) không tự động bao gồm hàng có field NULL. Nếu cần lấy các hàng khác value hoặc NULL, kết hợp ne(value).or(isNull()) một cách tường minh.

## 27. Kiểm thử predicate bằng database

Có thể kiểm thử predicate bằng @DataJpaTest để xác nhận biểu thức Querydsl được dịch thành query đúng và trả kết quả mong muốn.

Ví dụ:

~~~java
@DataJpaTest
class CustomerQuerydslTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void combinesTypedPredicates() {
        repository.saveAndFlush(
            new Customer(
                "Linh Nguyen",
                "linh@example.com",
                25,
                true,
                CustomerStatus.ACTIVE
            )
        );

        repository.saveAndFlush(
            new Customer(
                "An Tran",
                "an@example.com",
                17,
                false,
                CustomerStatus.NEW
            )
        );

        QCustomer c = QCustomer.customer;

        Predicate predicate = c.name.containsIgnoreCase("linh")
            .and(c.age.goe(18))
            .and(c.enabled.isTrue());

        Iterable<Customer> result = repository.findAll(predicate);

        List<String> names = StreamSupport
            .stream(result.spliterator(), false)
            .map(Customer::getName)
            .toList();

        assertThat(names).containsExactly("Linh Nguyen");
    }
}
~~~

Ví dụ giả định test fixture có thể lưu hai Customer độc lập và repository đã cấu hình Querydsl. Cần thêm import test framework, StreamSupport và entity/repository theo package dự án.

Nên kiểm thử:

1. Exact match và substring.
2. Case-insensitive matching theo database thực tế.
3. Numeric/date range.
4. Enum và Boolean false.
5. NULL với isNull/isNotNull.
6. Collection in và empty collection.
7. AND/OR grouping.
8. Quan hệ to-one và collection any/join.
9. Không có filter.
10. Pageable, Sort và count query.
11. Web binding chỉ expose property được whitelist.
12. Query có projection và custom fragment.

## 28. Debug SQL và hiệu năng

Querydsl tạo biểu thức có kiểu nhưng không tự đảm bảo query tối ưu. Hãy bật SQL logging hoặc datasource query counter để xem SQL thật.

Các điểm cần kiểm tra:

- Query có thêm join không cần thiết không.
- contains/containsIgnoreCase có tạo pattern wildcard đầu chuỗi không.
- Hàm LOWER trên cột có ảnh hưởng index không.
- Join collection có nhân hàng root không.
- DISTINCT có cần thiết và có chi phí cao không.
- Count query có cùng semantics với query content không.
- Sort có index phù hợp không.
- Offset pagination có quá sâu không.

Với tìm kiếm chuỗi con trên bảng lớn, B-tree index thường khó hỗ trợ pattern có wildcard đầu chuỗi. Cân nhắc full-text hoặc index chuyên biệt theo database nếu workload yêu cầu.

Dùng EXPLAIN/EXPLAIN ANALYZE hoặc công cụ tương ứng của database. So sánh kế hoạch thực thi với dữ liệu gần production thay vì kết luận từ code Querydsl.

## 29. Giới hạn và lựa chọn giữa Querydsl với các cách truy vấn khác

| Nhu cầu | Lựa chọn |
|---|---|
| Query đơn giản, cố định | Derived query hoặc @Query |
| Điều kiện động, cần Q-type | Querydsl Predicate/BooleanBuilder |
| Predicate entity đơn giản qua repository | QuerydslPredicateExecutor |
| DTO projection, grouping hoặc join phức tạp | JPAQueryFactory/custom fragment |
| Query cần API JPA chuẩn, không thêm thư viện | Criteria API |
| SQL đặc thù database | Native query |
| Chỉ cần một số cột cho màn hình đọc | DTO projection |

Querydsl là thư viện bổ sung, không phải một phần của Jakarta Persistence specification. Cần quản lý version, annotation processor và compatibility với JPA provider.

QuerydslPredicateExecutor thuận tiện nhưng giới hạn khả năng tùy chỉnh projection và cấu trúc query. Khi cần kiểm soát SQL/JPQL shape, dùng JPAQueryFactory trong custom repository fragment.

## 30. Lỗi thường gặp và cách khắc phục

**1. Không sinh được QCustomer**

Kiểm tra querydsl-apt, annotation processor path, classifier Jakarta/Javax và entity annotation. Chạy clean compile.

**2. IDE báo không tìm thấy Q-type nhưng Maven build thành công**

Đánh dấu generated sources là source root hoặc refresh project model. Không tự tạo QCustomer bằng tay.

**3. Dùng nhầm javax và jakarta**

Spring Boot 3 cần Jakarta classifier. Không dùng annotation processor javax để xử lý entity jakarta.persistence.

**4. Gọi eq(null)**

Dùng isNull(). Nếu null nghĩa là bỏ qua filter, không thêm predicate.

**5. Filter Boolean false bị bỏ qua**

Kiểm tra value != null thay vì if (value). Dùng Boolean wrapper cho filter tùy chọn.

**6. BooleanBuilder bị dùng chung giữa request**

Tạo builder mới cho từng lần xây query. Builder là mutable object.

**7. Query trả quá nhiều hàng sau join collection**

Kiểm tra cardinality và cân nhắc distinct hoặc EXISTS. Đừng dùng distinct để che một join sai.

**8. Pagination chậm hoặc total sai**

Kiểm tra count query, join collection và offset. Viết count query riêng cho query phức tạp.

**9. Client có thể lọc field nội bộ**

Dùng QuerydslBinderCustomizer, excludeUnlistedProperties và whitelist filter/sort key.

**10. containsIgnoreCase không bỏ dấu**

IgnoreCase không phải accent-insensitive. Kiểm tra collation hoặc chiến lược tìm kiếm riêng.

**11. Predicate rỗng bị truyền cho repository**

Phân biệt Optional.empty() với predicate luôn false. Khi không có predicate, gọi repository không điều kiện phù hợp; nếu cần kết quả rỗng, tạo biểu thức false.

**12. Querydsl query không tận dụng index**

Kiểm tra SQL, wildcard, hàm trên cột và execution plan. Tối ưu index theo workload thật.

## 31. Quy trình triển khai Querydsl Q-type

1. Xác định Spring Boot/Spring Data JPA đang dùng Jakarta hay javax.
2. Thêm querydsl-jpa và querydsl-apt đúng classifier/version.
3. Cấu hình annotation processor cho build tool.
4. Chạy clean compile và xác nhận Q-type được sinh.
5. Dùng Q-type thay cho property string trong predicate.
6. Chọn BooleanExpression cho điều kiện rõ ràng, BooleanBuilder cho filter động.
7. Xác định semantics null, false, zero và collection empty.
8. Kết hợp AND/OR theo đúng nhóm nghiệp vụ.
9. Dùng QuerydslPredicateExecutor cho query entity đơn giản.
10. Dùng JPAQueryFactory/custom fragment cho join, projection và grouping.
11. Whitelist web binding và sort key.
12. Kết hợp Pageable với tie-breaker ổn định.
13. Kiểm tra count query và collection pagination.
14. Viết integration test trên database mục tiêu.
15. Xem SQL và execution plan trước khi tối ưu.

## 32. Checklist tự đánh giá

- [ ] Tôi giải thích được Querydsl Predicate và Q-type.
- [ ] Tôi biết Q-type được sinh bởi annotation processor.
- [ ] Tôi phân biệt Q-type với JPA static metamodel.
- [ ] Tôi cấu hình đúng classifier Jakarta hoặc Javax.
- [ ] Tôi biết chạy clean compile và kiểm tra generated source.
- [ ] Tôi dùng StringPath, NumberPath, BooleanPath, EnumPath và DateTimePath.
- [ ] Tôi biết dùng eq, ne, goe, lt, between và in.
- [ ] Tôi biết dùng containsIgnoreCase và startsWith.
- [ ] Tôi dùng isNull/isNotNull thay cho eq(null).
- [ ] Tôi biết kết hợp BooleanExpression bằng AND/OR.
- [ ] Tôi biết xây filter tùy chọn bằng BooleanBuilder.
- [ ] Tôi không chia sẻ builder mutable giữa request.
- [ ] Tôi biết tích hợp QuerydslPredicateExecutor.
- [ ] Tôi biết xử lý trường hợp không có predicate.
- [ ] Tôi biết truy cập quan hệ và collection path.
- [ ] Tôi biết dùng JPAQueryFactory cho custom query.
- [ ] Tôi biết projection sang DTO.
- [ ] Tôi biết dùng QuerydslBinderCustomizer và whitelist field.
- [ ] Tôi hiểu giới hạn pagination khi join collection.
- [ ] Tôi có integration test và kiểm tra SQL/execution plan.

## 33. Câu hỏi ôn tập

**1. Q-type là gì?**

Là lớp Java do Querydsl annotation processor sinh từ entity, chứa path có kiểu để xây dựng predicate và query.

**2. Vì sao Q-type có kiểm tra kiểu?**

Mỗi property được biểu diễn bằng path phù hợp với kiểu dữ liệu. Compiler và IDE có thể phát hiện nhiều lỗi sai property hoặc phép toán không phù hợp trước runtime.

**3. QCustomer khác Customer thế nào?**

Customer là entity được quản lý bởi JPA; QCustomer là metadata/query type dùng để xây biểu thức, không phải entity instance.

**4. Vì sao Spring Boot 3 cần Querydsl Jakarta classifier?**

Entity dùng jakarta.persistence. Processor và Querydsl JPA runtime phải tương thích namespace đó để nhận diện annotation và chạy query.

**5. BooleanExpression khác BooleanBuilder thế nào?**

BooleanExpression biểu diễn điều kiện; BooleanBuilder là builder mutable để thêm điều kiện động từng bước.

**6. Khi nào dùng QuerydslPredicateExecutor?**

Khi cần lọc entity bằng Predicate với findAll, findOne, count, exists và Pageable/Sort mà không cần query projection phức tạp.

**7. Khi nào dùng JPAQueryFactory?**

Khi cần join có kiểm soát, DTO projection, grouping, aggregate hoặc cấu trúc query vượt quá khả năng tiện dụng của QuerydslPredicateExecutor.

**8. Làm sao xử lý một filter null?**

Nếu null nghĩa là bỏ qua, không thêm predicate. Nếu cần tìm cột NULL, dùng isNull(). Không dùng eq(null).

**9. Boolean false có được xem là không có filter không?**

Không. Với Boolean wrapper, null biểu diễn bỏ qua; false là một giá trị filter hợp lệ.

**10. Querydsl có bảo đảm query nhanh không?**

Không. Nó giúp xây query có kiểu; SQL và execution plan vẫn phụ thuộc query shape, database, index, cardinality và provider.

Q-type giúp đưa nhiều lỗi query từ runtime về thời điểm biên dịch và làm cho điều kiện tìm kiếm dễ đọc hơn. Khi kết hợp đúng annotation processor, Predicate, BooleanBuilder và repository executor, ứng dụng có thể xây filter động an toàn về kiểu; với truy vấn phức tạp hơn, JPAQueryFactory mở rộng khả năng kiểm soát mà vẫn giữ Q-type làm nền tảng.

## Tài liệu tham khảo

- [Querydsl Reference Guide](https://querydsl.com/static/querydsl/latest/reference/html/)
- [Querydsl JPA API](https://querydsl.com/static/querydsl/latest/apidocs/com/querydsl/jpa/impl/JPAQueryFactory.html)
- [Spring Data JPA — Querydsl Extension](https://docs.spring.io/spring-data/jpa/reference/repositories/core-extensions.html)
- [Spring Data Commons — Querydsl Web Support](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html)
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/)
