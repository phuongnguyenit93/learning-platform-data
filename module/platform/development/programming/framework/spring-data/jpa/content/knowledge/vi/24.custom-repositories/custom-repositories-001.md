# Khi nào nên bổ sung hành vi ngoài phương thức truy vấn

## Mục tiêu

Spring Data JPA tạo được nhiều truy vấn từ tên method, `@Query`, `Specification` và các API truy vấn khác. Tuy nhiên, có những thao tác persistence cần nhiều quyền kiểm soát hơn: xây query động phức tạp, kết hợp nhiều nguồn dữ liệu, dùng Criteria API, native SQL, batch operation hoặc áp dụng một chiến lược tải dữ liệu riêng.

Khi đó, có thể bổ sung hành vi tùy biến vào repository. Cách mở rộng hiện đại được khuyến nghị là **repository fragment**: định nghĩa một interface nhỏ cho hành vi cần thêm, triển khai interface đó bằng class riêng, rồi kết hợp fragment vào repository chính.

Điều quan trọng là chọn đúng tầng:

- Query đơn giản, ổn định: dùng derived query method hoặc `@Query`.
- Bộ lọc động: cân nhắc `Specification`, Query by Example hoặc Querydsl.
- Hành vi truy cập dữ liệu cần API riêng hoặc điều khiển EntityManager: dùng custom repository fragment.
- Điều phối nhiều repository, kiểm tra quyền, gọi dịch vụ ngoài hoặc thực hiện quy trình nghiệp vụ: đặt ở service.
- Thay đổi hành vi mặc định dùng chung cho nhiều repository: cân nhắc custom repository base class.

Bài này giải thích dấu hiệu cần custom behavior, cách thiết kế fragment, transaction boundary, những lựa chọn thay thế và ví dụ chạy được với Java 17+, Spring Boot 3.4.5 và H2.

## 1. Khi nào query method đã đủ?

Derived query method phù hợp khi điều kiện có thể diễn đạt rõ bằng tên method và không cần cấu trúc truy vấn đặc biệt:

```java
List<Product> findByCategoryAndActiveTrueOrderByNameAsc(String category);
Optional<Product> findBySku(String sku);
long countByActiveTrue();
```

`@Query` phù hợp khi query có JPQL rõ ràng, ổn định và gắn với một repository method:

```java
@Query("select p from Product p where p.price >= :minimumPrice")
List<Product> findAffordable(@Param("minimumPrice") BigDecimal minimumPrice);
```

Không cần tạo custom implementation chỉ để thay một query đơn giản bằng Criteria API. Một method có tên rõ ràng thường ngắn hơn, dễ đọc hơn và ít mã bảo trì hơn.

## 2. Dấu hiệu nên bổ sung hành vi tùy biến

Custom repository behavior có ích khi xuất hiện một hoặc nhiều nhu cầu sau:

1. **Cấu trúc query thay đổi đáng kể theo runtime input.** Nhiều filter tùy chọn, nhóm AND/OR, join và subquery khiến một derived method hoặc `@Query` tĩnh trở nên khó quản lý.
2. **Cần điều khiển Criteria API hoặc EntityManager trực tiếp.** Ví dụ chọn projection theo yêu cầu, áp dụng locking, hint, flush hoặc persistence context.
3. **Cần native SQL hoặc tính năng riêng của database.** Ví dụ CTE, window function, full-text search, JSON operator hoặc truy vấn tối ưu theo execution plan.
4. **Cần thao tác dữ liệu theo lô.** Ví dụ bulk update/delete, batch insert hoặc xử lý lượng lớn dữ liệu có kiểm soát bộ nhớ.
5. **Cần truy vấn đặc thù không phù hợp với abstraction có sẵn.** Ví dụ kết hợp nhiều bước đọc, xử lý cursor hoặc chiến lược phân trang riêng.
6. **Cần đóng gói một năng lực persistence có thể tái sử dụng.** Ví dụ tìm kiếm nâng cao được nhiều service gọi với cùng semantics.

