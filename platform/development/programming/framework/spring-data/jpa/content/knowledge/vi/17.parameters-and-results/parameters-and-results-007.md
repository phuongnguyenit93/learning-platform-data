# Truy vấn vô hướng và ánh xạ giá trị tổng hợp

JPQL không chỉ trả về toàn bộ Entity. Một truy vấn có thể chọn một thuộc tính đơn lẻ, một biểu thức tính toán hoặc kết quả của hàm tổng hợp như COUNT, SUM, AVG, MIN và MAX. Những kết quả này được gọi là kết quả vô hướng (scalar result): mỗi dòng trả về một giá trị hoặc một nhóm giá trị thay vì một Entity hoàn chỉnh.

Trong Spring Data JPA, kiểu trả về của phương thức Repository phải phù hợp với kiểu kết quả mà JPQL tạo ra. Nếu SELECT một giá trị, có thể trả về kiểu Java tương ứng như Long, BigDecimal hoặc String. Nếu SELECT nhiều giá trị, nên ánh xạ bằng interface projection hoặc DTO constructor expression thay vì để Object[] lan rộng khắp ứng dụng.

## 1. Truy vấn vô hướng là gì?

Truy vấn Entity thông thường chọn một Entity:

~~~java
@Query("select p from Product p where p.id = :id")
Optional<Product> findProduct(@Param("id") Long id);
~~~

Truy vấn vô hướng chọn một thuộc tính hoặc biểu thức:

~~~java
@Query("select p.name from Product p where p.id = :id")
Optional<String> findProductName(@Param("id") Long id);
~~~

~~~java
@Query("select p.price from Product p where p.id = :id")
Optional<BigDecimal> findProductPrice(@Param("id") Long id);
~~~

Trong hai ví dụ sau, kết quả không phải Product. JPQL chỉ trả về giá trị của thuộc tính name hoặc price. Vì vậy, kiểu trả về phải là String hoặc BigDecimal tương ứng.

Một truy vấn vô hướng có thể trả về nhiều dòng:

~~~java
@Query("select p.name from Product p where p.active = true order by p.name")
List<String> findActiveProductNames();
~~~

Mỗi phần tử trong List là một giá trị String. Nếu không có dòng phù hợp, danh sách rỗng.

## 2. Kiểu trả về phải khớp với biểu thức SELECT

Khi thiết kế phương thức Repository, hãy xác định biểu thức SELECT trả về kiểu Java nào.

| Biểu thức JPQL | Kiểu kết quả thường dùng |
|---|---|
| select p.name | String |
| select p.id | Kiểu Java của ID, ví dụ Long |
| select p.price | BigDecimal nếu thuộc tính là BigDecimal |
| select count(p) | Long |
| select avg(p.price) | Double |
| select sum(p.price) | BigDecimal nếu price là BigDecimal |
| select min(p.createdAt) | Kiểu của thuộc tính createdAt |
| select max(p.createdAt) | Kiểu của thuộc tính createdAt |

Ví dụ:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query("select count(p) from Product p where p.active = true")
    long countActiveProducts();

    @Query("select max(p.price) from Product p")
    Optional<BigDecimal> findHighestPrice();

    @Query("select avg(p.price) from Product p")
    Optional<Double> findAveragePrice();
}
~~~

COUNT luôn trả về Long theo quy tắc JPQL. Nếu dùng kiểu primitive long trong phương thức Repository, giá trị đếm luôn có kết quả số, kể cả khi không có dòng phù hợp (kết quả là 0).

AVG trả về Double theo quy tắc JPQL, kể cả khi biểu thức đầu vào là kiểu số thập phân. MIN và MAX trả về kiểu của biểu thức được tổng hợp. SUM có kiểu kết quả phụ thuộc kiểu số đầu vào; các trường hợp thường gặp được trình bày ở phần tiếp theo.

Không nên chọn kiểu trả về chỉ dựa vào kiểu cột SQL. Hãy dựa vào kiểu Java của thuộc tính Entity và quy tắc kiểu kết quả JPQL.

