# JPQL truy vấn theo Entity và thuộc tính thay vì bảng và cột

## 1. Mục tiêu

JPQL (Jakarta Persistence Query Language) là ngôn ngữ truy vấn làm việc với mô hình đối tượng của JPA. JPQL truy vấn Entity và thuộc tính Java của Entity, trong khi SQL truy vấn bảng và cột vật lý trong database.

Ví dụ, nếu Entity `Product` được ánh xạ vào bảng `catalog_products` và thuộc tính `name` được ánh xạ vào cột `product_name`, JPQL vẫn viết `select p from Product p where p.name = :name`. Tên bảng và tên cột không xuất hiện trong JPQL.

Sau bài học, bạn có thể:
- Phân biệt JPQL với SQL và nhận diện entity name, attribute name.
- Viết truy vấn JPQL trong `@Query` của Spring Data JPA.
- Dùng named parameter, positional parameter, join, path expression và các toán tử điều kiện.
- Trả về Entity, scalar, DTO hoặc Page từ JPQL.
- Dùng fetch join để kiểm soát tải quan hệ và tránh N+1 trong use case phù hợp.
- Thực hiện bulk update/delete và hiểu tác động tới persistence context, lifecycle callback.

## 2. JPQL làm việc với mô hình Entity

JPQL sử dụng:
- **Entity name**: tên Entity trong mô hình JPA. Mặc định là tên lớp không kèm package; có thể đổi bằng `@Entity(name = "...")`.
- **Persistent attribute**: tên thuộc tính Java được ánh xạ trong Entity, gồm field hoặc property theo access strategy của Entity.
- **Association path**: đường dẫn đi qua quan hệ, ví dụ `p.category.name`.

JPQL không dùng tên bảng từ `@Table`, tên cột từ `@Column`, tên getter Java hay tên biến local của ứng dụng. Nó dùng entity name và persistent attribute name.

```java
@Entity
@Table(name = "catalog_products")
public class Product {
    @Id
    private Long id;

    @Column(name = "product_name")
    private String name;
}
```

JPQL:

```jpql
select p from Product p where p.name = :name
```

SQL tương đương có thể là:

```sql
select p.id, p.product_name
from catalog_products p
where p.product_name = ?
```

Provider JPA chịu trách nhiệm chuyển JPQL thành SQL phù hợp với database và mapping. Vì vậy, cùng một JPQL có thể chạy trên các database khác nhau nếu mapping và các biểu thức dùng đều tương thích.

### Đổi tên Entity

Nếu khai báo:

```java
@Entity(name = "CatalogProduct")
@Table(name = "catalog_products")
public class Product {
    // Các thuộc tính persistent.
}
```

JPQL phải dùng entity name `CatalogProduct`:

```jpql
select p from CatalogProduct p where p.name = :name
```

`@Entity(name = ...)` đổi tên trong mô hình JPQL. `@Table(name = ...)` chỉ định tên bảng vật lý. Hai tên này có vai trò khác nhau.

## 3. Ví dụ mô hình dữ liệu

Ví dụ dùng Java 17+, Maven, Spring Boot 3.5.0, Spring Data JPA và H2. Mô hình gồm `Category` và `Product`; mỗi sản phẩm có thể thuộc một danh mục.

### Entity Category

`src/main/java/com/example/catalog/product/Category.java`:

```java
package com.example.catalog.product;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "categories")
public class Category {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 80)
    private String name;

    @Column(nullable = false)
    private boolean active;

    protected Category() {
        // JPA cần constructor không tham số.
    }

    public Category(String name, boolean active) {
        if (name == null || name.isBlank() || name.length() > 80) {
            throw new IllegalArgumentException("Category name is required");
        }
        this.name = name.trim();
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public boolean isActive() {
        return active;
    }
}
```

### Entity Product

`src/main/java/com/example/catalog/product/Product.java`:

```java
package com.example.catalog.product;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "catalog_products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "product_name", nullable = false, length = 160)
    private String name;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "category_id")
    private Category category;

    protected Product() {
        // JPA cần constructor không tham số.
    }

    public Product(String name, BigDecimal price, Category category) {
        if (name == null || name.isBlank() || name.length() > 160) {
            throw new IllegalArgumentException("Product name is required");
        }
        if (price == null || price.signum() < 0) {
            throw new IllegalArgumentException("Price cannot be negative");
        }
        this.name = name.trim();
        this.price = price;
        this.category = category;
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

    public Category getCategory() {
        return category;
    }
}
```

