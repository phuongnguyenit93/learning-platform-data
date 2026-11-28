# Biến thể reactive và phạm vi API được hỗ trợ

Spring Data Neo4j (SDN) tích hợp Cypher-DSL để xây dựng truy vấn Cypher bằng Java API có kiểu dữ liệu. Khi ứng dụng dùng reactive stack, SDN cung cấp các repository mixin reactive tương ứng. Hai nhóm API chính giải quyết hai nhu cầu khác nhau: thêm điều kiện vào truy vấn do SDN sinh sẵn, hoặc thực thi một `Statement` Cypher-DSL hoàn chỉnh do ứng dụng tự xây dựng.

Điểm cần nhớ là reactive không chỉ đổi `List` thành `Flux`. Repository phải dùng reactive base interface, các mixin phải đúng biến thể reactive và kết quả được biểu diễn bằng Reactor `Mono` hoặc `Flux`. Ngoài ra, mỗi mixin có tập method riêng; không nên giả định mọi khả năng của imperative API đều có mặt ở reactive API.

## 1. Cypher-DSL trong reactive SDN

Cypher-DSL mô tả câu truy vấn bằng các đối tượng Java như `Node`, `Relationship`, `Condition` và `Statement`. SDN chuyển biểu thức đó thành Cypher, truyền tham số và ánh xạ kết quả theo entity metadata hoặc projection được yêu cầu.

Trong reactive application, luồng xử lý thường có dạng:

~~~mermaid
flowchart TD
    A["WebFlux controller"] --> B["Service trả Mono / Flux"]
    B --> C["Reactive repository + Cypher-DSL mixin"]
    C --> D["Reactive SDN operations"]
    D --> E["Reactive Neo4j Driver"]
    E --> F["Neo4j Server"]
~~~

`Mono<T>` biểu diễn không hoặc một phần tử; `Flux<T>` biểu diễn một chuỗi có thể gồm không, một hoặc nhiều phần tử. Chúng là publisher: thao tác truy vấn chỉ thực thi khi publisher được subscribe bởi framework hoặc subscriber ở cuối luồng. Trong service reactive, hãy trả publisher để caller kết hợp tiếp; tránh gọi `.block()` hoặc `.subscribe()` thủ công bên trong luồng nghiệp vụ vì sẽ phá vỡ cách điều phối reactive.

## 2. Chọn reactive repository và đúng mixin

Reactive repository cho entity `Person` có thể khai báo như sau:

~~~java
import org.springframework.data.neo4j.repository.ReactiveNeo4jRepository;
import org.springframework.data.neo4j.repository.support.ReactiveCypherdslConditionExecutor;
import org.springframework.data.neo4j.repository.support.ReactiveCypherdslStatementExecutor;

public interface PersonRepository extends
        ReactiveNeo4jRepository<Person, String>,
        ReactiveCypherdslConditionExecutor<Person>,
        ReactiveCypherdslStatementExecutor<Person> {
}
~~~

Ví dụ gộp hai mixin trong cùng repository để minh họa. Trong ứng dụng, chỉ kế thừa mixin mà use case thực sự cần. `ReactiveNeo4jRepository` cung cấp CRUD reactive cơ bản; `ReactiveCypherdslConditionExecutor` và `ReactiveCypherdslStatementExecutor` bổ sung các method truy vấn được mô tả ở các phần tiếp theo.

Hai mixin imperative có tên gần giống nhưng không thay thế được biến thể reactive. Khi repository kế thừa `ReactiveNeo4jRepository`, hãy dùng `ReactiveCypherdslConditionExecutor` hoặc `ReactiveCypherdslStatementExecutor` tương ứng để nhận các method trả `Mono` và `Flux`.

`ReactiveCypherdslStatementExecutor` được đánh dấu ổn định từ SDN 6.1; `ReactiveCypherdslConditionExecutor` ổn định từ SDN 6.3.3. Kiểm tra phiên bản SDN thực tế của dự án trước khi dùng API, đặc biệt nếu dự án đang ở nhánh cũ hơn các mốc này.

## 3. Biến thể thứ nhất: ReactiveCypherdslConditionExecutor