Đây là tín hiệu để đánh giá, không phải quy tắc rằng cứ có nhiều dòng code là phải tạo custom repository. Hãy chọn abstraction nhỏ nhất vẫn diễn đạt rõ ý định.

## 3. Phân biệt custom repository với service

Repository chịu trách nhiệm truy cập và lưu trữ dữ liệu. Service điều phối use case và quy tắc nghiệp vụ. Ranh giới này giúp mỗi tầng có một lý do thay đổi rõ ràng.

| Công việc | Nơi phù hợp |
| --- | --- |
| Tạo predicate Criteria và thực thi query | Repository fragment |
| Chạy native SQL đặc thù database | Repository fragment |
| Thực hiện bulk update có kiểm soát persistence context | Repository fragment, được gọi trong transaction phù hợp |
| Kết hợp dữ liệu từ nhiều repository | Service |
| Kiểm tra quyền truy cập hoặc chính sách nghiệp vụ | Service/domain layer |
| Gọi API thanh toán, email hoặc hệ thống ngoài | Service |
| Điều phối transaction qua nhiều bước nghiệp vụ | Service |
| Tạo query nhỏ theo thuộc tính entity | Derived method hoặc `@Query` |

Không đưa HTTP client, gửi email hoặc logic điều phối workflow vào repository implementation. Ngược lại, service không nên chứa một đoạn Criteria API dài nếu đó thực chất là một năng lực truy vấn có thể tái sử dụng.

### Repository default method

Default method trên repository interface có thể kết hợp các repository method đã có:

```java
public interface ProductRepository extends JpaRepository<Product, Long> {
    List<Product> findByCategory(String category);

    default boolean hasProductsInCategory(String category) {
        return !findByCategory(category).isEmpty();
    }
}
```

Cách này phù hợp với logic tiện ích nhỏ, được xây từ các method repository hiện có. Nếu cần truy cập EntityManager, xây Criteria query hoặc thực hiện thao tác persistence riêng, hãy dùng fragment.

## 4. Repository fragment là gì?

Repository fragment là một phần chức năng được ghép vào repository chính. Fragment gồm:

1. Interface mô tả các method tùy biến.
2. Class triển khai interface đó.
3. Repository chính kế thừa interface fragment cùng với `JpaRepository` hoặc repository interface khác.

Ví dụ cấu trúc:

```text
ProductSearchOperations.java
ProductSearchOperationsImpl.java
ProductRepository.java
```

Interface fragment:

```java
public interface ProductSearchOperations {
    Page<Product> search(ProductFilter filter, Pageable pageable);
}
```

Implementation:

```java
public class ProductSearchOperationsImpl implements ProductSearchOperations {
    // EntityManager and custom persistence logic
}
```

Repository chính:

```java
public interface ProductRepository extends
        JpaRepository<Product, Long>,
        ProductSearchOperations {
}
```

Caller dùng `ProductRepository` như một interface thống nhất. Spring Data ghép phần triển khai fragment vào repository proxy khi tạo repository bean.

### Quy ước tên implementation

Với fragment interface `ProductSearchOperations`, class triển khai theo mặc định là `ProductSearchOperationsImpl`. Hậu tố mặc định là `Impl`; có thể cấu hình postfix khác trong repository configuration.

Đặt implementation trong package mà Spring Data có thể dò tìm theo repository configuration, thông thường cùng package hoặc package con phù hợp. Tên class và package phải khớp quy ước discovery.

Fragment có thể được chia nhỏ theo năng lực, ví dụ `ProductSearchOperations`, `ProductBulkOperations` và `ProductLockingOperations`. Repository chính có thể kế thừa nhiều fragment nếu chúng có trách nhiệm độc lập.

## 5. Vì sao nên ưu tiên fragment thay vì một class Impl lớn?

Repository composition cho phép ghép nhiều fragment có trách nhiệm riêng:

