# Suy diễn truy vấn từ tên phương thức

Spring Data Relational R2DBC cho phép khai báo một số truy vấn repository chỉ bằng tên phương thức. Spring Data phân tích tên phương thức, nhận diện phần mở đầu như `find` hoặc `count`, phần điều kiện sau `By`, các toán tử như `And`, `Or`, `Between`, `In`, rồi tạo câu SQL dựa trên metadata của entity và dialect database.

Cơ chế này được gọi là *query derivation* hoặc *derived query methods*. Nó giúp repository biểu đạt các truy vấn CRUD và tìm kiếm thường gặp mà không cần viết SQL cho từng phương thức. Tuy nhiên, tên phương thức phải tuân theo quy tắc parser và chỉ các toán tử được Spring Data Relational hỗ trợ mới có thể được chuyển thành truy vấn. Khi logic quá phức tạp hoặc phụ thuộc tính năng riêng của database, nên dùng `@Query`, `DatabaseClient` hoặc `R2dbcEntityTemplate`.

## 1. Repository method được phân tích như thế nào?

Một derived query method thường có cấu trúc:

```text
<subject><By><predicate><OrderBy><sort properties>
```

Ví dụ:

```java
Flux<Customer> findByStatusAndAgeGreaterThanOrderByNameAsc(
        String status,
        int age
);
```

Spring Data diễn giải tên trên theo các phần:

- `find`: phương thức truy vấn dữ liệu.
- `By`: đánh dấu điểm bắt đầu của điều kiện.
- `Status`: property `status` của entity.
- `And`: nối điều kiện logic.
- `AgeGreaterThan`: property `age` với toán tử lớn hơn.
- `OrderByNameAsc`: sắp xếp kết quả theo property `name` tăng dần.

Về ý nghĩa, truy vấn tương đương:

```sql
SELECT ...
FROM customer
WHERE status = ? AND age > ?
ORDER BY name ASC
```

SQL thực tế, marker tham số và tên cột được tạo theo dialect cùng metadata mapping. Không nên coi đoạn SQL minh họa là chuỗi chính xác mà mọi driver sẽ nhận.

Spring Data phân tích phương thức khi tạo repository query. Nếu tên property không tồn tại hoặc cú pháp không được hỗ trợ, lỗi thường xuất hiện khi khởi tạo repository hoặc khi chuẩn bị query, thay vì đợi đến lúc người dùng gửi request.

## 2. Subject: phần mở đầu của tên phương thức

Subject là phần đứng trước `By`. Nó cho Spring Data biết loại thao tác cần thực hiện. Các tiền tố truy vấn phổ biến gồm:

| Subject | Ý nghĩa |
| --- | --- |
| `find…By` | Tìm entity hoặc projection |
| `read…By` | Đọc dữ liệu |
| `get…By` | Lấy dữ liệu |
| `query…By` | Thực hiện truy vấn |
| `search…By` | Tìm kiếm |
| `stream…By` | Truy vấn theo dạng stream nếu kiểu trả về và module hỗ trợ |
| `count…By` | Đếm số hàng phù hợp |
| `exists…By` | Kiểm tra có hàng phù hợp hay không |
| `delete…By` / `remove…By` | Xóa các hàng phù hợp |

Các từ mô tả subject như `find`, `read` hoặc `get` thường không làm thay đổi điều kiện SQL. Chúng giúp tên method đọc tự nhiên hơn. Ví dụ `findByEmail` và `readByEmail` cùng mô tả việc tìm theo property `email`.

Ví dụ repository:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByStatus(String status);

    Mono<Long> countByStatus(String status);

    Mono<Boolean> existsByEmail(String email);

    Mono<Void> deleteByStatus(String status);
}
```

Các kiểu trả về ở đây mang tính reactive: truy vấn nhiều entity thường dùng `Flux<T>`, kết quả đơn như count hoặc exists thường dùng `Mono<T>`. Kiểu trả về cụ thể cần phù hợp với loại query và khả năng của phiên bản Spring Data đang dùng.

## 3. Predicate: property và toán tử sau `By`

Predicate mô tả điều kiện lọc. Tên property được viết theo Java property name của entity, thường theo camelCase. Spring Data sử dụng mapping metadata để chuyển property thành tên cột theo `@Column` và naming strategy.

Ví dụ entity:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("first_name")
    private String firstName;

    private String status;

    private Integer age;
}
```

