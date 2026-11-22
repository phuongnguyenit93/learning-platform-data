# Thiết kế Repository fragment và lớp triển khai trong Spring Data JPA

Spring Data JPA cho phép mở rộng repository bằng cách ghép các interface và implementation lại thành một repository hoàn chỉnh. Cách mở rộng hiện đại là **repository fragments**: mỗi fragment định nghĩa một nhóm hành vi, còn lớp triển khai cung cấp logic cụ thể. Repository chính kế thừa fragment cùng với `JpaRepository`, và Spring Data tự tạo một proxy kết hợp các phần đó.

Cần phân biệt hai cơ chế:

- **Repository fragment** thêm một khả năng riêng cho một hoặc nhiều repository, ví dụ tìm kiếm nâng cao, bulk operation hoặc tích hợp hệ thống ngoài.
- **Custom repository base class** thay đổi hành vi nền tảng dùng chung cho tất cả repository thuộc cấu hình, ví dụ bổ sung một API chung hoặc thay đổi cách thực hiện phương thức cơ sở.

Với chức năng riêng lẻ, fragment thường là lựa chọn dễ ghép, tái sử dụng và kiểm thử. Base class phù hợp khi thật sự cần hành vi chung ở cấp repository framework. Tránh gom mọi logic vào một lớp `ProductRepositoryImpl` khổng lồ.

Tài liệu dùng Spring Data JPA với Jakarta Persistence (`jakarta.persistence`) trong Spring Boot 3 trở lên. Ví dụ là thành phần của một ứng dụng Spring đã cấu hình JPA, không phải chương trình Java độc lập.

## 1. Repository fragment là gì?

Một repository fragment gồm:

1. **Fragment interface:** khai báo các method mà repository muốn cung cấp thêm.
2. **Fragment implementation:** lớp Java thực hiện các method đó.
3. **Repository chính:** kế thừa fragment interface và repository Spring Data như `JpaRepository`.

Ví dụ cấu trúc:

```text
com.example.product
├── Product.java
├── ProductRepository.java
├── ProductSearchFragment.java
└── ProductSearchFragmentImpl.java
```

Fragment interface:

```java
public interface ProductSearchFragment {
    List<ProductSummary> search(
        String keyword,
        BigDecimal minimumPrice,
        int limit
    );
}
```

Repository chính ghép fragment:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                ProductSearchFragment {
}
```

Spring Data tạo repository proxy thực hiện cả method có sẵn của `JpaRepository` lẫn method do fragment cung cấp. Người gọi dùng cùng một bean `ProductRepository`:

```java
List<ProductSummary> products =
    productRepository.search("tea", new BigDecimal("10.00"), 50);
```

Caller không cần biết method search được triển khai bằng Criteria API, JPQL hay native SQL; chi tiết đó nằm trong fragment implementation.

## 2. Vì sao nên chia chức năng thành fragment?

Fragment giúp chia repository theo trách nhiệm thay vì tạo một implementation khổng lồ.

Ví dụ một ProductRepository có thể ghép nhiều khả năng:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                ProductSearchFragment,
                ProductBulkFragment,
                ProductExportFragment {
}
```

Mỗi fragment có một mục đích:

- `ProductSearchFragment`: truy vấn tìm kiếm nhiều điều kiện.
- `ProductBulkFragment`: thao tác hàng loạt có quy tắc cụ thể.
- `ProductExportFragment`: đọc dữ liệu theo luồng hoặc chuẩn bị dữ liệu export.

Các fragment có thể được tái sử dụng ở repository khác nếu cùng contract và domain semantics phù hợp. Không nên tạo fragment chỉ để bọc một method derived query đơn giản như `findByName`; method đó có thể khai báo trực tiếp trên repository interface.

## 3. Quy ước tên fragment và lớp triển khai

Spring Data mặc định dùng postfix `Impl` để tìm implementation của fragment. Tên lớp triển khai được tạo từ tên fragment interface cộng postfix:

| Fragment interface | Implementation mặc định |
|---|---|
| `ProductSearchFragment` | `ProductSearchFragmentImpl` |
| `ProductBulkFragment` | `ProductBulkFragmentImpl` |
| `ProductExportFragment` | `ProductExportFragmentImpl` |

Ví dụ:

