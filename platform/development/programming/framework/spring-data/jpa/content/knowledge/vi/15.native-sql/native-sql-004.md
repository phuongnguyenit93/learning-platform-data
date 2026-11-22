# Trả về dữ liệu vô hướng, interface projection và DTO trong Spring Data JPA native SQL

Khi dùng SQL thuần qua Spring Data JPA, câu truy vấn có thể trả về một giá trị đơn, một tập cột hoặc một cấu trúc dữ liệu dành riêng cho ứng dụng. Cách chọn kiểu kết quả ảnh hưởng tới cách Spring Data JPA và JPA provider ánh xạ hàng SQL thành Java object.

Ba lựa chọn phổ biến:

- **Scalar result**: trả về một giá trị như `Long`, `String`, `BigDecimal`, `LocalDate` hoặc một kiểu đơn.
- **Interface projection**: ánh xạ các cột kết quả vào getter của một interface; tên alias cột cần khớp với property projection.
- **DTO projection**: tạo object/record có constructor nhận các giá trị từ kết quả query; với native SQL phức tạp có thể cần result set mapping tường minh.

Native SQL cho phép dùng cú pháp và tính năng riêng của database, nhưng ứng dụng phải kiểm soát tên cột, alias, kiểu JDBC, thứ tự constructor, phân trang và tính portable. Tài liệu này tập trung vào Spring Data JPA với Jakarta Persistence (`jakarta.persistence`) và Spring Boot 3 trở lên. Dự án cũ có thể dùng `javax.persistence`; không trộn hai namespace.

## 1. Native SQL và JPQL

JPQL truy vấn entity và thuộc tính Java:

```jpql
select p.name
from Product p
where p.active = true
```

Native SQL truy vấn bảng và cột vật lý:

```sql
select p.name
from product p
where p.active = true
```

Khai báo native query trong Spring Data JPA:

```java
@Query(
    value = "select p.name from product p where p.active = true",
    nativeQuery = true
)
List<String> findActiveNames();
```

Native query hữu ích khi:

- Cần CTE, window function, JSON operator, full-text search hoặc cú pháp database-specific.
- Query báo cáo phức tạp cần tối ưu bằng SQL trực tiếp.
- Cần gọi view, stored procedure hoặc cấu trúc schema không thuận tiện với JPQL.
- Đã đo và xác nhận JPQL/provider sinh SQL chưa phù hợp.

Đổi lại, native query gắn chặt hơn với schema và database. Đổi tên bảng/cột hoặc chuyển database có thể buộc phải sửa query. Không dùng native SQL chỉ vì câu query ngắn hơn; JPQL thường dễ bảo trì hơn khi truy vấn theo mô hình entity.

## 2. Các dạng kết quả thường gặp

| Dạng kết quả | Ví dụ Java | Khi phù hợp |
|---|---|---|
| Scalar đơn | `Long`, `String`, `BigDecimal`, `Optional<String>` | COUNT, SUM, một cột hoặc một giá trị |
| Danh sách scalar | `List<Long>`, `List<String>` | Danh sách ID, tên, mã hoặc giá trị đơn |
| Nhiều cột dạng thô | `Object[]` | Truy vấn động hoặc kiểm tra nhanh; ít an toàn kiểu |
| Interface projection | `List<ProductView>` | Một tập cột có alias ổn định, muốn getter rõ ràng |
| DTO/class/record | `List<ProductSummary>` | Kết quả có cấu trúc rõ, dùng cho service/API/report |
| Entity | `Product`, `List<Product>` | Cần entity được quản lý và đủ các cột mapping |

Không phải mọi kiểu kết quả đều có thể suy ra tự động từ tên method. Kiểu trả về, số cột, alias và khả năng chuyển đổi của provider phải tương thích với query.

## 3. Trả về scalar result

Scalar là kết quả đơn như ID, tên, tổng số lượng hoặc tổng tiền. Nếu query chỉ chọn một cột, JPA thường trả mỗi hàng dưới dạng một giá trị thay vì `Object[]`.

### 3.1. Trả về một giá trị