```java
public interface ProductRepository extends
        JpaRepository<Product, Long>,
        ProductSearchOperations,
        ProductBulkOperations {
}
```

Các lợi ích:

- Mỗi fragment có interface nhỏ, mô tả một nhóm hành vi cụ thể.
- Có thể tái sử dụng fragment ở nhiều repository nếu kiểu dữ liệu và thiết kế phù hợp.
- Implementation được kiểm thử độc lập hơn.
- Không phải gom mọi truy vấn tùy biến vào một class dài.
- Dễ thay đổi một năng lực mà ít ảnh hưởng phần còn lại.

Spring Data vẫn hỗ trợ một số quy ước implementation cũ gắn trực tiếp với tên repository, nhưng fragment composition là cách mở rộng rõ ràng và linh hoạt hơn cho thiết kế mới. Tránh đặt toàn bộ custom behavior vào một `RepositoryImpl` duy nhất khi nhiều năng lực độc lập đang tăng lên.

## 6. Dùng EntityManager và Criteria API trong fragment

Fragment implementation có thể inject `EntityManager` bằng `@PersistenceContext`:

```java
public class ProductSearchOperationsImpl implements ProductSearchOperations {
    @PersistenceContext
    private EntityManager entityManager;
}
```

Từ EntityManager, implementation có thể:

- Tạo JPQL bằng `createQuery` hoặc native SQL bằng `createNativeQuery`.
- Tạo Criteria query với `CriteriaBuilder`.
- Gọi `persist`, `merge`, `remove`, `flush`, `clear` khi phù hợp.
- Thiết lập lock mode, query hint và giới hạn kết quả.
- Thực hiện bulk update/delete bằng `executeUpdate()`.

Với query động, Criteria API cho phép chỉ thêm predicate khi filter có giá trị:

```java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<Product> cq = cb.createQuery(Product.class);
Root<Product> root = cq.from(Product.class);
List<Predicate> predicates = new ArrayList<>();

if (filter.category() != null) {
    predicates.add(cb.equal(root.get("category"), filter.category()));
}
if (filter.minimumPrice() != null) {
    predicates.add(cb.greaterThanOrEqualTo(
            root.<BigDecimal>get("price"), filter.minimumPrice()));
}

cq.select(root).where(predicates.toArray(Predicate[]::new));
List<Product> result = entityManager.createQuery(cq).getResultList();
```

Đây là đoạn minh họa cơ chế. Ví dụ hoàn chỉnh ở phần sau bổ sung sort, phân trang và count query.

## 7. Quản lý transaction và persistence context

Custom fragment không có nghĩa là tự động có transaction cho mọi thao tác. Hãy xác định transaction boundary ở service hoặc cấu hình transaction phù hợp cho repository method.

Ví dụ service đọc:

```java
@Service
public class ProductSearchService {
    private final ProductRepository repository;

    public ProductSearchService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Page<Product> search(ProductFilter filter, Pageable pageable) {
        return repository.search(filter, pageable);
    }
}
```

Với thao tác ghi, dùng `@Transactional` read-write. Nếu fragment chạy nhiều câu lệnh cần tính nguyên tử, đặt chúng trong cùng transaction ở service hoặc method phù hợp.

### Bulk update/delete và entity đang managed

JPQL bulk update/delete tác động trực tiếp lên database, không cập nhật từng entity đã có trong persistence context. Sau bulk operation, các entity đang managed có thể giữ dữ liệu cũ.

Ví dụ:

```java
int updated = entityManager.createQuery(
        "update Product p set p.active = false where p.category = :category")
        .setParameter("category", "RETIRED")
        .executeUpdate();
entityManager.clear();
```

`clear()` detach tất cả entity đang được quản lý trong persistence context hiện tại. Chỉ dùng khi hiểu rõ tác động tới các thay đổi chưa flush; trong một số tình huống có thể cần flush trước, hoặc refresh các entity cụ thể thay vì clear toàn bộ.

