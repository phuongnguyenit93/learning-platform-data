# Chọn truy vấn theo tên, JPQL, Specification, Querydsl hoặc native SQL

Spring Data JPA cung cấp nhiều cách xây dựng truy vấn. Mỗi cách giải quyết một kiểu nhu cầu khác nhau: **derived query** phù hợp với điều kiện đơn giản, **JPQL** phù hợp với truy vấn cố định cần kiểm soát rõ, **Specification** phù hợp với bộ lọc động, **Querydsl** cung cấp API truy vấn có kiểm tra kiểu ở compile time, còn **native SQL** dành cho trường hợp cần tính năng hoặc cách tối ưu đặc thù của database.

Không có một lựa chọn tốt nhất cho mọi repository. Chọn sai cách có thể khiến method name quá dài, JPQL khó bảo trì, Specification thành một khối predicate khó đọc, Querydsl tăng độ phức tạp build, hoặc native SQL làm ứng dụng phụ thuộc database.

Bài này so sánh năm cách tiếp cận trên cùng một miền dữ liệu, giải thích cách Spring Data JPA thực thi chúng, đưa ra tiêu chí lựa chọn theo độ phức tạp và khả năng thay đổi của truy vấn, đồng thời đề cập phân trang, count query, projection, bảo mật parameter binding và kiểm thử.

**Điều kiện của ví dụ:** Java 17+, Spring Boot 3.x, Spring Data JPA, Jakarta Persistence và Hibernate. Ứng dụng cần **spring-boot-starter-data-jpa**, JDBC driver, DataSource và schema phù hợp. Querydsl cần thêm dependency và annotation processor tương thích Jakarta. Các đoạn mã là thành phần của ứng dụng Spring Boot, không phải chương trình Java độc lập chạy chỉ bằng javac.

## 1. Bắt đầu từ cùng một yêu cầu nghiệp vụ

Giả sử ứng dụng quản lý Product với các thuộc tính:

- id: khóa chính.
- name: tên sản phẩm.
- category: danh mục.
- status: trạng thái.
- price: giá.
- createdAt: thời điểm tạo.

Một màn hình tìm kiếm có thể cần:

1. Tìm sản phẩm theo status.
2. Tìm tên có chứa từ khóa, không phân biệt hoa thường.
3. Lọc theo category tùy chọn.
4. Lọc giá trong một khoảng.
5. Sắp xếp theo giá hoặc thời điểm tạo.
6. Phân trang kết quả.
7. Có thể bổ sung filter mới theo yêu cầu sau này.

Repository có thể dùng một hoặc nhiều phương pháp truy vấn tùy use case. Điều quan trọng là không cố đưa mọi kiểu tìm kiếm vào một cơ chế duy nhất.

Ví dụ entity rút gọn:

~~~java
@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    private String category;

    @Enumerated(EnumType.STRING)
    private ProductStatus status;

    private BigDecimal price;

    private Instant createdAt;

    protected Product() {
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

    public ProductStatus getStatus() {
        return status;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

Ví dụ dùng các field đơn giản để tập trung vào cách chọn query. Trong dự án thật, entity cần đầy đủ constructor, accessor, mapping và lifecycle theo convention của ứng dụng.

## 2. Tổng quan năm cách xây dựng truy vấn

| Cách | Cách viết | Phù hợp nhất khi | Đánh đổi chính |
|---|---|---|---|
| Derived query | Đặt điều kiện trong tên method | Điều kiện ngắn, ổn định, dễ đọc | Method name dài khi nhiều điều kiện |
| JPQL | Viết query trên entity/property | Query cố định, cần join, projection hoặc aggregate | Query string không được kiểm tra đầy đủ khi compile |
| Specification | Ghép predicate bằng Criteria API | Filter tùy chọn, kết hợp động | Có thể nhiều abstraction và khó đọc nếu chia quá vụn |
| Querydsl | Dùng fluent, type-safe API | Query động phức tạp, cần kiểm tra kiểu | Thêm dependency, generated Q-types và build setup |
| Native SQL | Viết SQL theo database | Cần CTE, window function, hint hoặc SQL đặc thù | Phụ thuộc engine, schema và mapping kết quả |

Có thể bắt đầu bằng derived query cho nhu cầu nhỏ. Khi logic tăng, chuyển sang JPQL hoặc Specification. Nếu nhiều truy vấn động phức tạp và nhóm phát triển chấp nhận Querydsl, đó là lựa chọn type-safe. Native SQL nên được dùng có chủ đích khi lợi ích của SQL cụ thể lớn hơn chi phí phụ thuộc database.

## 3. Derived query: truy vấn theo tên method

Spring Data phân tích tên method repository để tạo truy vấn. Tên method gồm phần mô tả truy vấn, property và keyword như **And**, **Or**, **Containing**, **StartingWith**, **Between**, **In**, **OrderBy**.

Repository:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    List<Product> findByStatus(ProductStatus status);

    List<Product> findByCategoryAndStatus(
        String category,
        ProductStatus status
    );

    List<Product> findByNameContainingIgnoreCase(String keyword);

    List<Product> findByPriceBetween(
        BigDecimal minPrice,
        BigDecimal maxPrice
    );

    Page<Product> findByStatus(
        ProductStatus status,
        Pageable pageable
    );

    List<Product> findByStatusOrderByCreatedAtDesc(
        ProductStatus status
    );
}
~~~

Spring Data đọc tên method và ánh xạ property trong entity. Ví dụ:

~~~java
List<Product> products =
    repository.findByNameContainingIgnoreCase("keyboard");
~~~

có ngữ nghĩa tìm tên chứa từ khóa và bỏ qua khác biệt chữ hoa/thường theo khả năng của JPA provider/database.

### Keyword thường dùng

| Keyword | Ý nghĩa |
|---|---|
| findBy / readBy / getBy | Bắt đầu một truy vấn đọc |
| And / Or | Kết hợp điều kiện |
| Is / Equals | So sánh bằng |
| Not | Phủ định |
| IsNull / IsNotNull | Kiểm tra null |
| GreaterThan / LessThan | So sánh lớn hơn/nhỏ hơn |
| Between | Nằm trong khoảng |
| Like / Containing | So khớp LIKE/chứa chuỗi |
| StartingWith / EndingWith | Bắt đầu/kết thúc bằng |
| In / NotIn | Thuộc/không thuộc tập giá trị |
| IgnoreCase | So sánh chuỗi không phân biệt hoa thường |
| OrderBy | Sắp xếp kết quả |
| Top / First | Giới hạn số kết quả |

Keyword và cách phân tích tên method được định nghĩa trong tài liệu Spring Data; khi dùng property lồng nhau, hãy kiểm tra quy tắc phân giải tên và dùng dấu gạch dưới nếu cần làm rõ đường dẫn.

### Khi nào derived query bắt đầu khó bảo trì?

Ví dụ method sau đã diễn đạt khá nhiều điều kiện:

~~~java
Page<Product> findByStatusAndCategoryAndNameContainingIgnoreCaseAndPriceBetweenOrderByCreatedAtDesc(
    ProductStatus status,
    String category,
    String name,
    BigDecimal minPrice,
    BigDecimal maxPrice,
    Pageable pageable
);
~~~

Method này vẫn hợp lệ nếu mọi điều kiện luôn bắt buộc. Nhưng nếu category, name, minPrice và maxPrice đều tùy chọn, việc biểu diễn mọi tổ hợp trong tên method nhanh chóng trở nên bất tiện.

Không tạo hàng chục method cho từng tổ hợp filter. Khi điều kiện tùy chọn tăng lên, chuyển sang Specification hoặc Querydsl thường rõ ràng hơn.

## 4. JPQL: viết truy vấn trên entity và property

JPQL dùng tên entity và thuộc tính Java, không dùng trực tiếp tên bảng/cột database. Nó phù hợp khi truy vấn có hình dạng cố định và cần kiểm soát join, projection, aggregate hoặc điều kiện rõ ràng.

Ví dụ:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query("""
        select p
        from Product p
        where p.status = :status
          and lower(p.name) like lower(concat('%', :keyword, '%'))
        order by p.createdAt desc
        """)
    List<Product> search(
        @Param("status") ProductStatus status,
        @Param("keyword") String keyword
    );
}
~~~

Trong query:

- Product là entity name.
- p.name và p.status là property Java.
- :status và :keyword là named parameters.
- concat tạo chuỗi cho LIKE; cú pháp biểu thức JPQL được provider dịch sang SQL.

Nếu muốn tránh wildcard trong input có ý nghĩa đặc biệt của LIKE, hãy escape ký tự wildcard theo quy tắc phù hợp và thêm ESCAPE clause. Không giả định chuỗi người dùng nhập luôn là literal nếu query dùng LIKE.

### JPQL join và projection

Ví dụ Product thuộc Category entity thay vì dùng chuỗi category:

~~~java
@Query("""
    select p
    from Product p
    join p.category c
    where c.name = :categoryName
      and p.status = :status
    """)
List<Product> findByCategoryNameAndStatus(
    @Param("categoryName") String categoryName,
    @Param("status") ProductStatus status
);
~~~

