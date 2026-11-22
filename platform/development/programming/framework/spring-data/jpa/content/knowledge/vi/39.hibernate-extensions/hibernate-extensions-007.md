# Khóa tự nhiên và khả năng truy xuất đặc thù Hibernate

Khóa tự nhiên (natural key hoặc natural ID) là một hay nhiều thuộc tính nghiệp vụ có thể nhận diện duy nhất một bản ghi, chẳng hạn mã ISBN của sách, mã quốc gia, mã SKU hoặc email trong phạm vi một tenant. Khóa chính (primary key) thường là định danh kỹ thuật do hệ thống quản lý, ví dụ một giá trị `Long` được sinh tự động.

Hibernate hỗ trợ đánh dấu natural ID bằng `@NaturalId`, tìm entity bằng API `Session.byNaturalId()` hoặc `Session.bySimpleNaturalId()`, và cache ánh xạ natural ID sang primary key bằng `@NaturalIdCache`. Đây là các tiện ích riêng của Hibernate, không thuộc API chuẩn JPA. Chúng hữu ích khi ứng dụng thường xuyên tìm entity theo khóa nghiệp vụ và muốn mô tả rõ khóa đó trong mapping.

## 1. Khóa chính và khóa tự nhiên

Hai loại khóa phục vụ những mục đích khác nhau:

| Tiêu chí | Khóa chính (surrogate key) | Khóa tự nhiên |
|---|---|---|
| Ý nghĩa | Định danh kỹ thuật | Định danh có ý nghĩa nghiệp vụ |
| Ví dụ | `customer.id = 8124` | `tenantId = 7, email = "a@example.com"` |
| Tính ổn định | Thường không thay đổi | Có thể bất biến hoặc thay đổi theo nghiệp vụ |
| Được dùng trong quan hệ | Thường là FK của các bảng khác | Thường dùng để tra cứu hoặc tích hợp |
| Sinh giá trị | Sequence, identity, UUID hoặc ứng dụng | Từ dữ liệu nghiệp vụ |
| Phạm vi duy nhất | Theo bảng/entity | Có thể duy nhất toàn hệ thống hoặc chỉ trong một phạm vi |

Một mô hình phổ biến là dùng surrogate primary key cho quan hệ nội bộ, đồng thời khai báo natural ID cho khóa nghiệp vụ. Điều này giúp các bảng liên quan giữ FK ổn định ngay cả khi một thuộc tính nghiệp vụ như email hoặc mã hiển thị thay đổi.

Không phải thuộc tính có vẻ duy nhất ở thời điểm hiện tại đều phù hợp làm natural ID. Một khóa tốt nên có quy tắc duy nhất rõ ràng, giá trị chuẩn hóa nhất quán và ít thay đổi. Số điện thoại, email, tên người dùng hoặc mã do đối tác cấp có thể thay đổi hoặc được tái sử dụng; cần đánh giá chính sách nghiệp vụ trước khi chọn.

## 2. Bảo đảm tính duy nhất ở database

`@NaturalId` mô tả khóa nghiệp vụ cho Hibernate, nhưng database vẫn cần ràng buộc unique để bảo vệ dữ liệu trước các request đồng thời, script SQL và ứng dụng khác.

Ví dụ email chỉ duy nhất trong phạm vi tenant:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

import org.hibernate.annotations.NaturalId;