### Read-only transaction

`@Transactional(readOnly = true)` phù hợp với truy vấn chỉ đọc và có thể cho provider cơ hội tối ưu. Đây không phải cơ chế bảo mật ngăn tuyệt đối mọi thao tác ghi. Không đặt bulk update/delete trong luồng được khai báo read-only.

## 8. Những lựa chọn thay thế trước khi viết custom implementation

Không phải mọi query phức tạp đều cần custom fragment. So sánh các lựa chọn:

| Nhu cầu | Lựa chọn nên xem xét trước | Khi nào cần fragment? |
| --- | --- | --- |
| Điều kiện cố định, dễ đọc | Derived query | Tên method trở nên quá dài hoặc query không thể biểu đạt. |
| JPQL cố định | `@Query` | Cần điều khiển EntityManager hoặc query được xây động. |
| Bộ lọc tùy chọn trên entity | `Specification` | Cần hành vi persistence chuyên biệt vượt ngoài predicate. |
| Tìm kiếm động theo thuộc tính | Query by Example | Cần OR/grouping/subquery/biểu thức phức tạp mà QBE không đáp ứng. |
| Querydsl predicate | Querydsl | Cần tích hợp sâu với EntityManager hoặc SQL đặc thù. |
| Kết hợp các method repository | Default method | Cần Criteria, native SQL hoặc thao tác dữ liệu tùy biến. |
| Quy trình nghiệp vụ nhiều bước | Service | Không nên chuyển orchestration thành custom repository. |

Chọn abstraction dựa trên độ phức tạp, khả năng tái sử dụng, yêu cầu hiệu năng và mức độ kiểm soát cần thiết. Đừng tạo fragment chỉ để bọc một dòng `findById`.

## 9. Custom base repository khi muốn thay đổi hành vi dùng chung

Repository fragment phù hợp với một năng lực cụ thể. Nếu muốn thay đổi hành vi nền tảng cho nhiều repository, có thể tạo custom repository base class và cấu hình `repositoryBaseClass`.

Ví dụ use case có thể là:

- Cung cấp method audit chung cho mọi repository.
- Áp dụng một quy tắc truy vấn nền tảng cho một họ repository.
- Thay đổi cách triển khai một số thao tác CRUD mặc định.

Đây là lựa chọn có phạm vi ảnh hưởng lớn hơn fragment. Chỉ dùng khi nhiều repository thực sự cần cùng hành vi và nhóm phát triển có thể kiểm soát tác động. Với một năng lực riêng như tìm kiếm sản phẩm nâng cao, fragment thường phù hợp hơn.

## 10. Kiểm thử custom repository behavior

Nên kiểm thử cả logic Criteria lẫn cách Spring Data ghép fragment:

1. **Integration test với `@DataJpaTest`:** xác nhận repository proxy tìm thấy fragment implementation và query chạy với database.
2. **Test điều kiện rỗng:** không có filter tùy chọn thì query trả tập dữ liệu dự kiến.
3. **Test kết hợp filter:** xác minh AND/OR, khoảng giá, null và điều kiện biên.
4. **Test sort:** chỉ property được whitelist mới được chấp nhận; thứ tự có tie-breaker ổn định.
5. **Test pagination:** nội dung trang, offset, page size và tổng count phải khớp.
6. **Test transaction:** xác nhận read/write transaction và trạng thái persistence context sau bulk operation.
7. **Test database mục tiêu:** native SQL, collation, JSON, CTE và execution plan có thể khác H2.

Đối với custom query dùng nhiều join to-many, kiểm tra count query có đếm distinct root đúng không. Nếu query có thể nhân bản hàng root, `count(root)` đơn giản có thể trả tổng lớn hơn số entity duy nhất; cân nhắc `countDistinct(root)` hoặc viết count query tương ứng.

## 11. Ví dụ chạy được với Java 17+, Spring Boot và H2

