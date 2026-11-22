# Spring Data JPA: Kiểm thử phân trang, sắp xếp, projection và dữ liệu tổng

## 1. Mục tiêu: chứng minh đúng tập dữ liệu, thứ tự và tổng số

Một endpoint danh sách sản phẩm có thể trả đúng 20 phần tử nhưng vẫn sai hợp đồng vì **thiếu bản ghi, thứ tự không ổn định, tổng số bản ghi bị đếm trùng, projection lộ trường không cần thiết hoặc số liệu tổng hợp không khớp với bộ lọc**.

Khi kiểm thử Spring Data JPA, cần phân biệt bốn câu hỏi:

1. **Phân trang (pagination):** trang này có đúng phần tử, offset, số lượng và thông tin về trang kế tiếp không?
2. **Sắp xếp (sorting):** kết quả tuân thủ `ORDER BY` nào, kể cả khi nhiều bản ghi có cùng giá trị sort?
3. **Projection:** repository có đưa đúng hình dạng dữ liệu cho use case không, thay vì bắt API mang cả JPA entity?
4. **Dữ liệu tổng (totals/aggregates):** `totalElements`, `totalPages`, `COUNT`, `SUM`, tổng theo nhóm có đúng điều kiện lọc, đúng độ chính xác và đúng ý nghĩa không?

Ví dụ một bộ dữ liệu sáu sản phẩm có năm sản phẩm active:

| ID | SKU | Category | Price | Active |
| --- | --- | --- | --- | --- |
| 101 | BOOK-101 | BOOK | 100.00 | true |
| 102 | BOOK-102 | BOOK | 50.00 | true |
| 103 | BOOK-103 | BOOK | 50.00 | true |
| 104 | BOOK-104 | BOOK | 25.00 | false |
| 105 | TOOL-105 | TOOL | 200.00 | true |
| 106 | TOOL-106 | TOOL | 150.00 | true |

Nếu query chỉ lấy `active=true`, sort `price ASC, id ASC`, page size 2, ta kỳ vọng:

~~~text
Page 0: BOOK-102 (50),  BOOK-103 (50)
Page 1: BOOK-101 (100), TOOL-106 (150)
Page 2: TOOL-105 (200)

totalElements = 5
totalPages    = 3
pageSize      = 2
~~~

Khi tổng hợp **chỉ active**:

~~~text
BOOK: count = 3, sum(price) = 200.00
TOOL: count = 2, sum(price) = 350.00
ALL:  count = 5, sum(price) = 550.00
~~~

Bài thực hành sẽ tạo đúng dataset này và dùng `@DataJpaTest` kiểm **repository thật với JPA/Hibernate và H2 test database**, không mock repository. Để kiểm đặc tính SQL riêng của PostgreSQL/MySQL, cần thêm integration test trên database tương ứng.

### Bạn sẽ làm được gì?

- Phân biệt `Page<T>`, `Slice<T>`, `List<T>` và metadata của chúng.
- Dùng `PageRequest.of(page,size,Sort)`, `Sort.Order` và secondary sort theo ID.
- Hiểu khi nào Spring Data tạo/có thể bỏ qua `count query`; khi nào cần `countQuery` riêng.
- Viết closed interface projection, DTO record projection và dynamic projection.
- Kiểm `COUNT`, `SUM`, `GROUP BY`, các nhóm rỗng, dữ liệu âm/nullable và `BigDecimal`.
- Xử lý lỗi 0-based page, size, sort field, join-to-many, N+1, offset drift và dữ liệu thay đổi giữa hai query.
- Có một bộ ví dụ Java 17+/Spring Boot 3.5.x với 10 phương thức JUnit Jupiter thực hành toàn bộ các chủ điểm.

## 2. Cơ chế: Pageable, Sort, Page, Slice và List

Spring Data nhận các **special parameters** như `Pageable` và `Sort` để áp dụng phân trang, sắp xếp mà không cần một cặp repository method cho mỗi số trang.

~~~java
Page<Product> findByActiveTrue(Pageable pageable);
Slice<Product> findByCategory(String category, Pageable pageable);
List<Product> findByCategory(String category, Sort sort);
~~~

Đây là ví dụ **chữ ký method trong một repository interface**, không phải file có thể chạy một mình. Ba cách trả về đều có mục đích riêng.

| Return type | Đưa nội dung trang? | Biết có next? | Biết tổng toàn tập? | Chi phí đặc trưng |
| --- | --- | --- | --- | --- |
| `Page<T>` | Có | Có | **Có:** `totalElements`, `totalPages` | Có thể cần thêm count query |
| `Slice<T>` | Có | Có | **Không** | Thường chỉ cần hỏi đủ dữ liệu để biết còn next |
| `List<T>` + `Pageable` | Có nhưng không có Page metadata | Không tự cung cấp | Không | Query giới hạn kết quả, không làm count riêng cho Page |
| `List<T>` + `Sort` | Có, toàn bộ kết quả phù hợp query | Không phải trang | Không | Có thể tải rất nhiều dòng nếu không giới hạn |

**Không đồng nhất `Page` với “một List kèm count” ở mọi thời điểm.** Spring Data JPA có thể suy luận total trên một số trang, chẳng hạn trang cuối ít hơn page size, mà không nhất thiết chạy câu SQL count riêng. Test nên xác minh **giá trị public API**, không assert cứng số lần gọi `SELECT COUNT` nếu công nghệ hoặc cấu hình có quyền tối ưu.

### 2.1 Mỗi phần metadata có ý nghĩa gì?

Giả sử lấy `Page<Product> page`:

| API | Ý nghĩa |
| --- | --- |
| `getContent()` | Danh sách phần tử thực tế trong trang |
| `getNumber()` | Chỉ số trang, **bắt đầu từ 0** |
| `getSize()` | Kích thước trang đã yêu cầu |
| `getNumberOfElements()` | Số phần tử thật trong trang hiện tại |
| `getTotalElements()` | Tổng số phần tử **khớp bộ lọc** trên toàn tập |
| `getTotalPages()` | Số trang theo tổng và page size |
| `isFirst()`, `isLast()` | Vị trí trang đầu/cuối theo metadata |
| `hasNext()`, `hasPrevious()` | Có trang sau/trước theo metadata |
| `getSort()` | Thứ tự sắp xếp gắn với trang |
| `map(converter)` | Chuyển từng phần tử, thường giữ metadata của trang |

Ví dụ `totalElements=5` và `size=2` tạo `totalPages=3`, không phải 2. `getNumberOfElements()` của trang cuối là 1, nhưng `getSize()` vẫn là 2.

Nếu không có dữ liệu phù hợp, thông thường `totalElements=0`, `totalPages=0` và `getContent().isEmpty()==true`. **Không tạo một trang giả có một dòng null** để biểu diễn tập rỗng.

### 2.2 PageRequest.of(page,size)

~~~java
Pageable first = PageRequest.of(0, 20);
Pageable second = PageRequest.of(1, 20);
Pageable sorted = PageRequest.of(
        0, 20, Sort.by(Sort.Order.asc("price"),
                     Sort.Order.asc("id")));
~~~

`page` là **0-based**, `size` phải dương. `PageRequest.of(-1,10)` hoặc `PageRequest.of(0,0)` ném `IllegalArgumentException`.

Một API nhận page từ client cần kiểm đầu vào, giới hạn page size và trả lỗi phù hợp (thường 400) trước khi tạo query. Không dùng `PageRequest.of(1,20)` để lấy trang đầu tiên trừ khi API của bạn cố ý có quy ước client 1-based và đã chuyển đổi.

### 2.3 SQL tương ứng ở mức khái niệm

Với page 2, size 20:

~~~sql
SELECT ...
FROM catalog_product
WHERE active = TRUE
ORDER BY price ASC, id ASC
LIMIT 20 OFFSET 40;
~~~

Đây là **SQL minh họa** kiểu H2/PostgreSQL, không phải SQL Hibernate cam kết sinh ra trên mọi database; dialect có thể dùng `FETCH FIRST` hoặc cú pháp khác. Ý quan trọng là:

- `OFFSET = page * size`.
- `ORDER BY` phải đủ xác định cho trang ổn định.
- `LIMIT` cắt số dòng, **không bảo đảm đúng tổng** nếu query có join làm nhân dòng.

## 3. Sắp xếp đúng và ổn định: luôn nghĩ đến tie-breaker

Đây là lỗi rất phổ biến: hai sản phẩm đều có giá `50.00`. Query:

~~~java
Sort.by(Sort.Order.asc("price"));
~~~

không quy định phần tử ID 102 hay ID 103 đứng trước. Database **có quyền** trả thứ tự khác nhau khi giá trùng, nhất là khi execution plan/index/concurrency thay đổi.

Để kết quả xác định:

~~~java
Sort stable = Sort.by(
        Sort.Order.asc("price"),
        Sort.Order.asc("id"));
~~~

Khóa phụ `id` phải là **duy nhất và ổn định** trong tập; đây là cách giảm nguy cơ trùng/bỏ qua phần tử ở ranh giới trang khi dữ liệu không thay đổi.

### 3.1 Hai cách tạo sort

~~~java
Sort bySkuDesc = Sort.by(Sort.Direction.DESC, "sku");

Sort byPriceThenId = Sort.by(
        Sort.Order.asc("price"),
        Sort.Order.asc("id"));
~~~

`Sort.by("price")` mặc định tăng dần; `Sort.unsorted()` có nghĩa không truyền sort. Nếu dự án cần phân biệt nulls-first/nulls-last, hãy biết rằng tùy chọn `nullsFirst()`/`nullsLast()` có thể chỉ là **hint** và kết quả phụ thuộc JPA provider/DB.

### 3.2 Tên property Java, không phải SQL column

Spring Data JPA Sort thông thường tham chiếu **tên thuộc tính entity**, ví dụ `price` hoặc `category`, không phải tên cột tùy ý như `PRICE_CENTS_DB`, trừ khi query đã thiết kế alias phù hợp.

Không nhận nguyên chuỗi sort từ HTTP rồi chuyển thẳng vào câu SQL tự ghép. Với `@Query`, Spring Data có những trường hợp dùng `JpaSort.unsafe` cho biểu thức hàm không được kiểm tra như property path; chỉ dùng cho biểu thức **tin cậy do ứng dụng định nghĩa**, không dùng input của client làm biểu thức tùy ý.

### 3.3 Whitelist sort ở ranh giới API

Ví dụ một hàm service/controller **minh họa, chưa là file độc lập**:

~~~java
static Sort safeSort(String requested, boolean descending) {
    String property = switch (requested) {
        case "price" -> "price";
        case "name" -> "name";
        case "sku" -> "sku";
        default -> throw new IllegalArgumentException(
                "Unsupported sort field");
    };

    Sort.Direction direction = descending
            ? Sort.Direction.DESC : Sort.Direction.ASC;

    return Sort.by(
            new Sort.Order(direction, property),
            Sort.Order.asc("id"));
}
~~~

Với API thật, mapping `IllegalArgumentException` thành HTTP 400 một cách rõ ràng, hoặc chỉ chấp nhận enum đã validate. ID làm tie-breaker được cố định `ASC`, dù khóa chính có direction khác. Một sort có nhiều cột vẫn chỉ là **hợp đồng thứ tự**; nó không tự làm dữ liệu đứng yên nếu có write đồng thời.

### 3.4 Offset paging và thay đổi dữ liệu

Ngay cả `ORDER BY price,id` ổn định, nếu giữa lúc lấy page 0 và page 1 có người chèn/xóa bản ghi với price nhỏ hơn, `OFFSET` có thể làm một phần tử bị lặp hoặc bị bỏ qua.

Đối với feed lớn hoặc cập nhật liên tục, cân nhắc **keyset/cursor pagination** (`Window<T>`, `ScrollPosition` khi dùng API phù hợp), đi từ tuple sort key của bản ghi cuối. Keyset giúp tránh quét OFFSET sâu và giảm page drift, nhưng **không tự cung cấp totalElements**; cần logic cursor, sort keys unique/non-null theo hợp đồng và test riêng khi dữ liệu thay đổi.

## 4. Khi nào nên dùng Page, Slice hay List?

| Use case | Đề xuất | Vì sao |
| --- | --- | --- |
| UI có “Trang 1/12” và tổng số kết quả | `Page<T>` | Cần totalElements/totalPages |
| Infinite scroll chỉ cần biết còn item tiếp không | `Slice<T>` | Không cần count toàn bộ tập |
| Dropdown có tối đa vài chục mục, chỉ cần sort | `List<T> + Sort` hoặc giới hạn rõ | Không cần metadata |
| Export nhiều triệu dòng | Stream/scroll/batch thay vì một List khổng lồ | Tránh memory/offset cost |
| Báo cáo số lượng/tổng tiền theo nhóm | Query aggregate riêng | Page total là số hàng, không phải tổng tiền |
| Danh sách projection gọn cho mobile | `Page<Summary>` hoặc `Slice<Summary>` | Trả đúng trường cần thiết |
| Dashboard số liệu gần thời gian thực | Aggregate/materialized view/counter theo yêu cầu | COUNT trên toàn bảng lớn có thể tốn kém |

**Quy tắc:** Chỉ dùng `Page` khi người dùng **thật sự cần tổng số**. Nếu không, `Slice` có thể giảm chi phí count. Nhưng nếu sản phẩm yêu cầu “có 247 kết quả”, không lấy `slice.getContent().size()` rồi giả đó là total.

## 5. Count query và totalElements: đếm đúng tập, không đếm nhầm trang

Với method:

~~~java
Page<Product> findByActiveTrue(Pageable pageable);
~~~

Spring Data JPA sinh query lấy nội dung và cơ chế xác định total theo predicate `active=true`. Khi cần, framework dùng count query tương ứng. Vì page size nhỏ, `totalElements` vẫn phải phản ánh **toàn bộ** bản ghi active, không chỉ số dòng được lấy về.

So sánh:

~~~text
page = 0, size = 2, content.size = 2
totalElements = 5
numberOfElements = 2
totalPages = 3
~~~

Đừng viết `assertEquals(2, page.getTotalElements())` chỉ vì `page.getContent().size()==2`.

### 5.1 Tại sao một countQuery riêng quan trọng?

Với JPQL projection:

~~~java
@Query(
  value = """
      select new example.catalog.ProductCard(p.id, p.sku, p.price)
      from Product p
      where p.category = :category
      """,
  countQuery = """
      select count(p)
      from Product p
      where p.category = :category
      """)
Page<ProductCard> findCardsByCategory(
        @Param("category") String category,
        Pageable pageable);
~~~

Ở đây:

- Query nội dung trả **DTO `ProductCard`**, không trả toàn entity.
- Query count phải dùng **đúng predicate `category = :category`**.
- Count không cần `ORDER BY` hoặc DTO constructor.
- `Page` nhận cả content và total, không buộc count khớp size của một trang.

Với query đơn giản, Spring Data có thể tự suy ra count. Với `JOIN`, `DISTINCT`, `GROUP BY`, native SQL và query phức tạp, **khai báo `countQuery` có chủ đích** giúp kiểm soát nghĩa và tránh count sai.

### 5.2 Một số lỗi count query thực tế

**Predicate khác nhau:** content lọc `active=true AND category=:category` nhưng count chỉ lọc `category` → total quá lớn.

