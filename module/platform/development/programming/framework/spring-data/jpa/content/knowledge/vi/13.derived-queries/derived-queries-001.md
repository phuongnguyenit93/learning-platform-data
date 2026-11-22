# Cấu trúc tên phương thức: chủ ngữ, điều kiện và thứ tự

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân tích một derived query method của Spring Data JPA thành phần chủ ngữ, phần điều kiện và phần sắp xếp.
- Dùng đúng các tiền tố `find`, `exists`, `count`, `delete` và `remove`.
- Kết hợp thuộc tính bằng `And`, `Or` và các toán tử như `Between`, `In`, `Like`, `IsNull`.
- Biểu diễn đường dẫn thuộc tính lồng nhau và xử lý tên thuộc tính mơ hồ.
- Chọn kiểu trả về phù hợp như `Optional`, `List`, `Page` và `Slice`.
- Dùng `Sort` hoặc `Pageable` cho sắp xếp động.
- Nhận biết khi nào tên phương thức trở nên quá phức tạp và nên chuyển sang `@Query` hoặc custom repository.

## 1. Derived query method là gì?

Spring Data JPA có thể tạo truy vấn từ tên phương thức khai báo trong repository. Cách này thường được gọi là query derivation hoặc derived query.

Ví dụ:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    List<Customer> findByStatusAndCreatedAtAfter(
        CustomerStatus status,
        Instant time
    );
}
~~~

Spring Data phân tích tên phương thức, tìm các thuộc tính của entity và tạo truy vấn tương ứng. Phương thức thứ nhất tìm Customer theo email. Phương thức thứ hai tìm các Customer có status phù hợp và thời điểm tạo sau một mốc thời gian.

Derived query hữu ích khi truy vấn có cấu trúc đơn giản, tên mô tả đúng ý nghĩa nghiệp vụ và không cần viết JPQL/SQL. Nó không phải là một cơ chế hiểu ngôn ngữ tự nhiên; tên phương thức phải tuân theo grammar của Spring Data.

## 2. Cấu trúc tổng quát: chủ ngữ, By, điều kiện và thứ tự

Một derived query thường có cấu trúc:

~~~text
[Subject][By][Predicate][OrderBy][SortDirection]
~~~

Ví dụ:

~~~java
List<Customer> findDistinctTop10ByStatusAndCreatedAtAfterOrderByCreatedAtDesc(
    CustomerStatus status,
    Instant createdAfter
);
~~~

Có thể tách thành:

| Phần | Giá trị | Ý nghĩa |
|---|---|---|
| Subject | `findDistinctTop10` | Trả về kết quả tìm kiếm, loại trùng và giới hạn tối đa 10 |
| Delimiter | `By` | Bắt đầu phần điều kiện |
| Predicate | `StatusAndCreatedAtAfter` | Status bằng giá trị truyền vào và createdAt sau mốc thời gian |
| Ordering | `OrderByCreatedAtDesc` | Sắp xếp createdAt giảm dần |

Thứ tự tham số trong chữ ký phương thức tương ứng với thứ tự các điều kiện có tham số trong phần predicate. Các toán tử không cần tham số như `IsNull`, `True` hoặc `False` không tạo thêm tham số đầu vào.

## 3. Phần chủ ngữ (Subject)

Phần chủ ngữ nằm trước `By`. Nó cho Spring Data biết loại thao tác hoặc kiểu kết quả mong muốn.

### Các tiền tố phổ biến

| Tiền tố | Mục đích | Ví dụ |
|---|---|---|
| `findBy` | Tìm entity | `findByEmail(...)` |
| `readBy` | Đọc entity | `readByStatus(...)` |
| `getBy` | Lấy entity | `getById` có thể trùng reserved method; ưu tiên tên rõ nghĩa |
| `queryBy` | Truy vấn entity | `queryByStatus(...)` |
| `searchBy` | Tìm kiếm entity | `searchByName(...)` |
| `streamBy` | Trả kết quả dạng Stream nếu kiểu trả về hỗ trợ | `streamByStatus(...)` |
| `existsBy` | Kiểm tra có bản ghi hay không | `existsByEmail(...)` |
| `countBy` | Đếm bản ghi | `countByStatus(...)` |
| `deleteBy` | Xóa theo điều kiện | `deleteByStatus(...)` |
| `removeBy` | Xóa theo điều kiện | `removeByStatus(...)` |

