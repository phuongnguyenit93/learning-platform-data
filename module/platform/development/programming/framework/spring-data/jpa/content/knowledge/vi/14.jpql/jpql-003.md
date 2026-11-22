# SELECT, WHERE, ORDER BY và biểu thức điều kiện trong JPQL

JPQL (Jakarta Persistence Query Language) là ngôn ngữ truy vấn hướng entity của JPA. JPQL dùng tên entity và thuộc tính Java trong mô hình persistence, sau đó provider như Hibernate chuyển truy vấn thành SQL phù hợp database. Vì vậy, JPQL thường không dùng trực tiếp tên bảng hoặc tên cột vật lý.

Ba phần cơ bản của một truy vấn đọc là:

- **SELECT** xác định dữ liệu cần trả về: entity, thuộc tính đơn, nhiều giá trị hoặc DTO.
- **WHERE** lọc các hàng theo điều kiện logic.
- **ORDER BY** sắp xếp kết quả theo thuộc tính hoặc biểu thức.

Biểu thức điều kiện gồm phép so sánh, toán tử logic, kiểm tra NULL, BETWEEN, IN, LIKE, EXISTS và các biểu thức khác. Hiểu đúng kiểu dữ liệu, null semantics và parameter binding giúp truy vấn chính xác, an toàn và dễ tối ưu.

Tài liệu dùng Jakarta Persistence với namespace `jakarta.persistence` trong Spring Boot 3 / Spring Framework 6 trở lên. Dự án Spring Boot 2 cũ thường dùng `javax.persistence`.

## 1. JPQL khác SQL như thế nào?

Giả sử entity:

```java
@Entity
@Table(name = "product")
public class Product {
    @Id
    private Long id;

    private String name;

    private BigDecimal price;

    private Boolean active;

    @Column(name = "created_at")
    private Instant createdAt;
}
```

SQL truy vấn bảng và cột:

```sql
select p.id, p.name
from product p
where p.price >= 100
order by p.name;
```

JPQL truy vấn entity và thuộc tính:

```jpql
select p
from Product p
where p.price >= 100
order by p.name
```

Các điểm khác nhau:

- `Product` là entity name; mặc định là tên class entity, không phải tên bảng.
- `p.price`, `p.name` là thuộc tính Java được mapping, không phải tên cột vật lý.
- JPQL hiểu quan hệ entity và có thể điều hướng association.
- JPQL không viết `select *`.
- JPQL không viết tên bảng vật lý trong `FROM`, trừ khi dùng native SQL qua API riêng.
- JPQL được kiểm tra theo mô hình entity và provider chuyển thành SQL theo dialect.

JPQL keyword thường không phân biệt hoa thường, nhưng tên entity, alias và thuộc tính nên được viết đúng casing như trong mapping. Tên entity có thể được tùy chỉnh bằng `@Entity(name = "...")`; khi đó JPQL dùng entity name đã khai báo.

## 2. Cấu trúc truy vấn SELECT cơ bản

Một JPQL select query có hình dạng tổng quát:

```jpql
SELECT [DISTINCT] select_item
FROM entity_name identification_variable
[JOIN ...]
[WHERE conditional_expression]
[GROUP BY ...]
[HAVING ...]
[ORDER BY ...]
```

Phần bài học này tập trung vào SELECT, WHERE, ORDER BY và biểu thức điều kiện. GROUP BY/HAVING là chủ đề riêng, chỉ xuất hiện khi cần phân biệt kết quả tổng hợp.

Ví dụ:

```jpql
select p
from Product p
where p.active = true
order by p.createdAt desc, p.id desc
```

- `Product p`: khai báo entity range variable `p`.
- `select p`: trả về entity Product.
- `where p.active = true`: chỉ lấy sản phẩm đang hoạt động.
- `order by p.createdAt desc, p.id desc`: sắp xếp mới nhất trước; nếu cùng thời điểm thì ID lớn hơn trước.

Alias `p` giúp tham chiếu thuộc tính. Alias có thể là một chữ hoặc tên có ý nghĩa như `product`, nhưng tránh trùng keyword.

## 3. Các kiểu kết quả của SELECT

### 3.1. Trả về entity

