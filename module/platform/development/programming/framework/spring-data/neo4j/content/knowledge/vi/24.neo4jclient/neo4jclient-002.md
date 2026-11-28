# Thực thi Cypher bằng query và bind tham số

`Neo4jClient` là API của Spring Data Neo4j (SDN) nằm trên Neo4j Java Driver. Nó cho phép chạy Cypher trực tiếp, truyền tham số theo tên, đọc kết quả dưới dạng record hoặc map và tự ánh xạ kết quả thành kiểu Java. Client đặc biệt hữu ích khi repository method hoặc entity mapping tiêu chuẩn không diễn tả đủ một truy vấn nghiệp vụ.

So với việc tự mở session bằng Java Driver, `Neo4jClient` tích hợp với transaction management của Spring và cung cấp API fluent thống nhất cho việc khai báo query, bind tham số và đọc kết quả. Ứng dụng Spring Boot thường đã có bean client được cấu hình sẵn, vì vậy service có thể inject trực tiếp thay vì tự tạo Driver hoặc Client mới.

## 1. Neo4jClient nằm ở đâu trong kiến trúc?

Repository phù hợp với các thao tác gắn với entity và các truy vấn có hợp đồng ổn định. `Neo4jClient` phù hợp khi cần viết Cypher cụ thể, trả về dữ liệu tổng hợp, map, DTO hoặc kết quả không phải entity. Client vẫn sử dụng Neo4j Driver để giao tiếp với server.

~~~mermaid
flowchart TD
    A["Application service"] --> B["Neo4jClient"]
    B --> C["Spring transaction integration"]
    B --> D["Neo4j Java Driver"]
    D --> E["Neo4j Server"]
~~~

Hai biến thể client có cùng cách dùng tổng quát nhưng không tương thích API với nhau:

| Client | Mô hình xử lý | Kết quả thường gặp |
| --- | --- | --- |
| `Neo4jClient` | Imperative, thực thi khi gọi terminal operation | `Optional`, `Collection`, `ResultSummary` |
| `ReactiveNeo4jClient` | Reactive, truy vấn thực thi khi publisher được subscribe | `Mono`, `Flux` |

Không trộn hai biến thể trong cùng một chuỗi gọi. Chọn client phù hợp với stack imperative hoặc reactive của ứng dụng.

## 2. Inject client vào service

Với Spring Boot và starter Neo4j được cấu hình, thông thường có thể inject `Neo4jClient` trực tiếp:

~~~java
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;

@Service
public class PersonQueryService {
    private final Neo4jClient neo4jClient;

    public PersonQueryService(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }
}
~~~

Nếu tự tạo client, cần dùng cùng instance `Driver` với `Neo4jTransactionManager` khi muốn các truy vấn client tham gia transaction Spring. Tạo client từ một Driver khác có thể khiến thao tác không đồng bộ với transaction đang quản lý. Trong ứng dụng Boot thông thường, hãy ưu tiên bean được auto-configure.

## 3. Khai báo câu query

Bắt đầu bằng `query(String)` với câu Cypher có named parameter:

~~~java
var result = neo4jClient.query("""
    MATCH (person:Person {id: $personId})
    RETURN person.id AS id, person.name AS name
    """);
~~~

Tên tham số được đặt sau ký hiệu `$`, ví dụ `$personId`. Phần tên tham số trong Cypher phải khớp với tên được bind trong Java. Named parameter giúp câu truy vấn dễ đọc và tách giá trị đầu vào khỏi cấu trúc Cypher.

Client cũng hỗ trợ `query(Supplier<String>)`. Supplier được gọi muộn khi cần tạo câu query, hữu ích khi câu lệnh được dựng từ query builder hoặc Cypher-DSL. Dù dùng chuỗi hay Supplier, các giá trị đầu vào vẫn nên được truyền qua bind API.

Nếu ứng dụng dùng nhiều database, có thể chọn database đích bằng `.in("databaseName")` sau khi khai báo query:

~~~java
var rows = neo4jClient.query("MATCH (person:Person) RETURN person")
    .in("people")
    .fetch()
    .all();
~~~

Nếu không gọi `.in(...)`, client sử dụng database mặc định của kết nối. Tên database phải đến từ cấu hình đáng tin cậy của ứng dụng; không lấy tùy ý từ request mà không kiểm tra quyền.