Ví dụ lấy tên sản phẩm:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query(
        value = """
            select p.name
            from product p
            where p.id = ?1
            """,
        nativeQuery = true
    )
    Optional<String> findNameById(Long id);
}
```

Ví dụ đếm số sản phẩm:

```java
@Query(
    value = "select count(*) from product where active = true",
    nativeQuery = true
)
Long countActiveProducts();
```

Spring Data JPA/provider thực hiện chuyển kết quả JDBC sang kiểu method khi có conversion phù hợp. Với aggregate như COUNT/SUM, kiểu JDBC trả về có thể phụ thuộc database và driver; nếu dùng EntityManager trực tiếp, nhận kết quả dưới dạng `Number` rồi chuyển bằng `longValue()` hoặc `intValue()` khi phù hợp.

### 3.2. Scalar với EntityManager

```java
Object result = entityManager
    .createNativeQuery("""
        select count(*)
        from product
        where active = true
        """)
    .getSingleResult();

long count = ((Number) result).longValue();
```

Cách dùng `Number` an toàn hơn việc giả định mọi database luôn trả COUNT là cùng một lớp Java. Kiểu cụ thể có thể là Long, BigInteger hoặc kiểu Number khác theo provider/driver.

### 3.3. Danh sách scalar

```java
@Query(
    value = """
        select p.id
        from product p
        where p.category = ?1
        order by p.id
        """,
    nativeQuery = true
)
List<Long> findIdsByCategory(String category);
```

Một cột được chọn nên tương ứng với kiểu phần tử của List. Nếu query chọn nhiều cột, không khai báo `List<Long>` chỉ vì cột đầu tiên là ID; cần dùng DTO/interface hoặc nhận kết quả thô có cấu trúc.

### 3.4. Single result và nhiều kết quả

Với EntityManager:

- `getSingleResult()` ném `NoResultException` nếu không có hàng.
- `getSingleResult()` ném `NonUniqueResultException` nếu có nhiều hơn một hàng.
- `getResultList()` trả danh sách, rỗng nếu không có hàng.

Với Spring Data repository, dùng `Optional<T>` khi kết quả có thể không có và method được thiết kế trả tối đa một hàng. Nếu query có thể trả nhiều hàng, dùng List hoặc Page. Không dùng Optional để che một query đáng lẽ phải unique nhưng đang trả nhiều hàng.

## 4. Scalar có NULL và kiểu dữ liệu

Cột SQL có thể trả NULL. Khi ánh xạ vào Java:

- Dùng wrapper như `Long`, `Integer`, `Boolean` thay cho primitive nếu cột có thể NULL.
- Dùng `Optional<T>` cho method có thể không có hàng; Optional không tự thay thế NULL trong từng cột của một projection.
- Kiểm tra kiểu của DATE/TIMESTAMP, DECIMAL, UUID, enum, JSON và kiểu database-specific.
- Với SUM/AVG, kiểm tra kiểu trả về thực tế theo database và provider.

Ví dụ cột nullable:

```java
@Query(
    value = "select p.discount_rate from product p where p.id = ?1",
    nativeQuery = true
)
BigDecimal findDiscountRate(Long id);
```

Nếu discount_rate có thể NULL, kiểu BigDecimal có thể nhận null; hãy khai báo API service phù hợp. Không dùng `double` hoặc `int` primitive để nhận một cột có thể NULL.

Một aggregate như `SUM` có thể trả NULL khi không có hàng phù hợp hoặc tất cả giá trị là NULL. Có thể dùng `COALESCE` trong SQL nếu muốn giá trị mặc định:

```sql
select coalesce(sum(p.price), 0)
from product p
where p.active = true
```

Giá trị mặc định phải có kiểu tương thích với biểu thức và database.

## 5. Nhiều cột và Object[]

Nếu native query chọn nhiều cột mà không có mapping cụ thể, JPA thường trả mỗi hàng dưới dạng một mảng Object:

```java
List<Object[]> rows = entityManager
    .createNativeQuery("""
        select p.id, p.name, p.price
        from product p
        where p.active = true
        """)
    .getResultList();