@Entity
@Table(
    name = "customer",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customer_tenant_email",
        columnNames = {"tenant_id", "email_normalized"}
    )
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NaturalId
    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @NaturalId
    @Column(name = "email_normalized", nullable = false, length = 254)
    private String emailNormalized;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    protected Customer() {
    }

    public Customer(Long tenantId, String emailNormalized, String displayName) {
        this.tenantId = tenantId;
        this.emailNormalized = emailNormalized;
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public String getEmailNormalized() {
        return emailNormalized;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

Trong ví dụ, natural ID là tổ hợp `tenantId` và `emailNormalized`, không phải riêng email. Hai khách hàng ở hai tenant khác nhau có thể dùng cùng email nếu nghiệp vụ cho phép.

Với migration production, nên tạo unique constraint bằng Flyway hoặc Liquibase và kiểm tra dữ liệu trùng trước khi áp dụng. Annotation `@UniqueConstraint` mô tả schema cho công cụ tạo schema; nó không tự sửa dữ liệu đang trùng và không thay thế migration có kiểm soát.

### 2.1. Chuẩn hóa giá trị trước khi lưu và tìm kiếm

Quy tắc chuẩn hóa phải giống nhau ở cả lúc ghi và lúc truy xuất. Ví dụ, nếu nghiệp vụ xem email không phân biệt chữ hoa/thường, ứng dụng có thể lưu một giá trị chuẩn hóa trong `email_normalized`. Không nên chỉ lowercase ở truy vấn mà lưu dữ liệu gốc không theo cùng quy tắc.

Cần quyết định rõ:

- Có loại bỏ khoảng trắng đầu/cuối không?
- Có phân biệt chữ hoa/thường không?
- Unicode được chuẩn hóa theo dạng nào nếu dữ liệu cho phép?
- Mã có dấu gạch, khoảng trắng hoặc ký tự phân cách được xử lý thế nào?
- Khóa có duy nhất toàn hệ thống hay chỉ theo tenant/organization?

Với yêu cầu không phân biệt hoa thường, có thể dùng cột chuẩn hóa hoặc functional unique index tùy database. Quy tắc ở database và ứng dụng phải nhất quán. Đặc biệt, không nên tự ý lowercase mọi phần của email nếu quy tắc nghiệp vụ hoặc hệ thống nguồn yêu cầu giữ nguyên; hãy xác định semantics trước.

Không dựa vào bước kiểm tra `existsByEmail(...)` để bảo đảm duy nhất. Hai transaction có thể cùng kiểm tra “chưa tồn tại” rồi cùng insert. Unique constraint ở database mới là hàng rào cuối cùng; ứng dụng cần xử lý lỗi vi phạm constraint phù hợp.

## 3. Đánh dấu natural ID bằng @NaturalId

`@NaturalId` là annotation riêng của Hibernate, thuộc package `org.hibernate.annotations`. Có thể đặt trên một thuộc tính hoặc nhiều thuộc tính để tạo khóa tự nhiên tổng hợp.

Mặc định, natural ID được xem là bất biến (`mutable = false`). Điều này phù hợp với mã sản phẩm, mã quốc gia hoặc mã định danh được nghiệp vụ cam kết không đổi.

```java
@NaturalId
@Column(nullable = false, unique = true)
private String sku;
```

Nếu khóa nghiệp vụ được phép thay đổi, phải khai báo rõ:

```java
@NaturalId(mutable = true)
@Column(nullable = false)
private String emailNormalized;
```

Với khóa tổng hợp, đánh dấu từng thuộc tính tham gia khóa bằng `@NaturalId`. Các thuộc tính đó cùng xác định một entity. Hãy đảm bảo unique constraint ở database phản ánh đúng cùng tập thuộc tính.

`@NaturalId` không biến thuộc tính thành `@Id`, không tự sinh primary key và không thay thế foreign key. Entity vẫn có thể dùng surrogate key làm `@Id`.

## 4. Truy xuất bằng Hibernate Session API

JPA `EntityManager.find()` tìm entity theo primary key. Để tìm theo natural ID, Hibernate cung cấp API chuyên biệt trên `Session`.

### 4.1. Natural ID gồm một thuộc tính

Nếu entity có đúng một thuộc tính natural ID duy nhất, dùng `bySimpleNaturalId()`. Để ví dụ này độc lập với `Customer` ở mục 2 (có natural ID tổng hợp), ta dùng entity `Product` với SKU là natural ID đơn:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

import org.hibernate.annotations.NaturalId;

@Entity
@Table(
    name = "product",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_product_sku",
        columnNames = "sku"
    )
)
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NaturalId
    @Column(nullable = false, length = 64)
    private String sku;

    protected Product() {
    }

    public Product(String sku) {
        this.sku = sku;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }
}
```

Lookup bằng Hibernate Session:

```java
import java.util.Optional;

import jakarta.persistence.EntityManager;

import org.hibernate.Session;
import org.springframework.stereotype.Repository;

@Repository
public class ProductLookup {

    private final EntityManager entityManager;

