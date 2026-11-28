# Bind nhiều tham số bằng map hoặc chuyển đổi đối tượng

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Bind nhiều tham số Cypher cùng lúc bằng `bindAll(Map<String, Object>)`.
- Phân biệt một Map chứa nhiều tham số với một Map được bind thành một tham số duy nhất.
- Bind một giá trị đơn bằng `bind(value).to(name)`.
- Chuyển một domain object thành nhiều tham số bằng `bind(object).with(Function)`.
- Chuẩn hóa collection và object lồng nhau thành kiểu dữ liệu mà Neo4j Java Driver có thể truyền.
- Kết hợp nhiều cách bind trong một truy vấn và nhận biết lỗi do tên tham số hoặc giá trị không hợp lệ.

## 1. Vì sao cần bind tham số?

`Neo4jClient` cho phép thực thi Cypher trực tiếp trong ứng dụng Spring Data Neo4j (SDN). Thay vì ghép giá trị đầu vào vào chuỗi truy vấn, hãy dùng tham số có tên trong Cypher và bind giá trị qua API fluent của client.

Ví dụ, truy vấn:

```cypher
MATCH (p:Person)
WHERE p.name = $name
  AND p.active = $active
RETURN p
```

có hai tham số là `name` và `active`. Giá trị thực tế được cung cấp khi xây dựng lời gọi `Neo4jClient`.

Bind tham số giúp:

- Tách cấu trúc truy vấn khỏi dữ liệu đầu vào.
- Tránh nối chuỗi giá trị vào Cypher và giảm nguy cơ Cypher injection.
- Tái sử dụng cùng một câu truy vấn với nhiều bộ dữ liệu.
- Truyền nhiều giá trị theo nhóm hoặc chuyển domain object thành dữ liệu phù hợp với driver.

Trong SDN có hai client với cùng phong cách API:

- `Neo4jClient`: thực thi imperative.
- `ReactiveNeo4jClient`: thực thi reactive.

Hai client có cách viết tương tự nhưng là hai API riêng, không thể thay thế trực tiếp cho nhau.

## 2. Cấu trúc fluent API khi bind

Một lời gọi cơ bản có dạng:

Các ví dụ dưới đây giả sử bean `Neo4jClient` đã được inject vào service hoặc component đang thực thi truy vấn.

```java
client.query("MATCH (p:Person) WHERE p.name = $name RETURN p")
    .bind("An").to("name")
    .fetch()
    .all();
```

Các bước:

1. `query(...)` khai báo câu Cypher.
2. `bind(value)` bắt đầu bind một giá trị.
3. `to("name")` gắn giá trị vào tham số Cypher `$name`.
4. `fetch()` chọn cách lấy kết quả.
5. `all()` lấy toàn bộ record.

Tên truyền cho `to()` là `name`, không có ký tự `$`. Tên đó phải khớp với tham số `$name` trong Cypher.

Có thể bind nhiều giá trị riêng lẻ trong cùng chuỗi fluent:

```java
var people = client
    .query("""
        MATCH (p:Person)
        WHERE p.name = $name
          AND p.active = $active
        RETURN p
        """)
    .bind("An").to("name")
    .bind(true).to("active")
    .fetch()
    .all();
```

Cách này dễ đọc khi chỉ có một vài tham số. Khi số lượng tham số tăng hoặc đã có sẵn một tập dữ liệu dạng Map, `bindAll()` thường gọn hơn.

## 3. Bind nhiều tham số bằng bindAll(Map)

`bindAll(Map<String, Object>)` nhận một Map mà:

- Key là tên tham số trong Cypher, không có ký tự `$`.
- Value là giá trị tương ứng mà Neo4j Java Driver có thể chuyển đổi.

Ví dụ:

```java
import java.util.Map;

Map<String, Object> parameters = Map.of(
    "departmentCode", "ENG",
    "active", true,
    "limit", 20
);

var people = client
    .query("""
        MATCH (p:Person)-[:MEMBER_OF]->(d:Department)
        WHERE d.code = $departmentCode
          AND p.active = $active
        RETURN p
        ORDER BY p.name
        LIMIT $limit
        """)
    .bindAll(parameters)
    .fetch()
    .all();
```

Map chứa ba entry, tương ứng với ba tham số của truy vấn. Ứng dụng không cần gọi `bind().to()` riêng cho từng entry.

Có thể tạo Map trong service từ dữ liệu đầu vào:

```java
import java.util.HashMap;
import java.util.Map;

Map<String, Object> parameters = new HashMap<>();
parameters.put("departmentCode", request.departmentCode());
parameters.put("active", request.active());
parameters.put("limit", request.pageSize());

var result = client
    .query("""
        MATCH (p:Person)-[:MEMBER_OF]->(d:Department)
        WHERE d.code = $departmentCode
          AND p.active = $active
        RETURN p
        LIMIT $limit
        """)
    .bindAll(parameters)
    .fetch()
    .all();
```

Cách này hữu ích khi request hoặc service đã chuẩn bị một bộ tham số có tên. Nên tạo Map ở nơi dễ kiểm tra, với key rõ ràng và khớp chính xác với Cypher.

### 3.1. Có thể kết hợp bindAll() và bind().to()

Không bắt buộc phải chọn duy nhất một cách bind. Có thể bind một tham số quan trọng riêng, rồi dùng Map cho các tham số còn lại:

```java
Map<String, Object> filters = Map.of(
    "active", true,
    "limit", 10
);

var result = client
    .query("""
        MATCH (p:Person)
        WHERE p.name CONTAINS $keyword
          AND p.active = $active
        RETURN p
        ORDER BY p.name
        LIMIT $limit
        """)
    .bind("An").to("keyword")
    .bindAll(filters)
    .fetch()
    .all();
```

Ở đây, `keyword` được bind riêng, còn `active` và `limit` được bind theo Map. Không được khai báo cùng một tên tham số nhiều lần trong các thao tác bind của cùng query.

## 4. Phân biệt Map tham số và Map được bind thành một tham số

Hai cách sau có ý nghĩa khác nhau.

**Cách A: Map chứa nhiều tham số riêng**

```java
Map<String, Object> parameters = Map.of(
    "name", "An",
    "active", true
);

client.query("""
    MATCH (p:Person)
    WHERE p.name = $name AND p.active = $active
    RETURN p
    """)
    .bindAll(parameters);
```

Ở đây, Map có hai key, nên client bind hai tham số `$name` và `$active`.

**Cách B: Bind toàn bộ Map thành một tham số**

```java
Map<String, Object> filters = Map.of(
    "minAge", 18,
    "active", true
);

client.query("""
    MATCH (p:Person)
    WHERE p.age >= $filters.minAge
      AND p.active = $filters.active
    RETURN p
    """)
    .bind(filters).to("filters");
```

Ở cách này, toàn bộ Map là giá trị của một tham số tên `filters`. Cypher truy cập các key bên trong thông qua biểu thức `$filters.minAge` và `$filters.active`.

| Cách gọi | Ý nghĩa |
| --- | --- |
| `bindAll(parameters)` | Mỗi entry trở thành một tham số Cypher riêng |
| `bind(filters).to("filters")` | Cả Map là giá trị của một tham số `$filters` |

Đây là khác biệt quan trọng khi thiết kế query nhận một nhóm filter hoặc một cấu trúc dữ liệu có tên.

## 5. Khi nào cần chuyển domain object thành tham số?

Các kiểu dữ liệu đơn giản mà Neo4j Java Driver hỗ trợ có thể được bind trực tiếp. Tuy nhiên, một domain object tùy chỉnh thường không thể được gửi nguyên trạng như một giá trị Bolt.