for (Object[] row : rows) {
    Long id = ((Number) row[0]).longValue();
    String name = (String) row[1];
    BigDecimal price = (BigDecimal) row[2];
}
```

Thứ tự phần tử trong Object[] tương ứng thứ tự các cột trong SELECT. Cách này có nhược điểm:

- Không an toàn kiểu tại compile time.
- Thay đổi thứ tự SELECT có thể làm code đọc nhầm cột.
- Dễ gặp ClassCastException nếu kiểu JDBC/provider khác giả định.
- Code phụ thuộc index 0, 1, 2 nên khó bảo trì.

Dùng Object[] phù hợp cho kiểm tra nhanh hoặc xử lý query rất động. Với kết quả ổn định trong ứng dụng, interface projection hoặc DTO rõ ràng hơn.

## 6. Interface projection

Interface projection cho phép Spring Data JPA ánh xạ cột kết quả vào getter của interface. Mỗi getter tương ứng với một property projection.

Ví dụ:

```java
public interface ProductView {
    Long getId();
    String getName();
    BigDecimal getPrice();
}
```

Native query:

```java
@Query(
    value = """
        select
            p.id as id,
            p.name as name,
            p.price as price
        from product p
        where p.active = ?1
        order by p.name, p.id
        """,
    nativeQuery = true
)
List<ProductView> findActiveProductViews(boolean active);
```

Spring Data JPA có thể dùng kết quả dạng tuple/map để tạo proxy projection. Alias trong SELECT là cầu nối giữa tên cột SQL và getter Java:

- `id` → `getId()`
- `name` → `getName()`
- `price` → `getPrice()`

Tên alias nên duy nhất và khớp rõ với property projection. Không chọn hai cột có cùng label như `id`; nếu query JOIN nhiều bảng, đặt alias riêng như `productId` và `categoryId`.

### 6.1. Alias camelCase và snake_case

Database thường có cột `created_at`, trong Java property có thể là `createdAt`.

Có thể viết alias rõ ràng:

```sql
select p.created_at as createdAt
from product p
```

Một số database chuẩn hóa casing của alias không quote; một số Spring Data JPA/provider có cơ chế thử ánh xạ camelCase sang snake_case cho native tuple. Hành vi này phụ thuộc phiên bản và database. Nếu cần alias giữ chính xác chữ hoa/thường, có thể dùng quoted alias theo cú pháp database, ví dụ:

```sql
select p.created_at as "createdAt"
from product p
```

Quoted identifier không có cùng quy tắc trên mọi database; hãy kiểm thử trên engine đang chạy. Cách an toàn là dùng alias đơn giản, duy nhất, kiểm tra metadata/giá trị projection trong integration test và tránh dựa vào fallback naming không được bảo đảm.

### 6.2. Getter nullable

Nếu một cột có thể NULL, getter nên dùng wrapper:

```java
public interface ProductView {
    Long getId();
    String getName();
    BigDecimal getDiscountRate();
}
```

Không khai báo `long getId()` hoặc `boolean isActive()` nếu query có thể trả NULL cho cột tương ứng. Primitive không thể biểu diễn null.

### 6.3. Projection lồng nhau

Interface projection có thể hỗ trợ nested projection trong nhiều trường hợp JPQL/entity mapping, nhưng native SQL result là tập cột phẳng. Đừng giả định một alias như `category.id` tự động dựng được object Category lồng nhau từ native query. Với native query, nên:

- Chọn các cột cần thiết và dùng alias phẳng.
- Dùng DTO để gom các giá trị theo cấu trúc.
- Hoặc chạy query riêng cho association nếu hợp lý.

## 7. DTO projection bằng class hoặc record

DTO là object chỉ chứa dữ liệu cần trả về. DTO không phải entity và không được quản lý bởi PersistenceContext.

Ví dụ record:

```java
public record ProductSummary(
    Long id,
    String name,
    BigDecimal price
) {}
```

Native query trong Spring Data JPA:

```java
@Query(
    value = """
        select p.id, p.name, p.price
        from product p
        where p.active = ?1
        order by p.name, p.id
        """,
    nativeQuery = true
)
List<ProductSummary> findActiveSummaries(boolean active);
```

Với class-based projection từ native query, việc ánh xạ trực tiếp phù hợp khi thứ tự cột SELECT và kiểu dữ liệu trả về khớp constructor DTO. Ví dụ:

1. Cột thứ nhất → tham số Long id.
2. Cột thứ hai → tham số String name.
3. Cột thứ ba → tham số BigDecimal price.

Nếu số cột, thứ tự hoặc kiểu không khớp, mapping có thể thất bại lúc chạy. Đừng chỉ đổi thứ tự tham số DTO rồi mong framework tự suy ra tên property từ alias trong mọi trường hợp.

DTO phù hợp khi:

- Cần cấu trúc kết quả ổn định cho service/API.
- Muốn tránh Object[] và ép kiểu thủ công.
- Query JOIN nhiều bảng và trả về dữ liệu tổng hợp.
- Không cần entity lifecycle, dirty checking hay lazy association.
- Muốn kiểm soát chính xác các trường được tải.

## 8. Native DTO mapping khi constructor không khớp trực tiếp

Khi native query có alias, kiểu dữ liệu hoặc cấu trúc phức tạp, dùng `@SqlResultSetMapping` để khai báo mapping tường minh.

Ví dụ DTO:

```java
public class ProductRevenue {
    private final Long productId;
    private final String productName;
    private final BigDecimal revenue;

