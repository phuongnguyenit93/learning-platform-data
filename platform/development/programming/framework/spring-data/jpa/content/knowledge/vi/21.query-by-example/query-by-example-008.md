# Giới hạn về điều kiện nhóm, quan hệ và truy vấn phức tạp

## 1. Query by Example phù hợp với loại truy vấn nào?

Spring Data JPA Query by Example (QBE) tạo điều kiện truy vấn từ một object mẫu, gọi là **probe**. Các thuộc tính có giá trị trong probe được dùng để tìm những Entity có thuộc tính tương ứng phù hợp. QBE phù hợp với form tìm kiếm đơn giản, nơi người dùng nhập một số trường tùy chọn như tên, email, trạng thái hoặc thành phố.

QBE giảm nhu cầu tạo nhiều repository method cho các tổ hợp filter đơn giản. Tuy nhiên, probe không phải một ngôn ngữ biểu thức truy vấn đầy đủ. QBE có giới hạn rõ về cách kết hợp điều kiện, toán tử so sánh, collection và quan hệ phức tạp. Khi yêu cầu vượt quá những giới hạn đó, hãy chuyển sang Specification, Querydsl, JPQL hoặc custom repository.

## 2. Ba thành phần của QBE

QBE gồm ba thành phần:

- **Probe:** một object chứa các giá trị mẫu cần tìm. Thường là một Entity mới được tạo và chỉ gán những property muốn lọc.
- **ExampleMatcher:** quy định cách so khớp, chẳng hạn AND hay OR, cách xử lý chuỗi, ignore case, bỏ qua property hoặc xử lý null.
- **Example:** kết hợp probe và matcher để truyền cho repository.

Ví dụ repository:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
}
```

`JpaRepository` cung cấp các thao tác Query by Example thông qua `QueryByExampleExecutor`, chẳng hạn `findOne`, `findAll`, `count` và `exists` với một `Example`.

## 3. Tạo probe và ExampleMatcher

Giả sử Entity `Customer` có `id`, `firstName`, `lastName`, `email`, `status` và `createdAt`. Có thể tạo probe để tìm theo tên và trạng thái:

```java
Customer probe = new Customer();
probe.setFirstName("Lan");
probe.setStatus(CustomerStatus.ACTIVE);

ExampleMatcher matcher = ExampleMatcher.matching()
    .withIgnorePaths("id", "createdAt")
    .withMatcher(
        "firstName",
        ExampleMatcher.GenericPropertyMatchers.startsWith().ignoreCase()
    );

Example<Customer> example = Example.of(probe, matcher);
List<Customer> customers = customerRepository.findAll(example);
```

Đoạn code minh họa cần Entity và enum tương ứng. `matching()` mặc định kết hợp các property được đưa vào probe bằng AND. `firstName` được so khớp theo tiền tố và không phân biệt hoa thường; `status` được so khớp theo giá trị tương ứng.

`withIgnorePaths` loại các property khỏi điều kiện, hữu ích khi probe được tạo từ object có ID hoặc giá trị kỹ thuật không nên tham gia tìm kiếm. Tên trong matcher là property Java, không phải tên cột vật lý.

## 4. Null mặc định được bỏ qua

QBE mặc định bỏ qua các property null trong probe. Ví dụ:

```java
Customer probe = new Customer();
probe.setFirstName("Lan");
probe.setEmail(null);
```

Với matcher mặc định, điều kiện tìm kiếm chỉ dùng `firstName`; `email = null` không được tự động thêm vào query. Đây là hành vi thuận tiện cho form tìm kiếm có nhiều trường tùy chọn.

Nếu cần so khớp property null, có thể dùng `withIncludeNullValues()`. Khi đó các property null được đưa vào điều kiện theo semantics của store, thường tương ứng với kiểm tra IS NULL. Phải cân nhắc kỹ vì một probe có nhiều trường null có thể tạo điều kiện null ngoài ý muốn. Kết hợp `withIgnorePaths` để loại các property không nên tham gia.

## 5. Cẩn thận với kiểu primitive trong probe

Property primitive như `int`, `long` hoặc `boolean` luôn có giá trị mặc định trong Java: `0`, `0L` hoặc `false`. QBE không thể phân biệt giá trị mặc định đó với giá trị mà người dùng thực sự muốn tìm.

Ví dụ nếu `Customer` có `int age`, một probe mới có thể mang `age = 0` và QBE có thể đưa điều kiện age vào truy vấn. Nếu form không nhập tuổi, điều này có thể làm kết quả sai.

Đối với trường tìm kiếm tùy chọn, ưu tiên kiểu wrapper như `Integer`, `Long` và `Boolean` để biểu diễn null khi chưa có giá trị. Nếu Entity phải dùng primitive, có thể thêm property vào `withIgnorePaths("age")` khi filter không được cung cấp.

## 6. matchingAll và matchingAny

QBE hỗ trợ hai cách kết hợp điều kiện ở mức tổng thể:

| Matcher | Logic kết hợp |
| --- | --- |
| `ExampleMatcher.matching()` hoặc `matchingAll()` | Tất cả property được đưa vào probe phải khớp (AND) |
| `ExampleMatcher.matchingAny()` | Chỉ cần một property được đưa vào probe khớp (OR) |

Ví dụ tìm khách hàng có first name hoặc email chứa từ khóa:

```java
Customer probe = new Customer();
probe.setFirstName("an");
probe.setEmail("an");

