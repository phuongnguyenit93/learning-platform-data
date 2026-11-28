# Dùng Neo4jTemplate cho entity và Neo4jClient cho kết quả riêng

Khi mở rộng Spring Data Neo4j repository, có những truy vấn vẫn trả về entity thuộc mô hình domain, nhưng cũng có truy vấn trả về dữ liệu báo cáo hoặc kết quả tổng hợp không tương ứng với một node. Chọn đúng API cho từng loại kết quả giúp code dễ đọc và giữ đúng cơ chế ánh xạ.

`Neo4jTemplate` phù hợp khi truy vấn tùy chỉnh vẫn cần trả về entity đã được ánh xạ theo metadata của Spring Data Neo4j. `Neo4jClient` phù hợp khi kết quả có hình dạng riêng, chẳng hạn một DTO chứa tên node, loại relationship hoặc giá trị tổng hợp. Hai API có thể được dùng trong cùng một custom repository fragment và đều tích hợp với transaction management của Spring.

## 1. Phân biệt hai cấp độ truy cập

Spring Data Neo4j cung cấp nhiều cách truy cập dữ liệu. Repository xử lý CRUD và các truy vấn phổ biến; custom repository fragment bổ sung hành vi chuyên biệt; bên dưới các lớp đó, `Neo4jTemplate` và `Neo4jClient` giải quyết hai nhu cầu khác nhau.

| Tiêu chí | `Neo4jTemplate` | `Neo4jClient` |
|---|---|---|
| Trọng tâm | Entity và mô hình domain đã ánh xạ | Record và kết quả truy vấn tùy chỉnh |
| Đầu vào | ID, domain type, Cypher hoặc statement Cypher-DSL cùng tham số | Câu Cypher cùng tham số |
| Đầu ra | Entity/domain type được SDN ánh xạ | Map theo alias hoặc kiểu do ứng dụng tự ánh xạ |
| Mapping | Dùng metadata entity, converter và quy tắc relationship mapping của SDN | Ứng dụng kiểm soát mapping qua `fetchAs(...).mappedBy(...)` |
| Phù hợp | Custom query trả về entity đầy đủ | DTO, projection phẳng, thống kê hoặc dữ liệu không phải entity |
| Transaction | Tham gia transaction Spring | Tích hợp transaction management của Spring |

Quy tắc lựa chọn đơn giản: nếu kết quả là `Movie`, `Person` hoặc một entity khác cần được SDN quản lý, hãy cân nhắc `Neo4jTemplate`. Nếu kết quả là `RelationSummary`, `DashboardRow` hoặc một cấu trúc chỉ phục vụ đọc, hãy cân nhắc `Neo4jClient`.

## 2. Tổ chức custom repository bằng fragment

Một custom repository fragment gồm interface khai báo chức năng và class triển khai. Repository chính kế thừa fragment interface để ghép chức năng đó với CRUD có sẵn.

Giả sử ứng dụng có entity phim:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Movie")
public class Movie {

    @Id
    private String title;

    private String tagline;

    // constructors, getters and setters
}
```

Và entity người:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String personId;

    private String name;

    // constructors, getters and setters
}
```

Khai báo fragment interface với hai loại kết quả:

```java
import java.util.Collection;
import java.util.List;

import org.springframework.transaction.annotation.Transactional;

public interface MovieSearchFragment {

    @Transactional(readOnly = true)
    List<Movie> findMoviesForPeople(Collection<String> personIds);

    @Transactional(readOnly = true)
    Collection<RelationSummary> findRelationsToMovie(String title);
}
```

`findMoviesForPeople` trả về entity `Movie`; `findRelationsToMovie` trả về DTO `RelationSummary`. Hai phương thức có thể cùng nằm trong một fragment vì chúng cùng phục vụ nhóm chức năng tìm kiếm phim.