Repository method phải dùng `FirstName`, không dùng tên cột `first_name`:

```java
Flux<Customer> findByFirstName(String firstName);
```

Spring Data hiểu `FirstName` là property Java và dùng mapping để tạo điều kiện trên cột `first_name`.

### Các toán tử thường dùng

| Keyword trong method | Ý nghĩa điều kiện | Ví dụ |
| --- | --- | --- |
| `Is`, `Equals` | Bằng | `findByStatus(String status)` |
| `Not` | Khác | `findByStatusNot(String status)` |
| `GreaterThan` | Lớn hơn | `findByAgeGreaterThan(int age)` |
| `GreaterThanEqual` | Lớn hơn hoặc bằng | `findByAgeGreaterThanEqual(int age)` |
| `LessThan` | Nhỏ hơn | `findByAgeLessThan(int age)` |
| `LessThanEqual` | Nhỏ hơn hoặc bằng | `findByAgeLessThanEqual(int age)` |
| `Between` | Nằm trong khoảng | `findByAgeBetween(int min, int max)` |
| `After` | Sau một mốc thời gian | `findByCreatedAtAfter(Instant time)` |
| `Before` | Trước một mốc thời gian | `findByCreatedAtBefore(Instant time)` |
| `IsNull`, `Null` | Giá trị SQL NULL | `findByDeletedAtIsNull()` |
| `IsNotNull`, `NotNull` | Giá trị khác SQL NULL | `findByDeletedAtIsNotNull()` |
| `Like` | So khớp mẫu LIKE | `findByNameLike(String pattern)` |
| `NotLike` | Không so khớp mẫu LIKE | `findByNameNotLike(String pattern)` |
| `StartingWith` | Bắt đầu bằng chuỗi | `findByNameStartingWith(String prefix)` |
| `EndingWith` | Kết thúc bằng chuỗi | `findByNameEndingWith(String suffix)` |
| `Containing` | Chứa chuỗi con | `findByNameContaining(String part)` |
| `In` | Thuộc một tập giá trị | `findByStatusIn(Collection<String> statuses)` |
| `NotIn` | Không thuộc một tập giá trị | `findByStatusNotIn(Collection<String> statuses)` |
| `True`, `False` | Giá trị boolean | `findByEnabledTrue()` |
| `IgnoreCase` | So khớp không phân biệt hoa/thường | `findByEmailIgnoreCase(String email)` |

Các keyword trên là nhóm thường dùng trong truy vấn quan hệ. Khả năng hỗ trợ và cách sinh SQL có thể khác theo phiên bản Spring Data Relational và dialect; không nên giả định các keyword đặc thù của module khác như full-text, regex hoặc địa lý đều hoạt động trong R2DBC.

### Equals và Is

Nếu không ghi rõ toán tử, điều kiện property thường mặc định là bằng:

```java
Flux<Customer> findByStatus(String status);
Flux<Customer> findByStatusIs(String status);
Flux<Customer> findByStatusEquals(String status);
```

Các cách viết này có cùng ý nghĩa truy vấn trong trường hợp thông thường. Nên ưu tiên cách ngắn, dễ đọc.

### Between nhận hai tham số

`Between` cần hai giá trị biên:

```java
Flux<Customer> findByAgeBetween(int minimum, int maximum);
```

Tương đương về ý nghĩa với điều kiện `age BETWEEN ? AND ?`. Giá trị biên được bao gồm theo semantics của SQL `BETWEEN`.

### In nhận tập giá trị

`In` dùng khi property cần khớp với một trong nhiều giá trị:

```java
Flux<Customer> findByStatusIn(Collection<String> statuses);
```

Lời gọi:

```java
repository.findByStatusIn(List.of("ACTIVE", "PENDING"));
```

đại diện cho điều kiện status thuộc tập giá trị đã truyền. Kiểm tra trường hợp collection rỗng theo hành vi của phiên bản Spring Data/dialect đang dùng; nếu danh sách rỗng là đầu vào hợp lệ trong nghiệp vụ, nên xử lý rõ trước khi gọi repository.

### LIKE, StartingWith, EndingWith và Containing

