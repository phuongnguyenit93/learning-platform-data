# Count query tự sinh, countQuery tùy chỉnh và chi phí đếm

Khi một Repository trả về Page<T>, Spring Data JPA cần cung cấp cả nội dung trang hiện tại lẫn thông tin tổng số phần tử để tính totalElements và totalPages. Vì vậy, ngoài truy vấn lấy dữ liệu, framework có thể thực hiện thêm một truy vấn đếm (count query).

Spring Data có thể suy ra count query từ tên phương thức derived query hoặc từ một số truy vấn khai báo đơn giản. Với truy vấn phức tạp, đặc biệt khi có JOIN collection, DISTINCT, GROUP BY, HAVING hoặc native SQL, nên khai báo countQuery tường minh để bảo đảm số lượng được đếm đúng.

Count query có thể tốn kém đáng kể trên bảng lớn. Thiết kế phân trang cần cân bằng giữa nhu cầu hiển thị tổng số chính xác, chi phí database và trải nghiệm người dùng.

## 1. Vì sao phân trang cần truy vấn đếm?

Một Page<T> thường cung cấp:

- Nội dung của trang hiện tại.
- Số phần tử trong trang.
- Tổng số phần tử phù hợp với điều kiện lọc.
- Tổng số trang.
- Thông tin trang đầu/cuối và trạng thái phân trang.

Ví dụ:

~~~java
Page<Product> page =
        productRepository.findByActiveTrue(
                PageRequest.of(0, 20)
        );

List<Product> products = page.getContent();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
~~~

Truy vấn nội dung lấy tối đa 20 Product cho trang đầu. Để biết tổng số Product active trên toàn bộ tập kết quả, Spring Data cần một phép đếm tương ứng.

SQL minh họa:

~~~sql
SELECT p.*
FROM products p
WHERE p.active = true
ORDER BY p.name
LIMIT 20 OFFSET 0;
~~~

Truy vấn đếm tương ứng:

~~~sql
SELECT COUNT(*)
FROM products p
WHERE p.active = true;
~~~

Đây là hai công việc khác nhau: truy vấn nội dung trả về các hàng cần hiển thị, còn count query tính kích thước của toàn bộ tập kết quả logic.

Không nên nhầm count query với số dòng đang có trong trang. Một trang có 20 phần tử vẫn có thể thuộc tập kết quả gồm hàng triệu phần tử.

## 2. Spring Data tự tạo count query cho derived query

Với phương thức derived query trả về Page<T>, Spring Data có thể tạo truy vấn đếm từ cùng tên phương thức.

Entity ví dụ:

~~~java
@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private boolean active;

    protected Product() {
    }

    public Product(String name, boolean active) {
        this.name = name;
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
~~~

Repository:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Page<Product> findByActiveTrue(Pageable pageable);

    Page<Product> findByNameContainingIgnoreCase(
            String keyword,
            Pageable pageable
    );
}
~~~

Spring Data phân tích điều kiện trong tên phương thức để tạo truy vấn nội dung và truy vấn đếm tương ứng. Với findByActiveTrue, count query phải đếm Product có active = true. Với findByNameContainingIgnoreCase, count query phải giữ cùng điều kiện tìm kiếm tên không phân biệt hoa thường.

Không cần tự khai báo một phương thức count riêng chỉ để Page hoạt động. Framework xử lý count query theo metadata của phương thức phân trang.

### Khi nào việc tự suy ra phù hợp?

Cách này phù hợp khi:
- Điều kiện truy vấn đơn giản.
- Không có cấu trúc JOIN hoặc grouping phức tạp.
- Mỗi kết quả tương ứng với một Entity duy nhất.
- Không có quy tắc đặc biệt làm thay đổi số lượng kết quả logic.

Nếu query method dài, có nhiều quan hệ hoặc cần DISTINCT, hãy kiểm tra SQL đếm được sinh ra. Khi không chắc chắn, dùng @Query với countQuery rõ ràng hoặc viết integration test xác nhận totalElements.

## 3. Page, Slice và List khác nhau về chi phí đếm

Không phải mọi kiểu trả về phân trang đều cần tổng số chính xác.

