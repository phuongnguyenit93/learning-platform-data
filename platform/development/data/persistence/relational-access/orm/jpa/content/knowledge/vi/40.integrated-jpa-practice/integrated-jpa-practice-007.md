# Xây dựng tìm kiếm động bằng JPQL và Criteria

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Nhóm kiến thức:** Thực hành tổng hợp

Một trang danh sách sản phẩm thường có ô từ khóa, bộ lọc danh mục, khoảng giá, trạng thái, ngày tạo, sắp xếp và phân trang. Nếu mỗi tổ hợp điều kiện được viết thành một repository method riêng, số truy vấn sẽ tăng nhanh, logic bị lặp, khó bảo đảm tất cả truy vấn áp điều kiện bảo mật như tenant scope và khó kiểm thử.

**Tìm kiếm động** nghĩa là xây dựng tập điều kiện từ những tiêu chí người dùng thực sự cung cấp. Với JPA có hai hướng phổ biến:

- **JPQL động:** Lắp ghép các đoạn cú pháp cố định mà lập trình viên đã kiểm soát, sau đó bind **mọi giá trị từ client** qua named parameters.
- **Criteria API:** Biểu diễn câu truy vấn bằng các đối tượng Java như CriteriaBuilder, CriteriaQuery, Root, Predicate, Join và Order. Phù hợp khi nhiều nhánh điều kiện, toán tử AND/OR, join, projection được kết hợp có hệ thống.

Bài thực hành xây dựng **hai cách tìm kiếm cho cùng một bộ lọc**, kiểm thử các trường hợp đặc biệt và so sánh ưu điểm, hạn chế về bảo mật, hiệu năng và bảo trì.

Ví dụ request:

~~~text
GET /products?keyword=keyboard
    &categoryId=20
    &minPrice=500000
    &maxPrice=2000000
    &status=ACTIVE
    &sort=PRICE_ASC
    &page=0
    &size=20
~~~

Yêu cầu kết quả:
1. Chỉ có Product **thuộc tenant đã xác thực** và chưa bị xóa mềm.
2. Chỉ thêm predicate cho filter có giá trị.
3. Không nối raw input vào cú pháp JPQL hoặc ORDER BY.
4. Tìm keyword không phân biệt hoa/thường, xử lý ký tự wildcard nếu cần tìm literal.
5. Sắp xếp ổn định bằng tie-breaker duy nhất.
6. Count query và data query dùng **cùng điều kiện**.
7. Trả DTO, không tự serialize JPA entity graph.
8. Kiểm thử NULL, biên khoảng giá, thời gian, kết hợp AND/OR, cross-tenant và pagination.

## 1. Mục tiêu của bài thực hành

- Biết chia **điều kiện bắt buộc** (tenant, soft delete, quyền) và **điều kiện tùy chọn** (keyword, category, giá, trạng thái, ngày).
- Thiết kế SearchFilter typed, validation và normalization ở application boundary.
- Viết JPQL động an toàn với named parameters.
- Dùng CriteriaBuilder.and/or/equal/like/greaterThanOrEqualTo/lessThan.
- Tạo DTO constructor projection và LEFT JOIN cho category có thể vắng.
- Xây count query đúng khi nhiều điều kiện, phân trang và sort allowlist.
- Hiểu sự khác biệt giữa join một-nhiều, countDistinct, fetch join và projection.
- Biết khi nào dùng Spring Data Specification, Criteria, JPQL hoặc giải pháp khác.
- Đo SQL query shape, tối ưu indexes/EXPLAIN, tránh N+1 và request tốn tài nguyên.
- Viết integration tests xác minh kết quả và authorization thực sự.

## 2. Bài toán sản phẩm đa tenant

Hai bảng chính:

~~~text
categories
  id             PK
  tenant_id
  name

products
  id             PK
  tenant_id
  category_id    FK nullable
  name
  sku
  price
  status
  deleted
  created_at
~~~

Dữ liệu minh họa:

| ID | Tenant | Tên | Category | Giá | Status | Deleted |
|---:|---|---|---|---:|---|---|
| 101 | tenant-a | Mechanical Keyboard | 20 | 1.500.000 | ACTIVE | false |
| 102 | tenant-a | Office Keyboard | 20 | 400.000 | ACTIVE | false |
| 103 | tenant-a | Wireless Mouse | 30 | 700.000 | ACTIVE | false |
| 104 | tenant-a | Gaming Keyboard | 20 | 2.500.000 | DRAFT | false |
| 105 | tenant-a | Legacy Keyboard | 20 | 900.000 | ACTIVE | true |
| 201 | tenant-b | Mechanical Keyboard Pro | 20 | 1.100.000 | ACTIVE | false |

Tìm keyword=keyboard, categoryId=20, minPrice=500000, maxPrice=2000000, status=ACTIVE cho tenant-a phải trả **Product 101**. Product 105 bị soft-delete phải được loại, còn Product 201 thuộc tenant-b không được hiện dù cùng điều kiện dữ liệu.

### 2.1. Quy tắc filter

- **keyword:** trim; rỗng coi như không lọc; không phân biệt hoa/thường, tìm tên hoặc SKU; %, _ và ký tự escape có ý nghĩa literal.
- **categoryId:** bằng ID chỉ định; nếu không cung cấp thì Product không có Category vẫn được phép xuất hiện.
- **minPrice:** price lớn hơn hoặc bằng.
- **maxPrice:** price nhỏ hơn hoặc bằng.
- **status:** thuộc enum và trạng thái được người dùng phép xem.
- **createdFromInclusive:** createdAt từ thời điểm đầu, gồm biên.
- **createdToExclusive:** createdAt nhỏ hơn thời điểm cuối, không gồm biên.
- **sort:** một trong key allowlisted, có ID tie-breaker.
- **page/size:** page 0-based, size có giới hạn an toàn.

### 2.2. Tenant ID không phải filter tùy ý

Tenant hiệu lực phải đến từ authenticated principal hoặc trusted tenant context, không chỉ do client tự gửi query parameter. Cả data/count query đều phải có p.tenantId = :tenantId. Một query đầy đủ logic nghiệp vụ mà quên điều kiện tenant vẫn là lỗi phân quyền.

### 2.3. Entity không phải request DTO

Không tạo một Product entity trống rồi dùng các nullable fields của entity làm filter. Search DTO mô tả **điều kiện**, còn Entity mô tả persistent state và vòng đời JPA.

## 3. Entities và output DTO

### 3.1. ProductStatus

~~~java
package com.example.catalog.domain;

public enum ProductStatus {
    DRAFT,
    ACTIVE,
    ARCHIVED
}
~~~

### 3.2. Category

~~~java
package com.example.catalog.persistence;

import jakarta.persistence.*;

@Entity
@Table(name = "categories")
public class Category {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(nullable = false, length = 150)
    private String name;

    protected Category() {}

    public Category(String tenantId, String name) {
        this.tenantId = tenantId;
        this.name = name;
    }

    public Long getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getName() { return name; }
}
~~~

### 3.3. Product

~~~java
package com.example.catalog.persistence;

import com.example.catalog.domain.ProductStatus;
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(
    name = "products",
    indexes = {
        @Index(
            name = "idx_product_tenant_visible_date",
            columnList = "tenant_id, deleted, created_at"
        ),
        @Index(
            name = "idx_product_tenant_category",
            columnList = "tenant_id, category_id"
        )
    },
    uniqueConstraints = @UniqueConstraint(
        name = "uk_product_tenant_sku",
        columnNames = {"tenant_id", "sku"}
    )
)
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(nullable = false, length = 200)
    private String name;

    @Column(nullable = false, length = 64)
    private String sku;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal price;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 24)
    private ProductStatus status;

    @Column(nullable = false)
    private boolean deleted;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "category_id")
    private Category category;

    protected Product() {}

    public Product(
            String tenantId,
            String name,
            String sku,
            BigDecimal price,
            ProductStatus status,
            Instant createdAt,
            Category category) {

        this.tenantId = tenantId;
        this.name = name;
        this.sku = sku;
        this.price = price;
        this.status = status;
        this.createdAt = createdAt;
        this.category = category;
        this.deleted = false;
    }

    public Long getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getName() { return name; }
    public String getSku() { return sku; }
    public BigDecimal getPrice() { return price; }
    public ProductStatus getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }
    public Category getCategory() { return category; }
    public boolean isDeleted() { return deleted; }
}
~~~

Đây là mô hình minh họa, không phải schema production hoàn chỉnh. Constraints tenant/reference, migrations, audit, getters/setters domain, unique policy và generator strategies phải được xác định theo hệ thống thực.

### 3.4. ProductListItem DTO

~~~java
package com.example.catalog.api;

import java.math.BigDecimal;

public record ProductListItem(
    Long id,
    String name,
    String sku,
    BigDecimal price,
    String categoryName
) {}
~~~

Response chỉ chọn fields cần thiết. Không trả thẳng Product entity hoặc expose tenantId/deleted/internalCost/lazy collections.

### 3.5. SearchPage DTO

~~~java
package com.example.catalog.api;

import java.util.List;

public record SearchPage<T>(
    List<T> items,
    long total,
    int page,
    int size
) {}
~~~

Total đếm các records khớp **mọi filter trước khi phân trang**.

## 4. Chuẩn hóa và kiểm tra bộ lọc

### 4.1. Sort key là enum, không phải mảnh SQL do client gửi

~~~java
package com.example.catalog.api;

public enum ProductSort {
    NEWEST,
    OLDEST,
    PRICE_ASC,
    PRICE_DESC,
    NAME_ASC
}
~~~

Giả sử client gửi sort=PRICE_ASC, ứng dụng chuyển thành ProductSort.PRICE_ASC. Nếu client gửi raw text kiểu PRICE_ASC; DELETE FROM ..., nó không phải enum hợp lệ và bị từ chối, không trở thành JPQL.

### 4.2. SearchFilter

~~~java
package com.example.catalog.api;

import com.example.catalog.domain.ProductStatus;
import java.math.BigDecimal;
import java.time.Instant;

public record ProductSearchFilter(
    String keyword,
    Long categoryId,
    BigDecimal minPrice,
    BigDecimal maxPrice,
    ProductStatus status,
    Instant createdFromInclusive,
    Instant createdToExclusive,
    ProductSort sort,
    int page,
    int size
) {
    public ProductSearchFilter {

        if (page < 0) {
            throw new IllegalArgumentException("page < 0");
        }
        if (size < 1 || size > 100) {
            throw new IllegalArgumentException(
                "size must be 1..100"
            );
        }
        if (categoryId != null && categoryId <= 0) {
            throw new IllegalArgumentException(
                "categoryId must be positive"
            );
        }
        if (minPrice != null && minPrice.signum() < 0) {
            throw new IllegalArgumentException(
                "minPrice must be nonnegative"
            );
        }
        if (maxPrice != null && maxPrice.signum() < 0) {
            throw new IllegalArgumentException(
                "maxPrice must be nonnegative"
            );
        }
        if (minPrice != null && maxPrice != null
                && minPrice.compareTo(maxPrice) > 0) {
            throw new IllegalArgumentException(
                "minPrice > maxPrice"
            );
        }
        if (createdFromInclusive != null
                && createdToExclusive != null
                && !createdFromInclusive.isBefore(
                    createdToExclusive
                )) {
            throw new IllegalArgumentException(
                "createdFrom must precede createdTo"
            );
        }
        if (keyword != null) {
            keyword = keyword.trim();

            if (keyword.isEmpty()) {
                keyword = null;
            } else if (keyword.length() > 100) {
                throw new IllegalArgumentException(
                    "keyword too long"
                );
            }
        }
        if (sort == null) {
            sort = ProductSort.NEWEST;
        }
    }
}
~~~

Compact record constructor có thể chuẩn hóa keyword và sort trước khi fields được gán. Không nhầm validation filter với authorization: tenant và resource visibility được kiểm tra riêng.

### 4.3. Biên giá

Dùng BigDecimal thay vì float/double cho giá tiền. Với min=500000, max=2000000, điều kiện sẽ là:

~~~text
p.price >= :minPrice
AND
p.price <= :maxPrice
~~~

min > max là input invalid, không nên chỉ lặng lẽ trả danh sách rỗng. Nếu business muốn min hoặc max có thể âm (ví dụ báo cáo lỗ), validation phải điều chỉnh theo domain.

### 4.4. Biên thời gian nửa mở

Với khoảng thời gian:

~~~text
[startInclusive, endExclusive)
~~~

tạo predicates:

~~~text
p.createdAt >= :createdFromInclusive
p.createdAt < :createdToExclusive
~~~

Đây là cách tránh phải đoán độ chính xác timestamp khi UI chọn ngày. Nếu UI cho phép tìm theo ngày tại Asia/Ho_Chi_Minh, hãy chuyển đầu ngày và đầu ngày kế tiếp sang Instant bằng ZoneId tương ứng trước khi query.

### 4.5. NULL và “không có filter” là hai yêu cầu khác nhau

Trong bài:
- categoryId=null nghĩa **không lọc category**.
- categoryId=20 nghĩa chỉ những Product thuộc Category#20.
- Tìm Product chưa có category là một tiêu chí khác; cần field như categoryMode=UNCATEGORIZED hoặc boolean uncategorizedOnly.

Không tự hiểu categoryId=null là SQL IS NULL, vì nó sẽ làm các Product có Category biến mất khi user không chọn filter.

## 5. Tìm kiếm keyword và tránh wildcard ngoài ý muốn

### 5.1. LIKE là phép so khớp pattern

Trong SQL/JPQL, ký tự phần trăm thường khớp nhiều ký tự, gạch dưới khớp một ký tự. Nếu client tìm chuỗi literal 100% thì pattern không escape sẽ cho kết quả rộng hơn mong đợi.

### 5.2. Chọn ký tự escape tường minh

Có thể dùng dấu chấm than làm escape:

~~~java
package com.example.catalog.search;

import java.util.Locale;

public final class LikePatterns {

    private LikePatterns() {}

    public static String containsLiteral(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "keyword must be provided"
            );
        }

        String normalized =
            value.trim().toLowerCase(Locale.ROOT);

        String escaped = normalized
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");

        return "%" + escaped + "%";
    }
}
~~~

Ví dụ:
- keyword=Keyboard → pattern=%keyboard%
- keyword=100% → pattern=%100!%%
- keyword=A_B → pattern=%a!_b%
- keyword=Wow! → pattern=%wow!!%

Đây là **LIKE literal escaping**, không phải HTML escaping hoặc SQL parameter binding thay thế. Vẫn cần bind pattern qua parameter.

### 5.3. JPQL LIKE với escape character

~~~java
String jpql = """
    select p from Product p
    where lower(p.name) like :keyword escape '!'
    """;

List<Product> products =
    em.createQuery(jpql, Product.class)
      .setParameter(
          "keyword",
          LikePatterns.containsLiteral("100%")
      )
      .getResultList();
~~~

Nếu muốn tìm trong name **hoặc** sku:

~~~text
(
  lower(p.name) like :keyword escape '!'
  OR
  lower(p.sku) like :keyword escape '!'
)
~~~

Phải **đặt dấu ngoặc OR** để AND với tenant/deleted/filter khác theo đúng logic. Nếu viết thiếu ngoặc:

~~~text
p.tenantId = :tenant
AND lower(p.name) LIKE :keyword
OR lower(p.sku) LIKE :keyword
~~~

thì do thứ tự ưu tiên AND cao hơn OR, nhánh SKU có thể bỏ qua tenant filter → **rò dữ liệu khác tenant**.

### 5.4. LOWER không phải tìm kiếm ngôn ngữ toàn diện

