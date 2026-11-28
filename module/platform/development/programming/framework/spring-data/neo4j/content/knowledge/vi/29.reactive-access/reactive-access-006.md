# Truy vấn tùy chỉnh bằng ReactiveNeo4jClient

`ReactiveNeo4jClient` cho phép gửi Cypher tùy chỉnh tới Neo4j và xử lý kết quả dưới dạng `Mono` hoặc `Flux`. API này phù hợp khi truy vấn cần pattern graph, aggregation, thao tác relationship hoặc hình dạng kết quả mà repository method thông thường khó biểu diễn. Client cung cấp cách bind tham số, ánh xạ từng `Record` sang DTO và tham gia transaction reactive do Spring quản lý.

Bài học thuộc module **SPRING_DATA_NEO4J**, tập trung xây dựng tầng dữ liệu đồ thị qua node entity, relationship, repository và Cypher. Ví dụ dùng `Person`, `Movie` và `ACTED_IN` để tìm diễn viên, tổng hợp số phim, cập nhật relationship và kết hợp nhiều truy vấn trong một reactive transaction.

## 1. Khi nào dùng ReactiveNeo4jClient?

Spring Data Neo4j có nhiều tầng truy cập dữ liệu:

| API | Phù hợp khi |
|---|---|
| `ReactiveNeo4jRepository` | CRUD theo entity, derived query và các truy vấn repository có cấu trúc ổn định |
| `ReactiveNeo4jTemplate` | Thao tác entity tổng quát bằng mapping metadata và fluent API |
| `ReactiveNeo4jClient` | Viết Cypher tùy chỉnh, bind tham số và ánh xạ kết quả theo nhu cầu |
| Neo4j Java Driver reactive API trực tiếp | Cần điều khiển cấp thấp; phải chủ động tích hợp transaction và quản lý tài nguyên |

`ReactiveNeo4jClient` là lớp client mỏng trên Neo4j Java Driver. Nó giữ cú pháp fluent gần với `Neo4jClient` imperative nhưng trả về publisher reactive. Client không tự biến mọi kết quả Cypher thành entity `@Node`; khi truy vấn trả về DTO hoặc cấu trúc riêng, ta chủ động ánh xạ kết quả.

Hai client imperative và reactive có tên method gần giống nhau nhưng không tương thích kiểu API. Không gán kết quả `Mono`/`Flux` vào biến `Optional`/`List` như khi dùng `Neo4jClient` đồng bộ.

## 2. Inject ReactiveNeo4jClient từ Spring

Trong ứng dụng Spring Boot có Spring Data Neo4j và Project Reactor trên classpath, cấu hình reactive repositories/template có thể được auto-configure. Hãy inject `ReactiveNeo4jClient` do Spring quản lý thay vì tự tạo driver hoặc client trong mỗi service:

```java
import org.springframework.data.neo4j.core.ReactiveNeo4jClient;
import org.springframework.stereotype.Service;

@Service
public class MovieQueryService {

    private final ReactiveNeo4jClient neo4jClient;

    public MovieQueryService(ReactiveNeo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }
}
```

Nếu tự cấu hình SDN mà không dùng Spring Boot, có thể dùng `AbstractReactiveNeo4jConfig` và `@EnableReactiveNeo4jRepositories` để đăng ký hạ tầng reactive. Hãy sử dụng cùng `Driver` do cấu hình đó quản lý.

### 2.1. Cấu hình ReactiveNeo4jTransactionManager

Reactive repositories và template có thể được cấu hình khi Reactor có mặt, nhưng Spring Boot không tự tạo `ReactiveTransactionManager` cho Neo4j. Nếu cần `@Transactional` cho luồng reactive, hãy khai báo `ReactiveNeo4jTransactionManager`:

```java
import org.neo4j.driver.Driver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.ReactiveDatabaseSelectionProvider;
import org.springframework.data.neo4j.core.transaction.ReactiveNeo4jTransactionManager;

@Configuration(proxyBeanMethods = false)
public class ReactiveNeo4jTransactionConfiguration {

    @Bean
    ReactiveNeo4jTransactionManager reactiveTransactionManager(
            Driver driver,
            ReactiveDatabaseSelectionProvider databaseSelectionProvider) {
        return new ReactiveNeo4jTransactionManager(
            driver,
            databaseSelectionProvider
        );
    }
}
```

