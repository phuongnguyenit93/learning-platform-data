# Kiểm thử Page, count query, projection và trường hợp kết quả rỗng

## 1. Mục tiêu kiểm thử truy vấn phân trang

Spring Data JPA cung cấp các kiểu trả về khác nhau cho repository query. Khi một phương thức nhận Pageable, ứng dụng có thể yêu cầu dữ liệu theo trang, giới hạn số bản ghi, sắp xếp và đôi khi cần cả tổng số kết quả.

Một bài kiểm thử phân trang tốt cần xác nhận đồng thời:

- Nội dung của trang đúng với điều kiện lọc và thứ tự sắp xếp.
- Page number, page size và số phần tử thực tế trong trang chính xác.
- totalElements và totalPages phản ánh đúng số hàng phù hợp với điều kiện lọc.
- Count query đếm đúng tập dữ liệu mà truy vấn nội dung trả về.
- Projection ánh xạ đúng trường và kiểu dữ liệu.
- Trường hợp không có kết quả và trường hợp yêu cầu trang vượt quá phạm vi được phân biệt rõ.

Chỉ kiểm tra page.getContent() là chưa đủ. Một trang có thể chứa đúng hai bản ghi nhưng totalElements sai do count query sai; ngược lại count đúng nhưng thứ tự không ổn định khiến test lúc pass lúc fail.

Các ví dụ dưới đây dùng Spring Data JPA với Hibernate, JUnit 5 và AssertJ. Tên package là minh họa; trong dự án, thay bằng package thật của entity và DTO.

## 2. Page, Pageable và Slice khác nhau thế nào?

Ba kiểu trả về thường gặp:

| Kiểu | Nội dung | Thông tin tổng số | Cách xác định còn trang sau |
|---|---|---|---|
| Page<T> | Các phần tử của trang hiện tại | Có totalElements và totalPages | Dựa trên tổng số kết quả |
| Slice<T> | Các phần tử của lát dữ liệu hiện tại | Không có tổng số toàn bộ | Thường lấy thêm một phần tử để biết có trang sau |
| List<T> với Pageable | Danh sách giới hạn theo Pageable | Không có metadata trang | Ứng dụng tự quyết định |

Page<T> hữu ích khi giao diện cần hiển thị “trang 2 trên 8” hoặc tổng số kết quả. Để cung cấp metadata này, Spring Data thường cần count query bổ sung. Tuy nhiên, Spring Data có thể suy ra tổng số từ nội dung trang trong một số trường hợp và bỏ qua việc gọi count supplier, ví dụ trang đầu tiên có ít phần tử hơn page size. Vì vậy, không phải mọi lần gọi Page đều chắc chắn phát sinh COUNT SQL.

Slice<T> phù hợp khi chỉ cần biết có thể tải tiếp hay không. Nó tránh nhu cầu tính tổng số toàn bộ, thường giúp giảm chi phí ở tập dữ liệu lớn. List<T> kết hợp Pageable cũng có thể giới hạn dữ liệu mà không cần metadata tổng số.

Page number trong PageRequest bắt đầu từ 0. Ví dụ PageRequest.of(0, 10) là 10 phần tử đầu; PageRequest.of(1, 10) là trang thứ hai.

## 3. Chuẩn bị entity và repository cho ví dụ

Giả sử ứng dụng quản lý Product với tên, danh mục, mã SKU và giá:

~~~java
package com.example.catalog;