ExampleMatcher matcher = ExampleMatcher.matchingAny()
    .withMatcher(
        "firstName",
        ExampleMatcher.GenericPropertyMatchers.contains().ignoreCase()
    )
    .withMatcher(
        "email",
        ExampleMatcher.GenericPropertyMatchers.contains().ignoreCase()
    );

Example<Customer> example = Example.of(probe, matcher);
List<Customer> matches = customerRepository.findAll(example);
```

Logic ở đây là `firstName CONTAINS 'an' OR email CONTAINS 'an'`. `matchingAny()` áp dụng OR trên toàn bộ các property được chọn; nó không cho phép định nghĩa các nhóm AND/OR lồng nhau tùy ý.

## 7. QBE không biểu diễn được điều kiện nhóm tùy ý

Giới hạn quan trọng nhất là QBE không hỗ trợ grouped/nested predicates. Ví dụ nghiệp vụ cần:

```text
status = ACTIVE
AND
(firstName = 'Lan' OR lastName = 'Tran')
```

Đây là biểu thức `A AND (B OR C)`. QBE chỉ cung cấp lựa chọn tổng thể matchingAll hoặc matchingAny; không có API probe/matcher để tạo nhóm ngoặc như trên.

Tương tự, biểu thức sau không thể được mô tả trực tiếp bằng một ExampleMatcher:

```text
firstName = 'Lan'
OR
(firstName = 'Linh' AND lastName = 'Tran')
```

Không cố mô phỏng biểu thức nhóm bằng cách tạo nhiều probe rồi ghép kết quả Java nếu tập dữ liệu lớn hoặc có phân trang. Cách đó dễ gây tải thừa, trùng ID, sai count và sai thứ tự. Hãy để database thực hiện logic nhóm bằng Specification, Querydsl hoặc JPQL.

## 8. Giới hạn về toán tử so sánh

QBE chủ yếu hỗ trợ so khớp bằng giá trị và một số kiểu matching chuỗi. Với String, `ExampleMatcher.StringMatcher` cung cấp các kiểu như:

| String matcher | Ý nghĩa |
| --- | --- |
| `EXACT` | Chuỗi phải khớp chính xác |
| `STARTING` | Bắt đầu bằng chuỗi probe |
| `ENDING` | Kết thúc bằng chuỗi probe |
| `CONTAINING` | Có chứa chuỗi probe |
| `REGEX` | Khớp biểu thức chính quy, phụ thuộc hỗ trợ của store |

QBE không cung cấp DSL tổng quát để biểu diễn các điều kiện số/ngày như:

- `age > 18` hoặc `price >= 100`.
- `createdAt BETWEEN from AND to`.
- `score < threshold`.
- `status IN (A, B, C)` như một toán tử collection tùy ý.
- So sánh hai property với nhau hoặc viết function tùy ý trên cột.

Không dùng giá trị probe như một cách ngầm hiểu `greater than` hoặc `between`. Với điều kiện khoảng, danh sách, so sánh hoặc function, dùng công cụ truy vấn phù hợp.

## 9. QBE với quan hệ đơn và property lồng nhau

QBE có thể đi theo property path lồng nhau, bao gồm các property của object nhúng hoặc quan hệ đơn khi mapping cho phép. Ví dụ `Customer` có `Address` nhúng:

```java
@Embeddable
public class Address {
    private String city;
    private String postalCode;
}
```

```java
@Entity
public class Customer {
    @Id
    private Long id;

    private String firstName;

    @Embedded
    private Address address;
}
```

Tạo probe chỉ có city:

```java
Customer probe = new Customer();
Address address = new Address();
address.setCity("Da Nang");
probe.setAddress(address);

ExampleMatcher matcher = ExampleMatcher.matching()
    .withIgnorePaths("id", "firstName");

