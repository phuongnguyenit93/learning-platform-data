# Tìm, đếm và kiểm tra tồn tại qua QueryByExampleExecutor

Bài học này thuộc chương **Query by Example** của module **SPRING_DATA_NEO4J**. Khi cần tìm node theo một tập điều kiện được tạo động từ dữ liệu đầu vào, Spring Data Neo4j hỗ trợ Query by Example (QBE). Thay vì viết một phương thức repository cho từng tổ hợp bộ lọc, ứng dụng tạo một object mẫu (probe), cấu hình `ExampleMatcher`, rồi gửi `Example` tới repository.

`Neo4jRepository` đã kế thừa `QueryByExampleExecutor`, vì vậy repository thông thường có thể dùng trực tiếp các thao tác `findOne`, `findAll`, `count` và `exists`. Các thao tác này dùng cùng một `Example`, giúp việc tìm kiếm, đếm kết quả và kiểm tra sự tồn tại giữ chung quy tắc matching.

## 1. QBE gồm Probe, ExampleMatcher và Example

QBE có ba thành phần chính:

- **Probe:** một instance domain entity chứa các giá trị muốn dùng làm điều kiện.
- **ExampleMatcher:** quy định cách so khớp, ví dụ AND/OR, cách xử lý chuỗi, phân biệt chữ hoa chữ thường và các property cần bỏ qua.
- **Example:** kết hợp probe và matcher thành đối tượng truy vấn bất biến.

Ví dụ, ứng dụng có entity `Person`:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String id;

    private String name;

    private String city;

    private Boolean active;

    // constructors, getters and setters
}
```

Repository:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {
}
```

`Neo4jRepository<Person, String>` đã cung cấp `QueryByExampleExecutor<Person>`. Không cần khai báo lại interface này để sử dụng QBE.

Tạo probe chỉ chứa các điều kiện cần tìm:

```java
import org.springframework.data.domain.Example;

Person probe = new Person();
probe.setCity("Hà Nội");
probe.setActive(true);

Example<Person> example = Example.of(probe);
```

Trong ví dụ này, các property có giá trị `null` được bỏ qua theo mặc định. Điều kiện tìm kiếm sẽ dựa trên `city` và `active`; `id` và `name` không tham gia nếu chúng đang là `null`.

## 2. Quy tắc mặc định của probe

QBE xác định property nào tham gia điều kiện dựa trên giá trị của probe:

| Giá trị trong probe | Mặc định |
|---|---|
| Reference property là `null` | Bỏ qua, không tạo điều kiện |
| Reference property có giá trị | Dùng giá trị đó làm điều kiện so khớp |
| String | So khớp theo quy tắc mặc định của store, thường là chính xác nếu không cấu hình matcher khác |
| Kiểu số, ngày giờ, enum và kiểu không phải chuỗi | So khớp chính xác |
| Primitive như `int`, `boolean` | Luôn có giá trị mặc định (`0`, `false`...) nên được đưa vào điều kiện, trừ khi bị ignore |

Đối với trường có thể không được cung cấp trong bộ lọc, nên ưu tiên wrapper như `Integer`, `Boolean` thay cho primitive. Ví dụ `Boolean active = null` có thể được bỏ qua; `boolean active` luôn có giá trị `false` nếu chưa được gán và vì thế có thể vô tình lọc theo `false`.

Nếu probe có ID, ID cũng là một property được so khớp. Khi muốn tìm theo các field nghiệp vụ và bỏ qua ID, hãy cấu hình `withIgnorePaths("id")`.

Một probe không có điều kiện có thể tạo truy vấn rất rộng. Service nên xác thực đầu vào và bảo đảm người dùng cung cấp ít nhất một tiêu chí có ý nghĩa trước khi gọi `findAll`, `count` hoặc `exists`.

## 3. matching() và matchingAny()

`ExampleMatcher.matching()` là chế độ mặc định: tất cả các điều kiện có giá trị phải khớp (AND).