Trong các phương thức tìm kiếm, phần Subject có thể chứa thêm từ khóa:

- `Distinct`: yêu cầu kết quả distinct.
- `First` hoặc `Top`: giới hạn số kết quả.
- Một số dạng có thể kết hợp, ví dụ `findDistinctTop5ByStatus(...)`.

Ví dụ:

~~~java
List<Customer> findTop5ByStatusOrderByCreatedAtDesc(
    CustomerStatus status
);
~~~

Phương thức này lấy tối đa 5 Customer có status tương ứng và sắp xếp theo createdAt giảm dần.

`First` và `Top` có thể không ghi số lượng; khi đó giới hạn mặc định là một kết quả. Có thể dùng kiểu trả về entity hoặc `Optional` nếu nghiệp vụ bảo đảm không có nhiều hơn một kết quả.

### Distinct cần hiểu đúng

`findDistinctByLastname(...)` tạo truy vấn distinct cho kết quả entity. Nhưng `countDistinctByLastname(...)` thường đếm distinct entity identifier, không nhất thiết đếm số họ tên khác nhau. Vì mỗi entity có ID riêng, kết quả có thể giống `countByLastname(...)`.

Nếu cần đếm số giá trị khác nhau của một thuộc tính, hãy viết `@Query` rõ ràng, ví dụ `select count(distinct c.lastname) ...`, thay vì suy luận rằng `countDistinctByLastname` có nghĩa đếm distinct lastname.

## 4. Phần điều kiện (Predicate)

Phần Predicate nằm sau `By`. Nó mô tả thuộc tính và toán tử so sánh.

### Toán tử so sánh phổ biến

| Từ khóa | Ý nghĩa | Ví dụ |
|---|---|---|
| Không ghi toán tử, `Is`, `Equals` | Bằng | `findByStatus(...)` |
| `IsNot`, `Not` | Khác | `findByStatusNot(...)` |
| `LessThan`, `Before` | Nhỏ hơn / trước | `findByAgeLessThan(...)` |
| `LessThanEqual` | Nhỏ hơn hoặc bằng | `findByAgeLessThanEqual(...)` |
| `GreaterThan`, `After` | Lớn hơn / sau | `findByCreatedAtAfter(...)` |
| `GreaterThanEqual` | Lớn hơn hoặc bằng | `findByAgeGreaterThanEqual(...)` |
| `Between` | Nằm trong khoảng | `findByCreatedAtBetween(from, to)` |
| `IsNull`, `Null` | Giá trị null | `findByDeletedAtIsNull()` |
| `IsNotNull`, `NotNull` | Khác null | `findByDeletedAtIsNotNull()` |
| `In` | Nằm trong tập giá trị | `findByStatusIn(statuses)` |
| `NotIn` | Không nằm trong tập giá trị | `findByStatusNotIn(statuses)` |
| `True`, `False` | Boolean đúng/sai | `findByActiveTrue()` |
| `Like` | So khớp mẫu LIKE | `findByNameLike(pattern)` |
| `NotLike` | Không khớp mẫu LIKE | `findByNameNotLike(pattern)` |

Ví dụ:

~~~java
List<Customer> findByAgeBetween(int minAge, int maxAge);

List<Customer> findByStatusIn(Collection<CustomerStatus> statuses);

List<Customer> findByDeletedAtIsNull();

List<Customer> findByActiveTrue();
~~~

Với `Between`, hai tham số tương ứng với cận dưới và cận trên. Với `In` và `NotIn`, tham số thường là Collection hoặc array phù hợp với kiểu thuộc tính.

### Null trong tham số