```jpql
select p
from Product p
where p.active = true
```

Với repository:

```java
@Query("""
    select p
    from Product p
    where p.active = true
    order by p.name asc, p.id asc
    """)
List<Product> findActiveProducts();
```

Kết quả là entity Product. Nếu được nạp trong transaction/persistence context, entity có thể ở trạng thái managed và thay đổi thuộc tính sẽ được dirty checking.

Không nên trả entity ra ngoài service boundary rồi serialize tùy tiện nếu entity có lazy association. Dùng DTO/projection khi API chỉ cần một phần dữ liệu.

### 3.2. Trả về một thuộc tính đơn

```jpql
select p.name
from Product p
where p.active = true
order by p.name
```

Repository:

```java
@Query("""
    select p.name
    from Product p
    where p.active = true
    order by p.name
    """)
List<String> findActiveProductNames();
```

Kiểu kết quả phải khớp với thuộc tính được chọn. Nếu chọn `p.price`, kiểu kết quả có thể là BigDecimal; nếu chọn `p.id`, kiểu tương ứng là Long.

### 3.3. Chọn nhiều giá trị

Khi SELECT nhiều biểu thức mà không dùng DTO constructor expression, kết quả thường là `Object[]` cho mỗi hàng:

```jpql
select p.id, p.name, p.price
from Product p
where p.active = true
```

Có thể nhận:

```java
List<Object[]> rows = query.getResultList();
for (Object[] row : rows) {
    Long id = (Long) row[0];
    String name = (String) row[1];
    BigDecimal price = (BigDecimal) row[2];
}
```

Cách này nhanh để minh họa nhưng ít an toàn về kiểu và dễ sai index. Trong ứng dụng thật, DTO projection thường rõ ràng hơn.

### 3.4. DISTINCT

`DISTINCT` loại kết quả trùng theo ngữ nghĩa của select item:

```jpql
select distinct p.category
from Product p
where p.active = true
```

Với entity và JOIN, DISTINCT thường được dùng để tránh entity bị lặp trong kết quả do một hàng cha khớp nhiều hàng con. Cần phân biệt việc loại trùng ở kết quả JPQL với việc database có thể trả nhiều hàng sau JOIN; provider có thể xử lý distinct ở SQL hoặc ở tầng kết quả tùy truy vấn/phiên bản.

Không thêm DISTINCT theo thói quen mà không hiểu vì sao JOIN tạo bản ghi lặp. DISTINCT có thể làm query nặng hơn và không sửa được một JOIN sai cardinality.

## 4. DTO projection bằng constructor expression

JPQL hỗ trợ constructor expression với cú pháp `select new fully.qualified.Dto(...)`. DTO cần constructor phù hợp với thứ tự và kiểu các biểu thức.

```java
package com.example.product;

public record ProductSummary(
    Long id,
    String name,
    BigDecimal price
) {}
```

JPQL:

```java
@Query("""
    select new com.example.product.ProductSummary(
        p.id, p.name, p.price
    )
    from Product p
    where p.active = true
    order by p.name asc, p.id asc
    """)
List<ProductSummary> findActiveSummaries();
```

Với record Java, canonical constructor có thể được sử dụng nếu provider hỗ trợ đúng constructor expression và kiểu tham số. Tên class trong JPQL phải là fully qualified class name; JPQL không dùng cú pháp `new ProductSummary(...)` nếu class không được định danh đầy đủ.

DTO projection giúp:

- Chỉ lấy những cột cần thiết.
- Tránh đưa entity managed/lazy proxy ra ngoài service.
- Tạo kết quả ổn định cho API/report.
- Giảm dữ liệu truyền từ database khi query không cần toàn bộ entity.

## 5. WHERE và phép so sánh

WHERE nhận một conditional expression trả về giá trị logic. Các phép so sánh cơ bản:

| Toán tử | Ý nghĩa | Ví dụ |
|---|---|---|
| `=` | Bằng | `p.status = :status` |
| `<>` | Khác | `p.status <> :status` |
| `>` | Lớn hơn | `p.price > :min` |
| `>=` | Lớn hơn hoặc bằng | `p.price >= :min` |
| `<` | Nhỏ hơn | `p.createdAt < :cutoff` |
| `<=` | Nhỏ hơn hoặc bằng | `p.price <= :max` |