| Kiểu trả về | Nội dung trang | Tổng số phần tử | Chi phí count query |
|---|---|---|---|
| Page<T> | Có | Có | Thường cần count query, nhưng framework có thể bỏ qua khi suy ra được tổng |
| Slice<T> | Có | Không | Không cần đếm tổng; thường đọc thêm một phần tử để xác định còn trang sau |
| List<T> với Pageable | Có giới hạn trang | Không | Không cần đếm tổng |

Ví dụ Page:

~~~java
Page<Product> findByActiveTrue(Pageable pageable);
~~~

Ví dụ Slice:

~~~java
Slice<Product> findByActiveTrueOrderByIdAsc(Pageable pageable);
~~~

Ví dụ List có Pageable:

~~~java
List<Product> findByActiveTrueOrderByIdAsc(Pageable pageable);
~~~

### Khi nào nên dùng Page?

Dùng Page khi giao diện thực sự cần:
- Tổng số bản ghi.
- Tổng số trang.
- Hiển thị “trang 2 trên 15”.
- Cho phép người dùng nhảy đến một trang bất kỳ dựa trên tổng số.

### Khi nào nên dùng Slice?

Dùng Slice khi giao diện chỉ cần:
- Nội dung trang hiện tại.
- Biết còn dữ liệu để tải tiếp hay không.
- Nút “Tải thêm” hoặc “Trang tiếp theo”.

Slice thường lấy thêm một phần tử ngoài page size để xác định hasNext(), rồi bỏ phần tử kiểm tra đó khỏi nội dung trả về. Vì không cần totalElements, nó tránh được count query riêng.

Nếu giao diện chỉ hiển thị danh sách và nút “Xem thêm”, việc yêu cầu Page chỉ để lấy getContent() có thể tạo chi phí đếm không cần thiết.

## 4. Spring Data có luôn chạy count query cho Page không?

Page cần thông tin tổng số, nhưng Spring Data có thể tối ưu và không chạy count query trong một số trường hợp mà tổng số có thể suy ra từ nội dung trang cùng Pageable.

Ví dụ, nếu trang đầu trả về ít phần tử hơn page size, framework có thể kết luận đó là trang cuối và suy ra tổng số từ số phần tử đã nhận. Nếu trang sau trả về ít hơn page size, tổng số cũng có thể suy ra từ offset cộng số phần tử trong trang.

Khi không thể suy ra tổng số, framework gọi count query để tính totalElements.

Vì vậy, hãy hiểu Page có nhu cầu về tổng số, nhưng không nên giả định mỗi lần gọi Page đều chắc chắn phát ra đúng hai câu SQL. Số câu SQL thực tế còn phụ thuộc dữ liệu, vị trí trang và tối ưu của phiên bản Spring Data.

## 5. Khai báo countQuery bằng @Query

Với truy vấn JPQL khai báo bằng @Query, Spring Data có thể suy ra count query cho những cấu trúc đủ đơn giản. Thuộc tính countQuery cho phép cung cấp câu truy vấn đếm riêng.

Ví dụ:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query(
        value = """
            select p
            from Product p
            where p.active = true
              and p.price >= :minimumPrice
            order by p.name
            """,
        countQuery = """
            select count(p)
            from Product p
            where p.active = true
              and p.price >= :minimumPrice
            """
    )
    Page<Product> findActiveProductsAtPrice(
            @Param("minimumPrice") BigDecimal minimumPrice,
            Pageable pageable
    );
}
~~~

Ở đây:
- value là truy vấn lấy nội dung trang.
- countQuery là truy vấn tính tổng số Product phù hợp.
- Điều kiện active và minimumPrice phải xuất hiện trong cả hai truy vấn.
- ORDER BY không cần thiết trong countQuery vì kết quả chỉ là một số đếm.

Không được bỏ một điều kiện lọc khỏi countQuery. Nếu truy vấn nội dung lọc active và giá, nhưng countQuery chỉ lọc active, totalElements sẽ lớn hơn số kết quả thực tế.

### Count query phải đếm cùng một tập kết quả logic

Hãy kiểm tra sự tương ứng giữa hai truy vấn:

| Truy vấn nội dung | Truy vấn đếm cần bảo toàn |
|---|---|
| WHERE active = true | Cùng điều kiện active |
| Lọc theo khoảng ngày | Cùng cận ngày và tham số |
| JOIN để lọc quan hệ | Cùng điều kiện liên quan |
| DISTINCT Entity | Đếm Entity duy nhất |
| GROUP BY/HAVING | Đếm số nhóm thỏa điều kiện |
| Soft-delete hoặc tenant filter | Cùng phạm vi dữ liệu được phép thấy |