Condition executor phù hợp khi SDN đã biết cách tạo truy vấn cho entity và ứng dụng chỉ muốn bổ sung điều kiện, sắp xếp hoặc yêu cầu đếm/tồn tại. Mixin này làm việc với `Condition` của Cypher-DSL thay vì yêu cầu ứng dụng tự viết toàn bộ `MATCH` và `RETURN`.

Ví dụ entity:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {
    @Id
    private String id;

    private String name;

    private String status;

    // Constructor, getter và setter được lược bỏ.
}
~~~

Có thể xây dựng điều kiện theo property của node:

~~~java
import org.neo4j.cypherdsl.core.Cypher;
import org.neo4j.cypherdsl.core.Node;

Node person = Cypher.node("Person").named("person");
var activeCondition = person.property("status")
    .isEqualTo(Cypher.anonParameter("ACTIVE"));
~~~

Sau đó gọi repository:

~~~java
Flux<Person> activePeople = personRepository.findAll(activeCondition);
~~~

Điều kiện được ghép vào truy vấn SDN tạo cho `Person`. Tham số giá trị được tạo bằng Cypher-DSL; dùng parameter thay cho ghép chuỗi dữ liệu đầu vào vào biểu thức Cypher.

### Các method reactive của condition executor

| Method | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `findOne(Condition)` | `Mono<T>` | Tìm không hoặc một entity theo điều kiện |
| `findAll(Condition)` | `Flux<T>` | Tìm các entity theo điều kiện |
| `findAll(Condition, Sort)` | `Flux<T>` | Tìm và sắp xếp bằng Spring `Sort` |
| `findAll(Condition, SortItem...)` | `Flux<T>` | Tìm và sắp xếp bằng Cypher-DSL sort items |
| `findAll(SortItem...)` | `Flux<T>` | Lấy entity với thứ tự chỉ định |
| `count(Condition)` | `Mono<Long>` | Đếm entity khớp điều kiện |
| `exists(Condition)` | `Mono<Boolean>` | Kiểm tra có entity khớp điều kiện hay không |

Ví dụ sắp xếp:

~~~java
var nameSort = person.property("name").ascending();
Flux<Person> activePeopleByName =
    personRepository.findAll(activeCondition, nameSort);
~~~

Condition executor chủ yếu trả domain type `T`; API này không cung cấp overload dynamic projection như statement executor. Nếu cần kết quả chỉ gồm vài trường, có thể dùng một truy vấn/projection phù hợp khác hoặc chuyển sang statement executor.

## 4. Biến thể thứ hai: ReactiveCypherdslStatementExecutor

Statement executor phù hợp khi ứng dụng cần toàn quyền xây dựng cấu trúc truy vấn: `MATCH`, relationship pattern, điều kiện, phép thu thập và phần `RETURN`. Repository chỉ nhận một `Statement` đã được dựng bằng Cypher-DSL.

Ví dụ tìm người theo trạng thái và trả về node `Person`: 

~~~java
import org.neo4j.cypherdsl.core.Cypher;
import org.neo4j.cypherdsl.core.Node;
import org.neo4j.cypherdsl.core.Statement;

static Statement findPeopleByStatus(String status) {
    Node person = Cypher.node("Person").named("person");

    return Cypher.match(person)
        .where(person.property("status")
            .isEqualTo(Cypher.anonParameter(status)))
        .returning(person.getRequiredSymbolicName())
        .build();
}
~~~

Gọi statement executor:

~~~java
Flux<Person> people =
    personRepository.findAll(findPeopleByStatus("ACTIVE"));
~~~

Ở đây ứng dụng tự chịu trách nhiệm tạo một statement hoàn chỉnh. `Statement` chứa cả cấu trúc truy vấn và các tham số được khai báo trong Cypher-DSL. Nếu truy vấn cần tham số, hãy tạo named hoặc anonymous parameter trong DSL và cung cấp giá trị tại thời điểm dựng statement; không truyền một map tham số tách rời cho các method executor này.

Ví dụ relationship traversal:

~~~java
static Statement findPeopleAndTeams(String status) {
    Node person = Cypher.node("Person").named("person");
    Node team = Cypher.node("Team").named("team");
    var membership = person.relationshipTo(team, "MEMBER_OF");

    return Cypher.match(membership)
        .where(person.property("status")
            .isEqualTo(Cypher.anonParameter(status)))
        .returning(
            person.getRequiredSymbolicName(),
            Cypher.collect(membership),
            Cypher.collect(team)
        )
        .build();
}
~~~