Repository chính chỉ cần kế thừa fragment:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface MovieRepository
        extends Neo4jRepository<Movie, String>, MovieSearchFragment {
}
```

Spring Data Neo4j ghép fragment implementation vào repository khi khởi tạo. Theo quy ước mặc định, class triển khai có tên là tên fragment cộng hậu tố `Impl`, ở đây là `MovieSearchFragmentImpl`.

## 3. Dùng Neo4jTemplate khi kết quả là entity

Giả sử cần tìm các phim có người tham gia nằm trong danh sách `personIds`. Truy vấn tùy chỉnh vẫn trả về node `Movie`, nên có thể dùng `Neo4jTemplate` để SDN ánh xạ kết quả theo entity metadata:

```java
import org.springframework.data.neo4j.core.Neo4jClient;
import java.util.Collection;
import java.util.List;
import java.util.Map;

import org.springframework.data.neo4j.core.Neo4jTemplate;

class MovieSearchFragmentImpl implements MovieSearchFragment {

    private final Neo4jTemplate neo4jTemplate;
    private final Neo4jClient neo4jClient;

    MovieSearchFragmentImpl(
            Neo4jTemplate neo4jTemplate,
            Neo4jClient neo4jClient) {
        this.neo4jTemplate = neo4jTemplate;
        this.neo4jClient = neo4jClient;
    }

    @Override
    public List<Movie> findMoviesForPeople(Collection<String> personIds) {
        String query = """
            MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
            WHERE p.personId IN $personIds
            RETURN DISTINCT m
            ORDER BY m.title
            """;

        Map<String, Object> parameters = Map.of("personIds", personIds);
        return neo4jTemplate.findAll(query, parameters, Movie.class);
    }

    // Phương thức Neo4jClient được trình bày ở phần tiếp theo.
}
```

`findAll(query, parameters, Movie.class)` yêu cầu template thực thi Cypher rồi ánh xạ node trả về thành `Movie`. Các converter, định danh và metadata của entity được SDN sử dụng theo cấu hình hiện tại.

Trong ví dụ, `RETURN DISTINCT m` trả node phim để mapping. Nếu cần nạp thêm relationship của `Movie`, truy vấn phải trả đủ node và relationship cần cho graph mapping. Không nên lấy một entity chỉ được nạp một phần rồi dùng nó làm trạng thái đầy đủ để ghi lại, vì các relationship không được hydrate có thể bị xóa hoặc ghi đè ngoài ý muốn.

Nếu đầu vào `personIds` có thể rỗng, hãy xử lý trường hợp đó trước khi gọi template, ví dụ trả về `List.of()`. Điều này giúp tránh chạy truy vấn không cần thiết và làm rõ ý nghĩa của danh sách rỗng trong API.

## 4. Dùng Neo4jClient khi kết quả không phải entity

Giả sử cần biết những người có relationship với một phim và loại relationship tương ứng. Kết quả không phải một node `Person` hay `Movie`; mỗi dòng là một cặp `name` và `relationshipType`.

Định nghĩa DTO:

```java
public record RelationSummary(
    String name,
    String relationshipType
) {}
```

Triển khai phương thức bằng `Neo4jClient`:

```java
import org.springframework.data.neo4j.core.Neo4jClient;

@Override
public Collection<RelationSummary> findRelationsToMovie(String title) {
    return neo4jClient.query("""
        MATCH (people:Person)-[relatedTo]-(:Movie {title: $title})
        RETURN people.name AS name,
               type(relatedTo) AS relationshipType
        ORDER BY name, relationshipType
        """)
        .bind(title).to("title")
        .fetchAs(RelationSummary.class)
        .mappedBy((typeSystem, record) -> new RelationSummary(
            record.get("name").asString(),
            record.get("relationshipType").asString()
        ))
        .all();
}
```

Đặt phương thức này vào `MovieSearchFragmentImpl` đã khai báo ở phần trước; đây là phần triển khai còn lại của cùng class.

Các bước trong fluent API:

1. `query(...)` nhận câu Cypher.
2. `bind(title).to("title")` gắn giá trị Java với tham số `$title`.
3. `fetchAs(RelationSummary.class)` khai báo kiểu kết quả mong muốn.
4. `mappedBy(...)` nhận từng `Record` và chuyển các cột theo alias thành DTO.
5. `all()` thực thi và trả về toàn bộ kết quả đã ánh xạ.

`type(relatedTo)` trả về tên relationship type, ví dụ `ACTED_IN` hoặc `DIRECTED`. Alias `name` và `relationshipType` phải khớp với các cột mà mapper đọc. Vì DTO chỉ là kết quả đọc, không cần khai báo `@Node` hoặc cố gắng biến nó thành entity lưu trữ.

## 5. Dùng record và Neo4j type system khi mapping

Trong `mappedBy`, callback nhận `typeSystem` và `record`. `record` cho phép đọc từng cột theo alias; `typeSystem` cung cấp thông tin kiểu của Neo4j khi cần chuyển đổi linh hoạt.

Ví dụ truy vấn có giá trị có thể null:

```java
public record PersonScore(String name, Double score) {}