Transaction manager và client phải dùng cùng cấu hình `Driver`, đồng thời phải thống nhất database selection. Nếu starter hoặc cấu hình SDN đã cung cấp client phù hợp, hãy dùng bean đó; không tạo một `Driver` độc lập chỉ cho client.

Lưu ý này dựa trên tài liệu Spring Boot hiện hành: Boot có thể auto-configure reactive repositories/template khi Reactor có mặt, nhưng yêu cầu ứng dụng khai báo reactive transaction manager. Với dự án dùng Spring Boot hoặc SDN phiên bản khác, hãy đối chiếu tài liệu khớp với dependency management của dự án trước khi thêm bean để tránh cấu hình trùng.

Với cấu hình Spring không dùng Boot, bật transaction annotation management trong configuration cùng với hạ tầng reactive repositories. Khi ứng dụng có nhiều transaction manager, chỉ rõ bean reactive Neo4j trên `@Transactional` bằng thuộc tính `transactionManager`.

## 3. Cấu trúc một truy vấn reactive

Một truy vấn thường đi qua các bước:

1. `query(...)`: khai báo Cypher dưới dạng `String` hoặc `Supplier<String>`.
2. `in(...)`: tùy chọn chọn database đích.
3. `bind(...).to(...)` hoặc `bindAll(...)`: gắn giá trị cho named parameter.
4. `fetch()` hoặc `fetchAs(...)`: chọn cách đọc và ánh xạ kết quả.
5. `all()`, `first()`, `one()` hoặc `run()`: tạo publisher kết quả cuối cùng.

Ví dụ lấy danh sách phim theo năm phát hành:

```java
import java.util.Map;
import reactor.core.publisher.Flux;

public Flux<Map<String, Object>> findMoviesReleasedSince(int year) {
    return neo4jClient.query("""
            MATCH (m:Movie)
            WHERE m.released >= $year
            RETURN m.movieId AS movieId,
                   m.title AS title,
                   m.released AS released
            ORDER BY released DESC, title ASC
            """)
        .bind(year).to("year")
        .fetch()
        .all();
}
```

`fetch().all()` trả về `Flux<Map<String, Object>>`. Mỗi map tương ứng một hàng Cypher; key của map là alias trong `RETURN`. Phương thức trả publisher cho caller, không tự subscribe.

## 4. Chọn one(), first(), all() hay run()

Reactive client cung cấp các terminal operation khác nhau:

| Phương thức | Kiểu trả về | Ngữ nghĩa |
|---|---|---|
| `one()` | `Mono<T>` | Yêu cầu đúng một hàng; nếu có nhiều hơn một hàng thì phát lỗi. Không có hàng thì publisher hoàn tất rỗng |
| `first()` | `Mono<T>` | Lấy hàng đầu tiên nếu có; không có hàng thì publisher hoàn tất rỗng |
| `all()` | `Flux<T>` | Phát lần lượt tất cả các hàng kết quả |
| `run()` | `Mono<ResultSummary>` | Thực thi query mà không ánh xạ các hàng; trả summary và counters của driver |

Ví dụ tìm một người theo ID:

```java
public Mono<Map<String, Object>> findPerson(String personId) {
    return neo4jClient.query("""
            MATCH (p:Person {personId: $personId})
            RETURN p.personId AS personId, p.name AS name
            """)
        .bind(personId).to("personId")
        .fetch()
        .one();
}
```

Chỉ dùng `one()` khi điều kiện truy vấn bảo đảm tối đa một hàng, ví dụ `personId` có uniqueness constraint. Nếu truy vấn có thể trả nhiều hàng và nghiệp vụ chỉ cần một kết quả, dùng `first()` cùng `ORDER BY` để xác định rõ hàng được chọn.

Ví dụ cập nhật relationship không cần đọc hàng:

```java
public Mono<ResultSummary> addActingCredit(
        String personId,
        String movieId) {
    return neo4jClient.query("""
            MATCH (p:Person {personId: $personId})
            MATCH (m:Movie {movieId: $movieId})
            MERGE (p)-[:ACTED_IN]->(m)
            """)
        .bind(personId).to("personId")
        .bind(movieId).to("movieId")
        .run();
}
```