Trong mapping này, `Product.category` là thuộc tính Java. Cột vật lý tương ứng là `category_id`. JPQL truy cập quan hệ bằng `p.category`, không viết `p.category_id`.

## 4. Khai báo JPQL bằng @Query

Spring Data JPA cho phép đặt JPQL trong `@Query` trên phương thức Repository. Tên phương thức lúc này có thể mô tả mục đích nghiệp vụ; chuỗi JPQL xác định truy vấn thực tế.

`src/main/java/com/example/catalog/product/ProductRepository.java`:

```java
package com.example.catalog.product;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

public interface ProductRepository extends JpaRepository<Product, Long> {
    @Query("""
           select p
           from Product p
           where p.category.name = :categoryName
           order by p.name asc
           """)
    List<Product> findByCategoryName(@Param("categoryName") String categoryName);

    @Query("""
           select p
           from Product p
           join p.category c
           where c.active = true
             and p.price <= :maxPrice
           order by p.price asc, p.name asc
           """)
    List<Product> findAffordableProductsInActiveCategories(
            @Param("maxPrice") BigDecimal maxPrice);

    @Query("""
           select p
           from Product p
           left join fetch p.category
           where p.id = :id
           """)
    Optional<Product> findWithCategoryById(@Param("id") Long id);

    @Query(
            value = "select p from Product p join p.category c where c.name = :categoryName",
            countQuery = "select count(p) from Product p join p.category c where c.name = :categoryName")
    Page<Product> findPageByCategoryName(
            @Param("categoryName") String categoryName, Pageable pageable);

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Transactional
    @Query("""
           update Product p
           set p.price = :newPrice
           where p.category.name = :categoryName
           """)
    int updatePriceByCategoryName(
            @Param("categoryName") String categoryName,
            @Param("newPrice") BigDecimal newPrice);
}
```

Phương thức `findByCategoryName` dùng path expression `p.category.name`. JPQL có thể tự tạo join cần thiết để đi qua association. Phương thức thứ hai viết join tường minh để đặt điều kiện trên alias `c`.

`@Query` mặc định nhận JPQL trong Spring Data JPA. Chỉ khi bật `nativeQuery = true` mới chuyển sang SQL native.

## 5. Named parameter và positional parameter

JPQL hỗ trợ named parameter và positional parameter.

Named parameter:

```java
@Query("select p from Product p where p.name = :name and p.price <= :maxPrice")
List<Product> search(
        @Param("name") String name,
        @Param("maxPrice") BigDecimal maxPrice);
```

Positional parameter:

```java
@Query("select p from Product p where p.name = ?1 and p.price <= ?2")
List<Product> search(String name, BigDecimal maxPrice);
```

Named parameter thường dễ đọc và ít nhầm lẫn khi phương thức có nhiều tham số. Tên trong `@Param` phải khớp chính xác tên sau dấu `:` trong JPQL.

Không nối trực tiếp chuỗi do người dùng nhập vào JPQL. Hãy dùng parameter binding để tránh lỗi cú pháp và rủi ro injection.

### Điều kiện LIKE và IN

```java
@Query("""
       select p from Product p
       where lower(p.name) like lower(concat('%', :keyword, '%'))
       """)
List<Product> searchByName(@Param("keyword") String keyword);

@Query("select p from Product p where p.id in :ids")
List<Product> findAllByIds(@Param("ids") List<Long> ids);
```

`IN` với collection parameter phù hợp khi danh sách có phần tử. Với danh sách rỗng, hãy xử lý ở tầng Service trước khi gọi repository để tránh phụ thuộc vào cách provider/database xử lý biểu thức `IN` rỗng.

## 6. Path expression và JOIN

JPQL có thể đi qua thuộc tính lồng nhau bằng dấu chấm:

```jpql
select p from Product p where p.category.name = :categoryName
```