Example<Customer> example = Example.of(probe, matcher);
List<Customer> result = customerRepository.findAll(example);
```

Matcher chỉ dùng `address.city` có giá trị; `address.postalCode` null được bỏ qua theo mặc định. Có thể bỏ qua riêng property lồng nhau bằng dot path như `address.postalCode` nếu cần.

Với quan hệ đơn như ManyToOne, có thể xây nested probe cho property của Entity liên quan, ví dụ `customer.accountManager.email`, nếu path đó là persistent property hợp lệ. Query provider sẽ tạo đường dẫn/join cần thiết. Hãy kiểm tra SQL và kiểm thử trường hợp association null, vì semantics của đường dẫn quan hệ và loại join có thể ảnh hưởng tập kết quả.

QBE không phải công cụ phù hợp để lọc qua collection association như `orders.items` hoặc ManyToMany. Các collection và map không được hỗ trợ như property matching trong QBE. Với điều kiện dựa trên phần tử collection, dùng EXISTS/JOIN trong Specification, Querydsl hoặc JPQL.

## 10. Quan hệ phức tạp và điều kiện trên child collection

Ví dụ cần tìm Customer có ít nhất một đơn hàng đang ở trạng thái PAID. Đây là điều kiện tồn tại trên collection `orders`. Probe không thể biểu diễn điều kiện trên một phần tử collection bằng một object lồng nhau thông thường.

Với Specification, có thể tạo join và predicate rõ ràng:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {
}
```

```java
Specification<Customer> hasPaidOrder = (root, query, cb) -> {
    Join<Customer, PurchaseOrder> order = root.join("orders");
    query.distinct(true);
    return cb.equal(order.get("status"), OrderStatus.PAID);
};

List<Customer> customers = customerRepository.findAll(hasPaidOrder);
```

Đây là đoạn minh họa; cần import `Join`, `Specification` và các domain type tương ứng. `distinct(true)` giúp loại Customer trùng khi một khách hàng có nhiều đơn hàng PAID. Nếu dùng `Page`, count query cần được kiểm tra để đếm Customer duy nhất. Khi chỉ cần kiểm tra có đơn hàng phù hợp, một subquery EXISTS có thể tránh nhân hàng root.

## 11. Dùng Specification cho điều kiện nhóm

Specification dựa trên JPA Criteria API cho phép xây predicate AND/OR tùy ý:

```java
Specification<Customer> spec = (root, query, cb) -> cb.and(
    cb.equal(root.get("status"), CustomerStatus.ACTIVE),
    cb.or(
        cb.equal(root.get("firstName"), "Lan"),
        cb.equal(root.get("lastName"), "Tran")
    )
);

List<Customer> result = customerRepository.findAll(spec);
```

Biểu thức này thể hiện đúng `status = ACTIVE AND (firstName = Lan OR lastName = Tran)`. Có thể kết hợp các Specification nhỏ để tái sử dụng:

```java
Specification<Customer> active =
    (root, query, cb) -> cb.equal(root.get("status"), CustomerStatus.ACTIVE);

Specification<Customer> nameMatches =
    (root, query, cb) -> cb.or(
        cb.equal(root.get("firstName"), "Lan"),
        cb.equal(root.get("lastName"), "Tran")
    );

Specification<Customer> combined = active.and(nameMatches);
```

Specification phù hợp khi điều kiện động có thể kết hợp nhiều nhóm logic, filter tùy chọn và join. Với query có nhiều aggregate, projection hoặc SQL đặc thù, cân nhắc Querydsl, JPQL hoặc custom repository.

## 12. Dùng @Query khi logic tĩnh và rõ

Nếu điều kiện nhóm ổn định, JPQL có thể thể hiện trực tiếp:

```java
@Query("""
    select c
    from Customer c
    where c.status = :status
      and (c.firstName = :firstName or c.lastName = :lastName)
    """)
List<Customer> searchByStatusAndEitherName(
    @Param("status") CustomerStatus status,
    @Param("firstName") String firstName,
    @Param("lastName") String lastName
);
```

JPQL dùng entity name và property Java. Nếu cần lọc collection, có thể dùng JOIN hoặc EXISTS; nếu dùng JOIN to-many và trả root, cân nhắc `distinct` để tránh trùng Entity. Với Page, khai báo count query phù hợp khi query có join, distinct hoặc group.

## 13. Khi nào nên chọn QBE, Specification, Querydsl hay @Query?