## 4. Bind một tham số đơn giản

Cách phổ biến nhất là gọi `.bind(value).to("parameterName")` cho từng tham số:

~~~java
import java.util.Map;
import java.util.Optional;

public Optional<Map<String, Object>> findPerson(String personId) {
    return neo4jClient.query("""
            MATCH (person:Person {id: $personId})
            RETURN person.id AS id, person.name AS name
            """)
        .bind(personId).to("personId")
        .fetch()
        .one();
}
~~~

Tên truyền vào `to("personId")` không có ký hiệu `$`. Giá trị `personId` được truyền riêng khỏi câu query, vì vậy ký tự đặc biệt trong giá trị không thể làm thay đổi cấu trúc Cypher.

Các kiểu đơn giản mà Neo4j Java Driver hỗ trợ có thể được bind trực tiếp, chẳng hạn chuỗi, boolean, số, kiểu ngày giờ, danh sách và map có giá trị hợp lệ. Khả năng chuyển đổi cuối cùng tuân theo các kiểu dữ liệu được Driver và Neo4j hỗ trợ.

### Bind nhiều tham số cùng lúc

Nếu có nhiều giá trị, dùng `bindAll(Map<String, Object>)`: 

~~~java
import java.util.Map;

Map<String, Object> parameters = Map.of(
    "status", "ACTIVE",
    "minimumAge", 18L
);

var rows = neo4jClient.query("""
        MATCH (person:Person)
        WHERE person.status = $status
          AND person.age >= $minimumAge
        RETURN person.id AS id, person.name AS name
        ORDER BY person.name
        """)
    .bindAll(parameters)
    .fetch()
    .all();
~~~

Key của map phải trùng tên named parameter trong Cypher và không có ký hiệu `$`. `bindAll` hữu ích khi tham số được chuẩn bị từ một object filter hoặc được gom trong service.

Client ngăn việc bind trùng cùng một tên tham số, nhưng không tự kiểm tra đầy đủ rằng mọi placeholder trong query đã được bind hoặc map không có key thừa. Driver sẽ báo lỗi khi query thực thi nếu tham số bắt buộc còn thiếu hoặc giá trị không hợp lệ. Hãy kiểm tra hợp đồng giữa query và map ngay trong code và kiểm thử các nhánh điều kiện.

## 5. Bind object miền bằng mapping function

Nếu đầu vào là một object Java phức tạp, không nên giả định Driver có thể chuyển trực tiếp mọi object thành parameter. Dùng `.bind(object).with(mappingFunction)` để chuyển object thành `Map<String, Object>` chứa những named parameter mà query cần.

Ví dụ object lệnh tạo người và các kỹ năng:

~~~java
import java.util.List;

public record CreatePersonCommand(
    String id,
    String name,
    List<String> skills
) {}
~~~

Query sử dụng `$id`, `$name` và `$skills`; mapping function tạo map tương ứng:

~~~java
import java.util.HashMap;
import java.util.Map;
import org.neo4j.driver.summary.ResultSummary;

public ResultSummary createPerson(CreatePersonCommand command) {
    return neo4jClient.query("""
            MERGE (person:Person {id: $id})
            SET person.name = $name
            WITH person
            UNWIND $skills AS skillName
            MERGE (skill:Skill {name: skillName})
            MERGE (person)-[:HAS_SKILL]->(skill)
            """)
        .bind(command).with(value -> {
            Map<String, Object> values = new HashMap<>();
            values.put("id", value.id());
            values.put("name", value.name());
            values.put("skills", value.skills());
            return values;
        })
        .run();
}
~~~

Mapping function cần cung cấp các named parameter mà query sử dụng. Ví dụ này giả định các trường không null và danh sách kỹ năng đã được kiểm tra ở tầng nghiệp vụ. Nếu danh sách rỗng, `UNWIND []` không tạo dòng tiếp theo; node `Person` vẫn được MERGE và cập nhật trước bước `UNWIND`.

Chỉ đưa các giá trị cần thiết vào parameter map. Không serialize toàn bộ object graph tùy ý rồi gửi xuống Driver; các entity có quan hệ, object lồng nhau hoặc kiểu domain riêng cần được chuyển đổi có chủ đích.