Nếu dùng phương thức bằng thông thường và truyền null, Spring Data thường chuyển phép so sánh đó thành điều kiện IS NULL. Với `Not`/not equal và null, hành vi tương ứng có thể là IS NOT NULL. Hãy dùng tên `IsNull` hoặc `IsNotNull` khi ý định rõ ràng là kiểm tra null; tránh dựa vào việc truyền null ngầm để biểu đạt nhiều ý nghĩa.

## 5. Ghép điều kiện bằng And và Or

`And` và `Or` kết hợp các predicate:

~~~java
List<Customer> findByStatusAndActiveTrue(
    CustomerStatus status
);

List<Customer> findByFirstNameOrLastName(
    String firstName,
    String lastName
);
~~~

Có thể kết hợp cả hai:

~~~java
List<Customer> findByStatusAndActiveTrueOrPriority(
    CustomerStatus status,
    boolean priority
);
~~~

Cách đặt tên này tương ứng với nhóm điều kiện:

~~~text
(status = ? AND active = true) OR priority = ?
~~~

Spring Data phân tích các phần `Or` thành các nhánh, trong mỗi nhánh có thể có nhiều điều kiện `And`. SQL cũng có quy tắc ưu tiên AND cao hơn OR, nhưng không nên dùng tên dài để mô tả logic nghiệp vụ phức tạp hoặc dễ gây hiểu nhầm.

Derived method không cung cấp cú pháp ngoặc tùy ý như trong biểu thức Java. Nếu logic có nhiều nhóm OR/AND, điều kiện lồng nhau, subquery hoặc cần kiểm soát rõ precedence, hãy dùng `@Query` hoặc Specification/Criteria API.

## 6. LIKE, Containing và tìm kiếm chuỗi

Spring Data hỗ trợ nhiều từ khóa cho thao tác LIKE:

| Từ khóa | Ý nghĩa |
|---|---|
| `Like` | Dùng pattern LIKE do tham số cung cấp |
| `StartingWith` | Chuỗi bắt đầu bằng giá trị |
| `EndingWith` | Chuỗi kết thúc bằng giá trị |
| `Containing` | Chuỗi chứa giá trị |
| `NotLike` | Không khớp pattern |
| `NotContaining` | Không chứa giá trị |

Ví dụ:

~~~java
List<Customer> findByNameStartingWith(String prefix);

List<Customer> findByNameEndingWith(String suffix);

List<Customer> findByNameContaining(String fragment);

List<Customer> findByNameContainingIgnoreCase(String fragment);
~~~

Với `Like`, tham số thường phải chứa ký tự wildcard như `%` hoặc `_` theo cú pháp SQL. Với `StartingWith`, `EndingWith` và `Containing`, Spring Data tự bổ sung wildcard phù hợp.

Spring Data có cơ chế escape một số ký tự wildcard trong các derived query dạng chứa/bắt đầu/kết thúc để chúng được hiểu như ký tự dữ liệu thay vì pattern. Nếu cần kiểm soát chính xác pattern, escape character hoặc tìm kiếm full-text, hãy dùng `@Query` hay tính năng chuyên dụng của database.

### IgnoreCase

Có thể thêm `IgnoreCase` sau thuộc tính chuỗi:

~~~java
Optional<Customer> findByEmailIgnoreCase(String email);

List<Customer> findByFirstNameAndLastNameAllIgnoreCase(
    String firstName,
    String lastName
);
~~~

`IgnoreCase` áp dụng cho một thuộc tính String; `AllIgnoreCase` áp dụng cho các thuộc tính String phù hợp trong predicate. Nó không có ý nghĩa với kiểu số, ngày giờ hoặc enum.

Cách so sánh không phân biệt hoa thường phụ thuộc database, collation và cách provider tạo SQL. Với dữ liệu định danh như email, nên chuẩn hóa giá trị khi ghi và xác định quy tắc duy nhất rõ ràng, thay vì chỉ dựa vào IgnoreCase lúc truy vấn.

## 7. Đường dẫn thuộc tính lồng nhau

Derived query có thể đi qua association hoặc embedded property.