`Like` thường nhận pattern do caller cung cấp, có thể bao gồm ký tự wildcard SQL `%` và `_`:

```java
Flux<Customer> findByNameLike(String pattern);
```

`StartingWith`, `EndingWith` và `Containing` diễn đạt ý định rõ hơn và framework tự xây dựng pattern tương ứng:

```java
Flux<Customer> findByNameStartingWith(String prefix);
Flux<Customer> findByNameEndingWith(String suffix);
Flux<Customer> findByNameContaining(String part);
```

Các toán tử này phù hợp với property dạng chuỗi. Cách xử lý ký tự wildcard và collation phụ thuộc SQL/dialect. Nếu đầu vào có `%` hoặc `_` và nghiệp vụ muốn tìm đúng ký tự literal, cần kiểm tra quy tắc escape của module và database.

### IgnoreCase

`IgnoreCase` thường dùng cho property chuỗi:

```java
Mono<Customer> findByEmailIgnoreCase(String email);
```

Spring Data tạo biểu thức so sánh không phân biệt hoa/thường theo khả năng dialect, thường dựa trên chuyển đổi chữ hoa/thường. Kết quả còn phụ thuộc collation và quy tắc Unicode của database. Không áp dụng keyword này tùy tiện cho kiểu không phải chuỗi.

## 4. Kết hợp điều kiện bằng `And` và `Or`

Có thể nối nhiều điều kiện trong một method:

```java
Flux<Customer> findByStatusAndAgeGreaterThan(
        String status,
        int age
);

Flux<Customer> findByFirstNameOrLastName(
        String firstName,
        String lastName
);
```

Ví dụ đầu tương ứng với `status = ? AND age > ?`; ví dụ thứ hai tương ứng với `first_name = ? OR last_name = ?` theo mapping của entity.

Một method có thể kết hợp cả hai:

```java
Flux<Customer> findByStatusAndAgeGreaterThanOrVipTrue(
        String status,
        int age
);
```

Khi có nhiều toán tử logic, parser chia predicate theo các nhóm `Or`, trong mỗi nhóm kết hợp các phần `And`. Do đó biểu thức trên được hiểu theo cấu trúc:

```text
(status = ? AND age > ?) OR (vip = true)
```

Tên method dài và nhiều `Or` dễ gây nhầm về phạm vi điều kiện. Nếu logic có nhiều nhánh, lồng nhóm phức tạp hoặc yêu cầu ngoặc cụ thể, hãy dùng `@Query` hay xây dựng truy vấn bằng API phù hợp để thể hiện biểu thức rõ ràng.

## 5. Property path và thuộc tính lồng nhau

Tên method tham chiếu tới property của entity, không phải tên cột SQL. Với object có property lồng nhau, Spring Data có thể phân tích property path theo mapping metadata nếu cấu trúc đó được hỗ trợ trong mô hình relational.

Ví dụ entity có một object địa chỉ được ánh xạ embedded:

```java
public class Address {
    private String city;
    private String postalCode;
}

@Table("customer")
public class Customer {

    @Id
    private Long id;

    private Address address;
}
```

Khi property path hợp lệ theo mapping, có thể dùng dấu gạch dưới để làm rõ ranh giới path:

```java
Flux<Customer> findByAddress_City(String city);
```

Dấu `_` là dấu phân tách path trong parser; nó không biểu thị tên cột. Tên cột thực tế vẫn do mapping của embedded property và naming strategy quyết định.

### Khi tên property gây mơ hồ

Giả sử entity có cả property `addressZip` và object `address` chứa property `zipCode`. Tên method viết liền có thể khiến parser chọn đường phân tích không như dự định. Dấu `_` giúp chỉ rõ đường dẫn:

```java
Flux<Customer> findByAddress_ZipCode(String zipCode);
```

Nếu có thể, hãy đặt tên property rõ ràng và tránh tên method quá dài. Property path phải tồn tại trong entity mapping; không thể dùng tên cột tùy ý hoặc tên property không được ánh xạ.

## 6. Sắp xếp bằng `OrderBy`

Có thể thêm `OrderBy` ở cuối method để mô tả thứ tự kết quả:

```java
Flux<Customer> findByStatusOrderByLastNameAscFirstNameAsc(String status);
```

Method này lọc theo status, sau đó sắp xếp theo `lastName` tăng dần và `firstName` tăng dần.