Ví dụ, ứng dụng có object `Director` gồm tên đạo diễn và danh sách các object `Movie`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class Director {

    private final String name;
    private final List<Movie> movies;

    public Director(String name, List<Movie> movies) {
        this.name = name;
        this.movies = new ArrayList<>(movies);
    }

    public String getName() {
        return name;
    }

    public List<Movie> getMovies() {
        return Collections.unmodifiableList(movies);
    }
}

class Movie {

    private final String title;

    public Movie(String title) {
        this.title = title;
    }

    public String getTitle() {
        return title;
    }
}
```

Câu Cypher cần hai tham số:

- `$name`: tên đạo diễn.
- `$movies`: danh sách tiêu đề phim dạng chuỗi.

Domain object lại có cấu trúc khác: `movies` là `List<Movie>`, không phải `List<String>`. Cần chuyển đổi object trước khi bind.

## 6. Dùng bind(object).with(Function) để chuyển đổi đối tượng

API `bind(value).with(binder)` cho phép cung cấp một hàm chuyển đổi:

```java
.bind(director).with(value -> {
    Map<String, Object> parameters = new HashMap<>();
    // Chuyển object thành các named parameters
    return parameters;
})
```

Hàm binder nhận domain object và trả về `Map<String, Object>`. Mỗi key trong Map tương ứng với một tham số Cypher; mỗi value phải là kiểu mà driver có thể chuyển đổi.

Ví dụ hoàn chỉnh:

```java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public final class DirectorParameters {

    private DirectorParameters() {
    }

    public static Map<String, Object> toParameters(Director director) {
        Map<String, Object> parameters = new HashMap<>();

        List<String> movieTitles = director.getMovies().stream()
            .map(Movie::getTitle)
            .collect(Collectors.toList());

        parameters.put("name", director.getName());
        parameters.put("movies", movieTitles);

        return parameters;
    }
}
```

Sử dụng trong `Neo4jClient`:

```java
import java.util.List;
import org.neo4j.driver.summary.ResultSummary;

Director director = new Director(
    "Joseph Kosinski",
    List.of(
        new Movie("Tron Legacy"),
        new Movie("Top Gun: Maverick")
    )
);

ResultSummary summary = client
    .query("""
        MERGE (p:Person {name: $name})
        WITH p
        UNWIND $movies AS movieTitle
        MERGE (m:Movie {title: movieTitle})
        MERGE (p)-[:DIRECTED]->(m)
        """)
    .bind(director)
    .with(DirectorParameters::toParameters)
    .run();
```

Hàm `toParameters()` chuyển object thành Map có hai entry:

```text
name   -> "Joseph Kosinski"
movies -> ["Tron Legacy", "Top Gun: Maverick"]
```

Sau chuyển đổi, các giá trị đều là kiểu dữ liệu đơn giản mà driver hiểu được. Cypher dùng chúng để tạo hoặc tìm node và relationship.

### 6.1. Binder phải cung cấp đủ tham số cho truy vấn

Nếu câu Cypher dùng `$name` và `$movies`, binder cần trả về cả hai key. Nếu thiếu một key, driver sẽ báo lỗi khi thực thi do tham số cần thiết chưa được cung cấp.

Nên đặt việc chuyển đổi trong một hàm riêng thay vì viết lambda dài ngay trong chuỗi fluent. Hàm riêng có thể được kiểm tra độc lập và tái sử dụng trong nhiều truy vấn.

Có thể dùng binder cho nhiều loại object khác nhau. Ví dụ, object `OrderRequest` có thể chuyển thành `orderId`, `customerCode`, `itemCodes` và `requestedAt`. Chỉ cần bảo đảm các key trả về khớp với named parameters trong Cypher.

## 7. Kết hợp nhiều nguồn dữ liệu tham số

Một truy vấn có thể nhận tham số từ nhiều nguồn: một giá trị đơn, một Map filter và một domain object.

Ví dụ:

```java
import java.util.Map;

public record DepartmentFilter(String departmentCode) {
}