Collection<PersonScore> scores = neo4jClient.query("""
    MATCH (p:Person)
    OPTIONAL MATCH (p)-[r:REVIEWED]->(:Movie)
    RETURN p.name AS name,
           avg(r.score) AS score
    """)
    .fetchAs(PersonScore.class)
    .mappedBy((typeSystem, record) -> new PersonScore(
        record.get("name").asString(),
        record.get("score").isNull()
            ? null
            : record.get("score").asDouble()
    ))
    .all();
```

`avg()` có thể trả về null khi không có điểm hợp lệ. Vì vậy, DTO dùng `Double` thay vì primitive `double`, và mapper kiểm tra `isNull()` trước khi gọi `asDouble()`.

Với kiểu dữ liệu phức tạp, hãy kiểm tra null và kiểu thực tế trước khi gọi các hàm chuyển đổi như `asString()`, `asLong()` hoặc `asLocalDate()`. Không giả định mọi cột đều luôn có giá trị chỉ vì một số bản ghi thử nghiệm có dữ liệu đầy đủ.

## 6. Đọc map khi cấu trúc kết quả thực sự linh hoạt

Nếu cần đọc dữ liệu theo alias mà chưa muốn tạo DTO, `Neo4jClient` có thể trả về map:

```java
Collection<Map<String, Object>> rows = neo4jClient.query("""
    MATCH (p:Person)-[r]->(m:Movie {title: $title})
    RETURN p.name AS personName,
           type(r) AS relationshipType,
           m.title AS movieTitle
    """)
    .bind(title).to("title")
    .fetch()
    .all();
