# Kết hợp điều kiện, sắp xếp tĩnh và giới hạn từ tên phương thức

Spring Data R2DBC cho phép khai báo truy vấn ngay trong tên phương thức của repository. Spring Data phân tích tên phương thức, nhận diện thuộc tính entity và các từ khóa như `And`, `Or`, `GreaterThan`, `OrderBy`, `First` hoặc `Top`, sau đó tạo câu SQL phù hợp với mapping và dialect của database.

Cách này phù hợp với các truy vấn có cấu trúc ổn định: tìm theo nhiều điều kiện, luôn sắp xếp theo cùng một thứ tự và chỉ lấy một số lượng kết quả tối đa. Nhờ đó, repository thể hiện rõ ý nghĩa truy vấn ngay trong hợp đồng Java, còn ứng dụng không phải tự ghép chuỗi SQL.

## 1. Cấu trúc tên phương thức truy vấn

Một tên derived query thường có các phần sau:

```text
find[Distinct][TopN|FirstN]By<Predicate>OrderBy<Property><Asc|Desc>
```

Các phần có ý nghĩa:

- `find`, `read`, `get`, `query` hoặc `search` là phần mô tả thao tác đọc.
- `Distinct` yêu cầu loại bỏ các hàng trùng theo ngữ nghĩa truy vấn.
- `TopN` hoặc `FirstN` giới hạn số kết quả tối đa.
- `By` bắt đầu phần điều kiện lọc.
- Predicate chứa tên thuộc tính và từ khóa so sánh, có thể kết hợp bằng `And` hoặc `Or`.
- `OrderBy` bắt đầu phần sắp xếp tĩnh.
- `Asc` và `Desc` xác định hướng sắp xếp cho từng thuộc tính.

Ví dụ:

```java
Flux<Product> findTop20ByStatusAndCategoryOrderByCreatedAtDescIdDesc(
    String status,
    String category
);
```

Tên phương thức thể hiện truy vấn tìm sản phẩm theo `status` và `category`, sắp xếp `createdAt` giảm dần rồi `id` giảm dần, và trả về tối đa 20 sản phẩm.

Không phải mọi từ trong tên phương thức đều là tên cột SQL. Spring Data diễn giải chúng theo thuộc tính của lớp entity, rồi dùng mapping metadata để xác định tên cột và kiểu dữ liệu tương ứng.

## 2. Khai báo repository reactive

Giả sử có entity `Product`:

```java
import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("product")
public class Product {

    @Id
    private Long id;

    private String name;

    private String status;

    private String category;

    private BigDecimal price;

    @Column("created_at")
    private Instant createdAt;

    // Constructor, getters và setters được lược bớt.
}
```

Repository kế thừa `ReactiveCrudRepository`:

```java
import java.math.BigDecimal;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {

    Flux<Product> findByStatusAndCategory(
        String status,
        String category
    );

    Flux<Product> findByPriceGreaterThanEqual(BigDecimal minPrice);

    Flux<Product> findByStatusOrderByCreatedAtDescIdDesc(String status);

    Flux<Product> findTop20ByStatusOrderByCreatedAtDescIdDesc(String status);

    Mono<Product> findFirstByNameOrderByCreatedAtDescIdDesc(String name);
}
```

Spring Data tạo implementation cho các phương thức truy vấn khi khởi tạo repository. Ứng dụng chỉ khai báo chữ ký phương thức; không cần viết phần thân để thực hiện SQL.

## 3. Kết hợp điều kiện bằng And và Or

`And` và `Or` cho phép mô tả nhiều điều kiện ngay trong tên phương thức.

### 3.1. Kết hợp AND

Ví dụ tìm sản phẩm có trạng thái `ACTIVE`, thuộc danh mục được chỉ định và có giá từ một mức trở lên:

```java
Flux<Product> findByStatusAndCategoryAndPriceGreaterThanEqual(
    String status,
    String category,
    BigDecimal minPrice
);
```

