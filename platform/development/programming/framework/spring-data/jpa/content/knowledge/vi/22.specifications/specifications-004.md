# Tạo điều kiện so sánh, chuỗi, khoảng, null và tập hợp bằng Specification

## 1. Mục tiêu

`Specification<T>` của Spring Data JPA cho phép xây dựng điều kiện truy vấn động bằng JPA Criteria API. Thay vì tạo một method repository cho mọi tổ hợp bộ lọc, ta có thể viết các điều kiện nhỏ, tái sử dụng chúng và kết hợp bằng `and`, `or`, `not`.

Bài học tập trung vào năm nhóm predicate thường gặp:
- **So sánh:** bằng, khác, lớn hơn, lớn hơn hoặc bằng, nhỏ hơn, nhỏ hơn hoặc bằng.
- **Chuỗi:** bằng không phân biệt hoa thường, chứa chuỗi, bắt đầu bằng chuỗi và xử lý ký tự đại diện.
- **Khoảng:** giá trị nằm trong khoảng số hoặc thời gian.
- **Null:** tìm thuộc tính có giá trị null hoặc khác null.
- **Tập hợp:** điều kiện `IN` và `NOT IN`, gồm cả chính sách cho collection rỗng và phần tử null.

Sau bài học, bạn có thể bật khả năng Specification cho Repository, tạo các predicate có thể tái sử dụng, ghép điều kiện động trong Service, phân trang kết quả và kiểm thử hành vi trên database.

## 2. Specification và JPA Criteria API

`Specification<T>` là abstraction của Spring Data JPA để biểu diễn một điều kiện lọc cho Entity kiểu `T`. Nó dựa trên Criteria API của JPA, không yêu cầu nối chuỗi JPQL hoặc SQL.

Một Specification triển khai phương thức:

```java
Predicate toPredicate(
        Root<T> root,
        CriteriaQuery<?> query,
        CriteriaBuilder criteriaBuilder);
```

Ba đối tượng có vai trò:

| Đối tượng | Vai trò |
| --- | --- |
| `Root<T>` | Đại diện cho Entity đang được truy vấn; dùng để lấy thuộc tính bằng `root.get("property")`. |
| `CriteriaQuery<?>` | Đại diện cho cấu trúc truy vấn; có thể dùng để điều chỉnh distinct hoặc subquery khi cần. |
| `CriteriaBuilder` | Tạo predicate như `equal`, `greaterThan`, `like`, `between`, `isNull`, `in`, `and`, `or`. |

Ví dụ đơn giản:

```java
Specification<Product> expensive = (root, query, cb) ->
        cb.greaterThan(root.get("price"), new BigDecimal("100"));
```

Specification trên mô tả điều kiện `price > 100`. Nó chưa chạy truy vấn; Repository thực thi nó khi gọi `findAll(specification)`.

## 3. Bật Specification cho Repository

Repository cần kế thừa `JpaSpecificationExecutor<T>` bên cạnh `JpaRepository<T, ID>`.

```java
public interface ProductRepository
        extends JpaRepository<Product, Long>, JpaSpecificationExecutor<Product> {
}
```

`JpaSpecificationExecutor` cung cấp các thao tác thường dùng:

| Phương thức | Công dụng |
| --- | --- |
| `findAll(spec)` | Lấy tất cả Entity khớp điều kiện. |
| `findAll(spec, sort)` | Lấy kết quả theo điều kiện và thứ tự sắp xếp. |
| `findAll(spec, pageable)` | Lấy một trang theo điều kiện. |
| `count(spec)` | Đếm số Entity khớp điều kiện. |
| `exists(spec)` | Kiểm tra có Entity khớp điều kiện hay không. |

Specification có thể tái sử dụng ở nhiều method mà không cần khai báo lại câu query.

## 4. Mô hình Entity dùng trong ví dụ

Ví dụ dùng Java 17+, Maven, Spring Boot 3.5.x, Spring Data JPA và H2. Entity `Product` có tên, giá, trạng thái, thời điểm tạo và mô tả tùy chọn.

### 4.1. Enum ProductStatus

`src/main/java/com/example/catalog/ProductStatus.java`:

```java
package com.example.catalog;

public enum ProductStatus {
    DRAFT,
    ACTIVE,
    DISCONTINUED
}
```

### 4.2. Entity Product

