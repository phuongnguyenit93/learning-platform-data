# Kết hợp điều kiện bằng and, or, not và nhóm logic

## Mục tiêu

`Specification<T>` trong Spring Data JPA biểu diễn một điều kiện truy vấn có thể tái sử dụng. Mỗi Specification tạo một `Predicate` bằng Criteria API; các Specification có thể kết hợp bằng `and`, `or` và `not` để xây dựng bộ lọc từ những điều kiện nhỏ.

Khả năng kết hợp này hữu ích khi bộ lọc phụ thuộc input của người dùng hoặc quy tắc nghiệp vụ có nhiều nhánh logic. Thay vì ghép chuỗi JPQL thủ công, ta xây các điều kiện có kiểu, gom thành nhóm rồi chuyển cho `JpaSpecificationExecutor` thực thi.

Ví dụ yêu cầu:

```text
Chỉ lấy sản phẩm đang hoạt động và chưa ngừng kinh doanh,
đồng thời thỏa một trong hai nhóm:
  (category là BOOK hoặc TOOL)
  HOẶC (giá từ 100 đến 500),
và nếu người dùng nhập thì tên phải chứa 'spring'
và giá phải từ 100 trở lên.
```

Biểu thức tương ứng:

```text
active
AND NOT discontinued
AND ((category = BOOK OR category = TOOL)
     OR (price >= 100 AND price <= 500))
AND (name contains spring AND price >= 100)
```

Bài này tập trung vào cách xây dựng nhóm điều kiện rõ ràng, xử lý filter tùy chọn, hiểu semantics của `NOT` với giá trị null và tránh lỗi khi kết hợp Specification với join, phân trang và count query.

## 1. Specification và Predicate

`Specification<T>` là abstraction của Spring Data JPA để mô tả một điều kiện cho entity `T`. Nó tạo `Predicate` từ ba đối tượng Criteria API:

- `Root<T>`: entity gốc trong `FROM`, dùng để truy cập thuộc tính và association.
- `CriteriaQuery<?>`: query đang được xây dựng; có thể dùng để cấu hình distinct, subquery hoặc phần query phù hợp.
- `CriteriaBuilder`: factory tạo điều kiện như `equal`, `like`, `greaterThan`, `isNull`, `and`, `or`, `not`.

Định nghĩa cơ bản:

```java
public interface Specification<T> {
    Predicate toPredicate(
            Root<T> root,
            CriteriaQuery<?> query,
            CriteriaBuilder criteriaBuilder
    );
}
```

Trong ứng dụng, thường viết Specification bằng lambda:

```java
static Specification<Product> hasCategory(String category) {
    return (root, query, cb) ->
            cb.equal(root.get("category"), category);
}
```

Specification chỉ mô tả điều kiện; nó không tự chạy query. Repository phải hỗ trợ `JpaSpecificationExecutor<T>` để nhận Specification và thực thi.

```java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                JpaSpecificationExecutor<Product> {
}
```

## 2. Tạo các điều kiện nhỏ có thể tái sử dụng

Mỗi điều kiện nên thể hiện một quy tắc đơn, có tên dễ hiểu. Ví dụ:

```java
public final class ProductSpecifications {
    private ProductSpecifications() {
    }

    public static Specification<Product> hasCategory(String category) {
        return (root, query, cb) ->
                cb.equal(root.get("category"), category);
    }

    public static Specification<Product> isActive(boolean active) {
        return (root, query, cb) ->
                cb.equal(root.get("active"), active);
    }

    public static Specification<Product> isDiscontinued() {
        return (root, query, cb) ->
                cb.isTrue(root.get("discontinued"));
    }

    public static Specification<Product> priceAtLeast(BigDecimal minimum) {
        return (root, query, cb) ->
                cb.greaterThanOrEqualTo(root.get("price"), minimum);
    }

    public static Specification<Product> priceAtMost(BigDecimal maximum) {
        return (root, query, cb) ->
                cb.lessThanOrEqualTo(root.get("price"), maximum);
    }
}
```

Ví dụ trên minh họa cách tạo điều kiện; phần runnable ở cuối bài sẽ cung cấp đầy đủ import, entity và repository.

### Tránh lặp logic

Nếu nhiều màn hình cùng lọc theo category hoặc trạng thái, hãy dùng chung một Specification. Khi quy tắc thay đổi, cập nhật tại một nơi thay vì sửa nhiều chuỗi JPQL.