Publisher từ `run()` có thể được dùng để đọc số node hoặc relationship đã tạo:

```java
public Mono<Long> addCreditAndCountChanges(String personId, String movieId) {
    return addActingCredit(personId, movieId)
        .map(summary -> summary.counters().relationshipsCreated());
}
```

Nếu dùng `MERGE` cho relationship, hãy xác định rõ khóa nhận diện và uniqueness của hai đầu graph; `MERGE` không tự tạo uniqueness constraint cho mọi dữ liệu nghiệp vụ.

## 5. Bind tham số bằng bind() và bindAll()

Cypher nên dùng named parameter thay vì ghép trực tiếp dữ liệu đầu vào vào chuỗi truy vấn:

```java
return neo4jClient.query("""
        MATCH (p:Person)
        WHERE toLower(p.name) CONTAINS toLower($fragment)
          AND p.born >= $minBorn
        RETURN p.personId AS personId, p.name AS name
        ORDER BY p.name
        """)
    .bind(fragment).to("fragment")
    .bind(minBorn).to("minBorn")
    .fetch()
    .all();
```

Khi có nhiều tham số, có thể truyền một map:

```java
Map<String, Object> parameters = Map.of(
    "fragment", fragment,
    "minBorn", minBorn
);

return neo4jClient.query("""
        MATCH (p:Person)
        WHERE toLower(p.name) CONTAINS toLower($fragment)
          AND p.born >= $minBorn
        RETURN p.personId AS personId, p.name AS name
        ORDER BY p.name
        """)
    .bindAll(parameters)
    .fetch()
    .all();
```

Các kiểu đơn giản mà Neo4j Java Driver hiểu được có thể bind trực tiếp. Với object Java phức tạp, hãy chuyển object thành map các property được hỗ trợ bằng binder function; không giả định driver tự serialize mọi domain object.

Client không tự kiểm tra rằng tất cả placeholder đã được bind hoặc không có tham số thừa; driver sẽ báo lỗi khi thực thi. Hãy giữ tên placeholder trong Cypher và tên truyền cho `.to(...)` hoặc key trong map đồng nhất.

`Map.of(...)` chỉ dùng được khi tất cả giá trị đều khác `null`. Nếu filter tùy chọn cần bind `null`, hãy tạo `HashMap` hoặc map mutable tương đương rồi truyền bằng `bindAll(...)`.

### 5.1. Không bind được tên label, property hoặc keyword Cypher

Cypher parameter dùng cho giá trị, ví dụ `$personId`, `$year` hoặc `$title`. Không thể dùng parameter để thay tên label, tên property, tên relationship type hay keyword như `ASC`/`DESC`.

Nếu truy vấn cần sort theo trường do người dùng chọn, hãy ánh xạ lựa chọn đó qua whitelist:

```java
String orderBy = switch (sortField) {
    case "released" -> "m.released";
    case "title" -> "m.title";
    default -> "m.title";
};

String direction = descending ? "DESC" : "ASC";
String cypher = "MATCH (m:Movie) RETURN m ORDER BY "
        + orderBy + " " + direction;

return neo4jClient.query(cypher)
    .fetch()
    .all();
```

Ví dụ minh họa nguyên tắc chọn identifier từ whitelist; kết quả được trả về dưới dạng map. Trong ứng dụng thực tế, nên đóng gói whitelist thành hàm riêng và có thể ánh xạ map sang DTO. Không nối trực tiếp `sortField`, `direction`, label hoặc relationship type chưa được kiểm tra từ request vào Cypher.

## 6. Ánh xạ kết quả thành DTO bằng fetchAs()

Nếu query trả dữ liệu thống kê hoặc một tập trường riêng, hãy dùng DTO thay vì cố ánh xạ thành entity graph không đầy đủ.

DTO Java record:

```java
public record MovieSummary(
        String movieId,
        String title,
        Integer released,
        long actorCount) {
}
```

Truy vấn và mapping:

```java
import org.neo4j.driver.Record;
import org.neo4j.driver.types.TypeSystem;
import reactor.core.publisher.Flux;

public Flux<MovieSummary> findMovieSummaries() {
    return neo4jClient.query("""
            MATCH (m:Movie)
            OPTIONAL MATCH (p:Person)-[:ACTED_IN]->(m)
            RETURN m.movieId AS movieId,
                   m.title AS title,
                   m.released AS released,
                   count(DISTINCT p) AS actorCount
            ORDER BY released DESC, title ASC
            """)
        .fetchAs(MovieSummary.class)
        .mappedBy((TypeSystem typeSystem, Record record) ->
            new MovieSummary(
                record.get("movieId").asString(),
                record.get("title").asString(),
                record.get("released").isNull()
                    ? null
                    : record.get("released").asInt(),
                record.get("actorCount").asLong()
            )
        )
        .all();
}
```

`fetchAs(MovieSummary.class)` khai báo kiểu đích; `mappedBy(...)` nhận `TypeSystem` và một `Record` cho mỗi hàng. Hàm mapping đọc alias trong `RETURN` và tạo DTO. `count()` của Cypher trả số nguyên dài, vì vậy component `actorCount` dùng `long` và đọc bằng `asLong()`.

Nếu một property có thể `null`, hãy kiểm tra `Value.isNull()` trước khi gọi `asString()`, `asInt()` hoặc `asLong()`. Nếu query đổi alias, callback mapping phải được cập nhật tương ứng. Java record yêu cầu Java 16 trở lên; có thể thay bằng DTO class có constructor phù hợp.

## 7. Khi cần ánh xạ Node hoặc Relationship

Khi `RETURN` trả về một node, relationship hoặc path, `Record` chứa các giá trị driver tương ứng. Có thể dùng `fetchAs(...)` với mapping thủ công, hoặc lấy mapping function có sẵn từ `Neo4jMappingContext` nếu node đã có entity mapping.

Ví dụ truy vấn trả node `m`:

```cypher
MATCH (m:Movie {movieId: $movieId})
RETURN m AS movie;
```

Nếu chỉ cần một DTO, đọc trực tiếp các property từ `record.get("movie")`. Nếu cần ánh xạ node theo metadata SDN, inject `Neo4jMappingContext`, lấy mapping function cho `Movie` và áp dụng nó lên `MapAccessor` tương ứng. Cách này hữu ích khi query tùy chỉnh kết hợp dữ liệu ngoài entity nhưng vẫn cần chuyển một node thành entity đã mapping.

Không mặc định rằng một `Record` là entity. `RETURN p.name` trả scalar; `RETURN p, m` trả hai giá trị graph trong một hàng; `RETURN p, collect(m) AS movies` trả node cùng collection. Hãy xác định hình dạng `RETURN` trước khi viết mapping.

## 8. Thực thi ghi và đọc summary bằng run()

Với `CREATE`, `MERGE`, `SET` hoặc `DELETE` mà không cần lấy từng hàng kết quả, dùng `run()`:

```java
public Mono<Long> deleteActingCredits(String personId) {
    return neo4jClient.query("""
            MATCH (p:Person {personId: $personId})-[r:ACTED_IN]->(:Movie)
            DELETE r
            """)
        .bind(personId).to("personId")
        .run()
        .map(summary -> summary.counters().relationshipsDeleted());
}
```

`ResultSummary` cung cấp counters như số node, relationship hoặc property đã tạo/xóa/cập nhật và thông tin thực thi. Dùng summary để trả kết quả phù hợp cho use case mà không phải chạy thêm một truy vấn đếm nếu counters đã đáp ứng nhu cầu.

Lệnh xóa relationship trong ví dụ chỉ xóa các cạnh `ACTED_IN` từ người đó tới phim; node `Person` và `Movie` vẫn tồn tại. Nếu thay bằng `DETACH DELETE p`, phạm vi tác động khác hẳn. Luôn xác định rõ graph element mà câu Cypher sẽ thay đổi.

## 9. ReactiveNeo4jClient chỉ chạy khi publisher được subscribe

Điểm khác biệt quan trọng nhất so với `Neo4jClient` imperative là thời điểm thực thi:

- Khi gọi `query()`, `bind()` và `fetch()`, client đang xây dựng mô tả publisher.
- Database chỉ được truy cập khi publisher được subscribe.
- `Flux` phát nhiều hàng theo nhu cầu downstream; `Mono` phát tối đa một giá trị.
- Publisher do reactive client tạo ra được thiết kế cho một lần subscribe; không giữ và tái sử dụng cùng một publisher như một kết quả đã materialize.