Giả sử Customer có thuộc tính `address`, và Address có `zipCode`:

~~~java
List<Customer> findByAddressZipCode(String zipCode);
~~~

Spring Data phân tích tên để tìm property path `address.zipCode`.

Tuy nhiên, tên camel case có thể mơ hồ nếu entity đồng thời có property `addressZip` và property `address.zipCode`. Parser có thể chọn một đường dẫn khác với ý định.

Dùng dấu gạch dưới để chỉ rõ ranh giới:

~~~java
List<Customer> findByAddress_ZipCode(String zipCode);
~~~

Dấu gạch dưới là ký hiệu phân tách property path trong tên derived method. Nếu model có property bắt đầu bằng dấu gạch dưới hoặc tên bất thường, cần tuân theo quy tắc escaping/property path của Spring Data và cân nhắc đổi tên thuộc tính để tránh mơ hồ.

Ví dụ với association:

~~~java
List<Order> findByCustomer_EmailIgnoreCase(String email);
~~~

Đường dẫn này có nghĩa là lọc Order theo email của Customer liên kết.

## 8. Thứ tự sắp xếp bằng OrderBy

`OrderBy` đặt ở cuối tên phương thức, sau predicate:

~~~java
List<Customer> findByStatusOrderByCreatedAtDesc(
    CustomerStatus status
);
~~~

Có thể sắp xếp nhiều thuộc tính:

~~~java
List<Customer> findByStatusOrderByCreatedAtDescIdAsc(
    CustomerStatus status
);
~~~

- `Asc`: tăng dần.
- `Desc`: giảm dần.
- Có thể kết hợp nhiều thuộc tính liên tiếp.
- Tên thuộc tính sau OrderBy vẫn phải tồn tại trong entity/property path.

Nếu không ghi Asc hoặc Desc, hướng mặc định là tăng dần. Khi cần thứ tự ổn định cho phân trang, nên thêm một khóa phụ duy nhất như ID để tránh bản ghi cùng timestamp đổi vị trí giữa các trang.

## 9. Sắp xếp động và phân trang

Tên phương thức phù hợp với thứ tự cố định. Nếu thứ tự do người gọi quyết định, dùng `Sort` hoặc `Pageable`.

~~~java
Page<Customer> findByStatus(
    CustomerStatus status,
    Pageable pageable
);

List<Customer> findByActiveTrue(Sort sort);
~~~

Ví dụ gọi:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
    )
);

Page<Customer> page =
        customerRepository.findByStatus(CustomerStatus.ACTIVE, pageable);
~~~

`Page` thường cần thêm count query để biết tổng số phần tử/trang. `Slice` có thể hữu ích nếu chỉ cần biết còn dữ liệu ở trang tiếp theo mà không cần tổng số:

~~~java
Slice<Customer> findByStatus(
    CustomerStatus status,
    Pageable pageable
);
~~~

Khi kết hợp static `OrderBy` với `Sort` hoặc `Pageable`, cần xác định rõ thứ tự cuối cùng theo API Spring Data đang dùng. Tránh vừa đặt một thứ tự cố định trong tên method vừa truyền sort khác nếu không cần thiết.

## 10. Kiểu trả về và ý nghĩa

| Kiểu trả về | Ý nghĩa |
|---|---|
| Entity | Mong đợi tối đa một kết quả; nếu có nhiều kết quả, có thể phát sinh lỗi không đúng cardinality |
| `Optional<Entity>` | Không có kết quả thì Optional rỗng; nhiều hơn một kết quả vẫn là lỗi |
| `List<Entity>` | Danh sách kết quả, có thể rỗng |
| `Set<Entity>` | Tập kết quả; cần equals/hashCode phù hợp |
| `Page<Entity>` | Dữ liệu trang và thông tin tổng số, thường có count query |
| `Slice<Entity>` | Dữ liệu trang và thông tin còn trang tiếp theo, không cần tổng số |
| `long` / `Long` | Thường dùng cho count query |
| `boolean` / `Boolean` | Thường dùng cho exists query |
| `void` hoặc số lượng phù hợp | Có thể dùng cho derived delete tùy method và API |