Khi cần lọc, sắp xếp hoặc chọn dữ liệu từ association, có thể khai báo join và alias:

```jpql
select p from Product p join p.category c where c.active = true
```

### INNER JOIN

`join` hoặc `inner join` chỉ trả về các bản ghi có association phù hợp. Ví dụ:

```jpql
select p from Product p join p.category c where c.name = :categoryName
```

### LEFT JOIN

`left join` giữ lại phía trái ngay cả khi không có association ở phía phải:

```jpql
select p from Product p left join p.category c
```

Vì `Product.category` trong ví dụ là optional, sản phẩm chưa có category vẫn có thể xuất hiện trong kết quả.

### Điều kiện ON và WHERE

JPQL cho phép đặt điều kiện bổ sung trên join bằng `on`:

```jpql
select p
from Product p
left join p.category c on c.active = true
```

Điều kiện `on` giới hạn những dòng khớp ở phía join nhưng vẫn giữ Product ở phía trái. Nếu chuyển `c.active = true` xuống `where`, các dòng không có category sẽ bị loại vì điều kiện trên `c` không đúng. Sự khác biệt này đặc biệt quan trọng với `left join`.

### JOIN qua collection

Nếu Entity có collection association, có thể join collection đó:

```jpql
select distinct d
from Department d
join d.employees e
where e.active = true
```

`distinct` giúp loại kết quả Entity trùng lặp khi một Department khớp nhiều Employee. Với collection join, một hàng kết quả SQL có thể tương ứng với cùng một Entity root.

## 7. JOIN FETCH và tránh N+1

`join fetch` yêu cầu provider tải association cùng với Entity root trong cùng truy vấn. Ví dụ:

```jpql
select p
from Product p
left join fetch p.category
where p.id = :id
```

Truy vấn này tải Product và Category liên quan để khi đọc `product.getCategory()` trong transaction, provider không cần truy vấn riêng cho association đó.

Phân biệt:
- `join p.category c`: join để lọc, sắp xếp hoặc dùng dữ liệu từ association; không nhất thiết yêu cầu association được fetch vào Entity graph.
- `join fetch p.category`: join đồng thời yêu cầu tải association.

Fetch join là công cụ hữu ích để xử lý N+1 khi biết trước use case cần dữ liệu liên quan. Có thể dùng `@EntityGraph` thay thế nếu muốn tách fetch plan khỏi chuỗi JPQL.

Không nên phân trang trực tiếp một truy vấn fetch join collection như `@OneToMany` hoặc `@ManyToMany`. Join collection có thể nhân số dòng, làm pagination sai ý nghĩa hoặc khiến Hibernate phải tải nhiều dữ liệu vào bộ nhớ rồi phân trang. Với trường hợp này, cân nhắc truy vấn ID theo trang rồi tải chi tiết, dùng batch fetching, DTO projection hoặc `@EntityGraph` phù hợp. Fetch join to-one thường dễ kiểm soát hơn.

## 8. Projection và DTO bằng JPQL

Không phải lúc nào Service cũng cần toàn bộ Entity. JPQL hỗ trợ constructor expression để trả về DTO.

`src/main/java/com/example/catalog/product/ProductSummary.java`:

```java
package com.example.catalog.product;

import java.math.BigDecimal;

public class ProductSummary {
    private final Long id;
    private final String name;
    private final BigDecimal price;

    public ProductSummary(Long id, String name, BigDecimal price) {
        this.id = id;
        this.name = name;
        this.price = price;
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

Thêm phương thức vào `ProductRepository`:

```java
@Query("""
       select new com.example.catalog.product.ProductSummary(p.id, p.name, p.price)
       from Product p
       where p.category.name = :categoryName
       order by p.name
       """)
List<ProductSummary> findSummariesByCategoryName(
        @Param("categoryName") String categoryName);
```

Constructor expression dùng tên lớp đầy đủ (fully qualified class name) và tham số phải khớp với một constructor phù hợp. Kết quả là DTO, không phải Entity managed. Cách này giảm lượng dữ liệu lấy từ database và tránh đưa Entity graph không cần thiết ra ngoài tầng persistence.

## 9. Aggregate, GROUP BY và HAVING

JPQL hỗ trợ các phép tổng hợp như `count`, `sum`, `avg`, `min`, `max`, cùng `group by` và `having`.

```java
@Query("""
       select c.name, count(p)
       from Product p
       join p.category c
       group by c.name
       having count(p) >= :minimumProducts
       order by c.name
       """)