## 3. Các hàm tổng hợp cơ bản

JPQL hỗ trợ các hàm tổng hợp thường dùng:

- COUNT: đếm số giá trị hoặc Entity.
- SUM: tính tổng các giá trị số.
- AVG: tính trung bình cộng.
- MIN: tìm giá trị nhỏ nhất.
- MAX: tìm giá trị lớn nhất.

Ví dụ với Entity Product có thuộc tính price kiểu BigDecimal và active kiểu boolean:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query("select count(p) from Product p")
    Long countAllProducts();

    @Query("select sum(p.price) from Product p")
    Optional<BigDecimal> sumAllPrices();

    @Query("select avg(p.price) from Product p")
    Optional<Double> averagePrice();

    @Query("select min(p.price) from Product p")
    Optional<BigDecimal> minimumPrice();

    @Query("select max(p.price) from Product p")
    Optional<BigDecimal> maximumPrice();
}
~~~

Các chữ ký trên minh họa kiểu kết quả của JPQL. Với SUM, AVG, MIN và MAX, nếu không có dữ liệu phù hợp, kết quả có thể là null; trong ứng dụng thực tế nên dùng wrapper hoặc Optional để thể hiện khả năng vắng mặt, hoặc dùng COALESCE nếu nghiệp vụ quy định giá trị thay thế.

### COUNT

COUNT đếm số kết quả phù hợp:

~~~java
@Query("""
    select count(p)
    from Product p
    where p.active = true
    """)
long countActiveProducts();
~~~

COUNT trả về Long. Nếu không có sản phẩm active, kết quả là 0 chứ không phải null.

COUNT có thể dùng DISTINCT:

~~~java
@Query("""
    select count(distinct p.category.id)
    from Product p
    """)
Long countDistinctCategoriesWithProducts();
~~~

Truy vấn này đếm số danh mục khác nhau xuất hiện trong các Product. Danh mục không có sản phẩm sẽ không được tính vì truy vấn bắt đầu từ Product.

### SUM

SUM tính tổng các giá trị số:

~~~java
@Query("""
    select sum(p.price)
    from Product p
    where p.active = true
    """)
Optional<BigDecimal> sumActiveProductPrices();
~~~

Với thuộc tính BigDecimal, SUM trả về BigDecimal. Nếu không có giá trị để cộng, kết quả là null.

### AVG

AVG tính giá trị trung bình và trả về Double:

~~~java
@Query("select avg(p.price) from Product p")
Optional<Double> averageProductPrice();
~~~

Nếu cần kết quả tiền tệ với quy tắc làm tròn cụ thể, hãy xác định rõ cách chuyển đổi và scale ở tầng nghiệp vụ. Không nên ép kiểu trung bình sang BigDecimal mà bỏ qua quy tắc làm tròn.

### MIN và MAX

MIN/MAX trả về kiểu của biểu thức đầu vào:

~~~java
@Query("select min(p.createdAt) from Product p")
Optional<Instant> findFirstProductCreatedAt();

@Query("select max(p.price) from Product p")
Optional<BigDecimal> findHighestProductPrice();
~~~

Có thể dùng với số, ngày giờ và các kiểu có thứ tự so sánh phù hợp theo JPA/provider/database.

## 4. Kiểu kết quả chính xác của SUM

Theo quy tắc JPQL, kiểu trả về của SUM phụ thuộc kiểu số của biểu thức:

| Kiểu thuộc tính đầu vào | Kiểu kết quả SUM |
|---|---|
| Byte, Short, Integer, Long và các kiểu số nguyên tương ứng | Long |
| Float, Double | Double |
| BigInteger | BigInteger |
| BigDecimal | BigDecimal |

COUNT trả về Long; AVG trả về Double; MIN và MAX giữ kiểu của biểu thức được tổng hợp.

