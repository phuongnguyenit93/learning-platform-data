# Xây dựng tìm kiếm nhiều điều kiện bằng Specification

## 1. Vì sao cần Specification?

Màn hình tìm kiếm trong ứng dụng thường có nhiều bộ lọc tùy chọn: từ khóa, trạng thái, danh mục, khoảng giá, khoảng ngày, người tạo hoặc thuộc tính của entity liên quan. Người dùng có thể chỉ nhập một điều kiện, kết hợp nhiều điều kiện bằng AND hoặc tạo nhóm OR.

Nếu tạo một repository method cho mọi tổ hợp điều kiện, số lượng method tăng rất nhanh. Việc ghép chuỗi JPQL/SQL thủ công cũng dễ gây lỗi cú pháp, tham số và bảo mật.

**Spring Data JPA Specification** cho phép mô tả điều kiện truy vấn thành các thành phần nhỏ có thể tái sử dụng và kết hợp. Specification dựa trên JPA Criteria API, nên điều kiện được xây dựng bằng biểu thức có kiểu thay vì nối chuỗi SQL.

Một Specification thường trả về Predicate cho CriteriaQuery:

- **AND**: tất cả điều kiện phải đúng.
- **OR**: ít nhất một điều kiện trong nhóm phải đúng.
- **NOT**: phủ định một điều kiện.
- **Join**: lọc theo thuộc tính của entity liên quan.
- **Subquery/EXISTS**: lọc theo sự tồn tại của bản ghi liên quan.

Bài học dùng ví dụ tìm kiếm Product. Tên entity và thuộc tính có thể thay theo domain của ứng dụng.

## 2. Chuẩn bị entity và repository

Giả sử ứng dụng có Product với tên, SKU, giá, trạng thái, thời điểm tạo, trạng thái kích hoạt và danh mục:

```java
@Entity
@Table(name = "product")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private ProductStatus status;

    @Column(nullable = false)
    private boolean active;

    @Column(nullable = false)
    private LocalDateTime createdAt;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "category_id")
    private Category category;

    protected Product() {
    }

    // Constructor, getter và domain methods được lược bỏ.
}
```

Ví dụ dùng Jakarta Persistence (Spring Boot 3 trở lên). Với Spring Boot 2, package persistence thường là javax.persistence. Entity cần có identifier, constructor không tham số phù hợp và mapping phải khớp schema/migration.

Enum trạng thái:

```java
public enum ProductStatus {
    DRAFT,
    ACTIVE,
    DISCONTINUED
}
```

Repository cần mở rộng **JpaSpecificationExecutor**:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                JpaSpecificationExecutor<Product> {
}
```

JpaSpecificationExecutor cung cấp các phương thức thường dùng:

- `findAll(Specification<T>)`: lấy các entity thỏa điều kiện.
- `findAll(Specification<T>, Pageable)`: tìm kiếm có phân trang và sắp xếp.
- `findOne(Specification<T>)`: tìm tối đa một kết quả; nếu có nhiều hơn một kết quả, có thể phát sinh lỗi.
- `count(Specification<T>)`: đếm số bản ghi thỏa điều kiện.
- `exists(Specification<T>)`: kiểm tra có bản ghi phù hợp hay không.

Khai báo Specification không tự thực thi query. Repository chuyển Specification thành CriteriaQuery khi gọi phương thức tương ứng.

## 3. Cấu trúc Specification

Specification mô tả một điều kiện qua phương thức toPredicate:

```java
public interface Specification<T> {
    Predicate toPredicate(
            Root<T> root,
            CriteriaQuery<?> query,
            CriteriaBuilder criteriaBuilder
    );
}
```

Ba tham số quan trọng:

- **Root<T> root**: entity gốc trong FROM; dùng để truy cập thuộc tính entity.
- **CriteriaQuery<?> query**: query đang được xây dựng; có thể dùng để đặt distinct hoặc tạo subquery.
- **CriteriaBuilder cb**: tạo điều kiện như equal, like, greaterThan, between, and, or và not.

Ví dụ lọc theo trạng thái:

```java
public final class ProductSpecifications {

    private ProductSpecifications() {
    }