**Join nhân bản root entity:** một đơn hàng có 3 lines, query `JOIN order.lines` có 3 dòng SQL; `count(o)` có thể đếm 3 trong khi UI muốn 1 order. Khi hợp đồng là số order duy nhất, cân nhắc `count(distinct o.id)` và thiết kế content query tương ứng.

**Collection fetch join cùng Pageable:** `JOIN FETCH` một collection + LIMIT/OFFSET có thể tạo bản ghi trùng, pagination trong bộ nhớ hoặc exception tùy Hibernate config. Không dùng cách này như “tối ưu” mặc định; có thể cần hai bước: page IDs trước, rồi fetch details theo IDs.

**Group by:** mỗi dòng content có thể đại diện **một nhóm**, không phải một entity. Nếu bạn page danh sách nhóm, total phải là **số nhóm** khớp filter/HAVING, không phải tổng số entity. Count query có thể cần `count(distinct key)` hoặc một subquery/native strategy phù hợp DB.

**Optimization:** một số trang (nhất là last page ít dòng) có thể có total được suy ra mà không chạy count. Test không nên buộc “đã gọi COUNT đúng một lần” khi chỉ cần public metadata đúng.

### 5.3 PageableExecutionUtils không phải hợp đồng SQL

Spring Data Commons có cơ chế tối ưu tạo `Page` với count supplier và chỉ gọi khi cần. Điều đó giải thích vì sao đo log SQL đôi khi không thấy query count ở tất cả các trang. Đừng nhầm “không thấy COUNT” với “totalElements chắc chắn sai”, cũng đừng dùng suy đoán này để bỏ kiểm total.

Một bài test repository tốt cần kiểm **content**, **predicate**, **totalElements** và **totalPages** trong nhiều trang/kịch bản rỗng. Nếu muốn kiểm performance, hãy đo số SQL trong benchmark/integration test riêng trên dữ liệu thực tế.

## 6. Projection: chỉ lấy cấu trúc phù hợp use case

Trả cả `Product` từ API có thể gây nhiều vấn đề: entity có relationship lazy, field nội bộ, serialization khó kiểm soát, coupling với persistence. **Projection** cho phép repository trả một view chuyên dụng.

Spring Data hỗ trợ **interface-based projection**, **DTO/class/record projection** và **dynamic projection**. Chúng không phải một cơ chế giống nhau 100%: cách select, proxy, constructor, nested joins và performance phụ thuộc implementation.

### 6.1 Closed interface projection

Ví dụ:

~~~java
public interface ProductBrief {
    Long getId();
    String getSku();
    String getName();
    BigDecimal getPrice();
}
~~~

Đây là một **Java interface**, getters khớp tên property của entity. Với:

~~~java
Page<ProductBrief> findByCategoryAndActiveTrue(
        String category, Pageable pageable);
~~~

Spring Data JPA có thể tạo một projection proxy và chỉ chọn các thuộc tính top-level cần thiết. Không nên tuyên bố “mọi SQL projection luôn chỉ select bốn cột” mà chưa xem query/provider, nhất là khi có nested projection hoặc custom JPQL.

**Test cần chứng minh:**

1. Tập bản ghi đúng predicate.
2. Mỗi getter trả giá trị đúng type.
3. `Page<ProductBrief>` vẫn có metadata chính xác.
4. API serialization hoặc service mapping không vô tình lộ các field entity khác.

Projection interface là **view đọc**, không phải entity để sửa rồi gọi `save`.

### 6.2 Open projection dùng SpEL

Ví dụ minh họa:

~~~java
public interface ProductLabelView {
    String getSku();

    @Value("#{target.sku + ' - ' + target.name}")
    String getLabel();
}
~~~

`@Value` ở đây là `org.springframework.beans.factory.annotation.Value`; `target` trỏ tới object nền của projection. Đây là **open projection** vì SpEL có thể chạm nhiều thuộc tính, nên framework khó tối ưu selection như closed projection.

Nếu chỉ nối hai getters đã có, Java interface `default String getLabel() { return getSku()+" - "+getName(); }` thường rõ hơn. Đừng nhầm open projection là cách tạo “materialized computed SQL column” tối ưu.

### 6.3 DTO/record projection

Java 17 record:

~~~java
public record ProductCard(
        Long id,
        String sku,
        BigDecimal price) {
}
~~~

Khi viết JPQL `@Query` có constructor expression:

~~~jpql
select new example.catalog.ProductCard(p.id, p.sku, p.price)
from Product p
where p.category = :category
~~~

Tên DTO **phải là fully-qualified name** bên trong JPQL constructor expression. Nó phải có constructor phù hợp thứ tự và kiểu arguments. Record có constructor canonical nên thuận tiện cho DTO projection, so sánh bằng `equals` theo giá trị.

Không thêm `as id`/`as price` vào **bên trong constructor expression**; alias ở đó không hợp lệ theo quy tắc JPQL được tài liệu Spring Data JPA nhấn mạnh.

### 6.4 Dynamic projection

~~~java
<T> List<T> findByCategory(
        String category, Class<T> type);
~~~

Có thể gọi:

~~~java
List<ProductBrief> briefs =
        repository.findByCategory("BOOK", ProductBrief.class);

List<Product> entities =
        repository.findByCategory("BOOK", Product.class);
~~~

Đây là **mẫu dùng trong code có ProductRepository**. `Class<T>` chọn kiểu projection tại runtime. Khi method có overload khác nhận `Sort`/`Pageable`, Java sẽ chọn method theo **kiểu tham số**, không theo return type.

Dùng dynamic projection khi thật sự có nhiều view của cùng predicate; nếu mọi caller dùng một DTO, một method tĩnh rõ ràng thường đơn giản và dễ audit hơn.

### 6.5 Nested projection và join cost

Một projection lấy `order.customer.address.city` có thể tạo join và load phần association nhiều hơn dự kiến. “Projection chỉ lấy trường được khai báo” được tối ưu tốt nhất ở **top-level properties**; nested property không đảm bảo giống việc chỉ chọn một SQL column đơn giản.

Không coi projection là giải pháp tự động cho N+1, fetch join hoặc transaction boundary. Với aggregate endpoint lớn, hãy kiểm log SQL, số query, row multiplicity và database-specific execution plan.

## 7. Dữ liệu tổng: count, sum, group by và kiểu số

“Dữ liệu tổng” có ít nhất ba lớp nghĩa:

1. **Page totals:** `totalElements` và `totalPages` của tập kết quả đang lọc.
2. **Domain count:** `countByCategoryAndActiveTrue("BOOK")`, số sản phẩm thỏa một predicate riêng.
3. **Business aggregates:** `SUM(price)`, `AVG`, `MIN`, `MAX`, `COUNT` theo category, khoảng thời gian, tenant hoặc trạng thái.

Chúng có thể liên quan nhưng **không thay nhau**. `getTotalElements()` là số **dòng logical result** của một query phân trang; không phải doanh thu hoặc số entity toàn database.

### 7.1 Aggregate JPQL constructor projection

~~~java
@Query("""
    select new example.catalog.CategoryTotals(
        p.category, count(p), sum(p.price))
    from Product p
    where p.active = true
    group by p.category
    order by p.category
    """)
List<CategoryTotals> activeTotalsByCategory();
~~~

DTO:

~~~java
public record CategoryTotals(
        String category,
        Long productCount,
        BigDecimal totalPrice) {
}
~~~

Test sẽ kiểm BOOK có 3 sản phẩm tổng 200.00 và TOOL có 2 sản phẩm tổng 350.00. Ta dùng `Long` cho `COUNT` và `BigDecimal` cho `SUM(BigDecimal)`, tránh dùng `double` để so tổng tiền.