Điều này quan trọng khi khai báo kiểu trả về Repository hoặc constructor DTO. Ví dụ nếu Product.quantity là Integer, truy vấn SUM(p.quantity) trả về Long, không phải Integer:

~~~java
@Query("select sum(p.quantity) from Product p")
Long sumAllQuantities();
~~~

Nếu khai báo phương thức trả Integer, có thể gặp lỗi chuyển đổi kiểu hoặc lỗi lúc thực thi tùy cách provider xử lý. Hãy dùng đúng kiểu theo đặc tả JPQL.

## 5. NULL và kết quả khi không có dữ liệu

Các hàm tổng hợp có hành vi khác nhau khi tập dữ liệu rỗng:

| Hàm | Khi không có giá trị phù hợp |
|---|---|
| COUNT | 0 |
| SUM | NULL |
| AVG | NULL |
| MIN | NULL |
| MAX | NULL |

Ví dụ:

~~~java
Long count = repository.countActiveProducts(); // 0 nếu không có sản phẩm
Optional<BigDecimal> total = repository.sumActiveProductPrices(); // empty nếu SUM là NULL
~~~

COUNT trả 0 vì số lượng phần tử của tập rỗng là 0. Các hàm SUM, AVG, MIN và MAX trả NULL khi không có giá trị đầu vào để tính.

Cũng cần phân biệt hai trường hợp:
- Không có Entity thỏa WHERE.
- Có Entity nhưng thuộc tính được tổng hợp là NULL.

Với SUM/AVG/MIN/MAX, cả hai trường hợp đều có thể tạo kết quả NULL nếu không còn giá trị không-null để tổng hợp. Nếu cần phân biệt, hãy truy vấn thêm COUNT hoặc kiểm tra Entity/dữ liệu theo yêu cầu nghiệp vụ.

### Dùng COALESCE để thay NULL

Nếu nghiệp vụ quy định tổng tiền không có dữ liệu được xem là 0, có thể dùng COALESCE:

~~~java
@Query("""
    select coalesce(sum(p.price), :zero)
    from Product p
    where p.active = true
    """)
BigDecimal sumActivePricesOrZero(
        @Param("zero") BigDecimal zero
);
~~~

Gọi phương thức với BigDecimal.ZERO:

~~~java
BigDecimal total =
        repository.sumActivePricesOrZero(BigDecimal.ZERO);
~~~

COALESCE trả về giá trị đầu tiên không-null. Tham số zero cần có kiểu tương thích với kiểu kết quả SUM. Cách khác là nhận Optional<BigDecimal> rồi dùng orElse(BigDecimal.ZERO) ở service nếu muốn giữ rõ ranh giới giữa dữ liệu và quy tắc nghiệp vụ.

## 6. Biểu thức vô hướng và CASE

SELECT có thể trả về biểu thức thay vì một thuộc tính trực tiếp. JPQL hỗ trợ biểu thức số học, hàm chuỗi, hàm ngày giờ và CASE theo phạm vi của đặc tả/provider.

Ví dụ tính giá sau giảm:

~~~java
@Query("""
    select p.price * (1 - p.discountRate)
    from Product p
    where p.id = :id
    """)
Optional<BigDecimal> findDiscountedPrice(@Param("id") Long id);
~~~

Ví dụ CASE phân loại sản phẩm theo giá:

~~~java
@Query("""
    select case
        when p.price >= :premiumThreshold then 'PREMIUM'
        when p.price >= :standardThreshold then 'STANDARD'
        else 'BUDGET'
    end
    from Product p
    """)
List<String> classifyProducts(
        @Param("premiumThreshold") BigDecimal premiumThreshold,
        @Param("standardThreshold") BigDecimal standardThreshold
);
~~~

Kiểu trả về của biểu thức CASE phải nhất quán và tương thích với các nhánh kết quả. Nếu các nhánh trả về kiểu khác nhau, provider có thể không xác định được kiểu kết quả phù hợp.

Với biểu thức số học, cần chú ý kiểu toán hạng và phép chia. Nếu cần độ chính xác tiền tệ, hãy kiểm soát kiểu BigDecimal, scale và làm tròn ở tầng nghiệp vụ.

