# Ranh giới tích hợp Graph Data Science qua client hoặc procedure

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò riêng của Spring Data Neo4j (SDN) và Neo4j Graph Data Science (GDS).
- Nhận biết GDS là thư viện phía Neo4j, cung cấp thuật toán qua Cypher procedure.
- Gọi GDS procedure từ `Neo4jClient` và ánh xạ kết quả thành DTO của ứng dụng.
- Phân biệt `stream`, `stats`, `mutate` và `write`.
- Quản lý vòng đời graph projection trong GDS Graph Catalog.
- Chọn giữa `Neo4jClient`, repository `@Query` và Neo4j Java Driver.
- Quản lý transaction, quyền truy cập, bộ nhớ và tính nhất quán của dữ liệu.
- Thiết kế lớp tích hợp GDS mà không trộn kết quả thuật toán vào entity persistence một cách tùy tiện.

## 1. SDN và GDS giải quyết hai bài toán khác nhau

Spring Data Neo4j là tầng persistence của ứng dụng Java. SDN ánh xạ domain object sang node, relationship và property; cung cấp repository, template, transaction integration và API chạy Cypher.

Neo4j Graph Data Science là thư viện thuật toán đồ thị chạy phía Neo4j. GDS cung cấp các procedure để chiếu dữ liệu graph thành graph trong bộ nhớ, chạy thuật toán như PageRank, community detection, node similarity hoặc pathfinding, rồi trả kết quả hoặc ghi kết quả trở lại database.

Hai thành phần phối hợp qua giao thức Bolt và Cypher:

~~~text
Ứng dụng Spring
    |
    +-- Repository / Neo4jTemplate
    |       |
    |       +-- Đọc và ghi domain entity
    |
    +-- Neo4jClient
            |
            +-- Gửi CALL gds.*(...) qua Cypher
                    |
                    v
             Neo4j DBMS + GDS library
                    |
                    +-- Graph Catalog (in-memory graph)
                    +-- Graph algorithms
                    +-- Stream / mutate / write results
~~~

Điểm ranh giới cần nhớ:

- SDN không chứa implementation thuật toán GDS.
- `Neo4jClient` không chạy thuật toán trong JVM của ứng dụng; nó gửi Cypher procedure tới Neo4j.
- GDS chạy trên server Neo4j nơi thư viện GDS đã được cài đặt và bật.
- Kết quả GDS có thể là record chuyên biệt, không nhất thiết là một `@Node` entity.
- Graph projection của GDS là cấu trúc trong bộ nhớ của GDS Graph Catalog, không phải một tập node mới được lưu bằng repository.

Vì vậy, khi ứng dụng cần PageRank hoặc community detection, hãy xem GDS như một dịch vụ thuật toán phía database và dùng client để gọi procedure, nhận kết quả, rồi chuyển kết quả thành mô hình phù hợp ở application layer.

## 2. Điều kiện để gọi được GDS

Trước khi viết code Spring, môi trường Neo4j phải đáp ứng các điều kiện sau:

1. GDS library được cài đặt và tương thích với phiên bản Neo4j đang chạy.
2. Database đích cho phép gọi các procedure `gds.*` cần dùng.
3. Tài khoản kết nối có quyền đọc dữ liệu được chiếu và quyền thực thi procedure.
4. Máy chủ có đủ bộ nhớ cho graph projection và thuật toán.
5. Ứng dụng kết nối đúng database, vì graph catalog được quản lý theo database.

Có thể kiểm tra procedure có sẵn từ Neo4j Browser hoặc qua client:

~~~cypher
SHOW PROCEDURES
YIELD name
WHERE name STARTS WITH 'gds.'
RETURN name
ORDER BY name
~~~

Có thể kiểm tra phiên bản GDS:

~~~cypher
CALL gds.version()
YIELD version
RETURN version
~~~

Nếu procedure không tồn tại hoặc tài khoản không được phép gọi, lỗi phát sinh từ phía Neo4j. Việc thêm dependency Spring Data Neo4j vào ứng dụng không tự cài đặt GDS lên DBMS.