Count query có thể đơn giản hơn truy vấn nội dung nếu vẫn giữ đúng tập kết quả logic. Ví dụ, có thể bỏ SELECT fetch dữ liệu và ORDER BY, nhưng không được bỏ điều kiện làm thay đổi tập phần tử.

## 6. JOIN collection có thể làm đếm trùng

Một lỗi phổ biến là dùng COUNT(entity) sau khi JOIN một collection one-to-many hoặc many-to-many.

Giả sử:
- Một Product có nhiều Tag.
- Product A có 3 Tag.
- Product B có 1 Tag.

Truy vấn:

~~~java
@Query("""
    select distinct p
    from Product p
    join p.tags t
    where t.name in :tagNames
    """)
Page<Product> findProductsByAnyTag(
        @Param("tagNames") Collection<String> tagNames,
        Pageable pageable
);
~~~

Truy vấn nội dung dùng DISTINCT để mỗi Product chỉ xuất hiện một lần dù có nhiều Tag phù hợp.

Nếu count query viết:

~~~java
select count(p)
from Product p
join p.tags t
where t.name in :tagNames
~~~

Product có nhiều Tag phù hợp có thể bị đếm nhiều lần. Khi đó totalElements không khớp với số Product duy nhất.

Count query phù hợp hơn:

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
Page<Product> findProductsByAnyTag(
        @Param("tagNames") Collection<String> tagNames,
        Pageable pageable
);
~~~

COUNT(DISTINCT p.id) đếm mỗi Product một lần. Đây là cách thường dùng khi truy vấn nội dung có DISTINCT Entity sau JOIN collection.

Không thêm DISTINCT máy móc. Nếu JOIN là quan hệ many-to-one và không thể nhân bản Entity ở phía được chọn, count thông thường có thể đã đúng. Hãy xác định cardinality của quan hệ và kết quả logic mà API cam kết.

## 7. COUNT(*), COUNT(id) và COUNT(DISTINCT id)

Các biểu thức đếm có ngữ nghĩa khác nhau:

- COUNT(*) đếm số dòng trong tập kết quả SQL.
- COUNT(expression) đếm số giá trị không NULL của expression.
- COUNT(DISTINCT expression) đếm số giá trị khác nhau và không NULL của expression.

Trong JPQL:
- COUNT(entity) đếm số Entity theo truy vấn.
- COUNT(entity.id) đếm số ID không-null.
- COUNT(DISTINCT entity.id) đếm các Entity có ID khác nhau.

Với Entity có khóa chính không-null, COUNT(p) và COUNT(p.id) thường tương đương nếu truy vấn không tạo duplicate. Khi JOIN collection, cần chú ý việc một Entity có thể xuất hiện ở nhiều dòng SQL.

Ví dụ đếm đơn hàng duy nhất theo khách hàng:

~~~java
@Query("""
    select c.id, count(distinct o.id)
    from Customer c
    left join c.orders o
    group by c.id
    """)
List<Object[]> countOrdersPerCustomer();
~~~

COUNT(DISTINCT o.id) giúp tránh đếm trùng một Order nếu truy vấn còn JOIN thêm các collection khác.

## 8. GROUP BY và HAVING: count số nhóm, không phải số dòng nguồn

Nếu truy vấn nội dung trả về một hàng cho mỗi nhóm, totalElements phải là số nhóm được trả về.

Ví dụ lấy danh mục có ít nhất 5 sản phẩm:

~~~java
public interface CategorySummary {
    Long getCategoryId();
    String getCategoryName();
    Long getProductCount();
}
~~~

~~~java
@Query(
    value = """
        select c.id as categoryId,
               c.name as categoryName,
               count(p.id) as productCount
        from Category c
        left join c.products p
        group by c.id, c.name
        having count(p.id) >= :minimumCount
        """,
    countQuery = """
        select count(c.id)
        from Category c
        where (
            select count(p2.id)
            from Product p2
            where p2.category = c
        ) >= :minimumCount
        """
)
Page<CategorySummary> findCategoriesWithMinimumProducts(
        @Param("minimumCount") Long minimumCount,
        Pageable pageable
);
~~~

Truy vấn nội dung nhóm theo Category và trả về một dòng cho mỗi Category đạt ngưỡng. Count query đếm số Category thỏa cùng điều kiện.