Nếu một truy vấn có thể trả về nhiều kết quả, không khai báo `Optional<Entity>` chỉ để hy vọng lấy bản ghi đầu tiên. Dùng `First`/`Top` và thứ tự rõ ràng nếu thật sự muốn giới hạn.

## 11. Reserved methods và tên thuộc tính

Một số tên phương thức kế thừa từ `CrudRepository`/`JpaRepository` là reserved methods, ví dụ:

- `findById(ID id)`
- `existsById(ID id)`
- `deleteById(ID id)`

Các method này luôn thao tác trên identifier được khai báo bằng `@Id`, không nhất thiết là property có tên `id`.

Nếu entity có primary key tên `pk` nhưng có một field nghiệp vụ tên `id`, `findById(...)` vẫn là method reserved để tìm theo primary key. Để truy vấn property nghiệp vụ, dùng một tên method khác rõ ràng, ví dụ:

~~~java
Optional<Customer> findCustomerById(String externalId);
~~~

Phần mô tả `Customer` nằm trước `By` để tránh trùng reserved signature và parser sẽ tìm property `id` theo predicate.

Khi tên method gây nhầm lẫn, hãy đặt tên mô tả hơn hoặc dùng `@Query` để làm rõ ý định.

## 12. Derived delete, exists và count

Ngoài truy vấn lấy entity, có thể dùng subject để tạo thao tác khác:

~~~java
boolean existsByEmailIgnoreCase(String email);

long countByStatus(CustomerStatus status);

long deleteByStatus(CustomerStatus status);
~~~

`existsBy` kiểm tra sự tồn tại, `countBy` đếm kết quả và `deleteBy`/ `removeBy` xóa các entity thỏa điều kiện.

Derived delete có thể tải các entity phù hợp rồi xóa từng entity để áp dụng lifecycle callback và cascade theo semantics của repository. Điều này khác với bulk delete bằng `@Modifying @Query`, vốn có thể thực hiện một lệnh DELETE trực tiếp và không đồng bộ các entity đang nằm trong persistence context.

Các query method khai báo trực tiếp không mặc định luôn có transaction giống các CRUD method kế thừa. Hãy đặt `@Transactional` ở service hoặc method phù hợp khi thao tác cần transaction:

~~~java
@Service
public class CustomerCleanupService {

    private final CustomerRepository repository;

    public CustomerCleanupService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public long removeInactive(CustomerStatus status) {
        return repository.deleteByStatus(status);
    }
}
~~~

Với bulk delete, cân nhắc clear persistence context hoặc không giữ các entity bị ảnh hưởng trong context sau thao tác để tránh trạng thái managed bị stale.

## 13. Ví dụ repository tổng hợp

Giả sử Customer có các thuộc tính `email`, `firstName`, `lastName`, `status`, `active`, `createdAt` và embedded `address.zipCode`.

~~~java
package com.example.customer;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.domain.Sort;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmailIgnoreCase(String email);

    List<Customer> findByStatusAndActiveTrue(
        CustomerStatus status
    );

    List<Customer> findByCreatedAtBetween(
        Instant from,
        Instant to
    );

    List<Customer> findByAddress_ZipCode(String zipCode);

    List<Customer> findTop5ByStatusOrderByCreatedAtDesc(
        CustomerStatus status
    );

    Page<Customer> findByLastNameContainingIgnoreCase(
        String fragment,
        Pageable pageable
    );

    List<Customer> findByStatus(CustomerStatus status, Sort sort);

    boolean existsByEmailIgnoreCase(String email);

    long countByStatus(CustomerStatus status);
}
~~~

Tên method cần khớp chính xác với property của entity. Nếu đổi `createdAt` thành `createdOn`, các method liên quan cũng phải thay đổi. Spring Data thường phân tích repository method khi khởi tạo application context; tên property sai có thể làm ứng dụng lỗi ngay lúc startup.

