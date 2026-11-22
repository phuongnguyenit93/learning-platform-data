# Điều kiện so sánh, khoảng giá trị, IN và NULL

Spring Data JDBC cho phép tạo truy vấn từ tên phương thức repository. Các từ khóa như **GreaterThan**, **LessThan**, **Between**, **In**, **NotIn**, **IsNull** và **IsNotNull** giúp diễn đạt điều kiện lọc mà không cần viết SQL cho từng method.

Cơ chế này được gọi là **query derivation**: Spring Data phân tích tên method, xác định property trong domain model và tạo truy vấn phù hợp. Khi dùng các toán tử này, cần hiểu cả quy tắc đặt tên của Spring Data lẫn semantics SQL, đặc biệt với NULL và tập tham số rỗng.

Bài học sử dụng ví dụ danh mục sản phẩm để trình bày cách so sánh giá trị, lọc theo khoảng, lọc theo tập, xử lý NULL và kết hợp nhiều predicate trong Spring Data Relational/JDBC.

## 1. Query derivation và domain property

Spring Data Commons cung cấp cơ chế phân tích tên method; Spring Data JDBC dùng cơ chế đó để thực thi truy vấn trên relational database.

Ví dụ:

```java
List<Product> findByPriceGreaterThan(BigDecimal price);
```

Tên method có thể đọc thành:

- `findBy`: bắt đầu một truy vấn đọc.
- `Price`: property cần kiểm tra.
- `GreaterThan`: toán tử lớn hơn.

Framework ánh xạ property Java `price` tới cột database theo metadata của entity. Tên method sử dụng **tên property trong domain model**, không sử dụng tên cột vật lý nếu hai tên khác nhau.

Ví dụ domain:

```java
import java.math.BigDecimal;
import java.time.LocalDate;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("products")
public record Product(
    @Id Long id,
    @Column("product_name") String name,
    @Column("unit_price") BigDecimal price,
    ProductStatus status,
    @Column("released_at") LocalDate releasedAt,
    @Column("discontinued_at") LocalDate discontinuedAt,
    boolean active
) {}
```

Enum:

```java
public enum ProductStatus {
    DRAFT,
    AVAILABLE,
    OUT_OF_STOCK,
    DISCONTINUED
}
```

Với mapping trên, query method viết `findByPriceGreaterThan`; SQL được tạo sẽ sử dụng cột `unit_price` theo metadata.

Repository:

```java
import org.springframework.data.repository.ListCrudRepository;

public interface ProductRepository
        extends ListCrudRepository<Product, Long> {
}
```

`ListCrudRepository` trả về `List` cho phương thức nhiều kết quả. Nếu kế thừa `CrudRepository`, các phương thức đọc nhiều phần tử trong hợp đồng CRUD trả về `Iterable`.

## 2. Các toán tử so sánh

Các từ khóa phổ biến:

| Từ khóa | Ý nghĩa | Điều kiện SQL |
| --- | --- | --- |
| `Is`, `Equals` | Bằng | `= ?` |
| `Not`, `IsNot` | Khác | `<> ?` |
| `GreaterThan`, `After` | Lớn hơn | `> ?` |
| `GreaterThanEqual` | Lớn hơn hoặc bằng | `>= ?` |
| `LessThan`, `Before` | Nhỏ hơn | `< ?` |
| `LessThanEqual` | Nhỏ hơn hoặc bằng | `<= ?` |
| `Between` | Nằm trong khoảng | `BETWEEN ? AND ?` |
| `In` | Thuộc tập giá trị | `IN (...)` |
| `NotIn` | Không thuộc tập giá trị | `NOT IN (...)` |
| `IsNull`, `Null` | Giá trị NULL | `IS NULL` |
| `IsNotNull`, `NotNull` | Không phải NULL | `IS NOT NULL` |

Các tên alias có thể dùng để diễn đạt cùng một loại predicate. Hãy chọn cách viết dễ đọc và thống nhất trong codebase.

### 2.1. GreaterThan và LessThan

Repository có thể khai báo:

```java
List<Product> findByPriceGreaterThan(BigDecimal price);

List<Product> findByPriceGreaterThanEqual(BigDecimal price);

List<Product> findByPriceLessThan(BigDecimal price);

List<Product> findByPriceLessThanEqual(BigDecimal price);
```

