# Phân biệt chuẩn Jakarta Persistence và tính năng riêng của Hibernate

Trong Spring Data JPA, Jakarta Persistence định nghĩa hợp đồng chuẩn để ánh xạ object Java với dữ liệu quan hệ, còn Hibernate ORM là một persistence provider triển khai hợp đồng đó và cung cấp thêm nhiều tính năng riêng. Hai khái niệm thường được dùng cùng nhau nhưng không đồng nghĩa: mã dùng API chuẩn có khả năng chuyển sang provider khác dễ hơn; mã dùng extension của Hibernate có thể giải quyết một nhu cầu cụ thể tốt hơn nhưng gắn chặt với Hibernate.

Khi phát triển ứng dụng, hãy nhận diện rõ mỗi annotation, API, query language và cấu hình thuộc lớp nào. Điều này giúp chọn đúng tính năng, tránh import nhầm package và kiểm soát chi phí khi nâng cấp hoặc thay provider.

## 1. Jakarta Persistence và Hibernate ORM là gì?

**Jakarta Persistence** là đặc tả Jakarta EE định nghĩa cách ứng dụng Java làm việc với persistence trong cơ sở dữ liệu quan hệ. Đặc tả quy định các khái niệm và API như:

- Entity, embeddable, mapped superclass và quan hệ giữa các entity.
- `EntityManager`, persistence context, lifecycle và dirty checking.
- JPQL, Criteria API, entity graph và optimistic locking.
- Mapping annotation như `@Entity`, `@Id`, `@OneToMany`, `@ManyToOne`.
- Các API chuẩn cho transaction integration, query và cache.

**Hibernate ORM** là một implementation (provider) của Jakarta Persistence. Hibernate thực thi các API chuẩn, chuyển thao tác entity/query thành SQL và quản lý persistence context. Ngoài phần chuẩn, Hibernate cung cấp extension để kiểm soát fetching, filter, type mapping, cache, SQL và các hành vi chuyên sâu.

**Spring Data JPA** là một lớp abstraction ở phía trên Jakarta Persistence. Nó giúp tạo repository, derived query, pagination, sorting, projection và tích hợp transaction của Spring. Spring Data JPA thường sử dụng Hibernate làm provider trong ứng dụng Spring Boot, nhưng bản thân Spring Data JPA không phải Hibernate và cũng không phải đặc tả Jakarta Persistence.

Mối quan hệ có thể hình dung:

```text
Application service
       |
Spring Data JPA repositories
       |
Jakarta Persistence API (EntityManager, JPQL, mapping)
       |
Hibernate ORM (provider + Hibernate extensions)
       |
JDBC driver
       |
Relational database
```

Ứng dụng có thể dùng trực tiếp `EntityManager` mà không cần repository abstraction. Spring Data JPA chỉ giúp giảm mã truy cập dữ liệu; Hibernate là provider thực hiện persistence khi được cấu hình làm implementation.

## 2. Nhận diện package và dependency

Từ Spring Boot 3 trở đi, ứng dụng dùng namespace `jakarta.persistence.*`. Các phiên bản Spring Boot 2.x trước đó dùng namespace `javax.persistence.*`.

| Thành phần | Namespace thường gặp |
|---|---|
| Jakarta Persistence chuẩn | `jakarta.persistence.*` |
| JPA đời cũ trước Jakarta | `javax.persistence.*` |
| Hibernate extension | `org.hibernate.*`, thường là `org.hibernate.annotations.*` |
| Spring Data JPA | `org.springframework.data.jpa.*` |
| Spring transaction annotation | `org.springframework.transaction.annotation.*` |

Ví dụ import chuẩn:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.FetchType;
import jakarta.persistence.EntityManager;
```

Ví dụ import extension:

```java
import org.hibernate.annotations.BatchSize;
import org.hibernate.annotations.Fetch;
import org.hibernate.annotations.FetchMode;
import org.hibernate.annotations.Formula;
```

Ví dụ import Spring Data:

```java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.EntityGraph;
```

Không trộn `javax.persistence` và `jakarta.persistence` trong cùng một ứng dụng Hibernate/JPA. Annotation từ hai namespace là các kiểu Java khác nhau; provider Jakarta không tự xem annotation `javax.persistence.Entity` là `jakarta.persistence.Entity`.

Với Spring Boot, ưu tiên dùng starter và dependency management của Boot:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    runtimeOnly("org.postgresql:postgresql")
}
```