Nếu chỉ cần một phần dữ liệu, có thể dùng DTO projection:

~~~java
public record ProductSummary(
    Long id,
    String name,
    BigDecimal price
) {
}
~~~

~~~java
@Query("""
    select new com.example.catalog.dto.ProductSummary(
        p.id,
        p.name,
        p.price
    )
    from Product p
    where p.status = :status
    order by p.name
    """)
List<ProductSummary> findSummariesByStatus(
    @Param("status") ProductStatus status
);
~~~

Constructor expression phải dùng tên class DTO đầy đủ và thứ tự/kiểu đối số phải khớp constructor. Với Java record, canonical constructor đáp ứng cách gọi này khi kiểu và thứ tự thành phần phù hợp.

### @Query và named query

Có thể khai báo JPQL ngay trên repository bằng **@Query** hoặc dùng named query metadata. @Query thường thuận tiện khi query gắn với đúng repository method. Named query phù hợp khi muốn đặt query cạnh entity mapping hoặc tái sử dụng theo tên.

Tránh nhúng logic nghiệp vụ dài vào một chuỗi JPQL khó đọc. Khi query trở nên động hoặc có nhiều nhánh, Specification/Querydsl dễ tổ chức hơn.

## 5. JPQL với phân trang và count query

Một method trả Page cần dữ liệu trang và tổng số phần tử để tạo metadata. Spring Data có thể suy ra count query cho một số JPQL đơn giản, nhưng query có join, distinct, group by hoặc projection phức tạp nên khai báo countQuery riêng.

~~~java
@Query(
    value = """
        select p
        from Product p
        where p.status = :status
        """,
    countQuery = """
        select count(p)
        from Product p
        where p.status = :status
        """
)
Page<Product> findPageByStatus(
    @Param("status") ProductStatus status,
    Pageable pageable
);
~~~

Count query phải đếm đúng tập kết quả của content query. Nếu content query join collection và có thể lặp entity cha, count có thể cần **count(distinct p.id)**. Nếu có GROUP BY, count phải đếm số nhóm trả về.

Có thể dùng **Slice** nếu chỉ cần biết còn trang tiếp theo hay không và không cần totalElements/totalPages. Slice thường tránh yêu cầu count query, nhưng vẫn phải đọc đủ dữ liệu để xác định hasNext.

Không dùng Page chỉ vì API có phân trang. Hãy cân nhắc chi phí count trên tập dữ liệu lớn.

## 6. Specification: ghép điều kiện động bằng Criteria API

**Specification<T>** biểu diễn một predicate trên entity. Repository cần kế thừa **JpaSpecificationExecutor<T>**:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                JpaSpecificationExecutor<Product> {
}
~~~

Mỗi Specification có thể tạo một predicate hoặc trả null để bỏ qua điều kiện. Các Specification có thể kết hợp bằng and/or.

Ví dụ các filter độc lập:

~~~java
public final class ProductSpecifications {

    private ProductSpecifications() {
    }

    public static Specification<Product> hasStatus(
            ProductStatus status) {
        return (root, query, cb) ->
            status == null
                ? null
                : cb.equal(root.get("status"), status);
    }

    public static Specification<Product> inCategory(
            String category) {
        return (root, query, cb) ->
            category == null || category.isBlank()
                ? null
                : cb.equal(root.get("category"), category);
    }

    public static Specification<Product> nameContains(
            String keyword) {
        return (root, query, cb) -> {
            if (keyword == null || keyword.isBlank()) {
                return null;
            }

            String pattern =
                "%" + keyword.toLowerCase(Locale.ROOT) + "%";

            return cb.like(
                cb.lower(root.get("name")),
                pattern
            );
        };
    }

    public static Specification<Product> priceAtLeast(
            BigDecimal minimum) {
        return (root, query, cb) ->
            minimum == null
                ? null
                : cb.greaterThanOrEqualTo(
                    root.get("price"),
                    minimum
                );
    }

    public static Specification<Product> priceAtMost(
            BigDecimal maximum) {
        return (root, query, cb) ->
            maximum == null
                ? null
                : cb.lessThanOrEqualTo(
                    root.get("price"),
                    maximum
                );
    }
}
~~~

Kết hợp trong service:

~~~java
@Transactional(readOnly = true)
public Page<Product> search(ProductSearchRequest request,
                            Pageable pageable) {

    Specification<Product> specification =
        Specification.where(
            ProductSpecifications.hasStatus(request.status())
        )
        .and(ProductSpecifications.inCategory(request.category()))
        .and(ProductSpecifications.nameContains(request.keyword()))
        .and(ProductSpecifications.priceAtLeast(request.minimumPrice()))
        .and(ProductSpecifications.priceAtMost(request.maximumPrice()));

    return repository.findAll(specification, pageable);
}
~~~