`src/main/java/com/example/catalog/Product.java`:

```java
package com.example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.LocalDateTime;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 160)
    private String name;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private ProductStatus status;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Column(length = 500)
    private String description;

    protected Product() {
        // JPA cần constructor không tham số.
    }

    public Product(
            String name,
            BigDecimal price,
            ProductStatus status,
            LocalDateTime createdAt,
            String description) {
        if (name == null || name.isBlank() || name.length() > 160) {
            throw new IllegalArgumentException("Product name is required");
        }
        if (price == null || price.signum() < 0) {
            throw new IllegalArgumentException("Price cannot be negative");
        }
        if (status == null || createdAt == null) {
            throw new IllegalArgumentException("Status and createdAt are required");
        }
        if (description != null && description.length() > 500) {
            throw new IllegalArgumentException("Description is too long");
        }
        this.name = name.trim();
        this.price = price;
        this.status = status;
        this.createdAt = createdAt;
        this.description = description;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
    public ProductStatus getStatus() { return status; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public String getDescription() { return description; }
}
```

`description` được phép null để minh họa `IS NULL` và `IS NOT NULL`. `status` dùng `EnumType.STRING` để lưu tên enum, còn `createdAt` dùng `LocalDateTime` vì ví dụ coi đây là ngày giờ địa phương của hệ thống.

## 5. Predicate so sánh

`CriteriaBuilder` có các phương thức so sánh cho kiểu dữ liệu phù hợp. Với số hoặc kiểu triển khai `Comparable`, có thể dùng:

| Ý nghĩa | Criteria API |
| --- | --- |
| Bằng | `cb.equal(path, value)` |
| Khác | `cb.notEqual(path, value)` |
| Lớn hơn | `cb.greaterThan(path, value)` |
| Lớn hơn hoặc bằng | `cb.greaterThanOrEqualTo(path, value)` |
| Nhỏ hơn | `cb.lessThan(path, value)` |
| Nhỏ hơn hoặc bằng | `cb.lessThanOrEqualTo(path, value)` |

Ví dụ Specification:

```java
public static Specification<Product> priceEqualTo(BigDecimal value) {
    return (root, query, cb) -> cb.equal(root.<BigDecimal>get("price"), value);
}

public static Specification<Product> priceGreaterThan(BigDecimal value) {
    return (root, query, cb) -> cb.greaterThan(root.<BigDecimal>get("price"), value);
}

public static Specification<Product> priceAtLeast(BigDecimal value) {
    return (root, query, cb) ->
            cb.greaterThanOrEqualTo(root.<BigDecimal>get("price"), value);
}

public static Specification<Product> priceAtMost(BigDecimal value) {
    return (root, query, cb) ->
            cb.lessThanOrEqualTo(root.<BigDecimal>get("price"), value);
}
```

Trong code thực tế, nên đặt các phương thức này trong một lớp tiện ích như `ProductSpecifications`. Không truyền `null` vào các phương thức so sánh; nếu bộ lọc không được cung cấp, Service nên bỏ qua predicate tương ứng.

## 6. Predicate chuỗi

### 6.1. Bằng không phân biệt hoa thường

Để so sánh chuỗi không phân biệt hoa thường, chuyển cả thuộc tính và giá trị tìm kiếm về cùng dạng:

```java
public static Specification<Product> nameEqualsIgnoreCase(String value) {
    String normalized = value.trim().toLowerCase(Locale.ROOT);
    return (root, query, cb) ->
            cb.equal(cb.lower(root.get("name")), normalized);
}
```

Ví dụ `nameEqualsIgnoreCase("KEYBOARD")` khớp với tên `Keyboard`. `Locale.ROOT` tránh phụ thuộc locale mặc định của máy chạy ứng dụng.

### 6.2. Chứa chuỗi và bắt đầu bằng chuỗi

`LIKE` hỗ trợ ký tự đại diện:
- `%` khớp với không hoặc nhiều ký tự.
- `_` khớp với đúng một ký tự.

Ví dụ điều kiện chứa chuỗi:

```java
public static Specification<Product> nameContainsIgnoreCase(String value) {
    String pattern = "%" + escapeLike(value.trim().toLowerCase(Locale.ROOT)) + "%";
    return (root, query, cb) ->
            cb.like(cb.lower(root.get("name")), pattern, '\\');
}

public static Specification<Product> nameStartsWithIgnoreCase(String value) {
    String pattern = escapeLike(value.trim().toLowerCase(Locale.ROOT)) + "%";
    return (root, query, cb) ->
            cb.like(cb.lower(root.get("name")), pattern, '\\');
}

private static String escapeLike(String value) {
    return value.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_");
}
```

Escape ký tự `%` và `_` giúp chuỗi do người dùng nhập được hiểu là văn bản cần tìm, không vô tình trở thành wildcard. Ký tự escape được truyền rõ vào overload `CriteriaBuilder.like`.

Ví dụ:

- Tìm `key` khớp `Mechanical Keyboard` khi dùng contains.
- Tìm `wire` khớp `Wireless Mouse` khi dùng starts-with.
- Tìm `100%` chỉ khớp chuỗi có ký tự `%` thật, thay vì coi `%` là wildcard.

Với truy vấn không phân biệt hoa thường, database có thể cần index phù hợp (ví dụ functional index trên `lower(name)`) để tối ưu. Predicate `lower(column) like '%value%'` thường không tận dụng được B-tree index thông thường theo cách đơn giản; hãy đo execution plan nếu bảng lớn.

## 7. Predicate khoảng

### 7.1. Khoảng số

`between` bao gồm cả hai đầu mút. Ví dụ giá từ 100 đến 500:

```java
public static Specification<Product> priceBetween(
        BigDecimal minimum, BigDecimal maximum) {
    return (root, query, cb) -> cb.between(
            root.<BigDecimal>get("price"), minimum, maximum);
}
```

Điều kiện tương đương `price >= minimum AND price <= maximum`. Kiểm tra `minimum <= maximum` trước khi tạo truy vấn để tránh điều kiện đầu vào vô nghĩa.

### 7.2. Khoảng thời gian

Với `LocalDateTime`, có thể dùng `between` nếu nghiệp vụ yêu cầu bao gồm cả thời điểm bắt đầu và kết thúc:

```java
public static Specification<Product> createdAtBetweenInclusive(
        LocalDateTime from, LocalDateTime to) {
    return (root, query, cb) -> cb.between(
            root.<LocalDateTime>get("createdAt"), from, to);
}
```

Đối với timestamp, nhiều hệ thống ưu tiên khoảng nửa mở `[from, to)`: bao gồm đầu mút và loại trừ cuối mút. Cách này tránh phải tạo thời điểm cuối ngày phụ thuộc precision của database:

```java
public static Specification<Product> createdAtOnOrAfter(LocalDateTime from) {
    return (root, query, cb) ->
            cb.greaterThanOrEqualTo(root.<LocalDateTime>get("createdAt"), from);
}

public static Specification<Product> createdAtBefore(LocalDateTime toExclusive) {
    return (root, query, cb) ->
            cb.lessThan(root.<LocalDateTime>get("createdAt"), toExclusive);
}
```

Kết hợp hai Specification này bằng `and()` sẽ tạo điều kiện `createdAt >= from AND createdAt < toExclusive`. Với các khoảng liên tiếp, bản ghi đúng tại ranh giới không bị trùng ở cả hai khoảng.

## 8. Predicate null

Không so sánh null bằng `equal(path, null)`. Trong SQL, `column = NULL` không trả TRUE; phải dùng `IS NULL` hoặc `IS NOT NULL`.

```java
public static Specification<Product> descriptionIsNull() {
    return (root, query, cb) -> cb.isNull(root.get("description"));
}

public static Specification<Product> descriptionIsNotNull() {
    return (root, query, cb) -> cb.isNotNull(root.get("description"));
}
```

Có thể kết hợp điều kiện null với các điều kiện khác:

```java
Specification<Product> missingDescription =
        ProductSpecifications.descriptionIsNull()
                .and(ProductSpecifications.priceAtLeast(new BigDecimal("50")));
```

Điều này tìm sản phẩm chưa có mô tả và có giá ít nhất 50.

Phân biệt rõ:
- Không truyền bộ lọc mô tả: không thêm predicate null.
- Muốn tìm mô tả null: thêm `descriptionIsNull()`.
- Muốn tìm mô tả khác null: thêm `descriptionIsNotNull()`.

Đừng dùng một tham số null với nhiều ý nghĩa ngầm. Hãy để Service quyết định có thêm predicate hay không.