Starter quản lý các dependency tương thích cho Spring Data JPA, Hibernate và Jakarta Persistence. Tránh tự nâng riêng `hibernate-core` lên một phiên bản không được Spring Boot BOM hỗ trợ nếu chưa kiểm tra compatibility matrix và migration guide.

## 3. Những API và annotation thuộc chuẩn Jakarta Persistence

Các ví dụ sau thuộc API chuẩn và có thể dùng với provider Jakarta Persistence tương thích.

### Entity và mapping

```java
import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "country_id")
    private Country country;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Các annotation như `@Entity`, `@Table`, `@Id`, `@Column`, `@ManyToOne`, `@JoinColumn` và `FetchType` thuộc Jakarta Persistence. Hibernate triển khai cách diễn giải chúng nhưng không sở hữu các annotation này.

### EntityManager và persistence context

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerLookup {

    @PersistenceContext
    private EntityManager entityManager;

    public Customer find(Long id) {
        return entityManager.find(Customer.class, id);
    }
}
```

`EntityManager` là API chuẩn để persist, find, merge, remove, flush, refresh và tạo query. Hibernate cung cấp implementation cho API này khi được dùng làm provider.

### JPQL và Criteria API

JPQL truy vấn theo entity name và property Java, không truy vấn trực tiếp tên bảng/cột như SQL:

```java
List<Customer> customers = entityManager.createQuery("""
    select c
    from Customer c
    where c.name like :prefix
    order by c.name
    """, Customer.class)
    .setParameter("prefix", "An%")
    .getResultList();
```

Criteria API là API chuẩn để xây dựng query có cấu trúc bằng Java:

```java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<Customer> query = cb.createQuery(Customer.class);
Root<Customer> customer = query.from(Customer.class);

query.select(customer)
     .where(cb.like(customer.get("name"), "An%"));

List<Customer> result = entityManager.createQuery(query)
        .getResultList();
```

JPQL và Criteria API là lựa chọn tốt khi cần giữ khả năng chuyển provider. Native SQL cũng được Jakarta Persistence hỗ trợ, nhưng nội dung SQL có thể phụ thuộc database.

### EntityGraph và locking

`@NamedEntityGraph`, `EntityGraph`, `LockModeType` và các API chuẩn liên quan giúp khai báo dữ liệu cần tải và chiến lược khóa mà không cần dùng API riêng của Hibernate.

Ví dụ:

```java
@Entity
@NamedEntityGraph(
    name = "Customer.withCountry",
    attributeNodes = @NamedAttributeNode("country")
)
public class Customer {
    // mapping entity
}
```

Spring Data JPA có thể dùng graph đó trên repository method bằng annotation `org.springframework.data.jpa.repository.EntityGraph`. Annotation repository là API của Spring Data, còn graph và metadata entity graph là khái niệm thuộc Jakarta Persistence.

## 4. Những tính năng riêng thường gặp của Hibernate

Các extension sau không phải annotation/API chuẩn của Jakarta Persistence. Chúng hữu ích khi ứng dụng chủ động dùng Hibernate và chấp nhận phụ thuộc provider.

| Extension | Mục đích |
|---|---|
| `@BatchSize` | Gom việc tải lazy entity/collection thành batch để giảm N+1. |
| `@Fetch` và `FetchMode.SUBSELECT` | Điều khiển chiến lược fetching cụ thể của Hibernate. |
| `@Formula` | Ánh xạ một thuộc tính đọc từ biểu thức SQL. |
| `@NaturalId` | Đánh dấu khóa nghiệp vụ tự nhiên để Hibernate hỗ trợ lookup/cache. |
| `@FilterDef` và `@Filter` | Định nghĩa filter có thể bật/tắt theo Session. |
| `@Cache` và `CacheConcurrencyStrategy` | Cấu hình second-level cache theo cơ chế Hibernate. |
| `@JdbcTypeCode` và `SqlTypes` | Chỉ định JDBC type mapping của Hibernate, ví dụ kiểu JSON tùy database. |
| `Session` và `StatelessSession` | API truy cập và xử lý dữ liệu riêng của Hibernate. |

