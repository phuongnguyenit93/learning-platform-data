# Ủy quyền thao tác driver khi cần truy cập mức thấp

`Neo4jClient` cung cấp API fluent để viết Cypher, bind tham số và ánh xạ kết quả. Phần lớn truy vấn ứng dụng có thể dùng trực tiếp API này. Tuy nhiên, đôi khi use case cần kiểm soát chi tiết hơn cách chạy statement, đọc `Record`, lấy `ResultSummary` hoặc thực hiện nhiều thao tác Driver trong cùng một callback. Khi đó, `Neo4jClient.delegateTo(...)` cho phép ủy quyền phần tương tác database cho Neo4j Java Driver thông qua một query runner do Spring quản lý.

Điểm quan trọng là runner được ủy quyền có thể tham gia transaction Spring hiện tại. Nếu tự tạo session hoặc transaction mới bằng `Driver` bên trong một phương thức `@Transactional`, thao tác đó có thể chạy ngoài transaction đang quản lý bởi Spring. Vì vậy, khi cần API mức thấp mà vẫn muốn giữ transaction integration, hãy ưu tiên runner do `Neo4jClient` cung cấp.

## 1. Khi nào cần truy cập mức thấp?

`Neo4jClient.query(...).fetch()` và `fetchAs(...).mappedBy(...)` đã đáp ứng phần lớn nhu cầu đọc và ghi. Chỉ cân nhắc ủy quyền khi cần một khả năng cụ thể mà API fluent không diễn đạt thuận tiện, ví dụ:

- Thực hiện nhiều lần gọi `runner.run(...)` trong cùng callback.
- Đọc trực tiếp `Record` và dùng các phương thức của Neo4j Java Driver.
- Lấy `ResultSummary` và các counter của thao tác ghi.
- Tận dụng một API nhận `QueryRunner` hoặc `ReactiveQueryRunner`, chẳng hạn một tiện ích nội bộ hoặc tích hợp Cypher-DSL.
- Kiểm soát rõ cách tiêu thụ kết quả và chuyển đổi dữ liệu ở cấp Driver.

Không cần dùng `delegateTo` chỉ để chạy một câu `MATCH` đơn giản, bind vài tham số hoặc map một DTO. Với các trường hợp đó, API `query`, `bind`, `fetchAs` và `run` của `Neo4jClient` dễ đọc hơn.

## 2. delegateTo() hoạt động như thế nào?

Với imperative `Neo4jClient`, `delegateTo(...)` nhận callback sử dụng một `QueryRunner`. Callback trả về `Optional<T>`, sau đó gọi `.run()` để thực thi phần ủy quyền và nhận kết quả:

```java
Optional<Long> count = neo4jClient
        .delegateTo(runner -> {
            long total = runner
                    .run("MATCH (n) RETURN count(n) AS total")
                    .single()
                    .get("total")
                    .asLong();

            return Optional.of(total);
        })
        .run();
```

Các thành phần trong ví dụ:

- `delegateTo(...)` chuyển quyền thực hiện truy vấn cho callback.
- `runner` là query runner được Neo4jClient cung cấp; nó tương thích với API truy vấn mức thấp của Neo4j Java Driver.
- `runner.run(...)` thực thi Cypher và trả về kết quả Driver.
- `single()` đọc một record và yêu cầu kết quả có đúng một record.
- `Optional.of(total)` trả kết quả cho lời gọi bên ngoài.
- `.run()` cuối cùng kích hoạt callback và trả về `Optional<Long>`.

Trong Spring Data Neo4j 8.1, kiểu callback được khai báo bằng `QueryRunner` của package `org.neo4j.driver`. Một số tài liệu tham khảo dùng tên `StatementRunner` để mô tả runner. Hãy đối chiếu chữ ký API của đúng phiên bản SDN mà dự án đang sử dụng.

## 3. Đọc Record và bind tham số bằng Driver API

Trong callback, dùng các overload của `QueryRunner.run(...)` để truyền Cypher cùng map tham số. Cách này vẫn giữ dữ liệu tách khỏi câu lệnh và tránh nối chuỗi đầu vào:

```java
import java.util.Map;
import java.util.Optional;

import org.springframework.stereotype.Repository;
import org.springframework.data.neo4j.core.Neo4jClient;

@Repository
public class PersonDriverReader {

    private final Neo4jClient neo4jClient;

    public PersonDriverReader(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public Optional<PersonSummary> findByEmail(String email) {
        return neo4jClient.delegateTo(runner -> {
            var result = runner.run("""
                    MATCH (p:Person {email: $email})
                    RETURN p.personId AS personId,
                           p.name AS name
                    """, Map.of("email", email));

            var records = result.list();
            if (records.isEmpty()) {
                return Optional.empty();
            }
            if (records.size() > 1) {
                throw new IllegalStateException("Email must identify one person");
            }

            var record = records.get(0);
            return Optional.of(new PersonSummary(
                    record.get("personId").asString(),
                    record.get("name").asString()));
        }).run();
    }
}
```