```java
public interface ProductSearchFragment {
    List<Product> searchByKeyword(String keyword);
}

public class ProductSearchFragmentImpl
        implements ProductSearchFragment {

    @Override
    public List<Product> searchByKeyword(String keyword) {
        // Custom implementation.
        return List.of();
    }
}
```

Implementation phải nằm trong package mà cấu hình repository scanning có thể phát hiện; thông thường đặt cùng package với fragment/repository giúp việc tìm kiếm rõ ràng. Tên phải khớp chính xác theo convention và postfix đang cấu hình.

Không cần tự tạo bean repository proxy. Spring Data phát hiện fragment implementation và ghép nó vào repository. Nếu implementation cần dependency như EntityManager hoặc service khác, constructor injection là cách phù hợp.

### 3.1. Tùy chỉnh postfix

Có thể đổi postfix mặc định thông qua cấu hình repository:

```java
@EnableJpaRepositories(
    basePackages = "com.example.product",
    repositoryImplementationPostfix = "CustomImpl"
)
@Configuration
public class JpaRepositoryConfiguration {
}
```

Khi cấu hình postfix là `CustomImpl`, implementation fragment cần dùng tên tương ứng, ví dụ `ProductSearchFragmentCustomImpl`.

Trong Spring Boot, chỉ thêm cấu hình `@EnableJpaRepositories` khi thực sự cần tùy chỉnh. Nếu ứng dụng đã có cấu hình repository scanning, hãy bổ sung thuộc tính vào cấu hình hiện tại thay vì tạo một cấu hình trùng lặp ngoài ý muốn.

## 4. Triển khai fragment bằng EntityManager và Criteria API

Fragment implementation có thể inject `EntityManager` để dùng JPQL, Criteria API hoặc native SQL.

DTO kết quả:

```java
public record ProductSummary(
    Long id,
    String name,
    BigDecimal price
) {
}
```

Interface:

```java
public interface ProductSearchFragment {
    List<ProductSummary> search(
        String keyword,
        BigDecimal minimumPrice,
        int limit
    );
}
```

Implementation minh họa:

```java
@Repository
public class ProductSearchFragmentImpl
        implements ProductSearchFragment {

    private final EntityManager entityManager;

    public ProductSearchFragmentImpl(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Override
    public List<ProductSummary> search(
            String keyword,
            BigDecimal minimumPrice,
            int limit) {

        if (limit < 1 || limit > 500) {
            throw new IllegalArgumentException(
                "limit must be between 1 and 500"
            );
        }

        CriteriaBuilder cb = entityManager.getCriteriaBuilder();
        CriteriaQuery<ProductSummary> cq =
            cb.createQuery(ProductSummary.class);
        Root<Product> product = cq.from(Product.class);

        List<Predicate> predicates = new ArrayList<>();
        predicates.add(cb.isTrue(product.get(Product_.active)));

        if (keyword != null && !keyword.isBlank()) {
            String pattern =
                "%" + keyword.toLowerCase(Locale.ROOT) + "%";

            predicates.add(
                cb.like(
                    cb.lower(product.get(Product_.name)),
                    pattern
                )
            );
        }

        if (minimumPrice != null) {
            predicates.add(
                cb.greaterThanOrEqualTo(
                    product.get(Product_.price),
                    minimumPrice
                )
            );
        }

        cq.select(cb.construct(
                ProductSummary.class,
                product.get(Product_.id),
                product.get(Product_.name),
                product.get(Product_.price)
            ))
          .where(cb.and(predicates.toArray(Predicate[]::new)))
          .orderBy(
              cb.desc(product.get(Product_.createdAt)),
              cb.desc(product.get(Product_.id))
          );

        return entityManager.createQuery(cq)
            .setMaxResults(limit)
            .getResultList();
    }
}
```

Đây là ví dụ minh họa cần entity Product có các property `active`, `name`, `price`, `createdAt`, metamodel `Product_` được sinh và DTO có constructor tương ứng. Cần các import Criteria API, collection, BigDecimal và Locale phù hợp.

Các điểm thiết kế:

- Dùng Criteria API để xây predicate có parameter binding; không nối input thành JPQL/SQL.
- Giới hạn limit ở server để tránh query trả quá nhiều dữ liệu.
- Thêm ID làm tie-breaker để thứ tự ổn định khi nhiều sản phẩm có cùng createdAt.
- Trả DTO để chỉ tải các cột cần thiết.
- Nếu keyword có thể chứa ký tự wildcard `%` hoặc `_` và cần tìm theo nghĩa literal, phải escape chúng và chỉ định escape character phù hợp.
- Nếu query có nhiều filter, có thể tách predicate thành method nhỏ hoặc dùng Specification khi muốn chia sẻ logic.

`@Repository` trên fragment implementation giúp thể hiện đây là thành phần persistence và hỗ trợ exception translation theo cấu hình Spring. Việc phát hiện fragment vẫn dựa trên repository fragment scanning và convention của Spring Data.

## 5. Dùng JPQL hoặc native SQL trong fragment

Fragment không bắt buộc dùng Criteria API. Khi query cố định, JPQL có thể ngắn và dễ đọc:

```java
@Repository
public class ProductSearchFragmentImpl
        implements ProductSearchFragment {

    private final EntityManager entityManager;

    public ProductSearchFragmentImpl(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    public List<Product> findActiveByCategory(String category) {
        return entityManager.createQuery("""
            select p
            from Product p
            where p.active = true
              and p.category.name = :category
            order by p.createdAt desc, p.id desc
            """, Product.class)
            .setParameter("category", category)
            .getResultList();
    }
}
```

Ví dụ này minh họa method riêng; nếu thêm vào fragment interface thì cần khai báo signature tương ứng.

Native SQL cũng có thể dùng khi cần CTE, window function hoặc tính năng riêng của database:

```java
@SuppressWarnings("unchecked")
public List<Object[]> findRecentRows(int limit) {
    return entityManager.createNativeQuery("""
        select id, name, created_at
        from product
        where active = true
        order by created_at desc, id desc
        """)
        .setMaxResults(limit)
        .getResultList();
}
```

Với native query:

- Dùng tên bảng/cột vật lý, không dùng entity name/property JPQL.
- Bind mọi giá trị dữ liệu bằng parameter.
- Không nối trực tiếp input vào SQL identifier hoặc WHERE fragment.
- Nếu trả DTO, xác định rõ alias, thứ tự và kiểu cột; cân nhắc `@SqlResultSetMapping` cho mapping phức tạp.
- Kiểm thử trên đúng database/driver production vì native SQL phụ thuộc dialect.

## 6. Ghép nhiều fragment trong một repository

Một repository có thể kế thừa nhiều fragment interface:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                ProductSearchFragment,
                ProductBulkFragment {
}
```

Mỗi fragment có implementation riêng:

```java
public class ProductSearchFragmentImpl
        implements ProductSearchFragment {
    // Search implementation.
}

public class ProductBulkFragmentImpl
        implements ProductBulkFragment {
    // Bulk operation implementation.
}
```

Spring Data ghép các fragment implementation vào proxy repository. Nhờ vậy, mỗi lớp chỉ tập trung vào một nhóm hành vi và có thể được kiểm thử độc lập hơn.

Không khai báo cùng một method signature trong nhiều fragment nếu không có chủ đích rõ ràng. Khi nhiều fragment cùng cung cấp method trùng tên/chữ ký, việc phân giải implementation có thể gây khó hiểu và phụ thuộc thứ tự composition. Hãy tránh xung đột bằng cách đặt tên method theo trách nhiệm hoặc gom contract về một fragment duy nhất.

## 7. Tái sử dụng fragment cho nhiều repository

Fragment có thể được chia sẻ nếu hành vi thực sự giống nhau. Ví dụ interface tìm kiếm theo trạng thái có thể dùng cho nhiều entity, nhưng implementation phải biết domain type hoặc có contract đủ rõ.

Một fragment tổng quát có thể khai báo:

```java
public interface ActiveRecordSearch<T> {
    List<T> findAllActive();
}
```

Tuy nhiên, implementation generic cần cách xác định entity type và property active hợp lệ. Không thể mặc định mọi T đều có property `active`. Có thể:

- Dùng một base type/mapped superclass chung có mapping active.
- Viết implementation riêng theo domain entity.
- Dùng Specification hoặc repository method derived nếu chỉ cần query đơn giản.
- Truyền query strategy rõ ràng thay vì dựa vào reflection không kiểm soát.

Ví dụ dùng mapped superclass:

```java
@MappedSuperclass
public abstract class ActivatableEntity {
    private boolean active;