Ví dụ service nên trả publisher:

```java
public Flux<MovieSummary> listSummaries() {
    return findMovieSummaries();
}
```

Trong WebFlux controller, có thể trả trực tiếp `Flux` hoặc `Mono`; framework sẽ subscribe để ghi response. Trong test, dùng `StepVerifier` để subscribe và xác minh kết quả.

Không gọi `.subscribe()` bên trong service chỉ để “kích hoạt” truy vấn. Nếu tự subscribe, luồng xử lý tách khỏi caller: lỗi khó truyền về controller, transaction reactive có thể không bao trùm công việc và caller không thể điều phối backpressure hoặc cancellation.

Không gọi `.block()` trong request path reactive. `block()` biến thao tác thành đồng bộ và có thể chặn event-loop thread. Nếu ứng dụng cần API đồng bộ, hãy dùng imperative stack một cách có chủ đích thay vì trộn hai mô hình trong cùng luồng.

## 10. Kết hợp nhiều truy vấn trong reactive transaction

`ReactiveNeo4jClient` tích hợp với transaction reactive của Spring. Khi method service trả về `Mono` hoặc `Flux` và được đánh dấu `@Transactional`, transaction được gắn với Reactor context của publisher. Các thao tác client trong cùng chuỗi reactive có thể tham gia cùng transaction nếu client và transaction manager dùng cùng Driver/database selection.

Ví dụ cập nhật tên người và ghi audit trong một transaction:

```java
public record PersonName(String personId, String name) {
}

@Service
public class PersonCommandService {

    private final ReactiveNeo4jClient neo4jClient;

    public PersonCommandService(ReactiveNeo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    @Transactional
    public Mono<PersonName> renameAndAudit(
            String personId,
            String newName) {

        return neo4jClient.query("""
                MATCH (p:Person {personId: $personId})
                SET p.name = $newName
                RETURN p.personId AS personId, p.name AS name
                """)
            .bind(personId).to("personId")
            .bind(newName).to("newName")
            .fetchAs(PersonName.class)
            .mappedBy((typeSystem, record) -> new PersonName(
                record.get("personId").asString(),
                record.get("name").asString()
            ))
            .one()
            .flatMap(updated -> neo4jClient.query("""
                    MATCH (p:Person {personId: $personId})
                    CREATE (event:AuditEvent {
                        eventType: 'PERSON_RENAMED',
                        createdAt: datetime(),
                        newName: $newName
                    })
                    CREATE (event)-[:ABOUT]->(p)
                    """)
                .bind(personId).to("personId")
                .bind(newName).to("newName")
                .run()
                .thenReturn(updated));
    }
}
```

Hai truy vấn nằm trong cùng reactive chain. Nếu truy vấn audit phát lỗi, lỗi đi xuống publisher và transaction reactive có thể rollback thay đổi tên người. Nếu query đầu không tìm thấy `Person`, `one()` hoàn tất rỗng; `flatMap` không chạy bước tạo audit.

Điều kiện để transaction hoạt động đúng:

- Có `ReactiveNeo4jTransactionManager` được cấu hình.
- `ReactiveNeo4jClient` dùng cùng `Driver` và database selection tương ứng.
- Phương thức đi qua Spring transaction proxy.
- Publisher được trả về cho caller và được subscribe trong phạm vi lời gọi được quản lý.
- Không tách thao tác database sang một subscription độc lập bên trong method.

Nếu ứng dụng có nhiều transaction manager, chỉ rõ bean reactive Neo4j:

```java
@Transactional(transactionManager = "reactiveTransactionManager")
public Mono<PersonName> renameAndAudit(String personId, String newName) {
    // Reactive chain như ví dụ trên.
}
```

Tên bean phải khớp cấu hình thực tế. `@Transactional` trên method trả về `void` không tạo được cùng ngữ nghĩa reactive vì Spring không có publisher để quản lý vòng đời transaction.

## 11. Chọn database cho truy vấn

Client dùng database mặc định theo cấu hình SDN. Nếu cần chọn database cụ thể, có thể gọi `.in("databaseName")` sau `query(...)`:

```java
Flux<Map<String, Object>> actors = neo4jClient
    .query("MATCH (p:Person) RETURN p.name AS name ORDER BY name")
    .in("movies")
    .fetch()
    .all();
```

Trong transaction được quản lý, database selection của truy vấn phải nhất quán với database mà transaction manager đã chọn. Nếu ứng dụng dùng `ReactiveDatabaseSelectionProvider` theo tenant, hãy dùng cùng provider cho client và transaction manager. Không chuyển sang database khác giữa một transaction rồi kỳ vọng các truy vấn vẫn thuộc cùng transaction.

## 12. Xây dựng Cypher động an toàn

Client nhận `Supplier<String>` khi muốn tạo Cypher trễ hoặc dùng query builder:

```java
return neo4jClient.query(() -> queryBuilder.build())
    .bindAll(parameters)
    .fetch()
    .all();
```

Supplier chỉ trì hoãn việc tạo chuỗi; nó không tự làm cho query an toàn. Giá trị dữ liệu vẫn phải bind qua parameter. Nếu query builder thêm label, relationship type, property name hoặc sort expression, các thành phần này phải đến từ metadata hoặc whitelist do ứng dụng kiểm soát.

Với filter tùy chọn, có thể giữ một câu query và bind `null` cho điều kiện không dùng:

```cypher
MATCH (p:Person)
WHERE ($namePart IS NULL OR toLower(p.name) CONTAINS toLower($namePart))
  AND ($born IS NULL OR p.born = $born)
RETURN p.personId AS personId, p.name AS name
ORDER BY p.name, p.personId;
```

Nếu filter nhiều nhánh hoặc làm truy vấn khó tối ưu, hãy tạo một số biến thể Cypher từ whitelist rõ ràng và bind mọi giá trị. Dùng `EXPLAIN` hoặc `PROFILE` để kiểm tra kế hoạch truy vấn trên dữ liệu thực tế.

## 13. Backpressure, giới hạn kết quả và bộ nhớ

`Flux<T>` cho phép downstream yêu cầu dữ liệu theo nhịp tiêu thụ. Tuy vậy, việc dùng `collectList()` sẽ materialize toàn bộ kết quả thành một `List` trong bộ nhớ:

```java
Mono<List<MovieSummary>> allMovies = findMovieSummaries()
    .collectList();
```

Chỉ dùng cách này khi tập kết quả có giới hạn hợp lý. Với dữ liệu lớn:

- Thêm điều kiện lọc và `LIMIT` trong Cypher.
- Phân trang theo thứ tự xác định, có khóa phụ duy nhất.
- Trả `Flux` để xử lý từng hàng thay vì gom tất cả.
- Tránh chuyển `Flux` thành `List` sớm trong tầng repository/service.
- Theo dõi cancellation và đảm bảo không tạo publisher bị subscribe nhiều lần.

Backpressure không tự thay thế pagination ở database. Nếu query vẫn yêu cầu Neo4j tìm và sắp xếp hàng triệu kết quả, chỉ phát từng phần tử xuống downstream không làm biến mất chi phí thực thi ở database.

## 14. Xử lý lỗi trong reactive query

Lỗi từ driver hoặc Cypher được phát thành error signal trong Reactor. Có thể chuyển đổi lỗi ở service bằng `onErrorMap`:

```java
public Mono<PersonName> rename(String personId, String newName) {
    return runRenameQuery(personId, newName)
        .onErrorMap(
            Neo4jException.class,
            ex -> new PersonGraphException("Cannot rename person", ex)
        );
}
```

Nếu transaction cần rollback, đừng nuốt lỗi bằng `onErrorResume` rồi thay bằng một giá trị thành công giả. Khi cần trả fallback, hãy hiểu rằng việc chuyển error signal thành completion bình thường có thể khiến transaction được commit nếu không có rollback-only marker.

Với thao tác ghi, cân nhắc tính idempotent trước khi dùng `retry`. Retry có thể thực hiện lại query sau lỗi mạng hoặc lỗi tạm thời. `MERGE` theo khóa nghiệp vụ, uniqueness constraint và thiết kế command idempotent giúp giảm nguy cơ tạo dữ liệu trùng; không retry mù quáng một lệnh `CREATE` không có khóa nhận diện.

