# Khi nào dùng Query by Example trong Spring Data Neo4j?

Khi xây dựng API tìm kiếm, người dùng thường chỉ nhập một vài trường: tên, trạng thái, mã hoặc loại đối tượng. Nếu viết một phương thức repository riêng cho mọi tổ hợp bộ lọc, số lượng phương thức sẽ tăng nhanh. **Query by Example (QBE)** giải quyết trường hợp này bằng cách tạo truy vấn từ một đối tượng mẫu (probe) và quy tắc so khớp (matcher).

Trong Spring Data Neo4j, QBE phù hợp với truy vấn tìm kiếm động dựa trên các thuộc tính đơn giản của entity. Bạn tạo một entity mẫu, điền những trường cần tìm, cấu hình `ExampleMatcher`, rồi truyền `Example` cho repository. Cách này giảm nhu cầu viết Cypher cho các bộ lọc cơ bản, nhưng không thay thế được truy vấn có điều kiện phức tạp, phép so sánh theo khoảng hoặc traversal qua nhiều relationship.

## 1. Query by Example gồm những thành phần nào?

QBE có bốn thành phần chính:

| Thành phần | Vai trò |
|---|---|
| **Probe** | Đối tượng domain mẫu, chứa các giá trị cần tìm. |
| **ExampleMatcher** | Quy định cách so khớp: tất cả hay bất kỳ điều kiện nào, cách so khớp chuỗi, phân biệt hoa thường, bỏ qua property và xử lý null. |
| **Example** | Kết hợp probe và matcher thành một điều kiện truy vấn bất biến. |
| **FetchableFluentQuery** | API cho phép tùy chỉnh kết quả như sort, limit, projection, page, first hoặc all. |

Ví dụ, probe `Person` có `status = "ACTIVE"` và `city = "Hanoi"` có thể được dùng để tìm người thỏa các điều kiện đó. Các trường không được gán giá trị thường không tham gia điều kiện theo mặc định.

## 2. Repository hỗ trợ Query by Example

Với Spring Data Neo4j, repository kế thừa `Neo4jRepository` có các thao tác QBE thông qua cơ chế `QueryByExampleExecutor`.

Ví dụ entity:

```java
@Node("Person")
public class Person {

    @Id
    private String personId;

    private String firstName;
    private String lastName;
    private String status;
    private Integer age;
    private Boolean active;

    // Constructors, getters and setters
}
```

Repository:

```java
public interface PersonRepository extends Neo4jRepository<Person, String> {
}
```

Bạn có thể sử dụng các phương thức như:

```java
Iterable<Person> people = personRepository.findAll(example);
Optional<Person> one = personRepository.findOne(example);
long count = personRepository.count(example);
boolean exists = personRepository.exists(example);
```

`findAll` trả về các entity phù hợp; `count` đếm số kết quả và `exists` kiểm tra có kết quả hay không. Chỉ dùng `findOne` khi probe được kỳ vọng khớp tối đa một entity. Nếu có nhiều kết quả, thao tác tìm một kết quả sẽ báo lỗi kích thước kết quả không hợp lệ.

## 3. Tạo probe và Example đơn giản

Probe là một instance của entity. Chỉ cần gán những property muốn dùng làm điều kiện:

```java
Person probe = new Person();
probe.setFirstName("An");
probe.setStatus("ACTIVE");

Example<Person> example = Example.of(probe);

List<Person> people = personRepository.findAll(example);
```

Với matcher mặc định, các property có giá trị được so khớp chính xác và được kết hợp theo kiểu tất cả điều kiện đều đúng (`matchingAll`). Trong ví dụ, kết quả cần có `firstName = "An"` và `status = "ACTIVE"`.

Các property có giá trị `null` được bỏ qua theo mặc định. Do đó, `lastName`, `age` và `active` không tham gia điều kiện nếu probe chưa gán chúng. `Example` là immutable: sau khi tạo, nếu cần bộ điều kiện khác, hãy tạo probe hoặc Example mới thay vì coi Example là đối tượng truy vấn có thể chỉnh sửa tại chỗ.