Ví dụ:

```jpql
select p
from Product p
where p.price >= :minPrice
  and p.price <= :maxPrice
```

Không so sánh hai kiểu không tương thích. Ví dụ không nên so sánh một thuộc tính LocalDate với một chuỗi tùy ý hoặc so sánh enum với tên bảng. Parameter type cần phù hợp với thuộc tính entity.

## 6. AND, OR, NOT và dấu ngoặc

JPQL hỗ trợ các toán tử logic:

- `AND`: cả hai điều kiện phải đúng.
- `OR`: ít nhất một điều kiện đúng.
- `NOT`: phủ định điều kiện.

Thứ tự ưu tiên logic thông thường là NOT, AND, OR. Khi biểu thức có nhiều toán tử, dùng ngoặc để làm rõ ý định:

```jpql
select p
from Product p
where p.active = true
  and (p.category = :category or p.featured = true)
```

Nếu bỏ ngoặc:

```jpql
where p.active = true
  and p.category = :category
   or p.featured = true
```

Thì OR có thể làm truy vấn trả cả sản phẩm featured dù active=false, vì AND có độ ưu tiên cao hơn OR. Đây là lỗi logic thường gặp.

Với nhiều filter tùy chọn, biểu thức có thể dài và khó bảo trì. Hãy cân nhắc Specification, Criteria API hoặc xây dựng query động thay vì tạo một WHERE với hàng chục nhánh OR.

## 7. NULL và logic ba giá trị

SQL/JPQL có logic ba giá trị: TRUE, FALSE và UNKNOWN. Khi một toán hạng là NULL, phép so sánh thông thường thường cho UNKNOWN, không phải TRUE/FALSE.

Sai:

```jpql
where p.description = null
```

Đúng:

```jpql
where p.description is null
```

Kiểm tra khác NULL:

```jpql
where p.description is not null
```

Ví dụ kết hợp:

```jpql
select p
from Product p
where p.deletedAt is null
  and p.price is not null
```

Không dùng `= null` hoặc `<> null`. Dùng `IS NULL` và `IS NOT NULL`.

Nếu parameter có thể null, mẫu thường gặp:

```jpql
where (:status is null or p.status = :status)
```

Nếu status null, filter bị bỏ qua; nếu có giá trị, chỉ lấy status khớp. Mẫu này tiện nhưng OR có thể làm optimizer khó dùng index trong một số database. Với nhiều filter tùy chọn hoặc dữ liệu lớn, query động/Specification có thể tạo predicate gọn hơn.

## 8. BETWEEN

`BETWEEN` kiểm tra giá trị nằm trong khoảng bao gồm cả hai biên:

```jpql
select p
from Product p
where p.price between :minPrice and :maxPrice
```

Tương đương về ý nghĩa:

```jpql
where p.price >= :minPrice
  and p.price <= :maxPrice
```

Với ngày giờ, cần chú ý biên cuối. Nếu lọc dữ liệu trong một ngày, dùng khoảng nửa mở thường an toàn hơn:

```jpql
where p.createdAt >= :start
  and p.createdAt < :nextDay
```

Cách này tránh vấn đề precision của timestamp và không cần đoán giá trị “cuối ngày” là 23:59:59.999.

## 9. IN và NOT IN

`IN` kiểm tra một giá trị có nằm trong danh sách hoặc kết quả subquery hay không:

```jpql
select p
from Product p
where p.status in :statuses
```

Repository:

```@Query("""
    select p
    from Product p
    where p.status in :statuses
    """)
List<Product> findByStatuses(
    @Param("statuses") Collection<ProductStatus> statuses
);
```

Có thể dùng NOT IN:

```jpql
where p.status not in :excludedStatuses
```

Lưu ý:

- Collection parameter rỗng có thể được provider xử lý khác nhau hoặc tạo SQL không hợp lệ. Hãy kiểm tra danh sách trước khi gọi query; nếu rỗng, quyết định rõ trả empty hay bỏ filter.
- Nếu danh sách rất lớn, có thể vượt giới hạn bind parameter của database/driver. Chia chunk hoặc dùng bảng tạm/array/table-valued parameter theo database.
- `NOT IN` kết hợp với NULL trong danh sách có thể tạo kết quả UNKNOWN và khiến không hàng nào khớp như kỳ vọng. Làm sạch NULL khỏi danh sách hoặc dùng NOT EXISTS khi phù hợp.