## 9. Predicate tập hợp IN và NOT IN

Criteria API hỗ trợ `in()` để kiểm tra một giá trị có thuộc tập hợp hay không.

```java
public static Specification<Product> statusIn(Collection<ProductStatus> statuses) {
    if (statuses == null) {
        throw new IllegalArgumentException("statuses must not be null");
    }
    if (statuses.stream().anyMatch(Objects::isNull)) {
        throw new IllegalArgumentException("statuses must not contain null");
    }
    if (statuses.isEmpty()) {
        return (root, query, cb) -> cb.disjunction();
    }
    return (root, query, cb) -> root.get("status").in(statuses);
}

public static Specification<Product> statusNotIn(Collection<ProductStatus> statuses) {
    if (statuses == null) {
        throw new IllegalArgumentException("statuses must not be null");
    }
    if (statuses.stream().anyMatch(Objects::isNull)) {
        throw new IllegalArgumentException("statuses must not contain null");
    }
    if (statuses.isEmpty()) {
        return (root, query, cb) -> cb.conjunction();
    }
    return (root, query, cb) -> root.get("status").in(statuses).not();
}
```

Ví dụ gọi:

```java
Specification<Product> activeOrDraft =
        ProductSpecifications.statusIn(
                List.of(ProductStatus.ACTIVE, ProductStatus.DRAFT));
```

### 9.1. Chính sách cho collection rỗng

Ví dụ trên chọn hai semantics rõ ràng:

| Điều kiện | Collection rỗng | Ý nghĩa |
| --- | --- | --- |
| `statusIn(empty)` | `cb.disjunction()` | Predicate luôn FALSE, không trả sản phẩm nào. |
| `statusNotIn(empty)` | `cb.conjunction()` | Predicate luôn TRUE, không giới hạn theo trạng thái. |

Đây là chính sách được chọn cho ví dụ; ứng dụng khác có thể quy định khác. Điều quan trọng là quyết định trước khi gọi Repository, không phụ thuộc cách provider/database tạo SQL `IN ()`.

### 9.2. Vì sao từ chối phần tử null?

SQL dùng logic ba giá trị TRUE/FALSE/UNKNOWN. Với `NOT IN`, chỉ một phần tử null trong tập hợp cũng có thể khiến phép so sánh trở thành UNKNOWN và loại những dòng mà người viết tưởng sẽ được giữ lại.

Trong ví dụ, `status` là NOT NULL ở database và helper từ chối phần tử null. Nếu thuộc tính có thể null, cần định nghĩa riêng việc có muốn giữ những dòng null khi dùng `NOT IN` hay không; không giả định `NOT IN` tự bao gồm chúng.

## 10. Tổ chức lớp ProductSpecifications

Các phương thức ở những phần trước được gom vào một lớp để Repository và Service có thể tái sử dụng.

`src/main/java/com/example/catalog/ProductSpecifications.java`:

```java
package com.example.catalog;

import jakarta.persistence.criteria.CriteriaBuilder;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Collection;
import java.util.Locale;
import java.util.Objects;
import org.springframework.data.jpa.domain.Specification;

public final class ProductSpecifications {
    private ProductSpecifications() {
    }

    public static Specification<Product> nameEqualsIgnoreCase(String value) {
        String normalized = value.trim().toLowerCase(Locale.ROOT);
        return (root, query, cb) ->
                cb.equal(cb.lower(root.get("name")), normalized);
    }

    public static Specification<Product> nameContainsIgnoreCase(String value) {
        String pattern = "%" + escapeLike(value.trim().toLowerCase(Locale.ROOT)) + "%";
        return (root, query, cb) ->
                cb.like(cb.lower(root.get("name")), pattern, '\\');
    }

    public static Specification<Product> nameStartsWithIgnoreCase(String value) {
        String pattern = escapeLike(value.trim().toLowerCase(Locale.ROOT)) + "%";
        return (root, query, cb) ->
                cb.like(cb.lower(root.get("name")), pattern, '\\');
    }

    public static Specification<Product> priceAtLeast(BigDecimal minimum) {
        return (root, query, cb) ->
                cb.greaterThanOrEqualTo(root.<BigDecimal>get("price"), minimum);
    }

    public static Specification<Product> priceAtMost(BigDecimal maximum) {
        return (root, query, cb) ->
                cb.lessThanOrEqualTo(root.<BigDecimal>get("price"), maximum);
    }

    public static Specification<Product> priceBetween(
            BigDecimal minimum, BigDecimal maximum) {
        return (root, query, cb) -> cb.between(
                root.<BigDecimal>get("price"), minimum, maximum);
    }

    public static Specification<Product> createdAtOnOrAfter(LocalDateTime from) {
        return (root, query, cb) ->
                cb.greaterThanOrEqualTo(root.<LocalDateTime>get("createdAt"), from);
    }

    public static Specification<Product> createdAtBefore(LocalDateTime toExclusive) {
        return (root, query, cb) ->
                cb.lessThan(root.<LocalDateTime>get("createdAt"), toExclusive);
    }

    public static Specification<Product> descriptionIsNull() {
        return (root, query, cb) -> cb.isNull(root.get("description"));
    }

    public static Specification<Product> descriptionIsNotNull() {
        return (root, query, cb) -> cb.isNotNull(root.get("description"));
    }

    public static Specification<Product> statusIn(Collection<ProductStatus> statuses) {
        Objects.requireNonNull(statuses, "statuses must not be null");
        if (statuses.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException("statuses must not contain null");
        }
        if (statuses.isEmpty()) {
            return (root, query, cb) -> cb.disjunction();
        }
        return (root, query, cb) -> root.get("status").in(statuses);
    }

    public static Specification<Product> statusNotIn(Collection<ProductStatus> statuses) {
        Objects.requireNonNull(statuses, "statuses must not be null");
        if (statuses.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException("statuses must not contain null");
        }
        if (statuses.isEmpty()) {
            return (root, query, cb) -> cb.conjunction();
        }
        return (root, query, cb) -> root.get("status").in(statuses).not();
    }

    private static String escapeLike(String value) {
        return value.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_");
    }
}
```

Trong ví dụ lớp tiện ích trên, các method so sánh nhận giá trị khác null. Service chỉ gọi chúng khi bộ lọc tương ứng được cung cấp. `statusIn` và `statusNotIn` chủ động định nghĩa semantics của collection rỗng và từ chối phần tử null.

## 11. Kết hợp Specification bằng AND, OR và NOT

Mỗi Specification có thể kết hợp với Specification khác:

- `and(other)`: cả hai điều kiện phải đúng.
- `or(other)`: ít nhất một điều kiện đúng.
- `not(spec)`: phủ định điều kiện.

Ví dụ tìm sản phẩm có tên chứa `keyboard` hoặc `mouse`, đồng thời có giá tối đa 200:

```java
Specification<Product> keyboardOrMouse =
        ProductSpecifications.nameContainsIgnoreCase("keyboard")
                .or(ProductSpecifications.nameContainsIgnoreCase("mouse"));

Specification<Product> affordable =
        ProductSpecifications.priceAtMost(new BigDecimal("200"));

Specification<Product> finalSpec = keyboardOrMouse.and(affordable);
```

Điều kiện tương đương:

```text
(name contains 'keyboard' OR name contains 'mouse')
AND price <= 200
```

Phép `not` có thể dùng để phủ định một Specification:

```java
Specification<Product> notDraft = Specification.not(
        (root, query, cb) -> cb.equal(root.get("status"), ProductStatus.DRAFT));
```

Giữ các nhóm `and`/`or` có ngoặc logic rõ ràng. Nếu ghép nhiều điều kiện bằng chuỗi, rất dễ vô tình thay đổi thứ tự ưu tiên giữa AND và OR.

## 12. Xây dựng truy vấn động trong Service

Ví dụ criteria object chứa những bộ lọc mà màn hình tìm kiếm có thể gửi:

`src/main/java/com/example/catalog/ProductSearchCriteria.java`:

```java
package com.example.catalog;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

public record ProductSearchCriteria(
        String name,
        BigDecimal minimumPrice,
        BigDecimal maximumPrice,
        LocalDateTime createdFrom,
        LocalDateTime createdBefore,
        List<ProductStatus> statuses,
        Boolean descriptionMissing) {
}
```

`null` trong criteria có nghĩa là bỏ qua filter tương ứng. `statuses` rỗng có nghĩa là không có trạng thái nào được chấp nhận, do helper `statusIn(empty)` tạo predicate FALSE. `descriptionMissing` nhận `true` để tìm mô tả null, `false` để tìm mô tả khác null và `null` để bỏ qua điều kiện.