| Yêu cầu | Công cụ phù hợp |
| --- | --- |
| Form tìm kiếm với nhiều trường tùy chọn, chủ yếu exact/string matching | Query by Example |
| AND/OR lồng nhau, nhóm điều kiện tùy ý | Specification hoặc Querydsl |
| So sánh `>`, `<`, BETWEEN, IN hoặc điều kiện động nhiều loại | Specification hoặc Querydsl |
| Lọc qua collection/quan hệ to-many | EXISTS/JOIN bằng Specification, Querydsl hoặc JPQL |
| Query tĩnh có logic rõ và ít thay đổi | `@Query` JPQL |
| CTE, window function hoặc tính năng riêng database | Native SQL/custom repository |

Không cần thay QBE nếu form chỉ có các trường tùy chọn đơn giản và AND/OR tổng thể đã đủ. Chuyển công cụ khi giới hạn của QBE khiến logic phải vòng vo hoặc kết quả khó kiểm soát.

## 14. Hiệu năng và phân trang với QBE

QBE vẫn tạo query database; nó không lọc toàn bộ dữ liệu trong Java. Hiệu năng phụ thuộc điều kiện được tạo, index, dữ liệu, join và execution plan.

- Chỉ đưa vào probe các property thực sự cần lọc.
- Dùng `withIgnorePaths` để loại ID, timestamp hoặc giá trị primitive mặc định không thuộc điều kiện tìm kiếm.
- Cẩn thận `matchingAny()` vì OR trên nhiều cột có thể khó tận dụng index hơn AND tùy database và dữ liệu.
- Với property lồng nhau, xem SQL có join ngoài dự kiến không.
- Với `Page<T>`, Spring Data có thể chạy thêm count query; kiểm tra tổng số và query count.
- Không lấy tất cả kết quả rồi lọc bằng stream Java khi database có thể áp dụng predicate.

QBE có thể kết hợp với `Sort` hoặc `Pageable`:

```java
Page<Customer> page = customerRepository.findAll(
    example,
    PageRequest.of(0, 20, Sort.by("lastName").ascending())
);
```

Sort dùng property Java hợp lệ của domain, không dùng tên cột vật lý. Nếu query có association hoặc điều kiện phức tạp, hãy kiểm tra SQL và count query trên database mục tiêu.

## 15. Lỗi thường gặp và cách chẩn đoán

**Kết quả quá ít vì một trường mặc định bằng 0 hoặc false.** Kiểm tra primitive trong probe; dùng wrapper nullable hoặc thêm property vào `withIgnorePaths`.

**Muốn tìm property null nhưng kết quả không có.** Null mặc định bị bỏ qua. Dùng `withIncludeNullValues()` khi cần match null và bỏ qua các property không liên quan.

**matchingAny trả quá nhiều kết quả.** `matchingAny()` OR tất cả property được đưa vào probe. Nếu cần nhóm logic, chuyển sang Specification/Querydsl.

**Không thể biểu diễn `A AND (B OR C)`.** QBE chỉ có matchingAll/matchingAny toàn cục, không có nested predicate groups.

**Muốn lọc age lớn hơn hoặc ngày trong khoảng.** QBE không có toán tử so sánh tổng quát; dùng Specification, Querydsl hoặc JPQL.

**Không lọc được collection hoặc child.** QBE không hỗ trợ collection/map matching. Dùng EXISTS/JOIN trong query phù hợp.

**Nested association làm query chậm hoặc bỏ sót kết quả.** Kiểm tra property path, association null, SQL join và index; cân nhắc viết query tường minh.

**Count hoặc Page có kết quả trùng.** Join to-many có thể nhân root; dùng distinct/EXISTS và count query đếm đúng root.

## 16. Checklist trước khi chọn Query by Example

- Probe có thể biểu diễn các điều kiện chủ yếu bằng giá trị exact hoặc string matching không?
- Logic tổng thể chỉ cần AND hoặc OR hay cần nhóm ngoặc tùy ý?
- Có cần toán tử `>`, `<`, BETWEEN, IN, function hoặc subquery không?
- Có phải lọc qua collection/map hoặc nhiều quan hệ to-many không?
- Các primitive trong probe có giá trị mặc định gây filter ngoài ý muốn không?
- Null cần được bỏ qua hay phải match IS NULL?
- Property lồng nhau có hợp lệ và join sinh ra có phù hợp không?
- Nếu phân trang, count query và distinct root đã đúng chưa?
- Nếu vượt giới hạn QBE, Specification, Querydsl hoặc @Query có thể diễn đạt rõ hơn không?

Query by Example là lựa chọn gọn cho tìm kiếm theo probe với các điều kiện đơn giản. Nó không thay thế ngôn ngữ truy vấn tổng quát: không có nhóm AND/OR lồng nhau, toán tử so sánh tùy ý hoặc lọc collection/map. Nhận biết các giới hạn này sớm giúp chọn đúng công cụ và giữ truy vấn dễ đọc, đúng kết quả, dễ tối ưu.