**COUNT(p)** đếm thực thể phù hợp; **COUNT(p.someNullableField)** chỉ đếm các giá trị không null của field đó. **COUNT(DISTINCT ...)** cần khi loại trùng. **SUM** trên tập rỗng thường trả **null** theo SQL/JPQL, trong khi `COUNT` trả 0. Với `GROUP BY`, nếu không có nhóm nào thì thường kết quả là **list rỗng**, không phải một nhóm với count 0.

### 7.2 Tổng theo nhóm không nhất thiết cộng được thành một tổng toàn hệ thống

Để cộng thành tổng toàn hệ thống, các nhóm phải **không chồng lấn**, sử dụng **cùng filter**, cùng đơn vị/currency, và không có rows bị loại bởi join/HAVING.

Ví dụ nếu nhóm BOOK active là 200.00 và TOOL active là 350.00, grand total active là 550.00. Nếu truy vấn `Page<Product>` chỉ lọc category BOOK, metadata totalElements là **3**, không phải 5; không lấy tổng từ một endpoint khác có filter rộng hơn rồi ghép vào page như thể cùng ngữ nghĩa.

### 7.3 Vì sao không dùng double cho số tiền?

~~~java
BigDecimal a = new BigDecimal("100.00");
BigDecimal b = new BigDecimal("50.00");

BigDecimal sum = a.add(b);
assertEquals(0, sum.compareTo(new BigDecimal("150.00")));
~~~

Đây là **đoạn minh họa JUnit**, cần import `BigDecimal` và `assertEquals`. `BigDecimal.equals` xem cả scale: `150.0` và `150.00` có thể không `equals`; `compareTo` kiểm giá trị số. Khi serialization/money contract cần đúng scale, test thêm scale hoặc cách định dạng theo policy.

Nếu hệ thống có nhiều loại tiền, **không cộng USD và EUR như một tổng**; group theo currency hoặc đổi tiền bằng tỷ giá/điều kiện rõ ràng.

### 7.4 Aggregate khi dataset biến động

Pagination query và query tổng hợp có thể chạy ở hai thời điểm khác nhau. Dưới isolation `READ COMMITTED`, một transaction khác có thể thêm dòng giữa hai lần đọc; `totalElements=100` và `SUM` phản ánh 101 dòng **không hẳn là bug tính toán**, mà là vấn đề snapshot consistency.

Nếu API yêu cầu nhất quán tuyệt đối, dùng transaction/isolation, snapshot hoặc kiến trúc báo cáo phù hợp, hiểu rằng một read-only transaction không tự đảm bảo snapshot mạnh ở mọi database. Test consistency riêng bằng integration test trên DB production-like thay vì suy từ H2.

## 8. Ví dụ chạy được: Java 17+ / Spring Boot 3.5.x / Spring Data JPA

Mục này trình bày **một ứng dụng nhỏ thực sự** với repository và bộ `@DataJpaTest`; không cần HTTP server, Docker, môi trường cloud hay credentials. Dùng H2 in-memory cho tính lặp lại trong CI, đồng thời ghi rõ các giới hạn khác biệt với PostgreSQL/MySQL.

### 8.1 Cấu trúc file

~~~text
src/
  main/
    java/example/catalog/
      CatalogApplication.java
      Product.java
      ProductBrief.java
      ProductCard.java
      CategoryTotals.java
      ProductRepository.java
  test/
    java/example/catalog/
      ProductRepositoryTest.java
~~~

Tất cả files dùng `package example.catalog;`. Test nằm cùng package hierarchy với root `@SpringBootApplication` để Boot tự tìm cấu hình gốc cho test slice.

### 8.2 CatalogApplication.java

~~~java
package example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Lớp này cung cấp primary Boot configuration. Bài `@DataJpaTest` sẽ chỉ nạp **JPA test slice**, không khởi động server TCP.

### 8.3 Product.java — entity có ID cố định phục vụ fixture

~~~java
package example.catalog;

import java.math.BigDecimal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "catalog_product")
public class Product {

    @Id
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private String category;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean active;

    protected Product() {
        // JPA cần constructor không tham số.
    }