Không nên dùng countQuery đếm số Product nguồn nếu API đang trả về số nhóm Category. Hai đại lượng này khác nhau.

JPQL chuẩn không cho phép đặt một subquery tùy ý trong FROM như derived table SQL. Vì vậy, với truy vấn nhóm phức tạp, có thể viết count query bằng một điều kiện tương quan tương đương, dùng Criteria API/custom repository, hoặc chuyển sang native SQL nếu phù hợp.

## 9. Native SQL và countQuery riêng

Với native query, Spring Data có thể tự suy ra count query cho một số câu SQL đơn giản. Tuy nhiên, khả năng phân tích và viết lại phụ thuộc cấu trúc SQL, phiên bản Spring Data và parser được sử dụng.

Với CTE, UNION, window function, GROUP BY/HAVING, DISTINCT phức tạp hoặc nhiều JOIN, nên khai báo countQuery tường minh.

Ví dụ native query:

~~~java
@Query(
    value = """
        SELECT p.id, p.name, p.price
        FROM products p
        WHERE p.active = true
          AND p.price >= :minimumPrice
        ORDER BY p.name
        """,
    countQuery = """
        SELECT COUNT(*)
        FROM products p
        WHERE p.active = true
          AND p.price >= :minimumPrice
        """,
    nativeQuery = true
)
Page<Object[]> findActiveProductsNative(
        @Param("minimumPrice") BigDecimal minimumPrice,
        Pageable pageable
);
~~~

Nếu native query có JOIN làm nhân bản Product:

~~~sql
SELECT COUNT(DISTINCT p.id)
FROM products p
JOIN product_tags pt ON pt.product_id = p.id
JOIN tags t ON t.id = pt.tag_id
WHERE t.name IN (...);
~~~

Count query native phải dùng đúng tên bảng, cột và cú pháp database. Không dùng tên Entity hoặc thuộc tính Java trong SQL thuần.

Với native query có GROUP BY, có thể đếm số nhóm bằng cách bọc truy vấn nhóm trong derived table nếu database hỗ trợ:

~~~sql
SELECT COUNT(*)
FROM (
    SELECT category_id
    FROM products
    GROUP BY category_id
    HAVING COUNT(*) >= ?
) grouped_categories;
~~~

Cú pháp này là SQL và khả năng hỗ trợ phụ thuộc database. Hãy kiểm tra query trên đúng engine production.

## 10. Chi phí thực tế của count query

Count query có thể đắt dù nó chỉ trả về một số nguyên. Database vẫn phải đọc và đánh giá những dòng cần thiết để xác định có bao nhiêu kết quả phù hợp.

Các yếu tố làm count query tốn kém:

1. Bảng có rất nhiều dòng.
2. Điều kiện WHERE có độ chọn lọc thấp.
3. JOIN nhiều bảng hoặc JOIN collection.
4. COUNT(DISTINCT ...) cần loại trùng.
5. GROUP BY/HAVING tạo nhiều nhóm trung gian.
6. Điều kiện dùng hàm trên cột khiến index thường khó được sử dụng.
7. Thiếu index trên khóa ngoại hoặc cột lọc.
8. Statistics không phản ánh dữ liệu hiện tại.
9. Query phải kiểm tra quyền tenant, soft-delete hoặc nhiều điều kiện động.
10. Database đang chịu tải từ nhiều request đếm đồng thời.

Một trang chỉ hiển thị 20 bản ghi vẫn có thể cần quét hoặc xử lý hàng triệu dòng để tính tổng số chính xác. Giảm page size không nhất thiết làm count query rẻ hơn vì tổng số cần đếm không phụ thuộc số phần tử của trang hiện tại.

## 11. Index có thể giúp count query như thế nào?

Index phù hợp có thể giúp database tìm các dòng thỏa điều kiện mà không phải đọc toàn bộ bảng. Tuy nhiên, index cần phù hợp với predicate và kế hoạch thực thi.

Ví dụ truy vấn:

~~~sql
SELECT COUNT(*)
FROM products
WHERE active = true
  AND category_id = 10;
~~~

Có thể xem xét index kết hợp:

~~~sql
CREATE INDEX idx_products_active_category
ON products (active, category_id);
~~~

Nếu thường xuyên lọc theo category_id rồi active, thứ tự cột trong index có thể cần khác. Quyết định phụ thuộc vào các truy vấn thực tế, độ chọn lọc, database và workload ghi.