    public ProductRevenue(
            Long productId,
            String productName,
            BigDecimal revenue) {
        this.productId = productId;
        this.productName = productName;
        this.revenue = revenue;
    }

    public Long getProductId() { return productId; }
    public String getProductName() { return productName; }
    public BigDecimal getRevenue() { return revenue; }
}
```

Khai báo mapping trên một entity:

```java
@Entity
@Table(name = "product")
@SqlResultSetMapping(
    name = "ProductRevenueMapping",
    classes = @ConstructorResult(
        targetClass = ProductRevenue.class,
        columns = {
            @ColumnResult(name = "product_id", type = Long.class),
            @ColumnResult(name = "product_name", type = String.class),
            @ColumnResult(name = "revenue", type = BigDecimal.class)
        }
    )
)
public class Product {
    @Id
    private Long id;
}
```

Chạy native query qua EntityManager:

```java
@SuppressWarnings("unchecked")
List<ProductRevenue> results = entityManager
    .createNativeQuery("""
        select
            p.id as product_id,
            p.name as product_name,
            sum(oi.quantity * oi.unit_price) as revenue
        from product p
        join order_item oi on oi.product_id = p.id
        group by p.id, p.name
        """, "ProductRevenueMapping")
    .getResultList();
```

`@ConstructorResult` ghép các `@ColumnResult` với constructor theo thứ tự khai báo. Tên cột trong mapping phải khớp alias của SELECT; kiểu phải tương thích constructor. Dù có khai báo type, vẫn cần kiểm thử kiểu mà driver/provider trả về, đặc biệt với aggregate, enum và kiểu database-specific.

Với Spring Data JPA từ phiên bản có annotation `@NativeQuery` hỗ trợ thuộc tính `sqlResultSetMapping` (Spring Data JPA 3.4 trở lên), có thể liên kết named mapping với repository method. Ví dụ:

```java
@NativeQuery(
    value = """
        select
            p.id as product_id,
            p.name as product_name,
            sum(oi.quantity * oi.unit_price) as revenue
        from product p
        join order_item oi on oi.product_id = p.id
        group by p.id, p.name
        """,
    sqlResultSetMapping = "ProductRevenueMapping"
)
List<ProductRevenue> findRevenueByProduct();
```

Nếu phiên bản đang dùng chưa hỗ trợ `@NativeQuery` hoặc thuộc tính mapping tương ứng, dùng `EntityManager.createNativeQuery(sql, mappingName)` như ví dụ trên, hoặc nâng cấp sau khi kiểm tra tương thích. Không giả định annotation của phiên bản mới tồn tại trong Spring Data JPA cũ.

## 9. Entity result và DTO result khác nhau

Native query có thể trả về entity:

```java
@Query(
    value = "select p.* from product p where p.id = ?1",
    nativeQuery = true
)
Optional<Product> findEntityById(Long id);
```

Khi ánh xạ entity, kết quả phải cung cấp đủ các cột cần thiết cho entity mapping, bao gồm các cột kế thừa/association cần thiết theo mapping và provider. Nếu thiếu cột, kết quả có thể không hợp lệ hoặc lỗi lúc chạy.

Entity result:

- Có thể trở thành managed trong PersistenceContext khi được thực hiện trong context phù hợp.
- Có lifecycle, dirty checking và association mapping.
- Có thể kéo theo lazy/eager loading behavior.

DTO/interface projection:

- Chỉ biểu diễn dữ liệu truy vấn.
- Không được quản lý như entity.
- Không có dirty checking hay cascade.
- Thường phù hợp hơn cho read model, báo cáo và API response.

Không trả entity chỉ vì query đang đọc từ một bảng. Nếu chỉ cần ba cột, projection giúp giảm dữ liệu và giảm coupling với persistence lifecycle.

## 10. Native interface projection với JOIN nhiều bảng

Ví dụ muốn trả về tên sản phẩm và tên category:

```java
public interface ProductCategoryView {
    Long getProductId();
    String getProductName();
    String getCategoryName();
}
```

Query:

```java
@Query(
    value = """
        select
            p.id as productId,
            p.name as productName,
            c.name as categoryName
        from product p
        join category c on c.id = p.category_id
        where c.active = ?1
        order by p.name, p.id
        """,
    nativeQuery = true
)
List<ProductCategoryView> findProductsWithCategory(boolean categoryActive);
```

Alias phải không trùng và tương ứng getter. Nếu hai bảng đều có cột `id`, đừng trả cả hai dưới alias `id`; dùng `productId`, `categoryId`. Với quoted alias, chú ý quy tắc casing của database.

Nếu muốn trả nested DTO như `ProductSummary(category = new CategorySummary(...))`, interface projection phẳng không tự dựng cấu trúc đó từ native SQL. Có thể dùng DTO constructor mapping, mapping nhiều bước trong service hoặc một query riêng.

## 11. Native query với Page và countQuery

Khi native query trả Page, cần đảm bảo Spring Data có thể tạo count query chính xác. Với SQL có JOIN, GROUP BY, DISTINCT, CTE hoặc subquery phức tạp, nên khai báo `countQuery` rõ ràng.

```java
@Query(
    value = """
        select
            p.id as id,
            p.name as name,
            p.price as price
        from product p
        where p.active = ?1
        order by p.created_at desc, p.id desc
        """,
    countQuery = """
        select count(*)
        from product p
        where p.active = ?1
        """,
    nativeQuery = true
)
Page<ProductView> findActivePage(
    boolean active,
    Pageable pageable
);
```

Ví dụ này dùng ORDER BY cố định trong SQL. Khi dùng Pageable, cần xác định query đã chứa ORDER BY hay chưa và cách phiên bản Spring Data JPA xử lý Sort động với native SQL. Khả năng rewrite native query phụ thuộc parser và độ phức tạp câu SQL; không giả định mọi Sort property đều được nối an toàn vào SQL.

Nếu cần sort động, chỉ cho phép các cột nằm trong whitelist do ứng dụng định nghĩa và xây dựng custom repository query phù hợp. Không nối trực tiếp tên cột hoặc hướng sort do người dùng gửi lên.

Nếu query trả group/aggregate, count query phải đếm đúng số kết quả sau grouping, có thể cần subquery:

```sql
select count(*)
from (
    select p.category_id
    from product p
    group by p.category_id
) grouped_categories
```

Đây là SQL minh họa; cú pháp subquery trong FROM và cách Spring Data phân tích count phụ thuộc database/provider. Cần test Page totalElements và nội dung từng trang trên engine thực tế.

## 12. Parameter binding và an toàn SQL

Không nối input trực tiếp vào native SQL:

```java
// Không an toàn: tránh nối chuỗi đầu vào vào SQL.
String sql = "select * from product where name = '" + userInput + "'";
```

Dùng parameter binding:

```java
@Query(
    value = "select p.id from product p where p.name = ?1",
    nativeQuery = true
)
List<Long> findIdsByName(String name);
```

Với native SQL, positional parameter thường là lựa chọn portable theo Jakarta Persistence. Named parameter trong native query được một số provider hỗ trợ và thường thấy trong ứng dụng Spring Data JPA, nhưng không nên mặc định mọi provider đều hỗ trợ giống nhau. Nếu cần tính portable cao, dùng positional parameter và kiểm thử với provider/database mục tiêu.

Parameter chỉ thay giá trị. Không thể dùng parameter để thay tên bảng, tên cột, keyword hoặc `ASC/DESC`. Nếu cần chọn sort column, dùng whitelist:

```java
String orderBy = switch (sortKey) {
    case "name" -> "p.name";
    case "price" -> "p.price";
    case "createdAt" -> "p.created_at";
    default -> "p.id";
};
```

Đoạn switch chỉ minh họa whitelist; khi tạo SQL động, chỉ ghép các literal do ứng dụng kiểm soát, còn mọi giá trị dữ liệu vẫn phải bind parameter.

## 13. Kiểu dữ liệu đặc thù và conversion

Native query nhận kiểu từ JDBC driver và provider. Một số điểm cần chú ý:

- **COUNT/SUM/AVG:** kiểu trả về có thể khác theo database; kiểm tra Number/BigDecimal và conversion.
- **DECIMAL/NUMERIC:** dùng BigDecimal cho tiền và độ chính xác; tránh chuyển qua double không cần thiết.
- **DATE/TIMESTAMP:** mapping sang LocalDate, LocalDateTime, Instant hoặc kiểu khác phụ thuộc JDBC/provider và timezone.
- **BOOLEAN:** một số database lưu boolean bằng kiểu số/char; kiểm tra conversion.
- **ENUM:** native SQL thường trả giá trị cột, cần mapping/conversion tương thích với cách enum được lưu.
- **UUID:** kiểu JDBC có thể khác theo database.
- **JSON/ARRAY/vendor type:** thường cần provider-specific mapping, converter hoặc đọc qua kiểu JDBC tương ứng.
- **NULL:** dùng wrapper/reference type; kiểm tra nullable column trong DTO.

Nếu conversion tự động không rõ ràng, dùng `@ColumnResult(type = ...)`, converter, custom repository mapping hoặc chuyển đổi rõ ràng ở service. Đừng ép cast dựa trên một lần chạy trên H2 nếu production dùng PostgreSQL/MySQL/Oracle.

## 14. Projection không phải Entity và không tự đồng bộ

Interface projection thường là proxy đọc dữ liệu từ kết quả query. DTO là object dữ liệu thông thường. Cả hai không tự trở thành entity managed chỉ vì chứa ID của một entity.

Ví dụ:

```java
ProductView view = repository.findViewById(id);
```

Không thể gọi `view.setName(...)` nếu interface chỉ có getter và kỳ vọng JPA tự UPDATE database. Muốn sửa dữ liệu, load entity managed hoặc thực hiện UPDATE query rõ ràng.

Nếu projection chứa association hoặc property lồng nhau, việc mapping có thể kích hoạt query khác trong một số cách triển khai. Với native SQL, ưu tiên chọn các cột cần thiết và trả projection phẳng/DTO để tránh truy vấn ẩn.

## 15. Lựa chọn scalar, interface hay DTO

| Tiêu chí | Scalar | Interface projection | DTO |
|---|---|---|---|
| Độ phức tạp kết quả | Một giá trị | Nhiều property có tên | Nhiều property có cấu trúc |
| Khai báo | Kiểu trả về trực tiếp | Interface getter | Class/record constructor |
| Mapping | Theo kiểu cột | Theo alias/property | Theo constructor hoặc result set mapping |
| An toàn kiểu | Tốt nếu scalar conversion rõ | Tốt ở API getter, runtime alias cần đúng | Tốt khi constructor/type mapping đúng |
| Native SQL nhiều bảng | Phù hợp aggregate đơn | Tốt cho kết quả phẳng | Tốt cho cấu trúc rõ/phức tạp |
| Nested object | Không | Không nên giả định với native SQL | Có thể dựng bằng mapping/service |
| PersistenceContext | Không phải entity | Không phải entity | Không phải entity |
| Phù hợp | Count, sum, ID, name | Danh sách read-only đơn giản | API/report/read model ổn định |

Quy tắc chọn:

1. Một giá trị duy nhất: trả scalar.
2. Một vài cột phẳng với alias rõ: interface projection.
3. Kết quả nhiều cột có cấu trúc, cần constructor và kiểm soát kiểu: DTO/record.
4. Cần entity lifecycle và association: entity result.
5. Native mapping phức tạp hoặc thứ tự constructor không phù hợp: `@SqlResultSetMapping` hoặc custom repository.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| ClassCastException khi đọc COUNT | Giả định kiểu Number cụ thể không đúng | Nhận Number rồi chuyển kiểu; kiểm tra driver |
| Interface projection trả null ở getter | Alias không khớp property hoặc casing bị database chuẩn hóa | Đặt alias rõ, duy nhất; test trên database thật |
| DTO constructor mapping thất bại | Sai thứ tự cột, số cột hoặc kiểu constructor | So khớp SELECT với constructor; dùng SqlResultSetMapping |
| Duplicate alias | JOIN nhiều bảng có cột cùng tên | Đặt alias riêng cho từng cột |
| DTO native query chạy trên H2 nhưng lỗi production | Kiểu JDBC/dialect khác nhau | Test trên cùng database engine hoặc Testcontainers |
| Page totalElements sai | Count query không tương đương query dữ liệu | Viết countQuery riêng và test nhiều trường hợp |
| Sort động không hoạt động | Native SQL parser không rewrite được query phức tạp | ORDER BY cố định hoặc custom repository với whitelist |
| Primitive getter nhận NULL | Cột nullable nhưng projection dùng primitive | Dùng wrapper/reference type |
| Query bị SQL injection | Nối input vào SQL hoặc sort identifier không kiểm soát | Bind value; whitelist identifier/order |
| Entity result thiếu cột | Native SELECT không trả đủ dữ liệu entity mapping | Chọn đầy đủ cột hoặc dùng projection/DTO |
| Named parameter không portable | Provider xử lý native named binding khác nhau | Dùng positional parameter nếu cần portable |
| Mapping nested projection không hoạt động | Native result là tập cột phẳng | Dùng DTO mapping hoặc xử lý nhiều bước |

## 17. Kiểm thử native result mapping

Với mỗi query, nên có integration test xác nhận:

- Số cột và alias đúng như projection mong đợi.
- Scalar trả đúng kiểu và xử lý NULL.
- Interface getter nhận đúng giá trị, đặc biệt alias camelCase/snake_case.
- DTO constructor nhận đúng thứ tự và kiểu.
- JOIN không tạo hàng trùng ngoài ý muốn.
- Page content và countQuery trả tổng số đúng.
- Sort, pagination và ORDER BY ổn định.
- Query chạy trên đúng database engine và driver production.
- Parameter binding xử lý chuỗi đặc biệt mà không làm sai SQL.
- Query không vô tình trả entity khi chỉ cần DTO.

Không chỉ dùng mock repository để test mapping. Mock không chạy SQL, không thực hiện JDBC conversion và không kiểm tra alias. Hãy dùng `@DataJpaTest` với Testcontainers hoặc database test cùng engine khi mapping phụ thuộc database.

## 18. Checklist trước khi đưa native projection vào production

- [ ] Query thật sự cần native SQL hay JPQL đã đủ?
- [ ] Kiểu kết quả là scalar, interface, DTO hay entity?
- [ ] Số cột SELECT và kiểu trả về tương thích method?
- [ ] Alias duy nhất và khớp getter/property?
- [ ] DTO constructor đúng thứ tự và kiểu, hoặc có SqlResultSetMapping?
- [ ] Cột nullable dùng kiểu Java có thể nhận null?
- [ ] Aggregate COUNT/SUM/AVG đã kiểm tra kiểu thực tế?
- [ ] Named/positional parameter phù hợp provider và tính portable mong muốn?
- [ ] Không nối input vào SQL identifier/order?
- [ ] Page có countQuery chính xác?
- [ ] Sort động được whitelist và test?
- [ ] Integration test chạy trên database/driver mục tiêu?
- [ ] SQL log không làm lộ dữ liệu nhạy cảm?

## 19. Kết luận

Scalar phù hợp với một giá trị đơn; interface projection phù hợp với tập cột phẳng có alias rõ; DTO/record phù hợp với read model có cấu trúc và constructor được kiểm soát. Khi native SQL trả về entity, query phải đáp ứng đầy đủ mapping entity và entity có thể tham gia PersistenceContext.

Với native SQL, alias và kiểu JDBC quyết định phần lớn độ tin cậy của projection. Hãy dùng alias duy nhất, kiểm tra NULL và kiểu aggregate, so khớp thứ tự constructor DTO hoặc khai báo `@SqlResultSetMapping`, đồng thời viết countQuery riêng cho Page khi cần. Test trên database thật để phát hiện khác biệt giữa dialect, driver và provider trước khi triển khai.
