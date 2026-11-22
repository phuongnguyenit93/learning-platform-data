# Điều kiện so sánh, tập giá trị và khoảng giá trị

Trong Spring Data Relational R2DBC, truy vấn động thường được hình thành từ các điều kiện lọc. Một điều kiện có thể so sánh một thuộc tính với một giá trị, kiểm tra thuộc tính có thuộc một tập giá trị hay xác định nó nằm trong một khoảng. Những phép lọc này xuất hiện trong tìm kiếm sản phẩm, lọc đơn hàng theo trạng thái, truy vấn dữ liệu theo thời gian và nhiều nghiệp vụ khác.

Spring Data R2DBC hỗ trợ nhiều cách diễn đạt các điều kiện: derived query method từ tên phương thức, Criteria kết hợp với R2dbcEntityTemplate, hoặc SQL tường minh qua DatabaseClient. Dù chọn cách nào, cần hiểu chính xác ý nghĩa của toán tử, cách xử lý NULL, biên của khoảng và cách bind tham số.

## 1. Mô hình một điều kiện truy vấn

Một điều kiện lọc có thể được nhìn như phép so sánh giữa thuộc tính của entity và một giá trị đầu vào:

```text
property  operator  value
price     >=        100
status    IN        (NEW, PAID)
createdAt BETWEEN   startTime AND endTime
```

Trong SQL, các điều kiện này thường xuất hiện trong mệnh đề WHERE:

```sql
SELECT id, name, price, status
FROM products
WHERE price >= 100
  AND status IN ('ACTIVE', 'PREORDER');
```

Trong Spring Data, điều kiện có thể được tạo từ tên method hoặc metadata của entity. Spring Data chuyển property của Java thành cột tương ứng theo mapping. Ví dụ property createdAt có thể được ánh xạ tới cột created_at.

Một truy vấn có nhiều điều kiện cần xác định rõ cách kết hợp:

- AND: mọi điều kiện phải đúng.
- OR: ít nhất một điều kiện phải đúng.
- NOT: phủ định một điều kiện.
- Nhóm ngoặc: kiểm soát thứ tự đánh giá khi trộn AND và OR.

Đừng chỉ nhìn tên method dài rồi giả định thứ tự kết hợp. Với logic phức tạp, hãy dùng Criteria hoặc SQL có dấu ngoặc rõ ràng và kiểm thử kết quả.

## 2. Các phép so sánh cơ bản

Các toán tử so sánh thường dùng trong SQL và Spring Data gồm:

| Toán tử | Ý nghĩa | Ví dụ SQL |
| --- | --- | --- |
| = | Bằng | status = 'ACTIVE' |
| <> hoặc != | Khác | status <> 'CANCELLED' |
| > | Lớn hơn | price > 100 |
| >= | Lớn hơn hoặc bằng | price >= 100 |
| < | Nhỏ hơn | quantity < 10 |
| <= | Nhỏ hơn hoặc bằng | quantity <= 10 |
| IS NULL | Giá trị SQL là NULL | deleted_at IS NULL |
| IS NOT NULL | Có giá trị SQL | deleted_at IS NOT NULL |

Các phép so sánh thứ tự phù hợp với kiểu dữ liệu có thứ tự như số, ngày giờ và một số kiểu chuỗi tùy collation. Không nên áp dụng so sánh lớn hơn/nhỏ hơn cho một thuộc tính nếu ngữ nghĩa nghiệp vụ không xác định được thứ tự của nó.

### So sánh bằng và khác

Với derived query method:

```java
public interface ProductRepository
        extends ReactiveCrudRepository<Product, UUID> {

    Flux<Product> findByStatus(ProductStatus status);

    Flux<Product> findByStatusNot(ProductStatus status);
}
```

findByStatus biểu diễn điều kiện bằng. findByStatusNot biểu diễn điều kiện khác. Các từ khóa được phân tích dựa trên property status của entity.

### So sánh lớn hơn và nhỏ hơn

Có thể khai báo truy vấn theo ngưỡng:

```java
Flux<Product> findByPriceGreaterThan(BigDecimal minimum);

Flux<Product> findByPriceGreaterThanEqual(BigDecimal minimum);

Flux<Product> findByPriceLessThan(BigDecimal maximum);

Flux<Product> findByPriceLessThanEqual(BigDecimal maximum);
```