## 15. Delegate xuống reactive driver runner

Khi fluent API không đủ và cần dùng API driver reactive ở mức thấp hơn, `ReactiveNeo4jClient` cung cấp `delegateTo(...)`. Callback nhận `ReactiveQueryRunner` và trả về một `Mono`:

```java
public Mono<Long> countPeople() {
    return neo4jClient.delegateTo(runner ->
        Flux.from(runner.run(
                "MATCH (p:Person) RETURN count(p) AS total")
            .records())
            .map(record -> record.get("total").asLong())
            .single()
    ).run();
}
```

Đoạn code cần import `reactor.core.publisher.Flux`. Đây là API cấp thấp hơn; callback phải tuân theo reactive streams và không block. Trong phần lớn use case, `query(...).fetch()` hoặc `fetchAs(...).mappedBy(...)` dễ đọc và đủ dùng hơn. Chỉ dùng `delegateTo` khi cần khả năng driver không được bộc lộ qua fluent API.

## 16. Kiểm thử bằng StepVerifier

Vì query chỉ thực thi khi subscribe, kiểm thử reactive nên dùng `StepVerifier`:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import reactor.test.StepVerifier;

@SpringBootTest
class MovieQueryServiceTest {

    @Autowired
    MovieQueryService movieQueryService;