import java.math.BigDecimal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private String category;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    protected Product() {
    }

    public Product(String name, String category, String sku, BigDecimal price) {
        this.name = name;
        this.category = category;
        this.sku = sku;
        this.price = price;
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

    public String getSku() {
        return sku;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

Một interface projection lấy một phần thuộc tính:

~~~java
package com.example.catalog;

import java.math.BigDecimal;

public interface ProductSummary {
    String getName();

    String getSku();

    BigDecimal getPrice();
}
~~~

Một DTO dạng record dùng cho constructor projection:

~~~java
package com.example.catalog;

import java.math.BigDecimal;

public record ProductRow(String name, String sku, BigDecimal price) {
}
~~~

Repository cung cấp truy vấn entity, truy vấn có countQuery tường minh và các dạng projection:

~~~java
package com.example.catalog;

import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository extends JpaRepository<Product, Long> {
    Page<Product> findByCategory(String category, Pageable pageable);

    @Query(
        value = """
            select p
            from Product p
            where p.category = :category
            """,
        countQuery = """
            select count(p)
            from Product p
            where p.category = :category
            """
    )
    Page<Product> searchByCategory(
        @Param("category") String category,
        Pageable pageable
    );

    Page<ProductSummary> findProjectedByCategory(
        String category,
        Pageable pageable
    );

    @Query(
        value = """
            select new com.example.catalog.ProductRow(
                p.name, p.sku, p.price
            )
            from Product p
            where p.category = :category
            """,
        countQuery = """
            select count(p)
            from Product p
            where p.category = :category
            """
    )
    Page<ProductRow> findRowsByCategory(
        @Param("category") String category,
        Pageable pageable
    );

    List<Product> findAllByCategory(String category);
}
~~~

Ví dụ giả định tất cả lớp nằm đúng package đã khai báo và database schema có các cột tương ứng. Với JPQL constructor expression, tên lớp DTO phải là tên fully qualified và thứ tự, kiểu tham số trong constructor phải khớp với các biểu thức SELECT.

## 4. Kiểm thử nội dung trang và metadata

Một test dùng @DataJpaTest có thể inject ProductRepository và TestEntityManager. TestEntityManager giúp chuẩn bị entity, flush SQL và clear persistence context.

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

@DataJpaTest
class ProductRepositoryPageTest {
    @Autowired
    private ProductRepository products;

    @Autowired
    private TestEntityManager entityManager;

    private void insertProducts() {
        entityManager.persist(new Product(
            "A Book", "BOOK", "B-01", new BigDecimal("10.00")
        ));
        entityManager.persist(new Product(
            "B Book", "BOOK", "B-02", new BigDecimal("20.00")
        ));
        entityManager.persist(new Product(
            "C Book", "BOOK", "B-03", new BigDecimal("30.00")
        ));
        entityManager.persist(new Product(
            "D Book", "BOOK", "B-04", new BigDecimal("40.00")
        ));
        entityManager.persist(new Product(
            "E Book", "BOOK", "B-05", new BigDecimal("50.00")
        ));
        entityManager.persist(new Product(
            "Pen", "STATIONERY", "P-01", new BigDecimal("2.00")
        ));

        entityManager.flush();
        entityManager.clear();
    }

    @Test
    void returnsExpectedContentAndPageMetadata() {
        insertProducts();

        Sort sort = Sort.by("name").ascending()
            .and(Sort.by("id").ascending());
        Page<Product> page = products.searchByCategory(
            "BOOK",
            PageRequest.of(0, 2, sort)
        );

        assertThat(page.getContent())
            .extracting(Product::getName)
            .containsExactly("A Book", "B Book");

        assertThat(page.getNumber()).isZero();
        assertThat(page.getSize()).isEqualTo(2);
        assertThat(page.getNumberOfElements()).isEqualTo(2);
        assertThat(page.getTotalElements()).isEqualTo(5);
        assertThat(page.getTotalPages()).isEqualTo(3);
        assertThat(page.isFirst()).isTrue();
        assertThat(page.hasNext()).isTrue();
        assertThat(page.hasPrevious()).isFalse();
    }
}
~~~

Trong ví dụ, page size bằng 2 và có 5 sản phẩm thuộc BOOK. Trang đầu có hai phần tử, tổng số là 5 và tổng số trang là 3.

Các assertion kiểm tra những khía cạnh khác nhau:

- getContent() xác nhận đúng các entity trong trang.
- getNumber() xác nhận chỉ số trang, bắt đầu từ 0.
- getSize() là kích thước trang được yêu cầu.
- getNumberOfElements() là số phần tử thực tế trong trang hiện tại; trang cuối có thể ít hơn page size.
- getTotalElements() là tổng số hàng phù hợp với bộ lọc.
- getTotalPages() là tổng số trang được tính từ tổng số hàng và page size.
- hasNext(), hasPrevious() và isFirst() xác nhận điều hướng.

Nên dùng thứ tự ổn định khi phân trang. Nếu chỉ sort theo name và nhiều hàng có cùng name, thứ tự giữa các hàng trùng tên có thể thay đổi. Thêm khóa duy nhất như id làm tie-breaker giúp test ổn định và giảm nguy cơ một hàng xuất hiện ở hai trang hoặc bị bỏ qua khi dữ liệu thay đổi giữa các lần truy vấn.

## 5. Kiểm thử count query

### 5.1. Count query làm nhiệm vụ gì?

Với Page<T>, ngoài truy vấn lấy nội dung trang, Spring Data có thể chạy một truy vấn đếm để tính totalElements. Ví dụ:

~~~sql
select p
from Product p
where p.category = :category
order by p.name
~~~

Count query tương ứng:

~~~sql
select count(p)
from Product p
where p.category = :category
~~~

Count query phải đếm đúng tập hàng mà truy vấn nội dung đại diện. Các điều kiện lọc phải tương ứng; count query không cần ORDER BY vì thứ tự không ảnh hưởng tổng số.

Khi dùng @Query cho truy vấn phân trang, có thể khai báo countQuery riêng. Đây là cách rõ ràng khi câu truy vấn chính phức tạp hoặc Spring Data không thể tự suy ra câu đếm phù hợp.

### 5.2. Lỗi count query thường gặp

1. **Thiếu điều kiện lọc:** truy vấn nội dung lọc theo category và trạng thái active nhưng count query chỉ lọc category. Khi đó totalElements lớn hơn thực tế.
2. **JOIN làm nhân bản hàng:** một Product có nhiều dòng liên quan trong bảng con. COUNT(p) sau join có thể đếm lặp Product. Khi mục tiêu là đếm entity gốc, có thể cần count(distinct p.id).
3. **Sai kiểu đếm với DISTINCT hoặc GROUP BY:** truy vấn chính trả các nhóm hoặc kết quả distinct nhưng count query lại đếm hàng nguồn. Cần xác định chính xác đơn vị kết quả cần đếm.
4. **Dùng FETCH JOIN trong count query:** count query thường không nên mang fetch join vì mục đích của nó chỉ là đếm. Hãy viết câu count riêng.
5. **Native SQL phức tạp:** Spring Data không phải lúc nào cũng phân tích được câu SQL phức tạp để tạo count query chính xác. Nên khai báo countQuery tường minh.
6. **Count query trả tổng số sai do filter phụ:** nếu query sử dụng tenant, soft-delete, authorization hoặc specification, count phải tuân thủ cùng điều kiện nghiệp vụ.

Ví dụ khi truy vấn join có thể tạo nhiều dòng cho cùng Product:

~~~java
@Query(
    value = """
        select distinct p
        from Product p
        join p.tags t
        where t.name in :tagNames
        """,
    countQuery = """
        select count(distinct p.id)
        from Product p
        join p.tags t
        where t.name in :tagNames
        """
)
Page<Product> findByAnyTag(
    @Param("tagNames") List<String> tagNames,
    Pageable pageable
);
~~~

Ví dụ này giả định Product có quan hệ tags và Tag có thuộc tính name. Nếu nghiệp vụ yêu cầu sản phẩm phải có tất cả tag thay vì bất kỳ tag nào, cả truy vấn nội dung và count query phải được thiết kế lại theo cùng semantics.

### 5.3. Kiểm thử tổng số với custom countQuery

Trong test ở phần trước, trang đầu có đúng hai phần tử và page size cũng bằng hai. Spring Data cần xác định xem còn dữ liệu ở trang tiếp theo hay không và có thể gọi count supplier để hoàn thiện metadata. Assertion totalElements bằng 5 kiểm tra kết quả tổng số mà Page cung cấp.

Có thể kiểm tra thêm trang thứ hai:

~~~java
@Test
void returnsSecondPageWithCorrectTotal() {
    insertProducts();

    Page<Product> page = products.searchByCategory(
        "BOOK",
        PageRequest.of(
            1,
            2,
            Sort.by("name").ascending().and(Sort.by("id").ascending())
        )
    );

    assertThat(page.getContent())
        .extracting(Product::getName)
        .containsExactly("C Book", "D Book");

    assertThat(page.getNumber()).isEqualTo(1);
    assertThat(page.getNumberOfElements()).isEqualTo(2);
    assertThat(page.getTotalElements()).isEqualTo(5);
    assertThat(page.getTotalPages()).isEqualTo(3);
    assertThat(page.hasPrevious()).isTrue();
    assertThat(page.hasNext()).isTrue();
}
~~~

Nếu cần chứng minh chính xác câu COUNT SQL đã được thực thi, chỉ assert totalElements có thể chưa đủ trong mọi trường hợp vì Spring Data có thể suy ra tổng số từ nội dung trang. Hãy dùng SQL logging, Hibernate Statistics hoặc datasource proxy để quan sát câu SQL và số lần thực thi. Với trang đầy đủ như ví dụ, count supplier thường cần được gọi; tuy nhiên tối ưu hóa của framework vẫn phụ thuộc hình dạng trang và phiên bản.

### 5.4. Native query và countQuery

Với native SQL, khai báo rõ countQuery đặc biệt hữu ích:

~~~java
@Query(
    value = """
        select p.*
        from products p
        where p.category = :category
        order by p.name
        """,
    countQuery = """
        select count(*)
        from products p
        where p.category = :category
        """,
    nativeQuery = true
)
Page<Product> findNativePage(
    @Param("category") String category,
    Pageable pageable
);
~~~

Tên bảng và cột phải khớp schema thật. Việc áp dụng Sort từ Pageable vào native query có giới hạn phụ thuộc phiên bản Spring Data và khả năng phân tích SQL. Với câu native phức tạp, nên viết ORDER BY rõ ràng hoặc kiểm tra kỹ cách framework bổ sung phân trang và sắp xếp.

## 6. Kiểm thử interface projection

Projection cho phép repository chỉ trả các thuộc tính cần dùng thay vì tải toàn bộ entity. Interface projection thường khai báo getter có tên khớp với thuộc tính entity.

Ví dụ ProductSummary:

~~~java
public interface ProductSummary {
    String getName();

    String getSku();

    BigDecimal getPrice();
}
~~~

Repository có phương thức:

~~~java
Page<ProductSummary> findProjectedByCategory(
    String category,
    Pageable pageable
);
~~~

Bài test:

~~~java
@Test
void returnsInterfaceProjectionForRequestedPage() {
    insertProducts();

    Page<ProductSummary> page = products.findProjectedByCategory(
        "BOOK",
        PageRequest.of(0, 2, Sort.by("name").ascending())
    );

    assertThat(page.getContent()).hasSize(2);
    assertThat(page.getContent())
        .extracting(ProductSummary::getName)
        .containsExactly("A Book", "B Book");
    assertThat(page.getContent())
        .extracting(ProductSummary::getSku)
        .containsExactly("B-01", "B-02");
    assertThat(page.getTotalElements()).isEqualTo(5);
}
~~~

Các điều cần xác nhận:

- Getter có tên đúng với property mà projection cần đọc.
- Kiểu trả về tương thích với kiểu thuộc tính entity.
- Projection chỉ chứa các trường cần thiết cho use case.
- Metadata Page vẫn đúng; projection không làm mất yêu cầu count query.
- Sắp xếp sử dụng property hợp lệ và tạo thứ tự ổn định.

Interface projection có thể được Spring Data triển khai bằng proxy. Khi dùng nested projection hoặc open projection có SpEL, câu SQL thực tế có thể cần thêm dữ liệu hoặc thực hiện cách ánh xạ khác. Không nên kết luận projection luôn chỉ SELECT đúng các cột getter nếu chưa quan sát SQL thực tế.

## 7. Kiểm thử DTO/class-based projection

DTO projection trả về một kiểu dữ liệu cụ thể thay vì proxy interface. Với JPQL, có thể dùng constructor expression:

~~~java
select new com.example.catalog.ProductRow(
    p.name, p.sku, p.price
)
from Product p
where p.category = :category
~~~

Constructor hoặc record canonical constructor phải có thứ tự và kiểu tham số khớp với biểu thức SELECT. Nếu tên class hoặc chữ ký constructor sai, query có thể thất bại khi thực thi.

Test:

~~~java
@Test
void returnsDtoProjectionAndCorrectCount() {
    insertProducts();

    Page<ProductRow> page = products.findRowsByCategory(
        "BOOK",
        PageRequest.of(0, 2, Sort.by("name").ascending())
    );

    assertThat(page.getContent()).hasSize(2);
    assertThat(page.getContent())
        .extracting(ProductRow::name)
        .containsExactly("A Book", "B Book");
    assertThat(page.getContent())
        .extracting(ProductRow::sku)
        .containsExactly("B-01", "B-02");
    assertThat(page.getTotalElements()).isEqualTo(5);
}
~~~

Test DTO cần xác nhận cả dữ liệu từng trường lẫn metadata trang. Một DTO có thể nhận đúng tên nhưng sai thứ tự price/sku nếu constructor expression không khớp; assertion từng trường sẽ phát hiện lỗi này.

Với native query, mapping DTO có thể cần constructor mapping hoặc projection interface với alias cột đúng. Không giả định JPQL constructor expression có thể áp dụng nguyên xi cho mọi native query.

## 8. Kiểm thử trường hợp kết quả rỗng

Có hai tình huống dễ bị nhầm:

1. Không có bản ghi nào thỏa điều kiện lọc.
2. Có bản ghi thỏa điều kiện nhưng trang được yêu cầu nằm ngoài phạm vi dữ liệu.

Cả hai đều có thể trả content rỗng, nhưng totalElements khác nhau.

~~~java
@Test
void distinguishesNoMatchesFromOutOfRangePage() {
    insertProducts();

    Page<Product> noMatches = products.searchByCategory(
        "TOY",
        PageRequest.of(0, 2)
    );

    assertThat(noMatches.getContent()).isEmpty();
    assertThat(noMatches.getTotalElements()).isZero();
    assertThat(noMatches.getTotalPages()).isZero();
    assertThat(noMatches.hasNext()).isFalse();

    Page<Product> outOfRange = products.searchByCategory(
        "BOOK",
        PageRequest.of(3, 2)
    );

    assertThat(outOfRange.getContent()).isEmpty();
    assertThat(outOfRange.getTotalElements()).isEqualTo(5);
    assertThat(outOfRange.getTotalPages()).isEqualTo(3);
    assertThat(outOfRange.hasNext()).isFalse();
}
~~~

Trong ví dụ, 5 sản phẩm BOOK với page size 2 tạo ra 3 trang hợp lệ có chỉ số 0, 1 và 2. Yêu cầu trang 3 là vượt phạm vi. Nội dung rỗng nhưng totalElements vẫn bằng 5 nếu count query được tính đúng.

Với một truy vấn không có kết quả, Page thường có content rỗng, totalElements bằng 0 và totalPages bằng 0. Đây là kết quả bình thường, không phải lỗi repository.

### 8.1. List, Optional và projection khi không có kết quả

Các kiểu trả về khác có semantics riêng:

- Repository method trả List<T> thường trả danh sách rỗng khi không có hàng phù hợp, không nên trả null.
- Method trả Optional<T> biểu thị rõ có hoặc không có một kết quả.
- Method trả entity đơn có thể trả null khi không tìm thấy, tùy kiểu method.
- Projection Page hoặc Slice vẫn có thể có content rỗng và metadata tương ứng.
- DTO projection cũng cần kiểm thử trường hợp không có hàng; không nên chỉ kiểm tra đường có dữ liệu.

Ví dụ test List và Optional:

~~~java
@Test
void returnsEmptyCollectionAndOptionalWhenNoProductMatches() {
    insertProducts();

    assertThat(products.findAllByCategory("TOY")).isEmpty();
    assertThat(products.findBySku("UNKNOWN")).isEmpty();
}
~~~

Test này giả định repository có thêm phương thức findBySku(String sku) trả Optional<Product>. Có thể thêm khai báo sau vào ProductRepository:

~~~java
import java.util.Optional;

Optional<Product> findBySku(String sku);
~~~

Không nên dùng một assertion duy nhất kiểu result is not null. Với collection hãy assert empty; với Optional hãy assert isEmpty; với Page hãy kiểm tra cả content và metadata.

### 8.2. Trường hợp `out-of-range`: yêu cầu trang vượt phạm vi

`out-of-range` là trường hợp bộ lọc vẫn có dữ liệu nhưng `PageRequest` yêu cầu một trang nằm sau trang cuối cùng. Ví dụ có 5 sản phẩm phù hợp và page size bằng 2 thì `totalPages` bằng 3, với các chỉ số trang hợp lệ là 0, 1 và 2. Khi gọi `PageRequest.of(3, 2)`, `Page.getContent()` phải là danh sách rỗng; `totalElements` vẫn bằng 5, `totalPages` vẫn bằng 3 và `hasNext()` là false. Đây khác với truy vấn không có bản ghi phù hợp, nơi `totalElements` và `totalPages` đều bằng 0.

Có thể thêm assertion sau vào repository test đã chuẩn bị 5 sản phẩm BOOK:

~~~java
Page<Product> beyondLastPage = products.searchByCategory(
    "BOOK",
    PageRequest.of(3, 2, Sort.by("name").ascending().and(Sort.by("id").ascending()))
);

assertThat(beyondLastPage.getContent()).isEmpty();
assertThat(beyondLastPage.getTotalElements()).isEqualTo(5);
assertThat(beyondLastPage.getTotalPages()).isEqualTo(3);
assertThat(beyondLastPage.getNumber()).isEqualTo(3);
assertThat(beyondLastPage.hasNext()).isFalse();
~~~

Khi cần total metadata cho một trang rỗng nằm ngoài phạm vi, Spring Data có thể phải gọi count supplier để xác định tổng số hàng. Hãy kiểm tra count query và các assertion trên cùng nhau để phân biệt chính xác `out-of-range` với trường hợp không có kết quả.

### 8.3. Dùng Testcontainers để xác minh semantics trên database production

`Testcontainers` là một lựa chọn integration test tùy chọn khi embedded database như H2 không phản ánh đầy đủ hành vi của database production. Có thể chạy chính repository test trên engine thật, ví dụ PostgreSQL hoặc MySQL, để kiểm tra native SQL, kiểu dữ liệu, phân trang, custom `countQuery`, interface projection và DTO projection.

Với Spring Boot 3.1+, có thể khai báo container bằng `@Container` và `@ServiceConnection`; với phiên bản cũ hơn, dùng `@DynamicPropertySource` để cung cấp JDBC URL, username và password. Khi muốn giữ DataSource do container cung cấp, cấu hình `@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)`. Chạy lại các test Page, count query và projection trên container giúp phát hiện khác biệt dialect/driver mà embedded database có thể không thể hiện. Testcontainers là đường kiểm thử bổ sung cho semantics cần tương đồng production, không bắt buộc cho mọi repository slice test.


## 9. Kiểm thử Sort và tính ổn định giữa các trang

Pagination dựa trên offset/page number có thể gặp kết quả khó đoán nếu thứ tự không xác định. Nếu nhiều hàng có cùng giá trị sort, database không bảo đảm thứ tự giữa các hàng đó khi không có tiêu chí phụ duy nhất.

Ví dụ:

~~~java
PageRequest.of(
    0,
    2,
    Sort.by("name").ascending()
        .and(Sort.by("id").ascending())
);
~~~

Khi test, nên:

- Chọn dữ liệu có giá trị sort phân biệt nếu chỉ kiểm tra thứ tự cơ bản.
- Hoặc thêm id làm tie-breaker khi tên có thể trùng.
- Kiểm tra cả trang đầu và trang tiếp theo để phát hiện trùng/lọt hàng.
- Dùng property Java entity trong Sort, không mặc định dùng tên cột SQL nếu mapping có @Column khác tên.
- Kiểm tra sort direction ASC/DESC và nhiều tiêu chí nếu repository hỗ trợ.

Ví dụ kiểm tra hai trang liền nhau không trùng sản phẩm:

~~~java
@Test
void consecutivePagesContainDifferentProductsInStableOrder() {
    insertProducts();

    Sort sort = Sort.by("name").ascending()
        .and(Sort.by("id").ascending());

    Page<Product> first = products.findByCategory(
        "BOOK", PageRequest.of(0, 2, sort)
    );
    Page<Product> second = products.findByCategory(
        "BOOK", PageRequest.of(1, 2, sort)
    );

    assertThat(first.getContent())
        .extracting(Product::getSku)
        .containsExactly("B-01", "B-02");

    assertThat(second.getContent())
        .extracting(Product::getSku)
        .containsExactly("B-03", "B-04");
}
~~~

Offset pagination vẫn có thể dịch chuyển kết quả nếu dữ liệu được thêm/xóa giữa các request của người dùng. Với tập dữ liệu lớn hoặc thay đổi thường xuyên, cân nhắc keyset/scrolling pagination mà phiên bản Spring Data hỗ trợ. Test keyset cần xác nhận cursor, thứ tự duy nhất và ranh giới trang; không thể thay bằng assertion Page.totalElements vì keyset thường phục vụ một mô hình đọc khác.

## 10. Flush, clear và transaction trong repository test

@DataJpaTest thường chạy mỗi test method trong một transaction và rollback khi kết thúc. Đây là môi trường thuận tiện để tạo dữ liệu rồi truy vấn mà không làm bẩn database test.

Tuy nhiên, persistence context có first-level cache. Nếu test persist entity rồi truy vấn ngay, Hibernate có thể trả instance đang được quản lý hoặc chưa phát SQL ở thời điểm mà người viết nghĩ. Để kiểm tra database query thực sự, hãy flush và clear:

- flush(): buộc các thay đổi đang chờ được đồng bộ xuống database.
- clear(): detach toàn bộ entity đang được quản lý, tránh lấy lại instance từ L1.
- Repository query sau đó phải thực hiện công việc đọc theo transaction và cache semantics thực tế.

Ví dụ:

~~~java
entityManager.persist(new Product(
    "A Book", "BOOK", "B-01", new BigDecimal("10.00")
));
entityManager.flush();
entityManager.clear();

Page<Product> page = products.findByCategory(
    "BOOK", PageRequest.of(0, 10)
);
~~~

Flush không commit. Test transaction vẫn rollback khi test kết thúc, trừ khi cấu hình @Commit hoặc @Rollback(false) thay đổi hành vi.

Nếu cần kiểm tra count query, hãy quan sát SQL bằng Hibernate SQL logging, Statistics hoặc datasource proxy. Không nên dựa vào số lần gọi method repository để suy ra số câu SQL.

## 11. Kiểm tra SQL và count query thực tế

Có thể bật Hibernate statistics trong cấu hình test:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Hoặc đặt property trên test:

~~~java
@DataJpaTest(properties = {
    "spring.jpa.properties.hibernate.generate_statistics=true"
})
class ProductRepositoryPageTest {
}
~~~

Để quan sát query, có thể bật log SQL phù hợp với phiên bản Hibernate:

~~~properties
spring.jpa.show-sql=true
logging.level.org.hibernate.SQL=DEBUG
~~~

Nếu cần xem bind parameter, logger và package thay đổi giữa Hibernate 5 và Hibernate 6; hãy đối chiếu phiên bản thực tế. Không nên bật log bind parameter trong môi trường có dữ liệu nhạy cảm.

Khi xác minh Page query, hãy quan sát hai dạng SQL:

1. SELECT lấy content có LIMIT/OFFSET hoặc cú pháp phân trang tương ứng của database.
2. SELECT COUNT(...) tính tổng số hàng phù hợp với filter.

Một số trường hợp framework có thể không chạy COUNT vì suy ra tổng số từ page content. Nếu mục tiêu là xác minh custom countQuery, hãy thiết kế dữ liệu và page request khiến count cần thiết, rồi kiểm tra log/metrics. Assertion totalElements vẫn cần có trong test để kiểm tra kết quả metadata.

## 12. Lỗi thường gặp khi test Page, count và projection

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Content đúng nhưng totalElements sai | Count query thiếu điều kiện hoặc đếm trùng do JOIN | Viết countQuery tương ứng; cân nhắc count(distinct p.id) |
| Trang cuối có ít phần tử hơn page size | Không phải lỗi; đây là hành vi bình thường | Assert numberOfElements theo dữ liệu, không bắt buộc bằng size |
| Trang ngoài phạm vi có content rỗng | Page index vượt tổng số trang | Kiểm tra totalElements và totalPages để phân biệt với không có kết quả |
| Kết quả giữa các lần chạy đổi thứ tự | Sort không có tiêu chí duy nhất | Thêm id hoặc khóa duy nhất làm tie-breaker |
| Projection getter trả null | Tên getter không khớp property hoặc alias native query sai | Kiểm tra mapping, alias và kiểu dữ liệu |
| DTO query lỗi constructor | Fully qualified class hoặc thứ tự/kiểu tham số không khớp | Đối chiếu constructor expression với record/class |
| Native Page query lỗi hoặc count sai | Framework không suy ra được count SQL phức tạp | Khai báo countQuery tường minh |
| Không thấy COUNT SQL | Spring Data tối ưu và suy ra total từ content | Dùng page request/dữ liệu cần count; quan sát SQL/metrics |
| Test không thấy SQL SELECT như mong đợi | Entity còn trong persistence context hoặc cache | Flush/clear và kiểm soát cache |
| Test chạy trên H2 pass nhưng production fail | Khác biệt dialect, native SQL, kiểu dữ liệu hoặc pagination | Chạy integration test trên đúng engine production |

## 13. Checklist cho một test repository phân trang đáng tin cậy

Trước khi hoàn tất test, hãy xác nhận:

1. Dữ liệu chuẩn bị có số hàng và giá trị đủ để kiểm tra nhiều trang.
2. Pageable có page index, page size và sort rõ ràng.
3. Thứ tự sort ổn định, tốt nhất có khóa duy nhất làm tiêu chí phụ.
4. Assertion kiểm tra content, number, size, numberOfElements, totalElements và totalPages.
5. Custom @Query có countQuery tương ứng khi cần; count không bị nhân bản do join.
6. Projection test kiểm tra từng trường cần thiết và metadata Page.
7. Trường hợp không có kết quả được phân biệt với trang ngoài phạm vi.
8. Dữ liệu được flush/clear khi cần xác minh truy vấn database.
9. Count SQL được quan sát khi mục tiêu test yêu cầu chứng minh câu COUNT thực sự chạy.
10. Native query và database-specific behavior được kiểm thử trên database phù hợp với production.

Kiểm thử Page, count query, projection và kết quả rỗng cần xác nhận cả dữ liệu trả về lẫn metadata mà Spring Data xây dựng. Khi kiểm tra đúng count semantics, projection mapping, thứ tự ổn định và các trường hợp rỗng, repository test sẽ phát hiện được nhiều lỗi mà việc chỉ assert danh sách content không thể thấy.