LOWER giúp tìm không phân biệt hoa/thường trong nhiều trường hợp, nhưng:
- Quy tắc Unicode case folding có thể khác giữa JVM và DB;
- Dấu tiếng Việt, collation, accent normalization có thể tạo kết quả khác;
- LOWER(column) có thể khiến index B-tree thường khó được sử dụng;
- LIKE '%word%' có leading wildcard, nhiều DB không dùng B-tree hiệu quả;
- Cần cân nhắc full-text, trigram hoặc search engine nếu dữ liệu lớn.

Bài dùng LOWER+LIKE để minh họa JPQL portable-ish, không coi đó là bộ máy tìm kiếm ngôn ngữ toàn văn.

## 6. JPQL động: chỉ ghép các đoạn cú pháp cố định

### 6.1. Hai cách thường gặp

**Cách A — static query với null checks:**

~~~java
@Query("""
    select p
    from Product p
    where p.tenantId = :tenant
      and p.deleted = false
      and (:status is null or p.status = :status)
      and (:minPrice is null or p.price >= :minPrice)
    """)
List<Product> search(
    String tenant,
    ProductStatus status,
    BigDecimal minPrice
);
~~~

Dễ đọc khi rất ít filters, nhưng:
- Tất cả null guards vẫn nằm trong SQL;
- Provider/database có thể gặp khó khăn với kiểu của null parameters;
- Optimizer/index selectivity có thể không tối ưu;
- Khi rất nhiều filters và OR groups, query dài và dễ khó bảo trì.

**Cách B — lắp WHERE từ filters có mặt:**

~~~text
base predicates:
  tenantId = :tenantId
  deleted = false

if keyword:
  and (name like :keyword or sku like :keyword)

if categoryId:
  and categoryId = :categoryId

if minPrice:
  and price >= :minPrice

if maxPrice:
  and price <= :maxPrice
~~~

Cách B giúp database nhận những predicates thực sự cần. Phần tiếp theo triển khai hoàn chỉnh với named parameters, projection, sorting và count.

### 6.2. Quy tắc an toàn tối thiểu

**Có thể ghép cú pháp do lập trình viên định nghĩa:**

~~~java
if (filter.minPrice() != null) {
    conditions.add("p.price >= :minPrice");
}
~~~

**Không ghép raw input như một expression:**

~~~java
conditions.add("p.price >= " + rawRequestValue);
~~~

**Không làm:**

~~~java
String order = " order by " + sortFromHttp;
~~~

**Nên dùng enum allowlist:**

~~~java
String order = switch (filter.sort()) {
    case NEWEST -> "p.createdAt desc, p.id desc";
    case OLDEST -> "p.createdAt asc, p.id asc";
    case PRICE_ASC -> "p.price asc, p.id asc";
    case PRICE_DESC -> "p.price desc, p.id desc";
    case NAME_ASC -> "p.name asc, p.id asc";
};
~~~

Sort fragment đến từ các **string literal cố định**, không phải từ raw client-supplied property name.

## 7. Biên dịch WHERE clause và named parameters

Ta muốn dùng **cùng một bộ predicates và parameters** cho data query và count query, tránh lỗi page trả một tập rows còn total đếm tập khác.

### 7.1. Record chứa phần JPQL đã tạo

~~~java
package com.example.catalog.search;

import java.util.Map;

public record JpqlSearchParts(
    String whereClause,
    Map<String, Object> parameters
) {}
~~~

### 7.2. ProductJpqlPredicateBuilder

~~~java
package com.example.catalog.search;

import com.example.catalog.api.ProductSearchFilter;
import java.util.*;

public final class ProductJpqlPredicateBuilder {

    private ProductJpqlPredicateBuilder() {}

    public static JpqlSearchParts build(
            String authorizedTenantId,
            ProductSearchFilter filter) {

        Objects.requireNonNull(filter, "filter");

        if (authorizedTenantId == null
                || authorizedTenantId.isBlank()) {
            throw new IllegalArgumentException(
                "Missing authorized tenant"
            );
        }

        List<String> predicates = new ArrayList<>();
        Map<String, Object> params = new LinkedHashMap<>();

        // Điều kiện bắt buộc, không phụ thuộc client filters.
        predicates.add("p.tenantId = :tenantId");
        predicates.add("p.deleted = false");
        params.put("tenantId", authorizedTenantId);

        if (filter.keyword() != null) {
            predicates.add(
                """
                (
                    lower(p.name) like :keyword escape '!'
                    or lower(p.sku) like :keyword escape '!'
                )
                """
            );
            params.put(
                "keyword",
                LikePatterns.containsLiteral(filter.keyword())
            );
        }

        if (filter.categoryId() != null) {
            predicates.add(
                "p.category.id = :categoryId"
            );
            params.put("categoryId", filter.categoryId());
        }

        if (filter.minPrice() != null) {
            predicates.add("p.price >= :minPrice");
            params.put("minPrice", filter.minPrice());
        }

        if (filter.maxPrice() != null) {
            predicates.add("p.price <= :maxPrice");
            params.put("maxPrice", filter.maxPrice());
        }

        if (filter.status() != null) {
            predicates.add("p.status = :status");
            params.put("status", filter.status());
        }

        if (filter.createdFromInclusive() != null) {
            predicates.add("p.createdAt >= :from");
            params.put(
                "from", filter.createdFromInclusive()
            );
        }

        if (filter.createdToExclusive() != null) {
            predicates.add("p.createdAt < :to");
            params.put(
                "to", filter.createdToExclusive()
            );
        }

        return new JpqlSearchParts(
            " where " + String.join(" and ", predicates),
            Map.copyOf(params)
        );
    }
}
~~~

Chỉ các đoạn JPQL **cố định** nằm trong builder. Giá trị từ client được lưu trong params và đi qua setParameter.

### 7.3. Tại sao keyword group có ngoặc?

WHERE cần có nghĩa:

~~~text
tenant = :tenant
AND deleted = false
AND (name LIKE :keyword OR sku LIKE :keyword)
AND price >= :min
~~~

Nếu viết không có ngoặc:

~~~text
tenant = :tenant AND name LIKE :keyword
OR sku LIKE :keyword
~~~

thì nhánh SKU có thể không còn bị giới hạn bởi tenant. Đây vừa là lỗi logic vừa có thể thành **lỗ hổng phân quyền**.

### 7.4. Map.copyOf

Builder chỉ thêm params cho filter hiện diện, nên Map không chứa null values. Map.copyOf tạo bản bất biến để caller không vô tình thay giá trị sau khi WHERE đã được biên dịch. Nếu design cho phép parameter null, cần cách khác vì Map.copyOf không nhận null.

## 8. Sort allowlist và thứ tự ổn định

~~~java
package com.example.catalog.search;

import com.example.catalog.api.ProductSort;

public final class ProductJpqlSorts {

    private ProductJpqlSorts() {}

    public static String orderBy(ProductSort sort) {
        return switch (sort) {
            case NEWEST ->
                "p.createdAt desc, p.id desc";
            case OLDEST ->
                "p.createdAt asc, p.id asc";
            case PRICE_ASC ->
                "p.price asc, p.id asc";
            case PRICE_DESC ->
                "p.price desc, p.id desc";
            case NAME_ASC ->
                "p.name asc, p.id asc";
        };
    }
}
~~~

Lưu ý:
- Không nhận raw ORDER BY fragments từ client.
- Named parameter không thể thay tên property hoặc SQL identifier.
- ID là tie-breaker vì nhiều Products có thể cùng price/name/createdAt.
- Thứ tự ổn định không tự giải quyết việc tập rows bị insert/delete giữa hai lần page requests.

## 9. Repository JPQL động hoàn chỉnh

### 9.1. Interface

~~~java
package com.example.catalog.search;

import com.example.catalog.api.*;

public interface ProductSearchRepository {
    SearchPage<ProductListItem> search(
        String authorizedTenantId,
        ProductSearchFilter filter
    );
}
~~~

### 9.2. Implementation sử dụng EntityManager

~~~java
package com.example.catalog.search;

import com.example.catalog.api.*;
import jakarta.persistence.*;
import org.springframework.stereotype.Repository;
import java.util.Map;

@Repository
public class ProductJpqlSearchRepository
        implements ProductSearchRepository {

    @PersistenceContext
    private EntityManager em;

    @Override
    public SearchPage<ProductListItem> search(
            String authorizedTenantId,
            ProductSearchFilter filter) {

        JpqlSearchParts parts =
            ProductJpqlPredicateBuilder.build(
                authorizedTenantId, filter
            );

        String dataJpql = """
            select new com.example.catalog.api.ProductListItem(
                p.id, p.name, p.sku, p.price, c.name
            )
            from Product p
            left join p.category c
            """
            + parts.whereClause()
            + " order by "
            + ProductJpqlSorts.orderBy(filter.sort());

        String countJpql =
            "select count(p) from Product p"
            + parts.whereClause();

        TypedQuery<ProductListItem> data =
            em.createQuery(
                dataJpql, ProductListItem.class
            );

        TypedQuery<Long> count =
            em.createQuery(countJpql, Long.class);

        for (Map.Entry<String, Object> entry
                : parts.parameters().entrySet()) {
            data.setParameter(
                entry.getKey(), entry.getValue()
            );
            count.setParameter(
                entry.getKey(), entry.getValue()
            );
        }

        long offset =
            (long) filter.page() * filter.size();

        if (offset > Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                "Page offset too large"
            );
        }

        data.setFirstResult((int) offset);
        data.setMaxResults(filter.size());

        return new SearchPage<>(
            data.getResultList(),
            count.getSingleResult(),
            filter.page(),
            filter.size()
        );
    }
}
~~~

### 9.3. Vai trò các thành phần

- **ProductJpqlPredicateBuilder:** nơi tập trung điều kiện bảo mật và optional filters.
- **ProductJpqlSorts:** nơi duy nhất chuyển enum sort thành JPQL fragment.
- **Data query:** chọn ProductListItem DTO với LEFT JOIN to-one Category, order, offset và limit.
- **Count query:** đếm trên cùng WHERE nhưng không áp order, offset hoặc limit.
- **EntityManager:** bind typed parameters, thực thi query.

Category là quan hệ many-to-one, nên LEFT JOIN Category không nhân bản Product rows. Nếu query chuyển sang join collection to-many thì count/pagination cần xử lý khác.

### 9.4. Tại sao count query không có LEFT JOIN Category?

Count không cần categoryName nên không cần join chỉ để projection. Nếu filter categoryId có mặt, expression p.category.id có thể gây implicit join theo cách provider xây SQL; kết quả chỉ gồm products thuộc Category đó. Với filter categoryId vắng mặt, products không có category vẫn được đếm.

### 9.5. Service lấy tenant từ context đáng tin

~~~java
@Service
public class ProductSearchService {

    private final ProductSearchRepository repository;
    private final TenantAccess tenantAccess;

    public ProductSearchService(
            ProductSearchRepository repository,
            TenantAccess tenantAccess) {
        this.repository = repository;
        this.tenantAccess = tenantAccess;
    }

    @Transactional(readOnly = true)
    public SearchPage<ProductListItem> search(
            ProductSearchFilter filter) {

        String tenantId =
            tenantAccess.requirePermission(
                "PRODUCT_READ"
            );

        return repository.search(tenantId, filter);
    }
}
~~~

TenantAccess là abstraction application tự triển khai. Nếu có cả ProductJpqlSearchRepository và ProductCriteriaSearchRepository cùng implement interface, Spring phải chọn đúng bean qua @Qualifier hoặc cấu hình tương ứng.

### 9.6. Read-only transaction không tự đảm bảo snapshot của hai câu query

Ở PostgreSQL READ COMMITTED, data query và count query có thể dùng snapshots riêng. Nếu có INSERT/DELETE đồng thời giữa hai câu, total và items có thể không phản ánh cùng một thời điểm. readOnly=true là hint transaction; nếu business cần read snapshot nhất quán, phải chọn isolation/snapshot strategy với DB thực tế.

## 10. JPQL động: những trường hợp kiểm tra

| Filter | Predicate | Điều cần kiểm chứng |
|---|---|---|
| keyword=null | Không LIKE | Vẫn lấy các Product hợp lệ |
| keyword="  " | Chuẩn hóa null | Không cần LIKE '%%' |
| keyword="mouse" | name OR sku | Có ngoặc AND/OR |
| keyword="100%" | LIKE escaped | Ký tự % là literal |
| categoryId=20 | category.id = 20 | Loại uncategorized |
| Không có categoryId | Không có category predicate | Uncategorized vẫn hiện |
| minPrice=500000 | >= minPrice | Biên 500000 được lấy |
| maxPrice=2000000 | <= maxPrice | Biên 2000000 được lấy |
| status=ACTIVE | enum parameter | Không raw SQL string |
| from/to | >= from, < to | Half-open range |
| deleted=true | Luôn loại | Mandatory filter |
| tenant-b | Luôn loại với tenant-a | Mandatory tenant predicate |
| sort=NAME_ASC | name asc, id asc | Tie-breaker |
| page=1,size=20 | offset 20, limit 20 | Không trả ngoài page |

## 11. Khi JPQL string builder trở nên khó bảo trì

JPQL động phù hợp khi:
- Số nhánh lọc vừa phải;
- Query shape tương đối ổn định;
- Nhóm AND/OR rõ và không quá lồng nhau;
- Projection và count không phức tạp.

Nhưng cần cân nhắc Criteria nếu:
- Có nhiều nhóm AND/OR compose từ nhiều modules;
- Join được thêm/bỏ theo một nhóm filters;
- Có cả EXISTS, subquery, aggregate/HAVING;
- Nhiều repository queries tái sử dụng predicate rules;
- Refactor property names thường xuyên.

Criteria xây **expression tree bằng Java API**, giảm nguy cơ sai dấu ngoặc ở JPQL string, nhưng vẫn cần kiểm soát query shape, authorization và SQL được provider tạo ra.

## 12. Criteria API: biến truy vấn thành cây biểu thức

Criteria API thuộc Jakarta Persistence, cho phép dựng câu truy vấn bằng object model thay vì string JPQL hoàn chỉnh.

### 12.1. Các thành phần chính

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| EntityManager | Cung cấp CriteriaBuilder | em.getCriteriaBuilder() |
| CriteriaBuilder | Tạo Predicate, Order, expression | cb.equal(...), cb.like(...) |
| CriteriaQuery<T> | Query có kiểu kết quả T | cb.createQuery(ProductListItem.class) |
| Root<Product> | Root entity trong FROM | cq.from(Product.class) |
| Path<X> | Truy cập property | root.get("price") |
| Predicate | Điều kiện boolean | cb.greaterThanOrEqualTo(...) |
| Join<X,Y> | Kết nối quan hệ | root.join("category", JoinType.LEFT) |
| Order | Mô tả sắp xếp | cb.asc(root.get("price")) |
| Selection | Mô tả projection | cb.construct(ProductListItem.class, ...) |

### 12.2. Criteria đơn giản

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Product> cq =
    cb.createQuery(Product.class);

Root<Product> p = cq.from(Product.class);

cq.select(p);

cq.where(
    cb.and(
        cb.equal(p.get("tenantId"), authorizedTenantId),
        cb.isFalse(p.get("deleted")),
        cb.greaterThanOrEqualTo(
            p.<BigDecimal>get("price"),
            new BigDecimal("500000")
        )
    )
);

cq.orderBy(
    cb.desc(p.get("createdAt")),
    cb.desc(p.get("id"))
);

List<Product> result =
    em.createQuery(cq).getResultList();
~~~

