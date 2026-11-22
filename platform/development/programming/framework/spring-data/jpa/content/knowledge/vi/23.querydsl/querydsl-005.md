# Kết hợp điều kiện tìm kiếm động bằng BooleanBuilder

## 1. Mục tiêu

`BooleanBuilder` của Querydsl giúp ghép các điều kiện tìm kiếm được chọn tại runtime. Với màn hình có nhiều bộ lọc tùy chọn, ta có thể thêm từng predicate vào builder thay vì tạo một method Repository cho mọi tổ hợp điều kiện.

Bài học xây dựng tìm kiếm sản phẩm với các nhóm điều kiện:
- So sánh số: giá tối thiểu, tối đa và các toán tử lớn hơn/nhỏ hơn.
- Chuỗi: tìm từ khóa trong tên hoặc SKU, không phân biệt hoa thường.
- Khoảng thời gian: từ mốc bắt đầu bao gồm đến mốc kết thúc không bao gồm.
- Null: tìm sản phẩm có mô tả null hoặc khác null.
- Tập hợp: trạng thái thuộc danh sách được chọn.
- Logic: ghép các bộ lọc bằng AND và nhóm nhiều lựa chọn bằng OR.

Sau bài học, bạn có thể cấu hình Querydsl cho Spring Data JPA, hiểu Q-type được sinh tự động, tạo BooleanBuilder cho từng request, xử lý collection rỗng có chủ đích và phân trang kết quả bằng `QuerydslPredicateExecutor`.

## 2. BooleanBuilder là gì?

`BooleanBuilder` là implementation mutable của Querydsl `Predicate`. Nó bắt đầu rỗng và cho phép thêm điều kiện dần dần bằng `and()` hoặc `or()`.

```java
QProduct product = QProduct.product;
BooleanBuilder predicate = new BooleanBuilder();

predicate.and(product.status.eq(ProductStatus.ACTIVE));
predicate.and(product.price.goe(new BigDecimal("100")));
predicate.and(product.price.loe(new BigDecimal("500")));
```

Logic tương đương:

```text
status = ACTIVE
AND price >= 100
AND price <= 500
```

Điều kiện chỉ được thêm khi người dùng cung cấp bộ lọc:

```java
if (keyword != null && !keyword.isBlank()) {
    predicate.and(product.name.containsIgnoreCase(keyword.trim()));
}
```

Nếu keyword rỗng, predicate tên sản phẩm không được thêm. `BooleanBuilder` có thể thay đổi sau mỗi lời gọi; hãy tạo builder mới cho từng lần tìm kiếm, không lưu nó trong field của Service singleton hoặc chia sẻ giữa nhiều request.

## 3. Querydsl, Q-type và Spring Data JPA

Querydsl cung cấp API Java có kiểu dữ liệu để biểu diễn query. Annotation processor đọc Entity JPA và sinh các lớp Q-type tương ứng. Với Entity `Product`, lớp được sinh là `QProduct`, thường nằm trong `target/generated-sources/annotations`.

| Entity property | Q-type thường được sinh | Ví dụ |
| --- | --- | --- |
| `Long id` | `NumberPath<Long>` | `product.id.eq(10L)` |
| `String name` | `StringPath` | `product.name.containsIgnoreCase("keyboard")` |
| `BigDecimal price` | `NumberPath<BigDecimal>` | `product.price.goe(minimum)` |
| Enum `status` | `EnumPath<ProductStatus>` | `product.status.in(statuses)` |
| `LocalDateTime createdAt` | `DateTimePath<LocalDateTime>` | `product.createdAt.lt(end)` |

Q-type giúp compiler phát hiện nhiều lỗi sai kiểu hoặc sai tên thuộc tính trước khi chạy ứng dụng. Không sửa thủ công các lớp Q vì chúng được tạo lại từ Entity ở mỗi lần build.

Spring Data JPA cung cấp `QuerydslPredicateExecutor<T>` để Repository thực thi predicate Querydsl, gồm cả truy vấn có phân trang.

## 4. Cấu hình Querydsl cho Spring Boot 3