Khi kết quả cần ánh xạ graph có quan hệ, phần `RETURN` phải cung cấp node và relationship cần thiết cho mapper. Chỉ trả node gốc không đồng nghĩa SDN tự tải mọi tầng quan hệ của graph.

### Các method reactive của statement executor

| Method | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `findOne(Statement)` | `Mono<T>` | Ánh xạ không hoặc đúng một record thành domain type |
| `findOne(Statement, Class<PT>)` | `Mono<PT>` | Ánh xạ không hoặc đúng một record thành projection |
| `findAll(Statement)` | `Flux<T>` | Phát các domain object từ những record truy vấn |
| `findAll(Statement, Class<PT>)` | `Flux<PT>` | Phát các projection từ những record truy vấn |

`findOne` yêu cầu statement trả về không hoặc đúng một record có thể ánh xạ. Nếu truy vấn có thể trả nhiều record, hãy dùng `findAll` hoặc sửa điều kiện truy vấn để bảo đảm tính duy nhất theo nghiệp vụ. Không dùng `findOne` như một cách ngầm chọn tùy ý một kết quả trong tập nhiều dòng.

## 5. Dynamic projection với statement executor

Statement executor hỗ trợ chọn kiểu projection ngay tại lời gọi. Ví dụ interface projection:

~~~java
public interface PersonNameView {
    String getId();
    String getName();
}
~~~

Statement chỉ trả node và projection được chọn:

~~~java
Flux<PersonNameView> names = personRepository.findAll(
    findPeopleByStatus("ACTIVE"),
    PersonNameView.class
);
~~~

Với một kết quả đơn, dùng `findOne(statement, projectionClass)` và nhận `Mono<PT>`. Kiểu projection cần phù hợp với dữ liệu mà statement trả về. Khi projection cần các property của entity, phần `RETURN` phải chứa dữ liệu tương ứng; khi cần giá trị tổng hợp hoặc cấu trúc tùy biến, hãy kiểm tra rõ khả năng ánh xạ của projection và cân nhắc `ReactiveNeo4jClient` nếu cần tự chuyển record thành DTO.

## 6. Condition executor và statement executor khác nhau thế nào?

| Tiêu chí | Reactive condition executor | Reactive statement executor |
| --- | --- | --- |
| Đầu vào | `Condition` và tùy chọn sort | Một `Statement` Cypher-DSL hoàn chỉnh |
| Phần truy vấn do ai xây dựng? | SDN tạo truy vấn entity; ứng dụng thêm điều kiện/sắp xếp | Ứng dụng xây dựng `MATCH`, `WHERE`, `RETURN` và các phần cần thiết |
| Kết quả | Domain type `T` | Domain type `T` hoặc projection `PT` |
| Method đơn | `findOne` trả `Mono<T>` | `findOne` trả `Mono<T>` hoặc `Mono<PT>` |
| Method nhiều kết quả | `findAll` trả `Flux<T>` | `findAll` trả `Flux<T>` hoặc `Flux<PT>` |
| Đếm và tồn tại | Có `count` và `exists` | Không có method tương ứng trong mixin này |
| Sắp xếp | Có overload `Sort` và `SortItem` | Thể hiện trong chính `Statement` |
| Phân trang | Không có `Pageable`/`Page` trong các method condition được liệt kê | Không có overload paged result trong reactive statement executor |

Chọn condition executor khi chỉ cần thêm predicate vào truy vấn SDN đã biết cách ánh xạ entity. Chọn statement executor khi cấu trúc truy vấn biến đổi nhiều hoặc cần traversal, aggregation và projection riêng. Không trộn hai kiểu API chỉ để có nhiều method hơn; chọn theo phần truy vấn mà use case cần kiểm soát.

## 7. Giới hạn phân trang và xử lý luồng lớn

Reactive statement executor trả `Flux`, nhưng `Flux` không đồng nghĩa truy vấn đã được phân trang ở database. Các method `findAll` phát nhiều kết quả; bản thân mixin này không có overload nhận `Pageable` hoặc trả `Page` như một số imperative API.