## 7. GROUP BY: tổng hợp theo từng nhóm

Nếu muốn tính tổng hợp riêng cho từng danh mục, dùng GROUP BY. Ví dụ đếm số sản phẩm trong từng Category:

~~~java
@Query("""
    select c.name, count(p)
    from Category c
    left join c.products p
    group by c.id, c.name
    order by c.name
    """)
List<Object[]> countProductsByCategory();
~~~

Mỗi dòng kết quả có hai phần tử:
- Phần tử thứ nhất là tên Category (String).
- Phần tử thứ hai là số Product (Long).

LEFT JOIN giúp danh mục chưa có sản phẩm vẫn xuất hiện; COUNT(p) cho nhóm đó bằng 0. Nếu dùng INNER JOIN, danh mục không có sản phẩm sẽ bị loại khỏi kết quả.

Trong JPQL, các biểu thức được chọn mà không nằm trong hàm tổng hợp thường phải xuất hiện trong GROUP BY. Ở ví dụ này, c.name được chọn nên c.id và c.name được nhóm để tạo một nhóm cho mỗi danh mục theo định danh và tên.

Không nên chọn toàn bộ Entity cùng với một aggregate tùy tiện nếu không có GROUP BY phù hợp. Hãy chọn đúng thuộc tính nhóm và các giá trị tổng hợp cần trả về.

## 8. HAVING: lọc sau khi đã nhóm

WHERE lọc các dòng trước khi nhóm; HAVING lọc các nhóm sau khi áp dụng GROUP BY và hàm tổng hợp.

Ví dụ chỉ lấy danh mục có ít nhất 5 sản phẩm:

~~~java
@Query("""
    select c.name, count(p)
    from Category c
    left join c.products p
    group by c.id, c.name
    having count(p) >= :minimumCount
    order by c.name
    """)
List<Object[]> findCategoriesWithEnoughProducts(
        @Param("minimumCount") Long minimumCount
);
~~~

Phân biệt:

~~~sql
WHERE p.active = true
GROUP BY c.id, c.name
HAVING COUNT(p) >= 5
~~~

- WHERE loại sản phẩm không active trước khi tính COUNT.
- GROUP BY gom các dòng còn lại theo danh mục.
- HAVING chỉ giữ các nhóm có số sản phẩm đạt ngưỡng.

Nếu điều kiện chỉ liên quan đến thuộc tính từng dòng, ưu tiên WHERE. Nếu điều kiện dựa trên COUNT, SUM, AVG hoặc kết quả tổng hợp của nhóm, dùng HAVING.

## 9. Ánh xạ nhiều giá trị bằng Object[]

JPQL có thể SELECT nhiều biểu thức:

~~~java
@Query("""
    select p.category.name, count(p), max(p.price)
    from Product p
    group by p.category.id, p.category.name
    """)
List<Object[]> getCategoryStatistics();
~~~

Mỗi Object[] chứa các phần tử theo đúng thứ tự trong SELECT:
- index 0: category.name, kiểu String.
- index 1: count(p), kiểu Long.
- index 2: max(p.price), kiểu BigDecimal nếu price là BigDecimal.

Cách này đơn giản nhưng có nhược điểm:
- Mã gọi phải nhớ thứ tự index.
- Dễ ép kiểu sai.
- Khi thêm hoặc đổi một biểu thức SELECT, nhiều nơi sử dụng có thể bị ảnh hưởng.
- Ý nghĩa của từng giá trị không rõ khi đọc code.

Nếu chỉ có một truy vấn nội bộ nhỏ, Object[] có thể chấp nhận được. Với kết quả dùng trong service/API hoặc được nhiều nơi sử dụng, hãy ưu tiên projection hoặc DTO.

## 10. Interface projection cho kết quả tổng hợp

Spring Data JPA hỗ trợ interface projection. Mỗi getter tương ứng với alias của một biểu thức SELECT.