    public ProductLookup(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    public Optional<Product> findBySku(String sku) {
        Session session = entityManager.unwrap(Session.class);

        Product product = session
                .bySimpleNaturalId(Product.class)
                .load(sku);

        return Optional.ofNullable(product);
    }
}
```

`load()` trả về entity nếu tìm thấy và `null` nếu không có kết quả. Đoạn code chuyển kết quả thành `Optional` để API của repository không phải trả `null` cho caller. `bySimpleNaturalId()` phù hợp ở đây vì `Product` chỉ có một thuộc tính được đánh dấu `@NaturalId`.

### 4.2. Natural ID gồm nhiều thuộc tính

Với natural ID tổng hợp, dùng `byNaturalId()` và truyền từng thuộc tính bằng tên property của entity:

```java
public Optional<Customer> findByTenantAndEmail(
        Long tenantId,
        String normalizedEmail) {

    Session session = entityManager.unwrap(Session.class);

    Customer customer = session
            .byNaturalId(Customer.class)
            .using("tenantId", tenantId)
            .using("emailNormalized", normalizedEmail)
            .load();

    return Optional.ofNullable(customer);
}
```

Tên trong `using()` là tên thuộc tính Java được Hibernate mapping, ví dụ `emailNormalized`, không phải tên cột database `email_normalized`.

### 4.3. Dùng trong transaction của service

Nên thực hiện lookup trong transaction/service method phù hợp để vòng đời Hibernate Session rõ ràng:

```java
@Service
public class CustomerQueryService {

    private final CustomerLookup customerLookup;

    public CustomerQueryService(CustomerLookup customerLookup) {
        this.customerLookup = customerLookup;
    }

    @Transactional(readOnly = true)
    public CustomerResponse getCustomer(
            Long tenantId,
            String normalizedEmail) {

        Customer customer = customerLookup
                .findByTenantAndEmail(tenantId, normalizedEmail)
                .orElseThrow(() -> new CustomerNotFoundException());

        return new CustomerResponse(
                customer.getId(),
                customer.getDisplayName()
        );
    }
}
```

Ví dụ giả định có `CustomerResponse` và `CustomerNotFoundException` trong ứng dụng. Ánh xạ DTO trong transaction giúp response không phụ thuộc vào việc serializer có tiếp tục truy cập quan hệ lazy sau khi Session đóng hay không.

Không cần dùng Hibernate API chỉ vì muốn tìm theo một trường. Spring Data JPA có thể tạo truy vấn theo tên phương thức hoặc `@Query`; hãy chọn API chuyên biệt khi cần semantics natural ID, khả năng dùng natural-id cache hoặc các tính năng Hibernate liên quan.

## 5. Natural ID và first-level cache

Trong một Hibernate Session, Hibernate duy trì persistence context (first-level cache) và thông tin tra cứu natural ID tương ứng. Khi lookup cùng natural ID nhiều lần trong cùng Session, Hibernate có thể tìm entity đã được quản lý mà không cần chạy lại truy vấn database.

Điều này có nghĩa query count trong một Session có thể khác query count giữa nhiều Session. First-level cache chỉ tồn tại trong phạm vi persistence context; khi transaction/request kết thúc và Session đóng, trạng thái này không phải cache dùng chung lâu dài.

Cần phân biệt:

- **Persistence context/L1:** quản lý entity instance trong một Session.
- **Natural-id cross-reference:** ánh xạ natural ID sang entity identifier trong phạm vi Session.
- **Natural ID cache:** cache chia sẻ ánh xạ natural ID sang primary key giữa các Session nếu được cấu hình.
- **Entity second-level cache:** cache trạng thái entity theo primary key.
- **Query cache:** cache kết quả truy vấn theo cơ chế riêng của Hibernate.

Các lớp cache này giải quyết những vấn đề khác nhau. Bật một loại không có nghĩa mọi loại khác cũng tự động bật.

## 6. Cache natural ID với @NaturalIdCache

Hibernate hỗ trợ `@NaturalIdCache` để cache ánh xạ natural ID sang primary key. Điều này hữu ích khi ứng dụng thường xuyên lookup cùng khóa nghiệp vụ qua nhiều Session.

Ví dụ:

```java
import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;
import org.hibernate.annotations.NaturalIdCache;

@Entity
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "customer-entity"
)
@NaturalIdCache(region = "customer-natural-id")
public class Customer {
    // @Id và các thuộc tính @NaturalId
}
```

Cần bật second-level cache và cấu hình cache provider tương thích với version Hibernate đang dùng. Ví dụ ở mức thuộc tính Hibernate:

```properties
spring.jpa.properties.hibernate.cache.use_second_level_cache=true
spring.jpa.properties.hibernate.cache.region.factory_class=jcache
```

Cấu hình `jcache` yêu cầu module tích hợp JCache của Hibernate và một JCache provider như Ehcache hoặc provider khác. Region `customer-natural-id` phải được quản lý với giới hạn dung lượng và chính sách hết hạn phù hợp theo provider. Tên region trong annotation phải khớp cấu hình cache nếu provider yêu cầu khai báo tường minh.

Natural ID cache lưu ánh xạ khóa nghiệp vụ sang primary key; nó không nhất thiết lưu toàn bộ trạng thái entity. Khi lookup thành công, Hibernate có thể tiếp tục lấy trạng thái entity từ entity L2 cache hoặc database. Vì vậy, natural ID cache và entity cache là hai region có mục đích khác nhau.

### 6.1. Khi nào nên cache natural ID?

Phù hợp khi:

- Ứng dụng thường xuyên tìm entity bằng một natural ID ổn định.
- Tỷ lệ đọc cao hơn nhiều so với cập nhật.
- Khóa tự nhiên có quy tắc duy nhất rõ ràng.
- Có cache provider với dung lượng và eviction được kiểm soát.
- Hệ thống có chiến lược invalidation phù hợp khi dữ liệu thay đổi.

Không nên cache tự động mọi natural ID. Nếu khóa thay đổi thường xuyên hoặc dữ liệu cần tính mới tức thời từ nhiều ứng dụng, lợi ích có thể không bù được chi phí đồng bộ cache.

### 6.2. Theo dõi hiệu quả cache

Có thể bật Hibernate statistics trong môi trường kiểm thử hoặc quan sát có kiểm soát:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Theo dõi natural-id cache hit, miss, put, entity cache hit/miss, số SQL và thời gian truy vấn. Khi đánh giá, dùng Session mới để phân biệt cache chia sẻ với first-level cache trong cùng Session.

Không suy ra cache hoạt động tốt chỉ vì lần lookup thứ hai trong cùng transaction không phát sinh SQL. Đó có thể chỉ là hiệu quả của persistence context.

## 7. Natural ID có thể thay đổi

Một natural ID thường nên bất biến. Tuy nhiên, một số thuộc tính như email hoặc username có thể thay đổi theo nghiệp vụ. Với trường hợp này, khai báo `@NaturalId(mutable = true)` và cập nhật entity đang được quản lý trong transaction.

```java
@NaturalId(mutable = true)
@Column(name = "email_normalized", nullable = false)
private String emailNormalized;

