# Fluent find: chọn kiểu miền, projection và kết quả cuối

## Mục tiêu bài học

`Neo4jTemplate` cung cấp API tìm kiếm theo kiểu fluent để ứng dụng mô tả một thao tác đọc theo từng bước: chọn kiểu entity gốc, chọn kiểu kết quả nếu cần projection, thêm điều kiện truy vấn và chọn cách lấy kết quả. Cách viết này hữu ích khi một service cần truy vấn nhiều kiểu entity mà không muốn tạo repository riêng cho từng kiểu.

Bài học tập trung vào ba quyết định của fluent find:

1. **Domain type:** node entity nào là gốc của thao tác đọc?
2. **Projection type:** ứng dụng cần trả về entity đầy đủ hay một góc nhìn dữ liệu nhỏ hơn?
3. **Terminal operation:** cần lấy tất cả kết quả, đúng không hoặc một kết quả, hay một giá trị nullable?

Bạn sẽ thực hành chuỗi `find(...).as(...).matching(...).all()`, hiểu khác biệt giữa `one()` và `oneValue()`, và tránh nhầm `one()` với thao tác lấy phần tử đầu tiên.

## 1. Fluent find giải quyết vấn đề gì?

Repository phù hợp khi ứng dụng muốn có một contract ổn định theo từng aggregate hoặc entity. Tuy nhiên, một service tổng hợp có thể cần đọc nhiều kiểu node, hoặc cần chọn projection tùy từng luồng nghiệp vụ. `Neo4jTemplate` cho phép thực hiện các thao tác này trực tiếp mà không phải tạo một repository chỉ để dùng một truy vấn.

Ví dụ, một trang quản trị cần:

- Danh sách khách hàng đang hoạt động.
- Một bản tóm tắt khách hàng theo email.
- Một danh sách projection chỉ gồm tên và email.

Các truy vấn đều bắt đầu từ node `Person`, nhưng kiểu dữ liệu ứng dụng nhận về có thể khác nhau. Fluent find biểu đạt điều đó trong cùng một chuỗi thao tác.

```java
List<Person> people = neo4jTemplate
        .find(Person.class)
        .all();
```

`find(Person.class)` bắt đầu thao tác với domain type `Person`. Vì không có điều kiện bổ sung, `all()` lấy tất cả entity kiểu đó. Với tập dữ liệu lớn, hãy thêm điều kiện và cân nhắc phân trang hoặc giới hạn kết quả thay vì tải toàn bộ node.

## 2. Chọn domain type bằng find(Class)

`find(Class<T> domainType)` là điểm bắt đầu của fluent find. Kiểu được truyền vào là **domain type nguồn** mà SDN dùng để hiểu cấu trúc graph cần ánh xạ.

Ví dụ entity:

```java
@Node("Person")
public class Person {

    @Id
    private String id;

    private String name;

    private String email;

    private String status;

    // Constructor, getter và setter được lược bỏ.
}
```

Bắt đầu truy vấn:

```java
FluentFindOperation.ExecutableFind<Person> findPerson =
        neo4jTemplate.find(Person.class);
```

Domain type cho SDN biết:

- Label node cần ánh xạ, ở đây là `Person`.
- Property Java nào thuộc entity.
- Relationship nào được khai báo trong entity và cách ánh xạ chúng.
- Metadata cần thiết để chuyển dữ liệu graph thành object Java.

Hãy chọn đúng entity gốc của dữ liệu. Nếu muốn tìm node `Person`, hãy bắt đầu bằng `find(Person.class)`; nếu muốn tìm node `Order`, hãy bắt đầu bằng `find(Order.class)`. Không dùng DTO làm domain type chỉ vì đó là kiểu dữ liệu mà controller muốn trả về.

Khi cần đọc nhiều kiểu entity, mỗi thao tác có thể bắt đầu bằng domain type tương ứng. Đây là một trong những lợi ích chính của template trong module có nhiều loại node.

## 3. Chọn kiểu kết quả bằng as(Class)

Mặc định, fluent find ánh xạ kết quả về chính domain type đã chọn. Khi ứng dụng chỉ cần một phần dữ liệu, dùng `as(Class<R> resultType)` để chọn projection type.

Ví dụ, màn hình danh sách chỉ cần tên và email:

```java
public interface PersonSummary {

    String getName();

    String getEmail();
}
```

Thao tác đọc projection:

```java
List<PersonSummary> summaries = neo4jTemplate
        .find(Person.class)
        .as(PersonSummary.class)
        .all();
```