    public boolean isActive() {
        return active;
    }
}
```

Các entity kế thừa có chung thuộc tính persistence. Dù vậy, generic fragment vẫn cần được cấu hình đúng để lấy entity type tương ứng; nếu implementation cần generic repository metadata, cân nhắc custom repository base class hoặc factory thay vì tự đoán generic type qua reflection.

Không hy sinh type safety chỉ để tái sử dụng một vài dòng code. Một implementation riêng ngắn gọn có thể dễ bảo trì hơn một framework generic phức tạp.

## 8. Phân biệt fragment với custom repository base class

Fragment bổ sung chức năng cho repository được chọn. Base class thay đổi implementation mặc định dùng chung của repository factory.

| Tiêu chí | Repository fragment | Custom base class |
|---|---|---|
| Phạm vi | Một hoặc một số repository | Mọi repository thuộc cấu hình |
| Mục tiêu | Thêm nhóm hành vi | Thay đổi/hỗ trợ hành vi nền |
| Cách ghép | Repository kế thừa fragment interface | Repository factory dùng base class |
| Implementation | Lớp fragment có postfix | Lớp kế thừa SimpleJpaRepository hoặc base implementation |
| Ví dụ | Search nâng cao, export, custom bulk | API refresh chung, audit hook chung, thay hành vi save |
| Độ ảnh hưởng | Cục bộ theo repository | Rộng, cần kiểm thử toàn hệ thống |

Đừng tạo custom base class chỉ để thêm một method search cho Product. Fragment phù hợp hơn vì không làm thay đổi mọi repository khác.

## 9. Tạo custom repository base class

Khi cần method dùng chung cho tất cả repository, có thể tạo base interface và implementation.

Interface:

```java
@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends JpaRepository<T, ID> {

    void refreshEntity(T entity);
}
```

Implementation:

```java
public class BaseRepositoryImpl<T, ID>
        extends SimpleJpaRepository<T, ID>
        implements BaseRepository<T, ID> {

    private final EntityManager entityManager;

    public BaseRepositoryImpl(
            JpaEntityInformation<T, ?> entityInformation,
            EntityManager entityManager) {

        super(entityInformation, entityManager);
        this.entityManager = entityManager;
    }

    @Override
    public void refreshEntity(T entity) {
        entityManager.refresh(entity);
    }
}
```

Cấu hình repository factory:

```java
@Configuration
@EnableJpaRepositories(
    basePackages = "com.example",
    repositoryBaseClass = BaseRepositoryImpl.class
)
public class JpaConfiguration {
}
```

Repository cụ thể:

```java
public interface ProductRepository
        extends BaseRepository<Product, Long> {
}
```

`@NoRepositoryBean` ngăn Spring Data tạo repository bean trực tiếp cho interface generic chưa xác định domain type. Các repository cụ thể kế thừa BaseRepository sẽ dùng BaseRepositoryImpl làm base implementation.

Lưu ý:

- Base implementation cần constructor phù hợp với repository factory, thường nhận `JpaEntityInformation` và `EntityManager`.
- Nếu ứng dụng đã khai báo `@EnableJpaRepositories`, bổ sung `repositoryBaseClass` vào cấu hình hiện tại.
- Base class ảnh hưởng mọi repository được scan trong phạm vi cấu hình.
- Khi override method có sẵn như save/delete, phải giữ đúng semantics của Spring Data JPA, cascade, entity state và transaction.
- Viết integration test cho nhiều entity/repository trước khi áp dụng rộng.

## 10. Quy tắc transaction cho fragment implementation

Không nên giả định mọi method tự viết trong fragment sẽ tự động có transaction giống các method CRUD được cung cấp bởi `SimpleJpaRepository`.

Đặt transaction boundary ở service là cách thường dùng:

```java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<ProductSummary> search(String keyword) {
        return repository.search(
            keyword,
            null,
            100
        );
    }

    @Transactional
    public void runMaintenance() {
        repository.deleteExpiredProducts();
    }
}
```

Có thể đặt `@Transactional` trên method implementation nếu transaction là một phần contract của fragment:

```java
@Transactional(readOnly = true)
@Override
public List<ProductSummary> search(
        String keyword,
        BigDecimal minimumPrice,
        int limit) {
    // Execute read query.
}
```

Chọn một nơi rõ ràng để quản lý transaction. Tránh đặt transaction annotation tùy tiện ở cả interface, implementation và service với propagation/isolation mâu thuẫn.

Nếu fragment gọi nhiều repository hoặc nhiều thao tác cần atomicity, service-level transaction thường giúp xác định ranh giới nghiệp vụ rõ hơn. Lưu ý Spring transaction thường dựa trên proxy; self-invocation trong cùng bean không đi qua proxy nên có thể không kích hoạt annotation như mong muốn.

## 11. EntityManager, flush và clear trong custom implementation

Fragment dùng EntityManager trực tiếp cần hiểu persistence context:

- Entity đang managed được theo dõi bằng dirty checking.
- `flush()` đồng bộ thay đổi pending thành SQL trong transaction.
- `clear()` detach toàn bộ entity đang managed.
- Flush không commit; transaction vẫn có thể rollback.

Nếu fragment thực hiện bulk JPQL DELETE/UPDATE, persistence context có thể stale. Cân nhắc:

```java
@Transactional
public int deleteExpiredProducts(Instant cutoff) {
    entityManager.flush();

    int deleted = entityManager.createQuery("""
        delete from Product p
        where p.expiresAt < :cutoff
        """)
        .setParameter("cutoff", cutoff)
        .executeUpdate();

    entityManager.clear();
    return deleted;
}
```

Đây là ví dụ method trong implementation; cần khai báo method tương ứng trên fragment interface. Clear detach tất cả entity trong persistence context, không chỉ Product bị xóa. Chỉ dùng khi caller không cần tiếp tục dựa vào các entity managed hiện có hoặc đã có chiến lược phù hợp.

Với native DML, cần kiểm soát flush/clear tương tự và hiểu database trigger/FK. Không tự động clear sau mọi query đọc.

## 12. Phân trang trong fragment

Nếu custom query cần trả Page, implementation cần xử lý cả query dữ liệu và count query:

```java
public Page<ProductSummary> searchPage(
        String keyword,
        Pageable pageable) {

    CriteriaBuilder cb = entityManager.getCriteriaBuilder();

    CriteriaQuery<ProductSummary> dataQuery =
        cb.createQuery(ProductSummary.class);
    Root<Product> root = dataQuery.from(Product.class);

    Predicate filter = cb.like(
        cb.lower(root.get(Product_.name)),
        "%" + keyword.toLowerCase(Locale.ROOT) + "%"
    );

    dataQuery.select(cb.construct(
            ProductSummary.class,
            root.get(Product_.id),
            root.get(Product_.name),
            root.get(Product_.price)
        ))
        .where(filter);

    List<Order> orders = new ArrayList<>();
    for (Sort.Order order : pageable.getSort()) {
        Path<?> path = root.get(order.getProperty());
        orders.add(
            order.isAscending() ? cb.asc(path) : cb.desc(path)
        );
    }
    dataQuery.orderBy(orders);

    List<ProductSummary> content = entityManager
        .createQuery(dataQuery)
        .setFirstResult(Math.toIntExact(pageable.getOffset()))
        .setMaxResults(pageable.getPageSize())
        .getResultList();

    CriteriaQuery<Long> countQuery = cb.createQuery(Long.class);
    Root<Product> countRoot = countQuery.from(Product.class);
    countQuery.select(cb.count(countRoot))
        .where(cb.like(
            cb.lower(countRoot.get(Product_.name)),
            "%" + keyword.toLowerCase(Locale.ROOT) + "%"
        ));

    Long total = entityManager.createQuery(countQuery).getSingleResult();

    return new PageImpl<>(content, pageable, total);
}
```

Đây là khung minh họa, chưa phải implementation production đầy đủ. Cần bổ sung validation keyword/page size, whitelist Sort property, xử lý sort null/case, escaping LIKE wildcard và đảm bảo count predicate tương đương data predicate. Nếu có JOIN/DISTINCT/GROUP BY, count query có thể cần logic khác. Với offset lớn, cân nhắc keyset/cursor pagination.

Không nối trực tiếp `order.getProperty()` vào SQL/JPQL. Với Criteria API, hãy kiểm tra property theo whitelist và dùng typed metamodel khi có thể. Ví dụ trên chỉ nhằm minh họa cách tổ chức data/count query trong fragment.

## 13. Dependency injection và cấu hình implementation

Fragment implementation là Spring-managed component do repository infrastructure phát hiện. Constructor injection giúp khai báo rõ dependency:

```java
public class ProductSearchFragmentImpl
        implements ProductSearchFragment {

    private final EntityManager entityManager;
    private final ProductPricingService pricingService;

    public ProductSearchFragmentImpl(
            EntityManager entityManager,
            ProductPricingService pricingService) {
        this.entityManager = entityManager;
        this.pricingService = pricingService;
    }
}
```

Spring có thể inject EntityManager thông qua shared proxy. Nếu implementation cần nhiều bean, chúng phải nằm trong application context và có thể được resolve.

Nếu fragment implementation không được phát hiện:

1. Kiểm tra fragment interface có được repository chính kế thừa.
2. Kiểm tra tên implementation theo postfix.
3. Kiểm tra package scanning.
4. Kiểm tra constructor dependency có bean tương ứng.
5. Kiểm tra cấu hình repository base package và postfix.
6. Xem lỗi khởi động Spring để xác định bean/fragment nào không được tạo.

Không tự tạo một bean repository khác cùng interface để “bù” cho repository proxy; điều đó có thể gây ambiguity khi inject.

## 14. Naming convention cũ và legacy custom implementation

Các phiên bản Spring Data cũ thường được hướng dẫn tạo interface `ProductRepositoryCustom` và class `ProductRepositoryImpl`. Cách này dựa trên việc tìm implementation theo tên repository và postfix.

Ví dụ legacy:

```java
public interface ProductRepositoryCustom {
    List<Product> searchProducts(String keyword);
}