public void changeEmail(String newNormalizedEmail) {
    this.emailNormalized = newNormalizedEmail;
}
```

Khi cập nhật, Hibernate cần đồng bộ natural-id cross-reference của Session và natural-id cache để lookup khóa cũ/mới không trả kết quả sai. Cập nhật qua vòng đời entity được quản lý cho phép Hibernate nhận biết thay đổi.

Với natural ID mutable, một số lookup có thể yêu cầu Hibernate đồng bộ các thay đổi đang chờ trong Session trước khi tra cứu. Hibernate cung cấp tùy chọn tắt synchronization cho một lookup cụ thể, nhưng chỉ nên làm vậy khi chắc chắn Session không có thay đổi natural ID chưa được đồng bộ. Tắt đồng bộ không đúng lúc có thể khiến kết quả tra cứu không phản ánh trạng thái hiện tại trong persistence context.

Nếu nghiệp vụ cho phép, dùng khóa tự nhiên bất biến sẽ đơn giản hơn cho cache, đồng bộ và quan hệ tích hợp. Nếu bắt buộc phải thay đổi, cần kiểm thử cả lookup bằng giá trị cũ, giá trị mới, flush/clear và cache sau commit.

### 7.1. Tránh cập nhật natural ID bằng SQL trực tiếp

Câu UPDATE trực tiếp hoặc bulk JPQL bỏ qua vòng đời entity. Hibernate không tự biết mọi natural ID đã thay đổi ngoài Session. Sau cập nhật kiểu này, persistence context có thể còn dữ liệu cũ và natural-id cache có thể cần invalidation.

Nếu phải cập nhật bằng SQL trực tiếp:

1. Thực hiện trong transaction được kiểm soát.
2. Xác định entity/region natural-id cache bị ảnh hưởng.
3. Flush thay đổi JPA cần giữ trước bulk SQL.
4. Clear/refresh persistence context có entity liên quan.
5. Evict natural-id cache và entity cache phù hợp sau khi transaction commit.
6. Kiểm thử lookup bằng cả khóa cũ và khóa mới.

Hibernate có API cache riêng để evict natural ID data; ví dụ:

```java
SessionFactory sessionFactory =
        entityManagerFactory.unwrap(SessionFactory.class);