public final class DepartmentParameters {

    private DepartmentParameters() {
    }

    public static Map<String, Object> toParameters(DepartmentFilter filter) {
        return Map.of("departmentCode", filter.departmentCode());
    }
}

Map<String, Object> options = Map.of(
    "active", true,
    "limit", 10
);

var result = client
    .query("""
        MATCH (p:Person)-[:MEMBER_OF]->(d:Department)
        WHERE p.name CONTAINS $keyword
          AND p.active = $active
          AND d.code = $departmentCode
        RETURN p
        ORDER BY p.name
        LIMIT $limit
        """)
    .bind("An").to("keyword")
    .bind(new DepartmentFilter("ENG"))
    .with(DepartmentParameters::toParameters)
    .bindAll(options)
    .fetch()
    .all();
```

Trong ví dụ, binder của `DepartmentFilter` trả về key `departmentCode`. Map `options` cung cấp `active` và `limit`; giá trị đơn cung cấp `keyword`.

Không nên để hai nguồn cùng trả về một key. Nếu một tham số được bind nhiều lần, client ngăn việc sử dụng tên đó hai lần. Hãy phân chia trách nhiệm giữa các nguồn dữ liệu ngay từ đầu.

## 8. Giá trị nào có thể truyền cho Neo4j Java Driver?

Neo4j Java Driver chỉ nhận các kiểu giá trị mà nó biết cách chuyển đổi thành kiểu dữ liệu Bolt. Các kiểu đơn giản như chuỗi, số, boolean, giá trị thời gian được hỗ trợ và collection phù hợp có thể được bind trực tiếp. Domain class tùy chỉnh cần được chuyển thành cấu trúc dữ liệu được driver hỗ trợ.

Một số nguyên tắc:

- Dùng `String`, kiểu số, `Boolean` và các kiểu temporal được driver hỗ trợ cho giá trị đơn.
- Dùng List hoặc Map có cấu trúc giá trị phù hợp với driver.
- Chuyển `List<Movie>` thành `List<String>` nếu truy vấn chỉ cần tiêu đề phim.
- Không giả định driver tự đọc getter hoặc serialize POJO tùy chỉnh.
- Không truyền trực tiếp object graph chứa entity, relationship hoặc object không được driver hỗ trợ.
- Kiểm tra cách xử lý null trước khi đưa vào Map; một số factory như `Map.of()` không cho phép value null.

Nếu cần truyền một node hoặc relationship đã tồn tại, hãy truyền định danh hoặc property cần thiết rồi tìm node trong Cypher. Không coi một Java entity là giá trị tham số có thể bind trực tiếp thành node Neo4j.

## 9. Bind tham số và kết quả trả về là hai việc khác nhau

Việc bind dữ liệu đầu vào không quyết định cách ứng dụng đọc kết quả. Sau khi bind, client vẫn cần chọn cách lấy record:

```java
import java.util.Collection;
import java.util.Map;

Collection<Map<String, Object>> records = client
    .query("""
        MATCH (p:Person)
        WHERE p.active = $active
        RETURN p.name AS name, p.age AS age
        """)
    .bindAll(Map.of("active", true))
    .fetch()
    .all();
```

Ở đây:

- `bindAll()` truyền dữ liệu đầu vào.
- `fetch().all()` lấy các record.
- Mỗi record được biểu diễn thành Map có key là alias trong `RETURN`, ví dụ `name` và `age`.

Nếu muốn ánh xạ record thành DTO, có thể dùng `fetchAs()` và `mappedBy()`:

```java
import java.util.Collection;

public record PersonSummary(String name, long age) {
}
```

```java
import org.neo4j.driver.Record;
import org.neo4j.driver.types.TypeSystem;

Collection<PersonSummary> summaries = client
    .query("""
        MATCH (p:Person)
        WHERE p.active = $active
        RETURN p.name AS name, p.age AS age
        """)
    .bindAll(Map.of("active", true))
    .fetchAs(PersonSummary.class)
    .mappedBy((TypeSystem typeSystem, Record record) ->
        new PersonSummary(
            record.get("name").asString(),
            record.get("age").asLong()
        )
    )
    .all();