Hai kiểu trong chuỗi có vai trò khác nhau:

- `Person.class` là domain type nguồn, xác định node và metadata mapping.
- `PersonSummary.class` là kiểu kết quả, xác định góc nhìn mà ứng dụng nhận về.

Không cần tạo một entity Neo4j mới chỉ để phục vụ projection. Interface projection được Spring Data tạo thành proxy dựa trên entity nguồn; các getter như `getName()` và `getEmail()` phải tương ứng với property mà domain type có thể ánh xạ.

### Interface projection và DTO projection

Interface projection phù hợp với một góc nhìn chỉ đọc, có các getter trỏ tới property của entity:

```java
public interface PersonCard {

    String getName();

    String getEmail();
}
```

DTO phù hợp khi ứng dụng cần một kiểu dữ liệu cụ thể để truyền qua các tầng hoặc trả về từ API:

```java
public record PersonCardDto(
        String name,
        String email
) {
}
```

Có thể chọn DTO trong fluent find:

```java
List<PersonCardDto> cards = neo4jTemplate
        .find(Person.class)
        .as(PersonCardDto.class)
        .all();
```

Với projection dựa trên entity, tên property trong projection cần khớp với tên property Java của domain model. Nếu entity dùng `@Property("full_name")` cho trường Java `fullName`, projection nên dùng `getFullName()` hoặc component `fullName`, không dùng tên vật lý `full_name`.

Projection giúp giới hạn dữ liệu cần chuyển về ứng dụng, đặc biệt khi entity có nhiều property hoặc relationship mà một màn hình không sử dụng. Hãy thiết kế projection theo nhu cầu của từng use case, tránh tạo một projection quá rộng rồi dùng ở mọi nơi.

## 4. Thêm điều kiện bằng matching

Sau khi chọn domain type và projection, có thể thêm điều kiện bằng `matching(...)`. Fluent find hỗ trợ query dạng chuỗi cùng map tham số, hoặc một `Statement` được xây dựng bằng Cypher-DSL.

Cách dùng Cypher-DSL giúp tạo điều kiện có cấu trúc và gắn giá trị tham số mà không nối trực tiếp dữ liệu đầu vào vào chuỗi Cypher.

Ví dụ tìm những người có trạng thái `ACTIVE`:

```java
import org.neo4j.cypherdsl.core.Cypher;
import org.neo4j.cypherdsl.core.Node;
import org.neo4j.cypherdsl.core.Statement;

Node person = Cypher.node("Person").named("p");

Statement activePeopleQuery = Cypher.match(person)
        .where(person.property("status")
                .isEqualTo(Cypher.parameter("status", "ACTIVE")))
        .returning(person)
        .build();

List<Person> activePeople = neo4jTemplate
        .find(Person.class)
        .matching(activePeopleQuery)
        .all();
```

Ở đây:

- `Cypher.node("Person").named("p")` mô tả node và bí danh dùng trong câu lệnh.
- `Cypher.parameter("status", "ACTIVE")` tạo tham số có tên và giá trị.
- `matching(activePeopleQuery)` đưa statement vào thao tác tìm kiếm.
- `all()` thực thi và trả về danh sách entity phù hợp.

Có thể kết hợp điều kiện với projection:

```java
List<PersonSummary> activeSummaries = neo4jTemplate
        .find(Person.class)
        .as(PersonSummary.class)
        .matching(activePeopleQuery)
        .all();
```

Khi đó, SDN vẫn dùng metadata của `Person` làm domain type để ánh xạ graph, nhưng chuyển kết quả sang `PersonSummary`.

Nếu dùng dạng chuỗi, `matching(String query, Map<String, Object> parameters)` nhận câu truy vấn và map tham số. Hãy truyền giá trị động qua parameter map. Tránh ghép trực tiếp chuỗi từ request vào Cypher vì có thể làm sai cú pháp và tạo rủi ro injection.

## 5. Chọn terminal operation phù hợp

Fluent find chỉ thực thi truy vấn khi gọi một terminal operation. Terminal operation quyết định cách biểu diễn số lượng kết quả.

| Terminal operation | Kiểu trả về | Ý nghĩa |
|---|---|---|
| `all()` | `List<T>` | Lấy tất cả kết quả phù hợp; danh sách không null |
| `one()` | `Optional<T>` | Yêu cầu có không hoặc đúng một kết quả |
| `oneValue()` | `T` hoặc null | Yêu cầu có không hoặc đúng một kết quả, không dùng Optional |