## 10. LIKE và tìm kiếm chuỗi

`LIKE` hỗ trợ wildcard:

- `%`: khớp chuỗi có độ dài bất kỳ, kể cả rỗng.
- `_`: khớp đúng một ký tự.

Ví dụ tìm tên bắt đầu bằng prefix:

```jpql
select p
from Product p
where p.name like :pattern
```

Truyền `pattern = "Sam%"` qua parameter. Tìm chứa từ khóa dùng `"%Sam%"`; tìm kết thúc bằng suffix dùng `"%Sam"`.

Có thể dùng `ESCAPE` khi muốn tìm ký tự wildcard như dữ liệu thường:

```jpql
where p.name like :pattern escape '\\'
```

Nếu cần tìm chuỗi có dấu phần trăm hoặc gạch dưới do người dùng nhập, hãy escape wildcard và ký tự escape trước khi thêm wildcard của ứng dụng.

JPQL hỗ trợ `LOWER` và `UPPER`:

```jpql
where lower(p.name) like lower(:pattern)
```

Dùng function trên cột có thể làm database khó sử dụng index thường. Với tìm kiếm không phân biệt hoa thường ở dữ liệu lớn, cân nhắc functional index, collation hoặc cột chuẩn hóa theo database.

## 11. EXISTS, IS EMPTY và MEMBER OF

### EXISTS

`EXISTS` kiểm tra subquery có ít nhất một hàng:

```jpql
select c
from Customer c
where exists (
    select o.id
    from Order o
    where o.customer = c
)
```

Đây là cách lấy Customer có ít nhất một Order mà không cần trả về từng cặp Customer/Order. EXISTS thường phù hợp với câu hỏi dạng “có hay không”, nhưng hiệu năng vẫn phụ thuộc query plan và index.

### IS EMPTY

Dùng với collection-valued association:

```jpql
select c
from Customer c
where c.orders is empty
```

Ngược lại:

```jpql
where c.orders is not empty
```

### MEMBER OF

Kiểm tra một phần tử có thuộc collection association:

```jpql
select c
from Customer c
where :order member of c.orders
```

Parameter phải là entity tương thích với phần tử collection. Với association phức tạp, JOIN tường minh hoặc EXISTS có thể dễ tối ưu và dễ đọc hơn.

## 12. Biểu thức số học và chuỗi

JPQL hỗ trợ biểu thức số học trên kiểu dữ liệu phù hợp:

```jpql
select p
from Product p
where p.price * p.stockQuantity > :threshold
```

Các phép toán thường dùng:

- `+`: cộng.
- `-`: trừ.
- `*`: nhân.
- `/`: chia.

Biểu thức phải tương thích kiểu. Chia số nguyên có thể cho kết quả khác kỳ vọng tùy kiểu và database; nếu cần precision tiền tệ, dùng BigDecimal và kiểm tra kiểu mapping.

Nối chuỗi portable nên dùng `CONCAT`:

```jpql
select concat(p.code, '-', p.name)
from Product p
```

Không dựa vào toán tử nối chuỗi riêng của một database trong JPQL portable.

## 13. Hàm JPQL phổ biến

Một số hàm chuẩn hữu ích:

| Hàm | Mục đích | Ví dụ |
|---|---|---|
| `CONCAT(a, b)` | Nối chuỗi | `concat(p.code, p.name)` |
| `LOWER(x)` | Chuyển chữ thường | `lower(p.name)` |
| `UPPER(x)` | Chuyển chữ hoa | `upper(p.name)` |
| `TRIM(x)` | Bỏ khoảng trắng hai đầu | `trim(p.name)` |
| `LENGTH(x)` | Độ dài chuỗi | `length(p.name) > 3` |
| `LOCATE(a, b)` | Vị trí chuỗi con | `locate('Pro', p.name) > 0` |
| `SUBSTRING(x, start, len)` | Lấy chuỗi con | `substring(p.code, 1, 3)` |
| `ABS(x)` | Giá trị tuyệt đối | `abs(p.balance)` |
| `SQRT(x)` | Căn bậc hai | `sqrt(p.area)` |
| `MOD(x, y)` | Phần dư | `mod(p.quantity, 2) = 0` |
| `COALESCE(a, b)` | Giá trị đầu tiên khác NULL | `coalesce(p.nickname, p.name)` |
| `NULLIF(a, b)` | Trả NULL nếu hai giá trị bằng nhau | `nullif(p.score, 0)` |