Tên và khả năng của extension có thể thay đổi giữa các major version. Hãy đối chiếu Javadoc và migration guide đúng phiên bản Hibernate mà Spring Boot đang quản lý.

## 5. Ví dụ: batch fetching bằng @BatchSize

Jakarta Persistence có `FetchType.LAZY` nhưng không định nghĩa annotation chuẩn để chỉ định batch size của lazy association. Hibernate bổ sung `@BatchSize`.

```java
import jakarta.persistence.*;
import org.hibernate.annotations.BatchSize;
import java.util.ArrayList;
import java.util.List;

@Entity
public class PurchaseOrder {

    @Id
    private Long id;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    @BatchSize(size = 32)
    private List<OrderItem> items = new ArrayList<>();

    protected PurchaseOrder() {
    }
}
```

Khi ứng dụng truy cập nhiều collection lazy, Hibernate có thể tải một nhóm collection bằng một câu query có điều kiện `IN`, thay vì phát một query riêng cho từng parent. Kết quả thực tế phụ thuộc số association cần tải, persistence context, batch size và provider version.

`@BatchSize` là extension Hibernate. Nếu cần chuyển sang provider khác, phải tìm chiến lược tương đương hoặc đổi fetch plan bằng EntityGraph, fetch join hay projection.

Cấu hình batch size mặc định ở mức Hibernate có thể đặt trong cấu hình ứng dụng:

```yaml
spring:
  jpa:
    properties:
      hibernate.default_batch_fetch_size: 32
```

Đây là Hibernate property, không phải property chuẩn của Jakarta Persistence. Không đặt batch size quá lớn theo cảm tính; hãy đo SQL, kích thước kết quả và thời gian thực thi với dữ liệu đại diện.

## 6. Ví dụ: @Fetch và FetchMode.SUBSELECT

Hibernate có `@Fetch` để chỉ định cách tải một association:

```java
import jakarta.persistence.*;
import org.hibernate.annotations.Fetch;
import org.hibernate.annotations.FetchMode;

@Entity
public class Department {

    @Id
    private Long id;

    @OneToMany(mappedBy = "department", fetch = FetchType.LAZY)
    @Fetch(FetchMode.SUBSELECT)
    private List<Employee> employees;
}
```

Với `FetchMode.SUBSELECT`, Hibernate có thể tải collection của các parent đã được tải trong cùng persistence context bằng một truy vấn subselect. Điều này có thể giảm N+1 trong một số use case, nhưng có thể tải nhiều collection hơn dự kiến nếu persistence context chứa nhiều parent.

`@Fetch` và `FetchMode` là extension Hibernate. Chúng không thay thế việc hiểu rõ fetch plan. Với một màn hình cụ thể, EntityGraph hoặc fetch join thường diễn đạt rõ dữ liệu cần tải hơn; batch/subselect phù hợp khi lazy association được truy cập theo nhóm.

Không kết hợp tùy tiện nhiều collection fetch cùng lúc. Hãy kiểm tra SQL và số hàng trả về vì join hoặc subselect đều có thể tạo chi phí đáng kể.

## 7. Ví dụ: @Formula cho thuộc tính tính từ SQL

`@Formula` cho phép ánh xạ một thuộc tính read-only từ biểu thức SQL do Hibernate đưa vào câu SELECT:

```java
import jakarta.persistence.*;
import org.hibernate.annotations.Formula;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {

    @Id
    private Long id;

    @Column(nullable = false)
    private BigDecimal price;

    @Column(nullable = false)
    private BigDecimal taxRate;

    @Formula("price * tax_rate")
    private BigDecimal priceWithTax;
}
```

Biểu thức trong `@Formula` là SQL theo schema/database, không phải JPQL. Tên cột và cú pháp cần khớp database thực tế. Giá trị được đọc từ kết quả query; ứng dụng không gán và persist trực tiếp thuộc tính formula như một cột thông thường.

Ưu điểm là có thể lấy giá trị tính toán cùng entity mà không cần viết lại phép tính ở mọi query. Hạn chế là biểu thức phụ thuộc SQL dialect, có thể làm query phức tạp và khó chuyển sang provider khác. Nếu phép tính là logic nghiệp vụ hoặc cần portability, cân nhắc tính trong Java, DTO projection hoặc view/database generated column theo yêu cầu.

## 8. Ví dụ: @NaturalId cho khóa nghiệp vụ