    @Test
    void shouldReturnMovieSummaries() {
        // Giả định fixture đã tạo ít nhất một Movie trong database test.
        StepVerifier.create(movieQueryService.findMovieSummaries())
            .expectNextMatches(summary ->
                summary.title() != null && summary.actorCount() >= 0
            )
            .thenConsumeWhile(summary -> true)
            .verifyComplete();
    }
}
```

Với dữ liệu fixture xác định, nên kiểm tra chính xác số hàng và nội dung thay vì chỉ kiểm tra một điều kiện tổng quát. Có thể dùng `expectNext(...)`, `expectNextCount(...)`, `expectError(...)` hoặc `verifyComplete()` để kiểm tra các trường hợp tương ứng.

Khi kiểm tra transaction, tạo một service method gồm nhiều truy vấn ghi, cố ý phát error signal sau bước đầu và xác nhận bằng một truy vấn mới rằng dữ liệu đã rollback. Không gọi `.subscribe()` trong method đang được kiểm tra vì test cần điều khiển subscription và quan sát kết quả.

## 17. Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `Neo4jClient` imperative trong reactive flow | Gọi database đồng bộ và có thể block thread | Dùng `ReactiveNeo4jClient` |
| Gọi `.subscribe()` trong service | Tách query khỏi lifecycle của caller và transaction | Trả `Mono`/`Flux` cho tầng trên |
| Gọi `.block()` trên event-loop | Chặn luồng xử lý reactive | Giữ publisher xuyên suốt ứng dụng |
| Nghĩ query chạy ngay khi gọi `query()` | Bỏ qua tính lazy của publisher | Chỉ coi query thực thi khi publisher được subscribe |
| Dùng `one()` cho query nhiều hàng | Phát lỗi khi có hơn một hàng | Dùng `all()` hoặc `first()` với `ORDER BY` |
| Dùng `first()` không có `ORDER BY` | Hàng được chọn không xác định theo nghiệp vụ | Sắp xếp rõ ràng và thêm tie-breaker |
| Quên bind placeholder | Driver báo thiếu tham số lúc thực thi | Đối chiếu `$name` với `.to("name")` hoặc `bindAll` |
| Dùng parameter cho label/property | Cypher không thay identifier bằng parameter | Chọn identifier từ whitelist và bind giá trị |
| Trả DTO nhưng gọi `fetch()` mặc định | Nhận map thay vì DTO mong muốn | Dùng `fetchAs(...).mappedBy(...)` |
| Đọc `Value` có thể null bằng `asString()` ngay | Lỗi chuyển đổi runtime | Kiểm tra `isNull()` trước |
| `@Transactional` nhưng thiếu ReactiveNeo4jTransactionManager | Không có reactive transaction manager phù hợp | Khai báo bean manager dùng cùng Driver |
| Client và manager khác database selection | Query không thuộc transaction/database mong muốn | Dùng cùng provider và chọn cùng database |
| `collectList()` trên kết quả lớn | Tăng bộ nhớ theo toàn bộ kết quả | Dùng `Flux`, filter và LIMIT ở Cypher |
| Retry lệnh CREATE không idempotent | Có thể tạo dữ liệu trùng | Thiết kế MERGE theo khóa và uniqueness constraint |

## 18. Checklist trước khi dùng ReactiveNeo4jClient

- Inject `ReactiveNeo4jClient` do Spring quản lý.
- Nếu dùng `@Transactional`, cấu hình `ReactiveNeo4jTransactionManager` với cùng `Driver` và database selection.
- Viết Cypher có named parameter và bind mọi giá trị đầu vào.
- Không ghép trực tiếp input vào label, property, relationship type hoặc sort expression.
- Chọn `one()`, `first()`, `all()` hoặc `run()` theo hình dạng kết quả.
- Thêm `ORDER BY` khi thứ tự kết quả ảnh hưởng nghiệp vụ.
- Dùng `fetchAs(...).mappedBy(...)` cho DTO hoặc mapping tùy chỉnh.
- Kiểm tra null và kiểu dữ liệu của từng `Value`.
- Trả publisher; không tự subscribe hoặc block trong service.
- Giữ các truy vấn thuộc một transaction trong cùng reactive chain.
- Không nuốt error signal nếu cần rollback.
- Giới hạn kết quả ở database và tránh `collectList()` trên tập dữ liệu lớn.
- Kiểm thử bằng `StepVerifier`, gồm trường hợp thành công, không có hàng và lỗi/rollback.

## 19. Bài tập thực hành

1. Viết query tìm `Movie` theo năm phát hành và trả về `Flux<Map<String, Object>>` bằng `fetch().all()`.
2. Viết query tìm một `Person` theo `personId`; giải thích khi nào dùng `one()` và khi nào dùng `first()`.
3. Viết `MovieSummary` bằng Java record và ánh xạ kết quả `count(DISTINCT p)` qua `fetchAs().mappedBy()`.
4. Viết lệnh `MERGE` tạo relationship `ACTED_IN` và đọc số relationship được tạo từ `ResultSummary`.
5. Viết query có filter tùy chọn `namePart` và `born`; bind `null` cho điều kiện không sử dụng.
6. Viết một service method `@Transactional` đổi tên `Person` rồi tạo `AuditEvent` bằng truy vấn thứ hai; dùng `flatMap` để nối hai thao tác.
7. Cố ý phát lỗi sau truy vấn đầu và dùng integration test xác nhận transaction reactive rollback.
8. Viết query chọn database bằng `.in(...)` và giải thích vì sao database selection phải khớp transaction manager.
9. Viết truy vấn trả nhiều hàng, dùng `Flux` để xử lý tuần tự và so sánh với `collectList()`.
10. Viết một query builder có sort field động; chỉ cho phép các field trong whitelist và bind mọi giá trị còn lại.
11. Dùng `StepVerifier` kiểm tra kết quả thành công, publisher rỗng và error signal.
12. Dùng `delegateTo()` để đọc `count(p)` bằng reactive driver runner; giải thích vì sao callback không được block.

Khi hoàn thành, bạn cần biết xây dựng truy vấn tùy chỉnh bằng `ReactiveNeo4jClient`, bind tham số an toàn, chọn terminal operation, ánh xạ `Record` sang DTO và kết hợp nhiều truy vấn trong một reactive transaction. Quan trọng nhất, hãy giữ publisher trong cùng reactive flow để subscription, backpressure, lỗi và transaction được quản lý xuyên suốt.

## Tài liệu tham khảo

- [Spring Data Neo4j — Neo4jClient và ReactiveNeo4jClient](https://docs.spring.io/spring-data/neo4j/reference/appendix/neo4j-client.html)
- [Spring Data Neo4j — ReactiveNeo4jClient API 8.1.2](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/ReactiveNeo4jClient.html)
- [Spring Data Neo4j — ReactiveNeo4jClient.RecordFetchSpec API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/ReactiveNeo4jClient.RecordFetchSpec.html)
- [Spring Data Neo4j — FAQ và cấu hình reactive](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Boot — Working with Neo4j](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