```java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withIgnorePaths("id");

Example<Person> example = Example.of(probe, matcher);
```

Với `city = "Hà Nội"` và `active = true`, kết quả phải thỏa cả hai điều kiện.

Nếu muốn chỉ cần một trong các điều kiện khớp (OR), dùng `matchingAny()`:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAny()
    .withIgnorePaths("id");

Example<Person> example = Example.of(probe, matcher);
```

Với cùng probe, kết quả có thể là người ở Hà Nội hoặc người có trạng thái active. `matchingAny()` tạo OR phẳng giữa các điều kiện được khai báo; nó không phải công cụ để xây dựng các nhóm logic phức tạp như `(city = 'Hà Nội' AND active = true) OR (city = 'Đà Nẵng' AND active = false)`.

## 4. Tùy chỉnh cách so khớp chuỗi

`ExampleMatcher` cho phép cấu hình kiểu matching chung hoặc riêng từng property. Các chế độ chuỗi thường dùng gồm:

| String matcher | Ý nghĩa |
|---|---|
| `EXACT` | Giá trị bằng chính xác chuỗi probe |
| `STARTING` | Giá trị bắt đầu bằng chuỗi probe |
| `ENDING` | Giá trị kết thúc bằng chuỗi probe |
| `CONTAINING` | Giá trị chứa chuỗi probe |
| `REGEX` | So khớp theo biểu thức chính quy nếu store hỗ trợ |

Ví dụ tìm người có tên chứa `an`, không phân biệt hoa thường:

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

Person probe = new Person();
probe.setName("an");

ExampleMatcher matcher = ExampleMatcher.matching()
    .withIgnorePaths("id", "city", "active")
    .withMatcher("name", match -> match.contains().ignoreCase());

Example<Person> example = Example.of(probe, matcher);
```

Có thể cấu hình mặc định cho tất cả chuỗi:

```java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withIgnorePaths("id")
    .withStringMatcher(ExampleMatcher.StringMatcher.CONTAINING)
    .withIgnoreCase();
```

Hoặc chỉ định cách so khớp cho từng property:

```java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withIgnorePaths("id")
    .withMatcher("name", match -> match.startsWith().ignoreCase())
    .withMatcher("city", match -> match.exact());
```

Thiết lập theo property có độ ưu tiên cao hơn thiết lập mặc định của matcher. Các chế độ chuỗi được hỗ trợ phụ thuộc store và phiên bản; đặc biệt cần kiểm tra regex và ignore-case trước khi dùng trong chức năng tìm kiếm chính thức.

## 5. Bỏ qua property và xử lý null

`withIgnorePaths(...)` loại các field khỏi điều kiện ngay cả khi probe đang chứa giá trị:

```java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withIgnorePaths("id", "internalNote");
```

Mặc định, property `null` không tham gia điều kiện. Nếu cần đưa null vào tiêu chí, có thể dùng `withIncludeNullValues()`:

```java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withIncludeNullValues();
```

Neo4j không lưu property có giá trị `null`; gán null trong Cypher có nghĩa là xóa property. Vì vậy, khi dùng `withIncludeNullValues()`, hãy kiểm tra semantics của việc so khớp property không tồn tại trong phiên bản SDN đang sử dụng. Không xem null như một giá trị chuỗi hoặc số được lưu trong node.

Nếu yêu cầu nghiệp vụ cần phân biệt “không gửi field” với “muốn tìm node không có field”, một probe thông thường có thể chưa đủ rõ. Hãy biểu diễn ý định đó trong DTO tìm kiếm và chuyển thành matcher phù hợp, hoặc viết custom query để kiểm soát điều kiện `IS NULL` tường minh.

## 6. Tìm một kết quả bằng findOne

`findOne(example)` trả về `Optional<S>`:

```java
import java.util.Optional;

Optional<Person> person = personRepository.findOne(example);

if (person.isPresent()) {
    System.out.println(person.get().getName());
}
```