Ví dụ dùng **Specification.where()** và **and()** để thể hiện cách ghép. Tùy phiên bản Spring Data JPA, API composition có thể có thêm các factory method; hãy dùng API có trong version dự án đang quản lý.

### Ưu điểm của Specification

- Điều kiện tùy chọn được tách thành các predicate nhỏ.
- Có thể kết hợp AND/OR theo nhu cầu.
- Có thể tái sử dụng điều kiện giữa nhiều use case.
- Repository không cần method cho mọi tổ hợp filter.
- Tương thích với JpaSpecificationExecutor và Pageable.

### Giới hạn cần chú ý

Specification dựa trên Criteria API, nên code có thể dài và ít trực quan hơn JPQL. Nếu lạm dụng việc chia mỗi điều kiện thành một class nhỏ, người đọc phải đi qua quá nhiều file mới hiểu query hoàn chỉnh.

Ngoài ra, Specification có thể thay đổi query shape bằng join, distinct hoặc fetch. Nếu dùng chung cho truy vấn phân trang, cần kiểm tra count query; một fetch join collection không nên được thêm tùy tiện vào Specification dùng cho Page.

## 7. EXISTS trong Specification khi lọc theo collection

Nếu chỉ cần lọc Product có ít nhất một Review đạt điểm tối thiểu, không nhất thiết join collection rồi loại trùng.

Ví dụ minh họa với entity Review có association product:

~~~java
public static Specification<Product> hasReviewScoreAtLeast(
        Integer minimumScore) {
    return (root, query, cb) -> {
        if (minimumScore == null) {
            return null;
        }

        Subquery<Integer> subquery =
            query.subquery(Integer.class);

        Root<Review> review = subquery.from(Review.class);

        subquery.select(cb.literal(1))
            .where(
                cb.equal(review.get("product"), root),
                cb.greaterThanOrEqualTo(
                    review.get("score"),
                    minimumScore
                )
            );

        return cb.exists(subquery);
    };
}
~~~

Subquery tương quan tham chiếu root của truy vấn ngoài. Cách này diễn đạt trực tiếp yêu cầu “có ít nhất một review phù hợp”, tránh tạo nhiều dòng Product do join collection.

Nếu cần hiển thị Review trong response, EXISTS chỉ lọc Product chứ không tải Review. Hãy chọn fetch plan hoặc DTO projection riêng cho phần dữ liệu cần trả về.

## 8. Querydsl: truy vấn động có kiểm tra kiểu

Querydsl cung cấp fluent API để xây dựng predicate và query bằng Java. Các class Q-type được sinh từ entity, ví dụ **QProduct**. IDE và compiler có thể hỗ trợ kiểm tra property và kiểu dữ liệu tốt hơn so với chuỗi JPQL.

Repository có thể kế thừa:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                QuerydslPredicateExecutor<Product> {
}
~~~

Predicate đơn giản:

~~~java
QProduct product = QProduct.product;

BooleanExpression predicate =
    product.status.eq(ProductStatus.ACTIVE)
        .and(product.price.goe(new BigDecimal("100000")));

Iterable<Product> products =
    repository.findAll(predicate);
~~~

QProduct là class generated từ entity Product; nó không được viết thủ công. Cấu hình build phải chạy annotation processor trước khi compile source sử dụng QProduct.

### Ghép filter tùy chọn

~~~java
public Predicate buildPredicate(ProductSearchRequest request) {
    QProduct p = QProduct.product;

    BooleanBuilder builder = new BooleanBuilder();

    if (request.status() != null) {
        builder.and(p.status.eq(request.status()));
    }

    if (request.category() != null
            && !request.category().isBlank()) {
        builder.and(p.category.eq(request.category()));
    }

    if (request.keyword() != null
            && !request.keyword().isBlank()) {
        builder.and(p.name.containsIgnoreCase(request.keyword()));
    }

    if (request.minimumPrice() != null) {
        builder.and(p.price.goe(request.minimumPrice()));
    }

    if (request.maximumPrice() != null) {
        builder.and(p.price.loe(request.maximumPrice()));
    }

    return builder;
}
~~~

Gọi:

~~~java
Predicate predicate = buildPredicate(request);

Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Order.asc("name"), Sort.Order.asc("id"))
);

Page<Product> page =
    repository.findAll(predicate, pageable);
~~~

**BooleanBuilder** giúp thêm điều kiện theo từng input. Querydsl cũng có thể dùng trực tiếp qua JPAQueryFactory để tạo projection, join, group by, subquery và các query phức tạp hơn.

