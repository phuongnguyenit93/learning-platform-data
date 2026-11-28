# Bảo vệ endpoint trả đồ thị khỏi truy vấn sâu hoặc dữ liệu quá lớn

Endpoint trả graph có thể tạo tải lớn dù request ban đầu rất nhỏ. Một client chỉ cần gửi ID của một node rồi yêu cầu mở rộng qua nhiều tầng relationship; nếu mỗi node có nhiều hàng xóm, số node cần duyệt tăng rất nhanh theo độ sâu. Kết quả có thể làm database tốn CPU và bộ nhớ, tăng dữ liệu truyền qua Bolt, khiến SDN hydrate nhiều object và làm response HTTP quá lớn.

Khi xây dựng API trên Spring Data Neo4j (SDN), cần kiểm soát đồng thời **đầu vào request**, **phạm vi traversal trong Cypher**, **số node/relationship trả về**, **quyền truy cập từng nhánh graph** và **thời gian thực thi**. Không nên chỉ giới hạn số phần tử ở Java sau khi database đã duyệt một graph không giới hạn.

## 1. Vì sao endpoint graph dễ bị quá tải?

Giả sử một node có trung bình 20 relationship đi ra. Nếu endpoint mở rộng 4 tầng, số node được xét theo lý thuyết có thể tăng theo cấp số nhân:

```text
Độ sâu 0:       1 node
Độ sâu 1:      20 node
Độ sâu 2:     400 node
Độ sâu 3:   8.000 node
Độ sâu 4: 160.000 node
```

Đây chỉ là mô hình minh họa, vì graph thực tế có thể có node trùng, chu trình và độ rộng không đồng đều. Tuy nhiên, nó cho thấy một tham số `depth` không giới hạn có thể khiến một request tạo ra lượng công việc rất lớn.

Các nguồn rủi ro thường gặp:

- Variable-length path không có giới hạn trên, ví dụ `[:KNOWS*]`.
- Trả toàn bộ entity graph dù màn hình chỉ cần vài property.
- Cho client tự chọn relationship type, label, sort field hoặc Cypher fragment.
- Không giới hạn page size, số path hoặc số node trong response.
- Chỉ kiểm tra quyền truy cập node gốc, bỏ qua node trung gian và node đích.
- Cho phép nhiều request graph nặng chạy đồng thời mà không có rate limit hoặc timeout.

## 2. Đặt ngân sách cho mỗi request

Trước khi viết query, hãy xác định ngân sách tối đa mà endpoint được phép sử dụng. Ví dụ dưới đây dùng giới hạn minh họa; hãy điều chỉnh theo kích thước graph, SLA và tải thực tế của hệ thống.

| Hạng mục | Giới hạn minh họa | Mục đích |
|---|---:|---|
| Độ sâu traversal | 0–3 | Giới hạn số tầng relationship |
| Số path trả về | 1–32 | Giới hạn số đường đi được trả về |
| Node tối đa trong response | 97 | 1 root + tối đa 32 path × 3 bước |
| Relationship tối đa | 96 | Tối đa 32 path × 3 relationship |
| Thời gian transaction | 3 giây | Ngắt thao tác vượt ngân sách thời gian |
| Page size cho danh sách root | 1–100 | Không tải danh sách không giới hạn |

Ngân sách phải được áp dụng ở nhiều lớp. Controller xác thực tham số, Cypher giới hạn traversal, service giới hạn cấu trúc response, còn transaction timeout và rate limiting bảo vệ tài nguyên khi có nhiều request đồng thời.

## 3. Không để client tự quyết định giới hạn tối đa

Client có thể yêu cầu độ sâu nhỏ hơn giới hạn hệ thống, nhưng không được tự nâng giới hạn. Một cách đơn giản là định nghĩa hằng số dùng chung:

```java
public final class GraphLimits {

    public static final int MAX_DEPTH = 3;
    public static final int MAX_PATHS = 32;
    public static final int MAX_NODES = 1 + MAX_PATHS * MAX_DEPTH;
    public static final int MAX_EDGES = MAX_PATHS * MAX_DEPTH;

    private GraphLimits() {
    }
}
```

Các giá trị này là giới hạn cứng của API. Nếu muốn thay đổi theo môi trường, có thể đưa chúng vào `@ConfigurationProperties`, nhưng vẫn phải kiểm tra giá trị cấu hình lúc khởi động để không vô tình cho phép giới hạn quá lớn.