    public static Specification<Product> hasStatus(ProductStatus status) {
        return (root, query, cb) -> status == null
                ? cb.conjunction()
                : cb.equal(root.get("status"), status);
    }
}
```

`cb.conjunction()` tạo predicate luôn đúng, tương đương không thêm điều kiện. Cách này hữu ích khi một bộ lọc không được gửi lên: điều kiện đó không làm thay đổi kết quả chung.

Không nên trả về predicate luôn sai khi bộ lọc bị bỏ trống, vì query sẽ luôn trả rỗng. Cũng không nên biến chuỗi rỗng thành LIKE wildcard nếu logic nghiệp vụ muốn bỏ qua bộ lọc.

## 4. Xây dựng các bộ lọc tùy chọn

Tạo mỗi điều kiện thành một Specification nhỏ. Các method dưới đây có thể đặt trong lớp ProductSpecifications.

### 4.1 Tìm từ khóa trên nhiều cột

Tìm theo tên hoặc SKU, không phân biệt chữ hoa/chữ thường:

```java
import java.util.Locale;
import org.springframework.util.StringUtils;

public static Specification<Product> nameContains(String keyword) {
    return textContains("name", keyword);
}

public static Specification<Product> skuContains(String keyword) {
    return textContains("sku", keyword);
}

private static Specification<Product> textContains(
        String property,
        String keyword) {

    if (!StringUtils.hasText(keyword)) {
        return (root, query, cb) -> cb.conjunction();
    }

    String value = escapeLike(keyword.trim().toLowerCase(Locale.ROOT));
    String pattern = "%" + value + "%";

    return (root, query, cb) ->
            cb.like(cb.lower(root.<String>get(property)), pattern, '\\');
}

public static Specification<Product> keywordContains(String keyword) {
    return nameContains(keyword).or(skuContains(keyword));
}

private static String escapeLike(String value) {
    return value.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_");
}
```

Dùng `lower()` để so sánh không phân biệt hoa/thường theo collation/database. Hàm `escapeLike` bảo đảm ký tự `%` và `_` do người dùng nhập được xem là ký tự thường, không vô tình trở thành wildcard; ký tự escape cũng được xử lý.

Lưu ý hiệu năng: pattern bắt đầu bằng `%` thường không tận dụng được B-tree index thông thường. Với dữ liệu lớn, cân nhắc full-text search, trigram index, search engine hoặc chiến lược tìm kiếm phù hợp DBMS.

### 4.2 Lọc theo danh mục liên quan

Product có quan hệ ManyToOne với Category. Dùng join để lọc theo ID danh mục:

```java
public static Specification<Product> belongsToCategory(Long categoryId) {
    return (root, query, cb) -> {
        if (categoryId == null) {
            return cb.conjunction();
        }

        Join<Product, Category> category =
                root.join("category", JoinType.INNER);

        return cb.equal(category.get("id"), categoryId);
    };
}
```

Tên thuộc tính truyền vào `root.join("category")` là tên field/property Java của entity, không phải tên cột SQL `category_id`. Nếu quan hệ có thể null, lựa chọn INNER/LEFT join phải phản ánh đúng logic nghiệp vụ.

### 4.3 Lọc theo khoảng số

Khoảng giá có thể có min, max hoặc cả hai:

```java
public static Specification<Product> priceAtLeast(BigDecimal minPrice) {
    return (root, query, cb) -> minPrice == null
            ? cb.conjunction()
            : cb.greaterThanOrEqualTo(
                    root.<BigDecimal>get("price"), minPrice);
}

public static Specification<Product> priceAtMost(BigDecimal maxPrice) {
    return (root, query, cb) -> maxPrice == null
            ? cb.conjunction()
            : cb.lessThanOrEqualTo(
                    root.<BigDecimal>get("price"), maxPrice);
}
```

Không dùng float/double cho tiền tệ. BigDecimal giúp giữ precision/scale theo mapping database. Cần xác thực minPrice không âm và minPrice không lớn hơn maxPrice trước khi tạo query.

### 4.4 Lọc theo thời gian

Ví dụ tìm Product được tạo từ một thời điểm và trước một thời điểm:

```java
public static Specification<Product> createdFrom(LocalDateTime from) {
    return (root, query, cb) -> from == null
            ? cb.conjunction()
            : cb.greaterThanOrEqualTo(
                    root.<LocalDateTime>get("createdAt"), from);
}