GreaterThan tương ứng >; GreaterThanEqual tương ứng >=; LessThan tương ứng <; LessThanEqual tương ứng <=.

Ví dụ, nếu yêu cầu là “giá từ 100 trở lên”, dùng GreaterThanEqual. Nếu yêu cầu là “giá cao hơn 100”, dùng GreaterThan. Sự khác nhau ở biên có thể làm thay đổi kết quả, nhất là khi lọc số tiền, số lượng hoặc mốc thời gian.

### Kết hợp nhiều phép so sánh

Một method có thể kết hợp điều kiện bằng And:

```java
Flux<Product> findByPriceGreaterThanEqualAndStockQuantityGreaterThan(
        BigDecimal minimumPrice,
        int minimumStock);
```

Method trên chọn sản phẩm có giá ít nhất minimumPrice và lượng tồn kho lớn hơn minimumStock. Hai điều kiện đều phải đúng.

Khi tên method trở nên dài, có nhiều nhánh OR hoặc cần điều kiện tùy chọn, Criteria thường dễ đọc và dễ bảo trì hơn.

## 3. Điều kiện so sánh bằng Criteria

Criteria trong Spring Data Relational biểu diễn điều kiện cho truy vấn theo kiểu API. Nó giúp tạo truy vấn động mà không phải nối chuỗi SQL.

Ví dụ dùng R2dbcEntityTemplate để tìm sản phẩm có giá lớn hơn một ngưỡng:

```java
import java.math.BigDecimal;

import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.data.domain.Sort;
import org.springframework.data.r2dbc.core.R2dbcEntityTemplate;

import reactor.core.publisher.Flux;

public class ProductQueryService {

    private final R2dbcEntityTemplate template;

    public ProductQueryService(R2dbcEntityTemplate template) {
        this.template = template;
    }

    public Flux<Product> findExpensiveProducts(BigDecimal minimum) {
        Query query = Query.query(
            Criteria.where("price").greaterThan(minimum)
        ).sort(Sort.by(Sort.Direction.ASC, "price"));

        return template.select(query, Product.class);
    }
}
```

Criteria.where("price") tham chiếu property price của entity. greaterThan(minimum) tạo điều kiện lớn hơn. Query.query(...) đóng gói điều kiện thành truy vấn; template.select(...) thực thi và ánh xạ các hàng thành Product.

Một số phương thức so sánh thường dùng:

| Criteria method | Ý nghĩa |
| --- | --- |
| is(value) | Bằng giá trị |
| not(value) | Khác giá trị |
| greaterThan(value) | Lớn hơn |
| greaterThanOrEquals(value) | Lớn hơn hoặc bằng |
| lessThan(value) | Nhỏ hơn |
| lessThanOrEquals(value) | Nhỏ hơn hoặc bằng |
| between(lower, upper) | Nằm trong khoảng |
| in(values) | Thuộc tập giá trị |
| notIn(values) | Không thuộc tập giá trị |
| isNull() | Là SQL NULL |
| isNotNull() | Không phải SQL NULL |

Tên và overload cụ thể cần khớp phiên bản Spring Data Relational của dự án. Các ví dụ sử dụng API Criteria của Spring Data Relational; khi nâng cấp dependency, có thể đối chiếu Javadoc phiên bản tương ứng.

## 4. So sánh ngày giờ và kiểu số

Các phép so sánh lớn hơn/nhỏ hơn đặc biệt hữu ích cho dữ liệu có thứ tự.

Ví dụ, truy vấn đơn hàng được tạo sau một thời điểm:

```java
Flux<Order> findByCreatedAtAfter(LocalDateTime moment);

Flux<Order> findByCreatedAtBefore(LocalDateTime moment);
```

After và Before thường diễn đạt điều kiện sau/trước mốc. Nếu cần bao gồm chính mốc thời gian, dùng từ khóa GreaterThanEqual hoặc LessThanEqual trên property tương ứng.

Với kiểu số tiền, nên dùng BigDecimal thay vì double để tránh sai số biểu diễn nhị phân:

```java
Flux<Product> findByPriceGreaterThanEqual(BigDecimal minimumPrice);
```