Các hướng sắp xếp thường dùng:

- `Asc`: tăng dần.
- `Desc`: giảm dần.

Ví dụ:

```java
Flux<Customer> findByStatusOrderByCreatedAtDesc(String status);
Flux<Customer> findByStatusOrderByAgeAscNameDesc(String status);
```

Trong method thứ hai, kết quả được sắp theo tuổi tăng dần, rồi tên giảm dần trong các trường hợp tuổi bằng nhau.

Nếu cần thứ tự thay đổi theo request, có thể dùng tham số `Sort` khi phương thức query và phiên bản Spring Data hỗ trợ. Ví dụ hình thức:

```java
Flux<Customer> findByStatus(String status, Sort sort);
```

Hãy kiểm tra API của phiên bản dự án và bảo đảm các property trong `Sort` là property hợp lệ của entity. Không nối trực tiếp chuỗi sắp xếp do người dùng gửi vào SQL.

## 7. Giới hạn số kết quả với `First` và `Top`

`First` và `Top` giới hạn số hàng trả về. Có thể dùng không kèm số để giới hạn một hàng hoặc thêm số để chỉ định số lượng:

```java
Mono<Customer> findFirstByStatusOrderByCreatedAtDesc(String status);

Flux<Customer> findTop10ByStatusOrderByCreatedAtDesc(String status);
```

Ví dụ đầu lấy customer mới nhất theo status; ví dụ sau lấy tối đa 10 customer mới nhất. `Top` và `First` là giới hạn của truy vấn, không phải toán tử lấy phần tử đầu tiên sau khi tải toàn bộ dữ liệu về ứng dụng.

Nên kết hợp giới hạn với `OrderBy` nếu cần xác định chính xác bản ghi nào được chọn. Nếu không có thứ tự, database không bảo đảm hàng nào sẽ là hàng đầu tiên.

### Mono hay Flux?

Chọn kiểu trả về theo số phần tử mong đợi:

```java
Mono<Customer> findByEmail(String email);
Flux<Customer> findByStatus(String status);
```

`Mono<Customer>` thể hiện truy vấn dự kiến không có hoặc có tối đa một entity. Nếu truy vấn thực tế phát nhiều hàng, publisher đơn có thể báo lỗi cardinality. Nếu email cần duy nhất, nên có unique constraint ở database để bảo đảm quy tắc đó.

Nếu mục tiêu chỉ là lấy một hàng trong nhiều hàng phù hợp, dùng `First`/`Top` và `OrderBy` rõ ràng. Nếu cần nhận toàn bộ kết quả, dùng `Flux<Customer>`.

## 8. Distinct và các modifier của subject

`Distinct` yêu cầu loại bỏ các hàng trùng theo semantics của câu truy vấn được sinh:

```java
Flux<Customer> findDistinctByStatus(String status);
```

Có thể kết hợp modifier giới hạn:

```java
Flux<Customer> findDistinctTop20ByStatusOrderByNameAsc(String status);
```

`Distinct` áp dụng ở tầng SQL query, không đơn giản là gọi `distinct()` trên một `Flux` sau khi dữ liệu đã được tải. Với projection hoặc entity có nhiều cột, semantics của SQL `DISTINCT` dựa trên tập cột được select; đừng mặc định nó tương đương với “unique theo một property” trong mọi tình huống.

## 9. Derived count, exists và delete

Ngoài truy vấn entity, Spring Data hỗ trợ các subject dành cho thao tác khác.

### Count

```java
Mono<Long> countByStatus(String status);
```

Phương thức trả về số hàng phù hợp. Vì thao tác là reactive, kết quả được phát qua `Mono<Long>` khi publisher được subscribe.

### Exists

```java
Mono<Boolean> existsByEmail(String email);
```

Phương thức phát `true` nếu có ít nhất một hàng phù hợp và `false` nếu không có. Đây là kiểm tra tồn tại; nó không thay thế constraint unique hoặc transaction khi cần bảo đảm không có hai request tạo cùng một dữ liệu.

### Delete

```java
Mono<Void> deleteByStatus(String status);
```