Hàm ngày giờ chuẩn thường dùng:

```jpql
select p
from Product p
where p.createdAt < CURRENT_TIMESTAMP
```

Một số hàm database-specific không thuộc tập portable của JPQL. Hibernate hỗ trợ thêm nhiều function; có thể gọi function qua `FUNCTION('function_name', ...)` trong JPQL, nhưng khi dùng cần chấp nhận phụ thuộc database/provider và kiểm thử SQL được sinh.

## 14. CASE, COALESCE và biểu thức điều kiện

JPQL hỗ trợ CASE expression:

```jpql
select
    p.id,
    case
        when p.stockQuantity = 0 then 'OUT_OF_STOCK'
        when p.stockQuantity < 5 then 'LOW_STOCK'
        else 'AVAILABLE'
    end
from Product p
```

Có thể dùng trong WHERE:

```jpql
where case
        when p.active = true then p.price
        else 0
      end >= :minPrice
```

Tuy nhiên, biểu thức CASE trong WHERE có thể khiến query khó tối ưu hơn so với predicate trực tiếp:

```jpql
where p.active = true
  and p.price >= :minPrice
```

Dùng CASE khi thực sự cần tính giá trị theo điều kiện, ví dụ tạo nhãn trong projection hoặc sắp xếp theo nhóm.

COALESCE xử lý giá trị NULL:

```jpql
select coalesce(p.nickname, p.name)
from Person p
```

Nếu nickname null, query trả name. `NULLIF` có thể tránh chia cho 0:

```jpql
select p.total / nullif(p.quantity, 0)
from ProductMetric p
```

Kết quả của phép chia khi quantity bằng 0 sẽ là NULL thay vì lỗi chia cho 0, tùy kiểu và database hỗ trợ.

## 15. ORDER BY và thứ tự kết quả

ORDER BY sắp xếp kết quả theo một hoặc nhiều biểu thức:

```jpql
select p
from Product p
where p.active = true
order by p.createdAt desc, p.name asc, p.id asc
```

- `ASC`: tăng dần, là mặc định.
- `DESC`: giảm dần.
- Có thể sắp xếp nhiều tiêu chí; tiêu chí sau chỉ dùng khi các tiêu chí trước bằng nhau.
- Thứ tự các hàng không được bảo đảm nếu không có ORDER BY.

Nên thêm một tiêu chí unique như ID ở cuối để có thứ tự ổn định khi phân trang:

```jpql
order by p.createdAt desc, p.id desc
```

Nếu chỉ sắp xếp theo createdAt và nhiều hàng có cùng thời điểm, thứ tự giữa các hàng đó không xác định. Điều này có thể làm dữ liệu xuất hiện lặp hoặc bị bỏ qua giữa các trang khi dữ liệu thay đổi.

### 15.1. Sắp xếp theo biểu thức

JPQL có thể sắp xếp theo state field path expression hoặc scalar expression hợp lệ:

```jpql
select p
from Product p
order by lower(p.name) asc
```

Với constructor projection hoặc select item có result variable, có thể dùng alias trong ORDER BY khi biểu thức hợp lệ theo JPQL:

```jpql
select p.name as productName
from Product p
order by productName asc
```

Không dùng tên cột SQL như `product_name` trong JPQL trừ khi đó là tên thuộc tính Java/entity mapping thực sự.

### 15.2. NULL trong ORDER BY

Vị trí NULL (đầu hay cuối) có thể khác nhau giữa database. JPQL portable không cung cấp một cú pháp NULLS FIRST/LAST được hỗ trợ đồng nhất trong mọi provider/version. Hibernate hoặc database có thể hỗ trợ extension.