Đầu vào và cột cần có precision/scale phù hợp. Nếu database lưu NUMERIC(12, 2), hãy thống nhất quy tắc làm tròn và số chữ số thập phân trước khi truy vấn.

Với ngày giờ, phải thống nhất timezone và kiểu cột. Một giá trị LocalDateTime không tự mang thông tin múi giờ; nếu nghiệp vụ cần thời điểm tuyệt đối, hãy thiết kế schema và kiểu Java tương ứng với quy ước UTC hoặc offset/time zone của hệ thống.

## 5. Điều kiện thuộc tập giá trị: IN và NOT IN

Khi một thuộc tính có thể nhận một trong nhiều giá trị được cho phép, dùng điều kiện IN. Ví dụ, tìm các đơn hàng có trạng thái NEW, PAID hoặc SHIPPED.

Trong derived query method:

```java
Flux<Order> findByStatusIn(Collection<OrderStatus> statuses);

Flux<Order> findByStatusNotIn(Collection<OrderStatus> statuses);
```

Có thể gọi repository với một tập trạng thái:

```java
List<OrderStatus> visibleStatuses = List.of(
    OrderStatus.NEW,
    OrderStatus.PAID,
    OrderStatus.SHIPPED
);

Flux<Order> result = orders.findByStatusIn(visibleStatuses);
```

IN trả về bản ghi có giá trị thuộc tập đầu vào. NOT IN trả về bản ghi có giá trị không thuộc tập đó.

Với Criteria:

```java
Criteria criteria = Criteria.where("status")
    .in(OrderStatus.NEW, OrderStatus.PAID, OrderStatus.SHIPPED);

Query query = Query.query(criteria);

return template.select(query, Order.class);
```

Nếu danh sách đầu vào được tạo động:

```java
List<OrderStatus> statuses = request.statuses();

if (statuses == null || statuses.isEmpty()) {
    // Chọn rõ chính sách: không lọc theo trạng thái,
    // hoặc trả về kết quả rỗng theo hợp đồng API.
} else {
    Criteria criteria = Criteria.where("status").in(statuses);
    return template.select(Query.query(criteria), Order.class);
}
```

### Xử lý tập rỗng

Tập rỗng là trường hợp cần quyết định rõ. Một truy vấn SQL có dạng IN () thường không hợp lệ hoặc không có ý nghĩa thống nhất giữa các hệ quản trị. Vì vậy, đừng để kết quả phụ thuộc cách driver xử lý danh sách rỗng.

Hãy xác định ngữ nghĩa ở tầng ứng dụng:

- Nếu danh sách rỗng nghĩa là “không áp dụng bộ lọc này”, bỏ điều kiện IN khỏi truy vấn.
- Nếu danh sách rỗng nghĩa là “không có giá trị nào được phép”, trả về Flux.empty() hoặc xây dựng điều kiện luôn sai.
- Nếu trường không xuất hiện trong request, xử lý riêng với trường xuất hiện nhưng chứa danh sách rỗng nếu API phân biệt hai trạng thái này.

Không nên tự chuyển mọi danh sách rỗng thành không lọc. Trong một endpoint phân quyền, danh sách rỗng có thể phải có nghĩa là không được phép xem bản ghi nào.

### NULL trong tập giá trị

SQL có logic ba giá trị. Nếu danh sách của NOT IN chứa NULL, kết quả có thể trở thành UNKNOWN cho những hàng không khớp giá trị nào. Điều này thường khiến truy vấn trả về ít hàng hơn dự kiến.

Ví dụ:

```sql
SELECT id, status
FROM orders
WHERE status NOT IN ('CANCELLED', NULL);
```

Không nên đưa NULL vào danh sách IN/NOT IN nếu mục tiêu chỉ là so sánh tập giá trị thông thường. Nếu cần bao gồm hoặc loại trừ các hàng có cột NULL, hãy viết điều kiện IS NULL hoặc IS NOT NULL tường minh.

Ví dụ, tìm các đơn hàng không bị hủy và có trạng thái được xác định:

```sql
SELECT id, status
FROM orders
WHERE status IS NOT NULL
  AND status <> 'CANCELLED';
```

## 6. Điều kiện khoảng: BETWEEN

