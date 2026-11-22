# Tránh đọc toàn bảng, chọn thừa cột và đếm không cần thiết

## 1. Mục tiêu

Trong Spring Data JPA, một truy vấn có thể trả về Entity đầy đủ, một projection chỉ chứa vài thuộc tính, một trang dữ liệu hoặc chỉ một con số. Chọn đúng kiểu kết quả giúp giảm dữ liệu đọc từ database, giảm bộ nhớ ứng dụng và tránh các câu truy vấn đếm không cần thiết.

Bài học tập trung vào ba vấn đề:
- **Đọc toàn bảng:** gọi `findAll()` không giới hạn có thể tải quá nhiều dòng vào bộ nhớ.
- **Chọn thừa cột:** trả về Entity đầy đủ dù màn hình chỉ cần ID, tên và giá.
- **Đếm không cần thiết:** dùng `Page` khi giao diện chỉ cần biết còn dữ liệu tiếp theo, hoặc tải danh sách chỉ để kiểm tra có bản ghi hay không.

Sau bài học, bạn có thể:
- Giới hạn số dòng bằng filter, `Pageable`, `Slice`, `Top` và `First`.
- Dùng interface projection và DTO projection để chỉ lấy các cột cần thiết.
- Dùng dynamic projection khi cùng một query phục vụ nhiều kiểu hiển thị.
- Chọn giữa `Page`, `Slice` và `List` theo nhu cầu metadata.
- Dùng `existsBy...` thay cho tải Entity hoặc đếm toàn bộ khi chỉ cần kiểm tra tồn tại.
- Viết `countQuery` phù hợp cho truy vấn phân trang phức tạp.
- Kiểm tra SQL được sinh ra để xác nhận ứng dụng thực sự chỉ đọc dữ liệu cần thiết.

## 2. Tránh đọc toàn bộ bảng

Ví dụ một màn hình chỉ hiển thị 20 sản phẩm đang bán. Cách gọi sau thường không phù hợp với bảng lớn:

```java
List<Product> products = productRepository.findAll();
```

`findAll()` tải toàn bộ Entity vào persistence context và bộ nhớ ứng dụng. Nếu bảng có hàng trăm nghìn dòng, ứng dụng có thể tốn nhiều bộ nhớ, mất thời gian chuyển dữ liệu qua mạng và tạo áp lực lên database.

Hãy đưa điều kiện lọc và giới hạn vào truy vấn:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id")));

Slice<ProductSummary> products =
        productRepository.findSliceByStatus(ProductStatus.ACTIVE, pageable);
```

Query chỉ lấy một nhóm kết quả. Sort có `id` làm tiêu chí phụ để thứ tự ổn định khi nhiều sản phẩm có cùng `createdAt`.

Nếu use case luôn chỉ cần một số lượng nhỏ cố định, có thể dùng `Top` hoặc `First`:

```java
List<ProductSummary> latestTwenty =
        productRepository.findTop20ProjectedByStatusOrderByCreatedAtDescIdDesc(
                ProductStatus.ACTIVE);
```

Không dùng phân trang chỉ để che giấu một truy vấn không có filter nếu nghiệp vụ thực tế cần một phạm vi cụ thể. Hãy xác định điều kiện tìm kiếm, phạm vi tenant/quyền truy cập và giới hạn dữ liệu phù hợp ngay trong query.

## 3. Tránh chọn thừa cột bằng Projection

Giả sử Entity `Product` có nhiều thuộc tính: tên, SKU, mô tả dài, trạng thái, giá, thời gian tạo và các thông tin khác. Một trang danh sách chỉ cần:

```text
id, name, price
```

Nếu Repository trả `Product`, ORM thường phải hydrate Entity với các cột persistent cần thiết của mapping. Với một danh sách chỉ đọc, điều đó có thể lấy nhiều dữ liệu hơn giao diện cần.

Projection định nghĩa một góc nhìn nhỏ hơn của Entity. Spring Data JPA có thể truy vấn các thuộc tính được yêu cầu và trả về kiểu projection thay vì Entity đầy đủ.

### 3.1. Closed interface projection

Tạo interface chỉ khai báo các getter cần dùng:

`src/main/java/com/example/catalog/ProductSummary.java`:

```java
package com.example.catalog;

import java.math.BigDecimal;