public static Specification<Product> createdBefore(LocalDateTime before) {
    return (root, query, cb) -> before == null
            ? cb.conjunction()
            : cb.lessThan(
                    root.<LocalDateTime>get("createdAt"), before);
}
```

Dùng khoảng nửa mở `[from, before)` thường thuận tiện khi lọc theo ngày/tháng vì không phải đoán độ chính xác mili/micro/nanosecond ở cuối ngày. Nếu API nhận ngày thay vì timestamp, hãy chuyển đổi rõ timezone và mốc đầu/cuối ngày theo timezone nghiệp vụ.

### 4.5 Lọc boolean

Không kiểm tra boolean bằng điều kiện if (active) vì như vậy không phân biệt được người dùng chọn false với không gửi bộ lọc:

```java
public static Specification<Product> isActive(Boolean active) {
    return (root, query, cb) -> active == null
            ? cb.conjunction()
            : cb.equal(root.get("active"), active);
}
```

Với Boolean nullable, có ba trạng thái: true, false và null (không lọc). Enum cũng cần validate giá trị đầu vào; không nhận chuỗi tùy ý rồi nối vào JPQL/SQL.

## 5. Kết hợp điều kiện AND và OR

### 5.1 Kết hợp AND

Giả sử yêu cầu tìm Product thỏa tất cả điều kiện: từ khóa phù hợp, trạng thái ACTIVE, giá từ 100 đến 500 và thuộc category 10.

```java
Specification<Product> specification = Specification.allOf(
        ProductSpecifications.keywordContains("phone"),
        ProductSpecifications.hasStatus(ProductStatus.ACTIVE),
        ProductSpecifications.priceAtLeast(new BigDecimal("100.00")),
        ProductSpecifications.priceAtMost(new BigDecimal("500.00")),
        ProductSpecifications.belongsToCategory(10L)
);

Page<Product> page = productRepository.findAll(
        specification,
        PageRequest.of(0, 20, Sort.by(Sort.Direction.DESC, "createdAt"))
);
```

`Specification.allOf(...)` kết hợp các specification bằng AND. Trong Spring Data JPA 3.x, có thể dùng `allOf(Iterable)` hoặc varargs. Nếu dự án dùng phiên bản cũ chưa có API này, ghép lần lượt bằng `Specification.where(...)` và `and(...)` theo version đang sử dụng.

### 5.2 Kết hợp OR trong một nhóm

Ví dụ tìm Product có tên chứa keyword hoặc SKU chứa keyword. Có thể kết hợp hai Specification riêng:

```java
Specification<Product> nameOrSku =
        ProductSpecifications.nameContains("camera")
                .or(ProductSpecifications.skuContains("camera"));

Specification<Product> activeAndMatches =
        ProductSpecifications.hasStatus(ProductStatus.ACTIVE)
                .and(nameOrSku);
```

Biểu thức trên tương đương:

`status = ACTIVE AND (name LIKE '%camera%' OR sku LIKE '%camera%')`

Dấu ngoặc logic rất quan trọng. Nếu viết nhầm thành `(status = ACTIVE AND name LIKE ...) OR sku LIKE ...` thì các sản phẩm có SKU khớp nhưng không ACTIVE vẫn có thể lọt vào kết quả.

### 5.3 Kết hợp nhiều nhóm điều kiện

Một tìm kiếm phức tạp có thể có các nhóm:

- Bắt buộc: trạng thái ACTIVE.
- Nhóm từ khóa: tên hoặc SKU khớp.
- Nhóm giá: nằm trong khoảng min/max.
- Nhóm thời gian: được tạo trong khoảng yêu cầu.

Mỗi nhóm nên được đặt trong Specification riêng rồi kết hợp bằng and/or để thể hiện đúng dấu ngoặc nghiệp vụ. Đừng tạo một lambda khổng lồ chứa mọi nhánh if/else nếu các điều kiện có thể tái sử dụng hoặc kiểm thử độc lập.

## 6. Tạo Search Criteria và ghép Specification động

### 6.1 DTO chứa bộ lọc

Dùng request/criteria object để gom các điều kiện tìm kiếm:

```java
public record ProductSearchCriteria(
        String keyword,
        Long categoryId,
        ProductStatus status,
        BigDecimal minPrice,
        BigDecimal maxPrice,
        LocalDateTime createdFrom,
        LocalDateTime createdBefore,
        Boolean active
) {
}
```

Có thể dùng Bean Validation hoặc constructor validation để kiểm tra:

- minPrice và maxPrice không âm.
- minPrice không lớn hơn maxPrice.
- createdFrom phải trước createdBefore.
- keyword có độ dài tối đa hợp lý.
- categoryId phải hợp lệ và người dùng có quyền truy cập nếu danh mục cũng thuộc tenant.

Không để client truyền tên entity field hoặc đoạn JPQL tự do để tạo filter. DTO chỉ nên chứa các trường API cho phép.

### 6.2 Factory tạo Specification

```java
import java.util.ArrayList;
import java.util.List;
import org.springframework.data.jpa.domain.Specification;