BETWEEN kiểm tra giá trị có nằm trong khoảng giữa hai biên hay không. Trong SQL, BETWEEN bao gồm cả hai đầu mút, tương đương với điều kiện lớn hơn hoặc bằng cận dưới và nhỏ hơn hoặc bằng cận trên.

```sql
SELECT id, name, price
FROM products
WHERE price BETWEEN 100 AND 500;
```

Điều kiện trên tương đương:

```sql
WHERE price >= 100 AND price <= 500
```

Derived query method có thể biểu diễn bằng Between:

```java
Flux<Product> findByPriceBetween(
        BigDecimal minimum,
        BigDecimal maximum);
```

Với Criteria:

```java
Criteria criteria = Criteria.where("price")
    .between(minimum, maximum);

return template.select(Query.query(criteria), Product.class);
```

### Kiểm tra biên trước khi truy vấn

Trước khi tạo truy vấn, hãy xác định:

- Cận dưới có nhỏ hơn hoặc bằng cận trên không?
- Hai biên có được bao gồm không?
- Giá trị đầu vào có cùng kiểu và precision với cột không?
- Nếu một biên bị bỏ qua, đó là khoảng mở hay request không hợp lệ?

Nếu minimum lớn hơn maximum, thông thường nên trả lỗi validation hoặc kết quả rỗng theo hợp đồng đã định. Không nên âm thầm hoán đổi hai biên, vì điều đó có thể che giấu lỗi từ client.

### Khoảng thời gian và nửa mở [start, end)

Với timestamp, một khoảng nửa mở thường dễ kết hợp hơn: bao gồm thời điểm bắt đầu và loại trừ thời điểm kết thúc. Ví dụ lấy sự kiện trong một ngày:

```sql
SELECT id, occurred_at
FROM audit_event
WHERE occurred_at >= :start
  AND occurred_at < :end;
```

Nếu ngày bắt đầu là 2026-11-15 và ngày kế tiếp là 2026-11-16 theo timezone nghiệp vụ, truy vấn dùng [start, end) sẽ lấy toàn bộ thời điểm trong ngày 15, không cần tự tạo giá trị 23:59:59.999999.

Cách này tránh lỗi liên quan đến độ chính xác timestamp khác nhau giữa database, driver và ứng dụng. Khi phân trang theo thời gian, khoảng nửa mở cũng giúp hai cửa sổ liền nhau không bị trùng hoặc bỏ sót ở biên.

Có thể khai báo derived method bằng hai điều kiện:

```java
Flux<AuditEvent> findByOccurredAtGreaterThanEqualAndOccurredAtLessThan(
        LocalDateTime start,
        LocalDateTime end);
```

Nếu truy vấn thời gian theo ngày lịch, cần chuyển ngày và timezone thành start/end cụ thể trước khi gọi repository. Không nên giả định mọi ngày đều có đúng 24 giờ ở những vùng có thay đổi giờ mùa hè.

## 7. Kết hợp tập giá trị với khoảng giá trị

Một truy vấn nghiệp vụ thường kết hợp nhiều loại điều kiện. Ví dụ tìm sản phẩm đang bán, thuộc một số danh mục và có giá trong khoảng:

```java
Flux<Product> findByStatusAndCategoryIdInAndPriceBetween(
        ProductStatus status,
        Collection<Long> categoryIds,
        BigDecimal minimum,
        BigDecimal maximum);
```

Tương đương SQL:

```sql
SELECT id, name, status, category_id, price
FROM products
WHERE status = :status
  AND category_id IN (:categoryIds)
  AND price BETWEEN :minimum AND :maximum;
```

Điều kiện được nối bằng AND nên một bản ghi phải thỏa mãn tất cả. Nếu cần biểu diễn các nhóm OR, hãy dùng Criteria hoặc SQL có dấu ngoặc để tránh thay đổi ý nghĩa do thứ tự ưu tiên toán tử.

Ví dụ, yêu cầu “sản phẩm đang bán có giá trong khoảng, hoặc sản phẩm khuyến mãi bất kể giá” có cấu trúc logic:

```text
(status = ACTIVE AND price BETWEEN min AND max)
OR
(status = PROMOTION)
```

Không nên viết một chuỗi điều kiện dài mà không xác định nhóm logic. Hãy thể hiện nhóm bằng ngoặc trong SQL hoặc tạo các nhóm Criteria riêng.