## 4. Kết hợp tất cả hoặc bất kỳ điều kiện nào

`ExampleMatcher.matchingAll()` yêu cầu tất cả property có giá trị trong probe phải khớp. Đây là chế độ mặc định và phù hợp với tìm kiếm có nhiều bộ lọc đồng thời.

```java
Person probe = new Person();
probe.setStatus("ACTIVE");
probe.setActive(true);

Example<Person> example = Example.of(
    probe,
    ExampleMatcher.matchingAll()
);
```

Logic tương đương:

```text
status = 'ACTIVE' AND active = true
```

Nếu muốn chỉ cần một trong các điều kiện khớp, dùng `matchingAny()`:

```java
Person probe = new Person();
probe.setStatus("ACTIVE");
probe.setLastName("Nguyen");

Example<Person> example = Example.of(
    probe,
    ExampleMatcher.matchingAny()
);
```

Logic tương đương:

```text
status = 'ACTIVE' OR lastName = 'Nguyen'
```

`matchingAny()` áp dụng OR cho các predicate được tạo từ probe. Nó không cung cấp cú pháp để tạo các nhóm lồng nhau tùy ý như `(A AND B) OR (C AND D)`. Nếu nghiệp vụ cần nhóm logic như vậy, hãy dùng `@Query` với Cypher có dấu ngoặc rõ ràng.

## 5. Tùy chỉnh cách so khớp chuỗi

`ExampleMatcher` cho phép đặt quy tắc so khớp chuỗi chung hoặc riêng cho từng property. Các kiểu thường gặp gồm:

| String matcher | Ý nghĩa minh họa |
|---|---|
| `EXACT` | Giá trị phải khớp chính xác |
| `STARTING` | Chuỗi bắt đầu bằng giá trị probe |
| `ENDING` | Chuỗi kết thúc bằng giá trị probe |
| `CONTAINING` | Chuỗi có chứa giá trị probe |

Ví dụ tìm người có tên chứa `an`, không phân biệt chữ hoa/chữ thường:

```java
Person probe = new Person();
probe.setFirstName("an");
probe.setStatus("ACTIVE");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withMatcher(
        "firstName",
        match -> match.contains().ignoreCase()
    );

Example<Person> example = Example.of(probe, matcher);
List<Person> people = personRepository.findAll(example);
```

Ở đây, `firstName` dùng kiểu chứa chuỗi và không phân biệt hoa thường; `status` vẫn dùng so khớp chính xác theo mặc định. Có thể cấu hình matcher ở cấp toàn bộ Example bằng `withStringMatcher(...)`, rồi ghi đè riêng một property bằng `withMatcher(...)`.

Khả năng và cách triển khai string matching phụ thuộc datastore. Với Spring Data Neo4j, hãy xác minh kiểu matcher đang dùng trên phiên bản SDN của dự án và kiểm thử với dữ liệu thực tế, nhất là khi cần regex hoặc quy tắc ký tự đặc biệt. Không nên mặc định mọi biểu thức chuỗi đều được xử lý giống nhau ở mọi store.

## 6. Bỏ qua property và xử lý null

Bạn có thể bỏ qua một hoặc nhiều property ngay cả khi probe đã có giá trị:

```java
Person probe = new Person();
probe.setFirstName("An");
probe.setLastName("Nguyen");
probe.setStatus("ACTIVE");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnorePaths("lastName");

Example<Person> example = Example.of(probe, matcher);
```

Trong ví dụ, `lastName` không được đưa vào điều kiện; chỉ `firstName` và `status` được dùng.