Các tham số được gắn với điều kiện theo thứ tự xuất hiện trong predicate:

| Phần tên phương thức | Tham số | Ý nghĩa |
|---|---|---|
| `Status` | `status` | Trạng thái bằng giá trị truyền vào |
| `AndCategory` | `category` | Đồng thời phải thuộc danh mục truyền vào |
| `AndPriceGreaterThanEqual` | `minPrice` | Giá lớn hơn hoặc bằng mức tối thiểu |

Về logic, truy vấn tương đương:

```sql
SELECT ...
FROM product
WHERE status = :status
  AND category = :category
  AND price >= :minPrice;
```

Đây là SQL minh họa để giải thích ý nghĩa. SQL thực tế do Spring Data và dialect của driver tạo ra, có thể dùng bind marker khác.

### 3.2. Kết hợp OR

Ví dụ tìm sản phẩm có trạng thái `ACTIVE` hoặc thuộc danh mục `FEATURED`:

```java
Flux<Product> findByStatusOrCategory(
    String status,
    String category
);
```

Điều kiện có nghĩa:

```sql
WHERE status = :status OR category = :category
```

`Or` mở rộng tập kết quả: chỉ cần một nhánh đúng là hàng có thể được trả về.

### 3.3. Kết hợp nhiều nhánh AND/OR

Tên phương thức có thể kết hợp cả hai từ khóa, nhưng biểu thức dài sẽ khó đọc và dễ hiểu sai. Ví dụ:

```java
Flux<Product> findByStatusAndCategoryOrFeaturedTrue(
    String status,
    String category
);
```

Khi cần biểu thức có ngoặc rõ ràng, chẳng hạn `(status = ? AND category = ?) OR featured = true`, hãy xác nhận cách parser nhóm các predicate trong phiên bản Spring Data đang dùng. Không nên đặt một biểu thức nghiệp vụ quan trọng vào một tên phương thức quá dài mà không có integration test.

Nếu logic cần nhiều nhóm lồng nhau hoặc ngoặc phức tạp, dùng `@Query` với SQL tường minh hoặc `R2dbcEntityTemplate` cùng `Criteria` thường dễ kiểm soát hơn.

## 4. Các từ khóa so sánh thường dùng

Spring Data hỗ trợ nhiều từ khóa để diễn đạt điều kiện theo thuộc tính entity. Một số từ khóa phổ biến:

| Từ khóa | Ý nghĩa | Ví dụ |
|---|---|---|
| `Is`, `Equals` | Bằng | `findByStatus(String status)` |
| `Not` | Khác | `findByStatusNot(String status)` |
| `GreaterThan` | Lớn hơn | `findByPriceGreaterThan(BigDecimal price)` |
| `GreaterThanEqual` | Lớn hơn hoặc bằng | `findByPriceGreaterThanEqual(BigDecimal price)` |
| `LessThan` | Nhỏ hơn | `findByPriceLessThan(BigDecimal price)` |
| `LessThanEqual` | Nhỏ hơn hoặc bằng | `findByPriceLessThanEqual(BigDecimal price)` |
| `Between` | Nằm trong khoảng | `findByPriceBetween(BigDecimal from, BigDecimal to)` |
| `After`, `Before` | Sau hoặc trước một giá trị thời gian/thứ tự phù hợp | `findByCreatedAtAfter(Instant time)` |
| `In` | Thuộc một tập | `findByStatusIn(Collection<String> statuses)` |
| `NotIn` | Không thuộc một tập | `findByStatusNotIn(Collection<String> statuses)` |
| `IsNull` | Giá trị null | `findByDeletedAtIsNull()` |
| `IsNotNull` | Giá trị không null | `findByDeletedAtIsNotNull()` |
| `Like` | Khớp mẫu LIKE | `findByNameLike(String pattern)` |
| `Containing` | Chứa chuỗi con | `findByNameContaining(String part)` |
| `StartingWith` | Bắt đầu bằng chuỗi | `findByNameStartingWith(String prefix)` |
| `EndingWith` | Kết thúc bằng chuỗi | `findByNameEndingWith(String suffix)` |
| `True`, `False` | Giá trị boolean | `findByFeaturedTrue()` |