Ví dụ trên trả managed Product entities, phù hợp khi business cần entities. Với trang danh sách public, phần sau chọn DTO projection để tránh nạp dư quan hệ và state.

### 12.3. root.get dùng persistent attribute names

~~~java
root.get("createdAt")
~~~

dùng tên Java property, không dùng tên SQL column created_at. Cách string literal này vẫn dễ sai khi refactor; có thể dùng **JPA static metamodel** để tăng type safety khi project đã cấu hình annotation processor tương ứng.

### 12.4. Criteria không tự an toàn nếu bỏ tenant predicate

Query Criteria có thể tránh việc ghép raw SQL, nhưng vẫn sai authorization nếu không giới hạn tenant. Query builder nên đưa điều kiện bắt buộc vào **mọi nhánh**, và service phải cung cấp trusted tenantId.

## 13. Viết hàm dựng Predicate dùng lại

Tách điều kiện WHERE thành một hàm nhận CriteriaBuilder, Root và filter. Lợi ích: data query và count query có **cùng rule** dù Root là hai instances khác nhau.

### 13.1. ProductCriteriaPredicates

~~~java
package com.example.catalog.search;

import com.example.catalog.api.ProductSearchFilter;
import com.example.catalog.persistence.Product;
import jakarta.persistence.criteria.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;

public final class ProductCriteriaPredicates {

    private ProductCriteriaPredicates() {}

    public static List<Predicate> build(
            CriteriaBuilder cb,
            Root<Product> root,
            String authorizedTenant,
            ProductSearchFilter filter) {

        Objects.requireNonNull(cb);
        Objects.requireNonNull(root);
        Objects.requireNonNull(filter);

        if (authorizedTenant == null
                || authorizedTenant.isBlank()) {
            throw new IllegalArgumentException(
                "Missing authorized tenant"
            );
        }

        List<Predicate> parts = new ArrayList<>();

        // Mandatory predicates.
        parts.add(
            cb.equal(
                root.get("tenantId"),
                authorizedTenant
            )
        );
        parts.add(
            cb.isFalse(root.get("deleted"))
        );

        if (filter.keyword() != null) {
            String pattern = LikePatterns.containsLiteral(
                filter.keyword()
            );

            Predicate nameMatches = cb.like(
                cb.lower(root.get("name")),
                pattern,
                '!'
            );

            Predicate skuMatches = cb.like(
                cb.lower(root.get("sku")),
                pattern,
                '!'
            );

            parts.add(
                cb.or(nameMatches, skuMatches)
            );
        }

        if (filter.categoryId() != null) {
            parts.add(
                cb.equal(
                    root.get("category").get("id"),
                    filter.categoryId()
                )
            );
        }

        if (filter.minPrice() != null) {
            parts.add(
                cb.greaterThanOrEqualTo(
                    root.<BigDecimal>get("price"),
                    filter.minPrice()
                )
            );
        }

        if (filter.maxPrice() != null) {
            parts.add(
                cb.lessThanOrEqualTo(
                    root.<BigDecimal>get("price"),
                    filter.maxPrice()
                )
            );
        }

        if (filter.status() != null) {
            parts.add(
                cb.equal(
                    root.get("status"),
                    filter.status()
                )
            );
        }

        if (filter.createdFromInclusive() != null) {
            parts.add(
                cb.greaterThanOrEqualTo(
                    root.<Instant>get("createdAt"),
                    filter.createdFromInclusive()
                )
            );
        }

        if (filter.createdToExclusive() != null) {
            parts.add(
                cb.lessThan(
                    root.<Instant>get("createdAt"),
                    filter.createdToExclusive()
                )
            );
        }

        return parts;
    }
}
~~~

Trong một số JPA versions, CriteriaBuilder.like overload với escape char được hỗ trợ trực tiếp; nếu provider/database dialect xử lý LIKE escape khác, cần integration test trên target DB. Pattern vẫn được tạo từ trusted routine **LikePatterns**, không phải ghép SQL.

### 13.2. AND toàn bộ predicates

~~~java
List<Predicate> predicates =
    ProductCriteriaPredicates.build(
        cb, root, authorizedTenant, filter
    );

cq.where(
    cb.and(predicates.toArray(Predicate[]::new))
);
~~~

Có thể truyền array trực tiếp vào cq.where. Dùng cb.and giúp code mô tả rõ tập predicates phải **cùng đúng**, trong khi keyword đã là một OR group riêng.

### 13.3. Predicate là object thuộc query context

Không tạo một Predicate với Root A rồi cố gắn vào CriteriaQuery B với Root B khác. Data query và count query phải gọi builder với **Root riêng**, vì các expressions/path được gắn với cây truy vấn gốc.

### 13.4. Điều kiện bắt buộc khác điều kiện tùy chọn

Việc tenant/deleted nằm ở đầu builder là một quy ước quan trọng, nhưng security review vẫn cần kiểm tra **tất cả query paths** trong project có đi qua builder hay không. Đừng xem builder này là biện pháp bảo vệ toàn DB nếu một repository khác vẫn có findAll() public hoặc native SQL thiếu tenant filter.

## 14. Sắp xếp bằng Criteria Order

### 14.1. ProductCriteriaOrders

~~~java
package com.example.catalog.search;

import com.example.catalog.api.ProductSort;
import com.example.catalog.persistence.Product;
import jakarta.persistence.criteria.*;
import java.util.List;

public final class ProductCriteriaOrders {

    private ProductCriteriaOrders() {}

    public static List<Order> by(
            CriteriaBuilder cb,
            Root<Product> root,
            ProductSort sort) {

        return switch (sort) {
            case NEWEST -> List.of(
                cb.desc(root.get("createdAt")),
                cb.desc(root.get("id"))
            );
            case OLDEST -> List.of(
                cb.asc(root.get("createdAt")),
                cb.asc(root.get("id"))
            );
            case PRICE_ASC -> List.of(
                cb.asc(root.get("price")),
                cb.asc(root.get("id"))
            );
            case PRICE_DESC -> List.of(
                cb.desc(root.get("price")),
                cb.desc(root.get("id"))
            );
            case NAME_ASC -> List.of(
                cb.asc(root.get("name")),
                cb.asc(root.get("id"))
            );
        };
    }
}
~~~

CriteriaBuilder tạo SQL ordering từ **properties đã chọn trong code**, không từ raw sort expression của client. Enum ProductSort được kiểm tra ở API boundary.

### 14.2. Sort key bị NULL

Với các trường có thể null như categoryName, thứ tự NULLS FIRST/LAST có thể khác theo database/dialect. Nếu API yêu cầu quy tắc cố định, cần xử lý bằng expression/case hoặc provider/DB-specific ordering và test. Trong ví dụ price/name/createdAt là NOT NULL, nên chưa có vấn đề đó.

### 14.3. Sắp xếp theo tên danh mục

Nếu thêm sort CATEGORY_NAME, data query đã có LEFT JOIN Category và có thể order theo categoryJoin.get("name"), nhưng count query không cần sort. Trong một số DB, sort trên nullable Category làm các Product chưa gán Category nằm đầu/cuối khác nhau. Nên quyết định rõ null placement trong API contract.

## 15. Criteria repository hoàn chỉnh với DTO và count

### 15.1. Search implementation

~~~java
package com.example.catalog.search;

import com.example.catalog.api.*;
import com.example.catalog.persistence.*;
import jakarta.persistence.*;
import jakarta.persistence.criteria.*;
import org.springframework.stereotype.Repository;
import java.util.List;

@Repository("productCriteriaSearchRepository")
public class ProductCriteriaSearchRepository
        implements ProductSearchRepository {

    @PersistenceContext
    private EntityManager em;

    @Override
    public SearchPage<ProductListItem> search(
            String authorizedTenant,
            ProductSearchFilter filter) {

        CriteriaBuilder cb = em.getCriteriaBuilder();

        // DATA QUERY
        CriteriaQuery<ProductListItem> cq =
            cb.createQuery(ProductListItem.class);

        Root<Product> root = cq.from(Product.class);
        Join<Product, Category> category =
            root.join("category", JoinType.LEFT);

        cq.select(cb.construct(
            ProductListItem.class,
            root.get("id"),
            root.get("name"),
            root.get("sku"),
            root.get("price"),
            category.get("name")
        ));

        List<Predicate> conditions =
            ProductCriteriaPredicates.build(
                cb, root, authorizedTenant, filter
            );

        cq.where(
            conditions.toArray(Predicate[]::new)
        );

        cq.orderBy(
            ProductCriteriaOrders.by(
                cb, root, filter.sort()
            )
        );

        TypedQuery<ProductListItem> data =
            em.createQuery(cq);

        long offset =
            (long) filter.page() * filter.size();

        if (offset > Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                "Page offset too large"
            );
        }

        data.setFirstResult((int) offset);
        data.setMaxResults(filter.size());

        // COUNT QUERY: ROOT MỚI, CÙNG RULES
        CriteriaQuery<Long> countCq =
            cb.createQuery(Long.class);

        Root<Product> countRoot =
            countCq.from(Product.class);

        countCq.select(cb.count(countRoot));

        List<Predicate> countConditions =
            ProductCriteriaPredicates.build(
                cb,
                countRoot,
                authorizedTenant,
                filter
            );

        countCq.where(
            countConditions.toArray(Predicate[]::new)
        );

        long total =
            em.createQuery(countCq)
              .getSingleResult();

        return new SearchPage<>(
            data.getResultList(),
            total,
            filter.page(),
            filter.size()
        );
    }
}
~~~

### 15.2. Những điểm cần chú ý

- Data query và count query tạo **Root khác nhau** rồi gọi chung predicate-builder.
- Data query LEFT JOIN Category để tạo categoryName; count query không cần join chỉ để output field.
- Quan hệ Category là many-to-one, nên không nhân duplicate Product rows.
- Không fetch join collection trong câu query có setFirstResult/setMaxResults.
- Không trả managed Product entity từ public list API khi chỉ cần năm fields.
- Application service vẫn chịu trách nhiệm authorization trước khi gọi repository.
- Nếu dùng cả hai implementations trong cùng Spring context, cần quyết định inject bean bằng @Qualifier hoặc một cấu hình lựa chọn chiến lược.

### 15.3. Hai lần truy vấn và yêu cầu consistent snapshot

Count và data được thực hiện riêng; ở database READ COMMITTED có concurrent writes thì chúng có thể nhìn state ở hai thời điểm khác nhau. Đó là consistency tradeoff của pagination thông thường, không phải lỗi riêng Criteria.

Nếu cần snapshot chặt, kiểm tra database isolation/snapshot semantics và chi phí. Nếu không cần total chính xác, trả Slice/hasNext có thể giảm một count query.

### 15.4. So sánh truy vấn JPQL và Criteria

| Thành phần | JPQL động | Criteria API |
|---|---|---|
| Cấu trúc WHERE | List câu điều kiện string cố định | List Predicate |
| Named parameters | Phải bind bằng setParameter | Expressions typed vào query tree |
| Keyword OR | Ngoặc trong string | cb.or() |
| Giá/Instant | JPQL comparison | cb.greaterThanOrEqualTo/lessThan |
| Join Category | LEFT JOIN p.category c | root.join("category", LEFT) |
| DTO | select new ... | cb.construct(...) |
| Order | String allowlist | Criteria Order allowlist |
| Count | JPQL thứ hai | CriteriaQuery<Long> thứ hai |
| Refactor tên property | String literal dễ sai | String Path vẫn dễ sai; metamodel tốt hơn |
| Query phức tạp | String khó quản lý | Biểu thức tường minh nhưng verbose |
| SQL thực tế | Do provider/dialect sinh | Do provider/dialect sinh |

Criteria API không phải công cụ tạo ra SQL tự động nhanh hơn JPQL; cả hai thường được JPA provider dịch sang SQL. Hãy đánh giá **query plan** và code clarity, không giả định một cách luôn hiệu quả hơn.

## 16. Toán tử AND, OR và dấu ngoặc trong bộ lọc phức tạp

### 16.1. Một tìm kiếm có hai nhánh điều kiện

Giả sử yêu cầu:

- Luôn thuộc tenant-a và chưa deleted.
- Giá nằm trong khoảng quy định.
- Đồng thời thỏa **một trong hai nhánh**:
  - Status ACTIVE và name chứa "keyboard"; hoặc
  - Status DRAFT và SKU bắt đầu bằng "PRE-".

Logical expression:

~~~text
tenant = :tenant AND deleted = false
AND price BETWEEN :min AND :max
AND (
    (status = ACTIVE AND name matches keyword)
    OR
    (status = DRAFT AND sku starts with PRE-)
)
~~~

Nếu không đặt group OR đúng cách, nhánh DRAFT có thể bỏ qua giá, deleted hoặc tenant filter.

### 16.2. Criteria dựng cấu trúc trực tiếp

~~~java
Predicate activeName = cb.and(
    cb.equal(root.get("status"), ProductStatus.ACTIVE),
    cb.like(
        cb.lower(root.get("name")),
        "%keyboard%"
    )
);

Predicate draftSku = cb.and(
    cb.equal(root.get("status"), ProductStatus.DRAFT),
    cb.like(root.get("sku"), "PRE-%")
);

Predicate specialGroup = cb.or(
    activeName,
    draftSku
);

Predicate finalCondition = cb.and(
    cb.equal(root.get("tenantId"), authorizedTenant),
    cb.isFalse(root.get("deleted")),
    cb.greaterThanOrEqualTo(
        root.<BigDecimal>get("price"), minPrice
    ),
    cb.lessThanOrEqualTo(
        root.<BigDecimal>get("price"), maxPrice
    ),
    specialGroup
);
~~~

Các literal "%keyboard%" và "PRE-%" trong ví dụ là **patterns được lập trình viên cố định** để minh họa; với chuỗi người dùng nhập phải normalize, escape và bind/type đúng. Không ghép raw user input thành một JPQL expression.

### 16.3. Phân biệt OR trong keyword và OR của filters

- Keyword name/sku: **OR nội bộ** của một filter.
- Mỗi filter khác nhau: **AND** với tenant, deleted, price, status.
- Nếu người dùng chọn nhiều statuses: thường là **IN** hoặc OR trên statuses, không phải AND status=ACTIVE AND status=DRAFT.
- Nếu yêu cầu ít nhất một trong nhiều tags: thường dùng EXISTS hoặc IN/OR trên tag IDs, không phải AND tất cả tags theo một join alias.

### 16.4. Logic rỗng của AND/OR

Về logic boolean:
- AND của một tập điều kiện rỗng có thể coi là true.
- OR của một tập điều kiện rỗng có thể coi là false.

CriteriaBuilder có conjunction()/disjunction() cho các tình huống này. Nhưng **không bao giờ** để toàn bộ WHERE trống vì không có filters: tenant/deleted vẫn phải được thêm.

## 17. NULL, IN, EXISTS và kiểu tìm kiếm ba trạng thái

### 17.1. Không có filter khác với tìm NULL

Nếu categoryId không được gửi, Product chưa có Category vẫn hợp lệ. Nếu user muốn chỉ những Product chưa gán Category, cần thiết kế filter riêng.

Ví dụ enum:

~~~java
public enum CategoryMode {
    ANY,
    ASSIGNED,
    UNASSIGNED
}
~~~

Predicate Criteria:

~~~java
switch (categoryMode) {
    case ANY -> {
        // Không thêm predicate.
    }
    case ASSIGNED -> predicates.add(
        cb.isNotNull(root.get("category"))
    );
    case UNASSIGNED -> predicates.add(
        cb.isNull(root.get("category"))
    );
}
~~~

JPQL tương đương:

~~~text
p.category is not null
p.category is null
~~~

Nếu có categoryId cụ thể cùng mode=UNASSIGNED, hãy **reject combination vô nghĩa** hoặc định nghĩa precedence rõ, không lặng lẽ trả dữ liệu khó hiểu.

### 17.2. Tại sao = NULL sai trong JPQL/SQL?

NULL biểu diễn unknown/missing; dùng:

~~~text
p.category = null
~~~

không phải cách biểu diễn an toàn/chuẩn để tìm NULL. Dùng **IS NULL**:

~~~text
p.category is null
~~~

Trong Criteria API dùng cb.isNull(...) và cb.isNotNull(...).

### 17.3. IN cho nhiều trạng thái

Nếu client có thể chọn nhiều status values:

~~~java
List<ProductStatus> statuses =
    List.of(ProductStatus.ACTIVE, ProductStatus.DRAFT);

Predicate condition =
    root.get("status").in(statuses);
~~~

JPQL:

~~~text
p.status in :statuses
~~~

với setParameter("statuses", statuses) theo provider support. Cần validation mỗi enum status được phép hiển thị.

### 17.4. Empty IN list phải có semantics rõ

Một empty list có thể nghĩa:
1. **Không lọc status**; hoặc
2. **Không cho bản ghi nào khớp**.

Đừng tạo raw JPQL "IN ()" rồi giả định mọi database chấp nhận. Chọn policy rõ:
- Nếu empty = no filter → không thêm predicate.
- Nếu empty = match none → cb.disjunction() hoặc một predicate luôn false.

### 17.5. Filter quan hệ một-nhiều có thể dùng EXISTS

Giả sử Product được mở rộng quan hệ tags:

~~~java
@ManyToMany(fetch = FetchType.LAZY)
@JoinTable(
    name = "product_tags",
    joinColumns = @JoinColumn(name = "product_id"),
    inverseJoinColumns = @JoinColumn(name = "tag_id")
)
private Set<Tag> tags = new HashSet<>();
~~~

Với yêu cầu Product có ít nhất một tag thuộc tagIds:

~~~text
exists (
  select 1
  from Product sub
  join sub.tags tag
  where sub.id = p.id
    and tag.id in :tagIds
)
~~~

JPQL EXISTS biểu đạt **sự tồn tại**, không cần join Product với tags ở top-level để tạo rows trùng.

### 17.6. Criteria correlated subquery

Với CriteriaQuery<?> query và Root<Product> root:

~~~java
Subquery<Long> tagSubquery =
    query.subquery(Long.class);

Root<Product> correlated =
    tagSubquery.correlate(root);

Join<Product, Tag> tagJoin =
    correlated.join("tags", JoinType.INNER);

tagSubquery.select(cb.literal(1L));
tagSubquery.where(
    tagJoin.get("id").in(tagIds)
);

Predicate hasTag = cb.exists(tagSubquery);
~~~

Ở đây Tag và association tags cần được khai báo thật trong entity/model; đoạn này là phần **mở rộng** bài toán. Nếu muốn dùng nó trong cả data và count query, predicate builder cần nhận query hiện tại để tạo subquery theo **từng CriteriaQuery**, không tái sử dụng Subquery/Root của query khác.

### 17.7. EXISTS và security scope

Nếu tags/related entities thuộc tenant, cần kiểm tra authorization của các references. Tùy model, correlated Product đã bị tenant scope bên ngoài nhưng tags relation có thể vẫn trỏ cross-tenant nếu DB cho phép; hệ thống nên bảo vệ reference integrity qua application và DB.

## 18. JOIN một-nhiều, DISTINCT và COUNT DISTINCT

### 18.1. Khi join làm nhân rows

Một Product có 3 tags. Query:

~~~text
select p
from Product p
join p.tags t
where ...
~~~

về mặt relational join có thể tạo ba rows cho cùng Product. Provider có thể xử lý entity identity/distinct theo các trường hợp khác nhau, nhưng **không được tự mặc định** result list và SQL count luôn có đúng số Product.

### 18.2. JPQL DISTINCT

~~~java
String jpql = """
    select distinct p
    from Product p
    join p.tags t
    where p.tenantId = :tenant
      and p.deleted = false
      and t.id in :tagIds
    """;
~~~

Với count:

~~~java
String countJpql = """
    select count(distinct p.id)
    from Product p
    join p.tags t
    where p.tenantId = :tenant
      and p.deleted = false
      and t.id in :tagIds
    """;
~~~

JPA providers/dialects có thể phát SQL khác nhau và có chi phí DISTINCT. Với many-to-many/tags filter, **EXISTS** thường là lựa chọn đáng cân nhắc để tránh duplicate ngay ở truy vấn cha.

### 18.3. Criteria distinct

~~~java
cq.select(root).distinct(true);

CriteriaQuery<Long> countCq =
    cb.createQuery(Long.class);

Root<Product> countRoot =
    countCq.from(Product.class);

countCq.select(
    cb.countDistinct(countRoot.get("id"))
);
~~~

Nếu có joins trong count query, phải tạo joins/predicates tương ứng trên countRoot. Không copy Predicate đang gắn với Root của data query.

### 18.4. Phân trang với join collection

Nếu query SELECT Product JOIN FETCH p.tags và setFirstResult/setMaxResults, database có thể trả nhiều rows mỗi Product; provider có thể phải pagination trong memory hoặc báo lỗi tùy cấu hình. Đây là vấn đề correctness/performance.

Giải pháp thường dùng:
1. Page **Product IDs** với filters và stable ORDER BY.
2. Fetch entities/related collections cho tập IDs nhỏ.
3. Ghép DTO và **khôi phục thứ tự IDs** của trang.
4. Count riêng theo cùng filter nếu cần.

Hoặc dùng query DTO projection/multiple queries phù hợp, không fetch collection một cách tùy tiện.

### 18.5. Criteria LEFT JOIN và INNER JOIN

- LEFT JOIN Category: giữ Product chưa gán Category.
- INNER JOIN Category: loại Product không có Category.
- JOIN tags: có thể nhân rows nếu nhiều tags.
- LEFT JOIN tags rồi WHERE t.id=... thường khiến các rows không có tag bị loại, về mặt filter giống inner join.
- Mọi join có thể ảnh hưởng execution plan và cardinality.

Thiết kế join theo **yêu cầu nghiệp vụ**, không chỉ thêm join để “chắc có dữ liệu”.

## 19. Dữ liệu nhiều giá trị và thứ tự logic filters

### 19.1. Lọc theo nhiều category IDs

~~~java
if (!categoryIds.isEmpty()) {
    Predicate oneOfCategories =
        root.get("category").get("id")
            .in(categoryIds);

    predicates.add(oneOfCategories);
}
~~~

Chọn semantics cho empty categoryIds; validate upper bound số IDs (ví dụ tối đa 50) để tránh IN list hàng chục nghìn phần tử.

### 19.2. Price ranges lẻ

Nếu UI hỗ trợ các khoảng:
- Dưới 500.000;
- 500.000–1.500.000;
- Trên 1.500.000;

có thể dùng OR group:

~~~java
Predicate low = cb.lessThan(
    root.<BigDecimal>get("price"),
    new BigDecimal("500000")
);

Predicate mid = cb.between(
    root.<BigDecimal>get("price"),
    new BigDecimal("500000"),
    new BigDecimal("1500000")
);

Predicate high = cb.greaterThan(
    root.<BigDecimal>get("price"),
    new BigDecimal("1500000")
);

Predicate anyRange = cb.or(low, mid, high);
~~~

cb.between bao gồm cả hai biên; nếu các khoảng liền nhau cần không chồng lấn, dùng half-open intervals hoặc xác định rõ các điểm ranh giới.

### 19.3. User-facing filters cần chính sách visibility

Một user chỉ được xem ACTIVE Products có thể không được quyền chọn status=DRAFT tùy ý. Status filter do client nhập là một **đề xuất tìm kiếm**, không phải quyền truy cập; service có thể giới hạn tập statuses bằng permission predicate được thêm bắt buộc.

### 19.4. Không áp “visibility” sau pagination

Nếu page lấy 20 rows rồi ứng dụng filter bỏ 15 rows không có quyền đọc, page chỉ còn 5 items, count sai và dữ liệu chưa được phép đã tải vào JVM. Đưa access control/tenant/visibility vào query trước offset, limit.

## 20. Spring Data JPA Specification

Spring Data JPA cung cấp abstraction **Specification<T>** để ghép predicates dựa trên Criteria API. Nó hữu ích với bộ lọc entity nhiều đoạn và repository đã dùng JpaSpecificationExecutor.

### 20.1. Repository

~~~java
public interface ProductJpaRepository
        extends JpaRepository<Product, Long>,
                JpaSpecificationExecutor<Product> {
}
~~~

### 20.2. Specifications có trách nhiệm đơn lẻ

~~~java
public final class ProductSpecifications {

    private ProductSpecifications() {}

    public static Specification<Product> visibleTo(
            String tenantId) {

        return (root, query, cb) -> cb.and(
            cb.equal(root.get("tenantId"), tenantId),
            cb.isFalse(root.get("deleted"))
        );
    }

    public static Specification<Product> hasStatus(
            ProductStatus status) {

        return (root, query, cb) ->
            cb.equal(root.get("status"), status);
    }

    public static Specification<Product> minPrice(
            BigDecimal price) {

        return (root, query, cb) ->
            cb.greaterThanOrEqualTo(
                root.<BigDecimal>get("price"),
                price
            );
    }

    public static Specification<Product> keyword(
            String keyword) {

        return (root, query, cb) -> {
            String pattern =
                LikePatterns.containsLiteral(keyword);

            return cb.or(
                cb.like(
                    cb.lower(root.get("name")),
                    pattern,
                    '!'
                ),
                cb.like(
                    cb.lower(root.get("sku")),
                    pattern,
                    '!'
                )
            );
        };
    }
}
~~~

Các snippets cần imports org.springframework.data.jpa.domain.Specification, Product, BigDecimal và ProductStatus; chúng mô tả một composition style phù hợp Spring Data JPA. Không gọi keyword() nếu keyword null/rỗng vì LikePatterns sẽ từ chối; caller chỉ thêm spec khi filter hiện diện.

### 20.3. Kết hợp với Pageable

~~~java
Specification<Product> spec =
    ProductSpecifications.visibleTo(authorizedTenant);

if (filter.status() != null) {
    spec = spec.and(
        ProductSpecifications.hasStatus(
            filter.status()
        )
    );
}

if (filter.minPrice() != null) {
    spec = spec.and(
        ProductSpecifications.minPrice(
            filter.minPrice()
        )
    );
}

if (filter.keyword() != null) {
    spec = spec.and(
        ProductSpecifications.keyword(
            filter.keyword()
        )
    );
}

Pageable pageable = PageRequest.of(
    filter.page(),
    filter.size(),
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);

Page<Product> result =
    repository.findAll(spec, pageable);
~~~

Lưu ý đây là ví dụ **chỉ ghép một phần filters** để minh họa Specification; production phải thêm category/maxPrice/date và sort enum allowlist cho tương đương search contract ở phần trước.

### 20.4. Khi nào Specification phù hợp?

- Project dùng Spring Data JPA;
- Muốn tái sử dụng predicates giữa repository methods;
- Filters chủ yếu trả Entity;
- Muốn kết hợp and/or mà không xây query class đầy đủ.

### 20.5. Khi nào cần custom Criteria repository thay vì Specification đơn giản?

- Output là DTO projection phức tạp;
- Query sử dụng aggregates/grouping/HAVING;
- Count query khác data query;
- Joins/subqueries nhiều và chỉ thêm theo điều kiện;
- Cần keyset/cursor protocol đặc biệt;
- Muốn kiểm soát chặt SELECT list để tránh tải dư.

### 20.6. Không dùng fetch join collection bừa trong Specification

Một Specification có root.fetch("orders") có thể được áp vào cả count query hoặc pagination query, gây lỗi/fetch nhiều hàng. Nên tách fetch plan/query shape khỏi filter predicate, hoặc dùng custom Criteria/DTO projection.

### 20.7. Page<Product>.map() có thể gây N+1

~~~java
Page<ProductListItem> dtoPage =
    result.map(product -> new ProductListItem(
        product.getId(),
        product.getName(),
        product.getSku(),
        product.getPrice(),
        product.getCategory() == null
            ? null
            : product.getCategory().getName()
    ));
~~~

Nếu category lazy, mapping mỗi Product có thể phát SELECT riêng. Dùng projection JOIN hoặc EntityGraph/fetch plan có kiểm soát, và đo SQL thực tế. Không suy rằng “đã dùng Specification” thì tự tối ưu lazy relationships.

## 21. Những cấu trúc query nào nên được tái sử dụng?

Tái sử dụng **business predicate rules**:
- Tenant visibility;
- Deleted=false;
- Status allowed;
- Category filter;
- Keyword literal matching;
- Price/date ranges.

Không nhất thiết tái sử dụng:
- SELECT fields (public list DTO khác admin detail);
- Order list (mỗi endpoint có sort contract);
- Fetch graph (mỗi use case cần dữ liệu khác nhau);
- Count query shape (to-many join có thể cần distinct);
- Limit/cursor mechanism.

Nếu trộn tất cả vào một “UniversalSearchBuilder” lớn, code có thể trở nên khó hiểu hơn các repository queries riêng. Tách theo **search use case**, không cố tạo một DSL tổng quát khi không cần.

## 22. Offset pagination và giới hạn tài nguyên

### 22.1. OFFSET + LIMIT trong JPA

Trong JPQL/Criteria, dùng:

~~~java
query.setFirstResult(page * size);
query.setMaxResults(size);
~~~

Không nhét raw LIMIT/OFFSET syntax vào portable JPQL. setFirstResult nhận int; với page và size từ input cần:
1. page >= 0;
2. size từ 1 đến giới hạn;
3. Tính offset bằng long để không integer overflow;
4. Từ chối offset lớn hơn Integer.MAX_VALUE;
5. Có max page/cost policy nếu workload cần.

### 22.2. Tại sao OFFSET lớn chậm?

Với một truy vấn ORDER BY, database có thể phải xem/đi qua nhiều rows để bỏ 1.000.000 rows trước khi lấy 20 rows kế tiếp. Nó còn phải thực hiện filters và đôi khi sort dataset lớn. Chỉ số page tăng không có nghĩa truy vấn có độ phức tạp không đổi.

### 22.3. Concurrent insert/delete làm page không ổn định

Giả sử trang đầu lấy Products IDs [30,29,28] theo createdAt desc. Trong lúc user chọn trang hai, Product mới được thêm ở đầu. Offset=3 có thể khiến Product#28 xuất hiện lần nữa.

ID tie-breaker ngăn thứ tự không xác định giữa các rows có cùng timestamp, nhưng **không ngăn dịch chuyển vị trí do concurrent changes**.

### 22.4. Count query có thể rất đắt

Với nhiều joins, keyword '%term%', tenant lớn hoặc nhiều điều kiện, COUNT(*) chính xác có thể tốn chi phí tương đương scan lượng dữ liệu lớn. Với endless scroll, có thể trả:
- Items;
- hasNext;
- Cursor sau cùng;

thay vì total exact ở mọi request. Nếu UI bắt buộc total, cần đo cost và chọn indexes/caching thích hợp.

### 22.5. Tạo Slice bằng cách lấy size + 1

~~~java
int fetchLimit = Math.addExact(filter.size(), 1);

List<ProductListItem> fetched =
    dataQuery.setMaxResults(fetchLimit)
             .getResultList();

boolean hasNext = fetched.size() > filter.size();