Mặc định, property `null` trong probe bị bỏ qua. `withIncludeNullValues()` thay đổi quy tắc này để các giá trị null được xem xét trong điều kiện truy vấn:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIncludeNullValues();
```

Hãy dùng tùy chọn này cẩn thận. Trong Neo4j, property có giá trị `null` thường tương đương property không tồn tại trên node. Nếu đưa tất cả trường null vào probe, truy vấn có thể trở nên rộng hoặc khác với ý định của form tìm kiếm. Với yêu cầu cụ thể như “tìm node chưa có email”, hãy cân nhắc Cypher tường minh với `p.email IS NULL` để thể hiện rõ điều kiện.

Một lưu ý khác: QBE dựa vào nullability để xác định property có tham gia điều kiện hay không. Các kiểu primitive như `int`, `long`, `boolean` luôn có giá trị mặc định và do đó có thể luôn được đưa vào điều kiện, trừ khi được khai báo bỏ qua bằng `withIgnorePaths`. Với probe tìm kiếm, nên ưu tiên kiểu wrapper như `Integer`, `Long`, `Boolean` để phân biệt “không nhập bộ lọc” với `0` hoặc `false`.

## 7. Tùy chỉnh một property mà không ảnh hưởng các property khác

Các cấu hình ở cấp property có thể ghi đè cấu hình mặc định của matcher. Ví dụ, muốn tìm theo tên không phân biệt hoa thường và bắt đầu bằng chuỗi nhập vào, nhưng vẫn khớp trạng thái chính xác:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withStringMatcher(ExampleMatcher.StringMatcher.EXACT)
    .withMatcher(
        "firstName",
        match -> match.startsWith().ignoreCase()
    );
```

Ở đây, `firstName` được cấu hình riêng. Các trường chuỗi khác vẫn kế thừa quy tắc mặc định `EXACT`. Cách này hữu ích khi một form có nhiều bộ lọc với cách tìm khác nhau.

`ExampleMatcher` có thể tái sử dụng cho nhiều probe nếu các quy tắc tìm kiếm giống nhau. Bản thân matcher cũng là đối tượng cấu hình bất biến theo API builder: mỗi lời gọi cấu hình tạo ra matcher mới, vì vậy hãy giữ lại kết quả trả về từ chuỗi cấu hình.

## 8. Phân trang, sắp xếp và projection bằng fluent API

QBE không chỉ trả về toàn bộ entity. `findBy(example, queryFunction)` cung cấp fluent API để giới hạn số kết quả, sắp xếp, phân trang hoặc đọc projection.

Ví dụ interface projection:

```java
public interface PersonSummary {
    String getPersonId();
    String getFirstName();
    String getLastName();
}
```

Thực thi QBE và trả về trang kết quả:

```java
Page<PersonSummary> page = personRepository.findBy(
    example,
    query -> query
        .as(PersonSummary.class)
        .page(PageRequest.of(
            0,
            20,
            Sort.by("lastName").ascending()
        ))
);
```

`as(PersonSummary.class)` chọn kiểu projection; `page(...)` áp dụng phân trang và sắp xếp. Các thao tác trung gian và kết thúc phải được gọi bên trong hàm query truyền cho `findBy`.

Có thể lấy một kết quả đầu tiên theo thứ tự:

```java
Optional<Person> first = personRepository.findBy(
    example,
    query -> query
        .sortBy(Sort.by("lastName").descending())
        .first()
);
```

Fluent API còn hỗ trợ `all`, `first`, `one`, `count`, `exists`, `slice`, `scroll` và `stream` tùy phiên bản Spring Data. Khi dùng `stream()`, cần đóng stream sau khi xử lý vì nó giữ tài nguyên đọc trong quá trình duyệt.

## 9. Khi nào nên dùng Query by Example?

QBE phù hợp khi người dùng có thể nhập một tập bộ lọc đơn giản, và số trường được nhập thay đổi theo từng request.

Ví dụ phù hợp:

- Tìm `Person` theo một hoặc nhiều trường như `firstName`, `lastName`, `status`.
- Form quản trị cho phép chọn bộ lọc tùy ý, trong đó các điều kiện được kết hợp theo AND hoặc OR đơn giản.
- Tìm theo chuỗi chính xác, bắt đầu bằng, kết thúc bằng hoặc chứa chuỗi khi store hỗ trợ.
- Muốn phân trang, sắp xếp hoặc lấy projection từ cùng một Example.
- Muốn giảm số lượng phương thức repository cho nhiều tổ hợp điều kiện cơ bản.