### Lấy tất cả bằng all()

Dùng `all()` khi truy vấn có thể trả về nhiều entity:

```java
List<Person> people = neo4jTemplate
        .find(Person.class)
        .matching(activePeopleQuery)
        .all();
```

Nếu không có node nào phù hợp, kết quả là danh sách rỗng. Không cần bọc `List` trong `Optional`.

### Lấy không hoặc một kết quả bằng one()

Dùng `one()` khi điều kiện truy vấn có quy tắc duy nhất, ví dụ tìm theo ID hoặc email đã được bảo đảm duy nhất:

```java
Node person = Cypher.node("Person").named("p");

Statement personByEmail = Cypher.match(person)
        .where(person.property("email")
                .isEqualTo(Cypher.parameter("email", "an@example.com")))
        .returning(person)
        .build();

Optional<Person> result = neo4jTemplate
        .find(Person.class)
        .matching(personByEmail)
        .one();
```

Kết quả:

- Không có node phù hợp: `Optional.empty()`.
- Có đúng một node: `Optional.of(person)`.
- Có nhiều hơn một node: SDN ném `IncorrectResultSizeDataAccessException`.

Vì vậy, `one()` không có nghĩa là lấy phần tử đầu tiên trong danh sách. Nó xác nhận hợp đồng truy vấn là tối đa một kết quả. Nếu email phải duy nhất, hãy bảo vệ quy tắc đó bằng uniqueness constraint trong Neo4j, không chỉ dựa vào giả định của code.

### Dùng oneValue() khi muốn giá trị nullable

`oneValue()` cũng yêu cầu tối đa một kết quả, nhưng trả về trực tiếp entity hoặc `null`:

```java
Person personValue = neo4jTemplate
        .find(Person.class)
        .matching(personByEmail)
        .oneValue();

if (personValue == null) {
    // Không tìm thấy người phù hợp.
}
```

Chọn `one()` nếu ứng dụng đang dùng `Optional` để biểu đạt sự vắng mặt. Chọn `oneValue()` khi hợp đồng của tầng gọi dùng null. Cả hai đều báo lỗi nếu truy vấn trả về nhiều hơn một kết quả.

## 6. Không nhầm one() với lấy phần tử đầu tiên

Fluent find có các terminal operation `all()`, `one()` và `oneValue()`. Không có terminal operation `first()` trong API này.

Nếu nghiệp vụ muốn lấy người mới nhất, cần định nghĩa rõ thứ tự và giới hạn kết quả trong truy vấn. Chỉ sau khi truy vấn đã giới hạn tối đa một dòng, `one()` mới phù hợp.

Ví dụ về ý tưởng truy vấn:

```cypher
MATCH (p:Person)
WHERE p.status = $status
RETURN p
ORDER BY p.createdAt DESC, p.id ASC
LIMIT 1
```

`ORDER BY` xác định người nào được ưu tiên; `LIMIT 1` giới hạn kết quả tối đa một node. Khóa phụ `id` giúp thứ tự ổn định nếu nhiều người có cùng thời điểm tạo.

Nếu bỏ `ORDER BY`, không nên giả định node đầu tiên sẽ luôn giống nhau giữa các lần thực thi. Nếu bỏ `LIMIT 1` rồi gọi `one()` cho điều kiện có nhiều kết quả, SDN sẽ báo lỗi thay vì tự chọn một node.

## 7. Ví dụ hoàn chỉnh trong service

Có thể gom thao tác fluent find trong một service dùng chung `Neo4jTemplate`:

```java
@Service
public class PersonLookupService {

    private final Neo4jTemplate neo4jTemplate;

    public PersonLookupService(Neo4jTemplate neo4jTemplate) {
        this.neo4jTemplate = neo4jTemplate;
    }

    public List<PersonSummary> findActivePeople() {
        Node person = Cypher.node("Person").named("p");

        Statement query = Cypher.match(person)
                .where(person.property("status")
                        .isEqualTo(Cypher.parameter("status", "ACTIVE")))
                .returning(person)
                .build();

        return neo4jTemplate
                .find(Person.class)
                .as(PersonSummary.class)
                .matching(query)
                .all();
    }
}
```

Service không cần một repository riêng cho truy vấn này. Nó chọn entity nguồn `Person`, chọn projection `PersonSummary`, áp dụng điều kiện và trả danh sách.