## 8. Xây dựng truy vấn động bằng Criteria

Derived query method phù hợp khi tập điều kiện tương đối cố định. Khi request có nhiều bộ lọc tùy chọn, một phương thức có thể phải có quá nhiều biến thể. Criteria cho phép thêm điều kiện khi tham số thực sự được cung cấp.

Ví dụ, tìm sản phẩm theo trạng thái bắt buộc, đồng thời có thể lọc theo giá tối thiểu, giá tối đa và tập danh mục:

```java
public Flux<Product> search(
        ProductStatus status,
        BigDecimal minimumPrice,
        BigDecimal maximumPrice,
        Collection<Long> categoryIds) {

    Criteria criteria = Criteria.where("status").is(status);

    if (minimumPrice != null) {
        criteria = criteria.and("price").greaterThanOrEquals(minimumPrice);
    }

    if (maximumPrice != null) {
        criteria = criteria.and("price").lessThanOrEquals(maximumPrice);
    }

    if (categoryIds != null && !categoryIds.isEmpty()) {
        criteria = criteria.and("categoryId").in(categoryIds);
    }

    Query query = Query.query(criteria)
        .sort(Sort.by(Sort.Direction.ASC, "price"));

    return template.select(query, Product.class);
}
```

Trong ví dụ:

- Trạng thái luôn là điều kiện bắt buộc.
- Giá tối thiểu chỉ được thêm khi request có giá trị.
- Giá tối đa chỉ được thêm khi request có giá trị.
- Bộ lọc danh mục được thêm khi danh sách có phần tử.
- Sắp xếp dùng property price của entity.

Đoạn code minh họa trường hợp danh sách danh mục rỗng có nghĩa là không lọc theo danh mục. Nếu hợp đồng API quy định danh sách rỗng có nghĩa là không có danh mục hợp lệ, cần trả kết quả rỗng thay vì bỏ điều kiện.

### Phân biệt bộ lọc không được gửi với bộ lọc có giá trị NULL

Với một bộ lọc tùy chọn, có ba tình huống:

- Không có bộ lọc: bỏ điều kiện.
- Có bộ lọc và có giá trị: so sánh với giá trị đó.
- Có bộ lọc và yêu cầu tìm các hàng có SQL NULL: dùng điều kiện IS NULL.

Một biến Java null thường không đủ để biểu diễn cả ba trạng thái. DTO tìm kiếm cần có hợp đồng rõ ràng; nếu client cần yêu cầu tìm NULL, hãy dùng cờ hoặc biểu diễn điều kiện riêng thay vì mặc định coi mọi null là “bỏ qua”.

## 9. Dùng DatabaseClient khi cần SQL tường minh

Với truy vấn phức tạp, có thể viết SQL trực tiếp qua DatabaseClient. Các giá trị đầu vào phải được bind thay vì nối vào chuỗi SQL.

Ví dụ tìm sản phẩm trong khoảng giá và theo trạng thái:

```java
import java.math.BigDecimal;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Repository;

import reactor.core.publisher.Flux;

@Repository
public class ProductSqlRepository {

    private final DatabaseClient databaseClient;

    public ProductSqlRepository(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Flux<ProductSummary> findByPriceRange(
            ProductStatus status,
            BigDecimal minimum,
            BigDecimal maximum) {

        return databaseClient.sql("""
                SELECT id, name, price, status
                FROM products
                WHERE status = :status
                  AND price >= :minimum
                  AND price <= :maximum
                ORDER BY price ASC
                """)
            .bind("status", status.name())
            .bind("minimum", minimum)
            .bind("maximum", maximum)
            .map((row, metadata) -> new ProductSummary(
                row.get("id", UUID.class),
                row.get("name", String.class),
                row.get("price", BigDecimal.class),
                ProductStatus.valueOf(row.get("status", String.class))
            ))
            .all();
    }
}
```

Bind parameter có một số lợi ích:

- Driver xử lý giá trị theo kiểu dữ liệu tương ứng.
- Dữ liệu đầu vào không thể thay đổi cấu trúc SQL như khi nối chuỗi.
- Truy vấn rõ ràng về điều kiện và kiểu dữ liệu.
- Có thể giúp database/driver tái sử dụng kế hoạch hoặc statement tùy cơ chế thực thi.