Phương thức xóa các hàng phù hợp. Nếu nghiệp vụ cần biết số hàng bị tác động, có thể dùng kiểu trả về số lượng được hỗ trợ bởi phiên bản Spring Data R2DBC đang dùng, chẳng hạn `Mono<Long>` khi query method và driver hỗ trợ. Với thao tác xóa hàng loạt, cần đặc biệt cẩn thận với điều kiện lọc: một method có predicate quá rộng có thể xóa nhiều dữ liệu.

Các method `delete…By` hoặc `remove…By` là derived delete query. Chúng không có nghĩa là Spring Data tải toàn bộ entity vào bộ nhớ rồi gọi delete từng object; cơ chế thực thi phụ thuộc module và kiểu query được tạo.

## 10. Kiểu tham số và thứ tự bind

Với derived query, tham số phương thức được gắn vào các điều kiện theo thứ tự parser nhận diện trong predicate. Số lượng và kiểu tham số phải phù hợp với toán tử.

Ví dụ:

```java
Flux<Customer> findByStatusAndAgeBetween(
        String status,
        int minAge,
        int maxAge
);
```

Phương thức cần ba tham số: một cho `status`, hai cho `Between`. Với `In`, tham số thường là collection hoặc array các giá trị:

```java
Flux<Customer> findByIdIn(Collection<Long> ids);
```

Không truyền một tham số cho `Between` hoặc một scalar trong khi query yêu cầu tập giá trị `In`. Nếu kiểu Java không tương thích với kiểu property hoặc driver không thể bind giá trị, query có thể lỗi khi thực thi.

Đối với derived query, tên biến tham số Java không quyết định cách ghép giá trị; thứ tự khai báo tham số phải tương ứng với điều kiện trong tên method. `@Param` thường hữu ích với named parameters trong `@Query`, còn derived query được tạo từ cấu trúc method name.

## 11. Quy tắc đặt tên và lỗi parser thường gặp

Tên method là một phần của hợp đồng repository. Một lỗi nhỏ trong tên property hoặc keyword có thể khiến Spring Data không tạo được query.

| Lỗi | Ví dụ không đúng | Cách xử lý |
| --- | --- | --- |
| Dùng tên cột thay tên property | `findByFirst_name(...)` | Dùng `findByFirstName(...)` và khai báo `@Column` nếu cần |
| Sai chính tả property | `findByFristName(...)` | Kiểm tra đúng tên Java property |
| Dùng keyword không hỗ trợ | `findByNameRegex(...)` trong module không hỗ trợ regex | Dùng `@Query` hoặc API phù hợp |
| Thiếu tham số | `findByAgeBetween(int age)` | Cung cấp đủ hai biên |
| Sai kiểu tham số | `findByAgeGreaterThan(String age)` | Dùng kiểu tương thích với property |
| Dùng `Mono` cho nhiều kết quả | `Mono<Customer> findByStatus(...)` khi status không duy nhất | Dùng `Flux<Customer>` hoặc `First`/`Top` có thứ tự |
| Method quá dài, nhiều `Or` | Một tên method chứa nhiều nhóm điều kiện | Tách method hoặc viết truy vấn tường minh |
| Dùng tên path mơ hồ | `findByAddressZipCode(...)` khi có nhiều property có thể khớp | Dùng `_` để chỉ rõ property path |
| Kỳ vọng tên method dùng raw SQL | `findByAgePlusOneGreaterThan(...)` | Tạo `@Query` cho biểu thức SQL tùy chỉnh |

Nên đặt tên method theo ngôn ngữ nghiệp vụ nhưng vẫn giữ cấu trúc parser dễ đọc. Nếu tên method trở thành một câu quá dài, đó thường là dấu hiệu truy vấn cần được biểu diễn bằng `@Query` hoặc một query builder.

## 12. Khi nào query derivation không còn phù hợp?

Derived query phù hợp với điều kiện lọc dựa trên property, các phép so sánh thường gặp, sắp xếp và giới hạn kết quả đơn giản. Nó không phải ngôn ngữ SQL tổng quát.

Hãy cân nhắc truy vấn tường minh khi cần:

- Join nhiều bảng hoặc join theo điều kiện phức tạp.
- Aggregate, group by, having hoặc biểu thức tính toán.
- Subquery, CTE, window function hoặc truy vấn đệ quy.
- Toán tử JSON/JSONB, array, full-text hoặc kiểu đặc thù riêng của database.
- Locking clause, hint hoặc cú pháp phụ thuộc dialect.
- Projection phức tạp hoặc alias được kiểm soát chính xác.
- Nhóm điều kiện có ngoặc phức tạp mà tên method khó thể hiện.