Không nên tạo một Specification khổng lồ chứa mọi điều kiện và nhiều nhánh `if` lồng nhau. Tách điều kiện nhỏ giúp có thể kiểm thử riêng, đặt tên rõ ràng và tổ hợp theo từng use case.

## 3. Kết hợp AND

`and()` yêu cầu cả hai Specification cùng đúng:

```java
Specification<Product> spec = hasCategory("BOOK")
        .and(isActive(true));
```

Logic:

```sql
where category = 'BOOK'
  and active = true
```

Có thể nối nhiều điều kiện:

```java
Specification<Product> spec = hasCategory("BOOK")
        .and(isActive(true))
        .and(priceAtLeast(new BigDecimal("100")))
        .and(priceAtMost(new BigDecimal("500")));
```

Mỗi lần gọi `and()` tạo một Specification kết hợp. Cách viết nối tiếp phù hợp khi toàn bộ điều kiện đều phải đúng.

## 4. Kết hợp OR

`or()` yêu cầu ít nhất một Specification đúng:

```java
Specification<Product> categoryGroup = hasCategory("BOOK")
        .or(hasCategory("TOOL"));
```

Logic:

```sql
where category = 'BOOK'
   or category = 'TOOL'
```

Có thể kết hợp nhiều nhánh:

```java
Specification<Product> spec = hasCategory("BOOK")
        .or(hasCategory("TOOL"))
        .or(hasCategory("COURSE"));
```

Không nên dùng OR thay cho AND chỉ để làm query “dễ có kết quả”. Mỗi toán tử phải phản ánh đúng quy tắc nghiệp vụ; OR mở rộng tập kết quả, còn AND thu hẹp tập kết quả.

## 5. Dùng NOT để phủ định một điều kiện

`Specification.not(spec)` tạo điều kiện phủ định Specification đầu vào:

```java
Specification<Product> notDiscontinued =
        Specification.not(isDiscontinued());
```

Logic tương ứng với:

```sql
where not (discontinued = true)
```

Hoặc viết trực tiếp bằng CriteriaBuilder trong một Specification:

```java
static Specification<Product> notInCategory(String category) {
    return (root, query, cb) ->
            cb.not(cb.equal(root.get("category"), category));
}
```

`NOT` hữu ích khi quy tắc được diễn đạt tự nhiên dưới dạng loại trừ: không thuộc category, chưa bị ngừng kinh doanh, không có trạng thái bị khóa.

### Cẩn thận với NULL và logic ba giá trị của SQL

Trong SQL, biểu thức so sánh với `NULL` thường cho kết quả `UNKNOWN`, không phải `TRUE` hoặc `FALSE`. Vì vậy:

```sql
not (discontinued = true)
```

không tự động bao gồm hàng có `discontinued IS NULL`. `NOT UNKNOWN` vẫn là `UNKNOWN`, và hàng đó bị loại trong `WHERE`.

Nếu nghiệp vụ coi `NULL` là “chưa ngừng kinh doanh”, viết điều kiện tường minh:

```java
static Specification<Product> isNotDiscontinuedOrUnknown() {
    return (root, query, cb) -> cb.or(
            cb.isFalse(root.get("discontinued")),
            cb.isNull(root.get("discontinued"))
    );
}
```

Trong ví dụ chạy được bên dưới, `discontinued` là cột `NOT NULL`, nên `Specification.not(isDiscontinued())` có nghĩa rõ ràng.

## 6. Nhóm logic và dấu ngoặc

Đây là phần quan trọng nhất khi query có nhiều nhánh. Không nên dựa vào cách đọc tự nhiên của một chuỗi dài; hãy tạo biến Specification cho từng nhóm rồi kết hợp theo cấu trúc mong muốn.

Ví dụ:

```java
Specification<Product> categoryGroup = hasCategory("BOOK")
        .or(hasCategory("TOOL"));

Specification<Product> priceGroup = priceAtLeast(new BigDecimal("100"))
        .and(priceAtMost(new BigDecimal("500")));

Specification<Product> eligible = isActive(true)
        .and(Specification.not(isDiscontinued()))
        .and(categoryGroup.or(priceGroup));
```

Cấu trúc tương đương:

```sql
where active = true
  and not (discontinued = true)
  and (
       (category = 'BOOK' or category = 'TOOL')
       or
       (price >= 100 and price <= 500)
  )
```