Có hai trường hợp cần lưu ý:

- Không có kết quả: trả `Optional.empty()`.
- Có nhiều hơn một kết quả: ném `IncorrectResultSizeDataAccessException`.

Vì vậy, chỉ dùng `findOne()` khi tiêu chí được kỳ vọng xác định tối đa một entity. Nếu cần lấy một phần tử bất kỳ trong nhiều kết quả, hãy sắp xếp và giới hạn bằng fluent API `findBy(..., q -> q.first())`. Nếu nghiệp vụ yêu cầu tính duy nhất, hãy bảo vệ khóa bằng unique constraint trong Neo4j; không dựa vào `findOne()` để tạo ra tính duy nhất.

## 7. Tìm tất cả kết quả bằng findAll

`findAll(example)` trả về danh sách entity phù hợp:

```java
List<Person> people = personRepository.findAll(example);
```

Nếu không có kết quả, danh sách rỗng được trả về. Không nên giả định thứ tự kết quả nếu không cung cấp `Sort`.

Sắp xếp theo property của entity:

```java
import org.springframework.data.domain.Sort;

List<Person> people = personRepository.findAll(
    example,
    Sort.by(Sort.Direction.ASC, "name")
);
```

Phân trang bằng `Pageable`:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Page<Person> page = personRepository.findAll(
    example,
    PageRequest.of(0, 20, Sort.by("name").ascending())
);
```

`Page` chứa nội dung của trang cùng metadata phân trang như số trang, kích thước và tổng số phần tử. Khi chỉ cần một cửa sổ dữ liệu mà không cần tổng số kết quả, cân nhắc `Slice` qua fluent API để tránh yêu cầu metadata tổng số không cần thiết.

## 8. Đếm kết quả bằng count

`count(example)` trả về số entity phù hợp dưới dạng `long`:

```java
long totalPeople = personRepository.count(example);
```

Đây là lựa chọn phù hợp khi màn hình cần tổng số kết quả, thống kê hoặc kiểm tra quy mô tập dữ liệu. Không nên gọi `findAll(example).size()` chỉ để đếm, vì cách đó phải tải các entity về ứng dụng trong khi chỉ cần một con số.

Ví dụ service:

```java
public long countPeopleInCity(String city) {
    Person probe = new Person();
    probe.setCity(city);

    Example<Person> example = Example.of(
        probe,
        ExampleMatcher.matching().withIgnorePaths("id")
    );

    return personRepository.count(example);
}
```

## 9. Kiểm tra tồn tại bằng exists

`exists(example)` trả về `boolean` cho biết có ít nhất một entity khớp điều kiện hay không:

```java
boolean hasActivePeople = personRepository.exists(example);
```

Đây là lựa chọn phù hợp khi chỉ cần quyết định có dữ liệu hay không, ví dụ kiểm tra trước khi hiển thị thông báo hoặc thực hiện một bước nghiệp vụ. Không cần tải danh sách chỉ để gọi `isEmpty()`.

Ví dụ kiểm tra tên đã được sử dụng:

```java
public boolean nameAlreadyUsed(String name) {
    Person probe = new Person();
    probe.setName(name);

    ExampleMatcher matcher = ExampleMatcher.matching()
        .withIgnorePaths("id", "city", "active", "internalNote");

    return personRepository.exists(Example.of(probe, matcher));
}
```

Nếu đây là kiểm tra uniqueness trước khi tạo dữ liệu, vẫn cần unique constraint trong Neo4j để xử lý các yêu cầu đồng thời. Một lời gọi `exists()` rồi một lời gọi `save()` riêng biệt có thể gặp race condition nếu hai request cùng kiểm tra trước khi một request ghi dữ liệu.

## 10. Dùng fluent API findBy để tùy biến kết quả

`QueryByExampleExecutor` cung cấp `findBy(example, queryFunction)`. API này cho phép kết hợp điều kiện từ probe với sắp xếp, giới hạn, projection và kiểu kết quả.

Lấy người đầu tiên theo tên tăng dần:

```java
Optional<Person> firstPerson = personRepository.findBy(
    example,
    query -> query
        .sortBy(Sort.by("name").ascending())
        .first()
);
```

Lấy tối đa 10 người:

```java
List<Person> firstTen = personRepository.findBy(
    example,
    query -> query
        .sortBy(Sort.by("name"))
        .limit(10)
        .all()
);
```

Đếm và kiểm tra tồn tại với cùng fluent query:

```java
long total = personRepository.findBy(example, query -> query.count());