## 6. Đọc kết quả bằng fetch()

Sau khi khai báo query và bind tham số, gọi `fetch()` rồi chọn cách lấy kết quả:

| Terminal operation | Kết quả imperative | Ý nghĩa |
| --- | --- | --- |
| `one()` | `Optional<T>` | Mong đợi chính xác một record |
| `first()` | `Optional<T>` | Lấy record đầu tiên nếu có |
| `all()` | `Collection<T>` | Lấy toàn bộ record |

Ví dụ lấy một record dưới dạng map:

~~~java
Optional<Map<String, Object>> person = neo4jClient.query("""
        MATCH (p:Person {id: $id})
        RETURN p.id AS id, p.name AS name
        """)
    .bind(personId).to("id")
    .fetch()
    .one();
~~~

Mỗi map tương ứng với một record mà Cypher trả về; key là tên cột hoặc alias trong phần `RETURN`. Với truy vấn có nhiều dòng, dùng `all()`. Dùng `first()` chỉ khi nghiệp vụ chấp nhận lấy một kết quả đầu tiên và query có thứ tự xác định nếu thứ tự có ý nghĩa.

`one()` phù hợp khi điều kiện truy vấn bảo đảm một kết quả duy nhất, chẳng hạn tìm theo ID đã có uniqueness constraint. Nếu query có thể trả nhiều record, hãy dùng `all()` hoặc sửa điều kiện truy vấn; không dựa vào `one()` để chọn ngẫu nhiên một dòng.

## 7. Ánh xạ record thành DTO với fetchAs()

Khi kết quả có cấu trúc cố định, có thể dùng DTO thay cho `Map<String, Object>`. Khai báo kiểu kết quả:

~~~java
public record PersonSummary(String id, String name) {}
~~~

Dùng `fetchAs()` để chọn kiểu và `mappedBy()` để chuyển từng record:

~~~java
import java.util.Optional;
import org.neo4j.driver.Record;
import org.neo4j.driver.types.TypeSystem;

public Optional<PersonSummary> findSummary(String personId) {
    return neo4jClient.query("""
            MATCH (person:Person {id: $personId})
            RETURN person.id AS id, person.name AS name
            """)
        .bind(personId).to("personId")
        .fetchAs(PersonSummary.class)
        .mappedBy((TypeSystem typeSystem, Record record) ->
            new PersonSummary(
                record.get("id").asString(),
                record.get("name").asString()
            )
        )
        .one();
}
~~~

`mappedBy` nhận một hàm với `TypeSystem` và `Record`. `TypeSystem` cung cấp thông tin kiểu của Driver; `Record` cho phép đọc các cột theo alias. Alias `id` và `name` trong Cypher phải khớp với key mà mapper đọc.

Nếu một property có thể null, kiểm tra trước khi chuyển kiểu. Ví dụ `record.get("email").isNull()` cho biết giá trị vắng mặt; không gọi `asString()` một cách mù quáng với trường có thể null. Với danh sách hoặc map lồng nhau, dùng các phương thức chuyển đổi như `asList(...)` và ánh xạ từng phần tử theo kiểu mong muốn.

`fetchAs()` không tự biến một map kết quả tùy ý thành entity SDN. Hàm `mappedBy` là nơi ứng dụng định nghĩa rõ cách tạo đối tượng. Nếu kết quả có node đã được mô hình hóa bằng `@Node`, có thể dùng `Neo4jMappingContext` để lấy mapping function tương ứng và tái sử dụng quy tắc ánh xạ của SDN.

## 8. Thực thi lệnh ghi bằng run()

Nếu query không cần trả về các record mà chỉ cần thực hiện lệnh ghi, dùng `run()`. Với imperative client, kết quả là `ResultSummary`, chứa counters và thông tin thực thi:

~~~java
import org.neo4j.driver.summary.ResultSummary;

public long renamePerson(String personId, String newName) {
    ResultSummary summary = neo4jClient.query("""
            MATCH (person:Person {id: $personId})
            SET person.name = $newName
            """)
        .bind(personId).to("personId")
        .bind(newName).to("newName")
        .run();

    return summary.counters().propertiesSet();
}
~~~