List<ProductListItem> items = fetched.subList(
    0,
    Math.min(fetched.size(), filter.size())
);
~~~

Chỉ áp dụng khi business chấp nhận không có total chính xác. Nếu dùng subList để trả ra async/lâu dài, có thể copy List.copyOf(...) để tránh giữ backing list lớn.

## 23. Keyset pagination: tìm trang kế tiếp bằng khóa sắp xếp

Khi dữ liệu lớn hoặc cập nhật thường xuyên, keyset/cursor pagination thường hợp lý hơn OFFSET. Ý tưởng: trang kế tiếp bắt đầu **sau bản ghi cuối của trang trước** trong thứ tự xác định.

### 23.1. Ví dụ NEWEST: createdAt DESC, id DESC

Trang một:

~~~text
Product 105: 2026-11-15T10:00:00Z, id=105
Product 104: 2026-11-15T09:00:00Z, id=104
Product 103: 2026-11-15T09:00:00Z, id=103
~~~

Cursor lấy từ Product cuối:

~~~text
cursorCreatedAt = 2026-11-15T09:00:00Z
cursorId        = 103
~~~

Trang sau cần:

~~~text
p.createdAt < :cursorCreatedAt
OR
(
    p.createdAt = :cursorCreatedAt
    AND p.id < :cursorId
)
~~~

Những predicates này phải được AND với tenant, deleted, status, keyword và các filters khác.

### 23.2. JPQL keyset query

~~~java
String jpql = """
    select new com.example.catalog.api.ProductListItem(
        p.id, p.name, p.sku, p.price, c.name
    )
    from Product p
    left join p.category c
    where p.tenantId = :tenantId
      and p.deleted = false
      and (
          p.createdAt < :cursorTime
          or (
              p.createdAt = :cursorTime
              and p.id < :cursorId
          )
      )
    order by p.createdAt desc, p.id desc
    """;

List<ProductListItem> page =
    em.createQuery(jpql, ProductListItem.class)
      .setParameter("tenantId", authorizedTenant)
      .setParameter("cursorTime", lastCreatedAt)
      .setParameter("cursorId", lastId)
      .setMaxResults(21)
      .getResultList();
~~~

Ví dụ rút gọn chỉ có mandatory filters + cursor; production phải thêm **mọi filter khác** với logic chung và giữ filter state nhất quán giữa requests.

### 23.3. Criteria keyset predicate

~~~java
Predicate olderTimestamp = cb.lessThan(
    root.<Instant>get("createdAt"),
    lastCreatedAt
);

Predicate sameTimeSmallerId = cb.and(
    cb.equal(root.get("createdAt"), lastCreatedAt),
    cb.lessThan(
        root.<Long>get("id"),
        lastId
    )
);

Predicate afterCursor = cb.or(
    olderTimestamp,
    sameTimeSmallerId
);
~~~

Sau đó thêm afterCursor vào tập mandatory/optional predicates và ORDER BY createdAt DESC, ID DESC.

### 23.4. Cursor phải gắn với sort và filter contract

Một cursor tạo cho sort=NEWEST không được áp thẳng vào sort=PRICE_ASC. Cursor nên encode các key tương ứng, ví dụ price+id cho PRICE_ASC, và có thể gắn version/hash của filters.

Nếu cursor được client sửa tùy ý, cần validate/canonicalize hoặc ký token/HMAC tùy threat model, tránh để nó bypass tenant/visibility. Tenant vẫn phải lấy từ trusted context trong query, không tin metadata tenant trong cursor.

### 23.5. Cursor không luôn cho snapshot cố định

Keyset tránh nhiều vấn đề OFFSET nhưng không tự “đóng băng” dataset. Một Product đổi price/status/createdAt trong quá trình user duyệt vẫn có thể thay đổi vị trí hoặc visibility. Nếu yêu cầu export đúng một snapshot, cần snapshot ID/staging/query isolation phù hợp.

### 23.6. Composite cursor với nhiều sort fields

Nếu sắp xếp PRICE_ASC, ID_ASC, predicate sau cursor:

~~~text
price > :cursorPrice
OR
(
  price = :cursorPrice
  AND id > :cursorId
)
~~~

Nếu sort PRICE_DESC, ID_DESC thì đổi dấu comparator tương ứng. Với nullable sort fields, keyset phức tạp hơn vì cần định nghĩa NULLS FIRST/LAST và xử lý null trong cursor.

### 23.7. Khi nào vẫn chọn OFFSET?

- Màn hình quản trị có ít dữ liệu;
- User muốn đi trực tiếp đến page N;
- Dataset tương đối ổn định;
- Count exact là một yêu cầu;
- Complexity của cursor vượt lợi ích.

Cần chọn theo workload và API contract, không áp keyset như một quy tắc tuyệt đối.

## 24. SQL và database indexes để tìm kiếm nhanh

### 24.1. Query plan quan trọng hơn “JPQL hay Criteria”

Hai cách truy vấn có thể được JPA provider sinh SQL rất giống nhau. Nếu truy vấn chậm:
- Xem generated SQL và parameters hợp lệ;
- Xem EXPLAIN plan;
- Kiểm tra index selectivity, row estimates, join strategy;
- Kiểm tra COUNT và ORDER BY cost;
- Đo DB CPU, I/O, wall time, lock waits;
- Tách chi phí query khỏi JSON serialization/network.

Đừng kết luận Criteria nhanh hơn JPQL chỉ vì được dựng bằng Java objects.

### 24.2. Index theo tenant và visibility

Với truy vấn thường gặp:

~~~sql
WHERE tenant_id = ?
  AND deleted = false
  AND status = ?
ORDER BY created_at DESC, id DESC
LIMIT 20
~~~

một composite index đáng cân nhắc trên PostgreSQL:

~~~sql
CREATE INDEX idx_products_visible_status_recent
ON products(
    tenant_id,
    deleted,
    status,
    created_at DESC,
    id DESC
);
~~~

Đây chỉ là **ứng viên**. Nếu filters, phân phối status, phần trăm deleted hoặc ORDER BY khác, optimizer có thể chọn index khác. Đo trên dữ liệu gần production và tránh tạo quá nhiều indexes vì chúng làm INSERT/UPDATE chậm hơn.

### 24.3. Index cho category

~~~sql
CREATE INDEX idx_products_tenant_category
ON products(tenant_id, category_id);
~~~

Có thể giúp điều kiện tenant + category, nhưng hiệu quả phụ thuộc dữ liệu và planner. Không suy có index là mọi query dùng được nó.

### 24.4. Leading wildcard với LIKE

~~~sql
WHERE lower(name) LIKE '%keyboard%'
~~~

thường không dùng B-tree index thông thường hiệu quả vì pattern có wildcard ở đầu. Với PostgreSQL, có thể cân nhắc extension **pg_trgm**:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_products_lower_name_trgm
ON products
USING gin (lower(name) gin_trgm_ops);
~~~

Đây là **PostgreSQL-specific** và cần quyền/migration/policy phù hợp. Cũng có thể thêm index cho lower(sku) hoặc lựa chọn full-text search. Kiểm tra EXPLAIN với pattern/size thực tế trước khi quyết định.

### 24.5. Functional indexes và LOWER

Một query dùng lower(name) có thể cần functional index tương ứng. Nếu search có accent-insensitive normalization, index và query expression phải thống nhất; không áp một chức năng normalization ở Java mà DB index dùng logic khác.

### 24.6. EXPLAIN có kiểm soát

Trên PostgreSQL staging/test:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, name, price
FROM products
WHERE tenant_id = 'tenant-a'
  AND deleted = false
  AND status = 'ACTIVE'
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

EXPLAIN ANALYZE **thực thi query** để đo; không tùy tiện chạy những statements gây side effect hoặc truy vấn cực lớn trên production. Với dữ liệu nhạy cảm, logs/plan reports cần che parameters khi cần.

### 24.7. N+1 và DTO projection

Nếu load 100 Product entities rồi gọi product.getCategory().getName() trong mapper, có thể gây nhiều SELECT. Constructor projection với LEFT JOIN Category lấy categoryName trong câu query chính, giảm nguy cơ N+1 cho thuộc tính này.

DTO projection không tự chữa mọi N+1 nếu sau đó vẫn truy cập các lazy relations khác. Chỉ lấy đúng dữ liệu UI cần.

### 24.8. Không fetch tất cả rồi filter trong Java

Sai:

~~~java
List<Product> all = repository.findAll();

return all.stream()
    .filter(p -> p.getPrice().compareTo(min) >= 0)
    .toList();
~~~

Có thể tải hàng triệu rows, khó phân trang/đếm đúng và lộ dữ liệu ngoài tenant trước khi filter. Database nên thực hiện filters/ORDER BY/pagination trước khi chuyển rows về application.

### 24.9. Giới hạn độ phức tạp filter

Một API search có thể bị lạm dụng qua:
- keyword rất dài;
- hàng nghìn category IDs;
- page/size cực lớn;
- nested OR groups không giới hạn;
- regex/full-text query tốn tài nguyên;
- sort trên unindexed expression;
- count trên join graph rộng.

Cần validation, size limits, rate limit, query timeout, circuit/backpressure và observability theo threat model; không coi “đã bind parameters” là đã chống DoS.

## 25. Caching và tính đúng đắn của truy vấn

### 25.1. Cache key phải bao gồm security scope

Nếu cache key chỉ là:

~~~text
search:keyword=keyboard&page=0
~~~

thì tenant-b có thể nhận kết quả tenant-a nếu cache dùng chung. Key cần ít nhất:
- Trusted tenant/resource visibility scope;
- Filter normalized;
- Sort;
- Page/cursor;
- Audience/permission scope nếu response khác theo quyền;
- API version khi format thay đổi.

### 25.2. Kết quả tìm kiếm là dữ liệu thay đổi

Khi Product đổi price/status/deleted hoặc Category name, cached search result có thể stale. Cần TTL/invalidation strategy và xác định eventual consistency có chấp nhận không.

### 25.3. Không cache managed JPA entities cho HTTP response

Một cached Product entity/proxy có thể detached, chứa lazy state hoặc leak fields khi serializer thay đổi. Cache DTOs/projections hoặc search IDs với contract rõ, và không tái dùng dữ liệu qua tenants/roles trái phép.

### 25.4. Query cache không thay authorization

Bật Hibernate query cache hoặc second-level cache không tự cấp quyền và không tự giúp mọi dynamic search nhanh hơn. Cache hit rate có thể thấp khi filters đa dạng. Đo thực tế và bảo đảm visibility policy được gắn vào query/key.

## 26. Thiết kế HTTP API nhận filter

### 26.1. HTTP params phải được chuyển sang typed filter

Một controller Spring Web skeleton:

~~~java
@RestController
@RequestMapping("/products")
public class ProductSearchController {

    private final ProductSearchService service;

    public ProductSearchController(
            ProductSearchService service) {
        this.service = service;
    }

    @GetMapping
    public SearchPage<ProductListItem> search(
            @RequestParam(required = false)
            String keyword,

            @RequestParam(required = false)
            Long categoryId,

            @RequestParam(required = false)
            BigDecimal minPrice,

            @RequestParam(required = false)
            BigDecimal maxPrice,

            @RequestParam(required = false)
            ProductStatus status,

            @RequestParam(required = false)
            @DateTimeFormat(
                iso = DateTimeFormat.ISO.DATE_TIME
            )
            Instant createdFrom,

            @RequestParam(required = false)
            @DateTimeFormat(
                iso = DateTimeFormat.ISO.DATE_TIME
            )
            Instant createdTo,

            @RequestParam(defaultValue = "NEWEST")
            ProductSort sort,

            @RequestParam(defaultValue = "0")
            int page,

            @RequestParam(defaultValue = "20")
            int size) {

        ProductSearchFilter filter =
            new ProductSearchFilter(
                keyword, categoryId,
                minPrice, maxPrice,
                status, createdFrom, createdTo,
                sort, page, size
            );

        return service.search(filter);
    }
}
~~~

Các imports từ Spring Web, Spring format, BigDecimal, Instant và application classes cần bổ sung theo project package. Đoạn này cố tình không nhận raw tenantId từ HTTP. ProductSearchService lấy trusted tenant qua TenantAccess.

### 26.2. Input validation và error mapping

Nếu client gửi:
- page=-3;
- size=100000;
- minPrice>maxPrice;
- sort=someUntrustedExpression;
- status không thuộc enum;
- createdFrom sau createdTo;

thì binding/validation phải trả lỗi API có kiểm soát, không để stack trace/SQL/provider internals ra public response. Có thể dùng @ControllerAdvice và stable code như INVALID_SEARCH_FILTER.

### 26.3. Không bỏ qua validation khi API có default values

Default size=20, sort=NEWEST không thay việc kiểm tra upper bound và unknown enum values. Với optional filters, phân biệt query param không tồn tại, blank và invalid.

### 26.4. Controller không nên tự lắp JPQL

Controller chỉ chuyển HTTP params thành DTO và gọi service. Authorization ở application layer; query logic ở repository adapter. Điều này giúp:
- Test HTTP binding độc lập;
- Test repository JPQL/Criteria bằng dữ liệu thực;
- Thay công nghệ query mà không đổi API contract;
- Giảm nguy cơ controller tự bỏ tenant predicate.

### 26.5. Định nghĩa contract rõ cho keyword

Nếu keyword là chuỗi literal, dấu %/ _ không mang wildcard ý định của user. Nếu business muốn cho phép wildcard advanced search, phải thiết kế một chế độ riêng có parser, grammar allowlist, độ dài/chi phí giới hạn; không cho phép tùy ý raw JPQL.

## 27. Chuẩn bị integration test PostgreSQL

Test mock EntityManager không chứng minh JPQL được provider parse, Criteria đúng join, counts chính xác hay LEFT JOIN giữ uncategorized. Với tìm kiếm động, integration test nên dùng database gần production, có dữ liệu nhiều tenants/statuses.

### 27.1. Các nhóm dependencies

Với Spring Boot 3/Jakarta và Java 17:
- spring-boot-starter-data-jpa;
- postgresql JDBC driver;
- spring-boot-starter-test;
- org.testcontainers:postgresql;
- org.testcontainers:junit-jupiter;
- spring-boot-starter-web nếu test HTTP layer.

Dùng BOM/versions tương thích với Spring Boot project. Testcontainers cần container runtime (Docker hoặc tương đương) sẵn sàng. Không trộn javax.persistence của JPA cũ với jakarta.persistence của Boot 3.

### 27.2. Testcontainers fixture