```

`mappedBy()` là hàm chuyển record trả về thành object Java. Nó khác với `bind(object).with(...)`, vốn chuyển object Java thành các tham số đầu vào.

## 10. Lưu ý về kiểm tra tên tham số và lỗi binding

Neo4jClient hỗ trợ bind named parameters, nhưng không thay thế hoàn toàn việc kiểm tra tham số của driver.

- Client ngăn việc bind cùng một tên tham số hai lần trong một query.
- Việc thiếu tham số hoặc truyền thừa tham số được giao cho driver kiểm tra khi thực thi.
- Key trong Map phải khớp với tên tham số Cypher.
- Giá trị trong Map phải có kiểu driver hỗ trợ.
- Không đưa ký tự `$` vào key của Map hoặc tên truyền cho `to()`.
- Không nối trực tiếp dữ liệu đầu vào vào câu Cypher.

Ví dụ lỗi tên:

```java
Map<String, Object> parameters = Map.of(
    "department_code", "ENG"
);
```

Trong khi Cypher sử dụng:

```cypher
WHERE d.code = $departmentCode
```

Hai tên không khớp nhau, nên tham số `$departmentCode` vẫn chưa được bind. Hãy thống nhất quy tắc đặt tên camelCase hoặc snake_case trong toàn bộ truy vấn và binder.

Ngoài ra, tên label, relationship type và property không phải giá trị tham số thông thường. Nếu cần thay đổi cấu trúc truy vấn theo lựa chọn người dùng, hãy dùng danh sách cho phép (allowlist) và xây dựng phần cấu trúc Cypher từ lựa chọn đã xác thực.

## 11. Imperative và reactive binding

Hai client có cách bind tương tự:

```java
imperativeClient
    .query("MATCH (p:Person {name: $name}) RETURN p")
    .bind("An").to("name")
    .fetch()
    .all();
```

```java
reactiveClient
    .query("MATCH (p:Person {name: $name}) RETURN p")
    .bind("An").to("name")
    .fetch()
    .all();