Không nhận một tham số `maxDepth` tùy ý rồi truyền thẳng vào query. API chỉ nên nhận giá trị trong khoảng đã được server phê duyệt.

## 4. Xác thực tham số ngay tại controller

Spring MVC có thể dùng Jakarta Bean Validation để từ chối request sai trước khi gọi service. Ví dụ endpoint nhận ID, độ sâu và số path tối đa:

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/people")
@Validated
public class PersonGraphController {

    private final PersonGraphService graphService;
    private final CurrentTenant currentTenant;

    public PersonGraphController(
            PersonGraphService graphService,
            CurrentTenant currentTenant) {
        this.graphService = graphService;
        this.currentTenant = currentTenant;
    }

    @GetMapping("/{personId}/graph")
    public GraphResponse graph(
            @PathVariable @NotBlank String personId,
            @RequestParam(defaultValue = "2")
            @Min(0) @Max(GraphLimits.MAX_DEPTH) int depth,
            @RequestParam(defaultValue = "20")
            @Min(1) @Max(GraphLimits.MAX_PATHS) int maxPaths) {

        String tenantId = currentTenant.requireTenantId();
        return graphService.loadGraph(personId, tenantId, depth, maxPaths);
    }
}
```

`CurrentTenant` là abstraction do ứng dụng định nghĩa để lấy tenant từ principal đã xác thực. Tenant không được lấy từ query parameter do client tự gửi, vì client có thể sửa giá trị đó để thử truy cập graph của tenant khác.

Ứng dụng cần có dependency Bean Validation và cấu hình method validation phù hợp với phiên bản Spring đang dùng. Khi tham số vượt `@Min` hoặc `@Max`, trả lỗi `400 Bad Request` với thông báo ngắn, không gọi database. Không tự động clamp mọi giá trị sai về giới hạn tối đa; trả lỗi giúp client biết hợp đồng API.

## 5. Trả DTO thay vì serialize entity graph trực tiếp

Không nên trả thẳng entity SDN từ endpoint graph nếu client chỉ cần một read model cụ thể. Entity có thể chứa relationship không liên quan, vòng tham chiếu và property nội bộ.

Định nghĩa response DTO nhỏ:

Mỗi record dưới đây được đặt trong file Java riêng (`GraphNode.java`, `GraphEdge.java` và `GraphResponse.java`):

```java
import java.util.List;

public record GraphNode(String id, String name) {}

public record GraphEdge(String source, String target, String type) {}

public record GraphResponse(
    String rootId,
    int requestedDepth,
    List<GraphNode> nodes,
    List<GraphEdge> edges,
    boolean truncated
) {}
```

DTO giúp endpoint công bố chính xác các trường được phép trả về. Không đưa password hash, token, internal flags, tenant metadata hoặc property nhạy cảm vào node projection chỉ vì chúng tồn tại trên entity.

Nếu client chỉ cần một số trường, hãy chọn projection hoặc scalar property trong Cypher. Tránh `RETURN p` rồi serialize toàn bộ object graph cho một màn hình chỉ cần `personId` và `name`.

## 6. Giới hạn traversal ngay trong Cypher

Giả sử graph có node `Person` và relationship `KNOWS`. Một query không giới hạn như:

```cypher
MATCH p = (root:Person {personId: $personId})-[:KNOWS*]-(target:Person)
RETURN p
```

có thể duyệt rất sâu. Hãy đặt giới hạn trên cố định trong pattern và dùng tham số đã validate để yêu cầu độ sâu nhỏ hơn hoặc bằng giới hạn đó:

```cypher
MATCH (root:Person {personId: $personId, tenantId: $tenantId})
MATCH p = (root)-[:KNOWS*1..3]-(target:Person)
WHERE length(p) <= $depth
  AND all(n IN nodes(p) WHERE n.tenantId = $tenantId)
WITH p, target
ORDER BY length(p), target.personId
LIMIT $pathLimit
RETURN [n IN nodes(p) | {id: n.personId, name: n.name}] AS nodes,
       [r IN relationships(p) | {
           source: startNode(r).personId,
           target: endNode(r).personId,
           type: type(r)
       }] AS edges,
       length(p) AS hops;