Với môi trường Neo4j managed service, hãy kiểm tra danh sách procedure và khả năng sử dụng GDS theo dịch vụ, phiên bản và gói triển khai đang dùng. Không giả định mọi môi trường Neo4j đều bật cùng một tập procedure.

## 3. Quy trình làm việc điển hình của GDS

Một workflow GDS thường gồm bốn giai đoạn:

1. **Project:** chọn node, relationship và property cần dùng để tạo graph trong bộ nhớ.
2. **Run:** chạy thuật toán trên graph projection.
3. **Consume:** nhận kết quả, xem thống kê hoặc ghi property kết quả.
4. **Drop:** giải phóng graph projection khi không còn cần dùng.

Ví dụ, ứng dụng có graph nghiệp vụ:

~~~text
(:Person {personId, name})
    -[:KNOWS]->
(:Person {personId, name})
~~~

Ứng dụng muốn tính PageRank để xếp hạng mức độ quan trọng của Person. GDS sẽ chiếu các node `Person` và relationship `KNOWS` vào Graph Catalog, chạy PageRank trên graph đó, rồi trả score.

~~~mermaid
flowchart TD
    A["Neo4j database: Person, KNOWS"] --> B["gds.graph.project"]
    B --> C["GDS in-memory graph"]
    C --> D["gds.pageRank.stream / stats / mutate / write"]
    D --> E["Neo4jClient nhận procedure result"]
    E --> F["DTO / API response"]
    D --> G["Ghi property về database nếu dùng write"]
    C --> H["gds.graph.drop"]
~~~

Graph projection chỉ chứa phần dữ liệu được chọn. Nó không tự động bao gồm mọi label, relationship hoặc property trong database.

Ở dạng viết tắt `gds.graph.project(graphName, 'Person', 'KNOWS')`, projection chỉ chọn node label và relationship type; nó không nạp sẵn các property để thuật toán dùng làm trọng số. Nếu thuật toán cần property, hãy khai báo property trong projection map, ví dụ:

~~~cypher
CALL gds.graph.project(
    $graphName,
    'Person',
    {KNOWS: {properties: 'strength'}}
)
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount
~~~

Sau đó, thuật toán hỗ trợ trọng số có thể tham chiếu `relationshipWeightProperty: 'strength'`. Hãy kiểm tra property có tồn tại và có kiểu dữ liệu hợp lệ trên các relationship được chiếu.

Một projection cũng không tự đồng bộ với các thay đổi phát sinh sau thời điểm project. Nếu ứng dụng ghi thêm Person hoặc KNOWS sau đó, graph trong bộ nhớ có thể không phản ánh thay đổi mới; hãy project lại hoặc dùng các thao tác cập nhật graph trong catalog theo nhu cầu.

Projection tồn tại trong bộ nhớ của Graph Catalog cho đến khi được drop, database nguồn bị dừng/xóa hoặc DBMS dừng. Vì vậy, đây là tài nguyên phía server cần được quản lý như một cache có dung lượng hữu hạn.

## 4. Gọi procedure bằng Neo4jClient

`Neo4jClient` là điểm tích hợp thuận tiện khi ứng dụng đã dùng SDN. Client cung cấp:

- Fluent API để bind tham số.
- Cách đọc record và Neo4j type system.
- Mapping tùy chỉnh bằng `fetchAs(...).mappedBy(...)`.
- Tích hợp với transaction management của Spring.

Ví dụ tạo graph projection:

~~~java
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Component;

@Component
public class PeopleGraphProjector {

    private final Neo4jClient client;

    public PeopleGraphProjector(Neo4jClient client) {
        this.client = client;
    }

    public GraphProjectionSummary projectPeople(String graphName) {
        return client.query("""
                CALL gds.graph.project(
                    $graphName,
                    'Person',
                    'KNOWS'
                )
                YIELD graphName, nodeCount, relationshipCount
                RETURN graphName, nodeCount, relationshipCount
                """)
            .bind(graphName).to("graphName")
            .fetchAs(GraphProjectionSummary.class)
            .mappedBy((typeSystem, record) ->
                new GraphProjectionSummary(
                    record.get("graphName").asString(),
                    record.get("nodeCount").asLong(),
                    record.get("relationshipCount").asLong()
                )
            )
            .one()
            .orElseThrow();
    }
}
~~~