Khóa chính thường là ID kỹ thuật. Một số domain có khóa nghiệp vụ duy nhất, ví dụ mã quốc gia hoặc mã SKU. Hibernate cung cấp `@NaturalId` để đánh dấu thuộc tính tự nhiên:

```java
import jakarta.persistence.*;
import org.hibernate.annotations.NaturalId;

@Entity
@Table(
    name = "countries",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_country_code",
        columnNames = "code"
    )
)
public class Country {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NaturalId
    @Column(nullable = false, length = 2)
    private String code;

    protected Country() {
    }
}
```

Có thể lookup bằng Hibernate Session:

```java
import org.hibernate.Session;

Country country = entityManager.unwrap(Session.class)
        .byNaturalId(Country.class)
        .using("code", "VN")
        .load();
```

`@NaturalId` và API `byNaturalId()` là Hibernate-specific. Ràng buộc unique trong database vẫn rất quan trọng: annotation không thay thế constraint ở database và không tự bảo đảm tính duy nhất khi có concurrent transaction.

Nếu muốn giữ portability, có thể dùng query chuẩn:

```java
Country country = entityManager.createQuery("""
    select c from Country c where c.code = :code
    """, Country.class)
    .setParameter("code", "VN")
    .getSingleResult();
```

## 9. Ví dụ: @Filter theo tenant hoặc trạng thái

Hibernate filter cho phép định nghĩa điều kiện có tham số và bật nó theo từng Session. Đây là tính năng provider-specific.

```java
import jakarta.persistence.*;
import org.hibernate.annotations.Filter;
import org.hibernate.annotations.FilterDef;
import org.hibernate.annotations.ParamDef;

@Entity
@Table(name = "documents")
@FilterDef(
    name = "tenantFilter",
    parameters = @ParamDef(name = "tenantId", type = Long.class)
)
@Filter(
    name = "tenantFilter",
    condition = "tenant_id = :tenantId"
)
public class Document {

    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    private String title;
}
```

Bật filter trên Hibernate Session:

```java
import org.hibernate.Session;

Session session = entityManager.unwrap(Session.class);
session.enableFilter("tenantFilter")
       .setParameter("tenantId", currentTenantId);

List<Document> documents = entityManager.createQuery(
        "select d from Document d", Document.class)
    .getResultList();
```

Điều kiện filter được áp dụng khi Hibernate thực hiện query phù hợp trong Session đã bật filter. Filter không tự bật ở mọi Session; phải có quy trình bật đúng tenant trước khi truy vấn.

Không dùng Hibernate filter làm lớp bảo mật duy nhất cho multi-tenancy. Native SQL, JDBC trực tiếp, query không được filter hoặc cấu hình sai có thể đi ngoài cơ chế này. Với dữ liệu tenant nhạy cảm, cân nhắc database row-level security, schema/database tách biệt, authorization ở service và kiểm thử xuyên tenant. Không cho phép client tự chọn tenant ID mà không xác thực quyền.

## 10. Second-level cache: chuẩn và extension

Jakarta Persistence định nghĩa một số API và annotation liên quan đến shared cache, ví dụ `@Cacheable`, `CacheRetrieveMode`, `CacheStoreMode` và `EntityManagerFactory.getCache()`.

Hibernate cung cấp thêm cách cấu hình cache region, concurrency strategy và tích hợp cache provider:

```java
import jakarta.persistence.*;
import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;

@Entity
@Cacheable
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "reference-data"
)
public class Country {
    // ...
}
```

Trong ví dụ, `@Cacheable` là annotation chuẩn Jakarta Persistence; `@Cache` và `CacheConcurrencyStrategy` là Hibernate-specific. Chỉ thêm annotation không đủ để bảo đảm cache hoạt động: cần cấu hình second-level cache và provider phù hợp với phiên bản Hibernate.

Không bật cache cho mọi entity. Dữ liệu thay đổi thường xuyên, cần tính nhất quán cao hoặc có nhiều đường cập nhật ngoài Hibernate có thể không phù hợp. Hãy xác định invalidation, cache region, concurrency strategy và đo hit/miss trước khi áp dụng.

## 11. Hibernate Session và API unwrap

