# run, ResultSummary và số node/relationship bị thay đổi

Khi dùng `Neo4jClient` để chạy câu lệnh Cypher chỉ ghi dữ liệu, ứng dụng thường không cần nhận danh sách record. Thay vào đó, gọi `run()` để thực thi câu lệnh và nhận `ResultSummary`. Summary này cho biết truy vấn đã tạo hoặc xóa bao nhiêu node, tạo hoặc xóa bao nhiêu relationship, đặt bao nhiêu property và thay đổi schema ra sao.

Trong module `SPRING_DATA_NEO4J`, các số liệu này hữu ích để trả kết quả cho thao tác ghi, ghi log vận hành, kiểm tra tác động của câu lệnh bảo trì và phân biệt số entity được match với số phần tử graph thực sự thay đổi. `ResultSummary` thuộc Neo4j Java Driver và được `Neo4jClient` trả về sau khi câu lệnh hoàn tất; nó không phải một entity hay một kết quả truy vấn để ánh xạ bằng `@Node`.

## 1. Khi nào dùng run()?

API imperative `Neo4jClient` kết thúc một truy vấn bằng một trong hai hướng:

- Dùng `fetch()` khi cần đọc record, ví dụ `.one()`, `.first()` hoặc `.all()`.
- Dùng `run()` khi không mong đợi record và chỉ cần thực thi câu lệnh cùng summary.

Ví dụ, câu lệnh `CREATE`, `SET`, `DELETE` không có `RETURN` phù hợp với `run()`:

```java
import org.neo4j.driver.summary.ResultSummary;
import org.springframework.data.neo4j.core.Neo4jClient;

// neo4jClient được inject qua constructor của service.
ResultSummary summary = neo4jClient.query("""
        CREATE (:Person {id: $id, name: $name})
        """)
    .bind(personId).to("id")
    .bind(personName).to("name")
    .run();
```

`run()` thực thi truy vấn imperative ngay tại lời gọi và trả về `ResultSummary`. Nếu truy vấn cần trả về node, relationship hoặc scalar để ứng dụng xử lý, hãy dùng `fetch()` thay vì `run()`.

Một câu lệnh có `RETURN` thường được viết theo dạng:

```java
import java.util.List;
import org.springframework.data.neo4j.core.Neo4jClient;

List<String> names = neo4jClient.query("""
        MATCH (p:Person)
        RETURN p.name AS name
        """)
    .fetchAs(String.class)
    .mappedBy((typeSystem, record) -> record.get("name").asString())
    .all();
```

Truy vấn trên cần dữ liệu từ record, do đó kết thúc bằng `.all()`. Không nên chọn `run()` chỉ vì câu lệnh có `MATCH`; hãy căn cứ vào việc use case có cần đọc các record được trả về hay không.

## 2. ResultSummary là gì?

`ResultSummary` nằm trong package `org.neo4j.driver.summary`. Đây là metadata do Neo4j trả về sau khi thực thi và tiêu thụ kết quả của một query. Nó cung cấp thông tin về câu truy vấn, database/server, loại query, thời gian xử lý, counters và query plan/profile nếu có.

Các thông tin thường dùng:

| API | Ý nghĩa |
|---|---|
| `summary.counters()` | Lấy các bộ đếm thay đổi do query tạo ra |
| `summary.query()` | Câu query đã thực thi |
| `summary.queryType()` | Loại query được server phân loại |
| `summary.database()` | Thông tin database thực thi query |
| `summary.server()` | Thông tin server xử lý query |
| `summary.resultAvailableAfter(unit)` | Thời gian server cần để kết quả sẵn sàng |
| `summary.resultConsumedAfter(unit)` | Thời gian server cần để tiêu thụ hết kết quả |
| `summary.queryPlan()` | Plan nếu query được chạy với `EXPLAIN` và plan có sẵn |
| `summary.queryProfile()` | Profile nếu query được chạy với `PROFILE` và profile có sẵn |

Đối với câu lệnh ghi không trả record, `run()` là cách trực tiếp để lấy summary. Với API driver mức thấp, `ResultSummary` chỉ có sau khi result đã được consume; khi dùng `Neo4jClient.run()`, framework thực hiện phần tiêu thụ cần thiết và trả summary cho ứng dụng.

`resultAvailableAfter` và `resultConsumedAfter` là thời gian phía server, không phải tổng thời gian end-to-end của request HTTP. Độ trễ ở ứng dụng còn có thể bao gồm mạng, connection pool, mapping, transaction và xử lý nghiệp vụ.