DTO nhận kết quả:

~~~java
public record GraphProjectionSummary(
    String graphName,
    long nodeCount,
    long relationshipCount
) {
}
~~~

`graphName` được bind như một giá trị tham số. Tên procedure `gds.graph.project` và các phần cấu trúc Cypher được khai báo cố định trong ứng dụng.

Không ghép dữ liệu người dùng trực tiếp vào chuỗi query. Với tên graph, nên tạo tên nội bộ theo quy tắc ứng dụng và kiểm soát quyền sử dụng; không lấy tùy ý một tên do request gửi lên.

Nếu projection đã tồn tại trong Graph Catalog, lệnh project cùng tên có thể thất bại. Hãy dùng tên duy nhất cho từng lần chạy hoặc kiểm tra và quản lý vòng đời graph trước khi tạo.

## 5. Chạy thuật toán và ánh xạ kết quả thành DTO

Chế độ `stream` trả các record kết quả về cho client. Với PageRank, mỗi record chứa `nodeId` và `score`.

~~~java
import java.util.Collection;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Component;

@Component
public class PageRankReader {

    private final Neo4jClient client;

    public PageRankReader(Neo4jClient client) {
        this.client = client;
    }

    public Collection<PageRankResult> streamPageRank(
            String graphName,
            int maxIterations,
            double dampingFactor
    ) {
        return client.query("""
                CALL gds.pageRank.stream($graphName, {
                    maxIterations: $maxIterations,
                    dampingFactor: $dampingFactor
                })
                YIELD nodeId, score
                RETURN gds.util.asNode(nodeId).personId AS personId,
                       score
                ORDER BY score DESC
                """)
            .bind(graphName).to("graphName")
            .bind(maxIterations).to("maxIterations")
            .bind(dampingFactor).to("dampingFactor")
            .fetchAs(PageRankResult.class)
            .mappedBy((typeSystem, record) ->
                new PageRankResult(
                    record.get("personId").asString(),
                    record.get("score").asDouble()
                )
            )
            .all();
    }
}
~~~

DTO:

~~~java
public record PageRankResult(
    String personId,
    double score
) {
}
~~~

Ở đây:

- GDS chạy PageRank trên graph projection có tên `graphName`.
- `gds.util.asNode(nodeId)` lấy node tương ứng trong database để đọc property `personId`.
- `Neo4jClient` ánh xạ mỗi record thành `PageRankResult`.
- Kết quả trả về là dữ liệu đọc chuyên biệt, không cần khai báo `PageRankResult` thành `@Node`.

Nên trả về business ID như `personId` thay vì lưu hoặc công khai internal node ID. Internal ID là chi tiết kỹ thuật của database và không phải định danh nghiệp vụ ổn định để trao đổi giữa các hệ thống.

`fetchAs(...).mappedBy(...)` cho phép ứng dụng kiểm soát mapping. Nếu chỉ cần dữ liệu đơn giản, có thể dùng `fetch().all()` để nhận collection các map theo tên cột trả về.

## 6. Phân biệt các execution mode

GDS cung cấp các execution mode phổ biến cho thuật toán:

| Mode | Kết quả | Có ghi dữ liệu vào Neo4j database? | Mục đích |
|---|---|---|---|
| `stream` | Các record kết quả | Không | Trả score, component ID hoặc giá trị thuật toán về ứng dụng |
| `stats` | Thống kê tổng hợp | Không | Xem phân phối và số liệu của lần chạy |
| `mutate` | Thống kê lần chạy | Không | Gắn kết quả vào graph projection trong bộ nhớ |
| `write` | Thống kê và counters ghi | Có | Ghi property kết quả về node hoặc relationship trong database |

Ví dụ `stream`:

~~~cypher
CALL gds.pageRank.stream($graphName)
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).personId AS personId, score
ORDER BY score DESC
~~~

Ví dụ `stats`:

~~~cypher
CALL gds.pageRank.stats($graphName)
YIELD ranIterations, didConverge
RETURN ranIterations, didConverge
~~~

Ví dụ `mutate`:

~~~cypher
CALL gds.pageRank.mutate($graphName, {
    mutateProperty: 'pageRank'
})
YIELD nodePropertiesWritten, ranIterations
RETURN nodePropertiesWritten, ranIterations
~~~

Ví dụ `write`:

~~~cypher
CALL gds.pageRank.write($graphName, {
    writeProperty: 'pageRank'
})
YIELD nodePropertiesWritten, ranIterations
RETURN nodePropertiesWritten, ranIterations
~~~

Cần phân biệt rõ:

- `mutate` thêm property vào graph đang nằm trong GDS Graph Catalog. Property này chưa được ghi về node của database.
- `write` ghi property kết quả về graph database. Đây là thay đổi dữ liệu bền vững và cần được quản lý như một thao tác ghi.
- `stream` phù hợp khi ứng dụng cần đưa score vào API response, bảng xếp hạng hoặc một bước tính toán khác.
- `stats` phù hợp khi chỉ cần thông tin tổng hợp, không cần tải toàn bộ kết quả từng node.

Không dùng `mutate` rồi giả định repository có thể đọc property đó từ entity trong database. Nếu muốn SDN đọc được property sau thuật toán, hãy dùng `write` hoặc tự lưu kết quả qua một luồng ghi khác.

## 7. Quản lý vòng đời graph projection

Graph projection chiếm bộ nhớ trên Neo4j server. Khi không còn cần graph, hãy giải phóng nó bằng `gds.graph.drop`.

~~~cypher
CALL gds.graph.drop($graphName, false)
YIELD graphName
RETURN graphName
~~~

Tham số `false` yêu cầu không báo lỗi nếu graph không còn tồn tại. Điều này hữu ích trong bước cleanup.

Một service có thể kết hợp project, chạy thuật toán và drop:

~~~java
import java.util.Collection;
import java.util.UUID;

import org.springframework.stereotype.Service;

@Service
public class PeopleAnalyticsService {

    private final PeopleGraphProjector projector;
    private final PageRankReader pageRankReader;
    private final GraphCatalogWriter graphCatalogWriter;

    public PeopleAnalyticsService(
            PeopleGraphProjector projector,
            PageRankReader pageRankReader,
            GraphCatalogWriter graphCatalogWriter
    ) {
        this.projector = projector;
        this.pageRankReader = pageRankReader;
        this.graphCatalogWriter = graphCatalogWriter;
    }

    public Collection<PageRankResult> calculatePageRank() {
        String graphName = "people-" + UUID.randomUUID();
        try {
            projector.projectPeople(graphName);
            return pageRankReader.streamPageRank(
                graphName,
                20,
                0.85
            );
        } finally {
            graphCatalogWriter.dropIfExists(graphName);
        }
    }
}
~~~

`GraphCatalogWriter` có thể dùng `Neo4jClient` để gọi `gds.graph.drop`:

~~~java
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Component;

@Component
public class GraphCatalogWriter {

    private final Neo4jClient client;

    public GraphCatalogWriter(Neo4jClient client) {
        this.client = client;
    }

    public void dropIfExists(String graphName) {
        client.query("""
                CALL gds.graph.drop($graphName, false)
                YIELD graphName
                RETURN graphName
                """)
            .bind(graphName).to("graphName")
            .run();
    }
}
~~~

Một số lưu ý về lifecycle:

- Dùng graph name duy nhất để các request đồng thời không tranh chấp cùng một projection.
- Chỉ drop graph do workflow hiện tại sở hữu.
- Đặt cleanup trong `finally` để vẫn được gọi khi thuật toán hoặc mapping kết quả phát sinh lỗi.
- Bước cleanup nên được ghi log nếu thất bại; trong production, tránh để lỗi cleanup che mất exception gốc khiến thuật toán thất bại.
- Theo dõi graph catalog và bộ nhớ nếu ứng dụng giữ projection để tái sử dụng.
- Không để graph projection tạm thời tồn tại vô hạn sau khi request kết thúc.