Nếu cần giới hạn dữ liệu, hãy đưa `ORDER BY` và `LIMIT` vào statement Cypher-DSL. Ví dụ:

~~~java
static Statement firstPeople(int limit) {
    Node person = Cypher.node("Person").named("person");
    return Cypher.match(person)
        .returning(person.getRequiredSymbolicName())
        .orderBy(person.property("name").ascending())
        .limit(Cypher.parameter("limit", limit))
        .build();
}

Flux<Person> firstPage = personRepository.findAll(firstPeople(50));
~~~

Đoạn mã minh họa việc giới hạn ngay trong câu query. Với phân trang sâu trên dữ liệu lớn, cân nhắc keyset pagination và cursor như một phần của điều kiện Cypher, thay vì dùng offset lớn. Khi tiêu thụ `Flux`, có thể dùng `take`, `buffer` hoặc `limitRate` để điều tiết downstream, nhưng các operator này không thay thế `LIMIT` tại database nếu mục tiêu là giảm số record Neo4j phải tạo và truyền.

## 8. Reactive transaction và cách tiêu thụ publisher

Trong reactive application, transaction cần được quản lý bằng reactive transaction infrastructure của Spring. Có thể đặt `@Transactional` trên phương thức service trả `Mono` hoặc `Flux` để các thao tác reactive tham gia transaction phù hợp:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class PersonService {
    private final PersonRepository repository;

    public PersonService(PersonRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Mono<Person> findOne(Statement statement) {
        return repository.findOne(statement);
    }
}
~~~

Không gọi `.block()` bên trong service reactive để chờ kết quả trước khi tiếp tục; hãy kết hợp publisher bằng `map`, `flatMap`, `zip`, `then` hoặc các operator phù hợp. Cũng không gọi `.subscribe()` thủ công trong repository/service để “kích hoạt” truy vấn; framework WebFlux hoặc tầng tiêu thụ cuối cùng sẽ subscribe.

Nếu một nghiệp vụ cần nhiều thao tác ghi, hãy kết hợp chúng trong cùng reactive transaction và bảo đảm publisher được trả về từ phương thức transactional. Đoạn code tạo publisher nhưng không đưa nó vào chuỗi trả về có thể khiến thao tác không được thực thi trong transaction mong đợi.

## 9. Khi nào dùng ReactiveNeo4jClient thay vì repository mixin?

Hai mixin trên tập trung vào việc ánh xạ kết quả về domain type hoặc projection. Nếu truy vấn cần một cấu trúc record tùy biến, map động, hoặc DTO không phù hợp với entity projection, có thể dùng `ReactiveNeo4jClient` để thực thi Cypher và tự ánh xạ record.

Ví dụ ý tưởng:

~~~java
import org.springframework.data.neo4j.core.ReactiveNeo4jClient;
import reactor.core.publisher.Mono;

public record PersonNameDto(String id, String name) {}

public class PersonLookup {
    private final ReactiveNeo4jClient reactiveNeo4jClient;

    public PersonLookup(ReactiveNeo4jClient reactiveNeo4jClient) {
        this.reactiveNeo4jClient = reactiveNeo4jClient;
    }

    public Mono<PersonNameDto> findActivePerson(String personId) {
        return reactiveNeo4jClient.query("""
                MATCH (person:Person {status: $status})
                WHERE person.id = $personId
                RETURN person.id AS id, person.name AS name
                """)
            .bind("ACTIVE").to("status")
            .bind(personId).to("personId")
            .fetchAs(PersonNameDto.class)
            .mappedBy((typeSystem, record) -> new PersonNameDto(
                record.get("id").asString(),
                record.get("name").asString()
            ))
            .one();
    }
}
~~~

`ReactiveNeo4jClient` là API truy vấn reactive cấp thấp hơn repository mixin. Dùng nó khi cần kiểm soát việc đọc record/DTO; dùng statement executor khi muốn giữ Cypher-DSL và tận dụng entity mapping/projection tích hợp sẵn. Với DTO phức tạp, có thể dùng `mappedBy` để chuyển record theo quy tắc cụ thể của ứng dụng. Ví dụ trên minh họa ánh xạ tường minh và giả định `id`, `name` luôn có giá trị.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy method reactive | Repository kế thừa mixin imperative | Dùng `ReactiveCypherdslConditionExecutor` hoặc `ReactiveCypherdslStatementExecutor` |
| Method trả kiểu không đúng | Dùng `List`/`Optional` trong reactive flow | Dùng `Flux` cho nhiều kết quả, `Mono` cho không hoặc một kết quả |
| `findOne` thất bại khi có nhiều dòng | Statement không bảo đảm tối đa một record | Dùng `findAll` hoặc ràng buộc truy vấn để có tối đa một dòng |
| Projection thiếu property | `RETURN` không cung cấp dữ liệu mà projection cần | Kiểm tra phần `RETURN` và kiểu projection |
| Parameter không được bind | Giá trị chưa được khai báo/populate trong Cypher-DSL statement | Dùng `Cypher.parameter` hoặc `Cypher.anonParameter` với giá trị |
| Truy vấn lấy quá nhiều dữ liệu | Dùng `findAll` mà không giới hạn query | Thêm `LIMIT`, lọc và projection trong statement |
| Reactive pipeline bị block | Gọi `.block()` hoặc subscribe thủ công trong service | Kết hợp và trả publisher xuyên suốt luồng reactive |
| Cần Page nhưng không có overload | Nhầm API reactive statement với imperative statement executor | Tự xây dựng `LIMIT`/cursor trong Cypher hoặc dùng cách phân trang phù hợp |

## 11. Quy trình chọn API

1. Nếu cần truy vấn CRUD reactive thông thường, bắt đầu với `ReactiveNeo4jRepository`.
2. Nếu SDN đã sinh truy vấn entity và chỉ cần thêm điều kiện hoặc sort, thêm `ReactiveCypherdslConditionExecutor`.
3. Nếu cần xây dựng đầy đủ statement bằng Cypher-DSL, thêm `ReactiveCypherdslStatementExecutor`.
4. Nếu cần `count` hoặc `exists` dựa trên condition, dùng condition executor.
5. Nếu cần dynamic projection từ statement, dùng overload `findOne`/`findAll` có `Class<PT>`.
6. Nếu cần record mapping hoàn toàn tùy chỉnh, cân nhắc `ReactiveNeo4jClient`.
7. Nếu cần phân trang, hãy xác định rõ `LIMIT`/cursor trong query; đừng giả định `Flux` tự phân trang.

## 12. Bài tập tự kiểm tra

1. Vì sao repository reactive cần `ReactiveCypherdslStatementExecutor` thay cho `CypherdslStatementExecutor`?
2. Khi nào condition executor phù hợp hơn statement executor?
3. Nêu kiểu trả về của `findOne`, `findAll`, `count` và `exists` trong reactive condition executor.
4. Statement executor hỗ trợ những overload projection nào?
5. Vì sao `findOne(Statement)` yêu cầu tối đa một record?
6. Tại sao `Flux<T>` không đồng nghĩa với phân trang ở database?
7. Khi nào nên dùng `ReactiveNeo4jClient` thay vì repository mixin?
8. Vì sao không nên gọi `.block()` hoặc `.subscribe()` trong service reactive?

Khi hoàn thành bài học, bạn cần chọn đúng reactive Cypher-DSL mixin theo mức độ kiểm soát truy vấn, biết tập method mà từng API hỗ trợ và xây dựng luồng `Mono`/`Flux` không chặn. Đây là nền tảng để sử dụng Cypher-DSL trong các ứng dụng Spring Data Neo4j reactive một cách rõ ràng và có kiểm soát.

## Tài liệu tham khảo

- [Spring Data Neo4j – Extensions](https://docs.spring.io/spring-data/neo4j/reference/repositories/sdn-extension.html)
- [ReactiveCypherdslStatementExecutor API](https://docs.spring.io/spring-data/data-neo4j/reference/api/java/org/springframework/data/neo4j/repository/support/ReactiveCypherdslStatementExecutor.html)
- [ReactiveCypherdslConditionExecutor API](https://docs.spring.io/spring-data/neo4j/docs/8.1.x/api/org/springframework/data/neo4j/repository/support/ReactiveCypherdslConditionExecutor.html)