## 3. Các counter quan trọng

`summary.counters()` trả về `SummaryCounters`. Những counter quan trọng nhất khi theo dõi thay đổi graph:

| Phương thức | Số lượng được đếm |
|---|---|
| `nodesCreated()` | Node được tạo |
| `nodesDeleted()` | Node bị xóa |
| `relationshipsCreated()` | Relationship được tạo |
| `relationshipsDeleted()` | Relationship bị xóa |
| `propertiesSet()` | Property được đặt trên node hoặc relationship |
| `labelsAdded()` | Label được thêm vào node |
| `labelsRemoved()` | Label bị gỡ khỏi node |
| `indexesAdded()` / `indexesRemoved()` | Index được thêm hoặc gỡ |
| `constraintsAdded()` / `constraintsRemoved()` | Constraint được thêm hoặc gỡ |
| `containsUpdates()` | Query có thực hiện thay đổi dữ liệu/schema hay không |
| `containsSystemUpdates()` | Query có thay đổi system graph hay không |

Các phương thức đếm trả về số nguyên. `containsUpdates()` và `containsSystemUpdates()` là các cờ tổng quát, hữu ích khi không cần kiểm tra từng counter.

Ví dụ lấy số node và relationship được tạo:

```java
import org.neo4j.driver.summary.ResultSummary;
import org.neo4j.driver.summary.SummaryCounters;
import org.springframework.data.neo4j.core.Neo4jClient;

// neo4jClient được inject qua constructor của service.
ResultSummary summary = neo4jClient.query("""
        CREATE (a:Person {name: $name})
        CREATE (b:Person {name: $friendName})
        CREATE (a)-[:KNOWS]->(b)
        """)
    .bind("An").to("name")
    .bind("Bình").to("friendName")
    .run();

SummaryCounters counters = summary.counters();

int nodesCreated = counters.nodesCreated();
int relationshipsCreated = counters.relationshipsCreated();
```

Nếu dữ liệu ban đầu chưa có, ví dụ trên tạo hai node và một relationship. Số liệu thực tế phụ thuộc câu lệnh và dữ liệu đang có trong database.

## 4. Đóng gói summary thành kết quả nghiệp vụ

Không nhất thiết trả toàn bộ đối tượng `ResultSummary` ra controller. Service có thể chuyển những counter cần thiết thành DTO ổn định của ứng dụng:

```java
public record GraphWriteReport(
    int nodesCreated,
    int nodesDeleted,
    int relationshipsCreated,
    int relationshipsDeleted,
    int propertiesSet,
    boolean containsUpdates
) {
}
```

Service sử dụng `Neo4jClient`:

```java
import org.neo4j.driver.summary.ResultSummary;
import org.neo4j.driver.summary.SummaryCounters;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;

@Service
public class PersonGraphCommandService {

    private final Neo4jClient neo4jClient;

    public PersonGraphCommandService(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public GraphWriteReport createConnection(
        String personId,
        String personName,
        String friendId,
        String friendName
    ) {
        ResultSummary summary = neo4jClient.query("""
                CREATE (p:Person {id: $personId, name: $personName})
                CREATE (f:Person {id: $friendId, name: $friendName})
                CREATE (p)-[:KNOWS]->(f)
                """)
            .bind(personId).to("personId")
            .bind(personName).to("personName")
            .bind(friendId).to("friendId")
            .bind(friendName).to("friendName")
            .run();

        SummaryCounters counters = summary.counters();
        return new GraphWriteReport(
            counters.nodesCreated(),
            counters.nodesDeleted(),
            counters.relationshipsCreated(),
            counters.relationshipsDeleted(),
            counters.propertiesSet(),
            counters.containsUpdates()
        );
    }
}
```

DTO chỉ giữ những dữ liệu mà tầng ứng dụng cần. Nếu muốn ghi log hoặc đo lường, có thể lấy thêm `resultAvailableAfter()` và `resultConsumedAfter()` với đơn vị thời gian phù hợp.

## 5. Đọc counter khi tạo và cập nhật graph

### CREATE và MERGE

`CREATE` tạo phần tử mới mỗi lần pattern được thực thi. `MERGE` tìm phần tử phù hợp và chỉ tạo phần tử khi chưa tồn tại. Vì vậy, counter của `MERGE` phụ thuộc trạng thái dữ liệu:

```java
import org.neo4j.driver.summary.ResultSummary;
import org.neo4j.driver.summary.SummaryCounters;
import org.springframework.data.neo4j.core.Neo4jClient;

// neo4jClient được inject qua constructor của service.
ResultSummary summary = neo4jClient.query("""
        MERGE (p:Person {id: $id})
        ON CREATE SET p.name = $name
        ON MATCH SET p.lastSeen = datetime()
        """)
    .bind(personId).to("id")
    .bind(personName).to("name")
    .run();

SummaryCounters counters = summary.counters();
```

Nếu node chưa tồn tại, `nodesCreated()` có thể tăng. Nếu node đã tồn tại, không có node mới được tạo; `propertiesSet()` có thể tăng do `lastSeen` được cập nhật. Đừng suy ra số lần query match từ `nodesCreated()`.

### SET property và label

```java
import org.neo4j.driver.summary.ResultSummary;
import org.neo4j.driver.summary.SummaryCounters;
import org.springframework.data.neo4j.core.Neo4jClient;

// neo4jClient được inject qua constructor của service.
ResultSummary summary = neo4jClient.query("""
        MATCH (p:Person {id: $id})
        SET p.name = $name,
            p.active = true
        SET p:VerifiedPerson
        """)
    .bind(personId).to("id")
    .bind(personName).to("name")
    .run();

SummaryCounters counters = summary.counters();
int propertiesSet = counters.propertiesSet();
int labelsAdded = counters.labelsAdded();
```

`propertiesSet()` phản ánh số thao tác đặt property trên cả node và relationship. `labelsAdded()` đếm label được thêm vào node. Nếu node không tồn tại nên `MATCH` không tạo dòng nào, các counter thay đổi tương ứng sẽ là `0`.

## 6. Đọc counter khi xóa relationship và node

### Chỉ xóa relationship

Nếu mục tiêu là gỡ cạnh `KNOWS` nhưng giữ hai node:

```java
import org.neo4j.driver.summary.ResultSummary;
import org.springframework.data.neo4j.core.Neo4jClient;

// neo4jClient được inject qua constructor của service.
ResultSummary summary = neo4jClient.query("""
        MATCH (p:Person {id: $personId})-[r:KNOWS]->(f:Person {id: $friendId})
        DELETE r
        """)
    .bind(personId).to("personId")
    .bind(friendId).to("friendId")
    .run();

int relationshipsDeleted = summary.counters().relationshipsDeleted();
```

Nếu có một relationship phù hợp, counter `relationshipsDeleted()` tăng tương ứng. `nodesDeleted()` vẫn là `0` vì câu lệnh chỉ xóa cạnh.

### Xóa node cùng các relationship kề

```java
import org.neo4j.driver.summary.ResultSummary;
import org.neo4j.driver.summary.SummaryCounters;
import org.springframework.data.neo4j.core.Neo4jClient;

// neo4jClient được inject qua constructor của service.
ResultSummary summary = neo4jClient.query("""
        MATCH (p:Person {id: $personId})
        DETACH DELETE p
        """)
    .bind(personId).to("personId")
    .run();

SummaryCounters counters = summary.counters();
int nodesDeleted = counters.nodesDeleted();
int relationshipsDeleted = counters.relationshipsDeleted();
```

`DETACH DELETE` xóa node được match cùng các relationship kề với node đó. Vì vậy, một thao tác xóa node có thể đồng thời làm tăng cả `nodesDeleted()` và `relationshipsDeleted()`. Nếu dùng `DELETE p` trong khi node vẫn còn relationship, Neo4j từ chối xóa; hãy chỉ dùng `DETACH DELETE` khi nghiệp vụ thực sự cho phép gỡ mọi cạnh kề.

## 7. Counter không phải số record hoặc số entity được match

Một truy vấn có thể match nhiều record nhưng không tạo node mới. Ngược lại, một record có thể tạo nhiều node hoặc relationship qua `UNWIND` hay pattern nhiều phần tử.

Ví dụ:

```cypher
UNWIND $names AS name
CREATE (:Person {name: name})
```

Nếu `$names` có bốn phần tử, một câu query có thể tạo bốn node. `nodesCreated()` trả số node được tạo, không phải số record trả về cho client.

Phân biệt các loại số liệu:

| Số liệu | Trả lời câu hỏi |
|---|---|
| `records.size()` | Query trả về bao nhiêu record? |
| `nodesCreated()` | Query tạo bao nhiêu node? |
| `nodesDeleted()` | Query xóa bao nhiêu node? |
| `relationshipsCreated()` | Query tạo bao nhiêu relationship? |
| `relationshipsDeleted()` | Query xóa bao nhiêu relationship? |
| `propertiesSet()` | Query đặt bao nhiêu property? |

Không dùng số record trả về để báo số node hoặc relationship đã thay đổi. Khi cần cả hai, hãy dùng truy vấn trả record qua `fetch()` và chọn cách thống kê phù hợp, hoặc chạy một query ghi không trả record và đọc counters từ `ResultSummary`.

## 8. Transaction và ý nghĩa của summary

`ResultSummary` mô tả kết quả thực thi của câu lệnh. Trong một service có transaction bao ngoài, query có thể chạy thành công và trả counters trước khi transaction của service được commit:

```java
import org.neo4j.driver.summary.ResultSummary;
import org.neo4j.driver.summary.SummaryCounters;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonImportService {

    private final Neo4jClient neo4jClient;

    public PersonImportService(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    @Transactional
    public GraphWriteReport importPerson(String id, String name) {
        ResultSummary summary = neo4jClient.query("""
                CREATE (:Person {id: $id, name: $name})
                """)
            .bind(id).to("id")
            .bind(name).to("name")
            .run();

        SummaryCounters counters = summary.counters();
        return new GraphWriteReport(
            counters.nodesCreated(),
            counters.nodesDeleted(),
            counters.relationshipsCreated(),
            counters.relationshipsDeleted(),
            counters.propertiesSet(),
            counters.containsUpdates()
        );
    }
}
```

Nếu một thao tác sau đó làm transaction rollback, các thay đổi trong transaction không được commit dù câu lệnh trước đó đã trả summary. Vì vậy, counters là bằng chứng về tác động của query trong transaction tại thời điểm thực thi, không phải biên nhận commit cuối cùng. Khi cần thông báo trạng thái đã lưu bền vững, chỉ phát sự kiện hoặc trả xác nhận sau khi ranh giới transaction hoàn tất thành công.

Không bắt exception rồi vẫn trả report như thể query đã thành công. Nếu query lỗi, `run()` ném exception và không có `ResultSummary` hợp lệ để đọc. Hãy để exception đi qua transaction boundary hoặc chuyển thành lỗi nghiệp vụ theo chính sách của ứng dụng.

## 9. Reactive Neo4jClient

Với reactive client, chữ ký `run()` khác imperative client:

```java
import reactor.core.publisher.Mono;
import org.neo4j.driver.summary.ResultSummary;
import org.springframework.data.neo4j.core.ReactiveNeo4jClient;

// reactiveNeo4jClient được inject qua constructor của service.
Mono<ResultSummary> summaryPublisher = reactiveNeo4jClient
    .query("CREATE (:Person {id: $id, name: $name})")
    .bind(personId).to("id")
    .bind(personName).to("name")
    .run();
```

`run()` trả `Mono<ResultSummary>`. Query chỉ thực sự được thực thi khi publisher được subscribe hoặc được compose vào một pipeline có subscriber. Không gọi `block()` trong luồng xử lý reactive để chờ kết quả; hãy chuyển summary thành DTO ngay trong pipeline:

```java
Mono<GraphWriteReport> report = reactiveNeo4jClient
    .query("CREATE (:Person {id: $id, name: $name})")
    .bind(personId).to("id")
    .bind(personName).to("name")
    .run()
    .map(ResultSummary::counters)
    .map(counters -> new GraphWriteReport(
        counters.nodesCreated(),
        counters.nodesDeleted(),
        counters.relationshipsCreated(),
        counters.relationshipsDeleted(),
        counters.propertiesSet(),
        counters.containsUpdates()
    ));
```

Reactive API thực thi khi subscribe; chỉ tạo `Mono` rồi bỏ đó sẽ không chạy query. Giữ pipeline non-blocking để transaction reactive và backpressure hoạt động đúng.

## 10. Timing, plan và profile trong ResultSummary

Ngoài counters, summary còn cung cấp thông tin phục vụ chẩn đoán:

```java
import java.util.concurrent.TimeUnit;

long availableMs = summary.resultAvailableAfter(TimeUnit.MILLISECONDS);
long consumedMs = summary.resultConsumedAfter(TimeUnit.MILLISECONDS);
```