~~~java
@SpringBootTest
@Testcontainers
class ProductSearchIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void postgres(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.datasource.url",
            POSTGRES::getJdbcUrl
        );
        registry.add(
            "spring.datasource.username",
            POSTGRES::getUsername
        );
        registry.add(
            "spring.datasource.password",
            POSTGRES::getPassword
        );
        registry.add(
            "spring.jpa.hibernate.ddl-auto",
            () -> "create-drop"
        );
    }

    @Autowired
    @Qualifier("productJpqlSearchRepository")
    ProductSearchRepository jpqlRepository;

    @Autowired
    @Qualifier("productCriteriaSearchRepository")
    ProductSearchRepository criteriaRepository;

    @Autowired
    PlatformTransactionManager txManager;

    @PersistenceContext
    EntityManager em;

    private TransactionTemplate tx;
    private String tenantId;
    private Long categoryId;

    @BeforeEach
    void seedData() {
        tx = new TransactionTemplate(txManager);
        tenantId = "test-" + UUID.randomUUID();

        tx.executeWithoutResult(status -> {
            Category category =
                new Category(tenantId, "Keyboards");

            em.persist(category);
            em.flush();
            categoryId = category.getId();

            Instant base =
                Instant.parse("2026-01-01T00:00:00Z");

            em.persist(new Product(
                tenantId,
                "Mechanical Keyboard",
                "MK-" + UUID.randomUUID(),
                new BigDecimal("1500000"),
                ProductStatus.ACTIVE,
                base,
                category
            ));

            em.persist(new Product(
                tenantId,
                "Office Keyboard",
                "OK-" + UUID.randomUUID(),
                new BigDecimal("400000"),
                ProductStatus.ACTIVE,
                base.plusSeconds(60),
                category
            ));

            em.persist(new Product(
                tenantId,
                "Gaming Keyboard",
                "GK-" + UUID.randomUUID(),
                new BigDecimal("2500000"),
                ProductStatus.DRAFT,
                base.plusSeconds(120),
                category
            ));

            em.persist(new Product(
                tenantId,
                "Wireless Mouse",
                "WM-" + UUID.randomUUID(),
                new BigDecimal("700000"),
                ProductStatus.ACTIVE,
                base.plusSeconds(180),
                null
            ));

            em.persist(new Product(
                "another-" + tenantId,
                "Mechanical Keyboard Pro",
                "OTHER-" + UUID.randomUUID(),
                new BigDecimal("1100000"),
                ProductStatus.ACTIVE,
                base.plusSeconds(240),
                category
            ));
        });
    }
}
~~~

**Đây là khung test:** cần imports Jakarta Persistence, Spring Test, Testcontainers, JUnit Jupiter, TransactionTemplate, UUID, BigDecimal, Instant và các entity/DTO/repository. Có thể đặt test methods tiếp theo trong cùng class.

### 27.3. Ghi chú về fixture cross-tenant Category

Để mô hình multi-tenant nghiêm ngặt, Product khác tenant không nên tham chiếu Category của tenant hiện tại. Fixture trên nhằm kiểm tra **Product tenant predicate**, nhưng nếu schema/DB đã enforce composite FK/RLS, cần tạo một Category riêng cho "another-" + tenantId và liên kết đúng tenant đó.

Khi triển khai thật, hãy chủ động đảm bảo mọi references được phép; không dùng test fixture cross-tenant sai rồi hiểu đó là recommendation thiết kế schema.

### 27.4. Vì sao dùng transaction setup riêng?

tx.executeWithoutResult hoàn tất transaction seed trước khi query tests chạy, giúp:
- Records đã commit;
- Queries ở context mới có thể nhìn dữ liệu;
- Không phụ thuộc một @Transactional rollback-only test method;
- Tách rõ fixture DB state và search read outcome.

Với integration test thuần read có thể dùng @DataJpaTest rollback, nhưng nếu muốn xác minh commit boundary, concurrency hoặc nhiều connections, quản lý explicit transactions sẽ rõ hơn.

### 27.5. Fixture isolation

Mỗi test dùng tenantId ngẫu nhiên để tránh xung đột dữ liệu giữa test cases. Nếu suite tạo nhiều rows với create-drop theo toàn class, cần cleanup/data retention phù hợp để test không làm tăng DB vô hạn. Không dùng database production hoặc shared public tenant.

## 28. Integration tests: JPQL và Criteria phải tương đương

### 28.1. Helper tạo filter

~~~java
private ProductSearchFilter filter(
        String keyword,
        Long categoryId,
        BigDecimal minPrice,
        BigDecimal maxPrice,
        ProductStatus status) {

    return new ProductSearchFilter(
        keyword,
        categoryId,
        minPrice,
        maxPrice,
        status,
        null,
        null,
        ProductSort.NEWEST,
        0,
        20
    );
}
~~~

### 28.2. Test kết hợp keyword + category + price + status

~~~java
@Test
void bothEnginesFindSameMatchingProduct() {
    ProductSearchFilter f = filter(
        "keyboard",
        categoryId,
        new BigDecimal("500000"),
        new BigDecimal("2000000"),
        ProductStatus.ACTIVE
    );

    SearchPage<ProductListItem> a =
        jpqlRepository.search(tenantId, f);

    SearchPage<ProductListItem> b =
        criteriaRepository.search(tenantId, f);

    assertEquals(1L, a.total());
    assertEquals(1L, b.total());

    assertEquals(
        List.of("Mechanical Keyboard"),
        a.items().stream().map(
            ProductListItem::name
        ).toList()
    );

    assertEquals(
        a.items().stream().map(
            ProductListItem::id
        ).toList(),
        b.items().stream().map(
            ProductListItem::id
        ).toList()
    );
}
~~~

### 28.3. Test không lọc category vẫn giữ Product chưa gán Category

~~~java
@Test
void noCategoryFilterKeepsUncategorizedProduct() {
    ProductSearchFilter f = filter(
        "mouse",
        null,
        null,
        null,
        ProductStatus.ACTIVE
    );

    SearchPage<ProductListItem> result =
        criteriaRepository.search(tenantId, f);

    assertEquals(1, result.items().size());
    assertEquals(
        "Wireless Mouse",
        result.items().get(0).name()
    );
    assertNull(
        result.items().get(0).categoryName()
    );
}
~~~

Nếu data query vô tình dùng INNER JOIN Category, test này sẽ thất bại.

### 28.4. Test tenant khác không xuất hiện

~~~java
@Test
void otherTenantIsNeverReturned() {
    ProductSearchFilter f =
        filter(null, null, null, null, null);

    SearchPage<ProductListItem> result =
        jpqlRepository.search(tenantId, f);

    assertEquals(4L, result.total());

    assertTrue(
        result.items().stream()
            .noneMatch(p ->
                p.name().equals(
                    "Mechanical Keyboard Pro"
                )
            )
    );
}
~~~

Ở fixture hiện tại có bốn Products tenant hiện tại và một Product tenant khác. Trong production, đây phải là một HTTP authorization test nữa, để khẳng định caller không thể tự chọn raw tenantId.

### 28.5. Test biên giá

~~~java
@Test
void inclusivePriceBounds() {
    ProductSearchFilter f = filter(
        null,
        null,
        new BigDecimal("700000"),
        new BigDecimal("1500000"),
        ProductStatus.ACTIVE
    );

    SearchPage<ProductListItem> result =
        jpqlRepository.search(tenantId, f);

    assertEquals(
        Set.of(
            "Mechanical Keyboard",
            "Wireless Mouse"
        ),
        result.items().stream()
            .map(ProductListItem::name)
            .collect(Collectors.toSet())
    );
}
~~~

Min và max được lấy nếu price đúng bằng biên. Use cases tiền tệ nên giữ BigDecimal/scale policy rõ.

### 28.6. Test count và data dùng cùng filter

~~~java
@Test
void countMatchesFilteredItemsWhenPageLargeEnough() {
    ProductSearchFilter f = filter(
        "keyboard",
        null,
        null,
        null,
        ProductStatus.ACTIVE
    );

    SearchPage<ProductListItem> result =
        criteriaRepository.search(tenantId, f);

    assertEquals(2L, result.total());
    assertEquals(2, result.items().size());
}
~~~

Với size=20 lớn hơn số kết quả, total phải bằng items.size() khi không có concurrent writes. Nếu filter status bị bỏ sót trong count query, test sẽ phát hiện.

### 28.7. Test pagination không trùng IDs

~~~java
@Test
void twoPagesDoNotRepeatIdsOnStaticData() {
    ProductSearchFilter first =
        new ProductSearchFilter(
            null, null, null, null, null,
            null, null, ProductSort.NEWEST, 0, 2
        );

    ProductSearchFilter second =
        new ProductSearchFilter(
            null, null, null, null, null,
            null, null, ProductSort.NEWEST, 1, 2
        );

    List<Long> a = jpqlRepository.search(
        tenantId, first
    ).items().stream().map(
        ProductListItem::id
    ).toList();

    List<Long> b = jpqlRepository.search(
        tenantId, second
    ).items().stream().map(
        ProductListItem::id
    ).toList();

    assertEquals(2, a.size());
    assertEquals(2, b.size());
    assertTrue(
        Collections.disjoint(a, b)
    );
}
~~~

Đây là test dataset tĩnh; nó không chứng minh OFFSET không trùng khi dữ liệu thay đổi giữa page requests. Cần test riêng cho keyset pagination với concurrent insert/delete nếu API chọn keyset.

### 28.8. Test tìm dấu phần trăm literal

~~~java
@Test
void percentSignInKeywordIsNotAnUnrestrictedWildcard() {
    tx.executeWithoutResult(status -> {
        em.persist(new Product(
            tenantId,
            "100% Compatible Keyboard",
            "PCT-" + UUID.randomUUID(),
            new BigDecimal("100000"),
            ProductStatus.ACTIVE,
            Instant.parse("2026-01-02T00:00:00Z"),
            null
        ));

        em.persist(new Product(
            tenantId,
            "1000 Compatible Keyboard",
            "NUMBER-" + UUID.randomUUID(),
            new BigDecimal("100000"),
            ProductStatus.ACTIVE,
            Instant.parse("2026-01-03T00:00:00Z"),
            null
        ));
    });

    ProductSearchFilter f =
        filter("100%", null, null, null, null);

    SearchPage<ProductListItem> result =
        jpqlRepository.search(tenantId, f);

    assertEquals(1L, result.total());
    assertEquals(
        "100% Compatible Keyboard",
        result.items().get(0).name()
    );
}
~~~

Nếu LikePatterns không escape %, keyword "100%" có thể khớp "1000" và trả dữ liệu sai ngữ nghĩa. Test nên chạy cho cả JPQL và Criteria implementations.

### 28.9. Test soft-delete luôn bị loại

~~~java
@Test
void deletedProductsAreNeverReturned() {
    tx.executeWithoutResult(status ->
        em.createQuery(
            """
            update Product p
            set p.deleted = true
            where p.tenantId = :tenant
              and p.name = :name
            """
        )
        .setParameter("tenant", tenantId)
        .setParameter("name", "Office Keyboard")
        .executeUpdate()
    );

    ProductSearchFilter f =
        filter(null, null, null, null, null);

    SearchPage<ProductListItem> result =
        criteriaRepository.search(tenantId, f);

    assertEquals(3L, result.total());

    assertTrue(
        result.items().stream()
            .noneMatch(p ->
                p.name().equals("Office Keyboard")
            )
    );
}
~~~

Đây là thao tác bulk JPQL để chuẩn bị fixture, không phải gợi ý nên luôn soft-delete bằng bulk DML. Bulk DML bypass per-entity lifecycle/dirty checking của managed entities, vì vậy kiểm tra trong **transaction đọc mới** sau fixture update.

### 28.10. Test khoảng ngày nửa mở

~~~java
@Test
void createdToIsExclusive() {
    Instant start =
        Instant.parse("2026-01-01T00:00:00Z");

    Instant end =
        start.plusSeconds(60);

    ProductSearchFilter f =
        new ProductSearchFilter(
            null, null, null, null, null,
            start, end,
            ProductSort.OLDEST, 0, 20
        );

    SearchPage<ProductListItem> result =
        jpqlRepository.search(tenantId, f);

    assertEquals(1L, result.total());

    assertEquals(
        "Mechanical Keyboard",
        result.items().get(0).name()
    );
}
~~~

Product Office Keyboard tại đúng end bị loại. Bài học của khoảng [start,end) là không cần tạo timestamp giả kiểu 23:59:59.999.

### 28.11. Test input không hợp lệ

~~~java
@Test
void invalidPriceRangeIsRejected() {
    assertThrows(
        IllegalArgumentException.class,
        () -> new ProductSearchFilter(
            null, null,
            new BigDecimal("200"),
            new BigDecimal("100"),
            null, null, null,
            ProductSort.NEWEST, 0, 20
        )
    );
}
~~~

Các trường hợp tương tự:
- page âm;
- size=0;
- size vượt giới hạn;
- categoryId âm;
- ngày from >= to;
- keyword vượt max length;
- sort unknown khi parse từ HTTP.

### 28.12. Test JPQL injection input như dữ liệu thường

~~~java
@Test
void keywordTextDoesNotChangeJpqlStructure() {
    ProductSearchFilter f = filter(
        "' or 1=1 --",
        null, null, null, null
    );

    SearchPage<ProductListItem> result =
        jpqlRepository.search(tenantId, f);

    assertEquals(0, result.total());
}
~~~

Test này kiểm tra input cụ thể được bind như literal pattern, không trở thành OR condition của query. Không có test đơn lẻ nào chứng minh chống mọi injection; chính **design chỉ ghép fixed fragments + bind data + sort allowlist** mới là biện pháp gốc.

### 28.13. Test Criteria và JPQL parity qua tổ hợp filters

Có thể tạo table-driven tests:

| Keyword | Category | Min | Max | Status | Expected |
|---|---|---:|---:|---|---|
| null | null | null | null | null | 4 |
| keyboard | null | null | null | null | 3 |
| keyboard | category | 500000 | 2000000 | ACTIVE | 1 |
| mouse | null | null | null | ACTIVE | 1 |
| null | category | null | null | DRAFT | 1 |
| never-match | null | null | null | null | 0 |

Với mỗi row:
1. Tạo ProductSearchFilter;
2. Chạy JPQL repository và Criteria repository trên cùng committed fixture;
3. Assert totals bằng nhau;
4. Assert ordered Product IDs bằng nhau;
5. Assert output fields tương đương;
6. Kiểm tra SQL count và data filters nếu instrumentation cho phép.

Không chỉ assert số lượng; hai truy vấn có thể cùng count=2 nhưng trả **hai Products khác nhau**.

### 28.14. Test COUNT DISTINCT với tags

Nếu mở rộng Product có tags, tạo Product có 3 tags phù hợp cùng filter. Query JOIN có thể tạo 3 rows nhưng API phải coi đó là **một Product**. Test:
- Count=1, không phải 3;
- Trang không bị duplicate;
- Không bỏ sót Product khác do limit áp trên joined rows;
- So sánh EXISTS với COUNT DISTINCT;
- Có tenant/visibility filter trong cả two queries.

### 28.15. Test HTTP layer

Dùng MockMvc hoặc WebTestClient phù hợp stack:
- GET /products?size=100000 → 4xx;
- GET /products?sort=rawSqlExpression → 4xx;
- GET /products?minPrice=200&maxPrice=100 → 4xx;
- Authenticated tenant-a không thấy tenant-b;
- Response không chứa deleted/tenant/internal fields;
- Pagination metadata đúng contract;
- Unknown status hoặc invalid date format được map thành safe ApiError.

Đây là HTTP binding/authorization tests, không thay repository integration tests.