public class ProductRepositoryImpl
        implements ProductRepositoryCustom {
    // Legacy custom implementation.
}

public interface ProductRepository
        extends JpaRepository<Product, Long>,
                ProductRepositoryCustom {
}
```

Pattern này vẫn có thể xuất hiện trong codebase cũ, nhưng khi xây mới nên ưu tiên fragment-oriented naming:

```text
ProductSearchFragment
ProductSearchFragmentImpl
ProductRepository extends ProductSearchFragment
```

Lý do:

- Tên implementation gắn với fragment capability, không gắn chặt với một repository duy nhất.
- Có thể ghép nhiều fragment vào một repository.
- Dễ tái sử dụng fragment cho repository khác.
- Tránh một class `ProductRepositoryImpl` trở thành nơi chứa mọi custom method.

Nếu dự án đang dùng legacy implementation, không đổi tên hàng loạt chỉ để theo convention mới khi chưa đánh giá ảnh hưởng. Hiểu cách discovery hiện tại và migration từng phần.

## 15. Kiểm thử fragment implementation

Nên dùng integration test để xác nhận Spring Data thực sự phát hiện fragment, inject dependency và chạy query.

Ví dụ:

```java
@DataJpaTest
class ProductSearchFragmentTest {

    @Autowired
    private ProductRepository repository;