Projection:

~~~java
public interface CategoryStatistics {
    String getCategoryName();
    Long getProductCount();
    BigDecimal getHighestPrice();
}
~~~

Repository:

~~~java
@Query("""
    select c.name as categoryName,
           count(p) as productCount,
           max(p.price) as highestPrice
    from Category c
    left join c.products p
    group by c.id, c.name
    order by c.name
    """)
List<CategoryStatistics> findCategoryStatistics();
~~~

Alias phải khớp tên property mà projection mong đợi. Ví dụ categoryName ánh xạ tới getCategoryName(). Các kiểu getter cần tương thích với kiểu biểu thức: COUNT là Long, MAX(price) là kiểu của price.

Projection phù hợp khi:
- Chỉ cần một tập con dữ liệu.
- Muốn tên thuộc tính rõ ràng thay vì index của Object[].
- Kết quả chỉ phục vụ đọc và không cần quản lý như Entity.

Không dùng projection như một Entity có thể sửa và persist. Đây là cấu trúc kết quả đọc.

## 11. DTO constructor expression

JPQL hỗ trợ constructor expression để tạo DTO trực tiếp từ SELECT. DTO cần constructor có tham số tương ứng với thứ tự và kiểu của biểu thức.

DTO:

~~~java
package com.example.catalog.dto;

import java.math.BigDecimal;

public record CategoryStatisticsDto(
        String categoryName,
        Long productCount,
        BigDecimal highestPrice
) {
}
~~~

Repository:

~~~java
@Query("""
    select new com.example.catalog.dto.CategoryStatisticsDto(
        c.name,
        count(p),
        max(p.price)
    )
    from Category c
    left join c.products p
    group by c.id, c.name
    order by c.name
    """)
List<CategoryStatisticsDto> findCategoryStatisticsDto();
~~~

Trong constructor expression:
- Từ khóa new phải được theo sau bởi tên lớp DTO đầy đủ (fully qualified class name).
- Thứ tự đối số phải khớp constructor.
- count(p) là Long.
- max(p.price) có kiểu của thuộc tính price.

DTO constructor projection giúp kiểm tra kiểu rõ ràng và phù hợp khi kết quả cần đi qua service hoặc API. Record Java 17 có canonical constructor nên thường thuận tiện cho DTO chỉ đọc.

## 12. Tổng hợp có JOIN và tránh đếm trùng

Khi kết hợp nhiều quan hệ one-to-many, JOIN có thể nhân bản dòng. Ví dụ một Customer có nhiều Order và mỗi Order có nhiều OrderItem. Nếu JOIN cả hai collection rồi COUNT Order, một Order có nhiều item có thể bị đếm nhiều lần.

Ví dụ cần đếm số đơn hàng của từng khách hàng:

~~~java
@Query("""
    select c.id, count(distinct o.id)
    from Customer c
    left join c.orders o
    left join o.items i
    group by c.id
    """)
List<Object[]> countCustomerOrders();
~~~

COUNT(DISTINCT o.id) đếm mỗi Order một lần dù JOIN tạo nhiều dòng cho Order đó.

Hãy xác định cấp độ mà bạn muốn đếm:
- COUNT(p): đếm các Entity/dòng phù hợp sau join.
- COUNT(DISTINCT p.id): đếm Entity duy nhất.
- COUNT(i.id): đếm các phần tử con.
- SUM(i.quantity): tổng số lượng của các dòng con.

Đừng thêm DISTINCT một cách máy móc. DISTINCT có chi phí và chỉ nên dùng khi cần loại trùng theo đúng ngữ nghĩa. Nếu có thể, hãy viết query chỉ JOIN những quan hệ cần thiết.

## 13. Trả về Page cho truy vấn tổng hợp

Truy vấn nhóm có thể trả về Page<Projection> hoặc Page<DTO> nếu Spring Data xác định được count query phù hợp. Với GROUP BY/HAVING phức tạp, nên khai báo countQuery riêng và bảo đảm nó đếm số nhóm được trả về, không phải số dòng nguồn sau JOIN.