DTO nhận kết quả:

```java
public record PersonSummary(String personId, String name) {
}
```

`single()` phù hợp khi điều kiện truy vấn được bảo đảm trả đúng một record. Nếu không tìm thấy hoặc có nhiều hơn một record, thao tác này báo lỗi theo quy ước của Driver. Nếu kết quả có thể không tồn tại, hãy dùng cách đọc có kiểm soát như `list()` rồi xử lý danh sách rỗng hoặc dùng API kết quả phù hợp với phiên bản Driver.

`Map.of(...)` không chấp nhận key hoặc value null. Nếu tham số có thể null, hãy dùng một `Map` có thể chứa giá trị null theo yêu cầu của Driver và xác định rõ ý nghĩa null trong Cypher.

## 4. Thực hiện nhiều thao tác trong cùng callback

Một lợi ích của delegation là có thể thực hiện nhiều lệnh qua cùng runner trong một callback. Ví dụ, đọc số lượng node và lấy danh sách label:

```java
import java.util.List;
import java.util.Optional;

public record GraphOverview(long nodeCount, List<String> labels) {
}
```

```java
public Optional<GraphOverview> readOverview() {
    return neo4jClient.delegateTo(runner -> {
        long nodeCount = runner
                .run("MATCH (n) RETURN count(n) AS total")
                .single()
                .get("total")
                .asLong();

        List<String> labels = runner
                .run("CALL db.labels() YIELD label RETURN label ORDER BY label")
                .list(record -> record.get("label").asString());

        return Optional.of(new GraphOverview(nodeCount, labels));
    }).run();
}
```

Callback trả về một đối tượng tổng hợp từ hai kết quả Driver. Hãy tiêu thụ mỗi `Result` ngay trong callback bằng `single()`, `list(...)` hoặc `consume()`; không trả một `Result` chưa được tiêu thụ ra ngoài callback để dùng sau khi phạm vi delegation kết thúc.

Việc hai thao tác nằm trong cùng callback giúp chúng dùng runner được cung cấp cho cùng phạm vi tương tác. Nếu cần tính nguyên tử giữa nhiều lệnh, hãy gọi delegation trong transaction Spring đã cấu hình và bảo đảm transaction manager cùng Neo4jClient dùng chung Driver.

## 5. Lấy ResultSummary và các counter

Với lệnh ghi không cần `RETURN`, có thể đọc `ResultSummary` từ kết quả Driver để biết số node, relationship hoặc property đã thay đổi:

```java
import java.util.Map;
import java.util.Optional;

import org.neo4j.driver.summary.ResultSummary;

public Optional<Long> deactivatePerson(String personId) {
    return neo4jClient.delegateTo(runner -> {
        ResultSummary summary = runner.run("""
                MATCH (p:Person {personId: $personId})
                SET p.active = false,
                    p.updatedAt = datetime()
                """, Map.of("personId", personId))
                .consume();

        long propertiesSet = summary.counters().propertiesSet();
        return Optional.of(propertiesSet);
    }).run();
}
```

`consume()` tiêu thụ kết quả và trả về summary. `propertiesSet()` là số property đã được đặt trong transaction statement đó; nó không nhất thiết bằng số node được cập nhật vì một node có thể thay đổi nhiều property. Nếu cần biết có bao nhiêu node được cập nhật, hãy thiết kế query và counter phù hợp, hoặc trả về một số lượng rõ ràng từ Cypher.

Với truy vấn có `RETURN`, hãy đọc hết kết quả trước khi lấy summary. Với truy vấn không trả record, `consume()` là cách rõ ràng để hoàn tất và lấy thống kê thực thi.

## 6. Chọn database khi ủy quyền

Theo mặc định, `delegateTo` dùng database được cấu hình trong Neo4jClient. Nếu cần chạy trên database khác, có thể chọn database trước khi gọi `.run()`:

```java
Optional<Long> count = neo4jClient
        .delegateTo(runner -> {
            long total = runner
                    .run("MATCH (n) RETURN count(n) AS total")
                    .single()
                    .get("total")
                    .asLong();
            return Optional.of(total);
        })
        .in("analytics")
        .run();
```

Tên database phải là giá trị được ứng dụng tin cậy và có quyền truy cập. Không lấy trực tiếp tên database từ request rồi chuyển vào `.in(...)` mà không kiểm tra danh sách cho phép. Nếu ứng dụng luôn dùng một database, hãy để cấu hình Neo4jClient quyết định thay vì truyền database lặp lại ở mọi nơi.