Ví dụ này bổ sung một custom repository fragment để tìm sản phẩm bằng nhiều filter tùy chọn. Fragment dùng Criteria API để xây predicate, whitelist thuộc tính sort, tự thêm `id` làm tie-breaker và tạo `Page` bằng content query cùng count query.

### Cấu trúc dự án

```text
custom-repository-fragment/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/customrepo/
        │   ├── CustomRepositoryApplication.java
        │   ├── Product.java
        │   ├── ProductFilter.java
        │   ├── ProductSearchOperations.java
        │   ├── ProductSearchOperationsImpl.java
        │   ├── ProductRepository.java
        │   └── ProductSearchService.java
        └── resources/
            └── application.properties
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>custom-repository-fragment</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:customrepo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

### `Product.java`

```java
package com.example.customrepo;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false, length = 40)
    private String category;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean active;

    protected Product() {
    }

    public Product(String name, String category, BigDecimal price, boolean active) {
        this.name = name;
        this.category = category;
        this.price = price;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCategory() {
        return category;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public boolean isActive() {
        return active;
    }
}
```

### `ProductFilter.java`

```java
package com.example.customrepo;

import java.math.BigDecimal;

public record ProductFilter(
        String nameContains,
        String category,
        BigDecimal minimumPrice,
        Boolean active
) {
}
```

### `ProductSearchOperations.java`

```java
package com.example.customrepo;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface ProductSearchOperations {
    Page<Product> search(ProductFilter filter, Pageable pageable);
}
```

### `ProductSearchOperationsImpl.java`

```java
package com.example.customrepo;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.TypedQuery;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Order;
import jakarta.persistence.criteria.Predicate;
import jakarta.persistence.criteria.Root;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

public class ProductSearchOperationsImpl implements ProductSearchOperations {
    private static final Set<String> ALLOWED_SORTS =
            Set.of("id", "name", "category", "price");

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    public Page<Product> search(ProductFilter filter, Pageable pageable) {
        CriteriaBuilder cb = entityManager.getCriteriaBuilder();
        CriteriaQuery<Product> selectQuery = cb.createQuery(Product.class);
        Root<Product> root = selectQuery.from(Product.class);

        List<Predicate> predicates = buildPredicates(root, cb, filter);
        selectQuery.select(root)
                .where(predicates.toArray(Predicate[]::new))
                .orderBy(buildOrders(root, cb, pageable.getSort()));

        TypedQuery<Product> query = entityManager.createQuery(selectQuery);
        if (pageable.isPaged()) {
            query.setFirstResult(Math.toIntExact(pageable.getOffset()));
            query.setMaxResults(pageable.getPageSize());
        }
        List<Product> content = query.getResultList();

        long total = countMatching(filter);
        return new PageImpl<>(content, pageable, total);
    }

    private long countMatching(ProductFilter filter) {
        CriteriaBuilder cb = entityManager.getCriteriaBuilder();
        CriteriaQuery<Long> countQuery = cb.createQuery(Long.class);
        Root<Product> root = countQuery.from(Product.class);

        List<Predicate> predicates = buildPredicates(root, cb, filter);
        countQuery.select(cb.count(root))
                .where(predicates.toArray(Predicate[]::new));

        return entityManager.createQuery(countQuery).getSingleResult();
    }

    private List<Predicate> buildPredicates(
            Root<Product> root, CriteriaBuilder cb, ProductFilter filter) {
        List<Predicate> predicates = new ArrayList<>();

        if (filter.nameContains() != null && !filter.nameContains().isBlank()) {
            String pattern = "%" + filter.nameContains().trim()
                    .toLowerCase(Locale.ROOT) + "%";
            predicates.add(cb.like(cb.lower(root.<String>get("name")), pattern));
        }

        if (filter.category() != null && !filter.category().isBlank()) {
            predicates.add(cb.equal(root.<String>get("category"), filter.category()));
        }

        if (filter.minimumPrice() != null) {
            predicates.add(cb.greaterThanOrEqualTo(
                    root.<BigDecimal>get("price"), filter.minimumPrice()));
        }

        if (filter.active() != null) {
            predicates.add(cb.equal(root.<Boolean>get("active"), filter.active()));
        }

        return predicates;
    }

    private List<Order> buildOrders(
            Root<Product> root, CriteriaBuilder cb, Sort requestedSort) {
        Sort effectiveSort = requestedSort.isSorted()
                ? requestedSort
                : Sort.by(Sort.Order.asc("id"));

        List<Order> orders = new ArrayList<>();
        for (Sort.Order order : effectiveSort) {
            String property = order.getProperty();
            if (!ALLOWED_SORTS.contains(property)) {
                throw new IllegalArgumentException(
                        "Unsupported sort property: " + property);
            }

            if (order.isIgnoreCase()) {
                throw new IllegalArgumentException(
                        "Ignore-case sorting is not configured for: " + property);
            }

            orders.add(order.isAscending()
                    ? cb.asc(root.get(property))
                    : cb.desc(root.get(property)));
        }

        if (effectiveSort.getOrderFor("id") == null) {
            orders.add(cb.asc(root.get("id")));
        }
        return orders;
    }
}
```

Class `ProductSearchOperationsImpl` triển khai fragment `ProductSearchOperations`; hậu tố `Impl` giúp Spring Data phát hiện implementation theo quy ước. `buildPredicates` chỉ thêm điều kiện khi filter có giá trị. `buildOrders` kiểm tra whitelist để client không thể yêu cầu sort theo property tùy ý, rồi thêm `id` làm tie-breaker nếu chưa có.

Count query dùng cùng predicate với content query. Ví dụ không có join to-many nên `count(root)` phù hợp; nếu thêm join làm nhân bản root, cần cân nhắc `countDistinct(root)`.

### `ProductRepository.java`

```java
package com.example.customrepo;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends
        JpaRepository<Product, Long>,
        ProductSearchOperations {
}
```

### `ProductSearchService.java`

```java
package com.example.customrepo;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductSearchService {
    private final ProductRepository repository;

    public ProductSearchService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Page<Product> search(ProductFilter filter, Pageable pageable) {
        return repository.search(filter, pageable);
    }
}
```

Service đặt transaction boundary cho use case đọc. Fragment tập trung vào xây dựng và thực thi query.

### `CustomRepositoryApplication.java`

```java
package com.example.customrepo;

import java.math.BigDecimal;
import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

@SpringBootApplication
public class CustomRepositoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(CustomRepositoryApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(ProductRepository repository, ProductSearchService service) {
        return args -> {
            repository.saveAll(List.of(
                    new Product("Spring Data JPA", "BOOK",
                            new BigDecimal("150.00"), true),
                    new Product("Spring Boot Course", "COURSE",
                            new BigDecimal("250.00"), true),
                    new Product("Spring Security", "BOOK",
                            new BigDecimal("90.00"), true),
                    new Product("Legacy ORM", "TOOL",
                            new BigDecimal("300.00"), false),
                    new Product("Hibernate Tips", "BOOK",
                            new BigDecimal("180.00"), true)
            ));
            repository.flush();

            ProductFilter filter = new ProductFilter(
                    "spring", null, new BigDecimal("100.00"), true);
            Page<Product> page = service.search(
                    filter,
                    PageRequest.of(0, 10,
                            Sort.by(Sort.Order.desc("price"),
                                    Sort.Order.asc("name")))
            );

            page.getContent().forEach(product ->
                    System.out.println(product.getName() + " | " + product.getPrice()));
            System.out.println("Total: " + page.getTotalElements());
        };
    }
}
```

### Chạy chương trình

```bash
mvn spring-boot:run
```

Stdout:

```text
Spring Boot Course | 250.00
Spring Data JPA | 150.00
Total: 2
```

Kết quả được sắp xếp theo `price DESC`, `name ASC`, sau đó `id ASC` do fragment tự thêm tie-breaker. `Spring Security` bị loại vì giá thấp hơn 100; `Legacy ORM` bị loại vì không active; `Hibernate Tips` bị loại vì tên không chứa spring.

## 12. Những lỗi thường gặp

1. **Tạo custom implementation cho query đơn giản:** ưu tiên derived query hoặc `@Query` nếu đã đủ diễn đạt.
2. **Đặt sai tên fragment implementation:** interface `ProductSearchOperations` cần class `ProductSearchOperationsImpl` theo postfix mặc định.
3. **Đặt implementation ngoài vùng dò tìm:** giữ fragment implementation trong package được repository configuration quét.
4. **Gom mọi hành vi vào một class Impl:** tách fragment theo năng lực và trách nhiệm.
5. **Đưa nghiệp vụ hoặc gọi API ngoài vào repository:** chuyển orchestration sang service.
6. **Không có transaction boundary rõ ràng:** xác định transaction ở service hoặc method phù hợp.
7. **Bulk DML nhưng vẫn dùng entity cũ trong persistence context:** flush/clear/refresh theo tình huống.
8. **Dùng sort property từ client mà không whitelist:** kiểm tra property được phép trước khi tạo Criteria order.
9. **Count query không tương ứng với content query:** dùng cùng filter; cân nhắc distinct khi join to-many.
10. **Dùng H2 để kết luận native SQL production:** kiểm thử trên database mục tiêu.
11. **Không kiểm tra giới hạn offset:** JPA `setFirstResult` nhận int; offset quá lớn có thể vượt giới hạn hoặc rất tốn kém.
12. **Custom fragment chỉ bọc một method CRUD có sẵn:** tránh lớp abstraction không mang lại năng lực mới.

## 13. Checklist trước khi bổ sung custom behavior

- [ ] Derived query hoặc `@Query` có thể diễn đạt yêu cầu một cách rõ ràng không?
- [ ] `Specification`, Query by Example hoặc Querydsl có đáp ứng bộ lọc động không?
- [ ] Hành vi mới thực sự là truy cập dữ liệu, không phải orchestration nghiệp vụ?
- [ ] Có thể mô tả năng lực bằng một fragment interface nhỏ không?
- [ ] Implementation dùng đúng postfix và package discovery?
- [ ] Transaction boundary được đặt rõ ràng?
- [ ] Query có sort, paging, count và null semantics đúng không?
- [ ] Sort input đã được whitelist và parameter được bind an toàn?
- [ ] Bulk operation có xử lý persistence context sau khi chạy?
- [ ] Integration test xác nhận Spring Data ghép fragment và database trả kết quả đúng?

## 14. Nguyên tắc thực hành

- Dùng derived query hoặc `@Query` cho truy vấn đơn giản, ổn định.
- Dùng Specification/Querydsl cho predicate động khi abstraction đó đã đủ.
- Bổ sung custom repository fragment khi cần EntityManager, Criteria, native SQL, bulk operation hoặc chiến lược persistence riêng.
- Chia fragment theo năng lực thay vì tạo một implementation khổng lồ.
- Đặt orchestration và quy tắc nghiệp vụ ở service/domain layer.
- Đặt transaction boundary rõ ràng và hiểu tác động của bulk DML lên persistence context.
- Whitelist sort property, bind parameter và kiểm tra execution plan.
- Chỉ tạo custom base repository khi nhiều repository thực sự cần cùng hành vi nền tảng.
- Kiểm thử tích hợp fragment, paging/count và database mục tiêu.

Điểm cốt lõi: **Chỉ bổ sung hành vi tùy biến khi query method, `@Query` hoặc Specification không còn diễn đạt tốt nhu cầu persistence. Dùng repository fragment cho năng lực truy cập dữ liệu chuyên biệt, giữ orchestration ở service và chia implementation thành các phần nhỏ có trách nhiệm rõ ràng.**