```

Nhưng kết quả và thời điểm thực thi khác nhau:

| Client | Kết quả `fetch().all()` | Thời điểm truy vấn |
| --- | --- | --- |
| `Neo4jClient` | Collection | Thực thi khi gọi terminal operation |
| `ReactiveNeo4jClient` | `Flux` | Thực thi khi publisher được subscribe |

Với reactive client, chỉ tạo publisher chưa có nghĩa truy vấn đã chạy. Publisher cần được nối vào reactive pipeline và được subscribe bởi framework hoặc subscriber. Không nên gọi `block()` tùy tiện trong luồng reactive chỉ để lấy kết quả đồng bộ.

Binder function cũng cần tránh side effect. Hãy xem nó như hàm chuyển đổi dữ liệu đầu vào thành Map tham số, không phải nơi thực hiện thao tác ghi hoặc gọi dịch vụ bên ngoài.

## 12. Quy trình thiết kế binding dễ bảo trì

Khi xây dựng một custom query, có thể thực hiện theo trình tự:

1. Liệt kê tất cả named parameters trong Cypher.
2. Xác định tham số nào là giá trị đơn, tham số nào phù hợp để gom vào Map.
3. Xác định domain object nào cần chuyển thành nhiều tham số.
4. Viết binder function để chuyển object thành Map có key khớp truy vấn.
5. Kiểm tra tất cả value có kiểu driver hỗ trợ.
6. Tránh bind trùng tên giữa các nguồn.
7. Chọn `fetch().one()`, `first()`, `all()` hoặc `run()` theo mục đích.
8. Nếu dùng reactive client, bảo đảm publisher được subscribe trong pipeline.

Với truy vấn có nhiều tham số, nên tạo một hằng số hoặc tài liệu ngắn ghi lại hợp đồng tham số. Điều này giúp người bảo trì biết truy vấn cần những key nào và binder nào chịu trách nhiệm cung cấp chúng.

## 13. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Dùng `bindAll()` nhưng query vẫn thiếu tham số | Key trong Map không khớp tên `$parameter` | So sánh từng key và tên trong Cypher |
| Nghĩ `bindAll(map)` bind Map thành một tham số | Nhầm Map tham số với giá trị Map | Dùng `bind(map).to("name")` nếu muốn một tham số Map |
| Bind trực tiếp POJO tùy chỉnh | Driver không biết chuyển đổi object đó | Dùng `bind(object).with(...)` |
| Binder chỉ trả một phần key cần thiết | Query tham chiếu tham số chưa được cung cấp | Đảm bảo binder trả đủ named parameters |
| Dùng cùng key trong bind riêng và bindAll | Tên tham số bị bind lặp | Phân chia nguồn tham số không trùng |
| Đưa `List<Movie>` trực tiếp vào query | Phần tử là POJO tùy chỉnh | Chuyển thành `List<String>` hoặc kiểu driver hỗ trợ |
| Nối giá trị đầu vào vào Cypher | Query khó an toàn và khó tái sử dụng | Dùng named parameters |
| Tạo reactive publisher nhưng không subscribe | Truy vấn chưa được thực thi | Nối publisher vào pipeline được subscribe |
| Dùng `Map.of()` với value null | Factory không cho phép null | Dùng Map có thể thay đổi và xác định chính sách null |

## 14. Câu hỏi tự kiểm tra

1. `bindAll(Map<String, Object>)` diễn giải key và value trong Map như thế nào?
2. Khác biệt giữa `bindAll(map)` và `bind(map).to("filters")` là gì?
3. Khi nào nên dùng `bind(value).to(name)`?
4. Vì sao POJO tùy chỉnh thường cần `bind(object).with(Function)`?
5. Binder function phải trả về kiểu dữ liệu nào?
6. Nếu query dùng `$name` và `$movies`, binder cần trả về những key nào?
7. Vì sao nên chuyển `List<Movie>` thành `List<String>` khi Cypher chỉ cần tiêu đề phim?
8. Client xử lý thế nào khi một tên tham số bị bind hai lần?
9. Ai kiểm tra trường hợp thiếu hoặc thừa named parameters?
10. Khác biệt giữa `bind(object).with(...)` và `fetchAs().mappedBy(...)` là gì?
11. Khi nào reactive query thực sự được thực thi?

## Tài liệu tham khảo

- [Spring Data Neo4j – Neo4jClient](https://docs.spring.io/spring-data/neo4j/reference/appendix/neo4j-client.html)
- [Neo4jClient.BindSpec API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/Neo4jClient.BindSpec.html)
- [Neo4jClient.OngoingBindSpec API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/Neo4jClient.OngoingBindSpec.html)
- [Neo4j Java Driver – Values and types](https://neo4j.com/docs/java-manual/current/data-types/)

## Kết luận

`bindAll(Map<String, Object>)` giúp bind nhiều named parameters từ một Map; mỗi key tương ứng với một tên tham số trong Cypher. Nếu Map cần được truyền như một giá trị duy nhất, hãy dùng `bind(map).to(name)`. Với một domain object có cấu trúc riêng, `bind(object).with(Function)` cho phép chuyển object thành Map tham số phù hợp với Neo4j Java Driver.

Hãy thiết kế hợp đồng tham số rõ ràng, dùng key khớp với Cypher, chuyển các object và collection thành kiểu dữ liệu driver hỗ trợ, đồng thời tránh bind trùng tên. Khi tách bạch binding đầu vào với mapping kết quả, các custom query qua Neo4jClient sẽ dễ đọc, dễ kiểm tra và dễ tái sử dụng hơn.