Tập từ khóa và cách diễn giải có thể phụ thuộc phiên bản Spring Data Relational. Khi dùng từ khóa ít phổ biến, hãy đối chiếu tài liệu/Javadoc của phiên bản được quản lý bởi Spring Boot trong dự án.

Ví dụ tìm sản phẩm có giá trong một khoảng và trạng thái cụ thể:

```java
Flux<Product> findByStatusAndPriceBetween(
    String status,
    BigDecimal minPrice,
    BigDecimal maxPrice
);
```

Ví dụ tìm theo một tập trạng thái:

```java
Flux<Product> findByStatusIn(Collection<String> statuses);
```

Nếu collection rỗng, hãy xác định hành vi nghiệp vụ trước khi gọi repository. Đừng để một danh sách rỗng vô tình dẫn đến truy vấn rộng hoặc kết quả khó hiểu.

## 5. Sắp xếp tĩnh bằng OrderBy

`OrderBy` cho phép khai báo thứ tự sắp xếp cố định trong tên phương thức. Ví dụ:

```java
Flux<Product> findByStatusOrderByCreatedAtDesc(String status);
```

Phương thức này tìm theo trạng thái và luôn sắp xếp thời gian tạo giảm dần. Ứng dụng không cần truyền đối tượng `Sort` trong mỗi lần gọi.

Có thể sắp xếp theo nhiều thuộc tính:

```java
Flux<Product> findByStatusOrderByStatusAscCreatedAtDescIdDesc(
    String status
);
```

Spring Data đọc các cặp thuộc tính và hướng sắp xếp từ trái sang phải:

1. `status` tăng dần.
2. `createdAt` giảm dần.
3. `id` giảm dần.

Trong nhiều truy vấn, chỉ cần sắp xếp theo một thuộc tính là đủ. Tuy nhiên, nếu cột sắp xếp không duy nhất, nhiều hàng có thể có cùng giá trị. Thêm một khóa duy nhất như `id` làm tiêu chí cuối giúp thứ tự ổn định hơn.

### 5.1. Tại sao cần thứ tự ổn định?

Giả sử có nhiều sản phẩm cùng `createdAt`. Nếu chỉ sắp xếp theo thời gian tạo, database có thể trả các hàng cùng timestamp theo thứ tự khác nhau giữa những lần thực thi. Khi kết hợp giới hạn hoặc phân trang, điều này có thể làm hàng bị lặp hoặc bị bỏ qua giữa các lượt đọc.

Nên khai báo:

```java
Flux<Product> findByStatusOrderByCreatedAtDescIdDesc(String status);
```

`id` là khóa duy nhất nên tạo thứ tự phân định khi `createdAt` bằng nhau. Điều này đặc biệt hữu ích khi lấy các batch hoặc xây dựng cursor tiếp theo.

### 5.2. OrderBy dùng tên thuộc tính entity

Trong entity ví dụ, thuộc tính Java là `createdAt`, còn cột database là `created_at`:

```java
@Column("created_at")
private Instant createdAt;
```

Tên phương thức sử dụng `CreatedAt`:

```java
findByStatusOrderByCreatedAtDesc(...)
```

Spring Data dùng mapping metadata để ánh xạ property sang tên cột. Không viết `OrderByCreated_atDesc` chỉ vì tên cột vật lý có dấu gạch dưới.

## 6. Giới hạn kết quả bằng First và Top

Có thể giới hạn số hàng tối đa ngay trong tên phương thức bằng `First` hoặc `Top`.

```java
Flux<Product> findTop10ByStatusOrderByCreatedAtDescIdDesc(
    String status
);
```

Phương thức trên trả về tối đa 10 sản phẩm phù hợp với trạng thái, được sắp xếp theo thời gian tạo và ID giảm dần.