sessionFactory.getCache().evictNaturalIdData(Customer.class);
```

Đây là API riêng Hibernate. Trong ứng dụng nhiều node, việc evict trên một JVM chỉ đồng bộ toàn cluster nếu cache provider có cơ chế invalidation/replication được cấu hình đúng.

## 8. Spring Data JPA portable alternative

`@NaturalId`, `@NaturalIdCache`, `Session.byNaturalId()` và `Session.bySimpleNaturalId()` là tính năng Hibernate. Nếu ứng dụng muốn giữ khả năng đổi JPA provider, có thể dùng query method của Spring Data JPA:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByTenantIdAndEmailNormalized(
            Long tenantId,
            String emailNormalized
    );
}
```

Hoặc dùng JPQL:

```java
@Query("""
    select c
    from Customer c
    where c.tenantId = :tenantId
      and c.emailNormalized = :email
    """)
Optional<Customer> findByBusinessKey(
        @Param("tenantId") Long tenantId,
        @Param("email") String email
);
```

Các cách này portable hơn vì dùng Spring Data/JPA query abstraction, nhưng không tự cung cấp natural-id cache hay toàn bộ semantics riêng của Hibernate. Unique constraint ở database vẫn cần thiết trong mọi trường hợp.

Có thể chọn theo tiêu chí:

| Nhu cầu | Lựa chọn |
|---|---|
| Cần code ít phụ thuộc Hibernate | Spring Data derived query hoặc JPQL |
| Muốn mô tả natural ID trực tiếp trong Hibernate mapping | `@NaturalId` |
| Muốn lookup theo một thuộc tính natural ID | `bySimpleNaturalId()` |
| Muốn lookup theo nhiều thuộc tính natural ID | `byNaturalId().using(...)` |
| Muốn cache natural ID mapping | `@NaturalIdCache` cùng L2 cache provider |
| Cần bảo đảm duy nhất trước concurrent insert | Unique constraint/index ở database |

## 9. equals() và hashCode() khi dùng natural ID

Không nên tự động đưa mọi trường `@NaturalId` vào `equals()` và `hashCode()` mà không xét vòng đời entity.

Một số vấn đề cần cân nhắc:

- Natural ID có thể mutable, khiến hash code thay đổi sau khi object đã được đặt trong `HashSet` hoặc dùng làm key của `HashMap`.
- Entity có thể chưa có đầy đủ giá trị natural ID khi mới được khởi tạo.
- Proxy Hibernate có thể ảnh hưởng cách truy cập class/thuộc tính nếu triển khai equals không cẩn thận.
- Natural ID có thể chỉ duy nhất trong phạm vi tenant; bỏ tenant khỏi equals sẽ làm hai entity khác nhau bị xem là bằng nhau.

Nếu dùng natural ID cho equality, chỉ chọn các trường bất biến, không null và tạo thành khóa duy nhất toàn bộ theo semantics của entity. Với entity mutable hoặc có khóa tenant-scoped, cần triển khai và kiểm thử kỹ. Một lựa chọn phổ biến là dùng chiến lược equality dựa trên định danh ổn định hoặc giữ equals/hashCode theo quy ước của dự án.