`src/main/java/com/example/catalog/ProductSearchService.java`:

```java
package com.example.catalog;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class ProductSearchService {
    private final ProductRepository repository;

    public ProductSearchService(ProductRepository repository) {
        this.repository = repository;
    }

    public Page<Product> search(ProductSearchCriteria criteria, Pageable pageable) {
        Objects.requireNonNull(criteria, "criteria is required");
        Objects.requireNonNull(pageable, "pageable is required");

        if (criteria.minimumPrice() != null
                && criteria.maximumPrice() != null
                && criteria.minimumPrice().compareTo(criteria.maximumPrice()) > 0) {
            throw new IllegalArgumentException("minimumPrice must not exceed maximumPrice");
        }
        if (criteria.createdFrom() != null
                && criteria.createdBefore() != null
                && !criteria.createdFrom().isBefore(criteria.createdBefore())) {
            throw new IllegalArgumentException("createdFrom must be before createdBefore");
        }
        if (criteria.statuses() != null
                && criteria.statuses().stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException("statuses must not contain null");
        }

        List<Specification<Product>> filters = new ArrayList<>();

        if (criteria.name() != null && !criteria.name().isBlank()) {
            filters.add(ProductSpecifications.nameContainsIgnoreCase(criteria.name()));
        }
        if (criteria.minimumPrice() != null) {
            filters.add(ProductSpecifications.priceAtLeast(criteria.minimumPrice()));
        }
        if (criteria.maximumPrice() != null) {
            filters.add(ProductSpecifications.priceAtMost(criteria.maximumPrice()));
        }
        if (criteria.createdFrom() != null) {
            filters.add(ProductSpecifications.createdAtOnOrAfter(criteria.createdFrom()));
        }
        if (criteria.createdBefore() != null) {
            filters.add(ProductSpecifications.createdAtBefore(criteria.createdBefore()));
        }
        if (criteria.statuses() != null) {
            filters.add(ProductSpecifications.statusIn(criteria.statuses()));
        }
        if (criteria.descriptionMissing() != null) {
            filters.add(criteria.descriptionMissing()
                    ? ProductSpecifications.descriptionIsNull()
                    : ProductSpecifications.descriptionIsNotNull());
        }

        Specification<Product> specification =
                (root, query, cb) -> cb.conjunction();
        for (Specification<Product> filter : filters) {
            specification = specification.and(filter);
        }

        return repository.findAll(specification, pageable);
    }
}
```

Service kiểm tra khoảng đầu vào trước khi truy vấn. Sau đó chỉ thêm các predicate có filter tương ứng. `Specification` ban đầu là conjunction TRUE; khi không có filter, truy vấn trả về tập sản phẩm theo Pageable. Khi `statuses` là danh sách rỗng, predicate FALSE khiến kết quả rỗng theo chính sách đã chọn.

## 13. Repository

`src/main/java/com/example/catalog/ProductRepository.java`:

```java
package com.example.catalog;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface ProductRepository
        extends JpaRepository<Product, Long>, JpaSpecificationExecutor<Product> {
}
```

Gọi `repository.findAll(specification, pageable)` để lấy một Page. Sort được đặt trong Pageable bằng tên thuộc tính Java như `createdAt` hoặc `price`, không dùng tên cột vật lý như `created_at`.

## 14. Kiểm thử Specification với H2

Ví dụ dùng `spring-boot-starter-data-jpa`, H2 và `spring-boot-starter-test`. `@DataJpaTest` khởi tạo test slice cho Entity và Repository.

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:specdb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=true
```

`src/test/java/com/example/catalog/ProductSpecificationTest.java`:

```java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;

@DataJpaTest
class ProductSpecificationTest {
    @Autowired
    private ProductRepository repository;