    public Product(
            Long id,
            String sku,
            String name,
            String category,
            BigDecimal price,
            boolean active) {
        this.id = id;
        this.sku = sku;
        this.name = name;
        this.category = category;
        this.price = price;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public String getCategory() {
        return category;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

**ID do test cấp** (101–106) để thứ tự theo ID không phụ thuộc sequence hoặc thứ tự insert. Ở ứng dụng production thường dùng `@GeneratedValue` hoặc UUID theo thiết kế. Entity có constructor không tham số `protected` cho JPA; test dùng constructor public để tạo fixtures.

Không cho JPA entity tự động biến thành JSON response của mọi endpoint. `Product` trong ví dụ chỉ đóng vai domain/persistence; projection record hoặc API DTO thích hợp hơn để xuất dữ liệu.

### 8.4 ProductBrief.java — closed interface projection

~~~java
package example.catalog;

import java.math.BigDecimal;

public interface ProductBrief {
    Long getId();
    String getSku();
    String getName();
    BigDecimal getPrice();
}
~~~

Tên getter khớp các thuộc tính top-level `id`, `sku`, `name`, `price`. Không khai báo `getSecretToken()` giả định trong khi entity không có property tương ứng.

### 8.5 ProductCard.java — DTO record projection

~~~java
package example.catalog;

import java.math.BigDecimal;

public record ProductCard(
        Long id,
        String sku,
        BigDecimal price) {
}
~~~

### 8.6 CategoryTotals.java — aggregate DTO

~~~java
package example.catalog;

import java.math.BigDecimal;

public record CategoryTotals(
        String category,
        Long productCount,
        BigDecimal totalPrice) {
}
~~~

Chúng là **DTO thực**, không phải Mockito mocks. JPQL dùng fully-qualified type trong constructor expressions.

### 8.7 ProductRepository.java — Page, Slice, projection, totals

~~~java
package example.catalog;

import java.math.BigDecimal;
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Page<Product> findByActiveTrue(Pageable pageable);

    Slice<Product> findByCategory(
            String category, Pageable pageable);

    List<Product> findByCategory(
            String category, Sort sort);

    Page<ProductBrief> findByCategoryAndActiveTrue(
            String category, Pageable pageable);

    <T> List<T> findByCategory(
            String category, Class<T> type);

    long countByActiveTrue();

    long countByCategoryAndActiveTrue(String category);

    @Query(
      value = """
          select new example.catalog.ProductCard(
              p.id, p.sku, p.price)
          from Product p
          where p.category = :category
          """,
      countQuery = """
          select count(p)
          from Product p
          where p.category = :category
          """)
    Page<ProductCard> findCardsByCategory(
            @Param("category") String category,
            Pageable pageable);

    @Query("""
        select new example.catalog.CategoryTotals(
            p.category, count(p), sum(p.price))
        from Product p
        where p.active = true
        group by p.category
        order by p.category
        """)
    List<CategoryTotals> activeTotalsByCategory();

    @Query("""
        select sum(p.price)
        from Product p
        where p.active = true
        """)
    BigDecimal sumActivePrices();
}
~~~

**Lưu ý quan trọng:**

- `findByActiveTrue` thực hiện derived query với boolean property `active`.
- `findByCategory(String,Pageable)` trả `Slice`; overload `findByCategory(String,Sort)` chỉ sắp xếp.
- `findByCategoryAndActiveTrue` trả interface projection dưới dạng `Page` với đúng category và active filter.
- Method generic `findByCategory(String,Class<T>)` là **dynamic projection**, không yêu cầu overload theo return type.
- `findCardsByCategory` gồm **JPQL constructor expression** và count query tự viết với cùng category filter. Vì query này không lọc active, một sản phẩm BOOK inactive cũng được tính.
- `activeTotalsByCategory` dùng `COUNT`/`SUM` cho **active products**, chia nhóm theo category; list không có Page metadata.
- `sumActivePrices()` trả `BigDecimal` cho dataset có active rows; nếu predicate không có dòng, cần xử lý `null` hoặc `COALESCE` theo policy.
- Không đặt `Sort` vào query aggregate `GROUP BY` theo cách làm sai số nhóm; `ORDER BY category` ở đây chỉ phục vụ output stable.

## 9. @DataJpaTest với 10 bài kiểm thử JUnit Jupiter

File `src/test/java/example/catalog/ProductRepositoryTest.java`:

~~~java
package example.catalog;

import java.math.BigDecimal;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest(properties = "spring.jpa.hibernate.ddl-auto=create-drop")
@DisplayName("Spring Data JPA: paging, sorting, projection, totals")
class ProductRepositoryTest {

    @Autowired
    ProductRepository repository;

    @Autowired
    EntityManager entityManager;

    @BeforeEach
    void seed() {
        List<Product> rows = List.of(
                product(101, "BOOK-101", "Java 17", "BOOK", "100.00", true),
                product(102, "BOOK-102", "JPA A", "BOOK", "50.00", true),
                product(103, "BOOK-103", "JPA B", "BOOK", "50.00", true),
                product(104, "BOOK-104", "Draft", "BOOK", "25.00", false),
                product(105, "TOOL-105", "IDE", "TOOL", "200.00", true),
                product(106, "TOOL-106", "Build", "TOOL", "150.00", true));

        rows.forEach(entityManager::persist);
        entityManager.flush();
        entityManager.clear();
    }

    private static Product product(
            long id, String sku, String name,
            String category, String price, boolean active) {
        return new Product(
                id, sku, name, category,
                new BigDecimal(price), active);
    }

    private static Sort priceThenId() {
        return Sort.by(
                Sort.Order.asc("price"),
                Sort.Order.asc("id"));
    }

    @Test
    @DisplayName("Page 0: đúng hai bản ghi, totalElements=5, totalPages=3")
    void pageMetadataUsesAllMatchingRows() {
        Page<Product> page = repository.findByActiveTrue(
                PageRequest.of(0, 2, priceThenId()));

        assertEquals(0, page.getNumber());
        assertEquals(2, page.getSize());
        assertEquals(2, page.getNumberOfElements());
        assertEquals(5L, page.getTotalElements());
        assertEquals(3, page.getTotalPages());
        assertEquals(List.of(102L, 103L),
                page.getContent().stream()
                        .map(Product::getId).toList());
        assertTrue(page.isFirst());
        assertTrue(page.hasNext());
        assertFalse(page.isLast());
    }

    @Test
    @DisplayName("Tie-breaker theo ID cho thứ tự 3 trang ổn định")
    void sortingHasDeterministicTieBreaker() {
        Page<Product> first = repository.findByActiveTrue(
                PageRequest.of(0, 2, priceThenId()));
        Page<Product> second = repository.findByActiveTrue(
                PageRequest.of(1, 2, priceThenId()));
        Page<Product> third = repository.findByActiveTrue(
                PageRequest.of(2, 2, priceThenId()));

        List<Long> orderedIds = Stream.of(first, second, third)
                .flatMap(p -> p.getContent().stream())
                .map(Product::getId)
                .toList();

        assertEquals(
                List.of(102L, 103L, 101L, 106L, 105L),
                orderedIds);
        assertEquals(1, third.getNumberOfElements());
        assertTrue(third.isLast());
        assertFalse(third.hasNext());
    }

    @Test
    @DisplayName("Slice biết có next mà không cần totalElements")
    void sliceReportsHasNext() {
        Slice<Product> first = repository.findByCategory(
                "BOOK", PageRequest.of(0, 2, priceThenId()));
        Slice<Product> second = repository.findByCategory(
                "BOOK", PageRequest.of(1, 2, priceThenId()));

        assertEquals(List.of(104L, 102L),
                first.getContent().stream()
                        .map(Product::getId).toList());
        assertEquals(List.of(103L, 101L),
                second.getContent().stream()
                        .map(Product::getId).toList());
        assertTrue(first.hasNext());
        assertFalse(second.hasNext());
        assertTrue(second.isLast());
    }

    @Test
    @DisplayName("List + Sort trả đúng thứ tự, không có Page metadata")
    void listCanSortWithoutPaging() {
        List<Product> rows = repository.findByCategory(
                "BOOK", Sort.by(Sort.Direction.DESC, "sku"));

        assertEquals(
                List.of("BOOK-104", "BOOK-103",
                        "BOOK-102", "BOOK-101"),
                rows.stream().map(Product::getSku).toList());
    }

    @Test
    @DisplayName("Closed interface projection vẫn có Page totals")
    void interfaceProjectionKeepsPagingMetadata() {
        Page<ProductBrief> result =
                repository.findByCategoryAndActiveTrue(
                        "BOOK",
                        PageRequest.of(0, 2, priceThenId()));

        assertEquals(3L, result.getTotalElements());
        assertEquals(2, result.getTotalPages());
        assertEquals(List.of("BOOK-102", "BOOK-103"),
                result.getContent().stream()
                        .map(ProductBrief::getSku).toList());
        assertEquals(0,
                result.getContent().get(0).getPrice()
                        .compareTo(new BigDecimal("50.00")));
    }

    @Test
    @DisplayName("DTO JPQL projection dùng countQuery cùng predicate")
    void dtoProjectionHasCorrectCountQuery() {
        Page<ProductCard> result =
                repository.findCardsByCategory(
                        "BOOK",
                        PageRequest.of(0, 2, priceThenId()));

        // Query này KHÔNG lọc active: BOOK có 4 rows.
        assertEquals(4L, result.getTotalElements());
        assertEquals(2, result.getTotalPages());
        assertEquals(List.of(104L, 102L),
                result.getContent().stream()
                        .map(ProductCard::id).toList());
        assertEquals("BOOK-104",
                result.getContent().get(0).sku());
    }

    @Test
    @DisplayName("Dynamic projection chọn interface tại lúc gọi")
    void dynamicProjectionReturnsExpectedFields() {
        List<ProductBrief> rows = repository.findByCategory(
                "TOOL", ProductBrief.class);

        Set<String> skus = rows.stream()
                .map(ProductBrief::getSku)
                .collect(Collectors.toSet());

        assertEquals(
                Set.of("TOOL-105", "TOOL-106"), skus);
        assertEquals(2, rows.size());
    }

    @Test
    @DisplayName("COUNT/SUM/GROUP BY khớp dữ liệu active")
    void aggregatesMatchFilteredRows() {
        List<CategoryTotals> totals =
                repository.activeTotalsByCategory();

        assertEquals(2, totals.size());
        assertEquals("BOOK", totals.get(0).category());
        assertEquals(3L, totals.get(0).productCount());
        assertEquals(0, totals.get(0).totalPrice()
                .compareTo(new BigDecimal("200.00")));

        assertEquals("TOOL", totals.get(1).category());
        assertEquals(2L, totals.get(1).productCount());
        assertEquals(0, totals.get(1).totalPrice()
                .compareTo(new BigDecimal("350.00")));

        assertEquals(5L, repository.countByActiveTrue());
        assertEquals(3L,
                repository.countByCategoryAndActiveTrue("BOOK"));
        assertEquals(0, repository.sumActivePrices()
                .compareTo(new BigDecimal("550.00")));
    }

    @Test
    @DisplayName("Không có dữ liệu khớp: content rỗng, total=0")
    void emptyResultIsNotAOneRowPage() {
        Page<ProductBrief> none =
                repository.findByCategoryAndActiveTrue(
                        "MISSING",
                        PageRequest.of(0, 2, priceThenId()));

        assertTrue(none.getContent().isEmpty());
        assertEquals(0L, none.getTotalElements());
        assertEquals(0, none.getTotalPages());
        assertFalse(none.hasNext());
        assertEquals(0L,
                repository.countByCategoryAndActiveTrue("MISSING"));
    }

    @Test
    @DisplayName("Trang âm và size bằng 0 bị từ chối")
    void invalidPageArgumentsAreRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> PageRequest.of(-1, 2));
        assertThrows(IllegalArgumentException.class,
                () -> PageRequest.of(0, 0));
    }
}
~~~