Nếu cần tái sử dụng graph cho nhiều thuật toán, có thể giữ projection trong một khoảng thời gian có kiểm soát thay vì project lại cho mỗi thuật toán. Khi đó cần chính sách hết hạn, cleanup và đồng bộ khi dữ liệu nguồn thay đổi.

## 8. Repository @Query hay Neo4jClient?

Có thể gọi procedure qua repository method dùng `@Query`, nhưng kết quả GDS thường là DTO chuyên biệt, không phải aggregate `@Node`. Khi query cần bind nhiều tham số, map record tùy chỉnh hoặc phối hợp nhiều procedure, `Neo4jClient` thường dễ đọc và dễ kiểm soát hơn.

| Cách gọi | Phù hợp khi | Lưu ý |
|---|---|---|
| Repository `@Query` | Query procedure ngắn, kết quả map được vào projection/DTO | Giữ query gần repository và kiểm thử contract kết quả |
| `Neo4jClient` | Cần bind tham số, custom mapping, nhiều bước procedure hoặc transaction Spring | Thường là lựa chọn phù hợp cho lớp tích hợp GDS |
| Neo4j Java Driver trực tiếp | Cần API cấp thấp, session config riêng hoặc chức năng driver cụ thể | Session riêng không tự tham gia transaction Spring đang mở |

Ví dụ repository query có thể gọi một procedure stream:

~~~java
import java.util.Collection;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

@Node("Person")
public record Person(@Id String personId, String name) {
}

public interface PersonAnalyticsRepository
        extends Repository<Person, String> {

    @Query("""
        CALL gds.pageRank.stream($graphName)
        YIELD nodeId, score
        RETURN gds.util.asNode(nodeId).personId AS personId,
               score
        ORDER BY score DESC
        """)
    Collection<PageRankProjection> findPageRank(
        @Param("graphName") String graphName
    );
}
~~~

Projection:

~~~java
public interface PageRankProjection {
    String getPersonId();
    Double getScore();
}
~~~

Ví dụ này giả định projection `graphName` đã được tạo trước đó. Repository method chỉ gọi thuật toán và ánh xạ record; nó không tự tạo hoặc giải phóng graph projection.

Với query chuyên biệt hơn, `Neo4jClient` cung cấp mapping rõ ràng bằng `fetchAs(...).mappedBy(...)`.

Nếu dùng Java Driver trực tiếp trong ứng dụng SDN, cần chú ý transaction boundary. Một `Driver.session()` mới tạo session riêng; nó không tự tham gia transaction Spring chỉ vì method gọi nó có `@Transactional`. Nếu muốn query GDS cùng tham gia transaction đang quản lý, hãy ưu tiên `Neo4jClient` đã được cấu hình với SDN transaction infrastructure hoặc dùng cơ chế delegate Driver interaction do SDN cung cấp.

## 9. GDS và transaction của Spring

`Neo4jClient` tích hợp với transaction management của Spring. Nếu method service có `@Transactional`, các câu query được thực thi qua client có thể tham gia transaction hiện tại khi dùng cùng Driver và transaction manager.

Tuy nhiên, cần phân biệt hai loại trạng thái:

1. **Dữ liệu graph trong database:** node, relationship và property được ghi bởi Cypher hoặc GDS `write`.
2. **Graph projection trong GDS Graph Catalog:** graph trong bộ nhớ được tạo bởi `gds.graph.project`.

Projection là tài nguyên trong bộ nhớ của GDS, có vòng đời riêng. Không nên dựa vào rollback của transaction Spring để tự giải phóng projection. Hãy quản lý bằng `gds.graph.drop` và cleanup rõ ràng.

Với thao tác `write`, thuật toán cập nhật property trên node hoặc relationship trong database. Hãy xem đây là một thao tác ghi và xác định transaction boundary, quyền cập nhật và tác động lên dữ liệu ứng dụng.

Tránh đặt một workflow GDS tốn thời gian trong transaction nghiệp vụ dài nếu không cần thiết. Một quy trình phân tích có thể được chia thành các bước:

- Tạo projection.
- Chạy thuật toán.
- Lưu kết quả.
- Drop projection.

Mỗi bước cần có chính sách lỗi và cleanup phù hợp. Nếu yêu cầu nghiệp vụ đòi hỏi tất cả thay đổi database cùng commit hoặc rollback, hãy xác định rõ phần nào thực sự nằm trong transaction; graph projection vẫn cần lifecycle riêng.

## 10. Dữ liệu GDS và mô hình entity SDN

SDN ánh xạ entity theo domain model; GDS chiếu graph theo nhu cầu thuật toán. Hai mô hình có thể khác nhau.

Ví dụ, domain có:

~~~text
Person
  - id
  - personId
  - name
  - email
  - status
  - createdAt

KNOWS
  - since
  - source
~~~

Thuật toán PageRank có thể chỉ cần:

- Node label `Person`.
- Relationship type `KNOWS`.
- Property `personId` để liên kết kết quả về domain.
- Có thể thêm property weight nếu thuật toán cần trọng số.

Không cần project tất cả property của entity. Projection càng lớn càng tiêu thụ nhiều bộ nhớ và làm tăng chi phí xử lý.

Hãy tách các kiểu kết quả:

| Kiểu dữ liệu | Mục đích |
|---|---|
| `Person` entity | Đọc/ghi dữ liệu nghiệp vụ qua SDN |
| `PageRankResult` DTO | Trả score của thuật toán |
| `GraphProjectionSummary` DTO | Trả số node, relationship và tên projection |
| `CommunityResult` DTO | Trả community ID hoặc nhóm phát hiện được |

Không nên biến mọi kết quả thuật toán thành entity chỉ để tận dụng repository. Kết quả như score, rank, component ID hoặc similarity thường phù hợp với DTO, projection interface hoặc read model riêng.

Nếu GDS `write` lưu property `pageRank` vào Person, hãy quyết định có đưa property đó vào entity hay không. Chỉ thêm field vào entity khi nó thực sự là một phần của mô hình ứng dụng và có quy tắc cập nhật rõ ràng.

## 11. Tối ưu projection và thuật toán

Graph projection và thuật toán có thể tiêu thụ nhiều bộ nhớ. Trước khi chạy trên graph lớn:

- Chỉ chọn label và relationship cần thiết.
- Chỉ project node/relationship properties được thuật toán sử dụng.
- Với native projection, kiểm tra giới hạn kiểu property được GDS hỗ trợ ở phiên bản đang dùng; chuyển đổi hoặc mã hóa property không hỗ trợ sang kiểu được phép trước khi project.
- Dùng procedure estimate khi phù hợp để ước lượng bộ nhớ.
- Chọn execution mode phù hợp với kích thước kết quả.
- Đặt giới hạn số dòng trả về nếu chỉ cần top-N.
- Tránh stream hàng triệu record về ứng dụng nếu có thể dùng `write`, `mutate` hoặc `stats`.
- Theo dõi graph catalog để phát hiện projection tồn tại ngoài dự kiến.

Ví dụ giới hạn top 20 kết quả:

~~~cypher
CALL gds.pageRank.stream($graphName)
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).personId AS personId,
       score
ORDER BY score DESC
LIMIT $limit
~~~

Giới hạn `LIMIT` giảm lượng record truyền về ứng dụng. Tuy nhiên, thuật toán vẫn có thể phải tính score trên toàn graph trước khi sắp xếp và giới hạn kết quả.

Khi thuật toán cần property trọng số, hãy project property đó đúng kiểu và kiểm tra dữ liệu null hoặc thiếu trước khi chạy. Không giả định mọi relationship đều có property weight.

## 12. Quyền truy cập và an toàn khi gọi procedure

GDS procedure chạy với quyền của tài khoản kết nối và có thể đọc hoặc ghi lượng lớn dữ liệu. Hãy áp dụng các nguyên tắc sau:

- Chỉ cấp quyền execute procedure cần thiết.
- Tách quyền chạy thuật toán stream với quyền dùng chế độ write nếu kiến trúc cho phép.
- Kiểm soát database đích và loại graph được phép project.
- Bind mọi giá trị đầu vào như graph name, iteration count, damping factor và limit.
- Không ghép tham số người dùng vào tên procedure hoặc chuỗi Cypher.
- Kiểm tra giới hạn tài nguyên và quyền của người dùng trước khi chạy tác vụ nặng.
- Ghi log thời gian chạy, graph name, kích thước projection và summary counters.

Tên procedure là cú pháp query được ứng dụng định nghĩa, không phải giá trị bind tùy ý. Nếu cần chọn thuật toán theo request, hãy dùng allowlist ánh xạ lựa chọn nghiệp vụ sang một trong các query đã được định nghĩa sẵn.

Đối với GDS `write`, hãy xác định property nào được phép ghi và liệu ứng dụng khác có phụ thuộc vào property đó hay không. Không để một tác vụ phân tích ghi đè property nghiệp vụ có cùng tên.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Procedure không tồn tại | GDS chưa cài hoặc phiên bản không hỗ trợ procedure | Kiểm tra GDS installation và version |
| Không được phép gọi `gds.*` | Tài khoản thiếu quyền procedure | Cấp quyền tối thiểu cần thiết |
| Projection tạo thất bại | Graph name đã tồn tại hoặc projection không hợp lệ | Dùng tên duy nhất và kiểm tra label/relationship |
| Thuật toán báo thiếu property | Projection không đưa property cần thiết vào graph | Bổ sung property vào projection |
| `Neo4jClient` không map được kết quả | Tên cột hoặc kiểu dữ liệu khác DTO mong đợi | Kiểm tra YIELD/RETURN và mapping function |
| Không thấy property sau `mutate` | Mutate chỉ thay đổi graph trong bộ nhớ GDS | Dùng `write` nếu cần lưu vào database |
| Graph Catalog tăng liên tục | Không drop projection tạm thời | Cleanup bằng `gds.graph.drop` |
| Hai request ghi đè graph projection | Cùng sử dụng một graph name | Tạo tên duy nhất hoặc đồng bộ lifecycle |
| Đọc node bằng internal ID không ổn định | Đưa `nodeId` ra API như business ID | Trả về property định danh nghiệp vụ |
| Query GDS không tham gia Spring transaction | Dùng session Driver độc lập | Dùng Neo4jClient hoặc transaction integration phù hợp |
| Thuật toán làm DB thiếu bộ nhớ | Projection/algorithm quá lớn | Estimate, giảm projection và kiểm soát concurrency |
| `write` làm thay đổi dữ liệu ngoài ý muốn | Không phân biệt mode stream/mutate/write | Chọn mode và property đích rõ ràng |

## 14. Kiểm thử lớp tích hợp GDS

Unit test có thể kiểm tra mapper từ record sang DTO bằng dữ liệu mẫu. Tuy nhiên, chỉ integration test với Neo4j có GDS tương thích mới xác nhận được procedure, quyền thực thi, graph projection và kết quả thuật toán hoạt động trong môi trường thật.

Nên kiểm tra ít nhất các trường hợp:

1. Gọi `gds.version()` hoặc liệt kê procedure để xác nhận GDS đã sẵn sàng.
2. Project một graph nhỏ và xác nhận số node, relationship.
3. Chạy `stream` và xác nhận kết quả được ánh xạ thành DTO.
4. Xác nhận `stream` và `stats` không ghi property lên node nguồn.
5. Chạy `mutate` và xác nhận property chỉ có trong projection trước khi drop.
6. Chạy `write` và xác nhận property kết quả xuất hiện trong database.
7. Gọi cleanup khi thuật toán thành công và khi thuật toán phát sinh lỗi.
8. Chạy hai workflow đồng thời để xác nhận graph name không xung đột.

Môi trường test phải cài đúng GDS library. Một Neo4j test server thông thường không tự có GDS chỉ vì test dùng SDN hoặc Testcontainers. Nếu pipeline CI không thể cung cấp GDS, hãy tách unit test mapping khỏi integration test chạy trên môi trường Neo4j có plugin.