QBE đặc biệt hữu ích khi probe phản ánh trực tiếp các trường có thể tìm kiếm trên một entity. Nó giúp code tìm kiếm dễ đọc hơn vì đối tượng mẫu thể hiện rõ những giá trị người dùng cung cấp.

## 10. Khi nào không nên dùng Query by Example?

QBE có một số giới hạn quan trọng:

- Không hỗ trợ biểu thức điều kiện Boolean lồng nhau hoặc nhóm logic phức tạp tùy ý. Dù matcher có thể cấu hình theo property path, QBE không phải công cụ để mô tả mọi pattern traversal hoặc nhóm điều kiện tùy chỉnh trên đồ thị.
- Không phải công cụ tổng quát cho toán tử so sánh như `greater than`, `between`, phép tính hoặc điều kiện tùy chỉnh trên nhiều property.
- Khả năng string matching phụ thuộc datastore và phiên bản.
- Không phù hợp để mô tả traversal phức tạp qua nhiều relationship hoặc điều kiện nghiệp vụ trên thuộc tính relationship.
- Không thay thế Cypher aggregation, `OPTIONAL MATCH`, path traversal hoặc truy vấn cần kiểm soát graph shape.

Chọn công cụ theo nhu cầu:

| Nhu cầu | Công cụ nên cân nhắc |
|---|---|
| Bộ lọc đơn giản từ các property của entity | Query by Example |
| Một vài điều kiện có toán tử rõ như `GreaterThan`, `Between` | Derived query method |
| Điều kiện trên nhiều relationship hoặc property của relationship | `@Query` với Cypher |
| Nhóm logic lồng nhau, aggregation hoặc path traversal | `@Query` hoặc `Neo4jClient` |
| Kết quả tùy chỉnh, DTO hoặc projection đặc biệt | `@Query`/`Neo4jClient` kết hợp projection phù hợp |

Ví dụ, nếu cần tìm người từ 18 tuổi trở lên, QBE không diễn đạt trực tiếp phép `>=`. Có thể dùng derived query:

```java
List<Person> findByAgeGreaterThanEqual(Integer minimumAge);
```

Nếu cần tìm sinh viên đăng ký khóa học thuộc một khoa, với trạng thái và điểm nằm trên relationship, nên dùng Cypher:

```cypher
MATCH (s:Student)-[e:ENROLLED_IN]->(c:Course)-[:OFFERED_BY]->(d:Department)
WHERE d.departmentCode = $departmentCode
  AND e.status = $status
  AND e.score >= $minimumScore
RETURN s, e, c, d
```

Truy vấn này thể hiện rõ đường đi và điều kiện trên relationship, điều mà một probe đơn giản không diễn đạt tốt.

## 11. Ví dụ service tạo Example từ bộ lọc tìm kiếm

Trong ứng dụng thực tế, request tìm kiếm thường có nhiều trường tùy chọn. Có thể chuyển request thành probe và matcher trong service:

```java
public record PersonSearchRequest(
    String firstName,
    String lastName,
    String status
) {}
```

```java
public Page<Person> search(PersonSearchRequest request, Pageable pageable) {
    Person probe = new Person();
    probe.setFirstName(request.firstName());
    probe.setLastName(request.lastName());
    probe.setStatus(request.status());

    ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnorePaths("personId", "age", "active")
        .withMatcher("firstName", match -> match.contains().ignoreCase())
        .withMatcher("lastName", match -> match.contains().ignoreCase());

    Example<Person> example = Example.of(probe, matcher);

    return personRepository.findBy(
        example,
        query -> query.page(pageable)
    );
}
```