`First` và `Top` có ý nghĩa giới hạn kết quả tương tự. Có thể viết:

```java
Flux<Product> findFirst10ByStatusOrderByCreatedAtDescIdDesc(
    String status
);
```

Nếu không ghi số sau `First` hoặc `Top`, giới hạn mặc định là một kết quả:

```java
Mono<Product> findFirstBySku(String sku);
```

Khi cần chọn một hàng trong số nhiều hàng phù hợp, nên kết hợp với `OrderBy` để xác định hàng nào được chọn:

```java
Mono<Product> findFirstByCategoryOrderByCreatedAtDescIdDesc(
    String category
);
```

Nếu không có thứ tự, khái niệm “đầu tiên” không đảm bảo hàng nào sẽ được chọn bởi database. Thứ tự trả về có thể thay đổi theo execution plan hoặc dữ liệu.

### 6.1. Top/First kết hợp nhiều điều kiện

Các từ khóa giới hạn có thể đứng trước `By`, còn predicate và sort theo sau:

```java
Flux<Product> findTop20ByStatusAndCategoryOrderByCreatedAtDescIdDesc(
    String status,
    String category
);
```

Giới hạn được áp dụng trên tập kết quả thỏa mãn điều kiện và thứ tự sắp xếp. Về ý nghĩa, database tìm các hàng phù hợp, sắp xếp chúng rồi trả về tối đa 20 hàng.

### 6.2. Giới hạn là số lượng tối đa

`Top20` không bảo đảm lúc nào cũng có đúng 20 hàng. Nếu chỉ có 7 hàng phù hợp, kết quả có tối đa 7 hàng. Nếu không có hàng phù hợp, `Flux` hoàn tất mà không phát phần tử.

Với phương thức trả về `Mono<T>` và không có kết quả, publisher hoàn tất rỗng. Khi dùng `switchIfEmpty`, service có thể chuyển thành lỗi nghiệp vụ hoặc fallback theo yêu cầu.

## 7. Kết hợp điều kiện, sort và limit trong một repository

Ví dụ repository cho chức năng danh sách sản phẩm:

```java
public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {

    // Điều kiện AND.
    Flux<Product> findByStatusAndCategory(
        String status,
        String category
    );

    // Điều kiện so sánh.
    Flux<Product> findByPriceGreaterThanEqual(BigDecimal minPrice);

    // Sắp xếp tĩnh theo nhiều thuộc tính.
    Flux<Product> findByStatusOrderByCreatedAtDescIdDesc(String status);

    // Kết hợp AND + sort tĩnh + giới hạn 20 hàng.
    Flux<Product> findTop20ByStatusAndCategoryOrderByCreatedAtDescIdDesc(
        String status,
        String category
    );

    // Chọn một kết quả mới nhất.
    Mono<Product> findFirstByCategoryOrderByCreatedAtDescIdDesc(
        String category
    );

    // Các truy vấn tổng hợp.
    Mono<Long> countByStatus(String status);

    Mono<Boolean> existsBySku(String sku);
}
```

Service có thể sử dụng trực tiếp:

```java
public Flux<Product> findFeaturedProducts(String category) {
    return productRepository
        .findTop20ByStatusAndCategoryOrderByCreatedAtDescIdDesc(
            "ACTIVE",
            category
        );
}
```

Publisher được trả về cho tầng gọi. Trong WebFlux, framework có thể subscribe và ghi kết quả theo mô hình reactive; không cần gọi `block()` trong service.

## 8. Ý nghĩa của kiểu trả về Mono và Flux

Kiểu trả về nên phản ánh số lượng kết quả dự kiến và cách ứng dụng xử lý dữ liệu:

| Kiểu trả về | Ý nghĩa |
|---|---|
| `Flux<Product>` | Không, một hoặc nhiều sản phẩm; phù hợp danh sách và Top N |
| `Mono<Product>` | Tối đa một sản phẩm; phù hợp `First` hoặc truy vấn theo khóa duy nhất |
| `Mono<Long>` | Một giá trị đếm, thường dùng với `countBy...` |
| `Mono<Boolean>` | Một giá trị kiểm tra tồn tại, thường dùng với `existsBy...` |

Ví dụ:

```java
Mono<Long> activeCount = productRepository.countByStatus("ACTIVE");
Mono<Boolean> skuExists = productRepository.existsBySku("SKU-100");
```

Không dùng `Mono<List<Product>>` chỉ vì truy vấn có giới hạn nhỏ nếu `Flux<Product>` đã diễn đạt đúng luồng dữ liệu. Nếu cần danh sách trong bộ nhớ cho một use case cụ thể, có thể chủ động gọi `collectList()` ở tầng service sau khi đã giới hạn số hàng.

## 9. Tham số null và điều kiện tùy chọn

Derived query thể hiện một cấu trúc điều kiện cố định. Ví dụ:

```java
Flux<Product> findByStatusAndCategory(String status, String category);
```

Phương thức này luôn có cả hai điều kiện. Truyền `null` không có nghĩa là tự động bỏ qua điều kiện tương ứng. Với phép so sánh bằng, Spring Data thường diễn giải tham số null thành điều kiện kiểm tra null (`IS NULL`) theo semantics của derived query.

Nếu muốn bỏ qua một filter khi request không gửi giá trị, cần chọn cách khác:

- Tạo các phương thức repository riêng cho những tổ hợp filter ổn định và ít.
- Dùng `R2dbcEntityTemplate` với `Query`/`Criteria` để thêm điều kiện theo request.
- Dùng `@Query` nếu câu SQL động có cấu trúc phù hợp và được kiểm soát rõ.

Ví dụ filter có thể bỏ qua `category`:

```java
Flux<Product> search(ProductFilter filter) {
    if (filter.category() == null) {
        return repository.findByStatusOrderByCreatedAtDescIdDesc(
            filter.status()
        );
    }

    return repository.findByStatusAndCategory(
        filter.status(),
        filter.category()
    );
}
```

Với nhiều filter tùy chọn, số lượng tổ hợp phương thức có thể tăng rất nhanh. Khi đó, `Criteria` thường dễ bảo trì hơn việc tạo hàng chục derived methods.

## 10. Tên thuộc tính và đường dẫn thuộc tính lồng nhau

Spring Data phân tích tên property theo mô hình domain. Nếu entity có thuộc tính lồng nhau, query derivation có thể đi theo property path.

Ví dụ:

```java
public class Address {
    private String city;
    private String postalCode;
}

public class Customer {
    @Id
    private Long id;

    private Address address;
}
```

Một phương thức có thể sử dụng property path như:

```java
Flux<Customer> findByAddressCity(String city);
```

Khi tên property có thể gây nhập nhằng, dấu gạch dưới có thể dùng để làm rõ ranh giới đường dẫn trong parser:

```java
Flux<Customer> findByAddress_City(String city);
```

Khả năng ánh xạ object lồng nhau thành cột hoặc quan hệ phụ thuộc mô hình Spring Data Relational và cách entity được cấu hình. Đây không phải join tự động giữa hai bảng theo quy tắc ORM JPA. Nếu cần join nhiều bảng, hãy cân nhắc SQL tường minh hoặc projection phù hợp.

## 11. IgnoreCase, Containing và tìm kiếm chuỗi

Một số từ khóa hỗ trợ tìm kiếm chuỗi:

```java
Flux<Product> findByNameContainingIgnoreCase(String part);

Flux<Product> findByNameStartingWithIgnoreCase(String prefix);

Flux<Product> findByNameEndingWith(String suffix);
```

`Containing` biểu diễn tìm chuỗi con, thường được chuyển thành mẫu LIKE có wildcard ở hai đầu. `StartingWith` và `EndingWith` lần lượt biểu diễn tiền tố và hậu tố. `IgnoreCase` yêu cầu so sánh không phân biệt hoa thường trong phạm vi mà database/dialect hỗ trợ.