public final class ProductSpecificationFactory {

    private ProductSpecificationFactory() {
    }

    public static Specification<Product> from(
            ProductSearchCriteria criteria) {

        List<Specification<Product>> filters = new ArrayList<>();

        filters.add(ProductSpecifications.keywordContains(
                criteria.keyword()));
        filters.add(ProductSpecifications.belongsToCategory(
                criteria.categoryId()));
        filters.add(ProductSpecifications.hasStatus(
                criteria.status()));
        filters.add(ProductSpecifications.priceAtLeast(
                criteria.minPrice()));
        filters.add(ProductSpecifications.priceAtMost(
                criteria.maxPrice()));
        filters.add(ProductSpecifications.createdFrom(
                criteria.createdFrom()));
        filters.add(ProductSpecifications.createdBefore(
                criteria.createdBefore()));
        filters.add(ProductSpecifications.isActive(
                criteria.active()));

        return Specification.allOf(filters);
    }
}
```

Mỗi filter trả về conjunction khi không được áp dụng, vì vậy factory có thể thêm tất cả điều kiện mà không phải viết nhiều nhánh kiểm tra null. Với Spring Data JPA version hỗ trợ `Specification.unrestricted()`, có thể dùng cách đó cho filter không áp dụng; conjunction vẫn là cách diễn đạt Criteria API dễ hiểu.

Service gọi repository:

```java
@Service
public class ProductSearchService {

    private final ProductRepository repository;

    public ProductSearchService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Page<Product> search(
            ProductSearchCriteria criteria,
            Pageable pageable) {

        Specification<Product> specification =
                ProductSpecificationFactory.from(criteria);

        return repository.findAll(specification, pageable);
    }
}
```

Trong API thực tế, nên trả DTO thay vì entity trực tiếp để kiểm soát dữ liệu trả về và tránh lazy loading ngoài transaction. Có thể chuyển đổi page bằng `page.map(ProductResponse::from)`.

## 7. Phân trang và sắp xếp an toàn

Specification chỉ xác định điều kiện; Pageable quyết định page, size và sort. Không để client yêu cầu page size vô hạn hoặc sort theo bất kỳ property nào.

Ví dụ whitelist các trường sort:

```java
public enum ProductSortField {
    NAME,
    PRICE,
    CREATED_AT
}