Ví dụ dùng Java 17+, Spring Boot 3.5.x, Spring Data JPA 3.5.x và Querydsl 5.1.0 với Jakarta Persistence. Vì Spring Boot 3 dùng annotation `jakarta.persistence.*`, cần chọn artifact classifier `jakarta`.

Trong `pom.xml`, khai báo dependency và annotation processor:

```xml
<properties>
    <java.version>17</java.version>
    <querydsl.version>5.1.0</querydsl.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>com.querydsl</groupId>
        <artifactId>querydsl-jpa</artifactId>
        <version>${querydsl.version}</version>
        <classifier>jakarta</classifier>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>${java.version}</release>
                <annotationProcessorPaths>
                    <path>
                        <groupId>com.querydsl</groupId>
                        <artifactId>querydsl-apt</artifactId>
                        <version>${querydsl.version}</version>
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
```

Spring Boot dependency management cung cấp phiên bản cho các starter. Querydsl dùng version riêng được khóa ở `querydsl.version`; giữ `querydsl-jpa` và `querydsl-apt` cùng phiên bản.

Chạy build để sinh Q-type:

```bash
mvn clean compile
```

Sau build, kiểm tra `target/generated-sources/annotations/com/example/catalog/QProduct.java`. Nếu Q-type không được sinh, kiểm tra annotation processor path, classifier `jakarta`, package Entity và cấu hình compiler.

## 5. Mô hình Entity

### 5.1. Enum ProductStatus

`src/main/java/com/example/catalog/ProductStatus.java`:

```java
package com.example.catalog;

public enum ProductStatus {
    DRAFT,
    ACTIVE,
    DISCONTINUED
}
```