Hành vi collation, Unicode và chữ hoa/thường phụ thuộc database. Với ngôn ngữ có quy tắc biến đổi chữ phức tạp, hãy kiểm thử dữ liệu thực tế thay vì giả định `IgnoreCase` luôn tạo kết quả theo quy tắc ngôn ngữ mong muốn.

Khi người dùng nhập `%` hoặc `_`, các ký tự này có thể được hiểu là wildcard của LIKE. Nếu nghiệp vụ yêu cầu tìm literal, cần escape theo dialect phù hợp.

## 12. Đếm và kiểm tra tồn tại với điều kiện

Derived query không chỉ trả entity. Có thể khai báo truy vấn tổng hợp:

```java
Mono<Long> countByStatusAndCategory(String status, String category);

Mono<Boolean> existsByStatusAndPriceGreaterThanEqual(
    String status,
    BigDecimal minPrice
);
```

`countBy...` trả về số lượng hàng phù hợp; `existsBy...` trả về kết quả kiểm tra tồn tại. Dùng những phương thức này khi nghiệp vụ cần số đếm hoặc boolean, tránh tải toàn bộ entity chỉ để đếm hoặc kiểm tra có dữ liệu.

Đếm chính xác có thể tốn chi phí trên bảng lớn, tùy predicate, index và database. Hãy kiểm tra execution plan và chỉ dùng khi use case thực sự cần.

## 13. Giới hạn tĩnh so với phân trang động

`TopN` và `FirstN` rất tiện khi giới hạn là một phần cố định của nghiệp vụ, ví dụ:

- Lấy 5 đơn hàng gần nhất cho dashboard.
- Lấy 10 sản phẩm nổi bật.
- Lấy một bản ghi mới nhất cho mỗi tiêu chí duy nhất.
- Lấy tối đa 100 sự kiện cần xử lý trong một lượt.

Nếu số lượng kết quả hoặc offset thay đổi theo request, method name tĩnh có thể không còn phù hợp. Khi đó, hãy cân nhắc API hỗ trợ `Pageable`/`Limit` theo phiên bản Spring Data R2DBC hoặc dùng `R2dbcEntityTemplate` với `Query.limit(...)` và `Query.offset(...)`.

Reactive repository thường trả `Flux` thay vì một `Page` chứa toàn bộ dữ liệu và tổng số trang. Nếu giao diện cần tổng số chính xác, hãy xác định rõ chi phí của truy vấn count riêng. Với dữ liệu lớn được đọc tuần tự, keyset pagination có thể hiệu quả hơn offset.

## 14. Giới hạn và bảo vệ hiệu năng

`TopN` giới hạn số hàng trả về nhưng không tự bảo đảm truy vấn rẻ. Ví dụ:

```java
Flux<Product> findTop20ByStatusOrderByCreatedAtDescIdDesc(String status);
```

Nếu bảng rất lớn và database không có index phù hợp cho `status`, `created_at` và `id`, database vẫn có thể phải quét hoặc sắp xếp nhiều hàng trước khi tìm được 20 kết quả.

Khi truy vấn thường xuyên, hãy xem xét index phù hợp với điều kiện và thứ tự sắp xếp. Ví dụ với PostgreSQL, một index có thể được cân nhắc theo thứ tự `(status, created_at DESC, id DESC)`, nhưng index tối ưu phụ thuộc selectivity, workload, kiểu truy vấn và hệ quản trị.

Các điểm cần kiểm tra:

- Predicate có chọn lọc đủ tốt không?
- Các cột lọc và sắp xếp có index phù hợp không?
- Có cần chọn ít cột hơn qua projection không?
- `TopN` có đủ nhỏ để phù hợp với SLA và bộ nhớ downstream không?
- Thứ tự sort có ổn định và có khóa phân định duy nhất không?
- Query plan có sử dụng index theo kỳ vọng không?