    private void insertProducts() {
        repository.saveAll(List.of(
                new Product("Mechanical Keyboard", new BigDecimal("120.00"),
                        ProductStatus.ACTIVE, LocalDateTime.parse("2026-01-02T10:00:00"),
                        "Tactile keys"),
                new Product("Wireless Mouse", new BigDecimal("35.00"),
                        ProductStatus.ACTIVE, LocalDateTime.parse("2026-01-03T10:00:00"),
                        null),
                new Product("Mechanical Keyboard Pro", new BigDecimal("180.00"),
                        ProductStatus.ACTIVE, LocalDateTime.parse("2026-01-04T10:00:00"),
                        "RGB keys"),
                new Product("Mechanical Keyboard Budget", new BigDecimal("80.00"),
                        ProductStatus.ACTIVE, LocalDateTime.parse("2026-01-04T11:00:00"),
                        "Compact layout"),
                new Product("Keyboard Draft", new BigDecimal("140.00"),
                        ProductStatus.DRAFT, LocalDateTime.parse("2026-01-04T12:00:00"),
                        "Not published")));
        repository.flush();
    }

    @Test
    void combinesStringComparisonRangeAndCollectionPredicates() {
        insertProducts();

        Specification<Product> spec =
                ProductSpecifications.nameContainsIgnoreCase("KEYBOARD")
                        .and(ProductSpecifications.priceAtLeast(new BigDecimal("100")))
                        .and(ProductSpecifications.priceAtMost(new BigDecimal("200")))
                        .and(ProductSpecifications.createdAtOnOrAfter(
                                LocalDateTime.parse("2026-01-02T00:00:00")))
                        .and(ProductSpecifications.createdAtBefore(
                                LocalDateTime.parse("2026-01-05T00:00:00")))
                        .and(ProductSpecifications.statusIn(List.of(ProductStatus.ACTIVE)));

        Page<Product> page = repository.findAll(
                spec,
                PageRequest.of(0, 10,
                        Sort.by(Sort.Order.desc("price"), Sort.Order.asc("id"))));

        assertThat(page.getTotalElements()).isEqualTo(2);
        assertThat(page.getContent()).extracting(Product::getName)
                .containsExactly("Mechanical Keyboard Pro", "Mechanical Keyboard");
    }

    @Test
    void findsNullAndNonNullDescriptions() {
        insertProducts();

        List<Product> missing = repository.findAll(
                ProductSpecifications.descriptionIsNull());
        List<Product> present = repository.findAll(
                ProductSpecifications.descriptionIsNotNull());

        assertThat(missing).extracting(Product::getName)
                .containsExactly("Wireless Mouse");
        assertThat(present).hasSize(4);
    }

    @Test
    void emptyInMatchesNothingAndEmptyNotInAddsNoRestriction() {
        insertProducts();

        List<Product> inResult = repository.findAll(
                ProductSpecifications.statusIn(List.of()));
        List<Product> notInResult = repository.findAll(
                ProductSpecifications.statusNotIn(List.of()));

        assertThat(inResult).isEmpty();
        assertThat(notInResult).hasSize(5);
    }

    @Test
    void supportsOrCompositionAndEscapedLikeText() {
        insertProducts();

        Specification<Product> keyboardOrMouse =
                ProductSpecifications.nameContainsIgnoreCase("keyboard")
                        .or(ProductSpecifications.nameContainsIgnoreCase("mouse"));

        List<Product> result = repository.findAll(keyboardOrMouse);

        assertThat(result).hasSize(5);
    }