```

Trong query này:

1. `*1..3` đặt giới hạn traversal cứng ở database, không phụ thuộc client.
2. `$depth` chỉ thu hẹp giới hạn cứng, ví dụ client yêu cầu 1 hoặc 2 tầng.
3. `all(n IN nodes(p) ...)` kiểm tra tenant trên mọi node trong path, gồm cả node trung gian.
4. `LIMIT $pathLimit` giới hạn số path trả về.
5. Projection map trong `RETURN` chỉ lấy ID, tên và thông tin cạnh cần cho response.

`depth = 0` có nghĩa chỉ trả root node; service vẫn thêm root vào response dù query tìm path từ 1 đến 3 bước không trả dòng nào. `LIMIT` ở đây giới hạn số path, không phải số node duy nhất. Service cần loại trùng node và edge khi hợp nhất nhiều path.

Lưu ý: `LIMIT` không thay thế giới hạn độ sâu. Query có thể vẫn phải khám phá nhiều candidate path trước khi chọn đủ kết quả. Hãy kết hợp độ sâu nhỏ, relationship type cố định, tenant predicate, index cho root lookup, timeout và kiểm tra query plan.

## 7. Ánh xạ kết quả Cypher bằng Neo4jClient

Tạo DTO nội bộ cho từng path trả về:

```java
import java.util.List;

public record GraphPathRow(
    List<GraphNode> nodes,
    List<GraphEdge> edges,
    int hops
) {}
```

DAO dùng `Neo4jClient` để bind tham số và ánh xạ record:

```java
import java.util.List;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

@Repository
public class PersonGraphDao {

    private final Neo4jClient neo4jClient;