## 14. Khi nào nên chuyển sang @Query?

Derived query giúp giảm boilerplate, nhưng tên method có thể trở nên dài và khó đọc.

Ví dụ:

~~~java
List<Customer> findByStatusAndActiveTrueOrPriorityAndCreatedAtAfterOrderByLastNameAscFirstNameAsc(
    CustomerStatus status,
    boolean priority,
    Instant createdAfter
);
~~~

Khi truy vấn có nhiều nhóm điều kiện, subquery, aggregation, projection phức tạp hoặc cần kiểm soát join/fetch, hãy dùng `@Query`:

~~~java
@Query("""
    select c
    from Customer c
    where c.status = :status
      and (
          c.active = true
          or c.priority = true
      )
      and c.createdAt >= :createdAfter
    order by c.lastName asc, c.firstName asc
    """)
List<Customer> findCandidates(
    @Param("status") CustomerStatus status,
    @Param("createdAfter") Instant createdAfter
);
~~~

JPQL dùng tên entity và thuộc tính Java, không dùng tên bảng/cột SQL trực tiếp. Nếu truy vấn đặc thù database, có thể dùng native query, nhưng cần đánh giá tính di động và khả năng bảo trì.

## 15. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Application context không khởi động | Tên property trong method không tồn tại | Kiểm tra tên field và đường dẫn property |
| Truy vấn trả về nhiều kết quả gây lỗi | Dùng entity/Optional cho truy vấn không duy nhất | Dùng List/Page hoặc Top/First với thứ tự rõ |
| Tìm kiếm chuỗi không đúng | Dùng Like nhưng thiếu wildcard hoặc nhầm Containing | Chọn đúng operator và hiểu pattern |
| Property path trỏ nhầm | Tên camel case mơ hồ | Dùng underscore để chỉ ranh giới property |
| Kết quả phân trang đổi thứ tự | Sắp xếp không ổn định khi nhiều bản ghi cùng giá trị | Thêm khóa phụ duy nhất vào Sort |
| countDistinctBy không đếm distinct field như mong muốn | Distinct thường áp dụng trên entity/ID | Dùng @Query với count(distinct property) |
| deleteBy gây tải nhiều entity | Derived delete thực hiện lifecycle từng entity | Dùng bulk query nếu semantics cho phép và xử lý persistence context |
| Query method xóa nhưng không có transaction | Method khai báo trực tiếp chưa có transaction phù hợp | Gọi trong service @Transactional |
| Tên method quá dài và khó hiểu | Logic nhiều AND/OR hoặc nhiều nhóm | Dùng @Query, Specification hoặc custom repository |

## Checklist trước khi merge

- [ ] Subject dùng đúng tiền tố find/read/get/query/exists/count/delete/remove.
- [ ] By phân tách đúng phần subject và predicate.
- [ ] Predicate property name khớp entity và tham số đúng thứ tự.
- [ ] And/Or có logic rõ ràng; truy vấn phức tạp chuyển sang @Query.
- [ ] OrderBy có hướng Asc/Desc rõ ràng và sort phân trang ổn định.
- [ ] Return type phù hợp cardinality và nhu cầu phân trang.
- [ ] Property path lồng nhau dùng underscore khi cần tránh mơ hồ.
- [ ] Reserved method như findById được hiểu là identifier của entity.
- [ ] Delete/count/exists có transaction và semantics phù hợp.
- [ ] Repository method được kiểm tra bằng integration test.

## Kết luận

Derived query method của Spring Data JPA được phân tích từ phần subject, delimiter `By`, predicate và phần `OrderBy`. Subject xác định thao tác và giới hạn; predicate mô tả thuộc tính cùng toán tử; thứ tự có thể cố định trong tên hoặc truyền qua Sort/Pageable. Tên method cần phản ánh đúng property path và cardinality của truy vấn. Khi logic AND/OR phức tạp, cần projection đặc biệt hoặc kiểm soát join, hãy chuyển sang `@Query` hay custom repository để giữ truy vấn rõ ràng và dễ kiểm thử.