Với các thao tác đọc trong một nghiệp vụ chỉ đọc, có thể đặt service method trong transaction read-only:

```java
@Transactional(readOnly = true)
public List<PersonSummary> findActivePeople() {
    // Tạo statement và gọi fluent find như ví dụ trên.
}
```

Nếu service kết hợp đọc và ghi, hãy dùng transaction phù hợp với toàn bộ nghiệp vụ. Fluent find chỉ là cách xây dựng thao tác đọc; nó không thay thế transaction manager hoặc tự quyết định ranh giới transaction.

## 8. Chọn domain type và projection theo use case

Một vài tình huống thường gặp:

| Use case | Domain type | Projection | Terminal |
|---|---|---|---|
| Đọc hồ sơ đầy đủ của một người theo ID | `Person.class` | Không cần `as()` | `one()` |
| Hiển thị danh sách tên và email | `Person.class` | `PersonSummary.class` | `all()` |
| Tìm người theo trạng thái | `Person.class` | Entity hoặc summary | `all()` |
| Tìm người theo email duy nhất | `Person.class` | Entity hoặc summary | `one()` |
| Đọc giá trị đơn nullable cho code cũ | `Person.class` | Entity | `oneValue()` |
| Chọn người mới nhất | `Person.class` | Entity hoặc summary | Truy vấn có `ORDER BY` và `LIMIT 1`, sau đó `one()` |

Hãy chọn domain type dựa trên node gốc cần ánh xạ. Chọn projection dựa trên dữ liệu tầng gọi cần. Chọn terminal dựa trên cardinality của truy vấn. Ba quyết định này độc lập với nhau và nên được thể hiện rõ trong code.

## 9. Fluent find và các API truy cập dữ liệu khác

`Neo4jTemplate` nằm giữa repository và Neo4j Client trong các abstraction của SDN:

- **Repository:** phù hợp với contract truy cập dữ liệu theo aggregate và các truy vấn được dùng thường xuyên.
- **Neo4jTemplate:** phù hợp với thao tác theo kiểu entity động, projection và các service cần dùng chung một API đọc/ghi cho nhiều domain type.
- **Neo4jClient:** phù hợp khi cần điều khiển trực tiếp record và tự ánh xạ kết quả bằng mapper.

Nếu kết quả cần hydrate thành entity hoặc projection dựa trên entity, fluent find giúp tận dụng metadata mapping của SDN. Nếu truy vấn trả về một cấu trúc record hoàn toàn riêng, không giống domain model, `Neo4jClient` với `fetchAs(...).mappedBy(...)` có thể phù hợp hơn vì ứng dụng tự định nghĩa cách chuyển từng record thành object.

Không nên dùng fluent find chỉ vì chuỗi method trông ngắn hơn. Hãy chọn abstraction phù hợp với hình dạng dữ liệu và mức độ kiểm soát mapping mà use case yêu cầu.

## 10. Kiểm thử domain type, projection và terminal operation

Một integration test nên kiểm tra cả dữ liệu trả về và hợp đồng số lượng:

```java
@DataNeo4jTest
class PersonFluentFindTest {

    @Autowired
    private Neo4jTemplate neo4jTemplate;

    @Test
    void shouldReturnPersonSummaryProjection() {
        // Tạo và lưu một số Person có status khác nhau.
        // Xây dựng Statement lọc status = ACTIVE.
        // Gọi find(Person.class).as(PersonSummary.class)
        //     .matching(statement).all().
        // Xác nhận chỉ người ACTIVE được trả về.
        // Xác nhận projection có name và email.
    }

    @Test
    void shouldReturnOptionalForUniqueMatch() {
        // Tạo đúng một Person có email cần tìm.
        // Gọi find(Person.class).matching(statement).one().
        // Xác nhận Optional chứa Person đó.
    }
}
```

Nên bổ sung các trường hợp:

1. `all()` trả danh sách rỗng khi không có node phù hợp.
2. `one()` trả `Optional.empty()` khi không có kết quả.
3. `one()` trả entity khi có đúng một kết quả.
4. `one()` ném `IncorrectResultSizeDataAccessException` khi có nhiều kết quả.
5. `oneValue()` trả null khi không tìm thấy và báo lỗi khi có nhiều kết quả.
6. Projection chỉ cung cấp các property được khai báo.
7. Điều kiện được truyền bằng parameter không làm thay đổi cú pháp truy vấn.
8. Truy vấn chọn phần tử đầu tiên có `ORDER BY` và `LIMIT` rõ ràng.