### Dùng `@Query`

Với SQL cụ thể, có thể khai báo query trên repository method:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    @Query("SELECT * FROM customer WHERE status = :status ORDER BY created_at DESC")
    Flux<Customer> findRecentByStatus(@Param("status") String status);
}
```

`@Query` cho phép viết SQL tường minh và dùng named parameter qua `@Param`. Tên bảng/cột trong SQL cần phù hợp schema thật; unlike derived query, Spring Data không tự suy ra mọi biểu thức SQL từ property path trong chuỗi SQL viết tay.

Với câu lệnh `UPDATE` hoặc `DELETE` tùy chỉnh bằng `@Query`, kiểm tra yêu cầu `@Modifying` và kiểu trả về theo phiên bản Spring Data R2DBC đang dùng. Các thao tác thay đổi dữ liệu phải được đánh dấu/khai báo đúng để Spring Data xử lý như modifying query.

### Dùng `DatabaseClient`

Nếu query có nhiều phép bind, SQL đặc thù hoặc cần kiểm soát kết quả ở mức thấp, `DatabaseClient` cho phép xây dựng câu lệnh rõ ràng:

```java
Flux<CustomerSummary> summaries = databaseClient.sql("""
            SELECT status, COUNT(*) AS total
            FROM customer
            WHERE created_at >= :fromTime
            GROUP BY status
            ORDER BY status
            """)
        .bind("fromTime", fromTime)
        .map((row, metadata) -> new CustomerSummary(
                row.get("status", String.class),
                row.get("total", Long.class)
        ))
        .all();
```

Đây là truy vấn aggregate mà tên method derived khó diễn đạt rõ. `DatabaseClient` cũng cho phép bind kiểu đặc thù do driver hỗ trợ và kiểm soát mapping từng hàng.

## 13. Kết hợp query derivation với reactive pipeline

Derived query trả publisher, nên có thể nối trực tiếp với các toán tử Reactor:

```java
public Flux<CustomerView> findActiveCustomerViews() {
    return customerRepository.findByStatusOrderByNameAsc("ACTIVE")
            .filter(Customer::isEnabled)
            .map(customer -> new CustomerView(
                    customer.getId(),
                    customer.getName()
            ));
}
```

Điều kiện `status` và thứ tự theo `name` được thực hiện ở query database. `filter(Customer::isEnabled)` và `map(...)` là các bước xử lý reactive sau khi hàng được phát ra. Nếu điều kiện `enabled` có thể biểu diễn bằng derived query, có thể đưa nó vào method để database lọc sớm:

```java
Flux<Customer> findByStatusAndEnabledTrueOrderByNameAsc(String status);
```

Đẩy điều kiện lọc và giới hạn phù hợp xuống database thường giảm lượng dữ liệu phải truyền và xử lý trong ứng dụng. Tuy nhiên, các bước tính toán phức tạp hoặc logic domain có thể vẫn cần nằm trong pipeline Java.

### Không gọi `subscribe()` trong repository consumer

Service nên trả publisher đã kết hợp đầy đủ:

```java
public Mono<CustomerView> findCustomerView(Long id) {
    return customerRepository.findById(id)
            .map(customer -> new CustomerView(
                    customer.getId(), customer.getName()
            ));
}
```

Controller WebFlux hoặc tầng ứng dụng phù hợp sẽ tiêu thụ publisher. Tự gọi `subscribe()` bên trong service có thể làm mất khả năng phối hợp lỗi, cancellation và transaction context.

## 14. Kiểm thử derived query methods

Derived query cần được kiểm thử với database/driver phù hợp để xác nhận parser tạo điều kiện đúng, mapping cột đúng và kiểu tham số được bind chính xác.

Ví dụ với `StepVerifier`:

```java
StepVerifier.create(repository.findByStatusAndAgeGreaterThan("ACTIVE", 18))
        .expectNextMatches(customer ->
                customer.getStatus().equals("ACTIVE") && customer.getAge() > 18
        )
        .verifyComplete();