## 15. Khi nào nên chuyển sang @Query hoặc Criteria?

Derived query dễ đọc khi điều kiện đơn giản và tên phương thức còn ngắn. Tuy nhiên, có những trường hợp nên dùng cách biểu đạt khác.

| Tình huống | Cách tiếp cận thường phù hợp |
|---|---|
| Một vài điều kiện AND đơn giản | Derived query |
| Điều kiện so sánh, sort tĩnh và Top N | Derived query |
| Filter tùy chọn với nhiều tổ hợp | `R2dbcEntityTemplate` + `Criteria` |
| Biểu thức AND/OR lồng nhau phức tạp | `Criteria` hoặc `@Query` với SQL tường minh |
| Join nhiều bảng và DTO projection | `@Query` hoặc `DatabaseClient` |
| CTE, window function hoặc SQL đặc thù database | `@Query` hoặc `DatabaseClient` |
| Tên phương thức quá dài và khó hiểu | Chuyển logic sang truy vấn tường minh |

Ví dụ `@Query` khi cần biểu thức SQL rõ ràng:

```java
@Query("""
    SELECT id, name, status, category, price, created_at
    FROM product
    WHERE (status = :status AND category = :category)
       OR featured = true
    ORDER BY created_at DESC, id DESC
    LIMIT 20
    """)
Flux<Product> findMatchingFeatured(
    String status,
    String category
);
```

Đoạn SQL sử dụng `LIMIT` theo cú pháp PostgreSQL/MySQL và không phải cú pháp phổ quát cho mọi hệ quản trị. Với database khác, cần điều chỉnh dialect. Ưu điểm là nhóm ngoặc logic được thể hiện rõ; đổi lại, ứng dụng chịu trách nhiệm duy trì SQL theo schema và dialect.

## 16. Kiểm thử derived query

Kiểm thử tích hợp nên xác nhận Spring Data phân tích tên phương thức và tạo truy vấn đúng trên database/driver tương thích.

Các tình huống nên kiểm tra:

- Kết hợp nhiều điều kiện AND và OR.
- Giá trị biên cho `GreaterThan`, `GreaterThanEqual`, `Between`, `Before` và `After`.
- Thứ tự sort khi nhiều hàng có cùng giá trị ở cột đầu tiên.
- `TopN`/`FirstN` trả không quá số hàng yêu cầu.
- Không có kết quả với `Flux` và `Mono`.
- `In` với collection rỗng hoặc null theo hợp đồng API.
- Null parameter và các điều kiện `IsNull`/`IsNotNull`.
- `IgnoreCase`, `Containing`, wildcard và collation thực tế.
- Tên property có `@Column` khác tên cột vật lý.
- Index và execution plan trên tập dữ liệu có quy mô gần thực tế.

Ví dụ với `StepVerifier`:

```java
StepVerifier.create(
        productRepository.findTop2ByStatusOrderByCreatedAtDescIdDesc("ACTIVE")
    )
    .expectNextCount(2)
    .verifyComplete();
```

Ví dụ giả định database có ít nhất hai sản phẩm `ACTIVE`. Test thực tế nên chuẩn bị dữ liệu có timestamp bằng nhau để xác nhận tiêu chí `id` phân định thứ tự đúng như mong đợi.