Ví dụ về cấu trúc:

~~~java
@Query(
    value = """
        select c.name as categoryName,
               count(p) as productCount
        from Category c
        left join c.products p
        group by c.id, c.name
        having count(p) >= :minimumCount
        """,
    countQuery = """
        select count(c.id)
        from Category c
        where (
            select count(p2)
            from Product p2
            where p2.category = c
        ) >= :minimumCount
        """
)
Page<CategoryStatistics> findCategoryStatisticsPage(
        @Param("minimumCount") Long minimumCount,
        Pageable pageable
);
~~~

countQuery ở ví dụ đếm số Category thỏa ngưỡng tương ứng với số nhóm trong truy vấn chính. Trong truy vấn thực tế, nếu điều kiện JOIN hoặc HAVING khác, phải điều chỉnh countQuery theo cùng logic. Hãy test cả content, totalElements và totalPages; không chỉ kiểm tra danh sách phần tử đầu tiên.

## 14. Dùng native query cho phép tổng hợp đặc thù

Nếu cần hàm aggregate hoặc cú pháp riêng của database không được JPQL chuẩn hỗ trợ, có thể dùng native SQL. Khi đó, kiểu kết quả phụ thuộc JDBC driver và database.

Ví dụ:

~~~java
@Query(value = """
    SELECT
        category_id AS categoryId,
        COUNT(*) AS productCount,
        SUM(price) AS totalPrice
    FROM products
    GROUP BY category_id
    """, nativeQuery = true)
List<Object[]> getNativeCategoryTotals();
~~~

Với native query:
- COUNT thường được driver trả về kiểu số như Long/BigInteger tùy database và driver.
- SUM/AVG có kiểu JDBC phụ thuộc kiểu cột và hệ quản trị.
- Alias và result mapping cần được kiểm tra.
- Không nên giả định kiểu native aggregate luôn giống kiểu JPQL aggregate.

Nếu kết quả phức tạp, dùng @SqlResultSetMapping, DTO mapping phù hợp hoặc chuyển đổi tại một adapter/repository riêng. Chạy integration test trên database production để xác nhận kiểu dữ liệu thực tế.

## 15. Những lỗi thường gặp

**Khai báo kiểu trả về sai**

Ví dụ SUM(Integer) trả Long theo JPQL, nhưng method lại khai báo Integer. Kiểm tra quy tắc kiểu aggregate trước khi chọn chữ ký Repository.

**Dùng primitive cho aggregate có thể NULL**

SUM, AVG, MIN và MAX có thể trả NULL khi không có dữ liệu. Dùng wrapper/Optional hoặc COALESCE. COUNT là trường hợp khác vì trả 0.

**Nhầm AVG trả về BigDecimal**

JPQL AVG trả Double. Nếu cần quy tắc tiền tệ, xử lý chuyển đổi và làm tròn tường minh.

**Dùng Object[] rồi ép kiểu sai index**

Thứ tự phần tử phải theo SELECT. Ưu tiên projection/DTO để đặt tên và kiểu rõ ràng.

**Thiếu GROUP BY**

Mọi biểu thức SELECT không được tổng hợp cần phù hợp với GROUP BY theo quy tắc JPQL. Kiểm tra cả biểu thức và thuộc tính đường dẫn.

**Đặt điều kiện aggregate trong WHERE**

WHERE lọc dòng trước khi nhóm; điều kiện như COUNT(...) >= n phải đặt trong HAVING.

**Đếm trùng do JOIN**

JOIN nhiều collection có thể nhân bản dòng. Xác định đúng đơn vị đếm và dùng COUNT(DISTINCT ...) khi cần.

**Projection alias không khớp getter**

Tên alias cần tương ứng với property projection. Kiểm tra chính tả và kiểu dữ liệu.

**DTO constructor không khớp**