    @Test
    void searchesThroughCustomFragment() {
        repository.save(
            new Product("Tea", new BigDecimal("12.00"), true)
        );
        repository.save(
            new Product("Coffee", new BigDecimal("20.00"), true)
        );
        repository.flush();

        List<ProductSummary> results = repository.search(
            "tea",
            new BigDecimal("10.00"),
            20
        );

        assertThat(results)
            .extracting(ProductSummary::name)
            .containsExactly("Tea");
    }
}
```

Ví dụ giả định entity có constructor tương ứng, ProductRepository kế thừa ProductSearchFragment và fragment implementation được Spring Data phát hiện. `@DataJpaTest` cần dependency test phù hợp; nếu fragment phụ thuộc service ngoài, có thể import/mock dependency đó trong test theo thiết kế.

Các trường hợp nên kiểm tra:

- Repository proxy gọi được method fragment.
- Fragment implementation được tìm thấy theo convention.
- Constructor dependency được inject.
- Predicate đúng với null/empty input và dữ liệu biên.
- Sort có tie-breaker ổn định.
- Transaction rollback đúng khi method thất bại.
- Bulk DML có flush/clear đúng khi cần.
- Page content và count query nhất quán.
- Native query chạy trên database engine production.
- Nhiều repository ghép cùng fragment không bị bean ambiguity.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Method fragment không tồn tại trên repository | Repository chính chưa extends fragment interface | Thêm fragment interface vào extends list |
| Spring không tìm thấy implementation | Sai tên postfix hoặc package không được scan | Đặt tên FragmentImpl và kiểm tra repository scanning |
| Có hai bean cùng loại khi inject repository | Tạo repository bean thủ công hoặc cấu hình scan trùng | Dùng repository proxy của Spring Data và sửa scan |
| Constructor injection thất bại | Dependency không có bean hoặc nhiều bean không phân giải được | Đăng ký dependency, dùng qualifier khi cần |
| Method custom không có transaction | Custom method không có boundary phù hợp | Đặt @Transactional ở service hoặc implementation |
| Bulk update/delete trả dữ liệu cũ | PersistenceContext chưa được đồng bộ | Flush trước và clear sau khi phù hợp |
| Entity bị detach ngoài ý muốn | Gọi clear trong fragment dùng chung context | Xem lại transaction boundary và tác động clear toàn context |
| Base class ảnh hưởng repository không mong muốn | repositoryBaseClass áp dụng quá rộng | Giới hạn basePackages hoặc giữ base class tối thiểu |
| Method trùng giữa các fragment | Nhiều fragment cùng contract | Đổi tên hoặc hợp nhất trách nhiệm |
| Legacy Impl bị phát hiện nhầm | Tên class trùng convention custom implementation | Ưu tiên tên fragment rõ ràng, kiểm tra postfix |
| Pagination count sai | Count query không phản ánh filter/join giống data query | Viết count query riêng và test |
| Query động có injection | Nối input thành identifier/SQL fragment | Bind giá trị và whitelist identifier |

## 17. Quy trình thiết kế một custom repository

1. Xác định method có thực sự vượt quá derived query hoặc `@Query` đơn giản không.
2. Chia chức năng theo trách nhiệm: search, bulk, export hoặc integration.
3. Tạo fragment interface với method contract rõ, kiểu input/output cụ thể.
4. Tạo implementation theo tên fragment cộng postfix `Impl`.
5. Inject EntityManager và dependency qua constructor.
6. Chọn Criteria API, JPQL hoặc native SQL theo nhu cầu.
7. Xác định transaction boundary và semantics flush/clear.
8. Kế thừa fragment trong repository chính.
9. Viết integration test xác nhận fragment được phát hiện và kết quả đúng.
10. Chỉ tạo custom base class khi hành vi cần áp dụng rộng cho toàn bộ repository.

## 18. Checklist trước khi đưa fragment vào production

- [ ] Fragment có trách nhiệm rõ và không chỉ bọc một derived query đơn giản?
- [ ] Repository chính đã extends fragment interface?
- [ ] Implementation tên đúng postfix và nằm trong package được scan?
- [ ] Không trùng method signature giữa nhiều fragment?
- [ ] Dependency được inject qua constructor?
- [ ] Transaction boundary được xác định rõ?
- [ ] EntityManager flush/clear chỉ dùng khi có lý do?
- [ ] Query bind dữ liệu và whitelist identifier động?
- [ ] Page count query phản ánh cùng predicate?
- [ ] Custom base class chỉ áp dụng trong phạm vi cần thiết?
- [ ] Integration test xác minh Spring Data composition và SQL behavior?
- [ ] Legacy custom implementation được giữ/migrate có chủ đích?

## 19. Kết luận

Repository fragment là cách mở rộng Spring Data JPA theo từng nhóm chức năng: một interface mô tả contract, một implementation có hậu tố `Impl` cung cấp logic, và repository chính kế thừa fragment cùng `JpaRepository`. Cách này hỗ trợ ghép nhiều capability, tái sử dụng có chọn lọc và giữ code dễ kiểm thử.

Custom repository base class phục vụ nhu cầu rộng hơn: thay đổi hoặc bổ sung hành vi nền tảng cho mọi repository trong cấu hình. Chỉ nên dùng khi có yêu cầu thực sự ở cấp framework, vì ảnh hưởng của nó rộng hơn fragment.

Trong implementation, dùng constructor injection, chọn Criteria/JPQL/native SQL theo yêu cầu, kiểm soát transaction và PersistenceContext, không ghép input thành SQL identifier, và kiểm thử qua Spring Data repository proxy. Với dự án mới, ưu tiên fragment-oriented design; với codebase legacy, hiểu convention hiện có trước khi thay đổi.