Nhóm `categoryGroup` được tính trước, `priceGroup` được tính trước, rồi hai nhóm được OR với nhau. Cuối cùng nhóm đó được AND với trạng thái active và điều kiện NOT.

### Ví dụ về lỗi thiếu nhóm

Yêu cầu: sản phẩm phải active và có category BOOK hoặc TOOL.

Đúng:

```java
Specification<Product> correct = isActive(true)
        .and(hasCategory("BOOK").or(hasCategory("TOOL")));
```

```sql
where active = true
  and (category = 'BOOK' or category = 'TOOL')
```

Sai về logic nếu viết:

```java
Specification<Product> wrong = isActive(true)
        .and(hasCategory("BOOK"))
        .or(hasCategory("TOOL"));
```

Biểu thức này được ghép thành:

```sql
where (active = true and category = 'BOOK')
   or category = 'TOOL'
```

Nhánh TOOL không còn bị ràng buộc bởi `active = true`, nên sản phẩm TOOL đã ngừng hoạt động vẫn có thể xuất hiện.

Quy tắc: tạo Specification con cho từng nhóm OR/AND trước, rồi kết hợp các nhóm. Cách này làm cấu trúc logic thể hiện trực tiếp trong code và giảm lỗi khi thêm điều kiện.

## 7. Kết hợp filter tùy chọn từ request

Trong API tìm kiếm, người dùng có thể chỉ nhập một vài điều kiện. Chỉ thêm Specification khi filter tương ứng có giá trị:

```java
Specification<Product> filters = (root, query, cb) -> cb.conjunction();

if (filter.name() != null && !filter.name().isBlank()) {
    filters = filters.and(nameContains(filter.name()));
}

if (filter.minimumPrice() != null) {
    filters = filters.and(priceAtLeast(filter.minimumPrice()));
}
```

`cb.conjunction()` tạo predicate luôn đúng, đóng vai trò điều kiện trung tính cho phép AND. Khi chưa có filter tùy chọn, query vẫn hợp lệ và không bị lọc thêm.

Nếu xây một nhóm OR động, `cb.disjunction()` tạo predicate luôn sai, là phần tử trung tính cho phép OR. Cần chọn identity đúng:

| Phép kết hợp | Predicate trung tính |
| --- | --- |
| AND | `cb.conjunction()` (TRUE) |
| OR | `cb.disjunction()` (FALSE) |

Không thêm điều kiện với giá trị null theo cách vô tình tạo `field = null`. Nếu muốn tìm hàng có field null, dùng `cb.isNull(root.get("field"))`; nếu null nghĩa là không áp dụng filter, bỏ qua Specification đó.

### Tách filter request khỏi quy tắc nghiệp vụ

Filter do người dùng nhập và điều kiện bắt buộc của nghiệp vụ nên được tạo riêng:

```java
Specification<Product> businessRules = isActive(true)
        .and(Specification.not(isDiscontinued()));

Specification<Product> requestFilters = filtersFromRequest(filter);

Specification<Product> finalSpec = businessRules.and(requestFilters);
```

Nhờ vậy, caller không thể bỏ qua điều kiện bắt buộc chỉ bằng cách không gửi filter. Mọi request đều đi qua `businessRules`.

## 8. Kết hợp Specification theo danh sách

Khi số lượng filter động thay đổi, có thể tích lũy các Specification trong list:

```java
List<Specification<Product>> parts = new ArrayList<>();

if (category != null) {
    parts.add(hasCategory(category));
}
if (minimumPrice != null) {
    parts.add(priceAtLeast(minimumPrice));
}

Specification<Product> combined = (root, query, cb) -> cb.conjunction();
for (Specification<Product> part : parts) {
    combined = combined.and(part);
}
```

Đây là cách ghép tất cả filter bằng AND. Với nhóm OR, dùng một nhóm list riêng và khởi tạo bằng `cb.disjunction()` hoặc dùng các API tổ hợp có sẵn của phiên bản Spring Data JPA đang sử dụng.

Spring Data JPA có các phương thức tổ hợp `and`, `or`, `not` và các factory như `allOf`/`anyOf` trong các phiên bản hiện đại. Khi dự án cần tương thích nhiều phiên bản, kiểm tra API có trong dependency thực tế; cách tích lũy bằng `and()`/`or()` ở trên dễ áp dụng rộng rãi.

## 9. Join, subquery và điều kiện phức tạp

Specification không chỉ so sánh field của entity gốc. Nó có thể tạo join tới association:

```java
static Specification<Product> hasBrandName(String brandName) {
    return (root, query, cb) -> {
        Join<Product, Brand> brand = root.join("brand", JoinType.INNER);
        return cb.equal(brand.get("name"), brandName);
    };
}
```

`root.join` mặc định là inner join; truyền `JoinType.LEFT` nếu cần giữ entity gốc không có association phù hợp. Tên trong `join("brand")` là property Java trên entity, không phải tên bảng.

Với quan hệ to-many, join có thể tạo nhiều hàng SQL cho cùng entity gốc. Nếu query trả entity và cần loại trùng, có thể đặt `query.distinct(true)`, nhưng cần kiểm tra count query khi dùng `Page`.

Specification cũng có thể tạo subquery, ví dụ kiểm tra entity có bản ghi con phù hợp:

```java
static Specification<Product> hasReviewWithScoreAtLeast(int minimum) {
    return (root, query, cb) -> {
        Subquery<Long> subquery = query.subquery(Long.class);
        Root<Review> review = subquery.from(Review.class);
        subquery.select(review.get("product").get("id"))
                .where(
                    cb.equal(review.get("product"), root),
                    cb.greaterThanOrEqualTo(review.get("score"), minimum)
                );
        return cb.exists(subquery);
    };
}
```

Đây là mẫu minh họa cho association `Review.product`; cần có entity và mapping tương ứng trong ứng dụng thực tế.

## 10. Phân trang, count query và Specification

`JpaSpecificationExecutor` cho phép dùng cùng Specification để tìm dữ liệu và đếm:

```java
Page<Product> page = repository.findAll(
        finalSpec,
        PageRequest.of(0, 20, Sort.by("name").ascending().and(Sort.by("id").ascending()))
);

long total = repository.count(finalSpec);
```

`Page<T>` có thể cần count query để biết tổng số hàng. Nếu chỉ cần biết có trang kế tiếp, cân nhắc API trả `Slice<T>` hoặc một query giới hạn phù hợp.

Specification nên chủ yếu mô tả predicate. Hạn chế nhét `fetch`, `orderBy` hoặc thay đổi cấu trúc query vào Specification dùng chung, vì cùng Specification có thể được dùng cho query lấy entity và query đếm. Fetch join collection có thể làm count query sai hoặc phát sinh SQL không phù hợp.

Nếu thật sự cần fetch association, cân nhắc `@EntityGraph`, custom repository hoặc tách query lấy ID/trang trước rồi tải association riêng. Luôn kiểm tra SQL và kết quả khi kết hợp Specification với phân trang.

## 11. Kiểm soát null và kiểu dữ liệu

- Dùng đúng kiểu Java cho CriteriaBuilder: `BigDecimal` với giá, `Instant`/`LocalDate` với thời gian, enum với trạng thái enum.
- Dùng `isNull` và `isNotNull` để kiểm tra null; không dùng `equal(field, null)` thay cho `isNull`.
- Hiểu SQL three-valued logic khi phủ định một predicate có thể trả UNKNOWN.
- Nếu thuộc tính Boolean có thể null, xác định rõ null có được xem là false, true hay trạng thái riêng.
- Với chuỗi, chuẩn hóa hoa/thường và wildcard theo quy tắc nghiệp vụ; nếu input có `%` hoặc `_`, cân nhắc escape để chúng không vô tình trở thành wildcard.
- Với ngày giờ, xác định timezone và khoảng biên; dùng khoảng nửa mở `[from, to)` thường tránh lỗi phần mili/micro giây ở cuối ngày.

## 12. Ví dụ chạy được với Java 17+, Spring Boot và H2

Ví dụ tạo năm sản phẩm và tìm theo nhóm logic. Điều kiện bắt buộc là active và không discontinued; sản phẩm phải thuộc BOOK/TOOL hoặc có giá trong khoảng 100–500; filter request yêu cầu tên chứa `spring` và giá tối thiểu 100.

### Cấu trúc dự án