Ví dụ:

```java
List<Product> expensive =
    products.findByPriceGreaterThan(new BigDecimal("500000"));

List<Product> affordable =
    products.findByPriceLessThanEqual(new BigDecimal("200000"));
```

Ý nghĩa:

- `GreaterThan` không bao gồm giá trị bằng ngưỡng.
- `GreaterThanEqual` bao gồm giá trị bằng ngưỡng.
- `LessThan` không bao gồm giá trị bằng ngưỡng.
- `LessThanEqual` bao gồm giá trị bằng ngưỡng.

Với dữ liệu tiền tệ, dùng `BigDecimal` thay cho `double` để tránh sai số biểu diễn số thực nhị phân.

### 2.2. So sánh ngày và thời gian

Các toán tử so sánh cũng áp dụng cho property ngày/giờ:

```java
List<Product> findByReleasedAtAfter(LocalDate date);

List<Product> findByReleasedAtBefore(LocalDate date);

List<Product> findByReleasedAtGreaterThanEqual(LocalDate date);
```

`After` và `Before` diễn đạt so sánh theo thứ tự thời gian. Nếu nghiệp vụ cần tính cả ngày biên, dùng toán tử có dấu bằng hoặc `Between`.

Với timestamp, cần chọn kiểu Java và kiểu SQL phù hợp. `LocalDate` biểu diễn ngày lịch; `Instant` biểu diễn một thời điểm trên timeline. Hãy xác định timezone và quy tắc chuyển đổi thay vì chỉ dựa vào tên cột.

### 2.3. Equals và Not

Ví dụ:

```java
List<Product> findByStatus(ProductStatus status);

List<Product> findByStatusNot(ProductStatus status);
```

Các method này so sánh giá trị status. Với enum, cần mapping/conversion phù hợp với cách database lưu enum, chẳng hạn chuỗi `AVAILABLE` hoặc mã số.

`Not` là phép so sánh khác với giá trị truyền vào. Nó không đồng nghĩa với `IsNotNull`; kiểm tra NULL là một predicate riêng.

## 3. Truy vấn theo khoảng bằng Between

`Between` dùng khi property cần nằm giữa hai giá trị:

```java
List<Product> findByPriceBetween(
    BigDecimal minPrice,
    BigDecimal maxPrice
);
```

Gọi:

```java
List<Product> selected = products.findByPriceBetween(
    new BigDecimal("100000"),
    new BigDecimal("500000")
);
```

Điều kiện SQL tương ứng:

```sql
WHERE unit_price BETWEEN ? AND ?;
```

Trong SQL, `BETWEEN` bao gồm cả hai đầu mút. Điều kiện trên tương đương:

```sql
WHERE unit_price >= :minPrice
  AND unit_price <= :maxPrice;
```

Nếu nghiệp vụ cần khoảng nửa mở (bao gồm đầu dưới nhưng không gồm đầu trên), hãy kết hợp hai toán tử:

```java
List<Product> findByPriceGreaterThanEqualAndPriceLessThan(
    BigDecimal minPrice,
    BigDecimal maxPrice
);
```

### 3.1. Validate hai đầu khoảng

`Between` không tự kiểm tra rằng min nhỏ hơn hoặc bằng max theo quy tắc nghiệp vụ. Nên kiểm tra ở service hoặc request validation:

```java
public List<Product> findByPriceRange(
    BigDecimal min,
    BigDecimal max
) {
    if (min == null || max == null) {
        throw new IllegalArgumentException(
            "Hai đầu khoảng giá là bắt buộc"
        );
    }

    if (min.compareTo(max) > 0) {
        throw new IllegalArgumentException(
            "Giá tối thiểu không được lớn hơn giá tối đa"
        );
    }

    return products.findByPriceBetween(min, max);
}
```

Với khoảng thời gian theo ngày, hãy xác định rõ hai biên có được tính hay không. Đối với timestamp, khoảng `[start, end)` (bao gồm đầu, loại trừ cuối) thường tránh được việc tự tính giá trị “cuối ngày” phụ thuộc độ chính xác timestamp.

Ví dụ:

```java
List<Order> findByCreatedAtGreaterThanEqualAndCreatedAtLessThan(
    Instant startInclusive,
    Instant endExclusive
);
```