Constructor expression cần tên lớp đầy đủ, đúng thứ tự tham số và đúng kiểu kết quả.

**Không xử lý NULL của aggregate**

SUM/AVG/MIN/MAX có thể trả NULL. Xác định rõ nghiệp vụ muốn null, Optional hay giá trị mặc định.

## 16. Kiểm thử truy vấn vô hướng và tổng hợp

Một repository test nên xác nhận kiểu kết quả và trường hợp dữ liệu rỗng:

~~~java
@DataJpaTest
class ProductAggregateRepositoryTest {

    @Autowired
    private ProductRepository repository;

    @Test
    void countReturnsZeroWhenNoProductMatches() {
        assertEquals(0L, repository.countActiveProducts());
    }

    @Test
    void sumReturnsEmptyWhenThereAreNoMatchingPrices() {
        Optional<BigDecimal> total =
                repository.sumActiveProductPrices();

        assertTrue(total.isEmpty());
    }

    @Test
    void scalarQueryReturnsTheSelectedProperty() {
        Product saved = repository.save(
                new Product("Keyboard", new BigDecimal("125.50"), true)
        );

        Optional<BigDecimal> price =
                repository.findProductPrice(saved.getId());

        assertEquals(new BigDecimal("125.50"), price.orElseThrow());
    }
}
~~~

Ví dụ cần Entity Product và Repository có constructor/phương thức tương ứng. Test @DataJpaTest thường chạy trong transaction và rollback sau test. Nếu cần xác nhận constraint hoặc dữ liệu đã được gửi xuống database, gọi flush theo nhu cầu.

Nên bổ sung test cho:
- Một dòng và nhiều dòng kết quả scalar.
- Aggregate trên tập rỗng.
- Thuộc tính đầu vào có NULL.
- Nhóm có dữ liệu và nhóm không có dữ liệu với LEFT JOIN.
- COUNT(DISTINCT ...) khi JOIN nhiều quan hệ.
- Kiểu trả về BigDecimal, Long và Double.
- DTO constructor và interface projection.
- HAVING và phân trang/countQuery.

## 17. Quy trình chọn kiểu kết quả

Khi viết một query trả về giá trị tổng hợp, thực hiện theo trình tự:

1. Xác định truy vấn cần trả Entity, một scalar, nhiều scalar hay một nhóm kết quả.
2. Xác định kiểu Java của từng biểu thức SELECT.
3. Với COUNT, dùng Long; với AVG, dùng Double; với SUM, áp dụng quy tắc theo kiểu đầu vào; với MIN/MAX, dùng kiểu của biểu thức.
4. Xác định hành vi khi không có dữ liệu: 0, NULL, Optional.empty() hay giá trị mặc định.
5. Nếu SELECT nhiều cột, ưu tiên interface projection hoặc DTO constructor expression.
6. Nếu có JOIN và aggregate, kiểm tra khả năng đếm trùng và chọn COUNT(DISTINCT ...) khi cần.
7. Đặt điều kiện dòng ở WHERE và điều kiện nhóm ở HAVING.
8. Kiểm tra alias, constructor, kiểu tham số và countQuery.
9. Chạy integration test trên database mục tiêu, nhất là với native aggregate.

## 18. Kết luận

JPQL có thể trả về thuộc tính đơn lẻ, biểu thức vô hướng và kết quả tổng hợp mà không cần tải toàn bộ Entity. COUNT trả Long và bằng 0 khi không có dữ liệu; AVG trả Double; SUM có kiểu phụ thuộc kiểu số đầu vào; MIN/MAX giữ kiểu của biểu thức và các hàm này có thể trả NULL trên tập rỗng. Với nhiều giá trị hoặc GROUP BY, nên dùng interface projection hoặc DTO constructor expression để ánh xạ rõ ràng, tránh phụ thuộc Object[] và thứ tự index. Hãy kiểm tra NULL, kiểu kết quả, GROUP BY/HAVING, JOIN gây đếm trùng và countQuery bằng integration test trên database mục tiêu.