```

Các nhóm test nên có:

- Điều kiện bằng, so sánh lớn hơn/nhỏ hơn và `Between`.
- Kết hợp `And` và `Or`, đặc biệt khi có nhiều nhóm.
- `IsNull` và `IsNotNull`.
- `Like`, `StartingWith`, `EndingWith`, `Containing` và `IgnoreCase`.
- `In` với danh sách có một, nhiều và không có phần tử.
- Property path lồng nhau và mapping `@Column`.
- `OrderBy`, `First`/`Top` và `Distinct`.
- `CountBy`, `ExistsBy`, `DeleteBy`.
- Kiểu trả về `Mono` khi không có hàng, có một hàng và nhiều hàng.
- Kiểm tra query method có lỗi property/keyword ngay khi repository được khởi tạo.

Ví dụ kiểm tra `Mono` khi không tìm thấy:

```java
StepVerifier.create(repository.findByEmail("missing@example.test"))
        .verifyComplete();
```

Với method trả `Mono<T>`, kiểm thử thêm trường hợp có nhiều hàng phù hợp để bảo đảm database constraint hoặc query limit đáp ứng cardinality mong đợi.

## 15. Ví dụ repository tổng hợp

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByStatus(String status);

    Flux<Customer> findByStatusAndAgeGreaterThanOrderByNameAsc(
            String status,
            int age
    );

    Flux<Customer> findByEmailIgnoreCase(String email);

    Flux<Customer> findByNameContaining(String part);

    Flux<Customer> findByStatusIn(Collection<String> statuses);

    Flux<Customer> findTop10ByStatusOrderByCreatedAtDesc(String status);

    Mono<Customer> findFirstByEmailOrderByCreatedAtDesc(String email);

    Mono<Long> countByStatus(String status);

    Mono<Boolean> existsByEmail(String email);

    Mono<Void> deleteByStatus(String status);
}
```

Các method trên thể hiện các dạng query thường gặp: lọc bằng, kết hợp điều kiện, so khớp chuỗi, tập giá trị, sắp xếp, giới hạn, đếm, kiểm tra tồn tại và xóa. Mỗi method có thể được thực thi trong reactive pipeline mà không cần tự viết SQL.

## 16. Ghi nhớ

- Derived query là query được Spring Data tạo từ tên method repository; phần `By` bắt đầu predicate.
- Subject như `find`, `count`, `exists`, `delete` hoặc `remove` xác định loại thao tác.
- Predicate tham chiếu Java property name; mapping `@Column` và naming strategy chuyển property thành cột SQL.
- `And`, `Or`, `Between`, `In`, `Like`, `StartingWith`, `EndingWith`, `Containing`, `IsNull`, `GreaterThan` và các keyword tương tự mô tả điều kiện thường dùng.
- `OrderBy` định nghĩa sắp xếp; `First`/`Top` giới hạn số kết quả; `Distinct` yêu cầu kết quả distinct theo SQL query.
- `Mono<T>` phù hợp với tối đa một kết quả; `Flux<T>` phù hợp với nhiều kết quả. Dùng `First`/`Top` khi cần chọn một hàng từ nhiều hàng phù hợp.
- `CountBy`, `ExistsBy` và `DeleteBy` hỗ trợ các thao tác không cần trả toàn bộ entity.
- Property path lồng nhau cần khớp metadata; dấu `_` có thể làm rõ ranh giới path khi tên bị mơ hồ.
- Query derivation không thay thế SQL tổng quát. Dùng `@Query`, `DatabaseClient` hoặc `R2dbcEntityTemplate` cho join, aggregate, subquery và tính năng riêng database.
- Derived query trả publisher reactive; nối nó vào pipeline và để framework/tầng gọi quản lý subscription.
- Kiểm thử với database và driver phù hợp để xác nhận parser, mapping, binding và cardinality thực tế.

Khi thiết kế repository, hãy bắt đầu bằng việc xác định điều kiện có thể biểu đạt trực tiếp từ property của entity. Nếu method name vẫn ngắn, rõ và khớp keyword được hỗ trợ, query derivation là lựa chọn gọn. Khi tên method bắt đầu che khuất logic SQL hoặc cần tính năng riêng của database, chuyển sang truy vấn tường minh sẽ giúp hành vi dễ đọc và kiểm soát hơn.