public interface ProductSummary {
    Long getId();
    String getName();
    BigDecimal getPrice();
}
```

Repository:

```java
List<ProductSummary> findProjectedByStatus(ProductStatus status);
```

Ví dụ gọi:

```java
List<ProductSummary> rows =
        productRepository.findProjectedByStatus(ProductStatus.ACTIVE);

for (ProductSummary row : rows) {
    System.out.println(row.getName() + ": " + row.getPrice());
}
```

Vì interface chỉ có các accessor tương ứng với thuộc tính Entity, đây là closed projection. Spring Data biết những thuộc tính nào được sử dụng và có thể tối ưu phần dữ liệu cần lấy.

Projection trên phù hợp cho danh sách đọc. Nó không phải Entity managed; thay đổi một projection không được JPA dirty checking tự động ghi ngược như Entity.

### 3.2. Dùng projection với Pageable

Projection có thể kết hợp với `Pageable` và `Slice`:

```java
Slice<ProductSummary> findSliceByStatus(
        ProductStatus status, Pageable pageable);
```

Ví dụ:

```java
Slice<ProductSummary> slice = productRepository.findSliceByStatus(
        ProductStatus.ACTIVE,
        PageRequest.of(0, 20,
                Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id"))));
```

Repository chỉ trả các thuộc tính projection của tối đa một lát dữ liệu. `Slice` còn cho biết có trang tiếp theo hay không mà không cần cung cấp tổng số dòng.

### 3.3. Open projection và giới hạn tối ưu

Open projection có thể dùng SpEL để truy cập bất kỳ thuộc tính nào của target Entity:

```java
public interface ProductDisplay {
    @Value("#{target.name + ' (' + target.sku + ')'}")
    String getDisplayName();
}
```

Vì biểu thức có thể truy cập các thuộc tính tùy ý, Spring Data không thể luôn xác định chính xác tập cột tối thiểu cần lấy. Open projection có thể làm mất lợi ích tối ưu chọn cột.

Với truy vấn danh sách lớn, ưu tiên closed projection hoặc DTO projection có danh sách thuộc tính rõ ràng. Projection lồng nhau qua association cũng có thể khiến provider cần join và materialize thêm dữ liệu; hãy kiểm tra SQL thay vì giả định chỉ có một cột được lấy.

## 4. DTO projection bằng constructor expression

Nếu muốn kiểu trả về cụ thể, dùng DTO hoặc Java record. DTO không phải Entity và không được quản lý trong persistence context.

`src/main/java/com/example/catalog/ProductCard.java`:

```java
package com.example.catalog;

import java.math.BigDecimal;

public record ProductCard(Long id, String name, BigDecimal price) {
}
```

JPQL constructor expression:

```java
@Query("""
       select new com.example.catalog.ProductCard(
           p.id, p.name, p.price)
       from Product p
       where p.status = :status
       order by p.createdAt desc, p.id desc
       """)
List<ProductCard> findCardsByStatus(
        @Param("status") ProductStatus status);
```

JPQL phải dùng tên lớp đầy đủ trong constructor expression. Thứ tự và kiểu tham số phải khớp với constructor canonical của record.

DTO projection hữu ích khi:
- API chỉ cần một tập field cố định.
- Muốn response không phụ thuộc Entity mapping.
- Cần trả dữ liệu tổng hợp hoặc field được tính trong query.
- Muốn tách read model khỏi Entity được dùng để cập nhật.

Không dùng DTO projection rồi kỳ vọng thay đổi field sẽ được lưu bằng `save()` như Entity. Nếu cần cập nhật, tải Entity phù hợp, thay đổi nó trong transaction hoặc dùng câu lệnh update có chủ đích.

## 5. Dynamic projection

Đôi khi cùng một điều kiện lọc cần trả về các hình dạng dữ liệu khác nhau. Dynamic projection cho phép caller chọn kiểu kết quả bằng tham số `Class<T>`:

```java
<T> List<T> findByStatus(ProductStatus status, Class<T> projectionType);
```

Gọi với interface projection:

```java
List<ProductSummary> summaries = productRepository.findByStatus(
        ProductStatus.ACTIVE, ProductSummary.class);
```

Gọi với DTO:

```java
List<ProductCard> cards = productRepository.findByStatus(
        ProductStatus.ACTIVE, ProductCard.class);
```

Spring Data nhận diện `Class<T>` tương ứng với kiểu generic trả về là tham số dynamic projection. Constructor của DTO phải khớp các thuộc tính mà Spring Data dùng để tạo projection.

Dynamic projection giúp tái sử dụng điều kiện lọc, nhưng không nên tạo quá nhiều kiểu trả về tùy tiện. Mỗi projection nên đại diện cho một nhu cầu đọc cụ thể và ổn định.

## 6. Khi nào nên trả Entity?

Projection không thay thế Entity trong mọi trường hợp. Hãy trả Entity khi use case cần:

- Thay đổi dữ liệu và dựa vào dirty checking.
- Thực hiện nghiệp vụ qua domain method của Entity.
- Dùng association hoặc lifecycle callback của Entity.
- Cần Entity managed trong transaction.

Ví dụ cập nhật trạng thái:

```java
@Transactional
public void deactivate(Long id) {
    Product product = repository.findById(id)
            .orElseThrow(() -> new IllegalArgumentException("Product not found"));
    product.deactivate();
}
```

Ở đây Entity là lựa chọn hợp lý vì Service gọi domain method và muốn JPA ghi thay đổi khi transaction flush.

Với màn hình danh sách chỉ đọc, dùng projection thường phù hợp hơn việc tải toàn bộ Entity rồi chuyển từng object thành DTO:

```java
// Tải Entity đầy đủ rồi mới bỏ đi các field không cần.
List<ProductCard> cards = repository.findByStatus(ProductStatus.ACTIVE)
        .stream()
        .map(p -> new ProductCard(p.getId(), p.getName(), p.getPrice()))
        .toList();
```

Đoạn code trên tạo DTO sau khi Entity đã được tải. Nếu mục tiêu là giảm số cột từ database, hãy projection ngay trong Repository.

## 7. Page, Slice và List: tránh count query không cần thiết

Ba kiểu trả về thường gặp khi Repository nhận `Pageable` có chi phí và metadata khác nhau:

| Kiểu trả về | Metadata | Count query | Khi nên dùng |
| --- | --- | --- | --- |
| `Page<T>` | Trang hiện tại, tổng số dòng và tổng số trang. | Có thể cần count query để tính tổng; framework có thể tối ưu trong một số trường hợp. | UI thực sự cần hiển thị tổng số kết quả/trang. |
| `Slice<T>` | Trang hiện tại và `hasNext()`/`hasPrevious()`. | Không cần count toàn bộ; thường lấy thêm một dòng để xác định còn trang sau. | Nút “Tải thêm”, cuộn vô hạn hoặc chỉ cần biết còn dữ liệu. |
| `List<T>` + `Pageable` | Chỉ danh sách nội dung của trang. | Không cần count query để tạo metadata trang. | Caller chỉ cần các dòng trong một cửa sổ dữ liệu. |

### 7.1. Page khi cần tổng số chính xác

```java
Page<ProductSummary> findPageByStatus(
        ProductStatus status, Pageable pageable);
```

`Page` cung cấp:

- `getContent()`: nội dung trang.
- `getNumber()`: page index hiện tại.
- `getSize()`: page size được yêu cầu.
- `getNumberOfElements()`: số dòng thực tế trong trang.
- `getTotalElements()`: tổng số dòng khớp filter.
- `getTotalPages()`: tổng số trang.

Để có `getTotalElements()` và `getTotalPages()`, Spring Data thường cần thực hiện count query. Trong một số trường hợp framework có thể suy ra tổng từ nội dung trang và tránh count; vì vậy không nên giả định mọi lần gọi Page luôn có đúng hai SQL statement.

### 7.2. Slice khi chỉ cần biết còn dữ liệu

```java
Slice<ProductSummary> findSliceByStatus(
        ProductStatus status, Pageable pageable);
```

Ví dụ trang có size 20. Spring Data thường yêu cầu thêm một dòng để xác định `hasNext()`. Caller nhận tối đa 20 dòng và một cờ cho biết còn dữ liệu. Không có tổng số dòng hoặc tổng số trang.

Nếu UI không hiển thị tổng số, `Slice` thường tránh chi phí count không cần thiết.

### 7.3. List với Pageable khi chỉ cần nội dung

```java
List<ProductSummary> findPageContentByStatus(
        ProductStatus status, Pageable pageable);
```

Method này trả danh sách của trang yêu cầu nhưng không trả metadata tổng. Dùng khi Service đã biết cách điều hướng hoặc client chỉ cần nội dung trang.

Không nhầm `List` không có metadata với việc query không giới hạn. Khi truyền `Pageable`, truy vấn vẫn bị giới hạn theo page size và offset.

## 8. Dùng exists thay vì tải hoặc đếm

Nếu câu hỏi nghiệp vụ chỉ là “có sản phẩm với SKU này không?”, không cần tải Entity:

```java
boolean existsBySku(String sku);
```

Nếu dùng:

```java
boolean exists = !repository.findBySku(sku).isEmpty();
```

Repository có thể phải tải các Entity khớp vào bộ nhớ chỉ để kiểm tra danh sách có rỗng hay không. `existsBySku` thể hiện đúng ý định và cho phép Spring Data tạo truy vấn existence phù hợp.

Không dùng `countBySku(sku) > 0` nếu chỉ cần biết có tồn tại. `countBySku` phù hợp khi nghiệp vụ thực sự cần con số:

```java
long activeCount = repository.countByStatus(ProductStatus.ACTIVE);
```

Phân biệt:

| Câu hỏi | Repository method |
| --- | --- |
| Có SKU này không? | `existsBySku(sku)` |
| Có bao nhiêu sản phẩm ACTIVE? | `countByStatus(ACTIVE)` |
| Lấy một sản phẩm phù hợp đầu tiên? | `findFirstBySkuOrderByCreatedAtDescIdDesc(sku)` |
| Lấy tối đa 20 sản phẩm mới nhất? | `findTop20ProjectedByStatusOrderByCreatedAtDescIdDesc(status)` |

Tránh tải toàn bộ danh sách rồi gọi `.size()` để lấy tổng số dòng. Dùng `countBy...` nếu cần tổng, và `existsBy...` nếu chỉ cần boolean.

## 9. Tối ưu count query cho Page

Với query đơn giản, Spring Data có thể tự suy ra count query. Với query phức tạp, đặc biệt có join hoặc `distinct`, nên khai báo `countQuery` riêng để đếm đúng root Entity.

Ví dụ query có join tới collection tag:

```java
@Query(
    value = """
        select distinct new com.example.catalog.ProductCard(
            p.id, p.name, p.price)
        from Product p
        join p.tags t
        where p.status = :status
          and t.name = :tagName
        """,
    countQuery = """
        select count(distinct p.id)
        from Product p
        join p.tags t
        where p.status = :status
          and t.name = :tagName
        """
)
Page<ProductCard> findCardsByStatusAndTag(
        @Param("status") ProductStatus status,
        @Param("tagName") String tagName,
        Pageable pageable);
```

Join một-nhiều có thể tạo nhiều dòng cho cùng một Product. Count `count(p)` có thể đếm trùng root; `count(distinct p.id)` phản ánh số Product duy nhất trong ví dụ.

Count query nên giữ cùng điều kiện lọc với query dữ liệu. Không đưa `order by` vào count query. Nếu count query vẫn rất tốn kém và UI không cần tổng số, đổi kiểu trả về thành `Slice` hoặc `List` với `Pageable` thay vì cố tối ưu một con số không cần dùng.

## 10. Ví dụ Entity và Repository hoàn chỉnh

Ví dụ dùng Java 17+, Spring Boot 3.x, Spring Data JPA và database do ứng dụng quản lý. Entity có các thuộc tính đủ để minh họa projection.

`src/main/java/com/example/catalog/ProductStatus.java`:

```java
package com.example.catalog;

public enum ProductStatus {
    DRAFT,
    ACTIVE,
    DISCONTINUED
}
```

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

    @Column(length = 2000)
    private String description;

    protected Product() {
        // JPA cần constructor không tham số.
    }

    public Product(String name, String sku, BigDecimal price,
            ProductStatus status, LocalDateTime createdAt, String description) {
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

`src/main/java/com/example/catalog/ProductSummary.java`:

```java
package com.example.catalog;

import java.math.BigDecimal;

public interface ProductSummary {
    Long getId();
    String getName();
    BigDecimal getPrice();
}
```

`src/main/java/com/example/catalog/ProductCard.java`:

```java
package com.example.catalog;

import java.math.BigDecimal;

public record ProductCard(Long id, String name, BigDecimal price) {
}
```

`src/main/java/com/example/catalog/ProductRepository.java`:

```java
package com.example.catalog;

import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository extends JpaRepository<Product, Long> {
    List<ProductSummary> findProjectedByStatus(ProductStatus status);

    List<ProductSummary> findTop20ProjectedByStatusOrderByCreatedAtDescIdDesc(
            ProductStatus status);

    <T> List<T> findByStatus(ProductStatus status, Class<T> projectionType);

    Slice<ProductSummary> findSliceByStatus(
            ProductStatus status, Pageable pageable);

    List<ProductSummary> findPageContentByStatus(
            ProductStatus status, Pageable pageable);

    @Query("""
           select new com.example.catalog.ProductCard(p.id, p.name, p.price)
           from Product p
           where p.status = :status
           """)
    Page<ProductCard> findCardPageByStatus(
            @Param("status") ProductStatus status, Pageable pageable);

    boolean existsBySku(String sku);

    long countByStatus(ProductStatus status);

    Optional<Product> findFirstBySkuOrderByCreatedAtDescIdDesc(String sku);
}
```

Repository trên minh họa các kiểu kết quả khác nhau:

- `findProjectedByStatus`: interface projection.
- `findTop20ProjectedByStatus...`: danh sách có giới hạn cố định và thứ tự ổn định.
- `findByStatus(status, ProductCard.class)`: dynamic DTO projection.
- `findSliceByStatus`: phân trang không cần tổng số.
- `findPageContentByStatus`: nội dung trang dưới dạng List.
- `findCardPageByStatus`: DTO projection có metadata Page và count query tự suy ra cho query đơn giản.
- `existsBySku` và `countByStatus`: chỉ trả boolean hoặc số lượng.

## 11. Service chọn kiểu truy vấn theo use case

Service nên thể hiện rõ caller cần nội dung, metadata hay chỉ một giá trị:

```java
package com.example.catalog;

import java.util.List;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class ProductReadService {
    private static final int MAX_PAGE_SIZE = 100;

    private final ProductRepository repository;

    public ProductReadService(ProductRepository repository) {
        this.repository = repository;
    }

    public Slice<ProductSummary> browseActive(int page, int size) {
        Pageable pageable = validatedPageable(page, size);
        return repository.findSliceByStatus(ProductStatus.ACTIVE, pageable);
    }

    public List<ProductSummary> latestActive() {
        return repository.findTop20ProjectedByStatusOrderByCreatedAtDescIdDesc(
                ProductStatus.ACTIVE);
    }

    public boolean skuExists(String sku) {
        if (sku == null || sku.isBlank()) {
            return false;
        }
        return repository.existsBySku(sku.trim());
    }

    private Pageable validatedPageable(int page, int size) {
        if (page < 0) {
            throw new IllegalArgumentException("Page index must be zero or greater");
        }
        if (size < 1 || size > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException("Page size must be between 1 and 100");
        }
        return PageRequest.of(page, size,
                Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id")));
    }
}
```

Service giới hạn page size để client không thể yêu cầu một trang quá lớn. Với màn hình duyệt tuần tự, `Slice` tránh count query. Với widget chỉ cần 20 sản phẩm mới nhất, `Top20` đủ dùng. Với kiểm tra SKU, `existsBySku` trả boolean mà không tải danh sách Entity.

## 12. Kiểm tra SQL thực tế

Đừng chỉ nhìn kiểu trả về rồi kết luận truy vấn đã tối ưu. Hãy xem SQL do Hibernate phát ra để xác nhận:

- Projection chỉ chọn các cột cần dùng, ví dụ `id`, `name`, `price`.
- Query có `WHERE` tương ứng với bộ lọc.
- Query có giới hạn số dòng và offset khi dùng Pageable.
- `Slice` không phát sinh count query để lấy tổng số dòng.
- `Page` có thể phát sinh count query nếu cần tổng số.
- `existsBy...` không tải danh sách Entity đầy đủ.

Trong môi trường phát triển hoặc test, có thể bật:

```properties
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
logging.level.org.hibernate.SQL=DEBUG
```

Không bật bind parameter logging rộng rãi ở production nếu query có thể chứa dữ liệu nhạy cảm. SQL log cần được kiểm soát theo môi trường.

Ví dụ SQL mong đợi cho closed projection có thể có dạng:

```sql
select p.id, p.name, p.price
from products p
where p.status = ?
order by p.created_at desc, p.id desc
```

SQL cụ thể phụ thuộc dialect, naming strategy và provider. Điều cần xác nhận là danh sách cột được chọn, điều kiện lọc và giới hạn kết quả, không phải alias hoặc format chính xác.

## 13. Kiểm thử với H2

Ví dụ dùng `spring-boot-starter-data-jpa`, H2 và `spring-boot-starter-test`. `@DataJpaTest` kiểm thử Repository trong test slice.

`src/test/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:projectiondb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=true
```

`src/test/java/com/example/catalog/ProductProjectionTest.java`:

```java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;

@DataJpaTest
class ProductProjectionTest {
    @Autowired
    private ProductRepository repository;

    private void insertProducts() {
        repository.saveAll(List.of(
                new Product("Keyboard", "KB-100", new BigDecimal("120.00"),
                        ProductStatus.ACTIVE, LocalDateTime.parse("2026-01-01T10:00:00"),
                        "Long description that the list does not need"),
                new Product("Mouse", "MS-200", new BigDecimal("35.00"),
                        ProductStatus.ACTIVE, LocalDateTime.parse("2026-01-02T10:00:00"),
                        "Another long description"),
                new Product("Monitor", "MN-300", new BigDecimal("250.00"),
                        ProductStatus.ACTIVE, LocalDateTime.parse("2026-01-03T10:00:00"),
                        "Panel details"),
                new Product("Draft keyboard", "KB-400", new BigDecimal("90.00"),
                        ProductStatus.DRAFT, LocalDateTime.parse("2026-01-04T10:00:00"),
                        "Not published")));
        repository.flush();
    }

    @Test
    void returnsOnlyTheRequestedProjectionProperties() {
        insertProducts();

        List<ProductSummary> result =
                repository.findProjectedByStatus(ProductStatus.ACTIVE);

        assertThat(result).hasSize(3);
        assertThat(result).extracting(ProductSummary::getName)
                .containsExactlyInAnyOrder("Keyboard", "Mouse", "Monitor");
        assertThat(result).allSatisfy(row -> {
            assertThat(row.getId()).isNotNull();
            assertThat(row.getPrice()).isNotNull();
        });
    }

    @Test
    void dynamicProjectionCanReturnDtoRecords() {
        insertProducts();

        List<ProductCard> result = repository.findByStatus(
                ProductStatus.ACTIVE, ProductCard.class);

        assertThat(result).hasSize(3);
        assertThat(result).extracting(ProductCard::name)
                .containsExactlyInAnyOrder("Keyboard", "Mouse", "Monitor");
    }

    @Test
    void sliceProvidesNextFlagWithoutTotalCountMetadata() {
        insertProducts();

        Slice<ProductSummary> slice = repository.findSliceByStatus(
                ProductStatus.ACTIVE,
                PageRequest.of(0, 2, Sort.by("id").ascending()));

        assertThat(slice.getContent()).hasSize(2);
        assertThat(slice.hasNext()).isTrue();
        assertThat(slice.getNumber()).isZero();
    }

    @Test
    void pageDtoReturnsTotalWhenTheCallerNeedsIt() {
        insertProducts();

        Page<ProductCard> page = repository.findCardPageByStatus(
                ProductStatus.ACTIVE,
                PageRequest.of(0, 2, Sort.by("name").ascending()));

        assertThat(page.getContent()).hasSize(2);
        assertThat(page.getTotalElements()).isEqualTo(3);
        assertThat(page.getTotalPages()).isEqualTo(2);
    }

    @Test
    void existenceAndCountMethodsReturnOnlyScalarResults() {
        insertProducts();

        assertThat(repository.existsBySku("KB-100")).isTrue();
        assertThat(repository.existsBySku("UNKNOWN")).isFalse();
        assertThat(repository.countByStatus(ProductStatus.ACTIVE)).isEqualTo(3);
    }
}
```

Chạy kiểm thử từ thư mục chứa `pom.xml`:

```bash
mvn test
```

Kết quả mong đợi là Maven kết thúc với `BUILD SUCCESS`. Các test xác nhận interface projection, dynamic DTO projection, Slice, Page metadata, existence và count. Đây là kết quả kỳ vọng của ví dụ; chưa có log build thực tế.

Test dữ liệu xác nhận kiểu và nội dung trả về. Để xác nhận chính xác số cột SQL và việc không phát sinh count query, xem SQL log hoặc dùng công cụ đo SQL trong integration test; assertion trên kết quả Java không tự chứng minh hình dạng SQL.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Projection getter trả null | Tên getter không khớp thuộc tính Entity hoặc alias projection. | Dùng tên property chính xác và kiểm tra SQL/alias. |
| Projection vẫn chọn nhiều cột | Dùng open projection SpEL hoặc nested projection cần nhiều association. | Ưu tiên closed projection phẳng hoặc DTO constructor expression. |
| Tải Entity rồi mới chuyển DTO | Projection được thực hiện ở Java sau khi query đã hydrate Entity. | Chuyển projection xuống Repository/JPQL để giảm cột từ database. |
| `Page` chậm hơn dự kiến | Count query tốn kém, nhất là với join hoặc filter phức tạp. | Dùng Slice/List nếu không cần tổng; viết `countQuery` riêng nếu cần Page. |
| Count bị đếm trùng | Join collection tạo nhiều dòng cho một root Entity. | Dùng `count(distinct root.id)` và giữ điều kiện lọc tương ứng. |
| `findAll().size()` gây tải dữ liệu lớn | Ứng dụng lấy toàn bộ Entity chỉ để biết số lượng. | Dùng `countBy...` nếu cần số, `existsBy...` nếu chỉ cần boolean. |
| `exists` được viết bằng cách lấy danh sách | Caller chỉ cần biết có kết quả nhưng Repository trả Entity collection. | Dùng derived query `existsBy...`. |
| Trang sâu chạy chậm | Offset lớn buộc database bỏ qua nhiều dòng. | Giới hạn page size; cân nhắc keyset/scrolling khi duyệt dữ liệu lớn. |
| Projection dùng để cập nhật nhưng không lưu | DTO/interface projection không phải Entity managed. | Tải Entity cho use case thay đổi dữ liệu. |
| Fetch join làm query nặng hoặc trùng root | Join collection mở rộng số dòng và cột trả về. | Dùng projection, batch fetch hoặc query hai bước phù hợp. |

## 15. Nguyên tắc thiết kế

1. Không gọi `findAll()` không giới hạn cho màn hình danh sách hoặc API trả dữ liệu lớn.
2. Thêm filter và giới hạn phù hợp ngay trong Repository query.
3. Dùng closed interface projection hoặc DTO projection khi chỉ cần một phần thuộc tính.
4. Dùng Entity khi cần domain behavior, dirty checking hoặc lifecycle; dùng DTO cho read model.
5. Dùng `Slice` khi chỉ cần biết có trang kế tiếp; dùng `Page` khi tổng số là yêu cầu thật; dùng `List` với Pageable khi chỉ cần nội dung trang.
6. Dùng `existsBy...` cho câu hỏi có/không và `countBy...` khi thực sự cần số lượng.
7. Không tải danh sách rồi gọi `.size()` chỉ để đếm.
8. Với Page query phức tạp, khai báo `countQuery` đúng và dùng `count(distinct id)` nếu join làm nhân dòng.
9. Giữ sort ổn định với tiêu chí duy nhất như ID; giới hạn page size ở Service/API.
10. Kiểm tra SQL thực tế để xác nhận số cột, filter, limit và count query.
11. Đo hiệu năng trên database gần production; H2 không đại diện đầy đủ cho execution plan của mọi engine.
12. Chỉ tối ưu dữ liệu và count mà use case thực sự cần; tránh thêm query hoặc projection phức tạp không có lợi ích đo được.

## 16. Checklist hoàn thành

- [ ] Giải thích được vì sao `findAll()` không giới hạn có thể gây tải toàn bảng.
- [ ] Tạo được closed interface projection chỉ gồm các field cần dùng.
- [ ] Tạo được DTO/record projection bằng JPQL constructor expression.
- [ ] Dùng dynamic projection với `Class<T>`.
- [ ] Phân biệt projection và Entity managed.
- [ ] Chọn được `Page`, `Slice` hoặc `List` với `Pageable`.
- [ ] Hiểu khi nào Page cần count query và khi nào Slice tránh count.
- [ ] Dùng `existsBy...` thay cho tải Entity khi chỉ cần kiểm tra tồn tại.
- [ ] Dùng `countBy...` khi nghiệp vụ cần tổng số thật.
- [ ] Viết `countQuery` đúng cho truy vấn có join.
- [ ] Kiểm tra SQL để xác nhận không chọn thừa cột hoặc đếm không cần thiết.
- [ ] Kiểm thử projection, pagination, existence và count bằng `@DataJpaTest`.

Khi hoàn thành, bạn có thể thiết kế truy vấn đọc Spring Data JPA gọn hơn: chỉ lấy đúng dòng, đúng cột và đúng metadata mà use case cần.