Service chuyển các trường tùy chọn từ request thành probe. Các trường không được nhập có giá trị null và bị bỏ qua theo mặc định. `status` được so khớp chính xác; `firstName` và `lastName` dùng contains không phân biệt hoa thường. Những trường không thuộc form tìm kiếm được đưa vào `withIgnorePaths` để tránh vô tình tham gia điều kiện nếu entity có giá trị mặc định.

Với request thực tế, hãy validate và chuẩn hóa dữ liệu đầu vào trước khi tạo probe. Ví dụ, trim khoảng trắng của chuỗi, kiểm tra độ dài, giới hạn kích thước trang và chỉ cho phép sắp xếp theo các property được API công khai.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không có kết quả dù form chỉ nhập một trường | Một primitive khác trong probe có giá trị mặc định và tham gia điều kiện | Dùng wrapper type hoặc `withIgnorePaths`. |
| Kết quả ít hơn mong đợi | `matchingAll()` yêu cầu mọi property đã điền đều khớp | Kiểm tra probe; dùng `matchingAny()` nếu nghiệp vụ là OR đơn giản. |
| Chuỗi không tìm theo contains | Matcher mặc định là exact hoặc store không hỗ trợ kiểu so khớp mong muốn | Cấu hình `withMatcher` và kiểm thử với phiên bản SDN đang dùng. |
| Trường null làm truy vấn quá rộng hoặc quá chặt | Hiểu sai mặc định bỏ qua null hoặc bật `withIncludeNullValues()` | Xác định rõ null là “không lọc” hay “property chưa tồn tại”. |
| Không biểu diễn được điều kiện tuổi từ một ngưỡng | QBE chủ yếu dùng exact matching cho kiểu không phải chuỗi | Dùng derived query hoặc `@Query`. |
| Không lọc được property trên relationship | Probe không phải công cụ mô tả graph traversal tùy ý | Dùng custom Cypher và tham số có tên. |
| `findOne` báo nhiều kết quả | Probe không duy nhất nhưng API yêu cầu một kết quả | Dùng `findAll`, `first` hoặc bổ sung điều kiện duy nhất. |

## 13. Quy trình áp dụng QBE

1. Xác định các property đơn giản mà form tìm kiếm cho phép lọc.
2. Tạo probe từ entity tương ứng và chỉ gán các trường người dùng đã nhập.
3. Dùng wrapper type cho trường số/boolean tùy chọn để phân biệt null với giá trị mặc định.
4. Chọn `matchingAll()` hoặc `matchingAny()` theo đúng logic nghiệp vụ.
5. Cấu hình string matcher, ignore path và null handling cho từng trường cần thiết.
6. Chọn `findAll`, `findOne`, `count`, `exists` hoặc fluent API cho pagination/projection.
7. Kiểm thử probe rỗng, từng trường riêng lẻ, nhiều trường, chuỗi hoa thường và giá trị null.
8. Chuyển sang derived query hoặc Cypher khi cần toán tử, nhóm logic hoặc relationship traversal phức tạp.

## 14. Ghi nhớ

Query by Example trong Spring Data Neo4j tạo truy vấn từ probe và `ExampleMatcher`. Nó phù hợp với form tìm kiếm động có các điều kiện đơn giản trên property của entity. Mặc định, property null được bỏ qua và các giá trị đã điền được kết hợp theo AND; `matchingAny()` chuyển sang OR. `ExampleMatcher` cho phép bỏ qua property, tùy chỉnh string matching, phân biệt hoa thường và xử lý null.

QBE không phải ngôn ngữ truy vấn tổng quát. Nó không giải quyết tốt điều kiện lồng nhau, phép so sánh theo khoảng, aggregation hoặc traversal phức tạp qua relationship. Hãy dùng derived query cho toán tử property thông dụng và custom Cypher khi cần kiểm soát chính xác pattern đồ thị, relationship properties hoặc nhóm điều kiện.

## Tài liệu tham khảo

- [Spring Data Neo4j – Query by Example](https://docs.spring.io/spring-data/neo4j/reference/query-by-example.html)
- [Spring Data Neo4j – FAQ](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