### Querydsl cần generated Q-types

Với Spring Boot 3/Jakarta, cần chọn bộ artifact và annotation processor tương thích Jakarta Persistence. Cấu hình Maven/Gradle phụ thuộc version Querydsl và build plugin được dự án sử dụng. Không trộn artifact dành cho javax.persistence với entity dùng jakarta.persistence.

Các bước tổng quát:

1. Thêm Querydsl JPA dependency tương thích Jakarta.
2. Thêm annotation processor tương ứng vào build.
3. Cấu hình generated sources directory.
4. Chạy compile để sinh Q-type.
5. Đưa generated source vào compile path theo cấu hình build.
6. Xác nhận CI có thể sinh lại Q-type từ source sạch, không phụ thuộc file generated còn sót trên máy developer.

Querydsl tăng độ type-safe nhưng cũng tăng độ phức tạp build và phụ thuộc thư viện. Trước khi chọn, kiểm tra version tương thích với Hibernate, Jakarta Persistence, Spring Data và chính sách dependency của dự án.

### QuerydslPredicateExecutor hay JPAQueryFactory?

**QuerydslPredicateExecutor** tiện cho CRUD repository với Predicate, Sort và Pageable. Tuy nhiên, abstraction này không cung cấp toàn bộ khả năng điều khiển query của JPAQueryFactory.

Dùng **JPAQueryFactory** khi cần:

- Projection DTO phức tạp.
- Join nhiều entity.
- Group by/having.
- Subquery.
- Kiểm soát fetch và query shape.
- Tối ưu query riêng cho use case.

Có thể giữ repository interface cho thao tác đơn giản và đặt custom repository implementation cho truy vấn Querydsl phức tạp.

## 9. Native SQL: khi cần khả năng đặc thù database

Native SQL cho phép viết trực tiếp câu SQL theo schema vật lý. Nó hữu ích khi cần:

- Common Table Expression (CTE).
- Window function.
- Database hint hoặc optimizer-specific feature.
- JSON operator hoặc array operator.
- Truy vấn báo cáo/tổng hợp khó diễn đạt bằng JPQL.
- Tận dụng tính năng riêng của engine.
- Tối ưu query sau khi đã đo execution plan và chứng minh JPQL/provider chưa đáp ứng.

Ví dụ Spring Data repository:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query(
        value = """
            select p.*
            from products p
            where p.status = :status
              and p.price >= :minimumPrice
            order by p.created_at desc
            """,
        nativeQuery = true
    )
    List<Product> findNativeByStatusAndMinimumPrice(
        @Param("status") String status,
        @Param("minimumPrice") BigDecimal minimumPrice
    );
}
~~~

Đây là SQL theo schema minh họa. Tên bảng/cột, enum representation và kiểu bind phải khớp database thật. Nếu status được lưu bằng VARCHAR theo EnumType.STRING, tham số String có thể phù hợp; nếu mapping khác, cần điều chỉnh.

### Native query với DTO/interface projection

Nếu không cần entity đầy đủ, có thể trả interface projection khi tên cột được alias khớp property projection:

~~~java
public interface ProductNativeView {
    Long getId();
    String getName();
    BigDecimal getPrice();
}
~~~

~~~java
@Query(
    value = """
        select p.id as id,
               p.name as name,
               p.price as price
        from products p
        where p.status = :status
        """,
    nativeQuery = true
)
List<ProductNativeView> findNativeViews(
    @Param("status") String status
);
~~~

Alias là quan trọng vì provider/framework phải ánh xạ cột kết quả về property. Với DTO class, mapping constructor của native query có thể cần **@SqlResultSetMapping** hoặc cơ chế projection phù hợp với version Spring Data JPA. Không giả định mọi native result set đều tự map vào bất kỳ DTO constructor nào.

### Native query có phân trang

Khi dùng native query trả Page, khai báo countQuery riêng nếu Spring Data không thể suy ra chính xác:

~~~java
@Query(
    value = """
        select p.*
        from products p
        where p.status = :status
        """,
    countQuery = """
        select count(*)
        from products p
        where p.status = :status
        """,
    nativeQuery = true
)
Page<Product> findNativePageByStatus(
    @Param("status") String status,
    Pageable pageable
);
~~~

Query native phức tạp có thể cần countQuery tương ứng với logic DISTINCT/GROUP BY của query chính. Dynamic sorting với native query có giới hạn phụ thuộc Spring Data version và khả năng phân tích SQL; không ghép trực tiếp tên cột từ input. Nếu cần sort động, dùng allowlist cột hợp lệ và query builder có kiểm soát hoặc custom repository.