Test cần dùng Neo4j thật hoặc Testcontainers/Test Harness phù hợp với dự án để xác nhận cả Cypher-DSL, transaction và mapping. Kiểm tra một chuỗi method bằng mock không chứng minh rằng Neo4j trả dữ liệu có cấu trúc đúng.

## 11. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng DTO làm domain type trong `find(...)` | Nhầm kiểu nguồn với kiểu kết quả | Dùng entity trong `find`, DTO/interface trong `as` |
| Bỏ `as()` nhưng mong nhận projection | Kiểu kết quả mặc định là domain type | Khai báo `as(Projection.class)` |
| Getter projection không khớp property | Tên getter không tương ứng property Java | Đối chiếu domain model và mapping |
| Dùng `one()` cho truy vấn nhiều kết quả | `one()` yêu cầu tối đa một record | Dùng `all()` hoặc giới hạn truy vấn rõ ràng |
| Nghĩ `one()` lấy dòng đầu | Nhầm kiểm tra cardinality với giới hạn kết quả | Dùng `ORDER BY` và `LIMIT 1` nếu cần chọn đầu |
| Dùng `oneValue()` nhưng không kiểm tra null | Bỏ qua trường hợp không tìm thấy | Xử lý null hoặc dùng `one()` |
| Truyền dữ liệu đầu vào bằng nối chuỗi Cypher | Không dùng parameter binding | Dùng tham số Cypher hoặc Cypher-DSL |
| Dùng projection quá rộng | Chuyển nhiều property/relationship không cần thiết | Tạo projection theo use case |
| Dùng `all()` trên tập dữ liệu rất lớn | Tải toàn bộ kết quả vào bộ nhớ | Thêm điều kiện, giới hạn hoặc dùng chiến lược phân trang phù hợp |
| Dùng template cho truy vấn record hoàn toàn tùy biến | Domain mapping không còn là mục tiêu chính | Cân nhắc `Neo4jClient` và mapper riêng |

## 12. Tự kiểm tra

1. `find(Person.class)` xác định điều gì trong fluent find?
2. Khác biệt giữa domain type và projection type là gì?
3. `as(PersonSummary.class)` thay đổi phần nào của thao tác?
4. Có thể thêm điều kiện truy vấn bằng những dạng tham số nào của `matching(...)`?
5. `all()` trả về kiểu gì khi không có kết quả?
6. Vì sao `one()` ném `IncorrectResultSizeDataAccessException` nếu có nhiều kết quả?
7. `one()` khác `oneValue()` ở cách biểu diễn trường hợp không tìm thấy như thế nào?
8. Vì sao `one()` không phải là thao tác lấy phần tử đầu tiên?
9. Khi nào nên dùng `Neo4jClient` thay cho fluent find?
10. Làm thế nào để giảm lượng dữ liệu được hydrate cho một màn hình chỉ đọc?

Hãy viết một service dùng `Neo4jTemplate` để tìm `Person` theo trạng thái. Trước tiên trả về `List<Person>`, sau đó thêm interface projection chỉ có tên và email. Tiếp theo viết truy vấn theo email dùng `one()` và kiểm tra ba trường hợp: không có kết quả, đúng một kết quả và nhiều kết quả. Cuối cùng, mô phỏng yêu cầu “lấy người mới nhất” bằng `ORDER BY` cùng khóa phụ duy nhất và `LIMIT 1`, rồi xác nhận `one()` nhận tối đa một kết quả.

## Tài liệu tham khảo

- [Spring Data Neo4j — FluentFindOperation API](https://docs.spring.io/spring-data/neo4j/docs/8.1.x/api/org/springframework/data/neo4j/core/FluentFindOperation.html)
- [Spring Data Neo4j — FindWithProjection API](https://docs.spring.io/spring-data/neo4j/docs/8.1.x/api/org/springframework/data/neo4j/core/FluentFindOperation.FindWithProjection.html)
- [Spring Data Neo4j — FindWithQuery API](https://docs.spring.io/spring-data/neo4j/docs/8.1.x/api/org/springframework/data/neo4j/core/FluentFindOperation.FindWithQuery.html)
- [Spring Data Neo4j — TerminatingFind API](https://docs.spring.io/spring-data/neo4j/docs/8.1.x/api/org/springframework/data/neo4j/core/FluentFindOperation.TerminatingFind.html)
- [Spring Data Neo4j — Neo4jTemplate API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/Neo4jTemplate.html)