Không nối trực tiếp chuỗi do client gửi vào câu SQL. Bind parameter dành cho giá trị, không dành cho tên bảng, tên cột hay từ khóa SQL. Nếu cần sắp xếp động, hãy ánh xạ lựa chọn của client qua danh sách tên property/cột được cho phép rồi mới xây dựng phần ORDER BY.

## 10. NULL và logic ba giá trị trong SQL

SQL không dùng logic boolean hai giá trị đơn giản khi có NULL. Một phép so sánh với NULL thường tạo ra UNKNOWN thay vì TRUE hoặc FALSE.

Ví dụ:

```sql
SELECT id
FROM products
WHERE discontinued_at = NULL;
```

Truy vấn trên không tìm được các hàng có discontinued_at là NULL. Cần dùng:

```sql
SELECT id
FROM products
WHERE discontinued_at IS NULL;
```

Tương tự, dùng IS NOT NULL để chọn các hàng có giá trị.

Trong derived query method, có thể khai báo:

```java
Flux<Product> findByDiscontinuedAtIsNull();

Flux<Product> findByDiscontinuedAtIsNotNull();
```

Với Criteria:

```java
Criteria criteria = Criteria.where("discontinuedAt").isNull();

Criteria hasDate = Criteria.where("discontinuedAt").isNotNull();
```

Đừng thay điều kiện NULL bằng phép so sánh với chuỗi rỗng, số 0 hoặc giá trị giả. Những giá trị này có ý nghĩa riêng và có thể là dữ liệu hợp lệ.

### NOT IN và NULL

Một lỗi phổ biến là dùng NOT IN với danh sách có chứa NULL. Do logic ba giá trị, các phép so sánh không xác định có thể khiến điều kiện không trả về hàng như dự kiến.

Nếu cần loại trừ một tập trạng thái và vẫn giữ các hàng có trạng thái NULL, hãy viết rõ:

```sql
WHERE status IS NULL
   OR status NOT IN ('CANCELLED', 'ARCHIVED')
```

Nếu không muốn lấy hàng NULL, dùng:

```sql
WHERE status IS NOT NULL
  AND status NOT IN ('CANCELLED', 'ARCHIVED')
```

Chính sách này phải xuất phát từ nghiệp vụ. Đừng thêm hoặc bỏ nhánh IS NULL chỉ để truy vấn “có kết quả”.

## 11. Kiểm soát thứ tự và nhóm điều kiện

Một truy vấn có AND và OR cần thể hiện rõ nhóm logic. Ví dụ, chọn sản phẩm đang bán trong khoảng giá hoặc sản phẩm được gắn cờ nổi bật:

```sql
WHERE (status = 'ACTIVE' AND price BETWEEN 100 AND 500)
   OR featured = TRUE
```

Khi tạo Criteria, hãy nhóm điều kiện thành các đối tượng rõ ràng và kết hợp AND/OR theo API mà phiên bản Spring Data hỗ trợ. Nếu biểu thức trở nên khó đọc, SQL tường minh với dấu ngoặc thường dễ kiểm tra hơn.

## 12. Property name, column name và kiểu dữ liệu

Criteria và derived query method thường tham chiếu property của entity, không phải tên cột vật lý trong database.

Ví dụ entity:

```java
@Table("products")
public record Product(
    @Id UUID id,
    @Column("unit_price") BigDecimal price,
    @Column("created_at") LocalDateTime createdAt
) {}
```

Trong repository, dùng property Java:

```java
Flux<Product> findByPriceGreaterThan(BigDecimal minimum);

Flux<Product> findByCreatedAtAfter(LocalDateTime moment);
```

Trong Criteria, cũng tham chiếu property:

```java
Criteria.where("price").greaterThan(minimum);
```

Khi viết SQL tường minh qua DatabaseClient, dùng tên cột thật:

```sql
SELECT id, unit_price, created_at
FROM products
WHERE unit_price > :minimum;
```

Nhầm property name với column name có thể khiến query method không phân giải được thuộc tính hoặc khiến SQL tường minh báo lỗi cột không tồn tại.

Kiểu tham số cũng cần tương thích với kiểu cột. Ví dụ, so sánh NUMERIC với BigDecimal, timestamp với kiểu thời gian đã được mapping, enum với cách lưu enum mà schema đang sử dụng. Nếu cần converter tùy chỉnh, hãy kiểm tra cả thao tác ghi lẫn điều kiện truy vấn.