### 5.2. Entity Product

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

    @Column(nullable = false, unique = true, length = 40)
    private String sku;

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

    public Product(String name, String sku, BigDecimal price, ProductStatus status,
            LocalDateTime createdAt, String description) {
        if (name == null || name.isBlank() || name.length() > 160) {
            throw new IllegalArgumentException("Name is required");
        }
        if (sku == null || sku.isBlank() || sku.length() > 40) {
            throw new IllegalArgumentException("SKU is required");
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
        this.sku = sku.trim();
        this.price = price;
        this.status = status;
        this.createdAt = createdAt;
        this.description = description;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public String getSku() { return sku; }
    public BigDecimal getPrice() { return price; }
    public ProductStatus getStatus() { return status; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public String getDescription() { return description; }
}
```

`description` được phép null để minh họa `isNull()` và `isNotNull()`. Enum dùng `EnumType.STRING` để lưu tên trạng thái.

## 6. Criteria object cho bộ lọc tùy chọn

Không nên truyền quá nhiều tham số rời rạc nếu màn hình tìm kiếm có nhiều trường. Một record gom các tiêu chí thành một đối tượng.

`src/main/java/com/example/catalog/ProductSearchCriteria.java`:

```java
package com.example.catalog;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Set;

public record ProductSearchCriteria(
        String keyword,
        BigDecimal minimumPrice,
        BigDecimal maximumPrice,
        LocalDateTime createdFrom,
        LocalDateTime createdBefore,
        Set<ProductStatus> statuses,
        Boolean descriptionMissing) {
}
```

Quy ước của ví dụ:
- Trường scalar null nghĩa là bỏ qua bộ lọc.
- `statuses == null` nghĩa là không lọc trạng thái.
- `statuses` rỗng nghĩa là người dùng không chọn trạng thái nào, do đó kết quả phải rỗng.
- `descriptionMissing == true` tìm mô tả null; `false` tìm mô tả khác null; null bỏ qua điều kiện mô tả.
- Khoảng thời gian dùng `createdAt >= createdFrom` và `createdAt < createdBefore`.

Xác định semantics trước giúp phân biệt việc không gửi filter với việc gửi collection rỗng.

## 7. Tạo predicate bằng BooleanBuilder

Q-type được sinh từ Entity:

```java
QProduct product = QProduct.product;
BooleanBuilder predicate = new BooleanBuilder();
```

### 7.1. Điều kiện so sánh

Querydsl cung cấp toán tử có kiểu:

| Ý nghĩa | Querydsl |
| --- | --- |
| Bằng | `product.status.eq(ProductStatus.ACTIVE)` |
| Khác | `product.status.ne(ProductStatus.DRAFT)` |
| Lớn hơn | `product.price.gt(value)` |
| Lớn hơn hoặc bằng | `product.price.goe(value)` |
| Nhỏ hơn | `product.price.lt(value)` |
| Nhỏ hơn hoặc bằng | `product.price.loe(value)` |

Thêm điều kiện giá tùy theo input:

```java
if (criteria.minimumPrice() != null) {
    predicate.and(product.price.goe(criteria.minimumPrice()));
}
if (criteria.maximumPrice() != null) {
    predicate.and(product.price.loe(criteria.maximumPrice()));
}
```

Querydsl giữ kiểu của thuộc tính trong Q-type, nên compiler có thể phát hiện nhiều lỗi sai kiểu trước khi chạy ứng dụng.

### 7.2. Điều kiện chuỗi và nhóm OR

Để tìm từ khóa trong tên hoặc SKU:

```java
if (criteria.keyword() != null && !criteria.keyword().isBlank()) {
    String keyword = criteria.keyword().trim();
    BooleanBuilder keywordMatch = new BooleanBuilder();
    keywordMatch.or(product.name.containsIgnoreCase(keyword));
    keywordMatch.or(product.sku.containsIgnoreCase(keyword));
    predicate.and(keywordMatch);
}
```

Logic tương đương:

```text
AND (name contains keyword OR sku contains keyword)
```

Nhóm OR trước rồi thêm cả nhóm vào predicate chính bằng AND. Nếu gọi `predicate.or(...)` trực tiếp cho từng nhánh, kết quả có thể trở thành `(các filter trước AND name-match) OR sku-match`; khi đó SKU khớp có thể vượt qua điều kiện giá hoặc trạng thái.

`containsIgnoreCase` phù hợp với tìm chuỗi con không phân biệt hoa thường. Nếu `%` hoặc `_` trong đầu vào cần được coi là ký tự literal thay vì wildcard, hãy xác nhận semantics của phiên bản Querydsl/provider và bổ sung quy tắc escape phù hợp.

### 7.3. Điều kiện khoảng thời gian

Đối với timestamp, khoảng nửa mở thường thuận tiện khi ghép các khoảng liên tiếp:

```java
if (criteria.createdFrom() != null) {
    predicate.and(product.createdAt.goe(criteria.createdFrom()));
}
if (criteria.createdBefore() != null) {
    predicate.and(product.createdAt.lt(criteria.createdBefore()));
}
```

Điều kiện tương đương `createdAt >= from AND createdAt < before`. Bản ghi đúng tại `createdBefore` không thuộc khoảng. Nếu nghiệp vụ yêu cầu bao gồm cả hai đầu mút, dùng `between(from, to)` sau khi kiểm tra hai mốc hợp lệ.

### 7.4. Điều kiện null

Querydsl có API riêng để kiểm tra null:

```java
if (Boolean.TRUE.equals(criteria.descriptionMissing())) {
    predicate.and(product.description.isNull());
} else if (Boolean.FALSE.equals(criteria.descriptionMissing())) {
    predicate.and(product.description.isNotNull());
}
```

Không dùng `product.description.eq(null)` để biểu diễn SQL `IS NULL`. Dùng `isNull()` hoặc `isNotNull()`.

### 7.5. Điều kiện tập hợp IN và NOT IN

Với collection trạng thái:

```java
if (criteria.statuses() != null) {
    if (criteria.statuses().isEmpty()) {
        predicate.and(Expressions.asBoolean(false));
    } else {
        predicate.and(product.status.in(criteria.statuses()));
    }
}
```

`Expressions.asBoolean(false)` thêm predicate luôn sai khi người dùng truyền danh sách rỗng theo semantics đã chọn. Nếu `statuses` là null, bộ lọc bị bỏ qua; nếu là danh sách không rỗng, Querydsl tạo điều kiện IN.

Với `NOT IN`, có thể viết:

```java
predicate.and(product.status.notIn(excludedStatuses));
```

Không đưa phần tử null vào collection dùng với `IN`/`NOT IN` nếu chưa định nghĩa rõ cách xử lý. SQL dùng logic ba giá trị; đặc biệt một phần tử null trong `NOT IN` có thể khiến phép so sánh thành UNKNOWN. Hãy validate collection trước khi thêm predicate.

## 8. Lớp xây dựng predicate hoàn chỉnh

Đặt logic ghép điều kiện vào một lớp riêng để Service dễ đọc và kiểm thử.

`src/main/java/com/example/catalog/ProductPredicates.java`:

```java
package com.example.catalog;

import com.querydsl.core.BooleanBuilder;
import com.querydsl.core.types.dsl.Expressions;
import java.util.Objects;

public final class ProductPredicates {
    private ProductPredicates() {
    }

    public static BooleanBuilder from(ProductSearchCriteria criteria) {
        Objects.requireNonNull(criteria, "criteria must not be null");

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

        QProduct product = QProduct.product;
        BooleanBuilder predicate = new BooleanBuilder();

        if (criteria.keyword() != null && !criteria.keyword().isBlank()) {
            String keyword = criteria.keyword().trim();
            BooleanBuilder keywordMatch = new BooleanBuilder();
            keywordMatch.or(product.name.containsIgnoreCase(keyword));
            keywordMatch.or(product.sku.containsIgnoreCase(keyword));
            predicate.and(keywordMatch);
        }

        if (criteria.minimumPrice() != null) {
            predicate.and(product.price.goe(criteria.minimumPrice()));
        }
        if (criteria.maximumPrice() != null) {
            predicate.and(product.price.loe(criteria.maximumPrice()));
        }
        if (criteria.createdFrom() != null) {
            predicate.and(product.createdAt.goe(criteria.createdFrom()));
        }
        if (criteria.createdBefore() != null) {
            predicate.and(product.createdAt.lt(criteria.createdBefore()));
        }
        if (criteria.statuses() != null) {
            if (criteria.statuses().isEmpty()) {
                predicate.and(Expressions.asBoolean(false));
            } else {
                predicate.and(product.status.in(criteria.statuses()));
            }
        }
        if (Boolean.TRUE.equals(criteria.descriptionMissing())) {
            predicate.and(product.description.isNull());
        } else if (Boolean.FALSE.equals(criteria.descriptionMissing())) {
            predicate.and(product.description.isNotNull());
        }

        return predicate;
    }
}
```

`from()` tạo builder mới cho mỗi lần gọi. Nó kiểm tra khoảng đầu vào và phần tử null trong collection trước khi tạo query. Predicate chỉ được thêm khi filter tương ứng được cung cấp.

## 9. Repository với QuerydslPredicateExecutor

Repository kế thừa `QuerydslPredicateExecutor<Product>` để thực thi BooleanBuilder:

`src/main/java/com/example/catalog/ProductRepository.java`:

```java
package com.example.catalog;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;

public interface ProductRepository
        extends JpaRepository<Product, Long>, QuerydslPredicateExecutor<Product> {
}
```

Các method thường dùng:

| Phương thức | Công dụng |
| --- | --- |
| `findAll(Predicate)` | Lấy tất cả Entity khớp predicate. |
| `findAll(Predicate, Sort)` | Lấy kết quả theo predicate và thứ tự. |
| `findAll(Predicate, Pageable)` | Lấy Page theo predicate. |
| `count(Predicate)` | Đếm kết quả. |
| `exists(Predicate)` | Kiểm tra có kết quả hay không. |

Vì `BooleanBuilder` implements `Predicate`, có thể truyền trực tiếp vào các method trên.

## 10. Service thực thi tìm kiếm

`src/main/java/com/example/catalog/ProductSearchService.java`:

```java
package com.example.catalog;

import com.querydsl.core.BooleanBuilder;
import java.util.Objects;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
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
        Objects.requireNonNull(pageable, "pageable must not be null");
        BooleanBuilder predicate = ProductPredicates.from(criteria);

        if (!predicate.hasValue()) {
            return repository.findAll(pageable);
        }
        return repository.findAll(predicate, pageable);
    }
}
```

`hasValue()` cho biết builder có predicate hay chưa. Khi không có filter, Service gọi `findAll(pageable)` để tránh truyền builder rỗng. Khi có điều kiện, nó gọi `findAll(predicate, pageable)`.

Pageable có thể mang Sort. Hãy dùng tên thuộc tính Java của Entity và whitelist những field API cho phép sắp xếp. Để kết quả ổn định, thêm ID làm tiêu chí phụ:

```java
Pageable pageable = PageRequest.of(
        0, 20,
        Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id")));
```

## 11. Logic truy vấn khi có nhiều filter

Giả sử người dùng gửi:

```text
keyword = "keyboard"
minimumPrice = 100
maximumPrice = 200
statuses = [ACTIVE]
descriptionMissing = false
```

BooleanBuilder tạo logic tương đương:

```text
(lower(name) contains 'keyboard' OR lower(sku) contains 'keyboard')
AND price >= 100
AND price <= 200
AND status IN (ACTIVE)
AND description IS NOT NULL
```

Nếu có `createdFrom` và `createdBefore`, hai điều kiện thời gian được nối thêm bằng AND. Nếu keyword rỗng, nhóm OR không được thêm. Nếu `statuses` null, trạng thái không bị lọc; nếu `statuses` rỗng, predicate FALSE được thêm và kết quả không có dòng nào.

Những quy ước này là hợp đồng của ví dụ. Nếu ứng dụng muốn collection rỗng mang nghĩa bỏ qua filter, cần đổi logic và test tương ứng.

## 12. Kiểm thử với H2

Ví dụ dùng `spring-boot-starter-data-jpa`, Querydsl JPA, H2 và `spring-boot-starter-test`. Q-type phải được sinh trước khi test biên dịch.

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:querydsldb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=true
```

`src/test/java/com/example/catalog/ProductBooleanBuilderTest.java`:

```java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

@DataJpaTest
@Import(ProductSearchService.class)
class ProductBooleanBuilderTest {
    @Autowired
    private ProductRepository repository;

    @Autowired
    private ProductSearchService searchService;

    private void insertProducts() {
        repository.saveAll(List.of(
                new Product("Mechanical Keyboard", "KB-100", new BigDecimal("120.00"),
                        ProductStatus.ACTIVE, LocalDateTime.parse("2026-01-02T10:00:00"),
                        "Tactile keys"),
                new Product("Wireless Mouse", "MS-200", new BigDecimal("35.00"),
                        ProductStatus.ACTIVE, LocalDateTime.parse("2026-01-03T10:00:00"), null),
                new Product("Mechanical Keyboard Pro", "KB-200", new BigDecimal("180.00"),
                        ProductStatus.ACTIVE, LocalDateTime.parse("2026-01-04T10:00:00"),
                        "RGB keys"),
                new Product("Mechanical Keyboard Budget", "KB-050", new BigDecimal("80.00"),
                        ProductStatus.ACTIVE, LocalDateTime.parse("2026-01-04T11:00:00"),
                        "Compact layout"),
                new Product("Keyboard Draft", "KB-300", new BigDecimal("140.00"),
                        ProductStatus.DRAFT, LocalDateTime.parse("2026-01-04T12:00:00"),
                        "Not published")));
        repository.flush();
    }

    @Test
    void combinesKeywordPriceTimeStatusAndNullPredicates() {
        insertProducts();
        ProductSearchCriteria criteria = new ProductSearchCriteria(
                "KEYBOARD", new BigDecimal("100.00"), new BigDecimal("200.00"),
                LocalDateTime.parse("2026-01-02T00:00:00"),
                LocalDateTime.parse("2026-01-05T00:00:00"),
                Set.of(ProductStatus.ACTIVE), false);

        Page<Product> result = searchService.search(criteria,
                PageRequest.of(0, 10,
                        Sort.by(Sort.Order.desc("price"), Sort.Order.asc("id"))));

        assertThat(result.getTotalElements()).isEqualTo(2);
        assertThat(result.getContent()).extracting(Product::getName)
                .containsExactly("Mechanical Keyboard Pro", "Mechanical Keyboard");
    }

    @Test
    void keywordMatchesEitherNameOrSku() {
        insertProducts();
        ProductSearchCriteria criteria = new ProductSearchCriteria(
                "MS-200", null, null, null, null, null, null);

        Page<Product> result = searchService.search(criteria, PageRequest.of(0, 10));

        assertThat(result.getTotalElements()).isEqualTo(1);
        assertThat(result.getContent().get(0).getName()).isEqualTo("Wireless Mouse");
    }

    @Test
    void emptyStatusSetMatchesNoProducts() {
        insertProducts();
        ProductSearchCriteria criteria = new ProductSearchCriteria(
                null, null, null, null, null, Set.of(), null);

        Page<Product> result = searchService.search(criteria, PageRequest.of(0, 10));

        assertThat(result.getContent()).isEmpty();
        assertThat(result.getTotalElements()).isZero();
    }

    @Test
    void canSearchForNullDescription() {
        insertProducts();
        ProductSearchCriteria criteria = new ProductSearchCriteria(
                null, null, null, null, null, null, true);

        Page<Product> result = searchService.search(criteria, PageRequest.of(0, 10));

        assertThat(result.getTotalElements()).isEqualTo(1);
        assertThat(result.getContent().get(0).getName()).isEqualTo("Wireless Mouse");
    }

    @Test
    void rejectsAnInvalidPriceRange() {
        ProductSearchCriteria criteria = new ProductSearchCriteria(
                null, new BigDecimal("200"), new BigDecimal("100"),
                null, null, null, null);

        assertThatThrownBy(() -> searchService.search(criteria, PageRequest.of(0, 10)))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void emptyCriteriaReturnsPagedResults() {
        insertProducts();
        ProductSearchCriteria criteria = new ProductSearchCriteria(
                null, null, null, null, null, null, null);

        Page<Product> result = searchService.search(criteria,
                PageRequest.of(0, 2, Sort.by(Sort.Order.asc("name"), Sort.Order.asc("id"))));

        assertThat(result.getTotalElements()).isEqualTo(5);
        assertThat(result.getContent()).hasSize(2);
        assertThat(result.getNumber()).isZero();
    }
}
```

Chạy kiểm thử:

```bash
mvn clean test
```

Kết quả mong đợi là Maven kết thúc với `BUILD SUCCESS`. Các test xác nhận nhóm OR giữa tên và SKU, AND giữa giá/thời gian/trạng thái/null, collection rỗng, khoảng giá không hợp lệ và phân trang khi không có filter. Đây là kết quả kỳ vọng của ví dụ; chưa phải log build thực tế.

## 13. BooleanBuilder và các cách tạo query khác

| Cách tiếp cận | Phù hợp khi |
| --- | --- |
| Derived query | Điều kiện ít, ổn định và tên method vẫn dễ đọc. |
| JPQL `@Query` | Cấu trúc truy vấn cố định, có thể biểu diễn gọn bằng JPQL. |
| JPA Specification | Muốn dùng Criteria API chuẩn JPA và kết hợp predicate động. |
| Querydsl `BooleanBuilder` | Muốn predicate có kiểu dữ liệu, ghép động bằng API fluent và dùng Q-type. |
| Custom repository | Cần projection, join/fetch phức tạp, truy vấn nhiều bước hoặc tối ưu riêng. |

`BooleanBuilder` và `Specification` cùng giải quyết điều kiện động nhưng dựa trên API khác nhau. Querydsl cần annotation processor và Q-type; Criteria Specification dùng API chuẩn JPA nhưng tên thuộc tính thường được truyền dưới dạng chuỗi nếu không dùng static metamodel.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy `QProduct` khi compile | Annotation processor chưa chạy hoặc dùng sai classifier. | Kiểm tra `querydsl-apt` classifier `jakarta`, compiler plugin và chạy `mvn clean compile`. |
| Không resolve được `BooleanBuilder` | Thiếu Querydsl dependency hoặc import sai package. | Dùng `com.querydsl:querydsl-jpa` classifier `jakarta` và import `com.querydsl.core.BooleanBuilder`. |
| Bộ lọc OR làm bỏ qua điều kiện khác | Thêm từng nhánh OR trực tiếp vào builder chính. | Gom nhánh OR vào builder con rồi thêm cả nhóm bằng `predicate.and(group)`. |
| Không có filter nhưng query bất ngờ | Truyền builder rỗng vào executor. | Kiểm tra `hasValue()` và gọi `findAll(pageable)` khi không có predicate. |
| Collection rỗng trả kết quả ngoài dự kiến | Không định nghĩa semantics cho danh sách rỗng. | Chọn rõ predicate FALSE, bỏ filter hoặc báo lỗi; thể hiện trong service và test. |
| `NOT IN` bỏ sót dòng | Collection có null hoặc cột cũng có thể null. | Validate phần tử null và quyết định rõ cách xử lý giá trị null trong cột. |
| Tìm chuỗi đặc biệt sai kết quả | `%` hoặc `_` có semantics wildcard trong LIKE. | Xác định quy tắc literal/wildcard và kiểm thử escape với provider/database. |
| Dùng builder chung giữa nhiều request | `BooleanBuilder` mutable và bị thay đổi qua từng lần gọi. | Tạo builder mới trong mỗi lần search; không lưu ở field singleton. |
| Bản ghi trùng hoặc thiếu giữa các trang | Sort không ổn định hoặc dữ liệu thay đổi. | Thêm tiêu chí sort duy nhất; cân nhắc keyset pagination. |
| Querydsl và JPA không tương thích | Trộn artifact `javax` với Entity Jakarta hoặc lệch phiên bản. | Đồng bộ classifier `jakarta`, Querydsl JPA và annotation processor. |

## 15. Nguyên tắc thiết kế

1. Tạo một `BooleanBuilder` mới cho mỗi lần tìm kiếm; không chia sẻ builder mutable giữa các request.
2. Gom nhánh OR liên quan vào builder con, rồi ghép nhóm bằng AND với các filter còn lại.
3. Xác định semantics rõ cho null và collection rỗng trước khi xây dựng predicate.
4. Validate khoảng số, khoảng thời gian và phần tử null trong collection trước khi truy vấn.
5. Dùng Q-type để tận dụng kiểm tra kiểu ở compile time; không chỉnh sửa file Q được sinh tự động.
6. Chỉ thêm predicate khi filter được cung cấp; khi builder rỗng, gọi Repository không predicate.
7. Dùng `Pageable` và Sort với thuộc tính Entity đã whitelist; thêm khóa duy nhất để có thứ tự ổn định.
8. Chọn Querydsl khi cần điều kiện động có kiểu dữ liệu; chọn Specification hoặc JPQL nếu phù hợp hơn với kiến trúc hiện có.
9. Kiểm thử predicate riêng lẻ và các tổ hợp AND/OR quan trọng, đặc biệt collection rỗng và giá trị null.
10. Theo dõi SQL và execution plan khi truy vấn có nhiều điều kiện hoặc bảng lớn.

## 16. Checklist hoàn thành

- [ ] Giải thích được `BooleanBuilder` và vai trò của Q-type.
- [ ] Cấu hình được Querydsl JPA Jakarta annotation processor.
- [ ] Sinh và sử dụng được `QProduct`.
- [ ] Tạo predicate so sánh bằng, lớn hơn, nhỏ hơn và giới hạn biên.
- [ ] Tìm chuỗi bằng `containsIgnoreCase` và ghép nhiều nhánh bằng OR.
- [ ] Tạo khoảng thời gian bằng `goe` và `lt`.
- [ ] Dùng `isNull()` và `isNotNull()` cho thuộc tính nullable.
- [ ] Dùng `in()`/`notIn()` và xử lý collection rỗng/null có chủ đích.
- [ ] Kết hợp nhóm điều kiện bằng AND và OR mà không làm sai thứ tự logic.
- [ ] Thực thi predicate qua `QuerydslPredicateExecutor`.
- [ ] Phân trang và sắp xếp kết quả bằng `Pageable`.
- [ ] Kiểm thử các tổ hợp điều kiện bằng `@DataJpaTest`.

Khi hoàn thành, bạn có thể xây dựng bộ lọc tìm kiếm động bằng Querydsl `BooleanBuilder`, giữ logic AND/OR rõ ràng và thực thi predicate có kiểu dữ liệu qua Spring Data JPA.