## 7. Giữ transaction Spring khi dùng QueryRunner

`Neo4jClient` được tích hợp với transaction management của Spring. Runner mà callback nhận được được cung cấp để các thao tác Driver có thể tham gia transaction đang hoạt động.

Ví dụ service có transaction:

```java
import java.util.Optional;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonMaintenanceService {

    private final Neo4jClient neo4jClient;

    public PersonMaintenanceService(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    @Transactional
    public long archiveInactivePeople() {
        return neo4jClient.delegateTo(runner -> {
            var summary = runner.run("""
                    MATCH (p:Person {active: false})
                    SET p.status = 'ARCHIVED'
                    """).consume();

            return Optional.of(summary.counters().propertiesSet());
        }).run().orElse(0L);
    }
}
```

Trong ví dụ, `@Transactional` mở transaction ở tầng service; delegation dùng runner do Neo4jClient cung cấp để thực thi trong phạm vi transaction đó. Nếu có lỗi làm transaction rollback, thay đổi trong transaction cũng được rollback theo.

Điều kiện quan trọng là Neo4jClient và `Neo4jTransactionManager` phải dùng cùng một `Driver` instance. Spring Boot starter thường cung cấp các bean được cấu hình đồng bộ; nếu tự tạo client hoặc transaction manager, hãy bảo đảm chúng chia sẻ cùng Driver.

### Tránh tự mở session bên trong transaction Spring

Đoạn code sau có thể tạo session và transaction riêng, không tự động tham gia transaction Spring hiện tại:

```java
// Không dùng cách này để tham gia transaction Spring đang hoạt động.
try (var session = driver.session()) {
    session.executeWrite(tx -> tx.run("MATCH (n) RETURN count(n)").consume());
}
```

Nếu thao tác này chạy trong một phương thức `@Transactional`, transaction được mở trực tiếp từ Driver có thể commit hoặc rollback độc lập. Khi cần tương tác mức thấp trong transaction Spring, hãy dùng runner được cấp bởi `delegateTo` hoặc `getQueryRunner()` của Neo4jClient theo API phiên bản dự án.

## 8. ReactiveNeo4jClient và ReactiveQueryRunner

Với ứng dụng reactive, dùng `ReactiveNeo4jClient.delegateTo(...)`. Callback nhận `ReactiveQueryRunner` và trả về `Mono<T>`; không chặn luồng bằng `.block()` bên trong callback:

```java
import org.springframework.data.neo4j.core.ReactiveNeo4jClient;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class ReactivePersonMaintenance {

    private final ReactiveNeo4jClient client;

    public ReactivePersonMaintenance(ReactiveNeo4jClient client) {
        this.client = client;
    }

    public Mono<Long> deleteUnusedPeople() {
        return client.delegateTo(runner ->
                Mono.from(runner.run("MATCH (p:Person {unused: true}) DETACH DELETE p").summary())
                        .map(summary -> summary.counters().nodesDeleted())
        ).run();
    }
}
```

Reactive runner sử dụng API reactive của Neo4j Driver. `Mono.from(...summary())` chuyển publisher summary thành `Mono`, sau đó `map` lấy số node đã xóa. Query chỉ thực thi khi publisher được subscribe.

Không trộn `Neo4jClient` imperative với `ReactiveQueryRunner`, hoặc `ReactiveNeo4jClient` với API blocking `QueryRunner`. Chọn client phù hợp với transaction manager và mô hình lập trình của ứng dụng.

## 9. Khi nào nên dùng getQueryRunner()?

Trong các phiên bản SDN hiện đại, `Neo4jClient` còn cung cấp `getQueryRunner()` để lấy một `QueryRunner` tương thích với Neo4j Java Driver và được gắn với Spring transaction hiện tại. Có thể dùng nó khi một API khác cần nhận runner thay vì nhận toàn bộ Neo4jClient.

```java
import org.neo4j.driver.QueryRunner;

QueryRunner runner = neo4jClient.getQueryRunner();
```

Với database cụ thể, API có overload nhận `DatabaseSelection`. Tên kiểu và các overload có thể thay đổi theo phiên bản SDN; hãy kiểm tra Javadoc của dependency đang dùng. Nếu chỉ cần chạy một nhóm thao tác ngay tại chỗ, `delegateTo(...)` thường thể hiện phạm vi callback và kết quả rõ ràng hơn.

Không giữ runner hoặc `Result` để dùng sau khi transaction/callback kết thúc. Hãy thực hiện và tiêu thụ các thao tác trong phạm vi mà runner được cấp.

## 10. Những lưu ý về an toàn và vòng đời tài nguyên