`propertiesSet()` cho biết số property được đặt theo counters của kết quả. Nếu cần biết node có tồn tại hay không hoặc muốn trả dữ liệu sau cập nhật, hãy thêm `RETURN` và dùng `fetch()` thay vì chỉ gọi `run()`.

Một lệnh `CREATE`, `MERGE`, `SET` hoặc `DELETE` không cần record kết quả thường là trường hợp phù hợp cho `run()`. Đừng dùng `run()` nếu caller cần đọc các cột mà query đã trả về.

## 9. Chạy query trong transaction Spring

Một lợi ích quan trọng của `Neo4jClient` là tích hợp với transaction management của Spring. Có thể đặt thao tác client trong service có `@Transactional` để nhiều truy vấn tham gia cùng một đơn vị công việc:

~~~java
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonCommandService {
    private final Neo4jClient neo4jClient;

    public PersonCommandService(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    @Transactional
    public void updatePersonAndAudit(String personId, String newName) {
        neo4jClient.query("""
                MATCH (person:Person {id: $id})
                SET person.name = $name
                """)
            .bind(personId).to("id")
            .bind(newName).to("name")
            .run();

        neo4jClient.query("""
                MATCH (person:Person {id: $id})
                CREATE (person)-[:HAS_AUDIT]->(:AuditEvent {
                    action: "RENAMED",
                    createdAt: datetime()
                })
                """)
            .bind(personId).to("id")
            .run();
    }
}
~~~

Khi hai truy vấn tham gia cùng transaction manager và cùng cấu hình Driver, nếu thao tác sau thất bại thì transaction có thể rollback cả thay đổi trước đó theo quy tắc rollback của Spring. Không mở một Driver/session độc lập bên trong service nếu muốn dùng chung transaction.

Đối với thao tác chỉ đọc, có thể dùng `@Transactional(readOnly = true)` nếu phù hợp. Annotation transaction không thay thế kiểm tra quyền truy cập và không làm cho một query sai dữ liệu trở nên đúng.

## 10. ReactiveNeo4jClient: cùng ý tưởng, publisher khác

Với ứng dụng reactive, inject `ReactiveNeo4jClient` và bind tham số theo cùng vocabulary:

~~~java
import org.springframework.data.neo4j.core.ReactiveNeo4jClient;
import reactor.core.publisher.Mono;

public class ReactivePersonQueryService {
    private final ReactiveNeo4jClient client;

    public ReactivePersonQueryService(ReactiveNeo4jClient client) {
        this.client = client;
    }

    public Mono<PersonSummary> findSummary(String personId) {
        return client.query("""
                MATCH (person:Person {id: $personId})
                RETURN person.id AS id, person.name AS name
                """)
            .bind(personId).to("personId")
            .fetchAs(PersonSummary.class)
            .mappedBy((typeSystem, record) -> new PersonSummary(
                record.get("id").asString(),
                record.get("name").asString()
            ))
            .one();
    }
}
~~~

Reactive client trả `Mono` hoặc `Flux`; query chỉ được thực thi khi publisher được subscribe. Hãy trả publisher về tầng gọi và kết hợp bằng `map`, `flatMap`, `zip` hoặc operator phù hợp. Không gọi `.block()` trong service reactive để ép kết quả thành đồng bộ.

## 11. An toàn khi bind tham số và dựng query động

Luôn bind giá trị đầu vào bằng named parameter. Ví dụ an toàn:

~~~java
neo4jClient.query("MATCH (p:Person {name: $name}) RETURN p")
    .bind(userSuppliedName).to("name")
    .fetch()
    .all();
~~~

Tránh nối chuỗi dữ liệu người dùng vào query:

~~~java
// Không làm như vậy
String cypher = "MATCH (p:Person {name: '" + userSuppliedName + "'}) RETURN p";
~~~

Bind parameter dùng cho giá trị, không thay thế được tên label, relationship type, property key hoặc từ khóa sắp xếp. Nếu query cần chọn một trong nhiều label hoặc hướng sort, hãy whitelist lựa chọn hợp lệ rồi dùng query/template tương ứng. Không cho client tự đưa một đoạn Cypher tùy ý vào câu lệnh.

Các nguyên tắc thực hành:

- Bind mọi giá trị đầu vào bằng `$parameter` và `.bind(...).to(...)` hoặc `.bindAll(...)`.
- Không ghép chuỗi user input vào literal Cypher.
- Kiểm tra kiểu và kích thước danh sách/map trước khi bind.
- Giới hạn quyền truy cập theo nghiệp vụ ở service và theo tài khoản Neo4j.
- Chọn đúng database đích và không để người dùng tự do thay đổi database.
- Không ghi mật khẩu hoặc token vào query string hay log.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Driver báo thiếu parameter | Placeholder `$name` chưa được bind | Đối chiếu toàn bộ placeholder với tên trong `.to(...)` và `bindAll` |
| Parameter không hợp lệ | Giá trị Java không được Driver hỗ trợ hoặc map có kiểu lồng nhau không hợp lệ | Chuyển thành kiểu scalar/list/map được Neo4j hỗ trợ |
| `one()` báo nhiều kết quả | Query không bảo đảm một record | Dùng `all()` hoặc sửa điều kiện/constraint để bảo đảm duy nhất |
| Mapper không đọc được cột | Alias trong `RETURN` không khớp key mapper truy cập | Đặt alias ổn định và kiểm tra record |
| Giá trị null gây lỗi chuyển kiểu | Gọi `asString()`/`asLong()` trên giá trị null | Kiểm tra `isNull()` và xử lý null theo nghiệp vụ |
| Query chạy ngoài transaction mong đợi | Dùng Driver khác với transaction manager hoặc tự mở session | Dùng client bean chia sẻ cùng Driver và Spring transaction |
| Query động dễ bị injection | Ghép trực tiếp input vào chuỗi Cypher | Dùng bind parameter cho giá trị và whitelist phần cấu trúc |

## 13. Quy trình chọn terminal operation

1. Xác định query cần trả record hay chỉ cần thực thi lệnh.
2. Nếu cần dữ liệu, chọn `fetch().one()`, `fetch().first()` hoặc `fetch().all()` theo cardinality.
3. Nếu cần kiểu kết quả cố định, dùng `fetchAs(Type.class).mappedBy(...)`.
4. Nếu query chỉ ghi và cần summary/counters, dùng `run()`.
5. Bind đầy đủ các tham số và kiểm tra alias của mọi cột kết quả.
6. Đặt các query cần tính nguyên tử trong transaction service phù hợp.
7. Kiểm thử trường hợp không có kết quả, nhiều kết quả, null và tham số không hợp lệ.

## 14. Bài tập tự kiểm tra

1. `Neo4jClient` khác việc dùng trực tiếp Neo4j Java Driver ở điểm nào trong ứng dụng Spring?
2. Viết query tìm `Person` theo ID và bind giá trị `personId` bằng fluent API.
3. Khi nào nên dùng `bindAll(Map<String, Object>)` thay vì bind từng tham số?
4. `.bind(object).with(...)` giải quyết vấn đề gì khi object Java không phải kiểu Driver hỗ trợ trực tiếp?
5. Phân biệt `fetch().one()`, `fetch().first()` và `fetch().all()`.
6. Khi nào dùng `fetchAs(...).mappedBy(...)` thay cho `Map<String, Object>`?
7. Vì sao lệnh ghi không cần record nên kết thúc bằng `run()`?
8. Điều kiện nào cần được bảo đảm để Neo4jClient tham gia transaction Spring?
9. Vì sao bind parameter không thể thay thế label hoặc property key động?

Khi hoàn thành bài học, bạn cần có thể khai báo Cypher bằng `query`, bind giá trị an toàn, chọn cách lấy kết quả phù hợp và tự ánh xạ DTO khi cần. Bạn cũng cần hiểu cách Neo4jClient tham gia transaction Spring để sử dụng truy vấn tùy chỉnh trong tầng dữ liệu đồ thị một cách có kiểm soát.

## Tài liệu tham khảo

- [Spring Data Neo4j – Neo4jClient](https://docs.spring.io/spring-data/neo4j/reference/appendix/neo4j-client.html)
- [Neo4j Java Driver – Values and parameters](https://neo4j.com/docs/java-manual/current/query-simple/)