public static Sort toSort(
        ProductSortField field,
        Sort.Direction direction) {

    String property = switch (field) {
        case NAME -> "name";
        case PRICE -> "price";
        case CREATED_AT -> "createdAt";
    };

    return Sort.by(direction, property).and(Sort.by("id"));
}
```

Thêm ID làm tiêu chí phụ để có thứ tự ổn định khi nhiều hàng có cùng giá trị sort. API cần giới hạn page size, ví dụ tối đa 100 bản ghi, và kiểm tra direction chỉ nhận ASC/DESC.

Với dữ liệu lớn:

- `Page<T>` thường cần thêm count query để tính totalElements/totalPages.
- `Slice<T>` chỉ cần biết còn trang tiếp theo hay không, có thể giảm chi phí count.
- Keyset/scroll pagination có thể phù hợp khi offset lớn và dữ liệu thay đổi liên tục.
- Index cần phù hợp với điều kiện lọc và thứ tự sắp xếp thực tế.

Một query nhiều filter không có nghĩa database tự tối ưu được mọi tổ hợp. Kiểm tra execution plan và số lượng hàng thực tế.

## 8. Join, distinct và truy vấn quan hệ

### 8.1 Join quan hệ ManyToOne/OneToOne

Dùng join khi cần lọc theo thuộc tính entity liên quan, ví dụ category.name:

```java
public static Specification<Product> categoryNameContains(String keyword) {
    if (!StringUtils.hasText(keyword)) {
        return (root, query, cb) -> cb.conjunction();
    }

    String pattern = "%" + keyword.trim().toLowerCase(Locale.ROOT) + "%";

    return (root, query, cb) -> {
        Join<Product, Category> category =
                root.join("category", JoinType.INNER);

        return cb.like(
                cb.lower(category.<String>get("name")),
                pattern
        );
    };
}
```

Nếu quan hệ có thể thiếu và muốn giữ entity không có quan hệ trong một query khác, lựa chọn INNER/LEFT join phải phản ánh đúng logic nghiệp vụ.

### 8.2 Join collection có thể nhân bản hàng

Khi join một collection như Product có nhiều Tag, một Product có thể xuất hiện nhiều lần trong kết quả SQL. Có thể cần:

```java
return (root, query, cb) -> {
    Join<Product, Tag> tags = root.join("tags", JoinType.INNER);
    query.distinct(true);
    return cb.equal(tags.get("name"), tagName);
};
```

`distinct(true)` loại bản ghi entity trùng ở kết quả query. Tuy nhiên, khi kết hợp phân trang, count query có thể phức tạp hoặc tốn kém. Kiểm tra SQL count được sinh ra và dữ liệu trả về trên DBMS thực tế.

Nếu chỉ cần xác nhận có ít nhất một tag phù hợp, subquery EXISTS thường tránh nhân bản hàng tốt hơn join collection.

### 8.3 Dùng EXISTS với subquery

Ví dụ tìm Product có ít nhất một Review đạt điểm từ 4 trở lên:

```java
public static Specification<Product> hasHighRating() {
    return (root, query, cb) -> {
        Subquery<Integer> subquery = query.subquery(Integer.class);
        Root<Review> review = subquery.from(Review.class);

        subquery.select(cb.literal(1))
                .where(
                    cb.equal(review.get("product").get("id"), root.get("id")),
                    cb.greaterThanOrEqualTo(review.get("rating"), 4)
                );

        return cb.exists(subquery);
    };
}
```

Subquery EXISTS chỉ kiểm tra sự tồn tại của ít nhất một review phù hợp. Nó không yêu cầu join và trả nhiều dòng Product. Cần có quan hệ Review.product đúng kiểu và index phù hợp cho product_id/rating.

## 9. Projection và chỉ lấy dữ liệu cần thiết

Nếu màn hình tìm kiếm chỉ hiển thị tên, SKU, giá và trạng thái, không nhất thiết tải toàn bộ entity graph. Có thể dùng projection hoặc query DTO khi phù hợp.

Với Specification, JpaSpecificationExecutor chủ yếu trả entity. Có thể dùng `findBy(specification, queryFunction)` trong các phiên bản Spring Data JPA hỗ trợ để chọn projection, slice hoặc kiểu query khác; kiểm tra API theo version của dự án. Nếu projection phức tạp, cân nhắc custom repository dùng CriteriaQuery/JPQL DTO constructor hoặc query chuyên biệt.

Không fetch join nhiều collection chỉ để tránh một vài query. Điều này có thể nhân số hàng, làm sai pagination và tăng bộ nhớ. Chọn DTO projection, EntityGraph hoặc batch fetching theo dữ liệu thực sự cần.

## 10. Những lưu ý về hiệu năng và tính đúng đắn

### 10.1 Index theo workload

Specification linh hoạt nhưng không tự tạo index. Cần phân tích các tổ hợp filter phổ biến:

- status + createdAt.
- category_id + status.
- price range.
- tenant_id + business key nếu hệ thống multi-tenant.
- name/SKU search theo chiến lược tìm kiếm đã chọn.

Không tạo index cho mọi cột một cách máy móc. Index tăng tốc đọc nhưng làm tăng chi phí insert/update và dung lượng lưu trữ. Dùng execution plan và thống kê DBMS để quyết định.

### 10.2 Tránh N+1 và fetch join không phù hợp

Specification lọc entity không đồng nghĩa với việc quan hệ được tải. Khi response cần category, hãy chọn fetch strategy rõ ràng bằng EntityGraph, DTO query hoặc batch fetching. Tránh fetch join collection cùng Page nếu chưa hiểu tác động lên count và pagination.

### 10.3 Null, empty string và khoảng biên

Quy định rõ API xử lý:

- null: bỏ qua filter hay tìm bản ghi có cột NULL?
- chuỗi rỗng/space: bỏ qua hay tìm chuỗi rỗng?
- khoảng giá: hai đầu inclusive hay exclusive?
- khoảng ngày: dùng timezone nào, có inclusive/exclusive không?
- danh sách rỗng: bỏ qua filter hay trả rỗng?
- Boolean false: là filter hợp lệ, không phải giá trị bị bỏ qua.

Đừng để semantics thay đổi ngẫu nhiên giữa các filter.

### 10.4 Không nhận tên cột tùy ý

Criteria API giúp tránh nối chuỗi SQL, nhưng không có nghĩa mọi đầu vào đều an toàn. Chỉ ánh xạ các trường filter/sort được API cho phép. Không dùng reflection hoặc `root.get(clientField)` trực tiếp từ dữ liệu client nếu chưa whitelist.

### 10.5 Tenant scope và quyền truy cập

Nếu Product thuộc tenant, mọi Specification tìm kiếm phải ghép điều kiện tenant bắt buộc từ server context. Không cho client tắt hoặc thay tenant predicate. Nếu entity có trường tenantId, có thể tạo điều kiện riêng:

```java
public static Specification<Product> belongsToTenant(String tenantId) {
    return (root, query, cb) ->
            cb.equal(root.get("tenantId"), tenantId);
}
```

Sau đó AND tenant scope với các filter do người dùng chọn:

```java
Specification<Product> tenantScope =
        ProductSpecifications.belongsToTenant(
                TenantContext.requireTenantId());