List<Object[]> countProductsByCategory(
        @Param("minimumProducts") long minimumProducts);
```

Mỗi phần tử `Object[]` chứa hai giá trị theo thứ tự select: tên category và số lượng Product. Khi dùng lâu dài, nên cân nhắc DTO constructor expression hoặc projection có tên field để giảm ép kiểu thủ công.

## 10. Phân trang với Page và countQuery

Spring Data JPA có thể phân trang kết quả JPQL bằng cách nhận `Pageable` và trả về `Page<T>`. Khi cần kiểm soát câu truy vấn đếm, khai báo `countQuery` riêng:

```java
@Query(
        value = "select p from Product p join p.category c where c.name = :categoryName",
        countQuery = "select count(p) from Product p join p.category c where c.name = :categoryName")
Page<Product> findPageByCategoryName(
        @Param("categoryName") String categoryName, Pageable pageable);
```

`Page<T>` chứa nội dung trang và thông tin tổng số kết quả. Spring Data có thể cần chạy thêm count query để xác định tổng số phần tử và tổng số trang. Với truy vấn phức tạp, `countQuery` riêng giúp tránh việc tự suy diễn câu đếm không phù hợp.

Nếu chỉ cần biết còn trang tiếp theo mà không cần tổng số kết quả, cân nhắc trả `Slice<T>` để giảm nhu cầu count query.

Ví dụ gọi repository:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by("name").ascending().and(Sort.by("id").ascending()));

Page<Product> page = productRepository.findPageByCategoryName("Electronics", pageable);
System.out.println(page.getTotalElements());
System.out.println(page.getTotalPages());
```

Chỉ số trang bắt đầu từ 0. Nên có thứ tự ổn định, ví dụ thêm ID làm tiêu chí phụ, để tránh thứ tự không xác định khi nhiều bản ghi có cùng tên.

## 11. UPDATE và DELETE bằng JPQL

JPQL hỗ trợ bulk update và bulk delete. Trong Spring Data JPA, phương thức repository cần `@Modifying`; thao tác phải chạy trong transaction.

Ví dụ:

```java
@Modifying(clearAutomatically = true, flushAutomatically = true)
@Transactional
@Query("update Product p set p.price = :newPrice where p.category.name = :categoryName")
int updatePriceByCategoryName(
        @Param("categoryName") String categoryName,
        @Param("newPrice") BigDecimal newPrice);
```

Giá trị trả về `int` là số bản ghi bị ảnh hưởng. `flushAutomatically = true` yêu cầu flush thay đổi đang chờ trước bulk query; `clearAutomatically = true` yêu cầu clear persistence context sau đó để tránh tiếp tục dùng Entity managed có trạng thái cũ.

Bulk DML có các đặc điểm quan trọng:
- Nó tác động trực tiếp lên database theo một câu lệnh, không tải từng Entity vào persistence context.
- Lifecycle callback như `@PreUpdate`, `@PostUpdate`, `@PreRemove` và `@PostRemove` không chạy cho từng Entity bị tác động.
- Cascade của thao tác Entity thông thường không được áp dụng như khi gọi `remove()` trên từng Entity.
- Entity đang managed có thể giữ giá trị cũ sau bulk query; cần clear hoặc refresh phù hợp.

Không dùng bulk update khi nghiệp vụ yêu cầu chạy logic trên từng Entity. Hãy tải các Entity và thay đổi chúng trong transaction, hoặc chuyển quy tắc cần thiết vào chính bulk statement/database nếu phù hợp.

JPQL bulk update/delete có phạm vi và cú pháp hạn chế hơn SQL. Đặc biệt, không thể tùy ý dùng join trong phần update/delete như truy vấn select; hãy kiểm tra đặc tả JPA và dùng subquery hoặc thiết kế lại truy vấn khi cần.

## 12. JPQL và native SQL