## 13. Hiệu năng: chọn điều kiện và index phù hợp

Điều kiện đúng về logic chưa chắc đã chạy nhanh. Khi dữ liệu tăng, database cần chọn cách tìm hàng phù hợp dựa trên index, thống kê và kế hoạch thực thi.

Một số nguyên tắc:

- Tạo index cho các cột thường xuyên được dùng để lọc hoặc nối bảng, dựa trên workload thực tế.
- Với index ghép, thứ tự cột cần phản ánh các điều kiện truy vấn phổ biến và khả năng lọc của từng cột.
- Tránh áp dụng hàm lên cột trong WHERE nếu muốn tận dụng index thông thường, trừ khi có functional index phù hợp.
- Chỉ chọn các cột cần thiết thay vì luôn SELECT toàn bộ dữ liệu.
- Kiểm tra query plan với lượng dữ liệu đại diện; không suy luận hiệu năng chỉ từ số lượng điều kiện.

Ví dụ, truy vấn phổ biến lọc theo trạng thái và khoảng giá:

```sql
SELECT id, name, price
FROM products
WHERE status = 'ACTIVE'
  AND price >= 100
  AND price < 500;
```

Một index ghép có thể đáng cân nhắc:

```sql
CREATE INDEX idx_products_status_price
    ON products (status, price);
```

Đây chỉ là ví dụ thiết kế. Index phù hợp phụ thuộc tần suất từng truy vấn, phân bố giá trị, số lượng bản ghi, cách database tối ưu và chi phí ghi thêm index. Một index cho mỗi bộ lọc sẽ làm tăng dung lượng và chi phí insert/update.

### Tránh biến cột trong điều kiện nếu không cần

Điều kiện như:

```sql
WHERE LOWER(email) = LOWER(:email)
```

có thể không dùng được index thường trên email nếu database không có functional index tương ứng. Nếu tìm kiếm không phân biệt hoa thường là yêu cầu phổ biến, hãy cân nhắc collation phù hợp, cột chuẩn hóa hoặc functional index theo hệ quản trị.

Tương tự, việc chuyển đổi kiểu dữ liệu ngay trong WHERE có thể làm giảm khả năng sử dụng index hoặc tạo ra phép so sánh không mong muốn. Hãy bind tham số với kiểu phù hợp với cột.

## 14. Kiểm thử điều kiện và biên giá trị

Các truy vấn so sánh cần được kiểm thử ở cả bên trong, bên ngoài và đúng biên của điều kiện.

Với khoảng giá từ 100 đến 500 dùng BETWEEN:

| Giá trị | Kết quả mong đợi |
| --- | --- |
| 99.99 | Không khớp |
| 100.00 | Khớp |
| 250.00 | Khớp |
| 500.00 | Khớp |
| 500.01 | Không khớp |

Với khoảng thời gian nửa mở [start, end):

| Thời điểm | Kết quả mong đợi |
| --- | --- |
| Trước start | Không khớp |
| Đúng start | Khớp |
| Nằm giữa start và end | Khớp |
| Đúng end | Không khớp |
| Sau end | Không khớp |

Với tập giá trị, cần kiểm tra:

- Danh sách có một phần tử.
- Danh sách có nhiều phần tử.
- Danh sách rỗng.
- Danh sách không được gửi.
- Danh sách chứa NULL nếu API cho phép đầu vào đó.
- Giá trị cột trong database là NULL.

Có thể dùng StepVerifier để kiểm tra publisher:

```java
@Test
void findsProductsWithinInclusivePriceRange() {
    StepVerifier.create(
            repository.findByPriceBetween(
                new BigDecimal("100.00"),
                new BigDecimal("500.00")
            )
        )
        .expectNextMatches(product ->
            product.price().compareTo(new BigDecimal("100.00")) >= 0
                && product.price().compareTo(new BigDecimal("500.00")) <= 0
        )
        .verifyComplete();
}
```

Ví dụ giả định repository và dữ liệu kiểm thử đã được cấu hình. Khi so sánh BigDecimal trong Java, dùng compareTo để so sánh giá trị số; equals còn xét scale, nên 100.0 và 100.00 có thể không bằng nhau theo equals.