## 10. Bảo mật: bind giá trị, không nối chuỗi SQL

Với JPQL, Specification, Querydsl và derived query, framework hỗ trợ bind giá trị theo cơ chế tương ứng. Với native query, vẫn phải dùng named/positional parameter.

Không làm:

~~~java
String sql =
    "select * from products where name = '" + userInput + "'";
~~~

Nối chuỗi input tạo nguy cơ SQL injection và lỗi escaping.

Parameter binding dùng cho **giá trị**, không dùng để bind tên bảng, tên cột, keyword ORDER BY hoặc hướng ASC/DESC. Nếu API cho phép chọn sort field, hãy map lựa chọn của người dùng qua allowlist:

~~~java
Sort sort = switch (sortKey) {
    case "price" -> Sort.by("price");
    case "createdAt" -> Sort.by("createdAt");
    case "name" -> Sort.by("name");
    default -> Sort.by("id");
};
~~~

Không chuyển nguyên chuỗi sort từ request thành SQL. Với native query cần identifier động, chỉ chọn từ danh sách identifier do ứng dụng định nghĩa.

## 11. So sánh khả năng thay đổi truy vấn

| Tiêu chí | Derived | JPQL | Specification | Querydsl | Native SQL |
|---|---|---|---|---|---|
| Điều kiện đơn giản | Rất phù hợp | Phù hợp | Có thể quá nặng | Có thể quá nặng | Thường không cần |
| Filter tùy chọn | Hạn chế | Có thể dùng nhiều nhánh | Rất phù hợp | Rất phù hợp | Cần builder/SQL động có kiểm soát |
| Join và projection | Hạn chế theo method | Tốt | Criteria hỗ trợ | Rất tốt | Rất tốt |
| Type safety khi compile | Property parse lúc khởi tạo repository; không đầy đủ như Q-type | Thấp hơn API fluent | Property thường là string hoặc metamodel | Cao | Thấp |
| Portability giữa database | Cao | Cao trong phạm vi JPQL | Cao trong phạm vi JPA | Cao trong phạm vi Querydsl JPA | Thấp hơn |
| Query phức tạp đặc thù engine | Không phù hợp | Có giới hạn | Có giới hạn | Có giới hạn theo JPA | Phù hợp |
| Build/dependency complexity | Thấp | Thấp | Thấp | Cao hơn do code generation | Thấp ở build, cao hơn về bảo trì SQL |
| Debug SQL | Cần xem SQL sinh | Cần xem SQL sinh | Cần xem SQL sinh | Cần xem SQL sinh | SQL được viết trực tiếp |

Type-safe không có nghĩa query chắc chắn đúng nghiệp vụ hoặc nhanh. Tất cả cách đều cần kiểm tra SQL, dữ liệu, index và execution plan.

## 12. Cách chọn theo độ phức tạp

Có thể dùng các câu hỏi sau:

**Điều kiện có ngắn và luôn cố định không?**

- Có: derived query thường đủ.
- Không: tiếp tục.

**Query có hình dạng cố định, cần join/projection/aggregate rõ ràng không?**

- Có: JPQL thường dễ review.
- Không: tiếp tục.

**Các filter có tùy chọn và tổ hợp thay đổi theo request không?**

- Có: Specification là lựa chọn tự nhiên trong hệ sinh thái Spring Data JPA.
- Nếu query động phức tạp, nhiều join/projection và nhóm phát triển thích fluent API: cân nhắc Querydsl.

**Có cần tính năng SQL mà JPQL/Criteria không diễn đạt tốt hoặc cần tối ưu đặc thù engine đã được đo chứng minh không?**

- Có: dùng native SQL cho đúng use case.
- Không: giữ truy vấn ở abstraction JPA để giảm phụ thuộc database.

Không cần chuyển toàn bộ repository sang Querydsl hoặc native SQL chỉ vì một query phức tạp. Có thể dùng nhiều cách trong cùng repository/service, miễn là ranh giới và lý do được ghi nhận rõ.

## 13. Tổ chức repository và custom implementation

Repository nên tập trung vào việc truy cập dữ liệu. Logic nghiệp vụ về quyền truy cập, kiểm tra trạng thái và quy tắc xử lý thuộc service/domain.

Một tổ chức có thể như sau:

~~~text
product/
  domain/
    Product.java
  repository/
    ProductRepository.java
    ProductRepositoryCustom.java
    ProductRepositoryImpl.java
  specification/
    ProductSpecifications.java
  query/
    ProductSearchRequest.java
  service/
    ProductService.java
  dto/
    ProductSummary.java