**Có 10 phương thức `@Test`.** Các test sử dụng `@BeforeEach` để tạo dataset **mới cho từng test**, vì `@DataJpaTest` có transaction rollback sau method theo mặc định. `EntityManager.persist/flush/clear` giúp các query sau thực sự đọc từ database thay vì đơn thuần dựa vào các object vẫn đang ở persistence context.

### 9.1 Điều mỗi test thực sự chứng minh

| Test | Khẳng định nổi bật | Lỗi có thể phát hiện |
| --- | --- | --- |
| `pageMetadataUsesAllMatchingRows` | content 102,103, total5/pages3 | Count nhầm page size, sai predicate, sai page index |
| `sortingHasDeterministicTieBreaker` | 3 trang có đúng 5 ID, thứ tự ổn định | Sort thiếu ID, boundary/offset sai |
| `sliceReportsHasNext` | Slice BOOK 4 rows, hasNext theo từng trang | Dùng page totals giả thay hasNext |
| `listCanSortWithoutPaging` | SKU DESC đúng | Sort direction/property sai |
| `interfaceProjectionKeepsPagingMetadata` | Page projection BOOK active total3 | Projection field hoặc filter sai |
| `dtoProjectionHasCorrectCountQuery` | DTO BOOK gồm inactive, total4 | Count query lệch predicate, DTO mapping sai |
| `dynamicProjectionReturnsExpectedFields` | Dynamic interface projection trả đúng hai TOOL | Kiểu projection/derived query sai |
| `aggregatesMatchFilteredRows` | BOOK 200, TOOL 350, all 550 | COUNT/SUM/GROUP BY nhầm filter hoặc dữ liệu |
| `emptyResultIsNotAOneRowPage` | Không khớp → total0, content rỗng | Fallback giả, count sai |
| `invalidPageArgumentsAreRejected` | page âm/size0 ném exception | Chấp nhận paging input không hợp lệ |

**Lưu ý:** test `sortingHasDeterministicTieBreaker` với một snapshot ổn định không thể chứng minh pagination không lặp/bỏ qua khi **có ghi đồng thời**. Để kiểm dữ liệu thay đổi theo thời gian, phải có thêm test concurrency hoặc keyset/transaction semantics ở database thực.

### 9.2 Số lần COUNT không phải điều cần assert trong ví dụ

Bài này cố ý không spy SQL logs để đếm `SELECT count(...)`. Tối ưu Spring Data có thể làm query count bị bỏ qua ở một số trang. Điều cần chứng minh là **totalElements = 5, totalPages = 3 và content đúng**; kiểm SQL count execution count nếu chính performance là mục tiêu, dùng SQL metrics/integration benchmark riêng.

### 9.3 Vì sao dùng BigDecimal.compareTo?

Trên H2, cách biểu diễn scale của `DECIMAL(12,2)` thường cho kết quả có 2 chữ số thập phân, nhưng provider và phép aggregate có thể trả scale khác. `compareTo` kiểm số học 200.00/350.00/550.00 chính xác, còn `equals` quan tâm scale. API hợp đồng có thể yêu cầu scale=2; khi đó thêm assertion về serialization/scale ở tầng thích hợp.

## 10. Cấu hình Gradle và cách chạy

Trong một project Spring Boot **3.5.x** có Gradle plugin, dependency management và Java toolchain 17, thêm phần dependencies sau vào `build.gradle` (đoạn này **không phải build file hoàn chỉnh**):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Nếu ứng dụng production thật cần chạy standalone, phải có datasource/config tương ứng; **H2 ở đây chỉ khai báo testRuntimeOnly** vì chỉ chạy `@DataJpaTest`. Java 17 toolchain và Spring Boot plugin phải được cấu hình ở phần build khác.

Lệnh chạy:

~~~bash
./gradlew test --tests example.catalog.ProductRepositoryTest
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.catalog.ProductRepositoryTest
~~~

**Kết quả dự kiến:** JUnit Jupiter phát hiện **10 phương thức test**, và chúng PASS với project chứa đầy đủ các file/đúng dependency nêu trên. Test không tự `System.out.println`; console có thể có Hibernate/Spring startup logs và Gradle `BUILD SUCCESSFUL`. Đây là **kỳ vọng sau rà soát code**, không phải log xác nhận một lần build đã thực thi.

### 10.1 Vì sao không dùng @SpringBootTest cho mọi test này?

`@DataJpaTest` tải JPA repository, entity manager, transaction support và datasource test phù hợp, thay vì toàn bộ MVC/server/service graph. Nó vừa nhanh hơn vừa đúng phạm vi muốn kiểm query thực.

Không tạo `@Mock ProductRepository` rồi assert `getTotalElements() == 5` vì mock có thể trả bất cứ dữ liệu nào bạn stub; bài như vậy **không kiểm JPA query hay countQuery**.

## 11. Test dữ liệu tổng ở tầng API

Dữ liệu tổng thường được hiển thị ở API JSON. Khi một controller trả `Page<ProductCard>` trực tiếp, JSON có thể chứa các metadata do Spring Data serializer cung cấp, nhưng định dạng serialization của `PageImpl` có thể thay đổi giữa versions/configurations. Nếu API cần contract lâu dài, hãy định nghĩa **response DTO ổn định**.

Ví dụ:

~~~java
public record PageEnvelope<T>(
        List<T> items,
        int page,
        int size,
        long totalElements,
        int totalPages,
        boolean hasNext) {

    public static <T> PageEnvelope<T> from(Page<T> result) {
        return new PageEnvelope<>(
                result.getContent(),
                result.getNumber(),
                result.getSize(),
                result.getTotalElements(),
                result.getTotalPages(),
                result.hasNext());
    }
}
~~~

Đây là **class record minh họa**, cần import `java.util.List` và `org.springframework.data.domain.Page`, đặt trong file `PageEnvelope.java` khi áp dụng. Nó giữ JSON fields do ứng dụng kiểm soát thay vì serialize entity hoặc framework internal object.

### 11.1 Các bộ lọc phải tương ứng với totals

API `GET /products?category=BOOK&active=true&page=0&size=2` có thể trả:

~~~json
{
  "items": [
    {"id": 102, "sku": "BOOK-102", "price": 50.00},
    {"id": 103, "sku": "BOOK-103", "price": 50.00}
  ],
  "page": 0,
  "size": 2,
  "totalElements": 3,
  "totalPages": 2,
  "hasNext": true
}
~~~

**JSON minh họa theo contract ứng dụng**, không phải output trực tiếp của `ProductRepositoryTest`. Lưu ý `Page<ProductCard> findCardsByCategory` trong ví dụ repository không lọc `active=true`; muốn tạo response này phải gọi method/filter đúng (`findByCategoryAndActiveTrue` hoặc viết query DTO có active filter). **Không ghép total từ một method không lọc active vào content đã lọc active.**

### 11.2 Kiểm API với MockMvc/WebTestClient

Nếu test tầng HTTP:

- Gửi page=0, size=2, sort hợp lệ; assert 200, items theo đúng thứ tự, totalElements/totalPages.
- Gửi page âm, size=0 hoặc size quá lớn; assert 400 theo validation policy.
- Gửi sort field không cho phép; assert 400, không biến input thành JPQL expression.
- Gửi filter không có kết quả; assert `items=[]` và `totalElements=0`, không phải 404 trừ khi API đặc tả khác.
- Với cơ chế auth/tenant, kết quả và total **chỉ** bao gồm bản ghi được phép xem; count không được lộ số bản ghi của tenant khác.
- Với projection, assert JSON không chứa các field nội bộ dù entity có.

**Không dùng HTTP test để thay thế @DataJpaTest.** HTTP test với repository mock chỉ chứng minh controller mapping; repository test cần query thật.

## 12. Những case khó cần test riêng trong sản phẩm thực

### 12.1 Pagination trên quan hệ one-to-many

Giả sử mỗi Order có nhiều OrderLine. Nếu join Order với lines rồi phân trang dòng SQL, một Order có thể xuất hiện nhiều lần và count bị nhân lên.

~~~jpql
select distinct o
from Order o
join o.lines l
where l.status = :status
~~~

Đây là **JPQL minh họa**, chưa có entity Order trong mini project. `DISTINCT` có thể giúp định nghĩa logical root set, nhưng với collection fetch join + pagination, Hibernate có thể phải xử lý trong bộ nhớ hoặc từ chối theo config.

Một hướng ổn định:

1. Truy vấn **ID root** theo filter, sort và Pageable.
2. Đếm `distinct root ID` cho tổng, nếu API cần count.
3. Truy vấn chi tiết root/relationships cho các ID đã chọn.
4. Khôi phục đúng thứ tự ID đã page, vì `IN (...)` không đảm bảo ordering.

Viết test fixture có **một order 3 lines, một order 1 line**; assert total root=2 chứ không phải 4. Không chỉ dùng fixture mỗi order một line vì test đó không bao giờ lộ bug nhân dòng.

### 12.2 Group by và HAVING

Nếu UI muốn page “categories có tổng tiền lớn hơn 100”, query nội dung có thể dùng `GROUP BY category HAVING SUM(price) > 100`. Total phải là số **category groups** đáp ứng điều kiện HAVING, không phải tổng số products.

Ví dụ SQL khái niệm:

~~~sql
SELECT category, COUNT(*) AS product_count, SUM(price) AS total_price
FROM catalog_product
WHERE active = TRUE
GROUP BY category
HAVING SUM(price) > 100
ORDER BY category
LIMIT 20 OFFSET 0;
~~~

Query count nhóm có thể cần subquery:

~~~sql
SELECT COUNT(*)
FROM (
  SELECT category
  FROM catalog_product
  WHERE active = TRUE
  GROUP BY category
  HAVING SUM(price) > 100
) grouped;
~~~

Đây là **SQL minh họa**, không phải JPQL dùng trực tiếp cho mọi provider; một số JPQL dialect không hỗ trợ subquery ở `FROM`. Khi chọn native SQL, cần kiểm syntax/countQuery trên database thật và mapping aggregate DTO.

### 12.3 Null/đồng nhất sort giữa các database

PostgreSQL, MySQL và H2 có thể khác cách sort `NULL`, collation của text, chữ hoa/chữ thường, accent và timezone. Một test H2 PASS **không chứng minh** thứ tự tên tiếng Việt trên PostgreSQL production giống hệt.

Nếu UI yêu cầu sort tên theo locale, hãy kiểm rule cụ thể của DB/collation hoặc xử lý chuẩn hóa có chủ đích. `Sort.Order.ignoreCase()` không phải phép thần kỳ bảo đảm kết quả giống nhau trên mọi dialect.

### 12.4 Count distinct và soft delete

Với soft delete:

~~~text
active = true
deleted_at IS NULL
tenant_id = currentTenant
~~~

Cả content query, count query và aggregate query phải áp dụng **cùng visibility rules**. Một missing predicate trong count có thể lộ số bản ghi của tenant khác hoặc đã xóa. Viết test có dữ liệu thuộc ít nhất hai tenants và một soft-deleted row; assert both page metadata and grouped totals.

### 12.5 Aggregates với negative values và empty set

Một hệ thống giao dịch có refund âm, discount, null/unknown giá:

- Dùng `BigDecimal` và type/scale có thể biểu diễn giá âm.
- `SUM` trả null khi không có rows; quyết định API muốn null hay 0 rồi xử lý bằng `COALESCE` hoặc service mapping.
- `COUNT(field)` khác `COUNT(*)` khi field nullable.
- Nếu các giao dịch đã kết thúc/cancelled phải bị loại, áp dụng filter ở **mọi** count/sum query.
- Khi không có nhóm nào, `GROUP BY` trả list rỗng; không tự tạo “category=UNKNOWN, total=0” trừ khi contract yêu cầu.

### 12.6 Projection không phải giải pháp bảo mật hoàn chỉnh

Interface projection giảm các field trả về, nhưng không tự thực thi authorization. Nếu predicate thiếu `tenantId` hoặc dữ liệu nhạy cảm bị đưa vào custom JPQL, projection vẫn có thể trả record không được phép. Kiểm security filter/DB row-level rules riêng.

### 12.7 Offset rất lớn và chi phí database

`OFFSET 1_000_000` thường đòi database đi qua nhiều dòng để tìm trang sâu, nhất là khi sort không có index phù hợp. Đo `EXPLAIN ANALYZE` trên DB production-like, cân nhắc keyset/cursor. Không kết luận Page “chậm vì Java tạo DTO” khi bottleneck thực là sort và offset query.

## 13. Cách kiểm hiệu năng mà không đánh đồng với correctness

Một test repository với 6 rows có thể chứng minh **logic đúng**, nhưng không nói gì về performance trên 10 triệu rows. Tách ba loại bằng chứng:

| Loại | Mục tiêu | Công cụ |
| --- | --- | --- |
| Correctness | Content/sort/total đúng | `@DataJpaTest` với dữ liệu biên và assertions rõ |
| SQL semantics | Query/count/join/dialect đúng trên DB thật | Testcontainers PostgreSQL/MySQL, SQL logging, execution plan |
| Performance | Tối ưu latency, memory, count cost, index | Load/performance test, query plan, metrics/JMH khi phù hợp |

Đặc biệt đối với aggregate report, count query có thể đắt hơn content query. Nhưng cách tối ưu là đo workload thực, cân nhắc pre-aggregated tables, cache có invalidation, asynchronous report, hoặc bỏ total theo UX — **không** thay totalElements bằng `content.size()` mà không thay hợp đồng.

### Hạn chế của @DataJpaTest với H2

`@DataJpaTest` mặc định có thể thay datasource bằng embedded DB khi có H2/HSQL/Derby. H2 không tái hiện hoàn toàn behavior của PostgreSQL/MySQL (JSON columns, array, native CTE/window functions, collation, locking).

Khi cần database giống production, dùng Testcontainers và cấu hình `@ServiceConnection`/`@DynamicPropertySource` phù hợp phiên bản, hoặc `@AutoConfigureTestDatabase(replace = NONE)` khi cần tránh test database replacement. **Không trỏ test đến production database**.

## 14. Các lỗi phổ biến

**1. Dùng số trang 1 cho trang đầu theo thói quen UI.**  
`PageRequest` 0-based. Nếu UI 1-based, chuyển đổi có validate ở API boundary.

**2. Không giới hạn page size.**  
`size=10000000` có thể gây memory pressure. Whitelist/limit và trả 400 nếu vượt policy.

**3. Chỉ sort theo price khi price có thể trùng.**  
Page boundaries không ổn định. Thêm unique secondary key như `id`.