Với repository query method và Criteria, nên có integration test trên loại database thực tế. Test bằng mock chỉ xác nhận service gọi đúng method, không chứng minh SQL được sinh ra có đúng ngữ nghĩa hoặc driver bind kiểu dữ liệu chính xác.

## 15. Các lỗi thường gặp khi xây dựng điều kiện

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng GreaterThan khi nghiệp vụ cần bao gồm biên | Bỏ sót bản ghi đúng bằng ngưỡng. | Dùng GreaterThanEqual hoặc LessThanEqual phù hợp. |
| Nghĩ BETWEEN loại trừ hai đầu | Bản ghi đúng bằng cận bị hiểu sai. | Nhớ BETWEEN bao gồm cả cận dưới và cận trên. |
| Dùng BETWEEN cho ngày kết thúc cả ngày bằng timestamp cuối ngày | Có thể bỏ sót dữ liệu do độ chính xác timestamp. | Dùng khoảng nửa mở start-inclusive, end-exclusive. |
| Dùng NOT IN với danh sách chứa NULL | Kết quả có thể thành UNKNOWN và loại bỏ nhiều hàng. | Loại NULL khỏi tập hoặc thêm điều kiện IS NULL rõ ràng. |
| Không xác định ngữ nghĩa danh sách rỗng | Truy vấn có thể sai hoặc hành vi khác nhau theo driver/database. | Quyết định rõ bỏ bộ lọc hay trả kết quả rỗng. |
| So sánh cột với = NULL | Không tìm được hàng có giá trị NULL. | Dùng IS NULL hoặc IS NOT NULL. |
| Nối giá trị người dùng vào SQL | Có nguy cơ SQL injection và lỗi quoting. | Dùng bind parameter. |
| Dùng tên cột trong derived method | Spring Data không tìm thấy property tương ứng. | Dùng tên property của entity. |
| Trộn AND và OR không có nhóm rõ ràng | Logic lọc khác với yêu cầu nghiệp vụ. | Dùng ngoặc hoặc nhóm Criteria tường minh. |
| Dùng double cho tiền | Có thể xuất hiện sai số so sánh. | Dùng BigDecimal và precision/scale phù hợp. |

## 16. Quy trình thiết kế một bộ lọc động

Khi xây dựng endpoint tìm kiếm hoặc repository query, có thể thực hiện theo trình tự:

1. **Viết quy tắc bằng ngôn ngữ nghiệp vụ:** xác định điều kiện nào bắt buộc, điều kiện nào tùy chọn.
2. **Chọn toán tử:** bằng, khác, lớn hơn, lớn hơn hoặc bằng, nhỏ hơn, IN, NOT IN hay BETWEEN.
3. **Xác định biên:** khoảng có bao gồm hai đầu không; với thời gian có nên dùng khoảng nửa mở không?
4. **Xác định null semantics:** giá trị null nghĩa là bỏ bộ lọc, tìm cột NULL hay dữ liệu không hợp lệ?
5. **Xác định tập rỗng:** danh sách rỗng nghĩa là không giới hạn hay không có kết quả?
6. **Chọn cách triển khai:** derived query method cho truy vấn cố định; Criteria cho điều kiện tùy chọn; DatabaseClient cho SQL cần kiểm soát trực tiếp.
7. **Bind tham số an toàn:** không nối chuỗi dữ liệu đầu vào vào SQL.
8. **Kiểm tra property và kiểu dữ liệu:** đối chiếu entity mapping, kiểu cột và converter.
9. **Đánh giá index:** kiểm tra query plan và workload thực tế.
10. **Kiểm thử biên:** kiểm tra giá trị ngay dưới, đúng bằng và ngay trên ngưỡng; kiểm tra NULL và tập rỗng.

Điều kiện so sánh, tập giá trị và khoảng giá trị là nền tảng của truy vấn động. Spring Data R2DBC cho phép diễn đạt chúng bằng tên repository method, Criteria hoặc SQL tường minh. Khi xác định đúng ngữ nghĩa toán tử, xử lý rõ NULL và biên, bind tham số an toàn và kiểm thử trên database thực tế, các bộ lọc sẽ cho kết quả nhất quán và dễ bảo trì.