Specification<Product> userFilters =
        ProductSpecificationFactory.from(criteria);

Specification<Product> finalSpecification =
        tenantScope.and(userFilters);
```

Tenant predicate là điều kiện phân quyền, không phải filter tùy chọn trên giao diện. Cần kiểm thử rằng mọi đường tìm kiếm, export, count và pagination đều giữ điều kiện này.

## 11. Kiểm thử Specification

Nên kiểm thử bằng repository và database test để xác nhận Criteria API được chuyển thành SQL đúng. `@DataJpaTest` phù hợp cho test slice JPA; nếu query phụ thuộc DBMS-specific behavior, dùng Testcontainers với đúng DBMS mục tiêu.

Ví dụ:

```java
@DataJpaTest
class ProductSpecificationTest {

    @Autowired
    private ProductRepository repository;

    @Test
    void combinesStatusAndPriceFilters() {
        repository.save(product("Phone A", ProductStatus.ACTIVE,
                new BigDecimal("300.00")));
        repository.save(product("Phone B", ProductStatus.ACTIVE,
                new BigDecimal("700.00")));
        repository.save(product("Phone C", ProductStatus.DRAFT,
                new BigDecimal("250.00")));

        Specification<Product> specification = Specification.allOf(
                ProductSpecifications.hasStatus(ProductStatus.ACTIVE),
                ProductSpecifications.priceAtLeast(
                        new BigDecimal("200.00")),
                ProductSpecifications.priceAtMost(
                        new BigDecimal("500.00"))
        );

        List<Product> result = repository.findAll(specification);

        assertEquals(1, result.size());
        assertEquals("Phone A", result.get(0).getName());
    }
}
```

Đây là test minh họa; cần có factory helper product(...), entity constructor/getter, Category nếu mapping bắt buộc và các import JUnit/Spring Test. Nếu Product có unique SKU, helper phải tạo SKU khác nhau cho từng bản ghi.

Các ca test quan trọng:

1. Không có filter: kết quả theo chính sách mặc định, không bị rỗng ngoài ý muốn.
2. Chỉ có một filter: chỉ điều kiện đó được áp dụng.
3. Kết hợp nhiều filter: AND/OR và dấu ngoặc logic chính xác.
4. Biên min/max: giá bằng đúng ngưỡng có được nhận hay không.
5. Null, empty string và Boolean false.
6. Keyword chứa %, _, ký tự escape và tiếng Việt.
7. Join collection: không có bản ghi trùng và pagination/count đúng.
8. Không có kết quả hoặc nhiều kết quả khi dùng findOne.
9. Sort field không nằm trong whitelist bị từ chối.
10. Tenant scope luôn được ghép và không thể bị client ghi đè.

## 12. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Filter null làm query trả rỗng | Dùng predicate false thay cho điều kiện không giới hạn | Dùng cb.conjunction() hoặc unrestricted |
| OR làm lọt bản ghi không mong muốn | Thiếu nhóm ngoặc logic | Tạo Specification nhóm rồi AND/OR rõ ràng |
| Không tìm thấy property khi chạy | Dùng tên cột SQL thay cho property Java | Kiểm tra field trong entity và đường dẫn join |
| Kết quả bị trùng | Join collection tạo nhiều dòng cho một root entity | Dùng distinct hoặc EXISTS |
| Page total sai/chậm | Count query phức tạp do join/distinct | Kiểm tra SQL count, dùng Slice/EXISTS hoặc query riêng |
| Tìm kiếm chậm | LIKE '%keyword%' hoặc thiếu index phù hợp | Dùng full-text/trigram hoặc tối ưu index |
| Boolean false không lọc | Code chỉ kiểm tra điều kiện true | Dùng Boolean nullable và kiểm tra null |
| Sai kết quả khoảng ngày | Nhầm timezone hoặc inclusive/exclusive | Chuẩn hóa timezone và dùng khoảng nửa mở |
| Client sort được field ngoài ý muốn | Truyền trực tiếp property từ request | Whitelist field và direction |
| Query tìm kiếm bỏ qua tenant | Tenant predicate bị xem như filter tùy chọn | AND tenant scope bắt buộc từ server |

## 13. Quy trình triển khai một màn hình tìm kiếm

1. Xác định các filter được nghiệp vụ cho phép và semantics của null/range/OR.
2. Tạo request/criteria DTO có validation.
3. Viết từng Specification nhỏ theo một điều kiện.
4. Nhóm điều kiện OR/AND theo đúng logic nghiệp vụ.
5. Ghép danh sách Specification bằng allOf hoặc API tương thích phiên bản.
6. Gọi JpaSpecificationExecutor với Pageable và sort whitelist.
7. Trả DTO/projection phù hợp, không expose entity graph không cần thiết.
8. Kiểm thử filter đơn, filter kết hợp, biên dữ liệu, pagination, join và quyền truy cập.
9. Đo SQL/execution plan trên dữ liệu gần production và thêm index theo workload.

## 14. Ghi nhớ

- Specification đóng gói một predicate có thể tái sử dụng cho Criteria API.
- `JpaSpecificationExecutor` mở rộng repository để thực thi Specification.
- `and`, `or`, `not`, `allOf` giúp kết hợp điều kiện rõ ràng.
- Dùng `cb.conjunction()` khi filter tùy chọn không được áp dụng.
- Join theo property Java; join collection có thể nhân bản hàng và ảnh hưởng pagination.
- Giới hạn sort/filter field bằng whitelist; không nhận property path tùy ý từ client.
- Kiểm tra null, Boolean false, khoảng biên, timezone và ký tự LIKE.
- Dùng Pageable có page size giới hạn, sort ổn định và index phù hợp.
- Điều kiện phân quyền như tenant scope phải được ghép bắt buộc từ server.

## 15. Tài liệu tham khảo

- [Spring Data JPA — Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html)
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Jakarta Persistence — Criteria API](https://jakarta.ee/specifications/persistence/)
- [Spring Data Commons — Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html)