    public PersonGraphDao(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public List<GraphPathRow> findPaths(
            String personId,
            String tenantId,
            int depth,
            int pathLimit) {

        return neo4jClient.query("""
            MATCH (root:Person {personId: $personId, tenantId: $tenantId})
            MATCH p = (root)-[:KNOWS*1..3]-(target:Person)
            WHERE length(p) <= $depth
              AND all(n IN nodes(p) WHERE n.tenantId = $tenantId)
            WITH p, target
            ORDER BY length(p), target.personId
            LIMIT $pathLimit
            RETURN [n IN nodes(p) | {id: n.personId, name: n.name}] AS nodes,
                   [r IN relationships(p) | {
                       source: startNode(r).personId,
                       target: endNode(r).personId,
                       type: type(r)
                   }] AS edges,
                   length(p) AS hops
            """)
            .bind(personId).to("personId")
            .bind(tenantId).to("tenantId")
            .bind(depth).to("depth")
            .bind(pathLimit).to("pathLimit")
            .fetchAs(GraphPathRow.class)
            .mappedBy((typeSystem, record) -> new GraphPathRow(
                record.get("nodes").asList(node -> new GraphNode(
                    node.get("id").asString(),
                    node.get("name").isNull()
                        ? null
                        : node.get("name").asString()
                )),
                record.get("edges").asList(edge -> new GraphEdge(
                    edge.get("source").asString(),
                    edge.get("target").asString(),
                    edge.get("type").asString()
                )),
                record.get("hops").asInt()
            ))
            .all()
            .stream()
            .toList();
    }
}
```

Tên label `Person` và relationship type `KNOWS` được cố định trong query. Chỉ các giá trị dữ liệu như ID, tenant, depth và limit được bind thành tham số. Không nối label, relationship type hoặc một đoạn Cypher do client gửi vào query.

## 8. Hợp nhất path và áp dụng giới hạn response

Một node có thể xuất hiện trong nhiều path. Hãy dùng map theo ID để loại trùng và giới hạn số node/edge được trả về.

Repository root:

```java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {
    Optional<Person> findByPersonIdAndTenantId(String personId, String tenantId);
}
```

Entity tối thiểu dùng cho bước kiểm tra root:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String personId;

    private String tenantId;
    private String name;

    protected Person() {
    }

    public String getPersonId() {
        return personId;
    }

    public String getName() {
        return name;
    }
}
```

Service chỉ trả root thuộc tenant hiện tại, lấy tối đa `maxPaths` path và hợp nhất các node/edge:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonGraphService {

    private final PersonRepository personRepository;
    private final PersonGraphDao graphDao;

    public PersonGraphService(
            PersonRepository personRepository,
            PersonGraphDao graphDao) {
        this.personRepository = personRepository;
        this.graphDao = graphDao;
    }

    @Transactional(readOnly = true, timeout = 3)
    public GraphResponse loadGraph(
            String personId,
            String tenantId,
            int depth,
            int maxPaths) {

        if (depth < 0 || depth > GraphLimits.MAX_DEPTH
                || maxPaths < 1 || maxPaths > GraphLimits.MAX_PATHS) {
            throw new InvalidGraphRequestException("Giới hạn graph không hợp lệ");
        }

        Person root = personRepository
            .findByPersonIdAndTenantId(personId, tenantId)
            .orElseThrow(() -> new PersonNotFoundException(personId));

        List<GraphPathRow> rows = graphDao.findPaths(
            personId, tenantId, depth, maxPaths + 1
        );

        boolean truncated = rows.size() > maxPaths;
        Map<String, GraphNode> nodes = new LinkedHashMap<>();
        Map<String, GraphEdge> edges = new LinkedHashMap<>();

        nodes.put(root.getPersonId(),
            new GraphNode(root.getPersonId(), root.getName()));

        for (GraphPathRow row : rows.stream().limit(maxPaths).toList()) {
            for (GraphNode node : row.nodes()) {
                nodes.putIfAbsent(node.id(), node);
            }
            for (GraphEdge edge : row.edges()) {
                String key = edge.source() + "|" + edge.type() + "|" + edge.target();
                edges.putIfAbsent(key, edge);
            }
        }

        return new GraphResponse(
            root.getPersonId(),
            depth,
            List.copyOf(nodes.values()),
            List.copyOf(edges.values()),
            truncated
        );
    }
}
```

Vì `depth <= 3` và `maxPaths <= 32`, số node lý thuyết tối đa sau khi loại trùng là `1 + 32 × 3 = 97`; số edge tối đa là `32 × 3 = 96`. Query lấy thêm một path (`maxPaths + 1`) để xác định có thể còn kết quả bị cắt hay không, nhưng service chỉ đưa tối đa `maxPaths` path vào response.

`timeout = 3` là transaction timeout tính bằng giây trong cấu hình Spring transaction. Cần xác nhận transaction manager/driver đang dùng áp dụng timeout như mong muốn; vẫn nên có giới hạn thời gian ở driver/server hoặc gateway. Timeout không thay thế giới hạn depth và response size.

`PersonNotFoundException` và `CurrentTenant` là thành phần nghiệp vụ do ứng dụng định nghĩa. Trả cùng một kết quả not-found cho root không tồn tại và root không thuộc tenant hiện tại giúp tránh tiết lộ sự tồn tại của dữ liệu tenant khác.

## 9. Bảo vệ mọi node trên đường đi, không chỉ root

Kiểm tra quyền ở root là chưa đủ. Một path có thể bắt đầu từ node mà người dùng được phép xem nhưng đi qua node trung gian hoặc node đích thuộc tenant khác.

Query ví dụ dùng:

```cypher
AND all(n IN nodes(p) WHERE n.tenantId = $tenantId)
```

Điều kiện này yêu cầu mọi node trên path có cùng tenant. Với mô hình phân quyền phức tạp hơn, có thể cần kiểm tra:

- Tenant hoặc organization của từng node.
- Quyền truy cập relationship, nếu relationship có ACL hoặc trạng thái riêng.
- Trạng thái node đã bị ẩn, xóa mềm hoặc chưa được publish.
- Người dùng có quyền xem loại dữ liệu nhạy cảm trong từng nhánh hay không.

Không tải graph trước rồi lọc node bị cấm ở Java nếu database có thể áp dụng điều kiện ngay trong query. Lọc sau khi tải có thể đã làm lộ dữ liệu qua log, cache, metric hoặc chi phí xử lý, đồng thời tạo ra response graph không nhất quán.

## 10. Giới hạn relationship type và property được trả về

Không cho client truyền tự do tên relationship type hoặc label vào pattern. Nếu API cần hỗ trợ nhiều kiểu traversal, dùng allowlist phía server:

```java
public enum GraphView {
    FRIENDS,
    TEAMMATES,
    FOLLOWERS
}
```

Mỗi `GraphView` được ánh xạ tới một query hoặc một nhánh query cố định đã được kiểm tra. Không nối `request.getRelationshipType()` vào Cypher.

Tương tự, chỉ trả các property cần cho use case. Ví dụ node response chỉ có `id` và `name`; không trả toàn bộ `properties(n)` nếu graph chứa email, số điện thoại, access token hoặc metadata nội bộ.

## 11. Giới hạn page size cho endpoint liệt kê graph root

Endpoint liệt kê nhiều node gốc cũng cần giới hạn page size. Không nhận `size` tùy ý hoặc gọi `findAll()` cho dữ liệu lớn.

Ví dụ dùng `Pageable` với giới hạn tối đa:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

public class GraphPagePolicy {

    public PageRequest safePageRequest(int page, int size) {
        if (page < 0 || size < 1 || size > 100) {
            throw new InvalidGraphRequestException("Page hoặc size không hợp lệ");
        }

        return PageRequest.of(
            page,
            size,
            Sort.by(Sort.Direction.ASC, "personId")
        );
    }
}
```

Chỉ cho phép sort theo field đã allowlist. Không truyền tên property tùy ý từ client vào `Sort.by` nếu property đó không thuộc hợp đồng API. Với danh sách rất lớn, cân nhắc keyset scrolling thay vì page number sâu.

## 12. Không dùng `@Depth` của Neo4j-OGM cũ để bảo vệ SDN hiện đại

Các ví dụ cũ của Neo4j-OGM có thể dùng `@Depth` hoặc tham số depth của session để giới hạn graph mapping. Spring Data Neo4j hiện đại dùng entity mapping, aggregate boundary, projection và custom Cypher; không nên sao chép annotation `@Depth` của OGM vào ứng dụng SDN.

Đặc biệt, giới hạn mapping ở Java không thay thế giới hạn traversal trong Cypher. Nếu query đã duyệt hàng triệu path rồi mapper chỉ giữ một vài node, database vẫn phải trả chi phí tìm kiếm và xử lý các path đó.

## 13. Dùng projection cho endpoint chỉ cần một góc nhìn

Nếu endpoint chỉ cần vài property và một relationship cụ thể, hãy định nghĩa projection thay vì tải aggregate đầy đủ:

```java
public interface PersonCard {
    String getPersonId();
    String getName();

    TeamCard getTeam();

    interface TeamCard {
        String getTeamId();
        String getName();
    }
}
```

Repository có thể trả projection:

```java
import java.util.List;

List<PersonCard> findByTenantId(String tenantId);
```

Đây là method bổ sung vào `PersonRepository` đã khai báo ở phần 8, không phải một repository thứ hai cùng tên.

Projection giới hạn property và relationship mà SDN cần hydrate theo hợp đồng đọc. Nó phù hợp với màn hình hoặc API có cấu trúc ổn định. Với graph traversal tùy biến theo depth và fan-out, custom Cypher thường dễ đặt giới hạn hơn.

## 14. Giới hạn query complexity trong GraphQL endpoint

Nếu graph được trả qua GraphQL, ngoài giới hạn depth của graph database còn phải giới hạn độ sâu và độ phức tạp của chính GraphQL selection set.

Ví dụ client có thể yêu cầu:

```graphql
query {
  person(id: "P-100") {
    friends(first: 100) {
      friends(first: 100) {
        friends(first: 100) {
          id
          name
        }
      }
    }
  }
}
```

Ngay cả khi từng resolver có pagination, nhiều tầng nested field vẫn có thể tạo lượng truy vấn lớn. GraphQL endpoint nên áp dụng:

- Maximum query depth.
- Query complexity/cost limit có trọng số cho field collection.
- Maximum page size cho mọi connection/list field.
- Resolver batching hoặc DataLoader để tránh N+1 query.
- Timeout, rate limit và giới hạn concurrency.
- Authorization trong từng resolver và database query, không chỉ ở root resolver.

Các API GraphQL library có cơ chế instrumentation/validation riêng; cấu hình cụ thể phụ thuộc phiên bản thư viện. Dù dùng REST hay GraphQL, giới hạn traversal và quyền truy cập ở Cypher vẫn cần được áp dụng.

## 15. Timeout và hủy truy vấn

Một request có giới hạn depth vẫn có thể tốn thời gian nếu root node có degree rất lớn hoặc query plan không hiệu quả. Cần nhiều lớp bảo vệ thời gian:

1. Transaction timeout trong Spring transaction definition.
2. Transaction/query timeout ở driver hoặc server nếu cấu hình triển khai hỗ trợ.
3. HTTP request timeout ở reverse proxy/API gateway.
4. Cancellation khi client ngắt kết nối, nếu stack web và driver hỗ trợ truyền cancellation tới thao tác database.

Không đặt timeout quá dài chỉ để tránh lỗi. Một endpoint graph nên có SLA rõ ràng và trả lỗi timeout phù hợp khi vượt ngân sách. Với query nặng, kiểm tra `EXPLAIN` và `PROFILE` để sửa nguyên nhân thay vì chỉ tăng timeout.

## 16. Rate limit và giới hạn concurrency

Giới hạn mỗi request không đủ nếu một client có thể gửi hàng trăm request graph cùng lúc. Nên áp dụng rate limit theo user, API key hoặc tenant ở gateway/application layer.

Một chính sách minh họa:

| Loại request | Chính sách ví dụ |
|---|---|
| Graph depth 0–1 | Quota cao hơn |
| Graph depth 2–3 | Quota thấp hơn hoặc tính cost cao hơn |
| Request có `maxPaths` lớn | Tính thêm vào request cost |
| Tenant vượt concurrency limit | Trả `429 Too Many Requests` hoặc `503` theo chính sách |
| Request lặp lại cùng tham số | Có thể dùng cache nếu dữ liệu và quyền truy cập cho phép |

Không dùng một quota giống nhau cho request chỉ đọc một node và request mở rộng graph ba tầng. Có thể tính cost đơn giản từ `depth`, `maxPaths` và page size, sau đó dùng cost đó trong rate limiter.

## 17. Cache response graph có điều kiện

Cache có thể giảm tải cho các graph ít thay đổi, nhưng cần đưa quyền truy cập vào cache key. Nếu cache chỉ theo `personId`, người dùng tenant A có thể nhận response đã cache của tenant B.

Cache key nên bao gồm các yếu tố ảnh hưởng kết quả, ví dụ:

- Tenant và authorization scope.
- Root ID.
- Graph view/relationship allowlist.
- Depth và maxPaths/page size.
- Phiên bản dữ liệu hoặc cache invalidation token.

Không cache response chứa dữ liệu cá nhân nhạy cảm ở phạm vi dùng chung nếu chưa có chính sách phù hợp. Khi node hoặc relationship thay đổi, cần invalidation hoặc TTL ngắn đủ để chấp nhận độ trễ dữ liệu.

## 18. Index và query plan cho root lookup

Graph traversal thường bắt đầu từ một root node. Hãy bảo đảm điều kiện tìm root dùng ID hoặc property có index/constraint phù hợp.

Ví dụ constraint cho `personId`:

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;
```

Constraint giúp tìm root theo `personId` và bảo vệ uniqueness. Nếu tenant lookup là một điều kiện thường xuyên khác, hãy đánh giá index phù hợp với truy vấn thực tế; không tạo index tùy tiện cho mọi property.

Dùng `PROFILE` với dữ liệu gần production để xem:

- Root lookup có dùng index/constraint seek không.
- Số row trung gian sau mỗi relationship expansion.
- Số DB hits và thời gian từng operator.
- Query có tạo Cartesian product hoặc lặp path không cần thiết.
- `LIMIT` được áp dụng ở giai đoạn nào của execution plan.

`LIMIT` trong Cypher là một giới hạn kết quả, không bảo đảm mọi operator phía trước chỉ làm việc với số lượng tương ứng. Hãy kiểm tra plan và kiểm soát fan-out bằng pattern, filter và query design.

## 19. Kiểm thử giới hạn và quyền truy cập

Integration test nên xác nhận endpoint từ chối request vượt giới hạn và không trả dữ liệu ngoài phạm vi quyền.

Các trường hợp nên kiểm tra:

1. `depth = 0` chỉ trả root node.
2. `depth = 1` không trả node ở tầng thứ hai.
3. `depth` lớn hơn `MAX_DEPTH` bị từ chối trước khi truy vấn.
4. `maxPaths` lớn hơn `MAX_PATHS` bị từ chối.
5. Một root có nhiều path không làm response vượt giới hạn node/edge đã đặt.
6. Path đi qua node thuộc tenant khác không xuất hiện trong response.
7. Root ID thuộc tenant khác trả not-found hoặc kết quả không tiết lộ sự tồn tại.
8. Property nhạy cảm không xuất hiện trong DTO/JSON.
9. Request timeout và rate limit được xử lý theo hợp đồng API.
10. Query plan với dữ liệu lớn không tạo số row trung gian vượt ngân sách vận hành.
11. GraphQL selection set quá sâu hoặc quá phức tạp bị từ chối trước khi resolver thực thi.
12. Cache không trả dữ liệu giữa các tenant hoặc authorization scope khác nhau.

Không chỉ kiểm tra status code. Hãy kiểm tra số node, edge, property trả về và log query để xác nhận database cũng được giới hạn.

## 20. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Request nhỏ nhưng query chạy rất lâu | Variable-length path không giới hạn hoặc fan-out lớn | Đặt depth cứng, relationship allowlist và timeout. |
| Response JSON quá lớn | Trả entity graph đầy đủ hoặc page size không giới hạn | Dùng DTO/projection, giới hạn node/edge và page size. |
| Client gửi `depth=1000` | Không validate tham số ở controller | Áp dụng `@Min`/`@Max` và giới hạn cứng trong Cypher. |
| Node tenant khác xuất hiện trong graph | Chỉ kiểm tra quyền ở root | Kiểm tra tenant/ACL trên mọi node và relationship trong path. |
| Query vẫn tốn CPU dù response có `LIMIT` | Database phải mở rộng nhiều candidate path trước khi giới hạn kết quả | Giảm depth/fan-out, lọc sớm, kiểm tra `PROFILE`. |
| Có thể truyền relationship type tùy ý | Nối chuỗi request vào Cypher | Dùng enum/allowlist và query cố định. |
| Nhiều request graph đồng thời làm nghẽn DB | Chỉ giới hạn mỗi request, không có quota tổng | Thêm rate limit và concurrency limit theo user/tenant. |
| Cache trả nhầm dữ liệu tenant | Cache key thiếu tenant hoặc authorization scope | Đưa tenant/scope và tham số graph vào cache key. |
| Dùng `@Depth` nhưng không giới hạn query | Nhầm API Neo4j-OGM cũ với SDN hiện đại | Dùng projection, aggregate boundary và Cypher bounded traversal. |

## 21. Quy trình bảo vệ endpoint graph

1. Xác định graph view và property cần trả về cho từng endpoint.
2. Đặt giới hạn cứng cho depth, paths, nodes, edges và page size.
3. Validate tham số ở controller trước khi gọi service.
4. Lấy tenant/authorization scope từ principal đã xác thực, không nhận từ client.
5. Giới hạn relationship type, label và filter bằng allowlist.
6. Dùng Cypher có upper bound cố định, filter quyền trên mọi node trong path và `LIMIT` số path.
7. Ánh xạ DTO nhỏ; loại trùng node/edge và xác nhận response không vượt ngân sách.
8. Đặt transaction/query timeout và HTTP timeout phù hợp.
9. Áp dụng rate limit/concurrency limit theo user hoặc tenant.
10. Kiểm tra index và execution plan bằng `PROFILE` với dữ liệu đủ lớn.
11. Nếu dùng GraphQL, thêm query depth/complexity limit và pagination cho từng list field.
12. Kiểm thử boundary, tenant isolation, response size, timeout, rate limit và cache isolation.

## 22. Ghi nhớ

Endpoint trả graph cần giới hạn dữ liệu từ lúc nhận request tới khi truy vấn và tạo response. Hãy validate depth/page size, đặt upper bound cố định trong Cypher, giới hạn số path và số node/edge, dùng DTO/projection để chỉ trả property cần thiết, đồng thời kiểm tra quyền trên mọi node của đường đi. Không cho client tự gửi label, relationship type hoặc Cypher fragment.

`LIMIT` chỉ giới hạn số kết quả, không bảo đảm toàn bộ traversal phía trước rẻ; hãy kết hợp depth nhỏ, fan-out có kiểm soát, root index, timeout và `PROFILE`. Rate limit, concurrency limit và cache key có tenant scope bảo vệ hệ thống trước nhiều request nặng. Nếu dùng GraphQL, cần thêm giới hạn query depth/complexity ở tầng GraphQL. Các lớp kiểm soát này giúp endpoint giữ response nhỏ, không lộ graph ngoài quyền và duy trì hiệu năng ổn định khi dữ liệu tăng.

## Tài liệu tham khảo

- [Spring Data Neo4j – Projections](https://docs.spring.io/spring-data/neo4j/reference/projections/sdn-projections.html)
- [Spring Data Neo4j – Custom Queries](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html)
- [Neo4j Cypher Manual – Variable-length patterns](https://neo4j.com/docs/cypher-manual/current/patterns/variable-length-patterns/)
- [Neo4j Cypher Manual – PROFILE and EXPLAIN](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Spring Framework – Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