Với JOIN theo quan hệ, index trên khóa ngoại thường hữu ích:

~~~sql
CREATE INDEX idx_products_category
ON products (category_id);
~~~

Với count distinct, database có thể cần xử lý loại trùng. Index trên cột khóa hoặc cặp cột JOIN có thể giúp, nhưng không bảo đảm optimizer luôn chọn index.

Hãy dùng EXPLAIN hoặc công cụ execution plan của database để kiểm tra:
- Có dùng index không?
- Đọc bao nhiêu dòng?
- Có sort hoặc hash aggregate không?
- Có bước distinct/grouping tốn kém không?
- Join order có hợp lý không?

Không tạo index chỉ dựa trên tên method Repository. Hãy đo truy vấn thực tế và cân nhắc chi phí INSERT, UPDATE, DELETE cùng dung lượng index.

## 12. Tách truy vấn nội dung và truy vấn đếm

Một count query không cần lấy các trường mà màn hình không sử dụng. Thường có thể bỏ:
- ORDER BY.
- FETCH JOIN chỉ phục vụ hydrate Entity.
- Các cột projection không cần cho phép đếm.
- JOIN không ảnh hưởng đến điều kiện hoặc số lượng logic.

Tuy nhiên, chỉ được bỏ JOIN nếu nó không làm thay đổi tập kết quả. Nếu WHERE lọc theo thuộc tính của Entity liên quan, count query vẫn cần JOIN hoặc điều kiện tương đương.

Ví dụ truy vấn nội dung:

~~~java
@Query(
    value = """
        select distinct p
        from Product p
        join fetch p.category c
        join p.tags t
        where t.name = :tagName
        order by p.name
        """,
    countQuery = """
        select count(distinct p.id)
        from Product p
        join p.tags t
        where t.name = :tagName
        """
)
Page<Product> findProductsWithTagAndCategoryLoaded(
        @Param("tagName") String tagName,
        Pageable pageable
);
~~~

Count query không cần fetch category vì nó không trả Entity. JOIN tags vẫn cần thiết vì điều kiện lọc phụ thuộc Tag. COUNT(DISTINCT p.id) giữ đúng số Product duy nhất.

Lưu ý: phân trang cùng collection fetch join có thể gây vấn đề về kết quả hoặc khiến provider phải tải nhiều dữ liệu trước khi phân trang. Trong nhiều trường hợp, nên phân trang ID trước rồi tải quan hệ cho các ID đó, hoặc dùng projection phù hợp.

## 13. Tính nhất quán giữa truy vấn nội dung và count query

Truy vấn nội dung và count query thường là hai câu SQL riêng. Nếu dữ liệu thay đổi giữa hai lần thực thi, totalElements có thể không khớp hoàn toàn với nội dung tại thời điểm đọc.

Ví dụ:
1. Truy vấn nội dung lấy 20 Product.
2. Một transaction khác thêm hoặc xóa Product phù hợp.
3. Count query chạy sau đó và nhìn thấy trạng thái mới theo isolation level hiện tại.

Ở mức isolation như READ COMMITTED, hai statement có thể quan sát hai snapshot khác nhau. Vì vậy, Page là kết quả phân trang hữu ích cho ứng dụng, nhưng không nên mặc định totalElements là một snapshot bất biến trong mọi hệ thống đồng thời cao.

Nếu nghiệp vụ cần tính nhất quán chặt giữa nội dung và tổng số, cần xem xét transaction isolation và khả năng snapshot của database. Isolation cao hơn có thể tăng chi phí, lock hoặc retry; chỉ dùng khi yêu cầu nghiệp vụ thực sự cần.

## 14. Tối ưu khi tổng số chính xác không cần thiết

Nếu người dùng chỉ cần duyệt dữ liệu tiếp theo, tránh yêu cầu tổng số chính xác.

Các lựa chọn:

- Dùng Slice<T> để lấy nội dung và hasNext().
- Dùng List<T> với Pageable nếu chỉ cần một trang giới hạn.
- Dùng keyset/scrolling pagination cho tập dữ liệu lớn, tuần tự.
- Giới hạn số trang sâu hoặc dùng cursor thay cho offset lớn.
- Chỉ hiển thị tổng số khi nghiệp vụ thực sự cần.

Ví dụ Slice:

~~~java
Slice<Product> slice =
        productRepository.findByActiveTrueOrderByIdAsc(
                PageRequest.of(0, 50)
        );

for (Product product : slice.getContent()) {
    System.out.println(product.getName());
}

if (slice.hasNext()) {
    // Hiển thị nút tải trang tiếp theo.
}
~~~

Slice không cung cấp totalElements hoặc totalPages. Đây là đánh đổi có chủ đích để tránh chi phí count query.

Với màn hình quản trị cần tổng số chính xác, Page vẫn phù hợp. Với feed, lịch sử sự kiện hoặc danh sách cuộn vô hạn, Slice hoặc cursor pagination thường hiệu quả hơn.

## 15. Khi nào cần cache hoặc bảng tổng hợp?

Nếu một báo cáo cần tổng số hoặc thống kê rất lớn được đọc thường xuyên, count query trực tiếp có thể trở thành nút thắt.

Có thể cân nhắc:
- Cache tổng số trong thời gian ngắn nếu chấp nhận dữ liệu hơi cũ.
- Bảng summary/counter được cập nhật theo sự kiện hoặc batch.
- Materialized view hoặc bảng tổng hợp do database quản lý.
- Quy trình cập nhật thống kê định kỳ.
- Chỉ tính lại số liệu khi dữ liệu liên quan thay đổi.

Các giải pháp này làm tăng độ phức tạp đồng bộ và nguy cơ dữ liệu cũ. Cần xác định rõ yêu cầu freshness, cách xử lý transaction thất bại, retry và rebuild dữ liệu tổng hợp.

Không nên tự duy trì counter bằng cách tăng/giảm số trong code nếu chưa xử lý concurrency, rollback và các đường ghi dữ liệu khác như batch job hoặc SQL trực tiếp.

## 16. Derived count query và tên phương thức có DISTINCT

Spring Data có thể suy ra count query cho derived method, nhưng từ khóa DISTINCT trong tên phương thức cần được hiểu đúng.

Ví dụ:

~~~java
long countDistinctByLastname(String lastname);
~~~

Với Entity User có ID duy nhất, cách suy ra thường đếm các User duy nhất thỏa lastname. Vì mỗi User đã có ID riêng, kết quả có thể giống countByLastname(lastname). Nó không nhất thiết có nghĩa là đếm số giá trị lastname khác nhau trong toàn bộ bảng.

Nếu mục tiêu là đếm số họ khác nhau, cần truy vấn rõ biểu thức:

~~~java
@Query("select count(distinct u.lastname) from User u")
long countDistinctLastnames();
~~~

Hãy phân biệt:
- Đếm Entity duy nhất.
- Đếm giá trị thuộc tính duy nhất.
- Đếm dòng sau JOIN.
- Đếm nhóm sau GROUP BY.

Tên method ngắn không thay thế được việc xác định chính xác đại lượng nghiệp vụ cần đếm.

## 17. Kiểm thử count query

Test phân trang cần kiểm tra cả nội dung và tổng số, không chỉ kiểm tra số phần tử trong trang đầu.

Ví dụ:

~~~java
@DataJpaTest
class ProductPaginationRepositoryTest {

    @Autowired
    private ProductRepository repository;

    @Test
    void pageContainsCorrectContentAndTotal() {
        repository.save(new Product("Keyboard", true));
        repository.save(new Product("Mouse", true));
        repository.save(new Product("Monitor", false));

        Page<Product> page = repository.findByActiveTrue(
                PageRequest.of(0, 1, Sort.by("name"))
        );

        assertEquals(1, page.getContent().size());
        assertEquals(2, page.getTotalElements());
        assertEquals(2, page.getTotalPages());
        assertTrue(page.hasNext());
    }
}
~~~

Test này minh họa một trang có một Product nhưng tổng tập kết quả có hai Product active. Test repository cần Entity, constructor và mapping tương ứng trong dự án.

Với countQuery tùy chỉnh, nên kiểm tra thêm:
1. Có nhiều dòng JOIN trỏ đến cùng một Entity.
2. Điều kiện lọc có tham số null hoặc giá trị biên nếu nghiệp vụ cho phép.
3. DISTINCT có đếm đúng Entity duy nhất.
4. GROUP BY/HAVING đếm đúng số nhóm.
5. Native query trả totalElements đúng trên database mục tiêu.
6. Trang cuối có totalElements và hasNext đúng.
7. Không có kết quả thì totalElements bằng 0.
8. Truy vấn nội dung và countQuery dùng cùng tenant/soft-delete/security filter.