| Tiêu chí | JPQL | Native SQL |
| --- | --- | --- |
| Đối tượng truy vấn | Entity và persistent attribute. | Bảng, view và cột vật lý. |
| Tên trong query | Entity name, property name. | Tên bảng và cột. |
| Tính độc lập database | Cao hơn, provider chuyển thành SQL. | Phụ thuộc dialect/database nhiều hơn. |
| Tính năng đặc thù database | Hạn chế theo biểu thức JPQL và function được hỗ trợ. | Có thể dùng cú pháp, CTE, window function hoặc tính năng riêng của database. |
| Ánh xạ kết quả | Entity, scalar, DTO constructor expression. | Entity mapping, scalar hoặc projection theo cấu hình phù hợp. |

JPQL:

```java
@Query("select p from Product p where p.name = :name")
List<Product> findByNameJpql(@Param("name") String name);
```

Native SQL:

```java
@Query(value = "select * from catalog_products p where p.product_name = :name", nativeQuery = true)
List<Product> findByNameNative(@Param("name") String name);
```

Chỉ bật `nativeQuery = true` khi thực sự muốn viết SQL theo schema vật lý hoặc cần tính năng database mà JPQL không biểu đạt phù hợp.

## 13. Cấu hình dự án và kiểm thử

Ví dụ dùng Java 17+ và Spring Boot 3.5.0. Các dependency cần có:

```xml
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
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:jpqldb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=true
```

`src/test/java/com/example/catalog/product/ProductRepositoryJpqlTest.java`:

```java
package com.example.catalog.product;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

@DataJpaTest
class ProductRepositoryJpqlTest {
    @Autowired
    private ProductRepository productRepository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void queriesByEntityPropertyAndJoinsCategory() {
        Category electronics = entityManager.persist(new Category("Electronics", true));
        Category inactive = entityManager.persist(new Category("Archived", false));
        entityManager.persist(new Product("Keyboard", new BigDecimal("79.90"), electronics));
        entityManager.persist(new Product("Mouse", new BigDecimal("25.00"), electronics));
        entityManager.persist(new Product("Old device", new BigDecimal("10.00"), inactive));
        entityManager.flush();

        List<Product> products = productRepository.findByCategoryName("Electronics");

        assertThat(products)
                .extracting(Product::getName)
                .containsExactly("Keyboard", "Mouse");
    }

    @Test
    void returnsDtoProjection() {
        Category electronics = entityManager.persist(new Category("Electronics", true));
        entityManager.persist(new Product("Keyboard", new BigDecimal("79.90"), electronics));
        entityManager.flush();

        List<ProductSummary> summaries = productRepository
                .findSummariesByCategoryName("Electronics");

        assertThat(summaries).hasSize(1);
        assertThat(summaries.get(0).getName()).isEqualTo("Keyboard");
        assertThat(summaries.get(0).getPrice()).isEqualByComparingTo("79.90");
    }

    @Test
    void fetchesCategoryWithProduct() {
        Category electronics = entityManager.persist(new Category("Electronics", true));
        Product product = entityManager.persist(
                new Product("Keyboard", new BigDecimal("79.90"), electronics));
        entityManager.flush();
        Long productId = product.getId();
        entityManager.clear();

        Product loaded = productRepository.findWithCategoryById(productId).orElseThrow();

        assertThat(loaded.getCategory().getName()).isEqualTo("Electronics");
    }

    @Test
    void paginatesAndCountsResults() {
        Category electronics = entityManager.persist(new Category("Electronics", true));
        entityManager.persist(new Product("Keyboard", new BigDecimal("79.90"), electronics));
        entityManager.persist(new Product("Mouse", new BigDecimal("25.00"), electronics));
        entityManager.persist(new Product("Monitor", new BigDecimal("199.00"), electronics));
        entityManager.flush();

        Page<Product> page = productRepository.findPageByCategoryName(
                "Electronics",
                PageRequest.of(0, 2, Sort.by("name").ascending().and(Sort.by("id").ascending())));

        assertThat(page.getContent()).hasSize(2);
        assertThat(page.getTotalElements()).isEqualTo(3);
        assertThat(page.getTotalPages()).isEqualTo(2);
    }
}
```

Chạy kiểm thử từ thư mục chứa `pom.xml`:

```bash
mvn test
```

Kết quả mong đợi là Maven kết thúc với `BUILD SUCCESS` và cả bốn test đều thành công. Các test kiểm tra path expression, join, DTO constructor projection, fetch join và pagination/count query. Đây là kết quả kỳ vọng từ ví dụ; không phải log build thực tế.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `UnknownEntityException` hoặc không tìm thấy entity | Dùng tên bảng thay cho entity name hoặc entity chưa được scan. | Dùng tên Entity mặc định/tên `@Entity(name=...)` và kiểm tra component scan. |
| Không tìm thấy thuộc tính | Dùng tên cột SQL thay vì persistent attribute hoặc viết sai đường dẫn. | Đối chiếu tên property Java và association mapping. |
| `@Query` chạy như SQL nhưng báo cú pháp JPQL | Quên rằng `@Query` mặc định là JPQL. | Viết entity/property name hoặc bật `nativeQuery = true` nếu cần SQL. |
| Parameter không được bind | Tên `@Param` không khớp `:parameter` hoặc thứ tự positional sai. | Dùng named parameter và đối chiếu chính xác tên. |
| Truy vấn trả Entity trùng lặp sau collection join | Một root Entity khớp nhiều phần tử collection. | Dùng `select distinct` khi semantics yêu cầu Entity duy nhất. |
| N+1 query khi đọc association | Query không fetch association nhưng code truy cập lazy relation nhiều lần. | Dùng fetch join, `@EntityGraph`, batch fetching hoặc DTO. |
| Pagination với collection fetch join không đúng hoặc chậm | Join collection làm nhân dòng và cản trở phân trang ở database. | Tách truy vấn ID theo trang và truy vấn dữ liệu liên quan, hoặc dùng DTO/batch fetching. |
| Entity trong persistence context có dữ liệu cũ sau bulk DML | Bulk query bỏ qua trạng thái managed từng Entity. | Flush trước nếu cần và clear/refresh sau bulk query. |
| DTO constructor expression lỗi | Sai fully qualified class name, thứ tự tham số hoặc kiểu constructor. | Đảm bảo constructor public và tham số khớp biểu thức select. |

## 15. Nguyên tắc viết JPQL dễ bảo trì

1. Luôn dùng entity name và persistent attribute name; chỉ dùng table/column name trong native SQL.
2. Ưu tiên named parameter để query dễ đọc và tránh nhầm thứ tự tham số.
3. Dùng alias cho join để biểu thức điều kiện rõ ràng.
4. Dùng `distinct` khi join collection có thể tạo nhiều dòng cho cùng root Entity và kết quả cần loại trùng.
5. Chỉ dùng fetch join cho association cần thiết trong use case; tránh fetch collection cùng pagination.
6. Dùng DTO projection khi chỉ cần một phần dữ liệu.
7. Khai báo `countQuery` rõ ràng cho Page nếu truy vấn phức tạp.
8. Dùng `@Modifying` và transaction cho bulk DML; chủ động xử lý persistence context sau đó.
9. Chuyển sang native SQL khi cần tính năng đặc thù database hoặc truy vấn không thể biểu đạt tốt bằng JPQL.

## 16. Checklist hoàn thành

- [ ] Giải thích được JPQL truy vấn Entity và thuộc tính Java thay vì bảng/cột vật lý.
- [ ] Phân biệt entity name với tên bảng và persistent attribute với tên cột.
- [ ] Viết được `@Query` với named parameter.
- [ ] Dùng được path expression, inner join, left join và điều kiện `on`.
- [ ] Phân biệt join thường với join fetch.
- [ ] Trả về Entity, DTO và Page từ JPQL.
- [ ] Hiểu tác động của count query và collection fetch join với pagination.
- [ ] Dùng `@Modifying` cho bulk update/delete và xử lý persistence context.
- [ ] Biết khi nào chuyển sang native SQL.
- [ ] Chạy được integration test với H2.

Khi hoàn thành, bạn có thể viết JPQL bám sát mô hình Entity, truy vấn quan hệ đúng cách và lựa chọn giữa Entity result, DTO, pagination hoặc native SQL theo yêu cầu thực tế.