Nếu cần portable, có thể dùng CASE:

```jpql
order by
    case when p.createdAt is null then 1 else 0 end asc,
    p.createdAt desc,
    p.id desc
```

Cách này đưa giá trị NULL xuống cuối trong ví dụ. Kiểm tra SQL được sinh và execution plan nếu biểu thức sắp xếp làm database khó sử dụng index.

## 16. Parameter binding: named và positional

Không nối chuỗi input trực tiếp vào JPQL. Dùng parameter binding để tránh injection, xử lý kiểu dữ liệu và tăng khả năng tái sử dụng query plan.

Named parameter:

```java
@Query("""
    select p
    from Product p
    where p.category = :category
      and p.price >= :minPrice
    order by p.price asc, p.id asc
    """)
List<Product> search(
    @Param("category") String category,
    @Param("minPrice") BigDecimal minPrice
);
```

Positional parameter:

```java
@Query("""
    select p
    from Product p
    where p.category = ?1
      and p.price >= ?2
    """)
List<Product> search(String category, BigDecimal minPrice);
```

Named parameter thường dễ đọc và ít nhầm thứ tự hơn khi có nhiều điều kiện. Không trộn cú pháp positional và named trong cùng query nếu không có lý do đặc biệt.

Parameter dùng cho **giá trị**, không dùng để thay tên entity, tên thuộc tính, keyword hay hướng ORDER BY. Ví dụ `order by :column` không biến parameter thành tên thuộc tính. Nếu cần sắp xếp động, dùng Sort/Pageable hoặc xây dựng query động từ whitelist thuộc tính được phép.

## 17. Kết hợp ORDER BY với Pageable và Sort

Spring Data JPA cho phép phân trang và sắp xếp:

```java
Page<Product> findByActiveTrue(Pageable pageable);
```

Gọi:

```java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
    )
);

Page<Product> page = productRepository.findByActiveTrue(pageable);
```

Tên thuộc tính trong Sort là property path của entity, ví dụ `createdAt`, không phải tên cột vật lý `created_at`.

Với `@Query`, Spring Data có thể áp dụng dynamic Sort lên query nếu sort property hợp lệ. Khi query có alias/projection, cần bảo đảm Sort tham chiếu đúng property hoặc alias được hỗ trợ. Không đưa chuỗi sort từ người dùng vào JPQL tùy tiện.

Khác biệt Page và Slice:

- `Page<T>` thường cần tổng số bản ghi, vì vậy có thể phát sinh count query.
- `Slice<T>` chỉ cần biết còn trang tiếp theo hay không, thường tránh count query.
- Cả hai đều cần ORDER BY ổn định để phân trang đáng tin cậy.

Khi join collection, một parent có thể xuất hiện nhiều hàng SQL. Kết hợp fetch join collection với pagination có thể gây cảnh báo hoặc phân trang trong bộ nhớ tùy provider. Hãy kiểm tra query và cân nhắc hai bước: phân trang ID trước, sau đó tải dữ liệu cần thiết.

## 18. DISTINCT, JOIN và kết quả lặp

Khi JOIN một collection, mỗi parent có thể xuất hiện nhiều lần ở kết quả SQL:

```jpql
select c
from Customer c
join c.orders o
where o.status = :status
```

Nếu một Customer có nhiều Order thỏa điều kiện, kết quả có thể có Customer lặp. Dùng DISTINCT nếu mục tiêu là danh sách Customer duy nhất:

```jpql
select distinct c
from Customer c
join c.orders o
where o.status = :status
```

Nếu chỉ cần kiểm tra có ít nhất một Order, EXISTS thường diễn đạt ý định tốt hơn:

```jpql
select c
from Customer c
where exists (
    select o.id
    from Order o
    where o.customer = c
      and o.status = :status
)
```

DISTINCT không phải giải pháp chung cho mọi JOIN. Nó có thể tăng chi phí sort/hash và không giải quyết được việc chọn sai join cardinality.

## 19. Index và hiệu năng của WHERE/ORDER BY

JPQL không trực tiếp tạo index. Index phải được định nghĩa trong schema/migration. Các nguyên tắc:

- Index cột thường dùng trong điều kiện equality và join.
- Composite index nên theo thứ tự cột phù hợp với filter/order thực tế và selectivity.
- Nếu query lọc `category` rồi sắp xếp `created_at`, có thể đánh giá index composite `(category, created_at)`.
- Function trên cột như `lower(name)` có thể cần functional index hoặc collation phù hợp.
- LIKE với wildcard đầu chuỗi như `%term%` thường khó dùng B-tree index thông thường.
- ORDER BY nhiều cột cần xem query plan để quyết định index có hỗ trợ được không.
- Index làm SELECT có thể nhanh hơn nhưng tăng chi phí ghi và dung lượng.

Ví dụ query:

```jpql
select p
from Product p
where p.category = :category
  and p.active = true
order by p.createdAt desc, p.id desc
```

Một index ứng viên có thể là `(category, active, created_at, id)`, nhưng thứ tự và kiểu index tối ưu phụ thuộc database, cardinality và workload. Dùng EXPLAIN/EXPLAIN ANALYZE để kiểm tra thay vì áp dụng máy móc.

## 20. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng tên bảng/cột SQL trong JPQL | JPQL dùng entity name và thuộc tính Java | Dùng entity/field name; nếu cần SQL vật lý, dùng nativeQuery |
| Dùng `= null` | SQL/JPQL null logic không hoạt động như so sánh thông thường | Dùng `IS NULL` hoặc `IS NOT NULL` |
| OR làm mở rộng kết quả ngoài ý muốn | Không nhóm điều kiện bằng ngoặc | Viết lại predicate với parentheses rõ ràng |
| IN với danh sách rỗng | SQL/provider có thể xử lý không như kỳ vọng | Xử lý empty collection ở service trước khi query |
| NOT IN chứa NULL | Logic ba giá trị khiến kết quả UNKNOWN | Loại NULL hoặc cân nhắc NOT EXISTS |
| Sort theo tên cột database | Sort của Spring Data thường dùng property path | Dùng tên thuộc tính entity |
| Pagination có hàng trùng | JOIN collection làm nhân bản kết quả | DISTINCT, EXISTS hoặc phân trang ID trước |
| Page query chậm | Count query và data query đều tốn kém | Dùng Slice nếu không cần total count; tối ưu count riêng |
| ORDER BY không ổn định | Không có tie-breaker unique | Thêm ID hoặc khóa unique vào cuối |
| Function làm mất index | Áp dụng LOWER/UPPER/CAST lên cột | Cân nhắc functional index hoặc chuẩn hóa dữ liệu |

## 21. Quy trình kiểm tra một JPQL query

1. Xác nhận entity name và thuộc tính Java đúng mapping.
2. Xác định SELECT trả entity, scalar, Object[] hay DTO.
3. Viết WHERE theo từng điều kiện nhỏ, dùng parameter binding.
4. Xử lý NULL bằng IS NULL/IS NOT NULL và kiểm tra empty collection.
5. Dùng ngoặc cho các biểu thức AND/OR phức tạp.
6. Thêm ORDER BY rõ ràng, có tie-breaker ổn định khi phân trang.
7. Kiểm tra DISTINCT và cardinality khi có JOIN.
8. Kiểm tra SQL thực tế và bind parameters trong môi trường an toàn.
9. Chạy EXPLAIN/EXPLAIN ANALYZE trên database thật.
10. Viết integration test cho dữ liệu biên: NULL, trùng, rỗng, ngày ở biên và nhiều hàng có cùng giá trị sort.

## 22. Kết luận

SELECT xác định dữ liệu trả về, WHERE xác định predicate lọc, ORDER BY xác định thứ tự và các biểu thức cho phép tính toán/so sánh ngay trong query. JPQL dùng mô hình entity thay cho schema vật lý, vì vậy cần viết đúng entity name, property path và kiểu parameter.

Hãy ưu tiên named parameters, xử lý NULL đúng, nhóm AND/OR bằng ngoặc, tránh IN rỗng, dùng DTO projection khi không cần entity đầy đủ và sắp xếp ổn định khi phân trang. Cuối cùng, luôn kiểm tra SQL và execution plan trên database thực tế; một JPQL ngắn không đồng nghĩa SQL sinh ra sẽ rẻ.