boolean exists = personRepository.findBy(example, query -> query.exists());
```

`findBy` cũng hỗ trợ `as(Projection.class)` để chọn kiểu kết quả và `project(...)` để giới hạn property được đọc. Các thao tác trung gian và kết thúc phải được gọi bên trong query function. Không trả chính đối tượng `FetchableFluentQuery` ra ngoài vì query object chỉ có hiệu lực trong lời gọi `findBy`.

## 11. Kết hợp các thao tác trong service

Một service có thể tạo `Example` một lần rồi dùng lại cho tìm kiếm, đếm và kiểm tra tồn tại:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

@Service
public class PersonSearchService {

    private final PersonRepository personRepository;

    public PersonSearchService(PersonRepository personRepository) {
        this.personRepository = personRepository;
    }

    public List<Person> findByCityAndName(String city, String name) {
        Person probe = new Person();
        probe.setCity(city);
        probe.setName(name);

        ExampleMatcher matcher = ExampleMatcher.matching()
            .withIgnorePaths("id", "active", "internalNote")
            .withMatcher("name", match -> match.contains().ignoreCase());

        Example<Person> example = Example.of(probe, matcher);
        return personRepository.findAll(example, Sort.by("name"));
    }

    public Optional<Person> findUniqueByName(String name) {
        Person probe = new Person();
        probe.setName(name);

        Example<Person> example = Example.of(
            probe,
            ExampleMatcher.matching().withIgnorePaths("id", "city", "active", "internalNote")
        );

        return personRepository.findOne(example);
    }

    public long countByCity(String city) {
        Person probe = new Person();
        probe.setCity(city);

        Example<Person> example = Example.of(
            probe,
            ExampleMatcher.matching().withIgnorePaths("id", "name", "active", "internalNote")
        );

        return personRepository.count(example);
    }

    public boolean hasActivePeopleInCity(String city) {
        Person probe = new Person();
        probe.setCity(city);
        probe.setActive(true);

        Example<Person> example = Example.of(
            probe,
            ExampleMatcher.matching().withIgnorePaths("id", "name", "internalNote")
        );

        return personRepository.exists(example);
    }

    public Page<Person> findPage(Example<Person> example, int page, int size) {
        return personRepository.findAll(
            example,
            PageRequest.of(page, size, Sort.by("name"))
        );
    }
}
```

Trong ví dụ, mỗi phương thức tự xác định probe và các field cần bỏ qua. Với ứng dụng thực tế, có thể tách việc dựng `Example` thành một component hoặc factory để tránh lặp quy tắc matching giữa nhiều endpoint.

## 12. Giới hạn của Query by Example

QBE phù hợp với bộ lọc đơn giản được tạo từ giá trị probe. Nó không phải ngôn ngữ truy vấn tổng quát cho mọi biểu thức graph.

- Không hỗ trợ nhóm điều kiện lồng nhau tùy ý như `(A AND B) OR (C AND D)`.
- Hỗ trợ string matching phụ thuộc store; các kiểu không phải chuỗi thường được so khớp chính xác.
- Không diễn đạt trực tiếp các toán tử nghiệp vụ tùy ý như `greater than`, `between`, tập `IN` phức tạp hoặc biểu thức tính toán.
- Không thay thế truy vấn Cypher khi cần traversal nhiều hop, lọc trên relationship phức tạp, aggregation hoặc pattern graph đặc thù.
- Property path lồng nhau có thể dùng để cấu hình matcher khi được mapping và store hỗ trợ, nhưng điều đó không đồng nghĩa QBE hỗ trợ mọi biểu thức logic trên graph lồng nhau.