## 4. Lọc theo tập giá trị bằng In

`In` dùng khi giá trị của property phải thuộc một tập lựa chọn:

```java
List<Product> findByStatusIn(Collection<ProductStatus> statuses);
```

Ví dụ:

```java
List<ProductStatus> visibleStatuses = List.of(
    ProductStatus.AVAILABLE,
    ProductStatus.OUT_OF_STOCK
);

List<Product> visible =
    products.findByStatusIn(visibleStatuses);
```

Ý nghĩa SQL:

```sql
WHERE status IN (?, ?);
```

`In` phù hợp khi filter chứa nhiều trạng thái, ID, mã sản phẩm hoặc nhóm phân loại.

Có thể kết hợp với các điều kiện khác:

```java
List<Product> findByActiveTrueAndStatusInAndPriceBetween(
    Collection<ProductStatus> statuses,
    BigDecimal minPrice,
    BigDecimal maxPrice
);
```

Predicate có ý nghĩa:

```sql
WHERE active = TRUE
  AND status IN (...)
  AND unit_price BETWEEN ? AND ?;
```

### 4.1. In theo ID

Ví dụ:

```java
List<Product> findByIdIn(Collection<Long> ids);
```

Method này là query method dẫn xuất theo property `id`. Nó khác `findAllById(ids)` là CRUD method có sẵn trong repository contract.

Nếu chỉ cần tìm aggregate theo tập ID, `findAllById` thường là API trực tiếp. Dùng `findByIdIn` khi cần kết hợp thêm điều kiện hoặc muốn diễn đạt truy vấn qua query derivation.

### 4.2. Collection rỗng

Một câu SQL `IN ()` không hợp lệ trên nhiều database. Không nên phụ thuộc vào việc framework hoặc driver tự diễn giải collection rỗng theo ý nghiệp vụ.

Hãy quyết định rõ ở application layer:

- Nếu tập rỗng nghĩa là không có giá trị nào được phép, trả về danh sách rỗng mà không gọi repository.
- Nếu tập rỗng nghĩa là bỏ qua filter, gọi một method khác không có điều kiện đó.
- Nếu tập rỗng là input không hợp lệ, trả lỗi validation.

Ví dụ:

```java
public List<Product> findByStatuses(
    Collection<ProductStatus> statuses
) {
    if (statuses == null) {
        throw new IllegalArgumentException(
            "Danh sách trạng thái không được null"
        );
    }

    if (statuses.isEmpty()) {
        return List.of();
    }

    return products.findByStatusIn(statuses);
}
```

Không để semantics của một collection rỗng vô tình quyết định kết quả API.

## 5. Lọc ngược tập giá trị bằng NotIn

`NotIn` tìm những hàng có giá trị không thuộc tập đầu vào:

```java
List<Product> findByStatusNotIn(
    Collection<ProductStatus> excludedStatuses
);
```

Ví dụ:

```java
List<ProductStatus> excluded = List.of(
    ProductStatus.DRAFT,
    ProductStatus.DISCONTINUED
);

List<Product> listed =
    products.findByStatusNotIn(excluded);
```

Điều kiện SQL:

```sql
WHERE status NOT IN (?, ?);
```

### 5.1. NULL trong danh sách NotIn

Cần đặc biệt chú ý nếu collection chứa NULL. Theo logic ba giá trị của SQL, biểu thức `NOT IN` với danh sách có NULL có thể khiến những hàng khác cũng không được chọn.

Ví dụ:

```sql
WHERE status NOT IN ('DRAFT', NULL)
```

Với một hàng có status `AVAILABLE`:

- `AVAILABLE <> 'DRAFT'` là TRUE.
- `AVAILABLE <> NULL` là UNKNOWN.
- `TRUE AND UNKNOWN` là UNKNOWN.

WHERE chỉ chọn hàng có predicate TRUE. Vì vậy, hàng `AVAILABLE` cũng không xuất hiện trong kết quả.

Hãy loại bỏ phần tử null khỏi collection nếu không có chủ đích, và biểu diễn điều kiện NULL riêng bằng `IS NULL` khi cần.

## 6. Kết hợp điều kiện bằng And và Or

Có thể nối nhiều predicate trong method name:

```java
List<Product> findByStatusAndActiveTrue(
    ProductStatus status
);

List<Product> findByStatusInAndPriceLessThan(
    Collection<ProductStatus> statuses,
    BigDecimal maxPrice
);

List<Product> findByNameContainingIgnoreCaseOrStatus(
    String keyword,
    ProductStatus status
);
```

Ví dụ:

```java
List<Product> findByStatusAndPriceBetween(
    ProductStatus status,
    BigDecimal min,
    BigDecimal max
);
```

Có ý nghĩa:

```sql
WHERE status = ?
  AND unit_price BETWEEN ? AND ?;
```

### 6.1. Cẩn thận với nhiều nhóm OR

Một method như:

```java
findByStatusAndActiveTrueOrPriceLessThan(...)
```

có thể khó đọc nếu nghiệp vụ yêu cầu nhóm điều kiện phức tạp. Tên method không cung cấp cú pháp ngoặc tùy ý như một biểu thức boolean trong Java.

Khi có nhiều nhóm AND/OR, hãy dùng `@Query` hoặc custom repository để thể hiện điều kiện SQL tường minh. Kiểm thử các tổ hợp dữ liệu đại diện để chắc chắn predicate được nhóm theo đúng yêu cầu nghiệp vụ.

## 7. Xử lý NULL trong query derivation

Trong SQL, NULL biểu thị giá trị chưa biết hoặc không có. Nó không bằng một giá trị khác, kể cả NULL khác.

Các phép so sánh như:

```sql
column = NULL
column <> NULL
column > NULL
```

không trả về TRUE hoặc FALSE; chúng cho kết quả UNKNOWN. Trong WHERE, chỉ hàng có predicate TRUE mới được chọn.

Để kiểm tra NULL, SQL dùng `IS NULL` và `IS NOT NULL`. Spring Data query derivation có các từ khóa tương ứng.

### 7.1. Tìm property có giá trị NULL

```java
List<Product> findByDiscontinuedAtIsNull();
```

Method này tìm sản phẩm chưa có ngày ngừng kinh doanh:

```sql
WHERE discontinued_at IS NULL;
```

Có thể dùng alias `findByDiscontinuedAtNull`, nhưng `IsNull` thường dễ đọc hơn.

### 7.2. Tìm property không NULL

```java
List<Product> findByReleasedAtIsNotNull();
```

Điều kiện SQL:

```sql
WHERE released_at IS NOT NULL;
```

Có thể dùng `findByReleasedAtNotNull`. Hãy chọn cách viết thống nhất.

### 7.3. Truyền null vào predicate equality

Với query derivation, khi tham số của một predicate equality là null, Spring Data xử lý theo semantics NULL tương ứng, thường chuyển điều kiện thành `IS NULL`. Ví dụ:

```java
List<Product> findByDiscontinuedAt(LocalDate date);
```

Khi gọi với `date == null`, điều kiện có thể được dẫn xuất thành truy vấn tìm giá trị NULL. Tuy nhiên, tên method không thể hiện ý định rõ bằng `findByDiscontinuedAtIsNull()`.

Với predicate phủ định, null cũng có quy tắc tương ứng với `IS NOT NULL`. Để code dễ hiểu, nên dùng method có tên `IsNull`/`IsNotNull` khi mục tiêu thực sự là kiểm tra NULL.

### 7.4. NULL khác chuỗi rỗng

```sql
WHERE product_name IS NULL
```

khác với:

```sql
WHERE product_name = '';
```

NULL có nghĩa là không có giá trị; chuỗi rỗng là một giá trị string có độ dài bằng 0. Chuỗi chỉ có dấu cách cũng không phải NULL. Nếu nghiệp vụ coi chuỗi rỗng là thiếu dữ liệu, hãy kiểm tra riêng bằng điều kiện phù hợp, không dùng `IsNull` thay thế.

## 8. NULL trong @Query và SQL viết tay

Khi dùng `@Query`, developer viết SQL trực tiếp và phải tuân theo semantics của database.

Ví dụ:

```java
@Query("""
    SELECT id, product_name, unit_price, status,
           released_at, discontinued_at, active
    FROM products
    WHERE discontinued_at = :date
    """)
List<Product> findByDiscontinuedDate(
    @Param("date") LocalDate date
);
```