Trong code dùng Jakarta Persistence, `EntityManager` là abstraction chuẩn. Khi cần một tính năng chỉ có trong Hibernate, có thể lấy native Session qua `unwrap()`:

```java
import jakarta.persistence.EntityManager;
import org.hibernate.Session;

public void inspectHibernate(EntityManager entityManager) {
    Session session = entityManager.unwrap(Session.class);

    // Dùng API Hibernate tại đây khi thực sự cần.
    boolean open = session.isOpen();
}
```

Cách này giữ phần lớn code ở API chuẩn và khoanh vùng dependency Hibernate tại nơi cần extension. Không ép cast trực tiếp `EntityManager` sang `Session` vì proxy/wrapper của framework có thể không phải instance trực tiếp. `unwrap()` là cơ chế chuẩn của Jakarta Persistence để truy cập vendor-specific interface.

`StatelessSession` cũng là API riêng của Hibernate. Nó bỏ qua persistence context thông thường, dirty checking và nhiều hành vi lifecycle/cascade. Nó có thể hữu ích cho xử lý dữ liệu khối lượng lớn nhưng cần tự quản lý các hành vi mà entity managed thường cung cấp. Không thay `EntityManager` bằng `StatelessSession` nếu nghiệp vụ phụ thuộc dirty checking hoặc cascade.

## 12. JPQL, HQL và Native SQL

Ba dạng query cần được phân biệt:

| Query | Thuộc lớp nào | Cú pháp tham chiếu |
|---|---|---|
| JPQL | Jakarta Persistence | Entity name và property Java |
| HQL | Hibernate Query Language | Ngôn ngữ query của Hibernate, mở rộng JPQL |
| Native SQL | Database/JDBC | Tên bảng, cột và cú pháp SQL |

Ví dụ JPQL:

```java
select p from Product p where p.price > :minPrice
```

Ví dụ SQL:

```sql
select * from products where price > ?
```

HQL có nhiều khả năng mở rộng theo phiên bản Hibernate. Một số HQL có thể không hợp lệ với JPQL hoặc provider khác. Nếu query dùng cú pháp đặc thù Hibernate, ghi nhận rõ dependency đó trong repository và kiểm thử khi nâng phiên bản.

Trong Spring Data JPA, `@Query` là annotation của Spring Data. Mặc định query dạng JPQL nếu không đặt `nativeQuery = true`; `@Query` không phải annotation của Jakarta Persistence hay Hibernate.

## 13. Phân biệt annotation của Spring, Jakarta và Hibernate

Một số annotation có tên gần nhau nhưng thuộc các lớp khác nhau:

| Annotation/API | Chủ sở hữu | Vai trò |
|---|---|---|
| `@Entity`, `@Id`, `@OneToMany` | Jakarta Persistence | Mapping entity chuẩn |
| `EntityManager`, JPQL | Jakarta Persistence | API và ngôn ngữ persistence chuẩn |
| `@BatchSize`, `@Formula`, `@Filter` | Hibernate | Extension của provider |
| `Session`, `SessionFactory` | Hibernate | API native của provider |
| `JpaRepository`, `@Query`, `@Modifying` | Spring Data JPA | Repository abstraction và query method |
| `@Transactional` của Spring | Spring Framework | Transaction management qua proxy/interceptor |
| `@Transactional` của Jakarta Transactions | Jakarta Transactions | Annotation transaction chuẩn cho môi trường tương ứng |

Ví dụ, `org.springframework.transaction.annotation.Transactional` và `jakarta.transaction.Transactional` không cùng package và không phải cùng một class. Ứng dụng Spring thường dùng annotation của Spring để tận dụng các tính năng transaction của framework. Đọc đúng import giúp tránh hiểu nhầm annotation nào đang điều khiển transaction.

## 14. Khi nào nên dùng chuẩn, khi nào nên dùng extension?

Ưu tiên API chuẩn khi:

- Tạo entity và mapping quan hệ thông thường.
- Viết JPQL hoặc Criteria query có thể diễn đạt bằng chuẩn.
- Quản lý entity lifecycle qua `EntityManager`.
- Dùng EntityGraph, pagination và locking chuẩn.
- Viết thư viện dùng chung hoặc code có yêu cầu chuyển provider.

Cân nhắc extension Hibernate khi:

- Đã đo được vấn đề hiệu năng và extension giải quyết đúng nguyên nhân.
- Cần batch fetching hoặc chiến lược fetching chuyên sâu.
- Cần mapping SQL formula hoặc JDBC type đặc thù.
- Cần natural ID, filter hoặc cache region theo Hibernate.
- Ứng dụng đã xác định Hibernate là provider mục tiêu và có kế hoạch kiểm thử nâng cấp.

Một extension không mặc nhiên tốt hơn API chuẩn. Nó có thể giảm SQL hoặc giúp mapping gọn hơn, nhưng cũng tăng phụ thuộc provider và làm việc migration phức tạp hơn. Chọn extension vì nhu cầu đo được, ghi lại lý do và cô lập nó ở repository/domain mapping phù hợp.

## 15. Quản lý version và kiểm thử khi nâng cấp

Jakarta Persistence là đặc tả có version; Hibernate ORM cũng có version và migration guide riêng. Một ứng dụng cần đảm bảo provider hỗ trợ phiên bản Persistence API mà framework đang sử dụng.

Khi nâng Spring Boot hoặc Hibernate:

1. Kiểm tra Spring Boot release notes và dependency management để biết Hibernate version được quản lý.
2. Đọc Hibernate migration guide giữa các major version đang nâng cấp.
3. Tìm các import `javax.persistence` còn sót khi chuyển sang Jakarta.
4. Kiểm tra extension `org.hibernate.annotations.*` đã đổi package, signature hoặc behavior chưa.
5. Kiểm thử query HQL, native SQL, custom type, filter, cache và fetching.
6. Chạy integration test trên database thật hoặc Testcontainers nếu hành vi phụ thuộc dialect, locking hay JDBC type.
7. Đo lại SQL và hiệu năng; không giả định fetch plan hoặc cache hoạt động giống phiên bản trước.

Tránh override Hibernate version đơn lẻ chỉ để dùng một annotation mới. Nâng đồng bộ framework/provider theo compatibility matrix giúp giảm lỗi runtime do API không tương thích.

## 16. Ví dụ chiến lược giữ code portable nhưng vẫn dùng extension

Có thể tổ chức repository theo hướng query chính dùng API chuẩn, còn extension được giới hạn ở mapping hoặc một adapter nhỏ.

Ví dụ service chỉ phụ thuộc repository:

```java
@Service
@Transactional(readOnly = true)
public class ProductService {

    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }

    public List<ProductSummary> search(String keyword) {
        return products.searchSummaries(keyword);
    }
}
```

Repository có thể dùng JPQL DTO projection chuẩn về mặt ngôn ngữ:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query("""
        select new com.example.store.ProductSummary(p.id, p.name)
        from Product p
        where p.name like concat('%', :keyword, '%')
        """)
    List<ProductSummary> searchSummaries(
            @Param("keyword") String keyword);
}
```

Nếu cần batch fetching, extension có thể nằm trên mapping association bằng `@BatchSize`. Service không cần biết Hibernate đang gom lazy load thế nào. Tuy nhiên, entity mapping vẫn phụ thuộc Hibernate; cần ghi nhận điều đó trong tài liệu kiến trúc và test.

## 17. Checklist trước khi chọn tính năng

- Xác định tính năng thuộc Jakarta Persistence, Spring Data JPA, Spring Framework hay Hibernate.
- Kiểm tra package import trước khi thêm annotation.
- Dùng namespace `jakarta.persistence` với Spring Boot 3+; đồng bộ version dependency.
- Ưu tiên API chuẩn nếu đáp ứng được use case.
- Chỉ dùng Hibernate extension khi có lợi ích rõ ràng và chấp nhận phụ thuộc provider.
- Cô lập API `Session`/Hibernate trong phần code cần thiết; dùng `EntityManager.unwrap()` thay vì cast tùy tiện.
- Đo SQL, số hàng, thời gian và bộ nhớ trước/sau khi đổi fetch strategy.
- Đọc Javadoc và migration guide đúng phiên bản.
- Thêm integration test cho mapping, query, cache, filter và behavior phụ thuộc database.

Jakarta Persistence định nghĩa hợp đồng chung; Hibernate cung cấp implementation và extension. Hiểu rõ ranh giới này giúp tận dụng tính năng Hibernate khi cần mà vẫn giữ phần lớn ứng dụng dễ kiểm thử, nâng cấp và bảo trì.