Khi điều kiện vượt quá khả năng QBE, hãy dùng derived query method, `@Query` với Cypher hoặc Cypher DSL. Chọn công cụ theo độ phức tạp của điều kiện thay vì cố ép một probe biểu diễn toàn bộ logic nghiệp vụ.

## 13. Kiểm tra hiệu năng và tính đúng đắn

QBE giúp giảm mã tạo truy vấn, nhưng không tự bảo đảm truy vấn chạy nhanh. Khi triển khai:

1. Tạo index hoặc unique constraint cho property thường xuyên được tìm chính xác.
2. Kiểm tra `EXPLAIN`/`PROFILE` nếu truy vấn dùng nhiều điều kiện hoặc lượng dữ liệu lớn.
3. Cân nhắc tác động của `CONTAINING`, `ENDING`, regex và ignore-case; các kiểu tìm chuỗi này có thể tốn chi phí hơn tìm chính xác hoặc prefix.
4. Dùng `exists(example)` khi chỉ cần boolean và `count(example)` khi chỉ cần số lượng.
5. Dùng phân trang hoặc giới hạn khi danh sách kết quả có thể lớn.
6. Xác thực probe để tránh một Example rỗng vô tình tìm quá rộng.
7. Kiểm thử các trường hợp null, primitive mặc định, nhiều kết quả cho `findOne` và matcher OR.

Một bài test nên tạo dữ liệu có nhiều tổ hợp `name`, `city` và `active`, sau đó xác nhận `findAll`, `count` và `exists` trên cùng Example trả kết quả nhất quán. Kiểm tra thêm `findOne` với 0, 1 và hơn 1 kết quả để xác nhận đúng hợp đồng ngoại lệ.

## 14. Nguyên tắc lựa chọn API

| Nhu cầu | API nên dùng | Kết quả |
|---|---|---|
| Tìm đúng một entity, tối đa một kết quả | `findOne(example)` | `Optional<T>`; lỗi nếu có nhiều hơn một |
| Tìm tất cả entity khớp | `findAll(example)` | Danh sách entity |
| Tìm có sắp xếp | `findAll(example, sort)` | Danh sách đã sắp xếp |
| Tìm theo trang | `findAll(example, pageable)` | `Page<T>` |
| Đếm số entity khớp | `count(example)` | `long` |
| Kiểm tra có ít nhất một entity | `exists(example)` | `boolean` |
| Tùy biến sort, limit, projection hoặc kết quả | `findBy(example, queryFunction)` | Kiểu kết quả do fluent query quyết định |

`QueryByExampleExecutor` giúp tái sử dụng cùng một bộ điều kiện cho nhiều nhu cầu: tìm một entity, lấy danh sách, đếm và kiểm tra tồn tại. Hãy xây dựng probe có chủ đích, cấu hình matcher rõ ràng và chọn đúng API theo kết quả cần trả. Khi điều kiện truy vấn trở nên phức tạp hoặc cần traversal graph chuyên sâu, chuyển sang Cypher sẽ giúp biểu đạt logic chính xác hơn.

## Tài liệu tham khảo

- [Spring Data Neo4j – Query by Example](https://docs.spring.io/spring-data/neo4j/reference/query-by-example.html)
- [Spring Data Neo4j – Neo4jRepository API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/repository/Neo4jRepository.html)
- [Spring Data Commons – Query by Example](https://docs.spring.io/spring-data/commons/reference/query-by-example.html)
- [Spring Data Commons – QueryByExampleExecutor API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/query/QueryByExampleExecutor.html)