Nếu query native dùng cú pháp đặc thù, hãy chạy integration test trên cùng database engine và phiên bản gần với production. H2 không chứng minh được countQuery PostgreSQL hoặc MySQL sẽ có cùng hành vi.

## 18. Những lỗi thường gặp

**Count query bỏ sót điều kiện WHERE**

Kết quả trang có thể đúng nhưng totalElements quá lớn. Giữ tất cả điều kiện ảnh hưởng đến tập kết quả trong countQuery.

**Đếm trùng sau JOIN collection**

Dùng COUNT(DISTINCT entity.id) khi một Entity có thể xuất hiện nhiều lần do JOIN và truy vấn nội dung trả Entity duy nhất.

**Đếm dòng nguồn thay vì số nhóm**

Với GROUP BY/HAVING, count query phải đếm số nhóm được trả về, không phải số dòng trước khi nhóm.

**Đưa FETCH JOIN vào count query**

Count query không cần hydrate quan hệ. Bỏ fetch join và giữ JOIN thường chỉ khi nó cần cho điều kiện lọc hoặc ngữ nghĩa kết quả.

**Tin rằng Page luôn chỉ chạy một câu SQL**

Page có thể cần count query riêng. Quan sát SQL thực tế và dùng Slice nếu không cần tổng số.

**Dùng Page trong feed chỉ cần tải tiếp**

Đây có thể là chi phí đếm không cần thiết. Dùng Slice hoặc cursor pagination.

**Tự động suy ra count từ native SQL phức tạp**

Parser có thể không chuyển đổi đúng CTE, UNION, GROUP BY hoặc cấu trúc lồng nhau. Khai báo countQuery riêng.

**Tạo index mà không xem execution plan**

Index không phải lúc nào cũng được dùng và làm tăng chi phí ghi. Đo trước/sau bằng dữ liệu thực tế.

**Giả định totalElements bất biến giữa hai câu SQL**

Dữ liệu đồng thời có thể thay đổi giữa truy vấn nội dung và truy vấn đếm. Xem xét isolation nếu nghiệp vụ yêu cầu snapshot nhất quán.

## 19. Quy trình lựa chọn và tối ưu count query

Khi tạo phương thức phân trang, hãy làm theo các bước:

1. Xác định giao diện có thực sự cần tổng số chính xác hay chỉ cần biết còn trang tiếp theo.
2. Chọn Page, Slice hoặc List với Pageable theo nhu cầu.
3. Với derived query đơn giản, kiểm tra count query do Spring Data suy ra.
4. Với @Query phức tạp, khai báo countQuery riêng.
5. Đảm bảo count query đếm đúng Entity duy nhất hoặc số nhóm logic.
6. Bỏ ORDER BY và FETCH JOIN khỏi count query khi không cần thiết.
7. Giữ nguyên mọi điều kiện lọc, tenant và soft-delete.
8. Kiểm tra COUNT, COUNT(DISTINCT), GROUP BY, HAVING và NULL semantics.
9. Bật SQL logging và đo count query độc lập với truy vấn nội dung.
10. Dùng EXPLAIN/EXPLAIN ANALYZE và dữ liệu gần production để xem index, join và aggregate.
11. Chạy integration test xác nhận totalElements, totalPages và trang cuối.
12. Nếu count chính xác quá đắt và không cần thiết, chuyển sang Slice/cursor hoặc chiến lược tổng hợp có freshness được xác định.

## 20. Kết luận

Spring Data JPA có thể tự suy ra count query cho derived query và nhiều truy vấn khai báo đơn giản. Khi truy vấn có JOIN collection, DISTINCT, GROUP BY/HAVING hoặc native SQL phức tạp, hãy khai báo countQuery riêng và bảo đảm nó đếm đúng số Entity hoặc nhóm mà truy vấn nội dung trả về. Page cung cấp tổng số chính xác và có thể phát sinh chi phí đếm; Slice phù hợp khi chỉ cần biết còn dữ liệu để tải tiếp. Muốn tối ưu, hãy đo execution plan, tạo index theo workload, loại bỏ JOIN không cần thiết và chỉ yêu cầu tổng số khi sản phẩm thực sự cần.