- Dùng named parameter cho mọi giá trị dữ liệu; không nối chuỗi đầu vào vào Cypher.
- Chỉ chọn database từ cấu hình hoặc danh sách được phép.
- Tiêu thụ kết quả bằng `single()`, `list(...)` hoặc `consume()` trước khi rời callback.
- Không mở session hoặc transaction độc lập nếu mục tiêu là tham gia transaction Spring.
- Không tự đóng Driver do Spring Boot quản lý.
- Không giữ `QueryRunner`, `Result` hoặc `Record` để sử dụng ngoài phạm vi tương tác.
- Với kết quả lớn, tránh `list()` nếu không cần giữ toàn bộ dữ liệu trong bộ nhớ; cân nhắc xử lý theo lô hoặc API streaming phù hợp.
- Khi dùng reactive runner, giữ pipeline non-blocking và chỉ thực thi khi publisher được subscribe.

## 11. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `Driver.session()` trong phương thức `@Transactional` | Session mới có thể chạy ngoài transaction Spring | Dùng runner từ `delegateTo` hoặc `getQueryRunner()` |
| Tạo Driver riêng cho Neo4jClient | Không đồng bộ transaction với transaction manager đang dùng Driver khác | Dùng cùng một Driver instance do Spring quản lý |
| Không tiêu thụ `Result` | Kết quả hoặc tài nguyên phía Driver chưa được hoàn tất đúng cách | Gọi `single()`, `list(...)` hoặc `consume()` trong callback |
| Trả `Result` ra ngoài callback | Dùng kết quả sau phạm vi runner hoặc transaction | Map sang DTO/giá trị đã materialize ngay trong callback |
| Dùng `single()` khi query có thể trả nhiều record | Driver báo lỗi vì kết quả không đúng cardinality | Chọn `list()` hoặc sửa điều kiện truy vấn |
| Dùng `Map.of()` với tham số null | Java ném lỗi trước khi truy vấn chạy | Chuẩn hóa null hoặc dùng map phù hợp |
| Nối chuỗi tham số vào Cypher | Rủi ro injection và lỗi escape | Dùng overload nhận parameter map |
| Gọi blocking API trong reactive callback | Chặn event loop và làm giảm khả năng mở rộng | Dùng `ReactiveQueryRunner` và Reactor operators |
| Nghĩ `delegateTo` tự động chạy trên database mong muốn | Truy vấn chạy vào database mặc định | Dùng `.in("database")` khi cần và kiểm soát tên database |

## 12. Bài tập thực hành

Tạo một số node `Person` và thử các thao tác mức thấp:

```cypher
CREATE
  (:Person {personId: 'P-101', name: 'Lan', active: true}),
  (:Person {personId: 'P-102', name: 'Minh', active: false}),
  (:Person {personId: 'P-103', name: 'Hoa', active: false});
```

Thực hiện các yêu cầu:

1. Dùng `delegateTo` và `QueryRunner` để đếm số node `Person`.
2. Bind một tham số bằng overload `runner.run(cypher, parameters)` để tìm người theo `personId`.
3. Dùng `single()` khi tìm theo khóa duy nhất và thử trường hợp không có kết quả.
4. Dùng `list(...)` để lấy danh sách người inactive thành DTO.
5. Dùng `consume()` để lấy `ResultSummary` sau khi cập nhật trạng thái một nhóm người.
6. Gọi phương thức trong một service `@Transactional`, sau đó chủ động phát sinh lỗi để quan sát rollback.
7. So sánh thao tác qua runner được ủy quyền với việc tự mở `Driver.session()`; giải thích vì sao hai cách có thể tham gia transaction khác nhau.
8. Nếu dự án dùng reactive stack, viết phiên bản `ReactiveNeo4jClient.delegateTo(...)` và xác nhận truy vấn chỉ chạy khi publisher được subscribe.

Sau bài tập, cần giải thích được vì sao `delegateTo` là điểm nối giữa API SDN và Driver, vai trò của runner được quản lý, cách chọn database và cách giữ transaction Spring khi cần thao tác mức thấp.

## Kết luận

Khi API fluent của `Neo4jClient` chưa đủ cho một use case, `delegateTo(...)` cho phép thực hiện thao tác qua query runner của Neo4j Java Driver. Callback imperative trả `Optional<T>`; reactive callback trả `Mono<T>`. Runner được cung cấp để tham gia transaction Spring, vì vậy cần dùng cùng Driver instance với transaction manager, tiêu thụ kết quả trong callback và tránh tự mở session độc lập khi cần tính nguyên tử. Chỉ chuyển xuống mức Driver khi có nhu cầu cụ thể; với truy vấn thông thường, tiếp tục dùng API fluent của Neo4jClient để code đơn giản và dễ bảo trì.