## 17. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Sai tên property trong method | Spring Data không phân tích được query hoặc tìm property không tồn tại | Dùng đúng tên thuộc tính Java của entity |
| Dùng tên cột vật lý thay tên property | Derived query không khớp mapping metadata | Dùng property như `createdAt`, không phải `created_at` |
| Truyền tham số sai thứ tự | Điều kiện nhận nhầm giá trị | Đặt tham số theo thứ tự predicate trong tên method |
| Tên method kết hợp AND/OR quá dài | Khó hiểu logic và nhóm điều kiện | Chuyển sang Criteria hoặc `@Query` |
| Nghĩ null tự động bỏ qua filter | Có thể sinh điều kiện `IS NULL` thay vì bỏ predicate | Dùng Criteria động hoặc method riêng |
| Dùng `First` mà không có sort | Hàng được chọn không có thứ tự xác định | Thêm `OrderBy` với khóa phân định |
| Dùng `TopN` nhưng không có index | Database vẫn có thể quét/sort nhiều hàng | Xem execution plan và index |
| Dùng Top/First như phân trang động | Không thể thay đổi giới hạn theo request | Dùng API phân trang phù hợp hoặc Query template |
| Sort theo tên cột tùy ý từ client | Không kiểm soát identifier | Whitelist property hoặc dùng sort được kiểm soát |
| Giả định mọi database dùng cùng cú pháp limit | SQL có thể khác dialect | Để Spring Data sinh query hoặc điều chỉnh SQL tường minh theo dialect |
| Dùng `Mono<T>` khi kết quả có thể nhiều hàng | Cardinality không phù hợp | Dùng `Flux<T>` hoặc đảm bảo điều kiện duy nhất |

## 18. Quy trình thiết kế một derived query

Khi thêm một phương thức repository, có thể thực hiện theo trình tự:

1. Xác định entity và các thuộc tính persistent sẽ tham gia điều kiện.
2. Viết predicate bằng các từ khóa đơn giản như `Is`, `GreaterThanEqual`, `In`, `IsNull`.
3. Nối điều kiện bằng `And`/`Or` và giữ tên phương thức đủ dễ đọc.
4. Thêm `OrderBy` nếu thứ tự kết quả là một phần cố định của nghiệp vụ.
5. Thêm `FirstN`/`TopN` nếu nghiệp vụ có giới hạn tối đa cố định.
6. Chọn `Mono` hoặc `Flux` theo cardinality.
7. Kiểm tra null parameter, collection rỗng và trường hợp không có kết quả.
8. Kiểm thử trên database mục tiêu và xem execution plan nếu truy vấn được dùng thường xuyên.
9. Chuyển sang Criteria hoặc SQL tường minh khi tên phương thức trở nên quá phức tạp.

## 19. Nguyên tắc cần nhớ

- Derived query được tạo từ tên phương thức repository và metadata entity.
- `And` yêu cầu các điều kiện cùng đúng; `Or` cho phép một nhánh đúng.
- Tham số được truyền theo thứ tự xuất hiện trong predicate.
- `OrderBy` khai báo thứ tự sắp xếp tĩnh bằng tên thuộc tính Java và hướng `Asc`/`Desc`.
- Có thể sắp xếp theo nhiều thuộc tính; thêm khóa duy nhất làm tiêu chí cuối để có thứ tự ổn định.
- `TopN` và `FirstN` giới hạn số hàng tối đa; không bảo đảm luôn có đủ N hàng.
- Dùng `Mono` cho tối đa một kết quả và `Flux` cho tập kết quả.
- Null trong tham số derived query không đồng nghĩa tự động bỏ qua điều kiện.
- Dùng Criteria cho filter tùy chọn và `@Query` khi cần biểu thức SQL/ngoặc logic rõ ràng.
- Dùng đúng tên property của entity, để mapping metadata chuyển sang tên cột vật lý.
- `TopN` không thay thế index hoặc tối ưu execution plan.
- Kiểm thử sort, limit, null và các giá trị biên trên database/driver thực tế.

Kết hợp điều kiện, sắp xếp tĩnh và giới hạn từ tên phương thức giúp repository mô tả các truy vấn phổ biến một cách ngắn gọn. Khi predicate còn đơn giản, `OrderBy` thể hiện thứ tự nghiệp vụ và `Top`/`First` thể hiện giới hạn kết quả, derived query là một lựa chọn dễ đọc. Khi điều kiện động hoặc biểu thức logic trở nên phức tạp, chuyển sang `Criteria` hoặc SQL tường minh sẽ giúp truy vấn dễ hiểu và dễ kiểm soát hơn.