~~~

Repository chính:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                JpaSpecificationExecutor<Product> {
    List<Product> findByStatus(ProductStatus status);
}
~~~

Custom repository interface:

~~~java
public interface ProductRepositoryCustom {
    Page<ProductSummary> searchAdvanced(
        ProductSearchRequest request,
        Pageable pageable
    );
}
~~~

Implementation có thể dùng Querydsl hoặc EntityManager/Criteria tùy quyết định của dự án. Spring Data ghép custom implementation với repository fragment theo naming/configuration convention của version đang dùng. Giữ query phức tạp trong custom implementation giúp interface repository không biến thành danh sách method dài.

## 14. Đừng chọn query chỉ theo số dòng code

Một derived query một dòng có thể dễ viết nhưng method name dài và khó thay đổi. Một JPQL query dài hơn đôi khi lại dễ đọc hơn vì thể hiện rõ join và predicate. Specification có nhiều class nhỏ có thể tái sử dụng, nhưng cũng có thể làm người đọc khó lần theo query cuối cùng.

Hãy đánh giá theo:

- Người khác có hiểu được điều kiện nghiệp vụ từ query không?
- Có thể kiểm tra đúng/sai bằng test không?
- Khi thêm filter mới, có phải sửa nhiều method không?
- Query có phụ thuộc database không?
- Có thể quan sát SQL và execution plan không?
- Count query có đúng không?
- Có đang tải entity/association nhiều hơn response cần không?
- Có thể tái sử dụng predicate mà không tạo coupling khó hiểu không?

Chọn cách đơn giản nhất vẫn diễn đạt rõ yêu cầu và có đường nâng cấp khi query phức tạp hơn.

## 15. Kiểm thử từng cách xây dựng truy vấn

Test repository nên chạy với database phù hợp và dữ liệu đại diện. Với truy vấn JPQL, Specification và Querydsl, cần kiểm tra kết quả thực tế, không chỉ kiểm tra method được gọi.

Ví dụ @DataJpaTest cho derived query và JPQL:

~~~java
@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    private ProductRepository repository;

    @Test
    void derivedQueryFindsProductsIgnoringCase() {
        repository.save(product("Mechanical Keyboard", ProductStatus.ACTIVE));
        repository.save(product("Monitor", ProductStatus.ACTIVE));

        List<Product> result =
            repository.findByNameContainingIgnoreCase("keyboard");

        assertThat(result).hasSize(1);
        assertThat(result.get(0).getName())
            .isEqualTo("Mechanical Keyboard");
    }

    @Test
    void jpqlFiltersByStatus() {
        repository.save(product("Keyboard", ProductStatus.ACTIVE));
        repository.save(product("Mouse", ProductStatus.INACTIVE));

        List<Product> result =
            repository.findByStatus(ProductStatus.ACTIVE);

        assertThat(result).hasSize(1);
    }

    private Product product(String name, ProductStatus status) {
        // Factory helper tạo entity hợp lệ theo mapping của dự án.
        return ProductTestFactory.create(name, status);
    }
}
~~~

Factory trong ví dụ là helper của test do dự án định nghĩa; thay bằng constructor/builder thực tế của entity. Test này minh họa cấu trúc, không phải class độc lập có thể compile nếu thiếu ProductTestFactory và các domain type.

### Test Specification với filter tùy chọn

Tạo các hàng có category, status và price khác nhau. Kiểm tra:

- Không có filter trả về toàn bộ tập hợp được phép.
- Chỉ status được cung cấp thì các filter khác bị bỏ qua.
- Hai filter được kết hợp bằng AND.
- Giá trị null/blank được xử lý đúng.
- Page content và totalElements khớp.
- Sort ổn định khi nhiều hàng có cùng giá trị sort.

### Test Querydsl

Kiểm tra cả trường hợp từng filter riêng và nhiều filter cùng lúc. Build sạch phải sinh Q-type thành công; không chỉ chạy test trên máy developer có generated sources cũ.

### Test native SQL

Chạy trên đúng engine/version mục tiêu. H2 có thể không hỗ trợ CTE, JSON operator, hint hoặc cú pháp riêng của database production. Với native query có countQuery, kiểm tra tổng số và kết quả ở các trang đầu, giữa và cuối.

Testcontainers có thể khởi chạy database engine phù hợp trong CI để kiểm tra query, kiểu dữ liệu, collation, function và migration gần production.

## 16. Đo SQL và execution plan sau khi chọn query

Dù dùng cách nào, Spring Data JPA cuối cùng vẫn cần provider tạo SQL và database thực thi.

Khi query chậm:

1. Bật SQL logging ở môi trường phù hợp hoặc dùng datasource/proxy quan sát SQL.
2. Kiểm tra bind parameter và kiểu dữ liệu.
3. Xác định số câu SQL phát ra, không chỉ câu query chính.
4. Kiểm tra N+1 và lazy loading.
5. Đọc execution plan trên database đích.
6. Xem index, cardinality, sort, join và số dòng thực tế.
7. Đo latency với dữ liệu gần production.

Không bật log bind parameter nhạy cảm trên production nếu log có thể chứa email, token hoặc dữ liệu cá nhân. Dùng môi trường test/staging hoặc masking phù hợp.

Một JPQL query đẹp vẫn có thể sinh SQL kém hiệu quả. Một native query viết tay cũng không tự động nhanh hơn. Hiệu năng được quyết định bởi SQL thực tế, dữ liệu, index, optimizer và workload.

## 17. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Derived method quá dài | Nhiều điều kiện và filter tùy chọn | Chuyển sang Specification hoặc Querydsl |
| JPQL không tìm thấy property | Dùng tên cột thay vì property entity | Dùng entity name và Java property |
| JPQL trả entity trùng | JOIN collection tạo nhiều dòng | Xem xét DISTINCT hoặc EXISTS |
| Page có totalElements sai | Count query không cùng logic content query | Khai báo countQuery và kiểm thử |
| Specification khó hiểu | Chia predicate quá vụn hoặc trộn fetch với filter | Gom theo use case và tách fetch plan |
| Page query bị chậm | Count query đắt hoặc fetch collection | Cân nhắc Slice, ID pagination hoặc DTO |
| Querydsl không compile | Thiếu annotation processor hoặc sai Jakarta artifact | Đồng bộ dependency và generated source |
| Q-type mất trong CI | Generated source chỉ tồn tại trên máy local | Cấu hình build sinh Q-type từ source sạch |
| Native query lỗi trên production | Cú pháp/schema/kiểu dữ liệu phụ thuộc engine | Test trên đúng database/version |
| Native pagination sai | Count query không đúng hoặc sort không hỗ trợ | Viết countQuery riêng và kiểm soát sort |
| SQL injection qua sort | Ghép identifier từ input | Dùng allowlist sort key |
| Query chạy nhanh local nhưng chậm production | Khác dữ liệu, index, thống kê và execution plan | Đo trên dữ liệu gần production |

## 18. Checklist lựa chọn truy vấn

- [ ] Dùng derived query cho điều kiện ngắn, ổn định và dễ đọc.
- [ ] Dùng JPQL cho truy vấn cố định cần join, projection hoặc aggregate rõ ràng.
- [ ] Dùng Specification khi filter tùy chọn cần kết hợp động.
- [ ] Dùng Querydsl khi query động phức tạp và dự án chấp nhận code generation/dependency.
- [ ] Dùng native SQL khi cần tính năng hoặc tối ưu đặc thù database có lý do rõ.
- [ ] Ưu tiên DTO projection khi response chỉ cần một phần dữ liệu.
- [ ] Dùng parameter binding cho mọi giá trị đầu vào.
- [ ] Dùng allowlist cho identifier và sort field động.
- [ ] Kiểm tra countQuery và cardinality khi trả Page.
- [ ] Cân nhắc Slice nếu không cần tổng số trang.
- [ ] Không đặt fetch join collection tùy tiện vào truy vấn phân trang.
- [ ] Tách query phức tạp vào custom repository implementation.
- [ ] Kiểm tra SQL thực tế, số round-trip, N+1 và execution plan.
- [ ] Kiểm thử native query trên đúng database engine.
- [ ] Cấu hình Querydsl generated Q-types để CI build sạch tái tạo được.

## 19. Kết luận

**Derived query** là điểm bắt đầu tốt cho điều kiện đơn giản. **JPQL** phù hợp với query cố định cần thể hiện rõ join và projection. **Specification** xử lý tốt bộ lọc tùy chọn bằng Criteria API. **Querydsl** cung cấp fluent API type-safe cho query động phức tạp, đổi lại cần quản lý generated Q-types và dependency. **Native SQL** dành cho tính năng hoặc tối ưu đặc thù database, nhưng làm tăng coupling và yêu cầu kiểm thử trên đúng engine.

Hãy chọn theo độ phức tạp, khả năng thay đổi, portability và khả năng quan sát SQL. Không chọn chỉ vì ít dòng code hoặc vì một kỹ thuật đang phổ biến. Query tốt là query thể hiện đúng nghiệp vụ, có thể kiểm thử, dễ bảo trì và đã được đo trên dữ liệu thực tế.