`resultAvailableAfter` đo thời gian phía server đến khi kết quả sẵn sàng; `resultConsumedAfter` đo thời gian phía server để tiêu thụ hết kết quả. Với query ghi không trả record, hai giá trị giúp quan sát thời gian xử lý phía server nhưng không thay thế metrics tổng thể của ứng dụng.

Để xem kế hoạch mà Neo4j dự kiến dùng, chạy `EXPLAIN` và kiểm tra `summary.queryPlan()`. Để xem thông tin profile thực tế, chạy `PROFILE` trong môi trường phù hợp và kiểm tra `summary.queryProfile()`. Hai API trả `Optional`, vì vậy không phải summary nào cũng có plan hoặc profile.

Không nên chạy `PROFILE` một cách tùy tiện cho thao tác ghi trên production: `PROFILE` thực thi query thật. Với thao tác ghi, chỉ profile trên dữ liệu và môi trường có thể kiểm soát.

## 11. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không lấy được record sau `run()` | `run()` dành cho query không mong đợi kết quả record | Dùng `fetch().one()`, `first()` hoặc `all()` khi cần đọc |
| Không có `ResultSummary` | Query ném lỗi trước khi hoàn tất | Xử lý exception và kiểm tra Cypher, parameter, constraint |
| `nodesCreated()` bằng 0 dù query chạy | Query chỉ cập nhật property, match không có node hoặc `MERGE` tìm thấy node cũ | Kiểm tra tất cả counters và dữ liệu trước khi chạy |
| `relationshipsDeleted()` tăng khi xóa node | `DETACH DELETE` xóa cả các cạnh kề | Diễn giải đồng thời `nodesDeleted()` và `relationshipsDeleted()` |
| `nodesDeleted()` bằng 0 nhưng query không lỗi | Không có node nào khớp pattern `MATCH` | Kiểm tra điều kiện và ID truyền vào |
| `propertiesSet()` lớn hơn số node | Mỗi node hoặc relationship có thể đặt nhiều property | Đọc counter theo đúng loại thay đổi, không xem đây là số node |
| `containsUpdates()` là false | Query không làm thay đổi dữ liệu/schema | Kiểm tra query có thực sự ghi hoặc có match được dữ liệu không |
| Reactive query không chạy | `Mono<ResultSummary>` chưa được subscribe/compose | Trả publisher cho tầng gọi hoặc ghép vào pipeline reactive |
| Report báo thành công nhưng dữ liệu không còn | Transaction bao ngoài đã rollback sau khi summary được tạo | Chỉ xác nhận commit sau khi transaction boundary hoàn tất |

## 12. Tự kiểm tra

1. Khi nào nên kết thúc truy vấn `Neo4jClient` bằng `run()` thay vì `fetch()`?
2. `ResultSummary` nằm trong package nào và được trả về khi nào?
3. Phân biệt `nodesCreated()` với số record query trả về.
4. Khi xóa một relationship mà giữ nguyên hai node, counter nào cần kiểm tra?
5. Vì sao `DETACH DELETE` có thể làm tăng cả `nodesDeleted()` và `relationshipsDeleted()`?
6. `propertiesSet()` có phải số node được cập nhật không? Vì sao?
7. Reactive `run()` trả về kiểu gì và khi nào query được thực thi?
8. Vì sao counters không phải bằng chứng transaction bao ngoài đã commit?

`run()` là lựa chọn dành cho câu lệnh không cần record và trả `ResultSummary` để kiểm tra tác động của query. Dùng `SummaryCounters` để đọc số node, relationship, property và thay đổi schema; phân biệt rõ counters với số record hoặc số entity được match. Với reactive client, xử lý `Mono<ResultSummary>` trong pipeline; với transaction bao ngoài, chỉ xác nhận dữ liệu đã commit sau khi transaction hoàn tất.

## Tài liệu tham khảo

- [Spring Data Neo4j — Neo4jClient: retrieving result summaries](https://docs.spring.io/spring-data/neo4j/reference/appendix/neo4j-client.html)
- [Neo4j Java Driver — ResultSummary API](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/summary/ResultSummary.html)
- [Neo4j Java Driver — SummaryCounters API](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/summary/SummaryCounters.html)
- [Neo4j Java Driver Manual — Explore the query execution summary](https://neo4j.com/docs/java-manual/current/result-summary/)