`@NaturalId` không tự sinh implementation `equals()` hay `hashCode()`.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Lookup trả nhiều kết quả hoặc insert trùng khóa | Database chưa có unique constraint đúng phạm vi | Thêm unique constraint/index và làm sạch dữ liệu trùng |
| Lookup theo tenant trả sai hoặc không tìm thấy | Thiếu tenant trong natural ID tổng hợp | Đánh dấu đủ thuộc tính và truyền tất cả qua `using()` |
| `bySimpleNaturalId()` không phù hợp | Natural ID gồm nhiều thuộc tính | Dùng `byNaturalId()` |
| Đổi natural ID nhưng lookup cũ/mới bất thường | Mapping vẫn immutable hoặc cache/session chưa đồng bộ | Đánh dấu mutable khi cần, cập nhật managed entity và kiểm thử flush/cache |
| SQL vẫn chạy dù natural ID cache được bật | Entity state không có trong L2 hoặc cache miss | Phân biệt natural-id cache với entity cache và kiểm tra statistics |
| Dữ liệu cache cũ sau bulk SQL | Bulk/native SQL bỏ qua cơ chế đồng bộ Hibernate | Clear/refresh persistence context và evict cache liên quan sau commit |
| Test lần hai không có SQL nhưng production vẫn chậm | Test đang đo L1 trong cùng Session | Đo qua Session mới, kiểm soát L2 và theo dõi SQL |
| Unique pre-check vẫn tạo duplicate dưới tải đồng thời | Hai transaction cùng kiểm tra trước khi insert | Dùng unique constraint làm hàng rào cuối và xử lý vi phạm constraint |

## 11. Kiểm thử natural ID

Nên có integration test với database thực tế hoặc Testcontainers khi cần xác nhận unique constraint, collation và transaction behavior của đúng engine.

Các tình huống nên kiểm tra:

1. Tạo entity với natural ID hợp lệ và lookup bằng `bySimpleNaturalId()`.
2. Lookup natural ID tổng hợp với đầy đủ thuộc tính.
3. Lookup không tồn tại và xác nhận kết quả là `null`/empty theo API wrapper.
4. Thử insert hai entity trùng natural ID và xác nhận database unique constraint từ chối.
5. Cập nhật mutable natural ID, flush rồi lookup bằng giá trị mới.
6. Sau cập nhật, lookup bằng khóa cũ không còn trả entity đó.
7. Dùng Session mới để kiểm tra natural-id cache và entity cache.
8. Cập nhật bằng native SQL trong test, thực hiện invalidation rồi xác nhận cache không trả dữ liệu cũ.
9. Kiểm tra tenant isolation nếu natural ID chỉ duy nhất trong tenant.

Khi kiểm thử cache, tách rõ ba tình huống: lookup lặp trong cùng Session, lookup trong Session mới có L2 cache, và lookup sau khi cache bị evict. Điều này giúp xác định chính xác tầng nào đang phục vụ dữ liệu.

## 12. Checklist thiết kế

- [ ] Natural ID phản ánh khóa nghiệp vụ thực sự duy nhất và ổn định.
- [ ] Đã xác định phạm vi duy nhất: toàn hệ thống hay theo tenant/organization.
- [ ] Giá trị được chuẩn hóa nhất quán trước khi lưu và lookup.
- [ ] Database có unique constraint/index cho đúng tập thuộc tính natural ID.
- [ ] Surrogate primary key vẫn được dùng khi phù hợp cho quan hệ nội bộ.
- [ ] Dùng `@NaturalId` cho thuộc tính bất biến; chỉ dùng `mutable = true` khi nghiệp vụ yêu cầu.
- [ ] Dùng `bySimpleNaturalId()` cho một thuộc tính và `byNaturalId().using(...)` cho khóa tổng hợp.
- [ ] Tên thuộc tính trong `using()` khớp property Java đã mapping.
- [ ] Chỉ bật `@NaturalIdCache` khi có lợi ích đo được và cache provider được cấu hình giới hạn.
- [ ] Phân biệt natural-id cache với entity L2 cache, L1 và query cache.
- [ ] Có chiến lược invalidation khi dùng native SQL/bulk update hoặc nhiều node.
- [ ] Đã đánh giá tác động tới equals/hashCode nếu natural ID có thể thay đổi.
- [ ] Có integration test cho duplicate, mutable natural ID, tenant scope và cache.

Natural ID giúp Hibernate hiểu và truy xuất entity theo khóa nghiệp vụ một cách tường minh. Hãy giữ unique constraint ở database, chọn khóa ổn định và chỉ dùng mutable khi thật sự cần. Hibernate lookup API và natural-id cache có thể tối ưu các luồng tra cứu thường xuyên, còn Spring Data derived query/JPQL là lựa chọn phù hợp khi cần giữ tính portable giữa các JPA provider.