```text
specification-logic/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/specification/
        │   ├── SpecificationApplication.java
        │   ├── Product.java
        │   ├── ProductRepository.java
        │   └── ProductSpecifications.java
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
    <artifactId>specification-logic</artifactId>
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
spring.datasource.url=jdbc:h2:mem:specificationdb;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

### `Product.java`

```java
package com.example.specification;

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

    @Column(nullable = false, length = 30)
    private String category;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean active;

    @Column(nullable = false)
    private boolean discontinued;

    protected Product() {
    }

    public Product(String name, String category, BigDecimal price,
                   boolean active, boolean discontinued) {
        this.name = name;
        this.category = category;
        this.price = price;
        this.active = active;
        this.discontinued = discontinued;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
```

### `ProductRepository.java`

```java
package com.example.specification;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface ProductRepository extends
        JpaRepository<Product, Long>,
        JpaSpecificationExecutor<Product> {
}
```

### `ProductSpecifications.java`

```java
package com.example.specification;

import java.math.BigDecimal;
import java.util.Locale;
import org.springframework.data.jpa.domain.Specification;

public final class ProductSpecifications {
    private ProductSpecifications() {
    }

    public static Specification<Product> hasCategory(String category) {
        return (root, query, cb) ->
                cb.equal(root.<String>get("category"), category);
    }

    public static Specification<Product> isActive(boolean active) {
        return (root, query, cb) ->
                cb.equal(root.<Boolean>get("active"), active);
    }

    public static Specification<Product> isDiscontinued() {
        return (root, query, cb) ->
                cb.isTrue(root.<Boolean>get("discontinued"));
    }

    public static Specification<Product> priceAtLeast(BigDecimal minimum) {
        return (root, query, cb) ->
                cb.greaterThanOrEqualTo(root.<BigDecimal>get("price"), minimum);
    }

    public static Specification<Product> priceAtMost(BigDecimal maximum) {
        return (root, query, cb) ->
                cb.lessThanOrEqualTo(root.<BigDecimal>get("price"), maximum);
    }

    public static Specification<Product> nameContains(String text) {
        String pattern = "%" + text.toLowerCase(Locale.ROOT) + "%";
        return (root, query, cb) -> cb.like(
                cb.lower(root.<String>get("name")), pattern);
    }

    public static Specification<Product> fromOptionalFilters(
            String name, BigDecimal minimumPrice) {
        Specification<Product> filters =
                (root, query, cb) -> cb.conjunction();

        if (name != null && !name.isBlank()) {
            filters = filters.and(nameContains(name));
        }
        if (minimumPrice != null) {
            filters = filters.and(priceAtLeast(minimumPrice));
        }
        return filters;
    }
}
```

### `SpecificationApplication.java`

```java
package com.example.specification;

import java.math.BigDecimal;
import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;

import static com.example.specification.ProductSpecifications.*;

@SpringBootApplication
public class SpecificationApplication {
    public static void main(String[] args) {
        SpringApplication.run(SpecificationApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(ProductRepository repository) {
        return args -> {
            repository.saveAll(List.of(
                    new Product("Spring Data JPA", "BOOK",
                            new BigDecimal("150.00"), true, false),
                    new Product("Hibernate Tips", "BOOK",
                            new BigDecimal("90.00"), true, false),
                    new Product("Spring Boot Course", "COURSE",
                            new BigDecimal("250.00"), true, false),
                    new Product("Legacy ORM", "TOOL",
                            new BigDecimal("300.00"), false, false),
                    new Product("Retired JPA", "BOOK",
                            new BigDecimal("200.00"), true, true)
            ));
            repository.flush();

            Specification<Product> categoryGroup = hasCategory("BOOK")
                    .or(hasCategory("TOOL"));

            Specification<Product> priceGroup = priceAtLeast(new BigDecimal("100.00"))
                    .and(priceAtMost(new BigDecimal("500.00")));

            Specification<Product> mandatoryRules = isActive(true)
                    .and(Specification.not(isDiscontinued()))
                    .and(categoryGroup.or(priceGroup));

            Specification<Product> requestFilters = fromOptionalFilters(
                    "spring", new BigDecimal("100.00"));

            Specification<Product> finalSpec = mandatoryRules.and(requestFilters);

            Page<Product> page = repository.findAll(
                    finalSpec,
                    PageRequest.of(0, 10,
                            Sort.by(Sort.Order.asc("name"), Sort.Order.asc("id")))
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

Giải thích kết quả:

- `Legacy ORM` bị loại vì `active = false`.
- `Retired JPA` bị loại vì `discontinued = true`.
- `Hibernate Tips` có category BOOK và active, nhưng không chứa từ `spring` và giá thấp hơn 100 nên không qua filter request.
- `Spring Boot Course` không thuộc BOOK/TOOL nhưng giá nằm trong khoảng 100–500; nó qua nhóm OR và filter request.
- `Spring Data JPA` thuộc BOOK, active, chưa discontinued, tên chứa `spring` và giá đạt mức tối thiểu.

Sort theo name rồi id làm thứ tự kết quả xác định. `Page` cung cấp tổng số nên Spring Data có thể chạy thêm count query.

## 13. Kiểm thử Specification

Kiểm thử từng Specification nhỏ giúp xác định điều kiện có đúng hay không; integration test với database giúp kiểm tra Criteria API, join, null và SQL thực tế.

Các tình huống nên có:

- `hasCategory("BOOK")` chỉ trả sản phẩm thuộc BOOK.
- `A.and(B)` chỉ trả hàng thỏa cả hai điều kiện.
- `A.or(B)` trả hàng thỏa ít nhất một nhánh.
- `Specification.not(A)` loại hàng thỏa A.
- Nhóm `(A OR B) AND C` không bị biến thành `(A AND C) OR B`.
- Filter request null hoặc rỗng không làm phát sinh điều kiện ngoài ý muốn.
- Boolean nullable được xử lý theo quy tắc nghiệp vụ.
- Join to-many không làm trùng entity hoặc sai tổng count.
- `Page` trả đúng content, sort và total.

Ví dụ kiểm thử composition có thể dùng `@DataJpaTest`, lưu dữ liệu đại diện rồi gọi `repository.findAll(spec)` và so sánh ID hoặc tên kết quả. Đừng chỉ kiểm tra một Specification bằng cách nhìn chuỗi SQL; kết quả dữ liệu là xác nhận quan trọng.

## 14. Lỗi thường gặp

1. **Ghép AND/OR không có nhóm:** tạo các Specification con rồi kết hợp theo cấu trúc ngoặc mong muốn.
2. **Dùng AND thay cho OR hoặc ngược lại:** viết biểu thức logic trước khi chuyển thành code.
3. **Dùng NOT với field nullable mà không xét UNKNOWN:** quy định rõ cách xử lý NULL và dùng `isNull`/`isFalse` phù hợp.
4. **Dùng `equal(field, null)`:** dùng `isNull` hoặc bỏ filter nếu null nghĩa là không áp dụng.
5. **Quên repository executor:** repository phải extends `JpaSpecificationExecutor<T>`.
6. **Nhét filter tùy chọn vào một query cố định:** tạo Specification chỉ khi input có giá trị.
7. **Để caller bỏ qua business rule:** kết hợp mandatory Specification ở tầng service với filter do request cung cấp.
8. **Join collection gây trùng root:** cân nhắc `distinct`, `EXISTS` hoặc subquery; kiểm tra count query.
9. **Thêm fetch join vào Specification dùng chung:** có thể làm query count/phân trang không hợp lệ hoặc tốn kém.
10. **Dùng tên cột SQL thay tên property:** Criteria API truy cập property Java qua `root.get`.
11. **Tạo Specification quá lớn:** tách thành các predicate nhỏ có tên và trách nhiệm rõ ràng.
12. **Không kiểm thử trên database mục tiêu:** null semantics, collation và execution plan phụ thuộc database/provider.

## 15. Nguyên tắc thực hành

- Mỗi Specification nên mô tả một điều kiện có tên rõ ràng.
- Dùng `and()` khi mọi điều kiện đều phải đúng; dùng `or()` khi một nhánh bất kỳ là đủ.
- Dùng `Specification.not(...)` để phủ định một điều kiện và xem xét NULL theo logic SQL.
- Tạo Specification cho từng nhóm logic trước khi ghép để thể hiện dấu ngoặc.
- Dùng `cb.conjunction()` làm điều kiện trung tính khi tích lũy filter AND; dùng `cb.disjunction()` cho nhóm OR.
- Tách business rule bắt buộc khỏi filter tùy chọn của request.
- Giữ Specification chủ yếu tập trung vào predicate; quản lý fetch, sort và phân trang ở nơi phù hợp.
- Kiểm tra distinct/count khi join quan hệ to-many.
- Viết integration test cho nhóm AND/OR/NOT, null và dữ liệu biên.

Điểm cốt lõi: **`and` yêu cầu mọi điều kiện đúng, `or` yêu cầu ít nhất một nhánh đúng, `not` phủ định một điều kiện. Hãy tạo các nhóm Specification nhỏ rồi kết hợp theo dấu ngoặc nghiệp vụ; cách đó làm rõ logic, dễ thêm filter động và tránh lỗi do nhóm AND/OR sai.**