Nếu `date` là null, biểu thức SQL `discontinued_at = NULL` không tìm các hàng có giá trị NULL. Muốn tìm NULL, viết `IS NULL` riêng hoặc thiết kế predicate tùy chọn rõ ràng.

Một pattern thường gặp cho tham số filter tùy chọn:

```sql
WHERE (:status IS NULL OR status = :status)
```

Ý nghĩa: nếu status null thì bỏ qua filter; nếu có giá trị thì so sánh bằng. Tuy nhiên, một số database/driver cần kiểu dữ liệu rõ cho parameter null và biểu thức OR có thể ảnh hưởng execution plan. Với truy vấn quan trọng, có thể tách thành hai query hoặc xây dựng SQL động có kiểm soát.

### 8.1. Null parameter không tự động có nghĩa là bỏ qua filter

Ví dụ `findByStatus(null)` không nên được hiểu là “trả tất cả status”. Query derivation xử lý tham số null theo semantics predicate; nếu muốn bỏ qua filter khi không có giá trị, hãy điều phối ở service hoặc định nghĩa query tùy chọn riêng.

Cần phân biệt:

- Tìm hàng có property NULL.
- Không áp dụng điều kiện lọc theo property đó.

Hai yêu cầu có kết quả khác nhau.

## 9. Collection có phần tử null

Ví dụ:

```java
List<ProductStatus> statuses = Arrays.asList(
    ProductStatus.AVAILABLE,
    null
);
```

Với `IN`, phần tử NULL không phải cách rõ ràng để tìm các hàng có status NULL. Với `NOT IN`, nó có thể làm predicate trở thành UNKNOWN đối với các hàng khác.

Nếu muốn tìm các hàng có status thuộc tập lựa chọn **hoặc** status là NULL, hãy biểu diễn rõ:

```sql
WHERE status IN (:statuses)
   OR status IS NULL
```

Tốt nhất là loại null khỏi collection parameter và dùng predicate riêng cho trường hợp NULL.

## 10. Kết hợp so sánh, Between, In và NULL

Một bộ lọc sản phẩm có thể yêu cầu:

- Đang hoạt động.
- Trạng thái thuộc tập cho phép.
- Giá nằm trong khoảng.
- Chưa có ngày ngừng kinh doanh.

Query derivation:

```java
List<Product>
findByActiveTrueAndStatusInAndPriceBetweenAndDiscontinuedAtIsNull(
    Collection<ProductStatus> statuses,
    BigDecimal minPrice,
    BigDecimal maxPrice
);
```

Service kiểm tra đầu vào:

```java
public List<Product> findAvailableProducts(
    Collection<ProductStatus> statuses,
    BigDecimal minPrice,
    BigDecimal maxPrice
) {
    if (statuses == null || statuses.isEmpty()) {
        return List.of();
    }

    if (statuses.contains(null)) {
        throw new IllegalArgumentException(
            "Danh sách status không được chứa null"
        );
    }

    if (minPrice == null || maxPrice == null
            || minPrice.compareTo(maxPrice) > 0) {
        throw new IllegalArgumentException(
            "Khoảng giá không hợp lệ"
        );
    }

    return repository
        .findByActiveTrueAndStatusInAndPriceBetweenAndDiscontinuedAtIsNull(
            statuses,
            minPrice,
            maxPrice
        );
}
```

Method dài nhưng các predicate vẫn độc lập. Nếu có thêm nhiều filter tùy chọn hoặc nhiều nhóm OR, nên cân nhắc `@Query` hoặc custom repository thay vì tạo tên method quá khó bảo trì.

## 11. @Query với IN và named parameter

Khi cần SQL cụ thể, có thể khai báo:

```java
@Query("""
    SELECT id, product_name, unit_price, status,
           released_at, discontinued_at, active
    FROM products
    WHERE status IN (:statuses)
      AND unit_price BETWEEN :minPrice AND :maxPrice
      AND discontinued_at IS NULL
    ORDER BY unit_price ASC, id ASC
    """)
List<Product> searchAvailable(
    @Param("statuses") Collection<String> statuses,
    @Param("minPrice") BigDecimal minPrice,
    @Param("maxPrice") BigDecimal maxPrice
);
```