## 29. Nhận diện và sửa lỗi query qua triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Keyword khớp rows của tenant khác | OR thiếu ngoặc hoặc tenant filter bị bỏ | Nhóm OR, mandatory predicates |
| Không trả Product chưa có Category | INNER JOIN thay LEFT JOIN | LEFT JOIN for optional relation |
| Count lớn hơn số Product thực | Join một-nhiều nhân rows | EXISTS/COUNT DISTINCT |
| Pagination lặp IDs | Sort thiếu ID tie-breaker hoặc dataset thay đổi | Stable order, cân nhắc keyset |
| Total khác dữ liệu filter | Data/count dùng WHERE khác | Dùng chung predicate builder |
| Criteria query báo invalid path | Sai tên Java persistent property | Dùng property đúng/static metamodel |
| JPQL constructor projection lỗi | Sai class/package/order/types constructor | Kiểm tra DTO constructor signature |
| LIKE tìm "%" trả quá nhiều | Wildcards chưa escaped | Escaping + parameter binding |
| Query không dùng index | LOWER/leading wildcard, index không phù hợp | EXPLAIN, functional/trigram index |
| Query rất chậm ở page lớn | OFFSET lớn | Cursor/keyset hoặc limit page |
| Trả sai dữ liệu soft-deleted | Quên mandatory deleted=false | Shared mandatory predicate |
| User tự đổi tenant query param | Tenant lấy từ request | Trusted security context |
| Native query bị injection | Ghép raw values/order | Bind params, allowlist identifiers |
| Sorting theo unallowed property | Sort chưa validate | Enum allowlist |
| Sort order thiếu ổn định | Order chỉ theo price/name | Thêm ID |
| ClassCastException projection | Kiểu query/constructor không khớp | Typed query/projection |
| Query COUNT bị N+1 hoặc chậm | Joins/subqueries không cần | Count query chuyên biệt |
| @EntityGraph không giảm query | Fetch plan không khớp result shape | Đo SQL, projection |
| @Transactional readOnly vẫn thấy total lệch | Statement snapshots khác nhau | Isolation/snapshot policy |
| Dynamic query không trả rows | Min>max hoặc contradictory filters | Validate trước query |
| Unbounded search gây DB quá tải | Size/filter complexity không giới hạn | Quotas, caps, timeouts |
| Reuse Criteria Predicate gây lỗi | Root thuộc CriteriaQuery khác | Build lại predicates theo Root mới |
| Cache tenant-a bị trả cho tenant-b | Cache key thiếu scope | Tenant/permission-aware cache |
| Join collection + pagination warning | Fetch join to-many với offset | Two-stage IDs/fetch |
| Product Category có tenant sai | FK/reference không scope | Validate association + DB constraints |

## 30. Khác biệt giữa bài toán tìm kiếm và update nghiệp vụ

### 30.1. Search projection là read model

ProductListItem chỉ là **dữ liệu kết quả**. Nó không phải managed JPA entity. Không gọi em.merge(dto) hoặc cố dùng DTO chứa ID để cập nhật một Product.

### 30.2. Update cần managed entity và business methods

Nếu UI tìm Product rồi người dùng sửa giá:
1. Nhận UpdateProductPriceRequest;
2. Lấy Product theo ID + tenant scope;
3. Kiểm tra quyền update và version;
4. Áp business method trên managed entity;
5. Commit transaction.

Không dùng bộ lọc search để suy rằng user có quyền chỉnh mọi Product xuất hiện trong kết quả.

### 30.3. Kết quả Search không phải bản xác thực vĩnh viễn

User thấy Product ACTIVE hôm nay, nhưng khi nhấn Activate/Delete ngày mai, trạng thái và quyền có thể đổi. Mỗi write use case cần authorization và state revalidation tại transaction của mình.

### 30.4. Export/report có thể cần cơ chế riêng

Xuất 500.000 Products có thể dùng streaming/chunked read, keyset paging và asynchronous job với resource limits, thay vì GET list size=500000. Transaction/snapshot/tenant scope và dữ liệu nhạy cảm cần được thiết kế riêng.

## 31. Bài tập thực hành

Mỗi bài tập nên có **query contract**, **code hoặc pseudocode**, **đầu vào/đầu ra dự kiến** và **cách kiểm thử**. Khi đề cập tenant, dùng authorized tenant từ server, không tin raw HTTP tenantId. Không chỉ viết câu WHERE mà bỏ qua count, sort và pagination.

### Bài 1. Một bộ lọc tối thiểu

Thiết kế ProductSearchFilter chỉ có keyword, page, size. Với keyword rỗng, query phải lấy tất cả Products được phép của một tenant và deleted=false, không tạo LIKE vô nghĩa.

### Bài 2. Price range

Thêm minPrice/maxPrice dùng BigDecimal. Xác định bao gồm biên hay không và viết validation min <= max. Với Product giá đúng 500000, filter minPrice=500000 có trả Product đó không?

### Bài 3. Ngày tạo theo ngày địa phương

UI chọn 15/11/2026 theo Asia/Ho_Chi_Minh. Chuyển sang khoảng Instant [start,end) rồi tạo predicates >=start và <end. Vì sao không dùng 23:59:59.999?

### Bài 4. Trạng thái sản phẩm

Thêm status là ProductStatus enum. Vì sao không ghép raw status request vào JPQL? Nếu user không được xem DRAFT, nên xử lý filter DRAFT như thế nào?

### Bài 5. Category filter

Nếu categoryId null nghĩa “không lọc”, hãy kiểm tra Product category=null vẫn được trả. Nếu cần “chỉ uncategorized”, thiết kế CategoryMode enum khác.

### Bài 6. Keyword trim

Input keyword="   " nên tạo filter nào? Có nên thêm LIKE '%%' không? Nêu tác động tới query plan và kết quả.

### Bài 7. Escaping wildcard

Với keyword "100%", xây LIKE pattern để tìm literal %. Viết unit test chứng minh không khớp "1000" nếu không chứa ký tự phần trăm.

### Bài 8. Escape character

Với escape='!', input "Hi!_%" được chuyển thành LIKE pattern nào? Giải thích thứ tự escape ! trước % và _.

### Bài 9. Case-insensitive search

Viết lower(p.name) LIKE :keyword và cb.lower(root.get("name")). Nêu những khác biệt có thể xảy ra khi tìm từ tiếng Việt có dấu, Unicode case folding và DB collation.

### Bài 10. Giới hạn request

Đề xuất giới hạn keyword <=100, size <=100 và category IDs <=50. Điều gì xảy ra nếu endpoint cho phép size=1.000.000?

### Bài 11. Tenant predicate bắt buộc

Viết JPQL query luôn áp p.tenantId=:tenantId và p.deleted=false. Nếu search criteria từ client không có filter nào, hai predicates này có còn không?

### Bài 12. Lỗi OR thiếu ngoặc

So sánh:

~~~text
tenant=:tenant AND name LIKE :q OR sku LIKE :q
~~~

với:

~~~text
tenant=:tenant AND (name LIKE :q OR sku LIKE :q)
~~~

Trình bày ví dụ Product thuộc tenant khác chỉ khớp SKU, và viết regression test.

### Bài 13. JPQL string injection

Một client gửi keyword="' OR 1=1 --". Viết cách bind parameter đúng, giải thích tại sao SQL/JPQL structure không được biến đổi. Không coi string replace thủ công là biện pháp thay parameter binding.

### Bài 14. Sort injection

Client gửi sort="price desc; delete ...". Tạo ProductSort enum và switch trả fixed ORDER BY fragments. Named parameter có thể thay tên SQL column không?

### Bài 15. Thứ tự ổn định

Hai Products có cùng price. Nếu sort PRICE_ASC chỉ dùng price, pagination có thể có vấn đề gì? Thêm id ASC làm tie-breaker và kiểm thử hai pages.

### Bài 16. JPQL WHERE builder

Viết một builder tạo List<String> predicates và Map<String,Object> params. Tất cả optional filters chỉ thêm điều kiện khi field có giá trị.

### Bài 17. Count query chia sẻ filter

Data query có categoryId và status, count query bị thiếu status. UI có biểu hiện gì? Tái sử dụng một JpqlSearchParts cho cả data/count.

### Bài 18. JPQL DTO projection

Viết select new ProductListItem(p.id,p.name,p.sku,p.price,c.name) với LEFT JOIN Category. Vì sao ProductListItem không phải managed entity?

### Bài 19. Query thiếu Category

Product không gán Category. Nếu thay LEFT JOIN thành INNER JOIN trong data projection, kết quả khác thế nào? Viết test có categoryName=null.

### Bài 20. Count và LEFT JOIN

Với Category many-to-one, count trên Product root có nhân duplicate rows không? Nếu chuyển thành collection tags, vấn đề cardinality thay đổi thế nào?

### Bài 21. Criteria WHERE

Viết CriteriaBuilder.and của tenant, deleted, status và price >= min. Vì sao phải giữ mandatory predicates ngay cả khi optional filters trống?

### Bài 22. Criteria OR keyword

Dùng cb.or(nameMatches, skuMatches) rồi đặt group đó trong cb.and với tenant/deleted. So sánh với lỗi OR precedence ở JPQL string.

### Bài 23. Typed Path cho BigDecimal

Viết root.<BigDecimal>get("price") và cb.lessThanOrEqualTo. Tại sao root.get("price") dùng tên property Java thay vì column price_amount của SQL?

### Bài 24. Count Root riêng

Tạo CriteriaQuery<ProductListItem> và CriteriaQuery<Long>. Có thể tái sử dụng Predicate được tạo với Root của data query cho count query không? Giải thích vì sao cần tạo lại từ shared rules.

### Bài 25. Criteria DTO constructor

Dùng cb.construct(ProductListItem.class, ...) với Category LEFT JOIN. Những lỗi nào có thể xảy ra khi constructor types/order không khớp?

### Bài 26. Static metamodel

Khảo sát việc tạo JPA static metamodel Product_.price, Product_.createdAt. So sánh tính an toàn khi refactor với string property paths. Không cần đổi toàn project, chỉ mô tả thiết lập annotation processor.

### Bài 27. NULL semantics

Một filter categoryId=null được hiểu là không lọc. Viết riêng filter tìm category IS NULL. Vì sao không viết category = null?

### Bài 28. Multi-select statuses

User chọn ACTIVE và DRAFT. Dùng IN/list Predicate thay vì status=ACTIVE AND status=DRAFT. Xác định empty list nghĩa no filter hay match none.

### Bài 29. Nested AND/OR

Thiết kế query:

~~~text
tenant AND deleted=false AND
(
    (ACTIVE AND price<=1000000)
    OR
    (DRAFT AND name LIKE '%preview%')
)
~~~

Dựng bằng CriteriaBuilder.and/or và đảm bảo tenant nằm ngoài OR group.

### Bài 30. Tag filter và EXISTS

Product có nhiều tags. Viết EXISTS correlated subquery tìm Product có ít nhất một Tag ID trong list. Vì sao EXISTS tránh duplicate Product rows tốt hơn top-level JOIN trong nhiều trường hợp?

### Bài 31. CountDistinct

Một Product có 3 matching tags. Count(p) trên join tạo count=3; count(distinct p.id) cần trả bao nhiêu? Viết test fixture hai Products với số tags khác nhau.

### Bài 32. Fetch join collection và pagination

Một repository có JOIN FETCH p.tags rồi setFirstResult/setMaxResults. Tại sao có thể pagination in-memory hoặc duplicate? Thiết kế chiến lược page IDs rồi fetch relations.

### Bài 33. Spring Data Specification

Tạo visibleTo(tenantId), hasStatus(status), minPrice(price) Specifications rồi kết hợp với and. Tại sao không thêm public fetch join collection trong specification dùng cho cả count?

### Bài 34. Specification và N+1

Page<Product> được map thành DTO bằng product.getCategory().getName(). Nếu Category lazy, có thể phát bao nhiêu SELECT? Chọn cách đo và giải pháp.

### Bài 35. Offset deep page

Page=50000, size=20. Tính offset và nêu chi phí database. Khi nào keyset pagination phù hợp hơn?

### Bài 36. Keyset NEWEST

Với sort createdAt DESC, id DESC và cursor (T,100), viết predicate:

~~~text
createdAt < T
OR
(createdAt = T AND id < 100)
~~~

Nêu vì sao dùng cả createdAt và ID.

### Bài 37. Keyset PRICE_ASC

Với sort price ASC, id ASC và cursor (500000,101), viết predicate cho trang kế tiếp. Nếu price bằng 500000 nhưng id=102, row đó có được lấy không?

### Bài 38. Cursor thay đổi filter

Client lấy cursor theo status=ACTIVE, rồi dùng cursor với status=DRAFT. API nên cho phép không? Thiết kế cursor metadata/filter hash và validation.

### Bài 39. Count vs Slice

Trang vô hạn chỉ cần hasNext, không cần total. Hãy lấy size+1 rows rồi trả hasNext và items đúng size. Giải thích tradeoff với total exact.

### Bài 40. Index cho tenant/status/date

Dựng index candidate cho WHERE tenant,deleted,status và ORDER BY createdAt DESC,id DESC. Dùng EXPLAIN để quyết định có hiệu quả không, thay vì khẳng định index luôn được dùng.

### Bài 41. LIKE leading wildcard

Tìm keyword với pattern '%keyboard%'. Vì sao B-tree thường không giúp nhiều? Nêu PostgreSQL pg_trgm/full-text và sự phụ thuộc dialect.

### Bài 42. Truy vấn chậm

Một API search trả 20 rows nhưng mất 5 giây. Thiết kế kế hoạch đo: SQL logs, EXPLAIN, query count, count query, joins, indexes, pool wait, serialization, cache hit rate.

### Bài 43. Cache cross-tenant

Cache key chỉ có keyword/page. User B có thể thấy kết quả của user A không? Thiết kế key theo tenant + normalized filters + sort + page + permission.

### Bài 44. Testcontainers integration test

Thiết kế PostgreSQL fixture có Products thuộc tenant-a, tenant-b, deleted=true, category=null, giá biên và status khác nhau. Viết tests chạy hai repository implementations và so product IDs + totals.

### Bài 45. Bộ kiểm thử đầy đủ

Viết matrix test cho:
- Keyword blank và literal "%";
- Min/max inclusive;
- Created-to exclusive;
- Category missing/null;
- Status ACTIVE/DRAFT;
- JOIN to-many count distinct;
- Sort tie-breaker;
- Page sizes;
- Cross-tenant/deleted;
- Invalid parameters;
- Injection string;
- Keyset cursor;
- DTO field exposure.

### Bài 46. Kiểm tra quyền theo trạng thái

Public user chỉ được xem ACTIVE, admin được xem cả DRAFT. Nếu status filter null, hai audiences có nên trả cùng số rows không? Đưa visibility predicate ở đâu?

### Bài 47. Soft delete và count

Một Product bị đánh dấu deleted=true. Data query loại nó nhưng count vẫn đếm. Tìm lỗi ở đâu? Tạo regression test sau khi soft delete.

### Bài 48. Search và business update

User thấy Product trong kết quả tìm kiếm, sau đó muốn sửa giá. Có thể dùng ProductListItem DTO và merge vào EntityManager để cập nhật không? Thiết kế update use case đúng.

### Bài 49. Refactor từ JPQL sang Criteria

Chuyển một ProductJpqlSearchRepository sang Criteria API mà không đổi HTTP API. Các integration tests nào chứng minh hai cách tương đương? Sự khác biệt SQL nào cần quan sát?

### Bài 50. Mini-project cuối bài

Xây một endpoint tìm kiếm Product hoàn chỉnh:

1. Product/Category JPA entities với tenantId và soft delete.
2. SearchFilter typed, price/date validation, sort enum.
3. Keyword matching name OR SKU, lowercase và escape LIKE.
4. Repository JPQL động với bind parameters.
5. Repository Criteria dùng Predicate builder tương đương.
6. Data DTO projection + count query.
7. Category LEFT JOIN và optional category filter.
8. Page/size upper bounds, ID tie-breaker.
9. Tenant/visibility predicates bắt buộc.
10. Spring service lấy tenant từ authenticated context.
11. Safe error response khi input không hợp lệ.
12. PostgreSQL Testcontainers fixtures và parity tests.
13. EXPLAIN/index đề xuất từ workload.
14. Giải thích khi nào chuyển sang keyset pagination.
15. Báo cáo đánh đổi giữa JPQL, Criteria, Specification và native search.