**4. Nhầm `getNumberOfElements()` với `getTotalElements()`.**  
Một cái là số dòng trong trang, một cái là tổng matching rows.

**5. Dùng `Slice` nhưng lại hiển thị “Trang 1/120”.**  
Slice không có totalPages. Cần Page hoặc UX khác.

**6. Dùng `List<T>` không giới hạn cho bảng hàng triệu dòng.**  
Có thể load quá nhiều dữ liệu. Dùng paging/scrolling/export streaming.

**7. Count query thiếu một điều kiện filter.**  
Ví dụ content lọc active, count không lọc; test phải có inactive fixture để bắt lỗi.

**8. Count sai do join-to-many.**  
Phân biệt row count với distinct logical entity count.

**9. Dùng collection fetch join + pageable một cách máy móc.**  
Có thể bị in-memory pagination, nhân dòng hoặc lỗi Hibernate. Page root IDs rồi fetch details khi cần.

**10. Test chỉ có giá trị sort khác nhau.**  
Không phát hiện thiếu tie-breaker. Fixture cần ít nhất hai bản ghi cùng price/name/sort key.

**11. Test chỉ trang 0.**  
Dễ bỏ qua off-by-one/last-page bug. Kiểm trang đầu, giữa, cuối và empty.

**12. Trả JPA entity trực tiếp rồi tin projection sẽ tự che hết field nhạy cảm.**  
Entity có lazy relations/proxy; response contract phải chủ động dùng DTO/projection an toàn.

**13. Cho rằng mọi interface projection đều tối ưu SQL.**  
Open projection/SpEL, nested projections và custom joins có thể tải nhiều field hơn. Đo SQL thực khi performance quan trọng.

**14. JPQL constructor expression sai tên package/constructor.**  
Dùng fully-qualified DTO name, đúng thứ tự và kiểu; không thêm alias trong constructor arguments.

**15. Dùng native query phức tạp mà không định nghĩa countQuery.**  
Automatic parsing không xử lý đáng tin mọi trường hợp; test cả total và dialect.

**16. Cộng tiền bằng double.**  
Có sai số nhị phân; dùng `BigDecimal`, định nghĩa scale và currency.

**17. Mong `SUM` của tập rỗng luôn là 0.**  
SQL/JPQL thường trả null. Xác định contract và xử lý, đồng thời test.

**18. Nhầm COUNT(row) với SUM(amount).**  
`totalElements=5` không có nghĩa tổng tiền =5 hoặc số nhóm=5.

**19. Assert COUNT SQL luôn chạy đúng một lần.**  
Framework có thể tối ưu. Test public metadata trước, performance riêng.

**20. Dùng H2 để kết luận sort/collation/native SQL giống PostgreSQL.**  
Cần test container DB đúng dialect khi behavior đó quan trọng.

**21. Không kiểm dữ liệu biến động giữa các trang.**  
Offset có thể lặp/bỏ sót khi có inserts/deletes; dùng cursor/snapshot khi contract cần.

**22. Không nhận ra data total có thể lệch do visibility/security.**  
Mọi count/aggregate phải áp dụng tenant/auth/soft-delete filters giống content.

## 15. Quy trình thiết kế bài test pagination/sort/projection/totals

1. **Viết dữ liệu fixture** có tie sort, inactive/soft-deleted, category khác nhau và trường hợp empty.
2. **Định nghĩa predicate chính xác** của query nội dung, ví dụ `active=true AND category=:category`.
3. **Chọn Page/Slice/List** theo UX có cần total không.
4. **Thiết kế sort** gồm thứ tự chính và unique tie-breaker.
5. **Định nghĩa projection** chỉ gồm những property cần cho contract; DTO record với JPQL constructor khi cần.
6. **Định nghĩa total**: total matching rows, distinct logical roots, số groups hay tổng tiền?
7. **Kiểm page 0 và các page sau**; assert `getContent`, `getTotalElements`, `getTotalPages` và hasNext/last.
8. **Kiểm Slice** không dựa vào total metadata; assert hasNext và content.
9. **Kiểm projection** đúng getters/record fields, mapping/serialization khi qua HTTP.
10. **Kiểm aggregate** với dữ liệu số hữu hạn, cùng predicate, phân biệt group count và sum.
11. **Kiểm empty/invalid inputs**: total0, trang rỗng, page âm, size0/quá max, invalid sort.
12. **Kiểm DB-specific cases**: join duplicates, collation, native SQL, transaction isolation và concurrent writes.
13. **Quan sát SQL/performance** riêng với correctness assertions.
14. **Chạy CI có rollback/cleanup** để test không phụ thuộc thứ tự hoặc state từ test khác.
15. **Duy trì API contract** không lộ entity internals, tenant data hay sai total.

### Checklist trước khi commit

- [ ] Query có predicate rõ ràng và count query giữ đúng predicate.
- [ ] `PageRequest` được dùng với 0-based page và size dương/giới hạn.
- [ ] Sort sử dụng tên property/alias hợp lệ; có unique secondary key nếu cần ổn định.
- [ ] Đã test các hàng có sort key bằng nhau.
- [ ] Có test trang đầu, giữa, cuối, empty và invalid args.
- [ ] Phân biệt `Page.getTotalElements` với `getNumberOfElements`.
- [ ] `Slice` không được sử dụng để khẳng định totalPages.
- [ ] Interface projection getters khớp entity properties và đúng dữ liệu.
- [ ] DTO projection có constructor expression/return type tương thích, countQuery đúng.
- [ ] Nested/open projections không được mặc định xem là SQL tối ưu.
- [ ] Count distinct đúng khi có join/relationships và group results.
- [ ] Dữ liệu tổng dùng `BigDecimal`, quy ước null/zero/currency rõ.
- [ ] Aggregate filters khớp business visibility và count filters.
- [ ] @DataJpaTest có fixture chủ động, flush/clear và rollback/cleanup đúng.
- [ ] SQL/native/locale/collation/concurrency quan trọng có test database production-like.
- [ ] HTTP layer trả DTO có contract ổn định, validate size/sort và không lộ trường riêng tư.

**Kết luận:** phân trang đúng không chỉ là gọi `PageRequest.of(...)`. Bạn phải kiểm **đúng nội dung, đúng thứ tự, tổng số đúng bộ lọc và giới hạn nhất quán**. `Page` cho total metadata, `Slice` cho next-page navigation, projection cho dữ liệu gọn, còn `COUNT/SUM/GROUP BY` trả số liệu nghiệp vụ. Một bộ `@DataJpaTest` với dữ liệu có tie, inactive rows, nhiều nhóm và trang rỗng sẽ phát hiện phần lớn lỗi triển khai trước khi chúng xuất hiện trên API.

### Tài liệu tham khảo chính thức

- [Spring Data JPA 3.5 — Defining Query Methods: paging, sorting, limiting](https://docs.spring.io/spring-data/jpa/reference/3.5/repositories/query-methods-details.html): `Page`, `Slice`, `List`, `Pageable`, `Sort`, `ScrollPosition`.
- [Spring Data JPA 3.5 — Projections](https://docs.spring.io/spring-data/jpa/reference/3.5/repositories/projections.html): closed/open interface projection, DTO record, dynamic projection, nested join considerations.
- [Spring Data JPA 3.5 — JPA Query Methods](https://docs.spring.io/spring-data/jpa/reference/3.5/jpa/query-methods.html): `@Query`, JPQL constructor expressions, custom count query, native query, Sort rules.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@DataJpaTest` slice và test datasource.
- [Spring Data Commons API — Page](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Page.html): totalElements, totalPages và các Page methods.
- [Spring Data Commons API — Slice](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Slice.html): navigation metadata không cần total count.
- [Spring Data Commons API — PageRequest](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/PageRequest.html): page index, size và Sort.