Named parameter giúp câu SQL dễ đọc và bind giá trị an toàn. Spring JDBC hỗ trợ mở rộng collection parameter cho mệnh đề IN trong query phù hợp.

Cần nhớ:

- Collection nên được kiểm tra không rỗng trước khi gọi.
- Không để phần tử null nếu không có chủ đích.
- Tên bảng/cột trong SQL là tên vật lý của schema; query viết tay không tự chuyển property Java thành tên cột.
- `@Query` không tự bỏ điều kiện chỉ vì parameter null.
- SQL đặc thù database cần được kiểm thử trên đúng dialect.

Với nhiều filter có thể bật/tắt theo request, custom repository có thể xây dựng các predicate từ những mảnh SQL được kiểm soát và bind toàn bộ giá trị qua named parameter. Không nối trực tiếp input người dùng vào SQL.

## 12. Phân trang và sắp xếp với điều kiện lọc

Query derivation có thể kết hợp điều kiện với `Pageable` hoặc `Sort` khi method và kiểu truy vấn hỗ trợ:

```java
Page<Product> findByStatusInAndPriceBetween(
    Collection<ProductStatus> statuses,
    BigDecimal minPrice,
    BigDecimal maxPrice,
    Pageable pageable
);
```

Ví dụ gọi:

```java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.asc("price"),
        Sort.Order.asc("id")
    )
);

Page<Product> page = repository.findByStatusInAndPriceBetween(
    statuses,
    minPrice,
    maxPrice,
    pageable
);
```

`Sort` dùng tên property domain (`price`), không dùng tên cột SQL (`unit_price`). Mapping metadata sẽ chuyển property thành identifier tương ứng.

Nếu giao diện chỉ cần biết còn trang tiếp theo, `Slice<Product>` có thể phù hợp hơn `Page<Product>` vì `Page` có thể cần thêm truy vấn đếm tổng số hàng.

Với string-based `@Query` trong Spring Data JDBC, không nên mặc định framework tự rewrite SQL để thêm `Pageable`, `Sort` hoặc `Limit`. Nếu query viết tay cần giới hạn hoặc sắp xếp động, hãy dùng cơ chế được phiên bản hiện tại hỗ trợ hoặc viết SQL tương ứng một cách tường minh.

## 13. Chọn query derivation hay @Query?

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| So sánh một property với giá trị | `findByPriceGreaterThan` |
| Lọc theo khoảng | `findByPriceBetween` |
| Lọc theo tập giá trị | `findByStatusIn` |
| Loại trừ tập giá trị | `findByStatusNotIn` |
| Tìm NULL/không NULL | `findByReleasedAtIsNull` / `findByReleasedAtIsNotNull` |
| Kết hợp vài điều kiện AND đơn giản | Query derivation |
| Nhiều nhóm OR hoặc filter tùy chọn | `@Query` hoặc custom repository |
| SQL JOIN, aggregate/report query | `@Query` hoặc custom repository |
| SQL đặc thù database | SQL tường minh theo dialect |
| Filter động nhiều lựa chọn | Custom repository/query builder có kiểm soát |

Query derivation phù hợp với điều kiện đơn giản, ổn định và dễ đọc. `@Query` phù hợp khi cần kiểm soát SQL hoặc biểu diễn logic mà tên method trở nên quá dài.

## 14. Kiểm thử các điều kiện truy vấn

Test repository nên bao phủ cả trường hợp thông thường và các biên.

Ví dụ test cho Between:

```java
@DataJdbcTest
class ProductRepositoryTest {

    @Autowired
    ProductRepository products;

    @Test
    void findsProductsWithinInclusivePriceRange() {
        Product low = products.save(product("A", "100000"));
        Product middle = products.save(product("B", "250000"));
        Product high = products.save(product("C", "600000"));

        List<Product> found = products.findByPriceBetween(
            new BigDecimal("100000"),
            new BigDecimal("250000")
        );

        assertThat(found)
            .extracting(Product::id)
            .containsExactlyInAnyOrder(low.id(), middle.id())
            .doesNotContain(high.id());
    }
}
```

Các helper `product` là factory tạo fixture phù hợp với constructor của entity và cần được định nghĩa trong test thực tế.

Nên kiểm thử thêm:

- Giá đúng bằng min và max được bao gồm.
- Giá ngay dưới min và ngay trên max bị loại.
- In với một phần tử và nhiều phần tử.
- Collection In rỗng được service xử lý theo quy tắc đã chọn.
- NotIn không nhận collection có NULL ngoài ý muốn.
- IsNull và IsNotNull phân biệt đúng dữ liệu.
- Query kết hợp And/Or trả đúng tổ hợp.
- Sort/Pageable dùng tên property và có thứ tự ổn định.
- SQL tùy chỉnh chạy trên đúng database/dialect.

Không nên viết test phụ thuộc thứ tự ngẫu nhiên nếu query không có ORDER BY. Với kết quả không sắp xếp, dùng assertion không quan tâm thứ tự.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Không tìm thấy property | Tên trong method không khớp domain model. | Dùng tên property Java và kiểm tra mapping. |
| So sánh NULL không trả kết quả | Dùng `= NULL` hoặc `<> NULL`. | Dùng `IS NULL`/`IS NOT NULL`. |
| Null parameter trả kết quả ngoài mong đợi | Nhầm null với việc bỏ qua filter. | Thiết kế điều kiện optional riêng. |
| Between bỏ sót giá trị biên | Hiểu sai semantics của khoảng. | SQL BETWEEN bao gồm cả hai đầu. |
| In với collection rỗng gây lỗi | SQL `IN ()` không được database hỗ trợ. | Short-circuit hoặc dùng query không có filter. |
| NotIn trả ít hàng hơn dự kiến | Collection chứa NULL. | Loại NULL và xử lý riêng bằng predicate. |
| Query method quá dài | Ghép nhiều And/Or. | Dùng @Query hoặc custom repository. |
| Sort không hoạt động | Dùng tên cột SQL thay property hoặc query không hỗ trợ sort động. | Dùng property name và kiểm tra loại query. |
| @Query không áp dụng Pageable | String-based query không được rewrite như mong đợi. | Viết limit/sort tường minh. |
| H2 pass nhưng production lỗi | Khác biệt SQL, kiểu dữ liệu hoặc dialect. | Integration test trên database thực tế. |

## 16. Quy trình thiết kế bộ lọc động

Khi xây dựng chức năng tìm kiếm:

1. Liệt kê từng filter và xác định property domain tương ứng.
2. Chọn toán tử: bằng, khác, lớn hơn, nhỏ hơn, Between, In hoặc NULL.
3. Quyết định semantics khi filter không được truyền: bỏ qua điều kiện, tìm NULL hay từ chối request.
4. Validate khoảng min/max và collection đầu vào.
5. Loại bỏ hoặc xử lý rõ phần tử null trong tập In/NotIn.
6. Dùng query derivation cho các điều kiện đơn giản, ổn định.
7. Dùng @Query/custom repository khi có nhiều nhóm logic hoặc SQL đặc thù.
8. Bind giá trị qua named parameter; không nối input vào SQL.
9. Thêm sorting/pagination và tiêu chí sắp xếp ổn định khi dữ liệu lớn.
10. Kiểm thử biên, NULL, tập rỗng và đúng database dialect.

> **GreaterThan/LessThan biểu diễn điều kiện so sánh; Between lọc khoảng bao gồm hai đầu; In/NotIn lọc theo tập giá trị; IsNull/IsNotNull kiểm tra NULL.** Hãy thiết kế rõ semantics của tham số null và collection rỗng, vì SQL có logic ba giá trị và không tự hiểu null là “bỏ qua filter”.

### Tài liệu tham khảo

- [Spring Data Commons — Query Method Details](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): keyword và quy tắc phân tích tên query method.
- [Spring Data Relational — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): query derivation và truy vấn trong Spring Data JDBC.
- [Spring Data Commons — Repository Query Keywords](https://docs.spring.io/spring-data/commons/reference/repositories/query-keywords-reference.html): danh sách keyword được hỗ trợ.
- [PostgreSQL — Comparison Functions and Operators](https://www.postgresql.org/docs/current/functions-comparison.html): toán tử so sánh, BETWEEN, IN và xử lý NULL.
- [PostgreSQL — Logical Operators](https://www.postgresql.org/docs/current/functions-logical.html): logic ba giá trị TRUE/FALSE/UNKNOWN trong SQL.