**Tiêu chí thành công:** JPQL và Criteria phải trả **cùng Product IDs, cùng total, cùng thứ tự cho cùng filter/sort/page trên dataset tĩnh**, không lộ tenant khác, không bị keyword/sort injection, và xử lý đúng dữ liệu NULL, wildcards, ranges và soft deletion.

## 32. Checklist triển khai tìm kiếm động

### 32.1. Yêu cầu nghiệp vụ và hợp đồng input

1. **Đã liệt kê các điều kiện tìm kiếm bắt buộc và tùy chọn chưa?**
2. **Tenant/permission có lấy từ trusted server context không?**
3. **Có xác định keyword tìm trong những properties nào không?**
4. **Có quy định keyword blank nghĩa không lọc không?**
5. **Có quy định cách xử lý hoa/thường, Unicode/dấu tiếng Việt không?**
6. **Có xử lý %, _, escape character trong LIKE không?**
7. **Có giới hạn độ dài keyword không?**
8. **CategoryId null là không lọc hay tìm uncategorized đã rõ chưa?**
9. **Có validation category ID âm/không hợp lệ không?**
10. **Có dùng BigDecimal và chọn min/max inclusive/exclusive rõ không?**
11. **Có reject minPrice > maxPrice không?**
12. **Có quy định ngày theo timezone nào không?**
13. **Có chuyển date filter thành Instant đúng timezone không?**
14. **Có dùng khoảng ngày [start,end) khi phù hợp không?**
15. **Có reject thời gian start >= end không?**
16. **Có giới hạn danh sách statuses/categories/tags không?**
17. **Có xác định empty IN list nghĩa gì không?**
18. **Có giới hạn page/size không?**
19. **Có tránh integer overflow khi tính offset không?**
20. **Có sort enum/key allowlist không?**

### 32.2. Bảo mật và query correctness

21. **Mọi query đều có tenant predicate bắt buộc không?**
22. **Có deleted=false hoặc visibility predicate theo policy không?**
23. **Data và count query có cùng security scope không?**
24. **Keyword OR đã được nhóm bên trong AND bắt buộc chưa?**
25. **Có bind mọi dữ liệu người dùng qua parameters/typed expressions không?**
26. **Có tránh nối raw input vào JPQL/SQL không?**
27. **Có tránh ORDER BY lấy trực tiếp từ user string không?**
28. **Có tránh filter unauthorized rows sau khi đã paging không?**
29. **Có check permission nếu public/admin thấy statuses khác nhau không?**
30. **Có tránh lộ object tenant khác qua total/count không?**
31. **Có validate nested relation IDs theo tenant khi dùng làm filter không?**
32. **Có rate limits/query complexity limits phù hợp không?**
33. **Có safe error response thay vì raw JPA/SQL exception không?**
34. **Có tránh log raw credentials/PII/search content không?**
35. **Có cache keys tách tenant/role/filter/sort/page không?**

### 32.3. JPQL động

36. **JPQL fragments có phải fixed literals do code kiểm soát không?**
37. **Named parameters có cùng tên trong WHERE và params map không?**
38. **Có chỉ thêm params cho predicates có mặt không?**
39. **Có bind enum, BigDecimal và Instant đúng Java types không?**
40. **Có dùng một shared builder cho data và count không?**
41. **Có LEFT JOIN khi relation có thể NULL không?**
42. **Có đúng tên JPA entity và Java property trong JPQL không?**
43. **Constructor projection package/types/order có khớp không?**
44. **Có count riêng không ORDER BY/OFFSET không?**
45. **Có điều kiện group AND/OR đúng precedence không?**
46. **Có tránh copy/paste filter rồi bỏ sót một nhánh trong count không?**

### 32.4. Criteria API và Specification

47. **Data CriteriaQuery và count CriteriaQuery có Root riêng không?**
48. **Có build lại predicates cho countRoot riêng không?**
49. **Có dùng cb.and/cb.or đúng logical grouping không?**
50. **Có dùng cb.isNull/isNotNull thay vì equality với NULL không?**
51. **Có dùng typed Path cho các comparisons cần Comparable không?**
52. **Có đặt JOIN đúng hướng và JoinType không?**
53. **Có dùng cb.construct cho DTO projection khi phù hợp không?**
54. **Có dùng Criteria Order từ sort allowlist không?**
55. **Có xem xét static metamodel khi refactor properties thường xuyên không?**
56. **Có tránh đưa fetch join to-many vào count/paging query không?**
57. **Có bảo đảm Specification tái sử dụng không âm thầm đổi query shape không?**
58. **Có tách query predicate rules khỏi output/fetch plan khi phù hợp không?**
59. **Có hiểu Criteria không tự authorize hoặc tự tối ưu SQL không?**

### 32.5. JOIN, count và phân trang

60. **Có nhận biết join một-nhiều có thể nhân Product rows không?**
61. **Khi cần có DISTINCT/COUNT DISTINCT/EXISTS đúng chưa?**
62. **Data và count có dùng cùng semantic filters không?**
63. **Có test count=1 khi Product có nhiều matching tags không?**
64. **Có ID tie-breaker khi sort theo field không unique không?**
65. **Có định nghĩa NULLS FIRST/LAST nếu sort field nullable không?**
66. **Có giới hạn OFFSET rất sâu hoặc cung cấp keyset khi phù hợp không?**
67. **Keyset cursor có khớp sort fields và comparator không?**
68. **Có gắn cursor với normalized filters và scope không?**
69. **Có chấp nhận tính không ổn định do dữ liệu đổi giữa page requests không?**
70. **Nếu cần snapshot nhất quán, có policy transaction/isolation không?**
71. **Nếu UI không cần total, có cân nhắc Slice/size+1 không?**
72. **Có tránh page directly over to-many JOIN FETCH không?**

### 32.6. Hiệu năng và khả năng vận hành

73. **Có xem generated SQL cho JPQL và Criteria không?**
74. **Có kiểm tra N+1 khi mapping relations không?**
75. **Có dùng DTO projection thay vì load toàn entity graph khi chỉ đọc vài fields không?**
76. **Có đo riêng data query và count query không?**
77. **Có EXPLAIN với filters/sort đại diện workload không?**
78. **Có index hỗ trợ tenant/visible/status/date khi cần không?**
79. **Có hiểu leading-wildcard LIKE và LOWER có thể làm B-tree kém hiệu quả không?**
80. **Có cân nhắc trigram/full-text khi search lớn không?**
81. **Có giới hạn request/filter complexity để tránh DB overload không?**
82. **Có query timeout/observability/metrics phù hợp không?**
83. **Có tránh tạo quá nhiều indexes làm write chậm không?**
84. **Có test với số rows/cardinality gần production không?**
85. **Có phân biệt query latency với connection pool wait và response serialization không?**

### 32.7. Integration testing và regression

86. **Có test trên database tương đương production không?**
87. **Có fixtures thuộc nhiều tenants/statuses/categories/price ranges không?**
88. **Có Product category=null để test LEFT JOIN không?**
89. **Có soft-deleted Product để test mandatory filter không?**
90. **Có test ký tự %/_/! literal trong keyword không?**
91. **Có test invalid page/size/min>max/date range không?**
92. **Có test sort injection và keyword injection như literal data không?**
93. **Có đối chiếu ordered IDs của JPQL và Criteria không?**
94. **Có đối chiếu total của JPQL và Criteria không?**
95. **Có test price/date inclusivity/exclusivity không?**
96. **Có test COUNT DISTINCT với nhiều tags không?**
97. **Có test hai pages không duplicate trên dataset tĩnh không?**
98. **Có test cross-tenant visibility và count leakage không?**
99. **Có test response DTO không lộ internal fields không?**
100. **Có regression tests khi đổi JPA provider, DB dialect hoặc index/query strategy không?**

## 33. Sơ đồ quyết định chọn cách viết tìm kiếm

~~~text
                    API cần tìm kiếm có filter động
                                  |
                                  v
                         Xác định contract
                 keyword, ranges, category, status,
                       tenant, sort, pagination
                                  |
                                  v
                          Có nhiều filter?
                        /                \
                       Ít               Nhiều
                        |                  |
                        v                  v
                Static JPQL hoặc      Cần nhiều nhóm
                JPQL builder         AND/OR, joins,
                đơn giản?            subqueries?
                        |               /       \
                        |             Có        Không
                        |              |          |
                        |              v          v
                        |         Criteria API   JPQL builder
                        |         hoặc Querydsl  / Specification
                        |              |          |
                        +--------------+----------+
                                       |
                                       v
                         Mandatory security predicates
                         tenant + visibility + deleted
                                       |
                                       v
                              Bind input values
                          và sort bằng allowlist
                                       |
                                       v
                         Data query + DTO projection
                                       |
                                       v
                        Count query hoặc Slice/cursor
                                       |
                                       v
                           Integration test fixtures
                            JPQL/Criteria parity
                                       |
                                       v
                             EXPLAIN, indexes,
                           query count, timeout
                                       |
                                       v
                          Monitoring + regression tests
~~~

### 33.1. Nếu project đã dùng Spring Data Specifications

Có thể tiếp tục dùng Specification cho các filters đơn giản trả Entity. Nếu use case cần projection/chia hai query đặc biệt, viết custom Criteria repository cũng hợp lý. Không ép một abstraction đảm nhiệm cả filtering, fetching, pagination, authorization và output format khi kiến trúc trở nên khó kiểm soát.

### 33.2. Nếu cần full-text hoặc fuzzy search nâng cao

Nếu search cần ranking, stemming tiếng Việt, autocomplete, typo tolerance, faceting hoặc tìm hàng triệu văn bản dài, JPQL LIKE có thể không đủ. Cân nhắc PostgreSQL full-text/trigram hoặc hệ thống tìm kiếm chuyên dụng, nhưng vẫn phải giữ:
- Tenant/permission scope;
- Filter correctness;
- Pagination consistency;
- Index/state synchronization;
- Data minimization;
- Security tests.

Đổi search backend không xóa các yêu cầu nền tảng này.

## 34. Bảng tra cứu nhanh

| Nhu cầu | JPQL | Criteria |
|---|---|---|
| Tenant bắt buộc | p.tenantId = :tenantId | cb.equal(root.get("tenantId"), tenant) |
| Soft-delete | p.deleted = false | cb.isFalse(root.get("deleted")) |
| Keyword chứa literal | LIKE :q ESCAPE '!' | cb.like(cb.lower(path), pattern, '!') |
| Name OR SKU | (A OR B) | cb.or(A, B) |
| Giá tối thiểu | p.price >= :min | cb.greaterThanOrEqualTo(...) |
| Giá tối đa | p.price <= :max | cb.lessThanOrEqualTo(...) |
| Ngày từ | p.createdAt >= :from | cb.greaterThanOrEqualTo(...) |
| Ngày đến exclusive | p.createdAt < :to | cb.lessThan(...) |
| Category chưa gán | p.category is null | cb.isNull(root.get("category")) |
| Nhiều statuses | p.status in :statuses | root.get("status").in(statuses) |
| Tag tồn tại | EXISTS (subquery) | cb.exists(subquery) |
| Category LEFT JOIN | left join p.category c | root.join("category", LEFT) |
| DTO projection | select new ...ProductListItem | cb.construct(ProductListItem.class, ...) |
| Count Product | count(p) | cb.count(root) |
| Count sau join to-many | count(distinct p.id) | cb.countDistinct(root.get("id")) |
| Sort PRICE_ASC | order by p.price asc, p.id asc | cb.asc(price), cb.asc(id) |
| Offset pagination | setFirstResult/setMaxResults | setFirstResult/setMaxResults |
| Cursor NEWEST | createdAt < T OR (=T AND id<cursorId) | cb.or(...) |
| No filter | Không thêm optional WHERE | Không thêm optional Predicate |
| Invalid filter | Reject trước query | Reject trước query |

## 35. Tổng kết

**Xây dựng tìm kiếm động bằng JPQL và Criteria** là bài toán kết hợp **business filter semantics, truy vấn JPA, authorization, projection, phân trang và kiểm thử**. Không chỉ cần “ghép WHERE theo input”; truy vấn còn phải đúng về tenant, NULL, AND/OR, joins, counts, sort và giới hạn tài nguyên.

### 35.1. Ba nguyên tắc cốt lõi

**Thứ nhất: dữ liệu client luôn là dữ liệu, không phải cú pháp truy vấn.**

~~~java
// Tốt: fixed query fragment + bound parameter.
conditions.add("p.price >= :minPrice");
params.put("minPrice", filter.minPrice());

// Tránh: raw input được ghép thành JPQL.
conditions.add(
    "p.price >= " + untrustedInput
);
~~~

Với sort, chỉ dùng enum/map allowlist; không thể bind raw column name qua named parameter.

**Thứ hai: authorization và visibility phải nằm trong query.**

~~~text
tenantId = authorizedTenant
AND deleted = false
AND optionalConditions...
~~~

Nếu bỏ ngoặc OR hoặc bỏ tenant predicate khỏi count query, hệ thống có thể làm lộ dữ liệu dù JPQL/Criteria được viết đúng cú pháp.

**Thứ ba: data query, count query và pagination phải cùng một contract.**

- Query DTO projection chọn đúng fields.
- Count tính đúng tập filtered Products.
- JOIN to-many phải xử lý duplicate bằng EXISTS/DISTINCT khi cần.
- ORDER BY có tie-breaker.
- Pagination dùng size cap; keyset phù hợp hơn khi offset sâu hoặc tập kết quả liên tục thay đổi.
- Test trên dữ liệu có tenant khác, deleted rows, category null, giá/ngày biên và multiple tags.

### 35.2. JPQL động và Criteria không phải đối thủ tuyệt đối

~~~text
JPQL động:
    WHERE fragments cố định
    + named params
    + sort allowlist
    + DTO projection

Criteria:
    Predicate tree
    + typed expressions
    + joins
    + CriteriaQuery DTO/count

Cả hai:
    mandatory security scope
    + domain validation
    + stable pagination
    + SQL plan measurement
    + integration tests
~~~

JPQL dễ đọc và gọn khi query đơn giản. Criteria hữu ích khi nhiều điều kiện được compose, join/subquery xuất hiện có điều kiện hoặc cần tái sử dụng expression rules. Spring Data Specification là một lựa chọn trung gian dựa trên Criteria API, phù hợp với nhiều bài toán filter entity.

### 35.3. Các câu hỏi trước khi đưa lên production

1. Người dùng có thể thấy dữ liệu tenant khác qua result hoặc count không?
2. Một keyword có chứa %/_ hoặc chuỗi giống cú pháp JPQL có thay cấu trúc query không?
3. Khi không chọn Category, Product chưa có Category có xuất hiện đúng không?
4. Các joins có nhân rows làm count và page sai không?
5. Các mức giá, khoảng thời gian và NULL có semantics đúng business không?
6. Khi filter trống, query vẫn có điều kiện bảo vệ nào?
7. Sort có ổn định, allowlisted và có ID tie-breaker không?
8. Query COUNT và data query cùng filters và visibility không?
9. Query có hoạt động hiệu quả trên dữ liệu lớn, không N+1 không?
10. Integration tests có chứng minh JPQL và Criteria trả cùng kết quả trên dữ liệu thực không?

**Kết luận:** Hãy tách filter contract khỏi entity, chuẩn hóa input sớm, thêm điều kiện bảo mật bất biến, dùng JPQL parameters hoặc Criteria predicates đúng ngữ nghĩa, chọn DTO projection và pagination hợp lý, rồi chứng minh bằng integration tests. Khi làm đúng những bước đó, chức năng tìm kiếm có thể mở rộng thêm nhiều điều kiện mà vẫn rõ ràng, an toàn và dễ duy trì.


