    @Test
    void rejectsNullMembersInStatusCollection() {
        assertThatThrownBy(() ->
                ProductSpecifications.statusIn(java.util.Arrays.asList(ProductStatus.ACTIVE, null)))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
```

Chạy kiểm thử từ thư mục chứa `pom.xml`:

```bash
mvn test
```

Kết quả mong đợi là `BUILD SUCCESS`. Các test xác nhận AND composition cho chuỗi, so sánh, khoảng và tập hợp; `IS NULL`/`IS NOT NULL`; semantics collection rỗng; OR composition; và từ chối phần tử null. Đây là kết quả kỳ vọng của ví dụ, chưa phải log build đã chạy trong môi trường thực tế.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy thuộc tính khi chạy query | Chuỗi trong `root.get("...")` sai tên property Java. | Đối chiếu field/access strategy của Entity; cân nhắc static metamodel để tăng type safety. |
| Bộ lọc chuỗi trả nhiều kết quả hơn dự kiến | `%` hoặc `_` trong đầu vào bị hiểu là wildcard. | Escape ký tự LIKE và truyền escape character rõ ràng. |
| So sánh null không hoạt động | Dùng `equal(path, null)` thay cho predicate null. | Dùng `cb.isNull()` hoặc `cb.isNotNull()`. |
| `IN` với collection rỗng sinh SQL không hợp lệ | Dựa vào provider/database xử lý `IN ()`. | Quy định semantics rõ và trả predicate TRUE/FALSE phù hợp trước khi chạy query. |
| `NOT IN` cho kết quả bất ngờ | Collection có null hoặc cột database cũng có thể null. | Từ chối/lọc null trong tập hợp và quyết định rõ cách xử lý dòng có cột null. |
| Kết quả khoảng thời gian lệch ở ranh giới | Dùng khoảng đóng cho timestamp hoặc tạo mốc cuối ngày thiếu precision. | Dùng `[from, to)` với `>=` và `<` khi phù hợp. |
| Predicate OR làm query quá rộng | Ghép AND/OR không có nhóm logic rõ ràng. | Tạo Specification cho từng nhóm và ghép bằng ngoặc logic qua `.and()`/`.or()`. |
| Page query chạy count query phức tạp | Specification có join hoặc predicate tốn kém. | Kiểm tra SQL/count plan; dùng projection hoặc cách phân trang phù hợp. |
| Dùng fetch join trong Specification gây lỗi phân trang | Collection fetch có thể nhân dòng và ảnh hưởng count query. | Tránh đặt collection fetch trong Specification dùng với Page; dùng EntityGraph hoặc truy vấn riêng. |
| Query chậm khi lọc chuỗi contains | `lower(name) like '%...%'` khó tận dụng B-tree index thông thường. | Đo execution plan và cân nhắc full-text/trigram hoặc chiến lược index theo database. |

## 16. Nguyên tắc thiết kế

1. Mỗi Specification nên biểu diễn một điều kiện có tên rõ ràng, dễ kiểm thử và tái sử dụng.
2. Để Service quyết định filter nào được thêm; không biến null thành nhiều ý nghĩa ngầm.
3. Xác thực khoảng số và thời gian trước khi tạo predicate.
4. Dùng `cb.isNull`/`cb.isNotNull` cho null, không dùng equality với null.
5. Xác định semantics collection rỗng và từ chối phần tử null nếu nghiệp vụ không định nghĩa chúng.
6. Escape `%` và `_` khi tìm chuỗi literal bằng LIKE.
7. Dùng khoảng nửa mở cho timestamp khi cần ghép các khoảng liên tiếp.
8. Ghép điều kiện bằng `.and()`, `.or()` và `.not()` với nhóm logic dễ đọc.
9. Dùng `Pageable` để phân trang Specification; thêm sort ổn định với tiêu chí duy nhất.
10. Hạn chế sửa `CriteriaQuery` bên trong Specification nếu không cần; đặc biệt cẩn thận với distinct, fetch và count query.
11. Cân nhắc static metamodel nếu muốn kiểm tra tên thuộc tính ở compile time.
12. Kiểm thử predicate riêng lẻ và các tổ hợp thực tế trên database mục tiêu.

## 17. Checklist hoàn thành

- [ ] Giải thích được vai trò của `Specification`, `Root`, `CriteriaQuery` và `CriteriaBuilder`.
- [ ] Bật `JpaSpecificationExecutor` cho Repository.
- [ ] Tạo được predicate bằng, lớn hơn, nhỏ hơn và so sánh biên.
- [ ] Viết được điều kiện chuỗi không phân biệt hoa thường, contains và starts-with.
- [ ] Escape `%` và `_` trong điều kiện LIKE.
- [ ] Tạo điều kiện khoảng số và khoảng thời gian.
- [ ] Dùng `isNull` và `isNotNull` đúng cách.
- [ ] Dùng `IN`/`NOT IN` và định nghĩa semantics cho collection rỗng/null.
- [ ] Kết hợp điều kiện bằng AND, OR và NOT.
- [ ] Xây dựng truy vấn động từ criteria object trong Service.
- [ ] Phân trang và sắp xếp kết quả bằng Pageable.
- [ ] Kiểm thử các trường hợp biên bằng `@DataJpaTest`.

Khi hoàn thành, bạn có thể xây dựng bộ lọc tìm kiếm động bằng Specification, kết hợp điều kiện so sánh, chuỗi, khoảng, null và tập hợp theo cách dễ kiểm thử và bảo trì.