## 15. Bài tập thực hành

Giả sử ứng dụng quản lý mạng lưới `Person` với relationship `KNOWS`. Mỗi Person có `personId`, `name`; mỗi relationship có thể có property `strength`.

Thực hiện:

1. Kiểm tra Neo4j server đã cài GDS và tài khoản có quyền gọi procedure.
2. Tạo graph projection chỉ gồm Person và KNOWS.
3. Đọc `graphName`, `nodeCount` và `relationshipCount` từ kết quả projection.
4. Chạy `gds.pageRank.stream` qua `Neo4jClient`.
5. Ánh xạ `personId` và `score` thành `PageRankResult`.
6. Trả về top 10 Person theo score.
7. Chạy `gds.pageRank.stats` và so sánh kết quả thống kê.
8. Chạy `gds.pageRank.mutate` rồi kiểm tra property chỉ nằm trong graph projection.
9. Chạy `gds.pageRank.write` và xác nhận property được ghi về Person trong database.
10. Drop projection trong `finally`, kể cả khi bước tính toán thất bại.
11. Viết integration test xác nhận dữ liệu stream không làm thay đổi node.
12. Viết integration test xác nhận write mode tạo property kết quả.
13. Thử hai request đồng thời với graph name khác nhau.
14. Đo bộ nhớ và thời gian khi project toàn bộ graph so với một projection giới hạn.

Câu hỏi tự kiểm tra:

- GDS là thư viện chạy ở ứng dụng Java hay phía Neo4j server?
- Vì sao `Neo4jClient` có thể gọi GDS mà không cần một API thuật toán riêng trong SDN?
- Graph projection khác `@Node` entity ở điểm nào?
- `stream`, `stats`, `mutate` và `write` khác nhau ra sao?
- Vì sao `mutate` không làm property xuất hiện trong database?
- Khi nào nên dùng repository `@Query` và khi nào nên dùng `Neo4jClient`?
- Vì sao không nên dùng internal node ID làm định danh API?
- Vì sao cần drop projection sau khi hoàn tất?
- Direct Driver session có tự tham gia transaction Spring không?
- Những yếu tố nào ảnh hưởng đến bộ nhớ khi chạy GDS?

## Kết luận

Neo4j Graph Data Science cung cấp thuật toán đồ thị dưới dạng Cypher procedure chạy phía Neo4j. Spring Data Neo4j không triển khai các thuật toán này; ứng dụng dùng `Neo4jClient`, repository `@Query` hoặc Java Driver để gọi procedure. Trong các workflow cần bind tham số và ánh xạ kết quả chuyên biệt, `Neo4jClient` thường là điểm tích hợp rõ ràng vì nó phối hợp với transaction management của Spring.

Hãy phân biệt graph projection trong bộ nhớ với entity được SDN quản lý. Chọn `stream` khi cần nhận kết quả, `stats` khi cần thống kê, `mutate` khi cần cập nhật projection và `write` khi cần lưu property kết quả về database. Quản lý graph name, bộ nhớ, quyền procedure và cleanup tường minh; dùng DTO cho kết quả thuật toán và business ID để liên kết kết quả với domain model.

## Tài liệu tham khảo

- [Neo4j Graph Data Science: Getting started](https://neo4j.com/docs/graph-data-science/current/getting-started/)
- [Neo4j Graph Data Science: Running algorithms](https://neo4j.com/docs/graph-data-science/current/common-usage/running-algos/)
- [Neo4j Graph Data Science: Graph Catalog operations](https://neo4j.com/docs/graph-data-science/current/operations-reference/graph-operation-references/)
- [Neo4j Graph Data Science: Creating graphs and projections](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-creation/)
- [Neo4j Graph Data Science: Native projection, property selection and lifecycle](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-creation/graph-project/)
- [Spring Data Neo4j: Neo4jClient](https://docs.spring.io/spring-data/neo4j/reference/appendix/neo4j-client.html)
- [Spring Data Neo4j FAQ: Custom queries and custom mappings](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j API: Neo4jClient.MappingSpec](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/Neo4jClient.MappingSpec.html)