```

Mỗi map chứa các giá trị theo tên cột trong `RETURN`. Cách này hữu ích cho báo cáo động hoặc công cụ nội bộ cần xử lý nhiều hình dạng kết quả. Với API công khai có cấu trúc ổn định, DTO thường an toàn hơn vì kiểu dữ liệu và tên trường được kiểm tra ngay trong mã Java.

`Neo4jClient` cũng hỗ trợ `fetchAs(...)` kết hợp `mappedBy(...)` để kiểm soát chuyển đổi. Hãy ưu tiên cách đó khi cần một kiểu kết quả cụ thể, cần xử lý null hoặc cần dùng kiểu dữ liệu chuyên biệt của Neo4j Driver.

## 7. Vì sao không dùng Neo4jTemplate cho mọi kết quả?

`Neo4jTemplate` được thiết kế để làm việc với mapped domain objects. Nó cần biết kiểu entity đích và sử dụng metadata của SDN để dựng object graph. Điều này rất thuận tiện khi kết quả phù hợp với domain model.

Nhưng một truy vấn có thể trả về dữ liệu không đại diện cho entity:

- Số lượng relationship theo từng loại.
- Tổng doanh thu hoặc điểm trung bình.
- Tên node kết hợp với loại relationship.
- Một đường đi hoặc tập property được tính toán.
- Một hàng báo cáo tổng hợp từ nhiều node và relationship.

Không nên tạo `@Node` chỉ để chứa một hàng báo cáo tạm thời. DTO và mapper của `Neo4jClient` thể hiện đúng ý nghĩa rằng dữ liệu này chỉ phục vụ đọc. Nó cũng tránh việc một object báo cáo bị dùng nhầm làm entity để ghi ngược vào Neo4j.

## 8. Vì sao không dùng Neo4jClient cho mọi thao tác entity?

`Neo4jClient` cho phép kiểm soát sâu từng record, nhưng ứng dụng phải tự ánh xạ các cột và quản lý cấu trúc kết quả. Nếu mục tiêu chỉ là đọc một `Person` hoặc lưu một `Movie` theo domain model, việc tự chuyển từng property và relationship sẽ lặp lại công việc mà SDN đã cung cấp.

Khi dùng `Neo4jTemplate`, ứng dụng có thể tận dụng:

- Metadata entity và mapping context.
- Converter đã đăng ký.
- Mapping ID và relationship properties.
- Cơ chế ánh xạ entity theo kiểu domain.
- Các thao tác domain như `findById`, `findAll`, `save`, `saveAll`, `count` và `delete`.

Hãy dùng `Neo4jClient` khi kết quả hoặc thao tác đòi hỏi quyền kiểm soát record-level. Nếu chỉ cần một custom query trả về entity, template thường ngắn gọn hơn.

## 9. Cả hai API cùng tham gia transaction Spring

`Neo4jTemplate` và `Neo4jClient` do Spring Data Neo4j cung cấp đều tích hợp với transaction management của Spring. Khi custom repository fragment được gọi trong một phương thức `@Transactional`, các thao tác qua hai API có thể tham gia transaction hiện tại.

Ví dụ một fragment chỉ đọc:

```java
@Transactional(readOnly = true)
public interface MovieSearchFragment {
    List<Movie> findMoviesForPeople(Collection<String> personIds);
    Collection<RelationSummary> findRelationsToMovie(String title);
}
```

Với phương thức có ghi dữ liệu, dùng transaction read-write theo mặc định hoặc khai báo `@Transactional` không đặt `readOnly = true`:

```java
@Transactional
public Movie addMovie(Movie movie) {
    return neo4jTemplate.save(movie);
}
```

Không dùng transaction read-only cho phương thức có lệnh ghi. Trong Neo4j cluster, đánh dấu các luồng đọc là read-only còn giúp hệ thống định tuyến truy vấn đọc phù hợp với kiến trúc primary/secondary.

Một khác biệt quan trọng: nếu tự inject Neo4j Java Driver và mở session/transaction trực tiếp, transaction đó do Driver quản lý và không tự động tham gia transaction Spring. Nếu cần custom mapping nhưng vẫn muốn transaction Spring, ưu tiên `Neo4jClient`.

## 10. Kết hợp nhiều fragment trong cùng repository

Một repository có thể ghép nhiều fragment theo nhóm trách nhiệm. Ví dụ:

```java
public interface MovieRepository extends
        Neo4jRepository<Movie, String>,
        MovieSearchFragment,
        MovieStatisticsFragment {
}
```

Mỗi fragment có interface và implementation riêng:

```text
MovieSearchFragment.java
MovieSearchFragmentImpl.java
MovieStatisticsFragment.java
MovieStatisticsFragmentImpl.java
MovieRepository.java
```

Spring Data Neo4j phát hiện các implementation theo quy ước đặt tên và ghép chúng vào repository proxy. Constructor injection được dùng để nhận `Neo4jTemplate`, `Neo4jClient` hoặc các bean cần thiết; không cần thêm `@Autowired` nếu chỉ có một constructor.

Có thể đặt nhiều phương thức trong một fragment nếu chúng cùng một trách nhiệm. Khi fragment quá lớn hoặc trộn lẫn thao tác domain với báo cáo, tách thành các fragment nhỏ giúp kiểm thử và bảo trì dễ hơn.

## 11. Kiểm thử custom repository fragment

Integration test nên kiểm tra repository proxy đã ghép fragment, đồng thời xác nhận cả hai cách mapping:

1. Tạo các node `Person`, `Movie` và relationship `ACTED_IN` trong database kiểm thử.
2. Gọi `findMoviesForPeople(...)` và xác nhận kết quả là các entity `Movie` có property được ánh xạ đúng.
3. Gọi `findRelationsToMovie(...)` và xác nhận DTO chứa đúng `name` cùng `relationshipType`.
4. Kiểm tra tham số có ký tự đặc biệt để bảo đảm query dùng binding, không nối chuỗi.
5. Kiểm tra truy vấn không có kết quả trả collection rỗng.
6. Kiểm tra trường hợp property nullable để mapper không lỗi khi gặp null.
7. Đặt hai thao tác cần nguyên tử trong một transaction, cố ý phát sinh lỗi và xác nhận thay đổi được rollback.

Với phương thức dùng `Neo4jTemplate`, kiểm tra mapping entity và relationship cần thiết. Với phương thức dùng `Neo4jClient`, kiểm tra alias và từng cột DTO. Không chỉ xác nhận số lượng dòng vì dữ liệu có thể đúng số lượng nhưng ánh xạ sai cột.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tìm thấy fragment implementation | Class không đúng tên hoặc package nằm ngoài vùng scan | Dùng hậu tố `Impl` khớp tên interface và đặt trong package được scan. |
| Template trả entity thiếu relationship | Cypher không trả đủ node/relationship cần cho mapping | Bổ sung dữ liệu cần thiết vào kết quả hoặc dùng projection phù hợp. |
| DTO nhận null ở một trường | Alias không khớp tên mapper đọc hoặc property thực sự null | Đối chiếu alias và xử lý null tường minh. |
| Mapper lỗi khi đọc số hoặc ngày | Gọi conversion không phù hợp kiểu Neo4j thực tế | Kiểm tra kiểu bằng dữ liệu thử và chọn accessor tương ứng. |
| Dùng DTO như entity để lưu | Nhầm kết quả đọc tùy chỉnh với domain model | Giữ DTO ở read path; dùng entity hoặc command riêng cho write path. |
| Custom query không tham gia transaction Spring | Dùng Driver trực tiếp với session/transaction riêng | Dùng `Neo4jClient` hoặc để thao tác qua template trong Spring transaction. |
| Query trả về nhiều dòng trùng | Nhiều đường đi tạo cùng node hoặc DTO | Dùng `DISTINCT` hoặc aggregation theo đúng đơn vị nghiệp vụ. |

## 13. Quy trình chọn API

1. Xác định kết quả là entity domain hay dữ liệu đọc riêng.
2. Nếu là entity, dùng repository hoặc `Neo4jTemplate` với domain type rõ ràng.
3. Nếu là DTO, thống kê hoặc record tùy chỉnh, dùng `Neo4jClient` với alias ổn định và mapper rõ ràng.
4. Đặt phương thức trong custom repository fragment nếu truy vấn thuộc trách nhiệm của repository và cần tái sử dụng.
5. Truyền tham số bằng fluent binding; không ghép dữ liệu đầu vào vào chuỗi Cypher.
6. Đặt transaction read-only cho truy vấn đọc và transaction read-write cho luồng ghi cần nguyên tử.
7. Kiểm thử cả entity mapping, DTO mapping, null, kết quả rỗng và rollback.

## 14. Ghi nhớ

`Neo4jTemplate` là lựa chọn phù hợp cho custom query vẫn trả về entity của mô hình domain. Nó dùng mapping context của Spring Data Neo4j để chuyển node và relationship thành object Java. `Neo4jClient` phù hợp khi truy vấn trả về DTO, thống kê hoặc cấu trúc riêng; ứng dụng dùng `fetchAs(...).mappedBy(...)` để đọc từng record và tự ánh xạ kết quả.

Hai API có thể cùng nằm trong một custom repository fragment, được Spring ghép vào repository chính theo quy ước tên `Impl`. Cả hai đều tích hợp với transaction management của Spring. Hãy chọn theo hình dạng kết quả: entity thì ưu tiên template; dữ liệu đọc riêng thì ưu tiên client. Cách phân chia này giúp domain mapping tập trung ở SDN và custom result mapping nằm rõ ở nơi thực sự cần thiết.

## Tài liệu tham khảo

- [Spring Data Neo4j – FAQ: Custom queries, mappings and repository fragments](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j – Neo4jTemplate API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/Neo4jTemplate.html)
- [Spring Data Neo4j – Neo4jClient API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/Neo4jClient.html)
